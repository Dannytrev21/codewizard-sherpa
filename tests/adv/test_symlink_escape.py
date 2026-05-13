"""Adversarial: out-of-repo symlinks are skipped, not followed.

``LanguageDetectionProbe._classify_symlink`` returns ``"escaped"`` for any
symlink whose resolved target falls outside the analyzed-repo root. The
walker emits ``probe.symlink.escaped`` with a repo-relative path and never
the resolved target. This test pins four structural invariants:

1. **Skip** — the escaped symlink is NOT counted (closed-world dict equality
   on ``language_stack.counts``).
2. **Event emitted exactly once** — one escape, one event.
3. **Event payload binds to the offender** — ``path == "link.js"``.
4. **No resolved-target leak** — ``/etc/hosts`` must not appear in the
   structlog payload or the CLI's stdout/stderr.

Traces to:
- ADR-0007 (LanguageDetectionProbe contract).
- ``phase-arch-design.md §Edge cases`` row 4 (symlink-escape).
- ``language_detection.py:142-200`` — ``_classify_symlink`` and the walker
  emit ``probe.symlink.escaped`` with ``path=`` only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from structlog.testing import capture_logs


@pytest.mark.skipif(sys.platform == "win32", reason="symlink test requires POSIX")
def test_symlink_out_of_repo_skipped(tmp_path: Path) -> None:
    """
    Pins: a symlink whose target resolves outside the repo root is skipped by
          ``LanguageDetectionProbe`` and emits ``probe.symlink.escaped`` with
          the offender's repo-relative path and no resolved target.
    Traces to: ADR-0007; phase-arch-design.md §Edge cases row 4;
          language_detection.py:142-200.
    Catches:
      - A regression that dropped the ``if classification == "escaped":
        continue`` line — the symlink would be followed and counts would
        contain javascript == 2 → closed-world dict equality fails.
      - A regression that dropped the ``path=`` kwarg from the structlog
        call — the path-value assertion fails.
      - A regression that added a ``target=<resolved>`` field — the no-leak
        assertion fails.
    """
    from codegenie.cli import cli

    (tmp_path / "a.js").write_text("//\n")
    os.symlink("/etc/hosts", tmp_path / "link.js")

    with capture_logs() as logs:
        result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(tmp_path)])

    # (1) Gather succeeds — the surviving sibling probe (a.js) keeps the
    # ADR-0009 "at-least-one-probe-survived" gate green.
    assert result.exit_code == 0, (
        f"gather did not exit 0 in presence of an escaped symlink; "
        f"exit_code={result.exit_code}, output={result.output!r}"
    )

    # (2) Exactly one probe.symlink.escaped event, bound to the offender,
    # no resolved-target leak.
    escaped = [e for e in logs if e.get("event") == "probe.symlink.escaped"]
    assert len(escaped) == 1, f"expected exactly 1 escaped event, got {len(escaped)}: {escaped!r}"
    assert escaped[0].get("path") == "link.js", f"event bound to wrong entry: {escaped[0]!r}"
    assert "/etc/hosts" not in str(escaped[0]), (
        f"resolved target leaked into log payload: {escaped[0]!r}"
    )
    assert "/etc/hosts" not in result.output, "resolved target leaked into stdout/stderr"

    # (3) YAML parse (not substring): closed-world counts. An extra spurious
    # language entry would fail; counts of 2 for javascript (i.e., the
    # symlink was followed) would also fail.
    yaml_path = tmp_path / ".codegenie" / "context" / "repo-context.yaml"
    data = yaml.safe_load(yaml_path.read_text())
    counts = data["probes"]["language_detection"]["language_stack"]["counts"]
    assert counts == {"javascript": 1}, f"language_stack.counts drifted: {counts!r}"
