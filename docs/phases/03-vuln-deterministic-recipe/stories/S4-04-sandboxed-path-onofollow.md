# Story S4-04 — `SandboxedPath.create` (Result) + `open()` always `O_NOFOLLOW` + TOCTOU defense

**Step:** Step 4 — SubprocessJail Port + Bwrap + sandbox-exec + ALLOWED_BINARIES amendment
**Status:** Ready
**Effort:** S
**Depends on:** S4-01 (`JailedSubprocessSpec.cwd: SandboxedPath` is consumed here; the Port commits to this typename)
**ADRs honored:** 03-ADR-0011 (honest framing — `SandboxedPath` is "in-jail at construction, second-line defense at `open()` via `O_NOFOLLOW`"; NOT "in-jail forever"; consumers handle `OSError(errno=ELOOP)` and emit `FilesystemRaceDetected`)

## Context

`SandboxedPath` is one of three primitives ADR-0011 ships with explicit, downgraded framing. The security-lens design (`design-security.md`) overclaimed it as "in-jail forever" / "makes illegal states unrepresentable"; the critic correctly attacked this (`critique.md §Attacks on the security-first design — sandbox-path overclaim`):

> `Path.resolve(strict=True)` resolves symlinks at constructor time, but a symlink swap between `create()` and `open()` re-introduces the TOCTOU. The path is in-jail *at construction*, not forever.

The architecture's response (`phase-arch-design.md §Component design C10` + ADR-0011 §Decision §SandboxedPath) is **honest framing**: ship the primitive, document what it actually delivers, and add a meaningful second-line defense at the only place it can be added — `open()`-time `O_NOFOLLOW`. A symlink swap between `create()` and `open()` raises `OSError(errno=ELOOP)`, which consumers catch and translate into a typed `FilesystemRaceDetected` workflow-internal event (S6-01 lands the event taxonomy; this story emits the right exception that triggers it).

This story is **small** (S effort) and **focused**: ship `SandboxedPath` with the documented contract, ship the TOCTOU regression test that proves the second-line defense actually fires, and stop. The cost-to-build is dwarfed by the audit-trail value — every consumer (S5-02's `NpmLockfileRecipeEngine` writing the new `package.json`; S4-02 / S4-03 jail-cwd binds; S6-04's `LocalGitOps`) gets the same path-type and the same fail-loud behavior.

Critically, the file path per ADR-0011 §Consequences is `src/codegenie/plugins/sandbox_path.py` — under `plugins/`, NOT `transforms/`. The High-level-impl bullet says `src/codegenie/transforms/sandbox_path.py`; per Rule 7 (Surface conflicts, don't average), the ADR is the more recent / load-bearing decision and wins. See Notes for implementer.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C10` — `SandboxedPath` bullet: `create(jail, relative) -> Result[SandboxedPath, PathEscape]`; `.open(mode)` always `O_NOFOLLOW`; "in-jail at construction, second-line defense at `open()`-time `O_NOFOLLOW`"; consumers handle `OSError(errno=ELOOP)` and emit `FilesystemRaceDetected`.
  - `../phase-arch-design.md §Edge case E12` — Symlink TOCTOU detection at `open()`-time; `RemediationOutcome.Failed(filesystem_race)`; exit 4.
  - `../phase-arch-design.md §Control flow` — "Symlink TOCTOU detected at `open()` → `OSError(ELOOP)` caught → `FilesystemRaceDetected` event → `RemediationOutcome.Failed(filesystem_race)` → exit 4."
  - `../phase-arch-design.md §Tradeoffs (consolidated)` — row "`SandboxedPath` is 'in-jail at construction,' not 'in-jail forever'" — honest framing accepted; every consumer must handle `ELOOP`.
  - `../phase-arch-design.md §Testing strategy` — bullet `tests/unit/plugins/test_sandbox_path.py` — TOCTOU symlink swap raises `ELOOP` at `open()`; `is_relative_to(jail)` enforcement.
- **Phase ADRs:**
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — §Decision §SandboxedPath block pins the `Result`-returning constructor and the `O_NOFOLLOW`-always `open()`; §Consequences pins the file location `src/codegenie/plugins/sandbox_path.py` and the test `tests/unit/plugins/test_sandbox_path.py` exercising "the TOCTOU swap via deliberate fixture."
  - `../ADRs/0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md` — consumer of `SandboxedPath` at `JailedSubprocessSpec.cwd`; the Port commits to the typename.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "SandboxedPath framing"` (score 15/15) — honest-framing synthesis behind ADR-0011.
  - `../High-level-impl.md §Step 4 features delivered` — lists `src/codegenie/transforms/sandbox_path.py`. **This conflicts with ADR-0011's `src/codegenie/plugins/sandbox_path.py`.** ADR wins (Rule 7). See Notes.
- **Existing code:**
  - `src/codegenie/types/result.py` (or wherever the `Result[T, E]` type lives — verify via `grep -r "class Result" src/codegenie/` before starting). Phase 1 / Phase 2 already ship smart-constructor `Result`-returning functions; mirror the precedent.
  - `src/codegenie/types/identifiers.py` — newtype precedent (S1-01).
  - `src/codegenie/transforms/sandbox_jail.py` (S4-01) — the consumer. `JailedSubprocessSpec.cwd: SandboxedPath` is the load-bearing type binding.
- **External:**
  - Python stdlib `os.open(path, flags, ...)` with `os.O_NOFOLLOW` flag — raises `OSError` with `errno=errno.ELOOP` when the final component is a symlink. This is the kernel-level second-line defense.

## Goal

Land `src/codegenie/plugins/sandbox_path.py` with:
1. `class SandboxedPath` — frozen, immutable wrapper over a resolved absolute `Path`.
2. `SandboxedPath.create(jail: Path, relative: str | Path) -> Result[SandboxedPath, PathEscape]` — smart-constructor that resolves `(jail / relative).resolve(strict=True)`, checks `is_relative_to(jail.resolve(strict=True))`, returns `Err(PathEscape)` on any failure (path-escape, missing file, broken symlink, etc.).
3. `SandboxedPath.absolute: Path` — the resolved absolute path (read-only property).
4. `SandboxedPath.open(mode: str) -> IO[Any]` — **always** opens with `O_NOFOLLOW`. If the final path component is a symlink (created via a TOCTOU swap after `create` returned), `OSError(errno=ELOOP)` is raised. The Adapter does NOT catch it; consumers do.
5. `PathEscape(BaseModel)` Pydantic error variant: `kind: Literal["path_escape"]`, `attempted_path: str`, `jail: str`, `reason: Literal["not_under_jail", "not_resolvable", "missing"]`.
6. A `tests/unit/plugins/test_sandbox_path.py` covering: happy path; path-escape (relative `..` traversal); missing file; broken symlink; **TOCTOU swap** (the load-bearing test — symlink is created between `create()` and `open()` and `open()` raises `OSError(errno=ELOOP)`).

`mypy --strict` clean.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/plugins/sandbox_path.py` exists and exports exactly: `SandboxedPath`, `PathEscape`. A meta-test asserts the module's public surface is this set (no leakage of internal helpers).
- [ ] **AC-2.** `SandboxedPath.create(jail, relative)` returns `Result[SandboxedPath, PathEscape]`. Happy path: `jail = tmp_path` (a real dir), `relative = "file.txt"` (a real file inside `jail`). Returns `Ok(SandboxedPath(...))`. The unwrapped `SandboxedPath.absolute` equals `(jail / "file.txt").resolve()`.
- [ ] **AC-3.** Path-escape via `..` traversal returns `Err(PathEscape(reason="not_under_jail"))`. Test: `jail = tmp_path / "jail"` (created); `relative = "../outside.txt"` (escapes). The test creates `outside.txt` so `resolve(strict=True)` succeeds, then asserts the `is_relative_to(jail)` check fails with `PathEscape(reason="not_under_jail", attempted_path=...)`.
- [ ] **AC-4.** Missing file (when `strict=True`) returns `Err(PathEscape(reason="missing"))`. Test: `jail = tmp_path`; `relative = "does-not-exist.txt"`. `Path.resolve(strict=True)` raises `FileNotFoundError`; smart constructor catches and translates to `Err`.
- [ ] **AC-5.** Broken symlink (target doesn't exist) returns `Err(PathEscape(reason="not_resolvable"))`. Test: create a symlink inside `jail` pointing to `/does/not/exist`; `create()` returns `Err`.
- [ ] **AC-6.** `SandboxedPath` is frozen / immutable. Either implemented as `@dataclass(frozen=True)` over the resolved `Path`, or `pydantic.BaseModel(frozen=True)`. A test asserts mutating any attribute raises `FrozenInstanceError` (dataclass) or `ValidationError` (Pydantic).
- [ ] **AC-7.** `SandboxedPath.open(mode)` **always** uses `O_NOFOLLOW`. A test monkeypatches `os.open` (or `builtins.open` if the implementation routes through it), captures the flags argument, and asserts `os.O_NOFOLLOW` bit is set regardless of the `mode` string. Parametrize over `mode in {"r", "rb", "w", "wb", "r+", "a"}`.
- [ ] **AC-8.** **The load-bearing TOCTOU test.** `test_symlink_swap_between_create_and_open_raises_eloop`:
  - Create `jail/realfile.txt` (a real file).
  - Call `SandboxedPath.create(jail, "realfile.txt").unwrap()` — succeeds.
  - Unlink `jail/realfile.txt` and re-create it as a symlink to `/etc/passwd` (or any path outside jail).
  - Call `sandboxed_path.open("rb")` and assert it raises `OSError` with `errno == errno.ELOOP`. (Per `man 2 open` on Linux/macOS: `O_NOFOLLOW` causes `ELOOP` when the final component is a symlink.)
  - The test must NOT catch the exception with a generic `Exception` clause — the typed `OSError(errno=ELOOP)` is the structural contract.
- [ ] **AC-9.** Mirror of AC-8 with a **directory symlink swap** — replace the final component with a symlink to another directory (not just a regular file). Same `OSError(errno=ELOOP)` expected. (`O_NOFOLLOW` covers both file and directory final-component symlinks.)
- [ ] **AC-10.** Negative test confirming `O_NOFOLLOW` does NOT block intermediate-component symlinks (per `man 2 open`: `O_NOFOLLOW` only affects the final component). Test creates `jail/a/realdir/` containing `b.txt`, then replaces `jail/a` with a symlink to `jail/a/realdir/..` (or another path that still resolves under `jail`). `SandboxedPath.create(jail, "a/realdir/b.txt")` will resolve with `strict=True` to the real path before any check; `is_relative_to(jail)` succeeds; `open()` does NOT raise `ELOOP`. The test documents this as the *known limitation* — only the final component is protected. This is part of the honest framing: ADR-0011 commits to "second-line defense at `open()`-time `O_NOFOLLOW`", not "every-component symlink defense" (which would require something like `openat2(... RESOLVE_NO_SYMLINKS ...)` and is Linux-only).
- [ ] **AC-11.** Type binding: `JailedSubprocessSpec.cwd` (from S4-01) accepts a `SandboxedPath` instance without coercion. A round-trip test imports both and constructs a real `JailedSubprocessSpec(cwd=<real SandboxedPath>)` — no `type: ignore`, no `# noqa`, mypy-strict clean.
- [ ] **AC-12.** Path-escape symlink-target swap: `jail/file.txt` is initially a symlink pointing OUTSIDE the jail (e.g., to `/tmp/elsewhere.txt`). `SandboxedPath.create(jail, "file.txt")` resolves the symlink with `strict=True`, gets a path outside `jail`, returns `Err(PathEscape(reason="not_under_jail"))`. This proves the constructor's `is_relative_to(jail)` check is operative AFTER symlink resolution, not before. (Per ADR-0011 §Decision §SandboxedPath: "resolves with `strict=True`, checks `is_relative_to(jail)`.")
- [ ] **AC-13.** `PathEscape` is a frozen Pydantic model with `model_config = ConfigDict(frozen=True, extra="forbid")`. A test asserts construction with unknown field raises `ValidationError` and instance attributes cannot be mutated.
- [ ] **AC-14.** `mypy --strict src/codegenie/plugins/sandbox_path.py tests/unit/plugins/test_sandbox_path.py` clean. `ruff check` + `ruff format --check` clean.
- [ ] **AC-15.** Module docstring cites ADR-0011's honest framing verbatim: the docstring contains the phrases `"audit + lint"` (or `"audit + lint enforcement"`) and `"in-jail at construction"` and references `03-ADR-0011`. A meta-test asserts these substrings. This is the framing discipline ADR-0011 §Consequences requires ("The docs framing this ADR establishes is reused verbatim in operator runbooks — 'audit + lint' not 'unforgeable'; 'integrity check' not 'signature.'").
- [ ] **AC-16.** Lint-level fence (deferred to S4-05's broader fence story or landed here, implementer's choice): a fence test or grep asserts that anywhere in `src/codegenie/{plugins,transforms}/` that imports `SandboxedPath` and calls `.open(...)`, the call is either wrapped in a `try/except OSError` OR is routed through a helper that catches `ELOOP`. **If this AC is hard to land in this story (no consumers exist yet at Step 4 — they land at S5-02 and S6-04), it can be deferred** to a follow-up fence-story with a tracking note in the attempt log. Mark BLOCKED-PARTIAL in that case rather than weakening; do NOT land the helper without a real consumer.

## Implementation outline

1. Verify the `Result[T, E]` shape used elsewhere in the codebase. `grep -r "class Result\|from .result import\|Result\[" src/codegenie/` — likely `src/codegenie/types/result.py` or similar from Phase 1 newtype/smart-constructor work. Use that exact shape (Rule 11 — match the codebase's conventions).
2. Create `src/codegenie/plugins/sandbox_path.py`. Imports: `from __future__ import annotations`, `errno`, `os`, `pathlib.Path`, `typing.IO, Any, Literal`, `pydantic.BaseModel, ConfigDict`, `codegenie.types.result.{Result, Ok, Err}` (or whatever names exist).
3. Define `PathEscape(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")` and fields `kind: Literal["path_escape"] = "path_escape"`, `attempted_path: str`, `jail: str`, `reason: Literal["not_under_jail", "not_resolvable", "missing"]`.
4. Define `class SandboxedPath`. If the codebase prefers Pydantic frozen models for value types, use `BaseModel(frozen=True, extra="forbid", arbitrary_types_allowed=True)` with `_absolute: Path` (private). If `@dataclass(frozen=True)` is the convention, use that. Match the codebase precedent (Rule 11).
5. Class methods + properties:
   - `@classmethod def create(cls, jail: Path, relative: str | Path) -> Result["SandboxedPath", PathEscape]`:
     ```python
     try:
         jail_abs = jail.resolve(strict=True)
     except FileNotFoundError:
         return Err(PathEscape(attempted_path=str(jail / relative), jail=str(jail), reason="missing"))
     candidate = (jail_abs / relative)
     try:
         resolved = candidate.resolve(strict=True)
     except FileNotFoundError:
         return Err(PathEscape(attempted_path=str(candidate), jail=str(jail_abs), reason="missing"))
     except OSError:  # broken symlink chain
         return Err(PathEscape(attempted_path=str(candidate), jail=str(jail_abs), reason="not_resolvable"))
     if not resolved.is_relative_to(jail_abs):
         return Err(PathEscape(attempted_path=str(resolved), jail=str(jail_abs), reason="not_under_jail"))
     return Ok(cls(_absolute=resolved))
     ```
   - `@property def absolute(self) -> Path: return self._absolute`
   - `def open(self, mode: str) -> IO[Any]`:
     ```python
     flags = _flags_for_mode(mode) | os.O_NOFOLLOW
     fd = os.open(self._absolute, flags)
     return os.fdopen(fd, mode)
     ```
   where `_flags_for_mode` translates the Python `mode` string to the right `os.O_*` flags (`"r"` → `os.O_RDONLY`; `"w"` → `os.O_WRONLY | os.O_CREAT | os.O_TRUNC`; `"a"` → `os.O_WRONLY | os.O_CREAT | os.O_APPEND`; `"b"` is a no-op at the os.open layer).
6. Module docstring (AC-15): one paragraph framing per ADR-0011, citing it by ADR number.
7. Write the tests in `tests/unit/plugins/test_sandbox_path.py` per AC-1..AC-15. The TOCTOU test (AC-8) requires actual filesystem manipulation between `create()` and `open()` — use real `tmp_path` and `os.symlink` / `os.unlink`.
8. Run `mypy --strict`, `ruff`, `pytest tests/unit/plugins/test_sandbox_path.py -v`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

`tests/unit/plugins/test_sandbox_path.py`:

```python
from __future__ import annotations

import errno
import os
from pathlib import Path
from typing import IO, Any

import pytest

# RED — these imports fail until S4-04 lands
from codegenie.plugins.sandbox_path import PathEscape, SandboxedPath


# AC-2 happy path
def test_create_happy_path(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("hi")
    result = SandboxedPath.create(tmp_path, "file.txt")
    assert result.is_ok()
    sp = result.unwrap()
    assert sp.absolute == (tmp_path / "file.txt").resolve()


# AC-3 path-escape via ..
def test_create_path_escape_via_dotdot(tmp_path: Path) -> None:
    jail = tmp_path / "jail"
    jail.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("not yours")
    result = SandboxedPath.create(jail, "../outside.txt")
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, PathEscape)
    assert err.reason == "not_under_jail"


# AC-4 missing file
def test_create_missing_file(tmp_path: Path) -> None:
    result = SandboxedPath.create(tmp_path, "does-not-exist.txt")
    assert result.is_err()
    assert result.unwrap_err().reason == "missing"


# AC-5 broken symlink
def test_create_broken_symlink(tmp_path: Path) -> None:
    broken = tmp_path / "broken-link"
    broken.symlink_to("/does/not/exist/anywhere")
    result = SandboxedPath.create(tmp_path, "broken-link")
    assert result.is_err()
    assert result.unwrap_err().reason in {"missing", "not_resolvable"}


# AC-6 frozen
def test_sandboxed_path_is_frozen(tmp_path: Path) -> None:
    (tmp_path / "x.txt").write_text("")
    sp = SandboxedPath.create(tmp_path, "x.txt").unwrap()
    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError or ValidationError
        sp._absolute = Path("/etc")  # type: ignore[misc]


# AC-7 O_NOFOLLOW always set
@pytest.mark.parametrize("mode", ["r", "rb", "w", "wb", "r+", "a"])
def test_open_always_uses_o_nofollow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str,
) -> None:
    (tmp_path / "f.txt").write_text("")
    sp = SandboxedPath.create(tmp_path, "f.txt").unwrap()
    captured_flags: list[int] = []
    real_open = os.open
    def spy_open(path, flags, *a, **kw):  # type: ignore[no-untyped-def]
        captured_flags.append(flags)
        return real_open(path, flags, *a, **kw)
    monkeypatch.setattr(os, "open", spy_open)
    try:
        f: IO[Any] = sp.open(mode)
        f.close()
    except OSError:
        pass  # write modes may fail if the impl doesn't pre-create; flags still captured
    assert captured_flags, "os.open was never called"
    for flags in captured_flags:
        assert flags & os.O_NOFOLLOW, f"O_NOFOLLOW missing for mode={mode!r}; flags={flags}"


# AC-8 — THE LOAD-BEARING TOCTOU TEST
def test_symlink_swap_between_create_and_open_raises_eloop(tmp_path: Path) -> None:
    """ADR-0011 §Decision §SandboxedPath: the TOCTOU swap is detected at
    open()-time via O_NOFOLLOW. This test simulates an attacker swapping
    the final-component file for a symlink between create() and open()."""
    target = tmp_path / "realfile.txt"
    target.write_text("real")
    sp = SandboxedPath.create(tmp_path, "realfile.txt").unwrap()

    # Swap: unlink the real file, create a symlink in its place.
    target.unlink()
    elsewhere = tmp_path / "elsewhere.txt"
    elsewhere.write_text("attacker target")
    os.symlink(elsewhere, target)

    with pytest.raises(OSError) as excinfo:
        sp.open("rb")
    assert excinfo.value.errno == errno.ELOOP, (
        f"expected ELOOP from O_NOFOLLOW swap; got errno={excinfo.value.errno}"
    )


# AC-9 — directory-symlink swap, same ELOOP
def test_directory_symlink_swap_raises_eloop(tmp_path: Path) -> None:
    target = tmp_path / "dir_or_file"
    target.write_text("real")
    sp = SandboxedPath.create(tmp_path, "dir_or_file").unwrap()

    target.unlink()
    other_dir = tmp_path / "other_dir"
    other_dir.mkdir()
    os.symlink(other_dir, target)

    with pytest.raises(OSError) as excinfo:
        sp.open("rb")
    assert excinfo.value.errno == errno.ELOOP


# AC-10 — known limitation: only the final component is protected
def test_intermediate_component_symlink_is_not_caught(tmp_path: Path) -> None:
    """O_NOFOLLOW only affects the final component (man 2 open). Intermediate
    symlinks resolve normally. ADR-0011 documents this as the known limitation
    of the second-line defense."""
    realdir = tmp_path / "realdir"
    realdir.mkdir()
    target_file = realdir / "b.txt"
    target_file.write_text("ok")

    # Replace `realdir` with a symlink chain that still resolves under jail
    aliased = tmp_path / "aliased"
    aliased.symlink_to(realdir)
    sp = SandboxedPath.create(tmp_path, "aliased/b.txt").unwrap()
    f = sp.open("rb")
    try:
        assert f.read() == b"ok"  # opens fine — intermediate symlink is permitted
    finally:
        f.close()


# AC-11 — type binding to S4-01
def test_sandboxed_path_satisfies_subprocess_jail_cwd() -> None:
    from codegenie.transforms.sandbox_jail import (
        DenyAll, JailedSubprocessSpec, NpmEnv,
    )
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "f.txt").write_text("")
        sp = SandboxedPath.create(Path(td), "f.txt").unwrap()
        spec = JailedSubprocessSpec(
            cmd=("/bin/echo", "hi"),
            cwd=sp,
            env=NpmEnv(), network=DenyAll(),
            time_budget_s=1.0, memory_mib=1, pids_max=1,
        )
        assert spec.cwd is sp


# AC-12 — symlink-target outside jail rejected at create
def test_symlink_target_outside_jail_rejected_at_create(tmp_path: Path) -> None:
    jail = tmp_path / "jail"
    jail.mkdir()
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("target")
    link = jail / "file.txt"
    link.symlink_to(outside)
    result = SandboxedPath.create(jail, "file.txt")
    assert result.is_err()
    assert result.unwrap_err().reason == "not_under_jail"


# AC-13 — PathEscape Pydantic discipline
def test_path_escape_is_frozen_and_forbid() -> None:
    from pydantic import ValidationError
    err = PathEscape(attempted_path="/x", jail="/y", reason="not_under_jail")
    with pytest.raises(ValidationError):
        PathEscape(attempted_path="/x", jail="/y", reason="not_under_jail", extra="bad")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        err.reason = "missing"  # type: ignore[misc]


# AC-15 — docstring honest-framing pin
def test_module_docstring_uses_honest_framing() -> None:
    import codegenie.plugins.sandbox_path as mod
    doc = mod.__doc__ or ""
    assert "in-jail at construction" in doc
    assert "audit + lint" in doc or "audit and lint" in doc.lower()
    assert "03-ADR-0011" in doc or "ADR-0011" in doc
```

Run — all RED (module missing). Commit.

### Green — make it pass

Implement `src/codegenie/plugins/sandbox_path.py` per Implementation outline. Run AC-2..AC-15 — green. The TOCTOU test (AC-8) is the most likely to surface implementation bugs:
- If `open()` uses Python's `builtins.open` directly, you don't get a chance to add `O_NOFOLLOW` — must route through `os.open(..., flags | os.O_NOFOLLOW)` + `os.fdopen(fd, mode)`.
- Edge: on macOS, `open()` of an already-existing file with `O_RDONLY | O_NOFOLLOW` and a final-component symlink gives `ELOOP`; same on Linux. Test runs identically on both.

### Refactor — clean up

- Pull `_flags_for_mode(mode: str) -> int` into a private helper if `open()` exceeds ~20 lines.
- Consider whether `Result.unwrap()` / `is_ok()` / `is_err()` exist with those names in the codebase — if `Result` uses `.value` / `.error` / `match`-only access, mirror that (Rule 11).
- Docstring polish; ensure ADR-0011 citation is in the right place (module-level, not function-level — the AC-15 test reads `mod.__doc__`).
- `ruff format`, `mypy --strict`, full test suite green.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/sandbox_path.py` | New: `SandboxedPath` class with `create() -> Result`, frozen value type, `open()` always `O_NOFOLLOW`; `PathEscape` Pydantic error variant (AC-1..AC-15). |
| `tests/unit/plugins/test_sandbox_path.py` | New: AC-2..AC-15 including the load-bearing TOCTOU test (AC-8). |

## Out of scope

- **`FilesystemRaceDetected` event emission** — S6-01 lands the event taxonomy and the emit infrastructure. This story raises `OSError(errno=ELOOP)` from `open()`; the consumer (S5-02 / S6-04) catches it and emits the event.
- **Helper to wrap `.open()` in a try/except that emits the event** — per `High-level-impl §Step 4 Risk 5`: "a single `with_sandbox_open(...)` helper that catches `ELOOP` and emits the event; lint rule (or grep test) asserting every `.open(...)` on a `SandboxedPath` is routed through the helper." This helper lands when the first consumer arrives (S5-02) — adding it here without a real consumer is premature (Rule 2 — Simplicity First).
- **`openat2(... RESOLVE_NO_SYMLINKS ...)` Linux-only every-component defense** — explicitly out per AC-10. ADR-0011 commits to "second-line defense at `open()`-time `O_NOFOLLOW`", not full path-walking defense. Future hardening (if Phase 11 demands it) is a separate ADR.
- **`SubprocessJail` Protocol + adapters** — S4-01 / S4-02 / S4-03.
- **`Capability` tokens + ruff fence** — S4-05.
- **AC-16 consumer-side fence** — deferred to S5-02 or a follow-up fence story; this story has no consumers yet inside Phase 3 source.

## Notes for the implementer

- **File-location conflict, ADR wins.** `High-level-impl.md §Step 4 features delivered` says `src/codegenie/transforms/sandbox_path.py`. `phase-arch-design.md §Component design C10` and `ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md §Consequences` both say `src/codegenie/plugins/sandbox_path.py`. Per Rule 7 (Surface conflicts, don't average), the ADR is the more recent / more load-bearing decision. Use **`src/codegenie/plugins/sandbox_path.py`**. Flag the High-level-impl discrepancy in the attempt log so a follow-up doc-fix story can reconcile (do not fix it in this story — surgical).
- **`Result` shape — match the codebase.** Phase 1 / Phase 2 ship `Result`-returning smart constructors (search `src/codegenie/` for `Result[`); the API surface (`Ok` / `Err` / `is_ok` / `unwrap` vs `match`-only) is the convention. Don't introduce a second `Result` library or differing API surface. If the codebase has no `Result` yet (S1-01 was supposed to land it; verify), the story may need to coordinate landing order — surface in the attempt log.
- **`O_NOFOLLOW` is the heart of this story.** The TOCTOU regression (AC-8) is the test that proves the architecture's claim. A naive `open(path, mode)` implementation passes every other AC and silently fails AC-8 because Python's `open` doesn't pass `O_NOFOLLOW` by default. The fix is `os.open(path, flags | O_NOFOLLOW)` followed by `os.fdopen(fd, mode)`. This is not optional polish — it is the contract.
- **Honest framing in docstring is structural.** ADR-0011 §Consequences requires: "The docs framing this ADR establishes is reused verbatim in operator runbooks — 'audit + lint' not 'unforgeable'; 'integrity check' not 'signature.'" AC-15 pins this at the module docstring. The lint-rule fence in S4-05 will further enforce.
- **AC-10 documents a real limitation, not a bug.** `O_NOFOLLOW` only affects the final path component (`man 2 open`). An attacker who can swap an intermediate directory in the path can still escape — but they need write access to that intermediate dir, which is already a higher-level compromise than this primitive defends against. Document the limitation honestly in both the docstring AND AC-10 (the test serves as living documentation).
- **TOCTOU window in practice.** Between `SandboxedPath.create(jail, "file.txt")` and `sp.open("rb")`, a TOCTOU window exists. The window is small (microseconds in normal flow) but real. `O_NOFOLLOW` makes the attacker's window matter only if they can land the swap before `open()` returns; if they do, `ELOOP` fires and the workflow aborts. This is "second-line defense" not "no defense" — exactly the honest framing ADR-0011 commits to.
- **`is_relative_to` is Python 3.9+** — the codebase is on 3.11+ per CI matrix. Use it directly.
- **Strict-resolve is the first line of defense.** `Path.resolve(strict=True)` raises `FileNotFoundError` for missing files and follows symlinks. After resolution, `is_relative_to(jail.resolve(strict=True))` is the in-jail check. Both jail and candidate are resolved with `strict=True` so the comparison is between fully-canonicalized paths.
- **Don't catch the ELOOP in `open()`.** ADR-0011 §Decision §SandboxedPath: "Consumers handle `OSError(errno=ELOOP)`." The Adapter (`SandboxedPath.open`) raises; consumers (S5-02's `NpmLockfileRecipeEngine`, S6-04's `LocalGitOps`) catch and emit `FilesystemRaceDetected`. If this story catches the exception, it silently defeats the architecture's loud-fail discipline (Rule 12 — Fail loud).
- **AC-16 deferral acceptance.** S4-05 may extend the static-fence story with a consumer-side `with_sandbox_open` helper + lint rule. Or a future S5-02 story may land it inline. Either way, this story does not introduce a helper without a real consumer (Rule 2).
- **Effort sizing reality check.** ADR-0011 calls this primitive small; the four ACs that take real work are AC-7 (O_NOFOLLOW flag plumbing), AC-8 (TOCTOU regression — small but careful), AC-12 (symlink-target-outside-jail at construction), and AC-15 (docstring discipline). Everything else is bookkeeping. S sizing is honest; if implementation discovers a `Result` shape mismatch or `os.open` mode-translation rabbit hole, surface in attempt log and consider promoting to M.
