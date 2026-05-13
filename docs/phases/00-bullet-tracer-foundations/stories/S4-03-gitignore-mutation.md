# Story S4-03 — `.gitignore` mutation routine + flags

**Step:** Step 4 — Cut the vertical slice: CLI, `LanguageDetectionProbe`, fixtures, end-to-end smoke
**Status:** Done (2026-05-13)
**Effort:** S→M (test surface grew under validation)
**Depends on:** S4-02
**ADRs honored:** ADR-0011, ADR-0012
**Validated by:** phase-story-validator (see `_validation/S4-03-gitignore-mutation.md`)

## Evidence

- Helper: [`src/codegenie/output/gitignore.py`](../../../../src/codegenie/output/gitignore.py)
- Tests: [`tests/unit/test_gitignore_mutation.py`](../../../../tests/unit/test_gitignore_mutation.py) — 29 tests (AC-1..AC-23, AC-18 deferred per Out-of-scope §2)
- CLI wiring: [`src/codegenie/cli.py`](../../../../src/codegenie/cli.py) — `_seam_maybe_append_gitignore` + group-callback mutual-exclusivity guard
- Event constants: [`src/codegenie/logging.py`](../../../../src/codegenie/logging.py) — 5 new `GITIGNORE_APPEND_*` constants
- Toolchain: `pytest -q` → 568 passed (93.30% total coverage; 97% lines / 100% branches on the new module); `ruff check`, `ruff format --check`, `mypy --strict src/codegenie`, `lint-imports` all clean
- Smoke (Ralph Wiggum): `codegenie --auto-gitignore gather /tmp/rw_smoke` byte-exact appended canonical block; second run mtime-unchanged (`gitignore.append.idempotent` DEBUG); `--auto-gitignore --no-gitignore` exits 2 with "mutually exclusive"; `--no-gitignore` emits `gitignore.append.skipped reason=never_flag` DEBUG.
- Attempt log: [`_attempts/S4-03.md`](_attempts/S4-03.md)

## Divergences from the validated story

1. **AC-22 capture mechanism — `structlog.testing.capture_logs` instead of `capsys + json.loads`.** capsys rotates `sys.stdout`/`sys.stderr` between fixture setup and the test body, silently losing the `monkeypatch.setattr(sys.stdin, "isatty", lambda: True)` calls AND closing the structlog `PrintLogger`'s cached stderr ref ("I/O operation on closed file" — surfaced at runtime under pytest). `structlog.testing.capture_logs` swaps the structlog processor chain in-process, is immune to both bugs, and is already the codebase's pattern for unit-test event assertions (see [`tests/unit/test_cli_orchestration.py:124`](../../../../tests/unit/test_cli_orchestration.py) and [`tests/unit/test_cli_flags.py`](../../../../tests/unit/test_cli_flags.py)'s `test_cache_gc_stub_emits_exact_event_name`). The `level` field becomes `log_level` in capture_logs output — every assertion was updated. Rule 11 — match the codebase — survives because two existing S4-02 tests already use this pattern.
2. **CLI seam rename — `_seam_gitignore_mutation_stub` → `_seam_maybe_append_gitignore`.** S4-02 introduced an entire `_seam_*` family for the gather pipeline; the renamed seam stays in that family rather than becoming a bare direct call. The thin seam delegates to `codegenie.output.gitignore.maybe_append_gitignore` via `importlib.import_module` (the helper transitively imports `structlog`, which the cli.py `forbidden_modules` contract bans as an AST-visible import — same pattern as every other seam in S4-02).
3. **`_logger()` call-time resolver in the helper.** A module-level `_log = structlog.get_logger(__name__)` binds the proxy's underlying PrintLogger to whatever `sys.stderr` is at import time. Under pytest that's the very first test's `CaptureIO`, which gets closed when that test ends. Resolving the logger per call costs one extra dict lookup and stays correct across the lifecycle. Production cost is negligible (the helper runs once per gather invocation).

## Validation notes (2026-05-13)

Three critics (coverage, test-quality, consistency) flagged the v1 of this story as substantially under-specified for autonomous execution. Edits applied in place:

1. **Signature aligned with S4-02 AC-14.** v1 introduced `(auto, never, is_tty)`; S4-02 AC-14 explicitly pins `_gitignore_mutation_stub(repo_root: Path, *, auto: bool, skip: bool) -> None` and promises *"S4-03 replaces the body without changing the signature."* This story now keeps the pinned signature `(*, auto: bool, skip: bool) -> None`; TTY detection happens *inside* the helper via `sys.stdin.isatty() and sys.stdout.isatty()`. Tests monkeypatch those two functions on the helper module — the cost is small and the contract with S4-02 stays intact (Rule 11: consistency wins over taste).
2. **Comment-line body restored.** v1 dropped the courtesy comment line that `final-design.md §2.15` mandates ("`# codewizard-sherpa generated artifacts; safe to delete`"). The Goal, ACs, and TDD plan now pin the byte-exact appended block.
3. **Atomic-write contract is now testable.** v1 claimed "atomic" but no test would have caught an `open(path, "a")` mutation. New ACs and tests spy on `os.replace`/`os.fsync` and assert tmp-file cleanup on every failure point (`open`, `write`, `fsync`, `replace`).
4. **Mutation-resistant assertions throughout.** Exact-bytes content assertions replace `".codegenie/" in content`; `click.confirm` call spies replace silent monkeypatches; structlog-stderr JSON capture replaces wrong `caplog.message` assertions (matches `tests/unit/test_logging.py`'s existing pattern — Rule 11).
5. **Missing branches added.** Seven new branches: file-not-exist × 4 (accept/auto/decline/non-TTY), conflicting-flags (`--auto-gitignore` + `--no-gitignore` is a `click.UsageError`), comment-line false-positive, two-call metamorphic, empty-file, CRLF idempotence, non-regular-file refusal (symlink/directory/fifo).
6. **Conflict resolution — line-regex over substring.** `phase-arch-design.md §Harness engineering — Idempotence` (line 757) says "substring"; story uses line-anchored regex `^\.codegenie/?\s*$` to avoid false positives from prose comments. Resolution: story improves the arch contract. The arch line is queued for a one-line amendment in the same PR. Documented as a known divergence, not a violation.
7. **Stale event-name in `final-design.md §2.15` superseded.** v1 of `final-design.md` names `gitignore.codegenie.not_present` for the non-TTY skip; the `gitignore.append.*` family from `phase-arch-design.md §Edge case #8` wins. Same-PR amendment to `final-design.md §2.15` queued.
8. **Skip-event level discipline.** Both `non_tty` and `never_flag` reasons share the `gitignore.append.skipped` event; the AC now pins per-reason log levels (`non_tty` → WARNING, `never_flag` → DEBUG) and tests assert level + reason together.

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

`codegenie gather <path>` on a repo whose `<path>/.gitignore` lacks `.codegenie/` prompts the user (TTY) or skips with a structured warning (non-TTY); on accept, atomically appends the exact two-line block `# codewizard-sherpa generated artifacts; safe to delete\n.codegenie/\n` (preserving prior content; injecting a leading `\n` only if the existing file does not end with one); `--auto-gitignore` and `--no-gitignore` override the prompt and are mutually exclusive at the CLI layer; a second invocation under any flag combination is a true no-op (no rewrite, `mtime` unchanged).

## Acceptance criteria

### Surface & signature (must match S4-02 AC-14)

- [x] **AC-1 (signature).** `src/codegenie/output/gitignore.py` exposes `maybe_append_gitignore(repo_root: Path, *, auto: bool, skip: bool) -> None`. The signature matches the stub pinned by S4-02 AC-14 byte-for-byte; an `inspect.signature` test (`test_signature_matches_s4_02_stub`) asserts the exact parameter names, kinds (keyword-only after `repo_root`), and annotations. `cli.py`'s `_gitignore_mutation_stub` is deleted; `cli.py` imports and calls `maybe_append_gitignore` directly.
- [x] **AC-2 (TTY detection is internal).** TTY-ness is computed inside the helper as `is_tty = sys.stdin.isatty() and sys.stdout.isatty()`. Both gates are required; a test monkeypatches `sys.stdin.isatty`/`sys.stdout.isatty` on the helper's module and asserts the TTY branch fires only when both return `True`.

### Six branches — exact event names, levels, and `reason` fields

- [x] **AC-3 (TTY-accept).** With `auto=False`, `skip=False`, both isattys `True`: the routine prompts via `click.confirm("Append .codegenie/ to .gitignore?", default=True)`. On accept, it atomically appends the canonical two-line block (see AC-9). It emits exactly one structlog event `gitignore.append.accepted` at INFO with `reason="tty_accept"`.
- [x] **AC-4 (TTY-decline).** Same prompt; on decline, the file is byte-identical and `mtime` unchanged. Emits exactly one `gitignore.append.declined` event at INFO with `reason="tty_decline"`. `click.confirm` is called exactly once (verified by spy).
- [x] **AC-5 (non-TTY skip).** With `auto=False`, `skip=False`, either isatty `False`: no prompt is shown (`click.confirm` is never called — verified by spy). File untouched. Emits exactly one `gitignore.append.skipped` event at **WARNING** with `reason="non_tty"`.
- [x] **AC-6 (`--auto-gitignore` / `auto=True`).** No prompt (`click.confirm` spy records zero calls even with isatty `True`). Append happens atomically and is idempotent (see AC-7). Emits exactly one `gitignore.append.accepted` at INFO with `reason="auto_flag"`.
- [x] **AC-7 (`--no-gitignore` / `skip=True`).** No prompt, no write. Emits exactly one `gitignore.append.skipped` event at **DEBUG** with `reason="never_flag"`. `skip=True` takes precedence over `auto=True` (see AC-15).
- [x] **AC-8 (idempotent — pre-existing marker).** If `<repo>/.gitignore` already contains a line matching `^\.codegenie/?\s*$` under `re.MULTILINE` (line-anchored, not file-substring — see AC-11), the routine emits `gitignore.append.idempotent` at **DEBUG** and returns. No write, no `mtime` change, regardless of `auto`/`skip`/`is_tty` combination (except `skip=True` short-circuits before the check and emits `never_flag` instead).

### Write contract (byte-exact, atomic, regular-file-only)

- [x] **AC-9 (byte-exact appended block).** On accept/auto, the canonical block written is the exact 71 bytes: `b"# codewizard-sherpa generated artifacts; safe to delete\n.codegenie/\n"`. If the existing `.gitignore` content does not end with `\n`, the routine prepends a single `\n` before the comment line. If the existing content is empty (zero bytes) or the file does not exist, the canonical block is the sole content. Tests assert byte-exact final content (`assert content == b"..."`) for all three cases.
- [x] **AC-10 (atomic write).** The write path is: open `<repo>/.gitignore.tmp` with `os.open(..., O_WRONLY | O_CREAT | O_TRUNC)` (or `Path.open("w")`), write the composed content, call `os.fsync(fd)`, close, then `os.replace(<tmp>, <dst>)`. A test (`test_uses_atomic_replace_pattern`) spies on `os.fsync` and `os.replace` and asserts both are invoked exactly once per write call, with `os.replace` invoked AFTER `os.fsync` on the tmp path. A direct `open(path, "a")` mutation must fail this test.
- [x] **AC-11 (line-anchored idempotence — false-positive guard).** The idempotence check matches `^\.codegenie/?\s*$` per line (compiled with `re.MULTILINE`) — NOT a file-level substring. A `.gitignore` whose only mention of `.codegenie/` is inside a comment (e.g., `# do not commit .codegenie/ in real builds\n`) is NOT treated as idempotent and triggers the append. Test `test_codegenie_inside_comment_is_not_idempotent` pins this with byte-exact assertions on the post-write content (comment preserved, canonical block appended).
- [x] **AC-12 (non-regular file refusal).** If `<repo>/.gitignore` exists and is not a regular file (symlink, directory, fifo, socket, device), the routine emits `gitignore.append.skipped` at WARNING with `reason="unsafe_path"` and does NOT mutate or follow the link. Verification uses `Path(path).is_symlink()` first (refuses *symlinks* even if they point to regular files — the analyzed repo's `.gitignore` is the only file outside `.codegenie/` we ever touch, per ADR-0011, so we are explicit about the policy), then `Path(path).exists() and not Path(path).is_file()` to catch directories/fifos. Test parameterized over symlink + directory.
- [x] **AC-13 (CRLF idempotence).** A `.gitignore` whose contents are `b"node_modules/\r\n.codegenie/\r\n"` is recognized as idempotent — no rewrite (`\s` in the regex swallows `\r`). Test `test_idempotent_with_crlf_line_endings` pins this. A `.gitignore` ending in `\r\n` on a non-idempotent path appends correctly (no double-newline regression).
- [x] **AC-14 (file does not exist — four sub-cases).** If `<repo>/.gitignore` does not exist:
  - `auto=False, skip=False, is_tty=True` + confirm `True` → file created with sole content equal to the canonical 71-byte block. Event `gitignore.append.accepted` with `reason="tty_accept"`.
  - `auto=True, skip=False` → same as above with `reason="auto_flag"`.
  - `auto=False, skip=False, is_tty=True` + confirm `False` → file remains absent (`assert not path.exists()`). Event `gitignore.append.declined`.
  - `auto=False, skip=False, is_tty=False` → file remains absent. Event `gitignore.append.skipped` with `reason="non_tty"` at WARNING.
  Each sub-case has its own test.

### Failure handling — `mid-write` means at every point along the path

- [x] **AC-15 (conflicting flags).** Passing both `--auto-gitignore` and `--no-gitignore` to `codegenie gather` raises `click.UsageError("--auto-gitignore and --no-gitignore are mutually exclusive")` at the CLI layer *before* `maybe_append_gitignore` is invoked. The CLI exits with click's default usage-error code (2). A test in `tests/unit/test_cli_flags.py` (or piggybacked on this story's test file if simpler) pins this. The helper itself need not guard, but if both `auto` and `skip` are `True` when called directly, `skip` wins (no prompt, no write, `gitignore.append.skipped` with `reason="never_flag"`) — a `test_skip_beats_auto_at_helper_level` asserts the precedence so a future cli-bypass call site doesn't regress.
- [x] **AC-16 (mid-write failure cleanup — parameterized over four failure points).** `OSError` raised by any of `open(tmp, "w")`, `tmp_file.write(...)`, `os.fsync(fd)`, or `os.replace(tmp, dst)` is caught. The routine:
  1. Emits exactly one `gitignore.append.failed` event at WARNING with `exc_class` set to the exception's class name (e.g., `"OSError"`, `"PermissionError"`).
  2. Best-effort unlinks `<repo>/.gitignore.tmp` if it exists (wrapped in `try: ... except OSError: pass` — we don't fail-on-cleanup-failure).
  3. Returns `None` to the caller; does NOT re-raise; the analyzed `<repo>/.gitignore` is byte-identical to its pre-call state.
  Test `test_append_failure_at_each_step_cleans_up_tmp` is parameterized over the four failure points; each asserts (a) no exception escapes, (b) `not (repo / ".gitignore.tmp").exists()` after the call, (c) original `.gitignore` content unchanged, (d) the warning event with the correct `exc_class`.
- [x] **AC-17 (non-OS exceptions propagate).** `KeyboardInterrupt`, `SystemExit`, and any non-`OSError` exception raised inside the helper are NOT swallowed; they propagate to the caller. A test (`test_keyboard_interrupt_propagates`) monkeypatches `os.replace` to raise `KeyboardInterrupt` and asserts the routine re-raises via `pytest.raises(KeyboardInterrupt)`. Defends against an over-broad `except Exception` mutation.
- [x] **AC-18 (gather exit code unaffected).** Edge case #8 invariant: a `.gitignore`-append failure does NOT change `codegenie gather`'s exit code. Gather still exits 0 on probe success or 2 on probe failure — never on the gitignore append. Pinned by an integration assertion in S4-04's smoke test; this story restates the contract in the implementer notes and does not re-test at the CLI level (per Out-of-scope §2).

### Metamorphic + permissions

- [x] **AC-19 (two-call no-op).** A second call with identical args, after a first call has appended, is a true no-op: byte-identical file content AND identical `mtime_ns`. Test `test_call_twice_is_metamorphic_noop` invokes the helper twice with `auto=True, skip=False` on a fresh fixture; the second call must not rewrite the file (`mtime_ns` equality is the strict pin). This is `f(f(x)) == f(x)` and is the single test that catches the most write-path mutations.
- [x] **AC-20 (file mode per ADR-0011).** When the helper *creates* `<repo>/.gitignore` (AC-14 paths a/b), the new file's mode is the platform default after umask (typically `0644` on Linux/macOS) — the helper does NOT call `os.chmod`. This matches ADR-0011 §Consequences bullet 4: the analyzed repo's `.gitignore` is NOT under `.codegenie/` and keeps its default mode. A test on Linux/macOS asserts `(repo / ".gitignore").stat().st_mode & 0o777 == 0o644 & ~os.umask(0)` (or accepts `0o600 / 0o644 / 0o664` to tolerate test-runner umask differences — comment the rationale).

### Logging & toolchain

- [x] **AC-21 (event-name constants in `logging.py`).** `src/codegenie/logging.py` declares the five event-name constants `GITIGNORE_APPEND_ACCEPTED`, `..._DECLINED`, `..._SKIPPED`, `..._IDEMPOTENT`, `..._FAILED` alongside the `probe.*` family from S2-01. The helper imports and uses these constants — no raw strings in the helper body. If S2-01 did not declare them, this story adds them; the resulting `logging.py` diff is part of this story's PR. A test in `tests/unit/test_logging.py` asserts the five constants exist with their canonical string values.
- [x] **AC-22 (structlog stderr/JSON capture in tests).** Tests follow the existing precedent set by `tests/unit/test_logging.py` (Rule 11 — match the codebase): logging is configured via `cgl.configure_logging(verbose=True)` to unmute DEBUG events; logs are captured via `capsys.readouterr().err`, then split on `\n`, then each non-empty line parsed via `json.loads`. Tests assert on `payload["event"]`, `payload["level"]`, and `payload["reason"]`/`payload["exc_class"]` — NOT on `caplog.records[i].message` (the std-logging API doesn't capture structlog's stderr stream correctly here).
- [x] **AC-23 (toolchain).** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/output/gitignore.py`, and `pytest tests/unit/test_gitignore_mutation.py -q` all pass. Coverage on the new module is ≥ 95% lines and ≥ 90% branches (the routine is small and every branch is reached by an AC test).

## Implementation outline

1. **Create `src/codegenie/output/gitignore.py`** exporting `maybe_append_gitignore(repo_root: Path, *, auto: bool, skip: bool) -> None` — signature byte-for-byte equal to the S4-02 AC-14 stub. Module-level constants: `_CANONICAL_BLOCK = b"# codewizard-sherpa generated artifacts; safe to delete\n.codegenie/\n"`, `_TMP_NAME = ".gitignore.tmp"`, `_IDEMPOTENT_RE = re.compile(rb"^\.codegenie/?\s*$", re.MULTILINE)` (note: bytes-mode regex so we don't decode-then-fail on weird encodings).
2. **Branch order (precedence is contract — see AC-15):** `if skip: emit gitignore.append.skipped DEBUG reason=never_flag; return`. Then determine `is_tty = sys.stdin.isatty() and sys.stdout.isatty()`. Then:
   - existing path check: if `<repo>/.gitignore` exists and is a *symlink* OR (exists and is not a regular file) → emit `gitignore.append.skipped` WARNING `reason=unsafe_path`; return. (AC-12)
   - read existing bytes (or `b""` if absent); if `_IDEMPOTENT_RE.search(existing)` matches → emit `gitignore.append.idempotent` DEBUG; return. (AC-8, AC-13)
   - if `not auto and not is_tty` → emit `gitignore.append.skipped` WARNING `reason=non_tty`; return. (AC-5)
   - if `not auto`: call `click.confirm("Append .codegenie/ to .gitignore?", default=True)`; on `False` → emit `gitignore.append.declined` INFO `reason=tty_decline`; return. (AC-4)
   - compose new content: if `existing == b""` or `existing.endswith(b"\n")` → `existing + _CANONICAL_BLOCK`; else → `existing + b"\n" + _CANONICAL_BLOCK`. (AC-9)
   - write atomically (step 3); emit `gitignore.append.accepted` INFO with `reason="tty_accept"` (when `not auto`) or `reason="auto_flag"` (when `auto`). (AC-3, AC-6)
3. **Atomic write helper (local to the module, do NOT import from `output/writer.py` — AC-10 + impl note):**
   ```python
   tmp = repo_root / _TMP_NAME
   try:
       with tmp.open("wb") as f:
           f.write(new_content)
           f.flush()
           os.fsync(f.fileno())
       os.replace(tmp, repo_root / ".gitignore")
   except OSError as e:
       _emit_failed(e)
       try: tmp.unlink(missing_ok=True)
       except OSError: pass
       return
   ```
   Only `OSError` (and subclasses — `PermissionError`, `FileNotFoundError`, etc.) is caught. `KeyboardInterrupt`/`SystemExit`/any non-OS exception propagates (AC-17). On any failure, tmp is unlinked best-effort (AC-16).
4. **CLI wiring delta in `cli.py`:**
   - Delete `_gitignore_mutation_stub` (now dead — S4-02 only existed to give us a stable call site).
   - Add an `@cli.callback`/group-level invariant check: if `ctx.obj.get("auto_gitignore")` and `ctx.obj.get("no_gitignore")` are both `True`, raise `click.UsageError("--auto-gitignore and --no-gitignore are mutually exclusive")` (AC-15).
   - In the `gather` body, replace the stub call with `from codegenie.output.gitignore import maybe_append_gitignore; maybe_append_gitignore(repo_root, auto=ctx.obj["auto_gitignore"], skip=ctx.obj["no_gitignore"])`.
5. **Extend `src/codegenie/logging.py`** with the five `GITIGNORE_APPEND_*` constants (AC-21). The helper imports and uses them — no raw strings in the helper body.
6. **Update `tests/unit/test_logging.py`** (single-line change) to assert the five new constants exist (AC-21).

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/unit/test_gitignore_mutation.py`. All tests use `capsys` for structlog JSON (matches `tests/unit/test_logging.py` — Rule 11), `click.confirm` spies, byte-exact content assertions, and `mtime_ns` pinning where the contract says "no rewrite."

```python
# tests/unit/test_gitignore_mutation.py
"""Red tests for S4-03 (.gitignore mutation routine).

Pinned by AC-1..AC-23. Logging assertions follow tests/unit/test_logging.py:
configure_logging(verbose=True) -> capsys.readouterr().err -> json.loads(line).

WHY each test matters (Rule 9) is in each docstring; if you change behavior, fix
the test before the implementation.
"""
from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from typing import Any, Callable

import pytest

CANONICAL_BLOCK = b"# codewizard-sherpa generated artifacts; safe to delete\n.codegenie/\n"


def _load() -> Callable[..., None]:
    """Lazy import so ModuleNotFoundError is the first red marker."""
    from codegenie.output.gitignore import maybe_append_gitignore
    return maybe_append_gitignore


def _events(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    """Drain structlog JSON from stderr; matches test_logging.py pattern."""
    out = capsys.readouterr()
    events: list[dict[str, Any]] = []
    for line in out.err.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # ignore non-JSON pytest noise
    return events


@pytest.fixture(autouse=True)
def _configure_logging() -> None:
    """Unmute DEBUG so AC-7/AC-8 events are captured."""
    import codegenie.logging as cgl
    cgl.configure_logging(verbose=True)


@pytest.fixture
def both_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force is_tty=True at the helper's module boundary."""
    import codegenie.output.gitignore as g
    monkeypatch.setattr(g.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(g.sys.stdout, "isatty", lambda: True)


@pytest.fixture
def no_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    import codegenie.output.gitignore as g
    monkeypatch.setattr(g.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(g.sys.stdout, "isatty", lambda: False)


@pytest.fixture
def confirm_spy(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Replace click.confirm with a spy that returns True by default; tests can mutate."""
    calls: list[Any] = []
    def _spy(*args: Any, **kwargs: Any) -> bool:
        calls.append((args, kwargs))
        return calls.return_value if hasattr(calls, "return_value") else True
    # callers set calls.return_value to control the answer
    calls.return_value = True  # type: ignore[attr-defined]
    monkeypatch.setattr("click.confirm", _spy)
    return calls


# ---------- Surface ----------

def test_signature_matches_s4_02_stub() -> None:
    """AC-1: signature is locked to S4-02 AC-14's pinned stub."""
    fn = _load()
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    assert [p.name for p in params] == ["repo_root", "auto", "skip"]
    assert params[0].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert params[1].kind == inspect.Parameter.KEYWORD_ONLY
    assert params[2].kind == inspect.Parameter.KEYWORD_ONLY
    assert sig.return_annotation is None


def test_tty_detection_uses_both_stdin_and_stdout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                   confirm_spy: list, capsys) -> None:
    """AC-2: stdin-tty but stdout-pipe must take the non-TTY branch (CI prompt bug)."""
    import codegenie.output.gitignore as g
    monkeypatch.setattr(g.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(g.sys.stdout, "isatty", lambda: False)
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    _load()(tmp_path, auto=False, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n"
    assert confirm_spy == [], "must not prompt when stdout is not a tty"
    events = [e for e in _events(capsys) if e.get("event", "").startswith("gitignore.")]
    assert len(events) == 1
    assert events[0]["event"] == "gitignore.append.skipped"
    assert events[0]["reason"] == "non_tty"
    assert events[0]["level"] == "warning"


# ---------- Six core branches ----------

def test_tty_accept_appends_canonical_block_byte_exact(
    tmp_path: Path, both_tty: None, confirm_spy: list, capsys
) -> None:
    """AC-3 + AC-9: byte-exact append, comment line preserved, prior content untouched."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    _load()(tmp_path, auto=False, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n" + CANONICAL_BLOCK
    assert len(confirm_spy) == 1
    events = [e for e in _events(capsys) if e.get("event", "").startswith("gitignore.")]
    assert len(events) == 1
    assert events[0]["event"] == "gitignore.append.accepted"
    assert events[0]["reason"] == "tty_accept"
    assert events[0]["level"] == "info"


def test_tty_decline_byte_identical_and_no_mtime_change(
    tmp_path: Path, both_tty: None, confirm_spy: list, capsys
) -> None:
    """AC-4: decline path is a true no-op."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    before = (tmp_path / ".gitignore").stat().st_mtime_ns
    confirm_spy.return_value = False  # type: ignore[attr-defined]
    _load()(tmp_path, auto=False, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n"
    assert (tmp_path / ".gitignore").stat().st_mtime_ns == before
    assert len(confirm_spy) == 1
    events = [e for e in _events(capsys) if e.get("event", "").startswith("gitignore.")]
    assert any(e["event"] == "gitignore.append.declined" and e["reason"] == "tty_decline"
               and e["level"] == "info" for e in events)


def test_non_tty_skip_warns_and_does_not_prompt(
    tmp_path: Path, no_tty: None, confirm_spy: list, capsys
) -> None:
    """AC-5: non-TTY never prompts; emits WARNING with reason=non_tty."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    _load()(tmp_path, auto=False, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n"
    assert confirm_spy == [], "non-TTY must not prompt"
    events = [e for e in _events(capsys) if e.get("event", "").startswith("gitignore.")]
    assert any(e["event"] == "gitignore.append.skipped" and e["reason"] == "non_tty"
               and e["level"] == "warning" for e in events)


def test_auto_flag_appends_without_prompt_even_on_tty(
    tmp_path: Path, both_tty: None, confirm_spy: list, capsys
) -> None:
    """AC-6: auto bypasses confirm even when TTY is available (hostile case)."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    _load()(tmp_path, auto=True, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n" + CANONICAL_BLOCK
    assert confirm_spy == [], "auto flag must bypass click.confirm"
    events = [e for e in _events(capsys) if e.get("event", "").startswith("gitignore.")]
    assert any(e["event"] == "gitignore.append.accepted" and e["reason"] == "auto_flag" for e in events)


def test_skip_flag_never_writes_and_never_prompts(
    tmp_path: Path, both_tty: None, confirm_spy: list, capsys
) -> None:
    """AC-7: skip is the highest-precedence path; no prompt, no write, DEBUG event."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    before = (tmp_path / ".gitignore").stat().st_mtime_ns
    _load()(tmp_path, auto=False, skip=True)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n"
    assert (tmp_path / ".gitignore").stat().st_mtime_ns == before
    assert confirm_spy == []
    events = [e for e in _events(capsys) if e.get("event", "").startswith("gitignore.")]
    assert any(e["event"] == "gitignore.append.skipped" and e["reason"] == "never_flag"
               and e["level"] == "debug" for e in events)


def test_idempotent_pre_existing_marker_does_not_rewrite(
    tmp_path: Path, both_tty: None, confirm_spy: list, capsys
) -> None:
    """AC-8 + AC-19 stage-1: pre-existing line means no rewrite, mtime unchanged, idempotent event."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n.codegenie/\n")
    before = (tmp_path / ".gitignore").stat().st_mtime_ns
    confirm_spy.return_value = True  # would say yes; helper must not even ask
    _load()(tmp_path, auto=False, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n.codegenie/\n"
    assert (tmp_path / ".gitignore").stat().st_mtime_ns == before
    events = [e for e in _events(capsys) if e.get("event", "").startswith("gitignore.")]
    assert any(e["event"] == "gitignore.append.idempotent" and e["level"] == "debug" for e in events)


# ---------- Write contract: byte-exact, atomic, regular-file-only ----------

def test_no_trailing_newline_in_existing_file_gets_leading_newline(
    tmp_path: Path, both_tty: None, confirm_spy: list
) -> None:
    """AC-9: existing 'node_modules/' (no \\n) yields '...\\n# codewizard...\\n.codegenie/\\n'."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/")  # no trailing \n
    _load()(tmp_path, auto=True, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n" + CANONICAL_BLOCK


def test_empty_existing_gitignore_writes_canonical_block_as_sole_content(
    tmp_path: Path, both_tty: None, confirm_spy: list
) -> None:
    """AC-9: zero-byte existing file is treated like 'no leading content'; no blank prefix."""
    (tmp_path / ".gitignore").write_bytes(b"")
    _load()(tmp_path, auto=True, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == CANONICAL_BLOCK


def test_uses_atomic_replace_pattern(
    tmp_path: Path, both_tty: None, confirm_spy: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-10: spy on os.fsync and os.replace; both must fire; fsync before replace."""
    order: list[str] = []
    import codegenie.output.gitignore as g
    real_fsync = g.os.fsync
    real_replace = g.os.replace
    monkeypatch.setattr(g.os, "fsync", lambda fd: (order.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(g.os, "replace", lambda src, dst: (order.append("replace"), real_replace(src, dst))[1])
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    _load()(tmp_path, auto=True, skip=False)
    assert order == ["fsync", "replace"], "atomic write must fsync before replace"
    # Mutation-kill: open(path, 'a') would never call os.replace.


def test_codegenie_inside_comment_is_not_idempotent(
    tmp_path: Path, both_tty: None, confirm_spy: list
) -> None:
    """AC-11: false-positive guard. A comment mentioning '.codegenie/' must not block append."""
    initial = b"# do not commit .codegenie/ in real builds\n"
    (tmp_path / ".gitignore").write_bytes(initial)
    _load()(tmp_path, auto=True, skip=False)
    final = (tmp_path / ".gitignore").read_bytes()
    assert final == initial + CANONICAL_BLOCK
    assert final.count(b".codegenie/") == 2


@pytest.mark.parametrize("kind", ["symlink", "directory"])
def test_non_regular_gitignore_refused(
    tmp_path: Path, both_tty: None, confirm_spy: list, capsys, kind: str
) -> None:
    """AC-12: symlinks and directories trigger 'unsafe_path' skip, no mutation."""
    gi = tmp_path / ".gitignore"
    if kind == "symlink":
        target = tmp_path / "other.txt"
        target.write_bytes(b"node_modules/\n")
        gi.symlink_to(target)
    else:
        gi.mkdir()
    _load()(tmp_path, auto=True, skip=False)
    if kind == "symlink":
        # symlink intact, target unchanged
        assert gi.is_symlink()
        assert (tmp_path / "other.txt").read_bytes() == b"node_modules/\n"
    else:
        assert gi.is_dir()
    events = [e for e in _events(capsys) if e.get("event", "").startswith("gitignore.")]
    assert any(e["event"] == "gitignore.append.skipped" and e["reason"] == "unsafe_path"
               and e["level"] == "warning" for e in events)


def test_idempotent_with_crlf_line_endings(
    tmp_path: Path, both_tty: None, confirm_spy: list
) -> None:
    """AC-13: CRLF '.codegenie/\\r\\n' must register as idempotent via \\s in the regex."""
    initial = b"node_modules/\r\n.codegenie/\r\n"
    (tmp_path / ".gitignore").write_bytes(initial)
    before = (tmp_path / ".gitignore").stat().st_mtime_ns
    _load()(tmp_path, auto=True, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == initial
    assert (tmp_path / ".gitignore").stat().st_mtime_ns == before


# ---------- AC-14: file does not exist (four sub-cases) ----------

def test_no_gitignore_tty_accept_creates_file(
    tmp_path: Path, both_tty: None, confirm_spy: list
) -> None:
    """AC-14a"""
    _load()(tmp_path, auto=False, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == CANONICAL_BLOCK


def test_no_gitignore_auto_creates_file(
    tmp_path: Path, no_tty: None, confirm_spy: list
) -> None:
    """AC-14b"""
    _load()(tmp_path, auto=True, skip=False)
    assert (tmp_path / ".gitignore").read_bytes() == CANONICAL_BLOCK


def test_no_gitignore_tty_decline_does_not_create(
    tmp_path: Path, both_tty: None, confirm_spy: list
) -> None:
    """AC-14c"""
    confirm_spy.return_value = False
    _load()(tmp_path, auto=False, skip=False)
    assert not (tmp_path / ".gitignore").exists()


def test_no_gitignore_non_tty_does_not_create(
    tmp_path: Path, no_tty: None, confirm_spy: list, capsys
) -> None:
    """AC-14d"""
    _load()(tmp_path, auto=False, skip=False)
    assert not (tmp_path / ".gitignore").exists()
    events = [e for e in _events(capsys) if e.get("event", "").startswith("gitignore.")]
    assert any(e["event"] == "gitignore.append.skipped" and e["reason"] == "non_tty" for e in events)


# ---------- Failure handling (AC-15..AC-18) ----------

def test_skip_beats_auto_at_helper_level(
    tmp_path: Path, both_tty: None, confirm_spy: list, capsys
) -> None:
    """AC-15: if both auto and skip are True at the helper, skip wins (CLI should reject earlier)."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    before = (tmp_path / ".gitignore").stat().st_mtime_ns
    _load()(tmp_path, auto=True, skip=True)
    assert (tmp_path / ".gitignore").read_bytes() == b"node_modules/\n"
    assert (tmp_path / ".gitignore").stat().st_mtime_ns == before
    events = [e for e in _events(capsys) if e.get("event", "").startswith("gitignore.")]
    assert any(e["event"] == "gitignore.append.skipped" and e["reason"] == "never_flag" for e in events)


def test_conflicting_cli_flags_raise_usage_error() -> None:
    """AC-15: CLI rejects --auto-gitignore + --no-gitignore before helper invocation.

    Belongs in test_cli_flags.py philosophically but pinned here to avoid drift.
    """
    from click.testing import CliRunner
    from codegenie.cli import cli
    result = CliRunner().invoke(cli, ["--auto-gitignore", "--no-gitignore", "gather", "."])
    assert result.exit_code == 2  # click usage error
    assert "mutually exclusive" in result.output


@pytest.mark.parametrize("failure_point", ["open", "write", "fsync", "replace"])
def test_append_failure_at_each_step_cleans_up_tmp(
    tmp_path: Path, both_tty: None, confirm_spy: list, capsys,
    monkeypatch: pytest.MonkeyPatch, failure_point: str
) -> None:
    """AC-16: every step on the write path must clean up tmp on OSError and not raise."""
    initial = b"node_modules/\n"
    (tmp_path / ".gitignore").write_bytes(initial)
    import codegenie.output.gitignore as g

    if failure_point == "open":
        real_open = Path.open
        def _bad_open(self: Path, *a: Any, **kw: Any) -> Any:
            if self.name == ".gitignore.tmp":
                raise OSError("simulated open failure")
            return real_open(self, *a, **kw)
        monkeypatch.setattr(Path, "open", _bad_open)
    elif failure_point == "write":
        # Wrap the file object so write() raises after open succeeds.
        real_open = Path.open
        class _BadFile:
            def __init__(self, f: Any): self._f = f
            def __enter__(self): self._f.__enter__(); return self
            def __exit__(self, *a: Any): self._f.__exit__(*a)
            def write(self, _data: bytes) -> int: raise OSError("simulated write failure")
            def flush(self) -> None: pass
            def fileno(self) -> int: return self._f.fileno()
        def _wrap_open(self: Path, *a: Any, **kw: Any) -> Any:
            f = real_open(self, *a, **kw)
            if self.name == ".gitignore.tmp":
                return _BadFile(f)
            return f
        monkeypatch.setattr(Path, "open", _wrap_open)
    elif failure_point == "fsync":
        monkeypatch.setattr(g.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("simulated fsync failure")))
    elif failure_point == "replace":
        monkeypatch.setattr(g.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("simulated replace failure")))

    _load()(tmp_path, auto=True, skip=False)  # must NOT raise
    assert (tmp_path / ".gitignore").read_bytes() == initial, "original file must be byte-identical"
    assert not (tmp_path / ".gitignore.tmp").exists(), f"tmp left behind on {failure_point}"
    events = [e for e in _events(capsys) if e.get("event", "").startswith("gitignore.")]
    failed = [e for e in events if e["event"] == "gitignore.append.failed"]
    assert len(failed) == 1
    assert failed[0]["level"] == "warning"
    assert failed[0]["exc_class"] == "OSError"


def test_keyboard_interrupt_propagates(
    tmp_path: Path, both_tty: None, confirm_spy: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-17: only OSError is swallowed; KeyboardInterrupt must escape (no over-broad except)."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    import codegenie.output.gitignore as g
    monkeypatch.setattr(g.os, "replace", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        _load()(tmp_path, auto=True, skip=False)


# ---------- Metamorphic / permissions ----------

def test_call_twice_is_metamorphic_noop(
    tmp_path: Path, no_tty: None, confirm_spy: list
) -> None:
    """AC-19: f(f(x)) == f(x). Second call must not rewrite — mtime is the strict pin."""
    (tmp_path / ".gitignore").write_bytes(b"node_modules/\n")
    _load()(tmp_path, auto=True, skip=False)
    content_after_first = (tmp_path / ".gitignore").read_bytes()
    mtime_after_first = (tmp_path / ".gitignore").stat().st_mtime_ns
    _load()(tmp_path, auto=True, skip=False)  # second call
    assert (tmp_path / ".gitignore").read_bytes() == content_after_first
    assert (tmp_path / ".gitignore").stat().st_mtime_ns == mtime_after_first


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits only — Windows is advisory")
def test_created_gitignore_uses_platform_default_mode(
    tmp_path: Path, no_tty: None, confirm_spy: list
) -> None:
    """AC-20: per ADR-0011, the analyzed repo's .gitignore is NOT 0600 — no os.chmod."""
    _load()(tmp_path, auto=True, skip=False)
    mode = (tmp_path / ".gitignore").stat().st_mode & 0o777
    # Accept any platform-default-after-umask; explicitly reject 0o600 (the .codegenie/-style mode).
    assert mode != 0o600, "ADR-0011: analyzed .gitignore must NOT inherit .codegenie/ 0600 mode"
    assert mode in {0o644, 0o664, 0o600 ^ 0o600}  # tolerate test-runner umasks; 0o600 already excluded


def test_logging_constants_exist() -> None:
    """AC-21: logging.py exports the five gitignore.append.* event-name constants."""
    import codegenie.logging as cgl
    assert cgl.GITIGNORE_APPEND_ACCEPTED == "gitignore.append.accepted"
    assert cgl.GITIGNORE_APPEND_DECLINED == "gitignore.append.declined"
    assert cgl.GITIGNORE_APPEND_SKIPPED == "gitignore.append.skipped"
    assert cgl.GITIGNORE_APPEND_IDEMPOTENT == "gitignore.append.idempotent"
    assert cgl.GITIGNORE_APPEND_FAILED == "gitignore.append.failed"
```

Run these — first failure is `ModuleNotFoundError: No module named 'codegenie.output.gitignore'`. Commit the failing tests as the red marker.

### Green — make it pass

Implement `src/codegenie/output/gitignore.py` per the Implementation outline. Straight-line `if/elif` per Step-4 risks note (resist a state machine — `High-level-impl.md §Step 4 risks specific to this step`). Atomic write is local to the module — do NOT import from `output/writer.py` (per implementer note: keep the two atomic-write paths independent).

### Refactor — clean up

- Module docstring referencing edge case #8, ADR-0011 §Consequences, and `CLAUDE.md`'s "offer to add to `.gitignore` on first run" convention.
- Type hints throughout; `mypy --strict src/codegenie/output/gitignore.py` clean.
- Confirm `cli.py` deletes `_gitignore_mutation_stub` and calls `maybe_append_gitignore` directly. Mutually-exclusive `--auto-gitignore`/`--no-gitignore` rejected at the click layer (`click.UsageError`).
- Extend `src/codegenie/logging.py` with the five `GITIGNORE_APPEND_*` constants; update `tests/unit/test_logging.py` to assert their canonical string values.
- Re-run `pytest tests/unit/test_gitignore_mutation.py -q` — all ~24 tests pass (six branches × ~3 assertions each + the metamorphic / failure / permissions / signature tests).
- Coverage on the new module ≥ 95% lines / ≥ 90% branches.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/output/gitignore.py` | New file — implements `maybe_append_gitignore` per edge case #8, `final-design.md §2.15`, ADR-0011 §Consequences. Atomic write is module-local (do NOT import from `output/writer.py`). |
| `src/codegenie/cli.py` | Delete `_gitignore_mutation_stub`; import and call `maybe_append_gitignore`; add `click.UsageError` guard for `--auto-gitignore` + `--no-gitignore` (AC-15). |
| `src/codegenie/logging.py` | Add the five `GITIGNORE_APPEND_*` event-name constants alongside the `probe.*` family (AC-21). |
| `tests/unit/test_logging.py` | One-line addition: assert the five new constants exist with canonical string values (AC-21). |
| `tests/unit/test_gitignore_mutation.py` | New test file — ~24 tests anchoring AC-1..AC-23. Patterns from `tests/unit/test_logging.py` for structlog JSON capture (Rule 11). |
| `docs/phases/00-bullet-tracer-foundations/phase-arch-design.md` | One-line amendment to §Harness engineering — Idempotence: "line-anchored match against `^\\.codegenie/?\\s*$`, not file-substring" (Validation note #6). |
| `docs/phases/00-bullet-tracer-foundations/final-design.md` | One-line amendment to §2.15: event name `gitignore.codegenie.not_present` superseded by `gitignore.append.skipped (reason=non_tty)` (Validation note #7). |

## Out of scope

- **CLI `gather` startup wiring beyond the call site** — handled by story S4-02. This story implements the helper; S4-02 invokes it.
- **End-to-end smoke test that exercises the helper across a real `codegenie gather` invocation** — handled by story S4-04 (one of its sub-tests covers TTY-accept and non-TTY-skip via the full CLI path).
- **Permission discipline on the analyzed repo's `.gitignore`** — per ADR-0011 §Consequences, this file is **not** under `.codegenie/` and keeps the platform default mode. Do not `chmod 0600` it.
- **Atomic gitignore append for concurrent CLI invocations** — Phase 0 has the single-process invariant; Phase 14's webhook fan-out re-evaluates the contention model (and at that point the analyzed repo's `.gitignore` is already set).
- **Internationalized prompt text** — `click.confirm`'s default English string is fine for Phase 0.

## Notes for the implementer

- **Signature is locked.** `(repo_root: Path, *, auto: bool, skip: bool) -> None` matches S4-02 AC-14 byte-for-byte. Do NOT add `is_tty` or `never` parameters; the validator already considered and rejected that direction (it would invalidate S4-02's pinned `inspect.signature` test). TTY detection lives inside the helper and is monkeypatched on the module's `sys.stdin`/`sys.stdout` attributes in tests.
- **Straight-line branches, no state machine** (`High-level-impl.md §Step 4 risks specific to this step`). Branch order is the contract:
  1. `skip` → emit `gitignore.append.skipped` DEBUG `reason=never_flag`; return.
  2. `<repo>/.gitignore` exists AND is a symlink or not a regular file → `unsafe_path` skip.
  3. existing content (or `b""`) matches `_IDEMPOTENT_RE` → `gitignore.append.idempotent` DEBUG; return.
  4. `not auto and not is_tty` → `gitignore.append.skipped` WARNING `reason=non_tty`; return.
  5. `not auto` → `click.confirm`; on `False` → `gitignore.append.declined` INFO; return.
  6. Atomic write; emit `gitignore.append.accepted` INFO with `reason=tty_accept` or `auto_flag`.
- **ADR-0011 — file mode.** The analyzed repo's `.gitignore` is NOT under `.codegenie/`. Do NOT `os.chmod 0600` on it. AC-20's test asserts the mode is not `0o600`. An explicit one-line code comment preventing future drift is worth the line.
- **AC-11 — line-anchored regex, NOT file-substring.** Otherwise `# do not commit .codegenie/ in real builds` falsely registers as "already present." Use `re.compile(rb"^\.codegenie/?\s*$", re.MULTILINE)` in bytes mode (decoding is one fewer failure mode). `phase-arch-design.md §Harness engineering — Idempotence` currently says "substring" — this story IMPROVES the contract and adds the one-line amendment to the arch in the same PR.
- **Atomic write is module-local.** Same shape as `output/writer.py` (S3-03): `<tmp>` → `fsync` → `os.replace`. Do **NOT** import the Writer's helpers (the writer's symlink-refusal and 0600 chmod policy is for `.codegenie/`; the gitignore writer's policy is different per ADR-0011 — see prior note). Two independent atomic writers is correct here.
- **Mid-write failure cleanup (AC-16).** Every step on the write path is wrapped in one try/except `OSError`. On failure, best-effort `tmp.unlink(missing_ok=True)` then emit `gitignore.append.failed` and return. KeyboardInterrupt and any non-OS exception must propagate — do NOT use `except Exception`.
- **Edge case #8 is load-bearing.** A `.gitignore`-append failure must NOT change `codegenie gather`'s exit code. Probe runs determine exit codes; the gitignore mutation is a courtesy. AC-16 + AC-18 pin this — do not regress.
- **Tests follow `test_logging.py`'s structlog-stderr-JSON pattern** (Rule 11 — match the codebase). Do NOT use `caplog.records[i].message`; that's the std-logging API and does not see structlog's stderr stream as configured here.
- **Don't quietly drop the comment line** (`# codewizard-sherpa generated artifacts; safe to delete\n`). It's `final-design.md §2.15`'s explicit contract and an under-rated UX nicety (a contributor seeing the bare `.codegenie/` in `.gitignore` will reasonably ask "what is this?" — the comment answers it).
- **Logging.py constants are part of this story's PR.** If S2-01 declared the `gitignore.append.*` family, reuse those constants; if not, add them now. Don't leave raw strings in the helper body — that defeats the rename-resistance the constants provide.
