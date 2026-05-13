# Story S7-04 — HITL same-sig-flake routing + malformed-decision adversarial tests

**Step:** Step 7 — HITL replay + Phase 5 parity + retry-feedback-distinct-bytes tests (G3 + G4 + G5)
**Status:** Ready
**Effort:** S
**Depends on:** S7-01 (shared mocks, `initial_ledger.py` fixture, conftest helpers). Transitively: S3-02 (`route_after_attempt` returns `"non_retryable"` on same-signature flake), S4-08 (`await_human` resets `retry_count=0` on `continue`), S6-03 (CLI resume warning surface — this story names the warning string the CLI must emit).
**ADRs honored:** ADR-0003 (per-gate counter + same-signature flake short-circuit; ADR-0003 §Tradeoffs explicitly states *"`HumanDecision.action='continue'` after a same-signature flake routes to `non_retryable` again (see Phase 6 design Gap 4); the doc must say so"*), ADR-0008 (HITL `HumanDecision` is the typed contract; malformed payloads raise `ValidationError` at `model_validate` — ADR-0008 §Consequences names `test_hitl_malformed_decision_raises.py` as the canary).

## Context

This story ships **two small adversarial integration tests** that together document the loud-but-by-design behaviors of Phase 6's HITL contract. Neither test exercises new code paths; they pin the *observable consequences* of two design decisions so an operator (or a future implementer who decides to "fix" the behavior) can't silently break them.

**Test 1 — Gap 4: HITL `continue` after a same-signature flake silently routes to `non_retryable`.**

`phase-arch-design.md §Gap 4` documents the interaction:

> When HITL resumes with `action="continue"`, the design resets `retry_count=0` to give the operator-approved retry a fresh budget. But `prior_attempts` is **not** cleared — Phase 4 sees all 3 prior failures plus the new approval. This … interacts subtly with the same-signature flake detector: if the operator approves "continue" on a same-signature-flaked workflow, the very next call to `route_after_attempt` will *still* fire `non_retryable` (because `prior_attempts[-2:]` are still the same-signature pair). **The HITL "continue" is silently ignored.**

Three improvement options are documented:
- (a) `continue` clears `prior_attempts` (fresh start),
- (b) `continue` records a `hitl_continue` marker the detector skips,
- (c) document the current behavior loudly and surface a CLI warning when the operator runs `codegenie loop resume --decision continue` against a flaked state.

The synthesizer picked **option (c)** — defer the design change to a Phase 6 ADR amendment (proposed P6-009) if the team prefers (a) or (b). This story implements option (c)'s loud-doc-and-warning discipline: the integration test documents the routing behavior with a name a future operator can grep for; and pins the CLI warning S6-03 emits.

**Test 2 — ADR-0008 canary: `HumanDecision(action="approve")` raises `ValidationError`.**

ADR-0008 ships `HumanDecision.action` as a `Literal["continue", "override", "abort"]`. The three values are operator-facing names: `continue` resumes, `override` jumps to `emit_artifact`, `abort` routes to `escalate`. The temptation to add `"approve"` or `"reject"` (matching real-world PR-review vocabulary) is the contract-creep ADR-0008 explicitly rejects — Phase 11 owns PR-comment semantics, not Phase 6. The test asserts that a malformed `HumanDecision` payload raises `ValidationError` **at the resume boundary** (during `model_validate`), not deep inside `await_human`. The failure mode of bad input is loud and early.

Both tests are small (~30 lines each). The story is **S effort**: the work is in the *meaning* of the tests (Gap 4 documentation, ADR-0008 contract enforcement), not their LOC.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap 4` — the silent-non-retryable behavior verbatim.
  - `../phase-arch-design.md §Edge case 9 "Same-signature flake"` (line 1139) — the detection mechanism.
  - `../phase-arch-design.md §Component 6 "HumanRequest / HumanDecision / await_human"` — the typed contract.
- **Phase ADRs:**
  - `../ADRs/0003-per-gate-retry-counter-scope.md` §Tradeoffs — the explicit note about `continue` after flake.
  - `../ADRs/0008-hitl-operator-auth-deferred-to-phase11.md` §Consequences — names `test_hitl_malformed_decision_raises.py` as the canary.
- **High-level-impl:** `../High-level-impl.md §Step 7` — `tests/integration/test_hitl_continue_after_same_sig_flake_routes_to_non_retryable.py` and `tests/integration/test_hitl_malformed_decision_raises.py` named in the feature list; the operator-warning requirement is in Risk #6 (line 326).
- **Source design:**
  - `../final-design.md §Component 7 "HITL contract"` — the three-Literal-action shape.

## Goal

Land two small integration tests that pin the documented-by-design HITL edge cases:

1. `tests/integration/test_hitl_continue_after_same_sig_flake_routes_to_non_retryable.py` — drives the Gap 4 scenario: two consecutive same-signature failures trip the flake detector → `non_retryable` → `await_human` → HITL `continue` → `await_human` re-fires immediately (because `prior_attempts[-2:]` still match). The test asserts the second `interrupt()` fires; asserts the audit chain has two `interrupt.raised` events for the same workflow; asserts `cli/loop.py resume`'s mocked stderr contains an operator warning naming the situation; documents the legitimate resolution paths in the test docstring (`override`, `abort`, or amend with ADR-P6-009).
2. `tests/integration/test_hitl_malformed_decision_raises.py` — pins ADR-0008's contract: `HumanDecision(action="approve")` (a plausible operator typo) raises `ValidationError` at `model_validate`. Same for `action=""`, `action=None`, `action=42`, and a payload missing the required `operator` field. The CLI's malformed-decision exit code is `13` per S6-02; the test asserts this end-to-end.

## Acceptance criteria

### Test 1 — `test_hitl_continue_after_same_sig_flake_routes_to_non_retryable.py`

- [ ] File exists, `@pytest.mark.integration`, green on `main`.
- [ ] **The scripted outcomes are same-signature on attempts 1 and 2.** Both have `failing_signals=["tests"]` and identical `prior_failure_summary` strings (e.g., `"AssertionError: expected 200 got 500 at auth/jwt.test.ts:42"`). After `record_attempt` writes attempt 2, `_same_signature(prior_attempts[-1], prior_attempts[-2])` returns `True`.
- [ ] **First `interrupt()` fires on the `non_retryable` route** (not `retry_exhausted`). The test asserts the pre-pause state has `route_after_attempt(state) == "non_retryable"` (or equivalent — read the state-history's last edge label) and `retry_count == 2 < max_attempts == 3`. This pins that the flake detector — not the retry-exhausted predicate — is what fired.
- [ ] **HITL `continue` is injected.** `HumanDecision(action="continue", operator="alice", note="The test is real, push past the flake detector", at=fixed_ts)`. The test calls `aupdate_state(as_node="await_human")` and `ainvoke(None, config)`.
- [ ] **Second `interrupt()` fires immediately.** After resume, the very next `route_after_attempt` call still observes `_same_signature(prior_attempts[-2:]) == True` (because `continue` didn't clear `prior_attempts`); the route returns `"non_retryable"` again; `await_human` fires again. The test asserts the audit chain contains **two** `interrupt.raised` events for the same `workflow_id`.
- [ ] **Operator warning surface.** The test imports `cli.loop.resume`'s warning emitter (S6-03 ships it) and asserts it emits a stderr line containing the substrings `"WARNING"`, `"same-signature flake"`, and the suggested remediation `"--decision override"` or `"--decision abort"`. The test invokes the warning emitter directly with a fixture state; it does not invoke the CLI via subprocess (that's S6-03's responsibility).
- [ ] **The three legitimate resolution paths are exercised** as follow-up sub-tests:
  - `HumanDecision(action="override")` → routes to `emit_artifact`; the run completes with a marked-as-override `RemediationReport` (per S4-08 semantics).
  - `HumanDecision(action="abort")` → routes to `escalate`; the run exits via `END` with `kind="escalate"` event.
  - The test does **not** assert option (a) (`continue` clears `prior_attempts`) or option (b) (`hitl_continue` marker) — those are explicit future-ADR territory; the test docstring names them as the deliberate-future-change paths.
- [ ] **Test docstring** names: (a) Gap 4 verbatim from the arch design, (b) the three resolution options (a)/(b)/(c) and which the test pins (c), (c) the proposed ADR-P6-009 path if the team ever picks (a) or (b), (d) the amendment procedure ("if the team picks Gap 4 option (a) or (b), amend ADR-0003 + ship ADR-P6-009 + update this test in the same PR — the test asserts the *current* behavior, not the *desired* behavior, and the design decision is which is which").
- [ ] `mypy --strict` + `ruff check` + `ruff format --check` pass on the test file.

### Test 2 — `test_hitl_malformed_decision_raises.py`

- [ ] File exists, `@pytest.mark.integration`, green on `main`.
- [ ] **Parametrized over the malformed-decision cases.** Each case is a dict that `HumanDecision.model_validate` must reject:
  - `{"action": "approve", "operator": "alice", "at": "2026-05-12T12:00:00+00:00"}` — wrong Literal value (operator typo).
  - `{"action": "", "operator": "alice", "at": "..."}` — empty string.
  - `{"action": None, "operator": "alice", "at": "..."}` — None.
  - `{"action": 42, "operator": "alice", "at": "..."}` — wrong type.
  - `{"action": "continue", "at": "..."}` — missing required `operator` field.
  - `{"action": "continue", "operator": "alice"}` — missing required `at` field.
  - `{"action": "continue", "operator": "alice", "at": "...", "rogue_field": True}` — `extra="forbid"` rejects unexpected fields.
- [ ] **Each case raises `pydantic.ValidationError`** at `HumanDecision.model_validate(payload)`. The test asserts via `pytest.raises(ValidationError)`.
- [ ] **End-to-end CLI exit code is 13.** A separate sub-test invokes the malformed payload through `aupdate_state` directly (constructing the dict via `model_dump` is impossible since `HumanDecision.model_validate` rejects it; the test simulates a CLI that built a bad dict by writing the dict literal directly to `aupdate_state`). The test asserts the resulting `ainvoke(None, config)` surfaces the `ValidationError` and the workflow halts with state preserved (the pre-resume checkpoint frame is the last fsync'd frame; the chain is intact).
- [ ] **State preservation on malformed.** After the `ValidationError` raises, `graph.aget_state(config)` returns the pre-resume state (the operator can correct the typo and retry; no work is lost). The test asserts `pre_state == post_validation_error_state` byte-for-byte.
- [ ] **Audit chain contains a `resume.rejected` event.** The chain has an entry for the rejected resume attempt with `payload.reason == "malformed_decision"` and `payload.errors` listing the Pydantic validation errors. (This may require a Phase 6 follow-up to wire the rejection event — surface it as Gap-like in the story notes if `await_human` doesn't already emit one.)
- [ ] **Test docstring** names: (a) ADR-0008's three-Literal-action contract verbatim, (b) the rejection happens at `model_validate` (resume boundary), not deep inside `await_human`, (c) the exit-13 mapping per S6-02, (d) the amendment procedure ("if Phase 11 needs a fourth Literal value — `'request_changes'` or similar — extend `HumanDecision.action` additively, regenerate `docs/contracts/hitl-v0.6.0.json` via the S7-05 exporter, and update this test's parametrization in the same PR").
- [ ] `mypy --strict` + `ruff check` + `ruff format --check` pass.

## Implementation outline

1. **Test 1 setup** mirrors S7-01's mock infrastructure (`tests/integration/mocks.py`). The only difference is the scripted `GateOutcome` sequence: two **identical** outcomes (same `failing_signals`, same `prior_failure_summary`) followed by however many attempts the test needs (the post-`continue` re-fire makes only one further attempt before the second interrupt).
2. **The `_same_signature` precondition** is asserted via the route label observable from the state history. The test does **not** import `_same_signature` directly (it's an internal helper to `edges.py`).
3. **The warning emitter import** points at `codegenie.cli.loop.resume` (or wherever S6-03 places the warning function — likely a small private helper like `_warn_on_same_sig_continue(state) -> None`). The test patches the stderr stream to capture the warning.
4. **Test 2 parametrization** is a single `@pytest.mark.parametrize` with the seven malformed payloads. The sub-test for end-to-end exit-13 lives in the same file.
5. **Audit `resume.rejected` event.** If `await_human` doesn't emit this event yet (S4-08 may not have wired it), surface the gap loudly in the story's notes and either (a) extend S4-08 to emit it (story-internal scope) or (b) defer the assertion to a follow-up story. The current draft prefers (a) — emitting `resume.rejected` is a small additive change to `await_human` consistent with ADR-0008's "loud rejection at the resume boundary" discipline.

## TDD plan — red / green / refactor

### Red

**Test 1:** `tests/integration/test_hitl_continue_after_same_sig_flake_routes_to_non_retryable.py`

```python
"""Phase 6 design Gap 4 (`../phase-arch-design.md §Gap 4`): HITL `continue` after a
same-signature flake silently re-routes to `non_retryable`. The operator's approval is
NOT cleared from prior_attempts, so the flake detector keeps firing.

The synthesizer's design picks option (c) — document the behavior loudly and emit a CLI
warning. This test pins (c)'s observable consequences:
- Two `interrupt.raised` audit events fire for the same workflow.
- The CLI warning emitter prints "WARNING: same-signature flake ... --decision override".
- `override` and `abort` are the legitimate operator escape hatches.

If the team later picks option (a) — `continue` clears `prior_attempts` — amend
ADR-0003 + ship ADR-P6-009 + update this test in the same PR. This test asserts the
CURRENT behavior; the design decision is which behavior is current.
"""

import pytest
from datetime import datetime, UTC
from codegenie.graph import build_vuln_loop, AuditedSqliteSaver
from codegenie.graph.hitl import HumanDecision
from codegenie.cli.loop import _warn_on_same_sig_continue  # S6-03's emitter

_SAME_FAILING_SIGNALS = ["tests"]
_SAME_PRIOR_FAILURE_SUMMARY = "AssertionError: expected 200 got 500 at auth/jwt.test.ts:42"

@pytest.mark.integration
async def test_continue_after_same_signature_flake_routes_to_non_retryable_again(
    tmp_path, monkeypatch
) -> None:
    # Scripted same-signature failures × 2; third outcome doesn't matter (won't be reached).
    ...
    # Drive to first interrupt; assert route label "non_retryable" (not "retry_exhausted").
    ...
    # Inject HumanDecision(action="continue"); resume.
    decision = HumanDecision(action="continue", operator="alice", note=None,
                             at=datetime(2026, 5, 12, 12, 0, 0, tzinfo=UTC))
    await graph.aupdate_state(config, {"human_decision": decision.model_dump(mode="json")},
                              as_node="await_human")
    await graph.ainvoke(None, config)
    # Assert second interrupt fired; audit chain has two interrupt.raised events.
    ...

@pytest.mark.integration
async def test_override_after_same_signature_flake_completes_via_emit_artifact(...) -> None:
    ...

@pytest.mark.integration
async def test_abort_after_same_signature_flake_routes_to_escalate(...) -> None:
    ...

@pytest.mark.integration
def test_warning_emitter_prints_same_signature_flake_message(capsys) -> None:
    state = _build_flaked_state()
    _warn_on_same_sig_continue(state)
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "same-signature flake" in captured.err
    assert "--decision override" in captured.err or "--decision abort" in captured.err
```

**Test 2:** `tests/integration/test_hitl_malformed_decision_raises.py`

```python
"""ADR-0008 canary: HumanDecision.action is Literal["continue","override","abort"].
Malformed payloads raise ValidationError at model_validate (resume boundary), not
deep inside await_human. The CLI exits 13 per S6-02's exit-code map.

Amendment procedure: if Phase 11 needs a fourth Literal value, extend HumanDecision.action
additively, regenerate docs/contracts/hitl-v0.6.0.json via the S7-05 exporter, and
update this test's parametrization in the same PR.
"""

import pytest
from pydantic import ValidationError
from codegenie.graph.hitl import HumanDecision

_MALFORMED_PAYLOADS = [
    pytest.param({"action": "approve", "operator": "alice", "at": "2026-05-12T12:00:00+00:00"},
                 id="wrong-literal-approve"),
    pytest.param({"action": "", "operator": "alice", "at": "2026-05-12T12:00:00+00:00"},
                 id="empty-string"),
    pytest.param({"action": None, "operator": "alice", "at": "2026-05-12T12:00:00+00:00"},
                 id="none-action"),
    pytest.param({"action": 42, "operator": "alice", "at": "2026-05-12T12:00:00+00:00"},
                 id="wrong-type-int"),
    pytest.param({"action": "continue", "at": "2026-05-12T12:00:00+00:00"},
                 id="missing-operator"),
    pytest.param({"action": "continue", "operator": "alice"},
                 id="missing-at"),
    pytest.param({"action": "continue", "operator": "alice", "at": "2026-05-12T12:00:00+00:00",
                  "rogue_field": True},
                 id="extra-forbid-rogue-field"),
]

@pytest.mark.integration
@pytest.mark.parametrize("payload", _MALFORMED_PAYLOADS)
def test_malformed_human_decision_raises_validation_error(payload: dict) -> None:
    with pytest.raises(ValidationError):
        HumanDecision.model_validate(payload)

@pytest.mark.integration
async def test_aupdate_state_with_malformed_decision_preserves_state(tmp_path) -> None:
    # End-to-end: drive to interrupt, attempt to resume with malformed payload,
    # assert ValidationError raises and pre-state is preserved.
    ...
```

Run; commit red.

### Green

- Test 2 is mechanical and should go green immediately once `HumanDecision` ships per S1-03 — if any case fails, the model's `Literal`/`extra="forbid"` constraints are misconfigured.
- Test 1 may red-fail on the warning emitter (S6-03 may not have wired `_warn_on_same_sig_continue` yet). The remedy is to land the emitter as part of S6-03 (where it belongs) and import it here. If S6-03 lands without the emitter, surface the gap to S6-03 — this story should not implement the emitter itself.
- The `resume.rejected` audit event may need wiring into `await_human` if S4-08 didn't ship it. Land the additive emit as part of this story (small, ADR-0008-aligned).

### Refactor

- **Keep Test 1 and Test 2 in separate files.** They share design rationale but not assertion shape; bundling them obscures the separate Gap 4 / ADR-0008 traceability.
- **Do not parametrize Test 1 on `max_attempts`.** The flake-detection short-circuit fires regardless of cap; the parametrization muddies the meaning. S7-01 owns the `max_attempts` matrix.
- **The warning-emitter test uses `capsys`, not `caplog`.** The warning is operator-facing stderr text, not a structured log event.
- **Do not import `_same_signature` directly.** Observe its consequence via the route label in the state history.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_hitl_continue_after_same_sig_flake_routes_to_non_retryable.py` | New — Gap 4 documentation gate. |
| `tests/integration/test_hitl_malformed_decision_raises.py` | New — ADR-0008 canary. |
| `tests/integration/mocks.py` | Extend if needed — `same_signature_outcomes()` helper that returns a list of `GateOutcome`s with identical signals/summaries. |
| `src/codegenie/graph/nodes/await_human.py` | Extend (small) — emit `resume.rejected` audit event when `model_validate` raises during resume. (If this isn't already wired by S4-08, this story extends it; if it is, no-op.) |
| `src/codegenie/cli/loop.py` | Cross-reference only — `_warn_on_same_sig_continue` is S6-03's deliverable; this story imports it for the warning-emitter sub-test. |

## Out of scope

- **Implementing Gap 4 option (a) or (b).** Those are deliberate-future-change paths requiring ADR-P6-009. This story pins option (c).
- **The CLI surface for resume.** S6-03 owns `codegenie loop resume`; this story imports the warning emitter but does not test the CLI invocation end-to-end (a subprocess test).
- **Cross-phase amendment of `HumanDecision.action`.** If Phase 11 needs a fourth Literal, that's a Phase-11-coordinated change — out of scope here.
- **Operator authentication (Ed25519, HMAC).** Deferred to Phase 11/16 per ADR-0008.
- **HITL contract export.** S7-05 ships `docs/contracts/hitl-v0.6.0.json` + the CI gate.

## Notes for the implementer

- **Test 1 is documentation in test form.** Its value is forward-looking: a future engineer who reads `phase-arch-design.md §Gap 4` and decides to "fix" the silent-non-retryable behavior will see this test red-fail on their change. The test docstring should explicitly call out that this is *intentional behavior being documented*, not a desired-state assertion — so the engineer reads the docstring, finds ADR-P6-009 (or the gap reference), and brings the team into the loop instead of silently flipping the test green.
- **Why `cli.loop._warn_on_same_sig_continue` (and not a model-level emitter).** The warning is operator-facing; the model layer (`graph/`) is forbidden from emitting stderr (it's pure-data). S6-03 owns the CLI emitter; this story consumes it. If S6-03 hasn't landed it, surface the dependency loudly — do *not* invent a graph-layer emitter to make this test pass.
- **Why all seven malformed payloads in Test 2.** Each pins a different Pydantic constraint: Literal value, empty-string vs Literal, None coercion, type coercion, required-field, required-field, `extra="forbid"`. A test that only covered `action="approve"` would silently accept (say) a missing `operator` field if `HumanDecision` ever relaxes that constraint. Seven cases × seven constraints = a comprehensive contract gate.
- **`resume.rejected` audit event.** If `await_human` doesn't emit one yet, add the emit as part of this story's green pass. The event payload shape:
  ```python
  GraphEvent(
      kind="resume",
      payload={"reason": "malformed_decision", "errors": [...]},  # pydantic errors list
      at=datetime.now(UTC),
  )
  ```
  ADR-0007's chain extension means this event extends the BLAKE3 chain; the chain integrity check on next resume validates it. A separate sub-test in Test 2 can assert the chain extends correctly across a rejected resume (no chain break).
- **`HumanDecision.note` is plain text, never flowed into any LLM prompt.** ADR-0008 §Tradeoffs makes this explicit; S4-05 ships `test_hitl_note_not_in_prompt.py` to enforce. This story does *not* duplicate that check; Test 1 uses `note="..."` to confirm the human's reasoning persists in state but never asserts the note is or isn't in a prompt.
- **The override/abort sub-tests in Test 1** are small (~10 lines each) but important: they pin the *legitimate* operator escape hatches when the flake detector keeps firing. An operator who finds themselves in the "continue keeps re-firing" loop should be able to grep the test file for `override` and find the documented remedy.
- **Effort sizing rationale.** S because (a) the test shapes are small, (b) the mocked infrastructure is shared with S7-01, (c) the only new code is the `same_signature_outcomes()` helper (≤ 20 LOC) and possibly the `resume.rejected` audit emit (≤ 10 LOC). Total story size: ~150 LOC across two test files plus one helper. A junior implementer should expect 2–3 hours.
- **Regression risk if this story is skipped:** medium-high. Without Test 1, a future engineer "fixes" Gap 4 silently and the change ships unnoticed. Without Test 2, a `HumanDecision` constraint silently relaxes (e.g., `extra="forbid"` flipped to `extra="ignore"`) and bad payloads start being accepted. Both failure modes are easy to miss in code review and are exactly what the canary discipline exists to catch.
