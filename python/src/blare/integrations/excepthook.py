"""Crash capture — SPEC.md section 4.2.

Blare alerts and then hands control back to whatever handler was already
installed. Swallowing a crash in order to send a notification about it would be
a worse bug than the one being reported.
"""

from __future__ import annotations

import sys
import threading
from typing import Any


def install(client) -> Any:
    """Wrap ``sys.excepthook`` and the threading hook. Returns the old hook."""
    previous = sys.excepthook

    def hook(exc_type, exc_value, exc_tb):
        try:
            if not issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
                client.capture_exception(exc_value, level="critical")
                # The process is about to end, so the queued alert has to be
                # delivered now rather than by the worker thread.
                client.flush()
        except Exception:  # pragma: no cover - defensive
            pass
        previous(exc_type, exc_value, exc_tb)

    sys.excepthook = hook

    previous_thread_hook = threading.excepthook

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        try:
            if args.exc_value is not None and not isinstance(
                args.exc_value, (KeyboardInterrupt, SystemExit)
            ):
                client.capture_exception(args.exc_value, level="critical")
        except Exception:  # pragma: no cover - defensive
            pass
        previous_thread_hook(args)

    threading.excepthook = thread_hook
    return previous
