"""Microsoft Teams rendering.

Teams has two incoming-webhook shapes and the URL says which one you have:
Power Automate workflow URLs (`*.logic.azure.com`) take an Adaptive Card, while
the older Office 365 connectors (`*.webhook.office.com`) take a MessageCard.
Sending the wrong one gets accepted and then silently shows nothing, so Blare
picks by host rather than making the user find out during an incident.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from .base import (
    COLOR_BY_STATE,
    EMOJI_BY_STATE,
    Sink,
    location_line,
    stack_text,
    summarize,
)


class TeamsSink(Sink):
    provider = "teams"

    @property
    def uses_adaptive_card(self) -> bool:
        host = (urlsplit(self.url).hostname or "").lower()
        return not host.endswith(".webhook.office.com")

    def render(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.uses_adaptive_card:
            return self._adaptive_card(payload)
        return self._message_card(payload)

    def _facts(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        facts = [
            {
                "title": "Service",
                "value": f"{payload.get('service', '?')} · "
                f"{payload.get('environment', '?')}",
            },
            {"title": "Occurrences", "value": summarize(payload)},
            {"title": "Where", "value": location_line(payload)},
            {"title": "Fingerprint", "value": payload.get("fingerprint", "")},
            {"title": "Host", "value": payload.get("host", "?")},
        ]
        request = (payload.get("context") or {}).get("request")
        if request:
            facts.insert(
                2,
                {
                    "title": "Request",
                    "value": (
                        f"{request.get('method', '?')} "
                        f"{request.get('path', '?')} → "
                        f"{request.get('status', '?')}"
                    ),
                },
            )
        if payload.get("rate_limited"):
            facts.append(
                {
                    "title": "Rate limited",
                    "value": f"{payload['rate_limited']} alerts dropped",
                }
            )
        return facts

    def _adaptive_card(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = payload.get("state", "new")
        body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": f"{EMOJI_BY_STATE.get(state, '🔴')} "
                f"{payload.get('title', 'error')}",
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
                "color": "Good" if state == "resolved" else "Attention",
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": fact["title"], "value": fact["value"]}
                    for fact in self._facts(payload)
                ],
            },
        ]
        stack = stack_text(payload)
        if stack:
            body.append(
                {
                    "type": "TextBlock",
                    "text": stack,
                    "wrap": True,
                    "fontType": "Monospace",
                    "isSubtle": True,
                    "spacing": "Medium",
                }
            )
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": body,
                    },
                }
            ],
        }

    def _message_card(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = payload.get("state", "new")
        sections: list[dict[str, Any]] = [
            {"facts": self._facts(payload), "markdown": False}
        ]
        stack = stack_text(payload)
        if stack:
            sections.append({"text": f"<pre>{stack}</pre>", "markdown": False})
        return {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "themeColor": COLOR_BY_STATE.get(state, "#d1242f").lstrip("#"),
            "summary": payload.get("title", "error"),
            "title": f"{EMOJI_BY_STATE.get(state, '🔴')} {payload.get('title', 'error')}",
            "sections": sections,
        }
