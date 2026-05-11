# codewizard-sherpa — Production Design

*The authoritative production-target reference. Synthesizes [auto-agent-design.md](auto-agent-design.md), [gemini-auto-agent-design.md](gemini-auto-agent-design.md), and [context.md](context.md) into one canonical architecture. The local POC ([localv2.md](localv2.md)) implements the inner gather layer and lifts unchanged into this service.*

---

## 1. Executive summary

**codewizard-sherpa is an autonomous agentic system that opens pull requests to modify code across an organization's repositories at portfolio scale.** Phase 1 target: migrate Node.js services to Chainguard distroless containers. Phase 2+: vulnerability remediation and major language/dependency upgrades. The pipeline discovers candidate repos, assesses them, gathers structured context, plans changes recipe-first and LLM-last, executes them in sandboxed isolation, validates them against objective signals, and proposes them as human-reviewed PRs. **Merge is always human.**

The headline architectural shape is a **Temporal-durable workflow envelope** wrapping a **Layered Hybrid Orchestrator** with **structured-data-driven domain knowledge** feeding it:

```mermaid
flowchart TB
    subgraph TEMP["⏱  TEMPORAL — Durable workflow envelope (hours to days)"]
      direction TB
      subgraph PLAN["🧭 HIERARCHICAL PLANNER (Layer 1) — LangGraph Supervisor: reads intent, dispatches"]
        direction TB
        subgraph SUB["🛤  SHERPA-STYLE SUBGRAPH (Layer 2) — Pydantic state ledger; nodes never call nodes"]
          direction TB
          subgraph GATE["🛡  TRUST-AWARE GATES (Layer 3) — conditional_edge between every node; microVM sandbox; interrupt() on low trust"]
            direction TB
            LLM["💬 Leaf LLM calls<br/>via Agents SDK"]
          end
        end
      end
    end

    DATA["📚 Structured data feeds — MCP-served<br/>Skills · conventions · policies · exceptions · ADRs · solved examples"]
    DATA -. injects context .-> PLAN
    DATA -. injects context .-> SUB
    DATA -. injects context .-> GATE
```

The three inner layers are not alternatives to each other. They compose: a Supervisor dispatches into a SHERPA-disciplined subgraph whose every transition passes through a Trust-Aware guard. **LangGraph is the runtime engine; SHERPA is the architectural discipline; Trust-Aware is the safety layer.** Temporal wraps everything with the durable-execution properties needed for workflows that span hours of LLM work and days of human review.

---

## 2. Load-bearing architectural commitments

These constrain every decision below. A proposed change to any subsystem that violates one of these requires explicit justification and a corresponding update to this section.

1. **No LLM in the gather pipeline.** Anywhere. Probes are deterministic; same inputs always produce same outputs. This is what makes the `RepoContext` artifact reproducible, cacheable, and auditable.
2. **Facts, not judgments.** The gatherer captures evidence ("trace observed 0 shell invocations"). It does not write conclusions ("safe to migrate"). Conclusions are the Planner's job. Evidence is reusable across tasks; judgments are not.
3. **Honest confidence.** Every probe and every state node reports confidence and provenance. Silent staleness is the worst failure mode. `IndexHealthProbe` is the canonical example in the POC; objective-signal trust scoring is its analog in the service.
4. **Determinism over probabilism for structural changes.** AI agents are "safer builders, risky maintainers" — the empirical evidence in [gemini-auto-agent-design.md §"Empirical Realities"](gemini-auto-agent-design.md) shows agentic PRs introduce breaking changes during refactors and chores at 6.72–9.35% versus 2.69–2.89% for net-new features. Use recipes (OpenRewrite, rulesets) and AST/LST manipulation for structural transforms; reserve the LLM for judgment calls.
5. **Extension by addition.** Adding a new language, new task type, or new tool must be new probes + new Skills + new subgraphs, never edits to existing ones. The probe contract in [localv2.md §4](localv2.md) is the contract.
6. **Organizational uniqueness as data, not prompts.** Skills with YAML frontmatter, conventions catalogs, policy YAML, exception registries. The agent queries structured data; it never infers your company's rules from prose.
7. **Progressive disclosure.** The `RepoContext` artifact indexes evidence; it does not inline it. Skills, ADRs, repo notes, and external docs are referenced by manifest only. The agent reads originals at decision time via MCP. This is what keeps agent token budgets tractable.
8. **Humans always merge.** Autonomy ends at PR creation. This is the consistent finding from every published autonomous-migration study.

---

## 3. The 7-stage pipeline

Synthesized from [auto-agent-design.md §4](auto-agent-design.md) and refined against [gemini-auto-agent-design.md](gemini-auto-agent-design.md). Each stage is a Temporal Activity (or child workflow); collectively they form the per-repo migration workflow.

**Stage 0 — Discovery.** Scheduled scan of the org's repos. Lists candidates whose current image is a distroless candidate (or whose CVEs cross an action threshold). **Fully deterministic; no LLM.** Inputs: GitHub/GitLab API. Outputs: a `CandidateRepo` event per eligible repo, each spawning a Temporal workflow.

**Stage 1 — Assessment.** Per-language router classifies the candidate as Category 1 (clean migration), 2 (migration with caveats), or 3 (blocker — cannot proceed). **Hierarchical Planner routes; LLM used inside each language-specific assessor subgraph.** Inputs: `CandidateRepo`. Outputs: `AssessmentResult` with category, confidence, blockers found, evidence bundle.

**Stage 2 — Deep Scan.** The gather layer from [localv2.md](localv2.md) runs in service mode against the candidate. Produces the structured `RepoContext` artifact and the human-facing `CONTEXT_REPORT.md`. **Fully deterministic; no LLM.** Inputs: cloned repo, task type. Outputs: `RepoContext` resource served via MCP for downstream stages.

**Stage 3 — Planning.** Given `RepoContext`, emit an ordered list of step files with red/green TDD assertions plus a validation plan. **SHERPA subgraph: recipe-match → solved-example-RAG → LLM-fallback → emit-steps.** Recipes (OpenRewrite, internal rulesets) are tried first. Solved-example RAG queries the knowledge graph next. Only if both miss does the LLM plan from scratch with the context packet as few-shot. LLM appears at one node only, gated by Trust-Aware.

**Stage 4 — Execution.** Apply each step; validate each step. Two executor variants share the same step file contract: a **human executor** (PR opened with plan, engineer executes locally) and an **autonomous executor** (SHERPA subgraph: red-phase → apply-change → green-phase → commit). Autonomous-mode LLM appears at apply-change only; Trust-Aware gates fire after every step. Phased rollout: Phase 1 = human-only; Phase 2 = autonomous on narrow high-confidence fingerprints; Phase 3 = broader autonomous.

**Stage 5 — Validation.** Prove the migrated image is correct and better than the original. **Trust-Aware gate runs in a microVM sandbox: image builds, container runs, test suite passes, CVE delta is non-positive, Prove-It assertions pass (no shell, no package manager, expected user is non-root).** Deterministic evaluation. LLM appears only for failure adjudication when objective signals disagree (rare; e.g., one CVE scanner finds an issue another doesn't).

**Stage 6 — Handoff.** Open a PR with full evidence: migration summary, step-by-step changelog, CVE delta table, validator evidence bundle, solved-example references, local re-verification command. Request review from CODEOWNERS. Temporal pauses on a `pull_request.closed` webhook signal. **No LLM.**

**Stage 7 — Learning.** On successful merge, extract the diff, fingerprint, signals matched, and any error-triage events. Write to the solution store (vector DB) for future Stage-3 retrieval. Emit telemetry. Open a PR against the central kit if novel patterns surfaced. **No LLM.**

---

## 4. Orchestration — the Layered Hybrid

This is the deep chapter. Every architectural choice in this section is the load-bearing one; everything else flows from here.

### 4.1 The three layers and the outer envelope

#### Outer envelope: Temporal

Temporal owns the per-repo workflow. Why Temporal specifically:

- **Durable execution.** Workflow state rehydrates on worker restart. If Stage 4 crashes mid-migration, the next worker resumes at that exact step with all prior state intact.
- **Signals as first-class.** A `pull_request.closed` webhook arriving 72 hours after Stage 6 paused is a normal signal, not a special case.
- **Workflow-as-code in Python**, not YAML DAGs or a proprietary DSL.
- **Retry policies for free.** LLM transient failures and CI flakes are handled by Temporal's retry semantics, not bespoke code.
- **Production precedent.** OpenAI's Codex and Replit's coding agent both run on Temporal per [auto-agent-design.md §2.3](auto-agent-design.md).

The alternatives — Airflow (batch-oriented, can't suspend for days cleanly), Step Functions (AWS-locked, no in-language workflow code), Dagster (asset-pipeline-shaped, awkward for branching stage workflows), Prefect (smaller ecosystem, weaker durability), Argo Workflows (rigid YAML DAGs), home-rolled (~70% of Temporal poorly) — each fail on at least one load-bearing property.

#### Layer 1: Hierarchical Planner (the LangGraph Supervisor)

At the top sits a master `StateGraph` with a Supervisor node. Its only job is to read intent, map scope, and dispatch.

- **For a vulnerability task** ("Fix CVE-2026-145 in auth-service"): the Supervisor recognizes a high-risk targeted patch, isolates the specific repository, and spawns a single specialized worker agent on a short restrictive subgraph.
- **For a migration task** ("Migrate every Node service to distroless"): the Supervisor acts as a project manager. It maps cross-service dependencies via the gather layer, determines the order of operations, and spawns N worker agents in parallel — each on its own subgraph, each handling one repo.

Mechanically: the Supervisor analyzes the request and updates the shared state with a routing decision. It does not execute work. A `conditional_edge` reads the routing decision and drops the payload into the appropriate **subgraph** (Vulnerability Subgraph, Migration Subgraph, future task subgraphs). This keeps the codebases for different workflows entirely isolated — adding a new task type means adding a new subgraph, never editing existing ones.

The Supervisor implementation can be pure routing (deterministic intent classification + lookup) or LLM-driven. For Phase 1, pure routing likely suffices; see §7.

#### Layer 2: SHERPA-style State Machine (the worker subgraphs)

Each worker is dropped onto a strictly typed `StateGraph` backed by a Pydantic state model. The state ledger is the agent's entire memory; the LLM cannot escape it.

**The discipline (from arXiv 2509.00272):**

- **Nodes never call other nodes.** Each node reads state, mutates state, returns. It has no idea what runs next.
- **State as the contract.** The transition to the next step is handled entirely by the graph's structure. LangGraph inspects state after each node returns; if the state now contains the artifact the next node expects, the graph activates that next node.
- **Hierarchical decomposition.** Subgraphs nest. A Migration Subgraph contains a Dependency-Resolution Subgraph; failures at the inner level surface as state updates at the outer level.
- **Domain best-practices encoded as graph topology.** The Chainguard Guardener loop (parse → translate → dev-variant scaffolding → build → compare → iterate → validate, per [gemini-auto-agent-design.md §"AI-Assisted Iterative Migration"](gemini-auto-agent-design.md)) becomes the literal node sequence in the Migration Subgraph. The expert-encoded best practice is not a prompt; it is the graph.

This prevents the agent from hallucinating off-topic actions because it physically cannot execute anything outside of its current node. It cannot "decide to also push to main" or "decide to skip the test suite" — neither action exists in its graph.

Example Migration Subgraph topology:

```
Extract_Dependencies → Resolve_Conflicts → Rewrite_Manifests → Rewrite_Dockerfile
                                                                       │
                                                                       ▼
                              Open_PR ◄── Run_Smoke_Tests ◄── Build_Sandbox
                                              │
                                              └── (Trust-Aware gates between every arrow)
```

#### Layer 3: Trust-Aware Verification (the conditional edges)

Between every node is a `conditional_edge` that acts as a gate. The agent does not flow directly from one node to the next; it flows through a guard that evaluates objective signals.

The guard's logic:

- **Run sandbox checks.** Push the agent's output into a tightly permissioned microVM. For a Dockerfile rewrite: `docker build`, verify the image starts, run the smoke test, capture a runtime trace, diff against the pre-migration baseline. For a vulnerability patch: SAST + DAST + the targeted CVE test suite.
- **Compute the trust score from objective signals only** (see §4.6 for why self-reported LLM confidence cannot feed this).
- **If the build/test failed:** route the workflow back to the previous node with the sandbox error log attached to state. The agent retries with new context. Per-node retry limit defaults to 3; on exhaustion the subgraph gracefully halts and logs failure to the knowledge graph.
- **If checks passed but trust is low and the change is sensitive:** trigger LangGraph's `interrupt()`. This pauses the entire graph mid-execution, saves state via the checkpointer, and waits for a human engineer to review before continuing.
- **If trust is high and checks passed:** route to the next node.

The Trust-Aware layer is also the natural integration point for the **deterministic policy engine** pattern (Agent RuleZ, per [gemini-auto-agent-design.md §"Deterministic Policy Engines"](gemini-auto-agent-design.md)). Every state transition is a hookable event; policy rules can block, allow, or inject context with sub-10ms latency before the transition fires.

### 4.2 LangGraph as the physical engine; SHERPA as the blueprint discipline

These are not alternatives — they compose. The framing matters because LangGraph implementations elsewhere routinely violate SHERPA discipline (nodes call other nodes, agents are given freedom to choose paths outside the state contract, state is unstructured dicts) and lose most of the determinism benefits.

| Concern | What LangGraph provides | What SHERPA discipline adds |
|---|---|---|
| State management | `StateGraph` API with reducers | **Pydantic-typed state model; no untyped state allowed** |
| Node-to-node flow | Allows direct node calls; discourages but permits | **Forbidden. Nodes mutate state and return; only edges transition** |
| Branching | `conditional_edge` and dynamic edges | **Branches reflect domain best-practices, not ad-hoc agent choice** |
| Hierarchical composition | Subgraphs | **Subgraphs are first-class architectural primitives, used aggressively** |
| Human-in-the-loop | `interrupt()` + checkpointer | **Used at every low-trust transition, not only at end-of-flow** |
| Agent freedom | Up to the implementor | **Constrained to the leaf LLM call inside a node; no orchestration freedom** |

A LangGraph implementation that adheres to SHERPA discipline is what we mean by "the Layered Hybrid." A LangGraph implementation that doesn't is just "LangGraph alone" and loses on most of the rows below.

### 4.3 Comparison matrix

The five options compared. The chosen column is the rightmost; the four to its left are each rejected on specific grounds traceable to the commitments in §2.

| Criterion | LangGraph alone | CrewAI alone | Agents SDK alone | Hand-rolled HSM | **Layered Hybrid** ✓ |
|---|---|---|---|---|---|
| **1. Determinism / replayability** | Partial — ad-hoc node calls erode replay | Weak — emergent role-based coordination is non-deterministic | Weak — minimal tool-loop with no path constraints | Strong if disciplined | **Strong** — state-as-contract guarantees same inputs same path |
| **2. Hierarchical decomposition** | Subgraphs exist but rarely used | None — flat role list | None | Yes by definition | **Yes — first-class subgraph nesting** |
| **3. Domain best-practices as structure** | Possible but not enforced | Encoded as prompts, not structure | Encoded as prompts | Yes by design | **Yes — graph topology = best practices (per SHERPA paper)** |
| **4. Human-in-the-loop suspension** | `interrupt()` + checkpointer | Limited; not the design center | Not in the framework | Build it yourself | **`interrupt()` at every low-trust transition** |
| **5. Debuggability of agent decisions** | State-history visible; node calls confuse the trace | Hard — emergent multi-agent chatter | Tool-call log only, no state ledger | Whatever you build | **State diff per transition + sandbox evidence + gate verdict** |
| **6. Audit trail / governance** | Available via callbacks | Weak | Limited to tool-call traces | Build it yourself | **Every transition logged with state, signal, gate result** |
| **7. Compatibility with deterministic policy hooks** | Edges are hookable | No clean integration surface | None | Yes by definition | **`conditional_edge` is the natural Agent RuleZ hook point** |
| **8. Token-budget predictability** | Up to implementor — risk of loops | Higher — multi-agent debate burns tokens | Lower per call but no orchestration cap | Yes if disciplined | **Per-node retry cap (3); graceful halt; supervisor short-circuit** |
| **9. Framework / vendor lock-in** | LangChain ecosystem coupling | CrewAI-specific abstractions | Per-vendor SDK | None | **LangGraph for runtime; SDK for leaf calls only — both replaceable at boundaries** |
| **10. Maturity / production usage 2026** | Strong — used by serious agent shops | Strong for prototypes; less for production | Both Anthropic and OpenAI SDKs production-grade | Variable | **Strong substrate + emerging pattern (Sherpa paper recent)** |
| **11. Compatibility with Temporal** | Works as Activity payload | Works but awkward | Works as Activity | Works | **Works — LangGraph subgraph executes inside a Temporal Activity** |
| **12. Constrains agents during maintenance** (per "Safer Builders" finding) | Partially — depends on graph rigor | No — agents free to "collaborate" off-path | No — minimal constraints | Yes if rigorous | **Yes — agents physically cannot leave the state contract** |

The Layered Hybrid wins on rows 1, 2, 3, 5, 6, 7, 8, 9, 12 and ties on the rest. No alternative wins more rows than it.

### 4.4 How each layer maps to the 7-stage pipeline

| Pipeline stage | Layer that owns it | Implementation notes |
|---|---|---|
| 0. Discovery | Temporal scheduled workflow + deterministic Activities | No LLM. |
| 1. Assessment | Hierarchical Planner routes to language-specific assessor subgraph | LLM at the routing decision and inside the assessor subgraph. |
| 2. Deep Scan | Deterministic Activity (the `localv2.md` probe pipeline) | No LLM. |
| 3. Planning | SHERPA subgraph: `recipe_match` → `solved_example_rag` → `llm_fallback` → `emit_steps` | LLM at `llm_fallback` only; gated by Trust-Aware. |
| 4. Execution (autonomous) | SHERPA subgraph: `red_phase` → `apply_change` → `green_phase` → `commit` | LLM at `apply_change`; Trust-Aware gate after `green_phase`. |
| 5. Validation | Trust-Aware gate (microVM sandbox: build, test, SAST, CVE delta) | No LLM in evaluation; LLM only for failure adjudication. |
| 6. Handoff | Temporal signal wait on GitHub webhook | No LLM. |
| 7. Learning | Deterministic Activity writes solved examples to the knowledge graph | No LLM. |

Notice the LLM appears at only three nodes across the entire pipeline. Everything else is deterministic. This is the load-bearing commitment from §2.4 ("determinism over probabilism for structural changes") rendered as architecture.

### 4.5 Concrete worked examples

#### Scenario A: Application-layer vulnerability

**Trigger:** "Fix CVE-2026-145 in auth-service" (a high-severity finding from the org's CVE scan).

**Layer 1 — Hierarchical Planner:** Supervisor recognizes the task as a targeted security patch (single repo, narrow scope). Updates state with `routing.subgraph = "vulnerability"`. The `conditional_edge` dispatches into the Vulnerability Subgraph.

**Layer 2 — Vulnerability Subgraph (short, restrictive):**

```
Reproduce_CVE → Draft_Patch → Build_Sandbox → Run_Security_Suite → Open_PR
```

The agent receives the CVE description, the affected symbol from the `RepoContext` artifact, and the relevant Skill (e.g., `vuln-remediation-nodejs-prototype-pollution`). At `Draft_Patch`, the LLM proposes a fix. The state ledger now contains the patch diff.

**Layer 3 — Trust-Aware gates cranked to maximum:**

- After `Draft_Patch`: gate runs SAST against the patched file. If SAST fails or detects new findings, route back to `Draft_Patch` with the SAST output attached to state. Retry limit 3.
- After `Build_Sandbox`: gate verifies the image builds in a microVM. Build failure → back to `Draft_Patch` with build logs.
- After `Run_Security_Suite`: gate runs the targeted CVE test (proves the vulnerability is no longer exploitable) plus the full test suite. Any failure → back to `Draft_Patch`.
- On retry exhaustion: `interrupt()` fires, the workflow checkpoints, and a human engineer is paged.

**Result:** A PR with evidence (CVE reproduction artifact, patched file, SAST diff, sandbox test output) attached. Merge is human. If the agent failed after 3 attempts, no PR is opened — escalation only.

#### Scenario B: Org-wide migration

**Trigger:** Stage 0 nightly scan finds 50 Node services running outdated base images. CVE-delta prioritization ranks them.

**Layer 1 — Hierarchical Planner:** Supervisor sees a portfolio task. Queries the gather layer's cross-repo data to determine dependency order (shared libraries first, then leaf services). Spawns 50 worker workflows in parallel, each its own Temporal workflow, each entering the Migration Subgraph.

**Layer 2 — Migration Subgraph (longer, branching):** Per the Chainguard Guardener pattern encoded as graph topology:

```
Parse_Existing → Translate_Packages → Scaffold_Multi_Stage → Build_Dev_Variant
                                                                     │
                                                                     ▼
            Open_PR ◄── Compare_SBOM ◄── Build_Final ◄── Smoke_Test_Dev
                              │
                              └── (Trust-Aware gates between every arrow)
```

**Layer 3 — Trust-Aware gates plus the shared knowledge graph:**

- Standard gates per scenario A: build success, smoke test, SBOM diff non-positive on CVE count, no shell in final image, non-root user.
- **Cross-worker learning:** when Worker #45 hits a dependency conflict at `Translate_Packages` that Worker #2 resolved an hour ago, the Hierarchical Planner injects Worker #2's proven resolution into Worker #45's state before the LLM is consulted. Drastically reduces tokens and hallucination risk. This is the solution store from Stage 7 doing work mid-pipeline.

**Result:** Each of the 50 worker workflows independently produces a PR (or escalates on retry exhaustion). Failures in one worker do not crash the supervisor or sibling workers. The org wakes up to a dashboard of 50 PRs in various review states, each with full evidence.

### 4.6 Push-back: trust scores use objective signals only

The architecture as proposed includes a "trust score" gating low-trust transitions to human review. The user's initial framing referenced "internal confidence metrics" from the agent. **This design rejects that.** Trust score is computed from objective evidence only.

The reason is empirical, not philosophical. The Confidence Trap finding in [gemini-auto-agent-design.md §"Mitigating the Confidence Trap"](gemini-auto-agent-design.md) reports: agentic PRs at the highest self-reported confidence levels (8–10 out of 10) still introduce breaking changes at 3.16–3.96%. At confidence 10, the rate is 3.16% (458 breaks out of 14,509 commits). The correlation between LLM-reported confidence and code correctness during maintenance tasks **breaks down completely** — agents are overconfident in failure.

A gate keyed on self-reported confidence is therefore worse than no gate at all: it produces false reassurance proportional to risk.

The trust score this design uses is computed only from objective signals:

- Sandbox build status (binary)
- Test pass/fail counts and changes vs. baseline
- SAST/DAST findings, new vs. baseline
- CVE delta direction (more, same, or fewer)
- Runtime trace coverage (which scenarios completed cleanly)
- Policy-engine block events (any deterministic rule fired?)
- Coverage of changed code by existing tests

LLM self-reported confidence may be **logged** for observability and drift analysis. It does not feed the gate.

The specific gate threshold (initially proposed as T_conf ≤ 0.90) is deferred to §7 pending empirical calibration on the first 50 production migrations. Until then, gates use binary pass/fail on sandbox checks: all objective signals must pass, or the transition is blocked.

### 4.7 Why each alternative loses

**LangGraph alone (without SHERPA discipline).** Loses on rows 1, 3, 5, 12 of the matrix. The framework permits ad-hoc node-to-node calls, untyped state dicts, and unconstrained agent paths. Without the discipline of state-as-contract, the determinism we need for structural changes (commitment §2.4) erodes. Implementations elsewhere routinely allow agents to "collaborate" across nodes — exactly the failure mode the Safer Builders paper warns against.

**CrewAI alone.** Loses on rows 1, 2, 3, 5, 6, 7, 12. Role-based emergent coordination is the architectural opposite of state-as-contract. Agents debate, hand off, and improvise — useful for prototyping, catastrophic for high-stakes maintenance where agents fail at 9.35% during chore tasks. Violates commitments §2.2, §2.3, §2.4 simultaneously.

**Agents SDK alone (Anthropic or OpenAI).** Loses on rows 2, 3, 4, 6, 7, 8, 12. Minimal tool-use loops have no orchestration primitives at all. You would end up building LangGraph by hand, badly. The right place for an Agents SDK is at the leaf LLM call inside a node — and the chosen Layered Hybrid uses it there.

**Hand-rolled SHERPA-style HSM (no LangGraph runtime).** Loses on rows 9, 10, 11. Technically possible but reinvents checkpointing, interrupts, persistence, state-history visualization, and runtime tooling that LangGraph already supplies. The benefit (zero framework dependency) is paid for by years of edge-case debugging. Reject on §2.5 grounds — extension by addition presumes a stable runtime substrate.

---

## 5. AgentOps and the Trust-Aware layer

The Trust-Aware layer is where AgentOps lives architecturally. Most of what published AgentOps writeups treat as a separate concern is, in this design, the natural job of the gate edges between SHERPA nodes.

### Sandboxed reality checks

Every code-modifying transition runs the agent's output inside a microVM before the transition is allowed.

- **For migrations:** `docker build` the new image; run the existing smoke test against the running container; capture a runtime trace; diff shared-library loads against the pre-migration baseline.
- **For vulnerability patches:** SAST against the patched files; DAST against the running service; targeted CVE test (proves the vuln is no longer exploitable); full unit + integration test suite.
- **For any structural change:** AST-equivalence checks (where applicable) and a behavioral diff against known-good fixtures.

Sandbox stack (Firecracker vs. gVisor vs. nested QEMU) is deferred to §7 — the choice depends on cold-start sensitivity and kernel-feature requirements for `strace` and eBPF.

### Trust score and gates

Score is computed per §4.6: objective signals only, LLM self-confidence excluded. Each task class (vulnerability vs. migration vs. language upgrade) gets its own gate threshold profile — security patches gate harder than convenience migrations. Failure of the gate routes back to the previous node with full error context attached to state. Sustained failure (retry limit 3) triggers `interrupt()` and escalates to human review.

### Checkpointer

LangGraph's checkpointer backs durable state across interrupts. `InMemorySaver` for development and tests; a Postgres or Redis backend for production. Backend choice deferred to §7 pending volume estimate.

### Retry limits

Per-node retry cap defaults to 3. On exhaustion the subgraph halts gracefully, logs the failure to the knowledge graph as a "negative example" (so future planning can avoid the same path), and the supervisor continues with other parallel workers. The supervisor itself does not crash; a single worker's failure is isolated.

### Shared knowledge graph

Cross-worker solution reuse, populated by Stage 7 Learning. When a worker hits a problem a sibling worker has already solved, the Hierarchical Planner injects the proven resolution into the worker's state before the LLM is consulted. Drastically reduces token spend and hallucination risk at portfolio scale. Backend choice (Qdrant vs. pgvector vs. Neo4j) deferred to §7 — depends on whether traversal queries are needed or similarity search suffices.

### Identity and tool governance

Each agent runs under a scoped least-privilege identity. Tools are exposed via MCP servers, not as raw shell access — the gather-layer MCP from [context.md](context.md) is the canonical example. The Trust-Aware layer can intercept and audit every tool call before it executes; a dedicated policy engine (Agent RuleZ pattern, per [gemini-auto-agent-design.md §"Deterministic Policy Engines"](gemini-auto-agent-design.md)) can block, allow, or inject context at sub-10ms latency.

### Observability

Reasoning traces, tool-call logs, state-transition history, and gate-evaluation events are all persisted to an audit store. Drift detection runs against task success rates per stage and per agent role — if Stage 3 Planning's recipe-match rate suddenly drops, the system surfaces the regression before quality cascades.

### Cost controls

Per-workflow token ceilings (hard cap; workflow halts and escalates if exceeded). Per-stage retry bounds. Orchestration timeouts on long-running activities. The Hierarchical Planner can short-circuit a workflow that's burning tokens without making state progress — i.e., the same state has appeared three times after retries, no advancement.

### Confidence calibration as a future concern

The "40-Point Rule" from [gemini-auto-agent-design.md](gemini-auto-agent-design.md) — halt and escalate when the gap between agent pattern-match confidence and information completeness exceeds 40 points — is interesting but contingent on having reliable confidence signals. Per §4.6, we do not yet. This is a Phase 3 concern, not a Phase 1 implementation requirement.

---

## 6. POC-to-service mapping

The POC ([localv2.md](localv2.md)) is not a throwaway. Its components lift unchanged into the service. This is the architectural promise of the probe contract.

| POC component (`localv2.md`) | Service-time counterpart |
|---|---|
| `Probe` ABC contract (§4) | **Unchanged.** Same ABC; lifts directly. |
| Probe registry (decorator-based) | **Unchanged.** Same registry. |
| asyncio coordinator | Temporal Activities; each probe runs as its own Activity; one Activity-per-Probe pattern |
| Filesystem cache (`.codegenie/cache/`) | Object store (S3) for raw artifacts + Postgres metadata index for cache keys |
| `repo-context.yaml` artifact | MCP-served `RepoContext` resource, queried by Stage 3 Planning subgraph |
| Raw probe outputs (`.codegenie/context/raw/`) | Same content, stored in object store, referenced from MCP responses |
| Skills directory (`~/.codegenie/skills/`) | Service-level config repo, MCP-served, versioned |
| Conventions / policies / exceptions YAML | Service-level config repo, MCP-served |
| `CONTEXT_REPORT.md` | Generated as a Stage 2 output, attached to the PR in Stage 6 as evidence |
| CLI entry point (`codegenie gather`) | Triggered from Stage 0 Discovery as a Temporal Activity |
| `.codegenie/notes/` (RepoNotesProbe) | Per-repo directory, walked the same way at service time |
| External docs (D8/D9) | Same probes; production fetches go through approved API clients with audit logging |

The probe contract specifically does not change. New probes, new languages, new task types are added by addition; the coordinator's dispatch backend swaps (asyncio → Temporal) and the cache backend swaps (filesystem → object store), but no probe code is rewritten.

The reverse implication: every architectural decision made in the POC is a forward-compatible decision. Bugs in the POC's probe contract are bugs that propagate into the service. The probe contract review at the end of POC v0.1.0 is therefore the most consequential review in the project.

---

## 7. Open questions and decisions deferred

Each item below is deliberately not settled. The doc commits to revisiting each when the named evidence is available.

### Trust-score threshold calibration

The user proposed T_conf ≤ 0.90 as a reject threshold. The doc commits to objective-signal-only scoring (§4.6) but defers the formula weights and threshold to empirical calibration on the first 50 production migrations. Until then, gates use binary pass/fail on sandbox checks. Resolution requires: real migration data with merge outcomes, post-merge incident data, false-positive/false-negative rates by signal type.

### Checkpointer backend

`InMemorySaver` for development. Postgres vs. Redis for production. Decision waits on volume estimate (workflows per day, average state size per workflow, interrupt frequency, query patterns). Postgres is the default-correct answer; Redis becomes attractive only if state-update throughput dominates.

### Knowledge-graph backend

Qdrant (vector-only), pgvector (Postgres-integrated), or Neo4j (graph-native). Decision waits on the dominant query pattern. Pure similarity search → pgvector for operational simplicity. Cross-solution traversal queries ("show me every prior solution that touched this file plus that dependency") → Neo4j. Mixed → Qdrant. Default-correct: pgvector for Phase 1.

### Hierarchical Planner implementation

Pure routing logic vs. LLM-driven supervisor. The SHERPA paper allows ML-driven decisions; it does not require them. For Phase 1, pure routing (deterministic intent classification + lookup table) likely suffices — the routing decision is small and structured. LLM-driven supervisor becomes attractive when intent space grows beyond a handful of task types or when intent disambiguation requires context-sensitive reasoning.

### Sandbox stack

Firecracker (microVM-native, hardware-isolated, fastest cold start), gVisor (user-space kernel, simpler ops, slower for some workloads), or nested QEMU (most compatibility, slowest). Decision waits on workload profile, especially: do we need `strace`/eBPF inside the sandbox (Firecracker yes; gVisor partial), and how often do we cold-start vs. reuse?

### Agents SDK at the leaves

Anthropic vs. OpenAI vs. both behind a thin shim. The SHERPA discipline isolates this choice to leaf node implementations, so the cost of changing later is small. Default: start with Anthropic's SDK for Claude (the prompt-cache, citations, and extended-thinking features fit the planning use case); add an OpenAI implementation behind the same shim only if cost or capability arguments emerge.

### Policy engine: build vs. adopt

The Agent RuleZ pattern is well-described; an implementation library exists per [gemini-auto-agent-design.md](gemini-auto-agent-design.md). Evaluate whether its hook model integrates cleanly with LangGraph `conditional_edge`s (likely) or whether the LangGraph edges themselves are sufficient (also likely, with the right helper). Default: prototype with LangGraph edges + small custom helper; adopt Agent RuleZ if the policy DSL becomes a productivity multiplier.

### Per-subgraph topology

How much subgraph structure is shared boilerplate, how much is per-task. Migration and vulnerability subgraphs likely diverge significantly. Refactor opportunities surface after the third subgraph is built. Resist premature abstraction — three concrete subgraphs first, then identify the shared shape.

### MCP server topology

One global MCP serving all artifacts vs. per-stage MCP servers (gather-MCP, knowledge-graph-MCP, policy-MCP). Decision waits on operational complexity — global is simpler to deploy; per-stage is simpler to scope and authorize. Default: per-stage, since the authorization model is cleaner.

---

## 8. Architectural views (4+1)

The 4+1 model (Kruchten, 1995) separates the architecture into five concerns so different stakeholders can reason about the system without holding the whole picture in their head at once. Logical view = what components exist and how they relate. Process view = how the system behaves at runtime, concurrency, and timing. Development view = how the code is organized for engineers. Physical view = how it maps onto infrastructure. Scenarios = walkthroughs that tie all four together.

Each subsequent system design doc in this project should follow the same §8 structure with the same five views, so the documentation surface stays consistent as the surface area grows.

### 8.1 Logical view — components and their relationships

What the system is composed of, conceptually, regardless of where the code lives or how it's deployed.

```mermaid
graph TB
    subgraph EXT["External"]
      GH["GitHub / GitLab<br/>(source + PRs)"]
      REG["Container registries<br/>(docker.io, cgr.dev)"]
      LLMP["LLM provider APIs<br/>(Anthropic, OpenAI)"]
    end

    subgraph TWF["Temporal layer"]
      WF["Per-repo Workflow"]
      ACT["Activities<br/>(probes, gates, LLM calls)"]
    end

    subgraph ORCH["Orchestrator (LangGraph + SHERPA discipline)"]
      SUP["Supervisor Node<br/>(intent routing)"]
      VS["Vulnerability Subgraph"]
      MS["Migration Subgraph"]
      ST["Pydantic State Ledger"]
      GATE["Trust-Aware Gates<br/>(conditional_edges)"]
      LEAF["Leaf LLM via Agents SDK"]
    end

    subgraph SAFE["Trust-Aware verification"]
      SAND["microVM Sandbox<br/>(build, test, SAST, DAST)"]
      POL["Policy Engine<br/>(Agent RuleZ pattern)"]
      SCORE["Trust Score<br/>(objective signals only)"]
    end

    subgraph DATA["Structured-data backbone (MCP-served)"]
      CTX["Context MCP<br/>(RepoContext)"]
      SK["Skills MCP"]
      KG["Knowledge Graph MCP<br/>(solved examples)"]
      POLM["Policy MCP"]
    end

    subgraph GATHER["Gather layer (the localv2.md POC)"]
      COORD["Probe Coordinator"]
      PROBES["Probes A–G"]
    end

    GH -- candidate repos --> WF
    WF --> SUP
    SUP -- route --> VS
    SUP -- route --> MS
    VS --> ST
    MS --> ST
    ST -- transition --> GATE
    GATE --> SAND
    GATE --> POL
    GATE --> SCORE
    VS --> LEAF
    MS --> LEAF
    LEAF -. queries .-> CTX
    LEAF -. queries .-> SK
    LEAF -. queries .-> KG
    LEAF -. calls .-> LLMP
    GATE -. checks against .-> POLM
    SAND --> REG
    COORD --> PROBES
    PROBES --> CTX
    ACT --> COORD
    GATE -- open PR --> GH
```

**Reading guide.** The Hierarchical Planner (Supervisor) reads intent and routes into one of the task-specific subgraphs. The subgraph progresses node-by-node, mutating the Pydantic state ledger. Every transition passes through Trust-Aware gates, which consult the microVM sandbox, the deterministic policy engine, and the objective trust score. Leaf nodes call the LLM via the Agents SDK, with context pulled on-demand from MCP-served structured data (Context, Skills, Knowledge Graph, Policy). The gather layer is the canonical Context-MCP backend.

### 8.2 Process view — runtime behavior and concurrency

How the system behaves over time. Shows fan-out across parallel workers, the gate-evaluation loop, and the durable-pause-for-human-review pattern.

```mermaid
sequenceDiagram
    autonumber
    participant Cron as Stage 0 Scheduler
    participant TMP as Temporal
    participant SUP as Supervisor
    participant W as Worker Subgraph (one of N parallel)
    participant GATE as Trust-Aware Gate
    participant SND as microVM Sandbox
    participant KG as Knowledge Graph
    participant HUM as Human Reviewer
    participant GH as GitHub

    Cron->>TMP: nightly discovery scan
    TMP->>SUP: spawn N per-repo workflows (parallel)

    par per-repo workflows (N in parallel)
      SUP->>W: route into subgraph (state ledger initialized)
      loop per node transition in W
        W->>W: node executes (mutates state, returns)
        W->>GATE: state delta presented
        GATE->>KG: any prior solved example for this state?
        KG-->>GATE: inject proven solution if matched
        GATE->>SND: run objective checks (build, test, SAST)
        SND-->>GATE: pass/fail per signal
        alt all signals pass
          GATE-->>W: advance to next node
        else failure & retries < 3
          GATE-->>W: route back with error context attached to state
        else retries exhausted
          GATE->>TMP: interrupt() + checkpoint
          TMP-->>HUM: page on-call
          HUM->>TMP: review and resume / abandon
        end
      end
      W->>GH: open PR with evidence bundle
    end

    GH-->>TMP: pull_request.closed webhook (days later)
    TMP->>SUP: signal received
    SUP->>KG: write solved example (Stage 7 Learning)
```

**Reading guide.** Per-repo workflows execute in parallel; failures in one worker do not crash siblings or the Supervisor. Within a worker, the SHERPA subgraph is sequential — state-as-contract means each node waits for the prior gate verdict. The Knowledge Graph injection happens at gate-evaluation time, *before* the LLM is consulted, drastically reducing token spend at portfolio scale. `interrupt()` + checkpointer makes multi-day human-review pauses cheap.

### 8.3 Development view — code organization

How the codebase is laid out for engineers. Packages are organized by architectural layer, not by feature, so layer boundaries stay visible.

```mermaid
graph LR
    subgraph REPO["codewizard-sherpa (one Python project)"]
      direction TB

      subgraph GATHER["codegenie/ — gather layer (lifts from localv2.md POC)"]
        direction TB
        CLI["cli.py<br/>(codegenie gather)"]
        COORD["coordinator/<br/>(asyncio → Temporal)"]
        PROBES["probes/<br/>A–G layers"]
        SCHEMA["schema/<br/>(JSON Schema, Pydantic)"]
        CATALOG["catalogs/<br/>(shell-replacements, native-modules)"]
      end

      subgraph ORCH["sherpa/ — orchestrator"]
        direction TB
        SUP["supervisor/<br/>(intent routing)"]
        SUBM["subgraphs/migration/"]
        SUBV["subgraphs/vulnerability/"]
        STATE["state/<br/>(Pydantic models)"]
        GATES["gates/<br/>(conditional_edges)"]
      end

      subgraph TRUST["trust/ — verification"]
        direction TB
        SAND["sandbox/<br/>(microVM client)"]
        CHECKS["checks/<br/>(build, test, SAST, CVE diff)"]
        SCORE["score/<br/>(objective-signal aggregator)"]
      end

      subgraph PLAT["platform/ — durable substrate"]
        direction TB
        TWF["temporal/<br/>(workflows + activities)"]
        MCP["mcp_servers/<br/>(context, skills, kg, policy)"]
        STORE["stores/<br/>(object, postgres, vector)"]
      end

      subgraph CFG["config/ — domain knowledge as data"]
        direction TB
        SKILLS["skills/"]
        CONV["conventions/"]
        POLI["policies/"]
        EXC["exceptions/"]
      end
    end

    CLI --> COORD
    COORD --> PROBES
    PROBES --> SCHEMA
    PROBES --> CATALOG
    TWF --> SUP
    SUP --> SUBM
    SUP --> SUBV
    SUBM --> STATE
    SUBV --> STATE
    STATE --> GATES
    GATES --> CHECKS
    CHECKS --> SAND
    GATES --> SCORE
    SUP -. reads .-> MCP
    MCP --> STORE
    MCP --> SKILLS
    MCP --> POLI
    PROBES -. emits to .-> STORE
```

**Reading guide.** Five top-level packages, each owning one layer of the architecture: `codegenie/` (gather), `sherpa/` (orchestrator), `trust/` (verification), `platform/` (durable substrate), `config/` (organizational data). The probe contract in `codegenie/probes/` is the same ABC used by the POC — no rewrite at service-time. New languages or task types add subdirectories (`probes/java/`, `subgraphs/lang_upgrade/`) without touching existing code (commitment §2.5).

### 8.4 Physical view — deployment topology

How the components map onto running infrastructure. K8s-first, with a dedicated sandbox cluster for isolation.

```mermaid
graph TB
    subgraph K8S["Kubernetes cluster (main)"]
      direction TB

      subgraph CP["Control plane"]
        TS["Temporal Server"]
        TUI["Temporal UI"]
      end

      subgraph WORK["Worker pool (autoscaled)"]
        WW1["Workflow Worker"]
        WW2["Workflow Worker"]
        WWN["..."]
      end

      subgraph ACT["Activity workers (autoscaled, role-tagged)"]
        AP["Probe Runner pods<br/>(gather Activities)"]
        AG["Gate Runner pods<br/>(invoke sandbox + score)"]
        AL["LLM Caller pods<br/>(scoped identities)"]
      end

      subgraph MCPS["MCP servers"]
        M1["Context MCP"]
        M2["Skills MCP"]
        M3["Knowledge Graph MCP"]
        M4["Policy MCP"]
      end

      subgraph OBS["Observability"]
        TR["Trace store<br/>(reasoning + tool-call logs)"]
        AUD["Audit log<br/>(state transitions, gate verdicts)"]
      end
    end

    subgraph SBOX["Sandbox cluster (Firecracker microVMs)"]
      SB1["microVM"]
      SB2["microVM"]
      SBN["..."]
    end

    subgraph STORES["Persistent stores"]
      PG[("Postgres<br/>Temporal state + checkpoints")]
      S3[("Object store / S3<br/>SBOMs, CVE reports, traces, raw probe artifacts")]
      VDB[("Vector DB<br/>solved examples")]
    end

    subgraph EXT["External"]
      GH["GitHub / GitLab"]
      LLMP["Anthropic / OpenAI APIs"]
      REG["Container registries"]
    end

    WW1 --> TS
    WW2 --> TS
    WWN --> TS
    TS --> PG
    WW1 -. dispatches .-> AP
    WW1 -. dispatches .-> AG
    WW1 -. dispatches .-> AL
    AP --> S3
    AG --> SB1
    AG --> SB2
    AL --> LLMP
    AL -. consults .-> M1
    AL -. consults .-> M2
    AL -. consults .-> M3
    AG -. consults .-> M4
    M1 --> S3
    M1 --> PG
    M3 --> VDB
    SB1 --> REG
    WW1 --> GH
    WW1 --> AUD
    AL --> TR
    AG --> AUD
```

**Reading guide.** Temporal cluster is the durable substrate; workflow workers and activity workers autoscale independently (activity workers are heavier per pod). The sandbox cluster runs Firecracker microVMs in a separate trust boundary — gate runners RPC into it but never share a kernel with it. MCP servers are per-stage to keep authorization scopes clean (§7 deferred decision). Trace store + audit log are the observability backbone — every state transition and gate verdict is persisted for compliance review and drift detection.

### 8.5 Scenarios (+1) — vulnerability and migration walkthroughs

The +1 view validates the other four by walking concrete user stories through them. Two scenarios; both end at PR creation because **humans always merge** (commitment §2.8).

#### Scenario A: Single-CVE remediation (restrictive subgraph, high-rigor gates)

```mermaid
sequenceDiagram
    autonumber
    actor Sec as Security Team
    participant Trig as CVE Feed
    participant SUP as Supervisor
    participant VS as Vulnerability Subgraph
    participant GATE as Trust-Aware Gate (max rigor)
    participant SND as Sandbox
    participant LLM as Leaf LLM
    participant KG as Knowledge Graph
    participant HUM as Human Reviewer

    Sec->>Trig: triages CVE-2026-145
    Trig->>SUP: "Fix CVE-2026-145 in auth-service"
    SUP->>VS: route into Vulnerability Subgraph

    VS->>VS: Reproduce_CVE node
    VS->>GATE: state has repro
    GATE->>SND: run repro inside microVM
    SND-->>GATE: CVE triggers reliably ✓
    GATE-->>VS: advance

    VS->>KG: query prior fixes for this CVE class
    KG-->>VS: inject solved example if any
    VS->>LLM: Draft_Patch (with solved example as few-shot)
    LLM-->>VS: patch diff
    VS->>GATE: state has patch

    GATE->>SND: SAST + DAST + targeted CVE test + full test suite
    alt all signals pass
      SND-->>GATE: pass
      GATE-->>VS: advance to Open_PR
      VS->>HUM: PR opened with full evidence bundle
    else any signal fails AND retries < 3
      SND-->>GATE: fail (logs attached)
      GATE-->>VS: route back to Draft_Patch with error context
    else retries exhausted
      GATE-->>HUM: interrupt() + escalate
    end
```

**What this proves.** The vulnerability scenario is short, restrictive, and gate-heavy. The agent cannot drift outside `Reproduce → Draft_Patch → Open_PR`. Three failed `Draft_Patch` attempts trigger human escalation rather than silent fallthrough. Knowledge-graph lookup runs *before* the LLM call, reducing token spend on patterns we've already solved.

#### Scenario B: Org-wide migration (N parallel agents, knowledge-graph reuse)

```mermaid
sequenceDiagram
    autonumber
    participant CRON as Stage 0
    participant SUP as Supervisor
    participant W2 as Worker #2 (early)
    participant KG as Knowledge Graph
    participant W45 as Worker #45 (later, parallel)
    participant LLM as Leaf LLM
    participant GATE as Trust Gate
    participant SND as Sandbox
    participant GH as GitHub

    CRON->>SUP: 50 Node-service candidates discovered
    SUP->>W2: spawn (Migration Subgraph)
    SUP->>W45: spawn (Migration Subgraph)
    Note over SUP,W45: ... 48 more workers spawned in parallel

    rect rgba(200,220,255,0.4)
      Note over W2: Worker #2 — earlier in time
      W2->>LLM: Resolve dependency conflict (pnpm/sharp/libvips)
      LLM-->>W2: proposed resolution
      W2->>GATE: state has resolution
      GATE->>SND: build + smoke test
      SND-->>GATE: pass ✓
      GATE-->>W2: advance
      W2->>GH: PR opened
      Note right of GH: merged days later
      GH-->>KG: Stage 7 Learning writes solved example
    end

    rect rgba(220,255,220,0.4)
      Note over W45: Worker #45 — encounters same conflict
      W45->>GATE: state has dependency conflict
      GATE->>KG: query by state fingerprint
      KG-->>GATE: matched Worker #2's solved example
      GATE-->>W45: inject solved example into state
      W45->>LLM: Resolve (few-shot from solved example)
      LLM-->>W45: proposed resolution (high confidence, low tokens)
      W45->>GATE: state has resolution
      GATE->>SND: build + smoke test
      SND-->>GATE: pass ✓
      GATE-->>W45: advance
      W45->>GH: PR opened
    end
```

**What this proves.** The migration scenario shows portfolio-scale fan-out with cross-worker learning. Worker #45 benefits from Worker #2's earlier success without coordination overhead — the Knowledge Graph mediates. Token spend on Worker #45 drops dramatically because the LLM is doing few-shot pattern matching against a proven solution, not exploring the space cold. Failures in any one worker do not affect the others (parallel isolation guaranteed by Temporal).

---

*Last updated as the canonical production-target reference. Changes to load-bearing commitments (§2) or to the Layered Hybrid orchestration model (§4) require updating this document and re-aligning the POC roadmap.*
