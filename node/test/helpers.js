/** Shared test utilities. */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
export const CONFORMANCE = join(here, "..", "..", "conformance");

export function loadFixture(name) {
  return JSON.parse(readFileSync(join(CONFORMANCE, name), "utf8"));
}

/** A clock the tests drive, so dedupe windows need no sleeping. */
export class FakeClock {
  constructor(now = 1_700_000_000) {
    this.now = now;
  }
  tick = () => this.now;
  advance(seconds) {
    this.now += seconds;
    return this.now;
  }
}

/** A sink that keeps payloads instead of sending them. */
export class RecordingSink {
  constructor({ fail = false, throws = false } = {}) {
    this.payloads = [];
    this.fail = fail;
    this.throws = throws;
    this.provider = "recording";
  }
  redactedUrl() {
    return "recording://";
  }
  async send(payload) {
    if (this.throws) throw new Error("sink exploded");
    this.payloads.push(payload);
    return !this.fail;
  }
  get titles() {
    return this.payloads.map((p) => p.title);
  }
  get states() {
    return this.payloads.map((p) => p.state);
  }
  get counts() {
    return this.payloads.map((p) => p.occurrences.since_last_alert);
  }
}

/** Blare reads the environment, so tests must not inherit a real config. */
export function cleanEnvironment() {
  for (const key of Object.keys(process.env)) {
    if (key.startsWith("BLARE_")) delete process.env[key];
  }
}
