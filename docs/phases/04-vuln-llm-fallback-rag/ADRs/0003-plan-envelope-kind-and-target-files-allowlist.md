# ADR-0003: `Plan` envelope with `kind ∈ {recipe_invocation, manual_patch}` and `target_files` allowlist

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** action-surface · plan-schema · injection-defense · synthesizer-departure · phase-7-anchor
**Related:** [ADR-0008](0008-prompt-injection-structural-defenses.md), [ADR-0011](0011-llm-prompt-context-exfiltration-boundary.md), [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md)

## Context

The LLM emits a plan. Without a structural envelope, "plan" could be free-form natural language, a list of shell commands, or a unified diff — anything attacker-controlled bytes can rewrite the prompt into. The architect's headline departure from all three lens designs (`phase-arch-design.md §"Executive summary"`) is that the LLM does not emit a diff or a free-form plan directly; it emits a Pydantic-validated `Plan` envelope whose `target_files` field is constrained at validation time to a hard-coded path allowlist. The `rag_exact` materialization gap (`phase-arch-design.md §"Gap analysis" §"Gap 1"`) further constrains: only `kind="recipe_invocation"` plans are repo-portable, so `rag_exact` may only short-circuit the LLM when the retrieved example's plan is recipe-shaped.

This is the single defense that makes "an injected LLM can't edit source files, CI config, or `.git/hooks`" structurally true rather than just statistically rare.

## Options considered

- **No envelope, LLM emits a unified diff inside `<patch>...</patch>` markers.** Best-practices position. Pure pattern-matching defense; an injection that writes `<patch>...delete --rf /...</patch>` parses fine. Validation is post-hoc (`git apply --check`); Phase 3 already does this but only catches *unappliable* diffs, not malicious-but-appliable ones.
- **Envelope with a single `manual_patch` shape.** Performance-lens. Bounds the surface to "produces a diff" but provides no `target_files` constraint and no way to express the "use this registered recipe" path that `rag_exact` and Phase 7 need.
- **Envelope with `kind ∈ {recipe_invocation, manual_patch}` + `target_files` allowlist.** Two-kind envelope. `recipe_invocation` is repo-portable (`recipe_id` + parameters) so `rag_exact` can fire; `manual_patch` is repo-specific (a unified diff) and bounded by `target_files ⊆ {package.json, package-lock.json, yarn.lock, pnpm-lock.yaml, npm-shrinkwrap.json}` at validation time.
- **Free-form structured output via Anthropic `response_format` server-side JSON schema.** Server enforces shape; client validates again. Stronger but cassette-fragile (the response-format feature shape has changed during 2025–2026). Picked as a layered defense, not the sole defense.

## Decision

The LLM emits a Pydantic `Plan` envelope with `model_config = ConfigDict(extra="forbid", frozen=True)`:

```python
class Plan(BaseModel):
    kind: Literal["recipe_invocation", "manual_patch"]
    intent: str
    canary_echo: str
    recipe_invocation: RecipeInvocation | None = None
    manual_patch: ManualPatch | None = None
    rationale: str  # logged only; never executed
```

`ManualPatch.target_files` is validator-enforced ⊆ npm-manifest + lockfile allowlist. `rag_exact` short-circuits the LLM only when the retrieved `SolvedExample.plan.kind == "recipe_invocation"`. Retrieved `manual_patch` examples with cosine ≥ τ_hit demote to tier-3 with the example as few-shot. Phase 7 extends the allowlist by registering a `PathAllowlistProvider` — never by editing `OutputValidator`.

## Tradeoffs

| Gain | Cost |
|---|---|
| An injected LLM cannot edit source files, CI config, `.git/hooks`, or paths outside the npm-manifest+lockfile set — defense is structural, not statistical | Breaking-change CVEs that require source-rewrite exit cleanly with `exit 9 out_of_scope_action_surface` and don't get solved in Phase 4 |
| `rag_exact` is honest about what it short-circuits — only repo-portable plans (recipe_invocation) ever skip the LLM, so the cost story is correct ("near-free for parametric matches; cheap-but-not-free for diff matches") | Phase 4's RAG-hit-rate ≥ 55% goal mostly hits `manual_patch` examples (the dominant shape in early seeding) which means tier-2 still calls the LLM with the example as few-shot |
| Phase 7's distroless allowlist (`Dockerfile`, base-image paths) extends by registering a `PathAllowlistProvider` — no `OutputValidator` edit | Hard-coded allowlist in Phase 4 means the v0.4.0 ship cannot accept *any* operator override; widening the surface requires a Phase 5+ ADR amendment |
| `Plan.kind` becomes a tier-routing signal (Gap 1 resolution), not just a schema discriminator — the engine knows which kind is portable | Two kinds means two parser branches in `OutputValidator`; XOR invariant (exactly one of `recipe_invocation`/`manual_patch` is non-None) needs an explicit `@model_validator` |
| `rationale` field is logged-only; LLM self-confidence stripped before the gate ever sees it ([production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md)) | A `rationale` that smuggles confidence-as-text ("verified by upstream maintainer") may still mislead a human reviewer; the field has to be conspicuously labeled in `remediation-report.yaml` |
| Path-traversal attacks (`target_files=["package.json","../../etc/passwd"]`) caught by the subset check + a normalized-path regex | Adversarial test surface grows: every new path that needs writing requires a registered allowlist provider, not a code edit |

## Consequences

- `Plan` is one of three stable contracts frozen at v0.4.0 (alongside `LeafLlmAgent` Protocol and `SolvedExample` schema). Snapshot-tested.
- `OutputValidator.validate` runs the chain `parse_json → pydantic_validate(extra="forbid") → canary_check → canary_substring_scan → fence_residual_scan → action_surface_check`. First failure short-circuits with the specific error reason. Reasons are durable strings consumed by Phase 5's retry-with-context (e.g., retry on `git_apply_failed`; do not retry on `canary_echo_failed`).
- `rag_exact` materialization requires `recipe_invocation` shape. The dataflow scenario in `final-design.md §"Data flow"` Scenario A is updated to reflect: when the just-written example is `kind="manual_patch"`, the second peer hits tier-2 fewshot-LLM, not `rag_exact`. The "zero LLM cost on re-run" promise holds only for tier-1 query-key cache hits and `recipe_invocation`-shaped RAG hits.
- Phase 7 will register `DockerfilePathAllowlistProvider`; the npm allowlist becomes the default `NpmPathAllowlistProvider`. Mechanism is decorator-or-YAML; specifics deferred to Phase 5 (`phase-arch-design.md §"Open questions"` #1).
- The `Plan.kind="recipe_invocation"` path can dispatch through registered Phase 3 recipe engines if the LLM emits an OpenRewrite-shaped plan (Phase 15 preview); the architect's tentative answer is to route through patch-parse, but Phase 15 designer confirms (`phase-arch-design.md §"Open questions"` #7).

## Reversibility

**Low.** The `Plan` envelope is a public contract frozen across Phase 4–15. Replacing it means rewriting every cassette, every prompt template's expected output shape, every `OutputValidator` test, and every downstream consumer's parser. The *allowlist* is reversible (extensions are additive); the *envelope* is not.

## Evidence / sources

- `../phase-arch-design.md §"Executive summary"` — "The hardest architectural decision is the `Plan` envelope"
- `../phase-arch-design.md §"Component design"` #3 — `OutputValidator` + `Plan` schema
- `../phase-arch-design.md §"Gap analysis" §"Gap 1"` — `rag_exact` only on `recipe_invocation`
- `../final-design.md §"Components"` #5 — `OutputValidator` structural-plan check
- `../critique.md §performance "Things this design missed"` — no structural validation of LLM-produced patch
- `../critique.md §security.1` — tool-less agent + bounded action surface tension
- Production [ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) — facts not judgments
