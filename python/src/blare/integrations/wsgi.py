"""WSGI capture — any WSGI application.

A last-resort wrapper for stacks without a first-class integration. Frameworks
that convert exceptions into a 500 response before WSGI sees them (Flask and
Django both do) are better served by their own integration, which hooks the
framework's signal instead.
"""

from __future__ import annotations

from typing import Any, Callable


class BlareWSGIMiddleware:
    """::

    app = BlareWSGIMiddleware(app)
    """

    def __init__(self, app: Callable, client: Any = None) -> None:
        self.app = app
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is not None:
            return self._client
        from .. import get_client

        return get_client()

    def __call__(self, environ: dict, start_response: Callable) -> Any:
        try:
            return self.app(environ, start_response)
        except Exception as exc:
            client = self.client
            if client is not None:
                client.capture_exception(exc, request=request_context(environ, 500))
            raise


def request_context(environ: dict, status: int | None = None) -> dict[str, Any]:
    context: dict[str, Any] = {
        "method": environ.get("REQUEST_METHOD", ""),
        "path": environ.get("PATH_INFO", ""),
    }
    if status is not None:
        context["status"] = status
    return context
