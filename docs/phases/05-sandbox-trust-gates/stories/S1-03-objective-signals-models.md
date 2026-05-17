# Story S1-03 — `ObjectiveSignals` + six sub-models + `SignalProvenance`

**Step:** Step 1 — Scaffold packages, contracts, and CI fences
**Status:** Ready (HARDENED 2026-05-17)
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0014, ADR-0008, ADR-0015, ADR-0003

## Validation notes (2026-05-17 — phase-story-validator)

Four-critic pass. Verdict: **HARDENED**. Headline edits, with severity tags:

- **(coverage / patterns — block) Walker descent through `Optional[X]` was the most-critical hole.** Every `ObjectiveSignals` field is `Submodel | None = None`. A walker that ignores `Union[X, None]` makes the whole introspection test vacuous — `_iter_nested_field_names(ObjectiveSignals, set())` returns only the six container field names; none contain a forbidden substring; CI passes; ADR-0014 is silently dead. The original TDD plan had **no permanent positive test** for walker depth (the Notes paragraph proposed a "throwaway, then delete" synthetic — exactly inverting Rule 9). The hardened plan ships permanent in-test-file synthetic holders for Optional descent, dict-value descent, case-insensitivity, and recursion termination.
- **(coverage — block) `extra="forbid", frozen=True` was enforced only behaviourally on `BuildSignal`.** Five sibling sub-models + `SignalProvenance` + `ObjectiveSignals` could have shipped `extra="ignore"` or `frozen=False` and every draft test would still pass. Sibling S1-02 was hardened with a direct `model_config` introspection AC; mirrored here. Parametrized across all eight models.
- **(coverage / consistency / patterns — block) `SignalProvenance.signal_kind` open-registry posture was unpinned.** ADR-0003 widens kinds to an **open string** (not a closed Literal). A naive executor reading the six current kinds would naturally type `Literal["build","install","tests","trace","policy","cve_delta"]` and break Phase 7's `baseimage`/`shell_presence` extension. New ACs assert `get_type_hints(SignalProvenance)["signal_kind"]` is `SignalKind` (NewType over `str`, NOT a `Literal`) and that `SignalProvenance(signal_kind="baseimage", ...)` constructs without complaint.
- **(patterns — harden) Promoted `SignalKind = NewType("SignalKind", str)` to `src/codegenie/types/identifiers.py` now.** CLAUDE.md ("newtype when crossing ≥ 2 modules") + S1-02's just-hardened `RunId`/`SandboxSpecHash` precedent + rule-of-three already-cleared: `signal_kind` flows through `SignalProvenance` (S1-03) → `@register_signal_kind` registry (S1-05) → `gates/contract.py` (S1-04, where arch line 721 currently sketches `SignalKind = str`) → `StrictAndGate` (S4-05) → `AttemptSummary.failing_signals` / `RetryPolicy.retryable_failures` / `GateOutcome.failing_signals` (S1-04). ≥ 6 module boundaries. Landing the NewType in S1-03 means S1-04 picks it up cleanly; landing it later forces post-hoc rewrites.
- **(patterns — harden) Walker extracted to `sandbox/signals/_introspection.py` as a real abstraction with a public `iter_nested_field_names` function.** The original Notes call it "a small public helper" but spell it `_iter_nested_field_names` (underscored). Both ADR-0014's local introspection test (this story) and S1-07's `tests/schema/` fence will import it; Phase 7 (`baseimage`/`shell_presence`) and Phase 11 (evidence-bundle field screening) will reuse it. That makes it the trust anchor for the substring-screening invariant — kernel-tier, not "small helper." Module-private file (`_introspection.py` leading underscore — module-purity invariant), public function name (`iter_nested_field_names` no leading underscore — cross-module reuse legit).
- **(test-quality — block) The "remove before committing" instruction in the Notes was inverted.** A synthetic positive case (throwaway model with `confidence: str`, walker yields it) is *the* mutation test for the walker itself — delete the descent logic and this test fails. The hardened TDD plan keeps the synthetic **permanent**, in the test file (not production module), exercising Optional descent (M-10), dict-V descent (M-9), case-insensitivity (M-11), and recursion termination (M-16).
- **(test-quality — harden) Parametrized frozen / extra-forbid / field-set tests across all eight public models.** The draft only exercised `BuildSignal` for frozen + extra-forbid and only `ObjectiveSignals` for field-set exactness. Now every sub-model, `SignalProvenance`, and `ObjectiveSignals` are parametrized over the same uniform-coverage tests.
- **(test-quality — harden) `bool` ⊂ `int` and `float → int` coercion gaps closed.** `details={"k": True}` and `details={"k": 3.0}` both have non-obvious Pydantic 2 behavior. The hardened model uses `model_config = ConfigDict(extra="forbid", frozen=True, strict=True)` + a `@field_validator("details", mode="after")` that runtime-checks `type(v) in {str, int, bool}` AND disambiguates `bool`-vs-`int` via `type(v) is bool` / `type(v) is int`. New AC asserts `type(s.details["b"]) is bool` (not coerced).
- **(coverage / patterns — harden) `at: datetime` timezone-aware enforced via `AwareDatetime`.** Pydantic 2's `AwareDatetime` rejects naive `datetime`. Phase 5 evidence bundles + `RetryLedger` BLAKE3 chain ordering + Phase 13 telemetry break on naive timestamps across operator timezones. New AC asserts naive datetime is rejected; `datetime.now(timezone.utc)` succeeds.
- **(coverage / patterns — harden) Annotation pinning via `get_type_hints`.** Five annotation-level ACs catch wrong-type implementations that runtime tests miss: `details` is exactly `dict[str, str | int | bool]` (not `dict[str, Any]`); `signal_kind` is `SignalKind` (not `Literal` or bare `str`); `at` is `AwareDatetime`; the six `ObjectiveSignals` fields are typed as the correct optional sub-models; `inputs_blake3` is `str`.
- **(consistency — harden) Coverage floor wording bug fixed (same as S1-02 #1).** Original AC said "Branch ≥ 95%" — README's `95/90` is "line ≥ 95% AND branch ≥ 90%." Rewritten.
- **(consistency — harden) Standard codebase scaffolding promoted to ACs:** `from __future__ import annotations`, module docstring naming ADR-0014/0008/0015/0003 and the source story, `__all__` set-equality (exactly eight public names; `_SignalBase` and walker-helper excluded).
- **(patterns — harden) Module-purity invariant test (`tests/sandbox/test_signals_purity.py`).** Mirrors S1-02's `test_contract_purity.py`. AST scan asserts `models.py` and `_introspection.py` import only `{pydantic, typing, datetime, __future__, collections.abc, codegenie.types.identifiers}`. Importing from `sandbox.contract`, `gates.*`, or `trust.*` is a test failure.
- **(coverage — harden) Hash + equality + JSON round-trip ACs added.** Frozen Pydantic models support `__hash__`; the trust pipeline plausibly stores signals in sets / dict keys; two `BuildSignal`s with identical fields must equality-and-hash. JSON round-trip is critical for Phase 6 lift-unchanged + Phase 9 cache-key seam.
- **(test-quality — harden) Hypothesis property test for `details` non-primitive rejection** (T-N in critic report). The 5-value parametrize list is not exhaustive; `@given(st.dictionaries(...))` covers the open set.
- **(patterns — note-only) Module-level `Final` catalogs for known `details` keys** documented in Notes for the implementer (not promoted to AC). Pattern: `_TEST_SIGNAL_DETAIL_KEYS: Final[frozenset[str]] = frozenset({"failing_tests", "first_failure", "delta_test_count", "timed_out"})` etc. — informational discoverability for collector authors (S4-02..S4-06); extension-by-addition friendly.

No Stage-3 research was needed — every gap was answerable from arch §Data model + §Agentic best practices + §Open Q9, the four honored ADRs (-0014, -0008, -0015, -0003), CLAUDE.md load-bearing commitments (Extension by addition, Newtype identifiers, Functional core / imperative shell, Rule 9, Rule 11), and codebase precedents (`src/codegenie/result.py`, `src/codegenie/types/identifiers.py`, `src/codegenie/probes/language_detection.py` Final-catalog pattern, S1-02's HARDENED report). No story restructuring; goal, scope, dependencies (S1-01), out-of-scope discipline (collectors → Step 4, registry → S1-05, fence → S1-07, asymmetric `delta_test_count` logic → S4-02), and ADR mapping (-0014/-0008/-0015/-0003) are unchanged. See `_validation/S1-03-objective-signals-models.md` for the full audit log.

## Context

`ObjectiveSignals` is the strict-AND input — the model that every Phase 5 trust decision derives from. ADR-0014 mandates `extra="forbid", frozen=True` plus a static-introspection CI test asserting no field name reachable from `ObjectiveSignals` contains `confidence`, `llm`, `self_reported`, or `model_says`. This story ships the model family with that invariant baked in by construction; the fence test that polices it permanently lands in S1-07.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Data model — sandbox/signals/models.py` — full pseudo-code for `SignalProvenance`, `_SignalBase`, six sub-models, `ObjectiveSignals`.
  - `../phase-arch-design.md §Component design — SandboxSpec / SandboxRun / ObjectiveSignals` — `details: dict[str, str|int|bool]`; no float, no nested dict, no list as value type.
  - `../phase-arch-design.md §Agentic best practices — Confidence handling for ADR-0008` — the explicit rename `coverage_confidence` → `coverage_evidence_strength` (Open Q9).
  - `../phase-arch-design.md §Edge cases 6, 7` — `delta_test_count` semantics consumed by `TestSignal.details`.
  - `../phase-arch-design.md §CI gates` — `tests/schema/test_objective_signals_static.py` recursively walks every field reachable from `ObjectiveSignals` (this story produces the surface that walk traverses **plus** the walker itself).
- **Phase ADRs (rules this story honors):**
  - `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — ADR-0014 — `extra="forbid", frozen=True`; no banned substrings; `details` value type strictly `str | int | bool`.
  - `../ADRs/0008-llm-judge-persona-deferral.md` — ADR-0008 — no LLM judgment fields anywhere in this graph.
  - `../ADRs/0015-test-inventory-delta-asymmetric-policy.md` — ADR-0015 — `TestSignal.details["delta_test_count"]` is an `int`, always emitted, even when zero (collector-side invariant; model permits omission).
  - `../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md` — ADR-0003 — `signal_kind` is an **open string registry** (NOT a closed Literal); adding a new optional field on `ObjectiveSignals` requires an ADR amendment but is *additively* extensible.
- **Production ADRs:**
  - `../../../production/adrs/0008-objective-signal-trust-score.md` — strict-AND lineage; this is what ADR-0014 enforces.
- **Source design:**
  - `../final-design.md §Component-2 — ObjectiveSignals` — load-bearing commitments §2.2.
- **Codebase precedents to mirror:**
  - `src/codegenie/result.py` — frozen + `extra="forbid"` + module-purity invariant + module docstring discipline.
  - `src/codegenie/types/identifiers.py` — `NewType` pattern; canonical kernel-tier home for domain identifiers.
  - `src/codegenie/probes/language_detection.py` — `_WARNING_IDS: Final[frozenset[str]]` module-level catalog pattern.
  - `docs/phases/05-sandbox-trust-gates/stories/_validation/S1-02-sandbox-contract-protocol-models.md` — sibling validation; design-pattern and consistency findings transfer directly (coverage floor wording, newtype seam, module purity).

## Goal

Ship `src/codegenie/sandbox/signals/models.py` with `SignalProvenance`, an internal `_SignalBase`, six concrete frozen `extra="forbid", strict=True` sub-models (`BuildSignal`, `InstallSignal`, `TestSignal`, `TraceSignal`, `PolicySignal`, `CveDeltaSignal`), and the `ObjectiveSignals` container — with no field name (transitively) containing a forbidden substring. Ship the recursive introspection walker as a public function `iter_nested_field_names` in a sibling module `sandbox/signals/_introspection.py`. Promote `SignalKind = NewType("SignalKind", str)` to `src/codegenie/types/identifiers.py`.

## Acceptance criteria

### A. Import surface and module hygiene

- [ ] **AC-1** `from codegenie.sandbox.signals.models import ObjectiveSignals, BuildSignal, InstallSignal, TestSignal, TraceSignal, PolicySignal, CveDeltaSignal, SignalProvenance` succeeds. `from codegenie.sandbox.signals._introspection import iter_nested_field_names` succeeds. `from codegenie.types.identifiers import SignalKind` succeeds.
- [ ] **AC-1a** `models.py`'s top imports include `from __future__ import annotations` (asserted by AST scan over its source) and a module docstring whose first non-blank paragraph references `ADR-0014`, `ADR-0008`, `ADR-0015`, `ADR-0003` and the source story `S1-03`.
- [ ] **AC-1b** `set(codegenie.sandbox.signals.models.__all__) == {"SignalProvenance", "BuildSignal", "InstallSignal", "TestSignal", "TraceSignal", "PolicySignal", "CveDeltaSignal", "ObjectiveSignals"}` (byte-exact set equality). `"_SignalBase"`, `"iter_nested_field_names"`, and `"_iter_nested_field_names"` are NOT in this `__all__`.
- [ ] **AC-1c** `set(codegenie.sandbox.signals._introspection.__all__) == {"iter_nested_field_names"}`. Module name carries the leading underscore (module-private); the function does not (cross-module reuse legitimate).
- [ ] **AC-1d** `from codegenie.sandbox.signals import models; assert "_SignalBase" not in dir(models) or "_SignalBase" not in getattr(codegenie.sandbox.signals, "__all__", ())` — `_SignalBase` is not surfaced at the package level.

### B. `model_config` discipline (parametrized across ALL eight public models)

- [ ] **AC-2** For every `Cls ∈ {SignalProvenance, BuildSignal, InstallSignal, TestSignal, TraceSignal, PolicySignal, CveDeltaSignal, ObjectiveSignals}`: `Cls.model_config.get("extra") == "forbid"` AND `Cls.model_config.get("frozen") is True`. Test parametrized over all eight.
- [ ] **AC-2a** Each of the six concrete sub-models declares `model_config` in its own class body (`Cls.__dict__.get("model_config") is not None`) — i.e., does NOT rely on Pydantic v2 inheritance from `_SignalBase` (which is unreliable across patch releases). Parametrized.
- [ ] **AC-2b** Constructing any of the eight models with an unknown field raises `pydantic.ValidationError`. Parametrized over the eight.
- [ ] **AC-2c** Attempting to mutate any field on a constructed instance of the eight models raises `pydantic.ValidationError` (frozen). Parametrized.

### C. Field sets and annotation pinning

- [ ] **AC-3** Each of the six sub-models has `set(Cls.model_fields.keys()) == {"passed", "details", "provenance", "at"}` (exact set equality). Parametrized.
- [ ] **AC-3a** `set(ObjectiveSignals.model_fields.keys()) == {"build", "install", "tests", "trace", "policy", "cve_delta"}` (byte-exact; catches `cve` typo / early Phase-7 `baseimage` smuggle).
- [ ] **AC-3b** `set(SignalProvenance.model_fields.keys()) == {"signal_kind", "collector_module", "collector_version", "inputs_blake3"}` (byte-exact).
- [ ] **AC-3c** `typing.get_type_hints(SignalProvenance)` returns `{"signal_kind": SignalKind, "collector_module": str, "collector_version": str, "inputs_blake3": str}` exactly. No `bytes`, no `Path`, no `Literal[...]` on any field.
- [ ] **AC-3d** For each of the six sub-models, `typing.get_type_hints(Cls)["details"] == dict[str, str | int | bool]` byte-exact (rules out `dict[str, Any]`, `dict[str, str | int | float | bool]`, etc.).
- [ ] **AC-3e** For each of the six sub-models, `typing.get_type_hints(Cls)["at"]` resolves to `pydantic.AwareDatetime` (or the `Annotated[datetime, AfterValidator(...)]` equivalent if `AwareDatetime` is not used).
- [ ] **AC-3f** `typing.get_type_hints(ObjectiveSignals)` returns `{"build": BuildSignal | None, "install": InstallSignal | None, "tests": TestSignal | None, "trace": TraceSignal | None, "policy": PolicySignal | None, "cve_delta": CveDeltaSignal | None}` — each is exactly `Optional[<correct sub-model>]`.

### D. `signal_kind` open-registry posture (ADR-0003)

- [ ] **AC-4** `SignalKind = NewType("SignalKind", str)` is declared in `src/codegenie/types/identifiers.py` (NOT in `sandbox/signals/models.py`). `SignalKind.__supertype__ is str`. `SignalKind` appears in `codegenie.types.identifiers.__all__`.
- [ ] **AC-4a** `typing.get_origin(typing.get_type_hints(SignalProvenance)["signal_kind"]) is None` AND the hint is exactly `SignalKind` — NOT `Literal[...]`, NOT bare `str`. Negative-typecheck fixture under `tests/typecheck/` asserts `mypy --strict` rejects passing a `RunId`-typed value where a `SignalKind` is expected (or, if no mypy fixture infra exists yet, document as a Notes-only follow-up).
- [ ] **AC-4b** `SignalProvenance(signal_kind=SignalKind("baseimage"), collector_module="x", collector_version="0", inputs_blake3="0"*32)` succeeds — proves the registry is open (Phase 7's `baseimage` kind constructs without complaint). And the same with `SignalKind("shell_presence")`.
- [ ] **AC-4c** AST source-scan under `src/codegenie/sandbox/` and `src/codegenie/gates/` forbids any `NewType("SignalKind", ...)` redefinition outside `src/codegenie/types/identifiers.py`. (Mirrors `types/identifiers.py` docstring's "single declaration site" discipline.)

### E. `details` value-type policy (ADR-0014 strict primitives)

- [ ] **AC-5** Each sub-model rejects `details` containing any of the following value types at construction (`ValidationError`): `float`, `list`, nested `dict`, `None`, `bytes`, `Decimal`, `complex`. Parametrized.
- [ ] **AC-5a** `details={"k": True}` succeeds AND `type(s.details["k"]) is bool` (NOT coerced to `int`). Likewise `details={"k": 1}` succeeds AND `type(s.details["k"]) is int` (NOT coerced to `bool`). The `bool` ⊂ `int` Python ambiguity is disambiguated by runtime type identity.
- [ ] **AC-5b** `details={"k": 3.0}` rejected (the integer-valued float that Pydantic non-strict mode silently coerces). Strict mode + a `@field_validator("details", mode="after")` enforce.
- [ ] **AC-5c** `details={"k": "v", "i": 7, "b": True}` round-trips equal: `s.details == {"k": "v", "i": 7, "b": True}` and all three value types are preserved.
- [ ] **AC-5d** Hypothesis property: `@given(st.dictionaries(st.text(min_size=1, max_size=8), st.one_of(st.floats(allow_nan=True), st.lists(st.integers(), max_size=3), st.binary(max_size=4), st.dictionaries(st.text(max_size=4), st.integers(), max_size=2), st.none())))` — for every such dict `d`, `_build(details=d)` raises `ValidationError` (or `d == {}` passes vacuously, which the property allows).
- [ ] **AC-5e** Empty `details={}` is accepted on every sub-model.

### F. Timezone-aware `at`

- [ ] **AC-6** For each sub-model: `Cls(passed=True, details={}, provenance=_prov(), at=datetime(2026, 5, 17, 12, 0, 0))` (naive — no `tzinfo`) raises `pydantic.ValidationError`. Parametrized.
- [ ] **AC-6a** For each sub-model: `Cls(passed=True, details={}, provenance=_prov(), at=datetime.now(timezone.utc))` succeeds. Parametrized.

### G. `ObjectiveSignals` shape

- [ ] **AC-7** `ObjectiveSignals()` (no args) constructs successfully with all six fields `None`.
- [ ] **AC-7a** `ObjectiveSignals(build=_build(), install=_install(), tests=_tests(), trace=_trace(), policy=_policy(), cve_delta=_cve())` constructs; each field's type is the populated sub-model.
- [ ] **AC-7b** `ObjectiveSignals(unknown_kind=_build())` raises `ValidationError` (`extra="forbid"`).
- [ ] **AC-7c** `TestSignal` constructed with `details={"delta_test_count": 0}` succeeds; with `details={"delta_test_count": -1}` succeeds; with `details={"delta_test_count": 1}` succeeds. The *gate logic* that flips `passed=False` on negative delta lives in S4-02 / ADR-0015, **not here** — this story enforces only the model can carry the integer. `TestSignal(passed=True, details={})` (no `delta_test_count`) also succeeds; the always-present invariant is the collector's responsibility per ADR-0015 §Consequences.

### H. Introspection walker (ADR-0014 trust anchor)

- [ ] **AC-8** `iter_nested_field_names(ObjectiveSignals)` yields the full set of field names reachable from `ObjectiveSignals` — including names on `_SignalBase`-derived sub-models, `SignalProvenance` fields, and any nested model accessible through `Optional[X]` / `Union[X, Y, None]` / `dict[K, V]`. Walker is **type-driven, not instance-driven**: invoked on `type(ObjectiveSignals())` and on `type(ObjectiveSignals(build=_build()))` yields the SAME set.
- [ ] **AC-8a** No name in `iter_nested_field_names(ObjectiveSignals)` (lowercased) contains any of `{"confidence", "llm", "self_reported", "model_says"}` (the ADR-0014 fence; check is lowercase substring matching for defense-in-depth against camelCase smuggling).
- [ ] **AC-8b** **Walker mutation tests (permanent — kept in `test_objective_signals_introspection.py`, not deleted):** four throwaway models live in the test file. For each, the walker MUST yield the named forbidden field:
  - **W-1 Optional descent:** `class _OptHolder(BaseModel): inner: _Forbidden | None = None` where `_Forbidden(BaseModel): confidence_score: str` — walker yields `"confidence_score"`.
  - **W-2 dict-value descent:** `class _DictHolder(BaseModel): bag: dict[str, _Forbidden]` — walker yields `"confidence_score"`.
  - **W-3 case-insensitivity:** `class _UpperHolder(BaseModel): Confidence: str` (uppercase field name) — walker yields `"Confidence"`; the substring-check normalizes via `.lower()` and matches.
  - **W-4 recursion termination:** `class _Recur(BaseModel): name: str = ""; parent: "_Recur | None" = None` — `list(iter_nested_field_names(_Recur))` returns without hanging or recursing infinitely (the `visited` set must guard).
- [ ] **AC-8c** `iter_nested_field_names` has signature `(annotation: type, visited: set[type] | None = None) -> Iterator[str]`. `visited=None` materializes a fresh `set()` per call.
- [ ] **AC-8d** Walker is pure: same input → same yielded set (deterministic; no hidden state). Verified by calling twice and comparing.

### I. Equality, hash, and JSON round-trip

- [ ] **AC-9** Two `BuildSignal`s constructed with byte-identical field values are `==` AND have equal `hash()`; `{b1, b2}` has length 1.
- [ ] **AC-9a** For each sub-model: `Cls.model_validate_json(c.model_dump_json()) == c` (JSON round-trip identity). Parametrized.
- [ ] **AC-9b** `ObjectiveSignals(build=_build(), tests=_tests()).model_dump_json()` followed by `ObjectiveSignals.model_validate_json(...)` returns an equal object. Datetime serializes as ISO-8601 with timezone offset.

### J. Module purity

- [ ] **AC-10** AST-scan `tests/sandbox/test_signals_purity.py` asserts top-level imports in `src/codegenie/sandbox/signals/models.py` and `src/codegenie/sandbox/signals/_introspection.py` are a subset of `{__future__, typing, datetime, collections.abc, pydantic, codegenie.types.identifiers}`. Forbids importing from `codegenie.sandbox.contract`, `codegenie.gates.*`, `codegenie.trust.*`, or any I/O / logging modules.

### K. Process gates (Definition of done)

- [ ] **AC-11** TDD plan's red tests exist, are committed, and are green.
- [ ] **AC-12** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/sandbox/signals/models.py src/codegenie/sandbox/signals/_introspection.py src/codegenie/types/identifiers.py`, `pytest tests/sandbox/test_signal_models.py tests/sandbox/test_objective_signals_introspection.py tests/sandbox/test_signals_purity.py` all pass.
- [ ] **AC-13** Coverage on `src/codegenie/sandbox/signals/models.py` AND on `src/codegenie/sandbox/signals/_introspection.py`: **line ≥ 95% AND branch ≥ 90%** (95/90 floor from `stories/README.md`).
- [ ] **AC-14** If `tests/schema/test_no_llm_imports_in_sandbox.py` exists at land-time (it lands in S1-07), it remains green. If it does not yet exist, the local sibling at `tests/sandbox/test_signals_purity.py` is the standing surrogate.

## Implementation outline

1. Create `src/codegenie/sandbox/signals/__init__.py` (empty package marker; do NOT re-export internals).
2. Add `SignalKind = NewType("SignalKind", str)` to `src/codegenie/types/identifiers.py`; extend `__all__` alphabetically. Module docstring already documents the "single declaration site" rule — add a one-line note that `SignalKind` is the open-registry kind identifier per ADR-0003.
3. Create `src/codegenie/sandbox/signals/_introspection.py`:
   - `from __future__ import annotations`.
   - Module docstring naming ADR-0014 + the source story S1-03 + the reuse contract (in-story test + S1-07 fence + Phase 7 extension).
   - Imports limited to `__future__`, `typing` (`Iterator`, `get_args`, `get_origin`, `Union`), `pydantic` (`BaseModel`).
   - Public function `iter_nested_field_names(annotation: type, visited: set[type] | None = None) -> Iterator[str]`. Descends into:
     - Pydantic `BaseModel` subclasses (recurses into `model_fields`).
     - `Optional[X]` / `Union[X, None]` / `Union[A, B, ...]` (descends into each non-`None` arg).
     - `dict[K, V]` (descends into K AND V annotations; yields no extra names for primitive K/V).
     - `Literal[...]` (no descent — values are not field names).
     - `Annotated[T, ...]` (unwrap to T).
   - Use `visited: set[type]` to guard against recursive models (forward refs, self-references). Add to `visited` BEFORE recursing.
   - `__all__ = ["iter_nested_field_names"]`.
4. Create `src/codegenie/sandbox/signals/models.py`:
   - `from __future__ import annotations`.
   - Module docstring naming ADR-0014, ADR-0008, ADR-0015, ADR-0003 and the source story S1-03.
   - Imports: `datetime` (`datetime`), `typing` (`Final`, `frozenset` from `collections.abc` is not needed — use `frozenset` builtin), `pydantic` (`AwareDatetime`, `BaseModel`, `ConfigDict`, `Field`, `field_validator`), `codegenie.types.identifiers` (`SignalKind`).
5. Define `SignalProvenance`:
   ```python
   class SignalProvenance(BaseModel):
       model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
       signal_kind: SignalKind
       collector_module: str
       collector_version: str
       inputs_blake3: str
   ```
6. Define `_SignalBase` (internal — leading underscore, NOT in `__all__`):
   ```python
   class _SignalBase(BaseModel):
       model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
       passed: bool
       details: dict[str, str | int | bool]
       provenance: SignalProvenance
       at: AwareDatetime

       @field_validator("details", mode="after")
       @classmethod
       def _validate_detail_value_types(cls, v: dict) -> dict:
           for key, val in v.items():
               # Disambiguate bool vs int (bool is int subclass in Python).
               # Pydantic strict mode + explicit type-identity check.
               if type(val) not in {str, int, bool}:
                   raise ValueError(f"details[{key!r}] has type {type(val).__name__}; only str|int|bool allowed")
           return v
   ```
7. Subclass six sub-models. **Each re-declares `model_config` explicitly** (Pydantic v2 inheritance is unreliable across patch releases):
   ```python
   class BuildSignal(_SignalBase):
       model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
   # repeat for InstallSignal, TestSignal, TraceSignal, PolicySignal, CveDeltaSignal
   ```
   Add a one-line docstring on `TraceSignal` documenting the rename `coverage_confidence` → `coverage_evidence_strength` per ADR-0014 / Open Q9.
8. Define `ObjectiveSignals`:
   ```python
   class ObjectiveSignals(BaseModel):
       model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
       build: BuildSignal | None = None
       install: InstallSignal | None = None
       tests: TestSignal | None = None
       trace: TraceSignal | None = None
       policy: PolicySignal | None = None
       cve_delta: CveDeltaSignal | None = None
   ```
9. (Optional, informational) Add module-level `Final[frozenset[str]]` catalogs of known detail keys per sub-model — see Notes for the implementer. These are documentation for collector authors (S4-02..S4-06); the model does NOT enforce key membership (extension-by-addition stays clean).
10. Declare `__all__` with exactly the eight public names listed in AC-1b. Do NOT export `_SignalBase`, `iter_nested_field_names`, or the Final catalogs.
11. Write the three test files (see TDD plan); verify red; implement; verify green.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file paths: `tests/sandbox/test_signal_models.py`, `tests/sandbox/test_objective_signals_introspection.py`, `tests/sandbox/test_signals_purity.py`.

```python
# tests/sandbox/test_signal_models.py
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from typing import get_type_hints

import pytest
from hypothesis import given, strategies as st
from pydantic import AwareDatetime, ValidationError

from codegenie.sandbox.signals.models import (
    SignalProvenance, BuildSignal, InstallSignal, TestSignal,
    TraceSignal, PolicySignal, CveDeltaSignal, ObjectiveSignals,
)
from codegenie.types.identifiers import SignalKind

SUBMODELS = [BuildSignal, InstallSignal, TestSignal, TraceSignal, PolicySignal, CveDeltaSignal]
ALL_PUBLIC = SUBMODELS + [SignalProvenance, ObjectiveSignals]


def _prov(kind: str = "build") -> SignalProvenance:
    return SignalProvenance(
        signal_kind=SignalKind(kind),
        collector_module="codegenie.sandbox.signals.build",
        collector_version="0.1.0",
        inputs_blake3="0" * 32,
    )

def _build(cls=BuildSignal, **overrides):
    base = dict(passed=True, details={}, provenance=_prov(), at=datetime.now(timezone.utc))
    base.update(overrides)
    return cls(**base)


# -- B. model_config discipline (parametrized over all 8) -----------------

@pytest.mark.parametrize("cls", ALL_PUBLIC)
def test_every_model_is_frozen_and_forbids_extra(cls):
    assert cls.model_config.get("extra") == "forbid"
    assert cls.model_config.get("frozen") is True

@pytest.mark.parametrize("cls", SUBMODELS)
def test_each_submodel_declares_model_config_in_own_class_body(cls):
    # Pydantic v2 inheritance of model_config is unreliable; require explicit declaration.
    assert cls.__dict__.get("model_config") is not None

@pytest.mark.parametrize("cls", ALL_PUBLIC)
def test_every_model_rejects_unknown_field(cls):
    # Build minimal valid kwargs per class, then attempt one extra field.
    if cls is SignalProvenance:
        kw = dict(signal_kind=SignalKind("build"), collector_module="x", collector_version="0", inputs_blake3="0"*32)
    elif cls is ObjectiveSignals:
        kw = {}
    else:
        kw = dict(passed=True, details={}, provenance=_prov(), at=datetime.now(timezone.utc))
    with pytest.raises(ValidationError):
        cls(**kw, ghost_field="boom")

@pytest.mark.parametrize("cls", SUBMODELS)
def test_each_submodel_is_frozen_after_construction(cls):
    s = _build(cls)
    with pytest.raises(ValidationError):
        s.passed = False


# -- C. Field sets and annotation pinning ---------------------------------

@pytest.mark.parametrize("cls", SUBMODELS)
def test_submodel_field_set_is_exact(cls):
    assert set(cls.model_fields.keys()) == {"passed", "details", "provenance", "at"}

def test_objective_signals_field_set_is_exact():
    assert set(ObjectiveSignals.model_fields.keys()) == {
        "build", "install", "tests", "trace", "policy", "cve_delta"
    }

def test_signal_provenance_field_set_is_exact():
    assert set(SignalProvenance.model_fields.keys()) == {
        "signal_kind", "collector_module", "collector_version", "inputs_blake3"
    }

def test_signal_provenance_annotation_types():
    hints = get_type_hints(SignalProvenance)
    assert hints == {
        "signal_kind": SignalKind, "collector_module": str,
        "collector_version": str, "inputs_blake3": str,
    }

@pytest.mark.parametrize("cls", SUBMODELS)
def test_submodel_details_annotation_is_str_int_bool_only(cls):
    hints = get_type_hints(cls)
    assert hints["details"] == dict[str, str | int | bool]

def test_objective_signals_field_annotations_are_correct_optionals():
    hints = get_type_hints(ObjectiveSignals)
    expected = {
        "build": BuildSignal | None, "install": InstallSignal | None,
        "tests": TestSignal | None, "trace": TraceSignal | None,
        "policy": PolicySignal | None, "cve_delta": CveDeltaSignal | None,
    }
    assert hints == expected


# -- D. signal_kind open registry (ADR-0003) ------------------------------

def test_signal_kind_is_newtype_over_str_in_canonical_home():
    assert SignalKind.__supertype__ is str
    import codegenie.types.identifiers as ids
    assert "SignalKind" in ids.__all__

def test_signal_kind_is_not_a_literal_on_provenance():
    from typing import get_origin
    hints = get_type_hints(SignalProvenance)
    assert get_origin(hints["signal_kind"]) is None
    assert hints["signal_kind"] is SignalKind

def test_signal_provenance_accepts_unregistered_kind_for_future_extension():
    # Phase 7 will register "baseimage" / "shell_presence"; the model must already accept.
    SignalProvenance(signal_kind=SignalKind("baseimage"), collector_module="x",
                     collector_version="0", inputs_blake3="0"*32)
    SignalProvenance(signal_kind=SignalKind("shell_presence"), collector_module="x",
                     collector_version="0", inputs_blake3="0"*32)


# -- E. details value-type policy ----------------------------------------

@pytest.mark.parametrize("bad_value", [3.14, 3.0, [1, 2], {"nested": "x"}, None, b"bytes", Decimal("1.0"), 1+2j])
@pytest.mark.parametrize("cls", SUBMODELS)
def test_details_rejects_non_primitive(cls, bad_value):
    with pytest.raises(ValidationError):
        _build(cls, details={"k": bad_value})

@pytest.mark.parametrize("cls", SUBMODELS)
def test_details_accepts_str_int_bool_preserving_types(cls):
    s = _build(cls, details={"s": "v", "i": 7, "b": True})
    assert s.details == {"s": "v", "i": 7, "b": True}
    # Disambiguate bool from int (bool is int subclass in Python).
    assert type(s.details["b"]) is bool
    assert type(s.details["i"]) is int

@pytest.mark.parametrize("cls", SUBMODELS)
def test_details_accepts_empty_dict(cls):
    assert _build(cls, details={}).details == {}

@given(st.dictionaries(
    st.text(min_size=1, max_size=8),
    st.one_of(
        st.floats(allow_nan=True),
        st.lists(st.integers(), max_size=3),
        st.binary(max_size=4),
        st.dictionaries(st.text(max_size=4), st.integers(), max_size=2),
        st.none(),
    ),
    min_size=1, max_size=3,
))
def test_property_details_rejects_arbitrary_non_primitive(d):
    with pytest.raises(ValidationError):
        _build(BuildSignal, details=d)


# -- F. Timezone-aware at -------------------------------------------------

@pytest.mark.parametrize("cls", SUBMODELS)
def test_naive_datetime_rejected(cls):
    naive = datetime(2026, 5, 17, 12, 0, 0)
    with pytest.raises(ValidationError):
        _build(cls, at=naive)

@pytest.mark.parametrize("cls", SUBMODELS)
def test_aware_datetime_accepted(cls):
    aware = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
    _build(cls, at=aware)  # no raise


# -- G. ObjectiveSignals shape -------------------------------------------

def test_objective_signals_default_all_none():
    os = ObjectiveSignals()
    assert os.build is None and os.install is None and os.tests is None
    assert os.trace is None and os.policy is None and os.cve_delta is None

def test_objective_signals_all_populated():
    os = ObjectiveSignals(
        build=_build(BuildSignal), install=_build(InstallSignal),
        tests=_build(TestSignal), trace=_build(TraceSignal),
        policy=_build(PolicySignal), cve_delta=_build(CveDeltaSignal),
    )
    assert isinstance(os.build, BuildSignal) and isinstance(os.cve_delta, CveDeltaSignal)

def test_objective_signals_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        ObjectiveSignals(baseimage=_build())  # not yet a kind; ADR-0003 widens additively

def test_test_signal_carries_delta_test_count_int():
    # Model-side stores the int; gate logic that flips passed=False on neg delta is S4-02.
    s = TestSignal(passed=True, details={"delta_test_count": 0},
                   provenance=_prov("tests"), at=datetime.now(timezone.utc))
    assert s.details["delta_test_count"] == 0
    s_neg = TestSignal(passed=True, details={"delta_test_count": -1},
                       provenance=_prov("tests"), at=datetime.now(timezone.utc))
    assert s_neg.details["delta_test_count"] == -1
    # Always-present invariant is collector-side (ADR-0015); model permits omission.
    TestSignal(passed=True, details={}, provenance=_prov("tests"), at=datetime.now(timezone.utc))


# -- I. Equality / hash / JSON round-trip --------------------------------

def test_equality_and_hash_for_identical_field_values():
    fixed_at = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
    fixed_prov = _prov()
    b1 = BuildSignal(passed=True, details={"k": "v"}, provenance=fixed_prov, at=fixed_at)
    b2 = BuildSignal(passed=True, details={"k": "v"}, provenance=fixed_prov, at=fixed_at)
    assert b1 == b2
    assert hash(b1) == hash(b2)
    assert len({b1, b2}) == 1

@pytest.mark.parametrize("cls", SUBMODELS)
def test_submodel_json_round_trip(cls):
    s = _build(cls, details={"k": "v"})
    assert cls.model_validate_json(s.model_dump_json()) == s

def test_objective_signals_json_round_trip():
    os = ObjectiveSignals(build=_build(BuildSignal), tests=_build(TestSignal))
    assert ObjectiveSignals.model_validate_json(os.model_dump_json()) == os


# -- A. __all__ discipline -----------------------------------------------

def test_models_all_is_exact_public_surface():
    from codegenie.sandbox.signals import models
    assert set(models.__all__) == {
        "SignalProvenance", "BuildSignal", "InstallSignal", "TestSignal",
        "TraceSignal", "PolicySignal", "CveDeltaSignal", "ObjectiveSignals",
    }
    assert "_SignalBase" not in models.__all__
    assert "iter_nested_field_names" not in models.__all__

def test_introspection_all_is_exact_public_surface():
    from codegenie.sandbox.signals import _introspection
    assert set(_introspection.__all__) == {"iter_nested_field_names"}
```

```python
# tests/sandbox/test_objective_signals_introspection.py
"""In-story sibling of tests/schema/test_objective_signals_static.py (S1-07).
Asserts the ADR-0014 invariant at the place where the surface is defined.
PERMANENT synthetic models prove the walker descends through Optional, dict
values, mixed case, and terminates on recursive types — the mutation tests
for the walker itself (Rule 9)."""
from __future__ import annotations

from pydantic import BaseModel

from codegenie.sandbox.signals.models import ObjectiveSignals
from codegenie.sandbox.signals._introspection import iter_nested_field_names

FORBIDDEN = ("confidence", "llm", "self_reported", "model_says")


# -- AC-8a: production surface is clean -----------------------------------

def test_no_field_name_contains_forbidden_substring():
    names = list(iter_nested_field_names(ObjectiveSignals))
    for n in names:
        for bad in FORBIDDEN:
            assert bad not in n.lower(), f"forbidden substring {bad!r} in field {n!r}"


# -- AC-8: walker is type-driven, not instance-driven ---------------------

def test_walker_is_type_driven_not_instance_driven():
    empty = ObjectiveSignals()
    populated = ObjectiveSignals  # type itself
    # Walker takes a type; passing the type produces the same set regardless of populated/empty.
    set_from_empty = set(iter_nested_field_names(type(empty)))
    set_from_type = set(iter_nested_field_names(populated))
    assert set_from_empty == set_from_type


# -- AC-8b: WALKER MUTATION TESTS (PERMANENT — proves descent works) -----

class _ForbiddenInner(BaseModel):
    confidence_score: str = ""

class _OptHolder(BaseModel):
    """W-1: Optional[X] descent — the construct every ObjectiveSignals field uses."""
    inner: _ForbiddenInner | None = None

def test_walker_descends_through_optional():
    names = set(iter_nested_field_names(_OptHolder))
    assert "confidence_score" in names

class _DictHolder(BaseModel):
    """W-2: dict[K, V] value descent."""
    bag: dict[str, _ForbiddenInner] = {}

def test_walker_descends_through_dict_value():
    names = set(iter_nested_field_names(_DictHolder))
    assert "confidence_score" in names

class _UpperHolder(BaseModel):
    """W-3: case-insensitive substring check (defense-in-depth against camelCase)."""
    Confidence: str = ""  # uppercase, would slip past naive `in` check

def test_walker_substring_check_is_case_insensitive():
    names = {n.lower() for n in iter_nested_field_names(_UpperHolder)}
    assert any("confidence" in n for n in names)

class _Recur(BaseModel):
    """W-4: recursion termination via `visited` guard."""
    name: str = ""
    parent: "_Recur | None" = None

_Recur.model_rebuild()

def test_walker_terminates_on_recursive_model():
    # Must not infinite-loop; must yield at least "name" once.
    yielded = list(iter_nested_field_names(_Recur))
    assert "name" in yielded


# -- AC-8d: walker purity -------------------------------------------------

def test_walker_is_pure():
    a = set(iter_nested_field_names(ObjectiveSignals))
    b = set(iter_nested_field_names(ObjectiveSignals))
    assert a == b
```

```python
# tests/sandbox/test_signals_purity.py
"""Module-purity invariant — mirrors S1-02 tests/sandbox/test_contract_purity.py.

src/codegenie/sandbox/signals/models.py and _introspection.py are pure data + a
pure walker. Importing from sandbox.contract / gates.* / trust.* / any I/O or
logger module is a test failure — those packages depend on signals, not the
other way around (collectors consume SandboxRun and produce signals)."""
from __future__ import annotations

import ast
from pathlib import Path

ALLOWED = {
    "__future__", "typing", "datetime", "collections", "collections.abc",
    "pydantic", "codegenie.types.identifiers",
}

def _top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    mods: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name.split(".")[0] if "." not in alias.name else alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
    return mods

def _assert_pure(path: Path) -> None:
    imports = _top_level_imports(path)
    bad = {m for m in imports if not any(m == a or m.startswith(a + ".") for a in ALLOWED)}
    assert bad == set(), f"{path} imports forbidden modules: {bad}"

def test_models_py_is_pure():
    _assert_pure(Path("src/codegenie/sandbox/signals/models.py"))

def test_introspection_py_is_pure():
    _assert_pure(Path("src/codegenie/sandbox/signals/_introspection.py"))
```

Run; confirm `ImportError` on `SignalKind` from `types/identifiers`, on `iter_nested_field_names` from `_introspection`, and on the model symbols; commit; then implement.

### Green — make it pass

Implement per the Implementation outline above. Key points:

- `SignalKind` in `types/identifiers.py` lands FIRST (S1-04 / S1-05 will also reuse it; placing it now means no rewrite later).
- `_introspection.py` lands SECOND (models.py will import nothing from it; introspection.py imports nothing from models.py — they coexist as independent kernels).
- `models.py` lands THIRD. Each sub-model re-declares `model_config` in its own class body (no inheritance shortcut — Pydantic v2 fragility).
- The `field_validator("details", mode="after")` on `_SignalBase` does the `type(v) in {str, int, bool}` runtime check that closes the float-coercion and bool/int ambiguity gaps. With `strict=True` in `model_config`, most coercions are blocked at parse time; the validator is belt-and-suspenders.
- `iter_nested_field_names`'s visited-set guard MUST add the type to `visited` BEFORE recursing into its sub-types — otherwise a self-referential model infinite-loops.

### Refactor — clean up

- Add `__all__` listing exactly the eight public names; alphabetize per `result.py` precedent. Verify `_SignalBase`, `iter_nested_field_names`, and any module-level Final catalogs are NOT in `__all__`.
- Edge case (arch §Edge case 7): `delta_test_count > 0` is informational — this story does NOT enforce that; the sub-model just stores the int. The asymmetric policy lives in `collect_test_signal` (S4-02 / ADR-0015).
- Edge case (arch §Agentic best practices + Open Q9): `TraceSignal.details["coverage_evidence_strength"]` is the renamed field — `TraceSignal.__doc__` documents the rename and cross-references ADR-0014.
- (Optional) Add module-level `Final[frozenset[str]]` catalogs for known detail keys — see Notes for the implementer. Informational only; not enforced; extension-friendly.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Add `SignalKind = NewType("SignalKind", str)` and extend `__all__` (kernel-tier home per the module docstring's "single declaration site" rule) |
| `src/codegenie/sandbox/signals/__init__.py` | New file — empty package marker; do NOT re-export internals |
| `src/codegenie/sandbox/signals/models.py` | New file — `SignalProvenance` + `_SignalBase` + six sub-models + `ObjectiveSignals` with ADR-0014 enforcement by construction |
| `src/codegenie/sandbox/signals/_introspection.py` | New file — public `iter_nested_field_names` walker; the ADR-0014 trust anchor that S1-07's fence and Phase 7's extensions reuse |
| `tests/sandbox/test_signal_models.py` | New test — extra-forbid / frozen / `details` value-type policy / annotation pinning / open-registry / equality / JSON round-trip — parametrized across all 8 public models |
| `tests/sandbox/test_objective_signals_introspection.py` | New test — local mirror of the ADR-0014 fence; runs before S1-07 fence lands; ships **permanent** synthetic models exercising walker descent (Optional / dict-V / case-insensitivity / recursion-termination) |
| `tests/sandbox/test_signals_purity.py` | New test — module-purity AST scan for `models.py` and `_introspection.py`; mirrors S1-02's `test_contract_purity.py` |

## Out of scope

- **The structural CI fence test under `tests/schema/`** — lands in S1-07 (`test_objective_signals_static.py`). This story ships the same logic *inside* `tests/sandbox/` as an in-story assertion plus a permanent walker-mutation suite.
- **Signal collectors (`collect_build_signal`, etc.)** — Step 4 (S4-01..S4-04).
- **`@register_signal_kind` decorator** — S1-05.
- **`StrictAndGate.evaluate`** — S4-05.
- **Asymmetric `delta_test_count < 0` failure logic** — S4-02 + ADR-0015.
- **Always-emit `delta_test_count` even when zero** — collector-side invariant per ADR-0015 §Consequences (S4-02). The model permits `TestSignal.details` without `delta_test_count`.
- **`SignalKind` registry uniqueness** — `SignalKindAlreadyRegistered` raised by the decorator at import is S1-05's concern (per ADR-0003 §Consequences).
- **`inputs_blake3` hex-shape validation** — defers to the collector that computes the digest (S4-02..S4-04). Model carries `str`; collector enforces hex-shape (mirrors S1-02 deferring `sandbox_spec_hash` shape to S3-01's `SandboxSpecBuilder`).
- **Mypy negative-typecheck infra** — if `tests/typecheck/` does not yet exist, AC-4a's mypy fixture portion becomes a Notes-only deferral; the runtime `SignalKind.__supertype__ is str` AC stays in force.

## Notes for the implementer

- Six sub-models all subclass `_SignalBase`. Pydantic v2 does NOT reliably propagate `model_config` to subclasses across all field-resolution paths — set `model_config` explicitly on each. AC-2a parametrizes this.
- `details: dict[str, str | int | bool]` — Pydantic 2 accepts `True` for `int` slots and silently coerces `3.0` to `3` in non-strict mode. Belt-and-suspenders: `strict=True` in `model_config` AND a `@field_validator("details", mode="after")` that runtime-checks `type(v) in {str, int, bool}` (catches `bool` ⊂ `int` and `Decimal`/`Enum`/`complex` smuggling). Write AC-5a / AC-5b tests FIRST, watch them fail or pass on `bool` / `3.0`, then add the validator if needed.
- `iter_nested_field_names` is the **kernel** for ADR-0014's recursive substring screening. Stable signature `(annotation: type, visited: set[type] | None = None) -> Iterator[str]`. Use `typing.get_args` and `typing.get_origin`. Handle `Union`, `Optional`, `Literal`, generic `dict[K, V]`, `Annotated[T, ...]`. **Add to `visited` BEFORE recursing** (mistake here = infinite loop on self-references).
- The walker test ships a **permanent** synthetic-fixture model (`_ForbiddenInner` with `confidence_score`) and four holders (`_OptHolder`, `_DictHolder`, `_UpperHolder`, `_Recur`). DO NOT delete these after green — they are the mutation tests for the walker itself. A walker that returns `[]` would make every CI run pass without them; with them, the walker's descent into `Optional[X]`, `dict[K, V]`, mixed-case names, and recursive types is *positively* verified.
- ADR-0014 is the most-attacked invariant in the phase. If your introspection test passes but you suspect the walker is shallow, debug with `list(iter_nested_field_names(ObjectiveSignals))` and confirm it contains `"passed"`, `"details"`, `"provenance"`, `"signal_kind"`, `"collector_module"`, etc. — i.e., field names from the *sub-models and their nested `SignalProvenance`*, not just the six container field names.
- `SignalKind = NewType("SignalKind", str)` goes in `src/codegenie/types/identifiers.py`, NOT in `sandbox/signals/models.py`. The types module docstring documents the "single declaration site" rule; S1-04's `gates/contract.py` will import `SignalKind` from there (arch line 721's `SignalKind = str` sketch becomes `from codegenie.types.identifiers import SignalKind`). AC-4c forbids redefinition under `src/codegenie/sandbox/` / `src/codegenie/gates/` via AST source-scan.
- `AwareDatetime` is Pydantic 2's built-in for tz-aware datetimes; prefer it over an `Annotated[datetime, AfterValidator(...)]` hand-roll. Lives on `_SignalBase` so all six sub-models inherit the rejection of naive `datetime`. AC-6 parametrizes the check across the six.
- This is one of two modules with the 95/90 coverage floor (per `stories/README.md` §Definition of done). Cover: each sub-model frozen, each sub-model extra-forbid, each forbidden detail value type, the walker on populated / empty `ObjectiveSignals`, the walker on each of the four permanent synthetic holders, the equality / hash / JSON round-trip, the strict-mode + field-validator interaction on `bool`/`int`.
- Do not import anything from `sandbox/contract.py`, `gates/*`, `trust/*`, or any I/O / logger module here. `ObjectiveSignals` lives upstream of any sandbox `SandboxRun`; the dependency runs the other way (collectors consume `SandboxRun` and produce signals). Enforced by `tests/sandbox/test_signals_purity.py` (AC-10).
- **`__all__` discipline (S1-02 precedent):** the package surface must be the eight public model names plus the walker function. `_SignalBase` (private base — leading underscore), `_introspection` (module-private — leading underscore on the *module* name; the *function* `iter_nested_field_names` is public), and any informational Final catalogs must NOT be re-exported via `sandbox/signals/__init__.py`'s `__all__`.
- **Forward seam — module-level Final catalogs for known detail keys (P-5, Notes-only):** consider declaring `_TEST_SIGNAL_DETAIL_KEYS: Final[frozenset[str]] = frozenset({"failing_tests", "first_failure", "delta_test_count", "timed_out"})`, `_TRACE_SIGNAL_DETAIL_KEYS: Final[frozenset[str]] = frozenset({"new_shell", "new_endpoints", "coverage_ok", "coverage_evidence_strength"})`, etc. — at module level, NOT in `__all__`. These document intent for collector authors (S4-02..S4-06) and catch typos at code-review time. Pattern: `src/codegenie/probes/language_detection.py` `_WARNING_IDS`. Informational only; the model does NOT enforce key membership (extension-by-addition stays clean — Phase 7 collectors will append, not edit).
- **Forward seam — Phase 7 widening (P-10, Notes-only):** Phase 7 will add `baseimage: BaseimageSignal | None = None` and `shell_presence: ShellPresenceSignal | None = None` as additive optional fields on `ObjectiveSignals` per ADR-0003. `tests/sandbox/test_objective_signals_introspection.py` walker MUST keep passing — Phase 7's PR is the integration test for additive widening. The walker mutation suite (AC-8b W-1..W-4) is the regression protection for that path.
- **Forward seam — `Blake3Hex` NewType (P-9, Notes-only):** `SignalProvenance.inputs_blake3` is `str` here (opaque envelope). If a `Blake3Hex` NewType emerges as a kernel-tier abstraction (S3-01 may produce one for `SandboxSpecHash`, and `Attempt` carries `prev_hash` / `chain_hash` of the same shape), retrofit alongside. Not now — Rule 2.
- **Forward seam — `ObjectiveSignals` shape (P-8, Notes-only):** the record-of-optionals (NOT `list[Submodel]`) is intentional per ADR-0003. Single source of truth per kind; multiple signals of the same kind explicitly rejected. Phase 6's LangGraph nodes consume the populated optionals; do NOT migrate to a list shape in a future story without an ADR amendment.
