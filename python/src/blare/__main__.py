"""``python -m blare`` — check a configuration without writing any code.

Prints the resolved settings and offers to send one test alert, so "is this
wired up?" is answerable before an incident rather than during one.
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import Blare, __version__
from .config import Config
from .errors import ConfigError
from .sinks import detect_provider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m blare",
        description="Inspect and test a Blare configuration.",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="send one test alert to every configured sink",
    )
    parser.add_argument("--version", action="version", version=f"blare {__version__}")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    print(f"blare {__version__} (spec 1)")
    print(f"  service      {config.service}")
    print(f"  environment  {config.environment}")
    print(f"  level        {config.level}")
    print(
        f"  dedupe       {config.dedupe_window}s window, "
        f"max {config.max_per_hour or 'unlimited'}/hour"
    )
    print(f"  state        {config.state}")
    print(f"  resolve      {config.resolve_after or 'off'}")
    if config.ignore:
        print(f"  ignoring     {', '.join(config.ignore)}")

    if not config.sinks:
        print("\nNo sinks configured. Set BLARE_SINKS to your webhook URL.")
        return 1

    print("  sinks")
    for spec in config.sinks:
        try:
            provider, url = detect_provider(spec)
        except ConfigError as exc:
            print(f"    ! {exc}")
            return 2
        host = url.split("://", 1)[-1].split("/", 1)[0] if "://" in url else url
        print(f"    - {provider:<8} {host}")

    if not config.enabled:
        print("\nBLARE_ENABLED is false, so nothing would be sent.")
        return 0

    if not args.send:
        print("\nRun with --send to deliver one test alert.")
        return 0

    client = Blare(config, synchronous=True)
    print("\nsending test alert...")
    failures = 0
    for target, ok in client.selftest():
        print(f"  {'ok  ' if ok else 'FAIL'} {target}")
        failures += 0 if ok else 1
    client.close()
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
