"""Fingerprinting — SPEC.md sections 5.6 and 5.7.

The fingerprint answers "is this the same problem as last time?". It has to be
identical in every language port, which is what `conformance/fingerprint.json`
exists to guarantee.
"""

from __future__ import annotations

import hashlib
import os
import sysconfig
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from .normalize import normalize_message

UNIT_SEPARATOR = "\x1f"
LENGTH = 16

# Section 5.7. A frame under any of these is somebody else's code, so it is not
# where your bug lives — even though it is usually where the error surfaced.
VENDOR_SEGMENTS = (
    "site-packages",
    "dist-packages",
    "node_modules",
    "vendor",
    ".venv",
    "venv",
    "/usr/lib/python",
    "/go/pkg/mod",
    ".cargo/registry",
    ".gradle/caches",
    ".m2/repository",
)

_STDLIB = sysconfig.get_paths().get("stdlib", "")
_BLARE_DIR = str(Path(__file__).resolve().parent)


@dataclass(frozen=True)
class Location:
    """The application frame a failure is attributed to."""

    file: str = ""
    function: str = ""
    line: int = 0

    def key(self) -> str:
        if not self.file:
            return ""
        return f"{self.file}:{self.function}:{self.line}"


def is_vendor_path(path: str) -> bool:
    """True when ``path`` belongs to a dependency, the stdlib, or Blare."""
    if not path:
        return True
    normalized = path.replace("\\", "/")
    for segment in VENDOR_SEGMENTS:
        needle = segment.replace("\\", "/")
        if needle.startswith("/"):
            if needle in normalized:
                return True
        elif f"/{needle}/" in normalized or normalized.startswith(f"{needle}/"):
            return True
    resolved = os.path.abspath(path)
    if resolved.startswith(_BLARE_DIR):
        return True
    return bool(
        _STDLIB and resolved.startswith(_STDLIB) and "site-packages" not in resolved
    )


def relative_path(path: str, root: str | None = None) -> str:
    """Path relative to the application root, with forward slashes.

    Fingerprints must survive a redeploy to a different absolute directory, so
    the absolute path never enters the hash.
    """
    if not path:
        return ""
    base = Path(root or os.getcwd()).resolve()
    candidate = Path(path)
    try:
        return candidate.resolve().relative_to(base).as_posix()
    except (ValueError, OSError):
        parts = candidate.as_posix().split("/")
        return "/".join(parts[-3:]) if len(parts) > 3 else candidate.as_posix()


def select_frame(summary: traceback.StackSummary) -> traceback.FrameSummary | None:
    """Pick the application frame: innermost non-vendor, else innermost.

    ``summary`` is in Python's native order (outermost first), so it is walked
    in reverse.
    """
    if not summary:
        return None
    for frame in reversed(summary):
        if not is_vendor_path(frame.filename):
            return frame
    return summary[-1]


def select_path_index(paths: list[str]) -> int | None:
    """Index of the application frame in an innermost-first list of paths.

    Mirrors :func:`select_frame` for the language-neutral conformance fixture.
    """
    if not paths:
        return None
    for index, path in enumerate(paths):
        if not is_vendor_path(path):
            return index
    return 0


def location_from_traceback(
    tb: TracebackType | None, root: str | None = None
) -> tuple[Location, list[str]]:
    """Resolve the application frame and a readable stack from a traceback."""
    if tb is None:
        return Location(), []
    summary = traceback.extract_tb(tb)
    frame = select_frame(summary)
    location = Location()
    if frame is not None:
        location = Location(
            file=relative_path(frame.filename, root),
            function=frame.name or "",
            line=frame.lineno or 0,
        )
    stack = [
        f"{relative_path(f.filename, root)}:{f.lineno} in {f.name}"
        for f in reversed(summary)
    ]
    return location, stack


def compute(kind: str, type_name: str, location: str, message: str) -> str:
    """The fingerprint itself — section 5.6."""
    canonical = UNIT_SEPARATOR.join(
        (kind, type_name, location, normalize_message(message))
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:LENGTH]
