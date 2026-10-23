/** Slack rendering: Block Kit. */

import type { Payload } from "../event.js";
import { EMOJI_BY_STATE, Sink, locationLine, requestOf, stackText, summarize } from "./base.js";

const TITLE_LIMIT = 150;
const BLOCK_TEXT_LIMIT = 2900;

export class SlackSink extends Sink {
  static override readonly provider = "slack";

  override render(payload: Payload): Record<string, unknown> {
    const state = String(payload["state"] ?? "new");
    const emoji = EMOJI_BY_STATE[state] ?? "🔴";
    const title = String(payload["title"] ?? "error").slice(0, TITLE_LIMIT);
    const service = String(payload["service"] ?? "?");
    const environment = String(payload["environment"] ?? "?");

    const fields = [
      `*Service*\n${service} · ${environment}`,
      `*Occurrences*\n${summarize(payload)}`,
      `*Where*\n\`${locationLine(payload)}\``,
      `*Fingerprint*\n\`${payload["fingerprint"] ?? ""}\``,
    ];

    const blocks: Array<Record<string, unknown>> = [
      { type: "header", text: { type: "plain_text", text: `${emoji} ${title}`.slice(0, 150) } },
      { type: "section", fields: fields.map((text) => ({ type: "mrkdwn", text })) },
    ];

    const request = requestOf(payload);
    if (request) {
      blocks.push({
        type: "section",
        text: {
          type: "mrkdwn",
          text: `*Request* \`${request["method"] ?? "?"} ${request["path"] ?? "?"}\` → ` +
            `\`${request["status"] ?? "?"}\``,
        },
      });
    }

    const stack = stackText(payload);
    if (stack) {
      blocks.push({
        type: "section",
        text: { type: "mrkdwn", text: `\`\`\`${stack}\`\`\``.slice(0, BLOCK_TEXT_LIMIT) },
      });
    }

    const dropped = Number(payload["rate_limited"] ?? 0);
    blocks.push({
      type: "context",
      elements: [{
        type: "mrkdwn",
        text: `${payload["host"] ?? "?"} · ${payload["timestamp"] ?? ""}` +
          (dropped ? ` · ${dropped} alerts dropped by rate limit` : ""),
      }],
    });

    // `text` is the notification preview and the accessible fallback, so it
    // has to stand alone without the blocks.
    return { text: `${emoji} [${service}/${environment}] ${title}`, blocks };
  }
}
