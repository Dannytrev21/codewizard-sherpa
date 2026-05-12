# Story S1-06 — `ProbeContext` extension: `parsed_manifest` + `input_snapshot`

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0002

## Context

`ProbeContext` is the only Phase 0 frozen-contract dataclass that Phase 1 amends. ADR-0002 documents the amendment: two additive **optional** fields — `parsed_manifest: Callable[..., ...] | None = None` (the memo seam) and `input_snapshot: frozenset[InputFingerprint] | None = None` (the Gap 1 TOCTOU resolution). Both default to `None` so Phase 0 probes and any test path that constructs `ProbeContext` directly continue to work unchanged.

The single biggest risk is contract creep: once we crack open the dataclass, a third field is one PR away. The mitigation is structural — the regenerated snapshot test (Phase 0 ADR-0007's contract snapshot) must encode the **allowed field list** inside the regen script. A third field added later fails CI with a pointer to ADR-0002. The `CODEOWNERS` route on `src/codegenie/probes/base.py` adds review-time gating.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Data model"` — the exact dataclass shape with `parsed_manifest` and `input_snapshot` fields, both optional and defaulting to `None`.
  - `../phase-arch-design.md §"Component design" #3` — `ParsedManifestMemo` is exposed via the new field as a callable.
  - `../phase-arch-design.md §"Gap analysis" Gap 1` — `input_snapshot` rationale; key derivation moves to `content_hash` (not live `os.stat`).
  - `../phase-arch-design.md §"Edge cases"` row 12 — probes defensive-check `ctx.parsed_manifest is not None`.
- **Phase ADRs:**
  - `../ADRs/0002-parsed-manifest-memo-on-probe-context.md` — ADR-0002 — the one-and-only Phase-0 contract amendment in Phase 1; explicitly says "no further extensions in Phase 1."
- **Production ADRs:**
  - `../../../production/adrs/` — Phase 0 ADR-0007 (probe-contract snapshot) is the file this story regenerates.
- **Source design:**
  - `../final-design.md §"Components" #2` — design statement.
- **Existing code:**
  - `src/codegenie/probes/base.py` (Phase 0 frozen) — the `@dataclass` to amend.
  - `tests/unit/test_probe_contract.py` (Phase 0) — snapshot test; regenerate after the amendment.
  - `scripts/regen_probe_contract.py` (Phase 0, if it exists) — the regen script.

## Goal

Amend `ProbeContext` in `src/codegenie/probes/base.py` with two additive `None`-defaulting fields, regenerate the contract snapshot, and encode the **allowed field list inside the regen script** so a third future field fails CI loudly.

## Acceptance criteria

- [ ] `src/codegenie/probes/base.py`'s `ProbeContext` dataclass gains exactly two new fields: `parsed_manifest: Callable[[Path], Mapping[str, JSONValue] | None] | None = None` and `input_snapshot: frozenset[InputFingerprint] | None = None`.
- [ ] `InputFingerprint` is a new frozen `NamedTuple` (or `dataclass(frozen=True)`) with fields `path: str`, `mtime_ns: int`, `size: int`, `content_hash: str`. Defined in `src/codegenie/coordinator/input_snapshot.py` (NEW file) — keeps `base.py` free of new types except the forward type annotation.
- [ ] No other field on `ProbeContext` changes — old fields retained, in their existing order; new fields appended.
- [ ] The contract snapshot (`tests/unit/test_probe_contract.py` and its regen script) is regenerated with the documented additions; snapshot test passes.
- [ ] The regen script (`scripts/regen_probe_contract.py` or wherever Phase 0 placed it) encodes the **allowed `ProbeContext` field name list** as a literal constant. Adding a third field produces a snapshot diff and a script-internal assertion failure pointing at ADR-0002.
- [ ] `src/codegenie/probes/base.py` is added to `CODEOWNERS` (or its Phase-0 entry is confirmed to cover it).
- [ ] Phase 0 probes (`LanguageDetectionProbe` as it exists in Phase 0) continue to construct `ProbeContext` without specifying the new fields (defaults work).
- [ ] Unit test `tests/unit/coordinator/test_input_snapshot_shape.py` asserts `InputFingerprint` shape (immutability, equality semantics, hashability).
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest tests/unit/test_probe_contract.py` pass.

## Implementation outline

1. Create `src/codegenie/coordinator/input_snapshot.py` with the `InputFingerprint` `NamedTuple`. Field order: `(path, mtime_ns, size, content_hash)`.
2. Amend `src/codegenie/probes/base.py`:
   - Add `from collections.abc import Callable, Mapping` (if not present).
   - Add `from codegenie.coordinator.input_snapshot import InputFingerprint` (forward-safe import — `coordinator/` cannot import `probes/base` to avoid cycles; but `base` importing `coordinator/input_snapshot` is fine because `input_snapshot` is a leaf module).
   - Add `from pathlib import Path` if missing.
   - Append the two fields to `ProbeContext` after the existing ones; both `= None` default.
3. Regenerate the snapshot:
   - Edit `scripts/regen_probe_contract.py` (Phase 0). Add `parsed_manifest`, `input_snapshot` to the `ALLOWED_PROBECONTEXT_FIELDS` constant.
   - Re-run the regen script. Commit the updated snapshot file.
4. Add an assertion inside the regen script: after producing the snapshot, parse the `ProbeContext` field list and assert it equals `ALLOWED_PROBECONTEXT_FIELDS`. Fail with a `RuntimeError` pointing to ADR-0002 if it doesn't.
5. Add unit tests for `InputFingerprint`.
6. Confirm `CODEOWNERS` covers `src/codegenie/probes/base.py`.

## TDD plan — red / green / refactor

### Red — failing test first

Two test files.

```python
# tests/unit/coordinator/test_input_snapshot_shape.py
from codegenie.coordinator.input_snapshot import InputFingerprint

def test_input_fingerprint_fields():
    fp = InputFingerprint(path="/r/package.json", mtime_ns=123, size=100, content_hash="abc")
    assert fp.path == "/r/package.json"
    assert fp.mtime_ns == 123

def test_input_fingerprint_is_hashable_and_frozen():
    fp = InputFingerprint(path="/x", mtime_ns=0, size=0, content_hash="0")
    # hashable → can live in frozenset, which is the ProbeContext.input_snapshot type
    frozenset({fp})
    # equality is value-based
    assert fp == InputFingerprint(path="/x", mtime_ns=0, size=0, content_hash="0")
```

```python
# tests/unit/test_probe_contract.py — extension to existing Phase 0 test
import dataclasses
from codegenie.probes.base import ProbeContext

def test_probe_context_has_two_new_optional_fields_only():
    field_names = [f.name for f in dataclasses.fields(ProbeContext)]
    # ADR-0002: exactly two additions; old fields preserved in order
    assert field_names[-2:] == ["parsed_manifest", "input_snapshot"]
    # defaults are None so Phase 0 construction sites keep working
    fields_by_name = {f.name: f for f in dataclasses.fields(ProbeContext)}
    assert fields_by_name["parsed_manifest"].default is None
    assert fields_by_name["input_snapshot"].default is None

def test_regen_script_encodes_allowed_field_list():
    # arch §"Step 1 risks" #2: a third future field must fail CI
    import scripts.regen_probe_contract as regen  # type: ignore
    assert "parsed_manifest" in regen.ALLOWED_PROBECONTEXT_FIELDS
    assert "input_snapshot" in regen.ALLOWED_PROBECONTEXT_FIELDS
    # the list should be exactly N fields — read off the dataclass
    expected = {f.name for f in dataclasses.fields(ProbeContext)}
    assert set(regen.ALLOWED_PROBECONTEXT_FIELDS) == expected
```

Run; confirm `ImportError` / `AssertionError`. Commit as red.

### Green — minimal impl

- `coordinator/input_snapshot.py`:
  ```python
  from typing import NamedTuple
  class InputFingerprint(NamedTuple):
      path: str
      mtime_ns: int
      size: int
      content_hash: str
  ```
- `probes/base.py`: append two fields. Use forward `Callable` typing so mypy is satisfied without importing more than necessary. The full signature is `Callable[[Path], Mapping[str, JSONValue] | None] | None`. `JSONValue` should already exist as a recursive alias from Phase 0; if not, define it locally.
- `scripts/regen_probe_contract.py`: add the literal `ALLOWED_PROBECONTEXT_FIELDS = ("cache_dir", "output_dir", "workspace", "logger", "config", "parsed_manifest", "input_snapshot")` (order match the dataclass). Add the post-regen assertion.

### Refactor — clean up

- Module docstring on `coordinator/input_snapshot.py`: name `phase-arch-design.md §"Gap analysis" Gap 1`, ADR-0002, and the load-bearing role for the coordinator's pre-dispatch pass (S1-08).
- ADR-0002 already says "no further extensions in Phase 1" — link to it in a comment above the appended fields on `ProbeContext`.
- Verify `mypy --strict` on `base.py` and the new `input_snapshot.py`.
- If `CODEOWNERS` already covers `src/codegenie/probes/base.py` from Phase 0 setup, do nothing; otherwise add the entry. (Per Rule 3, surgical — don't widen the CODEOWNERS scope.)

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/base.py` | Append two optional fields to `ProbeContext` |
| `src/codegenie/coordinator/input_snapshot.py` | New — `InputFingerprint` NamedTuple |
| `scripts/regen_probe_contract.py` | Extend `ALLOWED_PROBECONTEXT_FIELDS`; add post-regen assertion |
| `tests/unit/test_probe_contract.py` | Extend Phase 0 test with new-field assertions + regen-script invariant |
| `tests/unit/coordinator/__init__.py` | New (empty) |
| `tests/unit/coordinator/test_input_snapshot_shape.py` | New — `InputFingerprint` shape |
| `tests/unit/test_probe_contract.snapshot.json` (or similar) | Regenerated by the script |
| `CODEOWNERS` | Confirm `src/codegenie/probes/base.py` is covered (add if missing) |

## Out of scope

- **`ParsedManifestMemo` itself** — S1-07 implements the memo class; this story only declares the seam on `ProbeContext`.
- **Coordinator wiring** of `ctx.parsed_manifest=memo.get` — S1-07 does that.
- **Coordinator computing `input_snapshot`** — S1-08 implements the pre-dispatch pass.
- **Any probe consuming `ctx.parsed_manifest`** — Step 2 onward.
- **Promoting `InputFingerprint` to a wider data model** (e.g., adding `permissions`) — not needed in Phase 1.

## Notes for the implementer

- **This is the single Phase-0-contract amendment for the entire phase.** Every other Phase-1 file is new. Treat it surgically: append two fields, regenerate the snapshot, and stop.
- **Both fields default to `None`** so every existing `ProbeContext(...)` constructor call in tests, fixtures, or the coordinator keeps working without edits. Probes already need to defensive-check `ctx.parsed_manifest is not None` (Edge case #12 in `phase-arch-design.md`); same pattern applies to `ctx.input_snapshot`.
- **Avoid import cycles.** `probes/base` should be the leaf of the dependency graph from `coordinator/`. If `input_snapshot` ends up importing anything that imports `probes`, you've broken the layering — use a `TYPE_CHECKING` guard or restructure.
- **The regen script's `ALLOWED_PROBECONTEXT_FIELDS` constant is load-bearing.** It is the *only* place a future engineer is forced to confront the ADR-0002 commitment when adding a third field. The post-regen assertion must reference ADR-0002 in its error message: `raise RuntimeError(f"ProbeContext fields {actual} do not match ADR-0002-allowed {ALLOWED_...}. See docs/phases/01-.../ADRs/0002-...md")`.
- **`InputFingerprint` is a `NamedTuple` (not a `dataclass(frozen=True)`)** because it must be hashable for `frozenset[InputFingerprint]` membership. `NamedTuple` is hashable for free; `dataclass(frozen=True)` requires explicit `eq=True, frozen=True` and is more boilerplate for the same result.
- **`content_hash` is a `str`** — Phase 0 uses blake3 hex strings. The `coordinator/input_snapshot.py` doesn't compute hashes — S1-08 does. This file just declares the shape.
- **Do not** add doc-comments on `ProbeContext` like "Phase 1 fields below." A line comment naming ADR-0002 is fine and surgical; rewriting the dataclass docstring is not (Rule 3).
- **Per Rule 12:** if the regen script's post-run assertion fails locally before commit, do NOT bypass it. The assertion is the only seam stopping silent third-field drift.
