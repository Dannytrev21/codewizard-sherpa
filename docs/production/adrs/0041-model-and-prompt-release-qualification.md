# ADR-0041: Model and prompt release qualification

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** llm · release · reproducibility · capability · content-addressed-digest
**Related:** ADR-0011, ADR-0015, ADR-0020, [Phase 4 ADR-0001](../../phases/04-vuln-llm-fallback-rag/ADRs/0001-plan-proposal-closed-sum-type.md), [Phase 4 ADR-0014](../../phases/04-vuln-llm-fallback-rag/ADRs/0014-cassette-discipline-security-control.md), [Phase 6.5 design](../../phases/06.5-per-task-class-eval-harness/final-design.md)

## Context

Phase 4 lands the first production-relevant LLM call (`LeafLlm.invoke` against Anthropic's Messages API) and Phase 15 will eventually let the system author its own Skills — together they create two pressures that the original design did not explicitly handle. First, behavior is now jointly determined by *three* moving parts: the model identifier (e.g. `claude-opus-4-7`), the prompt template the planner sends, and the retrieval configuration that decides which solved examples become few-shot context. Changing any one of them changes outcomes, and silent drift in any of them invalidates the evidence collected by Phase 6.5's bench harness. Second, vendors retire models on their own schedules; "the model we qualified six months ago" is a real failure mode that will hit production if nothing forces the issue.

The stub version of this ADR named `(model_id, prompt_template_version, retrieval_config_version)` as a qualified tuple but did not say where the tuple is pinned, what "version" actually means for prompts or retrieval, how the system upgrades, or how it rolls back. Phase 4's `LeafLlm`, `LlmInvocationGuard`, and prompt-template bundle were specified in enough detail (Phase 4 final-design.md §Component 4–5; Phase 4 ADR-0001, ADR-0010, ADR-0014) to commit those details now, while the implementation surface is still small enough to do so without amendment churn.

The downstream consumers are concrete: Phase 6.5's promotion gate (`bench_score.lower_bound_95 ≥ tier_threshold[bronze]` AND `block_severity_failure_modes == ()`) already exists and already gates merges, so qualification can reuse it instead of inventing a parallel gate; Phase 4 ADR-0014's `cassettes.lock` already content-addresses recorded responses, so prompt-template digesting is the same pattern one layer up; Phase 13's cost ledger will want to break spend down by `(model_id, prompt_digest)` band and needs those identifiers to be stable strings, not opaque database rows.

## Options considered

- **A — Pin only `(model_id, prompt_template_version)`, no retrieval-config pinning.** The stringly-numbered `prompt_template_version` of the original stub, plus model id. **Pattern:** Lightweight versioning. Fails reproducibility on RAG-bypass-on-retry tests — the same prompt with a different embeddings model or a different `rag.degraded_floor` value produces different few-shot context and therefore different outputs, but the tuple does not record that the input changed. Bench results from one retrieval configuration cannot be re-asserted on another with the same tuple. Audit replay cannot reconstruct the actual context window.
- **B — Out-of-band model registry / database.** A separate service or database table tracks qualified `(model, prompt, retrieval)` triples; the runtime reads from it. **Pattern:** Stateful service. Operationally heavier — needs a service to deploy, a schema to migrate, an access-control surface to police, a sync story between the registry and the code that uses it. The PR-as-config approach already adopted for cassettes (Phase 4 ADR-0014) and recipes (ADR-0011) is stateless: the qualified tuple is *in the same PR* as the cassette refresh and the code that depends on it, so a `git revert` reverts all three together.
- **C — Content-addressed digests pinned per-plugin in `plugin.yaml`, upgrades land as PRs gated by the existing Phase 6.5 bench (chosen).** Each plugin's `plugin.yaml` declares the exact model id (no aliases), a BLAKE3 digest over the prompt-template bundle, and a BLAKE3 digest over the retrieval configuration. Changing any of the three is an ordinary PR whose CI runs the bench harness; the existing promotion gate is the qualification gate. **Pattern:** Content-Addressed Capability + PR-as-Release-Gate.

## Decision

Adopt **option C**: the qualified release tuple is `(model_id, prompt_template_digest, retrieval_config_digest)`, pinned per-plugin in `plugin.yaml`, content-addressed by BLAKE3, upgraded only via PR, qualified by the existing Phase 6.5 promotion gate, and rolled back by `git revert`. **Pattern:** Content-Addressed Capability + PR-as-Release-Gate.

Concrete shape pinned in each `plugins/<plugin>/plugin.yaml`:

```yaml
llm:
  model: claude-opus-4-7                                  # exact id; no aliases like "latest"
  prompt_template_digest: blake3:<64-hex>                 # over the prompt bundle
  retrieval_config_digest: blake3:<64-hex>                # over (embeddings_model_id, embeddings_model_digest, rag.high_floor, rag.degraded_floor)
```

The two digests are computed deterministically:

- `prompt_template_digest` rolls BLAKE3 over the sorted concatenation of every component the planner sends to the model: `system[0]`, `system[1]`, the bodies of every referenced Skill (resolved at build time, not at call time), and the `response_format` JSON schema. Prompts live at `plugins/<plugin>/prompts/<name>.j2` (or `.md` if Jinja2 is not used). The bundle's canonical sorted form is the same approach `cassettes.lock` uses (Phase 4 ADR-0014).
- `retrieval_config_digest` rolls BLAKE3 over `(embeddings_model_id, embeddings_model_digest, rag.high_floor, rag.degraded_floor)`. This is what makes "retrieval_config_version" content-addressed instead of a stringly-numbered counter.

Upgrading the tuple is a typed PR, not a config flip:

1. A candidate `(model_id, prompt_digest, retrieval_digest)` lands in `plugin.yaml` in a PR.
2. `make refresh-cassettes` re-records the relevant cassettes under the candidate (operator-gated by `I_UNDERSTAND_THIS_SPENDS_TOKENS=1` per Phase 4 ADR-0014); `cassettes.lock` updates as part of the same PR.
3. The Phase 6.5 bench harness runs against the candidate. The existing promotion gate (`bench_score.lower_bound_95 ≥ tier_threshold[bronze]` AND `block_severity_failure_modes == ()`) is the qualification gate — no new gate is introduced.
4. A human reviewer plus a green bench is the merge requirement. Merging the PR promotes the tuple.

Rollback is `git revert` of that PR. Pinned tuples are bitwise reproducible against their cassettes, so reverting the configuration reverts the behavior — there is no out-of-band hotfix knob to remember to flip back.

Stale-model auto-degrade is a pure data lookup:

- A small repo-side table `models.lock` maps `model_id → retired_after` (date).
- When `now < retired_after - 30d`, behavior is unaffected.
- When `retired_after - 30d ≤ now < retired_after`, gather emits `ModelRetiredSoft` (warning).
- When `now ≥ retired_after`, gather emits `ModelRetiredHard` and the plugin refuses to dispatch the workflow.
- Refreshing `models.lock` (when Anthropic announces a retirement date) is an ordinary PR — the system never auto-upgrades to the "next-best" model; it refuses instead, forcing the qualification PR.

`SutDigest` and every per-workflow audit record include the full tuple. Unqualified tuples (anything not currently pinned in `plugin.yaml`) may be tested locally and may run through the bench, but cannot be promoted to a production default.

## Tradeoffs

| Gain | Cost |
|---|---|
| `(model_id, prompt_digest, retrieval_digest)` is bitwise reproducible — any future audit-replay produces the same context window the planner saw at decision time | The prompt-template bundle's canonical sorted form must be specified precisely; the digest is brittle to formatting churn (trailing newlines, key order in the JSON schema) and the canonicalizer needs its own tests |
| Upgrades and rollbacks use the same surface — `git` — so operators do not need a runbook for "how do we revert the model"; `git revert <PR>` is the runbook | Prompt iteration is slower: trying a new wording is no longer a five-second edit, it is a PR with a cassette refresh and a bench run. Iteration friction is the price of attributable regressions |
| The existing Phase 6.5 promotion gate is the qualification gate — no parallel gate to operate, no separate dashboard to monitor | The bench's coverage is the qualification coverage; gaps in the bench are silent qualification gaps. ADR-0015 (eval coverage) is load-bearing here |
| Stale-model auto-degrade refuses rather than silently picking a successor — the failure mode is loud and routes operators to a typed PR | Refusal means a real outage window between "Anthropic retires the model" and "we merge the qualification PR for the successor". `ModelRetiredSoft` 30 days ahead is the mitigation; operator vigilance is the residual risk |
| Statelessness (no model-registry service, no DB) keeps the operational surface as flat as the rest of the system (cassettes, recipes, skills are all PR-as-config) | Multi-plugin coordination on a model upgrade is N PRs (one per plugin), not one — each plugin owns its own tuple. The win is independence (one plugin's model upgrade can land without all others); the cost is N reviews when the upgrade is org-wide |
| Phase 13's cost ledger can break spend down by `(model_id, prompt_digest)` band trivially — both are stable strings already in the audit record | The cardinality of the prompt-digest band grows over time; ledger queries need to project on a window of recent digests, not all of history |

## Consequences

- Every plugin's `plugin.yaml` carries an `llm.model` exact id (no `claude-opus-latest` or similar moving aliases), an `llm.prompt_template_digest`, and an `llm.retrieval_config_digest`. Adding a new plugin adds three required fields.
- `SutDigest` (the system-under-test descriptor the bench harness consumes) and every per-workflow audit record include the full `(model_id, prompt_template_digest, retrieval_config_digest)` tuple. Audit replay reads the tuple to reconstruct the exact context.
- The canonicalizer that produces `prompt_template_digest` lives next to the canonicalizer that produces `cassettes.lock` — they are the same pattern, applied one layer up.
- The Phase 6.5 bench harness inherits the qualification gate by reference: no new gate is introduced; merging a tuple change requires `bench_score.lower_bound_95 ≥ tier_threshold[bronze]` AND `block_severity_failure_modes == ()` on the candidate.
- Phase 13's cost ledger can break spend down by `(model_id, prompt_digest)` band — the audit-event vocabulary already carries `prompt_digest_blake3` and `LeafKeyLoaded` (Phase 4 ADR-0010), so the ledger query is a `GROUP BY` on existing fields.
- Rollback is `git revert <PR>` plus a redeploy of the plugin; there is no model-registry sync step, no DB rollback, no flag flip. The same `git revert` reverts the cassette refresh.
- Anthropic retirement announcements become an ordinary repo PR (one row in `models.lock`); operators get a 30-day warning band (`ModelRetiredSoft`) before refusal kicks in (`ModelRetiredHard`).
- Prompt iteration is friction-bearing — operators feel the PR overhead. This is deliberate; the alternative (silent prompt edits) is what makes Phase 6.5's evidence non-attributable.
- Phase 15's eventual agentic-recipe-authoring inherits this regime: a Skill that authors a new prompt template must go through the same PR + cassette-refresh + bench-gate cycle as a human-authored one; the system cannot self-qualify its own prompts.
- The "tested but not promoted" path is explicit — a developer can run the bench against an unqualified tuple locally (and a CI job can be configured to do so for exploratory PRs), but `plugin.yaml` only carries qualified tuples.

## Reversibility

**Medium.** The mechanics of the gate (PR + cassette refresh + bench) are reversible at low cost — disabling the gate (or pointing it at a different bench) is configuration. Reverting the tuple in `plugin.yaml` is a `git revert`. What is harder to reverse is the *commitment shape*: moving from content-addressed digests to a stateful registry (option B) is a migration of every plugin's `plugin.yaml`, every audit record's schema, and every Phase 13 ledger query that projects on the tuple. Moving from per-plugin pinning to a global pin is similarly disruptive. The defaults (`claude-opus-4-7`, specific digests, specific retirement windows) are configuration and trivially adjustable.

## Evidence / sources

- [Phase 4 final-design.md](../../phases/04-vuln-llm-fallback-rag/final-design.md) §Component 4 — `LeafLlm` and the Anthropic SDK landing
- [Phase 4 final-design.md](../../phases/04-vuln-llm-fallback-rag/final-design.md) §Component 5 — `LlmInvocationGuard` (the audit events `LeafInvoked(prompt_digest_blake3)` / `LeafReturned(response_digest_blake3, ...)` that already carry the tuple)
- [Phase 4 final-design.md](../../phases/04-vuln-llm-fallback-rag/final-design.md) §Prompt template bundle (sorted-concatenation canonical form)
- [Phase 4 ADR-0001](../../phases/04-vuln-llm-fallback-rag/ADRs/0001-plan-proposal-closed-sum-type.md) (typed `PlanProposal` outcomes — the prompt's `response_format` schema is part of the bundle)
- [Phase 4 ADR-0010](../../phases/04-vuln-llm-fallback-rag/ADRs/0010-llm-invocation-guard-budget-token-capability.md) (audit event vocabulary the tuple rides on)
- [Phase 4 ADR-0014](../../phases/04-vuln-llm-fallback-rag/ADRs/0014-cassette-discipline-security-control.md) (`cassettes.lock` is the same BLAKE3 content-addressing pattern one layer down)
- [Phase 6.5 final-design.md](../../phases/06.5-per-task-class-eval-harness/final-design.md) §Promotion gate (the qualification gate is this gate)
- `../design.md §LLM agent leaf` (production-target description of the LLM call site)
- ADR-0011 (recipe-first → RAG → LLM fallback — the LLM path this ADR qualifies)
- ADR-0015 (eval coverage commitments — the bench is load-bearing for this ADR)
- ADR-0020 (multi-vendor deferral — preserved; this ADR is Anthropic-shaped today)

## Out of scope

- **Multi-vendor.** ADR-0020 defers a second LLM vendor; this ADR's `model_id` field is Anthropic-shaped today. A future ADR amendment can widen `model_id` to a `(vendor, model)` pair without changing the digest mechanics.
- **Live A/B between two models in production.** Comparison happens offline in the Phase 6.5 bench; production runs the qualified tuple, not a split.
- **Prompt-engineering UI.** Operators author prompts via PR — no in-browser prompt editor, no runtime prompt override.
