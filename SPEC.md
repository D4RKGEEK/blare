# Blare Specification v1

This document defines Blare's behaviour independently of any programming language.
Every language port **must** implement this spec and **must** pass the fixtures in
[`conformance/`](conformance/).

If a port disagrees with this document, the document is right and the port is a bug.

- Spec version: `1`
- Status: stable for v0.x; breaking changes bump the spec version and the payload's
  `blare_version` field.

---

## 1. Scope

Blare is a **library**, not a service. It runs inside the host application, in the
host process. It has no server, no database, no dashboard, and no account.

Blare does three things:

1. **Capture** — notice that something failed, without the user writing per-error code.
2. **Decide** — work out whether this failure is worth a notification *right now*.
3. **Deliver** — render the failure for a chat channel and send it over a webhook.

Step 2 is the reason Blare exists. Delivering every failure is easy and useless: a
channel that receives 800 messages gets muted, and a muted channel is worse than no
channel. Everything in §5 exists to keep the channel worth reading.

### Non-goals

- No storage or search of historical errors. Use an error tracker for that.
- No metrics, traces, uptime checks, or dashboards.
- No user-facing product notifications. Blare alerts operators, not customers.
- No capture of request bodies, local variables, or user records by default (§6).

---

## 2. Configuration

Configuration comes from environment variables. Every port reads the **same names**
with the **same defaults**. Ports may also accept the same values as constructor
arguments, which take precedence over the environment.

| Variable | Default | Meaning |
| --- | --- | --- |
| `BLARE_SINKS` | *(none)* | Comma-separated destinations (§3). Empty means Blare is inert. |
| `BLARE_ENABLED` | `true` | `false`/`0`/`no` disables all capture and delivery. |
| `BLARE_DRY_RUN` | `false` | Render alerts and write them to stderr; send nothing. |
| `BLARE_SERVICE` | *(derived)* | Service name shown in alerts. Derived per §2.1. |
| `BLARE_ENV` | `unknown` | Deployment environment, e.g. `production`. |
| `BLARE_LEVEL` | `ERROR` | Minimum log level that may alert. One of `DEBUG` `INFO` `WARNING` `ERROR` `CRITICAL`. |
| `BLARE_DEDUPE_WINDOW` | `300` | Seconds. Per-fingerprint silence after an alert (§5.1). |
| `BLARE_MAX_PER_HOUR` | `20` | Hard cap on alerts delivered per rolling hour (§5.2). `0` means no cap. |
| `BLARE_IGNORE` | *(none)* | Comma-separated glob patterns; matching events are dropped (§5.3). |
| `BLARE_STATE` | `file` | Dedupe state backend: `memory`, `file`, `file:<path>`, or `redis://…` (§5.4). |
| `BLARE_REDACT` | *(none)* | Comma-separated extra regular expressions to redact (§6). |
| `BLARE_TIMEOUT` | `5` | Seconds. Per-request HTTP timeout for delivery. |
| `BLARE_RESOLVE_AFTER` | `0` | Seconds of silence after which a "recovered" notice is sent. `0` disables (§5.5). |
| `BLARE_STACK_FRAMES` | `12` | Maximum stack frames included in an alert. |

Booleans accept `1/0`, `true/false`, `yes/no`, `on/off`, case-insensitively.
An invalid value is a startup error, not a silent fallback — a misconfigured alerting
library that stays quiet is the worst possible failure mode.

### 2.1 Deriving the service name

When `BLARE_SERVICE` is unset, ports derive it from the first of these that yields a
non-empty value, and the order is normative so that the same deployment gets the same
name from every language:

1. A platform-provided service name (`K_SERVICE`, `FLY_APP_NAME`, `RENDER_SERVICE_NAME`,
   `HEROKU_APP_NAME`, `VERCEL_URL`, `WEBSITE_SITE_NAME`).
2. The name of the directory containing the application entry point.
3. The literal `unknown-service`.

---

## 3. Sinks

A sink is **one webhook URL**. Users paste the URL their chat tool gave them; Blare
detects the provider from the URL's host. Nobody should have to learn a URL scheme to
send a message to Slack.

### 3.1 Detection

| Host pattern | Provider |
| --- | --- |
| `hooks.slack.com` | `slack` |
| `discord.com`, `discordapp.com`, `ptb.discord.com`, `canary.discord.com` | `discord` |
| `*.webhook.office.com`, `*.logic.azure.com`, `*.logic.azure.us` | `teams` |
| anything else | `generic` |

Detection may be overridden with a `provider+` prefix on the URL:
`teams+https://corp.example.com/relay`. A prefix naming an unknown provider is a
configuration error.

The pseudo-sink `console` writes rendered alerts to stderr and is used for local
development and tests.

### 3.2 Delivery rules

- Each sink is delivered to independently. One sink failing must not prevent another
  from being tried.
- **Delivery failure must never propagate into the host application.** A broken webhook
  cannot be allowed to break a request or crash a process. Failures are reported through
  the port's own diagnostic channel (§8) and otherwise swallowed.
- Retry at most twice, after 1s and 3s, on a connection error or on HTTP 429/5xx.
  Honour `Retry-After` when present and under 30s. Do not retry other 4xx — they mean
  the URL or payload is wrong, and repeating that wastes the host's time.
- Delivery must not block the thread that raised the error. Ports send from a worker
  thread, goroutine, or equivalent, with a bounded queue. If the queue is full, drop the
  alert and count the drop; back-pressure from a chat webhook must never become
  back-pressure on production traffic.
- On process shutdown, ports should flush the queue with a deadline of
  `BLARE_TIMEOUT` seconds.

### 3.3 Rendering

Each provider renders the canonical event (§7) into its own message format. Rendering is
deliberately not specified byte-for-byte — chat formats change. What is specified is that
every rendering must carry, legibly:

- the title (`type: message`, truncated),
- service and environment,
- the occurrence count when it is greater than 1,
- the code location,
- the short fingerprint,
- and the stack, in whatever collapsed form the provider supports.

The `generic` provider posts the canonical event (§7) as JSON with no transformation.
It is the escape hatch and the integration point for anything not listed above.

---

## 4. Capture

A port must offer capture at three layers, and each layer must work with **no change to
existing application code**.

### 4.1 Log capture

Attach to the language's standard logging mechanism, so that calls the application
already makes become alerts:

```
logger.error("payment failed")      # already alerts, no new code
```

Events at or above `BLARE_LEVEL` are candidates. If the logging call carries an
exception, the exception is used for classification (§4.4); otherwise `kind` is `log`.

Blare's own diagnostics must never re-enter capture. A port must guard against the
infinite loop where Blare logs a delivery failure, that log becomes an event, and
delivering it fails again.

### 4.2 Crash capture

Install the language's last-resort handler for unhandled errors (uncaught exception
hook, panic recovery, unhandled promise rejection) so that a process dying still
produces an alert. Blare must deliver the alert and then **re-raise or re-invoke the
previously installed handler**. Swallowing a crash to send a notification about it is
unacceptable.

### 4.3 Framework capture

Provide middleware or hooks for the ecosystem's common servers and job runners, which
add request context (§7) and catch handler errors that the framework would otherwise
convert into a 500 response without ever raising.

Framework integrations must re-raise. Blare observes; the framework still decides what
the client sees.

### 4.4 Classification

| Condition | `kind` | `type` |
| --- | --- | --- |
| An exception or panic value is available | `exception` | Fully-qualified type name |
| A log record with no exception | `log` | The logger/channel name |

---

## 5. Deciding what to send

### 5.1 Fingerprinting and the dedupe window

Every event is reduced to a **fingerprint** — a stable identifier for "this same
problem" (§5.6). Blare keeps, per fingerprint:

```
first_seen, last_seen, last_sent, count_since_sent, total
```

On each event, in this order:

1. If the event matches `BLARE_IGNORE` (§5.3) → **drop**, record nothing.
2. If this fingerprint has never been sent, or `now - last_sent >= BLARE_DEDUPE_WINDOW`
   → **send**.
3. Otherwise → **suppress**, and increment `count_since_sent`.

A sent alert carries `count_since_sent` as `occurrences.since_last_alert`, so the
suppressed events are not lost — they arrive as a number on the next alert:

> `DatabaseError: connection pool exhausted` — **847 times** in the last 5 minutes

This is why Blare needs no background timer for summaries. The summary *is* the next
alert. A port must not require a running thread to produce correct counts.

`state` in the payload is:

- `new` — never sent before, or previously resolved,
- `recurring` — sent before within the retention horizon,
- `resolved` — a recovery notice (§5.5).

### 5.2 The global cap

Independently of fingerprints, Blare delivers at most `BLARE_MAX_PER_HOUR` alerts per
rolling hour, counted with a token bucket refilling at `BLARE_MAX_PER_HOUR / 3600` per
second and a burst equal to `BLARE_MAX_PER_HOUR`.

When the bucket is empty, alerts are suppressed and counted. The next alert that gets
through reports the number dropped in `rate_limited`. A cap that hides its own existence
would be a lie by omission.

The cap never applies to `resolved` notices, which are rare by construction.

### 5.3 Ignore patterns

Each entry of `BLARE_IGNORE` is a glob (`*` matches any run of characters, `?` any one)
matched case-sensitively against, in turn: the `type`, the `title`, and the
`logger` of the event. A match on any of the three drops the event.

```
BLARE_IGNORE=*.DoesNotExist,KeyboardInterrupt,werkzeug*
```

### 5.4 State backends

| Backend | Behaviour |
| --- | --- |
| `memory` | Per-process. Correct, but every process alerts independently. |
| `file` | Default. A single file, shared by every process on the host, guarded by an exclusive OS file lock. Path defaults to the OS temporary directory, keyed by service name. |
| `redis://…` | Shared across hosts. Required for correct deduplication across replicas. |

`file` is the default because it makes multi-worker servers (Gunicorn, uWSGI, cluster
mode) behave correctly with no extra infrastructure, which is the common case. Ports
must degrade to `memory`, and report through §8, if the configured backend is
unavailable — the application must not fail to start because an alerting library could
not open a file.

State entries are retained for 24 hours after `last_seen` and then pruned.

### 5.5 Recovery notices

When `BLARE_RESOLVE_AFTER` is greater than zero, a fingerprint whose `last_seen` is
older than that many seconds produces one `resolved` notice, after which its state is
cleared, so the problem's return is announced as `new`.

Ports must evaluate this **opportunistically** — while handling any event, and on
flush — and may additionally run a timer. The default is `0` so that the common
installation needs no background thread at all.

### 5.6 The fingerprint

Fingerprinting must be identical in every language; this is the part most likely to
drift, and the conformance fixtures exist mainly to pin it.

```
fingerprint = lowercase_hex(sha256(canonical))[0:16]
canonical   = kind + US + type + US + location + US + normalized_message
US          = U+001F
```

- `kind` — `exception` or `log` (§4.4).
- `type` — the fully-qualified type or logger name, verbatim.
- `location` — `file:function:line` of the **application frame** (§5.7), with `file`
  relative to the application root and using `/` separators. Empty string when no
  frame is available.
- `normalized_message` — the message with the parts that vary between occurrences
  removed (§5.8).

The location deliberately uses one frame, not the whole stack: the same bug reached by
two code paths is one bug.

### 5.7 Choosing the application frame

Walk the stack from the innermost frame outward and take the first frame that is **not**
vendor code. If every frame is vendor code, take the innermost frame.

A frame is vendor code when its file path contains any of these path segments:
`site-packages`, `dist-packages`, `node_modules`, `vendor`, `.venv`, `venv`,
`/usr/lib/python`, `/go/pkg/mod`, `.cargo/registry`, `.gradle/caches`, `.m2/repository`,
or when it belongs to the language's own standard library, or to Blare itself.

This picks out the line in *your* code that caused the failure rather than the line
inside the database driver where it surfaced.

### 5.8 Message normalization

Applied in this exact order. Order matters: a later rule must not re-match the
placeholder left by an earlier one.

| # | Replace | With |
| --- | --- | --- |
| 1 | Quoted runs: `'…'` or `"…"` | `<s>` |
| 2 | Email addresses | `<email>` |
| 3 | URLs (`scheme://…`) | `<url>` |
| 4 | UUIDs (8-4-4-4-12 hex, any case) | `<id>` |
| 5 | Hex runs of 7+ characters containing at least one digit **and** one `a`–`f`, or any `0x`-prefixed run | `<hash>` |
| 6 | Absolute filesystem paths and Windows drive paths | `<path>` |
| 7 | IP addresses (v4, and bracketed v6) | `<ip>` |
| 8 | Integers and decimals, optionally signed | `<n>` |
| 9 | Runs of whitespace | a single space |
| 10 | Leading and trailing whitespace | removed |
| 11 | The result, lowercased and truncated | 200 characters |

Placeholders are never themselves rewritten. Truncation is applied last so that two
long messages differing only past character 200 collapse into one fingerprint.

```
"User 4821 not found in '/srv/app/users.db' (attempt 3)"
  → "user <n> not found in <s> (attempt <n>)"
```

---

## 6. Privacy and redaction

Blare sends failure data to a third-party chat service. It must therefore be
conservative by default, and the burden is on the library, not the user.

**Never collected, in any configuration:** local variable values, request bodies,
response bodies, and environment variable values.

**Collected:** the message, type, stack frames (file, function, line), the request
method, path, and status, plus anything the application explicitly attaches.

Redaction is applied to every string that leaves the process, including the message,
the title, the frame paths, the request path and query, and all explicitly attached
context. Redaction happens **after** fingerprinting, so that redaction can never
destabilise grouping, and **before** rendering, so that no sink can see an unredacted
value.

### 6.1 Key-based redaction

Any mapping key matching one of these, case-insensitively, as a whole word or with any
separator, has its value replaced with `[redacted]`:

```
password  passwd  pwd  secret  token  api_key  apikey  access_key  secret_key
private_key  client_secret  authorization  auth  cookie  set_cookie  session
sessionid  csrf  xsrf  credit_card  card_number  cvv  ssn  otp  passphrase
refresh_token  access_token  id_token  signature  salt  encryption_key
```

### 6.2 Pattern-based redaction

Applied to free text:

| Pattern | Replaced with |
| --- | --- |
| `Bearer <token>` | `Bearer [redacted]` |
| JWTs (`eyJ…` three dot-separated base64url segments) | `[redacted-jwt]` |
| AWS access key ids (`AKIA`/`ASIA` + 16 uppercase alphanumerics) | `[redacted-aws-key]` |
| Slack tokens (`xox[baprs]-…`) | `[redacted-slack-token]` |
| GitHub tokens (`gh[pousr]_` + 36+ characters) | `[redacted-github-token]` |
| Private key PEM blocks | `[redacted-private-key]` |
| Credentials inside URLs (`scheme://user:pass@host`) | `scheme://[redacted]@host` |
| 13–19 digit runs passing a Luhn check | `[redacted-card]` |
| Anything matching a `BLARE_REDACT` expression | `[redacted]` |

A port must apply §6.1 before §6.2, and must apply both to nested structures to a depth
of at least 8.

---

## 7. The canonical event

Every port produces this structure, and every sink renders from it. The `generic`
provider posts it verbatim, so it is a public interface: fields may be added in spec
version 1, but not removed or retyped.

```json
{
  "blare_version": "1",
  "fingerprint": "9f2a41c7b0e3d518",
  "kind": "exception",
  "state": "recurring",
  "level": "error",
  "title": "OperationalError: connection pool exhausted",
  "type": "sqlalchemy.exc.OperationalError",
  "message": "connection pool exhausted",
  "logger": "app.payments",
  "service": "checkout-api",
  "environment": "production",
  "host": "web-3",
  "timestamp": "2026-10-23T14:21:09.481Z",
  "runtime": { "language": "python", "version": "3.12.12" },
  "sdk": { "name": "blare-python", "version": "0.1.0" },
  "location": { "file": "app/payments.py", "function": "charge", "line": 142 },
  "stack": [
    "app/payments.py:142 in charge",
    "app/routes.py:88 in post_pay"
  ],
  "context": {
    "request": { "method": "POST", "path": "/pay", "status": 500 },
    "extra": {}
  },
  "occurrences": {
    "since_last_alert": 847,
    "total": 1203,
    "first_seen": "2026-10-23T13:02:55.100Z",
    "window_seconds": 300
  },
  "rate_limited": 0
}
```

`timestamp` and `occurrences.first_seen` are RFC 3339 with millisecond precision in UTC.
`stack` is ordered innermost frame first and truncated to `BLARE_STACK_FRAMES`.
`rate_limited` is the number of alerts dropped by §5.2 since the last delivered alert.

---

## 8. Diagnostics

Blare must be inspectable without being noisy, because a silent alerting library is
indistinguishable from a broken one.

- Internal messages go to a dedicated logger/channel named `blare`, never to stdout,
  and never through the capture path (§4.1).
- A port must expose a way to assert what *would* be sent, for the host's own tests.
- `BLARE_DRY_RUN=true` renders alerts to stderr and sends nothing.
- Ports should offer a self-test entry point that sends one synthetic alert to every
  configured sink and reports the HTTP outcome, so that "is this wired up?" is
  answerable before an incident rather than during one.

---

## 9. Conformance

A port is conformant when it passes every fixture in [`conformance/`](conformance/):

| Fixture | Pins |
| --- | --- |
| `normalize.json` | §5.8, message normalization, case by case |
| `fingerprint.json` | §5.6, exact fingerprints for known inputs |
| `vendor_frames.json` | §5.7, application-frame selection |
| `dedupe.json` | §5.1 and §5.2, as event timelines with expected decisions |
| `redaction.json` | §6, before and after |
| `sink_detection.json` | §3.1, URL to provider |

Fixtures are plain JSON with no language-specific content, and each is a list of cases
with an `id`, inputs, and expected outputs. A port's test suite is expected to read
these files directly rather than transcribe them, so that a fixture change breaks every
port that has drifted.

---

## 10. Versioning

- This spec is versioned independently of the ports.
- A port declares the spec version it implements in `sdk` and in its README.
- Changes that would alter an existing fingerprint are breaking: they regroup history
  and re-alert resolved problems. They require a spec major version.
