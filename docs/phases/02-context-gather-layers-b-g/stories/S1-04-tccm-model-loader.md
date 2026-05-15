# Story S1-04 — `TCCM` Pydantic model + `DerivedQuery` five variants + `TCCMLoader`

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Ready · **HARDENED 2026-05-15**
**Effort:** M-to-L (Result type lifted in here per sibling-story dependency)
**Depends on:** S1-01, S1-05
**ADRs honored:** 02-ADR-0007

## Validation notes (2026-05-15)

This story was hardened by `phase-story-validator` on 2026-05-15. The draft was structurally sound (correct discriminated-union shape, correct `safe_yaml` chokepoint commitment, correct refusal of an `Unknown` fallback variant) but carried **three block-tier executor-halt risks** and **eleven harden-tier gaps** that would have let an obviously-wrong implementation pass the Validator. The third Pydantic-discriminated-union family in Phase 2 (after S1-01 `IndexFreshness` and S1-03 `AdapterConfidence`) inherits no symmetric discipline from those siblings by default — every harden-tier closure mirrors a corresponding S1-01 or S1-03 closure ratified in their validation reports.

**Block-tier corrections applied:**
1. **`Result[T, E]` did not exist in the codebase.** All draft tests used `.is_ok() / .unwrap() / .unwrap_err()`; the sketch's `from codegenie._result import Result` would `ImportError`. S2-01's `Depends on: S1-04` line explicitly names S1-04 as the home for `Result[T, E]`. This story now ships `src/codegenie/result.py` as a deliverable (frozen Pydantic discriminated union: `Ok[T] | Err[E]`) with its own ACs and tests. AC-9's tuple-fallback alternative is removed.
2. **`safe_yaml.load(path)` would `TypeError`.** The real signature is `load(path, *, max_bytes, max_depth=64)` with `max_bytes` required keyword-only — every Phase 1 caller passes it explicitly. The sketch and AC-5 are now corrected; a module-scope `_TCCM_MAX_BYTES: Final[int] = 64 * 1024` (per `localv2.md` "manifests are small (< 10 KB)" + 6× headroom) is pinned and a test asserts the keyword reaches `safe_yaml.load`.
3. **Markers-only invariant.** AC-4 / AC-8 originally used `TCCMLoadError(reason="…")` (kwarg, implying `__init__`); the loader sketch correctly used positional `TCCMLoadError("parse: …")`. Phase 0/1 markers are bare — no `__init__`, no class attrs (see `errors.py` module docstring; `MalformedYAMLError`, `CatalogLoadError` precedent). ACs now match the sketch (positional `args[0]` prefix-encoded reason); a structural test asserts `TCCMLoadError.__init__ is Exception.__init__`.

**Harden-tier additions (sibling-family symmetric discipline):** discriminator-string literal pin (AC-12); JSON-shape pin (AC-13); runtime-immutability assertion on every variant + `TCCM` (AC-14); per-variant `extra="forbid"` rejection of foreign payload fields (AC-15); exhaustive `match` + `assert_never` over `DerivedQuery` (AC-16); `model_construct` source-scan ban inside this story (AC-17, not deferred to S1-11's pre-commit); module-purity invariant on `model.py` + `queries.py` (AC-18); `__all__` exact-set test (AC-19); parametrized parse-error coverage across all three `safe_yaml` markers (AC-20); `confidence_floor` parametrized over all three `AdapterConfidence` variants (AC-21 — closes the previous Trusted-only gap); audit-log emission (AC-22, replacing the Refactor narrative claim); chokepoint-by-AST source-scan to defend against the monkeypatch-spy's import-fragility (AC-23); empty-collection / duplicate-entries explicit acceptance decisions (AC-24); `TCCMLoadError` markers-only structural test (AC-25).

**Coverage verdict:** COVERAGE-HARDEN (17 findings). **Test-quality verdict:** TESTS-HARDEN (8 block-tier wrong implementations slipped past draft TDD). **Consistency verdict:** CONSISTENCY-HARDEN (3 block-tier resolved by the synthesizer; one informational note on the ADR-0030 ↔ phase-arch primitive-name disagreement — *not in S1-04's authority to reconcile*; phase-arch `§"Data model"` line 721 is the immediate source of truth and this story implements it). **Design-patterns verdict:** DESIGN-HARDEN (11 observations; sound shape, missing pins).

**Notes-for-implementer extensions** (below the AC list) document: deliberate non-newtyping of `pkg` / `module` / `symbol` (Phase 3 owns ID semantics — S1-03 precedent); deliberate intentionality of the Union-extension friction (ADR-0030 amendment is the gate); `LoaderReason: Literal[...]` typed alias for the three reason prefixes; `TCCMLoader` no `__init__` discipline; composition-over-inheritance non-extraction of a shared loader base; `ProbeId` precondition routing through S1-05; reference-TCCM path correction (`docs/phases/02-context-gather-layers-b-g/_reference-tccm/`); production-ADR-0030 filename correction (`0030-graph-aware-context-queries.md`).

No `NEEDS RESEARCH` findings — every gap was answerable from arch + ADR-0007 + ADR-0029 + ADR-0030 + the S1-01 / S1-03 validation precedents + repo state (verified by Bash/Grep).

Full audit log: [`_validation/S1-04-tccm-model-loader.md`](_validation/S1-04-tccm-model-loader.md).

## Context

Task-Class Context Manifests (TCCMs, production ADR-0029) declare what evidence a task class needs: required probes, required skills, derived queries (the five ADR-0030 primitives), and a confidence floor. Phase 2 ships the schema and a loader; Phase 8 ships the Bundle Builder that consumes them. The Phase-2 consumer is `docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml` (S2-03), which exercises every field and is the proof the schema is shaped right before any plugin ships in Phase 3.

Additionally, this story is the architecturally-named home for the **`Result[T, E]` sum type** at `src/codegenie/result.py` — S2-01 (`Depends on: S1-04`) and S2-02 (`ConventionsCatalogLoader`) both reuse it. Phase 1 ships exception-raising parsers (no `Result`); Phase 2 introduces `Result` for loaders that need to return *partial* answers (e.g., S2-01's `LoadOutcome { skills, per_file_errors }`). The `Result` type is a frozen Pydantic discriminated union (`Ok[T] | Err[E]`) following the same family discipline as `IndexFreshness` (S1-01) and `AdapterConfidence` (S1-03).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #8 — TCCMLoader` — public interface, internal structure, `safe_yaml` chokepoint route.
  - `../phase-arch-design.md §"Data model"` (lines `# ---------- [contract] codegenie/tccm/model.py ----------` and `# ---------- [contract] codegenie/tccm/queries.py ----------`) — exact field set and the five `DerivedQuery` primitives.
  - `../phase-arch-design.md §"Design patterns applied"` row 7 — TCCM under `docs/_reference-tccm/`, not `plugins/`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0007-no-plugin-loader-in-phase-2.md` — 02-ADR-0007 — Phase 2 ships the TCCM schema; Phase 3 ships the loader's first real consumer (a plugin's `plugin.yaml` → TCCM).
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0029-task-class-context-manifests.md` — production ADR-0029 — the manifest's purpose.
  - `../../../production/adrs/0030-graph-aware-context-queries.md` — production ADR-0030 — graph-aware derived queries. **Note:** ADR-0030 names five primitives `dep_graph.consumers`, `import_graph.reverse_lookup`, `import_graph.transitive_callers`, `scip.refs`, `test_inventory.tests_exercising`. The phase-arch (`phase-arch-design.md §"Data model"` line 721) deliberately translates these to `ConsumersOf | ProducersOf | ReverseLookup | RefsTo | TestsExercising` — replacing `transitive_callers` with `ProducersOf` (dep-graph upstream lookup) for Phase 2. **S1-04 implements the phase-arch literal set; reconciling phase-arch ↔ ADR-0030 is out of scope here and recorded as an open architectural note**. No `Unknown` variant; ADR-amend on a sixth.
- **Source design:**
  - `../final-design.md §"Synthesis ledger" — TCCMLoader schema only, no Bundle Builder` — the deliberate Phase-2 scope.
- **Existing code:**
  - `src/codegenie/parsers/safe_yaml.py` — Phase 1 chokepoint; the loader routes through `safe_yaml.load`. Size + depth caps already enforced. **Signature is `load(path, *, max_bytes, max_depth=64)` — `max_bytes` is required keyword-only; every Phase 1 caller (S1-07, S3-01, S3-02) passes a module-scope `Final[int]` constant.**
  - `src/codegenie/errors.py` — Phase 0/1 marker convention. Every subclass has **no `__init__`, no class attributes, no `__str__`** (see module docstring). Reason strings are positional `args[0]` with stable prefixes (e.g., `MalformedYAMLError(f"{path}: {kind}: {detail}")`). `TCCMLoadError` is a new marker subclass following this convention.
  - `src/codegenie/adapters/confidence.py` (S1-03) — `AdapterConfidence = Trusted | Degraded | Unavailable` (Pydantic discriminated union); type of `TCCM.confidence_floor`.
  - `src/codegenie/types/identifiers.py` (S1-05) — `TaskClassId`, `SkillId`, `IndexName` newtypes used by `TCCM` fields. **Per S1-05 hard precondition: `ProbeId = NewType("ProbeId", str)` is added to `types/identifiers.py` (Phase 0 did *not* ship `ProbeId`; S1-04 surfaces this gap and routes the fix through S1-05).**
  - `src/codegenie/indices/freshness.py` (S1-01) — prior Pydantic discriminated-union family precedent; sibling-family discipline (discriminator-string pins, JSON-shape pins, `model_construct` source-scan, module-purity tests) is carried forward here verbatim.
- **New code shipped by this story:**
  - `src/codegenie/result.py` — `Result[T, E] = Ok[T] | Err[E]` frozen Pydantic discriminated union. **First architecturally-named consumer is S1-04 itself (`TCCMLoader.load`); S2-01, S2-02 reuse.** See AC-0 below.
- **External docs (only if directly relevant):**
  - https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions — discriminated-union shape for `DerivedQuery`.

## Goal

Implement `src/codegenie/result.py` (`Result[T, E] = Ok[T] | Err[E]` Pydantic discriminated union) and `src/codegenie/tccm/{__init__.py,model.py,queries.py,loader.py}` — `TCCM` Pydantic `frozen=True, extra="forbid"` model, `DerivedQuery` as a five-variant Pydantic discriminated union (no `Unknown`), and `TCCMLoader.load(path) -> Result[TCCM, TCCMLoadError]` routing every YAML read through Phase 1's `codegenie.parsers.safe_yaml.load` chokepoint with an explicitly-pinned `max_bytes` cap.

## Acceptance criteria

### Result[T, E] sum type (new package — `src/codegenie/result.py`)

- [ ] **AC-0a.** `src/codegenie/result.py` ships `Ok[T]` and `Err[E]` Pydantic models (`frozen=True, extra="forbid"`, generic over `T` and `E` respectively) with `kind: Literal["ok"]` / `Literal["err"]` discriminators. `Result[T, E] = Annotated[Union[Ok[T], Err[E]], Field(discriminator="kind")]`. Helper methods on `Ok` / `Err`: `is_ok() -> bool`, `is_err() -> bool`, `unwrap() -> T` (raises `RuntimeError` on `Err`), `unwrap_err() -> E` (raises `RuntimeError` on `Ok`). **No** `map`, `and_then`, `or_else` monadic helpers — Rule 2; add only when a third real consumer needs them.
- [ ] **AC-0b.** `src/codegenie/result.py` exports `__all__ = ["Result", "Ok", "Err"]` exactly. A test asserts `set(codegenie.result.__all__) == {"Result", "Ok", "Err"}`.
- [ ] **AC-0c.** `Ok`, `Err` are immutable: `Ok(value=1).value = 2` raises `ValidationError` (or `pydantic.errors.FrozenInstanceError`); same for `Err`. Parametrized test.
- [ ] **AC-0d.** Round-trip identity: `Ok(value=42)`, `Err(error="boom")` (string-typed for type-system test), and a nested case `Ok(value=Ok(value=1))` all `model_dump_json` → `model_validate_json` round-trip with the right concrete class and value. (Exception-typed `E` is the production case for `TCCMLoadError` — verified separately in AC-4; AC-0d uses `str`-typed `E` for the type-system test.)
- [ ] **AC-0e.** `codegenie.result` imports only `__future__`, `typing`, `pydantic`. AST source-scan test rejects any other top-level import. Pure-typing module per arch §"Design patterns applied".

### `TCCM`, `DerivedQuery`, `TCCMLoader`

- [ ] **AC-1.** `src/codegenie/tccm/__init__.py` exports exactly `TCCM`, `TCCMLoader`, `TCCMLoadError`, `DerivedQuery`, `ConsumersOf`, `ProducersOf`, `ReverseLookup`, `RefsTo`, `TestsExercising` via `__all__` (nine names, no more, no less). Test `test_tccm_all_is_exactly_the_public_surface` asserts `set(codegenie.tccm.__all__) == {<the nine names>}` and `set(codegenie.tccm.__dict__) >= set(codegenie.tccm.__all__)`.
- [ ] **AC-2.** `TCCM` model fields (Pydantic, `frozen=True, extra="forbid"`):
  - `schema_version: Literal["1"]`
  - `task_class: TaskClassId`
  - `required_probes: list[ProbeId]` — **`ProbeId` is imported from `codegenie.types.identifiers` where S1-05 declares it.** Phase 0/1 did **not** ship `ProbeId` (verified via `grep -rn "ProbeId" src/codegenie/` returning zero hits at story-write time); S1-04 routes the addition through S1-05 (S1-05's deliverable expands to include `ProbeId`). If a Phase 0/1 hot-fix already lands `ProbeId` elsewhere before S1-04 starts, re-import from there and **do not** redeclare (Rule 11).
  - `required_skills: list[SkillId]`
  - `derived_queries: list[DerivedQuery]`
  - `confidence_floor: AdapterConfidence`
- [ ] **AC-3.** `DerivedQuery = Annotated[Union[ConsumersOf, ProducersOf, ReverseLookup, RefsTo, TestsExercising], Field(discriminator="compute")]`. Each variant is Pydantic `frozen=True, extra="forbid"` with a `compute` discriminator declared as `Literal["<exact-string>"]` and a single payload field appropriate to the primitive:
  - `ConsumersOf(compute=Literal["consumers_of"], pkg: str)`
  - `ProducersOf(compute=Literal["producers_of"], pkg: str)`
  - `ReverseLookup(compute=Literal["reverse_lookup"], module: str)`
  - `RefsTo(compute=Literal["refs_to"], symbol: str)`
  - `TestsExercising(compute=Literal["tests_exercising"], symbol: str)`

  Field-name set comes from `phase-arch-design.md §"Data model"` line 721 (the architect's translation of ADR-0030; see References for the open reconciliation note).
- [ ] **AC-4.** `TCCMLoader.load(path: Path) -> Result[TCCM, TCCMLoadError]` returns:
  - `Ok(value=tccm)` for a well-formed YAML.
  - `Err(error=TCCMLoadError("schema: <detail>"))` for a Pydantic `ValidationError` that is **not** an unknown-discriminator error.
  - `Err(error=TCCMLoadError("unknown_query_primitive: <detail>"))` for an unrecognized `compute:` value on any `DerivedQuery`. The check happens via Pydantic's discriminator failure path; the loader translates the validation-error code into the `unknown_query_primitive` prefix per the translation table documented in the loader docstring.
  - `Err(error=TCCMLoadError("parse: <detail>"))` if `safe_yaml.load` raises `MalformedYAMLError` / `SizeCapExceeded` / `DepthCapExceeded` (Phase 1 markers).

  **Reasons are positional `args[0]` prefixes** (`"parse: "`, `"schema: "`, `"unknown_query_primitive: "`) per the Phase 0/1 markers-only convention — `TCCMLoadError` has **no `__init__`, no `reason` attribute, no class state**. Consumers parse the prefix from `err.args[0]`; do not invent a structured `.reason` attribute.
- [ ] **AC-5.** Every file read goes through `codegenie.parsers.safe_yaml.load(path, max_bytes=_TCCM_MAX_BYTES)` (Phase 1 chokepoint). The loader declares `_TCCM_MAX_BYTES: Final[int] = 64 * 1024` at module scope (TCCMs are documented "< 10 KB" in arch §8; 6× headroom). The loader does **not** call `yaml.safe_load`, `yaml.load`, `Path.read_text`, `open(path)`, or `safe_yaml.load_all`.
- [ ] **AC-6.** Round-trip identity over **all five** `DerivedQuery` variants: parametrized `pytest.mark.parametrize` test asserts `TypeAdapter(DerivedQuery).validate_json(TypeAdapter(DerivedQuery).dump_json(q)) == q` and `type(decoded) is type(q)` for `q ∈ {ConsumersOf(pkg=...), ProducersOf(pkg=...), ReverseLookup(module=...), RefsTo(symbol=...), TestsExercising(symbol=...)}`.
- [ ] **AC-7.** A well-formed in-memory TCCM round-trips: `TCCM.model_validate(TCCM(...).model_dump()) == TCCM(...)`. (Variant-set coverage for `confidence_floor` is AC-21.)
- [ ] **AC-8.** Unknown `compute:` value (e.g., `compute: "implementations_of"`) produces `Err(error=TCCMLoadError("unknown_query_primitive: <detail>"))`. Test asserts `err.args[0].startswith("unknown_query_primitive:")` exactly — **prefix match, not substring** (closes the `"schema"` ↔ `"unknown_query_primitive"` substring-tautology that an `in err.args[0]` check would allow).
- [ ] **AC-9.** `TCCMLoader.load` returns `Result[TCCM, TCCMLoadError]` — the type shipped by AC-0a in this same story at `src/codegenie/result.py`. The tuple-fallback alternative the draft had is **withdrawn**: S2-01 / S2-02 declare `Depends on: S1-04` precisely because S1-04 is the architectural home for `Result[T, E]`.
- [ ] **AC-10.** The TDD plan's red tests exist (covering all of AC-0 through AC-25), were committed before any production code, and are green at green-stage exit.
- [ ] **AC-11.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/result/ tests/unit/tccm/ tests/property/test_tccm_roundtrip.py` all pass on the touched files. Property-based test (Hypothesis) covers AC-6 over the Cartesian product of variants × random ASCII payloads.

### Sibling-family symmetric discipline (S1-01 / S1-03 carry-forward)

- [ ] **AC-12.** **Discriminator-string literal pin.** Each `DerivedQuery` variant's `compute` literal is exactly the ADR-0030 string. Test `test_compute_discriminator_strings_are_exactly_pinned` asserts `ConsumersOf().compute == "consumers_of"` and the four siblings. A frozenset-equality test asserts `{cls.model_fields["compute"].default for cls in (ConsumersOf, ProducersOf, ReverseLookup, RefsTo, TestsExercising)} == {"consumers_of", "producers_of", "reverse_lookup", "refs_to", "tests_exercising"}`. Closes the symmetric-swap mutation (`ConsumersOf.compute = "producers_of"` + `ProducersOf.compute = "consumers_of"`) that AC-6 round-trip alone would not catch.
- [ ] **AC-13.** **JSON-shape pin.** For each `DerivedQuery` variant, `TypeAdapter(DerivedQuery).dump_python(<variant>)` equals an exact dict. Parametrized:
  - `ConsumersOf(pkg="x").model_dump() == {"compute": "consumers_of", "pkg": "x"}`
  - `ProducersOf(pkg="x").model_dump() == {"compute": "producers_of", "pkg": "x"}`
  - `ReverseLookup(module="x").model_dump() == {"compute": "reverse_lookup", "module": "x"}`
  - `RefsTo(symbol="x").model_dump() == {"compute": "refs_to", "symbol": "x"}`
  - `TestsExercising(symbol="x").model_dump() == {"compute": "tests_exercising", "symbol": "x"}`

  Closes the `compute → tag` symmetric-rename mutation (S1-01 F5, S1-03 F6).
- [ ] **AC-14.** **Runtime immutability.** Every `DerivedQuery` variant *and* `TCCM` raise on attribute assignment. Parametrized `test_tccm_and_query_instances_are_immutable`: `with pytest.raises((ValidationError, FrozenInstanceError)): instance.<field> = <new>`. Closes the "drop `frozen=True`" mutation.
- [ ] **AC-15.** **`extra="forbid"` per variant rejects foreign payloads.** Parametrized matrix: each variant rejects every *other* variant's payload field. E.g., `ConsumersOf(pkg="x", module="y")` raises; `ReverseLookup(module="x", pkg="y")` raises; `RefsTo(symbol="x", pkg="y")` raises. Also: `TCCM.model_validate({...valid..., "notes": "x"})` raises (closes the "drop extra=forbid on TCCM" mutation that AC-2 alone doesn't catch).
- [ ] **AC-16.** **Exhaustive `match` over `DerivedQuery`.** Test defines a tiny `_describe(q: DerivedQuery) -> str` that `match`es all five and ends with `case _: assert_never(q)`. `mypy --strict --warn-unreachable` on the test module catches drop-a-variant; `_describe` exercises every variant once. Closes "tag-and-dispatch without tagged union" (arch §"Anti-patterns avoided" row 7).
- [ ] **AC-17.** **`model_construct` source-scan ban (in-story enforcement).** Test `test_tccm_modules_have_no_model_construct` AST-scans `src/codegenie/result.py` and `src/codegenie/tccm/**/*.py` for any `Call(func=Attribute(attr="model_construct"))` node and `pytest.fail`s if found. Mirrors S1-03 AC-16 / S1-01 mut-10. This is in-story enforcement — S1-11's pre-commit hook ratifies the same ban repo-wide, but the in-story test prevents a temporal-coupling regression if S1-04 lands before S1-11.
- [ ] **AC-18.** **Module-purity invariant for `model.py` + `queries.py`.** Test `test_tccm_pure_modules_have_no_io_imports`: AST import-scan of `src/codegenie/tccm/model.py` and `src/codegenie/tccm/queries.py` allows only `__future__`, `typing`, `pydantic`, `codegenie.adapters`, `codegenie.types.identifiers`. Forbids `pathlib`, `logging`, `structlog`, `yaml`, `os`, `codegenie.parsers`, `codegenie.exec`. `loader.py` is exempt (it is the impure module). Mirrors S1-03 AC-15.
- [ ] **AC-19.** **`__all__` exact-set test (extended to `result.py`).** `test_result_all_is_exactly_the_public_surface` + `test_tccm_all_is_exactly_the_public_surface` (the latter listed in AC-1). Mirrors S1-03 F9.
- [ ] **AC-20.** **Parse-error coverage parametrized over all three `safe_yaml` markers.** Test `test_load_parse_errors_routed` parametrizes over `(monkeypatched_exception, expected_prefix)` ∈ `{(MalformedYAMLError, "parse:"), (SizeCapExceeded, "parse:"), (DepthCapExceeded, "parse:")}`. Closes the "loader misses `DepthCapExceeded` in except tuple" mutation that the draft's single `MalformedYAMLError` test would not catch.
- [ ] **AC-21.** **`confidence_floor` accepts every `AdapterConfidence` variant.** Parametrized `test_confidence_floor_accepts_all_variants` over three YAML bodies — Trusted (`kind: trusted`), Degraded (`kind: degraded`, `reason: …`), Unavailable (`kind: unavailable`, `reason: …`) — and asserts each round-trips with the right concrete class. Closes the previous Trusted-only / two-of-three gap.
- [ ] **AC-22.** **Audit-log emission on every `load()` exit.** Each `load(path)` call emits exactly one structured event — `tccm.load.ok` (path, `derived_queries_count`) on `Ok`, or `tccm.load.err` (path, `reason`) on `Err`. The `reason` is the first colon-delimited token of `err.args[0]` (`"parse"`, `"schema"`, or `"unknown_query_primitive"`); **no path content beyond `str(path)`, no YAML body, no validation-error detail-string is logged**. Test uses `structlog.testing.capture_logs` (S2-01 precedent); asserts event names + field set.
- [ ] **AC-23.** **Chokepoint source-scan (defense against monkeypatch fragility).** Test `test_loader_module_does_not_bypass_safe_yaml`: AST-scans `src/codegenie/tccm/loader.py` and rejects `Import("yaml")`, `ImportFrom(module="yaml")`, `Attribute(attr="read_text")` on `Path`, `Call(func=Name(id="open"))` with a path argument, and `ImportFrom(module="codegenie.parsers.safe_yaml", names=[..., "load_all", ...])`. The monkeypatch-spy `test_load_routes_through_safe_yaml` is preserved as a complementary positive test, but the AST scan is the durable enforcement: a future refactor that does `from codegenie.parsers.safe_yaml import load as _yload` and shadows the spy is caught at import-AST.
- [ ] **AC-24.** **Empty-collection / duplicate-entries decisions.** Three explicit acceptance decisions, one test each, named:
  - `test_tccm_accepts_empty_derived_queries`: `derived_queries: []` is a valid TCCM (a task class may declare zero derived queries; Phase 8 Bundle Builder handles).
  - `test_tccm_accepts_empty_required_probes_and_skills`: `required_probes: []` and `required_skills: []` are each accepted.
  - `test_tccm_accepts_duplicate_required_probes`: `required_probes: ["a", "a"]` is accepted at the schema layer; deduplication is a Phase 8 Bundle Builder concern (recorded as a Note-for-implementer + arch reference).

  These are *deliberate* acceptance decisions — failing loud would be the wrong choice because the Bundle Builder is the authority on derivation. Fail-loud (Rule 12) is preserved at the *consumer* boundary, not the schema.
- [ ] **AC-25.** **`TCCMLoadError` is a bare marker.** Test `test_tccm_load_error_is_bare_marker`: `TCCMLoadError.__init__ is Exception.__init__` (or, equivalently, `TCCMLoadError.__dict__.keys() <= {"__module__", "__qualname__", "__doc__"}`). Closes the "structured `__init__(reason=...)`" mutation.

## Implementation outline

1. **`src/codegenie/result.py`** — `Ok[T]`, `Err[E]`, `Result = Annotated[Union[Ok, Err], Field(discriminator="kind")]`. Pure typing module (`__future__`, `typing`, `pydantic` only). Methods: `is_ok`, `is_err`, `unwrap`, `unwrap_err`. No monadic helpers (Rule 2).
2. `src/codegenie/types/identifiers.py` (S1-05) — confirm `ProbeId = NewType("ProbeId", str)` is declared there (S1-04's hard precondition on S1-05; if S1-05 lands after, S1-04 surfaces a precondition violation, not a workaround).
3. `src/codegenie/tccm/queries.py` — five `DerivedQuery` variant classes + the `Annotated[Union, Field(discriminator="compute")]` alias. Field names per phase-arch `§"Data model"` line 721.
4. `src/codegenie/tccm/model.py` — `TCCM` model importing `AdapterConfidence` from `codegenie.adapters`, `ProbeId` / `TaskClassId` / `SkillId` from `codegenie.types.identifiers`.
5. `src/codegenie/tccm/loader.py` — `TCCMLoader.load(path)`. Module constants: `_TCCM_MAX_BYTES: Final[int] = 64 * 1024`, `LoaderReason: TypeAlias = Literal["parse", "schema", "unknown_query_primitive"]`. Reads via `safe_yaml.load(path, max_bytes=_TCCM_MAX_BYTES)`. On exception: route `(MalformedYAMLError, SizeCapExceeded, DepthCapExceeded)` → `Err(TCCMLoadError(f"parse: {detail}"))`; on `ValidationError`, run a small pure helper `_classify(ve: ValidationError) -> LoaderReason` that inspects `e["type"] ∈ {"union_tag_invalid", "literal_error"}` AND `e["loc"][-1] == "compute"` for `unknown_query_primitive`, else `schema`. Translation table is documented in the loader docstring as a stable Pydantic-version-cross-cut contract.
6. `src/codegenie/tccm/__init__.py` — re-export the nine names exactly.
7. `src/codegenie/errors.py` — append `TCCMLoadError` as a bare marker subclass of `CodegenieError` (no `__init__`, no class attrs, docstring names the three reason prefixes); extend `__all__`.
8. **Audit emission.** Loader's `load()` exit edges call `structlog.get_logger(__name__).info("tccm.load.ok", path=str(path), derived_queries_count=len(tccm.derived_queries))` or `.warning("tccm.load.err", path=str(path), reason=<prefix>)`. Field allowlist enforced inline.
9. Red tests → impl → refactor.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Two test packages: `tests/unit/result/` (AC-0a–0e) and `tests/unit/tccm/` (AC-1 through AC-25). Plus `tests/property/test_tccm_roundtrip.py` (AC-11 Hypothesis property).

Below is the **representative** Red sketch — the full hardened set covers every AC; entries are illustrative.

```python
# tests/unit/tccm/test_loader.py
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import assert_never

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.adapters import Degraded, Trusted, Unavailable
from codegenie.errors import (
    DepthCapExceeded,
    MalformedYAMLError,
    SizeCapExceeded,
    TCCMLoadError,
)
from codegenie.result import Err, Ok, Result
from codegenie.tccm import (
    ConsumersOf,
    DerivedQuery,
    ProducersOf,
    RefsTo,
    ReverseLookup,
    TCCM,
    TCCMLoader,
    TestsExercising,
)
from codegenie.types.identifiers import ProbeId, SkillId, TaskClassId


VALID_TCCM_YAML = textwrap.dedent(
    """
    schema_version: "1"
    task_class: "index-health-self-check"
    required_probes: ["index_health", "scip_index"]
    required_skills: ["scip.maintenance"]
    derived_queries:
      - compute: "consumers_of"
        pkg: "@org/payments"
      - compute: "producers_of"
        pkg: "@org/payments"
      - compute: "reverse_lookup"
        module: "src/payments/processor.ts"
      - compute: "refs_to"
        symbol: "PaymentProcessor.charge"
      - compute: "tests_exercising"
        symbol: "PaymentProcessor.charge"
    confidence_floor:
      kind: "trusted"
    """
)


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "tccm.yaml"
    p.write_text(body)
    return p


# AC-4, AC-5 — happy path through safe_yaml chokepoint
def test_load_happy_path(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID_TCCM_YAML)
    result = TCCMLoader().load(path)
    assert result.is_ok(), repr(result)
    tccm = result.unwrap()
    assert tccm.schema_version == "1"
    assert tccm.task_class == TaskClassId("index-health-self-check")
    assert SkillId("scip.maintenance") in tccm.required_skills
    assert ProbeId("index_health") in tccm.required_probes
    assert len(tccm.derived_queries) == 5
    assert {type(q) for q in tccm.derived_queries} == {
        ConsumersOf, ProducersOf, ReverseLookup, RefsTo, TestsExercising,
    }


# AC-8 — unknown compute: → exact "unknown_query_primitive:" prefix
def test_load_unknown_compute_prefix_pin(tmp_path: Path) -> None:
    bad = VALID_TCCM_YAML.replace('compute: "consumers_of"', 'compute: "implementations_of"')
    result = TCCMLoader().load(_write(tmp_path, bad))
    assert result.is_err()
    err = result.unwrap_err()
    assert err.args[0].startswith("unknown_query_primitive:")  # prefix pin, not substring


# AC-4 — schema violation: positional prefix pin
def test_load_schema_violation_prefix_pin(tmp_path: Path) -> None:
    bad = 'schema_version: "1"\n'  # missing every other required field
    result = TCCMLoader().load(_write(tmp_path, bad))
    assert result.is_err()
    assert result.unwrap_err().args[0].startswith("schema:")


# AC-20 — parse-error parametrized over all three safe_yaml markers
@pytest.mark.parametrize(
    "exc_cls",
    [MalformedYAMLError, SizeCapExceeded, DepthCapExceeded],
    ids=["malformed", "size_cap", "depth_cap"],
)
def test_load_parse_errors_routed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exc_cls: type[Exception]
) -> None:
    from codegenie.parsers import safe_yaml as sy

    def boom(*a: object, **kw: object) -> object:
        raise exc_cls("synthetic")
    monkeypatch.setattr(sy, "load", boom)
    path = _write(tmp_path, VALID_TCCM_YAML)
    result = TCCMLoader().load(path)
    assert result.is_err()
    assert result.unwrap_err().args[0].startswith("parse:")


# AC-5 — chokepoint: monkeypatch positive arm
def test_load_routes_through_safe_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from codegenie.parsers import safe_yaml as sy

    seen: list[tuple[Path, int]] = []
    original = sy.load
    def spy(path: Path, *, max_bytes: int, max_depth: int = 64):
        seen.append((path, max_bytes))
        return original(path, max_bytes=max_bytes, max_depth=max_depth)

    monkeypatch.setattr(sy, "load", spy)
    path = _write(tmp_path, VALID_TCCM_YAML)
    TCCMLoader().load(path)
    assert len(seen) == 1
    assert seen[0][0] == path
    assert seen[0][1] >= 10_240  # at least the documented "< 10 KB" floor


# AC-23 — chokepoint AST source-scan (durable against import-shadowing)
def test_loader_module_does_not_bypass_safe_yaml() -> None:
    import ast
    import codegenie.tccm.loader as loader_mod

    tree = ast.parse(Path(loader_mod.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "yaml", "loader must not import yaml directly"
        if isinstance(node, ast.ImportFrom):
            assert node.module != "yaml", "loader must not import from yaml directly"
            if node.module == "codegenie.parsers.safe_yaml":
                names = {alias.name for alias in node.names}
                assert "load_all" not in names, "loader must use load, not load_all"
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "read_text":
                pytest.fail("loader must not call Path.read_text")


# AC-6 — round-trip identity per DerivedQuery variant
@pytest.mark.parametrize("q", [
    ConsumersOf(pkg="@org/p"),
    ProducersOf(pkg="@org/p"),
    ReverseLookup(module="src/x.ts"),
    RefsTo(symbol="Foo.bar"),
    TestsExercising(symbol="Foo.bar"),
])
def test_derived_query_roundtrip(q: DerivedQuery) -> None:
    adapter = TypeAdapter(DerivedQuery)
    decoded = adapter.validate_json(adapter.dump_json(q))
    assert decoded == q
    assert type(decoded) is type(q)


# AC-12 — discriminator-string literal pin
def test_compute_discriminator_strings_are_exactly_pinned() -> None:
    expected = {
        ConsumersOf: "consumers_of",
        ProducersOf: "producers_of",
        ReverseLookup: "reverse_lookup",
        RefsTo: "refs_to",
        TestsExercising: "tests_exercising",
    }
    for cls, lit in expected.items():
        default = cls.model_fields["compute"].default
        assert default == lit, f"{cls.__name__}.compute = {default!r}, expected {lit!r}"


# AC-13 — JSON-shape pin (closes the `compute → tag` rename mutation)
@pytest.mark.parametrize("variant, expected", [
    (ConsumersOf(pkg="x"), {"compute": "consumers_of", "pkg": "x"}),
    (ProducersOf(pkg="x"), {"compute": "producers_of", "pkg": "x"}),
    (ReverseLookup(module="x"), {"compute": "reverse_lookup", "module": "x"}),
    (RefsTo(symbol="x"), {"compute": "refs_to", "symbol": "x"}),
    (TestsExercising(symbol="x"), {"compute": "tests_exercising", "symbol": "x"}),
])
def test_derived_query_json_shape_pinned(variant: DerivedQuery, expected: dict[str, str]) -> None:
    assert variant.model_dump() == expected


# AC-14 — runtime immutability
@pytest.mark.parametrize("instance, field", [
    (ConsumersOf(pkg="x"), "pkg"),
    (ProducersOf(pkg="x"), "pkg"),
    (ReverseLookup(module="x"), "module"),
    (RefsTo(symbol="x"), "symbol"),
    (TestsExercising(symbol="x"), "symbol"),
])
def test_derived_query_variants_are_immutable(instance: DerivedQuery, field: str) -> None:
    with pytest.raises(ValidationError):
        setattr(instance, field, "new")


# AC-15 — per-variant extra=forbid rejects foreign payload fields
def test_consumers_of_rejects_module_field() -> None:
    with pytest.raises(ValidationError):
        ConsumersOf(pkg="x", module="y")  # type: ignore[call-arg]

def test_reverse_lookup_rejects_pkg_field() -> None:
    with pytest.raises(ValidationError):
        ReverseLookup(module="x", pkg="y")  # type: ignore[call-arg]

def test_tccm_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        TCCM.model_validate({
            "schema_version": "1",
            "task_class": "x",
            "required_probes": [],
            "required_skills": [],
            "derived_queries": [],
            "confidence_floor": {"kind": "trusted"},
            "notes": "bonus",
        })


# AC-16 — exhaustive match + assert_never (mypy --strict --warn-unreachable also enforces)
def _describe(q: DerivedQuery) -> str:
    match q:
        case ConsumersOf(pkg=p): return f"consumers:{p}"
        case ProducersOf(pkg=p): return f"producers:{p}"
        case ReverseLookup(module=m): return f"reverse:{m}"
        case RefsTo(symbol=s): return f"refs:{s}"
        case TestsExercising(symbol=s): return f"tests:{s}"
        case _: assert_never(q)

def test_match_is_exhaustive_over_derived_query() -> None:
    descriptions = [
        _describe(ConsumersOf(pkg="x")),
        _describe(ProducersOf(pkg="x")),
        _describe(ReverseLookup(module="x")),
        _describe(RefsTo(symbol="x")),
        _describe(TestsExercising(symbol="x")),
    ]
    assert len(set(descriptions)) == 5


# AC-21 — confidence_floor variants (parametrized over all three)
@pytest.mark.parametrize("floor_yaml, expected_cls", [
    ("confidence_floor:\n      kind: \"trusted\"", Trusted),
    ("confidence_floor:\n      kind: \"degraded\"\n      reason: \"index_stale\"", Degraded),
    ("confidence_floor:\n      kind: \"unavailable\"\n      reason: \"tool_missing\"", Unavailable),
])
def test_confidence_floor_accepts_all_variants(
    tmp_path: Path, floor_yaml: str, expected_cls: type
) -> None:
    body = VALID_TCCM_YAML.replace('confidence_floor:\n      kind: "trusted"', floor_yaml)
    result = TCCMLoader().load(_write(tmp_path, body))
    assert result.is_ok()
    assert isinstance(result.unwrap().confidence_floor, expected_cls)


# AC-22 — audit log emission
def test_loader_emits_audit_log_on_ok(tmp_path: Path) -> None:
    from structlog.testing import capture_logs
    path = _write(tmp_path, VALID_TCCM_YAML)
    with capture_logs() as caplog:
        TCCMLoader().load(path)
    events = [e for e in caplog if e["event"] in ("tccm.load.ok", "tccm.load.err")]
    assert len(events) == 1
    assert events[0]["event"] == "tccm.load.ok"
    assert events[0]["derived_queries_count"] == 5

def test_loader_emits_audit_log_on_err(tmp_path: Path) -> None:
    from structlog.testing import capture_logs
    bad = VALID_TCCM_YAML.replace('compute: "consumers_of"', 'compute: "implementations_of"')
    path = _write(tmp_path, bad)
    with capture_logs() as caplog:
        TCCMLoader().load(path)
    err_events = [e for e in caplog if e["event"] == "tccm.load.err"]
    assert len(err_events) == 1
    assert err_events[0]["reason"] == "unknown_query_primitive"


# AC-17 — model_construct AST scan
def test_tccm_modules_have_no_model_construct() -> None:
    import ast
    import codegenie.result as r
    import codegenie.tccm.loader as l
    import codegenie.tccm.model as m
    import codegenie.tccm.queries as q

    for mod in (r, l, m, q):
        tree = ast.parse(Path(mod.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "model_construct":
                pytest.fail(f"{mod.__name__} uses model_construct (forbidden)")


# AC-18 — module purity for queries.py + model.py
def test_tccm_pure_modules_have_no_io_imports() -> None:
    import ast
    import codegenie.tccm.model as m
    import codegenie.tccm.queries as q

    allowed_prefixes = ("__future__", "typing", "pydantic", "codegenie.adapters", "codegenie.types")
    for mod in (m, q):
        tree = ast.parse(Path(mod.__file__).read_text())
        for node in ast.walk(tree):
            target = None
            if isinstance(node, ast.Import):
                target = node.names[0].name
            elif isinstance(node, ast.ImportFrom):
                target = node.module
            if target is None:
                continue
            assert any(target == p or target.startswith(p + ".") for p in allowed_prefixes), \
                f"{mod.__name__} imports {target!r} — forbidden in pure modules"


# AC-25 — TCCMLoadError markers-only
def test_tccm_load_error_is_bare_marker() -> None:
    from codegenie.errors import CodegenieError
    assert TCCMLoadError.__init__ is Exception.__init__
    assert issubclass(TCCMLoadError, CodegenieError)


# AC-24 — empty-collection / duplicate decisions
def test_tccm_accepts_empty_derived_queries() -> None:
    t = TCCM(
        schema_version="1",
        task_class=TaskClassId("x"),
        required_probes=[],
        required_skills=[],
        derived_queries=[],
        confidence_floor=Trusted(),
    )
    assert t.derived_queries == []

def test_tccm_accepts_duplicate_required_probes() -> None:
    t = TCCM(
        schema_version="1",
        task_class=TaskClassId("x"),
        required_probes=[ProbeId("a"), ProbeId("a")],
        required_skills=[],
        derived_queries=[],
        confidence_floor=Trusted(),
    )
    assert t.required_probes == [ProbeId("a"), ProbeId("a")]
```

```python
# tests/unit/result/test_result.py — AC-0a..AC-0e
from __future__ import annotations
import pytest
from pydantic import ValidationError
from codegenie.result import Err, Ok


def test_result_all_is_exactly_the_public_surface() -> None:
    import codegenie.result as r
    assert set(r.__all__) == {"Result", "Ok", "Err"}


def test_ok_unwrap_returns_value() -> None:
    assert Ok(value=42).unwrap() == 42

def test_err_unwrap_err_returns_error() -> None:
    assert Err(error="boom").unwrap_err() == "boom"

def test_ok_unwrap_err_raises() -> None:
    with pytest.raises(RuntimeError):
        Ok(value=42).unwrap_err()

def test_err_unwrap_raises() -> None:
    with pytest.raises(RuntimeError):
        Err(error="boom").unwrap()

def test_ok_is_immutable() -> None:
    o = Ok(value=1)
    with pytest.raises(ValidationError):
        o.value = 2  # type: ignore[misc]
```

```python
# tests/property/test_tccm_roundtrip.py — AC-11 Hypothesis property
from __future__ import annotations
from hypothesis import given, strategies as st
from pydantic import TypeAdapter
from codegenie.tccm import (
    ConsumersOf, DerivedQuery, ProducersOf, RefsTo, ReverseLookup, TestsExercising,
)

_payload_text = st.text(min_size=1, max_size=32, alphabet=st.characters(min_codepoint=33, max_codepoint=126))

_variant_strategy = st.one_of(
    st.builds(ConsumersOf, pkg=_payload_text),
    st.builds(ProducersOf, pkg=_payload_text),
    st.builds(ReverseLookup, module=_payload_text),
    st.builds(RefsTo, symbol=_payload_text),
    st.builds(TestsExercising, symbol=_payload_text),
)

@given(_variant_strategy)
def test_derived_query_roundtrip_property(q: DerivedQuery) -> None:
    adapter = TypeAdapter(DerivedQuery)
    decoded = adapter.validate_json(adapter.dump_json(q))
    assert decoded == q
    assert type(decoded) is type(q)
```

Run — confirm `ImportError` (result module + tccm package both missing). Commit.

### Green — make it pass

`result.py` skeleton:

```python
# src/codegenie/result.py
from __future__ import annotations
from typing import Annotated, Generic, Literal, TypeVar, Union
from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Result", "Ok", "Err"]

T = TypeVar("T")
E = TypeVar("E")

class Ok(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
    kind: Literal["ok"] = "ok"
    value: T

    def is_ok(self) -> bool: return True
    def is_err(self) -> bool: return False
    def unwrap(self) -> T: return self.value
    def unwrap_err(self) -> "object":
        raise RuntimeError("Ok has no error")

class Err(BaseModel, Generic[E]):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
    kind: Literal["err"] = "err"
    error: E

    def is_ok(self) -> bool: return False
    def is_err(self) -> bool: return True
    def unwrap(self) -> "object":
        raise RuntimeError(f"Err: {self.error!r}")
    def unwrap_err(self) -> E: return self.error

Result = Annotated[Union[Ok[T], Err[E]], Field(discriminator="kind")]
```

`queries.py` skeleton:

```python
from __future__ import annotations
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field

class ConsumersOf(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    compute: Literal["consumers_of"] = "consumers_of"
    pkg: str

class ProducersOf(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    compute: Literal["producers_of"] = "producers_of"
    pkg: str

class ReverseLookup(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    compute: Literal["reverse_lookup"] = "reverse_lookup"
    module: str

class RefsTo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    compute: Literal["refs_to"] = "refs_to"
    symbol: str

class TestsExercising(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    compute: Literal["tests_exercising"] = "tests_exercising"
    symbol: str

DerivedQuery = Annotated[
    Union[ConsumersOf, ProducersOf, ReverseLookup, RefsTo, TestsExercising],
    Field(discriminator="compute"),
]
```

`model.py` skeleton:

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict
from codegenie.adapters import AdapterConfidence
from codegenie.tccm.queries import DerivedQuery
from codegenie.types.identifiers import ProbeId, SkillId, TaskClassId

class TCCM(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["1"]
    task_class: TaskClassId
    required_probes: list[ProbeId]
    required_skills: list[SkillId]
    derived_queries: list[DerivedQuery]
    confidence_floor: AdapterConfidence
```

`loader.py` skeleton — `_classify` pure helper + `load` impure shell:

```python
# src/codegenie/tccm/loader.py — sketch
from __future__ import annotations
from pathlib import Path
from typing import Final, Literal, TypeAlias

import structlog
from pydantic import ValidationError

from codegenie.errors import (
    DepthCapExceeded, MalformedYAMLError, SizeCapExceeded, TCCMLoadError,
)
from codegenie.parsers import safe_yaml
from codegenie.result import Err, Ok, Result
from codegenie.tccm.model import TCCM

_TCCM_MAX_BYTES: Final[int] = 64 * 1024  # phase-arch §8: TCCMs are "< 10 KB"; 6× headroom
_logger = structlog.get_logger(__name__)

LoaderReason: TypeAlias = Literal["parse", "schema", "unknown_query_primitive"]


def _classify(ve: ValidationError) -> LoaderReason:
    """Translation table — public contract; pin this docstring against Pydantic minor upgrades."""
    for e in ve.errors():
        if e.get("type") in {"union_tag_invalid", "literal_error"}:
            loc = e.get("loc", ())
            if loc and loc[-1] == "compute":
                return "unknown_query_primitive"
    return "schema"


class TCCMLoader:
    """No __init__ — pure data at construction; first I/O is .load(path)."""

    def load(self, path: Path) -> Result[TCCM, TCCMLoadError]:
        try:
            data = safe_yaml.load(path, max_bytes=_TCCM_MAX_BYTES)
        except (MalformedYAMLError, SizeCapExceeded, DepthCapExceeded) as exc:
            err = TCCMLoadError(f"parse: {type(exc).__name__}")
            _logger.warning("tccm.load.err", path=str(path), reason="parse")
            return Err(error=err)
        try:
            tccm = TCCM.model_validate(data)
        except ValidationError as ve:
            reason = _classify(ve)
            err = TCCMLoadError(f"{reason}: {ve.errors()[0].get('msg', 'invalid')}")
            _logger.warning("tccm.load.err", path=str(path), reason=reason)
            return Err(error=err)
        _logger.info("tccm.load.ok", path=str(path), derived_queries_count=len(tccm.derived_queries))
        return Ok(value=tccm)
```

Add `TCCMLoadError` to `errors.py` as a marker (no `__init__`, docstring names the loader and the three reason prefixes: `parse`, `schema`, `unknown_query_primitive`).

### Refactor — clean up

- Module docstrings: `loader.py` names the three `reason` prefixes (`parse`, `schema`, `unknown_query_primitive`) as the public contract; future contributors must extend by amending the `_classify` helper + the `LoaderReason` `Literal[...]` alias + the docstring table — not by adding ad-hoc string prefixes.
- `model_construct` source-scan AC (AC-17) enforces in-story; S1-11's pre-commit hook adds repo-wide enforcement later. Do not regress.
- The loader does **not** log YAML body, validation-error detail, or any secret-shaped substring of `path`. The audit-log field allowlist is `{event, path, derived_queries_count, reason}` only (AC-22 verifies).
- Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/result.py src/codegenie/tccm/ tests/unit/result/ tests/unit/tccm/`, `pytest tests/unit/result/ tests/unit/tccm/ tests/property/test_tccm_roundtrip.py -v`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/result.py` | **NEW** — `Result[T, E] = Ok[T] | Err[E]` Pydantic discriminated union; S2-01 / S2-02 reuse. |
| `src/codegenie/tccm/__init__.py` | New package; re-export the surface (nine names exactly). |
| `src/codegenie/tccm/model.py` | `TCCM` Pydantic model. Pure typing (AC-18). |
| `src/codegenie/tccm/queries.py` | Five `DerivedQuery` variants + the `Annotated[Union, Field(discriminator="compute")]` alias. Pure typing (AC-18). |
| `src/codegenie/tccm/loader.py` | `TCCMLoader` over `safe_yaml.load`. The one impure module. Module constants `_TCCM_MAX_BYTES` + `LoaderReason: Literal[...]`. |
| `src/codegenie/errors.py` | Append `TCCMLoadError` bare marker; extend `__all__`. |
| `src/codegenie/types/identifiers.py` (S1-05) | Add `ProbeId = NewType("ProbeId", str)` if S1-05 didn't already. |
| `tests/unit/result/__init__.py` | New test package. |
| `tests/unit/result/test_result.py` | AC-0a..AC-0e. |
| `tests/unit/tccm/__init__.py` | New test package. |
| `tests/unit/tccm/test_loader.py` | Loader behavior: happy, unknown compute, schema, parse-parametrized, chokepoint monkeypatch + AST, confidence-floor parametrized, audit log. |
| `tests/unit/tccm/test_queries.py` | Round-trip identity per variant, discriminator pin, JSON-shape pin, immutability, foreign-payload rejection. |
| `tests/unit/tccm/test_model.py` | `TCCM` round-trip, extra=forbid, empty / duplicate decisions, exhaustive match, model_construct + module-purity AST scans, marker structural test. |
| `tests/property/test_tccm_roundtrip.py` | Hypothesis property over all five variants × random ASCII payloads. |

## Out of scope

- **Reference TCCM at `docs/phases/02-context-gather-layers-b-g/_reference-tccm/tccm.yaml` + integration roundtrip** — handled by S2-03.
- **Bundle Builder / Hierarchical Planner** — Phase 8.
- **Plugin Loader / `plugin.yaml` parser** — Phase 3; this story ships the TCCM schema only.
- **Sixth `DerivedQuery` variant** — explicitly out per production ADR-0030; ADR-amend required if Phase 3 discovers a sixth primitive.
- **`TCCM.required_probes` runtime-checked against the actual probe registry** — Phase 3+ concern.
- **Hashed body / progressive-disclosure for the manifest itself** — manifests are small (< 10 KB); `safe_yaml` caps already enforce.
- **Reconciliation between ADR-0030 named primitives and the phase-arch's five-tuple** — recorded in References as an open architectural note; phase-arch §"Data model" line 721 is the source of truth this story implements.
- **`Result.map` / `and_then` / `or_else` monadic helpers** — not added until a third consumer needs them (Rule 2).

## Notes for the implementer

- **`Result[T, E]` is shipped *by this story* — there is no preexisting Phase 0/1 type.** Verified at story-write time via `grep -rn "class Result|is_ok|unwrap" src/codegenie/` returning zero hits. S2-01 and S2-02 declare `Depends on: S1-04` precisely because S1-04 is the architectural home for `Result`. Implement `src/codegenie/result.py` per AC-0a..AC-0e *first*; the TCCM tests import it.
- **`ProbeId` precondition.** Phase 0/1 did **not** ship `ProbeId` (verified at story-write time). S1-05 owns the identifiers module; S1-04's precondition is that `ProbeId = NewType("ProbeId", str)` lands in `src/codegenie/types/identifiers.py` either before or simultaneously with this story. If the implementer encounters a missing `ProbeId` at green-stage time, the correct fix is to extend `S1-05`'s deliverable to add `ProbeId` — **not** to declare a local `ProbeId = str` alias in `tccm/model.py` (which would silently degrade the newtype to a structural alias and violate Rule 11 / arch §"Anti-patterns avoided" — stringly-typed identifiers).
- **Reasons are `Literal["parse", "schema", "unknown_query_primitive"]`.** Declare a `LoaderReason: TypeAlias = Literal[...]` at module scope in `loader.py` and use it as the return type of `_classify`. At three reasons this is below the rule-of-three threshold for a full `StrEnum` / dispatch table — keep it as a type alias. If a fourth reason ever ships, extract a typed translation table at that point (Rule 2 — three lines is better than premature abstraction).
- **`unknown_query_primitive` translation is brittle.** Pydantic v2 error codes (`union_tag_invalid`, `literal_error`) may shift across minor versions. The translation table in `_classify` is the public contract; the loader docstring pins it. If a Pydantic upgrade breaks AC-8, this is the regression site — **fix the translation, not the test** (Rule 12 — fail loud).
- **`safe_yaml.load` is the *only* file-read path.** Do not import `yaml`, do not call `Path.read_text`, do not use `open()`. The chokepoint is the Phase 1 commitment; AC-5 + AC-23 (monkeypatch + AST source-scan) double-defend it. The chokepoint *required keyword* `max_bytes=` must be passed — `_TCCM_MAX_BYTES: Final[int] = 64 * 1024` is the pinned constant.
- **Markers-only invariant.** `TCCMLoadError` is a bare marker (no `__init__`, no class attributes), exactly like `MalformedYAMLError` / `CatalogLoadError` from Phase 1. Reason strings live as positional `args[0]` *prefixes* (`"parse: …"`, `"schema: …"`, `"unknown_query_primitive: …"`); the loader emits stable prefixes. Consumers parse the prefix; **do not** invent a structured `.reason` attribute or kwarg-style construction. AC-25 verifies the structural invariant.
- **`schema_version: Literal["1"]` is the upgrade door.** A future TCCM v2 would add `schema_version: Literal["1", "2"]` and the loader would dispatch internally. Do not invent `TCCMSchemaV1` / `TCCMSchemaV2` classes preemptively (Rule 2 — Simplicity First).
- **Five variants, no `Unknown`.** Resist `class UnknownQuery(BaseModel): compute: str` as a "graceful degradation" fallback. The whole point of the discriminator is that unknown `compute` values are loader errors, not data-model variants (production ADR-0030 §Consequences).
- **Union-extension friction is intentional.** Adding a sixth `DerivedQuery` variant requires editing `queries.py` to extend the `Annotated[Union[…]]` alias. CLAUDE.md "Extension by addition" applies repo-wide, but ADR-0030 deliberately makes the variant Union edit load-bearing visible — a sixth primitive needs an ADR amendment, not a code-only PR. Do **not** redesign the union as a string-keyed registry to make addition "easier."
- **Deliberate non-newtyping of `pkg` / `module` / `symbol`.** S1-03 made the same call for `Occurrence.{file, line, col}`: Phase 2 does not yet know whether `pkg` means `PackageId` (canonical name) vs `PackageName` (display). Phase 3 plugin authors own the ID semantics. Do not introduce `PkgName = NewType("PkgName", str)` in this story. If a future phase needs the distinction, an ADR-amendment to ADR-0030 ratifies the newtypes and a sibling refactor lifts them.
- **`TCCMLoader` has no `__init__`.** Pure-data-at-construction discipline (arch §"Anti-patterns avoided" — side effects in constructors). Do not add I/O, do not cache file handles, do not add a logger attribute. First I/O is `.load(path)`. Mirrors `SkillsLoader` arch §9.
- **Composition over inheritance — no shared loader base class.** `TCCMLoader`, `SkillsLoader`, `ConventionsCatalogLoader` are three loaders with three I/O shapes. ~60 LOC shared is **not** worth a speculative `BaseYamlLoader` (arch §"Design patterns applied" row 7 — SRP + Rule of Three). Each loader stands alone.
- **Phase-arch ↔ ADR-0030 reconciliation is *not* in scope.** ADR-0030 names `dep_graph.consumers`, `import_graph.reverse_lookup`, `import_graph.transitive_callers`, `scip.refs`, `test_inventory.tests_exercising`. Phase-arch line 721 ratifies `ConsumersOf | ProducersOf | ReverseLookup | RefsTo | TestsExercising` — substituting `ProducersOf` for `transitive_callers`. This story implements the phase-arch literal. Surface the reconciliation question to the next phase-architecture review; do not unilaterally amend either document.
- **Audit log allowlist.** Loader emits only `{event, path, derived_queries_count, reason}`. **No YAML body, no validation-error detail string, no secret-shaped substring of `path`** leaks. AC-22 verifies. If the operator's logs need richer diagnostics, the loader docstring documents the audit-line contract — diagnostics belong in the operator-side log scrubber, not in the loader emission.
