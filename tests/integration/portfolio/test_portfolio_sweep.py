"""S7-05 AC-25..AC-32 — serial portfolio sweep integration test.

Runs ``codegenie gather`` against every fixture under
``tests/fixtures/portfolio/`` serially and asserts:

- AC-26 — every gather exits 0; stderr is the project's structured-JSON
  log stream (one ``{"event": ..., ...}`` per line) and contains no
  ``cli.unhandled`` events; the final ``cli.end`` carries
  ``outcome == "ok"``.
- AC-27 — the resulting ``repo-context.yaml`` validates against the
  Phase-2 envelope schema (``src/codegenie/schema/repo_context.schema.json``)
  via the project's ``codegenie.parsers.safe_yaml`` chokepoint.
- AC-28 — ``scripts/regen_golden.py --check --portfolio`` returns 0
  against the canonical fixture tree (delegates the byte-level diff to
  S7-03's harness).
- AC-29 — total wall-clock ≤ 360 s (the Phase-2 ``portfolio`` job budget).
- AC-30 — serial dispatch only (``@pytest.mark.serial``; for-loop
  iteration; no xdist / no asyncio.gather). ADR-0009 honored.
- AC-31 — each fixture is copied to a fresh ``tmp_path`` via
  ``shutil.copytree``; the canonical fixture tree is not mutated
  (``_dir_sha256`` snapshot pinned across the sweep).
- AC-32 — per-fixture wall-clock is recorded in memory and written to
  ``$CODEGENIE_PORTFOLIO_WALLTIME_OUT`` only when the env var is set;
  otherwise the table is printed under ``pytest -s``.

Story-deviation note (AC-25 / AC-28): the AC text names
``codegenie.exec.run_allowlisted`` for spawning the gather. ``python``
is not in ``ALLOWED_BINARIES`` (per ``codegenie.exec.ALLOWED_BINARIES``
— a deliberate Phase-0 invariant), and ``codegenie`` is not a
standalone binary either. The pragmatic substitute used here is the
``subprocess.run([sys.executable, "-m", "codegenie", ...])`` shape
already established in ``tests/golden/test_goldens_match.py`` (S7-03).
The AC's underlying intent (run the CLI end-to-end, capture
exit/stderr/stdout) is preserved.

Story-deviation note (AC-26): the AC literal text describes a
prefix-allowlist (``"skill_shadowed"``, ``"strace_unavailable"``,
``"image_digest_unresolved"``, ``"external_docs_skipped"``). The
project's stderr is structured-JSON logs, not bare warning IDs —
every line is a full JSON event envelope. The structural check
implemented here (every non-empty line parses as JSON; the set of
``event`` values must not contain ``"cli.unhandled"``; the final
``cli.end`` event has ``outcome == "ok"``) preserves the AC intent
(no undocumented stderr noise; no panicking exit) while matching the
shipped log format.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess  # noqa: S404 — tests/ scope; subprocess ban applies under src/
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from codegenie.parsers import safe_yaml
from codegenie.schema.validator import validate as validate_envelope

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PORTFOLIO = _REPO_ROOT / "tests" / "fixtures" / "portfolio"

_TOTAL_WALLCLOCK_BUDGET_S = 360.0  # AC-29 hard ceiling
_PER_FIXTURE_TIMEOUT_S = 180  # subprocess timeout per fixture

# Cap for safe_yaml.load — the envelope is ~tens of KB in practice; 4 MiB
# is generous and matches the chokepoint convention elsewhere in tests.
_YAML_READ_CAP_BYTES = 4 * 1024 * 1024


def _enumerate_fixtures() -> list[Path]:
    """Sorted, ``_``-prefix-skipped portfolio fixtures (AC-25 / S7-03 convention)."""
    return sorted(p for p in _PORTFOLIO.iterdir() if p.is_dir() and not p.name.startswith("_"))


def _dir_sha256(root: Path) -> str:
    """Stable SHA-256 over (relative path, file bytes) for every tracked file
    under ``root``. Used by AC-31 to prove the canonical fixture tree is
    not mutated by the sweep.
    """
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def _parse_stderr_log_lines(stderr_text: str) -> list[dict[str, Any]]:
    """Parse each non-empty stderr line as a JSON log envelope.

    The project's structlog configuration emits one JSON object per
    line. A line that fails to parse is a structural regression —
    surfaces as a test failure (AC-26 intent) rather than a silent
    skip.
    """
    events: list[dict[str, Any]] = []
    for raw in stderr_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:  # pragma: no cover — failure path
            raise AssertionError(
                f"stderr line is not a JSON log envelope: {line!r}; error={exc}"
            ) from exc
        if not isinstance(obj, dict):  # pragma: no cover — failure path
            raise AssertionError(f"stderr line is not a JSON object: {line!r}")
        events.append(obj)
    return events


def _assert_stderr_is_clean(fixture_name: str, stderr_text: str) -> None:
    """AC-26 structural check: parse-clean JSON log stream with no panics.

    Failure modes that fire this assertion:

    - any stderr line is not a JSON object
    - the event set includes ``cli.unhandled`` (the documented
      unhandled-crash signal — see ``codegenie.cli`` line ~775)
    - the final ``cli.end`` event has ``outcome != "ok"`` (or is absent)
    """
    events = _parse_stderr_log_lines(stderr_text)
    event_names = [e.get("event") for e in events]

    assert "cli.unhandled" not in event_names, (
        f"{fixture_name}: cli.unhandled appeared in stderr — "
        f"unhandled crash signal. Events: {event_names}"
    )

    cli_end_events = [e for e in events if e.get("event") == "cli.end"]
    assert cli_end_events, (
        f"{fixture_name}: no cli.end event in stderr; expected exactly one. Events: {event_names}"
    )
    outcome = cli_end_events[-1].get("outcome")
    assert outcome == "ok", f"{fixture_name}: cli.end carries outcome={outcome!r}, expected 'ok'"


@pytest.mark.serial  # AC-30 — ADR-0009; never xdist
def test_portfolio_sweep(tmp_path: Path) -> None:
    """Gather every fixture serially and assert exit/schema/golden + budget."""
    walltimes: dict[str, float] = {}
    pre_hash = _dir_sha256(_PORTFOLIO)  # AC-31
    sweep_t0 = time.perf_counter()

    fixtures = _enumerate_fixtures()
    assert fixtures, f"no fixtures under {_PORTFOLIO}"

    for fixture in fixtures:
        workdir = tmp_path / fixture.name
        shutil.copytree(fixture, workdir)  # AC-31 — never mutate canonical tree

        t0 = time.perf_counter()
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "codegenie",
                "--no-gitignore",
                "gather",
                str(workdir),
            ],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=_PER_FIXTURE_TIMEOUT_S,
            check=False,
        )
        walltimes[fixture.name] = time.perf_counter() - t0

        # AC-26 — stderr is structured JSON; no unhandled crashes; cli.end is ok.
        _assert_stderr_is_clean(fixture.name, result.stderr)
        assert result.returncode == 0, (
            f"{fixture.name}: gather exit={result.returncode}\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr (last 2000 bytes) ---\n{result.stderr[-2000:]}\n"
        )

        # AC-27 — envelope schema validation via the project's chokepoints.
        # ``safe_yaml.load`` for parsing; ``codegenie.schema.validator.validate``
        # for the envelope + per-probe sub-schema registry resolution
        # (S5-03 widened the glob to ``rglob`` so layer-scoped sub-schemas
        # register automatically — see attempts log lesson L27).
        ctx_path = workdir / ".codegenie" / "context" / "repo-context.yaml"
        assert ctx_path.is_file(), f"{fixture.name}: missing {ctx_path}"
        envelope = dict(safe_yaml.load(ctx_path, max_bytes=_YAML_READ_CAP_BYTES))
        validate_envelope(envelope)

    # AC-28 — golden diff empty (delegates byte-level diff to S7-03's harness).
    check_result = subprocess.run(
        [
            sys.executable,
            str(_REPO_ROOT / "scripts" / "regen_golden.py"),
            "--check",
            "--portfolio",
        ],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert check_result.returncode == 0, (
        "AC-28 — golden diff non-empty. Run "
        "`python scripts/regen_golden.py --update --portfolio` after "
        f"investigating each diff. stderr follows:\n{check_result.stderr}"
    )

    total_wallclock = time.perf_counter() - sweep_t0

    # AC-31 — canonical portfolio tree is byte-identical post-sweep.
    post_hash = _dir_sha256(_PORTFOLIO)
    assert post_hash == pre_hash, "canonical portfolio fixture tree was modified during the sweep"

    # AC-32 — walltime artifact emitted only when env-gated; otherwise
    # printed for pytest -s visibility (never writes the repo tree).
    walltimes_json = json.dumps(walltimes, sort_keys=True, indent=2)
    out_path = os.environ.get("CODEGENIE_PORTFOLIO_WALLTIME_OUT")
    if out_path:
        Path(out_path).write_text(walltimes_json + "\n")
    else:
        print(f"\nportfolio walltimes (seconds):\n{walltimes_json}")  # noqa: T201 — diagnostic under pytest -s; never persisted

    # AC-29 — budget assertion last so per-fixture detail above surfaces first.
    assert total_wallclock <= _TOTAL_WALLCLOCK_BUDGET_S, (
        f"portfolio sweep exceeded {_TOTAL_WALLCLOCK_BUDGET_S}s budget: "
        f"{total_wallclock:.1f}s\n{walltimes_json}"
    )
