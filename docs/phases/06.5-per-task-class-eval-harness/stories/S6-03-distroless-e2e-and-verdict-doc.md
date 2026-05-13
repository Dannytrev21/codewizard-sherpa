# Story S6-03 — `codegenie eval run` distroless E2E + N=3 conservative-verdict documentation

**Step:** Step 6 — Seed `bench/migration-chainguard-distroless/`
**Status:** Ready
**Effort:** S
**Depends on:** S6-02 (cases must exist and be signed), S4-04 (`PromotionGate.evaluate` must return typed verdicts)
**ADRs honored:** ADR-0002 (`lower_bound_95` is the gate signal; small-sample conservative), ADR-0006 (held-out floor governs silver — bronze is fine at N=3 *for case-count alone*; this story shows the verdict is still False), ADR-0009 (recommendation, not side-effect)

## Context

With registration + cases + rubric in place, the harness should run end-to-end against `migration-chainguard-distroless` and produce a `BenchRunReport` with N=3 per-case entries. The promotion gate is *supposed* to refuse to promote at N=3: even if the stub rubric scores all three at 1.0, the case-count floor (`min_cases_for_promotion["bronze"] = 10`) is not met, and `PromotionGate.evaluate(target_tier="bronze")` must return `evidence_sufficient=False` with `reasons` including "case count below floor" (3 < 10). This is the **conservative-by-design** behavior `final-design.md §Risks #3` warns curators about — the verdict is correct, not a bug, and the README must explain that so Phase 7 implementers don't misread the False verdict as a harness failure.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Scenarios → Scenario 4"` — promotion gate verdict flip logic; this story exercises the inverse (verdict-stays-False).
  - `../phase-arch-design.md §"Edge cases #13"` — N=3 conservative output is documented as intended.
  - `../phase-arch-design.md §"Component design → promotion.py"` — `evaluate(...)` ALL-conditions logic; `reasons` enumerates every failing condition.
  - `../phase-arch-design.md §"What's next — handoff to Phase 7"` — what Phase 7 must do structurally.
- **Phase ADRs:**
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md` — `lower_bound_95` at N=3 is one-sided and conservative; this is the point.
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md` — Phase 7 must grow corpus to ≥10 with ≥5 held-out.
  - `../ADRs/0009-automatic-demotion-as-recommendation-shift.md` — the verdict is advisory; tier changes are human PRs.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` — apply() raises; only humans promote.
- **Source design:** `../High-level-impl.md §"Step 6" §"Done criteria"` — exit 0; N=3; `evidence_sufficient=False`; README documents Phase 7 work.
- **Roadmap:** `../../../roadmap.md §"Phase 7"` — exit criteria reference `lower_bound_95 ≥ tier_threshold[bronze]` (after S7-03 lands the substitution).

## Goal

`codegenie eval run --task-class=migration-chainguard-distroless` exits 0 with three `per_case` entries; `PromotionGate.evaluate(target_tier="bronze")` returns `evidence_sufficient=False` with `reasons` enumerating "case count below floor (3 < 10)"; `bench/migration-chainguard-distroless/README.md` explains the conservative output and lists what Phase 7 must add.

## Acceptance criteria

- [ ] `codegenie eval run --task-class=migration-chainguard-distroless` exits 0 (no errors, no cost-cap, no tamper).
- [ ] The emitted `BenchRunReport` has exactly 3 `per_case` entries, all sorted by `case_id`, with `complete=True` and `isolation_class="subprocess"`.
- [ ] The audit chain extends by exactly one record after the run; `audit.verify().ok is True` over the resulting chain.
- [ ] `PromotionGate.evaluate(report, target_tier="bronze")` returns a `PromotionVerdict` with `evidence_sufficient=False` and `reasons` containing the exact substring `"case count below floor"` and naming `3 < 10`.
- [ ] If all three cases score 1.0 (the stub-rubric "everything correct" path), the `reasons` tuple **still** carries the case-count failure — case-count is checked independently of `lower_bound_95`.
- [ ] `PromotionGate.apply(verdict)` raises `PromotionMustBeHumanAuthorized` (no auto-mutation; ADR-0009 + production ADR-0009).
- [ ] `bench/migration-chainguard-distroless/README.md` exists and contains a "Phase 7 must add" section listing: (a) ≥7 more cases (≥5 held-out for silver eligibility per ADR-0006), (b) `silver` (and optionally `gold`) entries in `min_cases_for_promotion`, (c) rubric hardening (multi-stage detection, build sandboxing). It also explains that `evidence_sufficient=False` at N=3 is the intended conservative output (cite ADR-0002).
- [ ] The red test from §TDD plan exists, was committed at red, and is now green.
- [ ] `ruff format --check`, `ruff check`, `mypy --strict` clean; `pytest tests/integration/test_eval_end_to_end_distroless.py` passes.

## Implementation outline

1. Add `tests/integration/test_eval_end_to_end_distroless.py` driving `codegenie eval run --task-class=migration-chainguard-distroless` against a deterministic stub SUT (mirror `tests/integration/test_eval_end_to_end_vuln.py` from S5).
2. Add `tests/integration/test_promotion_at_n3.py` asserting `evidence_sufficient=False` + the exact `reasons` substring.
3. Hand-write `bench/migration-chainguard-distroless/README.md` with three sections:
   - "What this task class is" (one paragraph, link to ADR-0006).
   - "Why the N=3 verdict is `evidence_sufficient=False`" — cite ADR-0002 (`lower_bound_95` at small N) and the case-count floor logic; quote the actual `reasons` string the gate will emit.
   - "What Phase 7 must add" — the three structural deliverables above (≥7 more cases, silver tier entry, rubric hardening) plus a pointer to the extension-by-addition invariant in `CLAUDE.md`.
4. If the test harness needs a deterministic stub distroless SUT, add one to `tests/fixtures/sut/stub_distroless_sut.py` that emits a canned Dockerfile per input — small enough that all three cases score 1.0 deterministically.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/integration/test_eval_end_to_end_distroless.py`

```python
# tests/integration/test_eval_end_to_end_distroless.py
import json
import subprocess
from pathlib import Path

import pytest

from codegenie.eval.audit import verify as audit_verify
from codegenie.eval.promotion import PromotionGate

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_distroless_e2e_exits_0_with_three_per_case_entries(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = subprocess.run(
        ["codegenie", "eval", "run", "--task-class=migration-chainguard-distroless"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr

    # Find the emitted BenchRunReport.
    runs = sorted((tmp_path / ".codegenie/eval/runs").glob("*.json"))
    assert len(runs) == 1
    report = json.loads(runs[0].read_text())

    assert len(report["per_case"]) == 3
    assert report["complete"] is True
    assert report["isolation_class"] == "subprocess"
    # Audit chain extends by exactly one record.
    verify_result = audit_verify(tmp_path / ".codegenie/eval/runs")
    assert verify_result.ok is True


def test_promotion_verdict_at_n3_is_evidence_insufficient(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(
        ["codegenie", "eval", "run", "--task-class=migration-chainguard-distroless"],
        check=True,
    )
    runs = sorted((tmp_path / ".codegenie/eval/runs").glob("*.json"))
    report_path = runs[0]
    # Use the in-process API to evaluate.
    from codegenie.eval.models import BenchRunReport
    report = BenchRunReport.model_validate_json(report_path.read_text())

    gate = PromotionGate.from_yaml(REPO_ROOT / "docs/trust-tiers.yaml")
    verdict = gate.evaluate(report, target_tier="bronze")

    assert verdict.evidence_sufficient is False
    # The case-count failure must be enumerated explicitly.
    assert any("case count below floor" in r for r in verdict.reasons)
    assert any("3" in r and "10" in r for r in verdict.reasons)


def test_promotion_apply_raises_even_with_perfect_scores(tmp_path, monkeypatch):
    # Even on the (hypothetical) all-1.0 case, apply() must raise — humans always merge.
    from codegenie.eval.errors import PromotionMustBeHumanAuthorized
    from codegenie.eval.models import PromotionVerdict
    gate = PromotionGate.from_yaml(REPO_ROOT / "docs/trust-tiers.yaml")
    fake_verdict = PromotionVerdict(
        task_class="migration-chainguard-distroless",
        target_tier="bronze",
        evidence_sufficient=False,
        reasons=("case count below floor (3 < 10)",),
        requires_human_approval=True,
    )
    with pytest.raises(PromotionMustBeHumanAuthorized):
        gate.apply(fake_verdict)
```

Run; confirm exit-2 / `FileNotFoundError` on `.codegenie/eval/runs/`. Commit as red.

### Green

Wire the deterministic stub SUT, run the CLI, write the three-sentence README. If the CLI flag `--task-class` already supports the registered slug (S4-02), this story is mostly content — the harness machinery is unchanged.

### Refactor

- Confirm `verdict.reasons` is a tuple, not a list (frozen wire type, ADR-0008-ish discipline).
- Confirm the README's "Phase 7 must add" section names the held-out floor (≥5) explicitly — this is the load-bearing fact ADR-0006 commits Phase 7 to.
- Add a one-line cite in the README pointing at `tests/integration/test_promotion_at_n3.py` so future readers can find the executable contract.
- Verify the audit chain test (`audit_verify`) walks cleanly — if `report.chain_head` is populated by `audit.write_run_record` (S2-04), no extra wiring needed.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_eval_end_to_end_distroless.py` | New — E2E exit-0 + 3 per_case + audit chain extension |
| `tests/integration/test_promotion_at_n3.py` (or merged into above) | New — `evidence_sufficient=False` + reasons substring |
| `bench/migration-chainguard-distroless/README.md` | New — explains conservative output + what Phase 7 must add |
| `tests/fixtures/sut/stub_distroless_sut.py` | New, if not already present — deterministic SUT for E2E |

## Out of scope

- **Fence-CI assertions** — S7-01 lands them and exercises this corpus.
- **Audit chain golden snapshots** — S7-02 freezes `bench_run_report.v1.json` shape.
- **Cross-phase ADR amendments** (Phase 4, Phase 5, roadmap §Phase 7 wording) — S7-03.
- **Expanding the corpus to ≥10** — Phase 7's exit criteria, not Phase 6.5.
- **Rubric hardening** (multi-stage detection, build sandboxing, semver of Chainguard image tags) — Phase 7.

## Notes for the implementer

- **The False verdict is the test target.** A green test where `evidence_sufficient=True` at N=3 indicates a bug in `PromotionGate.evaluate`'s ALL-conditions logic — fix the gate, not the test. The `case_count >= min_cases_for_promotion[target_tier]` precondition is checked *independently* of `lower_bound_95`; both must hold.
- **The `reasons` substring assertion is load-bearing.** Operators read this tuple; if you change the diagnostic to `"insufficient cases"`, every downstream tool that parses for "below floor" silently breaks. Mirror the exact phrasing the existing test_promotion unit test (from S4-04) uses.
- **README quality matters here** because it's the handoff document Phase 7 reads. Cite ADR-0002 by file path; quote ADR-0006's held-out-floor rule; quote ADR-0009 on apply()-raises. Three references — `Rule 8 Read before you write` applies to the *Phase 7 implementer* reading this README cold.
- **The deterministic stub SUT can be trivial** — it returns the `expected/Dockerfile` byte-for-byte for each input. This produces score=1.0 on all three; the case-count floor is what fails the verdict. Don't over-engineer the SUT.
- **`audit.verify` semantics for genesis** — if this is the very first run on a fresh `.codegenie/eval/runs/` directory, the run record is the genesis (`prev_hash == "0" * 64`). The integration test must run in a tmp_path so it doesn't depend on prior chain state. Mirror S5-05's pattern.
- **Do not document the bootstrap CI math in the README.** It's tempting to teach `BCa` here; leave that to ADR-0002. The README is a Phase 7 implementer's pointer document, not a stats lesson.
- **Watch for cost-cap path.** With three cases and a stub SUT, total_cost_usd is 0.00 — `complete=True` should hold. If it doesn't, the `cost_tag` shim (S2-06) is misbehaving.
