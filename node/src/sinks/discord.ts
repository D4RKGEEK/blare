/** Discord rendering: embeds. */

import type { Payload } from "../event.js";
import { COLOR_BY_STATE, EMOJI_BY_STATE, Sink, locationLine, requestOf, stackText,
  summarize } from "./base.js";

const TITLE_LIMIT = 256;
const FIELD_LIMIT = 1024;

function intColor(state: string): number {
  return parseInt((COLOR_BY_STATE[state] ?? "#d1242f").replace("#", ""), 16);
}

export class DiscordSink extends Sink {
  static override readonly provider = "discord";

  override render(payload: Payload): Record<string, unknown> {
    const state = String(payload["state"] ?? "new");
    const emoji = EMOJI_BY_STATE[state] ?? "🔴";
    const fields: Array<Record<string, unknown>> = [
      {
        name: "Service",
        value: `${payload["service"] ?? "?"} · ${payload["environment"] ?? "?"}`,
        inline: true,
      },
      { name: "Occurrences", value: summarize(payload), inline: true },
      { name: "Where", value: `\`${locationLine(payload)}\``.slice(0, FIELD_LIMIT), inline: false },
    ];

    const request = requestOf(payload);
    if (request) {
      fields.push({
        name: "Request",
        value: `\`${request["method"] ?? "?"} ${request["path"] ?? "?"}\` → ` +
          `${request["status"] ?? "?"}`.slice(0, FIELD_LIMIT),
        inline: false,
      });
    }

    const stack = stackText(payload);
    if (stack) {
      fields.push({
        name: "Stack",
        value: `\`\`\`\n${stack}\n\`\`\``.slice(0, FIELD_LIMIT),
        inline: false,
      });
    }

    const dropped = Number(payload["rate_limited"] ?? 0);
    let footer = `${payload["host"] ?? "?"} · ${payload["fingerprint"] ?? ""}`;
    if (dropped) footer += ` · ${dropped} dropped by rate limit`;

    return {
      embeds: [{
        title: `${emoji} ${payload["title"] ?? "error"}`.slice(0, TITLE_LIMIT),
        color: intColor(state),
        fields,
        footer: { text: footer.slice(0, 2048) },
        timestamp: payload["timestamp"],
      }],
    };
  }
}
