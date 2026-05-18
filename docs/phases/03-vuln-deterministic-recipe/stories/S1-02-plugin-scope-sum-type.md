# Story S1-02 — PluginScope sum type + parser

**Step:** Step 1 — Scaffold packages, domain primitives, sum types, and structural CI fences
**Status:** HARDENED
**Effort:** S
**Depends on:** S1-01 (`ParseError` at `src/codegenie/types/errors.py`; `Result`/`Ok`/`Err` re-exported from `codegenie.result`; `parse_*` smart-constructor + keyword-instantiation convention)
**ADRs honored:** ADR-0010 (make-illegal-states-unrepresentable for `ScopeDim`; smart constructor for `PluginScope.parse`), ADR-0003 (plugin resolution semantics — `specificity` total order drives resolver ordering)

## Validation notes (added 2026-05-18 by `phase-story-validator`)

This story was hardened from `Ready` → `HARDENED`. Key changes (see [`_validation/S1-02-plugin-scope-sum-type.md`](_validation/S1-02-plugin-scope-sum-type.md) for the full critic-by-critic audit):

- **Rule-7 import drift fixed.** Original TDD code imported `from codegenie.types.result import Ok, Err`. That module does not exist; S1-01 (HARDENED) pins `Ok`/`Err`/`Result` at `codegenie.result` (Phase-2 S1-04 canonical home) and `ParseError` at `codegenie.types.errors`. TDD code rewritten accordingly. **Do not create `src/codegenie/types/result.py`.**
- **`Err(error=ParseError(message=..., value=...))` keyword-instantiation idiom pinned.** S1-01 established that `Ok`/`Err` are Pydantic discriminated unions on `kind`; positional instantiation is brittle. AC added.
- **Round-trip invariant promoted to AC.** Originally a one-line Refactor aside (`PluginScope.parse(str(scope)).value == scope`). It is load-bearing for YAML serialization (ADR-0010 §Decision §1 — "YAML still writes `*` and `<concrete>` strings via the smart constructor"); without an AC the executor may skip it and break S2-02's manifest loader silently.
- **`__str__` promoted to AC.** Originally only "needed by S2-03 loader error messages" — pinned now so S2-03 doesn't break on a missing method.
- **Adversarial parse rejection matrix expanded.** Original AC-3 listed three vague categories. Hardened table enumerates: empty input, leading/trailing `--`, uppercase, dot/slash, NUL byte, U+200B zero-width space, full-width digits, leading/trailing whitespace, per-dim length cap, NFKC normalization, and the universal-scope round-trip pin.
- **`assert_never` exhaustiveness promoted from advice to AC.** AST scan verifies every `match` over `ScopeDim` includes the `case _: assert_never(...)` arm — load-bearing for the closed-variant promise (`Negation`/`Range` variants must break the build, not silently misbehave).
- **Hashability + equality semantics pinned.** Notes-for-implementer claimed "scope instances are hashable (registry keys)"; now an AC + Hypothesis property. Same for `Wildcard() == Wildcard()` singleton-like behavior.
- **Specificity wording fixed: total order, not partial.** ADR-0003 §Decision sort key requires total order; specificity returns `int ∈ {0,1,2,3}`. Story now asserts `(*,*,*).specificity() == 0` and `monotonicity` for the resolver-sort consumer.
- **Module-purity AST scan AC.** Functional-core/imperative-shell discipline — `scope.py` is kernel; imports only `__future__`, `typing`, `dataclasses`, `re`, `codegenie.result`, `codegenie.types.errors`. Mirrors Phase-2 S1-04 `result.py` and Phase-2 S1-01 `freshness.py` precedents.
- **Reference path corrected.** Notes-for-implementer pointed at `src/codegenie/probes/layer_b/` for "match + assert_never precedent" — but Phase-2 probes use Pydantic discriminated unions, not dataclass variants. Correct precedent is `src/codegenie/indices/freshness.py` (Phase-2 S1-01 `IndexFreshness = Fresh | Stale`).
- **Hypothesis strategy regex aligned with parse regex.** Original draft strategy used `^[a-z][a-z0-9_-]{0,16}$` (forces leading lowercase letter); parse accepts `[a-z0-9_-]+` (also leading digit / underscore / hyphen). Strategy widened; round-trip property now actually covers the parse-admissible space.

Verdict: **HARDENED** — ACs went from 11 to 22, TDD plan has an explicit mutation kill-list, all imports trace to existing modules, and module-purity + exhaustiveness are observable rather than advisory.

## Context

The best-practices lens design proposed `PluginScope.task_class: NewType("TaskClass", str) | Literal["*"]` and was correctly attacked in `critique.md §Best-practices design — concrete problems`: that type collapses to `str` at runtime, so the resolver's `if dim == "*"` branch resurrects exactly the magic-string anti-pattern ADR-0033 forbids. This story ships the explicit `ScopeDim = Concrete | Wildcard` sum type and the `PluginScope` dataclass that S2-04's resolver iterates over — so every `match dim` in the resolver and every `extends`-chain walker is exhaustive at mypy time, not at runtime.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C3` — full public interface for `Concrete`, `Wildcard`, `ScopeDim`, `PluginScope.matches`, `PluginScope.specificity`, `PluginScope.parse`. Bytes-for-bytes the shape this story must land.
  - `../phase-arch-design.md §Scenarios §Scenario D` — `extends`-chain walk consumes `PluginScope` instances; specificity ordering is load-bearing.
  - `../phase-arch-design.md §Component design C2` — `Plugin.manifest.scope: PluginScope` ships in S2-02 against this type.
- **Phase ADRs:**
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — Decision §1 names the exact shape (`@dataclass(frozen=True, slots=True)` for both variants; `TypeAlias` for `ScopeDim`); §Pattern fit names "Make illegal states unrepresentable" as the failure mode.
  - `../ADRs/0003-plugin-resolution-and-universal-fallback-semantics.md` — `specificity desc` is one of the three resolver sort keys; the partial order this story defines is contracted by the resolver.
- **Existing code:**
  - `src/codegenie/types/identifiers.py` (after S1-01) — `Concrete.value: str` is wrapped at call sites with `TaskClassId`/`Language`/`PackageManager`; PluginScope itself stays type-agnostic so it can be shared by every task class.
  - `tests/unit/probes/layer_b/` — Phase-2 precedent for `match` + `assert_never` exhaustiveness in production code; same convention applies here.

## Goal

Land `src/codegenie/plugins/scope.py` with `Concrete`, `Wildcard`, `ScopeDim`, `PluginScope` exactly as ADR-0010 §Decision §1 specifies, with `PluginScope.parse` as a smart constructor returning `Result[PluginScope, ParseError]` and a Hypothesis-tested `matches`/`specificity` algebra.

## Acceptance criteria

### Package + module shape

- [ ] **AC-1** — `src/codegenie/plugins/__init__.py` exists (one-line module docstring naming the kernel namespace; no eager imports — `default_registry` lands in S2-01). Empty `__all__` is acceptable; if non-empty it MUST be alphabetically sorted.
- [ ] **AC-2** — `src/codegenie/plugins/scope.py` exports exactly `Concrete`, `Wildcard`, `ScopeDim`, `PluginScope` (via an explicit `__all__: Final[tuple[str, ...]] = ("Concrete", "PluginScope", "ScopeDim", "Wildcard")`, alphabetically sorted). `set(scope.__all__)` equality is asserted in a test — stowaway exports (leaked `re`, `dataclasses`, `Result`) fail CI.
- [ ] **AC-3** — `Concrete` and `Wildcard` are `@dataclass(frozen=True, slots=True)` *exactly* per ADR-0010 §Decision §1 — `Concrete.value: str` (no validation at construction; `parse` is the only safe boundary); `Wildcard` has zero fields. `ScopeDim: TypeAlias = Concrete | Wildcard`. `PluginScope` is also `@dataclass(frozen=True, slots=True)` with three `ScopeDim`-typed fields named `task_class`, `language`, `build_system`.

### Smart constructor (`parse`)

- [ ] **AC-4** — `PluginScope.parse(s: str) -> Result[PluginScope, ParseError]` is a `@classmethod` that returns `Ok(value=PluginScope(...))` on success and `Err(error=ParseError(message=<reason>, value=s))` on failure. **Keyword instantiation only** for `Ok` / `Err` / `ParseError` — discriminator-on-`kind` requires it (per S1-01 convention; mirrors `src/codegenie/tccm/loader.py` idiom). Positional instantiation in implementation code or tests is forbidden.
- [ ] **AC-5** — `parse` admits `"<task>--<lang>--<build>"` where each dim is either `"*"` (→ `Wildcard()`) or a non-empty string matching the regex `^[a-z0-9_-]+$` with per-dim length ≤ 64 chars (→ `Concrete(value=s_dim)`). The exact dim regex is exported as a module-level `Final` constant (e.g., `_DIM_PATTERN: Final[re.Pattern[str]]`) so a future S2-02 manifest loader can re-use it.
- [ ] **AC-6** — `parse` rejects (with `Err(error=ParseError(...))`, never raises) every input in the parametrized rejection matrix below. Each row is one parametrized test case; the test name encodes the mutation it would catch:

  | # | Input | Rejection reason |
  |---|---|---|
  | R1 | `""` | empty input |
  | R2 | `"a--b"` | only 2 dims |
  | R3 | `"a--b--c--d"` | 4 dims |
  | R4 | `"--b--c"` | leading empty dim |
  | R5 | `"a----c"` | middle empty dim |
  | R6 | `"a--b--"` | trailing empty dim |
  | R7 | `"a--b--c\n"` | trailing newline / control char |
  | R8 | `" a--b--c"` | leading whitespace |
  | R9 | `"a--b--c "` | trailing whitespace |
  | R10 | `"A--b--c"` | uppercase letter |
  | R11 | `"a.b--c--d"` | illegal char `.` |
  | R12 | `"a/b--c--d"` | illegal char `/` |
  | R13 | `"a--b--c\x00"` | NUL byte |
  | R14 | `"a--b--​c"` | U+200B zero-width space |
  | R15 | `"a--b--ｃ"` (full-width c) | non-ASCII / NFKC ambiguity |
  | R16 | `"a" * 65 + "--b--c"` | per-dim length cap (65 > 64) |
  | R17 | `"a--*--"` | trailing empty dim alongside wildcard |

  AC pin: `parse` does NOT silently NFKC-normalize input — adversarial homoglyphs reject; normalization is the call-site's responsibility.

### Membership + ordering algebra

- [ ] **AC-7** — `PluginScope.matches(*, task: str, language: str, build: str) -> bool` returns True iff *every* dim either is `Wildcard()` or its `Concrete.value` equals the supplied concrete. Implementation is a single `match` over the 3-tuple `(task_class, language, build_system)` with a `case _: assert_never(...)` arm. (Signature is `str`-typed, not newtype-typed — `PluginScope` stays task-class-agnostic per ADR-0010 §Decision §1; arch §C3's newtype-typed params are illustrative-at-the-call-site, not the kernel signature.)
- [ ] **AC-8** — `PluginScope.specificity() -> int` returns the count of `Concrete` dims, implemented as a single `match` block over the 3-tuple with a `case _: assert_never(...)` arm. Returned value is one of `{0, 1, 2, 3}` — asserted at the test boundary.
- [ ] **AC-9** — `specificity()` defines a **total order** on `PluginScope` (consumed by ADR-0003 §Decision step 2 resolver sort: `(specificity desc, precedence desc, name asc)`). The universal scope pin: `PluginScope.parse("*--*--*").unwrap().specificity() == 0`. The all-concrete pin: `PluginScope.parse("a--b--c").unwrap().specificity() == 3`. Monotonicity pin: there exist scopes `S0..S3` with `Si.specificity() == i`, and the sequence is strictly increasing.

### Round-trip + serialization

- [ ] **AC-10** — `PluginScope.__str__` returns the canonical `"<task>--<lang>--<build>"` form where each dim is `"*"` (for `Wildcard`) or the `Concrete.value` (for `Concrete`). For any constructible `PluginScope` `s` (built via `PluginScope.parse(input).unwrap()`), `str(s) == input` for every input that satisfies the dim regex *exactly* (no leading zeros, no trim, no normalization). The round-trip is exercised over the parametrized happy-path table AND as a Hypothesis property (see TDD plan).
- [ ] **AC-11** — `PluginScope.parse(str(scope)).unwrap() == scope` for any constructible `scope`. (Inverse of AC-10; load-bearing for S2-02 YAML manifest loader and S2-03's `extends`-chain reader.)

### Equality + hashability

- [ ] **AC-12** — `PluginScope`, `Concrete`, and `Wildcard` are hashable (frozen + slots dataclasses; default `__hash__` over fields). Two instances of `Wildcard()` are `==` and have equal `hash`. Two `Concrete("x")` instances are `==` and have equal `hash`. Two `PluginScope` instances with identical dims are `==` and have equal `hash`. AC also exercises usability as a `dict` key and `set` member (registry storage shape from S2-01).
- [ ] **AC-13** — A Hypothesis property test asserts hashability stability: for any constructible `PluginScope` `s`, `hash(s) == hash(PluginScope(s.task_class, s.language, s.build_system))` (rebuild from same dims). Same for `Concrete(v)` for any `v` admissible to `parse`.

### Exhaustiveness invariant

- [ ] **AC-14** — Every `match` block in `scope.py` over `ScopeDim` or any `tuple[ScopeDim, ScopeDim, ScopeDim]` includes a `case _: assert_never(...)` arm. AST-walk test (`tests/unit/plugins/test_scope_exhaustiveness.py`) parses `scope.py` and asserts: every `Match` node whose subject involves a `ScopeDim`-typed expression contains a final `MatchAs(pattern=None)` (the `_` pattern) whose body is a single `assert_never(...)` call. Adding a future `Negation` / `Range` variant without updating every `match` site MUST break `mypy --strict`; this AC is the static + AST belt-and-braces.

### Property-based + Hypothesis

- [ ] **AC-15** — `tests/unit/plugins/test_scope.py` contains a Hypothesis `@st.composite` strategy `scope_dims()` aligned to the parse regex (`^[a-z0-9_-]+$`, length ≤ 64) — not the original draft's `^[a-z][a-z0-9_-]{0,16}$` which over-constrained the leading character and under-constrained the length. The strategy emits `Wildcard()` ~50% and `Concrete(...)` ~50%.
- [ ] **AC-16** — Property test: for any `PluginScope` built from `scope_dims()` × 3 and any `(task, language, build)` triple from `text(min_size=1, max_size=64)`, `scope.matches(...)` returns True iff every concrete dim agrees with the supplied triple. Implementation re-derives the answer in the test body via a `match` block — *not* by calling `scope.matches` (that would tautologically pass).
- [ ] **AC-17** — Property test: for any constructible `PluginScope`, `specificity()` equals `sum(1 for d in (task_class, language, build_system) if isinstance(d, Concrete))` and is ∈ `{0, 1, 2, 3}`.
- [ ] **AC-18** — Property test: parse totality — for any `s: str` drawn from `st.text(max_size=200)`, `PluginScope.parse(s)` returns `Ok | Err` and never raises any exception (no `ValueError`, no `re.error`, no `UnicodeError`). Asserted via `try / except Exception: pytest.fail(...)`.
- [ ] **AC-19** — Property test: parse determinism — for any `s: str`, `PluginScope.parse(s) == PluginScope.parse(s)` (modulo Pydantic equality on the discriminated `Result` union). Guards against accidental regex-cache mutability or hidden state in the parser.
- [ ] **AC-20** — Round-trip property: for any constructible `scope`, `PluginScope.parse(str(scope)).unwrap() == scope`. (Hypothesis form of AC-11.)

### Module purity + style

- [ ] **AC-21** — Module-purity AST scan (`tests/unit/plugins/test_scope_purity.py`) parses `src/codegenie/plugins/scope.py` and asserts the `Import`/`ImportFrom` set is a subset of `{__future__, dataclasses, re, typing, codegenie.result, codegenie.types.errors}`. No logger, no fs, no sibling-package imports. Mirrors the `tests/unit/result/test_result_module_purity.py` precedent (Phase-2 S1-04) and `tests/unit/indices/test_freshness_module_purity.py` (Phase-2 S1-01 — `IndexFreshness` is the closest existing dataclass-variant + `match` precedent in the repo).
- [ ] **AC-22** — `mypy --strict src/codegenie/plugins/` clean; `ruff check src/codegenie/plugins/ tests/unit/plugins/` clean; `ruff format --check` clean. TDD plan's red test exists in a committed-and-then-greened sequence (separate commits acceptable, must both be present in the branch history).

## Implementation outline

1. Create `src/codegenie/plugins/__init__.py` (one-line module docstring naming the kernel namespace; no eager imports — S2-01 lands `default_registry`).
2. Create `src/codegenie/plugins/scope.py` with the four exports per ADR-0010 §Decision §1. Imports limited to `{__future__, dataclasses, re, typing (TypeAlias, Final, assert_never), codegenie.result (Ok, Err, Result), codegenie.types.errors (ParseError)}` — module-purity AC-21.
3. Implement `PluginScope.parse` as a `@classmethod`:
   - Split on the substring `"--"`; require exactly 3 non-overlapping resulting dims (`len(parts) != 3` → `Err(error=ParseError(message="expected exactly three '--'-separated dims", value=s))`).
   - For each dim: `"*" → Wildcard()`; else require non-empty, match `_DIM_PATTERN`, and `len(dim) <= 64` (→ `Concrete(value=dim)`; else `Err(error=ParseError(message=..., value=s))`).
   - Use keyword instantiation: `Ok(value=PluginScope(...))` / `Err(error=ParseError(...))`. Positional construction is forbidden by AC-4.
4. Implement `PluginScope.matches` and `PluginScope.specificity` as `match` blocks over `(task_class, language, build_system)`, each ending with `case _: assert_never(...)`.
5. Implement `PluginScope.__str__` to reproduce the canonical `"<t>--<l>--<b>"` form (AC-10).
6. Land `tests/unit/plugins/__init__.py` + `tests/unit/plugins/test_scope.py` + `tests/unit/plugins/test_scope_exhaustiveness.py` + `tests/unit/plugins/test_scope_purity.py`. Use the mutation kill-list below to name each test.
7. Run `mypy --strict src/codegenie/plugins/` + `pytest tests/unit/plugins/ -v`.

## TDD plan — red / green / refactor

### Mutation kill-list (every test below kills at least one of these)

| # | Wrong impl | Killed by test |
|---|---|---|
| M1 | `parse` returns `Ok(Wildcard(),...)` always | `test_parse_happy_path_concrete_dims` |
| M2 | `parse` accepts `"a----b"` (silently coerces empty middle to Wildcard) | `test_parse_rejects[R5]` |
| M3 | `parse` accepts uppercase | `test_parse_rejects[R10]` |
| M4 | `parse` accepts dot/slash | `test_parse_rejects[R11]`, `[R12]` |
| M5 | `parse` accepts NUL / U+200B / full-width | `test_parse_rejects[R13]`, `[R14]`, `[R15]` |
| M6 | `parse` accepts dim ≥ 65 chars | `test_parse_rejects[R16]` |
| M7 | `parse` strips whitespace | `test_parse_rejects[R8]`, `[R9]` |
| M8 | `parse` raises on adversarial input | `test_parse_totality` (Hypothesis) |
| M9 | `matches` returns True if any one dim agrees (instead of all) | `test_matches_exact_negative_build`, `test_matches_algebra` (Hypothesis) |
| M10 | `matches` ignores build dim | `test_matches_exact_negative_build` |
| M11 | `specificity` returns 0 always | `test_specificity_concrete_count[all_concrete]` |
| M12 | `specificity` returns `int(bool(any_concrete))` | `test_specificity_concrete_count` parametrized for 2-concrete case |
| M13 | `parse("*--*--*")` constructs `Concrete("*")` instead of `Wildcard()` | `test_parse_universal_wildcard_specificity_is_zero` |
| M14 | `__str__` returns `repr(self)` instead of `"t--l--b"` form | `test_str_round_trip[happy]`, `test_parse_str_round_trip` (Hypothesis) |
| M15 | `Concrete("x") != Concrete("x")` (some impl overrides `__eq__`) | `test_concrete_equality` |
| M16 | `Wildcard()` hashes differently across instances | `test_wildcard_hash_stable`, `test_hash_stability` (Hypothesis) |
| M17 | `match` block omits `assert_never` arm | `test_scope_match_blocks_have_assert_never` (AST scan) |
| M18 | `scope.py` imports `logging` or `pathlib` | `test_scope_module_purity` (AST scan) |
| M19 | `PluginScope(...)` not usable as dict key | `test_pluginscope_as_dict_key` |
| M20 | `Err` instantiated positionally → Pydantic discrimination breaks at runtime | `test_parse_err_uses_keyword_instantiation` (constructs Err manually + compares) |

### Red — write the failing test first

Test file path: `tests/unit/plugins/test_scope.py`

```python
import pytest
from hypothesis import given, strategies as st

from codegenie.plugins.scope import Concrete, PluginScope, ScopeDim, Wildcard
from codegenie.result import Err, Ok
from codegenie.types.errors import ParseError


# ---- Happy-path parsing ----

def test_parse_happy_path_concrete_dims():
    r = PluginScope.parse("vulnerability-remediation--node--npm")
    assert isinstance(r, Ok)
    s = r.value
    assert s.task_class == Concrete(value="vulnerability-remediation")
    assert s.language == Concrete(value="node")
    assert s.build_system == Concrete(value="npm")
    assert s.specificity() == 3


def test_parse_universal_wildcard_specificity_is_zero():
    r = PluginScope.parse("*--*--*")
    assert isinstance(r, Ok)
    assert r.value.task_class == Wildcard()
    assert r.value.specificity() == 0


def test_parse_mixed_concrete_and_wildcard():
    r = PluginScope.parse("vuln--*--npm")
    assert isinstance(r, Ok)
    s = r.value
    assert s.task_class == Concrete(value="vuln")
    assert s.language == Wildcard()
    assert s.build_system == Concrete(value="npm")
    assert s.specificity() == 2


# ---- Rejection matrix (AC-6) ----

REJECTIONS: list[tuple[str, str]] = [
    ("R1", ""),
    ("R2", "a--b"),
    ("R3", "a--b--c--d"),
    ("R4", "--b--c"),
    ("R5", "a----c"),
    ("R6", "a--b--"),
    ("R7", "a--b--c\n"),
    ("R8", " a--b--c"),
    ("R9", "a--b--c "),
    ("R10", "A--b--c"),
    ("R11", "a.b--c--d"),
    ("R12", "a/b--c--d"),
    ("R13", "a--b--c\x00"),
    ("R14", "a--b--​c"),
    ("R15", "a--b--ｃ"),  # full-width 'c'
    ("R16", "a" * 65 + "--b--c"),
    ("R17", "a--*--"),
]


@pytest.mark.parametrize("rid,bad", REJECTIONS, ids=[r[0] for r in REJECTIONS])
def test_parse_rejects(rid: str, bad: str) -> None:
    r = PluginScope.parse(bad)
    assert isinstance(r, Err), f"{rid}: expected Err, got {r!r}"
    assert isinstance(r.error, ParseError)
    assert r.error.value == bad


def test_parse_err_uses_keyword_instantiation() -> None:
    # If the impl uses positional Err(ParseError(...)) the Pydantic discriminator
    # on `kind` may dispatch wrong. Verify the keyword shape round-trips.
    r = PluginScope.parse("")
    assert isinstance(r, Err)
    rebuilt = Err(error=ParseError(message=r.error.message, value=r.error.value))
    assert r == rebuilt


# ---- matches algebra ----

def test_matches_exact_positive() -> None:
    s = PluginScope.parse("vuln--node--npm").unwrap()
    assert s.matches(task="vuln", language="node", build="npm")


def test_matches_exact_negative_build() -> None:
    s = PluginScope.parse("vuln--node--npm").unwrap()
    assert not s.matches(task="vuln", language="node", build="yarn")


def test_matches_exact_negative_language() -> None:
    s = PluginScope.parse("vuln--node--npm").unwrap()
    assert not s.matches(task="vuln", language="rust", build="npm")


def test_matches_wildcard_admits_anything() -> None:
    s = PluginScope.parse("*--*--*").unwrap()
    assert s.matches(task="anything", language="rust", build="cargo")


def test_matches_partial_wildcard() -> None:
    s = PluginScope.parse("*--node--*").unwrap()
    assert s.matches(task="vuln", language="node", build="npm")
    assert not s.matches(task="vuln", language="rust", build="npm")


# ---- specificity ----

@pytest.mark.parametrize(
    "scope_str,expected",
    [
        ("*--*--*", 0),
        ("a--*--*", 1),
        ("*--b--*", 1),
        ("*--*--c", 1),
        ("a--b--*", 2),
        ("a--*--c", 2),
        ("*--b--c", 2),
        ("a--b--c", 3),
    ],
)
def test_specificity_concrete_count(scope_str: str, expected: int) -> None:
    s = PluginScope.parse(scope_str).unwrap()
    assert s.specificity() == expected


def test_specificity_total_order_for_resolver_sort() -> None:
    """ADR-0003 §Decision step 2 sorts by specificity desc; pin monotonicity."""
    s0 = PluginScope.parse("*--*--*").unwrap()
    s1 = PluginScope.parse("a--*--*").unwrap()
    s2 = PluginScope.parse("a--b--*").unwrap()
    s3 = PluginScope.parse("a--b--c").unwrap()
    seq = [s0.specificity(), s1.specificity(), s2.specificity(), s3.specificity()]
    assert seq == [0, 1, 2, 3]


# ---- __str__ round-trip ----

@pytest.mark.parametrize(
    "canonical",
    ["*--*--*", "a--b--c", "vuln--*--npm", "vulnerability-remediation--node--npm"],
)
def test_str_round_trip(canonical: str) -> None:
    s = PluginScope.parse(canonical).unwrap()
    assert str(s) == canonical


# ---- equality + hashability ----

def test_concrete_equality() -> None:
    assert Concrete(value="x") == Concrete(value="x")
    assert hash(Concrete(value="x")) == hash(Concrete(value="x"))


def test_wildcard_hash_stable() -> None:
    assert Wildcard() == Wildcard()
    assert hash(Wildcard()) == hash(Wildcard())


def test_pluginscope_as_dict_key() -> None:
    s1 = PluginScope.parse("a--b--c").unwrap()
    s2 = PluginScope.parse("a--b--c").unwrap()
    d: dict[PluginScope, int] = {s1: 1}
    assert d[s2] == 1  # equality-keyed lookup works


# ---- Hypothesis property tests ----

@st.composite
def scope_dims(draw: st.DrawFn) -> ScopeDim:
    is_wild = draw(st.booleans())
    if is_wild:
        return Wildcard()
    # Align with parse regex: ^[a-z0-9_-]+$, length <= 64
    return Concrete(value=draw(st.from_regex(r"^[a-z0-9_-]{1,64}$", fullmatch=True)))


@given(
    t=scope_dims(),
    lng=scope_dims(),
    b=scope_dims(),
    task=st.text(min_size=1, max_size=64),
    lang=st.text(min_size=1, max_size=64),
    build=st.text(min_size=1, max_size=64),
)
def test_matches_algebra(
    t: ScopeDim, lng: ScopeDim, b: ScopeDim, task: str, lang: str, build: str
) -> None:
    s = PluginScope(task_class=t, language=lng, build_system=b)

    def dim_ok(dim: ScopeDim, v: str) -> bool:
        match dim:
            case Wildcard():
                return True
            case Concrete(value=val):
                return val == v

    expected = dim_ok(t, task) and dim_ok(lng, lang) and dim_ok(b, build)
    assert s.matches(task=task, language=lang, build=build) == expected


@given(t=scope_dims(), lng=scope_dims(), b=scope_dims())
def test_specificity_property(t: ScopeDim, lng: ScopeDim, b: ScopeDim) -> None:
    s = PluginScope(task_class=t, language=lng, build_system=b)
    expected = sum(1 for d in (t, lng, b) if isinstance(d, Concrete))
    assert s.specificity() == expected
    assert 0 <= s.specificity() <= 3


@given(s=st.text(max_size=200))
def test_parse_totality(s: str) -> None:
    """parse is a total function: never raises, always returns Ok | Err."""
    try:
        r = PluginScope.parse(s)
    except Exception as exc:  # pragma: no cover — fail loud if it ever raises
        pytest.fail(f"parse({s!r}) raised {type(exc).__name__}: {exc}")
    assert isinstance(r, (Ok, Err))


@given(s=st.text(max_size=200))
def test_parse_determinism(s: str) -> None:
    assert PluginScope.parse(s) == PluginScope.parse(s)


@given(t=scope_dims(), lng=scope_dims(), b=scope_dims())
def test_parse_str_round_trip(t: ScopeDim, lng: ScopeDim, b: ScopeDim) -> None:
    s = PluginScope(task_class=t, language=lng, build_system=b)
    reparsed = PluginScope.parse(str(s))
    assert isinstance(reparsed, Ok)
    assert reparsed.value == s


@given(t=scope_dims(), lng=scope_dims(), b=scope_dims())
def test_hash_stability(t: ScopeDim, lng: ScopeDim, b: ScopeDim) -> None:
    s1 = PluginScope(task_class=t, language=lng, build_system=b)
    s2 = PluginScope(task_class=t, language=lng, build_system=b)
    assert s1 == s2
    assert hash(s1) == hash(s2)
```

State why it fails: `ModuleNotFoundError: codegenie.plugins.scope` — the module doesn't exist yet.

### Exhaustiveness AST test (`tests/unit/plugins/test_scope_exhaustiveness.py`)

```python
"""AC-14: every match block over ScopeDim in scope.py ends with `case _: assert_never(...)`."""
import ast
from pathlib import Path

import codegenie.plugins.scope as scope_mod


def test_scope_match_blocks_have_assert_never() -> None:
    src = Path(scope_mod.__file__).read_text()
    tree = ast.parse(src)
    match_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Match)]
    assert match_nodes, "expected at least one `match` block in scope.py"
    for m in match_nodes:
        last = m.cases[-1]
        # Last case must be `case _: ...`
        assert isinstance(last.pattern, ast.MatchAs) and last.pattern.pattern is None, (
            f"last case in match at line {m.lineno} is not a wildcard `_`"
        )
        # Body must be a single Expr wrapping a Call to assert_never
        body = last.body
        assert len(body) == 1 and isinstance(body[0], ast.Expr), (
            f"wildcard arm at line {m.lineno} is not a single assert_never expression"
        )
        call = body[0].value
        assert isinstance(call, ast.Call) and getattr(call.func, "id", None) == "assert_never", (
            f"wildcard arm at line {m.lineno} does not call assert_never(...)"
        )
```

### Module-purity AST test (`tests/unit/plugins/test_scope_purity.py`)

```python
"""AC-21: scope.py imports only the allowed set."""
import ast
from pathlib import Path

import codegenie.plugins.scope as scope_mod

ALLOWED_TOP_LEVEL: frozenset[str] = frozenset({
    "__future__", "dataclasses", "re", "typing",
    "codegenie.result", "codegenie.types.errors",
})


def test_scope_module_purity() -> None:
    src = Path(scope_mod.__file__).read_text()
    tree = ast.parse(src)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0] if alias.name != "__future__" else alias.name)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    illegal = {name for name in imported if name and name not in ALLOWED_TOP_LEVEL}
    assert not illegal, f"scope.py imports outside allowed set: {sorted(illegal)}"
```

### Green — minimal pass

- Add `src/codegenie/plugins/__init__.py` with a one-line docstring; no eager imports.
- Add `src/codegenie/plugins/scope.py` with `Concrete`, `Wildcard`, `ScopeDim`, `PluginScope`, `parse`, `matches`, `specificity`, `__str__` — the minimum that turns every assertion green. Match the import allowlist from AC-21.

### Refactor

- Lift the per-dim regex to `_DIM_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9_-]+$")` with a comment naming ADR-0010 §Decision §1. Lift the per-dim length cap to `_DIM_MAX_LEN: Final[int] = 64`. Re-use in `parse`.
- Confirm `__str__` reproduces the parser input verbatim (`"task--lang--build"`) — needed by S2-03 loader error messages and YAML serialization round-trip.
- Edge cases: E2 (Yarn Berry mis-routed to npm plugin) is exercised at the resolver level (S2-04); here, the round-trip property (AC-11 / `test_parse_str_round_trip`) is the load-bearing serialization invariant for that integration.
- Confirm `assert_never(...)` calls land in *every* `match` block (AC-14 — AST test enforces).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/__init__.py` | NEW — package marker for the kernel namespace (load-bearing for S1-05 import-linter contracts). |
| `src/codegenie/plugins/scope.py` | NEW — the four exports per ADR-0010 §Decision §1, plus `__str__` and `parse` smart constructor. |
| `tests/unit/plugins/__init__.py` | NEW — test package marker. |
| `tests/unit/plugins/test_scope.py` | NEW — unit table (rejection matrix R1–R17, matches positives/negatives, specificity parametrized, equality/hashability, `__str__` round-trip) + Hypothesis property tests (totality, determinism, round-trip, hash stability, matches algebra, specificity property). |
| `tests/unit/plugins/test_scope_exhaustiveness.py` | NEW — AST scan asserting `assert_never` in every `match` over `ScopeDim` (AC-14). |
| `tests/unit/plugins/test_scope_purity.py` | NEW — AST scan asserting `scope.py` imports only the allowlist (AC-21). |

## Out of scope

- **`PluginRegistry`, `@register_plugin`, resolver** — handled by S2-01 / S2-04. This story only ships the value type the registry stores.
- **`PluginManifest` YAML loader** — handled by S2-02; uses `PluginScope.parse` from inside `from_yaml`.
- **`extends`-chain walker** — handled by S2-04; consumes `PluginScope.matches` and `PluginScope.specificity`.
- **`ConcreteResolution | UniversalFallbackResolution` sum** — handled by S2-04 (lives in `resolution.py`, not `scope.py`).
- **Re-using `TaskClassId`/`Language`/`PackageManager` newtypes** inside `Concrete.value` — ADR-0010 §Decision §1 deliberately keeps `Concrete.value: str` so `PluginScope` is task-class-agnostic; call sites wrap with the right newtype.

## Notes for the implementer

- **Import the right `Result` module.** `Ok`, `Err`, `Result` live at `codegenie.result` (Phase-2 S1-04 canonical home, consumed by `tccm/loader.py`, `skills/loader.py`, `conventions/loader.py`). `ParseError` lives at `codegenie.types.errors` (Phase-3 S1-01). **Do NOT** create `src/codegenie/types/result.py` — that would fork the canonical module and is a Rule-7 violation. AC-21 module-purity scan enforces this.
- **Keyword instantiation only** for `Ok` / `Err` / `ParseError` — the `Result` discriminated union dispatches on the literal `kind` field, and positional instantiation is brittle when Pydantic re-validates a model. Always `Ok(value=...)`, `Err(error=ParseError(message=..., value=...))`. Mirrors `src/codegenie/tccm/loader.py:98`.
- **`@dataclass(frozen=True, slots=True)` matters** for `Concrete`, `Wildcard`, and `PluginScope` — `frozen` so instances are hashable (registry keys in S2-01); `slots` for memory and accidental-attribute-assignment defense. Don't use `Pydantic` here — the data is too small and `match` exhaustiveness on Pydantic discriminated unions is awkward vs. native sum types. The choice is bytes-for-bytes mandated by ADR-0010 §Decision §1.
- **`Concrete.value` carries no internal validation.** Constructing `Concrete(value="UPPERCASE")` is legal at the dataclass level. `PluginScope.parse` is the only safe external entry; YAML loaders go through it (S2-02). Defense-in-depth `__post_init__` validation was considered and rejected (ADR-0010 §1 specifies bare dataclass; smart constructor is the boundary).
- **`ScopeDim: TypeAlias = Concrete | Wildcard`** must be a `TypeAlias`, not a bare union, so `mypy` (and `pyright` if anyone runs it) treats it as a closed sum.
- **`match` must include `case Wildcard():` (with parens), not `case Wildcard:`** — the former pattern-matches the type, the latter binds the name. Easy to get wrong; the closest existing dataclass-variant precedent in the repo is `src/codegenie/indices/freshness.py` (Phase-2 S1-01 — `IndexFreshness = Fresh | Stale` with the same shape). Phase-2 probes under `src/codegenie/probes/layer_b/` use *Pydantic* discriminated unions, not dataclass variants — do not copy that pattern here.
- **`assert_never` import** comes from `typing` in Python 3.11+ (the repo's minimum). Always include the `case _: assert_never(...)` arm even though the union is closed — it's the one line that makes adding a future `Negation`/`Range` variant break the build instead of silently misbehaving. AC-14 AST scan enforces this; do not skip.
- **Scope dims are a closed set.** Adding a 4th dim (e.g., `runtime_target`) would change `specificity()` semantics across every existing plugin and is an ADR-0003 §Tradeoffs known cost. Not Open/Closed at this seam — extension by *addition* applies to plugin scopes, recipes, and resolvers, not to the scope-dim count itself. New dims require an ADR amendment.
- **`PluginScope.matches` signature uses `str`, not newtypes** (`task: str`, `language: str`, `build: str`) — arch §C3 shows newtype-typed params, but ADR-0010 §Decision §1 says `Concrete.value: str` so the kernel stays task-class-agnostic. Newtypes (`TaskClass`, `Language`, `BuildSystem`) wrap at the call site (S2-04 resolver) — they are runtime-identical to `str` so the equality check is a no-op cast. Documented here so a future reader doesn't "fix" the signature and accidentally couple the kernel to a single task class's newtype.
- **Hypothesis is already in `[dev]` dependencies** — verify with `grep hypothesis pyproject.toml` before importing; no new dep needed.
- **`PluginScope.parse` must reject `"a----b"`** (empty middle dim), not silently coerce to a Wildcard. The smart constructor is the boundary; ADR-0010 §Pattern fit explicitly forbids `Literal["*"]`-collapsed-to-`str` behavior. Pin via R5 in the rejection matrix.
- **`parse` does not NFKC-normalize input.** Full-width digits and zero-width spaces reject (R14, R15); normalization is the call site's responsibility. ADR-0010 §Decision §1 names "make illegal states unrepresentable" — accepting visually-equivalent-but-bytewise-different input is the failure mode this story closes.
- **Specificity defines a total order**, not a partial order. `specificity() ∈ {0, 1, 2, 3}` and the linear order is consumed by ADR-0003 §Decision step 2 resolver sort key `(specificity desc, precedence desc, name asc)`. Earlier draft wording said "partial order" — that's wrong; an `int`-valued function over a finite-product domain is linearly ordered by output.
- **`__str__` is load-bearing for round-trip serialization** (AC-10 / AC-11). S2-02 writes `PluginScope.parse(yaml_value)` and reads back via `str(scope)`; if `__str__` returns `repr(self)` the YAML manifest serialization breaks silently. Pinned by `test_str_round_trip` and the Hypothesis `test_parse_str_round_trip` property.
