/**
 * The canonical event. SPEC.md section 7.
 *
 * Every sink renders from this structure and the `generic` provider posts it
 * verbatim, which makes it a public interface: fields may be added within spec
 * version 1, never removed or retyped.
 */

export const SPEC_VERSION = "1";
export const SDK_NAME = "blare-node";
export const VERSION = "0.1.0";
export const TITLE_LIMIT = 300;

/** RFC 3339 with millisecond precision, in UTC. */
export function rfc3339(seconds: number): string {
  return new Date(Math.round(seconds * 1000)).toISOString().replace(/(\.\d{3})\d*Z$/, "$1Z");
}

export function buildTitle(typeName: string, message: string): string {
  const tidy = (message ?? "").split(/\s+/).filter(Boolean).join(" ");
  const title = tidy ? `${typeName}: ${tidy}` : typeName;
  return title.slice(0, TITLE_LIMIT);
}

export interface RequestContext {
  method?: string;
  path?: string;
  status?: number;
  route?: string;
}

export interface EventInput {
  fingerprint: string;
  kind: string;
  level: string;
  typeName: string;
  message: string;
  service: string;
  environment: string;
  host: string;
  timestamp: number;
  state?: string;
  logger?: string;
  file?: string;
  function?: string;
  line?: number;
  stack?: string[];
  request?: RequestContext | null;
  extra?: Record<string, unknown>;
  sinceLastAlert?: number;
  total?: number;
  firstSeen?: number;
  windowSeconds?: number;
  rateLimited?: number;
}

export type Payload = Record<string, unknown>;

/** Serialize an event to the section 7 payload. */
export function toPayload(event: EventInput): Payload {
  const context: Record<string, unknown> = { extra: event.extra ?? {} };
  if (event.request) context["request"] = event.request;
  return {
    blare_version: SPEC_VERSION,
    fingerprint: event.fingerprint,
    kind: event.kind,
    state: event.state ?? "new",
    level: event.level.toLowerCase(),
    title: buildTitle(event.typeName, event.message),
    type: event.typeName,
    message: event.message,
    logger: event.logger ?? "",
    service: event.service,
    environment: event.environment,
    host: event.host,
    timestamp: rfc3339(event.timestamp),
    runtime: { language: "node", version: process.versions.node },
    sdk: { name: SDK_NAME, version: VERSION },
    location: {
      file: event.file ?? "",
      function: event.function ?? "",
      line: event.line ?? 0,
    },
    stack: [...(event.stack ?? [])],
    context,
    occurrences: {
      since_last_alert: event.sinceLastAlert ?? 1,
      total: event.total ?? 1,
      first_seen: rfc3339(event.firstSeen || event.timestamp),
      window_seconds: event.windowSeconds ?? 0,
    },
    rate_limited: event.rateLimited ?? 0,
  };
}
