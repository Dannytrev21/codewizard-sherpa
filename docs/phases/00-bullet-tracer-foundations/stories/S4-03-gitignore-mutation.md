# Story S4-03 — `.gitignore` mutation routine + flags

**Step:** Step 4 — Cut the vertical slice: CLI, `LanguageDetectionProbe`, fixtures, end-to-end smoke
**Status:** Ready
**Effort:** S
**Depends on:** S4-02
**ADRs honored:** ADR-0011, ADR-0012

## Context

The `.codegenie/` directory lands in any analyzed repo on the very first gather, and the design commits to "offer to add it to that repo's `.gitignore` on first run" (`CLAUDE.md` conventions; `phase-arch-design.md §Harness engineering — Idempotence`). Without this, every CI pipeline downstream of `codegenie gather` either picks up `.codegenie/` artifacts as untracked changes or contributors blindly `chmod -R 644 .codegenie/` to "fix" the perms (the bear-trap ADR-0011 explicitly calls out).

This story implements the TTY-prompted append, the non-TTY warn-and-skip path, and the two override flags `--auto-gitignore` / `--no-gitignore`. It also closes Phase 0 exit criterion #10 (`phase-arch-design.md §Goals`): both branches of the mutation path must be exercised in tests.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Control flow — Happy path` — the routine is called between tool-readiness check and `load_config`.
  - `../phase-arch-design.md §Edge cases` — row 8 (append failure on disk-full → warn + continue, gather succeeds).
  - `../phase-arch-design.md §Harness engineering — Idempotence` — idempotent on `.codegenie/` substring already present.
  - `../phase-arch-design.md §Component design — CLI` — global flags `--no-gitignore` and `--auto-gitignore`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0011-codegenie-directory-permissions-model.md` — ADR-0011 — the routine touches `<repo>/.gitignore`, **not** `.codegenie/`; the analyzed repo's `.gitignore` keeps its existing mode (call out explicitly in the ADR §Consequences).
  - `../ADRs/0012-subprocess-allowlist-chokepoint.md` — ADR-0012 — no subprocess; this is a pure-Python atomic append.
- **Source design:**
  - `../final-design.md §2.15` — the prompt routine spec; TTY vs non-TTY policy.
- **Existing code:**
  - `src/codegenie/cli.py` — the entry point in S4-02; this story replaces the stub call site with the real routine.
  - `src/codegenie/logging.py` — the `gitignore.append.*` event names live alongside the `probe.*` constants from S2-01.
  - `src/codegenie/errors.py` — no new error type needed; append failures degrade to a structured warning.

## Goal

`codegenie gather <path>` on a repo whose `<path>/.gitignore` lacks `.codegenie/` prompts the user (TTY) or warns and continues (non-TTY); on accept, appends `.codegenie/\n` atomically; `--auto-gitignore` and `--no-gitignore` override the prompt; second invocation is a no-op.

## Acceptance criteria

- [ ] `src/codegenie/cli.py` (or a new `src/codegenie/output/gitignore.py` helper imported by the CLI) exposes `maybe_append_gitignore(repo_root: Path, *, auto: bool, never: bool, is_tty: bool) -> None`. The function is the single call site for the routine.
- [ ] Idempotence: if `<repo>/.gitignore` already contains a line matching `^\.codegenie/?\s*$` (or `.codegenie/` as a substring on a line, per `phase-arch-design.md §Harness engineering`), the routine logs `gitignore.append.idempotent` at DEBUG and returns without writing.
- [ ] TTY-accept path: with `is_tty=True` and `auto=never=False`, the routine prompts (`click.confirm("Append .codegenie/ to .gitignore?", default=True)`); on accept, atomically appends `.codegenie/\n` and emits `gitignore.append.accepted`.
- [ ] TTY-decline path: same prompt; on decline, no write, emit `gitignore.append.declined` at INFO.
- [ ] Non-TTY skip path: with `is_tty=False` and `auto=never=False`, no prompt; emit a structured warning `gitignore.append.skipped` at WARNING with `reason="non_tty"`. Do **not** mutate the file.
- [ ] `--auto-gitignore` (i.e., `auto=True`): no prompt; always append (atomically; idempotent if already present); emit `gitignore.append.accepted` with `reason="auto_flag"`.
- [ ] `--no-gitignore` (i.e., `never=True`): no prompt; never write; emit `gitignore.append.skipped` at DEBUG with `reason="never_flag"`.
- [ ] Append failure (edge case #8): a simulated `OSError` mid-write does **not** raise to the caller. Emit `gitignore.append.failed` at WARNING with the exception class name; gather continues. The caller (`codegenie gather`) exits 0 unless probes themselves failed.
- [ ] Atomic write: append uses `<repo>/.gitignore.tmp` → write existing content + new line → `fsync` → `os.replace`. Never `open(..., "a")` without atomicity.
- [ ] If `<repo>/.gitignore` does not exist, the routine creates it (with `.codegenie/\n` as its sole content) only on accept/auto; not on decline/skip. The new file's mode is the platform default for `os.open` (typically `0644` after umask) — **not** `0600`; the analyzed repo's `.gitignore` is **not** under `.codegenie/` per ADR-0011.
- [ ] `tests/unit/test_gitignore_mutation.py` is the red-test anchor; all six branches (TTY-accept, TTY-decline, non-TTY-skip, `--auto-gitignore`, `--no-gitignore`, append-failure, idempotent) are covered.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` (on the new module), and `pytest tests/unit/test_gitignore_mutation.py -q` all pass.

## Implementation outline

1. Add the helper `maybe_append_gitignore(repo_root, *, auto, never, is_tty)` (location: either `src/codegenie/output/gitignore.py` or inline in `cli.py` — prefer the new module so `cli.py` stays at the lazy-import boundary).
2. Branch on `never`, then `auto`, then `is_tty`. Each branch corresponds to one acceptance criterion bullet.
3. For the write path: read `<repo>/.gitignore` if it exists (text mode, default encoding); check for the `.codegenie/` line via a small regex (`re.compile(r"^\.codegenie/?\s*$", re.MULTILINE)` against the file content, or substring match — pick one and document); if present, return without writing; otherwise compose new content as `existing + "\n.codegenie/\n"` (or just `".codegenie/\n"` if file doesn't exist) and write atomically (`<repo>/.gitignore.tmp` → `fsync` → `os.replace`).
4. Wrap the write in try/except `OSError`; on failure, emit `gitignore.append.failed` and return (do not re-raise).
5. From `cli.py`'s `gather` command body (S4-02), determine `is_tty` via `sys.stdin.isatty() and sys.stdout.isatty()`; read `auto`/`never` from the parsed `click.Context.obj`; call `maybe_append_gitignore(repo_root, auto=auto, never=never, is_tty=is_tty)`.
6. Replace the stub installed in S4-02 with this real implementation.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_gitignore_mutation.py`

```python
# tests/unit/test_gitignore_mutation.py
import pytest
from pathlib import Path

# Helper to import the function — fails before the module exists.
def _load():
    from codegenie.output.gitignore import maybe_append_gitignore  # ModuleNotFoundError until green
    return maybe_append_gitignore

def test_tty_accept_appends_codegenie(tmp_path, monkeypatch):
    # arrange: existing .gitignore without .codegenie; simulate TTY-accept
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    monkeypatch.setattr("click.confirm", lambda *a, **k: True)
    # act
    _load()(tmp_path, auto=False, never=False, is_tty=True)
    # assert
    content = (tmp_path / ".gitignore").read_text()
    assert ".codegenie/" in content

def test_tty_decline_does_not_mutate(tmp_path, monkeypatch):
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    monkeypatch.setattr("click.confirm", lambda *a, **k: False)
    _load()(tmp_path, auto=False, never=False, is_tty=True)
    assert (tmp_path / ".gitignore").read_text() == "node_modules/\n"

def test_non_tty_logs_warning_and_skips(tmp_path, caplog):
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    _load()(tmp_path, auto=False, never=False, is_tty=False)
    # assert: file unchanged + structured warning emitted
    assert (tmp_path / ".gitignore").read_text() == "node_modules/\n"
    assert any("gitignore.append.skipped" in rec.message for rec in caplog.records)

def test_auto_flag_appends_without_prompt(tmp_path):
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    _load()(tmp_path, auto=True, never=False, is_tty=False)
    assert ".codegenie/" in (tmp_path / ".gitignore").read_text()

def test_never_flag_never_writes(tmp_path):
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    _load()(tmp_path, auto=False, never=True, is_tty=True)
    assert (tmp_path / ".gitignore").read_text() == "node_modules/\n"

def test_idempotent_when_already_present(tmp_path, monkeypatch):
    (tmp_path / ".gitignore").write_text("node_modules/\n.codegenie/\n")
    # Even on TTY-accept, the file should not change.
    monkeypatch.setattr("click.confirm", lambda *a, **k: True)
    _load()(tmp_path, auto=False, never=False, is_tty=True)
    assert (tmp_path / ".gitignore").read_text() == "node_modules/\n.codegenie/\n"

def test_append_failure_does_not_raise(tmp_path, monkeypatch, caplog):
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    # arrange: monkeypatch os.replace to raise OSError mid-publish
    import os
    monkeypatch.setattr("os.replace", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    # act + assert: does not raise; warning logged
    _load()(tmp_path, auto=True, never=False, is_tty=False)
    assert any("gitignore.append.failed" in rec.message for rec in caplog.records)
```

Run these — first failure is `ModuleNotFoundError: No module named 'codegenie.output.gitignore'`. Commit the failing tests as the red marker.

### Green — make it pass

Add `src/codegenie/output/gitignore.py` exporting `maybe_append_gitignore`. Straight-line `if/elif` branches per the acceptance criteria — resist building a state machine (per `High-level-impl.md §Step 4 risks specific to this step`). Minimal logging via `structlog.get_logger("codegenie.gitignore")`. Atomic write via the `<tmp> → fsync → os.replace` pattern from the Writer in S3-03.

### Refactor — clean up

- Add a module docstring referencing edge case #8 and `CLAUDE.md`'s "offer to add to `.gitignore` on first run" convention.
- Type hints throughout; `mypy --strict` clean on the new module.
- Confirm `cli.py` calls the real helper (not the stub) — the stub from S4-02 is now dead code; delete it (surgical change, not adjacent-cleanup; the stub explicitly existed to be replaced).
- Confirm structlog event names match the four `gitignore.append.*` events declared in `logging.py` (extend `logging.py`'s event-name constants if S2-01 did not already include them; bind the new names to `gitignore.append.accepted | declined | skipped | idempotent | failed`).
- Re-run the test file end-to-end; all seven tests pass.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/output/gitignore.py` | New file — implements `maybe_append_gitignore` per edge case #8 and `final-design.md §2.15` |
| `src/codegenie/cli.py` | Replace the S4-02 stub with the real helper call inside the `gather` command body |
| `src/codegenie/logging.py` | Add the five `gitignore.append.*` event-name constants alongside the `probe.*` family (if not already declared in S2-01) |
| `tests/unit/test_gitignore_mutation.py` | New test — anchors all seven branches |

## Out of scope

- **CLI `gather` startup wiring beyond the call site** — handled by story S4-02. This story implements the helper; S4-02 invokes it.
- **End-to-end smoke test that exercises the helper across a real `codegenie gather` invocation** — handled by story S4-04 (one of its sub-tests covers TTY-accept and non-TTY-skip via the full CLI path).
- **Permission discipline on the analyzed repo's `.gitignore`** — per ADR-0011 §Consequences, this file is **not** under `.codegenie/` and keeps the platform default mode. Do not `chmod 0600` it.
- **Atomic gitignore append for concurrent CLI invocations** — Phase 0 has the single-process invariant; Phase 14's webhook fan-out re-evaluates the contention model (and at that point the analyzed repo's `.gitignore` is already set).
- **Internationalized prompt text** — `click.confirm`'s default English string is fine for Phase 0.

## Notes for the implementer

- Per `High-level-impl.md §Step 4 risks specific to this step`: resist building a state machine for the branches. Straight-line `if never: ... elif auto: ... elif is_tty: ... else: ...` keeps the code readable and testable. A state-machine refactor is the wrong abstraction for six branches.
- Per ADR-0011 §Consequences: the analyzed repo's `.gitignore` is **not** under `.codegenie/`. It keeps the platform default mode. Do **not** `os.chmod 0600` on it; an explicit comment in the code preventing future drift is worth the line.
- The `.codegenie/` substring check must operate at the line granularity, not the file substring level — otherwise a comment like `# do not commit .codegenie/ in real builds` falsely registers as "already present." Use the regex from `phase-arch-design.md §Harness engineering — Idempotence` (`^\.codegenie/?\s*$` with `re.MULTILINE`) or `splitlines()` + strip.
- The atomic-write pattern is the same one used by `output/writer.py` in S3-03 — `<tmp>` → `os.fsync(fd)` → `os.replace(tmp, dst)`. Reuse the shape; do **not** import the Writer's helpers (avoid coupling: the gitignore writer's atomicity is independent of the YAML writer's symlink-refusal logic).
- `is_tty` is plumbed in from the CLI (`sys.stdin.isatty() and sys.stdout.isatty()`) — passing it as a parameter rather than calling `sys.stdin.isatty()` inside the helper keeps the test using `monkeypatch.setattr` over `sys.stdin` unnecessary; the tests in the red plan pass `is_tty` directly.
- `click.confirm` is only imported when `is_tty=True` and `auto=False` and `never=False` — but `click` is already imported at the top of `cli.py`, so the lazy-import boundary is unaffected. If you put the helper in `src/codegenie/output/gitignore.py`, `import click` at module top is fine (the lazy boundary is `cli.py`, not the rest of the package).
- The append-failure path is the load-bearing edge case (#8): a gather that fails to mutate `.gitignore` must **not** exit non-zero. Probe runs are what determine exit codes; the gitignore append is a courtesy. The test `test_append_failure_does_not_raise` pins this — do not let it regress.
