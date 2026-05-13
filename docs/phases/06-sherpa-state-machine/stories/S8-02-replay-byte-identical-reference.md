# Story S8-02 — Reference replay-byte-identical test + no-app-fsync grep gate

**Step:** Step 8 — Replay-after-kill canary (G2)
**Status:** Ready
**Effort:** S
**Depends on:** S8-01
**ADRs honored:** ADR-0006, ADR-0011

## Context
S8-01 is the load-bearing kill canary: spawn → SIGKILL → resume → byte-identical artifacts. This story is the **clean reference test** that runs the same fixture twice without any kill in between and asserts the artifacts are byte-identical. It exists for two reasons:

1. **Isolation of failure surface.** When S8-01 goes red, the diagnostic question is always *"is replay broken, or is the kill harness broken?"* S8-02 answers it: if S8-02 is green and S8-01 is red, the bug is in the kill/resume path (likely a missed fsync or a race between WAL frame commit and process death); if both are red, the bug is in the loop itself (likely a `datetime.now()` or `uuid4()` leak into an artifact).
2. **The no-application-fsync grep gate.** ADR-0011 commits to *"aiosqlite WAL+NORMAL is the only durability primitive"*. A future contributor will, eventually, try to "fix" a replay test by adding `os.fsync(fd)` somewhere in `src/codegenie/graph/`. This story ships a CI-fast grep gate that fails the build if any application-level `os.fsync` (or `fdatasync`, or `fsync` import from `os`) appears under `src/codegenie/graph/`. The grep is in the test itself (not in `tools/fence_ci.yaml`) because the rule is replay-test-shaped: the test that proves WAL+NORMAL is sufficient is also the test that enforces "and nothing else is added."

The reference test is fast (~60 s — single sandbox boot × 2 runs, no kill overhead), so it can run on every PR rather than only on the merge queue. Mark it `@pytest.mark.integration` but **not** `@pytest.mark.slow`.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Edge cases #2` — "Worker SIGKILLed mid-checkpoint-write" cites `tests/integration/test_replay_byte_identical.py` directly.
- **Architecture:** `../phase-arch-design.md §Testing strategy — Layer 3 Replay`.
- **Phase ADRs:** `../ADRs/0006-audited-sqlite-saver-per-workflow-fsync.md` — fsync-per-boundary policy.
- **Phase ADRs:** `../ADRs/0011-sqlite-throughput-watch-and-postgres-escalation.md` — the explicit "no application-level fsync" rule this story enforces.
- **High-level plan:** `../High-level-impl.md §Step 8` — done criteria 3 and 4 (WAL recovery + no app fsync).
- **Sibling story:** `S8-01-replay-after-kill-canary.md` — reuse the `_run_child` helper and `_kill_harness.py` module (if extracted there); do not duplicate the spawn-and-run plumbing.

## Goal
Land `tests/integration/test_replay_byte_identical.py` that runs the same `cve-fixture` twice (no kill) and asserts `report.json` + `attempts.jsonl` are byte-identical, and a separate grep test that fails if any `os.fsync` / `os.fdatasync` / `fsync` symbol is referenced from `src/codegenie/graph/`.

## Acceptance criteria
- [ ] `tests/integration/test_replay_byte_identical.py` exists; decorated `@pytest.mark.integration` (NOT `@pytest.mark.slow`); expected runtime < 120 s on CI baseline hardware.
- [ ] Test runs the same fixture through `build_vuln_loop(...).ainvoke(...)` twice (two separate `multiprocessing.Process` spawns under `start_method="spawn"`, each into its own `tmp_path`), with the same `workflow_id` derived deterministically from `(repo_root_blake3, advisory_canonical_id)`.
- [ ] Both processes exit with `exitcode == 0`; assertion failure prints which run failed and the exitcode.
- [ ] `report.json` bytes are equal between the two runs (`open(p, "rb").read() == open(q, "rb").read()`); the assertion does **not** parse JSON or normalize whitespace — byte identity is the contract.
- [ ] `attempts.jsonl` bytes are equal between the two runs under the same byte-identity rule.
- [ ] If a wall-clock field exists in either artifact, the test surfaces this loudly with a clear diff (`difflib.unified_diff` of the two files in the assertion message) and points the maintainer at the conftest's `freeze_time` fixture rather than silently allowing drift.
- [ ] `tests/integration/test_no_app_fsync_in_graph.py` exists and walks `src/codegenie/graph/` (recursively, `.py` files only); it fails if **any** of the following appear in any line that is not a comment or string literal:
  - `os.fsync(`
  - `os.fdatasync(`
  - `from os import fsync` (or `fdatasync`)
  - `import os.fsync` (defensive; not real Python but defends against an attempted bypass)
- [ ] The grep test parses each `.py` file with `ast` (or, acceptably, with a regex that skips lines starting with `#` and ignores triple-quoted blocks) so a docstring quoting `os.fsync` for documentation purposes does NOT trip it. Bonus: use `ast.NodeVisitor` to find `Call(func=Attribute(value=Name("os"), attr="fsync"))` and `ImportFrom(module="os", names=[alias(name="fsync"), ...])`.
- [ ] The grep test's docstring quotes ADR-0011 verbatim: *"aiosqlite WAL+NORMAL is the only durability primitive"*; if the rule is ever relaxed, the test must be deleted in the same PR as the ADR amendment.
- [ ] The two tests reuse the `_run_child` / spawn-plumbing helpers from S8-01's `_kill_harness.py` (if S8-01 extracted them) or import them from `tests/integration/conftest.py` (if S8-01 chose the conftest location); no duplication.
- [ ] If wall-clock normalization is needed, this story does NOT invent a new mechanism — it consumes the `freeze_time` fixture from `tests/integration/conftest.py` (shared with S7-02) and documents the dependency.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest -m integration` all pass on the touched files.

## Implementation outline
1. Read `tests/integration/test_replay_after_kill.py` (from S8-01) first; the spawn helper, child entrypoint, and run-id discovery should already be factored. If they're not, this story does **not** refactor them mid-flight — surface that as a small follow-up PR and inline-import for now (matching S8-01's shape verbatim is acceptable).
2. Add `tests/integration/test_replay_byte_identical.py`. Module docstring explains the failure-isolation rationale (when both this test and S8-01 are red, the bug is in the loop; when only S8-01 is red, the bug is in the kill path).
3. Implement the run-twice-then-compare test body. Two spawns; two `tmp_path` subdirs; assert byte-identity of `report.json` and `attempts.jsonl`.
4. Add `tests/integration/test_no_app_fsync_in_graph.py`. AST-walk every `.py` file under `src/codegenie/graph/`; fail with a focused message listing offending file + line for each violation; success path runs in < 100 ms.
5. Confirm `mypy --strict` clean on both new test modules.

## TDD plan — red / green / refactor

### Red — write the failing test first

#### Test file 1: `tests/integration/test_replay_byte_identical.py`

```python
"""Reference replay test — run-twice, no kill, byte-identical artifacts.

Why this test exists: it isolates the failure surface from S8-01. If S8-01
goes red and this test is green, the bug is in the kill/resume path (likely a
WAL-frame race or a missed fsync at the SQLite layer). If both are red, the
bug is in the loop itself (likely a non-determinism leak — datetime.now(),
uuid4(), os.urandom, etc.).
"""

from __future__ import annotations

import difflib
import multiprocessing as mp
from pathlib import Path

import pytest

# Reuse the child entrypoint from S8-01 so the production invocation shape
# stays in one place.
from tests.integration._kill_harness import run_child_in_subprocess


@pytest.mark.integration
def test_two_runs_of_same_fixture_produce_byte_identical_artifacts(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Two clean runs of the same fixture must produce byte-identical output.

    No SIGKILL. No resume. No mid-run interruption. Just: run, look at bytes;
    run again, look at bytes; they must be equal.

    A failure here points at non-determinism in the loop itself (uuid4,
    datetime.now, os.urandom in a node body, dict-ordering in an artifact
    serializer, a sort_keys=False somewhere). The fix is to find and remove the
    non-determinism, not to relax the assertion.
    """
    workflow_id = "wfdeadbeefdeadbeef"  # deterministic; matches S8-01's reference

    root_a = tmp_path_factory.mktemp("run_a")
    root_b = tmp_path_factory.mktemp("run_b")

    code_a = run_child_in_subprocess(workflow_id, root_a, timeout_s=180)
    assert code_a == 0, f"first run failed with exitcode={code_a}"

    code_b = run_child_in_subprocess(workflow_id, root_b, timeout_s=180)
    assert code_b == 0, f"second run failed with exitcode={code_b}"

    rem_a = sorted((root_a / ".codegenie/remediation").iterdir())
    rem_b = sorted((root_b / ".codegenie/remediation").iterdir())
    assert [d.name for d in rem_a] == [d.name for d in rem_b], (
        "run_id differs across runs — content-addressing leaked a non-deterministic input"
    )
    run_id = rem_a[0].name

    for artifact in ("report.json", "attempts.jsonl"):
        bytes_a = (root_a / ".codegenie/remediation" / run_id / artifact).read_bytes()
        bytes_b = (root_b / ".codegenie/remediation" / run_id / artifact).read_bytes()
        if bytes_a != bytes_b:
            diff = "\n".join(
                difflib.unified_diff(
                    bytes_a.decode("utf-8", errors="replace").splitlines(),
                    bytes_b.decode("utf-8", errors="replace").splitlines(),
                    fromfile=f"run_a/{artifact}",
                    tofile=f"run_b/{artifact}",
                    lineterm="",
                )
            )
            pytest.fail(
                f"{artifact} bytes diverged across two clean runs. "
                "Check for datetime.now / uuid4 / os.urandom in node bodies "
                "or sort_keys=False in artifact serializers.\n\n" + diff
            )
```

#### Test file 2: `tests/integration/test_no_app_fsync_in_graph.py`

```python
"""ADR-0011 enforcement: aiosqlite WAL+NORMAL is the only durability primitive.

No application-level os.fsync / os.fdatasync may be called from anywhere under
src/codegenie/graph/. Adding one would silently double-fsync, corrupt the S9-02
throughput baseline, and signal that someone treated a failing replay test as a
durability bug instead of as a correctness bug.

If this rule must be relaxed, amend ADR-0011 in the same PR that deletes this
test. Do not amend the test in isolation.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

GRAPH_ROOT = Path("src/codegenie/graph")


def _violations_in(path: Path) -> list[tuple[int, str]]:
    """Return [(lineno, snippet), ...] for any os.fsync / os.fdatasync usage."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr in {"fsync", "fdatasync"}
            ):
                found.append((node.lineno, f"os.{node.func.attr}(...)"))
        if isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                if alias.name in {"fsync", "fdatasync"}:
                    found.append((node.lineno, f"from os import {alias.name}"))
    return found


def test_no_application_level_fsync_under_graph_package() -> None:
    """ADR-0011: WAL+NORMAL is the only durability primitive."""
    offenders: dict[str, list[tuple[int, str]]] = {}
    for py in GRAPH_ROOT.rglob("*.py"):
        violations = _violations_in(py)
        if violations:
            offenders[str(py)] = violations
    if offenders:
        lines = ["Application-level fsync found under src/codegenie/graph/:"]
        for path, hits in sorted(offenders.items()):
            for lineno, snippet in hits:
                lines.append(f"  {path}:{lineno}  {snippet}")
        lines.append("")
        lines.append("ADR-0011 forbids this. If the rule must change, amend the ADR.")
        pytest.fail("\n".join(lines))
```

### Green — make it pass
- Reference test: green falls out as long as the loop is deterministic. If it fails, the implementation owes a fix — `grep -rn "datetime.now\|uuid4\|os.urandom\|random\." src/codegenie/graph/` is the first diagnostic; the fence-CI from S1-01 should already forbid the obvious offenders.
- Grep test: green from day one if the implementation has obeyed ADR-0011. If red, delete the offending `os.fsync` call; the WAL+NORMAL config (set in S2-01's PRAGMAs) is the only durability primitive.

### Refactor — clean up
- If the run-id-discovery helper from S8-01 wasn't extracted yet, extract it now (`tests/integration/_kill_harness.py::discover_run_id(root: Path) -> str`) — S8-02 is the second consumer and the right time.
- If the `_kill_harness.py` module is the wrong home for non-killing helpers, rename it `_loop_harness.py` and update the S8-01 import; small mechanical change, single PR.

## Files to touch
| Path | Why |
|---|---|
| `tests/integration/test_replay_byte_identical.py` | New — the reference run-twice test. |
| `tests/integration/test_no_app_fsync_in_graph.py` | New — the ADR-0011 grep gate. |
| `tests/integration/_kill_harness.py` (or `_loop_harness.py`) | Possibly renamed / extended to host `run_child_in_subprocess` + `discover_run_id`. |
| `tests/integration/conftest.py` | No changes expected; if a small helper is needed, prefer the harness module over the conftest. |

## Out of scope
- The kill canary itself (S8-01).
- Throughput measurement (S9-02).
- Tamper / world-readable / schema-drift (S2-03 covers these adversarially).
- Adding a fence-CI rule under `tools/fence_ci.yaml` for `os.fsync` — the rule lives in this story's grep test because it is replay-shaped, not import-fence-shaped. If a future story wants both, the fence-CI rule can be added without removing this one.
- Any change to the loop, the checkpointer, or the ADRs — if a test goes red, fix the implementation.

## Notes for the implementer
- The grep test should run in well under 100 ms. If it ever becomes slow, the implementation is too large and the rule's value is suspect — that is a signal, not a problem the test should hide.
- The grep test's AST walk handles `os.fsync(...)` and `from os import fsync`. It does **not** attempt to catch `getattr(os, "fsync")(fd)` or `__import__("os").fsync(fd)` — anyone deliberately obfuscating a durability call past the ADR has bigger problems than this test, and the false-negative is acceptable. Surface that in a comment in the test so future readers know the boundary.
- The reference test must NOT silently invoke `freeze_time` to mask a real non-determinism leak. If a `datetime.now()` exists in a node body, the right fix is to remove it (or pass a clock parameter from `VulnLedger`), not to wrap the test in a time-freezer. The conftest's `freeze_time` is for genuine wall-clock-leaking-into-artifact-output cases like a generated timestamp inside `RemediationReport` that has a defensible product reason to exist — discuss in PR review before assuming this applies.
- If the `run_id` discovery diverges between runs, the most likely culprit is `workflow_id` itself drifting (e.g., somebody hashed `time.time_ns()` into it). Check `src/codegenie/cli/loop.py`'s workflow-id derivation before assuming the artifacts are broken.
- This story unblocks S10-01 (adversarial: forged-decision + out-of-order transition). Keep the test runtime tight so S10-* isn't gated on a slow reference run.
- Do not weaken either test. A "good enough" byte-identity comparison that normalizes whitespace or sorts JSON keys defeats the entire point — the production artifact bytes are what an operator sees, and those bytes must match.
