# Story S6-01 — `writeback_solved_example` synchronous triple-write

**Step:** Step 6 — Ship synchronous gated `writeback_solved_example` + Gap-4 semantics + operator CLI
**Status:** Ready
**Effort:** M
**Depends on:** S5-02 (`apply()` produces `tier_evidence` with `plan_source` and full cost story), S4-04 (`SolvedExampleStore` with always-on `embedding_model_digest` filter, flock, stale-lock-breaker, bodies-on-disk layout), S4-05 (`QueryKeyCache.put(qk, plan, example_id)` synchronous)
**ADRs honored:** ADR-P4-002 (two-tier writeback, `provenance.merge_status="pending_human"`), ADR-P4-005 (chromadb in-process), ADR-P4-006 (bge-small embedding model SHA-pinned + digest in every metadata row), ADR-P4-011 (`LlmPromptContext` exfil boundary — body must not carry untrusted-text artefacts beyond what the schema names), ADR-P4-015 (`SolvedExample` v0.4.0 task-class-generic schema)

## Context
S5-02 produced the `RecipeApplication` carrying `engine_used="rag_llm"` and a populated `tier_evidence`. S4-04 / S4-05 produced the durable substrate (chromadb collection + bodies dir + query-key cache). Phase 3's `TrustScorer` ran and `passed`. The orchestrator's S1-05 stub branch has so far been a `pass` — this story lands the real callable `writeback_solved_example` that the S6-03 promotion will invoke. The function performs **three writes in a deterministic order, all synchronous, all inside the same worker** (no background tasks, no fire-and-forget, no `asyncio.create_task` that outlives the caller): (1) write the canonical `SolvedExample` body JSON to `.codegenie/rag/bodies/<id>.json`; (2) upsert the chromadb row with an **eagerly-computed embedding** keyed on `provenance.embedding_model_digest`; (3) `query_key_cache.put(qk, plan, example_id)`. Body-first ordering is load-bearing — chromadb upsert can never reference a body that does not yet exist on disk. Failure handling is split by tier: a chromadb upsert failure retries once and on still-fail leaves the body as an orphan + audits `writeback.partial_failure` (recovered by `solved-examples prune --orphans`). The strict-guard matrix is deferred to S6-02; this story lands the happy path + body-first ordering + synchronous query-key-cache write.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §"Component design" #8` — `SolvedExampleStore` + `SolvedExampleWriter` + `SolvedExamplePromoter` interfaces; the body-on-disk vs chromadb-index split (chromadb stores `(id, embedding, small metadata)`; bodies at `.codegenie/rag/bodies/<id>.json` canonical sorted-keys LF).
  - `../phase-arch-design.md §"Control flow"` step 9 — Decision point E (`TrustScorer.passed && engine_used == "rag_llm"` → synchronous `writeback_solved_example`); this story implements the callable; S6-03 wires it into the orchestrator branch.
  - `../phase-arch-design.md §"Process view — runtime"` Scenario B — the writeback sequence diagram (`ORCH → WRITER → STORE → CACHE`); note that all three calls return before the orchestrator's branch exits.
  - `../phase-arch-design.md §"Data model"` — `SolvedExample` v0.4.0 (`extra="forbid", frozen=True`), `Provenance` (carries `merge_status`, `audit_chain_head`, `embedding_model_digest`), `EngineAttempt` (`engine_trajectory` list), `Fingerprint`.
  - `../phase-arch-design.md §"Edge cases"` rows EC4 (chromadb corruption — quarantine + force `--no-rag`), EC10 (chromadb upsert failure recovery), EC15 (orphan body — `prune --orphans`).
- **Phase ADRs:**
  - `../ADRs/0002-two-tier-writeback-pending-promoted.md` — ADR-P4-002 — `merge_status="pending_human"` at writeback time; promotion is a separate step Phase 11 owns.
  - `../ADRs/0015-solved-example-schema-task-class-generic.md` — ADR-P4-015 — `task_class="vuln"` and the v0.4.0 schema; `embedding_model_digest` is part of the schema, not a free-form metadata field.
  - `../ADRs/0005-chromadb-in-process-with-stale-lock-detection.md` — ADR-P4-005 — chromadb exclusive flock + stale-lock-breaker (consumed via `SolvedExampleStore.write()`).
  - `../ADRs/0006-bge-small-en-embedding-model-sha-pinned.md` — ADR-P4-006 — `EmbeddingProvider.model_digest` is the digest the writeback stamps into the row.
  - `../ADRs/0011-llm-prompt-context-exfiltration-boundary.md` — ADR-P4-011 — the body must not lift raw `RepoContext` / advisory description bytes; only fields named by `SolvedExample` are persisted.
  - `../ADRs/0010-llm-invocation-guard-running-total-with-override.md` — ADR-P4-010 — the `cost_report` field is the same `Decimal`-and-tokens shape `tier_evidence` carries.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` — production ADR-0009 — why writeback is two-tier; the writer ships `merge_status="pending_human"` only.
- **Source design:**
  - `../final-design.md §"Synthesis ledger" row "Writeback timing"` (winner sum 12/12) — the two-tier model.
  - `../final-design.md §"Components" #7` — the writer + promoter API surface this story instantiates.
- **Existing code:**
  - `src/codegenie/rag/store.py` (S4-04) — `store.write()` exclusive-flock context manager; `store.add_or_update(example, collection)`; bodies-dir path resolution.
  - `src/codegenie/rag/query_key_cache.py` (S4-05) — `cache.put(qk, plan, example_id)`.
  - `src/codegenie/rag/contract.py` + `models.py` (S1-03) — `SolvedExample`, `Provenance`, `EngineAttempt`, `Fingerprint`, `CostSummary`.
  - `src/codegenie/audit_writer.py` (Phase 2) — `audit.emit(event_name, payload)`; the BLAKE3-chained audit log.
  - `src/codegenie/recipes/contract.py` (Phase 3 + S5-02) — `RecipeApplication`, `TierEvidence`.

## Goal
Land `src/codegenie/rag/writeback.py` with `writeback_solved_example(...)` that synchronously and deterministically writes (body JSON → chromadb upsert with eagerly-computed embedding → query-key-cache `put`) inside the calling worker, leaves the body as an orphan + audits `writeback.partial_failure` on chromadb upsert failure, and returns the assembled `SolvedExample` with `provenance.merge_status="pending_human"`.

## Acceptance criteria
- [ ] `src/codegenie/rag/writeback.py` exports `writeback_solved_example(*, run_id: str, advisory: AdvisoryRef, recipe_selection: RecipeSelection, recipe_application: RecipeApplication, validation_outcomes: ValidationOutcomes, cost_report: CostReport, store: SolvedExampleStore, query_key_cache: QueryKeyCache, audit: AuditWriter, embedding: EmbeddingProvider) -> SolvedExample` — exact signature, all kwargs, returns the constructed `SolvedExample`. No `Any`, no `**kwargs`. `mypy --strict` clean.
- [ ] The three writes execute in this order **before** the function returns; no `asyncio.create_task`, no `threading.Thread`, no `concurrent.futures.Executor.submit` whose future is not awaited:
  1. Canonical body JSON written to `.codegenie/rag/bodies/<id>.json` via `tempfile + os.replace` (atomic). `id = blake3_hex(canonical_body_json_with_id_field_blanked)` — content-addressed and deterministic (`test_solved_example_id_deterministic` round-trips this).
  2. chromadb upsert with eagerly-computed embedding under `store.write()` (exclusive flock). Metadata row includes `embedding_model_digest = embedding.model_digest`, `task_class="vuln"`, `ecosystem`, `language`, `provenance.merge_status="pending_human"`, `provenance.repo_url`, `provenance.public`, `provenance.audit_chain_head`.
  3. `query_key_cache.put(qk, plan, example_id=solved_example.id)` synchronously — completes before the function returns.
- [ ] `tests/unit/rag/test_writeback_synchronous.py` verifies the no-background-task invariant with a fault-injected mock that records call-completion timestamps for all three writes and asserts the function does **not** return until all three have recorded completion. The test also asserts `asyncio.all_tasks()` is unchanged across the call and that no thread named `writeback*` survives the call.
- [ ] `tests/unit/rag/test_writeback_body_first_ordering.py` proves the body-first invariant: if chromadb upsert is patched to assert `Path(".codegenie/rag/bodies/<id>.json").exists()` on entry, the assertion passes; reversing the order in the implementation makes this test red.
- [ ] `tests/unit/rag/test_writeback_idempotent.py` — calling `writeback_solved_example` twice with byte-identical inputs results in: the same `SolvedExample.id`, exactly one body file on disk (second call's `os.replace` overwrites byte-identically), exactly one chromadb row (idempotent on id), exactly one `query_key_cache` entry. The second call emits `solved_example.duplicate_skipped` (or `writeback.idempotent_replay` — implementation choice, but tested).
- [ ] `tests/unit/rag/test_writeback_partial_failure_orphan_body.py` — body JSON write succeeds, chromadb upsert raises on first attempt, retry-once raises again → function returns a `SolvedExample` with `provenance.merge_status="pending_human"`, audit chain has `writeback.partial_failure(example_id, reason)`, the body file persists on disk for `prune --orphans` recovery. The query-key cache `put` does **not** fire in the partial-failure path.
- [ ] `tests/unit/rag/test_writeback_query_key_cache_synchronous.py` (closes critic §P.1) — `query_key_cache.put` is called exactly once with `(qk, plan, example_id)` *before* the function returns. A spy that records `time.monotonic_ns()` on `put` entry vs the function's return timestamp asserts `put_entry_ns <= return_ns`. No fire-and-forget.
- [ ] `tests/unit/rag/test_writeback_audit_chain_linkage.py` — the constructed `Provenance.audit_chain_head` matches the BLAKE3 hex of the run's audit chain head at writeback time (forensic linkage per ADR-P4-002). A `solved_example.written` audit event is emitted carrying `(run_id, example_id, body_blake3, audit_chain_head)`.
- [ ] `tests/unit/rag/test_writeback_two_worker_race.py` — two concurrent calls with the same `example_id` (same advisory, same lockfile fingerprint) both complete successfully under exclusive flock; both record byte-identical bodies (`os.replace` atomic); chromadb sees one row; exactly one `solved_example.race_observed` audit event is emitted by the second-arriving writer. The test uses `multiprocessing.Process` to dodge GIL serialisation.
- [ ] `SolvedExample` fields populated by the writer: `id`, `schema_version="0.4.0"`, `task_class="vuln"`, `ecosystem`, `language`, `advisory` (from `AdvisoryRef`), `repo_fingerprint` (from `recipe_selection.repo_fingerprint`), `recipe_failure_reason` (from `recipe_selection.failure_reason`), `engine_trajectory` (from `recipe_application.engine_trajectory`), `plan` (from `recipe_application.plan`), `diff_path` (path under bodies/ — body carries diff, not chromadb), `embedding_model="bge-small-en-v1.5"`, `embedding_digest=embedding.model_digest`, `dimensions=384`, `provenance` (constructed in this story — see next bullet), `created_at` (UTC ISO8601).
- [ ] `Provenance` fields populated: `merge_status="pending_human"` (always — no flag flips this in Phase 4), `repo_url`, `public`, `audit_chain_head`, `source = "llm_cold" | "llm_fewshot"` (mirrors `tier_evidence.plan_source`), `promoted_by=None`, `promoted_reason=None`, `merge_sha=None` (Phase 11 fills).
- [ ] `tests/unit/rag/test_writeback_body_canonical_form.py` — body JSON serialisation uses canonical form: sorted keys, LF line endings, no trailing whitespace, `ensure_ascii=False`, `separators=(",", ":")` (no spaces). Property test: shuffled-input-field-order produces byte-identical output.
- [ ] `tests/unit/rag/test_writeback_extra_forbid.py` — attempting to set any field not in the `SolvedExample` schema (e.g. an extra `notes` kwarg in a hand-rolled dict) raises Pydantic `ValidationError` at construction; same for `Provenance`.
- [ ] All Step 6 code under `src/codegenie/rag/writeback.py` passes `mypy --strict`, `ruff check`, `ruff format --check`; coverage floor for this file is 95/90 per `stories/README.md §"Per-module coverage"`.

## Implementation outline
1. Land `src/codegenie/rag/writeback.py` with the function signature and a docstring referencing ADR-P4-002 verbatim. Do not export anything else from this module (single public function).
2. Stage 1 — build the `SolvedExample` Pydantic object in-memory (no I/O yet). Compute `id` last: serialise the body with `id=""`, BLAKE3-hash the canonical bytes, fill `id`, re-serialise. The id is content-addressed; same inputs → same id (the `test_solved_example_id_deterministic` invariant from S4-04 covers this).
3. Stage 2 — body write. `tempfile.NamedTemporaryFile(dir=bodies_dir, delete=False)`, write canonical bytes, `os.replace(tmp_path, final_path)`. Wrap in `try`/`except OSError` → audit `writeback.body_write_failed` + re-raise (no retry — disk failure is operator territory).
4. Stage 3 — chromadb upsert. Compute embedding via `embedding.embed([advisory_summary + plan_summary_text])[0]` (the exact `text_for_embedding` formula is defined in S4-04; reuse the helper). Open `store.write()` (exclusive flock — re-uses S4-04 machinery), call `store.add_or_update(example, collection="vuln_solved_examples_pending")`. On exception: retry once after 100 ms sleep; on still-fail emit `writeback.partial_failure(example_id, reason)` audit event and skip stage 4. **Do not raise**; return the `SolvedExample` so the orchestrator can still write the run report.
5. Stage 4 — query-key-cache `put`. Compute `qk` via `QueryKey.from(advisory, repo_fingerprint, recipe_selection, prompt_template_id, prompt_template_version)` (the same helper `_compute_query_key` exposes from S5-02 — extract to a shared module if circular imports demand it). Call `query_key_cache.put(qk, plan=recipe_application.plan, example_id=solved_example.id)`. This is synchronous; the call's return is the function's return.
6. Stage 5 — audit. Emit `solved_example.written(run_id, example_id, body_blake3, audit_chain_head, plan_source, merge_status="pending_human")`. The audit-chain BLAKE3 update is part of `audit.emit` — captured by the linkage test.
7. **Strict-guard refusal logic is deferred to S6-02** — this story's body assumes the guard has already cleared. Write a `# guard checked in S6-02 — do not call this function without the guard` docstring comment so the dependency graph is explicit.

## TDD plan — red / green / refactor

### Red
Test file path: `tests/unit/rag/test_writeback_synchronous.py`
```python
import time
from unittest.mock import MagicMock
import pytest

from codegenie.rag.writeback import writeback_solved_example


def test_all_three_writes_complete_before_return(tmp_path):
    """No fire-and-forget: body, chromadb upsert, and qk-cache put all done synchronously."""
    completions: list[tuple[str, int]] = []

    def _record(name):
        def _fn(*a, **kw):
            completions.append((name, time.monotonic_ns()))
        return _fn

    store = MagicMock()
    store.write.return_value.__enter__.return_value.add_or_update.side_effect = _record("chroma")
    cache = MagicMock(); cache.put.side_effect = _record("qk")
    audit = MagicMock()
    embedding = MagicMock(model_digest="d" * 64); embedding.embed.return_value = [[0.0] * 384]

    # ... build minimal fixtures for advisory / recipe_selection / recipe_application / validation_outcomes / cost_report ...

    pre_return_ns = time.monotonic_ns()
    example = writeback_solved_example(
        run_id="r1", advisory=..., recipe_selection=..., recipe_application=...,
        validation_outcomes=..., cost_report=..., store=store, query_key_cache=cache,
        audit=audit, embedding=embedding,
    )
    post_return_ns = time.monotonic_ns()

    # body file written *before* return
    body_path = tmp_path / ".codegenie/rag/bodies" / f"{example.id}.json"
    assert body_path.exists()

    # chromadb upsert recorded *before* return
    assert any(name == "chroma" and ts <= post_return_ns for name, ts in completions)
    # qk-cache put recorded *before* return (critic §P.1)
    assert any(name == "qk" and ts <= post_return_ns for name, ts in completions)
```

`tests/unit/rag/test_writeback_partial_failure_orphan_body.py`
```python
def test_chromadb_failure_leaves_orphan_body_and_audits(tmp_path):
    store = MagicMock()
    store.write.return_value.__enter__.return_value.add_or_update.side_effect = RuntimeError("chroma down")
    cache = MagicMock()
    audit = MagicMock()
    embedding = MagicMock(model_digest="d" * 64); embedding.embed.return_value = [[0.0] * 384]

    example = writeback_solved_example(...)  # returns despite chromadb failure

    body_path = tmp_path / ".codegenie/rag/bodies" / f"{example.id}.json"
    assert body_path.exists(), "orphan body must persist for prune --orphans recovery"
    cache.put.assert_not_called(), "qk-cache must not fire on partial failure"
    audit.emit.assert_any_call("writeback.partial_failure", {
        "run_id": "r1", "example_id": example.id, "reason": "chromadb_upsert_failed_after_retry",
    })
```

### Green
Smallest implementation: build `SolvedExample`; `tempfile + os.replace` for the body; `store.write()` context manager around `embed + add_or_update` with one retry; on failure-after-retry, audit `writeback.partial_failure` and skip qk-cache; on success, call `query_key_cache.put` and audit `solved_example.written`. No threads, no tasks, no executors.

### Refactor
- Extract the canonical-body-bytes helper (`_canonical_body_bytes(example: SolvedExample) -> bytes`) into a module-private function — it is shared by the id-computation step and the on-disk write.
- Pull the chromadb-upsert + retry into `_upsert_with_retry(store, example, embedding) -> bool` returning success/failure; the caller decides whether to qk-cache-put.
- Bounded refactor: do **not** introduce a `Writer` class. The function shape is the contract; the orchestrator calls it as a module-level function in S6-03. A class would invite stateful drift.
- Add structured logging: `rag.writeback.body_written`, `rag.writeback.chroma_upserted`, `rag.writeback.qk_put`, `rag.writeback.race_observed`, `rag.writeback.partial_failure`. These power Step 7's audit-completeness test (G14).
- Note in the docstring: "S6-02 lands the strict guard that gates whether this function is called at all. This function itself is the **happy path**; the guard's refusal path emits `solved_example.writeback_refused` and does not call this."

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/rag/writeback.py` | NEW — `writeback_solved_example` module-level function + private helpers. |
| `src/codegenie/rag/__init__.py` | Export `writeback_solved_example` for the orchestrator. |
| `src/codegenie/rag/_canonical.py` | NEW (optional) — `_canonical_body_bytes` helper if extracted out of `writeback.py`. |
| `tests/unit/rag/test_writeback_synchronous.py` | NEW — no-background-task invariant + return-after-all-three-writes. |
| `tests/unit/rag/test_writeback_body_first_ordering.py` | NEW — body exists before chromadb upsert. |
| `tests/unit/rag/test_writeback_idempotent.py` | NEW — same inputs → same id, single body, single chroma row, single qk-cache entry. |
| `tests/unit/rag/test_writeback_partial_failure_orphan_body.py` | NEW — orphan body on chromadb failure; qk-cache not touched. |
| `tests/unit/rag/test_writeback_query_key_cache_synchronous.py` | NEW — closes critic §P.1; qk-cache `put` completes before return. |
| `tests/unit/rag/test_writeback_audit_chain_linkage.py` | NEW — `provenance.audit_chain_head` matches the run chain head. |
| `tests/unit/rag/test_writeback_two_worker_race.py` | NEW — multiprocessing race; `solved_example.race_observed` audit event. |
| `tests/unit/rag/test_writeback_body_canonical_form.py` | NEW — canonical serialisation; shuffled-input property test. |
| `tests/unit/rag/test_writeback_extra_forbid.py` | NEW — Pydantic `extra="forbid"` on `SolvedExample` + `Provenance`. |

## Out of scope
- **Strict-guard refusal matrix** — handled by S6-02. This story assumes the guard has cleared and writes the happy path.
- **Orchestrator branch promotion** — handled by S6-03; the Step-1 stub stays a stub until then. This story ships the callable; nobody calls it yet outside tests.
- **`solved-examples calibrate|list|show` CLI** — handled by S6-04.
- **`SolvedExamplePromoter.promote`** — Phase 11 owns the real promoter; the writer only writes `merge_status="pending_human"` (ADR-P4-002).
- **`--no-rag` / `--no-llm` writeback semantics** — handled by S6-03 (Gap 4).
- **Negative-example writeback** — explicitly forbidden in Phase 4 (G4); a failed-validation `rag_llm` run does NOT call this function. Enforcement test lives in S6-02.

## Notes for the implementer
- The **body-first invariant** is the single load-bearing ordering rule in this story. A reviewer who sees `add_or_update(...)` before `os.replace(...)` should reject the PR. The test `test_writeback_body_first_ordering` is the durable enforcement.
- The **`query_key_cache.put` synchronous** discipline closes critic §P.1 — a previous design attempt scheduled this on a background task. Do not reintroduce it. The cost is a few milliseconds; the value is "the second run on the same fingerprint provably hits tier-1 with no race window" — the very claim Phase 4's exit criterion makes.
- The **partial-failure orphan body** is intentional, not a bug. The `prune --orphans` recovery path is the operator-facing repair tool (S4-07); the writeback function's responsibility is "fail loud, leave evidence, do not corrupt the qk-cache."
- `solved_example.race_observed` audits **only** the second-arriving worker (the first writer succeeds normally). Detection: the second writer sees `os.replace` overwrite an existing path with identical bytes (body) AND chromadb reports a `row_already_exists` on `add_or_update` — both signals must coincide before the audit fires (no false positives on first writes).
- The function returns the assembled `SolvedExample` **even on partial failure** — the orchestrator needs the object to write the run report. The returned object's `provenance.merge_status` is still `"pending_human"`; the absence of the chromadb row is the only divergence.
- Do **not** lift fields out of `RepoContext` into the body beyond what `SolvedExample` schema names (ADR-P4-011 exfil boundary). If a future engineer wants to "enrich" the body with extra context, write an ADR first; the schema's `extra="forbid"` will reject silently-added fields.
- The Phase 11 `SolvedExamplePromoter.promote(reason="human_merge")` API is **not** shipped here — only the `merge_status="pending_human"` writeback. The promoter signature is fixed in arch §8 and Phase 11 fills the body. Do not pre-bake any promoter logic.
- Coverage floor 95/90 on `src/codegenie/rag/writeback.py` (per `stories/README.md §"Per-module coverage"`). This means every branch (success, body-write-fail, chroma-fail-first-attempt-then-success, chroma-fail-both-attempts, race) needs a test. The eight test files above cover this; the PR body must include the coverage number.
