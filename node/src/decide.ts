/**
 * The decision engine. SPEC.md sections 5.1 to 5.5.
 *
 * This module is the reason Blare exists. Capturing errors is easy and
 * delivering them is easy; deciding which of 10,000 identical failures
 * deserves a message is the part that keeps a channel readable, and therefore
 * keeps it unmuted.
 *
 * Nothing here does I/O, and the clock is injected, so the whole policy is
 * testable against `conformance/dedupe.json` without sleeping.
 */

import { prune, type Document, type Group, type Store } from "./state.js";

export const NEW = "new";
export const RECURRING = "recurring";
export const RESOLVED = "resolved";

export interface Candidate {
  fingerprint: string;
  typeName?: string;
  title?: string;
  logger?: string;
}

export interface Decision {
  send: boolean;
  state: string;
  sinceLastAlert: number;
  total: number;
  firstSeen: number;
  rateLimited: number;
  reason?: string;
}

export interface Outcome {
  decision: Decision | null;
  resolved: Array<[string, Decision]>;
}

export interface DeciderOptions {
  dedupeWindow?: number;
  maxPerHour?: number;
  ignore?: readonly string[];
  resolveAfter?: number;
}

/** Translate one `BLARE_IGNORE` glob into a regular expression. */
function globToRegExp(pattern: string): RegExp {
  let out = "";
  for (const char of pattern) {
    if (char === "*") out += ".*";
    else if (char === "?") out += ".";
    else out += char.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  }
  return new RegExp(`^${out}$`);
}

/** Applies the ignore list, the dedupe window, and the hourly cap. */
export class Decider {
  private readonly store: Store;
  private readonly window: number;
  private readonly cap: number;
  private readonly ignore: RegExp[];
  private readonly resolveAfter: number;

  constructor(store: Store, options: DeciderOptions = {}) {
    this.store = store;
    this.window = Math.max(0, options.dedupeWindow ?? 300);
    this.cap = Math.max(0, options.maxPerHour ?? 20);
    this.ignore = (options.ignore ?? []).map(globToRegExp);
    this.resolveAfter = Math.max(0, options.resolveAfter ?? 0);
  }

  /** Section 5.3: glob match against type, title, then logger. */
  ignored(candidate: Candidate): boolean {
    if (this.ignore.length === 0) return false;
    const subjects = [candidate.typeName, candidate.title, candidate.logger];
    return this.ignore.some((pattern) =>
      subjects.some((subject) => !!subject && pattern.test(subject)),
    );
  }

  /** Decide what to do with `candidate` and advance the stored state. */
  evaluate(candidate: Candidate, now: number): Outcome {
    if (this.ignored(candidate)) {
      // Dropped events leave no trace at all, so an ignored exception cannot
      // inflate the count of anything else.
      return { decision: null, resolved: [] };
    }
    return this.store.transaction((document) => {
      const resolved = this.collectResolved(document, now);
      const decision = this.evaluateOne(document, candidate, now);
      prune(document, now);
      return { decision, resolved };
    });
  }

  /** Emit recovery notices without an event to hang them off. */
  flushResolved(now: number): Array<[string, Decision]> {
    if (!this.resolveAfter) return [];
    return this.store.transaction((document) => {
      const resolved = this.collectResolved(document, now);
      prune(document, now);
      return resolved;
    });
  }

  private evaluateOne(document: Document, candidate: Candidate, now: number): Decision {
    let group = document.groups[candidate.fingerprint];
    if (!group) {
      group = {
        first_seen: now, last_seen: now, last_sent: 0,
        count_since_sent: 0, total: 0, ever_sent: false,
      } satisfies Group;
      document.groups[candidate.fingerprint] = group;
    }

    group.last_seen = now;
    group.total += 1;
    group.count_since_sent += 1;

    const neverSent = !group.ever_sent;
    const windowOpen = neverSent || now - group.last_sent >= this.window;
    if (!windowOpen) {
      return {
        send: false, state: RECURRING, sinceLastAlert: group.count_since_sent,
        total: group.total, firstSeen: group.first_seen, rateLimited: 0,
        reason: "within dedupe window",
      };
    }

    // The window is open, but the hourly cap gets the last word. When it
    // refuses, the group keeps accumulating: the suppressed occurrences are
    // reported on whichever alert eventually gets through.
    if (!this.takeToken(document, now)) {
      document.suppressed_by_cap += 1;
      return {
        send: false, state: RECURRING, sinceLastAlert: group.count_since_sent,
        total: group.total, firstSeen: group.first_seen, rateLimited: 0,
        reason: "hourly cap reached",
      };
    }

    const decision: Decision = {
      send: true,
      state: neverSent ? NEW : RECURRING,
      sinceLastAlert: group.count_since_sent,
      total: group.total,
      firstSeen: group.first_seen,
      rateLimited: document.suppressed_by_cap,
    };
    group.count_since_sent = 0;
    group.last_sent = now;
    group.ever_sent = true;
    document.suppressed_by_cap = 0;
    return decision;
  }

  /** Section 5.5: announce problems that have stopped happening. */
  private collectResolved(document: Document, now: number): Array<[string, Decision]> {
    if (!this.resolveAfter) return [];
    const notices: Array<[string, Decision]> = [];
    for (const [fingerprint, group] of Object.entries(document.groups)) {
      if (!group.ever_sent) continue;
      if (now - Number(group.last_seen ?? 0) < this.resolveAfter) continue;
      notices.push([
        fingerprint,
        {
          send: true, state: RESOLVED, sinceLastAlert: 0,
          total: group.total ?? 0, firstSeen: group.first_seen ?? 0, rateLimited: 0,
        },
      ]);
      // Clearing the group means a return of this problem is announced as new,
      // which is what an operator expects after a recovery notice.
      delete document.groups[fingerprint];
    }
    return notices;
  }

  /** Token bucket for section 5.2. A cap of 0 disables the limit. */
  private takeToken(document: Document, now: number): boolean {
    if (!this.cap) return true;
    const bucket = document.bucket ?? {};
    let tokens = Number(bucket.tokens ?? this.cap);
    const updatedAt = Number(bucket.ts ?? now);
    const rate = this.cap / 3600;
    tokens = Math.min(this.cap, tokens + Math.max(0, now - updatedAt) * rate);
    if (tokens < 1) {
      document.bucket = { tokens, ts: now };
      return false;
    }
    document.bucket = { tokens: tokens - 1, ts: now };
    return true;
  }
}
