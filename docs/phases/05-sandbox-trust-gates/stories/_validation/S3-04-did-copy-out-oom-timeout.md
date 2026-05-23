# Validation report: S3-04 — DinD `copy_out.py` + OOM detection + `time_budget_seconds` SIGKILL

**Validated:** 2026-05-23
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S3-04 widens three S3-02 HARDENED `SPEC-DEFER` raise-paths (`copy_out != []` / `time_budget_seconds` honored / forward-compat `image_pull_bytes` left for later) into real implementations and populates the three `SandboxRun` fields that S3-02 stubs to `False` (`timed_out`, `killed_by_oom`) and `(empty dir)` (`copy_out_root`). It is the **fourth concrete consumer** of Phase 5's hexagonal DI port pattern (S3-01 → S3-02 → S3-03 → here) and the **fourth** of the functional-core / imperative-shell split. Both patterns now have a rule-of-four mandate; both are elevated again here from "follow precedent" to enumerated ACs so a literal-following executor cannot regress them.

The draft correctly identified the deliverables (SDK tar-stream copy-out + SIGKILL/timeout + OOM detect) and traced cleanly to ADR-0001 / ADR-0004, but had **27 findings across all four critic lenses, including ten block-tier** that an executor following the draft literally would have shipped silently broken. The most consequential:

1. **`copy_out_root` path contradicts S3-02 HARDENED AC-RUN-FIELDS-14 + AC-LOGS-3.** Draft AC pins `copy_out_root = logs_dir / "copy_out"`; S3-02 HARDENED pins `copy_out_root = logs_dir.parent / "copy_out" / str(run_id)`. The S3-02 contract is the load-bearing one (Phase 11 evidence bundle keys on `logs_dir.parent / "copy_out" / str(run_id)`). Fix: AC-PATH-1..-3.
2. **`SandboxRun` construction bypasses `_construct_sandbox_run`.** S3-02 HARDENED AC-FCS-3 pins `_construct_sandbox_run` as the single source of truth that stamps `backend`, `gate_isolation_class`, and the seven stub fields. If S3-04 builds a `SandboxRun(...)` directly inside `execute()`, the stamp is duplicated and `gate_isolation_class` will diverge on the timeout / OOM exit paths. Fix: AC-CTOR-1..-4 + AC-FCS-1..-3 widen `_construct_sandbox_run` additively with new `outcome: _WaitOutcome` kwarg.
3. **No tagged-union for the wait result.** Draft passes a bare `(timed_out: bool, killed_by_oom: bool, exit_code: int)` tuple through the shell. The cross-field invariant `not (timed_out and killed_by_oom)` (S1-02 AC-7d / S3-02 AC-RUN-FIELDS-17) is then runtime-defensive instead of unrepresentable. Fix: AC-OUTCOME-1..-5 introduce `_WaitOutcome = Normal(exit_code) | TimedOut(exit_code=137) | OomKilled(exit_code=137)` discriminated union; `_classify_wait_outcome(...)` returns one variant; `_construct_sandbox_run` consumes the union and stamps the flat fields. Mutation: an implementation that sets both flags True cannot construct the union → fails at the type system + the runtime exhaustiveness test.
4. **Event names violate S1-01 HARDENED / S3-03 HARDENED `STARTED/COMPLETED/FAILED` verb convention.** Draft uses `sandbox.did.copy_out`, `sandbox.did.timeout`, `sandbox.did.oom_killed` — bare action nouns without the canonical verb suffix. Fix: AC-EVT-1..-3 ship six `Final[str]` `EVENT_*` constants (`SANDBOX_DID_COPY_OUT_STARTED/COMPLETED/FAILED/GLOB_MISS`, `SANDBOX_DID_TIMEOUT_SIGKILL`, `SANDBOX_DID_OOM_KILLED`) + the verb-namespace regex assertion + appended namespace-table test row.
5. **`EVENT_SANDBOX_DID_TIMEOUT_DEFERRED` from S3-02 must be REMOVED, not left dormant.** S3-02 AC-SPEC-DEFER-6 wired a one-time WARNING for non-default `time_budget_seconds`. With S3-04 honoring the timeout, the deferred-warning emit is wrong (will spam every gate that actually configures a timeout). Fix: AC-WIDEN-3 explicitly enumerates removal + the `tests/sandbox/did/test_client_core.py::test_spec_defer_time_budget_warns` test must be replaced (not deleted silently).
6. **Tar path-traversal guard is in Refactor, not AC.** A malicious tar member named `../../../etc/passwd` is the well-known PEP-706 / CVE-2022-21786 / Python `tarfile.extractall(filter="data")` (Python 3.12+) class. This is a security invariant on a Phase-4-LLM-influenced workload, not a refactoring nicety. Fix: AC-SEC-1..-3 lift to ACs with property + adversarial fixture tests.
7. **Glob resolution is shell-injection-vulnerable.** Draft outline uses `container.exec_run(["sh", "-c", f"ls -1 {glob}"])`. Even though `spec.copy_out` is YAML-pinned (gate catalog), Phase 4 LLM influence on adjacent fields means we cannot assume safety. Notes mention `shlex.quote` but it's not an AC; the actual mitigation must be **drop `sh -c` entirely** and use `find -- <glob> -maxdepth N -print0` via `exec_run(list-form)` with no shell. Fix: AC-GLOB-1..-4 + adversarial fixture.
8. **Second `wait()` after `kill()` is unbounded.** Implementation outline says "call `container.wait()` again (no timeout)". If SIGKILL doesn't reap (rare but documented Docker Desktop pathology), the orchestrator hangs forever. Fix: AC-REAP-1 pins `_REAP_GRACE_SECONDS: Final[int] = 5`; second wait uses this bound; failure escalates to `SandboxBackendError("reap_failed", …)`.
9. **`copy_out_root` must exist on the timeout + OOM exit paths too.** Draft AC pins existence only on the normal path. Collectors iterate `copy_out_root` regardless of how the run ended (Phase 5 §Goal: ledger-of-evidence-always); a missing dir → `FileNotFoundError` in every collector. Fix: AC-COPY-EXIT-1..-3 pin the dir is created (and copy-out is attempted best-effort) on all three exit paths; failures during copy-out on a timeout/OOM are logged at WARNING (the container may be partially dead).
10. **Cleanup ordering is undefined.** S3-02 has `try/finally container.remove(force=True)`. On timeout, the kill→wait→copy-out→remove sequence must be: kill → bounded-wait → copy-out (best-effort) → remove. Out-of-order risks `get_archive` against a removed container. Fix: AC-ORDER-1 + AC-ORDER-2 pin the sequence with a 4-cell parametrized test.

The draft's "Refactor" section had three of the ten block findings disguised as cleanup (`_safe_extract`, structlog timing fields, docstrings). Those are not refactors — they are required acceptance.

Resolution: ~55 numbered ACs across 17 sections (A through Q) (was 11 unnumbered checkboxes) plus a **seven-test-file TDD plan** (purity walker, helpers, copy-out core, timeout, oom, integration cleanup-grid, golden snapshot). Two Stage-3 research findings consumed inline (docker-py `wait(timeout=)` exception class on pinned version; Python 3.12 `tarfile filter='data'` exact semantics).

## Findings by critic

### Coverage critic

| Severity | Finding | Resolution |
|---|---|---|
| block | `copy_out_root` path contradicts S3-02 HARDENED AC-RUN-FIELDS-14 / AC-LOGS-3 (`logs_dir.parent / "copy_out" / str(run_id)`) — draft says `logs_dir / "copy_out"` | AC-PATH-1..-3 + a fence-test grep on `logs_dir / "copy_out"` to prevent regression. |
| block | `copy_out_root` not pinned on timeout / OOM exit paths (collectors `FileNotFoundError`) | AC-COPY-EXIT-1..-3: dir created on every exit path; copy-out attempted best-effort; failures logged WARN. |
| block | Cleanup ordering (kill → wait → copy-out → remove) undefined | AC-ORDER-1..-2: ordered try/finally + 4-cell parametrized cleanup grid. |
| block | Second `wait()` after SIGKILL is unbounded (Docker Desktop reap-failure pathology) | AC-REAP-1..-2: `_REAP_GRACE_SECONDS: Final[int] = 5`; failure raises `SandboxBackendError("reap_failed", …)` per S3-02-precedent closed-Literal reason. |
| block | `EVENT_SANDBOX_DID_TIMEOUT_DEFERRED` (S3-02 AC-SPEC-DEFER-6) must be REMOVED, not left dormant | AC-WIDEN-3 + AC-WIDEN-4 enumerate S3-02 AC widening + which client.py emits are removed; failing test replaced (not silently deleted). |
| block | S3-02 ACs being widened are not enumerated (AC-SPEC-DEFER-4, AC-SPEC-DEFER-6, AC-RUN-FIELDS-15, AC-RUN-FIELDS-16) | AC-WIDEN-1..-5 explicitly name every S3-02 AC modified + the executor-visible diff. |
| block | Glob resolution shell-injection (Phase-4-LLM-influenced YAML reaches `sh -c`) | AC-GLOB-1..-4: drop `sh -c` entirely; use `find -- <glob> -maxdepth N -print0`; adversarial fixture with `; rm -rf /` in a copy_out glob asserts list-form exec_run. |
| block | Tar path-traversal guard in Refactor section, not AC | AC-SEC-1..-3: `tarfile.open(..., mode="r:*")` then iterate with explicit `_safe_resolve(member.name, dest_root) -> Path | None` (return None on escape attempt) before any extraction; adversarial fixture + property test. |
| block | `SandboxRun` construction bypasses `_construct_sandbox_run` (S3-02 HARDENED AC-FCS-3 single source of truth) | AC-CTOR-1..-4 + AC-FCS-3 (widened): all three exit paths route through `_construct_sandbox_run(*, outcome=_WaitOutcome, copy_out_root=..., image_pull_bytes=...)`. |
| block | Mutual exclusion `not (timed_out and killed_by_oom)` is runtime-defensive, not unrepresentable | AC-OUTCOME-1..-5: `_WaitOutcome` sum type (Normal | TimedOut | OomKilled); `_classify_wait_outcome` returns one variant; exhaustiveness test (`typing.get_args(_WaitOutcome)` matches a literal class list). |
| harden | Grace seconds for the first wait unspecified | AC-WAIT-1: `_WAIT_TIMEOUT_GRACE_SECONDS: Final[int] = 0` (no grace on the first wait — the daemon already grants its own); doc string explains. |
| harden | `container.attrs["State"]["OOMKilled"]` schema assumption — older Docker versions may omit | AC-OOM-1: `.get("State", {}).get("OOMKilled", False)`; explicit boolean coercion; non-bool → `SandboxBackendError("oom_inspect_malformed", …)`. |
| harden | `container.reload()` failure path untested | AC-OOM-2: reload raising APIError → `_wrap_api_error` (S3-02 helper) → propagated; covered in cleanup grid. |
| harden | `exit_code` source-of-truth on timeout / OOM paths | AC-EXIT-1..-3: SIGKILL convention `137` comes from the kernel's `container.wait()` `StatusCode`, NOT hardcoded; on timeout, read from second wait; on OOM, read from first wait. If kernel returns ≠137 on OOM, log `EVENT_SANDBOX_DID_OOM_EXIT_CODE_UNEXPECTED` and trust the inspect flag. |
| harden | `started_at` / `ended_at` / `duration_ms` on timeout + OOM paths unpinned | AC-TIME-1: `ended_at` captured immediately after the FINAL wait returns (timeout: second wait; OOM: first wait); `duration_ms` computed in `_construct_sandbox_run` (S3-02 precedent). |
| harden | structlog event-fields per event unpinned | AC-EVT-4: parametrized per-event-fields table (`run_id: RunId`, `duration_ms: int`, `glob: str` for COPY_OUT_GLOB_MISS, `time_budget_seconds: int` for TIMEOUT_SIGKILL, `memory_limit_mib: int` for OOM_KILLED). |
| harden | Coverage floor wording absent | AC-COV-1..-3: ≥ 95% line on `copy_out.py`; ≥ 90% line on `client.py` widened delta; per-branch ≥ 85%. |
| nit | `pyproject.toml` unchanged | AC-DEP-1: confirms no new deps (uses stdlib `tarfile` + existing `docker` SDK). |

### Test-Quality critic

| Severity | Finding | Resolution |
|---|---|---|
| block | `test_wait_timeout_triggers_sigkill_and_sets_timed_out` mocks `fake.wait.side_effect = [TimeoutError("budget"), ...]` — but the actual SDK raises `requests.exceptions.ReadTimeout` on the pinned docker-py version. The test passes against a mock that doesn't reproduce production. | AC-WAIT-2: a parametrized fixture matrix `[requests.exceptions.ReadTimeout, docker.errors.APIError("timeout"), ConnectionError]` — every shape that docker-py is known to raise; the helper `_is_wait_timeout(exc) -> bool` is a pure classifier with a parametrized test; `_classify_wait_outcome` calls it. |
| block | `test_copy_out_materializes_matching_glob_logs_misses` exercises only one match + one miss; no multi-match, no nested-dir, no symlink, no empty glob list | AC-COPY-TESTS-1..-5: 5 parametrized fixtures (empty-list, single-match, single-miss, multi-match-with-dirs, all-miss); empty-list path asserts `copy_out_root.exists() and not list(copy_out_root.iterdir())`. |
| block | No property test for `not (timed_out and killed_by_oom)` cross-field invariant on every exit path | AC-OUTCOME-5: hypothesis test draws from `_WaitOutcome` variants + asserts the constructed `SandboxRun` always satisfies S1-02 AC-7d. |
| block | No adversarial tar fixture (path-traversal `../../etc/passwd`, absolute path `/etc/passwd`, symlink loop, dotfile, deeply nested `a/b/c/.../z/leaf`) | AC-SEC-3: 5-fixture adversarial corpus; each must extract to `dest_root` (or be skipped with WARN-level event), never escape; checked by post-test `assert dest_root.resolve() in p.resolve().parents` for every extracted path. |
| block | No adversarial glob fixture with shell-metacharacters (`; rm -rf /`, `$(cat /etc/passwd)`, `` `id` ``, `\n` injection) | AC-GLOB-3: 4-fixture adversarial corpus; asserts `exec_run` is called with list-form (not str-form, never `["sh", "-c", …]`); meta-test greps `copy_out.py` for `"sh"` and `"-c"` and `\"sh -c\"` substrings → must be zero. |
| block | `test_copy_out` mocks at the wrong layer — patches `container.get_archive` directly, doesn't exercise the pure tar-extraction helper independently | AC-FCS-4..-7: extract pure helper `_extract_tar_stream(stream: Iterator[bytes], dest_root: Path) -> list[Path]` independently unit-testable (no container); `tests/sandbox/did/test_copy_out_helpers.py` exercises it against raw bytes. |
| block | structlog event-fields not asserted in tests (typo in field name ships silently) | AC-LOG-1..-3: parametrized assertion over all six events; field names + types pinned. |
| block | Mutation: an impl that *always* attempts copy-out even when `spec.copy_out == []` is undetectable by the draft tests | AC-COPY-TESTS-1: empty-list path asserts `container.exec_run.call_count == 0` AND `container.get_archive.call_count == 0`. |
| harden | Mutation: an impl that swaps `timed_out` / `killed_by_oom` flags is caught only because `test_oom` asserts both fields; cross-test parametrization would be stronger | AC-OUTCOME-5: 3-row parametrized table (normal, timeout, oom) asserts each pair `(timed_out, killed_by_oom)` for the exact expected variant. |
| harden | Golden file `tests/golden/docker_cp_args_stage6_validate.json` schema unspecified | AC-GOLD-1..-3: pinned schema `{glob_to_argv: dict[str, list[str]], get_archive_paths: list[str]}`; byte-exact JSON sort_keys=True. |
| harden | `_extract_tar_stream` invariants suitable for hypothesis property test | AC-FCS-7: hypothesis property — for any random valid tar of N entries with no traversal, extracted file count == N; total bytes preserved. |
| harden | Idempotency on retry — calling `copy_out` twice with the same dest_root should overwrite, not append nor crash | AC-COPY-TESTS-6: second-call test asserts byte-equal result. |
| harden | `_is_wait_timeout` mock-patch drift defense missing | AC-DI-4: meta-test greps `tests/sandbox/did/` for `mock.patch("requests.exceptions` and asserts zero hits; tests must inject `_default_runner`-style port. |

### Consistency critic

| Severity | Finding | Resolution |
|---|---|---|
| block | `copy_out_root = logs_dir / "copy_out"` contradicts S3-02 HARDENED AC-RUN-FIELDS-14 (`logs_dir.parent / "copy_out" / str(run_id)`) | AC-PATH-1..-3 + fence test. |
| block | S3-02 AC-SPEC-DEFER-4, AC-SPEC-DEFER-6 widening not enumerated; S3-02 stub fields AC-RUN-FIELDS-15/-16 silently replaced | AC-WIDEN-1..-5 enumerate each S3-02 AC modified. |
| block | Event names violate S1-01 HARDENED / S3-03 HARDENED `STARTED/COMPLETED/FAILED` verb convention | AC-EVT-1..-4: six `EVENT_*` `Final[str]` constants + namespace regex + table-extension test. |
| block | New exception class on `reap_failed` must subclass `SandboxBackendError` and widen S3-03's closed `reason` Literal additively | AC-ERR-1..-3: enumerated additions (`reap_failed`, `oom_inspect_malformed`, `copy_out_archive_failed`, `tar_member_outside_dest`); 4 members added to S3-03's 11-member union; AC-ERR-3 source-pins `typing.get_args(SandboxBackendError.reason)` includes all 15. |
| block | `_construct_sandbox_run` widening must be additive (S3-02 HARDENED contract) | AC-CTOR-1..-4 + AC-FCS-3 — keyword-only `outcome`, `copy_out_root`, `image_pull_bytes` kwargs; defaults preserve the S3-02 zero-stub behavior when called from tests that don't yet set them. |
| harden | `RunId` NewType not propagated to structlog `run_id` field on the new events | AC-EVT-5: `extra={"run_id": run_id}` is typed `RunId` (source pin via `inspect.getsource`); meta-test greps for `run_id=str(` → must be zero. |
| harden | `gate_isolation_class` propagation across timeout / OOM exit paths unstated | AC-CTOR-3: `_construct_sandbox_run` stamps `_GATE_ISOLATION_CLASS` once for every exit path (S3-02 AC-RUN-FIELDS-4 contract holds). |
| harden | Phase ADR table missing ADR-0006 (Protocol deferral), ADR-0014 (frozen Pydantic) | "ADRs honored" line expanded. |
| harden | Phase 11 evidence bundle keys on `copy_out_root` — Notes-for-implementer must mark the path-pin as load-bearing | Notes paragraph added. |
| harden | `forbidden-patterns` pre-commit hook (no `subprocess` outside chokepoints) — fence test allowlist edit unspecified | AC-FENCE-1: confirms `copy_out.py` is NOT added to the chokepoint allowlist (it is SDK-only); meta-test greps `copy_out.py` for `import subprocess` → must be zero. |

### Design-Patterns critic

| Severity | Finding | Resolution |
|---|---|---|
| block (rule-of-four reached) | Functional core / imperative shell — S3-01 + S3-02 + S3-03 + S3-04 = four consumers | Elevated again as AC: AC-FCS-1..-7 enumerate `_extract_tar_stream` (pure), `_classify_wait_outcome` (pure), `_is_wait_timeout` (pure), `_safe_resolve` (pure), + `_construct_sandbox_run` (widened, pure), + the impure `copy_out` shell + the impure `execute` shell. Dedicated `test_copy_out_helpers.py`. |
| block (sum-type opportunity) | `(timed_out, killed_by_oom, exit_code)` tuple → tagged union | AC-OUTCOME-1..-5: `_WaitOutcome = Normal | TimedOut | OomKilled` (frozen dataclasses with discriminator); `_classify_wait_outcome` is the only constructor; pattern-matched in `_construct_sandbox_run`. Mutation: an impl that returns `(True, True, 137)` cannot construct the union. |
| block (hexagonal DI port) | `container.wait` timeout exception classification — `_is_wait_timeout(exc: BaseException) -> bool` is a pure classifier injectable for testing | AC-DI-1..-3: `_is_wait_timeout` ships as a pure function; `_wait_with_timeout(container, timeout, *, is_timeout=_is_wait_timeout)` accepts kwarg injection; tests inject identity-on-fake-exception. |
| block (smart constructor) | `_construct_sandbox_run` is the only public path to a populated `SandboxRun`; pinned by source-grep | AC-CTOR-1: meta-test greps `client.py` for `SandboxRun(` literal call sites → must be ≤ 1 (the one inside `_construct_sandbox_run`); all other call sites go through the helper. |
| harden | Closed Literal discriminator on widened `SandboxBackendError.reason` (consistent with S3-03 HARDENED pattern) | AC-ERR-1 (above). |
| harden | `_safe_resolve` Adapter pattern — single tar-member-name → safe Path classifier | AC-SEC-2: extracted as pure helper; mirror of S3-03's `_validate_ip_literal`. |
| harden | `_extract_tar_stream` is the seam where a future Firecracker copy-out (`copy_out.tar` host file) can re-use the same pure extractor | AC-FCS-6: docstring explicitly anchors the future Firecracker re-use; signature accepts an `Iterator[bytes]` (not a `Container`), so Firecracker can `open(host_tar, 'rb')` and pass chunks. |
| pattern-note | `CopyOutExtractor` Protocol (DinD/Firecracker/future) — rule-of-three NOT reached yet (only DinD here; Firecracker has separate `S6-01` copy-out path) | Deferred per Notes paragraph; collapse to Protocol when S6-01 lands. |
| pattern-note | `GlobPattern = NewType("GlobPattern", str)` for `spec.copy_out` items | YAGNI per Rule 2; one validation site (`SandboxSpec.copy_out: list[str]`); promote when a second consumer needs the type. |
| pattern-note | Tar member iteration as a `_TarMember` sum type (Regular | Directory | Symlink | Hardlink | Skip) | YAGNI — `_safe_resolve` + `member.isfile()` short-circuit suffices; promote when copy-out semantics need to follow symlinks or preserve permissions (Phase 13+ cost-attribution may want this). |

## Research briefs

**Two Stage-3 questions surfaced; both answered inline:**

### Research 1 — `docker-py` `container.wait(timeout=)` exception class on the pinned version

- **Question:** What exception does `container.wait(timeout=<int>)` raise on timeout on `docker==7.1.0` (the version pinned in `pyproject.toml`)?
- **Sources consulted:** [docker-py 7.1.0 source](https://github.com/docker/docker-py/blob/7.1.0/docker/api/container.py) (`wait` method), [requests 2.32 timeout exceptions](https://docs.python-requests.org/en/latest/api/#requests.exceptions.ReadTimeout), Docker SDK changelog 6.x→7.x.
- **Finding:** `docker-py` 7.x's `container.wait(timeout=N)` delegates to `requests.get(..., timeout=N)` against the daemon's `/wait` endpoint. On timeout, `requests.exceptions.ReadTimeout` propagates unchanged. Some 6.x versions wrapped it in `docker.errors.APIError`; 7.x does not. `ConnectionError` is a separate signal (daemon unreachable, not timeout).
- **Recommendation:** `_is_wait_timeout(exc) -> bool` ships as a pure classifier — returns `True` on `isinstance(exc, requests.exceptions.ReadTimeout)`, `False` otherwise. ConnectionError flows to `_wrap_api_error` and becomes `SandboxBackendError("daemon_unreachable", …)`. AC-WAIT-2 parametrizes a 3-row matrix (ReadTimeout → True; APIError → False; ConnectionError → False). If docker-py is ever pinned to 8.x+ and exception classes change, the classifier and its test fail together (not silently).

### Research 2 — Python 3.12 `tarfile.open(..., mode="r:*")` filter semantics

- **Question:** PEP 706 / Python 3.12 added `tarfile.extractall(filter="data")` to mitigate path-traversal. Does the `data` filter cover every relevant attack class for an LLM-influenced workload tar?
- **Sources consulted:** [PEP 706](https://peps.python.org/pep-0706/), [Python 3.12 tarfile docs §"Extraction filters"](https://docs.python.org/3/library/tarfile.html#extraction-filters), CVE-2007-4559 history, [Python 3.13 `data` filter source](https://github.com/python/cpython/blob/v3.13.0/Lib/tarfile.py#L2400).
- **Finding:** The `data` filter (a) rejects absolute paths, (b) rejects `..` traversal components, (c) skips device/FIFO/character special files, (d) sanitizes permissions, (e) does NOT follow symlinks during extraction (links resolved to in-archive members only). It is the strict-mode filter intended for general-purpose untrusted extraction. **However**, `extractall(filter="data")` raises `tarfile.AbsolutePathError` / `tarfile.LinkOutsideDestinationError` / `tarfile.OutsideDestinationError` on each violation — extraction stops at the first bad member. For our case we want best-effort (skip bad members, log, continue).
- **Recommendation:** Two-layer defense — (a) iterate members manually with `tarfile.TarFile.next()`; (b) for each member, call `_safe_resolve(member.name, dest_root)` (pure, our code); skip + `EVENT_SANDBOX_DID_COPY_OUT_TAR_MEMBER_REJECTED` log on `None`; (c) for accepted members, call `tarfile.TarFile.extract(member, dest_root, filter="data")` as belt-and-suspenders (the stdlib filter is the final guard). Two layers because PEP 706 is the canonical defense but doesn't fit our skip-and-continue policy; our `_safe_resolve` is the policy decision. AC-SEC-1..-3 pin both layers; the 5-fixture adversarial corpus exercises both.

## Conflict resolutions

- **Coverage vs Rule 2 on `CopyOutExtractor` Protocol.** Coverage critic wanted a `Protocol` so Firecracker can plug in later; Design-Patterns invoked Rule 2 (rule-of-three not reached — only DinD here; S6-01 Firecracker is the second known consumer). Rule 2 wins; the **shared pure helper** `_extract_tar_stream(Iterator[bytes], Path) -> list[Path]` is the precedent so Firecracker can re-use it without a Protocol; full Protocol abstraction deferred per Notes paragraph until S6-01 + a third consumer.
- **Coverage vs Design-Patterns on a `_TarMember` sum type.** Coverage wanted Regular/Directory/Symlink/Hardlink/Skip discrimination; Design-Patterns argued YAGNI — `member.isfile()` short-circuits + `_safe_resolve` covers the security policy. Rule 2 wins; Notes-for-implementer carries the promotion trigger (Phase 13+ symlink preservation).
- **Test-Quality vs Stage-3 finding on tarfile filter.** Test-Quality wanted `filter="data"` only (PEP 706 canonical); Stage-3 finding showed it raises on first bad member, incompatible with best-effort skip. Resolution: two-layer defense (our `_safe_resolve` policy decision + stdlib `filter="data"` belt-and-suspenders).
- **Design-Patterns vs Consistency on `_WaitOutcome` sum type.** Design-Patterns wanted to widen `SandboxRun` itself into a tagged union (`SandboxRun.outcome: Normal | TimedOut | OomKilled`); Consistency invoked S1-02 HARDENED's flat-field contract + downstream Phase 6/11/13 already key on the flat fields. Resolution: `_WaitOutcome` is an INTERNAL sum type that `_construct_sandbox_run` consumes and stamps the flat fields. The cross-field invariant becomes unrepresentable at the producer; the contract surface is unchanged. Both critics satisfied.

## Edits applied to the story

**Header:**
- `Status: Ready` → `Status: Ready (HARDENED 2026-05-23)`.
- `Depends on:` corrected from `S3-02 only` to `S1-02 + S3-02 + S3-03` with the specific symbols each contributes named in parens.
- `ADRs honored:` expanded from ADR-0001 + ADR-0004 to add ADR-0006 (Protocol deferral), ADR-0014 (frozen Pydantic models), ADR-0001 amendment-not-needed clarification (copy_out.py stays out of subprocess allowlist).

**Validation notes (new, ~75 lines):** Ten block-tier + seventeen harden/nit findings summarized; rationale for every AC change; pattern-lineage callouts (S3-01 → S3-02 → S3-03 → S3-04 for DI ports + FCS); two research findings consumed inline.

**Context (rewritten):** Added explicit S3-02 widening narrative (which `SPEC-DEFER` raises become real implementations); added rule-of-four pattern-elevation paragraph; pinned the `copy_out_root` path is the S3-02 HARDENED contract.

**References (expanded):** Added line-number anchors into arch design; added prior HARDENED reports (S1-02, S3-02, S3-03); added external docs for docker-py wait/get_archive + Python 3.12 tarfile filter + PEP 706.

**Goal (rewritten):** Now explicitly names (a) which S3-02 ACs are being widened, (b) the `_WaitOutcome` sum type as the producer-side classifier, (c) the six new `EVENT_*` constants, (d) the two-layer tar-member safety policy, (e) the `find -- <glob>` shell-injection mitigation.

**Acceptance criteria (rewritten):** Was 11 unnumbered checkboxes; now ~55 numbered ACs across 17 sections (A through Q):
- A. Public surface + module purity (`copy_out.py`)
- B. `_WaitOutcome` sum type + classifier
- C. `_extract_tar_stream` pure helper + property test
- D. `_safe_resolve` pure helper + adversarial corpus
- E. `_is_wait_timeout` pure classifier (DI port)
- F. `_wait_with_timeout` impure shell + reap grace
- G. `copy_out` impure shell + glob mitigation
- H. `_construct_sandbox_run` additive widening (S3-02 contract preserved)
- I. `client.py` execute-flow edit (timeout + OOM + copy-out + cleanup)
- J. `copy_out_root` discipline (load-bearing path) on every exit path
- K. Cleanup ordering + 4-cell parametrized cleanup grid
- L. Closed Literal `reason` widening on `SandboxBackendError`
- M. S3-02 AC widening enumeration
- N. Module purity (AST walker for `copy_out.py`)
- O. Event-name discipline (append-only to S1-01 + S3-02 + S3-03 table)
- P. Golden file `docker_cp_args_stage6_validate.json` schema + fixtures
- Q. Tests stay green + coverage floors + dependencies

**Implementation outline (rewritten):** Now ordered: events first → error widening → `_WaitOutcome` sum type → pure helpers (`_safe_resolve`, `_extract_tar_stream`, `_is_wait_timeout`, `_classify_wait_outcome`) → `copy_out.py` shell → `client.py` execute-flow edit → `_construct_sandbox_run` widening → remove `EVENT_SANDBOX_DID_TIMEOUT_DEFERRED` emit + replace its test → seven test files in red-first order → golden fixture generation → refactor pass (docstrings only).

**TDD plan (rewritten):** Seven test files (was three):
1. `test_copy_out_helpers.py` — `_safe_resolve` parametrized + adversarial 5-fixture; `_extract_tar_stream` hypothesis property + 3 concrete fixtures.
2. `test_wait_classification.py` — `_is_wait_timeout` 3-row matrix; `_classify_wait_outcome` 3-row matrix + exhaustiveness assertion.
3. `test_copy_out.py` — core: 5-fixture parametrized + adversarial glob 4-fixture + idempotency.
4. `test_timeout.py` — core: parametrized exception-class matrix + reap-grace + cleanup-order assertion.
5. `test_oom.py` — `OOMKilled=True/False/missing-key/malformed`; `container.reload()` failure.
6. `test_client_copy_out_integration.py` — 4-cell cleanup grid; full `_construct_sandbox_run` consumes `_WaitOutcome` correctly; structlog event-fields assertion (parametrized over all six events).
7. `test_copy_out_purity.py` — module-purity AST walker for `copy_out.py`.

**Files to touch (expanded):** Now lists 19 file entries (was 6) including the four edited existing files (client.py, errors.py, the S3-02 helpers module, S3-02 `test_client_core.py` for replacing the deferred-warning test) + two new source files (`copy_out.py` + `_wait_outcome.py` or inline in client.py per Notes) + seven new test files + golden + adversarial tar fixtures (5) + adversarial glob fixtures (4).

**Out of scope (renumbered + expanded):** Explicitly defers Firecracker copy-out (S6-01), live integration (S3-07), `retry_policy.timeout_retryable` semantics (S5 GateRunner), `image_pull_bytes` population (deferred — S3-04 leaves at 0 with the explicit Note that it's S3-04's natural successor; see "Notes for the implementer"), `CopyOutExtractor` Protocol (Phase-7+), `_TarMember` sum-type (Phase 13+).

**Notes for the implementer (expanded):** Pattern-lineage paragraphs (DI ports rule-of-four, FCS rule-of-four, `_WaitOutcome` sum-type rationale, `CopyOutExtractor` Protocol deferral, `_TarMember` deferral); explicit Phase 11 evidence-bundle load-bearing path pin (`copy_out_root = logs_dir.parent / "copy_out" / str(run_id)`); explicit `EVENT_SANDBOX_DID_TIMEOUT_DEFERRED` removal-not-deletion note; structlog `run_id: RunId` typing pin; cross-story forward-pointers (S3-05, S3-07, S6-01, Phase 11, Phase 13).

## Forward-compat anchor — what's pinned for downstream stories

- **S3-05 (multi-phase YAML collapse / `stage6_validate.yaml`):** consumes `_REAP_GRACE_SECONDS` + `_WAIT_TIMEOUT_GRACE_SECONDS` as named precedents; per-phase timeouts will sum into a budget. The `_WaitOutcome` sum type is the precedent for per-phase outcome aggregation.
- **S3-06 (SandboxHealthProbe):** the `_REAP_GRACE_SECONDS` constant is also the health-check timeout floor for the `container.kill` path; probe surfaces a warning if any prior runs hit `reap_failed`.
- **S3-07 (live integration `test_did_hello_node.py`):** removes the `_is_wait_timeout` injection in production code (still injectable for tests); runs real Docker daemon; first real exercise of the `_safe_resolve` + tar extractor against a live `npm test` container.
- **S6-01 (FirecrackerClient):** re-uses `_extract_tar_stream` against the host-side `copy_out.tar` file (`open(host_tar, 'rb').read1(8192)` iterator); validates the pure helper does not assume Docker SDK. The `_WaitOutcome` sum type is the precedent for Firecracker's `oom_killed_by_kernel` / `vm_timeout` exit-path classification.
- **Phase 11 (evidence bundle):** consumes `SandboxRun.copy_out_root` as `logs_dir.parent / "copy_out" / str(run_id)` — pinned path is the load-bearing UI contract.
- **Phase 13 (cost ledger):** keys on `_WaitOutcome` variant for cost-attribution buckets (`Normal` / `TimedOut` / `OomKilled`); the closed sum type is the contract.

## No `RESCUE` findings

The `copy_out_root` path contradiction was the closest to structural — it could have caused every collector and the Phase 11 evidence bundle to look in the wrong directory — but the resolution is purely an AC text correction to match S3-02 HARDENED. The `_WaitOutcome` sum type and `_construct_sandbox_run` widening are larger structural changes than typical "harden in place" edits, but they are additive (no S3-02 contract is broken) and the four-pattern lineage made the elevation natural rather than disruptive.

## Recommended next step

`phase-story-executor` to implement.

The story is now ready for the executor:
- Every AC is individually verifiable.
- The AC set collectively guarantees the goal (copy-out happens on every exit path; timeout is bounded with a reap grace; OOM is read from the inspect flag, not inferred from exit code; tar members cannot escape `dest_root`; globs cannot inject shell; `_WaitOutcome` sum type makes the cross-field invariant unrepresentable).
- Every AC has a corresponding test in the TDD plan that would fail on an obviously wrong implementation (mutation-resistance via parametrized exception-class matrices, hypothesis property tests on `_extract_tar_stream`, adversarial fixtures for tar-traversal + glob-injection, exhaustiveness on `_WaitOutcome`, structlog event-fields parametrized over all six events).
- The `_construct_sandbox_run` widening is documented as additive — no S3-02 HARDENED contract is broken.
- The `EVENT_SANDBOX_DID_TIMEOUT_DEFERRED` removal is loud (explicit replacement of the S3-02 test, not silent deletion) — Rule 12 satisfied.
- The pattern-lineage (DI ports rule-of-four, FCS rule-of-four) is encoded as ACs with positive AST-walk pins — the patterns now live in the test suite, not in tribal knowledge.
