/** Queueing and delivery isolation. */

import test from "node:test";
import assert from "node:assert/strict";

import { QUEUE_SIZE, Transport } from "../dist/esm/transport.js";
import { RecordingSink } from "./helpers.js";

test("events reach every sink", async () => {
  const first = new RecordingSink();
  const second = new RecordingSink();
  const transport = new Transport([first, second]);
  transport.submit({ title: "boom" });
  assert.equal(await transport.flush(), true);
  assert.deepEqual(first.payloads, [{ title: "boom" }]);
  assert.deepEqual(second.payloads, [{ title: "boom" }]);
});

test("one broken sink does not cost you the others", async () => {
  // A dead Discord webhook must not stop the Slack alert someone is watching.
  const broken = new RecordingSink({ throws: true });
  const working = new RecordingSink();
  const transport = new Transport([broken, working]);
  transport.onWarning = () => {};
  transport.submit({ title: "boom" });
  await transport.flush();
  assert.deepEqual(working.payloads, [{ title: "boom" }]);
  assert.equal(transport.failed, 1);
});

test("a full queue drops rather than blocking", async () => {
  // Back-pressure from a chat webhook must never reach production traffic.
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const blocking = { redactedUrl: () => "blocking://", send: () => gate.then(() => true) };

  const transport = new Transport([blocking]);
  transport.onWarning = () => {};
  let accepted = 0;
  for (let i = 0; i < QUEUE_SIZE + 50; i += 1) if (transport.submit({ n: i })) accepted += 1;
  release();
  assert.ok(accepted <= QUEUE_SIZE + 1, "the queue must be bounded");
  assert.ok(transport.dropped > 0);
  await transport.flush(1000);
});

test("submitting after close is a no-op", async () => {
  const transport = new Transport([new RecordingSink()]);
  await transport.close();
  assert.equal(transport.submit({ title: "boom" }), false);
});
