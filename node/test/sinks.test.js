/** Sink detection, rendering and the delivery retry policy. */

import test from "node:test";
import assert from "node:assert/strict";

import { ConfigError } from "../dist/esm/errors.js";
import { toPayload } from "../dist/esm/event.js";
import { Redactor } from "../dist/esm/redact.js";
import { ConsoleSink, DiscordSink, GenericSink, SlackSink, TeamsSink,
  buildSink, buildSinks } from "../dist/esm/sinks/index.js";

function samplePayload(overrides = {}) {
  return new Redactor().value(toPayload({
    fingerprint: "9f2a41c7b0e3d518", kind: "exception", level: "error",
    typeName: "OperationalError", message: "connection pool exhausted",
    service: "checkout-api", environment: "production", host: "web-3",
    timestamp: 1_700_000_000, state: "recurring", logger: "app.payments",
    file: "app/payments.js", function: "charge", line: 142,
    stack: ["app/payments.js:142 in charge", "app/routes.js:88 in postPay"],
    request: { method: "POST", path: "/pay", status: 500 },
    sinceLastAlert: 847, total: 1203, firstSeen: 1_699_999_000, windowSeconds: 300,
    ...overrides,
  }));
}

test("build picks the provider from the URL", () => {
  assert.ok(buildSink("https://hooks.slack.com/services/T/B/x") instanceof SlackSink);
  assert.ok(buildSink("https://discord.com/api/webhooks/1/x") instanceof DiscordSink);
  assert.ok(buildSink("https://acme.webhook.office.com/x") instanceof TeamsSink);
  assert.ok(buildSink("https://alerts.internal/x") instanceof GenericSink);
  assert.ok(buildSink("console") instanceof ConsoleSink);
  assert.equal(buildSinks(["console", "https://hooks.slack.com/services/T/B/x"]).length, 2);
});

test("bad sinks are rejected at startup", () => {
  assert.throws(() => buildSink("carrierpigeon+https://acme.dev/hook"), /unknown provider/);
  assert.throws(() => buildSink("ftp://acme.dev/hook"), /unsupported scheme/);
  assert.throws(() => buildSink(""), ConfigError);
});

test("the webhook URL never reaches a log", () => {
  // The URL is the credential, so the secret path must not be loggable.
  const sink = buildSink("https://hooks.slack.com/services/T000/B000/sUpErSeCrEt");
  assert.ok(!sink.redactedUrl().includes("sUpErSeCrEt"));
  assert.match(sink.redactedUrl(), /hooks\.slack\.com/);
});

test("Slack rendering carries the count, the place and the fallback line", () => {
  const body = new SlackSink("https://hooks.slack.com/services/T/B/x").render(samplePayload());
  const blocks = JSON.stringify(body.blocks);
  assert.match(blocks, /847 times in the last 5 min/);
  assert.match(blocks, /app\/payments\.js:142 in charge/);
  assert.match(blocks, /9f2a41c7b0e3d518/);
  assert.match(blocks, /POST/);
  // The fallback text must stand alone for notifications and screen readers.
  assert.match(body.text, /checkout-api/);
  assert.match(body.text, /OperationalError/);
});

test("Slack headers stay within the API limit", () => {
  const body = new SlackSink("https://hooks.slack.com/services/T/B/x")
    .render(samplePayload({ message: "x".repeat(500) }));
  assert.ok(body.blocks[0].text.text.length <= 150);
});

test("Discord fields stay within the API limit", () => {
  const stack = Array.from({ length: 200 }, (_, i) => `app/f${i}.js:${i} in handler`);
  const body = new DiscordSink("https://discord.com/api/webhooks/1/x")
    .render(samplePayload({ stack }));
  for (const field of body.embeds[0].fields) assert.ok(field.value.length <= 1024);
  assert.equal(typeof body.embeds[0].color, "number");
});

test("Teams picks the card shape from the hostname", () => {
  // The two shapes are not interchangeable: the wrong one is accepted and
  // then silently displays nothing.
  const workflow = new TeamsSink("https://prod-1.westus.logic.azure.com/workflows/x");
  assert.equal(workflow.usesAdaptiveCard, true);
  const card = workflow.render(samplePayload());
  assert.equal(card.type, "message");
  assert.equal(card.attachments[0].content.type, "AdaptiveCard");

  const legacy = new TeamsSink("https://acme.webhook.office.com/webhookb2/x");
  assert.equal(legacy.usesAdaptiveCard, false);
  const message = legacy.render(samplePayload());
  assert.equal(message["@type"], "MessageCard");
  assert.match(JSON.stringify(message.sections), /847 times/);
});

test("the generic sink posts the canonical event verbatim", () => {
  const payload = samplePayload();
  assert.deepEqual(new GenericSink("https://alerts.internal/x").render(payload), payload);
});

test("a resolved alert reads as a recovery", () => {
  const body = new SlackSink("https://hooks.slack.com/services/T/B/x")
    .render(samplePayload({ state: "resolved" }));
  assert.match(JSON.stringify(body.blocks), /Recovered/);
});

test("the rate-limit note is surfaced", () => {
  const body = new SlackSink("https://hooks.slack.com/services/T/B/x")
    .render(samplePayload({ rateLimited: 12 }));
  assert.match(JSON.stringify(body.blocks), /12 alerts dropped/);
});

// -- delivery --------------------------------------------------------------

function withFetch(implementation, run) {
  const original = globalThis.fetch;
  globalThis.fetch = implementation;
  return Promise.resolve(run()).finally(() => { globalThis.fetch = original; });
}

test("a successful post reports success and sends the canonical event", async () => {
  const calls = [];
  await withFetch(async (url, init) => {
    calls.push([url, JSON.parse(init.body)]);
    return new Response("", { status: 200 });
  }, async () => {
    assert.equal(await new GenericSink("https://alerts.internal/x").send(samplePayload()), true);
  });
  assert.equal(calls[0][0], "https://alerts.internal/x");
  assert.equal(calls[0][1].fingerprint, "9f2a41c7b0e3d518");
});

test("a client error is not retried", async () => {
  // A 400 means the payload or URL is wrong; repeating it wastes time.
  let attempts = 0;
  await withFetch(async () => { attempts += 1; return new Response("", { status: 400 }); },
    async () => {
      const sink = new GenericSink("https://alerts.internal/x");
      sink.onWarning = () => {};
      sink.retryDelaysMs = [0, 0];
      assert.equal(await sink.send(samplePayload()), false);
    });
  assert.equal(attempts, 1);
});

test("a server error is retried, and a retry can succeed", async () => {
  let attempts = 0;
  await withFetch(async () => {
    attempts += 1;
    return attempts === 1 ? new Response("", { status: 503 }) : new Response("", { status: 200 });
  }, async () => {
    const sink = new GenericSink("https://alerts.internal/x");
    sink.onWarning = () => {};
    sink.retryDelaysMs = [0, 0];
    assert.equal(await sink.send(samplePayload()), true);
  });
  assert.equal(attempts, 2);
});

test("delivery never throws into the host", async () => {
  await withFetch(async () => { throw new Error("something nobody anticipated"); },
    async () => {
      const sink = new GenericSink("https://alerts.internal/x");
      sink.onWarning = () => {};
      sink.retryDelaysMs = [0, 0];
      assert.equal(await sink.send(samplePayload()), false);
    });
});
