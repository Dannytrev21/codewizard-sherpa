"""Phase 0/1/2 kernel-frozen fence: git-diff against a pinned baseline SHA.

ADR-0011 framing: this is **audit + lint** enforcement, NOT a runtime guarantee.
A determined PR that edits both the baseline file
(``_phase2_baseline.txt``) and the violation defeats this fence; CODEOWNERS
on ``tests/fence/`` + ``tests/fence/_phase2_baseline.txt`` is the social
anchor (raise via review).

**CI fetch-depth requirement.** GitHub Actions defaults to a shallow clone.
The baseline SHA must be reachable from ``HEAD`` for ``git merge-base
--is-ancestor`` and ``git diff`` to work. ``_ensure_baseline_reachable``
self-heals a shallow clone by attempting ``git fetch --unshallow`` when the
baseline SHA is missing — so this fence works without callers having to set
``actions/checkout`` with ``fetch-depth: 0`` ahead of time. If the unshallow
fetch fails (e.g., the SHA was rewritten on the remote), the diff call
surfaces a clear error.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Final

import pytest

# ---------------------------------------------------------------------------
# Baselines — Final tuple keyed by phase name so adding ``_phase3_baseline.txt``
# at Phase-4 time is a one-row append (Open/Closed at the file boundary).
# ---------------------------------------------------------------------------

_BASELINES: Final[tuple[tuple[str, Path], ...]] = (
    ("phase-2", Path("tests/fence/_phase2_baseline.txt")),
)


# ---------------------------------------------------------------------------
# Allowlist — paths Phase 3 work is permitted to touch inside the kernel
# scope. Each entry carries an inline ``# adr:`` reason. "Allowed-IF-touched"
# semantics: a file on this list is NOT required to be modified; it MAY be.
# ---------------------------------------------------------------------------

# Each entry's trailing ``# adr:`` comment names the owning story / ADR.
_KERNEL_ALLOWLIST: Final[frozenset[Path]] = frozenset(
    {
        # S1-05 — import-linter contract extension
        Path("pyproject.toml"),
        # S4-05 / P3-ADR-0012 — ALLOWED_BINARIES amendment (allowed-if-touched)
        Path("src/codegenie/exec/__init__.py"),
        # S1-01 / P3-ADR-0010 — newtype additions
        Path("src/codegenie/types/identifiers.py"),
        # S1-01 — re-exports
        Path("src/codegenie/types/__init__.py"),
        # S1-01 — shared error envelope
        Path("src/codegenie/types/errors.py"),
        # S1-01 — smart-constructor parsers
        Path("src/codegenie/types/parsers.py"),
        # S1-01 — PEP 561 marker
        Path("src/codegenie/py.typed"),
        # S1-05 — this story's walker
        Path("src/codegenie/_phase3_fence.py"),
        # ADR-0010 Amendment 2026-05-18 — AdapterConfidence canonical-home
        # consolidation: adapters.confidence becomes a pure re-export of
        # transforms.outcomes (Phase 2 typed surface preserved; classes
        # de-duplicated). adr: docs/phases/03-vuln-deterministic-recipe/
        # ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md
        # §Amendments (2026-05-18).
        Path("src/codegenie/adapters/confidence.py"),
        # ADR-0010 Amendment 2026-05-18 — cycle-fix dependency: PackageManager
        # import moved under TYPE_CHECKING (annotation-only use under
        # ``from __future__ import annotations``). Required so that
        # types.identifiers can be imported by transforms.outcomes /
        # adapters.confidence without forming the types ↔ probes cycle.
        Path("src/codegenie/depgraph/registry.py"),
        # ADR-0010 Amendment 2026-05-18 — cycle-fix dependency: PackageManager
        # imported from the canonical origin (probes.node_build_system) rather
        # than the types.identifiers re-export, to keep this module out of the
        # types.identifiers init cycle. Phase 1 ADR-0013 still owns the enum.
        Path("src/codegenie/probes/layer_b/dep_graph.py"),
        # S2-03 — additive ``tree_digest_of_files`` extension of the ADR-0001
        # chokepoint. The Phase-3 plugin loader routes its per-plugin
        # tree-digest verification through this function rather than importing
        # ``hashlib.sha256`` directly. adr: docs/phases/03-vuln-deterministic-
        # recipe/ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md
        # §Consequences (Phase 11 substitution seam exposed as ``PluginVerifier``).
        Path("src/codegenie/hashing.py"),
    }
)


# ---------------------------------------------------------------------------
# Kernel scope — Phase 0/1/2 dirs the fence guards. Phase 3 NEW packages
# (``plugins/``, ``transforms/``) are deliberately excluded; they are the
# *expected* additive surface this story exists to protect.
# ---------------------------------------------------------------------------

_KERNEL_SCOPE_DIRS: Final[tuple[Path, ...]] = (
    Path("src/codegenie/probes"),
    Path("src/codegenie/coordinator"),
    Path("src/codegenie/output"),
    Path("src/codegenie/cache"),
    Path("src/codegenie/grammars"),
    Path("src/codegenie/exec"),
    Path("src/codegenie/indices"),
    Path("src/codegenie/conventions"),
    Path("src/codegenie/types"),
)
_TOP_LEVEL_PHASE3_PACKAGES: Final[frozenset[str]] = frozenset(
    {
        "plugins",
        "transforms",
        # S3-02 — content-addressed sqlite VulnIndex (Phase-3 ADR-0008 +
        # ADR-0005 staleness predicate). Additive Phase-3 surface; not part
        # of the Phase-0/1/2 kernel scope.
        "vuln_index",
    }
)


def _is_in_kernel_scope(path: Path) -> bool:
    parts = path.parts
    if len(parts) < 3 or parts[0] != "src" or parts[1] != "codegenie":
        return False
    # Top-level files like ``src/codegenie/__init__.py`` and ``py.typed`` are
    # in scope; ``src/codegenie/<subpkg>/...`` is in scope iff the subpkg is
    # NOT a Phase 3 new package.
    if len(parts) == 3:
        return True  # top-level src/codegenie/<file>
    subpkg = parts[2]
    if subpkg in _TOP_LEVEL_PHASE3_PACKAGES:
        return False
    return (
        any(
            path.is_relative_to(scope_dir) or scope_dir == Path("src/codegenie") / subpkg
            for scope_dir in _KERNEL_SCOPE_DIRS
        )
        or len(parts) >= 3
    )  # other src/codegenie/* subdirs default in-scope


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_baseline_sha(baseline_path: Path) -> str:
    text = baseline_path.read_text(encoding="utf-8").strip()
    return text


def _ensure_baseline_reachable(baseline: str) -> None:
    """Self-heal a shallow clone before reading ``git diff``.

    GitHub Actions defaults to ``fetch-depth: 1``, which means commits older
    than ``HEAD`` are not in the local history. We try ``git cat-file -e``
    first (cheap reachability check); if the baseline is missing AND the
    clone is shallow, attempt ``git fetch --unshallow``. This keeps the
    fence working without forcing every caller (CI YAML, local dev) to set
    ``fetch-depth: 0`` ahead of time. Falls through silently if the clone
    is already deep — the diff call will surface a clearer error if the
    SHA genuinely doesn't exist in the remote.
    """
    cat = subprocess.run(
        ["git", "cat-file", "-e", f"{baseline}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if cat.returncode == 0:
        return
    is_shallow = (
        subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        == "true"
    )
    if is_shallow:
        subprocess.run(
            ["git", "fetch", "--unshallow"],
            capture_output=True,
            text=True,
            check=False,
        )


def _run_git_diff(baseline: str, head: str = "HEAD") -> list[tuple[str, Path]]:
    """Return ``[(status, path), ...]`` from ``git diff --name-status -M``.

    ``-M`` enables rename detection so a delete-then-recreate that defeats the
    naive diff is treated as ``R`` (in-scope) rather than disappearing.
    Self-heals a shallow CI clone before invoking diff.
    """
    _ensure_baseline_reachable(baseline)
    result = subprocess.run(
        ["git", "diff", "--name-status", "-M", f"{baseline}..{head}"],
        capture_output=True,
        text=True,
        check=True,
    )
    out: list[tuple[str, Path]] = []
    for raw in result.stdout.splitlines():
        if not raw.strip():
            continue
        parts = raw.split("\t")
        status_letter = parts[0][:1]
        # For renames (R100\told\tnew) the new path is the last column.
        path_str = parts[-1]
        out.append((status_letter, Path(path_str)))
    return out


# ---------------------------------------------------------------------------
# AC-6.b baseline integrity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,baseline_path", _BASELINES, ids=[n for n, _ in _BASELINES])
def test_baseline_file_is_a_real_40_char_sha(name: str, baseline_path: Path) -> None:
    sha = _read_baseline_sha(baseline_path)
    assert re.fullmatch(r"[0-9a-f]{40}", sha), (
        f"{baseline_path} must contain exactly one 40-char lowercase hex SHA. Got: {sha!r}"
    )


@pytest.mark.parametrize("name,baseline_path", _BASELINES, ids=[n for n, _ in _BASELINES])
def test_baseline_resolves_to_ancestor_of_head_and_is_not_head(
    name: str, baseline_path: Path
) -> None:
    sha = _read_baseline_sha(baseline_path)
    _ensure_baseline_reachable(sha)
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert sha != head_sha, (
        f"{baseline_path} accidentally pasted HEAD ({head_sha}); baseline must be a "
        f"pre-Phase-3 commit."
    )
    ancestor_check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ancestor_check.returncode == 0, (
        f"{baseline_path} SHA {sha} is not an ancestor of HEAD. "
        f"This usually means a shallow clone (CI: set fetch-depth: 0)."
    )


# ---------------------------------------------------------------------------
# AC-6 live kernel-frozen check
# ---------------------------------------------------------------------------


def _kernel_violations(
    diff: list[tuple[str, Path]],
    allowlist: frozenset[Path] = _KERNEL_ALLOWLIST,
) -> list[tuple[str, Path]]:
    """Return diff entries that touch kernel scope and aren't allowlisted."""
    out: list[tuple[str, Path]] = []
    for status, path in diff:
        if path in allowlist:
            continue
        if _is_in_kernel_scope(path):
            out.append((status, path))
        elif path == Path("pyproject.toml"):
            # Allowlisted above already; defensive.
            continue
    return out


def test_phase3_has_not_modified_phase012_kernel_outside_allowlist() -> None:
    """AC-6 live: ``git diff`` between baseline and HEAD MUST be empty under
    the kernel scope (modulo the ADR-anchored allowlist)."""
    baseline = _read_baseline_sha(_BASELINES[0][1])
    diff = _run_git_diff(baseline)
    violations = _kernel_violations(diff)
    assert violations == [], (
        f"Phase 3 work touched Phase 0/1/2 kernel files outside the "
        f"`_KERNEL_ALLOWLIST`: {violations}. Either add the file to the "
        f"allowlist (with an `# adr:` comment) via ADR amendment, or revert "
        f"the change. See `tests/fence/_phase2_baseline.txt` + ADR-0011."
    )


# ---------------------------------------------------------------------------
# AC-6.c helpful-error guard via injected fake-diff source
# ---------------------------------------------------------------------------


def test_helpful_error_names_baseline_file_and_adr_amendment() -> None:
    """AC-6.c: if the kernel-frozen test fails, the error message MUST point
    operators at ``_phase2_baseline.txt`` and the words ``ADR amendment``."""
    fake_diff: list[tuple[str, Path]] = [
        ("M", Path("src/codegenie/probes/layer_a/language_detection.py"))
    ]
    violations = _kernel_violations(fake_diff)
    assert violations, "Fake diff MUST be flagged as a kernel violation"
    # Re-build the message the live test would emit so we can pin its shape.
    expected_message = (
        f"Phase 3 work touched Phase 0/1/2 kernel files outside the "
        f"`_KERNEL_ALLOWLIST`: {violations}. Either add the file to the "
        f"allowlist (with an `# adr:` comment) via ADR amendment, or revert "
        f"the change. See `tests/fence/_phase2_baseline.txt` + ADR-0011."
    )
    assert "_phase2_baseline.txt" in expected_message
    assert "ADR amendment" in expected_message


# ---------------------------------------------------------------------------
# AC-6.d renames + deletions are flagged
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,path,expected_flagged",
    [
        ("M", Path("src/codegenie/probes/layer_a/language_detection.py"), True),
        ("D", Path("src/codegenie/probes/layer_a/language_detection.py"), True),
        ("R", Path("src/codegenie/probes/layer_a/renamed.py"), True),
        ("A", Path("src/codegenie/probes/layer_a/new_file.py"), True),
        ("M", Path("src/codegenie/plugins/scope.py"), False),  # Phase 3 new pkg
        ("M", Path("src/codegenie/transforms/transform.py"), False),
        ("M", Path("pyproject.toml"), False),  # allowlisted
        ("M", Path("docs/anything.md"), False),  # outside src/
        ("M", Path("tests/unit/probes/foo.py"), False),  # outside src/codegenie/
    ],
)
def test_diff_status_classification(status: str, path: Path, expected_flagged: bool) -> None:
    """AC-6.d: rename + delete diff statuses are classified the same way as
    modification — the scope check is path-based, not status-based."""
    violations = _kernel_violations([(status, path)])
    assert bool(violations) is expected_flagged, (
        f"Diff entry ({status}, {path}) classification drift: "
        f"expected_flagged={expected_flagged}, got {violations}"
    )


# ---------------------------------------------------------------------------
# AC-6.e + AC-6.f framing docstring checks
# ---------------------------------------------------------------------------


def test_module_docstring_names_adr_0011_framing_and_fetch_depth() -> None:
    """AC-6.e + AC-6.f: the module docstring MUST flag the framing posture
    AND the CI fetch-depth requirement so a future reader doesn't quietly
    break the diff with a shallow clone."""
    from tests.fence import test_kernel_frozen as me  # self-reflective

    assert me.__doc__ is not None
    doc = me.__doc__.lower()
    assert "audit + lint" in doc or "audit and lint" in doc
    assert "not a runtime guarantee" in doc
    assert "fetch-depth" in doc
    # The baseline rotation file should be named so future readers find it.
    assert "_phase2_baseline.txt" in me.__doc__
