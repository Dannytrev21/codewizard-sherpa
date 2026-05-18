# ADR-0001: `PlanProposal` closed Pydantic discriminated union as the only shape the LLM may emit

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** tagged-union · smart-constructor · make-illegal-states-unrepresentable · llm-output-discipline · adr-0033
**Related:** ADR-0002 (this phase) · ADR-0004 (this phase) · [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) · [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md)

## Context

Phase 4 is the first phase where an LLM produces bytes the system *applies* (not bytes a human reviews before commit). The critic identified "LLM output discipline" as the single load-bearing disagreement across the three design lenses (`critique.md §"Which disagreement matters most"`): performance proposed prompt-instruction + Pydantic-validate-after-parse, best-practices proposed a LangGraph `_validate_lockfile_transform_shape` parse node, security proposed a closed Pydantic discriminated union validated at the SDK boundary via Anthropic's `response_format` JSON schema. The shape we pick determines (a) what an injected LLM can structurally emit, (b) whether the major-version-bump exit-criterion case is *expressible* at all (the 32 KB diff cap one lens shipped refused it on the headline fixture), and (c) Phase 5's already-merged retry interface.

The structural-vs-prose distinction is not academic. Prose-then-parse is the historical home of injection-shaped bugs in LLM pipelines: anything that flows through a free-text completion before reaching a typed model carries adversarial bytes as syntactically-valid prefixes. The critic's adversarial corpus (`tests/adversarial/test_red_team_prompts.py`) presupposes a target shape to enforce; without a closed sum type the corpus has nothing to assert against.

## Options considered

- **Free-form completion + Pydantic-validate afterward** (performance lens). LLM emits prose; an extractor parses out a `Transform.from_json(...)` block; Pydantic validates the parsed dict. **Pattern:** Parser/Validator pipeline. Cheap to ship, weakest enforcement, leaves the parse step as a soft-classification surface.
- **LangGraph parse node** (best-practices lens). A dedicated `_validate_lockfile_transform_shape` node downstream of the LLM node mutates state from prose to typed. **Pattern:** State machine + Validator node. Requires LangGraph (Phase 6 dep dragged into Phase 4) and is still a prose-then-parse pipeline structurally.
- **Closed Pydantic discriminated union with JSON schema enforced at the Anthropic SDK boundary** (security lens). `PlanProposal = dep_bump | override | callsite_rewrite | refuse`, all `frozen=True, extra="forbid"`; schema is exported via `model_json_schema()` and passed as `response_format` so the SDK validates before bytes reach Python. **Pattern:** Tagged union + Smart constructor + Make illegal states unrepresentable.
- **No structural constraint — trust the gates** (implicit option). Treat the LLM as a black box and rely on Phase 5's strict-AND validation to catch bad output. **Pattern:** Trust-then-verify. Rejected as a misread of the threat model — Phase 5 catches *functional* regressions, not structural ones; a syntactically-valid path-escape diff that nukes adjacent files would pass Phase 5's `tests` signal up to the point it broke them.

## Decision

The LLM emits exactly one of four variants: `PlanProposalDepBump`, `PlanProposalOverride`, `PlanProposalCallsiteRewrite`, `PlanProposalRefuse` — all `frozen=True, extra="forbid"`, all path fields smart-constructed as `SandboxedRelativePath`, `callsite_rewrite.diff` smart-constructed as `UnifiedDiff` (rejecting paths outside `files`, binary diffs, and `len(diff) > 64 KB`). The schema is exported via `PlanProposal.model_json_schema()` and passed to Anthropic's API as `response_format` so the SDK validates before bytes ever reach Python. **Pattern:** Tagged union (sum type) + Smart constructor + Make illegal states unrepresentable, per [ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md).

## Tradeoffs

| Gain | Cost |
|---|---|
| Free-form prose is structurally impossible — an injected LLM cannot emit a shell command, a `rm -rf`, or unfenced markdown | Novel plan shapes outside the four variants require an ADR amendment + Pydantic model edit |
| Adapter-boundary validation removes an entire class of parse-then-validate bugs | We are coupled to Anthropic's `response_format` semantics; if a future leaf vendor (per [ADR-0020](../../../production/adrs/0020-leaf-agents-sdk.md)) doesn't support JSON-schema'd output, the adapter must polyfill |
| Phase 5 receives a typed `RecipeApplication` whose innards are already shape-validated — retries are over typed `prior_attempts`, not raw prose | The 64 KB `diff` cap is a calibration knob; if Phase 6.5 evidence shows it kneecaps legitimate major bumps, the cap raises but the prompt budget shrinks to keep token totals constant |
| The adversarial test corpus (`tests/adversarial/test_red_team_prompts.py`) has a precise target — "does any payload yield a `PlanProposal` whose `manifest_path` escapes the sandbox" — measurable not subjective | Adding a fifth shape (e.g., Phase 15's agentic recipe authoring) costs a Phase-15 ADR amendment + downstream consumer updates |
| `PlanProposalRefuse(reason=...)` is a first-class outcome, not an exception — refuse paths get the same audit + chain treatment as accept paths | LLM may game `refuse` as the easy out on hard cases; mitigated by Phase 5 retry envelope counting refuse against the per-workflow attempt budget |

## Pattern fit

Tagged union + Smart constructor + Make illegal states unrepresentable is the toolkit's exact prescription for "state machines, failure-mode taxonomies, edge classification, promotion verdicts." The LLM's output *is* a failure-mode taxonomy with four named outcomes. Modeling it as `Optional[Transform] + Optional[ErrorString]` (the loose Pydantic-validate-after-parse shape) is the very anti-pattern the toolkit flags ("`is_pending: bool, is_running: bool, is_done: bool` instead of `Status = Literal[...]`"). The schema-at-API-boundary move adds Smart Constructor depth: invalid inputs are refused by Anthropic's server before our Python code sees them.

## Consequences

- Phase 5's `GateRunner` consumes `RecipeApplication` knowing every variant is already shape-valid — retry logic is over typed `prior_attempts`, not parse failures.
- Phase 7's distroless plugin can extend behavior by *registering a new plugin* with its own `PlanProposal` schema variants, without editing Phase 4's union (per ADR-0006).
- Phase 6's LangGraph migration receives `PlanProposal` as the typed state crossing the leaf-LLM node boundary — no parse-node needed in Phase 6 either.
- `tests/adversarial/test_plan_path_escape.py` becomes meaningful: every adversarial payload either lands in one of four typed variants or raises `LeafProtocolViolation` before reaching the orchestrator.
- `PlanProposal.rationale: str ≤ 2 KB` is **audit-log-only** and never re-prompted — enforced by `tests/fence/test_no_rationale_in_prompts.py` AST walk (commitment §2.2 — facts not judgments — would crack otherwise).
- Adding new plan shapes is now a public, ADR-tracked event rather than a silent prompt-template change.
- `model_construct()` (Pydantic's validation-bypass entry point) is forbidden in production code — asserted by `tests/fence/test_no_model_construct.py` AST walk.

## Reversibility

**Low.** Adding a fifth variant is one Pydantic class + one schema export + one branch in the consumer `match` statement. Removing a variant is harder — Phase 5 + Phase 6 + downstream plugins consume the typed union and `assert_never` exhaustiveness fires on missing arms — but a deprecation pass through one phase's worth of `match` sites is straightforward. The truly hard reversal is *abandoning* the closed-union discipline (going back to prose); that would require re-doing the entire adversarial corpus, which is the security control we're buying with this ADR.

## Evidence / sources

- `../final-design.md §Lens summary` (security-led on the trust-boundary primitives)
- `../final-design.md §Component 2 — PlanProposal`
- `../final-design.md §Design patterns applied` row 2
- `../phase-arch-design.md §Component design — PlanProposal`
- `../critique.md §"Which disagreement matters most for this phase"` (LLM output discipline is the load-bearing disagreement)
- `../critique.md §"[S] §3"` (32 KB cap kneecapped major bumps; relaxed to 64 KB)
- [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) (newtype + smart constructor + sum type + illegal-states-unrepresentable)
- [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) (`rationale` audit-only consequence)
- Anthropic SDK `messages.create(response_format=...)` API surface
