# Validation report: S5-05 — `runtime_trace` freshness-check registration + `image_digest_drift` adversarial

**Validated:** 2026-05-17
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story:** [`../S5-05-runtime-trace-freshness-and-drift.md`](../S5-05-runtime-trace-freshness-and-drift.md)

## Summary

S5-05 plants a `@register_index_freshness_check(IndexName("runtime_trace"))` function inside `src/codegenie/probes/layer_c/runtime_trace.py` (the S5-02 module) and lands the load-bearing `tests/adv/phase02/test_image_digest_drift.py` adversarial. The story's *intent* is well-formed and traces cleanly to the architecture's "honest confidence" commitment, the Open/Closed-at-the-file-boundary discipline (02-ADR-0006 §"Gap 3 improvement"), and the image-digest-as-declared-input-token mechanism (02-ADR-0004). The *contract surface* the original draft prescribed, however, contradicted the code already on disk at six load-bearing points — function signature, error class name, slice-field name `index_freshness` vs B2's actual `index_health`, upstream-unavailable signal, `Fresh.indexed_at` derivation, and `__all__` export convention. All six were fixable in place against existing precedents (`scip_freshness` at `index_health.py:143-204`; the `FreshnessRegistry` contract at `registry.py:67`; the `FreshnessRegistryError` shape at `errors.py:155`; the existing duplicate-rejection test at `tests/unit/indices/test_freshness_registry.py:78-106`); none required architectural change. Five test-quality and three design-pattern hardens were applied. No `NEEDS RESEARCH` findings — every gap traced to an in-repo precedent.

Eighteen in-place edits applied; verdict **HARDENED**. Story is now structurally consistent with the existing code and the four validation reports already landed for the S5-* family.

## Context Brief (Stage 1)

### Story snapshot
- **Goal:** Register `@register_index_freshness_check("runtime_trace")` in `runtime_trace.py` — a pure function `(slice, head) -> IndexFreshness` returning `Stale(DigestMismatch)` on drift, `Fresh` on parity. Land the load-bearing `tests/adv/phase02/test_image_digest_drift.py` adversarial.
- **Non-goals:** Other freshness registrations (S6-08); stale-scip fixture (S4-02); adversarial_dockerfile (S5-06); editing `IndexHealthProbe`; editing `cache/keys.py`.

### Phase / arch constraints touched
- 02-ADR-0003 — `IndexHealthProbe` `runs_last=True`; no per-tier semaphores.
- 02-ADR-0004 — image-digest as declared-input special token; cache invalidation is the load-bearing structural property.
- 02-ADR-0006 — `IndexFreshness` sum-type location at `codegenie.indices.freshness`; the registry decorator at `codegenie.indices.registry` (location deviation from ADR's §Consequences is documented in `registry.py` module docstring; bounded).
- `phase-arch-design.md §"Gap 3"` — `@register_index_freshness_check` Open/Closed seam; this story is the 2nd concrete consumer (`scip_freshness` is the 1st; S6-08 will be the 3rd-5th).
- `CLAUDE.md` "Extension by addition" — no edits to `IndexHealthProbe`; story makes this observable via AC-16.

### Sibling-family lineage
- **2nd concrete consumer** of `@register_index_freshness_check` (after `scip_freshness` at S4-01). Three more (`semgrep`, `gitleaks`, `conventions`) will land in S6-08.
- **Rule-of-three threshold:** reached but kernel-extraction deferred to S6-08 (mirrors S5-04 D2 conflict resolution: extract at the 3rd-5th-consumer-trigger, not the 2nd).
- **Prior validation framings carried forward:**
  - S5-02 hardening: `requires` is class attribute, not decorator kwarg; sibling-slice reads use `read_raw_slices(raw_dir(...))`; envelope `confidence` never widens to `"unavailable"`.
  - S5-03 hardening: AST-walk audits supersede source-grep purity tests.
  - S5-04 hardening: mutation-resistance suite is mandatory; `Final[...]` discipline on module constants; rule-of-three trigger documented for downstream story authors.

### Phase exit criteria the story contributes to
- G1 — `IndexHealthProbe` surfaces ≥1 staleness case beyond `scip` (this story is the runtime_trace staleness case).
- G2 — `tests/adv/phase02/test_image_digest_drift.py` is CI-gating (already named in phase-arch-design.md L953).
- G9 — kernel scaffolding ships before consumers; this story is a kernel consumer (S1-02 registry + S5-02 probe + S4-01 dispatcher).

### Open ambiguities discovered during Stage 1
- **`Fresh.indexed_at` source not pinned.** Story said "<some-sentinel-or-the-slice-timestamp>" — neither option is correct in the existing data model. **Resolved at synthesis**: the runtime_trace slice carries no timestamp today (S5-02 AC line 86 enumerates the slice keys; no `last_traced_at`). Two options were considered and the cleaner one picked: pin a small upstream-AC patch to S5-02 adding `last_traced_at: str` (ISO-8601 UTC). The alternative (sentinel datetime) was rejected because it regresses the honest-confidence rendering in S8-01's `CONTEXT_REPORT.md`. Surfaced as the load-bearing upstream-dependency note in Notes-for-implementer.

## Findings by critic

### Coverage critic

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| K1 | harden | No AC for the empty-dict sentinel path (registry dispatch passes `slices.get(name, {})` when `runtime_trace.json` is absent on disk). The draft's `confidence == "unavailable"` branch was the only upstream-degraded path and it referenced a non-existent slice field. | Branch table extended to (a) empty-dict → `_MSG_UPSTREAM_UNAVAILABLE`; (b) `trace_coverage_confidence == "unavailable"` → same; both verified by sibling B2 integration tests AC-6/7/8. |
| K2 | harden | No AC for malformed-slice handling (wrong field types). The `scip_freshness` precedent has a full isinstance-discipline branch; the draft had none. | New branch (c): isinstance-checks on `built_image_digest`, `last_traced_image_digest`, `last_traced_at` → `Stale(_MSG_SLICE_MALFORMED)` on any type error. Mirrors `scip_freshness` lines 168-184. Test 12 covers it. |
| K3 | harden | No AC for malformed-timestamp handling. `Fresh.indexed_at: datetime` requires a parseable ISO-8601 string; the function must not raise on a corrupted `last_traced_at`. | New branch (g) fallback: `try / except ValueError → Stale(_MSG_SLICE_MALFORMED)`. Mirrors `scip_freshness` lines 200-203. Test 13 covers it. |
| K4 | harden | No AC for the `IndexerError.message` constants. The four message strings are duplicated between the function body and the test files; a future typo (e.g., `"no_built_iamge"`) would silently regress B2's downstream confidence-section rendering. | New AC-3: `Final[str]` module constants `_MSG_*`; tests import them, not duplicate the literals. Test 4 audits the `Final[str]` annotation. |
| K5 | harden | Story's Scenario A asserted `RuntimeTraceProbe.run` is "entered" (cache MISS) — this is implementation-level state, not contract-level. The contract-level signal is **cache-key inequality** on different resolver returns. | Scenario A rewritten as `test_image_digest_change_changes_cache_key`; subject-under-test is `cache/keys.py::declared_inputs_for` + `_resolve_special_token`, not `_execute_scenario` invocation. |
| K6 | harden | No B2 integration test for the **clean** (Fresh) and **absent-slice** (empty dict) paths. Original AC-6 covered drift only; Rule 12 "fail loud" demands the negative cases. | New AC-7 (clean → Fresh + indexed_at) and AC-8 (absent → Stale + upstream_unavailable). Tests 15, 16. |
| K7 | harden | No AC for the `_check_runtime_trace_freshness` `__all__` export. The original draft said "leave it module-private"; the precedent (`scip_freshness` in `index_health.py:97`) exports it. | AC-1 amended to require the `__all__` entry. |
| K8 | nit | The duplicate-registration test (AC-10 in the draft) reads as a re-test of S1-02; per validator's "do not duplicate ACs that re-test sibling stories" rule, this should either land as a smoke test that imports `runtime_trace` first (genuinely Phase-2-integration), or be removed. | Kept as AC-15; reframed as a smoke test for the integration boundary; clear comment that the registry hardening itself is S1-02's discipline. |

### Test-Quality critic

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| T1 | harden | Test 7 in the original (`test_freshness_function_is_pure`) used source-grep — bypassable via string concatenation (`"date" + "time.now"`). S5-04 T4/T5 and S5-03 ASTAudit set the precedent: structural audits use AST-walk. | New AC-4: AST-walk audit over `_check_runtime_trace_freshness`'s body asserts no Name/Attribute references `datetime.now`, `time.time`, `Path.stat`, `os.path.getmtime`, etc. Test 5 implements it. |
| T2 | harden | No mutation-resistance suite. S5-04 T2 and S5-03 T16 established the precedent: tests must demonstrate a wrong implementation fails ≥ 1 named test. | New AC-9: parametrized table of 5+ wrong stubs (`always_fresh`, `always_stale`, `swap_expected_actual`, `wrong_reason_kind`, `drops_upstream_unavailable_branch`); each must fail ≥ 1 named test. Test 24. |
| T3 | harden | No property-based test on the totality of the freshness function. Hypothesis would catch a regression where some weird input shape escapes the branch table. | New AC-10: Hypothesis property `(slice_, head) -> Fresh \| Stale` is total (never raises, never returns None) and pure (idempotent across calls). Test 25. |
| T4 | harden | No argument-order canary. `FreshnessRegistry.dispatch_all` calls positional `(slice, head)`; if the function defensively accepts either order, a future registry-call typo silently corrupts every check. | New AC-11: positive call returns `Fresh`; swapped-arg call raises `TypeError`/`AttributeError`. Test 3. |
| T5 | harden | B2 integration test (Scenario B) referenced wrong slice key `index_freshness`. B2 actually emits `schema_slice["index_health"]`. Tests would have run red on the first try. | Fixed: every B2-integration test asserts against `schema_slice["index_health"]["runtime_trace"]["freshness"]` and the `model_dump(mode="json")` shape. Tests 14, 15, 16, 20, 21. |
| T6 | harden | Original Test 9 (cache MISS via `_execute_scenario` invocation count) couples the adversarial to S5-02's internal helper naming. If S5-02 renames `_execute_scenario` to `_run_scenario`, the test breaks for the wrong reason. | Scenario A rewritten to assert against `cache_key()` output equality, which is the **contract** surface. Implementation-detail decoupled. Test 19. |

### Consistency critic

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| C1 | block | **Function signature contradicts `FreshnessCheck` contract.** Draft: `(slice_: RuntimeTraceSlice, head: GitSha) -> IndexFreshness`. Actual contract at `registry.py:67`: `Callable[[dict[str, object], str], "IndexFreshness"]`. No `RuntimeTraceSlice` exists; no `GitSha` newtype exists in `types/identifiers.py`. The scip_freshness precedent at `index_health.py:144` is the canonical shape. | Rewrote AC-1 signature to verbatim match the registry contract. Notes-for-implementer paragraph explains why mypy would refuse the typed-Pydantic-model variant. |
| C2 | block | **Wrong error class name + wrong constructor shape.** Draft: `IndexFreshnessRegistryError(reason="duplicate_name")`. Actual at `errors.py:155`: `FreshnessRegistryError` (no "Index" prefix); positional message string with format `f"duplicate index_name {name!r}: {prior} and {origin}"`. The existing test at `tests/unit/indices/test_freshness_registry.py:78-106` asserts the message-string shape. | Rewrote AC-15: `FreshnessRegistryError`; assert message contains `"duplicate index_name"`, `"runtime_trace"`, and both qualname strings. |
| C3 | block | **Wrong B2 slice-field name.** Draft AC-6 Scenario B asserted `B2 slice's index_freshness["runtime_trace"]`. Actual emitted shape at `index_health.py:397-404`: `schema_slice={"index_health": results}`. Tests would fail. | Rewrote every B2-integration AC and test to use `schema_slice["index_health"]`. Five tests touched (14, 15, 16, 20, 21). |
| C4 | block | **Wrong upstream-unavailable signal field.** Draft branched on `slice_.confidence == "unavailable"`. The runtime_trace slice has no `confidence` field; the field name S5-02 records is `trace_coverage_confidence` (tetra-state) — and even that is secondary to the registry's canonical empty-dict sentinel. | Rewrote branch table: (a) empty dict → `_MSG_UPSTREAM_UNAVAILABLE`; (b) `trace_coverage_confidence == "unavailable"` → same; both map to the same `IndexerError` message so the downstream renderer collapses them identically. |
| C5 | block | **`Fresh.indexed_at` derivation hand-wave.** Draft said "<some-sentinel-or-the-slice-timestamp>". `Fresh.indexed_at: datetime` requires a real datetime; the function is pure (no clock read); no slice field today carries a timestamp. | Pinned the source: parse `slice_["last_traced_at"]` via `_dt.datetime.fromisoformat` (mirrors scip_freshness lines 200-203). Surfaced the upstream-AC dependency on S5-02 (which doesn't carry `last_traced_at` today) in Notes-for-implementer with a small-AC-patch surface. Alternative (sentinel datetime) considered and rejected. |
| C6 | harden | **`__all__` export omitted.** Draft said "leave it module-private". The `scip_freshness` precedent IS in `__all__` (`index_health.py:97`). | AC-1 amended; new test imports `_check_runtime_trace_freshness` symbolically via `from codegenie.probes.layer_c.runtime_trace import _check_runtime_trace_freshness`. |
| C7 | nit | Layer-C `tests/unit/probes/layer_c/` directory does not exist on disk today (S5-02 has not landed). The story creates the directory by landing the first test file there. | No change required; consistent with S5-02's planned layout. Test paths use `tests/unit/probes/layer_c/...`. |

### Design-Patterns critic

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| D1 | harden | **Primitive obsession on `IndexerError.message`.** Four message strings are inlined in the branch table (`"upstream_runtime_trace_unavailable"`, `"no_built_image"`, etc.). A test asserts the exact string; a future typo silently breaks the consumer's `match reason: case IndexerError(message="…"):` dispatch. | New AC-3: `Final[str]` module constants for all four messages. Tests import constants, not literal strings. Mirrors `_WARNING_IDS` / `_SCIP_REQUIRED_KEYS` `Final[...]` discipline in `index_health.py:109-132`. |
| D2 | harden | **Rule-of-three threshold reached but no documented trigger for S6-08 author.** Five `@register_index_freshness_check` registrations exist by phase end (scip + runtime_trace + 3 from S6-08); the kernel-extract opportunity (`_FreshnessHelpers` mini-kernel) is real but per Rule 2 / S5-04 D2 precedent, the extract waits until the consumer that triggers it. | New Notes-for-implementer paragraph: the kernel-extract trigger is recorded for S6-08 authors; this story does NOT pre-extract. Mirrors S5-04's `_shared/` deferred trigger. |
| D3 | harden | **No structural defense against editing `IndexHealthProbe`.** The whole Open/Closed promise of S1-02 is that adding a new freshness check requires zero B2 edits. Without an observable AC, a future contributor might "while I'm here, refactor B2's dispatch loop"; the discipline erodes silently. | New AC-16: `git diff` audit asserts `src/codegenie/probes/layer_b/index_health.py` is not modified by this story's PR. The "no edit" promise is made *observable*. |
| D4 | harden | **Argument-order canary doubles as a design-pattern defense.** The registry's positional call convention is a kernel contract; making the function defensively accept either order undermines the contract (the function shouldn't know about the registry; the registry shouldn't have to call by keyword). | Already covered by AC-11 (also surfaced by Test-Quality T4 — both critics independently flagged it). |
| D5 | nit | The freshness function reads `dict[str, object]` and isinstance-checks fields. A typed `RuntimeTraceFreshnessInput` Pydantic model would catch malformed inputs at construction time, but introducing one would deviate from the `scip_freshness` precedent and force S5-04's `SbomProbe` / S5-04's `CveProbe` / etc. to adopt the same pattern — a phase-wide design change masquerading as a story detail. | Documented in Notes-for-implementer as deliberately-NOT-typed; the `dict[str, object]` + isinstance discipline matches the precedent and keeps the registry contract simple. |
| D6 | nit | The `head` parameter is unused for runtime_trace but kept for registry uniformity. Some Python style guides recommend `_head` or `*_args, **_kwargs` to signal "intentionally unused" — but the uniform-shape registry argument is the more important property. | Already documented in Notes-for-implementer; the docstring explains the no-op. |

## Research briefs (if any)

None — every finding traced to an in-repo precedent (`scip_freshness` for shape; `FreshnessRegistry` contract for signature; `FreshnessRegistryError` for error type; S5-04/S5-03 validation reports for AST-audit + mutation-resistance + Final discipline; S5-04 D2 conflict resolution for the deferred kernel extract; the existing `test_freshness_registry.py:78-106` for the duplicate-rejection assertion shape). The Hypothesis property pattern is standard.

## Conflict resolutions

- **C5 (Fresh.indexed_at) vs Rule 3 (surgical changes).** Adding a `last_traced_at` field to S5-02's slice is a small upstream amendment; the alternative (sentinel datetime in `Fresh.indexed_at`) regresses S8-01's confidence-section rendering. Per editor priority Consistency > Coverage > Test-Quality > Design-Patterns, **Consistency wins**: the story surfaces the upstream-AC patch as a load-bearing Notes-for-implementer paragraph; the executor must verify S5-02 carries the field before proceeding. Rule 3 is honored because the patch is one new field on S5-02's snapshot test (additive only).
- **D2 (rule-of-three reached) vs Rule 2 (Simplicity First).** Kernel extraction now would split the work across this story and S6-08, risk getting the kernel shape wrong (we've only seen 2 of 5 concrete cases), and inflate the small-effort budget for this story. Rule 2 + S5-04 D2 precedent win: defer to S6-08.
- **K8 (duplicate test redundancy) vs Coverage (smoke-test integration boundary).** Re-testing the registry's own duplicate-rejection at the runtime_trace integration boundary is borderline duplicative, but the integration-boundary semantics are different (the assertion that a *concrete consumer*'s registration is rejected on a second decoration). Resolution: keep as AC-15; reframe as a smoke test; clear comment that S1-02's registry hardening is tested in `test_freshness_registry.py`.

## Edits applied

### Edit 1 — Header `Status` + `Depends on:` + `ADRs honored:` corrected (Consistency C1, C2, C3)

- **Status:** added "(hardened 2026-05-17)" marker.
- **Depends on:** expanded with S1-05 (`IndexName` newtype); reframed S1-02 dependency to point at the actual module location (`codegenie.indices.registry`); reframed S4-01 dependency to reference the `read_raw_slices` kernel.
- **ADRs honored:** unchanged in content; the citations were correct.

### Edit 2 — Validation notes block inserted under header (every Consistency block + harden)

Six-paragraph audit trail documents each Consistency block plus the five harden-tier improvements and the one design-pattern surfaced. Cross-references file:line numbers for every claim against existing code.

### Edit 3 — Context section rewritten (Consistency C3, C4, C5)

Slice fields renamed correctly (`built_image_digest`, `last_traced_image_digest`, `last_traced_at`); the upstream-unavailable mechanism is now the empty-dict sentinel; `last_traced_at` is named as the source of `Fresh.indexed_at`.

### Edit 4 — References section extended

Added direct references to `src/codegenie/indices/registry.py`, `src/codegenie/probes/layer_b/index_health.py:143-204`, and `tests/unit/indices/test_freshness_registry.py:78-106` — the three on-disk artifacts that pin the signature, the precedent, and the duplicate-rejection assertion shape.

### Edit 5 — Goal rewritten (Consistency C1)

Function signature corrected: `_check_runtime_trace_freshness(slice_: dict[str, object], head: str) -> IndexFreshness`. Decorator uses `IndexName("runtime_trace")` (newtype). Adversarial scope clarified (cache-key inequality, not `_execute_scenario` invocation count).

### Edit 6 — AC-1 (function placement + decorator + signature) rewritten (Consistency C1, C6)

Signature pinned verbatim; `IndexName` newtype usage; `__all__` export mandated.

### Edit 7 — AC-2 (branch table) expanded to seven branches (Coverage K1, K2, K3, K5)

Empty-dict sentinel; `trace_coverage_confidence` secondary signal; isinstance-malformed branch; `built_image_digest is None`; `last_traced_image_digest is None`; drift; clean (with try/except ValueError fallback to malformed). Each branch is in a table with the precise `IndexerError.message` constant.

### Edit 8 — AC-3 (Final[str] constants) added (Coverage K4 + Design-Patterns D1)

Four module-scope `Final[str]` constants; test asserts the annotations via `inspect.getmembers`.

### Edit 9 — AC-4 (purity via AST-walk) added (Test-Quality T1)

AST-walk audit replaces source-grep; precedent: S5-04 T4/T5 + S5-03 ASTAudit.

### Edit 10 — AC-5 (registry membership + retrieval) added (Coverage K7)

Uses identity (`is`) not equality; uses `clean_freshness_registry` snapshot+restore.

### Edit 11 — AC-6/7/8 (B2 end-to-end integration) rewritten (Consistency C3 + Coverage K6)

Three sister tests cover drift / clean / absent. Each uses correct field name `schema_slice["index_health"]["runtime_trace"]["freshness"]` and the `model_dump(mode="json")` shape; the four-part inequality assertion on drift is preserved and made explicit.

### Edit 12 — AC-9 (mutation-resistance suite) added (Test-Quality T2)

Parametrized table of 5+ wrong stubs; per-stub assertion that ≥ 1 named test fails.

### Edit 13 — AC-10 (Hypothesis property — totality + purity) added (Test-Quality T3)

Hypothesis text-strategy over slice dicts; totality + purity + sub-5ms wall-clock signal.

### Edit 14 — AC-11 (argument-order canary) added (Test-Quality T4 + Design-Patterns D4)

Positive call returns `Fresh`; swapped-arg call raises `TypeError`/`AttributeError`.

### Edit 15 — AC-12/13/14 (adversarial three scenarios) rewritten (Test-Quality T5, T6)

Scenario A is now cache-key inequality (contract surface, not implementation detail); Scenarios B/C mirror the unit-test sister tests but live under `tests/adv/phase02/`; `_forbid_real_subprocess` fixture prevents subprocess escape; ADR substring coverage assertion on failure messages.

### Edit 16 — AC-15 (duplicate registration smoke) rewritten (Consistency C2)

`FreshnessRegistryError` (correct name); positional message-string format; both call-site qualnames asserted; framed as smoke test, not re-test of S1-02.

### Edit 17 — AC-16 (no edits to `IndexHealthProbe`) added (Design-Patterns D3)

`git diff` audit; observable promise of the Open/Closed seam.

### Edit 18 — Implementation outline + TDD plan + Files to touch + Notes-for-implementer rewritten

Outline reflects the corrected signature, branch table, and constants. TDD plan grows from 12 to 25 tests covering every AC. Files-to-touch expanded with three new test files. Notes-for-implementer adds eight paragraphs: the `last_traced_at` upstream dependency, the typed-model rejection rationale, the AST-walk-vs-source-grep rationale, the argument-order canary's structural role, the rule-of-three threshold reached-but-deferred, the `_forbid_real_subprocess` discipline, the `read_raw_slices` integration path, the `Fresh.indexed_at` honesty argument. Plus carries forward the two open questions (re-trace on drift; multi-image repos) from the original draft with minor rewording.

## Verdict rationale

**HARDENED.** Story's goal (plant a registry-side freshness check for runtime_trace; land the load-bearing image-digest-drift adversarial) is intact, well-formed, and consistent with `phase-arch-design.md §"Gap 3"`, `02-ADR-0003`, `02-ADR-0004`, `02-ADR-0006`, and `High-level-impl.md §"Step 5"`. All findings were fixable in place against existing code precedents (no architectural change required). The six Consistency blocks were factual contract-drift bugs that would have caused the executor to write code that didn't compile and tests that ran red on the first attempt; the five Test-Quality hardens added structural defenses that the executor's Validator pass would not otherwise have caught (mutation-resistance, AST-walk audit, argument-order canary, Hypothesis totality, B2 integration with correct field names); the three Design-Patterns hardens pinned the `Final[str]` discipline, made the no-edit-to-`IndexHealthProbe` promise observable, and documented the rule-of-three deferred-extract trigger for S6-08 authors. The story is now ready for `phase-story-executor`; the structural tests (AC-4 AST audit, AC-5 identity check, AC-9 mutation table, AC-10 Hypothesis property, AC-11 arg-order canary, AC-16 `git diff` audit) backstop the load-bearing invariants against any future contributor regression.

## Recommended next step

`phase-story-executor` for S5-05 — but **first** verify S5-02's slice carries `last_traced_at: str`. If S5-02 has not yet been executed (it shows as Status: Ready in [stories/](..) but the layer_c module is absent), the executor either (a) executes S5-02 first under its own story file, then this one; or (b) lands both in the same PR if the dependency graph allows. The `last_traced_at` field is a one-line amendment to S5-02's AC line 86 and the snapshot test; the patch is surgical.
