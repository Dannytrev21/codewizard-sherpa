# Story S4-08 — Burst-harvest contention integration test (two coroutines under `asyncio.gather`; monotonic chain head; pinned-timeout failure mode)

**Step:** Step 4 — Ship RAG substrate kernel: Embedder + SolvedExampleStore + record provenance
**Status:** Done — GREEN 2026-05-25 (phase-story-executor; see [`_attempts/S4-08.md`](_attempts/S4-08.md) for the per-AC evidence table + gate log — Phase-4 burst-harvest contention pin landed with three tests in `tests/integration/test_phase4_harvest_contention.py` (happy-path, deliberate-timeout, `to_thread`-boundary), the arch §Edge-case-#5 wording amended to insertion-order, and AC-7's verbatim `SolvedExampleIngestFailed(reason="write_contention")` docstring grep handed off to S6-03. Story-scoped gates green: 3 new tests, `mypy --strict tests/integration/test_phase4_harvest_contention.py`, `ruff check`, `ruff format --check`.)
**Effort:** M
**Depends on:** S4-03 (single-writer `asyncio.Lock` + 30s `StoreWriteContention` contract), S4-04 (manifest with monotonic chain_head; canonical YAML write ordering)
**ADRs honored:** ADR-0016 (single-writer constraint enforced; concurrent ingest serializes), Gap 3 (contention contract pinned for Phase 11 pgvector conformance)

## Validation notes (2026-05-22 — phase-story-validator)

Verdict **HARDENED**. The goal — a two-coroutine `asyncio.gather` integration test pinning the Gap 3 contention contract for the Phase-11 pgvector swap — is sound, and the AC set traces cleanly to it. Four critic lenses surfaced 2 block-severity defects and ~9 harden-severity gaps, all fixed in place:

- **AC-8 — `freezegun` removed (block).** AC-8 mandated `freezegun.freeze_time(...)` and falsely cited Phase-2 precedent. `freezegun` is **not** a project dependency and **no** repo test uses it; S4-04 Notes §3 explicitly chose the fixture-default `created_at` *over* `freezegun` ("no extra dep"). AC-8 now relies on `make_solved_example`'s fixed `created_at` default; the `frozen_time` autouse fixture and the `tests/integration/conftest.py` change are dropped.
- **AC-10 — `@pytest.mark.integration` removed (block).** The marker is unregistered (`pyproject.toml § [tool.pytest.ini_options].markers` lists only `bench`, `adv`, `phase02_adv`, `serial`, `nightly_macos`, `phase_7_preview`) and `--strict-markers` is on — the test would fail at collection. No repo test uses it; Phase-2 integration tests rely on directory placement. AC-10 now states the test runs in the default lane via `tests/integration/` placement, no custom marker.
- **AC-6 broadened (harden).** Was "no orphan YAML" only; now pins the full no-trace posture — a timed-out harvest leaves `ex-B` absent from `_record_ids`, `manifest.yaml`, and the chain head. Fixed the `tmp_path` → `tmp_root` records-dir path typo.
- **TDD Red section de-muddled (harden).** It wrongly attributed the `to_thread`-unwrap regression to AC-4. AC-4 catches a wrong lock *granularity*; AC-9 catches the `to_thread` unwrap. Removing `to_thread` makes the critical section *more* serialised, not less. Each AC's mutation target is now stated distinctly.
- **AC-9 hardened.** Was `call_count == 2` only; now also asserts every `to_thread` call wraps `collection.add`, and pins the `monkeypatch.setattr(asyncio, "to_thread", ...)` target.
- **`cap_factory` dropped; unused `cap_a`/`ex_a` removed from the timeout test (harden).** `cap_factory` was declared but unused (every code block constructs inline); the unused `cap_a`/`ex_a` in the timeout test would fail `ruff` (AC-11). Direct construction now carries the `# AC-2-test-only-direct-construction` comment S4-03 AC-2 mandates.
- **Same-partition made explicit (harden).** Both records now explicitly share the `(task_class, language, build_system)` triple so the two adds collide on the same chromadb collection — the realistic single-writer worst case.

**Cross-doc action the validator could not apply (Rule 7):** `phase-arch-design.md §Edge case #5` still says concurrent records land "(sorted by `created_at`)"; S4-04 (HARDENED) superseded this with **insertion order** (S4-04 Notes §4). The arch table needs a one-line amendment. Flagged here; the References block below notes the supersession.

Full audit log: `docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S4-08-harvest-contention-integration-test.md`

## Context

ADR-0016 + Gap 3 (arch §1106) name the load-bearing contention contract: under concurrent harvest (two workflows finishing validation near-simultaneously), `SolvedExampleStore.add` serializes via the process-local `asyncio.Lock`; **both records land deterministically** (sorted by add-arrival under the lock); the manifest's `chain_head` advances **monotonically** without collision. A 30 s timeout converts unbounded contention into a typed `StoreWriteContention(workflow_id)` raise.

Gap 3 §"Improvement" (arch §1106): *"`tests/integration/test_phase4_harvest_contention.py` spawns two harvest coroutines on the same store within `asyncio.gather` and asserts both succeed (sequenced) and chain-head advances monotonically. **The test pins the behavior** so Phase 11's pgvector swap has a clear conformance bar."*

S4-03 lands the *short* contention test (one timed-out add); S4-04 lands the chain-head monotonicity property. **This story is the load-bearing integration test** that composes both: two real-shape harvest coroutines under `asyncio.gather`, real chromadb, real YAML+manifest write, asserting:

1. Both coroutines return successfully (no exceptions; no `StoreWriteContention` in the happy path).
2. The resulting `manifest.chain_head` is **one of two valid orderings** (ex-A-first or ex-B-first); both records appear.
3. `store.digest()` equals `manifest.chain_head` (S4-04 AC-5 holds under contention).
4. A deliberate-timeout variant (one coroutine artificially holds the lock past the timeout) raises `StoreWriteContention` from the second coroutine — pinning the Phase-11 conformance bar.

The test runs under the real `asyncio.gather` (not mocks); chromadb's actual single-writer behavior is exercised. **The `asyncio.to_thread`-wrapped `chromadb.add` is the production path** (arch §Concurrency mandates it so a sync chromadb call never blocks the event loop). AC-9 pins that wrapping as a structural regression guard — if a refactor unwraps it, AC-9 fails. It does **not** "mask the contention": the `asyncio.Lock` serialises writes regardless of the `to_thread` wrapping (see the TDD Red section, which keeps the AC-4 / AC-9 mutation targets distinct).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Concurrency"` (line 269) — single-async-event-loop per workflow; `asyncio.Lock` guards `add`.
  - `../phase-arch-design.md §Edge case #5` — chromadb writer contention: `asyncio.Lock` serializes; both records land. **Note:** the arch table's parenthetical "(sorted by `created_at`)" is *superseded* — S4-04 (HARDENED) fixed the manifest `records` list to **insertion order** (add-arrival under the lock), explicitly **not** `created_at`-sorted (S4-04 Notes §4). This story follows insertion order; the arch table needs a one-line amendment (flagged in the validation report).
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
  - Phase-2 integration tests under `tests/integration/` — concurrency-touching test idioms (`asyncio.gather`, `monkeypatch`). Note: these tests do **not** use `freezegun` — it is not a project dependency (see AC-8); determinism comes from fixed-value fixtures.

## Goal

Ship `tests/integration/test_phase4_harvest_contention.py` that drives two harvest coroutines through `asyncio.gather` against a real `ChromaPersistentStore`, asserts both succeed with monotonically-advancing `manifest.chain_head` and digest equality, and a deliberate-timeout fixture variant raises `StoreWriteContention(workflow_id)` — pinning the Gap 3 conformance bar for the Phase-11 pgvector swap.

## Acceptance criteria

- [x] **AC-1 — Two-coroutine happy path under `asyncio.gather`.** Test `test_two_harvests_under_gather_both_succeed_sequenced`:
    - Constructs a fresh `ChromaPersistentStore(root_dir=tmp_path)`.
    - Two `SolvedExampleWriteCapability` instances with distinct `workflow_id`s (`wf-A`, `wf-B`).
    - Two coroutines: `coro_a = store.add(make_solved_example(id_="ex-A"), cap_a)`; `coro_b = store.add(make_solved_example(id_="ex-B"), cap_b)`.
    - `results = await asyncio.gather(coro_a, coro_b)` — assert no exception; `results == (SolvedExampleId("ex-A"), SolvedExampleId("ex-B"))` (or the reverse if scheduling flips; assert set-equality of the result set).
    - Final state: `len(store._record_ids) == 2`; both IDs present.
- [x] **AC-2 — `manifest.chain_head` advances monotonically across the gather.** Same test extends:
    - After both adds complete, read `manifest.yaml`; the chain_head is **one of two valid heads** — `head_ab = BLAKE3(yaml_a_bytes + yaml_b_bytes)` or `head_ba = BLAKE3(yaml_b_bytes + yaml_a_bytes)` (depending on lock-acquisition order).
    - The chain_head **is not** `BLAKE3(b"")` (empty) AND **is not** `BLAKE3(yaml_a_bytes)` alone (one record only); both records contributed.
    - Assert `manifest.chain_head in {head_ab, head_ba}` (order non-deterministic; **content is**).
- [x] **AC-3 — `store.digest() == manifest.chain_head` after gather.** S4-04 AC-5's byte-identity contract holds under the gather workload. Catches a "race where digest is computed mid-update" mutant; the lock ensures digest is computed only after manifest write completes.
- [x] **AC-4 — `_record_ids` order matches manifest.records.** `store._record_ids == manifest.records` exactly (same order). Catches a "record_ids appended but manifest written from a different order" mutant.
- [x] **AC-5 — Deliberate-timeout fixture raises `StoreWriteContention`.** Test `test_harvest_contention_timeout_raises_typed_exception`:
    - Two coroutines, but `coro_a` is wrapped to **hold the lock for >30s** (in the test, the timeout constant is `monkeypatch`ed to `0.1s` for fast tests; `coro_a` is an async function that acquires the lock and sleeps `0.5s` before releasing — exceeding the 0.1s timeout for `coro_b`).
    - `await asyncio.gather(coro_a, coro_b, return_exceptions=True)`.
    - `coro_a`'s result: success.
    - `coro_b`'s result: `StoreWriteContention` instance with `workflow_id == cap_b.workflow_id`.
    - **After both coroutines complete, the lock is released** (no leak); a subsequent third `await store.add(...)` succeeds.
- [x] **AC-6 — a timed-out harvest leaves NO trace anywhere.** When `coro_b` times out, *every* write is skipped — S4-04's `add()` acquires the `asyncio.Lock` **before** the first write and does YAML → chromadb → manifest entirely inside that critical section, so a timeout on `acquire()` means none of the three writes ran. The test asserts the **complete** no-trace posture:
    - `(tmp_root / "records" / "ex-B.yaml")` does **not** exist — no orphan canonical YAML. *(Note the path root: records live under `<root_dir>/records/`, i.e. `tmp_root / "records"`, **not** `tmp_path`.)*
    - `SolvedExampleId("ex-B") not in store._record_ids`.
    - `(tmp_root / "manifest.yaml")` does **not** exist immediately after the timeout — no successful `add()` has happened (`slow_add_a` writes nothing).
    - After the recovery `ex-C` add (AC-5), `manifest.yaml` lists **exactly** `["ex-C"]` — `ex-B` never appears in `records` or in the chain head. This transitively proves `ex-B` left no trace in `_record_ids`, the manifest, the chain head, or (since chromadb writes are last in the lock-held sequence) the chromadb collection.
    - This is the load-bearing posture: a timed-out harvest is *atomic-nothing* — distinct from S4-04 AC-4's chromadb-failure-*after*-YAML-write, which leaves a recoverable orphan. Both cases are catalogued in Notes §3.
- [x] **AC-7 — `SolvedExampleIngestFailed(reason=write_contention)` contract is documented for S6-03.** This story does **not** wire the event emission (S6-03 does); the *raise* shape itself is already pinned by AC-5. AC-7 is the **observable hand-off**: the timeout test's docstring (`test_harvest_contention_timeout_raises_typed_exception`) carries the verbatim expected-emission block below, so S6-03's executor implements the payload correctly. Verifiable by grep — the block must appear in that docstring:
    ```
    Expected emission (S6-03 responsibility — NOT wired here):
      event = SolvedExampleIngestFailed(
          reason="write_contention",
          workflow_id=cap_b.workflow_id,
      )
    ```
- [x] **AC-8 — deterministic `created_at` via the `make_solved_example` fixture default — NOT `freezegun`.** Every `SolvedExample` in this story is built through `make_solved_example(...)`, whose `created_at` kwarg **defaults to a fixed timestamp**. S4-04 Notes §3 chose option (B) — the fixture default — explicitly *over* `freezegun` ("for unit tests (no extra dep)"). `freezegun` is **not** a project dependency and **no** repo test uses it: do **not** add it, and do **not** add a `frozen_time` autouse fixture. The records are deterministic because the fixture default is deterministic; if any test ever needs a non-default `created_at`, pass it explicitly via the kwarg. (S4-04 AC-7's two-store byte-identity test already pins `make_solved_example` determinism — see Notes §6.)
- [x] **AC-9 — `asyncio.to_thread` boundary preserved.** A separate test, `test_to_thread_invoked_per_add` (its own two adds — not folded into the contention tests), monkeypatches `asyncio.to_thread` with `Mock(wraps=asyncio.to_thread)` via `monkeypatch.setattr(asyncio, "to_thread", mock)` (attribute-on-module form — `store.py` resolves `asyncio.to_thread` at call time, so patching the `asyncio` module attr takes effect). After two adds it asserts **both**:
    - (a) `mock.call_count == 2` — one per chromadb add; and
    - (b) every call's first positional argument is the chromadb `collection.add` bound method (`call.args[0].__name__ == "add"`).
    Asserting (b) as well as (a) catches not only an *unwrap* (count drops to 0) but a *wrong-target* mutant that keeps a `to_thread` call but wraps something else. This pins the production non-blocking posture (arch §Concurrency) as a structural regression guard — it is **not** a contention-correctness assertion (see the TDD Red section).
- [x] **AC-10 — Test runs in the default CI lane; carries NO custom marker.** The file lives under `tests/integration/`, so `testpaths = ["tests"]` collects it and `make test` runs it in the default lane — no marker is needed or wanted. Do **NOT** add `@pytest.mark.integration`: it is **not** a registered marker (`pyproject.toml § [tool.pytest.ini_options].markers` lists only `bench`, `adv`, `phase02_adv`, `serial`, `nightly_macos`, `phase_7_preview`), and `--strict-markers` is enabled — an unregistered marker fails at collection. No repo test uses `pytest.mark.integration`; Phase-2's integration tests rely on directory placement alone. The test is **not** adversarial (no `adv` / `phase02_adv`) — it pins production behavior. `@pytest.mark.asyncio` on the coroutine tests is acceptable (pytest-asyncio registers that marker) though redundant under `asyncio_mode = "auto"`; keep it only to match the S4-03 / S4-04 sibling test style.
- [x] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean.

## Implementation outline

1. **Test file:** `tests/integration/test_phase4_harvest_contention.py`.
2. **Fixtures:**
   - `tmp_root` (per-test): `tmp_path / "rag"`.
   - `store` (per-test): `ChromaPersistentStore(root_dir=tmp_root)`; teardown `store.close()`.
   - **No `frozen_time` fixture** — `make_solved_example`'s fixed `created_at` default gives determinism (AC-8); `freezegun` is not a project dependency.
   - **No `cap_factory` helper** — construct `SolvedExampleWriteCapability(workflow_id=WorkflowId(...))` inline at each use site (matches S4-03 / S4-04 test style; a one-line wrapper for ~3 uses is below the Rule-2 abstraction threshold). Mark each direct construction with a `# AC-2-test-only-direct-construction` comment, per S4-03 AC-2's boundary-lift convention — the test **cannot** use S4-06's `_phase4_local_capability_mint` because the import-linter contract fences that symbol to `src/codegenie/gates/` + `src/codegenie/rag/ingest.py`, and a test module is outside that allowlist.
   - **Partition:** both `ex-A` and `ex-B` are built with the **same** `(task_class, language, build_system)` triple (the `make_solved_example` defaults), so the two adds collide on the **same chromadb collection** — the realistic single-writer worst case. (The per-store `asyncio.Lock` serialises across partitions too, but same-collection contention is what this test must pin.)
3. **Happy-path test (AC-1 to AC-4):**
   ```python
   @pytest.mark.asyncio  # redundant under asyncio_mode="auto"; kept for sibling-test parity
   async def test_two_harvests_under_gather_both_succeed_sequenced(
       store: ChromaPersistentStore,
       tmp_root: Path,
   ) -> None:
       # AC-2-test-only-direct-construction (S4-03 AC-2 boundary lift)
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
   @pytest.mark.asyncio  # redundant under asyncio_mode="auto"; kept for sibling-test parity
   async def test_harvest_contention_timeout_raises_typed_exception(
       store: ChromaPersistentStore,
       tmp_root: Path,
       monkeypatch: pytest.MonkeyPatch,
   ) -> None:
       monkeypatch.setattr("codegenie.rag.store._ADD_LOCK_TIMEOUT_SECONDS", 0.1)
       # AC-2-test-only-direct-construction (S4-03 AC-2 boundary lift)
       cap_b = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-B"))
       ex_b = make_solved_example(id_="ex-B")
       # NB: slow_add_a() only hijacks the lock — it adds no record, so it needs
       # neither a capability nor a SolvedExample (Notes §5).

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

       # AC-6: a timed-out harvest leaves NO trace anywhere.
       assert not (tmp_root / "records" / "ex-B.yaml").exists()  # no orphan YAML
       assert SolvedExampleId("ex-B") not in store._record_ids
       assert not (tmp_root / "manifest.yaml").exists()  # no successful add yet

       # AC-5: lock not leaked — a subsequent add succeeds.
       assert store._add_lock.locked() is False
       # AC-2-test-only-direct-construction (S4-03 AC-2 boundary lift)
       cap_c = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-C"))
       sid_c = await store.add(make_solved_example(id_="ex-C"), cap_c)
       assert sid_c == SolvedExampleId("ex-C")
       # ex-B left no trace: the manifest lists exactly ["ex-C"].
       manifest = yaml.safe_load((tmp_root / "manifest.yaml").read_text("utf-8"))
       assert manifest["records"] == ["ex-C"]
   ```
5. **`asyncio.to_thread` instrumentation (AC-9):** a separate test, `test_to_thread_invoked_per_add`, in the same module — `monkeypatch.setattr(asyncio, "to_thread", Mock(wraps=asyncio.to_thread))`, does its own two adds, then asserts `mock.call_count == 2` **and** that every `call.args[0]` is the chromadb `collection.add` bound method. Kept as a separate test so it doesn't pollute the contention tests.

## TDD plan — red / green / refactor

### Red — write the failing test first

The happy-path test (`test_two_harvests_under_gather_both_succeed_sequenced` above) is the red test. It fails today because `codegenie.rag.store` does not exist until S4-03 / S4-04 land — and even after they land, this story's `asyncio.gather` two-coroutine shape is exercised nowhere else (S4-03 ships only the *short*, single-add contention test).

**What each AC catches — keep these mutation targets distinct, do not conflate them:**

- **AC-4 (`_record_ids` order == `manifest.records` order) catches a wrong lock *granularity*.** If the `asyncio.Lock` wraps only the chromadb call — not the whole YAML → chromadb → manifest sequence — coroutine B's `_record_ids.append` can interleave between coroutine A's append and A's manifest write, so the manifest captures a record list that disagrees with `_record_ids`. AC-4 catches that. Removing `asyncio.to_thread` does **not** cause this: an unwrapped, sync `collection.add` removes a yield point, making the critical section *more* serialised, not less.
- **AC-9 (`to_thread.call_count == 2`, each wrapping `collection.add`) catches the `to_thread` *unwrap*.** That regression is a production-posture violation — a sync chromadb call would block the event loop (arch §Concurrency) — **not** a contention-correctness violation: the `asyncio.Lock` still serialises writes whether or not the chromadb call is `to_thread`-wrapped. AC-9 is the structural guard for the unwrap; AC-4 is not.
- **AC-2 (`chain_head ∈ {head_ab, head_ba}`) catches a chain head computed over record IDs instead of canonical YAML bytes, or rolled over one record only.**
- **AC-3 (`digest() == manifest.chain_head`) is a *consistency* check** — both sides delegate to `_compute_chain_head`, so it is necessary but not sufficient; AC-2's `_expected_head` recomputation is the independent correctness oracle (mirrors S4-04 AC-5's independent-oracle discipline).

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
| `tests/integration/test_phase4_harvest_contention.py` | The load-bearing burst-contention test pinning Gap 3 for Phase 11. The **only** file this story creates. |

`tests/integration/conftest.py` is **not** touched — it already exists (a Phase-7 autouse `provenance_registry_reset` fixture, a harmless no-op for this test), and the `frozen_time` fixture it was originally slated to host is dropped along with `freezegun` (AC-8).

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

### §2 — `_ADD_LOCK_TIMEOUT_SECONDS` monkeypatch target

The timeout test monkeypatches the module constant `codegenie.rag.store._ADD_LOCK_TIMEOUT_SECONDS`. S4-03 (HARDENED) already pins this: its AC-8 + Implementation Outline §7 mandate `_ADD_LOCK_TIMEOUT_SECONDS: Final[float] = 30.0` as a module-level constant referenced at call time (S4-03's own short contention test patches the same symbol). So the target exists by S4-03's contract — this is a *consistency check*, not an open risk. If, against the contract, the executor finds a hardcoded literal, surface per Rule 7 and fix S4-03's constant — do not work around it in this test.

### §3 — YAML write inside the lock means timed-out harvest has no orphan

S4-04 AC-4 covered the chromadb-failure-after-YAML-write case (YAML on disk, manifest unchanged). This story's AC-6 covers the **lock-timeout case**: the lock is acquired **before** the YAML write begins. So a timed-out harvest never wrote any canonical bytes — clean. The two cases together:

- Lock acquired → YAML written → chromadb fails → manifest unchanged → YAML orphan (S4-04 AC-4).
- Lock acquire timeout → no YAML written → no orphan (this story AC-6).

Document both in S4-04's module docstring if not already covered. The orphan case (S4-04) is recovered by `codegenie rag rebuild` (S4-07); the no-orphan case (this story) needs no recovery.

### §4 — Don't add a `@pytest.mark.flaky` retry

The test's outcome is **deterministic** given the `make_solved_example` fixed-`created_at` default (AC-8) + a deterministic `asyncio.Lock`. The only non-determinism is lock-acquisition order (AC-2 asserts the chain head is one of two valid heads); no retry is needed. If the test ever flakes, the right response is to diagnose the race, not retry-mask it. Flaky-marker is `# noqa: do not add — see Notes §4`.

### §5 — The `slow_add_a` coroutine doesn't call `store.add`

It manually acquires/holds/releases `store._add_lock` to simulate "writer A is taking forever." If you tried to call `store.add(...)` from `coro_a` and have it sleep mid-call, you'd be testing chromadb's behavior, not the lock contract. The hand-rolled coroutine is the right test posture — touches *only* the lock state we're pinning.

`slow_add_a` uses the **raw** `await store._add_lock.acquire()` (not `asyncio.wait_for`). `asyncio.Lock.acquire()` on a free lock returns *without suspending*, so `slow_add_a` — scheduled first by `asyncio.gather` — holds the lock before it yields at `asyncio.sleep`, and `coro_b` is guaranteed to find the lock held. That is what makes the timeout test deterministic; do not "tidy" it into a `store.add` call or a `wait_for` wrapper.

### §6 — `make_solved_example` is already deterministic (S4-04 AC-7)

AC-2's `_expected_head` reads the *actual* on-disk YAML bytes, so a non-deterministic fixture would not break AC-2's `in {head_ab, head_ba}` assertion *within a single run* — but it would make results irreproducible across runs and would break S4-04 AC-7's two-store byte-identity test outright. That AC (HARDENED) **already** forces `make_solved_example` to be deterministic: a fixed `created_at` default (S4-04 Notes §3) and a deterministic embedding vector, so two `make_solved_example(id_="ex-A")` calls produce byte-identical YAML. By the time this story executes, the fixture is deterministic by S4-04's contract — rely on it. If a regression slips the fixture back to randomness, S4-04 AC-7 fails first; do not duplicate that guard here.

### §7 — Real chromadb in the test

The test uses a real `ChromaPersistentStore` against `tmp_path / "rag/"` — actual chromadb sqlite created and destroyed per test. This is slow (~50–200 ms per test); acceptable for two integration tests. Do **not** mock chromadb here; the entire point is to exercise the real lock + real `asyncio.to_thread` + real chromadb sync `add`. If a future refactor introduces a mocked `chromadb.PersistentClient`, this test's value disappears and the Phase-11 conformance bar weakens.

### §8 — Optional N=3 follow-on test

A `test_three_harvests_under_gather_chain_head_one_of_six_orderings` extends the same shape: three records, six valid head orderings (`3! = 6`). Useful if you want to catch a class of "ID-set-equality but ordering-bug" mutations. Cheap (one extra test ~ 100 ms); add it if the executor has the budget — otherwise N=2 is sufficient to pin Gap 3.
