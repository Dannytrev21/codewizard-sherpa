# Validation report — S7-02 (end-to-end audit-chain integration + golden snapshots)

**Validated:** 2026-07-26
**Validator:** scheduled `story-validation-corrector` task
**Story:** `docs/phases/06.5-per-task-class-eval-harness/stories/S7-02-audit-chain-integration-and-snapshots.md`
**Verdict:** HARDENED
**Findings:** 19 total — 4 blocks, 12 hardens, 3 nits

## Stage 1 — Context loaded

Read in this order:

- `S7-02-audit-chain-integration-and-snapshots.md` (target)
- `phase-arch-design.md` §Component design → `audit.py`, §Testing strategy → Integration → `test_audit_chain_extension.py`, §Golden files, §Scenarios → Scenario 4
- `phase-arch-design.md` §Components → `runner.py` (`run_eval` six-phase internal structure)
- `ADRs/0010-isolation-class-annotation-on-bench-run-report.md` — the `isolation_class` field default the snapshot must carry
- `ADRs/0002-promotion-gate-keys-on-lower-bound-95.md` — `mean_score`, `score_stddev`, `lower_bound_95` all-on-wire discipline
- `stories/S1-01-typed-errors-module.md` (HARDENED) — `ChainTamperDetected` marker-only shape (irrelevant to this story except for shared context)
- `stories/S1-02-wire-models-frozen-extra-forbid.md` (HARDENED) — `_FROZEN_WIRE_TYPES` cardinality; `BenchRunReport` field surface
- `stories/S2-04-audit-chain-extension.md` (HARDENED) — **the load-bearing dependency.** Confirms `verify(out_dir: Path, since: str | None = None) -> VerifyResult` (not the story's `audit_verify(runs_dir)` call), `GENESIS_PREV_HASH`, `chain_identity`, the on-disk file layout at `.codegenie/eval/runs/<lex-sorted>.json`, the report-IS-the-record design (there is no separate "audit record wrapper" file — the BenchRunReport JSON that lands on disk *is* the chain record).
- `stories/S3-01-runner-plan-phase.md` (HARDENED) — pins `Runner().plan(task_class_name, *, sut_digest_fn, bench_root, out_dir, run_started_iso, cassette_root, harness_version, registry=None) -> RunPlan` and `stub_task_class_fixture(tmp_path)` under `tests/helpers/bench.py`; also confirms `run_id` derivation is fully content-addressed off inputs (no wall-clock, no uuid).
- `stories/S3-02-asyncio-fan-out-and-aggregator.md` (HARDENED) — pins `Runner.execute(plan, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds, concurrency=None, on_score=None) -> BenchRunReport` (audit-write-free); the `JitteredStubSUT.zero()` deterministic stub SUT + `make_stub_plan(tmp_path)` helper.
- `stories/S3-06-cost-cap-and-partial-reports.md` (HARDENED) — pins `Runner().run_eval(plan, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds, concurrency=None, on_score=None, max_cost_usd: float = 5.0, out_dir: Path) -> BenchRunReport` as the audit-writing composition root. The returned report has `chain_head` already stamped via `model_copy(update={"chain_head": head})`.
- `stories/S3-05-deterministic-bca-bootstrap.md` (HARDENED) — snapshot + `scripts/regen_bootstrap_snapshot.py` precedent for the drift/regen ergonomic.
- `stories/S4-02-eval-run-subcommand.md` (HARDENED) — F-CON-2 in that story is the *identical* runner-API mismatch this validator now flags in S7-02 (S4-02 was already caught; S7-02 was written the same wrong way).

**Context Brief:**

S7-02 is the end-to-end integration test that three consecutive `Runner().run_eval(...)` calls extend the S2-04 audit chain to length 3 with `verify().ok is True`; it also freezes the byte-shape of the on-disk `BenchRunReport` JSON as a golden snapshot so downstream Phase 7 / Phase 11 / Phase 13 readers cannot be silently invalidated by drift. The intent is right. But the story as-written invokes a `run_eval` signature that does not exist in any hardened dependency: `run_eval(task_class_name=..., bench_root=..., frozen_time=...)` — a shape S4-02 already had to correct via F-CON-2. The hardened flow is stateful-Runner-free but two-call: `plan = Runner().plan(...)`; `report = asyncio.run(Runner().run_eval(plan, ...))`. Time-freezing happens via `plan(run_started_iso="1970-01-01T00:00:00+00:00")`, not a `frozen_time` kwarg. The fixture path `tests/fixtures/bench/stub-task-class/` also does not exist — S3-01 ships `stub_task_class_fixture(tmp_path)` as a runtime helper under `tests/helpers/bench.py`.

Four structural blockers, plus a set of coverage / test-quality / design hardenings. Verdict is HARDENED (not RESCUE) because the *goal* is sound and the fixes are mechanical translations against the hardened runner contract.

## Stage 2 — Critic findings

### Coverage critic

| ID | Severity | Finding | Fix |
|---|---|---|---|
| F-COV-1 | harden | `isolation_class` is called out in AC-4 but no AC asserts the field is *present and equals `"subprocess"`* on the golden snapshot bytes — the drift check only fires if the snapshot changes shape, not if the writer regressed to omit the default. | AC-4 amended: `json.loads(snapshot.read_text())["isolation_class"] == "subprocess"` asserted independently (oracle) — not by trusting `model_dump`. |
| F-COV-2 | harden | No AC covers what happens when the runs dir doesn't exist yet on the very first `run_eval`. S2-04 handles it (creates on write); this story should assert the invariant end-to-end since it is a *load-bearing* precondition for genesis semantics. | New AC-9 — `runs_dir` does not exist before the first call; the first `run_eval` creates it at mode `0o700` and writes the genesis record. |
| F-COV-3 | harden | The three-runs test collides on filename when `run_started_iso` is frozen — the runner derives the on-disk basename from ISO time and `run_id` truncation (S3-01 §Implementation outline), so three runs with identical `run_started_iso` may attempt to write the same path. Determinism *within* a snapshot run is desired; three consecutive runs writing to the same runs dir must NOT collide. | New AC-10 — the runs-dir filename derivation is verified stable across three consecutive frozen-time runs *by threading distinct `run_started_iso` values through the three `plan()` calls* (`"1970-01-01T00:00:00+00:00"`, `"1970-01-01T00:00:01+00:00"`, `"1970-01-01T00:00:02+00:00"`) so the chain of length 3 test does not depend on time-based uniqueness. The snapshot test uses only the *first* record (single-run determinism), keeping the byte-freeze meaningful. |
| F-COV-4 | harden | Tamper-test target ambiguity: AC-3 pins `mean_score` byte-flip, but Notes-for-implementer #5 explicitly recommends flipping `prev_hash` (since `mean_score` invalidates the record's *own* content hash, not the chain link). AC and Notes contradict — the executor cannot follow both. | AC-3 rewritten: pin `prev_hash` as the mutation target (chain-link semantics, matches S2-04's `ChainTamperDetected` raise site). Notes updated to remove the contradiction. |
| F-COV-5 | harden | No AC that `audit.verify(runs_dir).ok is True` **before** any tamper; the story asserts it after but not as a pre-tamper baseline. Without the baseline, a broken chain that was never valid could pass the tamper-detection test vacuously. | AC-3 amended: assert `verify().ok is True` immediately after the three writes, *before* the tamper mutation, then `ok is False` after. |
| F-COV-6 | harden | Two-snapshot ambiguity: AC-4 and AC-5 name two files (`bench_run_report.v1.json`, `eval_run_audit_record.v1.json`), but S2-04's design puts the audit record ID fields (`prev_hash`, `chain_head`, `content_hash`) *inside* the `BenchRunReport` itself. The two snapshot files would carry identical bytes for identical fields. The story does not explain the intended distinction. | AC-4 / AC-5 clarified: `bench_run_report.v1.json` is the **full report byte snapshot** (all fields, including audit-record fields). `eval_run_audit_record.v1.json` is a **schema-only JSON Schema fixture** (property names + types, not values) — the two snapshots detect drift at *different* granularities and can survive independent regen cycles when only value distributions drift. AC-5 explicitly types the second file as JSON Schema (matches the `schema_slice` convention CLAUDE.md pins). If the executor / reviewer decides the schema variant is over-specified, they may collapse to a single snapshot with an ADR amendment; the choice is called out in Notes. |
| F-COV-7 | nit | No AC pins `content_hash` field format (`blake3:<64hex>`). S2-04 pins it in `chain_identity`. | AC-4 amended: snapshot's `content_hash` matches `^blake3:[0-9a-f]{64}$`; snapshot's `chain_head` matches `^sha256:[0-9a-f]{64}$`. Regex-tested independently. |

### Test-Quality critic

| ID | Severity | Finding | Fix |
|---|---|---|---|
| F-TQ-1 | **block** | Every test in the TDD plan calls `run_eval(task_class_name="stub-task-class", bench_root=STUB_BENCH.parent)` — a signature that does not exist. `run_eval` is a `Runner().run_eval(plan, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds, out_dir)` method, and it is not called *directly* against the task class name. The plan must be built first via `Runner().plan(...)`. | Entire TDD plan rewritten against the hardened two-call contract using `make_stub_plan(tmp_path)` (S3-02 helper) + `JitteredStubSUT.zero()` + a `_default_execute_kwargs(tmp_path)` helper that mirrors S3-02's `_default_kwargs`. |
| F-TQ-2 | **block** | The snapshot test uses `run_eval(..., frozen_time="1970-01-01T00:00:00Z")` — `run_eval` has no `frozen_time` kwarg. Determinism must be threaded via `plan(run_started_iso="1970-01-01T00:00:00+00:00")` per S3-01 / S3-02. | Snapshot test rewritten to build `plan` with a frozen `run_started_iso`; pass through `run_eval`. |
| F-TQ-3 | **block** | The fixture path `tests/fixtures/bench/stub-task-class/` referenced as `STUB_BENCH` does not exist — S3-01 ships `stub_task_class_fixture(tmp_path)` as a runtime *helper* under `tests/helpers/bench.py`. The story mis-attributes the location. | TDD plan uses `stub_task_class_fixture(tmp_path)` + `make_stub_plan(tmp_path)` helpers directly. `STUB_BENCH` module-level constant removed. |
| F-TQ-4 | harden | `test_three_run_evals_produce_a_chain_of_length_three` asserts only `len(records) == 3` and `verify().ok is True` — but neither of those pins that the three records are *chain-linked in order*. A wrong implementation that writes three records with `prev_hash = GENESIS_PREV_HASH` on all three but silently patches `chain_head` could still pass `verify().ok` if `verify` is buggy. | AC-1 / AC-2 amended: after three runs, walk the sorted records manually and assert `r2["prev_hash"] == r1["chain_head"]` AND `r3["prev_hash"] == r2["chain_head"]` — recomputed via oracle (`chain_identity(r_prev.prev_hash, content_hash_bytes(canonical(r_prev.model_copy(update={"chain_head": ""}))))`) rather than trusting the on-disk `chain_head`. Mirrors S2-04 AC-6's oracle discipline. |
| F-TQ-5 | harden | `assert_snapshot_byte_identical` compares `fresh.model_dump_json(indent=2)` against the snapshot bytes. Pydantic's `model_dump_json(indent=2)` does **not** sort keys — Notes-for-implementer #7 acknowledges this but the AC does not pin the fix. Executor could implement the helper with an unsorted serializer and the snapshot would drift on the first Pydantic point release. | New AC-11 — the helper canonicalizes via `json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True, separators=(",", ": "))`. Snapshot bytes committed under the same canonicalization. Fence-tested by round-tripping the committed snapshot through the canonicalizer and asserting equality with the committed bytes. |
| F-TQ-6 | harden | The tamper-detection test flips `mean_score` on disk and asserts `verify().ok is False`. `mean_score` breaks the record's *own* `content_hash`, but S2-04's `verify` also checks `prev_hash` linkage — the assertion is under-constrained. A wrong `verify` that never checks content hashes would still pass this test iff it happens to also fail the prev_hash link. | AC-3 amended: the assertion is *specific*: `result.tampered_path == records[1]` AND `result.reason.startswith("content_hash mismatch")` (per S2-04 AC-4's `VerifyResult` shape). This pins WHICH failure mode was detected. |
| F-TQ-7 | harden | No property test / determinism test: two calls to the regen script on the same checkout produce byte-identical snapshots. Without this the "zero diff on regen" AC-6 can be flaky if any nondeterminism sneaks in. | New AC-12 — `scripts/regen_eval_snapshot.py` invoked twice in a row from `tmp_path` produces byte-identical output (Hypothesis-free, just two invocations). |
| F-TQ-8 | nit | AC-6's `--tamper-stub` mode conflates "regenerate for real" and "test the drift diagnostic fires". A future contributor could accidentally invoke `--tamper-stub` and land tampered snapshots. | AC-6 amended: rename `--tamper-stub` to `--dry-run-tamper` and pin that it (a) writes to a `tmp_path` argument, NOT the committed snapshot paths, (b) prints the drift diagnostic to stdout, (c) does not touch `tests/snapshots/`. |

### Consistency critic

| ID | Severity | Finding | Fix |
|---|---|---|---|
| F-CON-1 | (merged into F-TQ-1) | Runner API mismatch — same defect surface. | See F-TQ-1. |
| F-CON-2 | (merged into F-TQ-2) | `frozen_time` kwarg does not exist. | See F-TQ-2. |
| F-CON-3 | harden | `audit_verify` (function-level import from `codegenie.eval.audit`) — S2-04 exports `verify`, not `audit_verify`. Import should be `from codegenie.eval.audit import verify as audit_verify`. Cosmetic but the story shows it wrong. | TDD plan rewritten with the correct import. |
| F-CON-4 | harden | Snapshot file naming: `.v1.json` implies a versioning scheme, but no ADR or story pins what a `v2` transition looks like. Phase 11 / Phase 13 downstream readers will need to know. | New AC-13 — Notes for implementer document the versioning rule: a wire-shape change requires (a) `--dry-run-tamper` diagnostic surfaces first, (b) new file `.v2.json` lands alongside `.v1.json` for one release cycle, (c) ADR amendment in `docs/phases/06.5-per-task-class-eval-harness/ADRs/` naming the removed / added fields. Deletion of `.v1.json` waits until Phase 11's consumer catches up. |
| F-CON-5 | nit | The story cites `templates/adr-amendment.md` as an existing artifact but does not pin whether it needs to be created (Files-to-touch marks it "Update if it doesn't exist already"). | AC-8 amended: if `templates/adr-amendment.md` does not exist, create a minimal Nygard-format stub with an "Amends: ADR-XXXX" line + "Change:" + "Justification:" sections. Story does not gate on the template's content beyond existence. |

### Design-Patterns critic

| ID | Severity | Finding | Fix |
|---|---|---|---|
| F-DP-1 | harden | `tests/integration/_snapshot_helpers.py` places the helper as story-local, but `tests/helpers/bench.py` and `tests/helpers/chain.py` (S3-01, S3-02 precedents) already establish `tests/helpers/` as the shared-test-helpers namespace (Rule 11 — match convention). Story-local `_snapshot_helpers.py` under `tests/integration/` splits the helper family. | Files-to-touch amended: `tests/helpers/snapshots.py` (NOT `tests/integration/_snapshot_helpers.py`). Also mirrored by AC-11's fence: `tests/fence/test_snapshot_canonicalization_chokepoint.py` rejects any snapshot comparison that opens `tests/snapshots/*.json` outside `tests/helpers/snapshots.py`. |
| F-DP-2 | harden | The `--dry-run-tamper` mode is a second responsibility for `scripts/regen_eval_snapshot.py` — the script does two unrelated things (regenerate real snapshots + prove drift diagnostic works). Command pattern: two subcommands, one script; keeps regen and drift-check honestly separate. | AC-6 amended: `scripts/regen_eval_snapshot.py regenerate` and `scripts/regen_eval_snapshot.py dry-run-tamper --out=<tmp_path>` — click subcommands (or `argparse` if the codebase prefers). One responsibility per subcommand. |
| F-DP-3 | (info) | The snapshot filename lives at module level (`bench_run_report.v1.json` literal in multiple places). If Phase 11 / Phase 13 readers need to load the same file, a `codegenie.eval.snapshots.CURRENT_REPORT_SNAPSHOT: Final[Path]` constant would prevent path drift. | Surface in Notes as a follow-up trigger (rule of three: this story is site 1, Phase 11 might be site 2, Phase 13 might be site 3). YAGNI today (Rule 2). No AC. |
| F-DP-4 | (info) | The three consecutive-run pattern is likely to recur (Phase 9 durable-workflow will want the same chain-of-N test against a Temporal event log). If S9 comes with the same pattern, extract a `_write_n_records_and_verify(runs_dir, n)` helper. YAGNI today. | Surface in Notes only. |
| F-DP-5 | harden | Snapshot serialization is currently proposed inline (`fresh.model_dump_json(indent=2)`). Elevating the canonicalizer to `codegenie.eval.snapshots.canonical_json(model: BaseModel) -> str` (pure function, no I/O, unit-testable) keeps the byte-shape contract in production code, not test code — the executor + Phase 11 consumer will use the *same* canonicalizer, so drift-vs-serializer-drift is impossible. | New AC-11a — `codegenie.eval.snapshots.canonical_json(model)` public helper; `tests/helpers/snapshots.py` imports and uses it; `scripts/regen_eval_snapshot.py` imports and uses it. Fence: any `model_dump_json` call in `src/codegenie/eval/` OR `tests/helpers/` OR `scripts/regen_eval_snapshot.py` on a wire type must route through `canonical_json` (AST walk under `tests/fence/`). |
| F-DP-6 | nit | `dict[str, ...]` for `runs_dir` file listings — S3-01 / S3-02 use `tuple[Path, ...]` sorted. Prefer `tuple` for immutability + reproducibility. | Notes: use `tuple(sorted(runs_dir.glob("*.json")))` uniformly. Not an AC — cosmetic. |

## Stage 3 — Research

Not invoked. No findings tagged `NEEDS RESEARCH`; all canonical patterns (byte-freeze snapshots, sort_keys canonicalization, three-record-chain-walk, JitteredStubSUT helper) have in-repo precedent from S2-04, S3-01, S3-02, S3-05, and S3-06.

## Stage 4 — Synthesis + edits applied

**Conflict resolution:** Consistency wins in every collision. The runner-API mismatch (F-CON-1/F-TQ-1) is a source-of-truth violation against hardened S3-01/S3-02/S3-06/S4-02 — the story's TDD plan must adapt to the hardened contract, not the other way around. Coverage's instinct to test three snapshots with different frozen-time values (F-COV-3) wins over "one snapshot, three runs would collide" — Consistency confirms that three distinct `run_started_iso` values are the correct threading.

**Edits applied directly to `S7-02-audit-chain-integration-and-snapshots.md`:**

- Header — Status `Ready` → `HARDENED`; Depends-on extended to `S3-01, S3-02, S3-06, S4-02` (previously only S5-05 + S2-04).
- Inserted `Validation notes` block under header summarizing every change and the four blocks.
- Context section: unchanged in intent; clarified the "two-snapshot" story.
- Acceptance criteria: rewrote 8 ACs (AC-1..AC-8 hardened) and added 6 new ones (AC-9..AC-14). Numbering renormalized.
- Implementation outline: rewrote in 6 numbered steps against the hardened two-call runner contract.
- TDD plan: entire test file body replaced. Uses `stub_task_class_fixture(tmp_path)`, `make_stub_plan(tmp_path)`, `JitteredStubSUT.zero()`, `_default_execute_kwargs(tmp_path)`. Six tests → five tests (`test_three_run_evals_produce_a_chain_of_length_three` folds in chain-link oracle from F-TQ-4 and pre-tamper baseline from F-COV-5; `test_genesis_record_has_zero_prev_hash` unchanged in intent; `test_tamper_detected` targets `prev_hash` with specific `VerifyResult` assertions; snapshot tests use canonical serializer).
- Files to touch: `tests/integration/_snapshot_helpers.py` moved to `tests/helpers/snapshots.py`; added `src/codegenie/eval/snapshots.py` (canonical_json helper); added `tests/fence/test_snapshot_canonicalization_chokepoint.py`.
- Out of scope: unchanged; the story stays surgical.
- Notes for the implementer: rewrote to remove the contradiction on tamper target; expanded on the versioning rule; called out the runner-API mismatch as historical (the writer's original prose was wrong; follow the hardened APIs).

## Verdict

**HARDENED.** The story now:

- Speaks the hardened runner API (`Runner().plan(...)` → `asyncio.run(Runner().run_eval(plan, ...))`), not the invented 2-arg `run_eval(task_class_name=..., bench_root=...)`.
- Threads `run_started_iso` for time-freezing via the `plan()` seam that already accepts it — no invented `frozen_time` kwarg.
- Uses `stub_task_class_fixture(tmp_path)` + `make_stub_plan(tmp_path)` per S3-01/S3-02 helper convention; no fictitious `tests/fixtures/bench/stub-task-class/` path.
- Pins byte-canonical snapshot serialization at a **single production chokepoint** (`codegenie.eval.snapshots.canonical_json`) rather than inline `model_dump_json(indent=2)` — Phase 11 / Phase 13 downstream consumers read the same shape.
- Names the tamper target *deterministically* (`prev_hash` — the chain-link semantic, not `mean_score` which invalidates the record's own content hash) and pins WHICH `VerifyResult` fields prove the correct failure mode was detected.
- Clarifies the "two-snapshot" question: `bench_run_report.v1.json` is the full-value byte snapshot; `eval_run_audit_record.v1.json` is the schema-shape fixture — they detect different drift classes and can regen independently. If the executor decides schema fixture is over-specified, the collapse-to-one path is documented in Notes with the ADR-amendment trigger.
- Places the snapshot helper under `tests/helpers/snapshots.py` per S3-01/S3-02's `tests/helpers/` convention (Rule 11); a fence pins that no other module opens the snapshot files directly.
- Splits the regen script into two subcommands (`regenerate` and `dry-run-tamper`) so operator intent is honest and unrecoverable regeneration is a distinct verb from drift-diagnostic proof-of-fire.

Ready for executor.
