# Story S3-02 — `DockerInDockerClient` SDK core — create/start/exec/inspect/remove

**Step:** Step 3 — Implement DinD backend + SandboxSpecBuilder + SandboxHealthProbe
**Status:** Ready (HARDENED 2026-05-23)
**Effort:** M
**Depends on:** S1-01 (`sandbox/errors.py` `SandboxBackendError` + `SandboxImageUnavailable` + `sandbox/logging.py` event-name table + append-only policy), S1-02 (`SandboxClient` Protocol, `SandboxSpec`/`SandboxRun`/`SandboxHealth`/`CopyInEntry` frozen models + `RunId` NewType + canonical Literal spellings + cross-field validators), S1-05 (`@register_sandbox_backend` decorator + `sandbox_backend_registry` + `get_backend`)
**ADRs honored:** ADR-0001 (two chokepoints — SDK lives here; subprocess does NOT — enforced by AST fence), ADR-0004 (DinD macOS default + `gate_isolation_class="shared_kernel"` permanent annotation), ADR-0006 (`SandboxClient` is a `runtime_checkable` Protocol — `DockerInDockerClient` satisfies it structurally, no inheritance)

## Validation notes (2026-05-23, phase-story-validator)

**Verdict:** HARDENED. The draft correctly identified the deliverables (SDK-only `execute()` + `health()` + cleanup discipline + AST fence) and traced cleanly to ADR-0001 / ADR-0004 / ADR-0006, but had **27 findings across all four critic lenses, including twelve block-tier** that an executor following the draft literally would have silently violated. The most consequential:

1. **(consistency + coverage + patterns — block) Phantom `EnvAllowlist` class type — same family bug S3-01 already caught.** Constructor `__init__(*, docker_url, allowlist: EnvAllowlist)` types against a class that does NOT exist: S1-05 HARDENED ships `env_allowlist.filter` as a **module-level function**, with `__all__ = {"ALLOWLIST", "ALLOWLIST_PREFIXES", "DENY_SUBSTRINGS", "filter"}` — no `EnvAllowlist` class. Worse, the DinD client has no business taking the filter at all — env filtering happens in `SandboxSpecBuilder.for_gate` (S3-01) BEFORE the spec reaches the client; by the time `client.execute(spec)` is called, `spec.env` is already the post-filter view (and pinned into `sandbox_spec_hash`). Resolution: **drop the `allowlist` parameter entirely**. Constructor becomes `__init__(self, *, docker_url: str | None = None, docker_factory: Callable[[], DockerClient] = docker.from_env)`. AC-DI-1 forbids any `EnvAllowlist` reference; AC-DI-2 introduces the `docker_factory` Hexagonal port per the S3-01 precedent (Rule 2 OK — single second consumer of the DI-port pattern; the rule-of-three threshold is reached when S6-01 Firecracker repeats it, at which point the pattern is canonical).

2. **(consistency + coverage — block) `run_id` typed as raw `str`, violates S1-02 HARDENED `RunId` NewType.** S1-02 promoted `RunId = NewType("RunId", str)` to `codegenie.types.identifiers` precisely because `run_id` crosses ≥5 module boundaries (S2-01 ledger / S3-02 client / S5-02 runner / S7-03 cost / S8-01 CLI). S3-02 is the GENERATION site — if it stamps raw `str`, every downstream consumer either casts (ceremony) or accepts `str` (defeats the NewType). Resolution: AC-RUN-ID-1 pins `run_id = RunId(uuid7_helper())` AND `typing.get_type_hints(_construct_sandbox_run)["run_id"]` is `RunId` (source-level pin via `inspect.getsource`).

3. **(consistency + coverage — block) `SandboxRun` field set incomplete vs S1-02 HARDENED contract.** S1-02 ships `SandboxRun` with 13 required fields, all `extra="forbid"`/`frozen=True`. Draft's "On success, SandboxRun carries…" lists 9. Missing: `spec`, `microvm_seconds`, `image_pull_bytes`, `build_cache_hit`, `trace_path`, `timed_out`, `killed_by_oom`. Because `extra="forbid"` and all fields are required, the executor literally cannot construct `SandboxRun` without them — but with no AC pinning the values, the silent-field-default drift can ship wrong constants downstream (Phase 13 cost ledger keys on `microvm_seconds`; Phase 11 evidence bundle keys on `build_cache_hit`). Resolution: AC-RUN-FIELDS-1..AC-RUN-FIELDS-13 enumerate every field + the S3-02 stub value with a Phase pointer for who populates it later.

4. **(coverage + test-quality — block) Canonical Literal spellings (`"docker_in_docker"`, `"shared_kernel"`) asserted by side-effect only.** S1-02 HARDENED AC-4/4a pin `Literal["docker_in_docker", "firecracker"]` and `Literal["shared_kernel", "microvm"]` byte-exact via `typing.get_args(...)`. S3-02's happy-path test only asserts `run.backend == "docker_in_docker"` for one fixture; a refactor that changes `client.py` to stamp `"dind"` would be caught at the model layer (ValidationError) — indistinguishable from "any backend Literal would also fail". Resolution: AC-CANONICAL-1 + AC-CANONICAL-2 pin positively at the *client* layer via (a) byte-exact `run.backend == "docker_in_docker"` AND (b) AST walk asserting the literal string appears in `client.py` source (catches `backend=os.environ.get("BACKEND", "docker_in_docker")` smuggling).

5. **(consistency + coverage — block) `enable_trace`, `network`, `egress_allowlist`, `copy_in`, `copy_out`, `time_budget_seconds` silently ignored.** Implementation outline §3 hardcodes `network_mode="none"` and reads only `base_image`, `cmd`, `env`, `memory_limit_mib`, `pids_limit`. The other six `SandboxSpec` fields (parts of the contract per S1-02 AC + spec hash per S3-01) are silently dropped — a `SandboxSpec(network="scoped", egress_allowlist=["registry.npmjs.org"], enable_trace=True, copy_in=[…], time_budget_seconds=600)` would run with `network=none`, no egress lockdown, no trace, no host→sandbox copy, no SIGKILL. Rule 12 "Fail loud" violation. Resolution: AC-SPEC-DEFER-1..AC-SPEC-DEFER-5 explicitly enumerate the deferred fields with fail-loud semantics — `NotImplementedError(f"…deferred to S3-03/S3-04…")` if specified non-default (parametrized table) — with the exception of `enable_trace=True`, which surfaces `trace_path=None` and a one-time WARNING event `sandbox.did.trace.deferred` (S4-03 owns trace capture; arch §Process view line 363 implies trace is the strace-in-VM concern of later collectors).

6. **(consistency — block) `SandboxBackendError` reason field is open free-form string.** Draft AC-4 says "structured `reason` field (kept short — no log bytes)" but does NOT pin the value set. Phase 13 cost ledger and Phase 11 evidence bundle key on `reason` — a free-form string is silently incompatible. Resolution: AC-ERR-1 pins `reason: Literal["create_failed", "start_failed", "stream_failed", "wait_failed", "image_unavailable", "remove_failed"]` — closed set, byte-exact. AC-ERR-2 pins which Docker SDK exception class maps to which reason (table).

7. **(coverage + test-quality — block) APIError tested only on `create`; `start`/`wait`/`logs`/`remove` paths untested.** Arch §Edge case #1 specifies "APIError raised during exec" — the daemon can die during start, logs streaming, wait, or remove. Draft TDD covers `.create.side_effect = APIError` only. A mutation that fails to wrap APIError in `start`/`wait`/`logs` passes every existing test. Resolution: AC-APIERR-1 parametrized over `[create, start, wait, logs]` × asserts wrap-as-`SandboxBackendError` + `reason` per AC-ERR-2 mapping.

8. **(coverage + test-quality — block) Image-pull failure not addressed.** Arch §Edge case #2 specifies `docker.errors.ImageNotFound` → `SandboxImageUnavailable` (distinct subclass of `SandboxBackendError`). Draft collapses everything into generic `SandboxBackendError`. Operator visibility for digest issues lost. Resolution: AC-IMG-1 pins `ImageNotFound` → `SandboxImageUnavailable("image_unavailable")` — distinct class hierarchy preserved.

9. **(coverage + test-quality — block) `SandboxHealth.confidence` and `detected_at` silently absent.** S1-02 HARDENED requires six fields on `SandboxHealth`; draft AC-5 mentions five. `detected_at` missing → construction raises `ValidationError`. `confidence` value unspecified per branch — `daemon_unreachable` vs `buildx_missing` vs `strace_ptrace_missing` could each return any of `"high"/"medium"/"low"`. Resolution: AC-HEALTH-1..AC-HEALTH-5 pin (a) `detected_at = datetime.now(timezone.utc)` populated on every return path, (b) deterministic confidence mapping table, (c) deterministic `reasons`/`warnings` ordering (alphabetical sort before return — catches set→list nondeterminism in audit diffs), (d) namespaced warning IDs per CLAUDE.md (`sandbox.buildx_missing`, `sandbox.daemon_unreachable`, `sandbox.strace_ptrace_missing`).

10. **(test-quality + coverage — block) Cleanup-failure path untested.** AC-6 says "Cleanup failure logs at WARNING but does not raise." Draft TDD has no test for this — the `finally` clause swallowing exceptions IS the silent-failure mode Rule 12 forbids. Resolution: AC-CLEANUP-1..AC-CLEANUP-4 pin: (a) `remove(force=True)` runs exactly once in `finally`; (b) cleanup failure logs at WARNING with `sandbox.did.cleanup.failed` event carrying `{run_id, error_class, error_message_truncated_512}`; (c) primary exception always wins (no `raise … from cleanup_err` clobbering); (d) cleanup-on-success failure → `execute()` still returns the `SandboxRun` (the run happened; cleanup is best-effort). Parametrized test grid: `[start, logs, wait]` × `[RuntimeError, APIError]` × `{primary success, primary failure}`.

11. **(consistency + coverage — block) Event names are bare strings — violates S1-01 HARDENED canonical-table + append-only policy.** Draft step 5 names four events as bare strings (`'sandbox.did.execute.start'` etc.). S1-01 HARDENED AC-4a/4b/4c require every Phase-5 event name to be a `Final[str]` constant in `sandbox/logging.py`, byte-equal to a pinned table value, with sorted `__all__`. Resolution: AC-EVT-1 appends four constants (`EVENT_SANDBOX_DID_EXECUTE_STARTED`, `_COMPLETED`, `_FAILED`, `EVENT_SANDBOX_DID_HEALTH_CHECKED` — matching S1-01's `STARTED/COMPLETED/FAILED` verb convention, NOT the draft's inconsistent `start/done/error`). AC-EVT-2 also lands `EVENT_SANDBOX_DID_CLEANUP_FAILED`, `EVENT_SANDBOX_DID_TRACE_DEFERRED`, `EVENT_SANDBOX_DID_COPY_IN_DEFERRED`. AC-EVT-3 pins the structured field set per event.

12. **(consistency — block) New runtime deps (`docker`, uuid7 source) absent from `pyproject.toml`.** Draft imports `docker` and `uuid_extensions` ("or stdlib UUID7 helper if vendored"). `grep "docker\|uuid" pyproject.toml` returns nothing in deps. The story neither pins the dep additions nor disambiguates `uuid7` source (three different PyPI packages have different APIs: `uuid7`, `uuid_utils`, `uuid_extensions` — the unmaintained one). Resolution: AC-DEP-1 adds `docker>=7,<8` to `[project.dependencies]`; AC-DEP-2 adds `types-docker` to dev deps. AC-UUID-1 vendors a tiny `codegenie/sandbox/did/_uuid7.py` helper (RFC 9562 bit-twiddling, ≤25 LOC, stdlib `secrets`/`time_ns` only — keeps dep surface minimal; ADR-0001 fence-closure unaffected). AC-UUID-2 + AC-UUID-3 unit-test the helper for version-nibble correctness, length, charset, and monotonicity across `time.time_ns()` calls.

Beyond the block-tier findings, the harden-tier work:

13. **(test-quality — harden) `stderr.log` never tested with non-empty content.** Draft fixture `iter([(b"hello\n", b"")])` has empty stderr — an implementation that swaps stdout/stderr file targets OR drops the stderr branch passes. Resolution: AC-STREAM-1 + AC-STREAM-2 + AC-STREAM-3 parametrize log-chunk shapes covering `(stdout-only, stderr-only, mixed, empty, None-halves, large)`; hypothesis property test asserts byte-faithful round-trip.

14. **(coverage — harden) `_construct_sandbox_run` `started_at`/`ended_at` semantics unpinned.** S1-02 AC-7c pins `ended_at >= started_at`. Draft says "populated `started_at`/`ended_at`/`duration_ms`" without (a) what tz, (b) when each is captured, (c) whether `duration_ms` is computed from the delta or measured independently. Resolution: AC-TIME-1 pins `started_at = datetime.now(timezone.utc)` immediately before `container.start()`; `ended_at = datetime.now(timezone.utc)` immediately after `container.wait()`; both `tzinfo=timezone.utc` (naive datetimes rejected by ADR-0014 model_config); `duration_ms == int((ended_at - started_at).total_seconds() * 1000)` — single source of truth.

15. **(patterns — harden, elevated to AC under rule-of-three) Functional-core / imperative-shell tangle.** Draft `execute()` mixes `run_id` gen, fs `mkdir`, SDK calls, log stream, file writes, `wait`, `SandboxRun` construct, cleanup in one 50-LOC method. S3-01 HARDENED set the precedent (`_canonical_blake3` etc.); S3-02 is the second concrete consumer in the family — rule-of-three reached once Firecracker (S6-01) replicates. Elevate now: AC-FCS-1 enumerates four pure helpers (`_build_container_kwargs(spec) -> ContainerKwargs`, `_construct_sandbox_run(*, …) -> SandboxRun`, `_wrap_api_error(err, *, where) -> SandboxBackendError | SandboxImageUnavailable`, `_demux_chunks(chunks) -> Iterator[tuple[bytes, bytes]]`); AC-FCS-2 + AC-FCS-3 + AC-FCS-4 + AC-FCS-5 unit-test each helper independently of `execute()`. The `_construct_sandbox_run` helper carries the `backend="docker_in_docker"` and `gate_isolation_class="shared_kernel"` literals as `Final` module constants — single source of truth, mutation-resistant.

16. **(test-quality + coverage — harden) Module-purity AST walker missing.** Every prior Phase-5 Step-1/3 story shipped `tests/.../test_*_purity.py` (S1-02..S1-06 confirmed; S3-01 AC-PURE-1..AC-PURE-5). Resolution: AC-PURE-1..AC-PURE-7 ship `tests/sandbox/did/test_client_purity.py` (TYPE_CHECKING-aware) enforcing (a) `from __future__ import annotations` immediately after the module docstring, (b) alphabetized `__all__` containing exactly `{"DockerInDockerClient"}`, (c) module docstring cites ADR-0001 / ADR-0004 / ADR-0006 by number, (d) imports limited to stdlib + `docker` + `structlog` + `codegenie.{sandbox.contract, sandbox.errors, sandbox.logging, sandbox.registry, sandbox.did._uuid7, types.identifiers}` (NO `subprocess`, NO `yaml`, NO LLM SDKs, NO `iptables`), (e) every event name in `client.py` references an `EVENT_*` constant from `sandbox.logging` (no bare strings), (f) `backend` and `gate_isolation_class` Literal values appear in source as module-level `Final` constants, NOT as inline string literals scattered across method bodies, (g) `RunId` constructor appears at the run-id generation site.

17. **(test-quality — harden) Registry round-trip not actually asserted.** Draft AC-2 says "Registered via `@register_sandbox_backend('docker_in_docker')`" — no test calls `get_backend(...)`. Resolution: AC-REG-1 pins `from codegenie.sandbox.registry import get_backend; assert get_backend('docker_in_docker') is DockerInDockerClient` (identity, not just isinstance — catches subclass-substitution mutations). AC-REG-2 pins `isinstance(DockerInDockerClient(), SandboxClient) is True` (Protocol structural conformance per ADR-0006).

18. **(test-quality — harden) `health()` strace SYS_PTRACE probe expensive + uncached.** Outline step 4 prescribes a one-off `--cap-add SYS_PTRACE` strace probe — creates+removes a container per `health()` call. `SandboxHealthProbe` (S3-06) calls health once at startup, but Phase 6 LangGraph nodes may call `health()` repeatedly during retry-loop diagnostics. Resolution: AC-HEALTH-CACHE-1 + AC-HEALTH-CACHE-2 pin memoization on `self._strace_probe_result: bool | None` (one-shot per instance lifetime); the test pattern `client.health(); client.health()` asserts exactly one container-create call for the probe. AC-HEALTH-CACHE-3 pins ≤ 5 s `health()` wall-clock budget against a mocked daemon (matches arch §perf envelope for `SandboxHealthProbe`).

19. **(test-quality — harden) `logs_dir` path discipline unpinned.** Draft hardcodes `Path(".codegenie/sandbox/runs") / run_id` — relative to CWD, no idempotency, no race protection. Resolution: AC-LOGS-1 pins `logs_dir = (Path.cwd() / ".codegenie/sandbox/runs" / str(run_id)).resolve()`; `mkdir(parents=True, exist_ok=True)` (idempotent under retries — without `exist_ok=True`, a retry on the same `run_id` raises `FileExistsError`); log files opened with `mode="wb"` (binary, byte-faithful per AC-STREAM-1).

20. **(test-quality — harden) `container.wait()` `Error` key handling untested.** Real Docker returns `{"StatusCode": int, "Error": {...}}` on daemon-side failure. Draft fixture has `{"StatusCode": 0}` only. Resolution: AC-WAIT-1 pins that `wait_result.get("Error")` non-None raises `SandboxBackendError("wait_failed", details=...)` — the exit_code is unsafe to trust on a daemon-side error.

21. **(test-quality — harden) `docker_url` non-None branch untested.** AC-1 says constructor accepts `docker_url: str | None = None`; draft TDD never exercises the non-None path. Resolution: AC-DI-3 pins `test_docker_url_routes_to_dockerclient_constructor` — `client = DockerInDockerClient(docker_url="tcp://remote:2376")` calls `DockerClient(base_url="tcp://remote:2376")` (asserted via `docker_factory` injection), NOT `docker.from_env()`.

22. **(consistency — harden) Coverage floor wording absent.** Phase-5 standard is "line ≥ 95% AND branch ≥ 90%". Draft AC-9 says "`pytest` pass" only. Resolution: AC-COV-1 + AC-COV-2 add explicit coverage floors against `src/codegenie/sandbox/did/`.

23. **(patterns — harden, surfaced as Note) `docker.from_env` Hexagonal port.** S3-01 set the precedent (`filter_fn`, `host_env_source`, `catalog` constructor ports). S3-02 introduces `docker_factory: Callable[[], DockerClient] = docker.from_env` — the second concrete consumer; rule-of-three reached when Firecracker (S6-01) ships its own `firecracker_client_factory`. The monkeypatch pattern in tests then collapses to direct DI: `DockerInDockerClient(docker_factory=lambda: fake_docker)`.

24. **(patterns — harden, surfaced as Note) Resource-handle lifecycle.** `docker.from_env()` opens a Unix-socket / HTTP connection. The class never closes it. Single-shot CLI use doesn't observe a leak; Phase 6 Temporal long-running workers may. Note for the implementer: when a leak is observed (Phase 6+), promote `DockerInDockerClient` to context manager (`__enter__`/`__exit__` calling `self._client.close()`). For S3-02, leave open — Rule 2.

25. **(coverage — harden) `spec.copy_in` non-empty handling needs explicit no-op + WARNING.** Block #5 above pins fail-loud for `network/egress/copy_out`. But `copy_in` is the bytes-into-sandbox path S3-04 will USE — silent ignore here is acceptable IFF a one-time `sandbox.did.copy_in.deferred` WARNING fires; otherwise S3-04's integration test only catches the gap after the fact. Resolution: AC-SPEC-DEFER-3 — `copy_in != []` → WARNING event + ignore; S3-04 owns the actual `docker cp` plumbing.

26. **(patterns — nit, fixed) Warning ID namespace.** Draft uses `"buildx_missing"`, `"daemon_unreachable"`, `"strace_ptrace_missing"` (bare). CLAUDE.md "Warning + error IDs match `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`". Renamed to `sandbox.buildx_missing`, `sandbox.daemon_unreachable`, `sandbox.strace_ptrace_missing`. AC-HEALTH-4 pins the namespace regex.

27. **(consistency — nit, fixed) `pytest-mock` not in dev deps.** AC-7 says "Unit tests use `pytest-mock` to stub the Docker SDK". `pytest-mock` is NOT in `pyproject.toml [dependency-groups.dev]`. Codebase convention is `unittest.mock` + `monkeypatch` (e.g., `tests/unit/test_audit_anchors.py`). Resolution: replaced `pytest-mock` references with `unittest.mock` + `monkeypatch` patterns; the `docker_factory` Hexagonal port (#23) makes most monkeypatches unnecessary.

**No `RESCUE`-tier findings.** The most structural weakness was finding #1 (phantom class); it cascaded to dead-port hidden state and was patchable by elimination + S3-01-style DI-port replacement. The story remains shippable; downstream stories (S3-03 build chokepoint, S3-04 copy-out/timeout/OOM, S3-07 integration) inherit a clean hand-off — every deferred concern is explicitly fail-loud-or-warn at this layer.

**Two Stage-3 research findings consumed inline:**

- **uuid7 source:** Stdlib `uuid.uuid7()` is in Python 3.14+ (PEP 9562 / RFC 9562 standardization shipped 2024). CI matrix is 3.11 × 3.12. Three PyPI alternatives differ in API + maintenance: `uuid7` (pure Python), `uuid_utils` (Rust-backed), `uuid_extensions` (unmaintained — the draft's choice). Resolution: vendor a 20-LOC `codegenie/sandbox/did/_uuid7.py` helper using stdlib `secrets` + `time.time_ns()` per RFC 9562 §5.7 — keeps dep surface minimal, ADR-0001 fence-closure unchanged, no PyPI version-pin churn. Direct unit test of the helper covers version nibble (=7), length (36 incl. hyphens), charset (hex), monotonicity (`uuid7() < uuid7()` over `time.time_ns()` advance).

- **Docker SDK type stubs:** `docker-stubs` does NOT exist on PyPI (draft's "vendor a `py.typed` shim if missing" was the right instinct but the wrong package name). The community stubs are `types-docker` (`python-docker-stubs` repo). `docker>=7` itself ships partial inline annotations. Resolution: dev dep `types-docker`; quarantine remaining `Any` behind a small typed shim `codegenie/sandbox/did/_docker_types.py` (`TypedDict` for `ContainerKwargs`, `LogChunk` alias). `mypy --strict src/codegenie/sandbox/did/` passes against the shim, not against the Docker SDK directly.

Full validation report at [`_validation/S3-02-did-client-sdk-core.md`](_validation/S3-02-did-client-sdk-core.md).

## Context

`DockerInDockerClient` is the macOS/Linux-default `SandboxClient` implementation. This story lands the SDK-driven happy path only — create + start + exec + stdout/stderr capture + inspect + remove, returning a populated `SandboxRun`. The build subprocess chokepoint (`docker buildx`) and the iptables network policy chokepoint are intentionally split into S3-03 because they are the only `subprocess` callers in the entire `sandbox/` tree and the AST fence test (`tests/schema/test_no_subprocess_outside_build_chokepoint.py`) only tolerates them in their dedicated files. Copy-out, OOM, SIGKILL/timeout handling are S3-04. Real-daemon integration is S3-07. The `SandboxHealthProbe` Phase-1-style wrapper is S3-06. Keep this story narrow.

This story is also the **second concrete consumer** of the Hexagonal-port + functional-core / imperative-shell pattern that S3-01 HARDENED introduced. The third concrete consumer — Firecracker (S6-01) — completes the rule-of-three and locks the convention; in this story we elevate two pattern findings from Notes to ACs precisely because S3-01 + S3-02 + S6-01 form the three-consumer set.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — DockerInDockerClient` (lines ~486–493) — public surface, internal structure (SDK only for create/cp/start/exec/inspect/remove; subprocess only in `did/build.py`), dependencies, performance envelope, failure-mode mapping (`docker.errors.APIError` → `SandboxBackendError`; `ImageNotFound` → `SandboxImageUnavailable`; OOM/timeout deferred to S3-04).
  - `../phase-arch-design.md §Logical view` (line ~78, ~175) — class diagram for `DockerInDockerClient` implementing `SandboxClient`.
  - `../phase-arch-design.md §Process view` (lines ~357–363, ~437) — sequence diagram: `docker create + cp + start + exec`.
  - `../phase-arch-design.md §Physical view` (line ~322) — workload container annotated `shared_kernel`.
  - `../phase-arch-design.md §Data model — SandboxSpec / SandboxRun / SandboxHealth` (lines ~640–683) — frozen field set, Literal values, cross-field validators.
  - `../phase-arch-design.md §Edge cases #1, #2, #9, #19` (lines ~853, ~854, ~861, ~871) — daemon-dies-mid-build, image-unpullable, strace-SYS_PTRACE-missing-on-macOS, policy-digest-missing.
  - `../phase-arch-design.md §Goals 5 and 6` (lines ~20–21) — DinD macOS default; `gate_isolation_class="shared_kernel"` permanent annotation.
- **Phase ADRs:**
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — `client.py` MUST NOT `import subprocess`; SDK only. Enforced by AST fence `tests/schema/test_no_subprocess_outside_build_chokepoint.py` AND by local `tests/sandbox/did/test_client_purity.py`.
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — every `SandboxRun` from this backend carries `gate_isolation_class="shared_kernel"`, `backend="docker_in_docker"` — byte-exact Literal spellings.
  - `../ADRs/0006-protocol-vs-abc-convention.md` — `DockerInDockerClient` satisfies `SandboxClient` Protocol structurally (`runtime_checkable`), no inheritance, no shared default behavior.
- **Source design:**
  - `../final-design.md §Synthesis ledger — Sandbox stack default macOS row` — DinD on macOS is the explicit pick.
- **High-level impl:**
  - `../High-level-impl.md §Step 3 — Features delivered` — bullet 1.
- **Existing code (HARDENED ancestors):**
  - `src/codegenie/sandbox/contract.py` (from S1-02 HARDENED) — `SandboxClient` Protocol (`@runtime_checkable`, two methods: `execute(spec) -> SandboxRun`, `health() -> SandboxHealth`), `SandboxSpec`, `SandboxRun` (13 fields including `microvm_seconds`/`image_pull_bytes`/`build_cache_hit`/`trace_path`/`timed_out`/`killed_by_oom`), `SandboxHealth` (6 fields including `confidence` + `detected_at`), `CopyInEntry`. `RunId = NewType("RunId", str)` lives in `codegenie.types.identifiers` (S1-02 Validation note #7). Canonical Literal spellings `Literal["docker_in_docker", "firecracker"]` and `Literal["shared_kernel", "microvm"]` (S1-02 AC-4).
  - `src/codegenie/sandbox/errors.py` (from S1-01 HARDENED) — `SandboxBackendError` (+ `reason: Literal[...]` discriminator per AC-ERR-1 this story), `SandboxImageUnavailable` (distinct subclass).
  - `src/codegenie/sandbox/logging.py` (from S1-01 HARDENED) — canonical event-name table; append-only policy; sorted `__all__`.
  - `src/codegenie/sandbox/registry.py` (from S1-05 HARDENED) — `@register_sandbox_backend("name")` decorator factory; `sandbox_backend_registry: SandboxBackendRegistry`; `get_backend(name) -> SandboxClient`; structural validation at decoration time pins `inspect.signature(cls.execute).parameters == {"self", "spec"}` and `cls.health == {"self"}`.
  - `src/codegenie/types/identifiers.py` — `RunId = NewType("RunId", str)`.
  - `src/codegenie/adapters/protocols.py` — `@runtime_checkable` Protocol precedent (DepGraphAdapter, etc.).
- **Prior HARDENED reports (consult before implementing):**
  - `_validation/S1-02-sandbox-contract-protocol-models.md` — canonical Literal spellings, RunId NewType, cross-field validators, `extra="forbid"`/`frozen=True` discipline.
  - `_validation/S1-05-registries-and-env-allowlist.md` — `env_allowlist.filter` is a **module-level function** (no `EnvAllowlist` class).
  - `_validation/S3-01-spec-builder-canonical-hash.md` — Hexagonal DI ports (constructor kwargs with production defaults), functional-core/imperative-shell concrete-helper pattern, module-purity AST walker, banned-substring field-name walker.
- **External docs:**
  - https://docker-py.readthedocs.io/en/stable/containers.html — `client.containers.create`, `.start`, `.exec_run`, `.wait`, `.remove`.
  - https://docker-py.readthedocs.io/en/stable/api.html — low-level `APIClient` for streaming logs.
  - https://datatracker.ietf.org/doc/rfc9562/ — UUIDv7 spec §5.7 (for the vendored `_uuid7.py` helper).
  - https://docs.pydantic.dev/2.0/usage/models/#model_copy — `model_copy(update=…)` on frozen models.

## Goal

Ship a Docker-SDK-only `execute()` path that creates an ephemeral container from a `SandboxSpec`, runs `cmd`, captures stdout/stderr to `logs_dir` byte-faithfully, and returns a `SandboxRun` populated with the **full 13-field S1-02-HARDENED contract** — `backend="docker_in_docker"`, `gate_isolation_class="shared_kernel"`, `RunId`-wrapped `run_id`, timezone-aware `started_at`/`ended_at`, computed `duration_ms`, `exit_code` from `container.wait()`, and explicit stub values for the seven fields S3-04+ later stories populate (`microvm_seconds=0.0`, `image_pull_bytes=0`, `build_cache_hit=False`, `trace_path=None`, `copy_out_root=logs_dir.parent / "copy_out"`, `timed_out=False`, `killed_by_oom=False`). Plus `health()` returning a fully-populated `SandboxHealth` with cached macOS strace probe.

## Acceptance criteria

### A. Public surface and module purity

- [ ] **AC-API-1** `src/codegenie/sandbox/did/__init__.py` exists; `src/codegenie/sandbox/did/client.py` exists; `from codegenie.sandbox.did.client import DockerInDockerClient` succeeds with no side effects (idempotent on second import: `id(mod_first) == id(mod_second)`).
- [ ] **AC-API-2** `set(codegenie.sandbox.did.client.__all__) == {"DockerInDockerClient"}`. `_build_container_kwargs`, `_construct_sandbox_run`, `_wrap_api_error`, `_demux_chunks`, `_BACKEND_NAME`, `_GATE_ISOLATION_CLASS` are module-private (single leading underscore) and NOT in `__all__`.
- [ ] **AC-API-3** Module docstring cites ADR-0001, ADR-0004, and ADR-0006 by number.
- [ ] **AC-API-4** `from __future__ import annotations` is the first non-docstring statement.
- [ ] **AC-API-5** `client.py` declares `_BACKEND_NAME: Final = "docker_in_docker"` and `_GATE_ISOLATION_CLASS: Final = "shared_kernel"` as module-level constants — single source of truth for the canonical Literal spellings. Method bodies reference the constants, never the string literals directly (AC-PURE-6 enforces).

### B. Constructor — Hexagonal DI ports

- [ ] **AC-DI-1** `DockerInDockerClient.__init__(self, *, docker_url: str | None = None, docker_factory: Callable[[str | None], DockerClient] = _default_docker_factory) -> None` — two keyword-only parameters. **No `EnvAllowlist` reference anywhere in `did/client.py`** (S1-05 ships no such class; env filtering is `SandboxSpecBuilder`'s job per S3-01).
- [ ] **AC-DI-2** `docker_factory` defaults to a module-private factory `_default_docker_factory(url: str | None) -> DockerClient` that returns `docker.from_env()` when `url is None`, else `docker.DockerClient(base_url=url)`. The factory is the Hexagonal port S3-01 set the precedent for; production code uses the default; tests inject `docker_factory=lambda url: fake_docker`.
- [ ] **AC-DI-3** `test_docker_url_routes_to_dockerclient_constructor` — `DockerInDockerClient(docker_url="tcp://remote:2376", docker_factory=spy)` calls the spy with the URL exactly once; with `docker_url=None` the spy is called with `None`.
- [ ] **AC-DI-4** `__init__` performs no I/O beyond the `docker_factory` invocation: no env reads, no fs reads, no network probes. Asserted via a test that constructs the client with `docker_factory=lambda url: pytest.fail("must not be called eagerly")` — construction succeeds iff the factory is lazy. (If the production default does eager-construct, the test injects `docker_factory=Mock()` and asserts call count == 1.)
- [ ] **AC-DI-5** `typing.get_type_hints(DockerInDockerClient.__init__)["docker_factory"]` is `collections.abc.Callable[[str | None], docker.DockerClient]`.

### C. `execute()` — SDK happy path

- [ ] **AC-EXEC-1** `execute(self, spec: SandboxSpec) -> SandboxRun` — single positional + keyword arg per S1-05 HARDENED AC-BR-3 (`{"self", "spec"}` set-equality on `inspect.signature(cls.execute).parameters`).
- [ ] **AC-EXEC-2** Calls (in order) `_validate_spec_supported(spec)` (raises per §G), `run_id = RunId(uuid7())`, `logs_dir = _ensure_logs_dir(run_id)` (idempotent), `kwargs = _build_container_kwargs(spec)`, `container = self._client.containers.create(**kwargs)`, captures `started_at = datetime.now(timezone.utc)`, `container.start()`, drains `container.logs(stream=True, stdout=True, stderr=True, demux=True)` via `_demux_chunks` into `stdout.log` + `stderr.log` byte-faithfully (binary mode), `result = container.wait()`, captures `ended_at = datetime.now(timezone.utc)`, validates `result.get("Error") is None` (else raises `SandboxBackendError("wait_failed", …)` per AC-WAIT-1), constructs and returns `_construct_sandbox_run(...)`.
- [ ] **AC-EXEC-3** A `try / finally` brackets the section starting at `containers.create(...)`. The `finally` calls `container.remove(force=True)` exactly once; if `container` was never assigned (create raised), no remove call attempted. Cleanup failure semantics per §F.
- [ ] **AC-EXEC-4** `network_mode="none"` is passed to `containers.create` (S3-02 stub; S3-03 widens for `network="scoped"`). Asserted via `fake_docker.containers.create.assert_called_once()`; positional+keyword args inspected via `call_args.kwargs["network_mode"] == "none"`.

### D. `SandboxRun` field coverage — S1-02 HARDENED contract

The returned `SandboxRun` carries every required field from S1-02 with the values below. AC numbering tracks the S1-02 field order.

- [ ] **AC-RUN-FIELDS-1** `run_id: RunId` — `RunId(uuid7_str)`. Test: `isinstance(run.run_id, str) and len(run.run_id) == 36 and run.run_id.count('-') == 4 and int(run.run_id.replace('-','')[12], 16) == 7` (UUIDv7 version nibble).
- [ ] **AC-RUN-FIELDS-2** `spec: SandboxSpec` — identity-equal to the input spec: `run.spec is spec_passed_to_execute`.
- [ ] **AC-RUN-FIELDS-3** `backend == "docker_in_docker"` — byte-exact (`_BACKEND_NAME` constant).
- [ ] **AC-RUN-FIELDS-4** `gate_isolation_class == "shared_kernel"` — byte-exact (`_GATE_ISOLATION_CLASS` constant).
- [ ] **AC-RUN-FIELDS-5** `started_at: datetime` — `tzinfo=timezone.utc`, captured immediately before `container.start()`.
- [ ] **AC-RUN-FIELDS-6** `ended_at: datetime` — `tzinfo=timezone.utc`, captured immediately after `container.wait()`. Cross-field invariant `ended_at >= started_at` per S1-02 AC-7c.
- [ ] **AC-RUN-FIELDS-7** `exit_code: int` — `int(result["StatusCode"])`. Test parametrized over `[0, 1, 127, -1]` (last verifies the int conversion path, since Docker returns int natively).
- [ ] **AC-RUN-FIELDS-8** `duration_ms: int` — `int((ended_at - started_at).total_seconds() * 1000)`; computed inside `_construct_sandbox_run` (single source of truth; not measured separately).
- [ ] **AC-RUN-FIELDS-9** `microvm_seconds: float == 0.0` — DinD has no microvm; Phase 13 cost ledger keys on this; field is pinned to `0.0` forever for `backend=="docker_in_docker"`.
- [ ] **AC-RUN-FIELDS-10** `image_pull_bytes: int == 0` — S3-04 will populate by parsing pull-event stream.
- [ ] **AC-RUN-FIELDS-11** `build_cache_hit: bool is False` — `True` requires Phase-7 distroless build-cache hit; never `True` for S3-02.
- [ ] **AC-RUN-FIELDS-12** `logs_dir: Path` — equals `(Path.cwd() / ".codegenie/sandbox/runs" / str(run_id)).resolve()`.
- [ ] **AC-RUN-FIELDS-13** `trace_path: Path | None is None` — S4-03 owns trace capture; `None` is the S3-02 stub.
- [ ] **AC-RUN-FIELDS-14** `copy_out_root: Path` — equals `logs_dir.parent / "copy_out" / str(run_id)`; the directory is created (empty) at the end of `execute()` for forward-compat with S3-04's `docker cp` step.
- [ ] **AC-RUN-FIELDS-15** `timed_out: bool is False` — S3-04 owns SIGKILL/timeout; S3-02 returns `False` always.
- [ ] **AC-RUN-FIELDS-16** `killed_by_oom: bool is False` — S3-04 owns OOM detection via `docker inspect State.OOMKilled`; S3-02 returns `False` always.
- [ ] **AC-RUN-FIELDS-17** Cross-field invariant `not (timed_out and killed_by_oom)` per S1-02 AC-7d holds trivially (both `False`).

### E. Canonical Literal spellings — positively pinned

- [ ] **AC-CANONICAL-1** `_BACKEND_NAME == "docker_in_docker"` byte-exact in `client.py` source (AST walk: `ast.parse(source).body` contains `ast.Assign(targets=[ast.Name(id="_BACKEND_NAME")], value=ast.Constant(value="docker_in_docker"))`).
- [ ] **AC-CANONICAL-2** `_GATE_ISOLATION_CLASS == "shared_kernel"` byte-exact in `client.py` source via the same AST walk.
- [ ] **AC-CANONICAL-3** `_BACKEND_NAME in typing.get_args(SandboxRun.__annotations__["backend"])` (consistency with S1-02's closed Literal).
- [ ] **AC-CANONICAL-4** Method bodies in `client.py` reference `_BACKEND_NAME` and `_GATE_ISOLATION_CLASS` constants by name; no inline string literal `"docker_in_docker"` or `"shared_kernel"` appears anywhere outside the two module-level `Final` assignments (AST walk over all `ast.FunctionDef.body` nodes finds zero `ast.Constant(value="docker_in_docker")` and zero `ast.Constant(value="shared_kernel")`).

### F. Error wrapping — closed reason discriminator

- [ ] **AC-ERR-1** `SandboxBackendError` (extended by this story if needed; otherwise the S1-01 HARDENED class) carries `reason: Literal["create_failed", "start_failed", "stream_failed", "wait_failed", "remove_failed"]` — closed set, byte-exact. (`image_unavailable` lives on the subclass `SandboxImageUnavailable` per AC-IMG-1.)
- [ ] **AC-ERR-2** Per-phase exception mapping table (asserted by parametrized test):

  | Phase | Docker exception | Wrapped as | `reason` |
  |---|---|---|---|
  | create | `docker.errors.ImageNotFound` | `SandboxImageUnavailable` | `"image_unavailable"` |
  | create | `docker.errors.APIError` | `SandboxBackendError` | `"create_failed"` |
  | start | `docker.errors.APIError` | `SandboxBackendError` | `"start_failed"` |
  | logs (stream) | `docker.errors.APIError` | `SandboxBackendError` | `"stream_failed"` |
  | wait | `docker.errors.APIError` | `SandboxBackendError` | `"wait_failed"` |
  | wait (Error key in result) | — | `SandboxBackendError` | `"wait_failed"` |
  | remove (in finally) | `docker.errors.APIError` | logged at WARNING; **NOT re-raised** | `"remove_failed"` (event payload) |
- [ ] **AC-ERR-3** `_wrap_api_error(err, *, where) -> SandboxBackendError | SandboxImageUnavailable` is the **single** call site that builds the wrapped exception. Pure function. Asserted via direct unit test parametrized over `(exception_class, where) → expected_wrap_class + expected_reason`.
- [ ] **AC-APIERR-1** Parametrized test `test_api_error_at_<phase>_wrapped` covers `phase ∈ {create, start, logs, wait}`: `fake_docker.containers.create / fake_container.start / fake_container.logs / fake_container.wait` `.side_effect = docker.errors.APIError("daemon down")` raises `SandboxBackendError` with the right `reason` value AND the wrapped exception's `__cause__` is the original `APIError` (chained, not swallowed).
- [ ] **AC-IMG-1** `docker.errors.ImageNotFound("digest pull failed")` during `containers.create` raises `SandboxImageUnavailable` (distinct from generic `SandboxBackendError` — operator sees the digest issue clearly). `isinstance(exc, SandboxBackendError) is True` (subclass relationship preserved).
- [ ] **AC-WAIT-1** A `container.wait()` return value `{"StatusCode": 0, "Error": {"Message": "...", "Code": 0}}` raises `SandboxBackendError("wait_failed", details={"docker_error": "..."})` — `exit_code` is unsafe to trust on a daemon-side error.

### G. Spec-feature fail-loud + deferred-warning policy

- [ ] **AC-SPEC-DEFER-1** `spec.network == "scoped"` raises `NotImplementedError("sandbox.did: spec.network=='scoped' deferred to S3-03 (iptables network policy)")` — fail-loud. Parametrized test asserts the exception message string contains `"S3-03"`.
- [ ] **AC-SPEC-DEFER-2** `spec.egress_allowlist != []` raises `NotImplementedError("sandbox.did: spec.egress_allowlist deferred to S3-03")`.
- [ ] **AC-SPEC-DEFER-3** `spec.copy_in != []` is accepted but emits a one-time `EVENT_SANDBOX_DID_COPY_IN_DEFERRED` WARNING event with `{run_id, copy_in_count}` (S3-04 will replace this with actual `docker cp` plumbing). NOT a `NotImplementedError` — copy_in is the bytes-in path S3-04 will USE, so silent acceptance + warning is the right migration story.
- [ ] **AC-SPEC-DEFER-4** `spec.copy_out != []` raises `NotImplementedError("sandbox.did: spec.copy_out deferred to S3-04")`.
- [ ] **AC-SPEC-DEFER-5** `spec.enable_trace is True` emits a one-time `EVENT_SANDBOX_DID_TRACE_DEFERRED` WARNING (`{run_id, label}`) and sets `trace_path=None` on the `SandboxRun`; NOT a `NotImplementedError` (trace is S4-03's collector concern; the client just ignores the flag at this layer per arch §Component design line 493).
- [ ] **AC-SPEC-DEFER-6** `spec.time_budget_seconds != DEFAULT_TIME_BUDGET` (where `DEFAULT_TIME_BUDGET` is the S1-02 model default if any, else `600`) is accepted but emits a one-time `EVENT_SANDBOX_DID_TIMEOUT_DEFERRED` WARNING (`{run_id, time_budget_seconds}`); `container.wait()` is NOT given a `timeout=` kwarg in S3-02 (SIGKILL/timeout is S3-04). Note for the implementer: if a test hangs on a real daemon, that's expected pre-S3-04.
- [ ] **AC-SPEC-DEFER-7** All six fail-loud/warning paths are covered by a single parametrized test `test_unsupported_spec_features_have_explicit_handling` indexed by field name → expected behavior (raise | warn).

### H. `health()` — fully populated `SandboxHealth`

- [ ] **AC-HEALTH-1** `health(self) -> SandboxHealth` returns a model with all six S1-02-required fields populated on every code path, including the success path: `backend="docker_in_docker"`, `reachable: bool`, `confidence: Literal["high","medium","low"]`, `reasons: list[str]`, `warnings: list[str]`, `detected_at = datetime.now(timezone.utc)`.
- [ ] **AC-HEALTH-2** Confidence mapping table (asserted by parametrized test):

  | Scenario | `reachable` | `confidence` | `reasons` | `warnings` |
  |---|---|---|---|---|
  | Daemon ping fails | `False` | `"high"` | `["sandbox.daemon_unreachable"]` | `[]` |
  | Ping OK; buildx absent in `api.version().Components` | `True` | `"medium"` | `[]` | `["sandbox.buildx_missing"]` |
  | Ping OK; macOS strace probe denied (Darwin only) | `True` | `"medium"` | `[]` | `["sandbox.strace_ptrace_missing"]` |
  | Ping OK; buildx absent AND strace denied (Darwin) | `True` | `"low"` | `[]` | `["sandbox.buildx_missing", "sandbox.strace_ptrace_missing"]` (sorted) |
  | Ping OK; all checks pass | `True` | `"high"` | `[]` | `[]` |
- [ ] **AC-HEALTH-3** `reasons` and `warnings` are alphabetically sorted before return (catches set→list nondeterminism in audit diffs). Asserted by hypothesis property test: any health probe outcome's `reasons == sorted(reasons)` and `warnings == sorted(warnings)`.
- [ ] **AC-HEALTH-4** Every reason/warning string matches the CLAUDE.md namespace regex `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` (e.g., `sandbox.daemon_unreachable`, `sandbox.buildx_missing`, `sandbox.strace_ptrace_missing`). Module-level constants for each warning ID are appended to `sandbox/logging.py` (`WARNING_SANDBOX_BUILDX_MISSING: Final[str] = "sandbox.buildx_missing"` etc., consistent with the S1-01 event-constant pattern).
- [ ] **AC-HEALTH-5** `detected_at` is timezone-aware UTC on every return path.
- [ ] **AC-HEALTH-CACHE-1** The macOS strace SYS_PTRACE probe — which spawns a real container — runs **at most once per `DockerInDockerClient` instance lifetime**. Result memoized on `self._strace_probe_result: bool | None` (initialized to `None`). Asserted via `client.health(); client.health()` causing exactly **one** `containers.create` call attributable to the probe (Linux: the probe is skipped entirely; Mac: called once).
- [ ] **AC-HEALTH-CACHE-2** On Linux (`platform.system() != "Darwin"`) the strace probe is skipped entirely — `warnings` never contains `"sandbox.strace_ptrace_missing"`; the `self._strace_probe_result` cache remains `None`. CI on Linux MUST NOT flake on this.
- [ ] **AC-HEALTH-CACHE-3** `health()` wall-clock budget is ≤ 5 s against a mocked daemon (matches arch §SandboxHealthProbe perf envelope). Asserted via `time.monotonic()` bracket inside the test.

### I. Cleanup discipline

- [ ] **AC-CLEANUP-1** `container.remove(force=True)` runs **exactly once** in the `finally` block on every path that reached `containers.create` successfully. Asserted via `fake_container.remove.assert_called_once_with(force=True)`.
- [ ] **AC-CLEANUP-2** Cleanup-side `docker.errors.APIError` raised by `container.remove` is caught and logged at WARNING with the structured event `EVENT_SANDBOX_DID_CLEANUP_FAILED`, fields `{run_id, error_class, error_message_truncated_512}`. The cleanup exception is **NOT re-raised**.
- [ ] **AC-CLEANUP-3** When `execute()` is mid-error (some other exception in flight) AND `remove` ALSO raises, the **primary exception** is propagated. No `raise … from cleanup_err` clobbering. Asserted via `pytest.raises(SandboxBackendError) as exc; assert exc.value.reason == "start_failed"` (the primary failure), NOT `"remove_failed"`.
- [ ] **AC-CLEANUP-4** When `execute()` succeeded (`SandboxRun` was constructed) AND `remove` raises in the finally, `execute()` STILL returns the `SandboxRun` — the run happened; cleanup is best-effort. Asserted via fixture where `fake_container.remove.side_effect = APIError("daemon stale")` AND happy-path log/wait fixtures; `run = client.execute(spec); assert run.exit_code == 0; assert <WARNING log captured>`.
- [ ] **AC-CLEANUP-5** Parametrized cleanup test grid covers `phase ∈ {start, logs, wait}` × `exception_class ∈ {RuntimeError, docker.errors.APIError}` × `cleanup_outcome ∈ {success, raises_APIError}` — 12 cells.

### J. Log streaming — byte-faithful demux

- [ ] **AC-STREAM-1** `_demux_chunks(chunks: Iterable[tuple[bytes | None, bytes | None]]) -> Iterator[tuple[bytes, bytes]]` is a pure helper that normalizes `None` halves to empty bytes (`b""`); never writes literal `b"None"`.
- [ ] **AC-STREAM-2** Log-stream loop writes the `(stdout, stderr)` halves of each tuple to `stdout.log` / `stderr.log` byte-faithfully, in binary mode (`open(..., "wb")`). Parametrized test grid with chunks: `[(b"a", None), (None, b"b"), (b"c", b"d"), (b"", b""), (b"x"*4096, b"y"*4096)]` asserts `stdout.log.read_bytes() == b"acx" + b"x"*4096` and `stderr.log.read_bytes() == b"bd" + b"y"*4096`.
- [ ] **AC-STREAM-3** Hypothesis property test `@given(st.lists(st.tuples(st.binary(max_size=64), st.binary(max_size=64))))` asserts byte-faithful round-trip: `stdout.log == b"".join(stdout for (stdout, _) in normalized_chunks)`; `stderr.log == b"".join(stderr for (_, stderr) in normalized_chunks)`. `min_size=0` allowed (empty chunks must work).

### K. `logs_dir` and `copy_out_root` discipline

- [ ] **AC-LOGS-1** `logs_dir = (Path.cwd() / ".codegenie/sandbox/runs" / str(run_id)).resolve()`. `mkdir(parents=True, exist_ok=True)` — idempotent under retries. Asserted via running `execute()` twice with the same `run_id` (via `docker_factory` injection + a UUID7 monkeypatch) — second run does not raise `FileExistsError`.
- [ ] **AC-LOGS-2** `stdout.log` and `stderr.log` open with `mode="wb"`. Test asserts byte-faithfulness on a chunk `(b"\x00\xff\n", b"\x01\x02")` (non-text bytes).
- [ ] **AC-LOGS-3** `copy_out_root = logs_dir.parent / "copy_out" / str(run_id)` created (empty dir) by end of `execute()` — forward-compat with S3-04's `docker cp` extraction path.

### L. Registry round-trip + Protocol conformance

- [ ] **AC-REG-1** `DockerInDockerClient` is registered via `@register_sandbox_backend("docker_in_docker")` from `codegenie.sandbox.registry` at module import time. Test: `from codegenie.sandbox.registry import sandbox_backend_registry; assert sandbox_backend_registry.get("docker_in_docker") is DockerInDockerClient` (identity equality, NOT just isinstance — catches subclass substitution).
- [ ] **AC-REG-2** Protocol structural conformance per ADR-0006: `from codegenie.sandbox.contract import SandboxClient; assert isinstance(DockerInDockerClient(docker_factory=lambda url: MagicMock()), SandboxClient)` returns `True` (`runtime_checkable` Protocol; S1-02 made it `@runtime_checkable`).
- [ ] **AC-REG-3** `inspect.signature(DockerInDockerClient.execute).parameters` keys equal `{"self", "spec"}`; `inspect.signature(DockerInDockerClient.health).parameters` keys equal `{"self"}` — matches S1-05 HARDENED AC-BR-3/-4 structural validation.

### M. uuid7 vendored helper

- [ ] **AC-UUID-1** `src/codegenie/sandbox/did/_uuid7.py` exists, ≤ 25 lines of code (excluding docstring/imports), pure stdlib (`secrets`, `time`, `os`), implements RFC 9562 §5.7 UUIDv7. Exports `uuid7() -> str`.
- [ ] **AC-UUID-2** Direct unit test `tests/sandbox/did/test_uuid7.py`:
  - `re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", uuid7())` — format.
  - `int(uuid7().replace("-", "")[12], 16) == 7` — version nibble.
  - `int(uuid7().replace("-", "")[16], 16) & 0xC == 0x8` — variant bits (`10xx`).
- [ ] **AC-UUID-3** Monotonicity property: under `time.time_ns()` advancing, `uuid7()` values are strictly increasing **across separate `time.time_ns()` calls** (within a single ns tick, ordering is best-effort — RFC 9562 doesn't require strict monotonicity inside one ns). Test uses `freezegun` (added to dev deps if not present) or a `monkeypatch.setattr("time.time_ns", iter([1, 2, 3, ...]).__next__)` pattern.
- [ ] **AC-UUID-4** The helper is consumed at exactly one site: `client.py:execute` does `run_id = RunId(uuid7())`. Single-call-site discipline matches S1-05 HARDENED's name-registry delegation pattern.

### N. Dependencies

- [ ] **AC-DEP-1** `pyproject.toml [project] dependencies` adds `docker>=7,<8`. Runtime dep — `docker` is the only Python SDK for the Docker daemon and is the ADR-0001 SDK chokepoint.
- [ ] **AC-DEP-2** `pyproject.toml [dependency-groups.dev]` adds `types-docker` (community stubs; `docker-stubs` does NOT exist on PyPI). And `freezegun` if not present (for AC-UUID-3 monotonicity test).
- [ ] **AC-DEP-3** `make fence` (the `tests/unit/test_pyproject_fence.py` ADR-0002 LLM-SDK closure test) stays green after the dep additions — `docker` is NOT in `FORBIDDEN_LLM_SDKS` (`{anthropic, langgraph, openai, langchain, transformers}`).

### O. Module purity (AST walker)

- [ ] **AC-PURE-1** `tests/sandbox/did/test_client_purity.py` (TYPE_CHECKING-aware) walks `client.py` AST and asserts:
- [ ] **AC-PURE-2** `from __future__ import annotations` is the first statement after the module docstring.
- [ ] **AC-PURE-3** `__all__ == ["DockerInDockerClient"]` (alphabetized, single entry).
- [ ] **AC-PURE-4** Module docstring contains the strings `"ADR-0001"`, `"ADR-0004"`, `"ADR-0006"` (number citations).
- [ ] **AC-PURE-5** Top-level imports are restricted to: stdlib (`datetime`, `pathlib`, `platform`, `typing`, `collections.abc`) + `docker` + `structlog` + `codegenie.sandbox.contract` + `codegenie.sandbox.errors` + `codegenie.sandbox.logging` + `codegenie.sandbox.registry` + `codegenie.sandbox.did._uuid7` + `codegenie.sandbox.did._docker_types` (the TypedDict shim) + `codegenie.types.identifiers`. **Forbidden:** `subprocess`, `os.system`, `pickle`, `yaml`/`pyyaml`, any LLM SDK in `FORBIDDEN_LLM_SDKS`, any `iptables`/`shellout` module.
- [ ] **AC-PURE-6** Every structlog `.bind` / event emission references an `EVENT_*` constant from `codegenie.sandbox.logging` — zero bare-string event names in `client.py`. AST walk asserts `ast.Call(func=…, keywords=[keyword(arg='event', value=ast.Constant(...))])` matches NEVER (every event name flows through a `Name` reference, not a `Constant`).
- [ ] **AC-PURE-7** No `Any` annotation leaks past the Docker SDK boundary: the `_docker_types.py` TypedDict shim contains the only `Any` references in the `did/` subpackage. AST walk over `client.py` finds zero `ast.Name(id="Any")` in annotation contexts.

### P. Event-name discipline (append-only to S1-01 table)

- [ ] **AC-EVT-1** Six new `Final[str]` constants appended to `src/codegenie/sandbox/logging.py` (alphabetized in `__all__`):
  - `EVENT_SANDBOX_DID_EXECUTE_STARTED = "sandbox.did.execute.started"`
  - `EVENT_SANDBOX_DID_EXECUTE_COMPLETED = "sandbox.did.execute.completed"`
  - `EVENT_SANDBOX_DID_EXECUTE_FAILED = "sandbox.did.execute.failed"`
  - `EVENT_SANDBOX_DID_HEALTH_CHECKED = "sandbox.did.health.checked"`
  - `EVENT_SANDBOX_DID_CLEANUP_FAILED = "sandbox.did.cleanup.failed"`
  - `EVENT_SANDBOX_DID_TRACE_DEFERRED = "sandbox.did.trace.deferred"`
  - `EVENT_SANDBOX_DID_COPY_IN_DEFERRED = "sandbox.did.copy_in.deferred"`
  - `EVENT_SANDBOX_DID_TIMEOUT_DEFERRED = "sandbox.did.timeout.deferred"`
  - (Plus three warning ID constants per AC-HEALTH-4.)
- [ ] **AC-EVT-2** Structured field set per event (asserted via `structlog.testing.capture_logs()` parametrized test):
  - `execute.started`: `{run_id, label, backend}`
  - `execute.completed`: `{run_id, label, backend, exit_code, duration_ms}`
  - `execute.failed`: `{run_id, label, backend, where, error_class}` (`where` is the phase per AC-ERR-2 table)
  - `health.checked`: `{backend, reachable, confidence}`
  - `cleanup.failed`: `{run_id, error_class, error_message_truncated_512}`
  - `trace.deferred`, `copy_in.deferred`, `timeout.deferred`: `{run_id, label}` plus deferred-feature-specific fields.
- [ ] **AC-EVT-3** Verbs match S1-01 convention (`started`/`completed`/`failed`, NOT `start`/`done`/`error`).

### Q. Functional core / imperative shell

- [ ] **AC-FCS-1** Four pure helpers defined at module level (`_build_container_kwargs`, `_construct_sandbox_run`, `_wrap_api_error`, `_demux_chunks`); plus the impure helper `_ensure_logs_dir(run_id) -> Path` which does the `mkdir`. Each helper is independently unit-tested in `tests/sandbox/did/test_client_helpers.py`.
- [ ] **AC-FCS-2** `_build_container_kwargs(spec: SandboxSpec) -> ContainerKwargs` is pure: same input → same output; no side effects; no env reads. Unit test parametrized over `[minimal_spec, full_spec]` × asserts output dict has exact keys `{"image", "command", "environment", "network_mode", "mem_limit", "pids_limit"}`.
- [ ] **AC-FCS-3** `_construct_sandbox_run(*, run_id, spec, started_at, ended_at, exit_code, logs_dir, copy_out_root) -> SandboxRun` is pure; stamps `backend=_BACKEND_NAME`, `gate_isolation_class=_GATE_ISOLATION_CLASS` once, and the seven stub fields per §D. Unit test asserts a minimal-spec call returns a `SandboxRun` byte-equal via `model_dump_json` to a golden fixture.
- [ ] **AC-FCS-4** `_wrap_api_error(err: docker.errors.APIError | docker.errors.ImageNotFound, *, where: Literal["create","start","logs","wait"]) -> SandboxBackendError | SandboxImageUnavailable` is pure; mapping per AC-ERR-2 table; unit-test parametrized over the table.
- [ ] **AC-FCS-5** `_demux_chunks` is pure; covered by AC-STREAM-1..AC-STREAM-3.

### R. structlog observability

- [ ] **AC-LOG-1** `structlog.contextvars.bind_contextvars(run_id=run_id)` is called once at the top of `execute()`; all events inside the call inherit `run_id`.
- [ ] **AC-LOG-2** `structlog.testing.capture_logs()` parametrized test covers: (a) happy path emits `execute.started` + `execute.completed`; (b) APIError-at-each-phase emits `execute.failed` with the right `where`; (c) cleanup-failure emits `cleanup.failed`; (d) deferred-feature warning paths emit their respective events exactly once each.

### S. Coverage + tooling gates

- [ ] **AC-COV-1** `src/codegenie/sandbox/did/` coverage: line ≥ 95% AND branch ≥ 90% (Phase-5 standard, matches S1-02..S1-06, S3-01).
- [ ] **AC-COV-2** `ruff check src/codegenie/sandbox/did/ tests/sandbox/did/`, `ruff format --check src/codegenie/sandbox/did/ tests/sandbox/did/`, `mypy --strict src/codegenie/sandbox/did/`, `pytest tests/sandbox/did/ tests/sandbox/test_uuid7.py` all pass.
- [ ] **AC-COV-3** AST fence tests stay green: `tests/schema/test_no_subprocess_outside_build_chokepoint.py` (no `subprocess` import in `client.py`), `tests/schema/test_no_llm_imports_in_sandbox.py` (no LLM SDK in `client.py` or `_docker_types.py` or `_uuid7.py`).
- [ ] **AC-COV-4** TDD plan's red tests exist, are committed, and are now green.

## Implementation outline

1. **Create the dependency surface first.**
   - Edit `pyproject.toml`: add `docker>=7,<8` to `[project] dependencies`; add `types-docker` and (if missing) `freezegun` to `[dependency-groups.dev]`. Run `uv pip install -e ".[dev]"` to refresh the lock.
   - Run `make fence` to confirm the LLM-SDK closure is undisturbed.

2. **Vendor `_uuid7.py`.** Create `src/codegenie/sandbox/did/_uuid7.py` per AC-UUID-1 — RFC 9562 §5.7 implementation using `time.time_ns()` for the 48-bit Unix-ts-ms prefix, `secrets.randbits` for the 12-bit `rand_a` and 62-bit `rand_b`, manual nibble-set for version `0b0111` and variant `0b10`. Format with `uuid.UUID(int=…).__str__()` or hand-format the dashes. Land the unit test in `tests/sandbox/did/test_uuid7.py` first (red), then the helper (green), then refactor for clarity (≤ 25 LOC).

3. **Land the TypedDict shim `_docker_types.py`.** Tiny module exporting `ContainerKwargs: TypedDict` with the six keys from AC-FCS-2 and `LogChunk = tuple[bytes | None, bytes | None]`. Quarantines the Docker SDK's untyped surface behind a thin typed boundary.

4. **Land `client.py`.**
   - Module docstring citing ADR-0001 / ADR-0004 / ADR-0006.
   - `from __future__ import annotations` (AC-API-4).
   - Imports: per AC-PURE-5 (NO subprocess).
   - Module-level `Final` constants `_BACKEND_NAME`, `_GATE_ISOLATION_CLASS` (AC-API-5).
   - Pure helpers in this order (each independently unit-testable): `_build_container_kwargs`, `_demux_chunks`, `_wrap_api_error`, `_construct_sandbox_run`.
   - Impure helpers: `_default_docker_factory`, `_ensure_logs_dir`.
   - `@register_sandbox_backend("docker_in_docker")` decorator above the class.
   - `class DockerInDockerClient:`
     - `__init__(self, *, docker_url: str | None = None, docker_factory: Callable[[str | None], DockerClient] = _default_docker_factory) -> None`: stores `self._client = docker_factory(docker_url)`; `self._strace_probe_result: bool | None = None`.
     - `def execute(self, spec: SandboxSpec) -> SandboxRun:` orchestrates the SDK calls per AC-EXEC-2; thin shell delegating to pure helpers.
     - `def health(self) -> SandboxHealth:` per AC-HEALTH-1..AC-HEALTH-5 + AC-HEALTH-CACHE-1..AC-HEALTH-CACHE-3.
     - `def _validate_spec_supported(self, spec) -> None:` raises per §G fail-loud table; emits the warning events for `copy_in`/`enable_trace`/`time_budget_seconds`.
     - `def _probe_strace_darwin_cached(self) -> bool:` returns the cached result; if `None`, runs the one-off `--cap-add SYS_PTRACE` strace probe via SDK only (still no subprocess); writes result to `self._strace_probe_result`.

5. **structlog event constants.** Append the eight `EVENT_*` + three `WARNING_*` constants to `src/codegenie/sandbox/logging.py` per AC-EVT-1 and AC-HEALTH-4. Sort `__all__`. Bump the value-equality test in `tests/sandbox/test_logging_constants.py` (or whatever S1-01 named it).

6. **Tests in red-first order.**
   - `tests/sandbox/did/test_uuid7.py` (AC-UUID-2..AC-UUID-3)
   - `tests/sandbox/did/test_client_purity.py` (AC-PURE-1..AC-PURE-7)
   - `tests/sandbox/did/test_client_helpers.py` (AC-FCS-1..AC-FCS-5)
   - `tests/sandbox/did/test_client_core.py` (AC-EXEC-* + AC-RUN-FIELDS-* + AC-ERR-* + AC-APIERR-* + AC-IMG-* + AC-WAIT-* + AC-CLEANUP-* + AC-STREAM-* + AC-LOGS-* + AC-CANONICAL-* + AC-REG-* + AC-SPEC-DEFER-* + AC-DI-* + AC-LOG-*)
   - `tests/sandbox/did/test_client_health.py` (AC-HEALTH-* + AC-HEALTH-CACHE-*)

7. **Refactor pass.** Type hints, docstrings (each pure helper carries a one-liner; `execute()` carries a paragraph citing ADR-0001 + ADR-0004). Verify `mypy --strict` clean. Verify coverage floor.

## TDD plan — red / green / refactor

The TDD plan now spans **five test files**. Each table cell maps a test to one or more ACs; the implementer writes the test red, makes it pass, then refactors.

### Red — write the failing tests first

#### File 1 — `tests/sandbox/did/test_uuid7.py`

```python
"""UUIDv7 vendored helper — AC-UUID-1..AC-UUID-4."""
from __future__ import annotations

import re
import time

from codegenie.sandbox.did._uuid7 import uuid7


def test_uuid7_format_and_version_nibble():
    """RFC 9562: 36-char string, 4 hyphens, version nibble == 7, variant bits == 10xx."""
    value = uuid7()
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value)
    hex_only = value.replace("-", "")
    assert int(hex_only[12], 16) == 7
    assert int(hex_only[16], 16) & 0xC == 0x8


def test_uuid7_monotonic_under_increasing_time_ns(monkeypatch):
    """Two calls across two time_ns ticks are strictly increasing (lexicographic)."""
    ticks = iter([1_700_000_000_000_000_000, 1_700_000_000_000_001_000])
    monkeypatch.setattr("time.time_ns", lambda: next(ticks))
    a = uuid7()
    b = uuid7()
    assert a < b, f"{a} should be < {b}"
```

#### File 2 — `tests/sandbox/did/test_client_purity.py`

```python
"""Module-purity AST walker for did/client.py — AC-PURE-1..AC-PURE-7."""
from __future__ import annotations

import ast
import pathlib

import codegenie.sandbox.did.client as client_mod

CLIENT_PATH = pathlib.Path(client_mod.__file__)
SOURCE = CLIENT_PATH.read_text()
TREE = ast.parse(SOURCE)

ALLOWED_IMPORT_PREFIXES = {
    "datetime", "pathlib", "platform", "typing", "collections.abc",
    "docker", "structlog",
    "codegenie.sandbox.contract", "codegenie.sandbox.errors",
    "codegenie.sandbox.logging", "codegenie.sandbox.registry",
    "codegenie.sandbox.did._uuid7", "codegenie.sandbox.did._docker_types",
    "codegenie.types.identifiers",
}

FORBIDDEN_PREFIXES = {"subprocess", "os.system", "pickle", "yaml", "pyyaml",
                       "anthropic", "langgraph", "openai", "langchain", "transformers"}


def test_future_annotations_first_statement():
    # docstring is body[0]; future-import must be body[1]
    second = TREE.body[1]
    assert isinstance(second, ast.ImportFrom)
    assert second.module == "__future__"
    assert any(a.name == "annotations" for a in second.names)


def test_all_is_alphabetized_single_entry():
    assert client_mod.__all__ == ["DockerInDockerClient"]


def test_module_docstring_cites_adrs():
    doc = ast.get_docstring(TREE) or ""
    for adr in ("ADR-0001", "ADR-0004", "ADR-0006"):
        assert adr in doc, f"module docstring must cite {adr}"


def test_imports_within_allowlist():
    for node in ast.walk(TREE):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = node.module if isinstance(node, ast.ImportFrom) else node.names[0].name
            assert not any(mod.startswith(f) for f in FORBIDDEN_PREFIXES), f"forbidden import: {mod}"
            assert any(mod == p or mod.startswith(p + ".") for p in ALLOWED_IMPORT_PREFIXES), f"unexpected import: {mod}"


def test_no_inline_canonical_literals():
    """AC-CANONICAL-4 — backend/isolation strings appear ONLY in two module-level Final assigns."""
    backend_constants = 0
    isolation_constants = 0
    for node in ast.walk(TREE):
        if isinstance(node, ast.Constant) and node.value == "docker_in_docker":
            backend_constants += 1
        if isinstance(node, ast.Constant) and node.value == "shared_kernel":
            isolation_constants += 1
    assert backend_constants == 1, "expected exactly one 'docker_in_docker' literal (in _BACKEND_NAME Final assign)"
    assert isolation_constants == 1, "expected exactly one 'shared_kernel' literal (in _GATE_ISOLATION_CLASS Final assign)"


def test_no_bare_event_strings():
    """AC-PURE-6 — every structlog event name flows through an EVENT_* Name reference."""
    # Walk every Call; check no keyword(arg='event', value=Constant) leaks
    for node in ast.walk(TREE):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "event":
                    assert not isinstance(kw.value, ast.Constant), \
                        f"bare 'event=' string at line {node.lineno}; use EVENT_* constant"
```

#### File 3 — `tests/sandbox/did/test_client_helpers.py`

Pure-helper unit tests for `_build_container_kwargs`, `_construct_sandbox_run`, `_wrap_api_error`, `_demux_chunks`. ≤ 25 tests; each parametrized where applicable. Property test on `_demux_chunks` via hypothesis per AC-STREAM-3.

#### File 4 — `tests/sandbox/did/test_client_core.py`

```python
"""DinD client core — execute() happy path, error wrapping, cleanup, registry. AC-EXEC, AC-RUN-FIELDS, AC-ERR, AC-APIERR, AC-IMG, AC-WAIT, AC-CLEANUP, AC-STREAM (integration), AC-LOGS, AC-CANONICAL, AC-REG, AC-SPEC-DEFER, AC-DI, AC-LOG."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from unittest.mock import MagicMock, call
from typing import Iterator

import docker.errors
import pytest
import structlog

from codegenie.sandbox.contract import SandboxRun, SandboxSpec, CopyInEntry
from codegenie.sandbox.did.client import DockerInDockerClient, _BACKEND_NAME, _GATE_ISOLATION_CLASS
from codegenie.sandbox.errors import SandboxBackendError, SandboxImageUnavailable
from codegenie.sandbox.registry import sandbox_backend_registry
from codegenie.sandbox import logging as sb_logging
from codegenie.types.identifiers import RunId, SandboxSpecHash


def _spec(**overrides) -> SandboxSpec:
    base = dict(
        base_image="cgr.dev/chainguard/node@sha256:" + "d" * 64,
        copy_in=[], env={"PATH": "/usr/bin"}, cmd=["true"],
        network="none", egress_allowlist=[], enable_trace=False,
        time_budget_seconds=600, memory_limit_mib=256, pids_limit=64,
        copy_out=[], label="t.attempt1",
        sandbox_spec_hash=SandboxSpecHash("0" * 32),
    )
    base.update(overrides)
    return SandboxSpec(**base)


@pytest.fixture
def fake_container():
    c = MagicMock()
    c.wait.return_value = {"StatusCode": 0}
    c.logs.return_value = iter([(b"hello\n", b""), (b"", b"oops\n")])
    return c


@pytest.fixture
def fake_docker_factory(fake_container):
    fake = MagicMock()
    fake.containers.create.return_value = fake_container
    fake.ping.return_value = True
    fake.api.version.return_value = {"Components": [{"Name": "Engine"}, {"Name": "buildx"}]}
    return lambda url: fake


@pytest.fixture
def client(fake_docker_factory, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return DockerInDockerClient(docker_factory=fake_docker_factory)


def test_canonical_literal_constants_byte_exact():
    """AC-CANONICAL-1/-2."""
    assert _BACKEND_NAME == "docker_in_docker"
    assert _GATE_ISOLATION_CLASS == "shared_kernel"


def test_registry_round_trip():
    """AC-REG-1."""
    assert sandbox_backend_registry.get("docker_in_docker") is DockerInDockerClient


def test_protocol_conformance(fake_docker_factory):
    """AC-REG-2 — DockerInDockerClient satisfies SandboxClient Protocol structurally."""
    from codegenie.sandbox.contract import SandboxClient
    instance = DockerInDockerClient(docker_factory=fake_docker_factory)
    assert isinstance(instance, SandboxClient)


def test_execute_returns_full_sandbox_run_field_set(client, fake_container, tmp_path):
    """AC-RUN-FIELDS-1..-17 — every required field carries its S3-02 stub value."""
    spec = _spec()
    run = client.execute(spec)
    assert isinstance(run, SandboxRun)
    # Identity / canonical literals (AC-RUN-FIELDS-2/-3/-4)
    assert run.spec is spec
    assert run.backend == "docker_in_docker"
    assert run.gate_isolation_class == "shared_kernel"
    # RunId shape (AC-RUN-FIELDS-1)
    assert isinstance(run.run_id, str) and len(run.run_id) == 36
    assert int(run.run_id.replace("-", "")[12], 16) == 7
    # Timestamps (AC-RUN-FIELDS-5/-6, AC-TIME-1)
    assert run.started_at.tzinfo is timezone.utc
    assert run.ended_at.tzinfo is timezone.utc
    assert run.ended_at >= run.started_at
    # Exit + duration (AC-RUN-FIELDS-7/-8)
    assert run.exit_code == 0
    assert run.duration_ms == int((run.ended_at - run.started_at).total_seconds() * 1000)
    # Stub field pins (AC-RUN-FIELDS-9..-16)
    assert run.microvm_seconds == 0.0
    assert run.image_pull_bytes == 0
    assert run.build_cache_hit is False
    assert run.trace_path is None
    assert run.timed_out is False
    assert run.killed_by_oom is False
    # logs_dir + copy_out_root discipline (AC-LOGS-1, AC-RUN-FIELDS-12/-14)
    assert run.logs_dir == (Path.cwd() / ".codegenie/sandbox/runs" / str(run.run_id)).resolve()
    assert run.copy_out_root == run.logs_dir.parent / "copy_out" / str(run.run_id)
    assert run.copy_out_root.is_dir()
    # Log content (AC-STREAM-2 integration)
    assert (run.logs_dir / "stdout.log").read_bytes() == b"hello\n"
    assert (run.logs_dir / "stderr.log").read_bytes() == b"oops\n"
    # Cleanup happened
    fake_container.remove.assert_called_once_with(force=True)
    # network_mode pinned (AC-EXEC-4)
    create_kwargs = client._client.containers.create.call_args.kwargs
    assert create_kwargs["network_mode"] == "none"


@pytest.mark.parametrize("phase,exc_class,expected_wrap,expected_reason", [
    ("create", docker.errors.APIError, SandboxBackendError, "create_failed"),
    ("create", docker.errors.ImageNotFound, SandboxImageUnavailable, "image_unavailable"),
    ("start",  docker.errors.APIError, SandboxBackendError, "start_failed"),
    ("logs",   docker.errors.APIError, SandboxBackendError, "stream_failed"),
    ("wait",   docker.errors.APIError, SandboxBackendError, "wait_failed"),
])
def test_api_error_at_phase_wrapped(client, fake_container, phase, exc_class, expected_wrap, expected_reason):
    """AC-APIERR-1 + AC-IMG-1 + AC-ERR-2 — each phase's docker error maps to the right wrap+reason."""
    err = exc_class("boom") if exc_class is docker.errors.APIError else exc_class("boom", explanation="boom")
    target = {"create": "containers.create", "start": "start", "logs": "logs", "wait": "wait"}[phase]
    if phase == "create":
        client._client.containers.create.side_effect = err
    else:
        getattr(fake_container, phase).side_effect = err
    with pytest.raises(expected_wrap) as exc_info:
        client.execute(_spec())
    assert exc_info.value.reason == expected_reason
    assert exc_info.value.__cause__ is err  # exception chained


def test_wait_with_error_key_wraps_as_backend_error(client, fake_container):
    """AC-WAIT-1 — daemon-side wait failure not silently passed as exit_code=0."""
    fake_container.wait.return_value = {"StatusCode": 0, "Error": {"Message": "OOM", "Code": 0}}
    with pytest.raises(SandboxBackendError) as exc_info:
        client.execute(_spec())
    assert exc_info.value.reason == "wait_failed"


@pytest.mark.parametrize("phase", ["start", "logs", "wait"])
@pytest.mark.parametrize("primary_exc", [RuntimeError, docker.errors.APIError])
@pytest.mark.parametrize("cleanup_raises", [False, True])
def test_cleanup_grid(client, fake_container, phase, primary_exc, cleanup_raises):
    """AC-CLEANUP-1..-5 — 12-cell parametrized grid."""
    primary = primary_exc("boom") if primary_exc is RuntimeError else primary_exc("boom")
    getattr(fake_container, phase).side_effect = primary
    if cleanup_raises:
        fake_container.remove.side_effect = docker.errors.APIError("daemon stale on remove")
    with pytest.raises(BaseException) as exc_info:
        client.execute(_spec())
    # Primary always wins (AC-CLEANUP-3)
    assert not isinstance(exc_info.value, type(fake_container.remove.side_effect)) if cleanup_raises else True
    # remove called exactly once with force=True (AC-CLEANUP-1)
    fake_container.remove.assert_called_once_with(force=True)


def test_cleanup_failure_on_success_path_returns_sandbox_run(client, fake_container):
    """AC-CLEANUP-4 — cleanup failure after successful run still returns the SandboxRun."""
    fake_container.remove.side_effect = docker.errors.APIError("daemon stale")
    with structlog.testing.capture_logs() as logs:
        run = client.execute(_spec())
    assert run.exit_code == 0
    assert any(e["event"] == sb_logging.EVENT_SANDBOX_DID_CLEANUP_FAILED for e in logs)


@pytest.mark.parametrize("field,value,expects_raise,expects_event", [
    ("network", "scoped", "NotImplementedError", None),
    ("egress_allowlist", ["registry.npmjs.org"], "NotImplementedError", None),
    ("copy_out", ["dist/**"], "NotImplementedError", None),
    ("copy_in", [{"src": "/tmp", "dst": "/work", "mode": "rw"}], None, sb_logging.EVENT_SANDBOX_DID_COPY_IN_DEFERRED),
    ("enable_trace", True, None, sb_logging.EVENT_SANDBOX_DID_TRACE_DEFERRED),
    ("time_budget_seconds", 1200, None, sb_logging.EVENT_SANDBOX_DID_TIMEOUT_DEFERRED),
])
def test_unsupported_spec_features_have_explicit_handling(client, field, value, expects_raise, expects_event):
    """AC-SPEC-DEFER-1..-7."""
    overrides = {field: value}
    if field == "copy_in":
        overrides["copy_in"] = [CopyInEntry(src=Path("/tmp"), dst=PurePosixPath("/work"), mode="rw")]
    if expects_raise:
        with pytest.raises(NotImplementedError) as exc:
            client.execute(_spec(**overrides))
        # message names a forward owner
        assert any(ref in str(exc.value) for ref in ("S3-03", "S3-04"))
    else:
        with structlog.testing.capture_logs() as logs:
            client.execute(_spec(**overrides))
        assert any(e["event"] == expects_event for e in logs)


def test_docker_url_routes_to_dockerclient_constructor():
    """AC-DI-3."""
    spy = MagicMock(side_effect=lambda url: MagicMock())
    DockerInDockerClient(docker_url="tcp://remote:2376", docker_factory=spy)
    spy.assert_called_once_with("tcp://remote:2376")


def test_constructor_does_not_eagerly_call_docker_factory_with_lazy_spy():
    """AC-DI-4 — construction calls docker_factory once, no other I/O.

    NB: this asserts the factory is called once at construction, not zero times — production
    DefaultDockerFactory is eager. The diagnostic value is that no OTHER I/O happens.
    """
    spy = MagicMock(side_effect=lambda url: MagicMock())
    DockerInDockerClient(docker_factory=spy)
    spy.assert_called_once_with(None)


def test_structlog_events_emitted_with_required_fields(client):
    """AC-EVT-2 + AC-LOG-2 — execute.started/completed emit with stable field set."""
    with structlog.testing.capture_logs() as logs:
        client.execute(_spec())
    started = next(e for e in logs if e["event"] == sb_logging.EVENT_SANDBOX_DID_EXECUTE_STARTED)
    completed = next(e for e in logs if e["event"] == sb_logging.EVENT_SANDBOX_DID_EXECUTE_COMPLETED)
    for key in ("run_id", "label", "backend"):
        assert key in started and key in completed
    for key in ("exit_code", "duration_ms"):
        assert key in completed
```

(Additional tests for byte-faithful log streaming with `\x00\xff` bytes — AC-LOGS-2; idempotency under retry — AC-LOGS-1; hypothesis property test on `_demux_chunks` — moved to `test_client_helpers.py`.)

#### File 5 — `tests/sandbox/did/test_client_health.py`

```python
"""DinD client health() — confidence mapping, strace cache, Linux skip. AC-HEALTH-1..-5, AC-HEALTH-CACHE-1..-3."""
from __future__ import annotations

import platform
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from codegenie.sandbox.did.client import DockerInDockerClient


@pytest.mark.parametrize("scenario,ping_ok,buildx_present,strace_ok,expected", [
    ("daemon_down",     False, True,  True,  ("False", "high", [], [])),
    ("buildx_missing",  True,  False, True,  ("True",  "medium", [], ["sandbox.buildx_missing"])),
    ("strace_missing_darwin", True, True, False, ("True", "medium", [], ["sandbox.strace_ptrace_missing"])),
    ("both_missing_darwin",   True, False, False, ("True", "low",  [], ["sandbox.buildx_missing", "sandbox.strace_ptrace_missing"])),
    ("all_ok",          True,  True,  True,  ("True",  "high", [], [])),
])
def test_health_confidence_mapping(monkeypatch, scenario, ping_ok, buildx_present, strace_ok, expected):
    """AC-HEALTH-2 — exhaustive confidence table."""
    monkeypatch.setattr("platform.system", lambda: "Darwin")  # force Darwin for strace branches
    # build a fake docker client whose ping/version reflect the scenario
    fake = MagicMock()
    if ping_ok:
        fake.ping.return_value = True
    else:
        fake.ping.side_effect = Exception("connection refused")
    fake.api.version.return_value = {
        "Components": ([{"Name": "Engine"}] + ([{"Name": "buildx"}] if buildx_present else []))
    }
    # strace probe: we mock the probe method directly to assert caching behavior elsewhere
    client = DockerInDockerClient(docker_factory=lambda url: fake)
    monkeypatch.setattr(client, "_probe_strace_darwin_cached", lambda: strace_ok)
    health = client.health()
    expected_reachable, expected_confidence, expected_reasons, expected_warnings = expected
    assert str(health.reachable) == expected_reachable
    assert health.confidence == expected_confidence
    assert health.reasons == expected_reasons
    assert health.warnings == expected_warnings
    # AC-HEALTH-1/-5
    assert health.backend == "docker_in_docker"
    assert health.detected_at.tzinfo is timezone.utc


def test_strace_probe_cached_across_calls(monkeypatch):
    """AC-HEALTH-CACHE-1 — strace probe runs at most once per instance."""
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    fake = MagicMock()
    fake.ping.return_value = True
    fake.api.version.return_value = {"Components": [{"Name": "Engine"}, {"Name": "buildx"}]}
    # Real strace probe path is gated; assert by mocking the SDK call the probe makes
    client = DockerInDockerClient(docker_factory=lambda url: fake)
    client.health()
    client.health()
    # The probe creates and removes one container; assert the create call count is at most 1
    assert fake.containers.create.call_count <= 1


def test_strace_probe_skipped_on_linux(monkeypatch):
    """AC-HEALTH-CACHE-2 — Linux never spawns the strace probe container."""
    monkeypatch.setattr("platform.system", lambda: "Linux")
    fake = MagicMock()
    fake.ping.return_value = True
    fake.api.version.return_value = {"Components": [{"Name": "Engine"}, {"Name": "buildx"}]}
    client = DockerInDockerClient(docker_factory=lambda url: fake)
    health = client.health()
    assert "sandbox.strace_ptrace_missing" not in health.warnings
    assert fake.containers.create.call_count == 0


def test_health_under_five_seconds(monkeypatch):
    """AC-HEALTH-CACHE-3."""
    monkeypatch.setattr("platform.system", lambda: "Linux")
    fake = MagicMock()
    fake.ping.return_value = True
    fake.api.version.return_value = {"Components": [{"Name": "Engine"}, {"Name": "buildx"}]}
    client = DockerInDockerClient(docker_factory=lambda url: fake)
    t0 = time.monotonic()
    client.health()
    assert time.monotonic() - t0 < 5.0
```

### Green — make it pass

Implement the SDK calls + pure helpers in the order of the test files (uuid7 first, purity walker next, pure helpers, then core, then health). Wrap `docker.errors.APIError` and `ImageNotFound` per the AC-ERR-2 table; use `try/finally` for `container.remove(force=True)` with the cleanup-failure log path; write logs to disk with `mode="wb"`; emit every event through the `sandbox/logging.py` `EVENT_*` constants.

### Refactor — clean up

- Confirm every literal `"docker_in_docker"` / `"shared_kernel"` collapses to the two `Final` module constants (purity walker enforces).
- Confirm every `event=` keyword in structlog calls references a `Name` (not a `Constant`).
- Confirm `mypy --strict src/codegenie/sandbox/did/` passes — quarantine any residual Docker SDK `Any` behind `_docker_types.py`.
- Confirm coverage line ≥ 95% AND branch ≥ 90%.
- Docstring on each pure helper (one-liner); docstring on `execute()` (paragraph citing ADR-0001 + ADR-0004).

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` | Add `docker>=7,<8` runtime dep; add `types-docker` (and `freezegun` if missing) to dev deps (AC-DEP-1, AC-DEP-2). |
| `src/codegenie/sandbox/did/__init__.py` | New subpackage marker. |
| `src/codegenie/sandbox/did/client.py` | The SDK-driven `execute` + `health`, pure helpers, registry registration. |
| `src/codegenie/sandbox/did/_uuid7.py` | Vendored RFC-9562 UUIDv7 helper (≤ 25 LOC). |
| `src/codegenie/sandbox/did/_docker_types.py` | `TypedDict` shim for `ContainerKwargs` + `LogChunk` alias. |
| `src/codegenie/sandbox/logging.py` | **Append-only:** eight new `EVENT_SANDBOX_DID_*` constants + three `WARNING_SANDBOX_*` constants; bump `__all__`. |
| `tests/sandbox/did/__init__.py` | New test subpackage marker. |
| `tests/sandbox/did/test_uuid7.py` | AC-UUID-2..AC-UUID-3. |
| `tests/sandbox/did/test_client_purity.py` | AC-PURE-1..AC-PURE-7. |
| `tests/sandbox/did/test_client_helpers.py` | AC-FCS-1..AC-FCS-5 + AC-STREAM property test. |
| `tests/sandbox/did/test_client_core.py` | AC-EXEC, AC-RUN-FIELDS, AC-ERR, AC-APIERR, AC-IMG, AC-WAIT, AC-CLEANUP, AC-STREAM (integration), AC-LOGS, AC-CANONICAL, AC-REG, AC-SPEC-DEFER, AC-DI, AC-LOG. |
| `tests/sandbox/did/test_client_health.py` | AC-HEALTH, AC-HEALTH-CACHE. |
| `tests/sandbox/test_logging_constants.py` | Existing S1-01 value-equality test — extended with the eight new event constants + three warning constants. |

## Out of scope

- `docker buildx build` — S3-03 owns the build chokepoint and the iptables network-policy chokepoint (the only two `subprocess` call sites under `sandbox/`).
- `network=="scoped"` widening + iptables rules — S3-03.
- `docker cp` copy-out, OOM detection (`docker inspect State.OOMKilled`), SIGKILL/timeout enforcement (`container.wait(timeout=…)`) — S3-04. S3-02 surfaces `time_budget_seconds`/`copy_out` as fail-loud-or-warn per §G but does NOT enforce.
- Real Docker daemon integration test — S3-07.
- `SandboxHealthProbe` Phase-1-style wrapper consuming `client.health()` — S3-06.
- Trace capture (`strace -f` inside the container; `trace_path` populated) — S4-03.
- Phase-7 distroless base-image-content probe (uses `SandboxRun` but doesn't change DinD) — Phase 7.

## Notes for the implementer

- **No `subprocess` import.** The AST fence test will fail PR immediately if you add one. If you find yourself wanting `subprocess.run("docker", ...)`, you're in the wrong file — that belongs in `did/build.py` (S3-03). The local purity walker (`test_client_purity.py`) defends in depth.
- **Single source of truth for canonical literals.** `_BACKEND_NAME` and `_GATE_ISOLATION_CLASS` are module-level `Final` constants; every method body references them. The purity walker counts string-literal occurrences and will fail if the constants are bypassed. Firecracker (S6-01) will declare its own pair.
- **`network_mode="none"` is the S3-02 stub**; S3-03 owns the `spec.network == "scoped"` branch. S3-02 fails loud on `"scoped"` per AC-SPEC-DEFER-1 — do NOT silently downgrade.
- **`gate_isolation_class="shared_kernel"` is a string literal on this backend, always — no conditional.** Firecracker's client (S6-01) sets `"microvm"`.
- **Don't try to detect `strace_ptrace_missing` on Linux**; only emit the warning on Darwin (AC-HEALTH-CACHE-2). CI on Linux MUST NOT flake on this.
- **Cleanup in `finally` must catch its own exceptions and log; never let a `remove` failure overwrite the real error.** AC-CLEANUP-3 enforces.
- **`container.logs(stream=True, demux=True)` is the only way to separate stdout/stderr cleanly from the SDK; the alternative `attach()` is unreliable on Docker Desktop.** Pinned in AC-EXEC-2.
- **Pattern lineage — Hexagonal DI ports.** S3-01 introduced the convention (constructor kwargs with production defaults — `catalog`, `filter_fn`, `host_env_source`); S3-02 is the second concrete consumer (`docker_factory`); when S6-01 lands the third (`firecracker_client_factory`), the rule-of-three is reached and the convention is canonical. If S6-01 or later adds a fourth concrete factory port, consider extracting a shared `ClientFactory` Protocol — until then a simple `Callable` typing is correct (Rule 2).
- **Pattern lineage — Functional-core / imperative-shell.** S3-01 set the pattern (`_canonical_blake3`, `_deep_merge`, `_assemble_partial_spec`, `_compute_hash_input` pure helpers + thin shell); S3-02 follows it (`_build_container_kwargs`, `_construct_sandbox_run`, `_wrap_api_error`, `_demux_chunks`). Two consumers; rule-of-three reached at S6-01.
- **Pattern lineage — resource-handle lifecycle.** `self._client` is never `.close()`'d. Single-shot CLI usage doesn't observe a leak. If Phase 6 Temporal long-running workers accumulate socket connections, promote `DockerInDockerClient` to a context manager (`__enter__`/`__exit__` calling `self._client.close()`); for S3-02, Rule 2 wins.
- **uuid7 source.** Stdlib `uuid.uuid7()` arrives in Python 3.14; the CI matrix is 3.11 × 3.12. Vendor a 20-LOC RFC-9562 helper rather than adding a PyPI dependency — keeps the `make fence` LLM-SDK closure surface unchanged. Single call site in `client.py` per AC-UUID-4.
- **Docker SDK type stubs.** `docker-stubs` does NOT exist on PyPI (community package is `types-docker`). `docker>=7` ships partial inline annotations; quarantine the rest behind `_docker_types.py` (TypedDict for `ContainerKwargs`, alias for `LogChunk`) so `mypy --strict src/codegenie/sandbox/did/` passes against the shim, not against the Docker SDK directly.
- **Sealed error-reason discriminator.** `SandboxBackendError.reason` is a closed `Literal["create_failed","start_failed","stream_failed","wait_failed","remove_failed"]` per AC-ERR-1; Phase 13 cost ledger and Phase 11 evidence bundle key on it. If S3-03 or later phases need to extend, that's a Phase 5 ADR amendment, NOT a silent string addition.
- **Event-name verb convention.** S1-01 HARDENED uses `STARTED/COMPLETED/FAILED`. The draft's `start/done/error` was inconsistent — corrected per AC-EVT-3.
