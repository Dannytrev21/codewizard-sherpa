# Story S7-06 — Phase-4 handoff contract test: `test_phase4_handoff_contract.py`

**Step:** Step 7 — Harden — ≥ 30 adversarial fixtures, determinism canary, perf canaries, Phase-2 regression hard-gate, Phase-4 handoff verification, CI gates
**Status:** Ready
**Effort:** M
**Depends on:** S5-05 (`remediate` CLI end-to-end — the test consumes the fully-wired `codegenie remediate` output: `remediation-report.yaml`, `RecipeSelection` exposed via the report, `TransformOutput.errors`, `ValidatorOutput.errors`); transitively S1-04 (Pydantic boundary models — the test reconstructs the consumer's view of `RecipeSelection`, `TransformOutput`, etc., without importing the Phase-3 implementations)
**ADRs honored:** ADR-0001 (closed `Transform` / `RecipeEngine` ABCs — Phase 4 inherits without editing; the handoff test pins what Phase 4 can read), ADR-0004 (`RecipeSelection` is a structured `(recipe, reason, diagnostics)` triple with closed `reason` enum — Phase 4 routes on `reason`), ADR-0013 (`TrustScore` strict-AND signal set — Phase 4 reads the binary trust signal + the per-signal detail), ADR-0010 (audit chain extension — Phase 4 consumes Phase-3 audit events without parsing private internals)

## Context

Phase 4 (LLM-fallback planning) reads Phase 3's deterministic outputs to decide whether to invoke RAG / LLM. The contract is *not* the Phase-3 source code — Phase 4 imports nothing from `src/codegenie/transforms/` or `src/codegenie/recipes/`. The contract is the on-disk artifacts (`remediation-report.yaml`, audit chain JSONL) plus the closed-enum public surfaces exposed in the Pydantic boundary models (`RecipeSelection.reason`, `TransformOutput.errors`, `ValidatorOutput.errors`, `TrustScore.binary` + `confidence` + `detail`, `RemediationReport`).

This story plants the **handoff contract snapshot test**: a single integration test that simulates a Phase-4-shaped consumer reading the Phase-3 outputs *without* importing any Phase 3 internals. The test reconstructs the consumer's view by parsing `remediation-report.yaml` as a plain dict (or via a *re-declared* Pydantic shape), reading the audit chain JSONL line-by-line, and asserting that every load-bearing handoff surface is present and shaped as the contract expects. If a future Phase-3 refactor silently widens or narrows the surface, this test red-fails — and the right response is to amend the relevant ADR (ADR-0001/0004/0010/0013) **plus** update this test in the same PR.

The test is **the load-bearing forward-looking gate** for Phase 3; S7-05 is the backward-looking gate (Phase 2 regression). The two gates together fully bracket Phase 3's adjacency to the prior + next phase per `stories/README.md`.

The test does **not** invoke any Phase-4 LLM or retrieval — Phase 4 has not been built yet. The test invokes `codegenie remediate` end-to-end on a known fixture, then verifies the *consumable surface* of the resulting artifacts. The simulated consumer is a small inline class that parses the report YAML and audit JSONL and asserts the expected fields are present + typed correctly. The closed `reason` enum (six values: `matched`, `no_engine`, `range_break`, `peer_dep_conflict`, `unsupported_dialect`, `catalog_miss`) is the key field — Phase 4's routing logic switches on it; any drift breaks Phase 4's design.

A second test variant covers the *failure-path* handoff: a `gate.signal_escalate` exit-8 case where Phase 4 must read the on-disk escalation JSON (`<run-dir>/escalation.json`) plus the `remediation-report.yaml#escalations[]` section plus the audit chain's `gate.signal_escalate` event. All three surfaces must align (same `signature_matched`, same `suggested_flag`) — drift between them is the failure mode this test catches.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Testing strategy" §"Integration tests"` — `test_phase4_handoff_contract.py` referenced.
  - `../phase-arch-design.md §"Roadmap coherence check" §"Phase-4 handoff"` — what Phase 4 consumes; the closed-surface commitment.
  - `../phase-arch-design.md §"Component design" #2 RecipeEngine + selector"` — `RecipeSelection` closed enum.
- **Phase ADRs:**
  - `../ADRs/0001-transform-recipe-engine-two-abc-contract.md` — frozen at v0.3.0; Phase 4 inherits without editing.
  - `../ADRs/0004-recipe-selection-structured-triple-not-optional.md` — `RecipeSelection` triple shape + closed `reason` enum.
  - `../ADRs/0010-audit-chain-extension-cache-replay-event.md` — audit event vocabulary Phase 4 consumes.
  - `../ADRs/0013-confidence-strict-and-of-binary-signals-no-llm.md` — `TrustScore` shape Phase 4 reads.
- **Production ADRs:**
  - `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — contract-preservation discipline this test enforces at the Phase 3 → Phase 4 boundary.
- **Source design:**
  - `../final-design.md §"What's next — handoff to Phase 4"` — the list of artifacts + contracts.
  - `../High-level-impl.md §"What's next — handoff to Phase 4"` — the consumer-side semantics + the four-edge `RecipeSelection.reason` routing.
- **Existing code:**
  - `src/codegenie/transforms/branch_writer.py` (S5-04) — writes `remediation-report.yaml`.
  - `src/codegenie/cli.py` (S5-05) — the entry point this test invokes.
  - `tests/fixtures/repos_bundles/` (S7-01) — the fixtures this test consumes (the express bundle for happy-path; the test-network bundle for escalation).

## Goal

Land `tests/integration/test_phase4_handoff_contract.py` that simulates a Phase-4-shaped consumer reading Phase-3 outputs without importing any Phase 3 internals, verifies all load-bearing handoff surfaces — `RecipeSelection.reason` closed-enum, `TransformOutput.errors`, `ValidatorOutput.errors`, `TrustScore` shape, `RemediationReport` schema, audit chain event vocabulary, `escalation.json` surface — are present and aligned with the documented contract, and red-fails on any drift in the public surface.

## Acceptance criteria

- [ ] `tests/integration/test_phase4_handoff_contract.py` exists and is green on `main` after S5-05 lands.
- [ ] The test does **not** import any symbol from `codegenie.transforms.*` or `codegenie.recipes.*` (these are the packages Phase 4 is forbidden from importing per ADR-0001). It may import:
  - `codegenie.cli` (to invoke `remediate` end-to-end via `CliRunner`) — this is allowed because Phase 4's own CLI integration is expected to invoke `codegenie remediate` as a subprocess, not in-process.
  - Stdlib-only for parsing artifacts (`yaml`, `json`).
  - Phase-4-mirror Pydantic shapes the test redeclares inline (a small `class _Phase4ViewOfRecipeSelection(BaseModel): reason: Literal["matched","no_engine","range_break","peer_dep_conflict","unsupported_dialect","catalog_miss"]; ...`) — these declarations are the *consumer-side* contract, not the producer-side, and red-fail if Phase 3 narrows / widens.
- [ ] **Happy-path test.** Invokes `codegenie remediate <express-fixture> --cve <known-CVE>` end-to-end; exit 0. Then:
  - Parses `remediation-report.yaml` as plain YAML; reconstructs Phase 4's view via the inline `_Phase4ViewOfRemediationReport` Pydantic; asserts every required field is present + typed.
  - Reads `audit/<run-id>.jsonl` line-by-line; asserts every event has `event_type` in the closed Phase-3 set (named in ADR-0010); `payload` matches the per-event Pydantic schema (the test redeclares the closed-enum vocabulary).
  - Asserts `RecipeSelection.reason == "matched"` for the happy path; asserts `recipe.id`, `engine_name`, and `diagnostics` are populated.
  - Asserts `TrustScore.binary == True`, `TrustScore.confidence in {"high","medium"}`, `TrustScore.detail` is a `dict[str, bool]` with exactly the nine objective signals named in ADR-0013.
- [ ] **`reason` closed-enum drift test.** A parametrized test runs through the six valid `RecipeSelection.reason` values and synthesizes (via fixture variants) a `remediation-report.yaml` that emits each value. The parametrized run-through verifies all six can be produced + parsed by the consumer-side Pydantic; a seventh value (`"unexpected_future_reason"`) injected synthetically into a report YAML must cause the consumer-side Pydantic to **fail validation** (proving Phase 4 would catch unauthorized widening at parse time).
- [ ] **Escalation-path test.** Invokes `codegenie remediate <test-requires-network-fixture> --cve <known-CVE>`; exit 8. Then:
  - Asserts `escalation.json` is on disk at `<run-dir>/escalation.json`; parses as JSON; reconstructs Phase 4's view via inline `_Phase4ViewOfEscalation`; asserts `signature_matched`, `suggested_flag: "--allow-test-network"`, `validator_name`, `timestamp` are present.
  - Asserts `remediation-report.yaml#escalations[]` section exists + each entry aligns with `escalation.json` (same `signature_matched`, same `suggested_flag`).
  - Asserts the audit chain has at least one `gate.signal_escalate` event whose payload aligns with `escalation.json`.
- [ ] **`TransformOutput.errors` + `ValidatorOutput.errors` shape.** A parametrized test produces representative error strings (e.g., from the exit-5 / exit-6 fixtures): each error is `Literal[<known-closed-set>]` or matches a documented regex; if a future Phase-3 refactor adds a free-form error message, the consumer-side Pydantic's `Literal` for closed errors red-fails — surfacing the unauthorized widening.
- [ ] **`RemediationReport` schema_version.** Asserts the report YAML's top-level `schema_version` field is `"v1"` (per cross-cutting "schema_version: v1 discipline"); any drift requires an ADR amendment + this test's update.
- [ ] **Audit event vocabulary closed.** A scan of the audit JSONL events compares the set of seen `event_type` values against the closed Phase-3 set named in ADR-0010 (the 18 events); any unknown event red-fails. The closed set is redeclared in the test, not imported from `audit/events.py`, so a sliently-added new event in `events.py` does **not** get a free pass through this gate.
- [ ] **Failure mode of the test is informative.** On red-fail, the test message names (a) what surface drifted (e.g., "`RecipeSelection.reason` widened with new value `'foo'`"), (b) the ADR that pins the surface (e.g., "ADR-0004 §Decision"), (c) the suggested resolution ("amend ADR-0004 + update this test in the same PR").
- [ ] The test is registered under `pytest.mark.phase4_handoff` (or whatever S7-07 wires); CI gate blocks merge on red.
- [ ] The test runs in **≤ 60 s** on the CI runner (happy-path + escalation-path together).
- [ ] A docstring at the top explains the gate's purpose, the four-edge `RecipeSelection.reason` routing Phase 4 implements (per High-level-impl §"What's next"), and the legitimate amendment procedure (ADR amendment + this test's update in the same PR).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict tests/integration/test_phase4_handoff_contract.py` pass.

## Implementation outline

1. **Declare the consumer-side Pydantic mirrors** inline in the test file. These are **intentional duplicates** of the producer-side models in `recipes/models.py` + `transforms/contract.py`. The duplication is the load-bearing piece — it pins what the consumer reads, decoupled from the producer's implementation.
   ```text
   class _Phase4ViewOfRecipeSelection(BaseModel):
       model_config = {"extra": "forbid"}
       recipe: dict | None  # opaque; Phase 4 doesn't parse the Recipe shape
       reason: Literal["matched","no_engine","range_break","peer_dep_conflict","unsupported_dialect","catalog_miss"]
       diagnostics: dict[str, Any]
   ```
   Similar shapes for `_Phase4ViewOfTransformOutput`, `_Phase4ViewOfValidatorOutput`, `_Phase4ViewOfTrustScore`, `_Phase4ViewOfRemediationReport`, `_Phase4ViewOfEscalation`.
2. **Declare the closed audit-event vocabulary** as a module-level frozenset, inline:
   ```text
   PHASE3_AUDIT_EVENT_TYPES: frozenset[str] = frozenset({
     "cve.feed.synced", "cve.feed.signature_check", "cve.retraction.detected",
     "recipe.selected", "recipe.engine.invoked", "transform.applied",
     "lockfile.scanned", "lockfile.policy_violation",
     "npm.install.run", "tests.executed", "gate.failed", "gate.signal_escalate",
     "evidence_stale.marked", "branch.created", "branch.refused_dirty_tree",
     "branch.refused_exists", "cache.replay", "meta.unexpected_exception",
   })
   ```
   (18 events per ADR-0010 + cross-cutting concerns).
3. **Happy-path test.** Use `CliRunner` to invoke `remediate` against the express fixture; assert exit 0; parse + validate via the consumer Pydantic; assert every field.
4. **Closed-enum drift test.** For each of the six `reason` values, either invoke a fixture that produces it or synthesize a `remediation-report.yaml` with the value (preferring real invocation when a fixture exists; falling back to synthesis for the rarer values).
5. **Synthesized-widening test.** Write a tmp `remediation-report.yaml` with `reason: "unexpected_future_reason"`; assert the consumer Pydantic raises `ValidationError`.
6. **Escalation-path test.** Use the test-requires-network fixture from S7-01; invoke `remediate`; assert exit 8; verify the three-surface alignment (`escalation.json` + report + audit event).
7. **Audit-vocabulary scan.** Read the audit JSONL; collect all `event_type` values; assert the set is a subset of `PHASE3_AUDIT_EVENT_TYPES`.
8. **Informative failure message.** Wrap each assertion in a `try/except` that re-raises with a message naming the ADR.

## TDD plan — red / green / refactor

### Red

Path: `tests/integration/test_phase4_handoff_contract.py`

```python
"""ADR-0001 + ADR-0004 + ADR-0010 + ADR-0013 | Invariant: Phase 4 consumes Phase 3's on-disk artifacts
without importing any Phase 3 internals. Any drift in the public surface red-fails this gate.

The four-edge RecipeSelection.reason routing Phase 4 implements:
- 'matched' → no LLM, Phase 3 path proceeds.
- 'catalog_miss' → RAG.
- 'range_break' / 'peer_dep_conflict' / 'unsupported_dialect' → RAG + LLM with diagnostics.
- 'no_engine' → exit cleanly (LLM cannot install Java).

Amendment procedure: amend the relevant ADR (0001/0004/0010/0013) AND update this test's
inline consumer-side Pydantic in the same PR. Without both, this gate red-fails."""
import pytest
from click.testing import CliRunner
from pydantic import BaseModel, ValidationError
from typing import Any, Literal

PHASE3_AUDIT_EVENT_TYPES: frozenset[str] = frozenset({...})

# Inline consumer-side Pydantic mirrors here (no imports from codegenie.transforms / .recipes)

@pytest.mark.phase4_handoff
def test_happy_path_handoff_surface(tmp_express_repo, audit_chain_validator) -> None:
    ...

@pytest.mark.phase4_handoff
def test_recipe_selection_reason_closed_enum_accepts_six_values() -> None:
    # Parametrize over the six valid values; each parses cleanly.
    ...

@pytest.mark.phase4_handoff
def test_recipe_selection_reason_rejects_unknown_widening(tmp_path) -> None:
    # Synthesize a report with reason="unexpected_future_reason"; assert ValidationError.
    ...

@pytest.mark.phase4_handoff
def test_escalation_path_handoff_three_surface_alignment(tmp_test_needs_network_repo) -> None:
    # Exit 8 → escalation.json + report#escalations + audit event align.
    ...

@pytest.mark.phase4_handoff
def test_audit_event_vocabulary_is_closed(tmp_express_repo) -> None:
    # Every event_type emitted is in PHASE3_AUDIT_EVENT_TYPES.
    ...
```

Run; commit red.

### Green

- Implement the consumer-side Pydantic mirrors carefully — they must match the producer-side fields the contract pins. Cross-reference against the producer files (read-only, do not import) and confirm every field name + type.
- Run each test; iterate until green.

### Refactor

- **Consumer-side Pydantic mirrors are the contract surface.** Do not import them from `codegenie.*`; that defeats the test. Re-declaring is the load-bearing duplication.
- **The closed audit-event vocabulary is duplicated** from ADR-0010 + cross-cutting concerns. Pin via this test; any drift in `audit/events.py` that adds an event without updating this test red-fails.
- **Failure messages are user-facing**: a future operator reading the test red-fail should immediately see "ADR-0004 §Decision pinned six values; you added a seventh; amend the ADR + update this test."
- **Confirm wall-clock budget** — both happy-path + escalation-path complete in ≤ 60 s.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_phase4_handoff_contract.py` | New — the load-bearing forward-looking gate. |
| `pyproject.toml` (extend) | Register `phase4_handoff` pytest marker. |
| `docs/phases/03-vuln-deterministic-recipe/runbook.md` (S7-07 owns; one cross-reference here) | Note the amendment procedure (ADR + test in same PR). |

## Out of scope

- **Building Phase 4** — Phase 4 has not been designed yet. This story plants the contract surface Phase 4 will eventually consume.
- **Testing Phase 4's LLM-fallback logic** — there is no LLM in Phase 3; the test is purely contract-shape verification.
- **Audit chain BLAKE3 integrity verification** — Phase 2 ADR-0012's chain validator is the right tool; this test consumes its output (presence of audit events) but does not re-run chain integrity. S7-02's adversarial corpus pins chain integrity directly.
- **Performance budgets for Phase 4's consumer-side reads** — Phase 4 owns its own perf gates.
- **`RemediationReport.schema_version` migration to v1.1** — additive minor bumps are out of scope; this test pins v1.
- **Replacing the consumer-side Pydantic mirrors with a generated client** — out of scope. The mirrors are deliberately hand-coded so they are the readable contract.

## Notes for the implementer

- **The duplication is the discipline.** A reviewer who suggests "import the Pydantic from `codegenie.recipes.models` to avoid duplication" is breaking the contract. The whole point of this test is that Phase 4 reads the *artifact surface*, not the *implementation surface*. The duplication is the load-bearing decoupling.
- **The closed-enum widening test is the most subtle.** Construct a synthetic `remediation-report.yaml` with `reason: "unexpected_future_reason"` (write it to a tmp file directly, do not invoke the CLI). The consumer-side Pydantic should `raise ValidationError` because its `Literal[...]` does not include the value. If the test passes when it should fail, the consumer-side `Literal` is wrong — narrow it.
- **The audit-vocabulary scan reads the JSONL line-by-line.** Use `pathlib.Path.read_text().splitlines()` and `json.loads(line)` per line. Skip the trailing newline gracefully. Phase 2's audit-chain validator may already provide a `parse_chain(path) -> list[AuditEvent]` helper; do NOT use it — that imports `audit/events.py` and re-introduces the coupling this test forbids.
- **`pytest.mark.phase4_handoff`** must be registered in `pyproject.toml`'s markers list, else pytest emits a warning that breaks the strict-warning mode Phase 0 may have enabled. Register it.
- **The escalation-path test depends on a `test_requires_network` fixture** — verify S7-01 produced one. If not, surface a follow-up; do not synthesize a fake escalation JSON here (the integration test must invoke the real `remediate` path).
- **`CliRunner` invocation** — pass `mix_stderr=False` to assert stderr independently. Capture both for the failure-message assertion (e.g., "exit 8 surfaced the escalation banner").
- **`mypy --strict`** on the test file — the inline Pydantic mirrors are straightforward; the trickiest part is the `dict[str, Any]` for `diagnostics`. Use `dict[str, object]` if `--strict` complains about `Any`.
- **The four-edge routing in the docstring** is operator-facing — a future Phase-4 implementer reading this test should immediately understand what Phase 4 does with each `reason` value. The High-level-impl §"What's next" is the source of truth; keep the docstring in sync.
- **The 60-second budget** is loose for the happy-path (the express fixture's `npm install` + `npm test` is the long pole — ~15-20 s). If the budget pressures, parallelize via `pytest-xdist` (the test is hermetic per `tmp_path`).
- **Phase-4 amendment procedure.** If Phase 4 genuinely needs a *seventh* `reason` value (or any new field), the procedure is: (a) amend ADR-0004 (or the relevant ADR), (b) update the consumer-side Pydantic in this test, (c) update the producer-side Pydantic in `recipes/models.py`, (d) all in one PR. Without all four, this gate red-fails.
- **Regression risk: medium.** The biggest risk is the test silently passing when it shouldn't — e.g., if a typo in the consumer-side `Literal` accepts everything by accident (`Literal[str]` vs `Literal["matched", ...]`). Pin the test with the synthesized-widening case; if that test passes when it should fail, the consumer-side mirror is broken.
