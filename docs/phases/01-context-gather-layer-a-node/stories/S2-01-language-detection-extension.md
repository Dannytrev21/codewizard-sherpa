# Story S2-01 — `LanguageDetectionProbe` extension: `framework_hints` + `monorepo`

**Step:** Step 2 — Extend `LanguageDetectionProbe` and ship `NodeBuildSystemProbe`
**Status:** Ready (hardened 2026-05-14)
**Effort:** S
**Depends on:** S1-05 (catalogs loader; not strictly required here but its hard-fail-at-startup pattern is the precedent), S1-07 (`ParsedManifestMemo` — `ctx.parsed_manifest` must be wired and the `probe.memo.{hit,miss}` events registered)
**ADRs honored:** ADR-0002 (this phase — consumes `ctx.parsed_manifest`), ADR-0004 (this phase — `additionalProperties: false` at sub-schema root), ADR-0007 (this phase — warning-ID **and error-ID** pattern; see Validation notes below), ADR-0010 (this phase — Layer A slices optional at envelope), Phase 0 ADR-0013 (envelope `probes.*: additionalProperties: true` preserved).

## Validation notes (added 2026-05-14)

This story was hardened by `phase-story-validator`. The full audit report lives at [`_validation/S2-01-language-detection-extension.md`](_validation/S2-01-language-detection-extension.md). Summary of in-place edits:

- **Field semantics fixed (block-tier).** Per ADR-0007 line 50 — `errors` is the typed-exception-raised list; `warnings` is the soft-degrade signal — and per arch §"Component design" #1 which prescribes `ProbeOutput(..., errors=["package_json.malformed"])`, the two failure IDs (`package_json.size_cap_exceeded`, `package_json.symlink_refused`, `package_json.malformed`) now belong in **`ProbeOutput.errors`**, not `language_stack.warnings`. The sub-schema constrains both `errors[]` AND `warnings[]` with the ADR-0007 pattern; the slice's `warnings[]` is preserved as an empty/forward-compatible array for future soft-degrade signals.
- **Confidence levels fixed (block-tier).** Per arch §"Component design" #1: size-cap-exceeded → `confidence: "medium"`; symlink-refused → `confidence: "low"`. The story originally collapsed both to `"medium"`. The edge-case row 2 disagreement (which says `low` for size-cap) is recorded as a known arch-internal contradiction; this story sides with §"Component design" #1 because it's the more detailed component-level prescription and is the section the story explicitly cites.
- **MalformedJSONError path added (harden).** The Refactor block originally caught three exceptions but only declared two error IDs. Added `package_json.malformed` as the third typed error ID (matches arch §"Component design" #1's `errors=["package_json.malformed"]`).
- **Monorepo precedence pinned (harden).** Added an explicit deterministic precedence rule for cases where multiple monorepo markers coexist: `(pnpm-workspace.yaml, "pnpm-workspaces") > (turbo.json, "turbo") > (nx.json, "nx") > (lerna.json, "lerna") > (package.json#workspaces, "workspaces")`. Encoded as a single precedence-ordered tuple (`_MONOREPO_PRECEDENCE`) so adding a new monorepo tool in Phase 2 is a one-line tuple insertion — no edits to branching logic (Open/Closed). The `markers` list contains the union of all marker filenames that hit (sorted), independent of which one determined `tool`.
- **`markers` content pinned.** `package.json` IS included in `markers` whenever its `workspaces` field is truthy, regardless of whether `tool == "workspaces"`. Test 2's expectation `sorted(markers) == ["package.json", "turbo.json"]` is now traceable to an explicit AC.
- **TDD plan strengthened.** Added negative-assertion to Test 1 (non-framework deps not classified); added Test 6 (symlink-refused path emits `errors[]` and demotes confidence to `low`); added Test 7 (memo consumption — `ctx.parsed_manifest` is called when available, falls back when `None`); added Test 8 (deterministic sort + dedup property test, parametrized over shuffled input orderings); added Test 9 (multi-monorepo precedence determinism); added Test 10 (`workspaces` as object-form vs array-form both detected; `workspaces == null` treated as absent).
- **Phase 0 fixture regression check.** Strengthened the "existing counts/primary fields are unaffected" AC into a byte-equal regression assertion: the Phase 0 fields (`counts`, `primary`, `total_files`, etc.) on a Phase 0 fixture must be byte-identical before/after the extension. New ACs cannot remove or rename existing keys.
- **Compile-time discipline.** The `_ERRORS` frozenset (renamed from `_WARNINGS`) is module-import-time assertion-checked against the ADR-0007 regex (Rule 12: fail loud). Same discipline for `_FRAMEWORK_SEED` keys (must be plausible npm package names; assert at import). `_MONOREPO_PRECEDENCE` tuple — last entry's first element is `"package.json"`, asserted at import.
- **Design-pattern notes lifted.** `_FRAMEWORK_SEED` and `_MONOREPO_PRECEDENCE` are single-use today — explicit rule-of-three deferral recorded in "Notes for the implementer": do NOT extract to YAML catalog until a third consumer arrives (Phase 2 polyglot detection is the candidate).
- **No `NEEDS RESEARCH` findings.** Stage 3 (researcher) skipped per skill's token-economy guidance.

The story moved from **7 ACs + 5 TDD tests** to **13 ACs + 10 TDD tests**. Verdict: **HARDENED**.

## Context

This story is one of the **three Phase-0-in-place edits** the phase is allowed (per the manifest "Backlog stats" and `../High-level-impl.md §"Order of operations"`). Phase 0's `LanguageDetectionProbe` ships extension-counting only; Phase 0 final-design §2.10 explicitly deferred framework hints and monorepo detection. This story closes that deferral.

It is also the **first real consumer of `ParsedManifestMemo`**. The framework lookup reads `package.json` via `ctx.parsed_manifest(...)` so that when `NodeBuildSystemProbe` (S2-02), `NodeManifestProbe` (S3-05), and `TestInventoryProbe` (S4-03) later read the same file, the memo serves it without re-parse. The integration test in S2-04 asserts exactly this: `probe.memo.miss == 1`, `probe.memo.hit == 1` across the two probes in this step.

Finally, this probe is `tier="base"` (already in Phase 0); it remains the Wave-1 prelude anchor (Phase 0 Gap #4 resolution). The extension keeps the Wave-1 role intact — the new fields populate before Wave 2 dispatches, so Phase-1 Node probes can branch on them.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #1` (this probe; framework dict, monorepo markers, perf envelope).
  - `../phase-arch-design.md §"Data model"` — `language_stack` extension is described in prose under §"Component design" #1; the sub-schema lives at `src/codegenie/schema/probes/language_detection.schema.json`.
  - `../phase-arch-design.md §"Control flow" → "Decision points" → "Memo hit vs. memo miss"`.
  - `../phase-arch-design.md §"Edge cases"` rows 2, 3, 12 (oversized `package.json`, symlink-out-of-repo `package.json`, `ctx.parsed_manifest is None`).
- **Phase ADRs:**
  - `../ADRs/0002-parsed-manifest-memo-on-probe-context.md` — the contract this probe consumes.
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — sub-schema must set `additionalProperties: false` at its own root.
  - `../ADRs/0007-warnings-id-pattern.md` — every warning emitted matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.
  - `../ADRs/0010-layer-a-slices-optional-at-envelope.md` — the slice is optional at envelope; non-Node repos validate.
- **Source design:**
  - `../../../localv2.md §5.1 A1` (LanguageDetection probe inventory entry; Phase 0 ships extension-counting only).
- **Existing code:**
  - `src/codegenie/probes/language_detection.py` (Phase 0; the file edited in place).
  - `src/codegenie/probes/base.py` (frozen — DO NOT EDIT here).
  - `src/codegenie/schema/probes/language_detection.schema.json` (Phase 0; extended in place).
  - `src/codegenie/coordinator/parsed_manifest_memo.py` (from S1-07; consumed via `ctx.parsed_manifest`).
- **External docs:** none required — the framework seed dict is enumerated in §"Component design" #1.

## Goal

Extend `LanguageDetectionProbe` so a gather over a Node fixture that declares `express` in `dependencies` and ships a `turbo.json` produces a `schema_slice` containing `language_stack.framework_hints == ["express"]` and `language_stack.monorepo == {"tool": "turbo", "markers": ["turbo.json"]}`, with the existing Phase 0 counts/primary fields unchanged.

## Acceptance criteria

- [ ] **AC-1 — Post-walk read + memo seam.** `src/codegenie/probes/language_detection.py` adds a post-walk pass that resolves `pkg_path = snapshot.root / "package.json"`, skips when absent, and otherwise reads via `ctx.parsed_manifest(pkg_path)` *if* `ctx.parsed_manifest is not None`, *else* falls back to direct `safe_json.load(pkg_path, max_bytes=5 * 1024 * 1024)` (edge case 12 — `ctx.parsed_manifest is None`). The fallback path MUST go through `parsers.safe_json` — no bare `json.load`.
- [ ] **AC-2 — Framework hints from seed dict.** `framework_hints: list[str]` is built from the constant seed dict `{"@nestjs/core": "nestjs", "express": "express", "fastify": "fastify", "next": "next", "koa": "koa", "@hapi/hapi": "hapi"}` against the **union** of `dependencies.keys() | devDependencies.keys()` (both treated as empty `{}` when absent or `None`). Result is `sorted(set(mapped_values))` — deterministic, deduped. Non-seed deps (`lodash`, `react`, etc.) do not appear.
- [ ] **AC-3 — Monorepo detection + deterministic precedence.** `monorepo: MonorepoBlock | None` is built from `Path.exists()` checks on `(pnpm-workspace.yaml, lerna.json, nx.json, turbo.json)` plus a `package.json#workspaces` truthy check. **Precedence** for the `tool` field (highest first): `pnpm-workspace.yaml → "pnpm-workspaces"`, `turbo.json → "turbo"`, `nx.json → "nx"`, `lerna.json → "lerna"`, `package.json#workspaces → "workspaces"`. Encoded as a single precedence-ordered tuple `_MONOREPO_PRECEDENCE: tuple[tuple[str, str], ...]` so a new tool is a one-line addition (no edits to branching logic). `monorepo is None` iff zero entries hit.
- [ ] **AC-4 — `markers` list shape.** `monorepo.markers: list[str]` is the lexicographically-sorted union of *all* hit marker filenames. `package.json` is included in `markers` whenever `package.json#workspaces` is truthy, regardless of which marker determined `tool`. Marker filenames are basenames only (never absolute paths).
- [ ] **AC-5 — `workspaces` field accepts both shapes.** A `workspaces` value that is a non-empty list (`["packages/*"]`), a non-empty object (`{"packages": [...]}`), or any other truthy value triggers detection. `workspaces` that is `null`, `[]`, `{}`, `false`, or absent is treated as not-present.
- [ ] **AC-6 — `declared_inputs` extended additively.** `declared_inputs` adds `"package.json"`, `"pnpm-workspace.yaml"`, `"lerna.json"`, `"nx.json"`, `"turbo.json"`; the Phase 0 extension globs are preserved **verbatim** (no removals, no reorderings of existing entries). A regression test (`test_declared_inputs_additive`) asserts the Phase 0 entries appear as a contiguous prefix.
- [ ] **AC-7 — Sub-schema extends `language_stack` strictly.** `src/codegenie/schema/probes/language_detection.schema.json` adds `framework_hints: array<string>` and `monorepo: object | null` (when object: `{tool: string, markers: array<string>}` with `additionalProperties: false`), sets `additionalProperties: false` at the slice root, and includes `pattern: "^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$"` on **both `warnings[]` and `errors[]`** items (per ADR-0007 line 50 — same pattern applies to both fields).
- [ ] **AC-8 — Phase 0 fields byte-stable.** Running the extended probe on a Phase 0 fixture (`tests/fixtures/<phase-0-fixture>/`) produces a slice whose existing keys (`counts`, `primary`, `total_files`, `detected_languages` — whatever Phase 0 shipped) are **byte-equal** to the Phase 0 baseline output. New keys (`framework_hints`, `monorepo`) are additive; no existing key is renamed or removed.
- [ ] **AC-9 — ADR-0004 rejection test exists.** A synthetic envelope with an extra field under `probes.language_detection.language_stack` is rejected by the sub-schema with `SchemaValidationError` at the expected JSON Pointer (`/probes/language_detection/language_stack/<rogue_field>`).
- [ ] **AC-10 — ADR-0007 pattern test exists.** An ID violating the regex (e.g., `"This Helm chart looks production-ready"`, `"CamelCase.id"`, `"missing_dot"`) inserted into either the slice's `warnings[]` or the `ProbeOutput.errors[]` fails sub-schema validation; the three IDs this extension can emit (`package_json.size_cap_exceeded`, `package_json.symlink_refused`, `package_json.malformed`) all pass.
- [ ] **AC-11 — Failure-mode semantics.** When `package.json` is absent: `framework_hints == []`, `monorepo is None`, `out.errors == []`, the existing Phase 0 fields are unchanged, and `confidence` matches Phase 0 baseline (typically `"high"`). When `package.json` raises `SizeCapExceeded`: `framework_hints == []`, `monorepo is None`, `out.errors == ["package_json.size_cap_exceeded"]`, `out.confidence == "medium"`. When `package.json` raises `SymlinkRefusedError`: same shape but `out.errors == ["package_json.symlink_refused"]` and `out.confidence == "low"` (per arch §"Component design" #1 — symlink is the lower-trust failure). When `package.json` raises `MalformedJSONError` (valid bytes, invalid JSON): `out.errors == ["package_json.malformed"]`, `out.confidence == "medium"`.
- [ ] **AC-12 — Compile-time ID discipline.** Module-level `_ERRORS: frozenset[str] = frozenset({"package_json.size_cap_exceeded", "package_json.symlink_refused", "package_json.malformed"})` is asserted at module import against the ADR-0007 regex (fail-loud, Rule 12). A unit test (`test_module_import_asserts_error_ids`) verifies the assertion fires when a malformed ID is injected (via a test-only side door or via patching `_ERRORS` and re-importing).
- [ ] **AC-13 — Tooling green.** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/probes/language_detection.py`, and `pytest tests/unit/probes/test_language_detection_extended.py` all pass. No new `# type: ignore`, no new `Any`.

## Implementation outline

1. Open `src/codegenie/probes/language_detection.py`. Add module-level constants:
   - `_FRAMEWORK_SEED: Mapping[str, str]` — `MappingProxyType`-wrapped immutable view.
   - `_MONOREPO_PRECEDENCE: tuple[tuple[str, str], ...]` — precedence-ordered `((marker_filename, tool_name), ...)`. Last entry is `("package.json", "workspaces")` (the `#workspaces`-only fallback). New monorepo tools are inserted as a single new tuple entry — **no edits to branching logic** (Open/Closed at the file boundary).
   - `_ERRORS: frozenset[str]` — the three error IDs (`package_json.size_cap_exceeded`, `package_json.symlink_refused`, `package_json.malformed`). Module-import-time assertion (Rule 12): every entry matches the ADR-0007 regex.
2. Extend the class's `declared_inputs` tuple additively (re-read `../phase-arch-design.md §"Component design" #1` — five entries added; Phase 0 globs kept as the contiguous prefix).
3. In `run(...)`, after the existing extension-walk pass, add a post-walk block:
   - Resolve `pkg_path = snapshot.root / "package.json"`. Skip if absent (then `framework_hints == []`, `monorepo is None`, `errors == []`, Phase 0 confidence preserved).
   - Read `package.json`: `pkg = ctx.parsed_manifest(pkg_path) if ctx.parsed_manifest is not None else safe_json.load(pkg_path, max_bytes=5 * 1024 * 1024)`. Wrap in `try/except (SizeCapExceeded, SymlinkRefusedError, MalformedJSONError) as exc`:
     - Map exception type → error ID via a small dict literal `{SizeCapExceeded: "package_json.size_cap_exceeded", SymlinkRefusedError: "package_json.symlink_refused", MalformedJSONError: "package_json.malformed"}`. Append to `errors`.
     - Set `confidence`: `"low"` for `SymlinkRefusedError`, `"medium"` for the other two (per arch §"Component design" #1).
     - Leave `framework_hints = []`, `monorepo = None` and continue (degraded, not raised).
   - Compute `framework_hints`: union `dependencies.keys() | devDependencies.keys()` (default each to `{}` when missing or `None`); intersect with `_FRAMEWORK_SEED.keys()`; map via the dict; `sorted(set(...))`.
   - Compute `monorepo`: single linear scan over `_MONOREPO_PRECEDENCE`:
     - For each `(filename, tool_name)`: if `filename == "package.json"`, test `bool(pkg.get("workspaces"))` for truthiness (handles list, dict, missing-as-falsy); else test `(snapshot.root / filename).exists()`.
     - Track the *first* hit as the `tool` (precedence-respecting).
     - Track *all* hits' filenames in `markers_set: set[str]`. (Include `"package.json"` whenever the workspaces-truthy check hit.)
     - If `markers_set` is empty: `monorepo = None`. Else: `monorepo = {"tool": <first_hit>, "markers": sorted(markers_set)}`.
4. Augment `schema_slice["language_stack"]` with `framework_hints` and `monorepo`. Keep existing Phase 0 keys **byte-identical** in shape and order. The probe builds `ProbeOutput(..., errors=errors_list, schema_slice={"language_stack": {...}})` — error IDs go on `ProbeOutput.errors`, not on the slice's `warnings[]`.
5. Extend `src/codegenie/schema/probes/language_detection.schema.json`:
   - `language_stack.framework_hints`: `{"type": "array", "items": {"type": "string"}}`.
   - `language_stack.monorepo`: `{"type": ["object", "null"], "properties": {"tool": {"type": "string"}, "markers": {"type": "array", "items": {"type": "string"}}}, "required": ["tool", "markers"], "additionalProperties": false}`.
   - `language_stack` itself: `additionalProperties: false` at the slice root (ADR-0004).
   - `language_stack.warnings[]` AND `language_stack.errors[]` (if the latter is declared in the slice) both gain `pattern: "^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$"` per ADR-0007 line 50.
   - Preserve all Phase 0 properties unchanged.
6. The `MappingProxyType` wrap on `_FRAMEWORK_SEED` is the cheap immutability fence; `_MONOREPO_PRECEDENCE` is a tuple-of-tuples (already immutable); `_ERRORS` is a `frozenset`. No mutable module-level state.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/unit/probes/test_language_detection_extended.py`

Write **ten** red tests. Tests T-1 through T-5 drive the Green block; T-6 through T-10 land during Refactor and cover failure modes + the property/determinism invariants. Every test names *why* it would fail under a wrong implementation (Rule 9).

```python
# tests/unit/probes/test_language_detection_extended.py

import asyncio
from pathlib import Path
import pytest


# T-1 — framework hints positive AND negative case (would fail under "always return ['express']" hardcode)
def test_framework_hints_detected_from_deps_and_devdeps(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export {}")
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"express": "^4.0.0", "lodash": "^4.0.0"},'
        ' "devDependencies": {"fastify": "^4.0.0"}}'
    )
    out = _run_probe(tmp_path)
    hints = out.schema_slice["language_stack"]["framework_hints"]
    # Positive: both seed-dict matches present, mapped to framework names
    assert hints == ["express", "fastify"]  # sorted, deduped
    # Negative: non-seed deps absent (would fail under naive "return all dep keys")
    assert "lodash" not in hints


# T-2 — monorepo detection with precedence-respected `tool` + union markers
def test_monorepo_detected_via_turbo_marker(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"workspaces": ["packages/*"]}')
    (tmp_path / "turbo.json").write_text('{"$schema": "https://turbo.build/schema.json"}')
    out = _run_probe(tmp_path)
    monorepo = out.schema_slice["language_stack"]["monorepo"]
    assert monorepo is not None
    assert monorepo["tool"] == "turbo"  # turbo beats workspaces fallback
    assert monorepo["markers"] == ["package.json", "turbo.json"]  # sorted union


# T-3 — Phase 0 fields byte-stable when extension fires
def test_no_package_json_leaves_phase0_fields_byte_stable(tmp_path: Path) -> None:
    (tmp_path / "a.go").write_text("package main")
    out = _run_probe(tmp_path)
    stack = out.schema_slice["language_stack"]
    assert stack["framework_hints"] == []
    assert stack["monorepo"] is None
    # Phase 0 contract — these keys must still be present and shape-identical
    assert "counts" in stack
    # Regression: when the same fixture runs through a Phase 0 baseline serializer, the
    # Phase 0 keys must match byte-for-byte. Helper `_phase0_baseline_keys(tmp_path)` runs
    # a minimal Phase-0-shaped serialization and returns a sorted key list. Adding/removing
    # a Phase 0 key here would fail this assertion.
    assert sorted(k for k in stack.keys() if k not in {"framework_hints", "monorepo"}) \
        == _phase0_baseline_keys(tmp_path)


# T-4 — ADR-0004 extra-field rejection at the JSON Pointer level
def test_sub_schema_rejects_extra_field_under_language_detection() -> None:
    from codegenie.schema import load_envelope_validator
    envelope = _minimal_envelope_with(
        probe_block="language_detection",
        extras={"language_stack": {"counts": {}, "primary": None,
                                   "framework_hints": [], "monorepo": None,
                                   "warnings": [], "errors": [], "rogue_field": "x"}},
    )
    with _expect_schema_violation_at("/probes/language_detection/language_stack/rogue_field"):
        load_envelope_validator().validate(envelope)


# T-5 — ADR-0007 pattern applies to BOTH warnings[] and errors[]
@pytest.mark.parametrize("field,bad_id,good_id", [
    ("warnings", "This Helm chart looks production-ready", "package_json.size_cap_exceeded"),
    ("warnings", "CamelCase.id",                           "package_json.symlink_refused"),
    ("errors",   "missing_dot",                            "package_json.malformed"),
    ("errors",   "trailing.",                              "package_json.size_cap_exceeded"),
])
def test_warning_and_error_id_pattern_enforced(field: str, bad_id: str, good_id: str) -> None:
    from codegenie.schema import load_envelope_validator
    bad_env  = _envelope_with_language_stack({field: [bad_id]})
    good_env = _envelope_with_language_stack({field: [good_id]})
    with pytest.raises(Exception):  # SchemaValidationError
        load_envelope_validator().validate(bad_env)
    load_envelope_validator().validate(good_env)  # passes


# T-6 — Refactor: size-cap → confidence=medium + errors[]; landing the typed-exception branch
def test_oversized_package_json_demotes_confidence_via_errors(tmp_path: Path) -> None:
    # 6 MB payload, > 5 MB cap
    (tmp_path / "package.json").write_text('{"x": "' + ("A" * (6 * 1024 * 1024)) + '"}')
    out = _run_probe(tmp_path)
    assert out.confidence == "medium"  # per arch §"Component design" #1
    # ADR-0007: typed-exception IDs go in errors[], not warnings[]
    assert "package_json.size_cap_exceeded" in out.errors
    assert out.schema_slice["language_stack"]["framework_hints"] == []
    assert out.schema_slice["language_stack"]["monorepo"] is None


# T-7 — Refactor: symlink-refused → confidence=low + errors[]
def test_symlink_package_json_refused_demotes_to_low(tmp_path: Path) -> None:
    # package.json is a symlink pointing OUTSIDE the repo root
    outside = tmp_path.parent / "outside.json"
    outside.write_text('{"dependencies": {"express": "^4.0.0"}}')
    (tmp_path / "package.json").symlink_to(outside)
    out = _run_probe(tmp_path)
    # Per arch §"Component design" #1: symlink-out-of-repo → confidence: low
    assert out.confidence == "low"
    assert "package_json.symlink_refused" in out.errors
    # The express hint must NOT leak through — the symlink was refused before parse
    assert out.schema_slice["language_stack"]["framework_hints"] == []


# T-8 — Refactor: malformed JSON → confidence=medium + errors[]
def test_malformed_package_json_demotes_to_medium(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"dependencies": {"express": "^4.0.0"')  # truncated
    out = _run_probe(tmp_path)
    assert out.confidence == "medium"
    assert "package_json.malformed" in out.errors
    assert out.schema_slice["language_stack"]["framework_hints"] == []


# T-9 — Memo seam: ctx.parsed_manifest is called when available; falls back when None
def test_memo_consumed_when_available_and_fallback_when_none(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"dependencies": {"express": "^4.0.0"}}')

    # Case A: memo present — probe must call it (load-bearing for S2-04 warm path)
    calls: list[Path] = []
    def memo(path: Path):
        calls.append(path)
        import json
        return json.loads((tmp_path / "package.json").read_text())
    out_a = _run_probe(tmp_path, ctx_overrides={"parsed_manifest": memo})
    assert len(calls) == 1
    assert calls[0] == (tmp_path / "package.json")
    assert out_a.schema_slice["language_stack"]["framework_hints"] == ["express"]

    # Case B: memo None — probe falls back to safe_json.load (edge case 12)
    out_b = _run_probe(tmp_path, ctx_overrides={"parsed_manifest": None})
    assert out_b.schema_slice["language_stack"]["framework_hints"] == ["express"]


# T-10 — Determinism property: framework_hints is sorted + deduped regardless of input order
@pytest.mark.parametrize("dep_order", [
    [("next", "^14"), ("express", "^4"), ("fastify", "^4")],
    [("fastify", "^4"), ("next", "^14"), ("express", "^4")],
    [("express", "^4"), ("next", "^14"), ("fastify", "^4")],
])
def test_framework_hints_deterministic_sort_and_dedup(tmp_path: Path, dep_order) -> None:
    import json
    deps = dict(dep_order)
    # Also put `express` in devDependencies to force a dedup
    (tmp_path / "package.json").write_text(json.dumps({
        "dependencies": deps,
        "devDependencies": {"express": "^4"},
    }))
    hints = _run_probe(tmp_path).schema_slice["language_stack"]["framework_hints"]
    assert hints == ["express", "fastify", "next"]  # lexicographic, deduped
```

Helpers (`_run_probe`, `_phase0_baseline_keys`, `_envelope_with_language_stack`, `_expect_schema_violation_at`, `_minimal_envelope_with`) live at the top of the test file. `_run_probe(path, ctx_overrides=None)` accepts an optional `ctx_overrides` dict so T-9 can inject a sentinel `parsed_manifest`.

Also: extend `tests/unit/probes/test_language_detection.py` (or a new sibling) with:
- **`test_declared_inputs_additive`** — asserts `LanguageDetectionProbe.declared_inputs[: len(PHASE_0_INPUTS)] == PHASE_0_INPUTS` (the Phase 0 entries are a contiguous prefix; the five new entries follow).
- **`test_module_import_asserts_error_ids`** — monkey-patch `_ERRORS` to include `"BadID"`, reload module, assert `AssertionError` on import.

The first five tests red on `KeyError`/`AssertionError` once the new fields aren't emitted. Run, confirm red, commit, then Green.

### Green — make it pass

Add the post-walk block to `LanguageDetectionProbe.run`:

- Build `framework_hints` from the seed-dict intersection + `sorted(set(...))`.
- Build `monorepo` from a single linear scan over `_MONOREPO_PRECEDENCE`; first hit wins for `tool`, all hits union into `markers`.
- Emit both keys into `schema_slice["language_stack"]`.

Extend `language_detection.schema.json`:

- `framework_hints` + `monorepo` property entries under `language_stack`.
- `additionalProperties: false` on the slice (ADR-0004).
- `monorepo` accepts `null` or `{tool, markers}` with `additionalProperties: false`.
- Pattern constraint on both `warnings[]` and `errors[]` items (ADR-0007).

No try/except for failure modes yet; tests T-1 through T-5 should pass before T-6.

### Refactor — clean up

- Wrap the `package.json` read in `try/except (SizeCapExceeded, SymlinkRefusedError, MalformedJSONError) as exc` (narrow — do NOT catch bare `Exception` / `OSError`; Rule 12). Map exception type → error ID and confidence level per AC-11.
- Append the mapped ID to `errors`. Leave both new fields default-empty.
- Add the `_ERRORS` frozenset + module-import-time assertion against the ADR-0007 regex.
- Add a module-import-time assertion that `_MONOREPO_PRECEDENCE[-1][0] == "package.json"` (the fallback is correctly placed last).
- Docstring on the probe explaining the memo-vs-fallback path and naming the four edge-case rows it covers (rows 2, 3, 11, 12 of `phase-arch-design.md §"Edge cases"`).
- `mypy --strict` clean; `ruff check` clean. No new `Any`, no new `# type: ignore`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/language_detection.py` | In-place edit: add post-walk pass + `_FRAMEWORK_SEED` + `_MONOREPO_PRECEDENCE` + `_ERRORS`; extend `declared_inputs` additively; module-import assertions for ID pattern + precedence-tuple invariants. |
| `src/codegenie/schema/probes/language_detection.schema.json` | Add `framework_hints` + `monorepo`; set `additionalProperties: false` at slice root; add pattern constraint on **both** `warnings[]` and `errors[]` (ADR-0007). |
| `tests/unit/probes/test_language_detection_extended.py` | New test file — ten tests (T-1..T-10) anchoring framework hints (positive + negative), monorepo precedence, Phase 0 field stability, ADR-0004 extra-field rejection, ADR-0007 pattern on both fields, size-cap/symlink/malformed failure modes, memo seam consumption, deterministic sort/dedup property. |
| `tests/unit/probes/test_language_detection.py` (or sibling) | Add `test_declared_inputs_additive` + `test_module_import_asserts_error_ids` (Phase 0 entries are contiguous prefix; ADR-0007 compile-time assertion fires). |

## Out of scope

- **`NodeBuildSystemProbe`** — handled by S2-02.
- **Fixture `node_typescript_helm/`** — handled by S2-03.
- **Warm-path memo + cache-hit integration tests** — handled by S2-04 and S2-05.
- **`tree-sitter` invocation for ambiguous extensions** — Phase 2 (`../phase-arch-design.md §"Path to production end state"`).
- **Monorepo package-graph enumeration (workspaces traversal)** — Phase 2.
- **Editing `ProbeContext`** — already landed in S1-06; this story consumes it only.
- **Changes to the Phase 0 envelope-level `probes.*: additionalProperties: true`** — ADR-0004 keeps the envelope loose by design.

## Notes for the implementer

- **The memo path is the load-bearing seam for S2-04.** If you bypass `ctx.parsed_manifest` and call `safe_json.load` directly even when the memo is available, the warm-path test in S2-04 will see `probe.memo.hit == 0` and fail. The pattern is: `if ctx.parsed_manifest is not None: pkg = ctx.parsed_manifest(pkg_path); else: pkg = safe_json.load(...)`. Defensive-check the `None` per edge case 12. T-9 anchors this seam.
- **Deterministic ordering matters.** Phase 1 commits `repo-context.yaml` to a golden in S6-01. `framework_hints` must be **sorted lexicographically** after dedup; `monorepo.markers` must be sorted; the seed-dict iteration order must not leak into output. Use `sorted(...)` explicitly; do not rely on dict-insertion order. T-10's parametrized property test is the contract.
- **Error IDs go on `ProbeOutput.errors`, not on the slice's `warnings[]`** (per ADR-0007 line 50: `errors` = typed-exception-raised, `warnings` = soft-degrade). The slice's `warnings[]` is preserved as an empty array for forward compatibility — Phase 2's `IndexHealthProbe` will populate it with non-exception soft-degrade signals. The three IDs this probe emits (`package_json.size_cap_exceeded`, `package_json.symlink_refused`, `package_json.malformed`) are all exception-derived, so all three go in `errors`. T-6, T-7, T-8 anchor each one.
- **The three error IDs are shared with S2-02 and S3-05.** Define them in `_ERRORS` here, OR wait for S1-10 to register them globally and import from there. Do not define a third copy in a separate probe. (If S1-10 has shipped its registry by the time you start, prefer the import.)
- **Open/Closed at the file boundary: monorepo precedence.** `_MONOREPO_PRECEDENCE: tuple[tuple[str, str], ...]` is the *single* place a new monorepo tool can be added — append (or insert at the correct precedence index) one tuple entry and the linear scan in `run(...)` picks it up. Do NOT introduce `if filename == "...": ...` branches in the scan. This is the rule-of-three threshold: 5 monorepo tools already; Phase 2's `pants`/`bazel`/`buck` additions would push to 8+. Encoding precedence as data not control flow keeps the kernel stable.
- **Rule-of-three deferral.** `_FRAMEWORK_SEED` is single-use today (only `LanguageDetectionProbe` consumes it). Per Rule 2 — three similar lines is better than premature abstraction — keep it inline. Do NOT extract to a `catalogs/frameworks.yaml` YAML file yet. The right moment to extract is when a second consumer arrives (Phase 2 polyglot detection for Python/Go frameworks is the candidate); at that point a small `catalogs/frameworks.yaml` per-language file makes sense. Same deferral for `_MONOREPO_PRECEDENCE` — single-use today; extract only when Phase 2's `IndexHealthProbe` or a recipe needs the same data.
- **Type the slice shape explicitly.** Use `TypedDict` for `MonorepoBlock` (`tool: str, markers: list[str]`) and for the framework-hints output. mypy --strict will catch shape regressions where Phase 0 fields are accidentally dropped. Do NOT use bare `dict[str, Any]` for the slice — the slice is the contract.
- **Extension by addition.** Even though this story edits `language_detection.py` in place, it is an additive edit: no removed lines, no changed signatures, no edits to `Probe` ABC. The `tests/unit/test_probe_contract.py` snapshot must continue to pass without regeneration here (only S1-06 regenerates it).
- **The sub-schema `additionalProperties: false` is at the slice root**, not at the envelope's `probes.*` level (this phase's ADR-0004 + Phase 0 ADR-0013). The Phase 0 envelope continues to allow unknown sub-probes (`probes.*: additionalProperties: true`); the strictness is per-slice. Do not change the envelope-level policy.
- **Warning/error-ID pattern.** Every ID string this probe can emit must round-trip through the sub-schema `pattern` constraint on **both** `warnings[]` and `errors[]` (ADR-0007 line 50). The compile-time `_ERRORS` assertion is the cheap pre-flight check; the schema validation in T-5 is the CI gate.
- **Confidence semantics (arch-internal conflict surfaced).** Arch §"Component design" #1 says size-cap → `medium`, symlink → `low`. Arch §"Edge cases" row 2 says size-cap → `low`. This story sides with §"Component design" #1 (the more detailed component-level prescription, and the section the story cites). If the arch is reconciled in a future patch to favor row 2, AC-11 and T-6 update together; flagged in the validation report. Do NOT silently change the confidence values mid-implementation — if you find a reason to disagree, surface it (Rule 7).
