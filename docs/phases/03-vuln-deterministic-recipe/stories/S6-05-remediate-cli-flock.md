# Story S6-05 — `codegenie remediate` CLI + `.codegenie/.lock` flock + `audit verify` spanning-chain extension

**Step:** Step 6 — RemediationOrchestrator, TrustScorer, two-stream EventLog, SubgraphNode Protocol, end-to-end happy path
**Status:** HARDENED (validated 2026-05-19 — see [`_validation/S6-05-remediate-cli-flock.md`](_validation/S6-05-remediate-cli-flock.md))
**Effort:** M
**Depends on:** S6-01 (must publish `WorkflowConcurrent` variant + `_chain_step` helper), S6-04 (orchestrator)
**ADRs honored:** ADR-0005 (BLAKE3-chained spanning stream — `audit verify` walks it; refuses startup on break), ADR-0010 (`RemediationOutcome` tagged union with exhaustive `match` + `assert_never`; `WorkflowConcurrent` is a typed spanning-stream variant)

## Validation notes (2026-05-19)

The story was hardened in place by the phase-story-validator. Highlights of what changed and why:

- **Class names corrected to shipped S1-03 reality.** Every occurrence of `RemediationOutcome.NotApplicable` / `RemediationOutcome.Failed` is now `RemediationNotApplicable` / `RemediationFailed` per [`src/codegenie/transforms/outcomes.py:274-294`](../../../../src/codegenie/transforms/outcomes.py) and the S6-04 validation report finding C-F1. The original `match` arms (`case Validated`, `case NotApplicable`, `case Failed`, `case RequiresHumanReview`) would never have matched the actual class names.
- **`WorkflowConcurrent` variant ownership pinned.** S6-01 ships exactly 9 spanning variants; `WorkflowConcurrent` is NOT one of them. The contradiction is resolved by **amending S6-01** (additive — 10th variant), with this story's executor responsible for landing the amendment alongside S6-05's CLI changes (since S6-01 is HARDENED but not GREEN, this is one merged change). The variant lives at the canonical S6-01 declaration site (`src/codegenie/plugins/events.py`), NOT in a separate module.
- **Exit-code translator is now a pure helper (`_exit_code_for(outcome) -> int`) with a parametrized property test**, replacing the original `inspect.getsource(...)` string-grep test that S6-04's validation already flagged as fragile. The kernel of the exit-code matrix is one `match` block — adding a future `RemediationOutcome` variant is one new arm + one new parametrized row (Open/Closed).
- **`_workflow_lock` context manager** added as an explicit AC + Notes-elevated extension seam. The lock primitive is reusable (e.g., Phase 5's `GateRunner` may need a sibling for a per-attempt advisory lock); the helper is the natural extension point.
- **Smart-constructor call shape corrected.** `CveId.parse(...)` does not exist; the codebase ships `parse_cve_id(s) -> Result[CveId, ParseError]` ([`src/codegenie/types/parsers.py:154`](../../../../src/codegenie/types/parsers.py)). `SandboxedPath.create(...).unwrap()` similarly replaced with the Result-handling convention used by the rest of the codebase (`match` over `Ok` / `Err` — see Implementation outline §2).
- **Chain-verification primitive is `_chain_step` from `codegenie.plugins.events`**, NOT `codegenie.audit`. The Phase-0 `verify_runs` walker is the *aggregation* precedent; the per-event hash recomputation reuses S6-01's pure helper. Notes-for-implementer corrected.
- **New ACs for edge cases**: lockfile symlink rejection (TOCTOU defence — `O_NOFOLLOW` + stat), lockfile permissions `0o600`, missing `.codegenie/` auto-create, invalid `<repo>` path → click usage error exit 2, invalid `--cve` format → exit 2 with `parse_cve_id` error string surfaced.
- **Audit-verify check seam.** The `audit verify` subcommand previously had one check (per-run anchors); this story adds a second (spanning chain). Notes-for-implementer flag the Open/Closed opportunity ahead of a possible third (Phase 5 contract snapshot) — the story does NOT introduce a registry now (Rule 2: three similar lines beat premature abstraction at two), but documents the future extraction so the next sibling story can land the registry without surprises.
- **Operator-sanitization ACs concretized** with a stdout/stderr regex test reusing `codegenie.output.sanitizer.scrub_paths` (the Phase-0 / Phase-2 module — corrected from the placeholder `src/codegenie/output/sanitizer.py or similar`).
- **Concurrent-invocation integration test** replaces fixed `time.sleep(0.5)` synchronization with a deterministic barrier (poll lockfile until the holder PID appears, max 5s) — flake-resistant; documented in the test docstring per the "Notes" warning in the original.

The Goal and the design-pattern choices survive. Only AC text + TDD plan + Notes needed correction.

## Context

This story is the CLI surface that turns the orchestrator (S6-04) into a runnable command. Three concerns are bundled:

1. **The click subcommand `codegenie remediate <repo> --cve <id>`** — entry point under `src/codegenie/cli/remediate.py`. Wires up: `PluginRegistry` load, `VulnIndex` open, `EventLog` construct, `RemediationOrchestrator` construct + `run(...)`, exit-code translation from `RemediationOutcome` variant.
2. **`.codegenie/.lock` `fcntl.flock` exclusive lock** (per architecture spec §Edge cases E13 + §Harness engineering §Idempotence): the *first* thing `remediate` does after parsing args is acquire an `LOCK_EX | LOCK_NB` lock on `<repo>/.codegenie/.lock`. If acquisition fails (another `codegenie remediate` is running on the same repo), the second invocation emits a `WorkflowConcurrent` spanning event (variant added in S6-01) and exits with code **8**. This is a different lock than the `EventLog`'s internal `fcntl.flock` on the spanning stream — that one is a deep defense for write interleaving; this one is the outer mutex on the workflow itself.
3. **`codegenie audit verify` extension** to walk the BLAKE3 chain on the spanning stream (`.codegenie/events/spanning/append.jsonl.zst`) — refusing startup on chain break. Phase 0's existing `codegenie audit verify` already walks the per-run audit anchors (`tests/integration/test_audit_chain_extension.py` precedent); this extension adds the spanning-stream walk as a new check inside the same command.

Exit codes (per architecture spec §Control flow — Decision points + §Edge cases). Class names are the canonical S1-03 shipped names (`RemediationNotApplicable` / `RemediationFailed`, NOT `RemediationOutcome.NotApplicable` / `RemediationOutcome.Failed`):

- `0` — `Validated(passed=True, failing=[])`
- `2` — click usage error (invalid `--cve` format, missing `<repo>`, mutually-exclusive flags). Standard click convention; NOT a `RemediationOutcome` mapping.
- `3` — `RemediationNotApplicable(reason)` (Phase 4 fallback territory)
- `4` — `RemediationFailed(error, partial_report_path)` OR `Validated(passed=False, failing=[...])` (per ADR-0007: Phase 3 alone does not retry on failed validation — Phase 5's `GateRunner` is the retry envelope). Both map to 4 because both represent "deterministic failure, escalation required."
- `7` — `RequiresHumanReview(reason, handoff_path)` (universal HITL fallback fired)
- `8` — `WorkflowConcurrent` spanning event emitted; second invocation refused at the outer flock

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Control flow` — full 11-step happy path; the CLI is step 1 (parse + mint `WorkflowId`) and step 11 (flush + exit).
  - `../phase-arch-design.md §Control flow — Decision points` — exit code matrix per `RemediationOutcome` variant.
  - `../phase-arch-design.md §Harness engineering §Idempotence` — *"second run aborts with `WorkflowConcurrent` (the `.codegenie/.lock` `flock`)"*. Exact semantics: re-running against an unchanged repo + unchanged `vuln-index.sqlite` would cache-hit and create the same branch; the flock makes the second invocation explicit-fail rather than silent-re-apply.
  - `../phase-arch-design.md §Edge cases E13` — concurrent invocation: `.codegenie/.lock` `fcntl.flock`; second exits immediately with `WorkflowConcurrent`.
  - `../phase-arch-design.md §Harness engineering — Replay / debuggability` — *"`codegenie audit verify` (extended from Phase 0) verifies BLAKE3 chain on the spanning stream and refuses startup on break"*.
- **Phase ADRs:**
  - `../ADRs/0005-two-stream-event-log-per-adr-0034.md` §Consequences — *"`codegenie audit verify` extends to verify the BLAKE3 chain on the spanning stream and refuses startup on break."*
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` §Decision (3) — `RemediationOutcome` tagged-union dispatch via `match` + `assert_never` (the CLI's exit-code translation is the textbook example).
- **Existing code to reuse / extend:**
  - `src/codegenie/cli/__main__.py` (or `cli/main.py` — verify via `ls src/codegenie/cli/`) — the click group `codegenie` and `codegenie audit verify` precedent.
  - `src/codegenie/audit.py` — `chain_verify` primitive that the spanning-stream walker reuses.
  - `src/codegenie/plugins/events.py` (S6-01) — `EventLog` + `WorkflowConcurrent` variant.
  - `src/codegenie/transforms/orchestrator.py` (S6-04) — `RemediationOrchestrator` constructed and `run(...)` here.
  - Phase 0's `tests/integration/test_audit_*` — precedent for verify-chain integration tests.
- **This phase, parallel stories:**
  - S6-01 — the `WorkflowConcurrent` event variant must exist on the spanning-stream union; the BLAKE3 chain this story walks.
  - S6-04 — the orchestrator; this CLI wires it up.
  - S6-06 — the contract snapshot test; this story does NOT modify it (the CLI surface is internal to Phase 3, not contracted to Phase 5).

## Goal

Land `src/codegenie/cli/remediate.py` exposing `remediate` click subcommand wired to `RemediationOrchestrator.run(...)`; a pure exit-code translator over `RemediationOutcome`; `.codegenie/.lock` `fcntl.flock` exclusive lock via a `_workflow_lock` context manager with `WorkflowConcurrent` + exit 8 on contention; extend `codegenie audit verify` to walk the spanning-stream BLAKE3 chain (reusing S6-01's `_chain_step` helper) and refuse startup on break. Also land the additive 10th `WorkflowConcurrent` variant on S6-01's `WorkflowSpanningEvent` discriminated union.

## Acceptance criteria

### CLI surface

- [ ] **AC-1.** `src/codegenie/cli/remediate.py` exists; `codegenie remediate --help` prints usage with `<repo>` positional argument and `--cve <id>` required option. The subcommand is registered on the existing `cli` click group in `src/codegenie/cli.py` (one new `@cli.command(name="remediate")` registration line + `from codegenie.cli.remediate import remediate as _remediate_cmd` import — no rewiring of the existing group).
- [ ] **AC-2.** `codegenie remediate ./path/to/repo --cve CVE-2024-21501` runs end-to-end against the Express CVE fixture ([S8-01](S8-01-fixture-portfolio.md) or the S6-04 stub) and exits `0` on `Validated(passed=True, failing=[])`. Branch matches the `codegenie/cve-2024-21501-<shortsha>` pattern; `remediation-report.yaml` is on disk; `outcome.kind == "validated"`.
- [ ] **AC-3.** Invalid `<repo>` (does-not-exist OR not-a-directory) → click `Path(exists=True, file_okay=False, path_type=Path)` raises usage error → exit `2`. Missing `--cve` → click usage error → exit `2`.
- [ ] **AC-4.** Invalid `--cve` syntax (not matching `parse_cve_id` regex) → click `UsageError` carrying the `ParseError.message` text → exit `2`. The CLI calls `parse_cve_id(cve)` and `match`es on the `Result[CveId, ParseError]`. NO silent coercion.
- [ ] **AC-5.** `--repo-context-path <path>` is an optional flag (default: `<repo>/.codegenie/context/repo-context.yaml`). If the YAML's mtime is `> 7 days` (Phase 1 staleness convention), the CLI logs `repo_context.stale` at WARN via `structlog` and continues. NOT a blocker.

### Exit-code translator

- [ ] **AC-6 (exhaustive over `RemediationOutcome`).** A pure helper `_exit_code_for(outcome: RemediationOutcome) -> int` lives at `src/codegenie/cli/remediate.py` module level. Its body is a single `match` block + `assert_never` over the four shipped S1-03 variants — **exact class names**: `Validated`, `RequiresHumanReview`, `RemediationNotApplicable`, `RemediationFailed`. The mapping is:
  - `Validated(passed=True, failing=[])` → `0`
  - `Validated(passed=False, failing=[...])` → `4`
  - `RemediationNotApplicable(reason)` → `3`
  - `RemediationFailed(error, partial_report_path)` → `4`
  - `RequiresHumanReview(reason, handoff_path)` → `7`
- [ ] **AC-7 (translator is the single source of truth).** `_exit_code_for` is **not** inlined into the click body; the click body calls it. A parametrized unit test (one row per variant; 5 rows total including the two `Validated` branches) asserts the exact integer returned. Adding a future variant to `RemediationOutcome` causes `mypy --strict` to fail at `assert_never(outcome)` — no string-grep, no `inspect.getsource(...)`.

### Outer flock

- [ ] **AC-8 (`_workflow_lock` context manager).** A context manager `_workflow_lock(repo: Path, *, holder_pid: int) -> ContextManager[Path]` lives at module level in `remediate.py`. It:
  1. Resolves `<repo>/.codegenie/.lock`; creates `<repo>/.codegenie/` with `mode=0o700` if missing (matching `codegenie gather` convention).
  2. Refuses if `.codegenie/.lock` exists and is a symlink (`os.lstat(...).st_mode & stat.S_IFLNK`) → `RemediationFailed(error=filesystem_race)` → exit `4`. (Security: TOCTOU defence; mirrors E12.)
  3. Opens with `os.open(path, O_WRONLY | O_CREAT | O_NOFOLLOW, 0o600)` (NOT `open(...)` — the mode bits must be enforced at creation time; `O_NOFOLLOW` rejects symlink races).
  4. Truncates and writes `str(holder_pid)` (best-effort holder hint — a contender reads this to populate `WorkflowConcurrent.lock_holder_pid`); calls `os.fsync(fd)`.
  5. Calls `fcntl.flock(fd, LOCK_EX | LOCK_NB)`.
  6. On `BlockingIOError`: yields `None` (lock-contended sentinel) AND records the contender's attempt for the caller's `WorkflowConcurrent` emission.
  7. On success: `yield` the lock path; on context exit, `fcntl.flock(fd, LOCK_UN)` then `os.close(fd)` in a `finally`.
- [ ] **AC-9 (lock-first ordering).** Inside the click body, the lock-acquire is the FIRST I/O operation after click finishes argument parsing and `parse_cve_id` validation. `EventLog` construction, `WorkflowId` minting, `RemediationOrchestrator` construction, and `WorkflowStarted` emission all happen **after** the outer lock is held (otherwise the spanning stream's own per-emit `fcntl.flock` would serialize concurrent invocations behind I/O latency, masking the outer-mutex semantics). A unit test inspects the CLI call graph (via a `pytest` monkeypatch on `_workflow_lock`, `EventLog.__init__`, and `RemediationOrchestrator.__init__`) and asserts the recorded call order: `_workflow_lock` → `EventLog.__init__` → `RemediationOrchestrator.__init__` → `EventLog.emit_spanning(WorkflowStarted)`.
- [ ] **AC-10 (`WorkflowConcurrent` emission on contention).** When `_workflow_lock` yields the contended sentinel, the CLI:
  1. Mints a contender `WorkflowId` (ULID) for the failed attempt.
  2. Reads `<repo>/.codegenie/.lock` (best-effort — `try: int(path.read_text().strip()) except (OSError, ValueError): None`) for the holder PID.
  3. Constructs a one-shot `EventLog` (without holding the outer mutex; the spanning stream's per-emit `flock` on the spanning file itself is sufficient — they are different files) and calls `emit_spanning(WorkflowConcurrent(workflow_id=<contender>, lock_holder_pid=<hint or None>, contested_at=<utcnow>, repo_path=str(repo)))`.
  4. Writes ONE operator-facing line to stderr matching `r'^workflow_concurrent: another codegenie remediate is running against [^\s]+; exiting\n$'`.
  5. Exits `8`. **No partial `remediation-report.yaml`. No branch creation.**
- [ ] **AC-11 (lock release).** The outer-mutex `fcntl.flock(fd, LOCK_UN)` + `os.close(fd)` always run via the `_workflow_lock` `finally` — verified by a fault-injection unit test that raises `KeyboardInterrupt` inside the `with` body and asserts (a) the FD is closed (per `psutil.Process().open_files()` snapshot, OR `os.fstat(fd)` raising `OSError(EBADF)`) and (b) a fresh `fcntl.flock(LOCK_EX | LOCK_NB)` on the same path succeeds afterwards. Kernel auto-unlock on FD close is fine; the explicit `LOCK_UN` is documented in the helper's docstring as the contract.

### `WorkflowConcurrent` variant (S6-01 amendment, additive)

- [ ] **AC-12.** `src/codegenie/plugins/events.py` (S6-01's canonical event module) gains a 10th spanning variant:
  ```python
  class WorkflowConcurrent(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      event_type: Literal["workflow_concurrent"] = "workflow_concurrent"
      event_id: EventId
      timestamp: datetime
      prev_hash: BlobDigest
      workflow_id: WorkflowId           # the contender's minted id
      lock_holder_pid: int | None       # best-effort hint from the lockfile
      contested_at: datetime
      repo_path: str                    # path-scrubbed at write site
  ```
  Added to the `WorkflowSpanningEvent` discriminated union (now 10 variants). S6-01's AC-7 ("9 variants") is amended to "10 variants" via the cross-story closure note in the executor's commit. No `Discriminator(...)` API change — additive only.
- [ ] **AC-13.** `_chain_step(prior_head, canonical_json_bytes(WorkflowConcurrent_without_prev_hash))` produces the same BlobDigest shape as the other 9 variants. A regression test under `tests/unit/plugins/test_events.py::test_workflow_concurrent_chains_like_other_variants` asserts BLAKE3-prefix + hex-len equality.

### `audit verify` spanning-chain extension

- [ ] **AC-14.** `codegenie audit verify` gains a new option `--spanning-events-path <path>` (default: derive from `--runs-dir` parent → `<root>/events/spanning/append.jsonl.zst`). If the path is absent or the file is empty (zero bytes), the check is a **no-op success** (genesis = nothing to verify; exit-code aggregation unaffected).
- [ ] **AC-15.** When the spanning file exists, the verifier:
  1. Opens with `O_RDONLY | O_NOFOLLOW` (symlink defence).
  2. Streams zstd-decompressed lines.
  3. For each line: parses via the S6-01 `WorkflowSpanningEvent` discriminated union; recomputes `expected_prev = _chain_step(prior_head, canonical_json_bytes(event_without_prev_hash))` (reusing the **S6-01-owned** `_chain_step` helper, not a private reimplementation in `audit.py`); compares to `event.prev_hash`.
  4. First mismatch → emits `audit.verify.chain_mismatch` log event (matching the existing `audit.verify.*` taxonomy in [`src/codegenie/audit.py:32-33`](../../../../src/codegenie/audit.py)) carrying `path`, `line_number`, `expected_prev`, `recorded_prev`, `event_id` of the first divergent record. Returns mismatch count ≥ 1.
- [ ] **AC-16.** `audit_verify` aggregates the existing per-run-anchor mismatches with the new chain-mismatch count; exit code is `0` if total `== 0`, else `4`. The existing exit-4 semantics ([cli.py:902](../../../../src/codegenie/cli.py)) are preserved. The chain check does NOT short-circuit per-run-anchor verification (both run, both report — operators see the union of evidence).
- [ ] **AC-17.** A truncated zstd frame (corrupted file mid-stream) → `EventLogCorrupted(path, line_number, "zstd_frame_truncated")` event → counted as a mismatch → exit `4`. NOT a Python exception leak.

### Sanitization

- [ ] **AC-18.** Operator-facing stdout/stderr written by this CLI is routed through `codegenie.output.sanitizer.scrub_paths(text, jail=<repo>)` (the Phase-0 / Phase-2 module — verified to exist at [`src/codegenie/output/sanitizer.py`](../../../../src/codegenie/output/sanitizer.py)). A unit test runs `codegenie remediate` with a synthetic absolute path `"/home/intruder/secret"` injected into a `RemediationFailed.error.message` and asserts the substring is NOT present on stderr (the scrubber maps outside-jail paths to `<external>`).
- [ ] **AC-19.** Sensitive env-value families (`GITHUB_TOKEN`, `OPENAI_API_KEY`, `AWS_*`, `SSH_AUTH_SOCK` — the Phase 0 `_SENSITIVE_*` lists) never appear in stdout/stderr. Verified by an integration test that sets `GITHUB_TOKEN=test_pizzapizza_marker` and asserts the marker is not in any subprocess capture from `codegenie remediate`.

### Integration tests

- [ ] **AC-20 (concurrent invocation).** `tests/integration/test_concurrent_remediate.py` spawns two `codegenie remediate` subprocesses against the same fixture repo. Synchronization is deterministic (NOT a fixed sleep): the test (a) starts the first subprocess with a monkeypatched orchestrator that `await asyncio.sleep(2.0)` mid-workflow; (b) polls `<repo>/.codegenie/.lock` until the file exists AND contains a non-empty PID (max 5s, 50ms intervals — if never seen, the test fails LOUD with "first invocation never wrote PID to lockfile"); (c) only then starts the second subprocess. Asserts the second exits `8`, stderr matches the AC-10 regex, and one `WorkflowConcurrent` event lands on the spanning stream with `lock_holder_pid` equal to the first subprocess's PID. The first eventually exits with the orchestrator-determined success code (assert `in (0, 4)` — covering both `Validated` branches per AC-6).
- [ ] **AC-21 (audit verify happy path).** `tests/integration/test_audit_verify_spanning_chain.py::test_intact_chain_exits_0` writes a valid 3-event spanning stream via S6-01's `EventLog.emit_spanning(...)`, runs `codegenie audit verify --spanning-events-path <path> ...` → exit `0` AND `audit.verify.ok` event emitted with `chain_checked=True`.
- [ ] **AC-22 (audit verify tamper).** `tests/integration/test_audit_verify_spanning_chain.py::test_tampered_chain_exits_4` writes a valid stream then flips one byte inside the zstd frame at line 2; runs `audit verify` → exit `4` AND `audit.verify.chain_mismatch` event emitted with `line_number=2` AND stderr contains the first-divergent `event_id`.
- [ ] **AC-23 (audit verify empty/missing).** `tests/integration/test_audit_verify_spanning_chain.py::test_missing_spanning_stream_exits_0` runs `audit verify` against a repo with no `events/spanning/` directory → exit `0` (no-op-success per AC-14).

### Hygiene

- [ ] **AC-24.** TDD red test exists, committed, green by end of story.
- [ ] **AC-25.** `make check` clean: `ruff format --check`, `ruff check`, `mypy --strict`, all targeted tests pass, fence tests stay green.
- [ ] **AC-26.** No new entries in `ALLOWED_BINARIES` (the CLI is pure Python; no new subprocess invocations beyond what `RemediationOrchestrator` already declares).

## Implementation outline

1. **Red.** Write `tests/unit/cli/test_remediate.py` + `tests/integration/test_concurrent_remediate.py` + `tests/integration/test_audit_verify_spanning_chain.py`. Confirm `ImportError`s. Commit the red marker.
2. **Land the `WorkflowConcurrent` variant FIRST** (the smallest change unlocking the rest): add the class + `__all__` export to `src/codegenie/plugins/events.py`; extend the `WorkflowSpanningEvent` `Annotated[... , Field(discriminator="event_type")]` alias from 9 to 10 variants; add the per-variant test under `tests/unit/plugins/test_events.py`. This is S6-01's amendment landed inside this story's commit (S6-01 is HARDENED but not GREEN — single change, no orphan).
3. **Create `src/codegenie/cli/remediate.py`** with the following module-level shape:
   - `_workflow_lock(repo, *, holder_pid)` — context manager per AC-8.
   - `_exit_code_for(outcome: RemediationOutcome) -> int` — pure helper per AC-6 / AC-7. Single `match` block, `assert_never` at the bottom.
   - `_emit_operator_message(text, *, stream)` — sanitizer-routed write helper (uses `codegenie.output.sanitizer.scrub_paths`).
   - `_emit_workflow_concurrent(repo, *, contender_workflow_id, holder_pid_hint)` — direct-emit path that constructs a transient `EventLog` for the failed attempt.
   - `@click.command(name="remediate")` body — sequence:
     a. `parse_cve_id(cve)` → `match` on `Result`; `Err` → `raise click.UsageError(parse_error.message)`.
     b. Acquire outer mutex via `_workflow_lock(repo, holder_pid=os.getpid())`. If contended → `_emit_workflow_concurrent(...)` → `_emit_operator_message(...)` → `sys.exit(8)`.
     c. Mint `WorkflowId` via `ulid` (Phase 0 dep) wrapped through `parse_workflow_id(str(ulid_value))`.
     d. Construct `EventLog(root=repo / ".codegenie", workflow_id=wf)`. Emit `WorkflowStarted` spanning event.
     e. Construct `RemediationOrchestrator(...)` (S6-04). Resolve `repo_context_path` (CLI flag or default); log `repo_context.stale` at WARN if mtime > 7d.
     f. `outcome: RemediationOutcome = asyncio.run(orchestrator.run(repo=<SandboxedPath via Result handling — match on Ok/Err>, cve=<CveId from step a>, ctx=ApplyContext(workflow_id=wf, capabilities=<bundle>)))`.
     g. `exit_code = _exit_code_for(outcome)`.
     h. `finally`: `event_log.flush()`; (lock release is automatic via the `_workflow_lock` context manager's `finally`); `sys.exit(exit_code)`.
4. **Register** the `remediate` command on the existing `cli` click group in `src/codegenie/cli.py` (single import + single decorator wiring; do not touch the existing `gather` / `audit` / `cache` registrations).
5. **Extend `audit verify`** in `src/codegenie/cli.py:audit_verify(...)`:
   - Add `--spanning-events-path` click option (defaulting from `--runs-dir.parent.parent / "events" / "spanning" / "append.jsonl.zst"`).
   - Add a new helper `_verify_spanning_chain(spanning_path: Path) -> int` in `src/codegenie/audit.py` mirroring the shape of `_verify_one_blob` / `_verify_one_yaml`. Body: open via `O_RDONLY | O_NOFOLLOW`; iterate decoded events; recompute via S6-01's `_chain_step` (`from codegenie.plugins.events import _chain_step`); compare; on mismatch emit `audit.verify.chain_mismatch` and return mismatch count.
   - Aggregate into `verify_runs` → return mismatch count; CLI maps to exit 0/4 as today.
6. **Refactor**: the `audit verify` aggregator is now invoking 2 of N checks (per-run-anchor + spanning-chain). Notes-for-implementer flag the future `AuditCheck` registry opportunity at the rule-of-three threshold (do NOT introduce yet — Rule 2).
7. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest -q` on the new + adjacent tests; full `make check` before commit.

## TDD plan — red / green / refactor

### Red — write the failing tests first

The tests below verify INTENT (Rule 9), not surface shape. The original string-grep test on `inspect.getsource` is dropped — it would pass on a refactored implementation that has no behavior at all (a function that returns `0` for everything would still contain the source tokens).

```python
# tests/unit/cli/test_remediate.py
import os
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from codegenie.cli.remediate import remediate, _exit_code_for, _workflow_lock
from codegenie.transforms.outcomes import (
    Validated, RequiresHumanReview, RemediationNotApplicable, RemediationFailed,
    RemediationError, NotApplicableReason, HumanReviewReason,
)
from codegenie.types.identifiers import BranchName, SignalKind


def _branch() -> BranchName:
    return BranchName("codegenie/cve-2024-21501-abcdef0")


@pytest.mark.parametrize(
    "outcome,expected",
    [
        # AC-6 — exhaustive over RemediationOutcome (5 rows; two for Validated branches).
        (Validated(branch=_branch(), report_path="r.yaml", passed=True, failing=[]), 0),
        (Validated(branch=_branch(), report_path="r.yaml", passed=False,
                   failing=[SignalKind("trust.test")]), 4),
        (RemediationNotApplicable(reason="peer_dep_conflict"), 3),
        (RemediationFailed(error=RemediationError(...), partial_report_path=None), 4),
        (RequiresHumanReview(reason="no_concrete_match", handoff_path="h.md"), 7),
    ],
)
def test_exit_code_for_is_exhaustive(outcome: Any, expected: int) -> None:
    """AC-6/AC-7 — the translator is a pure function over the discriminated union.

    Mutation: replacing _exit_code_for body with `return 0` would fail 4/5 rows.
    Adding a 5th variant without a new arm would fail mypy --strict at assert_never.
    """
    assert _exit_code_for(outcome) == expected


def test_remediate_help_lists_repo_and_cve() -> None:
    """AC-1 — CLI surface contract; smoke test."""
    result = CliRunner().invoke(remediate, ["--help"])
    assert result.exit_code == 0
    assert "REPO" in result.output  # click renders the argument name in uppercase
    assert "--cve" in result.output


def test_invalid_cve_format_exits_2(tmp_path: Path) -> None:
    """AC-4 — `parse_cve_id` error path; no silent coercion."""
    (tmp_path / ".codegenie").mkdir()
    result = CliRunner().invoke(remediate, [str(tmp_path), "--cve", "not-a-cve"])
    assert result.exit_code == 2
    assert "parse" in result.output.lower() or "cve" in result.output.lower()


def test_lock_rejects_symlink(tmp_path: Path) -> None:
    """AC-8 step 2 — TOCTOU defence: lockfile must not be a symlink."""
    (tmp_path / ".codegenie").mkdir()
    target = tmp_path / "elsewhere"
    target.touch()
    (tmp_path / ".codegenie" / ".lock").symlink_to(target)

    # Direct unit test on the context manager (bypasses click).
    with pytest.raises(OSError):
        with _workflow_lock(tmp_path, holder_pid=os.getpid()):
            pytest.fail("must not enter when lockfile is a symlink")


def test_lock_releases_on_keyboard_interrupt(tmp_path: Path) -> None:
    """AC-11 — fault injection: KeyboardInterrupt inside the `with` releases the lock."""
    (tmp_path / ".codegenie").mkdir()
    with pytest.raises(KeyboardInterrupt):
        with _workflow_lock(tmp_path, holder_pid=os.getpid()) as lock_path:
            assert lock_path is not None
            raise KeyboardInterrupt
    # A second acquire on the same path must succeed without contention.
    with _workflow_lock(tmp_path, holder_pid=os.getpid()) as lock_path:
        assert lock_path is not None


def test_lock_first_call_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-9 — observable ordering: lock → EventLog → Orchestrator → emit(WorkflowStarted)."""
    calls: list[str] = []
    # ... monkeypatch each constructor / method to append its name to `calls` and
    # short-circuit before doing real work; assert the recorded order matches
    # ["lock", "EventLog.__init__", "Orchestrator.__init__", "emit_workflow_started"].


def test_sanitizer_strips_external_absolute_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-18 — operator messages route through `scrub_paths`; outside-jail paths replaced."""
    # Inject a RemediationFailed carrying an outside-jail absolute path; capture stderr;
    # assert the path is NOT present (replaced by `<external>` token).
    ...


# tests/integration/test_concurrent_remediate.py
import subprocess
import time
import json

import pytest


@pytest.mark.integration
def test_second_invocation_exits_8_with_workflow_concurrent(tmp_path: Path) -> None:
    """AC-20 — deterministic synchronization via lockfile poll, not fixed sleep.

    The first subprocess is monkey-patched (via a CODEGENIE_TEST_HANG_SECONDS=2.0
    env var the orchestrator reads in tests) to hold the lock for 2s. The second
    subprocess waits until the lockfile contains the first's PID, then races.
    """
    repo = _copy_fixture_to(tmp_path)
    env = {**os.environ, "CODEGENIE_TEST_HANG_SECONDS": "2.0"}

    first = subprocess.Popen(
        ["python", "-m", "codegenie", "remediate", str(repo), "--cve", "CVE-2024-21501"],
        env=env, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
    )
    try:
        lockfile = repo / ".codegenie" / ".lock"
        deadline = time.monotonic() + 5.0
        first_pid: int | None = None
        while time.monotonic() < deadline:
            try:
                first_pid = int(lockfile.read_text().strip())
                break
            except (FileNotFoundError, ValueError):
                time.sleep(0.05)
        assert first_pid is not None, "first invocation never wrote PID to lockfile"

        second = subprocess.run(
            ["python", "-m", "codegenie", "remediate", str(repo), "--cve", "CVE-2024-21501"],
            capture_output=True, text=True, timeout=5,
        )
        assert second.returncode == 8
        assert "workflow_concurrent" in second.stderr
        assert str(repo) not in second.stderr  # AC-18 — path scrubbed

        # AC-10 — WorkflowConcurrent landed on the spanning stream with the holder PID.
        events = _read_spanning_events(repo)
        concurrent = [e for e in events if e["event_type"] == "workflow_concurrent"]
        assert len(concurrent) == 1
        assert concurrent[0]["lock_holder_pid"] == first_pid
    finally:
        first.wait()
        assert first.returncode in (0, 4)  # AC-20 — either Validated branch is fine


# tests/integration/test_audit_verify_spanning_chain.py
@pytest.mark.integration
def test_audit_verify_passes_on_intact_chain(tmp_path: Path) -> None:
    """AC-21."""
    _seed_valid_spanning_stream(tmp_path, num_events=3)
    result = _run_audit_verify(tmp_path)
    assert result.returncode == 0


@pytest.mark.integration
def test_audit_verify_fails_on_tampered_chain(tmp_path: Path) -> None:
    """AC-22 — mutation: flipping a payload byte breaks the chain at line 2."""
    _seed_valid_spanning_stream(tmp_path, num_events=3)
    _flip_one_byte_in_zstd_payload(
        tmp_path / "events" / "spanning" / "append.jsonl.zst",
        line=2,
    )
    result = _run_audit_verify(tmp_path)
    assert result.returncode == 4
    assert "chain" in result.stderr.lower() or "mismatch" in result.stderr.lower()
    # Specific diagnostic surface.
    assert "line_number" in result.stderr or "line 2" in result.stderr.lower()


@pytest.mark.integration
def test_audit_verify_no_op_when_spanning_missing(tmp_path: Path) -> None:
    """AC-23 — empty/missing spanning stream is genesis; exit 0."""
    # Set up only the per-run-anchor structure; no events/spanning/ dir.
    _seed_runs_only(tmp_path)
    result = _run_audit_verify(tmp_path)
    assert result.returncode == 0
```

Run; confirm `ImportError` (no `codegenie.cli.remediate`) and `AttributeError` (no `WorkflowConcurrent`). Commit the red marker.

### Green — make each AC pass

The implementation lands as outlined above. Approximate sizing:

- `WorkflowConcurrent` Pydantic class + alias amendment in `events.py`: ~20 lines.
- `_exit_code_for`: ~15 lines (5-arm `match` + `assert_never`).
- `_workflow_lock` context manager: ~40 lines (symlink defence, `O_NOFOLLOW`, PID write, `flock`, `finally` release).
- `remediate` click body: ~70 lines (parse, lock, mint workflow id, construct EventLog + Orchestrator, `asyncio.run`, exit-code translation, `finally` flush).
- `_verify_spanning_chain` in `audit.py`: ~30 lines (open, decompress, recompute via `_chain_step`, emit `audit.verify.chain_mismatch` on first divergence).
- `audit verify` CLI wiring (`--spanning-events-path` option + aggregation): ~10 lines.

Total: ~185 lines of source + ~250 lines of test.

### Refactor — clean up after green

- Confirm `_exit_code_for` body is a single `match` block with `assert_never(outcome)` at the end (mutation guard — adding a future variant breaks the build).
- Confirm `_workflow_lock` is the ONLY place `fcntl.flock(LOCK_EX | LOCK_NB)` appears in `cli/remediate.py` (DRY: lock semantics in one place).
- Confirm `_emit_operator_message` is the ONLY write path to stdout/stderr from this module that carries data derived from `<repo>` / `outcome.error` (sanitizer chokepoint).
- Confirm `_chain_step` is imported from `codegenie.plugins.events` (NOT reimplemented in `audit.py`). Add a fence test under `tests/fence/` if a new one is justified (defer to the implementer's judgment — likely covered by existing module-purity fences).
- Document the `_emit_workflow_concurrent` helper's docstring: explains why it constructs a one-shot `EventLog` outside the outer mutex (the spanning stream's per-emit `fcntl.flock` on the spanning file itself is sufficient; the outer mutex is on a different FD).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli/remediate.py` | **New file** — click subcommand body, `_workflow_lock` context manager, `_exit_code_for` translator, `_emit_operator_message` helper, `_emit_workflow_concurrent` direct-emit path |
| `src/codegenie/cli.py` | One import + one decorator registration to wire `remediate` onto the existing `cli` group; add `--spanning-events-path` option to `audit_verify` (existing function at line 891) |
| `src/codegenie/audit.py` | Add `_verify_spanning_chain(spanning_path) -> int` helper next to existing `_verify_one_blob` / `_verify_one_yaml`; aggregate in `verify_runs` |
| `src/codegenie/plugins/events.py` | Add `WorkflowConcurrent` Pydantic class to `WorkflowSpanningEvent` discriminated union (10th variant, additive — closes S6-01 amendment) |
| `tests/unit/cli/test_remediate.py` | **New file** — parametrized exit-code property test (5 rows), CLI help, invalid-CVE exit 2, symlink rejection, lock release on KeyboardInterrupt, call-order observation, sanitizer regression |
| `tests/integration/test_concurrent_remediate.py` | **New file** — two subprocesses, deterministic lockfile-PID synchronization, second exits 8 with `WorkflowConcurrent` on spanning stream |
| `tests/integration/test_audit_verify_spanning_chain.py` | **New file** — intact-chain pass, tampered-chain fail at correct line, missing-stream no-op |
| `tests/unit/plugins/test_events.py` | **Extend** — `WorkflowConcurrent` round-trip + chain step parity with the other 9 variants |

## Out of scope

- **The orchestrator implementation** — S6-04.
- **The `WorkflowConcurrent` variant's payload schema definition** — owned by S6-01 (this story exercises it; if the variant is missing, surface to S6-01).
- **The Phase 5 contract snapshot test** — S6-06.
- **Per-run audit anchors** — Phase 0's existing `codegenie audit verify` already handles them; this story does not modify that path.
- **`codegenie remediate --watch` / polling mode** — out of scope; one-shot only.
- **Multi-CVE batched remediation in one invocation** — out of scope; one `--cve` per invocation. Phase 10's portfolio discovery is the wrapper.
- **PR creation (real `git push` + GitHub API)** — Phase 11. This story writes a local branch only.

## Notes for the implementer

### Read-before-write (Rule 8)

- **Shipped class names.** S1-03 / [`src/codegenie/transforms/outcomes.py:274-294`](../../../../src/codegenie/transforms/outcomes.py) ships `RemediationNotApplicable` and `RemediationFailed`, NOT `NotApplicable` / `Failed`. The original story drafted `case Failed`-style `match` arms — they would never have matched. Use the shipped names verbatim.
- **Smart-constructor call shape.** Use `parse_cve_id(s)` from [`src/codegenie/types/parsers.py:154`](../../../../src/codegenie/types/parsers.py), NOT `CveId.parse(s)`. Returns `Result[CveId, ParseError]` — `match` on `Ok(value)` / `Err(parse_error)`. Same shape for `SandboxedPath` (Result-returning constructor).
- **Chain primitive.** `_chain_step(prior_head, event_bytes)` lives in `src/codegenie/plugins/events.py` per S6-01 AC-4. Import from there; do NOT reimplement in `audit.py`. The Phase-0 `audit.py` aggregator pattern (`_verify_one_blob`, `_verify_one_yaml`) is the shape to mirror — but the BLAKE3 computation reuses S6-01's helper, not `codegenie.audit`'s blob hashing.
- **Sanitizer module.** Path scrubber lives at [`src/codegenie/output/sanitizer.py`](../../../../src/codegenie/output/sanitizer.py) (Phase-0 / Phase-2 module). Use `scrub_paths(text, jail=<repo>)`; do NOT reinvent. The story's original wording ("`src/codegenie/output/sanitizer.py` or similar") was a placeholder — the actual module exists; verify before importing.

### Concurrency semantics

- **`fcntl.flock` is advisory + FD-scoped.** A determined process can ignore it. The lock is best-effort cooperative mutex per ADR-0011 honest-framing — Phase 3 does not promise unforgeable isolation. Phase 9+ may swap to a more robust mechanism (kernel-level file lease or DB-based mutex). Document this caveat in the operator runbook.
- **Nested-lock safety.** When the outer mutex acquisition fails and the CLI emits `WorkflowConcurrent`, the helper constructs a transient `EventLog` and calls `emit_spanning(...)`. `emit_spanning` takes `fcntl.flock(LOCK_EX)` on the **spanning file** (`events/spanning/append.jsonl.zst`), which is a different FD from the outer `.codegenie/.lock`. The second process can acquire the spanning-file lock even though the first holds the outer mutex — they are different files, different FDs, no deadlock. Verify by reading S6-01's `EventLog.emit_spanning` and confirming the FD targets are disjoint.
- **`WorkflowConcurrent` belongs on the spanning stream**, not internal. The contended workflow never advances past lock acquisition; there is no per-workflow internal stream to write to. Cross-workflow facts → spanning stream (ADR-0005 §Decision).
- **Exit-code slot collision check.** Exit code 8 is not yet used by `_EXIT_CODE_DISPATCH` ([`src/codegenie/cli.py:69`](../../../../src/codegenie/cli.py)). If the executor finds a collision (e.g., a Phase 5 addition that landed between this story being drafted and executed), surface it in the attempt log and pick the next free slot (likely 9), updating the matrix + tests atomically.

### Single-async-boundary discipline

- **`asyncio.run(orchestrator.run(...))`** is the single async boundary in this CLI. Click is sync; the orchestrator is async; `asyncio.run` bridges. Do NOT introduce `anyio` / `asyncclick` / `trio` — the codebase convention is sync click commands bridging via `asyncio.run` (mirrors Phase 0 / Phase 2 patterns).

### Design-pattern opportunities (for future stories, NOT this one)

- **`AuditCheck` registry — at rule-of-three.** This story brings `audit verify` from one check (per-run anchors) to two (per-run anchors + spanning chain). The third check is foreseeable (Phase 5 contract-snapshot verifier, or a Phase 9 Postgres-side hash). At three, the right move is `@register_audit_check(name="spanning_chain") -> AuditCheck` Protocol with `name`, `option_flags`, `verify(ctx)` — Open/Closed: a new check is one decorated function, no edits to `verify_runs`'s aggregator. **Do NOT introduce now** (Rule 2: three similar lines beat premature abstraction at two). The next sibling story should land the registry alongside its third consumer.
- **`_workflow_lock` as a reusable port.** The lock primitive is a candidate Port if Phase 5's `GateRunner` needs a per-attempt advisory lock or Phase 9's remote-coordinated mutex emerges. Keep the helper at module level (not nested inside the click body) so promotion to `src/codegenie/concurrency/locks.py` is a file move, not a refactor.
- **Verifier strategy.** Each `_verify_one_*` in `audit.py` is already a strategy in disguise — they share the `(record) -> mismatch_count` shape. The registry above is the natural Open/Closed home for them too. Same "wait for three" rule.

### Test hygiene

- **Mutation thinking.** Every AC test should fail if the implementation is wrong in a specific way:
  - `_exit_code_for` parametrized rows would catch a "return 0 for everything" mutation in 4/5 rows.
  - Symlink-rejection test would catch a `open(...)` regression (missing `O_NOFOLLOW`).
  - PID-synchronization test would catch a "lock acquired but PID never written" mutation.
  - Sanitizer test would catch a "stderr write bypassing `_emit_operator_message`" mutation.
- **Tests verify intent (Rule 9), not surface shape.** The discarded `inspect.getsource(...)` string-grep is the textbook anti-test — it asserts the *spelling* of the implementation, not its *behavior*. The parametrized property test is intent: "this function maps every variant to its documented exit code; missing a variant is a mypy error."
- **Integration-test timing.** Use the deterministic lockfile-PID poll documented in AC-20. The hard rule: **NO fixed `time.sleep()` longer than 50ms** as a synchronization mechanism. If the test author thinks they need a longer sleep, the test author is wrong — they need a barrier (file existence + content) instead.

### Operator-facing failure modes

- **Operator runbook update (out-of-scope but flag).** The new `WorkflowConcurrent` exit code 8 + the `audit verify --spanning-events-path` flag need a documentation line each. Phase 11+ owns the user-facing runbook; this story DOES NOT write it. Mention the additions in the commit message so the runbook-author backlog catches them.
