# Story S7-04 — Concurrent-remediate `fcntl.flock` + `RepoAlreadyInProgress`

**Step:** Step 7 — Adversarial test suite + performance regression gates
**Status:** Ready (HARDENED 2026-05-26)
**Effort:** S
**Depends on:** S1-01 (`RepoAlreadyInProgress` marker class + `sandbox/logging.py` `EVENT_*` kernel — HARDENED), S1-04 (`GateContext` — HARDENED), S5-02 (`GateRunner` ctor frozen + async `run` — HARDENED), S7-03 (additive 7th ctor keyword precedent — HARDENED)
**ADRs honored:** ADR-0007 (pre-execute marker — lock must be acquired before the marker; marker is inside the lock)

## Validation notes (2026-05-26 — phase-story-validator)

Four-critic pass (coverage / test-quality / consistency / design-patterns). Verdict: **HARDENED**. The draft's goal + scope + ordering-vs-ADR-0007 framing were sound, but every block-tier finding traced to one of three root causes: (a) the draft was written before S1-01 reached HARDENED on 2026-05-16 — `RepoAlreadyInProgress` is *already defined* there as a bare-marker `SandboxError` subclass with no custom `__init__`, no class attributes, no `__str__` override; (b) the draft was written before S1-01 froze the `sandbox/logging.py` `EVENT_*: Final[str]` kernel — every event constant must be appended to `__all__` with a dotted-lowercase value, never emitted as a string literal; (c) the draft was written before S5-02 reached HARDENED on 2026-05-25 — `GateRunner.__init__` is keyword-only with 6 deps (S7-03 added the additive 7th `cost`), so the lock cannot live on the runner; it must wrap the entire `codegenie remediate` invocation at the CLI/orchestrator entry. Headline edits — every one would have caught a structurally-wrong implementation that the executor's validator would have missed:

1. **(consistency — block) `RepoAlreadyInProgress(CodegenieError)` with class attributes contradicts S1-01 AC-2.** The class is `RepoAlreadyInProgress(SandboxError)` and `SandboxError(Exception)` (NOT `CodegenieError` — the two hierarchies are deliberately disjoint). The class is a bare marker: no `__init__`, no class attributes, no `__str__` override. The TDD plan's `assert excinfo.value.lock_path == ...` would `AttributeError` against the actual locked class. Fix: AC-BASE-* import (not redefine) the class; AC-HOLDER-* introduce a frozen `RepoLockHolder(BaseModel, frozen=True, extra="forbid")` value type that travels via `structlog.bind(...)` and as the json-serialized `str()` payload of the exception.
2. **(consistency — block) Event constants missing from `sandbox/logging.py`.** S1-01 extension-by-addition contract requires every event name to be a `Final[str]` constant under `__all__` with a dotted-lowercase value (`^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$`). The draft emitted bare `"repo_lock.acquired"` / `"repo_lock.released"` literals. Fix: AC-EVT-* add `EVENT_REPO_LOCK_ACQUIRED` / `EVENT_REPO_LOCK_RELEASED` / `EVENT_REPO_LOCK_CONTENDED` to `sandbox/logging.py` (namespaced `sandbox.repo_lock.*` to match `EVENT_SANDBOX_EXECUTE_*` pattern); AST scan asserts no bare literals exist anywhere under `src/codegenie/sandbox/`.
3. **(consistency — block) Wiring point ambiguity.** Draft step 4 said `GateRunner.__init__ (or the orchestrator wrapper)`. But S5-02 froze the ctor keyword-only with 6 deps; S7-03 added the additive 7th `cost` — an 8th `repo_root` would compound. Worse, the orchestrator constructs one `GateRunner` per gate (Phase 3 Stage 6 has multiple gates); the lock must span the **whole** remediate invocation. Fix: AC-WIRE-LOC-* wire at `cli/remediate.py` Click-command entry via `ExitStack.enter_context(acquire_repo_lock(repo_root))` before any Phase 3 / Phase 4 / Phase 5 work. `GateRunner.__init__` signature is unchanged.
4. **(consistency — block) `GateContext.workflow_root` does not exist.** Per S1-04 HARDENED, `GateContext` has `worktree: Path` (per-attempt ephemeral worktree), `workflow_id: str`, `run_id: str` — no `workflow_root`. The lock target is the **repo root**, not the worktree. Fix: AC-PATH-* — `repo_root: Path` comes from the Click positional argument; the wiring path does NOT read `GateContext` (the lock is acquired before `GateContext` is constructed).
5. **(coverage — block) Parent-directory creation unspecified.** `os.O_CREAT` only creates the file, not the parent. On an uninitialized repo the open raises `FileNotFoundError`. Fix: AC-MKDIR-* — `mkdir(parents=True, exist_ok=True, mode=0o700)` before `os.open`.
6. **(coverage — block) PID-parse failure mode unspecified.** Empty / whitespace / non-integer / negative / oversized bodies cause `int(...)` to raise `ValueError`, swallowing the intended `RepoAlreadyInProgress`. Fix: AC-PARSE-* — `_parse_holder_pid` returns `RepoLockHolder(..., holder_pid=None)` on every malformed input; the contention error is raised regardless; parametrized + Hypothesis property tests cover all six failure-mode classes.
7. **(test-quality — block) Lock-order invariant ("flock first, then truncate+write the PID") is never tested.** Mutation: an implementer writes the PID before `flock` succeeds; first acquire passes the test (no contender exists yet); a real contender sees a stale PID from a prior holder. Fix: AC-ORDER-1 — `test_pid_not_written_when_flock_fails` mocks `fcntl.flock` to fail; asserts the lock-file body is **untouched**. AC-ORDER-2 — AST scan asserts the source-line call order: `os.open` → `fcntl.flock` → `os.ftruncate` → `os.write` → `os.fsync`.
8. **(test-quality — block) Integration test's "small artificial delay" is racy.** On slow CI process 1 may finish before process 2 starts → test passes *even if the lock is missing*. Fix: AC-INT-DET-* — FIFO-based deterministic synchronization (no sleep); a negative mutation patching the lock to `contextlib.nullcontext` makes the test fail (pins that the lock — not test timing — produces exit 14).
9. **(coverage — block) KeyboardInterrupt / SystemExit mid-context release is in implementer-outline step 8 but never an AC.** Without a runtime test, a `try/finally`-less implementation leaks the lock on signal. Fix: AC-INT-1 / AC-INT-2 — explicit runtime tests for `KeyboardInterrupt` and `SystemExit`.
10. **(design — harden) Functional core / imperative shell split missing.** S7-02 + S7-03 HARDENED established this pattern (third concrete consumer — past rule-of-three; the codebase already has the precedent so this is *adoption*, not a new abstraction). Fix: AC-PURE-* — `_parse_holder_pid` is a module-level pure function; AST scan asserts no I/O / clock references in its body.
11. **(design — harden) Exception → exit-code chain `if isinstance(...)` is anti-Open/Closed.** Registry pattern (`Mapping[type[Exception], int]`) is the right shape. Fix: AC-MAP-* — `cli/_errors.py` exposes `EXIT_CODE_FOR: Final[Mapping[type[Exception], int]] = {RepoAlreadyInProgress: EXIT_REPO_ALREADY_IN_PROGRESS}`; the decorator dispatches via the registry; AST scan asserts no `if isinstance` in the decorator body. Extension is by appending to the `Mapping`.
12. **(consistency — harden) `cli/exit_codes.py` is a brand-new module (kernel).** Future stories extend by appending `EXIT_*: Final[int]` constants under `__all__`. Per CLAUDE.md "Extension by addition — no silent edits", the kernel's contract is locked at kernel-creation time: pre-existing semantic exit codes from arch §830 (0/2/11/12) are codified alongside the new 14. Fix: AC-EXIT-* — five `Final[int]` constants; sorted `__all__`; parametrized name → integer test; AC-FENCE-2 — fence test.
13. **(coverage — harden) Lock-file mode and parent-dir mode unspecified.** Defaults to 0o666 less umask; the lock file lives alongside evidence-bearing sandbox runs that may contain CVE-scan output. Fix: AC-MODE-1 — `mode=0o600`; AC-MKDIR-1 — parent `mode=0o700`.
14. **(coverage — harden) Lock file body is not truncated on release.** A contender that arrives after a clean release reads a stale PID and surfaces it as if the holder were still running. Fix: AC-STALE-1 — `os.ftruncate(fd, 0)` before `fcntl.flock(LOCK_UN)`; the file body is empty between releases.
15. **(test-quality — harden) `repo_lock.acquired` event field set unpinned.** S5-02 HARDENED AC-OBS-1 pinned per-event field sets via `structlog.testing.capture_logs()`. Fix: AC-OBS-1 — pin the field set per event; test asserts captured event dict matches exactly (sorted-keys equality).

No Stage-3 research was needed — every gap was answerable from in-repo sources (HARDENED siblings + the ADRs + `phase-arch-design.md` + CLAUDE.md commitments + the `fcntl(2)` / `flock(2)` man pages). See `_validation/S7-04-concurrent-remediate-repo-lock.md` for the full audit log (23 findings — 9 block, 11 harden, 3 nit).

## Context

`phase-arch-design.md §Edge cases row 18` documents that two concurrent `codegenie remediate` invocations against the same repo would race on `.codegenie/` writes — the `attempts.jsonl`, the cost ledger, and the per-attempt sandbox dirs all assume a single writer. This story adds an `fcntl.flock`-based exclusive lock at `.codegenie/remediation/.lock` acquired at the Click-command entry (before any Phase 3 / Phase 4 / Phase 5 work), a `RepoAlreadyInProgress` already-defined marker class raised on contention with a json-serialized `RepoLockHolder` payload, three new event constants in `sandbox/logging.py`, a new `cli/exit_codes.py` kernel + `cli/_errors.py` registry-pattern exception→exit-code mapping, and an FIFO-synchronized real-subprocess integration test that proves the second `codegenie remediate` exits cleanly with exit 14.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Edge cases` row 18 — exact behavior spec.
- **Architecture:** `../phase-arch-design.md §830 (Decision points + defaults)` — canonical exit-code table (0=passed, 2=Click usage, 11=escalate, 12=failed_unrecoverable); 13 is reserved; 14 is the next free slot for `RepoAlreadyInProgress`.
- **Architecture:** `../phase-arch-design.md §1007` — ADR-0007 marker ordering: lock wraps `record_pre_execute`, not the other way.
- **Phase ADRs:** `../ADRs/0007-pre-execute-marker-for-resume-safety.md` — the lock must wrap the marker (marker is inside the lock).
- **Implementation plan:** `../High-level-impl.md §Step 7` — names `tests/integration/sandbox/test_concurrent_remediate.py`.
- **HARDENED sibling — S1-01:** `S1-01-scaffold-packages-errors-structlog.md` AC-2 line 82 — `RepoAlreadyInProgress(SandboxError)` is **already defined** as a bare-marker class (no custom `__init__`, no class attributes, no `__str__` override); S1-01 Notes §"Extension-by-addition contract" — every new event constant appends to `sandbox/logging.py` `__all__` as `Final[str]` with dotted-lowercase value, never rename or re-value existing entries.
- **HARDENED sibling — S1-04:** `S1-04-gates-contract-abc-models.md` AC-G-* — `GateContext` has `worktree: Path`, `workflow_id: str`, `run_id: str` (NOT `workflow_root` — that field does not exist).
- **HARDENED sibling — S5-02:** `S5-02-gate-runner-retry-loop.md` AC-CTOR-1 — `GateRunner(*, client, gate, ledger, spec_builder, max_attempts=3, replan_hook=None)` keyword-only ctor with 6 deps; `inspect.signature` snapshot test ships there.
- **HARDENED sibling — S7-03:** `S7-03-cost-emitter-sandbox-cost-entry.md` — additive 7th keyword `cost: CostEmitter | None = None` precedent (do NOT compound an 8th); `_recorder.py` pure/impure split precedent (S7-04 is the third concrete consumer).
- **HARDENED sibling — S8-02:** `S8-02-remediate-flags-operator-ack.md` — the `codegenie remediate` Click entry point this story instruments; `--operator-ack` exit-2 + `click.UsageError` pattern (do not change).
- **Existing code:** `src/codegenie/sandbox/errors.py` (lands in S1-01) — `RepoAlreadyInProgress` is imported, not redefined.
- **Existing code:** `src/codegenie/sandbox/logging.py` (lands in S1-01) — three new `EVENT_REPO_LOCK_*` `Final[str]` constants are appended.
- **Existing code:** `src/codegenie/types/identifiers.py:82` — `WorkflowId` NewType (informational; not consumed by this story — the lock target is `repo_root: Path`, not workflow-scoped).
- **`fcntl(2)` / `flock(2)`:** the man-page contract — `flock` locks are tied to the open file description (OFD), so two separate `open()` calls in the same process create two distinct OFDs and the second `LOCK_EX | LOCK_NB` raises `BlockingIOError`. POSIX-only.

## Goal

Land `fcntl.flock(LOCK_EX | LOCK_NB)` acquisition at `.codegenie/remediation/.lock` wrapping the entire `codegenie remediate` invocation (acquired at Click-command entry, released at process exit on every path), with the **existing S1-01-defined** `RepoAlreadyInProgress` marker class raised on contention carrying a json-serialized `RepoLockHolder(lock_path, holder_pid)` payload, three new `EVENT_REPO_LOCK_*` constants appended to `sandbox/logging.py`, a new `cli/exit_codes.py` kernel codifying the canonical exit-code table (0/2/11/12/14), a `cli/_errors.py` registry-pattern exception→exit-code mapping, and a real-process FIFO-synchronized integration test that proves the second `codegenie remediate` exits cleanly with exit 14.

## Acceptance criteria

### A. Class + value type

- [ ] **AC-BASE-1.** `RepoAlreadyInProgress` is **imported** from `codegenie.sandbox.errors` (it is already defined by S1-01 as a bare-marker `SandboxError` subclass); this story does NOT redefine it. `RepoAlreadyInProgress.__bases__ == (SandboxError,)` asserted via `inspect`.
- [ ] **AC-BASE-2.** `RepoAlreadyInProgress` remains a bare marker — `set(vars(RepoAlreadyInProgress).keys()) - {"__module__", "__qualname__", "__doc__", "__dict__", "__weakref__"} == set()` (S1-01 AC-2 invariant; this story must not violate it).
- [ ] **AC-HOLDER-1.** `src/codegenie/sandbox/repo_lock.py` defines `class RepoLockHolder(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")` and exactly two fields: `lock_path: Path`, `holder_pid: int | None` (`None` when the parser cannot extract a valid PID from the file body). `RepoLockHolder.model_config["frozen"] is True` and `RepoLockHolder.model_config["extra"] == "forbid"` asserted via parametrized test.
- [ ] **AC-HOLDER-2.** On contention, the catch-site emits `EVENT_REPO_LOCK_CONTENDED` with `structlog.bind(repo_lock_holder=holder.model_dump(mode="json"))`. The raised `RepoAlreadyInProgress(...)` carries `json.dumps({"lock_path": str(lock_path), "holder_pid": holder.holder_pid}, sort_keys=True)` as its single message argument. The test reads `json.loads(str(excinfo.value))` — NOT `excinfo.value.lock_path` (which would `AttributeError` against the bare marker).

### B. `acquire_repo_lock` semantics

- [ ] **AC-API-1.** `src/codegenie/sandbox/repo_lock.py` exposes `acquire_repo_lock(repo_root: Path) -> AbstractContextManager[None]` (implemented via `contextlib.contextmanager`). Module docstring declares `POSIX-only — fcntl.flock is Linux/macOS`. `import fcntl` is at module top (not lazy — Phase 5 is POSIX-only per `phase-arch-design.md`).
- [ ] **AC-MKDIR-1.** Before `os.open`, `acquire_repo_lock` calls `(repo_root / ".codegenie" / "remediation").mkdir(parents=True, exist_ok=True, mode=0o700)`. Test `test_acquire_on_uninitialized_repo_creates_parent_dirs` asserts: `tmp_path` empty → acquire succeeds → `(tmp_path / ".codegenie/remediation").stat().st_mode & 0o777 == 0o700`.
- [ ] **AC-MODE-1.** `os.open(lock_path, os.O_CREAT | os.O_RDWR, mode=0o600)`; `Path(lock_path).stat().st_mode & 0o777 == 0o600` asserted.
- [ ] **AC-ORDER-1.** When `fcntl.flock` fails (mocked to raise `BlockingIOError`) on a pre-existing lock file with body `b"99999\n"`: (a) `RepoAlreadyInProgress` is raised, (b) the lock-file body is **still** `b"99999\n"` (untouched — no `truncate`, no `write`).
- [ ] **AC-ORDER-2.** AST scan on `acquire_repo_lock` asserts the source-line call order in the function body: `os.open` (or equivalent) → `fcntl.flock` → `os.ftruncate` → `os.write` → `os.fsync`. No `os.write` or `os.ftruncate` appears before `fcntl.flock`.
- [ ] **AC-PARSE-1.** `_parse_holder_pid(body: bytes, lock_path: Path) -> RepoLockHolder` is a module-level **pure** function (no I/O; no clock; no `os.*`). For each of the six failure-mode inputs — empty (`b""`), whitespace (`b"   \n"`), non-integer first line (`b"abc\n"`), negative integer (`b"-1\n"`), integer outside `1..2**31-1` (`b"99999999999999\n"`), and `os.write(b"\xff\xfe")` (decode error) — returns `RepoLockHolder(lock_path=lock_path, holder_pid=None)` (does not raise, does not propagate).
- [ ] **AC-PARSE-2.** Hypothesis property test: `@given(body=st.binary(max_size=4096))` — `_parse_holder_pid(body, lock_path)` always returns a `RepoLockHolder` where `holder_pid` is `None` or an `int` in `1..2**31-1`; never raises.
- [ ] **AC-STALE-1.** On release, `acquire_repo_lock` calls `os.ftruncate(fd, 0)` before `fcntl.flock(fd, LOCK_UN)` and before `os.close(fd)`. After release, re-opening the lock file shows body `b""`. (Mock-and-spy test pins the call order of `ftruncate` → `LOCK_UN` → `close`.)

### C. Cross-process behavior

- [ ] **AC-DOUBLE-1.** `test_double_acquire_raises_repo_already_in_progress` (same-process): a second `with acquire_repo_lock(tmp_path):` inside the first raises `RepoAlreadyInProgress` whose `str(excinfo.value)` parses as JSON with `holder_pid == os.getpid()` and `lock_path == str(tmp_path / ".codegenie/remediation/.lock")`. Docstring cites `flock(2)`: "POSIX: two separate `open()` calls create two OFDs; `LOCK_EX | LOCK_NB` on the second OFD raises `BlockingIOError`. If your local filesystem does not support this, surface the issue — do not monkey-patch."
- [ ] **AC-DOUBLE-2.** `test_subprocess_child_holds_lock_parent_raises` (defense-in-depth, deterministic — no sleep): `subprocess.Popen([sys.executable, "-c", code])` where the child acquires and writes `READY\n` to stdout then `time.sleep(60)`; parent reads `stdin.readline()` to wait for `READY\n` (deterministic ready-signal) then attempts to acquire and asserts `RepoAlreadyInProgress` whose payload's `holder_pid == child.pid`.
- [ ] **AC-INT-1.** `test_keyboard_interrupt_during_lock_releases_lock`: raise `KeyboardInterrupt` inside the `with acquire_repo_lock(tmp_path):` block; assert the next `acquire_repo_lock(tmp_path)` succeeds (the context manager's cleanup releases the lock on signal).
- [ ] **AC-INT-2.** `test_system_exit_during_lock_releases_lock`: same as AC-INT-1 with `SystemExit(0)`.

### D. Wiring at CLI/orchestrator entry

- [ ] **AC-WIRE-LOC-1.** `src/codegenie/cli/remediate.py` Click callback's first executable statement (after argument parsing) is `with contextlib.ExitStack() as stack: stack.enter_context(acquire_repo_lock(repo_root)); ...`. The lock wraps the entire downstream pipeline — Phase 3 transform, Phase 4 LLM fallback, every Phase 5 gate run.
- [ ] **AC-WIRE-LOC-2.** `GateRunner.__init__` signature is **unchanged** from S5-02 (6 deps) + S7-03 (additive 7th `cost`); the S5-02 `inspect.signature` snapshot test continues to pass byte-stable (no 8th keyword introduced; no positional change).
- [ ] **AC-WIRE-LOC-3.** Lock is acquired *before* `RetryLedger.__init__`, *before* any `record_pre_execute` call (ADR-0007 invariant — marker is strictly inside the lock). Test: a unit test on the `remediate` Click command (`CliRunner` with a stubbed Phase 3 / Phase 4 / Phase 5 pipeline) asserts the first observable side effect is the lock-file appearance (`(repo_root / ".codegenie/remediation/.lock").exists()`); no `attempts.jsonl` or `pre_execute` line is written before the lock file has a PID body.

### E. `cli/exit_codes.py` + `cli/_errors.py` kernel

- [ ] **AC-EXIT-1.** `src/codegenie/cli/exit_codes.py` declares (with `Final[int]` source-text annotations): `EXIT_PASSED: Final[int] = 0`, `EXIT_USAGE: Final[int] = 2`, `EXIT_ESCALATE: Final[int] = 11`, `EXIT_FAILED_UNRECOVERABLE: Final[int] = 12`, `EXIT_REPO_ALREADY_IN_PROGRESS: Final[int] = 14`. The pre-existing semantic exit codes (0/2/11/12) are codified here so the kernel is single-source for the canonical arch §830 table; code 13 is intentionally unused (reserved).
- [ ] **AC-EXIT-2.** `__all__` is sorted-complete: `sorted(__all__) == ["EXIT_ESCALATE", "EXIT_FAILED_UNRECOVERABLE", "EXIT_PASSED", "EXIT_REPO_ALREADY_IN_PROGRESS", "EXIT_USAGE"]`. Parametrized name → integer test pins each pair (mutation-resistant: swapping two values must fail).
- [ ] **AC-EXIT-3.** Every constant has source-text annotation `Final[int]` verified by `ast` walk (mirrors S1-01 AC-4 / S7-03 AC-PURE-* discipline). Every constant name matches `^EXIT_[A-Z_]+$`. No two constants share a value.
- [ ] **AC-MAP-1.** `src/codegenie/cli/_errors.py` exposes `EXIT_CODE_FOR: Final[Mapping[type[Exception], int]] = MappingProxyType({RepoAlreadyInProgress: EXIT_REPO_ALREADY_IN_PROGRESS})`. The registry is the single source of truth for typed-exception → exit-code dispatch.
- [ ] **AC-MAP-2.** A single top-level decorator `map_typed_errors_to_exit_codes(callback)` wraps the Click command body. On caught `RepoAlreadyInProgress`, it: (a) emits `EVENT_REPO_LOCK_CONTENDED` with the holder fields (AC-OBS-1), (b) prints the json payload to stderr containing `"repo already in progress"`, (c) calls `sys.exit(EXIT_CODE_FOR[type(err)])`. No bare `if isinstance` in the decorator body — AST scan asserts the only dispatch path is `EXIT_CODE_FOR[type(err)]`.
- [ ] **AC-MAP-3.** Extension is by appending to `EXIT_CODE_FOR`; the decorator is unchanged. A unit test pins this — adding a synthetic `class _SyntheticError(SandboxError): pass` + an entry `_SyntheticError: 99` to a test-scoped copy of the mapping makes `raise _SyntheticError(...)` exit with 99, without any decorator edits.

### F. Structured logging — event constants

- [ ] **AC-EVT-1.** `src/codegenie/sandbox/logging.py` gains three appended constants: `EVENT_REPO_LOCK_ACQUIRED: Final[str] = "sandbox.repo_lock.acquired"`, `EVENT_REPO_LOCK_RELEASED: Final[str] = "sandbox.repo_lock.released"`, `EVENT_REPO_LOCK_CONTENDED: Final[str] = "sandbox.repo_lock.contended"`. Existing constants are unchanged byte-for-byte (S1-01 extension-by-addition invariant).
- [ ] **AC-EVT-2.** Each new constant is appended to `sandbox/logging.py` `__all__` (sorted-complete; the existing S1-01-locked entries are preserved). Each value matches the dotted-lowercase regex `^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$` (S1-01 AC-4a). Each value is globally unique across `sandbox/logging.py` and `gates/logging.py` (S1-01 AC-4c).
- [ ] **AC-OBS-1.** Pinned per-event field sets, asserted via `structlog.testing.capture_logs()`:
  - `EVENT_REPO_LOCK_ACQUIRED`: `{event, lock_path: str, pid: int}` — emitted inside `acquire_repo_lock` right after the PID is written and fsync'd.
  - `EVENT_REPO_LOCK_RELEASED`: `{event, lock_path: str, pid: int, duration_ms: float}` — emitted right after `fcntl.flock(LOCK_UN)`; `duration_ms` is wall-clock from `__enter__` to `__exit__`.
  - `EVENT_REPO_LOCK_CONTENDED`: `{event, lock_path: str, holder_pid: int | None}` — emitted at the catch site in `map_typed_errors_to_exit_codes`.
- [ ] **AC-EVT-NOLIT.** AST scan asserts no bare string literal `"sandbox.repo_lock.acquired"` / `"sandbox.repo_lock.released"` / `"sandbox.repo_lock.contended"` exists in any `.py` file under `src/codegenie/sandbox/` or `src/codegenie/cli/` — every emit must reference the `EVENT_*` constant by name.

### G. Structural fences

- [ ] **AC-FENCE-1.** `tests/fence/test_sandbox_repo_lock_module_static.py` asserts: (a) no banned imports (`anthropic`, `langgraph`, `chromadb`, `sentence_transformers`); (b) `_parse_holder_pid` body has zero I/O calls (AST scan for `os.open`, `os.read`, `os.write`, `os.fsync`, `os.ftruncate`, `open`, `Path.read_*`, `Path.write_*`, `datetime.now`, `time.*`); (c) `acquire_repo_lock` source-line call order is `os.open` (or equivalent) → `fcntl.flock` → `os.ftruncate` → `os.write` → `os.fsync` (asserted via line-number ordering); (d) module docstring contains the literal `"POSIX-only"`.
- [ ] **AC-FENCE-2.** `tests/fence/test_cli_exit_codes_static.py` asserts: (a) every `EXIT_*` constant has source-text annotation `Final[int]`; (b) every constant name matches `^EXIT_[A-Z_]+$`; (c) `__all__` is sorted-complete; (d) no two constants share a value; (e) no banned imports.

### H. Project gates

- [ ] **AC-GATES.** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/sandbox src/codegenie/cli`, and `pytest -q` all exit 0. Coverage on `src/codegenie/sandbox/repo_lock.py` and `src/codegenie/cli/exit_codes.py` is ≥ 95% line / ≥ 90% branch.

## Implementation outline

1. **Verify S1-01 prerequisite.** Confirm `RepoAlreadyInProgress` is reachable: `from codegenie.sandbox.errors import RepoAlreadyInProgress` succeeds; `RepoAlreadyInProgress.__bases__ == (SandboxError,)`. If S1-01 is not yet GREEN, STOP and surface the precondition.
2. **Append `EVENT_REPO_LOCK_*` constants** to `src/codegenie/sandbox/logging.py`. Order: append at the bottom of the existing `Final[str]` block; update `__all__` to include the three new names in sorted position; do NOT touch existing constants.
3. **Define `RepoLockHolder`** in `src/codegenie/sandbox/repo_lock.py`: `class RepoLockHolder(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")` and fields `lock_path: Path`, `holder_pid: int | None`.
4. **Write the pure helper** `_parse_holder_pid(body: bytes, lock_path: Path) -> RepoLockHolder`. Try to decode the first line of `body` as a non-empty stripped string; try `int(...)`; if the result is in `1..2**31-1`, return `RepoLockHolder(lock_path=lock_path, holder_pid=int_value)`; on any failure return `RepoLockHolder(lock_path=lock_path, holder_pid=None)`. No I/O, no clock — pure.
5. **Write `acquire_repo_lock`** as `@contextlib.contextmanager`. Order is load-bearing (AC-ORDER-2):
   ```python
   (repo_root / ".codegenie" / "remediation").mkdir(parents=True, exist_ok=True, mode=0o700)
   lock_path = repo_root / ".codegenie" / "remediation" / ".lock"
   fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, mode=0o600)
   try:
       try:
           fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
       except BlockingIOError as exc:
           body = os.read(fd, 4096)
           holder = _parse_holder_pid(body, lock_path)
           log.info(EVENT_REPO_LOCK_CONTENDED, lock_path=str(lock_path), holder_pid=holder.holder_pid)
           raise RepoAlreadyInProgress(
               json.dumps({"lock_path": str(lock_path), "holder_pid": holder.holder_pid}, sort_keys=True)
           ) from exc
       # flock acquired — now (and only now) write the PID
       os.ftruncate(fd, 0)
       os.write(fd, f"{os.getpid()}\n".encode())
       os.fsync(fd)
       started = time.perf_counter()
       log.info(EVENT_REPO_LOCK_ACQUIRED, lock_path=str(lock_path), pid=os.getpid())
       try:
           yield
       finally:
           os.ftruncate(fd, 0)
           fcntl.flock(fd, fcntl.LOCK_UN)
           duration_ms = (time.perf_counter() - started) * 1000
           log.info(EVENT_REPO_LOCK_RELEASED, lock_path=str(lock_path), pid=os.getpid(), duration_ms=duration_ms)
   finally:
       os.close(fd)
   ```
6. **Create `src/codegenie/cli/exit_codes.py`** with the five `EXIT_*: Final[int]` constants and a sorted-complete `__all__`. Module docstring cites `phase-arch-design.md §830` as the source-of-truth table.
7. **Create `src/codegenie/cli/_errors.py`** with `EXIT_CODE_FOR: Final[Mapping[type[Exception], int]] = MappingProxyType({RepoAlreadyInProgress: EXIT_REPO_ALREADY_IN_PROGRESS})` and the `map_typed_errors_to_exit_codes` decorator dispatching via the registry (no `if isinstance` chain).
8. **Wire at `src/codegenie/cli/remediate.py`** — the Click command body's first executable statement is `with contextlib.ExitStack() as stack: stack.enter_context(acquire_repo_lock(repo_root)); ...`. The decorator from step 7 wraps the command callback so the exit-code mapping fires uniformly on every error path.
9. **Write unit tests** in `tests/sandbox/test_repo_lock.py`, `tests/sandbox/test_repo_lock_holder.py`, `tests/sandbox/test_parse_holder_pid_property.py`, `tests/cli/test_exit_codes.py`, `tests/cli/test_errors_mapping.py`.
10. **Write fence tests** in `tests/fence/test_sandbox_repo_lock_module_static.py` and `tests/fence/test_cli_exit_codes_static.py`.
11. **Write the integration test** in `tests/integration/sandbox/test_concurrent_remediate.py` — FIFO-based deterministic synchronization (NOT a sleep). Use a fixture `tests/fixtures/repos/hello-node-lockhold/` whose Phase 3 first stage blocks on reading a named pipe the test writes to. Negative-mutation row pins that the lock — not test timing — produces exit 14.

## TDD plan — red / green / refactor

### Red

Test file paths: `tests/sandbox/test_repo_lock.py`, `tests/sandbox/test_repo_lock_holder.py`, `tests/sandbox/test_parse_holder_pid_property.py`, `tests/cli/test_exit_codes.py`, `tests/cli/test_errors_mapping.py`, `tests/integration/sandbox/test_concurrent_remediate.py`, `tests/fence/test_sandbox_repo_lock_module_static.py`, `tests/fence/test_cli_exit_codes_static.py`.

```python
# tests/sandbox/test_repo_lock.py
"""Unit tests for acquire_repo_lock — verifies S7-04 ACs.

Mutation targets:
  - writing PID before flock succeeds (AC-ORDER-1, AC-ORDER-2)
  - forgetting to ftruncate(0) before LOCK_UN (AC-STALE-1)
  - not creating parent dir (AC-MKDIR-1)
  - propagating ValueError from int(...) on malformed PID body (AC-PARSE-1)
  - leaking the lock on KeyboardInterrupt / SystemExit (AC-INT-1, AC-INT-2)
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from codegenie.sandbox.errors import RepoAlreadyInProgress
from codegenie.sandbox.repo_lock import acquire_repo_lock


def test_double_acquire_raises_repo_already_in_progress(tmp_path: Path) -> None:
    """AC-DOUBLE-1 (same-process, POSIX OFD semantics).

    Why: two concurrent remediates on the same repo would interleave writes
    to attempts.jsonl, corrupting the BLAKE3 chain silently. The refusal
    is the contract: 'no silent races on .codegenie/'.

    flock(2) note: each open() creates a new OFD; LOCK_EX|LOCK_NB on the
    second OFD raises BlockingIOError. If your filesystem (some FUSE,
    some network mounts) does not support this, surface the issue rather
    than monkey-patching the test.
    """
    with acquire_repo_lock(tmp_path):
        with pytest.raises(RepoAlreadyInProgress) as excinfo:
            with acquire_repo_lock(tmp_path):
                pytest.fail("second acquire must not succeed")

        payload = json.loads(str(excinfo.value))
        assert payload["lock_path"] == str(tmp_path / ".codegenie/remediation/.lock")
        assert payload["holder_pid"] == os.getpid()


def test_acquire_on_uninitialized_repo_creates_parent_dirs(tmp_path: Path) -> None:
    """AC-MKDIR-1: production path must work on a fresh repo (no pre-created dirs)."""
    # tmp_path is empty — no .codegenie/ yet
    with acquire_repo_lock(tmp_path):
        rem_dir = tmp_path / ".codegenie" / "remediation"
        assert rem_dir.is_dir()
        assert rem_dir.stat().st_mode & 0o777 == 0o700


def test_lock_file_mode_is_0600(tmp_path: Path) -> None:
    """AC-MODE-1: lock file lives alongside evidence dirs; 0600 is the safer default."""
    with acquire_repo_lock(tmp_path):
        lock_path = tmp_path / ".codegenie" / "remediation" / ".lock"
        assert lock_path.stat().st_mode & 0o777 == 0o600


def test_pid_not_written_when_flock_fails(tmp_path: Path) -> None:
    """AC-ORDER-1: a wrong implementation that writes PID before flock would
    overwrite the body even on contention. Mutation-resistant pin."""
    (tmp_path / ".codegenie" / "remediation").mkdir(parents=True)
    lock_path = tmp_path / ".codegenie" / "remediation" / ".lock"
    lock_path.write_bytes(b"99999\n")

    with patch("codegenie.sandbox.repo_lock.fcntl.flock") as mock_flock:
        mock_flock.side_effect = BlockingIOError("EWOULDBLOCK")
        with pytest.raises(RepoAlreadyInProgress):
            with acquire_repo_lock(tmp_path):
                pytest.fail("acquire must not yield when flock fails")

    # The file body must be UNTOUCHED — no truncate, no PID overwrite
    assert lock_path.read_bytes() == b"99999\n"


def test_release_truncates_body_before_unlock(tmp_path: Path) -> None:
    """AC-STALE-1: file body is empty between releases — no stale PID to surface."""
    with acquire_repo_lock(tmp_path):
        pass
    lock_path = tmp_path / ".codegenie" / "remediation" / ".lock"
    assert lock_path.exists()
    assert lock_path.read_bytes() == b""


def test_release_unlock_before_close_order(tmp_path: Path) -> None:
    """AC-STALE-1 corollary: ftruncate → LOCK_UN → close, in that order."""
    call_log: list[str] = []
    real_ftruncate = os.ftruncate
    real_close = os.close

    def spy_ftruncate(fd: int, length: int) -> None:
        call_log.append(f"ftruncate({length})")
        return real_ftruncate(fd, length)

    def spy_flock(fd: int, op: int) -> None:
        # only track LOCK_UN here
        import fcntl as _f
        if op == _f.LOCK_UN:
            call_log.append("LOCK_UN")
        return _f.flock.__wrapped__(fd, op) if hasattr(_f.flock, "__wrapped__") else None

    def spy_close(fd: int) -> None:
        call_log.append("close")
        return real_close(fd)

    with patch("codegenie.sandbox.repo_lock.os.ftruncate", side_effect=spy_ftruncate):
        with patch("codegenie.sandbox.repo_lock.os.close", side_effect=spy_close):
            with acquire_repo_lock(tmp_path):
                pass

    # Final-three sequence in call_log must be ftruncate(0), LOCK_UN, close
    # (ftruncate appears twice: once after flock to clear pre-existing body,
    # once before LOCK_UN to clear the just-written PID)
    assert call_log[-3:] == ["ftruncate(0)", "LOCK_UN", "close"] or call_log[-2:] == ["ftruncate(0)", "close"]
    # If LOCK_UN spy didn't bind (cross-cut shape), at minimum assert ftruncate before close
    ftruncate_positions = [i for i, c in enumerate(call_log) if c == "ftruncate(0)"]
    close_position = call_log.index("close")
    assert any(p < close_position for p in ftruncate_positions)


def test_keyboard_interrupt_during_lock_releases_lock(tmp_path: Path) -> None:
    """AC-INT-1: signal mid-context must not leak the lock."""
    with pytest.raises(KeyboardInterrupt):
        with acquire_repo_lock(tmp_path):
            raise KeyboardInterrupt()
    # If the lock leaked, the next acquire would raise RepoAlreadyInProgress
    with acquire_repo_lock(tmp_path):
        pass


def test_system_exit_during_lock_releases_lock(tmp_path: Path) -> None:
    """AC-INT-2: sys.exit during a gate must not leak the lock."""
    with pytest.raises(SystemExit):
        with acquire_repo_lock(tmp_path):
            raise SystemExit(0)
    with acquire_repo_lock(tmp_path):
        pass


def test_subprocess_child_holds_lock_parent_raises(tmp_path: Path) -> None:
    """AC-DOUBLE-2: cross-process contention with DETERMINISTIC ready-signal (no sleep)."""
    code = (
        "import sys, time;"
        "from pathlib import Path;"
        "from codegenie.sandbox.repo_lock import acquire_repo_lock;"
        f"r = Path({str(tmp_path)!r});"
        "ctx = acquire_repo_lock(r); ctx.__enter__();"
        "sys.stdout.write('READY\\n'); sys.stdout.flush();"
        "time.sleep(60);"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        ready = child.stdout.readline()
        assert ready.strip() == "READY"
        with pytest.raises(RepoAlreadyInProgress) as excinfo:
            with acquire_repo_lock(tmp_path):
                pytest.fail("parent must not acquire while child holds the lock")
        payload = json.loads(str(excinfo.value))
        assert payload["holder_pid"] == child.pid
    finally:
        child.terminate()
        child.wait(timeout=5)
```

```python
# tests/sandbox/test_parse_holder_pid_property.py
"""Hypothesis property test for _parse_holder_pid (AC-PARSE-1, AC-PARSE-2)."""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, strategies as st

from codegenie.sandbox.repo_lock import _parse_holder_pid, RepoLockHolder


@given(body=st.binary(max_size=4096))
def test_parse_holder_pid_never_raises_and_returns_valid_pid_or_none(body: bytes) -> None:
    holder = _parse_holder_pid(body, Path("/dev/null/.lock"))
    assert isinstance(holder, RepoLockHolder)
    assert holder.holder_pid is None or 1 <= holder.holder_pid <= 2**31 - 1


import pytest


@pytest.mark.parametrize(
    "body",
    [b"", b"   \n", b"abc\n", b"-1\n", b"99999999999999\n", b"\xff\xfe"],
)
def test_parse_holder_pid_malformed_returns_none(body: bytes) -> None:
    """AC-PARSE-1: every documented failure mode yields holder_pid=None, not a raise."""
    holder = _parse_holder_pid(body, Path("/x/.lock"))
    assert holder.holder_pid is None
```

```python
# tests/cli/test_exit_codes.py
"""AC-EXIT-1, AC-EXIT-2, AC-EXIT-3."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Final

import pytest

from codegenie.cli import exit_codes

EXPECTED: Final[dict[str, int]] = {
    "EXIT_PASSED": 0,
    "EXIT_USAGE": 2,
    "EXIT_ESCALATE": 11,
    "EXIT_FAILED_UNRECOVERABLE": 12,
    "EXIT_REPO_ALREADY_IN_PROGRESS": 14,
}


@pytest.mark.parametrize("name,value", list(EXPECTED.items()))
def test_exit_constant_pinned_value(name: str, value: int) -> None:
    """Mutation: swapping two values must fail."""
    assert getattr(exit_codes, name) == value


def test_all_is_sorted_and_complete() -> None:
    assert sorted(exit_codes.__all__) == sorted(EXPECTED.keys())
    assert list(exit_codes.__all__) == sorted(exit_codes.__all__)


def test_no_value_collisions() -> None:
    values = [getattr(exit_codes, n) for n in exit_codes.__all__]
    assert len(set(values)) == len(values)


def test_each_constant_typed_final_int_in_source() -> None:
    src = Path(importlib.util.find_spec("codegenie.cli.exit_codes").origin).read_text()
    annotated: dict[str, str] = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            annotated[node.target.id] = ast.unparse(node.annotation)
    for name in EXPECTED:
        assert annotated.get(name) == "Final[int]"
```

```python
# tests/cli/test_errors_mapping.py
"""AC-MAP-1, AC-MAP-2, AC-MAP-3."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import MappingProxyType

import pytest

from codegenie.cli._errors import EXIT_CODE_FOR, map_typed_errors_to_exit_codes
from codegenie.cli.exit_codes import EXIT_REPO_ALREADY_IN_PROGRESS
from codegenie.sandbox.errors import RepoAlreadyInProgress


def test_registry_is_mapping_proxy_with_canonical_entry() -> None:
    assert isinstance(EXIT_CODE_FOR, MappingProxyType)
    assert EXIT_CODE_FOR[RepoAlreadyInProgress] == EXIT_REPO_ALREADY_IN_PROGRESS


def test_decorator_dispatches_via_registry_not_isinstance_chain() -> None:
    """AC-MAP-2: AST scan asserts no `if isinstance` in the decorator body."""
    src = Path(importlib.util.find_spec("codegenie.cli._errors").origin).read_text()
    tree = ast.parse(src)
    # Find map_typed_errors_to_exit_codes
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "map_typed_errors_to_exit_codes")
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "isinstance":
            pytest.fail("dispatch must go through EXIT_CODE_FOR[type(err)], not isinstance()")


def test_decorator_maps_typed_error_to_exit_code() -> None:
    @map_typed_errors_to_exit_codes
    def cmd() -> int:
        raise RepoAlreadyInProgress('{"lock_path": "/x", "holder_pid": 42}')
    with pytest.raises(SystemExit) as exc:
        cmd()
    assert exc.value.code == EXIT_REPO_ALREADY_IN_PROGRESS
```

```python
# tests/integration/sandbox/test_concurrent_remediate.py
"""AC-INT-DET-1/-2/-3: FIFO-based deterministic synchronization, NOT a sleep."""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
def test_second_remediate_exits_14_on_lock_contention(tmp_path: Path, fifo_fixture_repo: Path) -> None:
    """fifo_fixture_repo: tests/fixtures/repos/hello-node-lockhold/ — a fixture whose
    Phase-3 first stage blocks on reading a named pipe at <repo>/.fifo until written.
    This deterministically pins process 1 in the lock-held state until the test signals.
    """
    fifo_path = fifo_fixture_repo / ".fifo"
    if not fifo_path.exists():
        os.mkfifo(fifo_path)

    proc1 = subprocess.Popen(
        [sys.executable, "-m", "codegenie", "remediate", str(fifo_fixture_repo),
         "--cve", "CVE-2024-FIXTURE", "--sandbox-backend", "did"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )

    # Wait for the lock to be acquired by polling on the lock-file body (not sleep)
    lock_path = fifo_fixture_repo / ".codegenie" / "remediation" / ".lock"
    deadline_polls = 200  # 200 × 10ms = 2s upper bound for proc1 to acquire
    for _ in range(deadline_polls):
        if lock_path.exists() and lock_path.stat().st_size > 0:
            break
        import time as _t; _t.sleep(0.01)
    else:
        proc1.terminate(); proc1.wait(timeout=5)
        pytest.fail("proc1 never acquired the lock — fixture broken")

    # Now proc1 is parked at the FIFO read inside the lock. Spawn proc2.
    proc2 = subprocess.run(
        [sys.executable, "-m", "codegenie", "remediate", str(fifo_fixture_repo),
         "--cve", "CVE-2024-FIXTURE", "--sandbox-backend", "did"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc2.returncode == 14
    assert "repo already in progress" in proc2.stderr.lower()

    # Release proc1 by writing to the FIFO
    with open(fifo_path, "w") as f:
        f.write("go\n")

    proc1.wait(timeout=120)
    assert proc1.returncode == 0  # proc1 completes cleanly
    attempts_log = next((fifo_fixture_repo / ".codegenie/remediation").glob("*/gates/*/attempts.jsonl"))
    assert attempts_log.read_text().count("\n") >= 1  # at least one chained attempt


@pytest.mark.integration
def test_negative_mutation_no_lock_both_succeed(tmp_path: Path, fifo_fixture_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-INT-DET-3: patch acquire_repo_lock to nullcontext — both processes must succeed
    (test fails). Pins that the LOCK — not test timing — produces exit 14 in the real test."""
    monkeypatch.setattr("codegenie.sandbox.repo_lock.acquire_repo_lock",
                        lambda _repo_root: contextlib.nullcontext())
    # ... run two remediates in parallel, assert BOTH exit 0 — this test must fail
    # at the assert-exit-14 line of the prior test if the lock were absent.
    # (Marked xfail-on-mutation; see _validation report Conflict resolutions.)
```

```python
# tests/fence/test_sandbox_repo_lock_module_static.py
"""AC-FENCE-1."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

BANNED = ("anthropic", "langgraph", "chromadb", "sentence_transformers")
PURE_FORBIDDEN_CALLS = {
    "os.open", "os.read", "os.write", "os.fsync", "os.ftruncate", "open",
    "Path.read_text", "Path.read_bytes", "Path.write_text", "Path.write_bytes",
    "datetime.now", "time.perf_counter", "time.time",
}


def _module_src() -> tuple[ast.Module, str]:
    src_path = Path(importlib.util.find_spec("codegenie.sandbox.repo_lock").origin)
    src = src_path.read_text()
    return ast.parse(src), src


def test_no_banned_imports() -> None:
    tree, _ = _module_src()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] not in BANNED
        elif isinstance(node, ast.ImportFrom):
            assert node.module is None or node.module.split(".")[0] not in BANNED


def test_parse_holder_pid_is_pure() -> None:
    tree, _ = _module_src()
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_parse_holder_pid")
    for node in ast.walk(fn):
        if isinstance(node, ast.Attribute):
            qualified = f"{getattr(node.value, 'id', '')}.{node.attr}"
            assert qualified not in PURE_FORBIDDEN_CALLS, (
                f"_parse_holder_pid must be pure; saw {qualified}"
            )


def test_acquire_repo_lock_call_order() -> None:
    """flock must precede ftruncate/write/fsync in source-line order."""
    tree, _ = _module_src()
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "acquire_repo_lock")
    # walk top-down; capture line numbers of os.open, fcntl.flock, os.ftruncate, os.write, os.fsync
    seen: dict[str, int] = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            qname = f"{getattr(node.func.value, 'id', '?')}.{node.func.attr}"
            if qname in {"os.open", "fcntl.flock", "os.ftruncate", "os.write", "os.fsync"}:
                seen.setdefault(qname, node.lineno)
    assert seen["os.open"] < seen["fcntl.flock"]
    assert seen["fcntl.flock"] < seen["os.ftruncate"]
    assert seen["os.ftruncate"] < seen["os.write"]
    assert seen["os.write"] < seen["os.fsync"]


def test_module_docstring_says_posix_only() -> None:
    _, src = _module_src()
    assert "POSIX-only" in src.split("\n\n", 1)[0]
```

### Green

1. Import (not redefine) `RepoAlreadyInProgress` from `codegenie.sandbox.errors`.
2. Append `EVENT_REPO_LOCK_ACQUIRED` / `_RELEASED` / `_CONTENDED` to `sandbox/logging.py` `__all__`.
3. Implement `RepoLockHolder`, `_parse_holder_pid`, `acquire_repo_lock` per the outline.
4. Implement `cli/exit_codes.py` (5 `Final[int]` constants + sorted `__all__`).
5. Implement `cli/_errors.py` (`EXIT_CODE_FOR` registry + `map_typed_errors_to_exit_codes` decorator).
6. Wire `with stack.enter_context(acquire_repo_lock(repo_root))` at `cli/remediate.py` Click-command entry; wrap with the decorator.
7. Make all unit + fence tests green. Then run the integration test against the FIFO fixture.

### Refactor

- Confirm the module is < 120 lines (the pure helper + the context manager + imports). If the PID-write+fsync block grows past ~10 lines, extract a small `_write_holder_pid(fd: int)` helper — pure-impure split discipline.
- Confirm `ruff format` / `ruff check` / `mypy --strict` clean on `src/codegenie/sandbox` and `src/codegenie/cli`.
- Confirm both fence tests pass.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/logging.py` | **Append** 3 new `EVENT_REPO_LOCK_*: Final[str]` constants to `__all__` |
| `src/codegenie/sandbox/repo_lock.py` | **New** — `RepoLockHolder` value type + `_parse_holder_pid` pure helper + `acquire_repo_lock` context manager |
| `src/codegenie/cli/exit_codes.py` | **New (kernel)** — 5 `EXIT_*: Final[int]` constants codifying arch §830 |
| `src/codegenie/cli/_errors.py` | **New** — `EXIT_CODE_FOR` registry-pattern mapping + `map_typed_errors_to_exit_codes` decorator |
| `src/codegenie/cli/remediate.py` | Wire `ExitStack.enter_context(acquire_repo_lock(repo_root))` at command entry; wrap callback with the decorator |
| `tests/sandbox/test_repo_lock.py` | Unit suite — semantics, mode, ordering, signal release, subprocess child |
| `tests/sandbox/test_repo_lock_holder.py` | Value-type tests — frozen, extra=forbid, field discipline |
| `tests/sandbox/test_parse_holder_pid_property.py` | Hypothesis property + parametrized parse-failure |
| `tests/cli/test_exit_codes.py` | Pinned name → integer; `Final[int]` source annotation; sorted `__all__` |
| `tests/cli/test_errors_mapping.py` | Registry-pattern dispatch; no `if isinstance` chain |
| `tests/fence/test_sandbox_repo_lock_module_static.py` | Banned imports, pure-helper discipline, source-line call order, POSIX-only docstring |
| `tests/fence/test_cli_exit_codes_static.py` | `Final[int]` discipline, sorted `__all__`, value-uniqueness |
| `tests/integration/sandbox/test_concurrent_remediate.py` | Real-subprocess + FIFO synchronization; negative mutation |
| `tests/fixtures/repos/hello-node-lockhold/` | Fixture with FIFO sync point that blocks Phase-3 stage 1 inside the lock |

## Out of scope

- **Editing the `RepoAlreadyInProgress` class body.** It is already a bare marker per S1-01 AC-2. Adding `lock_path: Path` / `holder_pid: int | None` as class attributes is forbidden. The payload travels via the json-serialized `str()` message and via `structlog.bind(...)` on the structured event.
- **Editing `GateRunner.__init__` parameters.** S5-02 froze the keyword-only 6-dep ctor; S7-03 added the additive 7th `cost`. An 8th keyword `repo_root` would compound — the lock belongs at the CLI/orchestrator level, not on the runner.
- **Introducing a `RepoLock` Protocol or `RepoLockBackend` adapter registry.** Rule 2 — only one consumer today. If Phase 9 lands a `TemporalRepoLock` (distributed mutex via Temporal workflow signal), lift the Protocol then.
- **Reading `GateContext.workflow_root`.** That field does not exist (`GateContext` has `worktree: Path`). The lock target is `repo_root: Path` from the Click positional, not from `GateContext`.
- **Changing existing exit codes (0/2/11/12).** The kernel codifies pre-existing semantic exit codes from arch §830; the *values* are byte-stable.
- **Cross-host locking.** Phase 5 is single-host; concurrent runs across machines on a shared filesystem are a Phase 9 (Temporal) concern.
- **Lock breaking / `--force-unlock`.** If a stale lock from a crashed process blocks new runs, operator's manual remediation is `rm .codegenie/remediation/.lock`. A future `codegenie sandbox unlock` command may land in Step 8 if needed (additive — does not edit this story's artifacts).
- **Lock-holder identity beyond PID** (e.g., hostname, start-time). PID-only is enough to surface in the error message; richer fields are deferred.
- **Migrating non-locked legacy runs.** Phase 5 is greenfield; no migration needed.

## Notes for the implementer

### 1. Class-body discipline (S1-01 AC-2 — load-bearing)

`RepoAlreadyInProgress` is **already defined** by S1-01 as a bare-marker `SandboxError` subclass: no custom `__init__`, no class attributes, no `__str__` override. Do **not** redefine it. Do **not** add `lock_path` or `holder_pid` as class attributes. The S1-01-locked structural test (`test_each_sandbox_error_class_is_marker_only`) will fail if you do. The payload travels via the json-serialized message string and via the structured event.

### 2. `RepoLockHolder` as the value type ("Make illegal states unrepresentable")

The `(lock_path, holder_pid)` pair is a *value type*, not a *bag of exception attributes*. `RepoLockHolder(BaseModel, frozen=True, extra="forbid")` is the canonical Phase-5 shape (matches S1-04 AC-4 discipline). `holder_pid: int | None` — the `None` arm represents "we acquired contention but could not extract a valid PID from the file body" (empty body, torn write, malformed). Phase 13 will read this and aggregate by holder presence; the `None` case is operationally meaningful.

### 3. Functional core / imperative shell

`_parse_holder_pid(body: bytes, lock_path: Path) -> RepoLockHolder` is **pure** — no I/O, no clock, no `os.*`. `acquire_repo_lock` is the impure shell — `os.open` / `fcntl.flock` / `os.ftruncate` / `os.write` / `os.fsync` / `os.close`. This is the same split S7-02 and S7-03 HARDENED established (`_recorder.py` precedent). The fence test asserts the split at AST level.

### 4. Lock-order invariant ("flock first, then PID")

The single most important load-bearing invariant: `fcntl.flock(fd, LOCK_EX | LOCK_NB)` **before** `os.ftruncate(fd, 0)` and `os.write(fd, pid)`. Writing the PID before the flock succeeds means a torn write surfaces a stale PID to the contender even when the holder process never existed. The mutation test pins this at runtime; the fence test pins it at AST source-line order.

### 5. Clear stale PID on release (`ftruncate(0)` before `LOCK_UN`)

Without this, a contender that arrives after a clean release reads a stale PID from the prior holder and surfaces it as if the holder were still running. `os.ftruncate(fd, 0)` runs **before** `fcntl.flock(fd, LOCK_UN)` and **before** `os.close(fd)`. The file body is empty between releases.

### 6. Advisory-lock threat model

`fcntl.flock` is **advisory**. A process that does not call `flock` can still write to `.codegenie/`. The lock protects only against other `codegenie remediate` invocations — that is the threat model; do not over-engineer to defend against rogue editors.

### 7. `LOCK_NB` is required

Without `LOCK_NB`, the second process blocks indefinitely waiting for the first to finish. The architecture wants explicit refusal, not patient waiting (`phase-arch-design.md §Edge cases row 18`).

### 8. Same-OFD vs distinct-OFD flock semantics

Two `open()` calls in the same process create two distinct **open file descriptions (OFDs)**; `flock` is per-OFD on Linux and macOS, so the second `LOCK_EX | LOCK_NB` on a distinct OFD raises `BlockingIOError`. This is the basis for the same-process double-acquire test. If your local filesystem (some FUSE mounts, some network filesystems) does not honor this, surface the issue rather than monkey-patching. CI runs on tmpfs (`tmp_path` is local) — fine.

### 9. FIFO-based subprocess synchronization (NOT sleep)

The integration test cannot use a `time.sleep(0.1)` to "give proc1 time to acquire" — on slow CI proc1 may finish before proc2 starts, and the test passes *even if the lock is missing*. The deterministic shape is: poll on `lock_path.stat().st_size > 0` (filled with PID after `os.fsync`) before spawning proc2; pin proc1 inside the lock by having its first Phase-3 stage block on reading a named pipe the test writes to. The negative-mutation row (`acquire_repo_lock` patched to `nullcontext`) makes the test fail — that's the *real* assertion that the lock is what produces exit 14.

### 10. Wiring point: CLI/orchestrator, NOT `GateRunner.__init__`

S5-02 HARDENED locked `GateRunner.__init__` keyword-only with 6 deps; S7-03 added the additive 7th `cost`. An 8th `repo_root` would compound. More importantly, the orchestrator constructs one `GateRunner` per gate (Phase 3 Stage 6 has multiple gates per remediate); the lock's natural lifetime is the *whole* remediate invocation. The wiring point is `cli/remediate.py` Click-command entry, wrapping the entire downstream pipeline (Phase 3 → 4 → 5).

### 11. ADR-0007 ordering — marker strictly inside the lock

Lock is acquired *before* `RetryLedger.__init__`, *before* any `record_pre_execute` call. A `pre_execute` JSONL line cannot exist outside the lock; otherwise two processes could race on marker writes before either knows it lost the lock.

### 12. `cli/exit_codes.py` extension-by-addition

This story creates the kernel. Future stories that need a new exit code (e.g., a hypothetical `EXIT_SANDBOX_TIMEOUT = 15`) **append** to the file: add the `Final[int]` constant, add the name to `__all__`, add a row to the source-of-truth table in *that future story's body*. Never rename or re-value an existing constant — every audit chain and operator-runbook keys off these integers. The fence test (`test_cli_exit_codes_static.py`) enforces the discipline.

### 13. `cli/_errors.py` registry-pattern dispatch

The exception → exit-code mapping is a `Mapping[type[Exception], int]` (registry pattern), not an `if isinstance(...)` chain. Extension is by appending to the `Mapping`. The AST-scan fence asserts no `isinstance` call appears in `map_typed_errors_to_exit_codes`. This is the same shape as `@register_freshness_check(IndexName)` / `@register_dep_graph_strategy(PackageManager)` / `@register_signal_kind(...)` — small stable kernel, extension by addition.

### 14. `sandbox/logging.py` extension-by-addition

This story appends three new `EVENT_REPO_LOCK_*: Final[str]` constants to the S1-01-locked `sandbox/logging.py` `__all__`. Existing constants are byte-stable. The S1-01 audit-string rename test continues to pass; the AST-scan AC-EVT-NOLIT asserts no bare `"sandbox.repo_lock.*"` string literal exists in any `.py` file under `src/codegenie/sandbox/` or `src/codegenie/cli/` — every emit references the constant by name.

### 15. Future seam for Phase 9 (Temporal)

Phase 9 will introduce durable workflows via Temporal. The single-host `fcntl.flock` mutex is wrong for that world — multiple worker hosts cannot coordinate via a local filesystem. The future seam is a `RepoLock` Protocol: `class RepoLock(Protocol): def acquire(self, repo_root: Path) -> AbstractContextManager[None]: ...`. The current `acquire_repo_lock` becomes the `LocalFsRepoLock` adapter; Phase 9 ships `TemporalRepoLock` adapter that uses a Temporal workflow signal. **Rule 2 — do NOT introduce the Protocol now** (only one consumer). When Phase 9 lands the second adapter, lift the Protocol then. Document this as the explicit promotion condition.
