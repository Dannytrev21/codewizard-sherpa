# Phase 03 — Vuln remediation: deterministic recipe path: Best-practices design

**Lens:** Best practices — idiomatic, maintainable, conventional, well-tested.
**Designed by:** Best-practices design subagent
**Date:** 2026-05-15

## Lens summary

Phase 3 ships the first plugin (`plugins/vulnerability-remediation--node--npm/`), the universal HITL fallback (`plugins/universal--*--*/`), the plugin loader/resolver kernel that ADR-0031 mandates, the four ADR-0032 adapter implementations wrapping the Phase 2 structural probes, the TCCM Pydantic model from ADR-0029, and a deterministic transform engine that bumps a vulnerable npm package on a local branch — **no LLM anywhere**. The whole phase is, fundamentally, a contract-defining act: every line of code that ships now becomes the shape every future plugin must wear (Phase 7 distroless migration; Phase 15 agentic recipe authoring). The best-practices lens optimizes for **shape over flash**: the tiniest plausible public surface, the boring-est plausible registration pattern (mirror `@register_probe` exactly), the most idiomatic Python (Pydantic v2 discriminated unions, `typing.Protocol`, `typing.NewType`, `match` + `assert_never`), and the most reviewable plugin directory layout. We explicitly deprioritize: peak per-recipe performance (an extra subprocess per CVE is acceptable), peak isolation security (real microVM is Phase 5; Phase 3 runs inside a subprocess with constrained env), and clever transforms (OpenRewrite YAML adapters are deferred — `npm-check-updates` is the boring tool that solves 90% of cases at adoption). We refuse all *premature pluggability* (one recipe family, one resolver, one CVE-feed parser — no hooks "for the future"). Every domain primitive becomes a `NewType`; every state machine becomes a tagged union; every cross-module boundary becomes a `Protocol`. The phase's value, measured in maintainability, is the *uniformity of the plugin contract* that Phase 7 inherits unmodified.

## Conventions honored

- **No LLM in the gather pipeline → and now: no LLM in the deterministic transform path either.** `import_linter` (Phase 0) is extended with a new contract forbidding `anthropic`, `openai`, `langchain`, `langgraph` imports under `plugins/vulnerability-remediation--node--npm/`. The CI gate is identical to the gather-side check; one new entry in `pyproject.toml`. ([ADR-0005](../../production/adrs/0005-no-llm-in-gather-pipeline.md), `production/design.md §2.1`.)
- **Facts, not judgments.** The plugin writes a *patch diff and a CVE-resolution event*, never "the bump is safe to merge." A `RecipeOutcome` sum type carries `Applied(diff, lockfile_changes) | Skipped(reason) | NotApplicable(why) | Failed(error)`. No `safe: bool`, no `recommended: bool`, no string-typed verdicts. The Planner (Phase 8) consumes the typed outcome; humans merge (commitment §2.8).
- **Honest confidence.** Each adapter reports `AdapterConfidence` (sum type: `Trusted | Degraded(reason) | Unavailable(reason)`). The plugin's TCCM declares `fallback` chains so SCIP-stale degrades to tree-sitter declaratively (ADR-0032). Plugin resolution emits `PluginResolved` events carrying the full `extends_chain` and whether the universal fallback was used (ADR-0034).
- **Determinism over probabilism.** The recipe engine is fully deterministic: same `(repo_snapshot, cve_record, recipe_version)` → same diff bytes. Property test asserts it. ([ADR-0011](../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) recipe-first; the LLM-fallback branch is Phase 4 territory.)
- **Extension by addition.** Phase 3 ships *one plugin and the loader*. Phase 7 ships *one plugin and zero loader edits*. The loader is closed for modification (Open/Closed); plugin authors add files, never edit kernel code. A CI fence forbids any change to `src/codegenie/plugins/loader.py`, `src/codegenie/plugins/resolver.py`, or the universal fallback once they pass review — touching them requires a Phase-3-amendment ADR.
- **Organizational uniqueness as data, not prompts.** The plugin's TCCM (`plugins/vulnerability-remediation--node--npm/tccm.yaml`), skills (YAML frontmatter under `plugins/.../skills/`), and recipe inventory (`plugins/.../recipes/manifest.yaml`) are all data files. Zero hardcoded business rules in Python. ([ADR-0029](../../production/adrs/0029-task-class-context-manifests.md), `production/design.md §2.6`.)
- **Progressive disclosure.** The TCCM's three priority bands (`must_read` / `should_read` / `may_read`) are honored verbatim; the Bundle Builder emits a typed `Bundle` whose payload references rather than inlines large slices (lockfile path + hash, not full lockfile contents). ([ADR-0029.](../../production/adrs/0029-task-class-context-manifests.md))
- **Humans always merge.** The plugin's terminal node is `WriteLocalBranch`, never `OpenPR` (Phase 11). The universal fallback emits a `RequiresHumanReview` event and `interrupt()`s. ([ADR-0009](../../production/adrs/0009-humans-always-merge.md).)
- **Domain modeling discipline.** Every identifier (`PluginId`, `RecipeId`, `CVEId`, `PackageName`, `SemverRange`, `LockfileHash`, `BranchName`, `BundleId`, `AdapterId`, `CVSSScore`) is a `NewType` or Pydantic wrapper; every state machine (`RecipeOutcome`, `PluginResolution`, `InstallOutcome`, `AdapterConfidence`, `RecipeKind`) is a Pydantic discriminated union; every `bool`-coded state is rejected at review. ([ADR-0033](../../production/adrs/0033-domain-modeling-discipline.md).)
- **Event sourcing canonical primitive.** Phase 3 emits typed Pydantic events to an **append-only JSONL** at `.codegenie/events/<workflow-id>.jsonl` — Phase 9 graduates the store to Postgres without changing event types. The events are the same Pydantic models Phase 9 will ingest; only the writer changes. ([ADR-0034](../../production/adrs/0034-event-sourcing-canonical-primitive.md).)
- **Probe contract preserved.** Plugins consume probes via the language search adapters; the `Probe` ABC, `ProbeRegistry`, `Coordinator`, and `ProbeContext` are all *frozen Phase 0/1/2 surfaces*. Zero in-place edits. ([ADR-0007](../../production/adrs/0007-probe-contract-preserved-poc-to-service.md).)

## Goals (concrete, measurable)

- **Public API surface (count):** `src/codegenie/plugins/` exports ≤ **8 names**: `register_plugin`, `PluginRegistry`, `default_registry`, `Plugin`, `PluginManifest`, `PluginScope`, `PluginResolution`, `resolve_plugin`. The plugin's `vulnerability_remediation_node_npm.api` exports ≤ **4 names**: `run`, `TCCM`, `subgraph`, `manifest`. The universal fallback exports ≤ **2 names**: `run`, `manifest`.
- **Test coverage target:** 90% line / 80% branch on `src/codegenie/plugins/`, 90% line / 85% branch on `plugins/vulnerability-remediation--node--npm/`, 95% line on `plugins/universal--*--*/` (it is tiny and load-bearing).
- **Cyclomatic complexity ceiling:** 8 per function (`ruff C901`), already the project floor.
- **Number of net-new top-level packages:** **2** under `src/codegenie/` (`plugins/`, `transforms/`) + **2** new top-level repo directories (`plugins/`, `cve_feeds/` for parsers). No other top-level additions.
- **Lines of plain Python vs framework-coupled code:** target ratio **~85:15** (most of the plugin is pure data → diff functions; the only framework-coupled code is the LangGraph subgraph wiring, which Phase 6 fleshed out the runtime for).
- **Plugin manifest schema discipline:** Pydantic v2 model, `extra="forbid"`, `frozen=True` on all wire variants. JSON schema generated for documentation, not as a parallel source of truth.
- **Zero new external Python deps for the kernel.** Plugin uses `nodesemver` (mature MIT-licensed semver parser; ~1k LOC, 8 deps, used in the wild) and `npm-check-updates` (Node CLI; via `run_external_cli`). The CVE parsers use stdlib `json` + `pyyaml` (already pinned).
- **Wall-clock advisory:** plugin resolution ≤ 50ms p95 (it's a filesystem walk + Pydantic load + dict ops); first-CVE end-to-end on a fixture ≤ 8s warm (`npm install` dominates).
- **Phase 6.5 replay compatibility:** every plugin run emits a `BenchReplayable` event carrying the full input snapshot fingerprint + the produced diff bytes — Phase 6.5 lifts 10 cases into `bench/vuln-remediation/cases/` mechanically from this event stream.

## Architecture

```
                              ┌──────────────────────────────────────────────┐
                              │   src/codegenie/  — kernel (Phase 0/1/2 frozen)
                              │   + Phase 3 additions only at the boundary    │
                              └──────────────────────────────────────────────┘
                                              │
                                              │ import (one direction only)
                                              ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  src/codegenie/plugins/                            (NEW — Phase 3)   │
   │  ────────────────────────────────────────────────────────────────────│
   │  loader.py     — filesystem walk → list[Plugin]                      │
   │  registry.py   — @register_plugin decorator + dict + collisions      │
   │  manifest.py   — PluginManifest (Pydantic discriminated union)       │
   │  scope.py      — PluginScope newtype-rich tuple + match algebra      │
   │  resolver.py   — (task, lang, build) → PluginResolution (sum type)   │
   │  bundle.py     — TCCM → Bundle (calls adapters; honors fallback)     │
   │  events.py     — Pydantic event types (PluginResolved, …)            │
   │  fallback.py   — universal-fallback loader rules; tiny               │
   │  errors.py     — typed exceptions (one per failure variant)          │
   │  protocols.py  — Plugin Protocol + the four adapter Protocols re-exported
   └──────────────────────────────────────────────────────────────────────┘
                                              │
                                              │ loader walks `plugins/` at startup
                                              ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  plugins/                                            (NEW — Phase 3) │
   │  ────────────────────────────────────────────────────────────────────│
   │  universal--*--*/                  ←  the (*,*,*) HITL fallback      │
   │    plugin.yaml                       precedence: 0 (lowest)          │
   │    subgraph/__init__.py              one node: emit + interrupt()    │
   │    tccm.yaml                         must_read: workflow_summary     │
   │    api.py                            run(state) -> RequiresHumanReview
   │                                                                      │
   │  vulnerability-remediation--node--npm/                               │
   │    plugin.yaml                       precedence: 100                 │
   │    tccm.yaml                         must_read: lockfile, manifest…  │
   │    probes/                           (none new — uses Phase 1/2)     │
   │    adapters/                                                         │
   │      npm_dep_graph.py                NpmDepGraphAdapter              │
   │      node_import_graph.py            NodeImportGraphAdapter          │
   │      node_scip.py                    NodeScipAdapter                 │
   │      jest_inventory.py               JestTestInventoryAdapter        │
   │    subgraph/                                                         │
   │      __init__.py                     build_subgraph() — LangGraph    │
   │      nodes.py                        match_recipe, apply, install…   │
   │    recipes/                                                          │
   │      manifest.yaml                   recipe inventory                │
   │      ncu_bump.py                     NcuBumpRecipe (the workhorse)   │
   │      direct_dep_pin.py               DirectDepPinRecipe              │
   │    skills/                                                           │
   │      npm_audit_fix.md                YAML-frontmatter Skill          │
   │    cve_feeds/                                                        │
   │      nvd.py / ghsa.py / osv.py       — parsers, pure functions       │
   │    api.py                            run(state) -> RecipeOutcome     │
   └──────────────────────────────────────────────────────────────────────┘
                                              │
                                              │ emits to
                                              ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  .codegenie/events/<workflow-id>.jsonl   (NEW — Phase 3 anchor)      │
   │  one Pydantic-typed event per line; Phase 9 graduates to Postgres    │
   └──────────────────────────────────────────────────────────────────────┘
```

The relationship is *one direction*: `src/codegenie/plugins/` never imports from `plugins/`; the loader discovers plugin modules via filesystem walk and explicit `importlib.import_module` calls. Plugins import the kernel (`Plugin`, the adapter `Protocol`s, `PluginManifest`, the typed events). The Open/Closed boundary is the package wall.

## Components

### `PluginManifest` (`src/codegenie/plugins/manifest.py`)

- **Purpose:** Typed Pydantic model that mirrors `plugin.yaml` 1:1. Validation is `mypy --strict` clean; loading is `parse_obj`.
- **Public interface:**
  ```python
  class PluginManifest(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      name: PluginId
      version: str  # PEP 440-ish; smart-constructor validates
      scope: PluginScope
      extends: list[PluginId] = Field(default_factory=list)
      contributes: Contributes
      requirements: Requirements = Field(default_factory=Requirements)
      precedence: int = 50

      @classmethod
      def from_yaml(cls, path: Path) -> "PluginManifest": ...

  class Contributes(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      probes: list[ProbeId] = []
      adapters: AdaptersMap
      tccm: Path
      subgraph: Path
      skills: Path
      recipes: Path
  ```
- **Internal design:** Smart constructor (`from_yaml`) + Pydantic validators. The `version` field is parsed with `packaging.version.Version` and the parsed value is the source of truth, not the raw string. `AdaptersMap` is a typed dict of `PrimitiveName → AdapterImportPath`; the smart constructor splits `"module:Class"` and validates both halves exist.
- **Dependencies:** `pydantic>=2` (already pinned), `pyyaml` via the Phase 1 `safe_yaml` parser (size + depth-capped — `plugin.yaml` ≤ 64KiB, depth ≤ 16). No new runtime deps.
- **Where it lives:** `src/codegenie/plugins/manifest.py`. The schema is single-source-of-truth Pydantic; we generate `docs/schema/plugin-manifest.schema.json` as a build artifact for the documentation site, not as a parallel definition.
- **Tradeoffs accepted:** Pydantic costs ~25ms at startup to validate all manifests; we trade that for typed-everywhere safety. We could have parsed YAML straight into `dict[str, Any]` and saved the import — that would erase the entire reason ADR-0033 exists.

### `PluginScope` (`src/codegenie/plugins/scope.py`)

- **Purpose:** The `(task_class, language, build_system)` tuple with `*` wildcards. Pure data + a `matches(...)` algebra.
- **Public interface:**
  ```python
  TaskClass   = NewType("TaskClass", str)
  Language    = NewType("Language", str)
  BuildSystem = NewType("BuildSystem", str)
  WILDCARD: Final[str] = "*"

  @dataclass(frozen=True, slots=True)
  class PluginScope:
      task_class: TaskClass | Literal["*"]
      language: Language | Literal["*"]
      build_system: BuildSystem | Literal["*"]

      def matches(self, *, task: TaskClass, language: Language, build: BuildSystem) -> bool: ...
      def specificity(self) -> int:  # concrete dims (0..3); ties broken by precedence
          ...

      @classmethod
      def parse(cls, s: str) -> Result["PluginScope", ParseError]: ...
  ```
- **Internal design:** Functional core, no I/O. The `matches` algebra is one expression; `specificity` is `sum(dim != "*" for dim in self)`. Test it as a pure function — table-driven property test asserts the partial order. The smart-constructor `parse` is the only entry point from YAML.
- **Dependencies:** stdlib only.
- **Where it lives:** `src/codegenie/plugins/scope.py`. Idiomatic placement next to its sibling `PluginManifest`.
- **Tradeoffs accepted:** We could have made `*` a sum-type variant (`Concrete(value) | Wildcard()`) — which would be slightly more illegal-state-unrepresentable — but `Literal["*"]` reads better in YAML manifests and is one fewer Pydantic ceremony. Documented as a known weakness, called out in §"Patterns deliberately avoided".

### `PluginResolution` (`src/codegenie/plugins/resolver.py`)

- **Purpose:** The output of `resolve_plugin((task, language, build), registry)`. A tagged union so the Supervisor cannot accidentally proceed with no plugin matched.
- **Public interface:**
  ```python
  class ConcreteResolution(BaseModel):
      kind: Literal["concrete"] = "concrete"
      plugin: PluginId
      extends_chain: list[PluginId]
      matched_scope: PluginScope
      composed_tccm: ResolvedTCCM
      composed_adapters: dict[PrimitiveName, AdapterId]

  class FallbackResolution(BaseModel):
      kind: Literal["fallback"] = "fallback"
      reason: FallbackReason   # sum type: NoMatch | AllCandidatesUnusable
      candidates_considered: list[PluginId]
      universal_plugin: PluginId  # always plugins/universal--*--*

  PluginResolution = Annotated[
      Union[ConcreteResolution, FallbackResolution],
      Field(discriminator="kind"),
  ]

  def resolve_plugin(
      task: TaskClass, language: Language, build: BuildSystem,
      registry: PluginRegistry,
  ) -> PluginResolution: ...
  ```
- **Internal design:** Pure function over a snapshot of the registry. Algorithm: (1) filter candidates by `matches`; (2) sort by `(specificity desc, precedence desc, name asc)`; (3) walk the `extends` chain of the top candidate (left-to-right, later wins) per ADR-0031; (4) compose TCCM entries and adapter registrations; (5) emit `ConcreteResolution`. If candidates empty → `FallbackResolution(reason=NoMatch(...))`. The universal fallback is itself a registered plugin, but the resolver short-circuits its own selection to keep the audit signal honest ("the system fell back" vs "the system matched the universal plugin").
- **Dependencies:** kernel only; no I/O. The registry passed in is the populated `PluginRegistry` from `loader.load_all(...)`.
- **Where it lives:** `src/codegenie/plugins/resolver.py`.
- **Tradeoffs accepted:** We compose TCCMs at resolution time, not lazily. A few-millisecond up-front cost in exchange for a single inspectable Bundle the Supervisor uses unchanged. Phase 8's pre-rendered hot views (Redis) can cache the composed Bundle by `(repo, plugin_id)` later — Phase 3 doesn't pre-cache.

### `PluginRegistry` (`src/codegenie/plugins/registry.py`)

- **Purpose:** Dict of `PluginId → Plugin`, populated by `@register_plugin` at plugin module import. Mirrors `@register_probe` exactly.
- **Public interface:**
  ```python
  class PluginRegistry:
      def register(self, plugin: Plugin) -> None: ...
      def get(self, name: PluginId) -> Plugin: ...
      def all(self) -> list[Plugin]: ...

  default_registry: PluginRegistry

  def register_plugin(plugin: Plugin) -> Plugin:
      """Decorator: @register_plugin around a Plugin instance built from manifest + module."""
      default_registry.register(plugin)
      return plugin

  class PluginAlreadyRegistered(KeyError): ...
  class PluginNotRegistered(KeyError): ...
  ```
- **Internal design:** Just a dict. No eager validation (manifests are validated when loaded, before they reach the registry). Collision raises `PluginAlreadyRegistered` — same shape as `SignalKindAlreadyRegistered` from Phase 5 ADR-0003 and `TaskClassAlreadyRegistered` from Phase 6.5. Three siblings, one pattern.
- **Dependencies:** stdlib.
- **Where it lives:** `src/codegenie/plugins/registry.py`.
- **Tradeoffs accepted:** No lifecycle hooks, no priority callbacks, no eager cross-validation. The registry is dumb on purpose (ADR-0007's spirit: keep the contract small).

### `Plugin` (`src/codegenie/plugins/protocols.py`)

- **Purpose:** The minimal duck-typed contract every plugin satisfies. Not an ABC — a `Protocol`, so plugins compose without inheriting and we can test against any callable that quacks.
- **Public interface:**
  ```python
  class Plugin(Protocol):
      manifest: PluginManifest
      def build_subgraph(self) -> StateGraph: ...
      def adapters(self) -> dict[PrimitiveName, Adapter]: ...
      def cve_feed_parsers(self) -> dict[CVEFeedName, CVEFeedParser]: ...
  ```
- **Internal design:** Protocol + composition. The concrete `vulnerability_remediation_node_npm` plugin and the universal fallback both satisfy this Protocol structurally — no shared base class. (Composition over inheritance, ADR-0033 §Anti-pattern: "Inheritance for code reuse.")
- **Dependencies:** `typing.Protocol` (stdlib); `langgraph.StateGraph` only at the boundary (the Protocol type-only-imports it).
- **Where it lives:** `src/codegenie/plugins/protocols.py`. The four adapter Protocols (`DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`) live alongside, re-exported from the Phase 2 scaffolding so plugin authors import one symbol set.
- **Tradeoffs accepted:** No runtime conformance check at registration. Mypy strict on the plugin module catches it. If we wanted a runtime check we'd add a `@runtime_checkable` Protocol — deferred until we have a non-trivial reason.

### `PluginLoader` (`src/codegenie/plugins/loader.py`)

- **Purpose:** Walk `plugins/*/plugin.yaml`, validate each, import the plugin's `api` module, register.
- **Public interface:**
  ```python
  def load_all(search_paths: Iterable[Path]) -> PluginRegistry: ...
  ```
- **Internal design:** Functional shell. (1) `for p in search_paths.glob("*/plugin.yaml"): manifest = PluginManifest.from_yaml(p)`. (2) Import `manifest.contributes.subgraph` parent module via `importlib.import_module`, expecting a top-level `register_plugin(...)` call. (3) Validate the import paths in `contributes.adapters` at load time — broken adapter imports surface at startup, never at workflow time (ADR-0031 §"Schema enforcement and validation"). (4) After the walk, emit a `PluginsLoaded` event with the full registry inventory.
- **Dependencies:** stdlib, Pydantic.
- **Where it lives:** `src/codegenie/plugins/loader.py`. Called once from the CLI entrypoint; pure for everything below `import_module`.
- **Tradeoffs accepted:** Plugins are loaded eagerly at startup. Lazy loading would shave ~50ms but add a class of "plugin broken in production but didn't fail at startup" bugs. Fail loud (Global Rule 12).

### `BundleBuilder` (`src/codegenie/plugins/bundle.py`)

- **Purpose:** Given a `ResolvedTCCM` and an adapter map (both products of resolution), evaluate the TCCM's `must_read` / `should_read` / `may_read` queries and produce a typed `Bundle` for the plugin subgraph's initial state.
- **Public interface:**
  ```python
  class Bundle(BaseModel):
      kind: Literal["bundle"] = "bundle"
      bundle_id: BundleId
      must_read: dict[BundleKey, BundleEntry]
      should_read: dict[BundleKey, BundleEntry]
      may_read_handles: dict[BundleKey, BundleQueryHandle]  # lazy
      provenance: BundleProvenance       # which adapters answered, which fell back
      tokens_estimated: int

  def build_bundle(
      resolution: ConcreteResolution,
      repo_context: RepoContext,
      adapters: AdapterMap,
  ) -> Bundle: ...
  ```
- **Internal design:** Functional core. For each TCCM `derived` query, dispatch to the adapter registered for that primitive. If the adapter's `confidence()` is `Degraded` or `Unavailable`, consult the TCCM's declared `fallback` chain; log the downgrade in `provenance`; never silently substitute (ADR-0032). `may_read` items are stored as `BundleQueryHandle` (lazy) — the subgraph promotes them mid-execution by calling `handle.materialize()` which writes a `BundleEntryPromoted` event.
- **Dependencies:** kernel.
- **Where it lives:** `src/codegenie/plugins/bundle.py`.
- **Tradeoffs accepted:** No streaming — the whole `must_read + should_read` is materialized up front. With the TCCM budget caps in place (per-file + total token cap) this is bounded; if Phase 7's distroless TCCM blows the budget we add streaming then, not now (YAGNI).

### `Vulnerability remediation plugin` (`plugins/vulnerability-remediation--node--npm/`)

- **Purpose:** End-to-end deterministic vuln fix on a Node+npm repo. Reads CVE record → matches a recipe → applies the recipe → runs `npm install` → diff lands on a local branch.
- **Public interface:**
  ```python
  # plugins/vulnerability-remediation--node--npm/api.py
  def run(state: PluginState) -> RecipeOutcome: ...

  manifest: PluginManifest = PluginManifest.from_yaml("./plugin.yaml")
  subgraph: StateGraph = build_subgraph()
  ```
  `RecipeOutcome` is a tagged union: `Applied(diff, lockfile_delta, branch_name) | Skipped(reason: SkipReason) | NotApplicable(why: NotApplicableReason) | Failed(error: RecipeError)`.
- **Internal design:** The subgraph is **five nodes**, no more. (1) `ingest_cve` (parse NVD/GHSA/OSV into a unified `CVERecord` — pure function, three feed-specific parsers each producing the same Pydantic type, dispatched on `extension`). (2) `match_recipe` (look up which recipe applies; deterministic lookup table in `recipes/manifest.yaml`). (3) `apply_recipe` (the recipe is a `RecipeProtocol` callable; current implementations are `NcuBumpRecipe` and `DirectDepPinRecipe`). (4) `install_and_verify` (`npm ci` in subprocess via `run_external_cli` — Phase 2's port). (5) `write_branch` (`git checkout -b codegenie/vuln/<cve>/<sha> && git apply` — never `git push`; humans merge). On any node, returning a non-`Applied` `RecipeOutcome` short-circuits to the terminal `emit_outcome` node which appends to the event log.

  **Recipes are a Protocol, not an ABC.** A `RecipeProtocol` requires `applies(cve: CVERecord, context: Bundle) -> bool` and `apply(cve: CVERecord, context: Bundle) -> RecipeDiff`. Both `NcuBumpRecipe` and `DirectDepPinRecipe` are plain classes that structurally satisfy. Each recipe registers via `@register_recipe(plugin="vulnerability-remediation--node--npm")` (mirroring `@register_probe`).

  **Boring tool first:** `NcuBumpRecipe` shells to `npm-check-updates --upgrade --target=patch` with the package list constrained to the CVE-affected packages, then re-runs `npm install`. Why not OpenRewrite? Two reasons: (a) OpenRewrite npm coverage at adoption time is still YAML-recipe-shaped and the bridge from Python to its JVM runner is non-trivial; (b) `npm-check-updates` is the boring, widely-used tool with a stable contract — the best-practices answer. We isolate the dependency behind `RecipeProtocol` so swapping to OpenRewrite later requires only a new recipe class and a manifest entry. **No premature pluggability** — there are exactly two recipe implementations because there are exactly two real cases.

- **Dependencies:** `nodesemver` for semver parsing (~30KB, MIT, no transitive deps beyond stdlib); CLI tools `npm`, `npm-check-updates`, `git`, `jq` via Phase 2's `run_external_cli` allowlist (one entry added per binary, each ADR-0011-gated).
- **Where it lives:** `plugins/vulnerability-remediation--node--npm/` — the canonical plugin directory shape from ADR-0031.
- **Tradeoffs accepted:** `npm-check-updates` introduces an external CLI dep. The trade vs. a pure-Python lockfile editor: NCU is widely used (1M+ weekly downloads), has a stable JSON contract, and a hand-rolled equivalent would be ~800 LOC of error-prone semver math. NCU it is.

### `Universal HITL fallback` (`plugins/universal--*--*/`)

- **Purpose:** Match anything no concrete plugin handles. Never silently fail (ADR-0031 §"No-match fallback").
- **Public interface:** Same as any plugin (`manifest`, `subgraph`, `api.run(state)`). The subgraph is one node: `emit_requires_human_review` which writes `RequiresHumanReview(workflow_id, scope_attempted, candidates_considered)` to the event log and `interrupt()`s (Phase 6's LangGraph mechanism).
- **Internal design:** Two files — `plugin.yaml` (precedence: 0, scope: `(*, *, *)`) and `api.py` (~40 LOC). No TCCM derived queries; `must_read` is `workflow_summary` only.
- **Dependencies:** kernel only.
- **Where it lives:** `plugins/universal--*--*/`. The directory name uses `*` literally — the loader's filesystem walk pattern matches it. (Discussed in §"Open questions"; alternative was `plugins/_fallback/` with a manifest-declared wildcard scope, rejected as cleverness — the directory name *being* the scope is the idiomatic discoverability.)
- **Tradeoffs accepted:** Filesystem name `universal--*--*` requires shell-quoting on some platforms when listed. Acceptable; documented in `docs/plugins/authoring.md`.

### `Adapters` (`plugins/vulnerability-remediation--node--npm/adapters/`)

- **Purpose:** Four adapters implementing the ADR-0032 `Protocol`s by wrapping the Phase 2 probes. The contract surface plugin authors must understand.
- **Public interface (per adapter, structurally satisfying its Protocol):**
  ```python
  class NpmDepGraphAdapter:
      """Implements DepGraphAdapter for npm via Phase 1's NodeManifestProbe + parsed lockfile."""
      def __init__(self, repo_context: RepoContext) -> None: ...
      def consumers(self, package: PackageName) -> list[PackageName]: ...
      def confidence(self) -> AdapterConfidence: ...
  ```
  All four adapters take a `RepoContext` and an optional `IndexFreshness` (the Phase 2 sum type). `confidence()` returns `AdapterConfidence` — a tagged union: `Trusted | Degraded(reason: DegradedReason) | Unavailable(reason: UnavailableReason)`.
- **Internal design:** Each adapter is one class, one file, one Protocol satisfied. Pure functions inside; `confidence()` reads the underlying probe's freshness signal. `NodeScipAdapter` reads `IndexHealthProbe` output (B2) and degrades to `tree-sitter` via the TCCM's declared fallback when SCIP is stale. This is the *exact* shape Phase 7 will repeat for `dockerfile-parse`-backed adapters.
- **Dependencies:** Phase 1/2 probes (read-only); stdlib.
- **Where it lives:** `plugins/vulnerability-remediation--node--npm/adapters/*.py`. The adapter import paths are registered in `plugin.yaml`'s `contributes.adapters`.
- **Tradeoffs accepted:** Adapters wrap probes (not raw filesystem). A small indirection that pays for itself the moment a probe gets a richer output shape — adapters absorb the schema change without touching every callsite.

### `EventLog writer` (`src/codegenie/plugins/events.py`)

- **Purpose:** Append-only JSONL writer for typed events. Phase 9 lifts the same event types into Postgres unchanged.
- **Public interface:**
  ```python
  class EventLog:
      def __init__(self, path: Path) -> None: ...
      def append(self, event: Event) -> EventId: ...
      def replay(self) -> Iterator[Event]: ...   # for tests

  Event = Annotated[
      Union[
          PluginsLoaded, PluginResolved, BundleBuilt, BundleEntryPromoted,
          RecipeMatched, RecipeApplied, RecipeSkipped, RecipeFailed,
          InstallSucceeded, InstallFailed,
          LocalBranchWritten, RequiresHumanReview, AdapterDegraded,
      ],
      Field(discriminator="kind"),
  ]
  ```
- **Internal design:** One JSONL file per workflow under `.codegenie/events/<workflow-id>.jsonl`. Writer is `fcntl.flock`'d per Phase 6.5's pattern. Atomic append via `O_APPEND`. The reader is a generator for replay tests (and for Phase 6.5's bench backfill — read the 10 most recent vuln runs and lift them into `bench/vuln-remediation/cases/` mechanically).
- **Dependencies:** stdlib.
- **Where it lives:** `src/codegenie/plugins/events.py`. Phase 9 will swap the storage backend; the Pydantic event models survive unchanged.
- **Tradeoffs accepted:** JSONL is not a queryable store. We get hash-chain-style audit cheaply via Phase 0's `audit_anchor` helper extended with a per-line BLAKE3 chain. Real queries wait for Phase 9.

## Data flow

Representative run: `codegenie remediate ~/work/svc-checkout --cve=CVE-2024-12345 --advisory=ghsa.json` against a Node+npm repo.

1. **Plugin loader runs once at startup.** `loader.load_all([Path("plugins")])` walks `plugins/*/plugin.yaml`, validates each `PluginManifest`, imports each plugin's `api` module (which calls `@register_plugin`). Emits `PluginsLoaded(plugin_ids=[vulnerability-remediation--node--npm, universal--*--*])`. Wall: ~80ms.
2. **CVE record parsed.** `cve_feeds/ghsa.py` parses the GHSA JSON into a typed `CVERecord(id: CVEId, affected: list[AffectedPackage], cvss: CVSSScore | None, fixed_versions: dict[PackageName, SemverRange])`. Pure function. Three feed parsers (NVD/GHSA/OSV) emit the same `CVERecord` type. Smart constructors validate every field.
3. **Repo context resolved.** The Phase 1/2 gather is invoked (or cached); `RepoContext.languages` reports `[typescript]`; `RepoContext.build_systems` reports `[npm]`.
4. **Plugin resolved.** `resolve_plugin(task=TaskClass("vulnerability-remediation"), language=Language("typescript"), build=BuildSystem("npm"), registry)` returns `ConcreteResolution(plugin=PluginId("vulnerability-remediation--node--npm"), extends_chain=[], …)`. Emits `PluginResolved(...)`. If language had been `rust`, resolution would have returned `FallbackResolution(reason=NoMatch, universal_plugin=…)` and the universal subgraph would have fired.
5. **Bundle built.** `build_bundle(resolution, repo_context, adapters)` evaluates the TCCM:
   - `must_read.lockfile` → loads `package-lock.json` by reference (path + sha).
   - `must_read.manifest` → loads `package.json`.
   - `must_read.derived.affected_callsites` → `NodeScipAdapter.refs(cve.affected_symbols)`. The adapter checks `IndexHealthProbe.confidence()`; if `Stale`, the TCCM's declared `fallback: import_graph.reverse_lookup(...)` fires through `NodeImportGraphAdapter`, and `AdapterDegraded(primary=scip, primary_confidence=...)` lands in the event log.
   - `should_read.tests_for_affected` → `JestTestInventoryAdapter.tests_exercising(affected_files)`.
   - Bundle materialized. Emits `BundleBuilt(bundle_id, must_read_keys, should_read_keys, provenance)`. Total tokens estimated ≤ TCCM budget cap.
6. **Subgraph runs.** The plugin's LangGraph state machine takes `(Bundle, CVERecord)` and produces a `RecipeOutcome`:
   - `match_recipe`: lookup in `recipes/manifest.yaml` says CVE-2024-12345 against `lodash@<4.17.21` → `NcuBumpRecipe`. Emits `RecipeMatched(recipe_id=RecipeId("ncu-bump"), cve_id=...)`.
   - `apply_recipe`: `NcuBumpRecipe.apply(...)` invokes `run_external_cli("npm-check-updates", ["--upgrade", "--target=patch", "--filter", "lodash"], cwd=repo)`. Produces a unified diff against `package.json` and `package-lock.json`. Emits `RecipeApplied(diff_bytes_sha256=..., recipe_id=...)`.
   - `install_and_verify`: `run_external_cli("npm", ["ci"], cwd=temp_worktree)`. Records `InstallSucceeded(duration_ms=...)` or `InstallFailed(...)`. On failure, the subgraph routes to `emit_outcome` with `RecipeOutcome.Failed(InstallError(stderr))`.
   - `write_branch`: `git checkout -b codegenie/vuln/CVE-2024-12345/<short-sha>`, `git apply diff`, `git commit -m "fix(vuln): bump lodash to 4.17.21 (CVE-2024-12345)"`. Emits `LocalBranchWritten(branch_name=BranchName(...), commit_sha=...)`.
7. **Terminal event.** `RecipeOutcome.Applied(diff, lockfile_delta, branch_name)`. CLI prints the branch name and exits 0. Phase 6.5 can later replay this event stream to backfill a `bench/vuln-remediation/cases/CVE-2024-12345.toml` mechanically.

Where the conventions shine: every step is typed, every step is event-logged, every state machine transition is a tagged union with exhaustive `match`, every cross-module call is a `Protocol`, every domain primitive is a `NewType`, and *zero* lines of LLM SDK get imported. The plugin would round-trip through code review with no surprises.

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| Malformed `plugin.yaml` (missing field, wrong type) | `PluginManifest.from_yaml` Pydantic validation | `PluginManifestInvalid` (typed; names file + field). CLI exits 4. Loader does **not** load any plugin — partial-load is silent failure. |
| Plugin `extends` cycle | `resolver._walk_extends_chain` topological check | `PluginExtendsCycle(chain)` exception at loader time. CLI exits 4 with chain printed. |
| Adapter import path broken (`module:Class` doesn't exist) | `loader._validate_adapter_import` at load time | `AdapterImportFailed(plugin, primitive, path)`. CLI exits 4 with import path. ADR-0031 §"Schema enforcement" explicitly mandates fast-fail. |
| Resolution finds no concrete plugin | `resolver.resolve_plugin` returns `FallbackResolution` | Universal `(*, *, *)` plugin runs; emits `RequiresHumanReview`; `interrupt()`. Never silent. |
| Adapter `confidence()` is `Unavailable` | `BundleBuilder.dispatch` | If TCCM declares `fallback` for that derived query, dispatch fallback adapter; log `AdapterDegraded`. If no fallback, log `LowConfidenceAnswerUsed`; worker sees the value and decides. |
| `IndexHealthProbe.confidence` reports `Stale` | `NodeScipAdapter.confidence()` returns `Degraded(reason=ScipIndexStale(...))` | TCCM's declared `fallback: import_graph.reverse_lookup` fires; `AdapterDegraded` event logged; the worker proceeds with the wider tree-sitter set. |
| `npm install` fails post-bump | `InstallOutcome.Failed(exit_code, stderr)` from `run_external_cli` | `RecipeOutcome.Failed(InstallError(stderr))`; **no retry in Phase 3** — Phase 5 owns the three-retry trust-gate loop. Branch not written. |
| Recipe matched but no upgrade satisfies semver constraints | `NcuBumpRecipe.applies` returns `False` (peer-dep conflict; transitive vuln) | `RecipeOutcome.NotApplicable(reason=PeerDepConflict(...))`; Phase 4 LLM fallback territory. Event log records the gap. |
| External CLI missing (`npm-check-updates` not on PATH) | `tool_readiness` check at CLI startup (Phase 0 extension) | `MissingExternalTool(name="npm-check-updates", install_hint=...)`. CLI exits 2 *before* any plugin loads. Fail loud. |
| Concurrent runs racing the event log | `fcntl.flock` per Phase 6.5 | Second writer blocks; serialized. JSONL append is atomic under `O_APPEND` on POSIX. |
| Plugin author registers two plugins with the same `name` | `PluginRegistry.register` raises `PluginAlreadyRegistered(name, existing_version, new_version)` | CLI exits 4. Same shape as `SignalKindAlreadyRegistered` from Phase 5 and `TaskClassAlreadyRegistered` from Phase 6.5 — three siblings, one error class shape. |

Prefer typed exceptions over `RuntimeError`. The full taxonomy lives in `src/codegenie/plugins/errors.py`; ten classes, one per failure variant. No bare `except Exception`.

## Resource & cost profile

- **Startup:** plugin loader ~80ms on a cold disk (4 plugins × ~20ms each). Negligible.
- **Resolution:** ~5ms per workflow (dict lookup + sort + extends walk).
- **Bundle build:** dominated by adapter calls. `scip.refs(...)` is the slowest at ~50–200ms on a 5k-file repo (Phase 2 numbers). Bundle materialization total: ~250ms p95 warm.
- **Plugin subgraph run:** dominated by `npm ci` (~3–6s on the fixtures), recipe diff is ~50ms. Total warm: ~4–8s.
- **Memory:** plugin loader holds ~4 manifests × ~5KB; resolver allocates ~10KB per workflow; bundle holds references not contents → ~50KB even for large repos.
- **Tokens per run = 0.** The Phase 0 `fence` CI check forbids LLM SDK imports under `plugins/vulnerability-remediation--node--npm/` and under `src/codegenie/plugins/`. Asserted in CI.
- **Disk:** event log JSONL ~5KB per workflow. `.codegenie/events/` grows linearly; rotation is Phase 9 territory.

Where the convention costs: we accept a non-trivial pre-resolution cost (Pydantic validation of every plugin manifest at startup) in exchange for "broken plugin manifests fail at startup, never at workflow time." A custom hand-rolled YAML reader would shave milliseconds and lose the guarantee. Best practices wins this trade every time.

## Test plan

### Unit tests (bulk of the pyramid)

- **`tests/unit/plugins/test_manifest.py`** — `PluginManifest.from_yaml` against ~20 valid + ~15 invalid YAML fixtures. `extra="forbid"`, `frozen=True` enforcement. Smart-constructor `version` parsing.
- **`tests/unit/plugins/test_scope.py`** — `PluginScope.matches` table-driven: 100% branch coverage on the 3-dim wildcard algebra. `specificity` partial-order property test (`hypothesis`).
- **`tests/unit/plugins/test_resolver.py`** — `resolve_plugin` table-driven cases: exact match wins over wildcard; precedence breaks specificity ties; `extends` chain walks left-to-right; no-match → `FallbackResolution`; cycle detection → `PluginExtendsCycle`. ~30 cases.
- **`tests/unit/plugins/test_registry.py`** — collision raises `PluginAlreadyRegistered`. `default_registry` is a fresh instance per test (fixture isolation).
- **`tests/unit/plugins/test_loader.py`** — walks a fixture `plugins/` tree; broken adapter import fails at load; missing `tccm.yaml` referenced from `plugin.yaml` fails at load.
- **`tests/unit/plugins/test_bundle.py`** — Bundle builder dispatches to the right adapter; degraded adapter triggers declared fallback; `may_read` entries are handles, not materialized.
- **`tests/unit/plugins/test_events.py`** — `Event` discriminated union round-trips through Pydantic; replay reads what append wrote (`hypothesis` property: `for any event_stream, replay(write_all(stream)) == stream`).
- **`tests/unit/vulnerability_remediation_node_npm/test_cve_parsers.py`** — three parsers (NVD/GHSA/OSV) produce the same `CVERecord` for equivalent advisories. Golden fixtures under `tests/fixtures/cve/`.
- **`tests/unit/vulnerability_remediation_node_npm/test_ncu_recipe.py`** — `NcuBumpRecipe.applies` matrix; `apply` produces the expected diff bytes against fixture lockfiles. **The `npm-check-updates` invocation is mocked through `run_external_cli`'s injectable fake.**
- **`tests/unit/vulnerability_remediation_node_npm/test_adapters.py`** — each adapter against fixture `RepoContext`; `confidence()` against fixture `IndexHealthProbe` outputs. The SCIP-stale → tree-sitter degradation path has its own test.
- **`tests/unit/universal_fallback/test_emit.py`** — emits `RequiresHumanReview` with the correct fields; never returns a non-fallback outcome.

### Integration tests (a small set)

- **`tests/integration/plugins/test_end_to_end_lodash.py`** — fixture repo with vulnerable `lodash@4.17.20`, CVE-2024-12345 advisory, run the plugin end-to-end, assert: (a) branch `codegenie/vuln/CVE-2024-12345/<sha>` exists locally; (b) lockfile diff matches the golden; (c) `npm ci` exits 0; (d) the original test suite passes (run via `npm test`); (e) event stream contains `PluginsLoaded → PluginResolved → BundleBuilt → RecipeMatched → RecipeApplied → InstallSucceeded → LocalBranchWritten`.
- **`tests/integration/plugins/test_end_to_end_no_match.py`** — fixture Rust repo + vuln task class → universal fallback fires; `RequiresHumanReview` event; CLI exit code 0 with a "no plugin matched" message.
- **`tests/integration/plugins/test_end_to_end_install_fails.py`** — fixture with deliberately-incompatible peer dep; `RecipeOutcome.Failed(InstallError(...))`; no branch written.

### E2E (minimal)

- **`tests/e2e/plugins/test_real_advisory.py`** — one real archived GHSA against a small archived OSS repo (vendored under `tests/fixtures/archived/`). Asserts the system produces a green-tests-on-bumped-version branch end-to-end. Slow (~20s); runs nightly, not per PR.

### Property tests (`hypothesis`)

- `PluginScope` partial-order properties.
- Recipe determinism: for a fixed `(repo_snapshot, cve_record, recipe_version)` triple, `apply()` produces byte-identical diffs across 100 runs.
- Event log round-trip: `replay(write_all(stream)) == stream` for arbitrary event streams.
- Resolver invariants: for any registry and any `(task, lang, build)`, `resolve_plugin` returns either `ConcreteResolution` whose `plugin.scope.matches(task, lang, build)` is True, or `FallbackResolution` with `universal_plugin` present.

### Golden files

- Adapter outputs (`tests/golden/adapters/<adapter>/<fixture>.json`).
- Recipe diffs (`tests/golden/recipes/<recipe>/<fixture>.diff`).
- Event sequences for the three integration scenarios.

### Fence-CI

- **No LLM SDK under `src/codegenie/plugins/` or `plugins/`** — `import_linter` contract.
- **No edits to `src/codegenie/plugins/loader.py`, `resolver.py`, `registry.py` without a Phase-3-amendment ADR** — `tests/fence/test_plugin_kernel_frozen.py` git-diff fence (Phase 0 pattern).
- **Universal fallback plugin must exist** — `tests/fence/test_universal_fallback_present.py` asserts `plugins/universal--*--*/plugin.yaml` is parseable and registered.
- **Every plugin's `contributes.adapters` import paths resolve** — load test fails CI on broken import.

### Phase 6.5 backfill readiness

- `tests/e2e/plugins/test_replayable.py`: run a CVE end-to-end; export the event log; feed it into a stub `bench/vuln-remediation/cases/` generator; assert the generator produces a well-formed case file. (Phase 6.5 actually lifts this — Phase 3 ships the replayability.)

## Design patterns applied

| Decision (component or interface) | Pattern applied | Why this pattern *here* | Pattern *not* applied (and why) |
|---|---|---|---|
| `PluginRegistry` + `@register_plugin` | **Plugin / Registry** (mirrors `@register_probe`, `@register_signal_kind`, `@register_task_class`) | Extension by addition is *the* load-bearing commitment of this phase; the registry is the contract spine. Three siblings already exist with the same shape — Phase 3 makes it four. Adding a new plugin must never edit kernel code. (ADR-0031, ADR-0028, design-patterns-toolkit §Registry.) | Skipped a Factory pattern: there's no construction logic worth abstracting; `@register_plugin` wraps a fully-built `Plugin` instance and returns it untouched. |
| `PluginResolution` (`ConcreteResolution` ⊕ `FallbackResolution`), `RecipeOutcome` (`Applied` ⊕ `Skipped` ⊕ `NotApplicable` ⊕ `Failed`), `AdapterConfidence` (`Trusted` ⊕ `Degraded` ⊕ `Unavailable`), `InstallOutcome`, `Bundle` (`ConcreteBundle` ⊕ `FallbackBundle`) | **Tagged union / sum type** (Pydantic discriminated unions + `match` + `assert_never`) | Every Phase 3 state machine has more than two variants. Booleans for state would let illegal combinations construct ("matched but no plugin", "applied but no diff"); discriminated unions make those compile errors. ADR-0033 is the rule; this is its biggest application yet. | Skipped optional-field encoding (`Optional[Plugin]` + `is_fallback: bool`) — that's the exact anti-pattern ADR-0033 cites. |
| `Plugin`, `RecipeProtocol`, `CVEFeedParser`, the four adapter Protocols (`DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`) | **Dependency inversion via `typing.Protocol`** (structural conformance, no inheritance) | Plugins, recipes, adapters, and CVE feed parsers are all multi-implementation surfaces by definition. Protocols give plugin authors duck-typed flexibility while keeping `mypy --strict` honest. Composition over inheritance (ADR-0033 §Composition; design-patterns-toolkit §Dependency inversion). | Skipped ABCs. ABCs would force a base class import in every plugin; Protocols don't. The cost of `runtime_checkable` is real (slow `isinstance`) and unneeded — mypy is the enforcement layer. |
| Every domain primitive: `PluginId`, `RecipeId`, `CVEId`, `CVSSScore`, `PackageName`, `SemverRange`, `LockfileHash`, `BranchName`, `BundleId`, `AdapterId`, `WorkflowId`, `TaskClass`, `Language`, `BuildSystem`, `EventId`, `SymbolId`, `FilePath` | **Newtype** (`typing.NewType` or Pydantic wrapper for those needing validation) | Phase 3 has dozens of `str`-flavored domain primitives flowing across module boundaries. Without newtype, a `CVEId` and a `BranchName` are interchangeable to the type checker — a recipe could quietly write the wrong string into the wrong place. ADR-0033 §1. | Skipped runtime-validation everywhere: identifiers that originate inside code (e.g., a freshly-minted `BundleId` from `uuid4()`) don't need runtime parse. Only externally-sourced values (`CVEId` from JSON) get a smart constructor. |
| `PluginManifest.from_yaml`, `PluginScope.parse`, `CVERecord.parse_ghsa`, `CVERecord.parse_nvd`, `CVERecord.parse_osv` | **Smart constructor** returning `Result[T, ParseError]` (or raising a typed error on the CLI boundary) | All five are external-boundary deserializers. Every caller would otherwise have to "remember to validate" — and the few who forgot would ship the bug. Pydantic's validators + a `parse(...)` classmethod is the language idiom. ADR-0033 §2. | Skipped the open-box `__init__` route — Pydantic *does* let you `PluginManifest(**raw)`, but we make `from_yaml` the single import-time door and lint against direct constructor calls outside tests. |
| Plugin subgraph (5 nodes: `ingest_cve` → `match_recipe` → `apply_recipe` → `install_and_verify` → `write_branch`) | **Pipeline / Chain of responsibility** (LangGraph state machine; each node short-circuits with a typed `RecipeOutcome`) | The vuln-remediation flow has narrow per-stage contracts and each stage can short-circuit cleanly with a typed outcome. The pipeline shape composes with Phase 5's trust-gate retries and Phase 9's Temporal activities without restructuring. Five nodes is the calibrated size — more would be Phase 5 trust-gate territory. | Skipped a generic "step" framework with hooks before/after every node — premature pluggability, ADR-0031's anti-pattern. The five nodes are five files. |
| `EventLog` JSONL writer + Pydantic `Event` discriminated union | **Event sourcing** (Phase 3 anchor; Phase 9 graduates to Postgres without changing event types) | ADR-0034 names this as a canonical primitive. Six future projections (cost, ROI, Stage 7 Learning, plugin telemetry, audit, gate observability) all derive from the same typed event stream. Anchoring it here ensures Phase 7's distroless plugin emits the same `RecipeApplied`/`InstallSucceeded`/`LocalBranchWritten` events with zero refactor. | Skipped a generic message bus — Phase 3 is single-process. JSONL + `flock` is the boring, idiomatic solution; Phase 9's Postgres swap doesn't touch the event types. |

## Patterns deliberately avoided

- **No Visitor pattern over `CVERecord`.** The three feed parsers each produce the same Pydantic type; the consumer pattern-matches on the unified shape, not on the feed. A Visitor would add ceremony with no payoff.
- **No Builder pattern for `PluginManifest`.** Pydantic's `model_validate` is the builder. A separate `PluginManifestBuilder` class is the kind of pattern-soup ceremony the toolkit flags.
- **No Strategy pattern for recipe selection.** With exactly two recipes today, "strategy" would be `if applies(): apply()` dressed up as ceremony. The recipe registry is enough; if Phase 4 adds five more recipes, the pattern emerges from existing code naturally.
- **No Adapter Factory.** Adapters are instantiated once per workflow with a `RepoContext` reference. A factory would add a layer with no behavior.
- **No Observer / pub-sub on the event log.** Phase 3 has one consumer (the JSONL writer). Phase 9 adds projections — that's when subscription patterns earn their keep.
- **No Plugin lifecycle hooks (`on_load`, `on_register`, `on_resolve`).** Premature pluggability. The kernel does the lifecycle; plugins are pure data + a `Plugin` Protocol.
- **No abstract base class hierarchy `Plugin → VulnPlugin → NpmVulnPlugin`.** Composition over inheritance. Each plugin is a flat module that satisfies `Plugin` structurally.
- **No `dict[str, Any]` anywhere** in plugin contracts, event payloads, bundle entries, or adapter outputs. ADR-0033 §"Untyped `dict[str, Any]` interfaces" is the anti-pattern; the entire phase passes `mypy --strict` clean. Tested via a fence.
- **No boolean flags on public methods.** `Plugin.run(state, *, dry_run=False, strict=True)` is forbidden. The five subgraph nodes are explicit; dry-run is a Phase 5 trust-gate concept.
- **No bench `dict` payload.** Every event carries a typed Pydantic payload. Untyped events would erase ADR-0033's value at exactly the point it matters most (Phase 9's projections).
- **No service registry / DI container.** Plugin loading is one filesystem walk plus `importlib`. A DI container would be a 5x increase in indirection for zero capability we need.

## Risks (top 3–5)

1. **The plugin contract surface, once Phase 7 lands, is hard to change.** Anything wrong with `PluginManifest`, `PluginResolution`, the `Plugin` Protocol, or the adapter Protocols becomes an N-plugin refactor. *Mitigation:* keep the surface minimal (≤ 8 names from `src/codegenie/plugins/`); ship `vulnerability-remediation--node--npm` *and* the universal fallback in Phase 3 so the contract is exercised against two plugins from day one; add a synthetic third plugin in tests (`tests/fixtures/plugins/dummy--*--*/`) that exercises every contract feature for review purposes.
2. **`npm-check-updates` is an external CLI we don't control.** Future versions may change CLI flags, JSON output, or behavior. *Mitigation:* pin the version via `package.json` in `plugins/.../recipes/` (use NCU as a node-local dep, not a global tool); contract-test the CLI invocation as part of CI; the `RecipeProtocol` boundary means swapping recipes is local.
3. **TCCM derived-query coverage at adoption time is incomplete.** Phase 2 ships the four adapter `Protocol`s but not real production-tier indexers (SCIP, tree-sitter) for every case. *Mitigation:* the TCCM's `fallback` declarations are not optional — every derived query in the vuln plugin declares a coarser fallback; `IndexHealthProbe.confidence()` drives degradation transparently; the event log records every degradation so we measure real coverage in production.
4. **The "no LLM" fence is permissive in dev environments.** Engineers may add a one-line `import anthropic` for debugging and forget to remove it. *Mitigation:* `import_linter` runs on every PR; the contract is Phase 0's, extended only by adding `plugins/` to its scope; failing imports are a CI hard-block.
5. **Event log file growth is unbounded in Phase 3.** No rotation, no retention policy. *Mitigation:* per-workflow files (already partitioned); Phase 9 introduces retention; document the gap explicitly in the operator runbook.

## Acknowledged blind spots

- **Performance.** We accept ~80ms plugin-loader startup, ~250ms bundle build p95, and a non-trivial `npm install` cost as part of every run. The performance lens may propose lazy loading, async manifest parsing, or batched adapter calls — those are defensible *after* the contract is stable.
- **Security.** The plugin runs in-process; `run_external_cli` enforces the Phase 0 allowlist but there is no microVM isolation (Phase 5). A malicious plugin's Python code has the same access as the CLI. We accept this because: (a) plugins are first-party at adoption; (b) Phase 5 is the named escalation door; (c) `import_linter` + `mypy --strict` + a small audited surface area constrain what plugin code can do.
- **Concurrent plugin development.** Multi-plugin coordination (two teams editing adjacent plugins) is not addressed; Phase 7 will surface this. We assume single-team authoring in Phase 3.
- **Recipe coverage.** Only two recipes (`ncu_bump`, `direct_dep_pin`) ship. Many CVEs (transitive vulns, breaking-change majors) will fall through to `RecipeOutcome.NotApplicable` — Phase 4's job. The lens accepts this gap *explicitly*: ADR-0011 routes those to the LLM-fallback layer, which Phase 3 is forbidden from touching.
- **Out-of-tree plugins.** ADR-0031 §Consequences calls out v2 deferral; Phase 3 is in-tree only. Acceptable.

## Open questions for the synthesizer

1. **Universal fallback directory name.** `plugins/universal--*--*/` (the literal wildcard tuple is the directory name, idiomatic discoverability) vs. `plugins/_fallback/` (manifest declares scope; directory name uses convention `_`-prefix as "private"). Best-practices lens prefers the literal form for self-documenting placement; the security lens may flag the literal `*` for shell-quoting risk on tooling. Synthesizer should weigh discoverability against tool-friendliness.
2. **Recipe engine: NCU only vs. NCU + bare lockfile editor.** We ship NCU as the boring widely-used tool. Performance lens may argue for a hand-rolled in-process semver editor (no subprocess, ~40% wall-time savings on warm-cache CVE fixes). Acceptable trade if hand-rolled correctness is provably exhaustive — semver edge cases are surprisingly nasty.
3. **Plugin module discovery: filesystem walk vs. Python entry points.** ADR-0031 chose in-tree only at adoption; entry-point discovery is the v2 path. Phase 3 should probably ship filesystem walk only (boring, traceable). Synthesizer confirms.
4. **CVE feed parser placement: inside the plugin (`plugins/.../cve_feeds/`) vs. kernel (`src/codegenie/cve/`).** Best-practices lens places them inside the plugin (cohesion: the plugin understands its CVE sources). Performance lens may argue for a shared parser to avoid duplication across future plugins. Synthesizer's call — but note that Phase 7 (distroless migration) consumes the same NVD/GHSA/OSV feeds, so this question recurs.
5. **`RecipeProtocol.applies` signature.** Currently `applies(cve, context) -> bool`. ADR-0033 §"Tagged union" might suggest returning an `Applicability` sum type (`Applies | NotApplies(reason) | Maybe(needs_more_context)`). The `bool` is simpler; the sum type is more honest about partial knowledge. Synthesizer decides whether the sum type is worth the ceremony.
6. **Event log location.** `.codegenie/events/<workflow-id>.jsonl` (per-workflow) vs. `.codegenie/events.jsonl` (single file). Per-workflow simplifies replay; single file simplifies cross-workflow queries (which are Phase 9 territory anyway). Best-practices defaults to per-workflow; performance lens may push back.
7. **Whether to ship a third "synthetic test plugin" in `plugins/_examples--*--*/` to exercise the contract.** Pros: gives Phase 7 implementors an additional reference. Cons: adds surface area; risks becoming the de-facto contract.
