/**
 * Configuration. SPEC.md section 2.
 *
 * Every port reads the same variable names with the same defaults, so one set
 * of deployment settings describes a polyglot fleet.
 */

import { hostname } from "node:os";
import { basename, dirname, resolve } from "node:path";
import { ConfigError } from "./errors.js";

export const LEVELS: Record<string, number> = {
  DEBUG: 10, INFO: 20, WARNING: 30, ERROR: 40, CRITICAL: 50,
};

const TRUE = new Set(["1", "true", "yes", "on"]);
const FALSE = new Set(["0", "false", "no", "off"]);

/** Section 2.1: the order is normative, so one deployment gets one name. */
const PLATFORM_VARS = [
  "K_SERVICE", "FLY_APP_NAME", "RENDER_SERVICE_NAME", "HEROKU_APP_NAME",
  "VERCEL_URL", "WEBSITE_SITE_NAME",
] as const;

function env(name: string): string | undefined {
  const value = process.env[name];
  if (value === undefined) return undefined;
  const trimmed = value.trim();
  return trimmed === "" ? undefined : trimmed;
}

function readBoolean(name: string, fallback: boolean): boolean {
  const raw = env(name);
  if (raw === undefined) return fallback;
  const lowered = raw.toLowerCase();
  if (TRUE.has(lowered)) return true;
  if (FALSE.has(lowered)) return false;
  throw new ConfigError(
    `${name}=${JSON.stringify(raw)} is not a boolean; use one of ` +
      `${[...TRUE, ...FALSE].sort().join(", ")}`,
  );
}

function readInteger(name: string, fallback: number, minimum = 0): number {
  const raw = env(name);
  if (raw === undefined) return fallback;
  if (!/^[-+]?\d+$/.test(raw)) {
    throw new ConfigError(`${name}=${JSON.stringify(raw)} is not an integer`);
  }
  const value = Number(raw);
  if (value < minimum) throw new ConfigError(`${name}=${value} must be >= ${minimum}`);
  return value;
}

function readList(name: string): string[] {
  const raw = env(name);
  if (!raw) return [];
  return raw.split(",").map((part) => part.trim()).filter(Boolean);
}

/** Best-effort service name, per section 2.1. */
export function deriveServiceName(): string {
  for (const variable of PLATFORM_VARS) {
    const value = env(variable);
    if (value) return value;
  }
  const entry = process.argv[1];
  if (entry) {
    const parent = basename(dirname(resolve(entry)));
    if (parent) return parent;
  }
  return "unknown-service";
}

export interface ConfigInput {
  sinks?: string[];
  enabled?: boolean;
  dryRun?: boolean;
  service?: string;
  environment?: string;
  level?: string;
  dedupeWindow?: number;
  maxPerHour?: number;
  ignore?: string[];
  state?: string;
  redact?: string[];
  timeout?: number;
  resolveAfter?: number;
  stackFrames?: number;
  host?: string;
}

/** A fully resolved configuration. */
export class Config {
  sinks: string[];
  enabled: boolean;
  dryRun: boolean;
  service: string;
  environment: string;
  level: string;
  dedupeWindow: number;
  maxPerHour: number;
  ignore: string[];
  state: string;
  redact: string[];
  timeout: number;
  resolveAfter: number;
  stackFrames: number;
  host: string;

  constructor(input: ConfigInput = {}) {
    this.sinks = input.sinks ?? [];
    this.enabled = input.enabled ?? true;
    this.dryRun = input.dryRun ?? false;
    this.service = input.service ?? "";
    this.environment = input.environment ?? "unknown";
    this.level = (input.level ?? "ERROR").toUpperCase();
    this.dedupeWindow = input.dedupeWindow ?? 300;
    this.maxPerHour = input.maxPerHour ?? 20;
    this.ignore = input.ignore ?? [];
    this.state = input.state ?? "file";
    this.redact = input.redact ?? [];
    this.timeout = input.timeout ?? 5;
    this.resolveAfter = input.resolveAfter ?? 0;
    this.stackFrames = input.stackFrames ?? 12;
    this.host = input.host ?? "";

    if (!(this.level in LEVELS)) {
      throw new ConfigError(
        `BLARE_LEVEL=${JSON.stringify(this.level)} is not a level; ` +
          `use one of ${Object.keys(LEVELS).sort().join(", ")}`,
      );
    }
    if (!this.service) this.service = deriveServiceName();
    if (!this.host) this.host = hostname();
  }

  get levelNumber(): number {
    return LEVELS[this.level] as number;
  }

  /** True when Blare has somewhere to send and has not been switched off. */
  get active(): boolean {
    return this.enabled && this.sinks.length > 0;
  }

  /** Build a config from the environment; `overrides` win. */
  static fromEnv(overrides: ConfigInput = {}): Config {
    const base: ConfigInput = {
      sinks: readList("BLARE_SINKS"),
      enabled: readBoolean("BLARE_ENABLED", true),
      dryRun: readBoolean("BLARE_DRY_RUN", false),
      service: env("BLARE_SERVICE") ?? "",
      environment: env("BLARE_ENV") ?? "unknown",
      level: env("BLARE_LEVEL") ?? "ERROR",
      dedupeWindow: readInteger("BLARE_DEDUPE_WINDOW", 300),
      maxPerHour: readInteger("BLARE_MAX_PER_HOUR", 20),
      ignore: readList("BLARE_IGNORE"),
      state: env("BLARE_STATE") ?? "file",
      redact: readList("BLARE_REDACT"),
      timeout: readInteger("BLARE_TIMEOUT", 5, 1),
      resolveAfter: readInteger("BLARE_RESOLVE_AFTER", 0),
      stackFrames: readInteger("BLARE_STACK_FRAMES", 12, 1),
    };
    for (const [key, value] of Object.entries(overrides)) {
      if (value !== undefined) (base as Record<string, unknown>)[key] = value;
    }
    return new Config(base);
  }
}
