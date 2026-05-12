# Story S4-05 — `TrustScorer` strict-AND + `gate.py` orchestration + `gate.signal_escalate` operator surface (JSON + report + banner)

**Step:** Step 4 — Ship `LockfilePolicyScanner` (graded escape) and the single-profile `ValidationGate` (install/test/build + signal-escalate)
**Status:** Ready
**Effort:** L
**Depends on:** S4-03 (`test_validator` + `requires_network` signal), S4-04 (`build_validator` skipped + present), S4-01 (`LockfilePolicyScanner` for upstream signals), S1-07 (audit event types)
**ADRs honored:** ADR-0013 (strict-AND of binary objective signals; no LLM), ADR-0005 (`gate.signal_escalate` operator surface — Gap 3), ADR-0010 (audit chain — `gate.failed`, `gate.signal_escalate`), ADR-0008 (production: objective-signal trust score)

## Context

This story closes the Step 4 ring. `TrustScorer.score(signals)` is the strict-AND of nine binary objective signals per ADR-0013 — any false → `"low"`; all true and `tests.duration_vs_baseline_pct ≤ 150` → `"high"`; otherwise `"medium"`. The `gate.py` module composes the three validators (install → test → build, in that order; first failure short-circuits the chain except where `requires_network=true` is special-cased) and produces a `GateOutcome` that the orchestrator (S5-03) maps to exit codes 0/6/8.

The **single most architecturally critical responsibility** of this story is the `gate.signal_escalate` operator surface (Gap 3 from `phase-arch-design.md §"Gap analysis"`). In a service deployment, Phase 11 routes `signal_escalate` to a CODEOWNERS Slack message; in the **local POC**, there is no automated human-routing layer. The operator surface compensates:

1. **JSON event file** at `.codegenie/remediation/<run-id>/escalations/<utc>.json` — machine-readable, audit-grade.
2. **`remediation-report.yaml#escalations[]` section** populated with the same record — operator-discoverable through the canonical report.
3. **CLI stderr banner** printed prominently on exit 8 (wired in S5-05) — operator-discoverable in the terminal.

The strict-AND posture is conservative by construction (ADR-0013 tradeoff): a flaky test fails closed; an actually-broken bump also fails closed. The audit log records *which* signal flipped, so Phase 4 RAG and Phase 8 calibration can read the failure signal directly. The Hypothesis property test pins strict-AND semantics under arbitrary signal combinations.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #11 ValidationGate` — `validate()` orchestration shape.
  - `../phase-arch-design.md §"Component design" #12 TrustScorer` — strict-AND of nine objective signals; tier semantics (high/medium/low); rationale.
  - `../phase-arch-design.md §"Gap 3"` — `gate.signal_escalate` has no human in the local POC; operator surface = JSON + report + banner.
  - `../phase-arch-design.md §"Edge cases"` rows #2, #4 — gate-failed and signal-escalate exit paths.
- **Phase ADRs:**
  - `../ADRs/0013-confidence-strict-and-of-binary-signals-no-llm.md` — ADR-0013 — strict-AND signal set frozen at v0.3.0; signal additions require ADR amendment.
  - `../ADRs/0005-single-sandbox-profile-test-execution-overlay-signal-escalate.md` — ADR-0005 — `gate.signal_escalate` semantics; non-auto-allow posture.
  - `../ADRs/0010-audit-chain-extension-cache-replay-event.md` — ADR-0010 — `gate.failed` payload `{failing_signal, validator_name}` + `gate.signal_escalate` payload `{signature_matched, suggested_flag, validator_name}`.
- **Production ADRs:**
  - `../../../production/adrs/0008-objective-signal-trust-score.md` — load-bearing; no LLM self-confidence; strict-AND.
- **Source design:**
  - `../final-design.md §Goals #16` — strict-AND signal set listing.
  - `../final-design.md §"Components" #7 ValidationGate` — `GateOutcome` shape.
- **Existing code:**
  - `src/codegenie/transforms/contract.py` (S1-02) — `ValidatorOutput`, `Confidence` (`Literal["high", "medium", "low"]`).
  - `src/codegenie/transforms/validation/install.py` (S4-02), `test.py` (S4-03), `build.py` (S4-04), `lockfile_policy.py` (S4-01).
  - `src/codegenie/audit/events.py` (S1-07) — `gate.failed`, `gate.signal_escalate` Pydantic payloads.
  - Phase 0 `RunIdResolver` or equivalent for `<run-id>` path resolution under `.codegenie/remediation/`.

## Goal

Implement (a) `src/codegenie/transforms/validation/trust_score.py` exposing `TrustScorer.score(signals: dict) -> TrustScore(binary, confidence, detail)` as a strict-AND over the nine signals per ADR-0013; (b) `src/codegenie/transforms/validation/gate.py` exposing `validate(transform_output, *, allow_test_network) -> GateOutcome` that orchestrates install → test → build → trust-score and emits the audit events; (c) the `gate.signal_escalate` operator surface — `.codegenie/remediation/<run-id>/escalations/<utc>.json` JSON file + `GateOutcome.escalation_record` field for `remediation-report.yaml#escalations[]` population by S5-04.

## Acceptance criteria

- [ ] `TrustScore(binary: bool, confidence: Confidence, detail: dict[str, object], schema_version: Literal["v1"])` is a Pydantic model in `codegenie.transforms.validation.trust_score`; `model_config = ConfigDict(extra="forbid")`.
- [ ] `TrustScorer.score(signals: Mapping[str, object]) -> TrustScore` is defined and importable. It reads the **nine closed-enum signals** by name:
  - `lockfile.parse_ok`
  - `lockfile.policy_violation_count_zero`
  - `recipe.engine.exit_status_zero`
  - `npm.install.exit_status_zero`
  - `npm.install.disallowed_egress_bytes_zero`
  - `tests.exit_status_zero`
  - `tests.duration_vs_baseline_within_200pct`
  - `cve.delta.direction_non_increasing`
  - `patch.git_apply_dryrun_ok`
- [ ] Strict-AND: `binary = all(signals.get(s, False) for s in REQUIRED_SIGNALS)`. `confidence` derivation per ADR-0013:
  - `binary=False` → `"low"`.
  - `binary=True` AND `signals.get("tests.duration_vs_baseline_within_150pct", False)` → `"high"`.
  - Otherwise → `"medium"`. (The medium tier exists *only* for signal-escalate AND for the duration-band-between-150-and-200 case.)
- [ ] `TrustScore.detail` records which signals were true/false: `{"flipped_signal": <first-false-signal-name-or-None>, "all_signals": {<name>: <bool>}}`. The audit chain consumer reads `detail.flipped_signal` to surface "which signal failed."
- [ ] `REQUIRED_SIGNALS: Final[tuple[str, ...]]` is a module-level constant; **closed at v0.3.0** — signal additions require ADR-0013 amendment + this constant's update + snapshot test update in the same PR (cross-cutting "snapshot-frozen ABC contracts" applies by analogy).
- [ ] `GateOutcome(green: bool, confidence: Confidence, validators: list[ValidatorOutput], signal_escalate: bool, trust_score: TrustScore, escalation_record: EscalationRecord | None, schema_version: Literal["v1"])` is a Pydantic model with `extra="forbid"`.
- [ ] `EscalationRecord(kind: Literal["signal_escalate"], suggested_flag: Literal["--allow-test-network"], signature: str, signal: str, validator_name: str, timestamp_utc: str, run_id: str, schema_version: Literal["v1"])` is the JSON-serialized record.
- [ ] `validate(transform_output: TransformOutput, *, allow_test_network: bool, lockfile_scan_result: LockfileScanResult) -> GateOutcome` is defined and importable from `codegenie.transforms.validation.gate`.
- [ ] `validate` orchestration runs:
  1. `install_validator(transform_output)` → if `passed=False`, short-circuit; compute trust score; emit `gate.failed` audit event; return `GateOutcome(green=False, signal_escalate=False, ...)`.
  2. `test_validator(transform_output, allow_test_network=allow_test_network)` → if `passed=False` AND `requires_network=True`: write escalation JSON; emit `gate.signal_escalate` audit event (validator already emitted from S4-03; gate emits an additional gate-side event for the operator surface, OR — preferred — gate reads the validator's signal and skips re-emission; **the implementation choice is: gate does NOT re-emit `gate.signal_escalate`** — single emission, validator-owned, per S4-03; gate emits `gate.failed` with `failing_signal="requires_network"` for the parallel audit channel); short-circuit with `signal_escalate=True`.
  3. `test_validator passed=False` AND `requires_network=False` → emit `gate.failed`; short-circuit with `signal_escalate=False`.
  4. `build_validator(transform_output)` → if `passed=False`, short-circuit; emit `gate.failed`.
  5. All validators passed → compose `signals` dict from `ValidatorOutput.signals` of each validator + `lockfile_scan_result.violations == []` → `lockfile.policy_violation_count_zero` signal + the upstream `recipe.engine.exit_status_zero`, `cve.delta.direction_non_increasing`, `patch.git_apply_dryrun_ok` signals (populated by S5-01 + S5-03 — gate reads from `transform_output.upstream_signals` dict, populated by the orchestrator).
  6. `TrustScorer.score(signals)` → `TrustScore`.
  7. Return `GateOutcome(green=trust_score.binary, confidence=trust_score.confidence, validators=[install, test, build], signal_escalate=False, trust_score=trust_score, escalation_record=None)`.
- [ ] When `signal_escalate=True`, the gate writes `.codegenie/remediation/<run-id>/escalations/<utc>.json` containing the `EscalationRecord` (serialized via `model_dump_json(indent=2)`); `<utc>` is `datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")` for filename safety. Parent dirs are created. The path is recorded in `GateOutcome.escalation_record` as `{"path": str(path), "record": EscalationRecord(...)}`.
- [ ] **Single-emission discipline:** `gate.signal_escalate` audit event is emitted by `test_validator` (S4-03), NOT by `gate.py`. `gate.py` emits `gate.failed` with `failing_signal="requires_network"` when the test validator signal-escalates. This keeps the audit vocabulary clean: signal-escalate is a property of the test validator's signal; gate-failed is a property of the gate's decision. Single emission per event-type per run.
- [ ] `tests/unit/transforms/validation/test_trust_score.py` ships ≥ 5 cases: (a) all nine signals true + 150pct true → `"high"`; (b) all nine true + 150pct false → `"medium"`; (c) one signal false → `"low"`, `detail.flipped_signal` records the name; (d) all-false → `"low"`, `flipped_signal` is the first signal in `REQUIRED_SIGNALS` order; (e) unknown signal in input → ignored (no key error); `flipped_signal` is the first missing required signal.
- [ ] `tests/unit/transforms/validation/test_trust_score_strict_and.py` ships a Hypothesis property test: given arbitrary `dict[str, bool]` with subset of required keys, assert `TrustScorer.score(d).binary == all(d.get(s, False) for s in REQUIRED_SIGNALS)`.
- [ ] `tests/unit/transforms/validation/test_gate.py` ships ≥ 4 cases: (a) install fails → short-circuit, no test/build call; (b) test fails with network signature → `signal_escalate=True`, escalation JSON written to disk, `gate.failed` event with `failing_signal="requires_network"` emitted; (c) test fails without network signature → `signal_escalate=False`, `gate.failed` with `failing_signal="tests.exit_status"`; (d) all green → `GateOutcome(green=True, confidence="high")`, no `gate.failed` emitted.
- [ ] `tests/unit/transforms/validation/test_escalation_record.py` pins the JSON shape: extra-field rejection; UTC timestamp format; closed-enum on `kind` and `suggested_flag`.
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write the failing tests under `tests/unit/transforms/validation/test_trust_score.py`, `test_trust_score_strict_and.py`, `test_gate.py`, `test_escalation_record.py`.
2. Create `src/codegenie/transforms/validation/trust_score.py`:
   - `REQUIRED_SIGNALS: Final[tuple[str, ...]] = (...nine names in declaration order...)`.
   - `TrustScore` Pydantic model with `extra="forbid"`.
   - `class TrustScorer: @staticmethod def score(signals): ...`.
   - Body computes `binary`, finds `flipped_signal` (first required signal that is missing or false), derives `confidence` per ADR-0013 tier rules, returns `TrustScore`.
3. Create `src/codegenie/transforms/validation/gate.py`:
   - `EscalationRecord` Pydantic model.
   - `GateOutcome` Pydantic model.
   - `validate(transform_output, *, allow_test_network, lockfile_scan_result) -> GateOutcome` orchestration.
   - Use `from datetime import datetime, UTC` for timestamp.
   - Resolve escalations path: `transform_output.worktree_root.parent / ".codegenie/remediation" / transform_output.run_id / "escalations"` — actually, `.codegenie/remediation/<run-id>/escalations/` lives at the repo root, not under the worktree. Cross-check S5-04 (`PatchBranchWriter`) for the canonical path resolution; use the same helper.
   - Compose `signals` dict from each `ValidatorOutput.signals` + `lockfile_scan_result.violations == []` + `transform_output.upstream_signals` (dict populated by S5-01 with `recipe.engine.exit_status_zero`, `cve.delta.direction_non_increasing`, `patch.git_apply_dryrun_ok`, `lockfile.parse_ok`).
   - Map `ValidatorOutput.signals` keys to the strict-AND signal vocabulary — e.g., `signals["npm.install.exit_status_zero"] = (install.signals["npm.install.exit_status"] == 0)`. Define this mapping as a small static dict in the module.
4. Audit-event emission via the S1-07 `audit.writer.append(event_name, payload=...)` API. Only `gate.failed` is emitted from this module; `gate.signal_escalate` stays with the test validator (single-emission discipline).
5. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest tests/unit/transforms/validation/`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Path: `tests/unit/transforms/validation/test_trust_score.py`

```python
import pytest

from codegenie.transforms.validation.trust_score import (
    REQUIRED_SIGNALS, TrustScorer,
)


def _all_true() -> dict[str, bool]:
    return {s: True for s in REQUIRED_SIGNALS}


def test_high_confidence_requires_150pct_band() -> None:
    signals = _all_true() | {"tests.duration_vs_baseline_within_150pct": True}
    score = TrustScorer.score(signals)
    assert score.binary is True
    assert score.confidence == "high"


def test_medium_when_all_true_but_150pct_missing() -> None:
    signals = _all_true()  # 150pct flag NOT set
    score = TrustScorer.score(signals)
    assert score.binary is True
    assert score.confidence == "medium"


def test_low_when_any_required_signal_false() -> None:
    signals = _all_true() | {"tests.exit_status_zero": False}
    score = TrustScorer.score(signals)
    assert score.binary is False
    assert score.confidence == "low"
    assert score.detail["flipped_signal"] == "tests.exit_status_zero"


def test_first_false_in_declaration_order_is_flipped(self) -> None:
    signals = {s: False for s in REQUIRED_SIGNALS}
    score = TrustScorer.score(signals)
    assert score.detail["flipped_signal"] == REQUIRED_SIGNALS[0]


def test_unknown_signals_ignored() -> None:
    signals = _all_true() | {"unknown.signal": True}
    score = TrustScorer.score(signals)
    assert score.binary is True  # no key error
```

Path: `tests/unit/transforms/validation/test_trust_score_strict_and.py`

```python
from hypothesis import given, strategies as st

from codegenie.transforms.validation.trust_score import (
    REQUIRED_SIGNALS, TrustScorer,
)


@given(
    st.dictionaries(
        keys=st.sampled_from(REQUIRED_SIGNALS),
        values=st.booleans(),
        max_size=len(REQUIRED_SIGNALS),
    )
)
def test_strict_and_property(signals: dict[str, bool]) -> None:
    expected = all(signals.get(s, False) for s in REQUIRED_SIGNALS)
    score = TrustScorer.score(signals)
    assert score.binary == expected
```

Path: `tests/unit/transforms/validation/test_gate.py`

```python
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from codegenie.transforms.contract import TransformOutput, ValidatorOutput
from codegenie.transforms.validation.gate import validate
from codegenie.transforms.validation.lockfile_policy import LockfileScanResult


def _scan_clean() -> LockfileScanResult:
    return LockfileScanResult(
        violations=[], allowed_violations=frozenset(),
        lockfile_size_bytes=1024, schema_version="v1",
    )


def _to(tmp: Path) -> TransformOutput:
    return TransformOutput(
        name="npm_package_upgrade", diff_path=tmp / "p.patch",
        branch_name="codegenie/vuln-fix/CVE-2024-0001-abc1234",
        files_changed=[], confidence="high",
        worktree_root=tmp, run_id="run-1",
        upstream_signals={
            "lockfile.parse_ok": True,
            "recipe.engine.exit_status_zero": True,
            "cve.delta.direction_non_increasing": True,
            "patch.git_apply_dryrun_ok": True,
        },
    )


def test_install_failure_short_circuits(tmp_path: Path) -> None:
    with patch("codegenie.transforms.validation.gate.install_validator") as iv, \
         patch("codegenie.transforms.validation.gate.test_validator") as tv, \
         patch("codegenie.transforms.validation.gate.build_validator") as bv:
        iv.return_value = ValidatorOutput(
            name="install", passed=False, stdout_path=tmp_path/"a",
            stderr_path=tmp_path/"b", duration_ms=10, confidence="low",
            signals={"npm.install.exit_status": 1},
        )
        out = validate(_to(tmp_path), allow_test_network=False,
                       lockfile_scan_result=_scan_clean())
    assert out.green is False
    assert out.signal_escalate is False
    tv.assert_not_called()
    bv.assert_not_called()


def test_test_failure_with_network_sets_signal_escalate(tmp_path: Path) -> None:
    with patch("codegenie.transforms.validation.gate.install_validator") as iv, \
         patch("codegenie.transforms.validation.gate.test_validator") as tv, \
         patch("codegenie.transforms.validation.gate.build_validator"):
        iv.return_value = ValidatorOutput(
            name="install", passed=True, stdout_path=tmp_path/"a",
            stderr_path=tmp_path/"b", duration_ms=10, confidence="high",
            signals={"npm.install.exit_status": 0,
                     "npm.install.disallowed_egress_bytes": 0},
        )
        tv.return_value = ValidatorOutput(
            name="test", passed=False, requires_network=True,
            stdout_path=tmp_path/"c", stderr_path=tmp_path/"d",
            duration_ms=20, confidence="medium",
            signals={"tests.exit_status": 1,
                     "tests.duration_vs_baseline_pct": 100.0,
                     "tests.requires_network": True,
                     "tests.signature_matched": "ENOTFOUND"},
        )
        out = validate(_to(tmp_path), allow_test_network=False,
                       lockfile_scan_result=_scan_clean())
    assert out.signal_escalate is True
    assert out.escalation_record is not None
    # JSON file written to disk
    esc_dir = tmp_path / ".codegenie/remediation/run-1/escalations"
    assert any(esc_dir.glob("*.json"))


def test_test_failure_without_network_no_escalate(tmp_path: Path) -> None:
    with patch("codegenie.transforms.validation.gate.install_validator") as iv, \
         patch("codegenie.transforms.validation.gate.test_validator") as tv, \
         patch("codegenie.transforms.validation.gate.build_validator"):
        iv.return_value = ValidatorOutput(
            name="install", passed=True, stdout_path=tmp_path/"a",
            stderr_path=tmp_path/"b", duration_ms=10, confidence="high",
            signals={"npm.install.exit_status": 0,
                     "npm.install.disallowed_egress_bytes": 0},
        )
        tv.return_value = ValidatorOutput(
            name="test", passed=False, requires_network=False,
            stdout_path=tmp_path/"c", stderr_path=tmp_path/"d",
            duration_ms=20, confidence="low",
            signals={"tests.exit_status": 1,
                     "tests.duration_vs_baseline_pct": 100.0,
                     "tests.requires_network": False},
        )
        out = validate(_to(tmp_path), allow_test_network=False,
                       lockfile_scan_result=_scan_clean())
    assert out.signal_escalate is False
    assert out.green is False


def test_all_green_high_confidence(tmp_path: Path) -> None:
    # ... validators all pass with happy signals + 150pct band
    # assert out.green is True, out.confidence == "high"
    ...
```

Run; confirm `ImportError`. Commit red marker.

### Green — smallest impl shape

- `TrustScorer.score` body is ~15 lines. The flipped-signal walk is a single `for s in REQUIRED_SIGNALS: if not signals.get(s, False): flipped = s; break`.
- `gate.validate` body is ~60 lines: linear orchestration, three function calls, signal composition, trust score, audit event emission for `gate.failed` only.
- Escalation JSON write: `path.write_text(EscalationRecord(...).model_dump_json(indent=2))`.

### Refactor — bounded

- Static signal mapping table: `_VALIDATOR_SIGNAL_MAP: Final[dict[str, tuple[str, Callable[[Any], bool]]]]` — maps each strict-AND signal name to (source-key, predicate). Single source of truth for the install-validator-output → trust-signal translation. Keeps the gate body readable.
- `_write_escalation(record, run_id, worktree_root) -> Path` helper isolates the path resolution so S7-06 (Phase-4 handoff contract) can read the schema in one place.
- `REQUIRED_SIGNALS` snapshot test (`tests/contract/test_trust_score_signals_snapshot.py`) pins the closed-nine vocabulary; any change to the tuple fails the snapshot and forces ADR amendment.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/validation/trust_score.py` | New — `TrustScorer`, `TrustScore`, `REQUIRED_SIGNALS` |
| `src/codegenie/transforms/validation/gate.py` | New — `validate`, `GateOutcome`, `EscalationRecord`, validator-signal mapping |
| `tests/unit/transforms/validation/test_trust_score.py` | New — 5 tier-derivation cases |
| `tests/unit/transforms/validation/test_trust_score_strict_and.py` | New — Hypothesis property test |
| `tests/unit/transforms/validation/test_gate.py` | New — 4 orchestration cases (incl. on-disk JSON write) |
| `tests/unit/transforms/validation/test_escalation_record.py` | New — JSON shape + extra-field rejection |
| `tests/contract/test_trust_score_signals_snapshot.py` | New — `REQUIRED_SIGNALS` snapshot pin |

## Out of scope

- **Exit-code mapping (0/6/8) at the CLI layer** — S5-05.
- **`remediation-report.yaml#escalations[]` section serialization** — S5-04 (`PatchBranchWriter`) reads `GateOutcome.escalation_record` and writes it to the report.
- **CLI stderr banner on exit 8** — S5-05.
- **`upstream_signals` field population on `TransformOutput`** — S5-01 (`NpmPackageUpgradeTransform`) populates it from upstream stages (recipe engine, CVE-delta probe, git-apply-dry-run).
- **Phase 5 retry-on-signal-escalate** — explicit deferral; this story only signals.
- **LangGraph `interrupt()` routing of `signal_escalate`** — Phase 5 wiring.
- **Calibration of the `tests.duration_vs_baseline_within_150pct` threshold** — Phase 8.
- **Adding a tenth strict-AND signal (e.g., `npm.build.exit_status_zero`)** — explicit deferral; ADR-0013 amendment required.

## Notes for the implementer

- **Single emission discipline for `gate.signal_escalate`.** The audit chain (ADR-0010) closes the event vocabulary. `gate.signal_escalate` is emitted *by the test validator* (S4-03), not by `gate.py`. `gate.py` emits `gate.failed` with `failing_signal="requires_network"` for the parallel gate-side audit channel. If you re-emit `gate.signal_escalate` from gate.py, the audit chain has duplicate events for the same operator decision — Phase 4 RAG retrieval will double-count. Split: validator signals, gate decides.
- **Strict-AND is conservative by construction.** A flaky test fails the gate. A real bump-breaks-the-suite also fails the gate. The audit log records `flipped_signal` so Phase 4 (RAG) and Phase 8 (calibration) can read which signal flipped. Do NOT soften the strict-AND with weighted scoring or median voting — that defeats ADR-0013's posture verbatim. Phase 8 introduces calibration; not now.
- **The `medium` tier exists for exactly two reasons:** (1) `signal_escalate` from the test validator (the `requires_network=true` path bypasses strict-AND and sets `medium` directly); (2) the all-true-but-tests-slow-150-to-200pct band. Both are explicit in ADR-0013. Do not introduce a third `medium` case.
- **The `REQUIRED_SIGNALS` tuple is closed at v0.3.0.** Adding a signal (e.g., `npm.build.exit_status_zero`) requires: ADR-0013 amendment + this tuple's update + snapshot test update + cross-coordinator update (S5-01 populates the signal at the source) — all in the same PR. The cross-cutting "snapshot-frozen ABC contracts" discipline applies by analogy; the contract test `tests/contract/test_trust_score_signals_snapshot.py` is the merge gate.
- **`flipped_signal` walks `REQUIRED_SIGNALS` in declaration order.** This is a stable property — Phase 4 RAG can rely on the *first* false signal as the canonical diagnostic. If you sort the tuple alphabetically later, every Phase 4 retrieval query becomes incoherent. Declaration order is the contract; document it in the module docstring.
- **The escalation JSON timestamp is UTC, filename-safe.** Use `datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")` — no colons, no microseconds. Multiple escalations in the same second are unlikely but possible (e.g., test-runner re-entry); if you need uniqueness, append a 4-char random suffix; do not silently overwrite.
- **`extra="forbid"` on every Pydantic model in this story.** Cross-cutting "schema discipline" — `TrustScore`, `GateOutcome`, `EscalationRecord` all reject extra fields. The schema-version pin (`schema_version: Literal["v1"]`) is the merge-gate for any v2 migration.
- **No LLM anywhere in this module.** Cross-cutting fence (S1-09 + S7-07) forbids LLM imports under `transforms/`. The `TrustScorer` is deterministic Python; the `gate.py` orchestrator is deterministic Python. If your IDE auto-completes `import anthropic` because of a nearby model, delete it manually — the fence CI gate will catch it post-merge, but you want to catch it pre-merge.
- **The signal-mapping table is the load-bearing translation layer.** `ValidatorOutput.signals` keys are validator-vocabulary (`"npm.install.exit_status"`); `REQUIRED_SIGNALS` keys are scorer-vocabulary (`"npm.install.exit_status_zero"`). The translation is `signals["npm.install.exit_status_zero"] = (vo.signals["npm.install.exit_status"] == 0)`. Define this once, in a static dict at module top. If the vocabularies drift, the dict is the canonical reconciliation point.
- **`upstream_signals` is the seam to S5-01.** Five of the nine signals come from upstream stages (lockfile parsing, recipe engine, CVE-delta, git-apply-dry-run). S5-01 (`NpmPackageUpgradeTransform`) populates `TransformOutput.upstream_signals` as the gate reads it back. Cross-check the `TransformOutput` Pydantic surface — if the field doesn't exist yet (it should from S1-02), surface the contract mismatch in your story PR (Rule 11). The field is named in `phase-arch-design.md §"Component design" #4 NpmPackageUpgradeTransform`.
