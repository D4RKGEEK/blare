<img src="https://raw.githubusercontent.com/D4RKGEEK/blare/main/docs/assets/blare-logo.png" alt="blare" width="240">

# blare for Node

> Published as **`blare-node`**. npm's typosquatting filter refuses `blare`
> (too close to `base`, `brace`, `slate`) and `blarejs` (too close to
> `blakejs`), and the `@blare` scope belongs to someone else. It is the same
> project as `blare` on PyPI, and both pass the same conformance fixtures.

Production failures to Slack, Discord and Teams. One line of setup, no server,
no spam.

```bash
npm install blare-node
```

```js
import blare from "blare-node";
blare.init();
```

```bash
BLARE_SINKS=https://hooks.slack.com/services/T000/B000/xxxx
BLARE_ENV=production
```

That is the whole installation. Every unhandled exception, every rejected
promise and every framework 500 becomes a chat alert, grouped so that one
broken endpoint is one message rather than eight hundred.

Check it before you need it:

```bash
npx blare-node --send
```

## What is captured

| Layer | How | Code to write |
| --- | --- | --- |
| Unhandled exceptions, rejected promises | process hooks | none |
| **pino** | a destination stream | one line |
| **winston** | a transport | one line |
| Express | error middleware | one line |
| Fastify | `onError` hook | one line |
| NestJS | exception filter | one line |
| Next.js (server) | `onRequestError` | one line |

```js
// Express — after your routes, as Express requires
import { blareErrorHandler } from "blare-node/express";
app.use(blareErrorHandler());

// Fastify
import { blarePlugin } from "blare-node/fastify";
app.register(blarePlugin);

// NestJS
import { BlareExceptionFilter } from "blare-node/nest";
app.useGlobalFilters(new BlareExceptionFilter());

// Next.js — in instrumentation.ts
import blare from "blare-node";
export { onRequestError } from "blare-node/next";
export function register() { blare.init(); }
```

Node has no standard logger, so the equivalent of "attach to the root logger"
is a stream your logger already writes to:

```js
// pino — your existing log.error(...) calls become alerts
import pino from "pino";
import { blarePinoStream } from "blare-node/pino";
const log = pino({ level: "info" }, pino.multistream([
  { stream: process.stdout },
  { stream: blarePinoStream() },
]));

// winston
import { blareWinstonTransport } from "blare-node/winston";
const log = winston.createLogger({
  transports: [new winston.transports.Console(), blareWinstonTransport()],
});
```

## Why it does not flood the channel

Identical failures are fingerprinted together and one alert per problem goes
out per five minute window. The suppressed occurrences are not lost: they
arrive as a count on the next alert.

> 🟠 `OperationalError: connection pool exhausted` — **847 times in the last 5 min**

There is also a hard ceiling of 20 alerts an hour, and the number dropped by it
is reported on the next alert that gets through.

Crucially, this is the *same* grouping as every other blare port. A Node
service and a Python service in one fleet produce the same fingerprint for the
same failure, because both are tested against the same
[conformance fixtures](https://github.com/D4RKGEEK/blare/tree/main/conformance).

## Settings

Every setting is an environment variable, documented in
[SPEC.md section 2](https://github.com/D4RKGEEK/blare/blob/main/SPEC.md#2-configuration).
The ones most people touch:

| Variable | Default | |
| --- | --- | --- |
| `BLARE_SINKS` | — | webhook URLs, comma separated |
| `BLARE_ENV` | `unknown` | `production`, `staging`, … |
| `BLARE_SERVICE` | derived | name shown in alerts |
| `BLARE_LEVEL` | `ERROR` | minimum level that alerts |
| `BLARE_DEDUPE_WINDOW` | `300` | seconds of silence per problem |
| `BLARE_MAX_PER_HOUR` | `20` | hard ceiling; `0` disables |
| `BLARE_IGNORE` | — | glob patterns to drop |
| `BLARE_STATE` | `file` | `memory` or `file` |

## Privacy

Local variables, request bodies, response bodies, query strings and
environment variable values are never collected, in any configuration.
Everything that does leave the process is scanned for credentials first:
bearer tokens, JWTs, AWS keys, GitHub and Slack tokens, private keys, URL
passwords and card numbers. Keys named `password`, `token`, `secret` and
friends are replaced wholesale. See
[SPEC.md section 6](https://github.com/D4RKGEEK/blare/blob/main/SPEC.md#6-privacy-and-redaction).

## Testing your own code

```js
blare.init({ sinkObjects: [], synchronous: true });  // captures, sends nowhere
blare.stats();                                       // { delivered, suppressed, … }
```

Or set `BLARE_DRY_RUN=true` to render alerts to stderr and send nothing.

## Differences from the Python port

Both pass the same conformance fixtures, so grouping, throttling, redaction and
the payload are identical. Three things differ because Node does:

- **No standard logger**, so log capture is pino and winston rather than one
  built-in handler.
- **No `flock` in the standard library.** The shared file lock is an exclusive
  create with a stale timeout, and a contended wait gives up after ~180ms and
  proceeds, which can at worst duplicate an alert. Set `BLARE_STATE=memory` if
  a single process is the whole deployment.
- **No Redis backend yet.** `BLARE_STATE=redis://…` falls back to the shared
  file and says so.

## Requirements

Node 18.17+ (it uses the built-in `fetch`). Ships ESM and CommonJS with types.
**No runtime dependencies.**

Apache-2.0. Implements spec version 1.
