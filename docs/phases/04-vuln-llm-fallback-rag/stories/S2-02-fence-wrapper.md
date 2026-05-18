# Story S2-02 — FenceWrapper pure core + audit shell

**Step:** Step 2 — Ship trust-boundary primitives: ProvenanceGate, FenceWrapper/CanaryGuard/PromptBuilder, LlmInvocationGuard/BudgetToken
**Status:** Ready
**Effort:** M
**Depends on:** S1-02 (`PlanProposal` union — supplies `SandboxedRelativePath` / smart-constructor idiom and the substrate Newtypes); S1-01 (`HexNonce` newtype, `FencedSegment` model home, `SourceKind` literal alias) — implementer must verify both have landed before starting
**ADRs honored:** ADR-0013 (scan-untruncated-first ordering + functional-core/imperative-shell + per-source caps, this phase), ADR-0003 (path-scoped fence — module under `src/codegenie/fallback/fence/`, this phase), production ADR-0033 (newtype + smart-constructor + functional-core discipline)

## Context

ADR-0013 lifts the **load-bearing critic fix** out of the security-lens design: the original "scan after truncate" ordering let an attacker hide injection past the truncation byte. The synthesis order is **(1) scan untruncated → (2) on collision replace with `<<redacted: canary collision>>` + emit `CanaryCollision` → (3) truncate to per-source-kind cap → (4) return `FencedSegment`**. S2-02 ships the `FenceWrapper` shell + `fence_pure` pure core + the `Final` truncation-cap dict; S2-03 ships `CanaryGuard.scan` (the canary-detection primitive `fence_pure` invokes); S2-04 ships `PromptBuilder` (the sole minting site for `TrustedPrompt` + `FencedPromptBody`, which compose multiple `FencedSegment` results).

The story splits the **pure functional core** (`fence_pure(payload, nonce, source_kind, scanner) -> FencedSegment`) from the **imperative shell** (`FenceWrapper.fence(payload, source_kind) -> FencedSegment`) — the shell emits audit events and mints the nonce; the core is stdlib-only, no I/O, no global state, no event emission. The AST-walking parity test `tests/unit/fallback/test_fence_pure_shell_parity.py` is the load-bearing guard against drift.

The Hypothesis property `f"</UNTRUSTED_INPUT id={nonce}>" not in fence(p, ...).content` is the single most important invariant: the nonce must never appear inside fenced payload bytes (an attacker who guesses the nonce could otherwise "escape" the fence). The nonce is 16 random bytes (32 hex chars) per ADR-0013; collision probability per call ≈ 2⁻¹²⁸; on collision the canary fires and the payload is redacted.

This story does **not** ship `CanaryGuard.scan` itself — it ships a `Scanner` Protocol the pure core depends on, and a degenerate test-only `_AlwaysCleanScanner` so `fence_pure` is exercisable without S2-03 landed. S2-03 ships the real `CanaryGuard` implementing the Protocol; S2-04 wires the real scanner into `FenceWrapper.fence`'s default.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 3 — FenceWrapper + CanaryGuard` (lines 486-513) — public interface, per-source truncation cap table (§3), functional-core/imperative-shell separation, failure behavior.
  - `../phase-arch-design.md §Design patterns applied` row 5 (line 880) — "Newtype + Smart constructor + Functional core / Imperative shell" for `TrustedPrompt`/`FencedPromptBody`/`FencedSegment`.
  - `../phase-arch-design.md §Anti-patterns avoided` (line 908+) — "Pattern soup"; "Stringly-typed identifiers"; this story uses `SourceKind` literal alias, `HexNonce` newtype, `FencedSegment` Pydantic frozen-extra-forbid.
  - `../phase-arch-design.md §Edge cases row 6` (line 933) — canary detects injection in untruncated payload; this story's truncation runs AFTER the scan invocation `fence_pure` makes.
- **Phase ADRs:**
  - `../ADRs/0013-fence-wrapper-canary-scan-before-truncation.md` — the **load-bearing ordering decision**; per-source truncation caps table; `INJECTION_PATTERNS: Final[tuple]` convention (CanaryGuard owns it — S2-03); functional-core/imperative-shell pattern; `TrustedPrompt`/`FencedPromptBody`/`FencedSegment` newtype minting rules.
  - `../ADRs/0003-path-scoped-fence-amendment.md` — `src/codegenie/fallback/fence/` lives under the admitted path.
- **Source design:**
  - `../final-design.md §Component 3 — FenceWrapper + CanaryGuard` (critic fix on scan-before-truncate).
- **Existing code:**
  - `src/codegenie/audit.py` — `EventLog` shape + event-emission convention.
  - `src/codegenie/types/identifiers.py` + S1-01 additions (`HexNonce`, `BlobDigest`, etc.) — newtype catalog to extend.
  - `src/codegenie/probes/base.py` — Protocol idiom (`@runtime_checkable`).
  - `src/codegenie/_fence.py` — Phase-0 import-fence module (different concept; named confusingly close — read first to avoid namespace surprise; nothing to import).

## Goal

Ship `fence_pure(payload: str, nonce: HexNonce, source_kind: SourceKind, scanner: Scanner) -> FencedSegment` as a stdlib-only pure core, plus `FenceWrapper.fence(payload: str, source_kind: SourceKind) -> FencedSegment` as the imperative shell that mints the nonce, emits `FenceApplied` / `CanaryCollision` audit events, and delegates to `fence_pure` — with the per-source truncation cap dict at module scope as `Final[dict[SourceKind, int]]` and a Hypothesis property proving the nonce never appears in fenced payload content.

## Acceptance criteria

- [ ] **AC-1 — Module location & path-scoped fence.** `src/codegenie/fallback/fence/__init__.py` and `src/codegenie/fallback/fence/wrapper.py` exist. `tests/fence/test_pyproject_fence_phase4.py` remains green; the wrapper module imports only stdlib + `codegenie.*` + Pydantic.
- [ ] **AC-2 — `SourceKind` literal alias.** `SourceKind: TypeAlias = Literal["cve_description", "repo_readme", "transitive_dep_meta", "source_snippet", "sandbox_stderr", "rag_retrieved", "prior_attempt_summary"]` lives in `wrapper.py` (or `src/codegenie/fallback/fence/types.py` if a sibling file is cleaner). Adding a new source kind to the literal is one-line + one-row in `_TRUNCATION_CAPS`. Test asserts `get_args(SourceKind)` is exactly the seven names above.
- [ ] **AC-3 — `_TRUNCATION_CAPS` is module-level `Final[dict]`.** Exact values per ADR-0013's table:
   ```python
   _TRUNCATION_CAPS: Final[dict[SourceKind, int]] = {
       "cve_description":       4 * 1024,
       "repo_readme":           2 * 1024,
       "transitive_dep_meta":   1 * 1024,
       "source_snippet":       16 * 1024,
       "sandbox_stderr":        8 * 1024,
       "rag_retrieved":         8 * 1024,
       "prior_attempt_summary": 4 * 1024,
   }
   ```
   `transitive_dep_meta`'s "× max 16" and `rag_retrieved`'s "× max 3" multiplicities are per-segment, enforced by the caller (S2-04 `PromptBuilder` budgets the count) — this dict carries the **per-segment** cap only. Test asserts byte-exact values, and that `set(_TRUNCATION_CAPS.keys()) == set(get_args(SourceKind))` (so adding to one without the other fails loudly).
- [ ] **AC-4 — `FencedSegment` Pydantic frozen-extra-forbid model.** Fields: `content: str` (the fenced+truncated payload, with delimiter open + body + delimiter close), `nonce: HexNonce`, `source_kind: SourceKind`, `truncated: bool` (True iff truncation actually fired), `original_byte_length: int` (length of input payload before truncation), `canary_fired: bool` (True iff scanner returned a collision). `model_config = ConfigDict(frozen=True, extra="forbid")`. Lives in `src/codegenie/fallback/fence/models.py` or alongside `wrapper.py` — implementer's choice.
- [ ] **AC-5 — `Scanner` Protocol.** `@runtime_checkable Protocol` with one method `def scan(self, payload: str, nonce: HexNonce) -> CanaryResult`. `CanaryResult` is a Pydantic sum type with two variants: `CanaryClean()` and `CanaryCollision(pattern_id: str)` — both frozen-extra-forbid; discriminated via `kind: Literal[...]`. (S2-03 ships the production `CanaryGuard` implementation; this story may ship `CanaryResult` here since the fence's return type depends on it — surface to implementer if S2-03 has already committed `CanaryResult` to its own module, in which case S2-02 imports.)
- [ ] **AC-6 — `fence_pure` is side-effect-free and stdlib+Pydantic-only.** Signature: `def fence_pure(payload: str, nonce: HexNonce, source_kind: SourceKind, scanner: Scanner) -> FencedSegment`. The function:
   1. Invokes `scanner.scan(payload, nonce)` on the **untruncated** payload.
   2. If `CanaryCollision`: replaces `payload` with `<<redacted: canary collision>>`; sets `canary_fired=True`. Truncation still applies to the redacted string.
   3. Truncates the (possibly-redacted) payload to `_TRUNCATION_CAPS[source_kind]` bytes (UTF-8 encoded byte count, not character count — surface this to the implementer if ambiguous; ADR-0013's caps are byte caps per the security-lens framing).
   4. Wraps in delimiter: `f"<UNTRUSTED_INPUT id={nonce}>{body}</UNTRUSTED_INPUT id={nonce}>"`.
   5. Returns `FencedSegment(...)`.
   - AST-walking test `tests/unit/fallback/test_fence_pure_no_side_effects.py` asserts the `fence_pure` function body contains **no** `log.*`, no `EventLog`-shaped call (no `.emit(`), no `open(`, no `os.`, no `subprocess.`, no `print(`, no `time.` calls, no `random.`/`secrets.`/`os.urandom` calls (nonce is an arg, not generated here).
- [ ] **AC-7 — `FenceWrapper.fence` is the imperative shell.** `@dataclass(frozen=True, slots=True) class FenceWrapper`: fields `scanner: Scanner`, `event_log: EventLog`, `nonce_source: Callable[[], HexNonce] = secrets.token_hex_nonce` (or equivalent — the implementer may inline `secrets.token_hex(16)` as the default factory — the seam matters because Hypothesis tests deterministically inject a fixed-nonce factory). Method `fence(payload, source_kind) -> FencedSegment`:
   1. `nonce = self.nonce_source()` — 32-hex-char `HexNonce` (smart-constructed, asserts length and hex shape).
   2. Calls `fence_pure(payload, nonce, source_kind, self.scanner)`.
   3. If `result.canary_fired`: emits `CanaryCollision(source_kind=source_kind, pattern_id=<from scanner>)` event. (The pattern_id flows from the scanner's `CanaryCollision` variant — store it inside `fence_pure`'s returned `FencedSegment` for forwarding; add a private `_pattern_id: str | None` field if necessary, or thread the `CanaryResult` separately — implementer chooses, surface to validator.)
   4. Always emits `FenceApplied(source_kind, nonce, truncated, original_byte_length)` event.
   5. Returns the `FencedSegment` from the pure core.
- [ ] **AC-8 — Hypothesis: nonce-no-escape property.** `tests/property/test_fence_no_escape.py` — `@given(payload=st.text(), nonce=_hex_nonce_strategy())` asserts `f"</UNTRUSTED_INPUT id={nonce}>" not in fence_pure(payload, nonce, "source_snippet", _AlwaysCleanScanner()).content[delimiter_open_length:-delimiter_close_length]` — i.e., the close-delimiter never appears inside the *body* between the open and close delimiters. Equivalently, asserting the close-delimiter appears **exactly once** in `content` (at the end) is the same property — cleaner. 1000+ Hypothesis runs green.
- [ ] **AC-9 — Truncation actually fires at the cap.** Table-driven test: for each `SourceKind`, fence a payload of `_TRUNCATION_CAPS[kind] + 1000` bytes; assert `result.truncated is True` AND `len(result.content.encode("utf-8")) <= _TRUNCATION_CAPS[kind] + len(open_delim) + len(close_delim)`. For a payload of `_TRUNCATION_CAPS[kind] - 1` bytes: `result.truncated is False`.
- [ ] **AC-10 — Canary-collision redaction.** When the injected scanner returns `CanaryCollision(pattern_id="ignore_previous_instructions")`, `fence_pure` returns a `FencedSegment` whose body (between delimiters) is exactly `<<redacted: canary collision>>` (truncated only if the redaction string exceeds the cap — it won't, but the test sanity-checks the post-truncation length). `canary_fired is True`. The `FenceWrapper.fence` shell emits `CanaryCollision(source_kind, pattern_id="ignore_previous_instructions")` — assertion on event payload.
- [ ] **AC-11 — Pure/shell parity invariant.** `tests/unit/fallback/test_fence_pure_shell_parity.py` — for the same `(payload, nonce, source_kind, scanner)`, `FenceWrapper(scanner=scanner, event_log=log, nonce_source=lambda: nonce).fence(payload, source_kind)` returns a `FencedSegment` byte-identical (Pydantic `model_dump()` equality) to `fence_pure(payload, nonce, source_kind, scanner)`. Catches drift.
- [ ] **AC-12 — Event-kind allowlist.** `FenceApplied` and `CanaryCollision` registered in the audit event-kind allowlist (extends S2-01's registration mechanism). `tests/fence/test_event_kinds_complete.py` remains green.
- [ ] **AC-13 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean. `import-linter` (S1-06): the fence module imports zero phase-3 plugin code, zero LLM SDKs, zero RAG deps.

## Implementation outline

1. **Pre-check Step-1 outputs** — `HexNonce`, `BlobDigest`, etc. should be in `src/codegenie/types/identifiers.py`. If `SourceKind`, `FencedSegment`, `CanaryResult` are not in S1-01/S1-02 yet, this story is their first definer (likely the case — surface to implementer).
2. **Create package**: `src/codegenie/fallback/fence/__init__.py`, `wrapper.py`, optionally `models.py` and `types.py`.
3. **Define `SourceKind`, `_TRUNCATION_CAPS`, `CanaryResult`, `FencedSegment`, `Scanner` Protocol** — all in `wrapper.py` or split per the implementer's preference. Module-level `Final` annotations.
4. **Implement `fence_pure`** as a top-level pure function — no class state, no events, no I/O.
5. **Implement `FenceWrapper`** as `@dataclass(frozen=True, slots=True)` with `scanner`, `event_log`, `nonce_source` (default `lambda: HexNonce(secrets.token_hex(16))`).
6. **Register events** in the audit allowlist.
7. **Write the AST-walk pure-core test first** — it's a structural property that should never regress.
8. **Run `make check`**.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/property/test_fence_no_escape.py
from __future__ import annotations

from dataclasses import dataclass
from hypothesis import given, settings, strategies as st

from codegenie.fallback.fence.wrapper import (
    CanaryClean,
    CanaryResult,
    FencedSegment,
    Scanner,
    fence_pure,
)
from codegenie.types.identifiers import HexNonce


@dataclass(frozen=True)
class _AlwaysCleanScanner:
    def scan(self, payload: str, nonce: HexNonce) -> CanaryResult:
        return CanaryClean()


_HEX = "0123456789abcdef"


@given(
    payload=st.text(min_size=0, max_size=4096),
    nonce_seed=st.integers(min_value=0, max_value=2**128 - 1),
)
@settings(max_examples=1000, deadline=None)
def test_close_delimiter_appears_exactly_once_in_fenced_content(
    payload: str, nonce_seed: int
) -> None:
    nonce = HexNonce(f"{nonce_seed:032x}")
    segment = fence_pure(
        payload=payload,
        nonce=nonce,
        source_kind="source_snippet",
        scanner=_AlwaysCleanScanner(),
    )
    close = f"</UNTRUSTED_INPUT id={nonce}>"
    # The close delimiter is at the end of content exactly once.
    assert segment.content.count(close) == 1
    assert segment.content.endswith(close)
    # And the open delimiter is exactly at the start, exactly once.
    open_ = f"<UNTRUSTED_INPUT id={nonce}>"
    assert segment.content.count(open_) == 1
    assert segment.content.startswith(open_)
```

Run; expect `ModuleNotFoundError: codegenie.fallback.fence`.

### Green — make it pass

Implement `wrapper.py`. Minimum code to pass the property + the AC unit tests. If a payload contains the close-delimiter string verbatim (UTF-8 attacker payload), the canary scanner-clean variant lets it through — but the property says the *fenced* content has exactly one close delimiter. Mitigation: `fence_pure` must scan the post-truncation body for delimiter collisions and treat them as a canary collision (or strip the colliding bytes). **Surface this to the implementer**: ADR-0013's "nonce never appears in fenced content" is the property, and the production canary corpus from S2-03 *should* catch the close-delimiter pattern; for this story's `_AlwaysCleanScanner` test, the simplest correct implementation is to assert the property by *construction* — escape-or-redact the body if the close-delimiter string appears in it. The redaction-on-collision is the safer choice; document it inline.

### Refactor — clean up

- Hoist the delimiter format into a module-level `_DELIM_OPEN_FMT: Final[str]` / `_DELIM_CLOSE_FMT: Final[str]`.
- Verify `fence_pure` is one screen of code; if it grew past ~30 lines, the canary-handling branch may need a helper.
- The Hypothesis strategy for `HexNonce` should be reusable — pull into `tests/conftest.py` or `tests/_strategies.py`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/__init__.py` | Package init (likely already exists from S2-01; empty). |
| `src/codegenie/fallback/fence/__init__.py` | Sub-package init (empty). |
| `src/codegenie/fallback/fence/wrapper.py` | `SourceKind`, `_TRUNCATION_CAPS`, `Scanner` Protocol, `CanaryResult` sum type, `FencedSegment` model, `fence_pure`, `FenceWrapper`. |
| `src/codegenie/audit.py` | Register `FenceApplied` and `CanaryCollision` event kinds. |
| `tests/unit/fallback/test_fence_wrapper.py` | AC-2, AC-3, AC-4, AC-9, AC-10, AC-11, AC-12. |
| `tests/unit/fallback/test_fence_pure_no_side_effects.py` | AC-6 AST-walking test. |
| `tests/unit/fallback/test_fence_pure_shell_parity.py` | AC-11 (separate file emphasises the load-bearing parity check). |
| `tests/property/test_fence_no_escape.py` | AC-8 — 1000+ Hypothesis runs. |
| `tests/fence/test_event_kinds_complete.py` | AC-12 — extend with `FenceApplied`, `CanaryCollision`. |

## Out of scope

- `CanaryGuard.scan` implementation + `INJECTION_PATTERNS` corpus — owned by S2-03.
- `PromptBuilder.build` — owned by S2-04.
- `TrustedPrompt` / `FencedPromptBody` newtype minting + AST-walking sole-mint test — owned by S2-04.
- Phase-5 `prior_failure_summary` consumer — owned by S6-02 (uses `source_kind="prior_attempt_summary"` from this story's table).
- Adversarial corpus (`tests/adversarial/test_canary_bypass_via_truncation.py`) — owned by S2-03 / S7-09.
- Performance benchmarks (≤ 1 ms / 16 KB target per ADR-0013) — implementer may sanity-check but no `bench` marker test required.

## Notes for the implementer

- **Critic-fix reminder — scan UNTRUNCATED, then truncate.** ADR-0013 §Decision and §Tradeoffs row 1 spell this out: the original security design had scan-after-truncate; the critic flagged it as a load-bearing bypass; the fix is the ordering in `fence_pure`. AC-6 step (1) → (2) → (3) is the canonical order. A regression-style unit test in `test_fence_wrapper.py` that constructs a `_RecordingScanner` (capturing the payload it received) and asserts the scanner saw the **full untruncated** byte length, even when the source-kind cap is much smaller, is the load-bearing test for this story.
- **Cross-cutting reminder — Newtypes.** `HexNonce` is a `NewType(str)` smart-constructed to 32 hex chars per S1-01; do not accept raw `str` anywhere `HexNonce` is in the type signature.
- **Cross-cutting reminder — zero LLM tokens.** This story has no `BudgetToken` argument anywhere. The fence is composed before any `LeafLlm.invoke` call; if temptation arises to thread a `BudgetToken` through `fence` for "cost telemetry", **stop and re-read ADR-0010 §Pattern fit** — `BudgetToken` flows through exactly two frames (`FallbackTier → LeafLlm.invoke`), and `FenceWrapper` is not one of them.
- **Byte caps vs character caps.** ADR-0013's table is in KB; the natural reading is bytes-of-UTF-8-encoded-payload, not Python `len(str)` (which is unicode codepoints). Pick byte-cap; document in a module docstring. Hypothesis must generate strings whose UTF-8 byte length is bounded, which is non-trivial — the simplest correct approach is `payload.encode("utf-8")[:cap].decode("utf-8", errors="ignore")` and asserting `len(result.content.encode("utf-8")) <= cap + delim_overhead`.
- **Close-delimiter collision in the body.** The Hypothesis property AC-8 will surface payloads where the close-delimiter string appears verbatim in the body (e.g., attacker-supplied "I just wrote `</UNTRUSTED_INPUT id=DEADBEEF>` to escape" — Hypothesis will eventually generate something close). The correct response is: scan-clean + body-contains-close-delimiter → treat as canary collision (redact). Document this inline in `fence_pure`. S2-03's real scanner will catch this earlier via injection patterns; for `_AlwaysCleanScanner` tests, the in-body check is the structural backstop.
- **`secrets.token_hex(16)`, not `random.randbytes`.** Cryptographic-grade randomness for the nonce — `random` is forbidden by `tests/security/forbidden-patterns` (Phase-0). The fence test pattern asserts no `random.` import in the module.
- **Pure-core/shell parity is load-bearing.** AC-11 catches the drift where someone "fixes" the shell to add a special case the pure core doesn't have, or vice versa. Keep the shell a one-liner over the pure core plus event emissions.
- **`assert_never` for SourceKind.** The truncation function's `_TRUNCATION_CAPS[source_kind]` lookup uses dict-membership; if a new variant is added to `SourceKind` without extending the dict, `KeyError` raises at runtime — AC-3's `set(...keys()) == set(get_args(SourceKind))` test catches this at import time. Belt + suspenders.
