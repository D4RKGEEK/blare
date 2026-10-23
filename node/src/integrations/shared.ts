/**
 * Pieces shared by the framework integrations.
 *
 * Every integration is typed structurally rather than against the framework's
 * own types, so `blare` needs no peer dependencies and adding one framework
 * never drags in another.
 */

import type { Blare } from "../client.js";
import { getClient } from "../index.js";
import type { RequestContext } from "../event.js";

export function resolveClient(explicit?: Blare | null): Blare | null {
  return explicit ?? getClient();
}

export interface RequestLike {
  method?: string;
  url?: string;
  originalUrl?: string;
  path?: string;
  route?: { path?: string };
  routeOptions?: { url?: string };
  routerPath?: string;
}

/**
 * The request fields section 6 permits: method, path, status, route.
 *
 * The query string, headers and body are deliberately left out. They are where
 * tokens and personal data live, and this payload is going to a chat room.
 */
export function requestContext(request: RequestLike, status = 500): RequestContext {
  const raw = request.path ?? request.originalUrl ?? request.url ?? "";
  // Strip the query string: section 6 forbids sending it.
  const path = raw.split("?")[0] ?? "";
  const context: RequestContext = { method: request.method ?? "", path, status };
  // The templated route ("/users/:id") rather than the concrete path, so one
  // broken endpoint is one alert instead of one per user id.
  const route = request.route?.path ?? request.routeOptions?.url ?? request.routerPath;
  if (route) context.route = route;
  return context;
}
