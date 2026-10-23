/**
 * Winston capture.
 *
 *     import winston from "winston";
 *     import { blareWinstonTransport } from "blare/winston";
 *
 *     const log = winston.createLogger({
 *       transports: [new winston.transports.Console(), blareWinstonTransport()],
 *     });
 *
 * Your existing `log.error(...)` calls then become alerts, with no change to
 * the call sites.
 */

import { Writable } from "node:stream";
import type { Blare } from "../client.js";
import { LEVELS } from "../config.js";
import { resolveClient } from "./shared.js";

/** npm levels, which winston uses by default, mapped onto the spec's names. */
const WINSTON_LEVELS: Record<string, string> = {
  error: "ERROR", warn: "WARNING", info: "INFO", http: "INFO",
  verbose: "DEBUG", debug: "DEBUG", silly: "DEBUG",
  crit: "CRITICAL", alert: "CRITICAL", emerg: "CRITICAL", warning: "WARNING",
};

export interface WinstonTransportOptions {
  client?: Blare | null;
  /** Minimum level to alert on. Defaults to the client's `BLARE_LEVEL`. */
  level?: string;
}

interface WinstonInfo {
  level?: string;
  message?: unknown;
  stack?: string;
  error?: unknown;
  [key: string]: unknown;
}

/**
 * A winston transport that routes qualifying records through Blare.
 *
 * Built on a plain object-mode Writable rather than `winston-transport`, so
 * `blare` stays dependency-free; winston accepts any writable stream.
 */
export function blareWinstonTransport(options: WinstonTransportOptions = {}): Writable {
  return new Writable({
    objectMode: true,
    write(info: WinstonInfo, _encoding, callback) {
      try {
        const target = resolveClient(options.client);
        if (!target) return callback();

        const name = WINSTON_LEVELS[String(info.level ?? "info")] ?? "INFO";
        const minimum = (options.level ?? target.config.level).toUpperCase();
        if ((LEVELS[name] ?? 0) < (LEVELS[minimum] ?? 40)) return callback();

        const level = name.toLowerCase();
        if (info.error instanceof Error) {
          target.captureException(info.error, { level, logger: "winston" });
        } else if (info.stack) {
          const rebuilt = Object.assign(new Error(String(info.message ?? "")), {
            stack: info.stack,
          });
          target.captureException(rebuilt, { level, logger: "winston" });
        } else {
          target.captureMessage(String(info.message ?? ""), {
            level, typeName: "winston", logger: "winston",
          });
        }
      } catch {
        /* logging must never throw into the host */
      }
      callback();
    },
  });
}

export default blareWinstonTransport;
