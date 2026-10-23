/**
 * Fastify capture.
 *
 *     app.register(blarePlugin);
 *
 * Uses the `onError` hook, which fires for every error Fastify turns into a
 * response, and leaves the reply untouched.
 */

import type { Blare } from "../client.js";
import { requestContext, resolveClient, type RequestLike } from "./shared.js";

interface FastifyLike {
  addHook(name: "onError", handler: (request: RequestLike, reply: unknown,
    error: unknown, done: () => void) => void): void;
}

export function blarePlugin(
  app: FastifyLike,
  options: { client?: Blare | null } = {},
  done?: () => void,
): void {
  app.addHook("onError", (request, reply, error, next) => {
    const target = resolveClient(options.client);
    if (target) {
      const status = Number((reply as { statusCode?: number })?.statusCode) || 500;
      target.captureException(error, { request: requestContext(request, status) });
    }
    next();
  });
  done?.();
}

// Fastify reads this to skip its encapsulation wrapper, so the hook applies
// to the whole application rather than only to this plugin's scope.
Object.defineProperty(blarePlugin, Symbol.for("skip-override"), { value: true });

export default blarePlugin;
