"""Celery capture.

A failed background job produces no HTTP 500 and nobody is watching a worker
log, so a task failure is exactly the kind of silent failure Blare exists for.
"""

from __future__ import annotations

from typing import Any

_receiver: Any = None


def install(client: Any = None) -> None:
    """Attach Blare to Celery::

    from blare.integrations.celery import install
    install()
    """
    global _receiver
    from celery.signals import task_failure

    def handler(
        sender: Any = None,
        task_id: str | None = None,
        exception: BaseException | None = None,
        **_: Any,
    ) -> None:
        target = client
        if target is None:
            from .. import get_client

            target = get_client()
        if target is None or exception is None:
            return
        task_name = getattr(sender, "name", "") or ""
        # The task id is deliberately not in the fingerprint path: every run has
        # a different one, and grouping by it would defeat deduplication.
        target.capture_exception(
            exception,
            logger=f"celery.{task_name}" if task_name else "celery",
            extra={"task": task_name},
        )

    _receiver = handler
    task_failure.connect(handler, weak=False)
