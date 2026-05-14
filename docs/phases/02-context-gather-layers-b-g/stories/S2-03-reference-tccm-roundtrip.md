# Story S2-03 — Reference TCCM + roundtrip integration exercising every Protocol method

**Step:** Step 2 — Plant kernel-side loaders (`SkillsLoader`, `ConventionsCatalogLoader`) and reference TCCM
**Status:** Ready
**Effort:** S
**Depends on:** S1-04 (`TCCMLoader`, `TCCM` model, 5-variant `DerivedQuery` discriminated union, `TCCMLoadError`), S2-01 (`SkillsLoader` + `Skill` model — the reference TCCM names `required_skills` whose IDs must roundtrip)
**ADRs honored:** 02-ADR-0007 (kernel-side scaffolding only; reference TCCM lives in `docs/`, **not** in `plugins/` — "documentation as code, deliberately outside the plugin namespace"), production ADR-0029 (Task-Class Context Manifests), production ADR-0030 (graph-aware context queries — five primitives), production ADR-0032 (Language Search Adapters — four `Protocol`s); closes **Gap 1** from `../phase-arch-design.md §"Gap analysis"` ("Adapter Protocol drift between Phase 2 and Phase 3" / "Protocols defined, never called in Phase 2")

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
  - `../../production/adrs/0030-graph-aware-context-queries.md` — five-primitive `DerivedQuery` taxonomy (`reverse_lookup`, `scip.refs`, `tests_exercising`, plus `consumers_of` / `producers_of` from the dep-graph primitives section).
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
   - Includes **five `derived_queries` entries — one per `DerivedQuery` variant** (`ConsumersOf`, `ProducersOf`, `ReverseLookup`, `RefsTo`, `TestsExercising`) — each with the `compute:` form ADR-0030 names and each shaped to round-trip through Pydantic.

2. **`tests/integration/tccm/test_reference_tccm_roundtrips.py`** — six named tests:
   - **`test_reference_tccm_loads_and_equals_expected_pydantic_instance`** — `TCCMLoader.load(REFERENCE_PATH)` returns `Result.Ok(tccm)`; `tccm == _expected_tccm()` where `_expected_tccm()` constructs the TCCM by hand from the canonical Pydantic constructors. Pins the YAML-to-Pydantic deserialization shape end-to-end.
   - **`test_reference_tccm_exercises_every_derived_query_variant`** — exactly one entry per variant in `tccm.derived_queries`; the five-element set of `type(q).__name__` over `tccm.derived_queries` equals `{"ConsumersOf", "ProducersOf", "ReverseLookup", "RefsTo", "TestsExercising"}`. Pins the "exercises every variant" commitment.
   - **`test_mock_dispatcher_invokes_every_protocol_method_at_least_once`** — the load-bearing AC. A `_MockDispatcher` defines four mock adapters that structurally satisfy the four `Protocol`s (`isinstance(mock_dep, DepGraphAdapter)` is True under `runtime_checkable`). The dispatcher routes each `DerivedQuery` to the appropriate Protocol method; a call-recorder asserts that **every method on every Protocol is invoked at least once** across the five queries. Specifically:
     - `ConsumersOf` → `DepGraphAdapter.consumers(...)`
     - `ProducersOf` → `DepGraphAdapter.producers(...)`
     - `ReverseLookup` → `ImportGraphAdapter.reverse_lookup(...)`
     - `RefsTo` → `ScipAdapter.refs(...)`
     - `TestsExercising` → `TestInventoryAdapter.tests_exercising(...)`
     - All four `*.confidence()` methods are called once at the dispatcher boundary (single-batch confidence reporting); this picks up the `Protocol.confidence()` method from all four.
   - **`test_dispatcher_match_is_exhaustive_assert_never_fires_on_smuggled_variant`** — runtime smoke: a hand-constructed `object()` with a `kind` attribute the discriminator does not recognize triggers the dispatcher's `case _ as unreachable: assert_never(unreachable)` branch. Pins ADR-0033 §4.
   - **`test_unknown_compute_primitive_returns_typed_result_err`** — a sibling fixture (`_reference-tccm/_invalid/unknown_compute.yaml`) with `compute: graph_explode(...)` round-trips through `TCCMLoader` and yields `Result.Err(TCCMLoadError(reason="unknown_query_primitive"))`. Pins S1-04's failure-path contract from the perspective of a real on-disk fixture.
   - **`test_reference_tccm_lives_under_docs_not_under_plugins`** — directory-discipline guard: the resolved path of `REFERENCE_PATH` starts with `<repo_root>/docs/`, and `<repo_root>/plugins/` either does not exist or contains zero `tccm.yaml` files. If a future contributor moves the fixture to `tests/fixtures/plugins/`, this test fails — closes the boundary 02-ADR-0007 sets.

## Acceptance criteria

- [ ] **AC-1 — reference TCCM exists at the canonical path.** `docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml` exists; the directory holds **only** the reference TCCM and the `_invalid/` sibling fixture used by AC-7; no other files. Pinned by `test_reference_tccm_lives_under_docs_not_under_plugins`.
- [ ] **AC-2 — five `derived_queries` entries, one per variant.** The fixture YAML's `derived_queries` list has exactly five entries; after `TCCMLoader.load`, the multiset of `type(q).__name__` is exactly `{"ConsumersOf", "ProducersOf", "ReverseLookup", "RefsTo", "TestsExercising"}` (no duplicates, no omissions). Pinned by `test_reference_tccm_exercises_every_derived_query_variant`.
- [ ] **AC-3 — round-trip equality.** `TCCMLoader.load(REFERENCE_PATH)` returns `Result.Ok(tccm)` and `tccm == _expected_tccm()`, where `_expected_tccm()` is a hand-constructed `TCCM(...)` using the canonical Pydantic constructors. Asserts equality on every field (`schema_version`, `task_class`, `required_probes`, `required_skills`, `derived_queries`, `confidence_floor`). Pinned by `test_reference_tccm_loads_and_equals_expected_pydantic_instance`.
- [ ] **AC-4 — every Protocol method invoked.** The mock dispatcher's call recorder reports at least one invocation for each of the nine Protocol methods: `DepGraphAdapter.consumers`, `DepGraphAdapter.producers`, `DepGraphAdapter.confidence`, `ImportGraphAdapter.reverse_lookup`, `ImportGraphAdapter.confidence`, `ScipAdapter.refs`, `ScipAdapter.confidence`, `TestInventoryAdapter.tests_exercising`, `TestInventoryAdapter.confidence`. **This is the Gap 1 closer.** Pinned by `test_mock_dispatcher_invokes_every_protocol_method_at_least_once`.
- [ ] **AC-5 — mocks structurally satisfy the Protocols.** `isinstance(mock_dep, DepGraphAdapter)`, `isinstance(mock_import, ImportGraphAdapter)`, `isinstance(mock_scip, ScipAdapter)`, `isinstance(mock_test, TestInventoryAdapter)` are all `True` (relying on `@runtime_checkable`). Pins that the mocks aren't faking the conformance.
- [ ] **AC-6 — exhaustive `match` discipline.** The dispatcher's `match query: case ...: ... case _ as unreachable: assert_never(unreachable)` branch fires when a hand-constructed imposter object is passed. Pinned by `test_dispatcher_match_is_exhaustive_assert_never_fires_on_smuggled_variant`.
- [ ] **AC-7 — invalid-fixture path returns typed `Result.Err`.** `_reference-tccm/_invalid/unknown_compute.yaml` (`compute: graph_explode(...)`) loads to `Result.Err(TCCMLoadError(reason="unknown_query_primitive"))`. Pins the S1-04 failure-path contract under realistic on-disk input.
- [ ] **AC-8 — directory discipline (02-ADR-0007).** The reference TCCM's resolved path is rooted at `<repo_root>/docs/`. A walk of `<repo_root>/plugins/` (if it exists) finds **zero** files named `tccm.yaml`. Pinned by `test_reference_tccm_lives_under_docs_not_under_plugins`. This guards the Phase-2/Phase-3 directory boundary.
- [ ] **AC-9 — fixture passes `safe_yaml.load` chokepoint validity.** The reference TCCM YAML loads without raising via `safe_yaml.load(REFERENCE_PATH, max_bytes=64 << 10)` directly (independent of `TCCMLoader`) — proves the on-disk fixture is well-formed at the parser layer too. Asserted in a one-line sanity test.
- [ ] **AC-10 — README under `_reference-tccm/`.** A `_reference-tccm/README.md` (one paragraph) explains (a) why this directory lives under `docs/`, not `plugins/`; (b) which Phase 2 test consumes it; (c) cross-links to 02-ADR-0007 + Gap 1 in the arch design. Future contributors must not delete or move this fixture casually.
- [ ] **AC-11 — toolchain.** `ruff check`, `ruff format --check`, `mypy --strict`, `mypy --warn-unreachable` clean. `pytest tests/integration/tccm/test_reference_tccm_roundtrips.py` passes.
- [ ] **AC-12 — TDD discipline.** Red tests committed failing (because the fixture YAML and the mock dispatcher do not yet exist); green commit makes them pass; refactor commit is no-op behavior. Validator can reproduce.

## Implementation outline

1. **Author the reference TCCM** at `docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml`. Skeleton (the exact `compute:` strings must match the five-variant `DerivedQuery` deserialization the S1-04 loader implements — read `src/codegenie/tccm/queries.py` for the literal forms):
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
     - name: who_consumes_scip_index
       compute: dep_graph.consumers_of("@codegenie/scip")
       max_files: 50
     - name: who_produces_scip_index
       compute: dep_graph.producers_of("@codegenie/scip")
       max_files: 50
     - name: files_importing_index_health
       compute: import_graph.reverse_lookup("codegenie/probes/layer_b/index_health.py")
       max_files: 100
     - name: refs_to_index_freshness_type
       compute: scip.refs("codegenie/indices/freshness.IndexFreshness")
       max_files: 200
     - name: tests_exercising_index_health
       compute: test_inventory.tests_exercising("codegenie/probes/layer_b/index_health.py")
       max_files: 100
   ```
   The exact `compute:` string-to-variant mapping is owned by S1-04's `queries.py` parser; this fixture **must** parse cleanly under that parser. If S1-04's `compute:` parsing accepts a slightly different form (e.g., `consumers_of(pkg)` without a quoted argument), adjust the fixture to match. The story does not pin S1-04's parser shape; S1-04 does.
2. **Author the invalid fixture** at `docs/phases/02-context-gather-layers-b-g/_reference-tccm/_invalid/unknown_compute.yaml`:
   ```yaml
   schema_version: "1"
   task_class: index-health-self-check
   required_probes: [b2_index_health]
   required_skills: []
   confidence_floor: {kind: trusted}
   derived_queries:
     - name: bad_query
       compute: graph_explode("@codegenie/scip")
       max_files: 50
   ```
3. **Author `_reference-tccm/README.md`** — one paragraph per AC-10.
4. **Test file** `tests/integration/tccm/__init__.py` (empty) and `tests/integration/tccm/test_reference_tccm_roundtrips.py` with the six named tests:
   ```python
   # tests/integration/tccm/test_reference_tccm_roundtrips.py
   from __future__ import annotations
   from pathlib import Path
   from typing import assert_never
   from unittest.mock import MagicMock

   import pytest

   from codegenie.adapters.confidence import Degraded, Trusted, Unavailable
   from codegenie.adapters.protocols import (
       DepGraphAdapter, ImportGraphAdapter, ScipAdapter, TestInventoryAdapter,
   )
   from codegenie.tccm.loader import TCCMLoader
   from codegenie.tccm.queries import (
       ConsumersOf, ProducersOf, ReverseLookup, RefsTo, TestsExercising,
   )
   from codegenie.tccm.model import TCCM

   REPO_ROOT = Path(__file__).resolve().parents[3]
   REFERENCE_PATH = REPO_ROOT / "docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml"
   INVALID_UNKNOWN_COMPUTE = (REPO_ROOT
       / "docs/phases/02-context-gather-layers-b-g/_reference-tccm/_invalid/unknown_compute.yaml")


   # ---- Mocks that structurally satisfy the four Protocols --------------------

   class _MockDepGraph:
       def __init__(self) -> None:
           self.calls: list[tuple[str, tuple]] = []
       def consumers(self, pkg: str) -> list[str]:
           self.calls.append(("consumers", (pkg,))); return ["a", "b"]
       def producers(self, pkg: str) -> list[str]:
           self.calls.append(("producers", (pkg,))); return ["c"]
       def confidence(self) -> object:
           self.calls.append(("confidence", ())); return Trusted(kind="trusted")

   class _MockImportGraph:
       def __init__(self) -> None: self.calls: list = []
       def reverse_lookup(self, module: str) -> list[str]:
           self.calls.append(("reverse_lookup", (module,))); return ["x.py"]
       def confidence(self) -> object:
           self.calls.append(("confidence", ())); return Trusted(kind="trusted")

   class _MockScip:
       def __init__(self) -> None: self.calls: list = []
       def refs(self, symbol: str) -> list:
           self.calls.append(("refs", (symbol,))); return []
       def confidence(self) -> object:
           self.calls.append(("confidence", ()))
           return Degraded(kind="degraded", reason="self-check")

   class _MockTestInventory:
       def __init__(self) -> None: self.calls: list = []
       def tests_exercising(self, symbol: str) -> list:
           self.calls.append(("tests_exercising", (symbol,))); return []
       def confidence(self) -> object:
           self.calls.append(("confidence", ())); return Trusted(kind="trusted")


   def _dispatch(query, *, dep, imp, scip, tests) -> None:
       """Route a DerivedQuery to the appropriate Protocol method. assert_never
       on unreachable; this is the load-bearing exhaustiveness guard (AC-6)."""
       match query:
           case ConsumersOf(pkg=p):       dep.consumers(p)
           case ProducersOf(pkg=p):       dep.producers(p)
           case ReverseLookup(module=m):  imp.reverse_lookup(m)
           case RefsTo(symbol=s):         scip.refs(s)
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


   # ---- AC-9 ------------------------------------------------------------------

   def test_reference_tccm_is_safe_yaml_parseable() -> None:
       from codegenie.parsers import safe_yaml
       data = safe_yaml.load(REFERENCE_PATH, max_bytes=64 << 10)
       assert isinstance(data, dict)
       assert data["schema_version"] == "1"


   # ---- AC-3 ------------------------------------------------------------------

   def _expected_tccm() -> TCCM:
       return TCCM(
           schema_version="1",
           task_class="index-health-self-check",
           required_probes=["b2_index_health", "b1_scip", "b3_tree_sitter_imports"],
           required_skills=["diagnose-stale-scip"],
           confidence_floor=Degraded(kind="degraded",
                                     reason="stale_scip_acceptable_for_self_check"),
           derived_queries=[
               ConsumersOf(name="who_consumes_scip_index", pkg="@codegenie/scip", max_files=50),
               ProducersOf(name="who_produces_scip_index", pkg="@codegenie/scip", max_files=50),
               ReverseLookup(name="files_importing_index_health",
                             module="codegenie/probes/layer_b/index_health.py", max_files=100),
               RefsTo(name="refs_to_index_freshness_type",
                      symbol="codegenie/indices/freshness.IndexFreshness", max_files=200),
               TestsExercising(name="tests_exercising_index_health",
                               symbol="codegenie/probes/layer_b/index_health.py", max_files=100),
           ],
       )

   def test_reference_tccm_loads_and_equals_expected_pydantic_instance() -> None:
       result = TCCMLoader().load(REFERENCE_PATH)
       assert result.is_ok(), f"TCCMLoader failed: {result}"
       assert result.unwrap() == _expected_tccm()


   # ---- AC-2 ------------------------------------------------------------------

   def test_reference_tccm_exercises_every_derived_query_variant() -> None:
       tccm = TCCMLoader().load(REFERENCE_PATH).unwrap()
       variants = {type(q).__name__ for q in tccm.derived_queries}
       assert variants == {"ConsumersOf", "ProducersOf", "ReverseLookup",
                           "RefsTo", "TestsExercising"}


   # ---- AC-4, AC-5 (Gap 1 closer) ---------------------------------------------

   def test_mock_dispatcher_invokes_every_protocol_method_at_least_once() -> None:
       tccm = TCCMLoader().load(REFERENCE_PATH).unwrap()
       dep, imp, scip, tests = _MockDepGraph(), _MockImportGraph(), _MockScip(), _MockTestInventory()

       # Structural Protocol conformance — AC-5.
       assert isinstance(dep, DepGraphAdapter)
       assert isinstance(imp, ImportGraphAdapter)
       assert isinstance(scip, ScipAdapter)
       assert isinstance(tests, TestInventoryAdapter)

       for query in tccm.derived_queries:
           _dispatch(query, dep=dep, imp=imp, scip=scip, tests=tests)
       # Aggregate confidence call (the dispatcher boundary asks every adapter once).
       for adapter in (dep, imp, scip, tests):
           adapter.confidence()

       called = lambda calls, name: any(c[0] == name for c in calls)
       assert called(dep.calls, "consumers"),         "DepGraphAdapter.consumers never called"
       assert called(dep.calls, "producers"),         "DepGraphAdapter.producers never called"
       assert called(dep.calls, "confidence"),        "DepGraphAdapter.confidence never called"
       assert called(imp.calls, "reverse_lookup"),    "ImportGraphAdapter.reverse_lookup never called"
       assert called(imp.calls, "confidence"),        "ImportGraphAdapter.confidence never called"
       assert called(scip.calls, "refs"),             "ScipAdapter.refs never called"
       assert called(scip.calls, "confidence"),       "ScipAdapter.confidence never called"
       assert called(tests.calls, "tests_exercising"), "TestInventoryAdapter.tests_exercising never called"
       assert called(tests.calls, "confidence"),      "TestInventoryAdapter.confidence never called"


   # ---- AC-6 ------------------------------------------------------------------

   def test_dispatcher_match_is_exhaustive_assert_never_fires_on_smuggled_variant() -> None:
       class _Imposter:
           __match_args__ = ()
       with pytest.raises((AssertionError, TypeError, ValueError)):
           _dispatch(_Imposter(), dep=_MockDepGraph(), imp=_MockImportGraph(),
                     scip=_MockScip(), tests=_MockTestInventory())


   # ---- AC-7 ------------------------------------------------------------------

   def test_unknown_compute_primitive_returns_typed_result_err() -> None:
       result = TCCMLoader().load(INVALID_UNKNOWN_COMPUTE)
       assert result.is_err(), f"expected Result.Err, got {result}"
       err = result.unwrap_err()
       assert err.reason == "unknown_query_primitive"
   ```
5. **Validate against S1-04's actual variant fields.** Before committing the green code, run `python -c "from codegenie.tccm.queries import ConsumersOf; print(ConsumersOf.model_fields)"` and adjust `_expected_tccm()` field names to match S1-04's actual model. The story prescribes field names (`pkg`, `module`, `symbol`, `name`, `max_files`) consistent with ADR-0030; if S1-04 chose different names (e.g., `package` instead of `pkg`), update both the YAML fixture and `_expected_tccm()` and document the resolution in the implementer's attempt log.
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
| `docs/phases/02-context-gather-layers-b-g/_reference-tccm/_invalid/unknown_compute.yaml` | New — sibling negative fixture for `TCCMLoadError(reason="unknown_query_primitive")` |
| `docs/phases/02-context-gather-layers-b-g/_reference-tccm/README.md` | New — explains why the fixture lives under `docs/`, not `plugins/`; cites 02-ADR-0007 + Gap 1 |
| `tests/integration/__init__.py` | New if absent — package marker |
| `tests/integration/tccm/__init__.py` | New — package marker |
| `tests/integration/tccm/test_reference_tccm_roundtrips.py` | New — six named integration tests closing Gap 1 |

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
