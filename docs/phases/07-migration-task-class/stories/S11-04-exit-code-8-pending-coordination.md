# Story S11-04 — Exit-code 8 wiring + integration test

**Step:** Step 11 — `Both` variant emission + `coordination-summary.yaml` writer + `codegenie list-coordination-candidates` CLI
**Status:** Ready
**Effort:** S
**Depends on:** S11-02 (the writer that returns `Applicability.PendingCoordination` — the orchestrator translates this to exit code 8)
**ADRs honored:** Phase 7 ADR-0017 (exit code 8 reserved for "REQUIRES_MULTI_PLUGIN_COORDINATION — awaiting Phase 8 Planner"; documented in CLI `--help`; load-bearing operator contract), Phase 7 ADR-0001 (Phase 7 produces evidence, not coordination — exit code 8 is the operator-facing signal that the workflow is "pending Phase 8," not "failed")

## Context

ADR-0017 is split out from ADR-0001 specifically because the operator-facing CLI contract is independently load-bearing. Operators run `codegenie remediate <repo> --cve <id>`; on a `Both` workflow, the orchestrator's exit code is the single most-observable signal — operator shell scripts, CI matrix workflows, and downstream automation all branch on `$?`. ADR-0017 §Decision §3 reserves exit code **8** for this terminal state: distinct from 0 (success), distinct from 1 (generic failure), distinct from any future "pending X" codes (2–7 are reserved per ADR-0017 §Tradeoffs).

This story is small (S) and intentionally narrow: add the `EXIT_PENDING_COORDINATION = 8` constant to the existing exit-code module, wire the orchestrator to translate `Applicability.PendingCoordination` to that exit code at the CLI boundary, document it in `codegenie remediate --help`, and prove the full path end-to-end via an integration test that exercises a `Both` workflow and asserts the process exits 8.

Three correctness invariants the story locks: (1) **exit code 8 is reachable only via `PendingCoordination`** — no other path (success, recipe failure, gate failure, unknown provenance) emits 8; the integration test parametrizes other paths and asserts they do NOT exit 8. (2) **The `--help` text names exit code 8 explicitly** — operators discover the taxonomy from the CLI itself, not from external docs. (3) **The exit code is stable across re-runs** — running the same `Both` workflow twice both exits 8; the second run does not "remember" the first and exit 0.

The story respects the existing `src/codegenie/cli/exit_codes.py` (or wherever exit codes are defined — `grep -rn "EXIT_\|exit_code\|sys.exit" src/codegenie/cli/`) discipline. If exit codes are scattered (raw integers in `sys.exit(...)` calls), the story does NOT refactor them — Rule 3 (Surgical Changes) — it adds the new constant in the existing convention's spot and migrates only the `Both`-handling path. A separate follow-up can consolidate later.

The integration test `tests/integration/test_both_exits_with_code_8.py` is full-workflow: invoke the CLI as a subprocess (or via the in-process orchestrator entry point that supports it), feed a fixture that yields a `Both` provenance, assert exit code 8, assert `.codegenie/coordination/<workflow_id>.yaml` exists, assert the spanning log gained one event. This complements S12-03's `tests/e2e/test_both_provenance_emits_coordination_event_e2e.py` (which is the full e2e against a real vulnerable Node fixture under `@pytest.mark.phase07_e2e`); this story's test is a faster integration-level cousin that does not require Docker.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §13` (lines 905–948) — orchestrator translates `Applicability.PendingCoordination` to CLI exit code 8.
  - `../phase-arch-design.md §Scenario C` (lines 455–486) — sequence: `emit_coordination` returns `PendingCoordination` → orchestrator → CLI exit 8.
  - `../phase-arch-design.md §Goals §9` (line 28) — "Emits typed `RequiresMultiPluginCoordination` event + exit code 8 + `coordination-summary.yaml`."
- **Phase ADRs:**
  - `../ADRs/0017-both-provenance-exits-code-8-with-coordination-summary.md §Decision §3` — exit code 8 reserved across the project; §Tradeoffs (lines 38–42) — "exit code 8 becomes a reserved value … future task classes that want their own 'pending X' exit code must coordinate with this allocation"; §Consequences (line 50) — `Code.REQUIRES_MULTI_PLUGIN_COORDINATION = 8` documented in `--help`.
  - `../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md §Consequences` — CLI exit code 8 is reserved for "requires multi-plugin coordination — awaiting Phase 8 Planner"; documented in CLI help text and pinned by the e2e test.
- **Existing code:**
  - `src/codegenie/cli/` — locate the existing exit-code module (likely `exit_codes.py` or constants at the bottom of `__init__.py`). If none exists, this story creates `src/codegenie/cli/exit_codes.py` as the canonical home.
  - `src/codegenie/transforms/outcomes.py` (extended in S11-02) — `Applicability.PendingCoordination` variant.
  - Phase 3's `codegenie remediate` subcommand — the entry point that runs the migration plugin's subgraph and observes the `Applicability` return value. The translation `PendingCoordination → exit 8` happens at this boundary.

## Goal

Land `EXIT_PENDING_COORDINATION = 8` in the canonical CLI exit-code module; wire the `codegenie remediate` orchestrator to translate `Applicability.PendingCoordination` to that exit code at process termination; document the exit code in the CLI `--help` epilog; and prove via `tests/integration/test_both_exits_with_code_8.py` that a full workflow with `Both` provenance exits with code 8.

## Acceptance criteria

- [ ] **AC-1 — Constant landed.** `EXIT_PENDING_COORDINATION: Final[int] = 8` exists in `src/codegenie/cli/exit_codes.py` (creating the module if it doesn't yet exist; otherwise inserted in the existing convention's spot). The constant is `Final[int]` per the project's `mypy --strict` discipline; the module's `__all__` includes `"EXIT_PENDING_COORDINATION"`.
- [ ] **AC-2 — Other exit codes preserved.** If `exit_codes.py` already exists with `EXIT_SUCCESS = 0`, `EXIT_GENERIC_FAILURE = 1`, etc., the existing constants are byte-unchanged. The story is additive only.
- [ ] **AC-3 — Codes 2–7 reserved per ADR-0017 §Tradeoffs.** A comment in `exit_codes.py` directly above `EXIT_PENDING_COORDINATION` reserves codes 2–7 for future generic-failure subkinds and names ADR-0017 as the policy source ("`# Codes 2–7 reserved for future generic-failure subkinds; coordinate with ADR-0017 before allocating.`").
- [ ] **AC-4 — Orchestrator translates `PendingCoordination` to exit 8.** The `codegenie remediate` entry-point function (locate via `grep -rn "remediate\|RemediationOrchestrator" src/codegenie/cli/`) `match`-es over the final `Applicability` result; the `PendingCoordination` arm calls `sys.exit(EXIT_PENDING_COORDINATION)` (or returns the int from a `run(args) -> int` shape — match the existing convention).
- [ ] **AC-5 — `mypy --strict` exhaustiveness.** The `match` in AC-4 has an `assert_never(unexpected)` default arm; adding `PendingCoordination` to `Applicability` (S11-02) without updating the orchestrator's match produces a `mypy --strict` error. This story's `mypy` run must be clean; the test in AC-9 covers the runtime path.
- [ ] **AC-6 — `--help` epilog names exit code 8.** Running `codegenie remediate --help` prints a section (e.g., "EXIT CODES:") that includes `8 — REQUIRES_MULTI_PLUGIN_COORDINATION (Both-variant; see codegenie list-coordination-candidates)`. The text is asserted in `test_remediate_help_documents_exit_codes`.
- [ ] **AC-7 — No other exit path emits 8.** Test parametrizes the four other terminal `Applicability` / `RecipeOutcome` / `RemediationOutcome` returns (Applies-success, NotApplies, RecipeNotApplicable, gate-failure) and asserts the exit code is NOT 8 for any of them.
- [ ] **AC-8 — Exit code is stable across re-runs.** Running the same `Both` workflow twice both yields exit 8. The second run's `.codegenie/coordination/<workflow_id>.yaml` overwrites the first (per ADR-0017 §Tradeoffs — `WorkflowId` is per-invocation; if it does collide, the second write replaces).
- [ ] **AC-9 — Integration test landed.** `tests/integration/test_both_exits_with_code_8.py` exercises the full workflow:
  - Constructs a fixture or in-process invocation that yields a `Both` provenance.
  - Invokes the `remediate` entry point.
  - Asserts the exit code is 8.
  - Asserts `.codegenie/coordination/<workflow_id>.yaml` exists.
  - Asserts the spanning log has exactly one `RequiresMultiPluginCoordination` event for that `workflow_id`.
- [ ] **AC-10 — `mypy --strict src/codegenie/cli/exit_codes.py` clean** + `mypy --strict` clean on the edited orchestrator entry point.
- [ ] **AC-11 — `ruff check` + `ruff format --check` clean.**
- [ ] **AC-12 — `make lint-imports` green** (no new LLM-SDK paths through this surface).
- [ ] **AC-13 — Phase 3–6.5 regression suite green** (`make check`); `bench/vuln-remediation/` cassette replay byte-equal — the orchestrator edit must not change Phase 3 behavior.
- [ ] **AC-14 — TDD plan's red test (`test_both_workflow_exits_with_code_8`) exists, was committed in a failing state, is now green.**

## Implementation outline

1. **Locate the existing exit-code convention.**
   ```bash
   grep -rn "EXIT_\|sys.exit\|return.*# exit\|exit_code" src/codegenie/cli/
   ```
   If `src/codegenie/cli/exit_codes.py` exists: add `EXIT_PENDING_COORDINATION = 8` in alphabetical or numeric order (match convention). If only scattered raw integers exist: create `exit_codes.py` with the new constant; do NOT migrate the scattered integers (Rule 3 — Surgical Changes; flag the cleanup for a follow-up).
2. **Add the codes-2–7-reserved comment** directly above `EXIT_PENDING_COORDINATION` per AC-3.
3. **Update `__all__`** if the module declares one.
4. **Locate the `codegenie remediate` entry point.** It is the function that runs the migration plugin's subgraph and observes the `Applicability` return value. Likely `src/codegenie/cli/remediate.py::run(args) -> int` or similar. Read the file first.
5. **Add a `match` over `Applicability`** at the point where the entry point currently translates outcome → exit code. Cases:
   - `Applies(plan=...)` → existing path (success / failure flows via downstream gates).
   - `NotApplies(reason=...)` → existing path (likely `EXIT_GENERIC_FAILURE` or a domain-specific code).
   - `PendingCoordination(workflow_id=..., summary_path=...)` → return / `sys.exit` with `EXIT_PENDING_COORDINATION`. Optionally emit a stderr line: `pending multi-plugin coordination: see {summary_path}` (operator UX; the YAML path tells them where to look).
   - `case _ as unexpected: assert_never(unexpected)` — this is what makes mypy catch a future variant addition.
6. **Update the `--help` epilog** to include an "EXIT CODES:" block per AC-6. Match the existing CLI subcommand idiom; if other subcommands lack exit-code blocks, add one here as the first precedent (and the next CLI cleanup PR can backfill).
7. **Tests** under `tests/integration/`:
   - `test_both_exits_with_code_8.py` — full integration per AC-9.
   - `test_remediate_help_documents_exit_codes.py` (or co-located in the same file) — assert AC-6 text appears in `--help`.
   - `test_other_paths_do_not_exit_8.py` — parametrized over the four other terminal paths per AC-7.
8. **Run `make check`** + the Phase 3 cassette replay.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/test_both_exits_with_code_8.py`

```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from codegenie.cli.exit_codes import EXIT_PENDING_COORDINATION


def test_both_workflow_exits_with_code_8(tmp_path, monkeypatch, both_fixture_factory):
    """AC-9 — full Both workflow exits 8 + writes coordination-summary.yaml."""
    repo = both_fixture_factory(tmp_path)  # fixture under tests/fixtures/portfolio/node-vulnerable-alpine/
    # Run as subprocess to capture true exit code.
    result = subprocess.run(
        [sys.executable, "-m", "codegenie", "remediate", str(repo),
         "--cve", "CVE-2026-0001", "--codegenie-root", str(tmp_path / ".codegenie")],
        capture_output=True, text=True,
    )
    assert result.returncode == EXIT_PENDING_COORDINATION
    assert result.returncode == 8

    # Coordination summary written.
    coord_dir = tmp_path / ".codegenie" / "coordination"
    yaml_files = list(coord_dir.glob("*.yaml"))
    assert len(yaml_files) == 1
    summary = yaml.safe_load(yaml_files[0].read_text())
    assert summary["awaiting"] == "phase_8_planner"
    assert summary["schema_version"] == "phase-7-0"

    # Exactly one spanning event for that workflow.
    spanning_dir = tmp_path / ".codegenie" / "events" / "spanning"
    # ... walk + filter on kind == "requires_multi_plugin_coordination" + workflow_id ...
    assert _count_events(spanning_dir, summary["workflow_id"]) == 1


def test_remediate_help_documents_exit_code_8():
    """AC-6 — `--help` epilog names exit code 8."""
    result = subprocess.run(
        [sys.executable, "-m", "codegenie", "remediate", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "8" in result.stdout
    assert "REQUIRES_MULTI_PLUGIN_COORDINATION" in result.stdout or \
           "multi-plugin coordination" in result.stdout.lower()


@pytest.mark.parametrize("scenario", [
    "success",           # plain successful remediation — exit 0
    "not_applicable",    # NotApplies(reason=PEER_DEP_CONFLICT) — domain code, not 8
    "recipe_failure",    # RecipeOutcome.Failed — domain code, not 8
    "gate_failure",      # post-Applies gate failure — domain code, not 8
])
def test_other_paths_do_not_exit_8(scenario, tmp_path, scenario_fixture_factory):
    """AC-7 — exit 8 reserved solely for PendingCoordination."""
    repo = scenario_fixture_factory(tmp_path, scenario)
    result = subprocess.run(
        [sys.executable, "-m", "codegenie", "remediate", str(repo)],
        capture_output=True, text=True,
    )
    assert result.returncode != EXIT_PENDING_COORDINATION


def test_both_workflow_re_run_still_exits_8(tmp_path, both_fixture_factory):
    """AC-8 — re-running the same Both workflow still exits 8."""
    repo = both_fixture_factory(tmp_path)
    cmd = [sys.executable, "-m", "codegenie", "remediate", str(repo),
           "--cve", "CVE-2026-0001", "--codegenie-root", str(tmp_path / ".codegenie")]
    r1 = subprocess.run(cmd, capture_output=True, text=True)
    r2 = subprocess.run(cmd, capture_output=True, text=True)
    assert r1.returncode == EXIT_PENDING_COORDINATION
    assert r2.returncode == EXIT_PENDING_COORDINATION
```

State why the red tests fail: `ImportError: cannot import name 'EXIT_PENDING_COORDINATION' from 'codegenie.cli.exit_codes'` — constant does not exist; `--help` lacks the exit-code text; the orchestrator does not translate `PendingCoordination` → 8 yet.

### Green — minimal pass

- Land `EXIT_PENDING_COORDINATION = 8` in `src/codegenie/cli/exit_codes.py` (creating module if needed); update `__all__`.
- Edit the `remediate` entry point to `match` over `Applicability` with the four arms + `assert_never`.
- Update the `--help` epilog with the EXIT CODES block.

### Refactor

- Verify the `mypy --strict` exhaustiveness path (delete one `case` arm temporarily, confirm `mypy` errors, restore).
- Verify `make check` clean; verify the `bench/vuln-remediation/` cassette replay byte-equal.
- Add a code comment on the `match` block naming ADR-0017 as the source of the exit-code-8 contract.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli/exit_codes.py` | NEW or EDIT — `EXIT_PENDING_COORDINATION = 8` constant + codes-2–7-reserved comment + `__all__` update. |
| `src/codegenie/cli/remediate.py` (or wherever the entry point lives) | EDIT — `match` over `Applicability` with `PendingCoordination` arm + `assert_never` + `--help` epilog update. |
| `tests/integration/test_both_exits_with_code_8.py` | NEW — full-workflow integration test covering AC-6..AC-9. |
| `tests/fixtures/portfolio/node-vulnerable-alpine/` | CROSS-REF — fixture used (created in S12-01); this story does not create it. If S12-01 hasn't shipped yet when this story runs, this story creates a minimal stub fixture and tags it for S12-01 to subsume. |

## Out of scope

- **Migrating existing scattered `sys.exit(N)` calls to use named constants** — Rule 3 (Surgical Changes). Flag as a follow-up cleanup.
- **Phase 8's Planner consumption of the spanning log** — Phase 8.
- **`tests/e2e/test_both_provenance_emits_coordination_event_e2e.py`** — that's S12-03 (full e2e under `@pytest.mark.phase07_e2e` against a real Node fixture with Docker). This story's integration test is the no-Docker faster cousin.
- **`tests/property/vuln_provenance/test_both_always_emits_coordination.py`** — that's S11-02 (the writer property). This story's tests are integration-level (full process exit).
- **Other phases' exit-code allocations** — codes 2–7 are reserved; allocating them is a future-phase ADR decision.
- **Bulk exit-code documentation for all `codegenie` subcommands** — only `remediate` has the `Both`-path exit code today. Other subcommands' exit-code docs are a separate cleanup.

## Notes for the implementer

- **Read `src/codegenie/cli/` before writing anything.** The exit-code module may already exist; the `remediate` entry point may be wired differently than this story assumes. CLAUDE.md Rule 8 — read before you write. The convention you find is the convention you match (Rule 11), not the convention this story sketches.
- **`sys.exit(int)` vs `return int` from `run(args) -> int`.** If the project's CLI dispatcher uses `run(args) -> int` and a top-level `sys.exit(rc)` in `__main__.py`, return the int from the orchestrator. If the dispatcher calls `sys.exit(...)` directly inside subcommand handlers, do the same. Mixing the two patterns is a code smell — match exactly what the other subcommands do.
- **The `match` exhaustiveness is the load-bearing protection.** If you change the `match` to an `if/elif/else` chain "for clarity," you lose the `mypy --strict` exhaustiveness check. A future PR that adds a fifth `Applicability` variant (say, `RetryNeeded`) and forgets to update the orchestrator would silently fall through to the `else` arm — the `Both`-path UX would degrade or break. Keep the `match` + `assert_never(unexpected)`. (CLAUDE.md Rule 9 — tests verify intent, not just behavior; the mypy exhaustiveness is the type-time test.)
- **Exit code 8 is reserved across the project per ADR-0017 §Tradeoffs.** Future task classes that want their own "pending X" exit code (e.g., "pending human review" for a Phase 12 escalation flow) must coordinate with this allocation — likely 9, 10, or beyond. The comment in `exit_codes.py` (AC-3) is the discoverable policy surface.
- **Integration test fixtures.** S12-01 creates the canonical `tests/fixtures/portfolio/node-vulnerable-alpine/` fixture for the `Both` case. If S12-01 hasn't shipped when this story runs, create a minimal stub fixture (one `package.json` + one `package-lock.json` with the CVE'd dependency + one `Dockerfile FROM alpine:3.18`) and document in the attempt log that S12-01 should subsume it. Do not block on S12-01 — this story's integration test only needs *some* `Both` fixture, not the canonical one.
- **Stderr UX line on `PendingCoordination`.** Per Phase 7 ADR-0017 §Decision (closing notes), the operator-facing experience matters: alongside `sys.exit(8)`, emit a one-line stderr message: `pending multi-plugin coordination: see {summary_path}; run \`codegenie list-coordination-candidates\` to enumerate`. This is the discovery loop into S11-03's CLI. Test asserts the line is present.
- **`bench/vuln-remediation/` cassette replay must remain byte-equal.** This story edits the orchestrator's outcome-translation path. Phase 3's NpmLockfileRecipe workflows (the cassettes) do NOT produce `Both` — they all hit `Applies` and proceed normally. The `match`-block edit therefore does not change Phase 3 behavior; the cassette replay byte-equality is what proves it. If the replay drifts by even one byte, something is wrong — a stray `print(...)`, a changed default exit code on `NotApplies`, a re-ordered match arm with side effects. Bisect immediately.
- **The integration test under `tests/integration/`, not `tests/e2e/`.** Tests under `tests/e2e/` carry `@pytest.mark.phase07_e2e` and require Docker / privileged Linux runners. This story's integration test runs in plain `pytest` — its fixture is in-process / file-only; it does not invoke `docker build` or sandbox. S12-03 ships the Docker-requiring e2e. The two tests verify complementary slices: this one proves "the wiring is correct"; S12-03 proves "the full pipeline reaches this wiring under real Docker conditions."
- **Closest precedent.** Phase 3's `codegenie remediate` outcome → exit-code translation is the structural twin (it likely already exists, mapping `RemediationOutcome.Validated(passed=True)` to 0 and `RemediationOutcome.Failed(...)` to a domain code). This story extends that translation additively; do not refactor it.
