"""Dedupe state — SPEC.md section 5.4.

The store is the only shared, mutable thing in Blare. It is what lets four
Gunicorn workers seeing the same crash send one alert instead of four, so the
default backend is a lock-guarded file rather than per-process memory.

Every store exposes the same transaction: read the whole document, let the
caller mutate it, write it back while holding an exclusive lock.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

log = logging.getLogger("blare")

RETENTION_SECONDS = 24 * 60 * 60
SCHEMA = 1


def empty_document() -> dict[str, Any]:
    return {"schema": SCHEMA, "groups": {}, "bucket": {}, "suppressed_by_cap": 0}


def _valid(document: Any) -> bool:
    return (
        isinstance(document, dict)
        and document.get("schema") == SCHEMA
        and isinstance(document.get("groups"), dict)
    )


class Store:
    """Interface shared by every backend."""

    name = "base"

    @contextmanager
    def transaction(self) -> Iterator[dict[str, Any]]:  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:
        """Release any held resources."""

    @staticmethod
    def prune(document: dict[str, Any], now: float) -> None:
        """Forget groups nobody has seen for a day."""
        groups = document["groups"]
        for key in [
            key
            for key, group in groups.items()
            if now - float(group.get("last_seen", 0)) > RETENTION_SECONDS
        ]:
            del groups[key]


class MemoryStore(Store):
    """Per-process state. Correct, but each process alerts on its own."""

    name = "memory"

    def __init__(self) -> None:
        self._document = empty_document()
        self._lock = threading.Lock()

    @contextmanager
    def transaction(self) -> Iterator[dict[str, Any]]:
        with self._lock:
            yield self._document


class FileStore(Store):
    """State in one file, shared by every process on the host.

    Uses an exclusive advisory lock for the whole read-modify-write, which is
    what makes the count in "847 times" the host's count rather than one
    worker's. Writes go through a temporary file and an atomic replace so a
    crash mid-write cannot leave a truncated document behind.
    """

    name = "file"

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self._thread_lock = threading.Lock()

    @contextmanager
    def transaction(self) -> Iterator[dict[str, Any]]:
        import fcntl

        with self._thread_lock, open(self._lock_path, "a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                document = self._read()
                yield document
                self._write(document)
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read(self) -> dict[str, Any]:
        try:
            document = json.loads(self.path.read_text("utf-8"))
        except (FileNotFoundError, ValueError, OSError):
            return empty_document()
        return document if _valid(document) else empty_document()

    def _write(self, document: dict[str, Any]) -> None:
        # Write to a sibling temporary file and rename it over the target, so a
        # crash mid-write cannot leave a truncated document behind.
        descriptor, temporary = tempfile.mkstemp(
            dir=self.path.parent, prefix=self.path.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(document, handle)
            os.replace(temporary, self.path)
        except OSError as exc:
            log.warning("blare: could not persist dedupe state: %s", exc)
            with contextlib.suppress(OSError):
                os.unlink(temporary)


class RedisStore(Store):
    """State in Redis, shared across hosts.

    Needed once the service runs on more than one machine: without it each host
    deduplicates independently, and a ten-replica deployment sends ten alerts
    for one outage.
    """

    name = "redis"

    def __init__(self, url: str, key: str, timeout: int = 5) -> None:
        try:
            import redis
        except ImportError:  # pragma: no cover - optional dependency
            raise ImportError(
                "BLARE_STATE=redis://… needs the redis package: "
                "pip install 'blare[redis]'"
            ) from None
        self._client = redis.Redis.from_url(
            url, socket_timeout=timeout, socket_connect_timeout=timeout
        )
        self._key = key
        self._lock_key = f"{key}:lock"

    @contextmanager
    def transaction(self) -> Iterator[dict[str, Any]]:
        acquired = self._acquire()
        try:
            raw = self._client.get(self._key)
            document = empty_document()
            if raw:
                try:
                    parsed = json.loads(raw)
                except ValueError:
                    parsed = None
                if _valid(parsed):
                    document = parsed
            yield document
            self._client.set(self._key, json.dumps(document), ex=RETENTION_SECONDS)
        finally:
            if acquired:
                self._release()

    def _acquire(self, attempts: int = 50) -> bool:
        for _ in range(attempts):
            if self._client.set(self._lock_key, b"1", nx=True, px=2000):
                return True
            time.sleep(0.02)
        # Proceeding without the lock risks a lost update, which costs at worst
        # a duplicate alert. Blocking production traffic would cost more.
        log.warning("blare: redis dedupe lock busy; proceeding without it")
        return False

    def _release(self) -> None:
        try:
            self._client.delete(self._lock_key)
        except Exception as exc:  # pragma: no cover - network dependent
            log.debug("blare: releasing redis lock failed: %s", exc)

    def close(self) -> None:
        with contextlib.suppress(Exception):  # pragma: no cover
            self._client.close()


def default_file_path(service: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in service) or "blare"
    return Path(tempfile.gettempdir()) / f"blare-{safe}.json"


def build_store(spec: str, service: str, timeout: int = 5) -> Store:
    """Create the store named by ``BLARE_STATE``.

    Falls back to memory, loudly, rather than preventing the application from
    starting: an alerting library must never be the reason a deploy fails.
    """
    spec = (spec or "file").strip()
    try:
        if spec == "memory":
            return MemoryStore()
        if spec == "file":
            return FileStore(default_file_path(service))
        if spec.startswith("file:"):
            return FileStore(spec[len("file:") :])
        if spec.startswith(("redis://", "rediss://", "unix://")):
            return RedisStore(spec, key=f"blare:{service}", timeout=timeout)
    except Exception as exc:
        log.warning(
            "blare: state backend %r unavailable (%s); "
            "falling back to in-process memory, so each process will "
            "deduplicate on its own",
            spec,
            exc,
        )
        return MemoryStore()
    log.warning("blare: unknown BLARE_STATE=%r; using in-process memory", spec)
    return MemoryStore()
