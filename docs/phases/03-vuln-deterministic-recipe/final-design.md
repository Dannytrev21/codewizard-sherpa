# Phase 3 — Vuln remediation: deterministic recipe path: Final design

**Status:** Design of record (synthesized from three competing designs + critique).
**Synthesized by:** Graph-of-Thought synthesizer subagent
**Date:** 2026-05-15
**Sources:** `design-performance.md` · `design-security.md` · `design-best-practices.md` · `critique.md`
**Phase 5 cross-reference:** `docs/phases/05-sandbox-trust-gates/final-design.md` (already merged — names load-bearing Phase 3 artifacts: `RemediationOrchestrator`, `TrustScorer`, `ApplyContext`, `Transform`, `RecipeEngine`, lockfile policy scanner, BLAKE3 audit chain).

---

## Lens summary

The synthesis takes **best-practices' package shape, plugin contract spine, and `import_linter` LLM-fence discipline** as the skeleton; pulls **performance's `VulnIndex` (indexed sqlite over CVE feeds), `BundleBuilder` content-addressed cache, and process-singleton-via-instance plugin registry** for the hot path; and lifts **security's `SandboxedPath`, `--ignore-scripts` flag-plus-env enforcement, env-stripping at plugin import, and BLAKE3-chained event log** for the trust boundary. The synthesis **departs from all three** on five axes that the critic correctly attacked:

1. **The artifacts Phase 5 already commits to consuming exist by name.** This phase ships `RemediationOrchestrator` (the Stage 6 entrypoint), `TrustScorer` (the strict-AND scorer), `Transform` (the ABC for recipe outputs), `ApplyContext` (the per-attempt context that Phase 5 amends with `prior_attempts: list[AttemptSummary] = []`), and a `remediation-report.yaml` index. None of the three lens designs named these; all three lose the integration handshake. **Resolution: this is non-negotiable — Phase 5 ships before Phase 3 can be re-implemented, and the critic is right that Phase 5's exit criterion is unmeetable without them.**
2. **Phase 3 runs the repo's own tests now, inside a `SubprocessJail` (bwrap on Linux, sandbox-exec on macOS), in a tempdir-cloned worktree.** The roadmap's exit-criterion sentence is "passes the repo's own tests." Security's deferral to Phase 5 is the wrong reading. Phase 5 wraps the **retry envelope** around the Stage 6 validate node Phase 3 ships; the inner validate run *is* Phase 3.
3. **The `Plugin` Protocol does not carry `cve_feed_parsers()`.** Best-practices ships that method — the critic correctly flagged it as the anti-pattern ADR-0031 was built to refuse. CVE-feed parsing is plugin-private and is registered through the TCCM-derived `vuln_index_capabilities` hook (ADR-0029), never on the kernel `Plugin` contract.
4. **No hedged-race in the `BundleBuilder`.** Performance's "first high-confidence wins" violates commitment §2.4 (Determinism over probabilism for structural changes). Fallback fires *deterministically* when the primary returns `confidence ∈ {Degraded, Unavailable}`, never as a scheduler race.
5. **`OpenRewriteRecipeEngine` is *scaffolded* in Phase 3** (Protocol-conformant stub backed by a single Dockerfile-base-image-swap fixture) — not as a real npm recipe path, but to establish that the `RecipeEngine` Protocol takes more than one implementation **before Phase 7 commits**. The default npm engine is `NpmLockfileRecipeEngine` (pure-Python edit of `package.json` + `npm install --package-lock-only` — performance's recipe path, security's `SandboxedPath` discipline). NCU is rejected: it solves the wrong question (Phase 3 already knows the target version from the CVE record).

One non-obvious departure: the `EventLog` writer ships **two event categories** with different durability semantics, mirroring ADR-0034's hybrid model. Phase 3 doesn't ship Temporal, but it acknowledges the split now so Phase 9's migration is mechanical: `workflow_internal` events go to `.codegenie/events/workflow-internal/<workflow_id>.jsonl.zst` (these will live in Temporal history at Phase 9); `workflow_spanning` events go to `.codegenie/events/spanning/append.jsonl.zst` (these will live in the Postgres side-channel). This is the critic's "all three are wrong about ADR-0034" issue answered.

A second non-obvious departure: a **synthetic third plugin** (`plugins/example--noop--*/`) ships as a tests-only fixture under `tests/fixtures/plugins/`. It exercises every contract surface (`manifest`, `subgraph`, `Adapter` Protocol, `Recipe` Protocol, TCCM, event emission) with a no-op implementation. The critic's argument is correct: Phase 7 will be the first real consumer of the plugin contract, and if anything is wrong it costs an unbounded ADR amendment to fix. The synthetic third plugin is the bake test before Phase 7.

---

## Goals (concrete, measurable)

- **Roadmap exit criterion met end-to-end.** Given a Node.js repo with a known npm CVE, the system writes a working patch diff on a local branch that — when applied — installs cleanly *and passes the repo's own tests*. Tests run inside `SubprocessJail`. `[synth — critic-mandated]`
- **Phase 5 integration handshake.** The names `RemediationOrchestrator`, `TrustScorer`, `Transform`, `ApplyContext`, `RecipeEngine`, `remediation-report.yaml` exist in `src/codegenie/transforms/`, are exported from `__init__.py`, are unit-tested, and survive `tests/integration/test_phase5_contract_snapshot.py` (a Phase-5-shaped contract snapshot test that Phase 5 then amends additively per ADR-P5-002). `[synth — critic Issue 1]`
- **Plugin contract testable against two real plugins + one synthetic.** `plugins/vulnerability-remediation--node--npm/` and `plugins/universal--*--*/` ship as production plugins; `tests/fixtures/plugins/example--noop--*/` ships as a tests-only third plugin exercising every contract surface. `[synth — critic Issue 8]`
- **Determinism guarantee (commitment §2.4).** Same `(repo_snapshot_sha, cve_record_digest, plugin_version, recipe_version, vuln_index_digest)` → byte-identical `Transform` output, byte-identical event sequence (modulo timestamps + `workflow_id`). Property-tested across 100 runs. `[P+B+synth]`
- **Honest confidence (commitment §2.3).** `IndexHealthProbe` (Phase 2 B2) `Stale` → `NodeScipAdapter.confidence()` returns `Degraded(reason=ScipIndexStale)` → TCCM-declared fallback (`import_graph.reverse_lookup`) fires *deterministically* (not raced); `AdapterDegraded` event emitted; verdict carries `confidence: degraded` through to `remediation-report.yaml`. `[B+S]`
- **No LLM in Phase 3 (commitment §2.4 + ADR-0005).** `import_linter` contract extended: `plugins/vulnerability-remediation--node--npm/`, `plugins/universal--*--*/`, `src/codegenie/plugins/`, and `src/codegenie/transforms/` may NOT import `anthropic`, `openai`, `langchain`, `langgraph`. CI hard-block. `[B]`
- **Zero edits to Phase 0/1/2 code for the plugin contract.** A CI fence (`tests/fence/test_kernel_frozen.py`) asserts no diff against the Phase-0/1/2 file list outside an ADR-anchored allowlist. `[B]`
- **Universal HITL fallback fires when no concrete plugin matches.** `plugins/universal--*--*/` resolves for any `(*,*,*)` tuple a concrete plugin doesn't match; emits `RequiresHumanReview`; CLI exits with documented code 7. Not silently substituted by a concrete plugin. `[P+S+B]`
- **Time-to-PR p50 ≤ 18 s (warm), p95 ≤ 35 s** on a representative Node.js fixture, including `npm install` + `npm test` inside `SubprocessJail`. Slower than performance's 8 s target (which excluded `npm test`); faster than security's 15–70 s (which over-budgeted the threat model). `[synth]`
- **`$0.00` in LLM spend per Phase 3 workflow.** Hard zero, asserted by CI fence. `[P+B]`
- **CVE feed lookup p99 ≤ 5 ms.** `VulnIndex` sqlite indexed lookup; the critic's "best-practices missed VulnIndex" attack landed. `[P]`
- **Plugin loader cold start ≤ 400 ms** for the two production plugins + universal fallback + signature-validation pass. `[P+S]`
- **Bundle Builder cache hit rate ≥ 90% on second run for the same `(repo, cve)`** (cache key includes `vuln_index.digest` per the critic's correction). `[P+synth]`
- **Audit completeness:** every plugin resolution, recipe selection, recipe application, install attempt, test attempt, file mutation, branch creation, and HITL escalation emits a typed event. BLAKE3-chained for tamper evidence. Replay-test asserts post-state byte-equality. `[S]`
- **Phase 6.5 backfill readiness:** every workflow emits a `BenchReplayable` event carrying input snapshot fingerprint + produced `Transform` output bytes. Phase 6.5 lifts 10 cases mechanically. `[B]`

These goals are the contract. The performance lens's headline number (8 s p50) is relaxed to 18 s p50 because Phase 3 now runs `npm test` inside a jail; the security lens's threat model is narrowed (single-repo, local, operator-curated CVE feeds — not adversary-supplied at runtime).

---

## Architecture

```
                          codegenie remediate <repo> --cve <id>
                                          │
                                          ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/cli/remediate.py                                  [B+S]    │
   │   click entry; SandboxedPath.create(jail=repo); WorkflowId mint;         │
   │   loads .codegenie/context (Phase 2); warns if stale                     │
   └────────────────────────────────────┬─────────────────────────────────────┘
                                        │
                                        ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/plugins/   [B-core, P-perf, S-trust]                       │
   │   loader.py     — walks plugins/*/plugin.yaml; signature check;          │
   │                   imports adapters; populates a passed-around            │
   │                   PluginRegistry *instance* (NOT module-level mutable)   │
   │   registry.py   — PluginRegistry class; @register_plugin decorator       │
   │                   targets default_registry but tests pass a fresh one    │
   │   manifest.py   — PluginManifest (Pydantic; extra="forbid"; frozen)      │
   │   scope.py      — PluginScope; Wildcard() sum-type variant (not Literal) │
   │   resolver.py   — resolve(scope) -> PluginResolution sum type            │
   │   bundle.py     — BundleBuilder (content-addressed cache; declared       │
   │                   fallback, NOT hedged race)                             │
   │   protocols.py  — Plugin Protocol (NO cve_feed_parsers method)           │
   │                   Adapter Protocols (DepGraph, ImportGraph, Scip, Test)  │
   │                   RecipeEngine Protocol                                  │
   │                   Transform ABC                                          │
   │   events.py     — typed Pydantic events; BLAKE3 chain; two streams       │
   │                   (workflow_internal | workflow_spanning) per ADR-0034   │
   │   capabilities.py — Capability tokens (FsReadWrite, NpmInstall,          │
   │                     GitLocalOps); minted only inside `capabilities.mint` │
   └──────────────────────────────────────┬───────────────────────────────────┘
                                          │
                                          ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/transforms/   [synth — Phase-5 contract surface]           │
   │   orchestrator.py — RemediationOrchestrator: 7 stages, calls plugin      │
   │                     subgraph; Stage 6 is `validate_via_gate(...)`        │
   │   trust_scorer.py — TrustScorer (strict-AND); signal-kind registry       │
   │                     extension point Phase 5 widens additively            │
   │   apply_context.py — ApplyContext dataclass; carries prior_attempts=[]   │
   │                       (Phase 5 amends via ADR-P5-002)                    │
   │   transform.py    — Transform ABC + RecipeOutcome sum type               │
   │   recipe_engine.py — RecipeEngine Protocol; NpmLockfileRecipeEngine      │
   │                       (default); OpenRewriteRecipeEngine (scaffolded     │
   │                       stub w/ Phase-7 fixture)                           │
   │   sandbox_jail.py  — SubprocessJail (bwrap | sandbox-exec adapter)       │
   │   report.py       — remediation-report.yaml writer; BLAKE3 audit chain   │
   └──────────────────────────────────────┬───────────────────────────────────┘
                                          │
                                          ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/vuln_index/   [P — perf design's win]                      │
   │   ingest.py — codegenie vuln-index refresh; NVD/GHSA/OSV → sqlite        │
   │   query.py  — VulnIndex.lookup(package, ecosystem); affecting_range(cve) │
   │   schema.sql — vulnerabilities table; alembic migrations                 │
   │   parsers/   — nvd.py, ghsa.py, osv.py (smart constructors w/ size caps) │
   └──────────────────────────────────────┬───────────────────────────────────┘
                                          │
                                          ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ plugins/                                                                  │
   │   vulnerability-remediation--node--npm/   [B+P+S — the first plugin]     │
   │     plugin.yaml                  precedence: 100; signature in PLUGINS.lock
   │     tccm.yaml                    must_read: lockfile, manifest, …        │
   │     adapters/                    NpmDepGraph, NodeImportGraph,           │
   │                                  NodeScip, JestTestInventory             │
   │     subgraph/                    5 node Stage-6-shaped pipeline          │
   │     recipes/                                                              │
   │       lockfile_semver_bump.py    NpmLockfileSemverBumpRecipe (the workhorse)
   │       peer_dep_conflict.py       NpmPeerDepConflictRecipe → NotApplicable │
   │       transitive_overrides.py    NpmTransitiveOverridesRecipe            │
   │       major_bump_refuse.py       NpmMajorBumpRefuseRecipe                │
   │     skills/                      YAML-frontmatter Skills                  │
   │     cve_feeds_capability.py      registers NVD/GHSA/OSV parsers via      │
   │                                  TCCM-derived plugin-private hook       │
   │     api.py                       run(state, registry) -> Transform       │
   │     PLUGINS.lock entry           sha256(dir_tree)                        │
   │                                                                           │
   │   universal--*--*/             [P+S+B — convergent, name kept]           │
   │     plugin.yaml                  precedence: 0; scope: (*, *, *)         │
   │     subgraph/api.py              emits RequiresHumanReview; exits 7      │
   │                                                                           │
   │   PLUGINS.lock                   { plugin_id: sha256(dir_tree) }         │
   └──────────────────────────────────────┬───────────────────────────────────┘
                                          │
                                          ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ tests/fixtures/plugins/example--noop--*/   [synth — critic Issue 8]      │
   │   plugin.yaml; adapters/noop_*.py; subgraph/api.py; recipes/noop.py;     │
   │   tccm.yaml — exercises every contract surface so Phase 7 has a worked  │
   │   reference and bugs in the contract surface at *3* plugins, not 1.     │
   └──────────────────────────────────────┬───────────────────────────────────┘
                                          │
                                          ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ .codegenie/events/                                                       │
   │   workflow-internal/<workflow_id>.jsonl.zst                              │
   │     (Phase 9 → Temporal workflow history)                                │
   │   spanning/append.jsonl.zst (BLAKE3-chained)                             │
   │     (Phase 9 → Postgres side-channel `events` table)                     │
   │   remediation-report.yaml (per workflow; indexes both streams + reports) │
   └──────────────────────────────────────────────────────────────────────────┘
```

Three load-bearing architectural lines, each addressing a critic issue:

1. **`RemediationOrchestrator` ships in `src/codegenie/transforms/` as a concrete class** (not just step functions), so Phase 5's `GateRunner.run(transition=stage6_validate, ctx=GateContext(...))` has a callsite to wrap. Phase 5's "Stage 6 → wrapped by Phase 5" line in its already-merged architecture has Phase 3's orchestrator as the *thing being wrapped*. We ship the wrap-target now.

2. **The `Plugin` Protocol has exactly four methods**, none task-class-specific: `manifest`, `build_subgraph(registry)`, `adapters() -> dict[PrimitiveName, Adapter]`, `transforms() -> dict[TransformKind, RecipeEngine]`. CVE-feed parsing is a *plugin-private capability* registered through the plugin's TCCM via a `provides:` block declaring `vuln_index_capabilities` and consumed by the vuln-remediation TCCM via a `requires:` block. Phase 7's distroless plugin won't have `vuln_index_capabilities` at all; it will have `dockerfile_capabilities`. No vestigial `return {}`. (ADR-0029 + ADR-0031.)

3. **`NpmLockfileRecipeEngine` is the production engine; `OpenRewriteRecipeEngine` is a scaffolded stub.** The scaffold ships:
   - The `RecipeEngine` Protocol satisfied by both.
   - A single Phase-7-shaped fixture (`tests/fixtures/openrewrite/dockerfile-base-image-swap.yaml`) that exercises the engine end-to-end but does NOT run for any Phase-3 npm CVE.
   - A `bench/vuln-remediation/cases/` case marked `engine=openrewrite` that is excluded by tag from Phase 3's CI but Phase 7 picks up by retagging.

   This pays the rent the critic correctly demands: the Protocol now has *two* implementations from day one. NCU is rejected because Phase 3 already knows the target version from the CVE record — calling NCU is asking it to compute what we already know, with extra registry I/O.

---

## Components

### 1. `RemediationOrchestrator` (`src/codegenie/transforms/orchestrator.py`)

- **Provenance:** `[synth]` (critic Issue 1 — none of the three lens designs shipped this; Phase 5 names it as load-bearing).
- **Purpose:** The 7-stage pipeline entry point for a single repo × single CVE workflow. Stage 6 (Validate) is the callsite Phase 5's `GateRunner.run(...)` wraps.
- **Interface:**
  ```python
  class RemediationOrchestrator:
      def __init__(
          self,
          registry: PluginRegistry,
          vuln_index: VulnIndex,
          event_log: EventLog,
          *,
          sandbox: SubprocessJail | None = None,   # default constructed below
      ) -> None: ...

      def run(
          self,
          repo: SandboxedPath,
          cve: CveId,
          context: ApplyContext = ApplyContext(),
      ) -> RemediationOutcome:
          """Runs Stages 1-6. Returns the typed outcome.
          On `outcome.outcome_kind == "validated"`, a local branch exists and
          `remediation-report.yaml` is on disk."""
  ```
  `RemediationOutcome` is a tagged union: `Validated(branch, report) | RequiresHumanReview(reason) | NotApplicable(reason) | Failed(error)`. Phase 5's `GateRunner` consumes `Validated` to decide retry/escalate; the orchestrator emits a `Validated(passed=False)` shape when tests fail and Phase 5 wraps the retry.
- **Internal design:** Phase 3's seven stages collapse to five in code (Discovery is per-portfolio not per-workflow; Handoff/Learning are Phase 6+). The orchestrator drives:
  1. **Resolve plugin** (`PluginResolver.resolve(scope_from_repo_context)`).
  2. **Build context bundle** (`BundleBuilder.build(plugin, repo_context, cve)`).
  3. **Match recipe** (plugin subgraph node).
  4. **Apply recipe** → produces a `Transform` (typed; sum: `Applied(diff, branch_name) | Skipped(reason) | Failed(error)`).
  5. **Stage 6 — Validate** (the orchestrator method `_validate_stage6(transform, ctx) -> StageOutcome`). This is the seam Phase 5 wraps. Inside Stage 6: a temp worktree is made; the diff is applied; `SubprocessJail.run(npm_install)` then `SubprocessJail.run(npm_test)` produce `BuildSignal`, `InstallSignal`, `TestSignal`, `LockfilePolicySignal`, `CveDeltaSignal` for `TrustScorer`. Phase 5's `StrictAndGate` calls `TrustScorer.score(...)` with these + its own widened signals (`trace`, `policy`). In Phase 3 (no Phase 5 yet), the orchestrator calls `TrustScorer.score(...)` directly.
  6. **Write `remediation-report.yaml`** indexing both event streams + the validate-stage outcome.
- **Why this choice over the alternatives:** Performance's "no orchestrator class, just step functions" is the position the critic correctly attacked — Phase 5's exit criterion (retry-1-fail + retry-2-recover) needs an orchestrator object to wrap. Best-practices ships a LangGraph subgraph; that's Phase 6's job and the LangGraph dependency is rejected here (the orchestrator is a plain `for` loop over typed stages, like Phase 5's `GateRunner`). Security ships a one-shot data flow but doesn't name the orchestrator; we name it.
- **Tradeoffs accepted:** A `RemediationOrchestrator` class is slightly more ceremony than five step functions, but it's the named extension point Phase 5 needs. Phase 6 will *wrap* `_validate_stage6` in a LangGraph node — the function signature is what Phase 6 ports, not a rewrite.

### 2. `TrustScorer` (`src/codegenie/transforms/trust_scorer.py`)

- **Provenance:** `[synth]` (critic Issue 1 — Phase 5 names this by name and amends it additively via ADR-P5-003).
- **Purpose:** Strict-AND scoring of `TrustSignal` instances. Same scorer Phase 5 widens with `trace`, `policy`, `cve_delta` signal kinds.
- **Interface:**
  ```python
  class TrustSignal(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      kind: SignalKind                 # registered via @register_signal_kind
      passed: bool
      details: dict[str, str | int | bool | float]   # primitives only

  class TrustOutcome(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      passed: bool
      failing: list[SignalKind]
      signals: list[TrustSignal]
      confidence: Literal["high", "degraded"]   # degrades on AdapterDegraded

  class TrustScorer:
      def score(self, signals: list[TrustSignal]) -> TrustOutcome: ...
  ```
  `SignalKind` is an *open registry* (per ADR-P5-003): Phase 3 registers `build`, `install`, `tests`, `lockfile_policy`, `cve_delta`. Phase 5 will additively register `trace`, `policy`. Phase 7 will register `baseimage`, `shell_presence`.
- **Internal design:** Strict-AND: `passed = all(s.passed for s in signals)`. `confidence = "degraded" if any AdapterDegraded event preceded this score within the workflow_id, else "high"`. The scorer reads its own workflow's event log for `AdapterDegraded` markers — the freshness signal propagates structurally per commitment §2.3 (Honest confidence).
- **Why this choice over the alternatives:** None of the three lens designs shipped this. Phase 5 names it, names its extension point, and ships an integration test (`test_trustscorer_widening.py`) that requires it. We ship it the shape Phase 5 expects.
- **Tradeoffs accepted:** The scorer reading its own event log to compute `confidence` is mildly cyclical (event-log writes happen synchronously inside `_validate_stage6`; the scorer runs at the end of the stage). Tested by replay; documented in `Notes-for-implementer`.

### 3. `Transform` ABC + `RecipeOutcome` sum type (`src/codegenie/transforms/transform.py`)

- **Provenance:** `[synth]` (critic Issue 1 — Phase 5 names `Transform` ABC).
- **Purpose:** The typed product of a recipe application. What Phase 5 consumes via `GateContext.transform_output`.
- **Interface:**
  ```python
  class Transform(ABC):
      """Abstract base class for recipe outputs. Concrete subclasses:
         NpmLockfileTransform, DockerfileBaseImageTransform (Phase 7), …"""
      transform_id: TransformId
      diff_bytes: bytes
      files_changed: list[SandboxedPath]
      provenance: TransformProvenance

  class RecipeOutcome(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      kind: Literal["applied", "skipped", "not_applicable", "failed"]
      # discriminated union variants...
  ```
- **Why this choice over the alternatives:** Performance's `Diff in memory` (untyped bytes), best-practices' `RecipeDiff` (defined nowhere), security's `Patch` (also undefined) — three names for the same thing. Phase 5 will not accept three names. `Transform` is the name in Phase 5's `final-design.md`; we adopt it.
- **Tradeoffs accepted:** `Transform` is an ABC, not a Protocol, because Phase 5 expects to type-check the inheritance chain via `isinstance`. Composition-over-inheritance still applies elsewhere (`Plugin` is a Protocol); `Transform` is the small exception.

### 4. `ApplyContext` (`src/codegenie/transforms/apply_context.py`)

- **Provenance:** `[synth]` (critic Issue 1 — Phase 5's ADR-P5-002 amends this additively).
- **Purpose:** Per-attempt input context. Carries `prior_attempts: list[AttemptSummary] = []` (default empty; Phase 5 populates it on retry).
- **Interface:**
  ```python
  class ApplyContext(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      workflow_id: WorkflowId
      attempt: AttemptNumber = AttemptNumber(1)
      prior_attempts: list[AttemptSummary] = Field(default_factory=list)
      capabilities: CapabilityBundle    # type-checked at call site
  ```
- **Internal design:** Phase 3 callsites pass `ApplyContext()` (defaults). Phase 5 will pass `ApplyContext(prior_attempts=[AttemptSummary(...)])` on retry. The default-empty field is the additive extension; the Phase 3 contract-snapshot test regenerates with the new optional field at Phase 5 time.
- **Tradeoffs accepted:** `prior_attempts` is dead weight in Phase 3 (always empty). Acceptable — better to ship the field now and have Phase 5 populate it than to amend the Pydantic model later and break a contract snapshot.

### 5. `PluginRegistry` + `@register_plugin` (`src/codegenie/plugins/registry.py`)

- **Provenance:** `[B+synth]` (best-practices' registry instance with fixture-isolation, NOT performance's module-level singleton).
- **Purpose:** Dict of `PluginId → Plugin`, populated by `@register_plugin` decorators *targeted at a specific registry instance*.
- **Interface:**
  ```python
  class PluginRegistry:
      def register(self, plugin: Plugin) -> None: ...
      def get(self, name: PluginId) -> Plugin: ...
      def resolve(self, scope: PluginScope) -> PluginResolution: ...
      def all(self) -> list[Plugin]: ...

  default_registry: PluginRegistry  # the production singleton

  def register_plugin(plugin: Plugin, *, registry: PluginRegistry | None = None) -> Plugin:
      (registry or default_registry).register(plugin)
      return plugin
  ```
  `register_plugin` defaults to `default_registry` but tests can pass a fresh `PluginRegistry()` for fixture isolation. This is best-practices' shape; performance's module-level mutable dict is rejected because pytest doesn't restart the worker between tests.
- **Internal design:** Just a dict + a `resolve()` method that walks the registered plugins by `(specificity desc, precedence desc, name asc)`. The universal fallback (`plugins/universal--*--*/`) is itself registered with `precedence=0` and scope `(*, *, *)` — it's always the last match, and resolution never has a "no plugin matched" branch (the universal fallback IS the no-plugin-matched branch). This is the critic's Issue 5: best-practices was right that the fallback is just another plugin; we confirm.
- **Why this choice over the alternatives:** Performance's module-level mutable global is the design-patterns-toolkit's "Side effects at module import time" anti-pattern. Best-practices' instance-with-default-singleton-and-fixture-isolation is the boring idiomatic answer. Phase 6.5's `TaskClassRegistry` already adopted this exact shape; we match it.
- **Tradeoffs accepted:** Two ways to register (`@register_plugin` defaulting to `default_registry`, vs. `@register_plugin(registry=fresh)` in tests). The verbosity in tests is small; the test-isolation benefit is large.

### 6. `Plugin` Protocol (`src/codegenie/plugins/protocols.py`)

- **Provenance:** `[B+synth]` (critic Issue 4 — `cve_feed_parsers()` REMOVED).
- **Purpose:** The minimal duck-typed contract every plugin satisfies. Four methods, no task-class-specific knowledge.
- **Interface:**
  ```python
  class Plugin(Protocol):
      manifest: PluginManifest
      def build_subgraph(self, registry: PluginRegistry) -> PluginSubgraph: ...
      def adapters(self) -> dict[PrimitiveName, Adapter]: ...
      def transforms(self) -> dict[TransformKind, RecipeEngine]: ...
  ```
  `PluginSubgraph` is a typed step-function-pipeline (NOT a LangGraph `StateGraph` — that's Phase 6's runtime; we ship the *contract* Phase 6 wraps). It's a Pydantic model carrying an ordered list of `SubgraphNode` callables + transition predicates.
- **Internal design:** Plugin-private capabilities (like CVE-feed parsers for the vuln-remediation plugin) are NOT on this Protocol. They are declared in the plugin's TCCM under a `provides:` block:
  ```yaml
  # plugins/vulnerability-remediation--node--npm/tccm.yaml
  provides:
    vuln_index_capabilities:
      - cve_feed_parsers: cve_feeds_capability:parsers
  requires:
    vuln_index_capabilities: ["cve_feed_parsers"]
  ```
  At `Resolver.resolve(...)` time, the resolver matches `provides`/`requires` declarations and binds them; the orchestrator queries `plugin.tccm.provides["vuln_index_capabilities"]["cve_feed_parsers"]` and dispatches. **Phase 7's distroless plugin declares `provides.dockerfile_capabilities`, not `vuln_index_capabilities`. The kernel doesn't know about either. Zero edits to `protocols.py` between Phase 3 and Phase 7.**
- **Why this choice over the alternatives:** Best-practices' design had `cve_feed_parsers()` on the Protocol — the critic correctly flagged this as the exact anti-pattern ADR-0031 was created to refuse. The `provides`/`requires` TCCM hook is ADR-0029's intended extension point; we ship it. Phase 7 will validate the contract.
- **Tradeoffs accepted:** The TCCM gets one new top-level key (`provides`). One YAML field is the cost of not corrupting the kernel Protocol.

### 7. `PluginScope` with `Wildcard()` sum-type variant (`src/codegenie/plugins/scope.py`)

- **Provenance:** `[B+synth]` (critic Issue 4 on patterns — best-practices' `Literal["*"]` was correctly flagged as type-checker theater).
- **Interface:**
  ```python
  @dataclass(frozen=True, slots=True)
  class Concrete:
      value: str   # newtype-wrapped at call sites

  @dataclass(frozen=True, slots=True)
  class Wildcard:
      pass

  ScopeDim = Concrete | Wildcard

  @dataclass(frozen=True, slots=True)
  class PluginScope:
      task_class: ScopeDim
      language: ScopeDim
      build_system: ScopeDim

      def matches(self, *, task: TaskClass, language: Language, build: BuildSystem) -> bool: ...
      def specificity(self) -> int: ...   # count of Concrete dims

      @classmethod
      def parse(cls, s: str) -> Result["PluginScope", ParseError]: ...
  ```
- **Why this choice over best-practices' `Literal["*"]`:** Best-practices admitted in its own §Open questions #1 that `Concrete | Wildcard` is more illegal-state-unrepresentable, then declined for YAML aesthetics. The critic correctly attacked: a `NewType("Language", str) | Literal["*"]` collapses to `str` at runtime. ADR-0033 beats YAML aesthetics. The YAML still writes `*` — `PluginScope.parse("vulnerability-remediation/javascript/*")` is the smart constructor.
- **Tradeoffs accepted:** Slightly more code in `matches()` (one `match` statement). Compile-time soundness wins.

### 8. `PluginResolution` (sum type) + `Resolver` (`src/codegenie/plugins/resolver.py`)

- **Provenance:** `[B]`.
- **Interface:** `PluginResolution = ConcreteResolution(plugin, extends_chain, matched_scope, composed_tccm, composed_adapters) | UniversalFallbackResolution(reason, candidates_considered)`. The "no plugin matched" state is type-unrepresentable; the universal fallback is one variant of the sum.
- **Internal design:** Resolution algorithm:
  1. Filter all registered plugins by `scope.matches(task, language, build)`.
  2. Sort by `(specificity desc, precedence desc, name asc)`.
  3. If the top match is `universal--*--*`, return `UniversalFallbackResolution(reason=NoConcreteMatch)`. Otherwise return `ConcreteResolution(...)`.
  4. Compose `extends` chain (left-to-right, later wins, max depth 4, cycle-checked).
  5. Compose TCCM (`provides` declarations from each chain entry merged).
- **Tradeoffs accepted:** Universal fallback resolution is technically `O(plugins)` per workflow, not `O(1)`. Performance's claim of `O(1)` was self-contradicting (the critic was right). For 3 plugins this is sub-microsecond; the discrepancy is academic.

### 9. `BundleBuilder` (`src/codegenie/plugins/bundle.py`)

- **Provenance:** `[P+B+synth]` (performance's content-addressed cache, best-practices' typed Bundle model, synthesizer's removal of hedged-race + addition of `vuln_index.digest` to cache key).
- **Purpose:** Execute TCCM-derived queries via language adapters; cache results content-addressed.
- **Interface:**
  ```python
  class BundleBuilder:
      async def build(
          self,
          resolution: ConcreteResolution,
          repo_ctx: RepoContext,
          vuln: VulnerabilityRecord,
          vuln_index: VulnIndex,
      ) -> Bundle: ...
  ```
- **Internal design:**
  - **Cache key:** `blake3(plugin_id || plugin_version || primitive || canonicalize(args) || repo_ctx.digest || scip.digest || dep_graph.digest || vuln_index.digest)`. The critic correctly flagged that performance's key omitted `vuln_index.digest` — a feed refresh that re-classifies a CVE would return a stale cache hit. We fix it.
  - **Parallelism:** Each `must_read` query is an `asyncio.Task` under `Semaphore(min(4, os.cpu_count()))`. The 4-cap is **advisory and overridable via `CODEGENIE_BUNDLE_CONCURRENCY` env var** so CI-runner tuning is possible without code edits. The critic correctly noted the SSD-knee number is unbenchmarked on `ubuntu-latest`; the env-var escape hatch is the resolution.
  - **Determinism (commitment §2.4):** **No hedged race.** The TCCM-declared `fallback` query runs *only* when the primary returns `AdapterConfidence ∈ {Degraded, Unavailable}`. This is the critic's Issue 7 resolution. Same input → same Bundle, byte-equal. Property-tested.
- **Why this choice over performance's hedged race:** Performance's confidence-driven hedged-race produces non-deterministic Bundle bytes under scheduler timing. Commitment §2.4 forbids that. The latency cost of strictly-serial fallback (only ~100 ms when `Degraded`, which is rare) is acceptable; determinism is non-negotiable.
- **Tradeoffs accepted:** On `Degraded`, latency rises (~80 ms primary + ~100 ms fallback vs. performance's max(80,100)=100 ms hedged). The deterministic path costs ~80 ms in the common case; the rare degraded-path costs ~180 ms. Trade made.

### 10. `VulnIndex` (`src/codegenie/vuln_index/`)

- **Provenance:** `[P]` (performance's win — best-practices missed this and the critic flagged it).
- **Purpose:** Convert `(package, ecosystem)` → `list[VulnerabilityRecord]` from 50–200 ms JSON parse to 3 ms indexed sqlite lookup.
- **Interface:**
  ```python
  class VulnIndex:
      def lookup(self, package: PackageId, ecosystem: Ecosystem) -> list[VulnerabilityRecord]: ...
      def affecting_range(self, cve: CveId) -> AffectedRange: ...
      def digest(self) -> BlobDigest: ...
  ```
- **Internal design:** sqlite (~50 MB) keyed by `(ecosystem, package, affected_min_version, affected_max_version)`. Ingest CLI: `codegenie vuln-index refresh` — pulls NVD JSON 2.0 delta, GHSA via `since`-cursor, OSV via GCS zsync. Each feed projects into a typed Pydantic record via a smart constructor (size + depth caps from security's design: 1 MiB JSON cap, max-depth=16). Migration via alembic.
- **Tradeoffs accepted:** Local-only; portfolio-scale centralization is Phase 10. The CVE-feed-fetch threat model is narrowed (per critic's Hidden Assumption #1 attack on security): operators run `codegenie vuln-index refresh` deliberately; this is not adversary-supplied at runtime. Feed-data hardening is still kept (smart constructors with caps) but bwrap/SecurityManager-style ceremony is rejected.

### 11. `NpmLockfileRecipeEngine` (`src/codegenie/transforms/recipe_engine.py`)

- **Provenance:** `[P+S]` (performance's pure-Python edit, security's `SandboxedPath` + `--ignore-scripts` discipline).
- **Purpose:** The production default `RecipeEngine` for npm dep bumps. Pure Python.
- **Interface:**
  ```python
  class RecipeEngine(Protocol):
      async def apply(
          self,
          repo: SandboxedPath,
          plan: RecipePlan,
          capability: NpmInstallCapability,
      ) -> RecipeOutcome: ...

  class NpmLockfileRecipeEngine:    # production
      ...

  class OpenRewriteRecipeEngine:    # scaffolded stub; Phase 7 fleshes out
      ...
  ```
- **Internal design:**
  1. Parse `package.json` via `orjson` (1–2 ms; size cap 1 MiB).
  2. Edit the affected dep version in-memory; preserve key order.
  3. Write back through `SandboxedPath` with `O_NOFOLLOW`, atomic rename.
  4. `SubprocessJail.run(npm install --package-lock-only --ignore-scripts --no-audit --prefer-offline)` in a temp worktree (hardlink-copy of the source repo's `package.json` + `package-lock.json` only). `--ignore-scripts` is enforced at both CLI and env (`npm_config_ignore_scripts=true`) per security; the critic was right that one or the other has been buggy in npm history.
  5. Parse new `package-lock.json`; validate; return `RecipeOutcome.Applied(NpmLockfileTransform(...))`.
- **Why this over OpenRewrite for npm:** Performance's analysis stands: OpenRewrite cold-starts in 3.5–5 s on a JVM for a `package.json` JSON edit. The npm CVE surface is lockfile resolution, not source-tree rewrites. The `RecipeEngine` Protocol stays, so Phase 7 can ship `OpenRewriteRecipeEngine` for Dockerfile structural transforms (where OpenRewrite's LST-precision earns its boot cost). Best-practices' NCU is rejected: NCU's job is "what versions are available?" — Phase 3 already knows the target from the CVE record.
- **Tradeoffs accepted:** OpenRewrite's structural-edit precision unrealized for npm. Acceptable; the production CVE surface for npm in 2026 is lockfile resolution.

### 12. `OpenRewriteRecipeEngine` (scaffolded stub) (`src/codegenie/transforms/recipe_engine.py`)

- **Provenance:** `[synth]` (critic Issue 3 — establishes the Protocol takes >1 implementation before Phase 7 commits).
- **Purpose:** Protocol-conformant stub that proves the `RecipeEngine` Protocol generalizes. Not a real npm path.
- **Internal design:** Ships:
  - The implementation: `JvmRecipeEngine` that subprocess-runs OpenRewrite against a Dockerfile fixture, parses the rewrite report, returns `RecipeOutcome.Applied(DockerfileBaseImageTransform(...))`.
  - A Phase-7-tagged test (`tests/integration/openrewrite/test_dockerfile_base_image_swap.py @pytest.mark.phase_7_preview`) that runs against `tests/fixtures/openrewrite/dockerfile-base-image-swap/`. CI runs this in Phase 7 (the tag flips); Phase 3 CI excludes the tag but the engine is unit-tested.
  - A `recipes/openrewrite-distroless-stub.yaml` recipe file mock — proves the recipe-registration mechanism doesn't have hidden npm-shaped assumptions.
- **Why this choice:** All three lens designs demoted OpenRewrite. The critic correctly observed Phase 7 (distroless migration) needs *exactly* OpenRewrite-style structural refactors. If Phase 3 ships zero JVM scaffolding, Phase 7 invents it under a "zero edits" constraint and discovers Protocol issues that are too late to fix. Scaffolding now de-risks Phase 7.
- **Tradeoffs accepted:** A small amount of JVM-shaped code lands in Phase 3 that isn't used by any Phase-3 workflow. The cost is ~250 LOC + a fixture; the benefit is Phase 7's "zero edits to kernel" exit criterion is achievable.

### 13. `SubprocessJail` (`src/codegenie/transforms/sandbox_jail.py`)

- **Provenance:** `[S+synth]` (security's design, with the macOS-prefetch flow rejected as critic Issue 2's resolution).
- **Purpose:** Wrap every subprocess.run in Phase 3 (npm install, npm test, git) so child processes cannot reach `~`, cannot exceed time/memory caps, cannot reach the network beyond an explicit allowlist.
- **Interface:**
  ```python
  class SubprocessJail:
      def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult: ...

  class JailedSubprocessSpec(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      cmd: tuple[str, ...]
      cwd: SandboxedPath
      env: NpmEnv | GitEnv   # typed, never raw dict
      network: NetworkPolicy   # DenyAll | RegistryAllowlist(hosts)
      time_budget_s: float
      memory_mib: int
      pids_max: int
  ```
  `JailedSubprocessResult = Completed(exit_code, stdout, stderr, duration) | TimedOut | OomKilled | NetworkDenied(host) | DiskQuotaExceeded`.
- **Internal design (Linux):** bwrap with `--unshare-all --new-session --die-with-parent --ro-bind / / --tmpfs /tmp --bind <jail> <jail>`. Network namespace owned by parent; child sees `lo` + a single pf-routed outbound to `RegistryAllowlist` hosts (registry.npmjs.org by default). Seccomp filter blocks `mount`, `pivot_root`, `ptrace`, `bpf`, `unshare`, `keyctl`.
- **Internal design (macOS):** `sandbox-exec -f <generated.sb>`. Profile: `deny default`, explicit `allow file-read* file-write*` for the jail directory, `deny network-outbound` plus an allow-rule for the registry host(s) when `RegistryAllowlist` is set. **Online-mode is the default on macOS too** — the critic correctly attacked security's macOS offline-mode-only flow as introducing an unjailed prefetch step that defeats its own primary defense. The `sandbox-exec` egress-allowlist mechanism is honored by macOS even if the policy language is "undocumented" — the design accepts the deprecation risk (Phase 5 will replace with Lima-microVM-on-macOS per Phase 5's already-merged design).
- **Why this choice over security's macOS-offline-prefetch:** Security's macOS flow split the trust boundary: the prefetch step *was* networked, ran *outside* the jail, and the SHA-512 validation against the registry's own metadata response was circular. By keeping online-mode the default on both substrates and using `sandbox-exec` egress allowlisting on macOS, we have one defense (the jail's network policy) rather than two contradicting defenses (offline jail + unjailed prefetch).
- **`--ignore-scripts` enforcement:** Both at CLI (`npm install --ignore-scripts`) and env (`npm_config_ignore_scripts=true`). The critic acknowledged best-practices missed this; we lift it from security.
- **Tradeoffs accepted:** macOS `sandbox-exec` is deprecation-flagged. Phase 5 replaces; Phase 3 accepts the residual risk for the developer-laptop case. Linux/CI is the production substrate.

### 14. `Capability` tokens (`src/codegenie/plugins/capabilities.py`)

- **Provenance:** `[S+synth]` (security's design, with the "private constructor" claim toned down to "convention + lint + module-level discipline").
- **Purpose:** Hold `NpmInstallCapability`, `FsReadWriteCapability`, `GitLocalOpsCapability` as typed values that the resolver mints and recipe-engine consumers receive as arguments. Plugin code cannot construct them outside `capabilities.mint(...)`.
- **Interface:**
  ```python
  class NpmInstallCapability(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      registry: RegistryUrl
      _minted_by: PluginId   # tracking only

  # In src/codegenie/plugins/capabilities.py:
  def mint(plugin: PluginId, scope: CapabilityScope) -> CapabilityBundle: ...
  ```
- **Internal design:** Capability classes live in `capabilities.py`. A `ruff` custom rule (in `tooling/ruff_rules/no_capability_construction.py`) fails CI if any module outside `capabilities.py` and `tests/` constructs a `*Capability` directly via name lookup. **The critic correctly noted security's "unforgeable by construction" claim does not survive runtime — Pydantic doesn't know its caller.** The design accepts that the enforcement is a *lint plus convention*, not a Pydantic runtime check. The lint is real (a ruff rule with an AST visitor); plugin authors who bypass it are noisy in code review.
- **Why this is downgraded from security's "forgery-impossible" framing:** The critic was right. Pydantic `model_validate` doesn't know its caller. Stack inspection at runtime is fragile. The honest framing is "convention + lint enforces single-mint-point + review catches violations" — which is still useful, and aligns with how the rest of the codebase enforces conventions (`import_linter`, `ruff`, mypy).
- **Tradeoffs accepted:** Determined plugin authors can bypass the lint. The threat model accepts this: plugins are first-party, in-tree, and reviewed; the capability mechanism is *audit infrastructure* (every capability use logs a `CapabilityUsed` event) rather than a hard isolation boundary. Phase 11 + Sigstore + microVM will close the residual gap.

### 15. `SandboxedPath` (`src/codegenie/plugins/sandbox_path.py`)

- **Provenance:** `[S+synth]` (security's design, with the symlink TOCTOU semantics clarified per critic Issue 5 on patterns).
- **Purpose:** Make path traversal unrepresentable. A `SandboxedPath` exists only if `Path.resolve(strict=True)` puts the result inside the jail directory after symlink resolution.
- **Interface:**
  ```python
  class SandboxedPath:
      @classmethod
      def create(cls, jail: Path, relative: str | Path) -> Result["SandboxedPath", PathEscape]: ...
      @property
      def absolute(self) -> Path: ...
      def open(self, mode: str) -> IO[Any]: ...    # always uses O_NOFOLLOW
  ```
- **Internal design:** Constructor resolves the path with `strict=True`; verifies `result.is_relative_to(jail.resolve())`; stores both. **`open()` always uses `O_NOFOLLOW`.** The critic correctly noted that `resolve(strict=True)` follows symlinks, so a symlink swap between construction and open is detected at `open()` time (`ELOOP`), not at construction. We document this honestly: `SandboxedPath` is "in-jail at construction" not "in-jail forever"; consumers handle `ELOOP` from `open()`.
- **Why this honest framing over security's "unrepresentable" claim:** The critic correctly attacked the "unrepresentable" framing. TOCTOU is real; `SandboxedPath` reduces it (every consumer goes through `O_NOFOLLOW`), it doesn't eliminate it. We say so.
- **Tradeoffs accepted:** Consumers must handle `OSError(errno=ELOOP)` from `open()`. Documented in API docstring + integration test fixture.

### 16. `EventLog` two-stream writer (`src/codegenie/plugins/events.py`)

- **Provenance:** `[synth]` (critic Issue 6 — all three designs missed ADR-0034's two-store split).
- **Purpose:** Emit typed Pydantic events. **Two streams**: `workflow_internal` (will live in Temporal history at Phase 9) and `workflow_spanning` (will live in Postgres side-channel at Phase 9).
- **Interface:**
  ```python
  class EventLog:
      def __init__(self, root: Path, workflow_id: WorkflowId) -> None: ...
      def emit_internal(self, event: WorkflowInternalEvent) -> EventId: ...
      def emit_spanning(self, event: WorkflowSpanningEvent) -> EventId: ...
      def replay(self) -> Iterator[Event]: ...

  WorkflowInternalEvent = (
      PluginsLoaded | PluginResolved | BundleBuilt | BundleEntryPromoted
      | RecipeMatched | RecipeApplied | RecipeSkipped | RecipeFailed
      | InstallStageOutcome | TestStageOutcome | LocalBranchWritten
      | RequiresHumanReview | AdapterDegraded | StageOutcome
  )
  WorkflowSpanningEvent = (
      WorkflowStarted | WorkflowCompleted | CostSandboxRun
      | CapabilityMinted | CapabilityUsed | PluginRegistryCorrupted
      | BenchReplayable
  )
  ```
- **Internal design:**
  - **`workflow_internal/<workflow_id>.jsonl.zst`** per workflow; events fsync at workflow end, not per emit. Phase 9 reads this file once and ports the records to Temporal history; the record envelopes match Temporal's event shape (timestamp + workflow_id + event_type + payload).
  - **`spanning/append.jsonl.zst`** is the append-only file shared across workflows. BLAKE3-chained for tamper evidence (security's design); `fcntl.flock` for concurrent-writer safety. Phase 9 reads this file into the Postgres `events` table.
  - Both streams use the same Pydantic envelopes; Phase 9's projector reads from both.
- **Why this two-stream framing:** ADR-0034 commits to hybrid event sourcing (Temporal for workflow-internal, Postgres for workflow-spanning). All three lens designs missed it. Phase 3 ships the *split* now so Phase 9 doesn't have to re-partition the event taxonomy. Workflow-spanning events: `WorkflowStarted`, `WorkflowCompleted`, `CostSandboxRun`, capability events, registry-corruption alerts (these affect operator/portfolio observability), and `BenchReplayable` (Phase 6.5's backfill source). Workflow-internal events: everything that lives inside a single workflow's state transitions (`PluginResolved`, `RecipeApplied`, etc.).
- **Tradeoffs accepted:** Two files per workflow instead of one. The split is cheap; Phase 9 thanks us.

### 17. Vulnerability-remediation plugin (`plugins/vulnerability-remediation--node--npm/`)

- **Provenance:** `[P+B+S]` (best-practices' directory shape; performance's `VulnIndex` use + recipe choice; security's `SubprocessJail` + capability discipline).
- **Purpose:** End-to-end deterministic vuln fix on a Node+npm repo. The first plugin.
- **Interface:**
  ```python
  # plugins/vulnerability-remediation--node--npm/api.py
  def run(state: PluginState, registry: PluginRegistry) -> Transform: ...

  manifest: PluginManifest = PluginManifest.from_yaml("./plugin.yaml")
  ```
- **Subgraph (5 nodes — best-practices' shape):**
  1. **`ingest_cve`** → `VulnIndex.lookup(...)`. Uses TCCM `provides.vuln_index_capabilities.cve_feed_parsers` registered by this plugin (and ONLY by this plugin — the kernel doesn't know about CVE feeds).
  2. **`match_recipe`** → lookup in `recipes/manifest.yaml`. Four recipes in Phase 3: `NpmLockfileSemverBumpRecipe`, `NpmPeerDepConflictRecipe` (returns `NotApplicable`), `NpmTransitiveOverridesRecipe` (edits `overrides` block), `NpmMajorBumpRefuseRecipe`.
  3. **`apply_recipe`** → `NpmLockfileRecipeEngine.apply(repo, plan, capability)`.
  4. **`stage6_validate`** → orchestrator-mediated; uses `SubprocessJail.run(npm install)` then `SubprocessJail.run(npm test)`, both in a temp worktree. Emits `InstallStageOutcome`, `TestStageOutcome`. Calls `TrustScorer.score(...)` → `TrustOutcome`. **This is what Phase 5 wraps.**
  5. **`write_branch`** → `LocalGitOps.create_patch_branch(GitLocalOpsCapability, repo, transform)`. `core.hooksPath=/dev/null` (security's defense — log `GitHooksDisabledForRun`). `GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=/bin/false`.
- **Recipes — Protocol, not ABC:** `RecipeProtocol.applies(cve, bundle) -> Applicability` (sum: `Applies(plan) | NotApplies(reason)`). The critic correctly attacked best-practices' `applies(...) -> bool`; we use a sum type. **Four recipes ship — not "one + future" — the Protocol is exercised against four implementations in production, not a hypothetical second one.**
- **Tradeoffs accepted:** Four recipes shipped; major-bump CVEs fall through to `NotApplicable` (Phase 4's LLM-fallback territory).

### 18. Universal HITL fallback (`plugins/universal--*--*/`)

- **Provenance:** `[P+S+B]` (convergent — all three picked this; we confirm).
- **Purpose:** Match any `(*,*,*)` no concrete plugin handles. Never silently fail.
- **Internal design:** Two files — `plugin.yaml` (precedence: 0, scope: `(*, *, *)`) and `subgraph/api.py` (~40 LOC: emit `RequiresHumanReview`, write `.codegenie/handoff/<workflow_id>.md` (sanitized via NFKC + ANSI/bidi strip from security), CLI exits 7).
- **Internal design (directory name):** **`plugins/universal--*--*/` confirmed.** The literal `*` is unfortunate for shell quoting but the alternative (`plugins/_fallback/` with manifest-declared wildcard scope) introduces "this directory's scope is encoded somewhere other than the name" inconsistency. The literal form is self-documenting: walking `plugins/` and seeing the directory name reveals the scope. Documented in `docs/plugins/authoring.md` that listing the fallback directory requires shell-quoting.
- **Tradeoffs accepted:** Shell-quoting friction. Acceptable.

### 19. Synthetic third plugin: `example--noop--*` (`tests/fixtures/plugins/example--noop--*/`)

- **Provenance:** `[synth]` (critic Issue 8 — best-practices flagged the gap, none of the three lens designs filled it).
- **Purpose:** Exercise every plugin contract surface (manifest, subgraph, adapters, recipe engine, TCCM, event emission) with a no-op implementation so the contract is tested against 3 plugins, not 1, before Phase 7 commits.
- **Internal design:** Lives under `tests/fixtures/plugins/`, NOT under `plugins/` (so production plugin discovery doesn't pick it up). Registered only by test fixtures (`tests/integration/test_three_plugin_contract.py`). Implements:
  - A `NoopAdapter` for each of the four adapter Protocols (returns empty lists; `confidence() == Trusted`).
  - A `NoopRecipe` Protocol implementation returning `RecipeOutcome.NotApplicable(reason=NoopAlwaysSkips)`.
  - A `NoopSubgraph` with two nodes (entry + emit).
  - A `tccm.yaml` declaring `provides.example_capabilities.greet: ...` to exercise the `provides`/`requires` machinery on a non-vuln capability — proves the kernel doesn't know about `vuln_index_capabilities` specifically.
- **Why ship this:** The plugin contract is the most expensive thing to discover-late. Phase 7 is the first real consumer of "extension by addition"; if anything in the Protocol is wrong, Phase 7's "zero edits to existing files" exit criterion fails. The synthetic third plugin is the bake test — if it exists and the kernel works, the contract is stable.
- **Tradeoffs accepted:** Adds a tests-only directory tree. ~400 LOC of fixture code. Worth it.

### 20. `PLUGINS.lock` signature (`plugins/PLUGINS.lock`)

- **Provenance:** `[S+synth]` (security's design; the critic was correct that it's "no signing" rather than "weak signing" — we frame it honestly).
- **Purpose:** Detect *accidental* corruption of the plugin tree (a developer's typo, a botched merge, an editor saving to the wrong directory). NOT a cryptographic supply-chain defense.
- **Internal design:** Checked-in file mapping `{plugin_id: sha256(sorted_tree_excluding_pycache)}`. Loader recomputes hashes at startup and refuses to load on mismatch. CODEOWNERS on `plugins/PLUGINS.lock` (a separate PR-review gate). **The critic correctly noted this is `package.lock` cosplay, not signing — a PR that updates both files passes the runtime check.** We rename the operator-facing label from "signature" to "integrity check" and accept the tradeoff. Phase 11 lands Sigstore.
- **Tradeoffs accepted:** Trust is in PR review + CODEOWNERS, not in cryptography. Honest framing in the operator runbook.

### 21. `remediation-report.yaml` (`src/codegenie/transforms/report.py`)

- **Provenance:** `[S+synth]` (critic Issue 1 — Phase 5 names `remediation-report.yaml` by name).
- **Purpose:** Per-workflow YAML index of the workflow's event streams + the validate-stage outcome. The artifact Phase 5 reads to decide retry/escalate.
- **Internal design:** Generated at workflow end. Schema (Pydantic):
  ```yaml
  workflow_id: ...
  cve_id: ...
  plugin_id: vulnerability-remediation--node--npm
  outcome:
    kind: validated | requires_human_review | not_applicable | failed
    transform: { transform_id, diff_bytes_sha256, branch_name }
    trust_outcome: { passed, failing, signals, confidence }
  events:
    workflow_internal: .codegenie/events/workflow-internal/<workflow_id>.jsonl.zst
    workflow_spanning_window: [start_event_id, end_event_id]
  audit_chain_head: <blake3>
  ```
- **Why ship this:** Phase 5 reads it. End of story.

---

## Data flow

A representative end-to-end run: `codegenie remediate ./my-node-repo --cve CVE-2024-21501`.

```
T=0        CLI parse, SandboxedPath.create(jail=repo)        ~10 ms        [S]
T+10       WorkflowId mint; emit WorkflowStarted (spanning)   ~5 ms        [S+synth]
T+15       Worker bootstrap                                  cold: 350 ms  [B+P]
              - import codegenie.plugins, codegenie.transforms
              - PluginLoader.load_all(["plugins/"]):
                  walks plugin.yaml files
                  validates PLUGINS.lock SHA-256
                  Pydantic.parse manifests (extra=forbid)
                  imports adapter modules
                  registers via @register_plugin → PluginRegistry instance
              - Emit PluginsLoaded (spanning)
              (warm: ~5 ms)
T+365      RepoContextLoader.load(repo)                       ~8 ms        [P]
              - mmap .scip
              - JSON-shadow .codegenie/context
T+373      Resolver.resolve(VULN, JS, NPM)                    ~30 μs       [B]
              - returns ConcreteResolution(
                  plugin=vulnerability-remediation--node--npm,
                  extends_chain=[],
                  composed_tccm=..., composed_adapters=...)
              - emit PluginResolved (internal)
T+373      CapabilityMint(plugin, scope)                      ~30 μs       [S]
              - returns CapabilityBundle(FsReadWrite, NpmInstall,
                                          GitLocalOps)
              - emit CapabilityMinted (spanning) × 3
T+373      VulnIndex.lookup(express, npm) for CVE-2024-21501  ~3 ms        [P]
              - returns VulnerabilityRecord(fixed_in=^4.19.2, ...)
T+376      BundleBuilder.build(...)                           cold: 220 ms [P+synth]
              - cache miss; key includes vuln_index.digest
              - Sem(min(4, cpu_count)) over must_read queries:
                  scip.refs(...)             ~80 ms
                  import_graph.reverse_lookup ~40 ms
                  dep_graph.consumers         ~30 ms
                  test_inventory.tests_…      ~50 ms
              - SCIP confidence=Trusted; no fallback fires
              - emit BundleBuilt (internal)
              warm: 3 ms (cache hit)
T+596      Plugin subgraph: ingest_cve → match_recipe → apply
              - match_recipe: NpmLockfileSemverBumpRecipe matches
              - apply_recipe: NpmLockfileRecipeEngine.apply(...)
                  - edit package.json in mem            2 ms
                  - hardlink-copy to tmpdir             10 ms
                  - SubprocessJail.run(npm install
                       --package-lock-only
                       --ignore-scripts
                       --no-audit
                       --prefer-offline)               5–6 s              [S]
                  - parse new lockfile                  20 ms
                  - return NpmLockfileTransform(...)
              - emit RecipeMatched, RecipeApplied (internal)
T+6.6 s    Stage 6 — Validate (the wrap-target Phase 5 reuses)             [synth]
              - Apply transform to temp worktree       50 ms
              - SubprocessJail.run(npm install)         ~5 s     (full)
              - SubprocessJail.run(npm test)            ~3 s
              - Collect TrustSignal: build, install, tests,
                lockfile_policy, cve_delta
              - TrustScorer.score(signals) → TrustOutcome(
                   passed=True, failing=[], confidence=high)
              - emit StageOutcome (internal)
T+14.6 s   LocalGitOps.create_patch_branch(...)               150 ms       [S]
              - core.hooksPath=/dev/null
              - GIT_TERMINAL_PROMPT=0, GIT_ASKPASS=/bin/false
              - branch: codegenie/cve-2024-21501-<short>
              - commit (sanitized message)
              - emit LocalBranchWritten (internal)
T+14.75 s  report.write(...)                                  20 ms        [synth]
              - remediation-report.yaml indexes streams + outcome
              - audit-chain BLAKE3 head computed
T+14.77 s  EventLog.flush(); emit WorkflowCompleted (spanning) 20 ms
T+14.79 s  CLI exit                                           ~5 ms

Total warm:                                                   14.8 s p50
Total cold:                                                   15.2 s p50
Total p95 (includes degraded-adapter fallback + test slowness): ~30 s
```

**Where parallelism is extracted:**
1. `BundleBuilder.build` runs `must_read` queries concurrently under `Semaphore(min(4, os.cpu_count()))`. **No hedged race** — fallback fires only on `Degraded`.
2. The `npm install --package-lock-only` (Stage 4) and the validate-stage `npm install` (Stage 6) are serial; the validate-stage `npm install` re-resolves the full tree in the temp worktree. This is the wall-clock floor.

**Where determinism is enforced (commitment §2.4):**
- Bundle cache key includes `vuln_index.digest` (critic's Hidden Assumption #3 fix).
- No hedged race — same inputs → same Bundle bytes (critic Issue 7 fix).
- Recipe outputs are typed and content-addressed (`Transform.transform_id = blake3(diff_bytes)`).
- Event sequences are deterministic up to timestamps + `workflow_id` (replay-test asserts).

---

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery | Source |
|---|---|---|---|---|
| Plugin manifest invalid | `PluginManifest.from_yaml` Pydantic validation | Worker refuses to start | Exit code 4; CLI prints file + field | `[B]` |
| Plugin `extends` cycle | `Resolver` cycle check (visited set) | Refuse all plugins in cycle | `PluginExtendsCycle(chain)`; exit 4 | `[B+S]` |
| `PLUGINS.lock` SHA mismatch | Loader recomputes per-plugin tree SHA-256 at startup | Refuse to load mismatched plugin | `PluginRejected(integrity_mismatch)`; exit 4 | `[S]` |
| Adapter import unresolvable | Loader `importlib.import_module` raises | Worker refuses to start | Exit 4 with import path; ADR-0031 §schema enforcement | `[B+S]` |
| No concrete plugin matches `(task, lang, bt)` | `Resolver.resolve` returns `UniversalFallbackResolution` | Universal fallback emits `RequiresHumanReview`; CLI exit 7 | Sanitized markdown handoff under `.codegenie/handoff/` | `[P+S+B]` |
| Adapter `confidence() == Degraded` | `BundleBuilder` dispatches TCCM-declared fallback adapter; emit `AdapterDegraded` (internal) | Workflow continues; `TrustOutcome.confidence` propagates `degraded` | `[B+P+synth]` |
| Adapter `confidence() == Unavailable` AND no TCCM fallback | `BundleBuilder` | Workflow proceeds with `LowConfidenceAnswerUsed` event | Operator sees in `remediation-report.yaml` | `[B+synth]` |
| `IndexHealthProbe` (Phase 2 B2) `Stale` | `NodeScipAdapter.confidence() == Degraded(ScipIndexStale)` | TCCM fallback fires → `import_graph.reverse_lookup` | `AdapterDegraded` event | `[B+P]` |
| `npm install --package-lock-only` timeout (>60 s) | `SubprocessJail.run` `time_budget_s` cap | Subprocess killed; one retry with explicit registry | If still fails → fallback to UniversalFallbackPlugin path | `[P+S]` |
| `npm install --package-lock-only` non-zero exit | `JailedSubprocessResult.Completed(exit_code != 0)` | `RecipeOutcome.Failed(InstallError(stderr))` | Stage 6 reports `passed=False`; Phase 5 retries (Phase 3 alone: no retry) | `[S+synth]` |
| `npm test` non-zero exit | Same | `TestSignal(passed=False)`; `TrustScorer.score → TrustOutcome.passed=False` | Stage 6 returns `Validated(passed=False, failing=["tests"])`; Phase 5 retries via `GateRunner` | `[synth — critic Issue 2]` |
| Postinstall script attempts to run despite `--ignore-scripts` | bwrap/sandbox-exec containment (npm doesn't get the chance) | Script never runs; canary file unwritten | Tested via deliberately-malicious fixture | `[S]` |
| Egress to non-registry host inside jail | Network namespace policy / sandbox-exec deny | Connection blocked | `JailedSubprocessResult.NetworkDenied(host)` | `[S]` |
| `package.json` parse fails (malformed JSON / size > 1 MiB / depth > 16) | `NpmManifest.parse` smart constructor | `RecipeOutcome.Failed(MalformedPackageJson)`; exit 3 | `[S]` |
| Lockfile re-resolve introduces NEW CVE | `cve_delta` signal compares pre/post via `VulnIndex` | `CveDeltaSignal(passed=False)`; `TrustOutcome.passed=False` | Refuse to commit; exit 4 | `[P+S]` |
| Symlink TOCTOU between `SandboxedPath.create` and `open()` | `O_NOFOLLOW` open returns `ELOOP` | Caller handles `OSError(errno=ELOOP)` | `FilesystemRaceDetected` event; workflow aborts | `[S+synth]` |
| Git hook in target repo attempts to run on commit | `core.hooksPath=/dev/null` set per run | Hooks not executed | `GitHooksDisabledForRun` event visible in handoff | `[S]` |
| Concurrent run racing same repo | `.codegenie/.lock` flock | Second invocation exits | `WorkflowConcurrent` exit code | `[S]` |
| Event-log corruption (BLAKE3 chain break on spanning stream) | `codegenie audit verify` | Workflow refuses to start | Operator investigates; restoration from backup | `[S]` |
| CVE feed never refreshed (`vuln-index.sqlite` digest > 7 days old) | `VulnIndex.digest()` checked at start | Emit warning + `StaleVulnIndex` event | Workflow continues (warn, not block) | `[P]` |
| `Capability` constructed outside `capabilities.mint(...)` | ruff custom rule | CI hard-block | PR rejected | `[S+synth]` |
| Disk fills mid-write | Atomic-rename pattern; pre-write `os.statvfs` check | Partial write never visible | Rollback branch; `WorkflowFailed(disk_full)` | `[S]` |
| Adversarial repo content in `package.json` (zero-width chars, NUL bytes) | npm-grammar regex on `name` field; NFKC normalize | Reject at parse | `RecipeFailed(invalid_repo_content)` | `[S]` |

Three deliberately-not-Phase-3 failures (handed off):
- **Patch produces working diff but tests fail under retry-1, recover on retry-2** → Phase 5's `GateRunner` three-retry envelope wraps `_validate_stage6`.
- **Major-version-bump CVE** → `NpmMajorBumpRefuseRecipe` returns `NotApplicable`; Phase 4's LLM-fallback territory.
- **Compromised plugin author lands malicious PR + matching `PLUGINS.lock` update** → out of band: CODEOWNERS + PR review + Phase 11 Sigstore.

---

## Resource & cost profile

Numbers against `fixtures/vuln-repos/express-cve-2024-21501` (~800 files, npm v10, one direct-dep CVE) on a 2024 MacBook M3 Pro / 36 GB / NVMe. Linux orchestrator numbers within ±10%.

- **Tokens per run:** **0.** Hard zero, asserted by CI fence.
- **Wall-clock per run (warm worker, includes `npm install` AND `npm test` inside `SubprocessJail`):**
  - p50: **14.8 s** (NpmLockfile path + jail boot + install + test pass)
  - p95: **~30 s** (slow registry; large test suite; degraded SCIP)
  - p99 (cold registry, slow disk): **~60 s**
- **Wall-clock per run (cold worker):** p50 ~15.2 s (~350 ms one-time bootstrap).
- **Memory per worker:** steady-state ~320 MB RSS; npm subprocess peak ~800 MB during install; total worker memory ceiling **800 MB peak / 400 MB steady**.
- **Storage growth rate:**
  - `.codegenie/cache/bundles/`: ~50 KB per entry × ~10 entries per repo per CVE = ~500 KB. GC after 7 days mtime.
  - `.codegenie/events/workflow-internal/`: ~5 KB per workflow zstd. 200,000 workflows = 1 GB.
  - `.codegenie/events/spanning/append.jsonl.zst`: ~1 KB per workflow.
  - `vuln-index.sqlite`: ~50 MB steady; grows ~50 MB/yr.
  - `remediation-report.yaml`: ~3 KB per workflow.
- **CPU profile:**
  - ~70% in `npm` subprocesses (install + test)
  - ~10% in Python (Bundle, recipe match, scoring)
  - ~10% in bwrap/sandbox-exec setup + teardown
  - ~5% in mmap'd file reads (SCIP, dep_graph)
  - ~5% in I/O wait (lockfile writes, event writes, BLAKE3 chaining)

**Cost-of-security delta vs unsecured baseline:** ~1.2 s per workflow (bwrap/sandbox-exec setup × ~3 invocations + BLAKE3 chain + SHA-256 of plugin tree). The unsecured alternative (running `npm install` with postinstall scripts on the orchestrator host) is rejected on threat-model grounds — see §Failure modes.

**Cost-of-determinism delta vs hedged-race:** ~100 ms p95 on `Degraded` paths (rare). The deterministic path costs nothing on the common Trusted path; the rare `Degraded` path serializes primary + fallback. Trade made — commitment §2.4 is veto-strength.

---

## Test plan

### Unit tests

- `tests/unit/transforms/test_orchestrator.py` — `RemediationOrchestrator.run(...)` against the 5-stage pipeline; each stage individually mocked; Stage 6 returns `Validated(passed=True/False)`; orchestrator returns the right `RemediationOutcome` variant.
- `tests/unit/transforms/test_trust_scorer.py` — strict-AND for all `2^N` signal combinations; `confidence` propagation from `AdapterDegraded` events.
- `tests/unit/transforms/test_apply_context.py` — `prior_attempts: list[AttemptSummary] = []` default; explicit-pass round-trip; contract-snapshot test for Phase 5's ADR-P5-002 amendment.
- `tests/unit/transforms/test_recipe_engine.py` — `NpmLockfileRecipeEngine.apply` against fixture lockfiles; `OpenRewriteRecipeEngine` against the Phase-7-tagged Dockerfile fixture.
- `tests/unit/transforms/test_sandbox_jail.py` — Linux bwrap and macOS sandbox-exec adapters; `JailedSubprocessResult` discrimination for each error variant.
- `tests/unit/plugins/test_manifest.py` — `PluginManifest.from_yaml` for ~20 valid + ~15 invalid YAML fixtures.
- `tests/unit/plugins/test_scope.py` — `Concrete | Wildcard` matches algebra; property test on `specificity` partial order.
- `tests/unit/plugins/test_resolver.py` — exact match > wildcard; precedence ties; `extends` chain walk; no-match → `UniversalFallbackResolution`.
- `tests/unit/plugins/test_registry.py` — collision raises `PluginAlreadyRegistered`; fixture-isolated registry per test.
- `tests/unit/plugins/test_bundle.py` — Bundle builder dispatches; degraded adapter triggers declared fallback **deterministically** (not raced); `vuln_index.digest` in cache key.
- `tests/unit/plugins/test_capabilities.py` — `mint(...)` is the only construction path; `CapabilityUsed` event emitted on every `apply` call.
- `tests/unit/plugins/test_sandbox_path.py` — TOCTOU symlink swap raises `ELOOP` at `open()` time; `is_relative_to` jail enforcement.
- `tests/unit/plugins/test_events.py` — two-stream writer; BLAKE3 chain on spanning stream; replay round-trip.
- `tests/unit/vuln_index/test_parsers.py` — NVD/GHSA/OSV produce the same `CVERecord` for equivalent advisories; size/depth caps neutralize malformed input.
- `tests/unit/vuln_index/test_query.py` — `VulnIndex.lookup` p99 ≤ 5 ms on a populated sqlite.
- `tests/unit/vulnerability_remediation_node_npm/test_recipes.py` — each of the four recipes against fixture inputs; `RecipeOutcome` discriminated correctly.
- `tests/unit/vulnerability_remediation_node_npm/test_adapters.py` — each adapter against fixture `RepoContext`; SCIP-stale → tree-sitter via TCCM fallback.
- `tests/unit/universal_fallback/test_emit.py` — emits `RequiresHumanReview` with the correct sanitized markdown; exit code 7.

### Integration tests

- `tests/integration/test_phase5_contract_snapshot.py` — asserts `RemediationOrchestrator`, `TrustScorer`, `Transform`, `ApplyContext`, `RecipeEngine`, `remediation-report.yaml` exist; their signatures match what Phase 5's `GateRunner.run`, `StrictAndGate.evaluate`, etc. consume. **This is the integration handshake test the critic mandated.**
- `tests/integration/test_three_plugin_contract.py` — loads the production plugins + the synthetic `example--noop--*` fixture plugin; asserts the kernel resolves all three; exercises every contract surface (manifest, subgraph, adapters, recipes, TCCM `provides`/`requires`). The critic's Issue 8 resolution.
- `tests/integration/test_end_to_end_express_cve.py` — fixture Node.js repo + CVE-2024-21501; runs `codegenie remediate`; asserts branch created; lockfile diff matches golden; `npm install` exits 0 inside jail; `npm test` exits 0 inside jail (= meets roadmap exit criterion); event stream is `WorkflowStarted → PluginsLoaded → PluginResolved → BundleBuilt → RecipeMatched → RecipeApplied → InstallStageOutcome(passed=True) → TestStageOutcome(passed=True) → StageOutcome(passed=True) → LocalBranchWritten → WorkflowCompleted`.
- `tests/integration/test_universal_fallback.py` — fixture Rust repo + vuln task class → universal fallback fires; `RequiresHumanReview`; exit 7.
- `tests/integration/test_peer_dep_conflict.py` — fixture with peer-dep conflict; `NpmPeerDepConflictRecipe` returns `NotApplicable`; exit 3.
- `tests/integration/test_install_fails.py` — fixture with deliberately-incompatible deps; `InstallStageOutcome(passed=False)`; `TrustOutcome.passed=False`; no branch; orchestrator returns `Validated(passed=False)` so Phase 5 can retry.
- `tests/integration/test_test_fails.py` — fixture where install succeeds but tests fail; `TestStageOutcome(passed=False)`; same shape.
- `tests/integration/test_index_health_stale.py` — Phase 2 stale-SCIP fixture; `AdapterDegraded(primary=scip)`; TCCM fallback fires; `TrustOutcome.confidence == degraded`.
- `tests/integration/test_bundle_cache_includes_vuln_index_digest.py` — refresh `vuln-index.sqlite` between two runs; cache key changes; second run does NOT return stale answer.
- `tests/integration/test_event_replay.py` — record events; replay; assert post-state byte-equal (modulo timestamps + workflow_id).

### Property tests (Hypothesis)

- `BundleCacheKey` round-trips: same `(plugin_id, plugin_version, primitive, args, repo_ctx_digest, scip_digest, vuln_index_digest)` → same key (50 runs).
- `RecipePlan` round-trip via Pydantic.
- `SemverRange.intersects` reflexive/symmetric/wildcard-no-op.
- `Resolver.resolve` invariant: returns `ConcreteResolution` whose `plugin.scope.matches(task, lang, build)` is True, OR returns `UniversalFallbackResolution(universal_plugin=plugins/universal--*--*)`.
- `EventLog` round-trip: `for any event_stream, replay(write_all(stream)) == stream`.
- **Determinism property:** `for any (repo_snapshot, cve_record, plugin_version, recipe_version, vuln_index_digest), apply_transform()` produces byte-identical `transform.diff_bytes` across 100 runs.

### Adversarial tests (lifted from security's design, narrowed scope)

- CVE-record size cap (1 MiB) rejection.
- `package.json` size cap (1 MiB), depth cap (16) rejection.
- `package-lock.json` size cap (32 MiB), depth cap (24) rejection.
- `--ignore-scripts` enforcement: malicious postinstall canary fixture; assert canary file not written.
- Egress denial: malicious `.npmrc` redirecting registry to attacker host; assert connection blocked.
- Symlink TOCTOU: deliberate symlink-swap fixture; assert `O_NOFOLLOW` raises `ELOOP`.
- Capability fence: `tests/static/test_capability_fence.py` runs ruff custom rule against the codebase.

### Fence-CI

- **No LLM SDK** under `plugins/vulnerability-remediation--node--npm/`, `plugins/universal--*--*/`, `src/codegenie/plugins/`, `src/codegenie/transforms/` — `import_linter` contract.
- **Kernel frozen:** `tests/fence/test_plugin_kernel_frozen.py` git-diff fence asserts no edits to `src/codegenie/plugins/loader.py`, `resolver.py`, `registry.py` outside an ADR-anchored allowlist.
- **Universal fallback present:** asserts `plugins/universal--*--*/plugin.yaml` parses.
- **Every plugin's adapters resolve:** load test fails CI on broken import.
- **Three-plugin contract:** `tests/integration/test_three_plugin_contract.py` is a required CI job.

### Performance regression budgets (CI relative-budget, not absolute walls)

| Bench | Budget (CI) | Failure means |
|---|---|---|
| `bench_plugin_registry_build` | < 500 ms for 3 plugins | Pydantic bloat or filesystem-walk regression |
| `bench_bundle_builder_warm` | < 5 ms | Cache key broke or write/read regression |
| `bench_bundle_builder_cold` | < 300 ms | Adapter regression |
| `bench_vuln_index_lookup` | < 10 ms p99 over 100 lookups | Index plan regression |
| `bench_recipe_match` | < 60 ms p95 | Semver arithmetic regression |
| `bench_event_appender_throughput` | > 30,000 events/sec | Zstd or Pydantic encode regression |
| `bench_workflow_e2e_warm` | < 20 s p50, < 35 s p95 | Composite regression |

Relative-budget assertion: > 25% regression vs. rolling 7-day mean fails CI.

### Phase 6.5 backfill readiness

- Every Phase 3 workflow emits `BenchReplayable(input_snapshot_fingerprint, transform_bytes_sha256, outcome_kind)` on the spanning stream. Phase 6.5's `codegenie eval backfill --task-class=vuln-remediation --from-events` reads this stream and produces `bench/vuln-remediation/cases/CVE-*.toml` files mechanically.

---

## Design patterns applied

| Decision | Pattern | Why this *here* | Source |
|---|---|---|---|
| `PluginRegistry` instance + `@register_plugin` decorator targeting `default_registry` with fixture-isolation in tests | **Registry pattern + decorator data + Open/Closed at the file boundary** | Adding a third plugin is a new directory + decorator call; no edit to the resolver. Phase 6.5's `TaskClassRegistry` adopted this exact shape; Phase 5's `SignalKind` registry too. Three siblings, one pattern. | `[B+synth]` |
| `Plugin`, `Adapter` Protocols (no `cve_feed_parsers()` on `Plugin`); `RecipeEngine`, `RecipeProtocol` Protocols | **Dependency inversion via `typing.Protocol`** | Plugins/adapters/recipes are multi-implementation surfaces by definition; Protocols give duck-typed flexibility while `mypy --strict` enforces. Composition over inheritance (ADR-0033). | `[B+synth — critic Issue 4]` |
| `Transform` ABC | **Abstract base class** (the small exception) | Phase 5's `GateContext.transform_output` will `isinstance(t, Transform)`; the ABC is the typed marker. Protocol would work but `isinstance` checks against Protocols require `runtime_checkable` and runtime-overhead. `Transform` is a sealed hierarchy. | `[synth]` |
| `PluginResolution`, `RecipeOutcome`, `TrustOutcome`, `RemediationOutcome`, `AdapterConfidence`, `JailedSubprocessResult`, `Applicability` as tagged unions (Pydantic discriminated unions + `match` + `assert_never`) | **Tagged union / sum type** | Every Phase 3 state machine has >2 variants. Booleans for state allow illegal combinations. ADR-0033 §3-4 is the rule; this is its biggest application yet. | `[B+S+synth]` |
| `PluginScope.task_class: Concrete \| Wildcard` (sum type, NOT `Literal["*"]`) | **Make illegal states unrepresentable** | Best-practices admitted the `Literal["*"]` was for YAML aesthetics; the critic correctly attacked. `NewType | Literal["*"]` collapses to `str` at runtime. The sum type is one `match` statement and prevents typo'd wildcards. | `[synth — critic pattern Issue]` |
| `BundleBuilder` content-addressed cache with `vuln_index.digest` in the key | **Event sourcing + content-addressed registry** | All inputs are immutable digests. Same key → same Bundle. Disk format `msgpack+zstd` is durable across worker restarts. | `[P+synth]` |
| `NpmLockfileRecipeEngine` (default) + `OpenRewriteRecipeEngine` (scaffolded stub w/ Phase-7 fixture) | **Strategy + Plugin (registry pattern)** | Two genuinely-different implementations from day one — not "one + future." Phase 7 fleshes out the Java/Dockerfile path; Phase 3 ships the scaffold + fixture. Premature pluggability avoided by shipping both. | `[P+synth — critic Issue 3]` |
| `SubprocessJail` Port + `BwrapAdapter` (Linux) + `SandboxExecAdapter` (macOS) | **Hexagonal Port + Adapter** | Linux and macOS substrates have genuinely different APIs; Phase 5's future Firecracker adapter will be a third. The Port keeps Phase 3 callers substrate-agnostic. | `[S]` |
| Capability tokens (`NpmInstallCapability`, `FsReadWriteCapability`, `GitLocalOpsCapability`) | **Capability pattern + Smart constructor** (audit, not isolation) | Honest framing: capability *carries* its scope; consumers receive it as an argument; every use emits `CapabilityUsed`. Lint enforces single-mint-point. This is audit infrastructure, not unforgeable runtime isolation (critic was right; we adjust the framing). | `[S+synth]` |
| `SandboxedPath` (smart constructor + `O_NOFOLLOW` discipline) | **Smart constructor + Newtype** | Constructor proves "in jail at validation time"; `O_NOFOLLOW` open catches TOCTOU. Honest framing per critic: not "unrepresentable forever," just "in-jail at construction." | `[S+synth]` |
| Every domain primitive (`PluginId`, `RecipeId`, `CveId`, `PackageId`, `BundleId`, `TransformId`, `WorkflowId`, `EventId`, `BranchName`, `BlobDigest`, …) as `NewType` or Pydantic-validated wrapper | **Newtype** | `WorkflowId`/`BundleId` swaps are static type errors. ADR-0033 §1. The critic flagged "missed `Newtype` on `WorkflowId`" across all three designs; we adopt it. | `[B+synth]` |
| External-boundary parsers (`PluginManifest.from_yaml`, `PluginScope.parse`, `CveRecord.parse_nvd|ghsa|osv`, `BranchName.parse`) returning `Result[T, ParseError]` | **Smart constructor** | Every external-boundary deserializer. Pydantic + classmethod is the language idiom. | `[B+S]` |
| `EventLog` two-stream writer (workflow-internal vs workflow-spanning), BLAKE3-chained on the spanning stream | **Event sourcing + Adapter (file → Phase 9's Temporal+Postgres split)** | ADR-0034's hybrid model: Temporal for workflow-internal, Postgres for workflow-spanning. Phase 3 ships the split now so Phase 9 doesn't re-partition. | `[synth — critic Issue 6]` |
| 5-node plugin subgraph (`ingest_cve → match_recipe → apply_recipe → stage6_validate → write_branch`) | **Pipeline / Chain of responsibility** | Narrow per-stage contracts; each can short-circuit with `RecipeOutcome`. Phase 6 will wrap in LangGraph 1-to-1 (function signatures port). | `[B]` |
| Synthetic third plugin (`example--noop--*`) | **Contract test / Worked example** | The plugin contract is the most expensive thing to discover-late; the synthetic third plugin makes Phase 7's "zero edits" exit criterion testable at *Phase 3* time. | `[synth — critic Issue 8]` |

### Patterns considered and deliberately rejected

- **No LangGraph in Phase 3.** Phase 6 owns it (ADR-0002). The 5-node subgraph is typed step functions Phase 6 wraps; the runtime is a plain `for`-loop. Critic correctly attacked best-practices' LangGraph import.
- **No NCU (`npm-check-updates`).** NCU's job is "what versions are available?" — Phase 3 already knows the target from the CVE record. Calling NCU adds registry I/O + node-startup we don't need. Critic correctly noted all three designs converged here and missed the question.
- **No Visitor over `CveRecord` or `Transform`.** Pattern matching on discriminated unions handles dispatch; Visitor would add ceremony.
- **No Factory for plugin construction.** `@register_plugin` decorates a fully-built instance; there's no construction graph to abstract.
- **No DI container (`punq`, `dependency-injector`).** Plugin loading is one filesystem walk + `importlib`. A DI container is a 5x increase in indirection for zero capability we need.
- **No verdict cache in Phase 3.** Phase 9's territory once Temporal idempotency lands (Phase 5's synthesis also rejected verdict cache).
- **No SecurityManager + JVM ceremony.** SecurityManager is deprecated; bwrap/sandbox-exec is the real defense. The OpenRewrite scaffold subprocess-runs the JVM under `SubprocessJail`, period. No `-Djava.security.manager=default`, no policy files. Critic correctly attacked security's defense-in-depth-of-deprecated-API.
- **No hot-reload of plugins.** Worker process must restart on plugin changes. Phase 11's `--reload-plugins` flag will land for dev DX.
- **No service-registry / pub-sub on the event log.** One consumer (the writer) in Phase 3; Phase 9 adds projections.
- **No hedged-race fallback in `BundleBuilder`.** Determinism wins.

### Anti-patterns avoided

- **Pattern soup:** ~17 named components total (vs. performance's 16). Each earns its name (registry, builder, jail, scorer, …) or is a domain object (Bundle, Transform). No `*Factory`, `*Builder`, `*Provider` ceremony.
- **Premature pluggability:** `RecipeEngine` Protocol has *two* implementations from day one (`NpmLockfileRecipeEngine` + `OpenRewriteRecipeEngine`); `RecipeProtocol` has *four* (`SemverBump`, `PeerDepConflict`, `TransitiveOverrides`, `MajorBumpRefuse`). The Protocols pay rent.
- **Stringly-typed identifiers:** All domain primitives are `NewType`d (per ADR-0033). External-boundary parses go through smart constructors returning `Result`.
- **Untyped `dict[str, Any]`:** Forbidden by fence-CI under `plugins/` and `src/codegenie/{plugins,transforms}/`. Pydantic models or typed dataclasses everywhere.
- **Boolean flags on public methods:** Sum types replace them (`Applicability`, `RecipeOutcome`, `TrustOutcome`).
- **Tag-and-dispatch without sum type:** Every `kind: Literal[...]` field is a Pydantic discriminated union; `assert_never` in `match` blocks.
- **Capability passed through ten frames:** `CapabilityBundle` is *one* object carried in `ApplyContext`. Recipe engines unpack it locally. The critic's "context object trying to escape" attack on security's pure-per-frame design is heeded.
- **Side effects in constructors / import time:** `@register_plugin` mutates a *passed-in* registry (default_registry in production); the registry is an instance, not a module-level global. Best-practices' shape vs. performance's `_REGISTRY: dict = {}`.
- **String-typed enforcement of "no `git push`":** `GitLocalOpsCapability` does not have a `push` operation; minting one is type-impossible. The critic correctly attacked best-practices for "string-typed enforcement."

---

## Risks (top 5)

1. **The `Plugin` Protocol's `provides`/`requires` TCCM machinery is new in Phase 3 and untested at scale.** Phase 7 will be the first second consumer. *Mitigation:* the synthetic third plugin (`example--noop--*`) exercises the machinery with a non-vuln capability (`example_capabilities.greet`); integration test asserts kernel doesn't know about either CVE feeds or "greet." If Phase 7 discovers a Protocol gap, ADR amendment is required, but the synthetic-plugin bake should catch it.

2. **Phase 5's contract snapshot is a hard handshake.** Phase 5's already-merged final-design names `RemediationOrchestrator`, `TrustScorer`, `Transform`, `ApplyContext`, `RecipeEngine`, `remediation-report.yaml` by name. If our shapes drift from Phase 5's expectations, Phase 5 cannot ship. *Mitigation:* `tests/integration/test_phase5_contract_snapshot.py` asserts the public surface; CI gates on it; ADR-P5-002 amends `ApplyContext` additively at Phase 5 time (the optional `prior_attempts` field is in Phase 3 already).

3. **`SubprocessJail` macOS substrate is deprecation-flagged.** sandbox-exec's profile language is undocumented and Apple has signaled removal. *Mitigation:* Phase 5 replaces with Lima-microVM-on-macOS per its already-merged design. Phase 3 accepts the residual risk for developer-laptop runs; Linux/CI is the production substrate.

4. **`OpenRewriteRecipeEngine` is a stub; Phase 7 will discover whether the Protocol generalizes.** *Mitigation:* the Phase-7-tagged Dockerfile fixture is real (not a mock); the JVM subprocess actually runs OpenRewrite against it; the `Transform` produced is byte-validated. If Phase 7 finds a Protocol gap, ADR amendment + additive extension; not a "rewrite Phase 3" path.

5. **Performance budget (p50 ≤ 18 s) is aspirational; CI hardware variance is real.** *Mitigation:* relative-budget assertions vs. 7-day rolling mean (not absolute walls); `CODEGENIE_BUNDLE_CONCURRENCY` env-var escape hatch; benches are advisory, not blocking on first failure.

---

## Synthesis ledger

### Vertex count

- Performance design: **34** vertices extracted (8 components × ~4 design decisions each + 6 cross-cutting bench/cache/cost choices)
- Security design: **41** vertices extracted (9 components × ~3-4 decisions each + threat-model choices)
- Best-practices design: **38** vertices extracted (10 components × ~3-4 decisions each + conventions/fence choices)
- Total: **113**

### Edges

- AGREE: **24** (universal fallback name, BLAKE3 audit chain shape, plugin discovery via filesystem walk, `frozen=True` Pydantic models, no LLM in Phase 3, `@register_plugin` decorator pattern, …)
- CONFLICT: **22** (default recipe engine, `npm test` in Phase 3 or not, sandbox substrate, hedged-race-vs-deterministic-fallback, LangGraph in Phase 3, ApplyContext shape, `Plugin` Protocol surface, EventLog one-stream-vs-two, OpenRewrite-shipped-or-deferred, `PluginScope` Literal-vs-Wildcard, capability "unforgeable" claim, `SandboxedPath` "unrepresentable" claim, plugin registry singleton-vs-instance, three-plugin contract test, NCU-vs-pure-Python, sandboxed prefetch flow, …)
- COMPLEMENT: **19** (security's `SubprocessJail` + performance's `VulnIndex` are different dimensions; best-practices' `import_linter` fence + security's `--ignore-scripts` env enforcement are different defenses for the same boundary; performance's content-addressed cache + best-practices' typed Bundle are different sides of the same component; …)
- SUBSUME: **9** (best-practices' `PluginManifest.from_yaml` smart constructor subsumes security's separately-described "schema validation"; performance's content-addressed Bundle cache subsumes best-practices' "no streaming in Bundle"; …)

### Conflict-resolution table

| Dimension | [P] picks | [S] picks | [B] picks | Winner | Exit-fit | Roadmap-fit | Commitments-fit | Critic-fit | Pattern-fit | Sum |
|---|---|---|---|---|---|---|---|---|---|---|
| Phase 5 integration: `RemediationOrchestrator`/`TrustScorer`/`Transform`/`ApplyContext` | none shipped | none shipped | none shipped | **`[synth]` — SHIP them all by name** | 3 | 3 | 3 | 3 | 3 | **15** |
| `npm test` in Phase 3 | implicitly skip | explicitly defer to Phase 5 | run `npm ci` only | **`[synth]` — RUN both `npm install` and `npm test` inside `SubprocessJail`** | 3 | 3 | 3 | 3 | 2 | **14** |
| Default recipe engine (npm) | Pure-Python `NpmRecipeEngine` | Pure-Python `NpmDepBumpRecipe` (preferred); OR JVM (fallback) | NCU (`npm-check-updates`) shell-out | **`[P+S]` — Pure-Python `NpmLockfileRecipeEngine`** | 3 | 3 | 3 | 3 | 3 | **15** |
| `OpenRewriteRecipeEngine` ship-or-defer | Defer to Phase 7 (Protocol only) | Ship as JVM fallback | Defer to "later" (not scaffolded) | **`[synth]` — SCAFFOLD with Phase-7-fixture; not used by Phase 3 npm path** | 3 | 3 | 3 | 3 | 3 | **15** |
| `BundleBuilder` fallback semantics | Hedged-race (parallel) | Declarative (serial on Degraded) | Declarative (serial on Degraded) | **`[S+B]` — Declarative serial; commitment §2.4 vetoes hedged-race** | 3 | 3 | 3 | 3 | 3 | **15** |
| `PluginRegistry` shape | Module-level mutable singleton | Instance returned from loader | Instance + `default_registry` + fixture-isolation | **`[B]` — Instance + default_registry + fixture-isolation** | 3 | 3 | 3 | 3 | 3 | **15** |
| `Plugin` Protocol surface | (not specified — performance shipped a manifest + adapter dispatch) | (not specified — security shipped capability-typed nodes) | `manifest`, `build_subgraph`, `adapters`, `cve_feed_parsers` (4 methods, last one task-class-specific) | **`[synth]` — `manifest`, `build_subgraph(registry)`, `adapters()`, `transforms()`; cve_feed_parsers moves to TCCM `provides`** | 3 | 3 | 3 | 3 | 3 | **15** |
| `PluginScope` wildcard encoding | (not specified — performance treats `*` as fallback path) | (not specified) | `Literal["*"] \| NewType(...)` | **`[synth]` — `Concrete \| Wildcard` sum type** | 2 | 3 | 3 | 3 | 3 | **14** |
| Sandbox for npm | None (Phase 5 owns it) | bwrap (Linux) + sandbox-exec (macOS); offline-mode on macOS | `run_external_cli` (Phase 2 chokepoint) | **`[S]` — bwrap + sandbox-exec; ONLINE-mode default on both (reject macOS-prefetch-flow per critic Issue 2)** | 3 | 3 | 3 | 3 | 2 | **14** |
| Event log shape | Per-workflow JSONL+zstd | Per-workflow JSONL + BLAKE3 chain | Per-workflow JSONL + `flock` | **`[synth]` — TWO streams: workflow-internal (per-workflow JSONL+zstd) + workflow-spanning (shared JSONL+zstd, BLAKE3-chained)** | 3 | 3 | 3 | 3 | 3 | **15** |
| Plugin loader trust model | Trust filesystem; `@register_plugin` no signature | `PLUGINS.lock` SHA-256 + extra=forbid + env strip | `@register_plugin`; PR review is the anchor | **`[S]` — `PLUGINS.lock` integrity check (NOT "signing" per critic); env strip on plugin import** | 2 | 3 | 3 | 3 | 2 | **13** |
| Capability tokens | None | `*Capability` types; "unforgeable" claim | None — string-level discipline | **`[S+synth]` — Capability types; framing downgraded to "audit + lint enforcement" per critic** | 3 | 3 | 3 | 3 | 3 | **15** |
| `SandboxedPath` framing | None | "Make illegal states unrepresentable" (over-claim) | None | **`[S+synth]` — Smart-constructor + `O_NOFOLLOW`; honest "in-jail-at-construction" framing per critic Issue 5 pattern critique** | 3 | 3 | 3 | 3 | 3 | **15** |
| LangGraph in Phase 3 | No (Phase 6 owns it) | Unnamed but topology assumed | Yes (`build_subgraph() -> StateGraph`) | **`[P]` — No LangGraph in Phase 3; subgraph is typed step functions** | 3 | 3 | 3 | 3 | 3 | **15** |
| `VulnIndex` storage | sqlite (~50 MB) indexed | per-feed file parse on demand | per-feed parsers, no shared index | **`[P]` — sqlite VulnIndex with content-addressed digest in Bundle cache key** | 3 | 3 | 3 | 3 | 3 | **15** |
| NCU usage | Reject (we know target version) | Not used (pure-Python preferred) | Use NCU (shell-out) | **`[P]` — Reject NCU; we already know target from CVE record (critic's convergence-blind-spot)** | 3 | 3 | 3 | 3 | 3 | **15** |
| Synthetic third plugin | None | None | Open question (#7) | **`[synth]` — SHIP `tests/fixtures/plugins/example--noop--*/` per critic Issue 8** | 3 | 3 | 3 | 3 | 3 | **15** |
| Universal fallback directory name | `plugins/universal--*--*/` | `plugins/universal--*--*/` | `plugins/universal--*--*/` (open question) | **`[P+S+B]` — Keep convergent name** | 2 | 3 | 3 | 1 | 2 | **11** |
| `vuln_index.digest` in Bundle cache key | Omitted (acknowledged in §Open Q #7) | N/A (no Bundle) | N/A (no Bundle) | **`[synth]` — INCLUDE per critic Hidden Assumption #3** | 3 | 3 | 3 | 3 | 3 | **15** |
| `RecipeProtocol.applies` signature | `match(ctx) -> RecipeMatch (sum type)` | `apply(...) -> Result[RecipeOutcome, RecipeError]` | `applies(cve, ctx) -> bool` (open Q #5) | **`[P+synth]` — `applies(cve, bundle) -> Applicability` sum type (`Applies(plan) \| NotApplies(reason)`); resolves best-practices' open Q** | 3 | 3 | 3 | 3 | 3 | **15** |
| Threat model: adversarial CVE feeds at runtime | Out of scope | Adversary #1 (caps + jails) | Out of scope | **`[synth]` — narrow per critic Hidden Assumption #1; keep size/depth caps but reject runtime-adversary framing** | 3 | 3 | 3 | 3 | 2 | **14** |
| Concurrency bound (`Semaphore(N)`) | Hard-coded 4 with `min(4, cpu_count)` | N/A | N/A | **`[P+synth]` — `min(4, cpu_count)` default + `CODEGENIE_BUNDLE_CONCURRENCY` env var escape hatch (per critic on unbenchmarked SSD-knee)** | 3 | 3 | 3 | 3 | 2 | **14** |

### Shared blind spots considered

The critic flagged three shared blind spots:

1. **All three demoted OpenRewrite.** *Synthesizer departure:* `OpenRewriteRecipeEngine` is scaffolded (not just Protocol-only) with a Phase-7-tagged Dockerfile fixture. Phase 3 doesn't use it for npm; Phase 7 inherits it for Dockerfile structural transforms. The critic was right that Phase 7 needs OpenRewrite-style refactors and a Phase-3-shipped Protocol is a 1-impl Protocol — we ship 2 implementations.

2. **All three said "Phase 9 will lift the Phase 3 event log unchanged."** *Synthesizer departure:* Phase 3 ships **two** event streams (`workflow_internal` + `workflow_spanning`) matching ADR-0034's hybrid model. Phase 9 reads from both correctly the first time.

3. **All three accepted `plugins/universal--*--*/` without seriously testing the alternative.** *Synthesizer carries the convergence forward* but documents the tradeoff (shell quoting friction) explicitly. The alternative (`plugins/_fallback/` with manifest-declared wildcard scope) introduces "discoverability separated from scope" inconsistency that's worse. The convergence is right even if under-argued in the inputs.

### Pattern reconciliation

| Pattern | Where it appeared | Synthesis disposition | Rationale |
|---|---|---|---|
| Plugin / Registry on `PluginRegistry` | All three | **Adopted (instance-based, fixture-isolated)** | Phase 6.5's `TaskClassRegistry` already adopted this exact shape; we match. Performance's module-level singleton is the toolkit's "side effects at import time" anti-pattern. |
| Dependency inversion via `Protocol` | All three | **Adopted for `Plugin`, `Adapter`, `RecipeEngine`, `RecipeProtocol`** | Multiple implementations from day one (4 recipes; 2 recipe engines; 4 adapters). Pattern-fit pays rent. |
| Abstract base class on `Transform` | None named | **Adopted (the one exception)** | Phase 5's `isinstance(t, Transform)` check requires ABC; Protocol with `runtime_checkable` has runtime overhead. Sealed hierarchy. |
| Tagged union / sum type | All three | **Adopted everywhere** | Critic correctly flagged best-practices' `applies(...) -> bool` and performance's `confidence=bool`; we use sum types for all state. |
| Make-illegal-states-unrepresentable on `PluginScope` | Best-practices declined (`Literal["*"]` for YAML aesthetics) | **Adopted (sum-type `Concrete \| Wildcard`)** | ADR-0033 beats YAML aesthetics; critic correctly attacked. |
| Smart constructor on external-boundary parsers | All three | **Adopted (`PluginManifest.from_yaml`, `CveRecord.parse_*`, `PluginScope.parse`, `BranchName.parse`)** | Every external-boundary deserializer. Critic flagged security's missing `BranchName.parse`; we add it. |
| Newtype on every domain primitive | Best-practices adopted; performance partial; security partial | **Adopted across the board** (`WorkflowId`, `BundleId`, `TransformId`, `EventId`, etc. — critic flagged the swap risk) | Static-type-checker discrimination for free. |
| Capability pattern | Security adopted; others missed | **Adopted with downgraded framing** (audit + lint enforcement, NOT "unforgeable at runtime") | Critic correctly attacked the "unforgeable" claim; we keep the audit value, drop the runtime-impossibility overclaim. |
| Smart constructor on `SandboxedPath` | Security adopted with overclaim | **Adopted with honest framing** ("in-jail-at-construction"; TOCTOU is real and `O_NOFOLLOW` is the second-line defense) | Critic correctly attacked the "unrepresentable" claim. |
| Hexagonal Port + Adapter on `SubprocessJail` | Security adopted | **Adopted** (BwrapAdapter + SandboxExecAdapter; Phase 5's Firecracker is a third Adapter) | Two implementations from day one; Phase 5's Firecracker is real. |
| Strategy on `RecipeEngine` | Performance adopted with one-impl-deferred-second; security implicit; best-practices missed | **Adopted with TWO real implementations** (`NpmLockfileRecipeEngine` + `OpenRewriteRecipeEngine` scaffold) | Premature pluggability avoided; the Protocol pays rent from day one. |
| Pipeline / Chain of responsibility on plugin subgraph | All three | **Adopted (5 nodes)** | Each can short-circuit with typed `RecipeOutcome`; Phase 6 wraps in LangGraph 1-to-1. |
| Event sourcing with discriminated-union events | All three | **Adopted (two-stream split per ADR-0034)** | Critic correctly flagged all three for missing the hybrid-model split; we adopt the correct shape. |
| LangGraph as runtime engine in Phase 3 | Best-practices adopted; security implicit; performance rejected | **Rejected (Phase 6 owns it)** | ADR-0002 + roadmap Phase 6. Phase 3 ships typed step functions Phase 6 wraps. |
| NCU as recipe primitive | Best-practices adopted | **Rejected** | Phase 3 already knows target version from CVE record; NCU solves the wrong question. Critic's convergence-blind-spot. |
| JVM SecurityManager defense | Security adopted | **Rejected** | Deprecated upstream; `SubprocessJail`/`bwrap` is the real defense (defense-in-depth-of-deprecated-API has negative value). |
| Hedged-race in `BundleBuilder` | Performance adopted | **Rejected** | Commitment §2.4 vetoes; deterministic declarative fallback is the answer. |
| Three-plugin contract test | None — best-practices flagged as open question #7 | **Adopted (`tests/fixtures/plugins/example--noop--*/`)** | Critic correctly argued: contract bugs caught at Phase 3 with 3 plugins beats at Phase 7 with 2. |
| Verdict cache | None of the three; Phase 5 explicitly rejected | **Rejected (Phase 9 territory)** | Phase 5's synthesis also rejected; we match. |

### Departures from all three inputs

1. **Ship `RemediationOrchestrator`, `TrustScorer`, `Transform` ABC, `ApplyContext`, `remediation-report.yaml` by name.** None of the three lens designs did. Phase 5's already-merged design names these as load-bearing; the synthesis ships them. (Critic Issue 1.)
2. **Run `npm test` inside `SubprocessJail` in Phase 3.** Performance implicitly skipped; security explicitly deferred to Phase 5; best-practices ran `npm ci` (install only). Roadmap exit criterion reads "passes the repo's own tests"; Phase 5 wraps the retry envelope, not the inner validate. (Critic Issue 2.)
3. **`OpenRewriteRecipeEngine` scaffolded with a Phase-7-tagged Dockerfile fixture.** All three demoted OpenRewrite; the critic correctly argued Phase 7 needs it. Synthesis splits the difference: scaffold now, use later. (Critic Issue 3.)
4. **`Plugin` Protocol has NO `cve_feed_parsers()` method.** Best-practices put it there; critic correctly flagged the anti-pattern. CVE-feed parsers are registered via TCCM `provides.vuln_index_capabilities`. (Critic Issue 4.)
5. **Determinism over hedged-race in `BundleBuilder`.** Performance's hedged-race violates commitment §2.4; synthesis rejects it. (Critic Issue 7.)
6. **Two event streams (`workflow_internal` + `workflow_spanning`) per ADR-0034.** All three designs missed the hybrid-model split. (Critic Issue 6.)
7. **Synthetic third plugin (`tests/fixtures/plugins/example--noop--*/`).** Best-practices flagged the gap; none of the three filled it. (Critic Issue 8.)
8. **`PluginScope` uses `Concrete | Wildcard` sum type, not `Literal["*"]`.** Best-practices' design declined the sum type for YAML aesthetics; the critic correctly attacked. ADR-0033 beats aesthetics.
9. **Honest framing of `Capability` and `SandboxedPath` ("audit + lint" / "in-jail-at-construction"), NOT "unforgeable" / "unrepresentable."** Critic correctly attacked security's overclaims.
10. **`CODEGENIE_BUNDLE_CONCURRENCY` env-var escape hatch on the Semaphore bound.** Critic correctly noted the unbenchmarked SSD-knee claim; env-var lets CI tune without code edits.
11. **Reject macOS-offline-mode-only flow.** Online-mode default on both substrates via `sandbox-exec` egress allowlist on macOS. Critic correctly attacked security's unjailed-prefetch flow as defeating its own primary defense.
12. **PLUGINS.lock relabeled "integrity check" not "signature."** Critic correctly noted "package.lock cosplay"; honest framing instead of weakening it further.

---

## Exit-criteria checklist

Roadmap Phase 3 exit criterion: **"Given a Node.js repo with a known npm CVE, the system writes a working patch diff on a local branch that — when applied — installs cleanly and passes the repo's own tests."**

- [x] **"Given a Node.js repo with a known npm CVE"** → `RepoContextLoader` reads Phase 2's `repo-context.yaml`; `VulnIndex.lookup` resolves the CVE; `Resolver.resolve(VULN, JS, NPM)` matches `vulnerability-remediation--node--npm`.
- [x] **"the system writes a working patch diff"** → `NpmLockfileRecipeEngine.apply` produces `NpmLockfileTransform(diff_bytes, files_changed)`. `LocalGitOps.create_patch_branch` writes the branch. Tested by `tests/integration/test_end_to_end_express_cve.py`.
- [x] **"on a local branch"** → branch `codegenie/cve-2024-21501-<short>`. Never `git push` (commitment §2.8, `GitLocalOpsCapability` doesn't mint push permission).
- [x] **"when applied — installs cleanly"** → Stage 6 runs `SubprocessJail.run(npm install)` in a temp worktree; `InstallStageOutcome.passed=True` is part of `TrustScorer.score`.
- [x] **"and passes the repo's own tests"** → Stage 6 runs `SubprocessJail.run(npm test)` in the same temp worktree; `TestStageOutcome.passed=True` is part of `TrustScorer.score`. (Critic Issue 2 resolution.)

Plus the **plugin-architecture co-exit-criterion** (ADR-0031): "the first plugin doubles as the proof that the plugin loader works":

- [x] **Plugin loader walks `plugins/` and validates manifests** → `PluginLoader.load_all` tested in `test_loader.py`.
- [x] **Universal fallback registered** → `plugins/universal--*--*/`; fallback fires on no-match (`test_universal_fallback.py`).
- [x] **Contract testable against >1 real plugin + 1 synthetic** → `plugins/vulnerability-remediation--node--npm/` + `plugins/universal--*--*/` + `tests/fixtures/plugins/example--noop--*/` (the synthetic third plugin).

Plus the **Phase 5 integration handshake** (critic Issue 1 — not in roadmap text, but Phase 5's already-merged design requires it):

- [x] **`RemediationOrchestrator`, `TrustScorer`, `Transform` ABC, `ApplyContext`, `RecipeEngine` exist by name** → `src/codegenie/transforms/__init__.py` exports them; `tests/integration/test_phase5_contract_snapshot.py` asserts.

---

## Load-bearing commitments check

Each commitment from `docs/production/design.md` §2 that applies:

- **§2.1 No LLM in the gather pipeline.** Phase 3 extends: no LLM in the *deterministic transform path either*. `import_linter` fence under `src/codegenie/plugins/`, `src/codegenie/transforms/`, `plugins/vulnerability-remediation--node--npm/`, `plugins/universal--*--*/`. CI hard-block.
- **§2.2 Facts, not judgments.** `TrustSignal.passed: bool` over objective measurements (exit codes, lockfile diffs, CVE-delta); no `confidence_self_reported`, no `recommendation: str`. Each recipe emits `RecipeOutcome.Applied(diff, ...)` or `RecipeOutcome.NotApplicable(reason)`, never `RecipeOutcome.SafeToMerge(...)`.
- **§2.3 Honest confidence.** Every adapter reports `AdapterConfidence` (`Trusted | Degraded(reason) | Unavailable(reason)`); `AdapterDegraded` events flow into `TrustOutcome.confidence`; `IndexHealthProbe` (Phase 2 B2) `Stale` → `NodeScipAdapter.Degraded` → TCCM fallback fires deterministically.
- **§2.4 Determinism over probabilism for structural changes.** **Veto-strength.** No LLM in Phase 3; recipes are deterministic; Bundle cache key is content-addressed (includes `vuln_index.digest`); BundleBuilder uses declarative-fallback NOT hedged-race; property test asserts byte-identical `Transform` output across 100 runs.
- **§2.5 Extension by addition.** Plugin contract is closed-for-modification at the kernel; new plugins are new directories + decorator calls. CI fence: `tests/fence/test_kernel_frozen.py`. Phase 7 will validate. Synthetic third plugin proves the contract surface at *3* plugins, not 1.
- **§2.6 Organizational uniqueness as data, not prompts.** TCCM YAML, plugin manifests, Skills with YAML frontmatter, recipe inventory YAML, policy YAML. Zero hardcoded business rules in Python.
- **§2.7 Progressive disclosure.** TCCM `must_read`/`should_read`/`may_read` honored; Bundle holds references not contents; `remediation-report.yaml` indexes the streams, doesn't inline them.
- **§2.8 Humans always merge.** `GitLocalOpsCapability` does not mint push permission. `plugins/universal--*--*/` emits `RequiresHumanReview` on no-match. No PR creation in Phase 3 (Phase 11).
- **§2.9 Cost is observable end-to-end and bounded per workflow.** `CostSandboxRun` event emitted per `SubprocessJail.run` (carrying duration, exit, signal-collection breakdown); Phase 13's cost ledger projects from these. `LlmInvocationGuard` not used in Phase 3 (no LLM); event-shape compatible.

---

## Roadmap coherence check

**Prior phases established that this design depends on:**

- **Phase 0:** `tool_readiness` check (`bwrap`/`sandbox-exec`/`npm`/`jq`/`git` availability at startup); `import_linter` (extended); fence-CI shape; `audit_anchor` BLAKE3 helper (lifted to `EventLog` spanning stream).
- **Phase 1:** `Probe` ABC, `ProbeRegistry`, `Coordinator`, `RepoContext` schema, NodeBuildSystem/NodeManifest/CI/Deployment/TestInventory probes. All frozen surfaces.
- **Phase 2:** `IndexHealthProbe` (B2), dep_graph/import_graph/scip/test_inventory primitives, the four ADR-0032 adapter Protocols, `run_external_cli` chokepoint, conventions catalog and Skills loader. **The four adapter Protocols are what `plugins/vulnerability-remediation--node--npm/adapters/` implement.**
- **ADRs 0007 (probe contract preserved), 0008 (objective-signal trust score), 0009 (humans always merge), 0011 (recipe-first), 0028 (registry-pattern siblings), 0029 (TCCM), 0030 (graph-aware context queries), 0031 (plugin architecture), 0032 (language search adapters), 0033 (domain modeling), 0034 (event sourcing canonical primitive).**

**This design establishes that later phases will need:**

- **Phase 4 (LLM-fallback):** `ApplyContext.prior_attempts: list[AttemptSummary] = []` (Phase 5's ADR-P5-002 amends), `Transform` ABC for the LLM-produced output, `RecipeOutcome.NotApplicable` events as the fallback trigger.
- **Phase 5 (sandbox + trust gates):** `RemediationOrchestrator`, `TrustScorer` (extended via signal-kind registry — ADR-P5-003), `Transform`, `ApplyContext`, `remediation-report.yaml`, the Stage-6-validate seam.
- **Phase 6 (LangGraph state machine):** the 5-node plugin subgraph as typed step functions Phase 6 wraps 1-to-1.
- **Phase 6.5 (eval harness):** `BenchReplayable` events on the spanning stream as the backfill source.
- **Phase 7 (distroless migration):** the plugin contract (validated by 3 plugins in Phase 3); `OpenRewriteRecipeEngine` scaffold; `RecipeEngine` Protocol; TCCM `provides`/`requires` machinery (validated by `example--noop--*` synthetic plugin).
- **Phase 8 (Hierarchical Planner + hot views):** `Resolver.resolve` returns `ConcreteResolution` with `composed_tccm` ready for hot-view pre-rendering; `BundleBuilder` cache is what Redis hot-views replace.
- **Phase 9 (Temporal + Postgres event log):** the two event streams (workflow-internal → Temporal history; workflow-spanning → Postgres `events` table).

**New ADRs implied by this design that should be drafted in Phase 3 stories:**

- **ADR-P3-001 — `RemediationOrchestrator`, `TrustScorer`, `Transform`, `ApplyContext` shipped in Phase 3 as the Phase-5 integration handshake.** (Acknowledges the cross-phase break the critic flagged; commits Phase 3 to shipping the names Phase 5 already references.)
- **ADR-P3-002 — Two-stream event log shape per ADR-0034 hybrid model.** (Phase-3 anchor for the workflow-internal vs workflow-spanning split.)
- **ADR-P3-003 — Plugin-private capabilities via TCCM `provides`/`requires`, NOT via task-class methods on the kernel `Plugin` Protocol.** (Cements the ADR-0031 invariant against the best-practices design's `cve_feed_parsers()` anti-pattern.)
- **ADR-P3-004 — `OpenRewriteRecipeEngine` scaffolded in Phase 3 with Phase-7-tagged Dockerfile fixture.** (Establishes `RecipeEngine` Protocol has 2 implementations from day one; pays the pattern-fit rent.)
- **ADR-P3-005 — Synthetic `example--noop--*` plugin under `tests/fixtures/plugins/`.** (Locks in the 3-plugin contract bake test before Phase 7.)
- **ADR-P3-006 — Phase 3 runs the repo's own tests inside `SubprocessJail`; Phase 5 wraps the retry envelope around Stage 6, not the inner validate.** (Resolves the roadmap exit-criterion-vs-security-deferral conflict.)
- **ADR-P3-007 — Deterministic declarative fallback in `BundleBuilder` (NOT hedged-race).** (Commitment §2.4 anchor.)

---

## Open questions deferred to implementation

1. **Exact CI runner concurrency tuning.** `CODEGENIE_BUNDLE_CONCURRENCY` defaults to `min(4, os.cpu_count())`; on `ubuntu-latest` (cpu_count=2) this is 2. The right tuning is empirical; implementation should add a CI step that runs `bench_bundle_builder_cold` against representative fixtures on `ubuntu-latest` and records the actual knee.

2. **`OpenRewriteRecipeEngine` Phase-7-fixture detail.** The scaffold needs a single working Dockerfile-base-image-swap fixture (Phase 7 inherits + extends). Implementation defines the exact fixture; the synthesis only commits to "one working fixture exists at Phase 3 time."

3. **Sanitization of HITL `.codegenie/handoff/*.md`.** Synthesis adopts security's NFKC + ANSI/bidi/zero-width strip; implementation may need to add more (e.g., markdown HTML embed neutralization) once we see real HITL content.

4. **`PLUGINS.lock` update workflow.** Synthesis says CODEOWNERS on `plugins/PLUGINS.lock`. Implementation defines the CODEOWNERS file content and the PR-template that calls out lockfile changes.

5. **`vuln-index.sqlite` staleness threshold.** Synthesis says 7 days of mtime triggers `StaleVulnIndex` warning. Implementation may want it configurable per operator.

6. **`SubprocessJail` macOS `sandbox-exec` profile content.** Synthesis specifies the policy at a high level (deny default + allow jail + allow registry hosts). Implementation writes the actual `.sb` profile.

7. **`example--noop--*` synthetic plugin's exact contract-surface coverage.** Synthesis says it exercises every contract surface. Implementation may discover gaps (e.g., a `provides`/`requires` edge case not exercised) and extend.

8. **Whether `RecipeOutcome.NotApplicable(reason=PeerDepConflict)` should emit a separate event variant.** Synthesis treats `NotApplicable` as a single event variant with `reason`. Implementation may want per-reason variants for richer Phase-4 fallback dispatch.

9. **`CostSandboxRun` event shape exact fields.** Synthesis lists "duration, exit, signal-collection breakdown" as the payload. Implementation aligns with Phase 13's cost ledger schema as it firms up.

10. **Bench advisory budgets — exact wall-clock numbers on `ubuntu-latest` GitHub-hosted runners.** Synthesis commits to relative-budget assertions; implementation records the rolling-7-day-mean baseline once the benches first run.

---

*End of final-design.md — design of record. Phase-architect, ADR-extractor, and story-writer all read this artifact next.*
