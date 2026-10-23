/**
 * Microsoft Teams rendering.
 *
 * Teams has two incoming-webhook shapes and the URL says which one you have:
 * Power Automate workflow URLs (`*.logic.azure.com`) take an Adaptive Card,
 * while the older Office 365 connectors (`*.webhook.office.com`) take a
 * MessageCard. Sending the wrong one is accepted and then silently shows
 * nothing, so Blare picks by host rather than making the user find out during
 * an incident.
 */

import type { Payload } from "../event.js";
import { COLOR_BY_STATE, EMOJI_BY_STATE, Sink, locationLine, requestOf,
  stackText, summarize } from "./base.js";

interface Fact { title: string; value: string }

export class TeamsSink extends Sink {
  static override readonly provider = "teams";

  get usesAdaptiveCard(): boolean {
    try {
      return !new URL(this.url).hostname.toLowerCase().endsWith(".webhook.office.com");
    } catch {
      return true;
    }
  }

  override render(payload: Payload): Record<string, unknown> {
    return this.usesAdaptiveCard ? this.adaptiveCard(payload) : this.messageCard(payload);
  }

  private facts(payload: Payload): Fact[] {
    const facts: Fact[] = [
      { title: "Service", value: `${payload["service"] ?? "?"} · ${payload["environment"] ?? "?"}` },
      { title: "Occurrences", value: summarize(payload) },
      { title: "Where", value: locationLine(payload) },
      { title: "Fingerprint", value: String(payload["fingerprint"] ?? "") },
      { title: "Host", value: String(payload["host"] ?? "?") },
    ];
    const request = requestOf(payload);
    if (request) {
      facts.splice(2, 0, {
        title: "Request",
        value: `${request["method"] ?? "?"} ${request["path"] ?? "?"} → ${request["status"] ?? "?"}`,
      });
    }
    const dropped = Number(payload["rate_limited"] ?? 0);
    if (dropped) facts.push({ title: "Rate limited", value: `${dropped} alerts dropped` });
    return facts;
  }

  private adaptiveCard(payload: Payload): Record<string, unknown> {
    const state = String(payload["state"] ?? "new");
    const body: Array<Record<string, unknown>> = [
      {
        type: "TextBlock",
        text: `${EMOJI_BY_STATE[state] ?? "🔴"} ${payload["title"] ?? "error"}`,
        weight: "Bolder", size: "Medium", wrap: true,
        color: state === "resolved" ? "Good" : "Attention",
      },
      { type: "FactSet", facts: this.facts(payload) },
    ];
    const stack = stackText(payload);
    if (stack) {
      body.push({
        type: "TextBlock", text: stack, wrap: true,
        fontType: "Monospace", isSubtle: true, spacing: "Medium",
      });
    }
    return {
      type: "message",
      attachments: [{
        contentType: "application/vnd.microsoft.card.adaptive",
        contentUrl: null,
        content: {
          $schema: "http://adaptivecards.io/schemas/adaptive-card.json",
          type: "AdaptiveCard", version: "1.4", body,
        },
      }],
    };
  }

  private messageCard(payload: Payload): Record<string, unknown> {
    const state = String(payload["state"] ?? "new");
    const sections: Array<Record<string, unknown>> = [
      { facts: this.facts(payload), markdown: false },
    ];
    const stack = stackText(payload);
    if (stack) sections.push({ text: `<pre>${stack}</pre>`, markdown: false });
    return {
      "@type": "MessageCard",
      "@context": "https://schema.org/extensions",
      themeColor: (COLOR_BY_STATE[state] ?? "#d1242f").replace("#", ""),
      summary: payload["title"] ?? "error",
      title: `${EMOJI_BY_STATE[state] ?? "🔴"} ${payload["title"] ?? "error"}`,
      sections,
    };
  }
}
