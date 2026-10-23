"""Framework integrations — SPEC.md section 4.3.

Imported lazily: Blare has no dependencies, and asking for the Flask
integration must not require Flask to be installed for everyone else.
"""

from __future__ import annotations

__all__ = [
    "BlareASGIMiddleware",
    "BlareHandler",
    "BlareWSGIMiddleware",
]


def __getattr__(name: str):
    if name == "BlareASGIMiddleware":
        from .asgi import BlareASGIMiddleware

        return BlareASGIMiddleware
    if name == "BlareWSGIMiddleware":
        from .wsgi import BlareWSGIMiddleware

        return BlareWSGIMiddleware
    if name == "BlareHandler":
        from .logging_handler import BlareHandler

        return BlareHandler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
