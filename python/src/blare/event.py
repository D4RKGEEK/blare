"""The canonical event — SPEC.md section 7.

Every sink renders from this structure and the ``generic`` provider posts it
verbatim, which makes it a public interface: fields may be added within spec
version 1, never removed or retyped.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .version import __version__

SPEC_VERSION = "1"
SDK_NAME = "blare-python"
TITLE_LIMIT = 300


def rfc3339(timestamp: float) -> str:
    """RFC 3339 with millisecond precision, in UTC."""
    moment = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def build_title(type_name: str, message: str) -> str:
    message = " ".join((message or "").split())
    title = f"{type_name}: {message}" if message else type_name
    return title[:TITLE_LIMIT]


@dataclass
class Event:
    """A failure, resolved but not yet redacted or rendered."""

    fingerprint: str
    kind: str
    level: str
    type_name: str
    message: str
    service: str
    environment: str
    host: str
    timestamp: float
    state: str = "new"
    logger: str = ""
    file: str = ""
    function: str = ""
    line: int = 0
    stack: list[str] = field(default_factory=list)
    request: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    since_last_alert: int = 1
    total: int = 1
    first_seen: float = 0.0
    window_seconds: int = 0
    rate_limited: int = 0

    @property
    def title(self) -> str:
        return build_title(self.type_name, self.message)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the section 7 payload."""
        context: dict[str, Any] = {"extra": self.extra or {}}
        if self.request:
            context["request"] = self.request
        return {
            "blare_version": SPEC_VERSION,
            "fingerprint": self.fingerprint,
            "kind": self.kind,
            "state": self.state,
            "level": self.level.lower(),
            "title": self.title,
            "type": self.type_name,
            "message": self.message,
            "logger": self.logger,
            "service": self.service,
            "environment": self.environment,
            "host": self.host,
            "timestamp": rfc3339(self.timestamp),
            "runtime": {
                "language": "python",
                "version": platform.python_version(),
            },
            "sdk": {"name": SDK_NAME, "version": __version__},
            "location": {
                "file": self.file,
                "function": self.function,
                "line": self.line,
            },
            "stack": list(self.stack),
            "context": context,
            "occurrences": {
                "since_last_alert": self.since_last_alert,
                "total": self.total,
                "first_seen": rfc3339(self.first_seen or self.timestamp),
                "window_seconds": self.window_seconds,
            },
            "rate_limited": self.rate_limited,
        }
