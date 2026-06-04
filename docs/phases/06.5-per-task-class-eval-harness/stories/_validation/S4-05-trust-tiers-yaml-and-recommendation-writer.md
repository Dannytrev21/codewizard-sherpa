# Validation report — S4-05 `docs/trust-tiers.yaml` + recommendation writer

**Validated:** 2026-06-04
**Validator:** phase-story-validator
**Verdict:** HARDENED
**Findings:** 16 total — 5 block, 8 harden, 3 nit

The story's *goal* (ship `docs/trust-tiers.yaml` as CODEOWNERS-gated contract data with uncalibrated `bronze` candidate per ADR-0003 + ADR-0015; ship `write_recommendation` as the *only* side-effect surface of a `False→True` `evidence_sufficient` flip per ADR-0009; never read recommendation files as a control signal per Production ADR-0009 "humans always merge") is sound and traces directly to phase ADR-0003 / ADR-0009 and Production ADR-0009 / ADR-0015. **But the story as authored predates the S4-04 HARDENED contract surface and the actual `PromotionVerdict` field shape; an executor following it verbatim would (a) import `load_tier_config` / `TierConfig` from `codegenie.eval.promotion` (wrong module — they live in `tier_config.py` per S4-04 AC-1 HARDENED); (b) build a `sample_verdict` fixture with non-existent fields `chain_head` and `run_id` (those live on `BenchRunReport`, not `PromotionVerdict`); (c) call `PromotionVerdict.model_construct(...)` (forbidden by S4-04 AC-10 — full Pydantic validation is required); (d) leave `schema_version: 1` as a load-bearing-but-unspec'd literal in the YAML with no fence against silent v2 drift; (e) emit a static-introspection test so coarse it false-positives on any docstring containing "recommendations"; (f) write a `parents=True`-asserting test that admits a `parents=False` mutant.** Every issue is patchable in place → **HARDENED**, not RESCUE.

Conflict-resolution priority applied: **Consistency > Coverage > Test-Quality > Design-Patterns**. The dominant lens was Consistency — the story inherited several drifts from a pre-S4-04 draft. The Design-Patterns critic added one AC promotion (deterministic-time injection via keyword-only `now=None` parameter to keep the filename derivation a pure function) that was forced by Test-Quality F-TQ-2 and F-TQ-4, not gold-plating. The `schema_version` forward-compat fence was elevated from "decorative field" to load-bearing AC-7 because without it, silent v2 admission is exactly the kind of contract-data staleness `IndexHealthProbe` (B2) is designed to prevent in a different layer — the same discipline applies here.

---

## Critic: Consistency (lens: does the story contradict the hardened arch / ADRs / sibling stories?)

### F-CON-1 (BLOCK) — `load_tier_config` / `TierConfig` import path contradicts S4-04 HARDENED

S4-04 HARDENED Implementation outline §2 moved `TierConfig` + `load_tier_config` out of `codegenie.eval.promotion` into a dedicated `codegenie.eval.tier_config` module (functional-core / imperative-shell split — the only `import yaml` in `src/codegenie/eval/`). The original S4-05 TDD plan imported both symbols from `codegenie.eval.promotion`. An executor following this verbatim would either (a) fail import at red, then "fix" by adding a re-export in `promotion.py` (breaking the F-DP-3 discipline), or (b) move the symbols back, breaking S4-04. **Resolution:** every test import in §TDD switched to `from codegenie.eval.tier_config import load_tier_config, TierConfig`. AC-5 spells this out as a hard contract.

### F-CON-2 (BLOCK) — `sample_verdict` fixture references non-existent `PromotionVerdict` fields

The original §TDD `sample_verdict` set `chain_head` and `run_id` — those are `BenchRunReport` fields, not `PromotionVerdict` fields. With S1-02 HARDENED `extra="forbid"`, the constructor would raise `ValidationError` at fixture instantiation; every downstream test would fail at collect with no signal about the writer. **Resolution:** AC-9 + §TDD rewrote the fixture to populate all eight S1-02-required fields verbatim — `task_class`, `current_tier`, `target_tier`, `evidence_sufficient`, `reasons`, `lower_bound_95`, `threshold_at_target`, `requires_human_approval=True`. Notes-for-implementer carries the field reference for future contributors.

### F-CON-3 (BLOCK) — `PromotionVerdict.model_construct(...)` is forbidden by S4-04 AC-10

The original §TDD fixture suggestion mentioned `model_construct` as a "shortcut to skip validation." S4-04 AC-10 forbids this — fixtures must construct via full Pydantic validation so a future runner-output drift (e.g. tighter field constraints) cannot diverge from test fixtures. **Resolution:** §TDD pins `PromotionVerdict(...)` full construction; Notes-for-implementer references S4-04 AC-10 explicitly.

### F-CON-4 (HARDEN) — Bench-registration tier-validation test duplicates S4-04 AC-3

The original AC `"Bench-registration tier slugs are validated against the YAML at startup"` shipped a `test_unknown_tier_in_registration_raises_against_phase65_yaml` test relying on an undefined `registry_with_silver_min_cases` fixture. The test responsibility (PromotionGate constructor validates `task_class.min_cases_for_promotion` keys against `tier_config.thresholds`) belongs to S4-04 `test_promotion.py` AC-3, which already covers it for `min_cases_for_promotion` keys, `current_tiers` values, AND `thresholds` keys against the shipped YAML set. **Resolution:** AC-8 drops the duplicate and references S4-04 by name. Avoids the failure mode where two stories race on the same assertion with slightly-different fixtures.

### F-CON-5 (HARDEN) — `Status:` line format does not match HARDENED siblings

S4-04's validation report sets `**Status:** HARDENED (phase-story-validator, 2026-06-01)`. **Resolution:** S4-05 Status line updated to `**Status:** HARDENED (phase-story-validator, 2026-06-04)`.

### F-CON-6 (NIT) — `Depends on:` annotation undersells S4-04's split-module surface

The original `Depends on: S4-04 (PromotionGate.evaluate returns PromotionVerdict; TierConfig + load_tier_config exist)` did not say *where* `TierConfig`/`load_tier_config` live, which is exactly the failure F-CON-1 demonstrates. **Resolution:** annotation now names `src/codegenie/eval/tier_config.py` and the S4-04 AC-3 startup-validation behavior.

---

## Critic: Coverage (lens: do the ACs collectively guarantee the goal? edge cases?)

### F-COV-1 (BLOCK) — `sample_verdict` field-population invariants not enforced

Subsumed by Consistency F-CON-2. AC-9 + §TDD pin the eight required fields with explicit values; the fixture round-trips through full validation.

### F-COV-2 (BLOCK) — `schema_version` field is unspecified contract data; silent v2 drift admitted

The original AC body listed `schema_version: 1` in the YAML shape but never said what happens when `schema_version` is missing, equals `2`, or is accompanied by an unknown top-level key like `per_task_class_thresholds`. A v2 YAML with new keys would silently parse to v1 semantics — the worst kind of contract-data staleness. **Resolution:** AC-7 adds a forward-compat fence: `load_tier_config` accepts top-level keys ⊆ `{"schema_version", "thresholds", "current_tiers"}` only; raises `TierConfigInvalid` with exact `args` tuples for each of `unknown_key`, `schema_version_missing`, `schema_version != 1`. Three parametrized tests in `test_load_tier_config_forward_compat_fence` pin each branch.

### F-COV-3 (HARDEN) — Byte-identical reruns not asserted

ADR-0002 §Consequences pins "byte-identical across reruns" as a determinism contract. The original story tested filename, body content, and atomicity in isolation, but did not assert that the same `(verdict, now)` pair produces identical bytes on disk across two calls. **Resolution:** AC-18 + `test_writer_byte_identical_reruns_same_verdict_same_now` writes to two different out_dirs (to avoid `os.replace` clobbering) with the same fixed `now`; asserts `Path.read_bytes()` equality. Kills mutants that inject timestamps or random suffixes into the body.

### F-COV-4 (HARDEN) — Wire-up boundary with S4-02 was implicit

The original AC `"Recommendation writer is invoked from S4-02 only when --with-verdict is set"` named the trigger but never said *which* story owns the call-site test. Without an explicit boundary, the executor could either (a) duplicate the call-site test here (fragile against S4-02's HARDENED layout), or (b) skip it entirely on the assumption that S4-02 covers it. **Resolution:** AC-19 pins the boundary — this story exports the function; S4-02 owns and tests the call site. Auto-flip detection is explicitly deferred with a Notes-for-implementer rationale.

### F-COV-5 (NIT) — `current_tiers` mapping shape unpinned

The original `"loaded.current_tiers == {}"` was correct but didn't say what `current_tiers` is *for*. **Resolution:** AC-4 references ADR-0009 + Production ADR-0009 explicitly: empty until a human-authored PR promotes a task class; the empty mapping is the architecture's commitment to humans-always-merge.

---

## Critic: Test-Quality (lens: would the TDD plan catch an obviously wrong implementation? thin tests?)

### F-TQ-1 (BLOCK) — `model_construct` shortcut admits drift-blind tests

Subsumed by Consistency F-CON-3 + S4-04 F-TQ-1.

### F-TQ-2 (HARDEN) — Filename test admits constant-return mutant

The original §TDD asserted `re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z\.json", written.name)`. A mutant `_utc_iso_filename` that returns the constant string `"2000-01-01T00-00-00Z.json"` regardless of `now` would pass this test. **Resolution:** AC-12 adds two tests — `test_writer_filename_exact_with_injected_now` (exact-match on injected fixed `now`) and `test_writer_filename_default_now_within_10s` (±10s proximity against `datetime.now(UTC)` captured before/after the call). The pair kills both constant-return AND wrong-format mutants.

### F-TQ-3 (HARDEN) — `mkdir(parents=True)` test uses single nested level

A test like `out = tmp_path / "newdir"; write_recommendation(...); assert written.exists()` passes against both `parents=True` and `parents=False` (one level — `parents=False` works because the parent `tmp_path` exists). **Resolution:** AC-13 + `test_writer_creates_three_nested_levels` uses `tmp_path / "a" / "b" / "c"` — three levels deep. A `parents=False` mutant raises `FileNotFoundError` at `out_dir.mkdir(...)` and fails loudly.

### F-TQ-4 (HARDEN) — Byte-identical-rerun mutation coverage

Subsumed by Coverage F-COV-3.

### F-TQ-5 (BLOCK) — Atomic-write failure-path is asserted as "atomic" but not tested

The original "atomic write" claim asserted only the success path (no `.tmp` leftover after a successful call). A mutant that omits the `try/except + tmp.unlink(missing_ok=True)` branch would still pass the success-path test; only the failure path proves the cleanup. **Resolution:** AC-16 + `test_writer_cleans_up_tmp_when_os_replace_raises` monkeypatches `os.replace` to raise `OSError("disk full")`; asserts (a) the target file absent, (b) no `*.tmp` left in `out_dir`. Implementation must use `try/except OSError: tmp.unlink(missing_ok=True); raise` — the test fails without it.

### F-TQ-6 (BLOCK) — Static-introspection test false-positives on docstrings

The original test scanned `src/codegenie/**/*.py` and flagged any file containing the literal substring `"recommendations"`. A module that names a parameter `recommendations` in a docstring or logs a string containing the word would false-positive without any actual read. **Resolution:** AC-20 narrows the walk via AST role inspection — only string literals passed as arguments to read-shaped calls (`open`, `read_text`, `read_bytes`, `glob`, `iterdir`, `rglob`) are flagged, AND only if their parent `Call` resolves to a read function. `recommendation.py` is exempt. The walk is scoped to `src/codegenie/eval/` (not repo-wide) per phase-scoped Coverage F-COV-5 corollary.

### F-TQ-7 (NIT) — 200-byte UNCALIBRATED window is too tight

The original AC `"the first 200 bytes contain 'UNCALIBRATED'"` admits a SPDX header or licence preamble that pushes the disclaimer past byte 200. A future contributor adding a longer SPDX header would have to either strip comments (bad) or move the disclaimer earlier (acceptable but coupled). **Resolution:** AC-2 widens to 500 bytes — survives a Apache-2.0 / MIT-style SPDX header without forcing a comment-strip refactor.

---

## Critic: Design-Patterns (lens: does the prescribed implementation miss plugin/strategy/Open-Closed/DIP/hexagonal opportunities? primitive obsession? hidden state?)

### F-DP-1 (HARDEN) — `schema_version` forward-compat fence is a smart-constructor opportunity

The pure data-validation rejection of unknown keys + non-`1` schema version is the smart-constructor pattern at the loader layer — illegal states unrepresentable in the `TierConfig` value object. **Resolution:** AC-7 implements it; the fence lives in the loader, so the `TierConfig` dataclass remains structural-only. This mirrors S2-04's `RedactedSlice` smart-constructor discipline (Phase 2 ADR-0010).

### F-DP-2 (HARDEN) — `write_recommendation` mixes pure filename derivation with impure I/O

The original signature `write_recommendation(verdict, out_dir) -> Path` had the filename derivation inline with `datetime.now(UTC)`, an `os.replace`, an `os.chmod`, and a `Path.mkdir`. Testing the filename required monkeypatching `datetime.now` — fragile, and incompatible with byte-identical-rerun assertions. **Resolution:** AC-9 + AC-11 split:
  - `_utc_iso_filename(now: datetime) -> str` — pure helper; testable in isolation.
  - `write_recommendation(verdict, out_dir, *, now=None) -> Path` — impure shell; keyword-only `now` parameter enables deterministic-time injection.
The default `now=None → datetime.now(UTC)` keeps the public API ergonomic. This is functional-core / imperative-shell at the smallest scope — same discipline as the `_utc_iso_filename` helper in S4-02's audit JSON writer.

### F-DP-3 (held — Notes only) — Filename collision-resistance via short hex suffix

The architecture's `phase-arch-design.md §Dynamic view → Sequence` line 496 pins the filename literal as `<utc-iso>.json` (no `-<short>` hex suffix). Two writes in the same UTC second collide. The Design-Patterns critic suggested a `-<short>` BLAKE3 suffix mirroring S4-02's audit JSON convention. **Resolution:** held per **Consistency over Design-Patterns** priority — the arch dictates the filename literal; a divergence would require an architectural amendment. Notes-for-implementer documents the same-second collision as accepted residual; operators rarely flip verdicts twice in one second; if it happens, both writes contain the same verdict shape if the eval inputs are identical, so the loss is point-in-time advisory data only.

### F-DP-4 (held — Notes only) — Filename-helper duplication between S4-02 and S4-05

S4-02 names audit JSONs `<run_started_iso>-<short>.json` while S4-05 uses `<utc-iso>.json`. The Design-Patterns critic suggested consolidating into a shared `_paths.py` helper. **Resolution:** held — the two filename conventions are intentionally different (audit JSON is run-scoped with hex suffix; recommendation is point-in-time with no suffix per arch). Notes-for-implementer documents both conventions and instructs against unifying under pressure.

---

## Cross-cutting decisions

### Module constant `DEFAULT_RECOMMENDATION_DIR`

Mirroring S4-02's pattern of a module-top `Final[Path]` constant for the default output directory. AC-9 + `test_default_recommendation_dir_is_module_constant` pin the value. This is the smallest possible nod to "no magic strings" — the constant is single-sourced and the default expression in the public function references it. The Design-Patterns critic also flagged that the `_READ_CALL_NAMES` set in `recommendation.py` could be single-sourced for the AST-walk test; the recommendation is "single-source but optional" — the AST test redeclares the set locally for blast-radius isolation if the module ever moves.

### Test docstring scope correction

The original `test_recommendation_not_consumed.py` docstring said it walks `src/codegenie/**/*.py` but the implementation walked the same set. Coverage F-COV-5 narrowed scope to `src/codegenie/eval/` only. The docstring is updated to match the walk.

---

## Files touched

| Path | What changed |
|---|---|
| `docs/phases/06.5-per-task-class-eval-harness/stories/S4-05-trust-tiers-yaml-and-recommendation-writer.md` | Status → HARDENED; added Validation notes block with 16 findings; reorganized ACs from 12 implicit checkboxes to 22 numbered ACs grouped by surface (YAML / tier_config fence / writer / wire-up / write-only guard / quality); rewrote `sample_verdict` fixture to use 8 valid `PromotionVerdict` fields; switched every import to `codegenie.eval.tier_config`; added forward-compat fence ACs (AC-7) and tests; added byte-identical-rerun + cleanup-on-OSError tests; widened UNCALIBRATED window to 500 bytes; narrowed static-introspection walk to `src/codegenie/eval/` + AST-narrowed read-call detection; split filename into `_utc_iso_filename(now)` pure helper + `write_recommendation(..., *, now=None)` impure shell; added `DEFAULT_RECOMMENDATION_DIR` module constant. |

---

## Held findings (recorded, not promoted to ACs)

- **F-DP-3 — Short hex suffix on filename** — `phase-arch-design.md §Dynamic view → Sequence` line 496 dictates the literal `<utc-iso>.json`. Consistency wins over Design-Patterns. Notes-for-implementer documents same-second collision as accepted residual.
- **F-DP-4 — Shared `_paths.py` for filename helpers** — S4-02 and S4-05 use intentionally different filename conventions (audit JSON is run-scoped; recommendation is point-in-time). Premature abstraction.
- **`_REASON_FORMATS` catalog for the recommendation file** — not applicable; recommendation file content is `verdict.model_dump_json(indent=2)`, owned by `PromotionVerdict`'s Pydantic serializer. Reasons-format ownership lives in S4-04.

---

## Surfaced for follow-up (out of this story)

- **`phase-arch-design.md §Component design` carries `TierConfig`/`load_tier_config` references pointing at `promotion.py`** — already corrected by S4-04 HARDENED but the arch doc still names `promotion.py` in a couple of places. Filed for a doc-sweep PR; not blocking S4-05.
- **Auto-flip detection (`evidence_sufficient` False→True between consecutive runs writes a recommendation)** — Phase 6.5 ships the `--with-verdict` explicit trigger; the auto-flip CLI loop is documented in Notes-for-implementer and deferred.
- **Recommendation file consumers** — Phase 11/12 will read these files; `phase-arch-design.md §Open Q #7` covers the deferral. The static-introspection test (AC-20) protects the "write-only from this phase" invariant.
