# Story S1-02 — `safe_json` parser with `O_NOFOLLOW` + size + depth caps

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0008, ADR-0009, ADR-0007

## Context

`safe_json` is the chokepoint every Phase 1 probe (and every future probe) routes JSON reads through: `package.json`, `package-lock.json`, `tsconfig.json` (via `jsonc`), `coverage/lcov.info` is the only JSON-adjacent file that doesn't go through here. Its three structural defenses — `O_NOFOLLOW` open, pre-parse size cap on the fd, post-parse depth walker — close ~95% of the adversarial-bytes threat surface without per-probe sandboxes (ADR-0008). The stdlib `json` C extension exposes no native depth limit, so the post-parse walker is load-bearing.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #8` — full interface, `O_NOFOLLOW`, post-parse depth walker rationale; the five-way exception map (`SizeCapExceeded | DepthCapExceeded | MalformedJSONError | SymlinkRefusedError` plus passthrough `FileNotFoundError`).
  - `../phase-arch-design.md §"Harness engineering" → "Logging strategy"` — `probe.parser.cap_exceeded` event with `cap_kind ∈ {"size","depth"}`, `path`, `parser` fields; `parser_kind` tracing field.
  - `../phase-arch-design.md §"Edge cases"` rows 2, 3 — 600 MB string `package.json`, symlink to `/etc/passwd`.
- **Phase ADRs:**
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — ADR-0008 — in-process caps replace the sandbox; this module is the load-bearing surface.
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — ADR-0009 — must use stdlib `json.loads`; no `orjson`/`pyjson5`/`ruamel.yaml`.
  - `../ADRs/0007-warnings-id-pattern.md` — ADR-0007 — caller maps to `WarningId` like `package_json.size_cap_exceeded`.
- **Source design:**
  - `../final-design.md §"Components" #8` — the design statement.
- **Existing code:**
  - `src/codegenie/errors.py` (after S1-01) — `SizeCapExceeded`, `DepthCapExceeded`, `MalformedJSONError`, `SymlinkRefusedError`.
  - `src/codegenie/logging.py` (Phase 0) — `structlog` factory used for the cap-exceeded event.

## Goal

Ship `src/codegenie/parsers/safe_json.py::load(path, *, max_bytes, max_depth=64) -> dict[str, JSONValue]` that opens with `O_NOFOLLOW`, refuses oversize bytes pre-parse, parses with stdlib `json.loads`, and rejects over-depth structures with a stdlib walker.

## Acceptance criteria

- [ ] `src/codegenie/parsers/__init__.py` exists (empty module re-exports allowed).
- [ ] `src/codegenie/parsers/safe_json.py` exports `load(path: Path, *, max_bytes: int, max_depth: int = 64) -> dict[str, JSONValue]`.
- [ ] Open uses `os.open(path, os.O_RDONLY | os.O_NOFOLLOW)`; the resulting fd is closed in `try/finally`; `OSError` with `errno == ELOOP` is translated to `SymlinkRefusedError(path=path)`.
- [ ] Pre-parse size check: `os.fstat(fd).st_size > max_bytes` raises `SizeCapExceeded(path=path, cap=max_bytes)` **before** any `read()`.
- [ ] Post-parse depth walker (stdlib-only second pass) raises `DepthCapExceeded(path=path, cap=max_depth)` when nesting exceeds `max_depth`.
- [ ] Any `json.JSONDecodeError` is translated to `MalformedJSONError(path=path, detail=<short msg>)`.
- [ ] `FileNotFoundError` passes through unchanged (callers decide how to render absence).
- [ ] Emits one `probe.parser.cap_exceeded` structlog event on cap violation (fields: `cap_kind`, `path`, `parser`, `parser_kind="safe_json"`).
- [ ] Unit tests cover: happy path, size-cap pre-parse, depth-cap post-parse, `O_NOFOLLOW` symlink refusal, `MalformedJSONError` on invalid bytes, `FileNotFoundError` passthrough.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Create `src/codegenie/parsers/__init__.py` (empty, with module docstring referencing `phase-arch-design.md §"Component design" #8`).
2. Create `src/codegenie/parsers/safe_json.py` with the `load` function and a private `_assert_depth(obj, max_depth)` recursive walker.
3. Use `os.open(path, os.O_RDONLY | os.O_NOFOLLOW)`; size-check via `os.fstat`; `os.read(fd, size)` in one shot (since size is bounded by `max_bytes`); decode bytes with `json.loads`.
4. Catch `OSError` and translate `ELOOP`/`ENOTDIR`/`EINVAL` (symlink loop) to `SymlinkRefusedError`. All others re-raise.
5. Emit the structlog event before raising on cap violation.
6. Write `tests/unit/parsers/test_safe_json.py` with one test per acceptance criterion.

## TDD plan — red / green / refactor

### Red — failing test first

Test file: `tests/unit/parsers/test_safe_json.py`.

```python
# tests/unit/parsers/test_safe_json.py
import json
import os
from pathlib import Path

import pytest

import codegenie.errors as e
from codegenie.parsers import safe_json


def test_happy_path(tmp_path):
    # arrange: write a small valid JSON object
    p = tmp_path / "package.json"
    p.write_text(json.dumps({"name": "x", "version": "1.0.0"}))
    # act: parse with a generous cap
    out = safe_json.load(p, max_bytes=5_242_880)
    # assert: returns the dict; type is dict
    assert out["name"] == "x"

def test_size_cap_raises_pre_parse(tmp_path):
    # arrange: 1 KB of valid JSON, but cap is 100 bytes
    p = tmp_path / "big.json"
    p.write_text(json.dumps({"k": "v" * 1024}))
    # act/assert: SizeCapExceeded fires; the call must not have parsed
    with pytest.raises(e.SizeCapExceeded) as exc:
        safe_json.load(p, max_bytes=100)
    assert exc.value.cap == 100

def test_depth_cap_raises_post_parse(tmp_path):
    # arrange: build a 70-deep nested object; depth cap is 64
    obj = current = {}
    for _ in range(70):
        current["x"] = {}
        current = current["x"]
    p = tmp_path / "deep.json"
    p.write_text(json.dumps(obj))
    # act/assert
    with pytest.raises(e.DepthCapExceeded) as exc:
        safe_json.load(p, max_bytes=10_000, max_depth=64)
    assert exc.value.cap == 64

def test_symlink_refused(tmp_path):
    # arrange: create a symlink package.json → outside (e.g., target file in tmp)
    target = tmp_path / "outside"
    target.write_text("{}")
    link = tmp_path / "package.json"
    link.symlink_to(target)
    # act/assert: O_NOFOLLOW refuses to follow symlink
    with pytest.raises(e.SymlinkRefusedError):
        safe_json.load(link, max_bytes=5_000)

def test_malformed_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json}")
    with pytest.raises(e.MalformedJSONError):
        safe_json.load(p, max_bytes=5_000)

def test_file_not_found_passes_through(tmp_path):
    with pytest.raises(FileNotFoundError):
        safe_json.load(tmp_path / "missing.json", max_bytes=5_000)

def test_cap_exceeded_emits_structlog_event(tmp_path, capsys, monkeypatch):
    # arrange: route structlog to capsys; ensure JSON renderer
    monkeypatch.setattr("sys.stderr.isatty", lambda: False)
    from codegenie.logging import configure_logging
    configure_logging(verbose=False)
    p = tmp_path / "big.json"
    p.write_text("0" * 200)
    # act
    with pytest.raises(e.SizeCapExceeded):
        safe_json.load(p, max_bytes=100)
    # assert: stderr contains the event name
    err = capsys.readouterr().err
    assert "probe.parser.cap_exceeded" in err
    assert "safe_json" in err
```

Run; confirm `ModuleNotFoundError` / `AttributeError`. Commit as red.

### Green — minimal impl

`safe_json.load`:

1. `fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)` inside `try`; catch `OSError` → translate `ELOOP` to `SymlinkRefusedError(path=path)`.
2. `size = os.fstat(fd).st_size`; if `size > max_bytes`: emit cap-exceeded event, raise `SizeCapExceeded`.
3. `data = os.read(fd, size)` (one shot — size is bounded).
4. `os.close(fd)` in `finally`.
5. `try: obj = json.loads(data)` `except json.JSONDecodeError as exc: raise MalformedJSONError(path=path, detail=str(exc)) from exc`.
6. `_assert_depth(obj, max_depth, current=0)` — recursive dict/list walker; on overflow emit event + raise `DepthCapExceeded`.
7. Return `obj`.

### Refactor — clean up

- Type-annotate: `JSONValue` alias under `parsers/__init__.py` or local; the function returns `dict[str, JSONValue]`.
- Add module docstring referencing `phase-arch-design.md §"Component design" #8` and ADR-0008.
- Move structlog event emission to a private `_emit_cap_event(cap_kind, path)` helper to keep `load` readable.
- Docstring on `load` describes every raised exception (callers grep this when picking a `WarningId`).
- `_assert_depth` should use an explicit recursion limit guard — if `sys.getrecursionlimit()` would be hit before `max_depth`, raise `DepthCapExceeded` rather than `RecursionError` (rare in practice with depth 64, but defensive).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/parsers/__init__.py` | New module — declare package |
| `src/codegenie/parsers/safe_json.py` | New module — the `load` function |
| `tests/unit/parsers/__init__.py` | New (empty) |
| `tests/unit/parsers/test_safe_json.py` | New — happy path + four cap/error paths + event assertion |

## Out of scope

- **`safe_yaml`** — S1-03.
- **`jsonc`** — S1-04 (chains into `safe_json.load`).
- **Adversarial fixture corpus** — S5-01 (`test_json_bomb_huge_string.py`, `test_json_bomb_deep_nesting.py`, `test_symlink_escape_in_declared_inputs.py`). This story carries unit-test coverage of the same code paths via small in-test fixtures.
- **`probe.parser.cap_exceeded` event-name constant in `codegenie/logging.py`** — S1-10 registers it as a module-level `Final[str]`. This story emits the event literal-string; S1-10 lifts it into the constant.

## Notes for the implementer

- **One-shot `os.read(fd, size)`** is correct because `size` is bounded by `max_bytes` and we've already cap-checked. Don't loop — extra read state is one more chance to mis-handle EINTR.
- **`O_NOFOLLOW` semantics differ** on macOS vs Linux. Linux raises `ELOOP` when the **final** path component is a symlink. macOS does too, but symlinks in **intermediate** components are still followed. Phase 1's threat model only cares about the final component; document this in the module docstring.
- **`MalformedJSONError(detail=str(exc))`** — pass the first 200 chars of the JSONDecodeError message. Don't include the source bytes (`exc.doc`) in the detail — that's exactly the kind of secret-leak channel ADR-0008's sanitizer prevents from reaching disk, and the structlog event would carry it to logs.
- **The post-parse depth walker is load-bearing.** Until Python's stdlib `json` gains a `max_depth` parameter (PEP open since 2014, not landed), this walker is the only defense against JSON bombs that parse but consume O(depth) RSS during downstream traversal. Do not skip it as "we'll add it later."
- **Don't catch `BaseException`** in the cap path — only `OSError` (for `O_NOFOLLOW`) and `json.JSONDecodeError`. Anything else is a bug we want to see.
- **Per `Rule 12` (Fail loud):** if `os.read` returns fewer bytes than `os.fstat` size, do NOT silently retry or treat as success. Raise `MalformedJSONError(detail="short read")`. A short read on a regular file is OS misbehavior; the gather should fail this probe loudly, not produce a partial parse.
- The structlog event uses the literal `"probe.parser.cap_exceeded"`. S1-10 introduces a module-level constant; this story is allowed to use the literal pending that.
