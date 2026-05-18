# Story S2-03 — CanaryGuard scan-before-truncate + INJECTION_PATTERNS corpus

**Step:** Step 2 — Ship trust-boundary primitives: ProvenanceGate, FenceWrapper/CanaryGuard/PromptBuilder, LlmInvocationGuard/BudgetToken
**Status:** Ready
**Effort:** M
**Depends on:** S2-02 (`Scanner` Protocol + `CanaryResult` sum type live in `src/codegenie/fallback/fence/wrapper.py` — this story implements the Protocol)
**ADRs honored:** ADR-0013 (scan-untruncated-first ordering + `INJECTION_PATTERNS: Final[tuple[bytes, ...]]` convention + denylist-acknowledged-incomplete framing, this phase), ADR-0003 (path-scoped fence — module under `src/codegenie/fallback/fence/`, this phase)

## Context

S2-02 shipped the `FenceWrapper` shell + `fence_pure` core + the `Scanner` Protocol and `_AlwaysCleanScanner` test double. S2-03 ships the **production canary primitive**: `CanaryGuard.scan(payload: str, nonce: HexNonce) -> CanaryResult` over a `Final` tuple of `INJECTION_PATTERNS` (bytes), with the **load-bearing untruncated-scan property**: for any payload longer than the largest source-kind truncation cap (16 KB for `source_snippet`), if an injection pattern is hidden past byte `cap`, the scan still fires. This is the structural fix the critic flagged in ADR-0013 §Decision: the original "scan-then-truncate" order let an attacker hide payloads past the truncation byte. ADR-0013's `tests/property/test_canary_scan_untruncated.py` and `tests/adversarial/test_canary_bypass_via_truncation.py` are the load-bearing tests.

The story also ships a **50+ curated injection corpus** as `tests/unit/fallback/test_canary_corpus.py` — names like `ignore_previous_instructions`, `system_override`, `<|im_start|>`, `[INST]`, etc. Each row asserts a specific payload fires a specific `pattern_id`. ADR-0013 §Consequences row 3 calls out the 200+ payload `tests/adversarial/test_injection_corpus.py` — S7-09 owns that larger adversarial suite; this story ships the **first 50+ curated patterns** as the unit-test corpus.

The honest framing per ADR-0013: this is **defense, not a structural proof of injection immunity** — the denylist is acknowledged-incomplete; the corpus grows over time. The structural claim is "every byte is fenced + every collision is loud." This story does NOT claim canary catches every possible injection; it claims canary catches everything in `INJECTION_PATTERNS` regardless of truncation.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 3 — FenceWrapper + CanaryGuard` (lines 486-513) — `CanaryGuard.scan` signature, `INJECTION_PATTERNS: Final[tuple[bytes, ...]]`.
  - `../phase-arch-design.md §Edge cases row 6` (line 933) — canary detects injection in untruncated payload.
  - `../phase-arch-design.md §Testing strategy` row "tests/property/test_canary_scan_untruncated.py" (line 962) — Hypothesis property.
  - `../phase-arch-design.md §Adversarial / red-team` (line 1004+) — `test_injection_corpus.py` 200+ payloads target 0 escapes (S7-09 scope; S2-03 ships the seed corpus).
- **Phase ADRs:**
  - `../ADRs/0013-fence-wrapper-canary-scan-before-truncation.md` — load-bearing ordering decision; `INJECTION_PATTERNS` convention; functional-core/imperative-shell pattern; honest framing of denylist incompleteness.
  - `../ADRs/0003-path-scoped-fence-amendment.md` — module path.
- **Source design:**
  - `../final-design.md §Component 3 — FenceWrapper + CanaryGuard` (critic fix on scan-before-truncate, §"[S] §5").
  - `../critique.md §"[S] §5"` (the scan-after-truncate hole the synthesis fixes).
- **Existing code:**
  - `src/codegenie/fallback/fence/wrapper.py` (S2-02) — `Scanner` Protocol, `CanaryResult` sum type, `_AlwaysCleanScanner`.
  - `src/codegenie/_fence.py` — Phase-0 import-fence (named confusingly, unrelated).

## Goal

Ship `CanaryGuard.scan(payload, nonce) -> CanaryResult` with a `Final[tuple[bytes, ...]]` `INJECTION_PATTERNS` corpus of 50+ curated prompt-injection markers and a `scan_pure(payload, patterns) -> CanaryResult` stdlib-only pure core, plus a Hypothesis property `canary-fires-past-truncation` proving the scan covers bytes far beyond the largest source-kind cap, plus a unit corpus where each payload-pattern pair asserts a specific `pattern_id` fires.

## Acceptance criteria

- [ ] **AC-1 — Module location.** `src/codegenie/fallback/fence/canary.py` exists. Fence test green.
- [ ] **AC-2 — `INJECTION_PATTERNS` is `Final[tuple[bytes, ...]]`.** At least 50 entries. Each is a `(pattern_id: str, pattern: bytes)` tuple — concretely, the dict shape is `INJECTION_PATTERNS: Final[tuple[tuple[str, bytes], ...]] = (...)`. Pattern IDs match `^[a-z][a-z0-9_]*$` (matches existing Phase 0 / 1 warning-ID convention from `CLAUDE.md`). Includes at minimum the following pattern IDs (concrete bytes are implementer's curation, but the IDs must exist):
   - `ignore_previous_instructions`
   - `disregard_above`
   - `system_override`
   - `new_instructions`
   - `im_start_token` (`<|im_start|>` and variants)
   - `inst_token` (`[INST]` / `[/INST]`)
   - `tool_call_injection` (e.g., `<tool_call>` / `<function_call>`)
   - `prompt_leak_request` (e.g., `repeat the above`)
   - `role_override` (e.g., `you are now`, `your new role`)
   - `assistant_token` (`<|assistant|>`)
   - `developer_mode`
   - `jailbreak_dan`
   - `pretend_to_be`
   - `forget_instructions`
   - `output_above_in_full`
   - Plus 35+ additional patterns (red-team corpus + PromptInject-style + project-curated).
   Test asserts `len(INJECTION_PATTERNS) >= 50` and `len({pid for pid, _ in INJECTION_PATTERNS}) == len(INJECTION_PATTERNS)` (no duplicate IDs).
- [ ] **AC-3 — `scan_pure` is side-effect-free and stdlib-only.** Signature: `def scan_pure(payload: str, patterns: tuple[tuple[str, bytes], ...]) -> CanaryResult`. Encodes `payload` to UTF-8 bytes (lower-cased for case-insensitive scan — implementer's call; document either way), iterates patterns, returns `CanaryCollision(pattern_id=<first match>)` on first hit, else `CanaryClean()`. AST-walking test `tests/unit/fallback/test_scan_pure_no_side_effects.py` asserts no `.emit(`, no `open(`, no `os.`, no `subprocess.`, no `print(`, no `log.`, no `time.`, no `random.`, no `secrets.`.
- [ ] **AC-4 — `CanaryGuard.scan` is the classmethod/imperative-shell.** `class CanaryGuard: INJECTION_PATTERNS: Final[tuple[tuple[str, bytes], ...]] = (...); @classmethod def scan(cls, payload: str, nonce: HexNonce) -> CanaryResult: return scan_pure(payload, cls.INJECTION_PATTERNS)`. The `nonce` parameter is accepted to match the `Scanner` Protocol signature from S2-02; the production guard does not yet use it for nonce-collision detection (Phase 6+ may), but the parameter is present and `mypy --strict` clean. **Adds one nonce-collision pattern**: if `nonce` (as UTF-8 bytes) appears in `payload.encode("utf-8")`, return `CanaryCollision(pattern_id="nonce_collision")` — this defends against attackers who somehow leak / guess the nonce. The unit test seeds a payload containing the literal nonce string and asserts collision.
- [ ] **AC-5 — `Scanner` Protocol conformance.** `isinstance(CanaryGuard, Scanner)` is True (Protocol is `@runtime_checkable`); a `CanaryGuard()` instance can be passed to `FenceWrapper(scanner=CanaryGuard(), event_log=log)` (or `CanaryGuard` as a class — classmethod permits the latter; surface to implementer per Global Rule 11 — prefer instance-as-Scanner for symmetry with S2-02). Test asserts both `CanaryGuard()` and a no-op test stub satisfy `isinstance(..., Scanner)`.
- [ ] **AC-6 — Hypothesis property: scan fires past largest truncation cap.** `tests/property/test_canary_scan_untruncated.py` — `@given(prefix_kb=st.integers(min_value=17, max_value=64), pattern_idx=st.integers(0, len(INJECTION_PATTERNS) - 1))`: construct a payload `b"X" * (prefix_kb * 1024) + INJECTION_PATTERNS[pattern_idx][1]`; assert `scan_pure(payload.decode("utf-8", errors="ignore"), INJECTION_PATTERNS)` returns `CanaryCollision(pattern_id=INJECTION_PATTERNS[pattern_idx][0])`. 500+ runs. The byte count past the largest cap (16 KB `source_snippet`) ensures the pattern is in the "would-have-been-truncated" zone.
- [ ] **AC-7 — Adversarial: bypass-via-truncation test.** `tests/adversarial/test_canary_bypass_via_truncation.py` — table-driven over 5+ scenarios: payload is constructed as `b"BENIGN " * 4000 + b"\n" + INJECTION_PATTERN`; total length is exactly `source_snippet` cap + 200 bytes. Run through full `FenceWrapper.fence(..., source_kind="source_snippet")` (S2-02 shell) with `CanaryGuard()` as the scanner. Assert (i) the returned `FencedSegment.canary_fired is True`, (ii) the emitted event is `CanaryCollision(source_kind="source_snippet", pattern_id=<expected>)`, (iii) the segment body is `<<redacted: canary collision>>` (S2-02 fence_pure handles the redaction step). This is the **end-to-end proof** of the critic-fix ordering — running through the truncate path with injection past the cap.
- [ ] **AC-8 — Curated unit corpus (50+ payloads).** `tests/unit/fallback/test_canary_corpus.py` — parametrized over 50+ `(payload_str, expected_pattern_id)` rows. Each row asserts `CanaryGuard.scan(payload_str, nonce=HexNonce("0" * 32)).kind == "collision"` (or equivalent CanaryResult shape) AND `pattern_id == expected_pattern_id`. **Each curated payload must be drawn from a real injection corpus** — not synthetic dictionary words — and the test docstring cites the source (PromptInject dataset, OWASP LLM Top 10 examples, red-team papers, project-internal red-teamed payloads). The corpus is the documented seed; S7-09 grows it to 200+.
- [ ] **AC-9 — Clean payloads pass.** `tests/unit/fallback/test_canary_clean_corpus.py` — 20+ benign payloads (CVE descriptions, package metadata blurbs, source snippets containing imports / function bodies, README excerpts) assert `CanaryGuard.scan(...) == CanaryClean()`. **No false positives** on the clean set. If any pattern in `INJECTION_PATTERNS` causes a clean-corpus row to fail, that pattern is too broad — narrow the bytes OR drop the row.
- [ ] **AC-10 — Nonce-collision detection.** Unit test: construct `payload = f"some text {HexNonce('a' * 32)} more text"`; call `CanaryGuard.scan(payload, nonce=HexNonce('a' * 32))`; assert `CanaryCollision(pattern_id="nonce_collision")`. Asserts AC-4's nonce-aware behavior.
- [ ] **AC-11 — Event-kind: `CanaryCollision` already registered in S2-02.** No additional event-kind registration needed in this story; the S2-02 `FenceWrapper` consumes `CanaryResult` and emits the event.
- [ ] **AC-12 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean.

## Implementation outline

1. **Read S2-02 outputs**: `Scanner` Protocol, `CanaryResult` sum type, `FencedSegment` shape, the existing `_AlwaysCleanScanner` test double. Import `CanaryResult` / `CanaryClean` / `CanaryCollision` from `codegenie.fallback.fence.wrapper`.
2. **Curate `INJECTION_PATTERNS`**: 50+ rows, each `(pattern_id, bytes_pattern)`. Source list mix:
   - 15 from PromptInject-style "ignore previous instructions" variants.
   - 10 from OpenAI/Anthropic role-token leak attempts (`<|im_start|>`, `<|im_end|>`, `[INST]`, `<|assistant|>`).
   - 10 from jailbreak corpus (DAN-style, "developer mode", "pretend to be").
   - 10 from tool-call / function-call injection (`<tool_call>`, `<function_call>`, `<execute>`).
   - 5 from project-curated (Phase 4 red-team session payloads).
3. **Implement `scan_pure`** as a top-level pure function:
   ```python
   def scan_pure(payload: str, patterns: tuple[tuple[str, bytes], ...]) -> CanaryResult:
       lowered = payload.encode("utf-8").lower()
       for pid, pat in patterns:
           if pat.lower() in lowered:
               return CanaryCollision(pattern_id=pid)
       return CanaryClean()
   ```
   (Case-insensitivity is a design call — document it; attackers can mix case trivially. If case-sensitive scanning is preferred per a specific pattern's intent, encode that into the pattern itself rather than a per-row flag.)
4. **Implement `CanaryGuard`** as a class with classmethod `scan`. The nonce-collision check happens **before** the pattern loop (cheap; high-signal):
   ```python
   @classmethod
   def scan(cls, payload: str, nonce: HexNonce) -> CanaryResult:
       if nonce.encode("ascii") in payload.encode("utf-8"):
           return CanaryCollision(pattern_id="nonce_collision")
       return scan_pure(payload, cls.INJECTION_PATTERNS)
   ```
5. **Write tests** red-first.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/property/test_canary_scan_untruncated.py
from __future__ import annotations

from hypothesis import given, settings, strategies as st

from codegenie.fallback.fence.canary import INJECTION_PATTERNS, scan_pure
from codegenie.fallback.fence.wrapper import CanaryCollision


@given(
    prefix_kb=st.integers(min_value=17, max_value=64),  # past source_snippet 16 KB cap
    pattern_idx=st.integers(min_value=0, max_value=len(INJECTION_PATTERNS) - 1),
)
@settings(max_examples=500, deadline=None)
def test_pattern_hidden_past_largest_cap_is_still_detected(
    prefix_kb: int, pattern_idx: int
) -> None:
    pid, pat = INJECTION_PATTERNS[pattern_idx]
    payload_bytes = b"X" * (prefix_kb * 1024) + pat
    payload = payload_bytes.decode("utf-8", errors="ignore")
    result = scan_pure(payload, INJECTION_PATTERNS)
    assert isinstance(result, CanaryCollision)
    assert result.pattern_id == pid
```

```python
# tests/adversarial/test_canary_bypass_via_truncation.py
from __future__ import annotations

import pytest

from codegenie.audit import EventLog
from codegenie.fallback.fence.canary import CanaryGuard
from codegenie.fallback.fence.wrapper import FenceWrapper
from codegenie.types.identifiers import HexNonce


SOURCE_SNIPPET_CAP = 16 * 1024


@pytest.mark.parametrize(
    "pattern_bytes, expected_pid",
    [
        (b"ignore previous instructions", "ignore_previous_instructions"),
        (b"<|im_start|>system", "im_start_token"),
        (b"[INST] You are now", "inst_token"),
        (b"system_override:", "system_override"),
        (b"<tool_call>", "tool_call_injection"),
    ],
)
def test_injection_past_truncation_cap_is_caught_by_fence_wrapper(
    pattern_bytes: bytes, expected_pid: str
) -> None:
    benign = b"BENIGN " * (SOURCE_SNIPPET_CAP // 7)
    payload_bytes = benign + b"\n" + pattern_bytes
    assert len(payload_bytes) > SOURCE_SNIPPET_CAP
    payload = payload_bytes.decode("utf-8", errors="ignore")

    fixed_nonce = HexNonce("0" * 32)
    log = EventLog()
    fence = FenceWrapper(
        scanner=CanaryGuard(),
        event_log=log,
        nonce_source=lambda: fixed_nonce,
    )

    segment = fence.fence(payload, source_kind="source_snippet")

    assert segment.canary_fired is True
    body = segment.content.removeprefix(
        f"<UNTRUSTED_INPUT id={fixed_nonce}>"
    ).removesuffix(f"</UNTRUSTED_INPUT id={fixed_nonce}>")
    assert body == "<<redacted: canary collision>>"

    collisions = [e for e in log.events if type(e).__name__ == "CanaryCollision"]
    assert len(collisions) == 1
    assert collisions[0].pattern_id == expected_pid
    assert collisions[0].source_kind == "source_snippet"
```

Run; expect `ModuleNotFoundError: codegenie.fallback.fence.canary`.

### Green — make it pass

Implement `canary.py`. Curate the corpus. Wire `CanaryGuard.scan` to invoke `scan_pure` after the nonce-collision check.

### Refactor — clean up

- Group patterns by category in the source (comments separating "role-token injection", "ignore-instruction variants", "jailbreak corpus", etc.).
- Add a per-category count assertion in `test_canary_corpus.py` (e.g., "at least 5 role-token patterns") so accidentally trimming a category fails the corpus test.
- Verify `scan_pure` is one screen of code.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/fence/canary.py` | `INJECTION_PATTERNS`, `scan_pure`, `CanaryGuard` class. |
| `tests/unit/fallback/test_canary.py` | AC-2 (corpus size + ID-uniqueness), AC-4 (CanaryGuard.scan), AC-5 (Scanner conformance), AC-10 (nonce-collision). |
| `tests/unit/fallback/test_scan_pure_no_side_effects.py` | AC-3 AST-walking test. |
| `tests/unit/fallback/test_canary_corpus.py` | AC-8 — 50+ curated injection payloads. |
| `tests/unit/fallback/test_canary_clean_corpus.py` | AC-9 — 20+ benign payloads pass clean. |
| `tests/property/test_canary_scan_untruncated.py` | AC-6 Hypothesis property. |
| `tests/adversarial/test_canary_bypass_via_truncation.py` | AC-7 end-to-end critic-fix test. |

## Out of scope

- The 200+ adversarial corpus (`tests/adversarial/test_injection_corpus.py`) — S7-09.
- Probabilistic / ML-based injection classifier — Phase 13+ explicitly out of scope per ADR-0013 §Options considered.
- Pattern hot-reload — by-design forbidden per ADR-0013 §Tradeoffs row 6 (patterns frozen at module load).
- Per-source-kind pattern subsetting (e.g., only scan `source_snippet` for tool-call tokens) — single corpus for now; ADR-0013 §Tradeoffs row 4 calls this a future-work mitigation against false positives.
- `red_team_prompts` adversarial scenarios (50+ end-to-end red-team flows) — S7-09.
- `PromptBuilder` integration — S2-04.

## Notes for the implementer

- **Critic-fix reminder.** ADR-0013's load-bearing decision is "scan untruncated, then truncate." S2-02's `fence_pure` is structured around this; this story's `CanaryGuard.scan` is the scanner that runs against the **full** payload, which `fence_pure` then truncates only if scan returns clean (or replaces with redaction if collision). AC-6 (Hypothesis past-the-cap) + AC-7 (adversarial end-to-end) are the load-bearing tests. If either fails, the implementation is wrong — do not weaken the test.
- **Case-insensitivity is a design call.** Lowercasing both pattern and payload is the simplest robust scan. Document. If a future pattern needs case-sensitivity (none in the seed corpus does), encode it in the pattern itself (e.g., add `"<|IM_START|>"` as a separate row). Resist a per-row case-flag — primitive obsession on the pattern shape.
- **Bytes vs str.** `INJECTION_PATTERNS` is `bytes` (Pydantic-friendly, encoding-explicit); `scan_pure` accepts `str` (the prompt-shaped surface) and encodes internally. Mixing the boundary causes UnicodeDecodeError surprises — pinning to "bytes inside, str outside" is the convention.
- **Honest framing — denylist incompleteness.** ADR-0013 §Context: "the claim cannot be 'injection-proof'; the claim must be 'every byte is fenced + every collision is loud.'" Do not write tests or comments that imply canary catches all injection. The right framing is "canary catches `INJECTION_PATTERNS`; the corpus grows; fencing + nonce-uniqueness are the structural guarantees."
- **`pattern_id` is a stable identifier.** Once registered, do not rename — operator-portal dashboards key on it. Adding a pattern is additive; renaming is an ADR amendment.
- **Cross-cutting reminder — Newtypes.** `HexNonce` is `NewType(str)` from S1-01 — accept it as `HexNonce`, not `str`. The nonce-collision check encodes it as ASCII (32 hex chars are ASCII-safe).
- **Cross-cutting reminder — zero LLM tokens.** This story has no `BudgetToken`. Canary scanning happens deterministically in-process, before any LLM call.
- **No `re`, no regex.** Substring search (`pat in payload_bytes`) is enough. Regex is overkill, slower, and the patterns are concrete byte strings. If regex temptation arises, surface to validator per Global Rule 7.
- **Performance envelope.** ADR-0013 §Tradeoffs row 1: ~1 ms / 16 KB. The implementation is `O(N × P)` where N=payload size, P=pattern count. With 50 patterns × 16 KB × ~ns per byte, the budget holds comfortably. No `bench` test required; sanity-check with `pytest --durations=10` on the corpus test.
