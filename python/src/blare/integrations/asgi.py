"""ASGI capture — FastAPI, Starlette, Litestar, Quart.

Adds request context to the alert, then re-raises. Blare observes; the
framework still decides what the client sees.
"""

from __future__ import annotations

from typing import Any


def request_context(scope: dict, status: int | None = None) -> dict[str, Any]:
    """The request fields section 6 permits: method, path, status.

    The query string, headers and body are deliberately left out — they are
    where tokens and personal data live, and this payload is going to a chat
    room.
    """
    context: dict[str, Any] = {
        "method": scope.get("method", ""),
        "path": scope.get("path", ""),
    }
    if status is not None:
        context["status"] = status
    route = scope.get("route")
    path_format = getattr(route, "path_format", None)
    if path_format:
        # The templated route ("/users/{id}") rather than the concrete path, so
        # one broken endpoint is one alert instead of one per user id.
        context["route"] = path_format
    return context


class BlareASGIMiddleware:
    """Wrap an ASGI app so handler exceptions become alerts.

    ::

        from blare.integrations.asgi import BlareASGIMiddleware
        app.add_middleware(BlareASGIMiddleware)
    """

    def __init__(self, app: Any, client: Any = None) -> None:
        self.app = app
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is not None:
            return self._client
        from .. import get_client

        return get_client()

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            client = self.client
            if client is not None:
                client.capture_exception(exc, request=request_context(scope, 500))
            raise
