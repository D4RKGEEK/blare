"""Slack rendering — Block Kit."""

from __future__ import annotations

from typing import Any

from .base import EMOJI_BY_STATE, Sink, location_line, stack_text, summarize

TITLE_LIMIT = 150
BLOCK_TEXT_LIMIT = 2900


class SlackSink(Sink):
    provider = "slack"

    def render(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = payload.get("state", "new")
        emoji = EMOJI_BY_STATE.get(state, "🔴")
        title = payload.get("title", "error")[:TITLE_LIMIT]
        service = payload.get("service", "?")
        environment = payload.get("environment", "?")

        fields = [
            f"*Service*\n{service} · {environment}",
            f"*Occurrences*\n{summarize(payload)}",
            f"*Where*\n`{location_line(payload)}`",
            f"*Fingerprint*\n`{payload.get('fingerprint', '')}`",
        ]
        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{emoji} {title}"[:150]},
            },
            {
                "type": "section",
                "fields": [{"type": "mrkdwn", "text": field} for field in fields],
            },
        ]

        request = (payload.get("context") or {}).get("request")
        if request:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*Request* `{request.get('method', '?')} "
                            f"{request.get('path', '?')}` → "
                            f"`{request.get('status', '?')}`"
                        ),
                    },
                }
            )

        stack = stack_text(payload)
        if stack:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"```{stack}```"[:BLOCK_TEXT_LIMIT],
                    },
                }
            )

        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"{payload.get('host', '?')} · "
                            f"{payload.get('timestamp', '')}"
                            + (
                                f" · {payload['rate_limited']} alerts dropped "
                                "by rate limit"
                                if payload.get("rate_limited")
                                else ""
                            )
                        ),
                    }
                ],
            }
        )
        # `text` is the notification preview and the accessible fallback, so it
        # has to stand alone without the blocks.
        return {"text": f"{emoji} [{service}/{environment}] {title}", "blocks": blocks}
