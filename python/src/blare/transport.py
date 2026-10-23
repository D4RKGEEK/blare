"""Delivery — SPEC.md section 3.2.

Alerts leave on a worker thread behind a bounded queue. Both halves of that
matter: a chat webhook sitting on a 5 second timeout must not add 5 seconds to
a production request, and a chat outage must not turn into unbounded memory
growth or back-pressure on real traffic. When the queue is full Blare drops
alerts and counts the drops, because dropping an alert is survivable and
stalling the application is not.
"""

from __future__ import annotations

import atexit
import contextlib
import logging
import queue
import threading
from collections.abc import Sequence
from typing import Any

from .sinks import Sink

log = logging.getLogger("blare")

QUEUE_SIZE = 100
_SHUTDOWN = object()


class Transport:
    """A single worker thread fanning events out to every sink."""

    def __init__(self, sinks: Sequence[Sink], timeout: int = 5) -> None:
        self._sinks = list(sinks)
        self._timeout = timeout
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=QUEUE_SIZE)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._closed = False
        self.dropped = 0
        self.delivered = 0
        self.failed = 0

    def _ensure_thread(self) -> None:
        """Start the worker lazily, so importing Blare starts no threads."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            thread = threading.Thread(
                target=self._run, name="blare-transport", daemon=True
            )
            self._thread = thread
            thread.start()
            atexit.register(self.close)

    def submit(self, payload: dict[str, Any]) -> bool:
        """Queue one event. Returns False if it was dropped."""
        if self._closed:
            return False
        self._ensure_thread()
        try:
            self._queue.put_nowait(payload)
            return True
        except queue.Full:
            self.dropped += 1
            log.warning(
                "blare: delivery queue full; dropped an alert (%d dropped in total)",
                self.dropped,
            )
            return False

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is _SHUTDOWN:
                    return
                self._deliver(item)
            except Exception as exc:  # pragma: no cover - defensive
                log.warning("blare: transport error: %s", exc)
            finally:
                self._queue.task_done()

    def _deliver(self, payload: dict[str, Any]) -> None:
        # Each sink is independent: a dead Discord webhook must not stop the
        # Slack alert that someone is actually watching.
        for sink in self._sinks:
            try:
                if sink.send(payload):
                    self.delivered += 1
                else:
                    self.failed += 1
            except Exception as exc:  # pragma: no cover - defensive
                self.failed += 1
                log.warning("blare: sink %s raised: %s", sink.redacted_url(), exc)

    def flush(self, timeout: float | None = None) -> bool:
        """Wait for the queue to drain. True if it emptied in time."""
        if self._thread is None:
            return True
        deadline = timeout if timeout is not None else float(self._timeout)
        finished = threading.Event()

        def waiter() -> None:
            self._queue.join()
            finished.set()

        threading.Thread(target=waiter, daemon=True).start()
        return finished.wait(deadline)

    def close(self, timeout: float | None = None) -> None:
        """Flush within the deadline, then stop the worker."""
        if self._closed:
            return
        self._closed = True
        self.flush(timeout)
        if self._thread is not None and self._thread.is_alive():
            # Best effort: if the queue is still full at exit the daemon thread
            # dies with the process anyway.
            with contextlib.suppress(queue.Full):
                self._queue.put_nowait(_SHUTDOWN)


class SyncTransport(Transport):
    """Delivers on the calling thread.

    Used by the self-test and by host test suites, where "did it actually go
    out?" has to be answerable before the function returns.
    """

    def submit(self, payload: dict[str, Any]) -> bool:
        self._deliver(payload)
        return True

    def flush(self, timeout: float | None = None) -> bool:
        return True

    def close(self, timeout: float | None = None) -> None:
        self._closed = True
