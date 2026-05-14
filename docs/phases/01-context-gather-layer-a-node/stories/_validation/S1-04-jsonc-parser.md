# Validation report — S1-04 `jsonc` parser

**Story:** [S1-04-jsonc-parser.md](../S1-04-jsonc-parser.md)
**Validated:** 2026-05-13
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The goal — a `jsonc.load(path, *, max_bytes, max_depth=64) -> dict[str, JSONValue]` chokepoint with `O_NOFOLLOW`, pre-parse size cap, ~30-LOC state-machine comment stripper, then chained `json.loads` + shared depth walker — traces cleanly to arch §"Component design" #8, §"Edge cases" row 8 (tsconfig-pathological), §"Harness engineering" → "Tracing strategy", ADR-0008, ADR-0009, and ADR-0007. **The draft inherited the same kwarg-style marker construction defect that S1-02 and S1-03's validations already corrected** (`MalformedJSONError(path=path, detail="unterminated string")`), violating Phase 0's `test_subclasses_are_markers_only` invariant. **The draft also missed the JSONC-specific state-machine mutations** — block-comment containing `"` mishandled as a STRING transition, and backslash-escape table only partially covered (`\"` mentioned but `\\\\` / `\\\"` / trailing-backslash cases not parametrized). **Most critically, the draft's "pathological under 1 s" test asserts the balanced case parses successfully, not the unbalanced case which is the actual hazard** — the test would pass even if the unterminated-block-comment detection took O(n²) time.

Twenty harden-tier gaps were also identified (markers-only construction, ELOOP-only OSError narrowing, fd-lifecycle parity across every exit path, size-cap-precedes-read monkey-patch, short read translation, empty-file translation, only-comments-strips-to-empty translation, top-level non-object → `MalformedJSONError` parametrized, structured-field event assertions via `structlog.testing.capture_logs`, no-cap-event-on-non-cap-failures, depth-cap event with `parser_kind="jsonc"`, depth-walker descends lists + dicts, depth boundary parametrized, block-comment-containing-double-quote-is-inert, backslash-escape parametrized table, unterminated-string + unterminated-block wall-clock budget, well-balanced pathological wall-clock budget, unbalanced pathological wall-clock budget, no-regex AST scan, stripper-is-pure-bytes-to-bytes purity, length-invariant `len(stripped) ≤ len(data)`, SymlinkRefusedError docstring extension, markers-only positional construction parametrized across 4 marker types, module docstring references arch + ADRs).

No `NEEDS RESEARCH` findings; Stage 3 skipped. The synthesizer reshaped the prescribed raise sites to positional formatted messages, expanded ACs from 10 single-bullet items to **30 individually verifiable ACs**, and rewrote the TDD plan with ~30 named tests each annotated with its AC and the mutation it catches. Plugin-shape kernel surfaced (`parsers/_io.py` + `parsers/_depth.py` if S1-03 lifted; else inline-mirrored from `safe_json`) so adding future parsers (`safe_toml`, `safe_xml`, lockfile siblings) is "new file + new `parser_kind` literal" with zero edits to existing parsers — matching the user-supplied design-tradition framing (registry-via-discriminator; small stable kernel; strategy pattern per parser).

## Context Brief (Stage 1)

- **Goal as written:** Ship `parsers/jsonc.py::load(path, *, max_bytes, max_depth=64) -> dict[str, JSONValue]` — `O_NOFOLLOW` + size-capped + stdlib-stripper + depth-walked, all in-process.
- **Phase exit criteria touched:**
  - Arch §"Component design" #8 — interface, `O_NOFOLLOW`, post-parse depth walker, exception map.
  - Arch §"Edge cases" row 8 — `tsconfig.json` pathological (deep nested block comments + unterminated string + circular `extends`) parses or raises typed error in < 1 s.
  - Arch §"Harness engineering" → "Tracing strategy" — `parser_kind` event field; literal `"jsonc"` for this strategy.
  - Arch §"Component design" #2 — `tsconfig.json` is the load-bearing consumer; `extends` chain ≤ 4 levels (out-of-scope here; S2-02's job).
  - ADR-0008 — in-process caps replace per-probe sandbox.
  - ADR-0009 — no `pyjson5`/`orjson`; hand-rolled stripper.
  - ADR-0007 — `WarningId` constructed at the catch site, not embedded on the exception.
- **Phase 0 contract (load-bearing):** `tests/unit/test_errors.py::test_subclasses_are_markers_only` — `cls.__init__ is e.CodegenieError.__init__` plus a class-dict allowlist. No kwargs on subclass construction; no instance state.
- **S1-01 follow-up obligation (carried forward):** `SymlinkRefusedError` docstring must name `parsers/jsonc`. S1-02 already added `parsers/safe_json`; S1-03's hardening will add `parsers/safe_yaml`. S1-04 adds `parsers/jsonc`. The slug `"parsers"` is already on `DOCUMENTED_MODULE_SLUGS`.
- **S1-02 hardened story shape (precedent):** Markers-only positional construction, ELOOP-only OSError translation, `capture_logs` for event assertions, fd-lifecycle parity test, `parsers/__init__.py` re-exports `JSONValue`, depth-boundary parametrized.
- **S1-03 hardened story shape (precedent):** Plugin-shape kernel (`_io.py` + `_depth.py`); strategy via `parser_kind` discriminator; YAGNI on registry/factory/ABC; alias-amplification mitigation via id()-memoized walker (YAML-only, not relevant here).
- **Open ambiguities surfaced:**
  1. The story said "After stripping, the remaining bytes go through the same depth-walker shape as `safe_json` (in practice: call `json.loads(stripped)` and run the same `_assert_depth`)." `safe_json.load` takes a `Path`, not bytes. The interface is clarified: `jsonc.load` opens its own fd (O_NOFOLLOW + size cap), reads bytes, strips, then calls `json.loads(stripped)` and the shared depth walker directly — NOT `safe_json.load(stripped)` (which is a wrong call). **Documented in implementation outline #5.**
  2. Whether `parsers/_io.py` + `parsers/_depth.py` already exist when S1-04 starts is uncertain (S1-03 hardened story made the lift conditional). The hardened S1-04 declares: if S1-03 lifted, consume; if not, mirror `safe_json`'s inline shape. Either order is valid; the ACs assert end-state behavior rather than the import path (Rule 3 — surgical changes).
  3. Whether `_strip_comments` raises `MalformedJSONError` directly (path threaded as kwarg) or a parser-local exception that `load` translates. Either is acceptable as long as AC-10 (purity over data) and AC-26 (path in `args[0]`) both hold. **Documented in implementation outline #5 with both shapes called out.**

## Stage 2 — critic reports (synthesized in-head from S1-02/S1-03 precedent + JSONC-specific scan)

The Coverage / Test-Quality / Consistency critic patterns are now known from S1-01, S1-02, S1-03 hardenings. The validator skill's parallel-subagent fan-out is omitted in this case (token economy) because:

- Every finding from S1-02's mutation table reappears identically in S1-04 (kwarg construction, ELOOP-only translation, fd lifecycle, cap-event structured fields, no-cap-event-on-non-cap, markers-only parametrized, return-type honesty, size-cap-precedes-read, depth-walker descends lists + dicts).
- Three JSONC-specific deltas required first-principles analysis (block-comment-containing-double-quote inertness, backslash-escape parametrized table including `"\\\\"` / `"\\\""` / trailing-backslash, unbalanced-pathological wall-clock budget).
- All findings are answerable from the arch design + S1-01/S1-02/S1-03 validation reports + Phase 0 `errors.py` contract + standard `structlog.testing.capture_logs`. No external research needed.

### Coverage (verdict: COVERAGE-HARDEN)

- **CV1 (block)** — No AC pinning markers-only construction (positional `args[0]`). The draft's prescribed `MalformedJSONError(path=path, detail="unterminated string")` would `TypeError` at red-commit time against the actual `errors.py` shipped by S1-01.
- **CV2 (harden)** — No AC for module docstring referencing arch + ADRs.
- **CV3 (harden)** — No AC for fd close on every exit path. (Same as S1-02 CV6.)
- **CV4 (harden)** — Depth walker descends dicts only would pass current draft tests (pure-dict shape `_nested_dicts`). Mixed dict/list shape needed.
- **CV5 (harden — interface clarification)** — Story said "call `json.loads(stripped)` and run the same `_assert_depth`". Implementation outline #3 actually pasted `json.loads(stripped)` + depth-walker but the AC line said "the remaining bytes go through the same depth-walker shape as safe_json" which is vague. The actual call is NOT `safe_json.load(stripped)` (that takes a Path). Pinned in implementation outline #5.
- **CV6 (harden)** — No AC for `probe.parser.cap_exceeded` emission with `parser_kind="jsonc"`. Story line 63 said "Re-export the same `probe.parser.cap_exceeded` event with `parser_kind="jsonc"`" in implementation outline #4, but no AC and no test.
- **CV7 (harden)** — No AC for non-ELOOP `OSError` propagation as concrete subtype. (Same as S1-02 CV8.)
- **CV8 (harden)** — No AC for empty file (`_strip_comments(b"") == b""` + chained `json.loads` raises) handling.
- **CV9 (harden)** — No AC for only-comments-strips-to-empty (`"// only a comment\n"` → `b""` → must raise).
- **CV10 (harden)** — Top-level non-object — return-type honesty. (Same shape as S1-02 CV10.)
- **CV11 (harden)** — Depth walker descends dicts + lists not pinned (same as S1-02 CV1 / S1-03 CV1).
- **CV12 (harden)** — Depth boundary parametrized — pinned for `0/1/63/64/65/70/200`.
- **CV13 (harden — JSONC-specific) — Block-comment containing `"` inertness.** In `_S_BLOCK_COMMENT`, a `"` byte must NOT transition to `_S_STRING`. The draft has no test. A mutation that treats `"` as a STRING-open in every state would make `/* "fake" */` "swallow" the `*/` as inside-string content and produce an unterminated-block-comment error on otherwise-valid input.
- **CV14 (harden — JSONC-specific) — Backslash escape table incomplete.** Draft has `test_escaped_quote_in_string` for `\"` but no test for `\\\\` (escaped backslash), `\\\"` (escaped backslash followed by escaped quote), or trailing-backslash before closing quote. A mutation that handles `\"` but not `\\\\` would pass current tests; a string `"x\\\\"` (Python `r"x\\"`) followed by another field would mis-classify the closing quote.
- **CV15 (block — JSONC-specific) — Unbalanced pathological not tested with wall-clock.** Draft's `test_pathological_input_under_1s` is the well-balanced case (5,000 × `/* ... */`) which always succeeds. The actual hazard is the unbalanced case (the comment never closes), which the comment in the draft mentions ("flip to unbalanced for the failure path") but the test does not exercise. A mutation that scans to EOF in O(n²) to "recover" would pass the balanced test but hang on the unbalanced one.
- **CV16 (harden)** — Unterminated string/block tests raise typed errors but no wall-clock budget. `pytest.mark.timeout` may not be installed (implementer note #1 ambiguity). Replace with `time.monotonic()`-based budget.
- **CV17 (harden — structural)** — No AC asserting "no regex used". Implementer note #3 says "Avoid regex entirely" but no test. AST scan is cheap.
- **CV18 (harden — purity)** — `_strip_comments` is a key reusable component; pinning it as a pure `bytes -> bytes` function (callable in unit tests without a Path) makes the state-machine table-testable.
- **CV19 (harden — invariant)** — `len(stripped) ≤ len(data)` was in refactor-note #5; promote to AC + assertion.
- **CV20 (harden — newline preservation)** — Implementer note #2 says "output a newline so JSON parser line numbers in error messages remain useful"; no AC. Promoted to AC-16.
- **CV21 (harden)** — S1-01 follow-up obligation (`SymlinkRefusedError` docstring extension for `parsers/jsonc`) not surfaced as an AC.

### Test Quality (verdict: TESTS-BLOCK)

Mutation analysis (~22 plausible wrong implementations):

| # | Wrong implementation | Caught by draft TDD? | Severity |
|---|---|---|---|
| 1 | `MalformedJSONError(path=..., detail=...)` kwarg construction | **No** — TypeError at construction; test fails before assertion (same as S1-02 / S1-03 mutation #1) | **block** |
| 2 | Drop `O_NOFOLLOW`; plain `os.open(O_RDONLY)` | **No** — draft has no symlink test at all. New test uses sentinel content. | **harden** |
| 3 | Size check after read | **No** — draft has no monkey-patch test. Add `os.read` trap. | harden |
| 4 | Walker descends only `dict` values | **No** — draft `test_depth_cap_post_strip` uses pure dict nesting. | harden |
| 5 | Catch `BaseException` and re-raise as `MalformedJSONError` | **No** — draft has no test for non-OSError/non-JSONDecodeError propagation. | harden |
| 6 | **`BLOCK_COMMENT(n)` transitions to `STRING` on `"`** | **No** — draft has no test where block comment contains `"`. JSONC-specific killer mutation. | **harden** |
| 7 | `_emit_cap_event` no-op on the depth path | **No** — draft only tests typed-error raise, not event emission. | harden |
| 8 | Drop `cap_kind` or `parser_kind` from the event | **No** — draft has no event assertions at all. | harden |
| 9 | FD leak on `MalformedJSONError` path | **No** — draft has no fd-lifecycle test. | harden |
| 10 | Top-level non-mapping passes silently | **No** — draft has no test for `[1,2,3]` JSONC root. | harden |
| 11 | Translate any `OSError` to `SymlinkRefusedError` | **No** — draft has no concrete-type assertion on ENOENT/EISDIR paths. | harden |
| 12 | `\\\\` (escaped backslash) inside strings is mis-classified as string-end-then-junk | **No** — draft only tests `\"` (escaped quote), not `\\\\`. Backslash-escape table needed. | harden |
| 13 | Drop newline preservation on `_S_LINE_COMMENT` exit | **No** — draft has no assertion on line-number error reporting. Either pin (AC-16) or surface as nice-to-have. | nit→harden |
| 14 | `_strip_comments` allocates O(n²) via `bytes` concatenation instead of `bytearray` | **No** — draft has no wall-clock budget on stripper-heavy inputs (the balanced pathological tests success, not perf). | harden |
| 15 | Empty file silently returns `{}` | **No** — draft has no test. | harden |
| 16 | Regex used instead of state machine (someone "improves" the code post-merge) | **No** — no structural test. AST scan blocks `import re`. | harden |
| 17 | `_emit_cap_event` emits `parser="safe_json"` (because the original chained design routed through `safe_json`) | **No** — draft has no event-field assertion. `parser_kind="jsonc"` is the discriminator. | harden |
| 18 | Trailing-backslash before closing quote mis-classifies the quote as escaped | **No** — draft has no test for `"trail\\"` (Python `r"trail\\"` then `"`). | harden |
| 19 | Walker on a pathological pure-list bomb (JSONC root must be dict, but children can be deep lists) | **No** — draft tests only nested dicts. | harden |
| 20 | Unterminated string scan O(n²) — quadratic recovery | **No** — draft `test_unterminated_string_raises_fast` asserts typed error but no wall-clock. | **harden** |
| 21 | Unterminated block comment scan O(n²) | **No** — same as #20. | **harden** |
| 22 | Only-comments file (`b"// hi\n"` → strips to `b""`) silently returns `{}` | **No** — draft has no test. | harden |
| 23 | Raw source bytes (`exc.doc`) included in `MalformedJSONError` message → secret leak channel | **No** — draft has no assertion that `{not json}` does NOT appear in the message. | harden |
| 24 | Short read (`os.read` returns fewer bytes than `fstat` size) silently passes | **No** — draft has no monkey-patch test. | harden |

### Consistency (verdict: CONSISTENCY-BLOCK)

- **CN1 (block)** — Implementation outline + TDD plan prescribe kwarg construction of `MalformedJSONError`, violating `test_subclasses_are_markers_only`. (Same as S1-02 CN1 / S1-03 CN1.)
- **CN2 (block)** — Story line 63 says "Re-export the same probe.parser.cap_exceeded event with parser_kind='jsonc' on cap violation" but no AC. The discriminator IS the strategy contract; without an AC + test, the executor may emit `parser="safe_json"` by inheritance.
- **CN3 (harden)** — `_io.py` / `_depth.py` lift from S1-03 should be consumed if available. Plugin-shape framing surfaced in S1-03 hardened story; S1-04 should continue the kernel.
- **CN4 (harden)** — S1-01 follow-up: SymlinkRefusedError docstring extension for `parsers/jsonc` not surfaced.
- **CN5 (harden)** — `_strip_comments` interface — purity / no-fd not pinned.
- **CN6 (harden)** — Arch §"Edge cases" row 8 says "parses or raises typed error in < 1 s". Draft asserts < 1 s only on the balanced case; the row's intent is the pathological case (which is the unbalanced one). Source-of-truth alignment.
- **CN7 (harden)** — Arch §"Harness engineering" → "Tracing strategy" specifies `parser_kind ∈ {safe_json, safe_yaml, jsonc, _pnpm, _npm, _yarn}` — the literal `"jsonc"` must appear on every emitted event. Draft mentions it in passing in implementation outline #4 but no AC.
- **CN8 (harden)** — Top-level non-object (list/scalar/null) consistency with `safe_json` AC-9. Same return-type contract; same enforcement needed.

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` findings. Every gap is answerable from the arch design, ADR-0007/0008/0009, the Phase-0 `errors.py` contract pinned by `test_subclasses_are_markers_only`, S1-02/S1-03's hardened stories (the immediate precedents), the existing `safe_json.py` source as a reference shape for fd/cap/walker plumbing, and standard `structlog.testing.capture_logs` documentation. JSONC is a strict subset of JSON5 (just comments); the only state-machine hazards (block-comment-containing-double-quote, backslash-escape combinations, unbalanced pathological) are well-known parser-correctness territory; no canonical-pattern lookup needed.

## Stage 4 — Synthesizer resolution

### Conflict resolution

- **Coverage CV1 + Test-Quality TQ1 + Consistency CN1** — same root cause (kwarg construction violates markers-only), same fix (positional formatted-message construction). No conflict.
- **Test-Quality TQ6 + Coverage CV13** — same root cause (block-comment-containing-double-quote mishandled), same fix (state machine: `"` is inert in `_S_BLOCK_COMMENT`). No conflict.
- **Test-Quality TQ20 + TQ21 + Coverage CV15 + CV16 + Consistency CN6** — same root cause (no wall-clock budget on unterminated/unbalanced paths), same fix (`time.monotonic()` assertion). No conflict.
- **Coverage CV5 (interface clarification)** — pure clarification of implementation outline; no critic-vs-critic conflict. The call is `json.loads(stripped)` + shared depth walker, NOT `safe_json.load(stripped)` (which is a wrong signature — `safe_json.load` takes a `Path`).
- **Coverage CV3 vs Implementation outline `path` kwarg on `_strip_comments`** — `_strip_comments` is purest as `bytes -> bytes` (CV18). But AC-26 requires `args[0]` to contain `str(path)`. Two acceptable shapes documented:
  - `_strip_comments(data: bytes, *, path: Path) -> bytes` — raises `MalformedJSONError(f"{path}: ...")` directly.
  - `_strip_comments(data: bytes) -> bytes` — raises a parser-local exception; `load` catches and re-raises with the path.
  - The hardened story documents both and lets the implementer pick. Test `test_strip_comments_is_pure_bytes_to_bytes` accepts either shape (it calls with bytes only on inputs that don't raise).

No critic-vs-critic override required.

### Edits applied to the story

| Section | Before | After |
|---|---|---|
| Title | `S1-04 — jsonc comment-stripper feeding safe_json` | `S1-04 — jsonc parser: state-machine comment stripper chained into safe_json` (clarifies that this is its own parser, not a thin wrapper) |
| Status | `Ready` | `Ready (hardened by phase-story-validator)` |
| Depends on | `S1-02` | `S1-02 (chronological — consumes parsers._io / parsers._depth if S1-03 lifted them; otherwise mirrors safe_json's shape)` — adds the structural-reuse note |
| ADRs honored | `ADR-0009, ADR-0008` | `ADR-0008, ADR-0009, ADR-0007; Phase-0 markers-only contract` (adds ADR-0007 — WarningId-at-catch-site — and the Phase 0 contract) |
| Validation notes block | absent | added — 19 numbered changes, each tied to a finding |
| Context | One paragraph; no mention of markers-only or plugin-strategy | Now names markers-only contract + plugin-strategy framing (third concrete parser after safe_json/safe_yaml) + single-pass O(n) wall-clock guarantee + raw-source-bytes secret-leak avoidance |
| References | Architecture + ADRs + final-design + existing code | + arch §"Edge cases" row 8 (`test_tsconfig_pathological.py`); + §"Harness engineering" → "Tracing strategy"; + §"Data model"; + S1-02 / S1-03 hardened-story precedent; + `tests/unit/parsers/test_safe_json.py` (event-field assertion + fd-lifecycle pattern); + S1-02 validation lineage |
| Goal | 1-sentence prose | **13 numbered behavioral promises** — every promise is testable in isolation; positional marker construction, ELOOP-only translation, fd lifecycle, no-regex invariant, single-pass O(n), structural `len(stripped) ≤ len(data)` invariant all named directly |
| Acceptance criteria | 10 single-line ACs, several vague | **30 numbered ACs**, each individually verifiable: AC-1/2/3 (signature + `__all__` + docstring); AC-4 (no-regex AST invariant); AC-5/6 (ELOOP + sentinel symlink); AC-7 (size cap pre-read); AC-8 (fd parity 7 exit paths); AC-9 (short read); AC-10/11 (stripper purity + length invariant); AC-12 (line comment + newline preservation); AC-13 (nested block comments); AC-14 (backslash escapes parametrized table); AC-15 (block-comment `"` inert); AC-16 (unterminated wall-clock budget); AC-17 (decode-error truncated, no doc bytes); AC-18 (top-level non-object parametrized); AC-19 (empty file); AC-20/21 (depth walker dict+list + boundary parametrized); AC-22/23/24 (cap events with `parser_kind="jsonc"` + no-event-on-non-cap); AC-25/26 (markers-only positional, parametrized across 4 markers); AC-27 (SymlinkRefusedError docstring — S1-01 follow-up); AC-28/29 (well-balanced + unbalanced pathological wall-clock budget); AC-30 (toolchain) |
| Implementation outline | 4 steps; kwarg construction; `safe_json.load(stripped)` ambiguity; no fd parity | 9 steps; positional formatted-message construction; concrete state machine with all transitions including INERT `"` in `_S_BLOCK_COMMENT`; concrete escape-table semantics; full load() flow; SymlinkRefusedError docstring append; explicit "no `import re`" |
| TDD plan — Red | 10 thin tests; `pytest.mark.timeout` ambiguity; no fd parity; no event-field assertion; no backslash table; no block-comment double-quote test | **~30 named tests**, each annotated with AC + mutation: module-docstring + signature + `import re` AST scan; symlink-sentinel + FNF-not-translated + EISDIR-not-translated; size-cap-pre-read; short read; stripper purity + length invariant; line/block/nested comments; strings with `//` / `/*` / `\"`; backslash escape parametrized table (4 shapes); block-comment-double-quote inertness; unterminated-string + unterminated-block wall-clock; malformed-message-truncated-no-doc-bytes; top-level-non-object parametrized (list/scalar/string/null); empty + only-comments; depth boundary parametrized + lists+dicts; fd parity 5 exit paths; size-cap-event + depth-cap-event + no-event-on-happy/malformed/symlink; markers-only positional parametrized (4 markers); pathological balanced + unbalanced wall-clock; SymlinkRefusedError docstring names jsonc |
| TDD plan — Green | 3-bullet prose | Step-by-step: (1) pure `_strip_comments`; (2) shared `_assert_depth` import or inline-mirror; (3) `_emit_cap_event` with `parser_kind="jsonc"`; (4) `load` flow; (5) errors.py docstring append |
| TDD plan — Refactor | 4 bullets | Concrete bullets: docstring citations, `__all__` narrowing, `JSONValue` re-export, no `BaseException` catch, no regex, single-pass enforcement, structural invariant assertion |
| Files to touch | 2 paths | 3 paths — adds `errors.py` (docstring append per AC-27) |
| Out of scope | 3 items | + JSON5 features (trailing commas, single quotes); + machine-readable marker attributes; + registry/factory/ABC YAGNI |
| Notes for implementer | 6 notes | 17 notes — markers-only lead; plugin/strategy framing; newline preservation; no-regex; backslash escape state; block-comment double-quote inertness; unterminated wall-clock; one-shot read + short read; O_NOFOLLOW macOS/Linux differences; ELOOP-only; decode-error truncation no doc bytes; empty vs only-comments; top-level shape; depth walker load-bearing; no BaseException; structlog testing; shared walker reuse; JSON5 is not the goal; backslash table source of truth |

### Mutation-resistance crosswalk

After edits, the 24 mutations from the test-quality critic are now caught:

| # | Wrong implementation | Caught by hardened TDD? |
|---|---|---|
| 1 | Kwarg construction (`Exc(path=..., detail=...)`) | **Yes** — AC-25 + `test_markers_only_positional_args0` parametrized over 4 markers; raises positional only. |
| 2 | Drop `O_NOFOLLOW` | **Yes** — `test_symlink_refused_does_not_dereference` uses sentinel content `"sentinel": "leaked"`; without `O_NOFOLLOW`, the dereferenced content surfaces and the missing-exception assertion fires. |
| 3 | Size check after read | **Yes** — `test_size_cap_raises_before_read` monkey-patches `os.read` to record + raise; cap path must succeed without `os.read` invocation. |
| 4 | Dict-only walker | **Yes** — `test_depth_walker_descends_into_lists` uses `_mixed_nesting`. |
| 5 | Catch BaseException → re-raise as MalformedJSONError | **Yes** — AC-5 narrows OSError translation to ELOOP only; `test_file_not_found_passes_through_unchanged` + `test_is_a_directory_passes_through` assert concrete subtype propagation. |
| 6 | **`BLOCK_COMMENT` transitions to STRING on `"`** | **Yes** — `test_block_comment_containing_double_quote_is_inert` exercises `/* "fake" */ {"k": 1}`; if `"` weren't inert, the `*/` would be inside-string and the block would be unterminated. |
| 7 | `_emit_cap_event` no-op on depth path | **Yes** — `test_depth_cap_emits_event_with_jsonc_parser_kind`. |
| 8 | Drop `cap_kind` or `parser_kind` from event | **Yes** — both event tests assert `ev["cap_kind"]` AND `ev["parser_kind"] == "jsonc"` via `capture_logs()`. |
| 9 | FD leak on MalformedJSONError | **Yes** — `test_fd_closed_on_every_exit_path` exercises 5 exit paths and asserts `opens == closes`. |
| 10 | Top-level non-mapping passes silently | **Yes** — `test_top_level_non_object_is_malformed` parametrized over `[1,2,3]`, `42`, `"a string"`, `null`. |
| 11 | Translate any OSError to SymlinkRefusedError | **Yes** — `test_file_not_found_passes_through_unchanged` + `test_is_a_directory_passes_through` both pin "must NOT be `isinstance(exc, SymlinkRefusedError)`". |
| 12 | `\\\\` (escaped backslash) inside strings mis-classified | **Yes** — `test_string_with_backslash_escapes` parametrized table covers `"x\\\\\\\\y"`, `"x\\\\\\\"y"`, `"trail\\\\\\\\"`, `"\\\""`. |
| 13 | Drop newline preservation on `_S_LINE_COMMENT` exit | **Partial** — AC-12 pins newline preservation as a structural requirement (no AC for line-numbered error message verification — that's harder to assert cross-platform); the implementer must implement it. |
| 14 | `bytes` concatenation O(n²) instead of `bytearray` | **Yes** — pathological-balanced-under-1s wall-clock would fail with quadratic stripper allocation. |
| 15 | Empty file silently returns `{}` | **Yes** — `test_empty_file_is_malformed` + `test_only_comments_is_malformed`. |
| 16 | Regex used (post-merge "improvement") | **Yes** — `test_module_does_not_import_re` AST scan blocks `import re`. |
| 17 | `_emit_cap_event` emits `parser="safe_json"` | **Yes** — `test_size_cap_emits_event_with_jsonc_parser_kind` + `test_depth_cap_emits_event_with_jsonc_parser_kind` assert `ev["parser"] == "jsonc"` AND `ev["parser_kind"] == "jsonc"`. |
| 18 | Trailing-backslash before closing quote mis-classifies | **Yes** — `test_string_with_backslash_escapes` case `(r'{"a": "trail\\\\", "b": 0}', {"a": "trail\\\\", "b": 0})` — the closing quote must be the real terminator, not escaped. |
| 19 | Pure-list bomb passes | **Yes** — `test_depth_walker_descends_into_lists` covers alternating dict/list. |
| 20 | Unterminated string scan O(n²) | **Yes** — `test_unterminated_string_raises_typed_in_bounded_time` 1 MB unterminated input asserts ≤ 0.5 s. |
| 21 | Unterminated block scan O(n²) | **Yes** — `test_unterminated_block_comment_raises_typed_in_bounded_time` 1 MB unterminated input asserts ≤ 0.5 s. |
| 22 | Only-comments → silent `{}` | **Yes** — `test_only_comments_is_malformed`. |
| 23 | Raw source bytes (`exc.doc`) in MalformedJSONError message | **Yes** — `test_malformed_json_message_truncated_and_no_doc_bytes` asserts `"{not json}" not in msg`. |
| 24 | Short read silently passes | **Yes** — `test_short_read_translates_to_malformed_json` monkey-patches `os.read` to return half the requested bytes. |

Additional positive-coverage tests added beyond the 24 mutations:

- `test_module_docstring_references_arch_and_adrs` — pins observability invariant (AC-3).
- `test_load_signature_is_keyword_only_caps_and_default_depth_is_64` — pins the public surface (AC-1).
- `test_strip_comments_is_pure_bytes_to_bytes` — pins the stripper helper purity (AC-10).
- `test_strip_comments_length_invariant` parametrized — pins structural invariant (AC-11).
- `test_well_balanced_5000_nested_block_comments_parses_under_1s` — pins the arch §"Edge cases" row 8 budget (AC-28).
- `test_symlink_refused_error_doc_names_jsonc` — pins the S1-01 follow-up (AC-27).

### Edge-case coverage crosswalk

| Arch edge case | Hardened story AC |
|---|---|
| Row 8 — `test_tsconfig_pathological.py` (deeply nested block comments + unterminated string + circular `extends`) → `jsonc.py` parses or raises typed error in < 1 s | AC-28 (well-balanced 5,000-deep parses < 1 s) + AC-29 (unbalanced 1 MB raises < 1 s) + AC-16 (any unterminated input < 0.5 s) — circular `extends` is out-of-scope (S2-02) |
| Row 2 — 600 MB string `package.json` (size cap analog for JSONC) | AC-7 (size cap pre-read) |
| Row 3 — symlink to `/etc/passwd` (analog for JSONC) | AC-5 + AC-6 (ELOOP + sentinel symlink) |
| Phase 0 markers-only invariant (cross-cutting) | AC-25 + `test_markers_only_positional_args0` parametrized over 4 marker types |
| ADR-0009 — no `pyjson5` / `orjson` | AC-4 (no `import re` enforces the broader "no fast-parser drift" spirit; the actual parser is stdlib `json` per implementation outline #5) |
| ADR-0008 — secret-leak prevention (raw source bytes never on the typed-exception message) | AC-17 + `test_malformed_json_message_truncated_and_no_doc_bytes` |

### Conflict / open-question disposition

- **S1-01 follow-up adoption.** S1-01's validation listed `safe_json`, `safe_yaml`, `jsonc` as the partners for the SymlinkRefusedError docstring extension. S1-02 already added `safe_json`. S1-03's hardening adds `safe_yaml` (pending implementation). S1-04 adds `parsers/jsonc` (AC-27). The `parsers` module slug is already on `DOCUMENTED_MODULE_SLUGS` (Phase 0), so the test contract is satisfied; the human-readable append is observability.
- **`_io.py` + `_depth.py` lift conditional on S1-03.** If S1-03 implementer chose to keep both inline in `safe_yaml.py` (and `safe_json.py`), S1-04 mirrors the inline shape from `safe_json`. If S1-03 already lifted, S1-04 consumes. Either order is valid; the hardened story's AC asserts the end-state (the walker descends dicts + lists; the cap event has `parser_kind="jsonc"`) rather than the import path.
- **`_strip_comments` `path` kwarg vs purity.** Two acceptable shapes documented in implementation outline #5; AC-10 accepts either by requiring the bytes-only call to succeed on inputs that don't raise (the test `test_strip_comments_is_pure_bytes_to_bytes` uses a happy-path input).
- **Newline preservation cross-platform line-number assertion.** Hard to test cross-platform without flake; AC-12 pins the structural requirement (newline preserved on `_S_LINE_COMMENT` exit) but does not write a cross-platform JSON-error line-number assertion. Implementer note documents the rationale.

### Plugin / strategy / dependency-inversion framing (per user prompt)

The user's prompt asked the validator to "Consider plugin architecture / Pluggable systems / Strategy pattern / Open/Closed / Dependency inversion / Hexagonal" for maintainability since `jsonc` is one of several sibling parsers (`safe_json`, `safe_yaml`, `_pnpm`, `_npm`, `_yarn`).

The hardened story applies the relevant patterns **without over-engineering** (Rule 2):

- **Small stable kernel + strategy modules.** `parsers/_io.py` (O_NOFOLLOW + size cap + structlog event) and `parsers/_depth.py` (post-parse depth walker; id()-memoized for YAML alias-safety, no-op-but-correct for JSON which has no aliases) form the kernel. Each `parsers/*.py` is a strategy that supplies its `parser_kind` literal and any parser-specific shape — for `jsonc`, the comment stripper. New parsers added by **new file + new `parser_kind` literal**; no edits to existing parsers (Open/Closed; **Extension by Addition** — CLAUDE.md load-bearing commitment).
- **Dependency inversion.** Each parser depends on the abstractions in `_io.py` / `_depth.py`, not on a concrete YAML/JSON library. The dependency direction is: `jsonc.py` → `_io.py` / `_depth.py` / `json` (stdlib); the kernel has no parser-specific knowledge. The state-machine stripper in `jsonc.py` is the parser's own logic; everything else delegates.
- **Strategy pattern via `parser_kind` discriminator.** The structlog `parser_kind` field is the de-facto registry — each parser supplies its identity (`"jsonc"` here), and downstream observers (Phase 13's cost ledger, Phase 6's state ledger) can attribute events without a central registration list.
- **Registry pattern — YAGNI in Phase 1.** No `parser_registry.register(...)` decorator, no factory function, no `Parser` ABC. Three concrete parsers (json/yaml/jsonc) plus three lockfile siblings is below the "premature abstraction" threshold (Rule 2: three similar lines is better than a premature abstraction; but a stable two-function kernel that three siblings consume IS the right factoring). Defer the registry to whenever a fourth distinct parser-family arrives (Phase 7+ for `safe_toml`, maybe; arguably never).
- **Hexagonal / ports & adapters — already in place.** The probe → parsers boundary is the port; each parser is an adapter from "untrusted bytes on disk" to "typed `JSONValue` mapping." The hardened story preserves this without renaming.
- **Make illegal states unrepresentable.** The `MalformedJSONError` raise on non-object roots (AC-18) prevents a probe from receiving a `list` where it expected a mapping. The signature `dict[str, JSONValue]` is the type-system enforcement; the `MalformedJSONError` raise is the runtime enforcement. The state-machine's four-state enum (`_S_CODE | _S_STRING | _S_LINE_COMMENT | _S_BLOCK_COMMENT`) plus the `escaped: bool` and `block_depth: int` companions makes "in a string inside a block comment" structurally unreachable (AC-15).
- **Smart constructor (where applicable).** Markers are constructed with positional formatted-message strings. The "smart constructor" is the convention that every raise site supplies enough context (path + cap or detail) inside the message — the markers themselves remain dumb.
- **Functional core, imperative shell.** `_strip_comments` is a pure function (functional core: `bytes -> bytes`); `load` is the imperative shell (opens fds, reads, calls the pure stripper, decodes, emits events). The split makes the state machine table-testable without filesystem fixtures (AC-10).
- **Newtype pattern — deferred.** The user-supplied list includes "newtype pattern for every domain primitive — `UserId`, `ThreadId`, `ToolCallId`, `RunId`. Never raw `str` or `int` for identifiers." Parser-internal `parser_kind` is a `Final[str]` literal, not an identifier — newtype would be premature here. The `JSONValue` recursive alias IS the domain primitive for this layer; it's typed and strict-checked.

These framings are **documented in Notes for the implementer → "Plugin/strategy framing"** so the executor sees them. The hardened story does **not** add an ABC, decorator, or factory — Rule 2 says three similar lines is better than premature abstraction, and the kernel of two stateless functions plus a `parser_kind` literal is the minimum viable factoring.

## Verdict & rationale

**HARDENED.** Story is now ready for the executor. Goal preserved exactly (the title slight extension — "state-machine comment stripper chained into safe_json" — is descriptive, not scope-changing; the original "chained into safe_json" line was kept for continuity even though the actual implementation does NOT call `safe_json.load` — it mirrors the shape and calls `json.loads(stripped)` + shared walker directly per AC-clarification CV5). ACs are individually verifiable; TDD plan is mutation-resistant against the 24 plausible wrong implementations enumerated; the JSONC-specific state-machine mutations (block-comment-`"`-inertness, backslash-escape combinations, unbalanced pathological wall-clock) are pinned by AC-13/AC-14/AC-15/AC-16/AC-28/AC-29 + dedicated tests. Markers-only Phase-0 contract is preserved across all 4 marker types this module raises. The S1-01 docstring-extension follow-up for `parsers/jsonc` is now owned by AC-27. The plugin-shape kernel (`_io.py` + `_depth.py` if S1-03 lifted; else mirrored inline) is honored without forcing a refactor.

No structural goal-vs-arch conflict requiring `phase-story-writer` re-run.

## Open questions / follow-ups for downstream stories

- **S1-05 (catalog loader)** is the next parser-adjacent story; it consumes `safe_yaml.load` against `catalogs/_schema.json`. Catalog YAMLs are small and trusted, but the depth walker still applies. JSONC is not used by S1-05.
- **S2-02 (NodeBuildSystemProbe)** consumes `jsonc.load` for `tsconfig.json` parsing and follows the `extends` chain ≤ 4 levels. The hardened `jsonc.load` raises `MalformedJSONError` / `SizeCapExceeded` / `DepthCapExceeded` / `SymlinkRefusedError` — the probe maps each to a structured `WarningId` per ADR-0007.
- **S5-03 (`test_tsconfig_pathological.py`)** carries the full-stack adversarial fixture for `NodeBuildSystemProbe`. The unit-level wall-clock budgets in this story (AC-16, AC-28, AC-29) are structural defenses at the parser layer; both layers must hold.
- **S1-10 (`probe.parser.cap_exceeded` constant)** can lift the literal string into a module-level `Final[str]` in `src/codegenie/logging.py`. This story is unaffected; the literal continues to work.
- **Arch §"Component design" #8 follow-up.** If S1-03's hardened story lifted `_io.py` / `_depth.py`, the arch text should reference them. Filed for S6-03 (Phase 1 README + arch hygiene).
- **Registry pattern deferred.** If Phase 7+ adds `safe_toml` and `safe_xml`, revisit whether the `parser_kind` discriminator + module-level convention should become a registered-decorator pattern. Until then, YAGNI (Rule 2).

## Sources cited by critics

- `src/codegenie/parsers/safe_json.py` (S1-02 source — fd/cap/walker shape precedent)
- `src/codegenie/parsers/__init__.py` (S1-02 source — `JSONValue` alias)
- `src/codegenie/errors.py` (Phase 0 + S1-01 source)
- `tests/unit/test_errors.py` (`test_subclasses_are_markers_only`, `EXPECTED_SUBCLASSES`, `DOCUMENTED_MODULE_SLUGS`)
- `tests/unit/parsers/test_safe_json.py` (S1-02 source — event-field assertion + fd-lifecycle pattern)
- `src/codegenie/logging.py` (structlog `Final[str]` event-name convention; testing pattern precedent)
- `docs/phases/01-context-gather-layer-a-node/phase-arch-design.md` §"Component design" #8, §"Edge cases" row 8, §"Harness engineering" → "Tracing strategy", §"Data model"
- `docs/phases/01-context-gather-layer-a-node/ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md`
- `docs/phases/01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md`
- `docs/phases/01-context-gather-layer-a-node/ADRs/0007-warnings-id-pattern.md`
- `docs/phases/01-context-gather-layer-a-node/stories/_validation/S1-01-errors-extension.md`
- `docs/phases/01-context-gather-layer-a-node/stories/_validation/S1-02-safe-json-parser.md` (precedent for hardening pattern)
- `docs/phases/01-context-gather-layer-a-node/stories/_validation/S1-03-safe-yaml-parser.md` (plugin-shape kernel precedent)
- `CLAUDE.md` "Facts, not judgments" + "Determinism over probabilism for structural changes" + "Extension by addition"
- `~/.claude/CLAUDE.md` Rule 2 (Simplicity First) + Rule 7 (Surface conflicts, don't average them) + Rule 9 (Tests verify intent, not just behavior) + Rule 12 (Fail loud)
