# Validation report — S1-06 gate YAML catalog schema + empty `stage6_validate.yaml` stub

**Story:** [`../S1-06-gate-catalog-schema-stub.md`](../S1-06-gate-catalog-schema-stub.md)
**Validated:** 2026-05-23
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S1-06 ships the JSON-Schema-pinned catalog YAML loader that is the structural floor S3-01 (`SandboxSpecBuilder`) builds on. The draft was directionally correct — ADR-0006 / ADR-0014 / ADR-0015 were the right rules to honor, the `_schema.json` + `catalog_loader.py` + stub split matches arch §Component-5, and Out-of-scope correctly deferred S3-01 / S3-05 / S4-05. But it had **18 weaknesses across all four critic lenses, six of them block-tier** that an executor following the draft literally would have silently violated. The most consequential — the ones that would have produced code that *passes every draft test* but *fails when Phase 5 actually composes* — were:

1. **(consistency — block) `RetryPolicyEntry` re-declaration silently forks the canonical `gates/contract.RetryPolicy`.** The S1-04 HARDENED report pinned `RetryPolicy` with a disjoint-cross-field `@model_validator` (retryable ⊥ non_retryable per S1-04 AC-I-4). The draft proposed a new `RetryPolicyEntry` class inside `catalog_loader.py` — two parallel models, the contract invariant lost on the catalog side. An executor following the draft would have re-implemented the disjointness check (drift risk) or simply omitted it (a contradictory YAML would round-trip). Resolution: `CatalogEntry.retry_policy` is typed as `RetryPolicy` (imported from `codegenie.gates.contract`); the disjointness invariant rides for free. New AC-MOD-1 / AC-MOD-2 / AC-XFIELD-1.
2. **(consistency — block) `transition` string-enum drift from `TransitionId`.** The draft schema hardcoded `enum: ["stage6_validate","stage6_validate_loose"]`; `gates/contract.TransitionId` is the canonical closed enum (S1-04 AC-3a pins the member set). Two literal places to keep in sync — drift would silently ship a schema that accepts the wrong value or rejects a future Phase-6 TransitionId member. Resolution: schema enum values are DERIVED at test time from `TransitionId.__members__` (sync test in `tests/gates/test_catalog_schema.py` asserts byte-equality); `CatalogEntry.transition` is typed as `TransitionId`. New AC-ENUM-1 / AC-ENUM-2 / AC-ENUM-3.
3. **(coverage — block) `additionalProperties: false` enforced only at top level by the draft TDD plan.** The draft's `test_schema_rejects_unknown_top_level_key` would pass even if an executor omits `additionalProperties: false` from `retry_policy`, `sandbox`, each `phases[]` entry, and `attempt_overrides` values — every nested level is silently open. A YAML with `retry_policy: {ridiculous: 1}` or `sandbox: {smuggle: true}` would round-trip. New parametrized AC-SCHEMA-NESTED-1..AC-SCHEMA-NESTED-5 drive a parametrized rejection test that walks every nested object level.
4. **(coverage — block) Cross-field invariant inheritance not enforced.** Even with `CatalogEntry.retry_policy: RetryPolicy`, a YAML with `retry_policy.retryable_failures: [tests]` and `retry_policy.non_retryable_failures: [tests]` must raise `GateCatalogInvalid` (translating S1-04's Pydantic `ValidationError`). New AC-XFIELD-1 + paired test (`test_disjoint_retryable_lists_enforced`).
5. **(test-quality — block) `_*.yaml` skip is not mutation-resistant.** The draft's `test_load_all_skips_underscore_prefixed_files` only checks the **positive case** (`stage6_validate` present + no key starts with `_`). A mutation `if path.name == "_schema.json": continue` (skipping one specific file) passes the test trivially because no other underscore file exists in the fixture. Resolution: AC-SKIP-1..AC-SKIP-3 — fixture creates `_skipme.yaml` and `_also_skipme.yaml` and `_something_else.yaml` alongside `stage6_validate.yaml`; assert dict keys are exactly `{"x"}` and no `_`-prefixed file leaked.
6. **(coverage — block) Empty / non-mapping YAML produces `AttributeError`, not `GateCatalogInvalid`.** `yaml.safe_load("")` returns `None`; `yaml.safe_load("- a")` returns a list. Neither path is reliably translated to `GateCatalogInvalid` with a useful message by jsonschema alone — `None` raises `TypeError` deep in jsonschema. Resolution: explicit type-check after `yaml.safe_load` — anything that is not a `dict` raises `GateCatalogInvalid` with a uniform "expected YAML mapping, got <type>" message. AC-IO-1 / AC-IO-2 / AC-IO-3 / AC-IO-4 (the last for the syntax-error path).

Beyond the block-tier findings, the harden-tier work:

7. **(coverage / patterns — harden) `load_all` duplicate-`gate_id` raising promoted from Refactor to AC.** Draft buried "duplicate `gate_id` across files raises `GateCatalogInvalid`" in Refactor — a Refactor "should" is unobservable to the executor's validator. Promoted to AC-LOADALL-3 with paired test (`test_duplicate_gate_id_raises`).
8. **(coverage — harden) `load_all` deterministic ordering pinned.** Downstream consumers (S3-01 `SandboxSpecBuilder`, S4-05 `StrictAndGate.from_yaml`, Phase 6 LangGraph) may iterate the returned dict; relying on `Path.glob` order is platform-dependent. AC-LOADALL-2: iteration order is sorted lexicographically by `path.name`. Pinned by `test_load_all_sorted_by_filename`.
9. **(coverage — harden) Error message MUST include the offending YAML key path.** Draft Refactor said "use `err.absolute_path` from `jsonschema` and join with `/`" — unobservable. Promoted to AC-ERR-1 / AC-ERR-2 / AC-ERR-3 with paired test (`test_schema_error_message_names_key_path`) asserting both the file path AND the YAML key path appear in the exception string for a malformed `max_attempts: 0`. Format pinned: `f"{path}: {key_path}: {message}"`.
10. **(coverage — harden) `attempt_overrides` key shape constrained.** Arch shows `"2"` (numeric string); draft AC said only "string keys." A mutation that accepts `"never"` or empty string would pass. AC-SCHEMA-NESTED-5: keys MUST match `^[1-9][0-9]*$`. Parametrized rejection of `["never", "", "0", "01", "1.5", "-1"]`.
11. **(coverage — harden) `cmd: array[string]` requires `minItems: 1`.** Empty `cmd` would silently round-trip. AC-SCHEMA-CMD-1 + `test_schema_rejects_empty_cmd`.
12. **(coverage — harden) `base_image` is required, non-empty, and digest-shaped.** Schema requires `base_image: {type: string, pattern: "^[^\\s]+@sha256:[0-9a-f]{64}$"}` so S3-05's digest pinning has a structural floor. The stub uses the all-zeros placeholder which IS schema-valid (matches the pattern) but obviously fake. AC-SCHEMA-IMG-1 + `test_schema_rejects_unpinned_base_image`.
13. **(coverage — harden) `phases[].network` enum + `phases[].name` non-empty.** Draft Implementation outline §Green named the enum prose-only. AC-SCHEMA-PHASE-1 / AC-SCHEMA-PHASE-2 + `test_schema_rejects_unknown_network`.
14. **(coverage — harden) `retry_policy.max_attempts` integer ≥ 1, ≤ 1024 (matches S1-04 `AttemptNumber` bound).** Draft prose; pinned in AC-SCHEMA-RETRY-1 + parametrized rejection over `[0, -1, 1025, "3", 1.5]`.
15. **(consistency — harden) Module purity test (mirrors S1-02 / S1-03 / S1-04 / S1-05).** Every prior Step-1 story shipped a `test_*_purity.py` AST walker. Story now ships `tests/gates/test_catalog_loader_purity.py` (TYPE_CHECKING-aware) enforcing (a) `from __future__ import annotations` immediately after the module docstring, (b) alphabetized `__all__` containing exactly the public surface `{"CatalogEntry", "load", "load_all"}`, (c) module docstring cites ADR-0006 / ADR-0012 / ADR-0014 / ADR-0015 and the `lockfile_policy.py` precedent, (d) imports limited to stdlib + `jsonschema` + `pydantic` + `yaml` + `codegenie.{gates.contract, gates.errors, gates.logging, sandbox.contract, types.identifiers}`, (e) `yaml.load` (unsafe form) is absent — only `yaml.safe_load` allowed. AC-PURE-1..AC-PURE-4.
16. **(patterns — harden) Validator constructed ONCE at module import (`@functools.lru_cache(maxsize=1)`).** Mirrors `src/codegenie/schema/validator.py:_validator()`. Schema-read + Draft202012Validator construction is ~30 ms; per-call cost is unacceptable when `load_all` iterates N files. Pinned as AC-PERF-1 with identity test `_validator() is _validator()`.
17. **(consistency — harden) Two new `EVENT_GATE_CATALOG_*` constants appended to `gates/logging.py`.** S1-01 Validation note §6 explicitly permits later-story additions ("S2-01, S5-01, S6-02 ... add a row below the existing entries — they do not rename"). Added: `EVENT_GATE_CATALOG_LOADED = "gate.catalog.loaded"` (emitted by `load_all` on success), `EVENT_GATE_CATALOG_INVALID = "gate.catalog.invalid"` (emitted by `load` immediately before raising). The draft's event-emission was silent prose; promoted to AC-EVENT-1 / AC-EVENT-2 / AC-EVENT-3 with `caplog`-based tests.
18. **(consistency — nit) Coverage floor wording aligned.** Same conflation S1-02..S1-05 fixed: "line ≥ 95% AND branch ≥ 90%", not the draft's unqualified "tests pass." AC-GATE-5.

**No `RESCUE`-tier findings.** Every gap was patchable by adding ACs, tightening the TDD plan, reusing the existing `RetryPolicy` / `TransitionId` from `gates/contract.py`, and mirroring the established `LockfilePolicy.from_yaml` precedent for codegenie-owned trusted YAML.

**No Stage-3 research needed.** Every gap was answerable from Phase 5 arch + ADR-0006/-0012/-0014/-0015 + the five prior HARDENED reports (S1-01/S1-02/S1-03/S1-04/S1-05) + the codebase precedents in `src/codegenie/transforms/policy/lockfile_policy.py`, `src/codegenie/schema/validator.py`, `src/codegenie/skills/loader.py`, `src/codegenie/conventions/catalog.py`.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim, hardened):** Ship `src/codegenie/gates/catalog/_schema.json` (Draft 2020-12, `additionalProperties: false` at every object level, digest-shape regex on `base_image`), `src/codegenie/gates/catalog_loader.py` (single-file raise-on-error loader using `yaml.safe_load` per the `lockfile_policy` precedent, with a once-cached `Draft202012Validator`, `CatalogEntry` Pydantic model that reuses `RetryPolicy` and `TransitionId` from `gates/contract.py`), and an empty-but-schema-valid `stage6_validate.yaml` stub with a placeholder zeroed digest. The loader translates jsonschema and Pydantic validation errors into a single `GateCatalogInvalid` whose message names file path + YAML key path.
- **Non-goals (Out-of-scope, hardened):** Populating real `required_signals`/phases (S3-05); `stage6_validate_loose.yaml` (S3-05); `SandboxSpecBuilder.for_gate` translating `CatalogEntry` → `SandboxSpec` (S3-01); `StrictAndGate.from_yaml` (S4-05); catalog hot-reload; `sandbox-policy.yaml` digest pinning (S3-05, different file); tightening `sandbox.phases minItems` from 0 to 1 (S3-05 when real catalogs ship); extracting a shared `_yaml_with_schema` helper (note recorded for S3-05).

### Phase 5 exit criteria touched

- Step 1 done-criteria (High-level-impl.md §Step 1 bullets 5 + 6 + 7): `pytest tests/gates/test_catalog_schema.py tests/gates/test_catalog_loader.py tests/gates/test_catalog_loader_purity.py` green; `mypy --strict src/codegenie/gates/catalog_loader.py` clean.
- §Goal 6 (arch): "Gate logic is YAML data, not hardcoded — `gates/catalog/<gate_id>.yaml` defines required signals + retry policy + per-attempt sandbox overrides." This story is the schema + loader.
- §Component design — SandboxSpecBuilder (line 604-612): the YAML format and the `GateCatalogInvalid` raise semantics this story ships.
- §Edge case 13 (line 865): invalid YAML → `GateCatalogInvalid` → CLI exit 2 before any gate runs.
- §Open questions §4: one catalog stub here, S3-05 ships the second (`stage6_validate_loose.yaml`).

### Load-bearing commitments touched

- **ADR-0006** — Gate is ABC; loader produces structural payload (`CatalogEntry`), the eventual `StrictAndGate` instantiation lands in S4-05.
- **ADR-0012** — sandbox `env_allowlist` schema field is an array of strings; the loader does NOT resolve env values. Schema rejects any per-gate `env: {...}` block (illegal — only the allowlist is configurable here).
- **ADR-0014** — `CatalogEntry` (and all nested models) carry `extra="forbid", frozen=True`; the introspection walker `iter_nested_field_names` from `sandbox/signals/_introspection.py` (S1-03) is reused to assert no banned-substring field name slips in.
- **ADR-0015** — `retry_policy.non_retryable_failures` may include `trace`; the stub leaves the lists empty so the schema is exercised but no policy is implied.
- **CLAUDE.md "Match existing convention"** — `lockfile_policy.py` is the closest sibling (codegenie-owned trusted YAML, `yaml.safe_load` direct, `importlib.resources` for wheel-safe path, Pydantic round-trip). Module docstring cites the precedent.
- **CLAUDE.md "Extension by addition"** — Phase 7's `distroless_validate.yaml` is auto-discovered by `load_all`'s `*.yaml` glob + `_*.yaml` skip; zero edits to this story's files.
- **CLAUDE.md "Domain identifiers ... newtype when crossing ≥ 2 modules"** — `TransitionId` (S1-04) and `RetryPolicy` (S1-04) are reused, not re-declared. `gate_id` stays raw `str` (rule-of-three not yet cleared for a `GateId` newtype; the closed-Literal mirror `TransitionId` carries the typed-identity work).
- **CLAUDE.md "Functional core / imperative shell"** — `load` is impure (filesystem read + logger emission); the schema/Pydantic validation core is pure given a fixed YAML dict.
- **CLAUDE.md "Surface conflicts, don't average them"** — the `parsers.safe_yaml` (analyzed-repo chokepoint) vs `yaml.safe_load` (codegenie-owned trusted) tension is resolved explicitly with a module-docstring rationale paragraph mirroring `lockfile_policy.py`.

### Open ambiguities (resolved before Stage 2)

- **`yaml.safe_load` vs `parsers.safe_yaml`.** Resolution: `yaml.safe_load` directly, per the `lockfile_policy.py` precedent (codegenie-owned trusted YAML). Documented in the module docstring; pinned by AC-PURE-4 (`yaml.load` banned in AST).
- **`load(path)` module-function vs `CatalogEntry.from_yaml(path)` classmethod.** Resolution: module-function `load(path)` — parity with `codegenie.schema.validator.validate(...)` (the other JSON-Schema-backed loader). Both shapes are defensible; the module-function form is documented in AC-LOAD-1.
- **Single-file raise-on-error vs `Result[T, E]` discriminated union.** Resolution: raise-on-error. Arch §Edge case 13 explicitly wants `GateCatalogInvalid` → CLI exit 2 before any gate runs — fail-fast is the goal, not partial success.
- **`attempt_overrides[<n>]` value schema.** Resolution: relaxed copy of the `sandbox` block — `$defs/PartialSandboxBlock` shares `properties` with `$defs/SandboxBlock` but with empty `required`. Documented in §Schema design notes.

### Phase 1/3/5 prior art consulted

- [`src/codegenie/transforms/policy/lockfile_policy.py`](../../../../src/codegenie/transforms/policy/lockfile_policy.py) — Phase 3 S5-04 — closest sibling: codegenie-owned trusted YAML, `yaml.safe_load` direct, `importlib.resources` for wheel-safe path resolution, Pydantic-second round-trip. The pattern S1-06 mirrors.
- [`src/codegenie/schema/validator.py`](../../../../src/codegenie/schema/validator.py) — Phase 0 S3-02 — `@functools.lru_cache(maxsize=1)` Draft202012Validator construction; `err.json_path` (== `/`-joined absolute path) is the canonical operator-facing key path. AC-PERF-1 and AC-ERR-2 mirror this exactly.
- [`src/codegenie/skills/loader.py`](../../../../src/codegenie/skills/loader.py) — Phase 2 S2-01 — three-tier multi-file loader; NOT the shape S1-06 needs (S1-06 is single-file raise-on-error per arch §Edge case 13), but the `_*` skip pattern and the module-purity discipline (`__all__` exact, `from __future__ import annotations` first, closed import set) carry forward.
- [`src/codegenie/conventions/catalog.py`](../../../../src/codegenie/conventions/catalog.py) — Phase 2 S2-02 — `Catalog` Pydantic + `_apply_*` module-level helpers split (functional-core / imperative-shell). S1-06 follows the same shape: module-level `load`/`load_all` functions + private nested Pydantic models + `CatalogEntry` as the public payload.
- S1-01 HARDENED report — pins the 10-class sandbox error hierarchy (including `GateCatalogInvalid`) and the canonical event-name table; S1-06's two new `EVENT_GATE_CATALOG_*` constants append below the existing rows per the documented policy.
- S1-04 HARDENED report — pins `RetryPolicy` (with disjoint-cross-field `@model_validator`) and `TransitionId` (with closed member set). S1-06 *reuses* both rather than re-declaring; this is the load-bearing consistency check.
- S1-05 HARDENED report — establishes the registry-class-with-`.fresh()` pattern (not directly used here — catalogs are read-only data) AND the module-purity AST-walk fence pattern (directly carried forward).

## Critic findings (Stage 2)

### Critic A — Coverage

| Finding | Severity | Resolution |
|---|---|---|
| A-1 | block | `additionalProperties: false` enforced only at top level — nested levels (retry_policy, sandbox, phases[], attempt_overrides values) silently open | AC-SCHEMA-NESTED-1..AC-SCHEMA-NESTED-5 parametrized rejection at every nested object level |
| A-2 | block | Cross-field disjointness (retryable ⊥ non_retryable from S1-04 RetryPolicy) not enforced on catalog side | AC-XFIELD-1 + `test_disjoint_retryable_lists_enforced` |
| A-3 | block | Empty / non-mapping YAML produces opaque error, not GateCatalogInvalid | AC-IO-1..AC-IO-4 + parametrized `test_non_mapping_yaml_raises` |
| A-4 | harden | `base_image` not digest-shape-validated — S3-05's digest pinning has no structural floor | AC-SCHEMA-IMG-1 + regex `^[^\s]+@sha256:[0-9a-f]{64}$` + paired rejection test |
| A-5 | harden | `phases[].network` enum / `phases[].name` non-empty / `phases[].cmd minItems: 1` named in prose, not pinned | AC-SCHEMA-PHASE-1/-2 / AC-SCHEMA-CMD-1 + rejection tests |
| A-6 | harden | `retry_policy.max_attempts` integer ≥ 1 named in prose | AC-SCHEMA-RETRY-1 + parametrized rejection over `[0, -1, 1025, "3", 1.5]` |
| A-7 | harden | `attempt_overrides` key shape (`^[1-9][0-9]*$`) not constrained | AC-SCHEMA-NESTED-5 + parametrized rejection |
| A-8 | harden | `load_all` deterministic ordering not pinned | AC-LOADALL-2 + `test_load_all_sorted_by_filename` |
| A-9 | harden | `load_all` duplicate `gate_id` only in Refactor | AC-LOADALL-3 + `test_duplicate_gate_id_raises` |
| A-10 | harden | Error message contract (path + key path) only in Refactor | AC-ERR-1..AC-ERR-3 + `test_schema_error_message_names_key_path` |
| A-11 | harden | Two new `EVENT_GATE_CATALOG_*` constants for `caplog`-pinnable observability | AC-EVENT-1..AC-EVENT-3 |

### Critic B — Test Quality

| Finding | Severity | Resolution |
|---|---|---|
| B-1 | block | `test_load_all_skips_underscore_prefixed_files` passes for any mutation that special-cases `_schema.json` only — fixture has no other `_`-prefixed files | AC-SKIP-1..AC-SKIP-3 + `test_load_all_skips_arbitrary_underscore_files` with three different `_`-prefixed broken files |
| B-2 | block | `test_invalid_yaml_raises_gate_catalog_invalid` only asserts "bad.yaml in str(exc.value)" — doesn't pin the YAML key path AC implies | `test_schema_error_message_names_key_path` (AC-ERR-2) asserts both file path AND key path (`retry_policy/max_attempts`) appear |
| B-3 | block | No parametrized test for unknown nested key (`retry_policy.smuggle`, `sandbox.smuggle`, `phases[].smuggle`, `attempt_overrides.<n>.smuggle`) — mutation that omits nested `additionalProperties: false` passes | parametrized `test_schema_rejects_unknown_key_at_object_level` + `test_schema_rejects_unknown_key_inside_phase_entry` + `test_schema_rejects_unknown_key_inside_attempt_override` |
| B-4 | harden | `test_catalog_entry_is_frozen` — the Pydantic v2 API is `ValidationError`, not `TypeError`; need to also test `extra="forbid"` directly via `model_config` introspection | Parametrized `test_models_are_frozen_and_extra_forbid` (AC-MOD-1 / AC-MOD-4) over `[CatalogEntry, _SandboxBlock, _PhaseEntry, _AttemptOverride]` |
| B-5 | harden | No identity check for the cached validator | `test_validator_is_cached` (AC-PERF-1) — `_validator() is _validator()` |
| B-6 | harden | `caplog`-based event-emission tests missing | `test_load_all_emits_loaded_event` + `test_load_emits_invalid_event_on_error` (AC-EVENT-1/-2) |

### Critic C — Consistency

| Finding | Severity | Resolution |
|---|---|---|
| C-1 | block | `CatalogEntry.retry_policy: RetryPolicyEntry` silently forks the canonical `gates/contract.RetryPolicy` (S1-04) and loses the disjoint-cross-field invariant | AC-MOD-2 — type-hint identity check `typing.get_type_hints(CatalogEntry)['retry_policy'] is RetryPolicy` |
| C-2 | block | `transition` schema enum hardcoded — drift risk vs `gates/contract.TransitionId` member set | AC-ENUM-1 — sync test asserts `sorted(schema enum) == sorted(m.value for m in TransitionId)` |
| C-3 | block | `transition` field typed as raw `str` — re-runs `S1-04`'s closed-enum work | AC-MOD-3 — `typing.get_type_hints(CatalogEntry)['transition'] is TransitionId` |
| C-4 | harden | `yaml.safe_load` vs `parsers.safe_yaml` rationale not documented | AC-PURE-3 + AC-PURE-4 — module docstring cites `lockfile_policy.py` precedent; AST walk bans `yaml.load` |
| C-5 | harden | Module purity test (mirror S1-02/S1-03/S1-04/S1-05) missing | `tests/gates/test_catalog_loader_purity.py` + AC-PURE-1..AC-PURE-4 |
| C-6 | harden | Coverage floor wording aligned ("line ≥ 95% AND branch ≥ 90%" not "tests pass") | AC-GATE-5 |
| C-7 | harden | Two new event constants per S1-01 append-only policy | AC-EVENT-1..AC-EVENT-3 in `gates/logging.py` |

### Critic D — Design Patterns

| Finding | Severity | Resolution |
|---|---|---|
| D-1 | harden | `CatalogEntry.from_yaml` classmethod vs module-level `load` — sibling precedents go both ways (`LockfilePolicy.from_yaml` is classmethod; `codegenie.schema.validator.validate` is module function) | Chosen: module function, parity with `codegenie.schema.validator`. Documented in AC-LOAD-1. |
| D-2 | harden | Validator caching pattern (lru_cache singleton) implicit | AC-PERF-1 — `@functools.lru_cache(maxsize=1)` + identity test mirroring `schema/validator._validator` |
| D-3 | harden | `attempt_overrides[<n>]` partial-sandbox schema design not specified | §"Schema design notes" — `$defs/SandboxBlock` + `$defs/PartialSandboxBlock` (same properties, empty required) |
| D-4 | nit | Forward kernel-extract opportunity once S3-05's `sandbox-policy.yaml` ships its loader (third copy of jsonschema-first + Pydantic-second) | Recorded in Notes — NOT for S1-06 (rule-of-three not yet cleared for this exact shape); flagged for S3-05 evaluation |
| D-5 | nit | `_*.yaml` skip + auto-discovery is the canonical OCP seam for Phase 7's `distroless_validate.yaml` | Documented in Notes — extension-by-addition seam |

## Conflict resolution

- No real conflicts. Coverage A-1 (`additionalProperties: false` at every level) and Patterns D-3 (`$defs/PartialSandboxBlock` reuse) compose cleanly via shared `$defs`.
- Consistency C-1/C-2/C-3 (reuse `RetryPolicy` + `TransitionId`) and Patterns D-3 (relaxed-copy override schema) compose: the canonical Pydantic models gate the typed payload; the schema's relaxed `$defs/PartialSandboxBlock` gates the structural override shape.
- Test Quality B-1 (mutation-resistant `_*` skip fixture) is purely additive to the existing skip AC.

## Edits applied to the story

1. **Status** flipped from `Ready` to `HARDENED`.
2. **Depends on** widened from `S1-02, S1-04` to `S1-01, S1-02, S1-04, S1-05` (event constants from S1-01; `SignalKind` newtype + `signal_kind_registry` from S1-05; `RetryPolicy` + `TransitionId` from S1-04; `SandboxSpec` shape from S1-02).
3. **ADRs honored** widened from `ADR-0006, ADR-0014, ADR-0015` to add `ADR-0012` (static env allowlist).
4. **Validation notes** block appended directly under the story header documenting all 18 findings and resolutions with the verdict.
5. **Context** paragraph extended with the `yaml.safe_load` vs `parsers.safe_yaml` rationale paragraph (codegenie-owned trusted vs hostile analyzed-repo).
6. **References — where to look** extended with:
   - Phase ADRs section: added ADR-0012.
   - New "Prior validated stories carried forward" bullet (S1-01 / S1-04 / S1-05).
   - New "Codebase precedents" bullet (`lockfile_policy.py`, `schema/validator.py`).
7. **Goal** sentence rewritten to make explicit: digest-shape regex, canonical type reuse (`RetryPolicy` + `TransitionId`), once-cached validator, error-message contract.
8. **Acceptance criteria** rewritten from 9 prose bullets to ~50 individually-verifiable ACs organized into 17 lettered sections (A–Q): schema meta, top-level required, nested-`additionalProperties` parametrized, field shapes, `transition` enum sync, `CatalogEntry` model reuse, cross-field invariant inheritance, `load()` semantics, IO/parse error translation, error-message contract, `load_all()` semantics, `_*` skip mutation-resistance, stub digest shape + comment header, validator caching, module purity, event constants, quality gates.
9. **Schema design notes** new section added — explains the `$defs/SandboxBlock` + `$defs/PartialSandboxBlock` reuse for the `attempt_overrides` partial-override shape.
10. **Implementation outline** rewritten with explicit step-by-step ordering: schema first, stub second, loader third (with the IO type-check + jsonschema + Pydantic error-translation pipeline spelled out), event constants fourth, tests fifth.
11. **TDD plan** rewritten from 2 test files (~120 LOC sketch) to 3 test files (~480 LOC sketch) with:
    - parametrized nested-`additionalProperties` rejection (`test_schema_rejects_unknown_key_at_object_level` over `[[], ["retry_policy"], ["sandbox"]]` plus dedicated `phase` and `attempt_override` cases);
    - parametrized `attempt_overrides` key-pattern rejection (`["never", "", "0", "01", "1.5", "-1"]`);
    - parametrized non-mapping YAML rejection (`("", "NoneType")`, `("- a\n- b\n", "list")`, `("42\n", "int")`, `("just a string\n", "str")`);
    - parametrized `max_attempts` rejection over `[0, -1, 1025, "3", 1.5]`;
    - `test_disjoint_retryable_lists_enforced` (Pydantic cross-field roundtrip);
    - `test_transition_enum_byte_equal_to_TransitionId` (drift fence);
    - `test_schema_rejects_unpinned_base_image` + `test_schema_accepts_zero_placeholder_digest` (digest shape);
    - `test_validator_is_cached` (lru_cache identity);
    - `test_load_all_sorted_by_filename` + `test_duplicate_gate_id_raises` + `test_load_all_skips_arbitrary_underscore_files` (load_all semantics);
    - `caplog` event-emission tests for both new constants;
    - `tests/gates/test_catalog_loader_purity.py` mirroring S1-04/S1-05 AC-PURE with explicit `yaml.load` ban.
12. **Files to touch** expanded from 5 to 7 entries: added `tests/gates/test_catalog_loader_purity.py` (new) and `src/codegenie/gates/logging.py` (append two new EVENT_* constants).
13. **Out of scope** widened to explicitly defer: tightening `sandbox.phases minItems` to 1 (S3-05), extracting a shared `_yaml_with_schema` helper (note recorded for S3-05).
14. **Notes for the implementer** rewritten with:
    - the `yaml.safe_load` rationale + AST ban;
    - reuse-don't-redeclare warning citing the S1-04 validation report;
    - `additionalProperties: false` mutation-resistance reminder;
    - schema-first + Pydantic-second belt-and-suspenders rationale;
    - `$defs/SandboxBlock` + `$defs/PartialSandboxBlock` reuse note;
    - `importlib.resources` wheel-safety reminder;
    - lru_cache + cache_clear() reminder mirroring `schema/validator.py`;
    - error-message format consistency reminder;
    - Phase-7 distroless OCP-seam documentation;
    - future S3-05 kernel-extract candidate flag (NOT for S1-06);
    - coverage floor (line ≥ 95% AND branch ≥ 90%).

## Files written by this validation pass

- `docs/phases/05-sandbox-trust-gates/stories/S1-06-gate-catalog-schema-stub.md` (edited in place — `Status: HARDENED`, validation notes block + tightened ACs + 3-test-file TDD plan)
- `docs/phases/05-sandbox-trust-gates/stories/_validation/S1-06-gate-catalog-schema-stub.md` (this file)

## Verdict

**HARDENED** — Six block-tier weaknesses resolved by tightening ACs and adding mutation-resistant tests; no `RESCUE`-tier structural problems. Story is ready for `phase-story-executor`.
