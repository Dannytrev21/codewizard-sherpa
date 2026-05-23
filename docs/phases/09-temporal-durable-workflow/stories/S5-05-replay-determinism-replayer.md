# Story S5-05 — Replay-determinism `WorkflowReplayer` fixture + per-Python-minor matrix

**Step:** Step 5 — Postgres checkpointer adapter + workflow definitions
**Status:** Ready
**Effort:** M
**Depends on:** S5-02 (`VulnRemediationWorkflow` body must already exist and pass the AST/import-linter layers), S5-03 (freshness-window resume — included in the recorded history matrix so its replay path is also fenced), S1-07 (workflow-determinism three-layer infrastructure — `Replayer` is the third, most-expensive layer)
**ADRs honored:** Phase 9 ADR-0004 (workflow determinism three layers — this story IS the third layer: `WorkflowReplayer.run_replay_workflows(...)` against committed fixture histories on every PR, per Python-minor matrix); Phase 9 ADR-0010 (asymmetric activity granularity — replay is the workflow body's responsibility; the LangGraph subgraph runs inside an activity and is opaque to replay); Phase 9 ADR-0011 (Postgres checkpointer — the `PostgresCheckpointerAdapter` lives inside the `run_vuln_subgraph` activity, NOT inside the workflow body, so replay is unaffected by checkpointer state); Phase 9 ADR-0013 (no Temporal port abstraction — replay uses Temporal SDK directly).

## Context

ADR-0004 prescribes three layers of workflow-determinism enforcement: (1) `import-linter` (catches direct imports of `random/time/datetime/...`), (2) AST walker (catches direct call shapes like `random.choice(`, `datetime.now(`), and (3) `temporalio.testing.WorkflowReplayer.run_replay_workflows(...)` against a committed-history fixture (catches transitive non-determinism — LangGraph version drift, dict-iteration-order changes between Python 3.11 and 3.12, asyncio scheduling drift). Layers 1 and 2 land in S1-07; this story lands layer 3. It is the most expensive layer (history-fixture recording ceremony, per-Python-minor matrix in CI) and the easiest to mark `@pytest.mark.flaky` under operational pressure — `High-level-impl.md §Risks` calls this out explicitly as risk #1. The discipline: when this test fails on a PR that did not touch `codegenie.durable.workflows/`, the contributor MUST treat it as a real signal (transitive non-determinism leak through an upstream version drift), record the diff between recorded-and-replayed history as a CI artifact, and either pin the offending upstream or fix the leak. **The test MUST NOT be marked flaky.** This story commits the initial fixture histories (one for `VulnRemediationWorkflow` happy path; one for `VulnRemediationWorkflow` HITL-pause-resume; one for `MultiPluginParentWorkflow` 2-child happy path; one for the freshness-window stale-resume tier-descent path from S5-03), wires the per-Python-minor matrix into CI, and writes the regenerate-fixture ceremony.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Scenario 3 — Adversarial: replay-determinism violation (caught by CI Replayer)` — the canonical scenario this story protects against.
  - `../phase-arch-design.md §Harness engineering — Replay` — fixture lifecycle: "records a workflow's history once, then runs `WorkflowReplayer.run_replay_workflows(...)` against the recorded history on every PR. Includes a per-Python-minor matrix (3.11 + 3.12)."
  - `../phase-arch-design.md §Edge case 5 — Workflow determinism violation on resume` — the failure mode this layer catches.
  - `../phase-arch-design.md §Goals G4 — workflow determinism enforcement` — exit criterion.
- **Phase ADRs:**
  - `../ADRs/0004-workflow-determinism-enforcement-three-layers.md` — full layered model + `Replayer` rationale.
- **Implementation plan:**
  - `../High-level-impl.md §Step 5 — Features delivered — tests/workflows/test_replay_determinism.py` — exact prescription including the per-Python-minor matrix.
  - `../High-level-impl.md §Risks specific to this step` — risk #1: "the test must produce a deterministic error pointing at the offending diff (Temporal SDK does this — preserve the full `NondeterminismError` payload in the test output); CI must record the recorded-vs-replayed history diff as an artifact."
- **Upstream:**
  - `temporalio.testing.WorkflowReplayer` docs — `run_replay_workflows` / `replay_workflow` API.
  - Temporal docs: `https://docs.temporal.io/workflows#deterministic-constraints`.
- **Sibling stories:**
  - `S5-02-vuln-remediation-workflow.md` — records its own happy-path fixture; this story extends with HITL + stale-resume.
  - `S5-03-freshness-window-resume.md` — produces the stale-resume fixture; this story matrix-replays it.
  - `S5-04-multi-plugin-parent-workflow.md` — produces the parent happy-path fixture; this story matrix-replays it.
  - `S8-01-kill-worker-resume.md` — the G1 durability test consumes the same workflow code; this story's replay-determinism is the build-time guarantee that S8-01's runtime resume works.
- **Existing CI:** `.github/workflows/*.yml` (or equivalent CI config) — extend the matrix.

## Goal

Ship `tests/workflows/test_replay_determinism.py` that runs `temporalio.testing.WorkflowReplayer.run_replay_workflows(...)` against committed fixture histories (`tests/golden/temporal/*.json`) for `VulnRemediationWorkflow` and `MultiPluginParentWorkflow` across all four covered code paths (happy path, HITL pause-resume, stale-resume tier-descent, multi-plugin parent happy path), per Python-minor matrix (3.11 + 3.12). On `NondeterminismError`, the test preserves the full upstream payload in the test output (no `except: pass`) and CI uploads the recorded-vs-replayed history diff as an artifact. A `make record-replay-fixtures` target regenerates all fixture histories deliberately; commit hash of the generating revision is embedded in each fixture's metadata.

## Acceptance criteria

### A — Test file + matrix wiring

- [ ] **AC-A1** `tests/workflows/test_replay_determinism.py` exists. Module docstring cites ADR-0004 and explains "this is layer 3 of the determinism three-layer fence; if this fails, treat as real signal — do NOT mark flaky."
- [ ] **AC-A2** Test parameterizes over the four fixture histories (`vuln_remediation_happy_path.json`, `vuln_remediation_hitl_pause_resume.json`, `vuln_remediation_stale_resume.json`, `multi_plugin_parent_happy_path.json`) via `@pytest.mark.parametrize("fixture_name", [...])`. Each fixture is read from `tests/golden/temporal/`.
- [ ] **AC-A3** CI matrix: `python-version: ["3.11", "3.12"]` in `.github/workflows/test.yml` (or repo's CI config); the replay-determinism test runs once per Python minor. (Test asserts `sys.version_info[:2] in {(3, 11), (3, 12)}` and prints the version; the matrix wires both.)
- [ ] **AC-A4** Test is NOT decorated with `@pytest.mark.flaky`, `@pytest.mark.skip`, `@pytest.mark.xfail`, or any conditional-skip. A code-search/lint check verifies. If a future contributor adds a flake marker, the lint catches and fails CI.

### B — `WorkflowReplayer` invocation

- [ ] **AC-B1** For each fixture, the test invokes `temporalio.testing.WorkflowReplayer(workflows=[VulnRemediationWorkflow, MultiPluginParentWorkflow]).replay_workflow(history)` (or `run_replay_workflows([history])` per upstream's current API). Uses the Temporal SDK pinned in `pyproject.toml`.
- [ ] **AC-B2** Replay-success criterion: `replay_workflow(history)` returns without raising `NondeterminismError`. The test does NOT swallow the exception; if raised, the full payload (recorded events vs replayed events diff) propagates to pytest output.
- [ ] **AC-B3** On replay failure, the test writes the `NondeterminismError` payload (or equivalent diff representation) to `tests/_replay_artifacts/{fixture_name}-{python_version}-{commit_sha}.txt` *before* re-raising — CI uploads this directory as an artifact. (Or: use pytest's `caplog` + the `--tb=long` default to surface in CI logs.)

### C — Fixture history files

- [ ] **AC-C1** `tests/golden/temporal/vuln_remediation_happy_path.json` exists (recorded by S5-02's `make record-replay-fixture`; this story does NOT re-record it).
- [ ] **AC-C2** `tests/golden/temporal/vuln_remediation_hitl_pause_resume.json` exists — recorded by this story via `make record-replay-fixtures` against `VulnRemediationWorkflow` driven through the HITL-park-resume path (`AwaitingHumanReview → human_review_decision(Approved) → Completed`).
- [ ] **AC-C3** `tests/golden/temporal/vuln_remediation_stale_resume.json` exists — recorded by S5-03's fixture step; this story matrix-replays it. (If S5-03's executor has not yet shipped the fixture, this story records it from the same workflow code.)
- [ ] **AC-C4** `tests/golden/temporal/multi_plugin_parent_happy_path.json` exists (recorded by S5-04; this story matrix-replays it).
- [ ] **AC-C5** Each fixture file has a metadata header (top-level JSON field `_metadata`) containing `{"recorded_at": ISO-8601, "recorded_by_commit": "<sha>", "temporal_sdk_version": "<pinned>", "python_version": "3.11.x", "workflow_class": "VulnRemediationWorkflow"}`. Test asserts the metadata is present and `temporal_sdk_version` matches the current `pyproject.toml` pin (mismatch suggests an SDK bump — regenerate fixtures intentionally).

### D — Fixture regeneration ceremony

- [ ] **AC-D1** `Makefile` target `record-replay-fixtures` runs all four recording paths (one per fixture); writes JSON files to `tests/golden/temporal/`; updates the `_metadata` block. The target is **NOT** wired into `make check` or `make test` — fixtures are regenerated deliberately, not on every test run.
- [ ] **AC-D2** Recording uses `WorkflowEnvironment.start_local()` (in-process Temporal); spins up the workflow with mocked activities returning canned outputs; calls `await handle.fetch_history()`; serializes via the upstream-provided JSON dump path; writes to disk.
- [ ] **AC-D3** Re-running `make record-replay-fixtures` against an unchanged workflow body produces byte-identical fixture files except for the `_metadata.recorded_at` and `_metadata.recorded_by_commit` fields. (Mutation-resistance: re-recording is idempotent on content; metadata is the only churn.)
- [ ] **AC-D4** Documentation at `docs/development.md` (Step 8's `S8-06` augments this) describes when to regenerate: (a) intentional workflow body change → regenerate, commit fixture; (b) SDK pin bump → regenerate, commit fixture; (c) "test is flaking on a PR I didn't touch" → DO NOT regenerate; investigate the upstream-version drift.

### E — Determinism on the per-Python-minor matrix

- [ ] **AC-E1** All four fixtures replay-success on Python 3.11.x (matrix leg 1).
- [ ] **AC-E2** All four fixtures replay-success on Python 3.12.x (matrix leg 2).
- [ ] **AC-E3** A deliberate non-determinism violation injected into `vuln_remediation.py` (e.g., adding `if random.random() < 0.5:` to a workflow body branch — caught earlier by AST fence in S1-07, but for this AC's purposes the implementer uses a `force_violate=True` flag on a forked branch) causes the matrix to fail on at least one Python minor with a `NondeterminismError` payload that names the offending diff. (This AC is verified once in a CI dry-run; the violation is NOT committed.)

### F — Forensic-diff preservation (risk #1 mitigation)

- [ ] **AC-F1** On `NondeterminismError`, the recorded event sequence and the replayed event sequence are both visible in pytest output (no `except NondeterminismError: assert False`-style swallowing). Use `repr(exc)` or the SDK's built-in formatter; do not custom-format.
- [ ] **AC-F2** CI uploads `tests/_replay_artifacts/` as a workflow artifact on test-failure (`.github/workflows/*.yml` `upload-artifact` step). Artifact retention ≥ 14 days so a flake retry can be diffed against the original failure.
- [ ] **AC-F3** Test failure message explicitly mentions: "This is NOT a flake. See ADR-0004 §Risks and `docs/development.md §replay-determinism`. Do NOT mark @pytest.mark.flaky."

### G — Lint-against-flake-markers

- [ ] **AC-G1** `tests/fence/test_no_flake_marker_on_replay.py` — greps `tests/workflows/test_replay_determinism.py` for `@pytest.mark.flaky`, `@pytest.mark.skip`, `@pytest.mark.xfail`, `pytest.skip(`, `pytest.xfail(`. Zero matches. Build break on any.
- [ ] **AC-G2** Same fence-grep against `tests/golden/temporal/*.json` for any `_skip_replay: true` flag (in case a contributor invents an opt-out mechanism). Zero matches.

### H — SDK pin enforcement

- [ ] **AC-H1** `pyproject.toml` pins `temporalio == <pinned-version>` (exact pin — patch level included; replay-history-format stability requires it). A fence test (`tests/fence/test_temporal_sdk_pin.py`) asserts the importable version matches the pin.
- [ ] **AC-H2** SDK pin bump regenerates fixtures (per AC-D4); the regeneration is committed alongside the pin bump in the same PR — never split across PRs.

### I — Gates

- [ ] **AC-I1** `ruff format`, `ruff check`, `mypy --strict tests/workflows/test_replay_determinism.py` clean.
- [ ] **AC-I2** `make test` (without `-m bench`) runs the replay matrix on the *current* host's Python minor; CI runs both legs. Wall-clock per leg ≤ 60 s for the four fixtures combined.

## Implementation outline

1. **Write `tests/workflows/test_replay_determinism.py`.**
   - One parametrized test function: `@pytest.mark.parametrize("fixture_name", ["vuln_remediation_happy_path", "vuln_remediation_hitl_pause_resume", "vuln_remediation_stale_resume", "multi_plugin_parent_happy_path"]) async def test_workflow_history_replays_clean(fixture_name): ...`.
   - Body: read the JSON; parse via `temporalio.client.WorkflowHistory.from_json(...)` (or equivalent upstream API); instantiate `WorkflowReplayer(workflows=[VulnRemediationWorkflow, MultiPluginParentWorkflow])`; call `await replayer.replay_workflow(history)`; on `NondeterminismError`, write the payload to `tests/_replay_artifacts/{fixture_name}-py{sys.version_info[0]}{sys.version_info[1]}.txt` and re-raise.
   - Module-level note: "This test is layer 3 of the three-layer determinism fence (ADR-0004). Do NOT mark flaky."
2. **Write `tests/fence/test_no_flake_marker_on_replay.py`.**
   - AST + grep walk over `test_replay_determinism.py`; assert absence of flake markers.
3. **Write `tests/fence/test_temporal_sdk_pin.py`.**
   - `importlib.metadata.version("temporalio")` matches the `pyproject.toml` pin (parse via `tomllib`).
4. **Add `Makefile` target `record-replay-fixtures`.**
   - Shell out (in-process is fine since pytest is the runner) to a recording script `scripts/record_replay_fixtures.py` that:
     - For each of the four paths, spins `WorkflowEnvironment.start_local()`, registers the workflow + mocked activities, drives the workflow, fetches the history, dumps to JSON with the `_metadata` header.
     - Each path is a function: `record_vuln_remediation_happy_path()`, etc.
     - The script is NOT a test; it's an artifact-producing utility. Runs only when `make record-replay-fixtures` is invoked.
5. **Wire CI matrix.**
   - `.github/workflows/test.yml` (or equivalent) — add `strategy.matrix.python-version: ["3.11", "3.12"]` to the test job. `setup-python` action with the matrix value; `make check` runs.
   - Add `upload-artifact` step on test-failure for `tests/_replay_artifacts/`.
6. **Add `docs/development.md` paragraph.**
   - Section "Replay-determinism fence — when (not) to regenerate fixtures." Covers the three cases from AC-D4. S8-06 publishes this.
7. **Commit initial fixtures.**
   - Run `make record-replay-fixtures` once; commit the four JSON files. Note the `recorded_by_commit` SHA is the *previous* HEAD before this commit lands; that's fine — the metadata is informational.

## TDD plan — red / green / refactor

### Red

**Test file: `tests/workflows/test_replay_determinism.py`**

```python
import json
import sys
from pathlib import Path
import pytest
from temporalio.testing import WorkflowReplayer
from codegenie.durable.workflows.vuln_remediation import VulnRemediationWorkflow
from codegenie.durable.workflows.multi_plugin_parent import MultiPluginParentWorkflow

FIXTURES = [
    "vuln_remediation_happy_path",
    "vuln_remediation_hitl_pause_resume",
    "vuln_remediation_stale_resume",
    "multi_plugin_parent_happy_path",
]

@pytest.mark.parametrize("fixture_name", FIXTURES)
async def test_workflow_history_replays_clean(fixture_name: str):
    """
    Layer 3 of the determinism three-layer fence (ADR-0004).
    On NondeterminismError, the test re-raises with the full upstream payload preserved.
    Do NOT mark @pytest.mark.flaky. See docs/development.md §replay-determinism.
    """
    fixture_path = Path("tests/golden/temporal") / f"{fixture_name}.json"
    raw = json.loads(fixture_path.read_text())
    metadata = raw.pop("_metadata")
    history = raw  # rest is the history payload

    replayer = WorkflowReplayer(workflows=[VulnRemediationWorkflow, MultiPluginParentWorkflow])
    try:
        await replayer.replay_workflow(history)
    except Exception as exc:
        artifact_path = Path("tests/_replay_artifacts") / f"{fixture_name}-py{sys.version_info[0]}{sys.version_info[1]}.txt"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(f"{type(exc).__name__}: {exc!r}\n\nRecorded by: {metadata.get('recorded_by_commit', 'unknown')}\nSDK version: {metadata.get('temporal_sdk_version', 'unknown')}\n")
        raise
```

**Test file: `tests/fence/test_no_flake_marker_on_replay.py`**

```python
from pathlib import Path
import ast

REPLAY_TEST = Path("tests/workflows/test_replay_determinism.py")

def test_no_flake_skip_xfail_markers():
    src = REPLAY_TEST.read_text()
    for forbidden in ["@pytest.mark.flaky", "@pytest.mark.skip", "@pytest.mark.xfail",
                      "pytest.skip(", "pytest.xfail(", "pytestmark = pytest.mark.flaky"]:
        assert forbidden not in src, f"Forbidden marker found in {REPLAY_TEST}: {forbidden}"

def test_no_replay_skip_in_fixtures():
    for fix in Path("tests/golden/temporal").glob("*.json"):
        text = fix.read_text()
        assert '"_skip_replay": true' not in text, f"Forbidden skip flag in fixture {fix}"
```

**Test file: `tests/fence/test_temporal_sdk_pin.py`**

```python
from importlib.metadata import version
import tomllib
from pathlib import Path

def test_temporalio_version_matches_pin():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    deps = pyproject["project"]["dependencies"]
    pin_line = next(d for d in deps if d.startswith("temporalio"))
    pinned = pin_line.split("==")[1].strip()
    assert version("temporalio") == pinned, \
        f"Temporal SDK pin drift: {version('temporalio')} vs {pinned}. Replay-fixture format may have changed."
```

**Test file: `tests/workflows/test_replay_deliberate_violation.py`** (manual ceremony — NOT in CI by default)

```python
@pytest.mark.skip(reason="manual ceremony — uncomment to verify AC-E3")
async def test_deliberate_violation_fails_matrix():
    """One-off: inject random.random() into a workflow branch; assert WorkflowReplayer fires."""
    ...
```

### Green

1. Run `make record-replay-fixtures` to produce the four JSON files.
2. Commit fixtures.
3. Implement `test_replay_determinism.py` per outline.
4. Wire CI matrix.

### Refactor

- Extract the `tests/_replay_artifacts/` artifact-writing block into a `pytest` plugin hook (`conftest.py` `pytest_runtest_makereport`) so any test that raises `NondeterminismError` automatically dumps the artifact. Keeps the test file thin.
- Document the recording-script's API contract (`record_*` functions) in a module docstring; future stories adding new workflows add one `record_*` function + one entry in `FIXTURES`.

## Files to touch

| Path | Why |
|---|---|
| `tests/workflows/test_replay_determinism.py` | The matrix replay test |
| `tests/fence/test_no_flake_marker_on_replay.py` | Anti-flake-marker fence |
| `tests/fence/test_temporal_sdk_pin.py` | SDK version-pin fence |
| `tests/workflows/test_replay_deliberate_violation.py` | Manual ceremony — verifies AC-E3 |
| `tests/golden/temporal/vuln_remediation_hitl_pause_resume.json` | HITL fixture (recorded here) |
| `tests/golden/temporal/vuln_remediation_stale_resume.json` | Stale-resume fixture (recorded here or in S5-03) |
| `scripts/record_replay_fixtures.py` | Fixture-recording utility |
| `Makefile` | `record-replay-fixtures` target |
| `.github/workflows/test.yml` (or equivalent) | Per-Python-minor matrix + artifact upload |
| `docs/development.md` | "When (not) to regenerate fixtures" paragraph (S8-06 publishes) |

## Out of scope

- **Replay against `MultiPluginParentWorkflow.coordination_policy in {"all_or_nothing", "best_effort"}`.** Those raise `NotImplementedError` in Phase 9 (S5-04); replay of a failure path is Phase-10 work.
- **Replay against a real Postgres-backed `PostgresCheckpointerAdapter` history.** Replay is about the workflow body, not the activity body; `run_vuln_subgraph`'s checkpointer state is opaque to replay (the activity result is what Temporal records).
- **Per-Python-patch matrix.** 3.11.x and 3.12.x leg per minor; the patch level is whatever `actions/setup-python` resolves. Phase 16 may pin patch.
- **`temporal` server-version matrix.** Phase 9 ships `temporalio/auto-setup:1.25` (S2-01); the replay test uses `WorkflowEnvironment.start_local()` which is in-process and uses the SDK's pinned server impl. Server upgrades land in Phase 16.
- **Replay artifact retention policy.** AC-F2 sets `≥ 14 days`; tuning is operational.
- **Property-based fuzzing of workflow histories.** A Hypothesis-driven random-history generator could surface latent non-determinism — but the fixture-based approach is the canonical layer-3 fence per ADR-0004. Phase 13 may add a fuzzer additively.

## Notes for the implementer

- **Do NOT mark this test flaky. Read the risk paragraph in `High-level-impl.md` before you touch it.** When this test fails on a PR that did not touch `codegenie.durable.workflows/`, the contributor's instinct is "infra flake; re-run." That instinct is *wrong*. The likely cause is upstream-version drift (LangGraph, Python minor) introducing a transitive non-determinism. The fix is to investigate, not to retry.
- **Preserve the full `NondeterminismError` payload.** Temporal SDK formats the recorded-vs-replayed event diff inside the exception. Do NOT catch-and-summarize — re-raise verbatim. The CI artifact preserves the same payload for post-merge forensics.
- **Fixture regeneration is a deliberate ceremony.** `make record-replay-fixtures` is NOT wired into `make test`. Regeneration happens when (a) the workflow body intentionally changes (and the change is reviewed in the same PR), or (b) the Temporal SDK pin bumps (with intentional acknowledgment of the version-format change). It does NOT happen as a fix for a flaky CI run.
- **The per-Python-minor matrix is the canonical drift-detector.** dict-ordering and asyncio scheduling have changed between 3.11 and 3.12 in subtle ways; running both detects drift before production. If a future Phase pins a single Python minor, this matrix shrinks — but as long as the repo supports 3.11+3.12, the matrix runs.
- **The fixture `_metadata` header is informational, not contractual.** The test reads `_metadata.temporal_sdk_version` for human-readable failure messages, but doesn't enforce equality against the live pin (the SDK-pin fence does that separately). Keeps the test code focused on replay-success.
- **`tests/_replay_artifacts/` is ephemeral.** It's `.gitignore`'d (verify: add `tests/_replay_artifacts/` to `.gitignore` if not present). CI uploads it on failure; locally, it's a scratch directory.
- **The deliberate-violation test (`test_replay_deliberate_violation.py`) is a manual ceremony.** It's checked in but `@pytest.mark.skip`'d by default. The implementer runs it once before shipping (uncomments, injects a violation, observes the matrix failure, captures the output, reverts, commits with `_attempts/S5-05.md` evidence). This is AC-E3's verification.
- **CI matrix wiring is YAML — surgical edits.** Don't refactor the whole CI config; add the `python-version` matrix to the test job; add the artifact-upload step on failure. Match the repo's existing `actions/setup-python@vX` shape.
- **`record_replay_fixtures.py` script lives in `scripts/`, not `tests/`.** It's a tool, not a test. The `Makefile` invokes it directly.
- **Fixture file format follows upstream.** Whatever `WorkflowHistory.to_json()` or equivalent produces is the canonical shape; the `_metadata` block is a top-level addition (sibling to the history payload). On read, pop `_metadata` before passing to `WorkflowReplayer`.
- **Time-skipping inside fixture recording.** The HITL fixture spans a `wait_condition(human_review_decision)` — use `WorkflowEnvironment.start_local()` time-skipping (`env.sleep(...)`) to send the signal without waiting real wall-clock time. The fixture records the signal event correctly.
- **Stale-resume fixture coordination with S5-03.** If S5-03 ships first and produces the fixture, this story matrix-replays it. If S5-05 ships first, this story records the fixture (drives the workflow with mocked stale `RouteDecision`) and S5-03 consumes the same fixture in its own replay-safety test. Coordinate via the validator if order ambiguity.
- **Deferred design opportunities** (record in attempt log): (a) Hypothesis-fuzzer for workflow histories — Phase 13 observability work; (b) automated `temporalio` version-bump PR with auto-regenerated fixtures — Phase 16 supply-chain; (c) artifact retention beyond 14 days — operational tuning.
