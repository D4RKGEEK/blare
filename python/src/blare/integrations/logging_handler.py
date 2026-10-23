"""Log capture — SPEC.md section 4.1.

This is the integration that needs no new code at all: the application already
calls ``logger.error(...)``, and attaching this handler turns those calls into
alerts. It is also how most teams already wire up Slack by hand, so it is the
path that should feel familiar.
"""

from __future__ import annotations

import logging

from ..config import LEVELS
from ..fingerprint import Location, relative_path


class BlareHandler(logging.Handler):
    """A logging handler that routes records through Blare's pipeline."""

    def __init__(self, client, level: str = "ERROR") -> None:
        super().__init__(level=LEVELS.get(level.upper(), logging.ERROR))
        self._client = client

    def emit(self, record: logging.LogRecord) -> None:
        # Blare logs its own problems through the "blare" logger. Capturing
        # those would mean a failing webhook generating alerts about itself.
        if record.name == "blare" or record.name.startswith("blare."):
            return
        try:
            self._handle(record)
        except Exception:  # pragma: no cover - logging must never raise
            self.handleError(record)

    def _handle(self, record: logging.LogRecord) -> None:
        location = Location(
            file=relative_path(record.pathname or ""),
            function=record.funcName or "",
            line=record.lineno or 0,
        )
        extra = {"logger_level": record.levelname}

        exc = record.exc_info[1] if record.exc_info else None
        if exc is not None:
            # An exception carried on the record classifies the event, so
            # `logger.exception("failed")` groups by the exception rather than
            # by the wording of the log line.
            self._client.capture_exception(
                exc,
                level=record.levelname.lower(),
                logger=record.name,
                extra=extra,
            )
            return

        self._client.capture_message(
            record.getMessage(),
            level=record.levelname.lower(),
            type_name=record.name,
            logger=record.name,
            location=location,
            extra=extra,
        )
