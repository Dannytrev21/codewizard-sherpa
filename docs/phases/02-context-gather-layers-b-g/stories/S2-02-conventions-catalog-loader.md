# Story S2-02 — `ConventionsCatalogLoader` with discriminated-union pattern types

**Step:** Step 2 — Plant kernel-side loaders (`SkillsLoader`, `ConventionsCatalogLoader`) and reference TCCM
**Status:** Ready
**Effort:** M
**Depends on:** S1-04 (`TCCM` model + loader establishes the `Result[T, E]` + `safe_yaml`-chokepoint + Pydantic discriminated-union pattern this story repeats)
**ADRs honored:** 02-ADR-0007 (kernel-side scaffolding only — no plugin loader), Phase 1 ADR-0006 (`safe_yaml` chokepoint preserved), Phase 1 ADR-0008 (in-process parse caps + `O_NOFOLLOW`), production ADR-0033 §3–4 (make-illegal-states-unrepresentable — every pattern type a discriminated-union variant; one `match` per type with `assert_never` on unreachable)

## Context

`ConventionsCatalogLoader` is the kernel-side loader for the org **conventions catalog** — YAML files at `~/.codegenie/conventions/*.yaml` whose entries declare structural rules to check against a repo (e.g., "Dockerfile must use a Chainguard distroless base", "`tsconfig.json` must exist and set `strict: true`"). Conventions are organizational uniqueness expressed as **data**, not as prompts — the Planner queries a typed result list rather than re-discovering the org's policy at decision time (commitment "Organizational uniqueness as data, not prompts" in repo `CLAUDE.md`). Phase 2 ships the loader skeleton + four pattern-type variants; OPA/Rego is a Phase 16 concern (ADR-0021), and policy authoring tooling is out of scope.

The two load-bearing commitments are:

- **Pattern types as a Pydantic discriminated union, exhaustively matched.** The four variants — `dockerfile_pattern`, `dockerfile_pattern_inverted`, `file_pattern`, `missing_file` — are a closed `match`/`case` switch with `assert_never` on the unreachable branch. `mypy --warn-unreachable` is a per-module ratchet (`codegenie.conventions/**`) that turns a fifth-pattern-without-a-match-arm into a build error. Adding a `dockerfile_pattern_glob` variant (Phase 3+) is a new file + ADR-amend; **never** a string-keyed dispatch dict.
- **`ConventionResult = Pass | Fail | NotApplicable` as a Pydantic discriminated union.** `NotApplicable` is the load-bearing third value — without it, "rule did not run because the file isn't present" gets fused with "rule passed", and the Confidence section (Phase 2 Step 8) would silently green-flag an absent input. ADR-0033 §3: make-illegal-states-unrepresentable; "rule didn't apply" is a legal state, distinct from pass and fail.

YAML access routes exclusively through Phase 1's `codegenie.parsers.safe_yaml.load` chokepoint (final-design §"Conflict-resolution" row 9 — same Rule 7 discipline that S2-01 enforces). The catalog file is a single YAML document; multi-doc `load_all` is **not** required (rules within one catalog file are a list under a top-level key, not separate documents).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #10` — interface, four pattern types, one `match` per type with `assert_never`, `Result.Err(ConventionsError(reason="unknown_pattern_type"))` failure mode.
  - `../phase-arch-design.md §"Data model"` — `ConventionResult = Pass | Fail | NotApplicable`; `extra="forbid"` Pydantic discipline; sub-schemas with `additionalProperties: false`.
  - `../phase-arch-design.md §"Design patterns applied"` row 5 (sum type / make-illegal-states-unrepresentable) and row 8 (one file per Layer G scanner — Rule of Three) — informs Catalog vs. ScannerRunner shape.
  - `../phase-arch-design.md §"Anti-patterns avoided"` — "Side effects in constructors" applies to `ConventionsCatalogLoader.__init__`.
- **Phase ADRs:**
  - `../ADRs/0007-no-plugin-loader-in-phase-2.md` — `ConventionsCatalogLoader` is kernel-side; no `plugin.yaml`.
- **Production ADRs:**
  - `../../production/adrs/0033-domain-modeling-discipline.md` §3–4 — discriminated unions for pattern types + result types; `mypy --warn-unreachable` enforces exhaustiveness.
- **Source design:**
  - `../final-design.md §"Components" #10` — `ConventionsCatalogLoader` interface; OPA/Rego deferred to Phase 16; Catalog.apply pure-function shape.
  - `../final-design.md §"Departures from all three inputs"` §8 — Rule 7 (`safe_yaml` reused, no parallel loader).
  - `../final-design.md §"Conflict-resolution table"` row 9 — `safe_yaml` chokepoint discipline.
- **Existing code:**
  - `src/codegenie/parsers/safe_yaml.py` (Phase 1 S1-03) — `load(path, *, max_bytes, max_depth=64) -> Mapping[str, JSONValue]`. Only YAML loader; do not add a parallel.
  - `src/codegenie/result.py` (lifted in S1-04) — `Result[T, E]` sum type.
  - `src/codegenie/tccm/loader.py` (S1-04) — established `Result`-returning, `safe_yaml`-routing loader shape; this story mirrors it.
  - `src/codegenie/coordinator/validator.py` (Phase 0) — `JSONValue` recursive alias (single source of truth).
- **External docs:**
  - `localv2.md` §5.4 (Layer D probes) — `ConventionsProbe` (S6-02) is the Phase 2 consumer; it applies the catalog to the repo snapshot and emits per-convention `Pass | Fail | NotApplicable` slices.
  - `localv2.md` §5.5 (Layer E probes) — `Ownership` + `ServiceTopologyStub` + `SloStub` (S6-05) also depend on this loader for marker-driven evidence.

## Goal

Ship `src/codegenie/conventions/` (three files: `__init__.py`, `model.py`, `catalog.py`) with:

```python
# model.py
class ConventionRuleDockerfilePattern(BaseModel):           # frozen=True, extra="forbid"
    kind: Literal["dockerfile_pattern"] = "dockerfile_pattern"
    id: ConventionId
    description: str
    pattern: str                                            # compiled regex source
class ConventionRuleDockerfilePatternInverted(BaseModel):
    kind: Literal["dockerfile_pattern_inverted"] = "dockerfile_pattern_inverted"
    id: ConventionId
    description: str
    pattern: str                                            # must NOT match
class ConventionRuleFilePattern(BaseModel):
    kind: Literal["file_pattern"] = "file_pattern"
    id: ConventionId
    description: str
    file_glob: str
    pattern: str
class ConventionRuleMissingFile(BaseModel):
    kind: Literal["missing_file"] = "missing_file"
    id: ConventionId
    description: str
    file_glob: str                                          # presence required

ConventionRule = Annotated[
    Union[ConventionRuleDockerfilePattern, ConventionRuleDockerfilePatternInverted,
          ConventionRuleFilePattern, ConventionRuleMissingFile],
    Field(discriminator="kind")
]

class Pass(BaseModel):                                       # frozen=True, extra="forbid"
    kind: Literal["pass"] = "pass"; rule_id: ConventionId
class Fail(BaseModel):
    kind: Literal["fail"] = "fail"; rule_id: ConventionId; evidence: str
class NotApplicable(BaseModel):
    kind: Literal["not_applicable"] = "not_applicable"; rule_id: ConventionId; reason: str
ConventionResult = Annotated[Union[Pass, Fail, NotApplicable], Field(discriminator="kind")]

# catalog.py
class Catalog(BaseModel):
    rules: list[ConventionRule]
    def apply(self, repo: RepoSnapshot) -> list[ConventionResult]: ...

class ConventionsCatalogLoader:
    def __init__(self, search_paths: list[Path]) -> None: ...
    def load_all(self) -> Result[Catalog, ConventionsError]: ...
```

With invariants:

1. **Constructor is pure data.** `__init__` performs no I/O; first I/O is `load_all()`.
2. **`load_all()` uses `safe_yaml.load` exclusively.** No `yaml.*` imports anywhere in `src/codegenie/conventions/`.
3. **Unknown `kind` → `Result.Err(ConventionsError(reason="unknown_pattern_type", path=path, offending_kind=...))`.** Caught by Pydantic's `Field(discriminator="kind")` `ValidationError`; loader wraps as the typed `Result.Err`.
4. **`Catalog.apply(repo)` is a single `match rule` switch with `assert_never` on the unreachable branch.** Each variant has a dedicated `_apply_<kind>(rule, repo)` helper returning a `ConventionResult`. The discriminated-union `match` is the only branch on rule type; no `isinstance` chains; no string lookup tables.
5. **`NotApplicable` is the load-bearing third value.** A `dockerfile_pattern` rule against a repo with no `Dockerfile` → `NotApplicable(reason="no_dockerfile_present")`, **not** `Pass`. A `file_pattern` rule whose `file_glob` matches zero files → `NotApplicable(reason="file_glob_no_matches")`.
6. **`ConventionsError` is a Pydantic discriminated union over the documented failure modes** (`unknown_pattern_type`, `schema`, `symlink_refused`, `catalog_file_unreadable`) — same shape as `SkillsLoadError` (S2-01), reused convention.

## Acceptance criteria

- [ ] **AC-1 — module surface.** `src/codegenie/conventions/__init__.py` exports `Catalog`, `ConventionsCatalogLoader`, `ConventionRule`, `ConventionResult`, `Pass`, `Fail`, `NotApplicable`, `ConventionsError`. `Pass`/`Fail`/`NotApplicable` and the four `ConventionRule*` variants are all `frozen=True, extra="forbid"`. The two discriminated unions use `Field(discriminator="kind")`.
- [ ] **AC-2 — pure-data constructor.** `ConventionsCatalogLoader(search_paths=[non_existent_path])` does not raise and performs no I/O. Asserted via `monkeypatch.setattr(os, "listdir", record_calls)` + the recorded list is empty after `__init__` returns.
- [ ] **AC-3 — happy path per pattern type.** One test per `kind` (`dockerfile_pattern`, `dockerfile_pattern_inverted`, `file_pattern`, `missing_file`) loads a one-rule catalog and asserts the loaded `Catalog.rules[0].kind` matches the literal. Parametrized.
- [ ] **AC-4 — `dockerfile_pattern` `Pass` / `Fail` / `NotApplicable`.** Three sub-tests:
  - Repo with `Dockerfile` containing matching pattern → `Pass`.
  - Repo with `Dockerfile` not matching → `Fail` with `evidence` containing the offending line or "pattern not found".
  - Repo with no `Dockerfile` → `NotApplicable(reason="no_dockerfile_present")`.
- [ ] **AC-5 — `dockerfile_pattern_inverted` flips the meaning correctly.** Repo with `Dockerfile` containing the forbidden pattern → `Fail`; absence of the pattern → `Pass`; no `Dockerfile` → `NotApplicable`. Pins the off-by-negation mutation (`Pass` vs `Fail` flip).
- [ ] **AC-6 — `file_pattern` over a `file_glob` of zero matches → `NotApplicable`.** Distinct from `Pass`. Pins the bug where an empty match-set is conflated with a passing run.
- [ ] **AC-7 — `missing_file` semantics.** Rule with `file_glob: "Dockerfile"` against a repo **without** Dockerfile → `Pass` (the file is correctly missing per the rule's intent). Against a repo with Dockerfile → `Fail`. The kind is named for the **assertion**, not the observed outcome — read the kind literal carefully when implementing.
- [ ] **AC-8 — unknown pattern type → `Result.Err`.** A catalog YAML with `kind: dockerfile_pattern_glob` (not in the enumerated four) raises Pydantic `ValidationError` from the discriminator; the loader wraps as `Result.Err(ConventionsError(reason="unknown_pattern_type", path=catalog_path, offending_kind="dockerfile_pattern_glob"))`. Asserted by `test_unknown_kind_returns_typed_result_err`.
- [ ] **AC-9 — exhaustive `match` with `assert_never`.** `tests/unit/conventions/test_catalog.py::test_apply_match_is_exhaustive_compile_time` is a `mypy --warn-unreachable` smoke test: a fixture script imports `catalog._apply_rule` and pattern-matches; `mypy` over that script must be clean. A complementary runtime test injects a hand-constructed `object()` (bypassing Pydantic) into the `match` and asserts `assert_never` raises `AssertionError`/`TypeError`. Pins ADR-0033 §4.
- [ ] **AC-10 — `safe_yaml.load` chokepoint (Rule 7).** `ripgrep "yaml\\." src/codegenie/conventions/` returns zero hits. Asserted by `test_catalog_loader_routes_yaml_through_safe_yaml_chokepoint` (uses `monkeypatch.setattr(safe_yaml, "load", spy)` + asserts spy was called for every catalog file loaded).
- [ ] **AC-11 — sub-schemas with `additionalProperties: false` (`extra="forbid"`).** A catalog YAML with an unknown field (`unexpected_key: value`) on a rule entry produces `Result.Err(ConventionsError(reason="schema", details=[...]))`. Pins the "silently ignore unknown keys" anti-pattern.
- [ ] **AC-12 — `Catalog.apply(repo)` is pure (idempotent + no I/O on repeated calls).** Given the same `RepoSnapshot`, two consecutive `apply()` calls return equal `list[ConventionResult]` and the second call performs zero `os.open` / `os.read` calls (asserted via monkeypatch counters). The first call may read repo files (e.g., the `Dockerfile`); the snapshot is the I/O boundary.
- [ ] **AC-13 — `ConventionsError` discriminated union, four reasons enumerated.** Test parametrizes over `{"unknown_pattern_type", "schema", "symlink_refused", "catalog_file_unreadable"}` and asserts each constructs successfully via the discriminator; a fifth reason raises `ValidationError`.
- [ ] **AC-14 — `forbidden-patterns` continues to ban `model_construct`.** Pre-commit hook scans `src/codegenie/conventions/` and finds zero `model_construct` calls.
- [ ] **AC-15 — toolchain.** `ruff check`, `ruff format --check`, `mypy --strict`, `mypy --warn-unreachable` (per-module on `codegenie.conventions/**`) clean. `pytest tests/unit/conventions/` passes.
- [ ] **AC-16 — TDD discipline.** Red tests committed failing; green commit makes them pass; refactor commit is no-op behavior.

## Implementation outline

1. **`src/codegenie/conventions/model.py`** — define `ConventionId` newtype (lift from Step 1's ADR-0033 newtype roster if `codegenie.adapters.ids` exposes it; otherwise add here). Define the four `ConventionRule*` Pydantic models and the `ConventionRule` discriminated union. Define `Pass`/`Fail`/`NotApplicable` and the `ConventionResult` discriminated union. Define the `ConventionsError` discriminated union (mirrors S2-01's `SkillsLoadError` shape) with four reason variants.
2. **`src/codegenie/conventions/catalog.py`::`Catalog`** — Pydantic model with `rules: list[ConventionRule]`. `apply(self, repo: RepoSnapshot) -> list[ConventionResult]` is the consumer entry point:
   ```python
   def apply(self, repo: RepoSnapshot) -> list[ConventionResult]:
       return [self._apply_one(rule, repo) for rule in self.rules]

   def _apply_one(self, rule: ConventionRule, repo: RepoSnapshot) -> ConventionResult:
       match rule:
           case ConventionRuleDockerfilePattern():        return _apply_dockerfile_pattern(rule, repo)
           case ConventionRuleDockerfilePatternInverted(): return _apply_dockerfile_pattern_inverted(rule, repo)
           case ConventionRuleFilePattern():              return _apply_file_pattern(rule, repo)
           case ConventionRuleMissingFile():              return _apply_missing_file(rule, repo)
           case _ as unreachable:
               assert_never(unreachable)
   ```
3. **`_apply_dockerfile_pattern(rule, repo)`** — locate `Dockerfile` in repo root (or the documented set of locations; Phase 2 ships root-only). Absent → `NotApplicable(rule_id=rule.id, reason="no_dockerfile_present")`. Read via the repo snapshot (no direct `os.open` — the snapshot abstracts the boundary). `re.search(rule.pattern, contents)` — match → `Pass`; no match → `Fail(evidence="pattern not found in Dockerfile")`. The regex is compiled once via `re.compile`; compilation failure is a schema-time concern caught at load (a rule with an uncompilable `pattern` → `Result.Err(ConventionsError(reason="schema", ...))` via a Pydantic `model_validator`).
4. **`_apply_dockerfile_pattern_inverted(rule, repo)`** — same locate; match → `Fail`; no match → `Pass`; absent → `NotApplicable`. The negation lives in this helper, **not** by inverting the `Pass` of `_apply_dockerfile_pattern` (don't share machinery — Rule of Three; each helper reads independently).
5. **`_apply_file_pattern(rule, repo)`** — glob `rule.file_glob` over the repo. Zero matches → `NotApplicable(reason="file_glob_no_matches")`. For each matching file, run the regex; if all match → `Pass`; if any fails → `Fail(evidence=f"<file>: pattern not found")` for the first offending file (Phase 2 emits one result per rule, not per file; the Confidence section reads this).
6. **`_apply_missing_file(rule, repo)`** — glob `rule.file_glob`. Zero matches → `Pass` (the assertion is "this file is absent"). Any match → `Fail(evidence=f"unexpected file present: <first match>")`. Note: this kind's semantics are inverted relative to a naive read of the name — the rule **succeeds** when the file is **missing** (see AC-7).
7. **`ConventionsCatalogLoader.__init__(self, search_paths: list[Path]) -> None`** — store `self._search_paths = list(search_paths)`; no I/O. The default factory in `__init__.py` pins `[Path("~/.codegenie/conventions/").expanduser(), Path(".codegenie/conventions/")]` for production use; tests pass explicit paths.
8. **`ConventionsCatalogLoader.load_all(self) -> Result[Catalog, ConventionsError]`** — for each `search_path`, glob `*.yaml` and `*.yml`; for each catalog file:
   ```
   try:
       data = safe_yaml.load(catalog_path, max_bytes=1 << 20)   # Phase 1 chokepoint
   except SymlinkRefusedError:
       return Result.Err(SymlinkRefused(path=catalog_path))
   except MalformedYAMLError as exc:
       return Result.Err(SchemaError(path=catalog_path, details=[{"msg": str(exc)}]))
   try:
       catalog = Catalog.model_validate(data)
   except ValidationError as exc:
       # Inspect for discriminator failure → unknown_pattern_type; otherwise schema.
       if _is_unknown_kind_error(exc):
           return Result.Err(UnknownPatternType(path=catalog_path,
                                                offending_kind=_extract_kind(exc)))
       return Result.Err(SchemaError(path=catalog_path, details=exc.errors()))
   ```
   Multiple catalog files are merged into one `Catalog.rules` list in iteration order. Phase 2 ships **without** rule-ID deduplication across catalog files (single-file fixtures are the norm); a follow-up ADR can decide whether duplicate IDs across files are an error or a last-wins merge.
9. **`assert_never` import.** `from typing import assert_never` (Python 3.11+). The `mypy --warn-unreachable` per-module override in `pyproject.toml` (added in Step 1) ensures a missing variant in the `match` is a build error.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/unit/conventions/test_catalog.py` (16 named tests covering AC-1..AC-15).

```python
# tests/unit/conventions/test_catalog.py — red tests pinning the load-bearing ACs
import os
import textwrap
from pathlib import Path

import pytest

from codegenie.conventions import (
    Catalog, ConventionsCatalogLoader, Fail, NotApplicable, Pass,
)
from codegenie.conventions.model import (
    ConventionRuleDockerfilePattern, ConventionRuleMissingFile,
)
from codegenie.conventions.loader import UnknownPatternType, SchemaError


def _write_catalog(p: Path, body: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def _repo_snapshot_with(tmp_path: Path, files: dict[str, str]) -> "RepoSnapshot":
    """Build a Phase-0 RepoSnapshot rooted at tmp_path with the given files."""
    from codegenie.coordinator.snapshot import RepoSnapshot
    for relpath, contents in files.items():
        f = tmp_path / relpath
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(contents)
    return RepoSnapshot.build(tmp_path)


def test_constructor_is_pure_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-2: __init__ must perform no I/O."""
    calls: list = []
    monkeypatch.setattr(os, "listdir", lambda p: calls.append(p) or [])
    ConventionsCatalogLoader(search_paths=[tmp_path / "does-not-exist"])
    assert calls == []


def test_dockerfile_pattern_pass_fail_not_applicable(tmp_path: Path) -> None:
    """AC-4: three outcomes pinned for dockerfile_pattern."""
    catalog_path = _write_catalog(tmp_path / "conventions" / "c.yaml", textwrap.dedent("""\
        rules:
          - kind: dockerfile_pattern
            id: distroless-base
            description: must use a chainguard distroless base
            pattern: '^FROM cgr\\.dev/chainguard/'
        """))
    loader = ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
    catalog = loader.load_all().unwrap()

    # Pass
    repo_pass = _repo_snapshot_with(tmp_path / "pass-repo", {"Dockerfile": "FROM cgr.dev/chainguard/node:latest\n"})
    assert isinstance(catalog.apply(repo_pass)[0], Pass)

    # Fail
    repo_fail = _repo_snapshot_with(tmp_path / "fail-repo", {"Dockerfile": "FROM node:20-alpine\n"})
    result_fail = catalog.apply(repo_fail)[0]
    assert isinstance(result_fail, Fail)
    assert "pattern" in result_fail.evidence.lower() or "Dockerfile" in result_fail.evidence

    # NotApplicable — no Dockerfile
    repo_na = _repo_snapshot_with(tmp_path / "na-repo", {"package.json": "{}"})
    result_na = catalog.apply(repo_na)[0]
    assert isinstance(result_na, NotApplicable)
    assert result_na.reason == "no_dockerfile_present"


def test_missing_file_kind_succeeds_when_file_absent(tmp_path: Path) -> None:
    """AC-7: the kind is named for the assertion; rule passes when file is absent."""
    _write_catalog(tmp_path / "conventions" / "c.yaml", textwrap.dedent("""\
        rules:
          - kind: missing_file
            id: no-rogue-dockerfile
            description: this repo must not ship its own Dockerfile
            file_glob: Dockerfile
        """))
    loader = ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
    catalog = loader.load_all().unwrap()

    repo_clean = _repo_snapshot_with(tmp_path / "clean", {"package.json": "{}"})
    assert isinstance(catalog.apply(repo_clean)[0], Pass)

    repo_dirty = _repo_snapshot_with(tmp_path / "dirty", {"Dockerfile": "FROM scratch\n"})
    assert isinstance(catalog.apply(repo_dirty)[0], Fail)


def test_file_pattern_zero_matches_is_not_applicable(tmp_path: Path) -> None:
    """AC-6: empty glob match-set MUST NOT be conflated with Pass."""
    _write_catalog(tmp_path / "conventions" / "c.yaml", textwrap.dedent("""\
        rules:
          - kind: file_pattern
            id: tsconfig-strict
            description: all tsconfig files must enable strict mode
            file_glob: "**/tsconfig.json"
            pattern: '"strict"\\s*:\\s*true'
        """))
    loader = ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"])
    catalog = loader.load_all().unwrap()
    repo_no_ts = _repo_snapshot_with(tmp_path / "no-ts", {"package.json": "{}"})
    result = catalog.apply(repo_no_ts)[0]
    assert isinstance(result, NotApplicable)
    assert result.reason == "file_glob_no_matches"


def test_unknown_pattern_kind_returns_typed_result_err(tmp_path: Path) -> None:
    """AC-8: an unknown discriminator kind yields Result.Err(ConventionsError(...))."""
    catalog_path = _write_catalog(tmp_path / "conventions" / "c.yaml", textwrap.dedent("""\
        rules:
          - kind: dockerfile_pattern_glob       # not in the enumerated four
            id: x
            description: y
            pattern: ".*"
        """))
    result = ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"]).load_all()
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, UnknownPatternType)
    assert err.offending_kind == "dockerfile_pattern_glob"
    assert err.path == catalog_path


def test_schema_violation_extra_field_returns_typed_result_err(tmp_path: Path) -> None:
    """AC-11: extra='forbid' is the load-bearing discipline — unknown keys MUST raise."""
    _write_catalog(tmp_path / "conventions" / "c.yaml", textwrap.dedent("""\
        rules:
          - kind: dockerfile_pattern
            id: x
            description: y
            pattern: ".*"
            unexpected_key: value
        """))
    result = ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"]).load_all()
    assert result.is_err()
    assert isinstance(result.unwrap_err(), SchemaError)


def test_safe_yaml_chokepoint_is_the_only_yaml_call_site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-10: every YAML access routes through codegenie.parsers.safe_yaml.load."""
    from codegenie.parsers import safe_yaml as sy
    real_load = sy.load
    calls: list[Path] = []
    def spy(path, *, max_bytes, max_depth=64):
        calls.append(path)
        return real_load(path, max_bytes=max_bytes, max_depth=max_depth)
    monkeypatch.setattr(sy, "load", spy)
    _write_catalog(tmp_path / "conventions" / "c.yaml", "rules: []\n")
    ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"]).load_all().unwrap()
    assert calls, "safe_yaml.load was not called — chokepoint bypassed"


def test_apply_match_is_exhaustive_assert_never_fires_on_smuggled_variant() -> None:
    """AC-9: the match arm must have assert_never on the unreachable branch."""
    from codegenie.conventions.catalog import _apply_one
    class _Imposter:
        kind = "not_a_real_kind"
    with pytest.raises((AssertionError, TypeError, ValueError)):
        _apply_one(_Imposter(), repo=None)  # type: ignore[arg-type]


def test_apply_is_idempotent_without_repeated_io(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-12: second apply() call reads no files from disk (snapshot is the I/O boundary)."""
    _write_catalog(tmp_path / "conventions" / "c.yaml", textwrap.dedent("""\
        rules:
          - kind: dockerfile_pattern
            id: x
            description: y
            pattern: "FROM"
        """))
    catalog = ConventionsCatalogLoader(search_paths=[tmp_path / "conventions"]).load_all().unwrap()
    repo = _repo_snapshot_with(tmp_path / "r", {"Dockerfile": "FROM node\n"})

    first = catalog.apply(repo)
    reads: list = []
    monkeypatch.setattr(os, "open", lambda *a, **kw: reads.append(a) or (_ for _ in ()).throw(OSError(2, "stub")))
    second = catalog.apply(repo)
    assert first == second
    assert reads == [], f"second apply() performed disk I/O: {reads}"
```

Run; confirm every test fails because `src/codegenie/conventions/` does not exist. Commit as red.

### Green — make it pass

Land in this order:

1. `src/codegenie/conventions/model.py` — newtypes, four `ConventionRule*` variants, `ConventionRule` discriminator union, `Pass`/`Fail`/`NotApplicable`, `ConventionResult` discriminator union, regex-compile model validator on the `pattern`-carrying variants.
2. `src/codegenie/conventions/loader.py` — `ConventionsError` discriminated union (`UnknownPatternType`, `SchemaError`, `SymlinkRefused`, `CatalogFileUnreadable`), `ConventionsCatalogLoader` class, the `_is_unknown_kind_error` / `_extract_kind` introspection helpers over Pydantic `ValidationError.errors()`.
3. `src/codegenie/conventions/catalog.py` — `Catalog` Pydantic model, `_apply_dockerfile_pattern` + `_apply_dockerfile_pattern_inverted` + `_apply_file_pattern` + `_apply_missing_file` helpers, `_apply_one` `match` with `assert_never`.
4. `src/codegenie/conventions/__init__.py` — re-exports per AC-1.
5. `tests/unit/conventions/__init__.py` and `test_catalog.py` from above; add a per-module `mypy --warn-unreachable` line in `pyproject.toml` if not already added by Step 1.

### Refactor — clean up

- Module docstring on `catalog.py` cites `phase-arch-design.md §"Component design" #10`, ADR-0033 §3–4, and the four pattern types.
- The four `_apply_*` helpers live as module-level pure functions (not methods on `Catalog`) so they're independently testable and so the `_apply_one` `match` is a thin dispatcher — easier to read, easier to extend.
- `RepoSnapshot.read_text(relpath)` is the abstraction; `_apply_*` helpers never touch `os.open` directly. If `RepoSnapshot` (Phase 0) doesn't expose the needed shape, file a follow-up — do not bypass.
- Do **not** introduce a shared `ScannerRunner` / pattern-engine class. Four small helpers, four distinct shapes, ~30 LOC each. Phase-2 final design row 7 forbids the abstraction.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/conventions/__init__.py` | New — public surface |
| `src/codegenie/conventions/model.py` | New — four `ConventionRule*` variants + `ConventionRule` union + `Pass`/`Fail`/`NotApplicable` + `ConventionResult` union |
| `src/codegenie/conventions/loader.py` | New — `ConventionsCatalogLoader`, `ConventionsError` union, Pydantic-error introspection |
| `src/codegenie/conventions/catalog.py` | New — `Catalog`, four `_apply_*` helpers, `_apply_one` `match` with `assert_never` |
| `tests/unit/conventions/__init__.py` | New — package marker |
| `tests/unit/conventions/test_catalog.py` | New — 16 named tests |
| `pyproject.toml` | If not already in Step 1: `mypy --warn-unreachable` per-module override on `codegenie.conventions.*` |

## Out of scope

- **Layer D `ConventionsProbe`** — S6-02; consumes this loader, ships next.
- **Layer E probes** (`Ownership`, `ServiceTopologyStub`, `SloStub`) — S6-05; also consume this loader.
- **OPA/Rego policy backends** — Phase 16 (ADR-0021).
- **Per-file `Fail` results from a `file_pattern` match-set** — Phase 2 emits one `ConventionResult` per rule; a future ADR can decide whether to fan out per-file results. The first offending file is named in `evidence`.
- **Cross-catalog rule-ID deduplication** — left as a follow-up; single-file fixtures are the norm.
- **Catalog-version-as-`IndexFreshness` signal** — registered by Step 6 (`@register_index_freshness_check` for `conventions` with the catalog version). This story plants the loader; the freshness registration lands at probe time.
- **Hostile YAML adversarial tests** — Phase 1 S5-01 already pins `safe_yaml`'s `!!python/object` + alias-amplification defenses.
- **`SkillsLoader`** — S2-01 (parallel-after-S1-04 with this story).
- **Reference TCCM Protocol-mock dispatcher** — S2-03 (depends on S2-01; uses S1-04's `TCCMLoader`).

## Notes for the implementer

- **`match` exhaustiveness is type-enforced.** `mypy --warn-unreachable` per-module on `codegenie.conventions.*` makes a missing variant in `_apply_one` a build failure. Do NOT fall back to `else: raise ValueError(...)` — the `case _ as unreachable: assert_never(unreachable)` shape is the load-bearing one. The runtime smoke test (AC-9) catches anyone who replaces it.
- **`missing_file` semantics are subtle.** The rule's name describes what it **asserts**, not what it observes. A `missing_file` rule with `file_glob: Dockerfile` says "the Dockerfile MUST be missing"; the rule **passes** when no Dockerfile exists. Reviewers will misread this on first encounter — leave a one-line code comment in `_apply_missing_file` explaining the inversion.
- **`NotApplicable` is the load-bearing third value.** A future contributor will eventually be tempted to return `Pass` when a rule's file-glob matches zero files ("nothing to check, so it passes"). That fuses two distinct states and makes the Confidence section green-flag absent inputs. AC-6 + AC-4's third sub-test pin this; don't relax them.
- **Regex compilation at load, not at apply.** Each `pattern`-carrying variant has a Pydantic `model_validator(mode="after")` that calls `re.compile(self.pattern)` and stashes the compiled object (use `model_config = ConfigDict(arbitrary_types_allowed=True)` if needed, or compile lazily at first `apply` call). Per-apply compile is a perf bug if `apply` is called per repo in a batch.
- **No `yaml.*` imports.** AC-10 + the Phase 1 chokepoint. If you need a YAML capability `safe_yaml` lacks, file an issue.
- **`ConventionsError` mirrors `SkillsLoadError` (S2-01).** Both are Pydantic discriminated unions over a `reason` literal with `path: Path` + optional details. The shape is intentional — Phase 3 plugins will import both and pattern-match uniformly. Don't drift the field names (`reason`, `path`, `details`) between the two.
- **Discriminator-error introspection.** Pydantic's `ValidationError.errors()` for a discriminated-union failure includes a `loc` tuple ending in `kind` and a `type` of `union_tag_invalid` or `literal_error`. `_is_unknown_kind_error` checks this shape; `_extract_kind` pulls the offending value from `errors()[i]["input"]`. Stash a snippet of `ValidationError.errors()` output as a code comment for the next implementer — Pydantic v2 has revised this shape twice; future-proof the introspection.
- **`Catalog.apply` is consumed by Layer D `ConventionsProbe` (S6-02) and Layer E `Ownership`/`Topology`/`SLO` stubs (S6-05).** Keep `apply` pure and snapshot-driven so the probes can call it inside a `@register_probe(heaviness="light")` slot without I/O surprises. If a future rule type needs network access, that's a new variant + a new probe layer; don't smuggle I/O into `_apply_*` helpers.
- **Do NOT lift a shared `ScannerRunner` / pattern-engine.** Final-design row 7 explicitly rejects this (Rule of Three + SRP); four ~30-LOC helpers are cheaper than the abstraction they'd share. If a fifth variant lands in Phase 3+, that's the trigger to re-evaluate — not before.
