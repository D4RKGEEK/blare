/**
 * Sinks. SPEC.md section 3.
 *
 * A sink is one webhook URL. Users paste whatever Slack, Discord or Teams gave
 * them and Blare works out the rest: nobody should have to learn a URL scheme
 * in order to send a message to a chat room.
 *
 * Delivery uses the built-in fetch, so the package has no dependencies.
 */

import { ConfigError } from "../errors.js";
import type { Payload } from "../event.js";

export const RETRY_DELAYS = [1000, 3000] as const;
export const MAX_RETRY_AFTER_MS = 30_000;

export const SLACK_HOSTS = new Set(["hooks.slack.com"]);
export const DISCORD_HOSTS = new Set([
  "discord.com", "discordapp.com", "ptb.discord.com", "canary.discord.com",
]);
export const TEAMS_HOST_SUFFIXES = [
  ".webhook.office.com", ".logic.azure.com", ".logic.azure.us",
] as const;

export const COLOR_BY_STATE: Record<string, string> = {
  new: "#d1242f", recurring: "#bc4c00", resolved: "#1a7f37",
};
export const EMOJI_BY_STATE: Record<string, string> = {
  new: "🔴", recurring: "🟠", resolved: "🟢",
};

export const PROVIDERS = new Set(["slack", "discord", "teams", "generic", "console"]);

/** Return `[provider, url]` for a sink spec. Section 3.1. */
export function detectProvider(url: string): [string, string] {
  const spec = (url ?? "").trim();
  if (!spec) throw new ConfigError("empty sink");
  if (spec === "console") return ["console", spec];

  const schemeHead = spec.split("://", 1)[0] as string;
  if (schemeHead.includes("+")) {
    const index = spec.indexOf("+");
    const prefix = spec.slice(0, index).toLowerCase();
    const rest = spec.slice(index + 1);
    if (!PROVIDERS.has(prefix)) {
      throw new ConfigError(
        `unknown provider ${JSON.stringify(prefix)} in sink ${JSON.stringify(spec)}; ` +
          `use one of ${[...PROVIDERS].sort().join(", ")}`,
      );
    }
    return [prefix, rest];
  }

  let parsed: URL;
  try {
    parsed = new URL(spec);
  } catch {
    throw new ConfigError(`sink ${JSON.stringify(spec)} is not a URL`);
  }
  const scheme = parsed.protocol.replace(":", "");
  if (scheme !== "http" && scheme !== "https") {
    throw new ConfigError(
      `unsupported scheme ${JSON.stringify(scheme)} in sink ${JSON.stringify(spec)}; ` +
        "sinks are http(s) webhook URLs",
    );
  }
  const host = parsed.hostname.toLowerCase();
  if (SLACK_HOSTS.has(host)) return ["slack", spec];
  if (DISCORD_HOSTS.has(host)) return ["discord", spec];
  if (TEAMS_HOST_SUFFIXES.some((suffix) => host.endsWith(suffix))) return ["teams", spec];
  return ["generic", spec];
}

const sleep = (ms: number) => new Promise<void>((done) => setTimeout(done, ms));

/** Renders the canonical event for one provider and posts it. */
export class Sink {
  static readonly provider: string = "generic";
  readonly url: string;
  readonly timeout: number;
  onWarning?: (message: string) => void;
  /** Backoff between delivery attempts. Overridable so tests need not sleep. */
  retryDelaysMs: number[] = [...RETRY_DELAYS];

  constructor(url: string, timeout = 5) {
    this.url = url;
    this.timeout = timeout;
  }

  get provider(): string {
    return (this.constructor as typeof Sink).provider;
  }

  /**
   * The URL with its secret path removed, safe to log.
   *
   * A webhook URL *is* the credential, so it must never reach a log file.
   */
  redactedUrl(): string {
    try {
      const parsed = new URL(this.url);
      return `${parsed.protocol}//${parsed.host}/…`;
    } catch {
      return "(invalid url)";
    }
  }

  /** Provider-specific message body. Default: the event itself. */
  render(payload: Payload): unknown {
    return payload;
  }

  /**
   * Deliver one event, retrying per section 3.2.
   *
   * Never throws: a broken webhook must not become an application failure.
   */
  async send(payload: Payload): Promise<boolean> {
    const body = JSON.stringify(this.render(payload));
    const attempts = this.retryDelaysMs.length + 1;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const result = await this.post(body);
      if (result.ok) return true;
      if (!result.retryable || attempt === attempts - 1) {
        this.onWarning?.(
          `blare: delivery to ${this.redactedUrl()} failed (${result.detail}); giving up`,
        );
        return false;
      }
      await sleep(result.retryAfterMs ?? this.retryDelaysMs[attempt] ?? 1000);
    }
    return false;
  }

  private async post(
    body: string,
  ): Promise<{ ok: boolean; retryable: boolean; detail?: string; retryAfterMs?: number }> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout * 1000);
    try {
      const response = await fetch(this.url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "User-Agent": "blare-node" },
        body,
        signal: controller.signal,
      });
      if (response.ok) return { ok: true, retryable: false };
      const retryable = response.status === 429 || response.status >= 500;
      const result: { ok: boolean; retryable: boolean; detail: string; retryAfterMs?: number } = {
        ok: false, retryable, detail: `HTTP ${response.status}`,
      };
      const after = Number(response.headers.get("retry-after"));
      if (retryable && after > 0 && after * 1000 <= MAX_RETRY_AFTER_MS) {
        result.retryAfterMs = after * 1000;
      }
      return result;
    } catch (error) {
      const aborted = (error as { name?: string })?.name === "AbortError";
      return {
        ok: false,
        retryable: true,
        detail: aborted ? `timed out after ${this.timeout}s` : `connection error: ${String(error)}`,
      };
    } finally {
      clearTimeout(timer);
    }
  }
}

/** The one-line "how bad is it" summary shared by every renderer. */
export function summarize(payload: Payload): string {
  const occurrences = (payload["occurrences"] ?? {}) as Record<string, unknown>;
  const count = Number(occurrences["since_last_alert"] ?? 0);
  const window = Number(occurrences["window_seconds"] ?? 0);
  if (payload["state"] === "resolved") return "Recovered — no further occurrences";
  if (count > 1) {
    const minutes = Math.max(1, Math.floor(window / 60));
    return `${count} times in the last ${minutes} min`;
  }
  return "First occurrence";
}

export function locationLine(payload: Payload): string {
  const location = (payload["location"] ?? {}) as Record<string, unknown>;
  const file = String(location["file"] ?? "");
  if (!file) return "unknown location";
  return `${file}:${location["line"] ?? 0} in ${location["function"] || "?"}`;
}

export function stackText(payload: Payload, limit = 10): string {
  const stack = (payload["stack"] ?? []) as string[];
  return stack.slice(0, limit).join("\n");
}

export function requestOf(payload: Payload): Record<string, unknown> | undefined {
  const context = (payload["context"] ?? {}) as Record<string, unknown>;
  return context["request"] as Record<string, unknown> | undefined;
}
