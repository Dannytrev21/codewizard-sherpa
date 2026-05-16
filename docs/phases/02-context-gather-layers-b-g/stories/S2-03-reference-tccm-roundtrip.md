# Story S2-03 — Reference TCCM + roundtrip integration exercising every Protocol method

**Step:** Step 2 — Plant kernel-side loaders (`SkillsLoader`, `ConventionsCatalogLoader`) and reference TCCM
**Status:** Ready (HARDENED 2026-05-15)
**Effort:** S
**Depends on:** S1-04 (Done — `TCCMLoader`, `TCCM` model, 5-variant `DerivedQuery` discriminated union, `TCCMLoadError` marker), S1-05 (`SkillId` newtype — `required_skills` carries `list[SkillId]`). **Not** S2-01: the reference TCCM names `required_skills` as data only; `SkillsLoader.find_applicable(...)` is never invoked (Out of scope §5). The story is implementable today against the current `master`.
**ADRs honored:** 02-ADR-0007 (kernel-side scaffolding only; reference TCCM lives in `docs/`, **not** in `plugins/` — "documentation as code, deliberately outside the plugin namespace"), production ADR-0029 (Task-Class Context Manifests), production ADR-0030 (graph-aware context queries — five primitives), production ADR-0032 (Language Search Adapters — four `Protocol`s); closes **Gap 1** from `../phase-arch-design.md §"Gap analysis"` ("Adapter Protocol drift between Phase 2 and Phase 3" / "Protocols defined, never called in Phase 2")

## Validation notes (2026-05-15 — HARDENED)

The phase-story-validator identified **four block-tier defects** against the actually-shipped S1-04 modules (`src/codegenie/tccm/queries.py`, `loader.py`, `model.py`; `src/codegenie/result.py`; `src/codegenie/errors.py`) and rewrote the YAML, the `_expected_tccm()` constructors, and the failure-path assertions to match the source-of-truth shape. The original draft would have had every test red on `phase-story-executor`'s first attempt for non-design reasons (constructor errors, wrong API surface) — the executor would have burned attempts hunting parser bugs that don't exist.

**Block-tier corrections applied:**

1. **YAML `compute:` form rewritten to discriminator-form.** The original draft prescribed `compute: dep_graph.consumers_of("@codegenie/scip")` (an inline DSL). S1-04's `TCCMLoader` is a thin `safe_yaml.load → TCCM.model_validate` shim — there is **no DSL parser**. Each `DerivedQuery` variant is a Pydantic discriminated-union member with `compute: Literal[<primitive>]` + a single payload field (`pkg` / `module` / `symbol`) and `extra="forbid"`. The YAML now uses `compute: consumers_of` + `pkg: "@codegenie/scip"`. (Critic CO1 / T2 — block.)
2. **`name` and `max_files` dropped from variants and YAML.** The original draft constructed `ConsumersOf(name="who_consumes_scip_index", pkg=..., max_files=50)`. Neither `name` nor `max_files` is a field on any `DerivedQuery` variant in `queries.py`; `extra="forbid"` would raise on every constructor call. They have been removed everywhere. If a future story wants per-query naming or budgeting, that's an ADR amendment to the `DerivedQuery` model — out of scope here. (Critic CO3 / T1 — block.)
3. **`TCCMLoadError(reason=...)` corrected to positional `args[0]` prefix.** `errors.py` defines `TCCMLoadError` as a marker (no `__init__`, no `.reason` attribute). `loader.py` encodes the reason as a prefix in `args[0]` (e.g., `"unknown_query_primitive: <detail>"`). AC-7 now asserts `err.args[0].startswith("unknown_query_primitive:")`. (Critic CO7 / T3 — block.)
4. **`scip.refs` corrected to `refs_to`.** ADR-0030's author-facing primitive name is `scip.refs(symbol)`; the literal `compute` token shipped by S1-04 (per phase-arch §"Data model" line 721) is `refs_to`. Story prose now uses the literal token consistently and cites the alias once. (Critic CO2 — block.)

**Harden-tier strengthening applied:**

- **All three `AdapterConfidence` variants exercised** for `confidence_floor` round-trip (was: only `Degraded`). New AC-3b parametrizes `Trusted` / `Degraded(reason=...)` / `Unavailable(reason=...)` against three sibling fixtures under `_reference-tccm/_floors/`. (Critic C2.)
- **`frozen=True` / `extra="forbid"` invariants pinned** by AC-3c (mutation raises; extra top-level field raises). Arch §"Data model" requires both. (Critic C3.)
- **JSON round-trip identity per variant** pinned by AC-3d (`q == type(q).model_validate_json(q.model_dump_json())`). Catches discriminator-tag-name mismatches before Phase 3. (Critic C9.)
- **`_dispatch` Protocol-typed parameters** pinned by AC-4b — `dep: DepGraphAdapter`, `imp: ImportGraphAdapter`, etc. — so `mypy --strict` validates the call signatures against the Protocol surface, not the concrete mock. This is the actual Gap-1 closer for *signature* drift (mere "method called" tests don't catch a `consumers(self, pkg: str)` → `consumers(self, pkg: PackageId)` change). (Critic C1.)
- **`mypy --strict` scoped to `tests/integration/tccm/`** by AC-11b. (Critic C6.)
- **`pytest.raises(AssertionError)` only** for the `assert_never` test — the over-broad `(AssertionError, TypeError, ValueError)` umbrella would have hidden genuine dispatcher bugs. `typing.assert_never` deterministically raises `AssertionError` (Python 3.11+). (Critics C7 / T5 / CO9.)
- **Single-defect invalid fixture** — dropped extra `name` / `max_files` keys from `_invalid/unknown_compute.yaml` so the only Pydantic error is the unknown-discriminator one. Avoids accidental coupling to Pydantic v2's error-emission order. (Critic CO5.)
- **Multi-defect coverage spread to siblings under `_invalid/`** — three new fixtures (`bad_floor.yaml`, `missing_required_probes.yaml`, `extra_top_level_key.yaml`) parametrized in AC-7b, each pinning one row of the loader's `LoaderReason` taxonomy. (Critic C4.)
- **AC-1 reworded** to allow `README.md` alongside `tccm.yaml` and `_invalid/` (was: "only the reference TCCM and the `_invalid/` sibling"). (Critic C8.)
- **`MagicMock` import dropped** — never used in the prescribed code; would have failed `ruff check`. (Critic T7.)
- **`Trusted()` / `Degraded(reason=...)` / `Unavailable(reason=...)`** in mock `confidence()` returns — `kind` is defaulted, the redundant `kind=` kwarg suggests the author didn't read the model. (Critic T8.)
- **`Counter`-style multiset assertion** for AC-2 (was: set equality, which would silently accept a fixture with the right *set* of variants but the wrong *count*). (Critic T11.)

**Design-pattern strengthening applied (Notes for implementer §"Design patterns"):**

- **`_ProtocolMethod` StrEnum** introduced as the typed Protocol-method-name surface. Recorder and assertion both import the same enum; a typo (`"reverse_lookups"`) surfaces at import, not silently. The "fan of nine `assert called(...)` lines" is collapsed to one enum-iterating loop. The original story's Refactor §6 prohibition on a "central Protocol coverage map" was the right *spirit* (no production registry) but the wrong *form* — a typed enum **is** the Protocol surface (mirror of S1-04's `LoaderReason: TypeAlias = Literal[...]`), not a registry. The forcing-function discipline is preserved: a new Protocol method requires a new enum value, single-place edit, loud test failure on omission. (Critics DP2 / DP3.)
- **Coverage ratchet for the `match` arms** — AC-13 sister-test (`test_dispatcher_coverage_ratchet.py`) deletes one arm from a copy of `_dispatch` at runtime, runs `mypy --warn-unreachable` on the copy, asserts mypy reports the `assert_never` arm reachable. This is the production ADR-0030 §Consequences ratchet (same shape S1-04 already uses for `_classify`). Pins extension-by-addition: a sixth `DerivedQuery` variant cannot land green without a new `case` arm. (Critic DP1.)
- **Mock-class duplication is intentional** — the four `_Mock*` classes share an `__init__` + `confidence()` shape that violates three-strikes on its face. Rule 3 (Surgical Changes) wins here: these mocks are deleted when Phase 8's Bundle Builder ships real adapters; introducing a `_RecordingAdapter` mixin would couple the test fixtures to a micro-abstraction with one consumer. Notes-for-implementer flags it explicitly so a future contributor doesn't "fix" it. (Critic DP4.)
- **Newtype opportunity flagged for future ADR** — `pkg: str`, `module: str`, `symbol: str` on the Protocols are primitive-obsessed (production ADR-0033 §3); semantically distinct domains. S2-03 does **not** widen S1-03's Protocols (out of scope), but Notes-for-implementer records the opportunity for a Phase-3-entry amendment ADR. (Critic DP5.)

Twelve ACs original → **fifteen ACs** after hardening (AC-3b, AC-3c, AC-3d, AC-4b, AC-7b, AC-11b, AC-13 added; AC-1, AC-6 reworded). Implementation outline §1 / §2 / §4 rewritten. TDD-Red plan unchanged. Story is now ready for `phase-story-executor`.

Full critic reports + edit log: [`_validation/S2-03-reference-tccm-roundtrip.md`](_validation/S2-03-reference-tccm-roundtrip.md).

## Context

After S1-04 ships `TCCMLoader` and S2-01 ships `SkillsLoader`, Phase 2 still has a load-bearing hole: **the four adapter `Protocol`s** at `src/codegenie/adapters/protocols.py` (S1-03 — `DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`) are **typed but never invoked**. The arch's Gap 1 is explicit (`../phase-arch-design.md §"Gap analysis" §1`):

> The synthesis ships four `Protocol` classes with **zero implementations** in Phase 2; the only Phase-2-internal proof they're shaped correctly is the integration test loading the reference TCCM and dispatching to a mock. Phase 3's first adapter (`adapters/scip_node.py`, etc.) may discover the Protocol signature is wrong … Discovering it at Phase 3 land means amending a Phase 2 module, which ripples through `report/confidence_section.py` and any Phase 3 plugin code that was prototyped against the wrong shape.

This story closes Gap 1 by shipping **two artifacts together**:

1. **A reference TCCM under `docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml`** — an illustrative manifest for an `index-health-self-check` task class. Documentation as code, deliberately outside `plugins/` (the plugin namespace is Phase 3's per ADR-0031 §Consequences §1; this fixture is in `docs/` because shipping it under `tests/fixtures/plugins/` would imply pluggability Phase 3 owns — final-design §"Departures from all three inputs" §6). The TCCM exercises **every field** of the `TCCM` Pydantic model and **every variant** of the five-primitive `DerivedQuery` discriminated union (`ConsumersOf`, `ProducersOf`, `ReverseLookup`, `RefsTo`, `TestsExercising`).

2. **`tests/integration/tccm/test_reference_tccm_roundtrips.py`** — loads the reference TCCM via `TCCMLoader`; asserts the loaded model equals a hand-constructed Pydantic instance (field-for-field); and — closing Gap 1 — **dispatches each `DerivedQuery` variant to a mock adapter that implements the four Phase 2 `Protocol`s structurally**, asserting every Protocol method is invoked at least once. The mock dispatcher is the Phase-2-internal proof that the Protocol method signatures are shaped to receive the `DerivedQuery` variants they were designed for.

The mock dispatcher is **not** the Bundle Builder (Phase 8 owns that). It is a ~40-LOC pattern-matching `match query: case ConsumersOf(): dep_graph_adapter.consumers(...)` switch that lives inside the test file. Its purpose is to make "Protocol method called with `DerivedQuery` payload" type-checkable at PR review time. If Phase 3 discovers `consumers(self, pkg: str)` should have been `consumers(self, pkg: PackageId, *, transitively: bool = False)`, the amendment ADR points at this test file as the location where the drift was discovered. The "Phase-3 handoff trip-wire" (`tests/integration/adapters/test_phase3_handoff_smoke.py`, landed skipped in S7-04) is the cross-phase counterpart; this story is the in-Phase-2 proof.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #7` — the four adapter `Protocol` signatures (the mock dispatcher must call methods matching these signatures verbatim).
  - `../phase-arch-design.md §"Component design" #8` — `TCCMLoader.load(path) -> Result[TCCM, TCCMLoadError]`; five-variant `DerivedQuery`; `AdapterConfidence` placeholder.
  - `../phase-arch-design.md §"Gap analysis" Gap 1` — the gap this story closes; cross-references S7-04's Phase-3 handoff trip-wire.
  - `../phase-arch-design.md §"Data model"` — `TCCM` field list (`schema_version`, `task_class`, `required_probes`, `required_skills`, `derived_queries`, `confidence_floor`); `AdapterConfidence = Trusted | Degraded(reason) | Unavailable(reason)`.
  - `../phase-arch-design.md §"Scenarios" → Scenario 2` — `IndexHealthProbe` self-check is the conceptual fit for the reference TCCM's `task_class`.
- **Phase ADRs:**
  - `../ADRs/0007-no-plugin-loader-in-phase-2.md` — reference TCCM lives under `docs/`, not `plugins/`; the integration test loads from `docs/`.
- **Production ADRs:**
  - `../../production/adrs/0029-task-class-context-manifests.md` — TCCM schema; `required_probes`, `required_skills`, `derived_queries` semantics.
  - `../../production/adrs/0030-graph-aware-context-queries.md` — five-primitive `DerivedQuery` taxonomy. The literal `compute` tokens shipped by S1-04 (per phase-arch §"Data model" line 721) are `consumers_of`, `producers_of`, `reverse_lookup`, `refs_to`, `tests_exercising`. ADR-0030's author-facing alias for `refs_to` is `scip.refs(symbol)` — the alias is documentation; the literal token is the Pydantic discriminator.
  - `../../production/adrs/0032-language-search-adapters.md` — the four `Protocol`s and which queries each method serves.
- **Source design:**
  - `../final-design.md §"Components" #8` — Phase-2-internal consumer commitment for `TCCMLoader`; "reference TCCM under `docs/_reference-tccm/`, not `plugins/`" pattern decision.
  - `../final-design.md §"Departures from all three inputs" §6` — why `docs/` over `tests/fixtures/plugins/`.
  - `../final-design.md §"Risks and mitigations"` row "Adapter Protocol drift" — Gap 1 mitigation.
- **Existing code (Step 1 + S2-01):**
  - `src/codegenie/tccm/loader.py`, `model.py`, `queries.py` (S1-04) — `TCCMLoader.load`, `TCCM`, `DerivedQuery`.
  - `src/codegenie/adapters/protocols.py` (S1-03) — `DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter` `runtime_checkable` Protocols.
  - `src/codegenie/adapters/confidence.py` — `AdapterConfidence` discriminated union.
  - `src/codegenie/skills/__init__.py` (S2-01) — `Skill`, `SkillsLoader`; the reference TCCM's `required_skills` field names IDs that S2-01's loader would index.
- **Validation lineage:**
  - `_validation/S1-04-*.md` (if it lands) — confirms five-variant `DerivedQuery` shape this story relies on.

## Goal

Ship two artifacts that together close Gap 1:

1. **`docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml`** — a single illustrative TCCM for `task_class: index-health-self-check`. The manifest:
   - Sets `schema_version: "1"`.
   - Names `required_probes: [b2_index_health, b1_scip, b3_tree_sitter_imports]` (Phase-2 probe IDs).
   - Names `required_skills: [diagnose-stale-scip]` (illustrative — the SkillsLoader does not have to find an actual `SKILL.md` for this test; the field is data, not a resolution).
   - Sets `confidence_floor: {kind: degraded, reason: "stale_scip_acceptable_for_self_check"}`.
   - Includes **five `derived_queries` entries — one per `DerivedQuery` variant** (`ConsumersOf`, `ProducersOf`, `ReverseLookup`, `RefsTo`, `TestsExercising`) — each in S1-04's discriminator-form (`compute: <literal>` + payload field `pkg`/`module`/`symbol`; **no** `name` or `max_files` fields — neither exists on the variants and `extra="forbid"` rejects them).

2. **`tests/integration/tccm/test_reference_tccm_roundtrips.py`** — six named tests:
   - **`test_reference_tccm_loads_and_equals_expected_pydantic_instance`** — `TCCMLoader().load(REFERENCE_PATH)` returns an `Ok(value=tccm)` (from `codegenie.result`; `Ok`/`Err` are exported at module top-level — there is **no** `Result.Ok` namespacing); `tccm == _expected_tccm()` where `_expected_tccm()` constructs the TCCM by hand from the canonical Pydantic constructors. Pins the YAML-to-Pydantic deserialization shape end-to-end.
   - **`test_reference_tccm_exercises_every_derived_query_variant`** — exactly one entry per variant in `tccm.derived_queries`; the five-element set of `type(q).__name__` over `tccm.derived_queries` equals `{"ConsumersOf", "ProducersOf", "ReverseLookup", "RefsTo", "TestsExercising"}`. Pins the "exercises every variant" commitment.
   - **`test_mock_dispatcher_invokes_every_protocol_method_at_least_once`** — the load-bearing AC. A `_MockDispatcher` defines four mock adapters that structurally satisfy the four `Protocol`s (`isinstance(mock_dep, DepGraphAdapter)` is True under `runtime_checkable`). The dispatcher routes each `DerivedQuery` to the appropriate Protocol method; a call-recorder asserts that **every method on every Protocol is invoked at least once** across the five queries. Specifically:
     - `ConsumersOf` → `DepGraphAdapter.consumers(...)`
     - `ProducersOf` → `DepGraphAdapter.producers(...)`
     - `ReverseLookup` → `ImportGraphAdapter.reverse_lookup(...)`
     - `RefsTo` → `ScipAdapter.refs(...)`
     - `TestsExercising` → `TestInventoryAdapter.tests_exercising(...)`
     - All four `*.confidence()` methods are called once at the dispatcher boundary (single-batch confidence reporting); this picks up the `Protocol.confidence()` method from all four.
   - **`test_dispatcher_match_is_exhaustive_assert_never_fires_on_smuggled_variant`** — runtime smoke: a hand-constructed `object()` with a `kind` attribute the discriminator does not recognize triggers the dispatcher's `case _ as unreachable: assert_never(unreachable)` branch. Pins ADR-0033 §4.
   - **`test_unknown_compute_primitive_returns_typed_err_prefix`** — a sibling fixture (`_reference-tccm/_invalid/unknown_compute.yaml`) with `compute: graph_explode` round-trips through `TCCMLoader` and yields `Err(error=TCCMLoadError(...))` whose `error.args[0]` starts with `"unknown_query_primitive:"`. The `TCCMLoadError` marker has **no** `.reason` attribute (per `errors.py` + `loader.py` docstring); the reason is encoded as the positional `args[0]` prefix. Pins S1-04's failure-path contract from the perspective of a real on-disk fixture.
   - **`test_reference_tccm_lives_under_docs_not_under_plugins`** — directory-discipline guard: the resolved path of `REFERENCE_PATH` starts with `<repo_root>/docs/`, and `<repo_root>/plugins/` either does not exist or contains zero `tccm.yaml` files. If a future contributor moves the fixture to `tests/fixtures/plugins/`, this test fails — closes the boundary 02-ADR-0007 sets.

## Acceptance criteria

- [ ] **AC-1 — reference TCCM exists at the canonical path.** `docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml` exists; the directory holds exactly `tccm.yaml`, `README.md`, the `_invalid/` sibling subdirectory (AC-7, AC-7b), and the `_floors/` sibling subdirectory (AC-3b). No other files. Pinned by `test_reference_tccm_lives_under_docs_not_under_plugins` (path + walk assertion).
- [ ] **AC-2 — five `derived_queries` entries, one per variant.** The fixture YAML's `derived_queries` list has exactly five entries (`len(tccm.derived_queries) == 5`); after `TCCMLoader().load`, `Counter(type(q).__name__ for q in tccm.derived_queries)` equals `Counter({"ConsumersOf": 1, "ProducersOf": 1, "ReverseLookup": 1, "RefsTo": 1, "TestsExercising": 1})` (multiset equality — no duplicates, no omissions, no over-counts). Pinned by `test_reference_tccm_exercises_every_derived_query_variant`.
- [ ] **AC-3 — round-trip equality.** `TCCMLoader().load(REFERENCE_PATH)` returns an `Ok(value=tccm)` (`from codegenie.result import Ok`) and `tccm == _expected_tccm()`, where `_expected_tccm()` is a hand-constructed `TCCM(...)` using the **actual** Pydantic constructors from `src/codegenie/tccm/{model,queries}.py` and `src/codegenie/adapters/confidence.py`. Asserts equality on every field (`schema_version`, `task_class`, `required_probes`, `required_skills`, `derived_queries`, `confidence_floor`). The variant constructors carry **only** `compute` (defaulted Literal) + one payload field (`pkg`/`module`/`symbol`); no `name`, no `max_files` (those fields do not exist; `extra="forbid"` would reject them). Pinned by `test_reference_tccm_loads_and_equals_expected_pydantic_instance`.
- [ ] **AC-3b — every `AdapterConfidence` variant round-trips through `confidence_floor`.** Three sibling fixtures under `_reference-tccm/_floors/` (`trusted.yaml`, `degraded.yaml`, `unavailable.yaml`) — each a minimal TCCM identical to the reference except for `confidence_floor`. Parametrized test asserts `TCCMLoader().load(p).unwrap().confidence_floor` is the expected `Trusted()` / `Degraded(reason=...)` / `Unavailable(reason=...)` instance. Without this, an S1-04 discriminator-handling bug on `Unavailable` would ship uncaught (the canonical reference TCCM exercises only `Degraded`). Pinned by `test_confidence_floor_round_trips_for_every_variant`.
- [ ] **AC-3c — `frozen=True` and `extra="forbid"` invariants enforced on the loaded `TCCM`.** Two assertions: (a) attempting `tccm.task_class = "x"` raises `ValidationError` (Pydantic v2 `frozen` semantics); (b) loading a fixture (`_invalid/extra_top_level_key.yaml`) with an unknown top-level key (`unexpected_field: 1`) returns `Err(error=TCCMLoadError(...))` whose `args[0]` starts with `"schema:"`. Pins arch §"Data model" requirements explicitly. Pinned by `test_loaded_tccm_is_frozen_and_forbids_extras`.
- [ ] **AC-3d — JSON round-trip identity per variant.** For each `q` in `tccm.derived_queries`: `q == type(q).model_validate_json(q.model_dump_json())`. Catches discriminator-tag-name drift and any custom-validator regressions before Phase 3 plugins serialize/deserialize across IPC. Pinned by `test_every_derived_query_round_trips_through_json`.
- [ ] **AC-4 — every Protocol method invoked.** The mock dispatcher's call recorder reports at least one invocation for each of the nine Protocol methods enumerated by the in-test `_ProtocolMethod(StrEnum)` (see Implementation outline §4): `DepGraphAdapter.{consumers, producers, confidence}`, `ImportGraphAdapter.{reverse_lookup, confidence}`, `ScipAdapter.{refs, confidence}`, `TestInventoryAdapter.{tests_exercising, confidence}`. Asserted by iterating the enum, **not** by nine independent string-literal `assert called(...)` calls (DP3 — typo discipline). Adding a Protocol method requires a new enum value (single-place edit); the test fails loudly on omission. **This is the Gap 1 closer for *invocation*.** Pinned by `test_mock_dispatcher_invokes_every_protocol_method_at_least_once`.
- [ ] **AC-4b — `_dispatch` parameters are typed against the `Protocol`s, not the concrete mocks.** The `_dispatch` signature is `def _dispatch(query: DerivedQuery, *, dep: DepGraphAdapter, imp: ImportGraphAdapter, scip: ScipAdapter, tests: TestInventoryAdapter) -> None`. Under `mypy --strict tests/integration/tccm/`, the call sites inside `_dispatch` (`dep.consumers(p)`, etc.) are checked against the **Protocol** signatures, not the mocks' duck-typed methods. **This is the Gap 1 closer for *signature drift*** — a future change of `consumers(self, pkg: str)` to `consumers(self, pkg: PackageId, *, transitively: bool = False)` on the Protocol would break this file at type-check, surfacing the drift in this story's test (the in-Phase-2 anchor) the way Gap 1 promises. Pinned by AC-11b.
- [ ] **AC-5 — mocks structurally satisfy the Protocols.** `isinstance(mock_dep, DepGraphAdapter)`, `isinstance(mock_import, ImportGraphAdapter)`, `isinstance(mock_scip, ScipAdapter)`, `isinstance(mock_test, TestInventoryAdapter)` are all `True` (relying on `@runtime_checkable`). Pins that the mocks aren't faking the conformance.
- [ ] **AC-6 — exhaustive `match` discipline.** The dispatcher's `match query: case ...: ... case _ as unreachable: assert_never(unreachable)` branch fires when a hand-constructed imposter object is passed; the test asserts `pytest.raises(AssertionError)` exactly (Python 3.11+ `typing.assert_never` raises `AssertionError` deterministically — the previous draft's `(AssertionError, TypeError, ValueError)` umbrella was over-defensive and would have hidden genuine dispatcher bugs that swallowed exceptions or returned `None`). Pinned by `test_dispatcher_match_is_exhaustive_assert_never_fires_on_smuggled_variant`.
- [ ] **AC-7 — invalid-fixture path returns typed `Err` with `unknown_query_primitive:` prefix.** `_reference-tccm/_invalid/unknown_compute.yaml` (which contains a single `derived_queries` entry with `compute: graph_explode` + `pkg: "@x"` — single-defect fixture, no extra fields) loads via `TCCMLoader().load(...)` to `Err(error=TCCMLoadError(...))`; `result.unwrap_err().args[0].startswith("unknown_query_primitive:")` is `True`. The `TCCMLoadError` marker carries no `.reason` attribute (`errors.py` + `loader.py` docstring) — the test reads the prefix off `args[0]`, not `err.reason`. Pins the S1-04 failure-path contract under realistic on-disk input.
- [ ] **AC-7b — `LoaderReason` taxonomy covered by sibling invalid fixtures.** Three additional fixtures parametrize the loader's three-row `LoaderReason` taxonomy (`parse | schema | unknown_query_primitive`):
  - `_invalid/malformed.yaml` — invalid YAML bytes (`[unclosed`) → `args[0].startswith("parse:")`.
  - `_invalid/missing_required_probes.yaml` — well-formed YAML missing the `required_probes` field → `args[0].startswith("schema:")`.
  - `_invalid/extra_top_level_key.yaml` — well-formed YAML with `unexpected_field: 1` at top-level → `args[0].startswith("schema:")` (covered by AC-3c too — single fixture, two consumers).
  Each loaded fixture's `Err.error` is an instance of `TCCMLoadError`. Pinned by `test_invalid_fixtures_cover_loader_reason_taxonomy`.
- [ ] **AC-8 — directory discipline (02-ADR-0007).** The reference TCCM's resolved path is rooted at `<repo_root>/docs/`. A walk of `<repo_root>/plugins/` (if it exists) finds **zero** files named `tccm.yaml`. Pinned by `test_reference_tccm_lives_under_docs_not_under_plugins`. This guards the Phase-2/Phase-3 directory boundary.
- [ ] **AC-9 — fixture is `safe_yaml.load`-parseable independent of `TCCMLoader`.** Smoke-check that the on-disk reference fixture is well-formed at the parser-layer too: `safe_yaml.load(REFERENCE_PATH, max_bytes=64 << 10)` returns a `dict` with `data["schema_version"] == "1"`. Not a parser-layer test (S1-04 owns those); a fixture-validity smoke. Asserted in one-line sanity test.
- [ ] **AC-10 — README under `_reference-tccm/`.** A `_reference-tccm/README.md` (one paragraph) explains (a) why this directory lives under `docs/`, not `plugins/`; (b) which Phase 2 test consumes it; (c) cross-links to 02-ADR-0007 + Gap 1 in the arch design. Future contributors must not delete or move this fixture casually.
- [ ] **AC-11 — toolchain.** `ruff check`, `ruff format --check`, `mypy --strict`, `mypy --warn-unreachable` clean. `pytest tests/integration/tccm/` passes.
- [ ] **AC-11b — `mypy --strict` on the test directory.** `mypy --strict tests/integration/tccm/` exits zero. The test file's `_dispatch` is annotated with Protocol-typed parameters (per AC-4b); no `Any`, no unparameterized generics, no untyped `dict`. This is what makes AC-4b load-bearing: without `mypy --strict` on the test file, the Protocol-typed signature is just a comment.
- [ ] **AC-12 — TDD discipline.** Red tests committed failing (because the fixture YAML and the mock dispatcher do not yet exist); green commit makes them pass; refactor commit is no-op behavior. Validator can reproduce.
- [ ] **AC-13 — coverage ratchet for the `match` arms.** A sibling integration test `tests/integration/tccm/test_dispatcher_coverage_ratchet.py` writes a synthetic copy of the `_dispatch` function (under `tests/integration/tccm/_ratchet_fixtures/`) with one `case` arm intentionally removed, runs `mypy --warn-unreachable` against it via `subprocess`, and asserts mypy reports the `assert_never` arm reachable (i.e., the `error` count includes a hit on the deleted arm's coverage). This is the **production ADR-0030 §Consequences ratchet** — mirrors the discipline S1-04's `_classify` function uses. A sixth `DerivedQuery` variant (added under an ADR amendment) cannot land green without a corresponding `case` arm. Pinned by `test_dispatcher_match_arms_are_under_mypy_warn_unreachable_ratchet`.

## Implementation outline

1. **Author the reference TCCM** at `docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml`. Each `derived_queries` entry uses the Pydantic discriminator-form: `compute: <literal>` + a single payload field (`pkg` / `module` / `symbol`). **No `name`, no `max_files`** — neither field exists on any variant in `src/codegenie/tccm/queries.py` and `extra="forbid"` rejects them. Verify the literal `compute` tokens against `queries.py` before writing the file:
   ```yaml
   schema_version: "1"
   task_class: index-health-self-check
   required_probes:
     - b2_index_health
     - b1_scip
     - b3_tree_sitter_imports
   required_skills:
     - diagnose-stale-scip
   confidence_floor:
     kind: degraded
     reason: stale_scip_acceptable_for_self_check
   derived_queries:
     - compute: consumers_of
       pkg: "@codegenie/scip"
     - compute: producers_of
       pkg: "@codegenie/scip"
     - compute: reverse_lookup
       module: "codegenie/probes/layer_b/index_health.py"
     - compute: refs_to
       symbol: "codegenie/indices/freshness.IndexFreshness"
     - compute: tests_exercising
       symbol: "codegenie/probes/layer_b/index_health.py"
   ```
   The five literal `compute` tokens are owned by S1-04's `queries.py` (`consumers_of` / `producers_of` / `reverse_lookup` / `refs_to` / `tests_exercising`). If a future amendment renames any token, this fixture and `_expected_tccm()` move together.
2. **Author the invalid fixtures** under `docs/phases/02-context-gather-layers-b-g/_reference-tccm/_invalid/`. Each is a **single-defect** fixture (avoids accidental coupling to Pydantic v2's error-emission order):
   ```yaml
   # _invalid/unknown_compute.yaml — AC-7 (unknown_query_primitive: prefix)
   schema_version: "1"
   task_class: index-health-self-check
   required_probes: [b2_index_health]
   required_skills: []
   confidence_floor: {kind: trusted}
   derived_queries:
     - compute: graph_explode
       pkg: "@codegenie/scip"
   ```
   ```yaml
   # _invalid/malformed.yaml — AC-7b (parse: prefix)
   [unclosed: bracket
   ```
   ```yaml
   # _invalid/missing_required_probes.yaml — AC-7b (schema: prefix)
   schema_version: "1"
   task_class: index-health-self-check
   required_skills: []
   confidence_floor: {kind: trusted}
   derived_queries: []
   ```
   ```yaml
   # _invalid/extra_top_level_key.yaml — AC-3c + AC-7b (schema: prefix)
   schema_version: "1"
   task_class: index-health-self-check
   required_probes: []
   required_skills: []
   confidence_floor: {kind: trusted}
   derived_queries: []
   unexpected_field: 1
   ```
   And the three `_floors/` fixtures (AC-3b) — each identical to the reference TCCM except for the `confidence_floor` block:
   ```yaml
   # _floors/trusted.yaml
   confidence_floor: {kind: trusted}
   ```
   ```yaml
   # _floors/degraded.yaml
   confidence_floor: {kind: degraded, reason: "self_check_acceptable"}
   ```
   ```yaml
   # _floors/unavailable.yaml
   confidence_floor: {kind: unavailable, reason: "scip_offline"}
   ```
3. **Author `_reference-tccm/README.md`** — one paragraph per AC-10.
4. **Test file** `tests/integration/tccm/__init__.py` (empty) and `tests/integration/tccm/test_reference_tccm_roundtrips.py`. The `_ProtocolMethod(StrEnum)` is the typed surface of the nine Protocol methods; recorder + assertions both consume it (DP2/DP3). `_dispatch`'s parameters are typed against the **Protocols**, not the mocks (AC-4b). All `Trusted` / `Degraded` / `Unavailable` constructors omit the redundant `kind=` kwarg (the field has a default):
   ```python
   # tests/integration/tccm/test_reference_tccm_roundtrips.py
   from __future__ import annotations

   from enum import StrEnum
   from pathlib import Path
   from typing import assert_never

   import pytest
   from pydantic import ValidationError

   from codegenie.adapters.confidence import (
       AdapterConfidence, Degraded, Trusted, Unavailable,
   )
   from codegenie.adapters.protocols import (
       DepGraphAdapter, ImportGraphAdapter, ScipAdapter, TestInventoryAdapter,
       Occurrence, TestId,
   )
   from codegenie.errors import TCCMLoadError
   from codegenie.parsers import safe_yaml
   from codegenie.result import Ok
   from codegenie.tccm.loader import TCCMLoader
   from codegenie.tccm.model import TCCM
   from codegenie.tccm.queries import (
       ConsumersOf, DerivedQuery, ProducersOf, ReverseLookup, RefsTo, TestsExercising,
   )
   from codegenie.types.identifiers import ProbeId, SkillId, TaskClassId

   REPO_ROOT = Path(__file__).resolve().parents[3]
   REFERENCE_PATH = REPO_ROOT / "docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml"
   INVALID_DIR = REFERENCE_PATH.parent / "_invalid"
   FLOORS_DIR = REFERENCE_PATH.parent / "_floors"


   class _ProtocolMethod(StrEnum):
       """Typed enumeration of the nine Phase-2 Protocol methods. Recorder
       and assertions both consume this — typo discipline (DP2/DP3). Adding
       a Protocol method adds an enum value; the test then auto-asserts it."""
       DEP_CONSUMERS = "DepGraphAdapter.consumers"
       DEP_PRODUCERS = "DepGraphAdapter.producers"
       DEP_CONFIDENCE = "DepGraphAdapter.confidence"
       IMP_REVERSE_LOOKUP = "ImportGraphAdapter.reverse_lookup"
       IMP_CONFIDENCE = "ImportGraphAdapter.confidence"
       SCIP_REFS = "ScipAdapter.refs"
       SCIP_CONFIDENCE = "ScipAdapter.confidence"
       TESTS_EXERCISING = "TestInventoryAdapter.tests_exercising"
       TESTS_CONFIDENCE = "TestInventoryAdapter.confidence"


   # ---- Mocks that structurally satisfy the four Protocols --------------------
   # Duplication across the four mocks is intentional: these are deleted when
   # Phase 8 ships real adapters. Do NOT pull a `_RecordingAdapter` mixin (DP4).

   class _MockDepGraph:
       def __init__(self) -> None:
           self.calls: list[_ProtocolMethod] = []
       def consumers(self, pkg: str) -> list[str]:
           self.calls.append(_ProtocolMethod.DEP_CONSUMERS); return ["a", "b"]
       def producers(self, pkg: str) -> list[str]:
           self.calls.append(_ProtocolMethod.DEP_PRODUCERS); return ["c"]
       def confidence(self) -> AdapterConfidence:
           self.calls.append(_ProtocolMethod.DEP_CONFIDENCE); return Trusted()

   class _MockImportGraph:
       def __init__(self) -> None:
           self.calls: list[_ProtocolMethod] = []
       def reverse_lookup(self, module: str) -> list[str]:
           self.calls.append(_ProtocolMethod.IMP_REVERSE_LOOKUP); return ["x.py"]
       def confidence(self) -> AdapterConfidence:
           self.calls.append(_ProtocolMethod.IMP_CONFIDENCE); return Trusted()

   class _MockScip:
       def __init__(self) -> None:
           self.calls: list[_ProtocolMethod] = []
       def refs(self, symbol: str) -> list[Occurrence]:
           self.calls.append(_ProtocolMethod.SCIP_REFS); return []
       def confidence(self) -> AdapterConfidence:
           self.calls.append(_ProtocolMethod.SCIP_CONFIDENCE)
           return Degraded(reason="self_check")

   class _MockTestInventory:
       def __init__(self) -> None:
           self.calls: list[_ProtocolMethod] = []
       def tests_exercising(self, symbol: str) -> list[TestId]:
           self.calls.append(_ProtocolMethod.TESTS_EXERCISING); return []
       def confidence(self) -> AdapterConfidence:
           self.calls.append(_ProtocolMethod.TESTS_CONFIDENCE); return Trusted()


   def _dispatch(
       query: DerivedQuery,
       *,
       dep: DepGraphAdapter,
       imp: ImportGraphAdapter,
       scip: ScipAdapter,
       tests: TestInventoryAdapter,
   ) -> None:
       """Route a DerivedQuery to the appropriate Protocol method.
       Parameter types are the *Protocols*, not the concrete mocks: under
       `mypy --strict` the calls below are checked against the Protocol
       signatures — that's the in-Phase-2 anchor for Gap-1 signature drift
       (AC-4b). `assert_never` on unreachable is the exhaustiveness guard
       (AC-6); production ADR-0030 §Consequences ratchet (AC-13)."""
       match query:
           case ConsumersOf(pkg=p):        dep.consumers(p)
           case ProducersOf(pkg=p):        dep.producers(p)
           case ReverseLookup(module=m):   imp.reverse_lookup(m)
           case RefsTo(symbol=s):          scip.refs(s)
           case TestsExercising(symbol=s): tests.tests_exercising(s)
           case _ as unreachable:
               assert_never(unreachable)


   # ---- AC-1, AC-8 (location discipline) --------------------------------------

   def test_reference_tccm_lives_under_docs_not_under_plugins() -> None:
       assert REFERENCE_PATH.exists(), f"missing fixture: {REFERENCE_PATH}"
       assert str(REFERENCE_PATH).startswith(str(REPO_ROOT / "docs"))
       plugins_root = REPO_ROOT / "plugins"
       if plugins_root.exists():
           stray = list(plugins_root.rglob("tccm.yaml"))
           assert stray == [], (
               "02-ADR-0007 violation: reference TCCMs MUST live under docs/, "
               f"not plugins/. Found: {stray}"
           )


   # ---- AC-9 (fixture-validity smoke) -----------------------------------------

   def test_reference_tccm_is_safe_yaml_parseable() -> None:
       data = safe_yaml.load(REFERENCE_PATH, max_bytes=64 << 10)
       assert isinstance(data, dict)
       assert data["schema_version"] == "1"


   # ---- AC-3 (round-trip equality) --------------------------------------------

   def _expected_tccm() -> TCCM:
       return TCCM(
           schema_version="1",
           task_class=TaskClassId("index-health-self-check"),
           required_probes=[ProbeId("b2_index_health"),
                            ProbeId("b1_scip"),
                            ProbeId("b3_tree_sitter_imports")],
           required_skills=[SkillId("diagnose-stale-scip")],
           confidence_floor=Degraded(reason="stale_scip_acceptable_for_self_check"),
           derived_queries=[
               ConsumersOf(pkg="@codegenie/scip"),
               ProducersOf(pkg="@codegenie/scip"),
               ReverseLookup(module="codegenie/probes/layer_b/index_health.py"),
               RefsTo(symbol="codegenie/indices/freshness.IndexFreshness"),
               TestsExercising(symbol="codegenie/probes/layer_b/index_health.py"),
           ],
       )

   def test_reference_tccm_loads_and_equals_expected_pydantic_instance() -> None:
       result = TCCMLoader().load(REFERENCE_PATH)
       assert result.is_ok(), f"TCCMLoader failed: {result}"
       assert isinstance(result, Ok)
       assert result.unwrap() == _expected_tccm()


   # ---- AC-2 (Counter-style multiset) -----------------------------------------

   def test_reference_tccm_exercises_every_derived_query_variant() -> None:
       from collections import Counter
       tccm = TCCMLoader().load(REFERENCE_PATH).unwrap()
       assert len(tccm.derived_queries) == 5
       counts = Counter(type(q).__name__ for q in tccm.derived_queries)
       assert counts == Counter({
           "ConsumersOf": 1, "ProducersOf": 1, "ReverseLookup": 1,
           "RefsTo": 1, "TestsExercising": 1,
       })


   # ---- AC-3b (every confidence_floor variant round-trips) --------------------

   @pytest.mark.parametrize(("filename", "expected"), [
       ("trusted.yaml",     Trusted()),
       ("degraded.yaml",    Degraded(reason="self_check_acceptable")),
       ("unavailable.yaml", Unavailable(reason="scip_offline")),
   ])
   def test_confidence_floor_round_trips_for_every_variant(
       filename: str, expected: AdapterConfidence,
   ) -> None:
       result = TCCMLoader().load(FLOORS_DIR / filename)
       assert result.is_ok(), f"{filename}: {result}"
       assert result.unwrap().confidence_floor == expected


   # ---- AC-3c (frozen + extra=forbid) -----------------------------------------

   def test_loaded_tccm_is_frozen_and_forbids_extras() -> None:
       tccm = TCCMLoader().load(REFERENCE_PATH).unwrap()
       with pytest.raises(ValidationError):
           tccm.task_class = "x"  # type: ignore[misc]
       result = TCCMLoader().load(INVALID_DIR / "extra_top_level_key.yaml")
       assert result.is_err()
       assert result.unwrap_err().args[0].startswith("schema:")


   # ---- AC-3d (per-variant JSON round-trip) -----------------------------------

   def test_every_derived_query_round_trips_through_json() -> None:
       tccm = TCCMLoader().load(REFERENCE_PATH).unwrap()
       for q in tccm.derived_queries:
           same = type(q).model_validate_json(q.model_dump_json())
           assert q == same, f"JSON round-trip drift on {type(q).__name__}"


   # ---- AC-4, AC-5 (Gap 1 closer — invocation) --------------------------------

   def test_mock_dispatcher_invokes_every_protocol_method_at_least_once() -> None:
       tccm = TCCMLoader().load(REFERENCE_PATH).unwrap()
       dep, imp, scip, tests = (
           _MockDepGraph(), _MockImportGraph(), _MockScip(), _MockTestInventory(),
       )

       # AC-5 — structural Protocol conformance.
       assert isinstance(dep, DepGraphAdapter)
       assert isinstance(imp, ImportGraphAdapter)
       assert isinstance(scip, ScipAdapter)
       assert isinstance(tests, TestInventoryAdapter)

       for query in tccm.derived_queries:
           _dispatch(query, dep=dep, imp=imp, scip=scip, tests=tests)
       for adapter in (dep, imp, scip, tests):
           adapter.confidence()

       all_calls: set[_ProtocolMethod] = (
           set(dep.calls) | set(imp.calls) | set(scip.calls) | set(tests.calls)
       )
       missing = set(_ProtocolMethod) - all_calls
       assert not missing, f"never invoked: {sorted(m.value for m in missing)}"


   # ---- AC-6 (assert_never fires on imposter — narrow exception) --------------

   def test_dispatcher_match_is_exhaustive_assert_never_fires_on_smuggled_variant() -> None:
       # `match` matches ConsumersOf/etc. by class identity. An arbitrary
       # object falls cleanly through to `case _ as unreachable`.
       class _Imposter:
           pass
       with pytest.raises(AssertionError):
           _dispatch(
               _Imposter(),  # type: ignore[arg-type]
               dep=_MockDepGraph(), imp=_MockImportGraph(),
               scip=_MockScip(), tests=_MockTestInventory(),
           )


   # ---- AC-7 (unknown_query_primitive: prefix on args[0]) ---------------------

   def test_unknown_compute_primitive_returns_typed_err_prefix() -> None:
       result = TCCMLoader().load(INVALID_DIR / "unknown_compute.yaml")
       assert result.is_err(), f"expected Err, got {result}"
       err = result.unwrap_err()
       assert isinstance(err, TCCMLoadError)
       # TCCMLoadError is a marker — no .reason attribute. Reason lives in
       # args[0] as a prefix (errors.py + loader.py docstring).
       assert err.args[0].startswith("unknown_query_primitive:"), err.args


   # ---- AC-7b (LoaderReason taxonomy via sibling fixtures) --------------------

   @pytest.mark.parametrize(("filename", "expected_prefix"), [
       ("malformed.yaml",                "parse:"),
       ("missing_required_probes.yaml",  "schema:"),
       ("extra_top_level_key.yaml",      "schema:"),
       ("unknown_compute.yaml",          "unknown_query_primitive:"),
   ])
   def test_invalid_fixtures_cover_loader_reason_taxonomy(
       filename: str, expected_prefix: str,
   ) -> None:
       result = TCCMLoader().load(INVALID_DIR / filename)
       assert result.is_err(), f"{filename}: expected Err, got {result}"
       err = result.unwrap_err()
       assert isinstance(err, TCCMLoadError)
       assert err.args[0].startswith(expected_prefix), \
           f"{filename}: expected '{expected_prefix}…' got '{err.args[0]}'"
   ```

   The AC-13 ratchet test lives in a sibling file `tests/integration/tccm/test_dispatcher_coverage_ratchet.py` to keep this file focused on the round-trip story. It writes a copy of `_dispatch` with one `case` arm removed to a tmp file under `_ratchet_fixtures/`, runs `mypy --warn-unreachable` via `subprocess`, and asserts the `assert_never` arm is reported as unreachable (i.e., the inverse coverage ratchet fires).
5. **Sanity-check against the live `queries.py` before committing.** Run `python -c "from codegenie.tccm.queries import ConsumersOf, ProducersOf, ReverseLookup, RefsTo, TestsExercising; [print(c.__name__, list(c.model_fields)) for c in (ConsumersOf, ProducersOf, ReverseLookup, RefsTo, TestsExercising)]"`. The expected output (verified against `master` 2026-05-15) is two fields per variant: `compute` (defaulted Literal) and one of `pkg` / `module` / `symbol`. If `master` has drifted (additional fields, renamed payload field), align the YAML and `_expected_tccm()` to whatever `queries.py` ships and record the resolution in the attempt log — `queries.py` is the source of truth, this story conforms.
6. **`_reference-tccm/README.md`** — short, one paragraph:
   ```markdown
   # Reference TCCM for `index-health-self-check`

   This directory holds the Phase 2 reference TCCM — a minimal Task-Class
   Context Manifest (ADR-0029) that exercises every field of the `TCCM`
   Pydantic model and every variant of the five-primitive `DerivedQuery`
   discriminated union (ADR-0030). It is **documentation**, not a plugin
   (02-ADR-0007); it lives under `docs/`, not under `plugins/`, deliberately
   outside the namespace Phase 3 owns (ADR-0031 §Consequences §1).

   Consumed by `tests/integration/tccm/test_reference_tccm_roundtrips.py`,
   which closes `phase-arch-design.md §"Gap analysis" Gap 1`
   ("Protocols defined, never called in Phase 2") by dispatching each
   `DerivedQuery` variant to a mock adapter implementing all four Phase 2
   `Protocol`s and asserting every Protocol method is invoked at least once.

   Do not move this fixture without updating the test paths and 02-ADR-0007.
   `_invalid/unknown_compute.yaml` is a sibling negative fixture for the
   `TCCMLoadError(reason="unknown_query_primitive")` path (S1-04).
   ```

## TDD plan — red / green / refactor

### Red — write the failing test first

Land `tests/integration/tccm/__init__.py` + `test_reference_tccm_roundtrips.py` (the file shown in Implementation outline §4) **before** the YAML fixture. Every test fails because `REFERENCE_PATH` does not exist (or, in the case of `_expected_tccm`, because the `TCCMLoader` call returns an error). Commit as red.

### Green — make it pass

1. Create the directory `docs/phases/02-context-gather-layers-b-g/_reference-tccm/`.
2. Write `tccm.yaml` per Implementation outline §1. **Run the test once** — it will likely fail with a Pydantic `ValidationError` against `_expected_tccm()` if the variant field names differ from this story's prescription. Adjust the YAML and `_expected_tccm()` until they agree, **matching whatever shape S1-04 actually shipped** (which is the authoritative parser).
3. Write `_invalid/unknown_compute.yaml` per Implementation outline §2.
4. Write `_reference-tccm/README.md` per Implementation outline §6.
5. Re-run the test suite. All six tests pass.

### Refactor — clean up

- The mock adapter classes stay in the test file (one-shot mocks are not worth a fixture module).
- The `_dispatch` helper stays in the test file as a private function; it is the in-Phase-2 proof of correctness for the Protocol/Query alignment, not production code (Phase 8's Bundle Builder is the production dispatcher).
- If `_expected_tccm()` grows past ~30 lines, factor it to a `_fixtures.py` sibling; otherwise inline.
- Do **not** centralize a "Protocol coverage map" — the `called(...)` assertions in `test_mock_dispatcher_invokes_every_protocol_method_at_least_once` are the documentation. A central map would have to be edited every time a Protocol method is added; the test failure on a missed method is the better forcing function.

## Files to touch

| Path | Why |
|---|---|
| `docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml` | New — reference TCCM exercising every TCCM field + every `DerivedQuery` variant |
| `docs/phases/02-context-gather-layers-b-g/_reference-tccm/README.md` | New — explains why the fixture lives under `docs/`, not `plugins/`; cites 02-ADR-0007 + Gap 1 |
| `docs/phases/02-context-gather-layers-b-g/_reference-tccm/_invalid/unknown_compute.yaml` | New — `unknown_query_primitive:` prefix (AC-7) |
| `docs/phases/02-context-gather-layers-b-g/_reference-tccm/_invalid/malformed.yaml` | New — `parse:` prefix (AC-7b) |
| `docs/phases/02-context-gather-layers-b-g/_reference-tccm/_invalid/missing_required_probes.yaml` | New — `schema:` prefix (AC-7b) |
| `docs/phases/02-context-gather-layers-b-g/_reference-tccm/_invalid/extra_top_level_key.yaml` | New — `schema:` prefix (AC-3c, AC-7b) |
| `docs/phases/02-context-gather-layers-b-g/_reference-tccm/_floors/trusted.yaml` | New — `confidence_floor: Trusted` round-trip (AC-3b) |
| `docs/phases/02-context-gather-layers-b-g/_reference-tccm/_floors/degraded.yaml` | New — `confidence_floor: Degraded` round-trip (AC-3b) |
| `docs/phases/02-context-gather-layers-b-g/_reference-tccm/_floors/unavailable.yaml` | New — `confidence_floor: Unavailable` round-trip (AC-3b) |
| `tests/integration/__init__.py` | New if absent — package marker |
| `tests/integration/tccm/__init__.py` | New — package marker |
| `tests/integration/tccm/test_reference_tccm_roundtrips.py` | New — eleven named integration tests (incl. parametrized) closing Gap 1 |
| `tests/integration/tccm/test_dispatcher_coverage_ratchet.py` | New — AC-13 coverage ratchet via `mypy --warn-unreachable` subprocess |

## Out of scope

- **Bundle Builder** — Phase 8 owns the production dispatcher. The mock dispatcher in this story is a test-time proxy; it is not exported and not consumed by any production code.
- **A second TCCM** — Phase 3 ships the first real plugin's `tccm.yaml` (`plugins/vulnerability-remediation--node--npm/tccm.yaml`); Phase 2 ships one reference TCCM, deliberately under `docs/`.
- **Real adapter implementations** — Phase 3 (`adapters/scip_node.py`, etc.) per 02-ADR-0007. The mocks here are deliberately structural, not behavioral.
- **`@register_index_freshness_check` registration for the reference TCCM** — Phase 2's freshness registry is exercised by `IndexHealthProbe` (S4-01), not by the TCCM loader. The reference TCCM's `confidence_floor: degraded` is a model field, not a runtime registration.
- **A `SkillsLoader.find_applicable(["diagnose-stale-scip"])` call against the reference TCCM** — the reference TCCM's `required_skills` is data, not resolved against a live SkillsLoader; this story does not assert that the Skill named there exists. A future Phase 2 contributor adding `tests/fixtures/skills/diagnose-stale-scip/SKILL.md` and a `test_required_skill_is_findable` is welcome but outside this story.
- **`tests/integration/adapters/test_phase3_handoff_smoke.py`** — that file lands skipped in S7-04 as the cross-phase trip-wire. This story is the in-Phase-2 counterpart; the two are complementary, not duplicative.

## Notes for the implementer

- **Pin S1-04's variant field names before writing the YAML.** The story prescribes `ConsumersOf(pkg=..., name=..., max_files=...)` etc., but the authoritative definition lives in `src/codegenie/tccm/queries.py` (S1-04). Run `python -c "from codegenie.tccm.queries import ConsumersOf; print(ConsumersOf.model_fields.keys())"` first; align the YAML, `_expected_tccm()`, and the `match` arms to whatever S1-04 actually shipped. If a variant field name disagrees with this story's prescription, adjust this story's test file and YAML to match S1-04 — do not amend S1-04.
- **The `compute:` string parsing belongs to S1-04, not to this story.** S1-04 owns the regex / string-to-variant mapping (e.g., does `dep_graph.consumers_of("@x")` parse as `ConsumersOf(pkg="@x")`?). This story's YAML must produce a tree that S1-04's loader accepts. If S1-04's `compute:` form is `compute: { primitive: consumers_of, args: { pkg: "@x" } }` instead of the inline-DSL shape this story shows, adopt S1-04's form verbatim and update `_expected_tccm()`.
- **`runtime_checkable` is the load-bearing decorator on the Protocols.** AC-5's `isinstance(mock_dep, DepGraphAdapter)` only works because S1-03 applied `@runtime_checkable` to the Protocols. If for some reason S1-03 omitted that decorator, file a Phase 2 amendment ADR and add it — this is the discoverability mechanism for Phase 3 plugin authors.
- **Adapter-confidence shape.** The `AdapterConfidence` discriminated union lives at `src/codegenie/adapters/confidence.py`. The mock `confidence()` methods return one of `Trusted`, `Degraded`, `Unavailable` from there; do not invent a fourth state in this test. If the dispatcher boundary returns `Unavailable(reason="scip_offline_in_test")`, that's fine for the mock — the test only asserts the method was called, not that it returned a specific value.
- **`_invalid/` sibling directory.** The negative fixture (`unknown_compute.yaml`) lives under `_reference-tccm/_invalid/` so it's discoverable to a future contributor looking at the reference fixture. Do not put it under `tests/fixtures/` — keeping the positive and negative TCCM examples together is the documentation discipline 02-ADR-0007 implies.
- **`assert_never` in the test's `_dispatch`.** AC-6 demands a `case _ as unreachable: assert_never(unreachable)` arm. Python's `typing.assert_never` raises `AssertionError` at runtime when the static-typing escape hatch is reached; `pytest.raises((AssertionError, TypeError, ValueError))` is the defensive catch (different Python minor versions have raised different exception types).
- **The mock dispatcher is NOT production code.** Do not export it from a `src/` module. Do not let it leak into a future story. It is a test fixture that proves the Phase 2 Protocols are wired to accept the Phase 2 `DerivedQuery` shapes. Phase 8's Bundle Builder is the production dispatcher; that is a separate phase's design.
- **If the Phase 1 `Result` API is `Result.Ok(value)` / `Result.Err(error)` constructors plus `.is_ok()` / `.unwrap()` / `.is_err()` / `.unwrap_err()`** — verify the method names in `src/codegenie/result.py` before writing the test. The exact API was nailed down in S1-04; mirror it. If `result` uses `.value` / `.error` attribute access instead of `.unwrap()` methods, conform.
- **`mypy --warn-unreachable` on the dispatcher.** The five-arm `match` over `DerivedQuery` plus an `assert_never` final arm should type-check cleanly. If `mypy` complains that the `_ as unreachable` arm is reachable, you have a missing `case` — fix the dispatcher, do not silence the warning. This is the exhaustiveness ratchet `phase-arch-design.md §"Agentic best practices" → "Typed state"` requires from day 1.

### Design patterns

- **Sum type + exhaustive `match` + `assert_never`** is the correct shape for `_dispatch`. Sibling-symmetric with S1-01 (`StaleReason`), S1-04 (`_classify` over `LoaderReason`), and the `AdapterConfidence` consumers. **Do not** introduce a registry pattern here (`@register_dispatcher_for(ConsumersOf)`) — three-strikes hasn't fired (one dispatcher in this phase) and Phase 8's Bundle Builder is the production dispatcher per ADR-0030's design lineage. The Refactor section codifies "do not export" — keep it that way.
- **`_ProtocolMethod(StrEnum)` is the typed surface, not a registry.** Mirror of S1-04's `LoaderReason: TypeAlias = Literal[...]`. Adding a Protocol method requires adding an enum value (single-place edit); the AC-4 assertion auto-iterates. The forcing-function discipline survives without a "central Protocol coverage map" — the StrEnum **is** the surface.
- **Mock-class duplication is intentional.** The four `_Mock*` classes share an `__init__` + `confidence()` shape that violates three-strikes on its face. Rule 3 wins: these mocks are deleted when Phase 8's Bundle Builder ships real adapters. Pulling a `_RecordingAdapter` mixin couples four test fixtures to a micro-abstraction with one consumer, makes the mocks harder to delete later, and obscures the structural-Protocol-conformance proof (the explicit method list is the documentation).
- **Coverage ratchet via `mypy --warn-unreachable` subprocess.** AC-13's sibling test is the **inverse coverage ratchet**: a copy of `_dispatch` with one `case` arm deleted should make `mypy --warn-unreachable` flag the `assert_never` arm as reachable. This is the production ADR-0030 §Consequences ratchet — not a new mechanism, an enforcement of an existing one. Keep the synthetic copy under `_ratchet_fixtures/` (gitignored) so future renames don't ripple into the test.
- **Newtype opportunity flagged for future ADR (out of scope here).** The four Protocols take `pkg: str`, `module: str`, `symbol: str` — semantically distinct domains all collapsed to `str` (production ADR-0033 §3 "primitive obsession on domain identifiers" review-blocker pattern). S2-03 does **not** widen S1-03's Protocol surface; that's a Phase-3-entry amendment ADR. Record the opportunity here but do not act on it.
- **Functional-core / imperative-shell:** `_dispatch` mutates the mocks via the Protocol calls — tangled. Pure version would return `list[Call]`. Resist the refactor: this is a test fixture that proves Protocol invocation; the side effect IS the assertion target. Pure version would obscure intent.
