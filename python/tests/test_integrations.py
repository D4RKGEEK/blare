"""Framework integrations: request context in, exception back out."""

import logging

import pytest

from blare.client import Blare
from blare.config import Config
from blare.integrations.asgi import BlareASGIMiddleware, request_context
from blare.integrations.wsgi import BlareWSGIMiddleware
from helpers import FakeClock, RecordingSink


def make_client(sink, **overrides):
    overrides.setdefault("state", "memory")
    overrides.setdefault("sinks", ["console"])
    return Blare(Config(**overrides), sinks=[sink], synchronous=True, clock=FakeClock())


# -- ASGI ------------------------------------------------------------------


async def test_asgi_captures_and_reraises():
    sink = RecordingSink()
    client = make_client(sink)

    async def app(scope, receive, send):
        raise ValueError("handler blew up")

    wrapped = BlareASGIMiddleware(app, client=client)
    scope = {"type": "http", "method": "POST", "path": "/pay"}

    with pytest.raises(ValueError, match="handler blew up"):
        await wrapped(scope, None, None)

    assert len(sink.payloads) == 1
    request = sink.payloads[0]["context"]["request"]
    assert request == {"method": "POST", "path": "/pay", "status": 500}


async def test_asgi_passes_successful_requests_through():
    sink = RecordingSink()
    client = make_client(sink)
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["path"])

    await BlareASGIMiddleware(app, client=client)(
        {"type": "http", "method": "GET", "path": "/health"}, None, None
    )
    assert seen == ["/health"]
    assert sink.payloads == []


async def test_asgi_ignores_non_http_scopes():
    sink = RecordingSink()
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    await BlareASGIMiddleware(app, client=make_client(sink))(
        {"type": "lifespan"}, None, None
    )
    assert seen == ["lifespan"]


def test_the_templated_route_is_preferred_over_the_concrete_path():
    """One broken endpoint should be one alert, not one per user id."""

    class Route:
        path_format = "/users/{user_id}"

    context = request_context(
        {"method": "GET", "path": "/users/4821", "route": Route()}, 500
    )
    assert context["route"] == "/users/{user_id}"


# -- WSGI ------------------------------------------------------------------


def test_wsgi_captures_and_reraises():
    sink = RecordingSink()
    client = make_client(sink)

    def app(environ, start_response):
        raise RuntimeError("wsgi blew up")

    wrapped = BlareWSGIMiddleware(app, client=client)
    with pytest.raises(RuntimeError):
        wrapped({"REQUEST_METHOD": "GET", "PATH_INFO": "/x"}, lambda *a: None)
    assert sink.payloads[0]["context"]["request"]["path"] == "/x"


# -- FastAPI ---------------------------------------------------------------


def test_fastapi_end_to_end():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    sink = RecordingSink()
    client = make_client(sink)

    app = fastapi.FastAPI()
    app.add_middleware(BlareASGIMiddleware, client=client)

    @app.get("/boom")
    def boom():
        raise ValueError("fastapi route failed")

    @app.get("/fine")
    def fine():
        return {"ok": True}

    with TestClient(app, raise_server_exceptions=False) as http:
        assert http.get("/fine").status_code == 200
        assert http.get("/boom").status_code == 500

    assert len(sink.payloads) == 1
    payload = sink.payloads[0]
    assert payload["type"] == "ValueError"
    assert payload["message"] == "fastapi route failed"
    assert payload["context"]["request"]["path"] == "/boom"
    assert payload["location"]["function"] == "boom"


def test_fastapi_floods_are_grouped():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    sink = RecordingSink()
    client = make_client(sink, dedupe_window=300, max_per_hour=0)

    app = fastapi.FastAPI()
    app.add_middleware(BlareASGIMiddleware, client=client)

    @app.get("/pay")
    def pay():
        raise RuntimeError("payment provider unreachable")

    with TestClient(app, raise_server_exceptions=False) as http:
        for _ in range(50):
            http.get("/pay")

    assert len(sink.payloads) == 1, "50 identical 500s is one problem"


# -- Flask -----------------------------------------------------------------


def test_flask_end_to_end():
    flask = pytest.importorskip("flask")
    from blare.integrations.flask import install

    sink = RecordingSink()
    client = make_client(sink)

    app = flask.Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    install(app, client=client)

    @app.get("/boom")
    def boom():
        raise ValueError("flask route failed")

    with app.test_client() as http:
        assert http.get("/boom").status_code == 500

    assert len(sink.payloads) == 1
    payload = sink.payloads[0]
    assert payload["type"] == "ValueError"
    assert payload["context"]["request"] == {
        "method": "GET",
        "path": "/boom",
        "status": 500,
    }


def test_flask_signal_receiver_survives_garbage_collection():
    """Blinker holds receivers weakly; a local function would stop alerting."""
    import gc

    flask = pytest.importorskip("flask")
    from blare.integrations.flask import install

    sink = RecordingSink()
    client = make_client(sink)
    app = flask.Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    install(app, client=client)

    @app.get("/boom")
    def boom():
        raise ValueError("still captured")

    gc.collect()
    with app.test_client() as http:
        http.get("/boom")
    assert len(sink.payloads) == 1


# -- crash capture ---------------------------------------------------------


def test_the_excepthook_alerts_then_delegates():
    """Swallowing a crash to report it would be worse than the crash."""
    import sys

    sink = RecordingSink()
    client = make_client(sink)
    original = sys.excepthook
    delegated = []
    sys.excepthook = lambda *args: delegated.append(args)
    try:
        client.install_excepthook()
        try:
            raise RuntimeError("process died")
        except RuntimeError as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)
    finally:
        sys.excepthook = original

    assert len(sink.payloads) == 1
    assert sink.payloads[0]["level"] == "critical"
    assert len(delegated) == 1, "the previous hook must still run"


def test_keyboard_interrupt_is_not_an_alert():
    import sys

    sink = RecordingSink()
    client = make_client(sink)
    original = sys.excepthook
    sys.excepthook = lambda *args: None
    try:
        client.install_excepthook()
        exc = KeyboardInterrupt()
        sys.excepthook(KeyboardInterrupt, exc, None)
    finally:
        sys.excepthook = original
    assert sink.payloads == []


# -- Celery ----------------------------------------------------------------


def test_celery_task_failure_is_captured():
    pytest.importorskip("celery")
    from celery.signals import task_failure

    from blare.integrations.celery import install

    sink = RecordingSink()
    client = make_client(sink)
    install(client=client)

    class Sender:
        name = "app.tasks.send_invoice"

    task_failure.send(sender=Sender(), task_id="abc", exception=ValueError("job failed"))
    assert len(sink.payloads) == 1
    assert sink.payloads[0]["logger"] == "celery.app.tasks.send_invoice"
    assert sink.payloads[0]["context"]["extra"]["task"] == "app.tasks.send_invoice"


# -- public API ------------------------------------------------------------


def test_the_module_level_api_is_inert_before_init():
    import blare

    blare.close()
    assert blare.capture_message("boom") is False
    assert blare.capture_exception(ValueError("x")) is False
    assert blare.stats() == {}
    assert blare.flush() is True


def test_init_installs_both_hooks(monkeypatch):
    import blare

    sink = RecordingSink()
    monkeypatch.setenv("BLARE_SINKS", "console")
    monkeypatch.setenv("BLARE_STATE", "memory")
    client = blare.init(sinks=[sink], synchronous=True)
    try:
        logging.getLogger("app").error("captured with no extra code")
        assert len(sink.payloads) == 1
        assert blare.get_client() is client
    finally:
        blare.close()


def test_init_twice_replaces_the_previous_client(monkeypatch):
    import blare

    monkeypatch.setenv("BLARE_SINKS", "console")
    monkeypatch.setenv("BLARE_STATE", "memory")
    first = RecordingSink()
    second = RecordingSink()
    blare.init(sinks=[first], synchronous=True)
    blare.init(sinks=[second], synchronous=True)
    try:
        logging.getLogger("app").error("only the second client is live")
        assert first.payloads == []
        assert len(second.payloads) == 1
    finally:
        blare.close()


def test_selftest_without_init_is_an_error():
    import blare

    blare.close()
    with pytest.raises(blare.BlareError, match="init"):
        blare.selftest()
