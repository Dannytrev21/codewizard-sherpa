# Story S7-04 — Add the Redis-tamper fail-closed adversarial tests

**Step:** Step 7 — Close the exit criteria: latency, decision-log completeness, and adversarial gates
**Status:** Ready
**Effort:** M
**Depends on:** S5-02
**ADRs honored:** ADR-0003, ADR-0006

## Context
ADR-0003 makes Redis untrusted on read: a writable-Redis compromise must be a latency cost, never a context-poisoning cost. This story is the adversarial proof of that property. It writes attacker-controlled values into Redis — a wrong `gather_id` and attacker-chosen bytes for the `risk_flags` slice — and asserts the planner discards them, falls through to cold storage, emits the mismatch signal, and ends with planner context byte-identical to the no-tamper run. These are the Redis-tamper cases ADR-0003 §Consequences names as required; they lock the G5 security property ("Redis is untrusted on read").

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Testing strategy / Adversarial tests` — "**Redis-tamper / fail-closed** — write a value with a wrong `gather_id`; assert the planner discards it, falls through to cold storage, returns the correct value, emits the mismatch signal. A second test feeds attacker-controlled bytes for `risk_flags` and asserts the planner context is byte-identical to the no-tamper run."
  - `../phase-arch-design.md §Scenario 2` — the stale/tampered fail-closed-to-cold-storage sequence; `HotViewIntegrityMiss` signal emitted, logged.
  - `../phase-arch-design.md §Edge cases` — edge case 5 ("Redis returns a tampered or stale value") and edge case 4 ("Redis unreachable").
  - `../phase-arch-design.md §G5` — "A writable-Redis compromise is a latency cost, never a context-poisoning cost."
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-hot-view-integrity-by-gather-id-content-addressing.md` — ADR-0003 §Consequences — "Adversarial tests must cover: a wrong-`gather_id` value (discarded → cold read), and attacker-controlled bytes for `risk_flags` (planner context byte-identical to the no-tamper run)." Also: an integrity miss is logged via a `_WARNING_IDS`-registered ID — never silent.
  - `../ADRs/0006-cold-storage-fallback-reads-the-rendered-repocontext.md` — ADR-0006 — the cold reader returns the correct value the tampered Redis value was meant to be.
- **Existing code (if any):**
  - `src/codegenie/hotviews/store.py` — `HotViewStore.get` / `get_all` — the `(repo, slice, gather_id, slice_schema_version)` binding verification and the `ColdStoreReader` fallback (shipped S5-02).
  - `src/codegenie/hotviews/` — the package's `_WARNING_IDS` frozenset (shipped S3-05) — the integrity-miss signal ID must be a member.
  - `tests/golden/hotviews/` — a clean gathered `RepoContext` to use as the no-tamper baseline.

## Goal
Add adversarial tests proving a wrong-`gather_id` Redis value and attacker-controlled `risk_flags` bytes are both discarded in favor of cold storage, with the mismatch logged and planner context byte-identical to the no-tamper run.

## Acceptance criteria
- [ ] An adversarial test writes a `risk_flags` Redis value carrying a **wrong `gather_id`** (one that does not match the gather the planner is working against) and asserts `HotViewStore.get` / `get_all` discards it and returns the cold-storage value.
- [ ] That test asserts an integrity-miss signal is emitted — a `structlog` event or an event-log signal — carrying a `_WARNING_IDS`-registered ID (the miss is never silent, Rule 12 / ADR-0003).
- [ ] A second adversarial test writes **attacker-controlled bytes** as the `risk_flags` payload (e.g. forged risk flags that would change the routing decision) and asserts the resulting planner context is **byte-identical** to the context produced by an untampered run of the same gather.
- [ ] A third case writes a value with a mismatched `slice_schema_version` and asserts only that slice cold-reads while the other three are served warm (per-slice fail-closed, edge case 6 / 08-ADR-0003).
- [ ] The byte-identity comparison is over the serialized planner context, not a field spot-check.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Set up a real (or fake) Redis plus a `ColdStoreReader` over a clean golden `RepoContext`; render and write the four valid slices.
2. Capture the **no-tamper baseline**: read planner context via `get_all` on the honest store; serialize it.
3. Wrong-`gather_id` test: overwrite the `risk_flags` key with a `HotViewSlice` whose `gather_id` is wrong; assert `get_all` returns the cold value for `risk_flags`, the warm values for the other three, and that the integrity-miss signal fired with a registered ID.
4. Attacker-bytes test: overwrite `risk_flags` with a forged payload; assert the serialized planner context equals the baseline byte-for-byte.
5. Schema-version test: overwrite one slice's value with a mismatched `slice_schema_version`; assert per-slice fail-closed (that slice cold, others warm).
6. Capture the emitted signals via an `InMemorySink` `EventLog` and/or a `structlog` capture fixture.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/adv/phase08/test_redis_tamper.py`

```python
async def test_wrong_gather_id_value_is_discarded_for_cold_read(
    redis_store, cold_reader, golden_repo
) -> None:
    # WHY: ADR-0003 / G5 — a writable-Redis compromise must be a latency cost,
    # never a context-poisoning cost. A wrong-gather_id value must fail the
    # binding check and fall closed to cold storage, with the miss logged.
    tampered = HotViewSlice(slice_name="risk_flags", gather_id=WRONG_ID, ...)
    await redis_store.redis.set(key_for("risk_flags"), tampered.model_dump_json())

    result = await redis_store.get_all(golden_repo.repo_id)

    assert result["risk_flags"] == cold_reader_expected_risk_flags
    assert any(s.warning_id == "hotview.integrity_miss" for s in captured_signals)


async def test_attacker_risk_flags_bytes_yield_baseline_context(
    redis_store, golden_repo
) -> None:
    # WHY: attacker-chosen risk_flags must not reach the planner — the served
    # context must be byte-identical to an untampered run of the same gather.
    baseline = serialize(await honest_store.get_all(golden_repo.repo_id))
    await redis_store.redis.set(key_for("risk_flags"), FORGED_RISK_FLAGS_BYTES)
    tampered_run = serialize(await redis_store.get_all(golden_repo.repo_id))
    assert tampered_run == baseline
```

### Green — make it pass
No new production code — S5-02 already ships the binding verification and the cold fallback. "Green" is the adversarial tests passing. A failure means the integrity check has a hole (a tampered value reaching the planner) — fix `HotViewStore`, never weaken the test.

### Refactor — clean up
Module docstring naming ADR-0003 / G5; type hints on the tamper helpers; a `key_for(slice_name)` helper so the raw Redis key is constructed once. Honor §Harness engineering — the integrity-miss signal must carry a `_WARNING_IDS`-registered ID; assert that, not just that *some* log line appeared.

## Files to touch
| Path | Why |
|---|---|
| `tests/adv/phase08/test_redis_tamper.py` | The Redis-tamper fail-closed adversarial tests (new file). |
| `tests/adv/phase08/__init__.py` | Package marker for the Phase-8 adversarial corpus, if absent. |
| `tests/adv/phase08/conftest.py` | Redis + cold-reader + signal-capture fixtures, if not reusable. |

## Out of scope
- The honest-input warm/cold-equivalence property test — that is S7-03 (this story is the *adversarial* counterpart: equivalence must survive tampering).
- The decision-log completeness adversarial test — S7-05.
- Any cryptographic tamper-evidence (HMAC / KMS) — explicitly deferred to Phase 9 by ADR-0003; a reader-plus-artifact attacker is out of scope.
- The Skills-ID traversal adversarial test — that rides Step 8 (S8-03).

## Notes for the implementer
- ADR-0003 defends a Redis *writer* (a latency attacker), not a Redis *reader-with-the-artifact* (deferred to Phase 9). Do not over-scope — the threat model is a tampered/stale *value*, not a forged matching `gather_id`.
- The byte-identity assertion is the load-bearing one. Compare serialized planner context; a field spot-check could miss a forged nested value (Rule 9).
- Assert the integrity miss carries a **registered** warning ID — a silent fallback would still pass a naive "did cold storage win?" check but violates Rule 12 and ADR-0003 §Consequences.
- Use per-slice tampering for the schema-version case — 08-ADR-0003's whole point is that one slice's drift does not cold-evict the other three; the test must prove that isolation.
- Place the tests under `tests/adv/phase08/` to mirror the `tests/adv/phase02/` precedent (`phase02_adv` marker); confirm whether a `phase08_adv` marker is wanted or the tests run under the default suite — match the closest existing convention.

## ADRs honored
- **ADR-0003** — implements the §Consequences-required wrong-`gather_id` and attacker-`risk_flags` adversarial cases; proves fail-closed.
- **ADR-0006** — the cold reader supplies the correct value the tampered Redis value was meant to be.
