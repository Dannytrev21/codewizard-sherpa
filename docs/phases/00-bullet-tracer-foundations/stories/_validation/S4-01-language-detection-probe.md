# Validation report — S4-01 `LanguageDetectionProbe` + registration

**Validated:** 2026-05-13 by `phase-story-validator` v1
**Story file:** `../S4-01-language-detection-probe.md`
**Verdict:** **HARDENED**

## Summary

Three parallel critics returned **22 findings** (7 Coverage + 7 Test-Quality + 7 Consistency + 1 NIT; 7 block, 13 harden, 2 nit; 0 `NEEDS RESEARCH` — every gap was answerable from in-repo code, the existing `Probe` ABC, `cache/keys.py`, the S2-05 sub-schema + its test, and the adjacent stories S4-02 / S4-04). Stage 3 (researcher) was skipped.

The story had the **right Goal** and the right cross-phase framing (prelude pass anchor for Gap 4) but pre-hardening had three categories of structural defects that would have silently corrupted the vertical slice in implementation:

1. **`language_stack` wrapper mismatch with the on-disk sub-schema.** Arch + localv2 + this story + S4-04 all use `language_stack`. The S2-05 sub-schema (`language_detection.schema.json`) and its tests (`test_schema_validation.py:52–101`) do **not** wrap — the slice is `{counts, primary}` directly with `additionalProperties: false`. After S4-01 lands, S4-02 step 9 (envelope JSON Schema validation) would have failed on every gather. Per CLAUDE.md Rule 7 ("surface, don't average — pick the more authoritative source"), localv2 §5.1 A1 + arch §Gap 4 win over the S2-05 schema file. The fix ships in **this story's PR** as a coordinated sub-schema rewrite + test update.

2. **`declared_inputs` bare extensions silently match nothing.** Pre-hardening AC-1 listed `[".js", ".mjs", ...]` with "or the equivalent `**/*.<ext>` glob form" as an escape hatch. `cache/keys.py:declared_inputs_for` (lines 91–105) calls `snapshot.root.rglob(pattern)` — `rglob(".js")` returns files literally named `.js` (none). `content_hash_of_inputs([])` is constant → cache keys collide → false-positive warm-run cache hits that mask real source changes. The escape hatch is gone; glob form is mandatory.

3. **`layer`/`requires` class attributes are required by the ABC but missing from AC-1.** `Probe` ABC declares both as bare class attributes with **no defaults** (`src/codegenie/probes/base.py:54–63`). Story Notes line 164 pre-hardening said "do not set `requires=[...]`" — contradicting the ABC, which requires the field be set. Fixed: `layer="A"`, `requires=[]`.

All three are fixed below; fix #1 ships a coordinated in-PR amendment to the S2-05 sub-schema + its test (per Rule 7).

## Critic reports

### Stage 2A — Coverage critic

| # | Severity | Finding | Fix |
|---|---|---|---|
| C1 | block | No deny-list for `.git/`, `node_modules/`, `vendor/`, `dist/`, `build/`, `__pycache__/`, `.venv/`, `target/`, `out/`, `.next/`, `.cache/`. On any real repo, `node_modules` dwarfs source by 100×; `primary` becomes whatever the largest vendor tree contains. Phase 0 fixtures are clean so the smoke is green for the wrong reason. | Module-level `_SKIP_DIRS: frozenset[str]` — checked **before** recursion. AC-4. Red test #5 (1 root `.js` + 100 `node_modules/*/*.js` → counts == {"javascript": 1}). |
| C2 | harden | Case-insensitive extension lookup unspecified — `FOO.JS` on Linux ext4 counts as nothing. | Pin `.casefold()` in outline step 3. AC-4. Red test #6. |
| C3 | harden | Broken-symlink handling unspecified — `Path.resolve()` raises `FileNotFoundError`/`OSError` on dangling symlinks. | Split into `probe.symlink.broken` (broken) vs `probe.symlink.escaped` (escape). AC-4. Red test #9. |
| C4 | harden | Empty-repo `confidence` unpinned. | Pin `confidence="high"` (successful scan of zero files is evidence). AC-2. Red test #4. |
| C5 | harden | `os.scandir` access pattern is implementer-choice; S4-04 line 197 flags this as a gap. | Promote to AC-6: `import os`, declared in module docstring. |
| C6 | harden | Counter type unpinned. | Pin `dict(counter)` in outline step 4. AC-2. |
| C7 | nit | `version="0.1.0"` hardcoded; if sub-schema bumps, drift. | Implementer note: keep `version` in lockstep with sub-schema `$id`. |

### Stage 2B — Test-Quality critic

| # | Severity | Finding | Fix |
|---|---|---|---|
| T1 | block | Test 2 (`test_probe_output_passes_pydantic_validator`) references undefined `tmp_path_with_js_files` and `_run_probe`. Executor would fabricate them inconsistently across attempts. | Inlined `_snapshot(root)`, `_ctx(root)`, `_run(probe, root)` helpers in the TDD plan. |
| T2 | harden | `test_probe_contract_conformance` only asserts `declared_inputs != ["**/*"]`. Mutation `["**/*.py"]` (missing JS) survives. | Subset check: every value in `_EXT_TO_LANG` has a corresponding glob. AC-9, red test #3. |
| T3 | harden | Alpha tie-break has no test. Mutation `max(counts, key=counts.get)` (insertion-order tie-break) passes 2js+1py but breaks on 2js+2py. | Red test #7 (`test_primary_alpha_tiebreak`). |
| T4 | harden | Zero structlog assertions; mutation that drops `probe.failure` slips through. | Red tests #10 (failure path) + #11 (happy-path lifecycle). AC-7. |
| T5 | harden | `test_permission_error_demotes_confidence` named only — no implementation sketch; chmod-based simulation is non-deterministic on root-running CI. | Pinned to `monkeypatch.setattr(ld.os, "scandir", boom)`. Red test #10. |
| T6 | harden | Symlink-escape log payload says "sanitizer would scrub" — but structlog events don't pass through `OutputSanitizer.scrub` (ADR-0008 is a two-pass chokepoint on `RepoContext` emit). | Pin `str(Path(entry.path).relative_to(snapshot.root))` in outline step 3 + AC-4. Red test #8 asserts resolved target never in payload. |
| T7 | nit | Test 1 doesn't pin dict-key ordering of `counts`. | No change — `dict.__eq__` compares by key/value, not order; ordering is irrelevant here. |

### Stage 2C — Consistency critic

| # | Severity | Finding | Fix |
|---|---|---|---|
| K1 | block | `language_stack` wrapper mismatch with shipped sub-schema. (See Summary #1.) | AC-3 ships coordinated in-PR amendment: sub-schema `$id v0.1.0 → v0.1.1`; wraps `counts/primary` under `language_stack`; `primary: {"type": ["string", "null"]}`; `test_schema_validation.py` payloads updated; envelope `$ref` updated; new test `test_language_detection_primary_null_is_valid_for_empty_repo`. Probe `version` bumps `0.1.0 → 0.1.1` in lockstep. |
| K2 | block | `declared_inputs` bare extensions silently match nothing. (See Summary #2.) | AC-1 mandates glob form exactly; escape hatch removed. |
| K3 | block | `layer="A"` and `requires=[]` missing from AC-1. (See Summary #3.) Notes line 164 reworded. | AC-1 + AC-9 + Notes. |
| K4 | block | `primary` cannot be `None` per shipped sub-schema (`type: string`). Story AC-2 says `<lang-or-None>`. | Sub-schema amendment widens to `{"type": ["string", "null"]}`. AC-2 pins `None` for empty repo. |
| K5 | harden | `version` is convention, not ABC — confirm + document. | Implementer note added (Notes §`version` is convention). |
| K6 | harden | `ProbeOutput.raw_artifacts`, `duration_ms`, `warnings` unpinned. | AC-2 pins all three. Red test #1 asserts `raw_artifacts == []`, `warnings == []`, `duration_ms >= 0`. |
| K7 | nit | AC-7 contract-conformance test wording overlaps with `tests/unit/test_probe_contract.py`. | AC-9 reworded to "exact equality on each declared attribute; does not re-run the ABC fingerprint check." |

## Conflict resolution

| Conflict | Sources | Resolution | Rationale |
|---|---|---|---|
| `language_stack` wrapper present (arch, localv2, S4-04) vs absent (shipped sub-schema + S2-05 test) | `arch §Gap 4 line 970`, `localv2 §5.1 A1`, `S4-04:53,206` ↔ `schema/probes/language_detection.schema.json:8-22`, `test_schema_validation.py:52-101` | Wrapper wins; amend sub-schema + test in this PR. | Rule 7 — pick the more authoritative source. Localv2 + arch are the design intent; S2-05's schema is an implementation artifact that didn't match. The amendment fixes the artifact. |
| `primary` can be `None` (story AC-2 + S4-04 `in (None, "")`) vs must be `string` (shipped sub-schema `type: string`) | story AC-2, S4-04:53 ↔ `language_detection.schema.json:18-21` | Schema widens to `{"type": ["string", "null"]}`; AC-2 pins `None` on empty repo. | Same Rule 7 — design intent + downstream story tolerance win; schema lifts. |
| `requires` "do not set" (pre-hardened Notes line 164) vs "must be set, no default" (ABC `base.py:60`) | story Notes, base.py | ABC wins. | Code-level invariant beats a prose note. `requires=[]` (empty list) is the right encoding of "no upstream deps." |

## Edits applied to the story

Material changes (14) — see `Validation notes` block at the top of the hardened story for the canonical list. Summary of files touched and additions:

- **AC count: 8 → 11.** New ACs cover in-PR sub-schema amendment (AC-3), walker deny-list / case-folding / symlink trichotomy (AC-4), module-level structural pins (AC-6), structlog lifecycle events (AC-7), empty-repo Pydantic validation (AC-8). Existing ACs reworded for verifiability (AC-1, AC-2, AC-5, AC-9 strengthened; AC-10, AC-11 unchanged in intent).
- **Red tests: 3 → 12.** Added: empty-repo, vendor-dirs deny-list, case-insensitive extension, alpha tie-break, escaped symlink + log payload sanitization, broken symlink, PermissionError via monkeypatch, happy-path lifecycle, registration.
- **In-PR amendment files added to "Files to touch":** `schema/probes/language_detection.schema.json`, `schema/repo_context.schema.json`, `tests/unit/test_schema_validation.py`.
- **Notes section** expanded with `version` is convention, log payload sanitization is the probe author's responsibility (not the sanitizer's), and the in-PR amendment rationale.

## Verdict rationale — HARDENED

The story has the right Goal and the right cross-phase wiring (prelude pass for Gap 4, extension-scoped `declared_inputs` for the bullet tracer's cache-hit exit). The defects were all surgically fixable in place — no escape hatch in the Goal, no contradiction with phase invariants, and no missing dependency on an unspecified ADR. The single biggest fix (the `language_stack` wrapper amendment) is documented as a coordinated in-PR change rather than a downstream follow-up, per Rule 7.

The hardened story is ready for `phase-story-executor`.

## What "good" looked like for this story

- Every AC is now individually verifiable by a third party running a check (e.g., `LanguageDetectionProbe.layer == "A"`, `output.schema_slice["language_stack"]["primary"] is None`, `output.duration_ms >= 0`, a specific structlog event count).
- The AC set collectively guarantees the Goal — there is no path from "implementer reads ACs, ships code that satisfies all ACs" to "smoke fails."
- Every AC has at least one mutation-resistant red test in the TDD plan. The 12-test set covers extension counting, primary determinism (including alpha tie-break), Pydantic validation, the contract, empty repo, vendor-dir skipping, case-insensitivity, both symlink trichotomy branches, error-path confidence demotion, structlog lifecycle events, and registry presence.
- Cross-story conflicts are surfaced as coordinated in-PR amendments per CLAUDE.md Rule 7, not buried in follow-up debt.
