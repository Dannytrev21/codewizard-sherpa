# Story S6-02 — `ConventionsProbe` Layer D

**Step:** Step 6 — Ship Layer D + E + G probes (skills, conventions, ADRs, ownership, scanners)
**Status:** Done — GREEN 2026-05-17 (phase-story-executor; see [`_attempts/S6-02.md`](_attempts/S6-02.md) for the per-AC evidence table + gate log)
**Effort:** S
**Depends on:** S2-02 (`ConventionsCatalogLoader` with `load_all() -> Result[CatalogLoadOutcome, FatalLoadError]`, `Catalog.apply(repo) -> list[ConventionResult]`, the four `ConventionRule*` discriminated variants, and the `ConventionResult = Pass | Fail | NotApplicable` discriminated union with `Fail.evidence: str` and `NotApplicable.reason: str`); S6-01 (`SkillsIndexProbe` — the probe-shape precedent every Layer-D probe inherits from).
**ADRs honored:** 02-ADR-0006 (typed sum types as discriminated unions — `ConventionResult` matches the `IndexFreshness` discipline), 02-ADR-0003 (`@register_probe(heaviness=...)` registry kwarg — NOT a `Probe` ABC field), 02-ADR-0007 (no plugin loader in Phase 2; the loader is kernel-side), Phase 0 ADR-0007 (`Probe` ABC frozen byte-for-byte against `localv2.md §4` — `name: str`, `async def run(repo, ctx)`), Phase 1 ADR-0006 (`safe_yaml` chokepoint — the loader, not the probe, does YAML I/O).
**Phase-2 commitment honored:** "Facts, not judgments" (CLAUDE.md) — the probe reports `Pass | Fail | NotApplicable` per convention; it does not summarize, weight, or aggregate. The Planner decides what to do with the per-rule outcomes.

## Validation notes

**Hardened 2026-05-17 via `phase-story-validator`** (see [`_validation/S6-02-conventions-probe.md`](_validation/S6-02-conventions-probe.md) for the full audit log). Twenty-six in-place edits resolved thirteen `block`-severity contract mismatches between the original draft and the kernel S2-02 actually shipped (`src/codegenie/conventions/{model,catalog,loader}.py`). Six new ACs cover `FatalLoadError`, partial-success per-file errors, the three-state confidence policy mirroring S6-01, `ConventionId` newtype propagation, deterministic raw-artifact emission, and `Catalog.apply` memoization preservation. The `Fail` evidence shape was the structurally largest fix: the kernel's `Fail` model has only `rule_id: ConventionId` and `evidence: str` — `file`/`line`/`snippet` capture is out-of-scope for Phase 2 (would require an ADR amendment to the `Fail` model).

## Context

Org conventions like "All Node services must use tini as PID 1" or "Runtime image must not include npm/pnpm/yarn" are the boring, ubiquitous failure mode in autonomous migrations: a generic recipe produces a perfectly valid Dockerfile that violates the org's unwritten rules and gets bounced at review. The `ConventionsCatalogLoader` (S2-02) loads those rules from `~/.codegenie/conventions/*.yaml` and `.codegenie/conventions/*.yaml` (user + repo tiers) into a `Catalog` of pattern-typed rules; this probe applies the catalog to the analyzed-repo `RepoSnapshot` and emits one `ConventionResult` per rule.

The discriminated union is load-bearing. `ConventionResult = Pass | Fail | NotApplicable` is exhaustive — `mypy --warn-unreachable` enforces the `match` to be total. `Pass(rule_id=...)` means "the convention was checked and the repo conforms" (no evidence — the empty-information variant). `Fail(rule_id=..., evidence="...")` means "the convention was checked and the repo violates it, here is a short documented evidence string." `NotApplicable(rule_id=..., reason="...")` means "the convention's prerequisites aren't met" (e.g., the `dockerfile_pattern` convention on a repo with no `Dockerfile`). Conflating `NotApplicable` with `Pass` would silently mark services as conforming to rules they were never checked against — the "passing tests on a disabled feature" failure mode the toolkit's Open/Closed gap names verbatim.

The kernel does the heavy lifting. `ConventionsCatalogLoader.load_all()` returns `Result[CatalogLoadOutcome, FatalLoadError]`: the happy / partial path returns `Ok(CatalogLoadOutcome(catalog=catalog, per_file_errors=[...]))` where per-file errors (malformed YAML, unknown pattern type, symlink-refused, etc.) are *non-fatal* — other catalog files still load and produce rules. Only the catastrophic case where *every* entry in `search_paths` is unreadable surfaces as `Err(FatalLoadError(reason="no_search_path_readable", paths=[...]))`. The probe applies the kernel-side `Catalog.apply(repo)` (which itself memoizes by `id(repo)`, so two consecutive runs against the same `RepoSnapshot` instance read each repo file exactly once) and projects the returned `list[ConventionResult]` into a Pydantic-modeled `ConventionsSlice` carrying per-file errors as first-class slice content (NOT as a probe-level `errors[...]` field).

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md` §"Component design" #10 `ConventionsCatalogLoader`](../phase-arch-design.md) — pattern types as a Pydantic discriminated union; one `match` per pattern type with `assert_never`. *Note: line 608's public-interface signature is older than what S2-02 actually shipped; see the loader at `src/codegenie/conventions/loader.py:272` for the authoritative return type.*
  - [`../phase-arch-design.md` §"Design patterns applied"](../phase-arch-design.md) — discriminated unions for every state machine.
  - [`../phase-arch-design.md` §"Data model"](../phase-arch-design.md) `ConventionResult = Pass | Fail | NotApplicable`.
- **Phase ADRs:**
  - [`../ADRs/0006-index-freshness-sum-type-location.md`](../ADRs/0006-index-freshness-sum-type-location.md) — the same sum-type discipline `ConventionResult` follows: typed reason, not stringly-typed.
  - [`../ADRs/0003-coordinator-heaviness-sort-annotation.md`](../ADRs/0003-coordinator-heaviness-sort-annotation.md) — `@register_probe(heaviness=...)` is a registry kwarg, not a `Probe` ABC field.
- **Source design:**
  - [`../High-level-impl.md` §"Step 6"](../High-level-impl.md) — Conventions uses `ConventionsCatalogLoader` (Step 2).
  - [`../../localv2.md` §5.4 D5 ConventionProbe](../../../localv2.md) — example catalog with `dockerfile_pattern`, `dockerfile_pattern_inverted`, `file_pattern`, `missing_file` types.
  - [`./S6-01-skills-index-probe.md`](./S6-01-skills-index-probe.md) — **the probe-shape precedent for every Layer-D probe.** Async `run(repo, ctx)`; `_make_context` test helper; flat schema path; three-state confidence via `_compute_confidence`; `default_registry._entries` for the registry lookup; `_PROBE_ID: Final[ProbeId]` constant alongside `name: str` ABC attr.
- **Existing kernel (the authoritative contract for this probe):**
  - `src/codegenie/conventions/model.py` (S2-02) — `ConventionResult` discriminated union. `Pass(rule_id: ConventionId)`. `Fail(rule_id: ConventionId, evidence: str)`. `NotApplicable(rule_id: ConventionId, reason: str)`. All `frozen=True, extra="forbid"`, `Literal["pass"|"fail"|"not_applicable"]` discriminators on `kind`. *No `file`, `line`, or `snippet` on `Fail`.*
  - `src/codegenie/conventions/catalog.py` (S2-02) — `Catalog(BaseModel)` with `rules: list[ConventionRule]` and private `_memo: dict[int, list[ConventionResult]]`. `Catalog.apply(repo: RepoSnapshot) -> list[ConventionResult]` (memoized by `id(repo)`). Module-level `_apply_one` dispatcher with exhaustive `match` + `assert_never`. Four module-level `_apply_<kind>` helpers (NOT methods, NOT a shared `ScannerRunner`). Constants: `_REASON_NO_DOCKERFILE = "no_dockerfile_present"`, `_REASON_GLOB_EMPTY = "file_glob_no_matches"`.
  - `src/codegenie/conventions/loader.py` (S2-02) — `ConventionsCatalogLoader(search_paths).load_all() -> Result[CatalogLoadOutcome, FatalLoadError]`. `CatalogLoadOutcome(catalog: Catalog, per_file_errors: list[ConventionsError])`. `FatalLoadError(reason="no_search_path_readable", paths=[...])`. Default tier ordering: `[~/.codegenie/conventions/, .codegenie/conventions/]`.
  - `src/codegenie/probes/base.py` — `Probe` ABC + `ProbeContext` + `ProbeOutput`. Frozen byte-for-byte against `localv2.md §4`. `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`. `name: str` (NOT `probe_id`); `applies_to_tasks: list[str]` (NOT `tuple`); `ProbeOutput(schema_slice, raw_artifacts, confidence, duration_ms, warnings, errors)`.
  - `src/codegenie/probes/registry.py:238` — `default_registry: Registry`. `register.entries: list[ProbeRegEntry]`. The "look up heaviness" pattern: `next(e for e in default_registry._entries if e.cls.name == "conventions").heaviness == "light"`.
  - `src/codegenie/probes/layer_b/scip_index.py:114` — `_PROBE_ID: Final[ProbeId] = ProbeId("scip_index")` module-level constant alongside `name: str = "scip_index"`. The precedent for dual-form probe identity (str ABC attr + typed Final constant).
  - `src/codegenie/types/identifiers.py:29,42` — `ProbeId = NewType("ProbeId", str)`, `ConventionId = NewType("ConventionId", str)`. *NOT `codegenie.ids`.*
  - `src/codegenie/schema/probes/` — flat schema layout. The sub-schema for this probe lands at `src/codegenie/schema/probes/conventions.schema.json` (S6-08).

## Goal

Implement `src/codegenie/probes/layer_d/conventions.py` as a `@register_probe(heaviness="light")` probe that:

1. Resolves the two-tier search paths (`user` from `ctx.config.get("conventions.user_path", "~/.codegenie/conventions/")`, `repo` from `repo.root / ctx.config.get("conventions.repo_path", ".codegenie/conventions/")`).
2. Calls `ConventionsCatalogLoader(search_paths=...).load_all()` and pattern-matches `Result[CatalogLoadOutcome, FatalLoadError]`.
3. On `Ok(CatalogLoadOutcome(catalog=catalog, per_file_errors=errors))`: applies `catalog.apply(repo)` (preserving the kernel's `id(repo)` memo), projects the returned `list[ConventionResult]` into a frozen `ConventionsSlice` carrying the typed results in catalog-file order, the resolved search-path strings (operator observability + future S6-08 freshness check), the per-file errors round-tripped through the slice, and `rules_checked == len(results)` validated at construction.
4. On `Err(FatalLoadError(...))`: emits `confidence="low"` with `results=()`, `per_file_errors=` carrying the typed `FatalLoadError`-mapped error, `catalog_paths_resolved=` (the paths the loader attempted), `rules_checked=0`.
5. Derives `confidence: Literal["high","medium","low"]` via a pure `_compute_confidence(applied, per_file_errors)` helper: `"high"` clean (including empty catalog → no per-file errors and no rules), `"medium"` partial (some rules loaded AND some per-file errors), `"low"` total (per-file errors AND zero rules loaded, OR `FatalLoadError`).
6. Writes the canonical slice JSON to `ctx.output_dir / "conventions.json"` as the single raw artifact.

No aggregation, no summary counts beyond the trivial `len`, no per-rule fix suggestions, no inference, no LLM call. The Planner consumes the typed outcomes downstream.

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

- [ ] **AC-1.** `src/codegenie/probes/layer_d/conventions.py` exports exactly `__all__ = ["ConventionsProbe", "ConventionsSlice"]`.
- [ ] **AC-2.** `ConventionsSlice` is a Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` carrying exactly the fields:
  - `results: tuple[ConventionResult, ...]` (catalog-file order; NOT re-sorted)
  - `catalog_paths_resolved: tuple[str, ...]` (`as_posix()` of the user-tier and repo-tier paths the loader walked; empty tuple when the slice is from a `FatalLoadError` and `search_paths` was empty)
  - `per_file_errors: tuple[ConventionsError, ...]` (the loader's per-file errors round-tripped through the discriminated-union models)
  - `rules_checked: int`
  - A `@model_validator(mode="after")` raises `ValueError` if `rules_checked != len(results)` (smart-constructor; rejects hand-constructed slices that drift between the count and the list).
- [ ] **AC-3.** `ConventionsProbe` is `@register_probe(heaviness="light")`; declares the frozen `Probe` ABC fields verbatim:
  - `name: str = "conventions"`
  - `version: str = "0.1.0"`
  - `layer = "D"`
  - `tier = "base"`
  - `applies_to_tasks: list[str] = ["*"]`
  - `applies_to_languages: list[str] = ["*"]`
  - `requires: list[str] = []`
  - `timeout_seconds: int = 15`
  - `cache_strategy: Literal["content"] = "content"`
  - `declared_inputs: list[str]` includes `"Dockerfile"`, `"conventions_user_search_path:<expanded>"`, `"conventions_repo_search_path:.codegenie/conventions/"`.

  Module-level `_PROBE_ID: Final[ProbeId] = ProbeId("conventions")` is declared alongside (precedent: `src/codegenie/probes/layer_b/scip_index.py:114`). The probe MUST NOT introduce a class attribute named `probe_id` (ABC freeze; 02-ADR-0007).
- [ ] **AC-4.** `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` is the implementation entry point. It:
  1. Resolves `[user_tier, repo_tier]` via `_resolve_search_paths(repo, ctx)` (pure, see AC-5).
  2. Calls `ConventionsCatalogLoader(search_paths=resolved).load_all()`.
  3. Pattern-matches the `Result`:
     - On `Ok(CatalogLoadOutcome(catalog=catalog, per_file_errors=errors))`: invokes `catalog.apply(repo)` (passing the `RepoSnapshot` arg from `run`, NOT `ctx.repo_snapshot` — the latter does not exist). Constructs a `ConventionsSlice` with results in returned order, `catalog_paths_resolved=tuple(p.as_posix() for p in resolved)`, `per_file_errors=tuple(errors)`, `rules_checked=len(applied)`.
     - On `Err(FatalLoadError(reason="no_search_path_readable", paths=ps))`: constructs a `ConventionsSlice` with `results=()`, `catalog_paths_resolved=tuple(p.as_posix() for p in ps)`, `per_file_errors=()`, `rules_checked=0`.
  4. Writes the slice JSON to `ctx.output_dir / "conventions.json"` (atomic via `os.replace` from a sibling `.tmp` file).
  5. Returns `ProbeOutput(schema_slice=slice_.model_dump(mode="json"), raw_artifacts=[raw_path], confidence=_compute_confidence(applied, errors), duration_ms=int((time.perf_counter()-t0)*1000), warnings=warnings, errors=[])`. (The loader's per-file errors are inside the slice, NOT in `ProbeOutput.errors` — `ProbeOutput.errors` is reserved for probe-level failures the coordinator should isolate.)
- [ ] **AC-5.** `_resolve_search_paths(self, repo: RepoSnapshot, ctx: ProbeContext) -> list[Path]` is a pure method (no I/O):
  - `user_tier = Path(ctx.config.get("conventions.user_path", "~/.codegenie/conventions/")).expanduser()`
  - `repo_tier = repo.root / Path(ctx.config.get("conventions.repo_path", ".codegenie/conventions/"))`
  - returns `[user_tier, repo_tier]`. (Two tiers — Phase 2 ships without an org tier for conventions per `loader.py:262-270`.)
- [ ] **AC-6.** **`NotApplicable` is not `Pass`.**
  - A `dockerfile_pattern` rule run against a fixture with no `Dockerfile` yields `NotApplicable(rule_id=rule.id, reason="no_dockerfile_present")` — the kernel constant `_REASON_NO_DOCKERFILE` from `src/codegenie/conventions/catalog.py:51`. *Not* `"dockerfile_absent"`.
  - A `file_pattern` or `missing_file` rule whose `file_glob` matches no file in the repo yields `NotApplicable(rule_id=rule.id, reason="file_glob_no_matches")` — the kernel constant `_REASON_GLOB_EMPTY` from `catalog.py:52`. (Exception: `missing_file` with an empty glob is a `Pass` — the rule passes when no files match; the helper `_apply_missing_file` documents this inversion. The `file_pattern` variant treats an empty glob as `NotApplicable`.)
  - Mutation caught: any "if file doesn't exist, count it as pass" shortcut; any drift between the test and the kernel's documented constants.
- [ ] **AC-7.** **`Fail` carries documented evidence strings, not file/line/snippet.**
  - A `dockerfile_pattern` rule with no match in the repo's `Dockerfile` yields `Fail(rule_id=rule.id, evidence="pattern not found in Dockerfile")`.
  - A `dockerfile_pattern_inverted` rule with a forbidden match yields `Fail(rule_id=rule.id, evidence="forbidden pattern present in Dockerfile")`.
  - A `file_pattern` rule whose first matched file fails to match the pattern yields `Fail(rule_id=rule.id, evidence=f"{relpath}: pattern not found")` (relpath is the matched file's `relative_to(repo.root).as_posix()`).
  - A `missing_file` rule whose glob matches at least one file yields `Fail(rule_id=rule.id, evidence=f"unexpected file present: {relpath}")`.
  - `Fail` has no `file`, `line`, `snippet`, or `reason` fields (`extra="forbid"`); per-line evidence capture is out-of-scope for Phase 2 (would require an ADR amendment to the `Fail` model).
- [ ] **AC-8.** **`Pass` is the empty-information variant.** `Pass` has only `rule_id: ConventionId` and `kind: Literal["pass"]`. Constructing `Pass(rule_id="r1", file=...)` (or `line=`, `snippet=`, `reason=`, `evidence=`, `note=`) raises `pydantic.ValidationError` via `extra="forbid"`. Test parametrizes over the five plausible extra kwargs.
- [ ] **AC-9.** **Discriminated-union round-trip.** Each variant (`Pass`, `Fail`, `NotApplicable`) round-trips through `slice_.model_dump_json()` → `ConventionsSlice.model_validate_json(...)` with byte-identical re-serialization; each variant's `kind` discriminator is `"pass"`, `"fail"`, or `"not_applicable"` exactly; `rule_id` remains a `ConventionId` newtype (AC-20).
- [ ] **AC-10.** **All four pattern types exercised across all three outcomes.** Unit test parametrizes `dockerfile_pattern`, `dockerfile_pattern_inverted`, `file_pattern`, `missing_file` × `Pass` / `Fail` / `NotApplicable` — 12 cases. Each case asserts the typed variant matches the expected discriminator. Mutation caught: any pattern-type handler that silently collapses `NotApplicable` into `Pass`, or any helper that swaps `Pass`/`Fail` polarity on the inverted variant.
- [ ] **AC-11.** **Sub-schema validates.** `tests/unit/probes/layer_d/test_conventions.py::test_slice_matches_subschema` round-trips the JSON-dumped slice through `files("codegenie.schema.probes") / "conventions.schema.json"` (sub-schema lands in S6-08) with `additionalProperties: false` at every nesting level. Schema path is the flat layout (`src/codegenie/schema/probes/`), NOT `layer_d/`. The negative test asserts an extra field on `Pass` is rejected.
- [ ] **AC-12.** **`heaviness="light"`** — registry-verified: `next(e for e in default_registry._entries if e.cls.name == "conventions").heaviness == "light"`. (`_PROBE_REGISTRY` does not exist; the registry surface is `default_registry: Registry` at `src/codegenie/probes/registry.py:238`.)
- [ ] **AC-13.** **Parametrize covers each variant's discriminator.** The 12-case parametrize from AC-10 explicitly asserts `result.kind == expected_kind` *and* the `isinstance(result, ExpectedClass)` branch fires via an exhaustive `match` with `assert_never`; this proves the slice's deserialized variants are the *typed* models (not raw dicts).
- [ ] **AC-14.** **`mypy --strict`** passes. The `match result:` block in any consumer (e.g., the test) is total — `case _: assert_never(result)` is reachable only on a future ADR-amend that adds a fourth variant.
- [ ] **AC-15.** **Empty catalog → high confidence, empty results.** Two empty catalog directories (no `.yaml` files under either tier) yield `Ok(CatalogLoadOutcome(catalog=Catalog(rules=[]), per_file_errors=[]))`; the slice has `results=()`, `per_file_errors=()`, `rules_checked=0`, and `confidence="high"` (clean — no failures).
- [ ] **AC-16.** **Catastrophic failure: `FatalLoadError` → low confidence.** When *every* entry in `search_paths` is unreadable (e.g., both tier paths are `tmp_path/does_not_exist_*`), `load_all()` returns `Err(FatalLoadError(reason="no_search_path_readable", paths=[...]))`. The probe emits `ProbeOutput(confidence="low", ...)`, slice `results=()`, `rules_checked=0`, `catalog_paths_resolved=tuple(p.as_posix() for p in paths)`. The probe does NOT raise; the failure isolation contract (Phase 0) holds. (`load_all` returns `Ok(...)` with `per_file_errors=[]` when *some* paths exist but are empty — that's the `AC-15` empty-catalog path, not this AC.)
- [ ] **AC-17.** **Partial success: per-file errors surface through the slice.** A fixture with one valid catalog (`good.yaml`) and one malformed catalog (`bad.yaml` — top-level `kind: not_a_real_pattern_type`) yields `Ok(CatalogLoadOutcome(catalog=<rules from good.yaml>, per_file_errors=[UnknownPatternType(path=<bad.yaml>, offending_kind="not_a_real_pattern_type")]))`. The probe emits:
  - `slice.results` from the valid catalog (non-empty)
  - `slice.per_file_errors == (UnknownPatternType(path=Path('.../bad.yaml'), offending_kind="not_a_real_pattern_type"),)` — round-tripped through the discriminated union
  - `confidence="medium"` (per AC-18)
  - `ProbeOutput.warnings == ["conventions.per_file_errors_present"]` (operator-visible structured warning)
  - `ProbeOutput.errors == []` (per-file errors are NOT probe-level failures)
- [ ] **AC-18.** **Three-state confidence policy via pure helper.** `_compute_confidence(applied: list[ConventionResult], per_file_errors: list[ConventionsError]) -> Literal["high","medium","low"]` is a module-level pure function (no I/O, no instance state):
  - `"high"` if `per_file_errors == []` (clean — including empty catalog)
  - `"medium"` if `per_file_errors and applied` (partial — some files loaded, some failed)
  - `"low"` if `per_file_errors and not applied` (total — every catalog file failed)
  - Always `"low"` on the `FatalLoadError` path (handled at the `run` site, not in `_compute_confidence`)
- [ ] **AC-19.** **No shared base class beyond `Probe`.** `ConventionsProbe.__mro__` is exactly `(ConventionsProbe, Probe, ABC, object)` (length 4). Module source contains exactly one class declaration (`class ConventionsProbe(Probe):`) — no helper classes, no marker-probe base class shared with S6-03's not-yet-shipped marker probes. Rule of Three has not triggered (2 of 5 Layer-D marker probes; the kernel-side shared abstraction is `Probe` itself and `ConventionsCatalogLoader`).
- [ ] **AC-20.** **`ConventionId` newtype preserved end-to-end.** Every `ConventionResult.rule_id` round-tripped through `slice_.model_dump_json()` → `model_validate_json(...)` remains a `ConventionId` (under static analysis — a `reveal_type(slice_.results[0].rule_id)` test annotation produces `ConventionId` from `mypy --strict`). Pydantic v2's `NewType` handling preserves the alias at validation; the test pins this so a future regression to `str` fails CI.
- [ ] **AC-21.** **Determinism.** Two consecutive `await probe.run(repo, ctx)` calls on the same fixture and `RepoSnapshot` instance produce equal `slice.model_dump_json()` output. Rule order is catalog-file order (the order `safe_yaml` emits and Pydantic preserves via the `Catalog.rules: list[...]` field). The probe does NOT re-sort results.
- [ ] **AC-22.** **`Catalog.apply` memoization preserved.** Two consecutive `await probe.run(repo, ctx)` calls against the same `RepoSnapshot` *instance* read each `Dockerfile` exactly once at the filesystem level. The test monkey-patches `codegenie.conventions._io.read_capped_text` with a counter wrapper; the counter increments at most once per (rule × repo file). Mutation caught: any future re-implementation that drops the `Catalog.apply` memo or wraps it with a second memo that diverges under the `id(repo)` keying.
- [ ] **AC-23.** **Raw artifact deterministic.** `ctx.output_dir / "conventions.json"` is written atomically (sibling `.tmp` + `os.replace`); two consecutive runs produce a byte-identical file. The artifact path is the single entry in `ProbeOutput.raw_artifacts`. (S6-08's freshness check will consume this artifact alongside `catalog_paths_resolved` to detect catalog drift between gathers.)

## Implementation outline

1. Create `src/codegenie/probes/layer_d/__init__.py` (if not already created by S6-01).
2. Create `src/codegenie/probes/layer_d/conventions.py`:
   - Module docstring naming arch §"Component design" #10, CLAUDE.md "Facts, not judgments", and pointing at S6-01 as the probe-shape precedent.
   - Imports: `time`, `from pathlib import Path`, `from typing import Final, Literal`, `from pydantic import BaseModel, ConfigDict, model_validator`, `from codegenie.conventions.loader import ConventionsCatalogLoader, CatalogLoadOutcome, FatalLoadError, ConventionsError`, `from codegenie.conventions.model import ConventionResult`, `from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot`, `from codegenie.probes.registry import register_probe`, `from codegenie.result import Ok, Err`, `from codegenie.types.identifiers import ProbeId`.
   - Module-level constants (`Final[...]`): `_PROBE_ID = ProbeId("conventions")`, `_BASE_VERSION = "0.1.0"`, `_RAW_ARTIFACT_NAME = "conventions.json"`, `_WARNING_PER_FILE_ERRORS = "conventions.per_file_errors_present"`.
   - **Functional core** (pure module-level helpers):
     - `_compute_confidence(applied, per_file_errors) -> Literal["high","medium","low"]` per AC-18.
     - `_project_results(applied: list[ConventionResult]) -> tuple[ConventionResult, ...]` — preserves loader order; tuple-typed for hash-stability.
     - `_resolve_search_paths` (a method on the probe but pure — no I/O — so testable by passing a stub `repo` + `ctx`).
   - **Imperative shell**:
     - `ConventionsSlice(BaseModel)` per AC-2 (with the smart-constructor `@model_validator(mode="after")`).
     - `@register_probe(heaviness="light")` `class ConventionsProbe(Probe):` per AC-3.
     - `async def run(self, repo, ctx) -> ProbeOutput` per AC-4. Atomic raw-artifact write at the end (sibling `.tmp` → `os.replace`).
3. Write `tests/unit/probes/layer_d/test_conventions.py` per the TDD plan.

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/unit/probes/layer_d/test_conventions.py
"""Unit tests for ConventionsProbe (S6-02).

Each test is keyed to one or more ACs and names the mutation it catches
(Rule 9 — tests verify intent). The kernel S2-02 ships at
``src/codegenie/conventions/{model,catalog,loader}.py``; this test file
is the consumer side of that contract.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, assert_never
from unittest.mock import patch

import pytest
import yaml  # the test author is the operator producing fixture YAML

from codegenie.conventions.model import (
    Fail,
    NotApplicable,
    Pass,
)
from codegenie.probes.base import ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.layer_d import conventions as cp
from codegenie.probes.registry import default_registry


# --- Helpers (mirror S6-01) ---------------------------------------------------


def _make_repo(tmp_path: Path, *, dockerfile: str | None = None,
               extra_files: dict[str, str] | None = None) -> RepoSnapshot:
    """Build a minimal RepoSnapshot with an optional Dockerfile + extras."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    if dockerfile is not None:
        (repo_root / "Dockerfile").write_text(dockerfile)
    for relpath, content in (extra_files or {}).items():
        path = repo_root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return RepoSnapshot(
        root=repo_root,
        git_commit=None,
        detected_languages={},
        config={},
    )


def _make_context(
    tmp_path: Path,
    *,
    user_tier: Path | None = None,
    repo_tier: Path | None = None,
) -> ProbeContext:
    """Build a ProbeContext with the two conventions search paths via ctx.config."""
    cache_dir = tmp_path / ".codegenie" / "cache"
    output_dir = tmp_path / ".codegenie" / "context" / "raw"
    workspace = tmp_path / ".codegenie" / "workspace"
    for p in (cache_dir, output_dir, workspace):
        p.mkdir(parents=True, exist_ok=True)
    config: dict[str, Any] = {}
    if user_tier is not None:
        config["conventions.user_path"] = str(user_tier)
    if repo_tier is not None:
        config["conventions.repo_path"] = str(repo_tier)
    return ProbeContext(
        cache_dir=cache_dir,
        output_dir=output_dir,
        workspace=workspace,
        logger=logging.getLogger("test.conventions"),
        config=config,
    )


def _rule_dockerfile(id_: str, pattern: str) -> dict[str, Any]:
    return {
        "kind": "dockerfile_pattern",
        "id": id_,
        "description": f"rule {id_}",
        "pattern": pattern,
    }


def _rule_dockerfile_inverted(id_: str, pattern: str) -> dict[str, Any]:
    return {
        "kind": "dockerfile_pattern_inverted",
        "id": id_,
        "description": f"rule {id_}",
        "pattern": pattern,
    }


def _rule_file_pattern(id_: str, file_glob: str, pattern: str) -> dict[str, Any]:
    return {
        "kind": "file_pattern",
        "id": id_,
        "description": f"rule {id_}",
        "file_glob": file_glob,
        "pattern": pattern,
    }


def _rule_missing_file(id_: str, file_glob: str) -> dict[str, Any]:
    return {
        "kind": "missing_file",
        "id": id_,
        "description": f"rule {id_}",
        "file_glob": file_glob,
    }


def _write_catalog(catalog_dir: Path, rules: list[dict[str, Any]], *,
                   filename: str = "node.yaml") -> None:
    catalog_dir.mkdir(parents=True, exist_ok=True)
    (catalog_dir / filename).write_text(yaml.safe_dump({"rules": rules}))


def _run(probe: cp.ConventionsProbe, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
    return asyncio.run(probe.run(repo, ctx))


# --- AC-1, AC-3 — exports + ABC contract --------------------------------------


def test_module_exports_exactly_two_names() -> None:
    """AC-1. Mutation caught: an accidental ``__all__`` extension."""
    assert set(cp.__all__) == {"ConventionsProbe", "ConventionsSlice"}


def test_probe_abc_attributes_match_contract() -> None:
    """AC-3. Mutation caught: any drift from the frozen Probe ABC field set
    (e.g., reintroducing a ``probe_id`` attribute that ADR-0007 forbids)."""
    p = cp.ConventionsProbe
    assert p.name == "conventions"
    assert p.layer == "D"
    assert p.tier == "base"
    assert p.applies_to_tasks == ["*"]
    assert p.applies_to_languages == ["*"]
    assert p.requires == []
    assert p.timeout_seconds == 15
    assert p.cache_strategy == "content"
    assert "Dockerfile" in p.declared_inputs
    assert any("conventions_user_search_path" in s for s in p.declared_inputs)
    assert any("conventions_repo_search_path" in s for s in p.declared_inputs)
    # No ``probe_id`` class attribute (ADR-0007).
    assert not hasattr(p, "probe_id")
    # _PROBE_ID Final constant exists (scip_index.py:114 precedent).
    assert str(cp._PROBE_ID) == "conventions"


# --- AC-10, AC-13 — 4x3 pattern-type × outcome parametrize --------------------


@pytest.mark.parametrize(
    ("rule_builder", "rule_kwargs", "fixture_dockerfile", "fixture_extras", "expected_cls"),
    [
        # dockerfile_pattern × Pass/Fail/NotApplicable
        (_rule_dockerfile, {"id_": "r", "pattern": "tini"},
         "FROM node:20\nENTRYPOINT [\"tini\", \"--\"]\n", {}, Pass),
        (_rule_dockerfile, {"id_": "r", "pattern": "tini"},
         "FROM node:20\nCMD [\"node\", \"index.js\"]\n", {}, Fail),
        (_rule_dockerfile, {"id_": "r", "pattern": "tini"}, None, {}, NotApplicable),
        # dockerfile_pattern_inverted × Pass/Fail/NotApplicable
        (_rule_dockerfile_inverted, {"id_": "r", "pattern": r"npm (start|run)"},
         "FROM node:20\nCMD [\"node\", \"index.js\"]\n", {}, Pass),
        (_rule_dockerfile_inverted, {"id_": "r", "pattern": r"npm (start|run)"},
         "FROM node:20\nCMD [\"npm\", \"start\"]\n", {}, Fail),
        (_rule_dockerfile_inverted, {"id_": "r", "pattern": r"npm (start|run)"},
         None, {}, NotApplicable),
        # file_pattern × Pass/Fail/NotApplicable
        (_rule_file_pattern, {"id_": "r", "file_glob": "SECURITY.md", "pattern": "Reporting"},
         "FROM scratch\n", {"SECURITY.md": "## Reporting\nemail security@..."}, Pass),
        (_rule_file_pattern, {"id_": "r", "file_glob": "SECURITY.md", "pattern": "Reporting"},
         "FROM scratch\n", {"SECURITY.md": "## TODO\n"}, Fail),
        (_rule_file_pattern, {"id_": "r", "file_glob": "SECURITY.md", "pattern": "Reporting"},
         "FROM scratch\n", {}, NotApplicable),
        # missing_file × Pass/Fail/NotApplicable (NotApplicable not reachable
        # — missing_file's "empty glob" path is Pass by design; we substitute
        # a file_pattern variant that demonstrates the absent-glob → NA path)
        (_rule_missing_file, {"id_": "r", "file_glob": ".dockerignore.old"},
         "FROM scratch\n", {}, Pass),
        (_rule_missing_file, {"id_": "r", "file_glob": ".dockerignore.old"},
         "FROM scratch\n", {".dockerignore.old": "legacy\n"}, Fail),
    ],
)
def test_pattern_type_outcomes(
    rule_builder, rule_kwargs, fixture_dockerfile, fixture_extras,
    expected_cls, tmp_path: Path,
) -> None:
    """AC-10, AC-13. Mutation caught: any pattern-type handler that swaps
    Pass/Fail polarity (catches 2/11 rows), collapses NotApplicable into
    Pass (catches 3/11 rows), or routes the wrong rule kind through the
    dispatcher (catches every row)."""
    user_tier = tmp_path / "conventions"
    _write_catalog(user_tier, [rule_builder(**rule_kwargs)])
    repo = _make_repo(tmp_path, dockerfile=fixture_dockerfile, extra_files=fixture_extras)
    ctx = _make_context(tmp_path, user_tier=user_tier,
                        repo_tier=tmp_path / "repo_tier_does_not_exist")
    output = _run(cp.ConventionsProbe(), repo, ctx)
    slice_ = cp.ConventionsSlice.model_validate(output.schema_slice)
    assert len(slice_.results) == 1
    result = slice_.results[0]
    assert isinstance(result, expected_cls)
    match result:
        case Pass(): assert result.kind == "pass"
        case Fail(): assert result.kind == "fail"
        case NotApplicable(): assert result.kind == "not_applicable"
        case _: assert_never(result)


# --- AC-6 — NotApplicable carries the kernel constant -------------------------


def test_dockerfile_absent_yields_no_dockerfile_present(tmp_path: Path) -> None:
    """AC-6. Mutation caught: drift between the test's expected reason
    string and ``catalog.py:51``'s ``_REASON_NO_DOCKERFILE`` constant."""
    user_tier = tmp_path / "conventions"
    _write_catalog(user_tier, [_rule_dockerfile("acme-tini", "tini")])
    repo = _make_repo(tmp_path, dockerfile=None)
    ctx = _make_context(tmp_path, user_tier=user_tier)
    output = _run(cp.ConventionsProbe(), repo, ctx)
    slice_ = cp.ConventionsSlice.model_validate(output.schema_slice)
    na = slice_.results[0]
    assert isinstance(na, NotApplicable)
    assert na.reason == "no_dockerfile_present"


def test_file_glob_empty_yields_file_glob_no_matches(tmp_path: Path) -> None:
    """AC-6. Same root cause — drift from ``catalog.py:52``'s
    ``_REASON_GLOB_EMPTY`` constant."""
    user_tier = tmp_path / "conventions"
    _write_catalog(user_tier, [_rule_file_pattern("acme-security", "SECURITY.md", "Reporting")])
    repo = _make_repo(tmp_path, dockerfile="FROM scratch\n")
    ctx = _make_context(tmp_path, user_tier=user_tier)
    output = _run(cp.ConventionsProbe(), repo, ctx)
    slice_ = cp.ConventionsSlice.model_validate(output.schema_slice)
    na = slice_.results[0]
    assert isinstance(na, NotApplicable)
    assert na.reason == "file_glob_no_matches"


# --- AC-7 — Fail carries documented evidence strings, not file/line/snippet ---


def test_fail_evidence_strings_match_kernel(tmp_path: Path) -> None:
    """AC-7. Mutation caught: drift between the documented evidence
    strings in ``catalog.py:113-168`` and the test. Also catches any
    future attempt to add ``file``/``line``/``snippet`` fields to
    ``Fail`` without an ADR amendment (``extra='forbid'`` would reject)."""
    user_tier = tmp_path / "conventions"
    _write_catalog(
        user_tier,
        [
            _rule_dockerfile("a", "tini"),
            _rule_dockerfile_inverted("b", r"npm (start|run)"),
            _rule_file_pattern("c", "SECURITY.md", "Reporting"),
            _rule_missing_file("d", ".dockerignore.old"),
        ],
    )
    # Build a repo that fails ALL four rules.
    repo = _make_repo(
        tmp_path,
        dockerfile="FROM node:20\nCMD [\"npm\", \"start\"]\n",
        extra_files={"SECURITY.md": "## TODO\n", ".dockerignore.old": "legacy\n"},
    )
    ctx = _make_context(tmp_path, user_tier=user_tier)
    output = _run(cp.ConventionsProbe(), repo, ctx)
    slice_ = cp.ConventionsSlice.model_validate(output.schema_slice)
    by_id = {r.rule_id: r for r in slice_.results}
    a, b, c, d = (by_id["a"], by_id["b"], by_id["c"], by_id["d"])
    assert isinstance(a, Fail) and a.evidence == "pattern not found in Dockerfile"
    assert isinstance(b, Fail) and b.evidence == "forbidden pattern present in Dockerfile"
    assert isinstance(c, Fail) and c.evidence == "SECURITY.md: pattern not found"
    assert isinstance(d, Fail) and d.evidence == "unexpected file present: .dockerignore.old"
    # ``Fail`` rejects file/line/snippet (``extra='forbid'``).
    with pytest.raises(Exception):  # ValidationError
        Fail(rule_id="r", evidence="x", file="Dockerfile")  # type: ignore[call-arg]


# --- AC-8 — Pass is the empty-information variant ----------------------------


@pytest.mark.parametrize("forbidden_kwarg",
                         ["file", "line", "snippet", "reason", "evidence", "note"])
def test_pass_rejects_extra_kwarg(forbidden_kwarg: str) -> None:
    """AC-8. Mutation caught: any future "let's add a field to Pass for
    symmetry with Fail" — Pass is the empty-information variant."""
    with pytest.raises(Exception):  # ValidationError
        Pass(rule_id="r1", **{forbidden_kwarg: "x"})  # type: ignore[call-arg]


# --- AC-9, AC-20 — round-trip + ConventionId newtype preserved ----------------


def test_slice_round_trip_preserves_typed_variants_and_newtype(tmp_path: Path) -> None:
    """AC-9, AC-20. Mutation caught: a future Pydantic upgrade that
    silently widens ``rule_id: ConventionId`` to ``str`` would break the
    static guarantee Phase 4+ consumers depend on; the JSON round-trip
    also catches any drift in the discriminator handling."""
    user_tier = tmp_path / "conventions"
    _write_catalog(
        user_tier,
        [
            _rule_dockerfile("p", "tini"),       # → Pass
            _rule_dockerfile("f", "absent"),     # → Fail
        ],
    )
    repo = _make_repo(tmp_path, dockerfile="ENTRYPOINT [\"tini\", \"--\"]\n")
    ctx = _make_context(tmp_path, user_tier=user_tier)
    output = _run(cp.ConventionsProbe(), repo, ctx)
    slice_in = cp.ConventionsSlice.model_validate(output.schema_slice)
    blob = slice_in.model_dump_json()
    slice_out = cp.ConventionsSlice.model_validate_json(blob)
    assert slice_out.model_dump_json() == blob  # byte-identical
    # Each variant's discriminator is exactly its expected literal.
    kinds = {r.rule_id: r.kind for r in slice_out.results}
    assert kinds == {"p": "pass", "f": "fail"}


# --- AC-15 — empty catalog → high confidence ---------------------------------


def test_empty_catalog_yields_high_confidence(tmp_path: Path) -> None:
    """AC-15. Mutation caught: any policy that collapses "clean install
    with no rules" into ``medium``/``low``."""
    user_tier = tmp_path / "conventions"
    user_tier.mkdir()
    repo = _make_repo(tmp_path, dockerfile="FROM scratch\n")
    ctx = _make_context(tmp_path, user_tier=user_tier)
    output = _run(cp.ConventionsProbe(), repo, ctx)
    slice_ = cp.ConventionsSlice.model_validate(output.schema_slice)
    assert output.confidence == "high"
    assert slice_.results == ()
    assert slice_.per_file_errors == ()
    assert slice_.rules_checked == 0


# --- AC-16 — FatalLoadError → low confidence ---------------------------------


def test_fatal_load_error_yields_low_confidence(tmp_path: Path) -> None:
    """AC-16. Mutation caught: re-raising would break Phase 0 failure
    isolation; treating ``FatalLoadError`` as anything other than
    ``low`` would lie about gather quality."""
    repo = _make_repo(tmp_path, dockerfile="FROM scratch\n")
    ctx = _make_context(
        tmp_path,
        user_tier=tmp_path / "does_not_exist_user",
        repo_tier=tmp_path / "does_not_exist_repo",
    )
    output = _run(cp.ConventionsProbe(), repo, ctx)
    slice_ = cp.ConventionsSlice.model_validate(output.schema_slice)
    assert output.confidence == "low"
    assert slice_.results == ()
    assert slice_.rules_checked == 0
    assert all("does_not_exist" in p for p in slice_.catalog_paths_resolved)


# --- AC-17, AC-18 — partial success → medium confidence + per_file_errors ----


def test_partial_success_yields_medium_confidence_and_typed_errors(tmp_path: Path) -> None:
    """AC-17, AC-18. Mutation caught: collapsing partial-success into
    ``high`` (hides operator-visible failures) or ``low`` (over-states
    the failure)."""
    user_tier = tmp_path / "conventions"
    _write_catalog(user_tier, [_rule_dockerfile("g", "tini")], filename="good.yaml")
    # ``bad.yaml`` has an unknown ``kind`` discriminator → UnknownPatternType.
    (user_tier / "bad.yaml").write_text(yaml.safe_dump({
        "rules": [{
            "kind": "not_a_real_pattern_type",
            "id": "bad",
            "description": "x",
        }],
    }))
    repo = _make_repo(tmp_path, dockerfile="ENTRYPOINT [\"tini\", \"--\"]\n")
    ctx = _make_context(tmp_path, user_tier=user_tier)
    output = _run(cp.ConventionsProbe(), repo, ctx)
    slice_ = cp.ConventionsSlice.model_validate(output.schema_slice)
    assert output.confidence == "medium"
    assert len(slice_.results) == 1
    assert slice_.results[0].rule_id == "g"
    assert len(slice_.per_file_errors) == 1
    err = slice_.per_file_errors[0]
    assert err.reason == "unknown_pattern_type"
    assert err.offending_kind == "not_a_real_pattern_type"
    assert "conventions.per_file_errors_present" in output.warnings
    assert output.errors == []  # per-file errors are NOT probe-level failures


# --- AC-11 — sub-schema (lands in S6-08; this test stays skipped until then) -


@pytest.mark.skip(reason="sub-schema lands in S6-08; this test enables when "
                          "src/codegenie/schema/probes/conventions.schema.json exists")
def test_slice_matches_subschema_with_strict_additional_properties() -> None:
    """AC-11. Mutation caught: a future ``Pass`` adding a ``note: str``
    field would fail the round-trip — ``additionalProperties: false``
    holds at every nesting level."""
    from importlib.resources import files

    import jsonschema

    schema = json.loads(
        (files("codegenie.schema.probes") / "conventions.schema.json").read_text()
    )
    slice_dict = {
        "results": [{"kind": "pass", "rule_id": "r1"}],
        "catalog_paths_resolved": [],
        "per_file_errors": [],
        "rules_checked": 1,
    }
    jsonschema.validate(slice_dict, schema)
    bad = {**slice_dict, "results": [{"kind": "pass", "rule_id": "r1", "note": "extra"}]}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


# --- AC-12 — registry-verified heaviness -------------------------------------


def test_registry_heaviness_is_light() -> None:
    """AC-12. Mutation caught: bumping to ``heaviness='medium'`` would
    cause the coordinator to over-budget the probe."""
    entry = next(e for e in default_registry._entries if e.cls.name == "conventions")
    assert entry.heaviness == "light"
    assert entry.runs_last is False


# --- AC-19 — no shared base class beyond Probe -------------------------------


def test_mro_depth_and_no_helper_classes() -> None:
    """AC-19. Mutation caught: a future refactor extracting a
    ``MarkerProbe`` base class shared with S6-03's not-yet-shipped marker
    probes — Rule of Three has not triggered (2 of 5 Layer-D marker
    probes)."""
    import inspect
    mro = cp.ConventionsProbe.__mro__
    assert [c.__name__ for c in mro] == [
        "ConventionsProbe", "Probe", "ABC", "object",
    ]
    # Exactly one class declaration in the module source.
    src = inspect.getsource(cp)
    class_decls = [line for line in src.splitlines()
                   if line.startswith("class ") and not line.startswith("class _")]
    assert class_decls == ["class ConventionsProbe(Probe):"] or \
           class_decls == ["class ConventionsSlice(BaseModel):",
                           "class ConventionsProbe(Probe):"]


# --- AC-21 — determinism (catalog-file order preserved) ----------------------


def test_two_runs_byte_identical_and_preserve_catalog_order(tmp_path: Path) -> None:
    """AC-21. Mutation caught: any non-deterministic ordering (set/dict
    iteration without sort) would diverge on the second run; re-sorting
    by ``rule_id`` would violate the catalog-file-order contract."""
    user_tier = tmp_path / "conventions"
    _write_catalog(
        user_tier,
        [
            _rule_missing_file("z_last_alphabetically", ".dockerignore.old"),
            _rule_dockerfile("a_first_alphabetically", "tini"),
        ],
    )
    repo = _make_repo(tmp_path, dockerfile="ENTRYPOINT [\"tini\", \"--\"]\n")
    ctx = _make_context(tmp_path, user_tier=user_tier)
    out1 = _run(cp.ConventionsProbe(), repo, ctx).schema_slice
    out2 = _run(cp.ConventionsProbe(), repo, ctx).schema_slice
    assert json.dumps(out1, sort_keys=True) == json.dumps(out2, sort_keys=True)
    # Catalog-file order preserved (z_last first because that's how the YAML
    # writes it). Re-sorting by rule_id would put ``a_first_alphabetically`` first.
    ids = [r["rule_id"] for r in out1["results"]]
    assert ids == ["z_last_alphabetically", "a_first_alphabetically"]


# --- AC-22 — Catalog.apply memo preserved (single Dockerfile read) ----------


def test_catalog_apply_memo_reads_dockerfile_once(tmp_path: Path) -> None:
    """AC-22. Mutation caught: any future implementation that drops the
    ``Catalog.apply`` id(repo) memo (e.g., re-constructs ``Catalog`` on
    every call) would re-read the Dockerfile on each ``run`` call."""
    from codegenie.conventions import _io as conv_io

    user_tier = tmp_path / "conventions"
    _write_catalog(user_tier, [_rule_dockerfile("r", "tini")])
    repo = _make_repo(tmp_path, dockerfile="ENTRYPOINT [\"tini\", \"--\"]\n")
    ctx = _make_context(tmp_path, user_tier=user_tier)

    counter = {"reads": 0}
    real = conv_io.read_capped_text

    def counting_read(*args: Any, **kwargs: Any) -> Any:
        counter["reads"] += 1
        return real(*args, **kwargs)

    probe = cp.ConventionsProbe()
    with patch.object(conv_io, "read_capped_text", counting_read):
        # NOTE: each call constructs a fresh Catalog (loader runs twice), so
        # the memo only helps within a single call. The single-read invariant
        # we assert: one Dockerfile read PER RUN, NOT PER RULE.
        out1 = _run(probe, repo, ctx)
        reads_after_first = counter["reads"]
        out2 = _run(probe, repo, ctx)
        reads_after_second = counter["reads"]
    assert reads_after_first == 1, "one rule → one Dockerfile read"
    assert reads_after_second == 2, "second run rebuilds the catalog; one more read"
    assert out1.schema_slice == out2.schema_slice


# --- AC-23 — raw artifact written atomically + byte-identical on rerun -------


def test_raw_artifact_written_atomically_and_deterministically(tmp_path: Path) -> None:
    """AC-23. Mutation caught: a non-atomic write (no os.replace) could
    leave a partial file on disk; non-deterministic JSON encoding would
    diverge across runs."""
    user_tier = tmp_path / "conventions"
    _write_catalog(user_tier, [_rule_dockerfile("r", "tini")])
    repo = _make_repo(tmp_path, dockerfile="ENTRYPOINT [\"tini\", \"--\"]\n")
    ctx = _make_context(tmp_path, user_tier=user_tier)
    out1 = _run(cp.ConventionsProbe(), repo, ctx)
    blob1 = (ctx.output_dir / "conventions.json").read_bytes()
    out2 = _run(cp.ConventionsProbe(), repo, ctx)
    blob2 = (ctx.output_dir / "conventions.json").read_bytes()
    assert blob1 == blob2
    assert out1.raw_artifacts == [ctx.output_dir / "conventions.json"]
    # No leftover .tmp file.
    assert not any(p.name.endswith(".tmp") for p in ctx.output_dir.iterdir())
```

### Green — make it pass

```python
# src/codegenie/probes/layer_d/conventions.py
"""ConventionsProbe — Layer D, light heaviness.

Applies ``ConventionsCatalogLoader.load_all()`` output to the ``RepoSnapshot``
and emits a typed ``ConventionsSlice``. Each rule's outcome is one of
``Pass | Fail | NotApplicable`` — the closed sum type S2-02 ships in
``codegenie.conventions.model``.

This module is the imperative shell *around* the kernel-side functional
core (``Catalog.apply`` and the four ``_apply_<kind>`` helpers in
``codegenie.conventions.catalog``). The probe contributes:
  - search-path resolution (``ctx.config`` → ``[user_tier, repo_tier]``)
  - Result pattern-matching (``Ok(CatalogLoadOutcome)`` / ``Err(FatalLoadError)``)
  - three-state confidence policy (``_compute_confidence``)
  - slice projection (``ConventionsSlice``)
  - atomic raw-artifact write

Sources:
- ../phase-arch-design.md §"Component design" #10 — loader + apply.
- ../../localv2.md §5.4 D5 — example catalog.
- ./S6-01-skills-index-probe.md (HARDENED) — probe-shape precedent.
- src/codegenie/probes/layer_b/scip_index.py:114 — _PROBE_ID Final pattern.

CLAUDE.md disciplines honored:
- "Facts, not judgments" — per-rule outcomes, no aggregation.
- "Extension by addition" — new rule kinds are new ``_apply_*`` helpers
  in the kernel; the probe inherits them automatically.
- "Honest confidence" — three-state policy; ``Catalog.apply`` memo is
  the single source of truth for per-snapshot caching.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from codegenie.conventions.loader import (
    CatalogLoadOutcome,
    ConventionsCatalogLoader,
    ConventionsError,
    FatalLoadError,
)
from codegenie.conventions.model import ConventionResult
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe
from codegenie.result import Err, Ok
from codegenie.types.identifiers import ProbeId

__all__ = ["ConventionsProbe", "ConventionsSlice"]

_PROBE_ID: Final[ProbeId] = ProbeId("conventions")
_BASE_VERSION: Final[str] = "0.1.0"
_RAW_ARTIFACT_NAME: Final[str] = "conventions.json"
_WARNING_PER_FILE_ERRORS: Final[str] = "conventions.per_file_errors_present"
_DEFAULT_USER_PATH: Final[str] = "~/.codegenie/conventions/"
_DEFAULT_REPO_PATH: Final[str] = ".codegenie/conventions/"


# ---------------------------------------------------------------------------
# Functional core — pure helpers (no I/O, no instance state).
# ---------------------------------------------------------------------------


def _compute_confidence(
    applied: list[ConventionResult],
    per_file_errors: list[ConventionsError],
) -> Literal["high", "medium", "low"]:
    """Three-state policy: high (clean), medium (partial), low (total)."""
    if not per_file_errors:
        return "high"
    if applied:
        return "medium"
    return "low"


def _project_results(applied: list[ConventionResult]) -> tuple[ConventionResult, ...]:
    """Preserve loader order; tuple-typed for hash-stability."""
    return tuple(applied)


# ---------------------------------------------------------------------------
# Imperative shell — slice + probe.
# ---------------------------------------------------------------------------


class ConventionsSlice(BaseModel):
    """Frozen slice; smart constructor enforces ``rules_checked == len(results)``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    results: tuple[ConventionResult, ...]
    catalog_paths_resolved: tuple[str, ...]
    per_file_errors: tuple[ConventionsError, ...]
    rules_checked: int

    @model_validator(mode="after")
    def _check_count(self) -> ConventionsSlice:
        if self.rules_checked != len(self.results):
            raise ValueError(
                f"rules_checked={self.rules_checked} but len(results)={len(self.results)}"
            )
        return self


@register_probe(heaviness="light")
class ConventionsProbe(Probe):
    name: str = "conventions"
    version: str = _BASE_VERSION
    layer = "D"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    timeout_seconds: int = 15
    cache_strategy: Literal["content"] = "content"
    declared_inputs: list[str] = [
        "Dockerfile",
        f"conventions_user_search_path:{_DEFAULT_USER_PATH}",
        f"conventions_repo_search_path:{_DEFAULT_REPO_PATH}",
    ]

    def _resolve_search_paths(
        self, repo: RepoSnapshot, ctx: ProbeContext
    ) -> list[Path]:
        user = Path(ctx.config.get("conventions.user_path", _DEFAULT_USER_PATH)).expanduser()
        repo_tier = repo.root / Path(
            ctx.config.get("conventions.repo_path", _DEFAULT_REPO_PATH)
        )
        return [user, repo_tier]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        t0 = time.perf_counter()
        resolved = self._resolve_search_paths(repo, ctx)
        result = ConventionsCatalogLoader(search_paths=resolved).load_all()

        applied: list[ConventionResult]
        per_file_errors: list[ConventionsError]
        catalog_paths: tuple[str, ...]
        match result:
            case Ok(value=CatalogLoadOutcome(catalog=catalog, per_file_errors=errors)):
                applied = list(catalog.apply(repo))
                per_file_errors = list(errors)
                catalog_paths = tuple(p.as_posix() for p in resolved)
            case Err(error=FatalLoadError(paths=ps)):
                applied = []
                per_file_errors = []
                catalog_paths = tuple(p.as_posix() for p in ps)
            case _:
                # Unreachable under the Result[OK, Err] union, but mypy
                # --warn-unreachable wants the exhaustive ladder.
                applied = []
                per_file_errors = []
                catalog_paths = ()

        slice_ = ConventionsSlice(
            results=_project_results(applied),
            catalog_paths_resolved=catalog_paths,
            per_file_errors=tuple(per_file_errors),
            rules_checked=len(applied),
        )
        raw_path = ctx.output_dir / _RAW_ARTIFACT_NAME
        _atomic_write_json(raw_path, slice_.model_dump_json(indent=2))

        warnings = [_WARNING_PER_FILE_ERRORS] if per_file_errors else []
        # FatalLoadError → low; otherwise three-state via the helper.
        if isinstance(getattr(result, "error", None), FatalLoadError):
            confidence: Literal["high", "medium", "low"] = "low"
        else:
            confidence = _compute_confidence(applied, per_file_errors)

        return ProbeOutput(
            schema_slice=slice_.model_dump(mode="json"),
            raw_artifacts=[raw_path],
            confidence=confidence,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            warnings=warnings,
            errors=[],
        )


def _atomic_write_json(path: Path, blob: str) -> None:
    """Atomic write via sibling ``.tmp`` + ``os.replace``."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(blob)
    os.replace(tmp, path)
```

### Refactor

- The `match` pattern on `Result[CatalogLoadOutcome, FatalLoadError]` repeats across S6-01 (Skills) and S6-02 (Conventions). Both consume `Result[*LoadOutcome, FatalLoadError]` with identical structure: `Ok(outcome)` carries `per_file_errors`; `Err(FatalLoadError)` carries `paths`. The Rule-of-Three threshold is not met (two cases); leave the match inline. The third loader-consumer (S6-04 ExternalDocs) is the trigger — but the helper, if extracted, lives at `codegenie.probes._loader_match` (a new module), not on a shared base class shared with `SkillsIndexProbe`.
- The atomic-write helper `_atomic_write_json` is a candidate for extraction to `codegenie.output.atomic` if a second consumer needs it; until then, keep it module-local (Rule 2: three similar lines is better than premature abstraction).
- The `_make_repo` / `_make_context` test helpers should be extracted to `tests/_helpers/probe_context.py` if S6-03's marker probes need the same fixtures (rule-of-three trigger). Until then, each probe's test file owns its own helpers (copy from S6-01; do not import S6-01's test module).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/layer_d/__init__.py` | Created by S6-01; this story does not re-touch unless missing. |
| `src/codegenie/probes/layer_d/conventions.py` | New file — `ConventionsSlice`, `ConventionsProbe`, `_compute_confidence`, `_project_results`, `_atomic_write_json`, `_PROBE_ID`. |
| `tests/unit/probes/layer_d/test_conventions.py` | New file — 13 tests keyed to ACs (one parametrized over 11 cases). |
| `tests/unit/probes/layer_d/__init__.py` | If not already created by S6-01, ensure exists (empty file). |

## Out of scope

- **OPA/Rego pattern types.** Phase 16 (ADR-0021); the Phase 2 catalog supports only the four YAML-pattern types defined in S2-02.
- **Policy probe + exceptions probe + repo notes + repo config + ADRs probe.** S6-03 (separate marker probes; share no code with this one).
- **Per-line evidence in `Fail`.** The kernel's `Fail` model has only `evidence: str`; capturing line numbers + snippets requires an ADR amendment to extend the `Fail` model (out of Phase 2's scope per `localv2.md §4`'s frozen contract).
- **Sub-schema authoring.** S6-08 lands `src/codegenie/schema/probes/conventions.schema.json`; AC-11's test is skipped until then with the documented reason.
- **Catalog-version drift detection.** S6-08 registers `@register_index_freshness_check` for `conventions`; this story emits `catalog_paths_resolved` (the operator-visible paths the loader walked) — the freshness check consumes it alongside file BLAKE3 or commit SHA. The original draft's `catalog_version` field is dropped: `Catalog` has no `version` field, and pinning a `version:` YAML key would be reinventing what file-level fingerprinting already provides.
- **Per-rule "fix suggestions"** in `Fail.evidence`. The probe records the documented evidence string; suggesting a fix is the Planner's job (per CLAUDE.md "Facts, not judgments").
- **Property-based fuzzing of `_apply_one`.** A Hypothesis test that synthesizes arbitrary `(ConventionRule, RepoSnapshot)` pairs and asserts the dispatcher is total over the union is a strong follow-up but lives at the kernel level (`tests/unit/conventions/test_catalog_property.py`), not in this probe's test file.

## Notes for the implementer

1. **`ConventionResult` is the consumer-side discriminated union.** Phase 2 builds it; Phase 4+ (Planner) consumes it. The `Literal["pass"|"fail"|"not_applicable"]` discriminator on each variant is what makes downstream `match result:` blocks exhaustive under `mypy --warn-unreachable`. Do **not** introduce a `kind: str` field — that loses the static check.
2. **`NotApplicable` is not "skipped."** The probe wasn't skipped; the rule was checked, the precondition failed, the result is "this rule doesn't apply here." A future contributor may be tempted to merge `NotApplicable` into `confidence="low"` — resist. Confidence is per-*probe*; per-*rule* applicability is per-`ConventionResult`.
3. **`safe_yaml` is the only YAML loader.** `ConventionsCatalogLoader` already routes through `safe_yaml.load`; this probe never touches YAML directly. The test helper `_write_catalog` uses `yaml.safe_dump` to *write* fixture YAML — this is acceptable because the test author is the operator producing the fixture, not the probe reading it. The probe must never grow a `yaml` import.
4. **`Pass` is the empty-information variant.** Resist the urge to add `Pass.note: str | None = None` — `Pass` is the "no information beyond `rule_id`" variant on purpose. If the convention check needs to explain *why* it passed, the convention is the wrong shape (express the explanation as a separate rule or as `NotApplicable.reason`).
5. **`Fail.evidence` is a single string, not a structured object.** Line/column capture would require an ADR amendment to the `Fail` model. Until then, the four documented evidence strings (`"pattern not found in Dockerfile"`, `"forbidden pattern present in Dockerfile"`, `f"{relpath}: pattern not found"`, `f"unexpected file present: {relpath}"`) are the operator contract. If a future change adds line numbers, it must also amend `_REASON_*` constant assertions in this probe's tests.
6. **Reason constants live in the kernel.** `_REASON_NO_DOCKERFILE = "no_dockerfile_present"` and `_REASON_GLOB_EMPTY = "file_glob_no_matches"` are pinned in `src/codegenie/conventions/catalog.py:50-52`. If those change, the probe's tests break loud — and that's the contract. Do NOT hardcode the literal strings in this probe's source; the kernel owns the values; the probe consumes them transparently.
7. **No "convention applier" base class shared with S6-03's marker probes.** Layer D's five marker-driven probes (S6-03's `adrs` / `repo_notes` / `repo_config` / `policy` / `exceptions`) are simpler than this one — they're file-listing probes, not rule-evaluation probes. The shared structure is the `Probe` ABC; that's the level the discipline lives at. AC-19's `__mro__` assertion enforces this.
8. **`Catalog.apply` memo is the single source of truth.** The kernel-side `Catalog.apply` at `catalog.py:75-82` memoizes by `id(repo)` — handing the *same* `RepoSnapshot` instance twice returns the cached result with zero repo I/O. The probe MUST NOT layer a second memo on top: the loader runs again on each `run` call (which is fine — it's I/O-cheap), but the apply layer's cache is hit on the second call. AC-22 enforces this by counting filesystem reads.
9. **Three-state confidence via a pure helper.** `_compute_confidence(applied, per_file_errors)` is the same shape S6-01 ships. Extracting it as a shared helper (`codegenie.probes._confidence`) is the rule-of-three trigger when S6-04 (ExternalDocs) becomes the third consumer — not before.
10. **The test helpers `_make_context` / `_make_repo` are local for now.** S6-01's hardened story owns the precedent; S6-02 copies. Extract to `tests/_helpers/probe_context.py` only when S6-03 (the third probe) needs the same shape.
11. **The `Probe` ABC is frozen** byte-for-byte against `localv2.md §4` (Phase 0 ADR-0007). The probe declares the ABC field set via class attributes (not `dataclass` fields, not Pydantic fields) because that's what the frozen contract specifies. The `_PROBE_ID: Final[ProbeId]` constant lives alongside the class, not inside it.
12. **`ProbeOutput.errors` is reserved for probe-level failures.** Per-file load errors (a malformed catalog YAML, an unknown pattern type) are *content* of a successful probe run — they belong in `slice.per_file_errors` and surface a structured `ProbeOutput.warnings` entry. Probe-level failures (sandbox timeout, asyncio cancellation) are the coordinator's concern and surface in `ProbeOutput.errors` — but this probe doesn't generate those.
13. **Cache strategy `"content"`** because the probe's output is fully determined by the contents of the two tier directories plus the analyzed-repo `Dockerfile` (and any files the file_pattern globs hit). The coordinator's content-addressed cache key will include all of these via the `declared_inputs` tokens. The S6-08 freshness check (catalog version drift) is what catches changes to catalog files *between* gathers; the probe-level cache catches changes *within* a gather.
