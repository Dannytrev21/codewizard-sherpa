# Story S4-08 — Burst-harvest contention integration test (two coroutines under `asyncio.gather`; monotonic chain head; pinned-timeout failure mode)

**Step:** Step 4 — Ship RAG substrate kernel: Embedder + SolvedExampleStore + record provenance
**Status:** Ready
**Effort:** M
**Depends on:** S4-03 (single-writer `asyncio.Lock` + 30s `StoreWriteContention` contract), S4-04 (manifest with monotonic chain_head; canonical YAML write ordering)
**ADRs honored:** ADR-0016 (single-writer constraint enforced; concurrent ingest serializes), Gap 3 (contention contract pinned for Phase 11 pgvector conformance)

## Context

ADR-0016 + Gap 3 (arch §1106) name the load-bearing contention contract: under concurrent harvest (two workflows finishing validation near-simultaneously), `SolvedExampleStore.add` serializes via the process-local `asyncio.Lock`; **both records land deterministically** (sorted by add-arrival under the lock); the manifest's `chain_head` advances **monotonically** without collision. A 30 s timeout converts unbounded contention into a typed `StoreWriteContention(workflow_id)` raise.

Gap 3 §"Improvement" (arch §1106): *"`tests/integration/test_phase4_harvest_contention.py` spawns two harvest coroutines on the same store within `asyncio.gather` and asserts both succeed (sequenced) and chain-head advances monotonically. **The test pins the behavior** so Phase 11's pgvector swap has a clear conformance bar."*

S4-03 lands the *short* contention test (one timed-out add); S4-04 lands the chain-head monotonicity property. **This story is the load-bearing integration test** that composes both: two real-shape harvest coroutines under `asyncio.gather`, real chromadb, real YAML+manifest write, asserting:

1. Both coroutines return successfully (no exceptions; no `StoreWriteContention` in the happy path).
2. The resulting `manifest.chain_head` is **one of two valid orderings** (ex-A-first or ex-B-first); both records appear.
3. `store.digest()` equals `manifest.chain_head` (S4-04 AC-5 holds under contention).
4. A deliberate-timeout variant (one coroutine artificially holds the lock past the timeout) raises `StoreWriteContention` from the second coroutine — pinning the Phase-11 conformance bar.

The test runs under the real `asyncio.gather` (not mocks); chromadb's actual single-writer behavior is exercised. **The `asyncio.to_thread`-wrapped `chromadb.add` is the production path** — this test catches a regression where someone unwraps the to_thread (re-introducing event-loop blocking that would mask the contention).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Concurrency"` (line 269) — single-async-event-loop per workflow; `asyncio.Lock` guards `add`.
  - `../phase-arch-design.md §Edge case #5` — chromadb writer contention: `asyncio.Lock` serializes; both records land deterministically (sorted by `created_at`).
  - `../phase-arch-design.md §"Gap 3"` (line 1106) — the load-bearing improvement; this test is the **pinned conformance bar** Phase 11 pgvector must meet.
  - `../phase-arch-design.md §"Integration with Phase 11"` (line 1048) — pgvector adapter swap; merge-webhook ingest; portfolio-scale concurrent writes; the Protocol contract Phase 4 pins.
- **Phase ADRs:**
  - `../ADRs/0016-chromadb-embedded-yaml-canonical-store.md` §Decision — single-writer; `asyncio.Lock` around `add()`.
  - `../ADRs/0016-chromadb-embedded-yaml-canonical-store.md` §Consequences — "single-writer constraint is *declared* in Protocol + *enforced* by `asyncio.Lock` — the limit is visible, not a hidden race."
- **Source design:**
  - `../final-design.md §Component 7` — "Phase 11's concurrent-merge-webhook trigger is when the Protocol's adapter swaps to pgvector (ADR-0017 deferral resolution). The Phase 11 swap is one adapter, not a refactor."
- **Existing code (precedent to mirror):**
  - `tests/integration/test_phase4_store_contention_30s.py` (S4-03 ships) — the *short* contention test pinning the 30s timeout in isolation.
  - `tests/unit/rag/test_chain_head_monotonic.py` (S4-04 ships) — sequential chain-head monotonicity.
  - Phase-2 integration tests under `tests/integration/` — concurrency-touching test idioms (`asyncio.gather`, `freezegun`, `monkeypatch`).

## Goal

Ship `tests/integration/test_phase4_harvest_contention.py` that drives two harvest coroutines through `asyncio.gather` against a real `ChromaPersistentStore`, asserts both succeed with monotonically-advancing `manifest.chain_head` and digest equality, and a deliberate-timeout fixture variant raises `StoreWriteContention(workflow_id)` — pinning the Gap 3 conformance bar for the Phase-11 pgvector swap.

## Acceptance criteria

- [ ] **AC-1 — Two-coroutine happy path under `asyncio.gather`.** Test `test_two_harvests_under_gather_both_succeed_sequenced`:
    - Constructs a fresh `ChromaPersistentStore(root_dir=tmp_path)`.
    - Two `SolvedExampleWriteCapability` instances with distinct `workflow_id`s (`wf-A`, `wf-B`).
    - Two coroutines: `coro_a = store.add(make_solved_example(id_="ex-A"), cap_a)`; `coro_b = store.add(make_solved_example(id_="ex-B"), cap_b)`.
    - `results = await asyncio.gather(coro_a, coro_b)` — assert no exception; `results == (SolvedExampleId("ex-A"), SolvedExampleId("ex-B"))` (or the reverse if scheduling flips; assert set-equality of the result set).
    - Final state: `len(store._record_ids) == 2`; both IDs present.
- [ ] **AC-2 — `manifest.chain_head` advances monotonically across the gather.** Same test extends:
    - After both adds complete, read `manifest.yaml`; the chain_head is **one of two valid heads** — `head_ab = BLAKE3(yaml_a_bytes + yaml_b_bytes)` or `head_ba = BLAKE3(yaml_b_bytes + yaml_a_bytes)` (depending on lock-acquisition order).
    - The chain_head **is not** `BLAKE3(b"")` (empty) AND **is not** `BLAKE3(yaml_a_bytes)` alone (one record only); both records contributed.
    - Assert `manifest.chain_head in {head_ab, head_ba}` (order non-deterministic; **content is**).
- [ ] **AC-3 — `store.digest() == manifest.chain_head` after gather.** S4-04 AC-5's byte-identity contract holds under the gather workload. Catches a "race where digest is computed mid-update" mutant; the lock ensures digest is computed only after manifest write completes.
- [ ] **AC-4 — `_record_ids` order matches manifest.records.** `store._record_ids == manifest.records` exactly (same order). Catches a "record_ids appended but manifest written from a different order" mutant.
- [ ] **AC-5 — Deliberate-timeout fixture raises `StoreWriteContention`.** Test `test_harvest_contention_timeout_raises_typed_exception`:
    - Two coroutines, but `coro_a` is wrapped to **hold the lock for >30s** (in the test, the timeout constant is `monkeypatch`ed to `0.1s` for fast tests; `coro_a` is an async function that acquires the lock and sleeps `0.5s` before releasing — exceeding the 0.1s timeout for `coro_b`).
    - `await asyncio.gather(coro_a, coro_b, return_exceptions=True)`.
    - `coro_a`'s result: success.
    - `coro_b`'s result: `StoreWriteContention` instance with `workflow_id == cap_b.workflow_id`.
    - **After both coroutines complete, the lock is released** (no leak); a subsequent third `await store.add(...)` succeeds.
- [ ] **AC-6 — `coro_b`'s YAML record is NOT on disk.** When `coro_b` times out:
    - **Order matters.** S4-04's `add()` writes YAML *first*, then chromadb, then manifest. If `coro_b` times out **before** acquiring the lock, the YAML write never started — record `ex-B` has no canonical YAML.
    - Test asserts `(tmp_path / "records" / "ex-B.yaml")` does **not** exist after the timeout.
    - This is the load-bearing posture: a timed-out harvest leaves NO orphan canonical file (because the YAML write is inside the lock-acquired critical section). Surface in Notes §3 — this is a slight refinement of S4-04 AC-4 (which was about chromadb-failure-after-YAML-write).
- [ ] **AC-7 — `SolvedExampleIngestFailed(reason=write_contention)` event semantics.** This story does **not** wire the event emission (S6-03 does); the test asserts the *raise* shape. Document the expected event payload in the test docstring so S6-03's executor implements it correctly:
    ```
    Expected emission (S6-03 responsibility):
      event = SolvedExampleIngestFailed(
          reason="write_contention",
          workflow_id=cap_b.workflow_id,
      )
    ```
- [ ] **AC-8 — `freezegun` deterministic `created_at`.** Both AC-1 and AC-5 tests fix `datetime.now(timezone.utc)` via `freezegun.freeze_time("2026-05-18T12:00:00Z")` (or the fixture from S4-04). Otherwise the canonical YAML bytes differ between runs (and between coroutines mid-flight), and AC-2's chain-head assertion is non-deterministic.
- [ ] **AC-9 — `asyncio.to_thread` boundary preserved.** A small assertion: monkeypatch `asyncio.to_thread` to count invocations; after two adds, `to_thread.call_count == 2` (one per chromadb add). If a future refactor removes the `to_thread` wrapping (regression), this assertion catches it before the contention semantics silently change.
- [ ] **AC-10 — Test is marked `@pytest.mark.integration` and runs in CI.** The test is **not** an adversarial test — it pins production behavior; runs in the default lane (`make test`). Tagging matches Phase 2's integration test conventions.
- [ ] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean.

## Implementation outline

1. **Test file:** `tests/integration/test_phase4_harvest_contention.py`.
2. **Fixtures:**
   - `frozen_time` fixture (autouse for the module) via `freezegun.freeze_time("2026-05-18T12:00:00Z")`. Both happy-path and timeout tests share it.
   - `tmp_root` (per-test): `tmp_path / "rag"`.
   - `store` (per-test): `ChromaPersistentStore(root_dir=tmp_root)`; teardown `store.close()`.
   - `cap_factory(workflow_id_str)` helper that builds `SolvedExampleWriteCapability(workflow_id=WorkflowId(workflow_id_str))`.
3. **Happy-path test (AC-1 to AC-4):**
   ```python
   @pytest.mark.integration
   @pytest.mark.asyncio
   async def test_two_harvests_under_gather_both_succeed_sequenced(
       store: ChromaPersistentStore,
       tmp_root: Path,
   ) -> None:
       cap_a = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-A"))
       cap_b = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-B"))
       ex_a = make_solved_example(id_="ex-A", cve_id="CVE-2026-AAAA")
       ex_b = make_solved_example(id_="ex-B", cve_id="CVE-2026-BBBB")

       results = await asyncio.gather(store.add(ex_a, cap_a), store.add(ex_b, cap_b))

       assert set(results) == {SolvedExampleId("ex-A"), SolvedExampleId("ex-B")}
       manifest = yaml.safe_load((tmp_root / "manifest.yaml").read_text("utf-8"))
       assert set(manifest["records"]) == {"ex-A", "ex-B"}
       assert manifest["chain_head"] == store.digest()  # AC-3
       assert store._record_ids == [SolvedExampleId(x) for x in manifest["records"]]  # AC-4
       # AC-2: chain head is one of two valid orderings
       head_ab = _expected_head(tmp_root, ["ex-A", "ex-B"])
       head_ba = _expected_head(tmp_root, ["ex-B", "ex-A"])
       assert manifest["chain_head"] in {head_ab, head_ba}
   ```
   `_expected_head(root, order)` is a test helper that reads the canonical YAML bytes in the given order and rolls BLAKE3.
4. **Timeout test (AC-5 to AC-7):**
   ```python
   @pytest.mark.integration
   @pytest.mark.asyncio
   async def test_harvest_contention_timeout_raises_typed_exception(
       store: ChromaPersistentStore,
       tmp_root: Path,
       monkeypatch: pytest.MonkeyPatch,
   ) -> None:
       monkeypatch.setattr("codegenie.rag.store._ADD_LOCK_TIMEOUT_SECONDS", 0.1)
       cap_a = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-A"))
       cap_b = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-B"))
       ex_a = make_solved_example(id_="ex-A")
       ex_b = make_solved_example(id_="ex-B")

       async def slow_add_a() -> SolvedExampleId:
           # Hijack the lock past the timeout window.
           await store._add_lock.acquire()
           try:
               await asyncio.sleep(0.5)  # well past 0.1s timeout
               # We deliberately do NOT call store.add(...) inside — just hold the lock.
               return SolvedExampleId("ex-A-skipped")
           finally:
               store._add_lock.release()

       results = await asyncio.gather(slow_add_a(), store.add(ex_b, cap_b), return_exceptions=True)
       assert results[0] == SolvedExampleId("ex-A-skipped")
       assert isinstance(results[1], StoreWriteContention)
       assert results[1].workflow_id == WorkflowId("wf-B")

       # AC-6: no orphan YAML for ex-B
       assert not (tmp_root / "records" / "ex-B.yaml").exists()
       # Subsequent add succeeds — lock not leaked
       cap_c = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-C"))
       sid_c = await store.add(make_solved_example(id_="ex-C"), cap_c)
       assert sid_c == SolvedExampleId("ex-C")
   ```
5. **`asyncio.to_thread` instrumentation (AC-9):** small test that monkeypatches the symbol with a `Mock(wraps=asyncio.to_thread)` and asserts call count. Run it as a separate test in the same module so it doesn't pollute the contention tests.

## TDD plan — red / green / refactor

### Red — write the failing test first

The happy-path test (`test_two_harvests_under_gather_both_succeed_sequenced` above) is the red test. It fails today because:
- S4-03 ships only the short contention test; the full `asyncio.gather` shape isn't exercised.
- AC-3's `digest == chain_head` may pass trivially if S4-04 landed correctly, but AC-4's `_record_ids == manifest.records` ordering invariant catches a class of race-condition mutants.

Why it fails on a wrong impl: if `asyncio.to_thread` is removed (regression) and chromadb's sync `add` blocks the event loop, the second coroutine's `await store.add(...)` may complete its lock-acquire but its **YAML write** (which precedes the chromadb call inside the lock per S4-04) could interleave with the first coroutine's manifest write if the lock granularity is wrong. The test's AC-4 `_record_ids` order vs `manifest.records` order assertion catches this.

### Green — make it pass

If S4-03 + S4-04 are implemented correctly, this test passes immediately on first run. If not, the failure points to:
- Wrong lock granularity (lock around chromadb call only, not around the whole YAML+chromadb+manifest sequence) → AC-4 fails.
- Missing `await store._record_ids.append(...)` order vs manifest-write order → AC-4 fails.
- `digest()` rolls over IDs not YAML bytes → AC-3 fails.

Each diagnostic points at a specific S4-03/S4-04 AC.

### Refactor

- Hoist `_expected_head(root, order)` into a test-helper module if reused.
- Module docstring on the test file: cite Gap 3 + Phase-11 conformance bar framing.

### Required follow-on tests

- `test_to_thread_invoked_per_add` (AC-9).
- Optional: `test_three_harvests_under_gather_chain_head_one_of_six_orderings` — extend to N=3 to catch a class of "lock fairness" mutations. Cheap and informative.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_phase4_harvest_contention.py` | The load-bearing burst-contention test pinning Gap 3 for Phase 11. |
| `tests/integration/conftest.py` | Optional: shared `frozen_time` fixture if not already present. |

## Out of scope

- **Three+ concurrent harvest coroutines** — adding N=3, N=10 is incremental; the contention contract is binary (one writer at a time). Two coroutines is the minimum that exercises the lock; more is bench-territory (Phase 6.5 owns).
- **Cross-process concurrency** — Phase 11 pgvector adapter is the resolution; not Phase 4's case.
- **Performance benchmarks** — `tests/bench/` is where p99 latency lives; this test pins correctness, not perf.
- **Real network / portfolio-scale simulation** — Phase 11.
- **Emission of `SolvedExampleIngestFailed` event** — S6-03 (the test documents the contract in its docstring; AC-7).
- **Lock-fairness guarantees** — `asyncio.Lock` is not strictly FIFO across Python versions; the test asserts "both succeed" and "chain head is one of two valid orders" — does **not** assert which one wins. Lock fairness is not a Phase-4 commitment.

## Notes for the implementer

### §1 — Why this is a Phase-11 conformance bar, not just a Phase-4 test

Gap 3 names this test as "pinning the behavior so Phase 11's pgvector swap has a clear conformance bar." That framing matters: the **pgvector adapter** (Phase 11) will replace `ChromaPersistentStore` behind the same `SolvedExampleStore` Protocol. Phase 11 has multi-writer capability natively — so the question "does it still serialize?" is not auto-answered. Phase 11's adapter must either **also serialize** (matching this test's contract) or **explicitly document** that the conformance bar has changed (ADR amendment). Without this test, Phase 11 could silently parallelize and break a load-bearing Phase-4 invariant (e.g., chain-head monotonicity assumes serialized writes).

### §2 — `_ADD_LOCK_TIMEOUT_SECONDS` monkeypatch is brittle

The timeout constant must be patchable at test-time. S4-03's implementation should expose it as `_ADD_LOCK_TIMEOUT_SECONDS: Final[float] = 30.0` at module level. If S4-03's executor used a hardcoded literal (`timeout=30.0` inline), this test will fail because the monkeypatch has no target. Surface per Rule 7 if discovered; the fix is moving the literal into a module constant (which S4-03's AC-8 contention test also benefits from).

### §3 — YAML write inside the lock means timed-out harvest has no orphan

S4-04 AC-4 covered the chromadb-failure-after-YAML-write case (YAML on disk, manifest unchanged). This story's AC-6 covers the **lock-timeout case**: the lock is acquired **before** the YAML write begins. So a timed-out harvest never wrote any canonical bytes — clean. The two cases together:

- Lock acquired → YAML written → chromadb fails → manifest unchanged → YAML orphan (S4-04 AC-4).
- Lock acquire timeout → no YAML written → no orphan (this story AC-6).

Document both in S4-04's module docstring if not already covered. The orphan case (S4-04) is recovered by `codegenie rag rebuild` (S4-07); the no-orphan case (this story) needs no recovery.

### §4 — Don't add a `@pytest.mark.flaky` retry

The test's outcome is **deterministic** given `freezegun` + a deterministic `asyncio.Lock`. The only non-determinism is lock-acquisition order (AC-2 asserts the chain head is one of two valid heads); no retry is needed. If the test ever flakes, the right response is to diagnose the race, not retry-mask it. Flaky-marker is `# noqa: do not add — see Notes §4`.

### §5 — The `slow_add_a` coroutine doesn't call `store.add`

It manually acquires/holds/releases `store._add_lock` to simulate "writer A is taking forever." If you tried to call `store.add(...)` from `coro_a` and have it sleep mid-call, you'd be testing chromadb's behavior, not the lock contract. The hand-rolled coroutine is the right test posture — touches *only* the lock state we're pinning.

### §6 — `make_solved_example` deterministic-vector concerns

If `make_solved_example` (S4-03's fixture) generates a random embedding vector per call, two calls with `id_="ex-A"` produce different canonical YAML bytes → AC-2's expected-head computation breaks. **Pin the fixture to deterministic vectors** keyed on `id_` (e.g., `np.full(384, hash(id_) % 7 / 7.0, dtype=np.float32)`). This story's tests will catch the issue if it's not done; the fix lives in `tests/fixtures/rag/fake_solved_example.py`.

### §7 — Real chromadb in the test

The test uses a real `ChromaPersistentStore` against `tmp_path / "rag/"` — actual chromadb sqlite created and destroyed per test. This is slow (~50–200 ms per test); acceptable for two integration tests. Do **not** mock chromadb here; the entire point is to exercise the real lock + real `asyncio.to_thread` + real chromadb sync `add`. If a future refactor introduces a mocked `chromadb.PersistentClient`, this test's value disappears and the Phase-11 conformance bar weakens.

### §8 — Optional N=3 follow-on test

A `test_three_harvests_under_gather_chain_head_one_of_six_orderings` extends the same shape: three records, six valid head orderings (`3! = 6`). Useful if you want to catch a class of "ID-set-equality but ordering-bug" mutations. Cheap (one extra test ~ 100 ms); add it if the executor has the budget — otherwise N=2 is sufficient to pin Gap 3.
