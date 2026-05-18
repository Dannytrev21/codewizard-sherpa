# Validation report — S1-02 PluginScope sum type + parser

**Story:** [`../S1-02-plugin-scope-sum-type.md`](../S1-02-plugin-scope-sum-type.md)
**Validated:** 2026-05-18
**Validator:** phase-story-validator (scheduled task: `story-validation-corrector`)
**Verdict:** **HARDENED**

## Summary

The story lands the load-bearing `PluginScope` value type that S2-01 (registry kernel) keys on, S2-02 (YAML manifest loader) parses through, and S2-04 (resolver) sorts by. ADR-0010 §Decision §1 mandates a verbatim `Concrete | Wildcard` sum type with `@dataclass(frozen=True, slots=True)` — making this the *first* dataclass-variant + `match` pattern in `codegenie.plugins.*` (precedent established by Phase-2 S1-01 `IndexFreshness` at `src/codegenie/indices/freshness.py`). Validation found:

- **Two block-tier issues** the writer carried forward from a pre-S1-01 draft of the surrounding type vocabulary:
  - TDD code imported `from codegenie.types.result import Ok, Err` — but that module **does not exist** and S1-01 (HARDENED) explicitly forbids creating it. Canonical home is `codegenie.result` (Phase-2 S1-04); `ParseError` lives at `codegenie.types.errors`. Rule-7 ("Surface conflicts, don't average them") would have been violated had the executor consumed the draft verbatim.
  - `Err(ParseError(value=s, ...))` positional/`...` instantiation was ambiguous — S1-01 pins `ParseError(message: str, value: str)` with `extra="forbid"` and keyword-instantiation discipline (the `Result` discriminator on `kind` requires it). Fixed.
- **Two block-tier coverage gaps** load-bearing for downstream stories that were only one-liner Refactor asides:
  - **Round-trip `parse(str(scope)).unwrap() == scope`** — promoted from "one extra Hypothesis property is cheap" (Refactor §3) to AC-10 + AC-11 + the `test_parse_str_round_trip` property. ADR-0010 §Decision §1 says "YAML still writes `*` and `<concrete>` strings via the smart constructor"; without round-trip enforcement, S2-02's YAML manifest loader would break silently on the first serialization-then-deserialization in CI fixtures.
  - **`__str__` method** — promoted from "needed by S2-03 loader error messages" (Refactor §2) to AC-10. Without an explicit AC, the executor's Validator pass would not catch a missing `__str__` (the default `repr(self)` works syntactically but breaks the YAML round-trip).
- **Parametrized adversarial rejection matrix (R1–R17)** — original AC named three vague categories ("wrong dim count, empty dim, illegal chars"). Hardened table enumerates 17 specific mutations (empty input, leading/middle/trailing empty dim, control chars, whitespace, uppercase, dot, slash, NUL, U+200B, full-width chars, per-dim length cap, parse-does-not-NFKC-normalize pin). Each row in the table kills a named mutation in the kill-list.
- **`assert_never` exhaustiveness** — original Notes-for-implementer mentioned it; story had no observable AC. Promoted to AC-14 + AST-walk test (`test_scope_match_blocks_have_assert_never`). Mirrors the S1-01 precedent of replacing "ought to" with "asserted by AST". Without this, a future `Negation`/`Range` `ScopeDim` variant would silently misbehave instead of breaking the build.
- **Hashability + equality** — Notes-for-implementer asserted "scope instances are hashable (registry keys)" but no AC. S2-01 keys plugin registry on `PluginScope` — if `__hash__` is unstable across instances of equal scopes, the registry silently leaks duplicate entries. Pinned via AC-12 + AC-13 + Hypothesis property `test_hash_stability`.
- **Specificity wording fix** — story called specificity a "partial order"; it's `int`-valued over `{0,1,2,3}` — a *total* order. ADR-0003 §Decision step 2 resolver sort key requires total order. Pinned via AC-9 (`*--*--*` is 0, `a--b--c` is 3, strictly increasing along the chain).
- **Hypothesis strategy regex aligned** — original draft used `^[a-z][a-z0-9_-]{0,16}$` (forces leading lowercase letter, max-len 17). Parse regex per the implementation outline is `[a-z0-9_-]+` (any leading char, no length cap stated). Strategy widened to `^[a-z0-9_-]{1,64}$` so the round-trip property actually covers the parse-admissible space.
- **Module-purity AST scan** — promoted to AC-21 mirroring Phase-2 S1-04 (`result.py`) and Phase-2 S1-01 (`freshness.py`) precedents. `scope.py` is kernel — imports limited to `{__future__, dataclasses, re, typing, codegenie.result, codegenie.types.errors}`.
- **Reference path correction** — original Notes pointed at `src/codegenie/probes/layer_b/` for "right `match` + `assert_never` pattern". But Phase-2 probes use *Pydantic* discriminated unions, not dataclass variants. The actual precedent is `src/codegenie/indices/freshness.py` (`IndexFreshness = Fresh | Stale`).

Stage 3 research **skipped** — every closure is answerable from ADR-0010 + ADR-0003 + S1-01 validation precedent + verified repo state (`src/codegenie/result.py` exists; `src/codegenie/plugins/` does not exist yet; S1-01 is HARDENED but not yet GREEN).

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim):** Land `src/codegenie/plugins/scope.py` with `Concrete`, `Wildcard`, `ScopeDim`, `PluginScope` exactly as ADR-0010 §Decision §1 specifies, with `PluginScope.parse` as a smart constructor returning `Result[PluginScope, ParseError]` and a Hypothesis-tested `matches`/`specificity` algebra.
- **Non-goals (from Out-of-scope):** `PluginRegistry` / `@register_plugin` / resolver (S2-01 / S2-04); `PluginManifest` YAML loader (S2-02); `extends`-chain walker (S2-04); `ConcreteResolution | UniversalFallbackResolution` sum (S2-04 lives in `resolution.py`); newtype wrapping inside `Concrete.value` (ADR-0010 §Decision §1 keeps `Concrete.value: str` so `PluginScope` is task-class-agnostic).

### Goal-to-AC trace (pre-hardening)

- AC-1 (package marker) → goal: YES (namespace exists for S1-05 import-linter contract)
- AC-2 (four exports, exact bytes per ADR-0010 §1) → goal: YES
- AC-3 (parse smart constructor) → goal: PARTIAL — wrong-module imports + `Err(ParseError(value=s, ...))` ambiguity + thin rejection cases
- AC-4 (matches) → goal: PARTIAL — `assert_never` mentioned but not asserted
- AC-5 (specificity) → goal: PARTIAL — `assert_never` mentioned but not asserted; "partial order" wording wrong
- AC-6 (unit tests "≥4 deliberate malformed inputs") → goal: WEAK — under-specified; no mutation kill-list
- AC-7 / AC-8 (Hypothesis properties) → goal: YES (good shape; strategy regex slightly off from parse regex)
- AC-9 / AC-10 / AC-11 (mypy / ruff / red test) → goal: bar-ACs

### Phase / arch constraints

- **ADR-0010 §Decision §1** — names the exact shape `@dataclass(frozen=True, slots=True)` for `Concrete`/`Wildcard`; `ScopeDim: TypeAlias = Concrete | Wildcard`; `PluginScope.parse` smart constructor returning `Result[PluginScope, ParseError]`; YAML round-trip via `*`/`<concrete>` strings.
- **ADR-0010 §Pattern fit** — names "Make illegal states unrepresentable" as the failure mode: `NewType("Language", str) | Literal["*"]` collapses to `str` at runtime; the sum type forbids this.
- **ADR-0003 §Decision step 2** — resolver sort key `(specificity desc, precedence desc, name asc)`. Specificity is a *total* order on `PluginScope`; the universal scope's `specificity() == 0` is load-bearing — it places the universal fallback last in sort order so it never matches before a concrete plugin.
- **ADR-0003 §Decision step 3** — universal fallback's id is `universal--*--*`; that's the `PluginScope.parse("*--*--*")` value. Loader startup check expects this to construct (ADR-0003 §Consequences).
- **CLAUDE.md "Extension by addition"** — adding a new task class / language / build system never edits `PluginScope`; new dims would (ADR-0003 §Tradeoffs known cost).
- **CLAUDE.md "No LLM anywhere in the gather pipeline" + `import-linter`** — `codegenie.plugins.scope` is kernel; module-purity invariant applies.

### Sibling-family lineage (Design-Patterns critic)

- **This story is the 1st story to ship under `codegenie.plugins.*`.** Namespace doesn't exist yet (verified: `ls src/codegenie/plugins/` errored).
- **This is the 1st dataclass-variant + `match` precedent in `codegenie.plugins.*`.** Closest repo-wide precedent: `src/codegenie/indices/freshness.py` (Phase-2 S1-01 `IndexFreshness = Fresh | Stale`). Phase-2 probes under `src/codegenie/probes/layer_b/` use Pydantic discriminated unions — *not* the precedent here.
- **Rule-of-three for dataclass-variant + `match` kernel:** NOT YET REACHED. Only `IndexFreshness` and (after this story) `ScopeDim` exist. S1-03 will add `RecipeOutcome` (4 variants) and `PluginResolution` (2 variants); after those land, the family will reach 4 instances and any kernel-extraction question becomes live. Not for this story.
- **Rule-of-three for `Result` smart-constructor convention:** ALREADY-REACHED in Phase 2 (S1-04 TCCM loader, S2-01 Skills loader, S2-02 Conventions loader); S1-01 extends to 14 newtype parsers; this story is the +1 user. Convention is solid.

### Open ambiguities resolved before Stage 2

- **Import location of `Result` / `Ok` / `Err`.** Verified: `src/codegenie/result.py` exists (lines 40 `class Ok`, 60 `class Err`, 80 `Result = Annotated[...]`). Story's `from codegenie.types.result import Ok, Err` is a fork. Resolution: `from codegenie.result import Ok, Err` + `from codegenie.types.errors import ParseError`. Same fix S1-01 applied.
- **Per-dim length cap.** Story is silent; `_DIM_PATTERN = ^[a-z0-9_-]+$` admits unbounded input. Verified ADR-0010 / ADR-0003 don't pin a cap. Resolution: 64 chars per dim (R16 in rejection table) — generous for real task class names ("vulnerability-remediation" is 26 chars; "chainguard-distroless-migration" is 31).
- **`matches` signature: `str` vs newtypes.** Arch §C3 line 507 shows `matches(*, task: TaskClass, language: Language, build: BuildSystem)`; story shows `str`. Per Out-of-scope §5: "PluginScope stays task-class-agnostic; call sites wrap with the right newtype." Resolution: `str` is correct (kernel stays generic); arch §C3 is illustrative-at-the-call-site. Documented in Notes-for-implementer.
- **`parse` NFKC normalization.** Story is silent. Per ADR-0010 §Pattern fit "make illegal states unrepresentable", normalization at parse-time could *hide* adversarial input (full-width digits, zero-width spaces). Resolution: `parse` does **not** normalize; rejects U+200B and full-width chars (R14, R15). Call sites normalize before calling if they want lenience.
- **Specificity wording: "partial" or "total" order?** ADR-0003 sort requires total. Story says "partial". Resolution: total (it's `int`-valued).

### Adjacent test / production code

- `src/codegenie/result.py` (Phase-2 S1-04) — canonical `Ok`/`Err`/`Result` home. Reuse.
- `src/codegenie/indices/freshness.py` (Phase-2 S1-01) — closest precedent for `@dataclass(frozen=True, slots=True)` sum-type with `match` + `assert_never`. **Pattern to copy.**
- `tests/unit/indices/test_freshness.py` — adjacent test shape for dataclass-variant tests.
- `src/codegenie/tccm/loader.py:98` — first `Result` consumer; `Ok(value=...)` / `Err(error=...)` keyword-instantiation idiom precedent.

### Phase 3 Step-1 exit criteria the story must contribute to

(from `High-level-impl.md §Step 1 Done criteria`)
- `pytest tests/unit/plugins/test_scope.py` passes with the matches/specificity algebra covered.
- `mypy --strict src/codegenie/plugins` clean — *requires* S1-01's newtype catalog AND S1-02's `PluginScope` together (downstream stories type-check against both).
- `PluginScope.parse("*--*--*")` constructs successfully — loader startup check (ADR-0003 §Consequences) depends on it.

## Stage 2 — critic reports

### Coverage critic (verdict: COVERAGE-HARDEN — 12 findings, 4 block, 7 harden, 1 nit)

| ID | Sev | Finding | Closure |
|---|---|---|---|
| C-F1 | **block** | AC-3 rejection cases were vague ("wrong dim count, empty dim, illegal chars per dim"); only 5 examples in the parametrize. A wrong implementation that accepts uppercase, whitespace, or unicode silently passes. | Parametrized rejection matrix R1–R17 (AC-6) covering empty input, leading/middle/trailing empty dim, control chars, whitespace, uppercase, dot, slash, NUL, U+200B, full-width chars, per-dim length cap, universal-with-trailing-empty edge. |
| C-F2 | **block** | Round-trip invariant `PluginScope.parse(str(scope)).value == scope` mentioned only in Refactor as "one extra Hypothesis property is cheap". Without an AC, the executor's Validator pass cannot fail on a broken `__str__`. Load-bearing for ADR-0010 §1 YAML round-trip and S2-02 manifest loader. | Promoted to AC-10 (`__str__` canonical form) + AC-11 (`parse(str(scope)) == scope`) + Hypothesis property `test_parse_str_round_trip`. |
| C-F3 | **block** | `__str__` is named in Refactor "needed by S2-03 loader error messages" but is not an AC. The executor's "minimum that turns every assertion green" Green step would not add it. S2-03 then fails at integration. | Promoted to AC-10. |
| C-F4 | **block** | `assert_never` exhaustiveness arm in `match` blocks was Refactor advice + Notes hint; no AC. A wrong implementation without the arm would compile, run, and silently misbehave when a future `Negation`/`Range` variant ships. | AC-14 + AST-walk test `test_scope_match_blocks_have_assert_never`. |
| C-F5 | harden | Hashability claimed in Notes ("scope instances are hashable (registry keys)") but not asserted. S2-01 registry will key on `PluginScope`; unstable hash → silent registry corruption. | AC-12 + AC-13 + Hypothesis `test_hash_stability` + concrete `test_pluginscope_as_dict_key`. |
| C-F6 | harden | Equality semantics for `Concrete` / `Wildcard` not pinned (default frozen-dataclass `__eq__` is correct but unverified). | AC-12 + `test_concrete_equality` + `test_wildcard_hash_stable`. |
| C-F7 | harden | No per-dim length cap. `Concrete("a" * 1000000)` constructs and `parse` admits — degenerate-input bloat. | AC-5 + R16 in rejection table (cap 64). |
| C-F8 | harden | AC-8 asserts `specificity ∈ {0,1,2,3}` but does not assert monotonicity required for ADR-0003 sort: `(C,C,C) > (C,C,W) > (C,W,W) > (W,W,W)`. A wrong implementation `specificity = lambda: 1 if all_concrete else 0` would pass the property test (it satisfies `expected = sum(...)` only by coincidence per case). Actually: property test would catch — but the *resolver-sort* invariant should be a named assertion. | AC-9 + `test_specificity_total_order_for_resolver_sort` with 4 concrete-count cases. |
| C-F9 | harden | Universal scope identity unasserted: `PluginScope.parse("*--*--*").unwrap().specificity() == 0` is implicit. ADR-0003 §Decision step 3 needs this. | Included in AC-9 + `test_parse_universal_wildcard_specificity_is_zero`. |
| C-F10 | harden | Parse-totality property (never raises) not asserted. A `re.error` from an unusual unicode input would crash the resolver loader. | AC-18 + `test_parse_totality` Hypothesis property. |
| C-F11 | harden | Parse determinism not asserted (catches non-deterministic regex-cache bugs, hidden state). | AC-19 + `test_parse_determinism`. |
| C-F12 | nit | AC-8's "partial order" wording is wrong — `int`-valued specificity is total. ADR-0003 sort needs total. | AC-9 + wording fix in Notes. |

### Test-Quality critic (verdict: TESTS-HARDEN — 20 mutations identified; 8 not killed by original draft)

Selected mutations not killed by original draft:

| # | Wrong impl | Caught by original? | Closure |
|---|---|---|---|
| M2 | `parse("a----b")` silently coerces middle empty to Wildcard | Yes (`a----b` is in original parametrize) | Keep + extend |
| M3 | `parse` accepts uppercase `"A--b--c"` | No — original parametrize has no uppercase case | R10 |
| M4 | `parse` accepts `"a.b--c--d"` (dot) or `"a/b--c--d"` (slash) | No | R11, R12 |
| M5 | `parse` accepts `"a--b--c\x00"` (NUL), `"...​..."` (U+200B), `"...ｃ..."` (full-width) | No | R13, R14, R15 |
| M6 | `parse` accepts `"a" * 65 + "--b--c"` (degenerate length) | No — no length cap in original | R16 |
| M7 | `parse` strips leading/trailing whitespace | No — original strategy was to reject, but no test enumerated | R8, R9 |
| M8 | `parse` raises on adversarial input (`re.error` etc.) | No — original Hypothesis test asserts `Ok | Err` only on draws from `text()`; if `parse` raised, the property test would fail but not informatively | `test_parse_totality` with explicit `try/except` |
| M13 | `parse("*--*--*")` constructs `Concrete("*")` instead of `Wildcard()` | Yes (`test_parse_universal_wildcard` checks `specificity() == 0`) | Keep + `test_parse_universal_wildcard_specificity_is_zero` |
| M14 | `__str__` returns `repr(self)` | No — no `__str__` test in original | `test_str_round_trip[happy]`, `test_parse_str_round_trip` Hypothesis |
| M15 | `Concrete("x") != Concrete("x")` (impl overrides `__eq__`) | Yes (default frozen-dataclass works) but unasserted | `test_concrete_equality` |
| M16 | `Wildcard()` hashes differently across instances | No | `test_wildcard_hash_stable`, `test_hash_stability` Hypothesis |
| M17 | `match` block omits `assert_never` | No | AST scan `test_scope_match_blocks_have_assert_never` |
| M18 | `scope.py` imports `logging` or `pathlib` | No | AST scan `test_scope_module_purity` |
| M19 | `PluginScope(...)` not usable as dict key | No (S2-01 dependency) | `test_pluginscope_as_dict_key` |
| M20 | `Err(ParseError(...))` positional → Pydantic discriminator dispatches wrong on validation | No | `test_parse_err_uses_keyword_instantiation` |

Property-based opportunities surfaced:

- **Totality** (M8): `parse` over `st.text(max_size=200)` never raises.
- **Determinism**: `parse(s) == parse(s)` for all `s`.
- **Round-trip identity** (load-bearing for ADR-0010 §1 YAML): `parse(str(scope)).unwrap() == scope`.
- **Hash stability** (load-bearing for S2-01 registry): `hash(rebuild_from_dims) == hash(scope)`.
- **Matches algebra**: re-derive the answer in test body via independent `match` — not via `scope.matches` (tautology guard).
- **Specificity = concrete count**: `sum(isinstance(d, Concrete) for d in dims) == specificity()`.

Strategy alignment: original `scope_dims()` used `^[a-z][a-z0-9_-]{0,16}$` (max-len 17, leading lowercase letter). Parse regex per impl outline is `[a-z0-9_-]+` (any leading char, no length cap). Mismatch — property test missed the parse-admissible space. Widened to `^[a-z0-9_-]{1,64}$`.

### Consistency critic (verdict: CONSISTENCY-HARDEN — 7 findings, 2 block, 4 harden, 1 nit)

| ID | Sev | Finding |
|---|---|---|
| K-F1 | **block** | TDD code line 63: `from codegenie.types.result import Ok, Err`. Verified: `src/codegenie/types/result.py` **does not exist**; canonical `Result` home is `codegenie.result` (Phase-2 S1-04). S1-01 (HARDENED) explicitly forbids creating `codegenie.types.result` (Rule-7 violation). Closure: rewrite TDD imports to `from codegenie.result import Ok, Err` + `from codegenie.types.errors import ParseError`. |
| K-F2 | **block** | AC-3 says `Err(ParseError(value=s, ...))` — positional + ellipsis. S1-01 pins `ParseError(message: str, value: str)` with `extra="forbid"`; `Err` is a Pydantic discriminated union on `kind` requiring keyword instantiation (`Err(error=...)`). Closure: AC-4 + AC-6 pin `Err(error=ParseError(message=..., value=s))` keyword-only; `test_parse_err_uses_keyword_instantiation` asserts. |
| K-F3 | harden | Arch §C3 line 507 shows `matches(*, task: TaskClass, language: Language, build: BuildSystem)` (newtypes); story says `str`. Per ADR-0010 §1 "Concrete.value: str" and story Out-of-scope §5, the kernel stays task-class-agnostic. Resolution: `str` is correct; document in Notes that arch §C3's newtype params are illustrative-at-the-call-site. |
| K-F4 | harden | AC-8 names "partial order"; specificity is `int`-valued → **total** order. ADR-0003 §Decision step 2 requires total. Wording fix + AC-9 monotonicity assertion. |
| K-F5 | harden | Rejection parametrize uses `"a--b--BAD CHARS"` (space) but does not enumerate the actual `[^a-z0-9_-]` regex boundary — uppercase, dot, slash, unicode are silently uncovered. Closure: R10–R15 in rejection table. |
| K-F6 | harden | Notes-for-implementer points at `src/codegenie/probes/layer_b/` for "match + assert_never precedent" — but layer-B probes use Pydantic discriminated unions, not dataclass variants. Correct precedent is `src/codegenie/indices/freshness.py` (Phase-2 S1-01 `IndexFreshness = Fresh | Stale`). Notes updated. |
| K-F7 | nit | Implementation outline §3 says split on `--` "exactly two separators → 3 dims". For `"a----b"` the `--` substring appears twice consecutively; `"a----b".split("--")` returns `["a", "", "b"]` (3 dims, middle empty) — handled correctly by the per-dim regex (empty rejected). Wording clarified: "exactly 3 non-empty dims matching `_DIM_PATTERN`, separated by `--`". |

### Design-Patterns critic (verdict: PATTERNS-HARDEN — 8 findings, 5 harden, 2 documented-not-changed, 1 rejected)

| ID | Sev | Pattern | Finding |
|---|---|---|---|
| D-F1 | documented | **Make illegal states unrepresentable** | `Concrete.value: str` admits illegal strings at the dataclass level. `parse` is the only safe boundary. ADR-0010 §1 specifies this (no `__post_init__` validation). Decision: document the boundary in Notes-for-implementer; no validation injection. |
| D-F2 | harden | **Functional core / imperative shell** | `scope.py` must be pure-kernel (no logger, no fs, no sibling-package imports). Mirror Phase-2 S1-01/S1-04 module-purity AST scans. → AC-21 + `test_scope_module_purity`. |
| D-F3 | harden | **Smart constructor — keyword instantiation** | Same as K-F2: `Ok(value=...)` / `Err(error=PE(message=..., value=...))` keyword convention pinned by AC-4 + test. |
| D-F4 | harden | **Tagged union dispatch — exhaustiveness** | Every `match` over `ScopeDim` (and over `tuple[ScopeDim, ScopeDim, ScopeDim]`) must end with `case _: assert_never(...)`. → AC-14 + AST scan. |
| D-F5 | documented | **Open/Closed — scope-dim count** | ADR-0003 §Tradeoffs acknowledges that adding a 4th dim changes `specificity()` semantics across every existing plugin. Not Open/Closed at this seam. Documented in Notes — new dims require ADR amendment. |
| D-F6 | harden | **`__str__` round-trip serialization** | Load-bearing for YAML manifest writer (S2-02) + S2-03 error messages. → AC-10 + AC-11 + Hypothesis `test_parse_str_round_trip`. |
| D-F7 | harden | **Hashability for registry keys** | S2-01 keys plugin registry on `PluginScope`. Default frozen-dataclass `__hash__` works but is unasserted. → AC-12 + AC-13 + `test_pluginscope_as_dict_key`. |
| D-F8 | rejected | **Singleton `Wildcard`** (e.g., `WILDCARD: Final = Wildcard()`) | Rejected — ADR-0010 §Decision §1 specifies `@dataclass(frozen=True, slots=True)` exact bytes; multiple `Wildcard()` instances are intentional. Frozen+slots dataclasses with identical fields are `==` and hash-equal, so singleton optimization adds nothing for `Wildcard()` (zero fields). |

Kernel-extraction analysis (rule-of-three):

- **Dataclass-variant + `match` family:** 2 instances after this story (`IndexFreshness`, `ScopeDim`). NOT YET at three. S1-03's `RecipeOutcome` and `PluginResolution` will push to 4 — kernel extraction becomes live then, not here.
- **Smart-constructor + `Result` family:** Already at 3+ (TCCM, Skills, Conventions, 14 newtypes from S1-01). Convention is the kernel; this story consumes it cleanly.

## Stage 3 — Researcher

**Skipped.** No findings tagged `NEEDS RESEARCH`. Every closure is answerable from:

- ADR-0010 §Decision §1, §Pattern fit, §Consequences
- ADR-0003 §Decision steps 1–4, §Consequences (universal fallback id = `universal--*--*` requires `specificity() == 0`)
- S1-01 validation report (`_validation/S1-01-phase3-newtype-identifiers.md`) — established `codegenie.result` + `codegenie.types.errors` import convention, keyword-instantiation idiom, module-purity AST scan pattern, AST-walk for behavioral assertions
- Verified repo state (`src/codegenie/result.py` exists; `src/codegenie/types/errors.py` will exist after S1-01 GREEN; `src/codegenie/plugins/` does not exist yet; `src/codegenie/indices/freshness.py` is the dataclass-variant precedent)
- CLAUDE.md "No LLM in gather pipeline" + "Match the existing convention"

## Stage 4 — Synthesizer + edits applied

### Conflict resolution

- **K-F1 vs original TDD imports**: Consistency wins. `codegenie.result` + `codegenie.types.errors` imports replace the non-existent `codegenie.types.result` fork.
- **K-F2 vs original `Err(ParseError(value=s, ...))`**: Consistency wins. Keyword instantiation pinned.
- **K-F3 vs arch §C3 newtype-typed `matches` signature**: ADR-0010 §1 wins (kernel stays task-class-agnostic). Documented in Notes — arch §C3 newtype params are illustrative-at-the-call-site.
- **K-F4 / C-F12 "partial order" wording**: Consistency wins (ADR-0003 sort requires total).
- **D-F1 vs defense-in-depth `__post_init__`**: ADR-0010 §1 wins (no internal validation; smart constructor is the boundary). Documented in Notes.
- **D-F5 vs "Open/Closed for new dims"**: ADR-0003 §Tradeoffs wins (acknowledged closed set; documented).
- **D-F8 vs singleton optimization**: ADR-0010 §1 bytes-for-bytes wins.

### Edits applied to the story

1. **Status:** `Ready` → `HARDENED`.
2. **Depends on:** clarified — `ParseError` at `codegenie.types.errors`; `Result`/`Ok`/`Err` re-exported from `codegenie.result`.
3. **Validation notes block** added after the header.
4. **AC count: 11 → 22.** Organized by group: package shape (AC-1–3), smart constructor (AC-4–6), algebra (AC-7–9), serialization (AC-10–11), equality (AC-12–13), exhaustiveness (AC-14), Hypothesis (AC-15–20), purity + style (AC-21–22).
5. **Adversarial rejection matrix R1–R17** with one row per named mutation.
6. **TDD plan rewritten** with corrected imports, mutation kill-list (M1–M20), keyword-instantiation idiom, four new test files (rejection parametrize, exhaustiveness AST, module-purity AST, plus the main `test_scope.py`).
7. **`__str__` promoted to first-class AC** (AC-10) with parametrized round-trip table + Hypothesis property.
8. **`assert_never` promoted to AC-14** with AST scan precedent from S1-01.
9. **Hashability promoted to AC-12 + AC-13** with property test + `dict` key usage test.
10. **Module-purity AC-21** mirroring Phase-2 S1-04 / S1-01 precedents.
11. **Files-to-touch updated** — added `test_scope_exhaustiveness.py` + `test_scope_purity.py`.
12. **Notes-for-implementer expanded** — Rule-7 import warning, keyword-instantiation idiom, `Concrete.value` validation choice, precedent path correction (`indices/freshness.py`), `matches` signature rationale (str-not-newtype), NFKC non-normalization stance, "partial order" wording fix, `__str__` load-bearing-ness, closed-set scope-dim count.

### Verdict

**HARDENED.** Story is now ready for `phase-story-executor`. 22 individually-verifiable ACs (was 11), 20-entry mutation kill-list (was none), corrected import paths consistent with S1-01 + Phase-2 S1-04 canonical homes, AST-enforced exhaustiveness + module-purity, round-trip + hashability properties pinned via Hypothesis, adversarial parse coverage across the regex character-class boundary, and arch-§C3-vs-ADR-0010-§1 ambiguity documented rather than silently averaged. No structural problems remained that required `RESCUE`.
