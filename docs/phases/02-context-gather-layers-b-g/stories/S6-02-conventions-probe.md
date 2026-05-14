# Story S6-02 — `ConventionsProbe` Layer D

**Step:** Step 6 — Ship Layer D + E + G probes (skills, conventions, ADRs, ownership, scanners)
**Status:** Ready
**Effort:** S
**Depends on:** S2-02 (`ConventionsCatalogLoader` with discriminated-union pattern types + `ConventionResult = Pass | Fail | NotApplicable`)
**ADRs honored:** 02-ADR-0006 (typed sum types as discriminated unions — `ConventionResult` matches the IndexFreshness shape), Phase 1 ADR-0006 (`safe_yaml` chokepoint — catalogs load exclusively via `safe_yaml.load`)
**Phase-2 commitment honored:** "Facts, not judgments" (CLAUDE.md) — the probe reports `Pass | Fail | NotApplicable` per convention; it does not summarize, weight, or aggregate. The Planner decides what to do with the per-rule outcomes.

## Context

Org conventions like "All Node services must use tini as PID 1" or "Runtime image must not include npm/pnpm/yarn" are the boring, ubiquitous failure mode in autonomous migrations: a generic recipe produces a perfectly valid Dockerfile that violates the org's unwritten rules and gets bounced at review. The `ConventionsCatalogLoader` (S2-02) loads those rules from `~/.codegenie/conventions/*.yaml` into a `Catalog` of pattern-typed rules; this probe applies the catalog to the repo snapshot and emits one `ConventionResult` per rule.

The discriminated union is load-bearing. `ConventionResult = Pass | Fail | NotApplicable` is exhaustive — `mypy --warn-unreachable` enforces the `match` to be total. `Pass` means "the convention was checked and the repo conforms." `Fail` means "the convention was checked and the repo violates it, here is the file:line evidence." `NotApplicable` means "the convention's prerequisites aren't met" (e.g., the `dockerfile_pattern` convention on a repo with no Dockerfile). Conflating `NotApplicable` with `Pass` would silently mark services as conforming to rules they were never checked against — the "passing tests on a disabled feature" failure mode the toolkit's Open/Closed gap names verbatim.

The probe reads the catalog via `ConventionsCatalogLoader.load_all()`; the loader does `safe_yaml.load` on each `*.yaml` under `~/.codegenie/conventions/`, then builds a typed `Catalog`. The probe calls `Catalog.apply(repo: RepoSnapshot)` and projects the returned `list[ConventionResult]` into a Pydantic-modeled slice.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md` §"Component design" #10 `ConventionsCatalogLoader`](../phase-arch-design.md) — pattern types as a Pydantic discriminated union; one `match` per pattern type with `assert_never`.
  - [`../phase-arch-design.md` §"Design patterns applied"](../phase-arch-design.md) — discriminated unions for every state machine.
  - [`../phase-arch-design.md` §"Data model"](../phase-arch-design.md) `ConventionResult = Pass | Fail | NotApplicable`.
- **Phase ADRs:**
  - [`../ADRs/0006-index-freshness-sum-type-location.md`](../ADRs/0006-index-freshness-sum-type-location.md) — the same sum-type discipline `ConventionResult` follows: typed reason, not stringly-typed.
- **Source design:**
  - [`../High-level-impl.md` §"Step 6"](../High-level-impl.md) — Conventions uses `ConventionsCatalogLoader` (Step 2).
  - [`../../localv2.md` §5.4 D5 ConventionProbe](../../../localv2.md) — example catalog with `dockerfile_pattern`, `dockerfile_pattern_inverted`, `file_pattern`, `missing_file` types.
- **Existing kernel:**
  - `src/codegenie/conventions/catalog.py` (S2-02) — `Catalog.apply(repo: RepoSnapshot) -> list[ConventionResult]`.
  - `src/codegenie/conventions/model.py` (S2-02) — `ConventionResult` discriminated union; `Pass`, `Fail`, `NotApplicable` Pydantic models with `Literal["pass"|"fail"|"not_applicable"]` discriminators.
  - `src/codegenie/probes/base.py` — `Probe` ABC + `@register_probe`.

## Goal

Implement `src/codegenie/probes/layer_d/conventions.py` as a `@register_probe(heaviness="light")` probe that calls `ConventionsCatalogLoader.load_all()`, applies the resulting catalog to the repo snapshot, and emits a `ConventionsSlice` Pydantic model with `additionalProperties: false`. Each rule's outcome is one of `Pass | Fail | NotApplicable`; the slice carries the full list (no aggregation, no summary counts beyond the trivial `len`).

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

- [ ] **AC-1.** `src/codegenie/probes/layer_d/conventions.py` exports exactly `__all__ = ["ConventionsProbe", "ConventionsSlice"]`.
- [ ] **AC-2.** `ConventionsSlice` is a Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` carrying: `results: tuple[ConventionResult, ...]`, `catalog_version: str | None` (None if the catalog YAML has no `version:` field), `rules_checked: int` (= `len(results)`).
- [ ] **AC-3.** `ConventionsProbe` is `@register_probe(heaviness="light")`; `probe_id = ProbeId("conventions")`; `applies_to_tasks = ("*",)`; `applies_to_languages = ("*",)`; `timeout_seconds=15`.
- [ ] **AC-4.** `_run()` calls `ConventionsCatalogLoader(search_paths=self._resolve_search_paths(ctx)).load_all()`; on `Result.Ok(catalog)` invokes `catalog.apply(ctx.repo_snapshot)`; on `Result.Err(ConventionsError(...))` emits `confidence="low"` with the error reason.
- [ ] **AC-5.** **Discriminated-union round-trip.** A `ConventionResult` of each variant (`Pass`, `Fail`, `NotApplicable`) round-trips through `slice_.model_dump_json()` → `ConventionsSlice.model_validate_json(...)` with byte-identical re-serialization; each variant's `kind` discriminator is `"pass"`, `"fail"`, or `"not_applicable"` exactly.
- [ ] **AC-6.** **`NotApplicable` is not `Pass`.** A `dockerfile_pattern` rule run against a fixture with **no Dockerfile** yields `NotApplicable(rule_id=..., reason="dockerfile_absent")`, NEVER `Pass`. Mutation caught: any "if file doesn't exist, count it as pass" shortcut.
- [ ] **AC-7.** **`Fail` carries evidence.** A `dockerfile_pattern` rule that doesn't match in a fixture's Dockerfile yields `Fail(rule_id=..., file=PosixPath("Dockerfile"), line=None, snippet=None)` (line/snippet are `None` when the rule is whole-file "missing-pattern"; the smart constructor on `Fail` allows that); a `dockerfile_pattern_inverted` that finds a forbidden match populates `line` and `snippet`.
- [ ] **AC-8.** **`Pass` carries no evidence.** `Pass` has only `rule_id: str` and `kind: Literal["pass"]`; the model rejects `file=` / `line=` kwargs (`extra="forbid"`). Mutation caught: any future "let's add reason to Pass" — `Pass` is the empty-information variant; if you need to record *why* it passed, the convention check itself is the wrong shape.
- [ ] **AC-9.** **Catalog-load error.** Missing catalog directory yields `confidence="low"` slice, `results=()`, `errors=["catalog_search_path_missing: <path>"]`. The probe does not raise. Mutation caught: any future `raise FileNotFoundError` would break Phase 0 failure-isolation.
- [ ] **AC-10.** **Sub-schema validates.** `tests/unit/probes/layer_d/test_conventions.py::test_slice_matches_subschema` round-trips the JSON-dumped slice through `src/codegenie/schema/probes/layer_d/conventions.schema.json` (sub-schema lands in S6-08) with `additionalProperties: false` at every nesting level.
- [ ] **AC-11.** **`heaviness="light"`** — registry-verified.
- [ ] **AC-12.** **All four pattern types exercised.** The unit test parametrizes `dockerfile_pattern`, `dockerfile_pattern_inverted`, `file_pattern`, `missing_file` across `Pass` / `Fail` / `NotApplicable` outcomes — 12 cases. Each case asserts the typed variant and the discriminator value.
- [ ] **AC-13.** **`mypy --strict`** passes. The `match result:` block in any consumer (e.g., the test) is total — `case _: assert_never(result)` is reachable only on a future ADR-amend that adds a fourth variant.
- [ ] **AC-14.** **No shared "convention applier" abstraction.** Layer D's other marker probes (S6-03) do not extract a shared base class with this one. Architectural test: `inspect.getsource(conventions)` contains the probe class definition; it does not import from `adrs.py`, `policy.py`, etc. The shared kernel is `ConventionsCatalogLoader` and the `Probe` ABC — both Phase-2 chokepoints, not Rule-of-Three abstractions.
- [ ] **AC-15.** **Determinism.** Two consecutive `_run()` calls on the same fixture produce equal `model_dump_json(sort_keys=True)` output. Rule order is the catalog file order (preserved by `safe_yaml`'s pure-data mapping); within a rule, evidence is sorted by `(file, line)`.

## Implementation outline

1. Create `src/codegenie/probes/layer_d/conventions.py`:
   - Module docstring naming arch §"Component design" #10 + the "facts, not judgments" discipline.
   - `ConventionsSlice(BaseModel)` per AC-2.
   - `@register_probe(heaviness="light")` `class ConventionsProbe(Probe):`
     - `probe_id = ProbeId("conventions")`; applies-to / languages = `("*",)`; `timeout_seconds=15`.
     - `_run()` pattern-matches `ConventionsCatalogLoader.load_all()`:
       - `Ok(catalog)` → `catalog.apply(ctx.repo_snapshot)` → sort results by `rule_id` → wrap in `ConventionsSlice`.
       - `Err(ConventionsError(reason=...))` → `confidence="low"` with reason.
2. Write `tests/unit/probes/layer_d/test_conventions.py` per the TDD plan.

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/unit/probes/layer_d/test_conventions.py
"""Unit tests for ConventionsProbe (S6-02).

Each test is keyed to one or more ACs and names the mutation it catches
(Rule 9 — tests verify intent).
"""
from __future__ import annotations

from pathlib import Path
from typing import assert_never

import pytest

from codegenie.conventions.model import Fail, NotApplicable, Pass
from codegenie.probes.base import ProbeContext, _PROBE_REGISTRY
from codegenie.probes.layer_d import conventions as cp


def _write_catalog(catalog_dir: Path, rules: list[dict]) -> None:
    import yaml

    catalog_dir.mkdir(parents=True, exist_ok=True)
    (catalog_dir / "node.yaml").write_text(yaml.safe_dump(rules))


# --- AC-5, AC-12 — discriminated union round-trip + all pattern types --------


@pytest.mark.parametrize(
    ("pattern_type", "fixture", "expected_kind"),
    [
        ("dockerfile_pattern", "with_tini_dockerfile", "pass"),
        ("dockerfile_pattern", "no_tini_dockerfile", "fail"),
        ("dockerfile_pattern", "no_dockerfile_at_all", "not_applicable"),
        ("dockerfile_pattern_inverted", "no_npm_runtime", "pass"),
        ("dockerfile_pattern_inverted", "has_npm_runtime", "fail"),
        ("dockerfile_pattern_inverted", "no_dockerfile_at_all", "not_applicable"),
        ("file_pattern", "has_security_md", "pass"),
        ("file_pattern", "no_security_md", "fail"),
        ("file_pattern", "empty_repo", "not_applicable"),
        ("missing_file", "no_legacy_dockerignore", "pass"),
        ("missing_file", "has_legacy_dockerignore", "fail"),
        ("missing_file", "empty_repo", "not_applicable"),
    ],
)
def test_all_pattern_types_emit_typed_variants(
    pattern_type: str, fixture: str, expected_kind: str, tmp_path: Path, repo_fixture
) -> None:
    """AC-5, AC-12. Mutation caught: any pattern-type handler that
    silently collapses `NotApplicable` into `Pass` would fail the 4
    `not_applicable` rows. Any `Fail` that returns `Pass` would fail
    the corresponding `fail` row."""
    catalog_dir = tmp_path / "conventions"
    _write_catalog(catalog_dir, [{"name": "r1", "detect": {"type": pattern_type, "pattern": "tini"}}])
    repo = repo_fixture(name=fixture)
    ctx = ProbeContext.for_test(repo_snapshot=repo, conventions_search_paths=[catalog_dir])

    output = cp.ConventionsProbe()._run(ctx)
    slice_ = cp.ConventionsSlice.model_validate(output.schema_slice)
    assert len(slice_.results) == 1
    result = slice_.results[0]
    assert result.kind == expected_kind
    # Exhaustive match — assert_never proves the union is closed.
    match result:
        case Pass():
            assert expected_kind == "pass"
        case Fail():
            assert expected_kind == "fail"
        case NotApplicable():
            assert expected_kind == "not_applicable"
        case _:
            assert_never(result)


# --- AC-6 — NotApplicable is not Pass -----------------------------------------


def test_dockerfile_absent_yields_not_applicable_not_pass(tmp_path: Path, repo_fixture) -> None:
    """AC-6. Mutation caught: ``if not dockerfile_path.exists(): return Pass(...)``
    would silently certify services as conforming to dockerfile rules
    they were never checked against."""
    catalog_dir = tmp_path / "conventions"
    _write_catalog(
        catalog_dir,
        [{"name": "acme-tini-required", "detect": {"type": "dockerfile_pattern", "pattern": "tini"}}],
    )
    repo = repo_fixture(name="no_dockerfile_at_all")
    ctx = ProbeContext.for_test(repo_snapshot=repo, conventions_search_paths=[catalog_dir])
    output = cp.ConventionsProbe()._run(ctx)
    slice_ = cp.ConventionsSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.results[0], NotApplicable)
    assert slice_.results[0].reason == "dockerfile_absent"


# --- AC-7 — Fail carries file/line evidence -----------------------------------


def test_inverted_pattern_match_populates_line_and_snippet(tmp_path: Path, repo_fixture) -> None:
    """AC-7. Mutation caught: dropping `line`/`snippet` from `Fail`
    would render the evidence un-actionable by the Planner."""
    catalog_dir = tmp_path / "conventions"
    _write_catalog(
        catalog_dir,
        [
            {
                "name": "acme-no-npm-runtime",
                "detect": {
                    "type": "dockerfile_pattern_inverted",
                    "pattern": r"npm (start|run)",
                },
            }
        ],
    )
    repo = repo_fixture(name="has_npm_runtime")  # Dockerfile: CMD ["npm", "start"] on line 12
    ctx = ProbeContext.for_test(repo_snapshot=repo, conventions_search_paths=[catalog_dir])
    output = cp.ConventionsProbe()._run(ctx)
    slice_ = cp.ConventionsSlice.model_validate(output.schema_slice)
    f = slice_.results[0]
    assert isinstance(f, Fail)
    assert f.file.name == "Dockerfile"
    assert f.line == 12
    assert "npm" in f.snippet


# --- AC-8 — Pass is the empty-information variant ----------------------------


def test_pass_rejects_evidence_kwargs() -> None:
    """AC-8. Mutation caught: any future "let's add a `reason` to Pass
    for symmetry" — Pass is the empty-information variant; `extra="forbid"`
    on the Pydantic model is the type-level enforcement."""
    with pytest.raises(Exception):  # ValidationError
        Pass(rule_id="r1", file="Dockerfile")  # type: ignore[call-arg]


# --- AC-9 — catalog absent: low confidence, no raise --------------------------


def test_missing_catalog_dir_yields_low_confidence_no_raise(tmp_path: Path, repo_fixture) -> None:
    """AC-9. Mutation caught: re-raising would break Phase 0 isolation."""
    repo = repo_fixture(name="with_tini_dockerfile")
    nonexistent = tmp_path / "does_not_exist"
    ctx = ProbeContext.for_test(repo_snapshot=repo, conventions_search_paths=[nonexistent])
    output = cp.ConventionsProbe()._run(ctx)
    assert output.confidence == "low"
    assert output.schema_slice["results"] == []
    assert any("catalog_search_path_missing" in e for e in output.errors)


# --- AC-10 — sub-schema validates with additionalProperties: false ------------


def test_slice_matches_subschema_with_strict_additional_properties() -> None:
    """AC-10. Mutation caught: a future `Pass` adding a `note: str`
    field would fail the round-trip — `additionalProperties: false`
    holds at every nesting level."""
    import json
    from importlib.resources import files

    import jsonschema

    schema = json.loads(
        (files("codegenie.schema.probes.layer_d") / "conventions.schema.json").read_text()
    )
    slice_dict = {
        "results": [{"kind": "pass", "rule_id": "r1"}],
        "catalog_version": None,
        "rules_checked": 1,
    }
    jsonschema.validate(slice_dict, schema)
    # Negative — extra field on Pass must be rejected.
    bad = {
        "results": [{"kind": "pass", "rule_id": "r1", "note": "extra"}],
        "catalog_version": None,
        "rules_checked": 1,
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


# --- AC-11, AC-13 — registry annotation + total match -------------------------


def test_registry_heaviness_is_light() -> None:
    """AC-11. Mutation caught: bumping to `heaviness="medium"` would
    cause the coordinator to over-budget the probe."""
    assert _PROBE_REGISTRY["conventions"].heaviness == "light"


# --- AC-14 — no shared marker-probe base class --------------------------------


def test_no_shared_layer_d_base_class() -> None:
    """AC-14. Mutation caught: a future refactor extracting a
    `MarkerProbe` base class shared with `S6-03`'s probes — Rule of
    Three has not been triggered (4 marker probes in S6-03 + this one
    is 5; but they don't actually share runtime behavior, only
    "marker-driven" as a category). Premature abstraction would
    couple Layer D probes by inheritance."""
    import inspect

    src = inspect.getsource(cp)
    for forbidden in ("from codegenie.probes.layer_d.adrs", "from codegenie.probes.layer_d.policy"):
        assert forbidden not in src


# --- AC-15 — determinism ------------------------------------------------------


def test_two_consecutive_runs_byte_identical(tmp_path: Path, repo_fixture) -> None:
    """AC-15. Mutation caught: any non-deterministic ordering (set
    iteration, dict iteration without sort) would diverge on the
    second run."""
    catalog_dir = tmp_path / "conventions"
    _write_catalog(
        catalog_dir,
        [
            {"name": "a", "detect": {"type": "missing_file", "pattern": ".dockerignore.old"}},
            {"name": "b", "detect": {"type": "file_pattern", "pattern": "SECURITY.md"}},
        ],
    )
    repo = repo_fixture(name="has_security_md")
    ctx = ProbeContext.for_test(repo_snapshot=repo, conventions_search_paths=[catalog_dir])
    out1 = cp.ConventionsProbe()._run(ctx).schema_slice
    out2 = cp.ConventionsProbe()._run(ctx).schema_slice
    import json
    assert json.dumps(out1, sort_keys=True) == json.dumps(out2, sort_keys=True)
```

### Green — make it pass

```python
# src/codegenie/probes/layer_d/conventions.py
"""ConventionsProbe — Layer D, light heaviness.

Applies `ConventionsCatalogLoader.load_all()` output to the repo
snapshot and emits a typed `ConventionsSlice`. Each rule's outcome is
one of `Pass | Fail | NotApplicable` — the closed sum type the design
ratifies in arch §"Component design" #10.

Sources:
- ../phase-arch-design.md §"Component design" #10 — loader + apply.
- ../../localv2.md §5.4 D5 — example catalog.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from codegenie.conventions.catalog import ConventionsCatalogLoader
from codegenie.conventions.model import ConventionResult
from codegenie.ids import ProbeId
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, register_probe

__all__ = ["ConventionsProbe", "ConventionsSlice"]


class ConventionsSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    results: tuple[ConventionResult, ...]
    catalog_version: str | None
    rules_checked: int


@register_probe(heaviness="light")
class ConventionsProbe(Probe):
    probe_id = ProbeId("conventions")
    applies_to_tasks: tuple[str, ...] = ("*",)
    applies_to_languages: tuple[str, ...] = ("*",)
    timeout_seconds = 15

    def _run(self, ctx: ProbeContext) -> ProbeOutput:
        paths = ctx.conventions_search_paths or [ctx.user_home / ".codegenie" / "conventions"]
        result = ConventionsCatalogLoader(search_paths=paths).load_all()
        if result.is_err():
            return ProbeOutput(
                probe_id=self.probe_id,
                confidence="low",
                schema_slice=ConventionsSlice(
                    results=(), catalog_version=None, rules_checked=0
                ).model_dump(mode="json"),
                errors=[str(result.unwrap_err())],
            )
        catalog = result.unwrap()
        applied = sorted(catalog.apply(ctx.repo_snapshot), key=lambda r: r.rule_id)
        slice_ = ConventionsSlice(
            results=tuple(applied),
            catalog_version=catalog.version,
            rules_checked=len(applied),
        )
        return ProbeOutput(
            probe_id=self.probe_id,
            confidence="high",
            schema_slice=slice_.model_dump(mode="json"),
            errors=[],
        )
```

### Refactor

- The `match catalog.load_result:` pattern repeats across S6-01 and S6-02 (both consume a `Result[Loaded, LoaderError]`). The Rule-of-Three threshold is not met (two cases); leave the match inline. The third loader-consumer (S6-04 ExternalDocs) is allowed to be the trigger — but the helper, if extracted, lives in `codegenie.probes._loader_match` (a new module), not on a shared base class.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/layer_d/conventions.py` | New file — `ConventionsSlice`, `ConventionsProbe`. |
| `tests/unit/probes/layer_d/test_conventions.py` | New file — 8 tests (one parametrized over 12 cases) keyed to ACs. |
| `tests/fixtures/repo_fixture.py` | New conftest helper — produces minimal `RepoSnapshot`s with the named layouts (`with_tini_dockerfile`, `no_dockerfile_at_all`, etc.). Reused by S6-03/S6-05. |

## Out of scope

- **OPA/Rego pattern types.** Phase 16 (ADR-0021); the Phase 2 catalog supports only the four YAML-pattern types defined in S2-02.
- **Policy probe + exceptions probe.** S6-03 (separate marker probes; share no code with this one).
- **Catalog-version drift detection.** S6-08 registers `@register_index_freshness_check` for `conventions` (catalog version); this story emits `catalog_version`, the freshness check consumes it.
- **Per-rule "fix suggestions"** in `Fail.snippet`. The probe records the violating line + snippet; suggesting a fix is the Planner's job (per CLAUDE.md "Facts, not judgments").

## Notes for the implementer

1. **`ConventionResult` is the consumer-side discriminated union.** Phase 2 builds it; Phase 4+ (Planner) consumes it. The `Literal["pass"|"fail"|"not_applicable"]` discriminator on each variant is what makes downstream `match result:` blocks exhaustive under `mypy --warn-unreachable`. Do **not** introduce a `kind: str` field — that loses the static check.
2. **`NotApplicable` is not "skipped."** The probe wasn't skipped; the rule was checked, the precondition failed, the result is "this rule doesn't apply here." A future contributor may be tempted to merge `NotApplicable` into `confidence="low"` — resist. Confidence is per-*probe*; per-*rule* applicability is per-`ConventionResult`.
3. **`safe_yaml` is the only YAML loader.** `ConventionsCatalogLoader` (S2-02) already routes through `safe_yaml.load`; this probe never touches YAML directly. If a future change needs to read a catalog file path, it goes through the loader.
4. **`Pass` is the empty-information variant.** Resist the urge to add `Pass.note: str | None = None` — `Pass` is the "no information beyond `rule_id`" variant on purpose. If the convention check needs to explain *why* it passed, the convention is the wrong shape (express the explanation as a separate rule or as `NotApplicable.reason`).
5. **`Fail.line` is `int | None`** because some rules are whole-file ("missing pattern across whole Dockerfile"); others are line-specific ("forbidden pattern at this line"). The optional-line is honest; a sentinel `-1` would be primitive-obsession-with-extra-steps.
6. **No "convention applier" base class shared with S6-03's marker probes.** Layer D's five marker-driven probes (S6-03's adrs / repo_notes / repo_config / policy / exceptions) are simpler than this one — they're file-listing probes, not rule-evaluation probes. The shared structure is the `Probe` ABC; that's the level the discipline lives at.
7. **`ctx.conventions_search_paths`** is the Phase-0/1 `ProbeContext` field; if it's `None`, default to `ctx.user_home / ".codegenie" / "conventions"`. The default is documented in the module docstring so a future user can override without editing the probe.
8. **The 12-case parametrize is mutation-resistant by construction.** Each pattern type × outcome combo is its own row; a buggy `dockerfile_pattern_inverted` handler that swaps `Pass` / `Fail` polarity would fail exactly 2 rows out of 12 — not a 50/50 type confusion that a single test could miss.
