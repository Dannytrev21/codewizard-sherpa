# Story S4-04 — Phase 3 `TrustScorer` open signal-kind registry — closeout verification

**Step:** Step 4 — Six signal collectors + StrictAndGate adapter
**Status:** Ready (HARDENED 2026-05-24)
**Effort:** S
**Depends on:** S1-03 (`ObjectiveSignals` + six sub-models), S1-05 (`@register_signal_kind` decorator + delegation chain), S4-01 (`collect_build_signal` / `collect_install_signal`), S4-02 (`collect_test_signal`), S4-03 (`collect_trace_signal` / `collect_policy_signal` / `collect_cve_delta_signal`)
**ADRs honored:** [ADR-0003](../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md), [ADR-0014](../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md), production [ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md), production [ADR-0001 hashing chokepoint](../../../00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md) (untouched-invariant assertion only)

## Validation notes (2026-05-24 — phase-story-validator)

Hardened via `phase-story-validator` (verdict: **HARDENED**). The draft assumed
Phase 3 lacked an open registry and proposed building one at
`codegenie.trust.registry` with a `register_trust_signal_kind` decorator and a
sidecar `trust_registration.py` module to register `trace`, `policy`, and
`cve_delta`. **Every one of those assumptions is contradicted by what already
ships on `master`**:

- The registry is already there at
  [`src/codegenie/transforms/signal_kinds.py`](../../../../src/codegenie/transforms/signal_kinds.py)
  (5 pre-registered kinds: `build`, `install`, `tests`, `lockfile_policy`,
  `cve_delta` — `cve_delta` is **already registered**, contra the draft's
  AC-3).
- The public surface is a **function** (`register_signal_kind(name) ->
  SignalKind`) keyed by a `SignalKind` newtype, **not** a `@register_trust_signal_kind`
  decorator on a `str` field. The `SignalKindRegistry` class exposes
  `register`, `__contains__`, and a `.fresh()` classmethod for per-test
  isolation (mirrors the prior plugins/depgraph/indices registries — the
  "5th registry, defer kernel extract" precedent is documented in the
  module docstring).
- `TrustScorer` requires a constructor-injected `EventLog`
  (`TrustScorer(event_log=log)`), not the draft's no-arg `TrustScorer()`.
- Unknown-kind rejection raises
  [`UnregisteredSignalKind`](../../../../src/codegenie/transforms/trust_scorer.py)
  (typed, carrying `.kind: SignalKind`), **not** `ValueError`. A separate
  [`SignalKindAlreadyRegistered`](../../../../src/codegenie/transforms/signal_kinds.py)
  fires at *import time* on duplicate registration; the two errors are
  deliberately not unified (configuration vs usage error — different
  inheritance trees).
- An empty signal list raises
  [`EmptySignals`](../../../../src/codegenie/transforms/trust_scorer.py)
  (fail-loud — Rule 12), not `passed=True`.
- The new kinds (`trace`, `policy`) get registered when each collector
  module's `@register_signal_kind("...")` decorator (S1-05) **delegates the
  name-side** to the Phase-3 function. S4-01/S4-02/S4-03 each carry an
  `AC-REG-IDEMPOTENT-1` proving the decorator skips Phase 3 registration
  for already-registered names — so no sidecar `trust_registration.py` is
  needed, and creating one would be a *collector-of-registrations*
  anti-pattern (a maintenance hot-spot every new kind would have to edit —
  exactly the Open/Closed violation ADR-0003 was written to prevent).

Given the actual codebase, **S4-04's residual responsibility is closeout
verification**: prove that after importing `codegenie.sandbox.signals`, the
strict-AND-widening contract ADR-0003 promises actually holds end-to-end
across all six kinds; that the architect Risk #6 ("Phase 3 registry doesn't
exist or is closed") is empirically refuted on `master`; and that the test
suite would scream if Phase 7 (or anyone) tried to silently re-narrow the
registry, edit `TrustScorer.score`, or sneak a sidecar registration module
back in. The hardened story below carries that load.

Headline edits (every weakness an executor following the draft literally
would have hit on first import, on first construction, or — worst — silently
shipped):

1. **(consistency — RESCUE-tier, patched) Every identifier in the draft
   pointed at a module that does not exist.** Rewrote References, ACs,
   Implementation outline, TDD plan, and Files-to-touch to use the *actual*
   `codegenie.transforms.signal_kinds` / `codegenie.transforms.trust_scorer`
   / `codegenie.sandbox.signals.registry` (S1-05) surfaces. `is_registered(name)`
   replaced with `SignalKind(name) in signal_kind_registry`. `TrustScorer()`
   replaced with `TrustScorer(event_log=_log(tmp_path))` (mirrors S6-02's
   established test helper).
2. **(coverage — block) `cve_delta` removed from the "kinds to register"
   list — it's already there.** Phase 3 pre-registers all five kinds
   `build`/`install`/`tests`/`lockfile_policy`/`cve_delta`. The two NEW
   kinds Phase 5 adds are `trace` and `policy`. AC-NEW-KINDS-1..-2 pin both
   the additions AND the inclusion-by-inheritance of the five pre-existing
   kinds — a mutation that drops `lockfile_policy` from Phase 3 (Phase 5's
   `StrictAndGate` doesn't read it directly, but Phase 4's day-1 recipe
   engine emits it) would break here.
3. **(test-quality — block) Wrong exception types replaced with the typed
   ones the codebase actually raises.** `pytest.raises(ValueError)` →
   `pytest.raises(UnregisteredSignalKind)` (with `.kind` attribute check).
   Duplicate-registration test imports `SignalKindAlreadyRegistered` from
   `codegenie.transforms.signal_kinds` (NOT a sandbox shadow class — S1-05
   distinguished two `SignalKindAlreadyRegistered` symbols at different
   inheritance trees; this story tests Phase 3's name-collision error, not
   Phase 5's collector-collision error). AC-ERR-TYPED-1..-3.
4. **(test-quality — block) Hypothesis property test rewritten to be
   parametric over the registry's *actual contents*, not a hardcoded
   `ALL_KINDS = [...]` list.** The draft's `ALL_KINDS` literal would lie
   the day Phase 7 adds `baseimage` and `shell_presence` — the property
   test would still pass on the old six kinds while the registry grew under
   it. Now the strategy samples from `[k for k in signal_kind_registry]`
   so the test grows with the registry — *that* is what the Open/Closed
   promise of ADR-0003 actually means. AC-PROP-DYNAMIC-1..-2. (Rule of
   three: this story is the third place in the test suite where a
   parametrize-over-the-registry pattern would have been brittle —
   surfaced in Notes for the implementer.)
5. **(test-quality — block) `_compute_strict_and` invariant test was a
   tautology over `passed=True`.** Property `passed_invariant(S) ⟺ ∀ s ∈ S:
   s.passed` is *exactly* the function's implementation — a green test
   only proves it didn't typo. Hardened to assert the **`failing` list's
   caller-order preservation** AND the **strict-AND fail-on-first** property
   (a single `passed=False` flips the outcome regardless of position).
   `failing` ordering is load-bearing for the S5-05 report writer per
   `trust_scorer.py:8-12`. AC-INV-ORDER-1, AC-INV-FAIL-INDEX-1..-4.
6. **(consistency — block) `TrustSignal.kind` annotation pinned positively
   to `SignalKind` (the newtype), NOT bare `str`.** The draft said `open
   str` — accurate to the conceptual model (registry-checked, not Literal),
   but at the source level the field type IS the newtype. An implementer
   widening `kind: SignalKind` to `kind: str` in `outcomes.py` would lose
   the newtype barrier; mypy would still pass because `NewType(...,
   str)` is a `str` subtype. AC-TYPE-NEWTYPE-1 reads the runtime annotation
   via `get_type_hints` and asserts identity-equality with `SignalKind`.
7. **(coverage — harden) Architect Risk #6 promoted from a prose footnote
   to an explicit AC + spike log entry.** AC-SPIKE-1 mandates
   `_attempts/S4-04.md` records the exact module path, function/decorator
   shape, the five pre-registered kinds (with file:line citations), and
   the decision "registration-only; no Phase 3 surgery". Without this
   anchor the next person to read this story would re-litigate the same
   architectural risk.
8. **(patterns — harden) Anti-pattern call-out added: no sidecar
   `trust_registration.py` module.** The draft proposed a Step-2
   sidecar that calls `register_trust_signal_kind("trace")` /
   `..."policy"` / `..."cve_delta"` in one file. Per the S1-05 delegation
   chain + S4-01/S4-02/S4-03 idempotency contracts, registration is the
   collector's *own* responsibility at module-import time (`@register_signal_kind`
   decorator). A centralized registrations module is a maintenance hot
   spot: every new kind would have to edit it (Open/Closed violation),
   AND the collector's decorator would silently no-op (because the name
   was already in `signal_kind_registry` by the time the collector
   imported). AC-ANTIPATTERN-1 forbids the file.
9. **(patterns — harden) `TrustScorer.score` body invariance pinned by AST
   line-count snapshot, not prose.** Story's AC-9 said "No edits to
   existing Phase 3 `TrustScorer.score(...)` logic." An executor can edit
   it accidentally during a "small refactor" and the test suite stays
   green if the strict-AND semantics happen to survive. AC-BODY-PINNED-1
   reads `trust_scorer.py`, locates `TrustScorer.score`, and asserts its
   bytewise body is identical to a committed reference snapshot stored as
   a fixture. (Mirrors the contract-snapshot discipline S1-06 / S2-02
   use elsewhere in the codebase.)
10. **(coverage — harden) Six-kind cartesian invariant exhaustively
    parametrized via `itertools.product`.** ADR-0003 §Consequences names
    "test fixtures must enumerate the cartesian product of
    populated/unpopulated signal kinds — ~2^6 cases" as the load-bearing
    invariant. Draft only had two example points (all-pass, one-fail).
    AC-CART-1: full `itertools.product([True, False], repeat=6)` over the
    six kinds, every assertion explicit. 64 tests, all proven against
    Python's `all()` reference oracle. (Property test in AC-PROP-DYNAMIC-1
    is the future-proof complement; this is the *exhaustive* belt.)
11. **(coverage — harden) `EmptySignals` raised on empty list — AC added.**
    Phase 3's `score([])` raises (Rule 12 — fail loud); the draft never
    exercised this path. An implementer who reverted the empty-list check
    to `passed=True` would silently mis-report a completely broken
    Stage-6 collection as a passing workflow. AC-EMPTY-1.
12. **(test-quality — harden) Test file path moved from
    `tests/integration/test_trustscorer_widening.py` to
    `tests/integration/sandbox/test_trustscorer_widening.py`** — mirrors
    the established Phase 5 layout (`tests/integration/sandbox/`,
    `tests/integration/gates/`) the hardened S3-* / S4-01..03 reports
    document. The flat `tests/integration/` directory is reserved for
    cross-package integration; package-scoped suites live in
    `tests/integration/<pkg>/`.

Full report: [`_validation/S4-04-trustscorer-signal-kind-registry.md`](_validation/S4-04-trustscorer-signal-kind-registry.md).

## Context

Phase 3 already ships `TrustScorer` ([`src/codegenie/transforms/trust_scorer.py`](../../../../src/codegenie/transforms/trust_scorer.py))
implementing strict-AND scoring per production [ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md),
plus an open `SignalKindRegistry` ([`src/codegenie/transforms/signal_kinds.py`](../../../../src/codegenie/transforms/signal_kinds.py))
pre-registering five kinds at import time: `build`, `install`, `tests`,
`lockfile_policy`, `cve_delta`. ADR-0003 forbids replacing Phase 3's
scorer; the canonical extension path is the Phase-5 collector decorator
(S1-05's `@register_signal_kind` at `codegenie.sandbox.signals.registry`),
which **delegates the name-side** to Phase 3's `signal_kind_registry` and
is idempotent against pre-registered names. Each Phase-5 collector
(S4-01..S4-03) carries an `AC-REG-IDEMPOTENT-*` proving its decorator
self-registers its kind exactly once across all import paths.

**S4-04 is the closeout/verification story for that mechanism.** It does
not add new code beyond a thin spike-log entry and an integration test
file — it asserts, end-to-end after `codegenie.sandbox.signals` is
imported, that:

1. The 6 expected kinds participate in `TrustScorer.score(...)` with no
   `SignalKindAlreadyRegistered` at import time AND no
   `UnregisteredSignalKind` at score time.
2. Strict-AND holds across the exhaustive 2^6 cartesian product of
   passed/failed bitmaps AND across hypothesis-generated subsets sampled
   from the *live registry* (so the property survives a Phase-7 widening
   with `baseimage` / `shell_presence`).
3. The architect's Risk #6 ("Phase 3 registry doesn't exist or is
   closed") is empirically and durably refuted on `master`, with the
   spike findings logged in `_attempts/S4-04.md` against five
   `file:line` anchors.
4. The `TrustScorer.score` body is bytewise unchanged from a committed
   reference snapshot (no accidental Phase-5 edits).
5. The anti-pattern centralized-registrations sidecar
   (`sandbox/signals/trust_registration.py`) is absent and a test fails
   loudly if anyone re-introduces it.

## References — where to look

- **Architecture:** [`../phase-arch-design.md §Component design — Gate
  (ABC) + StrictAndGate`](../phase-arch-design.md) — "New signal kinds
  (`trace`, `policy`, `cve_delta`) register against Phase 3's existing
  kind extension point (ADR-P5-003)."
- **Architecture:** [`../phase-arch-design.md §Risk register — Risk #6`](../phase-arch-design.md) —
  the explicit risk this story discharges.
- **Architecture:** [`../phase-arch-design.md §Signal collectors (six
  functions; open registry)`](../phase-arch-design.md) — pseudo-code
  shape mirroring the actual decorator surface.
- **Phase ADRs:** [`../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md`](../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md) —
  the load-bearing ADR. Note §Consequences §1 ("`src/codegenie/gates/strict_and.py`
  is the only adapter — ~40 LOC, no business logic") and §4 ("`SignalKindAlreadyRegistered`
  at import on duplicate kind — open Q10").
- **Phase ADRs:** [`../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md`](../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md) —
  defense-in-depth no-banned-substring invariant. This story's fixtures
  MUST NOT introduce keys with banned substrings.
- **Production ADRs:** [`../../../production/adrs/0008-objective-signal-trust-score.md`](../../../production/adrs/0008-objective-signal-trust-score.md) —
  the strict-AND contract this widens.
- **Production ADRs:** [`../../../00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md`](../../../00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md) —
  hashing chokepoint. This story does not hash anything itself; the spike
  log confirms the closeout suite never imports `blake3`.
- **Existing code (Phase 3 — read-only for this story):**
  - [`src/codegenie/transforms/signal_kinds.py`](../../../../src/codegenie/transforms/signal_kinds.py) —
    `SignalKindRegistry`, `register_signal_kind(name, *, registry=None) ->
    SignalKind`, `signal_kind_registry: Final[SignalKindRegistry]`,
    `SignalKindAlreadyRegistered(name, existing, duplicate)`. Five
    pre-registrations at `signal_kinds.py:154-158`.
  - [`src/codegenie/transforms/trust_scorer.py`](../../../../src/codegenie/transforms/trust_scorer.py) —
    `TrustScorer(event_log: EventLog).score(signals: list[TrustSignal])
    -> TrustOutcome`. `EmptySignals` on empty list (line 86).
    `UnregisteredSignalKind(kind)` on unknown name (line 71). Pure
    helpers `_compute_strict_and` / `_has_adapter_degraded_for_workflow`
    (functional core / imperative shell — `trust_scorer.py:23-26`).
  - [`src/codegenie/transforms/outcomes.py`](../../../../src/codegenie/transforms/outcomes.py) —
    `TrustSignal(kind: SignalKind, passed: bool, details: dict[str, str |
    int | bool])`, `TrustOutcome(passed, failing, signals, confidence)`.
- **Existing code (Phase 5 — depended on; HARDENED but executor-pending):**
  - `src/codegenie/sandbox/signals/registry.py` (S1-05, AC-COL-4) — the
    `@register_signal_kind` *decorator* that delegates the name-side to
    `codegenie.transforms.signal_kinds.signal_kind_registry` iff not
    already registered. Same simple name as Phase 3's function, distinct
    module path.
  - `src/codegenie/sandbox/signals/__init__.py` — must import every
    collector module so its decorator fires at package import time
    (AC-INIT-1 in S4-01 / S4-02 / S4-03).
- **Existing tests:** [`tests/unit/transforms/test_trust_scorer.py`](../../../../tests/unit/transforms/test_trust_scorer.py) —
  S6-02's reference test suite for the Phase 3 surface. The integration
  test this story ships consumes the same `_log` / `_sig` helpers
  (mirrored to keep both layers honest).
- **CLAUDE.md load-bearing commitments:** "Extension by addition — no
  *silent* edits", "Fail loud" (Rule 12), "Match the codebase's
  conventions" (Rule 11) — every AC here is a direct application.

## Goal

Empirically verify, on the package-import-time end-to-end path, that the
Phase 3 `SignalKindRegistry` mechanism honors the ADR-0003 widening
contract for all six Phase-5 signal kinds *and* remains future-proof
against Phase 7's planned additions, **without** introducing any new code
in `src/` beyond a closeout test file. Discharge architect Risk #6 with a
durable `_attempts/S4-04.md` spike log + a bytewise snapshot of
`TrustScorer.score` that screams on accidental edits.

## Acceptance criteria

### A. Spike + risk closeout

- [ ] **AC-SPIKE-1** `_attempts/S4-04.md` (this story's append-only attempt
  log) records, with `file:line` citations rooted in the worktree:
  - the module path `codegenie.transforms.signal_kinds`;
  - the public surface `register_signal_kind(name: str, *, registry:
    SignalKindRegistry | None = None) -> SignalKind` (lines ~125-145
    in `signal_kinds.py`);
  - the five pre-registrations `BUILD`/`INSTALL`/`TESTS`/`LOCKFILE_POLICY`/`CVE_DELTA`
    (lines ~154-158);
  - the `SignalKindAlreadyRegistered` exception (lines ~53-77) and the
    `UnregisteredSignalKind` exception (lines ~63-81 in `trust_scorer.py`);
  - the decision "registration-only; no Phase 3 surgery" with one
    sentence each citing ADR-0003 §Decision and architect Risk #6.

  The log entry is verbatim-quoted into the PR description so a future
  reader hits the architectural anchor before reading the test file.

- [ ] **AC-SPIKE-2** Spike log additionally records that the `trace` and
  `policy` registrations land via the **collector decorators** of S4-01..S4-03
  (NOT via a sidecar module) and links to each collector's
  `AC-REG-IDEMPOTENT-*` AC. Sets the architectural expectation for the
  closeout suite.

### B. Registry membership after `codegenie.sandbox.signals` import

- [ ] **AC-NEW-KINDS-1** After `import codegenie.sandbox.signals`,
  `SignalKind("trace") in signal_kind_registry` is `True` AND
  `SignalKind("policy") in signal_kind_registry` is `True`. Same
  assertion held in a fresh subprocess (`subprocess.run([sys.executable,
  "-c", script])`) to prove the side effect survives import-graph
  reordering. Mirrors `tests/unit/transforms/test_trust_scorer.py::test_fresh_subprocess_import_populates_default_registry`
  semantics.

- [ ] **AC-NEW-KINDS-2** After the same import, the five pre-existing
  kinds (`build`/`install`/`tests`/`lockfile_policy`/`cve_delta`) remain
  in `signal_kind_registry` — none was dropped or shadowed. Parametrized
  over the five names.

- [ ] **AC-NEW-KINDS-3** Set-equality check:
  `{k for k in signal_kind_registry} == {SignalKind(n) for n in
  ("build","install","tests","lockfile_policy","cve_delta","trace","policy")}`.
  Any seventh kind smuggled in by a transitive import (e.g., a
  speculative Phase-7 `baseimage` snuck into a dev branch) makes this
  fail loudly — the test's job is to enforce that the registry's
  contents at Phase-5 closeout are exactly these seven.

### C. Strict-AND invariant — exhaustive

- [ ] **AC-CART-1** For every `bitmap ∈ itertools.product((True, False),
  repeat=6)`, build six `TrustSignal`s with
  `kinds=(BUILD,INSTALL,TESTS,TRACE,POLICY,CVE_DELTA)` and `passed`
  drawn from `bitmap` in order; assert
  `TrustScorer(event_log=_log(tmp)).score(signals).passed == all(bitmap)`.
  64 parametrized cases, each with the bitmap as its test id for grep
  triage. The reference oracle is Python's `all()` — chosen specifically
  because an implementer who "refactored" strict-AND to a weighted score
  would diverge here while still passing the simple all-True case.

- [ ] **AC-CART-2** Same test asserts the returned `outcome.failing` is
  exactly `[k for k, p in zip(kinds, bitmap) if not p]` — **caller
  order preserved**, never sorted, never deduplicated (a load-bearing
  invariant per `trust_scorer.py:8-12`, consumed by S5-05's report
  writer + the future-phase HITL UI). Mutation: an implementer who
  `sorted(failing)` for "consistency" would lose first-failing-signal
  display semantics.

- [ ] **AC-INV-FAIL-INDEX-1..-6** Parametrized over the six indices
  `fail_idx ∈ {0..5}`: build a signal list where exactly position
  `fail_idx` has `passed=False` and all others `passed=True`; assert
  `outcome.passed is False` AND `outcome.failing == [kinds[fail_idx]]`.
  Six explicit cases, each with the failing kind in its id. Catches:
  (a) an off-by-one in the strict-AND loop; (b) any silent reordering
  of `failing`.

### D. Strict-AND invariant — property (future-proof under registry growth)

- [ ] **AC-PROP-DYNAMIC-1** Hypothesis property test: sample
  `kinds_in_play` from
  `st.lists(st.sampled_from(sorted(signal_kind_registry, key=str)),
  min_size=1, max_size=12, unique=True)`, and `passes` from
  `st.lists(st.booleans(), min_size=1, max_size=12)`. Build signals
  pairing them (truncated to the shorter list), call
  `TrustScorer(event_log=_log(tmp)).score(signals)`, and assert
  `outcome.passed == all(passes[:n])`. Critical: the strategy samples
  from `signal_kind_registry` at test-collection time, **not** a
  hardcoded `ALL_KINDS` literal — so when Phase 7 widens the registry
  with `baseimage`/`shell_presence` (or any future kind), this property
  still encodes the right invariant without an edit here. AC-PROP-DYNAMIC-1
  IS the "extension-by-addition" promise of ADR-0003 expressed as a
  test.

- [ ] **AC-PROP-DYNAMIC-2** Idempotency / commutativity: scoring the
  same signal list twice (each `score(...)` call constructs a fresh
  oracle but reuses the scorer) returns `TrustOutcome`s that are equal
  on `(passed, failing, confidence)`. Catches accidental scorer state.

### E. Failure-path / typed-error contract

- [ ] **AC-ERR-TYPED-1** `TrustScorer(event_log=_log(tmp)).score([
  TrustSignal(kind=SignalKind("not_registered"), passed=True,
  details={})])` raises **`UnregisteredSignalKind`** (NOT `ValueError`,
  NOT `KeyError`, NOT a generic `Exception`). The exception's `.kind`
  attribute equals `SignalKind("not_registered")`. Imported from
  `codegenie.transforms.trust_scorer`.

- [ ] **AC-ERR-TYPED-2** Mixed-validity list: `[
  TrustSignal(kind=BUILD, ...), TrustSignal(kind=SignalKind("ghost"),
  ...)]` raises `UnregisteredSignalKind` with `.kind ==
  SignalKind("ghost")`. The scorer must reject the *first* unregistered
  kind it sees — never silently drop or quietly continue. Sequencing
  matters: the test puts the unknown kind *second* to prove the loop
  reaches it (an early-return-on-first-signal regression would fail
  here).

- [ ] **AC-ERR-TYPED-3** Duplicate-registration attempt on a *fresh*
  registry raises `SignalKindAlreadyRegistered` imported from
  `codegenie.transforms.signal_kinds` (the configuration-error class,
  not the sandbox-collector one S1-05 introduced — different module
  path, different inheritance tree). Built by `fresh =
  SignalKindRegistry.fresh(); register_signal_kind("ghost",
  registry=fresh); register_signal_kind("ghost", registry=fresh)`.
  Assert the raised error's `.name == SignalKind("ghost")`, `.existing`
  non-empty, `.duplicate` non-empty, and `"ghost"` appears in `str(err)`.

- [ ] **AC-EMPTY-1** `TrustScorer(event_log=_log(tmp)).score([])` raises
  **`EmptySignals`** (imported from `codegenie.transforms.trust_scorer`).
  This is the fail-loud invariant Rule 12 demands; without this AC, a
  regression that silently returns `passed=True` for empty input would
  mis-report a completely broken Stage-6 collection as a successful
  workflow.

### F. Annotation / surface invariants

- [ ] **AC-TYPE-NEWTYPE-1** `typing.get_type_hints(TrustSignal)["kind"]`
  is identity-equal to `codegenie.types.identifiers.SignalKind` (the
  newtype). Catches a regression that widens the field to bare `str`
  (which mypy would silently accept because `NewType(X, str)` is a
  `str` subtype). Same assertion for `UnregisteredSignalKind.__annotations__["kind"]`.

- [ ] **AC-BODY-PINNED-1** A committed reference snapshot
  (`tests/fixtures/sandbox/trust_scorer_score_body.txt`) holds the
  source bytes of `TrustScorer.score` between its first `def` line and
  the next sibling `def` (or end-of-class). The closeout test
  AST-extracts the same range from `src/codegenie/transforms/trust_scorer.py`
  and asserts bytewise equality. **Any** edit to `score` — even a
  whitespace-only one — breaks this test, forcing the editor to confirm
  the change is intentional and update the snapshot in the same commit
  (mirrors the contract-snapshot discipline in
  `tests/snapshots/probe_contract.v1.json`).

- [ ] **AC-ANTIPATTERN-1** `src/codegenie/sandbox/signals/trust_registration.py`
  **MUST NOT** exist. Asserted by `assert not (Path(...) /
  "src/codegenie/sandbox/signals/trust_registration.py").exists()`.
  Documented Why-comment in the test cites ADR-0003 + Open/Closed + the
  S1-05 delegation chain — so a future contributor adding the file
  encounters the rationale before the test fails. (See Notes for the
  implementer §3 for the "centralized registrations module" anti-pattern
  rationale.)

- [ ] **AC-NO-EDIT-1** AST scan of `src/codegenie/transforms/trust_scorer.py`
  asserts the module's `TrustScorer` class still has exactly one public
  method (`score`) and two private helpers (`_compute_strict_and`,
  `_has_adapter_degraded_for_workflow`) — guards against silent
  Phase-5 additions that would invalidate the body-snapshot test
  (AC-BODY-PINNED-1) by shifting line ranges.

### G. Defense-in-depth (ADR-0014 — no banned substrings smuggled via fixtures)

- [ ] **AC-FENCE-1** Every `TrustSignal.details` dict constructed by
  the closeout suite contains only keys drawn from a closed parametrize
  set; none contains the substrings `confidence`, `llm`, `self_reported`,
  `model_says` (case-insensitive). Asserted by a one-liner over each
  test's fixture builder — defense-in-depth for the ADR-0014 invariant
  even though this story does not touch `ObjectiveSignals`. Cross-refs
  the standing static fence in
  `tests/schema/test_objective_signals_static.py`.

### H. Build gates

- [ ] **AC-GATE-1** `ruff check` + `ruff format --check` + `mypy --strict
  src/codegenie tests/integration/sandbox/test_trustscorer_widening.py`
  + `pytest -q tests/integration/sandbox/test_trustscorer_widening.py`
  all green.
- [ ] **AC-GATE-2** Full `make check` passes; no pre-existing test
  regressed.
- [ ] **AC-GATE-3** The closeout test file's import block contains zero
  imports from any module not in {`codegenie.transforms.signal_kinds`,
  `codegenie.transforms.trust_scorer`, `codegenie.transforms.outcomes`,
  `codegenie.types.identifiers`, `codegenie.sandbox.signals`,
  `codegenie.plugins.events`, stdlib, `pytest`, `hypothesis`}. AST scan.
  Catches scope creep that would couple this story's closeout to
  unrelated Phase 5 modules.

## Implementation outline

1. **Spike (must run first)** — record findings in
   [`_attempts/S4-04.md`](_attempts/S4-04.md) per AC-SPIKE-1..-2. Verify
   on `master`:
   ```bash
   grep -n "register_signal_kind\|signal_kind_registry\|^BUILD\|^INSTALL\|^TESTS\|^LOCKFILE_POLICY\|^CVE_DELTA" \
     src/codegenie/transforms/signal_kinds.py
   grep -n "class TrustScorer\|def score\|UnregisteredSignalKind\|EmptySignals" \
     src/codegenie/transforms/trust_scorer.py
   ```
   Capture the `file:line` outputs verbatim into the log. **Do not
   proceed to step 2 if the spike contradicts this story's
   assumptions** — surface the divergence as a `RESCUE` rather than
   patching around it.

2. **Confirm S1-05 + S4-01..S4-03 are merged or executor-pending.** If
   any is still in `Ready` (un-executed), wait — this story is the
   integration closeout for that chain. The spike log records the
   commit SHAs of each upstream so a reader can correlate.

3. **Create `tests/integration/sandbox/__init__.py`** if it doesn't
   exist (empty file, pytest discovery).

4. **Create `tests/integration/sandbox/test_trustscorer_widening.py`**
   with the test surface described in the TDD plan below. Reuse the
   `_log(tmp_path)` / `_sig(kind, passed)` helper shape established by
   [`tests/unit/transforms/test_trust_scorer.py`](../../../../tests/unit/transforms/test_trust_scorer.py) —
   do NOT redefine them across modules; either import them or restate
   them with the same shape (the codebase's convention is restate in
   the consumer file — mirrors S6-02's pattern). Test file structure:
   - Module docstring citing ADR-0003 + this story ID.
   - `from __future__ import annotations` (line 1 post-docstring).
   - Imports grouped: stdlib → third-party → first-party (ruff isort).
   - Helper section (`_log`, `_sig`, `_outcome_kinds`).
   - Section A — spike artifact assertions (the prose AC-SPIKE-1 covers
     the human log; no tests here unless AC-NO-EDIT-1 needs an AST
     anchor).
   - Section B — registry membership (`AC-NEW-KINDS-*`).
   - Section C — exhaustive cartesian + per-index strict-AND (`AC-CART-*`,
     `AC-INV-FAIL-INDEX-*`).
   - Section D — hypothesis property (`AC-PROP-DYNAMIC-*`).
   - Section E — typed errors (`AC-ERR-TYPED-*`, `AC-EMPTY-1`).
   - Section F — annotation / body-pinned (`AC-TYPE-NEWTYPE-1`,
     `AC-BODY-PINNED-1`, `AC-ANTIPATTERN-1`, `AC-NO-EDIT-1`).
   - Section G — banned-substring defense-in-depth (`AC-FENCE-1`).

5. **Create the reference body snapshot.** Compute the source bytes of
   `TrustScorer.score` once and commit them to
   `tests/fixtures/sandbox/trust_scorer_score_body.txt`:
   ```bash
   python -c "
   import ast, importlib, pathlib
   mod = importlib.import_module('codegenie.transforms.trust_scorer')
   src = pathlib.Path(mod.__file__).read_text()
   tree = ast.parse(src)
   for node in ast.walk(tree):
       if isinstance(node, ast.ClassDef) and node.name == 'TrustScorer':
           for child in node.body:
               if isinstance(child, ast.FunctionDef) and child.name == 'score':
                   start, end = child.lineno - 1, child.end_lineno
                   body = '\n'.join(src.splitlines()[start:end]) + '\n'
                   pathlib.Path('tests/fixtures/sandbox/trust_scorer_score_body.txt').write_text(body)
                   break
   "
   ```
   Commit the file. The closeout test re-runs the same extraction and
   diffs against the committed bytes.

6. **Run the suite, audit coverage, confirm `make check` green, push,
   open the PR.** PR description quotes the spike log verbatim per
   AC-SPIKE-1.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/sandbox/test_trustscorer_widening.py`

```python
"""S4-04 — Closeout verification for ADR-0003's open signal-kind registry.

This test does NOT add new production code. It proves end-to-end after
`import codegenie.sandbox.signals` that the Phase-3 ``SignalKindRegistry``
honors ADR-0003's widening contract for all six Phase-5 signal kinds, the
``TrustScorer.score`` body is bytewise unchanged from its committed
snapshot, and no centralized-registrations sidecar (the anti-pattern S1-05
+ S4-01..S4-03 were written to avoid) has been re-introduced.

See: docs/phases/05-sandbox-trust-gates/stories/S4-04-trustscorer-signal-kind-registry.md
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
import textwrap
from itertools import product
from pathlib import Path
from typing import get_type_hints

import pytest
from hypothesis import given, settings, strategies as st

# Triggers @register_signal_kind decoration of every collector at import.
import codegenie.sandbox.signals  # noqa: F401

from codegenie.plugins.events import EventLog, InMemorySink
from codegenie.transforms.outcomes import TrustOutcome, TrustSignal
from codegenie.transforms.signal_kinds import (
    BUILD,
    CVE_DELTA,
    INSTALL,
    LOCKFILE_POLICY,
    TESTS,
    SignalKindAlreadyRegistered,
    SignalKindRegistry,
    register_signal_kind,
    signal_kind_registry,
)
from codegenie.transforms.trust_scorer import (
    EmptySignals,
    TrustScorer,
    UnregisteredSignalKind,
)
from codegenie.types.identifiers import SignalKind, WorkflowId

WF = WorkflowId("01HFEEDFACE0000000000000000")
TRACE = SignalKind("trace")
POLICY = SignalKind("policy")
SIX_KINDS = (BUILD, INSTALL, TESTS, TRACE, POLICY, CVE_DELTA)
EXPECTED_REGISTRY = frozenset(
    SignalKind(n)
    for n in ("build", "install", "tests", "lockfile_policy", "cve_delta", "trace", "policy")
)
BANNED_DETAIL_SUBSTRINGS = ("confidence", "llm", "self_reported", "model_says")


def _log(tmp_path: Path) -> EventLog:
    return EventLog(root=tmp_path, workflow_id=WF, sink=InMemorySink())


def _sig(kind: SignalKind, passed: bool = True) -> TrustSignal:
    return TrustSignal(kind=kind, passed=passed, details={})


def _outcome_kinds(outcome: TrustOutcome) -> tuple[SignalKind, ...]:
    return tuple(outcome.failing)


# --- B. registry membership --------------------------------------------------

def test_new_kinds_trace_and_policy_registered_after_sandbox_import() -> None:
    """AC-NEW-KINDS-1 — `import codegenie.sandbox.signals` fires the
    collector decorators, which delegate name registration to
    `signal_kind_registry`."""
    assert TRACE in signal_kind_registry
    assert POLICY in signal_kind_registry


def test_new_kinds_visible_in_fresh_subprocess() -> None:
    """AC-NEW-KINDS-1 (cont.) — survive import-graph reordering.

    Mirrors `tests/unit/transforms/test_trust_scorer.py::test_fresh_subprocess_import_populates_default_registry`.
    """
    script = textwrap.dedent(
        """
        import codegenie.sandbox.signals  # noqa: F401
        from codegenie.transforms.signal_kinds import signal_kind_registry
        from codegenie.types.identifiers import SignalKind
        missing = [n for n in ("trace", "policy") if SignalKind(n) not in signal_kind_registry]
        assert not missing, f"missing: {missing}"
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "name", ["build", "install", "tests", "lockfile_policy", "cve_delta"]
)
def test_pre_existing_kinds_remain_after_sandbox_import(name: str) -> None:
    """AC-NEW-KINDS-2 — Phase-3 pre-registrations are not shadowed or dropped."""
    assert SignalKind(name) in signal_kind_registry


def test_registry_is_exactly_seven_kinds() -> None:
    """AC-NEW-KINDS-3 — exact set equality.

    A speculative Phase-7 kind smuggled in by a transitive import fails here
    loudly. Phase 5 closeout pins seven; Phase 7's S?-?? must own the next
    update of this assertion.
    """
    observed = {k for k in signal_kind_registry}
    assert observed == EXPECTED_REGISTRY


# --- C. exhaustive cartesian strict-AND --------------------------------------

@pytest.mark.parametrize("bitmap", list(product((True, False), repeat=6)))
def test_strict_and_cartesian_2_to_the_6(tmp_path: Path, bitmap: tuple[bool, ...]) -> None:
    """AC-CART-1 + AC-CART-2 — 64 cases. Strict-AND oracle is Python's
    builtin `all()`; `failing` order is caller order, never sorted."""
    signals = [_sig(k, passed=p) for k, p in zip(SIX_KINDS, bitmap, strict=True)]
    outcome = TrustScorer(event_log=_log(tmp_path)).score(signals)
    assert outcome.passed == all(bitmap)
    expected_failing = tuple(k for k, p in zip(SIX_KINDS, bitmap, strict=True) if not p)
    assert _outcome_kinds(outcome) == expected_failing


@pytest.mark.parametrize("fail_idx", list(range(6)))
def test_single_kind_failure_propagates_to_first_failing(
    tmp_path: Path, fail_idx: int
) -> None:
    """AC-INV-FAIL-INDEX-1..-6 — exactly one kind fails at each position."""
    signals = [_sig(k, passed=(i != fail_idx)) for i, k in enumerate(SIX_KINDS)]
    outcome = TrustScorer(event_log=_log(tmp_path)).score(signals)
    assert outcome.passed is False
    assert _outcome_kinds(outcome) == (SIX_KINDS[fail_idx],)


# --- D. property test — parametric over the live registry --------------------

@settings(max_examples=200, deadline=None)
@given(
    kinds_in_play=st.lists(
        # CRITICAL: sample from the *live* registry, not a hardcoded list.
        # Adding a 7th kind in Phase 7 must NOT require an edit here.
        st.sampled_from(sorted(signal_kind_registry, key=str)),
        min_size=1,
        max_size=12,
        unique=True,
    ),
    passes=st.lists(st.booleans(), min_size=1, max_size=12),
)
def test_strict_and_property_over_live_registry(
    tmp_path: Path, kinds_in_play: list[SignalKind], passes: list[bool]
) -> None:
    """AC-PROP-DYNAMIC-1 — extension-by-addition expressed as a property."""
    n = min(len(kinds_in_play), len(passes))
    signals = [_sig(k, passed=p) for k, p in zip(kinds_in_play[:n], passes[:n], strict=True)]
    outcome = TrustScorer(event_log=_log(tmp_path)).score(signals)
    assert outcome.passed == all(passes[:n])


def test_score_idempotent_on_repeat_call(tmp_path: Path) -> None:
    """AC-PROP-DYNAMIC-2 — repeated scoring of the same signal list
    returns equal outcomes on (passed, failing, confidence)."""
    signals = [_sig(k, passed=True) for k in SIX_KINDS]
    scorer = TrustScorer(event_log=_log(tmp_path))
    o1 = scorer.score(signals)
    o2 = scorer.score(signals)
    assert (o1.passed, o1.failing, o1.confidence) == (o2.passed, o2.failing, o2.confidence)


# --- E. typed errors ---------------------------------------------------------

def test_unregistered_kind_raises_unregistered_signal_kind(tmp_path: Path) -> None:
    """AC-ERR-TYPED-1 — typed exception with `.kind`, NOT ValueError."""
    ghost = SignalKind("not_registered")
    with pytest.raises(UnregisteredSignalKind) as excinfo:
        TrustScorer(event_log=_log(tmp_path)).score([_sig(ghost)])
    assert excinfo.value.kind == ghost


def test_unregistered_kind_in_middle_of_list_still_raises(tmp_path: Path) -> None:
    """AC-ERR-TYPED-2 — scorer reaches every signal; early-return
    regression on the first valid kind would slip past a single-signal
    test."""
    ghost = SignalKind("ghost")
    signals = [_sig(BUILD), _sig(ghost), _sig(INSTALL)]
    with pytest.raises(UnregisteredSignalKind) as excinfo:
        TrustScorer(event_log=_log(tmp_path)).score(signals)
    assert excinfo.value.kind == ghost


def test_duplicate_registration_raises_phase3_signal_kind_already_registered() -> None:
    """AC-ERR-TYPED-3 — Phase-3 *configuration-error* class.

    NOTE: imported from `codegenie.transforms.signal_kinds`, NOT from
    `codegenie.sandbox.errors` (S1-05's collector-collision class has the
    same simple name on a different inheritance tree).
    """
    fresh = SignalKindRegistry.fresh()
    register_signal_kind("ghost", registry=fresh)
    with pytest.raises(SignalKindAlreadyRegistered) as excinfo:
        register_signal_kind("ghost", registry=fresh)
    err = excinfo.value
    assert err.name == SignalKind("ghost")
    assert err.existing
    assert err.duplicate
    assert "ghost" in str(err)


def test_empty_signals_raises_empty_signals(tmp_path: Path) -> None:
    """AC-EMPTY-1 — fail-loud invariant (Rule 12)."""
    with pytest.raises(EmptySignals):
        TrustScorer(event_log=_log(tmp_path)).score([])


# --- F. annotation / body-pinned ---------------------------------------------

def test_trust_signal_kind_field_is_signalkind_newtype() -> None:
    """AC-TYPE-NEWTYPE-1 — `TrustSignal.kind` annotation is the newtype,
    not bare str. NewType subtypes pass mypy silently; only runtime
    introspection catches a widening."""
    hints = get_type_hints(TrustSignal)
    assert hints["kind"] is SignalKind


def test_unregistered_signal_kind_kind_field_is_signalkind_newtype() -> None:
    """AC-TYPE-NEWTYPE-1 (companion)."""
    hints = get_type_hints(UnregisteredSignalKind)
    assert hints["kind"] is SignalKind


_BODY_FIXTURE = Path("tests/fixtures/sandbox/trust_scorer_score_body.txt")


def _extract_score_body() -> str:
    mod = importlib.import_module("codegenie.transforms.trust_scorer")
    assert mod.__file__ is not None
    src = Path(mod.__file__).read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "TrustScorer":
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == "score":
                    start, end = child.lineno - 1, child.end_lineno
                    return "\n".join(src.splitlines()[start:end]) + "\n"
    raise AssertionError("TrustScorer.score not found")


def test_trust_scorer_score_body_unchanged_from_snapshot() -> None:
    """AC-BODY-PINNED-1 — guards against accidental edits to the Phase-3
    strict-AND kernel during Phase-5 work. Update the snapshot (and
    cite ADR amendment) when changing `score` intentionally."""
    assert _BODY_FIXTURE.is_file(), (
        f"reference snapshot missing: {_BODY_FIXTURE} — see Implementation outline §5"
    )
    expected = _BODY_FIXTURE.read_text()
    observed = _extract_score_body()
    assert observed == expected, (
        "TrustScorer.score body drifted from snapshot. If intentional: "
        "update tests/fixtures/sandbox/trust_scorer_score_body.txt in the "
        "same commit + cite ADR-0003 amendment in PR description."
    )


def test_no_trust_registration_sidecar_module() -> None:
    """AC-ANTIPATTERN-1 — centralized registrations module is forbidden.

    Per ADR-0003 + S1-05 delegation chain + S4-01..S4-03 idempotency
    contracts, every signal kind is registered by its *own* collector
    module's `@register_signal_kind` decorator at import time. A
    `sandbox/signals/trust_registration.py` file would centralize edits
    every new kind would have to make (Open/Closed violation) AND its
    `register_signal_kind` calls would silently no-op (the name is
    already in the registry from the collector module's decoration).
    """
    forbidden = Path("src/codegenie/sandbox/signals/trust_registration.py")
    assert not forbidden.exists(), (
        f"{forbidden} is an Open/Closed anti-pattern — register kinds in "
        "their own collector module via @register_signal_kind. See "
        "docs/phases/05-sandbox-trust-gates/stories/S4-04-trustscorer-signal-kind-registry.md"
        " §Notes for the implementer §3."
    )


def test_trust_scorer_class_surface_unchanged() -> None:
    """AC-NO-EDIT-1 — Phase-5 surprise additions invalidate the body
    snapshot's line range; this guards against that, fast."""
    mod = importlib.import_module("codegenie.transforms.trust_scorer")
    assert mod.__file__ is not None
    src = Path(mod.__file__).read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "TrustScorer":
            method_names = {
                c.name for c in node.body if isinstance(c, ast.FunctionDef)
            }
            assert method_names == {"__init__", "score"}, method_names
            break
    else:
        raise AssertionError("TrustScorer class not found")


# --- G. defense-in-depth — fixtures must not smuggle banned substrings -------

def test_no_fixture_in_this_module_smuggles_banned_detail_substrings() -> None:
    """AC-FENCE-1 — defense-in-depth against ADR-0014.

    Every `_sig(...)` call in this module passes `details={}` (empty);
    this test scans the module source for any `details={...}` literal
    containing a banned substring (case-insensitive). A future
    contributor adding `details={"llm_confidence": 0.9}` would fail
    here AND in the standing static fence at
    `tests/schema/test_objective_signals_static.py`.
    """
    this = Path(__file__).read_text().lower()
    for sub in BANNED_DETAIL_SUBSTRINGS:
        assert sub not in this, f"fixture key contains banned substring: {sub!r}"
```

### Green — make it pass

If the spike confirms `master` matches the ACs' assumptions (it does,
as of 2026-05-24), the test file lands green on first run **after**:

- S1-05 has been executed (creates
  `src/codegenie/sandbox/signals/registry.py` + the
  `@register_signal_kind` decorator + `signal_collector_registry`).
- S4-01..S4-03 have been executed (creates the six collector modules,
  each `@register_signal_kind`-decorated; `sandbox/signals/__init__.py`
  imports each so the decorators fire on package import).
- The reference body snapshot at
  `tests/fixtures/sandbox/trust_scorer_score_body.txt` is generated and
  committed in the same PR (Implementation outline §5).

No edits to `src/codegenie/transforms/{signal_kinds,trust_scorer,outcomes}.py`
expected. If the spike contradicts this — i.e., `master` has actually
drifted from the documented surface — escalate as RESCUE and re-run
`phase-story-validator` rather than patch around it.

### Refactor — clean up

- The closeout test file is the only new code. Keep it under 350 lines;
  if it grows, split Section D (property tests) into a sibling file
  with a `_widening_helpers.py` for shared `_log` / `_sig`. The
  refactor threshold is the same Phase-5 convention used in
  `tests/unit/transforms/test_trust_scorer.py` (which spans 800+ lines
  for a deliberate reason — it IS the contract test surface).
- Do NOT extract a `_compare_outcome(a, b)` helper unless a third call
  site appears. Rule 2 / Rule of three: two equality assertions on a
  3-tuple do not justify abstraction.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/sandbox/__init__.py` | Empty file for pytest discovery (create if missing). |
| `tests/integration/sandbox/test_trustscorer_widening.py` | The closeout suite — every AC above. |
| `tests/fixtures/sandbox/trust_scorer_score_body.txt` | Reference snapshot of `TrustScorer.score` body bytes. Generated once via Implementation outline §5; never edited without an ADR-0003 amendment citation. |
| `_attempts/S4-04.md` | Spike findings — registry-present evidence with `file:line` anchors per AC-SPIKE-1..-2. |

**Not touched (deliberately):**

- `src/codegenie/transforms/signal_kinds.py` — already ships the open
  registry; this story discharges the architect Risk #6 by verifying
  not by editing.
- `src/codegenie/transforms/trust_scorer.py` — body-pinned by
  AC-BODY-PINNED-1; any edit must come with an ADR-0003 amendment.
- `src/codegenie/transforms/outcomes.py` — `TrustSignal.kind`
  newtype-pinned by AC-TYPE-NEWTYPE-1.
- `src/codegenie/sandbox/signals/*` — collector modules are
  S4-01/S4-02/S4-03's load; this story only consumes them at import.
- **`src/codegenie/sandbox/signals/trust_registration.py`** —
  explicitly forbidden by AC-ANTIPATTERN-1.

## Out of scope

- Building the `StrictAndGate` adapter — S4-05.
- The signal collectors themselves — S4-01, S4-02, S4-03.
- The `@register_signal_kind` decorator + `SignalCollectorRegistry` —
  S1-05.
- Threshold calibration (production ADR-0015) — Phase 5 is strict-AND
  only; calibration is future-phase per ADR-0003's Consequences §5.
- Any edit to Phase 3's `TrustScorer` body (would require an ADR-0003
  amendment and a new validator run).
- Phase 7's `baseimage` / `shell_presence` kinds — they will be added
  by Phase-7 stories registering through the same mechanism this story
  verifies. AC-PROP-DYNAMIC-1 is forward-compatible; AC-NEW-KINDS-3
  IS the Phase-5 closeout pin and Phase 7 must update it.

## Notes for the implementer

1. **Read `_attempts/S4-04.md` before you write anything.** Architect
   Risk #6 explicitly flags "Phase 3 registry doesn't exist or is
   closed" as the failure mode this story discharges — and the
   Validation note above shows the draft was written assuming exactly
   that failure mode. The spike step is the proof you've actually
   confirmed otherwise. If the codebase has drifted (the registry
   moved, was renamed, or a sidecar module appeared), escalate to
   RESCUE.

2. **The Phase-5 `@register_signal_kind` decorator is *not* Phase 3's
   `register_signal_kind` function.** Same simple name, two distinct
   import paths, distinct shapes:
   - Phase 3: `codegenie.transforms.signal_kinds.register_signal_kind(name:
     str, *, registry=None) -> SignalKind` — function call.
     `BUILD = register_signal_kind("build")`.
   - Phase 5 (S1-05): `codegenie.sandbox.signals.registry.register_signal_kind(name:
     str)` — decorator. `@register_signal_kind("build") def
     collect_build_signal(run): ...`.
   - The Phase-5 decorator **delegates** the name-side to Phase-3's
     function iff the name is not yet in `signal_kind_registry`.
     S1-05's Validation note #1 calls this collision out as Rule 7
     ("Surface conflicts, don't average them"). When you write or
     debug a test, always import by full module path and stick to one
     surface per call site. This story tests the *Phase-3* surface.

3. **No `sandbox/signals/trust_registration.py` sidecar — ever.** A
   centralized "register every kind here" module looks tempting (one
   file lists every name; easy to grep). But:
   - Every new Phase-7+ kind would edit this file (Open/Closed
     violation — the kernel for the registry is `transforms/signal_kinds.py`,
     and that's the only file allowed to grow).
   - The actual registration would silently no-op because the
     collector module's decorator already registered the name when
     `sandbox/signals/__init__.py` imported it.
   - The redundant registration would mask real collisions: a typo
     ("trrace") in the sidecar would be a silent no-op too.
   - Per S1-05 + S4-01..S4-03's `AC-REG-IDEMPOTENT-*`, registration
     is the *collector's own responsibility* at module-import time. AC-ANTIPATTERN-1
     enforces this.

4. **The body-pinned snapshot (AC-BODY-PINNED-1) is intentionally
   brittle.** Any change — even whitespace — fails the test. That's
   the design: it forces a Phase-5 author who "improves" Phase-3 code
   to (a) confirm the change is intentional, (b) update the snapshot
   in the same commit, (c) cite an ADR-0003 amendment in the PR
   description. The fence is much stronger than a behavioral test
   because it catches edits whose strict-AND semantics happen to
   survive (e.g., a refactor to `return not any(not s.passed for s in
   signals)` would behaviorally match but conceptually drift).
   Pattern precedent: the contract-snapshot discipline in
   `tests/snapshots/probe_contract.v1.json` (Phase 1 S1-06) +
   `_attempts/S1-06.md` recorded the rationale for bytewise pinning.

5. **AC-PROP-DYNAMIC-1's `st.sampled_from(sorted(signal_kind_registry,
   key=str))` is load-bearing.** Do NOT replace this with a hardcoded
   `ALL_KINDS = [...]` literal "for readability". The whole point of
   ADR-0003's open registry is that the *next* phase's kind addition
   should not require an edit to a closeout test like this one. When
   you grep for "registry-parametric hypothesis strategy" in this
   codebase, this story is the canonical example — keep it that way.
   (Rule of three: this is the third place — after
   `transforms/signal_kinds.py`'s 5-registries observation and the
   plugin-resolver tests — where the codebase chose "iterate the
   live registry" over "iterate a literal list". Notes-only because
   N=3 in a *test-suite* context is below the kernel-extract bar; the
   precedent stays inline.)

6. **`TrustScorer(event_log=...)` requires a real `EventLog`.** The
   `_log(tmp_path)` helper mirrors S6-02's pattern; do NOT pass `None`
   or a `MagicMock` — the scorer's `degraded` confidence path reads
   `event_log.replay()` and `event_log.workflow_id`, and a mock would
   hide a regression where someone removed the `EventLog` dependency.
   `InMemorySink` keeps the spanning sink in-memory; the internal
   workflow stream still goes to the zstd file under `tmp_path` (the
   convention `tests/unit/transforms/test_trust_scorer.py` pins).

7. **AC-NEW-KINDS-3's exact-set-equality is the closeout pin Phase 7
   must update.** When Phase 7 lands the `baseimage` / `shell_presence`
   kinds, the failing assertion here is the signal to update
   `EXPECTED_REGISTRY` (and to record the Phase-7 ADR amendment that
   widens the set). Do NOT loosen the set to `>=` — the exactness is
   the whole point.

8. **`make check` matrix.** This story's tests run in the
   `tests/integration/sandbox/` suite — make sure your local `make
   check` invocation includes it. If you ran a narrow subset, the
   `--cov-fail-under=85` global gate (pyproject.toml `addopts`) can
   false-fail; use `pytest --no-cov` for ad-hoc subset runs per CLAUDE.md
   guidance.
