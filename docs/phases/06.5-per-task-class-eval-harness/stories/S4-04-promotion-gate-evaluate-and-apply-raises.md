# Story S4-04 — `PromotionGate.evaluate` (all-conditions) + `apply()` raises unconditionally

**Step:** Step 4 — Wire the CLI and the read-only promotion gate
**Status:** HARDENED (phase-story-validator, 2026-06-01)
**Effort:** M
**Depends on:** S1-01 (typed errors — `IncompleteReportForPromotion`, `PromotionMustBeHumanAuthorized`, `TierConfigInvalid`, `TaskClassNotFound`; marker-only positional discipline — args land on `.args`, raisers own the tuple shape), S1-02 (wire models — `BenchRunReport` with eight required fields incl. `complete: bool`, `isolation_class: Literal[...]`; `PromotionVerdict` with eight required fields incl. `requires_human_approval: Literal[True]` no-default), S1-03 (`TaskClass` dataclass with `min_cases_for_promotion: Mapping[str, int]`, `failure_mode_taxonomy: Mapping[str, Literal[...]]`, `MappingProxyType`-normalized; `TaskClassRegistry` with `get(name)` raising `TaskClassNotFound`), S2-04 (`audit.verify(out_dir) -> VerifyResult(ok, verified_complete, verified_incomplete, tampered_path, reason)` — returns, never raises)
**ADRs honored:** ADR-0002 (gate keys on `lower_bound_95`), ADR-0003 (tier IDs as `str`, validated at startup against `docs/trust-tiers.yaml`), ADR-0004 (`block`-severity failure modes are data, not free-text), ADR-0009 (automatic-demotion is recommendation-shift), ADR-0010 (`isolation_class` homogeneous across evidence window; canonical reason format `"isolation_class mismatch in evidence window: subprocess={N1}, microvm={N2}"`), Phase 5 ADR-0016 (eval-harness-as-trust-evidence), Production ADR-0009 (humans always merge → `apply()` raises), Production ADR-0015 (calibration ADR named in the apply message)

## Validation notes

Validated: 2026-06-01
Verdict: HARDENED
Findings addressed: 47 total — 17 block, 22 harden, 8 nit

Conflict-resolution priority applied: **Consistency > Coverage > Test-Quality > Design-Patterns**. The dominant lens was Consistency — the story as written drifted from contracts hardened *after* it was authored:

- **`tamper_at` → `tampered_path`** everywhere (Consistency F-CON-1 / F-CON-2; S2-04 `VerifyResult.tampered_path: Path | None` is the canonical field; the S4-03 validation report flagged this carrying into S4-04).
- **`evaluate(report, target_tier, *, evidence_window=())`** — the signature no longer carries `task_class`; the gate resolves it internally via the constructor-injected `TaskClassRegistry` (Consistency F-CON-3; matches S4-02 HARDENED call site `gate.evaluate(report, target_tier)`). Phase-arch lines 187/639 carry two stale signatures; flagged for a doc-sweep PR.
- **`PromotionVerdict` construction made explicit** — all eight required fields populated, `requires_human_approval=True` written verbatim (Consistency F-CON-4 + Coverage F-COV-1 / F-COV-10; S1-02 AC-7a no-default discipline).
- **Isolation reason format** aligned to ADR-0010 §Decision exact text `"isolation_class mismatch in evidence window: subprocess={N1}, microvm={N2}"` (Consistency F-CON-5 + Coverage F-COV-13; three drifting variants collapsed to one).
- **`apply` signature** unified to the open `*args/**kwargs` form (Consistency F-CON-8 + Design-Patterns F-DP-8; the narrow `verdict: PromotionVerdict | None = None` form was a story-internal contradiction and a weaker fence).
- **`audit_verify` injection** promoted to AC; the default resolves via a module-top deferred-import wrapper so `promotion.py` carries zero heavy module-top imports (Design-Patterns F-DP-9 + Coverage F-COV-17; mirrors S4-03 cold-start discipline).
- **`load_tier_config` relocated** from `promotion.py` to a new `src/codegenie/eval/tier_config.py` (Design-Patterns F-DP-3; functional-core / imperative-shell — the gate is pure, the loader is I/O).
- **Six conditions are five** — condition #5 (`complete is True`) is unreachable from `evaluate` because the gate raises `IncompleteReportForPromotion` first; renumbered and the "fixture for #5" mutation-style AC is removed (Coverage F-COV-15).
- **Reasons order pinned** for byte-identical reruns (Coverage F-COV-8 + Test-Quality F-TQ-8 + F-TQ-13; ADR-0002 §Consequences "byte-identical across reruns" is load-bearing for audit reproducibility).
- **Happy-path `reasons == ("all conditions met",)`** pinned exactly (no `in ((), (...))` disjunction — Coverage F-COV-16 + Test-Quality F-TQ-2).
- **AST audit on `apply`** fixed (`textwrap.dedent`); extended to pin `len(body) == 1 and isinstance(body[0], ast.Raise)` so early-return mutants fail (Test-Quality F-TQ-5 / F-TQ-6).
- **Adversarial purity test for `evaluate`** added — symmetric to the `apply` AST fence (Design-Patterns F-DP-7).
- **`TierConfig` Mappings** normalized to `MappingProxyType` (Design-Patterns F-DP-5; mirrors S1-03 F-DP-5).
- **Boundary, ordering, property-based, metamorphic, spy-on-injection** tests added (Test-Quality F-TQ-4 / F-TQ-8 / F-TQ-11 / F-TQ-12 / F-TQ-13 + Coverage F-COV-11 / F-COV-12).
- **`BenchRunReport.model_construct` retired** in the helper — full validated construction so fixtures cannot diverge from runner output (Test-Quality F-TQ-1).

Full audit log: [`docs/phases/06.5-per-task-class-eval-harness/stories/_validation/S4-04-promotion-gate-evaluate-and-apply-raises.md`](_validation/S4-04-promotion-gate-evaluate-and-apply-raises.md)

## Context

`PromotionGate` is the read-only verdict surface. Phase 5 ADR-0016 §Decision §4 made "zero block-severity failure modes" a load-bearing precondition; ADR-0002 shifted the score signal from `mean` to `lower_bound_95`; Gap #4 added the `complete: bool` reject path (raise, not return); Gap #1 / ADR-0010 added the homogeneous-`isolation_class` precondition. Every one of these is a separate ADR amendment over the original synthesis; collapsing them into a single, structurally-enforced `evaluate(...)` is the load-bearing engineering work of this phase.

The gate's contract is two methods. `evaluate(report, target_tier, *, evidence_window=())` returns a `PromotionVerdict` with eight required fields. `apply(self, *args, **kwargs)` raises `PromotionMustBeHumanAuthorized` **unconditionally** — the interface exists as a discoverability marker; calling it is itself a finding (per `phase-arch-design.md §Tradeoffs (consolidated)`). The asymmetry is structural: there is no flag, no constructor parameter, no test fixture that lets `apply()` succeed. This is how "Humans always merge" (production ADR-0009) becomes load-bearing code, not aspirational prose.

`audit.verify(out_dir)` **returns** a `VerifyResult` on every code path — missing dir, empty dir, parse error, chain tamper (per S2-04 HARDENED AC-4). It does NOT raise. The gate must map `result.ok` and `result.tampered_path` / `result.reason` into the reasons tuple; it must NOT wrap the call in `try/except` (identical to the S4-03 F-CON-2 drift).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design → src/codegenie/eval/promotion.py` — class signature, the all-conditions enumeration, `reasons` discipline. (Lines 187 + 639 carry two stale signatures; ignore both; this story owns the signature contract.)
  - `../phase-arch-design.md §Data model → PromotionVerdict` (lines 797-808) — the eight required fields incl. `requires_human_approval: Literal[True]`, `lower_bound_95`, `threshold_at_target`.
  - `../phase-arch-design.md §Dynamic view → Sequence: 14-day silver-promotion candidate` — the day-15 verdict-flip walkthrough; the canonical happy-path verdict literal is `reasons=("all conditions met",)`.
  - `../phase-arch-design.md §Failure modes table` — rows for `IncompleteReportForPromotion` (Gap #4) and the homogeneous-`isolation_class` check (Gap #1).
  - `../phase-arch-design.md §Gap analysis Gap 1, Gap 4` — both gaps land their fix in this gate's evaluation logic.
  - `../phase-arch-design.md §Tradeoffs (consolidated)` — `apply()` raises unconditionally; "calling it is itself a finding."
- **Phase ADRs:**
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md` — `evidence_sufficient` keys on `report.lower_bound_95 >= tier_config.thresholds[target_tier]`, not `mean_score`. §Consequences pins the byte-identical-reruns invariant.
  - `../ADRs/0003-tier-identifiers-as-str-validated-at-startup.md` — `PromotionGate.__init__(tier_config)` validates tier names against `docs/trust-tiers.yaml`; unknown → `TierConfigInvalid(unknown_tier, available_tiers)`.
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md` — `report.block_severity_failure_modes` is `tuple[str, ...]` (deduplicated codes); non-empty → `evidence_sufficient=False` with one `reasons` entry per code, **emitted in `sorted(...)` order** for determinism.
  - `../ADRs/0009-automatic-demotion-as-recommendation-shift.md` — when a verdict implies demotion, the gate writes a recommendation (S4-05) but does not mutate state.
  - `../ADRs/0010-isolation-class-annotation-on-bench-run-report.md` §Decision — exact reason format: `"isolation_class mismatch in evidence window: subprocess={N1}, microvm={N2}"`.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` — the structural rationale `apply()` raises.
  - `../../../production/adrs/0015-trust-score-threshold-calibration.md` — the calibration ADR named in the `apply()` message (operators-facing escalation path).
- **Sibling stories (HARDENED):**
  - `S2-04-audit-chain-extension.md` AC-4 — `verify(out_dir) -> VerifyResult(ok, verified_complete, verified_incomplete, tampered_path, reason)`; returns, never raises.
  - `S1-02-wire-models-frozen-extra-forbid.md` AC-7 + AC-7a + AC-13 + AC-14 — `PromotionVerdict` shape; `requires_human_approval: Literal[True]` REQUIRED.
  - `S1-03-taskclass-dataclass-and-registry.md` AC-2 + AC-9 — `TaskClass` shape; `MappingProxyType` normalization; `TaskClassRegistry.get(name)` raises `TaskClassNotFound`.
  - `S1-01-typed-errors-module.md` AC-1 + AC-8 — nine markers; positional args land on `.args`; raisers own argument-tuple shape.
  - `S4-02-eval-run-subcommand.md` — the production call site: `gate.evaluate(report, target_tier)` (two positional args, no `task_class` kwarg).
- **Source design:** `../High-level-impl.md §Step 4` — names every condition in the all-conditions check explicitly.
- **Phase 5 ADR-0016:** `../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md` §Decision §4 — the parent ADR this gate operationalizes.

## Goal

Land `src/codegenie/eval/promotion.py` + `src/codegenie/eval/tier_config.py` such that `PromotionGate(tier_config, registry, *, audit_verify=None)`'s `evaluate(report, target_tier, *, evidence_window=())` returns a fully-populated `PromotionVerdict` with `evidence_sufficient=True` iff ALL five verdict conditions pass, enumerates each failing condition in `reasons` in a pinned deterministic order, raises `IncompleteReportForPromotion(report.run_id)` on `report.complete=False`, raises `TierConfigInvalid` on unknown-tier / unknown-task-class targets, raises `TaskClassNotFound` on unknown `report.task_class`, and whose `apply(*args, **kwargs)` always raises `PromotionMustBeHumanAuthorized` with a message naming `docs/trust-tiers.yaml`, the CODEOWNERS gate, and production ADR-0015.

## Acceptance criteria

### Loader + `TierConfig` (functional-core / imperative-shell separation — Design-Patterns F-DP-3)

- [ ] **AC-1.** `src/codegenie/eval/tier_config.py` defines:
  - `TierConfig` as `@dataclass(frozen=True, slots=True)` with `thresholds: Mapping[str, float]` and `current_tiers: Mapping[str, str]`.
  - `TierConfig.__post_init__` wraps both fields via `object.__setattr__(self, "<name>", types.MappingProxyType(dict(<value>)))` so a held reference to the inner dict cannot mutate the gate's view (mirrors S1-03 AC-9; Design-Patterns F-DP-5).
  - `load_tier_config(path: Path) -> TierConfig` reads `docs/trust-tiers.yaml` and returns a `TierConfig`. The loader lives here, **not** in `promotion.py`, so the gate module carries zero `pyyaml` import.
- [ ] **AC-1a.** `TierConfig.thresholds` and `TierConfig.current_tiers` are runtime-immutable: `tc.thresholds["silver"] = 0.95` raises `TypeError` (`MappingProxyType` does not support `__setitem__`). Verified by a test.

### `PromotionGate.__init__` (signature pin + startup validation — Coverage F-COV-17)

- [ ] **AC-2.** `PromotionGate.__init__(tier_config: TierConfig, registry: TaskClassRegistry | None = None, *, audit_verify: Callable[[Path], VerifyResult] | None = None)`. `registry` defaults to `codegenie.eval.registry.default_registry`. `audit_verify` is **keyword-only**; defaults to a module-top `_default_audit_verify` wrapper that imports `codegenie.eval.audit.verify` **inside the function body** (Design-Patterns F-DP-9 — `promotion.py` must not carry a module-top `from codegenie.eval.audit import verify`).
- [ ] **AC-2a.** Cold-start fence: after `import codegenie.eval.promotion`, `codegenie.eval.audit` is NOT in `sys.modules` and `pyyaml` is NOT in `sys.modules`. Pinned by `tests/fence/test_promotion_cold_start.py`. (Mirrors S4-01's cold-start discipline.)
- [ ] **AC-3.** Startup tier validation (per ADR-0003): at `__init__`, the gate asserts that every tier name in `tier_config.thresholds.keys()`, every value in `tier_config.current_tiers.values()`, and every key in every `TaskClass.min_cases_for_promotion` registered in `registry.all_task_classes()` is a member of `set(tier_config.thresholds.keys())` (the YAML-declared tier set). Unknown tier → `TierConfigInvalid(unknown_tier, available_tiers)` raised positionally where:
  - `unknown_tier: str` — the offending tier name.
  - `available_tiers: tuple[str, ...]` — `tuple(sorted(tier_config.thresholds.keys()))` (deterministic for operator "did you mean" diagnostics).
  - `exc.args == (unknown_tier, available_tiers)` (the marker class is positional-only — S1-01 AC-8); `str(exc)` includes both the unknown tier and the sorted available set.

### `PromotionGate.evaluate` — signature, errors, conditions, verdict (Consistency F-CON-3 / F-CON-4 + Coverage F-COV-1 / F-COV-2 / F-COV-3 / F-COV-4 / F-COV-5 + Design-Patterns F-DP-4)

- [ ] **AC-4.** Signature: `PromotionGate.evaluate(self, report: BenchRunReport, target_tier: str, *, evidence_window: tuple[BenchRunReport, ...] = ()) -> PromotionVerdict`. **No** `task_class` parameter (the gate resolves it internally via the constructor-injected registry — matches S4-02 HARDENED call site `gate.evaluate(report, target_tier)`).
- [ ] **AC-5.** Pre-condition errors raised in this fixed order before any condition is checked:
  1. `report.complete is False` → `IncompleteReportForPromotion(report.run_id)`. `exc.args == (report.run_id,)`. (Gap #4 — partial reports cannot be evidence; raise, do not return a False verdict.)
  2. `target_tier not in tier_config.thresholds` → `TierConfigInvalid(target_tier, tuple(sorted(tier_config.thresholds)))`.
  3. `report.task_class not in registry` → `TaskClassNotFound(report.task_class)`. `exc.args == (report.task_class,)`. (Uses `registry.get(name)` per S1-03 AC-3.)
  4. `target_tier not in resolved_task_class.min_cases_for_promotion` → `TierConfigInvalid(target_tier, tuple(sorted(resolved_task_class.min_cases_for_promotion)))`.
  5. `report.task_class not in tier_config.current_tiers` → `TierConfigInvalid(report.task_class, tuple(sorted(tier_config.current_tiers)))`. (Failure-loud per ADR-0003 — startup catches most; per-call catches dynamic-registration drift.)
- [ ] **AC-6.** When pre-conditions pass, the gate evaluates **five** verdict conditions. (`complete=True` is structurally enforced by AC-5.1's raise; it is NOT a verdict-time condition. The story originally listed six; condition #5 was unreachable — Coverage F-COV-15.) Returns `evidence_sufficient=True` iff **ALL** of:
  1. `report.lower_bound_95 >= tier_config.thresholds[target_tier]` (ADR-0002). Uses `>=` directly on `float` (no `math.isclose`, no epsilon — ADR-0002 §Tradeoffs row 5 owns the precision question).
  2. `report.passed_count >= resolved_task_class.min_cases_for_promotion[target_tier]` (Phase 5 ADR-0016 §Decision §4).
  3. `report.block_severity_failure_modes == ()` (ADR-0004 — empty tuple).
  4. `audit_verify_result.ok is True` where `audit_verify_result = self._audit_verify(self._audit_out_dir())` is invoked **exactly once per `evaluate` call** with **no surrounding try/except**.
  5. `len({r.isolation_class for r in (evidence_window + (report,))}) == 1` (Gap #1 / ADR-0010 — homogeneous across the window; empty window degrades to a single-element set = trivially homogeneous).
- [ ] **AC-7.** When False, `reasons` lists every failing condition individually in this **deterministic order**:
  1. lower-bound shortfall (if condition #1 failed).
  2. case-count shortfall (if condition #2 failed).
  3. block-severity failures (if condition #3 failed) — one entry per code, codes appearing in `sorted(report.block_severity_failure_modes)` order.
  4. audit-not-ok (if condition #4 failed).
  5. isolation-class mismatch (if condition #5 failed).
- [ ] **AC-8.** **Reasons format strings (contract; format-pinned by `_REASON_FORMATS` if/when the sixth format lands per F-DP-6):**
  1. Lower-bound shortfall: `"lower_bound_95={x:.3f} < threshold[{tier}]={y:.3f}"` where `x=report.lower_bound_95` and `y=tier_config.thresholds[target_tier]`. (ADR-0002 §Consequences line 46 carries an abbreviated example; this format is the contract.)
  2. Case-count shortfall: `"passed_count={x} < min_cases_for_promotion[{tier}]={y}"` (no decimals — these are integers).
  3. Block-severity: `"block-severity failure: {code}"` (one entry per code in sorted order).
  4. Chain tamper / parse error: `"audit.verify().ok is False at {tampered_path}: {reason}"` where `tampered_path = str(result.tampered_path)` and `reason = result.reason or ""`. If `result.reason is None`, the trailing colon-space is omitted (`f"audit.verify().ok is False at {tampered_path}"`).
  5. Isolation mismatch: **ADR-0010 §Decision verbatim** — `"isolation_class mismatch in evidence window: subprocess={N1}, microvm={N2}"` where `N1` / `N2` are the counts of each class across `(evidence_window + (report,))`. If a future third class lands (per ADR-0010's `Literal` widening contract), the format generalizes as `subprocess={N1}, microvm={N2}, <name>={N3}` in `Literal`-declaration order (foresight only — out of scope today).
- [ ] **AC-9.** When `evidence_sufficient=True`, `reasons == ("all conditions met",)` **exactly** (the arch's documented happy-path verdict literal — `phase-arch-design.md §Dynamic view → Sequence`). The empty-tuple alternative is rejected — operator UX + audit-chain reproducibility require a positive literal.
- [ ] **AC-10.** Every returned `PromotionVerdict` populates **all eight** S1-02-required fields with these explicit values (`PromotionVerdict.model_construct` is forbidden; full Pydantic validation must succeed):
  - `task_class = report.task_class`
  - `current_tier = tier_config.current_tiers[report.task_class]`
  - `target_tier = target_tier` (the argument)
  - `evidence_sufficient = not reasons` (boolean inverse of reasons emptiness)
  - `reasons = tuple(reasons) if reasons else ("all conditions met",)`
  - `lower_bound_95 = report.lower_bound_95` (copied; the gate does NOT recompute)
  - `threshold_at_target = tier_config.thresholds[target_tier]` (copied)
  - `requires_human_approval = True` (the `Literal[True]` structural marker per S1-02 AC-7a; written verbatim so a future refactor cannot default it to silence)
- [ ] **AC-11.** Determinism: `evaluate(report, target_tier, evidence_window=window)` called twice on identical inputs returns equal `PromotionVerdict` instances **and** identical `model_dump_json()` byte strings (load-bearing for ADR-0002 §Consequences "byte-identical across reruns" and downstream Phase 11 PR provenance).
- [ ] **AC-12.** **Boundary discipline** (mutation-resistance against `>=` ↔ `>` and `<` ↔ `<=` swaps):
  - `report.lower_bound_95 == tier_config.thresholds[target_tier]` → condition #1 passes (uses `>=`, not `>`).
  - `report.lower_bound_95 == tier_config.thresholds[target_tier] - 1e-12` → condition #1 fails.
  - `report.passed_count == resolved_task_class.min_cases_for_promotion[target_tier]` → condition #2 passes.
  - `report.passed_count == resolved_task_class.min_cases_for_promotion[target_tier] - 1` → condition #2 fails.
- [ ] **AC-13.** **Property-based truth table.** A `hypothesis` strategy over `(bool, bool, bool, bool, bool)` (one per verdict condition #1–#5) synthesizes a report + window per cell, calls `evaluate`, asserts `verdict.evidence_sufficient is (lower_bound_ok AND passed_count_ok AND no_block_severity AND audit_ok AND isolation_homogeneous)`. Pinned in `tests/unit/test_promotion_properties.py`. (Catches any AND→OR mutation.)
- [ ] **AC-14.** **Injection spy:** `tests/unit/test_promotion.py::test_evaluate_calls_injected_audit_verify` constructs a gate with a spy `audit_verify` that records its invocation, calls `evaluate`, asserts the spy was called exactly once with the gate-derived `out_dir`. (Without this, a mutant that ignores the injection and reaches for the real `codegenie.eval.audit.verify` ships.)
- [ ] **AC-15.** **Adversarial purity fence for `evaluate`** (symmetric to AC-19 on `apply`): `tests/adv/test_promotion_evaluate_is_stateless.py` AST-walks `PromotionGate.evaluate`'s source (via `textwrap.dedent(inspect.getsource(...))`); asserts **zero** `ast.Assign` / `ast.AugAssign` nodes whose target is `ast.Attribute(value=ast.Name(id='self'))`. (Pins the arch's "`evaluate` is a pure function" commitment structurally; prevents a future "memoize the verify result" optimization that would break the per-call evidence contract.)

### `PromotionGate.apply` — unconditional raise + escalation message (Consistency F-CON-8 + Design-Patterns F-DP-8 + Test-Quality F-TQ-9 / F-TQ-10)

- [ ] **AC-16.** Signature: `PromotionGate.apply(self, *args: object, **kwargs: object) -> NoReturn`. The open `*args/**kwargs` shape is the intentional non-affordance — there is no typed `verdict=` parameter (the narrow form is a weaker fence; rejected).
- [ ] **AC-17.** Body is **exactly one statement**: a `raise PromotionMustBeHumanAuthorized(<message>)` where `<message>: str` includes verbatim:
  - the substring `"docs/trust-tiers.yaml"`,
  - the substring `"CODEOWNERS"`,
  - the substring `"0015"` OR (case-insensitive) `"calibration"` (the calibration ADR pointer),
  - the substring `"PR"` OR (case-insensitive) `"pull request"`,
  - the substring (case-insensitive) `"human"`.
- [ ] **AC-18.** `exc.args == (<message>,)` — single-positional, per S1-01 marker discipline. `len(exc.args) == 1` and `isinstance(exc.args[0], str)`.
- [ ] **AC-19.** **Adversarial AST fence:** `tests/adv/test_promotion_apply_raises.py::test_apply_is_structurally_unconditional`:
  1. `src = textwrap.dedent(inspect.getsource(PromotionGate.apply))` (the `textwrap.dedent` is load-bearing — without it `ast.parse` raises `IndentationError` and the fence is silent — Test-Quality F-TQ-5).
  2. `tree = ast.parse(src)`; locate the `FunctionDef` body.
  3. Assert `len(func_def.body) == 1` and `isinstance(func_def.body[0], ast.Raise)` (catches early-return mutants — Test-Quality F-TQ-6).
  4. Walk every node and assert no `ast.If` / `ast.Try` / `ast.For` / `ast.While` node appears in the body (defense-in-depth — `apply` must be structurally branchless).
- [ ] **AC-20.** **Adversarial call-shape coverage:** `apply` raises `PromotionMustBeHumanAuthorized` (and **not** `TypeError`) for every plausible argument shape:
  - `gate.apply()` — no args.
  - `gate.apply(object())` — one positional.
  - `gate.apply(1, 2, 3)` — three positionals.
  - `gate.apply(verdict=object())` — one kwarg.
  - `gate.apply(force=True, override=True, signed_off_by="root")` — three kwargs.
  - `gate.apply(object(), force=True)` — mixed positional + kwarg.
  - `gate.apply(*range(10), **{"k": "v"})` — splat both.
- [ ] **AC-21.** **Signature-introspection fence:** `inspect.signature(PromotionGate.apply).parameters` includes one `VAR_POSITIONAL` and one `VAR_KEYWORD` kind (`*args` + `**kwargs`). Pins the open-signature non-affordance — closes the F-DP-8 "narrow signature" regression path.

### Quality gates

- [ ] **AC-22.** The red tests from §TDD plan exist, were committed at the red marker, and are now green.
- [ ] **AC-23.** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/eval/promotion.py src/codegenie/eval/tier_config.py`, and `pytest tests/unit/test_promotion.py tests/unit/test_promotion_properties.py tests/unit/test_tier_config.py tests/adv/test_promotion_apply_raises.py tests/adv/test_promotion_evaluate_is_stateless.py tests/fence/test_promotion_cold_start.py` all pass.

## Implementation outline

1. Write red tests in this order (each commit gates on `pytest` failing at the import / fixture step):
   1. `tests/unit/test_tier_config.py` — `TierConfig`, `load_tier_config`, `MappingProxyType` immutability.
   2. `tests/unit/test_promotion.py` — `__init__` tier validation, the five-condition matrix (six cells incl. boundary), the verdict-shape assertions, the determinism assertion, the injection spy.
   3. `tests/unit/test_promotion_properties.py` — hypothesis truth-table property.
   4. `tests/adv/test_promotion_apply_raises.py` — unconditional-raise asserter + the dedented AST audit + the signature-introspection fence + the call-shape matrix.
   5. `tests/adv/test_promotion_evaluate_is_stateless.py` — purity AST fence.
   6. `tests/fence/test_promotion_cold_start.py` — `sys.modules` cold-start assertions.
2. Create `src/codegenie/eval/tier_config.py`:
   - `TierConfig` `@dataclass(frozen=True, slots=True)` with `__post_init__` wrapping `thresholds` / `current_tiers` in `types.MappingProxyType(dict(...))` (Design-Patterns F-DP-5).
   - `load_tier_config(path: Path) -> TierConfig` — reads YAML, builds `TierConfig`. `import yaml` lives in this module only.
3. Create `src/codegenie/eval/promotion.py`:
   - **Imports (module top, deliberately narrow — Design-Patterns F-DP-9):** stdlib only (`from __future__ import annotations`, `dataclasses`, `inspect`, `types`, `typing` essentials, `pathlib.Path`), plus `from codegenie.eval.errors import (...)`, `from codegenie.eval.models import BenchRunReport, PromotionVerdict`, `from codegenie.eval.registry import TaskClassRegistry, default_registry`, `from codegenie.eval.tier_config import TierConfig`. **No** `from codegenie.eval.audit import verify` (deferred). **No** `from codegenie.eval.audit import VerifyResult` (use `TYPE_CHECKING` for the type).
   - Module-top `_default_audit_verify(out_dir: Path) -> VerifyResult`: imports `from codegenie.eval.audit import verify` inside the body, returns `verify(out_dir)`.
   - `PromotionGate.__init__` — startup tier validation per AC-3.
   - Five private pure helpers `_check_lower_bound`, `_check_passed_count`, `_check_block_severity`, `_check_audit_ok`, `_check_isolation_homogeneous`, each returning `str | None`. Each is a pure function over `(report, target_tier, task_class, evidence_window, audit_verify_result, tier_config)`. (Future: `_CONDITIONS: Final[tuple[_Condition, ...]]` registry when the sixth condition lands — Design-Patterns F-DP-1.)
   - `PromotionGate.evaluate` — runs pre-condition raises in the fixed order; calls `self._audit_verify(self._audit_out_dir())` exactly once; collects `reasons` via a single comprehension `tuple(r for r in (_check_lower_bound(...), _check_passed_count(...), _check_block_severity(...), _check_audit_ok(...), _check_isolation_homogeneous(...)) if r is not None)` (functional-core / imperative-shell — Design-Patterns F-DP-2); constructs `PromotionVerdict` with all eight fields explicit (AC-10); before returning, asserts the runtime invariant `if not ((evidence_sufficient and reasons == ("all conditions met",)) or (not evidence_sufficient and reasons)): raise AssertionError("PromotionVerdict invariant violated", reasons, evidence_sufficient)` (Design-Patterns F-DP-11; bare `assert` is banned, so the explicit `raise AssertionError`).
   - `PromotionGate.apply` — single-statement body:
     ```python
     def apply(self, *args: object, **kwargs: object) -> NoReturn:
         raise PromotionMustBeHumanAuthorized(
             "Tier promotion requires a human-authored PR (pull request) against "
             "docs/trust-tiers.yaml with CODEOWNERS approval and an accompanying ADR amendment. "
             "See docs/production/adrs/0015-trust-score-threshold-calibration.md for the calibration path."
         )
     ```
   - Structured log: at end of `evaluate`, emit `promotion_evaluated` via the project's `structlog` logger with `{task_class, target_tier, evidence_sufficient, reasons_count, lower_bound_95, threshold_at_target}` (Coverage F-COV-18 — keeps Phase 13 dashboard backfill cheap).
4. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/eval/promotion.py src/codegenie/eval/tier_config.py`, the full pytest set from AC-23.

## TDD plan — red / green / refactor

### Red — write the failing tests first

#### `tests/unit/test_tier_config.py` (new)

```python
import pytest
from types import MappingProxyType

from codegenie.eval.tier_config import TierConfig


def test_tier_config_normalizes_mappings_to_proxy():
    tc = TierConfig(
        thresholds={"bronze": 0.70, "silver": 0.80},
        current_tiers={"vuln-remediation": "bronze"},
    )
    assert isinstance(tc.thresholds, MappingProxyType)
    assert isinstance(tc.current_tiers, MappingProxyType)


def test_tier_config_inner_mutation_raises():
    tc = TierConfig(thresholds={"bronze": 0.70}, current_tiers={})
    with pytest.raises(TypeError):
        tc.thresholds["bronze"] = 0.99  # MappingProxyType blocks __setitem__
    with pytest.raises(TypeError):
        tc.current_tiers["vuln-remediation"] = "silver"


def test_tier_config_external_dict_mutation_does_not_leak():
    inner = {"bronze": 0.70}
    tc = TierConfig(thresholds=inner, current_tiers={})
    inner["bronze"] = 0.99
    assert tc.thresholds["bronze"] == 0.70  # snapshot-copied + proxied
```

#### `tests/unit/test_promotion.py` (new)

```python
import inspect
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Final

import pytest

from codegenie.eval.errors import (
    IncompleteReportForPromotion,
    PromotionMustBeHumanAuthorized,
    TaskClassNotFound,
    TierConfigInvalid,
)
from codegenie.eval.models import BenchRunReport, FailureMode, PromotionVerdict
from codegenie.eval.promotion import PromotionGate
from codegenie.eval.registry import TaskClassRegistry, register_task_class
from codegenie.eval.tier_config import TierConfig


# ---------- helpers ----------

class _StubRubric:
    """Trivial Rubric-shaped stub for fixture TaskClasses."""


def _stub_registry_with_vuln(min_for_silver: int = 25) -> TaskClassRegistry:
    reg = TaskClassRegistry()
    register_task_class(
        "vuln-remediation",
        bench_path=Path("bench/vuln-remediation"),
        min_cases_for_promotion={"bronze": 10, "silver": min_for_silver},
        breakdown_keys=frozenset(),
        failure_mode_taxonomy={
            "validator.tests_failed": "block",
            "validator.cve_not_dropped": "block",
            "validator.build_failed": "block",
        },
        registry=reg,
    )(_StubRubric)
    return reg


def _tier_config() -> TierConfig:
    return TierConfig(
        thresholds={"bronze": 0.70, "silver": 0.80, "gold": 0.90},
        current_tiers={"vuln-remediation": "bronze"},
    )


def _make_report(
    *,
    lower_bound_95: float = 0.85,
    passed_count: int = 25,
    block_failures: tuple[str, ...] = (),
    complete: bool = True,
    isolation_class: str = "subprocess",
    run_id: str = "abc12345def67890",
) -> BenchRunReport:
    """Full validated construction — NOT model_construct (Test-Quality F-TQ-1)."""
    return BenchRunReport(
        run_id=run_id,
        task_class="vuln-remediation",
        harness_version="0.1.0",
        sut_digest="d1",
        rubric_digest="d2",
        cassette_corpus_digest="d3",
        run_started_iso=datetime(2026, 5, 12, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        per_case=(),
        mean_score=min(lower_bound_95 + 0.05, 1.0),
        score_stddev=0.08,
        lower_bound_95=lower_bound_95,
        passed_count=passed_count,
        total_cost_usd=0.04,
        block_severity_failure_modes=block_failures,
        complete=complete,
        isolation_class=isolation_class,
        prev_hash="0" * 64,
        chain_head="0" * 64,
    )


def _fake_verify_factory(*, ok: bool = True, tampered_path: Path | None = None, reason: str | None = None):
    def fake_verify(_out_dir: Path) -> SimpleNamespace:
        return SimpleNamespace(
            ok=ok,
            tampered_path=tampered_path,
            reason=reason,
            verified_complete=10,
            verified_incomplete=0,
        )

    return fake_verify


def _gate(
    *,
    verify_ok: bool = True,
    tampered_path: Path | None = None,
    reason: str | None = None,
    min_for_silver: int = 25,
) -> PromotionGate:
    return PromotionGate(
        tier_config=_tier_config(),
        registry=_stub_registry_with_vuln(min_for_silver=min_for_silver),
        audit_verify=_fake_verify_factory(ok=verify_ok, tampered_path=tampered_path, reason=reason),
    )


def _assert_verdict_invariants(verdict: PromotionVerdict, *, report: BenchRunReport, target_tier: str) -> None:
    """Shared invariant pin for every six-condition test (Test-Quality F-TQ-3 / F-TQ-7)."""
    assert isinstance(verdict, PromotionVerdict), "must not be a SimpleNamespace fake"
    assert type(verdict.reasons) is tuple, f"reasons must be tuple; got {type(verdict.reasons).__name__}"
    assert all(isinstance(r, str) for r in verdict.reasons)
    assert verdict.requires_human_approval is True, "S1-02 AC-7a + ADR-0009 structural marker"
    assert verdict.task_class == report.task_class
    assert verdict.target_tier == target_tier
    assert verdict.lower_bound_95 == report.lower_bound_95
    assert verdict.threshold_at_target == 0.80 if target_tier == "silver" else verdict.threshold_at_target


# ---------- pre-condition errors (AC-5) ----------

def test_evaluate_raises_on_incomplete_report():
    gate = _gate()
    report = _make_report(complete=False, run_id="partial:abc")
    with pytest.raises(IncompleteReportForPromotion) as exc_info:
        gate.evaluate(report, target_tier="silver")
    assert exc_info.value.args == ("partial:abc",)


def test_evaluate_raises_on_unknown_target_tier_in_thresholds():
    gate = _gate()
    report = _make_report()
    with pytest.raises(TierConfigInvalid) as exc_info:
        gate.evaluate(report, target_tier="emerald")
    assert exc_info.value.args == ("emerald", ("bronze", "gold", "silver"))


def test_evaluate_raises_on_unknown_task_class_in_registry():
    gate = _gate()
    # Empty registry — vuln-remediation registered separately
    gate._registry = TaskClassRegistry()  # type: ignore[attr-defined]
    report = _make_report()
    with pytest.raises(TaskClassNotFound) as exc_info:
        gate.evaluate(report, target_tier="silver")
    assert exc_info.value.args == ("vuln-remediation",)


def test_evaluate_raises_on_unknown_tier_in_min_cases_for_promotion():
    reg = TaskClassRegistry()
    register_task_class(
        "vuln-remediation",
        bench_path=Path("bench/vuln-remediation"),
        min_cases_for_promotion={"bronze": 10},  # silver not declared
        breakdown_keys=frozenset(),
        failure_mode_taxonomy={},
        registry=reg,
    )(_StubRubric)
    gate = PromotionGate(
        tier_config=_tier_config(),
        registry=reg,
        audit_verify=_fake_verify_factory(),
    )
    report = _make_report()
    with pytest.raises(TierConfigInvalid) as exc_info:
        gate.evaluate(report, target_tier="silver")
    assert exc_info.value.args == ("silver", ("bronze",))


# ---------- happy path (AC-9, AC-10, AC-11) ----------

def test_evaluate_true_when_all_conditions_pass():
    gate = _gate()
    report = _make_report(lower_bound_95=0.85, passed_count=25)
    verdict = gate.evaluate(report, target_tier="silver")
    _assert_verdict_invariants(verdict, report=report, target_tier="silver")
    assert verdict.evidence_sufficient is True
    assert verdict.reasons == ("all conditions met",)  # AC-9 — exact, not "in ((), (...))"
    assert verdict.current_tier == "bronze"
    assert verdict.threshold_at_target == 0.80


def test_evaluate_deterministic_across_reruns():
    """AC-11 + ADR-0002 §Consequences — byte-identical reruns."""
    gate1 = _gate(verify_ok=False, tampered_path=Path("/tmp/x"), reason="content_hash mismatch")
    gate2 = _gate(verify_ok=False, tampered_path=Path("/tmp/x"), reason="content_hash mismatch")
    report = _make_report(lower_bound_95=0.50, passed_count=3, block_failures=("a", "b", "c", "d"))
    v1 = gate1.evaluate(report, target_tier="silver")
    v2 = gate2.evaluate(report, target_tier="silver")
    assert v1 == v2
    assert v1.model_dump_json() == v2.model_dump_json()


# ---------- single-condition failures (AC-6 verdict matrix) ----------

def test_evaluate_false_when_lower_bound_below_threshold():
    gate = _gate()
    report = _make_report(lower_bound_95=0.78, passed_count=25)
    verdict = gate.evaluate(report, target_tier="silver")
    assert verdict.evidence_sufficient is False
    assert verdict.reasons == ("lower_bound_95=0.780 < threshold[silver]=0.800",)


def test_evaluate_false_when_passed_count_below_floor():
    gate = _gate()
    report = _make_report(lower_bound_95=0.85, passed_count=10)
    verdict = gate.evaluate(report, target_tier="silver")
    assert verdict.evidence_sufficient is False
    assert verdict.reasons == ("passed_count=10 < min_cases_for_promotion[silver]=25",)


def test_evaluate_false_with_block_severity_failures_in_sorted_order():
    """AC-7 + Test-Quality F-TQ-8 — block-severity reasons emitted in sorted(code) order."""
    gate = _gate()
    # Pass codes in non-sorted order; output must be sorted.
    report = _make_report(block_failures=("validator.tests_failed", "validator.cve_not_dropped"))
    verdict = gate.evaluate(report, target_tier="silver")
    assert verdict.evidence_sufficient is False
    assert verdict.reasons == (
        "block-severity failure: validator.cve_not_dropped",  # sorted alphabetically
        "block-severity failure: validator.tests_failed",
    )


def test_evaluate_false_when_audit_verify_not_ok_with_reason():
    gate = _gate(verify_ok=False, tampered_path=Path("/path/to/record-001.json"), reason="content_hash mismatch")
    report = _make_report()
    verdict = gate.evaluate(report, target_tier="silver")
    assert verdict.evidence_sufficient is False
    assert verdict.reasons == (
        "audit.verify().ok is False at /path/to/record-001.json: content_hash mismatch",
    )


def test_evaluate_false_when_audit_verify_not_ok_without_reason():
    """AC-8 condition #4 — trailing colon-space omitted when result.reason is None."""
    gate = _gate(verify_ok=False, tampered_path=Path("/p"), reason=None)
    report = _make_report()
    verdict = gate.evaluate(report, target_tier="silver")
    assert verdict.reasons == ("audit.verify().ok is False at /p",)


def test_evaluate_false_when_isolation_class_mixed():
    """ADR-0010 §Decision verbatim format (AC-8 condition #5)."""
    gate = _gate()
    prior = _make_report(isolation_class="microvm", run_id="prior01_______02")
    report = _make_report(isolation_class="subprocess")
    verdict = gate.evaluate(report, target_tier="silver", evidence_window=(prior,))
    assert verdict.evidence_sufficient is False
    assert verdict.reasons == (
        "isolation_class mismatch in evidence window: subprocess=1, microvm=1",
    )


# ---------- positive isolation cases (Coverage F-COV-6 / F-COV-7) ----------

def test_evaluate_empty_evidence_window_passes_isolation_check():
    gate = _gate()
    report = _make_report(isolation_class="subprocess")
    verdict = gate.evaluate(report, target_tier="silver", evidence_window=())
    assert verdict.evidence_sufficient is True
    assert not any("isolation" in r for r in verdict.reasons)


def test_evaluate_homogeneous_window_passes():
    gate = _gate()
    prior = _make_report(isolation_class="subprocess", run_id="prior01_______02")
    report = _make_report(isolation_class="subprocess")
    verdict = gate.evaluate(report, target_tier="silver", evidence_window=(prior,))
    assert verdict.evidence_sufficient is True
    assert not any("isolation" in r for r in verdict.reasons)


# ---------- boundary discipline (AC-12) ----------

def test_evaluate_lower_bound_equal_to_threshold_passes():
    gate = _gate()
    report = _make_report(lower_bound_95=0.80, passed_count=25)
    verdict = gate.evaluate(report, target_tier="silver")
    assert verdict.evidence_sufficient is True


def test_evaluate_lower_bound_just_below_threshold_fails():
    gate = _gate()
    report = _make_report(lower_bound_95=0.80 - 1e-12, passed_count=25)
    verdict = gate.evaluate(report, target_tier="silver")
    assert verdict.evidence_sufficient is False
    assert any(r.startswith("lower_bound_95=") for r in verdict.reasons)


def test_evaluate_passed_count_equal_to_floor_passes():
    gate = _gate()
    report = _make_report(passed_count=25)
    verdict = gate.evaluate(report, target_tier="silver")
    assert verdict.evidence_sufficient is True


def test_evaluate_passed_count_one_below_floor_fails():
    gate = _gate()
    report = _make_report(passed_count=24)
    verdict = gate.evaluate(report, target_tier="silver")
    assert verdict.evidence_sufficient is False
    assert verdict.reasons == ("passed_count=24 < min_cases_for_promotion[silver]=25",)


# ---------- enumeration + order (AC-7 + Coverage F-COV-8) ----------

def test_evaluate_enumerates_every_failing_condition_in_pinned_order():
    """AC-7 — reasons appear in (lower_bound, passed_count, block-severity, audit, isolation) order."""
    gate = _gate(verify_ok=False, tampered_path=Path("/x"), reason="prev_hash mismatch")
    prior = _make_report(isolation_class="microvm", run_id="prior01_______02")
    report = _make_report(
        lower_bound_95=0.50, passed_count=3,
        block_failures=("validator.build_failed", "validator.tests_failed"),
        isolation_class="subprocess",
    )
    verdict = gate.evaluate(report, target_tier="silver", evidence_window=(prior,))
    assert verdict.evidence_sufficient is False
    assert verdict.reasons == (
        "lower_bound_95=0.500 < threshold[silver]=0.800",
        "passed_count=3 < min_cases_for_promotion[silver]=25",
        "block-severity failure: validator.build_failed",
        "block-severity failure: validator.tests_failed",
        "audit.verify().ok is False at /x: prev_hash mismatch",
        "isolation_class mismatch in evidence window: subprocess=1, microvm=1",
    )


# ---------- __init__ tier validation (AC-3) ----------

def test_unknown_tier_in_current_tiers_raises_at_init():
    bad = TierConfig(
        thresholds={"bronze": 0.70, "silver": 0.80},
        current_tiers={"vuln-remediation": "silvr"},  # typo
    )
    with pytest.raises(TierConfigInvalid) as exc_info:
        PromotionGate(tier_config=bad, registry=_stub_registry_with_vuln())
    assert exc_info.value.args == ("silvr", ("bronze", "silver"))


def test_unknown_tier_in_min_cases_for_promotion_raises_at_init():
    reg = TaskClassRegistry()
    register_task_class(
        "vuln-remediation",
        bench_path=Path("bench/vuln-remediation"),
        min_cases_for_promotion={"bronze": 10, "platinumm": 50},  # typo
        breakdown_keys=frozenset(),
        failure_mode_taxonomy={},
        registry=reg,
    )(_StubRubric)
    with pytest.raises(TierConfigInvalid) as exc_info:
        PromotionGate(tier_config=_tier_config(), registry=reg)
    assert exc_info.value.args == ("platinumm", ("bronze", "gold", "silver"))


# ---------- audit_verify injection spy (AC-14) ----------

def test_evaluate_calls_injected_audit_verify():
    captured: dict[str, object] = {}

    def spy(out_dir: Path):
        captured["called_with"] = out_dir
        captured["count"] = captured.get("count", 0) + 1
        return SimpleNamespace(ok=True, tampered_path=None, reason=None, verified_complete=0, verified_incomplete=0)

    gate = PromotionGate(
        tier_config=_tier_config(),
        registry=_stub_registry_with_vuln(),
        audit_verify=spy,
    )
    gate.evaluate(_make_report(), target_tier="silver")
    assert captured.get("count") == 1, "evaluate must invoke the injected audit_verify exactly once"
    assert isinstance(captured.get("called_with"), Path)
```

#### `tests/unit/test_promotion_properties.py` (new — AC-13)

```python
import hypothesis
import hypothesis.strategies as st
import pytest
from pathlib import Path
from types import SimpleNamespace

from codegenie.eval.promotion import PromotionGate
from tests.unit.test_promotion import (
    _stub_registry_with_vuln,
    _tier_config,
    _make_report,
)


@hypothesis.given(
    lb_ok=st.booleans(),
    pc_ok=st.booleans(),
    no_block=st.booleans(),
    audit_ok=st.booleans(),
    iso_ok=st.booleans(),
)
@hypothesis.settings(max_examples=64, deadline=None)
def test_evidence_sufficient_iff_all_five_pass(lb_ok, pc_ok, no_block, audit_ok, iso_ok):
    def fake_verify(_out_dir):
        return SimpleNamespace(
            ok=audit_ok,
            tampered_path=None if audit_ok else Path("/x"),
            reason=None if audit_ok else "content_hash mismatch",
            verified_complete=0, verified_incomplete=0,
        )

    gate = PromotionGate(
        tier_config=_tier_config(),
        registry=_stub_registry_with_vuln(),
        audit_verify=fake_verify,
    )
    report = _make_report(
        lower_bound_95=0.85 if lb_ok else 0.50,
        passed_count=25 if pc_ok else 3,
        block_failures=() if no_block else ("validator.tests_failed",),
        isolation_class="subprocess",
    )
    window = () if iso_ok else (_make_report(isolation_class="microvm", run_id="prior01_______02"),)
    verdict = gate.evaluate(report, target_tier="silver", evidence_window=window)
    expected = lb_ok and pc_ok and no_block and audit_ok and iso_ok
    assert verdict.evidence_sufficient is expected, (
        f"AND violation at cell ({lb_ok}, {pc_ok}, {no_block}, {audit_ok}, {iso_ok}): "
        f"got {verdict.evidence_sufficient}; reasons={verdict.reasons!r}"
    )
```

#### `tests/adv/test_promotion_apply_raises.py` (new)

```python
import ast
import inspect
import textwrap

import pytest

from codegenie.eval.errors import PromotionMustBeHumanAuthorized
from codegenie.eval.promotion import PromotionGate
from codegenie.eval.tier_config import TierConfig


@pytest.fixture
def gate_with_valid_config():
    return PromotionGate(
        tier_config=TierConfig(
            thresholds={"bronze": 0.70, "silver": 0.80, "gold": 0.90},
            current_tiers={},
        ),
    )


# ---------- call-shape matrix (AC-20) ----------

@pytest.mark.parametrize("call", [
    lambda g: g.apply(),
    lambda g: g.apply(object()),
    lambda g: g.apply(1, 2, 3),
    lambda g: g.apply(verdict=object()),
    lambda g: g.apply(force=True, override=True, signed_off_by="root"),
    lambda g: g.apply(object(), force=True),
    lambda g: g.apply(*range(10), **{"k": "v"}),
])
def test_apply_raises_for_every_call_shape(gate_with_valid_config, call):
    with pytest.raises(PromotionMustBeHumanAuthorized):
        call(gate_with_valid_config)


# ---------- escalation message (AC-17 + AC-18 + Test-Quality F-TQ-10) ----------

def test_apply_message_pins_canonical_escalation_path(gate_with_valid_config):
    with pytest.raises(PromotionMustBeHumanAuthorized) as exc_info:
        gate_with_valid_config.apply()
    err = exc_info.value
    assert len(err.args) == 1 and isinstance(err.args[0], str)
    msg = err.args[0]
    assert "docs/trust-tiers.yaml" in msg
    assert "CODEOWNERS" in msg
    assert ("0015" in msg) or ("calibration" in msg.lower())
    assert ("PR" in msg) or ("pull request" in msg.lower())
    assert "human" in msg.lower()


# ---------- structural fence (AC-19 + Test-Quality F-TQ-5 / F-TQ-6) ----------

def test_apply_is_structurally_unconditional():
    """The AST fence — dedent first or ast.parse raises IndentationError silently."""
    src = textwrap.dedent(inspect.getsource(PromotionGate.apply))
    tree = ast.parse(src)
    func_def = tree.body[0]
    assert isinstance(func_def, ast.FunctionDef) and func_def.name == "apply"

    # Body is exactly one statement, and that statement is Raise (kills early-return mutants).
    assert len(func_def.body) == 1, (
        f"apply() must have exactly one statement; got {len(func_def.body)}: "
        f"{[ast.dump(s) for s in func_def.body]}"
    )
    assert isinstance(func_def.body[0], ast.Raise), (
        f"apply()'s sole statement must be Raise; got {type(func_def.body[0]).__name__}"
    )

    # Defense-in-depth: no branching node anywhere in the body subtree.
    for node in ast.walk(func_def):
        for forbidden in (ast.If, ast.Try, ast.For, ast.While, ast.AsyncFor, ast.With, ast.AsyncWith):
            assert not isinstance(node, forbidden), (
                f"apply() body contains {type(node).__name__} — must be branchless"
            )


# ---------- signature-introspection fence (AC-21) ----------

def test_apply_signature_is_var_positional_plus_var_keyword():
    sig = inspect.signature(PromotionGate.apply)
    kinds = {p.kind for p in sig.parameters.values()}
    assert inspect.Parameter.VAR_POSITIONAL in kinds, "apply() must accept *args"
    assert inspect.Parameter.VAR_KEYWORD in kinds, "apply() must accept **kwargs"
    # And no other parameter kinds (besides self) — the open-signature non-affordance.
    non_self_kinds = {p.kind for name, p in sig.parameters.items() if name != "self"}
    assert non_self_kinds == {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
```

#### `tests/adv/test_promotion_evaluate_is_stateless.py` (new — AC-15)

```python
import ast
import inspect
import textwrap

from codegenie.eval.promotion import PromotionGate


def test_evaluate_does_not_assign_self_attributes():
    """phase-arch-design.md line 648 — 'evaluate is a pure function'.
    Symmetric AST fence to apply()'s structural-unconditionality fence."""
    src = textwrap.dedent(inspect.getsource(PromotionGate.evaluate))
    tree = ast.parse(src)
    func_def = tree.body[0]
    assert isinstance(func_def, ast.FunctionDef) and func_def.name == "evaluate"

    for node in ast.walk(func_def):
        if isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                    raise AssertionError(
                        f"evaluate() must be pure (no self.<attr> assignment); "
                        f"found assignment to self.{t.attr}"
                    )
```

#### `tests/fence/test_promotion_cold_start.py` (new — AC-2a)

```python
import sys


def test_importing_promotion_does_not_pull_audit_or_yaml():
    """Design-Patterns F-DP-9 — promotion.py's hot path must not drag audit + yaml in."""
    # Remove possibly-loaded modules to assert the import is clean.
    for mod in list(sys.modules):
        if mod.startswith(("codegenie.eval.promotion", "codegenie.eval.audit", "yaml")):
            del sys.modules[mod]

    import codegenie.eval.promotion  # noqa: F401

    assert "codegenie.eval.audit" not in sys.modules, (
        "promotion.py must defer the audit import (see _default_audit_verify wrapper)"
    )
    assert "yaml" not in sys.modules, (
        "promotion.py must not import pyyaml; load_tier_config lives in tier_config.py"
    )
```

Run; confirm failures. Commit as the red marker.

### Green — make them pass

Implement `tier_config.py` and `promotion.py` per §Implementation outline.

`evaluate`'s body (sketch):

```python
def evaluate(
    self,
    report: BenchRunReport,
    target_tier: str,
    *,
    evidence_window: tuple[BenchRunReport, ...] = (),
) -> PromotionVerdict:
    # Pre-condition raises in fixed order (AC-5).
    if report.complete is False:
        raise IncompleteReportForPromotion(report.run_id)
    if target_tier not in self._tier_config.thresholds:
        raise TierConfigInvalid(target_tier, tuple(sorted(self._tier_config.thresholds)))
    task_class = self._registry.get(report.task_class)  # raises TaskClassNotFound
    if target_tier not in task_class.min_cases_for_promotion:
        raise TierConfigInvalid(target_tier, tuple(sorted(task_class.min_cases_for_promotion)))
    if report.task_class not in self._tier_config.current_tiers:
        raise TierConfigInvalid(report.task_class, tuple(sorted(self._tier_config.current_tiers)))

    # Single audit-verify invocation (AC-6 #4); NO try/except.
    result = self._audit_verify(self._audit_out_dir())

    # Pure-function helpers; comprehension at the boundary (Design-Patterns F-DP-2).
    candidates = (
        _check_lower_bound(report, target_tier, self._tier_config),
        _check_passed_count(report, target_tier, task_class),
        _check_block_severity(report),                          # sorted yield internal
        _check_audit_ok(result),
        _check_isolation_homogeneous(report, evidence_window),
    )
    reasons_list: list[str] = []
    for cand in candidates:
        if cand is None:
            continue
        if isinstance(cand, tuple):  # block-severity returns tuple[str, ...]
            reasons_list.extend(cand)
        else:
            reasons_list.append(cand)
    reasons = tuple(reasons_list) if reasons_list else ("all conditions met",)
    evidence_sufficient = not reasons_list

    # Runtime invariant guard (Design-Patterns F-DP-11; bare `assert` forbidden).
    if not (
        (evidence_sufficient and reasons == ("all conditions met",))
        or (not evidence_sufficient and bool(reasons))
    ):
        raise AssertionError(
            "PromotionVerdict invariant violated",
            {"evidence_sufficient": evidence_sufficient, "reasons": reasons},
        )

    verdict = PromotionVerdict(
        task_class=report.task_class,
        current_tier=self._tier_config.current_tiers[report.task_class],
        target_tier=target_tier,
        evidence_sufficient=evidence_sufficient,
        reasons=reasons,
        lower_bound_95=report.lower_bound_95,
        threshold_at_target=self._tier_config.thresholds[target_tier],
        requires_human_approval=True,
    )
    _LOG.info(
        "promotion_evaluated",
        task_class=report.task_class,
        target_tier=target_tier,
        evidence_sufficient=evidence_sufficient,
        reasons_count=len(reasons),
        lower_bound_95=report.lower_bound_95,
        threshold_at_target=verdict.threshold_at_target,
    )
    return verdict
```

`apply`'s body is **exactly** one `raise` statement (AC-17).

### Refactor — clean up

- Each `_check_*` is a small pure function returning `str | None` (or `tuple[str, ...]` for block-severity which can emit many). Tested individually so each ADR's condition is regression-tested in isolation.
- Module docstring cites ADR-0002, ADR-0003, ADR-0004, ADR-0009, ADR-0010, Phase 5 ADR-0016 §Decision §4, production ADR-0009, production ADR-0015. Reasoning is load-bearing in the codebase.
- `mypy --strict`: `evaluate` returns `PromotionVerdict`; `apply` returns `NoReturn`; `_default_audit_verify` returns the `VerifyResult` `TYPE_CHECKING`-imported type.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/tier_config.py` | **New** — `TierConfig` (`MappingProxyType`-normalized) + `load_tier_config`. Isolates `pyyaml` import from `promotion.py` (Design-Patterns F-DP-3 / F-DP-5 / F-DP-9). |
| `src/codegenie/eval/promotion.py` | **New** — `_default_audit_verify` (deferred-import wrapper), `PromotionGate`, `evaluate`, `apply`, five pure `_check_*` helpers. **Zero** module-top imports of `codegenie.eval.audit` or `yaml`. |
| `tests/unit/test_tier_config.py` | **New** — `TierConfig` / `load_tier_config` / `MappingProxyType` immutability. |
| `tests/unit/test_promotion.py` | **New** — `__init__` tier validation; pre-condition raises in pinned order; five-condition matrix incl. boundary; deterministic-rerun; injection spy; isolation-class positive + negative cases; full verdict-shape pin via `_assert_verdict_invariants`. |
| `tests/unit/test_promotion_properties.py` | **New** — `hypothesis`-driven truth table (AC-13). |
| `tests/adv/test_promotion_apply_raises.py` | **New** — call-shape parametrize + dedented AST audit + signature-introspection fence (AC-19 / AC-20 / AC-21). |
| `tests/adv/test_promotion_evaluate_is_stateless.py` | **New** — purity AST fence (AC-15). |
| `tests/fence/test_promotion_cold_start.py` | **New** — `sys.modules` cold-start assertions (AC-2a). |

## Out of scope

- **`docs/trust-tiers.yaml` content** — S4-05 ships the minimal YAML with bronze candidate numbers + uncalibrated header. This story uses an in-memory `TierConfig` for tests and a `load_tier_config` callable for production wiring.
- **Recommendation file writing** — S4-05 owns `.codegenie/eval/recommendations/<utc-iso>.json` shape.
- **CLI wiring** — S4-02 (`--with-verdict` flag) calls `gate.evaluate(report, target_tier)`; this story owns the gate logic, not the CLI integration.
- **Mixed-isolation-class override (`--allow-isolation-mix`)** — ADR-0010 §Open Q reserves it; not in Phase 6.5.
- **Demotion logic** — ADR-0009 (automatic-demotion-as-recommendation-shift) is honored by *not* implementing demotion as a side-effect. The `reasons` tuple is the sole carrier of the operator-actionable signal.
- **Multi-window evidence aggregation** — `evidence_window` is a tuple of prior reports passed by the caller; this story does not implement window selection (Phase 5 / Phase 11 territory). The caller supplies the window; the gate checks `isolation_class` homogeneity over it.
- **`_CONDITIONS: Final[tuple[_Condition, ...]]` registry extraction** — Design-Patterns F-DP-1; the trigger is the sixth condition (Phase 16 microVM-transition condition or the `--allow-isolation-mix` override). With five conditions today, the six private helpers are correct (Rule 2).
- **`_REASON_FORMATS: Final[Mapping[str, str]]` catalog extraction** — Design-Patterns F-DP-6; same Phase 16 trigger (when the sixth format string lands).
- **Out-of-band tier widening to `"emerald"` etc.** — ADR-0003's startup validation handles widening as a YAML + ADR change with zero `promotion.py` edits.
- **`audit_verify` exposed via CLI** — Design-Patterns F-DP-12 reaffirmed: the injection is a testing affordance, not a public API.
- **Strengthening `PromotionVerdict` to a tagged union** (`EvidenceSufficient | EvidenceInsufficient`) — the wire shape is frozen by S1-02. The runtime invariant assertion inside `evaluate` is the substitute.

## Notes for the implementer

- **The asymmetry between `evaluate` and `apply` is the entire point.** `evaluate` is rich, ADR-honoring, returns data. `apply` is one line, returns nothing, always raises. Resist any review feedback to "make `apply` symmetric" — the asymmetry is documented in `phase-arch-design.md §Tradeoffs (consolidated)` and is what makes "Humans always merge" structurally enforced. The AST fence (AC-19) and the purity fence (AC-15) pin both halves of the asymmetry in code.

- **`reasons` discipline matters for the operator UX.** When `evidence_sufficient=False`, the operator reads `reasons` and acts on each entry. The format strings pinned in AC-8 are the *contract*; Phase 11 PR provenance + S4-05 recommendation writer parse against them. Any change requires an ADR amendment to ADR-0002 / ADR-0004 / ADR-0010. (When a sixth format string lands, promote to a module-top `_REASON_FORMATS: Final[Mapping[str, str]]` per Design-Patterns F-DP-6 — `_LOCKFILE_PRECEDENCE` precedent.)

- **`audit_verify` injection is a testing affordance, not a public API.** Default it to a module-top `_default_audit_verify` wrapper that **imports `codegenie.eval.audit.verify` inside the function body** (Design-Patterns F-DP-9). This keeps `promotion.py`'s cold start narrow (no `codegenie.eval.audit` at module top — pinned by AC-2a). The CLI never passes the parameter; only unit tests do.

- **Conditions-as-helpers, not as a registry, today.** Five `_check_*` pure functions are correct now (Rule 2: three similar lines is better than premature abstraction). The trigger for promoting to a `_CONDITIONS: Final[tuple[_Condition, ...]]` Strategy registry is the sixth condition (Phase 16 microVM-transition record check, or the `--allow-isolation-mix` override). Repo precedent for the future shape: `_LOCKFILE_PRECEDENCE: Final[tuple[...]]` in `src/codegenie/probes/node_build_system.py`.

- **Functional-core / imperative-shell.** Each `_check_*` is a pure function returning `str | None` (or `tuple[str, ...]` for block-severity). `evaluate` collects via a single comprehension at the boundary — **NOT** `reasons.append(...)` inside each helper. The shape pins reason-order to the comprehension order (visible at the top of the function) and prevents accidental shared-accumulator bugs (Design-Patterns F-DP-2).

- **`TierConfig.thresholds` and `current_tiers` are `MappingProxyType`-wrapped** in `__post_init__` (S1-03 F-DP-5 precedent). `frozen=True` on the dataclass freezes attribute reassignment; `MappingProxyType` blocks inner mutation. Without the wrapper, a held reference to the inner `dict` bypasses the freeze (Design-Patterns F-DP-5).

- **`load_tier_config` lives in `tier_config.py`, not `promotion.py`.** Functional-core / imperative-shell separation: the gate is pure logic; the loader is I/O (`pyyaml`). Colocating them regresses on the S1-03 / S2-01 precedent and grows `promotion.py`'s cold-start footprint (Design-Patterns F-DP-3).

- **`evaluate` is pure** (no `self.<attr>` assignment). Pinned structurally by AC-15's AST fence — symmetric to the `apply` fence. A future "memoize the verify result" optimization would break the per-call evidence contract; the fence makes the temptation impossible.

- **Floating-point comparison `lower_bound_95 >= threshold`** — use `>=` directly. ADR-0002 §Tradeoffs row 5 owns the precision question; introducing `math.isclose` or epsilons adds a third statistic operators must reason about. Boundary test (AC-12) pins `>=` vs `>`.

- **Block-severity reason ordering.** `report.block_severity_failure_modes` is already deduped (per ADR-0004), but the order from the runner is not specified to be deterministic. Emit reasons in `sorted(report.block_severity_failure_modes)` order — load-bearing for ADR-0002 §Consequences "byte-identical across reruns" and the Phase 11 PR-provenance equality (Test-Quality F-TQ-8 + AC-7).

- **`isolation_class` window check:** the homogeneity check counts each distinct value across `(evidence_window + (report,))`. Single-report (empty window) trivially homogeneous (set size 1). When mismatch: emit ADR-0010's exact reason format `f"isolation_class mismatch in evidence window: subprocess={N1}, microvm={N2}"` — counts in `Literal`-declaration order (`"subprocess"` first, then `"microvm"`). Foresight: a future third class extends the format to `..., <name>={N3}` in `Literal`-declaration order (ADR-0010 §Tradeoffs row 5).

- **`reasons` is a `tuple`, not a `list`.** S1-02 specifies `PromotionVerdict.reasons: tuple[str, ...]` and AC-11 pins the annotation. Build a `list` internally; return `tuple(...)`. Pydantic's coercion *would* convert a returned `list` silently, but the unit test pins `type(verdict.reasons) is tuple` — defense-in-depth against a future Pydantic upgrade tightening coercion.

- **The AST audits (AC-15 + AC-19) are the "fence" pattern from Phase 0** — codify the invariant in a test that walks the source. A future contributor cannot add `if force_override: return None` to `apply` (AC-19 blocks branching) or `self._cache = ...` to `evaluate` (AC-15 blocks self-mutation) without breaking the relevant fence. `textwrap.dedent` is required to make `ast.parse` accept method source — the test will silently `IndentationError` otherwise (Test-Quality F-TQ-5).

- **`PromotionMustBeHumanAuthorized` message:** include verbatim the path operators must follow — `docs/trust-tiers.yaml`, `CODEOWNERS`, `pull request` / `PR`, "human", and either `0015` or `calibration` (the calibration ADR pointer). Operators who hit this exception in CI should not have to grep the docs (AC-17 pins every substring).

- **`PromotionVerdict` construction is forbidden via `model_construct`.** Use the full constructor with all eight required fields. `model_construct` bypasses Pydantic validation — including the no-default `requires_human_approval` discipline (S1-02 AC-7a). The helper `_assert_verdict_invariants` in the test suite pins `isinstance(verdict, PromotionVerdict)` so mock objects also fail.

- **Stub `TaskClass` construction in tests uses `@register_task_class` into a fresh `TaskClassRegistry()`.** Direct dataclass construction with a plain `dict` for `min_cases_for_promotion` / `failure_mode_taxonomy` bypasses S1-03's `MappingProxyType` normalization (S1-03 AC-9). Using the decorator path keeps fixtures faithful to production wiring.

- **`audit.verify` returns; never raises.** S2-04 HARDENED AC-4 is explicit. Do NOT wrap `self._audit_verify(...)` in `try/except`. `ChainTamperDetected` is raised only by `write_run_record`, not by `verify` (identical drift to S4-03 F-CON-2 — flagged proactively here).
