"""Message normalization — SPEC.md section 5.8.

Strips the parts of a message that vary between occurrences of the same bug, so
that "User 4821 not found" and "User 9173 not found" fingerprint identically.

The rule order here is normative. A later rule must never re-match a placeholder
left by an earlier one, which is why quoted strings go first and numbers last.
"""

from __future__ import annotations

import re

MAX_LENGTH = 200

_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL = re.compile(r"\b[A-Za-z][A-Za-z0-9+.\-]*://\S+")
_UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
)
_HEX_PREFIXED = re.compile(r"\b0x[0-9a-f]+\b", re.I)
# A hex run only counts as an identifier when it mixes digits and a-f letters;
# requiring both keeps English words like "effaced" out of the placeholder.
_HEX_RUN = re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{7,}\b", re.I)
_WIN_PATH = re.compile(r"[A-Za-z]:\\[^\s'\"]+")
_UNIX_PATH = re.compile(r"/[A-Za-z0-9._\-]+(?:/[A-Za-z0-9._\-]+)+")
_IPV6 = re.compile(r"\[[0-9a-f]*:[0-9a-f:]*\]", re.I)
_IPV4 = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")
_WHITESPACE = re.compile(r"\s+")


def normalize_message(message: str) -> str:
    """Reduce ``message`` to its invariant shape."""
    if not message:
        return ""
    text = message
    text = _QUOTED.sub("<s>", text)
    text = _EMAIL.sub("<email>", text)
    text = _URL.sub("<url>", text)
    text = _UUID.sub("<id>", text)
    text = _HEX_PREFIXED.sub("<hash>", text)
    text = _HEX_RUN.sub("<hash>", text)
    text = _WIN_PATH.sub("<path>", text)
    text = _UNIX_PATH.sub("<path>", text)
    text = _IPV6.sub("<ip>", text)
    text = _IPV4.sub("<ip>", text)
    text = _NUMBER.sub("<n>", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text.lower()[:MAX_LENGTH]
