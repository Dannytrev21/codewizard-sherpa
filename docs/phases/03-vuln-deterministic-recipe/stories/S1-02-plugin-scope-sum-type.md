# Story S1-02 — PluginScope sum type + parser

**Step:** Step 1 — Scaffold packages, domain primitives, sum types, and structural CI fences
**Status:** Ready
**Effort:** S
**Depends on:** S1-01 (`Result`/`ParseError`/`parse_*` smart-constructor convention; newtype-as-`str` discipline)
**ADRs honored:** ADR-0010 (make-illegal-states-unrepresentable for `ScopeDim`; smart constructor for `PluginScope.parse`), ADR-0003 (plugin resolution semantics — `specificity` partial order drives resolver ordering)

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

- [ ] `src/codegenie/plugins/__init__.py` exists (empty package marker for the new `codegenie.plugins.*` namespace).
- [ ] `src/codegenie/plugins/scope.py` exports `Concrete`, `Wildcard`, `ScopeDim`, `PluginScope` with the exact bytes from ADR-0010 §Decision §1 — `@dataclass(frozen=True, slots=True)` on both variants; `ScopeDim: TypeAlias = Concrete | Wildcard`.
- [ ] `PluginScope.parse(s: str) -> Result[PluginScope, ParseError]` accepts `"<task>--<lang>--<build>"` with `*` admitted per dim; rejects malformed input (wrong dim count, empty dim, illegal chars per dim) with `Err(ParseError(value=s, ...))`.
- [ ] `PluginScope.matches(*, task: str, language: str, build: str) -> bool` returns True iff every dim either is `Wildcard` or equals the supplied concrete; implementation is a single `match` over the 3-tuple of dims with `assert_never` on the impossible branch.
- [ ] `PluginScope.specificity() -> int` returns the count of `Concrete` dims (0, 1, 2, or 3) — straight `match`-counting.
- [ ] `tests/unit/plugins/test_scope.py` covers happy parse, sad parse (≥4 deliberate malformed inputs), exact-match, wildcard-match, no-match.
- [ ] One Hypothesis property test asserts: for any randomized `PluginScope` and `(task, language, build)` triple, `scope.matches(...)` returns True iff every concrete dim agrees with the triple — generated via `@st.composite` strategy that draws `Concrete | Wildcard` per dim.
- [ ] One Hypothesis property test asserts the `specificity` partial order is well-defined: `Concrete > Wildcard` per dim; `specificity ∈ {0, 1, 2, 3}`; total over the (Concrete-count) lattice.
- [ ] `mypy --strict src/codegenie/plugins/` clean.
- [ ] `ruff check`, `ruff format --check` clean.
- [ ] TDD plan's red test exists, committed, green.

## Implementation outline

1. Create `src/codegenie/plugins/__init__.py` (one-line module docstring naming the kernel; no eager imports — S2-01 lands `default_registry`).
2. Create `src/codegenie/plugins/scope.py` with the four exports per ADR-0010 §Decision §1.
3. Implement `PluginScope.parse`: split on `--` (exactly two separators → 3 dims); per-dim, `"*" → Wildcard()`, else `Concrete(value=s_dim)`. Reject if `len(dims) != 3` or any dim is empty or contains illegal chars (`[^a-z0-9_-]`).
4. Implement `PluginScope.matches` and `PluginScope.specificity` as `match` blocks (one line each).
5. Land `tests/unit/plugins/__init__.py` + `tests/unit/plugins/test_scope.py` with unit + 2 Hypothesis property tests.
6. Run `mypy --strict src/codegenie/plugins/` + `pytest tests/unit/plugins/test_scope.py -v`.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/unit/plugins/test_scope.py`

```python
import pytest
from hypothesis import given, strategies as st

from codegenie.plugins.scope import Concrete, Wildcard, PluginScope
from codegenie.types.result import Ok, Err


def test_parse_happy_path():
    r = PluginScope.parse("vulnerability-remediation--node--npm")
    assert isinstance(r, Ok)
    assert r.value.task_class == Concrete("vulnerability-remediation")
    assert r.value.build_system == Concrete("npm")


def test_parse_universal_wildcard():
    r = PluginScope.parse("*--*--*")
    assert isinstance(r, Ok)
    assert r.value.specificity() == 0


@pytest.mark.parametrize("bad", ["", "only-two--dims", "a--b--c--d", "a----b", "a--b--BAD CHARS"])
def test_parse_rejects(bad: str):
    assert isinstance(PluginScope.parse(bad), Err)


def test_matches_exact():
    scope = PluginScope.parse("vuln--node--npm").value  # type: ignore[union-attr]
    assert scope.matches(task="vuln", language="node", build="npm")
    assert not scope.matches(task="vuln", language="node", build="yarn")


def test_matches_wildcard_admits_anything():
    scope = PluginScope.parse("*--*--*").value  # type: ignore[union-attr]
    assert scope.matches(task="anything", language="rust", build="cargo")


# ---- Property tests ----

@st.composite
def scope_dims(draw):
    is_wild = draw(st.booleans())
    if is_wild:
        return Wildcard()
    return Concrete(draw(st.from_regex(r"^[a-z][a-z0-9_-]{0,16}$", fullmatch=True)))


@given(t=scope_dims(), l=scope_dims(), b=scope_dims(),
       task=st.text(min_size=1, max_size=20),
       lang=st.text(min_size=1, max_size=20),
       build=st.text(min_size=1, max_size=20))
def test_matches_algebra(t, l, b, task, lang, build):
    s = PluginScope(task_class=t, language=l, build_system=b)
    def dim_ok(dim, v):
        match dim:
            case Wildcard(): return True
            case Concrete(value): return value == v
    assert s.matches(task=task, language=lang, build=build) == (
        dim_ok(t, task) and dim_ok(l, lang) and dim_ok(b, build)
    )


@given(t=scope_dims(), l=scope_dims(), b=scope_dims())
def test_specificity_is_concrete_count(t, l, b):
    s = PluginScope(task_class=t, language=l, build_system=b)
    expected = sum(1 for d in (t, l, b) if isinstance(d, Concrete))
    assert s.specificity() == expected
    assert 0 <= s.specificity() <= 3
```

State why it fails: `ModuleNotFoundError: codegenie.plugins.scope` — the module doesn't exist yet.

### Green — minimal pass
- Add `src/codegenie/plugins/__init__.py`.
- Add `src/codegenie/plugins/scope.py` with `Concrete`, `Wildcard`, `ScopeDim`, `PluginScope`, `parse`, `matches`, `specificity` — the minimum that turns every assertion green.

### Refactor
- Lift the per-dim regex (`^[a-z0-9_-]+$`) to a `Final` module constant with comment naming ADR-0010.
- Add a `__str__` on `PluginScope` that reproduces the parser input verbatim (`"task--lang--build"`) — needed by S2-03 loader error messages.
- Edge cases: E2 (Yarn Berry mis-routed to npm plugin) is exercised at the resolver level (S2-04); here, document the round-trip — `PluginScope.parse(str(scope)).value == scope` for any constructible scope (one extra Hypothesis property is cheap).
- Confirm `assert_never` lands in the `match` (forces mypy exhaustiveness across the closed `Concrete | Wildcard` union).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/__init__.py` | NEW — package marker for the kernel namespace (load-bearing for S1-05 import-linter contracts). |
| `src/codegenie/plugins/scope.py` | NEW — the four exports per ADR-0010 §Decision §1. |
| `tests/unit/plugins/__init__.py` | NEW — test package marker. |
| `tests/unit/plugins/test_scope.py` | NEW — unit + Hypothesis property tests. |

## Out of scope

- **`PluginRegistry`, `@register_plugin`, resolver** — handled by S2-01 / S2-04. This story only ships the value type the registry stores.
- **`PluginManifest` YAML loader** — handled by S2-02; uses `PluginScope.parse` from inside `from_yaml`.
- **`extends`-chain walker** — handled by S2-04; consumes `PluginScope.matches` and `PluginScope.specificity`.
- **`ConcreteResolution | UniversalFallbackResolution` sum** — handled by S2-04 (lives in `resolution.py`, not `scope.py`).
- **Re-using `TaskClassId`/`Language`/`PackageManager` newtypes** inside `Concrete.value` — ADR-0010 §Decision §1 deliberately keeps `Concrete.value: str` so `PluginScope` is task-class-agnostic; call sites wrap with the right newtype.

## Notes for the implementer

- **`@dataclass(frozen=True, slots=True)` matters** for `Concrete` and `Wildcard` — `frozen` so scope instances are hashable (registry keys); `slots` for memory and accidental-attribute-assignment defense. Don't use `Pydantic` here — the data is too small and `match` exhaustiveness on Pydantic discriminated unions is awkward vs. native sum types.
- **`ScopeDim: TypeAlias = Concrete | Wildcard`** must be a `TypeAlias`, not a bare union, so `mypy` and `pyright` (if anyone ever runs it) treat it as a closed sum.
- **`match` must include `case Wildcard():` (with parens), not `case Wildcard:`** — the former pattern-matches the type, the latter binds the name. Easy to get wrong; the existing Phase-2 code in `src/codegenie/probes/layer_b/` has the right pattern.
- **`assert_never` import** comes from `typing` in Python 3.11+ (the repo's minimum). Always include the `case _: assert_never(...)` arm even though the union is closed — it's the one line that makes adding a future `Negation`/`Range` variant break the build instead of silently misbehaving.
- **Hypothesis is already in `[dev]` dependencies** — verify with `grep hypothesis pyproject.toml` before importing; no new dep needed.
- **`PluginScope.parse` must reject `"a--b--*"` with `b` empty**, not silently coerce empty strings to wildcards. The smart constructor is the boundary; ADR-0010 §Pattern fit explicitly forbids `Literal["*"]`-collapsed-to-`str`.
