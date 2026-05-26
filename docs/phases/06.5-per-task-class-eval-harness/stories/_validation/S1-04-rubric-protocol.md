# Validation report: S1-04 — Rubric Protocol

**Validated:** 2026-05-26
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S1-04 lands `src/codegenie/eval/rubric.py` — the one-method `@runtime_checkable Rubric(Protocol)` that bench-author unit tests import in-process, and that the registry's `TaskClass.rubric_class: type[Rubric]` annotation makes static-type-meaningful. The story is well-referenced (every claim traces to `phase-arch-design.md §Component design → rubric.py`, ADR-0001's "Protocol-as-typing-aid-not-runtime-contract" rationale, and Phase 5 ADR-0006's Protocol-vs-ABC convention), the goal is small and singular, and the TDD plan correctly insists on red-marker-then-green discipline. But several load-bearing structural invariants live in prose or in `Notes for implementer` without ACs, one AC contains a **factual error that would make the test fail as written**, and the TDD plan's introspection technique is fragile against accidental Protocol-internals drift.

**Empirical verification of Python 3.11+ Protocol semantics performed** (`python3` interactive session before writing this report) to ground every test in real behavior rather than documented-but-untested assumption:

```text
>>> Rubric.__abstractmethods__               # AC-6 as-written asserts == frozenset({"score"})
frozenset()                                  # ← AC-6 IS FALSE; the test would fail
>>> typing._get_protocol_attrs(Rubric)
{'score'}                                    # ← the canonical "exactly one declared method" check
>>> Rubric()
TypeError: Protocols cannot be instantiated  # ← uninstantiable invariant — no AC pins this
>>> isinstance(WrongSig(), Rubric)           # class with score(self) only — no params
True                                         # ← runtime Protocol checks NAMES, not SIGNATURES
>>> isinstance(NonCallableScore(), Rubric)   # class with `score = 42` attribute
True                                         # ← runtime Protocol does not even require callable
```

Four blocks, ten hardens, three nits. No `NEEDS RESEARCH` — every pattern is precedented in this repo: `vuln_index/protocol.py` is the closest sibling (`@runtime_checkable Protocol` with one method, module docstring citing ADRs, `__all__` export discipline, `from __future__ import annotations`); `fallback/leaf/port.py` (`LeafLlmPort`) is the cross-process-boundary precedent (Protocol surface vs subprocess wire — same asymmetry); `cache/keys.py` and `coordinator/input_snapshot.py` for `@runtime_checkable` lineage.

Five themes ran through the findings:

1. **AC-6 as written is empirically false and would block the story** (block — F-COV-1 + F-TQ-1 + F-CON-1 converged). The AC claims `Rubric.__abstractmethods__ == frozenset({"score"})` "*only* by virtue of Protocol semantics; no `@abstractmethod` decorator is added." But Python 3.11+ `typing.Protocol` does **NOT** populate `__abstractmethods__` for a vanilla `Protocol` body — that frozenset is empty unless `@abstractmethod` is explicitly applied. A test asserting the original AC would fail. The canonical Protocol-internals API is `typing._get_protocol_attrs(Rubric)` which returns `{"score"}`. Rewrote AC-6 into three observable contracts: AC-6a (canonical declared-attrs via `_get_protocol_attrs`), AC-6b (AST inspection of `rubric.py` proves no `from abc import abstractmethod` import and no `@abstractmethod` decorator on `score`), AC-6c (the `dir()` filter test from the original TDD plan is *retained* as a structural belt-and-suspenders — it passes today and would catch a future Protocol-internals leak).

2. **Signature shape is asserted by type annotation only, not introspected** (block — F-COV-2 + F-TQ-3 + F-DP-1 converged). AC-3 names `score(self, case: BenchCase, harness_output: Mapping[str, Any]) -> BenchScore` but no test introspects `inspect.signature(Rubric.score)` to pin (a) parameter names exactly (`("self", "case", "harness_output")`), (b) parameter count exactly (3), (c) the return annotation exactly (`BenchScore`). The subprocess wire contract (ADR-0001) and the bench-author in-process call site **both depend on this signature being stable**. A regression renaming `case` → `c` or `harness_output` → `output` would: (a) break every bench-author keyword call (`rubric.score(case=c, harness_output=o)`); (b) break the JSON-to-kwargs unpacking the runner uses; (c) still pass mypy `--strict` for any *new* call site that adopts the renamed names. Added AC-3a + AC-3b + matching tests via `inspect.signature` and `typing.get_type_hints`.

3. **Protocol's runtime-isinstance limitation is unobserved — bench authors will be surprised** (block — F-COV-3 + F-TQ-4 + F-DP-2). `isinstance(obj, Rubric)` at runtime checks **attribute names only**, not signatures and not even callability. A class with `def score(self)` (0 args), or even `score = 42` (a non-callable int), passes the isinstance gate. The story's `_DuckTypedRubric` test pins the happy path; `_MissingScore` pins the obvious-typo negative; but the **deliberate language limitation** is not pinned — meaning a future contributor reading the tests could believe Protocol does what it doesn't, write a brittle runtime guard expecting tighter semantics, and ship a regression. Added AC-10 (`_WrongSignatureScore`: 0-arg `score` passes isinstance — pinned as deliberate-not-bug) + AC-10a (`_NonCallableScore`: `score = 42` passes isinstance — pinned as deliberate-not-bug). Both tests document **why** in the Arrange block: "mypy `--strict` is the structural enforcer; isinstance is the structural-presence check; the asymmetry is per ADR-0001's two-call-site model." This is **specification by example** for a footgun, not a behavior-change AC.

4. **Three module-shape invariants live in prose, not in ACs** (block — F-COV-4 + F-DP-3 + F-CON-3). (a) `__all__ = ["Rubric"]` is in the implementation outline but no test pins it — a regression adding a helper class or a second Protocol would slip silently. (b) `from __future__ import annotations` is the codebase convention for Protocol modules (cf. `vuln_index/protocol.py:17` and the typed-eval-of-forward-refs requirement when `BenchCase`/`BenchScore` live in a sibling module), but not in the story's implementation outline. (c) The module docstring citing ADR-0001 + Phase 5 ADR-0006 is in `Refactor` notes only — no AC pins it; sibling Protocol files in this repo (`vuln_index/protocol.py:1-15`, `fallback/leaf/port.py`) make ADR-citation-in-docstring a structural convention that fence-CI-adjacent tests verify elsewhere. Added AC-12 (`__all__` exactness), AC-13 (`from __future__ import annotations` present), AC-14 (module docstring cites both ADRs by id; AST-introspected on the parsed module).

5. **Direct-instantiation defense unpinned** (harden — F-COV-5 + F-TQ-5). `Rubric()` raises `TypeError("Protocols cannot be instantiated")` per CPython 3.11+ semantics. A test pinning this would catch a regression where a future contributor removes `Protocol` from the bases (e.g., refactoring to ABC), making `Rubric` instantiable — which would silently let bench-author tests construct `Rubric()` empty and seemingly "satisfy" isinstance via a base-class fallthrough. Added AC-11.

Stale-dependency declaration: `Depends on: —` is wrong. The story imports `from codegenie.eval.models import BenchCase, BenchScore` (which is S1-02's deliverable). The test file imports the same. S1-02 must be GREEN before S1-04 starts. Corrected to `Depends on: S1-02 (wire models — BenchCase, BenchScore)`.

Hardens covered: `inspect.signature` introspection (F-COV-2 + F-TQ-3); `__all__` exactness via `importlib` reload (F-COV-4); `from __future__ import annotations` (F-COV-4); module docstring ADR-citation discipline (F-COV-4); direct-instantiation defense (F-COV-5); `_get_protocol_attrs` canonical introspection (F-TQ-1); AST-based negative check for `@abstractmethod` (F-TQ-1 + F-CON-1); the dir()-filter test retained as belt-and-suspenders (F-TQ-1 — the canonical and the structural-belt are complementary, not redundant).

Test-Quality refactor: `_ok_score()` helper retained but expanded to verify `BenchScore` constructor surface stability — if S1-02's `BenchScore` field set drifts, the helper's `pytest.skip` with a structured reason routes the failure to S1-02 rather than masking it as a S1-04 regression.

Consistency review:
- ADRs referenced (Phase 6.5 ADR-0001, Phase 5 ADR-0006) — both exist; rationale in the story matches the decision sections.
- Cross-phase precedent (Phase 5 ADR-0006) cited correctly; the "Protocol when no shared default behavior" rule applies cleanly to rubrics (every task class's rubric is task-class-specific; nothing shared).
- Arch sections referenced (`§Component design → rubric.py`, `§Agentic best practices — Tool-use safety`) — both present; consistent with the story.
- CLAUDE.md commitments: "Make illegal states unrepresentable" → Protocol IS the illegal-states defense (a conformer without `score` cannot satisfy mypy `--strict`); "Extension by addition" → adding a Phase 7 distroless rubric is one new class implementing Rubric, zero edits to `rubric.py`; "Fail loud" → direct instantiation raises eagerly; "Tests verify intent, not just behavior" (Rule 9) → the deliberate-runtime-Protocol-limitation tests document intent (mypy is the enforcer) rather than just observing isinstance behavior. All preserved.

Design-pattern review surfaced:
- (a) **Hexagonal port pattern — sibling lineage.** `vuln_index/protocol.py` (`Feed`) and `fallback/leaf/port.py` (`LeafLlmPort`) are the two closest Protocol-port siblings; `Rubric` is the 3rd in the "structural Protocol with `@runtime_checkable` for in-process duck-typing + a parallel subprocess wire contract" family. The pattern is established, not invented here. The sibling files' module-docstring discipline (ADRs honored, sentinel comment naming the cross-boundary asymmetry) becomes the template. Surfaced as Notes for implementer with file:line references.
- (b) **Process-boundary asymmetry as a deliberate type-system feature.** The Protocol exists *because* the subprocess boundary erases static type relationships; bench-author tests are the trusted typed surface. Adding a runtime `isinstance(rubric, Rubric)` guard at registration time (which a defensive reader might propose) would be a category error — mypy already enforces it at type-check time; runtime adds nothing because the registration site has already been compiled. This becomes a Notes-for-implementer paragraph explicitly warning the executor against adding such a guard.
- (c) **Rule of three not crossed for a Protocol-port kernel.** Three Protocol-port files exist (`Feed`, `LeafLlmPort`, `Rubric`). The pattern is consistent — `from __future__ import annotations`, `@runtime_checkable Protocol`, `__all__ = ["Name"]`, module docstring citing ADRs, no class-level state. A shared `kernel/port_base.py` would couple cross-domain ports artificially; **YAGNI wins**. Documented in Notes for implementer as the deferred-extract target if a 5th Protocol-port lands and the discipline drifts.
- (d) **Functional core / imperative shell.** Rubric is pure structural — zero state, zero side effects, zero I/O. The imperative shell is the runner (S3-03) which does the subprocess invocation. Correct shape.
- (e) **`Mapping[str, Any]` for `harness_output` — typed-at-the-edge.** The Protocol accepts the JSON-deserialized untyped mapping at the in-process boundary; the bench-author's rubric internally narrows. Correct (the alternative — `BaseModel` for `harness_output` — would couple every rubric to a phase-pinned schema, defeating the per-task-class scoring contract).

None of these pattern findings become ACs (per skill guidance — pattern names are not observable; observable behaviors derived from them are). The sibling-lineage convention becomes Notes for implementer with file:line references.

Verdict: **HARDENED.** Four blocks (F-COV-1/F-TQ-1/F-CON-1 converged on the AC-6 factual error; F-COV-2/F-TQ-3/F-DP-1 converged on signature-introspection; F-COV-3/F-TQ-4/F-DP-2 converged on Protocol-limitation specification; F-COV-4/F-DP-3/F-CON-3 converged on module-shape ACs — all in-place-fixable with precedented patterns). Ten hardens. Three nits. No `NEEDS RESEARCH`. The mutation set the hardened suite resists includes (non-exhaustive): drop `@runtime_checkable`; drop `Protocol` from bases; add a 2nd method to `Rubric`; rename `case` → `c` or `harness_output` → `output`; change return annotation from `BenchScore` to `dict[str, Any]`; add `@abstractmethod` to `score`; add `from abc import abstractmethod`; drop `__all__`; export a 2nd symbol via `__all__`; drop `from __future__ import annotations`; drop the module docstring; instantiate `Rubric()` somewhere; assume `isinstance` catches signature mismatches; assume `isinstance` requires `score` to be callable.

## Findings by critic

### Coverage critic

#### F-COV-1: AC-6 contains a factually incorrect claim that would block the story
- **Severity:** block (converged with F-TQ-1 + F-CON-1)
- **Type:** factually wrong AC
- **Where:** Original AC-6 — "`Rubric.__abstractmethods__ == frozenset({"score"})` *only* by virtue of Protocol semantics; no `@abstractmethod` decorator is added"
- **Why it matters:** Empirically verified in Python 3.13 (and confirmed against the CPython 3.11+ `typing` module source): a vanilla `@runtime_checkable Protocol` body with `def score(...): ...` does **NOT** populate `__abstractmethods__`. The frozenset is `frozenset()`. The only way to get `score` into `__abstractmethods__` is to add `@abstractmethod` — which AC-6 simultaneously forbids. The AC is a logical contradiction; a test would fail at the green step.
- **Proposed fix:** Split AC-6 into three observable contracts:
  - AC-6a: `typing._get_protocol_attrs(Rubric) == frozenset({"score"})` (canonical Protocol-internals introspection).
  - AC-6b: AST inspection of `src/codegenie/eval/rubric.py` proves (i) no `from abc import abstractmethod` (or `from abc import ...abstractmethod...`) import, (ii) no `@abstractmethod` decorator on the `score` method.
  - AC-6c: Retain the original `dir()`-filter membership test as a structural belt — current Protocol implementation does pass this filter, and a future Protocol-internals leak (e.g., a public name added to the Protocol base in a Python upgrade) would be caught here.
- **Resolution:** Applied — AC-6 rewritten as AC-6a/b/c; three matching tests added; ACs renumbered.

#### F-COV-2: Signature shape unobserved beyond annotation
- **Severity:** block (converged with F-TQ-3 + F-DP-1)
- **Type:** missing AC for load-bearing wire contract
- **Where:** AC-3 names the signature; no test introspects it.
- **Why it matters:** Per ADR-0001, the signature `score(self, case, harness_output) -> BenchScore` is the **two-call-site contract** — bench-author tests (in-process, keyword args) AND the subprocess JSON-to-kwargs unpacking the runner does. A regression renaming `case` → `c` is mypy-clean for any *new* call site adopting the rename, but silently breaks every existing call site. Mypy alone doesn't catch parameter-name drift across modules that share the Protocol.
- **Proposed fix:**
  - AC-3a: `inspect.signature(Rubric.score).parameters` keys equal `("self", "case", "harness_output")` exactly; arity is 3 (excluding self → 2).
  - AC-3b: `typing.get_type_hints(Rubric.score)` resolves `case → BenchCase`, `harness_output → Mapping[str, Any]`, return → `BenchScore`. (Pinning return annotation as `BenchScore`, not `dict[str, Any]` or any structural-supertype.)
- **Resolution:** Applied — AC-3a + AC-3b + two matching tests.

#### F-COV-3: Protocol's runtime-isinstance limitation not pinned as specification
- **Severity:** block (converged with F-TQ-4 + F-DP-2)
- **Type:** missing AC for deliberate language limitation
- **Where:** AC-4/AC-5 cover happy path + obvious typo; nothing covers the Protocol footgun.
- **Why it matters:** Runtime Protocol isinstance is **name-only** — `isinstance(obj, Rubric)` is True if `obj` has a `score` attribute, whether it's the right signature, the right arity, or even callable. A reader unfamiliar with this footgun could (a) add a runtime guard expecting tighter semantics and be surprised; (b) ship a bench-author rubric with `score = some_constant` and find isinstance passes but the subprocess crashes. The right defense is to **pin the limitation as deliberate** so the next reader understands intent.
- **Proposed fix:**
  - AC-10: `_WrongSignatureScore` (a class with `def score(self): pass` — 0 args) passes `isinstance(..., Rubric)`. Test arranges with a docstring naming "mypy `--strict` is the structural enforcer; isinstance is name-presence-only" and citing ADR-0001.
  - AC-10a: `_NonCallableScore` (a class with `score = 42`) passes `isinstance(..., Rubric)`. Same docstring discipline.
- **Resolution:** Applied — AC-10 + AC-10a with intent-documenting test docstrings.

#### F-COV-4: Three module-shape invariants prose-only, not ACs
- **Severity:** block (converged with F-DP-3 + F-CON-3)
- **Type:** missing AC for codebase convention
- **Why it matters:**
  - `__all__ = ["Rubric"]` exports the public surface; a regression exporting a 2nd symbol (or dropping it) drifts the module's public contract silently.
  - `from __future__ import annotations` is the established convention for Protocol-port files in this repo (cf. `vuln_index/protocol.py:17`, `fallback/leaf/port.py`); dropping it makes forward references break + the file inconsistent with siblings.
  - Module docstring citing both ADRs is the established sibling-Protocol convention; without it, the rationale for the Protocol-vs-ABC choice is invisible to a future reader.
- **Proposed fix:**
  - AC-12: `rubric.__all__ == ("Rubric",)` (or `["Rubric"]` — pin the type+value) via `importlib.import_module` + attribute check.
  - AC-13: AST inspection finds `from __future__ import annotations` in `rubric.py`'s import block.
  - AC-14: Module docstring (parsed via `ast.get_docstring`) cites both `ADR-0001` and `Phase 5 ADR-0006` literally (substring presence is sufficient — the goal is rationale traceability, not prose form).
- **Resolution:** Applied — three ACs + matching tests.

#### F-COV-5: Direct instantiation defense unpinned
- **Severity:** harden (converged with F-TQ-5)
- **Type:** missing AC for runtime invariant
- **Where:** Implementation outline / Refactor notes mention "Protocol convention is `...` body" — nothing pins `Rubric()` raises.
- **Why it matters:** A regression replacing `class Rubric(Protocol)` with `class Rubric(ABC)` (or `class Rubric:` plain) would let `Rubric()` succeed. A bench-author test that constructs `Rubric()` and asserts `isinstance(Rubric(), Rubric)` would seemingly pass — but the Protocol's structural-typing intent has been destroyed.
- **Proposed fix:** AC-11 — `Rubric()` raises `TypeError`; assert the exception message contains `"Protocol"` substring (to catch the "regress-to-ABC" mutation which raises `TypeError("Can't instantiate abstract class")`).
- **Resolution:** Applied — AC-11 + test pinning both the exception and a substring of the message.

#### F-COV-6: Score helper's `_ok_score()` masks S1-02 drift
- **Severity:** nit
- **Type:** test-helper fragility
- **Where:** `_ok_score()` in the TDD plan
- **Why it matters:** If S1-02's `BenchScore` field set drifts (a field added, renamed, or removed), `_ok_score()` raises a Pydantic `ValidationError` at test-collection time — and the resulting noise is attributed to S1-04 (test "imports models and they don't match") rather than to S1-02. The right discipline is **fail-routing**: catch the constructor exception, raise `pytest.skip(reason=f"S1-02 BenchScore drift: {exc}")` so the operator knows where to look.
- **Proposed fix:** Wrap `_ok_score()` construction in a `try/except ValidationError` that routes failure with a structured `pytest.skip`.
- **Resolution:** Applied — `_ok_score()` rewritten with skip-routing per the F-COV-6 spec.

### Test-Quality critic

#### F-TQ-1: `dir()` filter is fragile and won't catch the AC-6 failure mode
- **Severity:** block (converged with F-COV-1)
- **Mutation that slips:** As written, the test asserts `members == {"score"}` after a `dir(Rubric)` + filter. This passes today, but: (a) it doesn't catch the AC-6 false claim (because `__abstractmethods__` is empty, no assertion fires); (b) a future Python version that exposes a new public name on `Protocol` (e.g., `_is_protocol_attrs` renamed `protocol_attrs`) would break the filter spuriously; (c) the filter relies on `not name.startswith("_")` which is convention-fragile.
- **Proposed fix:** Three-layer defense:
  1. **Canonical** — `typing._get_protocol_attrs(Rubric) == frozenset({"score"})` (private API but stable since 3.8; the codebase convention is to use it for Protocol introspection — see Notes for implementer).
  2. **AST** — parse `rubric.py`, walk for a `ClassDef` named `Rubric`, count `FunctionDef`/`AsyncFunctionDef` children = 1, name = `"score"`.
  3. **Belt-and-suspenders** — retain the original `dir()` filter as a smoke check; it would catch a future Protocol-internals leak even if (1) drifts.
- **Resolution:** Applied — three independent tests (`test_protocol_attrs_canonical`, `test_ast_proves_exactly_one_method_named_score`, `test_dir_filter_belt_and_suspenders`).

#### F-TQ-2: `try/except` to verify `@runtime_checkable` is asymmetric
- **Severity:** harden
- **Mutation that slips:** The original `test_runtime_checkable_decorator_is_applied` does `try: isinstance(object(), Rubric); except TypeError: pytest.fail(...)`. A regression dropping `@runtime_checkable` raises `TypeError("Instance and class checks can only be used with @runtime_checkable protocols")` — caught by `except`, calls `pytest.fail`. **But** the `pytest.fail` is inside a `# pragma: no cover` comment, signaling the path is expected unreachable — which silently downgrades the assertion to "test passes regardless." If the assertion path is unreachable, the test isn't really testing anything; it's a comment.
- **Proposed fix:** Direct positive assertion on the typing-internal flag: `assert Rubric._is_runtime_protocol is True` (private API but stable + the canonical CPython marker the decorator sets). Drop the try/except construct + the `# pragma: no cover`. Add a second positive assertion that `isinstance(object(), Rubric) is False` (a vanilla object doesn't have `score`; the False return is the runtime-isinstance pathway working).
- **Resolution:** Applied — `test_runtime_checkable_marker_is_set` + `test_runtime_isinstance_returns_false_for_unconformant_object`.

#### F-TQ-3: No signature-introspection tests
- **Severity:** block (converged with F-COV-2)
- **Mutation that slips:** Rename `case` → `c`, or `harness_output` → `output`, or `harness_output: Mapping[str, Any]` → `harness_output: dict[str, Any]`, or return annotation `BenchScore` → `dict[str, Any]`. Every one of these passes the original 4 tests (the structural conformance only checks method name + presence). Bench-author and runner call sites silently desynchronize.
- **Proposed fix:** `test_score_signature_parameter_names_and_arity` + `test_score_annotation_types`. Use `inspect.signature(Rubric.score).parameters` + `typing.get_type_hints(Rubric.score)`.
- **Resolution:** Applied — both tests added; the type-hints test resolves forward references via `globalns=vars(rubric)`.

#### F-TQ-4: Protocol-isinstance footgun unobserved
- **Severity:** block (converged with F-COV-3)
- **Mutation that slips:** A reader who deletes the `_WrongSignatureScore`/`_NonCallableScore` tests, replaces them with "runtime-validates signature" expectations, and adds a defensive runtime guard at the registry (S1-03) site would inflate the surface without ADR-0001 amendment. **The right shape is to pin the limitation explicitly so the next reader knows the asymmetry is deliberate.**
- **Proposed fix:** Two specification-by-example tests with arrange-block docstrings that name ADR-0001 and the "mypy is the structural enforcer" rule. Tests are positive (assert True isinstance) and document that this is **deliberate-not-a-bug**.
- **Resolution:** Applied — AC-10/AC-10a + tests.

#### F-TQ-5: No direct-instantiation test
- **Severity:** harden (converged with F-COV-5)
- **Mutation that slips:** Refactor `Protocol` to `ABC` — silent semantic shift; `Rubric()` raises `TypeError("Can't instantiate abstract class Rubric...")` instead of `TypeError("Protocols cannot be instantiated")`. The downstream registry would still type-check but the trust posture (Protocol-as-structural-aid-only) has been destroyed.
- **Proposed fix:** Assert exception class + that the message includes `"Protocol"`. Catches the ABC-regression specifically.
- **Resolution:** Applied — `test_rubric_cannot_be_instantiated`.

#### F-TQ-6: Test module-shape invariants (`__all__`, `__future__`, docstring)
- **Severity:** harden (converged with F-COV-4 + F-DP-3)
- **Mutation that slips:** Each of these can be dropped/regressed without any test catching it. Module-shape invariants are codebase convention; conventions enforced by tests, not by convention alone (Rule 11 caveat: convention without enforcement drifts).
- **Proposed fix:** Three tests:
  - `test_module_exports_only_rubric` — `rubric.__all__ == ("Rubric",)` (or `["Rubric",]`).
  - `test_future_annotations_imported` — AST walks the import list, finds `from __future__ import annotations`.
  - `test_module_docstring_cites_both_adrs` — `ast.get_docstring(parsed)` contains both `"ADR-0001"` and `"ADR-0006"` substrings.
- **Resolution:** Applied — three tests added.

#### F-TQ-7: `_ok_score()` constructor surface fragility
- **Severity:** nit (converged with F-COV-6)
- **Resolution:** Applied — `_ok_score()` wrapped with `try/except ValidationError → pytest.skip`.

### Consistency critic

#### F-CON-1: AC-6 contradicts CPython semantics
- **Severity:** block (converged with F-COV-1)
- **Where:** Original AC-6
- **Verdict:** AC-6 is internally inconsistent (claims a state that exists *only* via Protocol semantics, but the state in fact *only* exists when `@abstractmethod` is added — which the same AC forbids). The story's intent is correct (no `@abstractmethod`, one method); the AC's claim about `__abstractmethods__` is wrong. Replaced with `_get_protocol_attrs` + AST-no-@abstractmethod + dir-filter triad.
- **Resolution:** Applied (see F-COV-1).

#### F-CON-2: `Depends on: —` is stale
- **Severity:** harden
- **Where:** Story header
- **Verdict:** The story imports `from codegenie.eval.models import BenchCase, BenchScore` (S1-02's deliverable). The TDD plan's `_ok_score()` constructs `BenchScore(...)`. Without S1-02 GREEN, S1-04's red marker can't even be reached. The dependency declaration must reflect this so the executor doesn't attempt S1-04 before S1-02 ships.
- **Resolution:** Applied — corrected to `S1-02 (wire models — BenchCase, BenchScore)`.

#### F-CON-3: Module-shape conventions vs sibling Protocol-port files
- **Severity:** harden (converged with F-COV-4 + F-DP-3)
- **Where:** Implementation outline references `__all__` but not `from __future__ import annotations`; sibling Protocol-port files in this repo (`vuln_index/protocol.py:17`, `fallback/leaf/port.py`) consistently use it.
- **Verdict:** The codebase has an established Protocol-port shape; this story should mirror it (Rule 11 — match codebase conventions). Surfacing as ACs (not just prose) makes the convention enforcement structural, not social.
- **Resolution:** Applied via AC-13 + AC-14.

#### F-CON-4: ADRs and arch references all check out
- **Severity:** info
- **Verdict:** ADR-0001 (rubric-execution-isolation-via-subprocess) and Phase 5 ADR-0006 (Protocol-vs-ABC-convention) both exist; the story's rationale matches their Decision sections. Arch `§Component design → rubric.py` (lines 539-554) and `§Agentic best practices — Tool-use safety` both present and consistent with the story's framing.

#### F-CON-5: CLAUDE.md commitments respected
- **Severity:** info
- **Verdict:** "Make illegal states unrepresentable" → Protocol IS the illegal-states defense at the type system level. "Extension by addition" → adding a Phase 7 rubric is one new class implementing Rubric, zero edits to `rubric.py`. "Fail loud" → `Rubric()` raises eagerly (AC-11); the runtime-isinstance footgun is specified-by-example (AC-10/AC-10a) so the asymmetry isn't silent. "Tests verify intent, not just behavior" (Rule 9) → the deliberate-limitation tests document intent in docstrings.

#### F-CON-6: Sibling-story dependency timing
- **Severity:** info
- **Verdict:** S1-02 (wire models) is the only true dependency. S1-03 (TaskClass + registry) declares `Depends on: S1-01, S1-04` — meaning S1-03 consumes S1-04. The Step-1 execution order is S1-01 → S1-02 → S1-04 → S1-03 → S1-05. The corrected `Depends on:` row supports this ordering.

### Design-Patterns critic

#### F-DP-1: Signature-shape pinning is the "specification-by-introspection" pattern
- **Severity:** block (converged with F-COV-2)
- **Smell:** Critical wire-contract surface (the parameter names the JSON unpacking depends on) lives only as type annotation, not as observable test.
- **What's wrong:** The Protocol's signature is **the** wire contract per ADR-0001. Without introspection tests, mypy alone enforces it at *call sites* — but a parameter rename is mypy-clean if all call sites are updated together. In a multi-PR refactor (bench-author renames first, runner renames later), the intermediate state silently breaks the rubric subprocess invocation.
- **Proposed fix:** `inspect.signature` + `typing.get_type_hints` introspection tests pin the contract independent of call sites.
- **Resolution:** Applied via AC-3a + AC-3b.

#### F-DP-2: Specification-by-example for language limitations
- **Severity:** block (converged with F-COV-3)
- **Smell:** Reader-surprising deliberate behavior (Protocol's runtime-name-only isinstance) is unobserved; future contributors will be tempted to "fix" the gap.
- **What's wrong:** When a behavior is **deliberate-but-counterintuitive**, the right defense is a test that asserts the counterintuitive behavior + names the rationale in the docstring. This is **specification by example** for the language limitation — not a behavior change, but a documented intent guard.
- **Proposed fix:** AC-10/AC-10a + docstring-anchored Notes for implementer.
- **Resolution:** Applied.

#### F-DP-3: Sibling Protocol-port lineage (hexagonal port pattern)
- **Severity:** harden (converged with F-COV-4 + F-CON-3)
- **Smell:** Module-shape conventions established by siblings (`vuln_index/protocol.py`, `fallback/leaf/port.py`) are unenforced for this new sibling.
- **What's wrong:** `Rubric` is the 3rd Protocol-port in the repo. Each sibling pins: `from __future__ import annotations`, `@runtime_checkable Protocol`, `__all__`, module docstring citing the ADRs that justify the port shape. Without enforcement, this drifts.
- **Proposed fix:** AC-12/13/14 enforce the three module-shape invariants observably; sibling-lineage convention noted in `Notes for implementer` with file:line refs.
- **Resolution:** Applied.

#### F-DP-4: Rule-of-three for a `Port` kernel — NOT yet, defer
- **Severity:** info
- **Verdict:** Three Protocol-port files exist (`Feed`, `LeafLlmPort`, `Rubric`). Extracting a shared `kernel/port_base.py` would couple cross-domain ports artificially — each port's contract is task-domain-specific (CVE feeds, LLM calls, rubric scoring), and the shared invariants (`@runtime_checkable`, `__all__`, etc.) are Python-language conventions not domain-relevant ones. **YAGNI wins.** Documented in Notes for implementer as the deferred-extract trigger (a 5th Protocol-port that drifts from the discipline would be the right moment to revisit).

#### F-DP-5: Functional core / imperative shell
- **Severity:** info
- **Verdict:** Rubric Protocol is purely declarative — zero state, zero side effects, zero I/O. The imperative shell (subprocess invocation) is the runner's responsibility (S3-03). Correct shape.

#### F-DP-6: Process-boundary asymmetry as a deliberate type-system feature
- **Severity:** harden
- **Smell:** A defensive reader could propose adding `isinstance(rubric, Rubric)` at registry-registration time (S1-03), justifying it as "fail loud." But that would be a category error per ADR-0001: mypy `--strict` already enforces the structural contract at type-check time; runtime `isinstance` at registration adds zero value (the registration site is compiled code; the rubric class is the source the registration site names; mypy has already validated). **The asymmetry — typed at bench-author surface, untyped across the subprocess boundary — is the security posture, not an oversight.**
- **Proposed fix:** Notes for implementer paragraph: "Resist the urge to add `isinstance(rubric, Rubric)` at the registry (S1-03) registration site. ADR-0001 explicitly relegates the Protocol to a typing aid for bench-author tests; mypy `--strict` is the structural enforcer; runtime `isinstance` adds nothing because the registration site is already a compiled call. If S1-03's executor proposes such a guard, push back: it widens the runtime surface without defending against a real threat. The runtime check is in the tests of *this* file; nowhere else."
- **Resolution:** Notes for implementer paragraph added.

#### F-DP-7: `Mapping[str, Any]` for `harness_output` — typed-at-the-edge
- **Severity:** info
- **Verdict:** `Mapping[str, Any]` for the harness_output parameter is the correct typed-at-the-edge choice (not `BaseModel`, not `dict[str, Any]`). Each rubric internally narrows the mapping to its task-class-specific shape; the Protocol stays generic enough to support per-task-class diversity. Alternative (`BaseModel`) would couple every rubric to a phase-pinned schema; alternative (`dict[str, Any]`) would lose Mapping's read-only invariance.

#### F-DP-8: AST-based negative checks as a structural defense pattern
- **Severity:** harden
- **Smell:** Negative-space contracts ("no `@abstractmethod`", "no `from abc import abstractmethod`", "module-docstring cites ADRs") are usually enforced by review, not by tests.
- **What's wrong:** Review-enforced conventions drift. The codebase has precedent for AST-based negative checks (fence tests at `tests/fence/` walk `src/codegenie/` ASTs to enforce structural-defense patterns). Applying the same pattern at this story's micro level (one file, three negative invariants) is consistent.
- **Proposed fix:** AC-6b (no `@abstractmethod`), AC-13 (positive: `from __future__ import annotations`), AC-14 (module docstring cites ADRs) all use AST parsing.
- **Resolution:** Applied — three AST-based tests in the TDD plan.

#### F-DP-9: Open/Closed at the file boundary
- **Severity:** info
- **Verdict:** Adding a Phase 7 distroless rubric (or any future task class rubric) is one new class implementing Rubric structurally — **zero edits** to `rubric.py`. The Protocol itself is the extension seam; the file is closed for modification, open for new conformers. Surfaced as Notes for implementer.

#### F-DP-10: No `TaskClassName` / `RubricName` newtype primitive-obsession surface
- **Severity:** info
- **Verdict:** The Rubric Protocol doesn't expose any identifier surface — no `rubric_name: str` field, no slug, no version. So no primitive-obsession opportunity exists here. (S1-03's `TaskClass.name` would be the right home for a `TaskClassName` newtype, and S1-03's validation report already noted the deferral.) No action.

## Conflict resolution

| Conflict | Resolution |
|---|---|
| Coverage F-COV-1 + Test-Quality F-TQ-1 + Consistency F-CON-1 all converge on the AC-6 factual error. | Merged into single rewrite (AC-6a/b/c) with three independent tests (`_get_protocol_attrs`, AST no-`@abstractmethod`, dir()-filter belt). Test-Quality framing (mutation that slips: dropping `@runtime_checkable`) cited in test docstrings. |
| Coverage F-COV-2 + Test-Quality F-TQ-3 + Design-Patterns F-DP-1 converge on signature-introspection. | Merged into AC-3a (parameter-name introspection) + AC-3b (annotation-type introspection). |
| Coverage F-COV-3 + Test-Quality F-TQ-4 + Design-Patterns F-DP-2 converge on Protocol-isinstance-limitation as specification-by-example. | Merged into AC-10 (wrong-signature) + AC-10a (non-callable). Both tests are positive (assert isinstance returns True) and document **why** in arrange-block docstrings citing ADR-0001. |
| Coverage F-COV-4 + Consistency F-CON-3 + Design-Patterns F-DP-3 converge on module-shape ACs. | Merged into AC-12 (`__all__`), AC-13 (`from __future__ import annotations`), AC-14 (module docstring cites ADRs). Sibling-lineage convention noted in `Notes for implementer` with file:line refs. |
| Design-Patterns F-DP-4 (extract `port_base.py` kernel) vs YAGNI / scope. | YAGNI wins. Surfaced as deferred-extract trigger in Notes for implementer (5th Protocol-port discipline drift). |
| Design-Patterns F-DP-6 (no `isinstance` guard in S1-03 registry) vs defensive reader who might add one. | ADR-0001 binding: do not add. Notes for implementer paragraph explicitly pushes back so the S1-03 executor (or any future review) has the rationale documented. |
| Coverage F-COV-6 + Test-Quality F-TQ-7 (`_ok_score()` fail-routing on S1-02 drift). | `_ok_score()` wrapped with `try/except ValidationError → pytest.skip` so S1-02 drift is routed to S1-02, not masked as S1-04 regression. |
| No critic-to-critic conflicts otherwise. | — |

## Edits applied

Story file edited in place. New `Validation notes` block under the story header. ACs renumbered from 9 unnumbered checkboxes to 18 explicit `AC-N` entries (`AC-1..AC-14` + sub-ACs `AC-3a/AC-3b/AC-6a/AC-6b/AC-6c/AC-10a`). The factually-wrong AC-6 was replaced; **the original AC-6 would have failed at the test step**, so the edit is both correctness and clarity. Implementation outline expanded to call out `from __future__ import annotations`, `__all__ = ["Rubric"]`, module docstring citing both ADRs, and the AST-introspectable shape requirements. TDD plan rewritten — original 4 tests grew to 12 (3 from AC-6 triad; 2 from signature introspection; 2 from limitation specification; 3 from module-shape; 1 from direct-instantiation; original 4 retained where still useful, with `dir()`-filter renamed to belt-and-suspenders and `test_class_missing_score_fails_isinstance` retained as the obvious-typo negative). Out of scope grew from 5 to 7 bullets. Notes for implementer grew from 5 bullets to 10, with new paragraphs on: (a) Protocol-isinstance footgun is deliberate per ADR-0001; (b) sibling Protocol-port lineage + file:line references; (c) anti-pattern guard against `isinstance` guard at S1-03 registration site; (d) deferred extract trigger for `port_base.py` kernel; (e) AST-introspection convention as structural defense.

Pre/post diff summary:

| Section | Before | After |
|---|---|---|
| Status | `Ready` | `HARDENED` |
| Depends on | `—` (stale) | `S1-02 (wire models — BenchCase, BenchScore)` |
| ACs | 9 unnumbered checkboxes (one factually wrong) | 18 explicit `AC-N` (AC-6 split AC-6a/b/c; AC-3 expanded AC-3a/b; AC-10/10a/11/12/13/14 new) |
| TDD plan red tests | 4 unit tests | 12 unit tests (4 original retained where useful + 8 new) |
| Implementation outline | 3 steps | 4 steps; rubric.py now requires `from __future__ import annotations` + `__all__` + module docstring citing both ADRs |
| Out of scope items | 5 bullets | 7 bullets (added: runtime `isinstance` guard at registration site is forbidden; `port_base.py` kernel extract is deferred) |
| Notes for implementer | 5 bullets | 10 bullets (added: ADR-0001 footgun discipline; sibling Protocol-port file:line refs; S1-03 anti-pattern guard; deferred `port_base.py` trigger; AST-introspection as structural defense) |
| Refactor step bullets | 4 | 5 (added: AST-introspectable shape — `__all__`, `__future__`, docstring all verified by tests in S1-04, not by review-only convention) |

## Verdict rationale

**HARDENED.** Four blocks (F-COV-1/F-TQ-1/F-CON-1 converged on the AC-6 factual error that would have failed the green step; F-COV-2/F-TQ-3/F-DP-1 converged on signature-introspection; F-COV-3/F-TQ-4/F-DP-2 converged on Protocol-limitation specification; F-COV-4/F-CON-3/F-DP-3 converged on module-shape ACs — all in-place-fixable with precedented patterns). Ten hardens. Three nits. No `NEEDS RESEARCH` — every pattern is precedented in this repo: `@runtime_checkable Protocol` with one method (`vuln_index/protocol.py`); module-docstring ADR-citation discipline (`vuln_index/protocol.py:1-15`); `__all__` export contract (every sibling Protocol-port file); `from __future__ import annotations` (every sibling Protocol-port file); AST-based negative checks (`tests/fence/`); signature-introspection pattern (`tests/unit/test_probe_contract.py`); the `_get_protocol_attrs` canonical introspection (Python `typing` stdlib).

Design-pattern posture: validator endorses (a) the hexagonal port pattern (Protocol as the structural seam; module-shape conventions as the sibling-lineage discipline); (b) specification-by-example for the runtime Protocol-isinstance footgun (deliberate language limitation pinned, not silently relied-on); (c) functional core / imperative shell (Rubric is pure; the imperative shell is S3-03's runner subprocess); (d) Open/Closed at the file boundary (new task class rubrics extend by addition); (e) AST-based negative checks as structural defense (`@abstractmethod` exclusion, `__future__` import, docstring ADR-citation — all enforced observably); (f) typed-at-the-edge `Mapping[str, Any]` for `harness_output`. None elevated to ACs (per skill guidance — pattern names are not observable; observable behaviors derived from them are). Anti-pattern guard against a runtime `isinstance` guard at the registry (S1-03) site is documented in Notes for implementer for the next reader who might be tempted.

The mutation set the hardened suite resists is enumerated in the Summary section.

## Recommended next step

`phase-story-executor` to implement. Story is ready: every AC is individually verifiable; the AC set collectively guarantees the goal (Protocol surface + structural disciplines + module-shape conventions pinned, not merely sampled); every test in the TDD plan would fail under a wrong implementation; the prescribed implementation pattern is precedented in two sibling Protocol-port files; the runtime Protocol-isinstance footgun is specified-by-example so future contributors understand the asymmetry is deliberate; the anti-pattern (runtime `isinstance` guard at registration site) is explicitly forbidden with rationale; the deferred extract (`port_base.py` kernel for Protocol-port commonalities) is flagged with a clear trigger condition (5th Protocol-port + discipline drift) but explicitly out of scope here.
