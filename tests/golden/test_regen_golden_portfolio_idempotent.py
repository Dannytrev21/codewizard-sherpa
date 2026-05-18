"""S7-03 AC-27 — two-runs-byte-identical idempotence is a CI gate.

Invokes ``scripts/regen_golden.py --update --portfolio`` twice and asserts
the second invocation produced zero file changes (SHA-256 set is stable).

This test is the CI safety net behind AC-26's PR-merge discipline. Promotes
the S6-01 HARDENED precedent ("humans miss things; CI doesn't") from a
manual check to an enforceable gate.

Skipped on non-Linux when the matrix would error-out per AC-16; with the
current platform-agnostic matrix this test runs on every platform.
"""

from __future__ import annotations

import hashlib
import subprocess  # noqa: S404 — tests/ scope; subprocess ban applies under src/
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REGEN_SCRIPT = _REPO_ROOT / "scripts" / "regen_golden.py"
_GOLDEN_ROOT = _REPO_ROOT / "tests" / "golden" / "probes"


def _snapshot_sha_set(root: Path) -> dict[str, str]:
    """SHA-256 map of every ``*.json`` under *root* keyed by relpath."""
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*.json")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        out[str(path.relative_to(root))] = digest
    return out


def test_two_consecutive_updates_are_byte_identical() -> None:
    """`--update --portfolio` twice → second run produces zero file changes."""
    # First pass — captures baseline. We trust the committed goldens are
    # already a fixed point (the harness test enforces that). This test
    # verifies the *operation* itself is idempotent: running update against
    # a clean tree produces no churn on the second invocation.
    result1 = subprocess.run(
        [sys.executable, str(_REGEN_SCRIPT), "--update", "--portfolio"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result1.returncode == 0, (
        f"first --update failed (rc={result1.returncode}):\n{result1.stderr}"
    )
    snapshot_a = _snapshot_sha_set(_GOLDEN_ROOT)

    result2 = subprocess.run(
        [sys.executable, str(_REGEN_SCRIPT), "--update", "--portfolio"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result2.returncode == 0, (
        f"second --update failed (rc={result2.returncode}):\n{result2.stderr}"
    )
    snapshot_b = _snapshot_sha_set(_GOLDEN_ROOT)

    assert snapshot_a == snapshot_b, (
        "Two consecutive --update passes produced different golden bytes — "
        "a non-deterministic field slipped past the exclusion list. "
        "Investigate and add an entry to _EXCLUDED_FIELD_NAMES (with the "
        "source-of-non-determinism commented). "
        f"Pass 1: {len(snapshot_a)} files; Pass 2: {len(snapshot_b)} files; "
        f"differing entries: "
        f"{sorted(k for k in snapshot_a if snapshot_a.get(k) != snapshot_b.get(k))}"
    )
