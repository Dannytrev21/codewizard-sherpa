# Validation report — S4-04 `PromotionGate.evaluate` + `apply()` raises unconditionally

**Validated:** 2026-06-01
**Validator:** phase-story-validator
**Verdict:** HARDENED
**Findings:** 47 total — 17 block, 22 harden, 8 nit

The story's *goal* (a read-only verdict surface; `evaluate` returns a fully-populated `PromotionVerdict` keyed on `lower_bound_95 >= threshold ∧ passed_count >= floor ∧ no block-severity ∧ chain ok ∧ isolation homogeneous`; `apply` raises unconditionally to operationalize production ADR-0009 "humans always merge") is sound and traces directly to phase ADR-0002 / ADR-0003 / ADR-0004 / ADR-0009 / ADR-0010 and to Phase 5 ADR-0016 §Decision §4. **But the wire-shape claims (`tamper_at` vs `tampered_path`), the `evaluate` signature, the `PromotionVerdict` construction completeness, the isolation-reason format, the `apply` signature, and the AST-fence dedent are all incompatible with the hardened siblings or internally contradictory.** An executor following the story verbatim would (a) build a `_gate` test helper that calls a nonexistent `VerifyResult.tamper_at` field; (b) drift the `evaluate` signature from S4-02's `gate.evaluate(report, target_tier)` HARDENED call site by adding a `task_class=` kwarg; (c) construct a partial `PromotionVerdict` that fails Pydantic validation; (d) emit a `reasons` tuple in three competing formats for the isolation-mismatch case (none matching ADR-0010 §Decision verbatim); (e) ship two contradictory `apply` signatures (`apply(verdict=None, **kwargs)` in AC line 59 vs `apply(*args, **kwargs)` in §Green); (f) ship a structurally-broken AST fence that `IndentationError`s at collection and silently provides no protection. Every issue is patchable in place → **HARDENED**, not RESCUE.

Conflict-resolution priority applied: **Consistency > Coverage > Test-Quality > Design-Patterns**. The dominant lens was Consistency — the story was authored before S2-04 / S4-01 / S4-02 / S4-03 hardened, and inherited several drifts (notably `tamper_at`, which was flagged proactively by the S4-03 validator carrying into S4-04, and the `evaluate` signature divergence from S4-02). The Design-Patterns critic added two AC promotions (registry-as-port DIP seam; deferred `audit_verify` import for cold-start) that were forced by the goal, not gold-plating. Several pattern findings (conditions-as-registry, `_REASON_FORMATS` catalog) were correctly held as Notes-for-implementer per Rule 2 "three similar lines is better than premature abstraction" with explicit extraction-trigger conditions (the sixth condition / sixth format string — Phase 16's microvm-transition work).

---

## Critic: Consistency (lens: does the story contradict the hardened arch / ADRs / sibling stories?)

### F-CON-1 (BLOCK) — `tamper_at` is not on `VerifyResult`; the field is `tampered_path`

S2-04 HARDENED AC-4 + AC-13 pin the field as **`tampered_path: Path | None`**. The original S4-04 used `tamper_at` in six places: AC line 57 (reasons-format), §TDD line 121 (`_gate` signature), line 125 (`SimpleNamespace`), line 169 / 201 (test invocations), line 173 (substring assertion). The S4-03 validation (line 16-18) explicitly flagged this drift carrying forward: *"S4-04 (also `Ready`, not yet validated) shares this drift — flagged for the next validator pass."* **Resolution:** every occurrence renamed to `tampered_path`; the reasons-format string becomes `"audit.verify().ok is False at {tampered_path}: {reason}"` (richer — adds the `reason` field too, addressed in F-CON-2 and Coverage F-COV-1 sibling).

### F-CON-2 (BLOCK) — `fake_verify` return shape omits `reason` and uses wrong field name

The original §TDD plan `fake_verify` returned `SimpleNamespace(ok=verify_ok, tamper_at=tamper_at, verified_complete=10, verified_incomplete=0)` — missing `reason: str | None` (S2-04 AC-4) and using the wrong field name. **Resolution:** rewrote `_fake_verify_factory` to construct all five `VerifyResult` fields including `reason`. The `_gate` helper now accepts `tampered_path` (a `Path`, not a string) and `reason`. The reasons-format string surfaces `result.reason` in the operator-actionable diagnostic.

### F-CON-3 (BLOCK) — `evaluate(...)` signature contradicts S4-02 HARDENED call site

S4-02 (HARDENED) commits to the two-positional call `gate.evaluate(report, target_tier)`. The original S4-04 advertised `evaluate(report, target_tier, *, evidence_window=())` in §Goal but passed `task_class=stub_task_class_silver_min_25` as a third kwarg in every TDD test call. The TDD tests' kwarg was not declared by any AC, and the production caller (S4-02) cannot supply it. The phase-arch doc carries two stale signatures of its own (line 187 `evaluate(name, current_tier, report)`; line 639 `evaluate(self, task_class_name, current_tier, report)`) — both diverge from the story. **Resolution:** pinned the production signature as `evaluate(self, report, target_tier, *, evidence_window=()) -> PromotionVerdict` (AC-4). The `TaskClass` is resolved INSIDE `evaluate` via `self._registry.get(report.task_class)` — the gate's `__init__` already takes `registry: TaskClassRegistry | None = None` per AC-2. Tests construct the gate with a seeded `TaskClassRegistry()` via `@register_task_class` (faithful to S1-03 AC-9 `MappingProxyType` normalization). The phase-arch stale signatures are flagged for a doc-sweep PR (Surfaced section).

### F-CON-4 (BLOCK) — `PromotionVerdict` construction in §Green is incomplete; will fail Pydantic validation

The original §Green return showed `PromotionVerdict(evidence_sufficient=not reasons, reasons=tuple(reasons) if reasons else ("all conditions met",), ...)`. S1-02 HARDENED AC-7 + AC-7a + AC-13 pin EIGHT required fields including `requires_human_approval: Literal[True]` (no default — omission raises) and `extra="forbid"`. A constructor missing any required field raises `ValidationError`. **Resolution:** AC-10 now spells out all eight fields with explicit values; §Green's sketch constructs every field; the test `_assert_verdict_invariants` helper asserts each of `task_class`, `current_tier`, `target_tier`, `lower_bound_95`, `threshold_at_target`, `requires_human_approval is True` on every six-condition test (Coverage F-COV-1 + F-COV-10 + Test-Quality F-TQ-3 merged).

### F-CON-5 (BLOCK) — `reasons` format for isolation mismatch contradicts ADR-0010

The original story used three competing wordings, none matching ADR-0010 §Decision (line 27): `"isolation_class mismatch in evidence window: subprocess={N1}, microvm={N2}"`. The drifts were AC line 51 (paraphrased), AC line 58 (`"isolation_class mixed in evidence window: {sorted_set}"`), and AC line 28 (`"isolation_class mixed: subprocess and microvm in window"`). **Resolution:** AC-8 condition #5 adopts ADR-0010's exact format. The `test_evaluate_false_when_isolation_class_mixed` test asserts exact-tuple equality `verdict.reasons == ("isolation_class mismatch in evidence window: subprocess=1, microvm=1",)`. Notes-for-implementer documents the foresight for a future third `Literal` member (`subprocess={N1}, microvm={N2}, <name>={N3}` in declaration order; out of scope today).

### F-CON-6 (HARDEN) — `reasons` lower-bound format diverges from ADR-0002 example but is richer

ADR-0002 §Consequences line 46 carries an abbreviated example `("lower_bound_95=0.78 < threshold=0.80",)`. The story specifies `"lower_bound_95={x:.3f} < threshold[{tier}]={y:.3f}"` — richer (decimal-pinned, tier-bracketed). **Resolution:** keep the richer format as the contract; explicit Notes-for-implementer language says ADR-0002's example is illustrative and this story owns the contract. Same discipline applies to the `passed_count` shortfall format. Flagged for a future ADR-0002 amendment that codifies the strings (Surfaced section).

### F-CON-7 (HARDEN) — `evidence_window` is a story invention; no HARDENED caller supplies it

Phase-arch line 639 omits `evidence_window`; S4-02's HARDENED call site is `gate.evaluate(report, target_tier)` (empty window implicit). ADR-0010 §Decision requires the homogeneity check but doesn't pin who supplies the window. **Resolution:** keep `evidence_window: tuple[BenchRunReport, ...] = ()` as a kwarg with default `()`. S4-02's empty-window call site degrades gracefully — the homogeneity check is trivially True (set size 1). AC-6 condition #5 documents this degradation explicitly. Out-of-scope notes that window-selection logic is deferred to Phase 5 / Phase 11.

### F-CON-8 (BLOCK) — `apply()` signature contradicts itself between AC and §Green

AC line 59 (`apply(verdict: PromotionVerdict | None = None, **kwargs)`) vs §Green line 296 (`apply(self, *args, **kwargs)`). The narrow signature is *worse*: it gives callers an autocomplete-friendly `verdict=` parameter that lies about the API. **Resolution:** AC-16 pins `apply(self, *args: object, **kwargs: object) -> NoReturn` (the open form). Design-Patterns F-DP-8 elaborated the rationale: open `*args/**kwargs` is the intentional non-affordance; the narrow form invites a "well-meaning" `force: bool` parameter addition that would in turn invite a guarded `return`.

### F-CON-9 (BLOCK) — `TierConfigInvalid` argument tuple shape needs pinning

The story raised `TierConfigInvalid(unknown_tier, available_tiers)` per AC-2 but §TDD only asserted `"platinumm" in str(exc_info.value)` — a mutant `TierConfigInvalid("platinumm")` (single-arg) would pass. S1-01 HARDENED makes the marker positional-only (`.args`-routed) and explicitly delegates argument-tuple shape to raisers. S4-04 is the right owner. **Resolution:** AC-3 + AC-5.2 / AC-5.4 / AC-5.5 pin `exc.args == (unknown_tier, tuple(sorted(available_set)))` for every `TierConfigInvalid` raise; the `available_set` is a deterministic sorted tuple for operator "did you mean" diagnostics.

### F-CON-10 (HARDEN) — `IncompleteReportForPromotion` args shape unpinned

AC line 44 raised `IncompleteReportForPromotion(run_id)`. **Resolution:** AC-5.1 pins `exc.args == (report.run_id,)`; the test `test_evaluate_raises_on_incomplete_report` asserts the exact tuple.

### F-CON-11 (HARDEN) — `PromotionMustBeHumanAuthorized` args shape + message-content discipline

§TDD asserted `"trust-tiers.yaml" in msg` and `"ADR" in msg or "PR" in msg`. A mutant message `"call denied — see docs/development/internal-PR-checklist for the trust-tiers.yaml refactor"` passes both checks while pointing at the wrong path. **Resolution:** AC-17 pins five required substrings (`docs/trust-tiers.yaml`, `CODEOWNERS`, `0015` or `calibration`, `PR` or `pull request`, case-insensitive `human`). AC-18 pins `len(exc.args) == 1 and isinstance(exc.args[0], str)`. The test `test_apply_message_pins_canonical_escalation_path` asserts each substring individually.

### F-CON-12 (BLOCK) — `Status:` line format does not match HARDENED siblings

S4-03's validation report sets `**Status:** HARDENED (phase-story-validator, 2026-06-01)`. **Resolution:** story's Status line updated to match.

### F-CON-13 (HARDEN) — `Depends on:` annotation missing S1-03

Tests depend on a registry-constructed `TaskClass` fixture; the gate validates `registry.all_task_classes()`. **Resolution:** S1-03 added to the dependency list with explicit contracts named (`min_cases_for_promotion: Mapping[str, int]`, `failure_mode_taxonomy`, `MappingProxyType`, `TaskClassRegistry.get(name)` raising `TaskClassNotFound`).

### F-CON-14 (HARDEN) — `audit.verify` is documented to return, never raise; story doesn't pin this anchor

S2-04 AC-4 is explicit: `verify` returns on every code path. The original §Implementation outline did not anchor "returns, never raises" — risking a `try/except` wrapper from habit (identical to S4-03 F-CON-2). **Resolution:** AC-6 condition #4 says explicitly "with **no surrounding try/except**". Implementation outline + Notes-for-implementer reinforce. The Context section also calls this out so an executor reading top-to-bottom encounters the anchor before reaching the code.

### F-CON-15 (HARDEN) — Stub `TaskClass` fixture must honor S1-03 immutability

The original fixture description was "a TaskClass with `min_cases_for_promotion={"bronze": 10, "silver": 25}`" — a plain dict. S1-03 AC-9 + AC-9a require `MappingProxyType` normalization. Direct dataclass construction with a plain dict would bypass. **Resolution:** Files-to-touch + Notes-for-implementer pin that fixtures construct `TaskClass` via `@register_task_class` into a fresh `TaskClassRegistry()` (the decorator path normalizes). The `_stub_registry_with_vuln` helper in the test suite uses this path.

### F-CON-16 (NIT) — `"block-severity failure: {code}"` reasons format ownership

ADR-0004 pins the data shape but not the human-format reasons string. The story is the first owner. **Resolution:** Notes-for-implementer documents that this story owns the format; any change requires an ADR amendment or revising this story.

---

## Critic: Coverage (lens: do the ACs collectively guarantee the goal? edge cases?)

### F-COV-1 (BLOCK) — `PromotionVerdict` field-population invariants not in ACs

The original story constrained only `evidence_sufficient` and `reasons` (2 of 8 fields). An executor could ship `PromotionVerdict(task_class="", current_tier="", target_tier="", evidence_sufficient=True, reasons=("all conditions met",), lower_bound_95=0.0, threshold_at_target=0.0, requires_human_approval=True)` and pass all listed ACs. **Resolution:** AC-10 pins all eight fields with the explicit source-of-value (Consistency F-CON-4 merged).

### F-COV-2 (BLOCK) — `current_tier` lookup path is undefined; missing-mapping case unspecified

The verdict requires `current_tier`. The original signature did not show how it's derived. **Resolution:** AC-5.5 pins the missing-mapping behavior as `TierConfigInvalid`; AC-10 pins the lookup as `tier_config.current_tiers[report.task_class]`.

### F-COV-3 (BLOCK) — `task_class` not in `evaluate` signature, but verdict requires it

Subsumed by Consistency F-CON-3. Same resolution.

### F-COV-4 + F-COV-5 (BLOCK) — `target_tier not in tier_config.thresholds` / `not in task_class.min_cases_for_promotion`

Bare `KeyError` on raw `[]` lookup vs ADR-0003 "fail loud" intent. **Resolution:** AC-5.2 + AC-5.4 raise `TierConfigInvalid` with `(target_tier, available_set)` at the top of `evaluate`, before any condition check.

### F-COV-6 (HARDEN) — Empty `evidence_window` edge case not in AC matrix

**Resolution:** new test `test_evaluate_empty_evidence_window_passes_isolation_check`; AC-6 condition #5 explicit about set-size-1 degeneration.

### F-COV-7 (HARDEN) — Single-element matching-window not in AC matrix

**Resolution:** new test `test_evaluate_homogeneous_window_passes`.

### F-COV-8 (HARDEN) — `reasons` order not pinned

Audit reproducibility (ADR-0002 §Consequences). **Resolution:** AC-7 pins the deterministic order (lower_bound, passed_count, block-severity sorted by code, audit, isolation). The all-six-fail test `test_evaluate_enumerates_every_failing_condition_in_pinned_order` asserts exact-tuple equality on the ordered reasons.

### F-COV-9 (HARDEN) — Block-severity per-code dedup + sort not pinned

**Resolution:** AC-7 #3 pins `sorted(report.block_severity_failure_modes)` order. The block-severity test asserts the *alphabetically sorted* tuple even though codes are passed in non-sorted order.

### F-COV-10 (BLOCK) — `requires_human_approval=True` invariant unverified

**Resolution:** merged into AC-10 + the `_assert_verdict_invariants` helper. Every six-condition test asserts `verdict.requires_human_approval is True`.

### F-COV-11 (HARDEN) — Floating-point boundary `lower_bound_95 == threshold` not tested

**Resolution:** AC-12 pinned the boundary; tests `test_evaluate_lower_bound_equal_to_threshold_passes` + `test_evaluate_lower_bound_just_below_threshold_fails`.

### F-COV-12 (HARDEN) — `passed_count == floor` boundary not tested

**Resolution:** AC-12 pinned; tests `test_evaluate_passed_count_equal_to_floor_passes` + `test_evaluate_passed_count_one_below_floor_fails`.

### F-COV-13 (BLOCK) — Isolation reason string format drifts from ADR-0010

Subsumed by Consistency F-CON-5. Same resolution.

### F-COV-14 (BLOCK) — `audit.verify` reason references nonexistent `tamper_at` field

Subsumed by Consistency F-CON-1. Same resolution.

### F-COV-15 (HARDEN) — `BenchRunReport.complete` post-condition (condition #5) is dead code

The original story listed six verdict conditions, but condition #5 (`complete is True`) is unreachable because the gate raises `IncompleteReportForPromotion` first. The mutation-style AC "for each of the six conditions, the test suite has a fixture where exactly that condition fails" is unsatisfiable for #5. **Resolution:** verdict conditions renumbered to **five** (#5 removed; the `complete` check is the AC-5.1 raise, not a verdict-time condition). AC-13's property test iterates over five booleans, not six.

### F-COV-16 (HARDEN) — Happy-path `reasons` literal ambiguous

The original allowed both `()` and `("all conditions met",)`. **Resolution:** AC-9 pins `("all conditions met",)` exactly. Test asserts exact-tuple equality.

### F-COV-17 (HARDEN) — `PromotionGate.__init__` parameter list not in AC

`audit_verify` was introduced in §Implementation outline but no AC enumerated it. **Resolution:** AC-2 + AC-2a pin the full constructor signature including the keyword-only `audit_verify` parameter and the deferred-import discipline (Design-Patterns F-DP-9 merged).

### F-COV-18 (NIT) — `promotion_evaluated` structured log AC missing

**Resolution:** §Implementation outline + §Green sketch include the `_LOG.info("promotion_evaluated", ...)` emission with the six pinned fields. Not promoted to AC (no observable behavior change at the verdict surface), but the executor-facing prose is now explicit.

### F-COV-19 (NIT) — `passed_count == 0` edge case

Subsumed by AC-12 boundary tests and the property test. The format-string `f"passed_count={x}"` correctly renders `0` (no zero-pad).

### F-COV-20 (NIT) — `evidence_window` self-inclusion idempotent on the isolation check

**Resolution:** Notes-for-implementer documents the caller's responsibility for window selection (the gate does not deduplicate by `run_id`).

---

## Critic: Test-Quality (lens: would the TDD plan catch a wrong implementation?)

### F-TQ-1 (BLOCK) — `BenchRunReport.model_construct(...)` bypasses validation

The original helper used `model_construct` and elided required fields. A mutant `def evaluate(...): return PromotionVerdict(..., evidence_sufficient=True, ...)` ignoring `report` entirely would pass because no test exercises `model_validate` round-trips. **Resolution:** `_make_report` rewritten to use full validated `BenchRunReport(...)` construction with every required field populated (Test-Quality F-TQ-1 verbatim). The added guard test from the critic was rolled into the property-based suite (a property test that fails to construct the report at every cell would surface the mismatch loudly).

### F-TQ-2 (BLOCK) — Happy-path `assert verdict.reasons in ((), ("all conditions met",))` is tautological

Subsumed by Coverage F-COV-16. Same resolution: AC-9 pins exact-tuple equality.

### F-TQ-3 (BLOCK) — Happy-path test asserts only 2 of 8 verdict fields

Subsumed by Coverage F-COV-1 / F-COV-10. Same resolution: every six-condition test calls `_assert_verdict_invariants`.

### F-TQ-4 (BLOCK) — `len(reasons) >= 4` is too lax; padding-mutant passes

**Resolution:** the new `test_evaluate_enumerates_every_failing_condition_in_pinned_order` asserts EXACT tuple equality on the six-element reasons tuple (lower_bound, passed_count, 2 block-severity entries, audit, isolation). No `>=` checks remain. A padding mutant fails on exact equality; a dedup-via-set mutant fails on alphabetical order.

### F-TQ-5 (BLOCK) — AST audit's `inspect.getsource` source is indented; `ast.parse` raises silently

The original heuristic `if not src.startswith("def") else src` was wrong because `getsource` returns indented method source. **Resolution:** `test_apply_is_structurally_unconditional` uses `src = textwrap.dedent(inspect.getsource(PromotionGate.apply))` and parses cleanly. The `textwrap.dedent` is called out as load-bearing in AC-19 and in Notes-for-implementer (without it, the structural defense provides zero protection — silent fail at collection).

### F-TQ-6 (BLOCK) — AST audit misses early-return mutants

The original test only excluded `If` / `Try`. A `return None` followed by a dead `raise` ships. **Resolution:** the new fence asserts `len(func_def.body) == 1` AND `isinstance(func_def.body[0], ast.Raise)`. Catches every early-return / pass-only / shadow mutant. Defense-in-depth: also walks the subtree to exclude `If` / `Try` / `For` / `While` / `AsyncFor` / `With` / `AsyncWith`.

### F-TQ-7 (HARDEN) — No test pins `verdict.reasons` is a `tuple`, not a `list`

**Resolution:** `_assert_verdict_invariants` asserts `type(verdict.reasons) is tuple` — defense against a future Pydantic-coercion tightening.

### F-TQ-8 (HARDEN) — Block-severity ordering not pinned

Subsumed by Coverage F-COV-9 + F-COV-8. The block-severity test now asserts exact alphabetically-sorted output and the enumerate-every-failing-condition test asserts cross-condition ordering.

### F-TQ-9 (HARDEN) — Adversarial test misses positional `*args`

**Resolution:** AC-20 + `test_apply_raises_for_every_call_shape` (parametrized) covers positional, keyword, mixed, and splat shapes. AC-21 + `test_apply_signature_is_var_positional_plus_var_keyword` pins the open signature via `inspect.Parameter.VAR_POSITIONAL` + `VAR_KEYWORD`.

### F-TQ-10 (HARDEN) — `test_apply_raise_message_names_escalation_path` is too permissive

Subsumed by Consistency F-CON-11. The new test asserts five distinct substrings.

### F-TQ-11 (HARDEN) — No test proves `audit_verify` injection is honored

**Resolution:** AC-14 + `test_evaluate_calls_injected_audit_verify` constructs a spy `audit_verify` that records its invocation, asserts the spy was called exactly once. A mutant ignoring the injection (reaching for `codegenie.eval.audit.verify` directly) fails this test.

### F-TQ-12 (HARDEN) — No property-based test on the all-AND truth table

**Resolution:** AC-13 + `tests/unit/test_promotion_properties.py` use `hypothesis.strategies.booleans()` over five conditions (64 cells; `max_examples=64` covers exhaustively). The assertion is `verdict.evidence_sufficient is (lb AND pc AND no_block AND audit AND iso)`. Any AND→OR mutation surfaces at a non-corner cell.

### F-TQ-13 (HARDEN) — No metamorphic determinism test

**Resolution:** `test_evaluate_deterministic_across_reruns` asserts `v1 == v2 AND v1.model_dump_json() == v2.model_dump_json()` for two `evaluate` calls on identical inputs. Catches any `set`-iteration order mutation.

### F-TQ-14 (HARDEN) — `TierConfigInvalid` args-tuple shape not pinned

Subsumed by Consistency F-CON-9. Same resolution: AC-3 + AC-5.* pin `exc.args == (unknown_tier, tuple(sorted(available_set)))`.

---

## Critic: Design-Patterns (lens: easy to extend by addition?)

### F-DP-1 (HARDEN — Notes only) — Six condition helpers as inline calls vs `_CONDITIONS` registry

Five condition helpers are correct today (Rule 2). **Resolution:** Notes-for-implementer documents the extraction trigger (the sixth condition — Phase 16 microvm-transition record check, or the `--allow-isolation-mix` override per ADR-0010 §Open Q) and cites `_LOCKFILE_PRECEDENCE` as the repo precedent.

### F-DP-2 (HARDEN) — Functional-core reasons accumulation

The original §Refactor described `reasons.append` from each helper (imperative-shell-inside-helpers). **Resolution:** §Implementation outline + §Green sketch + Notes-for-implementer pin the comprehension-at-boundary pattern: each `_check_*` returns `str | None` (or `tuple[str, ...]` for block-severity); `evaluate` collects via a single comprehension. CLAUDE.md "Functional core / imperative shell" discipline.

### F-DP-3 (HARDEN — Files-to-touch + Notes) — `load_tier_config` colocation tangles pure logic with I/O

The original story placed `load_tier_config` in `promotion.py`. S1-03 / S2-01 precedent separates registry-logic from loader-I/O. **Resolution:** new `src/codegenie/eval/tier_config.py` houses `TierConfig` + `load_tier_config`; `promotion.py` carries zero `pyyaml` import. AC-1 + Files-to-touch + AC-2a (cold-start fence) pin the discipline.

### F-DP-4 (HARDEN — promoted to AC) — Registry-as-port DIP seam

The original story passed `task_class=` per call from tests but no AC pinned the production injection path. **Resolution:** promoted to AC-4 (signature pin: no `task_class` parameter). The gate resolves via `self._registry.get(report.task_class)` — DIP-compliant; the registry is constructor-injected with `default_registry` as default. Tests construct the gate with a seeded `TaskClassRegistry()` (S4-02 F-DP-1 elevation precedent).

### F-DP-5 (HARDEN — Notes + TierConfig refactor) — `TierConfig` Mappings must be `MappingProxyType`-wrapped

The original `@dataclass(frozen=True, slots=True)` did not deep-freeze inner Mappings. **Resolution:** AC-1 + AC-1a + Notes-for-implementer pin the `__post_init__` wrapper. Tests `test_tier_config_normalizes_mappings_to_proxy` + `test_tier_config_inner_mutation_raises` + `test_tier_config_external_dict_mutation_does_not_leak` pin the discipline. Mirrors S1-03 F-DP-5.

### F-DP-6 (HARDEN — Notes only) — `_REASON_FORMATS: Final[Mapping[str, str]]` catalog

Five format strings exist today (rule-of-three crossed). **Resolution:** Notes-for-implementer documents the extraction trigger (the sixth format string — same Phase 16 inflection as F-DP-1). Not promoted to AC today because the format strings remain small and the test-quality benefit is not yet load-bearing.

### F-DP-7 (HARDEN — promoted to AC) — `evaluate` purity AST audit (symmetric to `apply` fence)

**Resolution:** AC-15 + `tests/adv/test_promotion_evaluate_is_stateless.py` walks `evaluate`'s AST (after `textwrap.dedent`) and asserts zero `ast.Assign` / `ast.AugAssign` targeting `self.<attr>`. Symmetric to AC-19's `apply` fence. The arch's "evaluate is a pure function" commitment is now structurally pinned.

### F-DP-8 (HARDEN — AC line fix) — `apply()` signature: open `*args/**kwargs` over narrow `verdict=None`

Subsumed by Consistency F-CON-8. Same resolution.

### F-DP-9 (BLOCK — promoted to AC) — Deferred `audit_verify` import for cold-start

**Resolution:** AC-2 + AC-2a + Notes-for-implementer + the new fence test `tests/fence/test_promotion_cold_start.py`. The default `audit_verify` resolves via a module-top `_default_audit_verify` wrapper that imports `verify` **inside the function body**. Pinned by the cold-start fence asserting `codegenie.eval.audit not in sys.modules` and `yaml not in sys.modules` after `import codegenie.eval.promotion`. Mirrors S4-01 / S4-02 / S4-03 cold-start discipline.

### F-DP-10 (NIT) — Named `_distinct_isolation_classes` helper

Surface naming for ADR-0010 coupling. **Resolution:** the implementation has `_check_isolation_homogeneous` as the named helper (functions for each condition are already in AC-8 wording). Sufficient. Not separately surfaced.

### F-DP-11 (HARDEN — Notes + inline guard) — `PromotionVerdict` runtime invariant assertion

**Resolution:** §Green's sketch includes an explicit `if not (...) : raise AssertionError(...)` guard before returning (bare `assert` is banned by `forbidden-patterns`). The invariant: `(evidence_sufficient AND reasons == ("all conditions met",)) OR (not evidence_sufficient AND reasons)`.

### F-DP-12 (NIT — already in Notes) — `audit_verify` testing affordance only

Already pinned in original Notes; re-stated for explicit "do not expose via CLI" discipline.

---

## Research

No findings tagged `NEEDS RESEARCH`. Every pattern (functional-core, MappingProxyType, deferred-import for cold-start, AST-fence with dedent, hypothesis-property over boolean truth-table, S4-03's `_normalize_since` precedent for naming a coupling) is precedented in this repo (S1-02 / S1-03 / S2-04 / S4-01 / S4-02 / S4-03 validation reports). Stage 3 skipped.

---

## Edits applied to the story

- **Status** `Ready` → `HARDENED (phase-story-validator, 2026-06-01)`.
- **Depends-on** rewritten to enumerate specific contracts: S1-01 marker-only positional discipline; S1-02's eight required `PromotionVerdict` fields + `requires_human_approval: Literal[True]` no-default; S1-03's `MappingProxyType` normalization + `TaskClassRegistry.get` raising `TaskClassNotFound`; S2-04's `VerifyResult(ok, verified_complete, verified_incomplete, tampered_path, reason)` returns-not-raises.
- **ADRs-honored** extended with ADR-0010 (canonical isolation reason format named) + production ADR-0015 (calibration ADR cited in `apply` message).
- **Context** rewrote third paragraph to anchor "verify returns, never raises" up-front (preempts the S4-03 F-CON-2 drift).
- **References** rewritten: phase-arch lines flagged as stale (signatures 187 / 639); sibling HARDENED contracts explicitly named with their AC IDs.
- **Acceptance criteria** rewritten end-to-end from 9 ACs to 23 ACs, grouped:
  - AC-1 / AC-1a: `TierConfig` + loader in new `tier_config.py`; `MappingProxyType` immutability (F-CON-5 + F-DP-3 + F-DP-5).
  - AC-2 / AC-2a / AC-3: gate `__init__` signature pin + deferred-import + cold-start fence + startup tier validation (F-COV-17 + F-DP-9 + F-CON-9).
  - AC-4: production `evaluate` signature pinned (no `task_class` kwarg — F-CON-3 + F-DP-4).
  - AC-5: pre-condition raises in fixed order with explicit error args tuples (F-COV-2 / F-COV-4 / F-COV-5 / F-CON-9 / F-CON-10).
  - AC-6: **five** verdict conditions (was six — F-COV-15); each condition's exact source-of-value.
  - AC-7: pinned deterministic reasons order (F-COV-8 + F-TQ-13).
  - AC-8: five format strings pinned to ADR-0002 / ADR-0010 verbatim (F-CON-5 + F-CON-6).
  - AC-9: happy-path literal exact (`("all conditions met",)` — F-COV-16 + F-TQ-2).
  - AC-10: full eight-field `PromotionVerdict` construction (F-COV-1 + F-COV-10 + F-CON-4).
  - AC-11: byte-identical reruns (F-TQ-13).
  - AC-12: boundary discipline (F-COV-11 + F-COV-12).
  - AC-13: hypothesis truth table (F-TQ-12).
  - AC-14: injection spy (F-TQ-11).
  - AC-15: `evaluate` purity AST fence (F-DP-7).
  - AC-16 / AC-17 / AC-18 / AC-19 / AC-20 / AC-21: open `apply` signature + canonical escalation-message substrings + dedented AST fence + call-shape parametrize + signature-introspection fence (F-CON-8 + F-CON-11 + F-DP-8 + F-TQ-5 + F-TQ-6 + F-TQ-9 + F-TQ-10 + F-CON-11).
  - AC-22 / AC-23: red-marker discipline + tool gates.
- **Implementation outline** rewritten step-by-step — `tier_config.py` separation, deferred `_default_audit_verify` wrapper, pure `_check_*` helpers, comprehension-at-boundary collection, full eight-field verdict construction, runtime invariant guard.
- **TDD plan** rewritten in full — six new test files: `test_tier_config.py`, `test_promotion.py`, `test_promotion_properties.py`, `test_promotion_apply_raises.py`, `test_promotion_evaluate_is_stateless.py`, `test_promotion_cold_start.py`. Every helper uses validated `BenchRunReport(...)` construction (no `model_construct` — F-TQ-1). `_assert_verdict_invariants` helper pins the eight-field shape on every call. AST tests use `textwrap.dedent` explicitly. Parametrize covers seven `apply` call shapes.
- **Files to touch** expanded: 2 source files (`tier_config.py` + `promotion.py`) + 6 test files. Each row explains *why* (Design-Patterns + Coverage findings cited inline).
- **Out of scope** expanded to surface the F-DP-1 (`_CONDITIONS` registry) and F-DP-6 (`_REASON_FORMATS` catalog) extraction triggers as Phase-16 milestones; `audit_verify` exposed via CLI explicitly out-of-scope (F-DP-12); `PromotionVerdict` sum-type discipline noted as YAGNI today (F-DP-11).
- **Notes-for-implementer** rewritten — fifteen paragraphs covering asymmetry / reasons discipline + ADR amendments / injection affordance / functional-core / `MappingProxyType` / loader colocation / purity fence / float-comparison / block-severity ordering / isolation format / tuple-not-list / AST-fence dedent / escalation message / `model_construct` forbidden / stub fixture via decorator / `audit.verify` returns-not-raises.

## Surfaced, not auto-fixed

- **`phase-arch-design.md` lines 187 + 639** carry two stale `evaluate` signatures (`evaluate(name, current_tier, report)` and `evaluate(self, task_class_name, current_tier, report)`). Both contradict the HARDENED S4-02 call site (`gate.evaluate(report, target_tier)`) and this story's now-pinned `evaluate(report, target_tier, *, evidence_window=())`. Flag for a doc-sweep PR; not auto-edited (Rule 3 — surgical; one story per invocation).
- **ADR-0002 §Consequences line 46** carries an abbreviated reasons-format example `("lower_bound_95=0.78 < threshold=0.80",)`. This story owns the richer contract `"lower_bound_95={x:.3f} < threshold[{tier}]={y:.3f}"`. Flagged for a future ADR-0002 amendment that codifies the strings.
- **`phase-arch-design.md` line 652** documents `TierConfigInvalid(unknown_tier)` — single-arg shape. The hardened S1-01 marker discipline + this story pin two-arg `(unknown_tier, available_tiers)`. Flagged for the same doc-sweep PR.
- **The rule-of-three trigger for `_CONDITIONS` + `_REASON_FORMATS` extraction** is logged in Notes-for-implementer + Out-of-scope. Whoever implements the sixth condition (Phase 16 microvm-transition or the `--allow-isolation-mix` override) should propose extraction in their story. Until then, intentional inline correctness is correct per Rule 2.
- **`PromotionVerdict` could be a tagged-union sum type** (`EvidenceSufficient | EvidenceInsufficient`) making `evidence_sufficient=True ∧ non-empty reasons` structurally unrepresentable. The wire shape is frozen by S1-02 — out of scope. The runtime invariant guard inside `evaluate` is the substitute (Design-Patterns F-DP-11).
