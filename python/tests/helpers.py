"""Shared test utilities. Importable from test modules and from conftest."""

from __future__ import annotations

import json
import pathlib

CONFORMANCE = pathlib.Path(__file__).resolve().parents[2] / "conformance"


def load_fixture(name: str) -> dict:
    """Read a shared conformance fixture."""
    return json.loads((CONFORMANCE / name).read_text("utf-8"))


def ids(cases: list[dict]) -> list[str]:
    return [case["id"] for case in cases]


class FakeClock:
    """A clock the tests drive, so dedupe windows need no sleeping."""

    def __init__(self, now: float = 1_700_000_000.0) -> None:
        self.now = float(now)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += float(seconds)
        return self.now


class RecordingSink:
    """A sink that keeps payloads instead of sending them."""

    provider = "recording"

    def __init__(self, fail: bool = False, raises: bool = False) -> None:
        self.payloads: list[dict] = []
        self.fail = fail
        self.raises = raises

    def redacted_url(self) -> str:
        return "recording://"

    def send(self, payload: dict) -> bool:
        if self.raises:
            raise RuntimeError("sink exploded")
        self.payloads.append(payload)
        return not self.fail

    @property
    def titles(self) -> list[str]:
        return [p["title"] for p in self.payloads]

    @property
    def states(self) -> list[str]:
        return [p["state"] for p in self.payloads]

    @property
    def counts(self) -> list[int]:
        return [p["occurrences"]["since_last_alert"] for p in self.payloads]
