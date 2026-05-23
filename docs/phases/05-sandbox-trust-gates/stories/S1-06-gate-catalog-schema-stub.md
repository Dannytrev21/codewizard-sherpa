# Story S1-06 — Gate YAML catalog schema + empty `stage6_validate.yaml` stub

**Step:** Step 1 — Scaffold packages, contracts, and CI fences
**Status:** HARDENED
**Effort:** S
**Depends on:** S1-01 (errors + `EVENT_*` + structlog), S1-02 (`SandboxSpec` Pydantic shape), S1-04 (`RetryPolicy`, `TransitionId`, `Gate` ABC), S1-05 (`SignalKind` newtype + `signal_kind_registry`)
**ADRs honored:** ADR-0006, ADR-0012, ADR-0014, ADR-0015

## Validation notes (2026-05-23, phase-story-validator)

**Verdict:** HARDENED. The draft correctly identified the deliverables (schema + loader + stub) and traced to ADR-0006 / ADR-0014 / ADR-0015, but had **18 weaknesses across all four critic lenses including six block-tier findings** that an executor following the draft literally would have silently violated. The most consequential were:

1. **(consistency — block) `RetryPolicyEntry` re-declaration silently forks the canonical `gates/contract.RetryPolicy`.** S1-04 shipped `RetryPolicy` with the disjoint-cross-field `@model_validator` (retryable ⊥ non-retryable per S1-04 AC-I-4). The draft proposed a new `RetryPolicyEntry` class inside `catalog_loader.py` — two parallel models, the contract invariant lost on the catalog side, and an executor would have re-implemented or simply omitted the disjointness check. Resolution: `CatalogEntry.retry_policy` is typed as `RetryPolicy` (imported from `codegenie.gates.contract`); the disjointness invariant rides for free; the schema's `retry_policy` block remains the structural-shape gate (jsonschema first, Pydantic second — belt-and-suspenders). New AC-MOD-1 / AC-MOD-2 / AC-XFIELD-1.
2. **(consistency — block) `transition` string-enum drift from `TransitionId`.** Draft schema's `transition` enum hardcoded `["stage6_validate","stage6_validate_loose"]`; `gates/contract.TransitionId` is the canonical closed enum (S1-04 AC-3a pins the member set). Two literal places to keep in sync — drift would silently ship a schema that accepts the wrong value or rejects a future Phase-6 `TransitionId` member. Resolution: schema enum values are DERIVED at test time from `TransitionId.__members__` (a sync test in `tests/gates/test_catalog_schema.py` asserts byte-equality between the schema's `transition.enum` array and `[m.value for m in TransitionId]`); `CatalogEntry.transition` is typed as `TransitionId`. New AC-ENUM-1 / AC-ENUM-2 / AC-ENUM-3.
3. **(coverage — block) `additionalProperties: false` enforced only at top level by the draft TDD plan.** The draft's `test_schema_rejects_unknown_top_level_key` would pass even if an executor omits `additionalProperties: false` from `retry_policy`, `sandbox`, each `phases[]` entry, and `attempt_overrides` values — every nested level is silently open. A YAML with `retry_policy: {ridiculous: 1}` or `sandbox: {smuggle: true}` would round-trip. New parametrized AC-SCHEMA-NESTED-1..AC-SCHEMA-NESTED-5 — one row per nested object level — drives a parametrized rejection test.
4. **(coverage — block) Cross-field invariant inheritance not enforced.** Even with `CatalogEntry.retry_policy: RetryPolicy`, a YAML with `retry_policy: {max_attempts:1, retryable_failures:[tests], non_retryable_failures:[tests], timeout_retryable:false}` must raise `GateCatalogInvalid` (translating S1-04's `RetryPolicyAmbiguous` / `pydantic.ValidationError`). AC-XFIELD-1 + paired test.
5. **(test-quality — block) `_*.yaml` skip is not mutation-resistant.** Draft's `test_load_all_skips_underscore_prefixed_files` only checks the **positive case** (`stage6_validate` present + no key starts with `_`). A mutation `if path.name == "_schema.json": continue` (one specific file) passes the test trivially because no other underscore file exists in the fixture. Resolution: fixture creates `_skipme.yaml` and `_also_skipme.yaml` alongside `stage6_validate.yaml`; assert dict keys are exactly `{"stage6_validate"}`; assert `_skipme` and `_also_skipme` are NOT in the loaded payload by both prefix-absence AND positive id-set equality. AC-SKIP-1..AC-SKIP-3.
6. **(coverage — block) Empty / non-mapping YAML produces `AttributeError`, not `GateCatalogInvalid`.** `yaml.safe_load("")` returns `None`; `yaml.safe_load("- a\n- b")` returns a `list`. Passing either straight into `_validator.validate(...)` raises `jsonschema.ValidationError` for the list case but the `None` case raises `TypeError` deep in jsonschema (the surface arc says it's "unhashable") — neither path is reliably translated to `GateCatalogInvalid` with a useful message. Resolution: explicit type-check after `yaml.safe_load` — anything that is not a `dict` raises `GateCatalogInvalid` with a uniform "expected YAML mapping, got <type>" message that names the file path. AC-IO-1 / AC-IO-2 / AC-IO-3.

Beyond the block-tier findings, the harden-tier work:

7. **(coverage / patterns — harden) `load_all` duplicate-`gate_id` raising promoted from Refactor to AC.** Draft buried "duplicate `gate_id` across files raises `GateCatalogInvalid`" in Refactor — a Refactor "should" is unobservable to the executor's validator. Promoted to AC-LOADALL-3 with paired test (two stub files with identical `gate_id`).
8. **(coverage — harden) `load_all` deterministic ordering pinned.** Downstream consumers (S3-01 `SandboxSpecBuilder`, S4-05 `StrictAndGate.from_yaml`, Phase 6 LangGraph) may iterate the returned dict; relying on `Path.glob` order is platform-dependent. AC-LOADALL-2: iteration order is sorted lexicographically by `path.name`. (The dict insertion order in Python 3.7+ then preserves this; consumers may rely on it.)
9. **(coverage — harden) Error message MUST include the offending YAML key path.** Draft Refactor said "use `err.absolute_path` from `jsonschema` and join with `/`" — unobservable. Promoted to AC-ERR-1 / AC-ERR-2 / AC-ERR-3 with paired tests asserting the message contains both the file path (so a CLI exit 2 operator can locate the file) AND the YAML key path (so the operator can locate the offending field). Format: `"<path>: <yaml_key_path>: <jsonschema-message>"`.
10. **(coverage — harden) `attempt_overrides` key shape constrained.** Arch shows `"2"` (numeric string for attempt number); draft AC said only "string keys." A mutation that accepts `"never"` or empty string would pass. AC-OVR-1: keys MUST match `^[1-9][0-9]*$` (positive integer, no leading zero). AC-OVR-2: each value validates against the *partial sandbox* schema (relaxed copy — see §"Schema design notes" below).
11. **(coverage — harden) `cmd: array[string]` requires `minItems: 1` and `phases` validates with `minItems: 0` for the stub only.** Empty `cmd` would silently round-trip. AC-SCHEMA-CMD-1.
12. **(coverage — harden) `base_image` is required, non-empty, and digest-shaped.** Schema requires `base_image: {type: string, pattern: "^[^\\s]+@sha256:[0-9a-f]{64}$"}` so S3-05's digest pinning has a structural floor. The stub uses the all-zeros placeholder `cgr.dev/chainguard/node@sha256:0000000000000000000000000000000000000000000000000000000000000000` which IS schema-valid (matches the pattern) but obviously fake. A comment at the top of the stub names this and points at S3-05. AC-SCHEMA-IMG-1.
13. **(coverage — harden) `phases[].network` enum + `phases[].name` non-empty.** Draft Implementation outline §Green named the enum prose-only. AC-SCHEMA-PHASE-1 / AC-SCHEMA-PHASE-2 (parametrized rejection tests for unknown network value, empty name).
14. **(coverage — harden) `retry_policy.max_attempts` integer ≥ 1 (matches S1-04 `AttemptNumber` bound 1..1024).** Draft prose; pinned in AC-SCHEMA-RETRY-1.
15. **(consistency — harden) Module purity test (mirrors S1-02 / S1-03 / S1-04 / S1-05).** Every prior Step-1 story shipped a `test_*_purity.py` AST walker. Story now ships `tests/gates/test_catalog_loader_purity.py` (TYPE_CHECKING-aware) enforcing (a) `from __future__ import annotations` immediately after the module docstring, (b) alphabetized `__all__` containing exactly the public surface (`{"CatalogEntry", "load", "load_all"}`), (c) module docstring cites ADR-0006 / ADR-0012 / ADR-0014 / ADR-0015 and the `lockfile_policy.py` precedent for codegenie-owned trusted YAML, (d) imports limited to stdlib + `jsonschema` + `pydantic` + `yaml` + `codegenie.{gates.contract, gates.errors, gates.logging, sandbox.contract, types.identifiers}`. AC-PURE-1..AC-PURE-4.
16. **(patterns — harden) Validator constructed ONCE at module import (`@functools.lru_cache(maxsize=1)`).** Mirrors `src/codegenie/schema/validator.py:_validator()`. Schema-read + Draft202012Validator construction is ~30 ms; per-call cost is unacceptable when `load_all` iterates N files. Pinned as AC-PERF-1 (test-observable via `caplog`-free identity check: `_validator() is _validator()`).
17. **(patterns — nit, surfaced in Notes) `CatalogEntry` is the 4th codegenie-owned trusted-YAML loader (after `LockfilePolicy.from_yaml`, `TCCMLoader.load`, `SkillsLoader._load_one_skill`).** Rule-of-three has been technically reached but the four loaders have *legitimately different* error semantics: SkillsLoader is multi-file partial-success; TCCMLoader is single-file raise-on-error with marker-prefix protocol; LockfilePolicy uses `Result[T, E]` discriminated union; S1-06 is single-file raise-on-error (per arch §Edge case 13 — CLI exit 2 before any gate runs). The right pattern here is `LockfilePolicy.from_yaml` (the closest sibling). Note recorded: if S3-05's `sandbox-policy.yaml` loader and any Phase 7 distroless catalog loader both repeat the jsonschema+Pydantic-second pattern, extract a shared `codegenie.catalogs._yaml_with_schema.load(path, schema_path, model_cls)` helper. NOT for S1-06.
18. **(consistency — harden) Coverage floor wording aligned.** Draft's "tests pass" replaced by the standard "line ≥ 95% AND branch ≥ 90%" (same gap S1-02..S1-05 closed).

**No `RESCUE`-tier findings.** Every weakness was patchable by tightening ACs, adding nested-rejection parametrized tests, reusing the existing `RetryPolicy` and `TransitionId` from `gates/contract.py`, and mirroring the established `LockfilePolicy.from_yaml` precedent for codegenie-owned trusted YAML.

**No Stage-3 research needed.** Every gap was answerable from Phase 5 arch + ADR-0006/-0012/-0014/-0015 + the four prior HARDENED reports (S1-01/S1-02/S1-03/S1-04/S1-05) + the codebase precedents in `src/codegenie/transforms/policy/lockfile_policy.py`, `src/codegenie/schema/validator.py`, `src/codegenie/skills/loader.py`, `src/codegenie/conventions/catalog.py`.

Full validation report at [`_validation/S1-06-gate-catalog-schema-stub.md`](_validation/S1-06-gate-catalog-schema-stub.md).

## Context

Gate logic in Phase 5 is configured as **data** — YAML catalogs under `gates/catalog/` define each gate's required signals, retry policy, and per-attempt sandbox overrides. This satisfies the "organizational uniqueness as data, not prompts" load-bearing commitment from `CLAUDE.md`. This story ships the JSON Schema that pins the catalog shape, a loader that validates against it, and an empty-but-schema-valid `stage6_validate.yaml` stub so Step 3's `SandboxSpecBuilder` (S3-01) has a real file to consume.

The catalog YAML files are **codegenie-owned and trusted** (they ship inside the wheel under `src/codegenie/gates/catalog/`); they are NOT analyzed-repo content. The loader therefore uses `yaml.safe_load` directly (mirroring [`src/codegenie/transforms/policy/lockfile_policy.py`](../../../../src/codegenie/transforms/policy/lockfile_policy.py)) rather than the `codegenie.parsers.safe_yaml` chokepoint, which is reserved for hostile analyzed-repo YAML. Document this rationale in the loader module docstring; a future contributor must not refactor it into the parser chokepoint.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Data model — gates/catalog/stage6_validate.yaml` (lines 778–808) — full populated YAML showing every key the schema must accept; this story ships only the stub, but the *schema* must allow this full shape.
  - `../phase-arch-design.md §Component design — SandboxSpecBuilder` (lines 604–612) — `gates/catalog/<gate_id>.yaml` shape; per-attempt overrides; phases; env_allowlist reference; `GateCatalogInvalid` raise semantics.
  - `../phase-arch-design.md §Edge case 13` (line 865) — invalid YAML against `_schema.json` raises `GateCatalogInvalid`; CLI exit 2 before any gate runs.
  - `../phase-arch-design.md §Open questions §4` (line 1059) — one catalog or two (`stage6_validate.yaml` + `stage6_validate_loose.yaml`); this story ships one stub; S3-05 populates both.
- **Phase ADRs (rules this story honors):**
  - `../ADRs/0006-protocol-vs-abc-convention.md` — ADR-0006 — `Gate` is an ABC; YAML loader produces a structural payload (`CatalogEntry`); the eventual concrete `StrictAndGate` instantiation lands in S4-05; here we only validate shape.
  - `../ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md` — ADR-0012 — `sandbox.env_allowlist` schema field MUST be an array of strings; the loader does NOT resolve env values (S3-01 does that). The schema rejects any per-gate `env: {...}` block (illegal — only the allowlist is configurable here).
  - `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — ADR-0014 — `required_signals` enumerates `SignalKind` strings; loader does not coerce signal-kind names that contain banned substrings. `CatalogEntry` (and all nested models) carry `extra="forbid", frozen=True` per the ADR-0014 inheritance pattern that S1-03 / S1-04 already established. The introspection walker `iter_nested_field_names` from `sandbox/signals/_introspection.py` (S1-03) is reused to assert no banned-substring field name slips into `CatalogEntry`.
  - `../ADRs/0015-test-inventory-delta-asymmetric-policy.md` — ADR-0015 — `retry_policy.non_retryable_failures` may include `trace`; this story's stub leaves the policy lists empty so the schema is exercised but no logic is implied.
- **Source design:**
  - `../final-design.md §Component-5` — YAML catalog rationale.
- **High-level impl:**
  - `../High-level-impl.md §Step 1 — Features delivered` bullet 5 + Step 1 done-criteria bullet 1.
- **Prior validated stories carried forward:**
  - S1-01 (`_validation/S1-01-...`) — canonical event-name table (`EVENT_GATE_*` constants); rules for *adding* new constants ("append, never rename, never re-value"). This story adds two new gate-catalog event constants in `gates/logging.py` per that policy.
  - S1-04 (`_validation/S1-04-...`) — `RetryPolicy` Pydantic model with disjoint-cross-field `@model_validator`; `TransitionId` enum with pinned member set; `AttemptNumber` newtype bound 1..1024.
  - S1-05 (`_validation/S1-05-...`) — `Registry` class pattern with `.fresh()` factory + module-level singleton + optional `registry=` kwarg (Phase 3 `SignalKindRegistry` mirror). NOT directly used here (the catalog is read-only data, not a registry), but the module-purity AST-walk fence pattern carries forward.
- **Codebase precedents:**
  - [`src/codegenie/transforms/policy/lockfile_policy.py`](../../../../src/codegenie/transforms/policy/lockfile_policy.py) — codegenie-owned trusted YAML loader with `yaml.safe_load` directly + Pydantic round-trip + `importlib.resources` for wheel-shipped path resolution. CLOSEST sibling pattern.
  - [`src/codegenie/schema/validator.py`](../../../../src/codegenie/schema/validator.py) — `@functools.lru_cache(maxsize=1)` Draft202012Validator construction; `jsonschema.ValidationError → SchemaValidationError(f"validation failed at {err.json_path}: {err.message}")` error-translation pattern; the `json_path` (== `/`-joined key trail) is the canonical operator-facing "where did it fail" address.

## Goal

Ship `src/codegenie/gates/catalog/_schema.json` (JSON Schema draft 2020-12 with `additionalProperties: false` at every object level and a digest-shape regex on `base_image`), `src/codegenie/gates/catalog_loader.py` (single-file raise-on-error loader using `yaml.safe_load` per the `lockfile_policy` precedent, with a once-cached `Draft202012Validator`, `CatalogEntry` Pydantic model that *reuses* `RetryPolicy` and `TransitionId` from `gates/contract.py`), and an empty-but-schema-valid `src/codegenie/gates/catalog/stage6_validate.yaml` stub carrying a placeholder zeroed digest (S3-05 replaces with the real Chainguard digest). The loader translates jsonschema and Pydantic validation errors into a single `GateCatalogInvalid` exception whose message names both the file path and the YAML key path of the failing field.

## Acceptance criteria

### A. Schema is structurally valid JSON Schema draft 2020-12

- [ ] **AC-SCHEMA-META-1** `src/codegenie/gates/catalog/_schema.json` is parseable JSON and validates against its own meta-schema via `jsonschema.Draft202012Validator.check_schema(s)` (no exception).
- [ ] **AC-SCHEMA-META-2** The schema declares `"$schema": "https://json-schema.org/draft/2020-12/schema"` and `"$id"` (any stable identifier; e.g. `"https://codegenie.dev/schemas/gates/catalog/v1.json"`).
- [ ] **AC-SCHEMA-META-3** The schema's top-level `type` is `"object"`.

### B. Required top-level keys

- [ ] **AC-SCHEMA-TOP-1** Top-level `required` array (sorted alphabetically) is exactly `["gate_id", "required_signals", "retry_policy", "sandbox", "transition"]`. `attempt_overrides` is optional.
- [ ] **AC-SCHEMA-TOP-2** Top-level `properties` keys are exactly the six above (no others).
- [ ] **AC-SCHEMA-TOP-3** Top-level `additionalProperties: false`.

### C. `additionalProperties: false` at every nested object level (mutation-resistant)

For every nested object level listed, the schema sets `"additionalProperties": false` and the test suite parametrizes a rejection case (one extra key per level):

- [ ] **AC-SCHEMA-NESTED-1** `retry_policy` object — extra key `retry_policy.smuggle: 1` raises `GateCatalogInvalid` via `load()`.
- [ ] **AC-SCHEMA-NESTED-2** `sandbox` object — extra key `sandbox.smuggle: true` raises `GateCatalogInvalid`.
- [ ] **AC-SCHEMA-NESTED-3** Each `sandbox.phases[]` entry — extra key `sandbox.phases[0].smuggle: "x"` raises `GateCatalogInvalid`.
- [ ] **AC-SCHEMA-NESTED-4** Each `attempt_overrides[<n>]` value (partial sandbox block) — extra key inside an override raises `GateCatalogInvalid`.
- [ ] **AC-SCHEMA-NESTED-5** The `attempt_overrides` map itself rejects non-pattern keys: any key not matching `^[1-9][0-9]*$` raises `GateCatalogInvalid` (achieved via `patternProperties` + `additionalProperties: false`).

### D. Field-shape constraints

- [ ] **AC-SCHEMA-GATE-1** `gate_id: {type: "string", minLength: 1}`.
- [ ] **AC-SCHEMA-RETRY-1** `retry_policy.max_attempts: {type: "integer", minimum: 1, maximum: 1024}` (matches `AttemptNumber` newtype bound from S1-04).
- [ ] **AC-SCHEMA-RETRY-2** `retry_policy.retryable_failures` and `retry_policy.non_retryable_failures` are both `{type: "array", items: {type: "string", minLength: 1}}` (kind-name registry stays open per ADR-0003; schema does NOT enumerate kinds).
- [ ] **AC-SCHEMA-RETRY-3** `retry_policy.timeout_retryable: {type: "boolean"}`.
- [ ] **AC-SCHEMA-IMG-1** `sandbox.base_image: {type: "string", pattern: "^[^\\s]+@sha256:[0-9a-f]{64}$"}` — digest-shape pin. An unpinned image string (no `@sha256:`) raises `GateCatalogInvalid`. Paired test exercises both the all-zeros placeholder (passes) and `"cgr.dev/chainguard/node:latest"` (rejected — missing digest).
- [ ] **AC-SCHEMA-RES-1** `sandbox.time_budget_seconds`, `sandbox.memory_limit_mib`, `sandbox.pids_limit` are all `{type: "integer", minimum: 1}`.
- [ ] **AC-SCHEMA-ALLOWLIST-1** `sandbox.env_allowlist: {type: "array", items: {type: "string", minLength: 1}}`.
- [ ] **AC-SCHEMA-PHASE-1** Each `phases[]` entry requires `["cmd", "name", "network"]` (alphabetized) with optional `egress_allowlist` (array of string) and `enable_trace` (boolean).
- [ ] **AC-SCHEMA-PHASE-2** `phases[].name: {type: "string", minLength: 1}`.
- [ ] **AC-SCHEMA-PHASE-3** `phases[].network: {enum: ["none", "scoped"]}` — `"open"`, `"any"`, etc. rejected.
- [ ] **AC-SCHEMA-CMD-1** `phases[].cmd: {type: "array", minItems: 1, items: {type: "string"}}` — empty `cmd` rejected.
- [ ] **AC-SCHEMA-PHASES-1** `sandbox.phases: {type: "array", items: {...}}`. **Stub-only carve-out:** `minItems: 0` for now (S3-05 will tighten via amendment when populated catalogs ship). This is documented in the schema description.

### E. `transition` derives from `TransitionId` and stays in sync

- [ ] **AC-ENUM-1** `_schema.json`'s `properties.transition.enum` is byte-equal to `sorted(m.value for m in codegenie.gates.contract.TransitionId)`. Test loads both, sorts, asserts equality. (Pins the drift S1-04 AC-3a calls out.)
- [ ] **AC-ENUM-2** `CatalogEntry.transition: TransitionId` (Pydantic typed; not raw `str`).
- [ ] **AC-ENUM-3** YAML with `transition: stage7_distroless` (not a `TransitionId` member) raises `GateCatalogInvalid`. Paired test.

### F. `CatalogEntry` reuses canonical models from `gates/contract.py`

- [ ] **AC-MOD-1** `CatalogEntry` is a Pydantic v2 `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` (asserted via `model_config['extra'] == 'forbid' and model_config['frozen'] is True`).
- [ ] **AC-MOD-2** `CatalogEntry.retry_policy: RetryPolicy` (imported from `codegenie.gates.contract`); no `RetryPolicyEntry` class is declared in `catalog_loader.py` — `RetryPolicy` is the single declaration site (test asserts `typing.get_type_hints(CatalogEntry)['retry_policy'] is RetryPolicy`).
- [ ] **AC-MOD-3** `CatalogEntry.transition: TransitionId` (imported from `codegenie.gates.contract`).
- [ ] **AC-MOD-4** Nested Pydantic models `_SandboxBlock`, `_PhaseEntry`, `_AttemptOverride` (module-private — underscored — not in `__all__`) carry `model_config = ConfigDict(frozen=True, extra="forbid")`. Parametrized test for each.
- [ ] **AC-MOD-5** **No banned-substring field names anywhere in `CatalogEntry`'s recursive field tree.** Reuse S1-03's `iter_nested_field_names` from `codegenie.sandbox.signals._introspection`; assert no name (case-insensitive) matches `{"confidence", "llm", "self_reported", "model_says"}`. (ADR-0014 inheritance — same pattern as S1-04 AC-INH.)

### G. Cross-field invariant inherited from `RetryPolicy`

- [ ] **AC-XFIELD-1** YAML with `retry_policy.retryable_failures` and `retry_policy.non_retryable_failures` sharing any element (e.g., both contain `"tests"`) raises `GateCatalogInvalid`. The translation comes from Pydantic's `RetryPolicy` `@model_validator` (S1-04 AC-I-4) — the loader catches `pydantic.ValidationError` and re-raises as `GateCatalogInvalid` with the file path + key path prefix.

### H. `load(path) -> CatalogEntry`

- [ ] **AC-LOAD-1** `from codegenie.gates.catalog_loader import load` succeeds; `load` is a module-level function (not a classmethod) per the `LockfilePolicy.from_yaml` sibling-shape parity (smart-constructor classmethod is also valid; the module-function form is chosen for parity with `codegenie.schema.validator.validate` which is the *other* JSON-Schema-backed loader the codebase ships).
- [ ] **AC-LOAD-2** `load(Path("stage6_validate.yaml"))` returns a `CatalogEntry` instance with `entry.gate_id == "stage6_validate"`, `entry.transition is TransitionId.STAGE6_VALIDATE`.
- [ ] **AC-LOAD-3** `load` reads the file via `yaml.safe_load` (NEVER `yaml.load`); asserted by AST walk in the purity test (AC-PURE-4).
- [ ] **AC-LOAD-4** `load(missing_path)` raises `GateCatalogInvalid` (not the bare `FileNotFoundError`); message names the path.

### I. `load(path)` handles malformed / non-mapping YAML cleanly

- [ ] **AC-IO-1** Empty file (`""`) → `yaml.safe_load` returns `None` → `load` raises `GateCatalogInvalid` with message `"<path>: expected YAML mapping, got NoneType"`. Paired test.
- [ ] **AC-IO-2** YAML list at top level (`"- a\n- b"`) → `load` raises `GateCatalogInvalid` with message `"<path>: expected YAML mapping, got list"`. Paired test.
- [ ] **AC-IO-3** YAML scalar at top level (`"42"`) → `load` raises `GateCatalogInvalid` with message `"<path>: expected YAML mapping, got int"`. Paired test.
- [ ] **AC-IO-4** Syntactically invalid YAML (`": :"`) → `yaml.safe_load` raises `yaml.YAMLError`; `load` catches and re-raises as `GateCatalogInvalid` with `"<path>: YAML parse error: <pyyaml-message>"`. Paired test.

### J. Error-message contract

- [ ] **AC-ERR-1** Every `GateCatalogInvalid` raised by `load` includes the **file path** as the first colon-delimited token (so a CLI exit-2 operator can locate the file).
- [ ] **AC-ERR-2** Every `GateCatalogInvalid` raised by `load` from a *schema* violation includes the failing YAML key path derived from `jsonschema.ValidationError.absolute_path` joined with `/` (e.g., `"<path>: retry_policy/max_attempts: <message>"`). Paired test asserts presence of `"retry_policy/max_attempts"` in the exception string for a malformed `max_attempts: 0`.
- [ ] **AC-ERR-3** Every `GateCatalogInvalid` raised by `load` from a *Pydantic* violation (e.g., cross-field disjointness) includes the Pydantic location path (e.g., `"<path>: retry_policy: retryable_failures and non_retryable_failures must be disjoint"`). Paired test.

### K. `load_all(catalog_dir) -> dict[str, CatalogEntry]`

- [ ] **AC-LOADALL-1** `load_all(catalog_dir)` iterates `catalog_dir.glob("*.yaml")` excluding any file whose name begins with `_`; returns `dict[str, CatalogEntry]` keyed by `gate_id`.
- [ ] **AC-LOADALL-2** Iteration order is **sorted lexicographically by file name**; downstream consumers may rely on dict insertion order (Python 3.7+).
- [ ] **AC-LOADALL-3** **Duplicate `gate_id` across two files raises `GateCatalogInvalid`** with message naming both offending file paths and the colliding `gate_id`. Paired test creates `stage6_validate.yaml` and `dup.yaml` both carrying `gate_id: stage6_validate`.
- [ ] **AC-LOADALL-4** `load_all` on an empty directory returns `{}` (not an exception).
- [ ] **AC-LOADALL-5** `load_all` propagates per-file `GateCatalogInvalid` from any `load` call (no swallowing; raise-on-first-error since per arch §Edge case 13 the operator must fix and re-run).

### L. `_*.yaml` skip is mutation-resistant

- [ ] **AC-SKIP-1** Fixture: a temp directory containing `stage6_validate.yaml` (valid), `_skipme.yaml` (intentionally syntactically broken YAML), and `_also_skipme.yaml` (intentionally broken). `load_all(tmpdir)` returns exactly `{"stage6_validate": ...}` and does NOT raise on the underscore files.
- [ ] **AC-SKIP-2** No key in the returned dict starts with `_`.
- [ ] **AC-SKIP-3** A second fixture containing `_something_else.yaml` (alongside the stub) confirms the skip rule is "any `_`-prefixed name", not "the specific name `_schema.json`" — set-equality on the returned dict's `gate_id` keys is the strict assertion.

### M. Stub file is schema-valid and digest-shape-clean

- [ ] **AC-STUB-1** `src/codegenie/gates/catalog/stage6_validate.yaml` exists; `load(it)` returns successfully; `entry.gate_id == "stage6_validate"`, `entry.required_signals == []`, `entry.sandbox.phases == []`.
- [ ] **AC-STUB-2** The stub's `base_image` value matches the schema digest pattern (passes `AC-SCHEMA-IMG-1`); it is the all-zeros placeholder `"cgr.dev/chainguard/node@sha256:0000000000000000000000000000000000000000000000000000000000000000"`.
- [ ] **AC-STUB-3** The stub carries a YAML comment header naming "STUB — S3-05 replaces with real Chainguard digest" so an operator inspecting the file knows it's intentionally non-functional.

### N. Validator cached at module import (performance + correctness)

- [ ] **AC-PERF-1** `catalog_loader._validator` is decorated with `@functools.lru_cache(maxsize=1)`; `catalog_loader._validator() is catalog_loader._validator()` (identity check — same object on subsequent calls). Tests that mutate the schema file in-process must call `catalog_loader._validator.cache_clear()` first.

### O. Module purity (AST walker mirror of S1-02/S1-03/S1-04/S1-05)

- [ ] **AC-PURE-1** `tests/gates/test_catalog_loader_purity.py` walks `src/codegenie/gates/catalog_loader.py` AST and asserts: the very first non-docstring statement is `from __future__ import annotations`.
- [ ] **AC-PURE-2** `set(codegenie.gates.catalog_loader.__all__) == {"CatalogEntry", "load", "load_all"}` (exact set equality; private nested models `_SandboxBlock`, `_PhaseEntry`, `_AttemptOverride` are NOT exported; `_validator` is NOT exported).
- [ ] **AC-PURE-3** The module docstring contains the substrings `"ADR-0006"`, `"ADR-0012"`, `"ADR-0014"`, `"ADR-0015"`, and `"lockfile_policy"` (so a reader knows the precedent + the rules being honored).
- [ ] **AC-PURE-4** AST walk asserts only the following top-level imports: stdlib (`functools`, `json`, `pathlib`, `typing`) + third-party (`jsonschema`, `pydantic`, `yaml`) + `codegenie.{gates.contract, gates.errors, gates.logging, sandbox.contract, types.identifiers}`. ANY other import (especially `subprocess`, `os.system`, `urllib`, `socket`, `requests`, `anthropic`, `openai`) fails the test. AST walk explicitly searches for `yaml.load` (the unsafe form) and asserts ABSENT — only `yaml.safe_load` is allowed.

### P. New `EVENT_*` constants appended to `gates/logging.py` (S1-01 policy)

Per S1-01 Validation note §6 ("S2-01, S5-01, S6-02 ... add a row below the existing entries — they do not rename"), this story appends:

- [ ] **AC-EVENT-1** `EVENT_GATE_CATALOG_LOADED: Final[str] = "gate.catalog.loaded"` — emitted (`logger.info`) by `load_all` on success with `extra={"path": str(catalog_dir), "count": len(result)}`. Constant added to `src/codegenie/gates/logging.py` `__all__`. Pinned by `caplog` test.
- [ ] **AC-EVENT-2** `EVENT_GATE_CATALOG_INVALID: Final[str] = "gate.catalog.invalid"` — emitted (`logger.error`) by `load` immediately before raising `GateCatalogInvalid`, with `extra={"path": str(path), "yaml_key_path": "<derived>"}`. Pinned by `caplog` test.
- [ ] **AC-EVENT-3** Both new constants conform to the S1-01 `EVENT_VALUE_RE` regex (dotted-lowercase) and uniqueness assertions in `tests/sandbox/test_event_constants.py` continue to pass (no value collision with existing `EVENT_GATE_*` rows).

### Q. Quality gates

- [ ] **AC-GATE-1** `ruff check src/codegenie/gates/catalog_loader.py tests/gates/test_catalog_schema.py tests/gates/test_catalog_loader.py tests/gates/test_catalog_loader_purity.py` clean.
- [ ] **AC-GATE-2** `ruff format --check` clean on the same set.
- [ ] **AC-GATE-3** `mypy --strict src/codegenie/gates/catalog_loader.py` clean (no `Any`, no untyped function).
- [ ] **AC-GATE-4** `pytest tests/gates/test_catalog_schema.py tests/gates/test_catalog_loader.py tests/gates/test_catalog_loader_purity.py` green.
- [ ] **AC-GATE-5** Coverage on `src/codegenie/gates/catalog_loader.py`: **line ≥ 95% AND branch ≥ 90%**. Schema-rejection paths, file-not-found path, duplicate-`gate_id` path, empty-yaml / list-yaml / scalar-yaml paths, the lru_cache identity path — all exercised.
- [ ] **AC-GATE-6** TDD plan's red tests exist, are committed, and are green.

## Schema design notes (Implementer reference)

The `attempt_overrides` block is a **map of attempt-number-strings → partial `sandbox`-block overrides**. Schema design choice:

- The key constraint (`^[1-9][0-9]*$`) lives in `patternProperties` + top-level `attempt_overrides.additionalProperties: false`.
- The value constraint is a **relaxed copy** of the `sandbox` block — every key under `sandbox` becomes optional under `attempt_overrides.<n>`. (The arch example shows attempt-2 overriding only `phases`.)
- Implementation: define the `sandbox` block as a `$defs/SandboxBlock` reference, and define `$defs/PartialSandboxBlock` with the same `properties` but empty `required` array. The two share `additionalProperties: false` for safety.

This is the only piece of schema design that requires careful authoring — the rest is shape-pinning. Test fixtures in `tests/gates/test_catalog_schema.py` should include at least one fully-populated `attempt_overrides` example (the arch-line-803 example) plus a rejection case for each nested level.

## Implementation outline

1. **Write `src/codegenie/gates/catalog/_schema.json`** as a Draft 2020-12 schema with `$defs/SandboxBlock`, `$defs/PartialSandboxBlock`, `$defs/PhaseEntry`, `$defs/RetryPolicy`. `additionalProperties: false` at every object level (top, retry_policy, sandbox, each phase, each attempt-override value). Filename is `_`-prefixed so `load_all` skips it.
2. **Write `src/codegenie/gates/catalog/stage6_validate.yaml`** minimal stub with the all-zeros digest placeholder, empty `required_signals`, empty `phases`, and the comment header naming S3-05.
3. **Create `src/codegenie/gates/catalog_loader.py`:**
   - Module docstring cites ADR-0006/-0012/-0014/-0015 + the `lockfile_policy.py` precedent for codegenie-owned trusted YAML.
   - Imports: `functools`, `json`, `pathlib.Path`, `typing` + `jsonschema`, `pydantic` (`BaseModel`, `ConfigDict`, `ValidationError`), `yaml`. From `codegenie`: `gates.contract.{RetryPolicy, TransitionId}`, `gates.errors.GateCatalogInvalid`, `gates.logging.{EVENT_GATE_CATALOG_LOADED, EVENT_GATE_CATALOG_INVALID}`.
   - Module-private Pydantic models `_PhaseEntry`, `_SandboxBlock`, `_AttemptOverride` (frozen + extra-forbid).
   - Public `CatalogEntry` with `gate_id: str`, `transition: TransitionId`, `required_signals: list[str]`, `retry_policy: RetryPolicy` (canonical), `sandbox: _SandboxBlock`, `attempt_overrides: dict[str, _AttemptOverride] | None = None`.
   - `_SCHEMA_PATH = Path(__file__).parent / "catalog" / "_schema.json"` resolved via `importlib.resources` (wheel-safe — mirror `lockfile_policy._resolve_policy_path`).
   - `_validator() -> jsonschema.Draft202012Validator` decorated `@functools.lru_cache(maxsize=1)`.
   - `load(path: Path) -> CatalogEntry`:
     1. `try: raw = yaml.safe_load(path.read_text())` — catch `OSError` → `GateCatalogInvalid(f"{path}: …")`; catch `yaml.YAMLError` → `GateCatalogInvalid(f"{path}: YAML parse error: …")`.
     2. Type-check: `if not isinstance(raw, dict): raise GateCatalogInvalid(f"{path}: expected YAML mapping, got {type(raw).__name__}")`.
     3. `try: _validator().validate(raw)` — catch `jsonschema.ValidationError` → `key_path = "/".join(map(str, err.absolute_path))`; `raise GateCatalogInvalid(f"{path}: {key_path}: {err.message}")`. Emit `EVENT_GATE_CATALOG_INVALID` via logger before raising.
     4. `try: entry = CatalogEntry.model_validate(raw)` — catch `pydantic.ValidationError` → translate location list to `/`-joined path; `raise GateCatalogInvalid(f"{path}: {pyd_path}: {err.errors()[0]['msg']}")`.
     5. Return `entry`.
   - `load_all(catalog_dir: Path) -> dict[str, CatalogEntry]`:
     1. Iterate `sorted(catalog_dir.glob("*.yaml"), key=lambda p: p.name)`.
     2. Skip entries whose name starts with `_`.
     3. For each, call `load(p)`; build dict keyed by `entry.gate_id`. Duplicate key → `GateCatalogInvalid(f"duplicate gate_id {entry.gate_id} in {p} and {prev_path}")`.
     4. Emit `EVENT_GATE_CATALOG_LOADED` with `extra={"path": str(catalog_dir), "count": len(result)}`.
     5. Return result.
4. **Append two `EVENT_GATE_CATALOG_*` constants** to `src/codegenie/gates/logging.py` (per S1-01 policy: append, never re-value).
5. **Write the three test files** (`test_catalog_schema.py`, `test_catalog_loader.py`, `test_catalog_loader_purity.py`) per the TDD plan below.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file paths: `tests/gates/test_catalog_schema.py`, `tests/gates/test_catalog_loader.py`, `tests/gates/test_catalog_loader_purity.py`.

#### `tests/gates/test_catalog_schema.py`

```python
"""Schema-level tests — exercise _schema.json structurally without invoking the loader.

Covers AC-SCHEMA-META-1..3, AC-SCHEMA-TOP-1..3, AC-SCHEMA-NESTED-1..5, AC-SCHEMA-*-1..N
plus the AC-ENUM-1 TransitionId-sync invariant.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from codegenie.gates.contract import TransitionId

SCHEMA = Path(__file__).resolve().parents[2] / "src/codegenie/gates/catalog/_schema.json"

@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA.read_text())

@pytest.fixture(scope="module")
def validator(schema: dict) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(schema)

# --- AC-SCHEMA-META ---

def test_schema_is_valid_draft_2020_12(schema: dict) -> None:
    jsonschema.Draft202012Validator.check_schema(schema)

def test_schema_declares_meta_uri(schema: dict) -> None:
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "$id" in schema

def test_schema_top_type_is_object(schema: dict) -> None:
    assert schema["type"] == "object"

# --- AC-SCHEMA-TOP ---

def test_schema_top_required_is_exact(schema: dict) -> None:
    assert sorted(schema["required"]) == ["gate_id", "required_signals", "retry_policy", "sandbox", "transition"]

def test_schema_top_properties_keys_exact(schema: dict) -> None:
    assert set(schema["properties"].keys()) == {
        "gate_id", "transition", "required_signals", "retry_policy", "sandbox", "attempt_overrides",
    }

def test_schema_top_additional_properties_false(schema: dict) -> None:
    assert schema["additionalProperties"] is False

# --- AC-ENUM-1: TransitionId sync ---

def test_transition_enum_byte_equal_to_TransitionId(schema: dict) -> None:
    schema_enum = sorted(schema["properties"]["transition"]["enum"])
    actual = sorted(m.value for m in TransitionId)
    assert schema_enum == actual, f"schema/TransitionId drift: {schema_enum} vs {actual}"

# --- AC-SCHEMA-NESTED — parametrized extra-key rejection at every object level ---

_VALID = {
    "gate_id": "stage6_validate",
    "transition": "stage6_validate",
    "required_signals": [],
    "retry_policy": {"max_attempts": 1, "retryable_failures": [], "non_retryable_failures": [], "timeout_retryable": False},
    "sandbox": {
        "base_image": "cgr.dev/chainguard/node@sha256:" + "0" * 64,
        "time_budget_seconds": 1, "memory_limit_mib": 1, "pids_limit": 1,
        "env_allowlist": [], "phases": [],
    },
}

def _mutate(d: dict, path: list[str], key: str, value) -> dict:
    """Deep-copy d, walk to path, set d[...][key] = value."""
    import copy
    out = copy.deepcopy(d)
    cur = out
    for p in path:
        cur = cur[p]
    cur[key] = value
    return out

@pytest.mark.parametrize("path", [[], ["retry_policy"], ["sandbox"]])
def test_schema_rejects_unknown_key_at_object_level(validator, path: list[str]) -> None:
    bad = _mutate(_VALID, path, "smuggle", True)
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad)

def test_schema_rejects_unknown_key_inside_phase_entry(validator) -> None:
    bad = json.loads(json.dumps(_VALID))
    bad["sandbox"]["phases"] = [{"name": "x", "network": "none", "cmd": ["a"], "smuggle": "y"}]
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad)

def test_schema_rejects_unknown_key_inside_attempt_override(validator) -> None:
    bad = json.loads(json.dumps(_VALID))
    bad["attempt_overrides"] = {"2": {"smuggle": "y"}}
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad)

def test_schema_attempt_overrides_key_pattern(validator) -> None:
    for bad_key in ["never", "", "0", "01", "1.5", "-1"]:
        bad = json.loads(json.dumps(_VALID))
        bad["attempt_overrides"] = {bad_key: {"phases": []}}
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(bad)

# --- AC-SCHEMA-IMG-1: base_image digest pattern ---

def test_schema_rejects_unpinned_base_image(validator) -> None:
    bad = json.loads(json.dumps(_VALID))
    bad["sandbox"]["base_image"] = "cgr.dev/chainguard/node:latest"
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad)

def test_schema_accepts_zero_placeholder_digest(validator) -> None:
    validator.validate(_VALID)  # all-zeros digest is shape-valid by design

# --- AC-SCHEMA-PHASE-3 / AC-SCHEMA-CMD-1 ---

def test_schema_rejects_unknown_network(validator) -> None:
    bad = json.loads(json.dumps(_VALID))
    bad["sandbox"]["phases"] = [{"name": "x", "network": "open", "cmd": ["a"]}]
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad)

def test_schema_rejects_empty_cmd(validator) -> None:
    bad = json.loads(json.dumps(_VALID))
    bad["sandbox"]["phases"] = [{"name": "x", "network": "none", "cmd": []}]
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad)

# --- AC-SCHEMA-RETRY-1 ---

@pytest.mark.parametrize("bad_value", [0, -1, 1025, "3", 1.5])
def test_schema_rejects_invalid_max_attempts(validator, bad_value) -> None:
    bad = json.loads(json.dumps(_VALID))
    bad["retry_policy"]["max_attempts"] = bad_value
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad)

# --- AC-SCHEMA-FULL: arch-line-779 fully-populated example round-trips ---

def test_schema_accepts_full_example_from_arch_doc(validator) -> None:
    example = {
        "gate_id": "stage6_validate",
        "transition": "stage6_validate",
        "required_signals": ["build", "install", "tests", "trace", "policy", "cve_delta"],
        "retry_policy": {
            "max_attempts": 3,
            "retryable_failures": ["build", "install", "tests", "policy", "cve_delta"],
            "non_retryable_failures": ["trace"],
            "timeout_retryable": False,
        },
        "sandbox": {
            "base_image": "cgr.dev/chainguard/node@sha256:" + "a" * 64,
            "time_budget_seconds": 600, "memory_limit_mib": 2048, "pids_limit": 1024,
            "env_allowlist": ["PATH", "NODE_ENV", "NPM_CONFIG_*", "HTTPS_PROXY"],
            "phases": [
                {"name": "install", "network": "scoped",
                 "egress_allowlist": ["registry.npmjs.org"],
                 "cmd": ["sh", "-c", "cd /work && npm ci --ignore-scripts"]},
                {"name": "test", "network": "none", "enable_trace": True,
                 "cmd": ["sh", "-c", "cd /work && npm test"]},
            ],
        },
        "attempt_overrides": {
            "2": {"phases": [{"name": "test", "network": "none",
                              "cmd": ["sh", "-c", "cd /work && npm test -- --verbose"]}]},
        },
    }
    validator.validate(example)
```

#### `tests/gates/test_catalog_loader.py`

```python
"""Loader-level tests — exercise load() / load_all() error translation and event emission.

Covers AC-MOD-*, AC-XFIELD-1, AC-LOAD-*, AC-IO-*, AC-ERR-*, AC-LOADALL-*, AC-SKIP-*,
AC-STUB-*, AC-EVENT-*, AC-PERF-1.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml

from codegenie.gates.catalog_loader import CatalogEntry, _validator, load, load_all
from codegenie.gates.contract import RetryPolicy, TransitionId
from codegenie.gates.errors import GateCatalogInvalid

REPO = Path(__file__).resolve().parents[2]
CATALOG_DIR = REPO / "src/codegenie/gates/catalog"

VALID_YAML = """\
gate_id: x
transition: stage6_validate
required_signals: []
retry_policy: {max_attempts: 1, retryable_failures: [], non_retryable_failures: [], timeout_retryable: false}
sandbox:
  base_image: "cgr.dev/chainguard/node@sha256:0000000000000000000000000000000000000000000000000000000000000000"
  time_budget_seconds: 1
  memory_limit_mib: 1
  pids_limit: 1
  env_allowlist: []
  phases: []
"""

# --- AC-MOD-2 / AC-MOD-3: CatalogEntry uses canonical types ---

def test_catalog_entry_retry_policy_is_canonical() -> None:
    import typing
    assert typing.get_type_hints(CatalogEntry)["retry_policy"] is RetryPolicy

def test_catalog_entry_transition_is_TransitionId() -> None:
    import typing
    assert typing.get_type_hints(CatalogEntry)["transition"] is TransitionId

# --- AC-MOD-1 / AC-MOD-4: frozen + extra-forbid on every Pydantic model ---

@pytest.mark.parametrize("cls_name", ["CatalogEntry", "_SandboxBlock", "_PhaseEntry", "_AttemptOverride"])
def test_models_are_frozen_and_extra_forbid(cls_name: str) -> None:
    import codegenie.gates.catalog_loader as mod
    cls = getattr(mod, cls_name)
    assert cls.model_config["frozen"] is True
    assert cls.model_config["extra"] == "forbid"

# --- AC-MOD-5: no banned-substring field names ---

def test_no_banned_substring_in_catalog_entry_fields() -> None:
    from codegenie.sandbox.signals._introspection import iter_nested_field_names
    BANNED = {"confidence", "llm", "self_reported", "model_says"}
    names = set(iter_nested_field_names(CatalogEntry)) | set(CatalogEntry.model_fields)
    for name in names:
        for banned in BANNED:
            assert banned not in name.lower(), f"{name!r} contains banned substring {banned!r}"

# --- AC-LOAD-1 / AC-LOAD-2: stub round-trips ---

def test_stub_yaml_loads_cleanly() -> None:
    entry = load(CATALOG_DIR / "stage6_validate.yaml")
    assert entry.gate_id == "stage6_validate"
    assert entry.transition is TransitionId.STAGE6_VALIDATE
    assert entry.required_signals == []
    assert entry.sandbox.phases == []

def test_stub_yaml_carries_zero_digest_placeholder() -> None:
    entry = load(CATALOG_DIR / "stage6_validate.yaml")
    assert entry.sandbox.base_image == "cgr.dev/chainguard/node@sha256:" + "0" * 64

def test_stub_yaml_carries_S3_05_marker_comment() -> None:
    text = (CATALOG_DIR / "stage6_validate.yaml").read_text()
    assert "S3-05" in text  # operator-facing breadcrumb

# --- AC-LOAD-4: missing path ---

def test_missing_path_raises_gate_catalog_invalid(tmp_path: Path) -> None:
    with pytest.raises(GateCatalogInvalid) as exc:
        load(tmp_path / "does_not_exist.yaml")
    assert "does_not_exist.yaml" in str(exc.value)

# --- AC-IO-*: non-mapping / empty / scalar / list / syntax-error YAML ---

@pytest.mark.parametrize("body, type_name", [
    ("", "NoneType"),
    ("- a\n- b\n", "list"),
    ("42\n", "int"),
    ("just a string\n", "str"),
])
def test_non_mapping_yaml_raises(tmp_path: Path, body: str, type_name: str) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text(body)
    with pytest.raises(GateCatalogInvalid) as exc:
        load(p)
    assert "expected YAML mapping" in str(exc.value)
    assert type_name in str(exc.value)
    assert "bad.yaml" in str(exc.value)

def test_yaml_syntax_error_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text(": :\n")
    with pytest.raises(GateCatalogInvalid) as exc:
        load(p)
    assert "YAML parse error" in str(exc.value)
    assert "bad.yaml" in str(exc.value)

# --- AC-ERR-2: schema-violation message names the YAML key path ---

def test_schema_error_message_names_key_path(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    bad = yaml.safe_load(VALID_YAML)
    bad["retry_policy"]["max_attempts"] = 0  # below minimum
    p.write_text(yaml.safe_dump(bad))
    with pytest.raises(GateCatalogInvalid) as exc:
        load(p)
    assert "retry_policy/max_attempts" in str(exc.value)
    assert "bad.yaml" in str(exc.value)

# --- AC-XFIELD-1: disjoint cross-field inherited from RetryPolicy ---

def test_disjoint_retryable_lists_enforced(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    bad = yaml.safe_load(VALID_YAML)
    bad["retry_policy"]["retryable_failures"] = ["tests"]
    bad["retry_policy"]["non_retryable_failures"] = ["tests"]
    p.write_text(yaml.safe_dump(bad))
    with pytest.raises(GateCatalogInvalid) as exc:
        load(p)
    # Either jsonschema or Pydantic raises; either way the message names retry_policy
    assert "retry_policy" in str(exc.value)
    assert "bad.yaml" in str(exc.value)

# --- AC-ENUM-3: TransitionId rejection ---

def test_unknown_transition_value_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    bad = yaml.safe_load(VALID_YAML)
    bad["transition"] = "stage7_distroless"
    p.write_text(yaml.safe_dump(bad))
    with pytest.raises(GateCatalogInvalid) as exc:
        load(p)
    assert "transition" in str(exc.value)

# --- AC-LOADALL-1 / -2 / -4 ---

def test_load_all_real_catalog_returns_stub(tmp_path: Path) -> None:
    result = load_all(CATALOG_DIR)
    assert "stage6_validate" in result
    assert not any(k.startswith("_") for k in result)

def test_load_all_empty_dir_returns_empty(tmp_path: Path) -> None:
    assert load_all(tmp_path) == {}

def test_load_all_sorted_by_filename(tmp_path: Path) -> None:
    for name in ["zebra.yaml", "alpha.yaml", "middle.yaml"]:
        bad = yaml.safe_load(VALID_YAML)
        bad["gate_id"] = name.replace(".yaml", "")
        (tmp_path / name).write_text(yaml.safe_dump(bad))
    result = load_all(tmp_path)
    assert list(result.keys()) == ["alpha", "middle", "zebra"]

# --- AC-LOADALL-3: duplicate gate_id ---

def test_duplicate_gate_id_raises(tmp_path: Path) -> None:
    for name in ["a.yaml", "b.yaml"]:
        bad = yaml.safe_load(VALID_YAML)
        bad["gate_id"] = "shared"
        (tmp_path / name).write_text(yaml.safe_dump(bad))
    with pytest.raises(GateCatalogInvalid) as exc:
        load_all(tmp_path)
    msg = str(exc.value)
    assert "shared" in msg and "a.yaml" in msg and "b.yaml" in msg

# --- AC-SKIP-1 / -3: underscore prefix is a real rule, not a specific name ---

def test_load_all_skips_arbitrary_underscore_files(tmp_path: Path) -> None:
    # Valid stub
    valid = yaml.safe_load(VALID_YAML)
    (tmp_path / "ok.yaml").write_text(yaml.safe_dump(valid))
    # Intentionally broken files prefixed with underscore — must NOT be loaded
    (tmp_path / "_skipme.yaml").write_text("not: a: valid: catalog\n@@@\n")
    (tmp_path / "_also_skipme.yaml").write_text(": :\n")
    (tmp_path / "_something_else.yaml").write_text("garbage")
    result = load_all(tmp_path)
    assert set(result.keys()) == {"x"}  # only the valid one (gate_id=x)

# --- AC-PERF-1: validator cached ---

def test_validator_is_cached() -> None:
    _validator.cache_clear()
    a = _validator()
    b = _validator()
    assert a is b

# --- AC-EVENT-1 / -2: event emission ---

def test_load_all_emits_loaded_event(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    from codegenie.gates.logging import EVENT_GATE_CATALOG_LOADED
    valid = yaml.safe_load(VALID_YAML)
    (tmp_path / "ok.yaml").write_text(yaml.safe_dump(valid))
    with caplog.at_level(logging.INFO, logger="codegenie.gates.catalog_loader"):
        load_all(tmp_path)
    assert any(EVENT_GATE_CATALOG_LOADED in record.message or
               getattr(record, "event", "") == EVENT_GATE_CATALOG_LOADED
               for record in caplog.records)

def test_load_emits_invalid_event_on_error(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    from codegenie.gates.logging import EVENT_GATE_CATALOG_INVALID
    (tmp_path / "bad.yaml").write_text("")
    with caplog.at_level(logging.ERROR, logger="codegenie.gates.catalog_loader"):
        with pytest.raises(GateCatalogInvalid):
            load(tmp_path / "bad.yaml")
    assert any(EVENT_GATE_CATALOG_INVALID in record.message or
               getattr(record, "event", "") == EVENT_GATE_CATALOG_INVALID
               for record in caplog.records)
```

#### `tests/gates/test_catalog_loader_purity.py`

```python
"""Module-purity AST walk — mirrors S1-02/S1-03/S1-04/S1-05.

Covers AC-PURE-1..AC-PURE-4. Pin (a) `from __future__ import annotations` discipline,
(b) `__all__` shape, (c) docstring citations, (d) closed import set + `yaml.load` ban.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[2] / "src/codegenie/gates/catalog_loader.py"

@pytest.fixture(scope="module")
def tree() -> ast.Module:
    return ast.parse(MODULE.read_text())

# --- AC-PURE-1: future annotations first ---

def test_future_annotations_is_first_statement(tree: ast.Module) -> None:
    # Skip an optional module docstring
    stmts = list(tree.body)
    if isinstance(stmts[0], ast.Expr) and isinstance(stmts[0].value, ast.Constant):
        stmts = stmts[1:]
    first = stmts[0]
    assert isinstance(first, ast.ImportFrom)
    assert first.module == "__future__"
    assert [a.name for a in first.names] == ["annotations"]

# --- AC-PURE-2: __all__ exact ---

def test_all_is_exact() -> None:
    import codegenie.gates.catalog_loader as mod
    assert set(mod.__all__) == {"CatalogEntry", "load", "load_all"}

# --- AC-PURE-3: docstring citations ---

def test_module_docstring_cites_adrs_and_precedent(tree: ast.Module) -> None:
    doc = ast.get_docstring(tree) or ""
    for token in ("ADR-0006", "ADR-0012", "ADR-0014", "ADR-0015", "lockfile_policy"):
        assert token in doc, f"docstring missing {token}"

# --- AC-PURE-4: closed import set + yaml.load ban ---

_STDLIB = {"functools", "json", "pathlib", "typing"}
_THIRD_PARTY = {"jsonschema", "pydantic", "yaml"}
_CODEGENIE_ALLOWED = {
    "codegenie.gates.contract", "codegenie.gates.errors", "codegenie.gates.logging",
    "codegenie.sandbox.contract", "codegenie.types.identifiers",
}

def test_closed_import_set(tree: ast.Module) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top in _STDLIB | _THIRD_PARTY, f"forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            top = node.module.split(".")[0]
            if top == "codegenie":
                assert node.module in _CODEGENIE_ALLOWED, f"forbidden codegenie import: {node.module}"
            elif node.module == "__future__":
                continue
            else:
                assert top in _STDLIB | _THIRD_PARTY, f"forbidden import: {node.module}"

def test_yaml_load_unsafe_is_banned(tree: ast.Module) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "load":
            if isinstance(node.value, ast.Name) and node.value.id == "yaml":
                pytest.fail("yaml.load is forbidden — use yaml.safe_load")
```

Run; confirm failures (`ModuleNotFoundError`, file-not-found, etc.); commit the failing tests; then implement.

### Green — make it pass

1. Write `_schema.json` with the `$defs/SandboxBlock` / `$defs/PartialSandboxBlock` / `$defs/PhaseEntry` / `$defs/RetryPolicy` structure described in the §Schema design notes. `additionalProperties: false` at every object level. `patternProperties` for `attempt_overrides` keys. `$schema` + `$id` headers. Pull the `transition.enum` array from a copy-paste of `TransitionId` member values (the sync test catches drift).
2. Write the stub `stage6_validate.yaml` with the all-zeros digest placeholder and the `# STUB — S3-05 replaces with the real Chainguard digest` comment header.
3. Implement `catalog_loader.py` per §Implementation outline. Module docstring includes all four ADR citations and the `lockfile_policy` precedent reference.
4. Append `EVENT_GATE_CATALOG_LOADED` and `EVENT_GATE_CATALOG_INVALID` to `gates/logging.py` (extend `__all__`).
5. Run pytest; iterate until green.

### Refactor — clean up

- Verify the schema's `$defs` blocks are reused (don't inline `SandboxBlock` and copy-paste it into `PartialSandboxBlock` — derive via `unevaluatedProperties: false` + omit `required`).
- Inline-doc the partial-override pattern in `_schema.json` with a JSON `"description"` comment.
- Confirm the loader uses `importlib.resources` (NOT `Path(__file__).parent / ...`) for `_SCHEMA_PATH` resolution — wheel-safe.
- Verify the error-message format string is consistent across all four raise sites (`f"{path}: {key_path}: {message}"` for schema; `f"{path}: {message}"` for IO/parse errors).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/gates/catalog/_schema.json` | New file — JSON Schema for gate catalog entries (Draft 2020-12, `additionalProperties: false` at every object level, digest-shape pattern on `base_image`, `transition.enum` synced with `TransitionId`) |
| `src/codegenie/gates/catalog/stage6_validate.yaml` | New file — empty-but-valid stub with all-zeros digest placeholder + S3-05 marker comment |
| `src/codegenie/gates/catalog_loader.py` | New file — `load` / `load_all` / `CatalogEntry` (reusing `RetryPolicy`, `TransitionId` from `gates/contract.py`) + cached validator + event emission |
| `src/codegenie/gates/logging.py` | Append `EVENT_GATE_CATALOG_LOADED` and `EVENT_GATE_CATALOG_INVALID` constants + extend `__all__` |
| `tests/gates/test_catalog_schema.py` | New test — schema validates itself; nested-key rejection at every object level; arch-full-example round-trip; TransitionId sync |
| `tests/gates/test_catalog_loader.py` | New test — load stub; error paths (IO, syntax, schema, Pydantic cross-field); deterministic ordering; duplicate gate_id; underscore-skip mutation-resistant; event emission; validator-cache identity |
| `tests/gates/test_catalog_loader_purity.py` | New test — AST walk: `__future__` annotations, `__all__` exact, docstring citations, closed import set, `yaml.load` ban |

## Out of scope

- **Populating `stage6_validate.yaml` with real `required_signals` / phases** — S3-05.
- **`stage6_validate_loose.yaml`** — S3-05.
- **`SandboxSpecBuilder.for_gate` translating `CatalogEntry` → `SandboxSpec`** — S3-01. (This story produces the `CatalogEntry`; S3-01 consumes it.)
- **`StrictAndGate.from_yaml`** — S4-05 (or wherever the YAML → `Gate` instance translation lands).
- **Catalog hot-reload / watcher** — not a Phase 5 feature.
- **Digest pinning of `sandbox-policy.yaml`** — S3-05 (different file; this story handles gate catalog only).
- **Tightening `sandbox.phases minItems` from 0 to 1** — S3-05 (when real catalogs ship; tightening here would block this story's own stub).
- **Extracting a shared `codegenie.catalogs._yaml_with_schema.load(...)` helper** — recorded under Notes for S3-05 evaluation; only become a real opportunity once a third trusted-YAML-with-schema loader appears.

## Notes for the implementer

- **`yaml.safe_load` is correct, NOT `parsers.safe_yaml`.** The catalog YAML files are codegenie-owned and ship inside the wheel; they are NOT hostile analyzed-repo content. Mirror [`src/codegenie/transforms/policy/lockfile_policy.py`](../../../../src/codegenie/transforms/policy/lockfile_policy.py)'s rationale paragraph in the module docstring so a future contributor does not refactor this into the parser chokepoint. The purity test (AC-PURE-4) bans `yaml.load`.
- **Reuse, don't re-declare.** `RetryPolicy` and `TransitionId` live in `codegenie.gates.contract` (S1-04). Re-declaring them in `catalog_loader.py` would silently fork the disjoint-cross-field invariant and the closed-enum invariant. The validator caught this as a block-tier consistency issue in S1-04's own validation report; do not repeat the same gap here.
- **`additionalProperties: false` is the load-bearing safety latch.** Without it at EVERY nested object level, the "unknown top-level key" test passes trivially. The parametrized rejection test (`test_schema_rejects_unknown_key_at_object_level`) is the mutation-resistance check.
- **Schema-first, Pydantic-second is intentional belt-and-suspenders.** The two systems catch overlapping but distinct shapes of error (jsonschema catches shape; Pydantic catches cross-field + newtype constraints). Do not collapse them into one — the duplication is the safety property.
- **`$defs/SandboxBlock` and `$defs/PartialSandboxBlock` share the same `properties` but differ in `required`.** Author the schema with a single `$defs` source and reference both; the partial form omits `required` so per-attempt overrides can specify only the keys they're changing.
- **`importlib.resources` for the schema path.** Mirror `lockfile_policy._resolve_policy_path` exactly — `Path(__file__).parent` works under editable installs but breaks under some wheel-bundling tools.
- **Validator is `@functools.lru_cache(maxsize=1)`.** Constructing `Draft202012Validator` costs ~30 ms; `load_all` iterating N files would pay 30·N ms. The cache identity test (AC-PERF-1) pins this. Tests that mutate `_schema.json` in-process must `_validator.cache_clear()` first — matches `src/codegenie/schema/validator.py:_validator()` pattern.
- **Error message format is the operator-facing CLI exit 2 message** (arch §Edge case 13). Always include the file path and (for schema errors) the YAML key path. The format is `f"{path}: {key_path}: {message}"` for schema, `f"{path}: {message}"` for IO/parse. Consistency matters — a `make test` failure logging "GateCatalogInvalid: integer minimum violated" without context is the worst-case operator experience.
- **Forward-seam: distroless and Phase 7+.** Phase 7's `distroless_validate.yaml` is auto-discovered by `load_all`; it does NOT require editing this story's files (`load_all`'s `*.yaml` glob + `_*.yaml` skip handles it). Document this in the module docstring as the canonical OCP seam.
- **Future kernel-extract candidate (NOT for S1-06).** Once S3-05's `sandbox-policy.yaml` ships its loader, the jsonschema-first + Pydantic-second pattern will have three home-grown copies (`schema/validator.py`, `catalog_loader.py`, `sandbox-policy loader`). At that point, extract a shared `codegenie.catalogs._yaml_with_schema.load(path, schema_path, model_cls) -> T` helper. Not now — rule-of-three not yet cleared for this exact shape.
- **Coverage floor: line ≥ 95% AND branch ≥ 90%** (aligned with S1-02/S1-03/S1-04/S1-05). The schema-rejection paths + the IO failure modes + the duplicate-`gate_id` branch + the validator-cache identity path are the four spots most likely to be missed.
