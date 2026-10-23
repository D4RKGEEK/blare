/**
 * blare — production failures to Slack, Discord and Teams, with no server.
 *
 *     import blare from "blare";
 *     blare.init();
 *
 * From then on every unhandled exception, every rejected promise and every
 * framework 500 becomes a chat alert, deduplicated, rate limited and redacted.
 *
 * Configuration is environment variables only (SPEC.md section 2); the one
 * that matters is `BLARE_SINKS`, your webhook URL.
 */

import { Blare, type CaptureOptions, type ClientOptions, type MessageOptions } from "./client.js";
import { Config, type ConfigInput } from "./config.js";
import { BlareError, ConfigError } from "./errors.js";
import { SPEC_VERSION, VERSION } from "./event.js";
import { EMPTY_LOCATION, type Location } from "./fingerprint.js";

export { Blare, BlareError, Config, ConfigError, EMPTY_LOCATION, SPEC_VERSION, VERSION };
export type { CaptureOptions, ClientOptions, ConfigInput, Location, MessageOptions };
export type { Payload, RequestContext } from "./event.js";
export { Sink, buildSink, buildSinks, detectProvider } from "./sinks/index.js";

export interface InitOptions extends ClientOptions {
  /** Install the crash and unhandled-rejection hooks. Default true. */
  captureCrashes?: boolean;
}

let client: Blare | null = null;

/**
 * Start Blare and install the capture hooks.
 *
 * Call once, as early in startup as possible.
 */
export function init(options: InitOptions = {}): Blare {
  const { captureCrashes = true, ...rest } = options;
  if (client) void client.close();
  const created = new Blare(rest);
  if (captureCrashes) created.installProcessHooks();
  client = created;
  return created;
}

/** The client created by `init`, or null if it was never called. */
export function getClient(): Blare | null {
  return client;
}

/** Report a thrown value explicitly. A no-op before `init`. */
export function captureException(error: unknown, options?: CaptureOptions): boolean {
  return client ? client.captureException(error, options) : false;
}

/** Report a failure that is not a thrown value. A no-op before `init`. */
export function captureMessage(message: string, options?: MessageOptions): boolean {
  return client ? client.captureMessage(message, options) : false;
}

/** Wait for queued alerts to be delivered. */
export function flush(timeoutMs?: number): Promise<boolean> {
  return client ? client.flush(timeoutMs) : Promise.resolve(true);
}

/** Flush and detach everything Blare installed. */
export async function close(timeoutMs?: number): Promise<void> {
  if (!client) return;
  const current = client;
  client = null;
  await current.close(timeoutMs);
}

/** Send one test alert to every sink and report the outcome. */
export function selftest(): Promise<Array<[string, boolean]>> {
  if (!client) throw new BlareError("blare.init() has not been called");
  return client.selftest();
}

/** Delivery and suppression counters. */
export function stats(): Record<string, number> {
  return client ? client.stats() : {};
}

export default {
  init, getClient, captureException, captureMessage, flush, close, selftest, stats,
  Blare, Config, BlareError, ConfigError, VERSION, SPEC_VERSION,
};
