import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";

import { Config, deriveServiceName } from "../dist/esm/config.js";
import { ConfigError } from "../dist/esm/errors.js";
import { cleanEnvironment } from "./helpers.js";

beforeEach(cleanEnvironment);

test("defaults match the spec", () => {
  const config = Config.fromEnv();
  assert.equal(config.level, "ERROR");
  assert.equal(config.dedupeWindow, 300);
  assert.equal(config.maxPerHour, 20);
  assert.equal(config.state, "file");
  assert.equal(config.resolveAfter, 0);
  assert.equal(config.stackFrames, 12);
  assert.equal(config.timeout, 5);
  assert.equal(config.environment, "unknown");
  assert.equal(config.enabled, true);
  assert.equal(config.dryRun, false);
});

test("sinks are split and trimmed", () => {
  process.env.BLARE_SINKS = " https://a.example/x , https://b.example/y ,";
  assert.deepEqual(Config.fromEnv().sinks, ["https://a.example/x", "https://b.example/y"]);
});

test("every boolean form is accepted", () => {
  for (const [raw, expected] of [["1", true], ["true", true], ["TRUE", true], ["yes", true],
    ["on", true], ["0", false], ["false", false], ["no", false], ["off", false]]) {
    process.env.BLARE_ENABLED = raw;
    assert.equal(Config.fromEnv().enabled, expected, raw);
  }
});

test("a misread setting is fatal rather than silent", () => {
  // An alerting library that starts up quietly with a bad setting looks
  // exactly like one that works, until the incident it was meant to report.
  process.env.BLARE_ENABLED = "maybe";
  assert.throws(() => Config.fromEnv(), ConfigError);
  cleanEnvironment();
  process.env.BLARE_DEDUPE_WINDOW = "five minutes";
  assert.throws(() => Config.fromEnv(), /not an integer/);
  cleanEnvironment();
  process.env.BLARE_DEDUPE_WINDOW = "-1";
  assert.throws(() => Config.fromEnv(), /must be >=/);
  cleanEnvironment();
  process.env.BLARE_LEVEL = "LOUD";
  assert.throws(() => Config.fromEnv(), /not a level/);
});

test("a lowercase level is accepted", () => {
  process.env.BLARE_LEVEL = "warning";
  assert.equal(Config.fromEnv().level, "WARNING");
});

test("overrides beat the environment", () => {
  process.env.BLARE_SERVICE = "from-env";
  assert.equal(Config.fromEnv({ service: "from-code" }).service, "from-code");
});

test("the platform service name wins, in the spec's order", () => {
  process.env.FLY_APP_NAME = "fly-name";
  assert.equal(deriveServiceName(), "fly-name");
  process.env.K_SERVICE = "cloud-run-name";
  assert.equal(deriveServiceName(), "cloud-run-name");
  delete process.env.FLY_APP_NAME;
  delete process.env.K_SERVICE;
});

test("active requires both a sink and the switch", () => {
  assert.equal(Config.fromEnv().active, false);
  process.env.BLARE_SINKS = "console";
  assert.equal(Config.fromEnv().active, true);
  process.env.BLARE_ENABLED = "0";
  assert.equal(Config.fromEnv().active, false);
});
