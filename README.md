<div align="center">

<img src="https://raw.githubusercontent.com/D4RKGEEK/blare/main/docs/assets/blare-logo.png" alt="blare" width="280">

**Production failures, in the channel you already watch.**

One line of setup. No server, no dashboard, no account — and no 3 a.m. flood of
eight hundred identical messages.

[![CI](https://github.com/D4RKGEEK/blare/actions/workflows/ci.yml/badge.svg)](https://github.com/D4RKGEEK/blare/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/blare?color=306998)](https://pypi.org/project/blare/)
[![Spec](https://img.shields.io/badge/spec-v1-black)](SPEC.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

[Quickstart](#quickstart) · [What it captures](#what-it-captures) ·
[Why it won't spam you](#why-it-wont-spam-you) · [Specification](SPEC.md) ·
[Docs](https://d4rkgeek.github.io/blare/)

</div>

---

```python
import blare
blare.init()
```

```bash
BLARE_SINKS=https://hooks.slack.com/services/T000/B000/xxxx
```

That's the installation. Every `logger.error(...)` you already write, every
unhandled exception, and every framework 500 now arrives in Slack — grouped,
rate limited, and with credentials stripped out.

<div align="center">

> 🟠 **OperationalError: connection pool exhausted**
> `checkout-api · production` — **847 times in the last 5 min**
> `app/payments.py:142 in charge`

</div>

One message. Not 847.

## Why this exists

Most teams end up writing this twice: a logging handler that posts to a Slack
webhook, and then, a week later, the throttling that stops it drowning the
channel. The first half is a weekend. The second half is the part everybody
skips, and it's why that channel is muted today.

The tools that exist handle one half each:

| | What it does | What's missing |
| --- | --- | --- |
| **Apprise, Shoutrrr** | Send a message to 100+ services | Doesn't capture anything — you write the glue |
| **Sentry, GlitchTip, Bugsink** | Capture errors properly | You run a server, a database and a dashboard |
| **`express-error-slack` and friends** | Glue, for one framework and one channel | One language, no grouping, mostly unmaintained |

Blare is the missing middle: **capture + grouping + delivery, as a library.**
It is not an error tracker and does not try to be. There is no history, no
search and no UI — if you want those, run Sentry or Bugsink and let Blare stay
out of it.

## Quickstart

```bash
pip install blare
```

```python
import blare
blare.init()
```

```bash
# .env
BLARE_SINKS=https://hooks.slack.com/services/T000/B000/xxxx
BLARE_ENV=production
```

Confirm it's wired up before you need it:

```bash
python -m blare --send
```

Paste the webhook URL your chat tool gave you and Blare works out the rest —
there is no URL scheme to learn. Several, comma separated, all get a copy.

## What it captures

Everything in the first group needs **no code changes at all**:

| Layer | Hook | Python |
| --- | --- | --- |
| Standard logging | handler on the root logger | ✅ |
| Unhandled exceptions | `sys.excepthook`, thread hook | ✅ |
| **Framework errors** | | |
| FastAPI / Starlette / Litestar / Quart | ASGI middleware | ✅ |
| Flask | `got_request_exception` | ✅ |
| Django | `got_request_exception` | ✅ |
| Celery | `task_failure` | ✅ |
| Any WSGI app | WSGI middleware | ✅ |

## Where it sends

| Destination | Format | Status |
| --- | --- | --- |
| **Slack** | Block Kit | ✅ |
| **Discord** | embeds | ✅ |
| **Microsoft Teams** | Adaptive Card *and* legacy MessageCard, chosen by URL | ✅ |
| **Any webhook** | the canonical event as JSON | ✅ |
| Console | stderr, for local development | ✅ |

The generic sink posts [the canonical event](SPEC.md#7-the-canonical-event)
unchanged, so PagerDuty, n8n, a Lambda or your own relay all work today
without Blare knowing about them.

## Language support

Blare is specified first and implemented per language. [`SPEC.md`](SPEC.md)
defines fingerprinting, throttling, redaction and the payload exactly, and
[`conformance/`](conformance/) holds the shared fixtures **every** port must
pass — so a Go service and a Python service in the same fleet group the same
failure under the same fingerprint.

| Language | Status | Frameworks |
| --- | --- | --- |
| **Python** | ✅ **v0.1** | logging, FastAPI, Flask, Django, Celery, WSGI |
| **Go** | 🔜 next | `log/slog`, `net/http`, Gin, Echo, Fiber |
| **Node / TypeScript** | 📋 planned | Express, NestJS, Fastify, Next.js (server) |
| **Java / Kotlin** | 📋 planned | SLF4J/Logback, Spring Boot |
| **Ruby** | 📋 planned | Rails, Sidekiq |
| **PHP** | 📋 planned | Laravel, Symfony |
| **.NET** | 📋 planned | ASP.NET Core |
| Browser / React | 🔬 researching | needs a relay — see [below](#what-blare-does-not-do) |

Adding a port means implementing the spec and passing the fixtures.
[Contributions welcome](CONTRIBUTING.md) — the fixtures mean you never have to
guess what "correct" is.

## Why it won't spam you

This is the part that matters, and the reason Blare is not a fifty-line
snippet.

**1. Identical failures are grouped.** Each failure is reduced to a
fingerprint built from its type, the line in *your* code that caused it, and
the message with the variable parts stripped out. `User 4821 not found` and
`User 9173 not found` are one problem.

**2. One alert per problem per window.** Default five minutes. The suppressed
occurrences aren't lost — they ride along as a count on the next alert, so
there's no background timer and no second "summary" message.

**3. A hard ceiling.** At most 20 alerts an hour, whatever happens. The number
dropped by the ceiling is reported on the next alert that gets through, so the
limit can't hide a cascade from you.

**4. Blame the right line.** The frame chosen for both the fingerprint and the
alert is the innermost one that *isn't* in `site-packages`, `node_modules` or
`vendor` — the line in your code, not the line inside the database driver where
it surfaced.

**5. It works across workers.** Dedupe state lives in a lock-guarded file
shared by every process on the host, so four Gunicorn workers seeing one crash
send one alert. Running multiple hosts? Point `BLARE_STATE` at Redis.

## Privacy

Blare posts into a chat room, so it is conservative by default and the library
carries that burden, not you.

**Never collected, in any configuration:** local variables, request bodies,
response bodies, environment variable values.

**Scrubbed from everything that does leave:** bearer tokens, JWTs, AWS keys,
GitHub and Slack tokens, PEM private keys, passwords inside connection strings,
and card numbers that pass a Luhn check. Keys named `password`, `token`,
`secret`, `authorization`, `cookie` and [two dozen
more](SPEC.md#61-key-based-redaction) are replaced wholesale, at any nesting
depth.

Redaction runs *after* fingerprinting, so changing a redaction rule can never
regroup your history, and *before* rendering, so no sink ever sees a raw value.

## Configuration

All environment variables, [fully documented in the
spec](SPEC.md#2-configuration). The ones people actually touch:

| Variable | Default | |
| --- | --- | --- |
| `BLARE_SINKS` | — | webhook URLs, comma separated |
| `BLARE_ENV` | `unknown` | `production`, `staging`, … |
| `BLARE_SERVICE` | derived | name shown in alerts |
| `BLARE_LEVEL` | `ERROR` | minimum level that alerts |
| `BLARE_DEDUPE_WINDOW` | `300` | seconds of silence per problem |
| `BLARE_MAX_PER_HOUR` | `20` | hard ceiling; `0` disables |
| `BLARE_IGNORE` | — | glob patterns to drop |
| `BLARE_STATE` | `file` | `memory`, `file`, `redis://…` |
| `BLARE_DRY_RUN` | `false` | render to stderr, send nothing |
| `BLARE_ENABLED` | `true` | the off switch |

## What Blare does not do

Being clear about this up front, because the gaps are deliberate:

- **No history, search or dashboard.** It is a library. Use an error tracker if
  you need to look things up later.
- **No metrics, traces or uptime checks.** Not an observability platform.
- **No product notifications.** It alerts operators, not your users.
- **No browser support yet.** A webhook URL in frontend JavaScript is a public
  secret — anyone can read it and spam your channel. Browser capture needs a
  relay through your own backend, and that's a different shape of product; it
  comes after the server-side ports.

## Project layout

```
SPEC.md          the normative behaviour spec — the source of truth
conformance/     shared JSON fixtures every language port must pass
python/          the Python implementation (reference port)
docs/            the documentation site
```

## Contributing

New ports, new sinks and sharper fixtures are all welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md). If you think Blare makes a wrong call,
open an issue against [`SPEC.md`](SPEC.md) rather than one port: the behaviour
is the thing being argued about.

## License

[Apache-2.0](LICENSE).
