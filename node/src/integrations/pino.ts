/**
 * Pino capture.
 *
 * Node has no standard logger, so the closest equivalent to attaching a
 * handler to the root logger is a destination stream:
 *
 *     import pino from "pino";
 *     import { blarePinoStream } from "blare/pino";
 *
 *     const log = pino({ level: "info" },
 *       pino.multistream([{ stream: process.stdout }, { stream: blarePinoStream() }]));
 *
 * Your existing `log.error(...)` calls then become alerts, with no change to
 * the call sites.
 */

import { Writable } from "node:stream";
import type { Blare } from "../client.js";
import { LEVELS } from "../config.js";
import { resolveClient } from "./shared.js";

/** Pino's numeric levels, mapped onto the spec's names. */
const PINO_LEVELS: Array<[number, string]> = [
  [60, "CRITICAL"], [50, "ERROR"], [40, "WARNING"], [30, "INFO"], [20, "DEBUG"], [10, "DEBUG"],
];

function levelName(value: number): string {
  for (const [threshold, name] of PINO_LEVELS) {
    if (value >= threshold) return name;
  }
  return "DEBUG";
}

export interface PinoStreamOptions {
  client?: Blare | null;
  /** Minimum level to alert on. Defaults to the client's `BLARE_LEVEL`. */
  level?: string;
}

/** A pino destination that routes qualifying records through Blare. */
export function blarePinoStream(options: PinoStreamOptions = {}): Writable {
  let buffered = "";

  const handle = (line: string): void => {
    if (!line.trim()) return;
    const target = resolveClient(options.client);
    if (!target) return;

    let record: Record<string, unknown>;
    try {
      record = JSON.parse(line) as Record<string, unknown>;
    } catch {
      return; // not pino's NDJSON; nothing to classify
    }

    const name = levelName(Number(record["level"] ?? 30));
    const minimum = (options.level ?? target.config.level).toUpperCase();
    if ((LEVELS[name] ?? 0) < (LEVELS[minimum] ?? 40)) return;

    const logger = String(record["name"] ?? "pino");
    const err = record["err"] as { message?: string; type?: string; stack?: string } | undefined;
    if (err) {
      // An error on the record classifies the event, so `log.error({ err })`
      // groups by the error rather than by the wording of the log line.
      const rebuilt = Object.assign(new Error(err.message ?? ""), {
        name: err.type ?? "Error",
        stack: err.stack,
      });
      target.captureException(rebuilt, { level: name.toLowerCase(), logger });
      return;
    }
    target.captureMessage(String(record["msg"] ?? ""), {
      level: name.toLowerCase(),
      typeName: logger,
      logger,
    });
  };

  return new Writable({
    write(chunk, _encoding, callback) {
      buffered += String(chunk);
      const lines = buffered.split("\n");
      buffered = lines.pop() ?? "";
      for (const line of lines) {
        try {
          handle(line);
        } catch {
          /* logging must never throw into the host */
        }
      }
      callback();
    },
  });
}

export default blarePinoStream;
