"""S8-02 AC-6 — no new Phase-2 structlog event variants introduced.

This story emits zero new events; the existing ``envelope.written`` and
``skill_shadowed`` events remain the only structured-log surfaces for
the values the new stdout block reports. Verified two ways:

1. **Forbidden-event guard** — explicit assertion that the three
   "could-be-tempting" event names ``secrets.summary``,
   ``fingerprints.summary``, ``skills.shadowed.summary`` never appear in
   a clean gather's captured events.
2. **Source-grep interdict** — no call site in ``src/codegenie/cli.py``
   or ``src/codegenie/cli_summary.py`` emits a new event-name literal.
"""

from __future__ import annotations

import re
import shutil
from collections import Counter
from pathlib import Path

from click.testing import CliRunner
from structlog.testing import capture_logs

_FORBIDDEN_NEW_EVENTS: frozenset[str] = frozenset(
    {
        "secrets.summary",
        "fingerprints.summary",
        "skills.shadowed.summary",
        "skill_shadowed.summary",
        "phase2.summary",
        "cli.summary",
    }
)


def _seed_minimal_ts(tmp_path: Path) -> Path:
    src = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "portfolio" / "minimal-ts"
    dst = tmp_path / "minimal-ts"
    shutil.copytree(src, dst)
    return dst


def test_no_forbidden_event_names_in_clean_gather(tmp_path: Path) -> None:
    """AC-6 — none of the forbidden event-name variants appear at runtime."""
    from codegenie.cli import cli

    fixture = _seed_minimal_ts(tmp_path)
    with capture_logs() as captured:
        result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(fixture)])
    assert result.exit_code == 0, result.output
    seen = Counter(e.get("event") for e in captured)
    for forbidden in _FORBIDDEN_NEW_EVENTS:
        assert seen[forbidden] == 0, (
            f"forbidden Phase-2 event variant {forbidden!r} appeared "
            f"{seen[forbidden]}× — ADR-0008 violation"
        )


def test_no_new_event_emission_in_cli_summary_source() -> None:
    """AC-6 / ADR-0008 — the new module emits zero structlog events.

    Greps the source for ``_log.``, ``.warning(``, ``.info(`` patterns
    that would indicate a new event-emission call site. The pure
    formatter has no logger at all (also enforced by the AST gate in
    :func:`test_pure_no_io_imports`); this is the belt-and-suspenders
    check on the impure shell.
    """
    cli_src = (Path(__file__).resolve().parents[3] / "src" / "codegenie" / "cli.py").read_text()
    # New emission paths a contributor might add: any ``_log.<level>(``
    # call inside the new helper region of cli.py. Pattern is narrow on
    # purpose — pre-existing _log.info / log.info calls (cli.start,
    # cli.end, cli.unhandled, cache.gc.stub) are not regressed by this
    # story; the test is specifically a guard against this story's net-new
    # code adding a *new* event variant.
    summary_helper_re = re.compile(
        r"def _emit_phase2_summary\(.*?\)\s*->\s*None:\s*\"\"\".*?\"\"\"(.*?)(?=^def\s|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    m = summary_helper_re.search(cli_src)
    assert m is not None, "could not locate _emit_phase2_summary body"
    helper_body = m.group(1)
    for forbidden_call in ("_log.info", "_log.warning", "structlog.get_logger"):
        assert forbidden_call not in helper_body, (
            f"_emit_phase2_summary must not emit structured logs; found {forbidden_call!r}"
        )
    # The purity of ``cli_summary.py`` is covered by the AST gate in
    # ``test_summary_block_pure.py::test_pure_no_io_imports``; this test
    # focuses on the impure shell's net-new helper.
