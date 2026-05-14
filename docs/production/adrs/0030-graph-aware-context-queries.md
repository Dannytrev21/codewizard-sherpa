# ADR-0030: Graph-aware context queries — dep graph + tree-sitter + SCIP power TCCMs

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** context · graph-analysis · scip · tree-sitter · task-class
**Related:** ADR-0007, ADR-0010, ADR-0013, ADR-0029

## Context

[ADR-0029](0029-task-class-context-manifests.md) introduced Task-Class Context Manifests (TCCMs) as the consumer-side declaration of which `RepoContext` slices and filesystem globs each task class needs. The baseline primitives are:

- `repo_context_keys` — direct lookups into the gathered context
- `globs` — filesystem glob expansions
- `bootstrap_globs` — fallback when no `RepoContext` exists yet

These are sufficient for coarse selection ("read the lockfile and the package manifests") but fall short for the case that matters most in vulnerability remediation: a breaking-change library upgrade affects every call site of every affected API, plus every test exercising those call sites, plus possibly second-order callers if the upgrade ripples through internal abstractions.

A glob like `**/*.test.ts` pulls every test file in the repo — acceptable for small repos, catastrophic for large monorepos. The right set is much narrower (only the tests that actually exercise call sites of the affected module) and much wider than the glob can express (only the *affected* tests, not all tests). Globs cannot express "the set of files transitively reachable from a symbol reference."

The gather pipeline ([`../../localv2.md` §12](../../localv2.md)) already produces three structural-analysis artifacts that *can* answer this precisely:

- **Dependency graph** — parsed lockfile + manifest analysis, package-level edges
- **Tree-sitter parses** of every source file — file-level import edges
- **SCIP semantic index** — symbol-level references (file:line:col precise)

These differ in precision and cost. TCCMs need a way to compose them — without becoming a Turing-complete DSL.

## Options considered

- **Option A — globs only.** Keep TCCMs as in ADR-0029 baseline. Simple. Loses precision for the case that matters most. Fails on large monorepos where glob expansion blows the token budget on tests that have no path to the affected module.
- **Option B — inline graph queries in YAML.** Let TCCMs write arbitrary graph traversals as YAML expressions. Maximum power. Turns TCCMs into an effectively Turing-complete DSL — hard to author, hard to review, hard to test. Authoring quality drops; bugs become invisible.
- **Option C — named derived queries with bounded primitives.** TCCMs reference a small, fixed set of pre-defined query primitives — `reverse_lookup`, `scip.refs`, `tests_exercising`, `transitive_callers` — that the Bundle Builder knows how to execute against `RepoContext`'s structural artifacts. Each derived entry is bounded by `max_files`. The query language is small; the YAML stays declarative.

## Decision

**Adopt Option C — named derived queries.**

A TCCM may include a `derived` block in any priority band (`must_read`, `should_read`, `may_read`). Each derived entry declares:

- `name` — a human-readable handle, referenceable by later derived entries within the same TCCM
- `compute` — one of a small fixed set of query primitives, parameterized
- `max_files` — hard cap; the query truncates with provenance if exceeded
- optionally `depth` — for transitive queries

**Initial query primitives:**

| Primitive | Source artifact | Returns |
|---|---|---|
| `dep_graph.consumers(package)` | Lockfile + manifest parse | Internal packages that depend on `package` (package-level) |
| `import_graph.reverse_lookup(module)` | Tree-sitter import edges | Files that import `module` (file-level) |
| `import_graph.transitive_callers(file_set, depth=N)` | Tree-sitter import edges | Files that import any file in `file_set` within `depth` hops |
| `scip.refs(symbol)` | SCIP index | Exact call sites of `symbol` (file:line:col) |
| `test_inventory.tests_exercising(file_set)` | TestInventory probe output + import graph | Tests that exercise (directly or transitively) any file in `file_set` |

**Precision/cost ordering — TCCMs prefer the cheapest sufficient primitive:**

1. **Dep graph** — pennies per query; coarse (package-level)
2. **Tree-sitter import edges** — fast (~100ms across thousands of files); file-level
3. **SCIP refs** — slowest (single-digit seconds for a hot query); symbol-level, surgically precise

**Example — a CVE in `lodash@4.17.20`:**

```yaml
# task-class-contexts/vulnerability-remediation.yaml (excerpt)
must_read:
  derived:
    - name: affected_callsites
      compute: scip.refs(vulnerability.affected_symbols)
      max_files: 30
    - name: direct_importers
      compute: import_graph.reverse_lookup(vulnerability.affected_module)
      max_files: 50

should_read:
  derived:
    - name: tests_for_importers
      compute: test_inventory.tests_exercising(direct_importers)
      max_files: 100
    - name: one_hop_callers
      compute: import_graph.transitive_callers(direct_importers, depth=1)
      max_files: 100

may_read:
  derived:
    - name: deep_transitive_callers
      compute: import_graph.transitive_callers(direct_importers, depth=3)
      max_files: 200
```

This is operationally what "cast a larger net, bounded" looks like: SCIP-precise call sites always load (`must_read`); the wider tree-sitter file-level net loads if budget allows (`should_read`); the paranoid two-to-three-hop set is only fetched on explicit request from a worker node mid-execution (`may_read`).

## Tradeoffs

| Gain | Cost |
|---|---|
| Tight `must_read` — only the files the upgrade actually touches at the symbol level (no whole-test-suite globbing) | Requires SCIP to be fresh; `IndexHealthProbe` (B2 — single most important probe per CLAUDE.md) becomes load-bearing for query quality |
| Wide-but-bounded `should_read` — catches the cases SCIP missed (dynamic dispatch, codegen, runtime reflection) | One more layer of complexity in the Bundle Builder; query implementations need testing |
| Same TCCM works regardless of repo size — globs scale with repo size, derived queries scale with the affected subgraph | Query primitives form a small DSL; adding a new primitive requires Bundle Builder code change (mitigation: keep the primitive set small and stable; most needs compose from existing primitives) |
| TCCM authors pick the cheapest primitive that gives sufficient precision (dep graph → tree-sitter → SCIP) | Authoring quality TCCMs requires understanding the precision/cost ladder; documentation must be explicit |
| Bundle provenance now records per-query results — auditable when an agent missed something | Telemetry surface grows; Stage 7 Learning ingests more per-query signal |

## Consequences

- **`IndexHealthProbe` (B2) becomes load-bearing for context quality.** If SCIP is stale, `scip.refs` returns wrong call sites and the Bundle is wrong. The probe's confidence rating gates whether SCIP-derived queries are used; if confidence is low, the Bundle Builder falls back to tree-sitter-only with a logged downgrade and a Stage 7 telemetry entry.
- **Stage 7 Learning telemetry now covers query-level usefulness.** Did the worker consult any of the `should_read` derived files? Did it need to request a `may_read` promotion? Per-query consumption data tunes TCCMs over time — `should_read` items that are never consulted move to `may_read`; `may_read` items that get promoted often move up to `should_read`.
- **New query primitives are additive.** Adding `git_blame.recent_authors(file_set)` or `runtime_trace.hot_paths_using(symbol)` later doesn't break existing TCCMs — they just don't reference the new primitive.
- **The query DSL stays small and stable.** Five primitives at adoption. Additions require an ADR amendment, not a YAML free-for-all.
- **Bundle provenance includes per-query results.** The audit log records "`affected_callsites` returned 12 files, all included; `tests_for_importers` returned 87 files, 32 included, 55 deferred (budget cap)". An engineer reviewing why an agent missed something traces it to a specific query's truncation.
- **TCCM authoring becomes a probe-aware exercise.** TCCM authors need to know which structural probes have shipped and what they expose. This is fine — the same author needs to know which `RepoContext` keys exist, and the discipline is the same.

## Reversibility

**Medium.** Removing derived queries reverts TCCMs to globs-only — slow on large repos but functional. Re-introducing them after removal would need to rebuild query implementations against whatever structural artifacts the gather pipeline emits at that time. The structural artifacts themselves are stable (probe contract is preserved per ADR-0007), so the query implementations are the moving piece.

## Evidence / sources

- ADR-0029 — TCCMs (this ADR extends its primitive set)
- ADR-0007 — probe contract preserved POC→service (dep-graph / tree-sitter / SCIP probes are part of the contract this ADR consumes)
- ADR-0010 — seven-stage pipeline (Stage 3 Planning operates on the Bundle this ADR helps build)
- ADR-0013 — pre-rendered hot views (frequent derived-query results are cacheable in the same hot-views infrastructure)
- [`../../localv2.md` §12](../../localv2.md) — dep graph, tree-sitter, SCIP probes are scoped for Phase 1–2 of the roadmap
- CLAUDE.md load-bearing commitments — `IndexHealthProbe` (B2) is "the single most important probe because silent index staleness is the worst failure mode"
