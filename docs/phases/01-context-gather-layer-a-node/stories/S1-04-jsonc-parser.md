# Story S1-04 — `jsonc` parser: state-machine comment stripper chained into `safe_json`

**Step:** Step 1 — Plant shared primitives, sub-schema convention, and the three Phase-0 in-place edits
**Status:** Ready (hardened by phase-story-validator)
**Effort:** S
**Depends on:** S1-02 (chronological — consumes `parsers._io` / `parsers._depth` if S1-03 lifted them; otherwise mirrors `safe_json`'s shape)
**ADRs honored:** ADR-0008, ADR-0009, ADR-0007; Phase-0 markers-only contract

## Validation notes (phase-story-validator, 2026-05-13)

This story was hardened by the validator from its initial draft. Key changes:

- **Markers-only construction restored (block-tier consistency fix).** The original draft prescribed `MalformedJSONError(path=path, detail="unterminated string")` — kwarg construction. That violates the Phase 0 markers-only invariant pinned by `tests/unit/test_errors.py::test_subclasses_are_markers_only` (`cls.__init__ is e.CodegenieError.__init__` + class-dict allowlist) and re-affirmed by S1-01 / S1-02 / S1-03 hardening reports. **Marker subclasses accept exactly one positional `args[0]` message and expose no instance state.** Raise sites must construct via a formatted message string (e.g., `MalformedJSONError(f"{path}: unterminated string")`). Adding the prescribed kwargs would `TypeError` at red-commit time against the actual `errors.py` shipped by S1-01 (CN1, CV1, TQ1).
- **`O_NOFOLLOW` / size-cap parity with `safe_json` made explicit.** The original draft said "Open uses `O_NOFOLLOW`; size-check on `os.fstat` before any read" but did not pin that **no `os.read` is called when the cap is exceeded**, nor that the fd is closed on every exit path. A mutation that reorders to read-then-check, or leaks the fd on `MalformedJSONError`, would pass the original tests silently. Added ACs (AC-6, AC-7, AC-8) + tests (`test_size_cap_raises_before_read`, `test_fd_closed_on_every_exit_path`, `test_short_read_translates_to_malformed_json`) (CV3, TQ3, TQ10).
- **Interface clarified — `jsonc.load` is a strategy that pre-processes bytes, not a path-rewriter.** The original draft said "the remaining bytes go through the same depth-walker shape as `safe_json` (in practice: call `json.loads(stripped)` and run the same `_assert_depth`)". That is correct in spirit but does not pin the dependency. `safe_json.load` takes a `Path`, not bytes — `jsonc.load` cannot call it; it must (a) open + cap-check its own fd, (b) read bytes, (c) call `_strip_comments(bytes) -> bytes`, (d) `json.loads(stripped)`, (e) shared depth walker (`parsers._depth.assert_max_depth` if S1-03 lifted it; otherwise duplicate the same walker shape) (CN6, CV5).
- **Plugin / strategy framing made explicit (Open/Closed, Extension by Addition).** This is the third concrete parser after `safe_json` (S1-02) and `safe_yaml` (S1-03). The shared kernel (`parsers/_io.py` for O_NOFOLLOW + size-cap + structlog event, `parsers/_depth.py` for the post-parse depth walker) was established by S1-03's hardening. `jsonc.py` consumes the kernel; the parser-specific shape is the comment stripper. The `parser_kind="jsonc"` literal supplied to the structlog event is the strategy's discriminator — no `ParserRegistry` ABC, no factory; new parsers are new files + new `parser_kind` literals (Rule 2: three similar lines is better than premature abstraction; the kernel of two stateless functions IS the right factoring). CLAUDE.md load-bearing commitment — "Extension by addition" — is satisfied (CN2).
- **Depth walker descends both `dict` values and `list` items.** The original draft's `test_depth_cap_post_strip` used pure-dict nesting (`{"x":{"x":...`). A walker that descends only into `dict` would pass billion-laughs-via-list inside a JSONC file. Pinned to AC-15 + parametrized `test_depth_walker_descends_lists_and_dicts` (CV11, TQ8 — inherited from S1-02 hardening).
- **Depth boundary parametrized.** Added an AC and parametrized test: exactly `depth == max_depth` passes, `depth == max_depth + 1` raises. Original draft used 70 vs cap 64 only — no boundary assertion (CV12).
- **Cap-exceeded event structured fields pinned via `structlog.testing.capture_logs()`.** The original draft did not assert event emission at all. Added ACs (AC-17, AC-18, AC-19) + tests that assert `event="probe.parser.cap_exceeded"`, `cap_kind ∈ {"size","depth"}`, `path=str(path)`, `parser="jsonc"`, `parser_kind="jsonc"`. Also pins no event on happy / malformed / symlink paths (CV6, CN4, TQ17).
- **Non-ELOOP OSError passthrough pinned.** Added AC-5: only `errno == ELOOP` translates to `SymlinkRefusedError`. `FileNotFoundError` (ENOENT), `IsADirectoryError` (EISDIR), `PermissionError` (EACCES) all propagate unchanged. The test asserts `not isinstance(exc, SymlinkRefusedError)` for ENOENT and EISDIR paths (CV7, TQ6).
- **Symlink test sharpened against silent-dereference.** Added `test_symlink_refused_does_not_dereference` with a sentinel target (`{"sentinel": "leaked"}`). If `O_NOFOLLOW` were dropped, the sentinel dict would silently surface; the missing-exception assertion fires (TQ2 — same defense as S1-02).
- **Empty file → `MalformedJSONError`.** Original draft had no test. Added AC-9 + `test_empty_file_is_malformed`. `_strip_comments(b'') == b''` is a degenerate-input invariant; the chained `json.loads(b'')` raises, translated to `MalformedJSONError(f"{path}: empty file")` (CV13).
- **Top-level non-object → `MalformedJSONError`.** Original draft had no test for `[1,2,3]` JSONC root (a list, valid JSON, valid JSONC). The function signature promises `dict[str, JSONValue]`; non-object roots must raise. Added AC-10 + `test_top_level_non_object_is_malformed` parametrized over list / scalar / null (CV14 — inherited from S1-02 hardening).
- **Block-comment containing `"` does not transition to STRING.** State-machine mutation #6: in `BLOCK_COMMENT(n)`, a `"` byte must be inert. The original draft had no test for `/* "fake string" */`. Added `test_block_comment_containing_double_quote_is_inert` (TQ6).
- **`\\` escape inside strings handled.** Original draft's implementer note #4 named this case (`r'{"k": "trailing-backslash\\\\"}'`) but no AC. The state-machine correctness hazard is: a string ending in `\\"` (escaped backslash + closing quote) must NOT extend into the next state. Added AC-13 + parametrized `test_string_with_backslash_escapes`: covers `"\""` (escaped quote), `"\\\\"` (escaped backslash), `"\\\""` (escaped backslash followed by escaped quote), `"path\\"` (string ends in backslash THEN quote — closing quote is real), each with the next byte being a real JSON token (e.g., `,`) (CV14, TQ19).
- **Unterminated paths have wall-clock assertion, not just a typed-error assertion.** Original drafts' `test_unterminated_string_raises_fast` and `test_unterminated_block_comment_raises_fast` raised the typed error but did not assert "fast". A mutation that scans to EOF in O(n²) by trying to recover would pass. Added timing assertion via `time.monotonic()` (≤ 0.5 s on a 1 MB unterminated string) — works regardless of whether `pytest-timeout` is installed (CV15, TQ11, TQ12 — and implementer-notes #1 ambiguity resolved: stop relying on `pytest.mark.timeout`).
- **Pathological-input test uses unbalanced shape with explicit timeout.** Original draft's `test_pathological_input_under_1s` used the balanced 5,000 × `/* ... */` nesting and asserted success. The true hazard is the unbalanced version (the comment never closes), which the comment is supposed to test ("the well-balanced version should parse OK; flip to unbalanced for the failure path"). Replaced with two parametrized tests: well-balanced 5,000-deep nesting parses in < 1 s; unbalanced 1 MB block-comment-never-closes raises `MalformedJSONError` in < 1 s. The wall-clock budget is asserted via `time.monotonic()` (CV15, TQ11).
- **No-regex structural invariant pinned.** The implementer note "Avoid regex entirely" was promoted to a structural test: `test_module_does_not_import_re` asserts `import re` is not in the module's import graph (`"re" not in sys.modules` after `importlib.reload(codegenie.parsers.jsonc)` and AST scan of the module source) (TQ16, implementer-note #3).
- **`_strip_comments` is a pure function over `bytes -> bytes`.** Added AC-14 — the helper is callable in unit-tests directly (no fd, no path, no logging), making the state-machine table-testable. The `len(stripped) ≤ len(data)` structural invariant from refactor-note #5 promoted to an AC + assertion in the stripper (cheap; catches a bug where the machine accidentally emits more bytes than it consumed).
- **`SymlinkRefusedError` docstring extension (S1-01 / S1-02 follow-up).** S1-02's hardening added `parsers/safe_json` to the docstring; S1-03's hardening added `parsers/safe_yaml`. S1-04 adds `parsers/jsonc` (one-line append). The slug `"parsers"` is already in `DOCUMENTED_MODULE_SLUGS`; the append is human-readable observability so a grep for `jsonc` in the docstring inventory succeeds (AC-22).
- **Markers-only test parametrized across all four marker types this module raises.** Tests assert each marker carries exactly one `args[0]` positional string, contains `str(path)`, and has no `.path` / `.cap` / `.detail` / `.warning_id` attributes. Catches mutation #1 (kwarg construction) deterministically (AC-21).
- **`json.loads` decode-error message bound to 200 chars; raw source bytes NEVER included.** `JSONDecodeError.doc` carries the source bytes; including them in the structlog/exception message is a secret-leak channel (ADR-0008). Added AC-11 + test (`test_malformed_json_message_truncated_and_no_doc_bytes`). This is byte-equal to S1-02's AC-8.
- **Newline preservation when stripping line comments.** Original implementer-note #2 said "output a newline so JSON parser line numbers in error messages remain useful" but no AC. Promoted to AC-16: `_strip_comments` preserves the **newline** byte that terminated a line comment (the comment body is discarded; the trailing `\n` survives so downstream `json.loads` error line numbers track the source). Block comments are replaced with nothing (per implementer-note prescription).
- **AC-style "TDD red test exists, committed, green" demoted from AC.** Process discipline; replaced with a "red→green→refactor commit sequence is documented in the PR description" line under TDD plan, not as an AC (consistent with S1-02 / S1-03 hardenings).

Full report: `_validation/S1-04-jsonc-parser.md`.

## Context

`tsconfig.json` is JSON-with-comments (JSONC). `NodeBuildSystemProbe` (S2-02) parses it to follow the `extends` chain and read compiler options. The stdlib `json` rejects comments; ADR-0009 forbids adopting `pyjson5` / `orjson`. Phase 1 ships a ~30-LOC stdlib state-machine comment stripper that feeds the stripped bytes to `json.loads` + the shared depth walker, keeping a single chokepoint for size + depth + `O_NOFOLLOW` defenses (ADR-0008).

`jsonc.py` is the **third concrete parser strategy** after `safe_json` (S1-02) and `safe_yaml` (S1-03). The kernel established by S1-03's hardening — `parsers/_io.py` (O_NOFOLLOW + pre-parse size cap + structlog event) and `parsers/_depth.py` (post-parse depth walker; id()-memoized for YAML alias-safety, no-op-but-correct for JSON which has no aliases) — is consumed here. The parser-specific shape is the comment stripper; the `parser_kind="jsonc"` literal is the strategy's discriminator on the structlog event field. **No `ParserRegistry`, no `Parser` ABC, no factory.** Open/Closed is satisfied by "new file + new `parser_kind` literal" (Rule 2: three similar lines is better than premature abstraction; the kernel of two stateless functions consumed by N parsers IS the right factoring).

The stripper is the only hand-rolled parser in shared code, so pathological inputs (unterminated strings, nested block comments, strings containing `//`, strings inside block comments containing `"`, backslash-escapes at end-of-string) must complete in < 1 s or raise `MalformedJSONError` — never hang. Single-pass O(n) is the only safe shape (Rule 7 — regex on hostile input is exactly what ADR-0008 mitigates).

The Phase-0 markers-only invariant (`tests/unit/test_errors.py::test_subclasses_are_markers_only`) means the typed exceptions S1-01 introduced carry **no instance state**: path and parse-failure detail live in the positional `args[0]` formatted message, recoverable at the catch site by the calling probe.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #8` — full interface; jsonc is the chained pre-processor; `parsers/jsonc.py` ships alongside `safe_json.py` and `safe_yaml.py`.
  - `../phase-arch-design.md §"Edge cases"` row 8 (`test_tsconfig_pathological.py` — deeply nested block comments + unterminated string + circular `extends`; jsonc parses or raises typed error in < 1 s).
  - `../phase-arch-design.md §"Component design" #2` — `tsconfig.json` is the load-bearing consumer; `extends` chain ≤ 4 levels.
  - `../phase-arch-design.md §"Harness engineering" → "Tracing strategy"` — `parser_kind ∈ {safe_json, safe_yaml, jsonc, _pnpm, _npm, _yarn}` on every parse-related event.
  - `../phase-arch-design.md §"Data model"` — `JSONValue` recursive alias.
- **Phase ADRs:**
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — ADR-0009 — no `pyjson5`/`orjson` even for JSONC; hand-rolled stripper is the chosen path.
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — ADR-0008 — caps stay in-process; jsonc reuses safe_json's defenses by chaining into the shared kernel.
  - `../ADRs/0007-warnings-id-pattern.md` — ADR-0007 — caller maps to `WarningId` like `tsconfig.size_cap_exceeded`. **`WarningId` is constructed at the catch site, not embedded on the exception.**
- **Source design:**
  - `../final-design.md §"Components" #8` — short statement of the chained approach.
- **Existing code (already on `master` after S1-02):**
  - `src/codegenie/parsers/safe_json.py` (S1-02) — the precedent for O_NOFOLLOW open + size cap + depth walker shape. `jsonc.load` mirrors it for fd lifecycle + size/depth defenses; the additional pre-stage is `_strip_comments`.
  - `src/codegenie/parsers/__init__.py` (S1-02) — declares `JSONValue` and the parser-package module docstring.
  - `src/codegenie/errors.py` (S1-01) — `MalformedJSONError`, `SizeCapExceeded`, `DepthCapExceeded`, `SymlinkRefusedError` are **markers only** (no `__init__`, no class attributes; see module docstring lines 20–26 and `tests/unit/test_errors.py::test_subclasses_are_markers_only`). The slug `"parsers"` is already in `tests/unit/test_errors.py::DOCUMENTED_MODULE_SLUGS`.
  - `src/codegenie/logging.py` (Phase 0) — `structlog` factory used for the cap-exceeded event.
  - `tests/unit/parsers/test_safe_json.py` (S1-02) — precedent for `structlog.testing.capture_logs()` event-field assertions, fd-lifecycle test, markers-only parametrized check.
- **S1-02 hardened story shape (precedent):**
  - `_validation/S1-02-safe-json-parser.md` — kwarg-construction-is-the-block defense, ELOOP-only OSError narrowing, fd-lifecycle parity, size-cap-precedes-read monkey-patch.
- **S1-03 hardened story shape (precedent):**
  - `_validation/S1-03-safe-yaml-parser.md` — plugin-shape kernel framing (`_io.py` + `_depth.py`), structured-field event assertions via `structlog.testing.capture_logs`, markers-only positional construction across all 4 marker types.

## Goal

Ship `src/codegenie/parsers/jsonc.py::load(path, *, max_bytes, max_depth=64) -> dict[str, JSONValue]` that:

1. Opens the path with `os.open(path, os.O_RDONLY | os.O_NOFOLLOW)` and translates `OSError(errno=ELOOP)` to `SymlinkRefusedError` carrying a formatted message that names the path. **Only `ELOOP` translates; all other `OSError` subtypes propagate unchanged** (specifically `FileNotFoundError`, `IsADirectoryError`, `PermissionError`).
2. Refuses oversize bytes **before any `os.read` is called** by inspecting `os.fstat(fd).st_size`; raises `SizeCapExceeded` carrying a formatted message that names the path and the observed-vs-cap sizes.
3. Reads the bytes (one-shot `os.read(fd, size)`; short read raises `MalformedJSONError(f"{path}: short read")` — never silent retry).
4. Strips line comments (`// ...` to end-of-line), block comments (`/* ... */`), and **nested block comments** (`/* outer /* inner */ outer */`) via a pure `_strip_comments(data: bytes) -> bytes` state-machine helper. Strings containing `//`, `/*`, or `*/` are preserved verbatim; `\"`, `\\`, and other backslash escapes inside strings are honored; **`"` inside a block comment is inert** (does not enter STRING state).
5. Asserts the **structural invariant** `len(stripped) ≤ len(data)` (cheap; catches a bug where the machine emits more bytes than it consumed).
6. Decodes the stripped bytes with stdlib `json.loads` (ADR-0009; **no `orjson`/`pyjson5`/`hjson`**). Translates `json.JSONDecodeError` to `MalformedJSONError(f"{path}: <truncated detail>")`; **never** includes the raw source bytes (`exc.doc`) in the message (ADR-0008 secret-leak prevention).
7. Rejects non-object roots: a top-level list, scalar, or `null` raises `MalformedJSONError(f"{path}: expected JSON object at top level")` — the function signature promises `dict[str, JSONValue]`.
8. Rejects an empty file: `MalformedJSONError(f"{path}: empty file")` (or the `JSONDecodeError`-translation path — implementation chooses, but **must not** silently return `{}`).
9. Rejects unterminated strings (`MalformedJSONError(f"{path}: unterminated string")`) and unterminated block comments (`MalformedJSONError(f"{path}: unterminated block comment")`) **in O(n) wall-clock time**: a 1 MB unterminated input completes the typed-error raise in ≤ 0.5 s (no quadratic recovery, no EOF re-scan).
10. Runs the shared post-parse depth walker (`parsers._depth.assert_max_depth` if S1-03 lifted it; otherwise the inline walker mirroring `safe_json._assert_depth`) descending **both `dict` values and `list` items**; raises `DepthCapExceeded(f"{path}: depth>{max_depth}")` on violation.
11. Closes the file descriptor on every exit path (success, size cap, malformed bytes, malformed JSON, depth cap, short read). The symlink-refusal path never opens an fd.
12. Emits exactly one `probe.parser.cap_exceeded` structured log event before raising on a cap violation, with fields `event="probe.parser.cap_exceeded"`, `cap_kind ∈ {"size","depth"}`, `path=str(path)`, `parser="jsonc"`, `parser_kind="jsonc"`.
13. Uses **no regex** anywhere in the module (`import re` is forbidden — Rule 7; regex on hostile input is what ADR-0008 mitigates).

All typed exceptions are constructed as **markers** — single positional formatted-message string — preserving the Phase-0 `test_subclasses_are_markers_only` invariant.

## Acceptance criteria

Module / package shape:

- [ ] AC-1 — `src/codegenie/parsers/jsonc.py` exports `load(path: Path, *, max_bytes: int, max_depth: int = 64) -> dict[str, JSONValue]` with `max_bytes` and `max_depth` **keyword-only**. `max_depth` defaults to `64`.
- [ ] AC-2 — Module `__all__` includes `"load"`; `JSONValue` is re-exported from the package (already declared in `parsers/__init__.py`) so callers may spell `codegenie.parsers.JSONValue` or `codegenie.parsers.jsonc.JSONValue` interchangeably.
- [ ] AC-3 — `src/codegenie/parsers/jsonc.py` module docstring references `phase-arch-design.md §"Component design" #8`, ADR-0008, and ADR-0009.
- [ ] AC-4 — Module imports **do not** include `re` (regex banned; asserted by an AST scan in the unit test — `test_module_does_not_import_re`).

Open / cap / read:

- [ ] AC-5 — `OSError` with `errno == errno.ELOOP` is translated to `SymlinkRefusedError(f"{path}: O_NOFOLLOW refused symlink")`. **All other `OSError` subtypes propagate unchanged** — specifically `IsADirectoryError`, `PermissionError`, `FileNotFoundError`, and any `OSError` whose `errno` is not `ELOOP`. Tests assert `not isinstance(exc, SymlinkRefusedError)` for the `ENOENT` and `EISDIR` paths.
- [ ] AC-6 — Open uses `os.open(path, os.O_RDONLY | os.O_NOFOLLOW)`. A symlink whose final component is the link itself raises `SymlinkRefusedError`; the test target carries a sentinel (`{"sentinel": "leaked"}`) so a missing-`O_NOFOLLOW` mutation surfaces as a silent dereference.
- [ ] AC-7 — Pre-parse size check via `os.fstat(fd).st_size > max_bytes` raises `SizeCapExceeded(f"{path}: size={size} cap={max_bytes}")` **before any `os.read` is called**. Asserted via `monkeypatch.setattr(os, "read", _trap_read)`; `os.read` must not be called when the cap is exceeded.
- [ ] AC-8 — The fd is closed in `try/finally` on **every** exit path (success, `SizeCapExceeded`, short read, `MalformedJSONError` from strip stage, `MalformedJSONError` from `json.loads`, `MalformedJSONError` from top-level-non-object, `DepthCapExceeded`). The symlink-refusal path never opens an fd. Asserted by a monkey-patched `os.open` / `os.close` pair that records and compares counts.
- [ ] AC-9 — A short read (`os.read` returns fewer bytes than `os.fstat` size) raises `MalformedJSONError(f"{path}: short read")`. Forced via monkey-patch in the test; no silent retry.

Stripper — state machine correctness:

- [ ] AC-10 — `_strip_comments(data: bytes) -> bytes` is a **pure function** (no fd, no path argument, no logging); importable for unit-test table-testing.
- [ ] AC-11 — The stripper asserts the structural invariant `len(stripped) ≤ len(data)` at exit (cheap defensive assertion); tests force inputs that drive this invariant to its boundary (empty, all-comment, all-string).
- [ ] AC-12 — Line comments (`// ...` through end-of-line) are stripped; the terminating `\n` is **preserved** so downstream `json.loads` line-number errors track the source file's lines.
- [ ] AC-13 — Block comments (`/* ... */`) and **nested block comments** (`/* outer /* inner */ outer */`) are stripped. Nesting depth is unbounded by the stripper's state (the byte cap dominates); the block-depth counter is an `int`.
- [ ] AC-14 — Strings containing `//`, `/*`, or `*/` are preserved verbatim. Backslash escapes inside strings are honored:
  - `"\""` (escaped quote does NOT end the string),
  - `"\\\\"` (escaped backslash followed by a real closing quote),
  - `"\\\""` (escaped backslash, then escaped quote, then real closing quote),
  - `"\\"` (string ends in a backslash-followed-by-real-quote — the quote IS the terminator because the preceding `\` is itself escaped).
  Parametrized tests cover each shape, each followed by a real JSON token (e.g., `,` then another field).
- [ ] AC-15 — In `BLOCK_COMMENT(n)` state, a `"` byte is **inert** (does NOT transition to `STRING`). `/* "fake" */ {"k": 1}` strips to ` {"k": 1}` and parses successfully.
- [ ] AC-16 — Unterminated strings raise `MalformedJSONError(f"{path}: unterminated string")`. Unterminated block comments raise `MalformedJSONError(f"{path}: unterminated block comment")`. **In O(n) wall-clock time** — a 1 MB unterminated input completes the typed-error raise in ≤ 0.5 s. Asserted via `time.monotonic()`.

Decode / shape:

- [ ] AC-17 — After stripping, `json.loads(stripped)` is called. `json.JSONDecodeError` is translated to `MalformedJSONError(f"{path}: <detail>")`, where `<detail>` is the first 200 chars of `str(exc)`. The raw source bytes (`exc.doc`) are **never** included in the message (ADR-0008 secret-leak prevention).
- [ ] AC-18 — A top-level non-object JSON root (list, scalar, `null`) raises `MalformedJSONError(f"{path}: expected JSON object at top level")`. Parametrized tests cover `[1,2,3]`, `42`, `"a string"`, `null`.
- [ ] AC-19 — An empty file (`size == 0`) raises `MalformedJSONError` (path-named message). Must not silently return `{}`.

Depth walker:

- [ ] AC-20 — Post-parse depth walker (shared `parsers._depth.assert_max_depth` if S1-03 lifted; else inline-mirrored from `safe_json._assert_depth`) descends recursively into **both `dict` values and `list` items**. Raises `DepthCapExceeded(f"{path}: depth>{max_depth}")` when nesting exceeds `max_depth`.
- [ ] AC-21 — Boundary: a structure whose deepest leaf is at depth exactly `max_depth` passes; at depth `max_depth + 1` it raises. Parametrized tests cover depths `{0, 1, max_depth-1, max_depth, max_depth+1}` and at least one **mixed dict/list shape** (e.g., `[{"x": [{"x": ...}]}]`).

Logging:

- [ ] AC-22 — On size-cap violation, emits one structlog event with fields `event="probe.parser.cap_exceeded"`, `cap_kind="size"`, `path=str(path)`, `parser="jsonc"`, `parser_kind="jsonc"`. Asserted via `structlog.testing.capture_logs()`.
- [ ] AC-23 — On depth-cap violation, emits one structlog event with fields `event="probe.parser.cap_exceeded"`, `cap_kind="depth"`, `path=str(path)`, `parser="jsonc"`, `parser_kind="jsonc"`.
- [ ] AC-24 — No `probe.parser.cap_exceeded` event is emitted on the happy path, on `MalformedJSONError` (any cause), or on `SymlinkRefusedError`.

Phase-0 marker contract preservation:

- [ ] AC-25 — Every raise in this module constructs the marker with **exactly one positional argument** (the formatted message). No keyword arguments. No subclass adds `__init__`, `__str__`, or instance/class state — `tests/unit/test_errors.py::test_subclasses_are_markers_only` continues to pass. Asserted via parametrized `test_markers_only_positional_args0` exercising each raise site.
- [ ] AC-26 — Each raised exception's `args[0]` contains the absolute `str(path)` substring. Tests assert via `assert str(path) in exc_info.value.args[0]` (recoverable-at-catch-site contract per ADR-0007).

S1-01 / S1-02 / S1-03 follow-up:

- [ ] AC-27 — `src/codegenie/errors.py::SymlinkRefusedError.__doc__` is extended so its raise inventory names `parsers/jsonc` alongside the existing parsers/safe_json (and parsers/safe_yaml, if S1-03 has already landed). The docstring continues to satisfy `tests/unit/test_errors.py::test_every_subclass_has_raise_site_docstring` (slug `parsers` is already in `DOCUMENTED_MODULE_SLUGS`).

Pathological-input adversarial budget:

- [ ] AC-28 — A well-balanced pathological input (5,000 levels of nested block comments containing a single `"k": 1` payload) parses successfully in < 1 s (asserted via `time.monotonic()`).
- [ ] AC-29 — An unbalanced pathological input (1 MB of `/* never closed`) raises `MalformedJSONError(f"{path}: unterminated block comment")` in < 1 s (asserted via `time.monotonic()`).

Toolchain:

- [ ] AC-30 — `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files. `mypy --strict` accepts the recursive `JSONValue` alias and `Mapping[str, JSONValue]` return without `# type: ignore`.

## Implementation outline

1. Create `src/codegenie/parsers/jsonc.py` with module docstring referencing arch §"Component design" #8, ADR-0008, ADR-0009.
2. Imports: stdlib `errno`, `json`, `os`; `pathlib.Path`; `typing.Final`; `structlog`; `codegenie.errors`; `codegenie.parsers.JSONValue`. **No `import re`.** If S1-03 has lifted shared helpers, import `codegenie.parsers._io.open_capped_read` and `codegenie.parsers._depth.assert_max_depth`; otherwise mirror `safe_json`'s inline shape.
3. Module-level constants:
   ```python
   _PARSER_NAME: Final[str] = "jsonc"
   _EVENT_CAP_EXCEEDED: Final[str] = "probe.parser.cap_exceeded"
   _MAX_DECODE_DETAIL: Final[int] = 200
   _MAX_LINE_COMMENT_TERMINATOR: Final[int] = ord("\n")
   ```
4. Implement `_strip_comments(data: bytes) -> bytes` as a pure single-pass state machine:
   - States as integer constants: `_S_CODE = 0`, `_S_STRING = 1`, `_S_LINE_COMMENT = 2`, `_S_BLOCK_COMMENT = 3`.
   - Tracked variables: `i: int` (cursor), `state: int`, `block_depth: int` (meaningful only in `_S_BLOCK_COMMENT`), `escaped: bool` (meaningful only in `_S_STRING`).
   - Output: `bytearray` (avoids quadratic concatenation); returned as `bytes` at end.
   - Transitions (concise; expand in code with comments naming each transition):
     - `_S_CODE` + `//` (peek two bytes) → `_S_LINE_COMMENT` (output nothing for both bytes).
     - `_S_CODE` + `/*` → `_S_BLOCK_COMMENT(block_depth=1)`.
     - `_S_CODE` + `"` → `_S_STRING`; emit the `"`.
     - `_S_CODE` + other → emit byte.
     - `_S_STRING` + `\\` (backslash, when not already `escaped`) → emit `\\`, set `escaped = True`.
     - `_S_STRING` + any byte (when `escaped`) → emit, clear `escaped`.
     - `_S_STRING` + `"` (when not `escaped`) → emit `"`, transition to `_S_CODE`.
     - `_S_STRING` + other (when not `escaped`) → emit.
     - `_S_STRING` + EOF → `raise MalformedJSONError(f"{path}: unterminated string")`.
     - `_S_LINE_COMMENT` + `\n` → emit `\n`, transition to `_S_CODE`.
     - `_S_LINE_COMMENT` + other → drop.
     - `_S_LINE_COMMENT` + EOF → transition to `_S_CODE` (line comment at end of file is harmless).
     - `_S_BLOCK_COMMENT(n)` + `/*` → `_S_BLOCK_COMMENT(n+1)`. *Note: a `"` byte in this state is INERT (AC-15).*
     - `_S_BLOCK_COMMENT(n)` + `*/` → if `n == 1`, transition to `_S_CODE`; else `_S_BLOCK_COMMENT(n-1)`. Drop the `*/` bytes.
     - `_S_BLOCK_COMMENT(n)` + other → drop.
     - `_S_BLOCK_COMMENT(n)` + EOF → `raise MalformedJSONError(f"{path}: unterminated block comment")`.
   - Wall-clock guarantee: single-pass O(n) — every byte advances `i` at most by a constant amount; no inner loop scans back.
   - Final `assert len(stripped) <= len(data)` invariant (AC-11).
5. Implement `load(path, *, max_bytes, max_depth=64)`:
   ```python
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
       data = os.read(fd, size) if size > 0 else b""
       if len(data) != size:
           raise MalformedJSONError(f"{path}: short read")
   finally:
       os.close(fd)
   try:
       stripped = _strip_comments(data, path=path)  # path passed for the typed raise
   except MalformedJSONError:
       raise
   if not stripped:
       raise MalformedJSONError(f"{path}: empty file")
   try:
       obj = json.loads(stripped)
   except json.JSONDecodeError as exc:
       detail = str(exc)[:_MAX_DECODE_DETAIL]
       raise MalformedJSONError(f"{path}: {detail}") from exc
   if not isinstance(obj, dict):
       raise MalformedJSONError(f"{path}: expected JSON object at top level")
   _assert_depth(obj, max_depth=max_depth, current=0, path=path)
   return obj
   ```
   *Note:* `_strip_comments` takes a `path` kwarg so it can construct the typed exception with the path inside; the strip stage is the only stage that can be in a known "in-string" or "in-comment" parse state when raising, and the exception message must name the path per AC-26. An alternative shape is `_strip_comments(data) -> bytes` (purer) that raises a parser-local typed error which `load` translates to `MalformedJSONError(f"{path}: ...")`; either is acceptable as long as AC-10 (purity over data) and AC-26 (path in message) both hold. Pick one and document.
6. `_assert_depth` (or `parsers._depth.assert_max_depth`) — same shape as `safe_json._assert_depth`. Descends both `dict` values and `list` items. Emits depth-cap event before raise.
7. `_emit_cap_event(cap_kind, path)` — single private helper, emits one structlog event with `parser="jsonc"`, `parser_kind="jsonc"`.
8. Edit `src/codegenie/errors.py::SymlinkRefusedError.__doc__` per AC-27 — one-line append naming `parsers/jsonc`. Pre-existing slug `"writer"` / `"sanitizer walker"` / `"parsers/safe_json"` (and `parsers/safe_yaml` if S1-03 landed) remain.
9. Write `tests/unit/parsers/test_jsonc.py` with the test plan below.

## TDD plan — red / green / refactor

> **Red→green→refactor commit sequence** is documented in the PR description. The implementer first lands `tests/unit/parsers/test_jsonc.py` with `ModuleNotFoundError`-style red, then implements, then refactors; reviewers can check `git log` for the three commits.

### Red — failing test first

Test file: `tests/unit/parsers/test_jsonc.py`. The skeleton below names every test that the green implementation must satisfy. Each test is annotated with the AC(s) it pins and (where relevant) the mutation it catches.

```python
# tests/unit/parsers/test_jsonc.py
import ast
import errno
import inspect
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest
import structlog
from structlog.testing import capture_logs

import codegenie.errors as e
from codegenie.parsers import JSONValue, jsonc  # noqa: F401  # AC-2 surface
from codegenie.parsers.jsonc import _strip_comments, load


# --- Module surface & invariants -------------------------------------------

def test_module_docstring_references_arch_and_adrs() -> None:
    # AC-3.
    doc = (jsonc.__doc__ or "").lower()
    assert "component design" in doc and "#8" in doc
    assert "adr-0008" in doc
    assert "adr-0009" in doc

def test_load_signature_is_keyword_only_caps_and_default_depth_is_64() -> None:
    # AC-1.
    sig = inspect.signature(load)
    params = sig.parameters
    assert params["path"].kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.POSITIONAL_ONLY,
    )
    assert params["max_bytes"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["max_depth"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["max_depth"].default == 64

def test_module_does_not_import_re() -> None:
    # AC-4 / TQ16 — regex on hostile input is exactly what ADR-0008 mitigates.
    src = Path(jsonc.__file__).read_text()
    tree = ast.parse(src)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    assert "re" not in imports, f"jsonc module must not import re; got imports={imports}"


# --- Open / O_NOFOLLOW / errno mapping -------------------------------------

def test_symlink_refused_does_not_dereference(tmp_path: Path) -> None:
    # AC-5 + AC-6 + TQ2 — symlink target carries a sentinel. A mutation that
    # drops O_NOFOLLOW would silently dereference and return the sentinel dict.
    target = tmp_path / "outside_sentinel.json"
    target.write_text(json.dumps({"sentinel": "leaked"}))
    link = tmp_path / "tsconfig.json"
    link.symlink_to(target)
    with pytest.raises(e.SymlinkRefusedError) as exc_info:
        load(link, max_bytes=5_000)
    assert str(link) in exc_info.value.args[0]
    assert "O_NOFOLLOW" in exc_info.value.args[0]
    for forbidden in ("path", "cap", "detail"):
        assert not hasattr(exc_info.value, forbidden)

def test_file_not_found_passes_through_unchanged(tmp_path: Path) -> None:
    # AC-5 — FileNotFoundError (ENOENT) must NOT be smuggled into SymlinkRefusedError.
    with pytest.raises(FileNotFoundError) as exc_info:
        load(tmp_path / "missing.json", max_bytes=5_000)
    assert not isinstance(exc_info.value, e.SymlinkRefusedError)

def test_is_a_directory_passes_through(tmp_path: Path) -> None:
    # AC-5 — EISDIR must NOT be translated into SymlinkRefusedError.
    d = tmp_path / "adir"
    d.mkdir()
    with pytest.raises(OSError) as exc_info:
        load(d, max_bytes=5_000)
    assert not isinstance(exc_info.value, e.SymlinkRefusedError)


# --- Size cap pre-parse ----------------------------------------------------

def test_size_cap_raises_before_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-7 + TQ3 — size check must precede os.read.
    p = tmp_path / "big.json"
    p.write_text("0" * 1024)
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
    # AC-9 — forced short read raises MalformedJSONError; no silent retry.
    p = tmp_path / "small.json"
    p.write_text(json.dumps({"k": "v"}))
    real_read = os.read
    def _short(fd: int, n: int) -> bytes:
        return real_read(fd, max(1, n // 2))
    monkeypatch.setattr(os, "read", _short)
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=5_000)
    assert "short read" in exc_info.value.args[0]
    assert str(p) in exc_info.value.args[0]


# --- Stripper purity & invariants ------------------------------------------

def test_strip_comments_is_pure_bytes_to_bytes() -> None:
    # AC-10 — _strip_comments is a pure function callable without a Path.
    # (If the implementation chooses to pass `path` for typed-raise purposes,
    # the kwarg is optional and the function must still accept bytes-only callers.)
    out = _strip_comments(b'{"k": 1} // tail')
    assert isinstance(out, bytes)

@pytest.mark.parametrize("data", [
    b"",
    b"// line comment only\n",
    b'{"k": "all string"}',
    b"/* all comment */",
])
def test_strip_comments_length_invariant(data: bytes) -> None:
    # AC-11.
    out = _strip_comments(data)
    assert len(out) <= len(data)


# --- Stripper — comments ---------------------------------------------------

def test_line_comments_stripped(tmp_path: Path) -> None:
    # AC-12 — line comments to EOL stripped; terminating newline preserved.
    p = tmp_path / "tsconfig.json"
    p.write_text('{\n  "compilerOptions": {} // trailing comment\n}\n')
    out = load(p, max_bytes=10_000)
    assert out == {"compilerOptions": {}}

def test_block_comments_stripped(tmp_path: Path) -> None:
    # AC-13.
    p = tmp_path / "tsconfig.json"
    p.write_text('{\n  /* block */ "k": 1\n}\n')
    out = load(p, max_bytes=10_000)
    assert out == {"k": 1}

def test_nested_block_comments(tmp_path: Path) -> None:
    # AC-13 — nested block comments.
    p = tmp_path / "x.json"
    p.write_text('{ /* outer /* inner */ outer */ "k": 1 }')
    out = load(p, max_bytes=10_000)
    assert out["k"] == 1


# --- Stripper — strings: //, /*, */, escapes -------------------------------

def test_strings_containing_slash_slash_preserved(tmp_path: Path) -> None:
    # AC-14 — // inside a string is NOT a comment.
    p = tmp_path / "x.json"
    p.write_text('{"u": "https://example.com/path"}')
    out = load(p, max_bytes=10_000)
    assert out["u"] == "https://example.com/path"

def test_strings_containing_block_open_preserved(tmp_path: Path) -> None:
    # AC-14 — /* inside a string is NOT a block open.
    p = tmp_path / "x.json"
    p.write_text('{"k": "/* not a comment */"}')
    out = load(p, max_bytes=10_000)
    assert out["k"] == "/* not a comment */"

def test_escaped_quote_in_string(tmp_path: Path) -> None:
    # AC-14 — \" inside a string is NOT a terminator.
    p = tmp_path / "x.json"
    p.write_text(r'{"k": "she said \"hi\""}')
    out = load(p, max_bytes=10_000)
    assert out["k"] == 'she said "hi"'

@pytest.mark.parametrize(
    "raw,expected",
    [
        # Each case: a JSONC payload where the string's terminator is correctly
        # identified despite various backslash patterns. Each is followed by a
        # real JSON token (`, "next": 0`) to catch mutations that misclassify
        # the closing quote.
        (r'{"a": "x\\\\y", "b": 0}',  {"a": r"x\\y", "b": 0}),       # \\\\  → \\  (two real backslashes)
        (r'{"a": "x\\\"y", "b": 0}',  {"a": r"x\"y", "b": 0}),       # \\\"  → \"  (backslash then quote)
        (r'{"a": "trail\\\\", "b": 0}', {"a": "trail\\\\", "b": 0}), # \\\\ at end → \\ at end
        (r'{"a": "\"", "b": 0}',      {"a": "\"", "b": 0}),         # \"     → "
    ],
)
def test_string_with_backslash_escapes(tmp_path: Path, raw: str, expected: dict) -> None:
    # AC-14 — backslash-escape state-machine correctness.
    p = tmp_path / "x.json"
    p.write_text(raw)
    out = load(p, max_bytes=10_000)
    assert out == expected

def test_block_comment_containing_double_quote_is_inert(tmp_path: Path) -> None:
    # AC-15 / TQ6 — " in a block comment must NOT enter STRING state.
    # If the mutation treats `"` in BLOCK_COMMENT as a STRING transition, the
    # subsequent `*/` would be inside a "string" and never close the block.
    p = tmp_path / "x.json"
    p.write_text('/* "fake" */ {"k": 1}')
    out = load(p, max_bytes=10_000)
    assert out["k"] == 1


# --- Stripper — unterminated paths -----------------------------------------

def test_unterminated_string_raises_typed_in_bounded_time(tmp_path: Path) -> None:
    # AC-16 + TQ11 — typed error + wall-clock budget.
    p = tmp_path / "x.json"
    # 1 MB of payload, then opening quote, never closed.
    p.write_text('{"k": "' + "x" * 1_000_000)
    t0 = time.monotonic()
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=2_000_000)
    elapsed = time.monotonic() - t0
    assert "unterminated string" in exc_info.value.args[0]
    assert str(p) in exc_info.value.args[0]
    assert elapsed <= 0.5, f"unterminated-string detection took {elapsed:.3f}s; expected ≤ 0.5s"

def test_unterminated_block_comment_raises_typed_in_bounded_time(tmp_path: Path) -> None:
    # AC-16 + TQ12 — typed error + wall-clock budget.
    p = tmp_path / "x.json"
    p.write_text("{ /* " + ("x" * 1_000_000))
    t0 = time.monotonic()
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=2_000_000)
    elapsed = time.monotonic() - t0
    assert "unterminated block comment" in exc_info.value.args[0]
    assert str(p) in exc_info.value.args[0]
    assert elapsed <= 0.5, f"unterminated-block detection took {elapsed:.3f}s; expected ≤ 0.5s"


# --- Decode / shape --------------------------------------------------------

def test_malformed_json_message_truncated_and_no_doc_bytes(tmp_path: Path) -> None:
    # AC-17 — JSONDecodeError detail bounded; exc.doc bytes never included.
    p = tmp_path / "bad.json"
    p.write_text("// hi\n{not json}\n")
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=5_000)
    msg = exc_info.value.args[0]
    assert str(p) in msg
    assert "{not json}" not in msg  # raw source bytes must not appear

@pytest.mark.parametrize("payload", ["[1, 2, 3]", "42", '"a string"', "null"])
def test_top_level_non_object_is_malformed(tmp_path: Path, payload: str) -> None:
    # AC-18 — non-object roots raise.
    p = tmp_path / "x.json"
    p.write_text(payload)
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=5_000)
    assert "expected JSON object" in exc_info.value.args[0]

def test_empty_file_is_malformed(tmp_path: Path) -> None:
    # AC-19 — never silently return {}.
    p = tmp_path / "empty.json"
    p.write_text("")
    with pytest.raises(e.MalformedJSONError):
        load(p, max_bytes=5_000)

def test_only_comments_is_malformed(tmp_path: Path) -> None:
    # AC-19 follow-on — file that strips to b'' is empty JSON; must raise.
    p = tmp_path / "only_comments.json"
    p.write_text("// only a comment\n/* and a block */\n")
    with pytest.raises(e.MalformedJSONError):
        load(p, max_bytes=5_000)


# --- Depth walker — boundary + mixed shapes --------------------------------

def _nested_dicts(depth: int) -> dict:
    out: dict = {"leaf": True} if depth == 0 else {}
    cur = out
    for _ in range(depth):
        cur["x"] = {}
        cur = cur["x"]
    cur["leaf"] = True
    return out

def _mixed_nesting(depth: int) -> dict:
    leaf: object = "leaf"
    for i in range(depth):
        leaf = [leaf] if i % 2 == 0 else {"k": leaf}
    return {"root": leaf}

@pytest.mark.parametrize("inner_depth", [0, 1, 63, 64])
def test_depth_at_or_below_cap_passes(tmp_path: Path, inner_depth: int) -> None:
    # AC-21.
    p = tmp_path / "ok.json"
    p.write_text(json.dumps(_nested_dicts(inner_depth)))
    out = load(p, max_bytes=10_000_000, max_depth=64)
    assert isinstance(out, dict)

@pytest.mark.parametrize("inner_depth", [65, 70, 200])
def test_depth_above_cap_raises(tmp_path: Path, inner_depth: int) -> None:
    # AC-20 + AC-21.
    p = tmp_path / "deep.json"
    p.write_text(json.dumps(_nested_dicts(inner_depth)))
    with pytest.raises(e.DepthCapExceeded) as exc_info:
        load(p, max_bytes=10_000_000, max_depth=64)
    msg = exc_info.value.args[0]
    assert str(p) in msg
    assert "depth>64" in msg

def test_depth_walker_descends_into_lists(tmp_path: Path) -> None:
    # AC-20 — a dict-only walker would miss this.
    p = tmp_path / "list_bomb.json"
    p.write_text(json.dumps(_mixed_nesting(100)))
    with pytest.raises(e.DepthCapExceeded):
        load(p, max_bytes=10_000_000, max_depth=64)


# --- FD lifecycle ----------------------------------------------------------

def test_fd_closed_on_every_exit_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-8 — every load that opened an fd must close it exactly once.
    opened: list[int] = []
    closed: list[int] = []
    real_open = os.open
    real_close = os.close
    def _open(*args: Any, **kwargs: Any) -> int:
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd
    def _close(fd: int) -> None:
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
    # malformed JSON (after strip)
    bad = tmp_path / "bad.json"; bad.write_text("// hi\n{not json}")
    with pytest.raises(e.MalformedJSONError):
        load(bad, max_bytes=5_000)
    # malformed from strip stage (unterminated block)
    unterm = tmp_path / "unterm.json"; unterm.write_text("/* never closes")
    with pytest.raises(e.MalformedJSONError):
        load(unterm, max_bytes=5_000)
    # depth cap
    deep = tmp_path / "deep.json"; deep.write_text(json.dumps(_nested_dicts(70)))
    with pytest.raises(e.DepthCapExceeded):
        load(deep, max_bytes=10_000_000, max_depth=64)
    assert opened == closed, f"fd leak: opened={opened} closed={closed}"


# --- Cap event emission ----------------------------------------------------

def test_size_cap_emits_event_with_jsonc_parser_kind(tmp_path: Path) -> None:
    # AC-22.
    p = tmp_path / "big.json"; p.write_text("0" * 1024)
    with capture_logs() as logs:
        with pytest.raises(e.SizeCapExceeded):
            load(p, max_bytes=100)
    cap_events = [r for r in logs if r.get("event") == "probe.parser.cap_exceeded"]
    assert len(cap_events) == 1
    ev = cap_events[0]
    assert ev["cap_kind"] == "size"
    assert ev["path"] == str(p)
    assert ev["parser"] == "jsonc"
    assert ev["parser_kind"] == "jsonc"

def test_depth_cap_emits_event_with_jsonc_parser_kind(tmp_path: Path) -> None:
    # AC-23.
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
    assert ev["parser"] == "jsonc"
    assert ev["parser_kind"] == "jsonc"

def test_no_cap_event_on_happy_or_malformed_or_symlink(tmp_path: Path) -> None:
    # AC-24.
    ok = tmp_path / "ok.json"; ok.write_text(json.dumps({"a": 1}))
    with capture_logs() as logs:
        load(ok, max_bytes=5_000)
    assert not [r for r in logs if r.get("event") == "probe.parser.cap_exceeded"]

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


# --- Markers-only contract preserved (Phase-0 invariant) -------------------

def test_markers_only_positional_args0(tmp_path: Path) -> None:
    # AC-25, AC-26 — every typed exception this module raises is a marker;
    # path/cap/detail are recoverable from args[0] only.
    fixtures: list[tuple[Path, int, int, type[BaseException], str]] = []
    big = tmp_path / "big.json"; big.write_text("0" * 1024)
    fixtures.append((big, 100, 64, e.SizeCapExceeded, "cap=100"))
    bad = tmp_path / "bad.json"; bad.write_text("{not json}")
    fixtures.append((bad, 5_000, 64, e.MalformedJSONError, ""))
    deep = tmp_path / "deep.json"; deep.write_text(json.dumps(_nested_dicts(70)))
    fixtures.append((deep, 10_000_000, 64, e.DepthCapExceeded, "depth>64"))
    unterm = tmp_path / "unterm.json"; unterm.write_text('{"k": "never closed')
    fixtures.append((unterm, 5_000, 64, e.MalformedJSONError, "unterminated string"))
    for path, cap, depth, exc_type, substr in fixtures:
        with pytest.raises(exc_type) as exc_info:
            load(path, max_bytes=cap, max_depth=depth)
        assert isinstance(exc_info.value.args, tuple)
        assert len(exc_info.value.args) == 1
        assert isinstance(exc_info.value.args[0], str)
        assert str(path) in exc_info.value.args[0]
        if substr:
            assert substr in exc_info.value.args[0]
        for forbidden in ("path", "cap", "detail", "warning_id"):
            assert not hasattr(exc_info.value, forbidden), (
                f"{exc_type.__name__} must remain a marker; instance must not "
                f"carry {forbidden!r}"
            )


# --- Pathological inputs — wall-clock --------------------------------------

def test_well_balanced_5000_nested_block_comments_parses_under_1s(tmp_path: Path) -> None:
    # AC-28.
    payload = "{ " + "/* " * 5000 + '"k": 1 ' + " */" * 5000 + " }"
    p = tmp_path / "evil_balanced.json"
    p.write_text(payload)
    t0 = time.monotonic()
    out = load(p, max_bytes=1_000_000)
    elapsed = time.monotonic() - t0
    assert out["k"] == 1
    assert elapsed < 1.0, f"balanced pathological took {elapsed:.3f}s; expected < 1s"

def test_unbalanced_1mb_unterminated_block_comment_raises_under_1s(tmp_path: Path) -> None:
    # AC-29.
    payload = "/* " + ("x" * 1_000_000)
    p = tmp_path / "evil_unbalanced.json"
    p.write_text(payload)
    t0 = time.monotonic()
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=2_000_000)
    elapsed = time.monotonic() - t0
    assert "unterminated block comment" in exc_info.value.args[0]
    assert elapsed < 1.0, f"unbalanced pathological took {elapsed:.3f}s; expected < 1s"


# --- S1-01 / S1-02 / S1-03 follow-up — SymlinkRefusedError docstring -------

def test_symlink_refused_error_doc_names_jsonc() -> None:
    # AC-27.
    doc = (e.SymlinkRefusedError.__doc__ or "").lower()
    assert "jsonc" in doc or "parsers/jsonc" in doc
    # Pre-existing callers remain named so the slug test continues to pass.
    assert "writer" in doc or "sanitizer" in doc
    assert "safe_json" in doc  # S1-02 already added this; do not regress.
```

Run; confirm `ModuleNotFoundError` / `AttributeError`. Commit as **red**.

### Green — minimal impl

Follow the implementation outline above. Land enough code to make every test pass with no excess (Rule 2 / Rule 3):

1. `_strip_comments(data: bytes) -> bytes` (pure, no path) — the four-state machine; use a `bytearray` for the output. Single pass. On unterminated string/block, raise a parser-local exception (or `MalformedJSONError` directly if you pass `path` as a kwarg per AC-26). Either shape is acceptable; pick one.
2. `_assert_depth(obj, *, max_depth, current, path)` — copy `safe_json`'s shape (or import from `parsers._depth` if S1-03 lifted it).
3. `_emit_cap_event(cap_kind, path)` — single private helper, emits with `parser="jsonc"`, `parser_kind="jsonc"`.
4. `load(path, *, max_bytes, max_depth=64)` — sequence: open → fstat → cap → read → close (in finally) → strip → empty-check → `json.loads` → top-level-isinstance-dict → depth walk → return.
5. Edit `src/codegenie/errors.py::SymlinkRefusedError.__doc__` per AC-27. One-line append.

Commit as **green**.

### Refactor — clean up

- Module docstring carries arch + ADR references (AC-3).
- `__all__` narrows the public surface to `["load"]` (and the re-exported `JSONValue` if you choose to expose it at the module level).
- `JSONValue` recursive alias defined once in `parsers/__init__.py` (S1-02 already did this); imported here.
- `load` docstring enumerates every raised exception (callers grep this when picking a `WarningId` per ADR-0007).
- The state-machine table is dense; one-line comments per transition keep it readable for the reviewer.
- No catch of `BaseException` anywhere. Only `OSError` (for `O_NOFOLLOW`) and `json.JSONDecodeError`.
- Single-pass O(n) is structurally enforced — no inner loop scans back, no regex, no `str.replace` over the full buffer.
- Final `assert len(stripped) <= len(data)` invariant is a structural belt-and-suspenders (AC-11).

Commit as **refactor**. Reviewers can check `git log` for the three commits.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/parsers/jsonc.py` | New module — comment stripper + `load` |
| `src/codegenie/errors.py` | One-line docstring extension on `SymlinkRefusedError` (AC-27 / S1-01 follow-up) |
| `tests/unit/parsers/test_jsonc.py` | New — line/block/nested comments, strings with `//` / `/*` / `*/`, backslash escapes, double-quote-in-block-comment, unterminated paths with wall-clock budget, depth boundary, mixed dict/list nesting, fd lifecycle, event-field assertions, markers-only parametrized, no-regex AST scan, pathological well-balanced and unbalanced |

## Out of scope

- **`tsconfig.json` `extends` chain following** — `NodeBuildSystemProbe`'s job (S2-02). This story only parses the bytes of one `tsconfig.json`.
- **Local fuzzing** — the implementer should fuzz locally per `phase-arch-design.md §Step 1 risks` ("fuzz it locally with an atheris-style hostile input set before opening the Step 1 PR"). Atheris is not a project dependency; use stdlib `random` + timeout loop for local fuzzing. Acceptance criteria do not include a checked-in fuzz harness.
- **Adversarial fixture (`test_tsconfig_pathological.py`)** — S5-03; integration-layer adversarial coverage. This story carries unit-test coverage of the same code paths via inline pathological fixtures with wall-clock budgets (AC-28, AC-29).
- **JSON5 features** — trailing commas, single-quoted strings, unquoted keys, hex numbers, `+`/`-Infinity`/`NaN`. JSONC is a strict subset: comments only. Per Rule 2 (Simplicity First), the smallest stripper that handles `tsconfig.json` is the goal.
- **`probe.parser.cap_exceeded` event-name constant in `codegenie/logging.py`** — S1-10 registers it as a module-level `Final[str]`. This story emits the event literal-string; S1-10 lifts it into the constant.
- **Carrying machine-readable `path` / `cap` / `detail` attributes on exception instances** — explicitly forbidden by the Phase-0 markers-only invariant. The catch site reconstructs the `WarningId` from probe context per ADR-0007.
- **Registry / factory / `Parser` ABC** — YAGNI in Phase 1 (Rule 2). Three concrete parsers (`safe_json`, `safe_yaml`, `jsonc`) plus three lockfile siblings (`_pnpm`, `_npm`, `_yarn`) is below the premature-abstraction threshold. The `parser_kind` discriminator on the structlog event is the de-facto strategy registry; downstream observers (Phase 13 cost ledger, Phase 6 state ledger) attribute events without a central registration list. Revisit only if Phase 7+ adds a fourth distinct parser-family.

## Notes for the implementer

- **Markers-only construction.** Every typed exception this story raises is a Phase-0 marker. Construct with **one positional string** (the formatted message). No kwargs. No instance attributes. The catch site (a probe) parses `args[0]` if it needs to; the probe also constructs the `WarningId` per ADR-0007 (e.g., `tsconfig.size_cap_exceeded`).
- **Plugin / strategy framing.** `jsonc.py` is the third concrete parser strategy after `safe_json` (S1-02) and `safe_yaml` (S1-03). The kernel is `parsers/_io.py` + `parsers/_depth.py` (if S1-03 lifted them) or the inline shape mirrored from `safe_json` (if not). The parser-specific shape is the comment stripper. The `parser_kind="jsonc"` literal supplied to `_emit_cap_event` is the strategy's discriminator. **Open/Closed is satisfied by "new file + new `parser_kind` literal."** No `ParserRegistry`, no factory, no `Parser` ABC — three concrete parsers is below the premature-abstraction threshold (Rule 2).
- **Newline preservation when stripping line comments.** Output a `\n` when transitioning out of `_S_LINE_COMMENT` so JSON parser line numbers in error messages remain useful. Block comments are stripped to nothing (simpler; `tsconfig.json` errors are rarely line-number-debugged in Phase 1).
- **No regex.** Forbidden — Rule 7 (surface conflicts; don't average them) + ADR-0008 (regex DoS on hostile input is the very risk the in-process caps mitigate). Even for "find the next `*/`" — the linear scan is safer. Asserted by `test_module_does_not_import_re`.
- **Backslash escape state.** The `escaped: bool` flag is the only state needed for string-content correctness. Logic: in `_S_STRING`, when `escaped == True`, emit the byte and clear `escaped`; when `escaped == False` and the byte is `\\`, emit the byte and set `escaped = True`. This means `"\\\\"` (two backslashes) is two transitions: first `\\` sets `escaped`, second `\\` clears it (the second `\\` was the escaped value). Pinned by AC-14 parametrized table.
- **Block comment containing `"`.** In `_S_BLOCK_COMMENT`, the `"` byte is INERT — do NOT transition to `_S_STRING`. AC-15 catches a common state-machine bug.
- **Unterminated-input wall-clock budget.** `time.monotonic()`-based assertion is the test mechanism (independent of whether `pytest-timeout` plugin is installed). Implementation guarantee: single-pass O(n) — every byte advances `i` by at most a constant; no recovery loop scans back.
- **One-shot `os.read(fd, size)` is correct** because `size` is bounded by `max_bytes`; don't loop. But **always verify `len(data) == size`** — a short read is `MalformedJSONError(f"{path}: short read")`, never silent retry.
- **`O_NOFOLLOW` semantics differ** on macOS vs Linux. Both raise `ELOOP` when the **final** path component is a symlink. macOS still follows symlinks in **intermediate** components. Phase 1's threat model only cares about the final component; document this in the module docstring.
- **Only `errno == ELOOP` translates to `SymlinkRefusedError`.** `IsADirectoryError` (EISDIR), `PermissionError` (EACCES), `FileNotFoundError` (ENOENT), and any other `OSError` propagate unchanged. The test asserts `not isinstance(exc, SymlinkRefusedError)` for the `ENOENT` and `EISDIR` paths.
- **`MalformedJSONError` detail truncation.** Use `str(exc)[:200]` (the JSONDecodeError message). **Never** include `exc.doc` (the source bytes) — that's exactly the kind of secret-leak channel ADR-0008's sanitizer prevents from reaching disk, and the structlog event would carry it to logs.
- **Empty file vs all-comments file.** `b''` and (e.g.) `b'// only a line comment\n'` both strip to `b''` (or nearly so). Both must raise `MalformedJSONError` — the test pins both shapes. Do not silently return `{}`.
- **Top-level shape.** Phase 1's consumers all read top-level JSON objects (`tsconfig.json`, `package.json`, etc.). A top-level list/scalar/null is rejected. If a future probe needs JSONC whose root is not an object, add a sibling `load_any` function then — don't widen `load`'s return type.
- **The post-parse depth walker is load-bearing.** Until Python's stdlib `json` gains a `max_depth` parameter, this walker is the only defense against JSON bombs that parse but consume O(depth) RSS during downstream traversal. Walk **both** dicts and lists.
- **Don't catch `BaseException`.** Only `OSError` (for `O_NOFOLLOW`) and `json.JSONDecodeError`. Anything else is a bug we want to see (Rule 12).
- **Structlog testing.** Use `structlog.testing.capture_logs()` rather than reading stderr — robust across renderer/init order changes.
- **The shared depth walker** (if S1-03 extracted it to `parsers/_depth.py`) accepts a `path: Path` for the exception. Pass `path` here too. If S1-03 has not landed, mirror the inline `safe_json._assert_depth` shape; do not lift opportunistically in this story (Rule 3 — surgical changes).
- **JSON5 is not the goal.** JSONC is a strict subset: just comments. Don't add support for trailing commas, single-quoted strings, unquoted keys, or hex numbers. Per Rule 2, the smallest stripper that handles `tsconfig.json` is the goal.
- **`\"` and `\\` inside strings are the load-bearing escapes** for state-machine correctness. Backslash handling MUST cover `"\\\\"` (escaped backslash) — a string `"x\\\\y"` parses to Python `r"x\\y"` (two real backslashes). The parametrized AC-14 table is the source of truth.
- **The structlog event uses the literal `"probe.parser.cap_exceeded"`.** S1-10 introduces a module-level constant; this story is allowed to use the literal pending that.
