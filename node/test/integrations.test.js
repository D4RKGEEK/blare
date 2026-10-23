/**
 * Framework integrations: request context in, error back out.
 *
 * The integrations are typed structurally, so these tests drive them with
 * minimal fakes rather than installing six frameworks as dev dependencies.
 */

import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";

import blare, { init, close } from "../dist/esm/index.js";
import { blareErrorHandler } from "../dist/esm/integrations/express.js";
import { blarePlugin } from "../dist/esm/integrations/fastify.js";
import { BlareExceptionFilter } from "../dist/esm/integrations/nest.js";
import { onRequestError, withBlare } from "../dist/esm/integrations/next.js";
import { blarePinoStream } from "../dist/esm/integrations/pino.js";
import { blareWinstonTransport } from "../dist/esm/integrations/winston.js";
import { requestContext } from "../dist/esm/integrations/shared.js";
import { RecordingSink, cleanEnvironment } from "./helpers.js";

let sink;

beforeEach(async () => {
  cleanEnvironment();
  await close();
  sink = new RecordingSink();
  init({
    state: "memory", service: "test", environment: "test", sinks: ["console"],
    sinkObjects: [sink], synchronous: true, captureCrashes: false,
    dedupeWindow: 300, maxPerHour: 0, onWarning: () => {},
  });
});

test("the request context carries only what the spec permits", () => {
  const context = requestContext(
    { method: "GET", originalUrl: "/users/4821?token=secret", route: { path: "/users/:id" } },
    500,
  );
  // The query string is where tokens live, and this is going to a chat room.
  assert.equal(context.path, "/users/4821");
  assert.ok(!JSON.stringify(context).includes("secret"));
  // The templated route means one broken endpoint is one alert, not one per id.
  assert.equal(context.route, "/users/:id");
  assert.equal(context.status, 500);
});

test("Express reports and then passes the error on", async () => {
  const passed = [];
  const handler = blareErrorHandler();
  handler(new Error("route blew up"), { method: "POST", originalUrl: "/pay" },
    { statusCode: 500 }, (error) => passed.push(error));
  await blare.flush();

  assert.equal(sink.payloads.length, 1);
  assert.deepEqual(sink.payloads[0].context.request, { method: "POST", path: "/pay", status: 500 });
  // Express still decides what the client sees; Blare only observes.
  assert.equal(passed.length, 1);
  assert.equal(passed[0].message, "route blew up");
});

test("Fastify reports through the onError hook", async () => {
  let hook;
  blarePlugin({ addHook: (name, fn) => { if (name === "onError") hook = fn; } }, {}, () => {});
  assert.ok(hook, "the plugin must register an onError hook");

  let continued = false;
  hook({ method: "GET", url: "/boom", routeOptions: { url: "/boom" } },
    { statusCode: 500 }, new Error("fastify blew up"), () => { continued = true; });
  await blare.flush();

  assert.equal(sink.payloads[0].context.request.path, "/boom");
  assert.equal(continued, true);
});

test("the Nest filter reports and rethrows", async () => {
  const filter = new BlareExceptionFilter();
  const host = {
    switchToHttp: () => ({
      getRequest: () => ({ method: "DELETE", url: "/orders/9" }),
      getResponse: () => ({ statusCode: 500 }),
    }),
  };
  assert.throws(() => filter.catch(new Error("nest blew up"), host), /nest blew up/);
  await blare.flush();
  assert.equal(sink.payloads[0].context.request.method, "DELETE");
});

test("Next's onRequestError reports with the route", async () => {
  onRequestError(new Error("server component failed"),
    { method: "GET", path: "/blog/hello?draft=1" },
    { routePath: "/blog/[slug]", routeType: "render" });
  await blare.flush();

  const payload = sink.payloads[0];
  assert.equal(payload.context.request.path, "/blog/hello");
  assert.equal(payload.context.request.route, "/blog/[slug]");
  assert.equal(payload.context.extra.routeType, "render");
});

test("withBlare reports and rethrows", async () => {
  const wrapped = withBlare(async () => { throw new Error("action failed"); });
  await assert.rejects(wrapped(), /action failed/);
  await blare.flush();
  assert.equal(sink.payloads.length, 1);
});

test("a pino stream turns existing log calls into alerts", async () => {
  const stream = blarePinoStream();
  stream.write(JSON.stringify({ level: 50, msg: "payment failed", name: "app.payments" }) + "\n");
  stream.write(JSON.stringify({ level: 30, msg: "just information" }) + "\n");
  await blare.flush();

  assert.equal(sink.payloads.length, 1, "info must not alert at the default level");
  assert.equal(sink.payloads[0].message, "payment failed");
  assert.equal(sink.payloads[0].logger, "app.payments");
});

test("a pino record carrying an error is classified by the error", async () => {
  const stream = blarePinoStream();
  stream.write(JSON.stringify({
    level: 50, msg: "wrapper message",
    err: { type: "TypeError", message: "underlying cause", stack: "TypeError: underlying cause" },
  }) + "\n");
  await blare.flush();
  assert.equal(sink.payloads[0].kind, "exception");
  assert.equal(sink.payloads[0].type, "TypeError");
});

test("pino records split across chunks are still parsed", async () => {
  const stream = blarePinoStream();
  const line = JSON.stringify({ level: 50, msg: "split record", name: "app" });
  stream.write(line.slice(0, 10));
  stream.write(line.slice(10) + "\n");
  await blare.flush();
  assert.equal(sink.payloads.length, 1);
  assert.equal(sink.payloads[0].message, "split record");
});

test("a winston transport turns existing log calls into alerts", async () => {
  const transport = blareWinstonTransport();
  transport.write({ level: "error", message: "nightly job failed" });
  transport.write({ level: "info", message: "just information" });
  await blare.flush();
  assert.equal(sink.payloads.length, 1);
  assert.equal(sink.payloads[0].message, "nightly job failed");
});

test("winston records carrying an error are classified by the error", async () => {
  const transport = blareWinstonTransport();
  transport.write({ level: "error", message: "wrapper", error: new RangeError("out of range") });
  await blare.flush();
  assert.equal(sink.payloads[0].type, "RangeError");
});

test("malformed logger input never throws into the host", async () => {
  const stream = blarePinoStream();
  assert.doesNotThrow(() => stream.write("not json at all\n"));
  const transport = blareWinstonTransport();
  assert.doesNotThrow(() => transport.write({}));
});

test("the module API is inert before init", async () => {
  await close();
  assert.equal(blare.captureMessage("boom"), false);
  assert.equal(blare.captureException(new Error("x")), false);
  assert.deepEqual(blare.stats(), {});
  assert.equal(await blare.flush(), true);
});
