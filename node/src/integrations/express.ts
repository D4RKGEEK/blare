/**
 * Express capture.
 *
 * Register it *after* your routes, as Express requires for error middleware:
 *
 *     app.use(blareErrorHandler());
 *
 * It reports and then calls `next(error)`, so Express still decides what the
 * client sees. Blare observes; it never handles.
 */

import type { Blare } from "../client.js";
import { requestContext, resolveClient, type RequestLike } from "./shared.js";

type Next = (error?: unknown) => void;

export function blareErrorHandler(client?: Blare | null) {
  return function blareError(error: unknown, request: RequestLike, response: unknown, next: Next) {
    const target = resolveClient(client);
    if (target) {
      const status = Number((response as { statusCode?: number })?.statusCode) || 500;
      target.captureException(error, {
        request: requestContext(request, status >= 400 ? status : 500),
      });
    }
    next(error);
  };
}

export default blareErrorHandler;
