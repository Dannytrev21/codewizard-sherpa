# Validation report: S3-02 — `AnthropicLeafAdapter`

**Validated:** 2026-05-21 17:38 EDT
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S3-02's core goal is correct: keep Anthropic SDK details behind the `LeafLlm` port, load the API key only through keyring, enforce schema-shaped model output, wrap egress, bound retries, and leave budget reconciliation outside the adapter. The draft was not executor-ready because it drifted from hardened predecessors and from Anthropic's current structured-output API spelling. The story is now aligned to S3-01's `TypeAdapter[PlanProposal]` seam, S2-04's prompt-newtype boundary, S2-05's real `EventLog` API, and ADR-0014's cassette discipline.

## Context brief

### Story snapshot

- **Goal:** Land the concrete Anthropic `LeafLlm` adapter as the only `anthropic` importer, with keyring-only credentials, schema-at-SDK-boundary, egress wrapping, bounded retries, and cassette readiness.
- **Non-goals:** Concrete `EgressGuard` (S3-03), cassette sanitizer (S3-04), cassette lock/scanner (S3-05), live cassette refresh path (S3-06), `FallbackTier` composition (S6-01).

### Phase / arch constraints

- `phase-arch-design.md §Component 4` says the adapter owns SDK translation, key loading, retry policy, prompt-cache control, and leaf events.
- ADR-0001 requires the LLM output be constrained to the `PlanProposal` closed union at the API boundary.
- ADR-0003/S1-05/S1-06 allow `anthropic` only under `src/codegenie/fallback/leaf/`.
- ADR-0005 rejects env-var key fallback and SPKI pinning.
- ADR-0010 says `BudgetToken` is required at the `LeafLlm.invoke` signature and reconciliation happens outside the adapter.
- ADR-0014 says cassette bytes are sanitized before recording and then locked/scanned.

### Existing-code / sibling reality

- S3-01 hardened `LeafLlm.invoke(..., schema: TypeAdapter[PlanProposal], token: BudgetToken)`, not `type[PlanProposal]`.
- S1-02 hardened `PlanProposal` into an `Annotated` discriminated-union alias; schema export is `TypeAdapter(PlanProposal).json_schema()`.
- S2-04 hardened `PromptBuilder.build(...) -> tuple[TrustedPrompt, FencedPromptBody]`, where `TrustedPrompt` is the flattened `skill + "\n\n" + instruction_template` and RAG few-shots stay fenced inside `FencedPromptBody`.
- S2-05 hardened event use to `codegenie.plugins.events.EventLog.emit_internal(...)`, `WorkflowInternalEvent`, and `_INTERNAL_CLASSES`.
- S3-03/S3-04/S3-05/S3-06 are unvalidated successors; S3-02 cannot require their concrete implementation artifacts to exist.

### Open ambiguities

None requiring user input. The conflicts were resolvable by choosing the most recent hardened predecessor story and current vendor docs over stale draft wording.

## Findings by critic

### Coverage critic

- **Cov1 (block)** — `response_format = PlanProposal.model_json_schema()` could not satisfy the goal because `PlanProposal` is not a class and the current Anthropic request spelling is `output_config.format`. Fixed throughout.
- **Cov2 (block)** — AC-19/20/21 required live sanitized cassettes before the sanitizer, scanner, lock, and refresh workflow stories land. This was impossible and unsafe. Fixed by making S3-02 cassette-ready and deferring live cassette bytes to S3-04..S3-06.
- **Cov3 (harden)** — Event payloads lacked registration and replay requirements. Added workflow-internal event models and `EventLog.replay()` assertions.
- **Cov4 (harden)** — Usage-token mapping was underspecified. Added exact mapping from Anthropic usage fields to `LeafResponse` token fields, including zero defaults for optional cache counters.
- **Cov5 (harden)** — Egress wrapping did not state whether retries were physically wrapped. Added one enter/exit pair per physical SDK attempt.

### Test-Quality critic

- **TQ1 (block)** — The draft TDD plan used `event_log_spy.entries` and `src/codegenie/logging.py`; both are stale. Rewritten around the real `EventLog` surface.
- **TQ2 (harden)** — A `cast`-based Protocol proof can hide non-conformance. Replaced with subprocess-mypy positive assignment to `LeafLlm`.
- **TQ3 (harden)** — The malformed-output retry originally appended to `FencedPromptBody`, which could tempt the executor to mint a prompt newtype outside S2-04's sole minter. Rewritten: append trusted suffix only when constructing the SDK request; AST-fence forbids prompt-newtype constructors in the adapter.
- **TQ4 (harden)** — Transport and schema-retry counters could be conflated. Added an AC covering both in one bounded scenario.
- **TQ5 (nit)** — SDK version pinning was left as `X/Y`; story now requires an attempt-log rationale and a cassette compatibility smoke test.

### Consistency critic

- **C1 (block)** — S3-02 contradicted hardened S3-01 on `schema: TypeAdapter[PlanProposal]`. Fixed.
- **C2 (block)** — S3-02 contradicted hardened S2-04 by trying to assemble three system blocks, including RAG few-shots, even though S2-04 flattens trusted text and fences RAG into the user body. Fixed: one cached trusted-system block, exact fenced user body, no splitting/promoting.
- **C3 (block)** — S3-02 referenced concrete `EgressGuard` before S3-03 exists, while S3-03 depends on S3-02. Fixed with an injected `EgressGuardPort` Protocol; S3-03 can satisfy the port later.
- **C4 (harden)** — The story omitted S1-06's required import-linter ignore edge. Added exact singleton `codegenie.fallback.leaf.anthropic_adapter -> anthropic`.
- **C5 (harden)** — Exception/event name collision risk (`LeafProtocolViolation`). Fixed by naming the event `LeafProtocolViolationEvent`.

### Design-Patterns critic

- **D1 (strong aspect)** — The SDK adapter behind a `LeafLlm` Protocol is the correct adapter/port boundary; no registry/factory is warranted for one provider. Kept.
- **D2 (harden)** — Dependency inversion was incomplete because the adapter typed itself against a future concrete egress implementation. Fixed with `EgressGuardPort`.
- **D3 (harden)** — Functional core / imperative shell needed to be explicit. Added pure helper expectations for request building, output-config construction, response parsing, and hash calculation; `invoke(...)` remains the imperative shell.
- **D4 (harden)** — Untyped dict shuffling at the SDK boundary would hide API drift. Added typed local payload aliases or frozen models and a no-`Any` AC.

## Research briefs

- **Anthropic structured outputs API.** Current Anthropic docs describe structured output requests with `output_config={"format": {"type": "json_schema", "schema": ...}}` and the Python SDK `messages.parse(...)` helper. Because this repo's `PlanProposal` is an annotated-union `TypeAdapter`, the story uses `messages.create(...)` plus `schema.json_schema()` and defensive `schema.validate_json(...)`. Source: <https://platform.claude.com/docs/en/build-with-claude/structured-outputs>.

## Conflict resolutions

- **Stale ADR/arch `response_format` wording vs current API + S3-01.** The architectural invariant is schema-at-SDK-boundary, not a specific parameter spelling. Current Anthropic docs and hardened S3-01 make `output_config.format` + `TypeAdapter.json_schema()` the implementable form. Story updated; arch/ADR prose left untouched as out of scope.
- **Prompt-cache granularity vs S2-04 trust boundary.** The older component design wanted `skill`, `instruction_template`, and `rag_few_shot` as three cached system blocks. S2-04's validated contract is newer and security-critical: RAG few-shots are untrusted bytes inside `FencedPromptBody`. Consistency and security win; S3-02 now caches one trusted system block and leaves fenced content in the user message.
- **S3-02 cassette recording vs S3-04/S3-05/S3-06 discipline.** Live cassette recording before sanitizer and lock support would violate ADR-0014. The adapter story now provides scenario markers and expected variants only; recording happens when the cassette-discipline stories make it safe.
- **Concrete guard import vs story order.** Importing S3-03's concrete `EgressGuard` from S3-02 would create a dependency cycle. The port Protocol preserves the behavior and lets S3-03 implement later.

## Edits applied

1. Header `Status: Ready -> HARDENED`; added validation notes.
2. Dependencies updated to name S3-01's `TypeAdapter[PlanProposal]` seam and S1-05/S1-06 fence/import-linter pair.
3. Context rewritten around current API, S2-04 prompt shape, injected egress port, real event API, and deferred cassettes.
4. References updated with predecessor validations and Anthropic structured-output docs.
5. Goal rewritten to preserve adapter scope while removing unsafe live-cassette recording from S3-02.
6. AC-1/2 hardened around positive mypy conformance and `EgressGuardPort`.
7. AC-3/4/5 hardened around key secrecy, real internal events, and no env fallback.
8. AC-6/7/8/9/10/11 rewritten for exact `TypeAdapter` signature, `output_config.format`, one system block, exact user body, response parsing, digest formulas, and budget non-reconciliation.
9. AC-12/13/14 rewritten for one bounded malformed-output retry without prompt-newtype re-minting.
10. AC-15/16/17 hardened for transport retry schedule and counter separation.
11. AC-18 hardened for egress wrapping every physical SDK attempt.
12. AC-19/20/21 hardened for fence + import-linter singleton edge.
13. AC-22/23/24 added to defer live cassettes safely.
14. Implementation outline, TDD plan, files-to-touch, out-of-scope, and notes rewritten accordingly.

## Verdict rationale

HARDENED. The story's intent is valid and does not need a rewrite, but five blockers would have caused executor failure or a security regression: stale schema/API spelling, contradiction with the prompt-builder boundary, dependency cycle with future `EgressGuard`, unsafe cassette recording order, and stale event API assumptions. Each blocker had a clear in-place fix that preserves the story's goal. The adapter is now specified as a small typed SDK boundary with injected ports, bounded retries, schema validation, and no premature plugin/factory abstraction.

## Recommended next step

`phase-story-executor` can implement S3-02 after S3-01/S2-04/S2-05/S1-05/S1-06 are available. Start with the event models and the request-shape tests, then implement the adapter against SDK fakes. Do not record live cassettes until S3-04 through S3-06 have landed.
