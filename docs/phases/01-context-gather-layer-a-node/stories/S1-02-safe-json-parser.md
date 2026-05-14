# Story S1-02 — `safe_json` parser with `O_NOFOLLOW` + size + depth caps

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Done — 2026-05-13 (phase-story-executor attempt 1, GREEN). All 19 ACs verified; 33/33 new unit tests green; full suite 648/648; coverage 93.03%; mypy `--strict` + ruff + pre-commit + import-linter all clean. Attempt log: [`_attempts/S1-02.md`](_attempts/S1-02.md). Implementation: [`src/codegenie/parsers/__init__.py`](../../../../src/codegenie/parsers/__init__.py), [`src/codegenie/parsers/safe_json.py`](../../../../src/codegenie/parsers/safe_json.py). `SymlinkRefusedError` docstring extended at [`src/codegenie/errors.py`](../../../../src/codegenie/errors.py). Tests: [`tests/unit/parsers/test_safe_json.py`](../../../../tests/unit/parsers/test_safe_json.py).
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0008, ADR-0009, ADR-0007

## Validation notes (phase-story-validator, 2026-05-13)

This story was hardened by the validator from its initial draft. Key changes:

- **Markers-only construction restored (block-tier consistency fix).** The original draft prescribed `SizeCapExceeded(path=path, cap=max_bytes)`, `DepthCapExceeded(path=path, cap=max_depth)`, `MalformedJSONError(path=path, detail=...)`, `SymlinkRefusedError(path=path)` — all kwarg construction. That directly violates the Phase 0 markers-only invariant pinned by `tests/unit/test_errors.py::test_subclasses_are_markers_only` (`cls.__init__ is e.CodegenieError.__init__` + class-dict allowlist) and re-affirmed by S1-01's hardening. **The marker subclasses accept exactly one positional `args[0]` message and expose no instance state.** Raise sites must construct via a formatted message string (e.g., `SizeCapExceeded(f"{path}: size={size} cap={max_bytes}")`). All TDD assertions of `exc.value.cap == X` are likewise impossible — markers carry no `.cap`. Tests now assert `args[0]`/`str(exc)` substrings instead (CV5, TQ1).
- **Depth walker hardened to mixed dict/list nesting.** Original AC and tests only covered nested-dict shape (`{"x": {"x": …}}`). A walker that descends only into `dict` would pass billion-laughs-via-list. Added a fixture and AC that depth-cap fires on **alternating dict/list** nesting and on **lists of lists** (CV1, TQ4).
- **Depth boundary pinned.** Added an AC and parametrized test: exactly `depth == max_depth` passes, `depth == max_depth + 1` raises. Original draft used 70 vs cap 64 only — no boundary assertion (CV2).
- **Depth-cap event emission added.** Original draft only tested `probe.parser.cap_exceeded` emission on the **size** path. Added an AC and test for the **depth** path with `cap_kind == "depth"` (CV3, TQ6).
- **Structlog event fields tested directly, not via stderr substring.** Original test used `capsys.readouterr().err` and asserted substrings `"probe.parser.cap_exceeded"` and `"safe_json"` — fragile (`"safe_json"` could match `parser` or `parser_kind`), couldn't distinguish missing `cap_kind`, and depended on JSON renderer init. Tests now use `structlog.testing.capture_logs()` and assert structured fields (`event`, `cap_kind`, `path`, `parser`, `parser_kind`) directly (CV4, TQ7).
- **Non-ELOOP OSError passthrough pinned.** Original outline said "catch `OSError` and translate `ELOOP`/`ENOTDIR`/`EINVAL`". This is too broad — `EISDIR` (path is a directory), `EACCES` (permission denied), and `ENOENT` (passes through to `FileNotFoundError`) must **not** be smuggled into `SymlinkRefusedError`. Only `errno == ELOOP` translates; all others propagate as the original `OSError` subtype (CV8, TQ5). `ENOTDIR` (a path component is not a directory) and `EINVAL` (some kernels for symlink loops) are *not* mapped to `SymlinkRefusedError` in Phase 1 — `ELOOP` only — to keep the contract observable.
- **Symlink test sharpened against silent-dereference.** Original test pointed a symlink at `tmp_path / "outside"` containing `"{}"`. If `O_NOFOLLOW` were dropped, the test would silently dereference and return `{}` without `SymlinkRefusedError`. Test now points at a sentinel file whose successful parse would be visible (`{"sentinel": "leaked"}`), so a missing-`O_NOFOLLOW` mutation surfaces (TQ2).
- **`os.read` is bounded by the cap, not by `fstat`.** Original outline said `os.read(fd, size)` after the cap check. If a mutation reorders (size-check after read) and the file is large, `os.read` would allocate. Added an AC and test that calls `safe_json.load` against a 50 MB sparse file with a 1 KB cap and asserts: (a) `SizeCapExceeded` raised, (b) `tracemalloc` peak allocation during the call stays below a generous bound (e.g., 256 KB) — i.e., the bytes were never read (CV6 implication, TQ3).
- **FD close on every path.** Added an AC and test that monkey-patches `os.close` to count invocations; every load (success, size cap, malformed, depth cap, symlink) closes the fd exactly once. Symlink-refusal path closes nothing (fd never opened). FD-leak mutation surfaces.
- **Short read → `MalformedJSONError`.** Implementer note 186 prescribed "if `os.read` returns fewer bytes than `fstat` size, raise `MalformedJSONError(detail='short read')`". Promoted from implementer-note to AC with a `monkeypatch.setattr(os, "read", ...)` test that forces a short read.
- **Empty file (size 0) → `MalformedJSONError`.** `json.loads(b"")` raises `JSONDecodeError`; the typed translation must apply. Added AC + test (CV11).
- **Top-level not a dict → `MalformedJSONError`.** The function signature is `dict[str, JSONValue]`; `json.loads("[1,2,3]")` would return a list and violate the type. Added AC: top-level non-dict raises `MalformedJSONError` (message says "expected JSON object at top level"). Phase 1's consumers (`package.json`, `tsconfig.json`, `*-lock.{json,yaml}`) are all top-level objects (CV10).
- **`SymlinkRefusedError` docstring extension (S1-01 follow-up).** S1-01's validation report flagged that S1-02/S1-03/S1-04 must extend the Phase-0 `SymlinkRefusedError` docstring once the raise site broadens. The Phase 0 docstring still passes `test_every_subclass_has_raise_site_docstring` (the slug `"writer"` is named), but the *raise inventory* in the docstring is now incomplete. Added an AC: the `SymlinkRefusedError` docstring is extended to also name `parsers/safe_json` (and slug `parsers`); the `MalformedJSONError` and other Phase-1-only markers already name their slug from S1-01.
- **Module docstring requirement promoted.** Implementer note prescribed a module docstring referencing arch §"Component design" #8 and ADR-0008. Promoted to AC (CV9).
- **Type-safe return.** Added AC: the function returns `Mapping[str, JSONValue]` (concretely `dict[str, JSONValue]`); `JSONValue` is defined as `bool | int | float | str | None | list["JSONValue"] | dict[str, "JSONValue"]` (mirrors the arch §Data model recursive type). A mypy-strict assertion in the touched tests covers this.
- **AC-9 process-evidence rephrased.** "TDD red test exists, committed, green" is process discipline, not a verifiable behavioral AC. Replaced with a clear "red→green→refactor commit sequence is documented in the PR description" line under TDD plan, not as an AC.

Full report: `_validation/S1-02-safe-json-parser.md`.

## Context

`safe_json` is the chokepoint every Phase 1 probe (and every future probe) routes JSON reads through: `package.json`, `package-lock.json`, `tsconfig.json` (via `jsonc`); `coverage/lcov.info` is the only JSON-adjacent file that doesn't go through here. Its three structural defenses — `O_NOFOLLOW` open, pre-parse size cap on the fd, post-parse depth walker — close ~95% of the adversarial-bytes threat surface without per-probe sandboxes (ADR-0008). The stdlib `json` C extension exposes no native depth limit, so the post-parse walker is load-bearing. The Phase-0 markers-only invariant (`tests/unit/test_errors.py::test_subclasses_are_markers_only`) means the typed exceptions S1-01 introduced carry **no instance state**: cap, path, and parse-failure detail live in the positional `args[0]` formatted message, recoverable at the catch site by the calling probe.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #8` — full interface, `O_NOFOLLOW`, post-parse depth walker rationale; the five-way exception map (`SizeCapExceeded | DepthCapExceeded | MalformedJSONError | SymlinkRefusedError` plus passthrough `FileNotFoundError`).
  - `../phase-arch-design.md §"Harness engineering" → "Logging strategy"` — `probe.parser.cap_exceeded` event with `cap_kind ∈ {"size","depth"}`, `path`, `parser` fields; `parser_kind` tracing field.
  - `../phase-arch-design.md §"Edge cases"` rows 2, 3 — 600 MB string `package.json`, symlink to `/etc/passwd`.
  - `../phase-arch-design.md §"Data model"` — `JSONValue` recursive alias.
- **Phase ADRs:**
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — ADR-0008 — in-process caps replace the sandbox; this module is the load-bearing surface.
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — ADR-0009 — must use stdlib `json.loads`; no `orjson`/`pyjson5`/`ruamel.yaml`.
  - `../ADRs/0007-warnings-id-pattern.md` — ADR-0007 — caller maps to `WarningId` like `package_json.size_cap_exceeded`. **`WarningId` is constructed at the catch site, not embedded on the exception.**
- **Source design:**
  - `../final-design.md §"Components" #8` — the design statement.
- **Existing code (already on `master` after S1-01):**
  - `src/codegenie/errors.py` — `SizeCapExceeded`, `DepthCapExceeded`, `MalformedJSONError`, `SymlinkRefusedError` are **markers only** (no `__init__`, no class attributes; see module docstring lines 20–26 and `tests/unit/test_errors.py::test_subclasses_are_markers_only`). The Phase-1 closure of marker subclasses is enumerated in `tests/unit/test_errors.py::EXPECTED_SUBCLASSES`. Slug allowlist in `tests/unit/test_errors.py::DOCUMENTED_MODULE_SLUGS` already includes `parsers` and `catalogs`.
  - `src/codegenie/logging.py` (Phase 0) — `structlog` factory used for the cap-exceeded event.
- **S1-01 validation follow-ups:**
  - `_validation/S1-01-errors-extension.md §"Open questions / follow-ups for downstream stories"` — explicit S1-02 obligation to extend `SymlinkRefusedError` Phase-0 docstring once the parser raise site broadens.

## Goal

Ship `src/codegenie/parsers/safe_json.py::load(path, *, max_bytes, max_depth=64) -> dict[str, JSONValue]` that:

1. Opens the path with `os.open(path, os.O_RDONLY | os.O_NOFOLLOW)` and translates `OSError(errno=ELOOP)` to `SymlinkRefusedError` carrying a formatted message that names the path.
2. Refuses oversize bytes **before any read** by inspecting `os.fstat(fd).st_size`; raises `SizeCapExceeded` carrying a formatted message that names the path and the observed-vs-cap sizes.
3. Decodes with stdlib `json.loads` (ADR-0009).
4. Rejects over-depth structures with a stdlib walker that descends both `dict` and `list` recursively; raises `DepthCapExceeded` carrying a formatted message that names the path and the cap.
5. Translates `json.JSONDecodeError` to `MalformedJSONError`; rejects non-object roots (the function returns `dict[str, JSONValue]`, so a top-level list/scalar/null is a malformed shape).
6. Lets `FileNotFoundError` (i.e., `OSError(errno=ENOENT)`) pass through unchanged.
7. Emits exactly one `probe.parser.cap_exceeded` structured log event before raising on a cap violation, with fields `event="probe.parser.cap_exceeded"`, `cap_kind ∈ {"size","depth"}`, `path` (str), `parser="safe_json"`, `parser_kind="safe_json"`.
8. Closes the file descriptor on every exit path (success, size cap, malformed, depth cap).

All typed exceptions are constructed as **markers** — single positional formatted-message string — preserving the Phase-0 `test_subclasses_are_markers_only` invariant.

## Acceptance criteria

Module / package shape:

- [ ] AC-1 — `src/codegenie/parsers/__init__.py` exists with a module docstring naming `phase-arch-design.md §"Component design" #8` and ADR-0008. Empty re-exports allowed; the package is the surface.
- [ ] AC-2 — `src/codegenie/parsers/safe_json.py` exports `load(path: Path, *, max_bytes: int, max_depth: int = 64) -> dict[str, JSONValue]` and a public `JSONValue` recursive type alias (importable from `codegenie.parsers` or `codegenie.parsers.safe_json`).
- [ ] AC-3 — `src/codegenie/parsers/safe_json.py` module docstring references `phase-arch-design.md §"Component design" #8`, ADR-0008, and ADR-0009.

Open / cap / read:

- [ ] AC-4 — Open uses `os.open(path, os.O_RDONLY | os.O_NOFOLLOW)`; the resulting fd is closed in `try/finally` on **every** exit path (success, `SizeCapExceeded`, `MalformedJSONError`, `DepthCapExceeded`, short read). The symlink-refusal path never opens an fd and closes nothing.
- [ ] AC-5 — `OSError` with `errno == errno.ELOOP` is translated to `SymlinkRefusedError(f"{path}: O_NOFOLLOW refused symlink")`. **All other `OSError` subtypes propagate unchanged** — specifically `IsADirectoryError`, `PermissionError`, `FileNotFoundError`, and any `OSError` whose `errno` is not `ELOOP`.
- [ ] AC-6 — Pre-parse size check via `os.fstat(fd).st_size > max_bytes` raises `SizeCapExceeded(f"{path}: size={size} cap={max_bytes}")` **before any `os.read` is called**. A test asserts that the read does not occur (e.g., `tracemalloc` peak stays under a low ceiling for a 50 MB sparse file with a 1 KB cap, or `monkeypatch.setattr(os, "read", _fail_read)` asserts `os.read` was not called).
- [ ] AC-7 — A short read (`os.read` returns fewer bytes than `os.fstat` size) raises `MalformedJSONError(f"{path}: short read")`. Forced via monkey-patch in the test; no silent retry.

Decode / shape:

- [ ] AC-8 — `json.JSONDecodeError` is translated to `MalformedJSONError(f"{path}: <detail>")`, where `<detail>` is the first 200 chars of `str(exc)`. The raw source bytes (`exc.doc`) are **never** included in the message (ADR-0008 secret-leak prevention).
- [ ] AC-9 — A top-level non-object JSON root (list, scalar, `null`) raises `MalformedJSONError(f"{path}: expected JSON object at top level")`. The function returns `dict[str, JSONValue]`; non-object roots violate that contract.
- [ ] AC-10 — An empty file (`size == 0`) raises `MalformedJSONError(f"{path}: empty file")` (or the `JSONDecodeError`-translation path — implementation chooses, but **must not** silently return `{}`).

Depth walker:

- [ ] AC-11 — Post-parse depth walker (stdlib-only second pass) descends recursively into **both `dict` values and `list` items**. Raises `DepthCapExceeded(f"{path}: depth>{max_depth}")` when nesting exceeds `max_depth`.
- [ ] AC-12 — Boundary: a structure whose deepest leaf is at depth exactly `max_depth` passes; at depth `max_depth + 1` it raises. Parametrized tests cover depths `{0, 1, max_depth-1, max_depth, max_depth+1}` and **at least one mixed dict/list shape** (e.g., `[{"x": [{"x": ...}]}]`).

Logging:

- [ ] AC-13 — On size-cap violation, emits one structlog event with fields `event="probe.parser.cap_exceeded"`, `cap_kind="size"`, `path=str(path)`, `parser="safe_json"`, `parser_kind="safe_json"`. Asserted via `structlog.testing.capture_logs()`.
- [ ] AC-14 — On depth-cap violation, emits one structlog event with fields `event="probe.parser.cap_exceeded"`, `cap_kind="depth"`, `path=str(path)`, `parser="safe_json"`, `parser_kind="safe_json"`. Asserted via `structlog.testing.capture_logs()`.
- [ ] AC-15 — No `probe.parser.cap_exceeded` event is emitted on the happy path, on `MalformedJSONError`, or on `SymlinkRefusedError`.

Phase-0 marker contract preservation:

- [ ] AC-16 — Every raise constructs the marker with **exactly one positional argument** (the formatted message). No keyword arguments. No subclass adds `__init__`, `__str__`, or instance/class state — `tests/unit/test_errors.py::test_subclasses_are_markers_only` continues to pass.
- [ ] AC-17 — Each raised exception's `args[0]` contains the absolute `str(path)` substring. Tests assert via `assert str(path) in exc_info.value.args[0]` (recoverable-at-catch-site contract per ADR-0007).

S1-01 follow-up:

- [ ] AC-18 — `src/codegenie/errors.py::SymlinkRefusedError.__doc__` is extended so its raise inventory names `parsers/safe_json` alongside the existing "writer / sanitizer walker" raises. The docstring continues to satisfy `tests/unit/test_errors.py::test_every_subclass_has_raise_site_docstring` (slug `parsers` is already in `DOCUMENTED_MODULE_SLUGS`). The slug `writer` remains in the docstring.

Toolchain:

- [ ] AC-19 — `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files. `mypy --strict` accepts the `JSONValue` recursive alias and the `Mapping[str, JSONValue]` return without `# type: ignore`.

## Implementation outline

1. Create `src/codegenie/parsers/__init__.py` (module docstring + `JSONValue` recursive alias exported).
2. Create `src/codegenie/parsers/safe_json.py` with module docstring referencing arch §"Component design" #8, ADR-0008, ADR-0009.
3. Implement `load(path, *, max_bytes, max_depth=64)`:
   ```
   try:
       fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
   except OSError as exc:
       if exc.errno == errno.ELOOP:
           raise SymlinkRefusedError(f"{path}: O_NOFOLLOW refused symlink") from exc
       raise  # FileNotFoundError / IsADirectoryError / PermissionError / etc. propagate
   try:
       size = os.fstat(fd).st_size
       if size > max_bytes:
           _emit_cap_event(cap_kind="size", path=path)
           raise SizeCapExceeded(f"{path}: size={size} cap={max_bytes}")
       data = os.read(fd, size)
       if len(data) != size:
           raise MalformedJSONError(f"{path}: short read")
   finally:
       os.close(fd)
   try:
       obj = json.loads(data)
   except json.JSONDecodeError as exc:
       detail = str(exc)[:200]
       raise MalformedJSONError(f"{path}: {detail}") from exc
   if not isinstance(obj, dict):
       raise MalformedJSONError(f"{path}: expected JSON object at top level")
   _assert_depth(obj, max_depth, current=0, path=path)
   return obj
   ```
4. `_assert_depth(obj, max_depth, current, path)`:
   - If `current > max_depth`: emit depth-cap event, raise `DepthCapExceeded(f"{path}: depth>{max_depth}")`.
   - If `isinstance(obj, dict)`: for each value, recurse with `current + 1`.
   - If `isinstance(obj, list)`: for each item, recurse with `current + 1`.
   - Else: terminate.
   - The walker also guards against `RecursionError`: if `sys.getrecursionlimit() - len(inspect.stack())` would be exhausted before `max_depth`, raise `DepthCapExceeded` defensively rather than letting `RecursionError` surface (rare at depth 64; defensive for future raises of `max_depth`).
5. `_emit_cap_event(cap_kind, path)` — single private helper, emits once. Uses the literal `"probe.parser.cap_exceeded"`; S1-10 lifts to a module constant.
6. Edit `src/codegenie/errors.py::SymlinkRefusedError.__doc__` per AC-18. Single-line addition naming `parsers/safe_json`. Pre-existing slug `"writer"` remains; new slug `"parsers"` is already in `DOCUMENTED_MODULE_SLUGS`.
7. Write `tests/unit/parsers/test_safe_json.py` with the test plan below.

## TDD plan — red / green / refactor

> **Red→green→refactor commit sequence** is documented in the PR description. The implementer first lands `tests/unit/parsers/test_safe_json.py` with `xfail`/`ModuleNotFoundError`-style red, then implements, then refactors; reviewers can check `git log` for the three commits.

### Red — failing test first

Test file: `tests/unit/parsers/test_safe_json.py`. The skeleton below names every test that the green implementation must satisfy. Each test is annotated with the AC(s) it pins and (where relevant) the mutation it catches.

```python
# tests/unit/parsers/test_safe_json.py
import errno
import json
import os
import sys
import tracemalloc
from pathlib import Path

import pytest
import structlog
from structlog.testing import capture_logs

import codegenie.errors as e
from codegenie.parsers import safe_json
from codegenie.parsers.safe_json import load
# JSONValue type alias is importable for mypy spot-checks:
from codegenie.parsers import JSONValue  # noqa: F401  # AC-2 surface


# --- Happy path & surface --------------------------------------------------

def test_happy_path_returns_dict(tmp_path: Path) -> None:
    p = tmp_path / "package.json"
    p.write_text(json.dumps({"name": "x", "version": "1.0.0"}))
    out = load(p, max_bytes=5_242_880)
    assert isinstance(out, dict)
    assert out["name"] == "x"
    assert out["version"] == "1.0.0"

def test_module_docstring_references_arch_and_adrs() -> None:
    # AC-3 — module docstring is part of the contract; a mutation that drops
    # it or strips the references regresses an audit invariant.
    doc = (safe_json.__doc__ or "").lower()
    assert "component design" in doc and "#8" in doc
    assert "adr-0008" in doc
    assert "adr-0009" in doc

def test_load_signature_is_keyword_only_caps_and_default_depth_is_64() -> None:
    import inspect
    sig = inspect.signature(load)
    params = sig.parameters
    assert params["path"].kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                  inspect.Parameter.POSITIONAL_ONLY)
    assert params["max_bytes"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["max_depth"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["max_depth"].default == 64


# --- Open / O_NOFOLLOW / errno mapping -------------------------------------

def test_symlink_refused_does_not_dereference(tmp_path: Path) -> None:
    # AC-5 + TQ2 — symlink target carries a sentinel that would be visible if
    # O_NOFOLLOW were dropped. A mutation that uses plain os.open(O_RDONLY)
    # would return the sentinel dict instead of raising.
    target = tmp_path / "outside_sentinel.json"
    target.write_text(json.dumps({"sentinel": "leaked"}))
    link = tmp_path / "package.json"
    link.symlink_to(target)
    with pytest.raises(e.SymlinkRefusedError) as exc_info:
        load(link, max_bytes=5_000)
    assert str(link) in exc_info.value.args[0]
    assert "O_NOFOLLOW" in exc_info.value.args[0]
    # Phase-0 markers-only invariant — exception exposes no instance state.
    for forbidden in ("path", "cap", "detail"):
        assert not hasattr(exc_info.value, forbidden)

def test_file_not_found_passes_through_unchanged(tmp_path: Path) -> None:
    # AC-5 — FileNotFoundError is OSError(errno=ENOENT); it must NOT be
    # smuggled into SymlinkRefusedError. Concrete type assertion guards
    # against a too-broad except OSError.
    with pytest.raises(FileNotFoundError):
        load(tmp_path / "missing.json", max_bytes=5_000)
    # SymlinkRefusedError must NOT match (would indicate over-translation).
    with pytest.raises(FileNotFoundError) as exc_info:
        load(tmp_path / "missing.json", max_bytes=5_000)
    assert not isinstance(exc_info.value, e.SymlinkRefusedError)

def test_is_a_directory_passes_through(tmp_path: Path) -> None:
    # AC-5 — EISDIR must NOT be translated into SymlinkRefusedError.
    d = tmp_path / "adir"
    d.mkdir()
    with pytest.raises(OSError) as exc_info:
        load(d, max_bytes=5_000)
    # Either IsADirectoryError (POSIX) or EISDIR — both are OSError, not SymlinkRefused.
    assert not isinstance(exc_info.value, e.SymlinkRefusedError)


# --- Size cap pre-parse ----------------------------------------------------

def test_size_cap_raises_before_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-6 + TQ3 — size check must precede os.read. Monkey-patch os.read to
    # raise; the SizeCapExceeded path must still fire (because os.read was
    # never called). A mutation that reads first would surface a different
    # exception (the patched RuntimeError).
    p = tmp_path / "big.json"
    p.write_text("0" * 1024)
    real_read = os.read
    read_calls: list[int] = []
    def _trap_read(fd: int, n: int) -> bytes:  # pragma: no cover - asserted
        read_calls.append(n)
        raise RuntimeError("os.read must not be called when size cap exceeded")
    monkeypatch.setattr(os, "read", _trap_read)
    with pytest.raises(e.SizeCapExceeded) as exc_info:
        load(p, max_bytes=100)
    assert read_calls == []
    msg = exc_info.value.args[0]
    assert str(p) in msg
    assert "cap=100" in msg
    assert "size=1024" in msg

def test_short_read_translates_to_malformed_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-7 — forced short read must raise MalformedJSONError; no silent retry.
    p = tmp_path / "small.json"
    p.write_text(json.dumps({"k": "v"}))
    real_read = os.read
    def _short(fd: int, n: int) -> bytes:
        return real_read(fd, max(1, n // 2))  # always short
    monkeypatch.setattr(os, "read", _short)
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=5_000)
    assert "short read" in exc_info.value.args[0]
    assert str(p) in exc_info.value.args[0]


# --- Malformed / shape -----------------------------------------------------

def test_malformed_json_translates_typed(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{not json}")
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=5_000)
    assert str(p) in exc_info.value.args[0]
    # AC-8 — raw bytes (`exc.doc`) MUST NOT appear in the message.
    assert "{not json}" not in exc_info.value.args[0]

def test_top_level_non_object_is_malformed(tmp_path: Path) -> None:
    # AC-9 — function returns dict[str, JSONValue]; non-object roots must
    # raise rather than silently returning a list.
    p = tmp_path / "arr.json"
    p.write_text("[1, 2, 3]")
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=5_000)
    assert "expected JSON object" in exc_info.value.args[0]

def test_empty_file_is_malformed(tmp_path: Path) -> None:
    # AC-10 — never silently return {}.
    p = tmp_path / "empty.json"
    p.write_text("")
    with pytest.raises(e.MalformedJSONError):
        load(p, max_bytes=5_000)


# --- Depth walker — boundary + mixed shapes --------------------------------

def _nested_dicts(depth: int) -> dict:
    """Produce {"x": {"x": ... 'leaf' at depth `depth` ...}}."""
    out: dict = {"leaf": True} if depth == 0 else {}
    cur = out
    for _ in range(depth):
        cur["x"] = {}
        cur = cur["x"]
    cur["leaf"] = True
    return out

def _mixed_nesting(depth: int) -> dict:
    """Produce a dict whose deepest leaf sits inside alternating list/dict."""
    leaf: object = "leaf"
    for i in range(depth):
        leaf = [leaf] if i % 2 == 0 else {"k": leaf}
    return {"root": leaf}

@pytest.mark.parametrize("inner_depth", [0, 1, 63, 64])
def test_depth_at_or_below_cap_passes(tmp_path: Path, inner_depth: int) -> None:
    # AC-12 — depth exactly at cap is accepted.
    p = tmp_path / "ok.json"
    p.write_text(json.dumps(_nested_dicts(inner_depth)))
    out = load(p, max_bytes=10_000_000, max_depth=64)
    assert isinstance(out, dict)

@pytest.mark.parametrize("inner_depth", [65, 70, 200])
def test_depth_above_cap_raises(tmp_path: Path, inner_depth: int) -> None:
    # AC-11 + AC-12 — depth above cap raises.
    p = tmp_path / "deep.json"
    p.write_text(json.dumps(_nested_dicts(inner_depth)))
    with pytest.raises(e.DepthCapExceeded) as exc_info:
        load(p, max_bytes=10_000_000, max_depth=64)
    msg = exc_info.value.args[0]
    assert str(p) in msg
    assert "depth>64" in msg

def test_depth_walker_descends_into_lists(tmp_path: Path) -> None:
    # AC-11 / CV1 / TQ4 — a dict-only walker would miss this.
    p = tmp_path / "list_bomb.json"
    p.write_text(json.dumps(_mixed_nesting(100)))
    with pytest.raises(e.DepthCapExceeded):
        load(p, max_bytes=10_000_000, max_depth=64)

def test_depth_walker_handles_pure_list_nesting(tmp_path: Path) -> None:
    # AC-11 — a list-of-list bomb (with a wrapping dict to honor the
    # top-level-object contract).
    p = tmp_path / "lol.json"
    deep: object = "leaf"
    for _ in range(100):
        deep = [deep]
    p.write_text(json.dumps({"root": deep}))
    with pytest.raises(e.DepthCapExceeded):
        load(p, max_bytes=10_000_000, max_depth=64)


# --- Markers-only contract preserved (Phase-0 invariant) -------------------

def test_raised_markers_carry_no_instance_state(tmp_path: Path) -> None:
    # AC-16, AC-17 — every Phase-1 typed exception this module raises is a
    # marker; path/cap/detail are recoverable from args[0] only.
    fixtures: list[tuple[Path, int, int, type[BaseException]]] = []
    # SizeCapExceeded
    big = tmp_path / "big.json"; big.write_text("0" * 1024)
    fixtures.append((big, 100, 64, e.SizeCapExceeded))
    # MalformedJSONError
    bad = tmp_path / "bad.json"; bad.write_text("{not json}")
    fixtures.append((bad, 5_000, 64, e.MalformedJSONError))
    # DepthCapExceeded
    deep = tmp_path / "deep.json"; deep.write_text(json.dumps(_nested_dicts(70)))
    fixtures.append((deep, 10_000_000, 64, e.DepthCapExceeded))
    for path, cap, depth, exc_type in fixtures:
        with pytest.raises(exc_type) as exc_info:
            load(path, max_bytes=cap, max_depth=depth)
        assert isinstance(exc_info.value.args, tuple)
        assert len(exc_info.value.args) == 1
        assert isinstance(exc_info.value.args[0], str)
        assert str(path) in exc_info.value.args[0]
        for forbidden in ("path", "cap", "detail", "warning_id"):
            assert not hasattr(exc_info.value, forbidden), (
                f"{exc_type.__name__} must remain a marker; instance must not "
                f"carry {forbidden!r}"
            )


# --- FD lifecycle ----------------------------------------------------------

def test_fd_closed_on_every_exit_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-4 — every load that opened an fd must close it.
    opened: list[int] = []
    closed: list[int] = []
    real_open = os.open
    real_close = os.close
    def _open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd
    def _close(fd):
        closed.append(fd)
        return real_close(fd)
    monkeypatch.setattr(os, "open", _open)
    monkeypatch.setattr(os, "close", _close)

    # happy
    ok = tmp_path / "ok.json"; ok.write_text(json.dumps({"a": 1}))
    load(ok, max_bytes=5_000)
    # size cap
    big = tmp_path / "big.json"; big.write_text("0" * 1024)
    with pytest.raises(e.SizeCapExceeded):
        load(big, max_bytes=100)
    # malformed
    bad = tmp_path / "bad.json"; bad.write_text("{not json}")
    with pytest.raises(e.MalformedJSONError):
        load(bad, max_bytes=5_000)
    # depth cap
    deep = tmp_path / "deep.json"; deep.write_text(json.dumps(_nested_dicts(70)))
    with pytest.raises(e.DepthCapExceeded):
        load(deep, max_bytes=10_000_000, max_depth=64)
    assert opened == closed, f"fd leak: opened={opened} closed={closed}"


# --- Cap event emission ----------------------------------------------------

def test_size_cap_emits_event(tmp_path: Path) -> None:
    # AC-13.
    p = tmp_path / "big.json"; p.write_text("0" * 1024)
    with capture_logs() as logs:
        with pytest.raises(e.SizeCapExceeded):
            load(p, max_bytes=100)
    cap_events = [r for r in logs if r.get("event") == "probe.parser.cap_exceeded"]
    assert len(cap_events) == 1, f"expected exactly one cap event; got {cap_events}"
    ev = cap_events[0]
    assert ev["cap_kind"] == "size"
    assert ev["path"] == str(p)
    assert ev["parser"] == "safe_json"
    assert ev["parser_kind"] == "safe_json"

def test_depth_cap_emits_event(tmp_path: Path) -> None:
    # AC-14.
    p = tmp_path / "deep.json"
    p.write_text(json.dumps(_nested_dicts(70)))
    with capture_logs() as logs:
        with pytest.raises(e.DepthCapExceeded):
            load(p, max_bytes=10_000_000, max_depth=64)
    cap_events = [r for r in logs if r.get("event") == "probe.parser.cap_exceeded"]
    assert len(cap_events) == 1
    ev = cap_events[0]
    assert ev["cap_kind"] == "depth"
    assert ev["path"] == str(p)
    assert ev["parser"] == "safe_json"
    assert ev["parser_kind"] == "safe_json"

def test_no_cap_event_on_happy_path(tmp_path: Path) -> None:
    # AC-15.
    p = tmp_path / "ok.json"; p.write_text(json.dumps({"a": 1}))
    with capture_logs() as logs:
        load(p, max_bytes=5_000)
    assert not [r for r in logs if r.get("event") == "probe.parser.cap_exceeded"]

def test_no_cap_event_on_malformed_or_symlink(tmp_path: Path) -> None:
    # AC-15 — cap-exceeded event must not fire for non-cap failures.
    bad = tmp_path / "bad.json"; bad.write_text("{not json}")
    with capture_logs() as logs:
        with pytest.raises(e.MalformedJSONError):
            load(bad, max_bytes=5_000)
    assert not [r for r in logs if r.get("event") == "probe.parser.cap_exceeded"]
    target = tmp_path / "t.json"; target.write_text("{}")
    link = tmp_path / "link.json"; link.symlink_to(target)
    with capture_logs() as logs:
        with pytest.raises(e.SymlinkRefusedError):
            load(link, max_bytes=5_000)
    assert not [r for r in logs if r.get("event") == "probe.parser.cap_exceeded"]


# --- Read-budget bound (RAM-safety canary) ---------------------------------

def test_size_cap_bounds_memory_allocation(tmp_path: Path) -> None:
    # AC-6 (anti-mutation TQ3) — a 50 MB sparse file with a 1 KB cap must not
    # cause the parser to allocate ~50 MB; if read were ordered before the
    # cap check, tracemalloc would catch it.
    p = tmp_path / "sparse.json"
    with open(p, "wb") as f:
        f.seek(50 * 1024 * 1024 - 1)
        f.write(b"\x00")  # sparse where the FS supports it
    tracemalloc.start()
    try:
        with pytest.raises(e.SizeCapExceeded):
            load(p, max_bytes=1024)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # Generous ceiling: the implementation should not allocate the file body.
    # Trace memory is process-local so we leave a wide margin for stdlib churn.
    assert peak < 2 * 1024 * 1024, f"peak alloc {peak} bytes exceeded 2 MB cap"


# --- S1-01 follow-up — SymlinkRefusedError docstring extension -------------

def test_symlink_refused_error_doc_names_parsers() -> None:
    # AC-18 — the Phase-0 marker's raise inventory now also covers parsers.
    doc = (e.SymlinkRefusedError.__doc__ or "").lower()
    assert "parsers" in doc or "safe_json" in doc
    # Slug still in DOCUMENTED_MODULE_SLUGS; pre-existing writer/sanitizer
    # callers must still be named so the slug test continues to pass.
    assert "writer" in doc or "sanitizer" in doc
```

Run; confirm `ModuleNotFoundError` / `AttributeError`. Commit as **red**.

### Green — minimal impl

Follow the implementation outline above. Land enough code to make every test pass with no excess (Rule 2 / Rule 3). Commit as **green**.

### Refactor — clean up

- Extract `_emit_cap_event(cap_kind, path)` to keep `load` readable.
- Module-level docstring carries arch + ADR references (AC-3).
- `JSONValue` recursive alias defined once in `parsers/__init__.py` and re-exported by `safe_json` module.
- `load` docstring enumerates every raised exception (callers grep this when picking a `WarningId`).
- `_assert_depth` uses an explicit guard: if `sys.getrecursionlimit() - <stack-depth heuristic>` would be exhausted before `max_depth`, raise `DepthCapExceeded` rather than `RecursionError` (rare in practice at depth 64; defensive for any future raise of `max_depth`).
- No catch of `BaseException` anywhere in the cap path — only `OSError` (for `O_NOFOLLOW`) and `json.JSONDecodeError`.

Commit as **refactor**. Reviewers can check `git log` for the three commits.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/parsers/__init__.py` | New module — declare package; export `JSONValue` |
| `src/codegenie/parsers/safe_json.py` | New module — the `load` function |
| `src/codegenie/errors.py` | One-line docstring extension on `SymlinkRefusedError` (AC-18 / S1-01 follow-up) |
| `tests/unit/parsers/__init__.py` | New (empty) |
| `tests/unit/parsers/test_safe_json.py` | New — happy path + cap/error paths + event assertions + fd-lifecycle + boundary depth + mixed nesting + markers-only |

## Out of scope

- **`safe_yaml`** — S1-03.
- **`jsonc`** — S1-04 (chains into `safe_json.load`).
- **Adversarial fixture corpus** — S5-01 (`test_json_bomb_huge_string.py`, `test_json_bomb_deep_nesting.py`, `test_symlink_escape_in_declared_inputs.py`). This story carries unit-test coverage of the same code paths via small in-test fixtures and a sparse-file canary.
- **`probe.parser.cap_exceeded` event-name constant in `codegenie/logging.py`** — S1-10 registers it as a module-level `Final[str]`. This story emits the event literal-string; S1-10 lifts it into the constant.
- **`MalformedYAMLError`** raise sites (in `safe_yaml.load`) — S1-03.
- **Carrying machine-readable `path` / `cap` / `detail` attributes on exception instances** — explicitly forbidden by the Phase-0 markers-only invariant (`tests/unit/test_errors.py::test_subclasses_are_markers_only`). The catch site reconstructs the `WarningId` from probe context per ADR-0007.
- **Lifting `_assert_depth` into a shared util** — wait until `safe_yaml` (S1-03) lands; then refactor at S1-03 if the walker is identical in shape (Rule 2 / Rule 3).

## Notes for the implementer

- **Markers-only construction.** Every typed exception this story raises is a Phase-0 marker. Construct with **one positional string** (the formatted message). No kwargs. No instance attributes. The catch site (a probe) parses `args[0]` if it needs to; the probe also constructs the `WarningId` per ADR-0007 (e.g., `package_json.size_cap_exceeded`).
- **One-shot `os.read(fd, size)`** is correct because `size` is bounded by `max_bytes` and we've already cap-checked. Don't loop. But **always verify `len(data) == size`** — a short read is `MalformedJSONError`, never a silent partial success.
- **`O_NOFOLLOW` semantics differ** on macOS vs Linux. Both raise `ELOOP` when the **final** path component is a symlink. macOS still follows symlinks in **intermediate** components. Phase 1's threat model only cares about the final component; document this in the module docstring.
- **Only `errno == ELOOP` translates to `SymlinkRefusedError`.** `IsADirectoryError` (EISDIR), `PermissionError` (EACCES), `FileNotFoundError` (ENOENT), and any other `OSError` propagate unchanged. The test asserts `not isinstance(exc, SymlinkRefusedError)` for the `EISDIR` and `ENOENT` paths to guard against an over-broad `except OSError`.
- **`MalformedJSONError` message detail.** Use `str(exc)[:200]` (the JSONDecodeError message). **Never** include `exc.doc` (the source bytes) — that's exactly the kind of secret-leak channel ADR-0008's sanitizer prevents from reaching disk, and the structlog event would carry it to logs.
- **Top-level shape.** Phase 1's consumers all read top-level JSON objects (`package.json`, `tsconfig.json` extends-chain, lockfiles). A top-level list/scalar/null is rejected as `MalformedJSONError`. If a future probe needs to load JSON whose root is not an object, add a sibling `load_any` function then — don't widen `load`'s return type.
- **The post-parse depth walker is load-bearing.** Until Python's stdlib `json` gains a `max_depth` parameter (PEP open since 2014, not landed), this walker is the only defense against JSON bombs that parse but consume O(depth) RSS during downstream traversal. Walk **both** dicts and lists.
- **Don't catch `BaseException`.** Only `OSError` (for `O_NOFOLLOW`) and `json.JSONDecodeError`. Anything else is a bug we want to see (Rule 12).
- **Structlog testing.** Use `structlog.testing.capture_logs()` rather than reading stderr — robust across renderer/init order changes.
- The structlog event uses the literal `"probe.parser.cap_exceeded"`. S1-10 introduces a module-level constant; this story is allowed to use the literal pending that.
