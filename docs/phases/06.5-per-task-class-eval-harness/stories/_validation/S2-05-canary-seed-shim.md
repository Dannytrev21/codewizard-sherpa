# Validation report — S2-05 (canary seed thread-local shim + Phase 4 `Canary.mint(seed=...)` amendment)

**Validated:** 2026-05-26
**Verdict:** **RESCUE**
**Story status updated to:** `BLOCKED`
**No edits applied to story body** (per validator-skill anti-goal: "does not rewrite the story's goal or scope").

## TL;DR

The story is built on a phantom Phase 4 API. Three of its four foundational
premises are factually wrong against the shipped codebase as of 2026-05-26:

1. **`Canary.mint(...)` does not exist.** What Phase 4 actually shipped is
   `FenceWrapper(nonce_source: Callable[[], HexNonce] = _default_nonce_source)`
   in `src/codegenie/fallback/fence/wrapper.py:258`. `CanaryGuard` is a
   *scanner* (`scan(payload, nonce) -> CanaryResult`), not a *minter*.
2. **`src/codegenie/engines/canary.py` does not exist.** The `engines/`
   directory does not exist anywhere under `src/codegenie/`.
3. **Phase 4's cassette key does not include `canary_seed`.** Phase 4
   `final-design.md:37` lists the determinism tuple as
   `(repo_snapshot_sha, cve_record_digest, plugin_version, recipe_version,
   vuln_index_digest, store_digest, embedding_model_digest, cassette_blake3)`.
   `grep -rn "canary_seed" docs/phases/04-vuln-llm-fallback-rag/` returns
   zero hits.
4. AC-7's "BenchCase Pydantic field `cassette_canary_pin` already enforces
   32-hex at construction (S1-02)" is wrong: S1-02 explicitly **deferred**
   the 32-hex format check to "S2-02 (loader) or S5-07 cassette-seed-shim"
   (see S1-02 line 519). S2-02 (which has been HARDENED) does not validate
   the in-`case.toml` `cassette_canary_pin` shape — it only validates
   `digests.yaml`. So the 32-hex check lives **nowhere** today.

ADR-0005 itself (dated 2026-05-12, accepted before Phase 4's actual shipped
design landed) is the root cause: it prescribes a `Canary.mint(seed=...)`
amendment to Phase 4, and the story faithfully descends from it.

The cleanest rescue path (independently surfaced by both Consistency and
Design-Patterns critics) is to consume Phase 4's existing
`nonce_source: Callable[[], HexNonce]` seam:

```python
# In codegenie.eval.canary
def pinned_nonce_source(case: BenchCase) -> Callable[[], HexNonce]:
    pin = HexNonce(case.cassette_canary_pin)   # already 32-hex by contract
    return lambda: pin

# In the bench runner (per case):
wrapper = FenceWrapper(scanner=..., event_log=..., nonce_source=pinned_nonce_source(case))
```

This collapses the entire story to a few lines, requires **zero** Phase 4
edits, **zero** cross-phase ADR amendment, **zero** ContextVar action-at-a-
distance, **zero** asyncio-task-propagation hazard. It is a clean
dependency-injection through an explicit constructor parameter — exactly
the seam Phase 4 already documents as "seam for deterministic-nonce tests"
in `FenceWrapper.__init__`.

But applying that rescue requires:

- Rewriting the story's **goal** (currently invokes `Canary.mint`).
- Amending ADR-0005 to record the actual shipped Phase 4 surface and pick
  the `nonce_source`-injection option (none of the three options ADR-0005
  considered match the actual shipped Phase 4).
- Re-confirming Phase 4 has no hidden coupling that would prevent
  per-instance `FenceWrapper` construction inside the bench runner.
- Landing the 32-hex `cassette_canary_pin` validator somewhere (the
  pre-existing deferral target is S5-07; or amend S1-02 / S2-02 to absorb
  it now that the dependency is concrete).

All four steps are beyond surgical hardening. They are a redesign of the
story (and of ADR-0005). Per the validator skill's policy
("Does not rewrite the story's goal or scope — that's a `phase-story-writer`
re-run"), the verdict is **RESCUE** and the story body is left untouched.

## What was done

1. The story's `Status:` is updated from `Ready` to `BLOCKED`.
2. A `Validation notes` block is prepended to the story documenting the
   verdict, the four phantom premises, and the recommended rescue path.
3. **No changes** to Context, References, Goal, Acceptance criteria,
   Implementation outline, TDD plan, Files to touch, Out of scope, or
   Notes for implementer. Those are the writer/architect's territory.

## Recommended next actions (owner: phase architect)

1. **Re-run `phase-architect`** (or hand-edit `ADR-0005`) to record that
   Phase 4 actually ships `FenceWrapper.nonce_source` and amend the
   accepted decision accordingly. The "ADR-P4-006 amendment" half of
   ADR-0005 §Decision should be **withdrawn**; the bench-side
   `pinned_nonce_source` half stands.
2. **Re-run `phase-story-writer`** for S2-05 against the corrected ADR.
   New story scope: a pure `pinned_nonce_source(case) -> Callable[[], HexNonce]`
   factory in `codegenie.eval.canary` + a single AC asserting the bench
   runner constructs `FenceWrapper(..., nonce_source=pinned_nonce_source(case))`
   per case + a single integration test asserting byte-identical
   `FencedSegment` across two runs of the same case.
3. **Decide where the 32-hex `cassette_canary_pin` validator lands** —
   amend S1-02 to absorb it (cleanest; the model is the natural home), or
   amend S2-02 (loader-time check), or accept that S5-07 still owns it and
   make the new S2-05 depend on S5-07 + sanitize at the shim boundary.
4. **Pick the next free Phase 4 ADR slot** if any cross-phase amendment is
   still needed — 0006 is taken (`egress-guard-no-production-loopback-carveout.md`),
   Phase 4 is up to 0017, next free is **0018**.

## Critics' raw findings (verbatim)

### Coverage critic — 12 findings (5 block, 5 harden, 2 nit)

Subsumed by the RESCUE verdict, but preserved for the rewritten story:

- **F-COV-1 (block):** Nested `with_pinned_canary` cleanup not tested.
  `_pinned.set(None)` (wrong impl) passes the single-level test but
  corrupts nested usage. **Carries to the rewrite if the
  context-manager pattern is kept.**
- **F-COV-2 (block):** No AC for asyncio concurrency. Two parallel
  `asyncio.Task`s each entering `with_pinned_canary` with different pins
  must not cross-contaminate. **Carries to the rewrite.**
- **F-COV-3 (block):** No AC for `ContextVar` propagation across
  `asyncio.create_task` / `run_in_executor`. **Carries to the rewrite if
  ContextVar is kept.** (Goes away under the `nonce_source` rescue —
  the per-case `FenceWrapper` carries its own factory; no thread-local
  propagation question.)
- **F-COV-4 (harden):** AC-2 "decide ContextVar vs threading.local at
  impl time" is unverifiable; pin one in the AC.
- **F-COV-5 (block):** Missing AC — invalid/missing `cassette_canary_pin`
  at the shim boundary. S1-02 deferred the 32-hex check. **Direct
  match for the rescue's "decide where the validator lands" question.**
- **F-COV-6 (block):** AC-7 (ADR drafted + merged) is a process checkbox,
  not behavior. No test asserts Phase 4's `Canary.mint()` actually
  consults the `ContextVar`. **Dissolves under the rescue (no Phase 4
  amendment to checkbox).**
- **F-COV-7 (block):** Determinism AC-3 is satisfied by a constant
  function. **Carries to the rewrite** as the metamorphic
  "different pins → different canaries" property.
- **F-COV-8 (harden):** `case_with_pin` fixture undefined — tests will
  collection-error. **Carries to the rewrite.**
- **F-COV-9 (harden):** No AC against stray `_pinned_seed.set(...)`
  from a future careless caller. **Dissolves under the rescue** (no
  module-level mutable state).
- **F-COV-10 (harden):** Phase-arch Edge case #6 (cassette canary
  mismatch — cache invalidation via `cassette_corpus_digest` bump) not
  surfaced as an AC. **Carries to the rewrite.**
- **F-COV-11 (nit):** `test_canary_mint_is_random_outside_pin` is
  coincidence, not structural — entropy ≠ cardinality.
- **F-COV-12 (nit):** No AC pins that yielded seed and consumed seed
  are the same. **Dissolves under the rescue** (no yield;
  factory returns the consumer).

### Test-Quality critic — 12 findings (6 block, 5 harden, 1 nit)

Subsumed by the RESCUE verdict; preserved for the rewrite:

- **F-TQ-1 (block):** `test_canary_mint_is_random_outside_pin` confuses
  cardinality with entropy. Counter impl produces 1000 unique values
  and the set-cardinality test passes. Patch `secrets.token_bytes` /
  `token_hex` to a sentinel and assert mint consumed it. **Carries to
  the rewrite** as "the random factory is the default `_default_nonce_source`."
- **F-TQ-2 (block):** `test_canary_mint_is_deterministic_under_pin`
  passes against a constant impl. Add metamorphic companion:
  different pins → different canaries. **Carries to the rewrite.**
- **F-TQ-3 (block):** `test_explicit_seed_kwarg_overrides_thread_local`
  doesn't prove precedence — both sides derive from the same kwarg.
  **Dissolves under the rescue** (no precedence table to test).
- **F-TQ-4 (block):** `test_thread_local_cleared_on_exception` passes
  against a `finally: _pinned.set(LAST_SEEN_PIN)` (cleared to stale).
  Assert `_pinned_seed.get() is None` + mechanism patch.
  **Dissolves under the rescue.**
- **F-TQ-5 (block):** No nested-context-manager test. `set(None)`
  instead of `reset(token)` survives single-level. **Dissolves under
  the rescue.**
- **F-TQ-6 (block):** No asyncio task-boundary test — the load-bearing
  reason for ContextVar over threading.local. **Dissolves under
  the rescue.**
- **F-TQ-7 (harden):** No property-based test for "pin determines
  canary." `def mint(): return bytes.fromhex(case.cassette_canary_pin)`
  (returns seed verbatim) survives. **Carries to the rewrite.**
- **F-TQ-8 (harden):** `test_pinned_canary_yields_seed` purely
  structural — yielding ≠ downstream effect. **Dissolves under
  the rescue.**
- **F-TQ-9 (harden):** `case_with_pin` fixture undefined. **Carries
  to the rewrite.**
- **F-TQ-10 (harden):** `test_mint_without_seed_random` repeats F-TQ-1.
- **F-TQ-11 (harden):** No test exercises kwarg=`b"\x00"*32` (truthy-
  vs-non-empty failure mode). **Dissolves under the rescue.**
- **F-TQ-12 (nit):** No test for structlog `canary.pin_set/cleared`
  events. **Dissolves under the rescue** (no events to emit).

### Consistency critic — 12 findings (5 block, 5 harden, 2 nit) — **headline RESCUE driver**

- **F-CON-1 (block):** `src/codegenie/engines/canary.py` does not exist.
- **F-CON-2 (block):** Phase 4's cassette key does NOT include `canary_seed`.
- **F-CON-3 (block):** AC-7's "S1-02 enforces 32-hex" is false — S1-02 explicitly deferred the check.
- **F-CON-4 (block):** `0006-canary-seed-kwarg.md` slot already occupied by `0006-egress-guard-no-production-loopback-carveout.md`. Next free Phase 4 ADR slot is 0018.
- **F-CON-5 (block):** Phase 4 has no `Canary.mint` to amend. `FenceWrapper.nonce_source: Callable[[], HexNonce]` already provides the seam.
- **F-CON-6 (harden):** ADR-0005 §Tradeoffs warns thread-local can silently break under async refactors; story dismisses it in one sentence.
- **F-CON-7 (harden):** Implementation outline contradicts itself on option-(a)-vs-(b) for the Phase 4 import-direction; AC-6 is silent on which.
- **F-CON-8 (harden):** Cross-phase import edge needs an import-linter contract + a `tests/fence/` structural test; story adds neither.
- **F-CON-9 (harden):** "Out of scope" bullet 1 doubles down on F-CON-2's false premise.
- **F-CON-10 (harden):** TDD tests reference a non-existent `Canary.mint()`; the closest real surface already has GREEN randomness tests in S2-02 — duplicating them from Phase 6.5 against a phantom API is wasted motion.
- **F-CON-11 (nit):** "Production behavior unchanged" rests on a non-existent function.
- **F-CON-12 (nit):** ADR-0005 §Reversibility's "Medium" claim is calibrated against the imaginary surface; the actual reversibility (delete a per-case factory) is **Low**.

### Design-Patterns critic — 8 findings (2 block, 5 harden, 1 nit)

- **F-DP-1 (block):** Story reinvents `FenceWrapper.nonce_source`. The cleaner rescue: bench runner constructs `FenceWrapper(..., nonce_source=pinned_nonce_source(case))` per case. Zero Phase 4 edits.
- **F-DP-2 (block):** Module-level ContextVar that Phase 4 secretly reads = action-at-a-distance / hidden singleton. Even the "Phase-4-owns-the-ContextVar" option-(b) is still spooky-at-a-distance.
- **F-DP-3 (harden):** `with_pinned_canary` tangles pure transform (`pin -> HexNonce`) with impure side effects (`ContextVar.set/reset`). Functional core / imperative shell would split them.
- **F-DP-4 (harden):** Primitive obsession on `bytes` — Phase 4 already ships `HexNonce` newtype. `cassette_canary_pin` is already a 32-hex string. No `bytes.fromhex` round-trip needed.
- **F-DP-5 (harden):** Capability token is the right shape (mirror Phase 4 ADR-0010 `BudgetToken`). Surface the parallel in Notes-for-implementer.
- **F-DP-6 (harden):** Missed rule-of-three — same seam pattern serves S2-06 (cost-tag), future deterministic clock, RNG, etc. Story treats canary-pinning as bespoke instead of surfacing the reusable rule.
- **F-DP-7 (harden):** Three-tier precedence table + asyncio-task-propagation Notes + cleanup-on-exception AC + the integration test all exist *only* because the story chose ContextVar over constructor injection. All dissolve under F-DP-1.
- **F-DP-8 (nit):** Story references stale code paths; phase-story-executor would chase a phantom file.

## Conflict resolution

No conflicts to resolve. All four critics independently converged on the
same RESCUE driver (no `Canary.mint`; use the `nonce_source` seam).
Coverage and Test-Quality findings either dissolve under the rescue
(no ContextVar means no propagation / cleanup / precedence concerns)
or carry forward as harden-tier work for the rewritten story
(metamorphic determinism, fixture definition, edge-case-#6 cache
invalidation).

## Researcher (Stage 3)

**Not invoked.** No `NEEDS RESEARCH` findings — every critic could
propose a concrete fix from existing codebase precedent.
