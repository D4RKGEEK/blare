"""The capture pipeline end to end, with a recording sink."""

import logging

import pytest

from blare.client import Blare
from blare.config import Config
from helpers import FakeClock, RecordingSink


def make_client(sink=None, clock=None, **overrides):
    overrides.setdefault("state", "memory")
    overrides.setdefault("service", "test-service")
    overrides.setdefault("environment", "test")
    overrides.setdefault("sinks", ["console"])  # marks the config active
    config = Config(**overrides)
    return Blare(
        config,
        sinks=[sink] if sink is not None else [],
        synchronous=True,
        clock=clock or FakeClock(),
    )


def test_an_exception_becomes_an_alert(sink):
    client = make_client(sink)
    try:
        raise ValueError("invalid literal for int()")
    except ValueError as exc:
        client.capture_exception(exc)
    assert len(sink.payloads) == 1
    payload = sink.payloads[0]
    assert payload["type"] == "ValueError"
    assert payload["title"] == "ValueError: invalid literal for int()"
    assert payload["state"] == "new"
    assert payload["kind"] == "exception"
    assert payload["service"] == "test-service"
    assert payload["blare_version"] == "1"


def test_the_location_points_at_application_code(sink):
    client = make_client(sink)
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        client.capture_exception(exc)
    location = sink.payloads[0]["location"]
    assert location["file"].endswith("test_client.py")
    assert location["function"] == "test_the_location_points_at_application_code"
    assert location["line"] > 0


def test_a_qualified_type_name_is_used(sink):
    class CustomError(Exception):
        pass

    client = make_client(sink)
    client.capture_exception(CustomError("nope"))
    assert sink.payloads[0]["type"].endswith("CustomError")
    assert "." in sink.payloads[0]["type"]


def test_identical_failures_send_once_then_report_the_count(sink):
    clock = FakeClock(0)
    client = make_client(sink, clock, dedupe_window=300, max_per_hour=0)

    for _ in range(850):
        client.capture_message("connection pool exhausted", type_name="DBError")
    assert len(sink.payloads) == 1, "a flood must not become a flood of messages"
    assert sink.payloads[0]["occurrences"]["since_last_alert"] == 1

    clock.advance(300)
    client.capture_message("connection pool exhausted", type_name="DBError")
    assert len(sink.payloads) == 2
    second = sink.payloads[1]
    assert second["state"] == "recurring"
    assert second["occurrences"]["since_last_alert"] == 850
    assert second["occurrences"]["total"] == 851


def test_messages_differing_only_in_data_group_together(sink):
    client = make_client(sink, dedupe_window=300, max_per_hour=0)
    client.capture_message("User 4821 not found", type_name="KeyError")
    client.capture_message("User 9173 not found", type_name="KeyError")
    assert len(sink.payloads) == 1


def test_genuinely_different_failures_both_alert(sink):
    client = make_client(sink, dedupe_window=300, max_per_hour=0)
    client.capture_message("pool exhausted", type_name="DBError")
    client.capture_message("disk full", type_name="OSError")
    assert len(sink.payloads) == 2


def test_the_hourly_cap_reports_what_it_dropped(sink):
    clock = FakeClock(0)
    client = make_client(sink, clock, dedupe_window=0, max_per_hour=2)
    for index in range(5):
        client.capture_message(f"failure kind {index}", type_name=f"E{index}")
    assert len(sink.payloads) == 2
    clock.advance(3600)
    client.capture_message("one more", type_name="Elast")
    assert sink.payloads[-1]["rate_limited"] == 3


def test_ignored_types_are_dropped(sink):
    client = make_client(sink, ignore=["KeyboardInterrupt", "*.DoesNotExist"])
    client.capture_exception(KeyboardInterrupt())
    client.capture_message("gone", type_name="app.models.User.DoesNotExist")
    client.capture_message("real", type_name="ValueError")
    assert len(sink.payloads) == 1
    assert sink.payloads[0]["type"] == "ValueError"
    assert client.dropped_by_ignore == 2


def test_secrets_are_redacted_before_delivery(sink):
    client = make_client(sink)
    client.capture_message(
        "auth failed with Bearer abc123def456 for postgres://u:p@db/app",
        type_name="AuthError",
        extra={"password": "hunter2", "user": "ada"},
    )
    payload = sink.payloads[0]
    assert "abc123def456" not in payload["message"]
    assert "Bearer [redacted]" in payload["message"]
    assert "postgres://[redacted]@db/app" in payload["message"]
    assert payload["context"]["extra"]["password"] == "[redacted]"
    assert payload["context"]["extra"]["user"] == "ada"


def test_redaction_does_not_change_grouping(sink):
    """Fingerprints are computed before redaction, per spec section 6."""
    client = make_client(sink, dedupe_window=300, max_per_hour=0)
    client.capture_message("token Bearer aaaa111", type_name="AuthError")
    first = sink.payloads[0]["fingerprint"]

    other = make_client(RecordingSink(), redact=[r"aaaa\d+"])
    other.capture_message("token Bearer aaaa111", type_name="AuthError")
    assert other.sinks[0].payloads[0]["fingerprint"] == first


def test_request_context_is_included(sink):
    client = make_client(sink)
    client.capture_message(
        "boom", type_name="E", request={"method": "POST", "path": "/pay", "status": 500}
    )
    assert sink.payloads[0]["context"]["request"]["path"] == "/pay"


def test_the_stack_is_truncated(sink):
    client = make_client(sink, stack_frames=2)

    def deep(n):
        if n == 0:
            raise RuntimeError("bottom")
        deep(n - 1)

    try:
        deep(8)
    except RuntimeError as exc:
        client.capture_exception(exc)
    assert len(sink.payloads[0]["stack"]) == 2


def test_nothing_is_sent_without_a_sink_configured():
    config = Config(state="memory", sinks=[])
    client = Blare(config, sinks=[], synchronous=True)
    assert client.capture_message("boom", type_name="E") is False


def test_nothing_is_sent_when_disabled(sink):
    client = make_client(sink, enabled=False)
    assert client.capture_message("boom", type_name="E") is False
    assert sink.payloads == []


def test_capture_exception_uses_the_live_exception(sink):
    client = make_client(sink)
    try:
        raise ValueError("implicit")
    except ValueError:
        client.capture_exception()
    assert sink.payloads[0]["message"] == "implicit"


def test_capture_exception_without_an_exception_is_a_no_op(sink):
    client = make_client(sink)
    assert client.capture_exception() is False


def test_a_sink_that_raises_does_not_break_the_caller():
    """Instrumentation failing must never become an application failure."""
    exploding = RecordingSink(raises=True)
    client = make_client(exploding)
    assert client.capture_message("boom", type_name="E") is True
    assert client.stats()["failed"] == 1


def test_recovery_notice_then_the_problem_returns_as_new(sink):
    clock = FakeClock(0)
    client = make_client(
        sink, clock, dedupe_window=300, max_per_hour=0, resolve_after=3600
    )
    client.capture_message("pool exhausted", type_name="DBError")
    clock.advance(4000)
    client.capture_message("something else", type_name="OtherError")
    assert sink.states == ["new", "resolved", "new"]

    clock.advance(1)
    client.capture_message("pool exhausted", type_name="DBError")
    assert sink.states[-1] == "new", "a returning problem is news again"


def test_blare_does_not_capture_its_own_diagnostics(sink):
    client = make_client(sink)
    client.install_logging()
    logging.getLogger("blare").error("delivery failed")
    logging.getLogger("blare.transport").error("delivery failed again")
    assert sink.payloads == []
    client.close()


def test_the_logging_handler_captures_existing_calls(sink):
    client = make_client(sink)
    client.install_logging()
    logging.getLogger("app.payments").error("payment failed")
    assert len(sink.payloads) == 1
    payload = sink.payloads[0]
    assert payload["kind"] == "log"
    assert payload["logger"] == "app.payments"
    assert payload["message"] == "payment failed"
    client.close()


def test_the_logging_handler_prefers_the_exception(sink):
    client = make_client(sink)
    client.install_logging()
    try:
        raise ValueError("underlying cause")
    except ValueError:
        logging.getLogger("app").exception("wrapper message")
    payload = sink.payloads[0]
    assert payload["kind"] == "exception"
    assert payload["type"] == "ValueError"
    client.close()


def test_the_logging_handler_respects_the_level(sink):
    client = make_client(sink, level="ERROR")
    client.install_logging()
    logging.getLogger("app").warning("just a warning")
    assert sink.payloads == []
    logging.getLogger("app").error("a real error")
    assert len(sink.payloads) == 1
    client.close()


def test_warning_level_can_be_opted_into(sink):
    client = make_client(sink, level="WARNING")
    client.install_logging()
    logging.getLogger("app").warning("heads up")
    assert len(sink.payloads) == 1
    client.close()


def test_selftest_reports_each_sink(sink):
    client = make_client(sink)
    results = client.selftest()
    assert results == [("recording://", True)]
    assert sink.payloads[0]["type"] == "blare.SelfTest"


def test_stats_counts_suppression(sink):
    client = make_client(sink, dedupe_window=300, max_per_hour=0)
    for _ in range(5):
        client.capture_message("same", type_name="E")
    stats = client.stats()
    assert stats["delivered"] == 1
    assert stats["suppressed"] == 4


def test_timestamps_are_rfc3339_in_utc(sink):
    client = make_client(sink, clock=FakeClock(1_700_000_000.5))
    client.capture_message("boom", type_name="E")
    assert sink.payloads[0]["timestamp"] == "2023-11-14T22:13:20.500Z"


@pytest.mark.parametrize(
    "field",
    [
        "blare_version",
        "fingerprint",
        "kind",
        "state",
        "level",
        "title",
        "type",
        "message",
        "logger",
        "service",
        "environment",
        "host",
        "timestamp",
        "runtime",
        "sdk",
        "location",
        "stack",
        "context",
        "occurrences",
        "rate_limited",
    ],
)
def test_the_payload_has_every_spec_field(sink, field):
    client = make_client(sink)
    client.capture_message("boom", type_name="E")
    assert field in sink.payloads[0]
