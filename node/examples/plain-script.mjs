/**
 * The smallest possible installation: a script that crashes.
 *
 *   cd node && npm run build
 *   BLARE_SINKS=console node examples/plain-script.mjs
 */

import blare from "../dist/esm/index.js";

blare.init({ service: "nightly-job" });

function charge(orderId) {
  throw new Error(`order ${orderId} has no payment method`);
}

// Nothing catches this. blare alerts, then the process dies as it would have
// without blare installed.
charge(4821);
