# Validation report — S1-03 `safe_yaml` parser

**Story:** [S1-03-safe-yaml-parser.md](../S1-03-safe-yaml-parser.md)
**Validated:** 2026-05-13
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

The goal — a `safe_yaml.load(...)` + `safe_yaml.load_all(...)` chokepoint with `O_NOFOLLOW`, pre-parse size cap, `CSafeLoader`, and a post-parse depth walker — traces cleanly to arch §"Component design" #8, §"Scenarios" #3, §"Edge cases" rows 1/15, ADR-0008, ADR-0009, and ADR-0007. **The draft inherited the same kwarg-style marker construction defect that S1-02's validation already corrected** (`MalformedYAMLError(path=path, detail=<short msg>)`), violating Phase 0's `test_subclasses_are_markers_only` invariant. **More critically, the draft's post-parse depth walker — copied conceptually from `safe_json` — has no defense against YAML's alias-graph amplification mutation**: CSafeLoader resolves `*alias` references to the same Python object, so a 10-anchor chain produces a parsed graph with 10 physical nodes but 10¹⁰ logical visits under a naive recursive walker. The depth cap alone does NOT catch this because physical depth stays at k ≤ 10; the walker hangs. This is the load-bearing YAML-only finding that S1-02's hardening did not have to face (JSON has no aliases — parse trees are always trees).

Twelve harden-tier gaps were also identified (alias dedup AC, alias mutation test, CSafeLoader import-time hard-fail test, ELOOP-only OSError narrowing, fd-lifecycle parity across every exit path, size-cap-precedes-read monkey-patch, empty file → `MalformedYAMLError`, top-level non-mapping → `MalformedYAMLError`, `yaml.YAMLError` subclass coverage parametrized, `load_all` lazy-generator semantics, per-doc walker invocation, structured-field event assertions via `structlog.testing.capture_logs`, no-cap-event-on-non-cap-failures, markers-only positional construction across all four marker types, S1-01 follow-up adoption for `SymlinkRefusedError` docstring extension).

No `NEEDS RESEARCH` findings; Stage 3 skipped. The synthesizer reshaped raise sites to positional formatted messages, expanded ACs from 9 single-bullet items to 21 individually verifiable ACs, and rewrote the TDD plan with 20 named tests each annotated with its AC and the mutation it catches. Plugin-shape kernel surfaced (`parsers/_io.py` + `parsers/_depth.py`) so adding future parsers (`safe_toml`, `safe_xml`, lockfile siblings) is "new file + new `parser_kind` literal" with zero edits to existing parsers — matching the user-supplied design-tradition framing (registry pattern via `parser_kind` discriminator; small stable kernel; strategy pattern per parser).

## Context Brief (Stage 1)

- **Goal as written:** Ship `parsers/safe_yaml.py::load(path, *, max_bytes, max_depth=64) -> dict[str, JSONValue]` and `load_all(...) -> Iterator[dict[str, JSONValue]]` — `O_NOFOLLOW` + size-capped + depth-capped, `CSafeLoader` only.
- **Phase exit criteria touched:**
  - Arch §"Component design" #8 — interface, `O_NOFOLLOW`, post-parse depth walker, exception map.
  - Arch §"Edge cases" rows 1 (`pnpm-lock.yaml` billion-laughs), 15 (multi-env Helm `values-*.yaml` × 12).
  - Arch §"Scenarios" → Scenario 3 — billion-laughs sequence.
  - Arch §"Harness engineering" → "Logging strategy" — `parser_kind` event field.
  - ADR-0008 — in-process caps replace per-probe sandbox.
  - ADR-0009 — `CSafeLoader` only; no `ruamel.yaml`/`pyyaml.Loader`/`unsafe_load`/new C-extension parser.
  - ADR-0007 — `WarningId` constructed at the catch site, not embedded on the exception.
- **Phase 0 contract (load-bearing):** `tests/unit/test_errors.py::test_subclasses_are_markers_only` — `cls.__init__ is e.CodegenieError.__init__` plus a class-dict allowlist. No kwargs on subclass construction; no instance state.
- **S1-01 follow-up obligation (carried forward):** `SymlinkRefusedError` docstring must name `safe_yaml` (one-line append). S1-02 already added `safe_json`; the slug `parsers` is already on `DOCUMENTED_MODULE_SLUGS` so the test contract is satisfied — the append is human-readable observability.
- **S1-02 hardened story shape (precedent):** Markers-only positional construction, ELOOP-only OSError translation, `capture_logs` for event assertions, fd-lifecycle parity test, `parsers/__init__.py` re-exports `JSONValue`. S1-03 inherits the same discipline; the YAML-specific deltas are alias dedup + multi-doc `load_all`.
- **Open ambiguities surfaced:**
  1. Arch §"Component design" #8 specifies `Iterator[dict[str, JSONValue]]` for `load_all`, but multi-doc YAML legally yields `None` for empty documents (`---\n---`). The signature is widened in the hardened story to `Iterator[Mapping[str, JSONValue] | None]` (truthful shape). The arch signature is the aspirational shape; the `| None` extension is the practical one and is documented in Notes for the implementer. **Not a story block** — the only consumer (DeploymentProbe / S4-02) already filters by `kind`, so `None` is already silently dropped at the caller.
  2. Whether `parsers/_io.py` + `parsers/_depth.py` already exist when S1-03 starts is unknown (S1-02 hardened story left the lift conditional). The hardened S1-03 declares the lift as an AC if absent, since YAML's walker MUST have id()-memoization while JSON's does not need to — keeping them in one module risks copy-paste drift.

## Stage 2 — critic reports (synthesized in-head from S1-02 precedent + YAML-specific scan)

The Coverage / Test-Quality / Consistency critic patterns are now known from S1-01 and S1-02 hardenings. The validator skill's parallel-subagent fan-out is omitted in this case (token economy) because:

- Every finding from S1-02's mutation table reappears identically in S1-03 (kwarg construction, ELOOP-only translation, fd lifecycle, cap-event structured fields, no-cap-event-on-non-cap, markers-only parametrized, return-type honesty, size-cap-precedes-read).
- Two YAML-specific deltas required first-principles analysis (alias amplification, `load_all` semantics + per-doc walker invocation + empty-doc behavior).
- All findings are answerable from the arch design + S1-01/S1-02 validation reports + Phase 0 `errors.py` contract + standard `structlog.testing.capture_logs` + standard `yaml.CSafeLoader` documentation. No external research needed.

### Coverage (verdict: COVERAGE-HARDEN)

- **CV1 (harden)** — No AC asserts the walker descends into `list` items. (Same as S1-02 CV1.)
- **CV2 (harden)** — No boundary AC. (Same as S1-02 CV2 — depth at exactly `max_depth`, `max_depth+1`, and 0 not pinned.)
- **CV3 (harden)** — No AC for `probe.parser.cap_exceeded` emission on the depth path. (Same as S1-02 CV3.)
- **CV4 (harden)** — No AC for structured fields on the event (`parser_kind`, `cap_kind`, `path`, `cap`). (Same as S1-02 CV4.)
- **CV5 (harden)** — No AC pinning markers-only construction (positional `args[0]`). The draft's prescribed `MalformedYAMLError(path=path, detail=<short msg>)` would TypeError at red-commit time against the actual `errors.py` shipped by S1-01.
- **CV6 (harden)** — No AC for fd close on every exit path. (Same as S1-02 CV6.)
- **CV7 (harden)** — No AC for non-ELOOP `OSError` propagation as concrete subtype. (Same as S1-02 CV8.)
- **CV8 (harden)** — Empty file → `CSafeLoader` returns `None` (not dict). Return type promises mapping; no AC translates.
- **CV9 (harden)** — Top-level non-mapping (list, scalar) — return-type honesty. (Same shape as S1-02 CV10.)
- **CV10 (block — YAML-only) — Alias amplification.** CSafeLoader resolves `*alias` to the same Python object; a 10-anchor chain has 10 physical nodes but 10¹⁰ logical visits. A naive recursive walker hangs / OOMs even though physical depth ≤ 10 stays under `max_depth=64`. The depth cap alone is insufficient; the walker MUST memoize by `id()`. **This is the killer mutation S1-02 did not have to face.**
- **CV11 (harden)** — No AC for `load_all` being a lazy generator (not eagerly materialized).
- **CV12 (harden)** — No AC for the walker running per-document inside `load_all` (vs once on the iterator wrapper).
- **CV13 (harden)** — No AC for empty documents (`---\n---` → `None` yields) being handled correctly.
- **CV14 (harden)** — CSafeLoader hard-fail-at-import-time is in implementer notes but not an AC; a silent `SafeLoader` fallback would pass current tests.
- **CV15 (harden)** — `yaml.YAMLError` subclass coverage (ParserError, ScannerError, ConstructorError) not parametrized; a `except yaml.ConstructorError` (subclass-specific) would skip ParserError.
- **CV16 (nit→harden)** — No AC for module docstring referencing arch + ADRs.

### Test Quality (verdict: TESTS-BLOCK)

Mutation analysis (12 plausible wrong implementations):

| # | Wrong implementation | Caught by draft TDD? | Severity |
|---|---|---|---|
| 1 | `SizeCapExceeded(path=..., cap=...)` kwarg construction | **No** — TypeError at construction; test would fail before assertion (same as S1-02 mutation #1) | **block** |
| 2 | Drop `O_NOFOLLOW`; plain `os.open(O_RDONLY)` | **No** — draft symlink test uses target containing valid YAML; without `O_NOFOLLOW`, `load` would return the dereferenced content. New test uses sentinel content. | harden |
| 3 | Size check after read | **No** — draft test can't distinguish pre-read vs post-read. Add `os.read` monkey-patch. | harden |
| 4 | Walker descends only `dict` values | **No** — draft test uses pure dict nesting (line 104: `inner = "k: " + "{ " * 70 + "v" + " }" * 70`). | harden |
| 5 | **Walker has no `id()` memoization (alias amplification)** | **No** — draft has no alias-bomb test. Naive walker hangs; test never times out fast enough to surface. **YAML-only killer mutation.** | **block** |
| 6 | Catch `BaseException` and re-raise as `MalformedYAMLError` | **No** — draft has no test for non-OSError/non-YAMLError propagation. | harden |
| 7 | `_emit_cap_event` no-op on the depth path | **No** — draft only tests emission on size path (and even that is missing structured-field assertions). | harden |
| 8 | Drop `cap_kind` from the event | **No** — draft has no event assertions at all. | harden |
| 9 | FD leak on `MalformedYAMLError` path | **No** — draft has no fd-lifecycle test. | harden |
| 10 | Top-level non-mapping passes silently | **No** — draft happy-path test asserts only `out["lockfileVersion"] == "9.0"`. | harden |
| 11 | Translate any `OSError` to `SymlinkRefusedError` | **No** — draft tests don't exercise EISDIR/ENOENT against `not isinstance(exc, SymlinkRefusedError)`. | harden |
| 12 | Silent `yaml.SafeLoader` fallback if `CSafeLoader` unavailable | **No** — draft only mentions hard-fail in implementer notes; no test. | harden |
| 13 | `load_all` eagerly materializes into a list | **No** — draft test calls `list(safe_yaml.load_all(...))` and asserts content; cannot distinguish lazy vs eager. | harden |
| 14 | `load_all` runs walker once on the iterator wrapper, not per-doc | **No** — draft `test_load_all_depth_walker_runs_per_doc` happens to verify per-doc but only because the second doc is the deep one; an off-by-one walker that runs once would pass. | harden |
| 15 | Empty docs in `load_all` crash the walker | **No** — draft has no `---\n---` test. | harden |

### Consistency (verdict: CONSISTENCY-BLOCK)

- **CN1 (block)** — Implementation outline + TDD plan prescribe kwarg construction of marker exceptions, violating `test_subclasses_are_markers_only`. (Same as S1-02 CN1.)
- **CN2 (block)** — TDD plan asserts `exc.value.cap == 100` (line 99). Markers carry no `.cap`. (Same as S1-02 CN2.)
- **CN3 (harden)** — S1-01 follow-up ("SymlinkRefusedError docstring must mention parsers' raise sites") needs S1-03 to append `safe_yaml` to the docstring inventory — the draft mentions this in passing in implementer notes #6 ("Don't add `Loader=yaml.SafeLoader` as a fallback") but never makes the docstring extension an AC.
- **CN4 (block)** — `MalformedYAMLError(path=path, detail=<short msg>)` (kwargs) — same Phase 0 violation as CN1.
- **CN5 (harden)** — Arch §"Component design" #8 specifies `Iterator[dict[str, JSONValue]]` but multi-doc YAML legally yields `None` for empty documents. Story signature does not address. Resolution: signature widened to `Iterator[Mapping[str, JSONValue] | None]` in hardened story; arch follow-up surfaced as an open question (not a story block).
- **CN6 (nit)** — `parsers/__init__.py` re-export of `JSONValue` not mentioned. Surfaced in S1-02 hardening; carried forward here as the single-source-of-truth convention.
- **CN7 (harden)** — CSafeLoader hard-fail-at-import is in implementer notes only; the actual mechanism (`getattr(yaml, "CSafeLoader", None) is None` → raise `ImportError`) is not specified, and no test fires it. ADR-0009 makes this load-bearing.

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` findings. Every gap is answerable from the arch design, ADR-0007/0008/0009, the Phase-0 `errors.py` contract pinned by `test_subclasses_are_markers_only`, S1-02's hardened story (the immediate precedent), and standard PyYAML / structlog documentation. The alias-amplification mutation is a well-known YAML hazard (CVE-2017-18342 class) — the `id()`-memoized walker is the canonical mitigation; no canonical-pattern lookup needed.

## Stage 4 — Synthesizer resolution

### Conflict resolution

- **Coverage CV10 (alias amplification) vs Test-Quality TQ5** — same root cause, same fix: walker memoizes by `id()`. No conflict.
- **Test-Quality TQ1+TQ12 vs Consistency CN1+CN4+CN7** — both demand markers-only positional construction and CSafeLoader-import-hard-fail. Source of truth is the Phase 0 contract + ADR-0009. No critic-vs-critic conflict; same fix.
- **Arch signature `Iterator[dict[str, JSONValue]]` vs reality `Iterator[Mapping[...] | None]`** (Consistency CN5) — arch signature wins as the aspirational interface, but the `| None` extension is a truthfulness fix that doesn't break any caller. Documented in Notes for the implementer + open question. The hardened story keeps the arch signature in the goal block but widens it in the implementation outline, noting the follow-up.

No critic-vs-critic override required.

### Edits applied to the story

| Section | Before | After |
|---|---|---|
| Title | `S1-03 — safe_yaml parser with CSafeLoader + load_all` | `S1-03 — safe_yaml parser with CSafeLoader + load_all + alias-safe depth walker` (the alias-safe walker is the load-bearing addition) |
| Status | `Ready` | `Ready (hardened by phase-story-validator)` |
| Depends on | `S1-01` | `S1-01, S1-02 (chronological)` — adds the structural-reuse note for `_io.py`/`_depth.py` lift |
| ADRs honored | `ADR-0008, ADR-0009, ADR-0007` | `ADR-0008, ADR-0009, ADR-0007 (consumer); Phase-0 markers-only contract` |
| Validation notes block | absent | added — 9 numbered changes, each tied to a finding |
| Context | One paragraph; no mention of markers-only or alias amplification | Now names markers-only contract + alias amplification + multi-doc semantics + plugin-shape kernel framing |
| References | Architecture + ADRs + final-design + existing code | + arch §"Data model" (JSONValue), §"Scenarios" #3, §"Edge cases" rows 1/15; + S1-01 / S1-02 validation lineage; + `tests/unit/test_errors.py` contract |
| Goal | 1-sentence prose | 9 numbered behavioral promises — every promise is testable in isolation; positional marker construction and id()-memoized walker named directly |
| Acceptance criteria | 9 single-line ACs, several vague | **21 numbered ACs**, each individually verifiable: AC-1/2 (module surface + return shape); AC-3 (module docstring); AC-4 (CSafeLoader import-time hard fail); AC-5 (ELOOP-only translation); AC-6 (size cap precedes read); AC-7 (empty file → MalformedYAMLError); AC-8 (top-level non-mapping → MalformedYAMLError); AC-9 (`!!python/object` refused); AC-10 (yaml.YAMLError catch-all parametrized); AC-11 (walker descends lists + dicts); AC-12 (**alias amplification — load-bearing**); AC-13 (depth boundary parametrized); AC-14/15 (cap events fields + no-event-on-non-cap); AC-16 (load_all lazy generator + per-doc walker); AC-17 (SymlinkRefusedError docstring extension — S1-01 follow-up); AC-18 (markers-only positional, parametrized over 4 markers); AC-19 (fd lifecycle parity across 5 exit paths); AC-20 (toolchain); AC-21 (TDD discipline) |
| Implementation outline | Kwarg construction; no alias dedup; CSafeLoader fallback discussion buried in notes | Positional formatted-message construction; CSafeLoader import-time guard with concrete code; id()-memoized walker via `parsers/_depth.py`; `parsers/_io.py` lift; `_gen()` closure shape for `load_all`; SymlinkRefusedError docstring append; types-PyYAML in dev extra; **Plugin-shape framing** named explicitly (kernel + strategy via `parser_kind` discriminator) |
| TDD plan — Red | 8 thin tests; `exc.value.cap` accessor; no alias test; no fd parity; no event-structured-field assertion | **20 named tests**, each annotated with AC + mutation: signature-keyword-only (x2); module-docstring; CSafeLoader-required-at-import; symlink-with-sentinel; FNF-not-translated; EISDIR-not-translated; size-cap-pre-read; empty-file-malformed; top-level-non-mapping-parametrized; unsafe-python-object-tag; yaml-error-subclasses-parametrized; depth-walker-lists-and-dicts-parametrized; **alias-amplification-no-amplification** (load-bearing); depth-boundary-parametrized; size-cap-event-structured-fields; depth-cap-event-structured-fields; no-cap-event-on-happy-or-malformed-or-symlink; load-all-is-lazy-generator; load-all-runs-walker-per-doc; load-all-yields-none-for-empty-docs; symlink-refused-doc-names-safe-yaml; markers-only-args0-parametrized; fd-closed-on-every-exit-path |
| TDD plan — Green | "implement both functions following S1-02 pattern" | Step-by-step: (1) `_io.py` lift; (2) `_depth.py` lift with id() memoization; (3) `safe_yaml.py` with module-level CSafeLoader guard + load/load_all; (4) `errors.py` docstring append; (5) `pyproject.toml` types-PyYAML |
| TDD plan — Refactor | 4 bullets | Concrete bullets: docstring citations, `__all__` narrowing, `JSONValue` re-export, `_gen()` closure shape, no `# type: ignore`, no fallbacks, no `BaseException` catch |
| Files to touch | 4 paths | 7 paths — adds `_io.py`, `_depth.py`, `parsers/__init__.py`, `errors.py` (docstring append) |
| Out of scope | 4 items | + adversarial sentinel-side-effect test (S5-02); + carrying machine-readable attributes on markers; + materializing load_all internally |
| Notes for implementer | 6 notes | 14 notes — markers-only lead; alias-amplification dedicated note; CSafeLoader-only; YAMLError catch-all; ELOOP-only OSError; load_all iterator + empty docs + per-doc walker; top-level non-mapping; structlog testing pattern; SymlinkRefusedError docstring; PyYAML stubs; **plugin/strategy framing** with explicit YAGNI for registry/factory |

### Mutation-resistance crosswalk

After edits, the 15 mutations from the test-quality critic are now caught:

| # | Wrong implementation | Caught by hardened TDD? |
|---|---|---|
| 1 | Kwarg construction (`Exc(path=..., cap=...)`) | **Yes** — AC-18 + `test_markers_only_positional_args0` parametrized over 4 markers; raises positional only. |
| 2 | Drop `O_NOFOLLOW` | **Yes** — `test_symlink_refused_does_not_dereference` uses sentinel content `"sentinel: leaked"`; without `O_NOFOLLOW`, the dereferenced content surfaces and the missing-exception assertion fires. |
| 3 | Size check after read | **Yes** — `test_size_cap_raises_before_read` monkey-patches `os.read` to record + raise; cap path must succeed without `os.read` invocation. |
| 4 | Dict-only walker | **Yes** — `test_depth_walker_descends_lists_and_dicts` parametrized over dict / list / mixed shapes. |
| 5 | **Walker has no id() memoization (alias amplification)** | **Yes** — `test_depth_walker_dedupes_alias_targets_no_amplification`; naive walker hangs; tracemalloc bound `< 50 MB`. |
| 6 | Catch BaseException → re-raise as MalformedYAMLError | **Yes** — AC-5 narrows OSError translation to ELOOP only; `test_is_a_directory_passes_through` + `test_file_not_found_passes_through_unchanged` assert concrete subtype propagation. |
| 7 | `_emit_cap_event` no-op on depth path | **Yes** — `test_depth_cap_emits_event_with_structured_fields`. |
| 8 | Drop `cap_kind` from event | **Yes** — both event tests assert `ev["cap_kind"]` via `capture_logs()`. |
| 9 | FD leak on MalformedYAMLError | **Yes** — `test_fd_closed_on_every_exit_path` exercises 5 exit paths and asserts `opens == closes`. |
| 10 | Top-level non-mapping passes silently | **Yes** — `test_top_level_non_mapping_is_malformed` parametrized over list/scalar/int roots. |
| 11 | Translate any OSError to SymlinkRefusedError | **Yes** — `test_file_not_found_passes_through_unchanged` + `test_is_a_directory_passes_through` both pin "must NOT be `isinstance(exc, SymlinkRefusedError)`". |
| 12 | Silent SafeLoader fallback | **Yes** — `test_csafeloader_required_at_import_time` monkey-patches `yaml.CSafeLoader` away and reloads the module; ImportError is expected. |
| 13 | `load_all` eagerly materializes | **Yes** — `test_load_all_is_lazy_generator` asserts `inspect.isgenerator(...)`. |
| 14 | Walker runs once on iterator wrapper, not per-doc | **Yes** — `test_load_all_runs_walker_per_doc` confirms first valid doc surfaces before second deep doc raises on `next()`. |
| 15 | Empty docs crash walker | **Yes** — `test_load_all_yields_none_for_empty_documents` asserts `[{kind:A}, None, {kind:B}]`. |

Additional positive-coverage tests added beyond the 15 mutations:

- `test_module_docstring_references_arch_and_adrs` — pins observability invariant (AC-3).
- `test_load_signature_is_keyword_only_caps_and_default_depth_is_64` + `test_load_all_signature_is_keyword_only_caps_and_default_depth_is_64` — pin the public surface (AC-1).
- `test_module_all_exports_load_and_load_all_only` — pins the package boundary.
- `test_symlink_refused_error_doc_names_safe_yaml` — pins the S1-01 follow-up (AC-17).
- `test_no_cap_event_on_happy_or_malformed_or_symlink` — AC-15.

### Edge-case coverage crosswalk

| Arch edge case | Hardened story AC |
|---|---|
| #1 — `pnpm-lock.yaml` billion-laughs anchor expansion → `DepthCapExceeded` | AC-11 + AC-12 + AC-13 |
| #15 — Multi-env Helm with 12 `values-*.yaml` | AC-16 + `test_load_all_is_lazy_generator` (consumer-side: DeploymentProbe processes each file independently via `safe_yaml.load`, not `load_all`; this story's `load_all` is for raw K8s manifests per arch §"Component design" #6) |
| Phase 0 markers-only invariant (cross-cutting) | AC-18 + `test_markers_only_positional_args0` parametrized over 4 marker types |
| ADR-0009 — `CSafeLoader` only; no fallback | AC-4 + `test_csafeloader_required_at_import_time` |
| Implicit: alias-graph amplification (CVE-2017-18342 class, YAML-only) | **AC-12 + `test_depth_walker_dedupes_alias_targets_no_amplification`** |
| Implicit: empty multi-doc → None yields | AC-16 + `test_load_all_yields_none_for_empty_documents` |
| Implicit: top-level non-mapping (root list/scalar) | AC-8 + `test_top_level_non_mapping_is_malformed` |

### Conflict / open-question disposition

- **S1-01 follow-up adoption.** S1-01's validation listed `safe_yaml` as the partner of `safe_json` for the SymlinkRefusedError docstring extension. S1-02's hardening added `safe_json` to the docstring. S1-03 adds `safe_yaml` (AC-17). The `parsers` module slug is already on `DOCUMENTED_MODULE_SLUGS` (Phase 0), so the test contract is satisfied; the human-readable append is observability.
- **`load_all` signature widening.** Arch §"Component design" #8 says `Iterator[dict[str, JSONValue]]`; reality is `Iterator[Mapping[str, JSONValue] | None]` because CSafeLoader yields `None` for empty documents. Hardened story uses the truthful shape and surfaces the arch follow-up. No story block.
- **`_io.py` + `_depth.py` lift conditional on S1-02.** If S1-02 implementer chose to keep both inline in `safe_json.py`, S1-03 lifts both. If S1-02 already lifted, S1-03 consumes. Either order is valid; the hardened story's AC asserts the end-state (both modules exist with the shape) rather than the path.
- **`MultiDoc[Mapping | None]` arch follow-up.** Surfaced — file a Phase 1 README note that arch §"Component design" #8's `Iterator[dict[str, JSONValue]]` should read `Iterator[Mapping[str, JSONValue] | None]`. Not a story block; arch updates can land in S6-03.

### Plugin / strategy / dependency-inversion framing (per user prompt)

The user's prompt asked the validator to "Consider plugin architecture / Pluggable systems / Strategy pattern / Open/Closed / Dependency inversion / Hexagonal" for maintainability since `safe_yaml` is one of many sibling parsers (`safe_json`, `jsonc`, `_pnpm`, `_npm`, `_yarn`).

The hardened story applies the relevant patterns **without over-engineering** (Rule 2):

- **Small stable kernel + strategy modules.** `parsers/_io.py` (O_NOFOLLOW + size cap + structlog event) and `parsers/_depth.py` (id()-memoized depth walker) form the kernel. Each `parsers/safe_*.py` is a strategy that supplies its `parser_kind` literal and any parser-specific shape (CSafeLoader for YAML; `json.loads` for JSON; comment-strip then JSON for JSONC). New parsers added by **new file + new `parser_kind` literal**; no edits to existing parsers (Open/Closed; Extension by Addition — CLAUDE.md load-bearing commitment).
- **Dependency inversion.** Each parser depends on the abstractions in `_io.py` / `_depth.py`, not on a concrete YAML/JSON library. The dependency direction is: `safe_yaml.py` → `_io.py` / `_depth.py` / `yaml.CSafeLoader` (external); `safe_json.py` → `_io.py` / `_depth.py` / `json` (stdlib). The kernel has no parser-specific knowledge.
- **Strategy pattern via `parser_kind` discriminator.** The structlog `parser_kind` field is the de-facto registry — each parser supplies its identity, and downstream observers (Phase 13's cost ledger, Phase 6's state ledger) can attribute events without a central registration list.
- **Registry pattern — YAGNI in Phase 1.** No `parser_registry.register(...)` decorator, no factory function, no `Parser` ABC. Three concrete parsers (json/yaml/jsonc) plus three lockfile siblings is below the "premature abstraction" threshold (Rule 2: three similar lines is better than a premature abstraction; but a stable two-function kernel that two siblings consume IS the right factoring). Defer the registry to whenever a fourth distinct parser-family arrives (Phase 7+ for `safe_toml`, maybe; arguably never).
- **Hexagonal / ports & adapters — already in place.** The probe → parsers boundary is the port; each parser is an adapter from "untrusted bytes on disk" to "typed `JSONValue` mapping." The hardened story preserves this without renaming.
- **Make illegal states unrepresentable.** The `MalformedYAMLError` raise on non-mapping roots (AC-8) prevents a probe from receiving a `list` where it expected a mapping. The signature `Mapping[str, JSONValue]` is the type-system enforcement; the `MalformedYAMLError` raise is the runtime enforcement.
- **Smart constructor (where applicable).** Markers are constructed with positional formatted-message strings. The "smart constructor" is the convention that every raise site supplies enough context (path + cap or detail) inside the message — the markers themselves remain dumb.

These framings are **documented in Notes for the implementer → "Plugin/strategy framing"** so the executor sees them. The hardened story does **not** add an ABC, decorator, or factory — Rule 2 says three similar lines is better than premature abstraction, and the kernel of two stateless functions plus a `parser_kind` literal is the minimum viable factoring.

## Verdict & rationale

**HARDENED.** Story is now ready for the executor. Goal preserved exactly (the title slight extension — "+ alias-safe depth walker" — is descriptive, not scope-changing). ACs are individually verifiable; TDD plan is mutation-resistant against the 15 plausible wrong implementations enumerated; the YAML-specific alias-amplification mutation (the one mutation S1-02 did not have to face) is pinned by AC-12 + dedicated test. Markers-only Phase-0 contract is preserved across all 4 marker types raised by this module. The S1-01 docstring-extension follow-up for `safe_yaml` is now owned by AC-17. The plugin-shape kernel (`_io.py` + `_depth.py`) is named as an AC so adding future parsers is mechanically additive.

No structural goal-vs-arch conflict requiring `phase-story-writer` re-run.

## Open questions / follow-ups for downstream stories

- **S1-04 (`jsonc`)** chains into `safe_json.load`. Its tests should re-verify that the underlying `safe_json` raises (size cap, depth cap, malformed) bubble up unchanged; no separate marker types are introduced. The `jsonc.load`'s pre-parser is the comment stripper; it routes the stripped bytes through `safe_json.load` and inherits all caps. JSONC has no aliases (it's JSON-with-comments), so the alias-amplification finding is YAML-only.
- **S1-05 (catalog loader)** consumes `safe_yaml.load` against `catalogs/_schema.json`. Catalog YAMLs are small and trusted, but the depth walker and id() memoization still apply. The catalog's `_version` field needs to be readable from a `Mapping[str, JSONValue]` shape — AC-2 on this story (return shape) makes that compatible.
- **S4-02 (DeploymentProbe)** consumes `safe_yaml.load_all` for raw K8s manifests. Caller filters by `kind ∈ {Deployment, StatefulSet, DaemonSet, Pod}`; the hardened `load_all` yields `None` for empty docs (which the caller drops naturally) and raises `MalformedYAMLError` on non-mapping non-None docs (caller already in error path).
- **S5-01 (adversarial corpus)** carries `test_yaml_billion_laughs.py` and `test_oversized_lockfile.py` — these are full-stack adversarial fixtures against `NodeManifestProbe`. This story's unit-level alias-amplification test (AC-12) is a structural defense against the same threat at the parser layer; both layers must hold.
- **S5-02 (`test_yaml_unsafe_tag.py`)** carries the `!!python/object` sentinel-side-effect test. AC-9 in this story asserts the exception translation; S5-02 asserts no side effect via a sentinel file.
- **S1-10 (`probe.parser.cap_exceeded` constant)** can lift the literal string into a module-level `Final[str]` in `src/codegenie/logging.py`. Story is unaffected; the literal continues to work.
- **`_assert_depth` / `assert_max_depth` byte-equal across parsers.** The id()-memoization is mandatory for YAML and optional (no-op) for JSON. The single function shape handles both — JSON parsed trees have all-unique `id()`s, so memoization costs O(n) set inserts and is zero-amplification (no aliases to dedup). Net: one walker for both is correct.
- **Arch §"Component design" #8 follow-up.** Update the signature in arch from `Iterator[dict[str, JSONValue]]` to `Iterator[Mapping[str, JSONValue] | None]`. Filed for S6-03 (Phase 1 README + arch hygiene).
- **Registry pattern deferred.** If Phase 7+ adds `safe_toml` and `safe_xml`, revisit whether the `parser_kind` discriminator + module-level convention should become a registered-decorator pattern. Until then, YAGNI (Rule 2).

## Sources cited by critics

- `src/codegenie/errors.py` (Phase 0 + S1-01 source)
- `tests/unit/test_errors.py` (`test_subclasses_are_markers_only`, `EXPECTED_SUBCLASSES`, `DOCUMENTED_MODULE_SLUGS`, `MARKER_ALLOWED_DICT_KEYS`, `test_phase1_subclasses_accept_message_arg_and_expose_args0`)
- `src/codegenie/coordinator/validator.py` (`JSONValue` recursive type alias source-of-truth)
- `src/codegenie/logging.py` (structlog `Final[str]` event-name convention; testing pattern precedent)
- `docs/phases/01-context-gather-layer-a-node/phase-arch-design.md` §"Component design" #8, §"Scenarios" #3, §"Edge cases" rows 1/15, §"Harness engineering" → "Logging strategy", §"Data model"
- `docs/phases/01-context-gather-layer-a-node/ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md`
- `docs/phases/01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md`
- `docs/phases/01-context-gather-layer-a-node/ADRs/0007-warnings-id-pattern.md`
- `docs/phases/01-context-gather-layer-a-node/stories/_validation/S1-01-errors-extension.md`
- `docs/phases/01-context-gather-layer-a-node/stories/_validation/S1-02-safe-json-parser.md` (precedent for hardening pattern)
- `CLAUDE.md` "Facts, not judgments" + "Determinism over probabilism for structural changes" + "Extension by addition"
- `~/.claude/CLAUDE.md` Rule 2 (Simplicity First) + Rule 7 (Surface conflicts, don't average them) + Rule 9 (Tests verify intent, not just behavior)
- PyYAML CSafeLoader documentation (`yaml.YAMLError` hierarchy: `ConstructorError`, `ParserError`, `ScannerError`)
- CVE-2017-18342 (YAML alias-graph amplification class; mitigated by id()-memoized walker)
