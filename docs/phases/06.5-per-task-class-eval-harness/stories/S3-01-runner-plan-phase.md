# Story S3-01 — Runner plan phase: load + digest + cache-key compute

**Step:** Step 3 — Implement the runner: asyncio fan-out, subprocess rubric, aggregator with BCa bootstrap
**Status:** Ready
**Effort:** M
**Depends on:** S2-02 (loader + digests), S2-04 (audit chain extension)
**ADRs honored:** ADR-0001 (subprocess isolation — informs the digest set), ADR-0002 (lower_bound_95 — informs `run_id` derivation), ADR-0010 (isolation_class annotation — `RunPlan` carries it forward to the report)

## Context

The runner's first phase is pure planning: load the task class, verify the audit chain at startup, compute the three deterministic digests (`sut_digest`, `rubric_digest`, `cassette_corpus_digest`), derive per-case `cache_key`s, and abort *before* any SUT invocation if anything is wrong. This is the load-bearing gate that prevents poisoned cases or a tampered chain from contaminating a run.

The plan output is a plain dataclass consumed by S3-02's fan-out. Plan is **pure** — no SUT calls, no rubric subprocess, no cache writes. Plan's invariant is "abort early, abort loud" (CLAUDE.md "Fail loud"): if the chain is tampered or any case digest mismatches, no new state is created and exit code 5 (tamper) or 6 (digest mismatch) propagates to the CLI.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Process view` — the six-phase pipeline diagram; this story owns phases 1 (plan) and the integrity check at startup.
  - `../phase-arch-design.md §Components → runner.py` — `run_eval` six-phase internal structure; this story is phase 1 only.
  - `../phase-arch-design.md §Control flow → Happy path (cold cache, vuln-remediation, 10 cases)` — sequencing of `audit.verify` → `loader.load_task_class` → `loader.load_cases` → digest computation → per-case `cache_key`.
  - `../phase-arch-design.md §Control flow → Decision points #5 (audit chain tamper)` and `#6 (bench-case digest mismatch)` — both abort before any SUT invocation; exit codes 5 and 6.
  - `../phase-arch-design.md §Edge cases #11` — tamper detected at startup → exit code 5; no new record written.
  - `../phase-arch-design.md §Components → cache.py` — composition rule for `cache_key`: `BLAKE3(case_digest || sut_digest || rubric_digest || cassette_corpus_digest || harness_version || cassette_canary_pin)`.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md` — the rubric subprocess shape is what makes `rubric_digest` a single artifact (rubric.py + breakdown_keys.py + failure_modes.yaml).
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md` — `run_id` derives a deterministic bootstrap seed (`int(run_id[:8], 16)`); plan must produce a content-addressed `run_id` for that downstream contract to hold.
  - `../ADRs/0010-isolation-class-annotation-on-bench-run-report.md` — `isolation_class` is a *report* field, not a *cache_key* component; plan documents this distinction explicitly.
- **Production ADRs:** `../../../production/adrs/0009-humans-always-merge.md` — audit chain is hard gate; tamper aborts before any new state.
- **Source design:** `../final-design.md §Components → runner.py`, `§Synthesis ledger row "Concurrency knob source"`.

## Goal

Land `Runner.plan(task_class_name, *, sut_digest_fn, bench_root, out_dir, run_started_iso, cassette_root, harness_version) -> RunPlan` that resolves the task class, verifies the audit chain, computes the three digests, derives per-case cache keys, and aborts on digest mismatch or chain tamper *before* any SUT call.

## Acceptance criteria

- [ ] `RunPlan` is a `@dataclass(frozen=True, slots=True)` in `src/codegenie/eval/runner.py` carrying: `task_class: TaskClass`, `cases: tuple[BenchCase, ...]` (sorted by `case_id`), `sut_digest: str`, `rubric_digest: str`, `cassette_corpus_digest: str`, `harness_version: str`, `run_id: str`, `prev_chain_head: str`, `cache_keys: Mapping[str, str]`, `isolation_class: Literal["subprocess"] = "subprocess"`.
- [ ] `run_id` is content-addressed: `BLAKE3(task_class || sut_digest || rubric_digest || cassette_corpus_digest || run_started_iso)[:16]` (32 hex chars truncated to 16 — enough entropy for the bootstrap seed and the per-run filename short).
- [ ] Two `plan(...)` calls with identical inputs produce byte-identical `RunPlan` (asserted via `dataclasses.asdict` + JSON-serialize comparison) — load-bearing for ADR-0002's deterministic bootstrap seed.
- [ ] **Abort order is enforced**: `audit.verify(out_dir).ok is False` raises `ChainTamperDetected` **before** `loader.load_task_class` runs; `BenchCaseDigestMismatch` from `loader.load_cases` propagates **before** any digest computation.
- [ ] `rubric_digest = BLAKE3(rubric.py || breakdown_keys.py || failure_modes.yaml)` (files concatenated in sorted-by-name order); a one-byte edit to any of the three flips the digest and invalidates every per-case `cache_key` (asserted by a property test).
- [ ] Per-case `cache_key = BLAKE3(case_digest || sut_digest || rubric_digest || cassette_corpus_digest || harness_version || cassette_canary_pin)` — matches S2-03's composition rule exactly (asserted via shared helper test).
- [ ] `TaskClassNotFound(name, available_names)` raised when the task class is not registered after `loader.load_task_class` runs (exit code 3).
- [ ] `isolation_class` is **not** part of `cache_key` — documented in a code comment citing ADR-0010 §"`isolation_class` is structural, not a runtime measurement"; a regression test asserts the comment exists.
- [ ] `plan(...)` performs no SUT call, no rubric subprocess, no cache `put`, no audit `write_run_record` — asserted by a test using `unittest.mock.patch` to fail loudly if any is called.
- [ ] `mypy --strict`, `ruff format --check`, `ruff check` clean on touched files.
- [ ] All red tests in §TDD plan exist, were committed at the red marker, and are now green.

## Implementation outline

1. Add `RunPlan` `@dataclass(frozen=True, slots=True)` to `src/codegenie/eval/runner.py`.
2. Implement `Runner.plan(...)` with this **exact order** (abort early at each step):
   1. `chain_result = audit.verify(out_dir)`; if `not chain_result.ok` → raise `ChainTamperDetected(...)` (no other work performed).
   2. `prev_chain_head = chain_result.head` (genesis = `"0" * 64` per S2-04).
   3. `task_class = loader.load_task_class(name, bench_root)` (raises `TaskClassNotFound` on miss).
   4. `cases = loader.load_cases(task_class)` (raises `BenchCaseDigestMismatch`, `BenchCaseIDCollision` on inconsistencies).
   5. `sut_digest = sut_digest_fn()` (injected; Phase 6 supplies a digest provider in production; tests stub).
   6. `rubric_digest = BLAKE3(concat(rubric.py, breakdown_keys.py, failure_modes.yaml))` — explicit sorted-by-filename concat to keep the digest deterministic.
   7. `cassette_corpus_digest = codegenie.hashing.blake3_tree(cassette_root)`.
   8. `run_id = BLAKE3(task_class || sut_digest || rubric_digest || cassette_corpus_digest || run_started_iso)[:16]`.
   9. `cache_keys = {case.case_id: BLAKE3(case.case_digest || sut_digest || rubric_digest || cassette_corpus_digest || harness_version || case.cassette_canary_pin) for case in cases}` — extract the composition into a `_compose_cache_key(...)` module-level helper shared with S2-03.
3. Inject all I/O collaborators as parameters (`sut_digest_fn: Callable[[], str]`, `bench_root: Path`, `out_dir: Path`, `cassette_root: Path`, `harness_version: str`) — no module-level globals.
4. Log a single `INFO` record at `plan_complete` with `{run_id, n_cases, prev_chain_head[:16], sut_digest[:16], rubric_digest[:16]}` via `structlog`. No per-case logs in `plan(...)` (S3-02 owns those).
5. Document the abort-order invariant in the function docstring; cite the three exit codes (3/5/6) it can produce via raised exceptions.

## TDD plan — red / green / refactor

### Red — write failing tests first

Test file path: `tests/unit/test_runner_plan.py`

```python
import dataclasses
import json
import pytest
from codegenie.eval.errors import (
    ChainTamperDetected, BenchCaseDigestMismatch, TaskClassNotFound,
)
from codegenie.eval.runner import Runner, RunPlan
from tests.helpers.chain import seed_clean_chain, tamper_last_record
from tests.helpers.bench import stub_task_class_fixture


def test_plan_aborts_on_chain_tamper_before_any_load(tmp_path, monkeypatch):
    """Tamper is the most severe finding; surface it before any other error."""
    out_dir = tmp_path / ".codegenie" / "eval"
    seed_clean_chain(out_dir, n=2)
    tamper_last_record(out_dir)

    load_calls = []
    monkeypatch.setattr(
        "codegenie.eval.loader.load_task_class",
        lambda *a, **kw: load_calls.append(("load_task_class", a, kw)) or pytest.fail("must not load"),
    )

    runner = Runner()
    with pytest.raises(ChainTamperDetected) as exc:
        runner.plan(
            task_class_name="stub-task-class",
            sut_digest_fn=lambda: "stub_sut_digest_0000000000000000",
            bench_root=stub_task_class_fixture(),
            out_dir=out_dir,
            run_started_iso="2026-05-12T00:00:00Z",
            cassette_root=tmp_path / "cassettes",
            harness_version="0.6.5",
        )
    assert exc.value.file_path.name.startswith("2")  # ISO-prefixed file
    assert load_calls == []  # load_task_class never called


def test_plan_is_byte_identical_across_two_calls_with_identical_inputs():
    """Required for ADR-0002 deterministic bootstrap seed."""
    plan_a = Runner().plan(**_stable_plan_args())
    plan_b = Runner().plan(**_stable_plan_args())

    assert json.dumps(dataclasses.asdict(plan_a), default=str, sort_keys=True) == \
           json.dumps(dataclasses.asdict(plan_b), default=str, sort_keys=True)


def test_plan_run_id_is_16_hex_chars_of_blake3():
    plan = Runner().plan(**_stable_plan_args())
    assert len(plan.run_id) == 16
    assert all(c in "0123456789abcdef" for c in plan.run_id)


def test_plan_rubric_digest_flips_on_one_byte_edit_to_breakdown_keys(tmp_path):
    """Any edit to rubric.py / breakdown_keys.py / failure_modes.yaml invalidates the digest."""
    args = _stable_plan_args(bench_root=tmp_path)
    digest_before = Runner().plan(**args).rubric_digest
    breakdown = (tmp_path / "stub-task-class" / "breakdown_keys.py")
    breakdown.write_text(breakdown.read_text() + "\n# touch\n")
    digest_after = Runner().plan(**args).rubric_digest
    assert digest_before != digest_after


def test_plan_cache_keys_match_s2_03_composition():
    """The cache_key formula must match S2-03's BLAKE3 composition exactly."""
    from codegenie.eval.cache import compose_cache_key  # shared helper
    plan = Runner().plan(**_stable_plan_args())
    for case in plan.cases:
        expected = compose_cache_key(
            case_digest=case.case_digest,
            sut_digest=plan.sut_digest,
            rubric_digest=plan.rubric_digest,
            cassette_corpus_digest=plan.cassette_corpus_digest,
            harness_version=plan.harness_version,
            cassette_canary_pin=case.cassette_canary_pin,
        )
        assert plan.cache_keys[case.case_id] == expected


def test_plan_does_not_invoke_sut_or_cache_or_audit_write(monkeypatch):
    """Plan is pure. SUT, cache, and audit-write are S3-02/S3-03/S3-06 responsibilities."""
    monkeypatch.setattr("codegenie.eval.cache.put", lambda *a, **kw: pytest.fail("cache.put must not be called"))
    monkeypatch.setattr("codegenie.eval.audit.write_run_record", lambda *a, **kw: pytest.fail("audit.write must not be called"))
    plan = Runner().plan(**_stable_plan_args())
    assert plan.run_id  # smoke
```

Run all six tests; confirm five fail with `ImportError` or `AttributeError` and one (the helper test) fails with `ModuleNotFoundError`. Commit as the red marker.

### Green — make them pass

Smallest implementation: `RunPlan` dataclass + synchronous `Runner.plan(...)` doing the nine-step order above. Inject all I/O. Extract `compose_cache_key(...)` to `codegenie/eval/cache.py` (S2-03 will already host it; this story confirms the import).

### Refactor — clean up

- Docstring on `plan(...)` enumerates the abort order: verify → load_task_class → load_cases → digest_sut → digest_rubric → digest_cassettes → derive run_id → derive cache_keys.
- Module-level comment near `cache_keys` computation cites `ADR-0010 §"the value is structural, not a runtime measurement"` and explains why `isolation_class` is on the *report*, not the *cache key*.
- `structlog.bind(run_id=...)` once at plan entry; the bound context propagates through S3-02's workers when they call `log.info(...)`.
- `harness_version` defaults to `codegenie.__version__` if not injected — but the test always passes it explicitly to keep tests immune to package-version bumps.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/runner.py` | New module: `RunPlan` dataclass + `Runner.plan` |
| `tests/unit/test_runner_plan.py` | New tests: tamper-abort, digest determinism, missing-task-class, cache-key composition, purity |
| `tests/helpers/chain.py` | Helpers `seed_clean_chain`, `tamper_last_record` shared with S2-04 tests |
| `tests/helpers/bench.py` | Helper `stub_task_class_fixture()` returning the path from S2-02's fixture tree |
| `src/codegenie/eval/cache.py` | (May already exist from S2-03) — confirm `compose_cache_key(...)` is importable |

## Out of scope

- Actual fan-out, cache probe, SUT invocation — S3-02.
- Subprocess rubric invocation — S3-03.
- Bootstrap / cost cap / partial reports — S3-05, S3-06.
- The genesis-record case (`prev_hash == "0" * 64`) — owned by S2-04; this story just calls into the verified API.

## Notes for the implementer

- **Abort order is load-bearing.** Tamper > digest mismatch > unknown task class. A poisoned chain is the only failure where the rest of the run is meaningless; the rest are partial-recovery surfaces (the curator re-curates one case and reruns; they cannot recover from a tampered chain by partial re-run).
- The `sut_digest_fn` callable is the seam: Phase 6's `build_vuln_loop` will inject a digest provider; tests inject a constant. Do not couple the runner to Phase 6 directly — the runner has no `from codegenie.engines.vuln_loop import ...` import.
- `harness_version` is `codegenie.__version__` — not the git SHA. The git SHA is mutable across the same release; the package version is the stable contract.
- Do not compute `chain_head` here — that's the *post-run* append's output (S3-06 owns the write). `prev_chain_head` is the input.
- `isolation_class` lives on the *report*, not the *cache_key*. Including it in the cache key would invalidate the cache on every Phase 16 microVM rollout — wrong cardinality. ADR-0010 says the field is "structural foresight"; the cache key cares about the bytes-of-the-rubric, not the process-model-used-to-run-it.
- Resist the urge to call the cache here. Plan is pure; cache probe is S3-02's responsibility. The test that fails loudly on `cache.put`/`audit.write_run_record` is your guardrail.
- The `run_id[:16]` truncation matters for ADR-0002 (`int(run_id[:8], 16)` → bootstrap seed). 16 hex chars = 64 bits = plenty of entropy for the seed and the audit filename short.
