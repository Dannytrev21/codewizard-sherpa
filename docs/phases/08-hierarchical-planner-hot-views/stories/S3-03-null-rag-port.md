# Story S3-03 — Ship the NullRagPort concrete adapter

**Step:** Step 3 — Declare the planner ports and extend the event union
**Status:** Ready
**Effort:** S
**Depends on:** S3-01
**ADRs honored:** ADR-0011

## Context
The recipe→RAG→LLM routing pipeline (S5-05) has three fixed steps, but Phase 8 has no real RAG backend — the Knowledge Graph arrives in Phase 11. To keep the three-step *shape* correct from day one, Phase 8 ships `NullRagPort`: a concrete `SolvedExampleRagPort` whose `query` always returns `None` (no solved-example hit). Phase 11 swaps the KG-backed adapter in with zero routing-code change. This story is the named ADR-0011 escape from a degenerate two-step pipeline (Open Question 4 — the three-step shape is preferred for ADR-0011 fidelity).

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C3 — PlannerNode` — "The `SolvedExampleRagPort` is a `NullRagPort` in Phase 8 … the RAG branch is structurally present and fake-port-unit-tested; Phase 11 swaps the adapter with zero routing-code change."
  - `../phase-arch-design.md §Development view` — `planner/null_rag.py — NullRagPort`.
  - `../phase-arch-design.md §Tradeoffs` — the `NullRagPort` vs two-step-pipeline row.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0011-fixed-three-step-routing-pipeline.md` — ADR-0011 — "The RAG Port is a `NullRagPort` in Phase 8 — structurally present, fake-port-unit-tested; Phase 11 swaps the KG-backed adapter in with zero routing-code change."
- **Source design:**
  - `../README.md §Open implementation questions` — Open Question 4: NullRagPort vs a two-step chain; the three-step shape is preferred.
- **Existing code (if any):**
  - `src/codegenie/planner/ports.py` (from S3-01) — `SolvedExampleRagPort` and `RagHit`.

## Goal
Ship `NullRagPort` — the Phase-8 concrete `SolvedExampleRagPort` whose `query` always returns `None` — structurally satisfying the port and proven so by a `Protocol`-assignment test.

## Acceptance criteria
- [ ] `codegenie/planner/null_rag.py` exists declaring `NullRagPort` — a concrete class (not a `Protocol`, not an `ABC` subclass) with `async def query(self, bundle: Bundle) -> RagHit | None` that returns `None` unconditionally.
- [ ] `NullRagPort` does **not** inherit from `SolvedExampleRagPort` — it satisfies the port structurally (`Protocol` discipline; the test proves the structural match).
- [ ] A test asserts `isinstance(NullRagPort(), SolvedExampleRagPort)` is `True` (the port is `@runtime_checkable` from S3-01) **and** that a static assignment `_p: SolvedExampleRagPort = NullRagPort()` type-checks under `mypy --strict`.
- [ ] `NullRagPort` is exported from `planner/__init__.py`'s `__all__` (the supervisor / planner-node wiring injects it).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Create `src/codegenie/planner/null_rag.py`.
2. Declare `NullRagPort` as a plain class with one method, `query`, returning `None`.
3. Add `NullRagPort` to `planner/__init__.py`'s `__all__`.
4. Write the `Protocol`-assignment test: both a runtime `isinstance` check and a static-typing line that `mypy --strict` exercises.
5. Run `mypy --strict src/codegenie/planner/` — the structural conformance is a real type-check gate.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/planner/test_null_rag.py`
Assert `NullRagPort` satisfies the port and always misses.
```python
def test_null_rag_port_satisfies_solved_example_rag_port() -> None:
    # arrange: instantiate NullRagPort()
    # act:    isinstance(NullRagPort(), SolvedExampleRagPort)
    # assert: True — structural Protocol conformance (no inheritance)

async def test_null_rag_query_always_returns_none() -> None:
    # arrange: a NullRagPort and any Bundle fixture
    # act:    await port.query(bundle)
    # assert: result is None — Phase 8 has no RAG backend; the branch is a structural placeholder
```
### Green — make it pass
Write `null_rag.py` with `NullRagPort.query` returning `None`. Add it to `__all__`.
### Refactor — clean up
Docstring on `NullRagPort` naming ADR-0011 and Open Question 4 — state explicitly that Phase 11 swaps the KG-backed adapter in with zero routing-code change. Add a static-typing assertion line in the test module (`_p: SolvedExampleRagPort = NullRagPort()`) so `mypy --strict` proves the conformance, not just the runtime check. Note the public-surface running total in the attempt log.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/planner/null_rag.py` | The `NullRagPort` concrete adapter. |
| `src/codegenie/planner/__init__.py` | Export `NullRagPort` via `__all__`. |
| `tests/unit/planner/test_null_rag.py` | Red test — Protocol-assignment + always-`None` behavior. |

## Out of scope
- The KG-backed `SolvedExampleRagPort` adapter — Phase 11.
- `PlannerNode` wiring `NullRagPort` into the routing tuple — S5-05.
- `RecipeMatchPort` / `LeafLlmPort` concrete adapters — out of Phase 8's scope (recipe matching reuses the shipped `RecipeRegistry`; the LLM adapter lands with ADR-0020).

## Notes for the implementer
- `NullRagPort` must satisfy `SolvedExampleRagPort` **structurally** — do not write `class NullRagPort(SolvedExampleRagPort)`. The whole point of the hexagonal `Protocol` is that the adapter conforms by shape; the test proves it.
- The static-typing assertion (`_p: SolvedExampleRagPort = NullRagPort()` in the test) is the load-bearing half — it makes `mypy --strict` the gate, not just the runtime `isinstance`. A purely runtime check would pass even if the signature drifted.
- `query` returns `None` *unconditionally* — there is no logic, no flag, no config. Resist adding a "configurable null" — Open Question 4's named fallback is a two-step chain, decided only if the null branch creates dead-test burden, and that is not this story's call.
- Keep `null_rag.py` LLM-SDK-free — it lives in `codegenie.planner` and is fenced by S1-03.
