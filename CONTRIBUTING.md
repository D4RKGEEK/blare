# Contributing to Blare

Thanks for looking. The most valuable contributions, roughly in order:

1. **A new language port** — Go, Node/TypeScript, Java, Ruby, PHP, .NET.
2. **A framework integration** for a language that already has a port.
3. **A sharper conformance fixture** — a case the spec is vague about.
4. **A new sink** — though check whether the generic webhook already covers it.

## The one rule

`SPEC.md` is the source of truth, and `conformance/` is how that is enforced.

If a port disagrees with the spec, the port is wrong. If you think the *spec*
is wrong, open an issue about the spec — not a patch to one language — because
the behaviour is what's being argued about, and changing it in one port silently
breaks the promise that a Go service and a Python service group the same failure
the same way.

Changes that would alter an existing fingerprint are **breaking**: they regroup
everyone's history and re-alert problems that were already resolved. Those need
a spec major version.

## Adding a language port

1. Read [`SPEC.md`](SPEC.md) start to finish. It is long on purpose; the parts
   that bite are §5.6 (fingerprinting), §5.7 (frame selection) and §5.8
   (normalization, where rule order is normative).
2. Create a top-level directory named for the language (`go/`, `node/`, …).
3. Implement §2 configuration with the **same variable names and defaults**. A
   polyglot fleet should be describable by one set of environment variables.
4. Make your test suite read the JSON in [`conformance/`](conformance/)
   **directly**. Do not transcribe the cases into your language — the point is
   that a fixture change breaks every port that has drifted.
5. Honour the hard requirements, which are where ports usually go wrong:
   - Capture must need **no application code changes** for logs and crashes.
   - Crash capture **re-raises** or delegates to the previous handler. Never
     swallow a crash in order to report it.
   - Delivery **never** raises into the host, and never blocks the thread that
     raised the error.
   - The queue is **bounded**. Drop and count rather than applying
     back-pressure to production traffic.
   - Redaction happens after fingerprinting and before rendering.
   - The webhook URL is a credential and must never reach a log line.
6. Add your language to the support table in the root `README.md`, and ship a
   README, an example app, and a CI job.

A port is done when the conformance suite passes and someone can install it,
set one environment variable, and get an alert.

## Working on the Python port

```bash
cd python
uv venv && . .venv/bin/activate
uv pip install -e ".[dev]"
pytest          # 200+ tests, under a second
ruff check .
ruff format .
```

See it for real, with no webhook needed:

```bash
BLARE_SINKS=console python examples/plain_script.py
BLARE_SINKS=console uvicorn examples.fastapi_demo:app
```

Tests use a fake clock rather than sleeping, so a five-minute dedupe window
costs nothing to test. There are no network calls in the suite; `urlopen` is
patched where delivery is under test.

## Pull requests

- One concern per PR.
- Every behaviour change touches `SPEC.md` **and** `conformance/` in the same
  PR as the code.
- New behaviour ships with tests. The Python suite runs in under a second;
  there is no excuse not to add to it.
- Say what you *didn't* do. A PR that handles three of four cases and says so
  is much more useful than one that quietly handles three.

## Reporting a security issue

Please do not open a public issue for a vulnerability — especially a redaction
bypass, since that is a live secret-leak path for every user. Use GitHub's
private vulnerability reporting on this repository instead.

## Code of conduct

Be straightforward and kind. Argue about the behaviour, not the person. Project
maintainers will remove comments that don't manage that.
