# codewizard-sherpa — Phased Roadmap

This document sequences the work from a local bullet tracer through to a multi-tenant production system. It is **epic-level**: each phase defines *what ships*, not *how it is built*. Detailed designs live in [`production/design.md`](production/design.md) and [`production/adrs/`](production/adrs/).

## Reading guide

- **Phases are sequential.** Each builds on the previous one's exit criteria. Skipping is rarely safe — the architecture is layered.
- **Task classes are introduced one at a time.** Vulnerability remediation comes first (Phase 3), Chainguard distroless migration second (Phase 7), agentic recipe authoring third (Phase 15). This sequencing exists to prove that the probe + skill + recipe contracts extend by **addition**, not by editing.
- **Determinism comes before LLM.** Every phase that introduces probabilistic behavior is preceded by the deterministic version of the same capability. The arc is visible across Phases 3 → 4 → 15.
- **Every phase commits to tooling, tests, and exit criteria up front.** Setup is not retrofitted at the end. Documentation, CI, mypy, ruff, pre-commit, and the docs site land in Phase 0 — not phase 16.
- **Read alongside:** [`production/design.md`](production/design.md) (the canonical architecture reference), [`localv2.md`](localv2.md) (the local POC contract — frozen as the same contract used in the service), and the [ADR index](production/adrs/README.md).

## Phase summary

**Design pipeline status legend:** ✅ = full design pipeline complete (`final-design.md` + `phase-arch-design.md` + per-phase ADRs + `High-level-impl.md` + stories backlog under `docs/phases/NN-<slug>/`). Empty = not yet designed. *(pending plugin-architecture redesign)* = had a complete design pipeline that was removed because [ADRs 0029–0032](production/adrs/) (TCCMs, graph-aware queries, plugin architecture, language search adapters) materially changed how the phase will ship; the next design pipeline run must absorb the plugin framing.

| # | Title | Task classes | First-time introduction of | Design |
|---|---|---|---|---|
| 0 | Bullet tracer + project foundations | — | CLI shell, `pyproject.toml`, CI, docs site, mypy, ruff, pytest, pre-commit | ✅ [00-bullet-tracer-foundations](phases/00-bullet-tracer-foundations/) |
| 1 | Context gathering — Layer A (Node.js) | — | Probe contract, coordinator, content-addressed cache, schema validation | ✅ [01-context-gather-layer-a-node](phases/01-context-gather-layer-a-node/) |
| 2 | Context gathering — Layers B–G | — | IndexHealthProbe (B2 — the critical one), traces, depgraph, security, conventions, skills loader | ✅ [02-context-gather-layers-b-g](phases/02-context-gather-layers-b-g/) |
| 3 | **Vuln remediation — deterministic recipe path** | vuln | First plugin (`vulnerability-remediation--node--npm`); OpenRewrite / AST; writes a real diff | ✅ [03-vuln-deterministic-recipe](phases/03-vuln-deterministic-recipe/) |
| 4 | Vuln remediation — LLM fallback + solved-example RAG | vuln | Leaf LLM agents, local vector DB, recipe → RAG → LLM-fallback decision chain | ✅ [04-vuln-llm-fallback-rag](phases/04-vuln-llm-fallback-rag/) |
| 5 | Sandbox + Trust-Aware gates | vuln | microVM isolation, build/test/runtime gates, three-retry default | ✅ [05-sandbox-trust-gates](phases/05-sandbox-trust-gates/) |
| 6 | SHERPA-style state machine for the vuln loop | vuln | LangGraph runtime, Pydantic state ledger, stable harness-facing SUT contract, `interrupt()` + SQLite checkpointer | ✅ [06-sherpa-vuln-loop](phases/06-sherpa-vuln-loop/) |
| 6.5 | **Per-task-class eval harness + first benches** *(preamble to Phase 7)* | vuln | `eval/` package, `@register_task_class` registry, `BenchScore` model, `bench/{task-class}/` directory contract, fence-CI gate, backfilled `bench/vuln-remediation/` | ✅ [06.5-per-task-class-eval-harness](phases/06.5-per-task-class-eval-harness/) |
| 7 | **Add migration task class (Chainguard distroless)** | vuln + migration | Second plugin (`distroless-migration--node--npm`); proves no edits to existing plugins or stable behavior, with bounded ADR-backed primitives allowed when genuinely cross-task | *(pending Phase 7 redesign)* |
| 8 | Hierarchical Planner + pre-rendered hot views | vuln + migration | Planning supervisor, Redis hot views, MCP-style stdio Skills server |
| 9 | Durable workflow envelope — Temporal | vuln + migration | Temporal workflows + activities, Postgres checkpointer, temporal-ui |
| 10 | Stage 0 Discovery + Stage 1 Assessment | vuln + migration | Multi-repo discovery (GitHub API), assessment scoring, eligibility filtering, repo-side `codegenie.yaml` opt-out policy primitive |
| 11 | Stage 6 Handoff + Stage 7 Learning | vuln + migration | GitHub PR opening, outcome ingestion, KG write-back |
| 12 | Stage 3 deep planning + Stage 4 validation depth | vuln + migration | Cross-repo dep analysis, contract testing, regression suites beyond sandbox |
| 13 | AgentOps — cost ledger + budget enforcement + ROI dashboard | vuln + migration | Three-tier cost ledger, Budget Enforcer, Grafana ROI dashboard |
| 13.5 | **Operator portal** *(read-only views + plugin/task kill-switches)* | vuln + migration | Ops + repo-owner views projected off the canonical event log; GitHub OAuth; plugin/task kill-switches at three scopes; UI projection of the Phase 10 repo-side opt-out policy |
| 14 | Continuous gather + MCP servers operationalized | vuln + migration | Cron / webhook / PR / CVE-feed triggers; Context / Skills / KG / Policy MCP servers split |
| 15 | **Agentic recipe authoring (deterministic → agentic)** | vuln + migration + recipe-authoring | LLM proposes new recipes/skills from solved examples; humans accept |
| 16 | Production hardening | all | Deferred ADRs resolved; multi-tenancy, SSO/RBAC, audit, runbooks, on-call |

The two notable value milestones: **Phase 3** is the first time a real transform ships (locally). **Phase 11** is the first time a real PR opens at portfolio scale.

---

## Test architecture evolution

The test surface grows with the system. This subsection names *when* each cross-cutting test capability lands so a reader can see the arc without walking every phase. Per-phase **Testing** subsections below carry the same commitments; this is the at-a-glance index.

| Phase | New test capability | Why it lands here |
|---|---|---|
| 0–2 (shipped) | Unit + per-probe golden + adversarial + fence + smoke (`tests/smoke/test_cli_end_to_end.py`) + portfolio sweep (one mode) | Foundational; metamorphic cache pair pinned in smoke |
| **3** | (a) **Cache invariant as Hypothesis property** (`tests/property/test_cache_invariant.py`) — for any random sequence of `(gather, edit-tracked-input, gather, edit-untracked-file, gather)`, outputs match iff `declared_inputs` content is byte-identical; (b) **Parameterized portfolio sweep** over `{cold-cache, warm-cache, mid-run-cache-corruption, concurrent-multi-fixture}` modes; (c) **`tests/e2e/` slice harness** — table-driven `(task_class, fixture, expected_outcome)` rows; Phase 3 ships the first row (`gather → recipe → lockfile-diff`); (d) **Real-binary contract tests** (`tests/contract/`) for `npm`, `pnpm`, `yarn`, `jq` — version-pinned, ratcheted, excluded from `make test` but run nightly in CI | Phase 3 is the first phase to exercise the cache + portfolio + binary surface at scale; setting the scaffolding here means Phases 4–7 add rows, not new test architectures |
| **4** | (a) Add Phase 4 rows to `tests/e2e/` (recipe → RAG → LLM-fallback slice); (b) **Golden coverage for new event streams** — `AttemptAnchor` JSONL ([Phase 4 ADR-04-0017](phases/04-vuln-llm-fallback-rag/ADRs/0017-attempt-anchor-event-schema.md)) + the two-stream Phase 4 / Phase 5 event log — pinned under `tests/golden/events/`; (c) Add `tsc` to `tests/contract/`; (d) **Determinism-under-cassette-replay property** at `FallbackTier` scope ([Phase 4 S6-07](phases/04-vuln-llm-fallback-rag/stories/S6-07-determinism-cassette-replay-property.md)) | Phase 4 emits the first audit-anchor / two-stream event log; goldens calcify the schema before downstream consumers (operator portal, future critic training) lock in |
| **5** | (a) Add Phase 5 rows to `tests/e2e/` (sandbox + trust-gate slice); (b) **New `tests/resilience/` tier** — timeout, retry-exhaustion, partial-failure semantics across the gate runner; (c) Property tests over gate decisions for all combinations of objective signals (already in Phase 5 scope) | Phase 5 introduces the first operational-failure surface (sandbox timeout, gate-retry exhaustion) the existing fence + adversarial tiers don't catch |
| **6** | (a) Add Phase 6 rows to `tests/e2e/` (full state-machine slice); (b) **Workflow-scope replay determinism property** — extending Phase 4's `FallbackTier`-scope property to the full LangGraph state machine: for any `(repo_snapshot, cassette_id, embedding_model_digest)` triple, the entire pipeline produces byte-identical outputs across runs; (c) State-transition tests already in scope | Phase 6 is the first phase where workflow-level determinism becomes testable (the state machine ties Phases 3/4/5 together) |
| **6.5** | (a) **Per-task-class bench harness** (already in scope) — adds the scenario-driven slice runner consumed by Phase 7; (b) **Synthetic fixture generator** (initially manual; generator becomes load-bearing as ≥10 held-out + memorization split per task class becomes a fence-CI requirement); (c) **Nightly bench job in CI** (`pytest -m bench`) gates against frozen baselines | Phase 6.5 ADR-0002 already commits the harness; this row makes the nightly-bench expectation explicit |
| **7+** | Per-phase additions follow the same pattern: add rows to `tests/e2e/`, add binaries to `tests/contract/`, add scenarios to `bench/{task-class}/`, add properties for new invariants | Extension by addition applies to the test architecture too |

**Discipline.** Each phase's exit criteria include the test-capability rows above. Adding a probe/plugin/SignalKind without the corresponding test extension is a closeout-story failure ([closeout-story template](phases/_template/closeout-story.md)). The doc-consistency fence ([`tests/unit/test_doc_consistency.py`](../tests/unit/test_doc_consistency.py)) enforces the structural pieces mechanically.

---

## Phase 0 — Bullet tracer + project foundations

**Scope.** Wire up the local CLI shell end-to-end and establish project conventions up front: a `pyproject.toml` (PEP 621), strict mypy, ruff (lint + format), pytest with coverage, pre-commit hooks, and GitHub Actions CI (lint + type + test on every PR). The documentation site (`mkdocs-material`) is wired to the existing `docs/` tree so prose changes render locally. A GitHub Project board carries milestones aligned 1-to-1 with these phases, and issue templates exist for the three artifacts we'll generate by hand most often: new probe, new skill, ADR amendment. One trivial probe (LanguageDetection) executes end-to-end to prove the harness — the cache, coordinator, output writer, and schema validator — actually run together. A stub `.codegenie/context/repo-context.yaml` lands on disk.

**Tooling & setup.** Python 3.11+. Dependencies: `click`, `pyyaml`, `jsonschema`, `aiofiles`, `pydantic`. Dev dependencies: `pytest`, `pytest-asyncio`, `pytest-cov`, `mypy`, `ruff`, `pre-commit`, `mkdocs-material`. CI on GitHub Actions.

**Testing.** Unit test for the probe contract ABC. Smoke test for CLI invocation (`codegenie gather --help`, `codegenie gather <empty-dir>`). CI runs lint + type + test on every PR.

**Exit criteria.** `codegenie gather` runs on any directory, prints external-tool readiness, executes LanguageDetection, writes `.codegenie/context/repo-context.yaml`. CI is green on `main`. The docs site builds locally without warnings.

---

## Phase 1 — Context gathering — Layer A (Node.js)

**Scope.** The [`localv2.md §12`](localv2.md) plan. Real Layer A probes: LanguageDetection, NodeBuildSystem, NodeManifest, CI, Deployment, TestInventory. Probe coordinator with a bounded worker pool, per-probe timeout, and failure isolation (one probe's exception does not poison the rest). Filesystem-backed content-addressed cache under `.codegenie/cache/`, keyed off each probe's declared inputs. JSON Schema validation of the final `repo-context.yaml`.

**Tooling & setup.** `asyncio` (stdlib), `hashlib` for cache keys. A `fixtures/` directory in the repo contains the minimal Node.js fixture repos used by tests.

**Testing.** Per-probe unit tests against fixture repos (one fixture per coverage scenario). One integration test against a real small open-source Node.js repo. Schema validation enforced as a CI gate — the produced `repo-context.yaml` must parse against the schema or the build fails.

**Exit criteria.** A useful `repo-context.yaml` is produced on a real Node.js repo. Cache hits on second run (no probe re-executes). All probes pass schema validation.

**Domain modeling discipline.** Phase 1 adopts [ADR-0033](production/adrs/0033-domain-modeling-discipline.md) (newtype + smart constructor + sum type + illegal-states-unrepresentable) for all new code from the date of that ADR. Domain identifiers — `RepoId`, `ProbeId`, `SkillId`, `RecipeId`, `WorkflowId`, `BundleId`, `SignalKind`, etc. — use `typing.NewType`; external-boundary values (YAML, JSON, env, CLI) go through smart-constructor parsing returning `Result`; state machines (probe outcomes, gate decisions, build outcomes) use Pydantic discriminated unions with exhaustive `match` handling. Phase 0 code already shipped (raw `str` for identifiers, `Optional[X]` / `bool` for state) is allowed to remain temporarily; opportunistic retrofit happens as files are touched, with a planned focused retrofit pass tracked as a backlog item.

**Yarn variant detection.** The shipped `NodeBuildSystemProbe` (story S2-02) collapses Yarn Classic and Yarn Berry into a single `"yarn"` value. [ADR-0031](production/adrs/0031-plugin-architecture.md) treats them as distinct plugin scopes (different lockfile formats, different dependency-resolution models — `node_modules` vs. Plug'n'Play). A follow-up story `S2-02a-yarn-variant-detection` adds an additive `_detect_yarn_variant()` function to the probe (priority chain: `package.json#packageManager` field → `.yarnrc.yml` → `.yarn/` dir → `.pnp.cjs` → safe-default-classic-with-warning), updates the schema enum to `["bun", "pnpm", "yarn-classic", "yarn-berry", "npm"]`, bumps `$id` to `v0.2.0`, and lands two new Berry fixtures. Decision recorded in [Phase 1 ADR-0013](phases/01-context-gather-layer-a-node/ADRs/0013-yarn-variants-as-distinct-package-managers.md). Blocks story `S3-03` (the yarn lockfile parser must branch on variant: Berry's `yarn.lock` is YAML, Classic's is custom).

---

## Phase 2 — Context gathering — Layers B–G

**Scope.** The remaining probe layers per [`localv2.md`](localv2.md). The most important one is **IndexHealthProbe (B2)** — silent index staleness is the worst failure mode in any context-gathering system, so this probe is treated as a first-class citizen with its own tests and dashboards. Layer B also includes runtime traces (capturing which shell tools, files, and network endpoints a process actually touches), dependency graphs, secret/security probes, conventions catalog (the org's own style and patterns), and the skills loader (YAML-frontmatter skills indexed by `applies_to_tasks` and `applies_to_languages`).

**Tooling & setup.** External CLIs: `semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, and `tree-sitter` parsers. Python: `gitpython` for git introspection, `networkx` for the depgraph.

**Testing.** Golden-file tests per probe — the expected probe output is committed under `tests/golden/`, and CI diffs the live output against it. Updating a golden file is a deliberate PR step. Integration tests run against a multi-repo fixture portfolio of 3–5 small repos exercising the full probe set.

**Exit criteria.** Every probe layer runs against real repos. IndexHealthProbe surfaces at least one real staleness case in CI (deliberately seeded fixture) — proving the probe actually catches what it's there to catch.

---

## Phase 3 — **Vuln remediation: deterministic recipe path** *(first task class)*

**Scope.** The first end-to-end deterministic transform — and the first piece of code the system writes that has real value. The task class is **vulnerability remediation**: given a Node.js repo with a known npm CVE, bump the vulnerable package to a patched version. The transformation runs through OpenRewrite npm recipes (or hand-rolled AST manipulation as a fallback for cases OpenRewrite does not yet cover). The system reads `RepoContext` and the relevant Skills, chooses a recipe, applies it, and writes the diff plus a local branch. **No LLM enters this loop at all** — this phase exists specifically to prove the deterministic path works before any probabilistic component is introduced. Single-repo, local, deterministic.

**Tooling & setup.** External: `npm`, `jq`, `git`. OpenRewrite recipes for npm dependency updates (or `npm-check-updates` as a simpler first cut for cases where OpenRewrite is overkill). CVE data ingestion: parsers for NVD JSON 2.0, GHSA, and OSV feeds.

**Testing.** A library of fixture repos with known vulnerable lockfiles. Before/after assertions: lockfile diff is the expected one; `package.json` diff is the expected one; the test suite still passes; no semantic regression in entrypoints. Edge cases get their own fixtures: peer-dep conflicts, transitive vulns that can't be patched at the surface, semver-range resolution corner cases.

**Test-architecture additions** (per §"Test architecture evolution"). Four foundational additions land alongside Phase 3 implementation, added as additive stories under `phases/03-vuln-deterministic-recipe/stories/` when the implementation pipeline activates: (1) **`tests/property/test_cache_invariant.py`** — Hypothesis property over random `(gather, edit, gather)` sequences, asserts outputs match iff `declared_inputs` content is byte-identical; (2) **parameterized portfolio sweep** over `{cold-cache, warm-cache, mid-run-cache-corruption, concurrent-multi-fixture}` modes (extends `tests/integration/portfolio/test_portfolio_sweep.py`); (3) **`tests/e2e/` slice harness** — table-driven `(task_class, fixture, expected_outcome)` rows; Phase 3 ships the first row (`gather → recipe → lockfile-diff`); subsequent phases add rows, not new test files; (4) **`tests/contract/` real-binary tier** for `npm`, `pnpm`, `yarn`, `jq` — version-pinned, ratcheted; excluded from `make test` but run nightly in CI. These four are foundational for Phases 4–7 and cheapest to build now while the seam count is one task class.

**Plugin framing.** This is also the **first plugin** to ship — `plugins/vulnerability-remediation--node--npm/` — which doubles as the proof that the plugin loader works ([ADR-0031](production/adrs/0031-plugin-architecture.md)). The plugin bundles its own subgraph, TCCM ([ADR-0029](production/adrs/0029-task-class-context-manifests.md)), npm-and-Node-specific probes, the four language search adapters ([ADR-0032](production/adrs/0032-language-search-adapters.md)) wrapping the structural probes Phase 2 built (the npm/Node implementations of `dep_graph.consumers`, `import_graph.reverse_lookup`, `scip.refs`, `test_inventory.tests_exercising`), Skills, and OpenRewrite recipes. A universal `(*, *, *)` fallback plugin also ships in this phase (HITL escalation when no concrete plugin matches a workflow — never silently fail).

**Exit criteria.** Given a Node.js repo with a known npm CVE, the system writes a working patch diff on a local branch that — when applied — installs cleanly and passes the repo's own tests.

**Provenance refuse-mode (precondition for Phase 7's full primitive).** Per [ADR-0038](production/adrs/0038-vulnerability-provenance-attribution.md), Phase 3 does **not** ship the full `vuln.provenance` primitive — that lands in Phase 7. What Phase 3 *does* ship is the precondition that prevents the embarrassing failure: when a CVE's affected component cannot be located in the app's resolved npm dep graph (because it's actually in the base image, the JRE, or vendored source), the `vulnerability-remediation--node--npm` plugin returns `Applicability.NotApplicable(reason=CVE_NOT_IN_APP_LAYER)` and the orchestrator routes to the universal HITL fallback ([S7-03](phases/03-vuln-deterministic-recipe/stories/S7-03-universal-hitl-fallback-plugin.md)). This is a small acceptance-criterion-grade addition to `match_recipe`, not a redesign. Without it, Phase 3 could silently produce a wrong fix (bump an unrelated npm package) when given a glibc CVE.

---

## Phase 4 — Vuln remediation: LLM fallback + solved-example RAG

**Scope.** Not every vulnerability fix is mechanical. Transitive vulns sometimes require a peer-dep upgrade. Major-version bumps come with breaking-change call-site rewrites. When the deterministic recipe path fails or returns a low-confidence result, the system falls back to a solved-example RAG lookup first, then to a leaf LLM agent if RAG misses. This is the **recipe → RAG → LLM-fallback** decision chain per [ADR-0011](production/adrs/0011-recipe-first-rag-llm-fallback-planning.md). Confidence is computed from **objective signals only** — no LLM self-reported confidence — per [ADR-0008](production/adrs/0008-objective-signal-trust-score.md).

**Tooling & setup.** `anthropic` Python SDK for the leaf agent. `chromadb` (local mode) or `qdrant-client` (local docker) for the solved-example vector store. Embeddings via `sentence-transformers` locally or Voyage if remote is acceptable. `langgraph` imported minimally — just enough to wrap the leaf agent invocation.

**Testing.** Recorded LLM responses via `pytest-recording` (VCR cassettes) so CI runs are deterministic and free. Confidence-thresholding tests use synthetic objective signals to assert the decision chain routes correctly. RAG retrieval quality is tested against a labeled fixture set: known query → known top-k expected.

**Test-architecture additions** (per §"Test architecture evolution"). Phase 4 extends the Phase 3 scaffolding with four phase-specific items: (1) **Phase 4 rows added to `tests/e2e/`** — recipe → RAG → LLM-fallback slice exercised against fixtures `node_typescript_helm`, `node_yarn_berry_pnp`, and the four `fixtures/vuln-major-bump/*` examples; (2) **Goldens for new event streams under `tests/golden/events/`** — `AttemptAnchor` JSONL ([Phase 4 ADR-04-0017](phases/04-vuln-llm-fallback-rag/ADRs/0017-attempt-anchor-event-schema.md)) + the two-stream Phase 4 / Phase 5 event log; the goldens calcify the schema before downstream consumers (operator portal, future critic training) lock in; (3) **`tsc` added to `tests/contract/`** alongside Phase 3's npm/pnpm/yarn; (4) **`FallbackTier`-scope determinism property** ([Phase 4 S6-07](phases/04-vuln-llm-fallback-rag/stories/S6-07-determinism-cassette-replay-property.md)) — 50 runs with `(cassette_id, store_digest, repo_snapshot_sha, embedding_model_digest)` constant produce byte-identical `Transform.diff_bytes` and event order modulo timestamps. The workflow-scope generalization waits for Phase 6's state machine.

**Exit criteria.** A breaking-change vuln (e.g., a major-version-bump CVE) is solved end-to-end with the LLM fallback and recorded into the solved-example store. Re-running the same case uses RAG to shape a cheaper LLM call and produces an equivalent fix at lower cost.

**Verification signal — first `typecheck.*` `SignalKind` lands here.** Phase 4's call-site-rewriting failure modes (signature drift after a major-version bump, missing import after a refactor, type-shape change that compiles but breaks downstream) are exactly the cases the existing build + tests gates catch *late* and expensively. Per [ADR-0037](production/adrs/0037-layered-analysis-funnel-scip-typechecker-lsp.md), Phase 4 introduces the first `typecheck.<language>` TrustSignal (`tsc --noEmit` for the npm/Node plugin) registered through the Phase-3 `@register_signal_kind` open registry — a one-shot subprocess inside `SubprocessJail`, feeding the TrustScorer strict-AND alongside `build`/`install`/`tests`/`lockfile_policy`/`cve_delta`. **LSP is explicitly not introduced here**; the cheap signal is on the menu, the expensive one stays deferred until Phase 15.

---

## Phase 5 — Sandbox + Trust-Aware gates

**Scope.** Nothing leaves the agent's hands without being verified. The sandbox layer adds microVM isolation ([ADR-0012](production/adrs/0012-microvm-sandbox-for-trust-gates.md)) — proposed diffs are applied inside an isolated environment and checked against Trust-Aware gates: the build passes, tests pass, no policy violations fire, and the runtime trace stays stable (no new shell invocations, no new network endpoints). The three-retry default per gate ([ADR-0014](production/adrs/0014-three-retry-default-per-gate.md)) gives the system a chance to recover before escalating to humans.

**Tooling & setup.** Local dev (including macOS): Docker-in-Docker, since it is the portable choice. Linux dev or CI: Firecracker explored as a faster, stricter alternative — choice of sandbox stack itself remains deferred per [ADR-0019](production/adrs/0019-sandbox-stack.md). Tests use `pytest-docker` for orchestration of the sandbox lifecycle.

**Testing.** Property tests for gate decisions: for every combination of objective signals, the gate's outcome is asserted. Integration tests run real builds inside the sandbox (slow but high-signal). Negative cases — broken build, failing tests, policy violation — are explicit tests that the gate rejects, not edge cases.

**Test-architecture additions** (per §"Test architecture evolution"). Phase 5 introduces the first operational-failure surface (sandbox timeout, gate-retry exhaustion, partial-failure semantics) that today's fence + adversarial tiers do not catch as a behavior cluster. Two additions: (1) **Phase 5 rows added to `tests/e2e/`** — sandbox + trust-gate slice exercised end-to-end against a fixture that requires retry-1 failure and retry-2 recovery (mirrors the phase's own exit criterion); (2) **New `tests/resilience/` tier** — timeout exhaustion, retry-exhaustion-with-prior-attempts, partial-failure (one signal fails while others pass, strict-AND semantics), and gate-runner restart-mid-attempt. Each scenario is a behavioral assertion across the gate runner + Phase 4's `FallbackTier` retry envelope, not a unit-level mock.

**Exit criteria.** No transform leaves the sandbox unverified. The three-retry loop is demonstrated end-to-end with at least one case that fails on retry-1 and recovers on retry-2.

---

## Phase 6 — SHERPA-style state machine for the vuln loop

**Scope.** The deterministic + LLM + sandbox loop is now stitched together as a proper state machine — restartable, inspectable, with deterministic transitions. LangGraph is the runtime ([ADR-0002](production/adrs/0002-langgraph-as-runtime-sherpa-as-discipline.md)). The shared mutable state is a **Pydantic-typed state ledger**: nodes only read from and write to that ledger; nodes never call other nodes directly. Conditional edges are the Trust-Aware gates. `interrupt()` plus a SQLite checkpointer enables human-in-the-loop pause and resume.

**Tooling & setup.** `langgraph`, `pydantic`, `aiosqlite` for the checkpointer, `langgraph-cli` for graph inspection.

**Testing.** State-transition tests assert every conditional edge is exercised at least once. Replay tests use the checkpointer to kill a mid-run workflow, resume it, and assert the same final state. HITL interrupt tests inject mocked human responses and verify the workflow continues correctly.

**Test-architecture additions** (per §"Test architecture evolution"). Phase 6 is the first phase where *workflow-level* determinism becomes testable — the state machine ties Phases 3/4/5 together into one replayable graph. Two additions: (1) **Phase 6 rows added to `tests/e2e/`** — full state-machine slice exercised from gather through PR-ready local branch, against the fixture cohort `node_typescript_helm` + `node_yarn_berry_pnp` + `node_pnpm_native`; (2) **Workflow-scope replay-determinism property** — extends Phase 4 S6-07's `FallbackTier`-scope property to the entire LangGraph state machine: for any `(repo_snapshot, cassette_id, embedding_model_digest)` triple, the pipeline produces byte-identical outputs across N independent runs modulo timestamps. The property is workflow-scope because Phase 6's `VulnRemediationSut` contract is the seam Phase 6.5's bench harness reads — flaky determinism at this layer would silently poison every downstream eval.

**Stable harness-facing SUT contract.** Phase 6 owns `VulnRemediationSut`, a stable async contract that Phase 6.5 consumes for evaluation. Concrete LangGraph builders and checkpointers remain implementation details behind that contract. The harness may depend on the contract surface, never on informal assumptions about workflow internals.

**Plugin framing.** The subgraph topology lives in `plugins/vulnerability-remediation--node--npm/subgraph/` per [ADR-0031](production/adrs/0031-plugin-architecture.md); Phase 7's migration plugin will ship its own subgraph without touching this one. Subgraph topology is intentionally NOT inherited across plugins — graph behavior must be explicit per plugin, with reuse happening at the node level via shared Python modules in `src/codewizard_sherpa/nodes/`.

**Exit criteria.** The vuln-remediation loop runs as a LangGraph state machine. Mid-run kill + resume works without state loss. HITL interrupt fires when trust gates fail twice in a row, and a mocked human approval continues the run.

---

## Phase 6.5 — **Per-task-class eval harness + first benches** *(preamble to Phase 7)*

**Why this phase exists.** [Phase 5 ADR-0016](phases/05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) committed to a per-task-class eval harness as the evidence source for trust-tier promotion, threshold calibration ([production ADR-0015](production/adrs/0015-trust-score-threshold-calibration.md)), and eventual LLM-Judge un-deferral ([Phase 5 ADR-0008](phases/05-sandbox-trust-gates/ADRs/0008-llm-judge-persona-deferral.md)), and deferred the implementation explicitly: "Phase 5 does not own the implementation … a 'Phase 6.5 or Phase 7-preamble' implementation slot is needed for the harness package + the first two bench directories (vuln + migration)." This is that slot. The non-integer number is deliberate — renumbering Phases 7–16 to slot a preamble in would ripple through dozens of cross-doc references for no architectural gain.

**Scope.** Implement the eval harness contract. Ship `src/codegenie/eval/` containing the `@register_task_class` decorator (open registry mirroring `@register_probe` and `@register_signal_kind`), the `BenchScore` Pydantic model (`passed: bool`, `score: float ∈ [0, 1]`, `breakdown: dict[str, float]`, `failure_modes: list[str]`, `cost_usd: float`), the harness runner (loads cases, invokes the system-under-test, calls the rubric, aggregates), and the trust-tier promotion gate. Establish the `bench/{task-class-slug}/{cases,rubric.py,registration.py}` directory contract as contract territory (mutations require ADR amendment for `cases/` removals; additions are routine). Backfill `bench/vuln-remediation/` with ≥10 curated ground-truth cases (real CVE-fix scenarios drawn from Phases 3–4's solved-example corpus) plus the task-class rubric, so the harness has a worked example before its first new-task-class consumer in Phase 7. Land an initial `bench/migration-chainguard-distroless/cases/` skeleton with ≥3 seed cases so Phase 7 has somewhere to grow the bench set (Phase 7's exit criteria expand it to ≥10). Extend fence-CI: a task class registered via `@register_task_class("name")` without `bench/{name}/{cases,rubric.py,registration.py}` fails CI. Offline cadence — the harness runs nightly (or per-release-candidate), never per-PR. Per-PR strict-AND ([production ADR-0008](production/adrs/0008-objective-signal-trust-score.md)) is unchanged.

**Tooling & setup.** No new runtime dependencies — `pydantic>=2` (already pinned since Phase 0 S1-01), `pytest`, `pytest-asyncio` (already in dev). A new `[project.optional-dependencies] eval` extras slot in `pyproject.toml` for any harness-only deps that surface during implementation. A small CLI surface: `codegenie eval run --task-class=<name> [--cases=<glob>] [--out=<path>]`. No live LLM/API calls in CI — bench runs in CI use Phase 4's cassette discipline against frozen recordings; live runs are operator-invoked.

**Testing.** Unit tests for the registry (collision raises `TaskClassAlreadyRegistered` — same shape as `SignalKindAlreadyRegistered` from [Phase 5 ADR-0003](phases/05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md)), the `BenchScore` model (`extra="forbid"`, `frozen=True`, mirroring [Phase 5 ADR-0014](phases/05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md)), the rubric contract (input/output types, deterministic given same input). Property test: `BenchScore.score ∈ [0, 1]` for all rubric outputs against all `bench/vuln-remediation/cases/`. Integration test: run the harness end-to-end against `bench/vuln-remediation/` and produce per-case `BenchScore` plus an aggregate. Fence test: a synthetic task class registered without a `bench/` directory triggers a CI failure with a specific diagnostic. Rubric-meta test (deferred to Phase 16 per ADR-0016 §Open Questions §5): mutation-test the rubric itself — skipped here, recorded as a known gap.

**Test-architecture additions** (per §"Test architecture evolution"). The bench harness *is* the scenario-driven slice runner the cross-cutting arc references. Two obligations land here explicitly: (1) **Nightly bench CI job** — a GitHub Actions schedule runs `pytest -m bench` + `codegenie eval run --task-class=<each>` against frozen baselines, with regressions (`bench_score.lower_bound_95` drop > epsilon vs. baseline) gating master; the cassette discipline keeps the run deterministic and cost-free; (2) **Synthetic fixture generator** — initially manual curation per the curation-class contract ([Phase 6.5 ADR-0006](phases/06.5-per-task-class-eval-harness/ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md)); generator becomes load-bearing the moment a task class's `held-out` split needs to grow past hand-author velocity. The generator's contract goes through ADR amendment when the time comes — recorded as a deferred decision today.

**Exit criteria.**
1. `src/codegenie/eval/` package exists; `@register_task_class`, `BenchScore`, harness runner, and trust-tier promotion gate are unit-tested.
2. `bench/vuln-remediation/cases/` contains ≥10 curated cases with provenance metadata; `rubric.py` scores the full set; aggregate `bench_score.lower_bound_95` is recorded as the bronze→silver promotion threshold candidate (numeric value deferred to ADR-0015 calibration once production data accrues).
3. `bench/migration-chainguard-distroless/cases/` contains ≥3 seed cases and a working `rubric.py`; Phase 7 inherits and expands this.
4. Fence-CI extension: a PR that adds `@register_task_class("foo")` without `bench/foo/{cases,rubric.py,registration.py}` fails with a specific diagnostic naming the missing path.
5. The trust-tier promotion gate is wired but does not auto-promote any task class — promotion remains a deliberate, ADR-anchored decision per [Phase 5 ADR-0016 §Decision §4](phases/05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md).
6. `codegenie eval run --task-class=vuln-remediation` exits 0 against the backfilled bench and emits aggregate + per-case `BenchScore` to stdout (JSON) and to `.codegenie/eval/runs/<utc-iso>-<short>.json` (audit format consistent with Phase 0's audit-anchor pattern).
7. Phase 7's exit criteria can reference "`bench/migration-chainguard-distroless/cases/` ≥ 10 cases with `bench_score.lower_bound_95 ≥ tier_threshold[bronze]`" as a hard precondition for shipping the first migration PR at scale.

**Non-goals.** No live LLM calls in CI (cassettes only). No outcome-ledger reconciliation hook — that lands in Phase 13 per ADR-0016 §Consequences. No staleness probe on `last_validated_at` — Phase 16 territory. No threshold-number commitments — ADR-0015 stays deferred; this phase produces the *evidence shape*, not the calibrated numbers. No LLM Judge persona — [Phase 5 ADR-0008](phases/05-sandbox-trust-gates/ADRs/0008-llm-judge-persona-deferral.md) remains deferred; this phase makes its un-deferral *evidence-shaped* (a future ADR introducing the Judge cites a `bench/judgment-arbitration/` score), not un-deferred.

**Dependencies.** Phase 6 (state machine) must be stable — the harness's "system under test" entrypoint for vuln remediation is the `VulnRemediationSut` contract Phase 6 ships, not a concrete graph builder. Phase 4 (cassette discipline) must be operational — bench runs in CI replay frozen cassettes; without that, evals would either be flaky or require live API access.

---

## Phase 7 — **Add migration task class (Chainguard distroless)** *(second task class — extension by addition)*

**Scope.** A second task class is introduced — Chainguard distroless container migration — and the introduction itself is the test: the new task class lands as **new probes** (BaseImageProbe, ShellInvocationTraceProbe), **new Skills** (distroless-migration playbook), and **new recipes** (Dockerfile base-image swap, multi-stage build refactor). Existing plugins and stable existing behavior remain untouched. If Phase 7 reveals a genuinely new cross-task capability, a bounded additive core primitive may land only under its own ADR and then becomes part of the next stable contract surface ([ADR-0039](production/adrs/0039-extension-by-addition-allows-bounded-core-primitives.md)).

**Tooling & setup.** External: `dockerfile-parse`, `dive` (image inspection), `docker buildx`. Chainguard registry credentials. A CVE-to-image-recommendation lookup table.

**Testing.** The full vuln-remediation regression suite runs as a hard gate before merging this phase — proving that adding the new task class did not break the old one. New tests cover the distroless recipes specifically. An end-to-end test migrates a Node.js service with a vulnerable base image to a Chainguard distroless image.

**Plugin framing.** The extension-by-addition invariant is made concrete by the plugin architecture ([ADR-0031](production/adrs/0031-plugin-architecture.md)): Phase 7 adds `plugins/distroless-migration--node--npm/` and does not edit the existing `vulnerability-remediation--node--npm` plugin or stable existing behavior. The one allowed extra surface is an ADR-backed bounded primitive such as `vuln.provenance` when the new task class first exposes a genuinely cross-task need ([ADR-0039](production/adrs/0039-extension-by-addition-allows-bounded-core-primitives.md)).

**Exit criteria.** Both task classes run from the same orchestration. Existing plugins and stable existing behavior are unchanged. Any shared primitive added in the phase is bounded, additive, ADR-backed, and covered by regression tests before it becomes part of the next stable contract surface.

**First home of the `vuln.provenance` primitive.** Per [ADR-0038](production/adrs/0038-vulnerability-provenance-attribution.md), Phase 7 is where the full primitive lands — `vuln.provenance(cve_id, package_id, image_ref?) → Provenance` with seven sum-type variants (`app_direct`, `app_transitive`, `app_vendored`, `base_image`, `runtime_bundled`, `both`, `unknown`). The first concrete `VulnProvenanceAdapter` implementations ship here: an app-layer adapter (likely the Phase 3 `NpmVulnProvenanceAdapter` promoted from its refuse-mode shape) plus at least one base-image adapter (`AlpineVulnProvenanceAdapter` or `DistrolessVulnProvenanceAdapter`). The primitive reads the raw `syft-sbom.json` artifact Phase 2 already writes (`locations[].layerID` is the load-bearing field); **no Phase 2 changes are needed** — this is "wire new readers to existing evidence." The adapter-chain-assembly question (which adapters to invoke and in what order for repos that touch multiple layers) is owned by Phase 7's design pipeline. The `Both` variant — a CVE present in both app and base layers — is the headline test case proving the multi-plugin coordination story works.

---

## Phase 8 — Hierarchical Planner + pre-rendered hot views

**Scope.** A planning supervisor layer sits above the state machines. Given a new workflow, the Supervisor **resolves the matching plugin** for the `(task × language × build-tool)` tuple from the repo's gathered context ([ADR-0031](production/adrs/0031-plugin-architecture.md)) — walking the `extends` inheritance chain, validating manifests via Pydantic, falling back to the universal `(*, *, *)` HITL plugin if no concrete plugin matches. The dispatched plugin's TCCM ([ADR-0029](production/adrs/0029-task-class-context-manifests.md)) is then used to build the Context Bundle via graph-aware queries ([ADR-0030](production/adrs/0030-graph-aware-context-queries.md)) routed through the plugin's language search adapters ([ADR-0032](production/adrs/0032-language-search-adapters.md)). Inside the plugin's subgraph, the planner routes work between recipe lookup, solved-example RAG, and LLM-fallback. The Redis hot views ([ADR-0013](production/adrs/0013-pre-rendered-redis-hot-views.md)) — `available_skills`, `entrypoint`, `risk_flags`, `confidence_summary` — pre-compute the agent context so the planner never has to do expensive lookups inline; the slices pre-rendered are derived from the union of `must_read` entries across the active plugins' TCCMs. The Skills server runs as a local MCP stdio process, prefiguring the eventual MCP topology.

**Tooling & setup.** `redis` in docker-compose. `redis-py` for the client. The `mcp` Python SDK (stdio mode). View pre-rendering runs as a background asyncio task triggered off probe re-runs.

**Testing.** Planner-routing tests: given a fixture context plus skill manifest, assert the chosen path is the expected one. Redis hot-view cache-invalidation tests verify that probe re-runs invalidate the right views. MCP server contract tests pin the public interface.

**Exit criteria.** The planner makes the recipe/RAG/LLM decision and the chosen path is logged on every workflow. Hot views serve agent context in <50ms p95.

---

## Phase 9 — Durable workflow envelope: Temporal

**Scope.** The state machine gets wrapped in a Temporal workflow ([ADR-0003](production/adrs/0003-temporal-as-workflow-substrate.md)). Each LangGraph step becomes a Temporal Activity. The Postgres checkpointer ([ADR-0016](production/adrs/0016-checkpointer-backend.md)) replaces SQLite. Workers run as separate processes. The temporal-ui is wired up locally for live workflow inspection. With Temporal in place, failures survive process restarts; retries are framework-level, not application code.

**Tooling & setup.** `temporalio` Python SDK. The Temporal local dev server (`temporal server start-dev`) for local testing. Postgres added to docker-compose. `alembic` for schema migrations.

**Testing.** Temporal's `WorkflowEnvironment` runs workflow tests in-process. Activity-level unit tests use mocked side effects so the durability layer can be tested independently. Durability tests: kill the worker mid-activity, restart, assert the workflow continues to completion.

**Exit criteria.** Workflows survive process restarts without state loss. The temporal-ui shows live workflow inspection. All retries are framework-level — application code contains no retry loops.

**Canonical event log anchored here.** Phase 9 is where [ADR-0034](production/adrs/0034-event-sourcing-canonical-primitive.md) (event sourcing as canonical primitive) lands operationally. Temporal's workflow history is the workflow-scoped event store natively; this phase adds a typed side-channel **Postgres event log** for workflow-spanning concerns (cost rollups, KG writes, portfolio-level signals — things that don't fit inside a single workflow's history). Events are typed Pydantic models per [ADR-0033](production/adrs/0033-domain-modeling-discipline.md). Existing append-only structures — attempt logs from `phase-story-executor`, draft cost ledgers, plugin-resolution records — migrate to event-stream projections from this point. Phases 11 (Stage 7 Learning), 13 (cost ledger + ROI dashboard) become projections rather than independent stores; their implementations read from this canonical event log.

---

## Phase 10 — Stage 0 Discovery + Stage 1 Assessment

**Scope.** The system now sees a portfolio, not a single repo. Stage 0 (Discovery) enumerates the org's repos through the GitHub API. Stage 1 (Assessment) scores each repo for eligibility against each task class — does the repo's `RepoContext` match the preconditions of vuln remediation? Of distroless migration? The output is a portfolio dashboard listing eligible repos per task class.

**Tooling & setup.** `PyGithub` or GitHub GraphQL via `gql`. Temporal schedules drive nightly portfolio scans.

**Testing.** Discovery tests run against a mock GitHub API (recorded fixtures). Assessment scoring tests use a labeled fixture portfolio with some eligible and some non-eligible repos; correct classification is the assertion.

**Exit criteria.** A nightly scheduled scan runs unattended and produces a portfolio dashboard of eligible repos per task class.

**Assessment-stage task-class routing via `vuln.provenance`.** Per [ADR-0038](production/adrs/0038-vulnerability-provenance-attribution.md), Stage 1 Assessment is the first consumer of the provenance primitive for *routing*: eligibility scoring per task class is computed as a `vuln.provenance` query against each repo's open CVEs. A repo is eligible for `vulnerability-remediation--*` if at least one open CVE has provenance kind ∈ {`app_direct`, `app_transitive`, `both`}; eligible for `distroless-migration--*` if at least one has kind ∈ {`base_image`, `both`} *and* the base image is not already distroless; routed to the universal HITL fallback if all open CVEs have `Unknown` provenance. The `Both` case escalates as a multi-plugin coordination candidate to Phase 8's Planner. This sharpens what was previously described loosely as "score eligibility per task class" — the score is now a typed provenance distribution per repo.

**Repo-side opt-out policy primitive.** Before any portfolio scan can graduate into real PR opening, every watched repo must have a deterministic opt-out surface. Phase 10 introduces the repo-owned `codegenie.yaml` policy file and its loader so repositories can disable specific task classes or all automation before Phase 11 opens real PRs. Phase 13.5 later projects that policy into the operator portal; it does not invent the primitive.

---

## Phase 11 — Stage 6 Handoff + Stage 7 Learning *(first PR at scale)*

**Scope.** The agent now opens real GitHub PRs. Branch naming, label conventions, and PR templates are all standardized. Stage 7 (Learning) ingests merge/close/modified-on-review outcomes and writes them back to the knowledge graph — so the next workflow on a similar problem can hit RAG instead of LLM. The human-merge gate is enforced as a hard invariant per [ADR-0009](production/adrs/0009-humans-always-merge.md): the agent opens, humans merge, no exceptions.

**Tooling & setup.** `PyGithub` for the PR APIs; `gh` CLI as a fallback for cases where PyGithub lags. The KG is initially backed by pgvector inside the existing Postgres — this defers [ADR-0017](production/adrs/0017-knowledge-graph-backend.md) without blocking progress on the rest of the system.

**Testing.** PR creation runs against a sandbox GitHub repo in CI. Webhook ingestion tests cover the merge/close/comment events. Outcome → KG write tests assert that solved cases become retrievable for future RAG queries.

**Exit criteria.** A vuln-remediation PR opens on a real repo, awaits human merge, and the merge outcome is captured back into the KG within 5 minutes of the merge event.

---

## Phase 12 — Stage 3 deep planning + Stage 4 validation depth

**Scope.** Two depth additions. Stage 3 (deep planning) handles cross-repo dependency analysis: a CVE in an internal shared package may require coordinated PRs across N consumer services. Stage 4 (validation depth) goes beyond the sandbox: contract testing, integration test suites, regression-suite execution against staging environments.

**Tooling & setup.** Internal-package depgraph extraction (read `package.json`, lockfiles, and private registry metadata). `pact` for consumer-driven contract tests where applicable. `pytest-xdist` for parallel suite execution.

**Testing.** Multi-repo fixture portfolio with deliberate inter-service dependencies. Assert that a CVE in a shared package produces correlated PR proposals across all consumers.

**Exit criteria.** A single CVE in an internal shared package produces coordinated PRs across all consumer repos in one workflow.

---

## Phase 13 — AgentOps: cost ledger + budget enforcement + ROI dashboard

**Scope.** Cost becomes observable end-to-end and is held to a hard budget. The cost ledger emits entries in three tiers per [ADR-0027](production/adrs/0027-cost-attribution-model.md): direct (one workflow caused it), amortized (continuous gather divided across consumers), overhead (portfolio-level fixed cost). The Budget Enforcer middleware enforces per-workflow caps per [ADR-0025](production/adrs/0025-per-workflow-cost-cap.md): 80% triggers a warning, 100% triggers a halt, `--allow-overrun` provides an explicit escape valve. The ROI dashboard exposes the two headline ratios from [ADR-0026](production/adrs/0026-roi-kpi-model.md) — cost per merged PR and cost per CVE eliminated — alongside the supporting diagnostic metrics.

**Tooling & setup.** OpenTelemetry SDK + collector, Prometheus, Grafana (docker-compose). A custom cost-attribution module that reads OTel spans and writes ledger entries. LLM cost telemetry uses the response `usage` fields plus a per-model rate table.

**Testing.** Ledger schema migration tests. Budget Enforcer unit tests with synthetic spend traces (assert halt fires at exactly 100%). ROI ratio calculation tests against a fixture cost ledger plus outcome data.

**Exit criteria.** Every workflow appears on the cost dashboard with attributed direct + amortized + overhead spend. Budget caps fire correctly on a synthetic runaway workflow.

---

## Phase 13.5 — Operator portal *(read-only views + plugin/task kill-switches)*

**Scope.** The operator portal turns the canonical event log ([ADR-0034](production/adrs/0034-event-sourcing-canonical-primitive.md)) and the cost ledger ([ADR-0024](production/adrs/0024-cost-observability-end-to-end.md)) into an end-to-end view of the system: a live pipeline ribbon (every active workflow against the 7 stages), repo inventory, plugin catalog with TCCMs and recipes, multi-repo campaign rollups, embedded cost panels, and a searchable audit log. The portal is **read-only first** ([ADR-0035](production/adrs/0035-operator-portal-architecture.md)); the only mutation it surfaces is plugin/task enablement kill-switches ([ADR-0036](production/adrs/0036-plugin-task-enablement-dual-source-policy.md)), which prevent *new* work from starting (or short-circuit in-flight work at the next safe stage boundary) but never override gate decisions. Two role-scoped views ship: **ops** (admin allowlist; global read across workflows / campaigns / metrics; write-action scoped to repos the admin owns) and **repo owner** (sees only repos resolved by GitHub OAuth at session). Refresh is event-driven via SSE/WebSocket — no polling. Enablement is a **dual-source policy**: operator-side kill-switches in Postgres + repo-side `codegenie.yaml` opt-outs committed per repo. Resolution is logical OR (either side can disable; fail-closed). Plugin install / upgrade / removal is **explicitly out of scope** (display-only catalog v1; lifecycle deferred to a later phase). Multi-tenant org isolation is **out of scope** (single-org v1; `org_id` column added to new tables from day one for forward compatibility).

**Tooling & setup.** A single-page application (framework choice deferred to phase design) served by a thin FastAPI/Starlette gateway. Postgres tables `plugin_enablement(org_id, scope_task, scope_plugin, scope_repo, enabled, updated_by, updated_at, reason, expires)` and `portal_admins(github_user_id, granted_by, granted_at, reason)`. SSE or WebSocket for the live ribbon (choice deferred). GitHub OAuth via standard OAuth library; session identity resolves to repo-visibility via GitHub API at session establishment. Cost panels embedded from the Phase 13 Grafana dashboard. Portal runs as a Kubernetes deployment in the same cluster as the Phase 14 MCP servers.

**Testing.** Auth contract tests covering every visibility combination (admin/global-read; admin/own-repo-only-write; repo-owner/own-only-read+write; rejection of cross-repo writes). Four-quadrant kill-switch resolution matrix (operator-only / repo-only / both / neither). Mid-flight kill semantics — synthetic in-flight workflow at each of the 7 stages; kill mid-Discovery/Assessment/Scan/Planning/Validation/Learning short-circuits at the next boundary; kill mid-Execution and mid-Handoff is non-interruptible (clean candidate / clean PR). Audit-log replay test: every `PluginEnablementChanged` event in the canonical event log deterministically reconstructs the `plugin_enablement` table state.

**Exit criteria.** An ops admin opens the portal, sees every active workflow at stage granularity, flips a plugin kill-switch for a specific repo, and the next workflow targeting that repo emits a `Skipped(reason="operator-disabled")` event without invoking any gate. A repo owner with GitHub access to `repo-x` opens the portal and sees only `repo-x` and its workflow history. A `codegenie.yaml` opt-out committed to a repo is loaded by the next gather; the portal surfaces it as a "repo-opt-out" badge on the repo page. Every operator action and every workflow skip writes to the canonical event log.

**Depends on:** Phase 9 (canonical event log), Phase 13 (cost ledger + Grafana). Does **not** depend on Phase 14 (continuous gather), though the two phases compose naturally: Phase 14's webhook-driven re-gathers populate the live ribbon richer than the manual triggers available before it.

---

## Phase 14 — Continuous gather + MCP servers operationalized

**Scope.** The `RepoContext` is always-fresh, not on-demand. Triggers — cron, GitHub push webhooks, PR-event webhooks, CVE-feed events, manual — drive incremental re-gathers per [ADR-0006](production/adrs/0006-continuous-deterministic-gather.md). The MCP server topology splits the single local stdio server into separate Context, Skills, Knowledge Graph, and Policy services per [ADR-0023](production/adrs/0023-mcp-server-topology.md). Each MCP server runs as its own Kubernetes deployment.

**Tooling & setup.** A GitHub App for webhook ingestion (signed deliveries). CVE feed parsers for NVD JSON 2.0, GHSA, and OSV. MCP servers run as Kubernetes deployments (k3d locally; EKS in production).

**Testing.** Webhook signature verification tests. CVE feed deduplication tests (the same vuln from three feeds should produce one event). MCP server contract tests pin the published interface.

**Exit criteria.** A new CVE published to NVD triggers a portfolio reassessment within 10 minutes. MCP servers run as separate processes with versioned, tested contracts.

**Conditional fifth MCP server.** Per [ADR-0037](production/adrs/0037-layered-analysis-funnel-scip-typechecker-lsp.md), a **Language MCP server** (warm-pool LSP by language) may join the Context/Skills/KG/Policy quartet *only if* Phases 4 and 15 produce evidence that warm-pool LSP economics beat the per-workflow one-shot type-checker baseline at portfolio scale. Until that evidence exists, this phase does not introduce LSP infrastructure. The conditionality is the load-bearing part — admission is not automatic, and [ADR-0023](production/adrs/0023-mcp-server-topology.md) (MCP server topology) is the place where the un-deferral, if it happens, is recorded.

---

## Phase 15 — **Agentic recipe authoring (deterministic → agentic)** *(third task class — recipe creation itself)*

**Scope.** This is where the deterministic → agentic arc completes. The system now **authors new recipes and skills itself**. When the LLM fallback solves a problem and the same problem shape recurs (detected by clustering solved-example embeddings), an agent proposes a new deterministic recipe — or a new Skill — to handle the case mechanically going forward. Humans review and accept; the recipe lands in the catalog. The compounding-savings story from [ADR-0011](production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) becomes real: KG reuse rate rises, per-workflow LLM cost trends down, and the cost-per-merged-PR ratio improves over time even as more cases are handled.

**Tooling & setup.** The Anthropic agent SDK or the equivalent once [ADR-0020](production/adrs/0020-leaf-agents-sdk.md) is resolved. The recipe-authoring workflow itself is a LangGraph subgraph. Code-generation guardrails are non-negotiable: a proposed recipe must pass its own test suite (covering all the solved examples it claims to replace) before it reaches a human reviewer.

**Testing.** End-to-end test: feed 10 recorded LLM-fallback solutions for the same problem shape, assert the system proposes a deterministic recipe that solves all 10. Property tests on the proposed recipes themselves — they must be deterministic, idempotent, and refuse to apply outside their declared preconditions.

**Exit criteria.** At least one recipe authored by the system has been merged after human review, and that recipe handles a new vuln case end-to-end without any LLM invocation. The knowledge-graph reuse rate ([ADR-0026](production/adrs/0026-roi-kpi-model.md) supporting metric) ticks up after this phase ships.

**First admission of per-workflow LSP-in-jail.** Per [ADR-0037](production/adrs/0037-layered-analysis-funnel-scip-typechecker-lsp.md), the recipe-authoring tight edit-verify inner loop is the first place where LSP earns its keep over the one-shot type-checker baseline — the warmup tax amortizes across many per-workflow edits in a single agent loop. Phase 15 introduces LSP as a per-workflow ephemeral substrate inside `SubprocessJail` (the same Port Phase 5+ ships), with `ALLOWED_BINARIES` amendments per language server and a `NetworkPolicy = RegistryAllowlist` carve-out for dep resolution. **LSP is still not admitted to the gather pipeline** — Phase 15's use is scoped to the agent's authoring loop only.

---

## Phase 16 — Production hardening

**Scope.** Outstanding deferred ADR decisions get resolved with real production data, not speculation: sandbox stack ([ADR-0019](production/adrs/0019-sandbox-stack.md)), policy engine build-vs-adopt ([ADR-0021](production/adrs/0021-policy-engine-build-vs-adopt.md)), supervisor pure-routing vs LLM ([ADR-0018](production/adrs/0018-supervisor-pure-routing-vs-llm.md)), leaf SDK choice ([ADR-0020](production/adrs/0020-leaf-agents-sdk.md)), per-subgraph topology ([ADR-0022](production/adrs/0022-per-subgraph-topology.md)), trust-threshold calibration ([ADR-0015](production/adrs/0015-trust-score-threshold-calibration.md)). The system grows multi-tenancy, SSO with RBAC, an audit trail, compliance posture, runbooks, and an on-call rotation.

**Tooling & setup.** OIDC integration (Okta, Auth0, or Cognito). Postgres RBAC. PagerDuty or Opsgenie for paging. Runbook templates committed to the repo. SOC2 and ISO27001 audit readiness.

**Testing.** Chaos tests (Litmus or similar). Failover drills. External pentest as part of audit readiness.

**Exit criteria.** The system runs in a multi-tenant production environment with audit / RBAC / on-call established. Every deferred ADR is either resolved or explicitly extended with a new evidence-collection window.

---

## Arc summary — deterministic → agentic

The spine of the roadmap is the progressive introduction of probabilistic behavior, always preceded by the deterministic version of the same capability:

- **Phases 0–2** are entirely deterministic. Context gathering is a closed-form evidence collector. No LLM, no probabilism, no judgments — just facts.
- **Phase 3** introduces the first transform. Deterministic recipes (OpenRewrite / AST). Still no LLM. This phase exists specifically to prove the deterministic path works *before* anything probabilistic is added.
- **Phase 4** introduces the LLM, but only as a fallback after recipe-lookup and solved-example RAG. The decision chain is structural: recipe → RAG → LLM. Confidence is computed from objective signals only.
- **Phases 5–6** wrap that decision chain in a sandbox + trust gates and then a proper state machine. The state machine is itself deterministic; the LLM is only ever called inside a single leaf node.
- **Phases 7–14** scale the architecture outward — second task class, planner, durable workflows, full pipeline, ops — without changing the deterministic-first invariant.
- **Phase 15** closes the loop: the system writes its own deterministic recipes from solved LLM examples. Every successful LLM invocation is a candidate for promotion into a future deterministic path. The compounding-savings story from the ADRs becomes measurable.
- **Phase 16** hardens what's there.

The invariant across all 17 phases: **probabilistic components are leaves, never roots.** The orchestration, gating, and decision routing are deterministic at every level. The LLM is called for judgment; never for control flow.
