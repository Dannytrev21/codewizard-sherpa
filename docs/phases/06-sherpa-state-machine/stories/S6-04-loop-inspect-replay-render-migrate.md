# Story S6-04 — Implement `loop inspect`, `replay`, `migrate-checkpoint` (scaffold), `render`

**Step:** Step 6 — Ship `cli/loop.py` operator surface + workflow-id derivation + exit codes
**Status:** Ready
**Effort:** M
**Depends on:** S6-02
**ADRs honored:** ADR-0009 (cli/loop parallel — `cli/remediate.py` unmodified), ADR-0013 (JSON-golden topology snapshot; SVG advisory), ADR-0005 (`schema_version` literal pin — `migrate-checkpoint` is the only forward path on `SchemaDrift`)

## Context

`run` (S6-02) and `resume` (S6-03) are the two operator actions that *mutate* a workflow. The remaining four subcommands are **read-only / dev-only**: `inspect` prints the LangGraph state history table for an existing workflow; `replay` re-runs each persisted node with the captured input and asserts byte-identical outputs (the in-process companion to Step 8's multiprocessing SIGKILL canary); `render` dumps the compiled topology to both `.json` (CI-gated, ADR-0013) and `.svg` (committed for review only, advisory) — the SVG lands at the well-known path `docs/phases/06-sherpa-state-machine/vuln_loop.svg`; `migrate-checkpoint` is **scaffolding only** at v0.6.0 because no schema bump has happened yet — the command exists so its contract is locked in early and the first phase that adds a field (probably Phase 7's `DistrolessLedger`) has a documented forward path. Each subcommand is tight: low LOC, clean read-only seam, integration tests against fixtures. The tight grouping is intentional — the four bodies share the workflow-id parsing, checkpointer instantiation, and exit-code emitter from S6-02, so doing them in one story avoids three identical PRs.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — 8. cli/loop.py — operator surface` lines 853–860 — the four read-only subcommand bodies in one paragraph each.
  - `../phase-arch-design.md §Process view — Scenario 4 (codegenie loop render — topology dump)` lines 485–510 — the `render` flowchart: `build_vuln_loop(InMemorySaver()).get_graph().to_json()` → canonical JSON (CI gate) + `langgraph-cli` SVG (review-only).
  - `../phase-arch-design.md §Component design — 10. Golden-graph topology snapshot` lines 886–898 — the `canonical_json` contract `render` must emit.
  - `../phase-arch-design.md §Persisted-on-disk shapes` line 1004 — `tests/golden/vuln_loop_topology.json` is the diffed golden; `render --out` writes to a path passed by the operator, but the CI invocation lands at `tests/golden/vuln_loop_topology.json`.
  - `../phase-arch-design.md §Replay / debugability` lines 1090–1097 — `replay` semantics: re-runs each persisted node with the captured input; asserts byte-identical outputs.
  - `../phase-arch-design.md §Edge cases` — `SchemaDrift` is non-recoverable except via `migrate-checkpoint`; this story lands the scaffold so the failure mode has a documented forward path.
- **Phase ADRs:**
  - `../ADRs/0013-json-golden-topology-snapshot-svg-advisory.md` — JSON is the CI contract; SVG is advisory; updating either is a deliberate flag (`pytest --update-golden`).
  - `../ADRs/0005-static-schema-version-literal-pin.md` — `schema_version: Literal["v0.6.0"]`; no auto-migration; `migrate-checkpoint` is the only forward path.
  - `../ADRs/0009-cli-loop-ships-parallel-to-cli-remediate.md` — byte-identity gate still applies; do not edit `cli/remediate.py`.
- **Existing code:**
  - `src/codegenie/cli/loop.py` (S6-01..S6-03) — the four stubs become live bodies; `derive_workflow_id`, exit constants, and the terminal emitter are reused.
  - `src/codegenie/graph/vuln_loop.py` (S5-01) — `build_vuln_loop`; `render` calls it with `InMemorySaver()` (throwaway).
  - `src/codegenie/graph/checkpointer.py` (S2-01) — `make_checkpointer`; `inspect` and `replay` read via it.
  - `langgraph.graph.StateGraph.get_state_history` and `get_graph().to_json()` — LangGraph's introspection seams; consult `langgraph` docs for the pinned version.
  - `langgraph-cli` — dev tool; `pyproject.toml` adds it as an optional dependency.

## Goal

Four read/dev-only `codegenie loop` subcommands ship with sharp acceptance criteria: `inspect` prints a state-history table; `replay` re-runs every persisted node and asserts byte-identical outputs; `render --out <path>` emits canonical JSON + advisory SVG and writes `docs/phases/06-sherpa-state-machine/vuln_loop.svg` as a review artifact; `migrate-checkpoint` is the documented forward-path scaffold for the first future `SchemaDrift` (v0.6.0 ships no migrations).

## Acceptance criteria

### `loop inspect`

- [ ] `codegenie loop inspect <thread_id>` parses `THREAD_ID` (16-hex; same validator as `resume`).
- [ ] Builds `saver = make_checkpointer(workflow_id=thread_id)`; constructs `graph = build_vuln_loop(checkpointer=saver)`; iterates `graph.get_state_history(config)`.
- [ ] Prints a human-readable table with columns `checkpoint_id`, `last_node`, `retry_count`, `current_gate_id`, `at`, `events_count` for each frame, oldest-first. Uses `rich.table.Table` for the human path; `--json` toggles a JSON-Lines emission of frame dicts.
- [ ] Unknown thread_id → exit 1 with "no workflow found" (same as `resume`).
- [ ] Empty history (no checkpoints persisted) → exit 1 with "no checkpoints for thread_id=<id>".
- [ ] `tests/cli/test_loop_inspect.py` invokes `inspect` against a fixture workflow with 3+ persisted checkpoints; asserts the table contains the expected `last_node` values in order and the `--json` mode emits well-formed JSON Lines.

### `loop replay`

- [ ] `codegenie loop replay <thread_id> [--from <checkpoint_id>]` parses both args.
- [ ] If `--from` is provided, replays from that checkpoint forward; otherwise replays from the first persisted checkpoint.
- [ ] For each persisted checkpoint, replay invokes the corresponding node with the captured input and asserts the produced output is **byte-identical** to the persisted next checkpoint (canonical JSON comparison via the S2-01 `canonical_json` helper).
- [ ] A divergence is loud: prints a unified diff of the two JSON blobs and exits 1.
- [ ] The reference replay (no kill, run twice) is exit `0` with a "replay verified: N checkpoints, byte-identical" message.
- [ ] `tests/cli/test_loop_replay.py` (the in-process companion to S8-01) covers two paths: (a) a happy-path replay against a fixture run; (b) a deliberately-mutated checkpoint blob → divergence detected + exit 1.
- [ ] `replay` does **not** mutate state, does not write new checkpoints, does not extend the audit chain — it is purely read + recompute + compare. Verified by a fixture that snapshots the SQLite file before and after; bytes equal.
- [ ] Unknown `--from <checkpoint_id>` (id not in history) → exit 1 with "checkpoint_id <id> not found in thread_id=<thread>".

### `loop render`

- [ ] `codegenie loop render --out <path>` parses `--out` (required Path).
- [ ] Builds `graph = build_vuln_loop(checkpointer=InMemorySaver()).get_graph()` (throwaway checkpointer per Scenario 4).
- [ ] Emits **two** files:
  1. `<out>.json` — `canonical_json(graph.to_json())` (recursive key-sort, `separators=(",", ":")`); this is the CI gate per ADR-0013.
  2. `<out>.svg` — produced via `langgraph-cli` (subprocess); review-only per ADR-0013.
- [ ] When `--out tests/golden/vuln_loop_topology.svg` is invoked (the canonical CI path), the `.json` sibling matches the committed golden byte-for-byte; the `.svg` lands at the path **and** is also copied/symlinked into `docs/phases/06-sherpa-state-machine/vuln_loop.svg` (the artifact path called out in the story brief and in ADR-0013).
- [ ] `tests/cli/test_loop_render.py` invokes `render --out <tmp>/vuln_loop` and asserts: (a) both `<tmp>/vuln_loop.json` and `<tmp>/vuln_loop.svg` exist, (b) the `.json` is canonical (re-loading + re-canonicalizing is a fixed point), (c) `docs/phases/06-sherpa-state-machine/vuln_loop.svg` exists after the CI invocation (gated by env var `CODEGENIE_RENDER_DOC_SVG=1` so the test doesn't write into the docs tree on every dev run).
- [ ] `langgraph-cli` failure (binary missing) → exit 1 with "langgraph-cli not installed; `pip install langgraph-cli` to render SVG" — the `.json` is still written; SVG fails alone.

### `loop migrate-checkpoint`

- [ ] `codegenie loop migrate-checkpoint --from <old_version> --to <new_version>` parses both flags.
- [ ] At v0.6.0, the registry is **empty**; any invocation prints "no migrations registered at v0.6.0 — the first registered migration ships with the schema bump" and exits `0` (scaffold success) when `--from v0.6.0 --to v0.6.0`, and exits `1` with a documented error otherwise.
- [ ] The command exists to **record the contract** (ADR-0005 §"the only forward path on SchemaDrift"). The migration registry seam is a module-level dict `_MIGRATIONS: dict[tuple[str, str], MigrationFn] = {}`; documented as the extension point for the first future schema bump.
- [ ] `tests/cli/test_loop_migrate_checkpoint_scaffold.py` asserts the registry is empty at v0.6.0 and the documented identity invocation exits 0.

### Cross-cutting

- [ ] `cli/remediate.py` byte-identity gate (`tests/graph/test_cli_remediate_unchanged.py`) still passes after this story merges.
- [ ] All four subcommands honor the `--json` group flag from S6-01.
- [ ] `mypy --strict src/codegenie/cli/loop.py` clean.
- [ ] `ruff check src/codegenie/cli/loop.py` clean.
- [ ] TDD plan's red test exists, is committed, and is green.

## Implementation outline

1. **`inspect`** — replace the stub:
   ```python
   @loop.command(name="inspect")
   @click.argument("thread_id", type=str)
   @click.pass_context
   def inspect(ctx, thread_id):
       _validate_thread_id(thread_id)
       asyncio.run(_inspect_async(ctx, thread_id))

   async def _inspect_async(ctx, thread_id):
       saver = make_checkpointer(workflow_id=thread_id)
       graph = build_vuln_loop(checkpointer=saver)
       config = {"configurable": {"thread_id": thread_id}}
       frames = [s async for s in graph.aget_state_history(config)]
       if not frames:
           _terminal(ctx, EXIT_UNEXPECTED, reason="no checkpoints for thread")
       _render_history_table(ctx, frames)
   ```
2. **`replay`** — iterate persisted frames, recompute each node, compare canonical JSON. Use the S2-01 `canonical_json` helper. On divergence, render a unified diff (Python `difflib.unified_diff`) to stderr.
3. **`render`** — call `build_vuln_loop(checkpointer=InMemorySaver()).get_graph()`; write `<out>.json = canonical_json(graph.to_json())`; subprocess `langgraph-cli draw --output <out>.svg`; on success and `CODEGENIE_RENDER_DOC_SVG=1`, copy to `docs/phases/06-sherpa-state-machine/vuln_loop.svg`.
4. **`migrate-checkpoint`** — pure scaffold; module-level `_MIGRATIONS: dict[tuple[str, str], Callable[[dict], dict]] = {}`. Identity migration `("v0.6.0", "v0.6.0") -> lambda x: x` is implicit (no-op); anything else → "no migration registered" error.
5. Wire `_validate_thread_id` once in the module so `resume`, `inspect`, `replay`, `migrate-checkpoint` share it.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/cli/test_loop_inspect.py`

```python
# tests/cli/test_loop_inspect.py
from __future__ import annotations

import json
from click.testing import CliRunner

from codegenie.cli import cli


def test_inspect_prints_history_for_known_thread(runner_with_3_frame_fixture):
    runner, thread_id = runner_with_3_frame_fixture
    res = runner.invoke(cli, ["loop", "inspect", thread_id])
    assert res.exit_code == 0
    # Three frames in order
    for node in ["ingest_cve", "select_recipe", "validate_in_sandbox"]:
        assert node in res.output


def test_inspect_json_mode_emits_jsonlines(runner_with_3_frame_fixture):
    runner, thread_id = runner_with_3_frame_fixture
    res = runner.invoke(cli, ["loop", "--json", "inspect", thread_id])
    lines = [ln for ln in res.output.strip().splitlines() if ln.strip()]
    parsed = [json.loads(ln) for ln in lines]
    assert all("last_node" in p for p in parsed)


def test_inspect_unknown_thread_errors(runner):
    res = runner.invoke(cli, ["loop", "inspect", "deadbeefdeadbeef"])
    assert res.exit_code != 0
    assert "no workflow" in res.output.lower() or "no checkpoints" in res.output.lower()


def test_inspect_empty_history_errors(runner_with_empty_thread):
    runner, thread_id = runner_with_empty_thread
    res = runner.invoke(cli, ["loop", "inspect", thread_id])
    assert res.exit_code != 0
    assert "no checkpoints" in res.output.lower()
```

Test file path: `tests/cli/test_loop_replay.py`

```python
def test_replay_byte_identical_for_clean_run(runner_with_3_frame_fixture):
    runner, thread_id = runner_with_3_frame_fixture
    res = runner.invoke(cli, ["loop", "replay", thread_id])
    assert res.exit_code == 0
    assert "byte-identical" in res.output.lower()


def test_replay_detects_mutated_checkpoint(runner_with_mutated_checkpoint):
    runner, thread_id = runner_with_mutated_checkpoint
    res = runner.invoke(cli, ["loop", "replay", thread_id])
    assert res.exit_code != 0
    assert "diverged" in res.output.lower() or "differ" in res.output.lower()


def test_replay_does_not_mutate_sqlite(runner_with_3_frame_fixture, db_bytes_before):
    runner, thread_id = runner_with_3_frame_fixture
    runner.invoke(cli, ["loop", "replay", thread_id])
    db_bytes_after = (CHECKPOINTS_DIR / f"{thread_id}.sqlite3").read_bytes()
    assert db_bytes_after == db_bytes_before


def test_replay_unknown_from_checkpoint_id(runner_with_3_frame_fixture):
    runner, thread_id = runner_with_3_frame_fixture
    res = runner.invoke(cli, ["loop", "replay", thread_id, "--from", "ckpt-no-such-id"])
    assert res.exit_code != 0
    assert "not found" in res.output.lower()
```

Test file path: `tests/cli/test_loop_render.py`

```python
import json
from pathlib import Path

from click.testing import CliRunner

from codegenie.cli import cli


def test_render_emits_json_and_svg(tmp_path: Path, runner: CliRunner):
    out = tmp_path / "vuln_loop"
    res = runner.invoke(cli, ["loop", "render", "--out", str(out)])
    assert res.exit_code == 0
    assert (tmp_path / "vuln_loop.json").is_file()
    assert (tmp_path / "vuln_loop.svg").is_file()


def test_render_json_is_canonical(tmp_path, runner):
    out = tmp_path / "vuln_loop"
    runner.invoke(cli, ["loop", "render", "--out", str(out)])
    blob = (tmp_path / "vuln_loop.json").read_bytes()
    # Re-canonicalizing should be a fixed point
    from codegenie.graph.checkpointer import canonical_json
    assert canonical_json(json.loads(blob)) == blob


def test_render_doc_svg_lands_at_canonical_path(monkeypatch, tmp_path, runner):
    monkeypatch.setenv("CODEGENIE_RENDER_DOC_SVG", "1")
    out = tmp_path / "vuln_loop"
    runner.invoke(cli, ["loop", "render", "--out", str(out)])
    assert Path("docs/phases/06-sherpa-state-machine/vuln_loop.svg").is_file()


def test_render_without_langgraph_cli_still_writes_json(monkeypatch, tmp_path, runner):
    monkeypatch.setattr("shutil.which", lambda name: None if name == "langgraph" else "/usr/bin/" + name)
    out = tmp_path / "vuln_loop"
    res = runner.invoke(cli, ["loop", "render", "--out", str(out)])
    assert (tmp_path / "vuln_loop.json").is_file()
    assert res.exit_code != 0
    assert "langgraph-cli" in res.output.lower()
```

Test file path: `tests/cli/test_loop_migrate_checkpoint_scaffold.py`

```python
def test_migrate_checkpoint_identity_at_v0_6_0_succeeds(runner):
    res = runner.invoke(cli, ["loop", "migrate-checkpoint",
                              "--from", "v0.6.0", "--to", "v0.6.0"])
    assert res.exit_code == 0
    assert "no migrations registered" in res.output.lower()


def test_migrate_checkpoint_unregistered_pair_errors(runner):
    res = runner.invoke(cli, ["loop", "migrate-checkpoint",
                              "--from", "v0.6.0", "--to", "v0.7.0"])
    assert res.exit_code != 0
    assert "no migration registered" in res.output.lower()


def test_migration_registry_is_empty_at_v0_6_0():
    from codegenie.cli.loop import _MIGRATIONS
    assert _MIGRATIONS == {}
```

### Green — make it pass

Smallest implementation: ~150 LOC across the four bodies. `_render_history_table` uses `rich.table.Table`; `_diff_canonical_json(a, b)` uses `difflib.unified_diff`; `_render_to_files(out)` uses `subprocess.run(["langgraph", "draw", ...])` after `shutil.which("langgraph")` check.

### Refactor — clean up

- Extract `_validate_thread_id` once and reuse across all four subcommands (and `resume`).
- Pull the SVG-copy-to-docs side effect into a clearly-named helper `_publish_doc_svg(out_svg: Path)` so its gated behavior is obvious.
- Document the canonical golden path (`tests/golden/vuln_loop_topology.json`) in the `render` docstring.
- Confirm `langgraph-cli` is in `pyproject.toml` as an optional dependency under a `dev` extra (`pip install codegenie[dev]`).
- Add a one-line comment at `_MIGRATIONS` citing ADR-0005's "the only forward path on SchemaDrift" so a future implementer wires their migration in here.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli/loop.py` | Replace four stubs with live bodies; add `_validate_thread_id`, `_render_history_table`, `_diff_canonical_json`, `_render_to_files`, `_MIGRATIONS` registry. |
| `tests/cli/test_loop_inspect.py` | New — table + JSON-Lines + error cases. |
| `tests/cli/test_loop_replay.py` | New — byte-identical happy path + divergence detection + no-mutate guarantee. |
| `tests/cli/test_loop_render.py` | New — JSON+SVG emission + canonical-form fixed point + missing-langgraph-cli path + doc SVG copy. |
| `tests/cli/test_loop_migrate_checkpoint_scaffold.py` | New — identity invocation + unregistered-pair error + empty-registry assertion. |
| `tests/cli/conftest.py` | Add `runner_with_3_frame_fixture`, `runner_with_empty_thread`, `runner_with_mutated_checkpoint`. |
| `docs/phases/06-sherpa-state-machine/vuln_loop.svg` | New — the artifact written by `render` under `CODEGENIE_RENDER_DOC_SVG=1`; committed for review (ADR-0013 advisory). |
| `pyproject.toml` | Add `langgraph-cli` as a `dev` extra. |

## Out of scope

- Multiprocessing SIGKILL replay canary — S8-01.
- Reference replay-byte-identical test against real Phase 5 sandbox — S8-02.
- Actually shipping a registered migration (first will land with the first schema bump, post-Phase 6).
- Topology golden file `tests/golden/vuln_loop_topology.json` — landed in S5-02; this story uses the helper to emit canonical JSON but the golden file itself is already pinned.
- Per-node overhead canary (`test_canary_overhead.py`) — S9-01.

## Notes for the implementer

- The well-known SVG artifact path `docs/phases/06-sherpa-state-machine/vuln_loop.svg` is mentioned in the story brief, in ADR-0013, and in `phase-arch-design.md §Scenario 4`. Land the file with this story's PR (regenerated by your local `CODEGENIE_RENDER_DOC_SVG=1 codegenie loop render` invocation) so reviewers can eyeball it. It is **not** a CI gate; reviewers should accept reasonable SVG drift on minor LangGraph bumps and ignore textual diffs on it. The CI gate lives on `tests/golden/vuln_loop_topology.json` (S5-02).
- `replay` is the **in-process** byte-identical guarantee. The SIGKILL multiprocessing canary (S8-01) is the **cross-process** version. Both must pass; the in-process one is the cheaper smoke test gating the merge queue.
- `replay` must not mutate state. The simplest way to verify is to snapshot the SQLite file bytes before and after, then assert equality. Do not rely on the test framework's tmpdir clean-up to mask a write.
- `inspect` uses `aget_state_history` (the async iterator); not `get_state_history` (sync). LangGraph's pinned version may shape both APIs — use the async path consistently with the rest of the codebase.
- `migrate-checkpoint` is intentionally a no-op at v0.6.0. The contract is the registry shape (`dict[tuple[str,str], MigrationFn]`) and the "exit 0 on identity, exit 1 on unregistered" semantics. Resist building a generic migration framework; the first real migration will land with concrete needs.
- `langgraph-cli` is an *optional* dev dependency. The `.json` emission is the load-bearing artifact (CI gate); the `.svg` is review-only. If `langgraph-cli` is missing on a developer machine, the JSON still writes — only SVG fails. The test pins this behavior.
- The `--from <checkpoint_id>` flag on `replay` is for re-running a specific frame onwards; useful for debugging a divergence. Resist adding `--to`, `--node`, or other slicing flags — they're easily added later if the operator runbook demands.
- `cli/remediate.py` byte-identity must still hold after this story merges. The story does not touch it; the CI gate enforces.
- Resist exposing internal `_MIGRATIONS` as a public symbol. The first real migration will register via a decorator (e.g., `@register_migration("v0.6.0", "v0.7.0")`) — that's a follow-up story when the bump happens, not this one.
- All four subcommands honor `--json` from the group, but only `inspect` and the terminal emitter in `replay`/`migrate-checkpoint` actually produce structured JSON output; `render` is JSON-or-SVG content, not a JSON event stream. Keep the distinction clean.
