# Story S1-01 — `IndexFreshness` sum type at `codegenie.indices.freshness`

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Done (executed by phase-story-executor 2026-05-15; attempt log: [`_attempts/S1-01.md`](_attempts/S1-01.md))
**Effort:** M
**Depends on:** —
**ADRs honored:** 02-ADR-0006

## Execution evidence

All 12 acceptance criteria pass with runtime evidence (see [`_attempts/S1-01.md`](_attempts/S1-01.md) §"Acceptance criteria — evidence" for the AC-by-AC mapping). Summary:

- Tests added: 10 unit tests in [`tests/unit/indices/test_freshness.py`](../../../../tests/unit/indices/test_freshness.py) + 1 Hypothesis property test in [`tests/property/test_index_freshness_roundtrip.py`](../../../../tests/property/test_index_freshness_roundtrip.py).
- Implementation: [`src/codegenie/indices/__init__.py`](../../../../src/codegenie/indices/__init__.py) + [`src/codegenie/indices/freshness.py`](../../../../src/codegenie/indices/freshness.py) (stdlib + Pydantic only; no logger, no I/O, no registry — Open/Closed seam for new index sources lives in S1-02).
- Gates: `ruff format --check`, `ruff check`, `mypy --strict src/`, full pytest suite (1562 passed, coverage 93.20%).
- Dep change: added `hypothesis` to `[project.optional-dependencies].dev` and regenerated `uv.lock`.

## Validation notes

Hardened by `phase-story-validator` on 2026-05-15 (report: [`_validation/S1-01-index-freshness-sum-type.md`](_validation/S1-01-index-freshness-sum-type.md)). Four critic lenses (coverage, test-quality, consistency, design-patterns) ran; verdict **HARDENED**, no `RESCUE`. Substantive changes:

1. **AC-4 tightened — round-trip preserves the *typed nested reason*, not just the top-level Stale type.** A mutation that drops the `Field(discriminator="kind")` wrapper from `StaleReason` could pass the original AC-4 (Stale comes back as Stale) yet leave `decoded.reason` as a plain dict. Added per-variant assertion that `type(decoded.reason) is type(instance.reason)` for every `Stale` case.
2. **AC-2 tightened — discriminator strings are pinned values, not implementation choices.** Each `kind` Literal must be exactly the string named in `02-ADR-0006 §Decision` and `phase-arch-design.md §"Data model"`. A swap (e.g., `CommitsBehind.kind = "digest_mismatch"`) would route correctly through the round-trip and break every real consumer; now caught by a dedicated assertion.
3. **AC-6a added — exhaustive `match` test at the top-level `IndexFreshness` (Fresh | Stale)**, symmetric with the existing `StaleReason` exhaustive test. The renderer (S8-01) must `match` at this layer; the discipline is rehearsed in this story.
4. **AC-10 added — JSON-shape pin.** A representative `Fresh` and `Stale(reason=…)` instance's `model_dump()` is compared against a literal dict (`{"kind": "fresh", "indexed_at": …}` / `{"kind": "stale", "reason": {"kind": "commits_behind", "n": …, "last_indexed": …}}`). Round-trip identity alone tolerates a symmetric rename of `kind` → `tag`; the JSON-shape pin does not.
5. **AC-11 added — Hypothesis property test `tests/property/test_index_freshness_roundtrip.py`**, scaffolding the deliverable named in `02-ADR-0006 §Consequences` (`tests/property/test_index_freshness_roundtrip.py` — Hypothesis: any `IndexFreshness` round-trips identity-equal). `High-level-impl.md` Step 7 §247 references this test as *"already may exist from Step 1's freshness tests; extended here for portfolio-wide round-trip"* — Step 1 (this story) owns the scaffold.
6. **Notes for implementer extended — Open/Closed seam handoff to S1-02.** S1-02 lands `@register_index_freshness_check(index_name: IndexName)` on top of this module. `freshness.py` MUST remain pure data (no decorator, no registry dict, no I/O) so S1-02 can layer the registry in `src/codegenie/indices/registry.py` without circular imports.
7. **Notes for implementer extended — variant-set extension is intentionally ADR-amendment-gated** (named-trigger per ADR-0006 §Consequences). Adding a fifth `StaleReason` is NOT an Open/Closed-by-addition seam — that's by design. The `assert_never` in every consumer's `match` is the structural enforcement against silent widening.

No `RESCUE`-tier findings. No `NEEDS RESEARCH` (Stage 3 skipped — every gap was answerable from arch + ADR-0006).

## Context

`IndexFreshness` is the typed answer Phase 2 gives to commitment §2.3 (silent index staleness is the worst failure mode in the system). The probe (`IndexHealthProbe` / B2) returns it; the renderer (`ConfidenceSection`) consumes it; Phase 3 plugins read it as bundle metadata. This story is the very first thing landed in Phase 2 — every later step depends on this discriminated union existing, byte-stable through JSON round-trip, and exhaustively pattern-matchable.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #2 — IndexFreshness sum type` — public interface, smart-constructor commitment, why the package lives outside `probes/`.
  - `../phase-arch-design.md §"Data model"` — the exact Pydantic shape (`frozen=True, extra="forbid"`, `Literal["..."]` discriminators on `kind`, `Annotated[Union[...], Field(discriminator="kind")]`).
  - `../phase-arch-design.md §"Design patterns applied"` row 1 — sum type / make-illegal-states-unrepresentable; why `Optional[str]` and `Null Object` were rejected.
  - `../phase-arch-design.md §"Edge cases"` row 11 — the load-bearing stale-scip case asserts exact typed outcome.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0006-index-freshness-sum-type-location.md` — 02-ADR-0006 — `IndexFreshness` lives at `codegenie.indices.freshness`, with one Phase-2 consumer (`report/confidence_section.py`); `AdapterConfidence`/`IndexConfidence` are NOT Phase 2.
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — composes: typed freshness is the gather-side honest-confidence surface a Planner will later read.
- **Source design:**
  - `../final-design.md §"Synthesis ledger" — IndexFreshness sum type, single Phase-2 consumer` — the synthesizer's commitment to "one name, one module, one consumer."
- **Existing code:**
  - `src/codegenie/parsers/safe_yaml.py` — Pydantic-shaped Phase 1 style; mirror its `frozen=True, extra="forbid"` discipline.
  - `src/codegenie/probes/base.py` — the `ProbeOutput.schema_slice: dict[str, Any]` boundary `IndexFreshness` values flow through.
- **External docs (only if directly relevant):**
  - https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions — discriminated-union shape (`Annotated[Union[...], Field(discriminator="kind")]`).

## Goal

Implement `src/codegenie/indices/{__init__.py,freshness.py}` as a Pydantic discriminated-union sum type — `IndexFreshness = Fresh | Stale(reason: StaleReason)` with `StaleReason = CommitsBehind | DigestMismatch | CoverageGap | IndexerError` — that round-trips identity through `model_dump_json` / `model_validate_json` and is exhaustively matchable with `assert_never`.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/indices/__init__.py` exports the full variant set in `__all__`: `["IndexFreshness", "Fresh", "Stale", "StaleReason", "CommitsBehind", "DigestMismatch", "CoverageGap", "IndexerError"]`. Each name resolves to a class object importable as `from codegenie.indices import Fresh, Stale, …`.
- [ ] **AC-2.** Every concrete model in `freshness.py` is Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` and a `kind: Literal["..."]` field with the **exact** discriminator string named in `02-ADR-0006 §Decision` / `phase-arch-design.md §"Data model"`: `Fresh.kind == "fresh"`, `Stale.kind == "stale"`, `CommitsBehind.kind == "commits_behind"`, `DigestMismatch.kind == "digest_mismatch"`, `CoverageGap.kind == "coverage_gap"`, `IndexerError.kind == "indexer_error"`. Each discriminator string is unique within its `Union`. The strings are a cross-ADR contract; changing one is an ADR amendment, not a refactor.
- [ ] **AC-3.** `StaleReason = Annotated[Union[CommitsBehind, DigestMismatch, CoverageGap, IndexerError], Field(discriminator="kind")]` and `IndexFreshness = Annotated[Union[Fresh, Stale], Field(discriminator="kind")]`; type aliases are at module scope; importable directly.
- [ ] **AC-4.** For every variant, `TypeAdapter(IndexFreshness).validate_json(TypeAdapter(IndexFreshness).dump_json(instance)) == instance` (round-trip identity, parametrized). For every `Stale(reason=R)` instance the round-trip additionally preserves the nested typed reason: `type(decoded.reason) is type(instance.reason)`. (Top-level type equality alone is insufficient — a regression that drops the discriminator wrapper from `StaleReason` could leave `decoded.reason` as a plain `dict` while `Stale` itself still round-trips equal.)
- [ ] **AC-5.** Constructing `Stale(reason=…)` succeeds for every `StaleReason` variant; constructing `Stale.model_validate({"kind": "stale", "reason": {"kind": "bogus_reason", "x": 1}})` raises `pydantic.ValidationError`. Constructing `TypeAdapter(IndexFreshness).validate_python({"kind": "bogus_freshness"})` likewise raises (the top-level discriminator is enforced).
- [ ] **AC-6.** Exhaustive `match` test over every `StaleReason` variant terminates with `assert_never(reason)` in the default arm; with all four arms present, mypy is silent. Removing one arm and re-running `mypy --warn-unreachable` on this module is a build error (verified by S1-11 once the per-module override lands; this story documents the expectation in the test docstring).
- [ ] **AC-6a.** Exhaustive `match` test over the **top-level** `IndexFreshness` (Fresh | Stale) terminates with `assert_never(freshness)` in the default arm. Symmetric with AC-6; mirrors the discipline `report/confidence_section.py` (S8-01) will inherit.
- [ ] **AC-7.** The TDD plan's red test exists, was committed, and is green.
- [ ] **AC-8.** `model_construct` is **not** used anywhere in `freshness.py` (the forbidden-patterns rule lands in S1-11 but the discipline starts here); verified by a source-scan test.
- [ ] **AC-9.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/indices/test_freshness.py tests/property/test_index_freshness_roundtrip.py` all pass on the touched files.
- [ ] **AC-10.** **JSON shape pin.** `Fresh(indexed_at=datetime(2026,1,1,tzinfo=timezone.utc)).model_dump(mode="json")` has exactly `{"kind", "indexed_at"}` as its keys with `kind == "fresh"`. `Stale(reason=CommitsBehind(n=3, last_indexed="abc1234")).model_dump(mode="json")` equals `{"kind": "stale", "reason": {"kind": "commits_behind", "n": 3, "last_indexed": "abc1234"}}` — nested `kind` is present at both levels; no extra fields. Catches a symmetric `kind → tag` rename that AC-4's round-trip identity would tolerate.
- [ ] **AC-11.** `tests/property/test_index_freshness_roundtrip.py` exists, uses Hypothesis to build arbitrary `IndexFreshness` values (one composite strategy per variant), and asserts round-trip identity (`TypeAdapter(IndexFreshness)` dump/load returns an equal value AND preserves the nested `Stale.reason` concrete type). Required by `02-ADR-0006 §Consequences`; referenced by Step 7 (`High-level-impl.md §247`) as already existing from Step 1.

## Implementation outline

1. Create `src/codegenie/indices/__init__.py` re-exporting the variant set via `__all__`.
2. Create `src/codegenie/indices/freshness.py` with the four `StaleReason` variants, then `Fresh` and `Stale`, then the two `Annotated[Union[...], Field(discriminator="kind")]` aliases.
3. Use `pydantic.BaseModel` + `ConfigDict(frozen=True, extra="forbid")`; populate every field with explicit types (`n: int`, `last_indexed: str` raw — commit shas are str at the I/O boundary by design, see `../phase-arch-design.md §"Data model"`).
4. Add module docstring naming the consumer (`codegenie.report.confidence_section`) and pointing at ADR-0006.
5. Write the red test first (see TDD plan); confirm `ImportError`/`AttributeError`; commit.
6. Implement the module; confirm the test goes green.
7. Refactor: add docstrings on each class naming when the variant is constructed; ensure `__all__` is sorted; re-run gates.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/indices/test_freshness.py`

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import assert_never

import pytest
from pydantic import ValidationError

from codegenie.indices import (
    CommitsBehind,
    CoverageGap,
    DigestMismatch,
    Fresh,
    IndexerError,
    IndexFreshness,
    Stale,
    StaleReason,
)


STALE_REASONS: list[StaleReason] = [
    CommitsBehind(n=3, last_indexed="abc1234"),
    DigestMismatch(expected="sha256:aaa", actual="sha256:bbb"),
    CoverageGap(files_indexed=900, files_in_repo=1000),
    IndexerError(message="strace_unavailable"),
]

FRESHNESS_INSTANCES: list[IndexFreshness] = [
    Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=timezone.utc)),
    *(Stale(reason=r) for r in STALE_REASONS),
]


@pytest.mark.parametrize("instance", FRESHNESS_INSTANCES)
def test_index_freshness_roundtrip_identity(instance: IndexFreshness) -> None:
    # arrange: a freshness value
    # act: dump → load via discriminated union
    from pydantic import TypeAdapter

    adapter = TypeAdapter(IndexFreshness)
    encoded = adapter.dump_json(instance)
    decoded = adapter.validate_json(encoded)
    # assert: round-trip is identity; the discriminator routes correctly.
    assert decoded == instance
    assert type(decoded) is type(instance)
    # AC-4: nested reason concrete type is preserved (guards against a
    # regression that drops Field(discriminator="kind") from StaleReason,
    # which would leave decoded.reason as a plain dict while Stale itself
    # still round-trips equal).
    if isinstance(instance, Stale):
        assert isinstance(decoded, Stale)
        assert type(decoded.reason) is type(instance.reason)


def test_discriminator_strings_are_exactly_pinned() -> None:
    """AC-2: discriminator strings are a cross-ADR contract (02-ADR-0006).
    A symmetric swap (CommitsBehind.kind = "digest_mismatch" + DigestMismatch.kind = "commits_behind")
    would pass the round-trip test but break every real consumer; pin the exact strings."""
    assert Fresh(indexed_at=datetime(2026, 1, 1, tzinfo=timezone.utc)).kind == "fresh"
    assert Stale(reason=CommitsBehind(n=1, last_indexed="x")).kind == "stale"
    assert CommitsBehind(n=1, last_indexed="x").kind == "commits_behind"
    assert DigestMismatch(expected="a", actual="b").kind == "digest_mismatch"
    assert CoverageGap(files_indexed=1, files_in_repo=2).kind == "coverage_gap"
    assert IndexerError(message="x").kind == "indexer_error"


def test_json_shape_pinned() -> None:
    """AC-10: round-trip identity alone tolerates a symmetric `kind → tag` rename;
    the JSON-shape pin does not."""
    fresh_dump = Fresh(indexed_at=datetime(2026, 1, 1, tzinfo=timezone.utc)).model_dump(mode="json")
    assert fresh_dump["kind"] == "fresh"
    assert "indexed_at" in fresh_dump
    assert set(fresh_dump.keys()) == {"kind", "indexed_at"}

    stale_dump = Stale(reason=CommitsBehind(n=3, last_indexed="abc1234")).model_dump(mode="json")
    assert stale_dump == {
        "kind": "stale",
        "reason": {"kind": "commits_behind", "n": 3, "last_indexed": "abc1234"},
    }


def test_top_level_unknown_kind_is_rejected() -> None:
    """AC-5: the top-level IndexFreshness discriminator is enforced."""
    from pydantic import TypeAdapter

    adapter = TypeAdapter(IndexFreshness)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "bogus_freshness"})


def test_stale_reason_rejects_unknown_kind() -> None:
    # Construction via raw dict must reject an unknown discriminator.
    with pytest.raises(ValidationError):
        Stale.model_validate({"kind": "stale", "reason": {"kind": "bogus", "x": 1}})


def test_models_are_frozen_and_forbid_extra() -> None:
    inst = CommitsBehind(n=1, last_indexed="abc")
    with pytest.raises(ValidationError):
        # extra="forbid"
        CommitsBehind.model_validate({"kind": "commits_behind", "n": 1, "last_indexed": "x", "extra": "no"})
    with pytest.raises(ValidationError):
        # frozen=True
        inst.n = 2  # type: ignore[misc]


def test_match_is_exhaustive_over_stale_reason() -> None:
    """If a future contributor adds a fifth StaleReason without updating this
    match, mypy --warn-unreachable on this module (S1-11 override) will flag
    the `assert_never(reason)` line. At runtime this test only confirms every
    current variant routes."""
    seen: set[str] = set()
    for reason in STALE_REASONS:
        match reason:
            case CommitsBehind():
                seen.add("commits_behind")
            case DigestMismatch():
                seen.add("digest_mismatch")
            case CoverageGap():
                seen.add("coverage_gap")
            case IndexerError():
                seen.add("indexer_error")
            case _ as unexpected:
                assert_never(unexpected)
    assert seen == {"commits_behind", "digest_mismatch", "coverage_gap", "indexer_error"}


def test_match_is_exhaustive_over_index_freshness_top_level() -> None:
    """AC-6a: symmetric with test_match_is_exhaustive_over_stale_reason.
    The renderer (S8-01 — `report/confidence_section.py`) must `match` at this
    layer; the exhaustive discipline is rehearsed here so a future third
    top-level variant cannot be added without breaking every consumer's mypy
    build (via S1-11's `mypy --warn-unreachable` per-module override)."""
    seen: set[str] = set()
    for freshness in FRESHNESS_INSTANCES:
        match freshness:
            case Fresh():
                seen.add("fresh")
            case Stale():
                seen.add("stale")
            case _ as unexpected:
                assert_never(unexpected)
    assert seen == {"fresh", "stale"}


def test_all_exports_full_variant_set() -> None:
    import codegenie.indices as m
    assert set(m.__all__) == {
        "IndexFreshness", "Fresh", "Stale", "StaleReason",
        "CommitsBehind", "DigestMismatch", "CoverageGap", "IndexerError",
    }


def test_freshness_module_has_no_model_construct() -> None:
    """AC-8: `model_construct` bypasses validation; the forbidden-patterns
    rule lands in S1-11, but the discipline starts here. Source-scan guard."""
    from pathlib import Path
    import codegenie.indices.freshness as freshness_mod
    source = Path(freshness_mod.__file__).read_text()
    assert "model_construct" not in source
```

Run — confirm `ImportError: cannot import name 'IndexFreshness' from 'codegenie.indices'`. Commit as the red marker.

**Property test** — `tests/property/test_index_freshness_roundtrip.py` (AC-11; required by `02-ADR-0006 §Consequences`):

```python
from __future__ import annotations

from datetime import datetime, timezone

from hypothesis import given, strategies as st
from pydantic import TypeAdapter

from codegenie.indices import (
    CommitsBehind, CoverageGap, DigestMismatch, Fresh, IndexFreshness,
    IndexerError, Stale, StaleReason,
)


# Strategies — one per concrete variant.
_aware_datetimes = st.datetimes(
    min_value=datetime(2020, 1, 1), max_value=datetime(2030, 1, 1),
    timezones=st.just(timezone.utc),
)

_commits_behind = st.builds(
    CommitsBehind,
    n=st.integers(min_value=0, max_value=10_000),
    last_indexed=st.text(alphabet="0123456789abcdef", min_size=7, max_size=40),
)
_digest_mismatch = st.builds(
    DigestMismatch,
    expected=st.text(min_size=1, max_size=80),
    actual=st.text(min_size=1, max_size=80),
)
_coverage_gap = st.builds(
    CoverageGap,
    files_indexed=st.integers(min_value=0, max_value=1_000_000),
    files_in_repo=st.integers(min_value=0, max_value=1_000_000),
)
_indexer_error = st.builds(IndexerError, message=st.text(min_size=1, max_size=120))

_stale_reasons: st.SearchStrategy[StaleReason] = st.one_of(
    _commits_behind, _digest_mismatch, _coverage_gap, _indexer_error,
)
_freshness: st.SearchStrategy[IndexFreshness] = st.one_of(
    st.builds(Fresh, indexed_at=_aware_datetimes),
    st.builds(Stale, reason=_stale_reasons),
)

_adapter: TypeAdapter[IndexFreshness] = TypeAdapter(IndexFreshness)


@given(value=_freshness)
def test_index_freshness_roundtrips_identity(value: IndexFreshness) -> None:
    decoded = _adapter.validate_json(_adapter.dump_json(value))
    # Top-level: identity-equal and concrete type preserved.
    assert decoded == value
    assert type(decoded) is type(value)
    # Nested reason for Stale: concrete type preserved (guards against
    # silent loss of Field(discriminator="kind") on StaleReason).
    if isinstance(value, Stale):
        assert isinstance(decoded, Stale)
        assert type(decoded.reason) is type(value.reason)
```

### Green — make it pass

Write `src/codegenie/indices/freshness.py`:

```python
from __future__ import annotations
from datetime import datetime
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field

class CommitsBehind(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["commits_behind"] = "commits_behind"
    n: int
    last_indexed: str  # commit sha — raw str at the I/O boundary by design

class DigestMismatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["digest_mismatch"] = "digest_mismatch"
    expected: str
    actual: str

class CoverageGap(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["coverage_gap"] = "coverage_gap"
    files_indexed: int
    files_in_repo: int

class IndexerError(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["indexer_error"] = "indexer_error"
    message: str

StaleReason = Annotated[
    Union[CommitsBehind, DigestMismatch, CoverageGap, IndexerError],
    Field(discriminator="kind"),
]

class Fresh(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["fresh"] = "fresh"
    indexed_at: datetime

class Stale(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["stale"] = "stale"
    reason: StaleReason

IndexFreshness = Annotated[Union[Fresh, Stale], Field(discriminator="kind")]
```

Then `src/codegenie/indices/__init__.py`:

```python
from codegenie.indices.freshness import (
    CommitsBehind, CoverageGap, DigestMismatch, Fresh, IndexFreshness,
    IndexerError, Stale, StaleReason,
)

__all__ = [
    "CommitsBehind", "CoverageGap", "DigestMismatch", "Fresh", "IndexFreshness",
    "IndexerError", "Stale", "StaleReason",
]
```

### Refactor — clean up

- Add a module-level docstring on `freshness.py` naming the consumer (`codegenie.report.confidence_section`) and ADR-0006.
- Add per-class docstrings (one line each) naming when the variant is constructed (e.g., `CommitsBehind`: "constructed by `IndexHealthProbe` when `last_indexed_commit != git rev-parse HEAD`"; `IndexerError`: "constructed when the upstream indexer is unavailable; messages are stable identifiers like `'strace_unavailable'`, `'timeout'`, `'upstream_X_unavailable'`").
- Sort `__all__` alphabetically.
- Confirm: no `model_construct` calls (S1-11 will enforce — fail-loud here).
- Confirm: no logger / no I/O / stdlib + pydantic only (S1-11's `mypy --warn-unreachable` override on `codegenie.indices/**` is the structural protection).
- Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/indices/ tests/unit/indices/test_freshness.py`, `pytest tests/unit/indices/test_freshness.py -v`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/indices/__init__.py` | New package; re-export the eight names; pin `__all__`. |
| `src/codegenie/indices/freshness.py` | New module; the discriminated-union sum type. |
| `tests/unit/indices/test_freshness.py` | Red-then-green tests covering round-trip identity (incl. nested `Stale.reason` type preservation), discriminator-string pin, JSON-shape pin, `extra="forbid"`, `frozen=True`, exhaustive `match` over both `StaleReason` and top-level `IndexFreshness`, source-scan for `model_construct`. |
| `tests/property/__init__.py` | New package marker (if not already present from Phase 1 — adapt at impl time). |
| `tests/property/test_index_freshness_roundtrip.py` | Hypothesis property test (AC-11); required by `02-ADR-0006 §Consequences`. |

## Out of scope

- **`@register_index_freshness_check` decorator-registry** — handled by S1-02; the freshness module ships first, the registry layers on top.
- **`IndexHealthProbe`** — handled by S4-01; it constructs `IndexFreshness` values but does not define them.
- **`ConfidenceSection` renderer with exhaustive `match` + `assert_never` enforcement** — handled by S8-01; the consumer ships much later.
- **`mypy --warn-unreachable` per-module override on `codegenie.indices/**`** — handled by S1-11 (the `pyproject.toml` rollout).
- **`AdapterConfidence` / `IndexConfidence` type** — explicitly NOT in Phase 2 per 02-ADR-0006; the Phase 3 plugin owns adapter-side confidence.
- **Phase 1 retrofit** — Phase 1 probes use `confidence: Literal["high","medium","low"]` strings; Phase 2 does not migrate them. New code uses `IndexFreshness`.

## Notes for the implementer

- **`extra="forbid"` is load-bearing.** Pydantic's default permissive behavior on unknown keys silently swallows a typo (`commit_behind` instead of `commits_behind`) and the discriminated union mis-routes. `extra="forbid"` is the Phase 2 discipline; do not relax it.
- **`last_indexed: str` is the I/O-boundary type — not a newtype.** Commit SHAs come from `git rev-parse HEAD` as raw bytes/strings; this module does not import S1-05's `IndexId`/`SkillId` newtypes (those are *kernel* identifiers, not git-commit SHAs). Resist the temptation to invent a `CommitSha` newtype here — that's a separate, larger story and is not in the architecture.
- **No timezone-naïve datetimes.** `Fresh.indexed_at: datetime` accepts any `datetime`, but the producer (`IndexHealthProbe` in S4-01) MUST construct timezone-aware UTC datetimes. The test uses `datetime(2026,5,14,tzinfo=timezone.utc)`; do not change to naïve.
- **Do not co-locate with `probes/layer_b/index_health.py`.** 02-ADR-0006 explicitly places this in `codegenie.indices.freshness` so the renderer (`report/confidence_section.py`) can consume it without pulling in the probe registry. The mypy `--warn-unreachable` per-module override (S1-11) is on `codegenie.indices/**`; co-locating defeats the surgical-rollout discipline (final-design Open Q 5).
- **`TypeAdapter` is the canonical way to drive a discriminated-union round-trip in tests.** `IndexFreshness` is an `Annotated[Union, Field(discriminator=…)]` type alias, not a class — there is no `IndexFreshness.model_validate_json`. Use `pydantic.TypeAdapter(IndexFreshness)` and call its `.dump_json` / `.validate_json` methods.
- **`assert_never` from `typing`.** Python 3.11+ ships it in `typing`; do not import from `typing_extensions` (Phase 0 baseline is 3.11+, see `pyproject.toml`).
- **Mutation discipline.** A frequent silent regression here is "I added a fifth `StaleReason` and forgot to extend `StaleReason = Union[...]`." S1-11's `mypy --warn-unreachable` on this module is the structural safety net; this story's test makes the discipline observable today.
- **Open/Closed seam for new index sources lives in S1-02, NOT here.** S1-02 introduces `@register_index_freshness_check(index_name: IndexName)` in `src/codegenie/indices/registry.py`. `freshness.py` MUST remain pure data: no decorator, no registry dict, no I/O, no logger, no imports beyond stdlib + Pydantic. The registry layers on top by import; the seam is "new index source → new file + new decorator," never an edit to `freshness.py`. Resist any temptation to "while we're here" pre-stub the registry — it belongs in S1-02.
- **Variant-set extension is intentionally ADR-amendment-gated, not Open/Closed-by-addition.** Adding a fifth `StaleReason` (e.g., a hypothetical `IndexerRefused` for a future trust-policy reason) requires an amendment to 02-ADR-0006 — named-trigger discipline mirroring 02-ADR-0002. The `assert_never` arms in every consumer's `match` (this story's tests, S8-01's renderer, S1-11's per-module `--warn-unreachable` override) are the structural enforcement: silent widening via Pydantic `Union` extension is impossible without breaking the renderer's exhaustive match. The pattern fit is "Sum type + Make-illegal-states-unrepresentable" — *not* a Plugin/Strategy/Registry over variants. That is correct; do not architect for "pluggable freshness reasons."
- **Discriminator strings are a cross-ADR contract.** The six strings (`"fresh"`, `"stale"`, `"commits_behind"`, `"digest_mismatch"`, `"coverage_gap"`, `"indexer_error"`) appear by name in `02-ADR-0006 §Decision`, `phase-arch-design.md §"Data model"`, and (forthcoming) `confidence_section.py` golden files. AC-2 + AC-10 pin them. Treat a rename as an ADR-touching change, not a refactor.
- **The property test (AC-11) is small and additive.** ~50 LOC; one Hypothesis strategy per variant; one assertion (round-trip identity + nested-type preservation). It is a deliverable named in `02-ADR-0006 §Consequences` and referenced by Step 7 of `High-level-impl.md` as already existing from Step 1. Skipping it is a Consistency violation against the ADR.
