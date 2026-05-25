"""Phase-4 S3-05 — CI cassette walker (sanitizer + lock invariants).

Hard-fails the entire CI build the moment any cassette under
``tests/cassettes/`` leaks a forbidden header / body pattern, drifts from
``cassettes.lock``, orphans a cassette without a lock entry, or leaves a
stale lock entry whose cassette has been deleted. The CI walker is the
backstop layer; the sanitizer (S3-04) is the first defense.

Implementation discipline (AC-5/6/7/8/19):

- **Pure collector helpers** at module scope return a tuple of diagnostic
  strings rather than asserting inside loops. The top-level test bodies
  call ``pytest.fail("\\n".join(findings))`` exactly once so a single bad
  cassette cannot hide another. This is the AC-19 "no early return"
  invariant the validator surfaced.
- **One findings tuple per dimension** so the helpers can be unit-tested
  (`test_cassette_lock_invariants.py`) against synthetic tmp dirs without
  ever touching repo state.

ADR-0014 §Consequences: ``tests/security/test_cassettes_clean.py`` runs
in every CI build; failure = hard CI block.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.fallback.cassette.manifest import (
    LockfileMalformed,
    compute_cassette_digest,
    load_lockfile,
    rebuild_lockfile,
)
from codegenie.fallback.cassette.sanitizer import verify_cassette

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CASSETTES_DIR = _REPO_ROOT / "tests" / "cassettes"
_ANTHROPIC_DIR = _CASSETTES_DIR / "anthropic"


# --- Pure collector helpers (AC-19) --------------------------------------


def _collect_sanitizer_findings(cassettes_dir: Path) -> tuple[str, ...]:
    """Walk every cassette under ``cassettes_dir``; aggregate sanitizer leaks.

    PURE wrt writes. Reads cassette bytes through S3-04's
    :func:`verify_cassette`. Returns an empty tuple if no cassettes exist
    (the bootstrap path) or if every cassette is clean.
    """
    findings: list[str] = []
    if not cassettes_dir.exists():
        return ()
    for cassette in sorted(cassettes_dir.rglob("*.yaml")):
        if not cassette.is_file():
            continue
        result = verify_cassette(cassette)
        if result.passed:
            continue
        relpath = cassette.relative_to(cassettes_dir).as_posix()
        for v in result.violations:
            header = f" header_name={v.header_name!r}" if v.header_name else ""
            pattern = f" pattern={v.pattern!r}" if v.pattern else ""
            findings.append(
                f"{relpath} interaction={v.interaction_index} kind={v.kind}"
                f"{header}{pattern} snippet={v.snippet!r}"
            )
    return tuple(findings)


def _collect_lock_findings(anthropic_dir: Path) -> tuple[str, ...]:
    """Aggregate every lock invariant failure across ``anthropic_dir``.

    PURE wrt writes. Emits four named diagnostic shapes (AC-6/7/8):

    - ``cassette.lock_malformed`` — file missing or shape invalid.
    - ``cassette.lock_drift`` — cassette body changed without lock update.
    - ``cassette.lock_orphan`` — cassette on disk has no lock entry.
    - ``cassette.lock_stale`` — lock entry whose cassette has been deleted.

    When the lock file is malformed every drift/orphan/stale check is
    skipped — the malformation is the only finding (the other checks
    cannot be trusted against an unparsable lock).
    """
    findings: list[str] = []
    if not anthropic_dir.exists():
        return ()
    lock_path = anthropic_dir / "cassettes.lock"
    try:
        lock_map = load_lockfile(lock_path)
    except LockfileMalformed as exc:
        findings.append(
            f"cassette.lock_malformed: {exc.reason} "
            f"line={exc.line_number} content={exc.line_content!r}"
        )
        return tuple(findings)

    # On-disk cassette set (POSIX-relative).
    on_disk: dict[str, Path] = {}
    for cassette in sorted(anthropic_dir.rglob("*.yaml")):
        if not cassette.is_file():
            continue
        relpath = cassette.relative_to(anthropic_dir).as_posix()
        on_disk[relpath] = cassette

    # Drift + orphan: walk on-disk cassettes.
    for relpath, cassette in on_disk.items():
        if relpath not in lock_map:
            findings.append(f"cassette.lock_orphan: {relpath}")
            continue
        actual = compute_cassette_digest(cassette)
        expected = lock_map[relpath]
        if actual != expected:
            findings.append(
                "cassette.lock_drift: "
                f"{relpath} expected={expected} actual={actual} — "
                "run `python -m codegenie cassette rebuild-lockfile` and "
                "commit the result, then resubmit with cassette-steward "
                "CODEOWNERS approval"
            )

    # Stale: walk lock entries.
    for relpath in lock_map:
        if relpath not in on_disk:
            findings.append(f"cassette.lock_stale: {relpath}")
    return tuple(findings)


# --- Top-level pytest tests (AC-5/6/7/8) ---------------------------------


def test_every_cassette_passes_sanitizer() -> None:
    """No cassette in ``tests/cassettes/`` carries a sanitizer leak.

    Bootstrap: if ``tests/cassettes/`` is empty (the Phase 4 state until
    S3-06 records the first cassette), the helper returns ``()`` and
    this test trivially passes — but the empty-dir-is-fine semantics are
    pinned by ``test_collect_sanitizer_findings_is_empty_on_empty_dir``
    in ``test_cassette_lock_invariants.py``.
    """
    findings = _collect_sanitizer_findings(_CASSETTES_DIR)
    if findings:
        pytest.fail("sanitizer violations:\n" + "\n".join(findings))


def test_lock_matches_disk() -> None:
    """Every on-disk cassette under ``anthropic/`` is locked, current, and clean.

    Bootstrap-friendly: when ``anthropic/`` exists with an empty lock and
    no ``*.yaml`` cassettes, no findings are emitted. The dedicated
    aggregation cases live in ``test_cassette_lock_invariants.py``.
    """
    findings = _collect_lock_findings(_ANTHROPIC_DIR)
    if findings:
        pytest.fail("lock invariant violations:\n" + "\n".join(findings))


def test_lock_can_be_rebuilt_byte_identical() -> None:
    """The committed lock matches what ``rebuild_lockfile`` produces today.

    Defense-in-depth against a contributor who edits the lock by hand —
    the rebuild is the source of truth.
    """
    if not _ANTHROPIC_DIR.exists():
        # Bootstrap; the directory has not been created yet.
        return
    lock_path = _ANTHROPIC_DIR / "cassettes.lock"
    if not lock_path.exists():
        pytest.fail(
            "cassettes.lock is missing under tests/cassettes/anthropic/ — "
            "run `python -m codegenie cassette rebuild-lockfile`"
        )
    on_disk = lock_path.read_text(encoding="utf-8")
    rebuilt = rebuild_lockfile(_ANTHROPIC_DIR)
    if on_disk != rebuilt:
        pytest.fail(
            "tests/cassettes/anthropic/cassettes.lock is not byte-identical "
            "to rebuild_lockfile() — run "
            "`python -m codegenie cassette rebuild-lockfile` and commit"
        )
