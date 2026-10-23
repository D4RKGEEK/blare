"""The generic sink — posts the canonical event with no transformation.

This is the escape hatch: anything Blare does not know about (PagerDuty, an
internal relay, a Lambda, n8n) receives SPEC.md section 7 verbatim and decides
for itself what to do with it.
"""

from __future__ import annotations

from .base import Sink


class GenericSink(Sink):
    provider = "generic"
