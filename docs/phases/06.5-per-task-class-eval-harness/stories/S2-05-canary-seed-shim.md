# Story S2-05 — Canary seed thread-local shim + Phase 4 `Canary.mint(seed=...)` amendment

**Step:** Step 2 — Build harness internals: loader, cache, audit chain extension, canary + cost-tag shims
**Status:** Ready
**Effort:** S
**Depends on:** S1-02
**ADRs honored:** ADR-0005 (cassette canary-seed parameterization), Phase 4 final-design `ADR-P4-006` (additive `Canary.mint(seed=...)` kwarg)

## Context

Phase 4 ships cassette-based replay keyed on `(model_id, sdk_minor, prompt_template_hash, canary_seed)`. Byte-for-byte replay across bench runs requires the canary be the **same** bytes; production's prompt-injection defense requires it be **different** per invocation. ADR-0005 resolves this with two changes: (1) `BenchCase.cassette_canary_pin: str` (32 hex chars, curated once per case) lives in `case.toml`; (2) Phase 4's `Canary.mint(...)` is amended additively to accept `seed: bytes | None = None` — when `None`, behavior is unchanged. `src/codegenie/eval/canary.py` exposes a `with_pinned_canary(case)` context manager that thread-locally injects `bytes.fromhex(case.cassette_canary_pin)` so `Canary.mint(...)` (called transitively from inside the SUT) sees the pinned seed for the duration of one `SUT.ainvoke(case)` call. This story lands the eval-side shim **and** the cross-phase Phase 4 amendment in the same commit train.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — src/codegenie/eval/canary.py` — public-interface signature, thread-local injection strategy, "prefer thread-local over monkey-patching"
  - `../phase-arch-design.md §Edge cases #6` — missing `cassette_canary_pin` → Pydantic rejection at `BenchCase` construction (no separate check in the shim)
  - `../phase-arch-design.md §Risks #4` — cross-phase amendment risk + mitigation (start amendment PR with this story)
- **Phase ADRs:**
  - `../ADRs/0005-cassette-canary-seed-parameterization.md` — full rationale, `ADR-P4-006-canary-seed-kwarg.md` is the Phase 4 amendment artifact drafted as part of this work; the bench-side shim and the Phase 4 kwarg ship together
- **Production ADRs:**
  - (None — this is a Phase 4 amendment, not a production-level decision)
- **Source design:**
  - `../final-design.md §Canary-token handling` — original synthesis
  - Phase 4 final-design (cassette key shape `(model_id, sdk_minor, prompt_template_hash, canary_seed)`)
- **Existing code:**
  - `src/codegenie/eval/models.py` (S1-02) — `BenchCase.cassette_canary_pin: str` (32 hex; validated at construction)
  - `src/codegenie/engines/canary.py` (Phase 4) — the `Canary.mint(...)` function this shim cooperates with; the additive `seed` kwarg lands here under ADR-P4-006

## Goal

`codegenie.eval.canary.with_pinned_canary(case)` is a context manager that thread-locally pins the 32-byte seed derived from `case.cassette_canary_pin`, so Phase 4's `Canary.mint(...)` (called from inside the SUT during one `await SUT.ainvoke(case)`) produces deterministic, byte-identical canary tokens across reruns; production callers (no `seed` passed) are unaffected.

## Acceptance criteria

- [ ] `with_pinned_canary(case: BenchCase) -> ContextManager[bytes]` is importable from `codegenie.eval.canary`; yields the 32-byte seed (`bytes.fromhex(case.cassette_canary_pin)`).
- [ ] The shim uses a `threading.local()` (or `contextvars.ContextVar` — see §Notes) to store the pinned seed; Phase 4's `Canary.mint(...)` reads from this thread-local when its own `seed` kwarg is `None` AND the thread-local is set; otherwise the kwarg / random behavior wins. **Decision required at implementation time:** pick `threading.local()` for predictability with asyncio's default executor or `contextvars.ContextVar` if Phase 4 already uses one — document the choice.
- [ ] **Determinism:** two `Canary.mint()` calls inside two separate `with_pinned_canary(case)` blocks (same `case`, same seed) produce byte-identical canary tokens.
- [ ] **Production behavior unchanged:** outside any `with_pinned_canary(...)` block, `Canary.mint()` (no kwarg) continues to return cryptographically random 32-byte tokens. (Property test: 1000 invocations outside the shim — no duplicates; entropy intact.)
- [ ] **Cleanup on exception:** if the `with` block body raises, the thread-local seed is cleared before propagating; the next `Canary.mint()` outside the block reverts to random behavior.
- [ ] **Phase 4 amendment shipped:** `src/codegenie/engines/canary.py` gains the `seed: bytes | None = None` kwarg on `Canary.mint(...)`; default behavior unchanged; new test `tests/canary/test_seed_kwarg_deterministic.py` proves `Canary.mint(seed=b"\x00" * 32)` is byte-identical across calls.
- [ ] **ADR-P4-006 drafted and merged:** a separate `docs/phases/04-vuln-llm-fallback-rag/ADRs/0006-canary-seed-kwarg.md` (or equivalent path per Phase 4's ADR convention) is filed in the same PR train as this story; the architecture review of Phase 4 acknowledges the additive change.
- [ ] `BenchCase` Pydantic field `cassette_canary_pin` already enforces 32-hex at construction (S1-02); this story does NOT duplicate the check.
- [ ] **Cross-phase contract test:** `tests/integration/test_phase4_cassette_replay_canary.py` runs the same `with_pinned_canary(case): Canary.mint()` block twice and asserts byte-identical outputs.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff format`, `ruff check`, `mypy --strict` clean.

## Implementation outline

1. Create `src/codegenie/eval/canary.py`. Module docstring quotes ADR-0005 §Decision and the Phase 4 amendment dependency.
2. Define a module-level `_pinned_seed: ContextVar[bytes | None] = ContextVar("_pinned_seed", default=None)` (preferred over `threading.local()` because asyncio's default-executor cleanup is more predictable with `ContextVar`).
3. `@contextlib.contextmanager` `with_pinned_canary(case)`:
   - `seed = bytes.fromhex(case.cassette_canary_pin)`.
   - `token = _pinned_seed.set(seed)`.
   - `try: yield seed; finally: _pinned_seed.reset(token)`.
4. Amend `src/codegenie/engines/canary.py` (Phase 4 file):
   - Add `seed: bytes | None = None` kwarg to `Canary.mint(...)`.
   - Inside `mint`, look up `seed` precedence: explicit kwarg > `codegenie.eval.canary._pinned_seed.get()` > random.
   - **Important:** Phase 4 must NOT import `codegenie.eval` unconditionally (creates a dependency inversion). Resolve by either (a) lazy import inside `mint(...)`, or (b) inverting: Phase 4 reads from its own `ContextVar`; `eval.canary` writes to Phase 4's `ContextVar`. **Recommendation:** option (b) — Phase 4 owns the `ContextVar`; `eval.canary.with_pinned_canary` writes to it. This keeps Phase 4 oblivious to Phase 6.5's existence.
5. Draft `docs/phases/04-vuln-llm-fallback-rag/ADRs/0006-canary-seed-kwarg.md` (or per Phase 4's numbering) and add `tests/canary/test_seed_kwarg_deterministic.py`.

## TDD plan — red / green / refactor

### Red

Test file: `tests/unit/eval/test_canary_seed.py`

```python
def test_pinned_canary_yields_seed(case_with_pin):
    with with_pinned_canary(case_with_pin) as seed:
        assert seed == bytes.fromhex(case_with_pin.cassette_canary_pin)
        assert len(seed) == 32

def test_canary_mint_is_deterministic_under_pin(case_with_pin):
    with with_pinned_canary(case_with_pin):
        t1 = Canary.mint()
    with with_pinned_canary(case_with_pin):
        t2 = Canary.mint()
    assert t1 == t2  # byte-identical across two pinned blocks with same pin

def test_canary_mint_is_random_outside_pin():
    samples = {Canary.mint() for _ in range(1000)}
    assert len(samples) == 1000  # no duplicates

def test_thread_local_cleared_on_exception(case_with_pin):
    try:
        with with_pinned_canary(case_with_pin):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    # Outside the block — random behavior must be restored
    samples = {Canary.mint() for _ in range(100)}
    assert len(samples) == 100

def test_explicit_seed_kwarg_overrides_thread_local(case_with_pin):
    other_seed = b"\xff" * 32
    with with_pinned_canary(case_with_pin):
        t = Canary.mint(seed=other_seed)
    # t derives from other_seed, not the pin
    expected = Canary.mint(seed=other_seed)  # outside block
    assert t == expected
```

Phase 4 file: `tests/canary/test_seed_kwarg_deterministic.py`

```python
def test_mint_with_seed_kwarg_deterministic():
    t1 = Canary.mint(seed=b"\x00" * 32)
    t2 = Canary.mint(seed=b"\x00" * 32)
    assert t1 == t2

def test_mint_without_seed_random():
    samples = {Canary.mint() for _ in range(1000)}
    assert len(samples) == 1000
```

### Green

Smallest impl: §Implementation outline; ~25 lines in eval/canary.py + ~10 lines of Phase 4 amendment.

### Refactor

- Add structlog `debug canary.pin_set` and `canary.pin_cleared` events with `case_id` attribute — useful for the integration test in S5-05.
- Document in `eval/canary.py`'s docstring the explicit precedence (kwarg > thread-local > random) so a future reader doesn't have to re-derive it.
- The Phase 4 file gets a one-line module docstring update referencing ADR-P4-006.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/canary.py` | New module — `with_pinned_canary` context manager |
| `src/codegenie/engines/canary.py` | Phase 4 amendment — additive `seed` kwarg + `ContextVar` |
| `docs/phases/04-vuln-llm-fallback-rag/ADRs/0006-canary-seed-kwarg.md` | The cross-phase amendment ADR (file path per Phase 4's numbering convention) |
| `tests/unit/eval/test_canary_seed.py` | Red tests for the shim |
| `tests/canary/test_seed_kwarg_deterministic.py` | Phase 4 amendment's own tests |
| `tests/integration/test_phase4_cassette_replay_canary.py` | Cross-phase contract test |

## Out of scope

- **Editing Phase 4's cassette key composition** — the cassette key already includes `canary_seed` (per Phase 4 final-design); this story only flips the source-of-seed from "random" to "thread-local override".
- **`Canary.mint` re-derivation algorithm** — Phase 4 owns it; this story neither inspects nor changes the BLAKE3/HMAC/SHA derivation. We only add a kwarg.
- **The eventual S7-03 re-confirmation pass** — the Phase 4 amendment is **landed** here; S7-03 only re-checks that the amendment merged before the phase merge train. Do not defer the amendment to S7-03.

## Notes for the implementer

- **`ContextVar` vs `threading.local`:** `ContextVar` is the safer choice for asyncio because it propagates correctly across `asyncio.create_task` (when copy_context is in play). `threading.local` does NOT propagate to thread-pool executors cleanly. The runner (S3-02) uses `asyncio.Semaphore` + per-case workers; pinning a `ContextVar` survives the task boundary; pinning a `threading.local` does not. **Pick `ContextVar`.**
- **Dependency inversion (load-bearing):** Phase 4 must not import `codegenie.eval`. The `ContextVar` should live in `codegenie.engines.canary` (Phase 4); `codegenie.eval.canary.with_pinned_canary` *writes* to it. This way Phase 4's tests pass with no `codegenie.eval` import.
- **Cross-phase amendment trains:** Per `phase-arch-design.md §Risks #4` and `stories/README.md §Cross-cutting concerns`, the amendment ADR PR opens *with* this story to avoid review pile-up on the closing merge train. Do not wait until S7-03.
- **The integration test in `test_phase4_cassette_replay_canary.py`** is the load-bearing cross-phase contract: it proves the seed propagates from `BenchCase.cassette_canary_pin` all the way through to Phase 4's `Canary.mint()` byte-for-byte. Move it to `tests/integration/` (not `tests/unit/eval/`) so it's clear the test crosses a phase boundary.
- **Reversibility note (from ADR-0005):** Medium — reverting the seed kwarg would force a regenerate-cassettes-at-live-cost migration. Treat as one-way additive.
- The 32-hex-validation of `cassette_canary_pin` lives in S1-02's Pydantic schema; this story trusts it and does not re-validate (`phase-arch-design.md §Component design — canary.py Failure behavior`).
