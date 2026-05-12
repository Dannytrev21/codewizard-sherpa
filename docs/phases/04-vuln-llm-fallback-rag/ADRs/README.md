# Phase 04 — Vuln remediation: LLM fallback + solved-example RAG: ADRs

Architecture Decision Records for Phase 4, in Nygard format. Each ADR captures one load-bearing decision: the context, the alternatives considered, what was chosen, the tradeoffs accepted, the consequences, and how reversible the choice is.

**Phase architecture:** [phase-arch-design.md](../phase-arch-design.md) — full architecture spec.
**Source design:** [final-design.md](../final-design.md) — synthesized from three competing lens designs.
**Critique:** [critique.md](../critique.md) — devil's-advocate findings that shaped many of these decisions.
**Production reference:** [docs/production/adrs/](../../../production/adrs/) — the project-level ADR set this phase composes with.
**Prior phases:** [Phase 0 ADRs](../../00-bullet-tracer-foundations/ADRs/) · [Phase 1 ADRs](../../01-context-gather-layer-a-node/ADRs/) · [Phase 2 ADRs](../../02-context-gather-layers-b-g/ADRs/) · [Phase 3 ADRs](../../03-vuln-deterministic-recipe/ADRs/) — the spine these decisions extend.

## Index

| # | Title | Tags |
|---|---|---|
| [0001](0001-recipe-engine-literal-extends-with-rag-llm.md) | `Recipe.engine` Literal extends to include `rag_llm` and the orchestrator gains one conditional branch | contract · extension-by-addition · phase-3-edit · synthesizer-departure |
| [0002](0002-two-tier-writeback-pending-promoted.md) | Two-tier solved-example writeback — `pending/` shelf + `promoted/` corpus + `provenance.merge_status` lifecycle | writeback · trust-gate · phase-11-handoff · synthesizer-departure · adr-0009-fit |
| [0003](0003-plan-envelope-kind-and-target-files-allowlist.md) | `Plan` envelope with `kind ∈ {recipe_invocation, manual_patch}` and `target_files` allowlist | action-surface · plan-schema · injection-defense · synthesizer-departure · phase-7-anchor |
| [0004](0004-leaf-llm-agent-protocol-os-tiered.md) | `LeafLlmAgent` Protocol with OS-tiered implementations (in-process on macOS, bwrap+uid jailed on Linux) | trust-boundary · protocol · process-isolation · phase-5-handoff · synthesizer-departure |
| [0005](0005-chromadb-in-process-with-stale-lock-detection.md) | `chromadb` PersistentClient in-process with single-writer flock + stale-lock detection | vector-store · concurrency · phase-9-handoff · synthesizer-departure |
| [0006](0006-bge-small-en-embedding-model-sha-pinned.md) | `BAAI/bge-small-en-v1.5` as default embedding model, SHA-pinned via `huggingface_hub.snapshot_download(revision=<sha>)` | embedding-model · supply-chain · retrieval-quality · synthesizer-departure |
| [0007](0007-anthropic-model-pin-via-versioned-alias.md) | Anthropic model pin via versioned alias `claude-sonnet-4-7@vuln_remediation` resolved at startup | model-pin · cassette-discipline · supply-chain · synthesizer-departure |
| [0008](0008-prompt-injection-structural-defenses.md) | Prompt-injection structural defenses — canary + per-run random fence-id + structured-plan-references-registered-engine + Pydantic `extra="forbid"` | prompt-injection · canary · fence-wrapping · output-validation · synthesizer-departure |
| [0009](0009-prompts-as-versioned-yaml-data.md) | Prompts as versioned YAML data; inline f-string prompt construction forbidden by fence-CI | prompts-as-data · prompt-cache-discipline · fence-ci · synthesizer-departure |
| [0010](0010-llm-invocation-guard-running-total-with-override.md) | `LlmInvocationGuard` with per-invocation + per-workflow running-total ceiling and explicit `--allow-cost-overrun` override | cost-cap · budget-enforcer · phase-13-handoff · synthesizer-departure |
| [0011](0011-llm-prompt-context-exfiltration-boundary.md) | `LlmPromptContext` Pydantic schema with `extra="forbid"` as the `RepoContext` exfiltration boundary | exfiltration-defense · pydantic-schema · secrets-handling · synthesizer-departure |
| [0012](0012-vcr-cassette-discipline.md) | VCR cassette discipline — `pytest-recording`, `--record-mode=none`, content-addressed cassette key, `cassettes-reviewed` label, nightly canary | testing · cassettes · ci · supply-chain · synthesizer-departure |
| [0013](0013-api-key-store-env-var-refused.md) | `ApiKeyStore` — `ANTHROPIC_API_KEY` env-var refused at orchestrator start; mode-600 file / OS keyring only; OS-tiered strictness | secret-handling · supply-chain · synthesizer-departure |
| [0014](0014-langgraph-leaf-agent-node-minimal-wrap.md) | `LangGraph` imported minimally as `LeafAgentNode` one-node `StateGraph`; Phase 6 replaces the node, not the leaf | langgraph · phase-6-handoff · roadmap-fit · synthesizer-departure |
| [0015](0015-solved-example-schema-task-class-generic.md) | `SolvedExample` schema is task-class-generic (`task_class` as a field) so Phase 7 (Chainguard) and Phase 15 (recipe authoring) reuse the corpus | schema · task-class · phase-7-handoff · phase-15-handoff · synthesizer-departure |

## Conventions

- **Filenames** are `NNNN-kebab-case-title.md` with zero-padded four-digit numbers, numbered locally per phase starting at 0001.
- **Numbers are immutable** — a superseded ADR keeps its number; the new one gets the next number and cross-links.
- **Cross-references** to production ADRs use `../../../production/adrs/NNNN-*.md`. Cross-references to other phase ADRs use the relative filename inside this folder. Cross-references to Phase 0/1/2/3 ADRs use `../../00-bullet-tracer-foundations/ADRs/NNNN-*.md` etc.
- **The phase-arch-design and final-design documents are the architecture contract**; ADRs are the durable rationale. When the two diverge, the ADR is the *why* and the arch doc is the *what*.

## What got an ADR

These decisions met the bar — a real choice with viable alternatives, load-bearing on Phase 4 implementation or Phase 5+ interfaces, durable enough that a future reader benefits from rationale before changing them.

The 16-row conflict-resolution table and five "Departures from all three inputs" in `final-design.md §"Synthesis ledger"` surfaced the ADR candidates; the set was consolidated to 15 ADRs covering:

- **Phase 3 contract edits** (the only two; surfaced loudly) — `Recipe.engine` Literal extension + orchestrator branch (0001). The single edit precedent for Phase 7's distroless extension.
- **Writeback model — the load-bearing structural fight** — two-tier `pending/` + `promoted/` with `provenance.merge_status` lifecycle (0002). Resolves the ADR-0009 vs exit-criterion tension; Phase 11 swaps in the real merge-gated promoter.
- **Action-surface envelope** — `Plan.kind` + `target_files` allowlist (0003). The headline departure from all three lens designs; the structural defense that makes "injected LLM can't edit source files" true, not just rare.
- **Trust-boundary contract** — `LeafLlmAgent` Protocol with OS-tiered impls (0004). Phase 5's microVM swaps in as a third implementation without touching the engine.
- **Vector store + concurrency** — `chromadb` in-process with stale-lock detection (0005). Resolves the Gap-3 deadlock attack on the single-writer discipline.
- **Embedding model** — `bge-small-en-v1.5` SHA-pinned (0006). Closes the critic's MiniLM cosine-compression attack; supply-chain pin via `huggingface_hub.snapshot_download`.
- **Model pin format** — versioned alias `claude-sonnet-4-7@vuln_remediation` (0007). Resolves the cassette-corpus-regen bottleneck of hard-pinned dated models.
- **Prompt-injection structural defenses** — canary + fence + structural plan + Pydantic strict (0008). The four-layer stack that closes most of the threat model; microVM in Phase 5 closes the residual.
- **Prompts as data** — versioned YAML + auto-fence-wrap + fence-CI ban on inline prompts (0009). Resolves the per-call-site-fence-author-forgot-once vulnerability.
- **Cost-cap primitive** — `LlmInvocationGuard` with per-invocation + per-workflow running-total + explicit override (0010). Phase 13's Budget Enforcer is a swap, not a rewrite.
- **Exfiltration boundary** — `LlmPromptContext` Pydantic schema with `extra="forbid"` (0011). Closes the critic's cross-cutting blind spot on `RepoContext` slice leakage.
- **Cassette discipline** — `pytest-recording` + structured key + nightly canary + label gate (0012). Closes the critic's cassette-corpus-regen bottleneck attack.
- **API-key handling** — env-var refused on Linux (warn on macOS); mode-600 / keyring only (0013). Cheap to ship in Phase 4 and load-bearing; Phase 5's microVM tightens it further.
- **LangGraph minimal wrap** — one-node `StateGraph` for Phase 6 swap target (0014). Honors the roadmap line literally.
- **Solved-example schema task-class-generic** — `task_class` as a field, not a type (0015). Phase 7 and Phase 15 extend by addition.

## Decisions noted but not yet documented

Surfaced during ADR extraction as plausibly worth ADR-ing, but the documentation in `final-design.md` and `phase-arch-design.md` doesn't develop them enough to write a confident ADR. Flagged for the implementer / next-phase author:

- **`PathAllowlistProvider` registry mechanics** (`phase-arch-design.md §"Open questions"` #1). Decorator-based (`@register_path_allowlist`) versus YAML config (`src/codegenie/llm/path_allowlists/*.yaml`) — both work. Phase 4 hard-codes the npm list inline; the registry lands when Phase 7 opens the file. A dedicated ADR was deferred until Phase 7's distroless work surfaces the right shape.

- **Embedding sidecar wire format** (msgpack vs JSON over UDS) (`phase-arch-design.md §"Open questions"` #2; `final-design.md §"Open questions"` #3). The wire format is encapsulated in `embed_worker.py`; choice can flip without a public-contract change. Deferred as an implementation decision.

- **Auto-`τ_hit`-raise on misleading-match clusters: default-on or opt-in?** (`phase-arch-design.md §"Open questions"` #3; `final-design.md §"Open questions"` #1). Synth picks default-on; 6 weeks of real usage may show it's too aggressive. A Phase 5 calibration ADR will set the policy after data lands.

- **Cassette format (`.yaml` vs `.yaml.zst`)** (`phase-arch-design.md §"Open questions"` #4). Synth defaults `.yaml`; revisit if cassette corpus crosses 200 files. Mechanical choice; documented in [ADR-0012](0012-vcr-cassette-discipline.md).

- **`solved-examples calibrate` — auto-write thresholds, or suggest-only?** (`phase-arch-design.md §"Open questions"` #5). Synth picks suggest-only for v0.4.0 (operator reviews + commits `~/.config/codegenie/llm.yaml`). A Phase 5+ amendment to [ADR-0006](0006-bge-small-en-embedding-model-sha-pinned.md) may flip this once calibration data is large enough.

- **`τ_hit = 0.86` and `τ_few = 0.72` defaults** (`final-design.md §"Components"` #2 internal-design; ADR-P4-006 noted in final-design). Defaults are educated guesses; per-advisory neighborhood auto-raise on 3 wrong matches is documented as the runtime calibration loop. A dedicated ADR was deferred because the calibration data lands in Phase 5 with the gate machinery; once the data exists, an ADR captures the calibrated thresholds.

- **Audit-event type registry** (`final-design.md §"Open questions"` #5). Phase 4 introduces ~20 new event types (`solved_example.written_pending`, `cost.llm.invoked`, `canary.echo_failed`, etc.). A central `audit-events.yaml` registry would let Phase 13's dashboard consume the schema without hand-coding. Deferred as a Phase 5/13 ADR.

- **Phase 4 + Phase 11 promotion-rollback story** (`final-design.md §"Open questions"` #8). If a Phase 11 human-merge promotion is later determined to be a backdoor, what's the recall path? Synth ships `codegenie solved-examples delete <id>` and the audit chain reveals provenance, but no automatic recall. Phase 16 hardening problem.

- **OpenRewrite-shaped LLM output dispatch** (`final-design.md §"Open questions"` #3; `phase-arch-design.md §"Open questions"` #7). If the LLM emits an OpenRewrite-shaped plan (Phase 15 preview), does `RagLlmEngine` dispatch through `OpenRewriteEngineStub` or always through its own patch-parse path? Synth routes through patch-parse; Phase 15 designer confirms.

- **Negative-example pollution policy** (`final-design.md §"Open questions"` #4). `vuln_solved_examples_negative` grows monotonically; no GC. Phase 15 may consume negatives as anti-patterns. Open: ship a `prune --older-than` policy for negatives in Phase 4 or wait? Deferred to Phase 15's recipe-authoring ADRs.

- **SPKI pinning of `api.anthropic.com`** (`final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "SPKI pinning"). Synthesizer rejected pinning (no rotation runbook; CDN-issued LE certs rotate every ~60 days). Documented for Phase 16 hardening. The *non-decision* is captured in the conflict-resolution table; a dedicated ADR was deferred because the choice is "don't ship pinning yet" rather than a positive architectural commitment.

- **Streaming + Anthropic `response_format` server-side structured output** (`final-design.md §"Synthesis ledger"` row "Streaming vs non-streaming"). Synthesizer ships non-streaming in Phase 4 (cassette stability) and reopens in Phase 6. The non-decision is captured; Phase 6's state-machine ADR will document the reopen.

- **Retry policy in Phase 4** (`final-design.md §"Synthesis ledger"` row "Retry policy in Phase 4"; `phase-arch-design.md §"Non-goals"` NG4). Application retry = 0; transport-only retries ≤ 3 inside `AnthropicClient`. Deferred to Phase 5 with [production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md)'s gate machinery. The Phase 4 commitment is "no application retry"; the rationale lives in `phase-arch-design.md §"Non-goals"`.

- **Cross-repo RAG default + `CODEGENIE_ALLOW_PRIVATE_CROSS_REPO` env defense-in-depth** (`final-design.md §"Synthesis ledger"` row "Cross-repo RAG default"; `phase-arch-design.md §"Non-goals"` NG7). `--allow-cross-repo-rag` required + per-retrieval audit + env defense-in-depth. The mechanism is documented in `phase-arch-design.md §"Edge cases"` row 23; a dedicated ADR was deferred as it's a flag-shape decision contained inside [ADR-0011](0011-llm-prompt-context-exfiltration-boundary.md)'s exfiltration boundary.
