# Story S7-05 — Mixed portfolio warm E2E

**Step:** Step 7 — Performance canaries + fence-CI extension
**Status:** Ready
**Effort:** M
**Depends on:** S7-04
**ADRs honored:** ADR-P7-014 (perf-baseline pattern), ADR-P7-001 (additive seams — verifies vuln + distroless coexist on one substrate)

## Context

Goal G7 commits Phase 7 to ≥ 10/hr mixed-portfolio warm throughput — vuln workflows from Phase 6 interleaved with distroless workflows from Phase 7, exercising the *same* `AuditedSqliteSaver` + audit-chain + sandbox chokepoint. The throughput canary in S7-03 measured the *number*; this E2E story measures the *integration* — both task classes complete cleanly when interleaved, both audit chains stay disjoint (per Gap 1 / S5-07), both ledgers (`VulnLedger` from Phase 6, `DistrolessLedger` from S5-01) round-trip cleanly. This is the integration evidence for G1 ("both task classes run from the same orchestration substrate") under load.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals G1` — both task classes on the same substrate.
  - `../phase-arch-design.md §Goals G7` — warm mixed ≥ 10/hr.
  - `../phase-arch-design.md §Architectural context` — the `cli/loop.py` (vuln) and `cli/migrate.py` (distroless) sibling-CLI shape.
  - `../phase-arch-design.md §Testing strategy ›End-to-end tests` bullet 2 — `tests/e2e/test_mixed_portfolio_warm.py` is the named file.
  - `../phase-arch-design.md §Fixture portfolio` — the 3 distroless fixtures; need to identify ≥ 1 vuln fixture from Phase 6 to interleave.
- **Phase ADRs:**
  - `../ADRs/0014-regression-suite-wall-clock-canary.md` — ADR-P7-014 — baseline pattern.
  - `../ADRs/0001-six-named-additive-seams-and-adr-0028-amendment.md` — ADR-P7-001 — the integration goal (extension by addition lets these run side-by-side).
  - `../ADRs/0011-distroless-ledger-parallel-to-vuln-ledger.md` — ADR-P7-011 — confirms `DistrolessLedger` and `VulnLedger` are parallel; this E2E asserts they don't collide under interleaving.
  - `../ADRs/0012-parallel-cli-verbs-no-shared-dispatcher.md` — ADR-P7-012 — no shared dispatcher in Phase 7; this E2E drives both verbs from the test orchestrator, not from a shared dispatcher.
- **Source design:**
  - `../final-design.md §Goals#1` — throughput targets.
- **Existing code:**
  - `src/codegenie/cli/loop.py` (Phase 6, unchanged) — vuln entry point.
  - `src/codegenie/cli/migrate.py` (S5-05) — distroless entry point.
  - `tests/integration/test_chain_no_collision_across_tasks.py` (S5-07) — confirms audit chains are disjoint at the *contract* level; this E2E confirms it at the *runtime* level under interleaving.
  - Phase 6 vuln fixture(s) — at least one is needed; check `tests/fixtures/repos/` for the Phase-6-canonical fixture.
  - The 3 distroless fixtures from `tests/fixtures/repos/{express,static-go,alpine-to-glibc}-distroless/`.

## Goal

`pytest tests/e2e/test_mixed_portfolio_warm.py` runs 10 interleaved (vuln, distroless, vuln, distroless, …) workflows over a warm BuildKit cache and asserts: ≥ 10/hr throughput; both audit chains intact and disjoint; both ledger types deserialize cleanly; no cross-task contamination.

## Acceptance criteria

- [ ] `tests/e2e/test_mixed_portfolio_warm.py` exists and runs as an E2E test (not a unit test, not a perf-only test — it makes assertions about *behavior* under load, not just throughput).
- [ ] The test interleaves ≥ 10 workflows: 5 vuln (driven via `codegenie loop`) + 5 distroless (driven via `codegenie migrate`), strict alternation, sharing the same warm BuildKit cache populated by an in-fixture cold pre-pass.
- [ ] Warm throughput ≥ 10/hr (G7) — total wall-clock for the 10 interleaved workflows ≤ 3600 s.
- [ ] Every workflow exits 0 (success); a non-zero exit on any single workflow fails the E2E with the failing workflow's `<run-id>` and the captured CLI stderr.
- [ ] Audit chain disjointness asserted: `.codegenie/loop/audit/` and `.codegenie/migration/audit/` (or whatever the canonical directories are per S5-07) contain disjoint chain heads — no chain-head collision across the 10 runs.
- [ ] Both ledger types verified post-run: every distroless run's `migration-report.yaml` deserializes via `DistrolessLedger.model_validate(...)`; every vuln run's analog deserializes via `VulnLedger.model_validate(...)`.
- [ ] No cross-task contamination: a vuln workflow's audit-chain head does *not* reference a distroless workflow's checkpoint and vice versa; asserted by inspecting BLAKE3 prev-pointers in the two chains.
- [ ] Per-workflow time-to-PR recorded in test report (informational); the recipe-hot p95 from this leg cross-checks S7-03's number (within ±15 % is acceptable — different *interleaving* can change wall-clock).
- [ ] The TDD plan's red tests exist, were committed, and are green.
- [ ] Test is in CI's merge-gate lane (under the `e2e` lane, alongside `test_migrate_node_e2e.py` from S5-06).
- [ ] `ruff check`, `ruff format --check`, and `mypy --strict` clean on touched files.

## Implementation outline

1. Identify the canonical Phase 6 vuln fixture (read `tests/integration/test_migrate_node_e2e.py` from S5-06 and the Phase 6 fixture catalog for the convention). If there's exactly one canonical fixture, drive 5 vuln runs against it with 5 distinct `--cve` IDs (or 5 distinct `--workflow-tag` overrides). If there are multiple, rotate through them.
2. Add `tests/e2e/test_mixed_portfolio_warm.py`. Build a module-scoped fixture `mixed_portfolio_run` that:
   - performs the cold pre-pass (one workflow per fixture) to warm the BuildKit cache and pull `cgr.dev` images;
   - runs the 10 interleaved workflows (vuln, distroless, vuln, distroless, …) sequentially;
   - captures per-workflow exit code, wall-clock, `<run-id>`, and report-file path.
3. Drive workflows via `subprocess.run` against the installed CLI entry points (`codegenie loop run`, `codegenie migrate run`) — same pattern as S7-03; do *not* import `build_distroless_loop` directly.
4. Add three assertion blocks: (a) throughput, (b) audit-chain disjointness via BLAKE3 prev-pointer inspection, (c) ledger round-trip.
5. Add the test to the CI E2E lane.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/e2e/test_mixed_portfolio_warm.py
def test_mixed_portfolio_warm_throughput_at_least_10_per_hour(mixed_portfolio_run):
    per_hour = mixed_portfolio_run.per_hour
    assert per_hour >= 10.0, (
        f"mixed warm throughput {per_hour:.2f}/hr < 10/hr; "
        f"per-workflow: {mixed_portfolio_run.per_workflow_seconds}"
    )

def test_mixed_portfolio_no_audit_chain_collision(mixed_portfolio_run):
    vuln_heads = mixed_portfolio_run.vuln_chain_heads
    distroless_heads = mixed_portfolio_run.distroless_chain_heads
    assert vuln_heads.isdisjoint(distroless_heads), (
        f"audit chain heads collide across task types: {vuln_heads & distroless_heads}"
    )

def test_mixed_portfolio_both_ledger_types_round_trip(mixed_portfolio_run):
    # arrange: each distroless run produced a migration-report.yaml; each vuln run produced its analog
    # act/assert
    for path in mixed_portfolio_run.distroless_report_paths:
        DistrolessLedger.model_validate(yaml.safe_load(path.read_text()))
    for path in mixed_portfolio_run.vuln_report_paths:
        VulnLedger.model_validate(yaml.safe_load(path.read_text()))

def test_mixed_portfolio_no_cross_task_prev_pointer(mixed_portfolio_run):
    # arrange: walk every chain entry's BLAKE3 prev-pointer
    # act/assert: no vuln entry points at a distroless entry and vice versa
    cross_refs = find_cross_task_prev_pointers(mixed_portfolio_run.chain_graph)
    assert cross_refs == [], f"cross-task prev-pointer contamination: {cross_refs}"
```

`mixed_portfolio_run` fixture and `find_cross_task_prev_pointers` helper don't exist — pytest errors. Commit.

A unit-level red test for the chain-graph cross-task detector (so we can iterate without the slow E2E):

```python
# tests/e2e/test_chain_graph_helpers.py
def test_cross_task_prev_pointer_detected_when_present():
    # arrange: synthetic chain graph where a distroless entry's prev points at a vuln entry
    graph = ChainGraph(
        nodes=[
            ChainNode(id="d1", task="distroless", prev="v1"),
            ChainNode(id="v1", task="vuln", prev=None),
        ],
    )
    # act
    cross = find_cross_task_prev_pointers(graph)
    # assert
    assert cross == [("d1", "v1")]

def test_no_cross_task_returns_empty_list():
    graph = ChainGraph(nodes=[
        ChainNode(id="d1", task="distroless", prev=None),
        ChainNode(id="v1", task="vuln", prev=None),
    ])
    assert find_cross_task_prev_pointers(graph) == []
```

### Green — make it pass

- Add `tests/e2e/_chain_graph.py` with `ChainGraph`, `ChainNode` (frozen Pydantic), and `find_cross_task_prev_pointers()`.
- Add the `mixed_portfolio_run` fixture in `tests/e2e/conftest.py` (or extend the existing perf `conftest.py` — pick whichever Phase 0's convention prefers).
- Add the four test functions.

### Refactor — clean up

- Type hints + frozen Pydantic everywhere.
- Docstring on the test module explicitly stating: "This E2E is the *runtime* analog of S5-07 (`test_chain_no_collision_across_tasks.py`), which tested the contract; this story tests behavior under interleaving."
- Edge case from `phase-arch-design.md §Edge cases #9` (grype DB update race) — if the vuln workflows race on grype DB refresh, the test must surface the race rather than silently retry; the chain-graph detector catches it as a cross-task prev-pointer if it happens.
- Per Global Rule 12 (Fail loud): any non-zero CLI exit during the 10 interleaved workflows fails the E2E with the captured stderr — never silently retry.
- Per ADR-P7-011: the test asserts `VulnLedger` and `DistrolessLedger` are *distinct* — running both validators against the same report should produce one success and one `ValidationError`. Optional bonus assertion (do not add if it creates noise; tests should be honest).
- Wire test into CI E2E lane; document its ~6–10 minute wall-clock in the test docstring.

## Files to touch

| Path | Why |
|---|---|
| `tests/e2e/test_mixed_portfolio_warm.py` | New file — the E2E (G7). |
| `tests/e2e/test_chain_graph_helpers.py` | New file — unit tests for the chain-graph detector. |
| `tests/e2e/_chain_graph.py` | New file — `ChainGraph`, `ChainNode`, `find_cross_task_prev_pointers()`. |
| `tests/e2e/conftest.py` | Add `mixed_portfolio_run` module-scoped fixture (or extend `tests/perf/conftest.py` if Phase 0 conventions prefer). |
| `tests/perf/baseline.json` | Add `mixed_portfolio_warm_per_hr` key (cross-checked against S7-03's number). |
| `.github/workflows/ci.yml` | Add to E2E lane. |

## Out of scope

- **Cold mixed throughput.** Only warm is in G7; cold is implicitly bounded by G6 (cold distroless ≥ 6/hr) plus Phase 6's cold vuln number. Don't introduce a cold-mixed canary here.
- **Per-task memory differentiation.** Owned by S7-06 (per-worker steady-state ≤ 2.4 GB total).
- **Time-to-PR p95 cap enforcement.** Recorded informationally; G8 caps are observed-only in Phase 7 (recipe-hot enforced in S7-03; RAG/LLM observed until Phase 13 calibration).
- **3-fixture distroless portfolio expansion.** Owned by S6-01 (≥ 30 adversarial corpus); this E2E reuses the same 3 fixtures.
- **Supervisor-driven dispatch.** Per ADR-P7-012, no shared dispatcher in Phase 7. The test orchestrator dispatches by alternating CLI verbs.

## Notes for the implementer

- **Interleaving is strict alternation.** Vuln, distroless, vuln, distroless, ... — *not* "5 vuln then 5 distroless". The point is to catch shared-state collisions under back-and-forth load (e.g. SQLite WAL contention, audit-chain lock contention).
- **Drive both verbs through the operator CLI.** Per ADR-P7-012, there's no shared dispatcher in Phase 7. The test orchestrator is the closest thing to a dispatcher and lives only in test code.
- **Read S5-07's `test_chain_no_collision_across_tasks.py` first.** S5-07 asserts disjointness at the *contract* level (workflow_id schemes); this E2E asserts it at the *runtime* level (actual chain heads after 10 runs). The two tests should look like siblings.
- **The cold pre-pass is *not* one of the 10 interleaved workflows.** It's setup. The 10 measured workflows all run against a warm cache.
- **Identify the Phase 6 vuln fixture before writing the test.** Per Global Rule 8 (Read before you write) — there is exactly one Phase-6-canonical vuln fixture; don't fabricate one. If there are multiple, rotate through them deterministically (seeded ordering — no `random`).
- **Per `phase-arch-design.md §Harness engineering ›Determinism vs probabilism`:** no `random` or `time` imports under the test fixture. Workflow ordering is deterministic; per-run wall-clock varies but the *ordering* must not.
- **Per Global Rule 12 (Fail loud):** a non-zero CLI exit, a missing report file, or a deserialization failure all hard-fail the E2E. Do not "skip and continue" — the canary's job is to catch silent regressions, and silently skipping a failed workflow is the worst regression.
- **`VulnLedger`'s schema is owned by Phase 6.** Read its current shape before writing the round-trip assertion; if Phase 6's ledger has evolved post-S6 (extending Phase 6 is *itself* a Phase 8 question), this story may need a regen of the `tests/perf/baseline.json` keys — link the relevant ADR in the PR.
- **~6–10 min wall-clock budget for this E2E.** Document in test docstring; CI must accept the cost. If wall-clock exceeds 10 min, file as a perf follow-up, do not silently shard the test.
