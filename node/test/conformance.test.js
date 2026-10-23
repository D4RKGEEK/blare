/**
 * Every port must pass these. The fixtures live in ../../conformance/.
 *
 * This is what makes "one spec, every language" a fact rather than a promise:
 * these are the same bytes the Python port is tested against.
 */

import test from "node:test";
import assert from "node:assert/strict";

import { normalizeMessage } from "../dist/esm/normalize.js";
import * as fp from "../dist/esm/fingerprint.js";
import { Redactor } from "../dist/esm/redact.js";
import { detectProvider } from "../dist/esm/sinks/index.js";
import { Decider } from "../dist/esm/decide.js";
import { MemoryStore } from "../dist/esm/state.js";
import { ConfigError } from "../dist/esm/errors.js";
import { loadFixture } from "./helpers.js";

test("normalization matches the spec, case by case", async (t) => {
  for (const testCase of loadFixture("normalize.json").cases) {
    await t.test(testCase.id, () => {
      assert.equal(normalizeMessage(testCase.in), testCase.out);
    });
  }
});

test("the application frame is chosen the same way", async (t) => {
  for (const testCase of loadFixture("vendor_frames.json").cases) {
    await t.test(testCase.id, () => {
      assert.equal(fp.selectPathIndex(testCase.frames), testCase.expected_index);
    });
  }
});

test("sink detection matches the spec", async (t) => {
  for (const testCase of loadFixture("sink_detection.json").cases) {
    await t.test(testCase.id, () => {
      if (testCase.error) {
        assert.throws(() => detectProvider(testCase.url), ConfigError);
      } else {
        assert.equal(detectProvider(testCase.url)[0], testCase.provider);
      }
    });
  }
});

test("text redaction matches the spec", async (t) => {
  const redactor = new Redactor();
  for (const testCase of loadFixture("redaction.json").text_cases) {
    await t.test(testCase.id, () => {
      assert.equal(redactor.text(testCase.in), testCase.out);
    });
  }
});

test("structure redaction matches the spec", async (t) => {
  const redactor = new Redactor();
  for (const testCase of loadFixture("redaction.json").mapping_cases) {
    await t.test(testCase.id, () => {
      assert.deepEqual(redactor.value(testCase.in), testCase.out);
    });
  }
});

test("fingerprints are byte-identical to the other ports", async (t) => {
  const cases = loadFixture("fingerprint.json").cases;
  assert.ok(cases.length > 0, "fingerprint fixture is empty");
  for (const testCase of cases) {
    await t.test(testCase.id, () => {
      assert.equal(
        fp.compute(testCase.kind, testCase.type, testCase.location, testCase.message),
        testCase.fingerprint,
      );
    });
  }
});

test("dedupe timelines produce exactly the listed alerts", async (t) => {
  for (const testCase of loadFixture("dedupe.json").cases) {
    await t.test(testCase.id, () => {
      const config = testCase.config;
      const decider = new Decider(new MemoryStore(), {
        dedupeWindow: config.dedupe_window ?? 300,
        maxPerHour: config.max_per_hour ?? 0,
        ignore: config.ignore ?? [],
        resolveAfter: config.resolve_after ?? 0,
      });

      const sent = [];
      for (const event of testCase.events) {
        const now = event.t;
        const outcome = decider.evaluate(
          {
            fingerprint: event.fp,
            typeName: event.type ?? "",
            title: event.title ?? "",
            logger: event.logger ?? "",
          },
          now,
        );
        for (const [fingerprint, notice] of outcome.resolved) {
          sent.push({
            t: now, fp: fingerprint, state: notice.state,
            since_last_alert: notice.sinceLastAlert, total: notice.total,
            rate_limited: notice.rateLimited,
          });
        }
        const decision = outcome.decision;
        if (decision && decision.send) {
          sent.push({
            t: now, fp: event.fp, state: decision.state,
            since_last_alert: decision.sinceLastAlert, total: decision.total,
            rate_limited: decision.rateLimited,
          });
        }
      }

      const expected = testCase.sends;
      assert.equal(sent.length, expected.length,
        `expected ${expected.length} alerts, got ${sent.length}: ${JSON.stringify(sent)}`);
      for (const [index, want] of expected.entries()) {
        const actual = sent[index];
        assert.equal(actual.fp, want.fp);
        assert.equal(actual.t, want.t);
        for (const field of ["state", "since_last_alert", "total", "rate_limited"]) {
          if (field in want) {
            assert.equal(actual[field], want[field],
              `${want.fp} at t=${want.t}: ${field} was ${actual[field]}, expected ${want[field]}`);
          }
        }
      }
    });
  }
});
