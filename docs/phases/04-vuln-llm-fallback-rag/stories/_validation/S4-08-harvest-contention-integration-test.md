# Validation report — S4-08 Burst-harvest contention integration test

**Validated:** 2026-05-22
**Validator:** phase-story-validator (scheduled story-validation-corrector run)
**Verdict:** HARDENED
**Findings:** 2 block · 9 harden · 4 nit — all resolved in place

---

## Stage 1 — Context Brief

**Goal (verbatim):** Ship `tests/integration/test_phase4_harvest_contention.py` that drives two harvest coroutines through `asyncio.gather` against a real `ChromaPersistentStore`, asserts both succeed with monotonically-advancing `manifest.chain_head` and digest equality, and a deliberate-timeout fixture variant raises `StoreWriteContention(workflow_id)` — pinning the Gap 3 conformance bar for the Phase-11 pgvector swap.

**Story is the load-bearing integration test** composing two upstream contracts: S4-03 (single-writer `asyncio.Lock` + 30 s `StoreWriteContention`; module constant `_ADD_LOCK_TIMEOUT_SECONDS`) and S4-04 (canonical YAML write, `manifest.yaml` with BLAKE3-rolled `chain_head` over canonical YAML *bytes* in insertion order). Both dependencies are **HARDENED** but not yet GREEN — `src/codegenie/rag/` does not exist on disk; this is a pre-execution story-hardening pass.

**Phase / arch constraints checked:**
- ADR-0016 — single-writer declared in Protocol + enforced by `asyncio.Lock`; YAML canonical, chromadb derived.
- Gap 3 (arch §1106) — 30 s `await`, then `StoreWriteContention`; this very test is named as the pinned Phase-11 conformance bar.
- arch §Concurrency (line 269) — process-local `asyncio.Lock` guards `add`.
- arch §Edge case #5 (line 932) — concurrent records land; parenthetical "(sorted by `created_at`)" is **stale** (see Finding 6).
- `pyproject.toml § [tool.pytest.ini_options]` — `asyncio_mode = "auto"`, `--strict-markers`, registered markers `{bench, adv, phase02_adv, serial, nightly_macos, phase_7_preview}`.

**Verification reads performed:** S4-03 + S4-04 story files (full); `phase-arch-design.md` §Concurrency / §Edge case table / §Gap 3 / §Phase-11 integration; ADR-0016 §Decision; `pyproject.toml` markers + deps; `uv.lock` (`freezegun` grep); `tests/integration/conftest.py`; grep for `pytest.mark.integration` / `freezegun` across `tests/`.

**Open ambiguities:** none — proceeded to Stage 2.

---

## Stage 2 — Critic findings

### 2C · Consistency (highest priority)

**Finding 1 — BLOCK — AC-8 mandates `freezegun`, a non-existent dependency.**
AC-8 told the executor to fix `created_at` via `freezegun.freeze_time("2026-05-18T12:00:00Z")` and the References block claimed Phase-2 integration tests use `freezegun` as a "concurrency-touching test idiom". Verification: `freezegun` appears in neither `pyproject.toml` nor `uv.lock`; **zero** repo tests import `freezegun` / `freeze_time`. Worse, S4-04 Notes §3 — already HARDENED — explicitly evaluated freezegun (option A) vs a fixture-default `created_at` (option B) and **chose option B** with the stated rationale "for unit tests (no extra dep)". S4-08 AC-8 directly contradicts a hardened sibling decision and would introduce a dependency.
*Fix:* AC-8 rewritten to rely on `make_solved_example`'s fixed `created_at` default; `frozen_time` autouse fixture deleted from the Implementation outline; the `tests/integration/conftest.py` change dropped from Files-to-touch.

**Finding 2 — BLOCK — AC-10 mandates an unregistered pytest marker under `--strict-markers`.**
AC-10 required `@pytest.mark.integration`. The marker is **not** in `pyproject.toml`'s `markers` list, and `--strict-markers` is enabled (the config comment states it "forces every `pytest.mark.*` to be declared") — so collection would hard-fail. Verification: no repo test uses `pytest.mark.integration`; the existing `tests/integration/` tests run in the default lane purely by directory placement under `testpaths = ["tests"]`. The story's claim "Tagging matches Phase 2's integration test conventions" is false.
*Fix:* AC-10 rewritten — the test carries **no** custom marker; default-lane execution comes from the `tests/integration/` path. `@pytest.mark.integration` removed from both code blocks. `@pytest.mark.asyncio` retained (pytest-asyncio registers that marker; redundant under `asyncio_mode="auto"` but kept for S4-03/S4-04 parity).

**Finding 6 — HARDEN — References §Edge case #5 carries the stale "(sorted by `created_at`)" framing.**
The arch edge-case table still says concurrent records land "(sorted by `created_at`)". S4-04 (HARDENED, Notes §4) superseded this: the manifest `records` list is **insertion order** (add-arrival under the lock), explicitly *not* `created_at`-sorted — because sort-by-time would destroy the very monotonic-chain-head ordering this story pins. S4-08's own Context already says "sorted by add-arrival under the lock", so the story is internally correct; only the quoted References line propagated the stale text.
*Fix:* References line annotated with the supersession. **Cross-doc action the validator cannot apply (one story per invocation):** `phase-arch-design.md §Edge case #5` needs a one-line amendment dropping "(sorted by `created_at`)". Flagged in the story's Validation-notes block and here.

**Finding 9 — HARDEN — direct `SolvedExampleWriteCapability` construction lacks the S4-03 AC-2 boundary-lift comment.**
S4-03 AC-2 mandates a `# AC-2-test-only-direct-construction` comment at every direct construction site (the capability is normally minted; S4-06's `_phase4_local_capability_mint` is import-linter-fenced to `src/codegenie/gates/` + `src/codegenie/rag/ingest.py`, so a test module *must* construct directly). S4-08's code blocks constructed the capability with no such comment.
*Fix:* comment added at every construction site in both code blocks and documented in the fixtures note.

### 2A · Coverage

**Finding 3 — HARDEN — AC-6 under-specifies the timed-out-harvest posture.**
AC-6 asserted only "no orphan YAML for `ex-B`". The load-bearing invariant is broader: because every write is inside the lock-held critical section and the lock is never acquired on timeout, a timed-out harvest must leave **no trace anywhere** — not in `_record_ids`, not in `manifest.yaml`, not in the chain head, not in chromadb. Asserting only the YAML file leaves three of four surfaces unchecked; a mutant that times out but still appends to `_record_ids` would pass.
*Fix:* AC-6 broadened to pin `ex-B ∉ _record_ids`, `manifest.yaml` absent immediately post-timeout, and — after the `ex-C` recovery add — `manifest.records == ["ex-C"]` exactly (transitively proving no `ex-B` trace in the manifest, chain head, or chromadb). Timeout code block extended with the matching assertions.

**Finding 7 — HARDEN — AC-6 records-dir path typo (`tmp_path` vs `tmp_root`).**
AC-6 prose asserted `(tmp_path / "records" / "ex-B.yaml")`. The store is opened on `root_dir=tmp_root` (`tmp_path / "rag"`); records live under `<root_dir>/records/` = `tmp_root / "records"`. The code block was already correct; only the prose was wrong — but an executor copying the prose would assert a path that never exists and the test would pass vacuously.
*Fix:* corrected to `tmp_root` with an explicit path-root note.

**Finding 12 — HARDEN — partition placement of the two records left implicit.**
AC-1's `make_solved_example` calls vary `cve_id` but not the `(task_class, language, build_system)` triple — so both records default to the same partition, i.e. the same chromadb collection, which is the realistic single-writer worst case (HNSW writer contention). This is the *correct* posture but was never stated, so an executor could "spread" the records across partitions and silently weaken the test.
*Fix:* Implementation-outline fixtures note now states both records share the partition triple deliberately, and why.

### 2B · Test Quality

**Finding 4 — HARDEN — the TDD Red section conflates two distinct regressions.**
The Red prose claimed AC-4 (`_record_ids` order == `manifest.records` order) catches an `asyncio.to_thread` removal. It does not: an unwrapped sync `collection.add` removes a yield point and makes the critical section *more* serialised — it cannot cause the interleave AC-4 detects. AC-4 catches a wrong lock *granularity* (lock around the chromadb call only); AC-9 catches the `to_thread` unwrap (a production-posture violation, not a contention-correctness one — the `asyncio.Lock` serialises writes either way). Conflating them misdirects executor diagnosis.
*Fix:* Red section rewritten with a per-AC mutation-target list (AC-4 → lock granularity; AC-9 → `to_thread` unwrap; AC-2 → ID-vs-bytes / single-record chain head; AC-3 → consistency-only, AC-2's `_expected_head` is the independent oracle).

**Finding 5 — HARDEN — AC-9 asserted only `call_count`.**
`to_thread.call_count == 2` catches an unwrap (count → 0) but not a wrong-target mutant that keeps a `to_thread` call but wraps a different callable. The monkeypatch target was also unspecified.
*Fix:* AC-9 now pins `monkeypatch.setattr(asyncio, "to_thread", Mock(wraps=...))` (attribute-on-module form — `store.py` resolves `asyncio.to_thread` at call time) and asserts **both** `call_count == 2` and that every `call.args[0]` is the chromadb `collection.add` bound method.

**Finding 8 — HARDEN — unused `cap_a` / `ex_a` in the timeout test would fail `ruff` (AC-11).**
The timeout code block constructed `cap_a` and `ex_a`, but `slow_add_a` only hijacks the lock and adds no record — both are dead locals. `ruff` flags unused variables; AC-11 demands `ruff` clean, so the story as written was self-contradictory.
*Fix:* `cap_a` / `ex_a` removed from the timeout block; an explanatory `NB:` comment added.

### 2D · Design Patterns

**Finding 10 — HARDEN (Rule 2) — `cap_factory` declared but unused.**
The Implementation outline declared a `cap_factory(workflow_id_str)` helper, yet every code block constructs `SolvedExampleWriteCapability(...)` inline. A one-line wrapper used three times, never actually used in the prescribed code, is premature abstraction (Rule 2: "three similar lines is better than a premature abstraction") and diverges from the S4-03/S4-04 inline-construction precedent (Rule 11).
*Fix:* `cap_factory` dropped; fixtures note prescribes inline construction with the AC-2 boundary-lift comment.

**Observation (no edit) — AC-2's `{head_ab, head_ba}` superset assertion is a strength, not a defect.** Under CPython's FIFO task scheduling coroutine A deterministically wins the happy-path lock, so `head_ba` is effectively unreachable — but asserting membership in the two-element superset is the *robust* choice: it does not depend on an asyncio scheduling implementation detail that could shift across Python/loop versions. Kept as-is; the story's Out-of-scope ("does not assert which one wins") already documents the posture correctly.

### Nits (folded into the edits above)

- **N-11 — Context ¶ over-claimed** that an `asyncio.to_thread` unwrap "would mask the contention". Softened: AC-9 guards the production non-blocking posture (arch §Concurrency); the `asyncio.Lock` serialises regardless.
- **N — Notes §2** (timeout-constant brittleness) reframed: S4-03 (HARDENED) already pins `_ADD_LOCK_TIMEOUT_SECONDS` as a module constant — this is now a consistency check, not an open risk.
- **N — Notes §6** (`make_solved_example` determinism) reframed: S4-04 AC-7's two-store byte-identity test already pins fixture determinism; do not duplicate the guard.
- **N — Notes §5** gained a paragraph explaining *why* `slow_add_a`'s raw `acquire()` (vs `wait_for`) makes the timeout test deterministic — pre-empts a "tidy it up" refactor.
- **N — AC-7** reframed as an *observable* hand-off (the expected-emission block must appear verbatim in the named test's docstring — grep-checkable) rather than a vague "document it".

---

## Stage 3 — Researcher

Not invoked — no finding was tagged `NEEDS RESEARCH`. The contention contract, BLAKE3 chain-head shape, and `asyncio.gather` test idiom are all fully specified by ADR-0016 / Gap 3 / S4-03 / S4-04; the defects were consistency and specification gaps, not missing methodology.

---

## Stage 4 — Synthesis

Conflict resolution: no critic conflicts arose. Consistency findings (1, 2, 6, 9) drove the two blocks and the deepest edits; Coverage and Test-Quality findings strengthened the AC set without contradicting the goal. The goal and the test shape were sound throughout — no scope rewrite, no RESCUE.

**Edits applied to the story** (all in place):
- Header: `Status: Ready → HARDENED`; `Validation notes` block appended.
- Context: `to_thread` over-claim softened.
- References: Edge case #5 supersession annotated.
- AC-6: broadened to full no-trace posture; `tmp_path`→`tmp_root` corrected.
- AC-7: reframed as a grep-verifiable docstring hand-off.
- AC-8: `freezegun` mandate replaced with the `make_solved_example` fixed-default approach.
- AC-9: monkeypatch target pinned; wrapped-callable assertion added.
- AC-10: `@pytest.mark.integration` removed; default-lane-by-directory documented.
- Implementation outline: `frozen_time` + `cap_factory` removed; same-partition note added; both code blocks de-markered, de-`freezegun`'d, dead locals removed, AC-2 comments + AC-6 no-trace assertions added; AC-9 instrumentation step rewritten.
- TDD Red: per-AC mutation-target list replacing the conflated prose.
- Files to touch: `conftest.py` row removed.
- Notes §2 / §5 / §6: reframed per the nits above.

**Verdict: HARDENED.** Two block-severity defects (both "wrong prescription", not "broken goal") and nine harden gaps, all fixed in place. The story is ready for `phase-story-executor`.

**Carry-forward for the executor:**
1. `phase-arch-design.md §Edge case #5` still needs the "(sorted by `created_at`)" parenthetical removed — a one-line arch amendment outside this story's scope.
2. Execution is gated on S4-03 + S4-04 reaching GREEN (they are HARDENED, not yet implemented); `src/codegenie/rag/` does not exist yet.
