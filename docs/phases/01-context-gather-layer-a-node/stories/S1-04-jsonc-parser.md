# Story S1-04 — `jsonc` comment-stripper feeding `safe_json`

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Ready
**Effort:** S
**Depends on:** S1-02
**ADRs honored:** ADR-0009, ADR-0008

## Context

`tsconfig.json` is JSON-with-comments (JSONC). `NodeBuildSystemProbe` (S2-02) parses it to follow the `extends` chain and read compiler options. The stdlib `json` rejects comments; ADR-0009 forbids adopting `pyjson5` / `orjson`. Phase 1 ships a ~30-LOC stdlib state-machine comment stripper that feeds the stripped bytes back through `safe_json.load`, keeping a single chokepoint for size + depth + `O_NOFOLLOW` defenses.

The stripper is the only hand-rolled parser in shared code, so pathological inputs (unterminated strings, nested block comments, strings containing `//`) must complete in < 1 s or raise `MalformedJSONError` — never hang.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #8` — ~30-LOC state-machine; chains into `safe_json.load`.
  - `../phase-arch-design.md §"Edge cases"` rows for tsconfig-pathological — deeply nested block comments + unterminated string + circular `extends` must parse or raise typed error in < 1 s.
  - `../phase-arch-design.md §"Component design" #2` — `tsconfig.json` is the load-bearing consumer; `extends` chain ≤ 4 levels.
- **Phase ADRs:**
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — ADR-0009 — no `pyjson5`/`orjson` even for JSONC.
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — ADR-0008 — caps stay in-process; jsonc reuses safe_json's defenses by chaining into it.
- **Source design:**
  - `../final-design.md §"Components" #8` — short statement of the chained approach.
- **Existing code:**
  - `src/codegenie/parsers/safe_json.py` (S1-02) — `jsonc.load` calls this internally after stripping comments.
  - `src/codegenie/errors.py` (S1-01) — `MalformedJSONError`, `SizeCapExceeded`, `DepthCapExceeded`, `SymlinkRefusedError`.

## Goal

Ship `src/codegenie/parsers/jsonc.py::load(path, *, max_bytes, max_depth=64) -> dict[str, JSONValue]` that opens with `O_NOFOLLOW`, reads bytes, strips line + block + nested-block comments correctly (without breaking strings that contain `//`), and parses the cleaned text via `safe_json`'s post-parse depth path.

## Acceptance criteria

- [ ] `src/codegenie/parsers/jsonc.py` exports `load(path: Path, *, max_bytes: int, max_depth: int = 64) -> dict[str, JSONValue]`.
- [ ] Open uses `O_NOFOLLOW`; size-check on `os.fstat` before any read (raises `SizeCapExceeded`).
- [ ] Strip line comments `// ...` to end-of-line.
- [ ] Strip block comments `/* ... */` including nested block comments `/* outer /* inner */ outer */`.
- [ ] Strings containing `//` or `/*` are preserved verbatim (state machine tracks the in-string flag, including escaped `\"`).
- [ ] Unterminated strings raise `MalformedJSONError(path=path, detail="unterminated string")` deterministically; do not hang or scan to EOF in O(n²).
- [ ] Unterminated block comments raise `MalformedJSONError(path=path, detail="unterminated block comment")`.
- [ ] After stripping, the remaining bytes go through the same depth-walker shape as `safe_json` (in practice: call `json.loads(stripped)` and run the same `_assert_depth`).
- [ ] Adversarial single-file test (deeply nested block comments + unterminated string + circular references) completes in < 1 s (pytest `@pytest.mark.timeout(1)` or equivalent).
- [ ] Unit tests cover line, block, nested-block comments, strings with `//`, escaped quotes, unterminated string, unterminated block comment, happy-path tsconfig fixture, size-cap, depth-cap.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Create `src/codegenie/parsers/jsonc.py` with `load(...)` and a private `_strip_comments(data: bytes) -> bytes` state-machine.
2. State machine has four states: `CODE`, `STRING`, `LINE_COMMENT`, `BLOCK_COMMENT(depth)`. Transitions:
   - `CODE` + `//` → `LINE_COMMENT` (skip until `\n`).
   - `CODE` + `/*` → `BLOCK_COMMENT(1)`.
   - `CODE` + `"` → `STRING`.
   - `STRING` + `\"` → stay (escape).
   - `STRING` + `"` → `CODE`.
   - `STRING` + `\n` or EOF → raise `MalformedJSONError("unterminated string")`.
   - `BLOCK_COMMENT(n)` + `/*` → `BLOCK_COMMENT(n+1)`.
   - `BLOCK_COMMENT(n)` + `*/` → `BLOCK_COMMENT(n-1)` or back to `CODE` if `n-1 == 0`.
   - `BLOCK_COMMENT(n)` + EOF → raise `MalformedJSONError("unterminated block comment")`.
3. `load` flow: open + size-check (same as `safe_json`) → `data = os.read(...)` → `stripped = _strip_comments(data)` → `obj = json.loads(stripped)` (translate `JSONDecodeError` → `MalformedJSONError`) → depth-walk (raise `DepthCapExceeded`).
4. Re-export the same `probe.parser.cap_exceeded` event with `parser_kind="jsonc"` on cap violation.

## TDD plan — red / green / refactor

### Red — failing test first

Test file: `tests/unit/parsers/test_jsonc.py`.

```python
# tests/unit/parsers/test_jsonc.py
import pytest

import codegenie.errors as e
from codegenie.parsers import jsonc


def test_line_comments_stripped(tmp_path):
    p = tmp_path / "tsconfig.json"
    p.write_text('{\n  "compilerOptions": {} // trailing comment\n}\n')
    out = jsonc.load(p, max_bytes=10_000)
    assert out == {"compilerOptions": {}}

def test_block_comments_stripped(tmp_path):
    p = tmp_path / "tsconfig.json"
    p.write_text('{\n  /* block */ "k": 1\n}\n')
    out = jsonc.load(p, max_bytes=10_000)
    assert out == {"k": 1}

def test_nested_block_comments(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{ /* outer /* inner */ outer */ "k": 1 }')
    out = jsonc.load(p, max_bytes=10_000)
    assert out["k"] == 1

def test_strings_containing_slash_slash_preserved(tmp_path):
    # the // inside the string must NOT be treated as a comment
    p = tmp_path / "x.json"
    p.write_text('{"u": "https://example.com/path"}')
    out = jsonc.load(p, max_bytes=10_000)
    assert out["u"] == "https://example.com/path"

def test_strings_containing_block_open_preserved(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{"k": "/* not a comment */"}')
    out = jsonc.load(p, max_bytes=10_000)
    assert out["k"] == "/* not a comment */"

def test_escaped_quote_in_string(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(r'{"k": "she said \"hi\""}')
    out = jsonc.load(p, max_bytes=10_000)
    assert out["k"] == 'she said "hi"'

def test_unterminated_string_raises_fast(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{"k": "never closed')
    with pytest.raises(e.MalformedJSONError):
        jsonc.load(p, max_bytes=10_000)

def test_unterminated_block_comment_raises_fast(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{ /* never closed "k": 1 }')
    with pytest.raises(e.MalformedJSONError):
        jsonc.load(p, max_bytes=10_000)

@pytest.mark.timeout(1)
def test_pathological_input_under_1s(tmp_path):
    # deeply nested block comments + unterminated bits — must raise typed error in < 1s
    payload = "{ " + "/* " * 5000 + '"k": 1 ' + " */" * 5000 + " }"
    p = tmp_path / "evil.json"
    p.write_text(payload)
    # the well-balanced version should parse OK; flip to unbalanced for the failure path
    out = jsonc.load(p, max_bytes=1_000_000)
    assert out["k"] == 1

def test_depth_cap_post_strip(tmp_path):
    # 70 nested objects — the comment-strip leaves valid JSON; depth walker catches
    payload = "{" + '"x":{' * 70 + "}" + "}" * 70
    p = tmp_path / "deep.json"
    p.write_text(payload)
    with pytest.raises(e.DepthCapExceeded):
        jsonc.load(p, max_bytes=10_000, max_depth=64)
```

Run; confirm `ModuleNotFoundError`. Commit as red.

### Green — minimal impl

Implement the four-state machine in `_strip_comments`. Use a `bytearray` for the output to avoid quadratic string concatenation. Iterate by index (single pass). Track:

- `i: int` — current position
- `state: int` — one of `CODE`, `STRING`, `LINE_COMMENT`, `BLOCK_COMMENT`
- `block_depth: int` — only meaningful in `BLOCK_COMMENT`
- `escaped: bool` — only meaningful in `STRING`

Append the byte to output only when in `CODE` or `STRING`. Comment runs append nothing; preserve newlines from `LINE_COMMENT` so downstream `json.loads` line numbers stay sensible (optional but helpful for error messages).

After strip, the rest of `load` mirrors `safe_json` (parse + depth-walk).

### Refactor — clean up

- Module docstring naming `phase-arch-design.md §"Component design" #8` and ADR-0009 (no pyjson5).
- The depth walker code: if S1-03 lifted to `parsers/_depth.py`, reuse the same callable. Otherwise inline as in S1-02.
- Avoid regex entirely — Rule 7 + the regex-DoS concern. The state machine is the only safe shape.
- Single-pass guarantee — assert `len(stripped) ≤ len(data)` at the end as a structural invariant (cheap; catches bugs where the machine accidentally emits more bytes than it consumed).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/parsers/jsonc.py` | New module — comment stripper + `load` |
| `tests/unit/parsers/test_jsonc.py` | New — line/block/nested/strings/escaped/unterminated/depth-cap/pathological |

## Out of scope

- **`tsconfig.json` `extends` chain following** — that's `NodeBuildSystemProbe`'s job (S2-02). This story only parses the bytes of one `tsconfig.json`.
- **Local fuzzing** — the implementer should fuzz locally per `phase-arch-design.md §Step 1 risks` ("fuzz it locally with an atheris-style hostile input set before opening the Step 1 PR"). Atheris is not a project dependency; use stdlib `random` + timeout loop for local fuzzing. Acceptance criteria do not include checked-in fuzz harness.
- **Adversarial fixture** — S5-03 (`test_tsconfig_pathological.py`) extends to the integration layer.

## Notes for the implementer

- **`pytest-timeout` plugin** may not be installed. Use `pytest.mark.timeout` if available; otherwise wrap in `signal.alarm`-based timeout, or just measure `time.monotonic()` inside the test and `assert elapsed < 1.0`. Pick one and stick with it.
- **Newline preservation:** when skipping a line comment, output a newline so JSON parser line numbers in error messages remain useful. When skipping a block comment, output spaces equal to the length of the stripped block (or just nothing — debatable; prefer nothing because it's simpler and `tsconfig.json` errors are rarely line-number-debugged in Phase 1).
- **No regex.** Even for "find the next `*/`" — the linear scan is safer. Regex on hostile input is exactly what ADR-0008 mitigates.
- **`\"` inside strings is the only escape that matters** for state-machine correctness. `\\` is also important — `"path\\\\to"` followed by `"` should not be treated as unescaping. Test this case if not covered above (`r'{"k": "trailing-backslash\\\\"}'`).
- **JSON5 is not the goal.** JSONC is a strict subset: just comments. Don't add support for trailing commas, single-quoted strings, unquoted keys, or hex numbers. Per Rule 2 (Simplicity First), the smallest stripper that handles `tsconfig.json` is the goal.
- **The "well-balanced pathological" test in TDD** above uses 5,000 `/* ... */` pairs nested. That's 10,000 state transitions — O(n). Single-pass is the only sustainable shape.
- The shared depth walker (if extracted in S1-03) accepts a `path: Path` for the exception. Pass `path` here too.
