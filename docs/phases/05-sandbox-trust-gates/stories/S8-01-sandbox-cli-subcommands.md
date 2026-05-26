# Story S8-01 — `codegenie sandbox {health,inspect,gc,prepare}` Click subcommands

**Step:** Step 8 — Operator CLI surface + end-to-end smoke
**Status:** Ready (HARDENED 2026-05-26)
**Effort:** M
**Depends on:** S1-02 (`SandboxClient` Protocol member set frozen), S1-05 (`sandbox.registry.get_backend` / `auto_detect`), S2-01 (`RetryLedger.attempts/head`), S2-02 (`RetryLedger.entries` + `PreExecuteMarker`), S3-06 (`SandboxHealthProbe`), S6-03 (firecracker rootfs `bake`), S6-04 (`auto_detect` platform branch), S7-04 (`cli/exit_codes.py` kernel)
**ADRs honored:** ADR-0004, ADR-0005, ADR-0007, ADR-0013

## Validation notes (2026-05-26)

`phase-story-validator` HARDENED this story against eight HARDENED sibling stories (S1-02, S1-05, S2-01, S2-02, S3-06, S6-04, S7-03, S7-04). Eleven block-tier and twenty-three harden-tier findings folded in; full audit log at [`_validation/S8-01-sandbox-cli-subcommands.md`](_validation/S8-01-sandbox-cli-subcommands.md). Headline corrections:

1. **`inspect` switches from `attempts()` + secondary parse → `entries()`** (S2-02's `LedgerEntry: PreExecuteMarker | Attempt` discriminated reader). Per `payload["type"]` (not `"kind"` — the on-disk discriminator is `"type"`, frozen by S2-01 AC-T-1). Eliminates the double-read smell and gives chain-verification across mixed rows for free.
2. **`gate_isolation_class` is NOT on `SandboxClient` and NOT on `SandboxHealth`** — per S1-02 HARDENED AC-2a the Protocol member set is exactly `{execute, health}`, and the `SandboxHealth` Pydantic model is frozen without that field. Source it via a module-level `_BACKEND_TO_ISOLATION: Final[Mapping[str, Literal["shared_kernel", "microvm"]]]` exported from `sandbox/contract.py` (single source of truth; mirrors the `SandboxRun` `@model_validator` whitelist in S1-02 AC-7b). Phase 7's chainguard backend extends the mapping by one entry — zero CLI edits.
3. **Exit code 13 reserved by S7-04 HARDENED for chain corruption** (S7-04 took `14` for `RepoAlreadyInProgress` and explicitly noted "13 is intentionally unused (reserved)"). This story is the kernel-extender — adds `EXIT_CHAIN_CORRUPTED: Final[int] = 13` to `cli/exit_codes.py` (the new kernel S7-04 created) by *appending* under `__all__`; never edits existing entries.
4. **`prepare` rooted in the registry, not direct imports.** Per S6-04 + Open/Closed CLAUDE.md commitment, `cli/sandbox.py` has **zero** imports from `codegenie.sandbox.did` or `codegenie.sandbox.firecracker` (AST scan AC); `prepare`'s backend-specific call goes through a new `BackendPreparer` Protocol surfaced by `sandbox/registry.py` (additive). DinD's `prepare()` is a no-op returning `already-prepared: true` (not an error). Phase 7 distroless lands by registering its preparer — zero CLI edits.
5. **`prepare`'s "already-prepared" fast path is file-existence, not BLAKE3 rehash.** Re-hashing a multi-GB rootfs on every operator invocation is unacceptable; per the content-addressed dir convention (`tools/firecracker/<rootfs_digest>/rootfs.ext4`), existence is the integrity claim. A `--verify` opt-in performs the BLAKE3 check; a digest mismatch under `--verify` raises `RootfsDigestMismatch` (new error, additive).
6. **All four event names are `Final[str]` constants in `sandbox/logging.py`** under `__all__` (extension-by-addition contract from S1-01 HARDENED; mirrors the four `EVENT_SANDBOX_AUTO_DETECT_FALLBACK`-style entries S1-05 added). AC-EVT-1 + AST scan asserts no bare `"cli.sandbox.*"` literals in `src/codegenie/cli/`.
7. **The two `...` stubs in the TDD plan are filled in** with the chain-tamper subprocess witness and the digest-skip negative-mutation witness (assert `bake` is never called when the fast path triggers).
8. **`gc` window-parser is a pure module-level helper** (`_parse_age_window(s) -> timedelta` raises `click.BadParameter`); a parametrized table rejects `7days`, `7D`, `-7d`, `0d`, `""`, `7`, `7dx`. Hypothesis property test asserts the function never returns a non-positive `timedelta`.
9. **`gc` survival set widened.** Beyond `attempts.jsonl`: `manifest.yaml`, `chain_head.bin`, `cost.jsonl` (S7-03) — every file inside `.codegenie/remediation/<run-id>/gates/<gate_id>/` *outside* the `sandbox/` subdir must survive. Pinned via a survival-set fixture that pre-populates each.
10. **`GC_ROOTS: Final[tuple[str, ...]]`** module constant in `cli/sandbox/_gc.py` enumerates the two glob roots today; new roots (Phase 9 Temporal worker dirs, Phase 7 chainguard cache) extend the tuple by one entry — never branch on root pattern.
11. **KeyboardInterrupt / SystemExit lifecycle.** All four subcommands wrap their bodies in `contextlib.ExitStack` so cleanup is exception-safe; `gc` half-deletion mid-Ctrl+C exits ≠ 0 with a `partial: true` JSON field rather than silently truncating. Mirrors the S7-04 lifecycle discipline.

No `RESCUE` findings. No Stage-3 research needed — every gap was answerable from in-repo HARDENED sources + the ADR-0007 / ADR-0013 text.

## Context

Phase 5's runtime primitives (`SandboxClient`, `RetryLedger`, `SandboxHealthProbe`, `auto_detect`, `sandbox prepare`) are now all in place but operators have no way to inspect or maintain them. This story lands the four operator-facing Click subcommands under `codegenie sandbox` that close roadmap §Goal 15 and make `attempts.jsonl` + sandbox run dirs debuggable without writing custom Python.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — CLI surface (codegenie sandbox)` — exact subcommand surface, performance envelope, failure behavior.
  - `../phase-arch-design.md §Cross-cutting concerns §Replay / debugability` — `inspect` semantics; BLAKE3 chain re-verified every call.
  - `../phase-arch-design.md §Cross-cutting concerns §Idempotence` — `gc` idempotent on same `--older-than`; `prepare` idempotent on identical digests.
- **Phase ADRs:**
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — `health` must surface `gate_isolation_class` per backend.
  - `../ADRs/0005-phase4-chain-head-compatibility.md` — `inspect` reads the Phase 4 chain-head from `.codegenie/remediation/<run-id>/chain_head.bin` and warns on mismatch (does not abort — `inspect` is read-only).
  - `../ADRs/0007-pre-execute-marker-for-resume-safety.md` — `inspect` must render `pre_execute` markers distinctly from `attempt` rows.
  - `../ADRs/0013-digest-pinned-policy-yaml-codegenie-owned.md` — `prepare` validates `tools/digests.yaml#sandbox.policy_yaml` before rebake.
- **Production ADRs:**
  - `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — `health` is a probe surface; output schema is contract-stable.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Operator CLI"`.
- **Existing code:**
  - `src/codegenie/cli/__init__.py` — top-level Click group; add `sandbox` sub-group here.
  - `src/codegenie/sandbox/health/probe.py` (S3-06) — `SandboxHealthProbe.run()` returns `SandboxHealth`.
  - `src/codegenie/sandbox/registry.py` (S6-04) — `auto_detect()` and `get_backend(name)`.
  - `src/codegenie/gates/retry_ledger.py` (S2-01..S2-03) — `attempts()` + chain verification.
  - `src/codegenie/sandbox/firecracker/rootfs.py` (S6-03) — rootfs bake entry point reused by `prepare`.

## Goal

Ship the four Click subcommands `codegenie sandbox {health, inspect <gate-run-id>, gc [--older-than 7d], prepare [--backend firecracker]}` with chain verification on `inspect`, idempotent housekeeping for `gc` and `prepare`, and structured exit codes.

## Acceptance criteria

### A. `health` subcommand

- [ ] **AC-H-1 — Click choice pinned.** `--backend` accepts exactly `{"did", "firecracker", "auto"}` via `click.Choice(["did", "firecracker", "auto"])`; default `"auto"`. Out-of-set values fail with Click `UsageError` exit 2. Tested with parametrized `[("dind", 2), ("docker", 2), ("kvm", 2), ("", 2)]`.
- [ ] **AC-H-2 — Backend resolution goes through the registry kernel.** `--backend auto` calls `codegenie.sandbox.registry.auto_detect()` (zero-arg, returns `SandboxClient`, per S1-05 AC-AD-1); `--backend did` / `--backend firecracker` map to `get_backend("docker_in_docker")` / `get_backend("firecracker")`. The map from CLI name to registry name is a module-level `Final[Mapping[str, str]]` constant (`_CLI_BACKEND_NAMES`), not branched-on inline.
- [ ] **AC-H-3 — Calls `client.health()` (the `SandboxClient` Protocol method, S1-02 AC-2a)**, returning `SandboxHealth`. Does NOT instantiate `SandboxHealthProbe` (probe machinery needs a `RepoSnapshot`/`ProbeContext` the CLI cannot synthesize). Documented in Notes — the arch's "calls `SandboxHealthProbe.run()`" phrasing refers to the same data, not the same callable.
- [ ] **AC-H-4 — `gate_isolation_class` sourced from `sandbox/contract.py::_BACKEND_TO_ISOLATION`** — a new `Final[Mapping[Literal["docker_in_docker", "firecracker"], Literal["shared_kernel", "microvm"]]]` constant (single source of truth shared with `SandboxRun`'s `@model_validator` from S1-02 AC-7b). The CLI computes `isolation = _BACKEND_TO_ISOLATION[health.backend]`. A unit test asserts `set(_BACKEND_TO_ISOLATION.keys()) == {"docker_in_docker", "firecracker"}` and matches the `SandboxRun.backend` Literal arg set byte-for-byte.
- [ ] **AC-H-5 — Pretty-print fields and order are pinned.** Output lines are exactly `backend: ...`, `reachable: ...`, `confidence: ...`, `gate_isolation_class: ...`, then `reasons:` block (one `- {reason}` per line; `(none)` if empty), then `warnings:` block (same shape). Golden-file test on the output bytes for a canonical fixture.
- [ ] **AC-H-6 — Exit code mapping.** `health.reachable is True` → exit 0; `False` → exit 1. Tested with both branches.
- [ ] **AC-H-7 — structlog event field set pinned.** `EVENT_CLI_SANDBOX_HEALTH` carries exactly `{"backend": str, "reachable": bool, "confidence": Literal["high","medium","low"], "exit_code": int}`. Asserted via `structlog.testing.capture_logs()` sorted-keys equality (S5-02 HARDENED AC-OBS-1 precedent).

### B. `inspect <gate-run-id>` subcommand

- [ ] **AC-I-1 — `<gate-run-id>` parser is a pure module-level helper in `cli/sandbox/_resolve.py`.** Signature: `def resolve_gate_run(repo_root: Path, raw: str) -> tuple[Path, str]` returning `(run_dir, gate_id)`. Accepts `<run-id>:<gate_id>` (colon-separated, canonical). Falls back to `glob(".codegenie/remediation/*/gates/<raw>/")` — exactly one match required.
- [ ] **AC-I-2 — Ambiguous and unknown gate-run-ids exit 2 with `click.UsageError`.** Zero matches → `UsageError("unknown gate-run-id: <raw>")`; ≥ 2 matches → `UsageError("ambiguous gate-run-id: <raw> matched {n} runs; use <run-id>:<gate_id> form")`. Both branches tested.
- [ ] **AC-I-3 — Uses `RetryLedger.entries()` (S2-02 AC-DR-1), NOT `attempts()` + secondary parse.** `entries()` returns `list[LedgerEntry]` where `LedgerEntry: TypeAlias = PreExecuteMarker | Attempt` and the BLAKE3 chain is re-verified across mixed rows in one pass. The renderer dispatches on `isinstance(e, PreExecuteMarker)` vs `isinstance(e, Attempt)`. AST scan on `cli/sandbox.py` asserts `attempts.jsonl` is opened by the CLI **zero** times outside `RetryLedger` (no secondary read).
- [ ] **AC-I-4 — `Attempt` rows render with columns** `attempt_id`, `started_at`, `duration_ms` (computed as `ended_at − started_at` in milliseconds, integer), `state` (`outcome.kind` per S1-03), `failing_signals` (sorted list of `signal.kind` where `signal.passed is False`), `sandbox_run_id` (first 8 chars), `chain_hash[:8]`. Tab-aligned via `click.echo` only (no tabulate/rich).
- [ ] **AC-I-5 — `PreExecuteMarker` rows render with a `►` Unicode prefix** and the columns `►`, `attempt_id`, `started_at`, `sandbox_spec_hash[:8]`, `chain_hash[:8]` (`state`, `duration_ms`, `failing_signals`, `sandbox_run_id` are blank for markers). The `►` is U+25BA exactly; asserted via `assert "►" in result.output` AND `assert "►" in result.output`.
- [ ] **AC-I-6 — Exit code on chain corruption uses the kernel constant.** `EXIT_CHAIN_CORRUPTED: Final[int] = 13` is added to `src/codegenie/cli/exit_codes.py` (the S7-04 kernel) appended under `__all__`; nothing existing is edited. `inspect` catches `AuditChainCorrupted` and `LedgerAttemptOutOfOrder`, prints a single-line structured error to stderr (`json.dumps({"error": "audit_chain_corrupted", "kind": exc.kind, "row_index": exc.row_index, "attempt_id": exc.attempt_id}, sort_keys=True)`), and exits `EXIT_CHAIN_CORRUPTED`. Tested via byte-tamper subprocess witness (see TDD plan).
- [ ] **AC-I-7 — `inspect` is constructor-safe against ADR-0005.** `RetryLedger(run_dir, gate_id, prev_chain_head=None)` is constructed with `prev_chain_head=None` deliberately; `chain_head.bin` is read separately as a *display* check (`chain-head-match: yes|no`), never passed into the constructor. An AST/source assertion: the substring `prev_chain_head=` appears at most once in `cli/sandbox.py` and the literal argument is `None`.
- [ ] **AC-I-8 — `chain-head-match` line shape pinned.** When `chain_head.bin` exists: print `chain-head-match: yes` (stdout, exit code unchanged) or `chain-head-match: no` + a stderr warning of shape `chain-head mismatch: file=<hex8>, ledger=<hex8>`. When `chain_head.bin` is absent: print `chain-head-match: absent` (NOT `no` — distinct from mismatch). All three branches tested.

### C. `gc [--older-than 7d]` subcommand

- [ ] **AC-G-1 — Window parser is a pure module-level helper `_parse_age_window(s: str) -> timedelta`** in `cli/sandbox/_gc.py`. Regex `^(?P<n>\d+)(?P<unit>d|h|m)$`; `n > 0` required. Rejects: `7days`, `7D`, `-7d`, `0d`, `""`, `7`, `7dx`, `7s`, ` 7d`, `7d ` (parametrized table of all 10 rejections; each raises `click.BadParameter`). Hypothesis property test: for `n ∈ st.integers(min_value=1, max_value=10_000)` and `unit ∈ st.sampled_from("dhm")`, `_parse_age_window(f"{n}{unit}") > timedelta(0)`.
- [ ] **AC-G-2 — `GC_ROOTS: Final[tuple[str, ...]]` module constant** in `cli/sandbox/_gc.py` enumerates the relative-glob roots: `(".codegenie/sandbox/runs/*", ".codegenie/remediation/*/gates/*/sandbox/*")`. `gc` iterates over `GC_ROOTS`, never branches on root kind. Adding a Phase-9 Temporal root is one tuple-entry edit (the Open/Closed seam); a unit test asserts `len(GC_ROOTS) == 2` (mutation backstop — a future contributor adding a third root must update both the tuple and this AC, and the executor's validator catches it).
- [ ] **AC-G-3 — Idempotence pinned without wall-clock racing.** Test runs `gc --older-than 7d` twice in succession (no sleep, no wall-clock dependency). First run reports `removed >= 1` after pre-populating a `mtime`-aged dir; second run reports `removed == 0`. The first run's removed set is structurally captured (via the test fixture's pre-populated paths), and the assertion is `payload2["removed"] == 0` plus *every survival-set path still exists*.
- [ ] **AC-G-4 — Survival set widened.** Inside any `.codegenie/remediation/<run-id>/gates/<gate_id>/`, the survival assertion enumerates *every* file outside `sandbox/`: `attempts.jsonl`, `manifest.yaml`, `chain_head.bin` (if present), `cost.jsonl` (S7-03; if present), `.lock` (S7-04 repo lock). The test pre-populates one of each (per-file fixture); after `gc`, all five paths must exist with byte-identical contents (`Path.read_bytes()` equality).
- [ ] **AC-G-5 — Output is a single canonical JSON line.** `{"older_than": "<window>", "removed": <int>, "kept": <int>, "partial": false}`, sorted keys, on stdout. `kept` counts dirs that matched a root but were inside the window. `partial: true` only on Ctrl+C / SystemExit during the walk (see AC-G-7).
- [ ] **AC-G-6 — `gc` never recurses into `attempts.jsonl`-bearing directories.** AST/grep assertion on `cli/sandbox/_gc.py`: the only filesystem mutation calls are `shutil.rmtree` over paths matched by `Path.glob(root)` where `root in GC_ROOTS`; no `Path.rglob`, no `os.walk`. Mutation: a future contributor adding `Path.rglob("*sandbox*")` fails the AST scan.
- [ ] **AC-G-7 — Lifecycle safety.** `gc` runs inside a `contextlib.ExitStack`; an injected `KeyboardInterrupt` mid-walk (test patches `shutil.rmtree` to raise on the 2nd call) leaves the already-deleted dirs deleted (no rollback expected — operator intent) but prints the canonical JSON line with `partial: true` and exits 130. Verifies no half-truncated `attempts.jsonl` from a half-completed walk.

### D. `prepare [--backend firecracker]` subcommand

- [ ] **AC-P-1 — `prepare` is registry-dispatched.** A new `BackendPreparer` Protocol (`@runtime_checkable`, single method `prepare(self, *, verify: bool) -> PrepareOutcome`) lives in `sandbox/registry.py`. `cli/sandbox.py`'s `prepare` body is exactly: `preparer = registry.get_preparer(backend_name); outcome = preparer.prepare(verify=verify); click.echo(outcome.as_json())`. AST scan: `cli/sandbox.py` has **zero** import statements matching `from codegenie.sandbox.(did|firecracker)`.
- [ ] **AC-P-2 — DinD's preparer is a no-op.** `get_preparer("docker_in_docker").prepare(verify=False)` returns `PrepareOutcome(already_prepared=True, verified=False, backend="docker_in_docker", bake_invoked=False)` without raising. Tested with a `--backend did` parametrized case.
- [ ] **AC-P-3 — Firecracker fast path: file existence, NOT BLAKE3 rehash.** With `verify=False` (the default), the preparer reads `tools/digests.yaml#sandbox.rootfs` → checks `tools/firecracker/<rootfs_digest>/rootfs.ext4` exists → returns `PrepareOutcome(already_prepared=True, ...)` without invoking `bake`. AC asserted via `monkeypatch.setattr("codegenie.sandbox.firecracker.rootfs.bake", lambda **kw: pytest.fail("bake must not run on fast path"))`; test passes when `prepare` runs to completion without triggering the fail.
- [ ] **AC-P-4 — Firecracker rebake path.** When the digest-named rootfs file is absent, `prepare` calls `codegenie.sandbox.firecracker.rootfs.bake(...)` (S6-03 surface), then re-asserts the file exists, then returns `PrepareOutcome(already_prepared=False, bake_invoked=True, ...)`. Tested with a temp `tools/` tree where the rootfs file is missing initially and present after.
- [ ] **AC-P-5 — `--verify` opt-in performs BLAKE3 rehash.** With `verify=True`, the preparer computes the on-disk BLAKE3-256 of `rootfs.ext4` and compares to `<rootfs_digest>` (the dir name encodes the expected digest). On match: `PrepareOutcome(already_prepared=True, verified=True, ...)`. On mismatch: raises new `RootfsDigestMismatch(SandboxError)` with structured attributes `.expected: str`, `.actual: str`, `.path: Path`. CLI catches it, prints the structured error, exits 1.
- [ ] **AC-P-6 — `FirecrackerKvmMissing` propagates from the preparer.** On macOS without `/dev/kvm`, the firecracker preparer raises `FirecrackerKvmMissing` (existing S6-04 error). The CLI catches it at the `prepare` site, prints a single-line structured stderr (`{"error": "firecracker_kvm_missing", "hint": "DinD is the supported macOS backend; use --backend did or omit"}`), exits 1.
- [ ] **AC-P-7 — `PrepareOutcome` is a frozen Pydantic model** (`extra="forbid"`, `frozen=True`) with field set `{already_prepared: bool, verified: bool, bake_invoked: bool, backend: Literal["docker_in_docker", "firecracker"], rootfs_path: Path | None}`. `.as_json()` returns canonical JSON (sorted keys, no whitespace).

### E. Cross-cutting + Open/Closed extension contract

- [ ] **AC-X-1 — Event-name kernel discipline.** `sandbox/logging.py` gains four `Final[str]` constants appended to `__all__` (alphabetized): `EVENT_CLI_SANDBOX_GC = "cli.sandbox.gc"`, `EVENT_CLI_SANDBOX_HEALTH = "cli.sandbox.health"`, `EVENT_CLI_SANDBOX_INSPECT = "cli.sandbox.inspect"`, `EVENT_CLI_SANDBOX_PREPARE = "cli.sandbox.prepare"`. Each value matches `^cli\.sandbox\.[a-z][a-z0-9_]*$`. AST scan asserts no bare literal `"cli.sandbox.*"` strings appear anywhere under `src/codegenie/cli/`.
- [ ] **AC-X-2 — Per-event field set pinned.** Each event's field set is asserted via `structlog.testing.capture_logs()` sorted-keys equality (S5-02 AC-OBS-1 precedent). `EVENT_CLI_SANDBOX_HEALTH`: `{backend, reachable, confidence, exit_code}`. `EVENT_CLI_SANDBOX_INSPECT`: `{run_id, gate_id, attempt_count, marker_count, chain_head_match, exit_code}`. `EVENT_CLI_SANDBOX_GC`: `{older_than, removed, kept, partial, exit_code}`. `EVENT_CLI_SANDBOX_PREPARE`: `{backend, already_prepared, verified, bake_invoked, exit_code}`. No event includes raw env, absolute paths outside `repo_root`, or chain hashes (prefix-only).
- [ ] **AC-X-3 — Open/Closed for backends.** A new test under `tests/fence/test_cli_sandbox_backend_addition.py` runs an AST walk on `cli/sandbox.py` asserting (a) zero imports matching `from codegenie.sandbox.(did|firecracker|chainguard|gvisor)`; (b) zero string literals matching `"docker_in_docker"` or `"firecracker"` outside `_CLI_BACKEND_NAMES`. A Phase-7 chainguard backend lands as a new entry in `_CLI_BACKEND_NAMES` plus `_BACKEND_TO_ISOLATION` plus a registry registration — zero edits to `cli/sandbox.py`'s subcommand bodies.
- [ ] **AC-X-4 — Exit-code kernel extension.** `cli/exit_codes.py` is **extended additively**: this story appends `EXIT_CHAIN_CORRUPTED: Final[int] = 13` to `__all__`; existing constants (S7-04's `EXIT_REPO_ALREADY_IN_PROGRESS = 14`, the standard `EXIT_OK = 0` / `EXIT_GENERAL = 1` / `EXIT_USAGE = 2` / `EXIT_ESCALATE = 11` / `EXIT_FAILED_UNRECOVERABLE = 12`) are byte-stable. A unit test asserts `set(exit_codes.__all__).issuperset({"EXIT_CHAIN_CORRUPTED", "EXIT_REPO_ALREADY_IN_PROGRESS"})` and each value is unique.
- [ ] **AC-X-5 — `cli.py` → `cli/` package migration is in-scope only if needed.** If `src/codegenie/cli.py` is still a flat file, this story converts it to `src/codegenie/cli/__init__.py` *additively* (re-exporting every existing public symbol from the old file via `__all__`), then adds the `sandbox` sub-group. A grep asserts no existing import path breaks. The migration test: `from codegenie.cli import cli` still works; `from codegenie.cli import sandbox` works too.

### F. Test hygiene + harness

- [ ] **AC-T-1 — `tests/cli/test_sandbox_cli.py` ≥ 90% line + 80% branch coverage on `src/codegenie/cli/sandbox.py` and `src/codegenie/cli/sandbox/_*.py`.** Asserted in CI via `pytest --cov=codegenie.cli.sandbox --cov-fail-under=90`.
- [ ] **AC-T-2 — Every red test exists, is committed at the TDD's RED step, and is the only thing that turns the suite green when its corresponding production code lands.** Witnessed by per-AC mapping in the TDD plan (`# AC-H-1` / `# AC-I-3` comments above each test function).
- [ ] **AC-T-3 — `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/cli`, `pytest tests/cli/test_sandbox_cli.py` and `pytest tests/fence/test_cli_sandbox_backend_addition.py` all pass.**
- [ ] **AC-T-4 — Negative mutation witnesses pinned.** Three load-bearing mutations are explicitly tested:
  - **M-1 (fast-path skip):** delete `prepare`'s fast-path digest check → `bake` is invoked → test fails (the `pytest.fail` sentinel in the `monkeypatch.setattr` trips).
  - **M-2 (chain re-verify skip):** swap `entries()` for a no-verify reader → tamper test exits 0 instead of 13 → test fails.
  - **M-3 (event-constant bare-literal regression):** replace `EVENT_CLI_SANDBOX_HEALTH` with the bare string `"cli.sandbox.health"` at the emit site → AST scan AC-X-1 fails.

## Implementation outline

1. **Promote `src/codegenie/cli.py` → `src/codegenie/cli/__init__.py` (if still a flat file).** Re-export every existing public symbol; no caller-side import path changes. Add `src/codegenie/cli/sandbox/` sub-package directory.
2. **Extend `src/codegenie/cli/exit_codes.py`** (the S7-04 kernel) by appending `EXIT_CHAIN_CORRUPTED: Final[int] = 13` under `__all__` — no edits to existing constants.
3. **Extend `src/codegenie/sandbox/logging.py`** with the four `EVENT_CLI_SANDBOX_*: Final[str]` constants, appended under `__all__` alphabetically; values match `^cli\.sandbox\.[a-z][a-z0-9_]*$`.
4. **Extend `src/codegenie/sandbox/contract.py`** with `_BACKEND_TO_ISOLATION: Final[Mapping[Literal["docker_in_docker", "firecracker"], Literal["shared_kernel", "microvm"]]]`; export via `__all__`. The same mapping is referenced by `SandboxRun`'s `@model_validator` (S1-02 AC-7b) — replace any inline whitelist there with this constant (additive — one source of truth).
5. **Extend `src/codegenie/sandbox/registry.py`** additively:
   - `class BackendPreparer(Protocol)`: `@runtime_checkable`; single method `def prepare(self, *, verify: bool) -> PrepareOutcome: ...`.
   - `class PrepareOutcome(BaseModel)`: `extra="forbid"`, `frozen=True`, fields per AC-P-7.
   - `register_preparer(backend_name)` decorator + `get_preparer(backend_name) -> BackendPreparer`.
   - Land two concrete preparers in their respective packages (NOT in `cli/sandbox.py`):
     - `sandbox/did/preparer.py`: returns `PrepareOutcome(already_prepared=True, bake_invoked=False, ...)`.
     - `sandbox/firecracker/preparer.py`: reads `tools/digests.yaml`, fast-path file-existence check, calls `bake(...)` on miss, supports `verify=True` for BLAKE3 rehash.
6. **Add new errors (additive) in `src/codegenie/sandbox/errors.py`** (or wherever sandbox errors live): `class RootfsDigestMismatch(SandboxError)` with `.expected`, `.actual`, `.path` attributes.
7. **Create `src/codegenie/cli/sandbox/__init__.py`** exposing `@click.group("sandbox")` registered on the top-level `codegenie` group. Internal layout:
   - `cli/sandbox/_render.py` — pretty-printers for `SandboxHealth`, `Attempt`-row, `PreExecuteMarker`-row.
   - `cli/sandbox/_resolve.py` — `resolve_gate_run(repo_root, raw) -> (run_dir, gate_id)` plus `_CLI_BACKEND_NAMES: Final[Mapping[str, str]]`.
   - `cli/sandbox/_gc.py` — `_parse_age_window`, `GC_ROOTS`, the gc walker.
8. **Implement `health`:** resolve backend via `_CLI_BACKEND_NAMES`; call `client.health()`; print `_render_health(h, isolation=_BACKEND_TO_ISOLATION[h.backend])`; emit `EVENT_CLI_SANDBOX_HEALTH` with the AC-X-2 field set; exit per AC-H-6.
9. **Implement `inspect`:** call `resolve_gate_run(repo_root, raw)` (UsageError on unknown/ambiguous → exit 2); construct `RetryLedger(run_dir, gate_id, prev_chain_head=None)`; call `.entries()` (S2-02 AC-DR-1); dispatch on `isinstance` for rendering; read `chain_head.bin` and print `chain-head-match: yes|no|absent`; catch `AuditChainCorrupted` / `LedgerAttemptOutOfOrder` → exit `EXIT_CHAIN_CORRUPTED`.
10. **Implement `gc`:** wrap body in `contextlib.ExitStack`; iterate `GC_ROOTS` × `Path(repo_root).glob(root)`; `shutil.rmtree` each dir whose `stat().st_mtime < (now - window).timestamp()`; tally `removed` / `kept` / `partial`; emit canonical JSON line; emit `EVENT_CLI_SANDBOX_GC` with field set per AC-X-2.
11. **Implement `prepare`:** call `registry.get_preparer(backend_name).prepare(verify=verify_flag)`; print `outcome.as_json()`; catch `FirecrackerKvmMissing` and `RootfsDigestMismatch` per AC-P-5 / AC-P-6; emit `EVENT_CLI_SANDBOX_PREPARE`.
12. **Add `tests/fence/test_cli_sandbox_backend_addition.py`** — the Open/Closed AST scan (AC-X-3).

The four subcommand bodies are each ≤ 20 LOC because the registry/preparer/event-constant kernels carry the variant data. The "kernel + registry of capabilities" Open/Closed shape this story lands is the same pattern Phase 0's `@register_probe`, Phase 5 S1-05's `@register_sandbox_backend`, and Phase 3's `@register_dep_graph_strategy` use.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/cli/test_sandbox_cli.py`. Each test is prefixed with the AC it covers as an in-file comment; the executor's Validator pass uses these comments as the AC→test map.

```python
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner
from hypothesis import given, strategies as st

from codegenie.cli import cli  # top-level group
from codegenie.cli.exit_codes import EXIT_CHAIN_CORRUPTED  # =13 (added by this story)
from codegenie.cli.sandbox._gc import GC_ROOTS, _parse_age_window
from codegenie.cli.sandbox._resolve import resolve_gate_run, _CLI_BACKEND_NAMES
from codegenie.gates.retry_ledger import RetryLedger
from codegenie.sandbox.contract import SandboxHealth, _BACKEND_TO_ISOLATION
from codegenie.sandbox.registry import get_preparer
from codegenie.sandbox.errors import FirecrackerKvmMissing, RootfsDigestMismatch


# ---------- A. health ----------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# AC-H-1
@pytest.mark.parametrize("bad", ["dind", "docker", "kvm", ""])
def test_health_rejects_bad_backend_choice(bad: str) -> None:
    result = CliRunner().invoke(cli, ["sandbox", "health", "--backend", bad])
    assert result.exit_code == 2, result.output


# AC-H-2, AC-H-3, AC-H-4, AC-H-5, AC-H-6, AC-H-7
def test_health_prints_pinned_fields_and_isolation_from_mapping(monkeypatch) -> None:
    fake = SandboxHealth(
        backend="docker_in_docker",
        reachable=True,
        confidence="high",
        reasons=[],
        warnings=["strace_sys_ptrace_missing"],
        detected_at=_utc_now(),
    )

    class _FakeClient:
        def health(self) -> SandboxHealth:
            return fake
        def execute(self, spec):  # protocol satisfaction
            raise NotImplementedError

    monkeypatch.setattr("codegenie.sandbox.registry.auto_detect", lambda: _FakeClient())

    result = CliRunner().invoke(cli, ["sandbox", "health"])
    assert result.exit_code == 0, result.output
    # Isolation sourced from the contract mapping, NOT a client attribute.
    assert _BACKEND_TO_ISOLATION["docker_in_docker"] == "shared_kernel"
    assert "backend: docker_in_docker" in result.output
    assert "reachable: True" in result.output
    assert "confidence: high" in result.output
    assert "gate_isolation_class: shared_kernel" in result.output
    assert "- strace_sys_ptrace_missing" in result.output


# AC-H-6 (negative branch)
def test_health_exits_1_when_unreachable(monkeypatch) -> None:
    fake = SandboxHealth(
        backend="docker_in_docker",
        reachable=False,
        confidence="low",
        reasons=["daemon_unreachable"],
        warnings=[],
        detected_at=_utc_now(),
    )

    class _FakeClient:
        def health(self) -> SandboxHealth:
            return fake
        def execute(self, spec):
            raise NotImplementedError

    monkeypatch.setattr("codegenie.sandbox.registry.auto_detect", lambda: _FakeClient())
    result = CliRunner().invoke(cli, ["sandbox", "health"])
    assert result.exit_code == 1


# AC-H-4 (the mapping is the single source of truth)
def test_backend_to_isolation_keys_match_sandboxrun_backend_literal() -> None:
    from codegenie.sandbox.contract import SandboxRun
    from typing import get_args, get_type_hints
    hints = get_type_hints(SandboxRun)
    assert set(_BACKEND_TO_ISOLATION.keys()) == set(get_args(hints["backend"]))


# ---------- B. inspect ----------

# AC-I-1, AC-I-2 (unknown)
def test_inspect_exits_2_on_unknown_gate_run_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".codegenie/remediation").mkdir(parents=True)
    result = CliRunner().invoke(cli, ["sandbox", "inspect", "nope:stage6_validate"])
    assert result.exit_code == 2
    assert "unknown gate-run-id" in result.output


# AC-I-2 (ambiguous)
def test_inspect_exits_2_on_ambiguous_gate_run_id(tmp_path: Path, monkeypatch) -> None:
    for run in ("run-a", "run-b"):
        (tmp_path / ".codegenie/remediation" / run / "gates" / "stage6_validate").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["sandbox", "inspect", "stage6_validate"])
    assert result.exit_code == 2
    assert "ambiguous gate-run-id" in result.output


# AC-I-3, AC-I-4, AC-I-5, AC-I-8 — happy path with chain-head match
def test_inspect_uses_entries_renders_markers_and_attempts(
    tmp_path: Path, monkeypatch, fake_attempt_factory  # helper exposed by conftest
) -> None:
    run_dir = tmp_path / ".codegenie/remediation/run-1"
    gate_dir = run_dir / "gates" / "stage6_validate"
    gate_dir.mkdir(parents=True)
    ledger = RetryLedger(run_dir=gate_dir, gate_id="stage6_validate", prev_chain_head=None)
    ledger.record_pre_execute(attempt_id=1, sandbox_spec_hash="ab" * 16, started_at=_utc_now())
    ledger.record(fake_attempt_factory(1))
    ledger.record_pre_execute(attempt_id=2, sandbox_spec_hash="cd" * 16, started_at=_utc_now())
    ledger.record(fake_attempt_factory(2))
    (run_dir / "chain_head.bin").write_bytes(ledger.head())

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["sandbox", "inspect", "run-1:stage6_validate"])

    assert result.exit_code == 0, result.output
    assert "attempt_id" in result.output and "chain_hash" in result.output
    assert "►" in result.output, "pre_execute markers must use the ► (U+25BA) prefix row"
    assert result.output.count("►") == 2, "expected 2 marker rows for 2 markers"
    assert "chain-head-match: yes" in result.output


# AC-I-7 — RetryLedger constructed with prev_chain_head=None (ADR-0005)
def test_inspect_constructs_ledger_with_prev_chain_head_none() -> None:
    """Belt-and-braces source assertion: substring `prev_chain_head=` appears exactly
    once in cli/sandbox/__init__.py (or sandbox.py) and its literal arg is `None`."""
    from codegenie.cli import sandbox as cli_sandbox
    src = Path(cli_sandbox.__file__).read_text()
    occurrences = [ln for ln in src.splitlines() if "prev_chain_head=" in ln]
    assert len(occurrences) == 1, f"expected one occurrence, got {len(occurrences)}: {occurrences}"
    assert "prev_chain_head=None" in occurrences[0]


# AC-I-6 — chain corruption uses the kernel exit-code constant via subprocess witness
def test_inspect_exits_13_on_tampered_chain(
    tmp_path: Path, monkeypatch, fake_attempt_factory
) -> None:
    run_dir = tmp_path / ".codegenie/remediation/run-1"
    gate_dir = run_dir / "gates" / "stage6_validate"
    gate_dir.mkdir(parents=True)
    ledger = RetryLedger(run_dir=gate_dir, gate_id="stage6_validate", prev_chain_head=None)
    ledger.record(fake_attempt_factory(1))
    ledger.record(fake_attempt_factory(2))

    # Tamper: flip a single byte in attempts.jsonl.
    jsonl = gate_dir / "attempts.jsonl"
    raw = jsonl.read_bytes()
    mid = len(raw) // 2
    jsonl.write_bytes(raw[:mid] + bytes([raw[mid] ^ 0xFF]) + raw[mid + 1:])

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["sandbox", "inspect", "run-1:stage6_validate"])
    assert result.exit_code == EXIT_CHAIN_CORRUPTED == 13
    err = json.loads(result.stderr)
    assert err["error"] == "audit_chain_corrupted"
    assert err["kind"] in {"chain_mismatch", "schema_error", "extra_field"}
    assert isinstance(err["row_index"], int)


# AC-I-8 — chain-head absent
def test_inspect_reports_chain_head_absent_when_file_missing(
    tmp_path: Path, monkeypatch, fake_attempt_factory
) -> None:
    run_dir = tmp_path / ".codegenie/remediation/run-1"
    gate_dir = run_dir / "gates" / "stage6_validate"
    gate_dir.mkdir(parents=True)
    ledger = RetryLedger(run_dir=gate_dir, gate_id="stage6_validate", prev_chain_head=None)
    ledger.record(fake_attempt_factory(1))
    # NO chain_head.bin written.

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["sandbox", "inspect", "run-1:stage6_validate"])
    assert result.exit_code == 0
    assert "chain-head-match: absent" in result.output


# AC-I-8 — chain-head mismatch
def test_inspect_warns_on_chain_head_mismatch_but_exit_0(
    tmp_path: Path, monkeypatch, fake_attempt_factory
) -> None:
    run_dir = tmp_path / ".codegenie/remediation/run-1"
    gate_dir = run_dir / "gates" / "stage6_validate"
    gate_dir.mkdir(parents=True)
    ledger = RetryLedger(run_dir=gate_dir, gate_id="stage6_validate", prev_chain_head=None)
    ledger.record(fake_attempt_factory(1))
    (run_dir / "chain_head.bin").write_bytes(b"\x00" * 16)  # wrong head

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["sandbox", "inspect", "run-1:stage6_validate"])
    assert result.exit_code == 0
    assert "chain-head-match: no" in result.output
    assert "chain-head mismatch" in result.stderr


# ---------- C. gc ----------

# AC-G-1 — parametrized rejection table
@pytest.mark.parametrize(
    "bad",
    ["7days", "7D", "-7d", "0d", "", "7", "7dx", "7s", " 7d", "7d "],
)
def test_parse_age_window_rejects_malformed(bad: str) -> None:
    import click
    with pytest.raises(click.BadParameter):
        _parse_age_window(bad)


# AC-G-1 — Hypothesis property
@given(n=st.integers(min_value=1, max_value=10_000), unit=st.sampled_from("dhm"))
def test_parse_age_window_yields_positive_timedelta(n: int, unit: str) -> None:
    td = _parse_age_window(f"{n}{unit}")
    assert td > timedelta(0)


# AC-G-2 — GC_ROOTS mutation backstop
def test_gc_roots_is_pinned_tuple() -> None:
    assert isinstance(GC_ROOTS, tuple)
    assert len(GC_ROOTS) == 2  # mutation: a future contributor adding a 3rd must update this AC
    assert all(isinstance(r, str) for r in GC_ROOTS)


# AC-G-3, AC-G-4 — idempotence + survival set
def test_gc_idempotent_and_preserves_kernel_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    # Aged sandbox run dir (mtime > 7d old)
    aged_run = tmp_path / ".codegenie/sandbox/runs/aged"
    aged_run.mkdir(parents=True)
    aged_run_inner = aged_run / "logs"
    aged_run_inner.mkdir()
    eight_days_ago = time.time() - (8 * 86400)
    os.utime(aged_run_inner, (eight_days_ago, eight_days_ago))
    os.utime(aged_run, (eight_days_ago, eight_days_ago))

    # Survival set inside the gate dir.
    gate_dir = tmp_path / ".codegenie/remediation/r1/gates/g1"
    gate_dir.mkdir(parents=True)
    survival_set = {
        gate_dir / "attempts.jsonl": b'{"type":"attempt","attempt_id":1,...}\n',
        gate_dir / "manifest.yaml": b"gate_id: g1\n",
        gate_dir / "chain_head.bin": b"\x00" * 16,
        gate_dir / "cost.jsonl": b'{"kind":"sandbox.run",...}\n',
    }
    for p, body in survival_set.items():
        p.write_bytes(body)

    runner = CliRunner()
    r1 = runner.invoke(cli, ["sandbox", "gc", "--older-than", "7d"])
    assert r1.exit_code == 0, r1.output
    payload1 = json.loads([ln for ln in r1.output.splitlines() if ln.startswith("{")][-1])
    assert payload1["removed"] >= 1
    assert payload1["older_than"] == "7d"
    assert payload1["partial"] is False

    # Survival assertion — byte-identical contents.
    for p, expected_body in survival_set.items():
        assert p.exists(), f"{p} must survive gc"
        assert p.read_bytes() == expected_body

    r2 = runner.invoke(cli, ["sandbox", "gc", "--older-than", "7d"])
    payload2 = json.loads([ln for ln in r2.output.splitlines() if ln.startswith("{")][-1])
    assert r2.exit_code == 0
    assert payload2["removed"] == 0
    # Survival set still intact after the second pass.
    for p, expected_body in survival_set.items():
        assert p.read_bytes() == expected_body


# AC-G-6 — no rglob / no os.walk
def test_gc_walker_uses_only_glob_over_GC_ROOTS() -> None:
    import ast
    from codegenie.cli.sandbox import _gc
    tree = ast.parse(Path(_gc.__file__).read_text())
    forbidden = {"rglob", "walk"}
    found = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in forbidden
    }
    assert not found, f"gc must not recurse via {found}"


# ---------- D. prepare ----------

# AC-P-1 — registry-dispatched (zero direct backend imports in cli/sandbox)
def test_cli_sandbox_has_no_backend_imports() -> None:
    from codegenie.cli import sandbox as cli_sandbox
    pkg_dir = Path(cli_sandbox.__file__).parent
    forbidden_prefixes = (
        "from codegenie.sandbox.did",
        "from codegenie.sandbox.firecracker",
        "from codegenie.sandbox.chainguard",
        "from codegenie.sandbox.gvisor",
    )
    for src_path in pkg_dir.rglob("*.py"):
        src = src_path.read_text()
        for prefix in forbidden_prefixes:
            assert prefix not in src, f"{src_path}: must not import backends directly"


# AC-P-2 — DinD preparer is a no-op
def test_did_preparer_is_noop() -> None:
    outcome = get_preparer("docker_in_docker").prepare(verify=False)
    assert outcome.already_prepared is True
    assert outcome.bake_invoked is False
    assert outcome.verified is False
    assert outcome.backend == "docker_in_docker"


# AC-P-3 + M-1 — fast-path skip means bake is NEVER invoked
def test_prepare_skips_when_rootfs_file_exists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    rootfs_digest = "a" * 64
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/digests.yaml").write_text(f"sandbox:\n  rootfs: {rootfs_digest}\n")
    rootfs_dir = tmp_path / f"tools/firecracker/{rootfs_digest}"
    rootfs_dir.mkdir(parents=True)
    (rootfs_dir / "rootfs.ext4").write_bytes(b"fake-but-existence-only")

    def _fail_bake(**kw):
        pytest.fail("bake must not run on fast path (AC-P-3 / M-1)")

    monkeypatch.setattr("codegenie.sandbox.firecracker.rootfs.bake", _fail_bake)

    result = CliRunner().invoke(cli, ["sandbox", "prepare", "--backend", "firecracker"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["already_prepared"] is True
    assert payload["bake_invoked"] is False
    assert payload["verified"] is False


# AC-P-4 — rebake when rootfs file missing
def test_prepare_invokes_bake_when_rootfs_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    rootfs_digest = "b" * 64
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/digests.yaml").write_text(f"sandbox:\n  rootfs: {rootfs_digest}\n")

    bake_calls: list[dict] = []
    def _stub_bake(**kw):
        target = tmp_path / f"tools/firecracker/{rootfs_digest}/rootfs.ext4"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"baked")
        bake_calls.append(kw)

    monkeypatch.setattr("codegenie.sandbox.firecracker.rootfs.bake", _stub_bake)

    result = CliRunner().invoke(cli, ["sandbox", "prepare", "--backend", "firecracker"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["already_prepared"] is False
    assert payload["bake_invoked"] is True
    assert len(bake_calls) == 1


# AC-P-5 — --verify mismatch raises RootfsDigestMismatch
def test_prepare_verify_mismatch_exits_1(tmp_path: Path, monkeypatch) -> None:
    import blake3
    monkeypatch.chdir(tmp_path)
    wrong_digest = "c" * 64
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/digests.yaml").write_text(f"sandbox:\n  rootfs: {wrong_digest}\n")
    rootfs_dir = tmp_path / f"tools/firecracker/{wrong_digest}"
    rootfs_dir.mkdir(parents=True)
    body = b"actual-content-with-different-digest"
    (rootfs_dir / "rootfs.ext4").write_bytes(body)

    result = CliRunner().invoke(
        cli, ["sandbox", "prepare", "--backend", "firecracker", "--verify"]
    )
    assert result.exit_code == 1
    err = json.loads(result.stderr)
    assert err["error"] == "rootfs_digest_mismatch"


# AC-P-6 — macOS no-KVM
def test_prepare_firecracker_on_no_kvm_exits_1(monkeypatch) -> None:
    def _raise_no_kvm(**kw):
        raise FirecrackerKvmMissing("/dev/kvm not present")
    monkeypatch.setattr(
        "codegenie.sandbox.registry.get_preparer",
        lambda name: type("_P", (), {"prepare": staticmethod(_raise_no_kvm)})(),
    )
    result = CliRunner().invoke(cli, ["sandbox", "prepare", "--backend", "firecracker"])
    assert result.exit_code == 1
    err = json.loads(result.stderr)
    assert err["error"] == "firecracker_kvm_missing"
    assert "DinD is the supported macOS backend" in err["hint"]


# ---------- E. Cross-cutting ----------

# AC-X-1 — event-constant kernel discipline
def test_no_bare_cli_sandbox_event_literals_in_src() -> None:
    src_dir = Path(__file__).resolve().parents[2] / "src/codegenie/cli"
    bare = []
    for py in src_dir.rglob("*.py"):
        for ln in py.read_text().splitlines():
            if '"cli.sandbox.' in ln and "EVENT_CLI_SANDBOX" not in ln:
                bare.append(f"{py}: {ln.strip()}")
    assert not bare, f"bare event literals found: {bare}"


# AC-X-2 — per-event field set (one example shown; mirror for the other three)
def test_event_cli_sandbox_health_field_set(monkeypatch) -> None:
    import structlog
    from structlog.testing import capture_logs

    fake = SandboxHealth(
        backend="docker_in_docker",
        reachable=True,
        confidence="high",
        reasons=[],
        warnings=[],
        detected_at=_utc_now(),
    )

    class _FakeClient:
        def health(self): return fake
        def execute(self, spec): raise NotImplementedError

    monkeypatch.setattr("codegenie.sandbox.registry.auto_detect", lambda: _FakeClient())

    with capture_logs() as logs:
        CliRunner().invoke(cli, ["sandbox", "health"])

    health_events = [e for e in logs if e.get("event") == "cli.sandbox.health"]
    assert len(health_events) == 1
    keys_of_interest = {"backend", "reachable", "confidence", "exit_code"}
    assert keys_of_interest <= set(health_events[0].keys())


# AC-X-4 — exit-code kernel is additive
def test_exit_codes_kernel_is_additive() -> None:
    from codegenie.cli import exit_codes
    assert hasattr(exit_codes, "EXIT_CHAIN_CORRUPTED")
    assert exit_codes.EXIT_CHAIN_CORRUPTED == 13
    # S7-04's constant must still exist and have its original value (extension-by-addition).
    assert hasattr(exit_codes, "EXIT_REPO_ALREADY_IN_PROGRESS")
    assert exit_codes.EXIT_REPO_ALREADY_IN_PROGRESS == 14
    # No collisions.
    values = [getattr(exit_codes, name) for name in exit_codes.__all__ if name.startswith("EXIT_")]
    assert len(values) == len(set(values))
```

`tests/cli/conftest.py` exposes a `fake_attempt_factory(attempt_id)` fixture that returns a valid `Attempt(...)` with a stable canonical payload (sourced from S2-01 / S1-04 test helpers).

### Green

Implement only what each red test demands. `_render_health` is one `click.echo` per field. `_render_attempts` is one printf-style line per row. `gc` uses `Path.stat().st_mtime` + `time.time() - window.total_seconds()`. `prepare` short-circuits on digest match before any `bake(...)` import is invoked (assert via `monkeypatch.setattr` raising if called when it shouldn't be).

### Refactor

- The pure-helper extractions (`_render.py`, `_resolve.py`, `_gc.py`) are already required during GREEN by ACs above — Refactor only adds `__all__` exports and `--help` epilog text.
- `--help` for each subcommand has one example line and a one-line description of the exit-code table (`0`, `1`, `2`, `13`, `14`).
- The four-subcommand epilog references `docs/phases/05-sandbox-trust-gates/phase-arch-design.md §CLI surface` for the canonical documentation.
- A `tests/cli/sandbox/test_resolve.py` covers `resolve_gate_run` (the colon form, the glob fallback, ambiguous and unknown branches).
- A `tests/cli/sandbox/test_gc_parser.py` covers `_parse_age_window` (the rejection table + Hypothesis property).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli/__init__.py` | Promoted from flat `cli.py` (if still flat); top-level Click group registers `sandbox`. Re-exports every existing public symbol. |
| `src/codegenie/cli/exit_codes.py` | **Extended additively** with `EXIT_CHAIN_CORRUPTED: Final[int] = 13` appended under `__all__`. (Kernel from S7-04; existing constants byte-stable.) |
| `src/codegenie/cli/sandbox/__init__.py` | New — the `@click.group("sandbox")` + four subcommand functions. ≤ 20 LOC each. |
| `src/codegenie/cli/sandbox/_render.py` | Pure pretty-printers for `SandboxHealth`, `Attempt`-row, `PreExecuteMarker`-row. |
| `src/codegenie/cli/sandbox/_resolve.py` | `resolve_gate_run`, `_CLI_BACKEND_NAMES` map. |
| `src/codegenie/cli/sandbox/_gc.py` | `_parse_age_window`, `GC_ROOTS`, the gc walker. |
| `src/codegenie/sandbox/logging.py` | **Extended additively** with `EVENT_CLI_SANDBOX_{HEALTH, INSPECT, GC, PREPARE}: Final[str]` appended under `__all__`. |
| `src/codegenie/sandbox/contract.py` | **Extended additively** with `_BACKEND_TO_ISOLATION: Final[Mapping[...]]`. The `SandboxRun` `@model_validator` (S1-02 AC-7b) is rewritten to consult this constant instead of an inline whitelist — replaces the inline literal but keeps behavior byte-stable; S1-02's tests stay green. |
| `src/codegenie/sandbox/registry.py` | **Extended additively** with the `BackendPreparer` Protocol, `PrepareOutcome` Pydantic model, `register_preparer` decorator, `get_preparer(name) -> BackendPreparer`. |
| `src/codegenie/sandbox/did/preparer.py` | New — no-op DinD preparer (returns `PrepareOutcome(already_prepared=True, ...)`). Registers at import time. |
| `src/codegenie/sandbox/firecracker/preparer.py` | New — Firecracker preparer with fast-path file-existence check + `--verify` BLAKE3 rehash + KVM precheck. Registers at import time. |
| `src/codegenie/sandbox/errors.py` (or wherever sandbox errors live) | **Extended additively** with `class RootfsDigestMismatch(SandboxError)` carrying `.expected`, `.actual`, `.path`. |
| `tests/cli/test_sandbox_cli.py` | The red tests above; AC-prefixed comments. |
| `tests/cli/sandbox/test_resolve.py` | Focused tests for `resolve_gate_run`. |
| `tests/cli/sandbox/test_gc_parser.py` | Focused tests for `_parse_age_window` + Hypothesis property. |
| `tests/cli/conftest.py` | Shared `fake_attempt_factory` fixture + `tmp_codegenie_repo` skeleton. |
| `tests/fence/test_cli_sandbox_backend_addition.py` | The Open/Closed AST scan (AC-X-3). |

## Out of scope

- `codegenie remediate` flag wiring (`--sandbox-backend`, `--max-attempts-override`, `--allow-test-network`) — S8-02.
- The headline E2E test — S8-03.
- Coverage report and ADR audit — S8-04.
- Rich/Tabulate dependency — `click.echo` is sufficient; do not pull a table library for this story.
- Phase 11 evidence-bundle export — Phase 11 owns it; `inspect` only reads.
- Concurrent-invocation safety on `gc` — `fcntl.flock` from S7-04 covers `remediate`; `gc` is a pure filesystem operation and acceptably racy with itself.

## Notes for the implementer

### Architecture-shaping constraints (read first)

- **The CLI is a thin Open/Closed shell.** `cli/sandbox.py` (or the `cli/sandbox/` package) MUST NOT import anything from `codegenie.sandbox.did`, `codegenie.sandbox.firecracker`, `codegenie.sandbox.chainguard`, or any concrete backend module. Backend variation flows through three kernels:
  - `_CLI_BACKEND_NAMES` (CLI string → registry string) in `cli/sandbox/_resolve.py`.
  - `_BACKEND_TO_ISOLATION` (registry string → isolation literal) in `sandbox/contract.py`.
  - `register_preparer` / `get_preparer` in `sandbox/registry.py`.
  This is the **same kernel-plus-registry-of-capabilities shape** Phase 0's `@register_probe`, Phase 5 S1-05's `@register_sandbox_backend`, and Phase 3's `@register_dep_graph_strategy` already use. Phase 7's chainguard backend lands as one entry per kernel + one new `chainguard/preparer.py`. Zero edits to `cli/sandbox/`.
- **`inspect` uses `RetryLedger.entries()` (S2-02), NOT `attempts()` + secondary parse.** `entries()` returns `list[LedgerEntry]` where `LedgerEntry: TypeAlias = PreExecuteMarker | Attempt`, re-verifies the BLAKE3 chain across mixed rows in one pass, and gives a clean `isinstance`-based dispatch. The original draft's "open `attempts.jsonl` a second time line-by-line" is a smell — duplicate parse, no chain check on the marker rows, and uses a non-existent `payload["kind"]` (the discriminator is `payload["type"]`).
- **`gate_isolation_class` is NOT on `SandboxClient` and NOT on `SandboxHealth`.** Per S1-02 HARDENED AC-2a, the Protocol member set is exactly `{execute, health}`. Source the isolation class from `_BACKEND_TO_ISOLATION[health.backend]` — a single module-level constant in `sandbox/contract.py` that is *also* the source of truth for `SandboxRun`'s `@model_validator` whitelist. One place to update; the executor's validator catches drift.
- **The CLI must construct `RetryLedger(..., prev_chain_head=None)`** (ADR-0005). `inspect` is read-only — startup chain-head verification is `RetryLedger.__init__`'s job for `GateRunner`-driven sessions, not the inspector's. Display the match/mismatch result *separately* after construction.

### Exit-code kernel

- `EXIT_CHAIN_CORRUPTED: Final[int] = 13` is appended to `cli/exit_codes.py` (the kernel created by S7-04). The kernel now carries:
  - `0` (`EXIT_OK`), `1` (`EXIT_GENERAL`), `2` (`EXIT_USAGE`)
  - `11` (`EXIT_ESCALATE`), `12` (`EXIT_FAILED_UNRECOVERABLE`)
  - `13` (`EXIT_CHAIN_CORRUPTED`) — **this story**
  - `14` (`EXIT_REPO_ALREADY_IN_PROGRESS`) — from S7-04
- Document the full table in each subcommand's `--help` epilog.

### Discriminator key

- The ledger JSONL row discriminator is `payload["type"]`, not `payload["kind"]`. S2-01 AC-T-1 froze this; the `pre_execute` row shape is `{"type": "pre_execute", ...}`. A future contributor who writes `payload["kind"] == "pre_execute"` is invoking a `KeyError`.

### `prepare` fast path

- Re-hashing a multi-GB rootfs on every operator `prepare` invocation is unacceptable. The content-addressed dir layout (`tools/firecracker/<rootfs_digest>/rootfs.ext4`) means **file existence is the integrity claim**; `--verify` opts into the full BLAKE3-256 recompute and raises `RootfsDigestMismatch` on tamper. Default UX: instant.
- The DinD preparer is a no-op returning `PrepareOutcome(already_prepared=True, bake_invoked=False, ...)` — NOT an error. Operators routinely run `prepare` without thinking about backend; failing on DinD is unfriendly.

### macOS Firecracker

- macOS contributors running `prepare --backend firecracker` hit `FirecrackerKvmMissing`. That is expected. The stderr hint must be the exact string `"DinD is the supported macOS backend; use --backend did or omit"` so the operator copy-pastes a working command. The error JSON shape is canonical (sorted keys, single line).

### `gc` discipline

- `gc` walks via `Path(repo_root).glob(root)` for each `root in GC_ROOTS`. **No `Path.rglob`**, **no `os.walk`** (the AST scan AC-G-6 enforces this). The only sandbox-mtime-aged path types are sibling sandbox-run dirs and per-gate `sandbox/<sandbox_run_id>/` subdirs — never the `attempts.jsonl`-bearing root.
- `GC_ROOTS: Final[tuple[str, ...]]` is the data; the walker is one loop. Phase 9 Temporal worker-state cleanup lands by appending one tuple entry; the AC-G-2 mutation backstop (asserting `len(GC_ROOTS) == 2`) catches it during validation.
- Lifecycle: the walker runs inside a `contextlib.ExitStack`. A Ctrl+C mid-walk emits the canonical JSON with `partial: true` and exits 130 — never silent truncation.

### Event-name discipline

- All four events are `Final[str]` constants in `sandbox/logging.py` (S1-01's kernel). Bare `"cli.sandbox.*"` literals fail the AC-X-1 AST scan. The S1-01 audit-string rename test continues to pass because every name lives in the kernel.
- Each event's field set is pinned via `structlog.testing.capture_logs()` (S5-02 AC-OBS-1 precedent). The sets are tight — no env, no absolute paths outside `repo_root`, chain hashes truncated to 8 chars.

### CLI package migration

- If `src/codegenie/cli.py` is still a flat file when this story lands, promote it to `src/codegenie/cli/__init__.py` *additively*: re-export every existing public symbol via `__all__`. Verify by running `pytest tests/cli/` (existing tests) before adding the `sandbox` sub-group.

### Coverage + fence

- Coverage gate is per-file: `src/codegenie/cli/sandbox/**.py` ≥ 90% line, ≥ 80% branch. The fence test (`tests/fence/test_cli_sandbox_backend_addition.py`) enforces the Open/Closed contract and is fast enough for every PR (one AST walk over the `cli/sandbox/` directory).
