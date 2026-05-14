# ADR-0010: `RedactedSlice` smart constructor — making "redactor was called" type-checkable

**Status:** Accepted
**Date:** 2026-05-14
**Tags:** typing · smart-constructor · structural-defense · secrets · chokepoint · domain-modeling
**Related:** 02-ADR-0005, [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md)

## Context

02-ADR-0005 commits Phase 2 to persisting zero plaintext secrets — the `SecretRedactor` runs in the Phase 0 sanitizer pipeline, replaces matched secrets with `<REDACTED:fingerprint=BLAKE3_8>`, and returns an in-memory `list[SecretFinding]` for the CLI summary that is never persisted. The synthesis defends the chokepoint discipline at the *pipeline* layer: the `OutputSanitizer.scrub` pipeline calls `redact_secrets`, then writes.

The critic surfaced the residual gap (`phase-arch-design.md §"Gap analysis & improvements" Gap 4`): `redact_secrets` returns `tuple[dict[str, JSONValue], list[SecretFinding]]`. **The caller is responsible for not persisting the findings list.** A future contributor could thread the findings into a debug log, an audit-anchor extra field, or a CONTEXT_REPORT debug section, and silently leak plaintext fingerprints (or worse, plaintext if a contributor "improves" the return type). The discipline is enforced by code review, not by types — exactly the failure mode the toolkit's smart-constructor pattern was named to prevent (`design-patterns-toolkit.md §"Smart constructor"` failure mode: "every caller has to remember to call `.validate()` afterward. They won't.").

The Gap 4 improvement names the structural fix: apply the smart-constructor pattern at the redaction boundary. The writer accepts **only** `RedactedSlice`, a frozen Pydantic model whose construction is private to `redact_secrets`. A caller that drops the findings list cannot fake a `RedactedSlice` without going through `redact_secrets`, which by construction produces only fingerprints. The plaintext-cleartext audit-trail lives in the CLI summary path (returned separately by `redact_secrets`, not threaded into a `RedactedSlice`). This makes "redactor was called" **type-checkable**.

The arch doc estimates the cost at ~20 LOC in `output/sanitizer.py`; the writer signature tightens from `dict[str, JSONValue]` to `RedactedSlice`. This ADR records the design and the structural-defense rationale that makes it load-bearing.

## Options considered

- **Option A — Convention only (current state without this ADR).** The writer accepts `dict[str, JSONValue]`; `redact_secrets` returns `tuple[dict, list[SecretFinding]]`; the caller is trusted not to persist the findings list. **Pattern:** none. Critic-flagged: review-enforceable, type-leakable, regresses silently when a future contributor "improves" the return shape.
- **Option B — Return only the redacted slice; collect findings via a global side-channel (e.g., a `ContextVar`).** **Pattern:** ContextVar / hidden state. Wrong: introduces hidden state across module boundaries; the side-channel becomes the new leak surface; defeats the chokepoint discipline by making "who can read the findings" implicit.
- **Option C — `RedactedSlice` smart constructor; construction private to `redact_secrets`; writer signature tightens to accept only `RedactedSlice`; findings returned separately to the CLI summary path.** **Pattern:** Smart constructor + Make-illegal-states-unrepresentable at the I/O boundary. Synthesis pick.

## Decision

Adopt **Option C**. `RedactedSlice` is a frozen Pydantic model in `src/codegenie/output/sanitizer.py`:

```python
class RedactedSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    slice: dict[str, JSONValue]
    findings_count: int
    fingerprints: list[str]  # 8-hex BLAKE3 fingerprints only

# Construction is private; ONLY `redact_secrets(...)` can produce a RedactedSlice.
def redact_secrets(
    slice_: dict[str, JSONValue], probe_name: ProbeId
) -> tuple[RedactedSlice, list[SecretFinding]]: ...
```

The writer (`src/codegenie/output/writer.py`) accepts **only** `RedactedSlice` — its signature tightens from `dict` to `RedactedSlice`. The in-memory `list[SecretFinding]` carries the audit-trail (probe_name, fingerprint, pattern_class, file:line) to the CLI summary path; it is never threaded into the `RedactedSlice` and never persisted. A `forbidden-patterns` pre-commit rule bans `model_construct` under `src/codegenie/output/**` so contributors cannot bypass smart-constructor discipline. **Pattern: Smart constructor at the I/O boundary — making "redactor was called" type-checkable.**

## Tradeoffs

| Gain | Cost |
|---|---|
| The writer's signature **proves** redactor was called — a caller passing a raw `dict` to the writer fails typecheck; the structural enforcement replaces the convention 02-ADR-0005 relied on | ~20 LOC in `output/sanitizer.py` (the `RedactedSlice` model + the smart constructor wrapping the existing `redact_secrets` body); the writer signature change is a contract surface shift requiring a coordinated edit across all callers (one — the sanitizer pipeline) |
| `list[SecretFinding]` returned separately as `tuple[RedactedSlice, list[SecretFinding]]` — the findings list never sits inside the slice, so a "log the slice for debugging" PR cannot accidentally log fingerprints alongside plaintext (because there is no plaintext to log, only fingerprints) | The `RedactedSlice` carries `findings_count` and `fingerprints` as fields, deliberately — the CONTEXT_REPORT renderer can show "N secrets redacted, fingerprints: …" without re-running `redact_secrets`. The fingerprints are 8-hex BLAKE3 — privacy-preserving by construction, but contributors must understand that fingerprints **may** appear in persisted artifacts (the *only* secret-related field that does) |
| `forbidden-patterns` pre-commit bans `model_construct` under `src/codegenie/output/**` — the Pydantic bypass-by-omission failure mode (`final-design.md "Anti-patterns avoided" #5`) closes for this module specifically | The forbidden-patterns net for Phase 2 grows by one rule; a contributor explicitly bypassing `model_construct` for performance gets the build failure with the named ADR pointer |
| Composes with 02-ADR-0005's structural-defense ladder — "plaintext present in zero persisted files" (the runtime assertion) is now backed by "no `dict` reaches the writer" (the type-system assertion). Two structural defenses, layered | A test that wants to inject a known slice into the writer for unit-test purposes must construct it via `redact_secrets`; the test fixture is honest (real redaction path exercised) but slightly more boilerplate than a raw `dict` mock |
| Phase 4 (LLM fallback) RAG ingestion path inherits the type-system guarantee — any artifact reachable from the Phase 0 writer chokepoint is a `RedactedSlice`, never a raw `dict`. Gap 5's `test_no_inmemory_secret_leak.py` structural test verifies this at the source level | The Phase 4 designer must engage with `RedactedSlice` consciously; "we'll just dump the in-memory probe output" is not an option that compiles |

## Pattern fit

Pattern: **Smart constructor + Make-illegal-states-unrepresentable** (`design-patterns-toolkit.md §"Smart constructor"`, §"Make illegal states unrepresentable"). The toolkit's prescription is explicit: "a factory that validates inputs and refuses to construct invalid instances. The raw constructor is private (or doesn't exist); only the smart constructor is public." Phase 2's writer-boundary application is the canonical fit: `RedactedSlice` is the post-redaction value type; the smart constructor (`redact_secrets`) is the only path to it; the failure mode the toolkit names ("every caller has to remember to call `.validate()` afterward — they won't") is closed. The pattern's failure mode the toolkit warns against ("schema before consumer") is avoided — the consumer (the writer) exists and is the one type-checked. Composes with [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md)'s newtype + smart-constructor discipline applied at the I/O boundary rather than at the wire-type boundary — same pattern, different layer.

## Consequences

- `src/codegenie/output/sanitizer.py` ships `RedactedSlice` and the `redact_secrets(slice_, probe_name) -> tuple[RedactedSlice, list[SecretFinding]]` function. `RedactedSlice.__init__` is implicit (Pydantic `BaseModel`); contributors are expected to never construct it directly — the `forbidden-patterns` pre-commit ban on `model_construct` under `src/codegenie/output/**` is the structural enforcement.
- `src/codegenie/output/writer.py` signature: `write_envelope(slice_: RedactedSlice, …) -> Path`. The previous `dict[str, JSONValue]` shape is gone from the writer's public surface.
- `tests/unit/output/test_redacted_slice.py` asserts: (1) `RedactedSlice` round-trips through Pydantic identity; (2) `RedactedSlice.fingerprints` contains only 8-hex strings; (3) `RedactedSlice.findings_count` matches `len(fingerprints)`; (4) construction via `model_construct` is banned at lint time (the forbidden-patterns test asserts this rule fires on a deliberately-incorrect PR).
- `tests/adv/phase02/test_secret_in_source.py` (load-bearing per 02-ADR-0005) is unchanged in shape but assertion-tightened: the writer signature now structurally refuses raw dicts, so the test's "plaintext present in zero persisted files" invariant has two layers of defense (typed signature + runtime assertion).
- The Phase 4 RAG ingestion path (when Phase 4 lands) inherits `RedactedSlice` as the only artifact shape reachable from the writer. Gap 5's `test_no_inmemory_secret_leak.py` structural test asserts the same at the source-level (no `dict` reaches the writer call site).
- A future contributor wanting to add a debug-only "log redaction summary" path can do so via the `RedactedSlice.findings_count` + `RedactedSlice.fingerprints` fields — fingerprints are privacy-preserving by construction, and the type system encourages this safe shape over `list[SecretFinding]` threading.
- 02-ADR-0005 and this ADR together form the **structural ladder**: the redactor pipeline is the runtime defense; `RedactedSlice` is the type-system defense; the test invariant ("plaintext in zero persisted files") is the structural assertion. A regression on any rung is a build failure.

## Reversibility

**Medium-high.** Reverting to the convention-only shape (writer accepts `dict`) is a `writer.py` signature relaxation + a `RedactedSlice` deletion. The smart-constructor discipline would dissolve into review-enforcement, which is exactly the gap this ADR closes — so the reversal is unattractive by design. The harder reversal is **strengthening** the structural defense further (e.g., requiring `RedactedSlice` to carry a typed-capability token tying its construction to a specific probe registry entry); that's a Phase 4+ design concern if cleartext access becomes a Phase 4 task-class need (the Phase 5 microVM is the named escalation door per 02-ADR-0005).

## Evidence / sources

- `../phase-arch-design.md §"Gap analysis & improvements" Gap 4` — `RedactedSlice` smart-constructor improvement
- `../phase-arch-design.md §"Component design" #4 SecretRedactor` — the existing tuple return surface that Gap 4 tightens
- `../phase-arch-design.md §"Anti-patterns avoided" §"model_construct() bypass"` — forbidden-patterns enforcement
- `../final-design.md §"Components" #4 SecretRedactor` — original tuple return shape
- `../critique.md §"Design-pattern critiques" §"Missed patterns" §"Smart-constructor pattern missed at the secret-redactor boundary"` — the framing
- 02-ADR-0005 — the no-plaintext-persistence commitment this ADR structurally enforces
- [Production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) — smart-constructor discipline at wire-type boundaries; this ADR applies the same pattern at the I/O boundary
- `design-patterns-toolkit.md §"Smart constructor"` — the canonical pattern reference
