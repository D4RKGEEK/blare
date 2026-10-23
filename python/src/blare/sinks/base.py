"""Sinks — SPEC.md section 3.

A sink is one webhook URL. Users paste whatever Slack, Discord or Teams gave
them and Blare works out the rest: nobody should have to learn a URL scheme in
order to send a message to a chat room.

Delivery uses only the standard library, so installing Blare pulls in nothing.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

from ..errors import ConfigError

log = logging.getLogger("blare")

RETRY_DELAYS = (1.0, 3.0)
MAX_RETRY_AFTER = 30.0

SLACK_HOSTS = ("hooks.slack.com",)
DISCORD_HOSTS = (
    "discord.com",
    "discordapp.com",
    "ptb.discord.com",
    "canary.discord.com",
)
TEAMS_HOST_SUFFIXES = (".webhook.office.com", ".logic.azure.com", ".logic.azure.us")

COLOR_BY_STATE = {
    "new": "#d1242f",
    "recurring": "#bc4c00",
    "resolved": "#1a7f37",
}
EMOJI_BY_STATE = {"new": "🔴", "recurring": "🟠", "resolved": "🟢"}


def detect_provider(url: str) -> tuple[str, str]:
    """Return ``(provider, url)`` for a sink spec — section 3.1."""
    spec = (url or "").strip()
    if not spec:
        raise ConfigError("empty sink")
    if spec == "console":
        return "console", spec

    if "+" in spec.split("://", 1)[0]:
        prefix, _, rest = spec.partition("+")
        prefix = prefix.lower()
        if prefix not in PROVIDERS:
            raise ConfigError(
                f"unknown provider {prefix!r} in sink {spec!r}; "
                f"use one of {sorted(PROVIDERS)}"
            )
        return prefix, rest

    parts = urlsplit(spec)
    if parts.scheme not in ("http", "https"):
        raise ConfigError(
            f"unsupported scheme {parts.scheme!r} in sink {spec!r}; "
            "sinks are http(s) webhook URLs"
        )
    host = (parts.hostname or "").lower()
    if host in SLACK_HOSTS:
        return "slack", spec
    if host in DISCORD_HOSTS:
        return "discord", spec
    if any(host.endswith(suffix) for suffix in TEAMS_HOST_SUFFIXES):
        return "teams", spec
    return "generic", spec


class Sink:
    """Renders the canonical event for one provider and posts it."""

    provider = "generic"

    def __init__(self, url: str, timeout: int = 5) -> None:
        self.url = url
        self.timeout = timeout

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.redacted_url()}>"

    def redacted_url(self) -> str:
        """The URL with its secret path removed, safe to log.

        A webhook URL *is* the credential, so it must never reach a log file.
        """
        parts = urlsplit(self.url)
        return f"{parts.scheme}://{parts.netloc}/…"

    def render(self, payload: dict[str, Any]) -> Any:
        """Provider-specific message body. Default: the event itself."""
        return payload

    def send(self, payload: dict[str, Any]) -> bool:
        """Deliver one event, retrying per section 3.2.

        Never raises: a broken webhook must not become an application failure.
        """
        body = json.dumps(self.render(payload)).encode("utf-8")
        attempts = len(RETRY_DELAYS) + 1
        for attempt in range(attempts):
            retryable, detail = self._post(body)
            if detail is None:
                return True
            if not retryable or attempt == attempts - 1:
                log.warning(
                    "blare: delivery to %s failed (%s); giving up",
                    self.redacted_url(),
                    detail,
                )
                return False
            delay = RETRY_DELAYS[attempt]
            if isinstance(detail, tuple):
                delay = detail[1] or delay
                detail = detail[0]
            log.debug(
                "blare: delivery to %s failed (%s); retrying in %.1fs",
                self.redacted_url(),
                detail,
                delay,
            )
            time.sleep(delay)
        return False

    def _post(self, body: bytes) -> tuple[bool, Any]:
        """Return ``(retryable, detail)``; ``detail`` of None means success."""
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "blare-python",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout):
                return False, None
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code < 600
            after = self._retry_after(exc)
            detail: Any = f"HTTP {exc.code}"
            if retryable and after:
                detail = (detail, after)
            return retryable, detail
        except urllib.error.URLError as exc:
            return True, f"connection error: {exc.reason}"
        except Exception as exc:  # pragma: no cover - defensive
            return False, f"unexpected error: {exc}"

    @staticmethod
    def _retry_after(exc: urllib.error.HTTPError) -> float | None:
        raw = exc.headers.get("Retry-After") if exc.headers else None
        if not raw:
            return None
        try:
            seconds = float(raw)
        except ValueError:
            return None
        return seconds if 0 < seconds <= MAX_RETRY_AFTER else None


def summarize(payload: dict[str, Any]) -> str:
    """The one-line "how bad is it" summary shared by every renderer."""
    occurrences = payload.get("occurrences") or {}
    count = int(occurrences.get("since_last_alert") or 0)
    window = int(occurrences.get("window_seconds") or 0)
    if payload.get("state") == "resolved":
        return "Recovered — no further occurrences"
    if count > 1:
        minutes = max(1, window // 60)
        return f"{count} times in the last {minutes} min"
    return "First occurrence"


def location_line(payload: dict[str, Any]) -> str:
    location = payload.get("location") or {}
    file = location.get("file") or ""
    if not file:
        return "unknown location"
    return f"{file}:{location.get('line', 0)} in {location.get('function') or '?'}"


def stack_text(payload: dict[str, Any], limit: int = 10) -> str:
    frames = (payload.get("stack") or [])[:limit]
    return "\n".join(frames)


# Populated by sinks/__init__ once the concrete classes are imported.
PROVIDERS: dict[str, type[Sink]] = {}
