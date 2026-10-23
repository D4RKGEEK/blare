/** The package must work for both module systems, since Express apps are CJS. */

import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

test("the ESM entry point exports the public API", async () => {
  const esm = await import("../dist/esm/index.js");
  for (const name of ["init", "captureException", "captureMessage", "flush", "close",
    "selftest", "stats", "getClient", "Blare", "Config"]) {
    assert.equal(typeof esm[name], "function", `missing ${name}`);
  }
  assert.equal(esm.SPEC_VERSION, "1");
});

test("the CommonJS entry point works too", () => {
  const cjs = require("../dist/cjs/index.js");
  assert.equal(typeof cjs.init, "function");
  assert.equal(typeof cjs.default.init, "function");
  assert.equal(cjs.SPEC_VERSION, "1");
});

test("every integration subpath loads on its own", async () => {
  for (const name of ["express", "fastify", "nest", "next", "pino", "winston"]) {
    const loaded = await import(`../dist/esm/integrations/${name}.js`);
    assert.ok(Object.keys(loaded).length > 0, `${name} exports nothing`);
    assert.ok(require(`../dist/cjs/integrations/${name}.js`), `${name} fails under CJS`);
  }
});
