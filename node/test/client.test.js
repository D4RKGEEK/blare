/** The capture pipeline end to end, with a recording sink. */

import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";

import { Blare } from "../dist/esm/client.js";
import { FakeClock, RecordingSink, cleanEnvironment } from "./helpers.js";

beforeEach(cleanEnvironment);

function makeClient(sink, overrides = {}) {
  const clock = overrides.clock ?? new FakeClock(0);
  const client = new Blare({
    state: "memory", service: "test-service", environment: "test",
    sinks: ["console"], sinkObjects: sink ? [sink] : [],
    synchronous: true, clock: clock.tick ?? clock,
    onWarning: () => {},
    ...overrides, clock: clock.tick ?? clock,
  });
  return { client, clock };
}

test("an exception becomes an alert", async () => {
  const sink = new RecordingSink();
  const { client } = makeClient(sink);
  client.captureException(new TypeError("invalid literal"));
  await client.flush();

  assert.equal(sink.payloads.length, 1);
  const payload = sink.payloads[0];
  assert.equal(payload.type, "TypeError");
  assert.equal(payload.title, "TypeError: invalid literal");
  assert.equal(payload.state, "new");
  assert.equal(payload.kind, "exception");
  assert.equal(payload.service, "test-service");
  assert.equal(payload.blare_version, "1");
  assert.equal(payload.runtime.language, "node");
});

test("the location points at application code, not at node internals", async () => {
  const sink = new RecordingSink();
  const { client } = makeClient(sink);
  client.captureException(new Error("boom"));
  await client.flush();
  const location = sink.payloads[0].location;
  assert.match(location.file, /client\.test\.js$/);
  assert.ok(location.line > 0);
});

test("identical failures send once, then report the count", async () => {
  const sink = new RecordingSink();
  const { client, clock } = makeClient(sink, { dedupeWindow: 300, maxPerHour: 0 });

  for (let i = 0; i < 850; i += 1) {
    client.captureMessage("connection pool exhausted", { typeName: "DBError" });
  }
  await client.flush();
  assert.equal(sink.payloads.length, 1, "a flood must not become a flood of messages");

  clock.advance(300);
  client.captureMessage("connection pool exhausted", { typeName: "DBError" });
  await client.flush();
  assert.equal(sink.payloads.length, 2);
  assert.equal(sink.payloads[1].state, "recurring");
  assert.equal(sink.payloads[1].occurrences.since_last_alert, 850);
  assert.equal(sink.payloads[1].occurrences.total, 851);
});

test("messages differing only in data group together", async () => {
  const sink = new RecordingSink();
  const { client } = makeClient(sink, { dedupeWindow: 300, maxPerHour: 0 });
  client.captureMessage("User 4821 not found", { typeName: "KeyError" });
  client.captureMessage("User 9173 not found", { typeName: "KeyError" });
  await client.flush();
  assert.equal(sink.payloads.length, 1);
});

test("genuinely different failures both alert", async () => {
  const sink = new RecordingSink();
  const { client } = makeClient(sink, { dedupeWindow: 300, maxPerHour: 0 });
  client.captureMessage("pool exhausted", { typeName: "DBError" });
  client.captureMessage("disk full", { typeName: "OSError" });
  await client.flush();
  assert.equal(sink.payloads.length, 2);
});

test("the hourly cap reports what it dropped", async () => {
  const sink = new RecordingSink();
  const { client, clock } = makeClient(sink, { dedupeWindow: 0, maxPerHour: 2 });
  for (let i = 0; i < 5; i += 1) {
    client.captureMessage(`failure kind ${i}`, { typeName: `E${i}` });
  }
  await client.flush();
  assert.equal(sink.payloads.length, 2);

  clock.advance(3600);
  client.captureMessage("one more", { typeName: "Elast" });
  await client.flush();
  assert.equal(sink.payloads.at(-1).rate_limited, 3);
});

test("ignored types are dropped entirely", async () => {
  const sink = new RecordingSink();
  const { client } = makeClient(sink, { ignore: ["AbortError", "*.DoesNotExist"] });
  client.captureException(Object.assign(new Error("stop"), { name: "AbortError" }));
  client.captureMessage("gone", { typeName: "app.models.User.DoesNotExist" });
  client.captureMessage("real", { typeName: "ValueError" });
  await client.flush();
  assert.equal(sink.payloads.length, 1);
  assert.equal(sink.payloads[0].type, "ValueError");
  assert.equal(client.droppedByIgnore, 2);
});

test("secrets are redacted before delivery", async () => {
  const sink = new RecordingSink();
  const { client } = makeClient(sink);
  client.captureMessage(
    "auth failed with Bearer abc123def456 for postgres://u:p@db/app",
    { typeName: "AuthError", extra: { password: "hunter2", user: "ada" } },
  );
  await client.flush();
  const payload = sink.payloads[0];
  assert.ok(!payload.message.includes("abc123def456"));
  assert.match(payload.message, /Bearer \[redacted\]/);
  assert.match(payload.message, /postgres:\/\/\[redacted\]@db\/app/);
  assert.equal(payload.context.extra.password, "[redacted]");
  assert.equal(payload.context.extra.user, "ada");
});

test("redaction does not change grouping", async () => {
  // Fingerprints are computed before redaction, per spec section 6, so
  // changing a redaction rule can never regroup history.
  const plain = new RecordingSink();
  const { client: a } = makeClient(plain, { dedupeWindow: 300, maxPerHour: 0 });
  a.captureMessage("token Bearer aaaa111", { typeName: "AuthError" });
  await a.flush();

  const extra = new RecordingSink();
  const { client: b } = makeClient(extra, { redact: ["aaaa\\d+"] });
  b.captureMessage("token Bearer aaaa111", { typeName: "AuthError" });
  await b.flush();

  assert.equal(extra.payloads[0].fingerprint, plain.payloads[0].fingerprint);
});

test("the stack is truncated to the configured depth", async () => {
  const sink = new RecordingSink();
  const { client } = makeClient(sink, { stackFrames: 2 });
  const deep = (n) => { if (n === 0) throw new Error("bottom"); deep(n - 1); };
  try { deep(8); } catch (error) { client.captureException(error); }
  await client.flush();
  assert.equal(sink.payloads[0].stack.length, 2);
});

test("nothing is sent without a sink, or when disabled", async () => {
  const quiet = new Blare({ state: "memory", sinks: [], sinkObjects: [], synchronous: true,
    onWarning: () => {} });
  assert.equal(quiet.captureMessage("boom", { typeName: "E" }), false);

  const sink = new RecordingSink();
  const { client } = makeClient(sink, { enabled: false });
  assert.equal(client.captureMessage("boom", { typeName: "E" }), false);
  assert.deepEqual(sink.payloads, []);
});

test("a sink that throws does not break the caller", async () => {
  // Instrumentation failing must never become an application failure.
  const exploding = new RecordingSink({ throws: true });
  const { client } = makeClient(exploding);
  assert.equal(client.captureMessage("boom", { typeName: "E" }), true);
  await client.flush();
  assert.equal(client.stats().failed, 1);
});

test("non-Error throws are still reported", async () => {
  const sink = new RecordingSink();
  const { client } = makeClient(sink);
  client.captureException("just a string");
  client.captureException({ code: "E_WEIRD" });
  await client.flush();
  assert.equal(sink.payloads.length, 2);
  assert.equal(sink.payloads[0].message, "just a string");
});

test("a recovery notice, then the problem returns as new", async () => {
  const sink = new RecordingSink();
  const { client, clock } = makeClient(sink,
    { dedupeWindow: 300, maxPerHour: 0, resolveAfter: 3600 });
  client.captureMessage("pool exhausted", { typeName: "DBError" });
  clock.advance(4000);
  client.captureMessage("something else", { typeName: "OtherError" });
  await client.flush();
  assert.deepEqual(sink.states, ["new", "resolved", "new"]);

  clock.advance(1);
  client.captureMessage("pool exhausted", { typeName: "DBError" });
  await client.flush();
  assert.equal(sink.states.at(-1), "new", "a returning problem is news again");
});

test("selftest reports each sink", async () => {
  const sink = new RecordingSink();
  const { client } = makeClient(sink);
  assert.deepEqual(await client.selftest(), [["recording://", true]]);
  assert.equal(sink.payloads[0].type, "blare.SelfTest");
});

test("stats count suppression", async () => {
  const sink = new RecordingSink();
  const { client } = makeClient(sink, { dedupeWindow: 300, maxPerHour: 0 });
  for (let i = 0; i < 5; i += 1) client.captureMessage("same", { typeName: "E" });
  await client.flush();
  assert.equal(client.stats().delivered, 1);
  assert.equal(client.stats().suppressed, 4);
});

test("timestamps are RFC 3339 in UTC", async () => {
  const sink = new RecordingSink();
  const { client } = makeClient(sink, { clock: new FakeClock(1_700_000_000.5) });
  client.captureMessage("boom", { typeName: "E" });
  await client.flush();
  assert.equal(sink.payloads[0].timestamp, "2023-11-14T22:13:20.500Z");
});

test("the payload carries every field the spec names", async () => {
  const sink = new RecordingSink();
  const { client } = makeClient(sink);
  client.captureMessage("boom", { typeName: "E" });
  await client.flush();
  for (const field of ["blare_version", "fingerprint", "kind", "state", "level", "title",
    "type", "message", "logger", "service", "environment", "host", "timestamp", "runtime",
    "sdk", "location", "stack", "context", "occurrences", "rate_limited"]) {
    assert.ok(field in sink.payloads[0], `missing ${field}`);
  }
});
