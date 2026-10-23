"""Django capture.

Hooks ``got_request_exception``, which Django sends for any unhandled view
exception before converting it into a 500 response.
"""

from __future__ import annotations

from typing import Any

_receiver: Any = None


def install(client: Any = None) -> None:
    """Attach Blare to Django, typically from ``AppConfig.ready``::

    from blare.integrations.django import install
    install()
    """
    global _receiver
    from django.core.signals import got_request_exception

    def handler(sender: Any, request: Any = None, **_: Any) -> None:
        target = client
        if target is None:
            from .. import get_client

            target = get_client()
        if target is None:
            return
        import sys

        exc = sys.exc_info()[1]
        if exc is None:
            return
        context: dict[str, Any] = {}
        if request is not None:
            context = {
                "method": getattr(request, "method", ""),
                "path": getattr(request, "path", ""),
                "status": 500,
            }
        target.capture_exception(exc, request=context or None)

    _receiver = handler
    got_request_exception.connect(handler, weak=False)
