# ADR-0031: Plugin architecture — granular (task × language × build-tool) units of work

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** architecture · plugins · extension-by-addition · task-class
**Related:** ADR-0007, ADR-0010, ADR-0028, ADR-0029, ADR-0030

## Context

Earlier ADRs introduced task classes as the unit of "what kind of work the system does" — vulnerability remediation (ADR-0028), distroless migration (Phase 7 of the roadmap), library upgrades and language upgrades (future). Each task class had its own LangGraph subgraph (`design.md §4.1`), its own TCCM ([ADR-0029](0029-task-class-context-manifests.md)), and its own set of probes that contribute to the gathered `RepoContext`.

But task class is only one axis of variation. Real workflows differ on at least two more:

- **Language.** Java vulnerability remediation works against `pom.xml` or `build.gradle`, uses Maven Central / GitHub Packages, and resolves through Maven coordinates. Node.js vulnerability remediation works against `package.json`, uses npm / GitHub Packages, and resolves through semver. The two share *intent* (bump a vulnerable transitive dep without breaking the build) but share almost nothing operationally.
- **Build tool / package manager.** Within Node.js alone, npm, Yarn Classic, Yarn Berry, and pnpm have substantively different dependency models — classic `node_modules` vs. Yarn Berry's `.pnp.cjs` Plug'n'Play resolution graph vs. pnpm's content-addressed store. A distroless migration for an npm-resolved app uses `npm ci` in the runner stage; for a Yarn-Berry-resolved app there is no `node_modules` to copy at all, and the runner stage may not need a node-version-specific base image. Java Maven (`mvn dependency:tree`, `pom.xml` parent inheritance, settings profiles) likewise differs sharply from Java Gradle (`build.gradle.kts`, dependency configurations, Gradle plugins).

Treating task class as the only granularity forces a single subgraph to internally branch on language and build tool — sprawling if/then chains, fragile to extend, hard to test. One subgraph per `(task × language × build-tool)` tuple without any structural composition concept makes the codebase grow linearly with the matrix size, with shared distroless or vuln-remediation patterns duplicated across every combination.

The system needs a **plugin architecture**: a declarative bundle that captures one specific `(task × language × build-tool)` combination's behavior, including probes, TCCM, subgraph, skills, and recipes — with composition rules so common patterns aren't duplicated.

## Options considered

- **Option A — single subgraph per task class; internal branching on language/build-tool.** Today's design taken to its logical conclusion. Fast to start; quickly bloats into untestable if/then chains. Adding a new build tool means editing every relevant subgraph file — violates extension-by-addition.
- **Option B — one subgraph per (task × language × build-tool) tuple; no structural composition.** Each tuple gets its own hardcoded subgraph. Clear separation; massive duplication of shared distroless / vuln patterns. Codebase grows linearly with matrix size.
- **Option C — plugin architecture with scope tuple and inheritance.** Each plugin declares its scope (`task × language × build-tool`, with `*` wildcards allowed) and contributes probes, a TCCM, a subgraph, skills, and recipes. Plugins compose via an `extends` field so a Yarn-Berry-specific plugin inherits the base Node.js plugin and overrides only what's actually different. The Supervisor resolves which plugin applies to a workflow by matching the workflow's task class against the repo's gathered languages and build tools, choosing the most-specific plugin and walking the inheritance chain for shared contributions.

## Decision

**Adopt Option C — plugin architecture.**

### Plugin scope tuple

Three dimensions:

1. **Task class** — vulnerability-remediation, distroless-migration, container-layer-vulnerability, library-upgrade, language-upgrade, ...
2. **Language** — node, java, python, go, ruby, dotnet, ...
3. **Build tool / package manager** — npm, yarn-classic, yarn-berry, pnpm, maven, gradle, pip, poetry, uv, sbt, ...

Any dimension may be `*` (wildcard, "applies to all"). The most specific match wins (concrete dimensions beat wildcards). Equal-specificity ties are broken by an explicit `precedence` field in the plugin manifest.

### Plugin directory layout

```
plugins/{task-class}--{language}--{build-tool}/
├── plugin.yaml          # scope, version, contributions, requirements
├── tccm.yaml            # task-class context manifest (ADR-0029)
├── probes/              # probe implementations (ADR-0007 contract preserved)
├── adapters/            # language search adapters (ADR-0032)
├── subgraph/            # LangGraph state machine
├── skills/              # YAML-frontmatter skill files
├── recipes/             # deterministic transforms (OpenRewrite, AST, hand-rolled)
└── adrs/                # plugin-local design records (optional)
```

Example concrete plugins:

```
plugins/vulnerability-remediation--node--npm/
plugins/vulnerability-remediation--node--yarn-berry/
plugins/vulnerability-remediation--java--maven/
plugins/vulnerability-remediation--java--gradle/
plugins/distroless-migration--node--npm/
plugins/distroless-migration--node--yarn-berry/
plugins/distroless-migration--java--maven/
plugins/library-upgrade--python--poetry/
```

And base plugins with wildcards (parents for inheritance):

```
plugins/vulnerability-remediation--node--*/        # base for any Node vuln plugin
plugins/vulnerability-remediation--*--*/           # universal base (orchestration shell)
```

### Plugin manifest (`plugin.yaml`)

```yaml
name: vulnerability-remediation--node--yarn-berry
version: 0.1.0
scope:
  task_class: vulnerability-remediation
  languages: [typescript, javascript]
  build_systems: [yarn-berry]

extends:
  - vulnerability-remediation--node--*    # inherits common Node vuln behavior

contributes:
  probes:
    - YarnBerryPnpResolverProbe
    - YarnBerryConstraintsProbe
  adapters:                                                  # language search adapters (ADR-0032)
    dep_graph: adapters.yarn_berry_dep_graph:YarnBerryDepGraphAdapter
    import_graph: adapters.node_import_graph:NodeImportGraphAdapter
    scip: adapters.node_scip:NodeScipAdapter
    test_inventory: adapters.jest_inventory:JestTestInventoryAdapter
  tccm: ./tccm.yaml
  subgraph: ./subgraph/
  skills: ./skills/
  recipes: ./recipes/

requirements:
  external_tools:
    - yarn    # CLI must be in $PATH at runtime
  optional:
    - corepack

precedence: 100    # higher than parent (default 50) — wins on equal-specificity match
```

### Discovery and resolution

The Supervisor's plugin-resolution flow (one of the `conditional_edges` out of the Supervisor node, per `design.md §4.1`):

1. Read workflow's task class (e.g., `vulnerability-remediation`)
2. Read `RepoContext.languages` (the gathered language inventory)
3. Read `RepoContext.build_systems` (the gathered build-tool inventory)
4. Match against the plugin registry: find every plugin whose scope is compatible (exact match, or `*` for the dimension)
5. Order candidates by specificity (concrete > wildcard) then by `precedence` field
6. Pick the top candidate as the "primary" plugin
7. Walk the `extends` chain to collect inherited contributions (TCCM entries, probes, skills, recipes) — child overrides parent on name collision
8. Drop the workflow payload into the primary plugin's subgraph, with the resolved Context Bundle as initial state

### Inheritance and override

A plugin's `extends` field is a **list of parent plugins**, evaluated left-to-right. The child plugin is conceptually appended at the end of the list for resolution purposes. **Later entries in the list win on name collision** — this gives a deterministic resolution order even when a plugin extends multiple parents (e.g., `extends: [vulnerability-remediation--node--*, "*--*--yarn-berry"]` inherits Node-base vuln behavior AND Yarn-Berry resolution behavior; the Yarn Berry parent wins on overlapping names because it appears later, and the child wins over both because it is conceptually last).

Inheritance applies to:

- **TCCM entries** — child's `must_read` / `should_read` / `may_read` extend parents'; same-name entries resolve per the list-order rule above
- **Skills** — union; list-order resolution on name collision
- **Recipes** — union; list-order resolution on name collision
- **Probes** — union (a child requiring a probe a parent already required is idempotent)
- **Adapters** — per-primitive override; the latest registration for each primitive interface wins ([ADR-0032](0032-language-search-adapters.md))
- **Subgraph** — **NOT inherited.** Each plugin owns its own subgraph topology. Subgraphs may share nodes via Python imports, but the graph topology is per-plugin.

The subgraph exclusion is deliberate: graph topology is the most behavioral piece of a plugin, and surprise behavior from invisible inheritance would be hard to debug. Topology must be explicit; reuse happens at the node level via shared Python modules, not at the graph level via implicit composition.

### Probes stay scope-agnostic

Existing probes (the [ADR-0007](0007-probe-contract-preserved-poc-to-service.md) contract) do **not** know about plugins. They continue declaring `applies_to_tasks` and `applies_to_languages` as before. Plugins declare in `plugin.yaml` which probes they require; the Coordinator unions probe requirements across all candidate plugins for the repo and runs that set during gather. The probe contract is unchanged; the consumer-side declaration is the new piece.

This means plugin-introduced probes can write task-and-build-tool-specific slices into `RepoContext` — a Yarn Berry plugin's `YarnBerryPnpResolverProbe` writes a `pnp_resolution` slice that only repos in scope of that plugin will ever have; a Maven plugin's `MavenEffectivePomProbe` writes an `effective_pom` slice. The Bundle Builder (ADR-0029, ADR-0030) only sees slices that exist; missing slices are absence, not errors.

### Language search adapters

The query primitives that TCCMs use ([ADR-0030](0030-graph-aware-context-queries.md)) — `scip.refs`, `import_graph.reverse_lookup`, `dep_graph.consumers`, `test_inventory.tests_exercising`, `import_graph.transitive_callers` — are language-agnostic *interfaces*. Their implementations are deeply language-specific: `dep_graph.consumers` for Maven parses `pom.xml` and the effective POM; for npm it walks `package-lock.json`; for Poetry it reads `poetry.lock`. Plugins provide these implementations via **language search adapters** at `plugins/{slug}/adapters/*.py`, registered in `plugin.yaml`'s `contributes.adapters` map. The Bundle Builder routes a primitive call to the adapter declared by the resolved plugin chain (later-in-`extends`-list wins per primitive). Adapters carry the language-specific code; TCCMs stay language-agnostic. The full adapter contract is specified in [ADR-0032](0032-language-search-adapters.md).

### Schema enforcement and validation

Plugin manifests are typed: `plugin.yaml` and `tccm.yaml` are validated against **Pydantic models** at Supervisor startup. A malformed plugin (missing required field, wrong type, unknown contribution category, unresolvable adapter import path) fails fast with a clear diagnostic naming the file and the field. The Supervisor refuses to start if any plugin fails validation — partial-load is never silent. This matches the Pydantic state-ledger discipline used elsewhere in the architecture (`design.md §4.2`) and the schema-validation gate on `RepoContext` itself ([`localv2.md` §5](../../localv2.md)). A separate fast-fail check at plugin load resolves the `contributes.adapters` import paths — broken imports surface at startup, never at workflow time.

### No-match fallback

The plugin registry MUST include a universal `(*, *, *)` fallback plugin that matches any workflow on any repo. Its subgraph is the **HITL escalation flow**: emit a `requires_human_review` event with the workflow context attached, write to the audit log, and `interrupt()` for human triage. "No specific plugin matches" is never a silent failure — every workflow has a known handler. The universal fallback carries the lowest `precedence` value in the registry; any concrete plugin beats it on the resolution order. The fallback plugin is itself added by addition (it ships as `plugins/universal--*--*/` and is loaded by the same mechanism as every other plugin) — it is not a special case in the Supervisor's code path.

## Tradeoffs

| Gain | Cost |
|---|---|
| Real granularity matches real-world differences — Yarn Berry IS substantively different from npm; Maven IS substantively different from Gradle | Plugin registry needs a matcher with wildcard fallback and precedence rules — more complexity in dispatch |
| New language or new build tool = add a plugin; existing plugins untouched (extension-by-addition preserved per ADR-0028) | Plugin authoring is more involved than authoring just a TCCM or a probe — onboarding cost for plugin authors |
| Plugins are self-contained and team-ownable — Java team authors Java plugins independently of Node team | Cross-plugin coordination is needed for shared concerns (e.g., a new task class introduced across N language/build-tool combinations is N plugins, not 1) |
| Codebase scales sub-linearly with matrix size — inheritance avoids duplication of shared distroless / vuln-remediation patterns | Inheritance introduces resolution complexity; debugging "why did this plugin behave this way" requires walking the `extends` chain |
| Stage 7 Learning telemetry now keyed by `(task, language, build-tool)` — per-tuple ROI becomes measurable | Telemetry surface grows; cost-attribution model (ADR-0027) needs an `(language, build_tool)` partition |
| `RepoContext` can include language-stack-specific or build-tool-specific slices because plugins declare probe requirements | RepoContext schema grows over time as plugins add probes; schema-version discipline must be tight |
| **In-tree-only at adoption** keeps versioning trivial (single version per plugin, recorded for audit) and discovery a filesystem walk | Out-of-tree pip-installable plugins (with semver-range `extends` resolution, multi-version coexistence, third-party authoring) are a deliberate v2 deferral — see Consequences |

## Consequences

- **ADR-0028 (task class introduction order) generalizes.** "Task class added by addition" becomes "plugin added by addition." Ordering still applies — vulnerability remediation plugins ship before distroless migration plugins — but each task class can have multiple plugins introduced over time as more languages and build tools come online.
- **ADR-0029 (TCCMs) lives inside plugins.** A TCCM is one of a plugin's contributions, not a top-level concept. The `task-class-contexts/` location described in ADR-0029's initial draft becomes `plugins/{plugin-id}/tccm.yaml` — moved into the plugin bundle for cohesion.
- **The Supervisor's dispatch (`design.md §4.1`) is now plugin-aware.** The `conditional_edge` after the routing decision drops the payload into the resolved plugin's subgraph, with the inherited+composed TCCM already built into a Context Bundle.
- **Phase 3 of the roadmap (first vuln remediation, deterministic recipe path) becomes "author `vulnerability-remediation--node--npm`."** The first plugin doubles as the proof that the plugin loader works.
- **Phase 7 (first distroless migration, extension-by-addition test) becomes "author `distroless-migration--node--npm`."** The test of extension-by-addition is now concrete: adding this plugin requires zero edits to any file outside `plugins/distroless-migration--node--npm/`.
- **Plugin versions are recorded in the cost ledger and the workflow audit log.** A workflow records which plugin (and which version) handled it, so reproducibility survives across plugin updates.
- **The probe-contract change is purely additive.** ADR-0007 says the probe contract is preserved POC→service; plugins consume that contract without changing it. The `applies_to_build_systems` axis lives in plugin manifests, not in probe declarations.
- **Out-of-tree pip-installable plugins are a v2 direction, not v1.** All plugins ship in-tree under `plugins/` at adoption. Out-of-tree distribution (via Python entry-points, with semver-range `extends` resolution and multi-version coexistence) becomes relevant once the matrix passes ~15 plugins authored by ≥2 teams, or once customer-driven third-party plugin demand emerges. Until either trigger fires, in-tree-only keeps versioning, discovery, and review trivial.

## Reversibility

**Medium-high.** Plugins are largely declarative wrappers around concepts that already exist (subgraphs, probes, TCCMs, skills, recipes). Collapsing the plugin layer would require hardcoding the `(task × language × build-tool) → subgraph` mapping in the Supervisor and inlining each plugin's TCCM / probe-requirements / subgraph at the call site. Feasible but loses the extension-by-addition property and the team-ownability story. A reverse-direction migration (re-introducing plugins after they were removed) would be straightforward because the underlying artifacts (subgraphs, probes, TCCMs) survive.

## Evidence / sources

- ADR-0007 — probe contract preserved POC→service (plugins consume the contract; probes themselves don't change)
- ADR-0010 — seven-stage pipeline (plugins contribute at Stage 2 gather, Stage 3 planning, Stage 4 execution)
- ADR-0028 — task class introduction order (this ADR generalizes the principle to the full scope tuple)
- ADR-0029 — TCCMs (now live inside plugins)
- ADR-0030 — graph-aware context queries (plugin TCCMs use these primitives)
- [`../../localv2.md` §4](../../localv2.md) — probe contract that plugins consume
- [`../../localv2.md` §10](../../localv2.md) — skills as YAML-frontmatter data (plugins contribute skills)
- `CLAUDE.md` load-bearing commitments — "Extension by addition", "Organizational uniqueness as data, not prompts"
