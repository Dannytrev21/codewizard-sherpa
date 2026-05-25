# Validation report: S4-05 — `StrictAndGate` adapter + Phase-3 equivalence property test

**Validated:** 2026-05-25
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S4-05 is the load-bearing thin adapter that closes the Phase 5 ↔ Phase 3
trust seam — it materializes a `list[TrustSignal]` from a populated
`ObjectiveSignals` and delegates strict-AND scoring to the canonical
`TrustScorer` (ADR-0003). The goal is intact and correctly framed; the draft
correctly names the equivalence property test as the load-bearing artifact.

But the draft was written **before** S4-04's HARDENED report locked in the
Phase-3 surfaces it must consume, and before S1-04 / S1-03 fully hardened the
upstream contracts. As a result the draft would not have survived first
import — every block-tier finding traces back to that gap:

| Draft assumption | Reality on `master` (or HARDENED upstream story) |
|---|---|
| `Phase3TrustScorer()` no-arg constructor | `TrustScorer(event_log: EventLog)` — constructor-injection per ADR-0001/0005 functional-core discipline; bare `()` is a `TypeError` at first call |
| `from codegenie.trust.scorer import TrustScorer, TrustSignal` | `from codegenie.transforms.trust_scorer import TrustScorer` and `from codegenie.transforms.outcomes import TrustSignal` — neither symbol is reachable at `codegenie.trust.scorer` |
| Sidecar `import codegenie.sandbox.signals.trust_registration` triggers kind registration | S4-04 HARDENED **forbids** a `trust_registration.py` sidecar with an AC-ANTIPATTERN file-existence test; each collector self-registers via `@register_signal_kind` at module import time (S1-05 delegation chain) — the correct trigger is `import codegenie.sandbox.signals` |
| `GateOutcome.failing_signals` derives from `TrustOutcome.failing` | Phase-3 `TrustOutcome.failing` is **caller-order** ("never sorted or deduplicated" per the scorer docstring); a passthrough would directly contradict the draft AC's "sorted, deterministic" — the gate must derive its own sorted list from the populated `ObjectiveSignals`, not from `TrustOutcome.failing` |
| `TrustScorer.score` returns `.passed`-only | `TrustOutcome(passed, failing, signals, confidence)` — the gate silently dropped `confidence: Literal["high", "degraded"]` on the floor with no documented decision |
| `ctx.gate.required_signals` is the lookup path | `Gate.required_signals` is an *instance* attribute on the gate itself (S1-04); `ctx.gate` does not exist on `GateContext` |
| `ctx.attempt` provides the attempt number | `GateContext` has no `attempt` field (S1-04 fields: `worktree`/`advisory`/`recipe`/`transform_output`/`prior_attempts`); attempt must be derived from `len(ctx.prior_attempts) + 1` and minted as `AttemptNumber` |
| `TrustScorer.score([])` returns `passed=True` (implicit) | Raises `EmptySignals` (Rule 12 — fail loud); silent `passed=True` would mis-report a broken Stage-6 collection as a passing workflow |
| Sub-models accept naive `datetime.now(UTC)` and bare `str` kinds | S1-03 enforces `at: AwareDatetime` (naive rejected) and `signal_kind: SignalKind` (NewType); `provenance.inputs_blake3` is lowercase-hex; sub-models are `extra="forbid", frozen=True, strict=True` |
| Six kinds `{build, install, tests, trace, policy, cve_delta}` are pre-registered | Phase-3 pre-registers `{build, install, tests, lockfile_policy, cve_delta}`; `trace` + `policy` are net-new Phase-5 registrations fired by `import codegenie.sandbox.signals` (S4-04 ACs `NEW-KINDS-1..-3` + `EXACT-7`) |

No `RESCUE`-tier escalation: the goal text required no edit; the
acceptance-criteria set, the implementation outline, and the TDD plan were
rewritten in place to bind to the actual upstream surfaces. Every gap was
patchable from the four honored ADRs, arch §Component design + §Testing
strategy + §Integration with Phase 6, CLAUDE.md ("Extension by addition",
"Newtype identifiers", "Functional core / imperative shell", Rule 11), the
five prior HARDENED reports (S1-02, S1-03, S1-04, S1-05, S4-01..S4-04), and
the existing kernels (`transforms/trust_scorer.py`,
`transforms/signal_kinds.py`, `transforms/outcomes.py`, `types/identifiers.py`).
Stage 3 (research) was skipped — every gap was answerable from in-repo
precedents and the seven prior validation reports.

## Findings by critic

### Coverage critic

#### Block-tier (would silently pass / would crash on first real input)

1. **(coverage — block) `Phase3TrustScorer()` constructor signature wrong everywhere.**
   The actual constructor is `TrustScorer(event_log: EventLog)`. The draft's
   pseudo-code (`score = Phase3TrustScorer().score(trust_signals)`) and every
   test fixture would `TypeError` at first call. **Fix:** new AC-CTOR-1
   pinning the `event_log` keyword, AC-CTOR-2 pinning the `EventLog` import,
   AC-CTOR-3 pinning that the scorer is constructed once at `evaluate`
   entry (or stored from gate construction) — and the whole TDD plan was
   rewritten to thread a per-test `EventLog` through `_log(tmp_path)`.

2. **(coverage — block) Import paths invented.** The draft's
   `from codegenie.trust.scorer import TrustScorer, TrustSignal` resolves
   to neither module nor symbol — `TrustScorer` lives at
   `codegenie.transforms.trust_scorer`, `TrustSignal` at
   `codegenie.transforms.outcomes`. **Fix:** AC-IMPORT-1..-3 pin every
   import the adapter and tests must use.

3. **(coverage — block) `failing_signals` ordering contradiction.** The
   draft AC requires `failing_signals` to be "sorted, deterministic" — but
   Phase-3 `TrustOutcome.failing` is deliberately *caller-order* ("never
   sorted or deduplicated" — `trust_scorer.py:99-104`). A naive passthrough
   (`failing_signals = score.failing`) would violate the draft AC; the
   adapter must derive its own sorted list from the populated
   `ObjectiveSignals` (not from `TrustOutcome.failing`). **Fix:** new
   AC-FS-1 makes the derivation explicit (gate-side, not passthrough),
   AC-FS-2 asserts byte-exact `sorted()` order with a parametrized
   shuffle-input test (3 permutations of the same populated dict → same
   sorted output), AC-FS-3 forbids any reference to `score.failing` in the
   adapter body via AST scan.

4. **(coverage — block) Sidecar `trust_registration.py` import contradicts
   S4-04 AC-ANTIPATTERN.** The draft's test file imports
   `codegenie.sandbox.signals.trust_registration` — but S4-04 HARDENED has
   an explicit file-existence test that fails if that path exists. The
   correct kind-registration trigger is `import codegenie.sandbox.signals`
   (which transitively imports every collector module and fires
   `@register_signal_kind` per S1-05). **Fix:** all test fixtures use
   `import codegenie.sandbox.signals  # noqa: F401  (fires kind registration)`,
   AC-REG-1 forbids any reference to `trust_registration` in `gates/**` or
   the new test file, AC-REG-2 mirrors S4-04's file-existence anti-pattern
   assertion so a regression in S4-05's test layer can't reintroduce it.

5. **(coverage — block) `EmptySignals` exception path uncovered.**
   `TrustScorer.score([])` raises `EmptySignals` — a contractually distinct
   error from `GateMissingRequiredSignal`. The draft handles
   "all sub-models `None`" upstream via `GateMissingRequiredSignal` only
   when `required_signals` is non-empty; it has no AC for the corner case
   `required_signals=()` AND `os` all-`None` (which Phase-3 would surface
   as `EmptySignals`). **Fix:** AC-EMPTY-1 pins the adapter's
   `GateMissingRequiredSignal`-before-`score()` discipline; AC-EMPTY-2
   pins that `required_signals=()` AND `os` all-`None` raises
   `GateMissingRequiredSignal` *with a distinct message* ("no required
   signals and no populated signals" — never propagates the Phase-3
   `EmptySignals` to the caller).

6. **(coverage — block) `ctx.attempt` does not exist on `GateContext`.**
   S1-04 HARDENED's `GateContext` fields are `worktree`, `advisory`,
   `recipe`, `transform_output`, `prior_attempts`. The draft outline writes
   `attempt=ctx.attempt` — `AttributeError` at first construction. **Fix:**
   AC-ATTEMPT-1 derives the attempt number from
   `AttemptNumber(len(ctx.prior_attempts) + 1)` (1..1024 range inherited
   from `AttemptNumber` per S1-04 AC-J-3); AC-ATTEMPT-2 asserts a three-call
   accumulation (`ctx` with `prior_attempts=[]` → attempt 1; with one
   prior → attempt 2; with two priors → attempt 3); AC-ATTEMPT-3 rejects
   `len(ctx.prior_attempts) + 1 > 1024` via the inherited bound (positive
   AttemptNumber construction).

7. **(coverage — block) `ctx.gate.required_signals` is a phantom lookup.**
   `Gate` is the gate instance itself; `GateContext` does not carry a
   `gate` field. **Fix:** AC-REQ-1 pins the required-signals source as
   `self.required_signals` (the gate's own instance attribute per S1-04);
   AC-REQ-2 asserts a `GateMissingRequiredSignal` raised when a required
   kind is `None` on `os`, with the *missing kind names* in the exception
   `.missing: tuple[SignalKind, ...]` typed attribute (not free-text).

8. **(coverage — block) `signal_kind_registry` pre-population mismatch.**
   The draft KINDS tuple `("build", "install", "tests", "trace", "policy",
   "cve_delta")` assumes all six are pre-registered. Reality:
   `transforms/signal_kinds.py` pre-registers `{build, install, tests,
   lockfile_policy, cve_delta}`; `trace` and `policy` are net-new Phase-5
   registrations whose fire-trigger is `import codegenie.sandbox.signals`.
   **Fix:** AC-REG-3 pins the 7-element registry membership after the
   sandbox-signals import side-effect (mirrors S4-04 AC-EXACT-7);
   AC-REG-4 names the exact set
   `{build, install, tests, lockfile_policy, cve_delta, trace, policy}`;
   AC-REG-5 asserts that the gate uses ONLY the six Phase-5 kinds (the
   `lockfile_policy` Phase-3 kind is not a sub-model on `ObjectiveSignals`).

#### Harden-tier

9. **(coverage — harden) `TrustOutcome.confidence` dropped silently.** Phase-3
   returns `confidence: Literal["high", "degraded"]`; the adapter throws it
   away. The fix is a *decision*: either propagate to `GateOutcome.summary`
   or pin "intentionally discarded; runner reads via separate path." Per
   arch §Integration with Phase 6 the `state` field is the load-bearing
   downstream signal — `confidence` is not consumed by the runner's
   retry-decision logic. **Fix:** AC-CONF-1 pins that `TrustOutcome.confidence`
   is incorporated into `GateOutcome.summary` as a tail substring
   ("; confidence=high" or "; confidence=degraded"), so the audit trail
   preserves it without widening the `GateOutcome` schema (which is S1-04
   territory and frozen). AC-CONF-2 mutation defense: flipping
   `event_log` between a clean log and one carrying
   `AdapterDegraded(workflow_id=...)` flips the `summary` tail substring.

10. **(coverage / patterns — harden) Sub-model field set + provenance
    population unpinned end-to-end.** The draft's `_sub` fixture passes
    `details={}, provenance=_prov(kind), at=datetime.now(UTC)` — but
    S1-03 makes `at: AwareDatetime` (naive rejected) and `provenance`
    required with four sub-fields. The draft constructs `SignalProvenance`
    via `inputs_blake3="00" * 16` which is the right shape (32 hex chars)
    but no AC asserts: (a) the gate copies `details` byte-stable into
    `TrustSignal.details`; (b) the gate does NOT propagate the `provenance`
    field into `TrustSignal` (which has no provenance field — `TrustSignal`
    is `(kind, passed, details)` only per `transforms/outcomes.py:377-388`).
    **Fix:** AC-DETAILS-1 mutation defense — a `BuildSignal.details =
    {"k": "v", "i": 7, "b": True}` round-trips byte-exact to
    `TrustSignal.details`; AC-DETAILS-2 pins that `TrustSignal` is built
    with exactly three fields (no `provenance`, no `at`).

11. **(coverage — harden) `state` positive set is *three* members for the
    adapter** (`{"passed", "failed_retryable", "escalate"}`), not four —
    `"failed_unrecoverable"` is set by `GateRunner` based on attempt
    history. The draft says this in prose ("out of scope") but has no AC
    pinning the adapter never returns `failed_unrecoverable`. **Fix:**
    AC-STATE-1 byte-exact set inclusion (`outcome.state in {"passed",
    "failed_retryable", "escalate"}` across every test case); AC-STATE-2
    parametrized over the 64 cartesian + the missing-signal + the
    non-retryable + the all-pass; AC-STATE-3 explicit positive forbid
    (`assert outcome.state != "failed_unrecoverable"` in every test row).

12. **(coverage — harden) `retryable` ↔ `state` cross-field rule unpinned
    in adapter tests.** S1-04 AC-CF-2 enforces this at the model layer
    (model_validator rejects inconsistent), but the adapter's *own*
    construction path is unvalidated — an executor that passes
    `state="failed_retryable", retryable=False` would crash at
    construction (good), but no AC pins that the adapter's branch logic
    produces consistent pairs in the first place. **Fix:** AC-RETRY-1
    parametrizes the retry-policy across (a) all-retryable, (b) some
    non-retryable, (c) all non-retryable; asserts `retryable` matches the
    classification AND `state` aligns; AC-RETRY-2 asserts `retryable=False`
    when `failing_signals` is empty AND `passed=True` (i.e., state="passed"
    forces retryable=False — mirror of S1-04 AC-CF-1).

13. **(coverage — harden) Adapter LOC budget enforced by test, not prose.**
   Draft says "≤ 60 LOC including imports (≤ 40 LOC for the body)". An
   executor with verbose docstrings could blow this silently. **Fix:**
   AC-LOC-1 pins ≤ 60 lines total via `len(Path(...).read_text().splitlines())`;
   AC-LOC-2 pins ≤ 40 lines of executable body via an AST walk excluding
   comments, blank lines, and docstrings.

14. **(coverage — harden) Coverage floor wording.** Draft has no
    `≥ 95% line / ≥ 90% branch` AC. Same conflation S1-02 / S1-03 / S1-04
    fixed. **Fix:** AC-COV-1 mirrors the README's 95/90 floor on
    `src/codegenie/gates/strict_and.py`.

15. **(coverage — harden) Property-test strategy bug.** Draft's hypothesis
    strategy
    `st.lists(st.sampled_from(KINDS), min_size=1, max_size=6, unique=True)`
    paired with `st.lists(st.booleans(), min_size=1, max_size=6)`
    truncates via `min(len(present), len(passes))` — which deletes
    coverage when `len(passes) < len(present)`. **Fix:** AC-PROP-1
    rewrites to a single strategy
    `st.dictionaries(keys=st.sampled_from(KINDS), values=st.booleans(),
    min_size=1, max_size=6)` (no length mismatch possible); AC-PROP-2
    pins `≥ 500 examples` (up from 200) since the strategy is now denser;
    AC-PROP-3 derandomises the deadline with
    `@settings(deadline=None, max_examples=500)`.

16. **(coverage — harden) `summary` field shape unpinned.** Adapter
    outline has `summary=...` placeholder. **Fix:** AC-SUMMARY-1 pins the
    format: `"strict-AND: {n_passed}/{n_populated} signals passed; failing:
    {sorted-csv or 'none'}; confidence={high|degraded}"`; AC-SUMMARY-2
    asserts ≤ 4096 UTF-8 bytes (matches `AttemptSummary.prior_failure_summary`
    cap — forward compatibility); AC-SUMMARY-3 byte-stable substring
    inclusion `"strict-AND: "`, `"; failing:"`, `"; confidence="`.

### Test-quality critic (mutation analysis — 18 plausible wrong implementations)

| # | Mutation | Caught by draft? | Caught after harden? |
|---|---|---|---|
| M-1 | Adapter calls `Phase3TrustScorer()` (no event_log) | No — `TypeError` at first call but test fixtures share the bug | Yes — `_log(tmp_path)` fixture mandated; AC-CTOR-1 |
| M-2 | Adapter imports `TrustScorer` from `codegenie.trust.scorer` | No — ImportError at first run | Yes — AC-IMPORT-1..-3 pin exact paths |
| M-3 | Adapter passes through `score.failing` to `failing_signals` (caller-order, not sorted) | Partial — passes when caller-order happens to equal sorted; flaky | Yes — AC-FS-2 shuffle-permutation test |
| M-4 | Adapter sorts `score.failing` (still wrong source) | No | Yes — AC-FS-3 AST scan forbids `score.failing` reference |
| M-5 | Adapter uses `ctx.attempt` (AttributeError) | No — every test fixture has the same bug | Yes — AC-ATTEMPT-1 derives from `prior_attempts` |
| M-6 | Adapter reads `ctx.gate.required_signals` (AttributeError) | No — same bug shared | Yes — AC-REQ-1 pins `self.required_signals` |
| M-7 | Adapter returns `state="failed_unrecoverable"` on retry-exhausted | No | Yes — AC-STATE-3 forbid |
| M-8 | Adapter swallows `EmptySignals` and returns `passed=True` | No | Yes — AC-EMPTY-1 / -2 |
| M-9 | Adapter drops `details` (or shallow-copies and mutates) | No | Yes — AC-DETAILS-1 round-trip |
| M-10 | Adapter materializes `TrustSignal(kind=..., passed=..., details=..., provenance=...)` (extra field — Pydantic `extra="forbid"` raises) | No | Yes — AC-DETAILS-2 |
| M-11 | Adapter calls `signal_kind_registry` with raw `str` (not `SignalKind`) | No — coercion masks | Yes — AC-REG-5 (`SignalKind(...)` mandatory at call site) |
| M-12 | Adapter relies on `trust_registration.py` sidecar | No | Yes — AC-REG-1 / -2 file-existence forbid |
| M-13 | Adapter uses naive `datetime.now()` in any internal fixture | No | Inherited from S1-03 AC-6/-6a (any naive `at` rejects at construction) |
| M-14 | Adapter computes `retryable=True` when `failing_signals=[]` | No | Yes — S1-04 AC-CF-1 inherited; AC-RETRY-2 explicit |
| M-15 | Adapter returns `failing_signals` from non-required `os` populated kinds (e.g., includes a present-but-non-required failing signal) | No | Yes — AC-FS-4: `failing_signals` is the intersection of `required_signals` AND failing populated kinds (not just failing populated kinds) |
| M-16 | Adapter raises a different exception subclass on missing required signal | No | Yes — AC-EXC-1 pins `GateMissingRequiredSignal` exact type; AC-EXC-2 pins `.missing: tuple[SignalKind, ...]` typed attribute (not message-only) |
| M-17 | Adapter constructs `TrustScorer` per `evaluate()` call (state leak between gates) | No | Defensive Notes — both call-time and ctor-time construction are correct; the Functional-core invariant says scorer is stateless across `score()` per `trust_scorer.py:135-137` |
| M-18 | Adapter logs subprocess / writes filesystem | No | Yes — AC-PURITY-1 mirrors S1-04 AC-9a / AC-9b purity walker (no `subprocess`, no `os.system`, no `pathlib.Path.write_*`, no `logging`/`structlog`); inherited from Phase 5 fence (`tests/schema/test_no_llm_imports_in_sandbox.py`) |

Tests carried forward from draft (kept verbatim or near-verbatim):
- 64-case enumerative parametrize over all six populated (renamed
  AC-ENUM-1).
- Equivalence with Phase 3 (rewritten with correct `_log` fixture —
  AC-EQUIV-1).
- Missing required signal raises (rewritten with `.missing` attribute
  check — AC-EXC-1 / -2).
- Mutation-check on `passed` faithfulness (kept; AC-MUT-1).

Properties added:
- Live-registry parametrization over the 7-element set (mirrors S4-04
  pattern — AC-PROP-2 secondary).
- Three-call attempt-accumulation (AC-ATTEMPT-2).
- Shuffle-permutation `failing_signals` sort stability (AC-FS-2).
- Adversarial: `os` populates a non-required failing kind — adapter
  excludes it from `failing_signals` (AC-FS-4).

### Consistency critic

| # | Severity | Finding | Fix applied |
|---|---|---|---|
| #1 | **block** | Implementation outline pseudo-code names `Phase3TrustScorer` — class is `TrustScorer` (no `Phase3` prefix in production code) | Outline rewritten; AC-IMPORT-1 pins the symbol name |
| #2 | **block** | Implementation outline names `_retry_policy` private attribute — S1-04 `Gate` ABC declares `retry_policy` (public) as instance attr | Outline rewritten to `self.retry_policy.retryable_failures` |
| #3 | **block** | Implementation outline passes `gate_id=TransitionId.STAGE6_VALIDATE` to `StrictAndGate.__init__` — but per S1-04 AC-3 `TransitionId` is the *transition* enum, not the gate identifier. Conflation. Gates are named (e.g., `"stage6_validate"`) and *map to* a `TransitionId` — but they're not the same axis | Outline + tests pinned to use the `TransitionId` enum *value* as the gate id string (or a separate `GateId = NewType("GateId", str)` if S1-05's catalog loader has minted one). Surface as Open ambiguity (resolved): gate id is `TransitionId.STAGE6_VALIDATE.value` until S1-06's catalog loader supplies a distinct identifier |
| #4 | harden | Out-of-scope says "YAML catalog loading into `StrictAndGate.from_yaml` — that's S5-02's `from_yaml` factory" — actually S1-06 owns the catalog schema; the `from_yaml` factory may live in S1-06 or S5-02 depending on layering | Out-of-scope clarified: `from_yaml` factory deferred (owner story TBD between S1-06 and S5-02) — S4-05 ships only the constructor-injected adapter |
| #5 | harden | Coverage floor wording missing | AC-COV-1 mirrors S1-02/S1-03/S1-04 |
| #6 | harden | `__future__ annotations` + `__all__` discipline missing | AC-MOD-1 / AC-MOD-2 mirror S1-04 AC-9 family |
| #7 | harden | `Gate` ABC `gate_id` declared as `str` in S1-04 outline; `required_signals` declared as `tuple[SignalKind, ...]` — draft outline passes `list[str]` | Constructor outline + tests adjusted to `tuple[SignalKind, ...]` |
| #8 | harden | `summary` field semantics not pinned (Phase 6 reducer + audit trail consume) | AC-SUMMARY-1..-3 |
| #9 | nit | Test file path: draft says `tests/gates/test_strict_and.py` — matches S1-04 family convention (`tests/gates/...`); good | — |

No `RESCUE`-tier consistency findings — block-tier #1-#3 patch as outline +
test rewrites; the goal text required no edit.

### Design-patterns critic

| # | Severity | Finding | Fix applied |
|---|---|---|---|
| 1 | clean | **Adapter pattern is correctly framed** — `ObjectiveSignals` (Phase-5 sandbox-domain Pydantic) → `list[TrustSignal]` (Phase-3 trust-domain Pydantic) is a textbook anti-corruption-layer / hexagonal-port adapter. Note added in Implementer notes | — |
| 2 | harden | **Primitive obsession on the `(name → SignalKind)` translation.** Test fixtures pass raw `str` everywhere — `TrustSignal(kind=k, ...)` where `k: str`. Pydantic coerces, but the static surface loses the NewType discipline | AC-NEWTYPE-1: every `TrustSignal(kind=...)` call site in the adapter uses `SignalKind(name)`; AC-NEWTYPE-2: typing-level `get_type_hints` on adapter helper returns `list[SignalKind]` for the materialized kinds collection |
| 3 | harden | **`AttemptNumber` newtype unused.** S1-04 minted `AttemptNumber` for this exact downstream consumer. Draft outline uses `attempt=ctx.attempt` (`int`). Rule-of-three already cleared at S1-04. **Fix:** AC-ATTEMPT-1 mints `AttemptNumber(len(ctx.prior_attempts) + 1)` |
| 4 | harden | **Functional core / imperative shell.** Draft adapter mixes pure translation logic with the `Phase3TrustScorer()` call. The natural pure helper `_materialize_trust_signals(os, required) -> list[TrustSignal]` is unnamed. Mirrors `trust_scorer.py`'s `_compute_strict_and` discipline. **Fix:** Implementation outline now names two module-private pure helpers (`_materialize`, `_classify_retry`) at the top of `strict_and.py`, with `evaluate` as the only impure surface (constructs `TrustScorer`, calls `score()`) |
| 5 | clean | Functional / impure split now reflects the kernel's own discipline (Phase-3 `trust_scorer.py:96-123` factored two pure helpers ahead of `score()`); the parallel keeps consistency with the codebase convention | — |
| 6 | note (forward seam) | **Adapter is the first concrete `Gate` subclass.** A future `WeightedScoreGate` would also subclass `Gate` and follow the same shape (delegate to a scorer kernel). Rule-of-three is **not yet cleared** (StrictAndGate is N=1; LooseGate / WeightedGate would be N=2 / N=3). **No new abstraction extracted now** — defer per Rule 2. Recorded in Notes as forward seam | Notes added |
| 7 | note (forward seam) | **No `@register_gate` registry today.** The catalog loader (S1-06 / S5-02) instantiates concrete gates by `TransitionId` lookup. When a 2nd gate ships, the kernel-extract pattern from `signal_kinds.py` (registry-as-Final) is the precedent | Notes added |
| 8 | harden | **`GateMissingRequiredSignal.missing` typed attribute** vs message-parsing. Mirrors the `SignalKindAlreadyRegistered.{name, existing, duplicate}` typed-attribute pattern from `transforms/signal_kinds.py:69-75`. Forces operator tooling to dispatch on a typed field, not parse the exception message | AC-EXC-2 pins `.missing: tuple[SignalKind, ...]` typed attribute |
| 9 | harden | **Newtype `SignalKind` source-of-truth pinning** mirrors S1-04 AC-S/-A/-R: no `NewType("SignalKind", ...)` redefinition under `src/codegenie/gates/` | AC-NEWTYPE-3 mirrors S1-03 AC-4c chokepoint |
| 10 | harden | **Module purity** mirrors S1-04 AC-9a: `strict_and.py` may import only `{abc, typing, codegenie.errors, codegenie.types.identifiers, codegenie.gates.contract, codegenie.sandbox.signals.models, codegenie.transforms.outcomes, codegenie.transforms.trust_scorer, codegenie.transforms.signal_kinds, codegenie.plugins.events}` — `subprocess`, `os.system`, `pathlib.Path.write_*`, `logging`/`structlog`, `anthropic`/`langgraph` are forbidden | AC-PURITY-1 |

## Conflict resolution (Stage 4 synthesizer)

- **Coverage #3 (`failing_signals` sorted) vs codebase precedent
  (Phase-3 `TrustOutcome.failing` is caller-order):** Both are correct in
  their own scope. Phase-3's caller-order is the *scorer*'s contract;
  Phase-5's sorted is the *gate*'s contract (downstream consumers — ledger
  replay, Phase-6 reducer — want determinism independent of collector
  registration order). Resolution: gate derives its own sorted list from
  the populated `ObjectiveSignals` (NOT from `TrustOutcome.failing`).
  Documented in Notes as a deliberate departure that *protects* the
  equivalence property on `passed` while preventing accidental coupling
  to Phase-3's internal ordering.
- **Design-Patterns #1 (adapter framing) vs Rule 2 (no premature abstraction):**
  Rule 2 wins on extracting a `Gate` registry today (forward-seam note
  only). But the *adapter shape itself* is correctly framed — naming the
  pattern in the docstring helps the reader without adding code.
- **Design-Patterns #4 (functional core / imperative shell) vs Rule 2
  (no premature abstraction):** The two pure helpers (`_materialize`,
  `_classify_retry`) earn their keep because they each appear exactly
  once in `evaluate()` but each is independently testable — and the
  Phase-3 scorer's `_compute_strict_and` + `_has_adapter_degraded_*`
  split is a direct codebase precedent (Rule 11). Extracted.
- **Consistency #3 (`TransitionId` ≠ gate id) vs the draft's
  `gate_id=TransitionId.STAGE6_VALIDATE`:** The TransitionId is a closed
  Literal of stage-transition names; the gate id is the YAML catalog
  entry key. Until S1-06's catalog loader supplies a distinct typed gate
  identifier, the convention `gate_id = TransitionId.STAGE6_VALIDATE.value`
  is acceptable (str-mixin enum yields the value). Documented as Open
  ambiguity (resolved).

## Edits applied (summary)

1. **Validation notes block** added under the story header — 22 numbered
   headline edits.
2. **Acceptance criteria** rewritten from 11 ACs to ~40 ACs grouped A-N:
   A (constructor / import surface), B (gate ABC shape conformance), C
   (`evaluate` signature + pure-helper split), D (signal materialization
   `_materialize`), E (`failing_signals` deterministic sort + intersect),
   F (state / retryable cross-field), G (Phase-3 equivalence), H
   (attempt derivation from `prior_attempts`), I (exception shape +
   typed `.missing`), J (`summary` field shape), K (registry + import
   discipline), L (module purity + import allow-list), M (newtype
   source-of-truth pinning), N (process gates — LOC, coverage, fence,
   tooling).
3. **Implementation outline** rewritten end-to-end with correct
   constructor (`TrustScorer(event_log=...)`), correct imports, the two
   pure helpers (`_materialize`, `_classify_retry`), `AttemptNumber`
   derivation from `prior_attempts`, the `summary` format spec, and the
   open-ambiguity (resolved) note on gate-id conventions.
4. **TDD plan** rewritten — every test fixture now uses the correct
   imports, `_log(tmp_path)` Phase-3 event-log fixture, `SignalKind(...)`
   wrapping at every kind call site, `import codegenie.sandbox.signals`
   side-effect import (NOT a sidecar), and the rewritten property-test
   strategy (single `st.dictionaries`).
5. **Files to touch** unchanged in spirit; explicit columns added for
   "test imports" so the executor doesn't re-invent the path.
6. **Out of scope** expanded: `from_yaml` factory (S1-06 / S5-02 TBD),
   the `failed_unrecoverable` state (S5-02 GateRunner), the
   `ReplanHook` invocation (S5-01), `confidence`-as-first-class-field
   widening of `GateOutcome` (deferred to a future story — not S4-05's
   scope to widen the S1-04 contract).
7. **Notes for the implementer** rewritten and ~3× longer: adapter
   pattern framing, the deliberate `failing_signals` divergence from
   Phase-3 caller-order, the forward seam for `@register_gate` /
   `WeightedScoreGate`, the `AttemptNumber` derivation rationale, the
   `confidence` propagation decision, the `TrustScorer` construction
   discipline (stateless across calls per `trust_scorer.py:135-137`
   docstring), and the LOC-budget discipline.

No story restructuring; goal, scope, dependencies (S4-01..S4-04), and ADR
mapping (ADR-0003, ADR-0014) are unchanged.

## Final verdict

**HARDENED.** Story ready for `phase-story-executor`. Every AC is
individually verifiable; the AC set collectively guarantees the load-bearing
equivalence property on `passed` AND the gate-side `failing_signals`
determinism that Phase 6 / the ledger consume; every test in the TDD plan
would fail on at least one of the 18 enumerated mutations; CLAUDE.md Rule 11
(codebase convention) is honored (mirrors S1-04 / S4-04 precedents — `_log`
fixture pattern, side-effect import for kind registration, `.missing` typed
attribute, two-pure-helper functional-core split); the design-patterns
surface (adapter, functional-core/imperative-shell, AttemptNumber newtype,
no-sidecar-registration) is explicit; forward seams (`@register_gate`,
`WeightedScoreGate`, `from_yaml`, `confidence`-as-first-class) are
documented as Notes rather than over-specified now (Rule 2).
