# Story S2-03 — `LlmInvocationGuard` three layers + rates config

**Step:** Step 2 — Ship the deterministic LLM-side primitives — `OutputValidator`, `PromptLoader` + YAML prompts, `LlmInvocationGuard`, `ApiKeyStore`
**Status:** Ready
**Effort:** M
**Depends on:** S1-02, S2-02
**ADRs honored:** ADR-P4-010

## Context

Phase 4 is the first phase that spends money. The cost-cap primitive's shape determines how Phase 13's Budget Enforcer middleware swaps in. Per ADR-P4-010, the guard exposes one method (`check_budget(request, *, running_total_usd)`) and runs three defense-in-depth layers — L1 preflight estimate (refuses before the call), L2 `max_tokens` (Anthropic-side, can never exceed), L3 128 KB egress byte cap (Linux jailed only via `EgressProxy`, full path lands in S3-04). Only L1 + L2 are fully wired in this story; L3 is an interface stub the EgressProxy will satisfy. The `--allow-cost-overrun` flag is already CLI-wired by S1-06; this story plumbs it through to the guard with the audit event.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #9 "LlmInvocationGuard"` — three layers, public interface, the `chars/4 × $/token + max_tokens × $/output_token` estimator, the rates.yaml location.
  - `../phase-arch-design.md §"Edge cases"` row 9 — three-layer breach scenarios.
  - `../phase-arch-design.md §"Path to production end state"` — cost-ledger JSONL shape Phase 13 consumes.
- **Phase ADRs:**
  - `../ADRs/0010-llm-invocation-guard-running-total-with-override.md` — ADR-P4-010 — per-invocation + per-workflow running-total in one API; `--allow-cost-overrun=<usd>` with loud audit event; three-layer enforcement; estimation is conservative-high.
- **Production ADRs:**
  - `../../../production/adrs/0024-cost-observability-end-to-end.md` — production ADR-0024 — cost-ledger JSONL aggregation key `(workflow_id, stage, node, model)`.
  - `../../../production/adrs/0025-per-workflow-cost-cap.md` — production ADR-0025 — $0.50 per-workflow default; Phase 4 ships this default and the kwarg shape Phase 13's middleware reuses verbatim.
  - `../../../production/adrs/0027-cost-attribution-model.md` — production ADR-0027 — three-tier attribution model Phase 13's Budget Enforcer replaces `LlmInvocationGuard.check_budget` with; the kwarg signature is preserved.
- **Source design:** `../final-design.md §"Components" #6 "LlmInvocationGuard + CostEmitter"`; `../final-design.md §"Departures from all three inputs" #5` — running-total Guard.
- **Existing code:**
  - `src/codegenie/llm/contract.py` (from S1-02) — `LlmRequest` (with `max_tokens`, the input blocks the L1 estimator measures).
  - `src/codegenie/errors.py` (from S1-01) — `CostCeilingBreached`.
  - `src/codegenie/cli.py` (from S1-06) — `--max-llm-cost-usd` and `--allow-cost-overrun` flags parse; defaults / semantics deferred to Step 6 but the guard accepts the kwargs now.

## Goal

Land `src/codegenie/llm/guard.py` exposing `LlmInvocationGuard(rates_path, default_ceiling_usd=Decimal("0.50"))` with `check_budget(request, *, running_total_usd) -> None` (raises `CostCeilingBreached`) and the L3 byte-cap interface; ship `src/codegenie/llm/configs/rates.sample.yaml` documenting `input_rate_per_1m_tokens` / `output_rate_per_1m_tokens` / `cache_creation_rate_per_1m_tokens` / `cache_read_rate_per_1m_tokens` for Sonnet 4.7; honor `--allow-cost-overrun` as a kwarg that raises the per-invocation ceiling and emits `budget.overrun.allowed` audit event.

## Acceptance criteria

- [ ] `src/codegenie/llm/guard.py` exports `LlmInvocationGuard` with constructor `(rates_path: Path, default_ceiling_usd: Decimal = Decimal("0.50"), per_invocation_ceiling_usd: Decimal = Decimal("5.00"))` per ADR-P4-010 §Decision (defaults `$0.50` per-workflow, `$5.00` per-invocation).
- [ ] On construction, `rates.yaml` is parsed once into a `RateTable` (`input_rate_per_1m_tokens`, `output_rate_per_1m_tokens`, `cache_creation_rate_per_1m_tokens`, `cache_read_rate_per_1m_tokens`, all `Decimal`); missing file or malformed YAML raises `PromptTemplateInvalid`-style typed error (re-use or add `RatesFileMalformed` if needed — name in errors.py if added).
- [ ] `check_budget(request, *, running_total_usd, allow_cost_overrun_usd=Decimal("0"))` runs L1: `est_input_tokens = (input_chars / 4)`, `est = est_input_tokens * input_rate + request.max_tokens * output_rate`. Both rates divided by `1_000_000`. Inputs computed across `system_blocks + few_shots_block + query_block` total `len(text)`. Raises `CostCeilingBreached(estimate=est, remaining=remaining)` when `est > remaining`, where `remaining = max(per_invocation_ceiling_usd + allow_cost_overrun_usd, default_ceiling_usd - running_total_usd)`.
- [ ] When `allow_cost_overrun_usd > 0` is supplied, the guard emits `BUDGET_OVERRUN_ALLOWED` audit event (constant from S1-01) once per `check_budget` call carrying `(workflow_id, requested_overrun_usd, estimate_usd, model)` structured fields — even if the call would have passed without the override (the loudness is the point per ADR-P4-010 §Tradeoffs).
- [ ] L2 enforcement is verified by asserting `request.max_tokens` is honored on the produced request; the guard does not mutate `max_tokens`, only refuses preflight if it pushes the estimate above ceiling. A test confirms `request.max_tokens > 100_000` against a $0.50 budget rejects.
- [ ] L3 interface: `guard.egress_byte_cap_bytes -> int` returns `128 * 1024`; this constant is read by `EgressProxy` in S3-04. The guard itself does not enforce L3 (Linux jailed only via EgressProxy).
- [ ] `src/codegenie/llm/configs/rates.sample.yaml` ships with documented Sonnet 4.7 placeholder rates (commented in the file: "fill in from Anthropic console; values here are samples, not the live rate card") plus a `model_pin: claude-sonnet-4-7@vuln_remediation` field for cross-check against ADR-P4-007.
- [ ] `tests/unit/llm/test_llm_invocation_guard_three_layers.py` covers L1 (preflight raises when `est > remaining`), L2 (`max_tokens` honored — request unmodified), L3 (`egress_byte_cap_bytes == 131072`).
- [ ] `tests/unit/llm/test_guard_running_total_per_workflow.py` covers running-total accumulation: three sequential `check_budget` calls with `running_total_usd = 0.10, 0.30, 0.45`, the fourth at `0.49` rejects because `0.49 + est > 0.50`. The test demonstrates the integration shape Phase 13's middleware reuses.
- [ ] `tests/unit/llm/test_guard_allow_cost_overrun_audit.py` asserts `BUDGET_OVERRUN_ALLOWED` event is emitted on any `check_budget` call with `allow_cost_overrun_usd > 0` and that the event carries the requested-overrun and estimate fields.
- [ ] `tests/unit/llm/test_guard_estimate_is_conservative_high.py` constructs a request with known char counts; assert `est >= 1.15 × naive_calculation` per ADR-P4-010 "~20% high" disaster-prevention framing (use a tolerance window: `0.95 × expected <= est <= 1.25 × expected`).
- [ ] TDD red test exists, committed on a tagged commit, and the green commit brings it green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write tests first (red) — `test_llm_invocation_guard_three_layers.py`, `test_guard_running_total_per_workflow.py`, `test_guard_allow_cost_overrun_audit.py`.
2. Implement `RateTable` as a `frozen=True, extra="forbid"` Pydantic model (or NamedTuple with `Decimal` fields).
3. Implement `LlmInvocationGuard.__init__` — read `rates_path`, parse with `yaml.safe_load`, build `RateTable`. Add `RatesFileMalformed` to `src/codegenie/errors.py` if not already present from S1-01 (verify against the S1-01 list).
4. Implement `check_budget(request, *, running_total_usd, allow_cost_overrun_usd=Decimal("0"))`:
   - Sum input chars across all blocks in `request.system_blocks + request.few_shots_block + request.query_block` via `sum(len(b.text) for b in ...)`.
   - `est_input_tokens = Decimal(chars) / 4` (use `Decimal` from start to avoid float drift on rate math).
   - `est = est_input_tokens * rate.input_rate_per_1m / 1_000_000 + Decimal(request.max_tokens) * rate.output_rate_per_1m / 1_000_000`.
   - `effective_ceiling = self.per_invocation_ceiling_usd + allow_cost_overrun_usd`.
   - `remaining_invocation = effective_ceiling`.
   - `remaining_workflow = self.default_ceiling_usd - running_total_usd`.
   - Raise `CostCeilingBreached` when `est > min(remaining_invocation, remaining_workflow)`.
   - Emit `BUDGET_OVERRUN_ALLOWED` when `allow_cost_overrun_usd > 0`, regardless of pass/fail outcome.
5. Implement `egress_byte_cap_bytes` as a `Final[int] = 128 * 1024` constant on the class.
6. Write `src/codegenie/llm/configs/rates.sample.yaml` with comments naming each field.
7. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest`.

## TDD plan — red / green / refactor

### Red

Test file path (representative): `tests/unit/llm/test_llm_invocation_guard_three_layers.py`

```python
# tests/unit/llm/test_llm_invocation_guard_three_layers.py
from decimal import Decimal
from pathlib import Path

import pytest
from codegenie.llm.guard import LlmInvocationGuard
from codegenie.llm.contract import LlmRequest, CachedBlock, PlainBlock
from codegenie.errors import CostCeilingBreached


@pytest.fixture
def rates_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "rates.yaml"
    p.write_text("""
model_pin: claude-sonnet-4-7@vuln_remediation
input_rate_per_1m_tokens: "3.00"
output_rate_per_1m_tokens: "15.00"
cache_creation_rate_per_1m_tokens: "3.75"
cache_read_rate_per_1m_tokens: "0.30"
""")
    return p


def _req(input_chars: int, max_tokens: int) -> LlmRequest:
    body = "x" * input_chars
    return LlmRequest(
        system_blocks=[CachedBlock(text=body)],
        few_shots_block=[],
        query_block=[PlainBlock(text="")],
        expected_canary="a" * 64,
        max_tokens=max_tokens,
        temperature=0.0,
    )


def test_L1_preflight_refuses_when_estimate_exceeds_workflow_remaining(rates_yaml):
    g = LlmInvocationGuard(rates_yaml)
    # ~200k input chars × $3/1M tokens / 4 chars-per-token = ~$0.15
    # + 8k output × $15/1M = ~$0.12 → ~$0.27. Running total $0.30 → only $0.20 left → reject.
    with pytest.raises(CostCeilingBreached):
        g.check_budget(_req(input_chars=200_000, max_tokens=8000),
                       running_total_usd=Decimal("0.30"))


def test_L1_preflight_passes_when_within_budget(rates_yaml):
    g = LlmInvocationGuard(rates_yaml)
    g.check_budget(_req(input_chars=10_000, max_tokens=1024),
                   running_total_usd=Decimal("0.00"))


def test_L2_max_tokens_not_mutated(rates_yaml):
    g = LlmInvocationGuard(rates_yaml)
    req = _req(input_chars=1000, max_tokens=2048)
    g.check_budget(req, running_total_usd=Decimal("0.00"))
    assert req.max_tokens == 2048


def test_L3_egress_byte_cap_is_128_kb(rates_yaml):
    g = LlmInvocationGuard(rates_yaml)
    assert g.egress_byte_cap_bytes == 128 * 1024
```

And the running-total accumulation test:

```python
# tests/unit/llm/test_guard_running_total_per_workflow.py
from decimal import Decimal

def test_running_total_accumulates_across_calls(guard, request_):
    guard.check_budget(request_, running_total_usd=Decimal("0.10"))
    guard.check_budget(request_, running_total_usd=Decimal("0.30"))
    guard.check_budget(request_, running_total_usd=Decimal("0.45"))
    with pytest.raises(CostCeilingBreached):
        guard.check_budget(request_, running_total_usd=Decimal("0.49"))
```

Run; all fail because `LlmInvocationGuard` does not exist. Commit as red.

### Green

Implement `LlmInvocationGuard` per the outline. Minimum behavior: read rates, run L1 with `Decimal`, raise `CostCeilingBreached` with structured `estimate` / `remaining` attrs, expose `egress_byte_cap_bytes`, emit the audit event on overrun.

### Refactor

- Add docstrings naming each layer and the production ADR it traces to.
- Add `mypy --strict` types on every helper; rates math uses `Decimal` throughout (never `float`).
- Add module-level `Final[Decimal]` constants for the `DEFAULT_WORKFLOW_CEILING = Decimal("0.50")` and `DEFAULT_INVOCATION_CEILING = Decimal("5.00")` so the defaults round-trip from a single source.
- Confirm `pytest -k guard` is green; confirm `mypy --strict src/codegenie/llm/guard.py` is green.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/llm/guard.py` | New — guard + RateTable |
| `src/codegenie/llm/configs/rates.sample.yaml` | New — Sonnet 4.7 sample rates with field docs |
| `tests/unit/llm/test_llm_invocation_guard_three_layers.py` | L1 / L2 / L3 coverage |
| `tests/unit/llm/test_guard_running_total_per_workflow.py` | Per-workflow accumulation (Phase 13 integration shape) |
| `tests/unit/llm/test_guard_allow_cost_overrun_audit.py` | `BUDGET_OVERRUN_ALLOWED` audit event on override |
| `tests/unit/llm/test_guard_estimate_is_conservative_high.py` | Estimator within ADR-P4-010 ~20% high target |
| `src/codegenie/errors.py` | Append `RatesFileMalformed` if not already present from S1-01 (verify first) |

## Out of scope

- **`CostEmitter` and `cost-ledger.jsonl` writes** — `CostEmitter` lands in **S3-02** (`InProcessLeafLlmAgent` writes the JSONL after each successful call); this story only exposes the precheck.
- **EgressProxy enforcement of the 128 KB cap** — lands in **S3-04** (Linux-only). This story exposes the constant the proxy reads.
- **`--allow-cost-overrun` CLI default semantics** — flag parsing already shipped in **S1-06**; this story accepts the value as a kwarg. The CLI → guard wiring (which call site passes the kwarg) lands in **S5-02** (`_invoke_llm` helper).
- **Per-task-class budget tiers** — production ADR-0027 three-tier attribution lands in Phase 13; this story preserves the kwarg signature but does not implement it.
- **Cache-hit-rate cost discount math** — `cache_creation_rate_per_1m_tokens` and `cache_read_rate_per_1m_tokens` ship in the rates file for forward-compat; the L1 estimator does not currently use them (cache hit estimation requires actual prior call telemetry — Phase 13 work).
- **`cost.llm.invoked` event emission** — lands in **S3-02** at the call site, not in the guard.

## Notes for the implementer

- Use `Decimal` everywhere for money. Importing `Decimal` once at module top and never touching `float` is the cheapest way to satisfy ADR-P4-010 §Consequences "schema must include `cache_creation_input_tokens` and `cache_read_input_tokens` for cache-hit-rate accounting".
- The L1 estimator is **deliberately conservative** (~20% high per ADR-P4-010). Tests should verify this band, not insist on exact agreement with a "true" calculation. Real overruns will be loud, not silent — that is the trade.
- Per ADR-P4-010 §Tradeoffs: emitting `BUDGET_OVERRUN_ALLOWED` *unconditionally* on `allow_cost_overrun_usd > 0` (not only on actual breach) is intentional. The audit-event-volume dashboard is the policing mechanism; silent overruns are the failure mode.
- `request.max_tokens` is the L2 layer — Anthropic enforces it on the request body. The guard's responsibility is to *not* mutate it and to fold it into L1. Do not try to clamp `max_tokens` here.
- `egress_byte_cap_bytes` is a `Final[int]` on the class, not a method. `EgressProxy` (S3-04) reads it as a constant. Document the cross-package consumer in the docstring.
- The kwarg signature `check_budget(request, *, running_total_usd, allow_cost_overrun_usd=Decimal("0"))` is the Phase 13 middleware integration shape. ADR-P4-010 §Reversibility calls this out — do not rename or reshape these kwargs without an ADR.
- If `RatesFileMalformed` is not in S1-01's exception list, add it in this story under a clearly-delimited `# Phase 4 — additive (S2-03)` block. Do not edit existing subclasses.
- Inside the guard, build the `BUDGET_OVERRUN_ALLOWED` audit event payload with the `WORKFLOW_ID`, `FIELD_MODEL` field constants from S1-01 logging.py. Field consistency is enforced by ruff plugins; do not reconstruct keys from message strings (rule from `phase-arch-design.md §"Harness engineering"`).
