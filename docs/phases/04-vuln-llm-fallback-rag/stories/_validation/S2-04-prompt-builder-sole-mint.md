# Validation report: S2-04 — PromptBuilder sole mint site

**Validated:** 2026-05-21 15:39 EDT
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S2-04's goal is valid and important: `PromptBuilder` is the smart-constructor boundary that turns trusted system text plus fence-wrapped untrusted bytes into `TrustedPrompt` and `FencedPromptBody`, and no other code should mint either newtype. The draft was close, but not executor-ready. It inherited the recurring Phase-4 stale event API mistake (`codegenie.audit.EventLog` / audit allowlist), left the newtype home ambiguous even though S1-01 does not define these names, let the executor choose incompatible over-cap behaviors, and had tests that could pass while a payload such as `rag_few_shots` was concatenated raw into the prompt. All issues are fixable in place; the story is HARDENED.

## Context brief

- **Story snapshot:** `PromptBuilder.build(...) -> tuple[TrustedPrompt, FencedPromptBody]` composes S2-02 `FenceWrapper.fence(...)` and S2-03 `CanaryGuard` results into a deterministic prompt pair.
- **Phase constraints:** Phase arch G5 and ADR-0013 require every untrusted byte to be fenced before LLM invocation. Arch row 880 explicitly chooses Newtype + Smart constructor + Functional core / Imperative shell, and rejects a Visitor/Builder cascade.
- **Existing code reality:** `src/codegenie/fallback/` is not implemented yet. `src/codegenie/plugins/events.py` is the real `EventLog` surface; `src/codegenie/audit.py` has no `EventLog`. S1-01 does not ship `TrustedPrompt` / `FencedPromptBody`. S2-02 and S2-03 are HARDENED but unexecuted.
- **Sibling lineage:** S2-01, S2-02, and S2-03 were all hardened against stale `codegenie.audit.EventLog` assumptions. S2-02 defines `SourceKind`, `FencedSegment`, `CanaryResult`, and internal fence events; S2-03 defines `CanaryGuard`.
- **Open ambiguities:** none requiring user input.

## Findings by critic

### Coverage critic

- **F1 (block)** — AC-4 let the implementer choose between raising and truncating for multiplicity caps. That makes tests non-deterministic and leaves the executor to decide policy. Fixed by pinning `transitive_dep_meta` truncation-with-event and `rag_few_shots` fail-loud behavior.
- **F2 (harden)** — AC-7 did not prove each untrusted input was passed to `FenceWrapper.fence`. A lazy builder could raw-concatenate one segment and still satisfy delimiter-count assertions for the others. Fixed with a recording/deterministic fence sequence assertion and raw-payload-outside-delimiter check.
- **F3 (harden)** — AC-5 documented order as an example ("e.g.") instead of a contract. Fixed with exact source-kind order and event `source_kinds_used` equality.
- **F4 (harden)** — Empty optional behavior did not explicitly cover empty `transitive_dep_meta` / `source_snippets` as "no delimiter pair" while still requiring the two mandatory segments. Clarified via AC-8.
- **F5 (nit)** — The story's title says "sole mint site", but the goal did not mention the positive control must fail if the minter file is missing. Fixed in AC-3.

### Test-Quality critic

- **F1 (block)** — TDD imports `from codegenie.audit import EventLog`, constructs `EventLog()` with no args, and would fail at collection for the wrong reason. Fixed to `codegenie.plugins.events.EventLog(root, workflow_id)` + `replay()`.
- **F2 (harden)** — The multiplicity test had a comment saying "assert ONE of" two behaviors. That is not a test. Replaced with two concrete tests: truncation event for dependency metadata, pre-fence `ValueError` for over-cap RAG hits.
- **F3 (harden)** — Mutable default `rag_few_shots: list[str] = []` is a Python footgun and a strict-design smell. Replaced with `Sequence[str] = ()`.
- **F4 (harden)** — Determinism test only compared bodies; it did not assert assembly order or event metadata. Fixed by checking `PromptAssembled.source_kinds_used`.
- **F5 (harden)** — Sole-mint AST walk could pass before `prompt_builder.py` exists if no calls are found. Fixed with `_ALLOWED_MINTER.exists()`.

### Consistency critic

- **C1 (block)** — The story claims S1-01 listed/shipped `TrustedPrompt` and `FencedPromptBody`; it did not. Fixed by defining them in `prompt_builder.py` and removing the `identifiers.py` fallback.
- **C2 (block)** — `src/codegenie/audit.py` / "audit allowlist" is stale. Current event sourcing is `codegenie.plugins.events`, with `WorkflowInternalEvent`, `_INTERNAL_CLASSES`, and `__all__`. Fixed in AC-10, AC-11, TDD plan, Files-to-touch, and Notes.
- **C3 (harden)** — Event stream choice was implicit. `PromptAssembled` and `SegmentCountTruncated` are workflow-internal, not spanning, because they describe one workflow's prompt assembly. Fixed in AC-10/AC-11.
- **C4 (harden)** — Current `SourceKind` uses `rag_retrieved`; story parameter name `rag_few_shots` could lead to a new non-existent `SourceKind`. Fixed by explicitly mapping `rag_few_shots` entries to `source_kind="rag_retrieved"`.
- **C5 (nit)** — References omitted sibling validation history that explains the event-log correction. Added event pointers and S1-01 clarification.

### Design-Patterns critic

- **D1 (harden)** — Ambiguous newtype placement would either fork the central identifier catalog or expose constructors globally without need. Keeping these prompt-only newtypes beside the smart constructor preserves the smallest deep interface and the AST guard.
- **D2 (harden)** — PromptBuilder risked becoming a second fence implementation. Added AC-13 no-bypass AST fence to forbid delimiter literals, direct `FencedSegment`/`Canary*` construction, direct canary scan, `fence_pure`, and `_TRUNCATION_CAPS` access.
- **D3 (harden)** — `PromptBuilder` should be a composition shell over `FenceWrapper`, not a new Visitor/segment hierarchy. Notes keep the list-comprehension shape and explicitly reject pattern soup, consistent with ADR-0013.
- **D4 (nit)** — The event id generation helper should mirror S2-01's private `_new_event_id() -> EventId` pattern. Added to implementation outline.

## Research briefs

None. Every finding was resolved through in-repo docs, current source, and sibling validation reports.

## Conflict resolutions

- **Identifier catalog vs sole-mint locality.** Production ADR-0033 generally prefers typed domain primitives, and S1-01 centralizes many Phase-4 identifiers. But `TrustedPrompt` / `FencedPromptBody` are not general identifiers; their load-bearing invariant is "only `PromptBuilder` calls the constructor." The local `prompt_builder.py` definition wins here because it minimizes constructor exposure and avoids unnecessary `identifiers.py` / registry test coupling. AC-3 still enforces the real invariant: only the minter file may call the newtypes.
- **Transitive deps truncate vs raise.** Coverage wanted one deterministic behavior. Design-patterns favored fail-loud for illegal states. Split by source: `transitive_dep_meta` is noisy external context, so truncation-with-event is the safer operator experience; `rag_few_shots > 3` is an upstream programming error, so it raises before fencing.
- **Pattern abstraction.** No new `PromptSegment` hierarchy or registry was added. The phase arch explicitly rejects a Visitor/Builder cascade; a short ordered tuple of `(SourceKind, payload)` pairs is enough.

## Edits applied

1. Header `Status: Ready -> HARDENED`; added `Validation notes`.
2. Context now states S1-01 did not ship the prompt newtypes and pins them to `prompt_builder.py`.
3. References now point to `plugins/events.py`, `tests/unit/plugins/test_events.py`, and S1-01's actual newtype roster.
4. AC-2 rewritten: no `identifiers.py` fallback.
5. AC-3 hardened with `_ALLOWED_MINTER.exists()`.
6. AC-4 rewritten with `Sequence[str] = ()`, real `EventLog`, and deterministic cap policy.
7. AC-5 rewritten with exact deterministic source-kind order and event metadata assertion.
8. AC-7 strengthened to prove each untrusted segment went through the fence.
9. AC-10/AC-11 rewritten for `WorkflowInternalEvent` registration and replay-based tests.
10. AC-13 added: no direct fence/canary/delimiter bypass in `prompt_builder.py`.
11. Implementation outline rewritten around local newtypes, `_iter_segments`, `_new_event_id`, event registration, and AST tests.
12. TDD plan corrected to use `codegenie.plugins.events.EventLog`, `PromptAssembled`, `SegmentCountTruncated`, and pinned cap tests.
13. Files-to-touch updated: remove `identifiers.py`, `audit.py`, and `tests/fence/test_event_kinds_complete.py`; add `plugins/events.py`, `tests/unit/plugins/test_events.py`, and no-bypass AST test.
14. Notes for implementer updated for pinned multiplicity behavior, event API, local newtype placement, and no second fence implementation.

## Verdict rationale

HARDENED. The story's goal is correct, traces to ADR-0013 and the phase arch, and has no structural contradiction. The blockers were stale codebase assumptions and underspecified contracts, not a wrong story. After the edits, the executor has a deterministic policy for every source segment, a concrete event-sourcing contract, mutation-resistant tests for raw prompt leakage, and a local smart-constructor shape that keeps the `PromptBuilder` boundary maintainable.

## Recommended next step

`phase-story-executor` can implement S2-04 after S2-02 and S2-03 land. Start by reading the shipped `wrapper.py`, `canary.py`, `plugins/events.py`, and the sibling validation reports; then write AC-3 and AC-13 first because they guard the story's core invariant.
