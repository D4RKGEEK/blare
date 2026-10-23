"""Every port must pass these. The fixtures live in ../../conformance/."""

import pytest

from blare import fingerprint as fp
from blare.decide import Candidate, Decider
from blare.errors import ConfigError
from blare.normalize import normalize_message
from blare.redact import Redactor
from blare.sinks import detect_provider
from helpers import FakeClock, ids, load_fixture

NORMALIZE = load_fixture("normalize.json")["cases"]
VENDOR = load_fixture("vendor_frames.json")["cases"]
SINKS = load_fixture("sink_detection.json")["cases"]
REDACTION = load_fixture("redaction.json")
DEDUPE = load_fixture("dedupe.json")["cases"]


@pytest.mark.parametrize("case", NORMALIZE, ids=ids(NORMALIZE))
def test_normalization(case):
    assert normalize_message(case["in"]) == case["out"]


@pytest.mark.parametrize("case", VENDOR, ids=ids(VENDOR))
def test_application_frame_selection(case):
    assert fp.select_path_index(case["frames"]) == case["expected_index"]


@pytest.mark.parametrize("case", SINKS, ids=ids(SINKS))
def test_sink_detection(case):
    if "error" in case:
        with pytest.raises(ConfigError):
            detect_provider(case["url"])
    else:
        provider, _ = detect_provider(case["url"])
        assert provider == case["provider"]


@pytest.mark.parametrize(
    "case", REDACTION["text_cases"], ids=ids(REDACTION["text_cases"])
)
def test_text_redaction(case):
    assert Redactor().text(case["in"]) == case["out"]


@pytest.mark.parametrize(
    "case", REDACTION["mapping_cases"], ids=ids(REDACTION["mapping_cases"])
)
def test_mapping_redaction(case):
    assert Redactor().value(case["in"]) == case["out"]


@pytest.mark.parametrize("case", DEDUPE, ids=ids(DEDUPE))
def test_dedupe_timelines(case):
    from blare.state import MemoryStore

    config = case["config"]
    clock = FakeClock(0.0)
    decider = Decider(
        MemoryStore(),
        dedupe_window=config.get("dedupe_window", 300),
        max_per_hour=config.get("max_per_hour", 0),
        ignore=config.get("ignore", []),
        resolve_after=config.get("resolve_after", 0),
    )

    sent = []
    for event in case["events"]:
        clock.now = float(event["t"])
        candidate = Candidate(
            fingerprint=event["fp"],
            type_name=event.get("type", ""),
            title=event.get("title", ""),
            logger=event.get("logger", ""),
        )
        outcome = decider.evaluate(candidate, clock.now)
        for fingerprint, notice in outcome.resolved:
            sent.append(
                {
                    "t": clock.now,
                    "fp": fingerprint,
                    "state": notice.state,
                    "since_last_alert": notice.since_last_alert,
                    "total": notice.total,
                    "rate_limited": notice.rate_limited,
                }
            )
        decision = outcome.decision
        if decision is not None and decision.send:
            sent.append(
                {
                    "t": clock.now,
                    "fp": candidate.fingerprint,
                    "state": decision.state,
                    "since_last_alert": decision.since_last_alert,
                    "total": decision.total,
                    "rate_limited": decision.rate_limited,
                }
            )

    expected = case["sends"]
    assert len(sent) == len(expected), (
        f"expected {len(expected)} alerts, got {len(sent)}: {sent}"
    )
    for actual, want in zip(sent, expected):
        assert actual["fp"] == want["fp"]
        assert actual["t"] == want["t"]
        for field in ("state", "since_last_alert", "total", "rate_limited"):
            if field in want:
                assert actual[field] == want[field], (
                    f"{want['fp']} at t={want['t']}: {field} "
                    f"was {actual[field]}, expected {want[field]}"
                )


def test_fingerprint_fixture_matches_implementation():
    """Pins the exact hashes, so a port that drifts fails loudly."""
    cases = load_fixture("fingerprint.json")["cases"]
    assert cases, "fingerprint fixture is empty"
    for case in cases:
        assert (
            fp.compute(case["kind"], case["type"], case["location"], case["message"])
            == case["fingerprint"]
        ), case["id"]
