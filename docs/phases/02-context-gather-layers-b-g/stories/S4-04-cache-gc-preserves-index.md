# Story S4-04 — `cache gc` preserves `.codegenie/index/` + `cache prune-index` subcommand

**Step:** Step 4 — Ship Layer B remainder (`SCIPIndexProbe`, `NodeReflectionProbe`, `GeneratedCodeProbe`)
**Status:** Ready
**Effort:** S
**Depends on:** S4-01 (`SCIPIndexProbe` writes `.codegenie/index/scip-index.scip`)
**ADRs honored:** ADR-0013 (per-repo binary lifecycle; `.codegenie/index/` outside `cache/`; manual `cache prune-index`)

## Context

`.codegenie/index/scip-index.scip` is a **per-repo binary artifact**, rewritten in place by `SCIPIndexProbe` on every cache-miss (`final-design.md "Architecture"`, `phase-arch-design.md §"Component design" #17`, ADR-0013). It is **not** a per-gather cache blob — its lifecycle is per-repo (CI invalidates by running on a new commit; the user invalidates by editing TS sources). Phase 0's `cache gc` subcommand walks `.codegenie/cache/` with LRU eviction; if it ever recurses into a sibling `.codegenie/index/`, a single rogue gc invocation costs the next gather ~25 s of full SCIP re-index. The fix is mechanically tiny but architecturally load-bearing: scope `cache gc` to `.codegenie/cache/` only, document the lifecycle distinction in the help text, and ship a separate **manual** `cache prune-index` subcommand for the rare case where a user genuinely wants to drop the SCIP binary.

This story is the on-disk lifecycle's enforcement layer. S4-01 declares "the SCIP binary lives outside `cache/`"; S4-04 makes that survive a `cache gc` invocation forever.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #17 Per-file findings cache + .codegenie/index/` — the on-disk namespace distinction; "`cache gc` extended to manage; `.codegenie/index/scip-index.scip` is per-repo (never auto-deleted); manual `cache prune-index` for the SCIP file".
  - `../phase-arch-design.md §"Physical view"` — `cache/` vs `index/` sibling layout under `.codegenie/`.
- **Phase ADRs:**
  - `../ADRs/0013-scip-node-modules-conditional-mount.md` "Decision" bullet: "**Output artifact.** `.codegenie/index/scip-index.scip` is a **per-repo binary artifact**… Not under `cache/` because its lifecycle is per-repo, not per-gather. `cache gc` extended to manage (LRU on `cache/`; manual `cache prune-index` on `index/`)."
- **Source design:**
  - `../final-design.md §"Architecture"` — `.codegenie/index/` namespace summary.
  - `../final-design.md §"Components"` row `cache gc extended` (Synthesis ledger row D14 + sibling rows on namespaces).
- **Existing code (Phase 0 + Step 1):**
  - `src/codegenie/cli.py` — Phase 0's CLI; existing `cache` subcommand group with at least a `gc` subcommand walking `.codegenie/cache/`.
  - `src/codegenie/cache/` — Phase 0's cache module with LRU/by-access-time eviction.
  - `docs/contributing.md` (Phase 1) — contributor cheat sheet; gets one bullet appended here.
- **Existing stories** (for context, not direct dependencies):
  - S4-01 — writes the binary at `<repo>/.codegenie/index/scip-index.scip`.
  - S8-06 — the contributor cheat sheet revamp (this story drops one bullet; the full cheat sheet lands there).

## Goal

Ensure `cache gc` **never** touches `.codegenie/index/scip-index.scip`, document the per-repo binary lifecycle in the subcommand help text, and ship a manual `cache prune-index` subcommand whose sole purpose is to delete the SCIP binary on explicit user demand.

## Acceptance criteria

- [ ] `src/codegenie/cli.py` `cache gc` subcommand restricts its walk to `<repo>/.codegenie/cache/` exclusively; under no codepath does it `unlink`, `rmtree`, or otherwise touch any file under `<repo>/.codegenie/index/`.
- [ ] `cache gc --help` (Click) text explicitly states: "Walks `.codegenie/cache/` only; the per-repo SCIP binary at `.codegenie/index/scip-index.scip` is preserved (use `cache prune-index` to delete it manually)."
- [ ] `src/codegenie/cli.py` adds a new subcommand `cache prune-index` whose body deletes `<repo>/.codegenie/index/scip-index.scip` (and only that file — no recursive directory removal beyond `index/` itself) when present, prints a one-line confirmation, and exits 0. Idempotent: running twice on an empty `index/` exits 0 with "nothing to prune".
- [ ] `cache prune-index --help` text states: "Deletes the per-repo SCIP binary at `.codegenie/index/scip-index.scip`. Next gather will full-re-index (~25 s). Use only when manual invalidation is needed."
- [ ] **No `--force` / `--all` / `-y` flags** on `cache prune-index` in this story. The command is intentionally narrow — one file, one effect. Extension by addition (e.g., a future `cache prune-index --include-cache-blobs`) lands as a separate story.
- [ ] `tests/unit/cli/test_cache_gc_preserves_index.py` red test exists, was committed failing, is now green. Asserts: (a) populate `.codegenie/cache/blobs/x.msgpack` (stale per LRU) + `.codegenie/index/scip-index.scip`; (b) run `cache gc`; (c) the cache blob is removed per LRU rules **and** the SCIP binary survives unchanged (`Path.stat().st_size` + content hash unchanged).
- [ ] `tests/unit/cli/test_cache_prune_index.py` red test exists and is now green. Asserts: (a) populate `.codegenie/index/scip-index.scip`; run `cache prune-index`; the file is gone, exit 0; (b) re-run on empty `index/`; exits 0 with "nothing to prune" message; (c) `.codegenie/cache/blobs/x.msgpack` is **not** touched by `cache prune-index` (the inverse invariant).
- [ ] `tests/unit/cli/test_cache_gc_help_text.py`: invokes `cache gc --help`, asserts the help string contains the substring "per-repo SCIP binary" and "`cache prune-index`" — pins the distinction in user-facing text.
- [ ] `docs/contributing.md` gets one bullet appended under whatever caching-related section exists (or at the bottom of the file if no section exists yet): "`.codegenie/index/` is per-repo and survives `cache gc`; use `cache prune-index` to delete the SCIP binary manually." The full Phase 2 cheat sheet lands in S8-06; this story adds only the one bullet.
- [ ] Definition-of-done items hold: `ruff check`, `ruff format --check`, `mypy --strict` on `src/codegenie/cli.py`, `pytest tests/unit/cli/test_cache_gc_preserves_index.py tests/unit/cli/test_cache_prune_index.py tests/unit/cli/test_cache_gc_help_text.py -q` all pass.
- [ ] No other CLI command's behavior changes. The diff is additive: one help-text edit on `cache gc`, one new `cache prune-index` subcommand, one bullet in `contributing.md`. No refactor of `cache gc`'s walk logic beyond *narrowing* its root path.

## Implementation outline

1. **Find `cache gc`'s walk root.** In `src/codegenie/cli.py` (or wherever Phase 0 implements the subcommand), the gc walks something like `repo_root / ".codegenie" / "cache"`. Verify that it does not walk `repo_root / ".codegenie"` (a parent walk would inadvertently include `index/`). If it does, narrow the root to `cache/` — surgical, single-line.
2. **Update the help text.** Click's `@click.command(help="...")` or docstring → add the "per-repo SCIP binary preserved; use `cache prune-index`" clause.
3. **Implement `cache prune-index`.** Click subcommand under the same `cache` group. Body:
   ```python
   target = repo_root / ".codegenie" / "index" / "scip-index.scip"
   if target.exists():
       target.unlink()
       click.echo(f"Pruned {target.relative_to(repo_root)}")
   else:
       click.echo("Nothing to prune (.codegenie/index/scip-index.scip not present)")
   ```
   Exit 0 in both branches.
4. **Append the one bullet** to `docs/contributing.md`. Do not restructure the file; one paragraph addition.
5. **No coordinator changes.** This story does not touch `src/codegenie/coordinator/*` or any probe. The probe (S4-01) writes the binary; this story only governs deletion.

## TDD plan — red / green / refactor

### Red — failing test first

Path: `tests/unit/cli/test_cache_gc_preserves_index.py`

```python
"""Pins: cache gc preserves <repo>/.codegenie/index/scip-index.scip.
ADR-0013: per-repo binary lifecycle; never under cache/.
Traces to: phase-arch-design.md §Component design #17."""

import hashlib
from pathlib import Path
from click.testing import CliRunner
from codegenie.cli import cli

def test_cache_gc_does_not_touch_index(tmp_path):
    # Seed cache/ (eligible for LRU eviction) and index/scip-index.scip (must survive).
    (tmp_path / ".codegenie" / "cache" / "blobs").mkdir(parents=True)
    stale_blob = tmp_path / ".codegenie" / "cache" / "blobs" / "stale.msgpack"
    stale_blob.write_bytes(b"x" * 16)
    # Make it look old enough for LRU to evict (touch ctime/atime far back if needed).
    import os, time
    old = time.time() - 365 * 24 * 3600
    os.utime(stale_blob, (old, old))

    (tmp_path / ".codegenie" / "index").mkdir(parents=True)
    scip = tmp_path / ".codegenie" / "index" / "scip-index.scip"
    scip.write_bytes(b"\x00\x01\x02SCIPpayloadbytes")
    before_hash = hashlib.sha256(scip.read_bytes()).hexdigest()

    runner = CliRunner()
    result = runner.invoke(cli, ["cache", "gc"], catch_exceptions=False,
                           env={"CODEGENIE_REPO_ROOT": str(tmp_path)})
    assert result.exit_code == 0
    assert scip.is_file()
    assert hashlib.sha256(scip.read_bytes()).hexdigest() == before_hash
```

Path: `tests/unit/cli/test_cache_prune_index.py`

```python
def test_prune_index_removes_scip_only(tmp_path):
    (tmp_path / ".codegenie" / "cache" / "blobs").mkdir(parents=True)
    blob = tmp_path / ".codegenie" / "cache" / "blobs" / "x.msgpack"
    blob.write_bytes(b"keep")
    (tmp_path / ".codegenie" / "index").mkdir(parents=True)
    scip = tmp_path / ".codegenie" / "index" / "scip-index.scip"
    scip.write_bytes(b"\x00\x01\x02")

    runner = CliRunner()
    result = runner.invoke(cli, ["cache", "prune-index"], catch_exceptions=False,
                           env={"CODEGENIE_REPO_ROOT": str(tmp_path)})
    assert result.exit_code == 0
    assert not scip.exists()
    assert blob.is_file()  # cache/ untouched

def test_prune_index_idempotent_on_empty(tmp_path):
    (tmp_path / ".codegenie" / "index").mkdir(parents=True)
    runner = CliRunner()
    result = runner.invoke(cli, ["cache", "prune-index"], catch_exceptions=False,
                           env={"CODEGENIE_REPO_ROOT": str(tmp_path)})
    assert result.exit_code == 0
    assert "Nothing to prune" in result.output or "nothing to prune" in result.output
```

Path: `tests/unit/cli/test_cache_gc_help_text.py`

```python
def test_cache_gc_help_documents_index_distinction():
    runner = CliRunner()
    result = runner.invoke(cli, ["cache", "gc", "--help"])
    assert result.exit_code == 0
    assert "per-repo SCIP binary" in result.output
    assert "cache prune-index" in result.output
```

Run `pytest tests/unit/cli/test_cache_gc_preserves_index.py tests/unit/cli/test_cache_prune_index.py tests/unit/cli/test_cache_gc_help_text.py -q`. Expect all red — the `prune-index` subcommand doesn't exist; the help text doesn't mention the distinction; the gc may currently walk the parent `.codegenie/` directory.

### Green — smallest impl shape

1. Narrow `cache gc`'s walk root to `.codegenie/cache/` (one line).
2. Append the help-text clause to `cache gc`.
3. Add `cache prune-index` subcommand.
4. Append the bullet to `docs/contributing.md`.
5. Iterate to green.

### Refactor — bounded

- Extract a module-level constant `INDEX_NAMESPACE = Path(".codegenie/index")` and `CACHE_NAMESPACE = Path(".codegenie/cache")` in `src/codegenie/cli.py` — one source of truth for both subcommands.
- If `cache gc`'s walk root was previously a string concatenation, replace with the constant `CACHE_NAMESPACE`.
- Run `ruff format`, `ruff check`, `mypy --strict`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli.py` | Edit — narrow `cache gc` root to `.codegenie/cache/`; update help text; add `cache prune-index` subcommand |
| `docs/contributing.md` | Edit — append one bullet documenting the `.codegenie/cache/` vs `.codegenie/index/` lifecycle distinction |
| `tests/unit/cli/test_cache_gc_preserves_index.py` | New — SCIP binary survives `cache gc` |
| `tests/unit/cli/test_cache_prune_index.py` | New — `cache prune-index` deletes only the SCIP binary; idempotent |
| `tests/unit/cli/test_cache_gc_help_text.py` | New — help text pins the user-facing distinction |

## Out of scope

- **Phase 2 cheat sheet revamp** — handled by S8-06 (this story drops one bullet; the full cheat sheet lands later).
- **`cache prune-cache`, `cache prune-all`, `cache stats`, etc.** — extension by addition; not in scope. The narrow `cache prune-index` is the one new subcommand this story ships.
- **GC of `.codegenie/cache/<tool>/by-file/` sub-caches** — the LRU/access-time eviction for per-file findings is the responsibility of S7-01's cache module; this story does not redesign gc semantics.
- **Cross-repo SCIP index sharing** — explicitly out of scope (`.codegenie/index/` is per-repo by design).
- **CI canary asserting `cache gc` doesn't touch `index/`** — the unit test covers this for now; a future CI canary on a real fixture is a follow-up.
- **`SCIPIndexProbe`'s own write logic** — handled by S4-01.

## Notes for the implementer

- **The fix is one or two lines of real code change** (narrowing the gc walk root) + one help-text edit + one new ~10-line subcommand + one tests file + one bullet. If the diff balloons past ~80 lines of `src/codegenie/cli.py`, you are gold-plating. Re-read Rule 2.
- **`cache prune-index` is intentionally narrow.** No `--force` (the operation is already explicit), no `--all`, no recursive directory pruning. Future flags land as separate stories; resist scope creep.
- **The help text is load-bearing.** The user-facing CLI is the only place where the lifecycle distinction is visible to operators who haven't read ADR-0013. A misleading help string ("clears all cached data") would silently undo this story. Phrase it from the operator's mental model: "what does this command touch, and what does it spare?"
- **Idempotency on empty `index/`** matters because CI scripts may invoke `cache prune-index` defensively. An exit-non-zero on missing file would break that pattern.
- **Do not touch `SCIPIndexProbe`** — even if you spot something. The probe's write path is S4-01's surface; this story is the read/delete governance layer. Cross-story creep is the anti-pattern.
- **Click env var prefix.** Phase 0's CLI probably uses `CODEGENIE_REPO_ROOT` or similar for test injection; mirror whatever pattern exists. Don't introduce a new injection mechanism.
- **The single bullet in `contributing.md`** is intentionally minimal — if you find yourself rewriting the whole "Caching" section, stop. S8-06 owns the cheat sheet revamp; this story is one declarative sentence.
- A grep for `subprocess`, `import requests`, `import httpx` in your diff should return empty. The CLI is pure filesystem operations.
