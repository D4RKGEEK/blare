"""Sink detection, rendering and the delivery retry policy."""

import json
import urllib.error

import pytest

from blare.errors import ConfigError
from blare.event import Event
from blare.redact import Redactor
from blare.sinks import (
    ConsoleSink,
    DiscordSink,
    GenericSink,
    SlackSink,
    TeamsSink,
    build_sink,
    build_sinks,
)


@pytest.fixture
def payload():
    event = Event(
        fingerprint="9f2a41c7b0e3d518",
        kind="exception",
        level="error",
        type_name="sqlalchemy.exc.OperationalError",
        message="connection pool exhausted",
        service="checkout-api",
        environment="production",
        host="web-3",
        timestamp=1_700_000_000.0,
        state="recurring",
        logger="app.payments",
        file="app/payments.py",
        function="charge",
        line=142,
        stack=["app/payments.py:142 in charge", "app/routes.py:88 in post_pay"],
        request={"method": "POST", "path": "/pay", "status": 500},
        since_last_alert=847,
        total=1203,
        first_seen=1_699_999_000.0,
        window_seconds=300,
    )
    return Redactor().value(event.to_dict())


def test_build_sink_picks_the_provider():
    assert isinstance(build_sink("https://hooks.slack.com/services/T/B/x"), SlackSink)
    assert isinstance(build_sink("https://discord.com/api/webhooks/1/x"), DiscordSink)
    assert isinstance(build_sink("https://acme.webhook.office.com/x"), TeamsSink)
    assert isinstance(build_sink("https://alerts.internal/x"), GenericSink)
    assert isinstance(build_sink("console"), ConsoleSink)


def test_build_sinks_builds_several():
    sinks = build_sinks(["console", "https://hooks.slack.com/services/T/B/x"])
    assert [type(s).__name__ for s in sinks] == ["ConsoleSink", "SlackSink"]


def test_an_unknown_prefix_is_rejected():
    with pytest.raises(ConfigError, match="unknown provider"):
        build_sink("carrierpigeon+https://acme.dev/hook")


def test_a_non_http_url_is_rejected():
    with pytest.raises(ConfigError, match="unsupported scheme"):
        build_sink("ftp://acme.dev/hook")


def test_the_webhook_url_never_reaches_a_log():
    """The URL is the credential, so the secret path must not be loggable."""
    sink = build_sink("https://hooks.slack.com/services/T000/B000/sUpErSeCrEt")
    assert "sUpErSeCrEt" not in sink.redacted_url()
    assert "sUpErSeCrEt" not in repr(sink)
    assert "hooks.slack.com" in sink.redacted_url()


def test_slack_rendering(payload):
    body = SlackSink("https://hooks.slack.com/services/T/B/x").render(payload)
    assert "checkout-api" in body["text"]
    blocks = json.dumps(body["blocks"])
    assert "847 times in the last 5 min" in blocks
    assert "app/payments.py:142 in charge" in blocks
    assert "POST" in blocks and "/pay" in blocks
    assert "9f2a41c7b0e3d518" in blocks
    # The fallback text must stand alone for notifications and screen readers.
    assert "OperationalError" in body["text"]


def test_slack_header_stays_within_the_api_limit(payload):
    payload["title"] = "E: " + "x" * 500
    body = SlackSink("https://hooks.slack.com/services/T/B/x").render(payload)
    assert len(body["blocks"][0]["text"]["text"]) <= 150


def test_discord_rendering(payload):
    body = DiscordSink("https://discord.com/api/webhooks/1/x").render(payload)
    embed = body["embeds"][0]
    assert "OperationalError" in embed["title"]
    assert isinstance(embed["color"], int)
    rendered = json.dumps(embed["fields"])
    assert "847 times" in rendered
    assert "app/payments.py:142" in rendered


def test_discord_fields_stay_within_the_api_limit(payload):
    payload["stack"] = [f"app/f{i}.py:{i} in handler" for i in range(200)]
    body = DiscordSink("https://discord.com/api/webhooks/1/x").render(payload)
    for field in body["embeds"][0]["fields"]:
        assert len(field["value"]) <= 1024


def test_teams_uses_an_adaptive_card_for_workflow_urls(payload):
    sink = TeamsSink("https://prod-1.westus.logic.azure.com/workflows/x")
    assert sink.uses_adaptive_card is True
    body = sink.render(payload)
    assert body["type"] == "message"
    content = body["attachments"][0]["content"]
    assert content["type"] == "AdaptiveCard"
    assert json.dumps(content["body"]).count("847 times") == 1


def test_teams_uses_a_message_card_for_legacy_connectors(payload):
    """The two Teams webhook shapes are not interchangeable: the wrong one is
    accepted and then silently displays nothing."""
    sink = TeamsSink("https://acme.webhook.office.com/webhookb2/x")
    assert sink.uses_adaptive_card is False
    body = sink.render(payload)
    assert body["@type"] == "MessageCard"
    assert "847 times" in json.dumps(body["sections"])


def test_generic_posts_the_canonical_event_verbatim(payload):
    assert GenericSink("https://alerts.internal/x").render(payload) == payload


def test_console_rendering_is_readable(payload, capsys):
    sink = ConsoleSink()
    assert sink.send(payload) is True
    err = capsys.readouterr().err
    assert "checkout-api/production" in err
    assert "847 times" in err
    assert "9f2a41c7b0e3d518" in err


def test_resolved_alerts_read_as_recovery(payload):
    payload["state"] = "resolved"
    body = SlackSink("https://hooks.slack.com/services/T/B/x").render(payload)
    assert "Recovered" in json.dumps(body["blocks"])
    assert "🟢" in body["text"]


def test_rate_limit_note_is_surfaced(payload):
    payload["rate_limited"] = 12
    body = SlackSink("https://hooks.slack.com/services/T/B/x").render(payload)
    assert "12 alerts dropped" in json.dumps(body["blocks"])


# -- delivery --------------------------------------------------------------


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_a_successful_post_reports_success(monkeypatch, payload):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append((request.full_url, json.loads(request.data), timeout))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    sink = GenericSink("https://alerts.internal/x", timeout=3)
    assert sink.send(payload) is True
    url, body, timeout = calls[0]
    assert url == "https://alerts.internal/x"
    assert body["fingerprint"] == "9f2a41c7b0e3d518"
    assert timeout == 3


def test_a_client_error_is_not_retried(monkeypatch, payload):
    """A 400 means the payload or URL is wrong; repeating it wastes time."""
    attempts = []

    def fake_urlopen(request, timeout=None):
        attempts.append(1)
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert GenericSink("https://alerts.internal/x").send(payload) is False
    assert len(attempts) == 1


def test_a_server_error_is_retried(monkeypatch, payload):
    attempts = []

    def fake_urlopen(request, timeout=None):
        attempts.append(1)
        raise urllib.error.HTTPError(request.full_url, 503, "Unavailable", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda _: None)
    assert GenericSink("https://alerts.internal/x").send(payload) is False
    assert len(attempts) == 3


def test_a_retry_eventually_succeeds(monkeypatch, payload):
    attempts = []

    def fake_urlopen(request, timeout=None):
        attempts.append(1)
        if len(attempts) == 1:
            raise urllib.error.URLError("connection reset")
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda _: None)
    assert GenericSink("https://alerts.internal/x").send(payload) is True
    assert len(attempts) == 2


def test_retry_after_is_honoured(monkeypatch, payload):
    delays = []

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 429, "Too Many", {"Retry-After": "2"}, None
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda seconds: delays.append(seconds))
    GenericSink("https://alerts.internal/x").send(payload)
    assert delays[0] == 2.0


def test_an_absurd_retry_after_is_ignored(monkeypatch, payload):
    """A webhook asking us to sleep for an hour does not get to."""
    delays = []

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 429, "Too Many", {"Retry-After": "3600"}, None
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda seconds: delays.append(seconds))
    GenericSink("https://alerts.internal/x").send(payload)
    assert max(delays) <= 3.0


def test_delivery_never_raises(monkeypatch, payload):
    def fake_urlopen(request, timeout=None):
        raise RuntimeError("something nobody anticipated")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert GenericSink("https://alerts.internal/x").send(payload) is False
