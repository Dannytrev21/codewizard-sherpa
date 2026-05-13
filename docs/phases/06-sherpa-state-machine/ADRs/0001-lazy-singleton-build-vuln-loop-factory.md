# ADR-0001: `build_vuln_loop()` is a lazy-singleton factory, not a module constant

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** runtime · performance · testability
**Related:** [ADR-0002](0002-vuln-ledger-frozen-false-with-runtime-mutation-hook.md), [ADR-0009](0009-cli-loop-ships-parallel-to-cli-remediate.md), [production ADR-0002](../../../production/adrs/0002-langgraph-as-runtime-sherpa-as-discipline.md), [production ADR-0016](../../../production/adrs/0016-checkpointer-backend.md)

## Context

The compiled `StateGraph[VulnLedger]` is the artifact every workflow invocation consumes. Compiling it costs ~80 ms (`final-design.md §Component 2`, `phase-arch-design.md §Component 2`) — small for a single run, real for a worker that handles many. The three lens designs disagreed sharply about how to amortize that cost:

- The performance design shipped a **module-level constant** `VULN_LOOP: CompiledGraph = _build().compile(checkpointer=...)` so the compile cost was paid exactly once per process. But `critique.md performance.4` landed: a module-level singleton bakes the checkpointer path into module import, which means the `--checkpointer-db` CLI flag and per-test checkpointer swaps cannot work without re-compile, contradicting performance's own "saves 80 ms/wf" claim. Both can't be true.
- The best-practices and security designs ship **per-invocation** `build_vuln_graph(...)` / `build_vuln_loop_graph(...)`. Tests are clean; the 80 ms is paid on every CLI run and on every test setup.

Phase 6's exit criteria require the graph to be both performant in a long-lived worker (Phase 9 will reuse it) and testable in isolation (every replay/HITL test needs a fresh checkpointer at a fresh path). Tests must not silently share a stale compiled graph; production must not pay the compile cost per invocation.

## Options considered

- **Module-level singleton (performance's pick).** `VULN_LOOP = _build().compile(...)` at import. Fast, simple, broken: tests can't swap checkpointers without monkey-patching the module; the `--checkpointer-db` CLI flag is a no-op.
- **Per-invocation compile (best-practices' and security's pick).** Every call to `build_vuln_loop()` runs `_build().compile(...)`. Clean isolation; ~80 ms paid on every CLI run and every test setup.
- **Lazy singleton with explicit `force_rebuild`.** A module-level `_COMPILED` is populated on first call, keyed on `(id(checkpointer), max_attempts)`. Tests and CLI override with `force_rebuild=True` when they pass a fresh checkpointer.

## Decision

`build_vuln_loop()` lives in `src/codegenie/graph/vuln_loop.py` as a **lazy-singleton factory** with signature `build_vuln_loop(*, checkpointer, max_attempts=3, force_rebuild=False) -> CompiledGraph`. A module-level `_COMPILED: CompiledGraph | None` plus `_COMPILED_KEY: tuple[int, int] | None` caches the compiled graph; the cache is invalidated when `force_rebuild=True` or when the `(id(checkpointer), max_attempts)` key changes. Production workers pass the same checkpointer for the worker's lifetime and hit the cache; tests and the CLI's `--checkpointer-db` flag pass `force_rebuild=True` to bust it.

## Tradeoffs

| Gain | Cost |
|---|---|
| 80 ms compile cost paid once per worker, not per invocation | Adds two lines of cache-management state at module level (`_COMPILED`, `_COMPILED_KEY`) |
| `--checkpointer-db` CLI flag works correctly — tests can swap checkpointers | Test authors must remember to pass `force_rebuild=True` when swapping checkpointers; failure mode is a silent stale-graph reuse |
| Phase 9's worker model (long-lived process, many `ainvoke()`s) gets the win for free | Module-level mutable state is a code-smell future readers must understand before refactoring |
| The `_COMPILED_KEY` tuple makes the cache-miss condition explicit, so two checkpointers can coexist if the test runner reuses the worker | The `id()` of a checkpointer is not value-equality; a logically-equivalent fresh checkpointer triggers a recompile even when it didn't need to |

## Consequences

- The factory pattern is **the integration seam Phase 7 and Phase 8 build on.** Phase 7's `build_distroless_loop()` ships as a sibling factory in the same package; Phase 8's supervisor dispatches on `task_type` and calls one factory or the other. No factory shape, no clean Phase-7 "extension by addition."
- `tests/graph/conftest.py` carries a docstring explaining the `force_rebuild=True` discipline; the fixture `compiled_graph_for_test` always sets it.
- `tests/graph/test_compile_cache_uses_force_rebuild.py` is the canary that the cache busts when expected (`phase-arch-design.md §Edge cases #14`).
- A non-conforming `BaseCheckpointSaver` subclass surfaces as a `compile()` error at graph-build time, not at first invocation — failing loud (`phase-arch-design.md §Edge cases #13`).
- Phase 9's Postgres swap (`make_checkpointer(...)`) does not affect this ADR — the factory still owns the compile cache; only the checkpointer instance changes.
- A future engineer who introduces a third constructor parameter must add it to `_COMPILED_KEY` or risk silent stale-cache hits.

## Reversibility

**High.** The factory is one Python file; reverting to per-invocation compile is deleting `_COMPILED` and `_COMPILED_KEY` and removing the `force_rebuild` parameter. Moving in the *other* direction (toward a module-level constant) is harder — it requires re-auditing every test and the CLI `--checkpointer-db` flag — but the lazy singleton is the strict generalization, so the choice itself is cheap to undo.

## Evidence / sources

- [`../final-design.md` §Component 2 "build_vuln_loop()"](../final-design.md)
- [`../final-design.md` §Synthesis ledger row 7 "Module-level vs per-invocation"](../final-design.md)
- [`../phase-arch-design.md` §Component design — `build_vuln_loop()`](../phase-arch-design.md)
- [`../critique.md` §performance.4](../critique.md) — the contradiction that forced the synthesis
- [Production ADR-0002](../../../production/adrs/0002-langgraph-as-runtime-sherpa-as-discipline.md) — "use LangGraph's mature tooling for free" mandates the factory shape
