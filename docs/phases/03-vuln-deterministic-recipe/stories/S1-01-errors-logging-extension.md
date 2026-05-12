# Story S1-01 — Errors + structlog event constants for Phase 3

**Step:** Step 1 — Plant the two ABCs, the four Phase 0/1/2 additive edits, and the foundations every Phase 3 component consumes
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0001, ADR-0003, ADR-0004, ADR-0005, ADR-0007, ADR-0008, ADR-0010

## Context

Phase 3 introduces two new ABCs (`Transform`, `RecipeEngine`), the CVE feed surface, the `LockfilePolicyScanner`, the `ValidationGate`, the `PatchBranchWriter`, and 17 new audit event types. Every one of those raise/log sites needs a typed exception and a registered structlog event-name constant *before* the implementations land — otherwise every other Step 1 story (and Steps 2–7) introduces ad-hoc error strings and divergent log keys that drift in review. This story is the prerequisite for every other Step 1 story; nothing else compiles cleanly until the names exist.

Phase 0 ships `CodegenieError` with its initial subclasses; Phase 1 and Phase 2 each extended additively (Phase 2 added the nine tool/sandbox/skills/audit subclasses per Phase 2 S1-01). Phase 3 follows the same pattern — append-only extension, no edits to existing subclasses or constants.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Agentic best practices" → "Error escalation"` — naming convention and the rule that `CodegenieError` itself is unchanged.
  - `../phase-arch-design.md §"Component design" #14 "Audit chain — Phase-3 event extensions"` — the 17 new event-type names this story registers as structlog constants.
  - `../phase-arch-design.md §"Component design" #2 (RecipeEngine)` — `EngineUnavailable` raise site; `#5 (LockfileResolver)` — `LockfileResolveFailed`, `LockfileMalformed`; `#7 (CveFeedSyncer)` — `CveSnapshotCorrupt`, `CveSignatureMismatch`, `AdvisoryNotInStore`; `#13 (PatchBranchWriter)` — `WorkingTreeNotClean`, `BranchExists`.
- **Phase ADRs:**
  - `../ADRs/0001-transform-recipe-engine-two-abc-contract.md` — ADR-0001 — `TransformError` is the boundary type wrapping engine/validator faults caught by the coordinator (per `phase-arch-design.md §"Component design" #1` "Failure behavior").
  - `../ADRs/0003-recipe-engine-ncu-default-openrewrite-stub-registered.md` — ADR-0003 — `EngineUnavailable` raised when an engine's preflight fails *and* the selector did not already short-circuit via `RecipeSelection(reason="no_engine")`.
  - `../ADRs/0004-recipe-selection-structured-triple-not-optional.md` — ADR-0004 — `RecipeNotInDigestManifest` raised at recipe load time when `recipes/digests.yaml` lacks a digest pin for a catalog entry.
  - `../ADRs/0005-single-sandbox-profile-test-execution-overlay-signal-escalate.md` — ADR-0005 — `NpmScriptsEnabled` is the wrapper-level guard exception when `--ignore-scripts` is dropped outside the test-execution overlay.
  - `../ADRs/0007-lockfile-policy-scanner-graded-allow-policy-violations.md` — ADR-0007 — `LockfileResolveFailed`, `LockfileMalformed` raise sites.
  - `../ADRs/0008-cve-feed-integrity-content-hash-best-effort-signature-graded-staleness.md` — ADR-0008 — `CveSnapshotCorrupt` is hard-fail; `CveSignatureMismatch` is recorded into `Provenance.signature_verified` and *not* raised (best-effort posture); document this in the docstring.
  - `../ADRs/0010-audit-chain-extension-cache-replay-event.md` — ADR-0010 — the 17 event-type names this story registers as `Final[str]` constants.
- **Production ADRs:** `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — the per-binary / per-event ADR-justification precedent this story inherits.
- **Source design:** `../final-design.md §"Trust & safety goals" #15` — the closed event vocabulary; `§"Failure modes & recovery"` — every Phase 3 raise site maps to one of the 11 new typed exceptions.
- **Existing code:**
  - `src/codegenie/errors.py` (Phase 0 + Phase 1 + Phase 2 extensions) — append only; do not edit existing subclasses.
  - `src/codegenie/logging.py` (Phase 0 + Phase 2 event constants) — append only; do not edit existing constants.
  - `tests/unit/test_errors.py`, `tests/unit/test_logging.py` — extend `EXPECTED_SUBCLASSES` / event-name sets.

## Goal

Extend `src/codegenie/errors.py` with 11 new `CodegenieError` subclasses and `src/codegenie/logging.py` with the 17 Phase-3 audit-event-name constants plus four new structured-field constants (`cve_id`, `recipe_id`, `engine_name`, `run_id`) plus the `phase3.fence.violation` event, so every Step 1–7 story has the named primitives it raises and logs into.

## Acceptance criteria

- [ ] `src/codegenie/errors.py` exports the 11 new subclasses: `NpmScriptsEnabled`, `RecipeNotInDigestManifest`, `CveSnapshotCorrupt`, `CveSignatureMismatch`, `AdvisoryNotInStore`, `WorkingTreeNotClean`, `BranchExists`, `LockfileResolveFailed`, `LockfileMalformed`, `TransformError`, `EngineUnavailable`; each inherits from `CodegenieError`; each is in `errors.__all__`.
- [ ] Each subclass `__init__` is keyword-only and carries the exception-specific fields named in `phase-arch-design.md §"Component design"` (e.g., `LockfileResolveFailed(*, package: str, exit_code: int, stderr_excerpt: str)`; `CveSnapshotCorrupt(*, source: str, expected_sha256: str, actual_sha256: str)`; `BranchExists(*, branch_name: str)`; `WorkingTreeNotClean(*, repo_root: Path, dirty_paths: list[Path])`; `EngineUnavailable(*, engine_name: str, reason: str)`; `TransformError(*, transform_name: str, wrapped_class: str, detail: str)`; `NpmScriptsEnabled(*, argv: tuple[str, ...])`; `RecipeNotInDigestManifest(*, recipe_id: str)`; `AdvisoryNotInStore(*, cve_id: str, source: str)`; `CveSignatureMismatch(*, source: str, key_id: str | None, detail: str)`; `LockfileMalformed(*, path: Path, detail: str)`).
- [ ] `CveSignatureMismatch`'s docstring explicitly states it is **best-effort**: recorded as `Provenance.signature_verified=False` rather than raised in the happy `cve sync` path; only raised if an operator requests strict signature mode in a future ADR amendment. The class is defined so call sites have a typed handle when strict mode lands.
- [ ] `TransformError`'s docstring states it is the boundary type the coordinator wraps engine/validator exceptions in before writing `TransformOutput(confidence="low", errors=[...])`; never raised by the ABC itself (`phase-arch-design.md §"Component design" #1` "Failure behavior").
- [ ] `src/codegenie/logging.py` defines `Final[str]` constants — one per audit event listed in `phase-arch-design.md §"Component design" #14`, with string values matching that table verbatim. The full set: `CVE_FEED_SYNCED`, `CVE_FEED_SIGNATURE_CHECK`, `CVE_RETRACTION_DETECTED`, `EVIDENCE_STALE_MARKED`, `RECIPE_SELECTED`, `RECIPE_ENGINE_INVOKED`, `TRANSFORM_APPLIED`, `LOCKFILE_SCANNED`, `LOCKFILE_POLICY_VIOLATION`, `NPM_INSTALL_RUN`, `TESTS_EXECUTED`, `GATE_FAILED`, `GATE_SIGNAL_ESCALATE`, `BRANCH_CREATED`, `BRANCH_REFUSED_DIRTY_TREE`, `BRANCH_REFUSED_EXISTS`, `CACHE_REPLAY`. (17 audit events.)
- [ ] `src/codegenie/logging.py` defines additional `Final[str]` constants `PHASE3_FENCE_VIOLATION = "phase3.fence.violation"` and the four new structured-field constants `FIELD_CVE_ID = "cve_id"`, `FIELD_RECIPE_ID = "recipe_id"`, `FIELD_ENGINE_NAME = "engine_name"`, `FIELD_RUN_ID = "run_id"`.
- [ ] `tests/unit/test_errors.py` extends `EXPECTED_SUBCLASSES` with the 11 new names; asserts each is in `__all__`; one attribute-round-trip test per class.
- [ ] `tests/unit/test_logging.py` extends with assertions on every new event constant + field constant, including verbatim string equality.
- [ ] No Phase 0/1/2 subclass or constant is edited; the diff is append-only on both files.
- [ ] The TDD red test exists, is committed in the red state on a tagged commit, and the green commit brings it green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Extend `tests/unit/test_errors.py` first (red) — append the 11 new names to `EXPECTED_PHASE3_SUBCLASSES`; add one attribute-round-trip test per class (including the strict-vs-best-effort docstring assertion for `CveSignatureMismatch`).
2. Extend `tests/unit/test_logging.py` (red) — assert the 17 audit event constants + `PHASE3_FENCE_VIOLATION` + four field constants exist and equal the documented strings.
3. Append the 11 subclasses to `src/codegenie/errors.py` under a `# Phase 3 — additive` block. Each subclass:
   - One-line docstring naming its raise site (e.g., `"""Raised by tools/npm.py when --ignore-scripts is missing outside the test-execution overlay (ADR-0005)."""`).
   - Keyword-only `__init__` storing typed attributes; `super().__init__(f"<context>: <detail>")` for `str(exc)` rendering.
4. Append the 17 audit-event constants + `PHASE3_FENCE_VIOLATION` + four field constants to `src/codegenie/logging.py` under a `# Phase 3 — additive` block.
5. Extend `__all__` on both files (alphabetical re-sort permitted — Rule 3 carve-out same as Phase 2 S1-01).
6. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/errors.py src/codegenie/logging.py tests/unit/test_errors.py tests/unit/test_logging.py`, `pytest tests/unit/test_errors.py tests/unit/test_logging.py`.

## TDD plan — red / green / refactor

### Red — failing test first

Test file paths: `tests/unit/test_errors.py` (extend) and `tests/unit/test_logging.py` (extend).

```python
# tests/unit/test_errors.py — Phase 3 extension
import codegenie.errors as e

EXPECTED_PHASE3_SUBCLASSES = {
    "NpmScriptsEnabled", "RecipeNotInDigestManifest", "CveSnapshotCorrupt",
    "CveSignatureMismatch", "AdvisoryNotInStore", "WorkingTreeNotClean",
    "BranchExists", "LockfileResolveFailed", "LockfileMalformed",
    "TransformError", "EngineUnavailable",
}

def test_phase3_subclasses_present_and_in_all():
    # every Phase 3 subclass is a CodegenieError and exported in __all__
    ...

def test_cve_snapshot_corrupt_carries_expected_and_actual_sha256():
    # CveSnapshotCorrupt is hard-fail (ADR-0008); both hashes must round-trip
    ...

def test_cve_signature_mismatch_docstring_is_best_effort():
    # documents that this class exists for forward-compat; not raised in the
    # happy sync path; recorded as Provenance.signature_verified=False instead
    ...

def test_transform_error_documents_coordinator_wrapping_contract():
    # docstring asserts this is the wrap-once boundary type used by the
    # coordinator per phase-arch-design.md §"Component design" #1
    ...
```

```python
# tests/unit/test_logging.py — Phase 3 extension
import codegenie.logging as L

def test_phase3_audit_event_constants_present_with_documented_strings():
    assert L.CVE_FEED_SYNCED == "cve.feed.synced"
    assert L.RECIPE_SELECTED == "recipe.selected"
    assert L.GATE_SIGNAL_ESCALATE == "gate.signal_escalate"
    assert L.CACHE_REPLAY == "cache.replay"
    # ... (all 17)

def test_phase3_field_constants_present():
    assert L.FIELD_CVE_ID == "cve_id"
    assert L.FIELD_RECIPE_ID == "recipe_id"
    assert L.FIELD_ENGINE_NAME == "engine_name"
    assert L.FIELD_RUN_ID == "run_id"

def test_phase3_fence_violation_event_constant_present():
    assert L.PHASE3_FENCE_VIOLATION == "phase3.fence.violation"
```

Run; confirm `AttributeError` on every new name. Commit as red marker.

### Green — make it pass

Append the 11 subclasses + the 17 audit event constants + the 4 field constants + `PHASE3_FENCE_VIOLATION` to the two modules. Each subclass shape mirrors Phase 2's `ToolNonZeroExit` precedent (keyword-only, typed attributes, formatted `super().__init__`).

### Refactor — clean up

- Module-level docstrings on both files extended with a "Phase 3 additive extension per ADR-0001/0003/0004/0005/0007/0008/0010" note.
- `__all__` re-sorted alphabetical (per Phase 2 S1-01 precedent).
- Confirm `mypy --strict` is clean — each `__init__` is keyword-only, attributes typed, `super().__init__(...)` carries the formatted message.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/errors.py` | Append 11 subclasses; extend `__all__` |
| `src/codegenie/logging.py` | Append 17 audit event constants + 4 field constants + `PHASE3_FENCE_VIOLATION`; extend `__all__` |
| `tests/unit/test_errors.py` | Extend `EXPECTED_SUBCLASSES`; add attribute round-trip tests |
| `tests/unit/test_logging.py` | Add presence + value assertions for new constants |

## Out of scope

- **Raising the new exceptions from production code** — those raise sites land in the consuming stories (S1-02, S1-06, S1-07, S2-06, S2-07, S2-08, S3-*, S4-*, S5-*). This story is the type definitions only.
- **Emitting the new event constants in production code** — emissions land in the consuming stories (e.g., `RECIPE_SELECTED` in S3-08; `CACHE_REPLAY` in S3-07; `BRANCH_CREATED` in S5-04).
- **Pydantic event payload schemas** — those land in `src/codegenie/audit/events.py` in **S1-07**. This story only registers the *event names* as structlog constants.
- **Re-exporting from `codegenie/__init__.py`** — Phase 0 does not re-export `errors` or `logging`; do not start.
- **`audit_writer.py` event-type enum extension** — that one-line additive edit lands in S1-07.

## Notes for the implementer

- Keyword-only `__init__` (`def __init__(self, *, ...)`) is mandatory across all 11 — Phase 2 S1-01 established this; Phase 3 conforms (Rule 11).
- `CveSignatureMismatch` is the only subclass whose **happy-path use is non-raising**. The class exists so a future "strict-signature" ADR can land without an errors-module PR. Document this explicitly; otherwise a future implementer will wire it as a hard fail in S2-07 and break ADR-0008's "best-effort signature" posture (`§"Decision"` paragraph 2).
- `TransformError` is named like a base exception but is the **boundary wrap** at the coordinator. The coordinator catches engine/validator exceptions once and wraps them as `TransformError(transform_name=..., wrapped_class=type(exc).__name__, detail=...)` before writing the `TransformOutput`. Document this contract in the class docstring; otherwise S5-02's coordinator implementer will be tempted to add subclasses (Rule 3 violation).
- `WorkingTreeNotClean.dirty_paths` and `LockfileMalformed.path` are `pathlib.Path` — not strings. Stay typed. The structlog renderer will str-coerce at emit time.
- `stderr_excerpt` on `LockfileResolveFailed` is the **first 4 KiB** of stderr — the raise site (S3-06) truncates before constructing. Do not store unbounded stderr; this matches Phase 2's `ToolNonZeroExit` discipline.
- The 17 audit event constants live alongside the eight Phase 2 constants from S1-01 of Phase 2 — do **not** edit those; append under a clearly delimited block comment.
- Resist the urge to pre-add a 12th subclass or an 18th event name. The set comes verbatim from `phase-arch-design.md §"Component design" #14` and the 11 raise sites enumerated across ADRs 0003–0010. Any addition belongs in its consuming story, not here.
