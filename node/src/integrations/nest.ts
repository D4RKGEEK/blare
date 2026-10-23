/**
 * NestJS capture.
 *
 *     app.useGlobalFilters(new BlareExceptionFilter());
 *
 * The filter reports and then rethrows, so Nest's own exception layer still
 * produces the response. Typed structurally, so `@nestjs/common` is not a
 * dependency of this package.
 */

import type { Blare } from "../client.js";
import { requestContext, resolveClient, type RequestLike } from "./shared.js";

interface HttpArgumentsHost {
  getRequest<T = RequestLike>(): T;
  getResponse<T = unknown>(): T;
}
interface ArgumentsHost {
  switchToHttp(): HttpArgumentsHost;
}

export class BlareExceptionFilter {
  private readonly client: Blare | null | undefined;

  constructor(client?: Blare | null) {
    this.client = client;
  }

  catch(exception: unknown, host?: ArgumentsHost): never {
    const target = resolveClient(this.client);
    if (target) {
      let context;
      try {
        const http = host?.switchToHttp();
        const request = http?.getRequest<RequestLike>();
        const status =
          Number((exception as { status?: number })?.status) ||
          Number((http?.getResponse<{ statusCode?: number }>())?.statusCode) || 500;
        if (request) context = requestContext(request, status);
      } catch {
        /* not an HTTP context; report without request detail */
      }
      target.captureException(exception, context ? { request: context } : {});
    }
    // Rethrow: Nest decides the response, not Blare.
    throw exception;
  }
}

export default BlareExceptionFilter;
