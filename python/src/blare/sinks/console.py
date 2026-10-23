"""The console sink — rendered alerts on stderr, for development and tests."""

from __future__ import annotations

import sys
from typing import Any

from .base import EMOJI_BY_STATE, Sink, location_line, stack_text, summarize


class ConsoleSink(Sink):
    provider = "console"

    def __init__(self, url: str = "console", timeout: int = 5) -> None:
        super().__init__(url, timeout)

    def redacted_url(self) -> str:
        return "console"

    def render(self, payload: dict[str, Any]) -> str:
        state = payload.get("state", "new")
        lines = [
            f"{EMOJI_BY_STATE.get(state, '🔴')} blare "
            f"[{payload.get('service')}/{payload.get('environment')}] "
            f"{payload.get('title')}",
            f"    {summarize(payload)} · {location_line(payload)} "
            f"· {payload.get('fingerprint')}",
        ]
        request = (payload.get("context") or {}).get("request")
        if request:
            lines.append(
                f"    {request.get('method')} {request.get('path')} "
                f"→ {request.get('status')}"
            )
        stack = stack_text(payload, limit=5)
        if stack:
            lines.extend(f"    {frame}" for frame in stack.splitlines())
        return "\n".join(lines)

    def send(self, payload: dict[str, Any]) -> bool:
        print(self.render(payload), file=sys.stderr, flush=True)
        return True
