"""Configuration — SPEC.md section 2.

Every port reads the same variable names with the same defaults, so one set of
deployment settings describes a polyglot fleet.
"""

from __future__ import annotations

import os
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigError

LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}

# Section 2.1 — order is normative so that one deployment gets one name
# regardless of which language the service is written in.
_PLATFORM_VARS = (
    "K_SERVICE",
    "FLY_APP_NAME",
    "RENDER_SERVICE_NAME",
    "HEROKU_APP_NAME",
    "VERCEL_URL",
    "WEBSITE_SITE_NAME",
)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    lowered = raw.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise ConfigError(
        f"{name}={raw!r} is not a boolean; use one of {sorted(_TRUE | _FALSE)}"
    )


def _int(name: str, default: int, minimum: int = 0) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name}={raw!r} is not an integer") from None
    if value < minimum:
        raise ConfigError(f"{name}={value} must be >= {minimum}")
    return value


def _csv(name: str) -> list[str]:
    raw = _env(name)
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def derive_service_name() -> str:
    """Best-effort service name, per section 2.1."""
    for var in _PLATFORM_VARS:
        value = _env(var)
        if value:
            return value
    entry = sys.argv[0] if sys.argv and sys.argv[0] else ""
    if entry:
        parent = Path(entry).resolve().parent.name
        if parent:
            return parent
    return "unknown-service"


@dataclass
class Config:
    """A fully resolved configuration. See SPEC.md section 2."""

    sinks: list[str] = field(default_factory=list)
    enabled: bool = True
    dry_run: bool = False
    service: str = ""
    environment: str = "unknown"
    level: str = "ERROR"
    dedupe_window: int = 300
    max_per_hour: int = 20
    ignore: list[str] = field(default_factory=list)
    state: str = "file"
    redact: list[str] = field(default_factory=list)
    timeout: int = 5
    resolve_after: int = 0
    stack_frames: int = 12
    host: str = ""

    def __post_init__(self) -> None:
        self.level = self.level.upper()
        if self.level not in LEVELS:
            raise ConfigError(
                f"BLARE_LEVEL={self.level!r} is not a level; use one of {sorted(LEVELS)}"
            )
        if not self.service:
            self.service = derive_service_name()
        if not self.host:
            self.host = socket.gethostname()

    @property
    def level_number(self) -> int:
        return LEVELS[self.level]

    @property
    def active(self) -> bool:
        """True when Blare has somewhere to send and has not been switched off."""
        return self.enabled and bool(self.sinks)

    @classmethod
    def from_env(cls, **overrides: object) -> Config:
        """Build a config from the environment; ``overrides`` win."""
        config = cls(
            sinks=_csv("BLARE_SINKS"),
            enabled=_bool("BLARE_ENABLED", True),
            dry_run=_bool("BLARE_DRY_RUN", False),
            service=_env("BLARE_SERVICE", "") or "",
            environment=_env("BLARE_ENV", "unknown") or "unknown",
            level=_env("BLARE_LEVEL", "ERROR") or "ERROR",
            dedupe_window=_int("BLARE_DEDUPE_WINDOW", 300),
            max_per_hour=_int("BLARE_MAX_PER_HOUR", 20),
            ignore=_csv("BLARE_IGNORE"),
            state=_env("BLARE_STATE", "file") or "file",
            redact=_csv("BLARE_REDACT"),
            timeout=_int("BLARE_TIMEOUT", 5, minimum=1),
            resolve_after=_int("BLARE_RESOLVE_AFTER", 0),
            stack_frames=_int("BLARE_STACK_FRAMES", 12, minimum=1),
        )
        for key, value in overrides.items():
            if value is None:
                continue
            if not hasattr(config, key):
                raise ConfigError(f"unknown setting {key!r}")
            setattr(config, key, value)
        config.__post_init__()
        return config
