# Story S3-04 — DinD `copy_out.py` + OOM detection + `time_budget_seconds` SIGKILL

**Step:** Step 3 — Implement DinD backend + SandboxSpecBuilder + SandboxHealthProbe
**Status:** Ready (HARDENED 2026-05-23)
**Effort:** M
**Depends on:**
- **S1-02 HARDENED** — `SandboxClient` Protocol, `SandboxSpec` (`copy_out: list[str]`, `time_budget_seconds: int`), `SandboxRun` (frozen 13-field model — `copy_out_root: Path`, `timed_out: bool`, `killed_by_oom: bool`, cross-field invariant `not (timed_out and killed_by_oom)` per AC-7d), `RunId = NewType("RunId", str)`.
- **S3-02 HARDENED** — `DockerInDockerClient` SDK core, `_construct_sandbox_run` (single source of truth for `SandboxRun` construction — widened additively here), `_build_container_kwargs`, `_wrap_api_error`, `_GATE_ISOLATION_CLASS: Final = "shared_kernel"`, `_BACKEND_NAME`, `AC-SPEC-DEFER-4` (`copy_out != []` → `NotImplementedError`), `AC-SPEC-DEFER-6` (non-default `time_budget_seconds` → `EVENT_SANDBOX_DID_TIMEOUT_DEFERRED` WARNING), `AC-RUN-FIELDS-14/-15/-16` (stub values for `copy_out_root` / `timed_out` / `killed_by_oom`).
- **S3-03 HARDENED** — `SandboxBackendError.reason: Literal[...]` (11-member closed union — widened additively here to 15), shared `_DEFAULT_RUN_KWARGS` precedent (NOT shared from S3-04; copy-out uses no subprocess), `EVENT_*` `Final[str]` naming convention (`STARTED/COMPLETED/FAILED`).

**ADRs honored:**
- ADR-0001 (two chokepoints) — `copy_out.py` is **not** in the subprocess allowlist; SDK-only (`container.get_archive`, `container.exec_run` list-form, `container.wait`, `container.kill`, `container.reload`). No ADR amendment required.
- ADR-0004 (`shared_kernel` annotation) — `_construct_sandbox_run` stamps `gate_isolation_class` once for **every** exit path (normal / timeout / OOM); cannot diverge.
- ADR-0006 (Protocol-vs-ABC convention) — `_is_wait_timeout` ships as a pure function with kwarg-injectable signature; `CopyOutExtractor` Protocol abstraction deferred (rule-of-three not reached; S6-01 Firecracker is the second known consumer).
- ADR-0014 (frozen Pydantic models) — `_WaitOutcome` sum type members are `@dataclass(frozen=True, slots=True)` (internal — not crossing the contract); `SandboxRun` contract surface unchanged.

## Validation notes (HARDENED 2026-05-23)

This story was hardened via `phase-story-validator`. The full report lives at [`_validation/S3-04-did-copy-out-oom-timeout.md`](_validation/S3-04-did-copy-out-oom-timeout.md). Ten block-tier + seventeen harden/nit findings resolved.

Highest-impact changes from the original draft:

1. **`copy_out_root` path corrected to match S3-02 HARDENED.** Draft pinned `logs_dir / "copy_out"`; S3-02 HARDENED AC-RUN-FIELDS-14 + AC-LOGS-3 pin `logs_dir.parent / "copy_out" / str(run_id)` and Phase 11 evidence bundle keys on that exact path. Fixed in AC-PATH-1..-3 + fence-test.
2. **All `SandboxRun` construction routes through `_construct_sandbox_run`.** S3-02 HARDENED AC-FCS-3 is the single source of truth that stamps `backend`, `gate_isolation_class`, and the seven stub fields. S3-04 widens this helper additively with three new kwargs (`outcome: _WaitOutcome`, `copy_out_root: Path`, `image_pull_bytes: int`); defaults preserve S3-02 zero-stub call sites. Meta-test caps `SandboxRun(` literal call sites at 1.
3. **`_WaitOutcome` sum type makes mutual exclusion unrepresentable.** Internal discriminated union `Normal(exit_code) | TimedOut(exit_code=137) | OomKilled(exit_code=137)`; `_classify_wait_outcome(...)` is the only constructor; pattern-matched in `_construct_sandbox_run` to stamp the flat `timed_out` / `killed_by_oom` fields. An implementation that returns `(True, True, …)` cannot construct the union.
4. **Event names follow `STARTED/COMPLETED/FAILED` verb convention** (S1-01 HARDENED / S3-03 HARDENED). Six `EVENT_*` `Final[str]` constants; namespace regex + table-extension test pinned.
5. **`EVENT_SANDBOX_DID_TIMEOUT_DEFERRED` REMOVED, not left dormant.** S3-02 wired this WARNING for non-default `time_budget_seconds`; with S3-04 honoring the timeout, the emit is wrong (every configured gate would spam it). The S3-02 test `test_spec_defer_time_budget_warns` is **replaced** (not deleted silently). Rule 12 — loud removal.
6. **S3-02 AC widening enumerated.** Section M (AC-WIDEN-1..-5) explicitly names every S3-02 AC modified: AC-SPEC-DEFER-4 (`copy_out != []`) and AC-SPEC-DEFER-6 (`time_budget_seconds`) become real; AC-RUN-FIELDS-15/-16 (stub `False`) become real classification.
7. **Tar path-traversal guard lifted from Refactor to AC.** Two-layer defense — pure `_safe_resolve(member.name, dest_root)` policy + stdlib `tarfile.extract(..., filter="data")` belt-and-suspenders. Adversarial corpus (5 fixtures) + property test. PEP 706 cited.
8. **Glob resolution drops `sh -c` entirely.** Draft outline's `["sh", "-c", f"ls -1 {glob}"]` is shell-injection-vulnerable for any future LLM-influenced gate-catalog edit. S3-04 uses list-form `container.exec_run(["find", "--", glob, "-maxdepth", str(_MAX_GLOB_DEPTH), "-print0"])` with no shell. Meta-test greps `copy_out.py` for `"sh"`/`-c` substrings → zero.
9. **Second `wait()` after `kill()` is bounded.** `_REAP_GRACE_SECONDS: Final[int] = 5`; failure raises new `SandboxBackendError("reap_failed", …)` (4-member additive widening of S3-03's 11-member closed Literal reason union, total 15).
10. **`copy_out_root` exists on every exit path.** Normal / timeout / OOM all create the dir; copy-out is attempted best-effort on timeout/OOM (the container may be partially dead — WARN, do not raise). 4-cell parametrized cleanup grid pins the ordering: `kill → bounded-wait → copy-out (best-effort) → remove`.

**Rule-of-four pattern elevations** (S3-01 → S3-02 → S3-03 → S3-04):
- **Functional core / imperative shell** — five pure helpers (`_safe_resolve`, `_extract_tar_stream`, `_is_wait_timeout`, `_classify_wait_outcome`, widened `_construct_sandbox_run`) + two impure shells (`copy_out`, `execute`). AST-purity walker for `copy_out.py`.
- **Hexagonal DI port** — `_is_wait_timeout` injectable via kwarg (production default = the canonical classifier); tests inject without `mock.patch`. Meta-test forbids `mock.patch("requests.exceptions`.

**Deferred per Rule 2 (YAGNI — rule-of-three not reached):**
- `CopyOutExtractor` Protocol — promote when a third copy-out consumer lands (S6-01 Firecracker is the second).
- `_TarMember` sum type (Regular | Directory | Symlink | Hardlink | Skip) — `member.isfile()` short-circuit + `_safe_resolve` cover the security policy; promote when copy-out semantics need symlink preservation (Phase 13+).
- `GlobPattern = NewType("GlobPattern", str)` — one validation site; promote at second consumer.

## Context

A `SandboxRun` is only useful to downstream collectors if its artifacts arrive — `logs_dir` plus the load-bearing `copy_out_root` (= `logs_dir.parent / "copy_out" / str(run_id)`, pinned by S3-02 HARDENED AC-RUN-FIELDS-14) carry `stdout.log`, `stderr.log`, `trace.jsonl`, `policy.json`, `sbom.json`, and any glob-matched files from `spec.copy_out`. This story wires that copy-out path.

It also widens three S3-02 HARDENED `SPEC-DEFER` raise-paths into real implementations:
- **AC-SPEC-DEFER-4** (`copy_out != []` → `NotImplementedError("sandbox.did: spec.copy_out deferred to S3-04")`) becomes a working SDK tar-stream extraction.
- **AC-SPEC-DEFER-6** (`time_budget_seconds` non-default → `EVENT_SANDBOX_DID_TIMEOUT_DEFERRED` WARNING) becomes a real SIGKILL path; the WARNING event and its test are removed (loudly, see AC-WIDEN-3 and AC-WIDEN-4).
- **AC-RUN-FIELDS-15 / -16** (stub `timed_out=False`, `killed_by_oom=False`) become real classifications via `_WaitOutcome`.

The Phase 5 cross-field invariant `not (timed_out and killed_by_oom)` (S1-02 HARDENED AC-7d) is made **unrepresentable** by routing all wait-outcome stamping through an internal `_WaitOutcome` discriminated union — `Normal | TimedOut | OomKilled`. The flat `SandboxRun` contract surface is unchanged; the producer pattern just cannot construct an illegal combination.

Copy-out uses the Docker SDK's `container.get_archive()` (tar-stream extraction) and `container.exec_run([list-form])` (glob resolution) — both stay out of the subprocess chokepoint per ADR-0001. The golden-file test `tests/golden/docker_cp_args_stage6_validate.json` snapshots the **`get_archive` argument tuples + resolved glob paths** for the stage6 spec.

This story is the **fourth concrete consumer** of two Phase-5 patterns — hexagonal DI port (S3-01 → S3-02 → S3-03 → here) and functional-core/imperative-shell split (same lineage) — both elevated as ACs (sections E + N).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — DockerInDockerClient` (lines 486–493) — "wraps timeout into `SandboxRun(timed_out=True)`; wraps OOM (detected via `docker inspect` State.OOMKilled) into `SandboxRun(killed_by_oom=True)`".
  - `../phase-arch-design.md §Edge case 3` (line 855) — `time_budget_seconds` → SIGKILL → `timed_out=True`; non-retryable by default (`retry_policy.timeout_retryable=False`, out-of-scope for this story; wired in GateRunner Step 5).
  - `../phase-arch-design.md §Edge case 4` (line 856) — `docker inspect State.OOMKilled` → `killed_by_oom=True`; non-retryable.
  - `../phase-arch-design.md §Testing strategy — Golden files` (line 892) — `tests/golden/docker_cp_args_<scenario>.json`.
  - `../phase-arch-design.md §Data model — SandboxSpec / SandboxRun` (lines 640–674) — every field this story populates.
- **Phase ADRs:**
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — ADR-0001 — `copy_out.py` is **not** in the subprocess allowlist; SDK-only.
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — ADR-0004 — `gate_isolation_class="shared_kernel"` stamped on every exit path.
  - `../ADRs/0006-protocol-vs-abc-convention.md` — ADR-0006 — Protocol deferral until rule-of-three.
  - `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — ADR-0014 — frozen Pydantic for cross-contract types.
- **Prior HARDENED validation reports** (pattern-lineage anchors):
  - `_validation/S1-01-scaffold-packages-errors-structlog.md` — closed Literal `reason` discriminator pattern, `EVENT_*` `Final[str]` naming.
  - `_validation/S3-01-spec-builder-canonical-hash.md` — first FCS consumer (`_canonical_blake3`, `_deep_merge`, `_assemble_partial_spec`, `_compute_hash_input`).
  - `_validation/S3-02-did-client-sdk-core.md` — second FCS + DI consumer; `_construct_sandbox_run` single-source-of-truth contract; `copy_out_root` path pin (AC-RUN-FIELDS-14, AC-LOGS-3); `EVENT_SANDBOX_DID_TIMEOUT_DEFERRED` warning being removed here.
  - `_validation/S3-03-did-build-and-network-chokepoints.md` — third FCS + DI consumer; closed Literal `reason` widening pattern (11 members; this story adds 4 more to reach 15); shared subprocess kwargs deferred per Rule 2.
- **Source design:**
  - `../final-design.md §Synthesis ledger — Trace soft signal row` — informs why `timed_out` is non-retryable but configurable per `retry_policy.timeout_retryable` (S5 GateRunner-scope).
- **Existing code (post-S3-02 / S3-03):**
  - `src/codegenie/sandbox/did/client.py` — `execute()` and `_construct_sandbox_run`; widened by this story.
  - `src/codegenie/sandbox/contract.py` (from S1-02 HARDENED) — `SandboxRun.copy_out_root: Path`, `timed_out: bool`, `killed_by_oom: bool`, cross-field invariant.
  - `src/codegenie/sandbox/errors.py` (post-S1-01 / S3-03) — `SandboxBackendError.reason` closed Literal (11 members); widened here to 15.
  - `src/codegenie/sandbox/did/logging.py` (or `events.py`, per S1-01 HARDENED) — `EVENT_*` `Final[str]` table; appended here with 6 new constants.
  - `src/codegenie/types/identifiers.py` — `RunId = NewType("RunId", str)`; propagated to all new structlog events.
- **External docs:**
  - https://docker-py.readthedocs.io/en/stable/containers.html#docker.models.containers.Container.get_archive — tar-stream API.
  - https://docker-py.readthedocs.io/en/stable/containers.html#docker.models.containers.Container.kill — SIGKILL via SDK.
  - https://docker-py.readthedocs.io/en/stable/containers.html#docker.models.containers.Container.wait — `timeout=` kwarg + exception class.
  - https://peps.python.org/pep-0706/ — `tarfile.extractall(filter="data")` (Python 3.12+).
  - https://docs.python.org/3/library/tarfile.html#extraction-filters — `data` filter exact semantics.

## Goal

Wire the three S3-02 deferred SDK paths through a **producer-side discriminated union** (`_WaitOutcome`) that makes the `not (timed_out and killed_by_oom)` invariant unrepresentable, with **all `SandboxRun` construction routed through the widened `_construct_sandbox_run`** (additive — S3-02 contract preserved). Specifically:

1. **Copy-out** — `copy_out(container, *, globs: list[str], dest_root: Path) -> Path` using SDK-only primitives (`container.exec_run([list-form `find`])` for glob resolution + `container.get_archive(path)` for tar streaming). Two-layer tar-member safety: pure `_safe_resolve` policy + stdlib `tarfile.extract(..., filter="data")` belt-and-suspenders. Missing globs WARN, do not raise. `dest_root` exists after the call even when `globs == []` or every glob misses.
2. **Timeout / SIGKILL path** — `_wait_with_timeout(container, timeout, *, is_timeout=_is_wait_timeout)` wraps `container.wait(timeout=spec.time_budget_seconds)`. On `requests.exceptions.ReadTimeout` (or any `is_timeout(exc) == True` shape), calls `container.kill(signal="SIGKILL")`, then a **bounded** second `container.wait(timeout=_REAP_GRACE_SECONDS)`. The second wait failing → `SandboxBackendError("reap_failed", …)`. `_classify_wait_outcome` returns `TimedOut(exit_code=<from second wait>)`.
3. **OOM detection** — after the first wait returns normally, `container.reload()` + `container.attrs.get("State", {}).get("OOMKilled", False)`. `True` → `_classify_wait_outcome` returns `OomKilled(exit_code=<from wait>)`. Schema malformed (non-bool) → `SandboxBackendError("oom_inspect_malformed", …)`.
4. **`_construct_sandbox_run` widening (additive)** — three new keyword-only kwargs (`outcome: _WaitOutcome`, `copy_out_root: Path`, `image_pull_bytes: int`); pattern-matches `outcome` to stamp `(timed_out, killed_by_oom, exit_code)`. S3-02 call sites that don't pass `outcome` get the `Normal(exit_code=...)` default; their tests stay green.
5. **Six new `EVENT_*` `Final[str]` constants** following S1-01 / S3-03 `STARTED/COMPLETED/FAILED` verb convention; the S3-02 `EVENT_SANDBOX_DID_TIMEOUT_DEFERRED` is **removed** (and its test replaced).
6. **Cleanup ordering pinned** — `kill → bounded-wait → copy-out (best-effort) → remove`; 4-cell parametrized grid.

## Acceptance criteria

### A. Public surface + module purity (`copy_out.py`)

- [ ] **AC-API-1** New file `src/codegenie/sandbox/did/copy_out.py` exports `copy_out` and `_extract_tar_stream`, `_safe_resolve` (latter two are module-private with single leading underscore; `__all__ == ["copy_out"]`).
- [ ] **AC-API-2** `copy_out(container, *, globs: list[str], dest_root: Path) -> Path` — keyword-only kwargs; returns `dest_root` for caller-side composability.
- [ ] **AC-API-3** Module-level `Final` constants: `_MAX_GLOB_DEPTH: Final[int] = 10`, `_GLOB_RESOLVE_TIMEOUT_SECONDS: Final[int] = 30`.
- [ ] **AC-API-4** Module does NOT import `subprocess`; AST-walker test `tests/sandbox/did/test_copy_out_purity.py` asserts zero `subprocess` imports + zero `os.system` / `os.popen` / `eval` / `exec` / `__import__` calls + zero `["sh", "-c", …]`-shape list literals (matches the `forbidden-patterns` precommit hook).
- [ ] **AC-API-5** Module is not added to the subprocess chokepoint allowlist in `tests/schema/test_no_subprocess_outside_build_chokepoint.py` (it stays SDK-only).

### B. `_WaitOutcome` sum type + classifier

- [ ] **AC-OUTCOME-1** Internal sum type defined in `client.py` (or `_wait_outcome.py` sibling — implementer's choice; co-locate with `_construct_sandbox_run`):
  ```python
  from dataclasses import dataclass
  from typing import Final, TypeAlias

  @dataclass(frozen=True, slots=True)
  class _Normal: exit_code: int
  @dataclass(frozen=True, slots=True)
  class _TimedOut: exit_code: int = 137
  @dataclass(frozen=True, slots=True)
  class _OomKilled: exit_code: int = 137

  _WaitOutcome: TypeAlias = _Normal | _TimedOut | _OomKilled
  ```
- [ ] **AC-OUTCOME-2** `_classify_wait_outcome(*, wait_result: dict, oom_killed: bool, timed_out: bool) -> _WaitOutcome` is pure. Body is a single pattern decision: `if timed_out: return _TimedOut(exit_code=wait_result.get("StatusCode", 137)); elif oom_killed: return _OomKilled(exit_code=wait_result.get("StatusCode", 137)); else: return _Normal(exit_code=wait_result["StatusCode"])`.
- [ ] **AC-OUTCOME-3** Mutual-exclusion is enforced by the sum type — `_classify_wait_outcome` accepts a `timed_out=True, oom_killed=True` input and **MUST** raise `AssertionError("S1-02 AC-7d violated: timed_out and oom_killed both True")`. Unit test fixture exercises this branch.
- [ ] **AC-OUTCOME-4** Exhaustiveness assertion: `tests/sandbox/did/test_wait_classification.py::test_wait_outcome_variants` asserts `set(get_args(_WaitOutcome.__value__)) == {_Normal, _TimedOut, _OomKilled}` (or the `typing.get_origin` equivalent for the union); adding a new variant requires updating this test (loud, not silent).
- [ ] **AC-OUTCOME-5** Hypothesis property test in `test_client_copy_out_integration.py` draws from `_WaitOutcome` variants and asserts the constructed `SandboxRun` always satisfies `not (run.timed_out and run.killed_by_oom)` (S1-02 AC-7d).

### C. `_extract_tar_stream` pure helper + property test

- [ ] **AC-FCS-4** `_extract_tar_stream(stream: Iterator[bytes], dest_root: Path) -> list[Path]` is pure (input → file-system effect — pure in inputs, deterministic in side-effect; no SDK / no docker imports). Takes any iterator of bytes chunks; buffers to a `BytesIO` first; then `tarfile.open(fileobj=buf, mode="r:*")` (handles both uncompressed and gzipped).
- [ ] **AC-FCS-5** For each `member` in the tar, calls `_safe_resolve(member.name, dest_root)`. On `None` (escape attempt), skips + emits `EVENT_SANDBOX_DID_COPY_OUT_TAR_MEMBER_REJECTED` (warn). On a non-None `safe_path`, calls `tarfile.TarFile.extract(member, dest_root, filter="data")` (belt-and-suspenders per PEP 706).
- [ ] **AC-FCS-6** Returns the list of extracted paths (`safe_path` for each accepted member, in tar order). Docstring explicitly anchors the future Firecracker re-use: "`_extract_tar_stream` accepts an `Iterator[bytes]` — Firecracker's host-side `open(host_tar, 'rb')` chunks satisfy this contract without re-implementation."
- [ ] **AC-FCS-7** Hypothesis property test (`tests/sandbox/did/test_copy_out_helpers.py::test_extract_tar_stream_roundtrip`) — for any random tar of N entries with no traversal (generated by a hypothesis strategy), `len(_extract_tar_stream(...)) == N` AND each output file's bytes equal the input bytes. Three concrete fixtures alongside: empty tar (returns `[]`), single-file tar, multi-file-with-dirs tar.

### D. `_safe_resolve` pure helper + adversarial corpus

- [ ] **AC-SEC-1** `_safe_resolve(member_name: str, dest_root: Path) -> Path | None` is pure. Returns the **resolved** path if `member_name` lands strictly under `dest_root.resolve()`; returns `None` if it would escape (`..` traversal, absolute path, symlink to outside, NUL byte, Windows drive prefix on POSIX). Behavior parametrized — does NOT raise; the caller decides whether to log+skip or treat as fatal.
- [ ] **AC-SEC-2** Implementation: `candidate = (dest_root / member_name).resolve(strict=False); return candidate if dest_root.resolve() in candidate.parents or candidate == dest_root.resolve() else None`. NUL byte short-circuits to None before path math.
- [ ] **AC-SEC-3** Adversarial fixture corpus (5 fixtures in `tests/fixtures/sandbox/tar/`):
  - `traversal_dotdot.tar` — member `../../etc/passwd` → `_safe_resolve` returns None; `_extract_tar_stream` skips with `EVENT_SANDBOX_DID_COPY_OUT_TAR_MEMBER_REJECTED`.
  - `absolute_path.tar` — member `/etc/passwd` → None + skip.
  - `symlink_escape.tar` — symlink member pointing to `/etc/passwd` → stdlib filter rejects (`LinkOutsideDestinationError` caught locally, skipped + WARN).
  - `nul_byte.tar` — member `evil\x00.txt` → None + skip.
  - `deep_nested.tar` — member `a/b/c/d/e/f/leaf.txt` → accepted (no escape); extracted under `dest_root/a/b/c/d/e/f/leaf.txt`.
  Post-test invariant: every path in `dest_root.rglob("*")` satisfies `dest_root.resolve() in p.resolve().parents`.

### E. `_is_wait_timeout` pure classifier (hexagonal DI port — rule-of-four)

- [ ] **AC-DI-1** `_is_wait_timeout(exc: BaseException) -> bool` is pure; returns `isinstance(exc, requests.exceptions.ReadTimeout)`. Single source of truth — `_wait_with_timeout(container, timeout, *, is_timeout=_is_wait_timeout)` accepts it as keyword-only kwarg with production default.
- [ ] **AC-DI-2** Parametrized 3-row test matrix in `test_wait_classification.py`:
  | Exception | `_is_wait_timeout` |
  |---|---|
  | `requests.exceptions.ReadTimeout("budget")` | `True` |
  | `docker.errors.APIError("daemon error")` | `False` |
  | `requests.exceptions.ConnectionError("unreachable")` | `False` |
- [ ] **AC-DI-3** Tests inject `is_timeout=` directly (no `mock.patch`). Mock-patch-drift meta-test (`test_copy_out_purity.py::test_no_mock_patch_requests`) greps `tests/sandbox/did/` for `mock.patch("requests.exceptions` → must be zero.
- [ ] **AC-DI-4** If `docker-py` is pinned to 8.x+ in a future PR and the exception class changes, this classifier + its test fail together — never silently.

### F. `_wait_with_timeout` impure shell + reap grace

- [ ] **AC-WAIT-1** `_wait_with_timeout(container, timeout: int, *, is_timeout: Callable[[BaseException], bool] = _is_wait_timeout) -> tuple[dict, bool]` returns `(wait_result, timed_out_flag)`. On normal return: `wait_result, False`. On `is_timeout(exc) == True`: calls `container.kill(signal="SIGKILL")`, then `container.wait(timeout=_REAP_GRACE_SECONDS)`; returns `(wait_result, True)`. On the second wait raising any exception: raises `SandboxBackendError("reap_failed", details={"original": str(exc)})` (S3-03 closed-Literal pattern widened additively here).
- [ ] **AC-REAP-1** Module-level `_REAP_GRACE_SECONDS: Final[int] = 5`. Docstring: "If SIGKILL doesn't reap the container in 5s, the daemon is degraded; surface loudly rather than hang."
- [ ] **AC-REAP-2** Test `test_timeout.py::test_reap_grace_unbounded_hang_protection`: first wait raises ReadTimeout; second wait raises ReadTimeout; assert `SandboxBackendError("reap_failed", …)` raised; assert `container.kill` called exactly once.
- [ ] **AC-WAIT-2** Parametrized exception-class matrix test:
  | First-wait exception | Second-wait result | Expected |
  |---|---|---|
  | `ReadTimeout` | `{"StatusCode": 137}` | `(result, True)`; `kill` called once |
  | `ReadTimeout` | `ReadTimeout` raised | `SandboxBackendError("reap_failed", …)` |
  | `APIError("daemon")` | n/a | wrapped via `_wrap_api_error` (S3-02 helper) — not caught by `_is_wait_timeout` |
  | `ConnectionError` | n/a | wrapped via `_wrap_api_error` |
  | (none — normal return) | n/a | `(wait_result, False)`; `kill` NOT called |

### G. `copy_out` impure shell + glob mitigation

- [ ] **AC-GLOB-1** Glob resolution uses **list-form, no shell**: `container.exec_run(["find", "--", glob, "-maxdepth", str(_MAX_GLOB_DEPTH), "-print0"], demux=False)` for each glob.
- [ ] **AC-GLOB-2** Meta-test `test_copy_out_purity.py::test_no_shell_invocation`: AST-walks `copy_out.py` for any `Constant` node with value `"sh"` or `"-c"`; greps source for `"sh -c"`; asserts both zero. Forbidden-patterns precommit hook + import-linter cover the second line.
- [ ] **AC-GLOB-3** Adversarial glob fixture corpus (4 fixtures in `tests/fixtures/sandbox/globs/`):
  - `injection_semicolon` — `/work; rm -rf /` — `exec_run` is called with list-form `["find", "--", "/work; rm -rf /", ...]`; the shell metacharacters are passed as a single argument to `find` (which will fail to match anything); test asserts `exec_run` was called with the exact list-form, not str-form.
  - `injection_dollar` — `/work/$(cat /etc/passwd)` — same shape; list-form delivery.
  - `injection_backtick` — `/work/` + backtick `id` backtick — same.
  - `injection_newline` — `/work\nrm -rf /` — same.
  All four assert `EVENT_SANDBOX_DID_COPY_OUT_GLOB_MISS` is emitted (find finds nothing), and `dest_root` remains an empty directory.
- [ ] **AC-GLOB-4** Per-`exec_run` timeout: `_GLOB_RESOLVE_TIMEOUT_SECONDS: Final[int] = 30`. If `find` doesn't return in 30s, `SandboxBackendError("copy_out_glob_resolve_timeout", …)`.
- [ ] **AC-COPY-1** Empty `globs == []` short-circuits: no `exec_run` calls, no `get_archive` calls; `dest_root.mkdir(parents=True, exist_ok=True)`; returns `dest_root`. Test asserts `container.exec_run.call_count == 0` AND `container.get_archive.call_count == 0`.
- [ ] **AC-COPY-2** For each resolved path, `bits, _stat = container.get_archive(match)`; `_extract_tar_stream(bits, dest_root)` extracts.
- [ ] **AC-COPY-3** `get_archive` raising `docker.errors.NotFound` → log `EVENT_SANDBOX_DID_COPY_OUT_FAILED(reason="not_found", path=match)`; skip; continue with next match. (Other `APIError` → `_wrap_api_error` → propagated.)
- [ ] **AC-COPY-4** Idempotency: calling `copy_out` twice with the same `dest_root` produces byte-equal results (second call overwrites; no append, no exception). Test fixture exercises this.

### H. `_construct_sandbox_run` additive widening (S3-02 contract preserved)

- [ ] **AC-CTOR-1** Signature widens additively. New keyword-only kwargs with defaults that preserve S3-02 behavior:
  ```python
  def _construct_sandbox_run(
      *, run_id: RunId, spec: SandboxSpec, started_at: datetime, ended_at: datetime,
      logs_dir: Path,
      outcome: _WaitOutcome = _Normal(exit_code=0),       # NEW
      copy_out_root: Path | None = None,                  # NEW; default = logs_dir.parent / "copy_out" / str(run_id)
      image_pull_bytes: int = 0,                          # NEW; S3-04 still stubs this to 0
  ) -> SandboxRun: ...
  ```
- [ ] **AC-CTOR-2** Body pattern-matches `outcome`:
  ```python
  match outcome:
      case _Normal(exit_code=ec):       timed_out, killed_by_oom = False, False
      case _TimedOut(exit_code=ec):     timed_out, killed_by_oom = True,  False
      case _OomKilled(exit_code=ec):    timed_out, killed_by_oom = False, True
  ```
  `mypy --strict` exhaustiveness via `_: assert_never(outcome)` at the end (Python `typing.assert_never`).
- [ ] **AC-CTOR-3** `gate_isolation_class=_GATE_ISOLATION_CLASS` and `backend=_BACKEND_NAME` are stamped unchanged (S3-02 AC-RUN-FIELDS-3 / -4 contract).
- [ ] **AC-CTOR-4** Meta-test `test_copy_out_purity.py::test_single_sandbox_run_call_site`: AST-walks `src/codegenie/sandbox/did/client.py` for `Call` nodes with `func.id == "SandboxRun"`; asserts exactly 1 occurrence (the one inside `_construct_sandbox_run`). All other call sites go through the helper.
- [ ] **AC-CTOR-5** S3-02 call sites that omit the new kwargs continue to work — their tests stay green without edits. The S3-02 `test_client_core.py::test_construct_sandbox_run_minimal` is **not edited**.

### I. `client.py` execute-flow edit (timeout + OOM + copy-out + cleanup)

- [ ] **AC-EXEC-1** `execute()` body, in order: `_validate_spec_supported(spec)` (preserved), `run_id`, `logs_dir`, `kwargs = _build_container_kwargs(spec)`, `container = self._client.containers.create(**kwargs)`, `started_at`, `container.start()`, log demux, `wait_result, did_timeout = _wait_with_timeout(container, spec.time_budget_seconds)`, `ended_at`, `container.reload()`, `oom = container.attrs.get("State", {}).get("OOMKilled", False)` (type-checked — bool only; else `SandboxBackendError("oom_inspect_malformed", …)`), `outcome = _classify_wait_outcome(wait_result=wait_result, oom_killed=oom, timed_out=did_timeout)`, `copy_out_root = logs_dir.parent / "copy_out" / str(run_id)`, **`copy_out(container, globs=spec.copy_out, dest_root=copy_out_root)`** (best-effort — see AC-COPY-EXIT-1..-3), construct via `_construct_sandbox_run(..., outcome=outcome, copy_out_root=copy_out_root)`, **then** `try/finally container.remove(force=True)`.
- [ ] **AC-EXEC-2** `wait_result.get("Error")` is checked before classification (S3-02 AC-WAIT-1 preserved); on non-None Error → `_wrap_api_error("wait_failed", …)`.
- [ ] **AC-EXEC-3** `container.reload()` raising `APIError` → `_wrap_api_error` (S3-02 helper); propagated.
- [ ] **AC-EXEC-4** `container.attrs.get("State", {}).get("OOMKilled", False)` — if the value is present but not bool, `SandboxBackendError("oom_inspect_malformed", details={"value": repr(v)})`.

### J. `copy_out_root` discipline (load-bearing path) on every exit path

- [ ] **AC-PATH-1** `copy_out_root` **always** equals `logs_dir.parent / "copy_out" / str(run_id)` — pinned by S3-02 HARDENED AC-RUN-FIELDS-14 and AC-LOGS-3; Phase 11 evidence bundle keys on this path.
- [ ] **AC-PATH-2** Module-level fence test `test_copy_out_purity.py::test_copy_out_root_path_pin` AST-greps `client.py` for the literal expression `logs_dir / "copy_out"` (without `.parent`) → must return zero (would be the wrong path).
- [ ] **AC-PATH-3** Property test: for any random `run_id` + `logs_dir`, `_construct_sandbox_run` produces `run.copy_out_root == run.logs_dir.parent / "copy_out" / str(run.run_id)`.
- [ ] **AC-COPY-EXIT-1** On the **normal** exit path: `copy_out` is called; `copy_out_root` exists and contains matched files (or is empty if no globs match).
- [ ] **AC-COPY-EXIT-2** On the **timeout** exit path: `copy_out` is called best-effort (the container has been SIGKILL'd; `get_archive` may fail); failures are caught and logged at WARN (`EVENT_SANDBOX_DID_COPY_OUT_FAILED(reason="container_killed", …)`); `copy_out_root` still exists (created by the first `_extract_tar_stream` call or by `copy_out` itself).
- [ ] **AC-COPY-EXIT-3** On the **OOM** exit path: same as timeout — best-effort copy-out, dir exists, failures WARN.

### K. Cleanup ordering + 4-cell parametrized cleanup grid

- [ ] **AC-ORDER-1** Sequence pinned in `execute()`:
  ```
  try:
      container.start(); log_demux(); wait_result, did_timeout = _wait_with_timeout(...)
      reload + oom_classify; outcome = _classify_wait_outcome(...)
      copy_out(container, globs=spec.copy_out, dest_root=copy_out_root)  # best-effort on timeout/OOM
      run = _construct_sandbox_run(..., outcome=outcome, copy_out_root=copy_out_root)
  finally:
      container.remove(force=True)  # absorbs any exception; never raises
  ```
- [ ] **AC-ORDER-2** 4-cell parametrized test (`test_client_copy_out_integration.py::test_cleanup_grid`):
  | exit_path | workload_raises | expected_kill_calls | expected_remove_calls | expected_copy_out_attempted |
  |---|---|---|---|---|
  | normal | False | 0 | 1 | True |
  | timeout | False | 1 | 1 | True (best-effort) |
  | OOM | False | 0 | 1 | True (best-effort) |
  | normal | True (e.g. `_wrap_api_error` raises inside `_construct_sandbox_run`) | 0 | 1 | True (already happened pre-raise) |

### L. Closed Literal `reason` widening on `SandboxBackendError`

- [ ] **AC-ERR-1** `SandboxBackendError.reason` Literal widened additively. S3-03 HARDENED's 11 members are preserved; 4 new members appended:
  - `"reap_failed"` (from AC-WAIT-1)
  - `"oom_inspect_malformed"` (from AC-EXEC-4)
  - `"copy_out_archive_failed"` (general `get_archive` non-NotFound APIError)
  - `"copy_out_glob_resolve_timeout"` (from AC-GLOB-4)
  Total: 15 members.
- [ ] **AC-ERR-2** Source-pin meta-test `test_copy_out_purity.py::test_error_reason_union_widened`: `typing.get_args(SandboxBackendError.model_fields["reason"].annotation)` includes all 15 members; adding a new error reason without updating this test fails the build.
- [ ] **AC-ERR-3** Note: `tar_member_outside_dest` is NOT raised as an error — it's a WARN-level event because the policy is skip-and-continue (AC-FCS-5 + AC-SEC-3).

### M. S3-02 AC widening enumeration

- [ ] **AC-WIDEN-1** S3-02 AC-SPEC-DEFER-4 (`spec.copy_out != []` → `NotImplementedError("sandbox.did: spec.copy_out deferred to S3-04")`) is **removed** from `_validate_spec_supported`. The S3-02 test `test_spec_defer_copy_out_raises` is replaced by `test_copy_out.py::test_copy_out_with_globs_extracts` (the natural successor; not silent deletion).
- [ ] **AC-WIDEN-2** S3-02 AC-SPEC-DEFER-6 (`spec.time_budget_seconds != DEFAULT_TIME_BUDGET` → `EVENT_SANDBOX_DID_TIMEOUT_DEFERRED` WARNING) is **removed**. `container.wait()` IS now given `timeout=spec.time_budget_seconds`.
- [ ] **AC-WIDEN-3** The S3-02 test `test_client_core.py::test_spec_defer_time_budget_warns` is **replaced** (not deleted) by `test_timeout.py::test_wait_with_timeout_triggers_sigkill`. Replacement is a deliberate, named action — the PR diff shows the replacement, Rule 12 (fail loud) is satisfied.
- [ ] **AC-WIDEN-4** `EVENT_SANDBOX_DID_TIMEOUT_DEFERRED: Final[str]` constant is **removed** from `events.py` (or `logging.py`); meta-test `test_copy_out_purity.py::test_no_dormant_event_constants` greps for the removed constant name → must return zero hits across `src/codegenie/sandbox/`.
- [ ] **AC-WIDEN-5** S3-02 AC-RUN-FIELDS-15 (`timed_out: bool is False` — stub) and AC-RUN-FIELDS-16 (`killed_by_oom: bool is False` — stub) are widened: `_construct_sandbox_run` now stamps them from the `_WaitOutcome` argument. S3-02 happy-path test that asserts `run.timed_out is False, run.killed_by_oom is False` continues to pass (default `outcome=_Normal(...)`).

### N. Module purity (AST walker for `copy_out.py` — rule-of-four FCS)

- [ ] **AC-PURE-1** `tests/sandbox/did/test_copy_out_purity.py::test_module_purity` AST-walks `copy_out.py` and asserts:
  - No `import subprocess`, `import os.system`, `from os import system`, `from os import popen`.
  - No `Call` nodes with `func.id ∈ {"eval", "exec", "compile"}` or `func.attr == "popen"`.
  - No `Constant(value="sh")` immediately followed by `Constant(value="-c")` in any list literal.
  - No `Import(names=[alias("requests")])` (must use the SDK's exception passthrough, not direct requests imports).
- [ ] **AC-PURE-2** Same walker confirms `_extract_tar_stream`, `_safe_resolve` are at module level (not nested in `copy_out`).
- [ ] **AC-PURE-3** Pure-helper unit tests in `test_copy_out_helpers.py` import only `tarfile`, `pathlib`, `io`, `pytest`, `hypothesis` — no `docker`, no `requests`.

### O. Event-name discipline (append-only to S1-01 + S3-02 + S3-03 table)

- [ ] **AC-EVT-1** Six new `EVENT_*` `Final[str]` constants appended to `src/codegenie/sandbox/did/events.py` (or `logging.py`):
  - `EVENT_SANDBOX_DID_COPY_OUT_STARTED = "sandbox.did.copy_out.started"`
  - `EVENT_SANDBOX_DID_COPY_OUT_COMPLETED = "sandbox.did.copy_out.completed"`
  - `EVENT_SANDBOX_DID_COPY_OUT_FAILED = "sandbox.did.copy_out.failed"`
  - `EVENT_SANDBOX_DID_COPY_OUT_GLOB_MISS = "sandbox.did.copy_out.glob_miss"`
  - `EVENT_SANDBOX_DID_COPY_OUT_TAR_MEMBER_REJECTED = "sandbox.did.copy_out.tar_member_rejected"`
  - `EVENT_SANDBOX_DID_TIMEOUT_SIGKILL = "sandbox.did.timeout.sigkill"`
  - `EVENT_SANDBOX_DID_OOM_KILLED = "sandbox.did.oom_killed"`
- [ ] **AC-EVT-2** Verb-namespace regex `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?$` (allows the third segment for the verb suffix per S3-03 HARDENED). Test parametrizes over all new constants.
- [ ] **AC-EVT-3** Removed constant: `EVENT_SANDBOX_DID_TIMEOUT_DEFERRED` (per AC-WIDEN-4).
- [ ] **AC-EVT-4** Per-event field schema parametrized in `test_client_copy_out_integration.py::test_structlog_event_fields`:
  | Event | Required fields |
  |---|---|
  | `COPY_OUT_STARTED` | `run_id: RunId`, `glob_count: int` |
  | `COPY_OUT_COMPLETED` | `run_id: RunId`, `duration_ms: int`, `extracted_count: int` |
  | `COPY_OUT_FAILED` | `run_id: RunId`, `reason: str`, `path: str` |
  | `COPY_OUT_GLOB_MISS` | `run_id: RunId`, `glob: str` |
  | `COPY_OUT_TAR_MEMBER_REJECTED` | `run_id: RunId`, `member_name: str` |
  | `TIMEOUT_SIGKILL` | `run_id: RunId`, `time_budget_seconds: int` |
  | `OOM_KILLED` | `run_id: RunId`, `memory_limit_mib: int`, `exit_code: int` |
- [ ] **AC-EVT-5** `run_id` extra-field is typed `RunId` (NOT `str(run_id)`); meta-test greps for `run_id=str(` in new code → must be zero.

### P. Golden file `docker_cp_args_stage6_validate.json` schema + fixtures

- [ ] **AC-GOLD-1** Path: `tests/golden/docker_cp_args_stage6_validate.json`. Schema:
  ```json
  {
    "exec_run_calls": [["find", "--", "<glob>", "-maxdepth", "10", "-print0"], ...],
    "get_archive_calls": ["<resolved_path_1>", "<resolved_path_2>", ...]
  }
  ```
- [ ] **AC-GOLD-2** Generated from a `tests/sandbox/did/test_copy_out.py::test_argv_golden_stage6_validate` fixture that exercises the stage6 spec's `copy_out` list against a fake container (records `exec_run.call_args_list` + `get_archive.call_args_list`). `sort_keys=True` for byte-stability.
- [ ] **AC-GOLD-3** Mutation: an implementation that uses `exec_run(["sh", "-c", "ls -1 ..."])` produces a different golden → test fails loudly.

### Q. Tests stay green + coverage floors + dependencies

- [ ] **AC-COV-1** `coverage` on `src/codegenie/sandbox/did/copy_out.py` ≥ 95% line, ≥ 90% branch.
- [ ] **AC-COV-2** `coverage` on the `src/codegenie/sandbox/did/client.py` delta (lines added/modified by this story) ≥ 90% line.
- [ ] **AC-COV-3** TDD plan's red tests exist, are committed, and are green after implementation.
- [ ] **AC-COV-4** `ruff check`, `ruff format --check`, `mypy --strict`, `pytest -q` (full suite) all pass.
- [ ] **AC-DEP-1** `pyproject.toml` unchanged (uses stdlib `tarfile`, `pathlib`, `dataclasses`, `typing`, `io`; existing `docker` SDK; existing `requests` already a transitive of `docker`).
- [ ] **AC-FENCE-1** `tests/schema/test_no_subprocess_outside_build_chokepoint.py` allowlist **unchanged** — `copy_out.py` is NOT added. The fence stays at exactly 3 chokepoints (`did/build.py`, `did/network_policy.py`, `firecracker/client.py`).

## Implementation outline

Ordered for red-first TDD; each step has at least one failing test before the implementation lands.

1. **`events.py` (or `logging.py`) widening** — append six `EVENT_*` constants; **remove** `EVENT_SANDBOX_DID_TIMEOUT_DEFERRED`; namespace regex test fires red, then green.
2. **`errors.py` widening** — append 4 new members to `SandboxBackendError.reason` Literal (15 total); `test_error_reason_union_widened` fires red, then green.
3. **`_WaitOutcome` sum type** — add the three frozen dataclasses + `_WaitOutcome` TypeAlias to `client.py` (or `_wait_outcome.py` if implementer prefers; co-locate with `_construct_sandbox_run`).
4. **Pure helpers in this order** (each independently unit-testable):
   - `_safe_resolve(member_name, dest_root) -> Path | None` (5-fixture adversarial corpus)
   - `_extract_tar_stream(stream, dest_root) -> list[Path]` (hypothesis property + 3 concrete fixtures)
   - `_is_wait_timeout(exc) -> bool` (3-row matrix)
   - `_classify_wait_outcome(*, wait_result, oom_killed, timed_out) -> _WaitOutcome` (4-row matrix + the AC-OUTCOME-3 invariant-violation case)
5. **`copy_out.py` shell** — wires the pure helpers + `container.exec_run([find …])` + `container.get_archive()`; structured events; idempotency.
6. **`client.py::_wait_with_timeout` impure shell** — wraps `container.wait(timeout=spec.time_budget_seconds)` + SIGKILL + bounded second wait with `_REAP_GRACE_SECONDS`.
7. **`_construct_sandbox_run` additive widening** — three new keyword-only kwargs; pattern-match `outcome`; defaults preserve S3-02 call-site signatures; meta-test `test_single_sandbox_run_call_site`.
8. **`execute()` flow edit** — pinned sequence per AC-ORDER-1; 4-cell cleanup grid green.
9. **Removals**: `EVENT_SANDBOX_DID_TIMEOUT_DEFERRED` from `events.py`; the S3-02 `_validate_spec_supported` raise for `copy_out != []` and the deferred-warning-emit for non-default `time_budget_seconds`; the S3-02 `test_spec_defer_copy_out_raises` and `test_spec_defer_time_budget_warns` tests (replaced, not silent-deleted).
10. **Golden file generation** — `tests/sandbox/did/test_copy_out.py::test_argv_golden_stage6_validate` records the call-list against a fake container; commits `tests/golden/docker_cp_args_stage6_validate.json`.
11. **Refactor pass (genuine refactoring only — not the security/correctness guards)** — docstrings citing edge cases #3 and #4 + the cross-story forward-pointers; structlog `duration_ms` measured between START + final wait via a single `time.monotonic()` reading at each end.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file paths:
- `tests/sandbox/did/test_copy_out_purity.py` — module-purity AST walker + meta-tests.
- `tests/sandbox/did/test_copy_out_helpers.py` — `_safe_resolve` parametrized + adversarial, `_extract_tar_stream` hypothesis property + 3 fixtures.
- `tests/sandbox/did/test_wait_classification.py` — `_is_wait_timeout` 3-row, `_classify_wait_outcome` 4-row + exhaustiveness.
- `tests/sandbox/did/test_copy_out.py` — core 5-fixture parametrized + adversarial glob 4-fixture + idempotency + golden.
- `tests/sandbox/did/test_timeout.py` — exception-class matrix + reap-grace + cleanup-order.
- `tests/sandbox/did/test_oom.py` — `OOMKilled=True/False/missing-key/malformed`; reload failure.
- `tests/sandbox/did/test_client_copy_out_integration.py` — 4-cell cleanup grid + structlog event-fields parametrized + hypothesis property for the cross-field invariant.

Representative red tests:

```python
# tests/sandbox/did/test_copy_out_helpers.py
import io
import tarfile
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from codegenie.sandbox.did.copy_out import _extract_tar_stream, _safe_resolve

@pytest.mark.parametrize("member_name,expected_none", [
    ("../../etc/passwd", True),           # traversal
    ("/etc/passwd",      True),           # absolute
    ("evil\x00.txt",     True),           # NUL byte
    ("a/b/c/leaf.txt",   False),          # OK
    ("./leaf.txt",       False),          # OK after normalize
])
def test_safe_resolve_rejects_escape(tmp_path, member_name, expected_none):
    """Phase 4 LLM-influenced workloads MUST NOT write outside dest_root.
    Catches a regression where `_safe_resolve` accepts `..` segments after
    Path normalization removes them."""
    result = _safe_resolve(member_name, tmp_path)
    assert (result is None) == expected_none

def _make_tar(entries: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, content in entries:
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
    return buf.getvalue()

@given(st.lists(st.tuples(
    st.text(alphabet="abcdef/", min_size=1, max_size=20).filter(lambda s: ".." not in s and not s.startswith("/")),
    st.binary(min_size=0, max_size=512),
), min_size=0, max_size=8, unique_by=lambda t: t[0]))
def test_extract_tar_stream_roundtrip(tmp_path, entries):
    """For any traversal-free tar, extract count == input count and bytes preserved.
    Mutation: an impl that skips zero-byte entries would fail when bytes==b''."""
    tar_bytes = _make_tar([(n, c) for n, c in entries])
    extracted = _extract_tar_stream(iter([tar_bytes]), tmp_path)
    assert len(extracted) == len(entries)
    for name, content in entries:
        assert (tmp_path / name).read_bytes() == content
```

```python
# tests/sandbox/did/test_wait_classification.py
import pytest
import requests.exceptions
import docker.errors

from codegenie.sandbox.did.client import (
    _is_wait_timeout, _classify_wait_outcome, _Normal, _TimedOut, _OomKilled,
)

@pytest.mark.parametrize("exc,expected", [
    (requests.exceptions.ReadTimeout("budget"), True),
    (docker.errors.APIError("daemon error"),    False),
    (requests.exceptions.ConnectionError("x"),  False),
])
def test_is_wait_timeout_classifies_pinned_exceptions(exc, expected):
    """If docker-py is ever pinned to 8.x+ and exception class changes,
    this test fails together with the classifier — never silently."""
    assert _is_wait_timeout(exc) is expected

@pytest.mark.parametrize("wait_result,oom,timed_out,expected_cls,expected_ec", [
    ({"StatusCode": 0},   False, False, _Normal,   0),
    ({"StatusCode": 137}, False, True,  _TimedOut, 137),
    ({"StatusCode": 137}, True,  False, _OomKilled, 137),
])
def test_classify_wait_outcome_three_canonical_paths(wait_result, oom, timed_out, expected_cls, expected_ec):
    out = _classify_wait_outcome(wait_result=wait_result, oom_killed=oom, timed_out=timed_out)
    assert isinstance(out, expected_cls)
    assert out.exit_code == expected_ec

def test_classify_wait_outcome_rejects_mutual_exclusion_violation():
    """S1-02 AC-7d invariant `not (timed_out and killed_by_oom)`.
    If a caller bypasses _classify and constructs an illegal pair, fail loud."""
    with pytest.raises(AssertionError, match="S1-02 AC-7d violated"):
        _classify_wait_outcome(wait_result={"StatusCode": 137}, oom_killed=True, timed_out=True)
```

```python
# tests/sandbox/did/test_timeout.py
from unittest.mock import MagicMock
import pytest
import requests.exceptions

from codegenie.sandbox.errors import SandboxBackendError
from codegenie.sandbox.did.client import DockerInDockerClient, _REAP_GRACE_SECONDS

def test_wait_timeout_triggers_sigkill_and_sets_timed_out(monkeypatch, tmp_path, allowlist, spec_short_budget):
    """time_budget_seconds → wait() raises ReadTimeout → kill() once →
    bounded second wait returns → SandboxRun.timed_out=True, killed_by_oom=False, exit=137.
    Catches regression of the SIGKILL-then-second-wait sequence."""
    fake = MagicMock(); fake.id = "x"
    fake.wait.side_effect = [requests.exceptions.ReadTimeout("budget"), {"StatusCode": 137}]
    fake.logs.return_value = iter([])
    fake.attrs = {"State": {"OOMKilled": False}}
    fake_docker = MagicMock(); fake_docker.containers.create.return_value = fake
    monkeypatch.setattr("docker.from_env", lambda: fake_docker)
    monkeypatch.chdir(tmp_path)
    run = DockerInDockerClient(allowlist=allowlist).execute(spec_short_budget)
    assert run.timed_out is True
    assert run.killed_by_oom is False
    assert run.exit_code == 137
    fake.kill.assert_called_once_with(signal="SIGKILL")
    # Second wait used the bounded reap grace, NOT the original budget
    assert fake.wait.call_args_list[1].kwargs.get("timeout") == _REAP_GRACE_SECONDS

def test_reap_grace_unbounded_hang_protection(monkeypatch, tmp_path, allowlist, spec_short_budget):
    """If SIGKILL doesn't reap the container in 5s, raise reap_failed — never hang.
    Without _REAP_GRACE_SECONDS, this test would hang indefinitely."""
    fake = MagicMock(); fake.id = "x"
    fake.wait.side_effect = [
        requests.exceptions.ReadTimeout("budget"),
        requests.exceptions.ReadTimeout("reap also timed out"),
    ]
    fake.logs.return_value = iter([])
    fake_docker = MagicMock(); fake_docker.containers.create.return_value = fake
    monkeypatch.setattr("docker.from_env", lambda: fake_docker)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SandboxBackendError) as ei:
        DockerInDockerClient(allowlist=allowlist).execute(spec_short_budget)
    assert ei.value.reason == "reap_failed"
    fake.kill.assert_called_once_with(signal="SIGKILL")
```

```python
# tests/sandbox/did/test_oom.py — including the malformed-attr fence
import pytest
from unittest.mock import MagicMock

from codegenie.sandbox.errors import SandboxBackendError
from codegenie.sandbox.did.client import DockerInDockerClient

@pytest.mark.parametrize("state_attrs,expected_oom,expected_err", [
    ({"State": {"OOMKilled": True}},  True,  None),
    ({"State": {"OOMKilled": False}}, False, None),
    ({"State": {}},                   False, None),                  # missing key tolerated → False
    ({},                              False, None),                  # missing State tolerated → False
    ({"State": {"OOMKilled": "yes"}}, None,  "oom_inspect_malformed"),  # non-bool fails LOUD
])
def test_oom_inspect_branches(monkeypatch, tmp_path, allowlist, tiny_spec,
                              state_attrs, expected_oom, expected_err):
    fake = MagicMock()
    fake.wait.return_value = {"StatusCode": 137 if expected_oom else 0}
    fake.logs.return_value = iter([])
    fake.attrs = state_attrs
    fake_docker = MagicMock(); fake_docker.containers.create.return_value = fake
    monkeypatch.setattr("docker.from_env", lambda: fake_docker)
    monkeypatch.chdir(tmp_path)
    if expected_err:
        with pytest.raises(SandboxBackendError) as ei:
            DockerInDockerClient(allowlist=allowlist).execute(tiny_spec)
        assert ei.value.reason == expected_err
    else:
        run = DockerInDockerClient(allowlist=allowlist).execute(tiny_spec)
        assert run.killed_by_oom is expected_oom
        assert run.timed_out is False
```

```python
# tests/sandbox/did/test_copy_out.py — empty-list short-circuit + adversarial glob
from unittest.mock import MagicMock
from codegenie.sandbox.did.copy_out import copy_out

def test_empty_globs_short_circuits_no_exec_no_get_archive(tmp_path):
    """copy_out_root MUST exist after the call even with no globs;
    `find` / `get_archive` MUST NOT be invoked (cost + cleanliness)."""
    container = MagicMock()
    dest = tmp_path / "copy_out"
    result = copy_out(container, globs=[], dest_root=dest)
    assert result == dest
    assert dest.is_dir()
    assert list(dest.iterdir()) == []
    assert container.exec_run.call_count == 0
    assert container.get_archive.call_count == 0

@pytest.mark.parametrize("malicious_glob", [
    "/work; rm -rf /",
    "/work/$(cat /etc/passwd)",
    "/work/`id`",
    "/work\nrm -rf /",
])
def test_glob_resolution_uses_list_form_no_shell(tmp_path, malicious_glob):
    """Phase 4 LLM-influenced gate catalog MUST NOT reach `sh -c`.
    A regression to `["sh","-c",f"ls -1 {glob}"]` would let this glob escape."""
    container = MagicMock()
    container.exec_run.return_value = MagicMock(output=b"", exit_code=1)
    dest = tmp_path / "copy_out"
    copy_out(container, globs=[malicious_glob], dest_root=dest)
    # The malicious string is passed as ONE argument to `find`, not interpreted by a shell.
    args, _ = container.exec_run.call_args
    argv = args[0]
    assert argv[0] == "find"
    assert "sh" not in argv
    assert "-c" not in argv
    assert malicious_glob in argv
```

```python
# tests/sandbox/did/test_client_copy_out_integration.py — cleanup grid + cross-field property
import pytest
from hypothesis import given, strategies as st

@pytest.mark.parametrize("exit_path,workload_raises,expected_kill,expected_remove,expected_copy", [
    ("normal",  False, 0, 1, True),
    ("timeout", False, 1, 1, True),  # best-effort
    ("oom",     False, 0, 1, True),  # best-effort
    ("normal",  True,  0, 1, True),  # exception still cleans up
])
def test_cleanup_grid(monkeypatch, tmp_path, allowlist, spec_with_globs,
                      exit_path, workload_raises, expected_kill, expected_remove, expected_copy):
    # ... wire fakes per exit_path ...
    # assert fake.kill.call_count == expected_kill
    # assert fake.remove.call_count == expected_remove
    # assert (fake.get_archive.call_count > 0) == expected_copy
    ...

@given(st.sampled_from(["normal", "timeout", "oom"]))
def test_sandbox_run_satisfies_mutual_exclusion_invariant(monkeypatch, tmp_path, allowlist, tiny_spec, exit_path):
    """S1-02 AC-7d: not (timed_out and killed_by_oom). Hypothesis sweeps the
    three exit paths; any construction path that breaks the invariant is caught."""
    # ... build fakes per exit_path, call execute, assert ...
    # assert not (run.timed_out and run.killed_by_oom)
    ...
```

### Green — make it pass

- Implement pure helpers in dependency order (steps 4 above).
- Implement `copy_out.py` shell (step 5).
- Implement `_wait_with_timeout` + widen `_construct_sandbox_run` + edit `execute()` per AC-ORDER-1 (steps 6–8).
- Remove `EVENT_SANDBOX_DID_TIMEOUT_DEFERRED` + the two S3-02 deferred tests; replace with the natural successors (step 9).
- Generate `tests/golden/docker_cp_args_stage6_validate.json` from the fixture (step 10).

### Refactor — clean up

- Docstrings citing edge cases #3 and #4 + cross-story forward-pointers (S3-05 timeouts, S6-01 Firecracker `_extract_tar_stream` re-use, Phase 11 evidence-bundle path-pin).
- structlog `duration_ms` measured via a single `time.monotonic()` at start + end (cheaper than `(ended_at - started_at).total_seconds() * 1000` arithmetic when called per-event).
- Module-level docstring on `copy_out.py` documenting the no-shell glob policy + two-layer tar safety + the SDK-only chokepoint discipline.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/did/copy_out.py` | New — SDK tar-stream extractor + `find`-based glob resolver + `_safe_resolve` + `_extract_tar_stream`. |
| `src/codegenie/sandbox/did/client.py` | Edit — `_WaitOutcome` sum type (or sibling module), `_is_wait_timeout`, `_classify_wait_outcome`, `_wait_with_timeout`, widened `_construct_sandbox_run`, `execute()` flow per AC-ORDER-1; remove S3-02 `AC-SPEC-DEFER-4` raise + `AC-SPEC-DEFER-6` warning emit. |
| `src/codegenie/sandbox/did/events.py` (or `logging.py`) | Edit — append 6 new `EVENT_*` constants; **remove** `EVENT_SANDBOX_DID_TIMEOUT_DEFERRED`. |
| `src/codegenie/sandbox/errors.py` | Edit — widen `SandboxBackendError.reason` Literal additively from 11 to 15 members. |
| `tests/sandbox/did/test_copy_out_purity.py` | New — module-purity AST walker + meta-tests (`no_shell_invocation`, `single_sandbox_run_call_site`, `copy_out_root_path_pin`, `no_dormant_event_constants`, `no_mock_patch_requests`, `error_reason_union_widened`). |
| `tests/sandbox/did/test_copy_out_helpers.py` | New — `_safe_resolve` parametrized + 5-fixture adversarial; `_extract_tar_stream` hypothesis property + 3 concrete fixtures. |
| `tests/sandbox/did/test_wait_classification.py` | New — `_is_wait_timeout` 3-row matrix; `_classify_wait_outcome` 4-row matrix + exhaustiveness + AC-OUTCOME-3 invariant-violation. |
| `tests/sandbox/did/test_copy_out.py` | New — empty-list short-circuit; multi-glob; adversarial-glob 4-fixture; idempotency; golden-file generation. |
| `tests/sandbox/did/test_timeout.py` | New — exception-class matrix; reap-grace; second-wait-uses-`_REAP_GRACE_SECONDS`. |
| `tests/sandbox/did/test_oom.py` | New — 5-row OOMKilled branches; reload failure path. |
| `tests/sandbox/did/test_client_copy_out_integration.py` | New — 4-cell cleanup grid; structlog event-fields parametrized; cross-field-invariant hypothesis property. |
| `tests/sandbox/did/test_client_core.py` (from S3-02) | Edit — **remove** `test_spec_defer_copy_out_raises` + `test_spec_defer_time_budget_warns` (replaced, named in PR diff). |
| `tests/golden/docker_cp_args_stage6_validate.json` | New — `{exec_run_calls, get_archive_calls}` schema; sort_keys=True. |
| `tests/fixtures/sandbox/tar/{traversal_dotdot,absolute_path,symlink_escape,nul_byte,deep_nested}.tar` | New — 5 adversarial tar fixtures. |
| `tests/fixtures/sandbox/globs/{injection_semicolon,injection_dollar,injection_backtick,injection_newline}.txt` | New — 4 adversarial glob fixtures (text files holding the malicious glob strings for parametrize-from-file pattern). |
| `tests/schema/test_no_subprocess_outside_build_chokepoint.py` | **Unchanged** — `copy_out.py` is NOT added to the allowlist; AC-FENCE-1 asserts the allowlist file's hash. |

## Out of scope

- **`retry_policy.timeout_retryable` semantics** — `TestSignal(passed=False, details={"timed_out": True})` + the opt-in retryable behavior is wired in `GateRunner` Step 5, not here.
- **Live Docker daemon integration** — S3-07 (`tests/integration/sandbox/test_did_hello_node.py`, `test_did_oom.py`, `test_did_timeout.py`). This story's tests are pure unit + golden + adversarial against fakes.
- **`image_pull_bytes` population** — S3-04 leaves at `0` (S3-02 stub preserved); honest deferral. A future story (likely a Phase-13 cost work item) will parse the `pull` event stream to populate it.
- **`enable_trace` / `trace_path`** — S4-03 owns the strace-in-VM collector. S3-04 does not populate `trace_path`.
- **Firecracker copy-out** — S6-01 ships `sandbox/firecracker/copy_out.py` against a host-side `copy_out.tar`. `_extract_tar_stream` is the shared pure helper (signature `Iterator[bytes] -> list[Path]`); Firecracker passes `iter(open(host_tar, 'rb').read1, b'')`.
- **`CopyOutExtractor` Protocol** — rule-of-three not reached (only DinD here; S6-01 is the second known consumer). Promote when a third backend lands.
- **`_TarMember` sum type (Regular | Directory | Symlink | Hardlink | Skip)** — YAGNI for current copy-out semantics; promote when symlink preservation matters (Phase 13+ cost-attribution).
- **`GlobPattern = NewType("GlobPattern", str)`** — one validation site (`SandboxSpec.copy_out: list[str]`); promote at second consumer.
- **`pyproject.toml`** — no changes (AC-DEP-1).
- **Multi-phase YAML collapse (`stage6_validate.yaml` per-phase timeout sums)** — S3-05 owns the per-phase budget aggregation; this story owns the per-`execute()` SIGKILL only.
- **macOS-vs-Linux iptables execution context** — owned by S3-03 (already HARDENED) and S3-07.

## Notes for the implementer

- **The pinned `copy_out_root` path is Phase 11's load-bearing UI contract.** `logs_dir.parent / "copy_out" / str(run_id)` — do NOT regress to `logs_dir / "copy_out"`. The fence test `test_copy_out_root_path_pin` catches it, but reading this Note first saves an attempt.
- **`_construct_sandbox_run` is the only producer of populated `SandboxRun`s.** S3-02 HARDENED AC-FCS-3 made this the contract; S3-04 widens it additively. The meta-test caps `SandboxRun(` literal call sites at 1 (the one inside the helper). If you find yourself constructing a `SandboxRun(...)` directly in `execute()` or `copy_out`, you are violating the contract — back out and use the helper.
- **`_WaitOutcome` is the producer-side classifier.** The `SandboxRun` contract surface is unchanged (flat `timed_out` + `killed_by_oom` bools). The sum type lives behind the `_construct_sandbox_run` seam — Phase 6/11/13 consumers still see the flat fields. This is functional-core / imperative-shell at the type level: the union expresses the policy decision once; the flat fields are the wire-level contract.
- **`EVENT_SANDBOX_DID_TIMEOUT_DEFERRED` removal is loud, not silent.** The S3-02 test `test_spec_defer_time_budget_warns` is replaced (not deleted) by the natural successor `test_wait_with_timeout_triggers_sigkill`; the PR diff names both. AC-WIDEN-3. Rule 12 — fail loud.
- **OOM and timeout are mutually exclusive in the `SandboxRun` model** — set one or the other, never both. The kernel returns exit 137 for either; `State.OOMKilled` is the only reliable disambiguator. The `_WaitOutcome` sum type encodes this as an unrepresentable state at the producer; `_classify_wait_outcome` raises `AssertionError("S1-02 AC-7d violated")` if a caller bypasses the union.
- **`docker-py`'s `container.wait(timeout=)` raises `requests.exceptions.ReadTimeout`** on the pinned 7.x version. Stage-3 research finding confirmed against the 7.1.0 source. If we ever pin to 8.x, `_is_wait_timeout` + AC-DI-2 fail together; do not patch one without the other.
- **`container.get_archive` returns a tar stream (iterator of bytes chunks)**; buffer to a `BytesIO` before opening with `tarfile`. The `mode="r:*"` autodetects compression (uncompressed default for `get_archive`, gzipped for some Docker Desktop versions). Naive `BytesIO(b"".join(stream))` is fine for log-sized payloads but flag if any future `copy_out` glob hits a `node_modules/`-sized payload — that's a P0 cost regression (would belong in Phase 13).
- **`copy_out_root` directory must exist after `execute` returns even when `globs` is empty or every glob misses** — collectors iterate it. AC-COPY-1 + AC-COPY-EXIT-1..-3 + AC-PATH-1..-3 enforce this on every exit path.
- **Path traversal: a malicious tar entry with `../../../etc/passwd` must extract to `dest_root/etc/passwd` (relative if at all), never escape.** Two-layer defense: pure `_safe_resolve` policy (our skip-and-continue posture) + stdlib `tarfile.extract(..., filter="data")` belt-and-suspenders (PEP 706). Both layers must be exercised by the 5-fixture adversarial corpus.
- **Glob resolution uses `find -- <glob> -maxdepth 10 -print0`, NEVER `sh -c`.** Even though `spec.copy_out` is gate-catalog-pinned today, Phase 4 LLM influence on adjacent YAML keys means we cannot assume safety. List-form `container.exec_run(["find", ...])` is the only acceptable shape; the meta-test `test_no_shell_invocation` catches regressions.
- **Don't import `subprocess` in `copy_out.py`.** The SDK does the work. If you genuinely need a `docker cp` argv (e.g. a Docker Desktop version where `get_archive` is broken), escalate to ADR amendment — do not silently add a chokepoint. The current allowlist (`did/build.py`, `did/network_policy.py`, `firecracker/client.py`) is sealed by `tests/schema/test_no_subprocess_outside_build_chokepoint.py`; that fence test stays unchanged.
- **`_extract_tar_stream` is the seam Firecracker (S6-01) will re-use.** Keep the signature `Iterator[bytes] -> list[Path]` — no `Container` parameter, no Docker SDK imports inside the helper. The docstring's anchor paragraph is load-bearing for that re-use; don't elide it in refactor.
- **`CopyOutExtractor` Protocol is deferred per Rule 2** — rule-of-three not reached (DinD here, Firecracker is the second known consumer). The shared pure helper `_extract_tar_stream` is the seam; promote to a `Protocol` + registry only when a third backend lands.
- **Rule-of-four FCS elevation.** S3-01 + S3-02 + S3-03 + S3-04 all carry the pure-helper + impure-shell split as a positively-pinned AC. The `test_copy_out_purity.py` AST walker is the load-bearing test for this story's slice; future copy-out edits that smuggle SDK calls into the pure helpers fail it.
- **Future cleanup**: when S6-01 lands, hoist `_extract_tar_stream` to `src/codegenie/sandbox/_shared/tar.py` (or similar) and import from both DinD and Firecracker. This is the natural "shared backend" location ADR-0001 anticipates. Do NOT do this hoist in S3-04 (Rule 2 / surgical changes / extension by addition).
