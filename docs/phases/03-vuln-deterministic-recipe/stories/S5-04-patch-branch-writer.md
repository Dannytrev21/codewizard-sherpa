# Story S5-04 — `PatchBranchWriter` + branch refusals + bot identity (`transforms/branch_writer.py`)

**Step:** Step 5 — Ship `NpmPackageUpgradeTransform`, `RemediationOrchestrator`, `PatchBranchWriter`, and the `codegenie remediate` CLI surface
**Status:** Ready
**Effort:** M
**Depends on:** S5-03 (`RemediationOrchestrator` — the green-path caller); transitively S1-04 (`BranchHandoff` Pydantic shape), S1-05 (`ALLOWED_BINARIES` extension for `git`), S1-07 (audit events for `branch.created`, `branch.refused_*`).
**ADRs honored:** ADR-0001, ADR-0002, ADR-0014; ADRs/README.md "Decision noted but not yet documented" #2 (branch-naming convention)

## Context

`PatchBranchWriter` is the final-step writer for green outcomes. Three lenses (best-practices, security-first, performance-first) converged on every detail — there is no synth departure here. The job is mechanical but the contracts are load-bearing:

1. **Refuse dirty trees** — if the working tree has uncommitted changes, the writer raises `WorkingTreeNotClean` and emits `branch.refused_dirty_tree`. This is the same dirty-tree check `NpmPackageUpgradeTransform` (S5-01) performs at the source repo; the writer re-checks because the operator may have created changes between transform completion and branch write (rare but auditable).
2. **Refuse existing branches** — branch name is `codegenie/vuln-fix/<cve-id>-<short-sha>` where `short-sha = HEAD@remediate-time[:7]`. Per Open Question #9 (`final-design.md`), short-SHA collision is vanishingly rare; if `git rev-parse --verify <branch>` returns 0, the writer raises `BranchExists` and emits `branch.refused_exists`.
3. **Bot identity per-invocation only** — every git call uses the four `-c` flags: `-c core.hooksPath=/dev/null -c commit.gpgsign=false -c user.email=codegenie-bot@codegenie.invalid -c user.name=codegenie-bot`. NEVER `git config` (which writes to user-level config and silently relies on environment state on the next run).
4. **Write the artifact bundle** — `remediation-report.yaml` (index), `diff/<recipe-id>.patch` (the patch — already on disk from S5-01, just confirmed), `raw/*` (whatever validators emitted), `audit/<run-id>.jsonl` (BLAKE3-chained slice).

The writer ships the `BranchHandoff` Pydantic that Phase 4 (RAG ingestion) consumes — `branch_name`, `head_sha`, `files_changed`, `diff_path`, `report_path`. The Phase-4 handoff-contract test (S7-06) asserts this Pydantic's shape against a Phase-4-shaped consumer; this story's tests pin the producer side.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #13 PatchBranchWriter` — full internal design.
  - `../phase-arch-design.md §"Audit event payload extensions"` — `branch.created`, `branch.refused_dirty_tree`, `branch.refused_exists`.
  - `../phase-arch-design.md §"Data model" — BranchHandoff` — the Pydantic shape.
- **Phase ADRs:**
  - `../ADRs/0014-allowed-binaries-additions-npm-ncu-java.md` — `git` is in `ALLOWED_BINARIES`; every invocation routes through `exec.run_in_sandbox`.
  - `../ADRs/README.md "Decisions noted but not yet documented" #2` — branch-naming convention; Open Question #9 in `final-design.md`.
- **Production ADRs:**
  - `../../../production/adrs/0007-human-merge-required.md` — autonomy ends at PR creation; in Phase 3 it ends at branch write.
- **Source design:**
  - `../final-design.md §"Components" §7 stage 7` — branch writer in the seven-stage pipeline.
  - `../final-design.md §"Open questions" #9` — short-sha collision convention.
- **Existing code:**
  - `src/codegenie/transforms/npm_package_upgrade.py` (S5-01) — exports `_GIT_BOT_FLAGS: tuple[str, ...]`; this story imports the same constant for symmetry.
  - `src/codegenie/transforms/coordinator.py` (S5-03) — the orchestrator's green-path branch invokes `write_branch(transform_output, gate_outcome, run_id)` which delegates here.
  - `src/codegenie/exec.py` (Phase 1 + S1-02 Phase 2) — `run_in_sandbox`; the writer routes every git call through it.
  - `src/codegenie/audit/writer.py` — `AuditWriter.append`; shared instance threaded from the orchestrator.
  - `src/codegenie/audit/events.py` (S1-07) — typed event payloads.

## Goal

Implement `src/codegenie/transforms/branch_writer.py` exposing `PatchBranchWriter.write(outcome: BranchWriteInput) -> BranchHandoff` — a green-path writer that refuses dirty trees and existing branches, builds the branch name from `codegenie/vuln-fix/<cve-id>-<short-sha>`, threads the four `-c` bot-identity flags through every git invocation (never via `git config`), and emits the full artifact bundle under `.codegenie/remediation/<run-id>/`.

## Acceptance criteria

- [ ] `src/codegenie/transforms/branch_writer.py` exports `PatchBranchWriter` (class) with a single public method `write(self, outcome: BranchWriteInput) -> BranchHandoff`.
- [ ] `BranchWriteInput` is a frozen Pydantic carrying `transform_output: TransformOutput`, `gate_outcome: GateOutcome`, `run_id: str`, `repo_root: Path`, `cve_id: str`, `audit_writer: AuditWriter`. The orchestrator builds it from its boundary objects.
- [ ] `BranchHandoff` (lands in S1-04 — re-use) carries `branch_name: str`, `head_sha: str`, `files_changed: list[Path]`, `diff_path: Path`, `report_path: Path`, `raw_dir: Path`, `audit_path: Path`.
- [ ] Branch name computation: `f"codegenie/vuln-fix/{cve_id}-{short_sha}"` where `short_sha = head_sha[:7]` and `head_sha = git rev-parse HEAD` at remediate-time (passed in via `BranchWriteInput` — the transform captured it earlier; do not re-resolve here, that would be a different SHA after the commit).
- [ ] **Wait, refine**: the branch name uses the **pre-transform** HEAD short-SHA (so the branch label is stable regardless of what the transform committed). The `head_sha` written into `BranchHandoff` is the **post-commit** HEAD of the new branch. Both SHAs are recorded.
- [ ] Dirty-tree check: invoke `git -c core.hooksPath=/dev/null status --porcelain` inside `repo_root`'s worktree; non-empty stdout → raise `WorkingTreeNotClean(branch_name=...)` and append `branch.refused_dirty_tree` audit event. (Note: the transform operates inside a separate worktree `.codegenie/remediation/<run-id>/worktree`; the writer operates inside that worktree, where the only commit is the transform's. A dirty tree here is anomalous and indicates either a hook side-effect or a concurrent write.)
- [ ] Existing-branch check: invoke `git -c core.hooksPath=/dev/null rev-parse --verify <branch_name>` inside the worktree; exit-code 0 → raise `BranchExists(branch_name=...)` and append `branch.refused_exists` audit event.
- [ ] Branch creation: invoke `git <GIT_BOT_FLAGS> branch <branch_name>` then `git <GIT_BOT_FLAGS> checkout <branch_name>` — or equivalently `git <GIT_BOT_FLAGS> checkout -b <branch_name>`. Append `branch.created` audit event with `branch_name`, `head_sha` (post-commit), `files_changed_count`.
- [ ] Every git invocation in this file routes through `exec.run_in_sandbox` with the documented flags. **No `subprocess.run` direct calls.**
- [ ] **Bot identity is set per-invocation via `-c` flags, NEVER via `git config`.** The constant `_GIT_BOT_FLAGS` is imported from `src/codegenie/transforms/npm_package_upgrade.py` (S5-01); both modules reference the same tuple. A unit test in this file AND in S5-01's test file parse the produced patch's `From:`/`Author:` lines and assert `codegenie-bot@codegenie.invalid` is present.
- [ ] Artifact-bundle write — under `<repo_root>/.codegenie/remediation/<run_id>/`:
  - `remediation-report.yaml` — `RemediationReport` serialized via `yaml.safe_dump(sort_keys=True)`. Schema-version field present (`schema_version: "v1"`). `additionalProperties: false` at the JSON-schema layer.
  - `diff/<recipe-id>.patch` — already written by S5-01 transform; the writer verifies presence (existence + size > 0) and records the path.
  - `raw/` — directory containing whatever validators emitted (`install.log`, `test.xml`, `ncu.json`, …). The writer does not create files here; it records the directory path.
  - `audit/<run-id>.jsonl` — BLAKE3-chained slice. The writer **flushes** the audit writer here (forces the buffered events to disk) and records the path. The audit writer's flush method must exist; if it doesn't, this story adds a one-line additive method to S1-07's `AuditWriter`.
- [ ] On any failure (dirty tree, existing branch, write failure), the partial bundle remains on disk per S5-03's failure-preservation contract. The writer does NOT cleanup on failure.
- [ ] `tests/unit/transforms/test_branch_writer.py` ships ≥ 5 tests:
  - happy path — branch created, all four artifact-bundle entries present, `BranchHandoff` returned with correct paths and SHAs.
  - dirty-tree refusal — `WorkingTreeNotClean` raised, `branch.refused_dirty_tree` audit event emitted, no branch created.
  - existing-branch refusal — `BranchExists` raised (synthesize a pre-existing branch with the same name), `branch.refused_exists` emitted.
  - bot committer identity — parse the produced patch's `From:` line, assert `codegenie-bot@codegenie.invalid` + `codegenie-bot`.
  - `core.hooksPath=/dev/null` honored — place a pre-commit hook in the worktree that writes a marker file; assert the marker is absent after the writer completes.
  - `commit.gpgsign=false` honored — assert no signature header in the produced patch (no `gpgsig:` field).
  - bot identity NOT in `git config` — assert `git config user.email` returns the operator's identity (or empty), NOT `codegenie-bot@codegenie.invalid`.
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write the failing tests under `tests/unit/transforms/test_branch_writer.py` (red).
2. Create `src/codegenie/transforms/branch_writer.py` skeleton with `PatchBranchWriter` class + `BranchWriteInput` Pydantic + `WorkingTreeNotClean` / `BranchExists` exception classes.
3. Implement `_check_dirty_tree(worktree_root)` — wrap `exec.run_in_sandbox` for `git status --porcelain`; raise `WorkingTreeNotClean` on non-empty stdout.
4. Implement `_compute_branch_name(cve_id, pre_transform_head_sha) -> str` — `f"codegenie/vuln-fix/{cve_id}-{pre_transform_head_sha[:7]}"`.
5. Implement `_check_branch_exists(worktree_root, branch_name)` — wrap `exec.run_in_sandbox` for `git rev-parse --verify <branch>`; exit-code 0 → raise `BranchExists`.
6. Implement `_create_branch(worktree_root, branch_name)` — wrap `git checkout -b <branch>` with the four bot-identity flags.
7. Implement `_resolve_post_commit_head(worktree_root) -> str` — `git rev-parse HEAD` after checkout (the commit from the transform).
8. Implement `_write_remediation_report(...)` — serialize `RemediationReport` to `remediation-report.yaml` via `yaml.safe_dump(sort_keys=True)`.
9. Implement `_flush_audit_writer(writer)` — calls `writer.flush()`. If `AuditWriter` doesn't have a `flush()` method, add a one-line additive method to `audit/writer.py`.
10. Compose the public `write` method — flat sequence of the helpers; on any raised exception, emit the appropriate `branch.refused_*` audit event before re-raising.
11. Run pytest, ruff, mypy.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/transforms/test_branch_writer.py`.

```python
# Test signatures only — no implementation.

def test_happy_path_creates_branch_and_writes_artifact_bundle(tmp_path, transform_output_fixture, ...): ...
def test_branch_name_is_codegenie_vuln_fix_cve_id_short_sha(...): ...
def test_branch_name_uses_pre_transform_head_short_sha_not_post_commit(...): ...
def test_dirty_tree_raises_working_tree_not_clean(tmp_path, dirty_worktree, ...): ...
def test_dirty_tree_emits_branch_refused_dirty_tree_audit_event(audit_capture, ...): ...
def test_existing_branch_raises_branch_exists(tmp_path, worktree_with_preexisting_branch, ...): ...
def test_existing_branch_emits_branch_refused_exists_audit_event(audit_capture, ...): ...
def test_bot_committer_identity_in_patch_from_line(...): ...
def test_core_hookspath_devnull_honored_no_hook_marker_written(tmp_path, worktree_with_precommit_hook, ...): ...
def test_commit_gpgsign_false_no_signature_header_in_patch(...): ...
def test_bot_identity_not_persisted_in_git_config_user_email(tmp_path, ...): ...
def test_remediation_report_yaml_serialized_sorted_keys(...): ...
def test_audit_writer_flush_called_before_write_returns(audit_capture, ...): ...
def test_branch_created_event_carries_correct_files_changed_count(audit_capture, ...): ...
def test_branch_handoff_pydantic_carries_all_seven_fields(...): ...
def test_partial_bundle_remains_on_disk_after_branch_exists_refusal(tmp_path, ...): ...
```

Run pytest; confirm failures. Commit as red marker.

### Green — make it pass

Implement the helpers per the outline. The `_GIT_BOT_FLAGS` constant is imported from `npm_package_upgrade.py` (S5-01); if S5-01 hasn't landed yet (parallel work), define it in a small shared module `src/codegenie/transforms/_git_flags.py` and have both stories import from there.

The audit-event emit on refusal happens **before** the raise (the catch-block in the orchestrator is not the right place — the event names "branch.refused_*" indicate the writer made the decision, not the orchestrator). Use a small helper `_refuse(reason, branch_name, audit_writer)` that emits the event and raises in one line.

### Refactor — clean up

- Hoist the four `_GIT_BOT_FLAGS` into `src/codegenie/transforms/_git_flags.py` (a new tiny module). Both S5-01 and this story import from there; the next phase (4, 6, 9, 11) that touches git operations imports the same constant. This is the canonical bot-identity surface.
- Module docstring naming ADR-0014 and the branch-naming convention.
- Extract `_compute_branch_name` to `_git_flags.py` (or a sibling helper module) so Phase 11's PR-opening code can reuse it without re-importing the branch writer.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/branch_writer.py` | New — `PatchBranchWriter` + `BranchWriteInput` + two exceptions |
| `src/codegenie/transforms/_git_flags.py` | New (or extracted) — `_GIT_BOT_FLAGS` constant + `_compute_branch_name` helper |
| `src/codegenie/transforms/npm_package_upgrade.py` | One-line edit: import `_GIT_BOT_FLAGS` from `_git_flags` (replacing the local constant if S5-01 defined it inline) |
| `src/codegenie/audit/writer.py` | If `flush()` doesn't exist, add a one-line additive method (gated by S1-07's audit-event extension ADR) |
| `tests/unit/transforms/test_branch_writer.py` | New — ≥ 5 tests (16 listed for safety margin) |
| `tests/unit/transforms/fixtures/branch_writer/` | New — worktree fixtures (clean, dirty, with preexisting branch, with precommit hook) |

## Out of scope

- **The actual `git push` step** — Phase 3 ends at branch write; `git push` + GitHub API are Phase 11. The `BranchHandoff` is the seed; Phase 11 wraps additively.
- **PR-body construction** — Phase 11. The `remediation-report.yaml` is the payload Phase 11 reads.
- **Cleanup of `.codegenie/remediation/<run-id>/`** — `codegenie remediation gc` is a Phase-14 runbook stub (S7-07). This story leaves the bundle on disk.
- **Validating that the orchestrator's `RemediationReport` matches the writer's serialized YAML** — the orchestrator (S5-03) builds the report; this writer serializes it. Round-trip fidelity (Pydantic → YAML → Pydantic) is verified by an integration test in S5-05 / S7-06.
- **`raw/*` content** — the validators (S4-02/03/04) write into `raw/`; this writer just records the directory path.
- **Branch deletion on rollback** — out of scope. Failed runs preserve partial branches per S5-03's failure-preservation contract.
- **Submodules / sparse-checkout** — outside the express-fixture scope of Phase 3.

## Notes for the implementer

- **Bot identity is per-invocation `-c` flags only.** The single load-bearing test for this is `test_bot_identity_not_persisted_in_git_config_user_email`. If a future contributor "simplifies" the code to `git config user.email codegenie-bot@codegenie.invalid` once, that test fires red — and the writer is silently relying on the operator's environment, breaking determinism in containers where `user.email` is pre-set differently. The four `-c` flags MUST be on every git invocation. The shared `_GIT_BOT_FLAGS` constant in `_git_flags.py` is the canonical surface.
- **Branch name uses the pre-transform short-SHA.** This makes the label stable regardless of what the transform committed. The transform captures `git rev-parse HEAD` at the START of `_add_worktree` (S5-01); the writer reads that captured value from `BranchWriteInput`. If you re-resolve `HEAD` here, you'll get the post-commit SHA and the branch label drifts.
- **`branch.refused_*` events emit BEFORE the raise.** The audit-chain integrity invariant means the operator can see "the writer attempted the refusal" even if the orchestrator's catch-block re-raises something different. Use a tiny helper to keep the emit + raise atomic-feeling.
- **`git rev-parse --verify <branch>` is the existing-branch check, not `git branch --list`.** `--verify` exits 0 if the ref exists, non-zero otherwise — branchless one-call check. `git branch --list` is line-based, requires parsing, and is the wrong primitive here.
- **The four `-c` flags are short:**
  - `-c core.hooksPath=/dev/null` — disables every pre/post hook (a malicious or buggy pre-commit hook cannot run).
  - `-c commit.gpgsign=false` — disables GPG signing (no key prompts; no signing-key-absent errors).
  - `-c user.email=codegenie-bot@codegenie.invalid` — bot identity; the `.invalid` TLD per RFC 6761 guarantees no real mailbox.
  - `-c user.name=codegenie-bot` — bot identity name.
  All four must be on every git invocation. Three-of-four is a silent regression — write the test for all four.
- **`yaml.safe_dump(sort_keys=True)` is the canonical writer.** Phase 4 RAG ingestion will parse this file; any non-deterministic key order means the determinism canary (S7-03) sees byte drift in the report. Sort keys + `default_flow_style=False` (block style, not flow). Test the byte-level idempotence (`load → dump → load` produces the same dict).
- **`AuditWriter.flush()` may not exist yet.** If it doesn't, this story adds it as a one-line additive method to `audit/writer.py` — gated by S1-07's audit-event-extension ADR (the broader "extend Phase-2 audit writer additively" gating). Surface the addition in the PR description.
- **Per Rule 3 (Surgical Changes):** do not "improve" `audit/writer.py` (Phase 2 + S1-07) beyond the one-line `flush()` addition. Do not "improve" `exec.py` (Phase 1 + S1-02 Phase 2). Do not refactor S5-01's transform while wiring this writer.
- **`BranchHandoff` is the Phase-4 handoff contract.** The handoff-contract test in S7-06 asserts a Phase-4-shaped consumer can read this Pydantic without importing Phase-3 internals. Keep the field set minimal: `branch_name`, `head_sha`, `files_changed`, `diff_path`, `report_path`, `raw_dir`, `audit_path`. If Phase 4 needs more, that's an ADR amendment + S7-06 test update in the same PR.
