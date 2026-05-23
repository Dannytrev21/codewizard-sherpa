# Story S3-03 — DinD `build.py` subprocess chokepoint + `network_policy.py` iptables chokepoint

**Step:** Step 3 — Implement DinD backend + SandboxSpecBuilder + SandboxHealthProbe
**Status:** Ready (HARDENED 2026-05-23)
**Effort:** M
**Depends on:** S1-01 (`sandbox/errors.py` — `SandboxBackendError` closed `reason` Literal; `sandbox/logging.py` event-name table + append-only policy + sorted `__all__`), S1-02 (`SandboxSpec` / `CopyInEntry` frozen models + `network: Literal["none","scoped"]` + `egress_allowlist: list[str]` + `RunId` NewType), S3-02 (`DockerInDockerClient` SDK core + `_build_container_kwargs` pure helper + `_default_docker_factory` Hexagonal port — both EDITED additively here; AC-SPEC-DEFER-1 / AC-SPEC-DEFER-2 / AC-EXEC-4 widened)
**ADRs honored:** ADR-0001 (two subprocess chokepoints in `sandbox/did/` — `build.py` for `docker buildx`, `network_policy.py` for `iptables` — enforced by AST fence + `forbidden-patterns` pre-commit), ADR-0004 (DinD macOS default; iptables runs inside Docker Desktop's embedded Linux VM on macOS — host-side on Linux), ADR-0006 (`apply` / `revert` are plain callables, not a Protocol — third backend reaches rule-of-three; collapse to Protocol then), ADR-0014 (frozen Pydantic models with `extra="forbid"` for `BuildResult` / `AppliedPolicy` — banned-substring field-name walker applies)

## Validation notes (2026-05-23, phase-story-validator)

**Verdict:** HARDENED. The draft correctly identified the two-chokepoint deliverables (`docker buildx` subprocess + `iptables` subprocess) and traced cleanly to ADR-0001 / ADR-0004, but had **30+ findings across all four critic lenses, including thirteen block-tier** that an executor following the draft literally would have shipped silently broken. The most consequential:

1. **(coverage + consistency — block) DNS resolution semantic gap is load-bearing and was buried in implementer Notes.** Draft AC-4 said `_compute_rules(egress_allowlist, container_ip)` operates on raw hostnames; implementer Notes §6 hedged with "the rule pattern `-d <hostname>` works on most iptables versions; if not, resolve via SDK ... and use IP literals". This is **wrong on Docker Desktop's embedded VM (alpine-based)** — modern `iptables-nft` resolves `-d <hostname>` to a single IP at rule-add time, NOT at packet-match time. A CDN host like `registry.npmjs.org` resolves to one of N rotating IPs; the rule pins one IP; npm requests hitting any of the other N-1 IPs silently fail. Worse, the **golden-test contract** the story rests on (`tests/golden/iptables_rules_scoped_npmjs.txt`) becomes ambiguous: hostname-form vs IP-form produce different argv. Resolution: AC-DNS-1..AC-DNS-5 pin a **two-helper FCS split** — impure `_resolve_egress_allowlist(allowlist) -> tuple[ResolvedHost, ...]` (uses stdlib `socket.gethostbyname_ex`; called once inside `apply()`) feeds pure `_compute_rules(resolved: tuple[ResolvedHost, ...], container_ip: str) -> tuple[tuple[str, ...], ...]`. Golden file is IP-form (canonical `93.184.216.34` for `registry.npmjs.org`, monkeypatched in tests). Staleness window (DNS TTL → rule lifetime) documented in module docstring; per-`apply()` re-resolution is the migration path (no caching across runs).

2. **(consistency — block) New exception classes `SandboxBuildFailed` / `NetworkPolicyApplyFailed` violate S1-01 HARDENED's closed-Literal-`reason` discriminator pattern.** S1-01 ships `SandboxBackendError(reason: Literal["create_failed","start_failed","stream_failed","wait_failed","image_unavailable","remove_failed"])`. Draft introduces two free-form exception classes; Phase 13 cost ledger keys on `error_class` + `reason`, so a new `SandboxBuildFailed` without a matching closed Literal is silently incompatible. Resolution: **subclass** `SandboxBackendError`, widen the `reason` Literal additively. AC-ERR-1..AC-ERR-4 pin: `SandboxBuildFailed(SandboxBackendError)` with `reason: Literal["build_failed", "build_timeout", "buildx_missing"]`; `NetworkPolicyApplyFailed(SandboxBackendError)` with `reason: Literal["dns_resolution_failed", "iptables_apply_failed", "iptables_revert_failed", "container_ip_unknown"]`. The widened S1-01 union is now `Literal["create_failed", ..., "remove_failed", "build_failed", "build_timeout", "buildx_missing", "dns_resolution_failed", "iptables_apply_failed", "iptables_revert_failed", "container_ip_unknown"]` — eleven members, byte-exact, asserted via `typing.get_args`.

3. **(consistency — block) Event-name strings violate S1-01 HARDENED canonical-table + `STARTED/COMPLETED/FAILED` verb convention.** Draft uses `sandbox.did.build.done` (wrong verb), `sandbox.did.network.apply` (wrong noun — should be `network_policy`), `.revert` (bare). S3-02 HARDENED AC-EVT-1 standardized the verbs. Resolution: AC-EVT-1 appends six `Final[str]` constants — `EVENT_SANDBOX_DID_BUILD_STARTED/COMPLETED/FAILED`, `EVENT_SANDBOX_DID_NETWORK_POLICY_APPLIED/REVERTED/APPLY_FAILED` — alphabetized into `sandbox/logging.py`'s sorted `__all__`. AC-PURE-6 enforces zero bare-string event names via AST walk.

4. **(consistency + coverage — block) `BuildResult` and `AppliedPolicy` are referenced as load-bearing return types but never defined.** Draft AC-2 says `BuildResult(exit_code: int, stdout: str, stderr: str, image_digest: str | None)`; AC-3 mentions `AppliedPolicy` without field set. Both must be frozen Pydantic models per ADR-0014 (extra="forbid", `model_config = ConfigDict(frozen=True, extra="forbid")`) and pass the banned-substring field-name walker (no `confidence`, `llm`, `self_reported`, `model_says`). Resolution: AC-MODELS-1..AC-MODELS-8 pin both models, their field sets, validators (e.g., `image_digest` shape `^sha256:[0-9a-f]{64}$`; `applied_at: datetime` tz-aware UTC), and the test that constructs each from a golden JSON fixture.

5. **(coverage + consistency — block) S3-02's `_build_container_kwargs` pinned `network_mode="none"` always (AC-EXEC-4 byte-exact); S3-02's `_validate_spec_supported` raised `NotImplementedError` for `spec.network=="scoped"` (AC-SPEC-DEFER-1) and `spec.egress_allowlist != []` (AC-SPEC-DEFER-2). S3-03 must widen all three.** Draft Implementation outline §3 says "Set `network_mode='bridge'` ... when `spec.network == 'scoped'`, else `'none'`" but does NOT call out which S3-02 ACs are being widened, which tests are being amended, and how to keep the S3-02-era frozen golden artifacts (`_construct_sandbox_run` digest, etc.) untouched. Resolution: AC-WIDEN-1..AC-WIDEN-5 enumerate every S3-02 AC modified, the new spec-conditional `network_mode` logic via pure helper `_resolve_network_mode(spec) -> Literal["none", "bridge"]`, the S3-02 test amendments (parametrized over network ∈ {"none","scoped"}), and confirmation that S3-02's golden fixtures (frozen `SandboxRun` JSON) are NOT regenerated by this story.

6. **(coverage — block) Network policy ordering is racy without a happens-before barrier.** Draft Implementation outline §3 says "After `container.start()`, if `spec.network == 'scoped'`, call `network_policy.apply(spec, container_id=container.id)`". But the SDK's `container.start()` returns as soon as the container's init PID is alive — the workload (`npm ci ...`) is already racing. Between `start()` returning and `network_policy.apply()` finishing the last `iptables` rule, the workload can attempt egress to anywhere. **The fix is structural**: use `container.create(...)` with `entrypoint=["sleep", "infinity"]` (NOT `cmd`), apply iptables rules in `apply()`, THEN `container.exec_run(spec.cmd, detach=False, demux=True)` to run the real workload. AC-RACE-1..AC-RACE-3 pin this ordering and an adversarial test (`test_no_egress_window_before_policy_applied`) that monkeypatches `apply()` to sleep 100 ms and asserts the workload's `exec_run` has not been called yet at that moment.

7. **(coverage — block) Container IP resolution path unpinned.** Draft says "`apply()` resolves `container_ip` via the Docker SDK passed in (no subprocess for this)". But S3-02 HARDENED `DockerInDockerClient` does NOT pass a Docker SDK handle to `network_policy.apply`; the `apply` signature in AC-3 is `(spec, container_id) -> AppliedPolicy` — no SDK. The hidden state would force `network_policy.apply()` to call `docker.from_env()` internally, breaking the Hexagonal DI port pattern S3-02 established. Resolution: AC-IP-1..AC-IP-3 pin the dependency-injection seam — `apply(spec, *, container, runner=_default_runner)` takes the `container` SDK object directly (typed via the S3-02 `_docker_types.py` shim), reads `container.attrs["NetworkSettings"]["IPAddress"]`, raises `NetworkPolicyApplyFailed("container_ip_unknown")` if empty. The client.py edit (AC-CLIENT-1) passes its already-created `container` object, not just `container.id`.

8. **(coverage + test-quality — block) `revert()` failure semantics undefined.** Draft AC-5 says cleanup "calls `network_policy.revert(applied)` in the `finally` cleanup block". But (a) `iptables -D` on a rule that no longer exists exits with code 1 — does revert raise? Log? Silently swallow? (b) If revert is called twice (idempotency), does it raise on the second call? (c) If revert raises while `execute()` is already mid-error, primary exception must win (mirrors S3-02 AC-CLEANUP-3). Resolution: AC-REVERT-1..AC-REVERT-5 pin: revert is idempotent (catches per-rule `CalledProcessError` for already-gone rules, logs WARNING `sandbox.did.network_policy.revert_rule_missing`, continues); on a genuinely catastrophic revert failure (e.g., `iptables` binary missing), logs WARNING `EVENT_SANDBOX_DID_NETWORK_POLICY_APPLY_FAILED` with `reason="iptables_revert_failed"` and **does not re-raise**; primary exception always wins. 12-cell parametrized test grid (`phase ∈ {start, exec, wait}` × `policy_outcome ∈ {applied_ok, apply_raises, revert_raises, both_raise}`).

9. **(coverage — block) `subprocess.run` parameter set unpinned across both chokepoints.** Draft uses `subprocess.run(argv, capture_output=True, text=False, check=False, timeout=...)` for build (timeout left as `...`) and `subprocess.run([...], check=True)` for iptables. Neither covers: `cwd=` (where does build run from? — must be `context_dir`), `env=` (must be the closed allowlist, not inherited), `stdin=subprocess.DEVNULL` (prevent hangs), `start_new_session=True` (prevent SIGINT from killing the build prematurely), explicit `timeout` value, behavior on `TimeoutExpired`. Resolution: AC-SUBPROCESS-1..AC-SUBPROCESS-7 pin every kwarg explicitly via a shared module-level `_DEFAULT_RUN_KWARGS: Final[Mapping[str, object]] = MappingProxyType({...})` constant; AC-SUBPROCESS-8 fences `shell=True` / `os.system` / `os.popen` via the `forbidden-patterns` pre-commit (already repo-wide, but tested here at the file level for paper trail).

10. **(test-quality — block) The TDD plan's argv assertions are too loose.** Draft `test_argv_is_docker_buildx_progress_plain` asserts `argv[:4] == ["docker", "buildx", "build", "--progress=plain"]` plus `"--build-arg=NODE_VERSION=20" in argv` plus a disjunction `argv[-2:] == ["-t", "test:1"] or "-t" in argv`. The disjunction makes the test always pass (the second clause is trivially true for any argv containing `-t`). Mutation example: an implementation that emits `["docker", "buildx", "build", "--progress=plain", "-t", "test:1", str(context_dir)]` and silently drops `--build-arg=NODE_VERSION=20` passes 2/3 assertions and fails only one — a build that loses `--build-arg` ships a CVE-vulnerable image. Resolution: AC-ARGV-1..AC-ARGV-4 pin byte-exact argv via a parametrized **golden snapshot fixture** `tests/golden/docker_buildx_argv_*.txt` indexed by `[minimal, with_dockerfile, with_build_args, with_dockerfile_and_build_args]`; the test asserts `argv == golden_lines`.

11. **(test-quality + coverage — block) `_compute_rules` golden test is single-fixture.** Draft `test_rules_match_golden` covers exactly one allowlist (`["registry.npmjs.org"]`) and one container IP (`"172.17.0.2"`). A mutation that hardcodes `["iptables", "-I", "OUTPUT", "-s", "172.17.0.2", "-d", "93.184.216.34", "-j", "ACCEPT"]` (ignoring the input!) passes. Resolution: AC-RULES-1..AC-RULES-6 pin: hypothesis property test `@given(st.lists(st.from_regex(r"^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$"), min_size=0, max_size=5), st.from_regex(...))` asserting (a) `len(rules) == len(allowlist_ips) + 1`, (b) every rule contains `container_ip` exactly once, (c) the last rule's target is `DROP`, (d) first `len(allowlist_ips)` rules have target `ACCEPT`, (e) rule order is input-order-stable (no set→list reordering). Plus three concrete golden fixtures for `[]`, `[one_ip]`, `[three_ips]`.

12. **(test-quality — block) `test_revert_runs_even_when_workload_raises` mocks `network_policy.apply` / `revert` directly.** Doesn't actually exercise the integration between `client.py` and `network_policy.py` — a mutation that calls `apply` but never `revert` still passes the existing test because the test's revert mock is what's measured. Resolution: AC-INTEG-1 pins the mock at the docker SDK boundary (mock `container`, `runner` for subprocess); the test asserts that **the real `network_policy.revert` function** is called from `execute()`'s `finally` block. Plus AC-INTEG-2 — a parametrized 12-cell cleanup grid mirroring S3-02 AC-CLEANUP-5.

13. **(patterns — block, elevated to AC under rule-of-three) Hexagonal `subprocess.run` runner DI port.** S3-01 set the precedent (`filter_fn` / `host_env_source` / `catalog`); S3-02 added (`docker_factory`); S3-03 is the **third concrete consumer** of the DI-port pattern. Rule-of-three reached. Elevate from Note to AC: both `build.py::build_image` and `network_policy.py::apply/revert` accept `runner: Callable[..., subprocess.CompletedProcess[bytes]] = _default_runner` keyword-only; `_default_runner` is the only function that calls `subprocess.run` directly; tests inject `runner=spy` without `unittest.mock.patch`. AC-DI-1..AC-DI-5.

14. **(patterns — block, elevated under rule-of-three) Functional core / imperative shell split.** S3-01 + S3-02 + S3-03 = three Phase-5 stories with explicit FCS split. Elevate from Note to AC. **`build.py` pure helpers**: `_build_argv(context_dir, tag, dockerfile, build_args) -> tuple[str, ...]`, `_parse_image_digest(stderr: bytes) -> str | None`, `_truncate_stderr(stderr: bytes, max_bytes: int) -> str`, `_wrap_subprocess_error(err, *, where) -> SandboxBuildFailed | NetworkPolicyApplyFailed`. **`network_policy.py` pure helpers**: `_compute_rules(resolved_ips: tuple[str, ...], container_ip: str) -> tuple[tuple[str, ...], ...]`, `_compute_revert_rules(applied: AppliedPolicy) -> tuple[tuple[str, ...], ...]`, `_validate_ip_literal(s: str) -> bool`. **Impure shells**: `build_image()`, `apply()`, `revert()`, `_resolve_egress_allowlist()`. AC-FCS-1..AC-FCS-7 enumerate each + unit-test in isolation.

Beyond the block-tier findings, the harden-tier work:

15. **(test-quality — harden) Stderr truncation policy `≤ 4 KB` unspecified at byte level.** Draft says "truncated stderr (≤ 4 KB)". Is it 4 KiB (4096 bytes) or 4 KB (4000 bytes)? UTF-8 boundary handling on truncation? Resolution: AC-TRUNC-1 pins `_MAX_STDERR_BYTES: Final[int] = 4096` (4 KiB, matching POSIX `PIPE_BUF` semantics), UTF-8-safe slicing via `stderr_bytes[:_MAX_STDERR_BYTES].decode("utf-8", errors="replace")`. Test asserts an 8 KiB stderr is truncated to exactly 4 KiB worth of decoded characters.

16. **(test-quality — harden) `image_digest` regex `sha256:[0-9a-f]{64}` not validated as the full canonical form.** Mutation: regex `sha256:[0-9]{64}` (missing `a-f`) passes on lucky-digit fixtures. Resolution: AC-DIGEST-1..AC-DIGEST-3 pin `^sha256:[0-9a-f]{64}$` (anchored full-match), unit-test parametrized over `[valid_lowercase_digest, uppercase_digest (must fail), short_digest, no_prefix]`.

17. **(test-quality — harden) Build timeout behavior on `subprocess.TimeoutExpired`.** Draft says `timeout=...` (placeholder). What happens on timeout? Resolution: AC-TIMEOUT-1 pins `_DEFAULT_BUILD_TIMEOUT_SECONDS: Final[int] = 1800` (30 min — Phase-7 distroless multi-stage builds can run long); on `subprocess.TimeoutExpired`, raise `SandboxBuildFailed(reason="build_timeout")` with the partial stderr captured. AC-TIMEOUT-2 tests this via a `runner` that raises `TimeoutExpired`.

18. **(test-quality — harden) Module-purity AST walker missing.** Every prior Phase-5 story (S1-02..S3-02) shipped one. Resolution: AC-PURE-1..AC-PURE-8 ship `tests/sandbox/did/test_build_purity.py` AND `tests/sandbox/did/test_network_policy_purity.py` — both enforcing: `from __future__ import annotations` first; `__all__` alphabetized; module docstring cites ADR-0001 / ADR-0004 by number; **`build.py` allowed to import `subprocess`** (the explicit chokepoint exception); **`network_policy.py` allowed to import `subprocess` and `socket`** (DNS resolution); all other modules in `sandbox/did/` MUST NOT import `subprocess` (defense in depth on top of the AST fence).

19. **(test-quality — harden) `forbidden-patterns` pre-commit hook bans `shell=True` repo-wide — story should explicitly verify that NEITHER chokepoint file uses it.** Resolution: AC-PURE-7 walks both files' ASTs and asserts every `subprocess.run` call's `keywords` set does NOT contain `shell` with `value=Constant(True)`. Belt and suspenders on the pre-commit hook.

20. **(test-quality — harden) `_resolve_egress_allowlist` failure path untested.** What if `socket.gethostbyname_ex` raises `socket.gaierror`? Resolution: AC-DNS-3 pins `NetworkPolicyApplyFailed(reason="dns_resolution_failed", details={"host": "...", "errno": "..."})`; AC-DNS-4 tests the path via a `runner`-style DI port for the resolver (`resolver: Callable[[str], list[str]] = _default_resolver`).

21. **(test-quality — harden) Golden iptables file's hardcoded container IP `"172.17.0.2"` is brittle.** Resolution: AC-RULES-7 documents the canonical fixture container IP as `"172.17.0.2"` (Docker Desktop bridge-network default), pins it as a module-level `_FIXTURE_CONTAINER_IP: Final[str]` constant in the test file; live integration in S3-07 uses the real IP.

22. **(test-quality — harden) Registry / extension-point shape.** Should `network_policy` expose a `register_network_policy_backend(backend_name)` decorator factory now (forward-compat for Firecracker host-side nftables)? Per Rule 2 + the rule-of-three pattern: NO. Only one concrete `apply`/`revert` pair exists; S6-02 (Firecracker nftables) is the second; rule-of-three not reached. Resolution: **Notes-for-implementer paragraph** + AC-PATTERN-1 confirms `apply`/`revert` are plain module-level functions, NOT a Protocol, NOT registry-dispatched. When S6-02 ships its own `apply`/`revert` for nftables AND a third backend (e.g., gVisor in Phase 7+) reaches three, collapse to `NetworkPolicyApplier` Protocol per ADR-0006.

23. **(test-quality — harden) `apply()` is called BEFORE workload exec but AFTER `container.start()` with `entrypoint=["sleep","infinity"]`** (per AC-RACE-1). The "container's `cmd` field" carried in `SandboxSpec.cmd` is now executed via `container.exec_run`, not via container start. This is a **client.py architectural change**, not a pure additive edit. Resolution: AC-CLIENT-1..AC-CLIENT-7 pin the structural change explicitly: S3-02's create-then-start-then-stream pattern becomes create(`entrypoint=["sleep","infinity"]`)-then-start-then-apply_policy-then-exec_run(spec.cmd, demux=True)-then-revert-then-remove. S3-02 happy-path test grid amendments enumerated by AC number (the parametrized `[network=none, network=scoped]` sweep).

24. **(coverage — harden) `spec.copy_in != []` is the bytes-in path. S3-02 HARDENED AC-SPEC-DEFER-3 emits a deferred-WARNING.** S3-03 does NOT widen this; S3-04 owns it. Resolution: Notes for the implementer call this out explicitly — do NOT also widen AC-SPEC-DEFER-3 in this story.

25. **(coverage — harden) Coverage floor wording absent.** Phase-5 standard is "line ≥ 95% AND branch ≥ 90%". Resolution: AC-COV-1 + AC-COV-2.

26. **(coverage — harden) AppliedPolicy contains `applied_rules: tuple[tuple[str, ...], ...]`** (canonical rule argv) **but does NOT contain stdout/stderr from the subprocess calls** (could leak sensitive networking info to Phase 11 evidence bundle).  AC-MODELS-5 pins the closed field set: `{container_id: str, applied_rules: tuple[tuple[str, ...], ...], applied_at: datetime}` only.

27. **(coverage — harden) `iptables` rule for `network="none"` is no-op, but client.py with `network_mode="none"` already disables egress.** The "Network policy revert runs even when the workload raises" AC in the draft is over-permissive — for `network="none"`, no `apply()` was called, so no `revert()` should be called either. Resolution: AC-CLIENT-2 pins the conditional: `if spec.network == "scoped": applied = apply(spec, container=container); try: ...; finally: revert(applied)`.

28. **(consistency — harden) `pyproject.toml` does NOT need new dependencies in this story** (stdlib `subprocess` + stdlib `socket` only). Resolution: AC-DEP-1 explicitly confirms no `pyproject.toml` change.

29. **(patterns — harden) `BuildResult` not needed at the contract layer.** Phase-7 distroless and Phase-11 evidence bundle key on `SandboxRun.exit_code` and `SandboxRun.logs_dir`, not on a `BuildResult` object. Resolution: AC-MODELS-3 pins `BuildResult` as a `frozen=True` Pydantic model **internal to `sandbox/did/build.py`** (not re-exported from `sandbox/contract.py`); fields `{exit_code, stdout, stderr, image_digest, started_at, ended_at}`.

30. **(patterns — nit, fixed) Warning ID namespacing.** `iptables_apply_failed` (etc.) must match CLAUDE.md namespace regex `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. Resolution: AC-EVT-2 enforces.

**Two Stage-3 research findings answered inline:**

- **DNS-vs-IP in `iptables`:** Linux netfilter resolves `-d <hostname>` at rule-add time only (per [netfilter wiki / `iptables(8)` man page](https://www.netfilter.org/documentation/HOWTO/packet-filtering-HOWTO.html)). CDN hostnames with rotating IPs silently fail. The production-grade pattern is one-rule-per-resolved-IP, with per-`apply()` re-resolution (no caching across runs). For low-rotation hosts (`registry.npmjs.org` rotates within a small CIDR), this is acceptable; for high-rotation hosts (S3 buckets), `ipset` with dynamic DNS is the eventual fix — out of scope for Phase 5. Documented as a known limitation in the module docstring per AC-DNS-5.

- **Buildx `--progress=plain` stderr format:** Per [Docker BuildKit docs](https://docs.docker.com/build/buildkit/configure/#progress) and the BuildKit source (`progressui/textmux.go`), `--progress=plain` writes structured `#<step> <event>` lines to stderr with the final image digest appearing as `#<N> writing image sha256:<64-hex> done` on the success path. The regex `^#\d+ writing image (sha256:[0-9a-f]{64}) done$` (multiline, anchored) is the production extraction pattern. AC-DIGEST-1 pins this regex; AC-DIGEST-3 tests it against the BuildKit-canonical stderr fixture (committed under `tests/fixtures/buildx_stderr/`).

**No `RESCUE`-tier findings.** The DNS-vs-IP block was the closest to structural — it could have invalidated the golden file's argv form entirely — but the resolution is patchable: pre-resolve to IPs, re-resolve per `apply()`, golden tests use a monkeypatched resolver. Downstream stories (S3-04 copy-out, S3-07 integration, S6-02 Firecracker nftables) inherit a clean hand-off: AppliedPolicy is the contract surface; `apply`/`revert` are the callable boundary; the migration to a `NetworkPolicyApplier` Protocol is deferred to S6-02-or-later when the rule-of-three reaches.

## Context

ADR-0001 says only two files under `sandbox/did/` may `import subprocess`: `build.py` (for `docker buildx build --progress=plain` — the SDK's build streaming is unworkable for our progress capture needs) and `network_policy.py` (for `iptables` rule application, since the Docker SDK has no equivalent abstraction). Both are AST-fenced by `tests/schema/test_no_subprocess_outside_build_chokepoint.py` AND by per-file purity walkers shipped by this story. The `forbidden-patterns` pre-commit hook (ADR-0008 + ADR-0012) additionally bans `shell=True`, `os.system`, `os.popen` repo-wide.

This story implements both files surgically **AND** widens three S3-02 ACs additively: AC-SPEC-DEFER-1 (raise → accept for `network="scoped"`), AC-SPEC-DEFER-2 (raise → accept for non-empty `egress_allowlist`), and AC-EXEC-4 (`network_mode="none"` hardcode → spec-conditional via pure helper `_resolve_network_mode`). The S3-02 cmd-at-create-time pattern is restructured into create-with-sleep-entrypoint + apply-policy + exec_run(spec.cmd) — necessary to close the race window where the workload could egress to anywhere between `container.start()` returning and the last iptables rule being installed (AC-RACE-1).

This story is also the **third concrete consumer** of two Phase-5 patterns introduced by S3-01 and consolidated by S3-02 — the **Hexagonal DI port** pattern (S3-01: `filter_fn`/`host_env_source`/`catalog`; S3-02: `docker_factory`; here: `runner`/`resolver`) and the **functional core / imperative shell** pattern (S3-01: `_canonical_blake3` etc.; S3-02: `_build_container_kwargs`/`_construct_sandbox_run`/`_wrap_api_error`/`_demux_chunks`; here: `_build_argv`/`_parse_image_digest`/`_truncate_stderr`/`_compute_rules`/`_compute_revert_rules`/`_validate_ip_literal`/`_wrap_subprocess_error`). Rule-of-three reached for both; both are elevated from Note to AC in this story.

The `network=scoped` allowlist is the only path between `npm ci` (which needs `registry.npmjs.org`) and `network=none` (which `npm test` runs under, fenced by the workload's own per-phase `network` field — S3-05 owns the multi-phase split, this story handles the flat S3-02-era single-phase spec). iptables rules are generated deterministically from the **pre-resolved IP fan-out** of `spec.egress_allowlist` and snapshot-tested via `tests/golden/iptables_rules_<scenario>.txt`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — DockerInDockerClient` (lines ~486–493) — "Subprocess permitted only in `sandbox/did/build.py`" + "network_policy.py is the only module that may call `iptables` (same chokepoint pattern)" + `copy_out.py` is golden-file tested.
  - `../phase-arch-design.md §Logical view — module decomposition` (lines ~247–255) — explicit `did/{client,build,network_policy,copy_out}.py` map.
  - `../phase-arch-design.md §Physical view` (line ~322, ~347) — "`network=scoped` only for `npm ci`; `network=none` for `npm test`"; "Docker Desktop on macOS routes through its embedded Linux VM, so `iptables` runs there".
  - `../phase-arch-design.md §Process view — sequence diagrams` (lines ~357, ~437) — workload `exec_run` after `start()` (the race-closing pattern).
  - `../phase-arch-design.md §Edge cases` (lines ~853–871) — #1 (Docker daemon dies mid-build), #5 (postinstall egress dropped by allowlist), #19 (policy YAML digest mismatch — owned by S3-05).
  - `../phase-arch-design.md §Testing strategy — Golden files` (line ~891) — `tests/golden/iptables_rules_<network-policy>.txt`.
  - `../phase-arch-design.md §Tool-use safety` (line ~844) — closed subprocess allowlist.
  - `../phase-arch-design.md §Gap 4` (lines ~1026–1030) — Firecracker network policy is host-side nftables (ADR-0009), NOT the iptables we ship here.
- **Phase ADRs:**
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — Consequences §"any module under `sandbox/` or `gates/` that imports `subprocess` must live in one of the three allowlisted chokepoint files" — `did/build.py`, `did/network_policy.py`, `firecracker/client.py`.
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — DinD is shared-kernel; iptables runs on the host Linux VM (macOS = Docker Desktop's embedded VM); each `SandboxRun.gate_isolation_class="shared_kernel"`.
  - `../ADRs/0006-protocol-vs-abc-convention.md` — `apply`/`revert` are plain module functions, NOT a Protocol, until rule-of-three reaches with a third backend.
  - `../ADRs/0009-firecracker-network-policy-host-side-nftables.md` — defines Phase-5's other network policy backend (S6-02); this story's `apply`/`revert` shape is the forward-compat anchor.
  - `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — `extra="forbid"`/`frozen=True` Pydantic config applies to `BuildResult` and `AppliedPolicy`; banned-substring field-name walker applies.
- **Source design:**
  - `../final-design.md §Synthesis ledger` — subprocess chokepoint discipline.
- **Existing code (HARDENED ancestors):**
  - `src/codegenie/sandbox/did/client.py` (from S3-02 HARDENED) — `DockerInDockerClient`; AC-EXEC-4 (`network_mode="none"`), AC-SPEC-DEFER-1/-2 (NotImplementedError), `_build_container_kwargs` pure helper, `_default_docker_factory` Hexagonal port — all amended by this story (additively where possible; structurally where the race-closing pattern requires).
  - `src/codegenie/sandbox/errors.py` (from S1-01 HARDENED) — `SandboxBackendError(reason: Literal[...])`; this story widens the closed Literal by six members (AC-ERR-1).
  - `src/codegenie/sandbox/logging.py` (from S1-01 HARDENED, extended by S3-02) — canonical event-name table; this story appends six events + one warning ID constants per AC-EVT-1.
  - `src/codegenie/sandbox/did/_docker_types.py` (from S3-02 HARDENED) — `ContainerKwargs` TypedDict; this story widens its `network_mode` literal from `"none"` to `Literal["none","bridge"]`.
  - `src/codegenie/sandbox/registry.py` (from S1-05 HARDENED) — NOT used by `network_policy.py` (Rule 2; deferred to S6-02 rule-of-three reach).
  - `tests/schema/test_no_subprocess_outside_build_chokepoint.py` (from S1-07 HARDENED) — AST fence asserting only the three chokepoint files import `subprocess`; **`network_policy.py` must be added to this allowlist** (per AC-FENCE-1).
- **Prior HARDENED reports (consult before implementing):**
  - `_validation/S1-01-scaffold-packages-errors-structlog.md` — event-name table convention, append-only policy, `STARTED/COMPLETED/FAILED` verb discipline.
  - `_validation/S3-01-spec-builder-canonical-hash.md` — Hexagonal DI ports (constructor kwargs with production defaults; the precedent for `runner=_default_runner`), functional-core/imperative-shell pure-helper convention.
  - `_validation/S3-02-did-client-sdk-core.md` — `_default_docker_factory` Hexagonal port (rule-of-three second consumer), `_build_container_kwargs` / `_construct_sandbox_run` / `_wrap_api_error` / `_demux_chunks` FCS helpers (rule-of-three second consumer), closed `reason` Literal discriminator pattern.
- **External docs:**
  - https://docs.docker.com/build/buildx/ — `docker buildx build --progress=plain` argv shape.
  - https://docs.docker.com/build/buildkit/configure/#progress — BuildKit `--progress=plain` stderr line format (regex anchor for `_parse_image_digest`).
  - https://www.netfilter.org/documentation/HOWTO/packet-filtering-HOWTO.html — iptables rule semantics; `-d <hostname>` resolves at rule-add time only (the load-bearing finding behind AC-DNS-1).
  - https://docs.python.org/3/library/socket.html#socket.gethostbyname_ex — stdlib DNS resolution; raises `socket.gaierror` on failure.
  - https://datatracker.ietf.org/doc/html/rfc3986 — host-form vs IP-literal syntax (used by `_validate_ip_literal`).

## Goal

Land `src/codegenie/sandbox/did/build.py` (the `docker buildx build --progress=plain` subprocess chokepoint) and `src/codegenie/sandbox/did/network_policy.py` (the `iptables` subprocess chokepoint with DNS pre-resolution to IP fan-out, per-rule `apply`/`revert` idempotency, and AppliedPolicy frozen-Pydantic contract), then **widen S3-02's `DockerInDockerClient` additively** to wire `network=scoped` end-to-end: create with sleep-entrypoint, start, apply policy, exec_run(spec.cmd, demux=True), revert in finally, remove. Closed-`reason` Literal discriminator on both new exception subclasses (`SandboxBuildFailed`, `NetworkPolicyApplyFailed`), six new structlog event constants in `sandbox/logging.py` (`STARTED/COMPLETED/FAILED`/`APPLIED/REVERTED/APPLY_FAILED` verbs), byte-exact argv golden snapshots, hypothesis property tests on `_compute_rules`, and zero new `subprocess` imports anywhere outside the two chokepoint files (defense-in-depth on top of the existing AST fence).

## Acceptance criteria

### A. Public surface + module purity

- [ ] **AC-API-1** `src/codegenie/sandbox/did/build.py` exists with module docstring citing `ADR-0001`, `ADR-0014` by number; `__all__ == ["BuildResult", "SandboxBuildFailed", "build_image"]` (alphabetized).
- [ ] **AC-API-2** `src/codegenie/sandbox/did/network_policy.py` exists with module docstring citing `ADR-0001`, `ADR-0004`, `ADR-0009`, `ADR-0014` by number; `__all__ == ["AppliedPolicy", "NetworkPolicyApplyFailed", "apply", "revert"]` (alphabetized). Module docstring contains a paragraph documenting the **DNS staleness window** (per-`apply()` re-resolution; no caching across runs; rotating CDN hostnames are a known limitation tracked in `../High-level-impl.md`).
- [ ] **AC-API-3** `from __future__ import annotations` is the first statement after the docstring in both files.
- [ ] **AC-API-4** All pure-helper names (`_build_argv`, `_parse_image_digest`, `_truncate_stderr`, `_compute_rules`, `_compute_revert_rules`, `_validate_ip_literal`, `_wrap_subprocess_error`, `_default_runner`, `_default_resolver`) are module-private (single leading underscore) and NOT in `__all__`.
- [ ] **AC-API-5** Module-level `Final` constants in `build.py`: `_DEFAULT_BUILD_TIMEOUT_SECONDS: Final[int] = 1800`, `_MAX_STDERR_BYTES: Final[int] = 4096`, `_IMAGE_DIGEST_RE: Final[re.Pattern[str]]` (anchored full-match regex for `sha256:[0-9a-f]{64}`); in `network_policy.py`: `_IPTABLES_BIN: Final[str] = "iptables"`, `_DEFAULT_DNS_TIMEOUT_SECONDS: Final[int] = 5`. Method bodies reference these constants by name; AST walk confirms zero inline magic numbers (AC-PURE-8).

### B. Constructor / runner DI ports (rule-of-three Hexagonal port)

- [ ] **AC-DI-1** `build.py::build_image(context_dir, tag, *, dockerfile=None, build_args=None, timeout_seconds=_DEFAULT_BUILD_TIMEOUT_SECONDS, runner=_default_runner) -> BuildResult` — keyword-only `runner: Callable[..., subprocess.CompletedProcess[bytes]] = _default_runner`. Production callers pass nothing; tests inject `runner=spy`.
- [ ] **AC-DI-2** `network_policy.py::apply(spec, *, container, runner=_default_runner, resolver=_default_resolver) -> AppliedPolicy` — keyword-only `runner` (same callable shape as AC-DI-1) AND keyword-only `resolver: Callable[[str], list[str]] = _default_resolver`. `_default_resolver(host)` wraps `socket.gethostbyname_ex(host)[2]` and raises `NetworkPolicyApplyFailed(reason="dns_resolution_failed", ...)` on `socket.gaierror`.
- [ ] **AC-DI-3** `network_policy.py::revert(applied: AppliedPolicy, *, runner=_default_runner) -> None` — keyword-only `runner` matching AC-DI-2; revert does NOT take `resolver` (the IPs are already pinned in `applied.applied_rules`).
- [ ] **AC-DI-4** `_default_runner(argv: list[str], *, timeout: int, cwd: Path | None = None, env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[bytes]` is the SINGLE function in either file that calls `subprocess.run`. AST walk asserts `subprocess.run` appears exactly once across both files combined (AC-PURE-9).
- [ ] **AC-DI-5** Tests inject `runner=spy` via direct kwarg, NOT via `unittest.mock.patch("subprocess.run")`. Asserted by a meta-test that greps for `mock.patch("subprocess` in `tests/sandbox/did/` and counts zero occurrences (defense against drift back to mock magic).

### C. `build_image()` SDK shell

- [ ] **AC-BUILD-1** `build_image(context_dir: Path, tag: str, *, dockerfile: Path | None = None, build_args: Mapping[str, str] | None = None, ...) -> BuildResult` (signature byte-exact in `__init__` source via `inspect.signature`).
- [ ] **AC-BUILD-2** Calls (in order): `argv = _build_argv(context_dir, tag, dockerfile, build_args)`; `started_at = datetime.now(timezone.utc)`; `cp = runner(argv, timeout=timeout_seconds, cwd=context_dir, env=_default_build_env())`; `ended_at = datetime.now(timezone.utc)`; emit `EVENT_SANDBOX_DID_BUILD_STARTED` at start; on `cp.returncode != 0` raise `SandboxBuildFailed("build_failed", details={"exit_code": cp.returncode, "stderr_truncated": _truncate_stderr(cp.stderr, _MAX_STDERR_BYTES)})`; on `subprocess.TimeoutExpired` catch + raise `SandboxBuildFailed("build_timeout", details={"timeout_seconds": timeout_seconds, "partial_stderr": _truncate_stderr(err.stderr or b"", _MAX_STDERR_BYTES)})`; on success emit `EVENT_SANDBOX_DID_BUILD_COMPLETED`; on either raise path emit `EVENT_SANDBOX_DID_BUILD_FAILED`; return `BuildResult(...)` with `image_digest=_parse_image_digest(cp.stderr)`.
- [ ] **AC-BUILD-3** `_default_build_env() -> dict[str, str]` returns a closed allowlist `{"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "DOCKER_BUILDKIT": "1", "HOME": os.environ.get("HOME", "/tmp")}` — NO inheritance from the orchestrator's env (matches ADR-0012 spirit; the closed set is documented in the module).
- [ ] **AC-BUILD-4** `build_image` does NOT open files, does NOT chdir, does NOT read or write `.codegenie/`, does NOT call the Docker SDK. The only host effect is the subprocess invocation. Asserted by a test that runs `build_image` with a `runner` spy and a `tmp_path` `context_dir`, then asserts the directory's `Path.iterdir()` is unchanged.

### D. `BuildResult` and `AppliedPolicy` contracts (frozen, extra="forbid")

- [ ] **AC-MODELS-1** `BuildResult` is a `pydantic.BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")`. Fields: `{exit_code: int, stdout: bytes, stderr: bytes, image_digest: str | None, started_at: datetime, ended_at: datetime}`. Both timestamps tz-aware UTC. Cross-field validator: `ended_at >= started_at`; if `image_digest is not None`, `_IMAGE_DIGEST_RE.fullmatch(image_digest)`.
- [ ] **AC-MODELS-2** `AppliedPolicy` is a `pydantic.BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")`. Fields: `{container_id: str, applied_rules: tuple[tuple[str, ...], ...], applied_at: datetime}`. `applied_rules` is canonical argv (tuple-of-tuples, NOT list-of-lists — frozen-friendly + hash-friendly). `applied_at` tz-aware UTC. Validator: each inner tuple's first element equals `_IPTABLES_BIN`.
- [ ] **AC-MODELS-3** `BuildResult` lives in `did/build.py`, NOT re-exported from `sandbox/contract.py`. `AppliedPolicy` lives in `did/network_policy.py`, NOT re-exported. (Both are S3-03-internal; future contract promotion requires an ADR amendment.)
- [ ] **AC-MODELS-4** Banned-substring field-name walker (per ADR-0014): neither model's field names contain `confidence`, `llm`, `self_reported`, `model_says` substrings. Asserted by a test mirroring `tests/sandbox/test_objective_signals_static.py`.
- [ ] **AC-MODELS-5** `AppliedPolicy` does NOT contain stdout/stderr bytes from the `iptables` invocations (Phase 11 evidence bundle would otherwise leak networking topology to reviewers).
- [ ] **AC-MODELS-6** `BuildResult.model_dump_json()` round-trip equality test against a golden fixture `tests/fixtures/sandbox/build_result_minimal.json`.
- [ ] **AC-MODELS-7** `AppliedPolicy.model_dump_json()` round-trip equality test against a golden fixture `tests/fixtures/sandbox/applied_policy_npmjs.json`.
- [ ] **AC-MODELS-8** Frozen-reconstruction idiom: `applied.model_copy(update={"applied_at": new_ts})` succeeds; direct attribute set `applied.applied_at = new_ts` raises `pydantic.ValidationError` (frozen enforcement).

### E. `_compute_rules` — pure helper, golden + property

- [ ] **AC-RULES-1** `_compute_rules(resolved_ips: tuple[str, ...], container_ip: str) -> tuple[tuple[str, ...], ...]` is pure: same input → same output; no I/O; no `time` reads; no `os.environ` reads.
- [ ] **AC-RULES-2** For each `host_ip` in `resolved_ips`, emit one rule `(_IPTABLES_BIN, "-I", "OUTPUT", "-s", container_ip, "-d", host_ip, "-j", "ACCEPT")`; append a final `(_IPTABLES_BIN, "-A", "OUTPUT", "-s", container_ip, "-j", "DROP")`. `len(rules) == len(resolved_ips) + 1`.
- [ ] **AC-RULES-3** Hypothesis property test: `@given(st.lists(st.from_regex(r"^(\d{1,3}\.){3}\d{1,3}$"), min_size=0, max_size=5), st.from_regex(r"^(\d{1,3}\.){3}\d{1,3}$"))` asserts (a) rule_count == input_count + 1, (b) the last rule's last element is `"DROP"`, (c) all other rules' last element is `"ACCEPT"`, (d) `container_ip` appears exactly once in each rule (at position 4), (e) ordering is input-stable (`rules[i][6] == resolved_ips[i]` for `i < len(resolved_ips)`).
- [ ] **AC-RULES-4** Empty allowlist: `_compute_rules((), container_ip)` returns a single-element tuple containing only the DROP rule (no ACCEPT prefix — pure deny-all).
- [ ] **AC-RULES-5** Three golden fixtures committed: `tests/golden/iptables_rules_empty.txt`, `tests/golden/iptables_rules_scoped_npmjs.txt` (one IP), `tests/golden/iptables_rules_scoped_multi.txt` (three IPs); each is one rule per line, space-joined; tests parse via splitlines + assert against `_compute_rules` output.
- [ ] **AC-RULES-6** `_compute_revert_rules(applied: AppliedPolicy) -> tuple[tuple[str, ...], ...]` is pure; for each rule in `applied.applied_rules` whose target is `ACCEPT`, emit `(_IPTABLES_BIN, "-D", "OUTPUT", "-s", container_ip, "-d", host_ip, "-j", "ACCEPT")`; for the DROP rule, emit the corresponding `-D` form. Same input-order stability.
- [ ] **AC-RULES-7** `_FIXTURE_CONTAINER_IP: Final[str] = "172.17.0.2"` declared at top of the test module (NOT magic-string scattered across cases); documented in module docstring as the Docker Desktop default-bridge fixture IP.

### F. `_parse_image_digest` — pure helper

- [ ] **AC-DIGEST-1** `_parse_image_digest(stderr: bytes) -> str | None` is pure: takes raw `buildx --progress=plain` stderr bytes, returns the first match of `_IMAGE_DIGEST_RE` against the stderr decoded as UTF-8 with `errors="replace"`, or `None` if no match.
- [ ] **AC-DIGEST-2** `_IMAGE_DIGEST_RE: Final[re.Pattern[str]] = re.compile(r"writing image (sha256:[0-9a-f]{64})")` — anchored on the `writing image ` prefix to disambiguate from other `sha256:` hits in the stderr (cache-hit lines, etc.).
- [ ] **AC-DIGEST-3** Parametrized test fixtures (committed under `tests/fixtures/buildx_stderr/`): `success_simple.txt`, `success_multi_stage.txt`, `cache_hit_only.txt`, `failure_no_digest.txt`, `uppercase_digest.txt` (must NOT match — full canonical form is lowercase hex). Test asserts the parser returns the expected digest or None per fixture.

### G. `apply()` / `revert()` flow

- [ ] **AC-APPLY-1** `apply(spec, *, container, runner=_default_runner, resolver=_default_resolver) -> AppliedPolicy` — preconditions: `spec.network == "scoped"` AND `spec.egress_allowlist != []`. Both checked at function entry; violation raises `ValueError` (programmer error — `client.py` is the only caller and gates this).
- [ ] **AC-APPLY-2** Order: read `container.attrs["NetworkSettings"]["IPAddress"]` → if empty/missing, raise `NetworkPolicyApplyFailed(reason="container_ip_unknown", details={"container_id": container.id})`; resolve each host in `spec.egress_allowlist` via `resolver(host)` → flatten to `resolved_ips: tuple[str, ...]` (preserving input order, deduplicated within each host's expansion); compute rules via `_compute_rules`; invoke `runner` once per rule with `_DEFAULT_RUN_KWARGS` and `check=True`; on any `subprocess.CalledProcessError` raise `NetworkPolicyApplyFailed(reason="iptables_apply_failed", details={"rule": rule_argv, "stderr": _truncate_stderr(err.stderr or b"", _MAX_STDERR_BYTES)})`; on success emit `EVENT_SANDBOX_DID_NETWORK_POLICY_APPLIED` with `{container_id, rule_count, applied_at}` and return `AppliedPolicy(...)`.
- [ ] **AC-APPLY-3** Partial-failure rollback: if rule `i` of `N` raises, `apply()` MUST emit `_compute_revert_rules` for the `i-1` rules already applied (best-effort, per-rule WARNING on revert failure) BEFORE re-raising the primary `NetworkPolicyApplyFailed`. Asserted by a test that injects a `runner` spy raising on the 3rd call out of 4 + verifies the spy was called for revert of rules 0, 1, 2 (in reverse order) before the raise propagates.
- [ ] **AC-REVERT-1** `revert(applied: AppliedPolicy, *, runner=_default_runner) -> None` runs each rule in `_compute_revert_rules(applied)`, one `runner` call each, `check=False` (NOT `check=True` — see AC-REVERT-2).
- [ ] **AC-REVERT-2** Per-rule failure isolation: `iptables -D` on a rule that no longer exists returns exit code 1 (or 2 on `iptables-legacy`). Revert catches the `CompletedProcess` non-zero return + emits WARNING `EVENT_SANDBOX_DID_NETWORK_POLICY_APPLY_FAILED` (`reason="iptables_revert_failed"`, `details={"rule": rule_argv, "exit_code": cp.returncode}`) and CONTINUES to the next rule. Does NOT raise.
- [ ] **AC-REVERT-3** Idempotency: calling `revert(applied)` twice in succession is a no-op on the second call (modulo the per-rule WARNING on already-gone rules). Asserted by a test that calls revert twice with a runner spy and counts `len(spy.calls) == 2 * len(applied.applied_rules)` (every rule attempted twice, every second attempt logs the WARNING).
- [ ] **AC-REVERT-4** When `iptables` binary is itself missing (e.g., revert called on Linux CI where the test environment has no iptables), `runner` raises `FileNotFoundError`; revert catches + emits WARNING `EVENT_SANDBOX_DID_NETWORK_POLICY_APPLY_FAILED` (`reason="iptables_revert_failed"`) ONCE (not per-rule), does NOT re-raise.
- [ ] **AC-REVERT-5** Emit `EVENT_SANDBOX_DID_NETWORK_POLICY_REVERTED` on the success path with `{container_id, rule_count}`.

### H. DNS resolution + IP fan-out

- [ ] **AC-DNS-1** `_default_resolver(host: str, *, timeout_seconds: int = _DEFAULT_DNS_TIMEOUT_SECONDS) -> list[str]` calls `socket.gethostbyname_ex(host)` and returns the third tuple element (the IP list). Wraps `socket.gaierror` and `socket.herror` as `NetworkPolicyApplyFailed(reason="dns_resolution_failed", details={"host": host, "errno": str(err)})`. The `timeout_seconds` parameter is documented but stdlib `gethostbyname_ex` does NOT honor it directly (limitation noted in module docstring; per-OS resolver timeout is system-level).
- [ ] **AC-DNS-2** If `host` is already an IP literal (matches `_validate_ip_literal(host) is True`), resolver returns `[host]` directly without DNS query.
- [ ] **AC-DNS-3** `_validate_ip_literal(s: str) -> bool` — pure helper using `ipaddress.ip_address(s)` exception-driven check; unit-tested over `["127.0.0.1", "172.17.0.2", "::1", "registry.npmjs.org" (must be False), "" (False), "999.999.999.999" (False)]`.
- [ ] **AC-DNS-4** Resolver failure path test: inject `resolver=lambda h: (_ for _ in ()).throw(socket.gaierror("Name or service not known"))`; `apply()` raises `NetworkPolicyApplyFailed(reason="dns_resolution_failed")`; ZERO rules were applied (spy on `runner` confirms `call_count == 0`).
- [ ] **AC-DNS-5** Module docstring of `network_policy.py` contains a clearly marked `Known limitation:` paragraph explaining: per-`apply()` re-resolution; no caching across runs; rotating CDN hostnames may resolve to different IPs over the workload's lifetime and traffic to non-resolved IPs will be dropped. Forward-pointer to `S6-02` (Firecracker host-side nftables) and to the open Phase-7+ ipset migration.

### I. Subprocess discipline (the chokepoint contract)

- [ ] **AC-SUBPROCESS-1** `_DEFAULT_RUN_KWARGS: Final[Mapping[str, object]] = MappingProxyType({"capture_output": True, "text": False, "check": False, "stdin": subprocess.DEVNULL, "start_new_session": True})` — shared between `build.py` and `network_policy.py` via duplication (NOT a shared import — each chokepoint owns its kwargs; rule-of-three not yet reached for hoisting).
- [ ] **AC-SUBPROCESS-2** `_default_runner` in BOTH files explicitly does NOT pass `shell=True`. AST walk asserts the `Call` node for `subprocess.run` has no `keyword(arg='shell')` (AC-PURE-7).
- [ ] **AC-SUBPROCESS-3** `_default_runner` passes `cwd` only when the caller provides it (build does; network_policy does NOT).
- [ ] **AC-SUBPROCESS-4** `_default_runner` passes `env` only when the caller provides it (build does — closed allowlist per AC-BUILD-3; network_policy does NOT — iptables inherits orchestrator env, which is safe because iptables is a system binary with no env-controlled behavior we depend on; documented inline).
- [ ] **AC-SUBPROCESS-5** Timeout argv: build passes `timeout=timeout_seconds`; network_policy passes `timeout=10` per rule (iptables is local kernel API; 10 s is generous).
- [ ] **AC-SUBPROCESS-6** No `text=True` anywhere — all subprocess I/O is bytes (consistent with S3-02 AC-STREAM-* + `BuildResult.{stdout,stderr}: bytes`).
- [ ] **AC-SUBPROCESS-7** `_default_runner` is the ONLY function in either file that calls `subprocess.run` — single source of truth for kwargs, single edit-point for future changes.
- [ ] **AC-SUBPROCESS-8** Repo-wide `forbidden-patterns` pre-commit hook (banning `shell=True`, `os.system`, `os.popen`, `eval(`, `exec(`, `__import__(`, `pickle.loads`) is already in effect; AC-COV-3 verifies it stays green after the dep additions.

### J. Closed error-reason discriminator + per-phase mapping

- [ ] **AC-ERR-1** `SandboxBackendError.reason` Literal is widened (additively) to include `"build_failed"`, `"build_timeout"`, `"buildx_missing"`, `"dns_resolution_failed"`, `"iptables_apply_failed"`, `"iptables_revert_failed"`, `"container_ip_unknown"` (eleven total members). `typing.get_args(SandboxBackendError.__init__.__annotations__["reason"])` (or the closed Literal location) returns the exact 11-tuple, byte-exact.
- [ ] **AC-ERR-2** `SandboxBuildFailed(SandboxBackendError)` subclass: `reason: Literal["build_failed", "build_timeout", "buildx_missing"]` (closed via type narrowing). `NetworkPolicyApplyFailed(SandboxBackendError)` subclass: `reason: Literal["dns_resolution_failed", "iptables_apply_failed", "iptables_revert_failed", "container_ip_unknown"]`. Subclass relationship preserved: `isinstance(exc, SandboxBackendError) is True`.
- [ ] **AC-ERR-3** `_wrap_subprocess_error(err, *, where) -> SandboxBuildFailed | NetworkPolicyApplyFailed` is the single call site that builds the wrapped exception. Pure. Parametrized over the mapping table:

  | Source | Where | Wrapped as | `reason` |
  |---|---|---|---|
  | `CalledProcessError` (`docker buildx`) | `build` | `SandboxBuildFailed` | `"build_failed"` |
  | `TimeoutExpired` (`docker buildx`) | `build` | `SandboxBuildFailed` | `"build_timeout"` |
  | `FileNotFoundError` (`docker` not on PATH) | `build` | `SandboxBuildFailed` | `"buildx_missing"` |
  | `CalledProcessError` (`iptables`) | `apply` | `NetworkPolicyApplyFailed` | `"iptables_apply_failed"` |
  | `socket.gaierror` / `socket.herror` | `apply.resolve` | `NetworkPolicyApplyFailed` | `"dns_resolution_failed"` |
  | Empty `container.attrs["NetworkSettings"]["IPAddress"]` | `apply.ip` | `NetworkPolicyApplyFailed` | `"container_ip_unknown"` |
  | `CalledProcessError` (`iptables -D`) during revert | `revert` | (logged WARNING only — not raised) | `"iptables_revert_failed"` |
- [ ] **AC-ERR-4** Wrapped exception's `__cause__` is the original — `raise X from err` form, never `raise X` standalone (preserves traceback).

### K. `DockerInDockerClient` edit (additive widening of S3-02)

- [ ] **AC-CLIENT-1** `_resolve_network_mode(spec) -> Literal["none", "bridge"]` is a NEW pure helper in `client.py`: returns `"bridge"` when `spec.network == "scoped"`, else `"none"`. Independently unit-tested over `[("none", "none"), ("scoped", "bridge")]`.
- [ ] **AC-CLIENT-2** `_build_container_kwargs(spec)` (S3-02) is EDITED: its existing hardcoded `"network_mode": "none"` becomes `"network_mode": _resolve_network_mode(spec)`. Existing S3-02 `_build_container_kwargs` golden fixture (if any) is regenerated with the parametrized form.
- [ ] **AC-CLIENT-3** `client.py::execute` STRUCTURAL CHANGE: container is now created with `entrypoint=["sleep", "infinity"]` (added to `_build_container_kwargs` via a new `_build_container_kwargs(spec, *, entrypoint)` parameter OR a fixed module-level `_SLEEP_ENTRYPOINT: Final[tuple[str, ...]] = ("sleep", "infinity")`). After `container.start()` and (conditionally) `network_policy.apply`, the workload is executed via `container.exec_run(spec.cmd, demux=True, ...)` (not via the container's main cmd). `exec_run`'s output streams into `stdout.log` / `stderr.log` via the existing `_demux_chunks` helper (renamed if needed).
- [ ] **AC-CLIENT-4** Try/finally structure (replaces S3-02 AC-EXEC-3):
  ```
  try:
      container = client.containers.create(**kwargs)
      try:
          container.start()
          if spec.network == "scoped":
              applied = network_policy.apply(spec, container=container)
          try:
              exec_result = container.exec_run(spec.cmd, demux=True, ...)
              # stream chunks, capture exit_code, etc.
          finally:
              if spec.network == "scoped":
                  network_policy.revert(applied)
      finally:
          container.remove(force=True)  # S3-02 cleanup discipline preserved
  except docker.errors.APIError as err:
      raise _wrap_api_error(err, where=...) from err
  ```
  Note: the `applied` name is only bound inside the `if`; the finally for revert is correctly scoped (only fires when `apply()` was called AND returned). If `apply()` raises, the inner `try` body never executes; the outer `finally` (`container.remove`) still runs.
- [ ] **AC-CLIENT-5** `EVENT_SANDBOX_DID_EXECUTE_*` events (from S3-02) gain a `network` field in their structured payload: `{run_id, label, backend, network: Literal["none","scoped"]}` (`completed` also includes `exit_code`, `duration_ms`).
- [ ] **AC-CLIENT-6** S3-02 AC-SPEC-DEFER-1 (`spec.network == "scoped"` raises NotImplementedError) is REMOVED — the test case parametrized over `(spec.network, expected_behavior)` flips to `("scoped", "ok")`.
- [ ] **AC-CLIENT-7** S3-02 AC-SPEC-DEFER-2 (`spec.egress_allowlist != []` raises NotImplementedError) is REMOVED. Test case flips to `("non_empty_allowlist", "ok")` (provided `spec.network == "scoped"`).

### L. Race-window closure

- [ ] **AC-RACE-1** Workload (`spec.cmd`) MUST NOT execute before `network_policy.apply()` returns. Asserted by an integration-style test that injects an `apply` spy that sleeps 100 ms, plus a `container.exec_run` spy; the test asserts that at the moment `apply` starts sleeping, `exec_run.call_count == 0`, and after `apply` returns, `exec_run.call_count == 1`.
- [ ] **AC-RACE-2** Container is created with `entrypoint=("sleep", "infinity")` (NOT with `spec.cmd` as the main cmd). Asserted by inspecting `fake_docker.containers.create.call_args.kwargs["entrypoint"]`.
- [ ] **AC-RACE-3** `spec.cmd` flows ONLY through `container.exec_run(spec.cmd, ...)` — never through `containers.create(cmd=...)`. Asserted by `fake_docker.containers.create.call_args.kwargs.get("cmd") is None` AND `fake_container.exec_run.call_args.args[0] == spec.cmd`.

### M. Stderr truncation (Phase-11-evidence safety)

- [ ] **AC-TRUNC-1** `_truncate_stderr(stderr: bytes, max_bytes: int) -> str` — pure helper: `stderr[:max_bytes].decode("utf-8", errors="replace")`. Returns a `str`. Unit-tested over: empty input, ≤ max_bytes input, exactly max_bytes input, > max_bytes input (asserts result is exactly `len(result.encode("utf-8")) ≤ max_bytes`), input ending mid-multi-byte-UTF-8 (asserts no `UnicodeDecodeError`).
- [ ] **AC-TRUNC-2** Adversarial fixture: 8 KiB of `b"\xc3\xa9" * 4096` (UTF-8 `é`, 2 bytes each) truncated at `_MAX_STDERR_BYTES = 4096` produces exactly 2048 `é` characters in the decoded string.

### N. Module purity (AST walker)

- [ ] **AC-PURE-1** `tests/sandbox/did/test_build_purity.py` exists; walks `build.py` AST; asserts `from __future__ import annotations` is first non-docstring statement.
- [ ] **AC-PURE-2** `tests/sandbox/did/test_network_policy_purity.py` exists; same shape, walks `network_policy.py`.
- [ ] **AC-PURE-3** `build.py` import allowlist (asserted by AST walk over top-level `ast.Import` + `ast.ImportFrom` nodes): stdlib (`datetime`, `pathlib`, `re`, `subprocess`, `types`, `typing`) + `pydantic` + `structlog` + `codegenie.sandbox.errors` + `codegenie.sandbox.logging`. Forbidden: `os.system`, `os.popen`, `pickle`, `yaml`/`pyyaml`, `docker` (build does NOT import the Docker SDK — subprocess is the only path), any LLM SDK.
- [ ] **AC-PURE-4** `network_policy.py` import allowlist: stdlib (`datetime`, `ipaddress`, `socket`, `subprocess`, `types`, `typing`, `collections.abc`) + `pydantic` + `structlog` + `codegenie.sandbox.errors` + `codegenie.sandbox.logging` + `codegenie.sandbox.did._docker_types` (for the `Container` shim type alias). Forbidden: same set as AC-PURE-3, plus `docker` itself (the SDK handle is passed in via DI from `client.py`).
- [ ] **AC-PURE-5** Module docstring of `build.py` cites `ADR-0001`, `ADR-0014` by number; `network_policy.py` cites `ADR-0001`, `ADR-0004`, `ADR-0009`, `ADR-0014`.
- [ ] **AC-PURE-6** Every structlog event emission references an `EVENT_*` constant from `codegenie.sandbox.logging` — zero bare-string event names in either file. AST walk asserts `Call(keywords=[keyword(arg='event', value=Constant(value=<str>))])` matches NEVER.
- [ ] **AC-PURE-7** Every `subprocess.run` invocation across both files has NO `keyword(arg='shell')` (defense-in-depth on `forbidden-patterns`).
- [ ] **AC-PURE-8** Module-level `Final` constants per AC-API-5 are positively pinned by AST walk: the literal values (`1800`, `4096`, `5`, `"iptables"`) appear in source as named `Final` constants, not as inline magic numbers in method bodies (catches a refactor that re-introduces `4096` inline in `_truncate_stderr` and silently diverges).
- [ ] **AC-PURE-9** `subprocess.run` appears EXACTLY ONCE across both files combined (inside `_default_runner`). AST walk over both files asserts the count.

### O. Event-name discipline (append-only to S1-01 + S3-02 table)

- [ ] **AC-EVT-1** Six new `Final[str]` constants appended to `src/codegenie/sandbox/logging.py` (alphabetized in sorted `__all__`):
  - `EVENT_SANDBOX_DID_BUILD_STARTED = "sandbox.did.build.started"`
  - `EVENT_SANDBOX_DID_BUILD_COMPLETED = "sandbox.did.build.completed"`
  - `EVENT_SANDBOX_DID_BUILD_FAILED = "sandbox.did.build.failed"`
  - `EVENT_SANDBOX_DID_NETWORK_POLICY_APPLIED = "sandbox.did.network_policy.applied"`
  - `EVENT_SANDBOX_DID_NETWORK_POLICY_REVERTED = "sandbox.did.network_policy.reverted"`
  - `EVENT_SANDBOX_DID_NETWORK_POLICY_APPLY_FAILED = "sandbox.did.network_policy.apply_failed"`
- [ ] **AC-EVT-2** All event-name strings match the CLAUDE.md namespace regex `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` AND the verb is one of `started/completed/failed/applied/reverted/apply_failed` (NOT `start/done/error`).
- [ ] **AC-EVT-3** Structured field set per event (asserted via `structlog.testing.capture_logs()` parametrized test):
  - `build.started`: `{tag, context_dir, timeout_seconds}`
  - `build.completed`: `{tag, exit_code, duration_ms, image_digest_present: bool}` (digest itself omitted from logs — leaks to Phase 11; `present:` flag is enough for telemetry)
  - `build.failed`: `{tag, reason, exit_code, stderr_truncated_512}`
  - `network_policy.applied`: `{container_id, rule_count, allowlist_count}`
  - `network_policy.reverted`: `{container_id, rule_count}`
  - `network_policy.apply_failed`: `{container_id, reason, where, rule_argv_redacted}` (`rule_argv_redacted` = the rule shape with the actual IP/host replaced by `"<redacted>"` — avoids logging the egress-allowlist contents to telemetry)
- [ ] **AC-EVT-4** Sort `__all__` after the additions (matches S1-01 HARDENED policy).

### P. Functional core / imperative shell (rule-of-three elevation)

- [ ] **AC-FCS-1** `build.py` pure helpers (≥ 4): `_build_argv`, `_parse_image_digest`, `_truncate_stderr`, `_wrap_subprocess_error`. Each is independently unit-testable; tests live in `tests/sandbox/did/test_build_helpers.py`.
- [ ] **AC-FCS-2** `network_policy.py` pure helpers (≥ 3): `_compute_rules`, `_compute_revert_rules`, `_validate_ip_literal`. Tests in `tests/sandbox/did/test_network_policy_helpers.py`.
- [ ] **AC-FCS-3** `build.py` impure shell: `build_image` (the only impure function); `_default_runner`, `_default_build_env` (boundary helpers — impure by necessity, tested via spies). The single `subprocess.run` call site (AC-DI-4) is in `_default_runner`.
- [ ] **AC-FCS-4** `network_policy.py` impure shell: `apply`, `revert`, `_default_runner`, `_default_resolver`. The single `subprocess.run` call site is in `_default_runner`. The single `socket.gethostbyname_ex` call site is in `_default_resolver`.
- [ ] **AC-FCS-5** `_build_argv(context_dir: Path, tag: str, dockerfile: Path | None, build_args: Mapping[str, str] | None) -> tuple[str, ...]` is pure: same input → same output. Parametrized unit test asserts byte-exact argv against golden snapshots `tests/golden/docker_buildx_argv_{minimal,with_dockerfile,with_build_args,with_dockerfile_and_build_args}.txt`.
- [ ] **AC-FCS-6** `_parse_image_digest` covered by AC-DIGEST-* tests.
- [ ] **AC-FCS-7** `_compute_rules` / `_compute_revert_rules` covered by AC-RULES-* tests.

### Q. structlog observability

- [ ] **AC-LOG-1** `apply()` calls `structlog.contextvars.bind_contextvars(container_id=container.id)` once at entry; all events inside inherit `container_id`.
- [ ] **AC-LOG-2** `build_image()` calls `bind_contextvars(tag=tag)` once at entry; all events inside inherit `tag`.
- [ ] **AC-LOG-3** Parametrized `structlog.testing.capture_logs()` test covers: (a) build happy path emits `build.started` + `build.completed` in order; (b) build failure emits `build.started` + `build.failed` (NOT `build.completed`); (c) apply happy path emits `network_policy.applied` once; (d) apply with partial failure emits `network_policy.applied` for each successful rule (none, since AC-APPLY-3 says we only emit on full success) + `network_policy.apply_failed` once; (e) revert happy path emits `network_policy.reverted` once.

### R. Argv golden snapshots (build)

- [ ] **AC-ARGV-1** `tests/golden/docker_buildx_argv_minimal.txt` — one line per argv element; corresponds to `_build_argv(Path("/tmp/ctx"), "test:1", dockerfile=None, build_args=None)`. Expected: `docker / buildx / build / --progress=plain / -t / test:1 / /tmp/ctx` (each on its own line).
- [ ] **AC-ARGV-2** `tests/golden/docker_buildx_argv_with_dockerfile.txt` — adds `-f / /tmp/Dockerfile.alt` between `--progress=plain` and `-t`.
- [ ] **AC-ARGV-3** `tests/golden/docker_buildx_argv_with_build_args.txt` — adds `--build-arg=NODE_VERSION=20 / --build-arg=NPM_REGISTRY=https://registry.npmjs.org` (sorted by key for determinism) between `--progress=plain` and `-t`.
- [ ] **AC-ARGV-4** `tests/golden/docker_buildx_argv_with_dockerfile_and_build_args.txt` — combines AC-ARGV-2 and AC-ARGV-3. Each fixture's bytes are compared byte-exact via `Path.read_text().splitlines() == list(actual_argv)`.

### S. Tests stay green + AST fence allowlist

- [ ] **AC-FENCE-1** `tests/schema/test_no_subprocess_outside_build_chokepoint.py` (S1-07) has its allowlist set EXTENDED additively (NOT replaced) to include `src/codegenie/sandbox/did/network_policy.py`. The diff to that test file is exactly one line. Test renames if any (e.g., `test_no_subprocess_outside_chokepoints`) are out of scope for this story; the allowlist is the change.
- [ ] **AC-FENCE-2** `tests/sandbox/did/test_client_purity.py` (S3-02) is amended to add `_resolve_network_mode` to the allowed-helper set (the import allowlist itself does not change — only the helper name list).

### T. Dependencies + tooling

- [ ] **AC-DEP-1** `pyproject.toml` is NOT modified by this story — both new files use stdlib (`subprocess`, `socket`, `ipaddress`, `re`, `pathlib`, `types`, `typing`, `collections.abc`, `datetime`) + `pydantic` (already a dep) + `structlog` (already a dep). `make fence` stays green.
- [ ] **AC-COV-1** `src/codegenie/sandbox/did/` coverage stays at line ≥ 95% AND branch ≥ 90% (Phase-5 standard, matches S1-02..S1-06, S3-01, S3-02).
- [ ] **AC-COV-2** `ruff check src/codegenie/sandbox/did/ tests/sandbox/did/ tests/golden/iptables_rules_*.txt`, `ruff format --check src/codegenie/sandbox/did/ tests/sandbox/did/`, `mypy --strict src/codegenie/sandbox/did/`, `pytest tests/sandbox/did/` all pass.
- [ ] **AC-COV-3** Repo-wide `make fence` + `make lint` + `pre-commit run --all-files` (including `forbidden-patterns`) stay green after this story lands.
- [ ] **AC-COV-4** TDD plan's red tests exist, are committed, and are now green.

## Implementation outline

1. **Land event constants first.** Append the six `EVENT_*` constants per AC-EVT-1 to `src/codegenie/sandbox/logging.py`, re-sort `__all__`. Run any S1-01 event-constant value-equality test (if present) and bump it.

2. **Widen `SandboxBackendError.reason` Literal in `src/codegenie/sandbox/errors.py`.** Add the seven new members per AC-ERR-1 (additive — existing six are unchanged). Add the two new subclasses `SandboxBuildFailed` and `NetworkPolicyApplyFailed` with their narrower Literal types per AC-ERR-2.

3. **Land `network_policy.py` first** (build doesn't depend on it; client edit depends on both).
   - Module docstring citing ADR-0001 / ADR-0004 / ADR-0009 / ADR-0014, with the `Known limitation:` paragraph (AC-DNS-5).
   - `from __future__ import annotations`.
   - Imports per AC-PURE-4.
   - Module-level `Final` constants per AC-API-5.
   - Pure helpers in order: `_validate_ip_literal`, `_compute_rules`, `_compute_revert_rules`.
   - Impure helpers: `_default_resolver`, `_default_runner`.
   - `AppliedPolicy` Pydantic model (frozen, extra=forbid).
   - `apply()` per AC-APPLY-1..AC-APPLY-3.
   - `revert()` per AC-REVERT-1..AC-REVERT-5.

4. **Land `build.py`.**
   - Module docstring citing ADR-0001 / ADR-0014.
   - `from __future__ import annotations`.
   - Imports per AC-PURE-3.
   - Module-level `Final` constants per AC-API-5 (timeout, max-stderr, image-digest regex).
   - Pure helpers in order: `_build_argv`, `_parse_image_digest`, `_truncate_stderr`, `_wrap_subprocess_error`.
   - Impure helpers: `_default_runner`, `_default_build_env`.
   - `BuildResult` Pydantic model (frozen, extra=forbid).
   - `build_image()` per AC-BUILD-1..AC-BUILD-4.

5. **Edit `client.py` (additive widening).**
   - Add `_resolve_network_mode` pure helper (AC-CLIENT-1).
   - Edit `_build_container_kwargs` to use `_resolve_network_mode` and add `entrypoint=_SLEEP_ENTRYPOINT` (AC-CLIENT-2, AC-RACE-2).
   - Restructure `execute()` per AC-CLIENT-4 (create with sleep entrypoint → start → conditional `network_policy.apply` → `exec_run(spec.cmd)` → conditional `network_policy.revert` in inner finally → `container.remove` in outer finally).
   - Remove S3-02 AC-SPEC-DEFER-1 and AC-SPEC-DEFER-2 raise-paths from `_validate_spec_supported` (per AC-CLIENT-6, AC-CLIENT-7).
   - Add `network` field to `EVENT_SANDBOX_DID_EXECUTE_*` event payloads (AC-CLIENT-5).

6. **Edit `tests/schema/test_no_subprocess_outside_build_chokepoint.py`** (S1-07) — single-line allowlist extension per AC-FENCE-1.

7. **Edit `tests/sandbox/did/test_client_purity.py`** (S3-02) — add `_resolve_network_mode` to the allowed-helper-name set per AC-FENCE-2; widen `network_mode` literal check from `"none"` to `Literal["none","bridge"]`.

8. **Land test files in red-first order:**
   - `tests/sandbox/did/test_build_purity.py` (AC-PURE-1..-9)
   - `tests/sandbox/did/test_network_policy_purity.py` (AC-PURE-2..-9)
   - `tests/sandbox/did/test_build_helpers.py` (AC-FCS-1, AC-FCS-5, AC-DIGEST-*, AC-TRUNC-*, AC-ARGV-*)
   - `tests/sandbox/did/test_network_policy_helpers.py` (AC-FCS-2, AC-RULES-*, AC-DNS-3, AC-FCS-7)
   - `tests/sandbox/did/test_build.py` (AC-BUILD-*, AC-DI-1, AC-DI-4, AC-DI-5, AC-ERR-*, AC-MODELS-1/-3/-4/-6/-8, AC-EVT-3 build-side, AC-LOG-2, AC-LOG-3 b/c)
   - `tests/sandbox/did/test_network_policy.py` (AC-APPLY-*, AC-DNS-1/-2/-4, AC-DI-2/-3, AC-MODELS-2/-5/-7, AC-EVT-3 network-side, AC-LOG-1, AC-LOG-3 a/d)
   - `tests/sandbox/did/test_network_policy_revert.py` (AC-REVERT-*, AC-LOG-3 e)
   - `tests/sandbox/did/test_client_network_integration.py` (AC-CLIENT-*, AC-RACE-*, AC-INTEG-1/-2)

9. **Generate the golden fixtures** in this exact order: argv goldens (AC-ARGV-*) → iptables-rule goldens (AC-RULES-5) → buildx-stderr fixtures (AC-DIGEST-3) → Pydantic-model JSON goldens (AC-MODELS-6/-7).

10. **Refactor pass.** Type hints, one-line docstring per pure helper, paragraph docstring per impure shell function citing ADR-0001 + ADR-0004 / ADR-0009. Verify `mypy --strict` clean. Verify coverage floor.

## TDD plan — red / green / refactor

Five test files (was three). Each cell maps tests to AC numbers; the executor writes them red first.

### Red — write the failing tests first

#### File 1 — `tests/sandbox/did/test_build_helpers.py`

```python
"""Pure-helper unit tests for did/build.py — AC-FCS-1, AC-FCS-5, AC-ARGV-*, AC-DIGEST-*, AC-TRUNC-*."""
from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.sandbox.did.build import (
    _MAX_STDERR_BYTES,
    _build_argv,
    _parse_image_digest,
    _truncate_stderr,
)


GOLDEN_DIR = Path(__file__).parent.parent.parent / "golden"


@pytest.mark.parametrize(
    "fixture, dockerfile, build_args",
    [
        ("minimal", None, None),
        ("with_dockerfile", Path("/tmp/Dockerfile.alt"), None),
        ("with_build_args", None, {"NODE_VERSION": "20", "NPM_REGISTRY": "https://registry.npmjs.org"}),
        ("with_dockerfile_and_build_args", Path("/tmp/Dockerfile.alt"), {"NODE_VERSION": "20"}),
    ],
)
def test_build_argv_byte_exact_against_golden(fixture, dockerfile, build_args):
    """A loose argv assertion is a security regression vector — pin byte-exact."""
    expected = (GOLDEN_DIR / f"docker_buildx_argv_{fixture}.txt").read_text().splitlines()
    actual = list(_build_argv(Path("/tmp/ctx"), "test:1", dockerfile, build_args))
    assert actual == expected, f"argv drift on {fixture}: {actual} vs {expected}"


@pytest.mark.parametrize(
    "fixture, expected_digest",
    [
        ("success_simple.txt", "sha256:" + "a" * 64),
        ("success_multi_stage.txt", "sha256:" + "b" * 64),
        ("cache_hit_only.txt", None),
        ("failure_no_digest.txt", None),
        ("uppercase_digest.txt", None),  # canonical form is lowercase hex
    ],
)
def test_parse_image_digest_against_buildkit_fixtures(fixture, expected_digest):
    raw = (Path(__file__).parent.parent.parent / "fixtures" / "buildx_stderr" / fixture).read_bytes()
    assert _parse_image_digest(raw) == expected_digest


def test_truncate_stderr_handles_utf8_boundary():
    """A naive `stderr[:N]` on UTF-8 mid-multi-byte can raise UnicodeDecodeError."""
    # `é` = b"\xc3\xa9" (2 bytes). 4096 / 2 = 2048 — truncation lands cleanly.
    # But shift by one byte and the last byte is a stranded continuation byte.
    s = (b"\xc3\xa9" * 2048) + b"\xc3"  # 4097 bytes, last byte stranded
    out = _truncate_stderr(s, _MAX_STDERR_BYTES)
    assert isinstance(out, str)
    assert len(out.encode("utf-8")) <= _MAX_STDERR_BYTES + 1  # +1 for the U+FFFD replacement char
```

#### File 2 — `tests/sandbox/did/test_network_policy_helpers.py`

```python
"""Pure-helper unit tests for did/network_policy.py — AC-FCS-2, AC-RULES-*, AC-DNS-3."""
from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from codegenie.sandbox.did.network_policy import (
    _compute_revert_rules,
    _compute_rules,
    _IPTABLES_BIN,
    _validate_ip_literal,
    AppliedPolicy,
)

_FIXTURE_CONTAINER_IP: str = "172.17.0.2"
GOLDEN_DIR = Path(__file__).parent.parent.parent / "golden"


@pytest.mark.parametrize(
    "fixture, resolved_ips",
    [
        ("empty", ()),
        ("scoped_npmjs", ("93.184.216.34",)),
        ("scoped_multi", ("93.184.216.34", "151.101.1.69", "104.16.85.20")),
    ],
)
def test_compute_rules_matches_golden(fixture, resolved_ips):
    expected = (GOLDEN_DIR / f"iptables_rules_{fixture}.txt").read_text().splitlines()
    actual = [" ".join(rule) for rule in _compute_rules(resolved_ips, _FIXTURE_CONTAINER_IP)]
    assert actual == expected


@given(
    st.lists(st.from_regex(r"^(\d{1,3}\.){3}\d{1,3}\Z", fullmatch=True), min_size=0, max_size=5),
    st.from_regex(r"^(\d{1,3}\.){3}\d{1,3}\Z", fullmatch=True),
)
def test_compute_rules_invariants(resolved_ips_list, container_ip):
    """Properties: (a) DROP is always last, (b) container_ip appears once per rule
    at position 4, (c) ordering is input-stable, (d) rule_count == len(input)+1."""
    resolved = tuple(resolved_ips_list)
    rules = _compute_rules(resolved, container_ip)
    assert len(rules) == len(resolved) + 1
    assert rules[-1][-1] == "DROP"
    for i, ip in enumerate(resolved):
        assert rules[i][6] == ip  # input-order stability
        assert rules[i][-1] == "ACCEPT"
    for rule in rules:
        assert rule[4] == container_ip
        assert rule.count(container_ip) == 1


def test_compute_rules_empty_is_pure_deny_all():
    rules = _compute_rules((), _FIXTURE_CONTAINER_IP)
    assert len(rules) == 1
    assert rules[0][-1] == "DROP"


@pytest.mark.parametrize(
    "s, expected",
    [
        ("127.0.0.1", True),
        ("172.17.0.2", True),
        ("::1", True),
        ("registry.npmjs.org", False),
        ("", False),
        ("999.999.999.999", False),
        ("not-an-ip", False),
    ],
)
def test_validate_ip_literal(s, expected):
    assert _validate_ip_literal(s) is expected
```

#### File 3 — `tests/sandbox/did/test_build.py`

```python
"""Core build_image() tests — AC-BUILD-*, AC-DI-*, AC-ERR-*, AC-MODELS-* (build side)."""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codegenie.sandbox.did.build import build_image, BuildResult, SandboxBuildFailed


def _spy_runner_factory(returncode=0, stdout=b"", stderr=b"#1 writing image sha256:" + b"a" * 64 + b" done"):
    """Returns a runner spy that records all calls and returns a CompletedProcess."""
    calls: list = []

    def runner(argv, *, timeout, cwd=None, env=None):
        calls.append({"argv": argv, "timeout": timeout, "cwd": cwd, "env": env})
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    runner.calls = calls  # type: ignore[attr-defined]
    return runner


def test_build_image_happy_path(tmp_path):
    runner = _spy_runner_factory()
    result = build_image(tmp_path, "test:1", build_args={"NODE_VERSION": "20"}, runner=runner)
    assert isinstance(result, BuildResult)
    assert result.exit_code == 0
    assert result.image_digest == "sha256:" + "a" * 64
    assert result.started_at.tzinfo == timezone.utc
    assert result.ended_at >= result.started_at
    assert len(runner.calls) == 1
    assert runner.calls[0]["cwd"] == tmp_path


def test_build_image_nonzero_exit_raises_build_failed(tmp_path):
    runner = _spy_runner_factory(returncode=1, stderr=b"build error")
    with pytest.raises(SandboxBuildFailed) as exc:
        build_image(tmp_path, "test:1", runner=runner)
    assert exc.value.reason == "build_failed"
    assert "build error" in exc.value.details["stderr_truncated"]


def test_build_image_timeout_raises_build_timeout(tmp_path):
    def runner(argv, *, timeout, cwd=None, env=None):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=timeout, stderr=b"partial output")

    with pytest.raises(SandboxBuildFailed) as exc:
        build_image(tmp_path, "test:1", runner=runner, timeout_seconds=60)
    assert exc.value.reason == "build_timeout"


def test_build_image_buildx_missing_raises(tmp_path):
    def runner(argv, *, timeout, cwd=None, env=None):
        raise FileNotFoundError(2, "No such file or directory: 'docker'")

    with pytest.raises(SandboxBuildFailed) as exc:
        build_image(tmp_path, "test:1", runner=runner)
    assert exc.value.reason == "buildx_missing"
    assert isinstance(exc.value.__cause__, FileNotFoundError)


def test_build_image_no_mock_patch_in_module():
    """Defense against drift back to mock.patch — AC-DI-5."""
    import tests.sandbox.did.test_build as me

    source = Path(me.__file__).read_text()
    assert 'mock.patch("subprocess' not in source
    assert "patch('subprocess" not in source
```

#### File 4 — `tests/sandbox/did/test_network_policy.py`

```python
"""Core apply()/revert() tests — AC-APPLY-*, AC-DNS-*, AC-DI-2/-3, AC-MODELS-2/-5/-7."""
from __future__ import annotations

import socket
import subprocess
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from codegenie.sandbox.contract import SandboxSpec
from codegenie.sandbox.errors import NetworkPolicyApplyFailed
from codegenie.sandbox.did.network_policy import AppliedPolicy, apply, revert


def _fake_container(ip="172.17.0.2", container_id="abc123"):
    c = MagicMock()
    c.id = container_id
    c.attrs = {"NetworkSettings": {"IPAddress": ip}}
    return c


def _ok_runner(call_log: list):
    def runner(argv, *, timeout, cwd=None, env=None):
        call_log.append(argv)
        return subprocess.CompletedProcess(argv, 0, b"", b"")
    return runner


def test_apply_happy_path(scoped_spec):
    calls: list = []
    container = _fake_container()
    applied = apply(
        scoped_spec,
        container=container,
        runner=_ok_runner(calls),
        resolver=lambda h: ["93.184.216.34"],
    )
    assert isinstance(applied, AppliedPolicy)
    assert applied.container_id == container.id
    assert len(applied.applied_rules) == 2  # one ACCEPT, one DROP
    assert applied.applied_rules[-1][-1] == "DROP"
    assert len(calls) == 2  # one runner call per rule


def test_apply_dns_failure_raises_and_applies_zero_rules(scoped_spec):
    calls: list = []
    container = _fake_container()

    def boom_resolver(host):
        raise socket.gaierror(-2, "Name or service not known")

    with pytest.raises(NetworkPolicyApplyFailed) as exc:
        apply(scoped_spec, container=container, runner=_ok_runner(calls), resolver=boom_resolver)
    assert exc.value.reason == "dns_resolution_failed"
    assert len(calls) == 0


def test_apply_container_ip_unknown_raises(scoped_spec):
    container = _fake_container(ip="")  # empty IP — container not on bridge network
    with pytest.raises(NetworkPolicyApplyFailed) as exc:
        apply(scoped_spec, container=container, runner=lambda *a, **k: pytest.fail("no rule should run"),
              resolver=lambda h: ["1.2.3.4"])
    assert exc.value.reason == "container_ip_unknown"


def test_apply_partial_failure_rolls_back(scoped_spec):
    """If rule 3/4 fails, rules 0/1/2 must be reverted (in reverse order) before the raise."""
    spec_multi = scoped_spec.model_copy(update={"egress_allowlist": ["a.example", "b.example", "c.example"]})
    calls: list = []

    def runner(argv, *, timeout, cwd=None, env=None):
        calls.append(argv)
        # Fail on the 3rd rule (0-indexed: call #2). Three ACCEPTs + one DROP = 4 forward rules.
        if len(calls) == 3:
            return subprocess.CompletedProcess(argv, 1, b"", b"iptables: rule rejected")
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    def resolver(host):
        return {"a.example": ["1.1.1.1"], "b.example": ["2.2.2.2"], "c.example": ["3.3.3.3"]}[host]

    with pytest.raises(NetworkPolicyApplyFailed):
        apply(spec_multi, container=_fake_container(), runner=runner, resolver=resolver)
    # 3 forward attempts (incl. the failure) + 2 reverts (for rules 0, 1, in reverse) = 5 calls
    assert len(calls) == 5
    # The last two argvs are revert (-D) of rules 1 then 0
    assert calls[-2][1] == "-D"
    assert calls[-1][1] == "-D"


def test_revert_is_idempotent(applied_policy_fixture):
    calls: list = []
    revert(applied_policy_fixture, runner=_ok_runner(calls))
    revert(applied_policy_fixture, runner=_ok_runner(calls))
    # Second revert call also runs every rule (idempotent — kernel returns "no such rule" which we swallow)
    assert len(calls) == 2 * len(applied_policy_fixture.applied_rules)


def test_revert_swallows_per_rule_failures(applied_policy_fixture):
    def runner(argv, *, timeout, cwd=None, env=None):
        return subprocess.CompletedProcess(argv, 1, b"", b"iptables: bad rule")
    # Must not raise.
    revert(applied_policy_fixture, runner=runner)
```

#### File 5 — `tests/sandbox/did/test_client_network_integration.py`

```python
"""S3-02 widening: client.py end-to-end with network=scoped — AC-CLIENT-*, AC-RACE-*."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from codegenie.sandbox.did.client import DockerInDockerClient
from codegenie.sandbox.contract import SandboxSpec


def test_no_egress_window_before_policy_applied(monkeypatch, scoped_spec):
    """If exec_run runs before apply() returns, the workload can egress freely.

    This test fails immediately on any ordering bug in execute()'s try/finally.
    """
    apply_started_at: list = []
    exec_started_at: list = []

    fake_container = MagicMock(); fake_container.id = "abc"
    fake_container.attrs = {"NetworkSettings": {"IPAddress": "172.17.0.2"}}
    fake_container.wait.return_value = {"StatusCode": 0}
    fake_container.exec_run.side_effect = lambda *a, **k: (exec_started_at.append(time.monotonic()),
                                                          MagicMock(exit_code=0, output=(b"", b"")))[1]
    fake_docker = MagicMock(); fake_docker.containers.create.return_value = fake_container

    def slow_apply(spec, *, container, **kw):
        apply_started_at.append(time.monotonic())
        time.sleep(0.05)
        return MagicMock()

    monkeypatch.setattr("codegenie.sandbox.did.client.network_policy.apply", slow_apply)
    monkeypatch.setattr("codegenie.sandbox.did.client.network_policy.revert", lambda a: None)

    client = DockerInDockerClient(docker_factory=lambda url: fake_docker)
    client.execute(scoped_spec)

    assert apply_started_at[0] < exec_started_at[0], "exec_run started before apply returned"


def test_workload_cmd_flows_through_exec_run_not_create(monkeypatch, scoped_spec):
    fake_container = MagicMock(); fake_container.id = "abc"
    fake_container.attrs = {"NetworkSettings": {"IPAddress": "172.17.0.2"}}
    fake_container.wait.return_value = {"StatusCode": 0}
    fake_container.exec_run.return_value = MagicMock(exit_code=0, output=(b"", b""))
    fake_docker = MagicMock(); fake_docker.containers.create.return_value = fake_container

    monkeypatch.setattr("codegenie.sandbox.did.client.network_policy.apply", lambda *a, **k: MagicMock())
    monkeypatch.setattr("codegenie.sandbox.did.client.network_policy.revert", lambda a: None)

    DockerInDockerClient(docker_factory=lambda url: fake_docker).execute(scoped_spec)

    create_kwargs = fake_docker.containers.create.call_args.kwargs
    assert create_kwargs.get("cmd") is None
    assert tuple(create_kwargs["entrypoint"]) == ("sleep", "infinity")
    assert fake_container.exec_run.call_args.args[0] == scoped_spec.cmd


def test_revert_runs_when_workload_raises(monkeypatch, scoped_spec):
    """If revert is skipped on error, iptables rules leak. Mocks at the real boundary, not the function."""
    revert_calls: list = []

    fake_container = MagicMock(); fake_container.id = "abc"
    fake_container.attrs = {"NetworkSettings": {"IPAddress": "172.17.0.2"}}
    fake_container.exec_run.side_effect = RuntimeError("workload boom")
    fake_docker = MagicMock(); fake_docker.containers.create.return_value = fake_container

    sentinel_applied = MagicMock()
    monkeypatch.setattr("codegenie.sandbox.did.client.network_policy.apply", lambda *a, **k: sentinel_applied)
    monkeypatch.setattr("codegenie.sandbox.did.client.network_policy.revert", lambda a: revert_calls.append(a))

    with pytest.raises(RuntimeError):
        DockerInDockerClient(docker_factory=lambda url: fake_docker).execute(scoped_spec)
    assert revert_calls == [sentinel_applied]
```

### Green — make it pass

- Append the six event constants + extend `SandboxBackendError.reason` Literal additively.
- Land `network_policy.py` per AC-API-2/-4 / AC-PURE-2/-4 / AC-MODELS-2 / AC-APPLY-* / AC-REVERT-* / AC-DNS-* / AC-RULES-*.
- Land `build.py` per AC-API-1/-3 / AC-PURE-1/-3 / AC-MODELS-1/-3 / AC-BUILD-* / AC-DIGEST-* / AC-TRUNC-* / AC-ARGV-*.
- Edit `client.py` per AC-CLIENT-*; add `_resolve_network_mode`; restructure `execute()` per AC-RACE-1..-3.
- Generate golden fixtures (argv, iptables rules, buildx stderr).
- Extend `tests/schema/test_no_subprocess_outside_build_chokepoint.py` allowlist (one-line additive edit).

### Refactor — clean up

- Extract `_DEFAULT_RUN_KWARGS` constant per AC-SUBPROCESS-1 in both files.
- Top-of-file docstrings citing ADR-0001 + ADR-0004 / ADR-0009 as the only justification for `subprocess`.
- structlog events with `rule_argv_redacted` (no raw rule content — golden file is the source of truth) but `rule_count` present.
- `mypy --strict` quarantine note (only `_default_runner`'s `subprocess.CompletedProcess[bytes]` return needs a cast).

## Files to touch

| Path | Action | Why |
|---|---|---|
| `src/codegenie/sandbox/errors.py` | EDIT | Widen `SandboxBackendError.reason` Literal additively; add `SandboxBuildFailed` + `NetworkPolicyApplyFailed` subclasses (AC-ERR-1, AC-ERR-2). |
| `src/codegenie/sandbox/logging.py` | EDIT | Append six `EVENT_*` constants + re-sort `__all__` (AC-EVT-1, AC-EVT-4). |
| `src/codegenie/sandbox/did/network_policy.py` | NEW | iptables subprocess chokepoint + pure rule helpers + DNS resolution + AppliedPolicy model. |
| `src/codegenie/sandbox/did/build.py` | NEW | `docker buildx` subprocess chokepoint + pure argv/digest/truncation helpers + BuildResult model. |
| `src/codegenie/sandbox/did/client.py` | EDIT | Wire `network_policy.apply`/`revert` into try/finally; switch `_build_container_kwargs` to use `_resolve_network_mode`; restructure `execute()` create→start→apply→exec_run→revert→remove (AC-CLIENT-*, AC-RACE-*). |
| `src/codegenie/sandbox/did/_docker_types.py` | EDIT | Widen `ContainerKwargs.network_mode` to `Literal["none", "bridge"]`; add `entrypoint` field. |
| `tests/schema/test_no_subprocess_outside_build_chokepoint.py` | EDIT | One-line allowlist additive extension for `network_policy.py` (AC-FENCE-1). |
| `tests/sandbox/did/test_client_purity.py` | EDIT | Add `_resolve_network_mode` to allowed-helper set; widen `network_mode` literal check (AC-FENCE-2). |
| `tests/sandbox/did/test_build_purity.py` | NEW | Module-purity AST walker for `build.py` (AC-PURE-1, AC-PURE-3, AC-PURE-5..-9). |
| `tests/sandbox/did/test_network_policy_purity.py` | NEW | Module-purity AST walker for `network_policy.py` (AC-PURE-2, AC-PURE-4, AC-PURE-5..-9). |
| `tests/sandbox/did/test_build_helpers.py` | NEW | `_build_argv` / `_parse_image_digest` / `_truncate_stderr` unit tests (AC-FCS-1, AC-FCS-5, AC-DIGEST-*, AC-TRUNC-*, AC-ARGV-*). |
| `tests/sandbox/did/test_network_policy_helpers.py` | NEW | `_compute_rules` / `_compute_revert_rules` / `_validate_ip_literal` unit tests with hypothesis property tests (AC-FCS-2, AC-RULES-*, AC-DNS-3, AC-FCS-7). |
| `tests/sandbox/did/test_build.py` | NEW | Core `build_image` tests + error path table + DI-port + no-mock-patch defense (AC-BUILD-*, AC-DI-1/-4/-5, AC-ERR-*, AC-MODELS-1/-3/-4/-6/-8, AC-EVT-3 build-side, AC-LOG-2/-3). |
| `tests/sandbox/did/test_network_policy.py` | NEW | Core `apply` tests + DNS failure + container-IP failure + partial-rollback (AC-APPLY-*, AC-DNS-1/-2/-4, AC-DI-2/-3, AC-MODELS-2/-5/-7, AC-EVT-3 net-side, AC-LOG-1/-3). |
| `tests/sandbox/did/test_network_policy_revert.py` | NEW | `revert` idempotency + per-rule failure swallow + binary-missing path (AC-REVERT-*, AC-LOG-3 e). |
| `tests/sandbox/did/test_client_network_integration.py` | NEW | Race-window closure + workload-via-exec_run + revert-on-workload-failure (AC-CLIENT-*, AC-RACE-*, AC-INTEG-1/-2). |
| `tests/golden/iptables_rules_empty.txt` | NEW | Empty allowlist → single DROP rule. |
| `tests/golden/iptables_rules_scoped_npmjs.txt` | NEW | One IP → one ACCEPT + DROP. |
| `tests/golden/iptables_rules_scoped_multi.txt` | NEW | Three IPs → three ACCEPTs + DROP. |
| `tests/golden/docker_buildx_argv_minimal.txt` | NEW | Argv for `_build_argv(ctx, tag, None, None)`. |
| `tests/golden/docker_buildx_argv_with_dockerfile.txt` | NEW | + `-f /path/to/Dockerfile.alt`. |
| `tests/golden/docker_buildx_argv_with_build_args.txt` | NEW | + sorted `--build-arg=K=V`. |
| `tests/golden/docker_buildx_argv_with_dockerfile_and_build_args.txt` | NEW | Both. |
| `tests/fixtures/buildx_stderr/{success_simple,success_multi_stage,cache_hit_only,failure_no_digest,uppercase_digest}.txt` | NEW | BuildKit `--progress=plain` stderr fixtures (AC-DIGEST-3). |
| `tests/fixtures/sandbox/{build_result_minimal,applied_policy_npmjs}.json` | NEW | Pydantic-model round-trip goldens (AC-MODELS-6, AC-MODELS-7). |
| `tests/sandbox/did/conftest.py` | EDIT | Add `scoped_spec` + `applied_policy_fixture` fixtures consumed by multiple test files. |

## Out of scope

- Firecracker network policy (host-side nftables) — **S6-02 + ADR-0009**.
- Live integration against a real Docker daemon — **S3-07**.
- `--allow-test-network` CLI flag widening `egress_allowlist` — **S8-02**.
- Validating that the iptables rules actually drop packets — golden file is the contract; behavioral verification is the live integration test in **S3-07**.
- Multi-phase `phases:` collapse (one `network` per phase) — **S3-05** owns the catalog → flat-spec collapse.
- `copy_in` / `copy_out` plumbing — **S3-04** (this story DOES NOT widen S3-02 AC-SPEC-DEFER-3 / AC-SPEC-DEFER-4).
- `time_budget_seconds` SIGKILL enforcement — **S3-04** (this story DOES NOT widen S3-02 AC-SPEC-DEFER-6).
- `enable_trace=True` trace capture — **S4-03** (this story DOES NOT widen S3-02 AC-SPEC-DEFER-5).
- `NetworkPolicyApplier` Protocol abstraction — deferred until rule-of-three reaches with a third backend (Phase 7+ gVisor or similar) per ADR-0006.
- Migration to `ipset` for high-rotation CDN hostnames — Phase 7+ (acknowledged limitation in AC-DNS-5).
- `pyproject.toml` dep additions — none needed (AC-DEP-1).

## Notes for the implementer

- **The AST fence runs on every PR.** If you `import subprocess` in `client.py` or any other file outside the three chokepoints, the PR fails. Push the call into one of the two new chokepoint files and have `client.py` import the function, not `subprocess`. Pre-commit's `forbidden-patterns` hook additionally guards `shell=True`, `os.system`, `os.popen` repo-wide.

- **iptables `-d <hostname>` resolves at rule-add time only** (per netfilter docs). DO NOT pass hostnames to `_compute_rules` — pass pre-resolved IP literals. The `_resolve_egress_allowlist` impure step (calling `socket.gethostbyname_ex`) is the boundary. CDN hostnames with rotating IPs are an acknowledged limitation (AC-DNS-5); the migration to `ipset` is Phase-7+ and out of scope here.

- **Race window closure is structural, not a sleep**. The S3-02 pattern of `containers.create(cmd=spec.cmd)` + `start()` + log-stream + `wait()` cannot guarantee the workload doesn't egress between `start()` returning and the first `iptables` rule being installed. The fix is `containers.create(entrypoint=("sleep","infinity"))` + `start()` + (conditional) `network_policy.apply(...)` + `container.exec_run(spec.cmd, demux=True)` + (conditional) `network_policy.revert(...)` + `remove(force=True)`. See AC-CLIENT-4 for the precise try/finally layout.

- **iptables on Docker Desktop macOS runs inside the embedded Linux VM.** The orchestrator's `subprocess.run(["iptables", ...])` invocation is routed via `docker run --rm --net=host --privileged ...`? **NO** — the iptables binary on Docker Desktop's host (macOS) does not exist; the iptables calls run inside the *workload container's* network namespace via `docker run --rm --net=container:<container_id> --cap-add=NET_ADMIN ...` style pattern, OR they run inside Docker Desktop's embedded VM via SSH-into-VM. **Production-grade choice**: run `iptables` *inside a privileged sidecar container* attached to the workload's network namespace. **For S3-03 (which never executes on a real daemon — S3-07 owns that)**: leave the `subprocess.run(["iptables", ...])` shape as-is; the live-integration test in S3-07 will resolve the macOS host vs sidecar question + document the chosen path in this story's module docstring at S3-07-time. This deferral is acceptable because: (a) `_compute_rules` is pure and unit-tested via golden file, (b) the argv shape is the contract, (c) the live-execution path is one impure shell function. Track this in the module docstring's `Known limitation:` paragraph (AC-DNS-5 covers DNS; add a parallel paragraph here for the iptables-execution-context question, marked `TODO(S3-07):`).

- **`_compute_rules` must take a fixed `container_ip` argument (not call any IP resolver inside)** so it's pure and golden-testable. The IP resolution (`container.attrs["NetworkSettings"]["IPAddress"]`) sits in `apply()`, which is the impure shell.

- **DON'T `shell=True` on `subprocess.run`** — argv-list form only. The `forbidden-patterns` hook will catch you. The `_default_runner` in both files is the single edit point if you ever need to revisit subprocess kwargs.

- **Closed Literal discriminator pattern** (S3-02 HARDENED set the precedent): when adding a new error kind, widen `SandboxBackendError.reason` Literal additively + add a subclass with a narrower Literal type. Never invent a free-form `str` reason. The `typing.get_args` assertion in AC-ERR-1 will catch a stray `str` reason at test time.

- **DI-port pattern** (third concrete consumer): every external interaction has a kwarg-only port — `runner=_default_runner` for `subprocess.run`, `resolver=_default_resolver` for DNS, `docker_factory=_default_docker_factory` (from S3-02) for the SDK. Tests inject directly; NEVER `unittest.mock.patch("subprocess.run")` or `mock.patch("socket.gethostbyname_ex")`. Defense against drift back to mock magic is encoded in AC-DI-5 (a meta-test that greps `tests/sandbox/did/` for `mock.patch("subprocess`).

- **FCS pattern** (third concrete consumer): pure helpers carry the logic; impure shells (`build_image`, `apply`, `revert`) are thin orchestrators. Test pure helpers in `test_*_helpers.py` files; test impure shells in `test_<file>.py` with `runner` / `resolver` / `container` injected.

- **Rule of three for `NetworkPolicyApplier` Protocol**: S3-03 + S6-02 (Firecracker host-side nftables) = two backends. Rule-of-three not reached. Plain module-level `apply`/`revert` functions are correct today. When a third backend lands (gVisor in Phase 7+, or any other), collapse to a Protocol per ADR-0006: `class NetworkPolicyApplier(Protocol): def apply(...) -> AppliedPolicy: ...; def revert(applied) -> None: ...` plus a `register_network_policy_backend(backend_name)` decorator mirroring S1-05's pattern. Document the deferral here so the future implementer doesn't have to re-derive the decision.

- **Rule-of-three deferral for shared subprocess constants**: `_DEFAULT_RUN_KWARGS` is currently duplicated between `build.py` and `network_policy.py`. Two consumers ≠ rule-of-three. DO NOT hoist into a `sandbox/did/_subprocess.py` shared module; when a third consumer lands (Phase 7+ distroless build subprocess, or similar), promote then.

- **structlog redaction:** event payloads MUST NOT log raw iptables argv (leaks `egress_allowlist` contents — potentially sensitive routing topology) NOR the raw image digest (leaks build provenance to telemetry pipelines that downstream consumers may not be cleared for). AC-EVT-3 pins what to log; AC-EVT-3 `rule_argv_redacted` is a sample redaction shape.

- **Coverage floor (line ≥ 95% AND branch ≥ 90%)** is consistent with Phase-5 standard. The DI-port pattern is what makes this achievable: every external surface has an injectable port, every path through the impure shell is testable without mocks.

- **The `applied_at` timestamp in `AppliedPolicy` is required (tz-aware UTC)** — used by Phase 11 evidence bundle to order events. Don't make it optional. AC-MODELS-2 pins it.

- **`SandboxBuildFailed.__cause__` / `NetworkPolicyApplyFailed.__cause__`** must always carry the original exception (raise-from form). Phase 11 evidence bundle shows the traceback to the reviewer; a `raise X` standalone breaks the chain.

- **`make fence` (ADR-0002) stays green** — no `docker`, no LLM SDK added to the closure surface. `pyproject.toml` is untouched (AC-DEP-1).

- **Forward-pointer to S6-02**: when Firecracker host-side nftables lands, the shape will be `sandbox/firecracker/network_policy.py::apply(spec, *, microvm_handle, runner=_default_runner) -> AppliedPolicy` — same `AppliedPolicy` (or a Firecracker-specific variant if the rule set diverges substantially; ADR amendment if so). The `apply`/`revert` callable signature is the cross-backend forward-compat anchor.

- **Forward-pointer to S3-04**: `BuildResult` is currently internal to `build.py`. S3-04's `copy_out` plumbing reads `SandboxRun.copy_out_root` (already populated by S3-02); `BuildResult` does NOT need to be re-exported unless Phase-7 distroless or Phase-11 evidence bundle keys on it directly. Defer that decision.

- **Forward-pointer to Phase 13 (cost ledger)**: `SandboxBackendError.reason` is the discriminator field Phase 13 keys on. The eleven-member union AC-ERR-1 widens to is now the contract for cost-attribution buckets. Any future reason addition needs an additive widening + Phase 13 cost-bucket addition; closed Literal catches drift.
