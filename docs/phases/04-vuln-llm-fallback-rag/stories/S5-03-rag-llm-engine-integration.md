# Story S5-03 — `RagLlmEngine` integration tests — LLM cold + RAG few-shot + cache hit

**Step:** Step 5 — Compose `RagLlmEngine` + three-tier `apply()`
**Status:** Ready
**Effort:** M
**Depends on:** S5-02 (`apply()` three-tier helpers + `tier_evidence`), S3-06 (`LeafLlmAgent` integration + cassette discipline)
**ADRs honored:** ADR-P4-004 (`LeafLlmAgent` Protocol), ADR-P4-007 (model pin), ADR-P4-010 (cost ceilings), ADR-P4-011 (`LlmPromptContext` exfil), ADR-P4-012 (VCR cassette discipline), production ADR-0011 (recipe-first/RAG/LLM chain), production ADR-0024 (cost observability)

## Context
S5-01 and S5-02 produced a `RagLlmEngine` whose unit tests prove each helper in isolation. This story exercises the engine **end-to-end** — but without the orchestrator's writeback branch (that's S6-03). Three cassette-driven integration tests prove the three load-bearing observable trajectories of the engine: (1) **`llm_cold`** — empty store, tier-1 miss, tier-2 miss, LLM call, `plan_source="llm_cold"`, cost recorded; (2) **`rag_fewshot_llm`** — seeded store with a similar-but-not-identical example at cosine ≈ 0.79, LLM called with top-3 as few-shots, `cache_read_input_tokens > 0` proves prompt-caching worked, cost ≈ $0.011 vs $0.05 cold; (3) **`egress_proxy` re-exercise** — Step 3's defence (the agent-supplied `x-api-key` header is stripped at the proxy) routed through `_invoke_llm` to prove the engine cannot be tricked into smuggling a header. All three tests are cassette-driven (`pytest-recording` with `--record-mode=none` per ADR-P4-012) so CI is fully offline and Step 7's `VCR_BAN_NEW_CASSETTES=1` gate stays green.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Scenarios — 4 representative` — the four scenarios; tests in this story implement scenarios 1 (`llm_cold`), 2 (`rag_fewshot_llm`), and 4 (`query_cache` is covered as part of S5-02's unit pass and the E2E exit-criterion in Step 7).
  - `../phase-arch-design.md §Process view — runtime` — the sequence diagram these tests black-box.
  - `../phase-arch-design.md §Testing strategy — Test pyramid` — integration tier sits between unit (S5-02) and E2E (S7-04); cassettes are the integration substrate.
  - `../phase-arch-design.md §Harness engineering — Replay / debugability` — `before_record_response` rewrites canary, raw response JSON dumped under `.codegenie/remediation/<run-id>/llm/raw.json` — the test fixtures assert both.
  - `../phase-arch-design.md §Edge cases #12 (`x-api-key` smuggling)` — the proxy strips agent-supplied auth headers; this story re-exercises the Step-3 defence through the engine.
- **Phase ADRs:**
  - `../ADRs/0004-leaf-llm-agent-protocol-os-tiered.md` — ADR-P4-004 — the test pins the in-process and (where Linux) jailed `LeafLlmAgent` implementations both routed through `_invoke_llm`.
  - `../ADRs/0007-anthropic-model-pin-via-versioned-alias.md` — ADR-P4-007 — cassettes are recorded against the versioned alias; rate calculations come from the same `rates.yaml`.
  - `../ADRs/0010-llm-invocation-guard-running-total-with-override.md` — ADR-P4-010 — cassette-driven cost-aggregation assertions land in `tier_evidence.cost_usd`.
  - `../ADRs/0011-llm-prompt-context-exfiltration-boundary.md` — ADR-P4-011 — the `rag_fewshot_llm` cassette's recorded prompt is asserted not to contain seeded synthetic secrets.
  - `../ADRs/0012-vcr-cassette-discipline.md` — ADR-P4-012 — `--record-mode=none`, `before_record_response` canary rewrite, no new cassette without the `cassettes-reviewed` PR label.
  - `../ADRs/0008-prompt-injection-structural-defenses.md` — ADR-P4-008 — the prompt-injection cassettes are Step 7's harden surface, not this story's; this story exercises the happy paths through the same defences.
- **Production ADRs:**
  - `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — the decision chain these tests prove.
  - `../../../production/adrs/0024-cost-observability-end-to-end.md` — `cost.llm.invoked` event aggregation; the integration tests assert one event per network call.
- **Source design:** `../final-design.md §13 — Data-flow scenarios` — the cassette-A / cassette-B story for the first and second portfolio peers; this story instantiates the first-peer half.
- **High-level impl:** `../High-level-impl.md §Step 5` — done-criteria lines for `test_e2e_llm_cold.py`, `test_e2e_rag_then_llm_fewshot.py`, `test_egress_proxy_blocks_x_api_key_in_request.py`.
- **Existing code:**
  - `src/codegenie/recipes/engines/rag_llm.py` (S5-02) — the engine under test.
  - `src/codegenie/llm/leaf_anthropic/` (S3-01–S3-06) — the leaf implementations the engine calls through.
  - `tests/conftest.py` — cassette fixture scaffolding from Step 3.
  - `tests/cassettes/` — the Step 3 cassette directory; new fixtures land here under the `phase4_step5/` subfolder.

## Goal
Prove `RagLlmEngine` produces the right `plan_source`, `tier_evidence`, and observable side-effects (cost ledger, raw-response dump, prompt-cache hit, egress-proxy header strip) under three cassette-driven end-to-end scenarios — without invoking the orchestrator or writeback branch.

## Acceptance criteria
- [ ] `tests/integration/test_e2e_llm_cold.py` exists and:
  - Starts with an **empty** `SolvedExampleStore` (`store.read().query` returns `[]`) and an empty `QueryKeyCache`.
  - Drives `RagLlmEngine.apply(...)` against a real `InProcessLeafLlmAgent` (or `JailedLeafLlmAgent` on Linux) using a cassette `tests/cassettes/phase4_step5/llm_cold_first_peer.yaml` recorded against the pinned model.
  - Asserts `RecipeApplication.engine_used == "rag_llm"`, `tier_evidence.tier_used == "tier3_llm"`, `tier_evidence.plan_source == "llm_cold"`, `tier_evidence.few_shots_used == 0`, `tier_evidence.top1_cosine is None`, `tier_evidence.cache_hit_key is None`.
  - Asserts `tier_evidence.cost_usd > 0` and matches the cassette's recorded token counts × `rates.yaml` to within rounding tolerance.
  - Asserts `.codegenie/remediation/<run-id>/llm/raw.json` was written and the file's `cost_usd` matches `tier_evidence.cost_usd`.
  - Asserts a `cost.llm.invoked` audit event was emitted exactly once with the correct `(workflow_id, stage, node, model)` aggregation key (production ADR-0024 shape).
  - Asserts `remediation-report.yaml#phase4.tier_evidence` is populated and round-trips.
- [ ] `tests/integration/test_e2e_rag_then_llm_fewshot.py` exists and:
  - Seeds `SolvedExampleStore` with one `SolvedExample` whose embedding sits at cosine ≈ 0.79 to the query vector (close enough for tier-2 retrieval, below `τ_hit=0.86`). The seeded example's `plan.kind` is either `recipe_invocation` or `manual_patch` — the test parametrises both and asserts the same `plan_source == "rag_fewshot_llm"` (the `manual_patch` case in this band is *always* few-shot, never exact, even if a future τ_hit drop crossed 0.79).
  - Drives the engine using cassette `tests/cassettes/phase4_step5/rag_fewshot_llm.yaml` recorded with a few-shots block.
  - Asserts `tier_evidence.plan_source == "rag_fewshot_llm"`, `tier_evidence.few_shots_used == 3` (or fewer when fewer rows seeded), `tier_evidence.top1_cosine` within `[0.78, 0.80]`.
  - Asserts `cache_read_input_tokens > 0` on the recorded `LlmResponse` (prompt-caching the system + few-shots block worked — production ADR-0024 / cost story).
  - Asserts cost is in the ≈ $0.011 ± 25% band (the cassette pins token counts, so the band is conservative; the assertion exists to keep the cost story honest in the diff).
  - Asserts the rendered prompt body (dumped to `.../llm/request.json`) **does not** contain any of the seeded synthetic secrets from the fixture `RepoContext` (re-exercises ADR-P4-011 at the integration layer).
- [ ] `tests/security/test_egress_proxy_blocks_x_api_key_in_request.py` exists and:
  - Only runs on Linux (skipped on macOS with a documented `pytest.mark.skipif`) per ADR-P4-004's jailed-leaf-is-Linux-only invariant.
  - Routes through `RagLlmEngine._invoke_llm` against `JailedLeafLlmAgent` + `EgressProxy` daemon (the Step 3 wiring).
  - Crafts an `LlmRequest` whose `system_blocks` *attempt* to smuggle an `x-api-key` header (e.g. via an injected `headers:` field that an injection might try to coerce out of the schema; the test pins the negative — `LlmRequest` is `extra="forbid"` so the field can't exist on the model, but the test asserts the schema rejection AND the proxy's wire-level header strip).
  - Asserts the proxy log records `egress.header_stripped(name="x-api-key")` AND the upstream Anthropic call was made with the proxy-held key (not the agent-supplied one).
  - Asserts no `LlmTransportError` was raised on the happy path (the strip is silent to the engine; observability lives in the proxy log).
- [ ] All three test files use `@pytest.mark.vcr` with `record_mode="none"` — CI fails if any test tries to record a new cassette (Step 7 lands the `VCR_BAN_NEW_CASSETTES=1` env gate; this story sets `record_mode="none"` per-file as the local discipline).
- [ ] The cassettes live under `tests/cassettes/phase4_step5/` and are committed alongside the test files. PR carries the `cassettes-reviewed` label (ADR-P4-012 discipline) — the PR description lists the cassettes added and the human review attestation.
- [ ] The integration suite passes `pytest tests/integration/test_e2e_llm_cold.py tests/integration/test_e2e_rag_then_llm_fewshot.py tests/security/test_egress_proxy_blocks_x_api_key_in_request.py` with no network calls (assert via a `tests/conftest.py` fixture that monkeypatches `socket.socket` to refuse any non-cassette traffic — Step 3 already shipped this fixture; this story reuses it).
- [ ] `ruff`, `ruff format`, `mypy --strict` on the test files pass. Cassette YAML is reviewed; no `cache_creation_input_tokens > 0` on the `cassette-A` (cold) recording (cold-path can't hit cache) but **must** be present on the `cassette-B` (few-shot) recording.

## Implementation outline
1. Create `tests/integration/test_e2e_llm_cold.py`. Build a `RagLlmEngine` fixture (`@pytest.fixture engine_under_test`) wiring **real** `LeafLlmAgent` (in-process on macOS, jailed on Linux), `OutputValidator`, `PromptLoader`, `LlmInvocationGuard` (defaults from ADR-P4-010), `EmbeddingProvider` (S4-01 — local `bge-small-en-v1.5`; cassette pins the embedding output too via a `dummy=False, sha_pinned=True` fixture mode), `SolvedExampleStore` (empty), `QueryKeyCache` (empty).
2. Record cassette `tests/cassettes/phase4_step5/llm_cold_first_peer.yaml` against the live Anthropic API once (locally, with the `cassettes-reviewed` discipline). On replay, set `record_mode="none"`. Configure `before_record_response` to rewrite the canary token to a fixture-known value so the `OutputValidator`'s canary check survives replay.
3. The test fixture passes a `RepoContext` seeded with a known CVE advisory + a known lockfile fingerprint. Run `engine.apply(...)` and capture the `RecipeApplication`. Assertions follow the ACs.
4. Create `tests/integration/test_e2e_rag_then_llm_fewshot.py`. Seed the store via the writeback-internals (S6-01 not yet wired — this story uses a direct `SolvedExampleStore._test_seed(...)` helper added under `pytest.mark` so production code is not coupled). The seeded example's embedding sits at cosine ≈ 0.79 to the test query (computed offline; the cassette pins the embedding sidecar output).
5. Parametrise the `plan.kind` of the seeded example over `["recipe_invocation","manual_patch"]`. Both should produce `plan_source="rag_fewshot_llm"` because the cosine is in the few-shot band, not the exact band. The Gap-1 discipline is exercised more aggressively in S5-02's unit test (`test_rag_exact_only_fires_on_recipe_invocation_plan.py`); this story's value is the **few-shot bandwidth path** observed end-to-end.
6. Record cassette `tests/cassettes/phase4_step5/rag_fewshot_llm.yaml` with `cache_read_input_tokens > 0` on the second request of a paired record (prompt-caching needs a warm cache; either record two requests back-to-back or arrange the fixture to hit a `cache_creation` recording first). Document the recording procedure in the cassette directory's `README.md`.
7. Create `tests/security/test_egress_proxy_blocks_x_api_key_in_request.py`. Skip on non-Linux. Spin up the `EgressProxy` daemon (Step 3's helper), point `JailedLeafLlmAgent` at it, build an `LlmRequest` and route through `engine._invoke_llm`. Use a cassette that includes a `before_record_request` hook stripping the recorded API key. Assert the proxy log line.
8. Wire all three tests against the existing network-block conftest fixture (`tests/conftest.py::no_real_network`) so any test that tries to escape the cassette substrate fails loudly.
9. Run `pytest tests/integration tests/security` locally — must pass with no network. Re-run with the prod-cassette tooling to confirm cassettes haven't drifted.
10. Add the cassettes under `tests/cassettes/phase4_step5/` and tag the PR with `cassettes-reviewed`. The PR description lists each cassette by file name, with the reviewer attestation (`reviewed: yes — <name>, <date>`).

## TDD plan — red / green / refactor

### Red
`tests/integration/test_e2e_llm_cold.py`
```python
import pytest
from pathlib import Path
from codegenie.recipes.engines.rag_llm import RagLlmEngine
from codegenie.observability.audit import drain_audit_events

@pytest.mark.vcr(record_mode="none")
def test_llm_cold_first_peer_produces_llm_cold_plan_source(engine_under_test, npm_breaking_change_advisory, tmp_repo):
    app = engine_under_test.apply(recipe=_fallback_recipe(npm_breaking_change_advisory),
                                  repo=tmp_repo,
                                  ctx=_apply_ctx(remaining_budget_usd=Decimal("0.50")))
    te = app.tier_evidence
    assert app.engine_used == "rag_llm"
    assert te.tier_used == "tier3_llm"
    assert te.plan_source == "llm_cold"
    assert te.few_shots_used == 0
    assert te.top1_cosine is None
    assert te.cache_hit_key is None
    assert te.cost_usd > 0
    raw = Path(f".codegenie/remediation/{_run_id()}/llm/raw.json")
    assert raw.exists()
    events = drain_audit_events()
    invoked = [e for e in events if e.name == "cost.llm.invoked"]
    assert len(invoked) == 1
    assert invoked[0].attrs["model"] == "claude-sonnet-4-7"
```

`tests/integration/test_e2e_rag_then_llm_fewshot.py`
```python
@pytest.mark.parametrize("seeded_kind", ["recipe_invocation", "manual_patch"])
@pytest.mark.vcr(record_mode="none")
def test_cosine_in_fewshot_band_calls_llm_with_top3(seeded_kind, engine_under_test_seeded, ...):
    app = engine_under_test_seeded(kind=seeded_kind, cosine=0.79).apply(...)
    te = app.tier_evidence
    assert te.plan_source == "rag_fewshot_llm"
    assert te.few_shots_used in (1, 2, 3)
    assert 0.78 <= te.top1_cosine <= 0.80
    # cache-read proves prompt caching worked
    assert _last_recorded_response().cache_read_input_tokens > 0
    # No secret leakage (ADR-P4-011)
    request_dump = Path(f".codegenie/remediation/{_run_id()}/llm/request.json").read_text()
    for secret in SEEDED_SYNTHETIC_SECRETS:
        assert secret not in request_dump
```

`tests/security/test_egress_proxy_blocks_x_api_key_in_request.py`
```python
import sys, pytest

@pytest.mark.skipif(sys.platform != "linux", reason="Jailed leaf + EgressProxy is Linux-only (ADR-P4-004).")
@pytest.mark.vcr(record_mode="none")
def test_agent_supplied_x_api_key_is_stripped_at_proxy(engine_under_test_jailed, egress_proxy_log):
    # Engine-side: build a request that an injection might try to coerce headers from.
    # LlmRequest is extra="forbid" so a `headers:` field would never instantiate;
    # but the proxy is the wire-level defence — exercise it.
    app = engine_under_test_jailed.apply(...)
    log = egress_proxy_log.read_text()
    assert "egress.header_stripped(name=\"x-api-key\")" in log
    assert app.engine_used == "rag_llm"
```

### Green
Three test files; three cassettes; one `tests/cassettes/phase4_step5/README.md` documenting recording procedure. Reuse Step 3 conftest fixtures (`no_real_network`, `tmp_repo`, `npm_breaking_change_advisory`, `engine_under_test`).

### Refactor
- Extract `_apply_ctx`, `_fallback_recipe`, `_run_id` helpers into a `tests/integration/_helpers.py` so the three tests share scaffolding without copy-paste.
- Document the cassette recording procedure in `tests/cassettes/phase4_step5/README.md`: env-var setup, the `--record-mode=once` invocation, the `cassettes-reviewed` review checklist (canary rewrite verified, no API key in YAML, no secret echoes).
- Add a `tests/integration/conftest.py` fixture `assert_no_drift` that diffs the recorded cassette's recorded model against `rates.yaml`'s pinned alias — drift here means the next CI run will produce wrong cost numbers.
- Re-run the suite under `pytest -p pytest_recording -ra` to catch any cassette that was silently re-recorded.
- Watch out: the embedding-provider cassette layer (`SentenceTransformerProvider` is local, not network) is **not** in scope here. The store seeding uses pre-computed embeddings; if the embedding model changes (digest bump), Step 4's `solved-examples reindex` workflow handles it, but the fixture data here uses the SHA-pinned model from ADR-P4-006.

## Files to touch
| Path | Why |
|---|---|
| `tests/integration/test_e2e_llm_cold.py` | NEW — cold-path scenario 1 (`final-design.md §13`). |
| `tests/integration/test_e2e_rag_then_llm_fewshot.py` | NEW — few-shot scenario 2; cassette-B prompt-cache assertion. |
| `tests/security/test_egress_proxy_blocks_x_api_key_in_request.py` | NEW — Linux-only re-exercise of Step 3's header-strip defence routed through the engine. |
| `tests/integration/_helpers.py` | NEW — small shared helpers (`_apply_ctx`, `_run_id`). |
| `tests/cassettes/phase4_step5/llm_cold_first_peer.yaml` | NEW — recorded cassette (cold). |
| `tests/cassettes/phase4_step5/rag_fewshot_llm.yaml` | NEW — recorded cassette (warm; `cache_read_input_tokens > 0`). |
| `tests/cassettes/phase4_step5/egress_proxy_x_api_key_strip.yaml` | NEW — recorded cassette (Linux-only test). |
| `tests/cassettes/phase4_step5/README.md` | NEW — cassette recording / review checklist. |

## Out of scope
- **The E2E exit-criterion fixture (`tests/e2e/test_e2e_major_version_breaking_change.py`)** — handled by S7-04. This story's `test_e2e_llm_cold.py` is *integration*, not E2E; the orchestrator is not engaged.
- **Writeback assertions on the cold path** — handled by S6-01 / S6-02 / S6-03. The writeback function body is still `pass` at this story's commit.
- **Prompt-injection cassettes (ROT13 canary, action-surface block)** — handled by S7-02. This story exercises happy paths; adversarial cassettes are the harden surface.
- **Recall@3 ≥ 0.85 canary** — handled by S7-03. This story records two specific recordings; the labelled-triple recall measurement is its own fixture set.
- **Cost canary (G6/G7/G8) perf assertions** — handled by S7-05. This story's cost assertions are correctness (cost recorded; ≈ band), not performance regression.

## Notes for the implementer
- All three tests must run with `--record-mode=none`. If a test tries to re-record (because a developer rebuilt the cassette and committed it without review), the Step 7 CI gate `VCR_BAN_NEW_CASSETTES=1` will catch it — but the conscientious form is to fail locally first.
- The `cassettes-reviewed` label is non-optional. The reviewer checks: (a) no API key in the cassette body, (b) the `before_record_response` canary-rewrite hook ran, (c) the recorded model id matches `rates.yaml`, (d) no `RepoContext` secret-row leak in the recorded request. ADR-P4-012 lists this checklist verbatim.
- The few-shot cassette must have `cache_read_input_tokens > 0` on the recorded response — this proves the system + few-shots `cache_control=ephemeral` actually fired the Anthropic prompt-cache hit. Without that bit, the cost story is a lie and the integration test passes a fraud. If the recording shows zero cache reads, re-record after running the system prompt against the API once to warm the cache.
- The seeded synthetic secrets list (`SEEDED_SYNTHETIC_SECRETS`) lives in `tests/fixtures/synthetic_secrets.py` from ADR-P4-011's CI test. Reuse it; do not invent new patterns here.
- The `EgressProxy` test is Linux-only. The macOS skip is documented; do not "make it pass on macOS" by stubbing the proxy. ADR-P4-004's OS-tiered Protocol is the design — Linux gets the proxy, macOS gets the in-process leaf.
- The store-seeding helper (`SolvedExampleStore._test_seed`) is a test-only seam. Mark it with `pytest.mark` or guard it with a `_TESTING` env var so it cannot be called from production code. S6-01's real `writeback_solved_example` is the canonical writer; this seam is scaffold and will be torn out in Step 7 once the writeback path is exercised end-to-end.
- Cost-band assertions are deliberately wide (`±25%`). The cassette pins token counts exactly; the band is room for rate-table edits between recording and replay. If the band assertion fails, check `rates.yaml` first — not the engine.
