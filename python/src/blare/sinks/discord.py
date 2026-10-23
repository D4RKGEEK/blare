"""Discord rendering — embeds."""

from __future__ import annotations

from typing import Any

from .base import (
    COLOR_BY_STATE,
    EMOJI_BY_STATE,
    Sink,
    location_line,
    stack_text,
    summarize,
)

TITLE_LIMIT = 256
FIELD_LIMIT = 1024


def _int_color(state: str) -> int:
    return int(COLOR_BY_STATE.get(state, "#d1242f").lstrip("#"), 16)


class DiscordSink(Sink):
    provider = "discord"

    def render(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = payload.get("state", "new")
        emoji = EMOJI_BY_STATE.get(state, "🔴")
        fields = [
            {
                "name": "Service",
                "value": f"{payload.get('service', '?')} · "
                f"{payload.get('environment', '?')}",
                "inline": True,
            },
            {"name": "Occurrences", "value": summarize(payload), "inline": True},
            {
                "name": "Where",
                "value": f"`{location_line(payload)}`"[:FIELD_LIMIT],
                "inline": False,
            },
        ]

        request = (payload.get("context") or {}).get("request")
        if request:
            fields.append(
                {
                    "name": "Request",
                    "value": (
                        f"`{request.get('method', '?')} "
                        f"{request.get('path', '?')}` → "
                        f"{request.get('status', '?')}"
                    )[:FIELD_LIMIT],
                    "inline": False,
                }
            )

        stack = stack_text(payload)
        if stack:
            fields.append(
                {
                    "name": "Stack",
                    "value": f"```\n{stack}\n```"[:FIELD_LIMIT],
                    "inline": False,
                }
            )

        footer = f"{payload.get('host', '?')} · {payload.get('fingerprint', '')}"
        if payload.get("rate_limited"):
            footer += f" · {payload['rate_limited']} dropped by rate limit"

        return {
            "embeds": [
                {
                    "title": f"{emoji} {payload.get('title', 'error')}"[:TITLE_LIMIT],
                    "color": _int_color(state),
                    "fields": fields,
                    "footer": {"text": footer[:2048]},
                    "timestamp": payload.get("timestamp"),
                }
            ]
        }
