# Autonomous Distroless Migration Service — Research & Design

A shift from developer-invoked CLI to a **service**: a scheduled pipeline that discovers candidate repos, classifies them, analyzes them in detail, plans migration steps, and then hands off to either a human or an autonomous executor to apply and validate the steps. This document researches the closest prior art, maps it to your requirements, and proposes a concrete architecture.

---

## 1. What you are actually building (named precisely)

In the literature this pattern is called a **multi-stage agentic migration pipeline with static-analysis-grounded RAG and durable-execution orchestration.** Long name, real thing. The closest published analog is **Konveyor AI (Kai)** from Red Hat, which does exactly this shape for Java-to-Quarkus / framework upgrades. [konveyor.io](https://konveyor.io) Its workflow: static analysis with `analyzer-lsp` + rulesets → issue list → RAG lookup of "solved examples" from prior org migrations → LLM-generated fix → iterative validation. [CNCF](https://www.cncf.io/blog/2024/11/22/konveyor-ai-supporting-application-modernization/)

Your system differs in three important ways:
- **Target is distroless**, not framework upgrade.
- **Scope is portfolio-wide autonomous scanning**, not developer-invoked in IDE.
- **Languages are Node.js and Python**, where Kai has been Java-first (though its `kantra` analyzer added Go/.NET/Node.js support).

The naming matters because it tells you which building blocks have been figured out already and which you'd be designing from scratch.

---

## 2. Prior art worth copying from

### 2.1 Konveyor AI (Kai) — the closest analog

Architecture to copy:
- **`analyzer-lsp`** — a Language Server Protocol based analyzer that runs rules over a codebase and emits "incidents" (structured issue records).
- **Rulesets** — ~2,400 community rules for framework migrations, written in YAML. Extensible to custom rules. [Konveyor rulesets](https://github.com/konveyor/rulesets)
- **Solved-example store** — an MCP-backed solution server (`kai_mcp_solution_server`) that holds prior successful migration diffs keyed by incident type, retrieved via vector search during LLM planning. [Kai repo](https://github.com/konveyor/kai)
- **TaskManager** — a reactive planner that coordinates TaskRunner components and validation steps in a priority-driven workflow.

What to adapt, not copy:
- Kai's IDE-centric surface (VS Code extension) is wrong for your service model.
- Kai's rulesets are framework-focused; you'll write distroless-specific rules.

### 2.2 OpenRewrite + rewrite-docker — deterministic recipes where possible

[rewrite-docker](https://github.com/openrewrite/rewrite-docker) is an OpenRewrite module with recipes for Docker. Relevant recipes include `FindBaseImages` (search), `AddCleanupToAptGetRunInstructions` (size reduction), `AddOciImageLabels`, `AddUser` (non-root, CIS 4.1), `ChangeDockerfileInstruction`, and text-based recipes for base-image swaps. [Docker recipes index](https://docs.openrewrite.org/recipes/docker)

**What this buys you:** for whole categories of changes, you don't need an LLM. OpenRewrite recipes are idempotent, testable, and fast. The LLM is reserved for decisions that require reasoning — which base image, whether a runtime dependency is safe to drop, how to restructure a multi-stage build when the existing one is tangled.

The "if there is an open rewrite recipe it will use that instead" that you mentioned in the brief is exactly the right instinct. Make it the default path; LLM is the fallback.

### 2.3 Temporal — durable execution for long-running agent workflows

Temporal is the production pattern for exactly this kind of pipeline. OpenAI's Codex runs on Temporal; Replit migrated their coding agent to Temporal for reliability. [Temporal AI](https://temporal.io/solutions/ai) [dynamic agents](https://temporal.io/blog/of-course-you-can-build-dynamic-ai-agents-with-temporal)

The pattern it gives you:
- **Workflow** (deterministic orchestration) = the state machine of a single repo's migration journey.
- **Activities** (non-deterministic side-effectful work) = LLM calls, rule runs, test runs, PR opens.
- **Signals** = human approval, stage promotion, retry requests.
- **Durable timers** = "wait up to 72 hours for human review."

The crucial property: if an activity crashes mid-migration, the workflow resumes at that exact step on the next worker, with all prior state intact. For portfolio-scale (hundreds of repos), nothing else is close in reliability.

### 2.4 Tree-sitter for the "detailed scan" stage

For the stage you described as "scans the repo in detail, maybe AST or similar, to put that into a format that can be consumed by the next step" — **tree-sitter** is the canonical tool. [tree-sitter mcp](https://pypi.org/project/mcp-server-tree-sitter/)

Properties that matter for your pipeline:
- **Offline** — source never leaves the machine, which is the right default for source-code analysis at org scale.
- **Fast** — O(file size), seconds per repo.
- **Uniform** — same AST node shape across 19+ languages; Node and Python are both first-class.
- **Battle-tested grammars** used in GitHub's code navigation, Neovim, Zed.

The output you want to produce: a structured AST summary (function signatures, imports, call sites, dynamic-loading patterns, FS writes, subprocess invocations) plus the Dockerfile parse and dependency manifest. This is your "migration context packet" that feeds the planner.

### 2.5 Syft/Grype for the discovery + eligibility stage

[Syft](https://github.com/anchore/syft) generates SBOMs from container images; [Grype](https://github.com/anchore/grype) scans them for CVEs. [Trivy](https://github.com/aquasecurity/trivy) does both. These are the standard deterministic tools for:
- Discovering which base image a repo is currently using (pull the image, inspect `FROM` layers, or scan the built image's metadata).
- Quantifying the CVE delta between current and target (distroless) images — useful for prioritizing which repos are most worth migrating first.

### 2.6 Copilot Agent Mode research — what breaks in autonomous migration

The Emergent Mind analysis of Copilot Agent Mode on SQLAlchemy migrations is the most honest writeup of autonomous-migration failure modes I've seen. Headline findings:
- **High migration coverage ≠ post-migration correctness.** Test pass rates trail coverage significantly.
- **Dependency/environment issues** are the main failure class — not core logic.
- **Fully autonomous migration is insufficient** for production; human-in-the-loop and runtime feedback (dynamic test oracles, targeted error logging) close the gap.

Practical implication for your design: even if the execution stage is "autonomous agent," there must be a human gate before the PR merges. Autonomous through planning and *proposing* a PR is fine. Autonomous merging is where things catch fire.

---

## 3. Mapping your requirements to a concrete pipeline

Here's the pipeline you described, fleshed out into named stages with the right tool at each layer.

```
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 0 — DISCOVERY (deterministic, scheduled)                     │
│  Scans org repos; tags eligible candidates.                         │
├─────────────────────────────────────────────────────────────────────┤
│  STAGE 1 — ASSESSMENT (deterministic + LLM)                         │
│  Routes to language-specific assessor; produces Cat 1/2/3.          │
├─────────────────────────────────────────────────────────────────────┤
│  STAGE 2 — DEEP SCAN (deterministic)                                │
│  Tree-sitter AST + Dockerfile parse + dep manifest → context packet │
├─────────────────────────────────────────────────────────────────────┤
│  STAGE 3 — PLANNING (recipe-first, LLM-fallback)                    │
│  Match OpenRewrite/rulesets; fall back to LLM; emit step files.     │
├─────────────────────────────────────────────────────────────────────┤
│  STAGE 4 — EXECUTION (human OR autonomous agent)                    │
│  Applies each step; validates each step; resumable.                 │
├─────────────────────────────────────────────────────────────────────┤
│  STAGE 5 — VALIDATION (deterministic + LLM adjudication)            │
│  Full build, Prove-It checks, CVE delta, policy checks.             │
├─────────────────────────────────────────────────────────────────────┤
│  STAGE 6 — HANDOFF (PR, human gate)                                 │
│  PR opened; required human approval; merge is NOT automatic.        │
├─────────────────────────────────────────────────────────────────────┤
│  STAGE 7 — LEARNING (feedback into knowledge base)                  │
│  Successful migration diff stored as solved-example; kb updated.    │
└─────────────────────────────────────────────────────────────────────┘
```

Each stage is a Temporal activity (or a child workflow for the complex ones). The overall per-repo migration is a Temporal workflow that can span hours to weeks (real calendar time, including human review pauses) and survive any infrastructure failure.

---

## 4. Stage-by-stage design

### Stage 0 — Discovery

**Goal:** Find every repo in the org whose current runtime image is a candidate for distroless migration.

**Mechanism — all deterministic, no LLM:**
1. **GitHub/GitLab API scan** (scheduled cron, nightly or weekly). List active repos matching org filters.
2. For each repo: shallow `git clone`, detect if a `Dockerfile` or `dockerfile` or `**/Dockerfile.*` exists. Use `rewrite-docker`'s `FindBaseImages` recipe or a simple parser to extract `FROM` lines.
3. **Eligibility rules** (configurable):
   - Final stage uses `node:*`, `python:*`, `*-slim`, `*-alpine`, or `*-debian*` (not already distroless).
   - Dockerfile exists and parses.
   - Repo's default branch has CI green in last N builds (skip broken repos).
   - Ideally: an SBOM scan via Syft shows CVE count above threshold (prioritization signal, not gate).
4. For each candidate, emit a `CandidateRepo` event with metadata: repo URL, base image, last-commit SHA, detected language (guess), CVE count.

**Output schema:**
```json
{
  "repo_url": "https://github.myorg/team/service",
  "commit_sha": "abc123...",
  "candidate_id": "2026-04-21-service-abc123",
  "detected_languages": ["node"],
  "current_base_image": "node:20-slim",
  "cve_count": { "critical": 3, "high": 12 },
  "discovered_at": "2026-04-21T02:00:00Z"
}
```

Each candidate becomes a Temporal workflow execution ID, which is how the pipeline state is tracked end-to-end.

### Stage 1 — Assessment (language-routed)

**Goal:** Route to the right assessor; produce category 1/2/3 with cited evidence.

**Mechanism — deterministic router + LLM classifier:**
1. **Language router (deterministic).** Use language detection (file extensions, package manifests) to pick the assessor.
2. **Per-language assessor agent**, each with its own prompt and knowledge graph subset:
   - `node-assessor` — reads Node signals, fingerprints, error signatures.
   - `python-assessor` — same, Python-scoped.
3. Assessor runs **deterministic signal scans first** (ripgrep/AST for `child_process`, `subprocess`, `ctypes`, native deps, runtime shell calls, writes outside `/tmp`), then reasons over the evidence using the knowledge graph from your previous spec.
4. Emits `AssessmentResult`:
   ```json
   {
     "category": 1 | 2 | 3,
     "confidence": "low|medium|high",
     "fingerprint": { ... },
     "signals_matched": [...],
     "blockers_found": [...],
     "evidence_bundle_url": "s3://...assessment.md"
   }
   ```

**Decision gate after Stage 1:**
- Cat 3 → write a blocker report, open a tracking issue (not a PR), end this repo's workflow.
- Cat 1 or Cat 2 → proceed to Stage 2.

The per-language routing is important: a single giant assessor trying to handle both Node and Python will be worse than two specialists with focused context. This matches the subagent pattern in awesome-copilot (e.g., `react19-auditor` as a "deep-scan specialist").

### Stage 2 — Deep scan / context packaging

**Goal:** Produce a structured, LLM-consumable representation of everything relevant for this repo's distroless migration. Deterministic. No LLM calls.

**Mechanism:**
1. **Tree-sitter AST pass** (per-file):
   - Top-level imports / requires.
   - Function and class definitions.
   - Call sites of interest (shell, subprocess, fs writes, dynamic load, native module loads).
   - Entry-point files (what the Dockerfile `CMD`/`ENTRYPOINT` invokes).
2. **Dockerfile parse** (via `rewrite-docker` or `dockerfile-ast` library):
   - All stages and their bases.
   - All `RUN`, `COPY`, `ENV`, `ARG`, `USER`, `EXPOSE`, `ENTRYPOINT`, `CMD`.
   - Runtime-install detection (apt/yum/apk/pip/npm in runtime stage).
3. **Dependency manifest extraction:**
   - Node: `package.json`, `package-lock.json` / `yarn.lock` / `pnpm-lock.yaml` / `bun.lockb`. Record package manager, module system, direct deps, native deps list.
   - Python: `pyproject.toml`, `poetry.lock`, `uv.lock`, `requirements.txt`. Record package manager, Python version, native-backed deps.
4. **CI/CD file scan:**
   - `.github/workflows/*`, `.gitlab-ci.yml`, Azure pipelines, etc. — find existing build/test commands so the validator can reuse them.
5. **Test discovery:**
   - Node: `jest.config*`, `vitest.config*`, `package.json` test script.
   - Python: `pytest.ini`, `pyproject.toml [tool.pytest]`, `tox.ini`.
6. **SBOM + CVE baseline:**
   - Build the current image; `syft` → SBOM; `grype` → CVE list.
   - This is the baseline to diff against post-migration.

**Output — the "context packet":**
```
context-packet.json
├── repo_metadata
├── fingerprint                     (same shape as tracker.json fingerprint)
├── dockerfile
│   ├── parsed_stages[]
│   └── issues[]                    (runtime installs, root user, etc.)
├── ast_summary
│   ├── entry_points[]
│   ├── shell_invocations[]
│   ├── subprocess_calls[]
│   ├── native_module_usage[]
│   ├── dynamic_loading_sites[]
│   └── fs_write_sites[]
├── dependencies
│   ├── direct[]
│   └── native[]
├── test_suite
│   ├── runner
│   └── invocation
├── cve_baseline
└── ci_context
```

This packet is what Stage 3 consumes. It's bounded-size regardless of repo size, so the planner's LLM context stays predictable.

### Stage 3 — Planning (recipe-first, LLM fallback)

**Goal:** Given the context packet, produce an ordered list of step files with red/green TDD assertions.

**Mechanism — the decision tree:**

```
for each required transformation (rewrite runtime stage, install deps, etc.):
  1. Does a deterministic recipe cover this?
     - OpenRewrite rewrite-docker recipe?
     - A ruleset-style transform from your own library?
     → If yes: emit a step that invokes the recipe. No LLM call.
  2. Does a solved-example match in the solution store?
     - Vector-search the solution store keyed by fingerprint + signal type.
     - If high-similarity match found: use the LLM with the solved example as few-shot.
  3. Otherwise: LLM-plan from scratch with the context packet + relevant graph nodes + step templates.
```

**Step file output** — same shape as your v2 spec's red/green TDD format, with every assertion invoking a verifier from `scripts/verifiers/` rather than raw bash.

**Additional outputs for autonomous execution:**
- `step-validation.json` per step — machine-readable assertions the executor can check without human judgment.
- `global-validation.json` — assertions for the whole migration that must pass at the end.
- `rollback-plan.json` — explicit rollback recipe if any step fails unrecoverably.

**Critical design decision here:** the planner does NOT execute. It plans. The separation is what makes Stage 4 pluggable (human or agent).

### Stage 4 — Execution (human OR autonomous)

**Goal:** Apply each step; validate each step; stop on unrecoverable failure.

Two executors, same contract:

**4a. Human executor.** Receives a PR (or a branch + issue) with:
- The plan files in `.distroless-migrate/steps/`.
- A `README.md` describing how to execute each step (essentially the v2 `/migrate-distro` command adapted for non-interactive use).
- Validators runnable locally via `./scripts/verifiers/...`.

Human executes step-by-step, pushes commits, marks the PR ready when done. The Temporal workflow waits for a PR-ready signal from a GitHub webhook.

**4b. Autonomous executor.** A Temporal activity that:
- Checks out the target repo.
- For each step file:
  - Runs the red-phase verifier; asserts pre-condition.
  - Applies the change (recipe invocation OR LLM-driven edit based on step instructions).
  - Runs the green-phase verifier; asserts post-condition.
  - On failure: invokes `error-triage` specialist; retries with adjusted approach up to N times.
- Commits progress atomically (one commit per step so history is reviewable).
- If all steps pass: pushes branch, opens PR, transitions workflow to Stage 5.
- If any step fails unrecoverably: marks workflow for human intervention, pauses.

**Both executors use the same verifier script library** from your v3 spec. This is what guarantees the autonomous path isn't making up its own assertions.

Phased rollout:
- **Phase 1 (start here):** Human executor only. The service discovers, assesses, scans, plans, and opens a draft PR with the plan. Humans execute.
- **Phase 2:** Autonomous executor for high-confidence Cat 1 with simple fingerprints (e.g., `python-fastapi-poetry-wheels` with no native deps, no shell, no FS writes). Everything else stays human.
- **Phase 3:** Expand autonomous coverage as solved-examples accumulate and error-triage becomes more capable.

### Stage 5 — Validation

**Goal:** Prove the migrated image is correct and better than the original.

**Mechanism — all deterministic, scored by an LLM adjudicator only on ambiguous failures:**
1. Image builds.
2. Container runs with the app's normal entrypoint.
3. Existing test suite passes inside the new image (or against the running container for integration tests).
4. Prove-It: no shell, no package manager, expected user is non-root, required labels present.
5. **CVE delta:** compare Stage 2 baseline CVE count vs new image. Expected direction: down, often dramatically. If CVE count is higher, flag for review.
6. **Behavior diff:** for services with health endpoints or known-good fixtures, replay requests against old vs new and diff responses.

**Failure handling:**
- Hard failures (no build, no run, test failures) → workflow pauses, human is notified.
- Soft concerns (CVE count flat, missing a label) → PR is opened anyway with notes.

### Stage 6 — Handoff

**Goal:** Get the change in front of the right humans with enough context to approve.

**Mechanism:**
1. Open a PR against the target repo from a branch named `distroless-migration/<run-id>`.
2. PR body includes:
   - Migration summary: fingerprint, category, base image chosen.
   - Step-by-step changelog.
   - CVE delta table.
   - Validator evidence bundle (build log, test output, Prove-It output).
   - Links to the solved examples used.
   - A ready-to-run local verification command.
3. Request review from CODEOWNERS.
4. **Merge is never automatic.** This is the hard rule from the Copilot research: autonomous merge of AI-written code into production is how incidents happen. The pipeline plans and proposes; humans approve and merge.
5. Workflow waits on a GitHub webhook signal for `pull_request.closed` with `merged: true`.

### Stage 7 — Learning

**Goal:** Make the next migration better.

**Mechanism:**
1. On successful merge, extract:
   - The diff applied (per-step commits).
   - The fingerprint.
   - The signals matched.
   - The solved examples used (if any) and whether they needed adaptation.
   - Any error-triage events and their resolutions.
2. Write this to the **solution store** (Kai-style, MCP-backed vector DB) so future Stage-3 planners retrieve it.
3. Write an entry to `graph/log.md` in the central kit repo.
4. If novel signals / errors / fingerprints were involved: open a PR against the central kit with the proposed graph additions (v2 retro pattern).
5. Emit telemetry: migration duration, stage timings, human-intervention count, CVE delta.

---

## 5. Architecture diagram

```
                ┌──────────────────────────┐
                │ Scheduler (cron)         │
                │ nightly discovery scan   │
                └────────────┬─────────────┘
                             ▼
          ┌──────────────────────────────────┐
          │ STAGE 0: Discovery               │
          │  - list repos                    │
          │  - parse Dockerfiles             │
          │  - syft/grype baseline           │
          │  - emit CandidateRepo events     │
          └────────────┬─────────────────────┘
                       ▼
        ┌──────────────────────────────┐
        │ Temporal: spawn workflow     │
        │ per candidate                │
        └────────────┬─────────────────┘
                     ▼
    ┌────────────────────────────────────────┐
    │ STAGE 1: Assessment                    │
    │   language router                      │
    │   → node-assessor │ python-assessor    │
    │   → Cat 1/2/3                          │
    └───────┬───────────────┬────────────────┘
     Cat 3  │               │ Cat 1/2
            ▼               ▼
     ┌──────────┐   ┌──────────────────────────────┐
     │ blocker  │   │ STAGE 2: Deep Scan           │
     │ report + │   │  - tree-sitter AST           │
     │ tracking │   │  - Dockerfile parse          │
     │ issue    │   │  - dep manifest              │
     │ END      │   │  - CI/test discovery         │
     └──────────┘   │  - CVE baseline              │
                    │  → context-packet.json       │
                    └──────────┬───────────────────┘
                               ▼
                    ┌──────────────────────────────┐
                    │ STAGE 3: Planning            │
                    │  - try deterministic recipe  │
                    │  - try solved-example RAG    │
                    │  - fallback: LLM from graph  │
                    │  → step files + validators   │
                    └──────────┬───────────────────┘
                               ▼
                    ┌──────────────────────────────┐
                    │ STAGE 4: Execution           │
                    │  (human OR autonomous)       │
                    │  - per-step red/green        │
                    │  - resumable via Temporal    │
                    └──────────┬───────────────────┘
                               ▼
                    ┌──────────────────────────────┐
                    │ STAGE 5: Validation          │
                    │  - build + run + tests       │
                    │  - Prove-It                  │
                    │  - CVE delta                 │
                    │  - behavior diff             │
                    └──────────┬───────────────────┘
                               ▼
                    ┌──────────────────────────────┐
                    │ STAGE 6: Handoff             │
                    │  - PR opened                 │
                    │  - CODEOWNERS review         │
                    │  - WAIT (durable signal)     │
                    └──────────┬───────────────────┘
                       merged  │
                               ▼
                    ┌──────────────────────────────┐
                    │ STAGE 7: Learning            │
                    │  - store solved example      │
                    │  - update graph log          │
                    │  - propose graph updates     │
                    │  - emit telemetry            │
                    └──────────────────────────────┘
```

---

## 6. Deployment shape

### Service components

```
distroless-migration-service/
├── orchestrator/                # Temporal workflows + activities (Python or TS)
│   ├── workflows/
│   │   └── migrate_repo_workflow.py    # the big per-repo workflow
│   ├── activities/
│   │   ├── discovery.py
│   │   ├── assess.py
│   │   ├── deep_scan.py
│   │   ├── plan.py
│   │   ├── execute.py
│   │   ├── validate.py
│   │   ├── handoff.py
│   │   └── learn.py
│   └── worker.py                 # Temporal worker
├── analyzers/                    # deterministic analysis tools
│   ├── dockerfile_parser/
│   ├── tree_sitter_scan/         # wrapper over tree-sitter for Node+Python
│   ├── dep_extractors/
│   └── sbom_runners/             # syft/grype drivers
├── recipes/                      # deterministic transforms
│   ├── openrewrite/              # wrapper that invokes rewrite-docker
│   └── rulesets/                 # YAML rules (Konveyor style) specific to distroless
├── solution_store/               # MCP-backed solved-examples DB
│   ├── mcp_server/               # MCP interface for solved-example retrieval
│   └── storage/                  # vector DB (e.g., Qdrant or pgvector)
├── graph/                        # the markdown knowledge graph from your v2 spec
├── prompts/                      # LLM prompts (shared with CLI kit)
├── scripts/                      # verifier library (shared with CLI kit)
├── knowledge_base/               # CVE DB sync, base-image catalog, company conventions
└── infra/
    ├── k8s/                      # deployment manifests
    └── helm/
```

### Why Temporal specifically

The alternatives (Airflow, Step Functions, home-grown) all fall over on at least one of these:
- **Long pauses.** Human review can take days; Airflow is batch-oriented and doesn't suspend cleanly.
- **State durability.** If the orchestrator restarts, a home-grown system has to rebuild state from a DB; Temporal rehydrates workflows transparently.
- **Retries with backoff.** LLM calls fail transiently; Temporal's retry policies handle this without bespoke code.
- **Signals.** Human "approve" or "reject" decisions arrive minutes to weeks after the workflow was paused; signals are first-class.
- **Language choice.** Your team can write workflows in Python or TS, not a proprietary DSL.

OpenAI's Codex and Replit's coding agent both run on Temporal. This is the boring correct answer.

### Scale and cost

A single Temporal worker can easily handle hundreds of in-flight workflows (most time is spent waiting for humans or LLM responses, not compute). For thousands of repos, horizontal scaling is trivial — more workers pulling from the same task queue.

Per-repo cost is dominated by LLM calls in Stage 3. The recipe-first / solved-example-first strategy is not just for quality; it's for cost. A well-built ruleset catalog reduces per-repo LLM spend by an order of magnitude.

---

## 7. Interfaces (what other teams see)

### 7.1 Registration / opt-in

Teams opt in by adding their repo to an allowlist (or the org enables universal scanning). Either way, teams see:

- **A dashboard** showing: repos scanned, candidates identified, in-flight migrations by stage, recent PRs opened.
- **Automatic PR notifications** when a plan is ready for their repo (draft PR) or when a migration's execution-stage PR is ready for review.
- **A "pause" control** per repo — stop the pipeline on this repo.

### 7.2 Human executor workflow

For Phase 1 (human execution):
1. Pipeline posts a "draft migration plan" PR to the team's repo.
2. Team's designated engineer runs `distro-migrator --from-plan` locally (this command reads the plan the pipeline wrote) or follows the plan manually.
3. Each step's verifier is runnable: `./scripts/verifiers/common/assert-no-shell.sh test-image`.
4. When all steps done and validated locally, engineer marks PR ready.
5. Webhook signals Temporal; pipeline moves to Stage 5 validation.

### 7.3 Autonomous executor workflow

For Phase 2+ (autonomous execution on eligible fingerprints):
1. Pipeline posts a "migration executed by pipeline" PR directly, already at the validation stage.
2. Team reviews as normal code review — they see the diff, the validator evidence bundle, and the CVE delta.
3. Merge is human; the pipeline does not merge.

Having both paths share the same output artifact (a PR with evidence) means teams don't care whether execution was human or autonomous. The review surface is the same.

---

## 8. Knowledge base — what changes from the CLI-kit spec

The knowledge graph from v2 stays as-is: markdown vault, derived JSON index, node types for signals / categories / resolutions / blockers / base-images / patterns / errors / fingerprints / company-conventions / step-templates. That vault is the same source of truth.

What the service adds on top:

1. **Solution store (Kai-pattern).** A vector DB of prior successful migration diffs keyed by (fingerprint, signal-set). Populated by Stage 7 after every successful migration. Retrieved by Stage 3 planner as few-shot examples. This is **learned knowledge**, distinct from **curated knowledge** (the graph).
2. **Ruleset catalog.** YAML rules (Konveyor style) that map specific AST patterns or Dockerfile patterns to specific transformations. Deterministic. Shipped alongside the graph.
3. **CVE baseline history.** For telemetry: CVE count before/after per migration, per base image.

The graph is what humans author. The solution store is what the system accumulates. The ruleset catalog is the deterministic bridge between them.

---

## 9. Self-improvement in a service model

Your v2/v3 CLI kit had self-improvement via user-attributed PRs triggered by retros. The service model needs a different shape because the "user" is often the pipeline itself.

**Three improvement feedback loops, all running:**

- **Retro PR loop (unchanged).** When a migration surfaces a new signal / error / fingerprint, a retro activity opens a PR against the central kit. Reviewed by platform team.
- **Solution-store auto-fill.** Every successful migration's diff is automatically stored, no PR required. Only retrievals feed back into LLM prompts.
- **Feedback-on-failure loop.** When a validation fails and gets human-fixed in the PR, the pipeline diffs the human's fix against its own proposed change and writes that as a "correction example" in the solution store. The LLM planner learns from corrections, not just successes.

This is where the Konveyor AI pattern shows its real value: the system gets better as it runs, without retraining.

---

## 10. Risks and how to mitigate

| Risk | Mitigation |
|---|---|
| Autonomous executor produces a plausible-but-broken migration | Phase rollout; start human-executor only; autonomous only for high-confidence fingerprints; merge always human |
| LLM cost balloons at portfolio scale | Recipe-first planning; solved-example cache; cost ceilings per workflow |
| Portfolio scan generates noise (hundreds of low-value migrations) | Prioritize by CVE delta; staged rollout (10 repos, 100 repos, org-wide); teams can opt out |
| Pipeline gets out of sync with kit updates | Workflows pin kit version at start; mid-flight kit upgrades require explicit re-plan |
| A team's CI is broken → Stage 5 always fails for them | Stage 0 eligibility checks exclude repos with broken CI; explicit "fix CI first" path |
| Sensitive code leaves dev machines / compliance | Tree-sitter is fully local; LLM calls go to approved models; evidence bundles are stored in internal buckets; Temporal runs in your infra |
| Auth model for autonomous executor | Use a dedicated bot account with narrow scope; branch protection on target repos; cannot bypass review |

---

## 11. What to build first (service rollout plan)

### Month 1 — Pipeline skeleton, Phase 1 rollout
- Temporal cluster (self-hosted or Temporal Cloud).
- Stage 0 discovery activity: scans 1 team's repos nightly.
- Stage 1 language router + Node assessor only (Python next month).
- Stage 2 tree-sitter scanner for Node.
- Stage 3 planner: recipe-first (rewrite-docker for base-image swap + OCI labels + non-root user), LLM-fallback for everything else.
- Stage 4 human executor path only.
- Stage 5 validators (reuse the v3 verifier library).
- Stage 6 PR opener.
- One pilot team, 5–10 repos.

### Month 2 — Second language, solution store
- Python assessor + tree-sitter scanner.
- MCP solution-store server; start capturing solved examples from Month 1 migrations.
- Stage 7 learning activity.
- Expand to 2–3 teams.

### Month 3 — Autonomous executor (narrow scope)
- Autonomous Stage 4 for the two highest-confidence fingerprints (e.g., `python-fastapi-poetry-wheels-only`, `node-express-npm-no-native`).
- Side-by-side comparison: human vs autonomous plan on same repo; measure agreement.
- Expand based on results.

### Month 4–6 — Breadth
- More fingerprints into autonomous path.
- Ruleset catalog grows.
- Full org scan; prioritization by CVE delta.
- Dashboard + metrics.

### Beyond
- The Kai pattern: as solution store grows, LLM prompts use increasingly org-specific examples; quality and cost improve together.

---

## 12. TL;DR

You're building a **multi-stage agentic migration pipeline with static-analysis-grounded RAG and durable-execution orchestration**. The closest published analog is [Konveyor AI (Kai)](https://github.com/konveyor/kai), adapted for distroless instead of framework upgrades and for Node+Python instead of Java.

Use **Temporal** as the orchestrator (this is what OpenAI Codex and Replit's coding agent run on). Use **tree-sitter** for the deep AST scan. Use **OpenRewrite's rewrite-docker** for deterministic transforms (FROM swaps, label additions, non-root user, apt cleanup). Use **Syft + Grype** for SBOM + CVE baselining. Use an **MCP-backed solution store** (Kai's pattern) as the vector DB of prior successful migrations, queried by the planner as few-shot examples.

The pipeline has seven stages — discovery, assessment, deep scan, planning, execution, validation, handoff, learning. Planning is **recipe-first, solved-example-second, LLM-last** for both cost and correctness. Execution is **pluggable**: human executor in Phase 1, autonomous executor for narrow fingerprints in Phase 2. **Merge is always human.** This is the consistent finding across all the published autonomous-migration research: agents can plan and propose reliably; merging is where incidents happen.

The knowledge graph from your CLI-kit design stays as the curated knowledge substrate; the solution store accumulates learned examples automatically. Start with one team and one language, phase through autonomous execution narrowly, and let the solution store fill up before expanding.