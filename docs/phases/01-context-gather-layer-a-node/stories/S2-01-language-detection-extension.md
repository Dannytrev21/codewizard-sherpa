# Story S2-01 — `LanguageDetectionProbe` extension: `framework_hints` + `monorepo`

**Step:** Step 2 — Extend `LanguageDetectionProbe` and ship `NodeBuildSystemProbe`
**Status:** Ready
**Effort:** S
**Depends on:** S1-05 (catalogs loader; not strictly required here but its hard-fail-at-startup pattern is the precedent), S1-07 (`ParsedManifestMemo` — `ctx.parsed_manifest` must be wired and the `probe.memo.{hit,miss}` events registered)
**ADRs honored:** ADR-0002 (consumes `ctx.parsed_manifest`), ADR-0004 (`additionalProperties: false` at sub-schema root), ADR-0007 (warning-ID pattern), ADR-0010 (Layer A slices optional at envelope)

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

- [ ] `src/codegenie/probes/language_detection.py` adds a post-walk pass that reads `package.json` via `ctx.parsed_manifest(repo_root / "package.json")` (falling back to direct `safe_json.load` when `ctx.parsed_manifest is None`, per edge case 12), builds `framework_hints: list[str]` from a constant seed dict `{"@nestjs/core": "nestjs", "express": "express", "fastify": "fastify", "next": "next", "koa": "koa", "@hapi/hapi": "hapi"}` against the union of `dependencies + devDependencies`, and builds `monorepo: MonorepoBlock | None` from `Path.exists()` checks on `{pnpm-workspace.yaml, lerna.json, nx.json, turbo.json}` plus a `package.json#workspaces` presence check.
- [ ] `declared_inputs` is extended **additively** to include `"package.json"`, `"pnpm-workspace.yaml"`, `"lerna.json"`, `"nx.json"`, `"turbo.json"`; the Phase 0 extension globs are preserved verbatim (no removals).
- [ ] `src/codegenie/schema/probes/language_detection.schema.json` extends `language_stack` with `framework_hints: list[str]` and `monorepo: MonorepoBlock | null`, sets `additionalProperties: false` at the sub-schema root, and includes a `pattern` constraint on `warnings[]` items matching ADR-0007.
- [ ] An ADR-0004 rejection test exists: a synthetic envelope with an extra field under `probes.language_detection` is rejected with `SchemaValidationError` at the expected JSON Pointer.
- [ ] An ADR-0007 warning-ID test exists: emitting a warning whose ID violates the pattern fails sub-schema validation; emitting `package_json.size_cap_exceeded` and `package_json.symlink_refused` (the two warnings this extension can emit) passes.
- [ ] When `package.json` is absent: `framework_hints == []`, `monorepo == null`, the existing counts/primary fields are unaffected, and `confidence` is unchanged from Phase 0 behavior. When `package.json` raises `SizeCapExceeded` or `SymlinkRefusedError`, the slice is populated with `framework_hints: []`, `monorepo: null`, `confidence: "medium"` (per §"Component design" #1 failure behavior), warning emitted.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/probes/language_detection.py`, and `pytest tests/unit/probes/test_language_detection_extended.py` all pass.

## Implementation outline

1. Open `src/codegenie/probes/language_detection.py`. Add module-level constants: `_FRAMEWORK_SEED: Mapping[str, str]` and `_MONOREPO_MARKERS: tuple[str, ...]` (immutable; `MappingProxyType`-wrapped for the dict).
2. Extend the class's `declared_inputs` tuple additively. Re-read `../phase-arch-design.md §"Component design" #1` — the additions are five entries.
3. In `run(...)`, after the existing extension-walk pass, add a post-walk block:
   - Resolve `pkg_path = snapshot.root / "package.json"`. Skip if absent.
   - Call `ctx.parsed_manifest(pkg_path)` if `ctx.parsed_manifest is not None`, else `safe_json.load(pkg_path, max_bytes=5 * 1024 * 1024)`. Catch `SizeCapExceeded` and `SymlinkRefusedError` → emit the typed warning, leave `framework_hints` empty, set `confidence` to `"medium"`.
   - Union `dependencies` + `devDependencies` keys; intersect with `_FRAMEWORK_SEED.keys()`; map values via the dict; deterministic-sort the resulting list (lexicographic, dedup).
   - Build `monorepo`: walk markers; if `package.json` has a truthy `workspaces`, infer `tool="workspaces"` when no other marker hit, else attribute by marker file (`turbo.json → "turbo"`, `nx.json → "nx"`, `lerna.json → "lerna"`, `pnpm-workspace.yaml → "pnpm-workspaces"`). Collect marker filenames in `markers: list[str]` (sorted).
4. Augment `schema_slice["language_stack"]` with the two new keys. Keep existing keys byte-identical.
5. Extend `src/codegenie/schema/probes/language_detection.schema.json` — see §"Data model" prose under §"Component design" #1. Set `additionalProperties: false` at the slice root. Declare `monorepo` as `{type: ["object","null"], properties: {tool, markers}, additionalProperties: false}`. Declare `warnings[]` with `pattern` per ADR-0007.
6. Add `package_json.size_cap_exceeded` and `package_json.symlink_refused` to a module-level `_WARNINGS` frozenset (compile-time enforcement that the strings match ADR-0007 — fail at module import if any violates the pattern).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/probes/test_language_detection_extended.py`

Write **five** red tests (one per behavior contour). The first three are sufficient to drive Green; the last two refine confidence + warning handling and land during Refactor.

```python
# tests/unit/probes/test_language_detection_extended.py

import asyncio
from pathlib import Path

def test_framework_hints_detected_from_dependencies(tmp_path: Path) -> None:
    # arrange: a fixture with one .ts file and a package.json declaring express
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export {}")
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"express": "^4.0.0", "lodash": "^4.0.0"}}'
    )
    # act
    from codegenie.probes.language_detection import LanguageDetectionProbe
    probe = LanguageDetectionProbe()
    out = asyncio.run(probe.run(_snapshot(tmp_path), _ctx_with_memo(tmp_path)))
    # assert
    assert out.schema_slice["language_stack"]["framework_hints"] == ["express"]


def test_monorepo_detected_via_turbo_marker(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"workspaces": ["packages/*"]}')
    (tmp_path / "turbo.json").write_text('{"$schema": "https://turbo.build/schema.json"}')
    out = _run_probe(tmp_path)
    monorepo = out.schema_slice["language_stack"]["monorepo"]
    assert monorepo is not None
    assert monorepo["tool"] == "turbo"
    assert sorted(monorepo["markers"]) == ["package.json", "turbo.json"]


def test_no_package_json_leaves_extensions_intact(tmp_path: Path) -> None:
    # No package.json — existing Phase 0 behavior must hold; new fields default-empty
    (tmp_path / "a.go").write_text("package main")
    out = _run_probe(tmp_path)
    assert out.schema_slice["language_stack"]["framework_hints"] == []
    assert out.schema_slice["language_stack"]["monorepo"] is None
    # Phase 0 contract preserved
    assert "counts" in out.schema_slice["language_stack"]


def test_sub_schema_rejects_extra_field_under_language_detection() -> None:
    # ADR-0004 — extra-field rejection at the JSON-Pointer level
    from codegenie.schema import load_envelope_validator
    envelope = _minimal_envelope_with(
        probe_block="language_detection",
        extras={"language_stack": {"counts": {}, "primary": None,
                                   "framework_hints": [], "monorepo": None,
                                   "warnings": [], "rogue_field": "x"}},
    )
    with _expect_schema_violation_at("/probes/language_detection/language_stack/rogue_field"):
        load_envelope_validator().validate(envelope)


def test_oversized_package_json_demotes_confidence_with_typed_warning(tmp_path: Path) -> None:
    # Edge case 2 + ADR-0007 — typed warning ID matches the pattern
    (tmp_path / "package.json").write_text('{"x": "' + ("A" * (6 * 1024 * 1024)) + '"}')
    out = _run_probe(tmp_path)
    assert out.confidence == "medium"
    assert "package_json.size_cap_exceeded" in out.schema_slice["language_stack"]["warnings"]
```

The first three red on `KeyError`/`AssertionError` once the new fields aren't emitted. Run, confirm red, commit, then Green.

### Green — make it pass

Add the post-walk block to `LanguageDetectionProbe.run`:

- Build `framework_hints` from the dict-intersection + deterministic sort.
- Build `monorepo` from `Path.exists()` over the four marker filenames + `package.json#workspaces`.
- Emit both keys into `schema_slice["language_stack"]`.

Extend `language_detection.schema.json`:

- Two new property entries under `language_stack`.
- `additionalProperties: false` on the slice.
- `monorepo` allows `null` or `{tool, markers}` (no other properties).

No try/except for cap-exceeded yet; tests 1–4 should pass before test 5.

### Refactor — clean up

- Wrap the `package.json` read in a `try/except (SizeCapExceeded, SymlinkRefusedError, MalformedJSONError)` block. On catch: emit warning, set `confidence="medium"`, leave both new fields default.
- Add the `_WARNINGS` frozenset + a module-import-time assertion that each string matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` (fail loud, Rule 12).
- Docstring on the probe explaining the memo-vs-fallback path and naming the four edge-case rows it covers.
- `mypy --strict` clean; `ruff check` clean.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/language_detection.py` | In-place edit: add post-walk pass + `_FRAMEWORK_SEED` + `_MONOREPO_MARKERS` + `_WARNINGS`; extend `declared_inputs` additively. |
| `src/codegenie/schema/probes/language_detection.schema.json` | Add `framework_hints` + `monorepo`; set `additionalProperties: false` at slice root; add `warnings[].pattern`. |
| `tests/unit/probes/test_language_detection_extended.py` | New test file — five tests anchoring framework hints, monorepo detection, no-package.json fallback, ADR-0004 extra-field rejection, oversized-package.json confidence demotion. |

## Out of scope

- **`NodeBuildSystemProbe`** — handled by S2-02.
- **Fixture `node_typescript_helm/`** — handled by S2-03.
- **Warm-path memo + cache-hit integration tests** — handled by S2-04 and S2-05.
- **`tree-sitter` invocation for ambiguous extensions** — Phase 2 (`../phase-arch-design.md §"Path to production end state"`).
- **Monorepo package-graph enumeration (workspaces traversal)** — Phase 2.
- **Editing `ProbeContext`** — already landed in S1-06; this story consumes it only.
- **Changes to the Phase 0 envelope-level `probes.*: additionalProperties: true`** — ADR-0004 keeps the envelope loose by design.

## Notes for the implementer

- **The memo path is the load-bearing seam for S2-04.** If you bypass `ctx.parsed_manifest` and call `safe_json.load` directly even when the memo is available, the warm-path test in S2-04 will see `probe.memo.hit == 0` and fail. The pattern is: `if ctx.parsed_manifest is not None: pkg = ctx.parsed_manifest(pkg_path); else: pkg = safe_json.load(...)`. Defensive-check the `None` per edge case 12.
- **Deterministic ordering matters.** Phase 1 commits `repo-context.yaml` to a golden in S6-01. `framework_hints` must be **sorted lexicographically** after dedup; `monorepo.markers` must be sorted; the seed-dict iteration order must not leak into output. Use `sorted(...)` explicitly; do not rely on dict-insertion order.
- **The two new warning IDs (`package_json.size_cap_exceeded`, `package_json.symlink_refused`) are shared with S2-02 and S3-05.** Define them once in a module-level frozenset in `language_detection.py` and import them where reused — or wait for S1-10 to register them globally and import from there. Either way, do not define a third copy in a separate probe.
- **Extension by addition.** Even though this story edits `language_detection.py` in place, it is an additive edit: no removed lines, no changed signatures, no edits to `Probe` ABC. The `tests/unit/test_probe_contract.py` snapshot must continue to pass without regeneration here (only S1-06 regenerates it).
- **The sub-schema `additionalProperties: false` is at the slice root**, not at the envelope's `probes.*` level (ADR-0004 + ADR-0013). The Phase 0 envelope continues to allow unknown sub-probes; the strictness is per-slice.
- **Warning-ID pattern.** Every warning string this probe can emit must round-trip through the sub-schema `pattern` constraint. The compile-time `_WARNINGS` assertion is the cheap pre-flight check; the schema validation in tests is the CI gate.
