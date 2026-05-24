# Validation report: S4-04 — Phase 3 `TrustScorer` open signal-kind registry — closeout verification

**Validated:** 2026-05-24
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S4-04's draft was the first Phase 5 story whose draft *literally* could not
be executed by `phase-story-executor` without surfacing a contradiction on
the very first import — every identifier it named (`codegenie.trust.registry`,
`register_trust_signal_kind`, `is_registered`, `trust_registration.py`)
pointed at a module path that does not exist on `master`, and the surfaces
that *do* exist contradict the draft's assumptions on five different axes:

| Draft assumption | Reality on `master` |
|---|---|
| Phase 3 has no open registry; if absent, expand the story to land one | `src/codegenie/transforms/signal_kinds.py` ships a `SignalKindRegistry` class + `register_signal_kind(name, *, registry=None) -> SignalKind` function with five pre-registrations and a `.fresh()` classmethod for per-test isolation |
| Decorator-shaped `@register_trust_signal_kind` | Function-call-shaped `BUILD = register_signal_kind("build")` (S6-02 ADR-style — value-producing call, not a class decorator) |
| Three kinds to register: `trace`, `policy`, `cve_delta` | `cve_delta` is already pre-registered at `signal_kinds.py:158`; only `trace` and `policy` are net-new for Phase 5 |
| `pytest.raises(ValueError)` on unknown kind | `pytest.raises(UnregisteredSignalKind)` — a typed `CodegenieError` subclass carrying `.kind: SignalKind` |
| `TrustScorer()` no-arg constructor | `TrustScorer(event_log: EventLog)` — constructor-injected, per ADR-0001 / ADR-0005 functional-core discipline |
| Centralized `trust_registration.py` sidecar | Each collector (S4-01..S4-03) self-registers via `@register_signal_kind` decorator (S1-05); a sidecar is an explicit Open/Closed anti-pattern |

The dominant failure pattern: the draft was written **before** S1-05 +
S4-01..S4-03's validations (and possibly before S6-02 landed the Phase-3
registry at all), so it operated on a hypothetical surface rather than the
actual one. Every block-tier finding traces back to this gap.

Despite the depth of the misalignment, the **story's goal is recoverable**.
ADR-0003 names the *property* — "extension by addition for signal kinds via
an open registry that `StrictAndGate` (S4-05) consumes without editing
Phase 3 internals" — and that property is verifiable end-to-end after
`import codegenie.sandbox.signals` even though the registration mechanics
are owned by S1-05 + the per-collector decorators. **The hardened story
repositions S4-04 as a closeout / verification story** — its residual
contribution is an integration test that:

1. Empirically refutes architect Risk #6 with a `_attempts/S4-04.md`
   spike log carrying `file:line` anchors.
2. Verifies all 7 expected kinds (5 Phase-3 + 2 net-new Phase-5)
   participate after `import codegenie.sandbox.signals`.
3. Pins the strict-AND invariant across the exhaustive 2^6 cartesian
   product AND across hypothesis-generated subsets sampled from the
   *live registry* (so the property survives Phase 7's widening with
   `baseimage` / `shell_presence`).
4. Pins `TrustScorer.score`'s body bytewise via a committed snapshot —
   any accidental Phase-5 edit fails the test even if the strict-AND
   semantics happen to survive.
5. Forbids the centralized-registrations sidecar with a "thou shalt not
   exist" file test whose failure message points the reader back to
   ADR-0003 + the S1-05 delegation chain.

No `RESCUE`-tier escalation was triggered because the goal is intact —
every gap was patchable by rewriting against the actual surfaces + adding
ACs that the original goal already implied. The goal text required no
edit; the implementation outline was rewritten end-to-end.

Stage 3 (research) was skipped — every gap was answerable from the
codebase + the seven prior HARDENED reports (S1-03, S1-05, S3-01..S3-05,
S4-01, S4-02, S4-03) + the existing S6-02 test surface at
`tests/unit/transforms/test_trust_scorer.py`. No arXiv lookup or library
docs were needed; the canonical patterns (registry-parametric hypothesis
strategies, bytewise body snapshots, subprocess-import side-effect
assertions) all have established precedents in this repo.

## Critic findings

### Coverage critic

#### Block-tier (would-silently-pass / would-crash-on-first-real-input)

1. **`cve_delta` is already registered.** Draft AC-3 ("register the
   three new kinds: trace, policy, cve_delta") would have either (a) a
   no-op via the Phase-5 decorator's idempotency, masking that the
   draft's mental model is wrong, or (b) an explicit
   `SignalKindAlreadyRegistered` if the draft's proposed `trust_registration.py`
   sidecar tried to call Phase-3's function directly. Either way the
   executor's first run surfaces a confusing failure, and the story has
   no AC asserting the *real* set of kinds (5 Phase-3 + 2 Phase-5).
   **Fix:** AC-NEW-KINDS-1..-3 in the hardened story pin the net-new
   set `{trace, policy}`, the persistence of all 5 pre-registrations,
   AND the exact 7-element registry membership.

2. **Empty-list path completely uncovered.** Draft TDD plan never
   exercises `TrustScorer.score([])`. Phase 3 raises `EmptySignals`
   (Rule 12 — fail loud); an implementer reverting that to
   `passed=True` silently mis-reports a broken Stage-6 collection as
   a passing workflow. Severity: silently ships a broken workflow.
   **Fix:** AC-EMPTY-1.

3. **Architect Risk #6 was a prose footnote, not an AC.** The risk
   register paragraph names the failure mode but the story relies on
   "the spike step is the proof" — captured only in the `_attempts/`
   log if the executor remembers to do it. Without an AC, the spike is
   optional. **Fix:** AC-SPIKE-1..-2 promote spike findings to a
   verifiable artifact with `file:line` citations + verbatim quoting
   in the PR description.

4. **`failing` order assertion missing.** Draft test only checked
   `outcome.passed`. The S5-05 report writer + future HITL UI display
   the *first-failing* signal to humans; `failing` order is
   load-bearing (per `trust_scorer.py:8-12`). An implementer
   `sorted(failing)`-ing "for consistency" silently breaks UX without
   any test failing. **Fix:** AC-CART-2 and
   AC-INV-FAIL-INDEX-1..-6 assert caller-order preservation across
   the entire cartesian + per-position parametrize.

#### Harden-tier

5. **`itertools.product` cartesian only had 2 example points in the
   draft.** ADR-0003 §Tradeoffs names "~2^6 cartesian fixtures" as the
   load-bearing test surface; draft had `all-pass` and one example of
   `one-fail`. **Fix:** AC-CART-1 = full 64-case `itertools.product`.

6. **Property test would lie the day Phase 7 widens the registry.**
   Draft hardcoded `ALL_KINDS = [...]` literal in the hypothesis
   strategy. Phase 7's `baseimage` addition would still pass this
   test while the registry grew under it — exactly inverting ADR-0003's
   extension-by-addition promise. **Fix:** AC-PROP-DYNAMIC-1 samples
   from `sorted(signal_kind_registry, key=str)` at test-collection
   time, making the property parametric over the live registry.

### Test-quality critic

#### Block-tier

7. **Wrong exception types throughout.** Draft's `pytest.raises(ValueError)`
   for unknown-kind, plus no test for the typed `.kind` attribute on the
   exception. The codebase raises `UnregisteredSignalKind(kind)` — a
   `CodegenieError` subclass. A `ValueError`-catching test would
   silently pass even if Phase 5 accidentally raised a generic exception
   that lost the typed `.kind` field. **Fix:** AC-ERR-TYPED-1..-2 with
   typed-class assertions + `.kind` value pinning.

8. **Pure-function determinism missing.** Draft never asserted
   `score(signals)` called twice on the same input returns equal
   outcomes (or that state doesn't accumulate across calls). The
   `TrustScorer` docstring promises stateless `score(...)` across calls
   (`trust_scorer.py:127-129`); a regression introducing per-call cache
   would slip past the existing tests. **Fix:** AC-PROP-DYNAMIC-2.

9. **`_compute_strict_and` invariant test was a tautology.** Draft's
   `passed_invariant(S) ⟺ ∀ s ∈ S: s.passed` is the function's literal
   implementation. A green test only proves no typo. **Fix:** rewrote
   AC-INV-FAIL-INDEX-1..-6 around the *behavioural consequence* —
   first-failing-kind propagation with caller-order preservation —
   which a tautology can't capture.

#### Harden-tier

10. **`TrustScorer()` no-arg constructor in draft TDD plan would have
    crashed on first run.** `TrustScorer.__init__` requires `event_log`
    (S6-02 + ADR-0001 functional-core discipline). The implementer
    would have spent attempt-1 debugging an obvious `TypeError`. **Fix:**
    every `TrustScorer(...)` call in the hardened TDD plan threads
    `event_log=_log(tmp_path)` mirroring `tests/unit/transforms/test_trust_scorer.py`'s
    `_log` helper.

11. **No subprocess-import side-effect assertion.** S6-02 ships
    `test_fresh_subprocess_import_populates_default_registry` as the
    gold-standard "side effect survives import-graph reordering" test —
    the strongest assertion that module-import-time registrations are
    real. Draft didn't mirror it; a test-collection-order regression
    could silently mask a missing import in `sandbox/signals/__init__.py`.
    **Fix:** `test_new_kinds_visible_in_fresh_subprocess` mirrors S6-02
    AC-12c.

### Consistency critic

#### Block-tier

12. **Every identifier in the draft pointed at a non-existent module.**
    `codegenie.trust.registry`, `codegenie.trust.scorer`,
    `register_trust_signal_kind`, `is_registered`, `SignalKindAlreadyRegistered`
    (no module path), `TrustSignal(kind="x", passed=True, details={})`
    where `kind` is `str` instead of `SignalKind`. An executor would
    hit `ModuleNotFoundError` on the very first import line of the
    test file. **Fix:** complete rewrite using actual surfaces —
    `codegenie.transforms.signal_kinds`, `codegenie.transforms.trust_scorer`,
    `codegenie.transforms.outcomes`, `codegenie.types.identifiers.SignalKind`.
    Every reference in the hardened story is dereferenced against
    `master`.

13. **Draft contradicted ADR-0003 §Consequences §1** ("`src/codegenie/gates/strict_and.py`
    is the only adapter — ~40 LOC, no business logic"). Draft proposed
    inventing a `trust_registration.py` adapter module containing
    business logic (the "which kinds to register" decision). ADR-0003
    explicitly forbids this. **Fix:** AC-ANTIPATTERN-1 + Notes §3
    document the rationale and forbid the file by name.

14. **Draft contradicted S1-05 + S4-01..S4-03's `AC-REG-IDEMPOTENT-*`
    contracts.** Those stories pin "every kind is registered by its
    own collector module's `@register_signal_kind` decorator"; the
    draft would have created a parallel registration site. Two
    registration sites for the same name would: (a) be a Phase-3
    `SignalKindAlreadyRegistered` at import; (b) if the sidecar runs
    *first*, the collector's decorator would silently no-op,
    decoupling the registration from the collector's existence — a
    future "the collector was deleted but its kind is still in the
    registry" footgun. **Fix:** Notes §3 explains the failure mode;
    AC-ANTIPATTERN-1 prevents it structurally.

#### Harden-tier

15. **Test file path mismatched the established Phase-5 layout.**
    Sibling validation reports (S3-02..S3-07, S4-01..S4-03) place
    integration tests under `tests/integration/sandbox/`,
    `tests/integration/gates/`, etc. Draft used flat
    `tests/integration/test_trustscorer_widening.py`. **Fix:** moved to
    `tests/integration/sandbox/test_trustscorer_widening.py` + creating
    `tests/integration/sandbox/__init__.py` for pytest discovery.

### Design-patterns critic

#### Harden-tier

16. **Centralized-registrations sidecar is an Open/Closed anti-pattern,
    not just "redundant".** The draft framing ("one file lists every
    new kind") sounds like organization. In reality:
    - Every new Phase-7+ kind would edit a `trust_registration.py` file
      that's logically a "registration manifest" — but the registration
      mechanism is already provided by `@register_signal_kind` at the
      collector module. A second registration site is an explicit
      duplication of the registration mechanism (Rule 7 — surface
      conflicts, don't average them).
    - A typo in the sidecar (`"trrace"`) would be a silent no-op
      *iff* the corresponding collector already registered `"trace"`
      first — a subtle ordering-dependent footgun.
    - The bug surface in the registry pattern is "is the registration
      site discoverable, scoped, and impossible to forget" — a
      collector module that requires `@register_signal_kind` for its
      decorator to exist meets all three. A sidecar fails (1) and (3).
    **Fix:** AC-ANTIPATTERN-1 + Notes §3 (cites ADR-0003 + S1-05).

17. **Body-pinned snapshot pattern was missing.** ADR-0003 specifies
    "no edits to existing Phase 3 `TrustScorer.score(...)` logic" —
    enforceable only by *bytewise* comparison, not by behavioural
    tests (which would let semantically-equivalent edits through). The
    codebase's contract-snapshot precedent (`tests/snapshots/probe_contract.v1.json`,
    S1-06) is the right template. **Fix:** AC-BODY-PINNED-1 +
    AC-NO-EDIT-1 + Implementation outline §5 (snapshot generation).

#### Notes-only (defer kernel extract; rule-of-three not yet cleared)

18. **"Iterate the live registry" is at N=3 in test-suite usage.**
    `transforms/signal_kinds.py` ships the 5-registries observation;
    the plugin-resolver tests iterate `signal_kind_registry`; AC-PROP-DYNAMIC-1
    is the third site. A `live_registry_strategy()` extracted helper
    would couple this story to those two — premature per Rule 2.
    Recorded in Notes §5 so the next consumer can decide.

19. **`TrustScorer.score` already follows functional-core / imperative-shell.**
    No additional pattern opportunity in the production code; the
    only impure code is the `event_log.replay()` read, which the
    constructor-injected `EventLog` already isolates. No edits
    needed; documented for completeness.

20. **Anti-pattern doc itself is an Open/Closed seam.** The
    AC-ANTIPATTERN-1 + Notes §3 form a "register the rejected
    alternative so future contributors don't re-litigate it" pattern.
    A future story extracting this into a `docs/architecture-anti-patterns.md`
    is plausible at N≥3 instances; today only this case + the
    `coordinator's-inner-threadpool` ban (Phase 2 ADR-0003) qualify.
    Notes only.

## Edits applied

All edits land in the story file in place. Summary by section:

| Story section | Edit |
|---|---|
| Header | Status `Ready → Ready (HARDENED 2026-05-24)`; `Depends on` rewritten against actual upstream stories; `ADRs honored` adds production ADR-0008 + production ADR-0001 |
| Validation notes | New 12-item block appended documenting every change + why |
| Context | Complete rewrite reflecting actual Phase-3 surface + ADR-0003 chain |
| References | Replaced fictional paths with actual file/line citations |
| Goal | Repositioned from "build/confirm registry" to "closeout verification of the already-shipped mechanism" |
| Acceptance criteria | Replaced 9 vague ACs with 7 sections (A-H) covering 24 verifiable, mutation-resistant assertions: spike + risk closeout (2), registry membership (3), exhaustive cartesian + per-index strict-AND (8), property test (2), typed errors + empty (4), annotation / body-pinned / anti-pattern (4), defense-in-depth (1), build gates (3) |
| Implementation outline | 6 numbered steps; spike is step 1 with concrete `grep` commands; snapshot generation is step 5 with the exact Python one-liner |
| TDD plan | Complete rewrite — corrected imports, actual `TrustScorer(event_log=...)` constructor, `pytest.raises(UnregisteredSignalKind)` / `EmptySignals` / `SignalKindAlreadyRegistered`, parametrized `itertools.product`, registry-parametric hypothesis strategy, body-snapshot extraction helper, anti-pattern fail-loud test |
| Files to touch | Removed 3 fictional source paths; explicitly listed "not touched (deliberately)" — including the forbidden `trust_registration.py` |
| Out of scope | Added: Phase 7's `baseimage`/`shell_presence` (forward-compatible), edits to `TrustScorer` body (would require ADR amendment) |
| Notes for the implementer | Expanded from 6 prose paragraphs to 8 concrete guidance items, each anchored to an AC, an ADR, or a sibling-story precedent |

## Verdict rationale

**HARDENED**, not RESCUE, because:

- The story's *goal* — "verify the open-registry widening contract
  works end-to-end for Phase 5's six signal kinds" — survived the
  rewrite intact; only the prescribed mechanics were wrong. RESCUE
  would have required the goal itself to contradict the phase arch
  (it doesn't — ADR-0003 names this exact verification as the
  desired end state).
- Every block-tier finding was patchable in the story file without
  needing to re-run `phase-story-writer` or change ADRs. All identifier
  rewrites were directly mechanical against the actual codebase.
- The hardened story now exhibits every property in the validator's
  "STRONG" definition: every AC individually verifiable, AC set
  collectively guaranteeing the goal, every AC backed by at least one
  mutation-resistant TDD test, no tautologies, no vague qualitative
  statements, typed errors with `.kind` value pinning, body-bytes
  snapshot for unchanged-impl, anti-pattern fence with rationale,
  property test parametric over the live registry (extension-by-addition
  encoded as a test), exhaustive cartesian + per-position belt-and-suspenders,
  and an explicit spike step discharging the architect's risk register.

The story is now ready for `phase-story-executor`.

## Open items the executor should know

- **AC-BODY-PINNED-1's snapshot must be generated and committed in
  the same PR as the test.** The Implementation outline §5 has the
  exact Python one-liner. The reference body is the *current* `master`
  bytes; if it ever changes intentionally, an ADR-0003 amendment must
  cite the change in the PR description (the failure message embeds
  this instruction).
- **AC-NEW-KINDS-3 (exact-7-set equality) is the Phase-5 closeout
  pin.** When Phase 7 lands `baseimage` / `shell_presence`, the
  failing assertion here is the signal for the Phase-7 story to update
  the set. Notes §7 records the convention; do NOT loosen to `>=`.
- **S1-05 + S4-01..S4-03 must be executor-complete before this story
  is executed.** S4-04 is the integration closeout; if S1-05 hasn't
  landed `sandbox/signals/registry.py`, the test file's `import
  codegenie.sandbox.signals` line itself fails. The spike (AC-SPIKE-1)
  catches this — if the spike grep shows missing upstream, escalate.

## Conflict-resolution record

- **Coverage vs Test-Quality on `failing` order.** Coverage proposed
  AC-CART-2 ("`failing` matches input order"). Test-Quality refined to
  "and is never sorted / deduplicated" with a Python-`list`-vs-`sorted`
  mutation rationale. Both fold into AC-CART-2 + AC-INV-FAIL-INDEX-*.
- **Consistency vs Design-Patterns on `trust_registration.py`.**
  Consistency wanted to surface "the sidecar contradicts S1-05 +
  S4-01..S4-03 idempotency". Design-Patterns wanted to surface
  "Open/Closed anti-pattern". Both fold into AC-ANTIPATTERN-1 + Notes §3;
  Consistency's framing is the failure-mode prose; Design-Patterns'
  framing is the rationale.
- **Coverage's "add an AC asserting every collector module imports
  cleanly under -W error" was rejected.** S1-05 + S4-01..S4-03 already
  carry per-collector AC-INIT-1 / AC-COL-* coverage; duplicating here
  would couple S4-04 to the upstream stories' AC numbering. Recorded
  as a non-edit; the spike step (AC-SPIKE-2) cites the upstream ACs
  instead.
- **Design-Patterns' "extract `live_registry_strategy()` helper"
  rejected.** Rule of three not yet cleared in test-suite context;
  Notes §5 records the precedent for the next consumer.

## Sources cited (story-internal + codebase + sibling reports)

- [`docs/phases/05-sandbox-trust-gates/phase-arch-design.md`](../../phase-arch-design.md) §Component design — Gate (ABC) + StrictAndGate, §Risk register Risk #6, §Signal collectors
- [`docs/phases/05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md`](../../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md)
- [`docs/phases/05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md`](../../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md)
- [`docs/production/adrs/0008-objective-signal-trust-score.md`](../../../../production/adrs/0008-objective-signal-trust-score.md)
- [`docs/phases/00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md`](../../../00-bullet-tracer-foundations/ADRs/0001-cache-content-hash-algorithm.md) — hashing chokepoint (untouched-invariant context only)
- [`src/codegenie/transforms/signal_kinds.py`](../../../../../src/codegenie/transforms/signal_kinds.py)
- [`src/codegenie/transforms/trust_scorer.py`](../../../../../src/codegenie/transforms/trust_scorer.py)
- [`tests/unit/transforms/test_trust_scorer.py`](../../../../../tests/unit/transforms/test_trust_scorer.py) — S6-02 reference test surface
- [`docs/phases/05-sandbox-trust-gates/stories/_validation/S1-05-registries-and-env-allowlist.md`](S1-05-registries-and-env-allowlist.md)
- [`docs/phases/05-sandbox-trust-gates/stories/_validation/S4-01-build-install-collectors.md`](S4-01-build-install-collectors.md)
- [`docs/phases/05-sandbox-trust-gates/stories/_validation/S4-02-test-signal-with-inventory-delta.md`](S4-02-test-signal-with-inventory-delta.md)
- [`docs/phases/05-sandbox-trust-gates/stories/_validation/S4-03-trace-policy-cve-collectors.md`](S4-03-trace-policy-cve-collectors.md)
- CLAUDE.md (project) §Load-bearing architectural commitments — "Extension by addition" / "Fail loud"
- CLAUDE.md (user/global) Rules 2 (Simplicity First), 7 (Surface conflicts), 9 (Tests verify intent), 11 (Match the codebase's conventions), 12 (Fail loud)
