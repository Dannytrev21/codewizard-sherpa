# ADR-0013: `FenceWrapper` + `CanaryGuard` — canary scans the UNTRUNCATED payload, then truncate

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** functional-core-imperative-shell · trust-boundary · newtype · smart-constructor · prompt-injection-containment
**Related:** ADR-0001 (this phase) · ADR-0014 (this phase)

## Context

Phase 4 introduces prompt assembly. Every untrusted byte (CVE description, repo README, transitive-dep metadata, source snippets, sandbox stderr, RAG-retrieved content, prior-attempt summaries) flows into the LLM prompt. The security design proposed `FenceWrapper` to wrap each untrusted segment in a per-invocation nonce'd delimiter (`<UNTRUSTED_INPUT id=NONCE>...</UNTRUSTED_INPUT id=NONCE>`) and `CanaryGuard` to scan for known prompt-injection patterns and nonce-collision attempts.

The critic identified a load-bearing implementation bug (`critique.md §"[S] §5"`): the security design's code ordered scan-after-truncate, which let an attacker hide injection past the truncation byte. A 16 KB source snippet truncated to 4 KB would be canary-scanned only on the first 4 KB; anything past byte 4096 was invisible to the guard. Fixing the ordering is the load-bearing change.

The design must also acknowledge the residual: `INJECTION_PATTERNS` is a denylist; denylists are by definition incomplete. The claim cannot be "injection-proof"; the claim must be "every byte is fenced + every collision is loud."

## Options considered

- **Canary scan after truncation** (security design's original). Truncate to source-kind cap, then scan. **Pattern:** Truncate-then-scan. Lets injection past the truncation boundary in untouched.
- **Canary scan before truncation, then truncate** (synthesis fix). Scan the full payload for patterns and nonce collisions; only then apply the per-source-kind cap. **Pattern:** Scan-then-truncate.
- **No truncation; refuse to embed payloads exceeding caps** (alternative). Hard-reject any segment > cap. **Pattern:** Strict size limit. Loses ability to embed large legitimate context (full source snippet truncated is better than refused).
- **Probabilistic injection detection via ML classifier** (alternative). Train a classifier on injection corpora. **Pattern:** ML guard. Over-engineered for Phase 4 corpus; classifier is the same denylist with hidden tunable thresholds.

## Decision

`CanaryGuard.scan(payload, nonce)` runs on the **untruncated** payload. Truncation runs *afterwards* via `FenceWrapper._truncate(payload, source_kind)`. The order in `FenceWrapper.fence(...)` is: `(1) scan untruncated → (2) on collision: replace with redacted-block + emit CanaryCollision; (3) truncate to source-kind cap → (4) return FencedSegment`. `INJECTION_PATTERNS: Final[tuple[bytes, ...]]` is a tuple (not a list — frozen at module load); the canary corpus (`tests/unit/fallback/test_canary_corpus.py`) is acknowledged-incomplete and grown over time. The design ships the **Functional core / Imperative shell** separation: `fence_pure`, `scan_pure` operate on bytes only (no I/O); `FenceWrapper`, `CanaryGuard` are imperative-shell wrappers that emit audit events. `TrustedPrompt` and `FencedPromptBody` are newtypes minted *only* by `PromptBuilder` (asserted by AST-walking test). **Pattern:** Newtype + Smart constructor + Functional core / Imperative shell.

The per-source truncation caps are:

| Source kind | Cap |
|---|---|
| `cve_description` | 4 KB |
| `repo_readme` | 2 KB |
| `transitive_dep_meta` | 1 KB × max 16 |
| `source_snippet` | 16 KB |
| `sandbox_stderr` | 8 KB |
| `rag_retrieved` | 8 KB × max 3 |
| `prior_attempt_summary` | 4 KB |

## Tradeoffs

| Gain | Cost |
|---|---|
| The "hide injection past truncation byte" attack is structurally impossible — scan covers full payload | Scanning untruncated payloads costs more CPU on large inputs (worst case: 16 KB source snippet × ~10 patterns × byte-level scan); measured ≤ 1 ms / 16 KB; negligible |
| Functional-core `fence_pure` / `scan_pure` are testable in isolation with Hypothesis (`tests/property/test_fence_no_escape.py` — "nonce never appears in fenced content") | The imperative shell (`FenceWrapper`, `CanaryGuard`) duplicates a thin wrapper layer; both pure + shell must stay in sync (test: `tests/unit/fallback/test_fence_pure_shell_parity.py`) |
| `TrustedPrompt` and `FencedPromptBody` newtypes are minted only by `PromptBuilder` — AST-walking test asserts no other call site constructs them — the type system enforces "every byte reaching the LLM passed through fencing" | A future call site that legitimately needs to mint these (e.g., a Phase 6 test harness) must request a fixture or extend `PromptBuilder` — friction for legitimate test code, intentional |
| Canary collision replaces the payload with `<<redacted: canary collision>>` and emits `CanaryCollision(source_kind, pattern_id)` — the LLM sees a redacted block, typically returns `Refuse(insufficient_context)` → HITL | Legitimate content containing canary-pattern-shaped text (e.g., a security advisory describing prompt injection) is false-positive redacted; mitigated by per-source-kind pattern selection and operator-portal review of `CanaryCollision` events |
| The honest framing — "every byte fenced + every collision loud + denylist acknowledged incomplete" — is auditable; the test corpus (`tests/unit/fallback/test_canary_corpus.py`) grows over time with new patterns | The design does *not* claim injection-proofness; the security posture is "defense in depth, never sole reliance"; operators must understand this |
| `INJECTION_PATTERNS` is `Final[tuple]` — frozen at module load; the toolkit's "module-level Final tuple" convention is honored | Adding patterns is an additive code change + ADR amendment; can't hot-reload patterns at runtime — by design |

## Pattern fit

The toolkit's **Functional core, imperative shell** pattern is a textbook fit: `fence_pure(payload, nonce, source_kind) -> FencedSegment` is pure (no I/O, no audit emission, fully testable with Hypothesis); the `FenceWrapper.fence(...)` method is the imperative shell that emits the audit event and calls the core. Same for canary: `scan_pure(payload, nonce, patterns) -> CanaryResult` is pure.

**Newtype + Smart constructor** for `TrustedPrompt` and `FencedPromptBody`: only `PromptBuilder` can construct them; the type system enforces the invariant "every prompt-shaped byte passed through fencing." The toolkit's example "every domain primitive shows up in 50 call sites" applies — these newtypes flow from `PromptBuilder` through `FallbackTier.run` into `LeafLlm.invoke`, and no other constructor exists.

## Consequences

- The Hypothesis property `f"</UNTRUSTED_INPUT id={nonce}>" not in fence(p, ...).content` holds for any payload and any nonce — asserted in `tests/property/test_fence_no_escape.py`.
- `tests/unit/fallback/test_fence_wrapper.py` includes a regression test for the scan-untruncated-first ordering — flips ordering would fail loudly.
- `tests/adversarial/test_injection_corpus.py` runs 200+ payloads from PromptInject + project-curated through `FenceWrapper` + `CanaryGuard`; the target is 0 escapes (closes critic [S] §5).
- `INJECTION_PATTERNS` growth: each new pattern is an ADR-light single-line addition; the corpus test catches regressions automatically.
- `CanaryCollision` events are operator-portal-visible; a spike indicates either active adversarial probing or false-positive prone content (e.g., a research advisory).
- `PromptBuilder` is the *only* minting site for `TrustedPrompt` and `FencedPromptBody` — `tests/fence/test_prompt_newtype_minting_bounded.py` AST-walks asserting no other module constructs them.
- Phase 5's `prior_failure_summary` (per ADR-0011 of this phase) is fenced as `source_kind="prior_attempt_summary"` (4 KB cap) when re-entered through `FallbackTier.run`.
- The honest framing in design + ADR: this is *defense*, not a structural proof of injection immunity. Operators must understand the residual.

## Reversibility

**Low.** Flipping scan and truncate orderings is a one-line edit but reintroduces the bypass; would require a Phase-4 ADR amendment with explicit reasoning. Removing the fence entirely (no untrusted-byte protection) would be a load-bearing security regression. Adding new source kinds is additive (one row in the truncation table + one canary corpus pass). Replacing the denylist with an ML classifier (Phase 13+) lands behind the same `CanaryGuard.scan` Protocol — adapter swap.

## Evidence / sources

- `../final-design.md §Component 3 — FenceWrapper + CanaryGuard` (critic fix on scan-before-truncate)
- `../phase-arch-design.md §Component 3 — FenceWrapper + CanaryGuard`
- `../phase-arch-design.md §Design patterns applied` row 5
- `../critique.md §"[S] §5"` (scan-after-truncate hole)
- [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) (newtype + smart constructor + sum type discipline)
