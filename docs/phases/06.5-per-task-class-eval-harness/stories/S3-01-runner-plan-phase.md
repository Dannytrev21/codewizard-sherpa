# Story S3-01 — Runner plan phase: load + digest + cache-key compute

**Step:** Step 3 — Implement the runner: asyncio fan-out, subprocess rubric, aggregator with BCa bootstrap
**Status:** Ready (HARDENED 2026-05-27)
**Effort:** M
**Depends on:** S1-01 (typed errors — `ChainTamperDetected` marker-only; `TaskClassNotFound`; `BenchCaseDigestMismatch`; `BenchCaseIDCollision`), S1-02 (wire models — `BenchCase`, `BenchRunReport`; the wire shape `_FROZEN_WIRE_TYPES` cardinality is unchanged), S1-03 (`TaskClass` dataclass, `TaskClassRegistry`, `default_registry`), S2-01 (`load_task_class(name, bench_root, *, registry=None)`), S2-02 (`load_cases(task_class)` — returns sorted-by-`case_id` tuple, raises typed errors), S2-03 (`compose_cache_key(inputs: CacheKeyInputs) -> CacheKey`, `CacheKey` newtype, `CacheKeyInputs` aggregate), S2-04 (`audit.write_run_record`, `audit.verify`, `codegenie.hashing.chain_identity`, `GENESIS_PREV_HASH`)
**ADRs honored:** ADR-0001 (subprocess isolation — `isolation_class="subprocess"` annotated on the RunPlan that flows to the report), ADR-0002 (lower_bound_95 — `run_id` is content-addressed so the bootstrap seed `int(run_id[:8], 16)` is reproducible), ADR-0010 (isolation_class annotation — `isolation_class` is a *report* field and is **NOT** part of the cache-key composition; mutating it must NOT shift `cache_keys`)

## Validation notes

Hardened 2026-05-27 by the `phase-story-validator` skill. 26 critic findings (6 blocks, 16 hardens, 4 nits) applied. Highlights:

- **F-CON-1 (block).** `compose_cache_key(case_digest=..., sut_digest=..., ...)` (6 kwargs) replaced with `compose_cache_key(inputs: CacheKeyInputs) -> CacheKey` (HARDENED S2-03 shape). The 6-kwarg signature no longer exists.
- **F-CON-2 (block).** `chain_result.head` on `audit.verify(...)` replaced with a new public primitive `codegenie.eval.audit.read_chain_head(out_dir) -> str` (AC-19). `VerifyResult` has no `.head` field (HARDENED S2-04).
- **F-CON-3 (block).** `ChainTamperDetected.file_path` attribute access replaced with positional-args + `ei.value.args[N]` discipline (S1-01 + HARDENED S2-04 marker-only Exception).
- **F-CON-4 (block).** `"0" * 64` literal replaced with `codegenie.hashing.GENESIS_PREV_HASH` constant.
- **F-CON-5 (block).** Non-existent `codegenie.hashing.blake3_tree(cassette_root)` replaced with a new public primitive `codegenie.hashing.content_hash_tree(root, *, glob, follow_symlinks) -> str` (AC-20), composed via the existing `tree_digest_of_files` chokepoint.
- **F-CON-6 (block).** Bare BLAKE3 concatenation of three rubric files replaced with boundary-safe composition via `tree_digest_of_files` over a length-prefixed stream (AC-5).
- **F-TQ-1 (block).** Undefined `_stable_plan_args()` pinned with a concrete fixture shape; `tests/helpers/bench.py:stub_task_class_fixture(tmp_path)` and `tests/helpers/chain.py:seed_clean_chain(out_dir)` defined.
- **F-TQ-2 (block).** `test_plan_run_id_is_16_hex_chars_of_blake3` rewritten to recompute via an independent oracle (`identity_hash(...)[:16]`).
- **F-COV-1..F-COV-8.** Added ACs for empty-bench path, `cases` sort invariant, post-genesis head derivation, `BenchCaseDigestMismatch` / `BenchCaseIDCollision` propagation, `harness_version` validation, full abort-order positional pin.
- **F-DP-1/F-DP-2.** Primitive-obsession fixed: `cache_keys: Mapping[str, CacheKey]`; `RunId = NewType("RunId", str)` added; `_compose_run_id` is the smart constructor.
- **F-DP-3.** Three pure helpers extracted (`_compose_rubric_digest`, `_compose_cassette_corpus_digest`, `_compose_run_id`) for direct unit tests (functional core / imperative shell).
- **F-DP-5.** `RunPlan.__post_init__` invariant: `set(cache_keys.keys()) == {c.case_id for c in cases}`; makes broken state unrepresentable.
- **F-CON-8.** Plan threads `registry=` kwarg through to `load_task_class` (S2-01 AC-16 DI pattern).
- **F-TQ-3.** Import-site convention pinned: `runner.py` imports modules (`from codegenie.eval import audit, cache`), not symbols; tests patch at `codegenie.eval.cache.put` accordingly.
- **F-DP-6.** `RunnerCollaborators` injection aggregate **deferred** — rule of three not met today (Phase 9's durable workflow would be the second consumer). Surfaced in implementer notes with explicit trigger.

Full audit trail: `_validation/S3-01-runner-plan-phase.md`.

## Context

The runner's first phase is pure planning: load the task class, verify the audit chain at startup, **read** the current chain head, compute the three deterministic digests (`sut_digest`, `rubric_digest`, `cassette_corpus_digest`), derive per-case `cache_key`s, and abort *before* any SUT invocation if anything is wrong. This is the load-bearing gate that prevents poisoned cases or a tampered chain from contaminating a run.

The plan output is a plain frozen dataclass consumed by S3-02's fan-out. Plan is **pure** — no SUT calls, no rubric subprocess, no cache writes, no audit appends. Plan's invariant is "abort early, abort loud" (CLAUDE.md "Fail loud"): if the chain is tampered or any case digest mismatches, no new state is created and exit code 5 (tamper) or 6 (digest mismatch) propagates to the CLI.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Process view` — the six-phase pipeline diagram; this story owns phases 1 (plan) and the integrity check at startup.
  - `../phase-arch-design.md §Components → runner.py` — `run_eval` six-phase internal structure; this story is phase 1 only.
  - `../phase-arch-design.md §Control flow → Happy path (cold cache, vuln-remediation, 10 cases)` — sequencing of `audit.verify` → `loader.load_task_class` → `loader.load_cases` → digest computation → per-case `cache_key`.
  - `../phase-arch-design.md §Control flow → Decision points #5 (audit chain tamper)` and `#6 (bench-case digest mismatch)` — both abort before any SUT invocation; exit codes 5 and 6.
  - `../phase-arch-design.md §Edge cases #11` — tamper detected at startup → exit code 5; no new record written.
  - `../phase-arch-design.md §Components → cache.py` — composition rule for `cache_key`: matches HARDENED S2-03's `compose_cache_key(CacheKeyInputs)` signature.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md` — the rubric subprocess shape is what makes `rubric_digest` a single artifact (rubric.py + breakdown_keys.py + failure_modes.yaml).
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md` — `run_id` derives a deterministic bootstrap seed (`int(run_id[:8], 16)`); plan must produce a content-addressed `run_id` for that downstream contract to hold.
  - `../ADRs/0010-isolation-class-annotation-on-bench-run-report.md` — `isolation_class` is a *report* field, not a *cache_key* component; plan documents this distinction explicitly.
- **Production ADRs:** `../../../production/adrs/0009-humans-always-merge.md` — audit chain is hard gate; tamper aborts before any new state.
- **Sibling stories (HARDENED predecessors — the contracts THIS story consumes):**
  - `S2-01-bench-import-path-resolution.md` — `load_task_class(name, bench_root=Path("bench"), *, registry=None)` DI signature.
  - `S2-02-loader-cases-and-digests.md` — `load_cases(task_class) -> tuple[BenchCase, ...]` sorted by `case_id`; typed errors.
  - `S2-03-content-addressed-cache.md` — `compose_cache_key(inputs: CacheKeyInputs) -> CacheKey`; `CacheKey` newtype; `__all__` locked.
  - `S2-04-audit-chain-extension.md` — `audit.write_run_record`, `audit.verify`, `codegenie.hashing.chain_identity`, `GENESIS_PREV_HASH`; `ChainTamperDetected` is marker-only (no named attrs).
- **Source design:** `../final-design.md §Components → runner.py`, `§Synthesis ledger row "Concurrency knob source"`.

## Goal

Land `Runner.plan(task_class_name, *, sut_digest_fn, bench_root, out_dir, run_started_iso, cassette_root, harness_version, registry=None) -> RunPlan` that resolves the task class, verifies the audit chain, reads the current chain head, computes the three digests, derives per-case cache keys, and aborts on digest mismatch or chain tamper *before* any SUT call.

## Acceptance criteria

### Shape of `RunPlan` + pure-data invariants

- [ ] **AC-1.** `RunPlan` is a `@dataclass(frozen=True, slots=True)` in `src/codegenie/eval/runner.py` carrying: `task_class: TaskClass`, `cases: tuple[BenchCase, ...]` (sorted by `case_id`; pinned by AC-13), `sut_digest: str`, `rubric_digest: str`, `cassette_corpus_digest: str` (all three are `blake3:<64 hex>` strings), `harness_version: str`, `run_id: RunId`, `prev_chain_head: str` (either `GENESIS_PREV_HASH` or a `sha256:<64 hex>` from `chain_identity`), `cache_keys: Mapping[str, CacheKey]` (outer key = `case_id` raw `str`; value = `CacheKey` newtype from HARDENED S2-03), `isolation_class: Literal["subprocess"] = "subprocess"`.

- [ ] **AC-1a.** `RunPlan.__post_init__` enforces the cache-keys / cases invariant: `set(cache_keys.keys()) == {c.case_id for c in cases}` — otherwise `raise ValueError(f"cache_keys/cases mismatch: missing={..}, extra={..}")`. Pinned by `tests/fence/test_runner_plan_invariants.py` (mutation: a wrong impl that derives keys from `range(len(cases))` builds an unreachable state — the invariant raises).

- [ ] **AC-2.** `run_id` is content-addressed: derived via `_compose_run_id(task_class_name, sut_digest, rubric_digest, cassette_corpus_digest, run_started_iso) -> RunId`. The composition uses `codegenie.hashing.identity_hash(...)` (boundary-safe — prepends arity byte + UNIT_SEP per Phase 0 docstring) over the five string inputs; strips the leading `sha256:` prefix; truncates to the first 16 hex chars; wraps in `RunId(...)`. Independently testable via the oracle (AC-3a). **Bare `BLAKE3(a || b || c)` concatenation is forbidden** — boundary-shift unsafe.

- [ ] **AC-3.** Two `plan(...)` calls with byte-identical inputs produce byte-identical `RunPlan` — compared via `json.dumps(dataclasses.asdict(plan), default=str, sort_keys=True)`. Load-bearing for ADR-0002's deterministic bootstrap seed.

- [ ] **AC-3a.** **Hypothesis determinism property.** Generate `(task_class_name, sut_digest_hex, rubric_digest_hex, cassette_corpus_digest_hex, run_started_iso)` tuples drawn from constrained strategies; build the underlying fixtures deterministically from the tuple; assert that two consecutive `plan(...)` calls produce byte-identical RunPlans. (Stronger than AC-3's single-input determinism; catches dict-iteration-order non-determinism in `cache_keys`.)

### Abort order — verify → load_task_class → load_cases → sut_digest → rubric_digest → cassette_corpus_digest → run_id → cache_keys

- [ ] **AC-4.** **Chain tamper aborts first.** When `audit.verify(out_dir).ok is False`, `plan(...)` raises `ChainTamperDetected` constructed **positionally** (S1-01 marker-only discipline — no kwargs, no custom `__init__`): `ChainTamperDetected(str(verify_result.tampered_path or out_dir), verify_result.reason or "verify-not-ok", "")`. Tests assert via `ei.value.args == (...)` — **no attribute access** on the exception. `load_task_class` is NOT called.

- [ ] **AC-15.** **BenchCaseDigestMismatch propagates unwrapped.** When `load_cases` raises `BenchCaseDigestMismatch(case_id, expected, computed)`, `plan(...)` does NOT catch / re-raise / wrap; the original exception flows out with attributes intact (S2-02 HARDENED contract). Asserted via `pytest.raises(BenchCaseDigestMismatch) as ei: ...; assert ei.value.case_id == "002-x"`.

- [ ] **AC-16.** **BenchCaseIDCollision propagates unwrapped.** Same discipline as AC-15 for `BenchCaseIDCollision(case_id, paths)`.

- [ ] **AC-7.** **TaskClassNotFound propagates** — when `load_task_class` raises `TaskClassNotFound(name, looked_up_in, available_names)` (S2-01 HARDENED), `plan(...)` does NOT catch it. The S4-02 CLI maps this to exit code 3.

- [ ] **AC-18.** **`sut_digest_fn` is not called before `load_cases` returns.** A poisoned-bench run must not pay the cost of computing the SUT digest. Asserted by passing `sut_digest_fn = Mock(side_effect=lambda: pytest.fail("must not be called when load_cases raises"))` and exercising the `BenchCaseDigestMismatch` path.

### Rubric digest — boundary-safe composition

- [ ] **AC-5.** `_compose_rubric_digest(rubric_path, breakdown_path, failure_modes_path) -> str` returns `blake3:<64 hex>`. Implementation MUST compose via `codegenie.hashing.tree_digest_of_files([("rubric.py", rubric_bytes), ("breakdown_keys.py", breakdown_bytes), ("failure_modes.yaml", failure_modes_bytes)])` (length-prefixed records per Phase 0 chokepoint) and re-prefix the result as `f"blake3:{hex}"`. **Equivalent acceptable composition:** `identity_hash_bytes(content_hash_bytes(rubric) + content_hash_bytes(breakdown) + content_hash_bytes(failure_modes))` — both are boundary-safe. **Bare concatenation `BLAKE3(rubric || breakdown || failure_modes)` is forbidden.**

- [ ] **AC-5a.** **Parametrized one-byte-flip mutation test.** For each of `["rubric.py", "breakdown_keys.py", "failure_modes.yaml"]`, append one whitespace byte to the file, recompute `rubric_digest`, assert it differs from baseline. Catches the mutant that hashes only two of the three files.

- [ ] **AC-5b.** **Cache invalidation property.** Mutating `rubric_digest` (via the AC-5a edits) must change `plan.cache_keys[case_id]` for EVERY case — asserted via `dict(plan_a.cache_keys).items().isdisjoint(plan_b.cache_keys.items())`. (Pins the load-bearing claim that a rubric edit invalidates the entire cache.)

### Cassette-corpus digest — new public helper

- [ ] **AC-20.** **New public helper `codegenie.hashing.content_hash_tree(root: Path, *, glob: str = "**/*", follow_symlinks: bool = False) -> str`** returning `blake3:<64 hex>`. Implementation walks `sorted(root.rglob(glob))`, filters to files (skips symlinks unless `follow_symlinks=True`), builds `[(rel_posix, path.read_bytes()) for ...]` in lexicographic relpath order, composes via the existing `tree_digest_of_files` chokepoint (length-prefixed records), and re-prefixes the un-prefixed result as `f"blake3:{hex}"`. Added to `codegenie.hashing.__all__` (locked tuple grows by one). The implementation MUST NOT call `blake3` or `hashlib.sha256` directly — chokepoint discipline (ADR-0001).

- [ ] **AC-20a.** **`content_hash_tree` determinism + symlink discipline.** Two back-to-back calls on the same tree produce byte-identical digests. A symlink under the tree is skipped by default (asserted by adding a symlink, verifying the digest is unchanged); when `follow_symlinks=True` the symlink target's bytes are included.

- [ ] **AC-20b.** **`_compose_cassette_corpus_digest(cassette_root: Path) -> str`** in `runner.py` is a thin one-line consumer: `return content_hash_tree(cassette_root, glob="**/*")`. Tested directly (pure helper).

### Cache-key composition — consumes HARDENED S2-03

- [ ] **AC-6.** Per-case `cache_key` derivation: for each `case in plan.cases`, `plan.cache_keys[case.case_id] = compose_cache_key(CacheKeyInputs(case_digest=case.case_digest, sut_digest=plan.sut_digest, rubric_digest=plan.rubric_digest, cassette_corpus_digest=plan.cassette_corpus_digest, harness_version=plan.harness_version, cassette_canary_pin=case.cassette_canary_pin))`. Uses HARDENED S2-03's aggregate signature (NOT 6 kwargs). Result is `CacheKey` newtype (carried verbatim in the mapping value type).

- [ ] **AC-6a.** **Positional-swap mutation guard at the plan layer.** Build a fixture with `sut_digest="SUT_X"` and `rubric_digest="RUB_Y"`; build a sibling fixture that swaps the two values (same RunPlan inputs otherwise); assert `plan_a.cache_keys != plan_b.cache_keys`. Pins that plan wires inputs into the right `CacheKeyInputs` slots; mirrors HARDENED S2-03's `itertools.combinations`-based positional-swap pattern.

- [ ] **AC-8.** **`isolation_class` is NOT in `cache_key` composition (behavioural test, not source-grep).** Build a RunPlan with `isolation_class="subprocess"`; conceptually-mutate isolation by passing a different placeholder value via a thin test seam; assert `cache_keys` are byte-identical across the mutation. (Today only one `isolation_class` value exists, so the test fixture must use a stub `RunPlan` variant that exercises the absence; the load-bearing fact is the *implementation* of cache-key derivation must not read `isolation_class` — verified by inspecting `compose_cache_key`'s call site to confirm `isolation_class` is not in the `CacheKeyInputs` field list. The aggregate signature mechanically forbids it — AC-6 reading the S2-03 surface IS the structural guard.) Documented in implementer notes citing ADR-0010 §"`isolation_class` is structural, not a runtime measurement."

### Prev-chain-head reading — new public primitive

- [ ] **AC-19.** **New public primitive `codegenie.eval.audit.read_chain_head(out_dir: Path) -> str`.** Returns `GENESIS_PREV_HASH` when `out_dir` does not exist OR contains no `*.json`; otherwise returns the `chain_head` field of the lexicographically-greatest `*.json` parsed as the canonical record (S2-04 contract: the file's `chain_head` field IS the identity hash). Implementation is a thin shim over HARDENED S2-04's private `_current_head` — adds the function to `audit.__all__` and exposes it publicly. Phase 9's Temporal-durable event log will be the second consumer (extension by addition). `plan(...)` calls this AFTER `audit.verify(...).ok is True` to populate `RunPlan.prev_chain_head`.

- [ ] **AC-14.** **Happy-path chain-head derivation.** Seed one valid `BenchRunReport` via `audit.write_run_record(...)`; call `plan(...)`; assert `plan.prev_chain_head == chain_identity(GENESIS_PREV_HASH, content_hash_bytes(canonical_json(report.model_copy(update={"chain_head": ""}))))` — recomputed via the oracle (do NOT trust the function under test). Mirrors S2-04 AC-6's oracle discipline.

### Empty bench + sort invariant

- [ ] **AC-12.** **Empty-bench path.** When `load_cases(task_class)` returns `()`, `plan(...)` succeeds and returns `RunPlan(..., cases=(), cache_keys={}, ...)` with a valid 16-hex `run_id`. (Empty bench is a legitimate state during early Phase 7 / new-task-class scaffolding; the bootstrap seed concern is S3-05's problem, not plan's.)

- [ ] **AC-13.** **Cases-are-sorted invariant.** `tuple(c.case_id for c in plan.cases) == sorted(c.case_id for c in plan.cases)`. Mirrored as a hypothesis property over shuffled load_cases inputs (HARDENED S2-02 AC-17 precedent).

### Purity + side-effect discipline

- [ ] **AC-9.** `plan(...)` performs no SUT call, no rubric subprocess, no `cache.put`, no `audit.write_run_record` — asserted by patching at the import site (`codegenie.eval.cache.put`, `codegenie.eval.audit.write_run_record`) with `lambda *a, **kw: pytest.fail(...)` sentinels.

- [ ] **AC-9a.** **Ordered call log (stronger than per-sink fail-sentinels).** Pass instrumented spies as collaborators where injectable (`sut_digest_fn`); for the module-imported collaborators (`load_task_class`, `load_cases`, `audit.verify`, `audit.read_chain_head`), wrap them with `unittest.mock.MagicMock(wraps=...)`. Assert call order equals the canonical abort sequence: `audit.verify → audit.read_chain_head → load_task_class → load_cases → sut_digest_fn → (rubric digest read) → (cassette tree walk)`. Catches the mutant that calls `load_task_class` before `audit.verify`.

### Validation of inputs

- [ ] **AC-17.** **`harness_version` shape validation.** Non-empty `str` matching `re.compile(r"^[0-9a-z][0-9a-z.+-]*$")` (permissive CalVer / SemVer). Empty / `None` / `bytes` → `TypeError("harness_version must be a non-empty version string, got: ...")` at plan entry, before any I/O.

### DI for test isolation

- [ ] **AC-21.** **`registry=` kwarg threads through.** `plan(...)` accepts optional `registry: TaskClassRegistry | None = None`; passes through to `load_task_class(name, bench_root, registry=registry)`. When `None`, falls back to `codegenie.eval.registry.default_registry`. Mirrors HARDENED S2-01 AC-16. Test isolation: each test passes a fresh `TaskClassRegistry()` so no module-level state crosses tests.

### Observability

- [ ] **AC-22.** **Event-id discipline.** Module-level `_EVENT_IDS: Final[frozenset[str]] = frozenset({"runner.plan_complete"})` validated at import via `raise AssertionError(f"event id {eid} violates regex")` against the Phase 1 regex `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` (bare `assert` is forbidden by the `forbidden-patterns` pre-commit hook). On successful plan completion, emit `structlog.info("runner.plan_complete", run_id=plan.run_id, n_cases=len(plan.cases), prev_chain_head_short=plan.prev_chain_head[:16], sut_digest_short=plan.sut_digest[:16], rubric_digest_short=plan.rubric_digest[:16])` exactly once. No per-case logs in `plan(...)` (S3-02 owns those).

### Tooling

- [ ] **AC-10.** `mypy --strict`, `ruff format --check`, `ruff check` clean on touched files.
- [ ] **AC-11.** All red tests in §TDD plan exist, were committed at the red marker, and are now green.

## Implementation outline

1. **Add `RunId` newtype.** In `src/codegenie/types/identifiers.py`: `RunId = NewType("RunId", str)` (mirrors existing `CacheKey`, `ProbeId` precedent). Re-export from `codegenie.eval.runner` for ergonomics.

2. **Add `codegenie.hashing.content_hash_tree(root, *, glob="**/*", follow_symlinks=False) -> str`.** Implementation:
   ```python
   def content_hash_tree(root: Path, *, glob: str = "**/*", follow_symlinks: bool = False) -> str:
       paths = sorted(p for p in root.rglob(glob) if p.is_file() and (follow_symlinks or not p.is_symlink()))
       pairs = [(p.relative_to(root).as_posix(), p.read_bytes()) for p in paths]
       hex_no_prefix = tree_digest_of_files(pairs)  # un-prefixed sha256 hex per existing chokepoint
       # Re-hash through blake3 for the conventional blake3:<hex> shape so callers can compare apples-to-apples
       # with other content_hash_* helpers. Composition via the existing chokepoint primitives only.
       return content_hash_bytes(bytes.fromhex(hex_no_prefix))
   ```
   Add `"content_hash_tree"` to `hashing.__all__`. **Do not** call `blake3()` or `hashlib.sha256()` directly anywhere except the existing chokepoint primitives.

3. **Add `codegenie.eval.audit.read_chain_head(out_dir: Path) -> str`.** Thin shim over the (HARDENED S2-04) private `_current_head`:
   ```python
   def read_chain_head(out_dir: Path) -> str:
       prev, _path = _current_head(out_dir)
       return prev  # either GENESIS_PREV_HASH or a sha256:<hex> from chain_identity
   ```
   Add `"read_chain_head"` to `audit.__all__`. Phase 9's durable event log is the planned second consumer.

4. **Add `RunPlan` `@dataclass(frozen=True, slots=True)`** to `src/codegenie/eval/runner.py` per AC-1. Include `__post_init__` (AC-1a) that enforces the cache-keys / case-ids invariant.

5. **Extract three pure helpers** in `runner.py` (functional core; tested directly):
   - `_compose_rubric_digest(rubric_path: Path, breakdown_path: Path, failure_modes_path: Path) -> str` (AC-5).
   - `_compose_cassette_corpus_digest(cassette_root: Path) -> str` — one-line wrapper around `content_hash_tree` (AC-20b).
   - `_compose_run_id(task_class_name: str, sut_digest: str, rubric_digest: str, cassette_corpus_digest: str, run_started_iso: str) -> RunId` (AC-2): `raw = identity_hash(task_class_name, sut_digest, rubric_digest, cassette_corpus_digest, run_started_iso); return RunId(raw.removeprefix("sha256:")[:16])`.

6. **Implement `Runner.plan(...)`** with this exact order (abort early at each step):
   ```python
   class Runner:
       def plan(
           self,
           task_class_name: str,
           *,
           sut_digest_fn: Callable[[], str],
           bench_root: Path,
           out_dir: Path,
           run_started_iso: str,
           cassette_root: Path,
           harness_version: str,
           registry: TaskClassRegistry | None = None,
       ) -> RunPlan:
           _validate_harness_version(harness_version)                       # AC-17 (TypeError before any I/O)
           verify_result = audit.verify(out_dir)                            # AC-4: tamper check first
           if not verify_result.ok:
               raise ChainTamperDetected(
                   str(verify_result.tampered_path or out_dir),
                   verify_result.reason or "verify-not-ok",
                   "",
               )
           prev_chain_head = audit.read_chain_head(out_dir)                 # AC-19 — new public primitive
           task_class = loader.load_task_class(                             # AC-7 (TaskClassNotFound propagates)
               task_class_name, bench_root, registry=registry,
           )
           cases = loader.load_cases(task_class)                            # AC-15/AC-16 (typed errors propagate)
           sut_digest = sut_digest_fn()                                     # AC-18 — not called before load_cases returns
           rubric_digest = _compose_rubric_digest(                          # AC-5
               task_class.bench_path / "rubric.py",
               task_class.bench_path / "breakdown_keys.py",
               task_class.bench_path / "failure_modes.yaml",
           )
           cassette_corpus_digest = _compose_cassette_corpus_digest(cassette_root)  # AC-20b
           run_id = _compose_run_id(
               task_class_name, sut_digest, rubric_digest, cassette_corpus_digest, run_started_iso,
           )                                                                # AC-2
           cache_keys = {
               case.case_id: compose_cache_key(CacheKeyInputs(             # AC-6 — HARDENED S2-03 aggregate
                   case_digest=case.case_digest,
                   sut_digest=sut_digest,
                   rubric_digest=rubric_digest,
                   cassette_corpus_digest=cassette_corpus_digest,
                   harness_version=harness_version,
                   cassette_canary_pin=case.cassette_canary_pin,
               ))
               for case in cases
           }
           plan = RunPlan(
               task_class=task_class, cases=cases,
               sut_digest=sut_digest, rubric_digest=rubric_digest,
               cassette_corpus_digest=cassette_corpus_digest,
               harness_version=harness_version, run_id=run_id,
               prev_chain_head=prev_chain_head, cache_keys=cache_keys,
           )                                                                # AC-1a __post_init__ enforces invariant
           _log.info("runner.plan_complete", run_id=plan.run_id, n_cases=len(plan.cases),
                     prev_chain_head_short=plan.prev_chain_head[:16],
                     sut_digest_short=plan.sut_digest[:16],
                     rubric_digest_short=plan.rubric_digest[:16])           # AC-22
           return plan
   ```

7. **Import convention (F-TQ-3 / AC-9):** `runner.py` imports MODULES, not symbols — `from codegenie.eval import audit, cache, loader` and `from codegenie.eval.cache import compose_cache_key, CacheKey, CacheKeyInputs`. This way tests can patch sinks at `codegenie.eval.cache.put` / `codegenie.eval.audit.write_run_record` and the patch takes effect at the runner's call site. Document this convention as a comment at the top of `runner.py`.

## TDD plan — red / green / refactor

### Red — write failing tests first

Two new helper modules first:

**`tests/helpers/bench.py`:**
```python
from __future__ import annotations
from pathlib import Path

def stub_task_class_fixture(tmp_path: Path, *, n_cases: int = 3) -> Path:
    """Scaffold a deterministic n-case bench rooted under tmp_path / 'bench'.

    Returns the bench_root path. The fixture writes:
      bench/stub-task-class/registration.py        (registers 'stub-task-class')
      bench/stub-task-class/rubric.py              (deterministic content)
      bench/stub-task-class/breakdown_keys.py      (StrEnum with one key)
      bench/stub-task-class/failure_modes.yaml     (one block-severity code)
      bench/stub-task-class/cases/001-a/case.toml  (+input/, +expected/)
      bench/stub-task-class/cases/002-b/...
      bench/stub-task-class/cases/003-c/...
      bench/stub-task-class/cases/digests.yaml     (correct BLAKE3 for the three case dirs)
    Bytes are deterministic — two calls with the same n_cases produce byte-identical trees.
    """
    ...  # implementation per S2-02 fixture conventions
```

**`tests/helpers/chain.py`:**
```python
from pathlib import Path
from codegenie.eval.audit import write_run_record
from codegenie.eval.models import BenchRunReport
from codegenie.hashing import GENESIS_PREV_HASH

def seed_clean_chain(out_dir: Path, *, n: int = 1) -> list[Path]:
    """Write n valid chained BenchRunReports to out_dir. Returns the written paths."""
    ...

def tamper_last_record(out_dir: Path) -> Path:
    """Mutate the lexicographically-greatest *.json by flipping one byte in `run_id`
    (preserves JSON shape; HARDENED S2-04 AC-7 pattern)."""
    ...
```

**Test file: `tests/unit/eval/test_runner_plan.py`:**

```python
from __future__ import annotations
import dataclasses
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from hypothesis import given, strategies as st, settings

from codegenie.eval.errors import (
    ChainTamperDetected, BenchCaseDigestMismatch, BenchCaseIDCollision,
    TaskClassNotFound,
)
from codegenie.eval.registry import TaskClassRegistry
from codegenie.eval.runner import Runner, RunPlan, _compose_rubric_digest, _compose_run_id, _compose_cassette_corpus_digest
from codegenie.eval.cache import compose_cache_key, CacheKey, CacheKeyInputs
from codegenie.hashing import (
    GENESIS_PREV_HASH, content_hash_bytes, content_hash_tree,
    identity_hash, chain_identity,
)
from codegenie.types.identifiers import RunId

from tests.helpers.bench import stub_task_class_fixture
from tests.helpers.chain import seed_clean_chain, tamper_last_record


# ------------------------------------------------------------------------ helpers

def _stable_plan_args(tmp_path: Path) -> dict[str, object]:
    """Concrete fixture: 3-case stub bench + empty chain + cassette root."""
    bench_root = stub_task_class_fixture(tmp_path)
    cassette_root = tmp_path / "cassettes"
    cassette_root.mkdir()
    (cassette_root / "cassette-a.json").write_bytes(b'{"id":"a"}')
    out_dir = tmp_path / ".codegenie" / "eval"
    return dict(
        task_class_name="stub-task-class",
        sut_digest_fn=lambda: "blake3:" + "a" * 64,
        bench_root=bench_root,
        out_dir=out_dir,
        run_started_iso="2026-05-27T00:00:00Z",
        cassette_root=cassette_root,
        harness_version="0.6.5",
        registry=TaskClassRegistry(),  # AC-21 — fresh registry per call
    )


# ------------------------------------------------------------------------ AC-4: tamper aborts first

def test_plan_aborts_on_chain_tamper_before_load_task_class(tmp_path):
    args = _stable_plan_args(tmp_path)
    out_dir = args["out_dir"]
    out_dir.mkdir(parents=True)
    seed_clean_chain(out_dir, n=2)
    tampered_path = tamper_last_record(out_dir)

    # Wrap load_task_class to detect any call
    import codegenie.eval.loader as loader_mod
    loader_mod.load_task_class = MagicMock(side_effect=lambda *a, **kw: pytest.fail("load_task_class must not be called when chain is tampered"))

    with pytest.raises(ChainTamperDetected) as ei:
        Runner().plan(**args)

    # Positional-args discipline (S1-01 / S2-04 marker-only Exception); no .file_path access
    assert ei.value.args[0] == str(tampered_path)
    assert "verify-not-ok" in ei.value.args[1] or "content_hash" in ei.value.args[1]


# ------------------------------------------------------------------------ AC-7: TaskClassNotFound propagates

def test_plan_task_class_not_found_propagates(tmp_path):
    args = _stable_plan_args(tmp_path)
    args["task_class_name"] = "nonexistent-task-class"
    with pytest.raises(TaskClassNotFound) as ei:
        Runner().plan(**args)
    assert ei.value.name == "nonexistent-task-class"


# ------------------------------------------------------------------------ AC-15/16: digest mismatch + collision propagate; AC-18: sut_digest_fn not called

def test_plan_digest_mismatch_propagates_and_sut_digest_fn_not_called(tmp_path):
    args = _stable_plan_args(tmp_path)
    # Poison one case: append a byte to its expected/ file without updating digests.yaml
    bench_root = args["bench_root"]
    poisoned = bench_root / "stub-task-class" / "cases" / "002-b" / "expected" / "out.txt"
    poisoned.write_bytes(poisoned.read_bytes() + b"X")

    args["sut_digest_fn"] = MagicMock(side_effect=lambda: pytest.fail("must not be called when load_cases raises"))

    with pytest.raises(BenchCaseDigestMismatch) as ei:
        Runner().plan(**args)
    assert ei.value.case_id == "002-b"
    args["sut_digest_fn"].assert_not_called()


# ------------------------------------------------------------------------ AC-2 / AC-3 / AC-3a: run_id derivation + determinism

def test_plan_run_id_matches_oracle(tmp_path):
    args = _stable_plan_args(tmp_path)
    plan = Runner().plan(**args)
    # Independently compute expected run_id via the same primitive the impl is required to use
    expected = _compose_run_id(
        task_class_name="stub-task-class",
        sut_digest=plan.sut_digest,
        rubric_digest=plan.rubric_digest,
        cassette_corpus_digest=plan.cassette_corpus_digest,
        run_started_iso=args["run_started_iso"],
    )
    assert plan.run_id == expected
    assert isinstance(plan.run_id, str) and len(plan.run_id) == 16
    assert all(c in "0123456789abcdef" for c in plan.run_id)


def test_plan_byte_identical_across_two_calls(tmp_path):
    plan_a = Runner().plan(**_stable_plan_args(tmp_path))
    plan_b = Runner().plan(**_stable_plan_args(tmp_path))
    assert json.dumps(dataclasses.asdict(plan_a), default=str, sort_keys=True) == \
           json.dumps(dataclasses.asdict(plan_b), default=str, sort_keys=True)


@given(seed=st.integers(min_value=0, max_value=10_000))
@settings(max_examples=20, deadline=None)
def test_plan_determinism_property(seed, tmp_path_factory):
    """Hypothesis sweep — varying tmp_path realizations, identical conceptual inputs → byte-identical plan."""
    tmp_a = tmp_path_factory.mktemp(f"a_{seed}")
    tmp_b = tmp_path_factory.mktemp(f"b_{seed}")
    args_a = _stable_plan_args(tmp_a)
    args_b = _stable_plan_args(tmp_b)
    # Cache_keys depend on bench-case digests which depend on the file bytes; the fixture is byte-deterministic.
    plan_a = Runner().plan(**args_a)
    plan_b = Runner().plan(**args_b)
    # Compare structural-only fields (skip absolute paths)
    assert plan_a.run_id == plan_b.run_id
    assert plan_a.rubric_digest == plan_b.rubric_digest
    assert plan_a.cassette_corpus_digest == plan_b.cassette_corpus_digest
    assert plan_a.cache_keys == plan_b.cache_keys


# ------------------------------------------------------------------------ AC-5 / AC-5a / AC-5b: rubric digest is boundary-safe + parametrized mutation

@pytest.mark.parametrize("filename", ["rubric.py", "breakdown_keys.py", "failure_modes.yaml"])
def test_rubric_digest_flips_on_one_byte_edit_to_any_of_three_files(tmp_path, filename):
    args = _stable_plan_args(tmp_path)
    digest_before = Runner().plan(**args).rubric_digest
    target = args["bench_root"] / "stub-task-class" / filename
    target.write_bytes(target.read_bytes() + b"\n")
    digest_after = Runner().plan(**args).rubric_digest
    assert digest_before != digest_after


def test_rubric_digest_edit_invalidates_every_cache_key(tmp_path):
    args = _stable_plan_args(tmp_path)
    plan_a = Runner().plan(**args)
    rubric_py = args["bench_root"] / "stub-task-class" / "rubric.py"
    rubric_py.write_bytes(rubric_py.read_bytes() + b"\n# edit\n")
    plan_b = Runner().plan(**args)
    assert set(plan_a.cache_keys.values()).isdisjoint(set(plan_b.cache_keys.values()))


# ------------------------------------------------------------------------ AC-6 / AC-6a: cache_key uses HARDENED S2-03 aggregate + positional-swap mutation

def test_plan_cache_keys_match_compose_cache_key(tmp_path):
    args = _stable_plan_args(tmp_path)
    plan = Runner().plan(**args)
    for case in plan.cases:
        expected = compose_cache_key(CacheKeyInputs(
            case_digest=case.case_digest,
            sut_digest=plan.sut_digest,
            rubric_digest=plan.rubric_digest,
            cassette_corpus_digest=plan.cassette_corpus_digest,
            harness_version=plan.harness_version,
            cassette_canary_pin=case.cassette_canary_pin,
        ))
        assert plan.cache_keys[case.case_id] == expected
        assert isinstance(plan.cache_keys[case.case_id], str)  # CacheKey is NewType[str]


def test_plan_swapping_sut_and_rubric_digests_changes_cache_keys(tmp_path):
    """Mutation guard at the plan layer: plan must put each input in its CacheKeyInputs slot."""
    args = _stable_plan_args(tmp_path)
    plan_normal = Runner().plan(**args)
    # Compose with the two digests swapped via a separate compose_cache_key call (oracle)
    for case in plan_normal.cases:
        swapped = compose_cache_key(CacheKeyInputs(
            case_digest=case.case_digest,
            sut_digest=plan_normal.rubric_digest,   # swap
            rubric_digest=plan_normal.sut_digest,   # swap
            cassette_corpus_digest=plan_normal.cassette_corpus_digest,
            harness_version=plan_normal.harness_version,
            cassette_canary_pin=case.cassette_canary_pin,
        ))
        assert plan_normal.cache_keys[case.case_id] != swapped


# ------------------------------------------------------------------------ AC-19 / AC-14: read_chain_head + happy-path

def test_read_chain_head_returns_genesis_for_empty_chain(tmp_path):
    from codegenie.eval.audit import read_chain_head
    assert read_chain_head(tmp_path / "does-not-exist") == GENESIS_PREV_HASH


def test_plan_prev_chain_head_matches_post_genesis_oracle(tmp_path):
    args = _stable_plan_args(tmp_path)
    out_dir = args["out_dir"]
    out_dir.mkdir(parents=True)
    [r1_path] = seed_clean_chain(out_dir, n=1)
    # Oracle: parse r1, recompute its identity hash
    r1_data = json.loads(r1_path.read_text())
    r1_data["chain_head"] = ""
    canonical = json.dumps(r1_data, sort_keys=True, separators=(",", ":")).encode()
    expected_head = chain_identity(GENESIS_PREV_HASH, content_hash_bytes(canonical))
    plan = Runner().plan(**args)
    assert plan.prev_chain_head == expected_head


# ------------------------------------------------------------------------ AC-1a: __post_init__ invariant

def test_runplan_rejects_mismatched_cache_keys_and_cases():
    from tests.helpers.bench import _stub_bench_case  # tiny BenchCase factory for unit-shape tests
    case = _stub_bench_case(case_id="001-a")
    with pytest.raises(ValueError, match="cache_keys/cases mismatch"):
        RunPlan(
            task_class=...,  # placeholder; the invariant fires before any other field is read
            cases=(case,),
            sut_digest="blake3:" + "0" * 64, rubric_digest="blake3:" + "1" * 64,
            cassette_corpus_digest="blake3:" + "2" * 64,
            harness_version="0.6.5", run_id=RunId("0" * 16),
            prev_chain_head=GENESIS_PREV_HASH,
            cache_keys={"WRONG-CASE-ID": CacheKey("blake3:" + "3" * 64)},
        )


# ------------------------------------------------------------------------ AC-9 / AC-9a: purity + ordered call log

def test_plan_does_not_invoke_sut_or_cache_or_audit_write(monkeypatch, tmp_path):
    monkeypatch.setattr("codegenie.eval.cache.put",
                        lambda *a, **kw: pytest.fail("cache.put must not be called"))
    monkeypatch.setattr("codegenie.eval.audit.write_run_record",
                        lambda *a, **kw: pytest.fail("audit.write_run_record must not be called"))
    plan = Runner().plan(**_stable_plan_args(tmp_path))
    assert plan.run_id  # smoke


def test_plan_call_order_matches_canonical_abort_sequence(tmp_path):
    """AC-9a — strongest purity guard: track call order with MagicMock(wraps=...)."""
    import codegenie.eval.audit as audit_mod
    import codegenie.eval.loader as loader_mod

    call_log: list[str] = []
    real_verify = audit_mod.verify
    real_read_head = audit_mod.read_chain_head
    real_load_tc = loader_mod.load_task_class
    real_load_cases = loader_mod.load_cases

    audit_mod.verify = lambda *a, **kw: (call_log.append("verify"), real_verify(*a, **kw))[1]
    audit_mod.read_chain_head = lambda *a, **kw: (call_log.append("read_chain_head"), real_read_head(*a, **kw))[1]
    loader_mod.load_task_class = lambda *a, **kw: (call_log.append("load_task_class"), real_load_tc(*a, **kw))[1]
    loader_mod.load_cases = lambda *a, **kw: (call_log.append("load_cases"), real_load_cases(*a, **kw))[1]

    args = _stable_plan_args(tmp_path)
    args["sut_digest_fn"] = lambda: (call_log.append("sut_digest_fn"), "blake3:" + "a" * 64)[1]

    Runner().plan(**args)

    assert call_log == ["verify", "read_chain_head", "load_task_class", "load_cases", "sut_digest_fn"]


# ------------------------------------------------------------------------ AC-12: empty bench

def test_plan_empty_bench_returns_empty_cache_keys(tmp_path):
    args = _stable_plan_args(tmp_path)
    # Remove all cases from the stub bench
    cases_dir = args["bench_root"] / "stub-task-class" / "cases"
    for case_dir in cases_dir.iterdir():
        if case_dir.is_dir() and case_dir.name.startswith(("001", "002", "003")):
            import shutil; shutil.rmtree(case_dir)
    # Update digests.yaml to be empty
    (cases_dir / "digests.yaml").write_text("{}\n")
    plan = Runner().plan(**args)
    assert plan.cases == ()
    assert plan.cache_keys == {}
    assert len(plan.run_id) == 16


# ------------------------------------------------------------------------ AC-13: cases sorted by case_id

def test_plan_cases_sorted_by_case_id(tmp_path):
    plan = Runner().plan(**_stable_plan_args(tmp_path))
    ids = [c.case_id for c in plan.cases]
    assert ids == sorted(ids)


# ------------------------------------------------------------------------ AC-17: harness_version validation

@pytest.mark.parametrize("bad", ["", " ", " 1.0", "1.0 ", None, b"1.0", 123])
def test_plan_rejects_malformed_harness_version(tmp_path, bad):
    args = _stable_plan_args(tmp_path)
    args["harness_version"] = bad
    with pytest.raises(TypeError, match="harness_version"):
        Runner().plan(**args)


# ------------------------------------------------------------------------ AC-20 / AC-20a / AC-20b: content_hash_tree direct unit tests

def test_content_hash_tree_deterministic_and_skips_symlinks_by_default(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"alpha")
    (tmp_path / "b.txt").write_bytes(b"beta")
    digest_a = content_hash_tree(tmp_path)
    digest_b = content_hash_tree(tmp_path)
    assert digest_a == digest_b
    assert digest_a.startswith("blake3:")
    # Symlink ignored by default
    (tmp_path / "link.txt").symlink_to(tmp_path / "a.txt")
    digest_with_link = content_hash_tree(tmp_path)
    assert digest_with_link == digest_a


def test_content_hash_tree_in_hashing_all():
    import codegenie.hashing as h
    assert "content_hash_tree" in h.__all__
```

Run all ~16 tests; confirm they fail with `ImportError` / `AttributeError` / `NameError` (no `runner.py`, no `RunId`, no `content_hash_tree`, no `read_chain_head`). Commit as the red marker.

### Green — make them pass

Implement steps 1–7 of the Implementation outline in order. Land all helpers first (Steps 1–3 — newtypes + hashing + audit primitives — each with its own minimal unit tests passing), then `RunPlan` + `Runner.plan` (Steps 4–6), then verify the import convention (Step 7).

### Refactor — clean up

- Docstring on `Runner.plan(...)` enumerates the abort order verbatim: `verify → read_chain_head → load_task_class → load_cases → sut_digest_fn → rubric_digest → cassette_corpus_digest → run_id → cache_keys`.
- Module-level comment on `runner.py` documents the **import-the-module-not-the-symbol** convention (F-TQ-3) so future contributors don't break the mock-target-at-import-site test design.
- `structlog.bind(run_id=...)` once at plan-entry (just before the final `_log.info`); does NOT propagate inside `plan` since `plan` is single-step. S3-02's workers will rebind in their own scope.
- Note `RunnerCollaborators` aggregate as a deferred refactor with a single-sentence trigger: "extract when Phase 9's durable workflow becomes the second consumer of `audit` + `loader` modules from outside this file."

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Add `RunId = NewType("RunId", str)` (mirrors `CacheKey`, `ProbeId`) |
| `src/codegenie/hashing.py` | Add `content_hash_tree(root, *, glob, follow_symlinks)` public helper; extend `__all__` |
| `src/codegenie/eval/audit.py` | Add `read_chain_head(out_dir)` public primitive; extend `__all__` |
| `src/codegenie/eval/runner.py` | NEW MODULE: `RunPlan` frozen dataclass with `__post_init__` invariant; `Runner` class; `Runner.plan(...)`; three pure helpers (`_compose_rubric_digest`, `_compose_cassette_corpus_digest`, `_compose_run_id`); `_validate_harness_version`; `_EVENT_IDS: Final[frozenset[str]]` |
| `tests/unit/eval/test_runner_plan.py` | NEW: all ~16 unit tests above (AC-1..AC-22) |
| `tests/unit/eval/test_content_hash_tree.py` | NEW: focused tests on the `content_hash_tree` helper (AC-20/AC-20a) |
| `tests/unit/eval/test_audit_read_chain_head.py` | NEW: focused tests on the `read_chain_head` primitive (AC-19) |
| `tests/fence/test_runner_plan_invariants.py` | NEW fence: `RunPlan.__post_init__` raises on mismatch; `_EVENT_IDS` validation fires at import |
| `tests/helpers/chain.py` | NEW: `seed_clean_chain`, `tamper_last_record` helpers (shared with S2-04 tests) |
| `tests/helpers/bench.py` | NEW: `stub_task_class_fixture(tmp_path, *, n_cases=3)` helper returning a deterministic bench tree |

## Out of scope

- **Actual fan-out, cache probe, SUT invocation, rubric subprocess** — S3-02 / S3-03 own these.
- **Bootstrap / cost cap / partial reports** — S3-05, S3-06.
- **Genesis-record creation** (the `prev_hash == GENESIS_PREV_HASH` write path) — owned by S2-04; this story just consumes the verified-and-readable API.
- **`RunnerCollaborators` aggregate for DI** — deferred per F-DP-6; rule-of-three not met (only `plan` consumes `audit` + `loader`; Phase 9's durable workflow would be the second). Extraction trigger named in implementer notes.
- **`CaseId` newtype consolidation** — phase-wide deferred (S2-02 line 506, S2-06 F-CON-6 precedent); `cache_keys: Mapping[str, CacheKey]` uses raw `str` for the outer key until the consolidation lands.
- **Wire-contract changes to `BenchRunReport`** — out of scope (HARDENED S1-02 `_FROZEN_WIRE_TYPES` cardinality is unchanged by this story; `RunPlan` is a plan-time aggregate, not a wire type).
- **`audit.read_chain_head` returning a sum type** (`ChainEmpty()` | `ChainHead(identity, path)`) — surfaced in S2-04 as deferred (rule-of-three not met); plan consumes the `str` shape returned by the shim.

## Notes for the implementer

- **`ChainTamperDetected` is marker-only (S1-01 AC-8 + HARDENED S2-04 F-CON-1).** It has no custom `__init__`. Construct positionally — `raise ChainTamperDetected(path_str, reason_str, "")` — and assert via `ei.value.args`. **Do not** use kwargs and **do not** access fictitious `.file_path` / `.expected_prev` attributes. If a future story decides this loss of named-attribute access is too painful, the correct path is a Phase 6.5 ADR amendment that widens S1-01 to permit a custom `__init__` on selected subclasses — not a silent edit here.
- **Mock-target-at-import-site discipline (F-TQ-3).** `runner.py` MUST `from codegenie.eval import audit, cache, loader` (modules), not `from codegenie.eval.audit import verify, write_run_record` (symbols). Otherwise `monkeypatch.setattr("codegenie.eval.cache.put", ...)` silently misses because the patched name is no longer the one `runner.py` resolves at call time. Document this convention with a one-line comment at the top of `runner.py`.
- **`Runner` as a class** is justified by the arch design: this story owns phase 1 of a 6-phase orchestrator; S3-02 through S3-06 will land the other methods on the same class. The class is not gratuitous — it will gain state (the `asyncio.Semaphore`, the queue, the cost-cap counter) in those stories.
- **Abort order is load-bearing.** Tamper > digest mismatch > unknown task class > missing rubric. The poisoned-chain failure is the only one where the rest of the run is meaningless; all the others are partial-recovery surfaces (the curator re-curates one case and reruns; they cannot recover from a tampered chain by partial re-run).
- **`sut_digest_fn` is the injected seam.** Phase 6's `build_vuln_loop` will inject a digest provider that hashes the SUT subgraph; tests inject a constant string. Do not couple the runner to Phase 6 directly — the runner has no `from codegenie.engines.vuln_loop import ...` import.
- **`harness_version` is `codegenie.__version__`**, not the git SHA. The git SHA is mutable across the same release; the package version is the stable contract. The S4-02 CLI passes it explicitly; tests pass `"0.6.5"` explicitly to stay immune to package-version bumps.
- **`isolation_class` lives on the *report*, not the *cache_key*.** Including it in the cache key would invalidate the cache on every Phase 16 microVM rollout — wrong cardinality. ADR-0010 says the field is "structural foresight"; the cache key cares about the bytes-of-the-rubric, not the process-model-used-to-run-it. The structural guard is mechanical: `CacheKeyInputs` (HARDENED S2-03) has no `isolation_class` field — adding it would require an explicit edit there, which would be loudly visible.
- **`run_id[:16]` truncation matters for ADR-0002** (`int(run_id[:8], 16)` → bootstrap seed). 16 hex chars = 64 bits = plenty of entropy for the seed and the audit filename short.
- **Boundary-safe composition is non-negotiable.** Bare `BLAKE3(a || b || c)` of arbitrary user-provided strings is boundary-shift-unsafe. Always compose through `identity_hash(*parts)` (arity byte + UNIT_SEP) or `tree_digest_of_files` (length-prefixed records). This story's two compositions (`_compose_run_id` and `_compose_rubric_digest`) both consume the canonical primitives.
- **`RunnerCollaborators` aggregate trigger condition.** When Phase 9's durable workflow lands and imports `codegenie.eval.audit` for its event-log append, the rule-of-three is met. At that point, extract `@dataclass(frozen=True) class RunnerCollaborators(audit, loader, cache, hashing)`, accept it as a `plan(..., collaborators=...)` kwarg, and migrate the existing tests to inject spies via the aggregate (kills the F-TQ-3 import-site-patch convention as obsolete). Until then: import-the-module-not-the-symbol is the cheaper convention.
- **`CaseId` newtype is deferred phase-wide** (S2-02 line 506 precedent). When the consolidation story lands, `cache_keys: Mapping[str, CacheKey]` becomes `cache_keys: Mapping[CaseId, CacheKey]`. Today: raw `str` is conformant with the rest of Phase 6.5.
- **`audit.read_chain_head` is the new public seam** (AC-19). Phase 9's Temporal-durable event log is the documented second consumer. Until Phase 9 lands, the shim is a single thin wrapper over S2-04's private `_current_head` — but exposing it publicly NOW means Phase 9 lands by addition, not by editing.
