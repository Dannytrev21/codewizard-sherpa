# Validation report — S1-01 Phase 3 newtype identifiers + smart constructors

**Story:** [`../S1-01-phase3-newtype-identifiers.md`](../S1-01-phase3-newtype-identifiers.md)
**Validated:** 2026-05-18
**Validator:** phase-story-validator (scheduled task: `story-validation-corrector`)
**Verdict:** **HARDENED**

## Summary

The story lands the 14 Phase-3-new domain newtypes plus smart-constructor parsers — the load-bearing type vocabulary every subsequent Phase 3 story (S1-02 ScopeDim, S1-03 outcome unions, S1-04 ApplyContext / AttemptSummary, S2-* registry, S5-* recipe engine, S6-* orchestrator) imports from. Validation found:

- **One block-tier conflict** that the story already gestured at but did not resolve: it prescribes creating `src/codegenie/types/result.py` with `Ok`/`Err`/`Result`/`ParseError`, but **`src/codegenie/result.py` already exists** at the canonical Phase-2 location (S1-04 / `TCCMLoader`, also consumed by `SkillsLoader` and `ConventionsCatalogLoader`). Forking the `Result` type at a second path is a direct violation of CLAUDE.md Rule 7 ("Surface conflicts, don't average them") and the story's own Notes-for-implementer hedge. Closure: `Result`/`Ok`/`Err` are reused from `codegenie.result`; the *new* `ParseError` ships at `src/codegenie/types/errors.py`.
- **One block-tier verification gap** that S1-05 (Phase 2) already burned the family on and which the writer mirrored verbatim into S1-01: AC-6 ("cross-newtype substitution is a mypy error") points at `tests/unit/types/test_identifiers_typecheck.py`, whose mypy-rejecting lines are **commented out as prose**. No CI step runs them. Closure: an executable subprocess-mypy meta-test asserts `mypy --strict` returns non-zero on a generated swap module, by-name covering every Phase-3 newtype.
- **One block-tier API drift**: arch pseudo-code shows `PackageId.parse(s: str) -> Result[PackageId, ParseError]` and `BranchName.parse(s: str) -> Result[BranchName, ParseError]` (classmethod-on-type), but `PackageId` / `BranchName` are `NewType` (functions returning identity-typed `str` — no classmethods possible). Story chose free-function `parse_<x>` shape, which is the only viable implementation; the arch pseudo-code is an artifact of mixing Pydantic-class smart constructors (`PluginScope.parse`) and NewType smart constructors in one example block. Closure: documented in Notes-for-implementer with explicit rationale; AC added forbidding any module-level reassignment that would smuggle a Pydantic class into a NewType slot.
- **One block-tier coverage gap**: TDD plan covers 8 of 14 parsers with parametrized happy/sad cases; 6 (PluginId, RecipeId, TransformId, EventId, PrimitiveName, TransformKind) have no enumerated rejection test. Closure: AC pinning every parser to a happy-path + ≥ 1 rejection case, plus a parametrized "every parser is total" property test.
- **Family-symmetric harden-tier closures** the Phase-2 S1-05 validation already established (pairwise distinctness over the closed family; `NewType.__name__` pinning; exact-set `__all__`; identity-passthrough through `__init__`; `isinstance(x, ID)` runtime `TypeError` pin; AST source-scan over regex; module-purity invariant on `parsers.py` / `errors.py`).
- **Property-based test opportunities** (Hypothesis) — every parser is a total function from `str` (or `int` for `AttemptNumber`) to `Result`; never raises. This invariant is mutation-resistant and inexpensive to express.

Stage 3 research skipped — every closure is answerable from arch + ADR-0010 + production ADR-0033 + Phase-2 S1-05 precedent + verified repo state (`src/codegenie/result.py` exists; no `WorkflowId`/`TransformId`/`AttemptNumber` in `src/`).

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim):** Extend `codegenie.types.identifiers` with the 14 Phase-3 newtypes and pair each one with a smart-constructor wrapper returning `Result[T, ParseError]`, so every later Step 1 story (and every downstream Phase 3 module) imports its typed primitives from one canonical home.
- **Non-goals (from Out-of-scope):** `PluginScope` parsing (S1-02); `AttemptSummary` / `ApplyContext` Pydantic models (S1-04); tagged-union outcomes (S1-03); the "no raw `str` for domain IDs" fence test (S1-05); JSON/pickle helpers.

### ACs as written (verbatim, numbered)

- AC-1: 14 newtypes exported from `identifiers.py` (13 over `str`, `AttemptNumber` over `int`)
- AC-2: `src/codegenie/types/result.py` with `Ok`/`Err`/`Result`/`ParseError`
- AC-3: `src/codegenie/types/parsers.py` with 14 smart constructors
- AC-4: tests covering round-trip + rejection + cross-newtype substitution = mypy error
- AC-5: `mypy --strict src/codegenie/types/` clean
- AC-6: `ruff check`, `ruff format --check` clean on touched files
- AC-7: `__all__` sorted; docstring per newtype names ADR + consumer
- AC-8: TDD plan's red test exists, committed, green

### Goal-to-AC trace

- AC-1 → goal: YES (catalog landing).
- AC-2 → goal: WEAK — assumes a *new* `Result` module; the canonical home `codegenie.result` already exists. Trace breaks the moment a reader runs `grep -rn "class Ok" src/`.
- AC-3 → goal: YES (smart-constructor home) — but partial (only 8 of 14 parsers enumerated in TDD plan).
- AC-4 → goal: PARTIAL — round-trip + rejection cover behavior; "cross-newtype = mypy error" gestures at intent but the cited test pattern (commented-out lines) does not enforce it under CI.
- AC-5 → goal: YES (strict-typing bar).
- AC-6 → goal: YES (style bar).
- AC-7 → goal: YES (convention enforcement).
- AC-8 → goal: meta-AC; redundant under TDD plan section.

### Phase / arch constraints

- ADR-0010 §Decision (3): names the 14 newtypes; smart-constructor convention; `BranchName.parse` regex.
- ADR-0010 §Consequences: `src/codegenie/types/identifiers.py` centralizes every newtype; fence test `tests/fence/test_no_raw_str_for_domain_ids.py` is a *follow-up* — out of scope here per story.
- ADR-0001 §Consequences: `_validate_stage6` consumers (Phase 5 `GateRunner`) expect `WorkflowId`/`TransformId`/`AttemptNumber` already typed by the time `ApplyContext` lands in S1-04.
- Phase 5 S1-04 (`docs/phases/05-sandbox-trust-gates/stories/S1-04-gates-contract-abc-models.md` line 41) reads `GateContext.prior_attempts: list[AttemptSummary] = []`. Phase 3 S1-04 ships `AttemptSummary`; this story (S1-01) ships `AttemptNumber`, which `AttemptSummary.attempt: AttemptNumber` references.
- Production ADR-0033 §1, §3: newtype-per-domain-primitive is the binding discipline; primitive-obsession is a review-blocker.
- CLAUDE.md §"Match the existing convention": `IndexId`/`SkillId`/`TaskClassId`/`IndexName`/`ProbeId`/`Language`/`ConventionId` are the established convention shape (mirror exactly).
- CLAUDE.md §"No LLM anywhere in the gather pipeline" + `import-linter` fence — `types/` is kernel; must remain side-effect-free.

### Phase 3 Step-1 exit criteria the story must contribute to

(from `High-level-impl.md §Step 1 Done criteria`)
- `pytest tests/unit/types/test_identifiers_phase3.py` covers smart-constructor round-trip + parse-error variant for **every** newtype.
- `mypy --strict src/codegenie/plugins src/codegenie/transforms` clean (downstream — needs the 14 newtypes in place).

### Sibling-family lineage (Design-Patterns critic)

- **This story is the 2nd kernel-tier newtype expansion** of `codegenie.types.identifiers` (after Phase 2 S1-05 which landed the first five names + the `PackageManager` re-export).
- **Prior validation framings carried forward (Phase 2 S1-05 report):** pairwise distinctness over a closed family; exact-set `__all__`; AST source-scan over regex; module-purity invariant; `NewType.__name__` pinning; identity-passthrough through `__init__`; subprocess-mypy executable negative test (NOT commented-out lines); `isinstance(x, ID)` runtime `TypeError` pin; `type(val) is str` strict identity (over `isinstance(val, str)` which permits `str` subclasses).
- **Rule-of-three for "regex parser" kernel:** REACHED. `parse_cve_id`, `parse_branch_name`, `parse_signal_kind`, `parse_primitive_name`, `parse_transform_kind` are five regex-shaped parsers. A private `_regex_parse(name, rx, value, *, max_len) -> Result[str, ParseError]` helper is the right shape (NOT a registry / decorator — that is pattern soup at this scale).
- **Rule-of-three for `Result` module:** ALREADY-EXTRACTED. `codegenie.result` is the canonical home (Phase-2 S1-04). Forking it is a Rule-7 violation.

### Open ambiguities resolved before Stage 2

- **`Result` location.** Verified: `src/codegenie/result.py` exists (lines 40 `class Ok`, 60 `class Err`, 80 `Result = Annotated[Ok[T] | Err[E], Field(discriminator="kind")]`). Story's `src/codegenie/types/result.py` would be a fork. Resolution: consume `codegenie.result`; ship only `ParseError` in `src/codegenie/types/errors.py`.
- **`AttemptNumber` upper bound.** Production ADR-0014 establishes 3 retries default per gate; Phase 5 may run more. `parse_attempt_number` enforces `> 0` only — no upper cap (open-registry intent matches Phase 5 retry budget being policy, not type-level).
- **`PackageId` version grammar.** Pinned exact semver only (`^\d+\.\d+\.\d+(?:-[\w.+-]+)?$`); ranges (`^4.0.0`, `~4.0.0`, `>=4.0.0`) are rejected. Phase 3 vuln-remediation operates on a *fixed* version — ranges have no lookup answer.
- **`BlobDigest` shape.** "Hex 64 chars" is intentionally algorithm-agnostic at the type level; both SHA-256 and BLAKE3 32-byte fit. Documented in Notes.
- **`RegistryUrl` shape.** `https://` scheme required; reject userinfo (`user@host`); reject query/fragment; max length 2048; lowercase scheme; ASCII-only host (no IDN until a real use case demands it).
- **Free-function vs classmethod API.** Story chooses `parse_<x>(s)`; arch pseudo-code shows `Cls.parse(s)`. `NewType` cannot host classmethods. Resolution: free functions are the only viable shape; document in Notes.

### Adjacent test / production code

- `tests/unit/types/test_identifiers.py` — established round-trip + distinctness shape (8 tests for 5 newtypes).
- `tests/unit/types/test_identifiers_typecheck.py` — the broken pattern (commented-out swap lines). S1-05 validation flagged this as a block-tier gap; the executor merged the test as-shipped. **Do not repeat the mistake.**
- `src/codegenie/result.py` — canonical `Ok`/`Err`/`Result`. Reuse.
- `src/codegenie/tccm/loader.py` line 98 — first consumer of `Result` in the repo: `def load(self, path: Path) -> Result[TCCM, TCCMLoadError]:` — pattern is `(success-type, error-type)`; mirror.

## Stage 2 — critic reports

### Coverage critic (verdict: COVERAGE-HARDEN — 9 findings, 2 block)

| ID | Sev | Finding | Closure |
|---|---|---|---|
| C-F1 | **block** | TDD plan enumerates parametrized rejection cases for only 8 of 14 parsers (`parse_workflow_id`, `parse_cve_id`, `parse_branch_name`, `parse_blob_digest`, `parse_registry_url`, `parse_attempt_number`, `parse_signal_kind`, `parse_package_id`). Six parsers — `parse_plugin_id`, `parse_recipe_id`, `parse_transform_id`, `parse_event_id`, `parse_primitive_name`, `parse_transform_kind` — have no enumerated rejection case. A wrong implementation that always returns `Ok` for these six would pass. | New AC requires *every* parser to have ≥ 1 happy case + ≥ 1 rejection case + 1 total-function property test (Hypothesis). |
| C-F2 | **block** | AC-4's "cross-newtype substitution is a mypy error" cites `test_identifiers_typecheck.py` whose swap lines are commented-out prose (Phase-2 S1-05 §F5 verdict). No CI step verifies the assertion. | New AC adds executable subprocess-mypy meta-test (`test_identifiers_phase3_mypy_negative.py`) that writes a temp swap module, subprocess-invokes `mypy --strict`, asserts non-zero exit + expected error substring. Parametrized over every Phase-3 newtype (14 swap cases). |
| C-F3 | harden | `__name__` pinning unasserted — `WorkflowId = NewType("Workflow_Id", str)` typo would not be caught by any AC; mypy errors and stack traces would silently mislabel. | New AC: `getattr(ids, name).__name__ == name` for all 14. |
| C-F4 | harden | Pairwise distinctness unasserted — `WorkflowId = TransformId = NewType("Id", str)` (one NewType, two names) silently slips past — both `__supertype__ is str`. | New AC: pairwise `is not` over all 14 newtypes (91 pairs; small parametrized loop). |
| C-F5 | harden | `__all__` checked with implicit `⊇`; stowaway exports (e.g., leaked `re`, `NewType`) slip past. | New AC: `set(ids.__all__) == EXPECTED_PHASE2_NAMES \| EXPECTED_PHASE3_NAMES`, sorted equality. |
| C-F6 | harden | Identity-passthrough through `codegenie.types.__init__` unasserted for the 14 new names. | New AC: `from codegenie.types import WorkflowId; from codegenie.types.identifiers import WorkflowId as WW; assert WorkflowId is WW` (parametrized). |
| C-F7 | harden | `isinstance(x, IndexId)` runtime `TypeError` not pinned for the new types (NewType is callable, not a class; misuse is a real footgun). | New AC: `pytest.raises(TypeError)` on `isinstance("x", WorkflowId)` for each new type. |
| C-F8 | harden | NFKC normalization + ASCII-only check for `parse_package_id`/`parse_branch_name` mentioned in Refactor step only — not a hard AC. A wrong implementation that accepts zero-width-joiner or NFKC-equivalent homoglyphs passes. | New AC: NFKC-normalize + reject any byte > 0x7F; parametrized adversarial inputs (NUL, U+200B, U+FEFF, full-width `．`). |
| C-F9 | nit | AC-7 ("docstring per newtype names ADR + consumer") is not machine-verifiable; a missing docstring slips past. | Add AST-based test: `ast.get_docstring()` or a module-level `_NEWTYPE_DOCS: dict[str, str]` registry with one entry per newtype, asserted non-empty. |

### Test-Quality critic (verdict: TESTS-HARDEN — 8 findings, 2 block; mutation analysis)

Mutation table (selected):

| # | Wrong impl | Caught by original draft? | Closure |
|---|---|---|---|
| M1 | `parse_plugin_id = parse_recipe_id = lambda s: Ok(PluginId(s))` (no validation, six parsers always succeed) | No — TDD plan has no rejection case for these six | C-F1 closure: per-parser rejection AC |
| M2 | `def parse_attempt_number(n): return Ok(AttemptNumber(n))` (no `> 0` check) | Partial — story has `test_attempt_number_rejects_zero` but not `<0` or `int.__add__` boundary; mutation `if n >= 0` passes test | New AC parametrized: `[-1, 0, -2**31, "1" (str-not-int)]` all → `Err` |
| M3 | `parse_cve_id` accepts `"cve-2024-21501"` (lowercase) | Yes — `test_cve_id_rejects_malformed` covers | Keep |
| M4 | `parse_branch_name` accepts U+200B (zero-width space) | No — original tests do not cover | C-F8 closure |
| M5 | `parse_cve_id` accepts `"CVE-2024-1234567890123"` (very long suffix) | Partial — regex `\d{4,}` admits unbounded; mutation passes | New AC: length cap (≤ 32 chars total per MITRE practical bound) |
| M6 | `parse_blob_digest` accepts uppercase hex (`"AB...EF"`) | No | New AC: `^[0-9a-f]{64}$` (lowercase-only) |
| M7 | `parse_registry_url` accepts `http://attacker.com` (wrong scheme) | No — story says `https://` but no test enumerated | New AC: parametrized rejection of `http`, `ftp`, `javascript:`, missing scheme |
| M8 | `parse_registry_url` accepts `https://user:pass@registry.npmjs.org` (userinfo smuggling) | No | New AC |
| M9 | `parse_registry_url` accepts `https://registry.npmjs.org/?param=1` (query/fragment) | No | New AC |
| M10 | `parse_signal_kind` accepts `"BadKind"` (uppercase) | No — story says regex but no test enumerated | New AC: per ADR `^[a-z][a-z0-9_]*$` |
| M11 | `parse_package_id` accepts `"lodash@4.0"` (incomplete semver) | No | New AC: full semver `\d+\.\d+\.\d+` (pinned) |
| M12 | `parse_package_id` accepts `"lodash@^4.0.0"` (range) | No | New AC: explicit range rejection |
| M13 | NewType swap (`WorkflowId` ↔ `TransformId` at a call site) — commented-out test does not catch | No — block-tier C-F2 | Subprocess mypy meta-test |
| M14 | Forget to discriminate `Ok | Err` via `kind` field, lose Pydantic union dispatch | Partial — round-trip catches if test uses `Ok` literal class; weaker if test only checks `.value` | Keep `isinstance(r, Ok)` assertion shape (story already does) |

Property-based test opportunities (Hypothesis):

- **Totality:** for any `s: str` (Hypothesis `text()`), every `parse_<x>(s)` returns `Ok | Err` and never raises. Property test parametrized over the 13 str-parsers.
- **Determinism:** `parse_<x>(s) == parse_<x>(s)` for any `s`. (Cheap; catches non-deterministic regex-cache bugs or accidental Pydantic mutability.)
- **Round-trip identity:** for any `s` that satisfies the parser's regex, `parse_<x>(s).unwrap() == <X>(s)`. Hypothesis `from_regex(parser_rx)` strategy.

### Consistency critic (verdict: CONSISTENCY-RESCUE-TO-HARDEN — 5 findings, 1 block, 3 harden, 1 nit)

| ID | Sev | Finding |
|---|---|---|
| K-F1 | **block** | Story prescribes creating `src/codegenie/types/result.py` with `Ok`/`Err`/`Result`/`ParseError`. Verified: `src/codegenie/result.py` already exists (Phase-2 S1-04; consumed by `tccm/loader.py:98`, `skills/loader.py:230,300,392`, `conventions/loader.py:272`). Creating a second `Result` module is a Rule-7 violation ("Surface conflicts, don't average them") and the story's own Notes-for-implementer hedge ("If Phase 5 has already shipped a different `Result` shape, surface it and ask"). Closure: AC-2 split — `Ok`/`Err`/`Result` consumed from `codegenie.result`; new module `src/codegenie/types/errors.py` ships *only* `ParseError`. |
| K-F2 | harden | Arch (`phase-arch-design.md §Data model`) shows `PackageId.parse(s)` / `BranchName.parse(s)` as classmethod-on-type. NewType cannot host classmethods. Story chose free-function `parse_<x>(s)`. Surface the contradiction in Notes-for-implementer so a future reader does not "fix" the story by introducing Pydantic class wrappers that diverge from the kernel-tier discipline. |
| K-F3 | harden | Phase-2 S1-05 ships `Language = NewType("Language", str)`. ADR-0010 names `Language` as already-typed; story does not list `Language`. Confirm: `Language` is not in the 14 (it landed in S1-05, before Phase 3). Story is correct; add explicit note to disambiguate. |
| K-F4 | harden | `Language` discriminator is missing for `Result[T, ParseError]` — `codegenie.result.Result` uses `Annotated[Ok[T] \| Err[E], Field(discriminator="kind")]`. New consumer parsers must instantiate `Ok(value=...)` / `Err(error=...)` (not positional), or Pydantic discrimination is brittle. Mirror the `tccm/loader.py` instantiation idiom. |
| K-F5 | nit | `AttemptNumber = NewType("AttemptNumber", int)` — `int` is the *only* non-`str` newtype. Module docstring + `__all__` ordering should call this out so a future scanner doesn't mass-rewrite `NewType("...", str)`. |

### Design-Patterns critic (verdict: PATTERNS-HARDEN — 5 findings, 4 harden, 1 rejected)

| ID | Sev | Pattern | Finding |
|---|---|---|---|
| D-F1 | harden | **Smart constructor — kernel extraction (rule of three)** | Five regex parsers (`parse_cve_id`, `parse_branch_name`, `parse_signal_kind`, `parse_primitive_name`, `parse_transform_kind`) share the shape: `match regex → length cap → Ok(<X>(s)) \| Err(ParseError(msg, s))`. Private helper `_regex_parser(rx: re.Pattern, *, max_len: int, name: str)` removes the repetition. Express as Notes-for-implementer **and** an observable AC ("no parser duplicates the match-then-wrap pattern; the helper is module-private"). |
| D-F2 | harden | **Functional core / imperative shell** | `errors.py` and `parsers.py` must remain pure (`__future__`, `typing`, `re`, `pydantic`, `codegenie.result`, `codegenie.types.identifiers` only — no logger, no fs, no sibling-package imports). AST source-scan test mirrors the S1-05 `_module_purity` precedent. |
| D-F3 | harden | **Make illegal states unrepresentable** | `ParseError` is the *only* thing the parsers ever return in `Err`. Closing the variant means a frozen Pydantic model with `extra="forbid"`, `model_config` and two fields (`message: str`, `value: str`). AC pins this shape. |
| D-F4 | harden | **Newtype as private constructor / docstring discipline** | Each NewType's docstring names (a) the ADR (always ADR-0010), (b) the immediate Phase-3 consumer story (e.g., `WorkflowId` → S1-04 `ApplyContext` + S6-04 `RemediationOrchestrator`), (c) the *shape* of the value (BLAKE3 hex, ULID, semver-pinned package, etc.). Asserted by a module-level `_NEWTYPE_REGISTRY: Final[Mapping[str, str]]` so future readers + AST tests can verify. |
| D-F5 | rejected | **Decorator-based parser registry (`@register_parser(Newtype)`)** | Rejected under Rule 2 — 14 parsers in a flat file is well below the abstraction threshold; a registry adds indirection without extension benefit (parsers are not user-extensible; they are kernel-tier). |

## Stage 3 — Researcher

**Skipped.** No `NEEDS RESEARCH` findings — every closure is answerable from arch + ADR-0010 + production ADR-0033 + Phase-2 S1-05 precedent + verified repo state.

## Stage 4 — Synthesizer + edits applied

### Conflict resolution

- **K-F1 ↔ Story AC-2**: Consistency wins — Result is consumed from `codegenie.result`; only `ParseError` ships new. Story rewritten.
- **K-F2 ↔ Arch pseudo-code**: Free-function shape wins (only viable for NewType); arch pseudo-code documented as illustrative-not-literal in Notes.
- **C-F2 ↔ Existing test_identifiers_typecheck.py**: Subprocess meta-test wins; the existing commented-out pattern is documented as known-broken (already remediated for Phase 2 in S1-05 follow-up).
- **D-F5 (decorator registry) rejected** under Rule 2 + CLAUDE.md "three similar lines is better than premature abstraction".

### Edits applied to the story

1. **AC-2 rewritten**: `Ok`/`Err`/`Result` consumed from `codegenie.result`; new `src/codegenie/types/errors.py` ships `ParseError` only (frozen Pydantic, `extra="forbid"`, two fields).
2. **AC-3 strengthened**: per-parser happy-case + ≥ 1 rejection case for *every* parser; explicit regex/shape per parser pinned in AC text.
3. **AC-4 split** into AC-4a (round-trip), AC-4b (rejection), AC-4c (subprocess-mypy negative test as the executable assertion).
4. **New ACs added**: AC-9 (`__name__` pinning), AC-10 (pairwise distinctness), AC-11 (exact-set `__all__`), AC-12 (identity-passthrough through `__init__`), AC-13 (`isinstance` runtime `TypeError`), AC-14 (NFKC + ASCII-only adversarial), AC-15 (`_NEWTYPE_REGISTRY` docstring discipline + AST verification), AC-16 (module-purity AST scan on `errors.py` + `parsers.py`), AC-17 (Hypothesis totality + determinism property tests), AC-18 (private `_regex_parser` helper consumed by ≥ 3 callers; no duplicate match-then-wrap).
5. **TDD plan expanded**: parametrized rejection table covering all 14 parsers; explicit mutation kill-list (M1–M14 above) mapped to test names; subprocess-mypy negative test scaffold included; Hypothesis property tests with `from_regex` strategy.
6. **Files-to-touch updated**: removed `src/codegenie/types/result.py` (Rule 7); added `src/codegenie/types/errors.py`; added `tests/unit/types/test_identifiers_phase3_mypy_negative.py` (subprocess); added `tests/unit/types/test_parsers_properties.py` (Hypothesis).
7. **Notes-for-implementer expanded**: explicit "DO NOT create `types/result.py`" warning with file path; classmethod-vs-free-function rationale; `Ok(value=...)` / `Err(error=...)` instantiation idiom; helper rule-of-three rationale; AttemptNumber-is-int callout.
8. **Validation notes block** appended after the header.

### Verdict

**HARDENED.** Story now has 18 individually-verifiable ACs (was 8), one executable subprocess-mypy meta-test (was a comment), full parser-coverage rejection matrix (was 8/14), adversarial NFKC + URL-shape edge cases, Hypothesis totality/determinism properties, Rule-7 conflict resolved (no `Result` fork), and explicit kernel-extraction AC at rule-of-three threshold. Ready for `phase-story-executor`.
