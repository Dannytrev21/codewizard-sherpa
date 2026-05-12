# Story S6-03 — Orchestrator branch promotion + `--no-rag` / `--no-llm` semantics (Gap 4)

**Step:** Step 6 — Ship synchronous gated `writeback_solved_example` + Gap-4 semantics + operator CLI
**Status:** Ready
**Effort:** M
**Depends on:** S6-02 (`writeback_solved_example` with strict-AND guard returns `SolvedExample | None`), S1-05 (orchestrator writeback **stub** branch in `transforms/coordinator.py`)
**ADRs honored:** ADR-P4-001 (`Recipe.engine` Literal extension — the discriminator the branch reads), ADR-P4-002 (the two-tier writeback the branch invokes), ADR-P4-005 (chromadb in-process — `--no-rag` is a *runtime-only* skip, not a teardown), ADR-P4-010 (`LlmInvocationGuard` — `--no-llm` flips engine availability, not the guard), production ADR-0009 (humans always merge — `merge_status="pending_human"` after promotion)

## Context
S1-05 planted the conditional `if recipe_application.engine_used == "rag_llm" and trust_score.passed: pass  # Phase 4 ADR-P4-002 conditional` as a no-op stub. S6-01 + S6-02 shipped the real callable `writeback_solved_example` (with strict guard). This story **promotes the stub to the real call** and finalises the **Gap 4 CLI semantics** that decide *when the engine even runs*:

- `--no-llm` is the **hard switch** — `RagLlmEngine.available()` returns `False` for the run; the Phase 3 selector falls through; tier-2 and tier-3 are unreachable; the corpus does not grow (no LLM call → no writeback to fire).
- `--no-rag` is the **diagnostic switch** — `RagLlmEngine` is still available, but `FallbackTier` / `RagLlmEngine.apply` skips tier-2 retrieval (passes empty `retrieved_examples` straight through to the LLM-cold path). **Writeback still fires** if the LLM-cold path validates — the corpus should *grow* under `--no-rag`, because the operator is explicitly opting into "use only the LLM, ignore retrieval" to debug retrieval quality.

The third behaviour pinned here: the orchestrator's branch is now no longer a `pass`. It calls `writeback_solved_example(...)`; on the function's `None` return (a refusal under the S6-02 guard), the orchestrator skips the writeback section of the run report; on a returned `SolvedExample`, the orchestrator records it in `remediation-report.yaml#phase4.writeback`.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §"Control flow"` step 9 — Decision point E; this story replaces the `pass` with `example = writeback_solved_example(...); if example is not None: report.record_writeback(example)`.
  - `../phase-arch-design.md §"Component design" #1` — `RagLlmEngine.available()` reads the run's `--no-llm` flag; selector falls through to the next engine or exits 4 (`no_engine`).
  - `../phase-arch-design.md §"Component design" #2 — FallbackTier`  — `FallbackTier.run(...)` honours `run_config.skip_rag_retrieval` by short-circuiting tier-2; the LLM-cold path is reached without retrieval; writeback proceeds normally on validation pass.
  - `../phase-arch-design.md §"Gap analysis" Gap 4` — the verbatim two-bullet specification this story implements.
  - `../phase-arch-design.md §"Operator-facing surfaces"` table — `--no-llm` row: "Skip tier 2; if tier 0/1 miss, exit 4"; `--no-rag` row: "Skip tier 1; tier 0 → tier 2 directly".
  - `../phase-arch-design.md §"Harness engineering"` — exit codes table; `--no-llm` + no recipe match → exit 4.
- **Phase ADRs:**
  - `../ADRs/0001-recipe-engine-literal-extends-with-rag-llm.md` — ADR-P4-001 — `engine_used="rag_llm"` is the orchestrator's read discriminator.
  - `../ADRs/0002-two-tier-writeback-pending-promoted.md` — ADR-P4-002 — the writeback this story promotes the stub to; Phase 11's promoter is a separate Phase, not part of this story.
  - `../ADRs/0010-llm-invocation-guard-running-total-with-override.md` — ADR-P4-010 — `--no-llm` does **not** zero the cost guard; it flips engine availability before the guard even runs.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` — production ADR-0009 — the writeback only ever produces `merge_status="pending_human"` in Phase 4; promotion is Phase 11 territory.
  - `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — three-tier shape; `--no-rag` is the diagnostic that lets operators bypass tier-2 without disabling tier-3.
- **Source design:**
  - `../final-design.md §"Synthesis ledger" row "Writeback timing"` — winner 12/12; this story is the wiring that makes the row real.
  - `../final-design.md §"Open questions" #4` — `--no-rag` semantics (diagnostic vs reset) — synth picks diagnostic; this story instantiates it.
- **Existing code:**
  - `src/codegenie/transforms/coordinator.py` (S1-05) — the stub branch this story promotes.
  - `src/codegenie/recipes/engines/rag_llm.py` (S5-01 / S5-02) — `available()` and `apply()`.
  - `src/codegenie/recipes/selector.py` (Phase 3) — the engine selection logic the orchestrator drives.
  - `src/codegenie/rag/writeback.py` (S6-01 / S6-02) — `writeback_solved_example(...) -> SolvedExample | None`.
  - `src/codegenie/cli.py` (S1-06) — `--no-llm` / `--no-rag` flag parsing (semantics deferred to this story).
  - `src/codegenie/recipes/contract.py` — `RunConfig` (or `Ctx`) where `no_llm` / `no_rag` flags ride. If the field doesn't exist as named, add `skip_llm: bool` / `skip_rag_retrieval: bool` per `phase-arch-design.md §Component 1`.

## Goal
Promote the Step-1 orchestrator writeback stub to the real `writeback_solved_example` call (handling the `None` refusal path); and wire `--no-llm` to disable `RagLlmEngine.available()` while wiring `--no-rag` as a diagnostic-only tier-2 skip that **still fires writeback** when the LLM-cold path validates.

## Acceptance criteria
- [ ] `src/codegenie/transforms/coordinator.py` ADR-P4-002 conditional now reads (sketch — exact LOC is implementation choice, but the semantic must match):
  ```
  if recipe_application.engine_used == "rag_llm" and trust_score.passed:
      example = writeback_solved_example(
          run_id=..., advisory=..., recipe_selection=..., recipe_application=...,
          validation_outcomes=..., cost_report=..., store=..., query_key_cache=...,
          audit=..., embedding=..., trust_score=trust_score,
      )
      if example is not None:
          report.record_writeback(example)
  ```
  The `# Phase 4 ADR-P4-002 conditional` annotation remains; its `test_writeback_stub_annotated` AST scan from S1-05 still passes (the literal comment is preserved). The `pass` placeholder is replaced.
- [ ] `tests/unit/recipes/test_orchestrator_writeback_branch_wired.py` — exercises three scenarios end-to-end against the coordinator with mocked collaborators:
  1. `engine_used="rag_llm"` + `trust_score.passed=True` + `plan_source="llm_cold"` + all signals → `writeback_solved_example` called once with the kwargs above; `report.record_writeback` called once with the returned `SolvedExample`.
  2. `engine_used="rag_llm"` + `trust_score.passed=True` + `plan_source="query_cache"` (S6-02 will refuse) → `writeback_solved_example` returns `None`; `report.record_writeback` is **not** called; no exception.
  3. `engine_used="ncu"` → branch does not enter; `writeback_solved_example` is **not** called (assert via `mock.assert_not_called()`). Phase 3 paths byte-identical.
- [ ] `tests/unit/cli/test_no_llm_disables_rag_llm_engine.py` — running `codegenie remediate --no-llm ...` results in `RagLlmEngine.available() == False` (assert via a probe that intercepts engine registry lookup); the Phase 3 selector falls through; if no other engine matches, the run exits with code 4 (`no_engine`); if a Phase 3 recipe engine matches, the run proceeds without ever loading the `anthropic` package (assert `sys.modules` does not contain `anthropic` after the run).
- [ ] `tests/unit/cli/test_no_llm_skips_writeback.py` — `--no-llm` + a Phase 3 `ncu` path that succeeds → the orchestrator branch is not entered (engine_used != "rag_llm"); writeback function is not called; the corpus is byte-identical before/after.
- [ ] `tests/unit/rag/test_no_rag_still_writebacks_llm_cold.py` (Gap 4) — running with `--no-rag`, with empty `tier_evidence` retrieval (forced by the flag), the LLM-cold path runs, validation passes → `writeback_solved_example` **does** fire; chromadb gains a row; the body file lands on disk; `solved_example.written` audit event records `plan_source="llm_cold"`. This is the load-bearing Gap-4 assertion: `--no-rag` is diagnostic, not reset; the corpus still grows.
- [ ] `tests/unit/recipes/engines/test_no_rag_skips_tier2_only.py` — `--no-rag` set; `RagLlmEngine.apply` runs; the `_retrieve` helper from S5-02 short-circuits to `Cold()` without calling `store.read().query(...)` (assert `store.read().query.assert_not_called()`); `cache.get` is still consulted (tier-1 is not skipped — `--no-rag` is *tier-2 retrieval* only; the query-key cache is a separate tier).
- [ ] `tests/unit/cli/test_no_rag_no_llm_combo.py` — both flags together: engine is unavailable (no-llm wins); selector exits 4 (`no_engine`) if no recipe matches. `--no-rag` is operationally irrelevant when the engine isn't loaded, but the flag combination must not crash and must not write anything.
- [ ] `tests/integration/test_orchestrator_writeback_e2e_llm_cold.py` (cassette-driven, builds on Step 5's `test_e2e_llm_cold.py`) — full coordinator + real `RagLlmEngine` + cassette-recorded Anthropic call + in-process `SolvedExampleStore` (tmp_path): an empty store run → tier-3 LLM-cold → `TrustScorer.passed` → orchestrator branch fires → body file exists at `.codegenie/rag/bodies/<id>.json` after the run; chromadb has one row in `vuln_solved_examples_pending`; the second-run query-key cache hit verifies the cache `put` was synchronous (re-runs `_compute_query_key` and asserts `cache.get(qk) is not None` without an Anthropic call). This closes the Phase-4 exit-criterion loop on the writeback side; the full E2E lands in S7-04 with the breaking-change CVE fixture.
- [ ] `tests/unit/recipes/engines/test_rag_llm_available_honors_no_llm.py` — `RagLlmEngine.__init__` reads `RunConfig.skip_llm` (or whatever the named flag is) and `available()` returns `False` when set; otherwise `True` iff prerequisites (api key, embedding model, store) are present.
- [ ] `RunConfig` (or equivalent) exposes `skip_llm: bool` and `skip_rag_retrieval: bool` as frozen Pydantic fields; defaults `False`; `mypy --strict` clean; contract-snapshot regenerates and the PR carries the `phase-3-contract-bumped` label (this is `RunConfig`, which is shared with Phase 3 — the addition is purely additive).
- [ ] `--no-llm` propagation: the CLI flag from S1-06 reaches `RunConfig.skip_llm`; `RunConfig.skip_llm` is read by `RagLlmEngine.__init__` (or `available()`); a probe test in `tests/unit/cli/test_no_llm_flag_propagates.py` follows the wire end-to-end.
- [ ] `--no-rag` propagation: CLI flag → `RunConfig.skip_rag_retrieval` → `RagLlmEngine.apply` reads it → `_retrieve` short-circuits tier-2. A probe test in `tests/unit/cli/test_no_rag_flag_propagates.py` follows the wire.
- [ ] `solved_example.written` audit event payload includes `plan_source` so `--no-rag`-driven writebacks are conspicuously labelled (auditors can filter `plan_source="llm_cold" AND run_config.no_rag=True` for retrospective analysis).
- [ ] All Phase 3 regression tests still pass — the orchestrator's existing six-call linear path for `ncu` / `openrewrite` is byte-identical for engines other than `rag_llm`. `tests/unit/transforms/test_writeback_stub_unreachable.py` from S1-05 is rewritten to assert "Phase 3 paths never call `writeback_solved_example`" (the mock-based version, now that the symbol exists). It must still pass.
- [ ] Coverage for `src/codegenie/transforms/coordinator.py` regression-pass and the new `RunConfig` fields included in PR body. `mypy --strict`, `ruff check`, `ruff format --check` clean on every touched file.

## Implementation outline
1. Add `skip_llm: bool = False` and `skip_rag_retrieval: bool = False` to `RunConfig` in `src/codegenie/recipes/contract.py` (or wherever Phase 3's `RunConfig` lives). Regenerate the Phase-3 contract snapshot; this is an additive bump (existing fixtures still parse).
2. Edit `src/codegenie/recipes/engines/rag_llm.py`: `available()` returns `False` when `self.run_config.skip_llm`. (Inject `run_config` at `__init__` per the existing DI pattern from S5-01.)
3. Edit `src/codegenie/recipes/engines/rag_llm.py` `_retrieve` helper (S5-02): on `self.run_config.skip_rag_retrieval`, return `Tier2Hit(top=[])` (empty retrieval) without calling `store.read().query(...)`. The downstream `_plan_from_rag` then returns `Cold()` and the LLM-cold path executes normally.
4. Edit `src/codegenie/cli.py` (or wherever S1-06 landed the flag stubs): map `--no-llm` → `RunConfig.skip_llm=True`, `--no-rag` → `RunConfig.skip_rag_retrieval=True`. The S1-06 work parsed-but-no-op'd these flags; this story is where they take effect.
5. Edit `src/codegenie/transforms/coordinator.py`: replace the `pass` in the ADR-P4-002 branch with the `writeback_solved_example(...)` call. Pass all kwargs (the orchestrator owns every collaborator — `store`, `query_key_cache`, `audit`, `embedding` are already in scope or constructor-injected in Phase 3 plus the Phase 4 additions). On `None`, skip `report.record_writeback`. Preserve the literal comment `# Phase 4 ADR-P4-002 conditional` so S1-05's annotation test still passes.
6. Update `tests/unit/transforms/test_writeback_stub_unreachable.py` from S1-05: now that `writeback_solved_example` exists as a symbol, mock it directly (`unittest.mock.patch("codegenie.transforms.coordinator.writeback_solved_example")`); assert it is never called for `ncu` / `openrewrite` paths.
7. Write the eight new tests above. The two propagation tests (`test_no_llm_flag_propagates`, `test_no_rag_flag_propagates`) follow the flag from CLI to `RunConfig` to engine — they're cheap insurance against a future refactor breaking the wire.
8. Cassette-driven integration test `test_orchestrator_writeback_e2e_llm_cold.py` extends S5-03's `test_e2e_llm_cold.py`: same cassette, but now the coordinator's writeback branch is wired, so the post-run filesystem inspection adds body-file + chromadb-row assertions.

## TDD plan — red / green / refactor

### Red
Test file path: `tests/unit/rag/test_no_rag_still_writebacks_llm_cold.py`
```python
from unittest.mock import MagicMock, patch
from codegenie.transforms.coordinator import RemediationOrchestrator


def test_no_rag_diagnostic_still_writebacks_on_llm_cold_success(tmp_path):
    """Gap 4: --no-rag skips tier-2 retrieval but NOT the writeback when LLM-cold succeeds.

    The corpus grows under --no-rag because the operator is debugging retrieval, not
    rejecting future learning. Writeback discriminator is plan_source, not run_config.
    """
    run_config = _run_config(no_rag=True, no_llm=False)
    store, cache, audit, embedding, leaf = _phase4_collaborators(tmp_path)

    # Fixture: a CVE the LLM-cold path will solve cleanly under a cassette.
    advisory, repo_ctx, recipe_selection = _breaking_change_fixture()

    orch = RemediationOrchestrator(run_config=run_config, store=store, ...,
                                   writeback_fn=_real_writeback_fn(store, cache, audit, embedding))
    with patch.object(leaf, "invoke", return_value=_cassette_response_llm_cold()):
        result = orch.run(advisory, repo_ctx, recipe_selection)

    # tier-2 retrieval was skipped
    store.read().query.assert_not_called()
    # but writeback fired
    bodies = list((tmp_path / ".codegenie/rag/bodies").glob("*.json"))
    assert len(bodies) == 1
    # audit event records plan_source so we can filter --no-rag corpus growth
    written_events = [c for c in audit.emit.call_args_list if c.args[0] == "solved_example.written"]
    assert len(written_events) == 1
    assert written_events[0].args[1]["plan_source"] == "llm_cold"
```

`tests/unit/cli/test_no_llm_disables_rag_llm_engine.py`
```python
import sys
from click.testing import CliRunner
from codegenie.cli import cli


def test_no_llm_makes_engine_unavailable_and_does_not_import_anthropic(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["remediate", "--no-llm", "--repo", str(tmp_path), "--cve", "CVE-2024-12345"])

    # If no Phase 3 engine matches, exit 4
    assert result.exit_code in {0, 4}  # 0 if ncu/openrewrite handled it, 4 otherwise
    # anthropic was never imported — strongest evidence that available() returned False before any LLM init
    assert "anthropic" not in sys.modules, "--no-llm must not import anthropic"
```

`tests/unit/recipes/test_orchestrator_writeback_branch_wired.py`
```python
from unittest.mock import MagicMock, patch


def test_branch_calls_writeback_on_rag_llm_pass():
    coord = _coordinator()
    recipe_app = _recipe_application(engine_used="rag_llm", plan_source="llm_cold")
    trust = _trust_passed()
    with patch("codegenie.transforms.coordinator.writeback_solved_example",
               return_value=_solved_example()) as wb, \
         patch("codegenie.transforms.coordinator.report.record_writeback") as rec:
        coord._post_trust_branch(recipe_app, trust, ...)
        wb.assert_called_once()
        rec.assert_called_once()


def test_branch_skips_record_when_writeback_refuses():
    """Guard refusal (S6-02) returns None — orchestrator must not crash and must not record."""
    coord = _coordinator()
    recipe_app = _recipe_application(engine_used="rag_llm", plan_source="query_cache")
    trust = _trust_passed()
    with patch("codegenie.transforms.coordinator.writeback_solved_example",
               return_value=None) as wb, \
         patch("codegenie.transforms.coordinator.report.record_writeback") as rec:
        coord._post_trust_branch(recipe_app, trust, ...)
        wb.assert_called_once()
        rec.assert_not_called()


@pytest.mark.parametrize("engine", ["ncu", "openrewrite"])
def test_phase3_engines_never_enter_writeback_branch(engine):
    coord = _coordinator()
    recipe_app = _recipe_application(engine_used=engine, plan_source=None)
    trust = _trust_passed()
    with patch("codegenie.transforms.coordinator.writeback_solved_example") as wb:
        coord._post_trust_branch(recipe_app, trust, ...)
        wb.assert_not_called()
```

### Green
- Add `skip_llm` / `skip_rag_retrieval` to `RunConfig`.
- `RagLlmEngine.available()`: `return False if self.run_config.skip_llm else <existing prereq checks>`.
- `RagLlmEngine._retrieve`: `if self.run_config.skip_rag_retrieval: return Tier2Hit(top=[])` before the store query.
- `cli.py`: bind `--no-llm` / `--no-rag` to the new `RunConfig` fields.
- `coordinator.py`: replace `pass` with the `writeback_solved_example(...)` call + `None`-aware `report.record_writeback` follow-up.

### Refactor
- Extract the orchestrator's post-trust branch into a private method `_post_trust_branch(recipe_application, trust_score, ctx)` so the eight-line block has a name and a test surface. The tests above already address it by name.
- The `RunConfig` field additions are a Phase 3 contract bump; surface this on the PR description with the `phase-3-contract-bumped` label so the snapshot regen is reviewed.
- Add a structured event `coordinator.writeback_branch.entered` on every branch entry (regardless of writeback outcome) and `coordinator.writeback_branch.skipped(reason)` on guard-refusal paths. These are *coordinator* events, not `solved_example.*` events — they document "the coordinator did its part" independently of the writeback's own audit trail.
- Confirm the Phase 3 regression test from S1-05 is updated (now patches the real `writeback_solved_example`); the AST annotation test is unchanged.
- The cassette-driven integration test is the natural place to add a *negative* assertion: after the run, `sys.modules["anthropic"]` only appears once — i.e. the LLM-cold path imported it exactly once, not on every invocation.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/transforms/coordinator.py` | Replace the S1-05 `pass` with the real `writeback_solved_example` call. |
| `src/codegenie/recipes/contract.py` | Add `RunConfig.skip_llm`, `RunConfig.skip_rag_retrieval`; regenerate contract snapshot. |
| `src/codegenie/recipes/engines/rag_llm.py` | `available()` honours `skip_llm`; `_retrieve` honours `skip_rag_retrieval`. |
| `src/codegenie/cli.py` | Bind `--no-llm` / `--no-rag` flags from S1-06 to `RunConfig` fields. |
| `tests/unit/recipes/test_orchestrator_writeback_branch_wired.py` | NEW — the three-scenario test. |
| `tests/unit/transforms/test_writeback_stub_unreachable.py` | UPDATE — replace the speculative mock with a direct `writeback_solved_example` patch; assert never-called for Phase 3 engines. |
| `tests/unit/cli/test_no_llm_disables_rag_llm_engine.py` | NEW — `available()` + `sys.modules` assertion. |
| `tests/unit/cli/test_no_llm_skips_writeback.py` | NEW — Phase 3 path still works; writeback not called. |
| `tests/unit/rag/test_no_rag_still_writebacks_llm_cold.py` | NEW — Gap 4 load-bearing test. |
| `tests/unit/recipes/engines/test_no_rag_skips_tier2_only.py` | NEW — tier-1 still consulted; tier-2 skipped. |
| `tests/unit/cli/test_no_rag_no_llm_combo.py` | NEW — flag combination doesn't crash. |
| `tests/unit/cli/test_no_llm_flag_propagates.py` | NEW — wire trace CLI → RunConfig → engine. |
| `tests/unit/cli/test_no_rag_flag_propagates.py` | NEW — wire trace CLI → RunConfig → engine. |
| `tests/unit/recipes/engines/test_rag_llm_available_honors_no_llm.py` | NEW — engine-level test. |
| `tests/integration/test_orchestrator_writeback_e2e_llm_cold.py` | NEW — extends S5-03's cassette test with post-run filesystem assertions. |
| `tests/contracts/test_run_config_snapshot.py` | UPDATE — regenerate snapshot to include the two new fields. |

## Out of scope
- **The `writeback_solved_example` callable** — handled by S6-01 (body) + S6-02 (guard). This story only wires the caller.
- **`solved-examples calibrate|list|show` CLI** — handled by S6-04.
- **Phase 11 `human_merge` promotion** — Phase 11 swaps `reason="validation_pass_auto"` for `reason="human_merge"`; Phase 4's writeback only emits `merge_status="pending_human"`.
- **The end-to-end breaking-change CVE fixture** — handled by S7-04 (`test_e2e_major_version_breaking_change.py`); this story's integration test is the writeback-side smoke check, not the full exit-criterion.
- **`--auto-promote-on-validation-pass`** — explicitly **not** part of Phase 4's default surface (NG8); production ADR-0009 forbids un-merged auto-promotion in the default corpus path. If a future story reintroduces this flag, it goes through an ADR amendment, not this one.
- **`SolvedExampleHealthProbe` consumption** — Phase 5 owns the probe-confidence-as-gate question; Phase 4 just ships the probe (S4-06) and the writebacks it inspects.

## Notes for the implementer
- **`--no-rag` is diagnostic, not reset.** This is the single most-tested behaviour in this story. The temptation to make `--no-rag` skip the writeback ("if the operator doesn't trust retrieval, they don't trust the corpus either") is exactly wrong — `--no-rag` says "use the LLM directly", and the LLM-cold path is *the* way the corpus grows from a cold start. A reviewer who suggests skipping writeback under `--no-rag` should be redirected to `phase-arch-design.md §"Gap analysis" Gap 4` verbatim.
- **`--no-llm` is hard, not soft.** `available()` returns `False` before `__init__` finishes loading the engine; `anthropic` is never imported; the API key is never read. This is testable via `sys.modules` — that test in `test_no_llm_disables_rag_llm_engine.py` is the durable contract.
- **The `None` return from `writeback_solved_example` is a non-error.** A `solved_example.writeback_refused` audit event already records the reason; the orchestrator doesn't need to re-log. Don't add a "writeback refused" warning in the coordinator — that would double-log every refusal.
- **Preserve the `# Phase 4 ADR-P4-002 conditional` comment.** S1-05's `test_writeback_stub_annotated` AST scan asserts the literal comment exists. The exact bytes matter — moving it, changing capitalisation, or rewording will turn the test red. The comment is the durable mark for code review ("here's the load-bearing branch; treat changes here with extra care").
- **`RunConfig` field additions are a Phase-3 contract bump.** Even though they're purely additive and default-`False`, the snapshot test regenerates. Surface this in the PR body + `phase-3-contract-bumped` label so reviewers see the surface area growing.
- **Cassette-driven integration test caveats.** The cassette must record the *first* run only; the second-run query-key-cache assertion runs offline. If the cassette records the second-run Anthropic call, the test loses its meaning — pin the recording mode and the cassette assertion at "no further outbound requests after the first run."
- **Phase 3 regression discipline.** Every Phase 3 fixture must still pass byte-identically. If any fail, the cause is almost always a `RunConfig` default change or an accidental import-time side-effect from `rag_llm.py`. Bisect the snapshot regen first; the contract bump is the most likely culprit.
- **Test independence.** The eight new tests must not share `chromadb` state between runs — use `tmp_path` fixtures throughout. The S4-04 stale-lock-breaker exists for production failure modes, not for tests; a test that races against the lock-breaker is testing the wrong thing.
