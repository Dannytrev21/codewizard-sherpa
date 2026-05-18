"""S8-02 AC-1 — stdout summary shape on a clean gather.

Before this story, ``codegenie gather`` produced **zero** stdout on a
clean run (every byte went to stderr via structlog). After this story,
stdout carries exactly three lines, in the documented order:

```
secrets_redacted_count=<N>
fingerprints=[...]
skill_shadowed=[...]
```

The test runs against the ``minimal-ts`` portfolio fixture so the
behavior is exercised end-to-end through the real coordinator + writer
+ audit-record pipeline.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from click.testing import CliRunner
from structlog.testing import capture_logs


def _seed_fixture(tmp_path: Path) -> Path:
    """Copy the ``minimal-ts`` portfolio fixture into ``tmp_path``."""
    src = Path(__file__).resolve().parents[2] / "fixtures" / "portfolio" / "minimal-ts"
    dst = tmp_path / "minimal-ts"
    shutil.copytree(src, dst)
    return dst


def _invoke_gather_capturing_logs(fixture: Path) -> object:
    """Invoke ``codegenie gather`` with ``capture_logs()`` active.

    Structlog defaults to ``PrintLogger`` (stdout) when no
    ``configure_logging`` runs (the integration-cli conftest no-ops
    ``_seam_configure_logging`` so :func:`structlog.testing.capture_logs`
    survives ``CliRunner.invoke``). ``capture_logs`` swaps a non-emitting
    capture processor into the chain, so structlog events are intercepted
    rather than printed — leaving stdout for the Phase 2 summary block
    only.
    """
    from codegenie.cli import cli

    with capture_logs():
        return CliRunner().invoke(cli, ["--no-gitignore", "gather", str(fixture)])


def test_only_three_lines(tmp_path: Path) -> None:
    """AC-1 — stdout is exactly three lines on a clean gather."""
    fixture = _seed_fixture(tmp_path)
    result = _invoke_gather_capturing_logs(fixture)
    assert result.exit_code == 0, result.output
    lines = result.stdout.strip().split("\n")
    assert len(lines) == 3, (
        f"expected exactly 3 stdout lines; got {len(lines)} — stdout={result.stdout!r}"
    )
    assert lines[0].startswith("secrets_redacted_count=")
    assert lines[1].startswith("fingerprints=")
    assert lines[2].startswith("skill_shadowed=")
