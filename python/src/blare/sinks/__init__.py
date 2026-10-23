"""Sink registry — SPEC.md section 3."""

from __future__ import annotations

from ..errors import ConfigError
from .base import PROVIDERS, Sink, detect_provider
from .console import ConsoleSink
from .discord import DiscordSink
from .generic import GenericSink
from .slack import SlackSink
from .teams import TeamsSink

PROVIDERS.update(
    {
        "slack": SlackSink,
        "discord": DiscordSink,
        "teams": TeamsSink,
        "generic": GenericSink,
        "console": ConsoleSink,
    }
)


def build_sink(spec: str, timeout: int = 5) -> Sink:
    """Create the sink for one ``BLARE_SINKS`` entry."""
    provider, url = detect_provider(spec)
    sink_class = PROVIDERS.get(provider)
    if sink_class is None:  # pragma: no cover - guarded by detect_provider
        raise ConfigError(f"unknown provider {provider!r}")
    return sink_class(url, timeout=timeout)


def build_sinks(specs: list[str], timeout: int = 5) -> list[Sink]:
    return [build_sink(spec, timeout=timeout) for spec in specs]


__all__ = [
    "PROVIDERS",
    "ConsoleSink",
    "DiscordSink",
    "GenericSink",
    "Sink",
    "SlackSink",
    "TeamsSink",
    "build_sink",
    "build_sinks",
    "detect_provider",
]
