# Story S1-06 — `ProbeContext` extension: `parsed_manifest` + `input_snapshot`

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Ready (validator-hardened 2026-05-14)
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0002 (this phase, amended in this story), Phase 0 ADR-0007

## Validation notes

Hardened 2026-05-14 by `phase-story-validator`. Full report: [`_validation/S1-06-probe-context-extension.md`](_validation/S1-06-probe-context-extension.md). Five block-tier defects and twelve harden-tier gaps corrected; ACs expanded from 10 → 18; TDD plan rewritten with ~14 named tests each annotated with the mutation it catches.

Key reshapes vs. the original draft:

- **Script path corrected** — actual file is `scripts/regen_probe_contract_snapshot.py`, snapshot is `tests/snapshots/probe_contract.v1.json`.
- **`InputFingerprint` moved into `base.py`** (was `src/codegenie/coordinator/input_snapshot.py`). It is a contract type, lives with the contract; this preserves the stdlib-only fence on `base.py` (pinned by `test_base_py_imports_are_stdlib_only`) and respects DIP (contract types do not depend on worker packages).
- **`parsed_manifest` callable narrowed at the boundary** to `Mapping[str, Any]` (not `Mapping[str, JSONValue]`). `JSONValue` lives in `coordinator/validator.py` and importing it cycles; Phase 0 precedent (`RepoSnapshot.config`, `ProbeContext.config`, `ProbeOutput.schema_slice`) uses `Any` at the contract boundary. `_ProbeOutputValidator` re-narrows downstream.
- **`CODEOWNERS` edit removed** — collides with the existing `TODO(S5-02): CODEOWNERS entry required` in `base.py` and the Phase-0 invariant `test_base_py_carries_codeowners_todo_for_s5_02`. CODEOWNERS routing is S5-02's job; S1-06 preserves the TODO.
- **"Third future field fails CI" sentinel moved from script to test** — `ALLOWED_PROBECONTEXT_FIELDS` as a script-side constant didn't exist and would duplicate work done by `structural_signature(...)`. The dedicated test `test_probe_context_field_list_matches_adr_0002_amendment` in `tests/unit/test_probe_contract.py` is now the explicit ADR-0002 sentinel (Open/Closed at the file boundary: a contract change is a *test change* and a *snapshot change*, gated by ADR-0002).
- **`localv2.md §4` doc-update AC added** — per Phase-0 ADR-0007 ("code matches doc, never the inverse"), the §4 `ProbeContext` block must be amended in the same PR; the `doc_fingerprint` half of the snapshot then re-matches.
- **`ALLOWED_BASE_PY_IMPORTS` widening AC added** — `{"abc", "dataclasses", "logging", "pathlib", "typing"} + {"collections"}` to admit `from collections.abc import Callable, Mapping`. Pinned by a dedicated test so a future revert is a loud regression.
- **ADR-0002 amendment AC added** — ADR-0002's Decision section currently names only `parsed_manifest`; `input_snapshot` must be documented in the same PR.

## Context

`ProbeContext` is the only Phase 0 frozen-contract dataclass that Phase 1 amends. ADR-0002 (this phase) documents the amendment: two additive **optional** fields — `parsed_manifest` (the memo seam) and `input_snapshot` (the Gap 1 TOCTOU resolution). Both default to `None` so every existing `ProbeContext(...)` construction site (Phase 0 probes, tests, the coordinator itself) continues to work unchanged. The companion newtype `InputFingerprint` lands alongside `ProbeContext` in `base.py` because it is a contract type — it crosses the coordinator↔probes boundary (coordinator produces, probes consume via `ctx`) and it must satisfy the stdlib-only fence on `base.py`.

The single biggest risk is contract creep: once we crack open the dataclass, a third field is one PR away. The mitigation is structural — a dedicated mutation-killer test in `tests/unit/test_probe_contract.py` hard-codes the allowed 7-field tuple and fails CI with a failure message naming ADR-0002 the moment a third field appears. The existing `test_probe_class_structural_signature_matches_snapshot` catches the same drift generically; the new dedicated test makes the failure self-documenting. The `TODO(S5-02): CODEOWNERS entry required` comment in `base.py` (Phase 0) is the review-time gate; **S1-06 preserves it unchanged**, S5-02 lands the CODEOWNERS routing.

Per Phase-0 ADR-0007, `docs/localv2.md §4` is the source of truth for the probe contract. The S1-06 PR therefore amends `localv2.md §4`'s `ProbeContext` block **first**, then mirrors the change in `base.py`, then regenerates the snapshot — same commit, same reviewer.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §"Data model"`](../phase-arch-design.md) — the dataclass shape (note: arch §"Data model" line 666 shows only `parsed_manifest`; this is internally inconsistent with `§"Component design" #3`, `§"Gap analysis" Gap 1`, and `High-level-impl.md §"Constraints"`, all of which require two fields. The two-field landing is correct; the §"Data model" snippet is stale and will be corrected in a follow-up arch-doc PR.).
  - [`../phase-arch-design.md §"Component design" #3`](../phase-arch-design.md) — `ParsedManifestMemo` exposed via the new field as a callable; capability/strategy pattern at the contract surface.
  - [`../phase-arch-design.md §"Gap analysis" Gap 1`](../phase-arch-design.md) — `input_snapshot` rationale; cache-key derivation moves to `content_hash` (not live `os.stat`); ~5 ms pre-dispatch I/O cost; load-bearing for Phase 14's continuous-gather concurrent-edit threat model.
  - [`../phase-arch-design.md §"Edge cases"`](../phase-arch-design.md) row 12 — probes defensive-check `ctx.parsed_manifest is not None`.
  - [`../phase-arch-design.md §"Goals" #4`](../phase-arch-design.md) — the goal says "zero edits to base.py"; **this is aspirational shorthand and inconsistent with the rest of the document**. The amendment is allowed because it is ADR-gated and additive. Surface this in PR review so it doesn't blindside.
- **Phase ADRs:**
  - [`../ADRs/0002-parsed-manifest-memo-on-probe-context.md`](../ADRs/0002-parsed-manifest-memo-on-probe-context.md) — ADR-0002; S1-06 amends the Decision + Consequences sections to document `input_snapshot` and the new `InputFingerprint` type. ADR-0002 (post-amendment) is the only Phase-0-contract amendment ADR for the entire phase; the ADR text must explicitly say "no further extensions in Phase 1."
- **Phase-0 ADRs:**
  - [`../../00-bullet-tracer-foundations/ADRs/`](../../00-bullet-tracer-foundations/ADRs/) — Phase 0 ADR-0007 (probe-contract snapshot); ADR-0010 (`_ProbeOutputValidator`); the snapshot file `tests/snapshots/probe_contract.v1.json` and the regen script live within this contract.
- **High-level-impl:**
  - [`../High-level-impl.md §"Constraints"`](../High-level-impl.md) line 31 — explicitly: "`ctx.input_snapshot: frozenset[InputFingerprint] | None` added to `ProbeContext` alongside `parsed_manifest` (same ADR-0002 amendment, scoped to two fields)."
  - [`../High-level-impl.md §"Risks specific to this step"`](../High-level-impl.md) line 52 — the "third future field" risk and its sentinel-test mitigation.
- **Source-of-truth doc:**
  - [`../../../localv2.md §"## 4. The probe contract"`](../../../localv2.md) — the contract block. Per ADR-0007, code matches doc; the S1-06 PR amends §4 first.
- **Existing code:**
  - [`src/codegenie/probes/base.py`](../../../../src/codegenie/probes/base.py) (Phase 0) — the `@dataclass` to amend.
  - [`tests/unit/test_probe_contract.py`](../../../../tests/unit/test_probe_contract.py) (Phase 0) — snapshot test; new sentinel test lives here.
  - [`scripts/regen_probe_contract_snapshot.py`](../../../../scripts/regen_probe_contract_snapshot.py) (Phase 0) — regen script; **no behavior change** in S1-06 (the script auto-captures the new fields via `structural_signature`).
  - [`tests/snapshots/probe_contract.v1.json`](../../../../tests/snapshots/probe_contract.v1.json) (Phase 0) — regenerated by the script in the green phase.
  - [`src/codegenie/coordinator/validator.py:43-60`](../../../../src/codegenie/coordinator/validator.py) — `JSONValue` lives here (and stays here; not imported into `base.py`).

## Goal

Amend `ProbeContext` in `src/codegenie/probes/base.py` with two additive `None`-defaulting fields; ship the `InputFingerprint` newtype in the same module; amend `docs/localv2.md §4` to mirror the new contract surface; amend `ADR-0002` to document `input_snapshot`; regenerate the Phase-0 contract snapshot; add a dedicated mutation-killer test that fails CI with an explicit ADR-0002 pointer the moment a third future field appears.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/probes/base.py`'s `ProbeContext` dataclass gains exactly two new fields appended after the existing five, both with `None` defaults:
  - `parsed_manifest: Callable[[Path], Mapping[str, Any] | None] | None = None`
  - `input_snapshot: frozenset["InputFingerprint"] | None = None`
- [ ] **AC-2.** `InputFingerprint` is a new `typing.NamedTuple` defined in `src/codegenie/probes/base.py` (NOT in a worker package), with field order and types exactly `(path: str, mtime_ns: int, size: int, content_hash: str)`. NamedTuple is chosen so the type is auto-hashable for `frozenset[InputFingerprint]` membership without explicit `eq=True, frozen=True` boilerplate.
- [ ] **AC-3.** `ProbeContext`'s existing fields are preserved in their existing order, types, and defaults: `cache_dir: Path`, `output_dir: Path`, `workspace: Path`, `logger: Logger`, `config: dict[str, Any]`. A test pins the full ordered 7-tuple of field names.
- [ ] **AC-4.** The two new fields' **type annotations** are pinned by a test that reads `_serialize_dataclass_fields` (or `inspect.get_annotations`) and asserts the annotation `repr` contains `"Callable"` + `"Mapping"` for `parsed_manifest`, and `"frozenset"` + `"InputFingerprint"` for `input_snapshot`. A mutation that swaps `frozenset` → `set` (or `list`) is caught by this test independently of the structural-signature snapshot.
- [ ] **AC-5.** `tests/unit/test_probe_contract.py` gains a new test `test_probe_context_field_list_matches_adr_0002_amendment` that hard-codes the allowed 7-tuple `("cache_dir", "output_dir", "workspace", "logger", "config", "parsed_manifest", "input_snapshot")` and asserts `tuple(f.name for f in dataclasses.fields(base.ProbeContext)) == ALLOWED`. The `AssertionError` message includes the literal substring `"ADR-0002"` and a pointer to `docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md`.
- [ ] **AC-6.** `tests/unit/test_probe_contract.py` gains an `InputFingerprint` mutation-killer tier (4 tests): (a) `isinstance(fp, tuple)` (NamedTuple inherits from tuple); (b) `hash(fp)` does not raise + `frozenset({fp})` is a singleton; (c) `fp == InputFingerprint(...)` is value-equality; (d) `fp.path = "x"` raises `AttributeError` (immutability). All four tests pinned independently — they collectively catch the four most-plausible wrong implementations (regular class; mutable dataclass; missing `__hash__`; broken `__eq__`).
- [ ] **AC-7.** The Phase-0 construction site `ProbeContext(cache_dir=tmp/"c", output_dir=tmp/"o", workspace=tmp/"w", logger=logger, config={})` (kwargs-only, no new fields supplied) continues to work — a test exercises this exact construction and verifies `ctx.parsed_manifest is None and ctx.input_snapshot is None`. A mutation that removed the `= None` default on either new field breaks this test.
- [ ] **AC-8.** `ALLOWED_BASE_PY_IMPORTS` in `tests/unit/test_probe_contract.py` is widened by exactly one entry: `"collections"` (admitting `from collections.abc import Callable, Mapping` on `base.py`). The set is `{"abc", "collections", "dataclasses", "logging", "pathlib", "typing"}`. A dedicated test pins this so a future revert is a loud regression.
- [ ] **AC-9.** `src/codegenie/probes/base.py` imports `Callable` and `Mapping` from `collections.abc` (not from `typing`, which is deprecated for these). The pre-existing `from typing import Literal, Any` line is preserved; `Callable` and `Mapping` are added on a separate import line.
- [ ] **AC-10.** `docs/localv2.md §"## 4. The probe contract"` is amended to mirror the new contract surface — the `ProbeContext` block in §4 shows the two new fields in their new positions, and an `InputFingerprint` `NamedTuple` declaration is shown above `ProbeContext`. A doc-grep test asserts the literal substrings `"parsed_manifest:"`, `"input_snapshot:"`, and `"class InputFingerprint(NamedTuple):"` appear inside the §4 body extracted by `extract_section_4_body`. After regen, the snapshot's `doc_fingerprint` half matches; without the §4 edit, the structural_signature half passes but `test_probe_contract_doc_fingerprint_matches_snapshot` fails after regen, surfacing the drift.
- [ ] **AC-11.** `docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md` is amended to name `input_snapshot` and `InputFingerprint` explicitly in its Decision section (and to move the line that calls Gap 1 a "future amendment" into a "Resolved in this ADR" note in the Consequences section). A doc-grep test asserts the literal substrings `"input_snapshot"` and `"InputFingerprint"` appear in the ADR body.
- [ ] **AC-12.** `tests/snapshots/probe_contract.v1.json` is regenerated by running `python scripts/regen_probe_contract_snapshot.py` and committed. Both halves (`doc_fingerprint` after the §4 edit + `structural_signature` after the `base.py` edit) update.
- [ ] **AC-13.** The `TODO(S5-02): CODEOWNERS entry required` comment on `src/codegenie/probes/base.py` line 16 (or wherever it lives) **survives unchanged**; pinned by the pre-existing `test_base_py_carries_codeowners_todo_for_s5_02`.
- [ ] **AC-14.** `src/codegenie/probes/base.py` continues to declare exactly five dataclasses (`RepoSnapshot`, `Task`, `ProbeContext`, `ProbeOutput`) plus the new `InputFingerprint` `NamedTuple` plus the `Probe` ABC; pinned by `test_structural_signature_captures_required_dataclasses` (which is updated to include `InputFingerprint` in the expected key list).
- [ ] **AC-15.** A red TDD test exists, is committed at a red commit (CI fails or `pytest -q` shows failures), and turns green after the implementation lands.
- [ ] **AC-16.** `ruff check src tests scripts`, `ruff format --check src tests scripts`, `mypy --strict src`, and `pytest tests/unit/test_probe_contract.py -q` all pass. Mypy --strict accepts the new annotations without `Any`-leak warnings (the `Any` in `Mapping[str, Any]` is at the contract boundary; downstream `_ProbeOutputValidator` re-narrows).
- [ ] **AC-17.** The story's amendment surface is exactly: 1 source file (`base.py`), 1 doc (`localv2.md §4`), 1 ADR (ADR-0002), 1 test file (`test_probe_contract.py`), 1 snapshot (`probe_contract.v1.json`). Zero new files, zero `CODEOWNERS` edits, zero changes to the regen script's executable code path.
- [ ] **AC-18.** The dedicated sentinel test `test_probe_context_field_list_matches_adr_0002_amendment` actually fires against a synthetic mutation. A second test, `test_probe_context_sentinel_fires_on_synthetic_third_field`, monkeypatches `dataclasses.fields(ProbeContext)` with a synthetic three-field-extension (using a tiny throwaway dataclass) and asserts the sentinel's AssertionError surfaces with the ADR-0002 substring — proving the sentinel's failure-message contract is exercised (same pattern as Phase-0 `test_doc_fingerprint_failure_message_routes_to_amendment_template`).

## Implementation outline

1. **Amend `docs/localv2.md §4` first.** In the `ProbeContext` block, add the two fields with `None` defaults. Above `ProbeContext`, add the `InputFingerprint` NamedTuple declaration. Inline comment on each new field naming ADR-0002. Run `python scripts/regen_probe_contract_snapshot.py` — both halves of the snapshot file regenerate. Don't commit yet; the structural_signature half will fail until step 2 lands.
2. **Amend `src/codegenie/probes/base.py`.**
   - Add `from collections.abc import Callable, Mapping` on a new import line (preserving the existing imports). The existing `from typing import Literal, Any` stays.
   - Define `InputFingerprint(NamedTuple)` above `ProbeContext` with fields `(path: str, mtime_ns: int, size: int, content_hash: str)`. Add a one-line module docstring update or a comment naming ADR-0002 and `phase-arch-design.md §"Gap analysis" Gap 1` above the NamedTuple — surgical, single line.
   - Append the two fields to `ProbeContext` after `config`. Add a single line comment above the appended block: `# Phase 1 additions (ADR-0002). No further extensions without ADR amendment.`
   - **Preserve** the `TODO(S5-02): CODEOWNERS entry required` line exactly.
   - Re-run `python scripts/regen_probe_contract_snapshot.py`; both halves now match.
3. **Amend `tests/unit/test_probe_contract.py`.**
   - Widen `ALLOWED_BASE_PY_IMPORTS` by adding `"collections"`.
   - Update `test_structural_signature_captures_required_dataclasses` to include `"InputFingerprint"` in the expected sorted key list.
   - Add new test `test_probe_context_field_list_matches_adr_0002_amendment` with the hard-coded 7-tuple and ADR-0002-pointing failure message.
   - Add the `InputFingerprint` mutation-killer tier (4 tests, AC-6).
   - Add the type-annotation mutation-killers for the two new fields (AC-4).
   - Add the Phase-0-construction-still-works test (AC-7).
   - Add the doc-grep tests for `localv2.md §4` (AC-10) and `ADRs/0002-*.md` (AC-11).
   - Add `test_probe_context_sentinel_fires_on_synthetic_third_field` (AC-18) — same pattern as the existing Tier-5 failure-message contract tests.
4. **Amend `docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md`.**
   - Update the Decision section: name `input_snapshot: frozenset[InputFingerprint] | None` alongside `parsed_manifest`.
   - Update the Consequences section: move the "future amendment" line for Gap 1 into a "Resolved in this ADR" note.
   - Update the title block tags if applicable; add a "Last amended" line: `**Last amended:** 2026-05-14 (S1-06 — add `input_snapshot`)`.
5. **Run the full test suite.** Confirm `pytest tests/unit/test_probe_contract.py -q` passes (all anchor + extractor + normalizer + structural-signature mutation-killer + failure-message + stdlib-imports + CODEOWNERS-TODO + new ADR-0002 sentinel + InputFingerprint mutation-killer + doc-grep tests).
6. **Verify the amendment surface.** `git diff --stat` should show exactly 5 files modified, 0 added, 0 deleted. Run `ruff check`, `ruff format --check`, `mypy --strict`. Commit.

## TDD plan — red / green / refactor

### Red — failing tests first

Three commits, all red before any source edit:

```python
# tests/unit/test_probe_contract.py — appended to existing file

# --- ADR-0002 sentinel + Phase-1 mutation killers (S1-06) -------------------

_ADR_0002_ALLOWED_PROBE_CONTEXT_FIELDS: tuple[str, ...] = (
    "cache_dir", "output_dir", "workspace", "logger", "config",
    "parsed_manifest", "input_snapshot",
)
_ADR_0002_PATH = REPO_ROOT / "docs" / "phases" / "01-context-gather-layer-a-node" / "ADRs" / "0002-parsed-manifest-memo-on-probe-context.md"
_LOCALV2_PATH = LOCALV2_PATH  # already defined

def test_probe_context_field_list_matches_adr_0002_amendment() -> None:
    # AC-5: explicit ADR-0002 sentinel. A third future field fails CI here
    # with a self-documenting message that names the ADR.
    import dataclasses
    actual = tuple(f.name for f in dataclasses.fields(base.ProbeContext))
    assert actual == _ADR_0002_ALLOWED_PROBE_CONTEXT_FIELDS, (
        f"ProbeContext field list {actual} does not match ADR-0002. "
        f"Adding fields to ProbeContext is gated by ADR-0002 amendment. "
        f"See docs/phases/01-context-gather-layer-a-node/ADRs/"
        f"0002-parsed-manifest-memo-on-probe-context.md."
    )

def test_probe_context_new_field_annotations_pinned() -> None:
    # AC-4: catches `set` ↔ `frozenset` swap and `Mapping` → `dict` swap
    # independently of the structural-signature snapshot.
    import inspect
    ann = inspect.get_annotations(base.ProbeContext)
    assert "Callable" in repr(ann["parsed_manifest"])
    assert "Mapping" in repr(ann["parsed_manifest"])
    assert "frozenset" in repr(ann["input_snapshot"])
    assert "InputFingerprint" in repr(ann["input_snapshot"])

def test_probe_context_phase0_construction_keeps_working(tmp_path) -> None:
    # AC-7: a mutation that removed the `= None` default on either new field
    # breaks this test; the Phase 0 construction sites all use kwargs.
    import logging
    ctx = base.ProbeContext(
        cache_dir=tmp_path / "c",
        output_dir=tmp_path / "o",
        workspace=tmp_path / "w",
        logger=logging.getLogger("test"),
        config={},
    )
    assert ctx.parsed_manifest is None
    assert ctx.input_snapshot is None

def test_input_fingerprint_is_tuple_subclass() -> None:
    fp = base.InputFingerprint(path="/r/package.json", mtime_ns=1, size=100, content_hash="abc")
    assert isinstance(fp, tuple)  # NamedTuple inherits tuple

def test_input_fingerprint_is_hashable_and_frozenset_member() -> None:
    fp = base.InputFingerprint(path="/x", mtime_ns=0, size=0, content_hash="0")
    h = hash(fp)  # raises if not hashable
    assert {fp} == {fp}  # value-equality via __eq__
    assert frozenset({fp, fp}) == frozenset({fp})  # singleton on equal-value

def test_input_fingerprint_equality_is_value_based() -> None:
    a = base.InputFingerprint(path="/x", mtime_ns=0, size=0, content_hash="0")
    b = base.InputFingerprint(path="/x", mtime_ns=0, size=0, content_hash="0")
    c = base.InputFingerprint(path="/y", mtime_ns=0, size=0, content_hash="0")
    assert a == b
    assert a != c

def test_input_fingerprint_is_immutable() -> None:
    import pytest
    fp = base.InputFingerprint(path="/x", mtime_ns=0, size=0, content_hash="0")
    with pytest.raises(AttributeError):
        fp.path = "y"  # type: ignore[misc]

def test_input_fingerprint_field_types_pinned() -> None:
    # AC-2: a mutation that retyped `mtime_ns: float` (silent precision loss)
    # is caught here.
    ann = base.InputFingerprint.__annotations__
    assert ann["path"] is str
    assert ann["mtime_ns"] is int
    assert ann["size"] is int
    assert ann["content_hash"] is str

def test_allowed_base_py_imports_includes_collections() -> None:
    # AC-8: widening of the stdlib-only fence is itself part of the amendment;
    # this test pins the new entry so a future revert is a loud regression.
    assert "collections" in ALLOWED_BASE_PY_IMPORTS

def test_localv2_section_4_shows_phase1_probe_context_fields() -> None:
    # AC-10: code matches doc, never the inverse (ADR-0007). Without this
    # check the doc_fingerprint test catches drift but the source of drift
    # is opaque; this test names what was missed.
    body = extract_section_4_body(_LOCALV2_PATH.read_text(encoding="utf-8"))
    assert "parsed_manifest:" in body, "localv2.md §4 ProbeContext missing parsed_manifest"
    assert "input_snapshot:" in body, "localv2.md §4 ProbeContext missing input_snapshot"
    assert "class InputFingerprint(NamedTuple):" in body, (
        "localv2.md §4 missing InputFingerprint NamedTuple block"
    )

def test_adr_0002_names_input_snapshot_and_input_fingerprint() -> None:
    # AC-11: the ADR text is the human-facing record; an ADR that doesn't
    # name input_snapshot is rot the moment Phase 2 reads it for context.
    text = _ADR_0002_PATH.read_text(encoding="utf-8")
    assert "input_snapshot" in text
    assert "InputFingerprint" in text

def test_probe_context_sentinel_fires_on_synthetic_third_field() -> None:
    # AC-18: exercise the sentinel's failure-message contract (same pattern
    # as Tier-5 doc/structural-signature failure-message tests). A throwaway
    # dataclass with a third field stands in for the future amendment.
    import dataclasses, pytest
    @dataclasses.dataclass
    class _SyntheticThreeField:
        cache_dir: Path
        output_dir: Path
        workspace: Path
        logger: Any
        config: dict[str, Any]
        parsed_manifest: Any = None
        input_snapshot: Any = None
        future_third_field: Any = None  # the offending addition
    actual = tuple(f.name for f in dataclasses.fields(_SyntheticThreeField))
    with pytest.raises(AssertionError, match=r"ADR-0002"):
        assert actual == _ADR_0002_ALLOWED_PROBE_CONTEXT_FIELDS, (
            f"ProbeContext field list {actual} does not match ADR-0002. "
            f"Adding fields to ProbeContext is gated by ADR-0002 amendment. "
            f"See docs/phases/01-context-gather-layer-a-node/ADRs/"
            f"0002-parsed-manifest-memo-on-probe-context.md."
        )
```

Run; confirm `ImportError` (on `base.InputFingerprint`) and many `AttributeError` / `AssertionError` failures. Commit as red.

### Green — minimal impl

`src/codegenie/probes/base.py` — minimal diff:

```python
# ruff: noqa: I001
"""Frozen probe-contract surface — byte-for-byte ``docs/localv2.md §4`` (ADR-0007).
...
"""

# TODO(S5-02): CODEOWNERS entry required for src/codegenie/probes/base.py, docs/localv2.md, tests/snapshots/ — see ADR-0007 §Reversibility

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping  # ADR-0002 (Phase 1) — admitted by ALLOWED_BASE_PY_IMPORTS widening
from dataclasses import dataclass
from typing import Literal, Any, NamedTuple
from pathlib import Path
from logging import Logger


# Phase 1 contract type (ADR-0002 + phase-arch-design.md §"Gap analysis" Gap 1).
# Lives in base.py because it crosses the coordinator↔probes boundary and must
# satisfy the stdlib-only fence.
class InputFingerprint(NamedTuple):
    path: str
    mtime_ns: int
    size: int
    content_hash: str


# ... RepoSnapshot, Task unchanged ...


@dataclass
class ProbeContext:
    cache_dir: Path
    output_dir: Path
    workspace: Path
    logger: Logger
    config: dict[str, Any]
    # Phase 1 additions (ADR-0002). No further extensions without ADR amendment.
    parsed_manifest: Callable[[Path], Mapping[str, Any] | None] | None = None
    input_snapshot: frozenset[InputFingerprint] | None = None


# ... ProbeOutput, Probe unchanged ...
```

`tests/unit/test_probe_contract.py`:

```python
ALLOWED_BASE_PY_IMPORTS = {"abc", "collections", "dataclasses", "logging", "pathlib", "typing"}
# ... and the new tests as above ...

# update the captures_required_dataclasses test:
def test_structural_signature_captures_required_dataclasses() -> None:
    sig = structural_signature(base)
    assert list(sig.keys()) == [
        "InputFingerprint",
        "Probe",
        "ProbeContext",
        "ProbeOutput",
        "RepoSnapshot",
        "Task",
    ], list(sig.keys())
```

`docs/localv2.md §4` — update the code block to include `InputFingerprint` and the two new fields on `ProbeContext`. Run `python scripts/regen_probe_contract_snapshot.py`. Commit the regenerated `tests/snapshots/probe_contract.v1.json`.

`docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md` — amend Decision + Consequences as described in Implementation outline step 4.

### Refactor — clean up

- Reread the inline comment above the appended `ProbeContext` block: must be one line, name ADR-0002, and say "no further extensions without ADR amendment." Do NOT rewrite the dataclass docstring (Rule 3).
- Reread `InputFingerprint`'s preceding comment: must name ADR-0002 + `phase-arch-design.md §"Gap analysis" Gap 1`. Do not move existing imports just because new ones land near them.
- Verify the snapshot regen is byte-for-byte deterministic: run the regen script twice and `diff` the outputs; zero diff.
- Verify `mypy --strict src/codegenie/probes/base.py` and `mypy --strict tests/unit/test_probe_contract.py` — both clean.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/base.py` | Append two optional fields to `ProbeContext`; define `InputFingerprint` `NamedTuple`; add `Callable`+`Mapping` imports from `collections.abc`. **Preserve** the S5-02 CODEOWNERS TODO. |
| `docs/localv2.md` (§4 only) | Mirror the new `ProbeContext` shape and `InputFingerprint` block in the contract source-of-truth (ADR-0007). |
| `docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md` | Amend Decision + Consequences to name `input_snapshot` and `InputFingerprint`. Add "Last amended" line. |
| `tests/unit/test_probe_contract.py` | Widen `ALLOWED_BASE_PY_IMPORTS`; update `test_structural_signature_captures_required_dataclasses`; add ADR-0002 sentinel test + Phase-1 mutation killers + doc-grep tests + sentinel-fires-on-synthetic test. |
| `tests/snapshots/probe_contract.v1.json` | Regenerated by `python scripts/regen_probe_contract_snapshot.py` (both halves: `doc_fingerprint` after §4 edit, `structural_signature` after `base.py` edit). |

## Out of scope

- **`ParsedManifestMemo` itself** — S1-07 implements the memo class; this story only declares the seam on `ProbeContext`.
- **Coordinator wiring** of `ctx.parsed_manifest=memo.get` and `ctx.input_snapshot=...` — S1-07 and S1-08 do those.
- **Coordinator computing `input_snapshot`** — S1-08 implements the pre-dispatch pass.
- **Any probe consuming `ctx.parsed_manifest` or `ctx.input_snapshot`** — Step 2 onward.
- **Promoting `InputFingerprint` to a wider data model** (e.g., adding `permissions`) — not needed in Phase 1.
- **`CODEOWNERS` editing.** The `TODO(S5-02): CODEOWNERS entry required` in `base.py` is preserved as-is. S5-02 owns the CODEOWNERS routing. Adding it here would violate `test_base_py_carries_codeowners_todo_for_s5_02` and Phase 5's scope.
- **`scripts/regen_probe_contract_snapshot.py` behavior changes.** The script already captures the new fields via dynamic `structural_signature(...)`; no executable-code change is needed. The "third-future-field" sentinel lives in the test layer, not the script. (Open/Closed: the script's responsibility is regenerating the snapshot; the test's responsibility is asserting correctness.)

## Notes for the implementer

- **This is the single Phase-0-contract amendment for the entire phase.** Every other Phase-1 file is new. Treat it surgically: amend `localv2.md §4` first, mirror in `base.py`, regenerate the snapshot, update ADR-0002, add tests, stop.
- **Both fields default to `None`** so every existing `ProbeContext(...)` constructor call in tests, fixtures, or the coordinator keeps working without edits. Consumer probes already need to defensive-check `ctx.parsed_manifest is not None` (Edge case #12 in `phase-arch-design.md`); the same pattern applies to `ctx.input_snapshot`.
- **Stdlib-only fence widening.** The Phase-0 `test_base_py_imports_are_stdlib_only` pins `ALLOWED_BASE_PY_IMPORTS = {"abc", "dataclasses", "logging", "pathlib", "typing"}`. The S1-06 amendment widens this set by exactly `"collections"` (admitting `from collections.abc import Callable, Mapping`). This widening is itself part of the ADR-0002 amendment scope. AC-8 pins the widening so future reverts are a loud regression.
- **Why `Mapping[str, Any]` and not `Mapping[str, JSONValue]`** on `parsed_manifest`: `JSONValue` lives in `src/codegenie/coordinator/validator.py` (line 43-60). Importing it into `base.py` would (a) cycle (`coordinator/validator.py` imports `probes.base.ProbeOutput`), (b) violate the stdlib-only fence. Phase 0's contract surface uses `Any` at the dict/Mapping boundary throughout (`RepoSnapshot.config`, `ProbeContext.config`, `ProbeOutput.schema_slice`, `Task.options`) — the JSONValue narrowing happens downstream at `_ProbeOutputValidator` per ADR-0010. Keep this layering.
- **Why `InputFingerprint` is in `base.py` (not `coordinator/`).** It is a contract type — coordinator produces it, probes consume it via `ctx.input_snapshot`. Contract types live with the contract surface. Putting it in `coordinator/input_snapshot.py` would (a) break the stdlib-only fence (cross-package import on `base.py`), (b) invert the dependency arrow (contract should not depend on worker package), (c) require `TYPE_CHECKING` + `ForwardRef` gymnastics that complicate the snapshot's `f.type` repr. Define it in `base.py` next to `ProbeContext`.
- **Why `NamedTuple` and not `dataclass(frozen=True)`** for `InputFingerprint`: `NamedTuple` is hashable for free (inherits `tuple.__hash__`) and equality-by-value out of the box — exactly what `frozenset[InputFingerprint]` membership requires. `dataclass(frozen=True)` needs explicit `eq=True, frozen=True` and is more boilerplate for the same result. (Also: `NamedTuple` slots out the `__dict__` and is slightly smaller in memory; not load-bearing but symmetric with intent.)
- **`content_hash` is a `str`** — Phase 0's `hashing.py` returns blake3 hex strings. `InputFingerprint` only declares the shape; the coordinator's S1-08 pre-dispatch pass computes the hash. This file does not compute hashes.
- **`path: str` (not `Path`)** is intentional: cross-platform hashable + comparable; `Path` equality on macOS's case-insensitive filesystem is a foot-gun (`Path("/a/B") != Path("/a/b")` but both stat the same file). The coordinator normalizes to an absolute POSIX-form string at fingerprint time. (Phase-2 sharpening opportunity: introduce a `NormalizedAbsPath` newtype to remove the primitive-obsession smell — deferred until the third consumer crosses the rule-of-three threshold; do NOT introduce it in S1-06.)
- **The "third future field" sentinel lives in the test layer.** `test_probe_context_field_list_matches_adr_0002_amendment` hard-codes the 7-tuple and emits an AssertionError that names ADR-0002. The existing `test_probe_class_structural_signature_matches_snapshot` catches the same drift generically; the new dedicated test makes the failure self-documenting. Why not in the regen script? The script's responsibility is regenerating the snapshot, not asserting correctness — putting the assertion there mixes responsibilities (Open/Closed at the file boundary).
- **Arch goal #4 says "zero edits to `src/codegenie/probes/base.py`"** ([phase-arch-design.md:21](../phase-arch-design.md)) — this is **aspirational shorthand**, inconsistent with `§"Data model"` (line 666), `§"Component design" #3`, `§"Gap analysis" Gap 1`, ADR-0002, and `High-level-impl.md §"Constraints"`, all of which require the edit. The amendment is allowed because it is ADR-gated and additive. **Surface this in the PR description** so it doesn't blindside a reviewer who reads goal #4 in isolation.
- **`phase-arch-design.md §"Data model"` shows only one field added to `ProbeContext`** (line 667). This snippet is stale relative to `High-level-impl.md §"Constraints"` (line 31) and the Gap 1 improvement. The two-field landing is correct; the arch doc needs a one-line fix in a follow-up PR (not in scope for S1-06).
- **Per Rule 12:** if `pytest tests/unit/test_probe_contract.py -q` fails locally before commit, do NOT bypass it. The sentinel test + structural-signature test + doc-fingerprint test are the seams stopping silent contract drift. Surface failures explicitly.
- **Per Rule 3:** the amendment is exactly 5 files. No "improvements" to adjacent code, comments, or formatting. The `ruff format --check` AC pins style; do not run `ruff format` and reformat the existing untouched code in `base.py`.
- **Phase-2/14 sharpening opportunities** (record, do not implement now):
  - `path: NormalizedAbsPath` newtype — defer to when a 3rd consumer surfaces.
  - `input_snapshot: frozenset[InputFingerprint]` (non-`None`) with a sentinel `_EMPTY_SNAPSHOT` singleton — defer to Phase 14 when continuous-gather makes "no snapshot pass" a paradox.
  - A `ParsedManifestCapability` `Protocol` to replace the bare `Callable` — defer until S1-07 lands the concrete memo and we can see whether the Protocol pulls its weight (rule-of-three).
