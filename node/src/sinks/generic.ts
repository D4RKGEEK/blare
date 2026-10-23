/**
 * The generic sink: posts the canonical event with no transformation.
 *
 * This is the escape hatch. Anything Blare does not know about (PagerDuty, an
 * internal relay, a Lambda, n8n) receives SPEC.md section 7 verbatim and
 * decides for itself what to do with it.
 */

import { Sink } from "./base.js";

export class GenericSink extends Sink {
  static override readonly provider = "generic";
}
