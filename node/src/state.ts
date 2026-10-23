/**
 * Dedupe state. SPEC.md section 5.4.
 *
 * The store is the only shared, mutable thing in Blare. It is what lets four
 * cluster workers seeing the same crash send one alert instead of four, so the
 * default backend is a lock-guarded file rather than per-process memory.
 *
 * Node has no `flock` in its standard library, so the lock is an exclusive
 * file create with a stale timeout. That is weaker than an OS lock: a process
 * killed mid-transaction leaves a lock that the next writer waits out.
 *
 * The transaction is synchronous and so briefly blocks the event loop. It is
 * bounded: the lock is held only for a small read, mutate and atomic rename,
 * and a contended wait gives up after about 180ms and proceeds anyway. The
 * cost of giving up is at worst a duplicate alert, which is always cheaper
 * than stalling the process. Set BLARE_STATE=memory to avoid the file
 * entirely when a single process is the whole deployment.
 */

import { mkdirSync, openSync, closeSync, readFileSync, renameSync, rmSync,
  writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

export const RETENTION_SECONDS = 24 * 60 * 60;
export const SCHEMA = 1;
const LOCK_STALE_MS = 5000;
const LOCK_RETRY_MS = 3;
const LOCK_ATTEMPTS = 60;

export interface Group {
  first_seen: number;
  last_seen: number;
  last_sent: number;
  count_since_sent: number;
  total: number;
  ever_sent: boolean;
}

export interface Bucket {
  tokens?: number;
  ts?: number;
}

export interface Document {
  schema: number;
  groups: Record<string, Group>;
  bucket: Bucket;
  suppressed_by_cap: number;
}

export function emptyDocument(): Document {
  return { schema: SCHEMA, groups: {}, bucket: {}, suppressed_by_cap: 0 };
}

function isValid(document: unknown): document is Document {
  return (
    !!document &&
    typeof document === "object" &&
    (document as Document).schema === SCHEMA &&
    !!(document as Document).groups &&
    typeof (document as Document).groups === "object"
  );
}

/** Forget groups nobody has seen for a day. */
export function prune(document: Document, now: number): void {
  for (const [key, group] of Object.entries(document.groups)) {
    if (now - Number(group.last_seen ?? 0) > RETENTION_SECONDS) {
      delete document.groups[key];
    }
  }
}

export interface Store {
  readonly name: string;
  /** Read, let `mutate` change the document, write it back under a lock. */
  transaction<T>(mutate: (document: Document) => T): T;
  close(): void;
}

/** Per-process state. Correct, but each process alerts on its own. */
export class MemoryStore implements Store {
  readonly name = "memory";
  private document = emptyDocument();

  transaction<T>(mutate: (document: Document) => T): T {
    return mutate(this.document);
  }

  close(): void {
    /* nothing held */
  }
}

/** State in one file, shared by every process on the host. */
export class FileStore implements Store {
  readonly name = "file";
  readonly path: string;
  private readonly lockPath: string;

  constructor(path: string) {
    this.path = path;
    this.lockPath = `${path}.lock`;
    mkdirSync(dirname(path), { recursive: true });
  }

  transaction<T>(mutate: (document: Document) => T): T {
    const held = this.acquire();
    try {
      const document = this.read();
      const result = mutate(document);
      this.write(document);
      return result;
    } finally {
      if (held) this.release();
    }
  }

  private acquire(): boolean {
    for (let attempt = 0; attempt < LOCK_ATTEMPTS; attempt += 1) {
      try {
        closeSync(openSync(this.lockPath, "wx"));
        return true;
      } catch {
        // A lock left behind by a killed process must not stop alerting
        // forever, so one that is clearly stale is taken over.
        try {
          const age = Date.now() - Number(readFileSync(this.lockPath, "utf8") || 0);
          if (age > LOCK_STALE_MS) {
            rmSync(this.lockPath, { force: true });
            continue;
          }
        } catch {
          /* the holder is writing it right now */
        }
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, LOCK_RETRY_MS);
      }
    }
    // Proceeding without the lock risks a lost update, which costs at worst a
    // duplicate alert. Blocking the application would cost more.
    return false;
  }

  private release(): void {
    try {
      rmSync(this.lockPath, { force: true });
    } catch {
      /* already gone */
    }
  }

  private read(): Document {
    try {
      const parsed: unknown = JSON.parse(readFileSync(this.path, "utf8"));
      return isValid(parsed) ? parsed : emptyDocument();
    } catch {
      return emptyDocument();
    }
  }

  private write(document: Document): void {
    // Write to a sibling file and rename it over the target, so a crash
    // mid-write cannot leave a truncated document behind.
    const temporary = `${this.path}.${process.pid}.tmp`;
    try {
      writeFileSync(temporary, JSON.stringify(document), "utf8");
      renameSync(temporary, this.path);
    } catch {
      try {
        rmSync(temporary, { force: true });
      } catch {
        /* nothing more to do */
      }
    }
  }

  close(): void {
    /* nothing held between transactions */
  }
}

export function defaultFilePath(service: string): string {
  const safe =
    [...service].map((c) => (/[A-Za-z0-9\-_]/.test(c) ? c : "-")).join("") || "blare";
  return join(tmpdir(), `blare-${safe}.json`);
}

/**
 * Create the store named by `BLARE_STATE`.
 *
 * Falls back to memory rather than preventing the application from starting:
 * an alerting library must never be the reason a deploy fails.
 */
export function buildStore(
  spec: string,
  service: string,
  onWarning?: (message: string) => void,
): Store {
  const chosen = (spec || "file").trim();
  try {
    if (chosen === "memory") return new MemoryStore();
    if (chosen === "file") return new FileStore(defaultFilePath(service));
    if (chosen.startsWith("file:")) return new FileStore(chosen.slice("file:".length));
    if (/^rediss?:\/\//.test(chosen) || chosen.startsWith("unix://")) {
      onWarning?.(
        "blare: the Node port has no Redis state backend yet, so each host " +
          "will deduplicate on its own; using the shared file instead",
      );
      return new FileStore(defaultFilePath(service));
    }
  } catch (error) {
    onWarning?.(
      `blare: state backend ${JSON.stringify(chosen)} unavailable (${String(error)}); ` +
        "falling back to in-process memory, so each process will deduplicate on its own",
    );
    return new MemoryStore();
  }
  onWarning?.(`blare: unknown BLARE_STATE=${JSON.stringify(chosen)}; using in-process memory`);
  return new MemoryStore();
}
