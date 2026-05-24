# Validation report: S7-02 — `rag_query_builder` plugin recipe

**Validated:** 2026-05-24
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S7-02 ships the npm plugin's `rag_query_builder.py` — the plugin-scoped artifact `SolvedExampleRetriever` (S5-01) consumes via constructor injection to translate `(advisory, repo_ctx)` into the typed `Query` model (S1-04) and to render the canonical pipe-separated embedding text per arch §Process view Scenario 1. The goal is sound and traces to phase-arch Component 9, S5-01 line 33 + AC-1, S1-04 AC-3, High-level-impl Step 5/7, and production-ADR-0031.

The original draft was **not executor-ready**. It carried multiple block-level contradictions with already-hardened sibling stories and load-bearing CLAUDE.md commitments: (1) the entire `query_text_builder` peer callable mandated by S5-01 was silently dropped; (2) the `Query` field shape contradicted S1-04 in five ways (raw `str` for `cve_id`, a non-existent `version_constraint` field, wrong `task_class`/`language` literal values, missing required `affected_package`/`failure_mode` fields); (3) a non-existent `RagQueryBuilder` Protocol was cited as the contract; (4) `Pydantic v2 frozen ⇒ hashable` is false, breaking the determinism test; (5) the wiring point named "the plugin's TCCM" instead of the `transforms()` factory S7-01 established; (6) ADR-0003 was misattributed (its path-scoped fence does not cover `plugins/`); (7) the `failure_mode: FailureModeTag` derivation was undefined — a load-bearing gap with no in-repo spec. All are fixable in place by adopting sibling-story precedents (S1-04, S5-01, S7-01), so the verdict is **HARDENED** with explicit pre-execution caveats.

**54 findings — 17 block, 29 harden, 8 nit.** One finding tagged `NEEDS RESEARCH` (K10/C4/D7 — `failure_mode` derivation policy); resolved inline by picking the `Final[FailureModeTag] = "build_break"` constant (Simplicity First) with a Rule-7 surface in Notes for future parametrization. No external research was required — all decisions resolve against in-repo material.

## Context brief

- **Story promise:** Land plugin-resident `rag_query_builder.py` exporting `build(advisory, repo_ctx) -> Query` AND `render_query_text(q: Query) -> str` as pure free functions; wire both into the retriever via the plugin's `transforms()` factory composition root.
- **Phase constraints (S5-01 HARDENED + S7-01 HARDENED + S1-04 HARDENED):** the retriever's constructor takes BOTH callables (S5-01 line 71); the `Query` model has six S1-04 fields exactly; the composition root is the plugin's `transforms()` factory (S7-01 line 195); the plugin directory `--`-to-`_` import-resolution mechanism is documented in `plugins/.../__init__.py` (S7-01 AC-FILE).
- **Sibling constraints:** S7-01 must be GREEN before S7-02 executes (S7-01 ships the plugin directory + import shim + `transforms()` factory). As of 2026-05-24 S7-01 is HARDENED but not GREEN.
- **Open ambiguities after edit:** `CveAdvisory` shape is not yet specified in any HARDENED story — implementer must read whichever Phase-3/Phase-4 story finally lands it and surface a Rule-7 conflict if `advisory.id` is not `CveId`-typed.

## Findings by critic

### Coverage critic (15 findings — 4 block, 9 harden, 2 nit)

- **C1 (block) — `query_text_builder` is completely missing.** S5-01 line 33 + AC-1 mandate two injected callables; story ships only `build`. After this story lands, the retriever cannot construct embedding text. **Fix:** added AC-RENDER requiring `render_query_text(q: Query) -> str` in the same module with canonical text per arch §Scenario 1.
- **C2 (block) — `Query` field shape contradicts S1-04 HARDENED.** Story prescribed `cve_id: str` + `version_constraint: SemverString`. S1-04 ships six fields exact with newtypes. **Fix:** AC-FIELDS rewritten to the six S1-04 fields using newtype constructors.
- **C3 (block) — `affected_package: PackageId` derivation unspecified.** Story silent on how the builder reads the affected package from `CveAdvisory`. **Fix:** AC-PACKAGE-DERIVATION added with explicit zero/one/many handling.
- **C4 (block) — `failure_mode: FailureModeTag` derivation unspecified.** Story silent; `failure_mode` is required and Literal-typed. **Fix:** AC-FAILURE-MODE pins `_FAILURE_MODE_DEFAULT: Final[FailureModeTag] = "build_break"`; Rule-7 surface in Notes.
- **C5 (block) — Wiring point names contradict S7-01.** Story said "the plugin's TCCM" or "__init__.py". S7-01 established `transforms()` factory. **Fix:** AC-WIRING-FUNCTIONAL points at the same composition root.
- **C6 (harden) — `Query.digest()` is the determinism contract; story tests `hash()` instead.** **Fix:** AC-DIGEST-DETERMINISM uses `digest()`; AC-MODEL-DUMP-EQUALITY uses `model_dump_json()`. The `hash()` assertion is explicitly forbidden.
- **C7 (block) — Implementation outline re-asserts the S1-04 violation.** **Fix:** outline §4 rewritten with the six canonical S1-04 fields + newtype constructors + Final constants.
- **C8 (harden) — `task_class` value mismatch with S1-04.** Story used `"vulnerability-remediation"`; S1-04 uses `"vuln_remediation"`. **Fix:** AC-VALUES pins the canonical Phase-2 `TaskClassId` value; Notes call out the distinction from `PluginId`.
- **C9 (harden) — Empty/malformed `CveAdvisory` cases under-specified.** **Fix:** AC-PACKAGE-DERIVATION covers zero/one/many; Notes cover ecosystem-mismatch and malformed-cve-id surfacing.
- **C10 (harden) — ACs not individually verifiable (e.g., "surface a conflict").** **Fix:** "surface a conflict" instructions moved into Notes-for-implementer; ACs are now binary-verifiable with concrete tests or subprocess-mypy fixtures.
- **C11 (harden) — No structural-conformance test for the injected callable.** **Fix:** AC-WIRING-STRUCTURAL adds subprocess-`mypy --strict` fixture mirroring S1-03 AC-9 / S7-01 AC-PROTOCOL-CONFORMANCE.
- **C12 (harden) — Goal admits "free function or @dataclass callable" — under-constrained.** **Fix:** Goal + AC-FILE pin **free function only**; Notes-for-implementer explain why (stateless; matches the bare-Callable Protocol; `npm_lockfile._classify_jail_result` precedent).
- **C13 (block, follows C1) — Out-of-scope #2 contradicts ownership.** **Fix:** Out-of-scope rewritten; embedding-text concatenation moved into scope (AC-RENDER).
- **C14 (nit) — `RepoContext` unused by the corrected field set.** **Fix:** Notes document `del repo_ctx` pattern + cross-plugin Protocol justification.
- **C15 (harden) — `test_build_returns_typed_query` doesn't check all six fields.** **Fix:** TDD plan now asserts every field; parametrized field-by-field perturbation test added.

### Test-Quality critic (14 findings — 6 block, 6 harden, 2 nit)

- **T1 (block) — `hash(q1) == hash(q2)` assertion is brittle.** Pydantic v2 `frozen=True` does not auto-implement `__hash__`. **Fix:** swap to `digest()` + `model_dump_json()` equality; explicit ban in AC-MODEL-DUMP-EQUALITY.
- **T2 (block) — `test_missing_package_id_raises` checks wrong exception class.** `ValueError` vs `ValidationError` conflation. **Fix:** AC-PACKAGE-DERIVATION pins defensive `ValueError` raise before `Query(...)`; test pinpoints the raise origin.
- **T3 (block) — No test pins exact field-by-field values; "always-return-fixed-Query" mutant survives.** **Fix:** TDD plan adds parametrized field-by-field assertion + perturbation test.
- **T4 (block) — `test_distinct_cves_yield_distinct_queries` too weak.** **Fix:** field-by-field equality against expected `Query` literal kills the "only cve_id varies" mutant.
- **T5 (block) — No test for `failure_mode` derivation.** **Fix:** AC-FAILURE-MODE pins the constant; test asserts both `_FAILURE_MODE_DEFAULT` constant value AND the resulting `Query.failure_mode`.
- **T6 (block) — Wiring AC has zero tests.** **Fix:** Tier-6 integration test (`tests/integration/test_rag_query_builder_wired_into_retriever.py`) asserts `retriever.query_builder is rag_query_builder.build` identity.
- **T7 (harden) — AST f-string fence misses BinOp Add + `.format()`.** **Fix:** AC-NO-FSTRING-IN-BUILD mirrors S5-01 AC-3 — bans `JoinedStr`, `BinOp(Add)` over string operands, `.format()` calls; inspects only `build` body (not `render_query_text`).
- **T8 (harden) — Import-fence test misses relative imports.** **Fix:** AC-FENCE-IMPORT walker mirrors S7-01 AC-FENCE-IMPORT (handles `ImportFrom(level>0)`, `ImportFrom(module=None)`, alias names); forbidden set expanded to match production fence.
- **T9 (harden) — No Hypothesis purity property.** **Fix:** Tier-3 Hypothesis test (`tests/property/test_rag_query_builder_pure.py`) — same input ⇒ same digest across 100 draws; metamorphic relation on `cve_id`.
- **T10 (harden) — No test for `Query.digest()` stability.** **Fix:** AC-DIGEST-DETERMINISM + Tier-1 + Tier-3 cover it.
- **T11 (harden) — `test_build_returns_typed_query` partial coverage of fields.** **Fix:** subsumed by T3.
- **T12 (harden) — `test_build_is_deterministic` uses two-call sample.** **Fix:** Tier-3 Hypothesis promotes to 100-draw property.
- **T13 (nit) — Test for class vs free-function shape.** **Fix:** AC-SHAPE + `test_build_signature` pin via `inspect.signature`.
- **T14 (nit) — Hardcoded plugin import path may break.** **Fix:** AC-FILE references the same import shim S7-01 documents.

### Consistency critic (12 findings — 5 block, 6 harden, 1 nit; K10 was NEEDS RESEARCH)

- **K1 (block) — Non-existent `RagQueryBuilder` Protocol cited.** **Fix:** AC-1 rewritten to bare `Callable[[CveAdvisory, RepoContext], Query]` per S5-01 line 71; all Protocol references deleted; structural conformance via subprocess-mypy.
- **K2 (block) — Missing `query_text_builder` deliverable.** **Fix:** AC-RENDER added (paired with C1/D2 fix).
- **K3 (block) — `Query` field shape contradicts S1-04 in five ways.** **Fix:** AC-FIELDS + AC-VALUES rewrite both shape and literal values.
- **K4 (harden) — Composition root contradicts S7-01.** **Fix:** AC-WIRING-FUNCTIONAL points at `transforms()` factory.
- **K5 (harden) — ADR-0003 fence misattribution.** **Fix:** Notes adopt S7-01 framing ("primary control, not defense-in-depth"; `plugins/` outside ADR-0003 scope).
- **K6 (block) — Plugin directory + recipe layout do not yet exist.** **Fix:** Status line + Depends-on call out S7-01-must-be-GREEN precondition; "mirror existing recipe" cue deleted.
- **K7 (harden) — `ValueError` vs `ValidationError` mismatch.** **Fix:** AC-PACKAGE-DERIVATION pins defensive `ValueError` before `Query(...)`.
- **K8 (harden) — Import path ignores `--` resolution shim.** **Fix:** AC-FILE + Notes name the S7-01 shim explicitly.
- **K9 (harden) — "Frozen Pydantic supports hashing" claim is wrong.** **Fix:** AC-MODEL-DUMP-EQUALITY explicitly forbids `hash()`; Notes explain.
- **K10 (block, NEEDS RESEARCH → resolved inline) — `failure_mode` derivation gap.** **Resolution:** No external research needed; this is an internal modeling choice between (a) `Final` constant default and (b) injected classifier callable. Picked (a) `"build_break"` per Simplicity First (Rule 2) — no real signal exists at initial-plan time to drive (b); matches closed-data-driven dispatch precedent (`_LOCKFILE_PRECEDENCE` in `npm_lockfile.py`). Surfaced as Rule-7 conflict in Notes-for-implementer for future ADR amendment if `CveAdvisory` grows a typed `failure_mode` field.
- **K11 (harden) — `task_class="vulnerability-remediation"` would crash AST source-scan.** **Fix:** subsumed by K3/C8.
- **K12 (nit) — `tests/fence/test_kernel_frozen.py` framing inconsistent with S7-01.** **Fix:** AC-KERNEL-FROZEN adopts S7-01 `git diff --name-only` language.

### Design-Patterns critic (13 findings — 2 block, 8 harden, 3 nit)

- **D1 (block) — Primitive obsession on `cve_id: str`, etc.** **Fix:** AC-FIELDS + AC-NO-RAW-STR enforce newtype constructors at every domain-identifier site in `Query(...)` calls.
- **D2 (block) — Silent on `query_text_builder`.** **Fix:** AC-RENDER + Goal updated to ship both free functions.
- **D3 (harden) — Free-function vs dataclass ambiguity.** **Fix:** Goal + AC-FILE pin free-function-only; Notes explain.
- **D4 (harden) — Missing YAGNI guard against premature registry.** **Fix:** Out-of-scope + Notes explicitly forbid `QueryBuilderRegistry`; per-plugin free-function pair is the Open/Closed seam.
- **D5 (harden) — Composition root under-specified.** **Fix:** subsumed by K4/C5.
- **D6 (harden) — No functional-core purity AC.** **Fix:** AC-PURITY adds AST-walking test mirroring S7-01 `test_fallback_plan_engine_purity.py`.
- **D7 (harden) — `failure_mode` derivation strategy missing.** **Fix:** subsumed by K10/C4 — `Final` constant.
- **D8 (harden) — `Protocol`-name verification hand-waved + Protocol does not exist.** **Fix:** subsumed by K1.
- **D9 (harden) — `hash()` won't work on Pydantic v2 frozen models.** **Fix:** subsumed by T1/K9.
- **D10 (harden) — Embed-cache-key invariant should reference `digest()`, not `hash()`.** **Fix:** subsumed by C6/T1.
- **D11 (nit) — Open/Closed boundary should be explicit.** **Fix:** Out-of-scope last bullet explicitly excludes any abstraction shared with the Phase-7 distroless plugin.
- **D12 (nit) — Module docstring should name canonical field order.** **Fix:** Implementation outline §3 + Refactor block + Notes require the module docstring to name the canonical order and `_FAILURE_MODE_DEFAULT` rationale.
- **D13 (nit) — `RetrieverDeps` aggregate is premature.** **Fix:** Notes explicitly forbid introducing a `RetrieverDeps` aggregator; pass `query_builder` + `query_text_builder` as keyword-only kwargs into the existing 10-arg retriever constructor.

## Research briefs

None executed. The single `NEEDS RESEARCH` finding (K10/C4/D7 — `failure_mode` derivation policy) was a pure internal-modeling choice between two in-repo-resolvable options (constant default vs injected classifier). Per the skill's failure-mode handling for unresolvable canonical patterns and the scheduled-task instruction "make reasonable choices and note them in your output", picked the constant-default approach with Simplicity First + closed-dispatch in-repo precedent (`_LOCKFILE_PRECEDENCE` in `npm_lockfile.py`); surfaced as Rule-7 ADR amendment trigger in Notes.

## Conflict resolutions

- **S1-04 vs original S7-02 `Query` shape:** S1-04 HARDENED wins (priority: Consistency > Coverage). All six S1-04 fields are now mandated; `version_constraint` was deleted entirely; canonical literal values (`"vuln_remediation"`, `"typescript"`, `"npm"`) replace the wrong ones.
- **S5-01 vs original S7-02 callable surface:** S5-01 wins. Both `query_builder` and `query_text_builder` are now shipped; no `RagQueryBuilder` Protocol is referenced.
- **S7-01 vs original S7-02 wiring point:** S7-01 wins. The composition root is the plugin's `transforms()` factory.
- **CLAUDE.md "Newtype identifiers" vs original S7-02 raw `str` literals:** CLAUDE.md wins. Every domain identifier in `Query(...)` calls uses a newtype constructor or `Final` constant (AC-NO-RAW-STR enforces).
- **Design-Patterns D4 (YAGNI on registry) vs Coverage abstraction temptation:** YAGNI wins. The retriever's keyword-only kwargs are the Open/Closed seam between plugins; defer registry to phase-architect when a third plugin needs it (Rule of Three).
- **Test-Quality T1 vs original `hash()` assertion:** T1 wins. Pydantic v2 frozen models are not hashable; `digest()` + `model_dump_json()` are the correct equality contracts.

## Edits applied

1. Header set to `HARDENED (2026-05-24 — phase-story-validator)`; status + dependency line expanded with S7-01-must-be-GREEN precondition + S1-04 + S5-01 caveats.
2. Validation notes block inserted under the header summarizing every load-bearing fix.
3. Context rewritten around the two free-function deliverables, the typed `Query` discipline, the embed-cache-key contract, and the S7-01 precondition.
4. References corrected: S5-01 (both callables); S1-04 (six fields + canonical values + digest); S7-01 (composition root + `--`-to-`_` shim + AC-PROTOCOL-CONFORMANCE pattern); ADR-0003 scoping clarification; `npm_lockfile._classify_jail_result` free-function precedent; `probes/base.py:40` task-class canonical value.
5. Goal rewritten to ship both free functions + wire into `transforms()` factory + subprocess-mypy structural-conformance fixture.
6. Acceptance criteria restructured into 14 binary-verifiable ACs (AC-FILE, AC-SHAPE, AC-FIELDS, AC-VALUES, AC-PACKAGE-DERIVATION, AC-FAILURE-MODE, AC-RENDER, AC-DIGEST-DETERMINISM, AC-MODEL-DUMP-EQUALITY, AC-WIRING-FUNCTIONAL, AC-WIRING-STRUCTURAL, AC-PURITY, AC-NO-FSTRING-IN-BUILD, AC-FENCE-IMPORT, AC-KERNEL-FROZEN, AC-CHECK).
7. Implementation outline rewritten with concrete `build` + `render_query_text` code; `_FAILURE_MODE_DEFAULT` + `_CANONICAL_*` Final constants; correct imports.
8. TDD plan restructured into six tiers: Tier-1 unit tests for `build`; Tier-2 unit tests for `render_query_text`; Tier-3 Hypothesis property; Tier-4 AST guards (`no-fstring`, `no-raw-str`, `imports`, `purity`); Tier-5 subprocess-mypy structural conformance; Tier-6 integration wiring test.
9. Files-to-touch expanded with 13 explicit files (the recipe module, the `transforms()` factory edit, and 11 test files).
10. Out-of-scope expanded with explicit Rule-of-three YAGNI guards (no Phase-7-shared abstraction; no registry; no `RetrieverDeps`).
11. Notes-for-implementer expanded with 12 numbered guidance items covering free-function shape, no-Protocol contract, `task_class` vs `plugin_id` distinction, `Language` vs ecosystem, `_FAILURE_MODE_DEFAULT` Rule-7 surface, `repo_ctx` unused parameter, Pydantic v2 non-hashability, render vs build f-string discipline, composition-root identity, `CveAdvisory` read-before-write, `--`-to-`_` shim, no `RetrieverDeps`, ADR-0003 scoping, `make check` coverage subset.

## Verdict rationale

**HARDENED.** The story's core goal — ship the npm plugin's typed `Query` builder + canonical text renderer wired into the retriever — remains valid and traces correctly to the phase arch + High-level-impl Step 7. The original draft depended on stale sibling-contract assumptions and had unsourced design choices (`failure_mode` derivation, free-function vs class, `hash()` determinism). The hardened version is executor-ready only after its named preconditions are cleared: **S7-01 must be GREEN before S7-02 executes** (the plugin directory + import shim + `transforms()` composition root are all S7-01 deliverables). No story-goal rewrite was needed, so this is not a RESCUE.

## Recommended next step

Before executing S7-02:
1. Confirm S7-01 has shipped GREEN. If not, execute S7-01 first.
2. Locate or land the `CveAdvisory` model (likely an extension of `VulnerabilityRecord` in `src/codegenie/vuln_index/models.py`). If `CveAdvisory.id` is not a `CveId` newtype OR the affected-package shape is plural rather than singular, surface as Rule-7 to phase-architect before writing AC-PACKAGE-DERIVATION fixtures.
3. When `phase-story-executor` runs this story, the red marker should fail with `ImportError` on the recipe module + Tier-5/Tier-6 subprocess-mypy/integration `AttributeError`s. The green path is two small commits: (a) the two free functions + the `transforms()` factory wiring, (b) the test suite.
