/**
 * An Express service wired to blare, runnable with no webhook at all.
 *
 *   cd node && npm run build
 *   BLARE_SINKS=console BLARE_ENV=demo node examples/express-demo.mjs
 *
 * Then watch the terminal while you hit the endpoints:
 *
 *   curl localhost:3000/boom          # one alert
 *   for i in $(seq 50); do curl -s localhost:3000/boom; done   # still one alert
 *   curl localhost:3000/boom-other    # a different problem, so a new alert
 *   curl localhost:3000/leak          # shows redaction
 *
 * Point BLARE_SINKS at a real Slack or Discord webhook to see it in a channel.
 * Needs express: npm install express
 */

import express from "express";
import blare from "../dist/esm/index.js";
import { blareErrorHandler } from "../dist/esm/integrations/express.js";

// One call. Everything below is ordinary application code with no blare in it.
blare.init({ service: "demo-api" });

const app = express();

app.get("/", (_req, res) => {
  res.json({ try: ["/boom", "/boom-other", "/leak", "/flood"], stats: blare.stats() });
});

app.get("/boom", () => {
  // An unhandled throw. Hit it fifty times: you get one alert.
  const users = { ada: 1 };
  if (!users.grace) throw new Error("no such user: grace");
});

app.get("/boom-other", () => {
  throw new RangeError("payment provider unreachable");
});

app.get("/leak", () => {
  // Secrets in the message are stripped before anything is sent.
  throw new Error("upstream rejected Bearer abc123def456ghi789 for " +
    "postgres://admin:s3cr3t@db.internal:5432/app");
});

app.get("/flood", (_req, res) => {
  for (let i = 0; i < 100; i += 1) {
    blare.captureMessage(`queue worker ${i} died`, { typeName: "WorkerError" });
  }
  res.json({ reported: 100, stats: blare.stats() });
});

// Register after the routes, as Express requires for error middleware.
app.use(blareErrorHandler());

app.listen(3000, () => process.stdout.write("listening on http://localhost:3000\n"));
