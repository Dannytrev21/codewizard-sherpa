# codewizard-sherpa — Phased Roadmap

This document sequences the work from a local bullet tracer through to a multi-tenant production system. It is **epic-level**: each phase defines *what ships*, not *how it is built*. Detailed designs live in [`production/design.md`](production/design.md) and [`production/adrs/`](production/adrs/).

## Reading guide

- **Phases are sequential.** Each builds on the previous one's exit criteria. Skipping is rarely safe — the architecture is layered.
- **Task classes are introduced one at a time.** Vulnerability remediation comes first (Phase 3), Chainguard distroless migration second (Phase 7), agentic recipe authoring third (Phase 15). This sequencing exists to prove that the probe + skill + recipe contracts extend by **addition**, not by editing.
- **Determinism comes before LLM.** Every phase that introduces probabilistic behavior is preceded by the deterministic version of the same capability. The arc is visible across Phases 3 → 4 → 15.
- **Every phase commits to tooling, tests, and exit criteria up front.** Setup is not retrofitted at the end. Documentation, CI, mypy, ruff, pre-commit, and the docs site land in Phase 0 — not phase 16.
- **Read alongside:** [`production/design.md`](production/design.md) (the canonical architecture reference), [`localv2.md`](localv2.md) (the local POC contract — frozen as the same contract used in the service), and the [ADR index](production/adrs/README.md).

## Phase summary

**Design pipeline status legend:** ✅ = full design pipeline complete (`final-design.md` + `phase-arch-design.md` + per-phase ADRs + `High-level-impl.md` + stories backlog under `docs/phases/NN-<slug>/`). Empty = not yet designed.

| # | Title | Task classes | First-time introduction of | Design |
|---|---|---|---|---|
| 0 | Bullet tracer + project foundations | — | CLI shell, `pyproject.toml`, CI, docs site, mypy, ruff, pytest, pre-commit | ✅ [00-bullet-tracer-foundations](phases/00-bullet-tracer-foundations/) |
| 1 | Context gathering — Layer A (Node.js) | — | Probe contract, coordinator, content-addressed cache, schema validation | ✅ [01-context-gather-layer-a-node](phases/01-context-gather-layer-a-node/) |
| 2 | Context gathering — Layers B–G | — | IndexHealthProbe (B2 — the critical one), traces, depgraph, security, conventions, skills loader | ✅ [02-context-gather-layers-b-g](phases/02-context-gather-layers-b-g/) |
| 3 | **Vuln remediation — deterministic recipe path** | vuln | First end-to-end transform; OpenRewrite / AST; writes a real diff | ✅ [03-vuln-deterministic-recipe](phases/03-vuln-deterministic-recipe/) |
| 4 | Vuln remediation — LLM fallback + solved-example RAG | vuln | Leaf LLM agents, local vector DB, recipe → RAG → LLM-fallback decision chain | ✅ [04-vuln-llm-fallback-rag](phases/04-vuln-llm-fallback-rag/) |
| 5 | Sandbox + Trust-Aware gates | vuln | microVM isolation, build/test/runtime gates, three-retry default | ✅ [05-sandbox-trust-gates](phases/05-sandbox-trust-gates/) |
| 6 | SHERPA-style state machine for the vuln loop | vuln | LangGraph runtime, Pydantic state ledger, `interrupt()` + SQLite checkpointer | ✅ [06-sherpa-state-machine](phases/06-sherpa-state-machine/) |
| 6.5 | **Per-task-class eval harness + first benches** *(preamble to Phase 7)* | vuln | `eval/` package, `@register_task_class` registry, `BenchScore` model, `bench/{task-class}/` directory contract, fence-CI gate, backfilled `bench/vuln-remediation/` | ✅ [06.5-per-task-class-eval-harness](phases/06.5-per-task-class-eval-harness/) |
| 7 | **Add migration task class (Chainguard distroless)** | vuln + migration | Extension by addition — proves contracts extend without edits | ✅ [07-migration-task-class](phases/07-migration-task-class/) |
| 8 | Hierarchical Planner + pre-rendered hot views | vuln + migration | Planning supervisor, Redis hot views, MCP-style stdio Skills server |
| 9 | Durable workflow envelope — Temporal | vuln + migration | Temporal workflows + activities, Postgres checkpointer, temporal-ui |
| 10 | Stage 0 Discovery + Stage 1 Assessment | vuln + migration | Multi-repo discovery (GitHub API), assessment scoring, eligibility filtering |
| 11 | Stage 6 Handoff + Stage 7 Learning | vuln + migration | GitHub PR opening, outcome ingestion, KG write-back |
| 12 | Stage 3 deep planning + Stage 4 validation depth | vuln + migration | Cross-repo dep analysis, contract testing, regression suites beyond sandbox |
| 13 | AgentOps — cost ledger + budget enforcement + ROI dashboard | vuln + migration | Three-tier cost ledger, Budget Enforcer, Grafana ROI dashboard |
| 14 | Continuous gather + MCP servers operationalized | vuln + migration | Cron / webhook / PR / CVE-feed triggers; Context / Skills / KG / Policy MCP servers split |
| 15 | **Agentic recipe authoring (deterministic → agentic)** | vuln + migration + recipe-authoring | LLM proposes new recipes/skills from solved examples; humans accept |
| 16 | Production hardening | all | Deferred ADRs resolved; multi-tenancy, SSO/RBAC, audit, runbooks, on-call |

The two notable value milestones: **Phase 3** is the first time a real transform ships (locally). **Phase 11** is the first time a real PR opens at portfolio scale.

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

**Exit criteria.** Given a Node.js repo with a known npm CVE, the system writes a working patch diff on a local branch that — when applied — installs cleanly and passes the repo's own tests.

---

## Phase 4 — Vuln remediation: LLM fallback + solved-example RAG

**Scope.** Not every vulnerability fix is mechanical. Transitive vulns sometimes require a peer-dep upgrade. Major-version bumps come with breaking-change call-site rewrites. When the deterministic recipe path fails or returns a low-confidence result, the system falls back to a solved-example RAG lookup first, then to a leaf LLM agent if RAG misses. This is the **recipe → RAG → LLM-fallback** decision chain per [ADR-0011](production/adrs/0011-recipe-first-rag-llm-fallback-planning.md). Confidence is computed from **objective signals only** — no LLM self-reported confidence — per [ADR-0008](production/adrs/0008-objective-signal-trust-score.md).

**Tooling & setup.** `anthropic` Python SDK for the leaf agent. `chromadb` (local mode) or `qdrant-client` (local docker) for the solved-example vector store. Embeddings via `sentence-transformers` locally or Voyage if remote is acceptable. `langgraph` imported minimally — just enough to wrap the leaf agent invocation.

**Testing.** Recorded LLM responses via `pytest-recording` (VCR cassettes) so CI runs are deterministic and free. Confidence-thresholding tests use synthetic objective signals to assert the decision chain routes correctly. RAG retrieval quality is tested against a labeled fixture set: known query → known top-k expected.

**Exit criteria.** A breaking-change vuln (e.g., a major-version-bump CVE) is solved end-to-end with the LLM fallback and recorded into the solved-example store. Re-running the same case hits RAG, not LLM, and produces an equivalent fix at lower cost.

---

## Phase 5 — Sandbox + Trust-Aware gates

**Scope.** Nothing leaves the agent's hands without being verified. The sandbox layer adds microVM isolation ([ADR-0012](production/adrs/0012-microvm-sandbox-for-trust-gates.md)) — proposed diffs are applied inside an isolated environment and checked against Trust-Aware gates: the build passes, tests pass, no policy violations fire, and the runtime trace stays stable (no new shell invocations, no new network endpoints). The three-retry default per gate ([ADR-0014](production/adrs/0014-three-retry-default-per-gate.md)) gives the system a chance to recover before escalating to humans.

**Tooling & setup.** Local dev (including macOS): Docker-in-Docker, since it is the portable choice. Linux dev or CI: Firecracker explored as a faster, stricter alternative — choice of sandbox stack itself remains deferred per [ADR-0019](production/adrs/0019-sandbox-stack.md). Tests use `pytest-docker` for orchestration of the sandbox lifecycle.

**Testing.** Property tests for gate decisions: for every combination of objective signals, the gate's outcome is asserted. Integration tests run real builds inside the sandbox (slow but high-signal). Negative cases — broken build, failing tests, policy violation — are explicit tests that the gate rejects, not edge cases.

**Exit criteria.** No transform leaves the sandbox unverified. The three-retry loop is demonstrated end-to-end with at least one case that fails on retry-1 and recovers on retry-2.

---

## Phase 6 — SHERPA-style state machine for the vuln loop

**Scope.** The deterministic + LLM + sandbox loop is now stitched together as a proper state machine — restartable, inspectable, with deterministic transitions. LangGraph is the runtime ([ADR-0002](production/adrs/0002-langgraph-as-runtime-sherpa-as-discipline.md)). The shared mutable state is a **Pydantic-typed state ledger**: nodes only read from and write to that ledger; nodes never call other nodes directly. Conditional edges are the Trust-Aware gates. `interrupt()` plus a SQLite checkpointer enables human-in-the-loop pause and resume.

**Tooling & setup.** `langgraph`, `pydantic`, `aiosqlite` for the checkpointer, `langgraph-cli` for graph inspection.

**Testing.** State-transition tests assert every conditional edge is exercised at least once. Replay tests use the checkpointer to kill a mid-run workflow, resume it, and assert the same final state. HITL interrupt tests inject mocked human responses and verify the workflow continues correctly.

**Exit criteria.** The vuln-remediation loop runs as a LangGraph state machine. Mid-run kill + resume works without state loss. HITL interrupt fires when trust gates fail twice in a row, and a mocked human approval continues the run.

---

## Phase 6.5 — **Per-task-class eval harness + first benches** *(preamble to Phase 7)*

**Why this phase exists.** [Phase 5 ADR-0016](phases/05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) committed to a per-task-class eval harness as the evidence source for trust-tier promotion, threshold calibration ([production ADR-0015](production/adrs/0015-trust-score-threshold-calibration.md)), and eventual LLM-Judge un-deferral ([Phase 5 ADR-0008](phases/05-sandbox-trust-gates/ADRs/0008-llm-judge-persona-deferral.md)), and deferred the implementation explicitly: "Phase 5 does not own the implementation … a 'Phase 6.5 or Phase 7-preamble' implementation slot is needed for the harness package + the first two bench directories (vuln + migration)." This is that slot. The non-integer number is deliberate — renumbering Phases 7–16 to slot a preamble in would ripple through dozens of cross-doc references for no architectural gain.

**Scope.** Implement the eval harness contract. Ship `src/codegenie/eval/` containing the `@register_task_class` decorator (open registry mirroring `@register_probe` and `@register_signal_kind`), the `BenchScore` Pydantic model (`passed: bool`, `score: float ∈ [0, 1]`, `breakdown: dict[str, float]`, `failure_modes: list[str]`, `cost_usd: float`), the harness runner (loads cases, invokes the system-under-test, calls the rubric, aggregates), and the trust-tier promotion gate. Establish the `bench/{task-class-slug}/{cases,rubric.py,registration.py}` directory contract as contract territory (mutations require ADR amendment for `cases/` removals; additions are routine). Backfill `bench/vuln-remediation/` with ≥10 curated ground-truth cases (real CVE-fix scenarios drawn from Phases 3–4's solved-example corpus) plus the task-class rubric, so the harness has a worked example before its first new-task-class consumer in Phase 7. Land an initial `bench/migration-chainguard-distroless/cases/` skeleton with ≥3 seed cases so Phase 7 has somewhere to grow the bench set (Phase 7's exit criteria expand it to ≥10). Extend fence-CI: a task class registered via `@register_task_class("name")` without `bench/{name}/{cases,rubric.py,registration.py}` fails CI. Offline cadence — the harness runs nightly (or per-release-candidate), never per-PR. Per-PR strict-AND ([production ADR-0008](production/adrs/0008-objective-signal-trust-score.md)) is unchanged.

**Tooling & setup.** No new runtime dependencies — `pydantic>=2` (already pinned since Phase 0 S1-01), `pytest`, `pytest-asyncio` (already in dev). A new `[project.optional-dependencies] eval` extras slot in `pyproject.toml` for any harness-only deps that surface during implementation. A small CLI surface: `codegenie eval run --task-class=<name> [--cases=<glob>] [--out=<path>]`. No live LLM/API calls in CI — bench runs in CI use Phase 4's cassette discipline against frozen recordings; live runs are operator-invoked.

**Testing.** Unit tests for the registry (collision raises `TaskClassAlreadyRegistered` — same shape as `SignalKindAlreadyRegistered` from [Phase 5 ADR-0003](phases/05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md)), the `BenchScore` model (`extra="forbid"`, `frozen=True`, mirroring [Phase 5 ADR-0014](phases/05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md)), the rubric contract (input/output types, deterministic given same input). Property test: `BenchScore.score ∈ [0, 1]` for all rubric outputs against all `bench/vuln-remediation/cases/`. Integration test: run the harness end-to-end against `bench/vuln-remediation/` and produce per-case `BenchScore` plus an aggregate. Fence test: a synthetic task class registered without a `bench/` directory triggers a CI failure with a specific diagnostic. Rubric-meta test (deferred to Phase 16 per ADR-0016 §Open Questions §5): mutation-test the rubric itself — skipped here, recorded as a known gap.

**Exit criteria.**
1. `src/codegenie/eval/` package exists; `@register_task_class`, `BenchScore`, harness runner, and trust-tier promotion gate are unit-tested.
2. `bench/vuln-remediation/cases/` contains ≥10 curated cases with provenance metadata; `rubric.py` scores the full set; aggregate `bench_score.mean` is recorded as the bronze→silver promotion threshold candidate (numeric value deferred to ADR-0015 calibration once production data accrues).
3. `bench/migration-chainguard-distroless/cases/` contains ≥3 seed cases and a working `rubric.py`; Phase 7 inherits and expands this.
4. Fence-CI extension: a PR that adds `@register_task_class("foo")` without `bench/foo/{cases,rubric.py,registration.py}` fails with a specific diagnostic naming the missing path.
5. The trust-tier promotion gate is wired but does not auto-promote any task class — promotion remains a deliberate, ADR-anchored decision per [Phase 5 ADR-0016 §Decision §4](phases/05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md).
6. `codegenie eval run --task-class=vuln-remediation` exits 0 against the backfilled bench and emits aggregate + per-case `BenchScore` to stdout (JSON) and to `.codegenie/eval/runs/<utc-iso>-<short>.json` (audit format consistent with Phase 0's audit-anchor pattern).
7. Phase 7's exit criteria can reference "`bench/migration-chainguard-distroless/cases/` ≥ 10 cases with `bench_score.mean ≥ tier_threshold[bronze]`" as a hard precondition for shipping the first migration PR at scale.

**Non-goals.** No live LLM calls in CI (cassettes only). No outcome-ledger reconciliation hook — that lands in Phase 13 per ADR-0016 §Consequences. No staleness probe on `last_validated_at` — Phase 16 territory. No threshold-number commitments — ADR-0015 stays deferred; this phase produces the *evidence shape*, not the calibrated numbers. No LLM Judge persona — [Phase 5 ADR-0008](phases/05-sandbox-trust-gates/ADRs/0008-llm-judge-persona-deferral.md) remains deferred; this phase makes its un-deferral *evidence-shaped* (a future ADR introducing the Judge cites a `bench/judgment-arbitration/` score), not un-deferred.

**Dependencies.** Phase 6 (state machine) must be stable — the harness's "system under test" entrypoint for vuln remediation is the LangGraph workflow Phase 6 ships. Phase 4 (cassette discipline) must be operational — bench runs in CI replay frozen cassettes; without that, evals would either be flaky or require live API access.

---

## Phase 7 — **Add migration task class (Chainguard distroless)** *(second task class — extension by addition)*

**Scope.** A second task class is introduced — Chainguard distroless container migration — and the introduction itself is the test: the new task class lands as **new probes** (BaseImageProbe, ShellInvocationTraceProbe), **new Skills** (distroless-migration playbook), and **new recipes** (Dockerfile base-image swap, multi-stage build refactor). **No edits to existing Phase 0–6 code.** This is the "extension by addition" invariant from `CLAUDE.md` being put on the test stand. If anything in Phases 0–6 had to change, the contract was wrong.

**Tooling & setup.** External: `dockerfile-parse`, `dive` (image inspection), `docker buildx`. Chainguard registry credentials. A CVE-to-image-recommendation lookup table.

**Testing.** The full vuln-remediation regression suite runs as a hard gate before merging this phase — proving that adding the new task class did not break the old one. New tests cover the distroless recipes specifically. An end-to-end test migrates a Node.js service with a vulnerable base image to a Chainguard distroless image.

**Exit criteria.** Both task classes run from the same orchestration. The diff for this phase touches *only* new files — no Phase 0–6 source code is modified.

---

## Phase 8 — Hierarchical Planner + pre-rendered hot views

**Scope.** A planning supervisor layer sits above the state machine. Given a new workflow, it consults the pre-rendered hot views and routes work between recipe lookup, solved-example RAG, and LLM-fallback. The Redis hot views ([ADR-0013](production/adrs/0013-pre-rendered-redis-hot-views.md)) — `available_skills`, `entrypoint`, `risk_flags`, `confidence_summary` — pre-compute the agent context so the planner never has to do expensive lookups inline. The Skills server runs as a local MCP stdio process, prefiguring the eventual MCP topology.

**Tooling & setup.** `redis` in docker-compose. `redis-py` for the client. The `mcp` Python SDK (stdio mode). View pre-rendering runs as a background asyncio task triggered off probe re-runs.

**Testing.** Planner-routing tests: given a fixture context plus skill manifest, assert the chosen path is the expected one. Redis hot-view cache-invalidation tests verify that probe re-runs invalidate the right views. MCP server contract tests pin the public interface.

**Exit criteria.** The planner makes the recipe/RAG/LLM decision and the chosen path is logged on every workflow. Hot views serve agent context in <50ms p95.

---

## Phase 9 — Durable workflow envelope: Temporal

**Scope.** The state machine gets wrapped in a Temporal workflow ([ADR-0003](production/adrs/0003-temporal-as-workflow-substrate.md)). Each LangGraph step becomes a Temporal Activity. The Postgres checkpointer ([ADR-0016](production/adrs/0016-checkpointer-backend.md)) replaces SQLite. Workers run as separate processes. The temporal-ui is wired up locally for live workflow inspection. With Temporal in place, failures survive process restarts; retries are framework-level, not application code.

**Tooling & setup.** `temporalio` Python SDK. The Temporal local dev server (`temporal server start-dev`) for local testing. Postgres added to docker-compose. `alembic` for schema migrations.

**Testing.** Temporal's `WorkflowEnvironment` runs workflow tests in-process. Activity-level unit tests use mocked side effects so the durability layer can be tested independently. Durability tests: kill the worker mid-activity, restart, assert the workflow continues to completion.

**Exit criteria.** Workflows survive process restarts without state loss. The temporal-ui shows live workflow inspection. All retries are framework-level — application code contains no retry loops.

---

## Phase 10 — Stage 0 Discovery + Stage 1 Assessment

**Scope.** The system now sees a portfolio, not a single repo. Stage 0 (Discovery) enumerates the org's repos through the GitHub API. Stage 1 (Assessment) scores each repo for eligibility against each task class — does the repo's `RepoContext` match the preconditions of vuln remediation? Of distroless migration? The output is a portfolio dashboard listing eligible repos per task class.

**Tooling & setup.** `PyGithub` or GitHub GraphQL via `gql`. Temporal schedules drive nightly portfolio scans.

**Testing.** Discovery tests run against a mock GitHub API (recorded fixtures). Assessment scoring tests use a labeled fixture portfolio with some eligible and some non-eligible repos; correct classification is the assertion.

**Exit criteria.** A nightly scheduled scan runs unattended and produces a portfolio dashboard of eligible repos per task class.

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

## Phase 14 — Continuous gather + MCP servers operationalized

**Scope.** The `RepoContext` is always-fresh, not on-demand. Triggers — cron, GitHub push webhooks, PR-event webhooks, CVE-feed events, manual — drive incremental re-gathers per [ADR-0006](production/adrs/0006-continuous-deterministic-gather.md). The MCP server topology splits the single local stdio server into separate Context, Skills, Knowledge Graph, and Policy services per [ADR-0023](production/adrs/0023-mcp-server-topology.md). Each MCP server runs as its own Kubernetes deployment.

**Tooling & setup.** A GitHub App for webhook ingestion (signed deliveries). CVE feed parsers for NVD JSON 2.0, GHSA, and OSV. MCP servers run as Kubernetes deployments (k3d locally; EKS in production).

**Testing.** Webhook signature verification tests. CVE feed deduplication tests (the same vuln from three feeds should produce one event). MCP server contract tests pin the published interface.

**Exit criteria.** A new CVE published to NVD triggers a portfolio reassessment within 10 minutes. MCP servers run as separate processes with versioned, tested contracts.

---

## Phase 15 — **Agentic recipe authoring (deterministic → agentic)** *(third task class — recipe creation itself)*

**Scope.** This is where the deterministic → agentic arc completes. The system now **authors new recipes and skills itself**. When the LLM fallback solves a problem and the same problem shape recurs (detected by clustering solved-example embeddings), an agent proposes a new deterministic recipe — or a new Skill — to handle the case mechanically going forward. Humans review and accept; the recipe lands in the catalog. The compounding-savings story from [ADR-0011](production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) becomes real: KG reuse rate rises, per-workflow LLM cost trends down, and the cost-per-merged-PR ratio improves over time even as more cases are handled.

**Tooling & setup.** The Anthropic agent SDK or the equivalent once [ADR-0020](production/adrs/0020-leaf-agents-sdk.md) is resolved. The recipe-authoring workflow itself is a LangGraph subgraph. Code-generation guardrails are non-negotiable: a proposed recipe must pass its own test suite (covering all the solved examples it claims to replace) before it reaches a human reviewer.

**Testing.** End-to-end test: feed 10 recorded LLM-fallback solutions for the same problem shape, assert the system proposes a deterministic recipe that solves all 10. Property tests on the proposed recipes themselves — they must be deterministic, idempotent, and refuse to apply outside their declared preconditions.

**Exit criteria.** At least one recipe authored by the system has been merged after human review, and that recipe handles a new vuln case end-to-end without any LLM invocation. The knowledge-graph reuse rate ([ADR-0026](production/adrs/0026-roi-kpi-model.md) supporting metric) ticks up after this phase ships.

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
