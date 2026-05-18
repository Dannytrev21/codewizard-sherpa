# Validation report — S1-04 Transform ABC + ApplyContext + provenance

**Story:** [`../S1-04-transform-abc-apply-context.md`](../S1-04-transform-abc-apply-context.md)
**Validated:** 2026-05-18
**Validator:** phase-story-validator (scheduled task: `story-validation-corrector`)
**Verdict:** **HARDENED**

## Summary

S1-04 lands the Phase-3 contract-surface shapes `Transform` (ABC), `TransformProvenance`, `ApplyContext`, and `AttemptSummary` — every one consumed by Phase 5 by exact identifier (ADR-0001). Once shipped, the contract-snapshot test (S6-06) byte-pins these symbols and any drift breaks Phase 5's `GateRunner` wrap target. The original draft had the right scope but missed three load-bearing details (one block-tier, two harden-tier) and prescribed an implementation shape that would create churn at the S4-04 / S4-05 substitution boundary.

- **One block-tier consistency issue** (story drifts from `phase-arch-design.md §Data model L800-806`):
  - **`TransformProvenance.capability_use_id: EventId` missing.** Arch L806 ships it; ADR-0011 names it as the **audit anchor** that ties a Transform to its `CapabilityUsed` event in the two-stream event log. Without it, ADR-0011's "audit + lint" framing has no per-Transform anchor and the Phase-9 replay-consistency property is unprovable. Promoted to AC-2 with seven mandatory fields enumerated.
- **One block-tier test-quality issue** (mutation-resistance gap under Rule 9):
  - **UTF-8 bytes cap untested with multi-byte payloads.** The original test `"x" * 8193` only covers ASCII; a mutation `len(s) <= 8192` (chars, not bytes) passes this test silently. A 4-byte emoji × 2049 = 8196 bytes is the right adversarial fixture. Promoted to a parametrized AC-7c with four cases including 8192/8193 bytes via emoji.
- **One block-tier test-quality issue** (red-test not valid Python):
  - **`capabilities=...` ellipsis in red-test code.** `Ellipsis` is not a valid Pydantic value; the test cannot transition from red to green because the red is `TypeError` from Pydantic, not the intended `ModuleNotFoundError`. Same shape as S1-03 T-F8 closure. Rewritten with concrete fixture constructors.
- **Design-patterns harden-tier closures**:
  - **Placeholder strategy creates removal churn.** Original prescribed `CapabilityBundle` with a `_placeholder: bool = True` field that S4-05 must remove. Replaced with an empty Pydantic shell (`pass` body + `extra="forbid"`). S4-05 *adds* fields without removing anything; no `model_rebuild()` dance. Phase-boundary stable contract / extension-by-addition (ADR-0001 §Pattern fit).
  - **List immutability under `frozen=True`.** Pydantic v2's `frozen=True` freezes attribute reassignment but does NOT block `ctx.prior_attempts.append(x)`. Switched to `tuple[AttemptSummary, ...] = ()` for true immutability. Same for `failing_signals: tuple[SignalKind, ...]` and `evidence_paths: tuple[SandboxedPath, ...]`. Phase 5 ADR-P5-002 documents the immutable-update idiom: `ctx.model_copy(update={"prior_attempts": old + (new,)})`. "Make illegal states unrepresentable" — ADR-0010 §Pattern fit.
  - **ABC pattern precedent.** Original AC-1 wavered between `@property @abstractmethod` and class-level annotations. `src/codegenie/probes/base.py`'s `Probe(ABC)` uses **class-level type annotations** (not abstract properties); pinned to mirror that precedent. CLAUDE.md "Match the codebase's conventions" + Rule 11.
- **Harden-tier closures** mirrored from S1-03's validation:
  - **`applied_at` naive-datetime rejection** — `field_validator` raises on `tz is None`; new AC-2a + test.
  - **NUL / control / bidi rejection on `prior_failure_summary`** — E20 closure; promoted from Refactor §137 prose to AC-3 / AC-7d with parametrized adversarial test.
  - **`plugin_version` / `recipe_version` regex validator** — arch references `SemverVersion` (L803-804) but S1-01 doesn't ship that newtype. Pragmatic boundary defence: `^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][\w.-]+)?$` regex via `field_validator`. Document the arch-drift in Notes; do not introduce a newtype here (S1-01 scope).
  - **`transform_kind: TransformKind` newtype** — pinned in AC-2 (was implicit before).
  - **Module-purity fence** — `transform.py`, `apply_context.py`, `_forward.py` imports restricted to a known set; AST source-scan test mirrors S1-01 / S1-03 fence pattern. AC-6a.
  - **`model_construct` absence** — bypass-validation hole; source-scan absence. AC-6b.
  - **`__all__` exact-set pinning** — ADR-0001 §Consequences pins the re-export list (6 symbols at Phase-3-Step-1). AC-6.
  - **JSON-shape pinning on `TransformProvenance`** — catches symmetric `key`→`renamed_key` regressions that round-trip-stable. AC-7j.
  - **Round-trip preserves concrete type** — `type(parsed) is type(m)` across all three Pydantic models. AC-7b.
  - **Parametrized `frozen=True` + `extra="forbid"` over every field of every model.** AC-7e / AC-7f.

Stage 3 research **skipped** — every closure is answerable from arch (§Data model L800-830) + ADR-0001 + ADR-0010 + ADR-0011 + the S1-03 validation precedent + the `src/codegenie/probes/base.py` ABC precedent + Pydantic v2 docs on `frozen=True` semantics + tuple/list immutability semantics.

## Context Brief (Stage 1)

### Story snapshot
- **Goal (verbatim):** Land `src/codegenie/transforms/transform.py` (ABC + `TransformProvenance`) and `src/codegenie/transforms/apply_context.py` (`ApplyContext` + `AttemptSummary`) with the Phase-3-final shapes ADR-0001 commits to — including `prior_attempts: list[AttemptSummary] = Field(default_factory=list)` shipped already so Phase 5's amendment is a behavior-only change.
- **Non-goals (from Out of scope):** Concrete `NpmLockfileTransform` / `DockerfileBaseImageTransform` (S5-02 / S5-03); `CapabilityBundle` real fields (S4-05); `SandboxedPath` real type (S4-04); `RecipeEngine` Protocol (S5-01); `RemediationOrchestrator._validate_stage6` method (S6-04); the contract-snapshot test itself (S6-06).

### Goal-to-AC trace (pre-hardening)
- AC-1 (Transform ABC) → goal: YES, but PARTIAL — pattern (annotations vs property/abstractmethod) ambiguous; `list[SandboxedPath]` is mutable
- AC-2 (TransformProvenance) → goal: WEAK — **drifts from arch L800-806**: missing `capability_use_id: EventId`; `plugin_version`/`recipe_version` typed `str` while arch says `SemverVersion`
- AC-3 (AttemptSummary) → goal: PARTIAL — `len(s) ≤ 8192` ambiguous (chars vs bytes); NUL/control/bidi rejection from Refactor §137 not in AC; `list` mutability gap
- AC-4 (ApplyContext) → goal: PARTIAL — `list[AttemptSummary]` mutability gap; placeholder `CapabilityBundle` strategy creates S4-05 churn
- AC-5 (SandboxedPath forward-ref) → goal: PARTIAL — strategy ambiguous; consider `_PathPlaceholder` vs `TypeAlias = Path`
- AC-6 (`test_apply_context.py`) → goal: WEAK — round-trip not parametrized over all models; UTF-8 bytes cap untested with multi-byte; mutation rejection vague
- AC-7 (`test_transform_abc.py`) → goal: PARTIAL — subclass-required-attribute enforcement not asserted; FakeTransform fixture not concrete in TDD plan
- AC-8 / AC-9 / AC-10 → bar-ACs

### Phase / arch constraints
- **ADR-0001 §Decision §C** — names exactly `apply_context.py` and `transform.py`; ships `prior_attempts: list[AttemptSummary] = Field(default_factory=list)`. Contract-snapshot test (S6-06) byte-pins.
- **ADR-0001 §Consequences** — `Transform`, `ApplyContext` re-exported from `codegenie.transforms.__init__`; fence test asserts export list.
- **ADR-0010 §Decision §4** — `extra="forbid"` + `frozen=True` on every Pydantic model; `prior_failure_summary` truncated to 8 KB canary-checked downstream. Make illegal states unrepresentable.
- **ADR-0011 §Decision §Capability tokens + §Consequences L78-80** — `capability_use_id: EventId` is the audit anchor. Phase 5's gate policy can read `CapabilityUsed` events to enforce per-workflow capability budgets — the audit trail is the substrate.
- **Arch §Component design C4 L516-538** — `Transform` ABC fields verbatim; `transform_id: TransformId  # blake3(diff_bytes)` (subclass invariant; not enforceable at ABC).
- **Arch §Component design C5 L541-561** — `AttemptSummary` and `ApplyContext` field-for-field; `prior_attempts: list[AttemptSummary] = Field(default_factory=list)`.
- **Arch §Data model L793-814** — `TransformProvenance` Pydantic model with 7 fields: `plugin_id, plugin_version: SemverVersion, recipe_id, recipe_version: SemverVersion, applied_at: datetime, capability_use_id: EventId`.
- **CLAUDE.md "Extension by addition"** — `Transform` ABC closed for modification; subclasses are open extension points. The contract-snapshot test catches any drift.
- **CLAUDE.md "Match the codebase's conventions"** — Rule 11; the `Probe(ABC)` precedent at `src/codegenie/probes/base.py` is the convention to mirror.
- **CLAUDE.md "No LLM anywhere in the gather pipeline" + import-linter** — `transforms/` is Phase 3 contract surface; module-purity invariant.

### Phase 3 Step-1 exit criteria the story must contribute to
(from `High-level-impl.md §Step 1 Done criteria` lines 36–42)
- [ ] `mypy --strict src/codegenie/plugins src/codegenie/transforms` clean — S1-04 contributes `transforms/transform.py` + `transforms/apply_context.py` + `transforms/_forward.py`.
- [ ] `tests/fence/test_no_any_in_plugin_surface.py` — S1-04 must not introduce `dict[str, Any]`.
- [ ] `tests/fence/test_no_llm_in_transforms.py` — S1-04's modules must not pull LLM SDKs.

### Sibling-family lineage (Design-Patterns critic)
- **This is the 3rd ABC family** in the repo (after `Probe(ABC)` in `probes/base.py`, `Stream(ABC)` is hypothetical — Phase 0 only ships one ABC). For the Phase-3 contract namespace, this is the 1st ABC. The `Probe(ABC)` precedent dictates: class-level type annotations + `@abstractmethod` on methods (not properties). Rule-of-three NOT-YET-REACHED for ABC kernel extraction; subclassing is the established extension pattern.
- **Closest precedent for *this* story:** `src/codegenie/probes/base.py` (ABC with class-level annotations + abstract `run`). Mirror imports, structure, docstring convention.
- **Pydantic contract-surface precedent:** S1-03 (`outcomes.py`) + S1-01 (`identifiers.py` parsers). Mirror: `model_config = ConfigDict(frozen=True, extra="forbid")`; `field_validator` for boundary defence; `__all__` exact-set; module-purity AST fence; `model_construct` absence.
- **Tuple vs list immutability:** the closest repo precedent for `tuple[..., ...] = ()` as a frozen container has not yet been established (Phase 3 is the introduction point). Pin the convention here; future Phase 3+ stories follow.

### Open ambiguities resolved before Stage 2
- **`SemverVersion` newtype vs `str`.** Arch L803-804 references `SemverVersion`. S1-01 (`docs/phases/03-vuln-deterministic-recipe/stories/S1-01-phase3-newtype-identifiers.md`) lists 14 Phase-3 newtypes; `SemverVersion` is NOT among them. Resolution: ship `str` with a `field_validator` regex; document the arch-drift; do NOT introduce a new newtype here (scope creep — S1-01 amendment territory).
- **ABC pattern (annotations vs `@property @abstractmethod`).** Repo precedent (`probes/base.py`) uses class-level annotations on dataclass `Probe(ABC)`. Pin annotations.
- **List vs tuple for `prior_attempts` / `failing_signals` / `evidence_paths`.** Pydantic v2 `frozen=True` does not block list mutation. Tuple is the immutable choice. Phase 5 ADR-P5-002's update pattern (`model_copy(update=...)`) works identically for tuple; the tuple form makes the invariant unforgeable.
- **`CapabilityBundle` placeholder shape.** Original `_placeholder: bool = True` field creates removal churn at S4-05. Cleaner: empty Pydantic shell with `pass` body — Pydantic v2 accepts empty models; S4-05 *adds* fields with no need to remove or `model_rebuild()`.
- **`SandboxedPath` placeholder.** `TypeAlias = pathlib.Path` in `_forward.py` is the cleanest substrate; S4-04 replaces the alias with a re-export from `plugins/sandbox_path.py`; every import site stays stable.
- **Forward-ref module direction.** `transforms/_forward.py` is the only Phase-3-Step-1 substrate; `_forward.py` imports nothing from `codegenie.plugins.*`. S4-04 / S4-05 amend additively (re-exports replace placeholders).

### Adjacent test / production code
- `src/codegenie/probes/base.py` — closest precedent (ABC with class-level annotations + Pydantic-adjacent dataclasses). Mirror.
- `src/codegenie/output/sanitizer.py` — Pydantic `extra="forbid"` + `frozen=True` precedent. Mirror `model_config = ConfigDict(...)` shape.
- `src/codegenie/types/identifiers.py` — Phase 0/1/2 newtypes + the S1-01 Phase-3 amendment.
- `tests/unit/test_probe_contract.py` — pattern for byte-pinning a contract surface (S6-06 will mirror).

## Stage 2 — critic reports

### Coverage critic (verdict: COVERAGE-HARDEN — 8 findings, 1 block)

| ID | Sev | Finding | Closure |
|---|---|---|---|
| C-F1 | **block** | `TransformProvenance.capability_use_id: EventId` missing. Arch §Data model L800-806 ships it; ADR-0011 names it as the Capability audit anchor. Without it, Phase 5's `CapabilityUsed`-to-`Transform` audit linkage is broken and ADR-0011's framing has no per-Transform anchor. | Promote to AC-2 with seven-field enumeration. |
| C-F2 | harden | `applied_at` UTC timezone-awareness not testable from current AC set. Story says "validate tz is not None" in Notes but no AC enforces it. | New AC-2a + parametrized rejection test. |
| C-F3 | harden | `plugin_version` / `recipe_version: str` accept arbitrary garbage. Arch references `SemverVersion` (which S1-01 doesn't ship). | `field_validator` regex `^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][\w.-]+)?$`; document arch-drift in Notes. |
| C-F4 | harden | `prior_failure_summary` NUL/control/bidi rejection mentioned in Refactor §137 but no AC. E20 closure. | Promote to AC-3 + AC-7d. |
| C-F5 | harden | `prior_attempts` / `failing_signals` / `evidence_paths` are `list[...]` — `frozen=True` doesn't block `list.append()`. | Switch to `tuple[..., ...] = ()`; AC-7g asserts tuple-not-list at runtime. |
| C-F6 | harden | "isinstance(t, Transform) is True" tests ABC plumbing, not subclass-required-attribute enforcement. | New AC-8c — subclass omitting attributes either fails mypy or fails attribute access. |
| C-F7 | nit | `Transform.transform_id == blake3(diff_bytes)` invariant (arch C4 L522) is subclass-level, not ABC-level. Out-of-scope at ABC; note in docstring. | Notes only. |
| C-F8 | nit | `FakeTransform` "with all four fields" — but attributes are class vars (annotations), not init kwargs. AC mis-states. | Rewrite AC-8b/8c with the correct subclass-fixture shape. |

### Test-quality critic (verdict: TEST-HARDEN — 10 findings, 2 block)

| ID | Sev | Finding | Closure |
|---|---|---|---|
| T-F1 | **block** | TDD red-test uses `capabilities=...` (ellipsis = `Ellipsis`) — fails Pydantic validation; not a valid red→green starting point. Mirrors S1-03 T-F8. | Rewrite with concrete fixture constructors. |
| T-F2 | **block** | UTF-8 bytes cap untested with multi-byte payloads. `"x" * 8193` doesn't catch a `len(s)` regression. Need parametrized fixture: `[("x" * 8192, "accept"), ("x" * 8193, "reject"), ("💀" * 2048, "accept"  # 8192 bytes), ("💀" * 2049, "reject"  # 8196 bytes)]`. | AC-7c with parametrized verdict matrix. |
| T-F3 | harden | Round-trip via `model_dump_json` → `model_validate_json` tested on one model only; need parametrization over all three Pydantic models. | AC-7b parametrized + `type(parsed) is type(m)` assertion. |
| T-F4 | harden | Mutation rejection tested on `workflow_id` only; parametrize over every field of every model. | AC-7f parametrized. |
| T-F5 | harden | Tuple-not-list invariant untested — `ctx.prior_attempts.append(x)` either succeeds (bug) or raises (correct). | AC-7g + `isinstance(ctx.prior_attempts, tuple)` + `AttributeError` on `.append`. |
| T-F6 | harden | `applied_at` naive-datetime rejection not in TDD plan. | AC-7h test. |
| T-F7 | harden | Round-trip-preserves-type assertion missing — `type(parsed) is type(m)`. Mutation: a shape change that loses `datetime` and recovers as `str` slips past round-trip alone. | AC-7b covers. |
| T-F8 | harden | JSON-shape pinning on `TransformProvenance` missing — symmetric `key`→`renamed_key` regression slips past round-trip. Mirrors S1-03 T-F2. | AC-7j enumerates the seven keys. |
| T-F9 | harden | `extra="forbid"` tested implicitly; need parametrization over every model × one extra field. | AC-7e parametrized. |
| T-F10 | nit | `test_transform_abc.py` import block missing in TDD code. | Rewritten with full import block. |

### Consistency critic (verdict: CONSISTENCY-HARDEN — 6 findings, 0 block (1 already promoted by Coverage))

| ID | Sev | Finding | Closure |
|---|---|---|---|
| X-F1 | (Coverage C-F1) | `capability_use_id: EventId` missing — duplicate. | Same closure. |
| X-F2 | (Coverage C-F3) | `SemverVersion` arch-drift — duplicate. | Same closure. |
| X-F3 | harden | `__all__` exact-set not pinned for `transforms/__init__.py`. ADR-0001 §Consequences pins re-export list (6 symbols at Step-1). S1-03 closed the same gap. | AC-6 with exact set enumerated. |
| X-F4 | harden | Module-purity fence missing — `transform.py`, `apply_context.py`, `_forward.py` are contract-surface kernel; imports must be limited to a known set. Same closure as S1-01 / S1-03. | AC-6a; AST source-scan test mirrors `test_freshness_module_purity.py`. |
| X-F5 | harden | `model_construct` discipline unasserted — bypass-validation hole. | AC-6b source-scan absence. |
| X-F6 | harden | ABC pattern ambiguity — original AC-1 wavered between `@property @abstractmethod` and class-level annotations. Repo precedent (`probes/base.py`) uses annotations. Rule 11 / "Match the codebase's conventions." | AC-1 pinned to class-level annotations; precedent named explicitly. |

### Design-patterns critic (verdict: DP-HARDEN — 5 findings, 0 block)

| ID | Sev | Finding | Closure |
|---|---|---|---|
| D-F1 | harden | Placeholder strategy with `_placeholder: bool = True` creates S4-05 cleanup churn (remove field + `model_rebuild()`). Cleaner: empty Pydantic shell (`pass` body + `extra="forbid"`). S4-05 *adds* fields; no removal. Phase-boundary stable contract / extension-by-addition. | AC-5 rewritten. |
| D-F2 | harden | `SandboxedPath` shim direction. `_forward.py` adapter/facade with `TypeAlias = Path` (runtime) is the cleanest substrate; S4-04 re-exports through the same module so every import site stays stable. | AC-5a + AC-5b. |
| D-F3 | harden | Pydantic v2 `frozen=True` ≠ container immutability. Switch to `tuple` for true immutability — Phase 5's `model_copy(update={"prior_attempts": old + (new,)})` idiom works identically for tuple. "Make illegal states unrepresentable" — ADR-0010 §Pattern fit. | AC-3 / AC-4 + AC-7g. |
| D-F4 | harden | ABC pattern conflict — `@property @abstractmethod` vs class-level annotations. The `Probe(ABC)` precedent uses class-level annotations. Pick precedent. | AC-1 pinned. |
| D-F5 | nit | Extension-by-addition rule-of-three NOT YET REACHED for the `Transform` ABC family — S5-02 / S5-03 ship subclasses; Phase 4 / Phase 7 add more. The ABC pattern itself is the extension substrate. | Notes-for-implementer paragraph on extension. |

## Stage 4 — synthesis & edits applied

The story has the right scope and intent, but:
1. Drifts from arch on one load-bearing field (`TransformProvenance.capability_use_id`) — block-tier consistency.
2. Underspecifies tests in ways that admit symmetric-mutation regressions (UTF-8 bytes cap; ellipsis red-test) — block-tier test-quality.
3. Prescribes implementation shapes that create S4-04 / S4-05 churn (placeholder field; ABC-pattern ambiguity) — harden-tier design-patterns.
4. Misses the repo-uniform conventions for contract-surface modules (`__all__` exact-set, module-purity fence, `model_construct` absence) — harden-tier consistency.
5. Uses `list` containers that don't enforce immutability under `frozen=True` — harden-tier design-patterns + test-quality.

**Edits applied to the story file** (see `git diff` for the authoritative record):

- **Status:** `Ready` → `HARDENED`.
- **Validation notes block** added under the header naming this report.
- **Depends-on line** widened to include `TransformKind`, `EventId` newtypes (the latter to support the `capability_use_id` block fix).
- **ADRs honored** widened to call out ADR-0011's Capability audit-anchor framing.
- **Acceptance criteria** restructured into eleven labelled ACs grouped by concern:
  - AC-1 / AC-1a — Transform ABC pattern + subclass-required-attribute enforcement.
  - AC-2 — TransformProvenance seven fields (added `capability_use_id`).
  - AC-2a — `applied_at` UTC enforcement.
  - AC-3 — AttemptSummary with tuple containers + UTF-8 bytes cap + NUL/control/bidi rejection.
  - AC-4 — ApplyContext with `tuple[AttemptSummary, ...] = ()`.
  - AC-5 — Empty `CapabilityBundle` shell (NO `_placeholder` field).
  - AC-5a — `SandboxedPath: TypeAlias = Path` shim.
  - AC-5b — `_forward.py` module purity.
  - AC-6 — `__all__` exact-set with six symbols.
  - AC-6a — Module-purity AST fence.
  - AC-6b — `model_construct` absence source-scan.
  - AC-7 (a–j) — `test_apply_context.py` parametrized suite: defaults, round-trip-with-type, UTF-8 bytes cap with emoji fixture, NUL/control/bidi rejection, extra-forbid, frozen, tuple-not-list, naive-datetime rejection, semver regex, JSON-shape pinning.
  - AC-8 (a–d) — `test_transform_abc.py`: ABC instantiation `TypeError`, subclass with-all-attributes works, subclass omitting attributes fails, `isinstance` check.
  - AC-9 / AC-10 / AC-11 — mypy strict / ruff / TDD red-test (concrete fixtures).
- **Implementation outline** restructured to six steps reflecting the `_forward.py` shim module, the class-level annotation ABC pattern, the seven-field provenance, the tuple containers, and the contract-surface fences.
- **TDD plan** — red-test rewritten in valid Python with concrete fixture constructors (`_empty_caps()`, `_provenance()` helpers); refactor §expanded with bytes-cap, NUL/bidi, naive-datetime, semver-regex, and `list→tuple` coercion validators.
- **Files to touch** — added `src/codegenie/transforms/_forward.py` (NEW) and `tests/fence/test_transforms_module_purity.py` (NEW); existing `transform.py` / `apply_context.py` / `__init__.py` / `test_apply_context.py` / `test_transform_abc.py` widened.
- **Notes for the implementer** — added paragraphs on: tuple-not-list rationale and `model_copy(update=...)` idiom; ABC pattern precedent (`probes/base.py`); `capability_use_id` load-bearing rationale (ADR-0011 audit anchor); semver-regex pragmatic substitute for `SemverVersion`; empty `CapabilityBundle` shell vs `_placeholder` field; `_forward.py` shim direction; NUL/control/bidi adversarial cases; UTF-8 bytes semantics; extension-by-addition substrate; contract-snapshot test as the gate.

**Final verdict: HARDENED.** Story is ready for the executor with one block-tier consistency issue closed (`capability_use_id`), two block-tier test-quality regressions pinned (UTF-8 bytes cap; ellipsis red-test), and the repo-uniform contract-surface conventions (immutable tuples, ABC pattern precedent, module purity, `__all__` exact-set, `model_construct` absence, JSON-shape pinning) fenced.
