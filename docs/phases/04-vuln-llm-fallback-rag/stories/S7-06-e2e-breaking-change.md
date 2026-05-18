# Story S7-06 — E2E breaking-change exit criterion #1

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** Ready
**Effort:** L
**Depends on:** S7-05 (fixture portfolio), S6-05 (`typecheck.typescript` SignalKind), S6-03 (`on_validated` harvest hook), S7-01 (plugin adapter wired), S3-05 (`cassettes.lock` discipline)
**ADRs honored:** ADR-0009 (inline harvest gated by `passed AND confidence == "high"`), ADR-0012 (ProvenanceGate spends zero tokens on non-app-layer), ADR-0015 (`typecheck.typescript` SignalKind in strict-AND), ADR-0014 (cassette discipline)

## Context

This is **roadmap exit criterion #1** in one test file: a breaking-change CVE (Express 4→5, the `express-cve-2026-1234` fixture from S7-05) runs end-to-end — Phase-3 recipe returns `NotApplicable` because the bump is breaking → Phase-4 `FallbackTier` invokes the leaf LLM via cassette replay → the LLM emits a `PlanProposalCallsiteRewrite` → Phase-5 strict-AND (build + install + tests + lockfile_policy + cve_delta + **typecheck.typescript**) passes → orchestrator invokes `on_validated`, confidence-gate fires, inline harvest writes a `SolvedExample` to the store. Asserted by `LlmCostAccrued` event present, `SolvedExampleHarvested` event present, and a query of the store post-test returning the harvested record.

The test is **cassette-replayed**, not live — `pytest-recording` plays back the response Anthropic returned when the cassette was first recorded. Recording happens via `make refresh-cassettes --i-understand-this-spends-tokens` (S3-06) with `CODEGENIE_LIVE_LLM=1` set; the recorded cassette lands at `tests/cassettes/anthropic/test_phase4_e2e_breaking_change.yaml`, is sanitized by `CassetteSanitizer` (S3-04), and is BLAKE3-pinned in `cassettes.lock` (S3-05). CI replays only.

Three non-obvious failure modes the test must rule out:
1. **Provenance gate refuses but test still passes** — the test must positively assert `Provenance.AppTransitive` (or `AppDirect`) was the classification, so the LLM path actually ran (not a false-positive refuse).
2. **`tsc` reports degraded confidence (no `tsconfig.json`)** — the express fixture must ship `tsconfig.json` so `typecheck.typescript` reports `confidence="high"`, otherwise the harvest gate (`confidence == "high"`) won't fire and the test silently asserts the wrong final state.
3. **`SolvedExampleHarvested` event fires but the record isn't actually queryable** — the test must, after `on_validated`, query the store with the same CVE and assert the harvested record is returned with similarity ≥ `high_floor=0.85`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals — G1` — "Phase 3 recipe returns `NotApplicable` → Phase 4 LLM-replan succeeds → Phase 5 strict-AND (build, install, tests, lockfile_policy, cve_delta, **typecheck.typescript**) passes → outcome harvested → second run on the same case hits RAG and shapes a cheaper LLM call. Asserted by `tests/integration/test_phase4_e2e_breaking_change.py` + `tests/integration/test_phase4_e2e_replay_lands_rag.py`."
  - `../phase-arch-design.md §Scenario 2` — full sequence diagram (Major-version bump triggers LLM fallback, harvests on validate). Each numbered arrow is an assertable event.
  - `../phase-arch-design.md §Edge case #1` — provenance gate refusal scenario (the test must rule it out for express by asserting `AppTransitive` was classified).
  - `../phase-arch-design.md §Testing strategy §End-to-end` — "The two E2E tests above against `fixtures/vuln-major-bump/express-cve-2026-1234/` are end-to-end (CLI → patch on disk → Stage 6 strict-AND pass)."
- **Phase ADRs:**
  - `../ADRs/0009-inline-auto-harvest-confidence-gate.md` — `TrustOutcome.passed AND confidence == "high"` is the harvest gate; this story's test asserts both conditions hold and the harvest fires.
  - `../ADRs/0012-provenance-gate-explicit-tier-zero.md` — refuse-set; the test must assert `Provenance.AppTransitive` (so LLM was actually called).
  - `../ADRs/0015-typecheck-typescript-signal-and-tsc-allowed-binary.md` — `typecheck.typescript` is one of the six signals in strict-AND.
  - `../ADRs/0014-cassette-discipline-security-control.md` — the cassette this test consumes must be sanitized, lock-pinned, and CI-replayed.
- **Source design:**
  - `../final-design.md §Component 1 — FallbackTier` + §Component 11 — `TypecheckTypescriptSignal`.
- **High-level impl:**
  - `../High-level-impl.md §Step 7 §Done criteria` — "Roadmap exit criterion #1: `test_phase4_e2e_breaking_change.py` ... green under cassette replay."
- **Existing code:**
  - `tests/fixtures/repos/express-cve-2026-1234/` (S7-05) — the fixture.
  - `tests/integration/test_end_to_end_express_cve.py` (Phase-3 S8-02) — the **template** to mirror for CLI-driver pattern, masking helpers, golden-file approach. Read first.
  - `src/codegenie/cli/__init__.py` — the `codegenie remediate` Click subcommand (Phase 3 S6-05).
  - `src/codegenie/orchestrator/orchestrator.py` (Phase 3) — `RemediationOrchestrator.run`.
  - `src/codegenie/fallback/tier.py` (S6-01) and `plugins/.../subgraph/fallback_plan_engine.py` (S7-01) — the plan adapter.

## Goal

Land `tests/integration/test_phase4_e2e_breaking_change.py` as a cassette-replayed CI-gating integration test that runs `codegenie remediate ./tests/fixtures/repos/express-cve-2026-1234 --cve CVE-2026-1234` and asserts: (a) the CLI exits 0; (b) the `Provenance.AppTransitive` classification fired (provenance gate did **not** refuse); (c) Phase-3 recipe returned `NotApplicable(major_bump_breaking_change)`; (d) `LeafInvoked` fired exactly once; (e) `PlanProposalCallsiteRewrite` was returned; (f) Phase-5 strict-AND passed including `typecheck.typescript`; (g) `confidence == "high"`; (h) `SolvedExampleHarvested` fired; (i) querying the store post-run returns the harvested record with similarity ≥ `high_floor`. Green under cassette replay.

## Acceptance criteria

- [ ] `tests/integration/test_phase4_e2e_breaking_change.py` exists, is collected by pytest (not skipped), and is marked `@pytest.mark.integration` and `@pytest.mark.phase4`.
- [ ] The test runs via `click.testing.CliRunner` (not subprocess) so coverage instruments orchestrator + plugin paths; `result.exit_code == 0` is asserted with `result.output` in the failure message.
- [ ] `tests/cassettes/anthropic/test_phase4_e2e_breaking_change.yaml` exists, was recorded via `make refresh-cassettes`, passes `tests/security/test_cassettes_clean.py` (S3-05), and is entered in `cassettes.lock` (S3-05) with a BLAKE3 hash matching its on-disk bytes.
- [ ] The test runs hermetically: `shutil.copytree` clones the fixture into `tmp_path` before invoking the CLI; `.codegenie/` writes and git branch creation land in tmp; the source fixture stays unchanged across runs.
- [ ] **Provenance assertion (rules out the refuse false-positive):** the test reads the event stream and finds `ProvenanceClassified(kind="AppTransitive")` (or `AppDirect` — assert it's in the app-layer set, not in `{BaseImage, RuntimeBundled, Unknown}`).
- [ ] **Phase-3-recipe-returned-NotApplicable assertion:** the event stream contains a `RecipeOutcomeEmitted` for the Phase-3 dep-bump recipe carrying `kind="not_applicable"` with `reason` matching `major_bump_breaking_change` (or whatever the Phase-3 recipe's refusal reason string is — read S7-04 of Phase 3).
- [ ] **LLM-was-called assertion:** the event stream contains exactly one `LeafInvoked` event and exactly one `LeafReturned` event with `tokens_in > 0` and `tokens_out > 0`.
- [ ] **Plan-shape assertion:** the event stream's `PlanOutcomeEmitted` event carries variant `AppliedFromLlm` with a non-empty `response_id`.
- [ ] **Strict-AND-passed assertion:** the Phase-5 `TrustOutcome` event carries `passed=True`, `confidence="high"`, and `signals` contains a `typecheck.typescript` entry with `passed=True`.
- [ ] **Harvest-fired assertion:** the event stream contains one `SolvedExampleHarvested` event with a non-empty `solved_example_id`.
- [ ] **Store-queryable assertion:** after the test completes, the test instantiates a `ChromaPersistentStore` against the tmp `.codegenie/rag/chroma/` directory, builds a `Query` matching the express CVE via the plugin's `rag_query_builder` (S7-02), and asserts `store.query(q).top_score >= 0.85` (the harvested record is now queryable above the high floor).
- [ ] **Cost-recorded assertion:** the event stream contains one `LlmCostAccrued` event with non-zero tokens and dollars; the test captures these for S7-07 to compare against.
- [ ] **Determinism guard:** running the test twice in a row (cassette replay both times) produces byte-identical `remediation-report.yaml` after masking `workflow_id` / timestamps / `event_id` (mirror Phase-3 S8-02's masking helper).
- [ ] The test fails-loud (not skips) if `bwrap` / `sandbox-exec` is missing on Linux/macOS — mirror Phase-3 S8-02's contract.
- [ ] Cassette regeneration is documented: the test's module docstring names `make refresh-cassettes --i-understand-this-spends-tokens CODEGENIE_LIVE_LLM=1` as the regeneration command and cross-links the cassette CODEOWNERS entry (S3-06).
- [ ] `make check` clean with cassette replay.
- [ ] TDD red test exists, committed, green.

## Implementation outline

1. **Read first**: open `tests/integration/test_end_to_end_express_cve.py` (Phase-3 S8-02) for the CLI-driver, masking-helper, and golden-file patterns; mirror them (Global Rule 11).
2. Write the test skeleton: copy the fixture to `tmp_path`, invoke the CLI via `CliRunner`, assert exit code, parse the event stream.
3. Implement the cassette-recording flow first (one-time): run `make refresh-cassettes` with `CODEGENIE_LIVE_LLM=1` set + valid Anthropic API key in keyring; the recorded cassette lands under `tests/cassettes/anthropic/` and is sanitized by S3-04's hooks at record time.
4. Add the cassette to `cassettes.lock` (S3-05): compute BLAKE3, append the entry.
5. Implement the event-stream parser (read `.codegenie/events/workflow-internal/<workflow_id>.jsonl.zst`, decompress, parse line-by-line into typed `WorkflowInternalEvent` variants from Phase 3).
6. Add per-acceptance-bullet assertions, each with a meaningful failure message naming which roadmap criterion or arch §Scenario 2 numbered arrow is violated.
7. Add the post-test store-queryability assertion: open `ChromaPersistentStore` against the tmp dir; build a `Query` via `rag_query_builder.build(...)`; assert similarity ≥ 0.85.
8. Run with cassette replay to confirm green; flake-check by running 10× in a row.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/integration/test_phase4_e2e_breaking_change.py
"""
Phase 4 roadmap exit criterion #1 — breaking-change CVE solved end-to-end.

Regenerating the cassette:
    make refresh-cassettes --i-understand-this-spends-tokens CODEGENIE_LIVE_LLM=1
The cassette `tests/cassettes/anthropic/test_phase4_e2e_breaking_change.yaml`
is owned by the rotating cassette-steward (CODEOWNERS); regeneration requires
that owner's approval.
"""
from __future__ import annotations
import json
import shutil
from pathlib import Path
import pytest
import zstandard as zstd
from click.testing import CliRunner

from codegenie.cli import remediate
from codegenie.rag.store import ChromaPersistentStore
from codegenie.rag.embedder import FastembedEmbedder
from plugins.vulnerability_remediation_node_npm.recipes import rag_query_builder


FIXTURE = Path("tests/fixtures/repos/express-cve-2026-1234")
CASSETTE = Path("tests/cassettes/anthropic/test_phase4_e2e_breaking_change.yaml")


@pytest.fixture
def vcr_cassette_dir(tmp_path):
    return str(CASSETTE.parent)


@pytest.fixture
def hermetic_repo(tmp_path):
    target = tmp_path / "express-cve-2026-1234"
    shutil.copytree(FIXTURE, target)
    return target


def _parse_events(events_dir: Path) -> list[dict]:
    files = list(events_dir.rglob("*.jsonl.zst"))
    assert files, f"no internal event stream under {events_dir}"
    out = []
    for f in files:
        raw = zstd.ZstdDecompressor().decompress(f.read_bytes())
        for line in raw.decode().splitlines():
            out.append(json.loads(line))
    return out


@pytest.mark.integration
@pytest.mark.phase4
@pytest.mark.vcr(CASSETTE.name, record_mode="none")
def test_phase4_e2e_breaking_change(hermetic_repo, vcr_cassette_dir):
    runner = CliRunner()
    result = runner.invoke(
        remediate,
        [str(hermetic_repo), "--cve", "CVE-2026-1234"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"CLI failed:\n{result.output}"

    events = _parse_events(hermetic_repo / ".codegenie" / "events" / "workflow-internal")

    # (a) Provenance fires AppTransitive (rules out refuse false-positive).
    provs = [e for e in events if e["kind"] == "ProvenanceClassified"]
    assert provs and provs[0]["provenance_kind"] in {"AppDirect", "AppTransitive", "AppVendored", "Both"}

    # (b) Phase-3 recipe returned NotApplicable for major-bump.
    recipes = [e for e in events if e["kind"] == "RecipeOutcomeEmitted"]
    assert any(
        r.get("outcome", {}).get("kind") == "not_applicable" and "major" in r.get("outcome", {}).get("reason", "").lower()
        for r in recipes
    )

    # (c) LLM was invoked exactly once.
    leaf_invoked = [e for e in events if e["kind"] == "LeafInvoked"]
    leaf_returned = [e for e in events if e["kind"] == "LeafReturned"]
    assert len(leaf_invoked) == 1
    assert len(leaf_returned) == 1
    assert leaf_returned[0]["tokens_in"] > 0
    assert leaf_returned[0]["tokens_out"] > 0

    # (d) PlanOutcome is AppliedFromLlm.
    [plan_out] = [e for e in events if e["kind"] == "PlanOutcomeEmitted"]
    assert plan_out["plan_outcome"]["kind"] == "applied_from_llm"
    assert plan_out["plan_outcome"]["response_id"]

    # (e) Strict-AND passed including typecheck.typescript.
    [trust] = [e for e in events if e["kind"] == "TrustOutcomeEmitted"]
    assert trust["passed"] is True
    assert trust["confidence"] == "high"
    signal_kinds = {s["kind"] for s in trust["signals"]}
    assert "typecheck.typescript" in signal_kinds
    [ts_sig] = [s for s in trust["signals"] if s["kind"] == "typecheck.typescript"]
    assert ts_sig["passed"] is True

    # (f) Harvest fired.
    [harvest] = [e for e in events if e["kind"] == "SolvedExampleHarvested"]
    assert harvest["solved_example_id"]

    # (g) Cost recorded.
    [cost] = [e for e in events if e["kind"] == "LlmCostAccrued"]
    assert cost["tokens_total"] > 0
    assert float(cost["dollars"]) > 0

    # (h) Store is queryable post-run; harvested record returns above high_floor.
    store = ChromaPersistentStore(hermetic_repo / ".codegenie" / "rag" / "chroma")
    embedder = FastembedEmbedder()  # picks up the bootstrapped model
    advisory = _load_cve_yaml(hermetic_repo / "cve.yaml")
    repo_ctx = _load_repo_ctx(hermetic_repo)
    q = rag_query_builder.build(advisory, repo_ctx)
    outcome = store.query(q, top_k=1)
    assert outcome.kind == "rag_hit", f"expected RagHit, got {outcome.kind}"
    assert outcome.score >= 0.85
    store.close()
```

Run: `pytest tests/integration/test_phase4_e2e_breaking_change.py -v` — fails on every assertion before the implementation chain is wired.

### Green — make it pass

1. Wire the pieces from Steps 1–6 + S7-01..S7-05.
2. Record the cassette via `make refresh-cassettes` and confirm `tests/security/test_cassettes_clean.py` passes.
3. Add the cassette to `cassettes.lock`.
4. Run the test; iterate until every assertion is green.

### Refactor — clean up

- Extract `_load_cve_yaml`, `_load_repo_ctx`, and `_parse_events` into a `tests/integration/_phase4_e2e_helpers.py` module shared with S7-07 (Global Rule 7 — surface conflict if S7-07 wants to define them differently).
- Add a `_mask_nondeterministic_fields` helper if golden-file diffing is also part of this test (mirror Phase-3 S8-02 helper); document each masked field.
- Run 10× in a row to flake-check; document any flake-mitigation choice in the module docstring.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_phase4_e2e_breaking_change.py` | The exit-criterion test. |
| `tests/integration/_phase4_e2e_helpers.py` | Shared helpers for S7-06 + S7-07 (event-stream parser, fixture loaders). |
| `tests/cassettes/anthropic/test_phase4_e2e_breaking_change.yaml` | Recorded (sanitized) Anthropic cassette. |
| `tests/cassettes/anthropic/cassettes.lock` | New entry with BLAKE3 hash of the cassette. |

## Out of scope

- The replay-lands-RAG E2E test (S7-07) — sibling story consuming the harvested record from this test's store output.
- Adversarial corpus (S7-09).
- Golden-file masking (optional here; mandatory in S8-02 of Phase 3 for the report; this E2E test's primary assertions are event-driven, not byte-equal report).
- Performance regression `bench_phase4_e2e_cassette_replay` (covered under S6-01's `bench` markers).

## Notes for the implementer

- **Cassette recording is gated by `make refresh-cassettes --i-understand-this-spends-tokens` (S3-06) + valid keyring entry.** Do not run live API calls inside the test loop; one-time recording is the discipline.
- The `Provenance.AppTransitive` (or similar app-layer) assertion is the most-likely-to-be-skipped guard — without it, a regression in the provenance adapter (S7-03) could turn this test into a silent provenance-refuse passing case where the LLM is never called and the test still "passes" in the wrong way. **Fail loud per Global Rule 12.**
- The "harvested record queryable post-run" assertion is the proof of the Phase-4 exit criterion #1 plus the precondition for exit criterion #2 (S7-07). If the record isn't queryable above `high_floor`, S7-07 cannot succeed — surface loudly.
- The fixture's `tsconfig.json` must produce `tsc --noEmit` exit-code 0 on Express-4 (pre-patch). If `tsc` reports errors on the *baseline*, the `typecheck.typescript` signal's strict-AND will incorrectly flag the post-patch state. Validate this during S7-05 fixture construction, not at E2E time.
- The cassette body has been sanitized by S3-04; even so, do not log `cassette.serialize()` anywhere — keep the response BLAKE3-digested in audit events only (arch §Logging strategy).
- The `LeafInvoked == 1` assertion is the witness that the LLM was actually called — combine with `Provenance.AppTransitive` to rule out the refuse-false-positive failure mode.
- If the test passes on first replay but fails on second replay, the cassette is being mutated mid-test (a bug in S3-04 or `pytest-recording`); surface immediately per Global Rule 12.
