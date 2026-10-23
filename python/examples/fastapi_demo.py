"""A FastAPI service wired to Blare, runnable with no webhook at all.

    cd python
    BLARE_SINKS=console BLARE_ENV=demo uvicorn examples.fastapi_demo:app

Then watch the terminal while you hit the endpoints:

    curl localhost:8000/boom          # one alert
    repeat 50 curl -s localhost:8000/boom   # still one alert
    curl localhost:8000/boom-other    # a different problem, so a new alert
    curl "localhost:8000/leak"        # shows redaction

Point BLARE_SINKS at a real Slack or Discord webhook to see it in a channel.
"""

import logging

from fastapi import FastAPI

import blare
from blare.integrations.asgi import BlareASGIMiddleware

logging.basicConfig(level=logging.INFO)

# One call. Everything below is ordinary application code with no Blare in it.
blare.init(service="demo-api")

app = FastAPI()
app.add_middleware(BlareASGIMiddleware)

log = logging.getLogger("demo")


@app.get("/")
def index():
    return {
        "try": ["/boom", "/boom-other", "/log-error", "/leak", "/flood"],
        "stats": blare.stats(),
    }


@app.get("/boom")
def boom():
    """An unhandled exception. Hit it fifty times: you get one alert."""
    users = {"ada": 1}
    return users["grace"]


@app.get("/boom-other")
def boom_other():
    """A genuinely different failure, so a genuinely separate alert."""
    raise RuntimeError("payment provider unreachable")


@app.get("/log-error")
def log_error():
    """No exception, just the logging call the app already had."""
    log.error("nightly reconciliation did not run")
    return {"logged": True}


@app.get("/leak")
def leak():
    """Secrets in the message and the context are stripped before sending."""
    log.error(
        "upstream rejected Bearer abc123def456ghi789 "
        "for postgres://admin:s3cr3t@db.internal:5432/app",
        extra={"password": "hunter2"},
    )
    return {"logged": True}


@app.get("/flood")
def flood():
    """A hundred identical failures, deliberately."""
    for index in range(100):
        log.error("queue worker %d died", index)
    return {"logged": 100, "stats": blare.stats()}
