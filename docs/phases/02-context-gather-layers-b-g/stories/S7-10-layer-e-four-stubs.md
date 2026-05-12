# Story S7-10 — Layer E stubs: `service_topology` + `service_contract` + `slo` + `production_config`

**Step:** Step 7 — Ship Layer D, Layer E (real + stubs), Layer G; plant per-file findings sub-caches
**Status:** Ready
**Effort:** S
**Depends on:** S2-07
**ADRs honored:** `final-design.md` §"Components" §6 — Layer E E2–E5 stubs (real impl in Phase 14)

## Context

Four Layer E probes ship as **stubs** in Phase 2: `ServiceTopologyProbe` (E2), `ServiceContractProbe` (E3), `SLOProbe` (E4), `ProductionConfigProbe` (E5). Each `applies()` returns `False` unless `ctx.config` provides a source — the Phase 14 portfolio-scale phase wires the sources. Shipping them now means **the contract surface is on disk** so Phase 14 extends by *addition* (filling in implementations) rather than by *creating new probes*. Each stub has a real sub-schema + a real registration; the only thing missing is the real fetch logic. The "stub shape" assertion in tests is one per probe: `applies() == False` by default; `slice = {}` (or a canonical empty shape) when force-applied.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #21 Layer E` — stub policy.
  - `../phase-arch-design.md §"Data model"` — `applies_to_tasks` semantics.
- **Source design:**
  - `../final-design.md §"Components" §6 Layer E — E2-E5 are documented stubs per localv2.md §5.5`.
- **Existing code:**
  - `src/codegenie/probes/base.py` (Phase 0) — `Probe.applies(ctx) -> bool` ABC method; default `True`.
  - `src/codegenie/probes/__init__.py` — registration target.

## Goal

Ship four stub probes — `src/codegenie/probes/{service_topology,service_contract,slo,production_config}.py` — plus four sub-schemas; each `applies()` returns `False` unless `ctx.config.<probe_name>.source` is set; one unit test per stub asserts the stub shape + default `applies() == False`.

## Acceptance criteria

- [ ] `src/codegenie/probes/service_topology.py` — `ServiceTopologyProbe(Probe)`, `name="service_topology"`, `declared_inputs=[]`, `requires=[]`, `applies_to_languages=["*"]`. `applies(self, ctx) -> bool: return bool(ctx.config.get("service_topology", {}).get("source"))`. `run` returns `slice = {"services": [], "edges": [], "source": <configured-source>}` with `confidence: high`.
- [ ] `src/codegenie/probes/service_contract.py` — `ServiceContractProbe`, `name="service_contract"`. `applies()` keyed on `ctx.config.service_contract.source`. `run` returns `slice = {"contracts": [], "source": <configured-source>}`.
- [ ] `src/codegenie/probes/slo.py` — `SLOProbe`, `name="slo"`. `applies()` keyed on `ctx.config.slo.source`. `run` returns `slice = {"slos": [], "source": <configured-source>}`.
- [ ] `src/codegenie/probes/production_config.py` — `ProductionConfigProbe`, `name="production_config"`. `applies()` keyed on `ctx.config.production_config.source`. `run` returns `slice = {"configs": [], "source": <configured-source>}`.
- [ ] Four sub-schemas at `src/codegenie/schema/probes/{service_topology,service_contract,slo,production_config}.schema.json` — `additionalProperties: false`; `schema_version: "v1"`; each describes the canonical empty shape (e.g., `services: array` with `items` typed as the Phase 14 anticipated shape — at this stage, an empty array is the contract).
- [ ] When `applies() == False`, the probe **does not run**; the coordinator emits no slice for it (existing Phase 0 contract). No `Skipped` entry in `repo-context.yaml` per the Phase 0/1 convention.
- [ ] When `applies() == True` (test forces via fake config), the probe emits the canonical empty slice; downstream schema validation passes.
- [ ] `tests/unit/probes/test_e_stubs.py` — parametrized over the four stubs: `test_default_applies_false`, `test_with_source_applies_true_and_emits_canonical_empty_shape`. **One assertion per stub** × 2 cases = 8 test cases total (use `pytest.mark.parametrize`).
- [ ] Four goldens at `tests/golden/{service_topology,service_contract,slo,production_config}/applied/expected.json` (the "applies-true" case; default-skip case has no golden by design).
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Create four near-identical probe modules. Pattern:
   ```python
   # src/codegenie/probes/service_topology.py
   class ServiceTopologyProbe(Probe):
       name = "service_topology"
       declared_inputs: ClassVar[list[str]] = []
       requires: ClassVar[list[str]] = []
       applies_to_languages: ClassVar[list[str]] = ["*"]
       applies_to_tasks: ClassVar[list[str]] = ["*"]
       timeout_seconds = 10

       def applies(self, ctx: ProbeContext) -> bool:
           return bool(ctx.config.get("service_topology", {}).get("source"))

       async def run(self, snapshot: Snapshot, ctx: ProbeContext) -> ProbeOutput:
           source = ctx.config["service_topology"]["source"]
           return ProbeOutput(
               probe_name=self.name,
               probe_version="0.1.0",
               schema_version="v1",
               confidence="high",
               slice={"services": [], "edges": [], "source": source},
               errors=[],
               warnings=[],
               # ... cache-key + wall_clock + execution per Phase 0 contract
           )
   ```
2. Create four sub-schemas. Each canonical empty shape is documented inline in the schema; Phase 14 will extend by adding `items` schemas to the arrays.
3. Register all four in `probes/__init__.py`.
4. Plant minimal fixtures — no on-disk repo fixtures needed; tests construct config dicts inline.

## TDD plan — red / green / refactor

### Red

Path: `tests/unit/probes/test_e_stubs.py`.

```python
import pytest
from codegenie.probes.service_topology import ServiceTopologyProbe
from codegenie.probes.service_contract import ServiceContractProbe
from codegenie.probes.slo import SLOProbe
from codegenie.probes.production_config import ProductionConfigProbe

STUBS = [
    (ServiceTopologyProbe, "service_topology", {"services": [], "edges": []}),
    (ServiceContractProbe, "service_contract", {"contracts": []}),
    (SLOProbe, "slo", {"slos": []}),
    (ProductionConfigProbe, "production_config", {"configs": []}),
]

@pytest.mark.parametrize("probe_cls,config_key,expected_empty_fields", STUBS)
def test_default_applies_false(probe_cls, config_key, expected_empty_fields, ctx_empty):
    probe = probe_cls()
    assert probe.applies(ctx_empty) is False

@pytest.mark.parametrize("probe_cls,config_key,expected_empty_fields", STUBS)
async def test_with_source_applies_true_and_emits_canonical_shape(
    probe_cls, config_key, expected_empty_fields, ctx_factory
):
    ctx = ctx_factory(config={config_key: {"source": "stub-source"}})
    probe = probe_cls()
    assert probe.applies(ctx) is True
    out = await probe.run(snapshot_stub(), ctx)
    assert out.confidence == "high"
    for field in expected_empty_fields:
        assert out.slice.get(field) == []
    assert out.slice["source"] == "stub-source"
```

### Green

Minimal impl per outline. Each probe is ~30 LOC. Templating from one to four is fine; don't over-abstract into a metaclass-driven factory — the explicitness is the documentation.

### Refactor

- Module docstrings naming `phase-arch-design.md §"Component design" #21`, `final-design.md "Components" §6`. State explicitly: "Phase 14 fills in the real fetch logic; the contract surface is committed here."
- Each module is < 50 LOC — readable as one screen.
- Sub-schemas link to a comment in their `description` field: "Stub in Phase 2; canonical shape committed for Phase 14 extension."

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/service_topology.py` | New — stub. |
| `src/codegenie/probes/service_contract.py` | New — stub. |
| `src/codegenie/probes/slo.py` | New — stub. |
| `src/codegenie/probes/production_config.py` | New — stub. |
| `src/codegenie/schema/probes/service_topology.schema.json` | New — canonical empty shape. |
| `src/codegenie/schema/probes/service_contract.schema.json` | New — canonical empty shape. |
| `src/codegenie/schema/probes/slo.schema.json` | New — canonical empty shape. |
| `src/codegenie/schema/probes/production_config.schema.json` | New — canonical empty shape. |
| `src/codegenie/probes/__init__.py` | Register 4 stubs. |
| `tests/unit/probes/test_e_stubs.py` | New — parametrized over all 4 stubs. |
| `tests/golden/{service_topology,service_contract,slo,production_config}/applied/expected.json` | New — 4 goldens. |

## Out of scope

- **Real fetch logic for any of the four** — Phase 14 owns the implementations.
- **Source-type variation** — each `source` is a string in Phase 2; Phase 14 may introduce typed source kinds (`type: "manifest" | "consul" | ...`).
- **Cross-stub correlation** — Phase 14 wires service-topology ↔ service-contract relationships.
- **CLI flags to force-apply / skip the stubs** — Phase 14 may add; Phase 2 ships only the config-driven `applies()`.
- **Schema evolution from empty-shape to populated-shape** — covered by ADR-0008 / Schema-Evolution-Policy (S2-05) when Phase 14 lands.

## Notes for the implementer

- **Resist abstracting these into a single `StubProbe` base class.** Four separate modules with near-identical code is fine — the explicitness is the documentation. Phase 14 will diverge them rapidly (different source types, different schemas, different `run` logic); an abstract base will fight that. Rule 3 (Surgical Changes) and Rule 2 (Simplicity First).
- **`applies() == False` means the coordinator skips dispatch entirely** (Phase 0 contract). The slice doesn't appear in `repo-context.yaml`. This is *different* from `RuntimeTraceProbe`'s `not_applicable` status (`final-design.md` Conflict-resolution D10 — that probe emits a slice with `status: "not_applicable"` because `IndexHealthProbe` reads it). The Layer E stubs are absent-not-present.
- **The canonical empty shape is the Phase 14 contract.** Once committed, changing it requires a sub-schema bump (per S2-05's Schema-Evolution-Policy). Pick the empty-array shape that Phase 14 will most naturally extend. E.g., `services: []` will become `services: [{name, type, dependencies}]` — easy to extend; `services: {}` would force a Phase 14 breaking bump.
- **`source: str`** in the slice is the configured-source string verbatim. Don't sanitize, don't normalize. Phase 14 may move this to a typed object; that's a sub-schema bump.
- **Each probe's `probe_version = "0.1.0"`** because they're stubs. Phase 14 bumps to `1.0.0` when shipping real impl. The version is a cache-key component (Phase 0 contract).
- **Goldens at `applied/expected.json`** — the test that forces `applies()=True` is the goldened path. The default-skip case produces no slice and has no golden by design.
- **Tests can use a `ctx_factory` fixture** that mints a `ProbeContext` with arbitrary config. If Phase 0/1 doesn't already expose one, this story plants it under `tests/conftest.py` — small, testable, reusable.
- **`requires=[]`** — none of the stubs depend on other probes. Phase 14 may add dependencies (e.g., `slo` may require `service_topology`); leave the field empty for now.
- **Don't be tempted to add a `notes` field** to the canonical empty shape "in case Phase 14 wants it." Add nothing speculative. Phase 14's first PR will add what it needs; the sub-schema evolves under S2-05.
