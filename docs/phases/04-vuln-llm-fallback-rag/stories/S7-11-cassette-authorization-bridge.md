# Story S7-11 — Cassette-recording authorization bridge (S6-07/S7-06/S7-07 unblocker)

**Step:** Step 7 — Ship plugin wiring + E2E exit criteria (bridge: authorization-gate)
**Status:** HARDENED (validated 2026-05-27 by phase-story-validator — significant rewrite required; see Validation notes below)
**Effort:** M (one operator action plus pre-flight scaffold authoring + per-branch cassette recording for S6-07; the executor cannot self-fulfill the recording — see Goal)
**Depends on:** S3-04 (CassetteSanitizer shipped), S3-05 (cassettes.lock + CI scanner shipped), S3-06 (CODEOWNERS + `make refresh-cassettes` ergonomic + `docs/operations/cassettes.md` runbook shipped — verified on master via S7-10 Attempt #1 of `docs/operations/cassettes.md`); S6-07, S7-06, S7-07 test files at Red phase with `pytest.mark.uses_anthropic_cassette` markers and the canonical cassette paths pinned (otherwise `make refresh-cassettes` collects zero tests and the recording session produces no cassettes — see Validation block B5/H-ordering)
**Unblocks:** S6-07 (determinism-cassette-replay property), S7-06 (E2E breaking-change), S7-07 (E2E replay-lands-RAG)

## Validation notes (2026-05-27)

`phase-story-validator` ran four parallel critics and identified three block-tier defects in the original draft. The story is being hardened in place; the shipped scaffolding (`tests/integration/test_s7_11_cassette_sets.py` + `tests/integration/test_s7_11_preflight.py`) **also requires realignment** as a follow-up code change (the bridge does not silently move that work; the realignment is the executor's first Red-step on this hardened story).

Block-tier defects fixed by this hardening pass:

- **B1 — Cassette path divergence.** Original AC-1/AC-2/AC-3 prescribed bridge-invented subdirs (`s6_07_determinism/*.yaml`, `s7_06_e2e_breaking_change/*.yaml`, `s7_07_e2e_replay_lands_rag/*.yaml`) that the downstream stories never read. S6-07 pins **four** branch cassettes at `tests/cassettes/anthropic/test_determinism/{rag_hit,rag_degraded,rag_miss,retry_bypass}/cassette.yaml` + a `recording_arch.json` sidecar per branch (S6-07 AC-BRANCH-1..4 + AC-PLATFORM-1). S7-06 pins a **single top-level file** `tests/cassettes/anthropic/test_phase4_e2e_breaking_change.yaml` (S7-06 AC-3). S7-07 pins a **single top-level file** `tests/cassettes/anthropic/test_phase4_e2e_replay_lands_rag.yaml` AND *reuses* S7-06's cassette as its baseline (S7-07 AC-4). The bridge invented a third naming scheme — Global Rule 7 says don't average; pick. Downstream is older and HARDENED → downstream wins.
- **B2 — Empty-file blindness.** Original example test passed if *any* `.yaml` existed. A zero-byte commit would mark the bridge GREEN while pushing yaml-parse failures downstream. Hardened ACs now require `verify_cassette` from `codegenie.fallback.cassette` to return `passed=True`, plus BLAKE3-against-`cassettes.lock` per-file (not text-grep).
- **B3 — AC-6 referenced a section that doesn't exist.** `docs/operations/cassettes.md` has no level-2 `## Rotation cadence` heading, and `tests/integration/test_ops_docs_exist.py` does *not* require `"Rotation cadence"` for cassettes.md (it requires `Refresh trigger matrix`, `make refresh-cassettes invocation`, `CODEOWNERS approval flow`, `BLAKE3 lock refresh`, `Sanitizer guarantees`). Rotation cadence is documented in `docs/operations/secrets.md`. AC-6 dropped; the rotation log lives in `secrets.md` per S3-06's design, not here.
- **B5 — Ordering bug.** `make refresh-cassettes` runs `pytest -m "uses_anthropic_cassette" --record-mode=all`. Today only `tests/unit/fallback/test_leaf_adapter_cassette_scenarios.py` carries that marker. S6-07/S7-06/S7-07 are HARDENED-not-GREEN — their test files do not exist on master. An operator running the original S7-11 would record nothing useful. Hardened **Depends on** adds: downstream stories' Red-phase test scaffolds with the marker on master *before* the recording session runs. This may mean S7-11 unblocks itself only after S6-07/S7-06/S7-07 reach Red — the bridge fires at the seam.

Harden-tier defects fixed:

- Token-spend estimate corrected from "≤ 4 calls" to **≥ 6 calls** (S6-07: 4 branches × 1 call; S7-06: 1 call; S7-07: 1 call — S7-07 *replays* S7-06's baseline rather than re-recording it). Per-call upper bound still bounded by `LlmInvocationGuard.per_call_max_tokens=32_000` (phase4-config.yaml).
- AC-1 acceptance test strengthened: per-branch parametrize, `verify_cassette(path).passed is True`, `recording_arch.json` sidecar exists and parses as `{machine, system, embedder_model_digest}`, cassette appears in `cassettes.lock` with BLAKE3 matching `compute_cassette_digest(path)`.
- AC-4 acceptance test strengthened from text-substring to per-file `compute_cassette_digest == lock_map[relpath]` round-trip (rejects "operator ran the recording but forgot `rebuild-lockfile`" silently passing).
- AC-7 acceptance test added: `test_audit_trail_has_recorded_row` parses this file's `## Audit trail` table and rejects all-`—` rows when `Status: Done`.
- Preflight strengthened: `load_lockfile` round-trip must succeed (not just file-exists), and a known-good fixture cassette must round-trip through `verify_cassette` (catches sanitizer regressions hiding behind import-succeeds).

Design-pattern notes (deferred):

- **No `CassetteBundleId` newtype.** Cassette subdir names are test-local fixtures, not domain IDs crossing module boundaries. CLAUDE.md's newtype rule targets domain identifiers in production code (probe IDs, warning IDs); promoting a one-shot bridge fixture path is ceremony with no caller.
- **No data-driven `_CASSETTE_BUNDLES` registry.** Bridge is one-shot. If a second bridge ever appears, *that* is the rule-of-three moment to extract a registry. Don't pre-build; surface the seam in this note.
- **Three-test-file collapse already done.** The shipped scaffolding uses a single parametrized file (`test_s7_11_cassette_sets.py`); the original story's "three near-identical files" prescription is stale and the realignment work below will simultaneously update parametrize ids to match downstream paths.

Verdict: **HARDENED**.

## Context

Phase 4's E2E exit-criterion stories (S6-07, S7-06, S7-07) cannot run in CI today because the Anthropic cassettes they replay do not exist on master. The cassette-recording path is operational (S3-04 sanitizer + S3-05 lock + S3-06 runbook + `make refresh-cassettes` + CODEOWNERS approval flow — all GREEN on master), but **executing it spends real Anthropic API tokens**. The executor cannot self-authorize that spend; CLAUDE.md §"Cassette workflow" makes the human-authorization gate explicit: *"Never run `pytest --record-mode=all` directly; always go through the make target so the explicit-acknowledgement gate fires."*

S6-07/S7-06/S7-07 have all been HARDENED for weeks; they're not blocked on engineering work, only on the human-authorization step that's deliberately not automated.

This story is the **bridge artifact**: one observable operator action + an acceptance check that the resulting cassettes flow through the pre-existing S3-04/S3-05/S3-06 discipline, after which S6-07/S7-06/S7-07 can run their full TDD plans without further bridge work.

## References — where to look

- **`docs/operations/cassettes.md`** — the runbook (shipped in S7-10 Attempt #1). Names the refresh-trigger matrix, the `make refresh-cassettes` invocation, the CODEOWNERS approval flow, the BLAKE3 lock-refresh discipline, and the `CassetteSanitizer` guarantees.
- **`Makefile` — `refresh-cassettes` target** (shipped in S3-06). Mandates `I_UNDERSTAND_THIS_SPENDS_TOKENS=1`; CODEGENIE_LIVE_LLM=1 environment plumbing.
- **`tests/cassettes/anthropic/cassettes.lock`** — BLAKE3 manifest (shipped in S3-05); the CI scanner `tests/security/test_cassettes_clean.py` checks every cassette against this.
- **S6-07 story** — determinism property over 50 cassette-replay runs.
- **S7-06 story** — E2E breaking-change test (express CVE major bump).
- **S7-07 story** — E2E replay-lands-RAG (second-run hits RAG, lower cost).

## Goal

The cassette-steward (per CODEOWNERS) runs **one** authorized recording session producing the six cassettes S6-07/S7-06/S7-07 need at the **exact paths those stories pin**; the recording flows through `CassetteSanitizer` (S3-04) + lands a refreshed `cassettes.lock` (S3-05) + passes `tests/security/test_cassettes_clean.py` (S3-05) + this story's hardened acceptance tests verifying each cassette is per-file `verify_cassette`-clean, BLAKE3-pinned in `cassettes.lock`, and (for S6-07's four branches) accompanied by a `recording_arch.json` sidecar matching S6-07 AC-PLATFORM-1.

**The executor cannot self-fulfill this story.** This story exists so a future operator can:
1. Read this file.
2. Run the documented commands.
3. Verify the acceptance tests pass.
4. Mark this story Done.
5. Resume S6-07/S7-06/S7-07 with their TDD plans now reachable.

## Acceptance criteria

- [ ] **AC-0 — Downstream Red-phase scaffolds exist.** Before the operator runs the recording session, the three downstream stories' test files exist on master and carry `pytest.mark.uses_anthropic_cassette`, with the cassette paths pinned exactly as AC-1/AC-2/AC-3 below name them. Without this, `make refresh-cassettes` (which collects `-m "uses_anthropic_cassette"`) produces no cassettes for the bridge. **Acceptance test:** `tests/integration/test_s7_11_preflight.py::test_downstream_recording_targets_collected` invokes `pytest --collect-only -m uses_anthropic_cassette` and asserts the collected set is a superset of `{s6_07_determinism (4 branches), s7_06_e2e_breaking_change, s7_07_e2e_replay_lands_rag}`. Loud-skip when the operator has not yet reached the bridge step (downstream stories still at HARDENED) — the skip reason names the missing tests.
- [ ] **AC-1 — S6-07 cassette set (4 branches + sidecars).** All four branch cassettes exist at the **canonical paths S6-07 reads** (S6-07 AC-BRANCH-1..4): `tests/cassettes/anthropic/test_determinism/{rag_hit,rag_degraded,rag_miss,retry_bypass}/cassette.yaml`. Each carries a sibling `recording_arch.json` matching S6-07 AC-PLATFORM-1's shape (`{machine, system, embedder_model_digest}`). **Acceptance test:** `tests/integration/test_s7_11_cassette_sets.py::test_s6_07_branch_cassettes_present_and_verified` is `@pytest.mark.parametrize`'d over the four branches and asserts, per branch: (a) `cassette.yaml` exists and `verify_cassette(path).passed is True` (S3-04 sanitizer round-trip); (b) `recording_arch.json` exists and parses as a dict with the three required keys, non-empty string values; (c) the cassette's `tests/cassettes/anthropic/test_determinism/{branch}/cassette.yaml` relpath appears in `load_lockfile(cassettes.lock)` with a BLAKE3 equal to `compute_cassette_digest(path)`. Loud-skip when the branch directory doesn't exist.
- [ ] **AC-2 — S7-06 single cassette.** **Canonical path S7-06 reads** (S7-06 AC-3): `tests/cassettes/anthropic/test_phase4_e2e_breaking_change.yaml` (single file, top-level). **Acceptance test:** `tests/integration/test_s7_11_cassette_sets.py::test_s7_06_cassette_present_and_verified` asserts: (a) file exists; (b) `verify_cassette(path).passed is True`; (c) the on-disk BLAKE3 equals `load_lockfile(cassettes.lock)[relpath]`. Loud-skip when the file doesn't exist.
- [ ] **AC-3 — S7-07 single cassette (reuses S7-06's baseline).** **Canonical path S7-07 reads** (S7-07 AC-4): `tests/cassettes/anthropic/test_phase4_e2e_replay_lands_rag.yaml` (single file, top-level). S7-07 *replays* S7-06's `test_phase4_e2e_breaking_change.yaml` for its baseline-cost first-run leg — it does **not** record a second cassette for the first run. **Acceptance test:** `tests/integration/test_s7_11_cassette_sets.py::test_s7_07_cassette_present_and_verified` mirrors AC-2's three checks for this path; additionally asserts the S7-06 baseline cassette (AC-2's path) is present in the same recording PR — otherwise S7-07 will fail at start-of-test with a missing-baseline diagnostic.
- [ ] **AC-4 — `cassettes.lock` per-file BLAKE3 round-trip.** Every newly recorded cassette under AC-1..AC-3 has an entry in `tests/cassettes/anthropic/cassettes.lock` whose digest equals `compute_cassette_digest(path)`. **Acceptance test:** `tests/integration/test_s7_11_cassette_sets.py::test_cassettes_lock_round_trips_each_recorded_cassette` enumerates the six canonical paths (4 S6-07 branches + 1 S7-06 + 1 S7-07), loads `cassettes.lock` via `load_lockfile`, and asserts per-file `lock_map[relpath] == compute_cassette_digest(path)` — failing with the `rebuild-lockfile` recovery hint per `docs/operations/cassettes.md §Troubleshooting`. Loud-skip when the recording session hasn't run.
- [ ] **AC-5 — CODEOWNERS approval recorded.** The recording PR is approved by the named cassette-steward per `.github/CODEOWNERS` (S3-06). Verifiable artifact: the merged PR's GitHub review-by attribution (`gh pr view <num> --json reviews`) names the steward's handle, AND a `Co-Authored-By:` or `Approved-By:` trailer appears in the merge commit. Acceptance: human-verifiable PR artifact (no automated pytest — branch-protection "Require review from Code Owners" is the enforcement).
- [ ] **AC-6 — Operator audit-trail entry in `## Audit trail` table.** The operator appends one row to the `## Audit trail` table at the bottom of this file with `(date, steward handle, token count, USD cost, cassette commit hash)`. Acceptance test: `tests/integration/test_s7_11_cassette_sets.py::test_audit_trail_has_recorded_row_when_status_done` parses this file; if `Status: Done`, asserts the `## Audit trail` table contains ≥ 1 data row whose date field parses as `datetime.date` (i.e., not the placeholder `—`).
- [ ] **AC-7 — Story status flip.** After AC-0..AC-6 are green, this story file's `Status:` flips to `Done`. Acceptance: the same `test_audit_trail_has_recorded_row_when_status_done` gating (AC-6) implicitly enforces that flipping `Status: Done` without an audit row is a failing CI signal.

## Implementation outline

Two-phase: the **executor** lands the hardened pre-flight + acceptance-test scaffolding (Red phase that loud-skips on a clean master); the **operator** (cassette-steward) runs the one-time recording session.

### Phase 1 — Executor work (no token spend)

1. **Realign shipped scaffolding to downstream paths.** The pre-validation scaffolding shipped at `tests/integration/test_s7_11_cassette_sets.py` parametrizes over bridge-invented subdirs (`s6_07_determinism/`, etc.). Rewrite it to parametrize over the **canonical downstream paths** from AC-0..AC-4. The hardened test file should:
   - Use `_REPO_ROOT / "tests" / "cassettes" / "anthropic"` as the root.
   - Provide a `_DOWNSTREAM_CASSETTES: Final[tuple[tuple[str, str, str], ...]]` table of `(relpath, story_id, ac_id)` for the six canonical paths (4 S6-07 branches + 1 S7-06 + 1 S7-07).
   - One `verify_cassette + lock-roundtrip` parametrized test for AC-1..AC-3.
   - One `recording_arch.json` parametrized test over only the 4 S6-07 branches (AC-1 sidecar leg).
   - One `cassettes.lock` per-file BLAKE3 round-trip test (AC-4).
   - One `audit-trail-row-when-status-done` text-parse test (AC-6/AC-7).
2. **Strengthen `tests/integration/test_s7_11_preflight.py`.** Beyond import-succeeds / file-exists:
   - `load_lockfile(_CASSETTES_LOCK)` returns a `MappingProxyType[CassetteId, BlobDigest]` without raising `LockfileMalformed` (catches "lock is one byte" passing).
   - A known-good fixture cassette (the leaf-adapter scenarios cassette at `tests/cassettes/anthropic/test_leaf_adapter_cassette_scenarios.yaml` or similar) round-trips through `verify_cassette` returning `passed=True` (catches "sanitizer imports but is broken").
   - Add `test_downstream_recording_targets_collected` (AC-0) that runs `pytest --collect-only -m uses_anthropic_cassette` and asserts the collected test IDs are a superset of the six canonical S6-07/S7-06/S7-07 cassette-recording tests; loud-skip when downstream stories are still at HARDENED.
3. **Commit the realignment** as a single PR that lands the Red-phase scaffolding for the operator.

### Phase 2 — Operator action (token spend)

(NOT executor-runnable; gated by `I_UNDERSTAND_THIS_SPENDS_TOKENS=1` per ADR-0014 §Decision item 6.)

4. **Operator action — pre-flight before spending tokens:**
   ```bash
   .venv/bin/pytest -q tests/integration/test_s7_11_preflight.py
   ```
   All preflight tests must pass (no loud-skips reaching AC-0 — downstream tests are collected). Loud-skips above this line mean the operator is *not* yet at the bridge step.
5. **Operator action — authorized recording:**
   ```bash
   export ANTHROPIC_API_KEY=$(keyring get codegenie anthropic_api_key)
   make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1 CODEGENIE_LIVE_LLM=1
   ```
   This invocation collects `-m "uses_anthropic_cassette"` (the marker the downstream Red-phase tests carry); routes the leaf-LLM calls through `pytest-recording` + `CassetteSanitizer`; writes the **six** cassettes at the canonical paths AC-1..AC-3 name; recomputes BLAKE3 + writes to `cassettes.lock` via `python -m codegenie cassette rebuild-lockfile` (the Makefile target chains both). Expected ≥ 6 Anthropic API calls (see Notes-for-implementer for the breakdown).
6. **Operator action — author the S6-07 sidecars by hand.** `pytest-recording` does not produce `recording_arch.json` — the operator writes one per branch directory using:
   ```python
   import json, platform
   sidecar = {"machine": platform.machine(), "system": platform.system(), "embedder_model_digest": "<from .codegenie/rag/manifest.yaml>"}
   ```
   The `embedder_model_digest` comes from the current Phase-4 RAG manifest (per ADR-0007).
7. **Operator action — review the diff:** verify every new cassette under `tests/cassettes/anthropic/` is sanitized (the S3-04 hooks ran — body grep for `sk-ant-` / `claude_` / `Authorization:` must be empty); verify `cassettes.lock` covers every new cassette.
8. **Operator action — sanitizer self-test:** `pytest tests/unit/fallback/test_cassette_sanitizer.py` verifies the sanitize-idempotence property on the new cassettes (catches Anthropic-SDK-emits-new-header-shape regressions).
9. **Operator action — append the audit-trail row + flip status:** append a row to `## Audit trail` with the recording date (ISO `YYYY-MM-DD`), steward handle, token count, USD cost, and the cassette commit hash; flip `Status: HARDENED` → `Status: Done`.
10. **Operator action — run the bridge gates:** `pytest tests/integration/test_s7_11_*.py` — all of AC-0..AC-4 + AC-6 + AC-7 must be green (AC-5 is the PR review).
11. **Operator action — open downstream stories:** with cassettes now on master, S6-07 / S7-06 / S7-07 are unblocked for the executor.

## TDD plan — preflight + acceptance scaffolding

Single parametrized acceptance file (`tests/integration/test_s7_11_cassette_sets.py`) covering AC-0..AC-4 + AC-6/AC-7. Loud-skips when cassettes absent so a clean master stays green; un-skips automatically once the operator records.

```python
# tests/integration/test_s7_11_cassette_sets.py
"""S7-11 AC-0..AC-4 + AC-6/AC-7 — cassette-set presence, sanitizer-clean,
BLAKE3-lock round-trip, and audit-trail enforcement.

The shipped cassette paths are the canonical paths that S6-07/S7-06/S7-07
themselves read — this bridge does not invent a third naming scheme. See
docs/phases/04-vuln-llm-fallback-rag/stories/S6-07-* AC-BRANCH-1..4 +
AC-PLATFORM-1, S7-06 AC-3, S7-07 AC-4.
"""
from __future__ import annotations
import json
import re
from datetime import date
from pathlib import Path
from typing import Final

import pytest

from codegenie.fallback.cassette import (
    compute_cassette_digest,
    load_lockfile,
    verify_cassette,
)

_REPO_ROOT = Path(__file__).parents[2]
_CASSETTES_ROOT = _REPO_ROOT / "tests" / "cassettes" / "anthropic"
_LOCK = _CASSETTES_ROOT / "cassettes.lock"
_STORY = _REPO_ROOT / "docs" / "phases" / "04-vuln-llm-fallback-rag" / "stories" / "S7-11-cassette-authorization-bridge.md"

# Six canonical cassette paths the bridge must produce — exactly the
# paths S6-07/S7-06/S7-07 read.
_S6_07_BRANCHES: Final[tuple[str, ...]] = ("rag_hit", "rag_degraded", "rag_miss", "retry_bypass")
_DOWNSTREAM_CASSETTES: Final[tuple[tuple[str, str, str], ...]] = (
    *(
        (f"test_determinism/{b}/cassette.yaml", "S6-07", f"AC-1 ({b})")
        for b in _S6_07_BRANCHES
    ),
    ("test_phase4_e2e_breaking_change.yaml", "S7-06", "AC-2"),
    ("test_phase4_e2e_replay_lands_rag.yaml", "S7-07", "AC-3"),
)


@pytest.mark.parametrize(("relpath", "story_id", "ac_id"), _DOWNSTREAM_CASSETTES)
def test_cassette_present_sanitized_and_lock_pinned(relpath: str, story_id: str, ac_id: str) -> None:
    """AC-1/AC-2/AC-3 — for each canonical cassette: (a) exists on disk,
    (b) `verify_cassette(path).passed is True` (S3-04 sanitizer round-trip
    — rejects empty files, malformed YAML, leaked secrets), (c) `cassettes.lock`
    entry's BLAKE3 == `compute_cassette_digest(path)` (rejects "operator
    forgot rebuild-lockfile").
    """
    path = _CASSETTES_ROOT / relpath
    if not path.exists():
        pytest.skip(
            f"S7-11 {ac_id}: {story_id} cassette not yet recorded at "
            f"{path}. Operator path: see this story's Implementation outline §Phase 2."
        )
    result = verify_cassette(path)
    assert result.passed, f"S7-11 {ac_id}: sanitizer rejected cassette {relpath}: {result}"
    lock_map = load_lockfile(_LOCK)
    assert relpath in lock_map, (
        f"S7-11 {ac_id}: cassette {relpath} on disk but not in cassettes.lock. "
        f"Run `python -m codegenie cassette rebuild-lockfile`."
    )
    assert lock_map[relpath] == compute_cassette_digest(path), (
        f"S7-11 {ac_id}: cassette {relpath} digest mismatches lockfile. "
        f"Operator must re-run rebuild-lockfile after editing cassettes."
    )


@pytest.mark.parametrize("branch", _S6_07_BRANCHES)
def test_s6_07_branch_recording_arch_sidecar_present(branch: str) -> None:
    """AC-1 sidecar leg — S6-07 AC-PLATFORM-1 requires a
    `recording_arch.json` next to each branch's `cassette.yaml`."""
    sidecar = _CASSETTES_ROOT / "test_determinism" / branch / "recording_arch.json"
    if not sidecar.exists():
        pytest.skip(
            f"S7-11 AC-1 ({branch}): recording_arch.json not yet authored. "
            f"Operator path: see this story's Implementation outline §Phase 2 step 6."
        )
    payload = json.loads(sidecar.read_text())
    for key in ("machine", "system", "embedder_model_digest"):
        assert isinstance(payload.get(key), str) and payload[key], (
            f"S7-11 AC-1 ({branch}): recording_arch.json missing or empty key {key!r}"
        )


def test_cassettes_lock_round_trips_each_recorded_cassette() -> None:
    """AC-4 — every cassette recorded under AC-1..AC-3 has a
    `cassettes.lock` entry whose BLAKE3 matches the on-disk file.
    Stronger than the existing tests/security/test_cassettes_clean.py
    scanner because that scanner walks file-system-first; this one
    walks the SIX expected canonical paths and fails on a missing
    lock entry where the scanner would silently skip."""
    recorded = [
        (rel, _CASSETTES_ROOT / rel)
        for (rel, _, _) in _DOWNSTREAM_CASSETTES
        if (_CASSETTES_ROOT / rel).exists()
    ]
    if not recorded:
        pytest.skip("No bridge cassettes recorded yet — AC-4 unreachable.")
    lock_map = load_lockfile(_LOCK)
    for relpath, path in recorded:
        assert lock_map.get(relpath) == compute_cassette_digest(path), (
            f"S7-11 AC-4: digest mismatch for {relpath}. Run rebuild-lockfile."
        )


_AUDIT_ROW_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*\S.*\|\s*\d+", re.MULTILINE,
)


def test_audit_trail_has_recorded_row_when_status_done() -> None:
    """AC-6 + AC-7 — when this story's Status is Done, the
    `## Audit trail` table must contain ≥ 1 data row whose date
    field parses as `datetime.date`. Catches "flip status without
    appending audit row" failure mode."""
    body = _STORY.read_text()
    if "Status: Done" not in body:
        pytest.skip(
            "S7-11 not yet flipped to Status: Done — audit-trail row "
            "assertion only applies after the recording session lands."
        )
    audit_section = body.split("## Audit trail", 1)[-1]
    matches = _AUDIT_ROW_PATTERN.findall(audit_section)
    assert matches, (
        "S7-11 AC-6/AC-7: Status: Done but no audit-trail row with an "
        "ISO date + non-empty steward + token count was found. The "
        "operator must append a row before flipping status."
    )
    for iso in matches:
        date.fromisoformat(iso)  # raises if malformed
```

The preflight file (`tests/integration/test_s7_11_preflight.py`) gains three load-bearing checks per the Implementation outline §Phase 1 step 2:

```python
def test_lockfile_round_trips() -> None:
    """Catches 'cassettes.lock exists but is malformed' — load_lockfile
    raises LockfileMalformed on any non-conformant line."""
    lock_map = load_lockfile(_CASSETTES_LOCK)
    assert isinstance(lock_map, type(MappingProxyType({})))


def test_known_good_cassette_verifies() -> None:
    """Round-trip a shipped fixture cassette through verify_cassette;
    catches a sanitizer regression that imports cleanly but rejects
    everything."""
    known_good = next(_CASSETTES_ROOT.glob("test_leaf_adapter*.yaml"), None)
    if known_good is None:
        pytest.skip("Phase-4 leaf-adapter scenarios cassette not present — "
                    "S3-02 marker tests not yet on master.")
    assert verify_cassette(known_good).passed


def test_downstream_recording_targets_collected() -> None:
    """AC-0 — `make refresh-cassettes` collects `-m uses_anthropic_cassette`.
    If S6-07/S7-06/S7-07's Red-phase tests aren't on master with that
    marker + the canonical cassette paths pinned, the recording
    session produces no cassettes. Loud-skip in pre-bridge state;
    fail-loud if the operator is about to spend tokens with an empty
    collection."""
    # Implementation: subprocess pytest --collect-only -m uses_anthropic_cassette
    # and assert collected-id-set is a superset of the six canonical recordings.
    ...  # See Implementation outline §Phase 1 step 2.
```

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_s7_11_preflight.py` | Modify — strengthen with `load_lockfile` round-trip + known-good `verify_cassette` round-trip + AC-0 `test_downstream_recording_targets_collected`. |
| `tests/integration/test_s7_11_cassette_sets.py` | Modify — realign parametrize table to the **six canonical downstream paths**; add `verify_cassette` + per-file BLAKE3 round-trip; add `recording_arch.json` sidecar parametrize over the four S6-07 branches; add `test_audit_trail_has_recorded_row_when_status_done` (AC-6/AC-7). |
| `tests/cassettes/anthropic/test_determinism/{rag_hit,rag_degraded,rag_miss,retry_bypass}/cassette.yaml` | Operator-recorded under AC-1 (four files). |
| `tests/cassettes/anthropic/test_determinism/{rag_hit,rag_degraded,rag_miss,retry_bypass}/recording_arch.json` | Operator-authored under AC-1 (four sidecars; see Implementation outline §Phase 2 step 6). |
| `tests/cassettes/anthropic/test_phase4_e2e_breaking_change.yaml` | Operator-recorded under AC-2 (single top-level file). |
| `tests/cassettes/anthropic/test_phase4_e2e_replay_lands_rag.yaml` | Operator-recorded under AC-3 (single top-level file). |
| `tests/cassettes/anthropic/cassettes.lock` | Operator-refreshed under AC-4 (S3-05). |
| `docs/phases/04-vuln-llm-fallback-rag/stories/S7-11-cassette-authorization-bridge.md` | This file — status flip + audit-trail row under AC-6/AC-7. |

**Note on `s6_07_determinism/` etc.:** The pre-validation scaffolding's bridge-invented subdirs (`tests/cassettes/anthropic/{s6_07_determinism,s7_06_e2e_breaking_change,s7_07_e2e_replay_lands_rag}/*.yaml`) are **not** the canonical paths. Validation block B1 flagged that S6-07/S7-06/S7-07 read **different** paths. The realignment work in Implementation outline §Phase 1 step 1 retires the bridge subdirs and replaces them with the canonical downstream paths above. Any cassettes the operator may already have produced under the old subdirs must be re-recorded at the canonical paths (the bridge subdirs should be deleted before the recording session).

## Out of scope

- Re-implementing the cassette pipeline. S3-04/S3-05/S3-06 already shipped everything; S7-11 is a bridge story, not a re-implementation.
- Automating the token-spend authorization. CLAUDE.md §"Cassette workflow" explicitly mandates the human-acknowledgement gate; bypassing it is an ADR-level decision.
- The downstream story executions themselves (S6-07/S7-06/S7-07). Those have their own TDD plans; S7-11 unblocks them, doesn't replace them.

## Notes for the implementer (executor + operator)

- **Token spend estimate (corrected).** **≥ 6 Anthropic API calls**, broken out:
  - S6-07 — 4 calls (one per branch: rag_hit, rag_degraded, rag_miss, retry_bypass). The 50-iteration property *replays* a single cassette per branch; the recording is one call per branch's seeded prompt-and-store state.
  - S7-06 — 1 call (one major-bump CVE plan-and-trust cycle).
  - S7-07 — 1 call (the rerun-with-seed-in-store recording; the baseline-cost first-leg *replays* S7-06's cassette per S7-07 Context option (a), it does not re-record).
  Per-call upper bound bounded by `LlmInvocationGuard.per_call_max_tokens=32_000` (phase4-config.yaml). Expected total cost: under $2 with current Anthropic Sonnet 4.6 pricing — well within `LlmInvocationGuard.running_total` discipline.
- **Design-pattern decisions deferred (do not extract).**
  - *No `CassetteBundleId` newtype.* Cassette subdir names are test-local fixtures, not domain IDs flowing through registries or probe contracts. CLAUDE.md's newtype rule targets cross-module domain IDs (probe IDs, warning IDs); promoting a one-shot bridge fixture path is ceremony with no caller. If cassette-bundle IDs ever flow through an Open/Closed seam (e.g., a `@register_cassette_bundle(...)` registry wiring downstream replays), promote then.
  - *No `_CASSETTE_BUNDLES` registry.* The six canonical paths live in one `_DOWNSTREAM_CASSETTES` `Final` tuple inside this test file — that *is* the data-driven shape, scoped to one file. If a second bridge story ever appears (Phase 6+ adds another LLM-touching set of cassettes), *that* is the rule-of-three moment to extract a shared module-level registry under `tests/_fixtures/`. Don't pre-build.
- **Steward rotation.** Per `docs/operations/cassettes.md §CODEOWNERS approval flow`, the cassette-steward role rotates quarterly. The recording session counts as one steward turn; record it in the rotation log.
- **Sanitizer self-test.** Before pushing the recording PR, the operator runs `pytest tests/unit/fallback/test_cassette_sanitizer.py` to verify the sanitizer's idempotence property (sanitize ∘ sanitize ≡ sanitize) holds on the new cassettes. This catches a regression where a future Anthropic SDK upgrade emits a header shape the sanitizer doesn't strip.
- **Reverse-bridge:** if the recording session reveals that S6-07/S7-06/S7-07's TDD plans need adjustment (e.g., a fixture's hand-authored `package.json` doesn't trigger the expected CVE detection path), the operator opens a sibling story rather than amending S7-11. S7-11's success criterion is exactly the four operator actions producing the four sets of artifacts; downstream TDD adjustments are downstream stories' concerns.

## Audit trail

*(Operator appends here after the recording session completes.)*

| Date | Steward | Token count | USD cost | Cassette commit hash |
|---|---|---|---|---|
| — | — | — | — | — |
