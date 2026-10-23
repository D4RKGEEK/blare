"""Blare's own exception types."""

from __future__ import annotations


class BlareError(Exception):
    """Base class for Blare's own errors."""


class ConfigError(BlareError):
    """Raised for an invalid configuration value.

    Deliberately fatal: an alerting library that starts up quietly with a
    misread setting is indistinguishable from one that works, and you find out
    during the incident it was supposed to tell you about.
    """
