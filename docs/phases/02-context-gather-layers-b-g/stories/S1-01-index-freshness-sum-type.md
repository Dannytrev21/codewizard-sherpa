# Story S1-01 — `IndexFreshness` sum type at `codegenie.indices.freshness`

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Ready
**Effort:** M
**Depends on:** —
**ADRs honored:** 02-ADR-0006

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
- [ ] **AC-2.** Every concrete model in `freshness.py` is Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` and a `kind: Literal["..."]` field with a unique discriminator string (`"fresh"`, `"stale"`, `"commits_behind"`, `"digest_mismatch"`, `"coverage_gap"`, `"indexer_error"`).
- [ ] **AC-3.** `StaleReason = Annotated[Union[CommitsBehind, DigestMismatch, CoverageGap, IndexerError], Field(discriminator="kind")]` and `IndexFreshness = Annotated[Union[Fresh, Stale], Field(discriminator="kind")]`; type aliases are at module scope; importable directly.
- [ ] **AC-4.** For every variant, `model_validate_json(instance.model_dump_json()) == instance` (round-trip identity, parametrized).
- [ ] **AC-5.** Constructing `Stale(reason=…)` succeeds for every `StaleReason` variant; constructing `Stale(reason={"kind": "bogus_reason", ...})` raises `pydantic.ValidationError`.
- [ ] **AC-6.** Exhaustive `match` test over every `StaleReason` variant terminates with `assert_never(reason)` in the default arm; with all four arms present, mypy is silent. Removing one arm and re-running `mypy --warn-unreachable` on this module is a build error (verified by S1-11 once the per-module override lands; this story documents the expectation in the test docstring).
- [ ] **AC-7.** The TDD plan's red test exists, was committed, and is green.
- [ ] **AC-8.** `model_construct` is **not** used anywhere in `freshness.py` (the forbidden-patterns rule lands in S1-11 but the discipline starts here).
- [ ] **AC-9.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/indices/test_freshness.py` all pass on the touched files.

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


def test_all_exports_full_variant_set() -> None:
    import codegenie.indices as m
    assert set(m.__all__) == {
        "IndexFreshness", "Fresh", "Stale", "StaleReason",
        "CommitsBehind", "DigestMismatch", "CoverageGap", "IndexerError",
    }
```

Run — confirm `ImportError: cannot import name 'IndexFreshness' from 'codegenie.indices'`. Commit as the red marker.

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
| `tests/unit/indices/test_freshness.py` | Red-then-green tests covering round-trip identity, `extra="forbid"`, `frozen=True`, exhaustive `match`. |

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
