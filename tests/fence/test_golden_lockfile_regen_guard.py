"""AC-Gold-2 fence — golden lockfiles cannot change without a justification.

``tests/golden/lockfiles/*.before.json`` and ``*.after.json`` encode the
determinism contract G4: a byte-level drift IS a regression unless a human
deliberately reviewed it. This fence rejects any commit that modifies a
golden without an accompanying ``<name>.regen-justification.md`` sidecar
(carrying at minimum a ``Reason:`` line) changed in the same commit.

The pure :func:`_goldens_missing_sidecar` is exercised by planted cases that
always run; the live check inspects the real ``HEAD~1..HEAD`` git diff and
self-skips when no prior commit exists.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_PREFIX = "tests/golden/lockfiles/"


def _golden_base(path: str) -> str | None:
    """Return the golden base name for a ``*.before.json`` / ``*.after.json``
    path, else ``None``."""
    if not path.startswith(_GOLDEN_PREFIX):
        return None
    name = path[len(_GOLDEN_PREFIX) :]
    for suffix in (".before.json", ".after.json"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return None


def _goldens_missing_sidecar(changed_paths: set[str]) -> list[str]:
    """Return every golden base name whose lockfile changed but whose
    ``.regen-justification.md`` sidecar did NOT change in the same set."""
    changed_goldens = {
        base for base in (_golden_base(p) for p in changed_paths) if base is not None
    }
    out: list[str] = []
    for base in sorted(changed_goldens):
        sidecar = f"{_GOLDEN_PREFIX}{base}.regen-justification.md"
        if sidecar not in changed_paths:
            out.append(base)
    return out


def _git_changed_paths(diff_range: str) -> set[str] | None:
    proc = subprocess.run(
        ["git", "diff", "--name-only", diff_range],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_REPO_ROOT),
    )
    if proc.returncode != 0:
        return None
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def test_golden_changes_in_last_commit_carry_a_sidecar() -> None:
    """AC-Gold-2 live check — the most recent commit did not modify a golden
    lockfile without its regen-justification sidecar."""
    changed = _git_changed_paths("HEAD~1..HEAD")
    if changed is None:
        pytest.skip("no prior commit (HEAD~1 unavailable) — golden guard not applicable")
    missing = _goldens_missing_sidecar(changed)
    assert missing == [], (
        f"golden lockfile(s) changed without a .regen-justification.md sidecar: {missing}"
    )


def test_guard_flags_golden_change_without_sidecar() -> None:
    """AC-Gold-2 planted-positive — a golden change with no sidecar is flagged."""
    changed = {f"{_GOLDEN_PREFIX}express-cve-2024-21501.after.json"}
    assert _goldens_missing_sidecar(changed) == ["express-cve-2024-21501"]


def test_guard_passes_when_sidecar_accompanies_the_golden() -> None:
    """AC-Gold-2 complement — a golden change WITH its sidecar is allowed."""
    name = "express-cve-2024-21501"
    changed = {
        f"{_GOLDEN_PREFIX}{name}.after.json",
        f"{_GOLDEN_PREFIX}{name}.before.json",
        f"{_GOLDEN_PREFIX}{name}.regen-justification.md",
    }
    assert _goldens_missing_sidecar(changed) == []


def test_guard_ignores_non_golden_changes() -> None:
    """AC-Gold-2 complement — unrelated file changes never trip the guard."""
    assert _goldens_missing_sidecar({"src/codegenie/transforms/engines/npm_lockfile.py"}) == []
