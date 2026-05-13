# Story S10-02 — Layer-8 E2E `codegenie loop run` against `cve-fixture`

**Step:** Step 10 — Adversarial hardening + Layer-8 E2E + final polish
**Status:** Ready
**Effort:** M
**Depends on:** S10-01
**ADRs honored:** ADR-0001 (lazy-singleton factory — exercised by the cold-start of the E2E), ADR-0006 (per-workflow checkpointer file — the E2E writes one), ADR-0009 (`cli/loop.py` ships parallel to `cli/remediate.py` — the E2E is the umbrella check that the parallel CLI exists and works), ADR-0010 (`GateRunner.run_one` public promotion is the only Phase 5 source touch — the E2E re-validates Phase 5 parity end-to-end)

## Context

This is the umbrella exit-criterion test for **G1** ("the vuln-remediation loop runs as a LangGraph state machine"). It runs the entire `codegenie loop run` CLI against the real Phase-3 `cve-fixture` Node.js repo, end-to-end, with the real Phase 3 / 4 / 5 engines (VCR'd LLM cassettes), the real `AuditedSqliteSaver`, the real per-workflow SQLite checkpointer, and the real BLAKE3 audit-chain extension into Phase 5.

It is Layer-8 in the test pyramid (arch §Test pyramid line 1166): ~120 s wall-clock, `@pytest.mark.slow`, runs on the **`main` merge queue only** — not on every PR (cost mitigation, arch §CI gates line 1204). Every earlier story has been moving toward this: Steps 1–5 build the graph, Step 6 ships the CLI, Step 7 verifies HITL and Phase-5 parity at the integration layer, Step 8 verifies replay-after-kill, Step 9 measures perf. **This story is the test that says "the whole thing works."**

The test is deliberately tiny in test LOC: subprocess-spawn the CLI, wait, assert exit code 0, assert `report.json` exists and parses, assert key artifacts under `.codegenie/loop/` look right. Every load-bearing component is exercised transitively; this story does not duplicate any inner assertion that lower layers already cover.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Test pyramid` (line 1166) — defines Layer 8 (`@pytest.mark.slow`, ~120 s budget).
  - `../phase-arch-design.md §Fixture portfolio` (lines 1187–1194) — `tests/fixtures/repos/cve-fixture/` is the Phase-3 fixture, reused unchanged.
  - `../phase-arch-design.md §CI gates` (line 1204) — Layer 8 runs on `main` merge queue only.
  - `../phase-arch-design.md §Process view — Scenario 1 (happy path)` (lines 380–420) — the exact node sequence the E2E must traverse: `ingest_cve → select_recipe → apply_recipe → validate_in_sandbox → record_attempt → emit_artifact`.
- **Phase ADRs:**
  - `../ADRs/0009-cli-loop-ships-parallel-to-cli-remediate.md` — the E2E is the umbrella canary that the parallel CLI exists and `cli/remediate.py` is untouched.
  - `../ADRs/0006-audited-sqlite-saver-per-workflow-fsync.md` — the E2E writes a real per-workflow SQLite file; the test asserts the file mode is `0o600`.
- **High-level-impl:**
  - `../High-level-impl.md §Step 10 — Features delivered` — names the test file path and CLI invocation literally.
- **Existing fixtures (must not duplicate):**
  - `tests/fixtures/repos/cve-fixture/` — Phase 3's Node.js fixture (the README inside should list `CVE-2024-FAKE-NPM` as the seeded vuln).
  - `tests/fixtures/cassettes/cve_fixture_3retries/cassette-attempt-{1,2,3}.yaml` — VCR cassettes (arch §Fixture portfolio line 1194), needed only if the E2E ends up hitting the LLM fallback path; happy path should not.
- **CLI surface:**
  - `src/codegenie/cli/loop.py` — `loop run` subcommand (S6-02). The E2E spawns this; do not import it directly.
- **CI hooks:**
  - `.github/workflows/` (or wherever Phase 0 lands CI) — the merge-queue workflow must be wired to run `pytest -m slow`. If the workflow doesn't exist yet, this story creates it.

## Goal

`tests/e2e/test_loop_run_vuln_remediation.py` exists, is decorated `@pytest.mark.slow`, spawns `codegenie loop run ./tests/fixtures/repos/cve-fixture/ --cve CVE-2024-FAKE-NPM` as a subprocess, waits for completion, asserts exit code `0`, asserts a `report.json` was written, and asserts the per-workflow `.sqlite3` checkpoint exists at `0o600`. The test is wired into the merge-queue CI run (not the per-PR run).

## Acceptance criteria

- [ ] `tests/e2e/__init__.py` exists (empty package marker).
- [ ] `tests/e2e/test_loop_run_vuln_remediation.py` exists and contains a test that:
  - [ ] Is decorated `@pytest.mark.slow` (arch §Test pyramid line 1166).
  - [ ] Spawns the CLI as a subprocess: `subprocess.run([sys.executable, "-m", "codegenie", "loop", "run", str(fixture_repo), "--cve", "CVE-2024-FAKE-NPM"], ...)` — uses `python -m codegenie` rather than relying on a console-script entry point, so the test runs against the **source tree** under `pip install -e .` and not a stale globally-installed wheel.
  - [ ] Copies the fixture repo to a `tmp_path` so the E2E does not mutate `tests/fixtures/repos/cve-fixture/` (Phase 3's fixture must remain reusable).
  - [ ] Captures stdout + stderr; on non-zero exit, prints both to ease CI diagnosis.
  - [ ] Asserts `result.returncode == 0` (exit code 0 = happy path per S6-02's exit-code parametrization).
  - [ ] Asserts `(repo_copy / ".codegenie" / "loop" / "report.json").exists()` and that the JSON parses.
  - [ ] Asserts the report contains the expected top-level keys at minimum: `cve_id == "CVE-2024-FAKE-NPM"`, `final_state` matches one of `"resolved"|"emitted"` (whatever S4-09's `emit_artifact` writes — read the story before guessing), `patch_blake3` is a 64-char hex string.
  - [ ] Asserts the per-workflow checkpoint file exists at `(repo_copy / ".codegenie" / "loop" / "checkpoints" / f"{workflow_id}.sqlite3")` and that `stat.S_IMODE(...) == 0o600`.
  - [ ] Computes `workflow_id` the same way `cli/loop.py` does (S6-01: `blake3(f"{repo_root_blake3}|{advisory_canonical_id}").hexdigest()[:16]`) and asserts the on-disk path matches — proves the content-addressing seam works under real I/O.
  - [ ] Has a generous but bounded timeout (`subprocess.run(..., timeout=300)`); on timeout, the test fails with the captured partial stdout/stderr.
- [ ] The test does **not** require network access — VCR cassettes (if used) are committed under `tests/fixtures/cassettes/cve_fixture_3retries/`; otherwise the happy path skips Phase 4 entirely and no cassette is needed.
- [ ] The test completes in ≤ 180 s on a clean Mac/Linux dev machine; if it consistently exceeds 240 s, surface as a Step-9-style perf regression rather than `# flaky-skip`-ing.
- [ ] CI wiring: the merge-queue workflow runs `pytest -m slow tests/e2e/`. If a workflow file already runs `-m slow`, no edit needed; otherwise this story adds the one-liner.
- [ ] The per-PR workflow runs `pytest -m "not slow"` (so the E2E does **not** run on every PR) — assert this is already the case in `.github/workflows/`; if not, surface as a separate follow-up (do not bundle the per-PR workflow edit into this story).
- [ ] `cli/remediate.py` is byte-identical to its pre-Phase-6 state — the E2E does **not** invoke `cli/remediate.py` and the test does not import it (this is the umbrella check on ADR-0009 + Phase 7 exit-criterion "no Phase 0–6 source touched"; a `git diff src/codegenie/cli/remediate.py` against the merge-base must be empty at PR time, verified manually or via a small in-test `git` shell-out if the story wants belt-and-braces).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check tests/e2e/`, `ruff format --check tests/e2e/`, `mypy --strict tests/e2e/`, and `pytest tests/e2e/ -m slow` all pass on a clean run.

## Implementation outline

1. **Read `src/codegenie/cli/loop.py` (S6-02) end-to-end** before writing the test. Confirm the exact `--cve` flag name, the exit-code semantics, and the on-disk path the CLI writes `report.json` to. The arch design says `.codegenie/loop/report.json`; verify against S6-02's implementation rather than the design.
2. Confirm `tests/fixtures/repos/cve-fixture/` contains the expected vulnerability — open its `package.json` / lockfile and confirm `CVE-2024-FAKE-NPM` is one of the seeded advisories Phase 3's `AdvisoryLoader` resolves. If not, **stop** and surface; Phase 3's fixture is the canonical source.
3. Read the existing per-PR workflow under `.github/workflows/` (or `.gitlab-ci.yml`, depending on Phase 0's choice). Confirm it runs `pytest -m "not slow"` or equivalent. If the marker filter is missing, the per-PR run will silently include the E2E and blow the cost mitigation; surface and fix in a one-line edit, not a follow-up.
4. Create `tests/e2e/__init__.py`.
5. Write `tests/e2e/test_loop_run_vuln_remediation.py`:
   - Copy fixture repo to `tmp_path` via `shutil.copytree` (deep copy, follow_symlinks=False).
   - Compute `workflow_id` using the same content-addressing formula `cli/loop.py` uses.
   - Spawn the subprocess with `capture_output=True, text=True, timeout=300`.
   - Assert exit code, JSON shape, file mode, workflow-id-derived path.
6. Register the `slow` pytest marker in `pyproject.toml` if not already present from an earlier story.
7. Update the merge-queue CI workflow to run `pytest -m slow tests/e2e/`. If a separate `.github/workflows/merge-queue.yml` (or similar) doesn't exist yet, add one — keep it minimal, defer to the project's existing patterns.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/e2e/test_loop_run_vuln_remediation.py`

```python
"""Layer-8 E2E: codegenie loop run on cve-fixture.

This is the umbrella exit-criterion test for G1 (arch §Goals).
It is intentionally minimal — every inner invariant has its own
lower-layer test. What this test exclusively pins is:

  - The CLI entry point is reachable as `python -m codegenie loop run`.
  - The full Phase 3/4/5 pipeline runs to completion on a real repo.
  - `report.json` lands at the contract-documented path.
  - The per-workflow checkpoint exists at 0o600 (ADR-0006).
  - The workflow-id content-addressing seam works under real I/O.

It runs on the merge queue only (`@pytest.mark.slow`), per arch §CI gates.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from blake3 import blake3


FIXTURE_REPO = Path(__file__).parents[1] / "fixtures" / "repos" / "cve-fixture"
CVE_ID = "CVE-2024-FAKE-NPM"


def _compute_workflow_id(repo_root: Path, cve_id: str) -> str:
    """Mirror cli/loop.py's workflow-id formula (S6-01).

    If S6-01 changes the formula, this helper drifts and the test fails
    with a clear pointer to the seam — preferable to silently passing
    against a stale path.
    """
    repo_root_blake3 = blake3(str(repo_root.resolve()).encode("utf-8")).hexdigest()
    composite = f"{repo_root_blake3}|{cve_id}"
    return blake3(composite.encode("utf-8")).hexdigest()[:16]


@pytest.mark.slow
def test_codegenie_loop_run_completes_on_cve_fixture(tmp_path: Path) -> None:
    # Copy the fixture so we don't mutate the Phase-3 source-of-truth repo.
    repo = tmp_path / "cve-fixture"
    shutil.copytree(FIXTURE_REPO, repo, symlinks=False)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "codegenie",
            "loop",
            "run",
            str(repo),
            "--cve",
            CVE_ID,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        # Surface stdout + stderr loudly — CI logs become the debugger.
        print("---- STDOUT ----")
        print(result.stdout)
        print("---- STDERR ----")
        print(result.stderr)

    assert result.returncode == 0, f"loop run exited {result.returncode}"

    report_path = repo / ".codegenie" / "loop" / "report.json"
    assert report_path.exists(), f"missing {report_path}"

    report = json.loads(report_path.read_text())
    assert report["cve_id"] == CVE_ID
    assert report["final_state"] in {"resolved", "emitted"}, report["final_state"]
    assert isinstance(report.get("patch_blake3"), str) and len(report["patch_blake3"]) == 64

    workflow_id = _compute_workflow_id(repo, CVE_ID)
    checkpoint_path = repo / ".codegenie" / "loop" / "checkpoints" / f"{workflow_id}.sqlite3"
    assert checkpoint_path.exists(), f"missing checkpoint at {checkpoint_path}"
    mode = stat.S_IMODE(checkpoint_path.stat().st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"  # ADR-0006


@pytest.mark.slow
def test_cli_remediate_untouched_by_e2e_run(tmp_path: Path) -> None:
    """ADR-0009 + Phase 7 exit-criterion canary: cli/remediate.py is not invoked.

    If this test ever sees cli/remediate.py in the call graph, ADR-0009 has been
    silently violated and Phase 7's 'no Phase 0–6 source touched' canary is at
    risk.
    """
    repo = tmp_path / "cve-fixture"
    shutil.copytree(FIXTURE_REPO, repo, symlinks=False)

    # Use coverage-style import tracing via -X importtime to confirm
    # cli.remediate is NOT imported by the loop run path.
    result = subprocess.run(
        [
            sys.executable,
            "-X",
            "importtime",
            "-m",
            "codegenie",
            "loop",
            "run",
            str(repo),
            "--cve",
            CVE_ID,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0
    # importtime output goes to stderr.
    assert "codegenie.cli.remediate" not in result.stderr, (
        "cli/remediate.py was imported by loop run — ADR-0009 violation"
    )
```

### Green — make it pass

If S6-02 / S6-01 / S4-09 / S5-01 all landed correctly, this test should pass with no production code changes. The most likely first-time-red causes are:

- **CLI entry point**: if `python -m codegenie` doesn't resolve `loop run`, S6-01 missed registering the Click group at the top-level CLI. Fix in S6-01 follow-up, not here.
- **Workflow-id formula drift**: if the on-disk path doesn't match `_compute_workflow_id`, the formula changed somewhere. Reconcile against S6-01 — don't tweak the test.
- **Report shape**: the `final_state`/`patch_blake3` keys must come from S4-09's `emit_artifact`. If S4-09 emits different keys, update the test to match the *story-documented* shape, not whatever the code happens to produce.

Do **not** patch production code to make the test green if the test exposes a real contract violation — surface it.

### Refactor — clean up

- Cache the fixture copy across the two tests in the file via a module-scope fixture if the wall-clock pressure justifies (likely not; two ~60 s runs are within the 180 s budget for the whole file).
- Confirm the merge-queue CI workflow line reads `pytest -m slow tests/e2e/` (not `pytest -m slow` against the whole tree — would pull in S9's perf nightly accidentally).
- Add a one-liner comment in `tests/e2e/test_loop_run_vuln_remediation.py`'s module docstring that cross-references arch §Test pyramid line 1166 and the G1 exit criterion.

## Files to touch

| Path | Why |
|---|---|
| `tests/e2e/__init__.py` | New — package marker. |
| `tests/e2e/test_loop_run_vuln_remediation.py` | New — the Layer-8 E2E test. |
| `pyproject.toml` | Register `slow` pytest marker if not already from an earlier story. |
| `.github/workflows/merge-queue.yml` (or equivalent) | Wire `pytest -m slow tests/e2e/` into the merge-queue run. |
| `.github/workflows/<per-pr>.yml` | One-line edit only if the per-PR run currently lacks `-m "not slow"`. |

## Out of scope

- **Asserting node-sequence order** — Step 5's topology golden + Step 2/3's state-transition tests already prove the path; Layer 8 is end-to-end-correctness, not a duplicate trace.
- **HITL flow** — happy path doesn't trip HITL; S7-01 owns that.
- **Replay-after-kill** — S8-01.
- **Adversarial paths** — S10-01.
- **Phase 5 byte-parity** — S7-02 owns that integration; the E2E is content-correctness, not byte-byte.
- **ADR commits + Phase 5 regression** — S10-03.

## Notes for the implementer

- **Use `python -m codegenie`, not the `codegenie` console-script.** A stale globally-installed wheel will silently shadow the source tree and produce a green E2E against the *wrong* code. Phase 0's CI runs `pip install -e .` but local dev machines vary.
- The VCR cassettes under `tests/fixtures/cassettes/cve_fixture_3retries/` exist for the **three-retry** parity path (S7-03), not the happy path. The happy path should resolve via Phase 3's recipe matcher without hitting Phase 4 at all. If your E2E run *does* hit Phase 4, either (a) you've selected a CVE that bypasses the recipe (wrong CVE — confirm `CVE-2024-FAKE-NPM` is recipe-resolvable in Phase 3's fixture) or (b) the recipe matcher regressed (Phase 3 bug — surface).
- The `importtime` check in the second test is a belt-and-braces canary. It's slightly brittle (Python may import `codegenie.cli.remediate` transitively via `codegenie.cli.__init__`). If that happens, narrow the check to `from codegenie.cli.remediate` or to a specific function symbol — do not `# noqa` it; that defeats the ADR-0009 canary.
- 300 s subprocess timeout is generous on purpose: a flaky timeout on the merge queue is worse than a slow merge queue. If the E2E genuinely takes > 240 s consistently, raise via the perf-regression channel (Step 9), not by extending the timeout.
- Do **not** assert anything on the BLAKE3 audit-chain contents from this test — the chain has dedicated lower-layer tests (S2-02 + S2-03). The E2E asserts that the chain *file* exists and is at `0600`; chain *content* invariants are not Layer 8's job.
- If a future Phase-6 ADR (e.g., P6-008 from §Gap analysis Gap 1) lands and changes the default `max_attempts`, the happy-path E2E should still pass without `--max-attempts` on the CLI — confirm by running it locally before declaring green.
