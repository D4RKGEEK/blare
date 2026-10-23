/** The console sink: rendered alerts on stderr, for development and tests. */

import type { Payload } from "../event.js";
import { EMOJI_BY_STATE, Sink, locationLine, requestOf, stackText, summarize } from "./base.js";

export class ConsoleSink extends Sink {
  static override readonly provider = "console";

  constructor(url = "console", timeout = 5) {
    super(url, timeout);
  }

  override redactedUrl(): string {
    return "console";
  }

  override render(payload: Payload): string {
    const state = String(payload["state"] ?? "new");
    const lines = [
      `${EMOJI_BY_STATE[state] ?? "🔴"} blare ` +
        `[${payload["service"]}/${payload["environment"]}] ${payload["title"]}`,
      `    ${summarize(payload)} · ${locationLine(payload)} · ${payload["fingerprint"]}`,
    ];
    const request = requestOf(payload);
    if (request) {
      lines.push(`    ${request["method"]} ${request["path"]} → ${request["status"]}`);
    }
    const stack = stackText(payload, 5);
    if (stack) for (const frame of stack.split("\n")) lines.push(`    ${frame}`);
    return lines.join("\n");
  }

  override async send(payload: Payload): Promise<boolean> {
    process.stderr.write(`${this.render(payload)}\n`);
    return true;
  }
}
