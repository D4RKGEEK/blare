"""Blare — production failures to Slack, Discord and Teams, with no server.

    import blare
    blare.init()

From then on every ``logger.error``, every unhandled exception, and every
framework 500 becomes a chat alert — deduplicated, rate limited and redacted.

Configuration is environment variables only (see SPEC.md section 2); the one
that matters is ``BLARE_SINKS``, your webhook URL.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from typing import Any

from .client import Blare
from .config import Config
from .errors import BlareError, ConfigError
from .event import SPEC_VERSION
from .fingerprint import Location
from .sinks import Sink
from .version import __version__

__all__ = [
    "SPEC_VERSION",
    "Blare",
    "BlareError",
    "Config",
    "ConfigError",
    "Location",
    "__version__",
    "capture_exception",
    "capture_message",
    "close",
    "flush",
    "get_client",
    "init",
    "selftest",
    "stats",
]

_client: Blare | None = None
_lock = threading.Lock()

# Blare's own diagnostics. A library should not configure logging for its host,
# but it also must not print "no handler" warnings, so the channel exists and
# stays quiet until the application asks for it.
logging.getLogger("blare").addHandler(logging.NullHandler())


def init(
    *,
    sinks: Sequence[Sink] | None = None,
    capture_logs: bool = True,
    capture_crashes: bool = True,
    synchronous: bool = False,
    **overrides: Any,
) -> Blare:
    """Start Blare and install the capture hooks.

    Call once, as early in startup as possible.

    :param capture_logs: attach to the root logger (section 4.1).
    :param capture_crashes: install the unhandled-exception hooks (section 4.2).
    :param synchronous: deliver on the calling thread; for tests.
    :param overrides: any :class:`~blare.config.Config` field, winning over the
        environment — e.g. ``service="checkout-api"``.
    """
    global _client
    with _lock:
        if _client is not None:
            _client.close()
        client = Blare(sinks=sinks, synchronous=synchronous, **overrides)
        if capture_logs:
            client.install_logging()
        if capture_crashes:
            client.install_excepthook()
        _client = client
    return client


def get_client() -> Blare | None:
    """The client created by :func:`init`, or None if it was never called."""
    return _client


def capture_exception(exc: BaseException | None = None, **kwargs: Any) -> bool:
    """Report an exception explicitly. No-op before :func:`init`."""
    client = _client
    return client.capture_exception(exc, **kwargs) if client else False


def capture_message(message: str, **kwargs: Any) -> bool:
    """Report a failure that is not an exception. No-op before :func:`init`."""
    client = _client
    return client.capture_message(message, **kwargs) if client else False


def flush(timeout: float | None = None) -> bool:
    """Wait for queued alerts to be delivered."""
    client = _client
    return client.flush(timeout) if client else True


def close(timeout: float | None = None) -> None:
    """Flush and detach everything Blare installed."""
    global _client
    with _lock:
        if _client is not None:
            _client.close(timeout)
            _client = None


def selftest() -> list[tuple[str, bool]]:
    """Send one test alert to every sink and report the outcome."""
    client = _client
    if client is None:
        raise BlareError("blare.init() has not been called")
    return client.selftest()


def stats() -> dict[str, int]:
    """Delivery and suppression counters."""
    client = _client
    return client.stats() if client else {}
