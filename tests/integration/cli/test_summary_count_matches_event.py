"""S8-02 AC-2 — stdout ``secrets_redacted_count`` line equals the
``envelope.written`` structlog event's ``secrets_redacted_count`` field.

Asserts the new stdout surface and the existing structured-log surface
report the **same** in-memory value (per ADR-0008, the existing event
stays the only structured-log counterpart). Two scenarios:

- ``minimal-ts`` fixture — count must be 0 on both surfaces.
- ``tmp_path`` seeded with one AWS-access-key plaintext — count must be 1
  on both surfaces; no new ``secrets.summary`` event variant fires.
"""

from __future__ import annotations

import re
import shutil
from collections import Counter
from pathlib import Path

from click.testing import CliRunner
from structlog.testing import capture_logs

from codegenie.logging import EVENT_ENVELOPE_WRITTEN, SECRETS_REDACTED_COUNT_FIELD


def _seed_minimal_ts(tmp_path: Path) -> Path:
    src = Path(__file__).resolve().parents[2] / "fixtures" / "portfolio" / "minimal-ts"
    dst = tmp_path / "minimal-ts"
    shutil.copytree(src, dst)
    return dst


def _seed_minimal_ts_with_secret(tmp_path: Path, plaintext: str) -> Path:
    fixture = _seed_minimal_ts(tmp_path)
    secret_file = fixture / "src" / "secret.ts"
    secret_file.write_text(f'// fake secret for S8-02 test\nexport const KEY = "{plaintext}";\n')
    return fixture


def _invoke_with_capture(fixture: Path) -> tuple[object, list[dict[str, object]]]:
    from codegenie.cli import cli

    with capture_logs() as captured:
        result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(fixture)])
    return result, list(captured)


_COUNT_LINE_RE = re.compile(r"^secrets_redacted_count=(\d+)$", re.MULTILINE)


def _parse_stdout_count(stdout: str) -> int:
    m = _COUNT_LINE_RE.search(stdout)
    assert m is not None, f"no secrets_redacted_count line in stdout: {stdout!r}"
    return int(m.group(1))


def test_count_zero_on_clean_minimal_ts(tmp_path: Path) -> None:
    """Clean ``minimal-ts`` gather: stdout count == 0, event count == 0."""
    fixture = _seed_minimal_ts(tmp_path)
    result, captured = _invoke_with_capture(fixture)
    assert result.exit_code == 0, result.output

    stdout_count = _parse_stdout_count(result.stdout)
    written_events = [e for e in captured if e.get("event") == EVENT_ENVELOPE_WRITTEN]
    assert len(written_events) == 1, written_events
    event_count = written_events[0][SECRETS_REDACTED_COUNT_FIELD]
    assert stdout_count == event_count == 0


def test_count_one_when_secret_seeded(tmp_path: Path) -> None:
    """AWS-access-key plaintext seeded: stdout count == 1, event count == 1."""
    plaintext = "AKIA" + "A" * 16  # matches r"AKIA[0-9A-Z]{16}"
    fixture = _seed_minimal_ts_with_secret(tmp_path, plaintext)
    result, captured = _invoke_with_capture(fixture)
    assert result.exit_code == 0, result.output

    stdout_count = _parse_stdout_count(result.stdout)
    written_events = [e for e in captured if e.get("event") == EVENT_ENVELOPE_WRITTEN]
    assert len(written_events) == 1
    event_count = written_events[0][SECRETS_REDACTED_COUNT_FIELD]
    assert stdout_count == event_count
    # Plaintext NEVER appears in stdout (AC-3 boundary mirror).
    assert plaintext not in result.stdout
    # No new "secrets.summary" event variant introduced (AC-6).
    event_names = Counter(e.get("event") for e in captured)
    for forbidden in ("secrets.summary", "fingerprints.summary", "skills.shadowed.summary"):
        assert event_names[forbidden] == 0
