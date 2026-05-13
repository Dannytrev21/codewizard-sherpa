# Story S6-01 — Add `codegenie loop` command group + workflow-id derivation

**Step:** Step 6 — Ship `cli/loop.py` operator surface + workflow-id derivation + exit codes
**Status:** Ready
**Effort:** S
**Depends on:** S5-03
**ADRs honored:** ADR-0009 (cli/loop ships parallel to cli/remediate), ADR-0001 (lazy singleton build_vuln_loop), ADR-0013 (JSON-golden topology)

## Context

Phase 6's CLI surface lives at `src/codegenie/cli/loop.py` and is the only operator entry point for the LangGraph vuln loop. Per ADR-0009, `cli/remediate.py` is **not** modified — `cli/loop.py` ships in parallel as a sibling Click command group so Phase 7's exit criterion ("no Phase 0–6 source touched") survives by construction. This first story stands up the Click group, registers the six subcommand stubs (`run`, `resume`, `inspect`, `replay`, `migrate-checkpoint`, `render`), wires the group into the existing `codegenie` entry point, and lands the **content-addressed workflow-id derivation** that every later subcommand reads. The workflow_id is the single primary key for a vuln-remediation run — it names the per-workflow checkpoint file (`.codegenie/loop/checkpoints/<workflow_id>.sqlite3`), it is the LangGraph `thread_id`, and it is what makes the same `(repo HEAD, advisory)` resumable across kills (Scenario 3). Getting this hash right and stable is a load-bearing prerequisite for every test in Steps 7, 8, and 10.

The story is intentionally narrow: subcommand bodies are stubs (each prints "not implemented" and exits 1); only the group, the `workflow_id` helper, and a deterministic-content-addressing test land here. S6-02 fills in `run`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — 8. cli/loop.py — operator surface` (lines 840–862) — full subcommand surface, workflow-id derivation formula, dependencies, failure behavior.
  - `../phase-arch-design.md §Goals#13–14` — `codegenie loop run` is the CLI command; `cli/remediate.py` not modified.
  - `../phase-arch-design.md §Control flow — Happy path step 2` — `cli/loop.py:run()` derives workflow_id and constructs the checkpointer; this story lands the derivation half only.
  - `../phase-arch-design.md §Process view — Scenario 3 (Mid-run SIGKILL + resume)` — same advisory + same repo HEAD → same workflow_id → resumable; this is the property the determinism test asserts.
  - `../phase-arch-design.md §Harness engineering — Configuration` (lines 1098–1107) — config precedence: CLI flags → env vars → `tools/policy/graph-thresholds.yaml` → defaults; the group must surface `--json` at parse time even though no subcommand consumes it yet.
- **Phase ADRs:**
  - `../ADRs/0009-cli-loop-ships-parallel-to-cli-remediate.md` — the single most-cited ADR in this step; the "Decision" block names the six subcommands verbatim, the exit-code table, and the workflow-id formula.
  - `../ADRs/0013-json-golden-topology-snapshot-svg-advisory.md` — `render` is part of this group but defers its body to S6-04; the group must register it now so `--help` lists it.
- **Existing code:**
  - `src/codegenie/cli/__init__.py` — the `codegenie` top-level Click group; this story adds one line to register `loop` as a sub-group.
  - `src/codegenie/cli/remediate.py` — **read-only** reference; CI gate `tests/graph/test_cli_remediate_unchanged.py` (ADR-0009 §Consequences) snapshots its bytes. Do not edit.
  - `src/codegenie/gates/retry_ledger.py` — Phase 5's `RetryLedger`; the workflow-id derivation needs the canonical advisory id, not the ledger; this story does **not** import the ledger yet (S6-02 does).
  - `src/codegenie/planner/advisory_loader.py` (Phase 3) — `AdvisoryRef.canonical_id` property is the second input to the blake3 hash.

## Goal

Ship a `codegenie loop` Click command group at `src/codegenie/cli/loop.py` with six registered subcommand stubs and a content-addressed `derive_workflow_id(repo_root: Path, advisory_canonical_id: str) -> str` helper that is byte-stable across runs, OS file-mtime jitter, and `.git/` layout differences; `cli/remediate.py` byte-for-byte unchanged.

## Acceptance criteria

- [ ] `src/codegenie/cli/loop.py` exists and exports `loop` (a `click.Group`).
- [ ] `codegenie loop --help` lists exactly six subcommands in this order: `run`, `resume`, `inspect`, `replay`, `migrate-checkpoint`, `render` (matches ADR-0009 §Decision verbatim).
- [ ] Each subcommand body raises `click.ClickException("not implemented in S6-01; see S6-02..S6-04")` and the process exits with code `1` so the group is invocable but bodies are unambiguous stubs.
- [ ] `codegenie loop --json` is registered at the **group** level (chained Click option) and exposed on `ctx.obj["json"]`; default `False`.
- [ ] `derive_workflow_id(repo_root: Path, advisory_canonical_id: str) -> str` returns `blake3(f"{repo_root_blake3}|{advisory_canonical_id}".encode()).hexdigest()[:16]`, where `repo_root_blake3` is `blake3` of the resolved git HEAD SHA bytes (read via `subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"], ...)`); function is pure (no I/O beyond the git read).
- [ ] **Length & charset.** The returned id is exactly 16 lowercase hex chars; `re.fullmatch(r"[0-9a-f]{16}", workflow_id)` passes.
- [ ] **Content-addressing determinism.** `tests/cli/test_workflow_id_deterministic.py` asserts: given identical `(repo HEAD SHA, advisory_canonical_id)`, `derive_workflow_id` returns the same id across (a) repeated calls in one process, (b) two subprocess invocations, (c) two different absolute paths pointing at the same git HEAD (i.e., the function reads HEAD content, not path bytes).
- [ ] **Collision-input sensitivity.** Mutating any single byte of either input (different advisory id, different HEAD SHA) changes the workflow_id with probability ≈ 1 (verified by parametrized test over 5 advisory ids × 5 HEAD SHAs = 25 pairs all distinct).
- [ ] **Failure modes.** `derive_workflow_id` raises `WorkflowIdDerivationError(repo_root, reason)` if (a) `repo_root` is not a directory, (b) `git rev-parse HEAD` exits non-zero (e.g., not a repo, no commits), (c) `advisory_canonical_id` is empty / whitespace-only. Each cause has a distinct `reason` literal.
- [ ] `cli/remediate.py` is byte-for-byte identical to its master-branch contents — verified by `tests/graph/test_cli_remediate_unchanged.py` (this test ships in this story; ADR-0009 §Consequences) which compares `hashlib.sha256(<bytes>).hexdigest()` against a constant pinned in the test.
- [ ] `codegenie loop` is reachable from the top-level `codegenie` entry point; `src/codegenie/cli/__init__.py` registers it via `cli.add_command(loop)`.
- [ ] `mypy --strict src/codegenie/cli/loop.py` clean; no `Any` on `derive_workflow_id`'s public signature.
- [ ] `ruff check src/codegenie/cli/loop.py` clean.
- [ ] `pytest tests/cli/test_loop_group_registration.py tests/cli/test_workflow_id_deterministic.py tests/graph/test_cli_remediate_unchanged.py` all green.
- [ ] TDD plan's red test exists, is committed, and is green.

## Implementation outline

1. Create `src/codegenie/cli/loop.py` with:
   ```python
   @click.group(name="loop")
   @click.option("--json", "json_output", is_flag=True, default=False, help="Emit structured JSON on stderr")
   @click.pass_context
   def loop(ctx: click.Context, json_output: bool) -> None:
       ctx.ensure_object(dict)
       ctx.obj["json"] = json_output
   ```
2. Register six subcommand stubs:
   ```python
   @loop.command(name="run")
   @click.argument("repo", type=click.Path(exists=True, file_okay=False, path_type=Path))
   @click.option("--cve", required=True, type=str)
   @click.option("--max-attempts", type=int, default=None)
   def run(repo: Path, cve: str, max_attempts: int | None) -> None:
       raise click.ClickException("not implemented in S6-01; see S6-02")
   ```
   …and similar `@loop.command` stubs for `resume`, `inspect`, `replay`, `migrate-checkpoint`, `render` with their declared flag shapes from ADR-0009 (parse-time validation only; bodies error out).
3. Implement `derive_workflow_id(repo_root, advisory_canonical_id) -> str`:
   - Validate `repo_root.is_dir()`; otherwise raise `WorkflowIdDerivationError(reason="not_a_directory")`.
   - Validate `advisory_canonical_id.strip() != ""`; otherwise `reason="empty_advisory_id"`.
   - `head_sha = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)`; on non-zero exit, raise with `reason="not_a_git_repo_or_no_head"`.
   - `repo_root_blake3 = blake3(head_sha.stdout.strip().encode()).hexdigest()`.
   - `return blake3(f"{repo_root_blake3}|{advisory_canonical_id}".encode()).hexdigest()[:16]`.
4. Define `class WorkflowIdDerivationError(RuntimeError)` with `__init__(self, *, repo_root: Path, reason: Literal["not_a_directory","not_a_git_repo_or_no_head","empty_advisory_id"])`.
5. Wire into `src/codegenie/cli/__init__.py`: `from codegenie.cli.loop import loop; cli.add_command(loop)`.
6. Pin the SHA-256 of the master-branch `cli/remediate.py` in `tests/graph/test_cli_remediate_unchanged.py` as a module-level constant; the test reads the file bytes and compares.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/cli/test_workflow_id_deterministic.py`

```python
# tests/cli/test_workflow_id_deterministic.py
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from codegenie.cli.loop import derive_workflow_id, WorkflowIdDerivationError, loop


@pytest.fixture
def fresh_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "--allow-empty", "-m", "init", "-q"], cwd=repo, check=True)
    return repo


def test_workflow_id_is_16_lowercase_hex(fresh_git_repo: Path):
    wid = derive_workflow_id(fresh_git_repo, "CVE-2024-FAKE-NPM")
    assert len(wid) == 16
    assert wid == wid.lower()
    int(wid, 16)  # must parse as hex


def test_workflow_id_stable_across_repeated_calls(fresh_git_repo: Path):
    a = derive_workflow_id(fresh_git_repo, "CVE-2024-FAKE-NPM")
    b = derive_workflow_id(fresh_git_repo, "CVE-2024-FAKE-NPM")
    assert a == b


def test_workflow_id_stable_across_aliased_paths(fresh_git_repo: Path, tmp_path: Path):
    # symlink the same repo to a different absolute path; same HEAD content -> same id
    alias = tmp_path / "alias"
    alias.symlink_to(fresh_git_repo)
    assert derive_workflow_id(fresh_git_repo, "CVE-X") == derive_workflow_id(alias, "CVE-X")


def test_workflow_id_changes_with_advisory(fresh_git_repo: Path):
    ids = {derive_workflow_id(fresh_git_repo, f"CVE-{i}") for i in range(5)}
    assert len(ids) == 5


def test_workflow_id_changes_with_head(tmp_path: Path):
    ids: set[str] = set()
    for i in range(5):
        repo = tmp_path / f"r{i}"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "--allow-empty", "-m", f"c{i}", "-q"], cwd=repo, check=True)
        ids.add(derive_workflow_id(repo, "CVE-X"))
    assert len(ids) == 5


def test_workflow_id_rejects_non_directory(tmp_path: Path):
    f = tmp_path / "f"
    f.write_text("x")
    with pytest.raises(WorkflowIdDerivationError) as ei:
        derive_workflow_id(f, "CVE-X")
    assert ei.value.reason == "not_a_directory"


def test_workflow_id_rejects_non_git_dir(tmp_path: Path):
    d = tmp_path / "d"
    d.mkdir()
    with pytest.raises(WorkflowIdDerivationError) as ei:
        derive_workflow_id(d, "CVE-X")
    assert ei.value.reason == "not_a_git_repo_or_no_head"


def test_workflow_id_rejects_empty_advisory(fresh_git_repo: Path):
    with pytest.raises(WorkflowIdDerivationError) as ei:
        derive_workflow_id(fresh_git_repo, "   ")
    assert ei.value.reason == "empty_advisory_id"


def test_loop_group_lists_six_subcommands():
    runner = CliRunner()
    result = runner.invoke(loop, ["--help"])
    assert result.exit_code == 0
    for cmd in ["run", "resume", "inspect", "replay", "migrate-checkpoint", "render"]:
        assert cmd in result.output


def test_run_stub_exits_with_clear_message(fresh_git_repo: Path):
    runner = CliRunner()
    result = runner.invoke(loop, ["run", str(fresh_git_repo), "--cve", "CVE-X"])
    assert result.exit_code == 1
    assert "not implemented" in result.output.lower()
```

Test file path: `tests/graph/test_cli_remediate_unchanged.py`

```python
# tests/graph/test_cli_remediate_unchanged.py
import hashlib
from pathlib import Path

# Pin: master-branch SHA-256 of cli/remediate.py at Phase 5 close.
# Updating this constant is a deliberate ADR-0009 violation; reviewers must reject.
MASTER_SHA256 = "<paste from `shasum -a 256 src/codegenie/cli/remediate.py` on master>"


def test_cli_remediate_byte_identical_to_master():
    p = Path("src/codegenie/cli/remediate.py")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest == MASTER_SHA256, (
        f"cli/remediate.py modified — ADR-0009 violation. "
        f"Got {digest}, expected {MASTER_SHA256}."
    )
```

### Green — make it pass

Smallest implementation: ~80 LOC `cli/loop.py`. `derive_workflow_id` is ~20 LOC (subprocess `git rev-parse HEAD` + two blake3 calls + four validation guards). The six subcommand stubs are one-liners. Register `--json` on the group, ignore it for now.

### Refactor — clean up

- Extract `_run_git(repo_root, *args) -> str` helper if multiple subcommands will need git output (S6-02 will).
- Add module docstring citing ADR-0009 verbatim.
- Add type alias `WorkflowId = NewType("WorkflowId", str)` so later subcommands can't accidentally pass a raw advisory string where a workflow_id is expected.
- Confirm `subprocess.run` uses `check=False` and explicit `text=True`; no shell=True.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli/loop.py` | New — Click group + six subcommand stubs + `derive_workflow_id` + `WorkflowIdDerivationError`. |
| `src/codegenie/cli/__init__.py` | Add one line registering `loop` on the top-level `cli` group. |
| `tests/cli/test_workflow_id_deterministic.py` | New — the deterministic + failure-mode tests. |
| `tests/cli/test_loop_group_registration.py` | New — asserts the six subcommands are present and the stubs error out cleanly. |
| `tests/graph/test_cli_remediate_unchanged.py` | New — ADR-0009 byte-identity gate. |
| `pyproject.toml` | Confirm `blake3` is already a dep (Phase 5 added it); no change expected. |

## Out of scope

- `loop run` happy path + structured exit codes — S6-02.
- `loop resume` + `aupdate_state(as_node="await_human")` — S6-03.
- `loop inspect | replay | render | migrate-checkpoint` bodies — S6-04.
- Reading Phase 5's `RetryLedger.head_from_phase5(...)` — S6-02 (this story only derives the id; it does not seed the ledger).
- `Settings` Pydantic model for `tools/policy/graph-thresholds.yaml` — S5-03 (already landed).
- Operator-key authentication on `--operator` — deferred to Phase 11 (ADR-0008).

## Notes for the implementer

- The `--json` flag is registered on the **group** at this story so help text is correct, but no subcommand consumes it yet. S6-02 reads `ctx.obj["json"]` to toggle stderr structure.
- Do **not** import `codegenie.graph` from `cli/loop.py` in this story — that import adds LangGraph cold-start cost to `codegenie loop --help`, which Step 5's `test_compile_cold_start.py` is measuring against the lazy-singleton path. S6-02 will pull `build_vuln_loop` inside the `run` body, not at module top.
- `subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"])` is the **only** I/O `derive_workflow_id` performs. Resist the urge to read repo files, walk the tree, or hash the working tree — HEAD SHA is the canonical content address and is what Scenario 3 (replay-after-kill) re-derives.
- Phase 3's `AdvisoryRef.canonical_id` is the second input. This story does **not** import Phase 3 to compute it; the helper takes `advisory_canonical_id: str` as a parameter so S6-02 (which loads the advisory) is the only place that calls `AdvisoryRef(...).canonical_id`.
- The SHA-256 pin in `test_cli_remediate_unchanged.py` is updated only by an explicit ADR-0009 amendment PR. Reviewers should reject a "fix the constant" PR that doesn't also amend the ADR.
- Click's `chain=False` is the right default for `@click.group`; the subcommands are mutually exclusive operator actions, never chained.
- Resist adding `--verbose`, `--quiet`, or `--config` flags here; configuration precedence (CLI → env → YAML → defaults) is documented in `phase-arch-design.md §Configuration` and lands progressively across S6-02..S6-04.
