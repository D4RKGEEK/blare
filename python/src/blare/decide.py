"""The decision engine — SPEC.md sections 5.1 to 5.5.

This module is the reason Blare exists. Capturing errors is easy and delivering
them is easy; deciding which of 10,000 identical failures deserves a message is
the part that keeps a channel readable, and therefore keeps it unmuted.

Nothing here does I/O, and the clock is injected, so the whole policy is
testable against `conformance/dedupe.json` without sleeping.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any

from .state import Store

NEW = "new"
RECURRING = "recurring"
RESOLVED = "resolved"


@dataclass(frozen=True)
class Candidate:
    """What the decision engine needs to know about an event."""

    fingerprint: str
    type_name: str = ""
    title: str = ""
    logger: str = ""


@dataclass
class Decision:
    """The verdict for one candidate."""

    send: bool
    state: str = RECURRING
    since_last_alert: int = 0
    total: int = 0
    first_seen: float = 0.0
    rate_limited: int = 0
    reason: str = ""


@dataclass
class Outcome:
    """A candidate's verdict, plus any recovery notices it flushed out."""

    decision: Decision | None
    resolved: list[tuple[str, Decision]] = field(default_factory=list)


class Decider:
    """Applies the ignore list, the dedupe window, and the hourly cap."""

    def __init__(
        self,
        store: Store,
        *,
        dedupe_window: int = 300,
        max_per_hour: int = 20,
        ignore: Iterable[str] = (),
        resolve_after: int = 0,
    ) -> None:
        self._store = store
        self._window = max(0, dedupe_window)
        self._cap = max(0, max_per_hour)
        self._ignore = list(ignore)
        self._resolve_after = max(0, resolve_after)

    # -- public API ------------------------------------------------------

    def ignored(self, candidate: Candidate) -> bool:
        """Section 5.3 — glob match against type, title, then logger."""
        if not self._ignore:
            return False
        subjects = (candidate.type_name, candidate.title, candidate.logger)
        return any(
            fnmatchcase(subject, pattern)
            for pattern in self._ignore
            for subject in subjects
            if subject
        )

    def evaluate(self, candidate: Candidate, now: float) -> Outcome:
        """Decide what to do with ``candidate`` and advance the stored state."""
        if self.ignored(candidate):
            # Dropped events leave no trace at all, so an ignored exception
            # cannot inflate the count of anything else.
            return Outcome(decision=None)

        with self._store.transaction() as document:
            resolved = self._collect_resolved(document, now)
            decision = self._evaluate_one(document, candidate, now)
            Store.prune(document, now)
        return Outcome(decision=decision, resolved=resolved)

    def flush_resolved(self, now: float) -> list[tuple[str, Decision]]:
        """Emit recovery notices without an event to hang them off."""
        if not self._resolve_after:
            return []
        with self._store.transaction() as document:
            resolved = self._collect_resolved(document, now)
            Store.prune(document, now)
        return resolved

    # -- internals -------------------------------------------------------

    def _evaluate_one(
        self, document: dict[str, Any], candidate: Candidate, now: float
    ) -> Decision:
        groups = document["groups"]
        group = groups.get(candidate.fingerprint)
        if group is None:
            group = {
                "first_seen": now,
                "last_seen": now,
                "last_sent": 0.0,
                "count_since_sent": 0,
                "total": 0,
                "ever_sent": False,
            }
            groups[candidate.fingerprint] = group

        group["last_seen"] = now
        group["total"] = int(group["total"]) + 1
        group["count_since_sent"] = int(group["count_since_sent"]) + 1

        never_sent = not group["ever_sent"]
        window_open = never_sent or (now - float(group["last_sent"]) >= self._window)
        if not window_open:
            return Decision(
                send=False,
                state=RECURRING,
                since_last_alert=int(group["count_since_sent"]),
                total=int(group["total"]),
                first_seen=float(group["first_seen"]),
                reason="within dedupe window",
            )

        # The window is open, but the hourly cap gets the last word. When it
        # refuses, the group keeps accumulating: the suppressed occurrences are
        # reported on whichever alert eventually gets through.
        if not self._take_token(document, now):
            document["suppressed_by_cap"] = int(document["suppressed_by_cap"]) + 1
            return Decision(
                send=False,
                state=RECURRING,
                since_last_alert=int(group["count_since_sent"]),
                total=int(group["total"]),
                first_seen=float(group["first_seen"]),
                reason="hourly cap reached",
            )

        decision = Decision(
            send=True,
            state=NEW if never_sent else RECURRING,
            since_last_alert=int(group["count_since_sent"]),
            total=int(group["total"]),
            first_seen=float(group["first_seen"]),
            rate_limited=int(document["suppressed_by_cap"]),
        )
        group["count_since_sent"] = 0
        group["last_sent"] = now
        group["ever_sent"] = True
        document["suppressed_by_cap"] = 0
        return decision

    def _collect_resolved(
        self, document: dict[str, Any], now: float
    ) -> list[tuple[str, Decision]]:
        """Section 5.5 — announce problems that have stopped happening."""
        if not self._resolve_after:
            return []
        notices: list[tuple[str, Decision]] = []
        groups = document["groups"]
        for fingerprint in list(groups):
            group = groups[fingerprint]
            if not group.get("ever_sent"):
                continue
            if now - float(group.get("last_seen", 0)) < self._resolve_after:
                continue
            notices.append(
                (
                    fingerprint,
                    Decision(
                        send=True,
                        state=RESOLVED,
                        since_last_alert=0,
                        total=int(group.get("total", 0)),
                        first_seen=float(group.get("first_seen", 0)),
                    ),
                )
            )
            # Clearing the group means a return of this problem is announced as
            # new, which is what an operator expects after a recovery notice.
            del groups[fingerprint]
        return notices

    def _take_token(self, document: dict[str, Any], now: float) -> bool:
        """Token bucket for section 5.2. ``cap == 0`` disables the limit."""
        if not self._cap:
            return True
        bucket = document.get("bucket") or {}
        tokens = float(bucket.get("tokens", self._cap))
        updated_at = float(bucket.get("ts", now))
        rate = self._cap / 3600.0
        tokens = min(float(self._cap), tokens + max(0.0, now - updated_at) * rate)
        if tokens < 1.0:
            document["bucket"] = {"tokens": tokens, "ts": now}
            return False
        document["bucket"] = {"tokens": tokens - 1.0, "ts": now}
        return True
