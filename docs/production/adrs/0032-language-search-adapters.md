# ADR-0032: Language search adapters — bridging generic queries to language-specific indexers

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** adapters · code-search · scip · tree-sitter · plugins
**Related:** ADR-0007, ADR-0029, ADR-0030, ADR-0031

## Context

[ADR-0030](0030-graph-aware-context-queries.md) introduced query primitives that TCCMs use to compute affected file sets — `scip.refs`, `import_graph.reverse_lookup`, `import_graph.transitive_callers`, `dep_graph.consumers`, `test_inventory.tests_exercising`. [ADR-0031](0031-plugin-architecture.md) introduced plugins as the bundle for `(task × language × build-tool)` work, contributing probes, TCCMs, subgraphs, skills, and recipes.

These ADRs leave a gap: the primitives are **language-agnostic interfaces** but their implementations are deeply language-specific. A few examples make the gap concrete:

| Primitive | Maven implementation | npm implementation | Poetry implementation |
|---|---|---|---|
| `dep_graph.consumers(package)` | parse effective POM; resolve via Maven coordinates | walk `package-lock.json`'s semver tree | walk `poetry.lock`'s resolved graph |
| `import_graph.reverse_lookup(module)` | tree-sitter-java + classpath walking | tree-sitter-typescript + `tsconfig` path resolution | tree-sitter-python + `sys.path` resolution |
| `scip.refs(symbol)` | `scip-java` indexer output | `scip-typescript` indexer output | `scip-python` (pyright-based) indexer output |
| `test_inventory.tests_exercising(file_set)` | JUnit/TestNG discovery via Maven Surefire | jest/vitest config parsing | pytest collection |

A plugin doesn't just *use* these primitives — for its language stack, it **provides the implementation that makes them work**. That implementation is what this ADR calls a **language search adapter**: a small Python module wrapping a language-specific indexer with the generic primitive interface from ADR-0030. Without this layer, either every primitive has a giant switch statement on `repo_context.language` (Option A below — fragile and centralizing), or every plugin reimplements all primitives from scratch (Option B below — duplication, no shared interface).

The architecture needs a third layer that sits between ADR-0030 (interfaces) and ADR-0031 (plugin bundle): a contract that says "to support a new language stack, implement these adapter Protocols and register them in your plugin manifest."

## Options considered

- **Option A — inline language switching inside each primitive's implementation.** `dep_graph.consumers` becomes a giant `match` on the repo's language. Single-file growth as new languages arrive; centralizes language knowledge in the wrong layer; violates extension-by-addition (adding a language edits the primitives).
- **Option B — each plugin reimplements all primitives.** TCCMs reference `MavenDepGraph.consumers(...)` and `NodeDepGraph.consumers(...)` directly. Lots of duplication; the generic primitives become decorative interfaces; TCCMs are no longer portable across plugins.
- **Option C — adapter contract.** Plugins contribute adapter modules that implement the generic primitive interfaces for one `(language, build-tool)` slice. A runtime dispatcher in the Bundle Builder routes primitive calls to the right adapter based on the resolved plugin chain.

## Decision

**Adopt Option C — language search adapter contract.**

Each plugin may contribute one or more adapters at `plugins/{slug}/adapters/*.py`. An adapter implements one or more of the generic primitive interfaces declared in this ADR, registered in `plugin.yaml`'s `contributes.adapters` map.

### Adapter Protocols

The primitive interfaces are typed as Python `Protocol` classes. Adapters are duck-typed implementations of these Protocols — no inheritance required, only structural conformance.

```python
from typing import Protocol

class DepGraphAdapter(Protocol):
    """Implements dep_graph.* primitives for one (language, build-tool) slice."""

    def consumers(self, package: PackageId) -> list[PackageId]:
        """Internal packages depending on `package` (package-level, not file-level)."""
        ...

    def confidence(self) -> float:
        """0.0 – 1.0; signals freshness of the underlying gathered facts."""
        ...


class ImportGraphAdapter(Protocol):
    """Implements import_graph.* primitives."""

    def reverse_lookup(self, module: str) -> list[FilePath]:
        """Files in the repo that import `module` directly."""
        ...

    def transitive_callers(self, file_set: list[FilePath], depth: int) -> list[FilePath]:
        """Files that import any file in `file_set` within `depth` hops."""
        ...

    def confidence(self) -> float: ...


class ScipAdapter(Protocol):
    """Implements scip.* primitives."""

    def refs(self, symbol: SymbolId) -> list[CodeLocation]:
        """Symbol-precise call sites (file:line:col)."""
        ...

    def confidence(self) -> float: ...


class TestInventoryAdapter(Protocol):
    """Implements test_inventory.* primitives."""

    def tests_exercising(self, file_set: list[FilePath]) -> list[TestName]:
        """Tests that exercise (directly or transitively) any file in `file_set`."""
        ...

    def confidence(self) -> float: ...
```

`confidence()` is mandatory across all adapters because it feeds the Bundle Builder's degradation logic (see "Graceful degradation" below).

### Plugin manifest registration

A plugin registers its adapters via `contributes.adapters`, mapping each primitive interface to a Python import path:

```yaml
# plugins/vulnerability-remediation--node--yarn-berry/plugin.yaml (excerpt)
contributes:
  adapters:
    dep_graph: adapters.yarn_berry_dep_graph:YarnBerryDepGraphAdapter
    import_graph: adapters.node_import_graph:NodeImportGraphAdapter
    scip: adapters.node_scip:NodeScipAdapter
    test_inventory: adapters.jest_inventory:JestTestInventoryAdapter
```

The Python import path is `module.submodule:ClassName`. The Bundle Builder imports each entry on plugin load, instantiates it, and stores it indexed by `(plugin_id, primitive_name)`.

### Dispatch

When the Bundle Builder evaluates a TCCM's derived query (e.g., `scip.refs(vulnerability.affected_symbols)`):

1. Identify the primitive interface name (`scip`)
2. Look up the resolved plugin chain (ADR-0031 resolution result) for an adapter registered for `scip`
3. Walk the chain in `extends` order; the last (most-specific) registration wins
4. Call the adapter's `refs(...)` method
5. Record the result and the adapter's `confidence()` in the Bundle's provenance log

### Graceful degradation

Adapters compete on a *precision/cost ladder* — SCIP is most precise but expensive and can be stale; tree-sitter is faster and always-fresh from probe output; dep graph is cheapest but coarsest. When a higher-precision adapter reports low confidence (e.g., SCIP index is stale, surfaced via [`IndexHealthProbe`](../../localv2.md) B2), the dispatcher falls back to a lower-precision adapter that can answer a similar question and logs the downgrade in the Bundle provenance.

The fallback chain is **declared, not hardcoded**: each TCCM derived query can list acceptable substitutions:

```yaml
must_read:
  derived:
    - name: affected_callsites
      compute: scip.refs(vulnerability.affected_symbols)
      fallback: import_graph.reverse_lookup(vulnerability.affected_module)  # when scip.confidence() < 0.7
      max_files: 30
```

If no fallback is declared and the primary adapter has low confidence, the Bundle Builder logs an explicit "low-confidence answer used" entry instead of silently substituting — the worker sees the confidence value and can decide whether to proceed.

### Adapter external requirements

Adapters often need external tools (`scip-java`, `scip-typescript`, `tree-sitter-java` grammars, Maven CLI, etc.). These get declared in the plugin manifest's `requirements.external_tools` field. The Coordinator checks tool availability at workflow start; missing tools either fail-fast or downgrade per the adapter's `confidence()` (e.g., a `JavaScipAdapter` whose `scip-java` is missing reports `confidence() == 0.0`).

## Tradeoffs

| Gain | Cost |
|---|---|
| New language = author ~4 adapters + a subgraph; the ADR-0030 primitives stay stable | Each new language needs a non-trivial implementation per adapter — onboarding a language is real work |
| TCCMs stay language-agnostic; portable across plugins because the primitive interfaces are universal | Adapter contract must stay backwards-compatible — adding a method to a Protocol can break existing plugins |
| Multiple languages in one repo work — adapters dispatched per dimension | Dispatch logic is non-trivial; needs tests for polyglot repos, missing adapters, low-confidence fallback |
| Graceful degradation via `confidence()` — SCIP-stale falls back to tree-sitter declaratively | TCCM authors must decide which fallbacks are acceptable per query; meta-cognitive load |
| Plugin authoring story is now a *small, named contract* — implement these Protocols and you've added a language | Multiple inheritance via `extends` interacts with adapter resolution (later-in-list wins per primitive) — debugging requires understanding the chain |

## Consequences

- **The Bundle Builder grows a per-primitive dispatcher** ([ADR-0029](0029-task-class-context-manifests.md), [ADR-0030](0030-graph-aware-context-queries.md) consumer side) that imports adapters lazily, indexes by primitive name, and applies degradation rules.
- **`IndexHealthProbe` (B2) — already load-bearing per CLAUDE.md — becomes the input that makes SCIP adapter degradation decisions.** A stale SCIP index surfaces as `ScipAdapter.confidence() < threshold`; the Bundle Builder uses the declared fallback or logs a low-confidence warning.
- **The plugin authoring guide gains a "minimum adapter surface" section.** A new language plugin must implement at least `ImportGraphAdapter` (everyone needs imports) and `TestInventoryAdapter` (test-exercising queries are universal); `DepGraphAdapter` is required when the task class touches dependencies (vuln, library-upgrade); `ScipAdapter` is optional but unlocks the most precise queries.
- **Cross-cutting "base" adapters can live at `(*, *, *)` wildcard plugins.** A universal `TreeSitterImportGraphAdapter` written generically over tree-sitter grammars could ship in the universal fallback plugin and be inherited by every language plugin until they override with something language-aware.
- **Adapter telemetry feeds Stage 7 Learning.** Per-primitive call counts, average latency, average confidence, fallback-trigger rate — all logged in the Bundle provenance and aggregated as part of the per-plugin ROI signal.
- **Schema evolution discipline.** Adapter Protocol changes are versioned. Adding a new method with a default implementation is non-breaking; removing or changing signatures requires an ADR amendment with a migration window.

## Reversibility

**Medium.** Adapters are an additive layer. Removing them would require inlining the dispatch in primitive implementations (Option A) and accepting the centralization. The migration would be expensive in proportion to the number of plugins that exist at removal time — each plugin's adapters would need to be merged into the inlined switch. Reverse migration (re-introducing adapters after they were removed) would require re-deriving adapter implementations from the inlined dispatch logic — feasible but lossy.

## Evidence / sources

- ADR-0007 — probe contract preserved POC→service (adapters consume probe output; they do not change the probe contract)
- ADR-0029 — TCCMs (adapter calls happen during Bundle Builder execution against TCCM derived queries)
- ADR-0030 — graph-aware context queries (the primitive interfaces this ADR makes implementable)
- ADR-0031 — plugin architecture (adapters are one of the contribution categories)
- [`../../localv2.md` §4](../../localv2.md) — probe contract that produces the facts adapters query
- [`../../localv2.md` §12](../../localv2.md) — SCIP, tree-sitter, depgraph probes ship in Phase 2; adapters wrap them starting Phase 3
- CLAUDE.md — "IndexHealthProbe is the single most important probe" (B2 confidence drives adapter degradation)
