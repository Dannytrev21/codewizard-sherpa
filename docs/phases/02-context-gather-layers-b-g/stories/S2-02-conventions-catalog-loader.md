# Story S2-02 — `ConventionsCatalogLoader` with discriminated-union pattern types

**Step:** Step 2 — Plant kernel-side loaders (`SkillsLoader`, `ConventionsCatalogLoader`) and reference TCCM
**Status:** Ready
**Effort:** M
**Depends on:** S1-04 (`TCCM` model + loader establishes the `Result[T, E]` + `safe_yaml`-chokepoint + Pydantic discriminated-union pattern this story repeats). Sibling-and-precedent: S2-01 (`SkillsLoader`) — same multi-file partial-success loader shape; this story reuses the `SkillsLoadError`-style `reason: Literal[…]` discriminator + `LoadOutcome` + `per_file_errors` convention.
**ADRs honored:** 02-ADR-0007 (kernel-side scaffolding only — no plugin loader), Phase 1 ADR-0006 (`safe_yaml` chokepoint preserved), Phase 1 ADR-0008 (in-process parse caps + `O_NOFOLLOW`), Phase 0 ADR-0007 (probe-contract surface frozen — `RepoSnapshot` extension policy, see Validation notes B1), production ADR-0033 §1, §3–4 (newtypes for every domain primitive — `ConventionId`, `RegexPatternSource`; make-illegal-states-unrepresentable — every pattern type a discriminated-union variant; one `match` per type with `assert_never` on unreachable)

## Validation notes (added 2026-05-15 by phase-story-validator)

This story was hardened against four critic lenses (coverage, test-quality, consistency, design-patterns). **Verdict: HARDENED.** The core shape (Pydantic discriminated union over four pattern variants + `ConventionResult = Pass | Fail | NotApplicable` + `Catalog.apply` as a `match` with `assert_never` + `safe_yaml.load` chokepoint reuse) is correct and traces cleanly to arch §"Component design" #10, arch §"Design patterns applied" rows 5/8, 02-ADR-0007 §Decision, and production ADR-0033. Block-tier and harden-tier closures applied in place:

- **B1 — `RepoSnapshot` API mismatch (block).** Original story prescribed `RepoSnapshot.build(tmp_path)` (a factory) and `repo.read_text(relpath)` (a method). Neither exists. `src/codegenie/probes/base.py` ships `RepoSnapshot` as a plain `@dataclass` with `root: Path`, `git_commit: str | None`, `detected_languages: dict[str, int]`, `config: dict[str, Any]` — no factory, no `read_text`. Phase 0 ADR-0007 freezes the probe-contract surface — adding either method to `RepoSnapshot` would require a Phase 2 ADR amendment with sentinel-test wiring (`tests/unit/test_probe_contract.py`). The hardened story takes the **smaller blast radius**: `_apply_*` helpers read repo files via `repo.root / relpath` (`pathlib.Path` operations only — no new method on `RepoSnapshot`), capped at 1 MiB per file via `codegenie.parsers._io.open_capped`-style discipline (a `read_capped_text(path: Path, *, max_bytes: int) -> str | None`-style helper local to `codegenie.conventions._io`, **not** a new public method on `RepoSnapshot`). Test fixtures construct `RepoSnapshot` directly via `RepoSnapshot(root=tmp_path / "repo", git_commit=None, detected_languages={}, config={})` (no factory). AC-12 is the contract pin; the Implementation outline §3–6 was rewritten to reflect this. (See also DP-Notes "Functional core, RepoSnapshot at the boundary".)
- **B2 — `ConventionId` newtype location (block).** Original story said "lift from Step 1's ADR-0033 newtype roster if `codegenie.adapters.ids` exposes it; otherwise add here." `codegenie.adapters.ids` does **not** exist; canonical home for domain identifiers is `codegenie/types/identifiers.py` (which already exports `SkillId`, `TaskClassId`, `ProbeId`). Story now commits to **extending** `codegenie.types.identifiers` with `ConventionId = NewType("ConventionId", str)` and the `__all__` line — Open/Closed at the file boundary, mirroring the lift S1-05 established for the existing newtypes. The `Language` newtype is **not** introduced by this story (no language-applicability field on `ConventionRule*`); `ConventionId` is the only new newtype. AC-1 and AC-25 (new) pin the import location.
- **B3 — `rule_id` field never asserted on `ConventionResult` (block).** Every AC checked `isinstance(result, Pass|Fail|NotApplicable)` but never `result.rule_id == rule.id`. A mutation that fuses `rule_id` to a constant (e.g., always `ConventionId("")`) or swaps it with a sibling rule's id would pass every existing test. AC-4 / AC-5 / AC-6 / AC-7 now assert `result.rule_id == ConventionId("<expected id>")` exactly.
- **B4 — `assert_never` exception type was too lax (block, TQ1).** AC-9's runtime smoke test allowed `pytest.raises((AssertionError, TypeError, ValueError))`. `typing.assert_never` raises `AssertionError` in Python 3.11+ (`assert_never` is `raise AssertionError(...)`). Allowing `TypeError` / `ValueError` lets a defensive implementation that writes `if not isinstance(rule, _KNOWN_TYPES): raise TypeError("unknown kind")` pass — which is exactly the anti-pattern ADR-0033 §4 forbids (the load-bearing signal is the *compile-time* exhaustiveness check, not a runtime `isinstance` whitelist). Tightened to `pytest.raises(AssertionError)` only. (The runtime test exists because compile-time `mypy --warn-unreachable` only fires on a *missing* arm, not on someone writing the `isinstance`-chain anti-pattern.)
- **B5 — `_apply_one` import path pinned (block).** The TDD plan imports `from codegenie.conventions.catalog import _apply_one`, but the Implementation outline shows `_apply_one` as a method on `Catalog`. The hardened story pins `_apply_one(rule: ConventionRule, repo: RepoSnapshot) -> ConventionResult` as a **module-level** pure function in `catalog.py`; `Catalog.apply` is a thin wrapper that iterates `self.rules` and calls the module-level function. This composes with the "four module-level `_apply_*` helpers" prescription in §"Refactor" and makes the `assert_never` smoke test (AC-9) callable without instantiating `Catalog`.
- **B6 — `ConventionsError` reasons under-enumerated vs `safe_yaml.load` raise set (block, CN3).** Story enumerated four reasons (`unknown_pattern_type`, `schema`, `symlink_refused`, `catalog_file_unreadable`) but `safe_yaml.load` raises `MalformedYAMLError` (any `yaml.YAMLError` subclass, including `ConstructorError` for `!!python/object`), `SizeCapExceeded`, `DepthCapExceeded`, and `SymlinkRefusedError`. The S2-01 hardening surfaced this exact gap; this story now adopts the same convention: `unsafe_yaml` is the umbrella for *all* `MalformedYAMLError` causes (parser, scanner, constructor — operationally-prudent name), `size_cap_exceeded` is its own reason (the operator distinguishes a 200 MB hostile catalog from a parser typo), and `depth_cap_exceeded` is its own reason. Final `ConventionsError` is a seven-reason discriminated union: `unknown_pattern_type | schema | symlink_refused | unsafe_yaml | size_cap_exceeded | depth_cap_exceeded | catalog_file_unreadable`. AC-13 (parameterized over the seven reasons) replaces the previous four-reason form; AC-8 (umbrella honesty), AC-8b (size-cap), AC-8c (depth-cap) are new.
- **H1 — Multi-rule single-file catalog absent.** Every red test loaded a one-rule catalog. AC-3a (new) loads a two-rule catalog with **distinct** `kind`s in the same YAML file; asserts both rules round-trip and `Catalog.apply(repo)` returns `len(...) == 2` in the same order.
- **H2 — Multi-file catalog merge order never pinned.** Story says "merged into one `Catalog.rules` list in iteration order" but no AC verifies. AC-3b (new) writes two YAML files (`a.yaml` first-rule, `b.yaml` second-rule) in the same `search_paths[0]` directory; asserts ordering by sorted relative path (lexicographic; deterministic across xfs/ext4/APFS — same convention as S2-01 AC-19).
- **H3 — Regex compilation at load not pinned by an AC.** Notes-for-implementer say "compilation failure is a schema-time concern caught at load (a rule with an uncompilable `pattern` → `Result.Err(ConventionsError(reason="schema", ...))` via a Pydantic `model_validator`)." AC-11a (new) pins this: a `pattern: "[unterminated"` rule → `Result.Err(SchemaError(...))` with `details` non-empty and at least one row whose `loc` references the `pattern` field. Tied to DP1 (regex as a smart-constructor / validated newtype).
- **H4 — `re.search` MULTILINE semantics never pinned.** The example pattern `^FROM cgr\.dev/chainguard/` uses anchor `^` — `re.search` defaults to **single-line** mode where `^` only matches start of string. Pin: `re.search(pattern, contents, flags=re.MULTILINE)` (so `^` matches line starts inside the Dockerfile contents). AC-4d (new) is the mutation killer: a `FROM cgr.dev/chainguard/` line **not at the top** of the Dockerfile (e.g., preceded by a comment block) must `Pass` — would `Fail` without `re.MULTILINE`.
- **H5 — `file_glob` library / semantics never pinned.** AC-6 used `file_glob: "**/tsconfig.json"`. `pathlib.Path.glob` requires `Path.rglob("tsconfig.json")` for recursive; `Path.glob("**/tsconfig.json")` *also* recurses but with subtle dot-file rules. AC-6c (new) pins library and recursive semantics: `Path(repo.root).glob(rule.file_glob)` (NOT `rglob`), and asserts `file_glob: "**/foo.json"` finds `repo/x/y/foo.json` but does NOT match `repo/.hidden/foo.json` (dot-leading components excluded — `pathlib.Path.glob` default behavior).
- **H6 — `_apply_file_pattern` first-offending file is non-deterministic without sort.** Story says "the first offending file is named in `evidence`" but `Path.glob` order is filesystem-dependent. AC-6d (new) pins `evidence` to reference the **lexicographically-first failing path** (deterministic across filesystems); the implementation `sorted(...)`s the glob result before iterating.
- **H7 — `dockerfile_pattern_inverted` independent-helper invariant unenforced.** Notes say "don't share machinery with `_apply_dockerfile_pattern`." AC-5a (new) is an AST source-scan ratchet: `_apply_dockerfile_pattern_inverted` body must not contain a call to `_apply_dockerfile_pattern`. Mutation-killer for the "just invert the Pass/Fail" anti-pattern.
- **H8 — `Pass` evidence-emptiness invariant absent.** A defensive implementer might add `evidence: str = ""` to `Pass`. AC-9a (new): `Pass` has exactly the fields `{kind, rule_id}` and `model_dump()` returns exactly `{"kind": "pass", "rule_id": "<id>"}`. Same for `NotApplicable` (`{kind, rule_id, reason}`) and `Fail` (`{kind, rule_id, evidence}`). Pins the "make illegal states unrepresentable" discipline at the field-set level.
- **H9 — Toolchain extension to forbid direct `yaml.*` import via AST (not ripgrep).** AC-10 originally said `ripgrep "yaml\\." src/codegenie/conventions/`. S2-01 hardening surfaced that ripgrep misses aliases (`from yaml import safe_load as _y`). AC-10 now uses an `ast.parse` + `ast.walk` source-scan in `tests/unit/conventions/test_no_direct_yaml_import.py` — same shape as S2-01 AC-24.
- **H10 — `model_construct` ban via AST source-scan.** AC-14 was a "pre-commit hook scans … finds zero" — same alias-resistance concern as H9. AC-14 now an AST-source-scan test colocated with the test suite.
- **H11 — TOCTOU on catalog-file disappearance between glob and `safe_yaml.load`.** S2-01 hardened with `IoFailure(path, errno_name)`. AC-13a (new) wires the same: between `Path.glob("*.yaml")` enumeration and `safe_yaml.load(catalog_path)`, the file may be removed (`FileNotFoundError`). The hardened story adds `catalog_file_unreadable` semantics covering any non-symlink `OSError` (`FileNotFoundError`, `PermissionError`, `IsADirectoryError`) with `errno_name: str` field.
- **H12 — `LoadOutcome` partial-success shape consistent with S2-01.** Original `load_all` returns `Result[Catalog, ConventionsError]` — single-error semantics, fail-fast at first bad catalog. But the loader walks multiple catalog files and a per-file partial-success shape matches S2-01's convention (loaded skills + per-file errors), letting operators inspect a portfolio gather where some catalog files are good and others malformed. Hardened: `load_all(self) -> Result[CatalogLoadOutcome, FatalLoadError]` where `CatalogLoadOutcome(catalog: Catalog, per_file_errors: list[ConventionsError])` — same shape as S2-01's `LoadOutcome(skills, per_file_errors)`. A fatal `FatalLoadError` is reserved for "no search path is readable" / "every catalog file failed and the operator asked for fail-fast" (Phase 2 ships partial-success only; fail-fast deferred to a follow-up). AC-3, AC-3a, AC-3b, AC-13 are written against the partial-success shape; AC-13b pins that one malformed catalog does not erase other catalogs' rules from `outcome.catalog.rules`.
- **NEEDS RESEARCH:** none. All findings closeable from arch + ADRs + verified repo state (`src/codegenie/probes/base.py`, `src/codegenie/parsers/safe_yaml.py`, `src/codegenie/result.py`, `src/codegenie/types/identifiers.py`) + S2-01 hardening precedent. Stage 3 skipped.

A full audit log is at [`_validation/S2-02-conventions-catalog-loader.md`](_validation/S2-02-conventions-catalog-loader.md).

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

Ship `src/codegenie/conventions/` (four files: `__init__.py`, `model.py`, `loader.py`, `catalog.py`) plus a single-symbol additive extension to `src/codegenie/types/identifiers.py` (adds `ConventionId`).

```python
# codegenie/types/identifiers.py — additive extension (B2)
ConventionId = NewType("ConventionId", str)
# __all__ extended with "ConventionId"; existing newtypes unchanged.

# codegenie/conventions/model.py
class ConventionRuleDockerfilePattern(BaseModel):           # frozen=True, extra="forbid"
    kind: Literal["dockerfile_pattern"] = "dockerfile_pattern"
    id: ConventionId
    description: str
    pattern: str                                            # regex source; compiled by model_validator (H3 / DP1)
class ConventionRuleDockerfilePatternInverted(BaseModel):
    kind: Literal["dockerfile_pattern_inverted"] = "dockerfile_pattern_inverted"
    id: ConventionId
    description: str
    pattern: str                                            # must NOT match; compiled at load
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
    file_glob: str                                          # presence-as-assertion

ConventionRule = Annotated[
    Union[ConventionRuleDockerfilePattern, ConventionRuleDockerfilePatternInverted,
          ConventionRuleFilePattern, ConventionRuleMissingFile],
    Field(discriminator="kind")
]

class Pass(BaseModel):                                       # frozen=True, extra="forbid"
    kind: Literal["pass"] = "pass"
    rule_id: ConventionId
class Fail(BaseModel):
    kind: Literal["fail"] = "fail"
    rule_id: ConventionId
    evidence: str
class NotApplicable(BaseModel):
    kind: Literal["not_applicable"] = "not_applicable"
    rule_id: ConventionId
    reason: str
ConventionResult = Annotated[Union[Pass, Fail, NotApplicable], Field(discriminator="kind")]

# codegenie/conventions/loader.py — ConventionsError discriminated union (B6 — seven reasons)
class UnknownPatternType(BaseModel):       # frozen=True, extra="forbid"
    reason: Literal["unknown_pattern_type"] = "unknown_pattern_type"
    path: Path
    offending_kind: str
class SchemaError(BaseModel):
    reason: Literal["schema"] = "schema"
    path: Path
    details: list[dict[str, JSONValue]]    # Pydantic ValidationError.errors() shape
class SymlinkRefused(BaseModel):
    reason: Literal["symlink_refused"] = "symlink_refused"
    path: Path
class UnsafeYaml(BaseModel):               # umbrella for every MalformedYAMLError cause (B6, S2-01 convention)
    reason: Literal["unsafe_yaml"] = "unsafe_yaml"
    path: Path
class SizeCapExceeded(BaseModel):
    reason: Literal["size_cap_exceeded"] = "size_cap_exceeded"
    path: Path
class DepthCapExceeded(BaseModel):
    reason: Literal["depth_cap_exceeded"] = "depth_cap_exceeded"
    path: Path
class CatalogFileUnreadable(BaseModel):
    reason: Literal["catalog_file_unreadable"] = "catalog_file_unreadable"
    path: Path
    errno_name: str                        # e.g., "ENOENT", "EACCES", "EISDIR"
ConventionsError = Annotated[
    Union[UnknownPatternType, SchemaError, SymlinkRefused, UnsafeYaml,
          SizeCapExceeded, DepthCapExceeded, CatalogFileUnreadable],
    Field(discriminator="reason"),
]

class CatalogLoadOutcome(BaseModel):       # frozen=True, extra="forbid"
    catalog: Catalog
    per_file_errors: list[ConventionsError]

class FatalLoadError(BaseModel):           # frozen=True; reserved for "no search path readable"
    reason: Literal["no_search_path_readable"] = "no_search_path_readable"
    paths: list[Path]

# codegenie/conventions/catalog.py
class Catalog(BaseModel):                  # frozen=True, extra="forbid"
    rules: list[ConventionRule]
    def apply(self, repo: RepoSnapshot) -> list[ConventionResult]: ...

# Module-level (NOT a method on Catalog — B5):
def _apply_one(rule: ConventionRule, repo: RepoSnapshot) -> ConventionResult: ...
def _apply_dockerfile_pattern(rule, repo) -> ConventionResult: ...
def _apply_dockerfile_pattern_inverted(rule, repo) -> ConventionResult: ...
def _apply_file_pattern(rule, repo) -> ConventionResult: ...
def _apply_missing_file(rule, repo) -> ConventionResult: ...

class ConventionsCatalogLoader:
    def __init__(self, search_paths: list[Path]) -> None: ...      # pure data; no I/O
    def load_all(self) -> Result[CatalogLoadOutcome, FatalLoadError]: ...
```

With invariants:

1. **Constructor is pure data.** `__init__` stores `self._search_paths = list(search_paths)`; no I/O. First I/O is `load_all()`.
2. **`load_all()` uses `safe_yaml.load` exclusively.** No `yaml.*` imports anywhere in `src/codegenie/conventions/` — enforced by an AST source-scan in `tests/unit/conventions/test_no_direct_yaml_import.py` (H9), not a ripgrep (alias-resistant).
3. **Unknown `kind` → `per_file_errors` entry `UnknownPatternType(path=path, offending_kind=...)`.** Caught by Pydantic's `Field(discriminator="kind")` `ValidationError`; loader's `_classify_validation_error` helper distinguishes discriminator-tag failures from schema-shape failures by inspecting `errors()[i]["type"]` (`"union_tag_invalid"` / `"literal_error"` for tag failures; everything else is `SchemaError`).
4. **`Catalog.apply(repo)` is a single `match rule` switch with `assert_never` on the unreachable branch — `_apply_one` is a module-level function, not a method on `Catalog`.** Each variant has a dedicated `_apply_<kind>(rule, repo)` helper returning a `ConventionResult`. The discriminated-union `match` is the only branch on rule type; no `isinstance` chains; no string lookup tables; the `case _ as unreachable: assert_never(unreachable)` arm is the load-bearing exhaustiveness pin. `mypy --warn-unreachable` per-module on `codegenie.conventions.*` makes a missing arm a build failure.
5. **`NotApplicable` is the load-bearing third value.** A `dockerfile_pattern` rule against a repo with no `Dockerfile` → `NotApplicable(rule_id=rule.id, reason="no_dockerfile_present")`, **not** `Pass`. A `file_pattern` rule whose `file_glob` matches zero files → `NotApplicable(rule_id=rule.id, reason="file_glob_no_matches")`. Every `Pass` / `Fail` / `NotApplicable` carries `rule_id == rule.id` exactly — asserted by AC-4 / AC-5 / AC-6 / AC-7 (B3).
6. **`ConventionsError` is a Pydantic discriminated union over seven `reason` literals** (`unknown_pattern_type`, `schema`, `symlink_refused`, `unsafe_yaml`, `size_cap_exceeded`, `depth_cap_exceeded`, `catalog_file_unreadable`) — same shape as `SkillsLoadError` (S2-01 hardening B6). The `unsafe_yaml` umbrella covers every `MalformedYAMLError` cause (`!!python/object` constructor, syntax `ParserError`, `ScannerError`, top-level-non-mapping) — operationally-prudent name; convention documented in Notes-for-implementer.
7. **`Catalog.apply` is pure given a fixed `RepoSnapshot`.** Two consecutive `apply()` calls return equal `list[ConventionResult]`; the second call performs zero `os.open` / `Path.read_text` calls on the repo files (the first call may; the snapshot is the I/O boundary). AC-12 pins this with a counter-monkeypatch.
8. **Pattern regexes compile at load time, not at apply time.** A Pydantic `model_validator(mode="after")` on `ConventionRuleDockerfilePattern` / `ConventionRuleDockerfilePatternInverted` / `ConventionRuleFilePattern` calls `re.compile(self.pattern)`; failure → `ValidationError` → loader wraps as `SchemaError`. The compiled regex is stashed on the model via `_compiled_pattern: re.Pattern[str]` (private; `model_config = ConfigDict(arbitrary_types_allowed=True)`) so `_apply_*` helpers do not re-compile per call. AC-11a pins the load-time failure; the compiled-once invariant is documented in Notes (not promoted to AC because the per-apply timing is an implementation detail).
9. **Dockerfile pattern matching uses `re.MULTILINE`.** `re.search(rule.pattern, contents, flags=re.MULTILINE)` so `^` anchors match line starts inside multi-line Dockerfiles. AC-4d is the mutation killer.
10. **`file_glob` uses `pathlib.Path(repo.root).glob(rule.file_glob)`.** Recursive `**` is honored by `pathlib.Path.glob` natively; dot-leading path components are excluded by `pathlib` default. AC-6c pins library + recursion + dot-exclusion semantics. AC-6d pins `sorted(...)` ordering so multi-file `Fail` evidence is deterministic across xfs/ext4/APFS.
11. **`RepoSnapshot` is read at `repo.root`, not through a new method.** Phase 0 ADR-0007 freezes `RepoSnapshot`; the four `_apply_*` helpers compute `repo.root / relpath` and call `pathlib.Path` operations directly (`is_file()`, `read_text(encoding="utf-8", errors="replace")`). A capped-text helper local to `codegenie.conventions._io` (`read_capped_text(path, *, max_bytes=1 << 20) -> str | None`) is the safe reader; returns `None` when the file is absent. This avoids any Phase-0 ADR-0007 amendment. (B1.)
12. **`load_all()` returns `Result[CatalogLoadOutcome, FatalLoadError]` — partial success.** One malformed catalog file yields a `per_file_errors` entry; other catalog files still load (B6, H12). `FatalLoadError(reason="no_search_path_readable", paths=...)` is reserved for the catastrophic case where every entry in `search_paths` is unreadable (`os.access(path, os.R_OK) == False` for all). Empty `search_paths` → `Result.Ok(CatalogLoadOutcome(catalog=Catalog(rules=[]), per_file_errors=[]))`.

## Acceptance criteria

- [ ] **AC-1 — module surface.** `src/codegenie/conventions/__init__.py` exports — via exact-set `__all__` — `Catalog`, `ConventionsCatalogLoader`, `ConventionRule`, `ConventionResult`, `Pass`, `Fail`, `NotApplicable`, `ConventionsError`, `CatalogLoadOutcome`, `FatalLoadError`, and each of the four `ConventionRule*` Pydantic classes and each of the seven `ConventionsError` variant classes. `Pass`/`Fail`/`NotApplicable` and the four `ConventionRule*` variants and `Catalog` and `CatalogLoadOutcome` are all `frozen=True, extra="forbid"`. The two domain discriminated unions (`ConventionRule`, `ConventionResult`) use `Field(discriminator="kind")`; `ConventionsError` uses `Field(discriminator="reason")`.
- [ ] **AC-1a — `ConventionId` lives in `codegenie.types.identifiers`.** `from codegenie.types.identifiers import ConventionId` resolves; `ConventionId.__module__ == "codegenie.types.identifiers"`. AST source-scan in `tests/unit/conventions/test_no_local_convention_id.py` finds zero `NewType("ConventionId", ...)` calls under `src/codegenie/conventions/` (B2 — single canonical newtype home).
- [ ] **AC-2 — pure-data constructor (no I/O).** `ConventionsCatalogLoader(search_paths=[non_existent_path, another_missing_path])` does not raise and does not call any I/O primitive. Asserted by `monkeypatch.setattr` over all of `os.listdir`, `os.scandir`, `os.open`, `os.stat`, `pathlib.Path.exists`, `pathlib.Path.is_dir`, `pathlib.Path.glob`, `pathlib.Path.iterdir`, each replaced by `lambda *a, **kw: pytest.fail("constructor performed I/O")` (strengthens against `Path.glob` / `Path.iterdir` smuggling; matches S2-01 AC-2).
- [ ] **AC-3 — happy path per pattern type.** Parametrized over the four `kind` literals (`dockerfile_pattern`, `dockerfile_pattern_inverted`, `file_pattern`, `missing_file`): each test loads a one-rule catalog YAML and asserts the loaded `Catalog.rules[0]` is the matching `ConventionRule*` class with **every field fully populated** — `kind` literal, `id == ConventionId("<expected>")`, `description == "<expected literal>"`, `pattern`/`file_glob` exactly as authored. Replaces the kind-only assertion (H1 — catches a partial-deserialization mutation that loses `description` or `id`).
- [ ] **AC-3a — multi-rule single-file catalog round-trips in order.** A two-rule catalog YAML with `kind: dockerfile_pattern` first and `kind: missing_file` second yields `len(outcome.catalog.rules) == 2`, `outcome.catalog.rules[0].kind == "dockerfile_pattern"`, `outcome.catalog.rules[1].kind == "missing_file"`. Pins YAML-list order preservation.
- [ ] **AC-3b — multi-file catalog merge is sorted-relative-path order.** Two YAML files in the same `search_paths[0]` directory — `b.yaml` containing one rule with id `from-b`, `a.yaml` containing one rule with id `from-a`. After `load_all()`, `outcome.catalog.rules[0].id == ConventionId("from-a")` and `outcome.catalog.rules[1].id == ConventionId("from-b")` (lexicographic sort by `path.relative_to(search_root)` — deterministic across xfs/ext4/APFS).
- [ ] **AC-4 — `dockerfile_pattern` `Pass` / `Fail` / `NotApplicable` (rule_id assertion-strict).** Three sub-tests with one rule of `id: distroless-base`:
  - Repo with `Dockerfile` containing matching pattern → `Pass(rule_id=ConventionId("distroless-base"))` — `result.rule_id` assertion is exact.
  - Repo with `Dockerfile` not matching → `Fail(rule_id=ConventionId("distroless-base"), evidence=...)`. The `evidence` string contains either the offending line or the literal `"pattern not found in Dockerfile"`; `evidence != ""`.
  - Repo with no `Dockerfile` → `NotApplicable(rule_id=ConventionId("distroless-base"), reason="no_dockerfile_present")`. Reason literal pinned exactly.
- [ ] **AC-4d — `re.MULTILINE` semantics (`^` matches line starts).** Fixture: rule `pattern: '^FROM cgr\.dev/chainguard/'` against a `Dockerfile` whose **first** line is a `# comment` and whose second line is `FROM cgr.dev/chainguard/node:latest` — must return `Pass`. An implementation that omits `re.MULTILINE` from `re.search` returns `Fail` (H4 mutation killer).
- [ ] **AC-5 — `dockerfile_pattern_inverted` three outcomes (rule_id assertion-strict).** Symmetric to AC-4 with one rule of `id: no-root-user`: matching pattern → `Fail` (`rule_id` exact); absent pattern → `Pass` (`rule_id` exact); no `Dockerfile` → `NotApplicable(rule_id=..., reason="no_dockerfile_present")`. Mutation killer for the off-by-negation `Pass` ↔ `Fail` flip.
- [ ] **AC-5a — `_apply_dockerfile_pattern_inverted` does not delegate to `_apply_dockerfile_pattern`.** AST source-scan in `tests/unit/conventions/test_inverted_helper_is_independent.py` parses `src/codegenie/conventions/catalog.py`, locates the `_apply_dockerfile_pattern_inverted` function node, and asserts no `Call` whose `func.id == "_apply_dockerfile_pattern"` exists in its body. Mutation killer for the "just invert the Pass" anti-pattern (H7; Notes-for-implementer §"Don't share machinery").
- [ ] **AC-6 — `file_pattern` over a `file_glob` of zero matches → `NotApplicable`.** Rule `id: tsconfig-strict`, `file_glob: "**/tsconfig.json"`, against a repo with **no** `tsconfig.json` anywhere → `NotApplicable(rule_id=ConventionId("tsconfig-strict"), reason="file_glob_no_matches")` (exact `reason` literal; exact `rule_id`). Distinct from `Pass`. Pins the "empty match-set conflated with passing" bug.
- [ ] **AC-6a — `file_pattern` `Pass` when every matched file matches the pattern.** Rule `pattern: '"strict"\s*:\s*true'`, `file_glob: "**/tsconfig.json"`, against a repo with two `tsconfig.json` files both containing `"strict": true` → `Pass(rule_id=...)`.
- [ ] **AC-6b — `file_pattern` `Fail` names the lexicographically-first failing file (deterministic order).** Repo with `a/tsconfig.json` (passes) + `b/tsconfig.json` (fails) + `z/tsconfig.json` (fails). The `Fail.evidence` string contains `"b/tsconfig.json"` (the lexicographically-first failing path relative to `repo.root`), **not** `"z/tsconfig.json"` — pins `sorted(...)` over `Path.glob` results before iterating (H6).
- [ ] **AC-6c — `pathlib.Path.glob` library + recursive `**` + dot-component exclusion.** Rule `file_glob: "**/foo.json"` against a repo containing `repo/x/y/foo.json` and `repo/.hidden/foo.json` (a dot-leading subdirectory). The hidden file is **excluded** (pathlib `glob` default behavior); the visible file participates. Pins library choice (`pathlib.Path.glob`, not `glob.glob`, not `Path.rglob`).
- [ ] **AC-7 — `missing_file` semantics (rule_id assertion-strict).** Rule `id: no-rogue-dockerfile`, `file_glob: "Dockerfile"`:
  - Against a repo **without** `Dockerfile` → `Pass(rule_id=ConventionId("no-rogue-dockerfile"))`. The rule **succeeds** when the file is **absent** — the kind is named for the assertion, not the observed outcome.
  - Against a repo **with** `Dockerfile` → `Fail(rule_id=..., evidence=...)`. `evidence` contains the literal substring `"Dockerfile"` (the offending file's relative path).
- [ ] **AC-8 — unknown pattern type → `per_file_errors` entry, other rules unaffected.** Catalog YAML with one rule `kind: dockerfile_pattern_glob` (not in the enumerated four) + one well-formed `kind: missing_file` rule in a sibling YAML file. After `load_all()`: `outcome.per_file_errors` contains exactly one entry, an `UnknownPatternType(path=<bad-catalog-path>, offending_kind="dockerfile_pattern_glob")`; `outcome.catalog.rules` contains the well-formed `missing_file` rule (`len(...) == 1`). Asserts the partial-success contract (B6/H12).
- [ ] **AC-8a — `unsafe_yaml` umbrella covers `MalformedYAMLError` family (operationally-prudent name).** Two sub-tests, both produce `per_file_errors=[UnsafeYaml(path=...)]`:
  - Catalog YAML containing `!!python/object/apply:os.system ['touch {sentinel}']` — sentinel file does not exist after `load_all()`; `!isinstance(per_file_errors[0], (SchemaError, SizeCapExceeded))`.
  - Catalog YAML with a syntactic typo (`rules: [` — unterminated sequence) — same `UnsafeYaml` bucket. Operator reads `unsafe_yaml` and inspects (B6, S2-01 convention).
- [ ] **AC-8b — `size_cap_exceeded` on > 1 MiB catalog.** Catalog YAML padded to 1.1 MiB → `per_file_errors=[SizeCapExceeded(path=...)]`. The `safe_yaml.load(catalog_path, max_bytes=1 << 20)` call boundary is what fires. Other catalog files in the same `search_paths[0]` still load.
- [ ] **AC-8c — `depth_cap_exceeded` on deeply-nested catalog.** Catalog YAML with `rules: [{x: {y: {z: ...}}}]` nesting > 64 levels → `per_file_errors=[DepthCapExceeded(path=...)]`. Inherits `safe_yaml.load`'s `max_depth=64` default.
- [ ] **AC-9 — exhaustive `match` with `assert_never` (compile-time + runtime).** Two halves:
  - Compile-time half (`tests/unit/conventions/test_apply_match_is_exhaustive_compile_time.py`): a fixture script imports `codegenie.conventions.catalog._apply_one` and pattern-matches; `mypy --warn-unreachable` over that script must be clean. A complementary `tests/fixtures/mypy_unreachable_negative_should_fail/` (run under a separate `mypy` invocation that's expected to fail) proves removing a `case` arm causes a build failure.
  - Runtime half (`test_apply_match_smoke_asserts_assert_never_only`): a hand-constructed `_Imposter` object with `kind="not_a_real_kind"` is passed to **module-level** `_apply_one`; `pytest.raises(AssertionError)` only (NOT `TypeError` / `ValueError` — B4 / TQ1). The `assert_never` is the load-bearing signal; an `isinstance`-whitelist `raise TypeError("unknown kind")` is the anti-pattern this test catches.
- [ ] **AC-9a — `Pass` / `Fail` / `NotApplicable` field sets are exactly minimal (illegal-states-unrepresentable).** `Pass(rule_id=ConventionId("x")).model_dump() == {"kind": "pass", "rule_id": "x"}` (no `evidence`, no `reason`). `Fail(rule_id=ConventionId("x"), evidence="y").model_dump() == {"kind": "fail", "rule_id": "x", "evidence": "y"}`. `NotApplicable(rule_id=ConventionId("x"), reason="y").model_dump() == {"kind": "not_applicable", "rule_id": "x", "reason": "y"}`. Adding an extra field on construction (e.g., `Pass(rule_id=..., evidence="leak")`) raises `ValidationError` (frozen+extra=forbid). Pins ADR-0033 §4.
- [ ] **AC-10 — `safe_yaml.load` chokepoint via AST source-scan (alias-resistant).** `tests/unit/conventions/test_no_direct_yaml_import.py` parses every `.py` file under `src/codegenie/conventions/` with `ast.parse`, walks `Import` / `ImportFrom` nodes, and asserts:
  - No `import yaml` or `from yaml import ...` statement (alias-resistant — catches `from yaml import safe_load as _y`).
  - No identifier whose `Attribute.value.id == "yaml"` (e.g., `yaml.safe_load(...)` — catches `import yaml` followed by usage).
  - Companion runtime test `test_catalog_loader_routes_yaml_through_safe_yaml_chokepoint` uses `monkeypatch.setattr(codegenie.parsers.safe_yaml, "load", spy)` and asserts `spy` was called once per catalog file. Replaces the original `ripgrep` AC (H9 — S2-01 AC-24 precedent).
- [ ] **AC-11 — sub-schemas with `additionalProperties: false` (`extra="forbid"`).** A catalog YAML with an unknown field (`unexpected_key: value`) on a rule entry produces `per_file_errors=[SchemaError(path=..., details=[...])]` with `details` a non-empty `list[dict]` containing at least one row whose `loc` references the offending field. Pins the "silently ignore unknown keys" anti-pattern. Other rules in other catalog files still load.
- [ ] **AC-11a — uncompilable regex `pattern` → `SchemaError` at load (not at apply).** Catalog YAML with one rule `kind: dockerfile_pattern`, `pattern: "[unterminated"` (`re.error: unterminated character set`) → `per_file_errors=[SchemaError(path=..., details=[...])]` with at least one details row whose `loc` ends in `"pattern"`. Compilation happens via a Pydantic `model_validator(mode="after")`; `Catalog.apply` never sees an uncompilable regex (DP1; H3).
- [ ] **AC-12 — `Catalog.apply(repo)` is pure (idempotent + no repo I/O on repeated calls).** Given the same `RepoSnapshot`, two consecutive `apply()` calls return equal `list[ConventionResult]` (`first == second`). The second call performs zero `pathlib.Path.read_text` and zero `pathlib.Path.open` calls over the repo files (asserted via `monkeypatch` counters wrapped around `pathlib.Path.read_text`/`pathlib.Path.open`). The first call may read repo files (e.g., the `Dockerfile`); the snapshot is the I/O boundary. The hardened story does NOT add a `read_text` method to `RepoSnapshot` (B1) — counters wrap the *underlying* `pathlib.Path` methods.
- [ ] **AC-13 — `ConventionsError` discriminated union, seven reasons enumerated (sixth-and-after raises).** Test parametrizes over `{"unknown_pattern_type", "schema", "symlink_refused", "unsafe_yaml", "size_cap_exceeded", "depth_cap_exceeded", "catalog_file_unreadable"}` and asserts each constructs successfully via the discriminator with the documented field set; an eighth reason (`reason="bogus"`) raises `ValidationError`. JSON-shape pin: `SymlinkRefused(path=Path("/x")).model_dump() == {"reason": "symlink_refused", "path": "/x"}` (cross-version mutation catcher; S2-01 AC-10 precedent).
- [ ] **AC-13a — TOCTOU on catalog disappearance → `CatalogFileUnreadable` (other rules unaffected).** Fixture: two catalog files; between `Path.glob("*.yaml")` enumeration and `safe_yaml.load`, the first file is deleted (`monkeypatch.setattr(safe_yaml, "load", _raise_filenotfound_for_first_then_real)`). `outcome.per_file_errors == [CatalogFileUnreadable(path=<missing>, errno_name="ENOENT")]`; the second catalog's rules are present in `outcome.catalog.rules`.
- [ ] **AC-13b — partial-success contract under mixed-quality catalogs.** Three catalog files in `search_paths[0]`: one well-formed, one with `unknown_pattern_type`, one with `unsafe_yaml`. `len(outcome.catalog.rules) >= 1` (the well-formed catalog's rules persist); `len(outcome.per_file_errors) == 2` with one `UnknownPatternType` and one `UnsafeYaml`. Erasure of well-formed rules due to a sibling-catalog failure would be a regression (H12).
- [ ] **AC-13c — empty `search_paths` returns `Result.Ok(empty)`.** `ConventionsCatalogLoader(search_paths=[]).load_all() == Result.Ok(CatalogLoadOutcome(catalog=Catalog(rules=[]), per_file_errors=[]))`. The constructor with empty list does not crash and `load_all` produces a valid empty outcome.
- [ ] **AC-13d — fatal `no_search_path_readable` when every search path is unreadable.** `monkeypatch.setattr(os, "access", lambda *a, **kw: False)` + non-empty `search_paths` → `Result.Err(FatalLoadError(reason="no_search_path_readable", paths=<input search_paths>))`. The single fatal-shape; everything else is partial-success.
- [ ] **AC-14 — `model_construct` AST source-scan ban.** `tests/unit/conventions/test_no_model_construct.py` parses every `.py` under `src/codegenie/conventions/`, walks `Attribute` / `Call` nodes, and asserts no expression of the form `<X>.model_construct(...)`. Complementary `forbidden-patterns` pre-commit hook extension scans the same paths (defense in depth; matches H10 alias-resistance).
- [ ] **AC-15 — toolchain.** `ruff check`, `ruff format --check`, `mypy --strict`, `mypy --warn-unreachable` (per-module override on `codegenie.conventions.*`) all clean. `pytest tests/unit/conventions/` passes.
- [ ] **AC-16 — TDD discipline.** Red tests committed failing; green commit makes them pass; refactor commit is no-op behavior.

## Implementation outline

0. **`src/codegenie/types/identifiers.py`** — additive: append `ConventionId = NewType("ConventionId", str)` and add `"ConventionId"` to `__all__`. No edits to existing newtypes. Open/Closed at the file boundary; ADR-0033 §1; B2 closure.
1. **`src/codegenie/conventions/model.py`** — `from codegenie.types.identifiers import ConventionId`. Define the four `ConventionRule*` Pydantic models. Each `pattern`-carrying variant gets a `model_validator(mode="after")` that calls `re.compile(self.pattern)` and stashes the result on `_compiled_pattern` (private, `model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True, extra="forbid")`); `re.error` propagates as `ValueError` for Pydantic to bundle into `ValidationError`. Define the `ConventionRule` discriminated union with `Field(discriminator="kind")`. Define `Pass` / `Fail` / `NotApplicable` (each `frozen=True, extra="forbid"`, field sets exactly as AC-9a pins) and the `ConventionResult` discriminated union.
2. **`src/codegenie/conventions/loader.py`** — define the seven `ConventionsError` variants (`UnknownPatternType`, `SchemaError`, `SymlinkRefused`, `UnsafeYaml`, `SizeCapExceeded`, `DepthCapExceeded`, `CatalogFileUnreadable`) as `frozen=True, extra="forbid"` Pydantic models, each with its `Literal[…]` reason discriminator + `path: Path` + per-variant fields. Define the `ConventionsError` `Annotated[Union[...], Field(discriminator="reason")]`. Define `CatalogLoadOutcome(catalog: Catalog, per_file_errors: list[ConventionsError])` and `FatalLoadError(reason: Literal["no_search_path_readable"], paths: list[Path])`. Define `_classify_validation_error(exc: ValidationError, path: Path) -> ConventionsError` — inspects `exc.errors()` rows; a row whose `type` is `"union_tag_invalid"` or `"literal_error"` with `loc[-1] == "kind"` → `UnknownPatternType(offending_kind=<row.input>)`; a row whose loc ends in `"pattern"` with `type` indicating the `model_validator` re-raise → `SchemaError` (regex compile failure surfaces here via Pydantic's wrapping of `ValueError`); everything else → `SchemaError(details=exc.errors())`. Define `ConventionsCatalogLoader.__init__(self, search_paths: list[Path]) -> None` storing `self._search_paths = list(search_paths)` (no I/O). Define `ConventionsCatalogLoader.load_all(self) -> Result[CatalogLoadOutcome, FatalLoadError]` as the multi-file partial-success driver (§4 below).
3. **`_apply_dockerfile_pattern(rule, repo)` (module-level in `catalog.py`)** — `dockerfile_path = repo.root / "Dockerfile"`. If `not dockerfile_path.is_file()` → `NotApplicable(rule_id=rule.id, reason="no_dockerfile_present")`. Read via `_io.read_capped_text(dockerfile_path, max_bytes=1 << 20)` (returns `None` if absent — defense in depth against TOCTOU between `is_file` and `read_text`). `match = re.search(rule.pattern, contents, flags=re.MULTILINE)` — match → `Pass(rule_id=rule.id)`; no match → `Fail(rule_id=rule.id, evidence="pattern not found in Dockerfile")`. Regex is already compiled by the model_validator; this call uses the compiled regex (`rule._compiled_pattern.search(contents)`) — the `re.search(rule.pattern, ...)` form above is shorthand. AC-4d pins `re.MULTILINE`.
4. **`_apply_dockerfile_pattern_inverted(rule, repo)`** — independent body (NOT a wrapper over `_apply_dockerfile_pattern` — AC-5a AST-source-scan enforces this). Same locate (`repo.root / "Dockerfile"` + `is_file` + capped read); `re.search(..., flags=re.MULTILINE)` — match → `Fail(rule_id=..., evidence="forbidden pattern present")`; no match → `Pass(rule_id=...)`; absent file → `NotApplicable(rule_id=..., reason="no_dockerfile_present")`. The negation lives in this helper; each helper reads `repo` independently (Rule of Three; arch §"Design patterns applied" row 8).
5. **`_apply_file_pattern(rule, repo)`** — `matches = sorted(repo.root.glob(rule.file_glob), key=lambda p: p.relative_to(repo.root).as_posix())` (deterministic ordering across filesystems; AC-6b/AC-6c). Zero matches → `NotApplicable(rule_id=rule.id, reason="file_glob_no_matches")`. Iterate matches in order; for each, `contents = _io.read_capped_text(path, max_bytes=1 << 20)` then `re.search(rule.pattern, contents, flags=re.MULTILINE)`. If any fails → return `Fail(rule_id=rule.id, evidence=f"{matches_relpath}: pattern not found")` for the first failing path (`matches_relpath = path.relative_to(repo.root).as_posix()`); if all pass → `Pass(rule_id=rule.id)`. Per-rule emission only (one `ConventionResult` per rule); per-file emission is out of scope.
6. **`_apply_missing_file(rule, repo)`** — `matches = sorted(repo.root.glob(rule.file_glob), key=lambda p: p.relative_to(repo.root).as_posix())`. Zero matches → `Pass(rule_id=rule.id)` (the assertion is "this file is absent"; the rule **succeeds** when no file matches). Any match → `Fail(rule_id=rule.id, evidence=f"unexpected file present: {matches[0].relative_to(repo.root).as_posix()}")`. Code comment in the function body documents the inverted naming convention for the next reader.
7. **`_apply_one(rule: ConventionRule, repo: RepoSnapshot) -> ConventionResult` (module-level in `catalog.py`)** — the exhaustive `match`:
   ```python
   def _apply_one(rule: ConventionRule, repo: RepoSnapshot) -> ConventionResult:
       match rule:
           case ConventionRuleDockerfilePattern():         return _apply_dockerfile_pattern(rule, repo)
           case ConventionRuleDockerfilePatternInverted(): return _apply_dockerfile_pattern_inverted(rule, repo)
           case ConventionRuleFilePattern():               return _apply_file_pattern(rule, repo)
           case ConventionRuleMissingFile():               return _apply_missing_file(rule, repo)
           case _ as unreachable:
               assert_never(unreachable)
   ```
   `Catalog.apply(self, repo)` is a thin wrapper: `return [_apply_one(rule, repo) for rule in self.rules]`. Module-level function so tests can call it without instantiating `Catalog` (B5; AC-9 runtime smoke).
8. **`ConventionsCatalogLoader.load_all(self)` — multi-file partial-success driver.** Pseudocode:
   ```
   if self._search_paths:
       readable = [p for p in self._search_paths if os.access(p, os.R_OK)]
       if not readable and any(self._search_paths):
           return Result.Err(FatalLoadError(reason="no_search_path_readable",
                                            paths=list(self._search_paths)))
   merged_rules: list[ConventionRule] = []
   per_file_errors: list[ConventionsError] = []
   for search_path in self._search_paths:
       if not search_path.is_dir():
           continue   # missing search path → silent skip; matches S2-01 AC-3a
       catalog_files = sorted(search_path.glob("*.yaml")) + sorted(search_path.glob("*.yml"))
       for catalog_path in catalog_files:
           try:
               data = safe_yaml.load(catalog_path, max_bytes=1 << 20, max_depth=64)
           except SymlinkRefusedError:
               per_file_errors.append(SymlinkRefused(path=catalog_path)); continue
           except MalformedYAMLError:
               per_file_errors.append(UnsafeYaml(path=catalog_path)); continue
           except SizeCapExceeded:
               per_file_errors.append(SizeCapExceeded(path=catalog_path)); continue
           except DepthCapExceeded:
               per_file_errors.append(DepthCapExceeded(path=catalog_path)); continue
           except OSError as exc:
               per_file_errors.append(CatalogFileUnreadable(
                   path=catalog_path,
                   errno_name=errno.errorcode.get(exc.errno, str(exc.errno)),
               ))
               continue
           try:
               sub_catalog = Catalog.model_validate(data)
           except ValidationError as exc:
               per_file_errors.append(_classify_validation_error(exc, catalog_path))
               continue
           merged_rules.extend(sub_catalog.rules)
   return Result.Ok(CatalogLoadOutcome(
       catalog=Catalog(rules=merged_rules),
       per_file_errors=per_file_errors,
   ))
   ```
   Phase 2 ships **without** rule-ID deduplication across catalog files (single-file fixtures are the norm); a follow-up ADR can decide whether duplicate IDs across files are an error or a last-wins merge. Within-tier files are processed in `sorted(...)` order (AC-3b).
9. **`src/codegenie/conventions/_io.py`** — single small helper:
   ```python
   def read_capped_text(path: Path, *, max_bytes: int) -> str | None:
       """Return decoded text up to ``max_bytes``; None if the file does not exist.

       TOCTOU-safe: handles FileNotFoundError between caller's existence check
       and this read. Files larger than max_bytes are truncated (the offending
       region beyond the cap is not part of any pattern check, which is the
       Phase 2 documented behavior — a 100 MB Dockerfile is non-idiomatic and
       the truncation is observable via byte-counting for an operator).
       """
       try:
           with path.open("rb") as fh:
               return fh.read(max_bytes).decode("utf-8", errors="replace")
       except FileNotFoundError:
           return None
   ```
   This is the only file-read entry point from `_apply_*` helpers. Phase 2 deliberately does NOT add a `read_text` method to `RepoSnapshot` (Phase 0 ADR-0007 contract freeze; B1).
10. **`src/codegenie/conventions/__init__.py`** — `__all__` re-exports per AC-1. Default factory `ConventionsCatalogLoader.default()` (classmethod) pins `[Path("~/.codegenie/conventions/").expanduser(), Path(".codegenie/conventions/")]` for production callers; tests pass explicit paths.
11. **`assert_never` import.** `from typing import assert_never` (Python 3.11+). The `mypy --warn-unreachable` per-module override in `pyproject.toml` (added in Step 1) ensures a missing variant in the `match` is a build error.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/unit/conventions/test_catalog.py` plus colocated AST-source-scan test files (`test_no_direct_yaml_import.py`, `test_no_model_construct.py`, `test_inverted_helper_is_independent.py`, `test_no_local_convention_id.py`, `test_apply_match_is_exhaustive_compile_time.py`). 30+ named tests covering AC-1..AC-16.

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
from codegenie.conventions.loader import (
    UnknownPatternType, SchemaError, UnsafeYaml, SymlinkRefused,
    SizeCapExceeded, DepthCapExceeded, CatalogFileUnreadable,
    CatalogLoadOutcome, FatalLoadError,
)
from codegenie.probes.base import RepoSnapshot
from codegenie.types.identifiers import ConventionId


def _write_catalog(p: Path, body: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def _repo_snapshot_with(tmp_path: Path, files: dict[str, str]) -> RepoSnapshot:
    """Build a Phase-0 RepoSnapshot rooted at tmp_path with the given files.

    Uses the dataclass constructor directly — `RepoSnapshot` is Phase-0
    contract-frozen (ADR-0007). No `build()` factory; no `read_text()` method
    on the snapshot — `_apply_*` helpers compute `repo.root / relpath`.
    """
    for relpath, contents in files.items():
        f = tmp_path / relpath
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(contents)
    return RepoSnapshot(
        root=tmp_path, git_commit=None, detected_languages={}, config={}
    )


def test_constructor_is_pure_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-2: __init__ must perform no I/O across the full primitive set."""
    def _fail(*a, **kw):
        pytest.fail(f"constructor performed I/O: args={a} kwargs={kw}")
    monkeypatch.setattr(os, "listdir", _fail)
    monkeypatch.setattr(os, "scandir", _fail)
    monkeypatch.setattr(os, "open", _fail)
    monkeypatch.setattr(os, "stat", _fail)
    monkeypatch.setattr(Path, "exists", _fail, raising=False)
    monkeypatch.setattr(Path, "is_dir", _fail, raising=False)
    monkeypatch.setattr(Path, "glob", _fail, raising=False)
    monkeypatch.setattr(Path, "iterdir", _fail, raising=False)
    ConventionsCatalogLoader(search_paths=[
        tmp_path / "does-not-exist", tmp_path / "also-missing",
    ])


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
    outcome = loader.load_all().unwrap()
    catalog = outcome.catalog
    assert outcome.per_file_errors == []
    expected_id = ConventionId("distroless-base")

    # Pass — rule_id assertion-strict (B3)
    repo_pass = _repo_snapshot_with(tmp_path / "pass-repo", {"Dockerfile": "FROM cgr.dev/chainguard/node:latest\n"})
    result_pass = catalog.apply(repo_pass)[0]
    assert isinstance(result_pass, Pass)
    assert result_pass.rule_id == expected_id

    # Fail — rule_id assertion-strict, evidence non-empty
    repo_fail = _repo_snapshot_with(tmp_path / "fail-repo", {"Dockerfile": "FROM node:20-alpine\n"})
    result_fail = catalog.apply(repo_fail)[0]
    assert isinstance(result_fail, Fail)
    assert result_fail.rule_id == expected_id
    assert result_fail.evidence != ""
    assert "pattern" in result_fail.evidence.lower() or "Dockerfile" in result_fail.evidence

    # NotApplicable — no Dockerfile; rule_id + reason exact
    repo_na = _repo_snapshot_with(tmp_path / "na-repo", {"package.json": "{}"})
    result_na = catalog.apply(repo_na)[0]
    assert isinstance(result_na, NotApplicable)
    assert result_na.rule_id == expected_id
    assert result_na.reason == "no_dockerfile_present"


def test_dockerfile_pattern_uses_re_multiline(tmp_path: Path) -> None:
    """AC-4d: ^ anchors must match line starts inside multi-line Dockerfile contents."""
    _write_catalog(tmp_path / "conventions" / "c.yaml", textwrap.dedent("""\
        rules:
          - kind: dockerfile_pattern
            id: distroless-base
            description: chainguard base required
            pattern: '^FROM cgr\\.dev/chainguard/'
        """))
    outcome = ConventionsCatalogLoader(
        search_paths=[tmp_path / "conventions"]
    ).load_all().unwrap()
    # FROM is on the second line — only re.MULTILINE makes ^ match here
    repo = _repo_snapshot_with(tmp_path / "r", {
        "Dockerfile": "# build args first\nFROM cgr.dev/chainguard/node:latest\n",
    })
    assert isinstance(outcome.catalog.apply(repo)[0], Pass)


def test_missing_file_kind_succeeds_when_file_absent(tmp_path: Path) -> None:
    """AC-7: the kind is named for the assertion; rule passes when file is absent."""
    _write_catalog(tmp_path / "conventions" / "c.yaml", textwrap.dedent("""\
        rules:
          - kind: missing_file
            id: no-rogue-dockerfile
            description: this repo must not ship its own Dockerfile
            file_glob: Dockerfile
        """))
    outcome = ConventionsCatalogLoader(
        search_paths=[tmp_path / "conventions"]
    ).load_all().unwrap()
    catalog = outcome.catalog
    expected_id = ConventionId("no-rogue-dockerfile")

    repo_clean = _repo_snapshot_with(tmp_path / "clean", {"package.json": "{}"})
    result_clean = catalog.apply(repo_clean)[0]
    assert isinstance(result_clean, Pass)
    assert result_clean.rule_id == expected_id

    repo_dirty = _repo_snapshot_with(tmp_path / "dirty", {"Dockerfile": "FROM scratch\n"})
    result_dirty = catalog.apply(repo_dirty)[0]
    assert isinstance(result_dirty, Fail)
    assert result_dirty.rule_id == expected_id
    assert "Dockerfile" in result_dirty.evidence


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
    outcome = ConventionsCatalogLoader(
        search_paths=[tmp_path / "conventions"]
    ).load_all().unwrap()
    expected_id = ConventionId("tsconfig-strict")
    repo_no_ts = _repo_snapshot_with(tmp_path / "no-ts", {"package.json": "{}"})
    result = outcome.catalog.apply(repo_no_ts)[0]
    assert isinstance(result, NotApplicable)
    assert result.rule_id == expected_id
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
    outcome = ConventionsCatalogLoader(
        search_paths=[tmp_path / "conventions"]
    ).load_all().unwrap()
    # Partial-success: per_file_errors carries the typed UnknownPatternType,
    # the well-formed-rules section is empty (only one bad rule was in this file).
    assert outcome.catalog.rules == []
    assert len(outcome.per_file_errors) == 1
    err = outcome.per_file_errors[0]
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
    outcome = ConventionsCatalogLoader(
        search_paths=[tmp_path / "conventions"]
    ).load_all().unwrap()
    assert outcome.catalog.rules == []
    assert len(outcome.per_file_errors) == 1
    err = outcome.per_file_errors[0]
    assert isinstance(err, SchemaError)
    # Pydantic ValidationError.errors() shape — details non-empty
    assert err.details
    assert any("unexpected_key" in str(row) for row in err.details)


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


def test_apply_match_smoke_asserts_assert_never_only() -> None:
    """AC-9 runtime half: the match must end in assert_never (NOT a defensive
    `raise TypeError("unknown kind")`). assert_never raises AssertionError.

    Allowing TypeError/ValueError would let the isinstance-whitelist anti-pattern
    pass — the load-bearing signal is compile-time exhaustiveness, not a
    runtime defensive check (ADR-0033 §4; B4 / TQ1).
    """
    from codegenie.conventions.catalog import _apply_one
    class _Imposter:
        kind = "not_a_real_kind"
    with pytest.raises(AssertionError):
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
    outcome = ConventionsCatalogLoader(
        search_paths=[tmp_path / "conventions"]
    ).load_all().unwrap()
    catalog = outcome.catalog
    repo = _repo_snapshot_with(tmp_path / "r", {"Dockerfile": "FROM node\n"})

    first = catalog.apply(repo)
    # Wrap the underlying pathlib I/O — RepoSnapshot has no read_text method
    # (B1; Phase 0 ADR-0007 contract freeze).
    opens: list = []
    real_open = Path.open
    def _spy_open(self, *a, **kw):
        # Only count reads against repo files, not catalog files (which would
        # not be re-read here anyway since load_all is done).
        if self.is_relative_to(repo.root):
            opens.append(self)
        return real_open(self, *a, **kw)
    monkeypatch.setattr(Path, "open", _spy_open, raising=False)
    second = catalog.apply(repo)
    assert first == second
    assert opens == [], f"second apply() performed disk I/O on repo: {opens}"
```

Run; confirm every test fails because `src/codegenie/conventions/` does not exist. Commit as red.

### Green — make it pass

Land in this order:

1. `src/codegenie/types/identifiers.py` — additive: append `ConventionId = NewType("ConventionId", str)` + extend `__all__`. Zero edits to existing newtypes (B2).
2. `src/codegenie/conventions/_io.py` — `read_capped_text(path, *, max_bytes) -> str | None` helper. Single small function; no public re-export.
3. `src/codegenie/conventions/model.py` — four `ConventionRule*` variants with `model_validator(mode="after")` for regex compilation (`_compiled_pattern` stash), `ConventionRule` discriminator union, `Pass` / `Fail` / `NotApplicable` (exact minimal field sets per AC-9a), `ConventionResult` discriminator union.
4. `src/codegenie/conventions/loader.py` — seven `ConventionsError` variants (`UnknownPatternType`, `SchemaError`, `SymlinkRefused`, `UnsafeYaml`, `SizeCapExceeded`, `DepthCapExceeded`, `CatalogFileUnreadable`), `ConventionsError` discriminator union, `CatalogLoadOutcome`, `FatalLoadError`, `ConventionsCatalogLoader` class with multi-file partial-success driver, `_classify_validation_error` helper over Pydantic `ValidationError.errors()`.
5. `src/codegenie/conventions/catalog.py` — `Catalog` Pydantic model (frozen, extra=forbid), four module-level `_apply_*` helpers, module-level `_apply_one` with `match` + `assert_never`. `Catalog.apply` is the thin list-comprehension wrapper.
6. `src/codegenie/conventions/__init__.py` — `__all__` re-exports per AC-1; `ConventionsCatalogLoader.default()` classmethod factory.
7. `tests/unit/conventions/__init__.py`, `test_catalog.py` (main suite from above), `test_no_direct_yaml_import.py` (AC-10 AST), `test_no_model_construct.py` (AC-14 AST), `test_inverted_helper_is_independent.py` (AC-5a AST), `test_no_local_convention_id.py` (AC-1a AST), `test_apply_match_is_exhaustive_compile_time.py` (AC-9 compile-time half).
8. `pyproject.toml` — if not already added in Step 1, the per-module `mypy --warn-unreachable` override on `codegenie.conventions.*`.

### Refactor — clean up

- Module docstring on `catalog.py` cites `phase-arch-design.md §"Component design" #10`, ADR-0033 §3–4, and the four pattern types.
- The four `_apply_*` helpers live as module-level pure functions (not methods on `Catalog`) so they're independently testable and so the `_apply_one` `match` is a thin dispatcher — easier to read, easier to extend.
- `RepoSnapshot.read_text(relpath)` is the abstraction; `_apply_*` helpers never touch `os.open` directly. If `RepoSnapshot` (Phase 0) doesn't expose the needed shape, file a follow-up — do not bypass.
- Do **not** introduce a shared `ScannerRunner` / pattern-engine class. Four small helpers, four distinct shapes, ~30 LOC each. Phase-2 final design row 7 forbids the abstraction.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Modify (additive) — append `ConventionId = NewType("ConventionId", str)` + `__all__` extension. Zero edits to existing newtypes. (B2) |
| `src/codegenie/conventions/__init__.py` | New — public surface (`__all__` exact-set) + `ConventionsCatalogLoader.default()` factory |
| `src/codegenie/conventions/model.py` | New — four `ConventionRule*` variants with regex-compile `model_validator` + `ConventionRule` union + `Pass`/`Fail`/`NotApplicable` (exact minimal field sets) + `ConventionResult` union |
| `src/codegenie/conventions/loader.py` | New — `ConventionsCatalogLoader`, seven-variant `ConventionsError` discriminated union, `CatalogLoadOutcome`, `FatalLoadError`, `_classify_validation_error` Pydantic-error introspection |
| `src/codegenie/conventions/catalog.py` | New — `Catalog` Pydantic model, module-level `_apply_*` helpers, module-level `_apply_one` `match` with `assert_never` |
| `src/codegenie/conventions/_io.py` | New — `read_capped_text(path, *, max_bytes) -> str \| None`; the only file-read entry point from `_apply_*` helpers (B1) |
| `tests/unit/conventions/__init__.py` | New — package marker |
| `tests/unit/conventions/test_catalog.py` | New — main behavioral suite (~22 tests covering AC-2..AC-13d) |
| `tests/unit/conventions/test_no_direct_yaml_import.py` | New — AC-10 AST source-scan (alias-resistant; replaces ripgrep) |
| `tests/unit/conventions/test_no_model_construct.py` | New — AC-14 AST source-scan |
| `tests/unit/conventions/test_inverted_helper_is_independent.py` | New — AC-5a AST source-scan over `catalog.py` (`_apply_dockerfile_pattern_inverted` body must not call `_apply_dockerfile_pattern`) |
| `tests/unit/conventions/test_no_local_convention_id.py` | New — AC-1a AST source-scan (no local `NewType("ConventionId", ...)` outside `types/identifiers.py`) |
| `tests/unit/conventions/test_apply_match_is_exhaustive_compile_time.py` | New — AC-9 compile-time half: `mypy --warn-unreachable` over a fixture script |
| `tests/fixtures/mypy_unreachable_negative/` | New — fixture script that removes a `case` arm; companion `mypy` invocation expected to fail (AC-9 compile-time) |
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

### Design-pattern notes (added by validator 2026-05-15)

These are *contextual* observations that make the story easy to maintain and extend by addition. They are not ACs because the observable behavior is already constrained — but a contributor reaching for a tempting shortcut should see this section before they decide.

- **`ConventionId` lives in `codegenie.types.identifiers`, not a sibling location.** The newtype roster is the canonical home for every domain identifier that crosses ≥ 2 module boundaries (ADR-0033 §1). `ConventionId` will be imported by `loader.py`, `model.py`, `catalog.py`, the future `ConventionsProbe` (S6-02), and the Layer E `Ownership` / `Topology` / `SLO` stubs (S6-05) — five consumers and counting; the lift is overdetermined. Story line 0 of the Implementation outline is the one-line addition; AC-1a is the AST source-scan ratchet. (B2 closure.)
- **`RepoSnapshot` is read at the boundary; no new method on the frozen contract.** Adding `RepoSnapshot.read_text(relpath)` or a `build()` factory would amend Phase 0 ADR-0007. The cheaper path is `repo.root / relpath` + a local `_io.read_capped_text` helper. This composes with the broader pattern: `RepoSnapshot` is the **input** boundary (where the I/O is *named*); `_apply_*` helpers are the **functional core** that consume it via `pathlib.Path` operations. Functional core / imperative shell, with `pathlib.Path` itself as the seam. If a future probe needs a `read_text` *method* (e.g., for caching policy reasons), that's a Phase ADR amendment with the contract-freeze sentinel test as the gate — not a quiet attribute addition. (B1 closure.)
- **Regex as smart-constructor (Pydantic `model_validator`, not deferred to apply-time).** Each `pattern`-carrying variant compiles its regex at load time. Compilation failure is a `SchemaError` event the operator sees during the gather phase, not a `RuntimeError` mid-`Catalog.apply` after dozens of repos have already been scanned. AC-11a is the load-time pin; the compiled-once cache (`_compiled_pattern` stash) is an implementation detail. Mirrors S1-03's `safe_yaml`-level discipline: bad input fails at the parse boundary, not the consumption boundary.
- **`unsafe_yaml` umbrella naming is operationally-prudent.** A YAML parse failure can be (a) a hostile `!!python/object/apply:os.system` constructor exploit, (b) a syntactic `ParserError`, (c) a `ScannerError` (e.g., illegal Unicode), or (d) top-level-non-mapping. `safe_yaml.load` fuses all four into `MalformedYAMLError`. Operators reading `unsafe_yaml` in a CLI log are expected to inspect the file before re-running — same posture for any of the four causes. Splitting the umbrella into `parse_error` / `constructor_exploit` would require inferring intent from `__cause__` chains, which Pydantic v2 has already revised. Convention: the umbrella name names the *operational response*, not the parser-flavored root cause. (B6; S2-01 convention.)
- **Partial-success multi-file pattern matches S2-01.** `CatalogLoadOutcome(catalog, per_file_errors)` mirrors S2-01's `LoadOutcome(skills, per_file_errors)`. The convention going forward: single-file loaders (`TCCMLoader`, S1-04) use `CodegenieError`-marker exceptions with string-prefixed `args[0]`; multi-file partial-success loaders (`SkillsLoader`, this story, future Phase 4+ loaders of the same shape) use Pydantic discriminated unions + a `LoadOutcome`-shaped envelope. Phase 3 plugin authors will import both and pattern-match uniformly across `SkillsLoadError` and `ConventionsError` — keep the field names (`reason`, `path`, `details`) identically shaped. (H12; CN3.)
- **Four independent `_apply_*` helpers (rule of three NOT reached).** Adding a fifth variant (e.g., `dockerfile_pattern_glob` in Phase 3+) is: (1) a new `ConventionRule*` class with its own `model_validator`, (2) extension of the `ConventionRule` `Annotated[Union[...]]`, (3) a new `_apply_<kind>` helper, (4) a new `case` arm in `_apply_one` (the `mypy --warn-unreachable` ratchet on `_apply_one` makes a missing arm a build failure). **Zero edits to existing helpers; zero edits to `Catalog` or `ConventionsCatalogLoader`.** Open/Closed at the file boundary. If/when a sixth variant arrives, that's the rule-of-three trigger to re-evaluate whether a shared `_PatternEngine` reads-and-matches helper is justified — but not before. Arch §"Design patterns applied" row 8 is the load-bearing observation here. (DP framing.)
- **`Pass` / `Fail` / `NotApplicable` field sets are exactly minimal (illegal-states-unrepresentable).** `Pass` has no `evidence` field; `NotApplicable` has no `evidence`; `Fail` has no `reason`. A `Pass(rule_id=..., evidence="leaky data")` is rejected by `extra="forbid"`. The Confidence section (Phase 2 Step 8) pattern-matches on `kind` and reads only the fields documented for that kind — no defensive "if hasattr(result, 'evidence')" reader. ADR-0033 §4. (AC-9a.)
- **Module-level `_apply_one`, not a `Catalog` method.** Tests need to smuggle an `_Imposter` into the `match` arm to verify `assert_never`. Calling it as `Catalog(rules=[]).apply(...)` would require constructing a synthetic rule that Pydantic would reject. Module-level form sidesteps this and matches the four `_apply_*` helpers' visibility. `Catalog.apply` is a thin list-comprehension wrapper — almost no behavior of its own. (B5.)
- **Three-and-counting newtype lift moments to watch.** This story lifts `ConventionId` to `codegenie.types.identifiers`. S1-05's existing `SkillId` / `TaskClassId` / `ProbeId` live there too. Future Phase 2 stories may want `Language`, `EvidenceKey`, `ConventionRuleKind`-as-newtype — they should follow the same pattern: extend the module additively; AST-source-scan ratchet in the consumer module to forbid local redefinition.
- **No env-var auto-discovery; explicit `search_paths`.** Mirrors S2-01 / arch §"Anti-patterns avoided" row 11. The `ConventionsCatalogLoader.default()` classmethod factory is the **only** place that resolves `~/.codegenie/conventions/` + `.codegenie/conventions/` from disk; tests pass explicit paths. A future contributor who wants `CODEGENIE_CONVENTIONS_PATH` env-var resolution should file an ADR — not silently extend the loader.
- **`Catalog.apply` is consumed by Layer D `ConventionsProbe` (S6-02) and Layer E stubs (S6-05).** Keep `apply` pure and snapshot-driven so the probes can call it inside a `@register_probe(heaviness="light")` slot without I/O surprises (AC-12). If a future rule type needs network access (e.g., remote-policy fetch), that's a new variant + a new probe layer; don't smuggle I/O into `_apply_*` helpers.
