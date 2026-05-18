# Story S9-04 — `BenchReplayable` events + Phase 6.5 backfill hook

**Step:** Step 9 — CI gates, import-linter contracts, performance baselines, bench backfill hook
**Status:** Ready
**Effort:** S
**Depends on:** S9-02, S9-03
**ADRs honored:** ADR-0005 (two-stream event log — `bench_replayable` is the eighth literal in `WorkflowSpanningEvent.event_type`; the spanning stream is the seed source for Phase 6.5's backfill, per ADR §Consequences "The spanning stream is the seed source for Phase 6.5's `BenchReplayable` events — `codegenie eval backfill` reads it directly"), ADR-0011 (honest framing — the runbook must say what evidence the operator can verify and what they cannot)

## Context

Goal G9 (`phase-arch-design.md §Goals`) commits Phase 3 to making Phase 6.5's backfill **mechanical**: "Every workflow emits `BenchReplayable` on the spanning event stream carrying input-snapshot fingerprint + `Transform.diff_bytes_sha256`. Phase 6.5's `codegenie eval backfill` lifts 10 cases mechanically." The mechanical part is load-bearing: if a human has to write LLM prompts to extract bench cases from Phase 3 runs, Phase 6.5 ships months late and the cases drift from the runs they came from.

The payload must carry exactly enough that Phase 6.5's `loader.py` (see `docs/phases/06.5-per-task-class-eval-harness/final-design.md §Architecture — loader.py: bench/{tc}/cases/ → tuple[BenchCase, ...]`) can synthesize a `BenchCase` without re-running anything:

- **Input-snapshot fingerprint** — the BLAKE3 hash over the repo snapshot Phase 3 saw (the exact `RepoSnapshot.sha256` Phase 2 computed). This is what `case.toml § input/input-pointer.toml` carries forward; it lets Phase 6.5 reconstruct the input by name without re-snapshotting.
- **`Transform.diff_bytes_sha256`** — the hash over the diff bytes the transform produced. This is the ground-truth diff Phase 6.5's rubric scores future system outputs against (`expected/` under `bench/vuln-remediation/cases/{case-id}/`).
- **The `RemediationOutcome`** — minimally the `kind` (`validated`, `not_applicable`, `requires_human_review`, `failed`) so Phase 6.5 can route the case (`validated` → positive case; `failed` → negative case for adversarial bench).
- **`workflow_id`** — already on every event; lets Phase 6.5 cross-reference back to the original spanning stream for provenance.
- **`cve_id` + `plugin_id` + `recipe_id`** — so the case knows which task class to register under.

S6-04 owns the emit site (the orchestrator's `run(...)` exits via a `finally` that calls `event_log.emit_spanning(WorkflowSpanningEvent(event_type="bench_replayable", ...))`). S6-01 owns the `WorkflowSpanningEvent` union including the `bench_replayable` literal. **This story does not re-implement those.** What this story owns is:

1. The exact `BenchReplayablePayload` Pydantic schema (frozen, `extra="forbid"`) the orchestrator's call site instantiates.
2. The Phase 6.5 backfill-hook integration test that consumes ≥ 10 `bench_replayable` events from the spanning stream and produces eval cases mechanically (without a human in the loop).
3. The 1-page operator runbook documenting how to run, where artifacts land, how to verify the BLAKE3 chain, and how to surface the evidence to operators.

The fence S9-02 ships is what locks the `bench_replayable` literal into the union; this story ensures the emit site is real and the payload is consumed.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals G9` — "Phase 6.5 backfill readiness. Every workflow emits `BenchReplayable` on the spanning event stream carrying input-snapshot fingerprint + `Transform.diff_bytes_sha256`. Phase 6.5's `codegenie eval backfill` lifts 10 cases mechanically."
  - `../phase-arch-design.md §Component design C9` — `WorkflowSpanningEvent.event_type` includes `bench_replayable`; the payload shape commitment ("each type has a typed payload schema").
  - `../phase-arch-design.md §Integration with Phase 04` + `§Path to production end state` — "`BenchReplayable` spanning events are the seed source for Phase 4's solved-example store" / "Phase 6.5 unblocked".
  - `../High-level-impl.md §Step 9` — verbatim Done criterion: "`pytest tests/integration/test_phase65_backfill_hook.py` produces ≥10 eval cases mechanically from the test event stream."
- **Phase ADRs:**
  - `../ADRs/0005-two-stream-event-log-per-adr-0034.md` §Consequences — "The spanning stream is the seed source for Phase 6.5's `BenchReplayable` events — `codegenie eval backfill` reads it directly." Also: BLAKE3 chain semantics + `fcntl.flock` cross-process safety.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — the runbook framing: name what the chain detects (local tamper) and what it does not (host compromise — Phase 16's Sigstore anchors).
- **Existing code:**
  - `src/codegenie/plugins/events.py` (S6-01) — `WorkflowSpanningEvent` definition; the `bench_replayable` literal lives here.
  - `src/codegenie/transforms/orchestrator.py` (S6-04) — `RemediationOrchestrator.run(...)`'s `finally` is the emit site.
  - `src/codegenie/cli.py` + Phase 0's `audit verify` — the BLAKE3-chain verifier extended in S6-05.
  - Phase 6.5 final design: `docs/phases/06.5-per-task-class-eval-harness/final-design.md §Architecture` — `loader.py`, `bench/{tc}/cases/`, `BenchCase` shape; `bench/vuln-remediation/cases/` is the destination for the backfilled cases.
  - `docs/operations/` — runbook home (create if missing).

## Goal

Ship the `BenchReplayablePayload` Pydantic schema, an integration test that mechanically synthesizes ≥ 10 eval cases from the spanning stream (no human in the loop, no LLM), and a 1-page operator runbook covering how to run Phase 3, where artifacts land, how to verify the BLAKE3 chain, and how to surface evidence to operators.

## Acceptance criteria

- [ ] `src/codegenie/plugins/bench_replayable.py` (NEW) exports `BenchReplayablePayload` Pydantic v2 model: `model_config = ConfigDict(frozen=True, extra="forbid")`; fields: `input_snapshot_sha256: BlobDigest`, `transform_diff_bytes_sha256: BlobDigest`, `outcome_kind: Literal["validated", "not_applicable", "requires_human_review", "failed"]`, `cve_id: CveId`, `plugin_id: PluginId`, `recipe_id: RecipeId | None` (None when `outcome_kind` is `requires_human_review` and no recipe matched). All identifier types from `codegenie.types.identifiers` (S1-01).
- [ ] `RemediationOrchestrator.run(...)`'s `finally` block instantiates a `BenchReplayablePayload` and calls `event_log.emit_spanning(WorkflowSpanningEvent(event_type="bench_replayable", payload=payload.model_dump(), ...))` before flushing. Emission happens on every exit path (validated / not_applicable / requires_human_review / failed) — verified by `tests/unit/transforms/test_orchestrator.py` extension.
- [ ] `tests/integration/test_phase65_backfill_hook.py` (NEW) does the following in one test:
  1. Runs `codegenie remediate ...` against ≥ 10 distinct fixture repos (uses the Step 8 fixture portfolio: `express-cve-2024-21501/`, `monorepo-workspaces/`, `transitive-only-cve/`, `peer-dep-conflict/`, `major-bump-required/`, `breaking-test-suite/`, `stale-scip/`, `malformed-package-json/`, `malicious-npmrc/`, `postinstall-canary/`).
  2. Reads `.codegenie/events/spanning/append.jsonl.zst`; filters events to `event_type == "bench_replayable"`.
  3. Asserts ≥ 10 `BenchReplayablePayload` instances parse cleanly (Pydantic `model_validate`); each carries non-empty `input_snapshot_sha256` and `transform_diff_bytes_sha256` (or `transform_diff_bytes_sha256 == ""` when `outcome_kind == "not_applicable"` — fixtures `peer-dep-conflict/` and `major-bump-required/` exercise this branch).
  4. For each event, invokes a `_synthesize_bench_case(payload) -> BenchCase` helper that produces a `bench/vuln-remediation/cases/{case-id}/case.toml` mechanically (`{case-id}` derived from the payload's hashes; no human input). Writes the cases to `tmp_path / "bench/vuln-remediation/cases/"`.
  5. Asserts the written cases satisfy Phase 6.5's `loader.py` contract (load each via the Phase 6.5 `BenchCase` Pydantic shape — import path: `codegenie.eval.models.BenchCase` once Phase 6.5 ships; until then, vendor the schema into the test as a contract-snapshot per ADR-0007 pattern).
  6. No LLM SDK is imported by the test (asserts `"anthropic" not in sys.modules` and the four sibling LLM-SDK names — the mechanical-not-LLM commitment is structurally verified, not just claimed).
- [ ] `docs/operations/phase03-runbook.md` (NEW, 1 page / ≤ 60 lines of content excluding code blocks) covers exactly:
  - **How to run.** `codegenie vuln-index refresh` → `codegenie gather <repo>` (Phase 2) → `codegenie remediate <repo> --cve <id>`; exit codes 0 (validated), 3 (not-applicable), 4 (failed), 7 (requires-human-review), 8 (concurrent), 1 (internal). The four operator-facing flags (`--cve`, `--max-cost-usd` (Phase 4), `--dry-run` (Phase 4), `--verbose`). Phase 3 carries only `--cve`; the others are forward-stable surface.
  - **Where artifacts land.** `.codegenie/context/repo-context.yaml` (Phase 2 input), `.codegenie/events/workflow-internal/<workflow_id>.jsonl.zst`, `.codegenie/events/spanning/append.jsonl.zst`, `.codegenie/cache/bundles/`, `.codegenie/handoff/<workflow_id>.md` (HITL), `remediation-report.yaml` (workflow-local), the generated branch (`codegenie/cve-<id>-<shortsha>`).
  - **How to verify the BLAKE3 chain.** `codegenie audit verify --spanning-stream .codegenie/events/spanning/append.jsonl.zst`; exit 0 = unbroken; nonzero = break-point line emitted to stderr. What the chain *does* detect (local tamper, partial-write corruption); what it does *not* detect (host compromise — Phase 16's Sigstore anchors).
  - **How to surface to operators.** `remediation-report.yaml` is the canonical operator artifact; `outcome.kind`, `outcome.failing` (for `Validated(passed=False)`), and the handoff markdown (HITL) are the three fields operators read. The runbook gives one screenshot-equivalent (formatted code block) of each.
- [ ] `tests/fence/test_event_taxonomy_complete.py` (S9-02) passes — `bench_replayable` has both a declared variant in `WorkflowSpanningEvent` and an emit site in the orchestrator.
- [ ] `mypy --strict` clean; `ruff check`, `ruff format --check` clean on touched files.
- [ ] TDD plan's red test exists, committed, green.

## Implementation outline

1. **`BenchReplayablePayload` schema.** New file `src/codegenie/plugins/bench_replayable.py` (~30 LoC). Pydantic v2, frozen, `extra="forbid"`. Imports newtypes from `codegenie.types.identifiers`. `model_dump(mode="json")` produces the dict the spanning stream stores.
2. **Orchestrator emit site (extension of S6-04).** In `RemediationOrchestrator.run(...)`'s `finally`, build a `BenchReplayablePayload` from the closing state — `input_snapshot_sha256` from `repo_snapshot.sha256`; `transform_diff_bytes_sha256` from `transform.diff_bytes_sha256` (or `""` when there is no transform); `outcome_kind` from the `RemediationOutcome.kind`; identifiers from the resolution + recipe match. Emit via `event_log.emit_spanning(...)`. Flush after.
3. **Backfill integration test.** New file `tests/integration/test_phase65_backfill_hook.py`. Use `pytest.mark.parametrize` or a sequential loop over the 10 fixtures; share a `tmp_path` for the workspace; assert all four conditions (≥10 payloads, mechanically synthesizable, satisfy Phase 6.5 contract, no LLM SDK imported). The `_synthesize_bench_case(payload)` helper is the load-bearing piece — it must be deterministic, single-pass, and free of any I/O beyond `tmp_path` writes.
4. **Phase 6.5 contract snapshot.** Since Phase 6.5 has not shipped yet (per CLAUDE.md "Phases 3, 5, 6.5 — Designed but not implemented"), the test vendors Phase 6.5's `BenchCase` shape as a contract snapshot under `tests/integration/_phase65_contract.py`. When Phase 6.5 lands, that snapshot is replaced with a real import. This is the same `test_phase5_contract_snapshot.py` pattern from S6-06.
5. **Operator runbook.** `docs/operations/phase03-runbook.md`. Use the four headings above; ≤ 60 lines of content. Include verbatim CLI invocations for copy-paste. Cross-reference the ADRs (ADR-0005 for the BLAKE3 chain framing, ADR-0011 for what the chain does / does not detect). Add a `## See also` block linking `phase-arch-design.md` and `final-design.md`.
6. **mkdocs nav.** If `mkdocs.yml` has an `operations:` section, add the runbook there; if not, surface the file under the existing phases nav with a one-line note (do not invent a new top-level nav for a single page).

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/integration/test_phase65_backfill_hook.py`

```python
import sys
import zstandard
import json
from pathlib import Path

import pytest

from codegenie.plugins.bench_replayable import BenchReplayablePayload

FIXTURES = [
    "express-cve-2024-21501", "monorepo-workspaces", "transitive-only-cve",
    "peer-dep-conflict", "major-bump-required", "breaking-test-suite",
    "stale-scip", "malformed-package-json", "malicious-npmrc",
    "postinstall-canary",
]

_FORBIDDEN_LLM = {"anthropic", "langgraph", "openai", "langchain", "transformers"}


def _read_spanning(events_path: Path) -> list[dict]:
    raw = events_path.read_bytes()
    decompressed = zstandard.ZstdDecompressor().decompress(raw)
    return [json.loads(line) for line in decompressed.splitlines() if line]


def test_ten_workflows_emit_bench_replayable_and_backfill_mechanically(
    tmp_path: Path, run_remediate_against_fixture
) -> None:
    """Why it matters: Phase 6.5's promise — `codegenie eval backfill` lifts
    ≥10 cases mechanically — is unmeetable if the producer payload is missing
    fields or the consumer needs human glue. The mechanical-not-LLM contract
    is the cardinal G9 commitment (phase-arch-design.md §Goals)."""
    workspace = tmp_path / "ws"
    workspace.mkdir()

    for fx in FIXTURES:
        run_remediate_against_fixture(fx, workspace=workspace)

    spanning = workspace / ".codegenie" / "events" / "spanning" / "append.jsonl.zst"
    assert spanning.exists(), "spanning stream not produced"

    events = _read_spanning(spanning)
    bench_events = [e for e in events if e["event_type"] == "bench_replayable"]
    assert len(bench_events) >= 10, f"only {len(bench_events)} BenchReplayable events"

    payloads = [BenchReplayablePayload.model_validate(e["payload"]) for e in bench_events]

    cases_root = tmp_path / "bench" / "vuln-remediation" / "cases"
    for p in payloads:
        _synthesize_bench_case(p, cases_root)  # pure, mechanical, no I/O beyond writes
    case_dirs = sorted(cases_root.iterdir())
    assert len(case_dirs) >= 10

    # Mechanical-not-LLM contract: no LLM SDK was imported by this test.
    for name in _FORBIDDEN_LLM:
        assert name not in sys.modules, f"LLM SDK {name!r} imported during backfill"
```

State why it fails: `codegenie.plugins.bench_replayable` does not exist; the orchestrator does not yet emit `bench_replayable`; `_synthesize_bench_case` does not exist.

### Green — minimal pass
- Ship `BenchReplayablePayload` per AC.
- Extend `RemediationOrchestrator.run(...)`'s `finally` to emit the event.
- Implement `_synthesize_bench_case(payload, root)` as a pure helper: write `root / payload.hash_short / case.toml` with `[case]\ncve_id = ...\nexpected_diff_sha256 = ...`. ≤ 30 LoC.
- Write the runbook to satisfy the four-heading shape.

### Refactor
- Extract the spanning-stream reader (`_read_spanning`) into a `tests/_helpers.py` shared with `tests/fence/test_no_llm_spend.py`'s YAML walker (both consume `.codegenie/` artifacts).
- The `run_remediate_against_fixture` pytest fixture: factor from `tests/integration/test_end_to_end_express_cve.py` (S8-02) so this test does not re-invent invocation plumbing.
- Document at the top of `bench_replayable.py` exactly which Phase 6.5 fields the payload maps to (a small ASCII table is fine) so future readers see the cross-phase contract.
- Edge cases from §Edge cases that touch this code: E4 (`peer-dep-conflict/`) and E6 (`major-bump-required/`) produce `NotApplicable` outcomes — the payload's `transform_diff_bytes_sha256` is empty for these. E10 (universal fallback substitution refused) does not produce a `bench_replayable` event because the workflow exits before the orchestrator's `finally` runs — verify this with a regression test or document the exception explicitly.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/bench_replayable.py` | NEW — `BenchReplayablePayload` Pydantic schema. |
| `src/codegenie/transforms/orchestrator.py` | Extend `RemediationOrchestrator.run(...)`'s `finally` to emit `bench_replayable`. |
| `tests/integration/test_phase65_backfill_hook.py` | NEW — ≥10 cases synthesized mechanically; no LLM SDK imported. |
| `tests/integration/_phase65_contract.py` | NEW — vendored Phase 6.5 `BenchCase` shape (contract snapshot until Phase 6.5 ships). |
| `tests/unit/transforms/test_orchestrator.py` | Extend with assertions that every exit path emits `bench_replayable` exactly once. |
| `docs/operations/phase03-runbook.md` | NEW — 1-page runbook (run / artifacts / verify chain / surface to operators). |
| `mkdocs.yml` | Add the runbook to nav (or document why the existing nav already covers it). |

## Out of scope

- **Phase 6.5's `codegenie eval backfill` CLI** — owned by Phase 6.5 (not Phase 3). This story ships the **payload** and the **mechanical-synthesis pattern**; the CLI that lifts production cases ships with Phase 6.5.
- **Phase 4's solved-example store** (`.codegenie/solved/<task_class>/<example_id>.json`) — Phase 4 builds on top of `bench_replayable` additively. This story does not pre-empt the Phase 4 schema.
- **Sigstore anchoring of `bench_replayable` events** — Phase 16's hardening. The BLAKE3 chain detects local tamper; Sigstore would detect host compromise. Out of scope per ADR-0011 honest framing.
- **A `codegenie events query` CLI** — operators can `zstdcat | jq` in Phase 3 (`jq` is in `ALLOWED_BINARIES` per ADR-0012 specifically for this). A typed query CLI is Phase 13 operator-portal territory.
- **Bench files measuring the `bench_replayable` emit cost** — `bench_event_appender_throughput` (S9-03) already measures the spanning-stream write path. Single-event emit cost is dominated by the BLAKE3 + `fcntl.flock` round-trip already benchmarked.

## Notes for the implementer

- **Mechanical, not LLM-driven.** The test's `_FORBIDDEN_LLM` `sys.modules` assertion is load-bearing. If the synthesis temptation is "just ask Claude to extract the case fields from the payload," that is exactly the failure mode this story exists to prevent. The synthesis must be a pure dict→file mapping; if a field cannot be mapped without inference, the payload schema is missing a field — surface that to ADR-0005.
- **`transform_diff_bytes_sha256` for non-applied outcomes.** When `outcome_kind` is `not_applicable`, `requires_human_review`, or `failed`, there is no `transform.diff_bytes` — the field is the empty string (or `None` if the schema admits Optional; pick one and pin it in the Pydantic model). The test fixtures exercise both branches; the schema must accommodate both without `extra="forbid"` violations.
- **`BlobDigest` is a `NewType` (S1-01).** Pass it through; do not stringify and re-construct. The smart-constructor `parse_blob_digest` belongs at the *boundary* (when reading a payload back off disk), not at the emit site (which constructs from already-typed values).
- **The runbook is 1 page on purpose.** If the implementer hits 80+ lines, something belongs in `phase-arch-design.md` instead. Operators read this in a hurry; bullet density matters.
- **`codegenie audit verify` already exists** (Phase 0). S6-05 extends it to verify the BLAKE3 chain on the spanning stream. The runbook documents the operator-facing invocation; the implementation is S6-05's.
- **`mkdocs.yml` nav additions can break the docs CI.** Run `make docs` locally before committing.
- **Phase 6.5 vendoring is a documented contract snapshot.** When Phase 6.5 ships, the maintainer of that phase replaces `tests/integration/_phase65_contract.py` with a real import + deletes the vendored shape. Until then, drift between the vendored snapshot and the eventual real schema is a Phase 3 → Phase 6.5 handshake risk — surface it via the same `test_phase5_contract_snapshot.py` pattern S6-06 uses.
- **The orchestrator's `finally` runs even on exception** — that's the point of `finally`. If the workflow crashed before assigning a `transform`, the emit code must defensively handle the partial state (`outcome_kind="failed"`, empty `transform_diff_bytes_sha256`). Test this with a deliberate inner-stage exception fixture.
- **Match `S9-02`'s docstring discipline.** Every test docstring opens with the *why* (G9 commitment, mechanical contract) before the *how* — future readers should understand the load-bearing rationale at a glance.
