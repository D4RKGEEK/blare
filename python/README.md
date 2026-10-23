# blare (Python)

Production failures to Slack, Discord and Teams. One line of setup, no server,
no spam.

```bash
pip install blare
```

```python
import blare

blare.init()
```

```bash
BLARE_SINKS=https://hooks.slack.com/services/T000/B000/xxxx
BLARE_ENV=production
```

That is the whole installation. From then on every `logger.error(...)`, every
unhandled exception and every framework 500 becomes a chat alert — grouped so
that one broken endpoint is one message rather than eight hundred.

Check it before you need it:

```bash
python -m blare --send
```

## What is captured

| Layer | How | Code to write |
| --- | --- | --- |
| `logging` | handler on the root logger | none |
| Unhandled exceptions | `sys.excepthook`, `threading.excepthook` | none |
| FastAPI, Starlette, Litestar, Quart | `BlareASGIMiddleware` | one line |
| Flask | `got_request_exception` | one line |
| Django | `got_request_exception` | one line |
| Celery | `task_failure` | one line |
| Any WSGI app | `BlareWSGIMiddleware` | one line |

```python
# FastAPI
from blare.integrations.asgi import BlareASGIMiddleware

app.add_middleware(BlareASGIMiddleware)

# Flask
from blare.integrations.flask import install

install(app)

# Django, in AppConfig.ready()
from blare.integrations.django import install

install()

# Celery
from blare.integrations.celery import install

install()
```

## Why it does not flood the channel

Identical failures are fingerprinted together and one alert per problem goes
out per five minute window. The suppressed occurrences are not lost — they
arrive as a count on the next alert:

> 🟠 `OperationalError: connection pool exhausted` — **847 times in the last 5 min**

There is also a hard ceiling of 20 alerts an hour, and the number dropped by it
is reported on the next alert that gets through.

## Settings

Every setting is an environment variable, documented in
[SPEC.md section 2](https://github.com/D4RKGEEK/blare/blob/main/SPEC.md#2-configuration). The ones most people touch:

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

Running more than one host? Set `BLARE_STATE` to a Redis URL, or each host
deduplicates on its own and a ten-replica deployment sends ten alerts for one
outage.

## Privacy

Local variables, request bodies, response bodies and environment variable
values are never collected, in any configuration. Everything that does leave
the process is scanned for credentials first — bearer tokens, JWTs, AWS keys,
GitHub and Slack tokens, private keys, URL passwords, card numbers — and keys
named `password`, `token`, `secret` and friends are replaced wholesale. See
[SPEC.md section 6](https://github.com/D4RKGEEK/blare/blob/main/SPEC.md#6-privacy-and-redaction).

## Testing your own code

```python
blare.init(sinks=[], synchronous=True)  # captures, sends nowhere
blare.stats()  # {'delivered': .., 'suppressed': ..}
```

Or set `BLARE_DRY_RUN=true` to render alerts to stderr and send nothing.

## Development

```bash
uv venv && . .venv/bin/activate
uv pip install -e ".[dev]"
pytest
ruff check .
```

The suite reads the shared fixtures in [`../conformance/`](https://github.com/D4RKGEEK/blare/tree/main/conformance), so
behaviour cannot drift from the spec or from the other language ports.

Apache-2.0. Implements spec version 1.
