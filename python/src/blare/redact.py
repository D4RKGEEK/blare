"""Redaction — SPEC.md section 6.

Blare posts failure data into a chat room, so the library carries the burden of
not leaking secrets rather than trusting each caller to remember. Redaction runs
after fingerprinting (so it can never destabilise grouping) and before rendering
(so no sink ever sees a raw value).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

PLACEHOLDER = "[redacted]"
MAX_DEPTH = 8

# Section 6.1. Compared against keys with separators and case removed, so
# "api_key", "api-key" and "apiKey" all collapse onto "apikey".
SECRET_KEYS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "apikey",
        "accesskey",
        "secretkey",
        "privatekey",
        "clientsecret",
        "authorization",
        "auth",
        "cookie",
        "setcookie",
        "session",
        "sessionid",
        "csrf",
        "xsrf",
        "creditcard",
        "cardnumber",
        "cvv",
        "ssn",
        "otp",
        "passphrase",
        "refreshtoken",
        "accesstoken",
        "idtoken",
        "signature",
        "salt",
        "encryptionkey",
    }
)

_NON_ALNUM = re.compile(r"[^a-z0-9]")

_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.S,
)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_BEARER = re.compile(r"\b(Bearer)\s+[A-Za-z0-9._~+/=-]+", re.I)
_AWS_KEY = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
_SLACK_TOKEN = re.compile(r"\bxox[baprs]-[A-Za-z0-9-]+")
_GITHUB_TOKEN = re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")
_URL_CREDENTIALS = re.compile(r"\b([A-Za-z][A-Za-z0-9+.\-]*://)[^\s:/@]+:[^\s/@]+@")
_DIGIT_RUN = re.compile(r"\b\d{13,19}\b")


def _normalize_key(key: str) -> str:
    return _NON_ALNUM.sub("", str(key).lower())


def _luhn(digits: str) -> bool:
    total, alternate = 0, False
    for char in reversed(digits):
        value = ord(char) - 48
        if alternate:
            value *= 2
            if value > 9:
                value -= 9
        total += value
        alternate = not alternate
    return total % 10 == 0


class Redactor:
    """Applies section 6 to text and to nested structures."""

    def __init__(self, extra_patterns: Iterable[str] = ()) -> None:
        self._extra = [re.compile(p) for p in extra_patterns if p]

    def text(self, value: str) -> str:
        if not value:
            return value
        out = _PRIVATE_KEY.sub("[redacted-private-key]", value)
        out = _JWT.sub("[redacted-jwt]", out)
        out = _BEARER.sub(lambda m: f"{m.group(1)} {PLACEHOLDER}", out)
        out = _AWS_KEY.sub("[redacted-aws-key]", out)
        out = _SLACK_TOKEN.sub("[redacted-slack-token]", out)
        out = _GITHUB_TOKEN.sub("[redacted-github-token]", out)
        out = _URL_CREDENTIALS.sub(lambda m: f"{m.group(1)}{PLACEHOLDER}@", out)
        out = _DIGIT_RUN.sub(
            lambda m: "[redacted-card]" if _luhn(m.group(0)) else m.group(0), out
        )
        for pattern in self._extra:
            out = pattern.sub(PLACEHOLDER, out)
        return out

    def value(self, value: Any, _depth: int = 0) -> Any:
        """Redact a structure: secret keys by name, every string by pattern."""
        if _depth > MAX_DEPTH:
            return value
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                if _normalize_key(key) in SECRET_KEYS:
                    out[key] = PLACEHOLDER
                else:
                    out[key] = self.value(item, _depth + 1)
            return out
        if isinstance(value, (list, tuple)):
            return [self.value(item, _depth + 1) for item in value]
        return value
