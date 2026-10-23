"""The Blare client.

Pipeline for every captured failure, in this order:

    classify → fingerprint → decide → redact → render → deliver

Fingerprinting happens *before* redaction so that changing a redaction rule can
never regroup history, and redaction happens before rendering so that no sink
can ever see a raw secret.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections.abc import Sequence
from typing import Any

from . import fingerprint as fp
from .config import Config
from .decide import Candidate, Decider
from .event import Event, build_title
from .redact import Redactor
from .sinks import Sink, build_sinks
from .state import build_store
from .transport import SyncTransport, Transport

log = logging.getLogger("blare")


def _type_name(exc: BaseException) -> str:
    """Fully-qualified exception type, so two `ValidationError`s stay distinct."""
    cls = type(exc)
    module = getattr(cls, "__module__", "")
    if module in ("builtins", "__main__", "", None):
        return cls.__name__
    return f"{module}.{cls.__name__}"


class Blare:
    """A configured Blare instance.

    Usually created once by :func:`blare.init`, but constructing it directly is
    supported and is how the test suite avoids global state.
    """

    def __init__(
        self,
        config: Config | None = None,
        *,
        sinks: Sequence[Sink] | None = None,
        synchronous: bool = False,
        clock: Any = time.time,
        **overrides: Any,
    ) -> None:
        self.config = config or Config.from_env(**overrides)
        self._clock = clock
        self._redactor = Redactor(self.config.redact)
        self._local = threading.local()
        self._handler: logging.Handler | None = None
        self._previous_excepthook: Any = None
        self.suppressed = 0
        self.dropped_by_ignore = 0

        self._store = build_store(
            self.config.state, self.config.service, self.config.timeout
        )
        self._decider = Decider(
            self._store,
            dedupe_window=self.config.dedupe_window,
            max_per_hour=self.config.max_per_hour,
            ignore=self.config.ignore,
            resolve_after=self.config.resolve_after,
        )

        resolved_sinks = (
            list(sinks)
            if sinks is not None
            else build_sinks(self.config.sinks, self.config.timeout)
        )
        if self.config.dry_run and sinks is None:
            from .sinks import ConsoleSink

            log.info("blare: BLARE_DRY_RUN is set; alerts go to stderr only")
            resolved_sinks = [ConsoleSink()]

        transport_class = SyncTransport if synchronous else Transport
        self._transport = transport_class(resolved_sinks, self.config.timeout)
        self.sinks = resolved_sinks

        if not self.config.enabled:
            log.info("blare: disabled by BLARE_ENABLED")
        elif not self.config.sinks and sinks is None:
            log.warning(
                "blare: no sinks configured, so nothing will be sent. "
                "Set BLARE_SINKS to your webhook URL."
            )

    # -- capture ---------------------------------------------------------

    def capture_exception(
        self,
        exc: BaseException | None = None,
        *,
        level: str = "error",
        logger: str = "",
        extra: dict[str, Any] | None = None,
        request: dict[str, Any] | None = None,
    ) -> bool:
        """Report an exception. Returns True if an alert was delivered."""
        if exc is None:
            exc = sys.exc_info()[1]
        if exc is None:
            return False
        tb = exc.__traceback__
        location, stack = fp.location_from_traceback(tb)
        return self._process(
            kind="exception",
            type_name=_type_name(exc),
            message=str(exc),
            level=level,
            logger=logger,
            location=location,
            stack=stack,
            extra=extra,
            request=request,
        )

    def capture_message(
        self,
        message: str,
        *,
        level: str = "error",
        type_name: str = "",
        logger: str = "",
        location: fp.Location | None = None,
        stack: Sequence[str] | None = None,
        extra: dict[str, Any] | None = None,
        request: dict[str, Any] | None = None,
    ) -> bool:
        """Report a failure that is not an exception."""
        return self._process(
            kind="log",
            type_name=type_name or logger or "message",
            message=message,
            level=level,
            logger=logger,
            location=location or fp.Location(),
            stack=list(stack or []),
            extra=extra,
            request=request,
        )

    # -- pipeline --------------------------------------------------------

    def _process(
        self,
        *,
        kind: str,
        type_name: str,
        message: str,
        level: str,
        logger: str,
        location: fp.Location,
        stack: list[str],
        extra: dict[str, Any] | None,
        request: dict[str, Any] | None,
    ) -> bool:
        if not self.config.active:
            return False
        # Blare's own failures are logged, and that log must not come back in
        # as an event whose delivery fails and logs again.
        if getattr(self._local, "busy", False):
            return False
        self._local.busy = True
        try:
            return self._process_inner(
                kind=kind,
                type_name=type_name,
                message=message,
                level=level,
                logger=logger,
                location=location,
                stack=stack,
                extra=extra,
                request=request,
            )
        except Exception as exc:
            # Capture is instrumentation. If instrumentation breaks, the
            # application still has to work.
            log.warning("blare: capture failed: %s", exc)
            return False
        finally:
            self._local.busy = False

    def _process_inner(
        self,
        *,
        kind: str,
        type_name: str,
        message: str,
        level: str,
        logger: str,
        location: fp.Location,
        stack: list[str],
        extra: dict[str, Any] | None,
        request: dict[str, Any] | None,
    ) -> bool:
        now = float(self._clock())
        fingerprint = fp.compute(kind, type_name, location.key(), message)
        candidate = Candidate(
            fingerprint=fingerprint,
            type_name=type_name,
            title=build_title(type_name, message),
            logger=logger,
        )

        outcome = self._decider.evaluate(candidate, now)
        if outcome.decision is None:
            self.dropped_by_ignore += 1
            return False

        for resolved_fingerprint, notice in outcome.resolved:
            self._emit(
                Event(
                    fingerprint=resolved_fingerprint,
                    kind=kind,
                    level="info",
                    type_name=type_name,
                    message="",
                    service=self.config.service,
                    environment=self.config.environment,
                    host=self.config.host,
                    timestamp=now,
                    state=notice.state,
                    total=notice.total,
                    first_seen=notice.first_seen,
                    window_seconds=self.config.dedupe_window,
                )
            )

        decision = outcome.decision
        if not decision.send:
            self.suppressed += 1
            return False

        return self._emit(
            Event(
                fingerprint=fingerprint,
                kind=kind,
                level=level,
                type_name=type_name,
                message=message,
                service=self.config.service,
                environment=self.config.environment,
                host=self.config.host,
                timestamp=now,
                state=decision.state,
                logger=logger,
                file=location.file,
                function=location.function,
                line=location.line,
                stack=stack[: self.config.stack_frames],
                request=request,
                extra=extra or {},
                since_last_alert=decision.since_last_alert,
                total=decision.total,
                first_seen=decision.first_seen,
                window_seconds=self.config.dedupe_window,
                rate_limited=decision.rate_limited,
            )
        )

    def _emit(self, event: Event) -> bool:
        payload = self._redactor.value(event.to_dict())
        return self._transport.submit(payload)

    # -- lifecycle -------------------------------------------------------

    def install_logging(self, level: str | None = None) -> logging.Handler:
        """Attach to the root logger so existing `logger.error` calls alert."""
        from .integrations.logging_handler import BlareHandler

        if self._handler is not None:
            return self._handler
        handler = BlareHandler(self, level=level or self.config.level)
        logging.getLogger().addHandler(handler)
        self._handler = handler
        return handler

    def install_excepthook(self) -> None:
        """Alert on a crash, then let the process die as it would have."""
        from .integrations.excepthook import install

        self._previous_excepthook = install(self)

    def flush(self, timeout: float | None = None) -> bool:
        """Wait for queued alerts to be delivered."""
        return self._transport.flush(timeout)

    def close(self, timeout: float | None = None) -> None:
        """Flush, detach the logging handler, and release the store."""
        if self._handler is not None:
            logging.getLogger().removeHandler(self._handler)
            self._handler = None
        self._transport.close(timeout)
        self._store.close()

    def selftest(self) -> list[tuple[str, bool]]:
        """Send one synthetic alert to each sink and report the outcome.

        "Is this wired up?" should be answerable on a quiet afternoon rather
        than discovered during the outage it was installed for.
        """
        event = Event(
            fingerprint="selftest00000000",
            kind="log",
            level="error",
            type_name="blare.SelfTest",
            message="Blare is connected. This is a test alert.",
            service=self.config.service,
            environment=self.config.environment,
            host=self.config.host,
            timestamp=float(self._clock()),
            state="new",
            logger="blare",
            file="blare/client.py",
            function="selftest",
            line=0,
            window_seconds=self.config.dedupe_window,
        )
        payload = self._redactor.value(event.to_dict())
        results = []
        for sink in self.sinks:
            try:
                ok = sink.send(payload)
            except Exception as exc:
                log.warning("blare: selftest on %s raised: %s", sink.redacted_url(), exc)
                ok = False
            results.append((sink.redacted_url(), ok))
        return results

    def stats(self) -> dict[str, int]:
        """Counters for the host's own monitoring and tests."""
        return {
            "delivered": self._transport.delivered,
            "failed": self._transport.failed,
            "dropped_by_queue": self._transport.dropped,
            "suppressed": self.suppressed,
            "dropped_by_ignore": self.dropped_by_ignore,
        }
