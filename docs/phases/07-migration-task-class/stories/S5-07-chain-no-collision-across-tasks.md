# Story S5-07 — Cross-task chain-no-collision integration test

**Step:** Step 5 — `DistrolessLedger`, `build_distroless_loop()`, `cli/migrate.py`, and Node.js Express E2E
**Status:** Ready
**Effort:** S
**Depends on:** S5-05
**ADRs honored:** ADR-P7-001 (parallel `DistrolessLedger`; per-task directory separation), ADR-P7-005 (parallel CLI verbs; `workflow_id` prefix scheme)

## Context

This story closes `phase-arch-design.md §Gap 1` — the under-specified cross-task chain-head and audit-chain ownership problem. The Phase 6 audit chain is a single file under `.codegenie/remediation/<run-id>/audit/`; Phase 7 puts its chain under `.codegenie/migration/<run-id>/audit/`. The two directories are deliberately separate; the `wf:vuln:` vs `wf:distroless:` workflow-id prefix (S5-05) makes collisions structurally impossible.

But "structurally impossible" is only true if the directory split holds in practice. The test in this story exercises the failure mode directly: it launches *one* `codegenie loop` (vuln) workflow and *one* `codegenie migrate` (distroless) workflow with **intentionally identical `<run-id>`** and asserts the resulting audit chains live in disjoint directories — proving cross-task collisions can't happen by accident or by adversarial run-id reuse.

This is a small but load-bearing story. If it fails, Phase 8's supervisor inherits the worst possible debt: two task classes silently corrupting each other's audit chains.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap 1 — Cross-task chain-head + audit-chain ownership across two ledgers is under-specified` (lines 1403–1407) — the canonical problem statement and the proposed mitigation (`wf:<task>:` prefix + directory split + CI test).
  - `../phase-arch-design.md §Physical view` — `.codegenie/migration/<run-id>/audit/` vs `.codegenie/remediation/<run-id>/audit/`.
  - `../phase-arch-design.md §Component 12 — cli/migrate.py` — `workflow_id = blake3(...|wf:distroless:...)[:16]`.
- **Phase ADRs:**
  - `../ADRs/0011-distroless-ledger-parallel-to-vuln-ledger.md` — ADR-P7-001 — "different directory from vuln checkpoints — same `AuditedSqliteSaver` class, structurally impossible to collide on workflow_id".
  - `../ADRs/0012-parallel-cli-verbs-no-shared-dispatcher.md` — ADR-P7-005 — `wf:distroless:<sha>` prefix differs from `wf:vuln:<sha>`.
- **Source design:**
  - `../final-design.md §Conflict-resolution row 15` (per-task ledger).
- **Existing code:**
  - `src/codegenie/cli/loop.py` (Phase 6) — `wf:vuln:` workflow_id; `.codegenie/remediation/<run-id>/audit/` chain path.
  - `src/codegenie/cli/migrate.py` (S5-05) — `wf:distroless:` workflow_id; `.codegenie/migration/<run-id>/audit/` chain path.
  - `src/codegenie/graph/checkpointer.py` (Phase 6) — `AuditedSqliteSaver` class (single-writer `threading.Lock` per process).

## Goal

Land `tests/integration/test_chain_no_collision_across_tasks.py` proving that one vuln workflow and one distroless workflow with intentionally-identical `<run-id>` produce audit chains in disjoint directories (`.codegenie/remediation/<id>/` vs `.codegenie/migration/<id>/`).

## Acceptance criteria

- [ ] `tests/integration/test_chain_no_collision_across_tasks.py` exists with at least three tests:
  1. `test_chain_directories_disjoint_when_run_id_collides` — launches both workflows with the same `<run-id>` (parametrized via fixture); asserts both directories exist with their own audit chains; asserts no path overlap.
  2. `test_workflow_ids_have_distinct_prefixes_for_same_inputs` — derives workflow_ids for the same `repo + advisory_id` via both CLIs; asserts the prefixes differ (`wf:vuln:` vs `wf:distroless:`) and the resulting BLAKE3-truncated IDs differ.
  3. `test_audit_chain_writes_do_not_cross_directories` — runs both workflows concurrently (or serially with shared fixture); asserts each chain file is written only under its own task directory.
- [ ] The test uses real CLI invocations via `CliRunner` (not subprocess) — same-process is sufficient to catch path collisions.
- [ ] The test asserts directory paths *exactly* — `.codegenie/remediation/<id>/audit/<id>.jsonl` vs `.codegenie/migration/<id>/audit/<id>.jsonl`; the parent directories must not overlap.
- [ ] The test marks itself `@pytest.mark.integration`.
- [ ] `mypy --strict tests/integration/test_chain_no_collision_across_tasks.py` is clean.
- [ ] `ruff check`, `ruff format --check` clean.

## Implementation outline

1. Build a minimal shared fixture: a tmp dir with a git-initialized minimal Express service (the `express_fixture` from S5-06 can be reused) and a vuln-shaped advisory pinned to a CVE that the vuln catalog has a recipe for.
2. In the test, derive a deliberately-shared `<run-id>` (e.g., by passing `--run-id-override` if the CLI supports it, *or* by parametrizing such that the BLAKE3 truncation of distinct inputs happens to collide — easier: just hard-code identical `<run-id>` directory names and let both CLIs use them).
3. Invoke `codegenie loop run <fixture> --cve CVE-2025-XXXX` and `codegenie migrate run <fixture> --target distroless --cve CVE-2025-XXXX` against the same fixture (different commands, possibly same underlying CVE).
4. After both runs (or pauses), assert that `.codegenie/remediation/<run-id>/audit/` and `.codegenie/migration/<run-id>/audit/` *both* exist and contain their own chain files; assert no file lives in both.
5. Add the workflow-id prefix assertion: derive both workflow_ids for identical inputs (`repo`, `cve`) and confirm `wf:vuln:` vs `wf:distroless:` produce distinct BLAKE3 hashes.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/integration/test_chain_no_collision_across_tasks.py`.

```python
from pathlib import Path

import pytest
from click.testing import CliRunner

from codegenie.cli.loop import loop, _derive_workflow_id as derive_vuln_wid
from codegenie.cli.migrate import migrate, _derive_workflow_id as derive_distroless_wid


@pytest.mark.integration
def test_workflow_ids_have_distinct_prefixes_for_same_inputs() -> None:
    """ADR-P7-005 / arch §Gap 1 — wf:vuln: vs wf:distroless: prefixes guarantee distinct ids."""
    repo_blake3 = "a" * 64
    advisory = "CVE-2025-XXXX"
    vuln_wid = derive_vuln_wid(repo_root_blake3=repo_blake3, advisory_canonical_id=advisory)
    distroless_wid = derive_distroless_wid(
        repo_root_blake3=repo_blake3,
        advisory_canonical_id=advisory,
        target_image=None,
    )
    assert vuln_wid != distroless_wid, (
        "Workflow IDs collided across tasks — the wf:<task>: prefix scheme is broken."
    )


@pytest.mark.integration
@pytest.mark.requires_docker
def test_chain_directories_disjoint_when_run_id_collides(
    shared_fixture: Path,
) -> None:
    """Arch §Gap 1 — even if <run-id> collides, audit chains live in disjoint directories."""
    runner = CliRunner()
    # Invoke both CLIs against the same fixture.
    vuln_result = runner.invoke(loop, ["run", str(shared_fixture), "--cve", "CVE-2025-XXXX"])
    distroless_result = runner.invoke(
        migrate, ["run", str(shared_fixture), "--target", "distroless", "--cve", "CVE-2025-XXXX"]
    )
    # Allow either exit 0 (happy) or exit 12 (paused) — what matters is the chain files.
    assert vuln_result.exit_code in (0, 11, 12), f"vuln CLI failed unexpectedly: {vuln_result.output}"
    assert distroless_result.exit_code in (0, 11, 12), f"distroless CLI failed: {distroless_result.output}"

    remediation_dir = shared_fixture / ".codegenie/remediation"
    migration_dir = shared_fixture / ".codegenie/migration"
    assert remediation_dir.exists(), "vuln CLI did not write to .codegenie/remediation/"
    assert migration_dir.exists(), "distroless CLI did not write to .codegenie/migration/"

    # No path overlap
    remediation_files = set(p.relative_to(remediation_dir) for p in remediation_dir.rglob("*") if p.is_file())
    migration_files = set(p.relative_to(migration_dir) for p in migration_dir.rglob("*") if p.is_file())
    # The relative paths may coincide (e.g. both contain `audit/<id>.jsonl`), but the absolute
    # parents (.codegenie/remediation/ vs .codegenie/migration/) make collision impossible.
    common_absolute = set(remediation_dir.rglob("*")) & set(migration_dir.rglob("*"))
    assert common_absolute == set(), f"Cross-task file collision: {common_absolute}"


@pytest.mark.integration
@pytest.mark.requires_docker
def test_audit_chain_writes_do_not_cross_directories(shared_fixture: Path) -> None:
    """Each chain JSONL must live under its task's directory only."""
    runner = CliRunner()
    runner.invoke(loop, ["run", str(shared_fixture), "--cve", "CVE-2025-XXXX"])
    runner.invoke(migrate, ["run", str(shared_fixture), "--target", "distroless", "--cve", "CVE-2025-XXXX"])

    vuln_chains = list((shared_fixture / ".codegenie/remediation").rglob("audit/*.jsonl"))
    distroless_chains = list((shared_fixture / ".codegenie/migration").rglob("audit/*.jsonl"))
    assert vuln_chains, "No vuln audit chain emitted"
    assert distroless_chains, "No distroless audit chain emitted"
    # Confirm no vuln chain file appears in migration tree and vice versa
    for vc in vuln_chains:
        assert ".codegenie/migration/" not in str(vc)
    for dc in distroless_chains:
        assert ".codegenie/remediation/" not in str(dc)
```

Run; confirm failures (likely `ImportError` on the test file, or assertion on disjoint directories). Commit.

### Green — make it pass

The CLIs from S5-05 and Phase 6 already write to distinct directories by design. The test should pass as soon as both CLIs run end-to-end. If the test reveals an actual collision, that's a bug in either S5-05 (`cli/migrate.py`) or Phase 6's `cli/loop.py` — surface it loudly and fix the offender.

### Refactor — clean up

- Add `shared_fixture` to `tests/integration/conftest.py` — a tmp dir reusing the S5-06 Express fixture with a vuln-applicable CVE.
- Add docstrings citing arch §Gap 1 and ADR-P7-001 / ADR-P7-005 verbatim.
- Per cross-cutting determinism: no `random` / no `time` imports.
- Mark with `@pytest.mark.slow` if both CLIs together exceed 60 s.
- Document that Phase 8's supervisor will use `wf:<task>:` as the dispatch key — the test's prefix-distinction assertion is the early canary for that contract.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_chain_no_collision_across_tasks.py` | NEW — the cross-task collision test. |
| `tests/integration/conftest.py` | UPDATE — `shared_fixture` fixture (may reuse `express_fixture` from S5-06). |

## Out of scope

- **Phase 8's supervisor dispatch logic** — Phase 8 owns this story's outcomes.
- **The actual vuln catalog seed and CVE** — Phase 3 owns; this story consumes.
- **Concurrent-write race conditions across processes** — covered by `flock(2)` in S2-05 and grype-DB matrix in S8-03; this story is about *directory* disjointness, not lock contention.
- **End-to-end happy-path E2E** — owned by S5-06.
- **Replay-after-SIGKILL** — owned by S5-08.
- **A test that intentionally forces a hash collision in the BLAKE3-truncated ID** — that's a Hypothesis test for the hashing scheme (arch §Property tests), not this story.
- **Per-CLI workflow_id `--run-id-override` flag** — not introduced here; the test exercises the *natural* derivation.

## Notes for the implementer

- **The directory split (`.codegenie/remediation/` vs `.codegenie/migration/`) is the structural guarantee** — even if `workflow_id` BLAKE3 truncation produces a collision (vanishingly unlikely but not impossible), the chain files don't collide because they live in different parent directories. The prefix scheme (`wf:vuln:` vs `wf:distroless:`) is the *additional* defense at the workflow-id level. This test exercises both layers.
- **`_derive_workflow_id` must be exposed from both CLIs** — S5-05's `cli/migrate.py` makes it a module-level function (for testability per the S5-05 spec). If Phase 6's `cli/loop.py` does not expose its derive function the same way, the test can derive locally by re-implementing the formula (one-line each). Surface the inconsistency as a follow-up — per CLAUDE.md Rule 12, don't paper over.
- **The "intentionally identical `<run-id>`" framing is a thought experiment.** In practice the CLIs derive `<run-id>` from `workflow_id` so they're already distinct. The test still asserts directory disjointness because that's the *structural* invariant Phase 8 will rely on — the test surfaces a Phase 8 prerequisite, not a current-state bug.
- **Per `phase-arch-design.md §Gap 1`, the prefix scheme is Phase 8's dispatch key.** Phase 8's supervisor reads the workflow_id, splits on `wf:`, takes the next segment, and dispatches to `build_vuln_loop` or `build_distroless_loop`. This test pins the prefixes — if a future PR adds a third task class (`wf:upgrade:`), the same test pattern extends additively.
- **The Phase 6 `threading.Lock` is single-writer per process**, not per task class. Within one process, audit-chain appends are serialized. Across two CLI invocations (the realistic case), the directory split is the only thing preventing cross-task corruption. This test verifies the structural side; cross-process locking is S2-05 / S8-03's domain.
- **Per CLAUDE.md Rule 12 ("Fail loud"), if the directories ever overlap**, the failure should be obvious — printed paths, named offenders. Do not weaken the assertion to "directories exist"; the assertion is "no file path appears in both trees".
