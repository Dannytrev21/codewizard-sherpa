# Validation report — S1-02 `safe_json` parser

**Story:** [S1-02-safe-json-parser.md](../S1-02-safe-json-parser.md)
**Validated:** 2026-05-13
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The goal — a `safe_json.load(...)` chokepoint with `O_NOFOLLOW`, pre-parse size cap, and post-parse depth walker — is sound and traces cleanly to arch §"Component design" #8, ADR-0008, ADR-0009, and ADR-0007. **However the draft prescribed kwarg construction of the new marker exceptions (`SizeCapExceeded(path=..., cap=...)`, etc.) which directly violates the Phase-0 markers-only invariant pinned by `tests/unit/test_errors.py::test_subclasses_are_markers_only` and re-affirmed by S1-01's hardening.** The TDD plan further assumed `exc.value.cap` accessors that cannot exist on a marker. Eleven additional harden-tier gaps were found across coverage and test-quality lenses (mixed dict/list depth descent, boundary, depth-cap event, structlog field-level assertions, non-ELOOP OSError passthrough, short read, empty file, non-object root, FD lifecycle, S1-01 docstring follow-up, type-safe return).

No `NEEDS RESEARCH` findings; Stage 3 skipped. The synthesizer reshaped raise sites to positional formatted messages, added 18 individually verifiable ACs (up from 11 single-bullet ACs in the draft), and rewrote the TDD plan with 19 named tests, each annotated with its AC and the mutation it catches.

## Context Brief (Stage 1)

- **Goal as written:** Ship `parsers/safe_json.py::load(path, *, max_bytes, max_depth=64)` opening with `O_NOFOLLOW`, size-capping pre-parse, parsing with stdlib `json.loads`, depth-walking post-parse.
- **Phase exit criteria touched:**
  - Arch §"Component design" #8 — interface, `O_NOFOLLOW`, post-parse depth walker, exception map.
  - Arch §"Edge cases" rows 2, 3 — 600 MB string, symlink to `/etc/passwd`.
  - Arch §"Harness engineering" → "Logging strategy" — `probe.parser.cap_exceeded` fields.
  - ADR-0008 — in-process caps replace per-probe sandbox.
  - ADR-0009 — stdlib `json.loads` only; no `orjson`/`pyjson5`.
  - ADR-0007 — `WarningId` constructed at catch site, not embedded on the exception.
- **Phase 0 contract (load-bearing):** `tests/unit/test_errors.py::test_subclasses_are_markers_only` — `cls.__init__ is e.CodegenieError.__init__` plus a class-dict allowlist of `{"__module__","__qualname__","__doc__","__firstlineno__","__static_attributes__"}`. **No kwargs on subclass construction. No instance state.**
- **S1-01 follow-up obligation (carried forward):** "S1-02 / S1-03 / S1-04 must extend `SymlinkRefusedError` docstring (Phase 0) to mention the parser walker if the raise site broadens."
- **Open ambiguities:** None blocking; the kwarg-vs-positional question is settled by the Phase-0 contract.

## Stage 2 — critic reports

### Coverage (verdict: COVERAGE-HARDEN)

- **CV1 (harden)** — No AC asserts the depth walker descends into `list` items. A walker that only descends into `dict` values passes billion-laughs-via-list and through `_lockfiles/_npm.py` (a dict of dicts that *also* nest under `dependencies` lists in some shapes).
- **CV2 (harden)** — No boundary AC. Depths exactly at `max_depth`, at `max_depth+1`, and at 0 are not pinned. The draft test uses 70 vs cap 64 — a single-point assertion.
- **CV3 (harden)** — No AC for `probe.parser.cap_exceeded` emission on the **depth** path; only size-cap emission was tested. Mutation: drop event emission from `_assert_depth`.
- **CV4 (harden)** — No AC for the **structured fields** on the event. Draft assertions checked stderr substrings `"probe.parser.cap_exceeded"` and `"safe_json"`. Substring `"safe_json"` matches either `parser` or `parser_kind`, can't distinguish a dropped `cap_kind`, and depends on JSON-renderer init.
- **CV5 (harden)** — No AC pinning that raised exceptions are constructed as markers (positional `args[0]`). The draft is **silent** on the contract, and the implementation outline contradicts it.
- **CV6 (harden)** — No AC verifies fd is closed on every exit path; outline says `try/finally` but no test asserts open-close parity across success / size cap / malformed / depth cap.
- **CV7 (harden)** — Short-read behavior (note 186) is implementer-note prose only. No AC; no test.
- **CV8 (harden)** — Non-ELOOP `OSError` translation is loosely specified ("`ELOOP`/`ENOTDIR`/`EINVAL` to `SymlinkRefusedError`"). `EISDIR`, `EACCES`, `ENOENT` are not explicitly excluded; a mutation `except OSError: raise SymlinkRefusedError(...)` would pass the lone draft symlink test.
- **CV9 (nit→harden)** — No AC for module docstring (arch + ADR refs). Implementer-note only.
- **CV10 (harden)** — Return-type honesty: `load` returns `dict[str, JSONValue]`, but `json.loads("[1,2,3]")` returns a list. The draft is silent; the consumer (memo + downstream probes) would crash.
- **CV11 (harden)** — Empty file (size 0): `json.loads(b"")` raises `JSONDecodeError` → must translate to `MalformedJSONError`. Not pinned.
- **CV12 (nit)** — AC-9 in the draft ("TDD red test exists, committed, green") is process discipline, not a verifiable behavioral AC.

### Test Quality (verdict: TESTS-BLOCK)

Mutation analysis (10 plausible wrong implementations):

| # | Wrong implementation | Caught by draft TDD? | Severity |
|---|---|---|---|
| 1 | `SizeCapExceeded(path=path, cap=max_bytes)` kwarg construction (and `exc.value.cap == 100` assertion) | **No** — both the implementation and the test fail against the markers-only invariant; the test would never reach its assert because construction raises `TypeError`. Story is self-inconsistent. | **block** |
| 2 | Drop `O_NOFOLLOW`; plain `os.open(O_RDONLY)` | **No** — draft `test_symlink_refused` uses a target containing `"{}"`. Without `O_NOFOLLOW`, `load` would return `{}` and the `pytest.raises` would fail by **timing out the test only if** the assertion succeeded — actually the test simply fails (no exception raised), but a silent regression would be hard to debug. New test uses a sentinel that surfaces the failure mode. | harden |
| 3 | Size check after read (read whole file then check) | **No** — draft test still observes `SizeCapExceeded`; can't distinguish pre-read vs post-read. Added `os.read` monkey-patch + sparse-file tracemalloc canary. | harden |
| 4 | Walker descends only into `dict` values | **No** — draft test uses pure dict nesting. | harden |
| 5 | Catch `BaseException` and re-raise as `MalformedJSONError` (masks all errors) | **No** — draft has no test for non-OSError/non-JSONDecodeError propagation. Implicitly caught now: AC-5 requires `EISDIR`/`FileNotFoundError` propagate as their concrete OSError subtype. | harden |
| 6 | `_emit_cap_event` no-op on the depth path | **No** — draft only tests emission on size path. | harden |
| 7 | Drop `cap_kind` from the event | **No** — substring-on-stderr test can't see structured fields. Replaced with `capture_logs()` and direct field assertions. | harden |
| 8 | FD leak on `MalformedJSONError` path (close in `try`, not `finally`) | **No** — draft has no fd-lifecycle test. | harden |
| 9 | Top-level `json.loads("[1,2,3]")` silently returns the list, violating the `dict[str, JSONValue]` return type | **No** — draft happy-path test asserts only `out["name"] == "x"`. | harden |
| 10 | Translate any `OSError` to `SymlinkRefusedError` | **No** — draft tests don't exercise EISDIR/ENOENT against the type-narrow `SymlinkRefusedError` predicate. | harden |

Plus: the `capsys`-on-stderr pattern in `test_cap_exceeded_emits_structlog_event` is fragile (depends on `configure_logging` choosing a JSON renderer and `monkeypatch.setattr("sys.stderr.isatty", lambda: False)` working before structlog grabs a reference). `structlog.testing.capture_logs` is the canonical alternative.

### Consistency (verdict: CONSISTENCY-BLOCK)

- **CN1 (block)** — Implementation outline + TDD plan both prescribe kwarg construction of marker exceptions, violating `test_subclasses_are_markers_only` (the Phase-0 contract re-affirmed by S1-01). The story would block at red-test commit time — the test file itself would `TypeError` on `SizeCapExceeded(path=path, cap=max_bytes)`.
- **CN2 (block)** — TDD plan asserts `exc.value.cap == 100`. Markers carry no `.cap`. Tests written this way fail under the actual `errors.py` shipped by S1-01.
- **CN3 (harden)** — S1-01's open follow-up ("S1-02 / S1-03 / S1-04 must extend `SymlinkRefusedError` docstring") is **not addressed** in the draft. Story should carry it forward as an AC (it's a one-line docstring edit; doing it here pre-empts ambiguity for S1-03's `safe_yaml` and S1-04's `jsonc`).
- **CN4 (harden)** — Story uses `MalformedJSONError(path=path, detail=<short msg>)` (kwargs) — same Phase-0 violation as CN1.
- **CN5 (nit)** — Story mentions "ADR-0008 (Phase 0 chokepoint preservation)" in the ADRs-honored header. The Phase-0 chokepoint preservation is implicit via the `OutputSanitizer` not being edited; the **load-bearing** ADR is **Phase 1's** ADR-0008 (in-process caps), which the draft does list. No edit needed but the header was reviewed for accuracy.
- **CN6 (nit)** — `JSONValue` recursive type alias is referenced (return annotation) but not specified anywhere in the draft. Arch §"Data model" defines it; story should re-export via `parsers/__init__.py` (single-source-of-truth at the package boundary).

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` findings. Every gap is answerable from the arch design, ADR-0007/0008/0009, the Phase-0 `errors.py` contract pinned by `test_subclasses_are_markers_only`, and standard `structlog.testing.capture_logs` usage.

## Stage 4 — Synthesizer resolution

### Conflict resolution

- **Coverage CV1+CV2+CV3+CV4+CV5+CV6+CV7+CV8+CV9+CV10+CV11** vs **Consistency CN1/CN2/CN4**: no real conflict. Coverage wants richer evidence; Consistency wants the marker shape preserved. Both reconciled by adding ACs that pin behavior **via positional `args[0]`** rather than via kwarg construction or instance accessors.
- **Test-Quality TQ1** (kwarg construction caught by `TypeError`) vs **Consistency CN1** (kwarg construction violates Phase-0 contract): both demand the same fix — switch to positional formatted-message construction. Source of truth = the Phase-0 contract. Markers-only wins (per skill rule: arch + Phase-0 contract is authoritative).

No critic-vs-critic conflict required a Consistency override. The block-tier issues were all instances of the same root cause (draft was authored before the S1-01 hardening landed and inherited the kwarg-construction assumption).

### Edits applied to the story

| Section | Before | After |
|---|---|---|
| Status | `Ready` | `Ready (hardened by phase-story-validator)` |
| Validation notes block | absent | added — summarizes 14 structural changes, every change traced to a finding |
| Context | One paragraph; no mention of markers-only contract | Adds the Phase-0 markers-only contract as the binding invariant; names `tests/unit/test_errors.py::test_subclasses_are_markers_only` directly |
| References | Architecture + ADRs + final-design + existing code | Adds: arch §"Data model" (JSONValue); `tests/unit/test_errors.py::EXPECTED_SUBCLASSES`/`DOCUMENTED_MODULE_SLUGS`; S1-01 validation follow-ups |
| Goal | "raises `SizeCapExceeded(path=...)` etc." (kwargs) | Restated as eight numbered behaviors; every raise explicitly described as constructing a marker with a positional formatted-message string |
| Acceptance criteria | 11 single-line ACs, several vague | **19 numbered ACs**, each individually verifiable: AC-1/2/3 (module shape + docstring); AC-4 (fd close on every path); AC-5 (ELOOP-only translation; concrete non-translation for IsADirectoryError/PermissionError/FileNotFoundError); AC-6 (size cap precedes `os.read`); AC-7 (short read → MalformedJSONError); AC-8 (no `exc.doc` leak); AC-9 (top-level non-object → MalformedJSONError); AC-10 (empty file → MalformedJSONError); AC-11 (walker descends dicts **and** lists); AC-12 (boundary parametrized: 0, 1, 63, 64, 65, 70, 200 + mixed nesting); AC-13/14 (cap event fields asserted via `capture_logs`); AC-15 (no event on non-cap failures); AC-16/17 (markers-only construction + `args[0]` recovery); AC-18 (`SymlinkRefusedError` docstring extension — S1-01 follow-up); AC-19 (toolchain) |
| Implementation outline | Kwarg construction of every exception | Positional formatted-message construction (with concrete `f"..."` strings); fd close in `finally`; `_emit_cap_event` helper; top-level-dict check; `_assert_depth` walks both dicts and lists; explicit ELOOP-only mapping; `SymlinkRefusedError.__doc__` extension as step 6 |
| TDD plan — Red | 7 thin tests; capsys-on-stderr substring; `.cap` accessor | **19 named tests**, each annotated with AC + mutation caught: happy-path/signature/docstring/symlink-with-sentinel/FNF-not-translated/EISDIR-not-translated/size-cap-pre-read/short-read/malformed/top-level-non-object/empty-file/depth-boundary-parametrized/depth-above-cap/depth-walker-descends-lists/depth-walker-pure-list/markers-only-args0-roundtrip/fd-lifecycle/size-event/depth-event/no-event-on-happy/no-event-on-malformed-or-symlink/tracemalloc-canary/SymlinkRefusedError-doc-names-parsers |
| TDD plan — Green | "`exc.value.cap`", kwargs | Positional construction; structlog event via helper; ELOOP-only translation; `try/finally` close |
| TDD plan — Refactor | Type-annotate; module docstring; `_emit_cap_event` helper | + `JSONValue` recursive alias defined once in `parsers/__init__.py`; `load` docstring enumerates raised exceptions; `_assert_depth` recursion-limit guard; explicit no-catch-BaseException reminder |
| Files to touch | 4 paths | 5 paths — adds `src/codegenie/errors.py` (one-line docstring extension; AC-18) |
| Out of scope | Existing 4 items | + "Carrying machine-readable `path`/`cap`/`detail` attributes" (markers-only contract) + "Lifting `_assert_depth` into a shared util" (defer until S1-03 reveals symmetry) + `MalformedYAMLError` raise sites (S1-03) |
| Notes for implementer | Existing 6 notes | + "Markers-only construction" lead note + "Top-level shape" note + "Only ELOOP translates" emphasis + "Structlog testing" note (capture_logs) |

### Mutation-resistance crosswalk

After edits, the ten mutations from the test-quality critic are now caught:

| # | Wrong implementation | Caught by hardened TDD? |
|---|---|---|
| 1 | Kwarg construction (`Exc(path=..., cap=...)`) + `.cap` accessor | **Yes** — every raise is positional-only by AC-16; every test asserts via `args[0]`/`str(exc)`; AC-17 + `test_raised_markers_carry_no_instance_state` parametrize over all three Phase-1 marker types and assert `not hasattr(..., {"path","cap","detail","warning_id"})`. The implementation cannot satisfy ACs while violating the Phase-0 contract. |
| 2 | Drop `O_NOFOLLOW` | **Yes** — `test_symlink_refused_does_not_dereference` uses sentinel content `{"sentinel": "leaked"}`; without `O_NOFOLLOW`, the test would fail on the missing-exception assertion *and* a follow-up assertion would surface the dereference. |
| 3 | Size check after read | **Yes** — `test_size_cap_raises_before_read` monkey-patches `os.read` to record calls + raise; the SizeCapExceeded path must succeed without `os.read` being invoked. `test_size_cap_bounds_memory_allocation` is a secondary tracemalloc canary on a 50 MB sparse file. |
| 4 | Dict-only walker | **Yes** — `test_depth_walker_descends_into_lists` + `test_depth_walker_handles_pure_list_nesting` + parametrized mixed-nesting fixture (`_mixed_nesting`). |
| 5 | Catch BaseException → re-raise as MalformedJSONError | **Yes** — AC-5 narrows OSError translation to ELOOP only; `test_is_a_directory_passes_through` asserts `not isinstance(exc, SymlinkRefusedError)` and that the concrete `OSError` subtype propagates. |
| 6 | `_emit_cap_event` no-op on depth path | **Yes** — `test_depth_cap_emits_event` (AC-14). |
| 7 | Drop `cap_kind` from event | **Yes** — `test_size_cap_emits_event` and `test_depth_cap_emits_event` both assert `ev["cap_kind"]` directly via `capture_logs()`. |
| 8 | FD leak on MalformedJSONError path | **Yes** — `test_fd_closed_on_every_exit_path` asserts `opened == closed` after happy + size-cap + malformed + depth-cap paths. |
| 9 | Top-level list passes silently | **Yes** — `test_top_level_non_object_is_malformed` (AC-9). |
| 10 | Translate any OSError to SymlinkRefusedError | **Yes** — `test_file_not_found_passes_through_unchanged` + `test_is_a_directory_passes_through` both pin "must NOT be `isinstance(exc, SymlinkRefusedError)`". |

Additional positive-coverage tests added beyond the ten mutations:

- `test_module_docstring_references_arch_and_adrs` — module docstring is part of the audit invariant (AC-3).
- `test_load_signature_is_keyword_only_caps_and_default_depth_is_64` — pins the public surface (AC-2).
- `test_no_cap_event_on_happy_path` + `test_no_cap_event_on_malformed_or_symlink` — AC-15 (event must not fire on non-cap failures).
- `test_symlink_refused_error_doc_names_parsers` — AC-18 / S1-01 follow-up.

### Edge-case coverage crosswalk

| Arch edge case | Hardened story AC |
|---|---|
| #2 — 600 MB string in `package.json` → `SizeCapExceeded` | AC-6 + `test_size_cap_bounds_memory_allocation` (sparse-file canary) |
| #3 — `package.json` symlink → `SymlinkRefusedError` | AC-5 + `test_symlink_refused_does_not_dereference` (sentinel) |
| Implicit: billion-laughs via lockfile → `DepthCapExceeded` (S5-01 carries the YAML fixture, but the same walker shape applies to S1-04 jsonc deep nesting) | AC-11 + AC-12 + `test_depth_walker_handles_pure_list_nesting` |
| Implicit: malformed `tsconfig.json` → `MalformedJSONError` | AC-8 + AC-10 |
| Phase-0 markers-only invariant (cross-cutting) | AC-16 + AC-17 + `test_raised_markers_carry_no_instance_state` parametrized over Phase-1 markers |

### Conflict / open-question disposition

- **S1-01 follow-up adoption.** S1-01's validation explicitly named S1-02 as the owner of the `SymlinkRefusedError` docstring extension. The validator adopted this rather than deferring further (it's a one-line edit and pre-empts ambiguity for S1-03 + S1-04). The Phase-0 `DOCUMENTED_MODULE_SLUGS` set already includes `parsers`, so the test contract requires only that the slug appear in the docstring.
- **`load_any` for non-object roots.** Out of scope. Rejected forward-shaping (Rule 2 / Rule 3); a future probe that needs root-as-list can introduce `load_any` then.

## Verdict & rationale

**HARDENED.** Story is now ready for the executor. Goal preserved exactly; ACs are individually verifiable; TDD plan is mutation-resistant against the 10 plausible wrong implementations enumerated; markers-only Phase-0 contract is preserved across all six new ACs that touch typed-exception construction; the S1-01 docstring-extension follow-up is now owned by an AC. No structural goal-vs-arch conflict requiring `phase-story-writer` re-run.

## Open questions / follow-ups for downstream stories

- **S1-03 (`safe_yaml`)** inherits the same markers-only construction discipline. The `MalformedYAMLError` raise site there must use positional formatted messages and a parallel structlog event with `parser="safe_yaml"`. The `SymlinkRefusedError` docstring extended by AC-18 already covers `parsers/` as a slug, so S1-03 should **add `safe_yaml` to the docstring inventory** (one-line append) — not a new slug.
- **S1-04 (`jsonc`)** chains into `safe_json.load`. Its tests should re-verify that the underlying `safe_json` raises (size cap, depth cap, malformed) bubble up unchanged; no separate marker types are introduced.
- **S1-10 (`probe.parser.cap_exceeded` constant)** can lift the literal string into a module-level `Final[str]`. Story is unaffected; the literal continues to work.
- **`_assert_depth` deduplication.** If S1-03's `safe_yaml.load` walker is byte-identical in shape (likely — it walks `dict`/`list`), refactor into a shared `parsers/_depth.py` helper at S1-03 time. Defer until both walkers exist (Rule 2).
- **Future structured-state need.** If any later phase needs introspectable `.path` / `.cap` attributes on these markers (e.g., retry logic that branches on cap-vs-detail), it must amend the Phase-0 markers-only invariant via an ADR that re-shapes **all 17** subclasses uniformly — not an asymmetric Phase-1 carve-out (same caveat as S1-01).

## Sources cited by critics

- `src/codegenie/errors.py` (Phase 0 + S1-01 source)
- `tests/unit/test_errors.py` (`test_subclasses_are_markers_only`, `EXPECTED_SUBCLASSES`, `DOCUMENTED_MODULE_SLUGS`, `MARKER_ALLOWED_DICT_KEYS`)
- `tests/unit/test_logging.py` (structlog testing pattern precedent)
- `docs/phases/01-context-gather-layer-a-node/phase-arch-design.md` §"Component design" #8, §"Edge cases" rows 2/3, §"Harness engineering" → "Logging strategy", §"Data model"
- `docs/phases/01-context-gather-layer-a-node/ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md`
- `docs/phases/01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md`
- `docs/phases/01-context-gather-layer-a-node/ADRs/0007-warnings-id-pattern.md`
- `docs/phases/01-context-gather-layer-a-node/stories/_validation/S1-01-errors-extension.md` (open-question follow-up)
- `CLAUDE.md` "Facts, not judgments" + "Determinism over probabilism for structural changes" + "Extension by addition"
