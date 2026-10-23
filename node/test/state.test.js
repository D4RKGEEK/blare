import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { FileStore, MemoryStore, RETENTION_SECONDS, buildStore, defaultFilePath,
  prune } from "../dist/esm/state.js";

const scratch = () => mkdtempSync(join(tmpdir(), "blare-test-"));

test("memory state round-trips", () => {
  const store = new MemoryStore();
  store.transaction((d) => { d.groups.abc = { total: 1, last_seen: 0 }; });
  store.transaction((d) => assert.equal(d.groups.abc.total, 1));
});

test("file state persists across instances", () => {
  const path = join(scratch(), "state.json");
  new FileStore(path).transaction((d) => { d.groups.abc = { total: 7, last_seen: 0 }; });
  new FileStore(path).transaction((d) => assert.equal(d.groups.abc.total, 7));
});

test("file state is written atomically and leaves no temporary files", () => {
  const dir = scratch();
  const path = join(dir, "state.json");
  new FileStore(path).transaction((d) => { d.groups.abc = { total: 1, last_seen: 0 }; });
  assert.equal(JSON.parse(readFileSync(path, "utf8")).groups.abc.total, 1);
  assert.deepEqual(readdirSync(dir).filter((f) => f.endsWith(".tmp")), []);
});

test("a corrupt state file does not stop the application alerting", () => {
  const path = join(scratch(), "state.json");
  writeFileSync(path, "{not json at all");
  new FileStore(path).transaction((d) => assert.deepEqual(d.groups, {}));
});

test("a foreign schema is discarded rather than trusted", () => {
  const path = join(scratch(), "state.json");
  writeFileSync(path, JSON.stringify({ schema: 99, groups: { x: {} } }));
  new FileStore(path).transaction((d) => assert.deepEqual(d.groups, {}));
});

test("pruning forgets groups nobody has seen for a day", () => {
  const document = {
    schema: 1,
    groups: { old: { last_seen: 0 }, fresh: { last_seen: RETENTION_SECONDS + 10 } },
    bucket: {}, suppressed_by_cap: 0,
  };
  prune(document, RETENTION_SECONDS + 20);
  assert.deepEqual(Object.keys(document.groups), ["fresh"]);
});

test("the service name is sanitised for the filename", () => {
  assert.ok(!defaultFilePath("acme/checkout api").includes("/acme/checkout"));
});

test("an unknown backend degrades loudly instead of throwing", () => {
  // An alerting library must never be the reason a deploy fails.
  const warnings = [];
  const store = buildStore("postgres://nope", "svc", (m) => warnings.push(m));
  assert.equal(store.name, "memory");
  assert.match(warnings.join(" "), /unknown BLARE_STATE/);
});

test("redis is not yet implemented, and says so", () => {
  const warnings = [];
  const store = buildStore("redis://localhost:6379", "svc", (m) => warnings.push(m));
  assert.equal(store.name, "file");
  assert.match(warnings.join(" "), /no Redis state backend yet/);
});
