# Story S9-02 — Serial checkpoint throughput watchdog + ADR-P6-006

**Step:** Step 9 — Performance canary (G6) + SQLite throughput watchdog (G9) + ADR-P6-006 escalation hook
**Status:** Ready
**Effort:** S
**Depends on:** S2-04
**ADRs honored:** ADR-0006, ADR-0011 — and **ships** ADR-P6-006 as a new file

## Context
Phase 6's exit criterion ("Mid-run kill + resume works without state loss") forces fsync-per-node-boundary durability (ADR-0006). That choice trades throughput for correctness — the open question is *how much*. The synthesizer refused to defer this measurement to Phase 9 (`final-design.md §Synthesis ledger §Shared blind spots #1`): all three lens designs assumed SQLite would be adequate without measuring. This story closes the gap by shipping the **single-workflow throughput watchdog**: 1,000 serial `AuditedSqliteSaver.put()` calls must complete at ≥ 100 writes/s on CI hardware. Below that threshold, the durability discipline is unviable for Phase 9's projected workload, and the test fails with a printed escalation message; *concurrently*, this story commits ADR-P6-006 as a Nygard-format file enumerating the numeric thresholds and the procedure to pull Phase 9's Postgres migration forward. The ADR text and the test land in the same PR — that is the load-bearing contract of this story.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Goals — G9` (lines 28–29) — the 100 writes/s threshold.
  - `../phase-arch-design.md §Performance regression tests` (line 1211) — names the file, declares the threshold, ties failure to ADR-P6-006.
  - `../phase-arch-design.md §Tradeoffs table` row 10 (line 1140) — "SQLite throughput < 100 writes/s on CI hardware → ADR-P6-006 triggered → block merge."
  - `../phase-arch-design.md §Performance envelope` (line 698) — target ≥ 100 writes/s sustained.
- **Phase ADRs:**
  - `../ADRs/0011-sqlite-throughput-watch-and-postgres-escalation.md` — **the** policy ADR. ADR-P6-006 (this story's deliverable) is the *amendment* ADR that fires when ADR-0011's threshold is breached; the two are paired.
  - `../ADRs/0006-audited-sqlite-saver-per-workflow-fsync.md` — the durability discipline being measured. The throughput cost in this ADR's tradeoffs table is what the watchdog quantifies.
  - `../ADRs/README.md` — Nygard format and the existing ADR index; ADR-P6-006 must register there.
- **Source design:** `../final-design.md §Synthesis ledger row 9` (the policy commitment); `§Goals row 9`; `§Risk 3` (the escalation procedure outline).
- **High-level-impl:** `../High-level-impl.md §Step 9` — features delivered include "ADR-P6-006 lands as a tripwire — text only at first; if throughput threshold fails on CI hardware post-merge, the ADR's 'consequences' block triggers Phase 9 Postgres pull-forward."
- **Existing code:**
  - `src/codegenie/graph/checkpointer.py` — `AuditedSqliteSaver` + `make_checkpointer`; the test invokes these via the public factory.
  - `src/codegenie/graph/state.py` — `VulnLedger` is the payload; build a small but realistic one (not an empty stub).
  - `tests/perf/baseline.json` schema established by S9-01 — this story adds a sibling `"checkpoint_throughput"` key.

## Goal
Ship `tests/perf/test_checkpoint_throughput.py` such that 1,000 serial `AuditedSqliteSaver.put()` calls complete at ≥ 100 writes/s on CI hardware; on failure the test fails with an explicit `"ADR-P6-006 escalation: Postgres pull-forward triggered"` message. **Concurrently** commit `docs/phases/06-sherpa-state-machine/ADRs/P6-006-sqlite-throughput-insufficient.md` in Nygard format with the numeric thresholds and the explicit Phase-9 pull-forward procedure.

## Acceptance criteria
- [ ] `tests/perf/test_checkpoint_throughput.py` exists. It uses `make_checkpointer(workflow_id, base=tmp_path)` to construct one real `AuditedSqliteSaver` (per-workflow file, WAL=on, synchronous=NORMAL, mode 0600 — the production configuration) and issues exactly **1,000** serial `put()` calls each persisting a representative `VulnLedger` checkpoint.
- [ ] Each `put()` writes a *distinct* checkpoint — increment a counter field on `VulnLedger` (e.g., `attempt_index`) so the test does not measure a no-op same-bytes write that SQLite WAL could short-circuit; the same-bytes case is the wrong workload to measure.
- [ ] Wall-clock measurement uses `time.perf_counter_ns()` around the whole 1,000-call loop; achieved throughput is `1000 / (elapsed_ns / 1e9)` writes/s.
- [ ] The test asserts `achieved_writes_per_second >= 100.0`. On failure, the assertion message contains the literal string `"ADR-P6-006 escalation: Postgres pull-forward triggered"`, the measured throughput rounded to 2 decimal places, the elapsed wall-clock seconds, and the workflow_id used.
- [ ] On success, the test appends `{"checkpoint_throughput": {"writes_per_second": <float>, "elapsed_s": <float>, "iterations": 1000, "recorded_at": "<ISO-8601-UTC>", "sqlite_version": "<resolved>"}}` to `tests/perf/baseline.json` (preserving the `canary_overhead` key from S9-01). This is record-only on success; **no** regression check on subsequent runs — the 100 writes/s floor is the *only* assertion.
- [ ] A 10-call warmup phase runs before the timed 1,000 (absorbs `aiosqlite` connection-pool init + first-WAL-frame cost).
- [ ] The test is marked `@pytest.mark.slow` and is run only by the merge-queue nightly cron (matches arch §CI gates row 4 and `High-level-impl.md §Step 9` done criterion).
- [ ] No file `os.fsync()` calls exist in the test code — durability is the production checkpointer's responsibility (ADR-0006); the test must not artificially boost throughput by disabling fsync nor artificially lower it by force-syncing.
- [ ] `docs/phases/06-sherpa-state-machine/ADRs/P6-006-sqlite-throughput-insufficient.md` is committed in this PR in Nygard format with **all** of the following sections: `Status` (initial value: `Conditional — fires only on CI failure`), `Date`, `Tags`, `Related` (linking to ADR-0006 and ADR-0011), `Context`, `Trigger condition` (the literal: "`tests/perf/test_checkpoint_throughput.py` reports `achieved_writes_per_second < 100.0` on the merge-queue nightly cron"), `Decision` (Phase 9 Postgres migration pulls forward to Phase 7 or Phase 8; merge of any work that depends on Phase 6 operational throughput is blocked until the new Postgres-target ADR amendment lands), `Numeric thresholds` (a table with `single_workflow_floor=100 writes/s`, `concurrent_aggregate_floor=10×single_baseline` — pointing to S9-03, `re-measurement cadence=nightly`), `Escalation procedure` (a numbered list: (1) CI fails with the canonical message; (2) on-call opens an ADR-amendment story citing this ADR by ID; (3) production ADR-0016 is amended to mark the deferral closed; (4) Phase 9's Postgres migration plan moves earlier in the roadmap; (5) Phase 6's `make_checkpointer` factory is the swap seam — no other graph source changes), `Tradeoffs`, `Consequences`, `Reversibility`, `Evidence / sources`.
- [ ] `docs/phases/06-sherpa-state-machine/ADRs/README.md` index is updated to include ADR-P6-006 with status `Conditional — fires only on CI failure`.
- [ ] A second test, `test_throughput_failure_message_format` (which is **not** `@pytest.mark.slow`), monkey-patches the elapsed-time computation to simulate < 100 writes/s and asserts the failure message contains the canonical escalation string — this catches a future refactor that quietly drops the ADR-P6-006 reference from the assertion.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/perf/test_checkpoint_throughput.py -m slow` all pass.

## Implementation outline
1. Read `src/codegenie/graph/checkpointer.py` to confirm the `make_checkpointer` factory signature and `AuditedSqliteSaver.put()` shape (the async path — the test must `await` or use `asyncio.run`).
2. Read `tests/perf/test_canary_overhead.py` (from S9-01) to match the `BASELINE_PATH` and ISO-8601-UTC `recorded_at` conventions, and to confirm the baseline-merge logic (read existing JSON, set the new key, write).
3. Write the ADR file `P6-006-sqlite-throughput-insufficient.md` **first** — the test's failure message must quote the ADR ID verbatim, so the ADR is the spec.
4. Create `tests/perf/test_checkpoint_throughput.py`:
   - Async test function decorated with `@pytest.mark.asyncio` and `@pytest.mark.slow`.
   - Build a small valid `VulnLedger` fixture (use the same builder S2-01 uses; do not roll a new one).
   - Open `make_checkpointer(workflow_id="perftest_serial", base=tmp_path)`.
   - 10 warmup `put()` calls (untimed).
   - Capture `start_ns = time.perf_counter_ns()`.
   - Loop 1,000 times: mutate a counter on the ledger via `model_copy(update={...})`, call `await checkpointer.put(config, ledger, metadata)` (or whatever the LangGraph signature is — read S2-01 / S2-02).
   - Capture `end_ns`. Compute `writes_per_second`.
   - Assert with the canonical message.
   - On pass, merge into `tests/perf/baseline.json`.
5. Write the meta-test `test_throughput_failure_message_format` — pure-Python, no real I/O; verifies the assertion-message format contract is honored.
6. Update `docs/phases/06-sherpa-state-machine/ADRs/README.md` with the new ADR row.
7. Confirm `mypy --strict` passes; the `aiosqlite` path may surface untyped seams — narrow with `cast` only where necessary and only with an explanatory comment.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/perf/test_checkpoint_throughput.py` (the `test_throughput_failure_message_format` meta-test is the red one — it asserts the literal escalation message before any production code references it).

```python
# tests/perf/test_checkpoint_throughput.py
import pytest

from tests.perf.test_checkpoint_throughput import _format_throughput_failure_message


def test_throughput_failure_message_format_contains_adr_p6_006() -> None:
    # arrange: simulate the failure-path message construction
    msg = _format_throughput_failure_message(
        achieved_wps=42.50,
        elapsed_s=23.5294,
        workflow_id="perftest_serial",
        iterations=1000,
    )
    # assert: every load-bearing element is present
    assert "ADR-P6-006 escalation: Postgres pull-forward triggered" in msg
    assert "42.50" in msg  # measured throughput
    assert "23.5294" in msg or "23.53" in msg  # elapsed
    assert "perftest_serial" in msg
    assert "1000" in msg
    assert "100" in msg  # the floor


def test_throughput_floor_is_one_hundred_writes_per_second() -> None:
    # arrange: import the constant directly — guards against silent retuning
    from tests.perf.test_checkpoint_throughput import THROUGHPUT_FLOOR_WRITES_PER_SECOND
    # assert: ADR-0011 commits to 100; any change must be deliberate (and the ADR amended)
    assert THROUGHPUT_FLOOR_WRITES_PER_SECOND == 100.0
```

These two tests fail until `_format_throughput_failure_message` and `THROUGHPUT_FLOOR_WRITES_PER_SECOND` exist with the contractual shape.

### Green — make it pass
1. Implement `THROUGHPUT_FLOOR_WRITES_PER_SECOND: float = 100.0` as a module-level constant.
2. Implement `_format_throughput_failure_message(achieved_wps, elapsed_s, workflow_id, iterations) -> str` returning a single-line string that contains the canonical escalation prefix, all four parameters, and the floor.
3. Implement the real `test_checkpoint_throughput_meets_floor` async body using the helpers above.

### Refactor — clean up
Pull the 1,000-iteration loop into a private `_measure_serial_throughput(checkpointer, *, iterations: int = 1000, warmup: int = 10) -> tuple[float, float]` returning `(writes_per_second, elapsed_s)` so S9-03 can reuse the same measurement helper for its concurrent case. Keep the floor constant and the message formatter private to the module (S9-03 owns its own constants). Ensure the ADR file is referenced by `# See: docs/phases/06-sherpa-state-machine/ADRs/P6-006-sqlite-throughput-insufficient.md` in the test module docstring.

## Files to touch
| Path | Why |
|---|---|
| `tests/perf/test_checkpoint_throughput.py` | The watchdog itself. |
| `docs/phases/06-sherpa-state-machine/ADRs/P6-006-sqlite-throughput-insufficient.md` | The Nygard-format escalation ADR. |
| `docs/phases/06-sherpa-state-machine/ADRs/README.md` | Index update (one row). |
| `tests/perf/README.md` (extend, not create — S9-01 created it) | Add a paragraph: "Throughput watchdog (S9-02 / ADR-P6-006) is a *hard floor*, not a baseline-regression check; the only escape is to commit an ADR amendment, not to refresh `baseline.json`." |

## Out of scope
- **Concurrent-workflow throughput** — S9-03 lands the Gap 3 addendum. This story measures serial only.
- **Editing ADR-0011** — ADR-0011 already commits to the 100 writes/s floor; S9-02 ships *ADR-P6-006* as a sibling, not an amendment to ADR-0011.
- **Editing production ADR-0016** — step (3) of the escalation procedure happens *only when the test fires*, not as part of this PR.
- **Per-node overhead canary** — S9-01.
- **CI workflow file edits** — the nightly-cron schedule is owned by Step 10's polish work.

## Notes for the implementer
- The 100 writes/s number is **load-bearing**, not a placeholder. It derives from ADR-0011's `Consequences` block: "one workflow doing ~10 node transitions over ~100 s = 0.1 writes/s per workflow, scaled to N=100 concurrent workflows = 10 writes/s, with 10× headroom for spikes = 100 writes/s." Do not retune without amending ADR-0011 and ADR-P6-006 together.
- The mutation per put-call matters. SQLite's WAL can collapse identical writes; if every iteration sends the same bytes, the measurement is fictitious. Increment a monotonic field; the cheapest is `attempt_index` or a synthetic `tick` field if `VulnLedger` permits. If `VulnLedger` doesn't have an unconstrained integer field, *don't* widen the schema — use the `prior_attempts` list and append; that's a real production write pattern.
- The escalation procedure in ADR-P6-006 must be *executable*, not aspirational. Step 5 ("Phase 6's `make_checkpointer` factory is the swap seam") is the operative line — that factory is the single import the migration touches. If during this story you discover the factory is *not* in fact the single seam (e.g., direct `AuditedSqliteSaver(...)` constructions exist elsewhere), surface that as a defect in the seam and reference it in the ADR's `Consequences`.
- The `tests/perf/baseline.json` write on **success** is a record, not a regression baseline. The throughput floor is the *only* gate. This is intentionally asymmetric to S9-01: S9-01 catches *regressions* via baseline comparison; S9-02 catches *unviability* via a hard floor.
- Async hygiene: `AuditedSqliteSaver` is an async subclass. Use `pytest-asyncio` (already a project dep — verify); avoid creating a fresh event loop per iteration. One loop, one checkpointer, 1,000 awaits.
- The `cast` cost on aiosqlite types is real for `mypy --strict`. Prefer `from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver` re-exports if they already have stubs; only widen with `cast` and an `# explanation:` comment when unavoidable.
- ADR-P6-006's `Status: Conditional — fires only on CI failure` is **intentional**. ADR-0011 is `Accepted` because it commits the policy; ADR-P6-006 is `Conditional` because it commits the *consequence* — the latter only activates on a threshold breach. Reviewers may push to mark ADR-P6-006 `Accepted` for symmetry; push back — the status is the difference between "we have a plan" (Accepted) and "we will execute the plan iff CI fires" (Conditional).
- Do not couple this test to S9-03's concurrent case. The two assertions are independent: serial can pass while concurrent fails (event-loop overhead, shared `chain_lock` contention) and vice versa. ADR-P6-006 captures both as separate trigger conditions; the test files stay separate too.
- The test must isolate its working directory to `tmp_path`. The production checkpointer writes under `.codegenie/loop/checkpoints/<workflow_id>.sqlite3`; the test must override `base=tmp_path` so it never leaks state into the repo's `.codegenie/` and never contends with another CI shard.
- If the test fails on a developer's local box but passes on CI (or vice versa), the *CI* hardware number is what governs. Local machines vary by an order of magnitude; the escalation procedure explicitly references "CI hardware."
