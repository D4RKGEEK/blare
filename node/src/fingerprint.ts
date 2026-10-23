/**
 * Fingerprinting. SPEC.md sections 5.6 and 5.7.
 *
 * The fingerprint answers "is this the same problem as last time?". It must be
 * byte-identical to every other port, which is what
 * `conformance/fingerprint.json` guarantees.
 */

import { createHash } from "node:crypto";
import { sep, relative, resolve, isAbsolute } from "node:path";
import { normalizeMessage } from "./normalize.js";

/** U+001F, the unit separator the spec joins the canonical string with. */
export const UNIT_SEPARATOR = "\u001f";
export const LENGTH = 16;

/** Section 5.7: a frame under any of these is somebody else's code. */
export const VENDOR_SEGMENTS = [
  "site-packages", "dist-packages", "node_modules", "vendor", ".venv", "venv",
  "/usr/lib/python", "/go/pkg/mod", ".cargo/registry", ".gradle/caches",
  ".m2/repository",
] as const;

export interface Location {
  file: string;
  function: string;
  line: number;
}

export const EMPTY_LOCATION: Location = { file: "", function: "", line: 0 };

export function locationKey(location: Location): string {
  if (!location.file) return "";
  return `${location.file}:${location.function}:${location.line}`;
}

/** True when `path` belongs to a dependency, to Node itself, or to Blare. */
export function isVendorPath(path: string): boolean {
  if (!path) return true;
  const normalized = path.replace(/\\/g, "/");
  // Node's own internals surface as "node:fs" or "internal/process/...".
  if (normalized.startsWith("node:") || normalized.startsWith("internal/")) return true;
  for (const segment of VENDOR_SEGMENTS) {
    const needle = segment.replace(/\\/g, "/");
    if (needle.startsWith("/")) {
      if (normalized.includes(needle)) return true;
    } else if (normalized.includes(`/${needle}/`) || normalized.startsWith(`${needle}/`)) {
      return true;
    }
  }
  // Blare's own frames must never be blamed for the host's bug.
  if (/\/blare\/dist\/(esm|cjs)\//.test(normalized)) return true;
  return false;
}

/**
 * Path relative to the application root, with forward slashes.
 *
 * Fingerprints must survive a redeploy into a different absolute directory, so
 * the absolute path never enters the hash.
 */
export function relativePath(path: string, root?: string): string {
  if (!path) return "";
  let candidate = path;
  if (candidate.startsWith("file://")) {
    try {
      candidate = new URL(candidate).pathname;
    } catch {
      /* leave it as it came */
    }
  }
  const base = resolve(root ?? process.cwd());
  if (isAbsolute(candidate)) {
    const rel = relative(base, candidate);
    if (rel && !rel.startsWith("..")) return rel.split(sep).join("/");
  } else {
    return candidate.replace(/\\/g, "/");
  }
  const parts = candidate.replace(/\\/g, "/").split("/");
  return parts.length > 3 ? parts.slice(-3).join("/") : parts.join("/");
}

/**
 * Index of the application frame in an innermost-first list of paths.
 *
 * Mirrors the frame choice below for the language-neutral conformance fixture.
 */
export function selectPathIndex(paths: readonly string[]): number | null {
  if (paths.length === 0) return null;
  for (let index = 0; index < paths.length; index += 1) {
    if (!isVendorPath(paths[index] as string)) return index;
  }
  return 0;
}

interface ParsedFrame {
  file: string;
  function: string;
  line: number;
}

const FRAME_WITH_NAME = /^\s*at\s+(.+?)\s+\((.+):(\d+):(\d+)\)$/;
const FRAME_BARE = /^\s*at\s+(.+):(\d+):(\d+)$/;

/** Parse a V8 stack string into frames, innermost first. */
export function parseStack(stack: string | undefined): ParsedFrame[] {
  if (!stack) return [];
  const frames: ParsedFrame[] = [];
  for (const raw of stack.split("\n")) {
    const named = FRAME_WITH_NAME.exec(raw);
    if (named) {
      frames.push({
        function: named[1] as string,
        file: named[2] as string,
        line: Number(named[3]),
      });
      continue;
    }
    const bare = FRAME_BARE.exec(raw);
    if (bare) {
      frames.push({
        function: "<anonymous>",
        file: bare[1] as string,
        line: Number(bare[2]),
      });
    }
  }
  return frames;
}

/** Resolve the application frame and a readable stack from an error. */
export function locationFromError(
  error: unknown,
  root?: string,
): { location: Location; stack: string[] } {
  const stack = error instanceof Error ? error.stack : undefined;
  const frames = parseStack(stack);
  if (frames.length === 0) return { location: { ...EMPTY_LOCATION }, stack: [] };

  let chosen = frames[0] as ParsedFrame;
  for (const frame of frames) {
    if (!isVendorPath(frame.file)) {
      chosen = frame;
      break;
    }
  }
  return {
    location: {
      file: relativePath(chosen.file, root),
      function: chosen.function,
      line: chosen.line,
    },
    stack: frames.map(
      (frame) => `${relativePath(frame.file, root)}:${frame.line} in ${frame.function}`,
    ),
  };
}

/** The fingerprint itself. Section 5.6. */
export function compute(
  kind: string,
  typeName: string,
  location: string,
  message: string,
): string {
  const canonical = [kind, typeName, location, normalizeMessage(message)].join(UNIT_SEPARATOR);
  return createHash("sha256").update(canonical, "utf8").digest("hex").slice(0, LENGTH);
}
