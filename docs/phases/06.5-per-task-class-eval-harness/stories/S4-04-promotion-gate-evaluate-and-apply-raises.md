# Story S4-04 — `PromotionGate.evaluate` (all-conditions) + `apply()` raises unconditionally

**Step:** Step 4 — Wire the CLI and the read-only promotion gate
**Status:** Ready
**Effort:** M
**Depends on:** S1-02 (wire models — `BenchRunReport`, `PromotionVerdict`, `FailureMode`), S2-04 (`audit.verify` for the chain check), S1-01 (typed errors — `IncompleteReportForPromotion`, `PromotionMustBeHumanAuthorized`, `TierConfigInvalid`)
**ADRs honored:** ADR-0002 (gate keys on `lower_bound_95`), ADR-0003 (tier IDs as `str`, validated at startup against `docs/trust-tiers.yaml`), ADR-0004 (`block`-severity failure modes are data, not free-text), ADR-0009 (automatic-demotion is recommendation-shift), ADR-0010 (`isolation_class` homogeneous across evidence window), Phase 5 ADR-0016 (eval-harness-as-trust-evidence), Production ADR-0009 (humans always merge → `apply()` raises)

## Context

`PromotionGate` is the read-only verdict surface. Phase 5 ADR-0016 §Decision §4 made "zero block-severity failure modes" a load-bearing precondition; ADR-0002 shifted the score signal from `mean` to `lower_bound_95`; Gap #4 added the `complete: bool` reject path; Gap #1 / ADR-0010 added the homogeneous-`isolation_class` precondition. Every one of these is a separate ADR amendment over the original synthesis; collapsing them into a single, structurally-enforced `evaluate(...)` is the load-bearing engineering work of this phase.

The gate's contract is two methods. `evaluate(report)` returns a `PromotionVerdict` with `evidence_sufficient: bool` and `reasons: tuple[str, ...]`. `apply()` raises `PromotionMustBeHumanAuthorized` **unconditionally** — the interface exists as a discoverability marker; calling it is itself a finding (per `phase-arch-design.md §Tradeoffs (consolidated)`). The asymmetry is structural: there is no flag, no constructor parameter, no test fixture that lets `apply()` succeed. This is how "Humans always merge" (production ADR-0009) becomes load-bearing code, not aspirational prose.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design → src/codegenie/eval/promotion.py` — class signature, the all-conditions enumeration, `reasons` discipline.
  - `../phase-arch-design.md §Dynamic view → Sequence: 14-day silver-promotion candidate` — the day-15 verdict-flip walkthrough; the verdict is data, the human PR is the only effect.
  - `../phase-arch-design.md §Failure modes table` — rows for `IncompleteReportForPromotion` (Gap #4) and the homogeneous-`isolation_class` check (Gap #1).
  - `../phase-arch-design.md §Gap analysis Gap 1, Gap 4` — both gaps land their fix in this gate's evaluation logic.
  - `../phase-arch-design.md §Tradeoffs (consolidated)` — `apply()` raises unconditionally; "calling it is itself a finding."
- **Phase ADRs:**
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md` — `evidence_sufficient` keys on `report.lower_bound_95 ≥ tier_config.thresholds[target_tier]`, not `mean_score`. `reasons` enumerates the lower-bound shortfall explicitly when False (e.g., `"lower_bound_95=0.78 < threshold=0.80"`).
  - `../ADRs/0003-tier-identifiers-as-str-validated-at-startup.md` — `PromotionGate.__init__(tier_config)` validates tier names against `docs/trust-tiers.yaml`; unknown → `TierConfigInvalid`.
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md` — `report.block_severity_failure_modes` is `tuple[str, ...]`; non-empty → `evidence_sufficient=False` with one `reasons` entry per code.
  - `../ADRs/0009-automatic-demotion-as-recommendation-shift.md` — when a verdict implies demotion, the gate writes a recommendation (S4-05) but does not mutate state.
  - `../ADRs/0010-isolation-class-annotation-on-bench-run-report.md` — `evaluate` checks the evidence-window's `isolation_class` is homogeneous; mixed → `evidence_sufficient=False` with `reasons=("isolation_class mixed: subprocess and microvm in window",)`.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` — the structural rationale `apply()` raises.
  - `../../../production/adrs/0015-trust-score-threshold-calibration.md` — the threshold-calibration ADR whose numbers `docs/trust-tiers.yaml` carries (uncalibrated in Phase 6.5).
- **Source design:** `../High-level-impl.md §Step 4` — names every condition in the all-conditions check explicitly.
- **Phase 5 ADR-0016:** `../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md` §Decision §4 — the parent ADR this gate operationalizes.

## Goal

Land `src/codegenie/eval/promotion.py` with `PromotionGate(tier_config: TierConfig)` whose `evaluate(report, target_tier, *, evidence_window=())` returns `evidence_sufficient=True` iff ALL six conditions pass, enumerates each failing condition in `reasons`, raises `IncompleteReportForPromotion` on `report.complete=False`, and whose `apply()` always raises `PromotionMustBeHumanAuthorized`.

## Acceptance criteria

- [ ] `src/codegenie/eval/promotion.py` defines `TierConfig` as `@dataclass(frozen=True, slots=True)` with `thresholds: Mapping[str, float]` and `current_tiers: Mapping[str, str]`; both loaded from `docs/trust-tiers.yaml` at CLI startup (loader function `load_tier_config(path)` returns `TierConfig`).
- [ ] `PromotionGate.__init__(tier_config: TierConfig, registry: TaskClassRegistry | None = None)` validates at construction time that every tier name in `tier_config.thresholds`, every value in `tier_config.current_tiers`, and every key in every registered `TaskClass.min_cases_for_promotion` is a member of the YAML-declared tier set; unknown tier → `TierConfigInvalid(unknown_tier, available_tiers)` (per ADR-0003).
- [ ] `PromotionGate.evaluate(report: BenchRunReport, target_tier: str, *, evidence_window: tuple[BenchRunReport, ...] = ()) -> PromotionVerdict`:
  - Raises `IncompleteReportForPromotion(run_id)` if `report.complete is False` (Gap #4 reject path; partial reports cannot be evidence).
  - Returns `evidence_sufficient=True` if and only if **ALL** of:
    1. `report.lower_bound_95 >= tier_config.thresholds[target_tier]` (ADR-0002).
    2. `report.passed_count >= task_class.min_cases_for_promotion[target_tier]` (Phase 5 ADR-0016 §Decision §4).
    3. `report.block_severity_failure_modes == ()` (ADR-0004; zero block-severity codes).
    4. `audit.verify(out_dir=...).ok is True` (chain-integrity precondition; the verify call is delegated to S2-04's `audit.verify`).
    5. `report.complete is True` (Gap #4 — already gated by the raise above, but the verdict-time check is the documented "happy path" assertion).
    6. All reports in `(evidence_window + (report,))` share `isolation_class` (Gap #1 / ADR-0010); mixed window → False.
  - When False, `reasons` lists every failing condition individually as a human-readable string; passing conditions are NOT listed; an empty `reasons` tuple is forbidden when `evidence_sufficient=False` (the test pins this).
- [ ] `reasons` discipline (specific strings the test pins):
  - Threshold shortfall: `"lower_bound_95={x:.3f} < threshold[{tier}]={y:.3f}"`.
  - Case-count shortfall: `"passed_count={x} < min_cases_for_promotion[{tier}]={y}"`.
  - Block-severity failure modes: one entry per code, format `"block-severity failure: {code}"`.
  - Chain tamper: `"audit.verify().ok is False at {tamper_at}"`.
  - Isolation-class mixed: `"isolation_class mixed in evidence window: {sorted_set}"`.
- [ ] `PromotionGate.apply(verdict: PromotionVerdict | None = None, **kwargs: object) -> NoReturn`: **unconditionally** raises `PromotionMustBeHumanAuthorized` with a message naming the operator's escalation path (a PR against `docs/trust-tiers.yaml` + an ADR amendment). The signature accepts arbitrary kwargs so callers cannot work around the raise by adding an argument; every call site fails.
- [ ] **Adversarial test** `tests/adv/test_promotion_apply_raises.py` invokes `apply()` with every plausible argument shape (no args, with a verdict, with kwargs, with monkeypatched internals); every call raises `PromotionMustBeHumanAuthorized`.
- [ ] **Property test** asserts that `evidence_sufficient=True` implies `reasons` is empty *or* `reasons == ("all conditions met",)` (the architecture's documented happy-path verdict literal per `phase-arch-design.md §Dynamic view → Sequence: silver-promotion candidate`).
- [ ] Mutation-style coverage: for each of the six conditions, the test suite has a fixture where exactly that condition fails (all others pass); the resulting verdict's `reasons` contains exactly the one expected string and no others.
- [ ] The red test from §TDD plan exists, was committed at the red marker, and is now green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/test_promotion.py tests/adv/test_promotion_apply_raises.py` all pass on touched files.

## Implementation outline

1. Write red tests in `tests/unit/test_promotion.py` (the six-condition matrix) and `tests/adv/test_promotion_apply_raises.py` (the unconditional-raise asserter). See §TDD plan.
2. Create `src/codegenie/eval/promotion.py`:
   - `TierConfig` dataclass.
   - `load_tier_config(path: Path) -> TierConfig` reading `docs/trust-tiers.yaml`.
   - `PromotionGate.__init__` — startup tier validation per ADR-0003.
   - `PromotionGate.evaluate` — the six-condition all-AND logic; builds `reasons` by appending each failing condition's string.
   - `PromotionGate.apply` — single-line `raise PromotionMustBeHumanAuthorized(...)`.
3. Wire the chain-verify call (condition 4): the gate accepts an `audit_verify: Callable[[Path], VerifyResult] | None = None` constructor param defaulting to `codegenie.eval.audit.verify`; tests inject a fake to avoid filesystem setup for the unit suite. The default uses the real one.
4. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/eval/promotion.py`, `pytest tests/unit/test_promotion.py tests/adv/test_promotion_apply_raises.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/test_promotion.py
import pytest
from codegenie.eval.promotion import PromotionGate, TierConfig
from codegenie.eval.models import BenchRunReport, FailureMode
from codegenie.eval.errors import IncompleteReportForPromotion, TierConfigInvalid


def _make_report(
    *,
    lower_bound_95: float = 0.85,
    passed_count: int = 10,
    block_failures: tuple[str, ...] = (),
    complete: bool = True,
    isolation_class: str = "subprocess",
    run_id: str = "abc123def",
) -> BenchRunReport:
    # Helper using S1-02's wire model
    return BenchRunReport.model_construct(
        run_id=run_id,
        lower_bound_95=lower_bound_95,
        mean_score=lower_bound_95 + 0.05,
        score_stddev=0.08,
        passed_count=passed_count,
        block_severity_failure_modes=block_failures,
        complete=complete,
        isolation_class=isolation_class,
        chain_head="0" * 64,
        # ... other required fields filled with defaults
    )


def _tier_config() -> TierConfig:
    return TierConfig(
        thresholds={"bronze": 0.70, "silver": 0.80, "gold": 0.90},
        current_tiers={"vuln-remediation": "bronze"},
    )


def _gate(*, verify_ok: bool = True, tamper_at: str | None = None) -> PromotionGate:
    from types import SimpleNamespace

    def fake_verify(_out_dir):
        return SimpleNamespace(ok=verify_ok, tamper_at=tamper_at, verified_complete=10, verified_incomplete=0)

    return PromotionGate(tier_config=_tier_config(), audit_verify=fake_verify)


# Happy path
def test_evaluate_true_when_all_conditions_pass(stub_task_class_silver_min_25):
    gate = _gate()
    report = _make_report(lower_bound_95=0.85, passed_count=25)
    verdict = gate.evaluate(report, target_tier="silver", task_class=stub_task_class_silver_min_25)
    assert verdict.evidence_sufficient is True
    assert verdict.reasons in ((), ("all conditions met",))


# ADR-0002: lower_bound shortfall
def test_evaluate_false_when_lower_bound_below_threshold(stub_task_class_silver_min_25):
    gate = _gate()
    report = _make_report(lower_bound_95=0.78, passed_count=25)
    verdict = gate.evaluate(report, target_tier="silver", task_class=stub_task_class_silver_min_25)
    assert verdict.evidence_sufficient is False
    assert any("lower_bound_95=0.780" in r and "threshold[silver]=0.800" in r for r in verdict.reasons)


# Phase 5 ADR-0016 §4: case-count shortfall
def test_evaluate_false_when_passed_count_below_floor(stub_task_class_silver_min_25):
    gate = _gate()
    report = _make_report(lower_bound_95=0.85, passed_count=10)
    verdict = gate.evaluate(report, target_tier="silver", task_class=stub_task_class_silver_min_25)
    assert verdict.evidence_sufficient is False
    assert any("passed_count=10" in r and "min_cases_for_promotion[silver]=25" in r for r in verdict.reasons)


# ADR-0004: block-severity failures
def test_evaluate_false_with_block_severity_failure(stub_task_class_silver_min_25):
    gate = _gate()
    report = _make_report(block_failures=("validator.tests_failed", "validator.cve_not_dropped"))
    verdict = gate.evaluate(report, target_tier="silver", task_class=stub_task_class_silver_min_25)
    assert verdict.evidence_sufficient is False
    assert "block-severity failure: validator.tests_failed" in verdict.reasons
    assert "block-severity failure: validator.cve_not_dropped" in verdict.reasons


# Audit chain tamper
def test_evaluate_false_when_audit_verify_not_ok(stub_task_class_silver_min_25):
    gate = _gate(verify_ok=False, tamper_at="/path/to/record-001.json")
    report = _make_report()
    verdict = gate.evaluate(report, target_tier="silver", task_class=stub_task_class_silver_min_25)
    assert verdict.evidence_sufficient is False
    assert any("audit.verify().ok is False" in r and "/path/to/record-001.json" in r for r in verdict.reasons)


# Gap #4: complete=False raises (not returns)
def test_evaluate_raises_on_incomplete_report(stub_task_class_silver_min_25):
    gate = _gate()
    report = _make_report(complete=False, run_id="partial:abc")
    with pytest.raises(IncompleteReportForPromotion):
        gate.evaluate(report, target_tier="silver", task_class=stub_task_class_silver_min_25)


# Gap #1 / ADR-0010: mixed isolation_class in window
def test_evaluate_false_when_isolation_class_mixed(stub_task_class_silver_min_25):
    gate = _gate()
    prior = _make_report(isolation_class="microvm", run_id="prior01")
    report = _make_report(isolation_class="subprocess")
    verdict = gate.evaluate(
        report,
        target_tier="silver",
        task_class=stub_task_class_silver_min_25,
        evidence_window=(prior,),
    )
    assert verdict.evidence_sufficient is False
    assert any("isolation_class mixed" in r for r in verdict.reasons)


# All-conditions: every failing condition appears in reasons
def test_evaluate_enumerates_every_failing_condition(stub_task_class_silver_min_25):
    gate = _gate(verify_ok=False, tamper_at="/tmp/x")
    report = _make_report(
        lower_bound_95=0.50, passed_count=3, block_failures=("validator.build_failed",)
    )
    verdict = gate.evaluate(report, target_tier="silver", task_class=stub_task_class_silver_min_25)
    assert verdict.evidence_sufficient is False
    # At least four distinct reasons (lower_bound, passed_count, block_failure, audit)
    assert len(verdict.reasons) >= 4


# ADR-0003: unknown tier at construction raises
def test_unknown_tier_in_config_raises_at_init():
    bad_config = TierConfig(
        thresholds={"bronze": 0.70, "platinumm": 0.95},  # typo
        current_tiers={"vuln-remediation": "bronze"},
    )
    with pytest.raises(TierConfigInvalid) as exc_info:
        PromotionGate(tier_config=bad_config)
    assert "platinumm" in str(exc_info.value)


def test_unknown_tier_in_current_tiers_raises_at_init():
    bad_config = TierConfig(
        thresholds={"bronze": 0.70, "silver": 0.80},
        current_tiers={"vuln-remediation": "silvr"},  # typo
    )
    with pytest.raises(TierConfigInvalid):
        PromotionGate(tier_config=bad_config)
```

```python
# tests/adv/test_promotion_apply_raises.py
import pytest
from codegenie.eval.promotion import PromotionGate
from codegenie.eval.errors import PromotionMustBeHumanAuthorized


@pytest.fixture
def gate_with_valid_config():
    from codegenie.eval.promotion import TierConfig

    return PromotionGate(
        tier_config=TierConfig(
            thresholds={"bronze": 0.70, "silver": 0.80, "gold": 0.90},
            current_tiers={},
        )
    )


def test_apply_no_args_raises(gate_with_valid_config):
    with pytest.raises(PromotionMustBeHumanAuthorized):
        gate_with_valid_config.apply()


def test_apply_with_verdict_raises(gate_with_valid_config):
    # Even a "valid" verdict cannot make apply() succeed
    with pytest.raises(PromotionMustBeHumanAuthorized):
        gate_with_valid_config.apply(verdict=object())


def test_apply_with_arbitrary_kwargs_raises(gate_with_valid_config):
    with pytest.raises(PromotionMustBeHumanAuthorized):
        gate_with_valid_config.apply(force=True, override=True, signed_off_by="root")


def test_apply_raise_message_names_escalation_path(gate_with_valid_config):
    with pytest.raises(PromotionMustBeHumanAuthorized) as exc_info:
        gate_with_valid_config.apply()
    msg = str(exc_info.value)
    assert "trust-tiers.yaml" in msg
    assert "ADR" in msg or "PR" in msg


def test_apply_cannot_be_monkeypatched_to_succeed(gate_with_valid_config, monkeypatch):
    """Confirm there is no module-level flag the test can flip."""
    # We do NOT attempt to monkeypatch the method itself — the test asserts
    # that no constructor or module-level config makes apply() conditional.
    # Inspect the source: apply must contain exactly one `raise` statement,
    # gated by no `if` branches.
    import inspect, ast
    src = inspect.getsource(PromotionGate.apply)
    tree = ast.parse(src.strip().rstrip("\n") if not src.startswith("def") else src)
    # Walk the function: assert there is no `If` or `Try` node guarding the raise.
    for node in ast.walk(tree):
        assert not isinstance(node, ast.If), "apply() has an If branch — must be unconditional"
        assert not isinstance(node, ast.Try), "apply() has a Try block — must be a single raise"
```

Run; confirm failures. Commit as the red marker.

### Green — make it pass

Implement `promotion.py` per §Implementation outline. The body of `apply()` is exactly:

```python
def apply(self, *args: object, **kwargs: object) -> NoReturn:
    raise PromotionMustBeHumanAuthorized(
        "Tier promotion requires a human-authored PR against docs/trust-tiers.yaml "
        "with CODEOWNERS approval and an accompanying ADR amendment. "
        "See docs/production/adrs/0015-trust-score-threshold-calibration.md for the calibration path."
    )
```

No branches. The `*args/**kwargs` signature exists so accidental positional callers cannot bypass via `TypeError`.

`evaluate` is a sequence of `reasons: list[str] = []` accumulations; each condition appends on failure. `audit_verify` is called once (cache the result). Return `PromotionVerdict(evidence_sufficient=not reasons, reasons=tuple(reasons) if reasons else ("all conditions met",), ...)` — or `reasons=()` per the test's `in` assertion.

### Refactor — clean up

- Each condition check is a small private helper `_check_lower_bound(...)`, `_check_passed_count(...)`, etc., returning `str | None` (reason string on failure, `None` on pass). `evaluate` collects the non-None results.
- The six helper functions are tested individually (in addition to the integration test); this lets each ADR's condition be regression-tested in isolation.
- `mypy --strict`: `evaluate` returns `PromotionVerdict`; `apply` returns `NoReturn` (typing import from `typing`).
- Module docstring: cite ADR-0002, ADR-0003, ADR-0004, ADR-0009, ADR-0010, Phase 5 ADR-0016 §Decision §4, production ADR-0009. Reasoning load-bearing in the codebase.
- `PromotionVerdict`'s `reasons` is `tuple[str, ...]` per S1-02. Confirm the model accepts `()` (empty tuple) when `evidence_sufficient=True`; the test pins this is the happy-path output.
- Log structured events at `evaluate` start/end: `promotion_evaluated` with `evidence_sufficient`, `target_tier`, `reasons_count`. Useful for the Phase 13 dashboard backfill.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/promotion.py` | New file — `TierConfig`, `load_tier_config`, `PromotionGate`, `evaluate`, `apply`. |
| `tests/unit/test_promotion.py` | New file — the six-condition matrix + `__init__` validation. |
| `tests/adv/test_promotion_apply_raises.py` | New file — unconditional-raise asserter (signature-shapes test + AST audit). |
| `tests/unit/conftest.py` | Add `stub_task_class_silver_min_25` fixture (a `TaskClass` with `min_cases_for_promotion={"bronze": 10, "silver": 25}`). |

## Out of scope

- **`docs/trust-tiers.yaml` content** — S4-05 ships the minimal YAML with bronze candidate numbers + uncalibrated header. This story uses an in-memory `TierConfig` for tests and a `load_tier_config` callable for production wiring.
- **Recommendation file writing** — S4-05 owns `.codegenie/eval/recommendations/<utc-iso>.json` shape.
- **CLI wiring** — S4-02 (`--with-verdict` flag) calls `gate.evaluate(...)`; this story owns the gate logic, not the CLI integration.
- **Mixed-isolation-class override (`--allow-isolation-mix`)** — ADR-0010 §Open Q reserves it; not in Phase 6.5.
- **Demotion logic** — ADR-0009 (automatic-demotion-as-recommendation-shift) is honored by *not* implementing demotion as a side-effect. A separate "demotion recommendation" verdict could be emitted; this story does not, and the `reasons` tuple is the sole carrier of the operator-actionable signal.
- **Multi-window evidence aggregation** — `evidence_window` is a tuple of prior reports passed by the caller; this story does not implement window selection (which is Phase 5 / Phase 11 territory). The caller supplies the window; the gate checks `isolation_class` homogeneity over it.

## Notes for the implementer

- **The asymmetry between `evaluate` and `apply` is the entire point.** `evaluate` is rich, ADR-honoring, returns data. `apply` is one line, returns nothing, always raises. Resist any review feedback to "make `apply` symmetric" — the asymmetry is documented in `phase-arch-design.md §Tradeoffs (consolidated)` and is what makes "Humans always merge" structurally enforced.
- **`reasons` discipline matters for the operator UX.** When `evidence_sufficient=False`, the operator reads `reasons` and acts on each entry. If two ADRs' reasons collapse into one ambiguous string ("evidence insufficient"), the operator cannot tell whether to wait for more cases, fix a rubric, or investigate a chain tamper. The format strings pinned in §Acceptance criteria are the contract.
- **`audit_verify` injection is a testing affordance, not a public API.** Default it to `codegenie.eval.audit.verify`; do not let consumers swap it for "soft" verifiers. The CLI never passes this parameter; only the unit tests do.
- **Floating-point comparison for `lower_bound_95 ≥ threshold`** — use `>=` directly on `float`. The architecture-level ADR-0002 reasoning takes precision into account; introducing `math.isclose` or epsilons here adds a third statistic (epsilon) the operator must understand. Just `>=`.
- **`isolation_class` window check:** the homogeneity check compares the *set* of distinct values across `(evidence_window + (report,))`. Empty window + single report = trivially homogeneous (set size 1). Two reports with the same class = size 1 = pass. Any size > 1 = fail with the sorted set in the reason string.
- **`reasons` is a `tuple`, not a `list`.** S1-02 specifies `PromotionVerdict.reasons: tuple[str, ...]`. Build a `list` internally, return a `tuple(...)`. Pydantic's `frozen=True` is what makes the choice load-bearing.
- **The AST audit in `test_apply_cannot_be_monkeypatched_to_succeed`** is a deliberate over-test: it asserts that `apply` is *structurally* unconditional, not just *currently* unconditional. A future contributor cannot add `if force_override: return None` without breaking that test. This is the "fence" pattern from Phase 0 — codify the invariant in a test that walks the source.
- **`PromotionMustBeHumanAuthorized` message:** include the path operators must follow. The `phase-arch-design.md §Component design → promotion.py` documents the exact phrasing — name `docs/trust-tiers.yaml`, reference the CODEOWNERS gate, point at the calibration ADR. Operators who hit this exception should not have to grep the docs.
