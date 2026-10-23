/**
 * Next.js capture (server side only).
 *
 * In `instrumentation.ts`:
 *
 *     import blare from "blare";
 *     import { onRequestError as blareOnRequestError } from "blare/next";
 *
 *     export function register() { blare.init(); }
 *     export const onRequestError = blareOnRequestError;
 *
 * Browser errors are deliberately not covered: a webhook URL in client
 * JavaScript is a public secret that anyone can read and use to flood your
 * channel. Capturing those needs a relay through your own backend.
 */

import type { Blare } from "../client.js";
import { resolveClient } from "./shared.js";
import type { RequestContext } from "../event.js";

interface NextRequestInfo {
  path?: string;
  method?: string;
  headers?: Record<string, string>;
}
interface NextErrorContext {
  routerKind?: string;
  routePath?: string;
  routeType?: string;
}

/** Next's `onRequestError` instrumentation hook. */
export function onRequestError(
  error: unknown,
  request?: NextRequestInfo,
  context?: NextErrorContext,
): void {
  const target = resolveClient();
  if (!target) return;
  const request_: RequestContext = {
    method: request?.method ?? "",
    path: (request?.path ?? "").split("?")[0] ?? "",
    status: 500,
  };
  if (context?.routePath) request_.route = context.routePath;
  target.captureException(error, {
    request: request_,
    extra: context?.routeType ? { routeType: context.routeType } : {},
  });
}

/** Wrap a route handler or server action so its failures are reported. */
export function withBlare<A extends unknown[], R>(
  handler: (...args: A) => Promise<R> | R,
  client?: Blare | null,
): (...args: A) => Promise<R> {
  return async (...args: A): Promise<R> => {
    try {
      return await handler(...args);
    } catch (error) {
      resolveClient(client)?.captureException(error);
      throw error;
    }
  };
}

export default { onRequestError, withBlare };
