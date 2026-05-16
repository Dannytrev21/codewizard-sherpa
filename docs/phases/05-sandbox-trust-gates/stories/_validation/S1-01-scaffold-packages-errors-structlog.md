# Validation report — S1-01 Scaffold `sandbox/` + `gates/` packages

**Story:** [`../S1-01-scaffold-packages-errors-structlog.md`](../S1-01-scaffold-packages-errors-structlog.md)
**Validated:** 2026-05-16
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S1-01 is the kernel scaffolding for Phase 5: the package roots, marker error hierarchies, and `Final[str]` event-name constants on which every other Phase-5 story depends. The draft was structurally correct — the goal traced cleanly to ADR-0001 / ADR-0006 / ADR-0008, the file list was tight, and the out-of-scope section was disciplined.

It also had nine harden-tier weaknesses that, if shipped to the executor as-written, would have either let a structurally-wrong implementation pass the validator pass (under-specified ACs + thin tests) or diverged from Phase 0's already-established conventions (Rule 11). The most consequential were:

1. **`EVT_*` vs `EVENT_*` prefix divergence** — Phase 0 (`src/codegenie/logging.py`) and 11 existing consumers (`probes/*`, `parsers/*`) use `EVENT_*`. The draft introduced `EVT_*` with no rationale. This is Rule 11 ("Match the codebase's conventions") — silently forking the convention. Renamed everywhere.
2. **Vague event-name AC** — the draft said *"every event name in §Harness engineering and §Edge cases has a constant"*, leaving both the names and the string values undefined at the AC level. A future executor and validator could disagree on completeness; a swap of two string values would round-trip cleanly. Replaced with an explicit, pinned **Canonical event-name table** (10 constants → exact dotted-lowercase values).
3. **Unreliable forbidden-imports test** — the draft's `sys.modules` introspection fires from inside pytest, where another test in the session may have already imported `anthropic`. Replaced with a (static AST walk) + (fresh-subprocess runtime check) pair.

Nine hardening edits applied in place; no `RESCUE`-tier findings. No Stage-3 research needed — every gap was answerable from Phase 0 codebase precedent (`src/codegenie/errors.py`, `src/codegenie/logging.py`) plus the existing phase-05 ADRs.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim):** Create the two new top-level packages with empty `__init__.py` files, populated `errors.py` hierarchies, and a `logging.py` module exposing canonical structlog event-name constants the rest of Phase 5 imports.
- **Non-goals (from Out-of-scope):** SandboxClient Protocol + models (S1-02), ObjectiveSignals sub-models (S1-03), Gate ABC + GateContext (S1-04), decorator registries (S1-05), formal AST fence (S1-07), structlog BoundLogger configuration (deferred to first emitter, likely S2-01).

### Phase 5 exit criteria touched

- Step 1 done-criteria (High-level-impl.md §Step 1): `pytest tests/schema/` green; `mypy --strict src/codegenie/sandbox src/codegenie/gates` clean; branch coverage on `sandbox/contract.py` and `gates/contract.py` ≥ 95% (this story owns the package + errors + logging slice, not contract.py).
- **Load-bearing dependency:** every later Step 1 story (S1-02..S1-07) imports from `sandbox/errors.py`, `gates/errors.py`, and the two `logging.py` modules. Any rename here cascades.

### Load-bearing commitments touched

- **CLAUDE.md "Extension by addition"** — adding a new error class or event constant must be a new entry in this file, never editing the base/kernel.
- **CLAUDE.md "Match the codebase's conventions"** — Phase 0's `EVENT_*` prefix + dotted-lowercase values are the precedent.
- **ADR-0001** — two-chokepoint sandbox seam; this story plants the package roots, no chokepoint logic yet.
- **ADR-0006** — Protocol-vs-ABC convention; this story doesn't yet introduce either, but the package roots must accept both shapes added by S1-02 (`SandboxClient` Protocol in `sandbox/contract.py`) and S1-04 (`Gate` ABC in `gates/contract.py`).
- **ADR-0008** — LLM Judge deferral; the scaffold must not import `anthropic`, `langgraph`, `chromadb`, `sentence_transformers`. Formal CI fence lands in S1-07; this story owns its non-regression scaffold.

### Open/Closed boundaries (extension-by-addition contract)

- New error class → **append** subclass under `SandboxError`/`GateError`; add to `__all__`. **Never edit the base.**
- New event constant → **append** `EVENT_*: Final[str] = "..."` to the relevant `logging.py`; add to `__all__`; add a row to that future story's Canonical event-name table. **Never rename or re-value an existing constant** (audit chain + cost ledger key off these strings).
- New intermediate-base class (`SandboxBackendDockerError` between `SandboxError` and `SandboxBackendError`) — **forbidden** by the flat-hierarchy precedent in `src/codegenie/errors.py`. Structured context attaches at the catch site via structlog, not on the class.

### Phase 0 / Phase 1 prior art consulted

- `src/codegenie/errors.py` — flat-hierarchy marker shape (single base + direct subclasses, no `__init__`, no class attrs). Established the "behavior at catch site, not on class" pattern.
- `src/codegenie/logging.py` — `EVENT_*: Final[str] = "<dotted.lowercase>"` constant shape; `__all__` discipline; stdlib `logging` shadow via `import logging as _stdlib_logging`.
- `src/codegenie/indices/__init__.py` — counter-example: a package root that DOES re-export from `__init__.py`. This is permitted when the package has a single canonical user-facing surface; for Phase 5's `sandbox/` and `gates/`, flat imports are preferred so internal modules can grow without import cycles. AC-1 locks the flat shape.

### Open ambiguities (resolved before Stage 2)

- *"Every event name in `phase-arch-design.md §Harness engineering` and `§Edge cases` has a constant"* — resolved by enumerating in the Canonical event-name table (10 entries, sourced from arch §Tracing strategy + §Decision points + §Edge cases rows 5, 14, 16 + ADR-0007).
- Pre-execute marker event name — arch §Gap 1 calls it a `"pre_execute"` JSONL line; this story names the audit constant `EVENT_PRE_EXECUTE_MARKER_WRITTEN = "gate.pre_execute.written"`, chosen to live in the `gate.*` namespace alongside `gate.run.*` and `gate.attempt.*` for downstream consumers grepping for `gate.` prefix.

## Stage 2 — critic reports

### 2A · Coverage critic (verdict: COVERAGE-HARDEN)

| # | Severity | Finding | Fix applied |
|---|---|---|---|
| C-1 | harden | AC for event constants said "every name in arch has a constant" — no enumeration. Two readers could agree the AC was met with different name sets. | Added **Canonical event-name table** with 10 pinned `(name, value)` pairs sourced row-by-row from arch §Tracing strategy, §Decision points, §Edge cases 5/14/16, and ADR-0007. |
| C-2 | harden | No AC pinned the *string value* of each constant. A swap of two values (e.g., `EVENT_SANDBOX_EGRESS_BLOCKED = "sandbox.execute.started"`) would round-trip structurally. | New AC-4 asserts byte-exact value equality per constant; parametrized test enforces. |
| C-3 | harden | No AC for dotted-lowercase value shape. A typo `"GATE_RUN_STARTED"` would pass. | New AC-4a + value-level regex `^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$`. |
| C-4 | harden | No AC for `Final[str]` annotation (only in Refactor section). The executor's validator can't observe a refactor step. | Promoted to AC-4 (runtime + source-level annotation check). |
| C-5 | harden | No AC for `__all__` correctness. Mentioned only in Refactor. | Promoted to AC-4b (both `logging.py` modules) + AC-2/AC-3 (both `errors.py` modules); test asserts `__all__` is exactly the defined-constant set. |
| C-6 | harden | No AC for "errors extend `Exception` not `BaseException`" — explicitly named in Notes but not testable as written. | Promoted to AC-2 / AC-3 with a direct-base-class assertion test. |
| C-7 | harden | No AC for "no custom `__init__`, no class attributes". Notes said it; ACs didn't constrain it. A future contributor could add `def __init__(self, *a)` and break the marker discipline silently. | Promoted to AC-2 / AC-3 with a `vars(cls)` membership assertion that forbids any non-`__doc__`/`__module__`/`__qualname__` member. |
| C-8 | harden | No AC for import idempotence — AC-1 said "succeeds with no side effects" but the original test only checked `mod is not None`. | New AC-1a + `test_..._import_is_idempotent_same_object` (identity check on repeat import). |
| C-9 | harden | No AC for stdlib-`logging` shadow safety. Phase 0 accepted the shadow via `_stdlib_logging` alias; the new files could regress to bare `import logging`. | New AC-5 + AST-walk test forbidding bare-named `import logging`. |
| C-10 | harden | Cross-module value collision unconsidered. Nothing prevented `sandbox.execute.completed` from accidentally equaling `gate.run.completed` if two stories drifted apart. | New AC-4c (within-module uniqueness) + cross-module test `test_event_values_are_globally_unique_across_both_packages`. |
| C-11 | nit | AC-6's verification mechanism (`python -c "import ast; ..."` smoke) was vague. | Made AC-6 explicit: (a) static AST walk of every `.py` under both packages; (b) fresh-subprocess `sys.modules` check. |

### 2B · Test-quality critic (verdict: TESTS-HARDEN)

Mutation analysis — 10 plausible wrong implementations:

| # | Wrong implementation | Caught by draft TDD? | Caught after harden? |
|---|---|---|---|
| M-1 | `SandboxError(BaseException)` instead of `Exception` | Partial — `issubclass(..., SandboxError)` still passes | Yes — `test_sandbox_error_base_extends_exception_not_baseexception` asserts `__bases__ == (Exception,)` |
| M-2 | `SandboxBackendError(SandboxBackendInvalid)` (deepened hierarchy) | No — `issubclass` is transitively true | Yes — `test_each_sandbox_subclass_is_direct_child_of_sandbox_error` asserts direct bases |
| M-3 | Custom `__init__(self, code: int)` added to a subclass | No — test doesn't construct with args | Yes — `test_each_sandbox_error_class_is_marker_only` checks `vars(cls)` is empty |
| M-4 | `__str__` override returning `f"sandbox error: {msg}"` | No | Yes — `test_sandbox_error_message_is_passthrough` asserts `str(cls("x")) == "x"`; marker test catches the `__str__` member too |
| M-5 | Swap two event-constant values | No — original test only checked `isinstance(v, str)` + uniqueness | Yes — `test_*_event_constants_have_pinned_values` checks each value byte-exact |
| M-6 | Rename `EVENT_PROMPT_INJECTION_DETECTED` value to `"prompt-injection.detected"` (hyphen) | No | Yes — regex test rejects hyphens |
| M-7 | Drop `Final[str]` annotation, use bare assignment | No (runtime cares only about value) | Yes — AST walk asserts the source-level annotation text is `Final[str]` |
| M-8 | Forget to add `EVENT_SANDBOX_EGRESS_BLOCKED` to `__all__` | No | Yes — `__all__` exactness test |
| M-9 | Add a phantom `EVENT_SANDBOX_TRACE_BASELINE_MISSING` constant unmotivated by arch | Partial — passes; but caught by anti-speculation discipline at review | No automated test (Rule 2 enforced socially) — recorded as implementer-note guidance |
| M-10 | Re-export `SandboxError` from `sandbox/__init__.py` | No — original test didn't check `__init__` is empty | Indirect — AC-1 verifies no side effects + flat namespace; future story importing from `codegenie.sandbox.errors` directly catches drift |

Original test that did NOT survive review:

- `test_sandbox_package_has_no_forbidden_imports` relied on `assert banned not in sys.modules` AFTER `import codegenie.sandbox` in-process. Pytest runs many tests in one session; if another test imported `anthropic` (e.g., a future Phase 9 test), this would silently false-negative. **Replaced** with (a) AST walk of every `.py` under both packages (deterministic, session-independent) + (b) `subprocess.run([sys.executable, "-c", ...])` for fresh-interpreter runtime check.

Property-based testing not introduced — the surface (10 constants + 14 marker classes) is small and exhaustive parametrization is clearer than a Hypothesis strategy. Property tests will appear at S2-01 (`RetryLedger` chain determinism) where the input space is large.

### 2C · Consistency critic (verdict: CONSIST-HARDEN)

| # | Severity | Finding | Fix applied |
|---|---|---|---|
| K-1 | harden | **Rule 11 violation:** `EVT_*` prefix in draft diverged from Phase 0's `EVENT_*` prefix used in `src/codegenie/logging.py` and 11 existing import sites. No rationale given. | Renamed `EVT_*` → `EVENT_*` everywhere in ACs, TDD plan, and Notes. |
| K-2 | nit | "every event name in §Harness engineering and §Edge cases has a constant" — the arch sections cited do not actually contain explicit `EVENT_*` constant names; they contain prose audit-event strings. The story was reading prose values as if they were constant identifiers. | Resolved by introducing the Canonical event-name table — names are story-authored, values are extracted verbatim from arch prose and ADR-0007/ADR-0012. |
| K-3 | confirm | ADR-0006 says `sandbox/` will host a Protocol and `gates/` will host an ABC; story creates package roots only. Consistent — Protocol lands in S1-02, ABC in S1-04. | No change. |
| K-4 | confirm | ADR-0001 says `SandboxClient` is the seam, not a generalized `run_in_sandbox`. Story's `sandbox/__init__.py` is empty (no `run_in_sandbox` symbol). Consistent. | No change. |
| K-5 | confirm | ADR-0008 forbids `anthropic`/`langgraph`/`chromadb`/`sentence_transformers` imports under `sandbox/` or `gates/`. AC-6 enforces. | No change. |
| K-6 | harden | Story's Implementation outline §3 said "no `__init__` body beyond `super().__init__`" — but Phase 0's `src/codegenie/errors.py` uses bare `pass` (no `__init__` at all). The "beyond `super().__init__`" phrasing implies `__init__` exists, which contradicts Phase 0. | Rewrote §3 / §4: "single docstring + `pass`. **No** custom `__init__` (not even `super().__init__()`)." |
| K-7 | nit | `RepoAlreadyInProgress` lives in `sandbox/errors.py` per the story, but it's raised by the filesystem lock in `.codegenie/remediation/` (arch §Edge case 18) — arguably an orchestrator concern, not a sandbox concern. | Accepted as-written: the lock protects sandbox-side state, and Phase 5's lone consumer is `sandbox/health/probe.py` per arch §Component design. Not a contradiction; ledger comment added in Notes. |

### 2D · Design-patterns critic (verdict: PATTERNS-HARDEN)

| # | Severity | Finding | Fix applied |
|---|---|---|---|
| P-1 | harden | **Open/Closed contract under-specified.** The story creates the kernel that later stories extend, but did not explicitly state the extension shape ("add a subclass; never edit the base"). The risk is a future story noticing duplication and lifting a shared `__init__` onto the base. | Added "Extension-by-addition contract" subsection in Notes with two named extension points and the explicit forbid-list. |
| P-2 | nit | **No Strategy/Plugin/Registry premature abstraction.** Story keeps errors as bare markers and events as bare constants — correct by Rule 2 (three similar lines is better than premature abstraction). The temptation to introduce an `EventName` smart-constructor or a `register_error` decorator is explicitly resisted. | Added Notes section "Why these design-pattern choices" recording the deliberate non-abstraction and Phase 0's documented rationale for `Final[str]` over `StrEnum`. |
| P-3 | harden | **Primitive obsession risk on event names.** Phase 0 chose `Final[str]` (not `StrEnum`, not a newtype `EventName`) because Phase 13's cost ledger uses `type(x) is str`. Story originally didn't cite this — a future contributor would reasonably "fix" the primitive obsession with `StrEnum` and break the downstream destructure. | Added explicit "`Final[str]`, not `StrEnum`" rationale in Notes with the Phase-13 destructure citation. |
| P-4 | harden | **Anaemic-type risk on errors.** Story said "later stories may want to attach structured fields" — leaving the door open to a future migration to data-bearing errors (`Pydantic Error model` etc.). This would fork the codebase's load-bearing "behavior at catch site" pattern from Phase 0. | Closed the door in Notes: "structured context attaches at the catch site via structlog, not on the class." |
| P-5 | nit | **Make-illegal-states-unrepresentable** not directly applicable here (errors and event constants have no state to constrain). Story is correct to not invent state. | Recorded in Notes only ("Why these design-pattern choices"). |
| P-6 | harden | **Functional core / imperative shell** — the two `logging.py` modules are pure (constants only), the two `errors.py` modules are pure (classes only), the two `__init__.py` modules are pure (docstring only). AC-1's "no side effects" enforces the imperative-shell discipline at the package root. | Already enforced by AC-1 / AC-1a — no new edit. |
| P-7 | nit | **Newtype-pattern temptation.** A future contributor might propose `class EventName(str): pass` as a type-safety win. This would break the `type(x) is str` invariant. | Closed in Notes alongside P-3. |
| P-8 | accepted | **No registry pattern needed yet.** Two error packages + two event modules is below the rule-of-three threshold for extraction. Phase 0 has `src/codegenie/errors.py` + `src/codegenie/logging.py`; this story adds 2+2=4 sibling files; still no shared kernel needed. | No change. |

## Stage 3 — Researcher

**Skipped.** No critic finding was tagged `NEEDS RESEARCH`. Every gap was answerable from existing Phase 0 codebase precedent (`src/codegenie/errors.py`, `src/codegenie/logging.py`) plus the phase-05 ADRs and `phase-arch-design.md`.

## Stage 4 — Synthesizer + Editor

Conflict resolution priority `Consistency > Coverage > Test-Quality > Design-Patterns`:

- No real conflicts. The `EVT_*` → `EVENT_*` rename (Consistency K-1) and the value-pinning (Coverage C-2) compose cleanly.
- Design-Patterns P-3/P-4 (close the door on `StrEnum` / data-bearing errors) align with Coverage (don't introduce structure beyond what arch motivates) and Consistency (Phase 0 precedent).
- One implicit conflict resolved silently: Coverage wanted "AC for module docstrings"; Design-Patterns considered this nit-tier and Consistency had no opinion. Resolved as: docstring is in Refactor (already present in original), not promoted to AC. (Rule 2 — don't promote nice-to-haves into hard constraints.)

### Edits applied to story (summary)

1. **Validation notes block** — added under header summarizing the 9 substantive edits.
2. **Canonical event-name table** — new section pinning 10 constants → exact dotted-lowercase values, with arch/ADR provenance per row.
3. **ACs rewritten** — 6 original ACs expanded to 14 numbered, individually-verifiable criteria (AC-1, AC-1a, AC-2, AC-3, AC-4, AC-4a, AC-4b, AC-4c, AC-5, AC-6, AC-7, AC-8, AC-9). Each AC names what it locks.
4. **TDD plan tests rewritten** — original 6 tests → 24 parametrized + structural tests. Each names the AC it covers. Mutation-resistance matrix in this report shows what each catches.
5. **Implementation outline §3 / §4** — clarified "bare marker; no `__init__` at all" matching Phase 0.
6. **Refactor section** — narrowed (since most behaviors moved up to ACs; Refactor is now polish-only).
7. **Notes for implementer** — restructured into four explicit subsections (naming conventions, extension-by-addition contract, anti-speculation, design-pattern rationale, common pitfalls).

### Files / artifacts produced by this validation

- Edited: `docs/phases/05-sandbox-trust-gates/stories/S1-01-scaffold-packages-errors-structlog.md`
- Written: this report

## Final verdict

**HARDENED.** The story is now ready for `phase-story-executor`. The Validator pass will be able to verify every AC against observable runtime / static evidence; no AC is a refactor-step or qualitative statement. The mutation-resistance matrix above shows the TDD plan would catch 9/10 plausible wrong implementations (M-9 — phantom constant — is enforced socially per Rule 2, not by test).

## Sources consulted

- Story: `docs/phases/05-sandbox-trust-gates/stories/S1-01-scaffold-packages-errors-structlog.md`
- Phase arch: `docs/phases/05-sandbox-trust-gates/phase-arch-design.md` §Harness engineering, §Tracing strategy, §Decision points, §Edge cases, §Gap 1
- Phase ADRs: 0001 (two-chokepoint sandbox seam), 0006 (Protocol-vs-ABC convention), 0007 (pre-execute marker for resume safety), 0008 (LLM Judge persona deferral), 0012 (postinstall-exfil audit)
- Phase impl plan: `docs/phases/05-sandbox-trust-gates/High-level-impl.md` §Step 1
- Phase 0 precedent: `src/codegenie/errors.py`, `src/codegenie/logging.py`
- Phase 1+ consumers of `EVENT_*`: `src/codegenie/parsers/{_io,_depth,jsonc}.py`, `src/codegenie/probes/{deployment,language_detection,ci,test_inventory,node_build_system,node_manifest}.py`, `src/codegenie/probes/layer_b/index_health.py`
- Phase 2 prior validation precedent: `docs/phases/02-context-gather-layers-b-g/stories/_validation/S1-01-index-freshness-sum-type.md` (report shape + verdict vocabulary)
- CLAUDE.md (project + global Rule 11, Rule 2, Rule 9)
