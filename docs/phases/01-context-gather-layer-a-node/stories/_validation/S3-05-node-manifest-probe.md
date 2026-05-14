# Validation report — S3-05 `NodeManifestProbe` + sub-schema + native-module catalog cross-reference

**Story:** [S3-05-node-manifest-probe.md](../S3-05-node-manifest-probe.md)
**Validated:** 2026-05-14
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The goal — ship `NodeManifestProbe` with its sub-schema and the native-module catalog cross-reference so a Node-repo gather populates a valid `manifests` slice — is sound and traces cleanly to phase-arch-design.md §"Component design" #4, §"Data model", §"Edge cases" rows 1–4 + 8, ADR-0004 (per-probe sub-schema), ADR-0006 (catalog cache invalidation), ADR-0007 (warning-ID pattern), ADR-0011 (no `npm ls`), and CLAUDE.md "Extension by addition" + "Facts, not judgments".

The draft, however, carried **four block-level structural inconsistencies** against load-bearing code that S1-09, S2-02, S3-01, S3-02, and S3-03 have already settled, plus the same family of harden-tier defects every prior step-3 story inherited (positional markers, weak mutation resistance on the cross-reference, name-normalization gap across pnpm/npm/yarn lockfile key shapes). The hardened story corrects the structural contradictions and elevates the design-pattern opportunity that S3-01/S3-02/S3-03 explicitly deferred: this probe is the **third concrete consumer** of the lockfile-parser family, so the rule-of-three threshold for a registry/strategy seam is now reached.

**Four block-level corrections applied:**

1. **`declared_raw_artifact_budget_mb` is dead — use `declared_resource_budget = ResourceBudget(...)`.** Draft AC-1 prescribed `declared_raw_artifact_budget_mb = 25` as a class attribute on the probe. This contradicts the **more-recent, more-tested** Phase 0 + S1-09 mechanism (committed code, passing tests): per `src/codegenie/coordinator/budget.py:13–19` and `_validation/S1-09-raw-artifact-budget.md`, ADR-0007 freezes the `Probe` ABC; budgets are a coordinator-side concern. The S1-09 hardening **explicitly named S3-05 as the consumer**: *"`NodeManifestProbe` (S3-05) overrides via `declared_resource_budget = ResourceBudget(raw_artifact_mb=50, raw_artifact_truncate_mb=25)`."* The hardened S3-05 routes through this surface; AC-1 now pins the `ResourceBudget` invariant (`raw_artifact_truncate_mb <= raw_artifact_mb`), and the unit test asserts on `cls.declared_resource_budget`, not a dead attribute name. Phase-arch-design.md §"Gap analysis" Gap 2's prose is stale and is flagged for cleanup at the same level S1-09 already surfaced it. Per Rule 7 (surface conflicts, don't average them), Consistency wins.

2. **`ProbeOutput` API mismatch.** Draft Green-code and four test assertions used `ProbeOutput(data=..., confidence=..., errors=..., warnings=...)` and `out.data["manifests"][...]`. The frozen `Probe` ABC (`src/codegenie/probes/base.py:56–63`) defines `ProbeOutput` with fields `schema_slice`, `raw_artifacts`, `confidence`, `duration_ms`, `warnings`, `errors`. Every existing probe (`language_detection.py`, `node_build_system.py`) constructs `ProbeOutput(schema_slice=..., raw_artifacts=[], confidence=..., duration_ms=..., warnings=..., errors=...)`. The draft would have failed at import time. Hardened Green-code uses the correct field names; every test asserts on `out.schema_slice["manifests"][...]`.

3. **Lockfile precedence wrong.** Draft AC-4: *"`pnpm-lock.yaml` > `package-lock.json` > `yarn.lock`"*. Phase-arch-design.md line 801 and `node_build_system.py:116-121` (`_LOCKFILE_PRECEDENCE`) both pin: `bun.lockb > pnpm-lock.yaml > yarn.lock > package-lock.json`. The draft had `yarn` and `npm` reversed. Hardened AC-4 mirrors `_LOCKFILE_PRECEDENCE` order for the parsed-formats subset: `pnpm-lock.yaml > yarn.lock > package-lock.json`; `bun.lockb` is enumerated for presence-only (so multi-lockfile detection sees it) but never parsed by this probe.

4. **`@register_probe` missing.** Draft AC-12 said *"`src/codegenie/probes/__init__.py` is edited additively to register `NodeManifestProbe` via explicit import"*. The established pattern (S2-01 `LanguageDetectionProbe`, S2-02 `NodeBuildSystemProbe`) is **two-step**: (a) decorate the class with `@register_probe` from `codegenie.probes.registry`; (b) add an explicit module import to `probes/__init__.py`. The decorator is what populates `default_registry`; the import is what triggers it. Hardened AC-12 names both steps and pins them by reference to the established sibling pattern.

**Sixteen harden-tier additions** mirror the S3-01 / S3-02 / S3-03 / S3-04 hardened shape with `NodeManifestProbe`-specific deltas. The dominant theme: the probe is the rule-of-three consumer of the lockfile-parser family, so the dep-flattening + name-normalization logic must land as a **registry of pure flatteners** (`_FLATTENERS: Mapping[ParserKind, Callable[[Any], Mapping[str, str]]]`) so a future `_bun.py` is one entry + one literal addition, never a `run()` edit. The native-module cross-reference must be a pure module-level function (functional core) so it's testable in isolation. The error-ID translation must follow the same `args[0]` recovery pattern S3-02/S3-03 settled — no instance state on markers.

**Test-implementation deltas vs. draft:**

- **`os.fstat` monkey-patch for the size-cap path** (T-2). Draft `test_oversized_lockfile_degrades_gracefully` wrote 60 MB to tmpfs — same defect S3-01 / S3-02 / S3-03 already corrected. Hardened version forces the path via `monkeypatch.setattr(os, "fstat", ...)` returning a stat-result with an inflated `st_size`.
- **Name-normalization parametrize.** Draft `test_happy_path_pnpm_with_bcrypt` assumed lockfile keys naturally surface `"bcrypt"` as the package name. pnpm v9 stores `/bcrypt@5.1.1`; npm v3 stores `node_modules/bcrypt`; yarn classic stores `bcrypt@^5.1.0`. Without a `_flatten_*` helper that normalizes, the test silently misses the bug where a parser returns the raw key. Hardened TDD plan adds `test_flatten_*_normalizes_to_name_only_keys` parametrized across pnpm v6/v9, npm v1/v3, yarn classic.
- **Exact-match-not-substring** test for native-module cross-reference (Notes §7). Draft Notes said *"`'@types/bcrypt'` is not a hit for `'bcrypt'`; treat catalog names as exact matches"* — but no AC and no test pinned it. Hardened AC-15 + new test `test_cross_reference_exact_match_not_substring` parametrizes the false-positive vectors (`@types/bcrypt`, `bcryptjs`, `bcrypt-utils`).
- **Subprocess net broadened.** Draft `test_no_subprocess_for_dep_resolution` monkey-patched only `subprocess.run`. ADR-0011 forbids *any* subprocess for dep resolution. Hardened test monkey-patches `subprocess.run`, `subprocess.Popen`, `os.spawnv`, `os.execv`, `os.execvp` — every shape a future contributor might reach for.
- **Boundary mutants on multi-lockfile downgrade.** Draft asserts `confidence == "low"` AND `"lockfile.multi_present" in out.warnings` in the same test. Hardened version splits into two tests so each invariant is independently pinned (mutation-testing discipline — kill the "drop the warning but keep low" mutant separately from the "drop the downgrade but keep the warning" mutant).
- **`additionalProperties: false` rejection JSON-Pointer assertion.** Draft AC-13 named the path but provided no test code. Hardened TDD plan includes `test_subschema_rejects_extra_field_at_pointer` parametrized across three injection sites: root, `primary`, `primary.native_modules.packages[0]`. The assertion is on `exc.absolute_path` (jsonschema's path field), not the message.
- **`_lockfiles/__init__.py` non-edit re-asserted.** S3-02 / S3-03 settled the inert family-init. Hardened S3-05 inherits and adds an architectural test pinning that this story does not touch it.
- **`pkg_path.is_symlink()` co-presence with `.exists()`.** Mirrors `node_build_system.py:566` (`if pkg_path.exists() or pkg_path.is_symlink():`). A dangling symlink fails `.exists()` but is real; the symlink-passthrough path is the test of record (delegated to `safe_json`'s `O_NOFOLLOW`).

**Three design-pattern elevations** (cross-reference Notes for the implementer §10):

- **D-1 — Registry/strategy seam for lockfile dispatch.** Three lockfile formats now exist (S3-01 pnpm, S3-02 npm, S3-03 yarn); S3-05 is the third concrete consumer of the family. Rule-of-three threshold reached. Hardened story prescribes a module-level `_FLATTENERS: Mapping[ParserKind, Callable[[Any], Mapping[str, str]]]` registry — adding a future `_bun.py` is one new entry, zero edits to `run()`. AC-7 phrases the constraint as an *observable* "no edit" guarantee (the kernel/extract opportunity becomes an AC, not just a pattern-name in Notes).

- **D-2 — Functional core / imperative shell on cross-reference.** The native-module cross-reference is pure (`Mapping[str, str], Mapping[str, NativeModuleEntry] -> tuple[NativeModuleHit, ...]`). Lifted to module-level `_cross_reference_native_modules(resolved, catalog)` so it's testable in isolation; `run()` becomes the imperative shell.

- **D-3 — Tagged-union/`Literal` on parser kinds.** `ParserKind = Literal["pnpm", "yarn", "npm"]` declared at module scope; `_PARSER_KIND_BY_FILENAME` mapping is the single source of truth that drives both `_FLATTENERS` and `_error_id`. Mirrors S3-03's `_PARSER_KIND: Final[str] = "yarn_lockfile"` discipline; closes the primitive-obsession smell.

No `NEEDS RESEARCH` findings. Every fix uses patterns already established in the codebase (registry strategy from `node_build_system._LOCKFILE_PRECEDENCE`; functional-core split from `language_detection._framework_hints_from`; positional-message markers from S3-01/02/03; monkey-patch `os.fstat` for size-cap tests; `parser_kind` discriminator from `_io.open_capped`) or in widely-known testing practice (mutation thinking, JSON-Pointer-anchored schema rejection, exact-match catalog cross-reference). Stage 3 skipped.

## Context Brief (Stage 1)

- **Goal verbatim.** Ship `NodeManifestProbe`, its sub-schema, and the native-module catalog cross-reference so `codegenie gather` on a Node repo produces a valid `manifests` slice; multi-lockfile drops `confidence` to `low`; editing `native_modules.yaml` invalidates only this probe's cache.
- **Phase exit criteria touched.**
  - Phase-arch-design.md §"Component design" #4 — full interface contract.
  - Phase-arch-design.md §"Data model" — `ManifestsSlice`, `ManifestEntry`, `NativeModulesBlock`, `NativeModuleHit` shapes.
  - Phase-arch-design.md §"Edge cases" rows 1–4, 8 — pnpm depth-cap, multi-lockfile, catalog-gap, oversized lockfile.
  - Phase-arch-design.md §"Gap analysis" Gap 2 — raw-artifact budget mechanism (now routed through `ResourceBudget` per S1-09 hardening).
  - ADR-0004 — `additionalProperties: false` at sub-schema root + every nested block.
  - ADR-0006 — catalog YAML in `declared_inputs` so any catalog edit invalidates `node_manifest` cache entries at the file-bytes level.
  - ADR-0007 — warning-ID pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.
  - ADR-0011 — explicit "no `npm ls`" and no subprocess for dep resolution.
  - High-level-impl.md §"Step 3" — load-bearing for Phase 7's distroless migration five phases out.
- **Code already on disk that the story must align to.**
  - `src/codegenie/probes/base.py` — frozen `Probe` ABC + `ProbeContext` (extended with `parsed_manifest` / `input_snapshot` in S1-06) + `ProbeOutput` (fields: `schema_slice`, `raw_artifacts`, `confidence`, `duration_ms`, `warnings`, `errors`).
  - `src/codegenie/coordinator/budget.py` — `ResourceBudget(rss_mb, raw_artifact_mb, wall_clock_s, raw_artifact_truncate_mb)`, `BudgetingContext` (the runtime ctx mirror), `DEFAULT_RESOURCE_BUDGET`. **`Probe.declared_raw_artifact_budget_mb` is intentionally absent** per S1-09's hardening.
  - `src/codegenie/probes/_lockfiles/_pnpm.py` — S3-01 baseline (positional markers; `safe_yaml.load` wrapper; `MalformedYAMLError → MalformedLockfileError` translation; `total=False` `PnpmLock` TypedDict).
  - `src/codegenie/probes/_lockfiles/_npm.py` — S3-02 baseline (positional markers; `safe_json.load` wrapper; `__cause__` chain).
  - `src/codegenie/probes/_lockfiles/_yarn.py` — S3-03 baseline (positional markers; `_HAS_PYARN` dispatch; hand-rolled scanner; `parser_kind="yarn_lockfile"` discriminator).
  - `src/codegenie/probes/_lockfiles/__init__.py` — `__all__: list[str] = []` (inert; S3-02 / S3-03 invariant).
  - `src/codegenie/catalogs/__init__.py` — `NATIVE_MODULES`, `NATIVE_MODULES_CATALOG_VERSION` exported from S1-05.
  - `src/codegenie/probes/node_build_system.py` — `_LOCKFILE_PRECEDENCE`, `@register_probe`, `ProbeOutput` construction with `schema_slice=` / `raw_artifacts=[]` / `duration_ms=` — the sibling-probe pattern of record.
  - `src/codegenie/probes/registry.py` — `register_probe` decorator and `default_registry`.
- **Phase 0 marker contract (load-bearing).**
  - `tests/unit/test_errors.py::test_subclasses_are_markers_only`.
  - `tests/unit/test_errors.py::test_phase1_subclasses_accept_message_arg_and_expose_args0` (positional-only; `not hasattr(exc, "path" | "cap" | "detail" | "warning_id")`).
- **Validation precedents (the family discipline already settled).**
  - `_validation/S1-09-raw-artifact-budget.md` — `ResourceBudget` route; S3-05 explicitly named as consumer.
  - `_validation/S3-01-pnpm-lockfile-parser.md` — lockfile-parser shape; inert-init; positional markers.
  - `_validation/S3-02-npm-lockfile-parser.md` — S3-02's family inheritance; `_translate` rule-of-three deferred to S3-03 land-time then to S3-05 (this story).
  - `_validation/S3-03-yarn-lockfile-parser.md` — `parser_kind` discriminator; strict UTF-8; `_HAS_PYARN` dispatch; **rule-of-three explicitly deferred to the third caller** (this story).
  - `_validation/S3-04-yarn-parser-parity-oracle.md` — mutation thinking; functional-core helpers; registry threshold framing.
- **Open ambiguities surfaced (resolved in hardened story).**
  1. `declared_raw_artifact_budget_mb` vs. `declared_resource_budget` — **resolved**: `declared_resource_budget = ResourceBudget(raw_artifact_mb=50, raw_artifact_truncate_mb=25)` per S1-09.
  2. `ProbeOutput.data` vs. `ProbeOutput.schema_slice` — **resolved**: `schema_slice` (frozen ABC).
  3. Lockfile precedence `pnpm > npm > yarn` (draft) vs. `pnpm > yarn > npm` (arch + node_build_system) — **resolved**: arch wins.
  4. `@register_probe` decorator vs. explicit-import only — **resolved**: both; mirrors sibling probes.
  5. Lockfile-key name normalization (pnpm `/bcrypt@5.1.1`, npm `node_modules/bcrypt`, yarn `bcrypt@^5.1.0, bcrypt@^5.0`) — **resolved**: per-format pure flattener helpers exposed as a `_FLATTENERS` registry (D-1).
  6. Native-module catalog substring-vs-exact match — **resolved**: exact match pinned by AC-15 + dedicated false-positive parametrize.
  7. Subprocess net (only `subprocess.run`?) — **resolved**: broadened to `subprocess.run`, `subprocess.Popen`, `os.spawnv`, `os.execv`, `os.execvp` (T-3).
  8. Helper extraction rule-of-three — **resolved**: ELEVATE. S3-01/S3-02/S3-03 punted; S3-05 is the third concrete consumer of the lockfile-parser family. Registry pattern lands here (D-1).

## Stage 2 — critic reports (synthesized; parallel fan-out omitted per token economy, mirroring S3-03 / S3-04 precedent)

### Consistency (verdict: BLOCK + harden)

| # | Severity | Finding |
|---|---|---|
| K-1 | **block** | Draft AC-1 prescribes `declared_raw_artifact_budget_mb = 25` as a class attribute. The Phase 0 + S1-09 hardened mechanism explicitly does NOT extend the `Probe` ABC; budgets live in `ResourceBudget`. S1-09 names S3-05 as the consumer of `declared_resource_budget = ResourceBudget(raw_artifact_mb=50, raw_artifact_truncate_mb=25)`. |
| K-2 | **block** | Draft Green-code constructs `ProbeOutput(data=..., confidence=..., errors=..., warnings=...)`. Frozen ABC fields are `schema_slice`, `raw_artifacts`, `confidence`, `duration_ms`, `warnings`, `errors`. Every test in the TDD plan asserts on `out.data["manifests"]` — would fail to import. |
| K-3 | **block** | Draft AC-4 lockfile precedence: `pnpm > npm > yarn`. Phase-arch-design.md line 801 and `node_build_system._LOCKFILE_PRECEDENCE`: `bun > pnpm > yarn > npm`. yarn/npm reversed. |
| K-4 | **block** | Draft AC-12 says "explicit import" only; `@register_probe` decorator missing. Sibling probes use the two-step pattern. |
| K-5 | harden | Param naming `(snapshot, ctx)` doesn't match established `(repo, ctx)` (or `(snap, ctx)` per `budget.py` docstring). |
| K-6 | harden | Draft doesn't pin the `EVENT_PROBE_START` / `EVENT_PROBE_FAILURE` / `EVENT_PROBE_SUCCESS` structlog emission discipline — sibling probes emit on every lifecycle boundary. |
| K-7 | harden | No AC pins the `pkg_path.exists() or pkg_path.is_symlink()` co-presence check that `node_build_system.py:566` already established (dangling-symlink + `safe_json`'s `O_NOFOLLOW` passthrough). |
| K-8 | harden | The error-ID list in Notes §12 doesn't trace to a single source-of-truth helper. The `_error_id(filename, exc_type) -> WarningId` translation should be a pure module-level function with `_PARSER_KIND_BY_FILENAME` driving both flattener dispatch and error-ID prefix. |
| K-9 | harden | No AC pinning that `_lockfiles/__init__.py` remains inert (S3-02 / S3-03 architectural invariant). |

### Coverage (verdict: COVERAGE-block + harden)

| # | Severity | Finding |
|---|---|---|
| CV-1 | **block** | No AC and no test pins **lockfile-key name normalization**. pnpm v9 stores `/bcrypt@5.1.1`; npm v3 stores `node_modules/bcrypt`; yarn classic stores `bcrypt@^5.1.0, bcrypt@^5.0`. Without per-format `_flatten_*` helpers, the catalog cross-reference would either no-op (if it compares raw keys) or false-match-on-substring. Phase 7's distroless migration is silent-staleness-prone if this is wrong (final-design.md "Risks" #1). |
| CV-2 | harden | No AC for "lockfile present but no dep entries (`packages: {}`)" → `native_modules.detected: False`, `confidence: high` (arch edge case #8). |
| CV-3 | harden | No AC for "package.json present, no lockfile" → `manifests.primary.lockfile: None`, `native_modules.detected: False`. |
| CV-4 | harden | No AC for "package.json missing entirely" → slice is `None` (per arch §"Data model") or low-confidence with `package_json.missing`. |
| CV-5 | harden | No AC for "`optionalDependencies` absent or null in package.json" → `optional_dependencies: 0`. |
| CV-6 | harden | No AC pinning that `manifests.catalog_version` is the file-level integer, not a per-entry `catalog_entry_version`. Swap mutant would pass. |
| CV-7 | harden | Boundary case missing: exactly one lockfile present → `confidence: high`, no `lockfile.multi_present` warning. Mutation-killing test for "always-low" mutant. |
| CV-8 | harden | No AC for resource-budget invariant (`raw_artifact_truncate_mb=25 <= raw_artifact_mb=50`) at class construction time. |

### Test Quality (verdict: TESTS-block + harden)

Mutation-thinking pass — would the draft TDD plan catch these?

| # | Wrong implementation | Caught by draft TDD? | Severity |
|---|---|---|---|
| T-1 | `_cross_reference` does substring match (catches `@types/bcrypt`, `bcryptjs`) | NO — only positive happy-path test | **block** |
| T-2 | `_flatten_pnpm` returns lockfile keys verbatim (`/bcrypt@5.1.1`) | NO — happy-path test would pass if the catalog also lookups by `/bcrypt@5.1.1`; tested only end-to-end | **block** |
| T-3 | `confidence` set to `"low"` always, regardless of inputs | PARTIAL — multi-lockfile test passes; single-lockfile happy-path test asserts `"high"` (good) | harden |
| T-4 | `lockfile.multi_present` warning omitted; `confidence` still demoted to `"low"` | NO — single test conflates both assertions | harden |
| T-5 | `_error_id` always returns `pnpm_lock.size_cap_exceeded` | NO — only one parser-exception test | harden |
| T-6 | Subprocess call leak via `subprocess.Popen` (not `run`) | NO — only `subprocess.run` monkey-patched | harden |
| T-7 | Catalog version drift (uses `NATIVE_MODULES_CATALOG_VERSION + 1`) | NO — no equality check against expected | harden |
| T-8 | Sub-schema's `additionalProperties: false` removed at nested `packages[0]` block | NO — only one rejection test | harden |
| T-9 | 60 MB tmpfs write for size-cap | NA — defect from prior stories; `monkeypatch.setattr(os, "fstat", ...)` is the pattern of record | harden |

### Design Patterns (verdict: harden + elevate)

| # | Severity | Finding |
|---|---|---|
| D-1 | harden / **elevate to AC-7** | S3-01/S3-02/S3-03 deferred the rule-of-three threshold for a shared lockfile dispatch kernel to "the third consumer of the family." S3-05 is the third concrete consumer. Lift dispatch to a module-level `_FLATTENERS: Mapping[ParserKind, Callable[[Any], Mapping[str, str]]]` registry; adding a future `_bun.py` is one new entry + one literal in `ParserKind`. The Open/Closed seam becomes an AC ("adding a new lockfile format must require zero edits to `run()`"). |
| D-2 | harden | The native-module cross-reference is pure data → data. Lift to module-level `_cross_reference_native_modules(resolved, catalog)` for isolation testing. Functional core / imperative shell. |
| D-3 | harden | Introduce `ParserKind = Literal["pnpm", "yarn", "npm"]` at module scope. Drives `_FLATTENERS`, `_PARSER_KIND_BY_FILENAME`, and the `_error_id` prefix. Tagged-union/`Literal` discipline; closes primitive obsession. |
| D-4 | harden | Domain identifier discipline: `WarningId` already a typed `Annotated[str, Pattern(...)]` in arch §"Data model". The `_error_id` helper return type should be the same `WarningId` newtype-by-Annotated — types catch malformed prose-judgment IDs at land time, not at sub-schema validation. |
| D-5 | nit | The `manifests` slice is built as a plain dict per S2-02 convention (validated at envelope merge). Don't promote to a Pydantic model in this story — arch §"Data model" Pydantic shapes are illustrative; the Python-runtime validation chokepoint is `_ProbeOutputValidator`. Status-quo correct. |
| D-6 | nit | `_PARSER_KIND_BY_FILENAME` ordering must mirror `_LOCKFILE_PRECEDENCE` from `node_build_system.py` for the parsed-formats subset. Keep them in deliberate lockstep so a future re-ordering is a one-place edit. |
| D-7 | (validated) | The probe doesn't import sibling parsers via the `_lockfiles/__init__.py` family-init (which is inert); imports go directly to `_pnpm`, `_npm`, `_yarn`. Already extension-by-addition. |

## Stage 3 — Researcher

**Skipped.** No findings tagged `NEEDS RESEARCH`. Every fix uses patterns already established:

- Registry/strategy seam — `_LOCKFILE_PRECEDENCE` from `node_build_system.py:116-121`.
- Functional-core split — `_framework_hints_from`, `_detect_monorepo` from `language_detection.py`.
- Positional-message markers — every Phase 1 marker via `tests/unit/test_errors.py` parametrize.
- `os.fstat` monkey-patch for size-cap — settled by S3-01 / S3-02 / S3-03 hardenings.
- `parser_kind` discriminator + Literal — settled by S3-03.
- Mutation-resistance test pairing — settled by S3-04.

## Stage 4 — Edits applied

1. **Validation notes block** appended below the story header.
2. **`Depends on`** updated: replace the obsolete S1-09 `declared_raw_artifact_budget_mb` reference with `S1-09 (ResourceBudget extension — declared_resource_budget surface)`.
3. **Acceptance criteria** restructured from 17 unnumbered checkboxes to AC-1..AC-23 (numbered for TDD traceability):
   - AC-1 — `declared_resource_budget = ResourceBudget(raw_artifact_mb=50, raw_artifact_truncate_mb=25)` (K-1).
   - AC-2 — `node_modules/**` absent from `declared_inputs` (unchanged from draft AC-2).
   - AC-3 — `package.json` via memo + `safe_json.load` fallback; `pkg_path.exists() or pkg_path.is_symlink()` co-presence (K-7).
   - AC-4 — corrected precedence `pnpm-lock.yaml > yarn.lock > package-lock.json` driven by `_PARSER_KIND_BY_FILENAME` (K-3, D-6); `bun.lockb` present-only for multi-detect.
   - AC-5 — multi-lockfile splits into separate boundary assertions (T-3, T-4, CV-7).
   - AC-6 — parser-exception catch → `ProbeOutput(confidence="low", errors=[<typed id>])`; gather continues. Error-ID translation via the `_error_id` helper (K-8, D-3, D-4).
   - **AC-7 — D-1 registry elevation:** `_FLATTENERS` registry; adding a future format is zero-edit on `run()`. Pinned by an architectural test.
   - AC-8 — Native-module cross-reference as a pure module-level function (D-2); `detected = len(packages) > 0`.
   - AC-9 — `manifests.catalog_version` populated from `NATIVE_MODULES_CATALOG_VERSION` (file-level int, not per-entry) (CV-6).
   - AC-10 — `optionalDependencies` / `bundledDependencies` extraction; absent → `0` / `[]` (CV-5).
   - AC-11 — Sub-schema `additionalProperties: false` at root + every nested block.
   - AC-12 — `warnings[]` pattern constraint (ADR-0007).
   - AC-13 — `@register_probe` decorator + explicit `probes/__init__.py` import (K-4).
   - AC-14 — Sub-schema rejection test parametrized at three JSON Pointer injection sites (T-8).
   - AC-15 — Catalog cross-reference exact-match, not substring (CV-1, T-1).
   - AC-16 — Lockfile-key name normalization across pnpm v6/v9, npm v1/v3, yarn classic (CV-1, T-2).
   - AC-17 — Catalog YAML in `declared_inputs` (ADR-0006 invariant — unchanged).
   - AC-18 — No subprocess for dep resolution; broader net (T-6).
   - AC-19 — TDD red-green discipline.
   - AC-20 — `_lockfiles/__init__.py` non-edit (K-9).
   - AC-21 — `ResourceBudget` invariant pinned at class construction (CV-8).
   - AC-22 — Param-naming `(repo, ctx)` (K-5).
   - AC-23 — Structlog event discipline (K-6).
4. **Implementation outline** rewritten — registry-first ordering; pure helpers before `run()`; correct `ProbeOutput` field names; `@register_probe` decorator.
5. **Red TDD code** replaced:
   - All assertions use `out.schema_slice["manifests"]` (K-2).
   - `os.fstat` monkey-patch replaces 60 MB tmpfs write (T-9).
   - New tests: `test_flatten_pnpm_normalizes_keys`, `test_flatten_npm_normalizes_keys`, `test_flatten_yarn_normalizes_comma_joined_keys`, `test_cross_reference_exact_match_not_substring`, `test_register_probe_decorator_populates_default_registry`, `test_subschema_rejects_extra_field_at_pointer` (parametrized at three sites), `test_no_subprocess_for_dep_resolution` (broader net), `test_resource_budget_invariant`, `test_single_lockfile_keeps_confidence_high`, `test_multi_lockfile_emits_warning_independent_of_confidence`, `test_multi_lockfile_downgrades_confidence_independent_of_warning`, `test_lockfiles_init_remains_inert`.
6. **Green section** updated to reflect:
   - `declared_resource_budget = ResourceBudget(raw_artifact_mb=50, raw_artifact_truncate_mb=25)`.
   - `ProbeOutput(schema_slice=..., raw_artifacts=[], confidence=..., duration_ms=..., warnings=..., errors=...)`.
   - `@register_probe` decorator.
   - `_FLATTENERS` registry sketch.
   - `_cross_reference_native_modules` as a pure module-level function.
7. **Refactor section** updated with the rule-of-three resolution.
8. **Files to touch** added clarifying notes; `_lockfiles/__init__.py` listed as **NOT touched** (with architectural test).
9. **Out of scope** unchanged (correctly excludes fixtures + integration to S3-06).
10. **Notes for the implementer** restructured into 14 numbered points. Design-pattern review at §10–§13 records the rule-of-three resolution, the functional-core split, the `ParserKind` Literal, and the Open/Closed seam.

## Final state

- Every AC is individually verifiable from CI logs.
- The AC set collectively guarantees the goal (slice shape + multi-lockfile downgrade + catalog hit + cache-invalidation invariant + extension-by-addition).
- Every invariant has a mutation-killing test pair (boundary tests, broadened subprocess net, name-normalization parametrize, JSON-Pointer-anchored schema rejection, exact-match catalog cross-reference).
- No AC contradicts phase-arch-design.md, ADR-0004/0006/0007/0011, S1-09's `ResourceBudget` route, S3-01/02/03's family discipline, or CLAUDE.md "Extension by addition" + "Facts, not judgments".
- The registry/strategy seam at `_FLATTENERS` + `_PARSER_KIND_BY_FILENAME` makes adding a future `_bun.py` a zero-edit-to-`run()` change.

**Verdict: HARDENED. Ready for `phase-story-executor`.**
