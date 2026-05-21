# Story S2-03 — CanaryGuard scan-before-truncate + INJECTION_PATTERNS corpus

**Step:** Step 2 — Ship trust-boundary primitives: ProvenanceGate, FenceWrapper/CanaryGuard/PromptBuilder, LlmInvocationGuard/BudgetToken
**Status:** HARDENED
**Effort:** M
**Depends on:** S2-02 (`Scanner` Protocol + `CanaryResult` sum type live in `src/codegenie/fallback/fence/wrapper.py` — this story implements the Protocol)
**ADRs honored:** ADR-0013 (scan-untruncated-first ordering + the `INJECTION_PATTERNS` frozen-`Final`-tuple convention + denylist-acknowledged-incomplete framing, this phase — the ADR's literal `tuple[bytes, ...]` is necessarily refined to `tuple[tuple[str, bytes], ...]`; see Validation note V2), ADR-0003 (path-scoped fence — module under `src/codegenie/fallback/fence/`, this phase)

## Validation notes

**Validated:** 2026-05-21 — verdict **HARDENED** (phase-story-validator). Full report: `_validation/S2-03-canary-guard-scan-untruncated.md`.

Blocking fixes applied:
- **V1 — stale event API.** The TDD plan imported `from codegenie.audit import EventLog`, constructed `EventLog()` with no args, and read `log.events`. None exist — `codegenie.audit` ships the gather-pipeline `AuditWriter`, not an `EventLog`. The real log is `codegenie.plugins.events.EventLog(root, workflow_id)`, written via `emit_internal` and read via `replay()`. This is the exact mistake S2-02 was hardened against. AC-7 and its TDD code now use the real API.
- **V2 — `INJECTION_PATTERNS` shape vs ADR-0013.** ADR-0013 and the arch literally say `Final[tuple[bytes, ...]]`, but a flat bytes tuple cannot supply the `pattern_id` that the ADR's own `CanaryCollision(pattern_id=...)` requires. The `(pattern_id, bytes)` pair shape is a *necessary* refinement; the story now states the deviation explicitly instead of falsely claiming to honor the literal flat-tuple type.
- **V3 — AC-7 byte arithmetic.** The adversarial test placed the injection starting at byte 16 381 — three bytes *inside* the 16 KB cap — so it never proved "injection fully past truncation is caught" (the load-bearing ADR-0013 critic-fix). Filler length corrected so the entire pattern sits past the cap; the contradictory prose ("× 4000", "exactly cap + 200 bytes") reconciled with the code.
- **V4 — pattern shadowing / duplicate bytes.** AC-2 only checked ID uniqueness. Under `scan_pure`'s first-match semantics, a duplicate-bytes or substring-shadowed pattern is unreachable and silently breaks AC-6/AC-8's `expected_pattern_id` guarantees — and makes the refactor-step reorder unsafe. AC-2 now enforces unique bytes, non-empty bytes, valid-UTF-8 bytes, and no-substring-shadowing as import-time structural invariants.
- **V5 — unwritable per-category test.** The refactor step asked for a "per-category count assertion" against a flat tuple with no category field. Replaced with a concrete, writable guard: every one of AC-2's 15 mandated pattern IDs must exist and carry ≥1 corpus row (AC-8).

Hardening: AC-2 promoted to import-time validation via a pure `_validate_patterns` helper (warning-ID-convention style); AC-3 purity test switched denylist→allowlist; AC-5 pinned the `CanaryGuard()` instance as the sole `Scanner`; AC-7 asserts the `segment.canary` sum type instead of string-surgery on `content`; the dual-`CanaryCollision` namespace (sum-type variant vs audit event) disambiguated (**V6**); the adversarial test relocated `tests/adversarial/` → `tests/adv/` to match codebase reality. Original goal and scope unchanged.

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

- [ ] **AC-1 — Module location.** `src/codegenie/fallback/fence/canary.py` exists. The Phase-4 path-scoped fence test `tests/fence/test_pyproject_fence_phase4.py` (ADR-0003, S1-05) stays green with the new module in the `src/codegenie/fallback/` tree.
- [ ] **AC-2 — `INJECTION_PATTERNS` is a frozen `Final` tuple, structurally validated at import.** `INJECTION_PATTERNS: Final[tuple[tuple[str, bytes], ...]] = (...)` — at least 50 entries, each a `(pattern_id: str, pattern: bytes)` pair. (This `(pattern_id, bytes)` shape is the necessary refinement of ADR-0013's literal `tuple[bytes, ...]` — a flat bytes tuple cannot supply the `pattern_id` that `CanaryCollision(pattern_id=...)` carries; see Validation note V2.) The corpus is checked by a **pure** `_validate_patterns(patterns) -> None` helper invoked at module import — `_validate_patterns(INJECTION_PATTERNS)` runs at load time and `raise AssertionError(...)` (bare `assert` is forbidden by the `forbidden-patterns` hook) on any violation of:
   1. `len(patterns) >= 50`.
   2. **Unique IDs** — `len({pid for pid, _ in patterns}) == len(patterns)`.
   3. **Unique bytes** — `len({pat for _, pat in patterns}) == len(patterns)`. A duplicate-bytes row is unreachable under `scan_pure`'s first-match semantics.
   4. **ID shape** — every `pattern_id` matches `^[a-z][a-z0-9_]*$` (the Phase 0/1 warning-ID convention from `CLAUDE.md`).
   5. **Non-empty bytes** — `all(len(pat) > 0 for _, pat in patterns)`. `b"" in anything` is always `True`; an empty pattern would collide on every payload.
   6. **Valid-UTF-8 bytes** — every `pattern` round-trips through `.decode("utf-8")`. `scan_pure` receives a `str` payload and encodes it UTF-8; a pattern whose bytes are not valid UTF-8 can never match and is dead code.
   7. **No substring shadowing** — no pattern's lower-cased bytes is a substring of another pattern's lower-cased bytes. Shadowing makes the shadowed pattern's `pattern_id` unreportable under first-match and breaks AC-6/AC-8 determinism.
   Includes at minimum the following 15 pattern IDs (concrete bytes are implementer's curation, but the IDs must exist — AC-8 asserts each has a corpus row):
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
   `tests/unit/fallback/test_canary.py` asserts: (i) `_validate_patterns(INJECTION_PATTERNS)` does not raise; (ii) `_validate_patterns` *does* `raise AssertionError` once for **each** violation class above, fed a deliberately-bad tuple per class (a duplicate-ID tuple, a duplicate-bytes tuple, a `("BadID", b"x")` tuple, a `("ok", b"")` tuple, a non-UTF-8-bytes tuple, a substring-shadowed pair, an under-50 tuple) — a single catch-all assertion is not sufficient; (iii) all 15 mandated IDs are present in `INJECTION_PATTERNS`.
- [ ] **AC-3 — `scan_pure` is side-effect-free and stdlib-only.** Signature: `def scan_pure(payload: str, patterns: tuple[tuple[str, bytes], ...]) -> CanaryResult`. Encodes `payload` to UTF-8 bytes (case-folded via `bytes.lower()` for a case-insensitive scan — document the choice in the docstring), iterates patterns, returns `CanaryCollision(pattern_id=<first match>)` on first hit, else `CanaryClean()`. `scan_pure("", patterns)` returns `CanaryClean()` — `tests/unit/fallback/test_scan_pure_no_side_effects.py` includes an explicit empty-payload row. The purity test uses an **allowlist** AST walk, not a denylist (mirroring the hardened S2-02 `fence_pure` purity test — a denylist silently passes any impure call nobody enumerated): it walks every `ast.Call` node inside `scan_pure` and asserts each resolves to the explicit allowlist for this function (`.encode`, `.lower`, `len`, and the `CanaryClean`/`CanaryCollision` constructors). Any call outside the allowlist fails the test. `_validate_patterns` (AC-2) must likewise be pure (no I/O); it may use `re.match` for the import-time `pattern_id`-shape check — that is *not* the payload scan path the "no regex" Note forbids.
- [ ] **AC-4 — `CanaryGuard.scan` is the classmethod/imperative-shell.** `class CanaryGuard: INJECTION_PATTERNS: Final[tuple[tuple[str, bytes], ...]] = (...); @classmethod def scan(cls, payload: str, nonce: HexNonce) -> CanaryResult: return scan_pure(payload, cls.INJECTION_PATTERNS)`. The `nonce` parameter is accepted to match the `Scanner` Protocol signature from S2-02; the production guard does not yet use it for nonce-collision detection (Phase 6+ may), but the parameter is present and `mypy --strict` clean. **Adds one nonce-collision pattern**: if `nonce` (as UTF-8 bytes) appears in `payload.encode("utf-8")`, return `CanaryCollision(pattern_id="nonce_collision")` — this defends against attackers who somehow leak / guess the nonce. The unit test seeds a payload containing the literal nonce string and asserts collision.
- [ ] **AC-5 — `Scanner` Protocol conformance — the instance is the canonical `Scanner`.** A `CanaryGuard()` **instance** is the object that satisfies S2-02's `@runtime_checkable Scanner` Protocol and is passed as `FenceWrapper(scanner=CanaryGuard(), ...)`. Test asserts `isinstance(CanaryGuard(), Scanner) is True` and that a no-op test stub also satisfies `isinstance(..., Scanner)`. Do **not** specify the class object `CanaryGuard` itself as a `Scanner` — pin exactly one contract (the instance) so downstream code never has to handle both. `scan` stays a `@classmethod` per `phase-arch-design.md §Component 3` (so `INJECTION_PATTERNS` is reached via `cls`); a classmethod is fully callable on an instance, so this does not weaken the instance-as-`Scanner` pin — the classmethod is an implementation detail, not a second public contract.
- [ ] **AC-6 — Hypothesis property: scan fires past largest truncation cap.** `tests/property/test_canary_scan_untruncated.py` — `@given(prefix_kb=st.integers(min_value=17, max_value=64), pattern_idx=st.integers(0, len(INJECTION_PATTERNS) - 1))`: construct a payload `b"X" * (prefix_kb * 1024) + INJECTION_PATTERNS[pattern_idx][1]`; assert `scan_pure(payload.decode("utf-8", errors="ignore"), INJECTION_PATTERNS)` returns a `CanaryCollision` whose `pattern_id == INJECTION_PATTERNS[pattern_idx][0]`. 500+ runs. The byte count past the largest cap (16 KB `source_snippet`) ensures the pattern is in the "would-have-been-truncated" zone. Asserting the **exact** `pattern_id` (not merely `isinstance(result, CanaryCollision)`) means this property *also* enforces AC-2's no-substring-shadowing invariant: if pattern *idx* were shadowed by an earlier entry, `scan_pure` would return the earlier id and the property would fail. That is intended — **if AC-6 fails with an id mismatch, the bug is a shadowed corpus entry (fix AC-2's corpus); never weaken this assertion.** The `b"X"` filler must contain no injection-pattern bytes (true for the seed corpus — no pattern is `x`-only; AC-2's non-empty + real-corpus invariants keep it true).
- [ ] **AC-7 — Adversarial: bypass-via-truncation test.** `tests/adv/test_canary_bypass_via_truncation.py`, marked `@pytest.mark.adv` (the arch §Adversarial calls this suite `-m adv`; the file lives under the codebase's established `tests/adv/` root — **not** the arch doc's `tests/adversarial/`, which does not exist; see Validation note V6). Table-driven over 5+ scenarios. Construct the payload so the injection pattern sits **entirely past** the 16 KB `source_snippet` cap: `benign = b"BENIGN " * 3000` (= 21 000 bytes), then `payload_bytes = benign + b"\n" + INJECTION_PATTERN`. Assert `len(benign) >= SOURCE_SNIPPET_CAP` so every byte of the injection is in the "would-have-been-truncated" zone — this is what makes the test a real proof of the scan-untruncated-first ordering, rather than a payload whose first few injection bytes survive truncation anyway. Run through `FenceWrapper.fence(payload, source_kind="source_snippet")` (S2-02 shell) with a `CanaryGuard()` instance scanner. Assert:
   - (i) `segment.canary_fired is True`.
   - (ii) `isinstance(segment.canary, CanaryCollision)` **and** `segment.canary.pattern_id == expected_pid` — assert the `CanaryResult` sum type S2-02 exposes on `FencedSegment`, **not** by re-deriving S2-02's delimiter byte format with `removeprefix`/`removesuffix` (brittle cross-story coupling).
   - (iii) `"<<redacted: canary collision>>" in segment.content` — a loose containment check; the exact delimiter framing is S2-02's tested concern.
   - (iv) `FenceWrapper` emitted exactly one `CanaryCollision` **audit event** with `source_kind == "source_snippet"` and `pattern_id == expected_pid`. Read events via `EventLog.replay()`. Per the dual-`CanaryCollision` namespace (Validation note V6), the audit event is `codegenie.plugins.events.CanaryCollision` — import it aliased (`from codegenie.plugins.events import CanaryCollision as CanaryCollisionEvent`) and assert `isinstance(e, CanaryCollisionEvent)`, never `type(e).__name__ == "CanaryCollision"` (which would also match the same-named `CanaryResult` variant).
   This is the **end-to-end proof** of the critic-fix ordering — injection fully past the cap, caught by the untruncated scan.
- [ ] **AC-8 — Curated unit corpus (50+ payloads).** `tests/unit/fallback/test_canary_corpus.py` — parametrized over 50+ `(payload_str, expected_pattern_id)` rows. Each row asserts `CanaryGuard().scan(payload_str, nonce=HexNonce("0" * 32))` is a `CanaryCollision` with `kind == "collision"` AND `pattern_id == expected_pattern_id`. Each row's `expected_pattern_id` is deterministic *only because* AC-2's no-substring-shadowing invariant holds — without it, first-match could report a different id; do not pin a corpus row whose payload matches more than one pattern. **Each curated payload must be drawn from a real injection corpus** — not synthetic dictionary words — and the module docstring cites the sources (PromptInject dataset, OWASP LLM Top 10 examples, red-team papers, project-internal red-teamed payloads). The test also asserts **every one of AC-2's 15 mandated pattern IDs appears as the `expected_pattern_id` of at least one corpus row** — this replaces the (unwritable, against a flat tuple) "per-category count assertion" from the original refactor step and is the regression guard against silently dropping a load-bearing pattern. The corpus is the documented seed; S7-09 grows it to 200+.
- [ ] **AC-9 — Clean payloads pass.** `tests/unit/fallback/test_canary_clean_corpus.py` — 20+ benign payloads (CVE descriptions, package metadata blurbs, source snippets containing imports / function bodies, README excerpts) assert `CanaryGuard().scan(payload, nonce=HexNonce("0" * 32)) == CanaryClean()`. The nonce is the fixed benign `"0" * 32`; benign payloads must not contain that 32-character run (trivially true for prose). At least one clean row is a deliberate **near-miss** — e.g. a CVE description that benignly contains the word `instructions`, or quotes a security advisory *about* prompt injection — so the clean corpus actively pressures pattern over-breadth rather than passing trivially. **No false positives** on the clean set. If any pattern in `INJECTION_PATTERNS` causes a clean-corpus row to fail, that pattern is too broad — narrow the bytes OR drop the row.
- [ ] **AC-10 — Nonce-collision detection.** Unit test: construct `payload = f"some text {HexNonce('a' * 32)} more text"`; call `CanaryGuard.scan(payload, nonce=HexNonce('a' * 32))`; assert `CanaryCollision(pattern_id="nonce_collision")`. Asserts AC-4's nonce-aware behavior.
- [ ] **AC-11 — Audit event already registered in S2-02.** The `CanaryCollision` **`WorkflowInternalEvent`** (in `codegenie.plugins.events`, carrying `source_kind` + `pattern_id`) is wired into the `WorkflowInternalEvent` union + `_INTERNAL_CLASSES` tuple by S2-02 — no event registration in this story. This is a *distinct* class from the `CanaryCollision` `CanaryResult` variant (in `codegenie.fallback.fence.wrapper`, carrying `pattern_id` only) that `scan_pure` returns; the two share a name but live in different modules and carry different fields (Validation note V6). The S2-02 `FenceWrapper` consumes the `CanaryResult` and emits the audit event.
- [ ] **AC-12 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean.

## Implementation outline

1. **Read S2-02 outputs**: `Scanner` Protocol, `CanaryResult` sum type, `FencedSegment` shape, the existing `_AlwaysCleanScanner` test double. Import `CanaryResult` / `CanaryClean` / `CanaryCollision` from `codegenie.fallback.fence.wrapper`.
2. **Curate `INJECTION_PATTERNS`**: 50+ rows, each `(pattern_id, bytes_pattern)`. Source list mix:
   - 15 from PromptInject-style "ignore previous instructions" variants.
   - 10 from OpenAI/Anthropic role-token leak attempts (`<|im_start|>`, `<|im_end|>`, `[INST]`, `<|assistant|>`).
   - 10 from jailbreak corpus (DAN-style, "developer mode", "pretend to be").
   - 10 from tool-call / function-call injection (`<tool_call>`, `<function_call>`, `<execute>`).
   - 5 from project-curated (Phase 4 red-team session payloads).
   Curate so no pattern's bytes is a substring of another's (ship `disregard_above` as a distinct phrase, not as a prefix of a longer row). Then write the pure `_validate_patterns(patterns) -> None` helper (AC-2) and **call it at module import** — `_validate_patterns(INJECTION_PATTERNS)` — so a malformed corpus (duplicate id/bytes, bad id shape, empty/non-UTF-8 bytes, substring shadowing, under-50 count) fails loud at import, exactly as the warning-ID convention does.
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
# tests/adv/test_canary_bypass_via_truncation.py
from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.fallback.fence.canary import CanaryGuard
from codegenie.fallback.fence.wrapper import CanaryCollision, FenceWrapper
from codegenie.plugins.events import CanaryCollision as CanaryCollisionEvent
from codegenie.plugins.events import EventLog
from codegenie.types.identifiers import HexNonce, WorkflowId


SOURCE_SNIPPET_CAP = 16 * 1024


@pytest.mark.adv
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
    tmp_path: Path, pattern_bytes: bytes, expected_pid: str
) -> None:
    # The filler alone exceeds the cap, so the *entire* injection sits past it.
    benign = b"BENIGN " * 3000  # 21_000 bytes
    assert len(benign) >= SOURCE_SNIPPET_CAP
    payload_bytes = benign + b"\n" + pattern_bytes
    payload = payload_bytes.decode("utf-8", errors="ignore")

    fixed_nonce = HexNonce("0" * 32)
    log = EventLog(tmp_path, WorkflowId("wf-canary-test"))
    fence = FenceWrapper(
        scanner=CanaryGuard(),
        event_log=log,
        nonce_source=lambda: fixed_nonce,
    )

    segment = fence.fence(payload, source_kind="source_snippet")

    assert segment.canary_fired is True
    assert isinstance(segment.canary, CanaryCollision)
    assert segment.canary.pattern_id == expected_pid
    assert "<<redacted: canary collision>>" in segment.content

    collisions = [e for e in log.replay() if isinstance(e, CanaryCollisionEvent)]
    assert len(collisions) == 1
    assert collisions[0].pattern_id == expected_pid
    assert collisions[0].source_kind == "source_snippet"
```

Run; expect `ModuleNotFoundError: codegenie.fallback.fence.canary`.

### Green — make it pass

Implement `canary.py`. Curate the corpus. Wire `CanaryGuard.scan` to invoke `scan_pure` after the nonce-collision check.

### Refactor — clean up

- Group patterns by category in the source (comments separating "role-token injection", "ignore-instruction variants", "jailbreak corpus", etc.). The grouping is **organisational only** — `INJECTION_PATTERNS` stays a flat `tuple[tuple[str, bytes], ...]`; category is not a data field, so do not write a category-count test against it. The regression guard against silently dropping a load-bearing pattern is AC-8's "all 15 mandated IDs have a corpus row" assertion, which works against the flat tuple. (If finer per-category coverage is wanted later, see the `InjectionPattern` NamedTuple note in *Notes for the implementer* — out of scope here.)
- After any reorder, re-confirm `_validate_patterns(INJECTION_PATTERNS)` still passes: the no-substring-shadowing invariant (AC-2) is what makes reordering safe for AC-6/AC-8.
- Verify `scan_pure` is one screen of code.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/fence/canary.py` | `INJECTION_PATTERNS`, `_validate_patterns` (pure; called at module import), `scan_pure`, `CanaryGuard` class. |
| `tests/unit/fallback/test_canary.py` | AC-2 (`_validate_patterns` accepts the real corpus + rejects each violation class; all 15 mandated IDs present), AC-4 (`CanaryGuard.scan`), AC-5 (Scanner conformance — instance), AC-10 (nonce-collision). |
| `tests/unit/fallback/test_scan_pure_no_side_effects.py` | AC-3 allowlist AST-walk + empty-payload row. |
| `tests/unit/fallback/test_canary_corpus.py` | AC-8 — 50+ curated injection payloads + all-15-mandated-IDs-have-a-row. |
| `tests/unit/fallback/test_canary_clean_corpus.py` | AC-9 — 20+ benign payloads (incl. a near-miss) pass clean. |
| `tests/property/test_canary_scan_untruncated.py` | AC-6 Hypothesis property. |
| `tests/adv/test_canary_bypass_via_truncation.py` | AC-7 end-to-end critic-fix test (`@pytest.mark.adv`). |

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
- **No `re`, no regex in the scan path.** Substring search (`pat in payload_bytes`) is enough for `scan_pure`. Regex is overkill, slower, and the patterns are concrete byte strings. (`_validate_patterns` may use `re.match` for the import-time `pattern_id`-shape check — that is the warning-ID convention, not the payload scan.) If regex temptation arises in the scan, surface to validator per Global Rule 7.
- **Performance envelope.** ADR-0013 §Tradeoffs row 1: ~1 ms / 16 KB. The implementation is `O(N × P)` where N=payload size, P=pattern count. With 50 patterns × 16 KB × ~ns per byte, the budget holds comfortably. No `bench` test required; sanity-check with `pytest --durations=10` on the corpus test.
- **Event log is `codegenie.plugins.events.EventLog` — not `codegenie.audit`.** `codegenie.audit` has no `EventLog` (it ships the gather-pipeline `AuditWriter`). Construct as `EventLog(root_path, WorkflowId(...))` — both args required, no no-arg form; write via `emit_internal`, read via `replay()`; there is no `.events` attribute. This is the exact stale-API mistake S2-02 was hardened against — do not reintroduce it.
- **Two classes named `CanaryCollision`.** The `CanaryResult` sum-type variant (`codegenie.fallback.fence.wrapper`, `pattern_id` only) is what `scan_pure` / `CanaryGuard.scan` return. The `WorkflowInternalEvent` audit class (`codegenie.plugins.events`, `source_kind` + `pattern_id`) is what `FenceWrapper` emits. Same name, different modules, different shape. Always import the event aliased and assert with `isinstance`, never by `__name__` string. Surface to validator if S2-02's shipped code lets the two collide in a single import scope.
- **`pattern_id` stays a validated `str`, not a newtype.** S2-02's validation deferred the `CanaryPatternId`-newtype question to this story. Resolution: pattern IDs follow the repo's *warning-ID convention* — a `str` matching `^[a-z][a-z0-9_]*$`, validated against module-level `Final` data (here, `_validate_patterns`). That is the established Phase-0/1 convention (`_WARNING_IDS`); minting a newtype would drag the full `identifiers.py` `__all__`/registry/fence reconciliation onto this story for a field whose stability is already enforced by "the catalog is `Final` + an id is never renamed". Do **not** introduce `CanaryPatternId`.
- **`INJECTION_PATTERNS` row shape — the flat 2-tuple is fine; a `NamedTuple` is an acceptable readability upgrade.** The story prescribes `tuple[tuple[str, bytes], ...]` and indexes it positionally (`[idx][0]`/`[idx][1]`). If the positional indexing reads poorly to you, a frozen `class InjectionPattern(NamedTuple): pattern_id: str; pattern: bytes` is a zero-cost win (named fields, no abstraction or indirection added) and preserves every AC's semantics — `scan_pure`'s signature becomes `tuple[InjectionPattern, ...]`. This is *optional*. Do **not** add a `category` field or any registry/dispatch machinery — the catalog is iterated, never dispatched on (Rule 2).
- **Adversarial test directory.** `phase-arch-design.md §Adversarial` says `tests/adversarial/`; that directory does not exist. The codebase's adversarial tests live under `tests/adv/` (Phase 1 directly; Phase 2 in `tests/adv/phase02/`). Ship `tests/adv/test_canary_bypass_via_truncation.py` with `@pytest.mark.adv`. Correcting the arch doc's stale path is a separate doc-fix, not this story's scope.
- **Confirm S2-02's surface before relying on it.** AC-7's test assumes `FenceWrapper.__init__` kwargs `scanner=`, `event_log=`, `nonce_source=` and that `FencedSegment` exposes `.canary` / `.canary_fired` / `.content`. These are S2-02's (HARDENED — read `_validation/S2-02-fence-wrapper.md` and the shipped `wrapper.py` first; adjust the test if a name differs).
