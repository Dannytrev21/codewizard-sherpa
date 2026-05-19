# Story S4-02 — `BwrapAdapter` (Linux) — `bwrap --unshare-all` + seccomp + netns

**Step:** Step 4 — SubprocessJail Port + Bwrap + sandbox-exec + ALLOWED_BINARIES amendment
**Status:** HARDENED
**Effort:** L
**Depends on:** S4-01 (`SubprocessJail` Protocol, `JailedSubprocessSpec`, `JailedSubprocessResult` discriminated union, `NetworkPolicy = DenyAll | RegistryAllowlist` sum); transitively S1-03 (sum types). **Precondition:** S4-05 must land first OR co-land — it adds `bwrap` to `ALLOWED_BINARIES` AND removes `bwrap`/`bubblewrap` from `tests/unit/test_exec.py::test_allowed_binaries_closed_set_regression` (lines 362-363). Without S4-05, this story's `run_allowlisted("bwrap", ...)` calls fail the chokepoint check before any spawn. S4-04 strongly preferred (real `SandboxedPath` for integration tests); unit tests use `FakeSandboxedPath` shim.
**ADRs honored:** 03-ADR-0006 (`BwrapAdapter` is the Linux Adapter of the `SubprocessJail` Port; bwrap command-line and seccomp filter pinned in §Decision); 03-ADR-0012 (`bwrap` added to `ALLOWED_BINARIES` — S4-05 lands the data change; this story is the consumer).
**Doc-debt surfaced (deferred):** (a) ADR-0012 §Decision wording "the SubprocessJail adapters wrap bwrap / sandbox-exec via `run_external_cli`" is documentation drift — the existing `run_external_cli` is the Phase 2 probe-binary chokepoint and already does its own bwrap-wrapping (`_maybe_wrap_with_bwrap`, `src/codegenie/exec/__init__.py:428-482`). SubprocessJail adapters route through `run_allowlisted` (which accepts `env_extra` and performs a single allowlist check on the outer `bwrap` argv0). Follow-up: amend ADR-0012 §Decision in a doc-only story. (b) `High-level-impl.md:128` says "Test that exits 0 when `bwrap` missing must `pytest.skip` (not silently pass)" — sloppy wording that contradicts the same file's line 310 + ADR-0006 §Consequences ("fail the job — not skip — when on Linux and bwrap missing"). Per CLAUDE.md Rule 7, the more-recent + more-specific source (ADR + L310) wins; this story's AC-8 enforces fail-not-skip. Surface for the next phase-arch-design refresh.

## Validation notes (phase-story-validator, 2026-05-18)

The phase-story-validator hardened this story. Detailed report at `_validation/S4-02-bwrap-adapter-linux.md`. Summary of in-place edits:

- **Chokepoint correction (block).** Story originally prescribed `run_external_cli` calls with an `env_extra` parameter that doesn't exist on that function and would trigger double-bwrap-wrapping. Rewritten to call `run_allowlisted` directly — the function that actually has `env_extra` and performs a single allowlist check without implicit bwrap-wrap. Coordinated with S4-05 precondition (ALLOWED_BINARIES amendment + closed-set regression-test update). See doc-debt note above.
- **Runtime-Protocol fix (block).** AC-1 no longer uses `isinstance(BwrapAdapter(), SubprocessJail)` (S4-01 AC-2 pins SubprocessJail as NOT `@runtime_checkable`; isinstance would `TypeError`). Replaced with structural mypy + `inspect.signature` check + `_StubJail`-style call-site exercise.
- **Seccomp dep decision (block).** Story originally said "either libseccomp Python bindings (`pyseccomp`) or hand-written BPF — either is fine." Mandated hand-written BPF + `tools/seccomp/build_filter.py` helper. The six syscalls are a fixed list — ~30 lines of `struct.pack` BPF bytecode using `linux/seccomp.h` constants. No new Python runtime dependency; no ADR amendment required.
- **Mutation-resistance hardening.** AC-4 grep → AST walk (catches `from subprocess import run`, `getattr(subprocess, ...)`, `os.exec*`, `os.spawn*`); AC-5 sentinel-string fakes → real-shape `ProcessResult` mocks with explicit SIGKILL discriminator (timeout-vs-OOM tie-break pinned); AC-3 helper-boundary check supplemented with integration-tier kernel-boundary test (`unshare -U /bin/true` inside live jail → non-zero exit with SIGSYS); AC-11 dead loop removed; AC-12 fixture details + negative control pinned.
- **New ACs (coverage gaps).** AC-16 typed-error fence (no bare exception escapes Port boundary); AC-17 determinism property (same spec → same argv + same seccomp bytes); AC-18 property-based tests (DenyAll-no-share-net, allowlist-host-coverage, verbatim-cmd-preservation); AC-19 cleanup-on-exception; AC-20 concurrent-run serialization; AC-21 CAP_NET_ADMIN-absent typed-failure path; AC-22 stateless-across-calls.
- **Design-pattern surfacing.** AC-23 `_classify_outcome` extracted to a shared, pure module (consumed by `SandboxExecAdapter` in S4-03; rule-of-two satisfied at the boundary where the second adapter would otherwise copy-paste). AC-24 `Syscall` `StrEnum` + module-level `_BLOCKED_SYSCALLS: Final[frozenset[Syscall]]` (no primitive obsession on syscall names). AC-25 `match spec.network` on `NetworkPolicy` sum (exhaustive; mypy proves it).
- **Implementation outline corrections.** `spec.cwd.absolute` → `str(spec.cwd)` (SandboxedPath instances are already-resolved absolute paths per ADR-0011; `.absolute` is a method, not a property). OOM signal source pinned (cgroups v2 `memory.events:oom_kill` post-mortem; fallback heuristic when cgroups v2 unavailable). NetworkDenied detection pinned with false-positive prevention (host ∉ allowlist AND parent observed block event; ambiguous failures → `Completed(exit_code=N)`). Cleanup discipline pinned (try/finally + `TemporaryDirectory`).
- **Test/fixture relocation.** `src/codegenie/transforms/sandbox/_fakes_for_tests.py` (production-side test helper, smell) moved to `tests/unit/transforms/sandbox/_fakes.py`. AC-9 `curl` replaced with `node -e "fetch(...)"` (curl is in the deny list of the closed-set regression test; `node` is already in ALLOWED_BINARIES). Postinstall-canary fixture path concretized.
- **Registry-pattern decision.** Explicitly ruled out a `@register_jail` registry — orchestrator picks substrate at construction time, not request-time; constructor injection is the right shape. Note added so an implementer doesn't either over-engineer or hard-code substrate selection.

## Context

S4-01 landed the `SubprocessJail` Protocol — `async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult` — but no implementation. This story lands the **Linux Adapter**: `BwrapAdapter` wraps every child invocation in `bwrap --unshare-all --new-session --die-with-parent --ro-bind / / --tmpfs /tmp --bind <jail> <jail>`, applies a seccomp filter that blocks `mount`, `pivot_root`, `ptrace`, `bpf`, `unshare`, `keyctl`, and enforces `NetworkPolicy` at the network-namespace layer (parent owns netns; child sees `lo` + pf-routed allowlist hosts).

The architecture rationale (`phase-arch-design.md §Component design C8`, §Physical view, §Edge cases E7+E8+E12) is that Phase 3 cannot wait for Phase 5's Firecracker microVM, but the operator-laptop / CI threat model demands real isolation against a malicious target repo's `package.json`. bwrap on Linux + sandbox-exec on macOS (S4-03) are the two interim substrates; Phase 5's `FirecrackerAdapter` and `DinDAdapter` substitute via the same Port.

`bwrap` invocations route through **`run_allowlisted`** (not `run_external_cli` — the latter is the Phase 2 probe-binary chokepoint and already prepends its own bwrap wrap, which would result in double-bwrap. `run_allowlisted` is the canonical single-spawn chokepoint with `env_extra` support — exactly what the SubprocessJail adapter needs). No `subprocess.run` / `subprocess.Popen` / `os.system` / `os.popen` / `os.exec*` / `os.spawn*` / `asyncio.create_subprocess_*` direct calls — single chokepoint discipline (Phase 2 ADR-0001 / `forbidden-patterns` hook). S4-05 amends `ALLOWED_BINARIES` to admit `bwrap` and `sandbox-exec` AND amends `tests/unit/test_exec.py::test_allowed_binaries_closed_set_regression` to remove `bwrap`/`bubblewrap` from the deny-list (the closed-set regression test that currently pins them as MUST-NOT-be-allowlisted per 02-ADR-0001). This story consumes both halves of that amendment. (See the "Doc-debt surfaced" note in the header — ADR-0012 §Decision wording references `run_external_cli` but the correct seam is `run_allowlisted`; deferred to a doc-only follow-up amendment.)

**The load-bearing test discipline:** the integration test FAILS (not skips) when `bwrap` is missing on a Linux runner. Per `High-level-impl §Step 4 Risks`: "Test that exits 0 when `bwrap` missing must NOT silently pass — fail the job on Linux when bwrap absent." Silent skips defeat the entire substrate choice. The CI matrix for Phase 3 runs `apt-get install -y bubblewrap` (Ubuntu's package name for bwrap) as a setup step; if that step fails, the integration test fails — not the entire suite, but loudly.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C8` — `BwrapAdapter` bullet pins the exact bwrap command line and seccomp blocked syscalls; parent-owns-netns network-policy enforcement model.
  - `../phase-arch-design.md §Physical view` — Linux substrate diagram; pf-routed vs netns-enforced egress.
  - `../phase-arch-design.md §Edge cases E7 + E8 + E12` — `.npmrc` redirect → `NetworkDenied(host)`; postinstall canary unwritten; symlink TOCTOU at `open()`.
  - `../phase-arch-design.md §Tradeoffs (consolidated)` — "bwrap setup cost ~80–200 ms per spawn; 3 spawns/workflow → ~600 ms substrate cost — well within p50 ≤ 18 s budget."
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md` — §Decision pins the `BwrapAdapter` command line and the six blocked syscalls; §Tradeoffs row 7 names the typed `NetworkDenied(host)`; §Consequences §Adversarial tests names the three regression tests this Adapter must satisfy.
  - `../ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md` — S4-05's data change. This story's tests assume `bwrap` is in `ALLOWED_BINARIES`; if S4-05 has not landed, this story's tests fail at `run_external_cli` rejection. Coordinate landing order with S4-05 (typically S4-05 lands first, but S4-02's red→green flow surfaces the missing allowlist entry naturally).
  - `../ADRs/0007-run-npm-install-and-npm-test-in-phase3-jail.md` — the consumer ADR; S5-02 / S6-04 will pass real `JailedSubprocessSpec` instances to `BwrapAdapter`.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Sandbox for npm"` (score 14/15).
  - `../High-level-impl.md §Step 4 features delivered` — pins `src/codegenie/transforms/sandbox/bwrap.py` as the file path.
  - `../High-level-impl.md §Step 4 Risks` — bwrap install discipline, fail-not-skip on Linux.
- **Existing code:**
  - `src/codegenie/exec/__init__.py::run_external_cli` (Phase 2) — the chokepoint every adapter routes through. S4-02's `BwrapAdapter._invoke` calls `run_external_cli(["bwrap", "--unshare-all", ..., *inner_argv], ...)`.
  - `src/codegenie/exec/__init__.py::ALLOWED_BINARIES` — S4-05 adds `bwrap` and `npm`.
  - `src/codegenie/transforms/sandbox_jail.py` (S4-01) — the Port surface this Adapter implements.

## Goal

Land `src/codegenie/transforms/sandbox/bwrap.py` with `BwrapAdapter(SubprocessJail)` that:
1. Implements `async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult` by composing the bwrap command line per ADR-0006 §Decision.
2. Applies a seccomp BPF filter blocking `mount`, `pivot_root`, `ptrace`, `bpf`, `unshare`, `keyctl` (six syscalls per ADR-0006).
3. Enforces `NetworkPolicy` — `DenyAll` → child runs with no network interfaces beyond `lo`; `RegistryAllowlist(hosts)` → parent process configures a network namespace with pf/iptables rules permitting only the allowlist hosts on port 443.
4. Maps the child process's exit signals + resource accounting to the right `JailedSubprocessResult` variant: SIGKILL on OOM → `OomKilled(peak_rss_mib=...)`; timeout via `time_budget_s` → `TimedOut`; netns-blocked DNS / connect → `NetworkDenied(host=...)`; tmpfs/disk-quota → `DiskQuotaExceeded`; clean exit → `Completed`.
5. Routes through `run_allowlisted` for the outer `bwrap` invocation (no direct `subprocess.*` / `os.exec*` / `os.spawn*` / `asyncio.create_subprocess_*`). The chokepoint receives `env_extra=spec.env.to_env_mapping()` so the NpmEnv/GitEnv defenses ride along to the child.
6. An integration test (`tests/integration/transforms/test_bwrap_hello_world.py`) **fails** (does NOT skip) when run on Linux with `bwrap` missing — loud failure surface for CI's `apt-get install -y bubblewrap` step. (Reconciles `High-level-impl.md:128` vs L310 + ADR-0006 — the latter wins per CLAUDE.md Rule 7.)

`mypy --strict` clean. The Adapter's failure path emits typed `JailedSubprocessResult` variants only — no bare exceptions cross the Port boundary.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/transforms/sandbox/__init__.py` and `src/codegenie/transforms/sandbox/bwrap.py` exist. `BwrapAdapter` is exported. Structural conformance to `SubprocessJail` is verified **without `isinstance`** (S4-01 AC-2 pins SubprocessJail as NOT `@runtime_checkable`; isinstance raises `TypeError`). Three assertions, all must pass:
  - `adapter: SubprocessJail = BwrapAdapter()` type-checks under `mypy --strict` (assignment-conformance test in `tests/unit/transforms/sandbox/test_bwrap_protocol.py` includes the line; the test file itself is type-checked).
  - `inspect.iscoroutinefunction(BwrapAdapter.run)` is `True`.
  - `inspect.signature(BwrapAdapter.run).parameters.keys() == {"self", "spec"}` AND the resolved return annotation is `JailedSubprocessResult` (use `typing.get_type_hints(BwrapAdapter.run)` for the resolution).
  - A `_StubBwrapAdapter`-style call-site exercise: `jail: SubprocessJail = BwrapAdapter(); result = await jail.run(_spec())` runs through the Protocol surface and returns a `JailedSubprocessResult` variant (mocks `run_allowlisted` to keep the test offline).
- [ ] **AC-2.** `BwrapAdapter.run` invokes **`codegenie.exec.run_allowlisted`** (NOT `run_external_cli` — see Doc-debt note in header) with `argv[0] == "bwrap"` and the argv shape `prefix + seccomp_flags + spec.cmd` where:
  - `prefix == ["bwrap", "--unshare-all", "--new-session", "--die-with-parent", "--ro-bind", "/", "/", "--tmpfs", "/tmp", "--bind", str(spec.cwd), str(spec.cwd)]` (exact equality).
  - `seccomp_flags == ["--seccomp", "<fd-int>"]` (the fd of the temp file containing the BPF program; the fd value is implementation-defined but must be a non-negative integer printed as a decimal).
  - The captured argv equals `prefix + seccomp_flags + list(spec.cmd)` exactly — **no extra flags injected between the prefix and `spec.cmd`** (asserted via `set(argv) - set(prefix) - {"--seccomp", "<captured fd>"} - set(spec.cmd) == set()`). Catches mutants that smuggle `--share-net`, `--cap-add`, `--share-pid`, `--uid 0`, etc.
  - The call passes `cwd=spec.cwd` (the already-absolute `SandboxedPath` — `str(spec.cwd)`, NOT `str(spec.cwd.absolute)` which is a bound-method-repr bug), `timeout_s=spec.time_budget_s`, `env_extra=spec.env.to_env_mapping()`. The unit test (`tests/unit/transforms/sandbox/test_bwrap_unit.py::test_run_allowlisted_call_shape`) monkeypatches `codegenie.transforms.sandbox.bwrap.run_allowlisted` and captures both args and kwargs.
- [ ] **AC-3.** Seccomp filter integrity — three-tier verification:
  - **Helper-input boundary.** `BwrapAdapter.run` constructs the BPF filter via `tools.seccomp.build_filter.build(_BLOCKED_SYSCALLS)` (or equivalent in-tree helper — see AC-24). A unit test asserts the helper is called with `_BLOCKED_SYSCALLS == frozenset({Syscall.MOUNT, Syscall.PIVOT_ROOT, Syscall.PTRACE, Syscall.BPF, Syscall.UNSHARE, Syscall.KEYCTL})`.
  - **Helper-output boundary.** The bytes returned by the helper flow into the bwrap `--seccomp <fd>` flag — the test captures both the returned bytes and the argv and asserts the fd value in argv is `os.fstat()`-mappable to a file whose content equals the returned bytes. (Mutant that drops the helper's return on the floor fails here.)
  - **Kernel boundary (integration).** `tests/integration/transforms/test_bwrap_seccomp_live.py` (Linux-only, fail-not-skip when bwrap missing): runs `await BwrapAdapter().run(_spec(cmd=("/usr/bin/unshare", "-U", "/bin/true")))` and asserts the result is `Completed(exit_code=N)` where `N != 0` AND the child exited via SIGSYS (interpretable from `JailedSubprocessResult` or the captured stderr containing `"Bad system call"` / signal 31). If `/usr/bin/unshare` isn't on the runner, the test uses `python3 -c "import ctypes; ctypes.CDLL('libc.so.6').unshare(0x10000000)"` (CLONE_NEWUSER), since `python` is in ALLOWED_BINARIES post-S4-05 only if added — otherwise `pytest.fail` with a clear "neither unshare nor python available in jail; CI image regressed" message. Mutant `_build_seccomp_filter` that returns `b""` survives the helper-boundary test but fails this kernel-boundary test.
- [ ] **AC-4.** `BwrapAdapter` AND every module under `src/codegenie/transforms/sandbox/` NEVER invokes any direct subprocess primitive. Implemented as an **AST walk**, not a substring grep (substring is escapable via `from subprocess import run`, `getattr(subprocess, "run")(...)`, etc.). `tests/unit/transforms/sandbox/test_bwrap_no_direct_subprocess.py` parses each module under `src/codegenie/transforms/sandbox/` and asserts no `ast.Call` node resolves to any of:
  - `subprocess.run`, `subprocess.Popen`, `subprocess.call`, `subprocess.check_call`, `subprocess.check_output`
  - `os.system`, `os.popen`, `os.exec*` (any `execv`, `execve`, `execvp`, etc.), `os.spawn*` (any `spawnv`, etc.), `os.posix_spawn*`
  - `asyncio.create_subprocess_exec`, `asyncio.create_subprocess_shell`
  - `subprocess.*` reached via `getattr(subprocess, <string>)` (detected by scanning for `ast.Call(func=ast.Attribute(value=ast.Name(id="getattr"), ...))` with `subprocess` as the first arg)
  - Any call where `shell=True` is passed as a keyword argument (extra defense)
  Mirrors the AST-walk precedent at `tests/unit/transforms/test_outcomes_purity.py` (adapt the visitor). The single subprocess chokepoint is `codegenie.exec.run_allowlisted` (Phase 2 ADR-0001 / `forbidden-patterns` hook discipline).
- [ ] **AC-5.** Every `JailedSubprocessResult` variant is reachable via the **shared `_classify_outcome` helper** (AC-23). Unit tests mock `run_allowlisted` to return real-shape `ProcessResult` instances (or raise the typed exceptions Phase 2 chokepoint raises) and assert the variant translation. **SIGKILL discriminator pinned** — both timeout-and-OOM produce SIGKILL on Linux, so the classifier MUST tie-break in this exact order:
  1. If `elapsed_s >= spec.time_budget_s` (within 100 ms slack) AND the child was SIGKILLed → `TimedOut(budget_s=spec.time_budget_s, elapsed_s=...)`.
  2. Else if SIGKILLed AND `peak_rss_mib >= spec.memory_mib` (from cgroups v2 `memory.peak`) → `OomKilled(peak_rss_mib=...)`.
  3. Else if SIGKILLed AND cgroups v2 `memory.events:oom_kill > 0` → `OomKilled(peak_rss_mib=peak_or_estimate)`.
  4. Else SIGKILL with no deadline-hit and no OOM evidence → `Completed(exit_code=-9, ...)` (a third party killed it; preserve exit code rather than guess).
  Concrete parametric mocks (no sentinel-string indirection):
  - `run_allowlisted` returns `ProcessResult(returncode=0, stdout=b"", stderr=b"")` with elapsed = 0.05 s → `Completed(exit_code=0, wall_time_s≈0.05, ...)`.
  - `run_allowlisted` raises `ProbeTimeoutError("bwrap exceeded timeout_s=5.0 (elapsed_ms=5050)")` → `TimedOut(budget_s=5.0, elapsed_s≈5.05)`. Tests parse the `elapsed_ms` from the message OR consult a side-channel timer.
  - `run_allowlisted` returns `ProcessResult(returncode=-9, ...)` AND a stub cgroups reader returns `oom_kill=1, memory.peak=200*MiB` for a `spec.memory_mib=128` → `OomKilled(peak_rss_mib=200)`.
  - `run_allowlisted` returns `ProcessResult(returncode=N, stderr=b"connect: Network is unreachable\n")` AND `spec.network.kind == "registry_allowlist"` AND the inner argv contains a host literal NOT in the allowlist → `NetworkDenied(host="<that literal>")`. **The classifier requires BOTH a stderr signature AND host-not-in-allowlist** to return NetworkDenied (false-positive prevention per AC-H2 finding).
  - `run_allowlisted` returns `ProcessResult(returncode=N, stderr=b"... No space left on device\n")` AND the test stub asserts the bytes-written counter exceeds the tmpfs cap → `DiskQuotaExceeded(quota_bytes=..., bytes_written=...)`. If cheap detection isn't available on a particular runner, the classifier returns `Completed(exit_code=N)` with the stderr preserved — AC-5 documents that `DiskQuotaExceeded` is **best-effort** and the integration backfill is S8-04's responsibility.
- [ ] **AC-6.** `NetworkPolicy = DenyAll` ⇒ child invocation has unshared netns and no host-routing setup. Two assertions:
  - `--share-net`, `--bind-net-*`, `--unshare-net=false` do NOT appear anywhere in the argv (full-shape check from AC-2 catches the prefix-and-tail case; this AC adds an explicit token-set assertion that uses `assert "--share-net" not in argv and not any(a.startswith("--bind-net") for a in argv) and "--unshare-net=false" not in argv`).
  - `_setup_netns_with_allowlist` (or equivalent host-route helper) is NOT called. Implementation pattern: `match spec.network: case DenyAll(): pass; case RegistryAllowlist(hosts=h): _setup_netns_with_allowlist(h)` — pinned by AC-25.
- [ ] **AC-7.** `NetworkPolicy = RegistryAllowlist(hosts)` ⇒ `_setup_netns_with_allowlist` is invoked with the exact `hosts: frozenset[RegistryUrl]`. Strengthens the original story's mock-call check: `captured_hosts == hosts` (equality, not subset). The pf/iptables call itself is mocked at this layer; AC-9's live test exercises the actual netns/pf path on Linux.
- [ ] **AC-8.** **Linux-only integration test, FAIL not SKIP when bwrap missing.** `tests/integration/transforms/test_bwrap_hello_world.py`:
  - On non-Linux: `pytest.skip("Linux substrate; macOS uses sandbox-exec (S4-03)")`.
  - On Linux + `shutil.which("bwrap") is None`: `pytest.fail("bwrap missing on Linux runner — CI's apt-get install -y bubblewrap step failed or was skipped. Per ADR-0006 §Consequences + High-level-impl §Step 4 Risks, this MUST fail (not skip) — silent skips defeat the substrate choice.")`.
  - On Linux + bwrap present: `await BwrapAdapter().run(spec)` where `spec.cmd = ("/bin/echo", "hello")` → asserts `isinstance(result, Completed)` and `result.exit_code == 0`.
- [ ] **AC-9.** **Linux-only network-policy live test.** `tests/integration/transforms/test_bwrap_network_policy.py`, same Linux + fail-not-skip discipline as AC-8. Uses `node` (already in ALLOWED_BINARIES post-S4-05) NOT `curl` (which is pinned in the deny list of `test_allowed_binaries_closed_set_regression` — calling `curl` as `cmd[0]` would fail `run_allowlisted`'s chokepoint check):
  - Allowlist-permit case: `cmd=("node", "-e", "fetch('https://registry.npmjs.org/').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(2))")` + `RegistryAllowlist(hosts=frozenset({RegistryUrl("https://registry.npmjs.org")}))` → `Completed(exit_code=0)`.
  - Allowlist-deny case: same fetch against `https://github.com/` + same allowlist → `NetworkDenied(host="github.com")`.
  - **Loud failure when `node` missing**: fixture checks `shutil.which("node")` and `pytest.fail`s if absent on a Linux runner (mirrors AC-8). NO silent skip.
- [ ] **AC-10.** `BwrapAdapter` passes `spec.env.to_env_mapping()` to `run_allowlisted`'s `env_extra` parameter. Unit test mocks `run_allowlisted`, passes `spec(env=NpmEnv())`, and asserts `captured_kwargs["env_extra"]["npm_config_ignore_scripts"] == "true"`. Ties S4-01's structural env defense to S4-02's call-site discipline. Also asserts `env_extra` is a `dict[str, str]` (not `Mapping`, not `None`, not a custom subclass) so `run_allowlisted`'s `_filter_env` doesn't take an unintended path.
- [ ] **AC-11.** `spec.cmd` is preserved verbatim as the tail of the bwrap argv. Unit test passes `cmd = ("npm", "install", "--ignore-scripts", "--package-lock-only", "--no-audit")` and asserts `tuple(captured_argv[-len(cmd):]) == cmd`. Single strict-tail check (the original story's first loop was dead weight — out-of-order tokens trivially passed; removed in validation).
- [ ] **AC-12.** Postinstall-canary substrate test, two variants (the second is the **negative control** that proves the substrate — not just the `--ignore-scripts` flag — is what suppresses the canary):
  - **Fixture:** `tests/fixtures/phase03/postinstall_canary/package.json` with `{"scripts": {"postinstall": "node -e \"require('fs').writeFileSync(process.env.CANARY_PATH, 'x')\""}}`. The `CANARY_PATH` env var is set to `<tmp_path>/.codegenie-canary` (outside the bwrap `--bind` target).
  - **Variant A (substrate + flag both engaged):** `tests/integration/transforms/test_bwrap_postinstall_canary.py` (Linux-only, fail-not-skip when bwrap missing). Runs `BwrapAdapter().run(JailedSubprocessSpec(cmd=("npm", "install", "--ignore-scripts", "--package-lock-only"), env=NpmEnv(), cwd=<fixture path bind-mounted>, ...))` → asserts `isinstance(result, Completed)` AND `(tmp_path / ".codegenie-canary").exists() is False` (assertion order: canary-absent first, then variant — so a Completed-with-side-effect mutant fails on the canary check before the variant check).
  - **Variant B (substrate engaged, flag disabled — the negative control):** Same fixture, same Adapter, but `cmd=("npm", "install", "--package-lock-only")` (NO `--ignore-scripts` in the CLI). Asserts `isinstance(result, Completed)` AND `(tmp_path / ".codegenie-canary").exists() is False` — proves the bwrap binds + `npm_config_ignore_scripts=true` env (set by `NpmEnv`) suppress the canary even when the CLI flag is absent. Without this variant, AC-12 would pass against a misconfigured bwrap that shares writes — exactly the failure mode the substrate is meant to prevent.
  - Full adversarial regression (`tests/adversarial/test_postinstall_canary.py @pytest.mark.phase03_adv`) is S8-04's responsibility; this story lands the integration-tier precursor.
- [ ] **AC-13.** `mypy --strict src/codegenie/transforms/sandbox/ tests/unit/transforms/sandbox/ tests/integration/transforms/` clean. `ruff check` + `ruff format --check` clean on touched files.
- [ ] **AC-14.** `make lint-imports` Phase 3 contract (S1-05): no LLM SDK imported from `src/codegenie/transforms/sandbox/`. `tests/fence/test_no_llm_in_transforms.py` covers the new submodule (extend if prefix matching doesn't already cover it).
- [ ] **AC-15.** CI integration is detected by AC-8's loud failure. To give AC-15 a verifiable artifact today (independent of S9-01 landing the CI YAML edit), `tests/integration/test_ci_setup_fence.py` greps `.github/workflows/*.yml` for `bubblewrap|bwrap` AND fails with a structured TODO citing S9-01 if absent on Linux jobs. This test passes vacuously today (no CI YAML edit yet) by emitting a `pytest.xfail("S9-01 pending — CI YAML edit deferred")`, transitioning to hard-fail-if-missing once S9-01 lands. Gives AC-15 a present-tense observable artifact.
- [ ] **AC-16.** **Typed-error fence — no bare exception escapes the Port boundary.** Parametric unit test injects each failure into the chokepoint and asserts `await BwrapAdapter().run(spec)` returns a `JailedSubprocessResult` variant (does NOT raise). Cases:
  - `run_allowlisted` raises `ProbeTimeoutError` → `TimedOut`.
  - `run_allowlisted` raises `DisallowedSubprocessError` (would happen pre-S4-05) → `JailSetupFailed(reason="binary-not-allowlisted")` OR re-raised with explicit ADR cross-reference (pin which; the validator's call is to add a `JailSetupFailed` variant to `JailedSubprocessResult` if not already present, OR ship a clear "this is a precondition violation, not a runtime failure" re-raise with `from None`).
  - `run_allowlisted` raises `ToolMissingError` → `JailSetupFailed(reason="bwrap-not-on-path")`. (Distinct from AC-8's pytest.fail — AC-8 is the test-tier fail; AC-16 is the runtime-tier classifier behavior for the unlikely "bwrap on PATH at adapter-construct but vanished by spawn" race.)
  - `run_allowlisted` raises `FileNotFoundError`/`NotADirectoryError` from `spec.cwd` validation → `JailSetupFailed(reason="cwd-missing")` OR re-raise as a programming-error (pin which; the validator recommends a typed variant).
  - `_setup_netns_with_allowlist` raises `PermissionError` (no `CAP_NET_ADMIN`) → see AC-21.
  - A generic `OSError` from netns/seccomp setup → `JailSetupFailed(reason="kernel-setup-failed")`.
  No `except Exception:` blocks anywhere in `bwrap.py` (AST check covered by AC-4-adjacent fence; if not, add to AC-4's visitor: forbid bare `ExceptHandler(type=None)` and `ExceptHandler(type=ast.Name(id="Exception"))`).
- [ ] **AC-17.** **Determinism property.** Same `JailedSubprocessSpec` → same argv prefix + same seccomp bytes across two consecutive `BwrapAdapter().run(spec)` calls (back-to-back, mocked chokepoint). Test captures argv + seccomp bytes from call 1 and call 2; asserts equality (modulo the temp-file fd integer, which is process-state-dependent — extract by position). Catches hidden non-determinism (PID-derived tempdir suffixes, mtime, random padding in BPF).
- [ ] **AC-18.** **Property-based tests** (Hypothesis). Three properties:
  - **DenyAll never shares net.** `@given(_spec_strategy(network=just(DenyAll())))` → resulting argv contains no `--share-net`, no `--bind-net-*`, no `--unshare-net=false`.
  - **Allowlist host coverage.** `@given(_spec_strategy(network=registry_allowlists()))` → for every host in `spec.network.hosts`, the captured `_setup_netns_with_allowlist` call includes that host (set-equality, not subset).
  - **Verbatim cmd preservation.** `@given(_spec_strategy(cmd=tuples(text(min_size=1).filter(lambda s: '\x00' not in s))))` → `tuple(captured_argv[-len(spec.cmd):]) == spec.cmd`. Hypothesis-shrunken counterexamples on `cmd` containing whitespace, dashes, leading-dash tokens (would-be flags if not preserved verbatim).
- [ ] **AC-19.** **Cleanup-on-exception.** When `run_allowlisted` raises mid-call (any exception), the Adapter cleans up:
  - Seccomp temp file unlinked (use `tempfile.NamedTemporaryFile(delete=True)` + a closed-but-not-deleted-until-fstat assertion, OR `TemporaryDirectory` for the seccomp+netns artifacts).
  - `_teardown_netns(handle)` invoked exactly once when a netns was created (regardless of exception).
  Unit test: monkeypatch `run_allowlisted` to raise `RuntimeError("boom")` mid-call; assert the seccomp temp file's path does not exist post-run AND `_teardown_netns` was called exactly once via a `mock.MagicMock` spy. The Adapter MUST use `try/finally` or a context manager for both — no leaky failure paths.
- [ ] **AC-20.** **Concurrent-run serialization.** Two `BwrapAdapter().run()` calls from different asyncio tasks with different `RegistryAllowlist(hosts={...})` MUST NOT interleave pf/iptables rules. Pin ONE of two strategies:
  - **Strategy A (per-call isolation):** each call creates a uniquely-named netns (e.g., `f"codegenie-jail-{uuid.uuid4().hex[:12]}"`) so concurrent calls never share iptables tables. Test: launch two concurrent `run()` calls; each child observes only its own allowlist (the spec's RegistryAllowlist hosts).
  - **Strategy B (mutex):** an instance-level (NOT module-level) `asyncio.Lock` serializes netns/pf setup. Test: launch two concurrent calls; assert the second waits for the first (observable via timing OR a counter incremented inside the critical section).
  AC-20 pins **Strategy A** (per-call isolation) — Strategy B serializes throughput and inherits hidden state via the lock. If the implementer picks B, they must amend the story + ADR-0006 §Tradeoffs row 6 with the throughput cost.
- [ ] **AC-21.** **`CAP_NET_ADMIN` absent → typed failure, not silent skip.** When `_setup_netns_with_allowlist` cannot create the netns (e.g., `PermissionError`, `OSError(EPERM)`), the Adapter returns `JailSetupFailed(reason="cap-net-admin-missing", detail=...)` — a new variant added to `JailedSubprocessResult` if absent (per S4-01 AC-4 extensibility). Live integration tests (AC-9) guard the precondition: `if os.geteuid() != 0 and not _has_cap_net_admin(): pytest.fail("CAP_NET_ADMIN missing on Linux runner — `setcap cap_net_admin+ep` or run under sudo")`. NO silent skip on a permissions failure on Linux.
- [ ] **AC-22.** **Stateless across calls — no module-level mutable globals introduced.** AST check: `tests/unit/transforms/sandbox/test_bwrap_stateless.py` parses `bwrap.py` and asserts no `ast.Assign` / `ast.AugAssign` to a module-level `Name` (other than `Final`-typed declarations, which are immutable by typing convention; permit those via an allowlist of `_BLOCKED_SYSCALLS`, `_SECCOMP_FILTER_BYTES_CACHE` if it ends up needed, etc., but pin them as `Final`). Runtime check: invoke `BwrapAdapter().run(spec)` twice; assert the second call performs the same PATH lookups / seccomp-build / netns-setup as the first (no warm-cache fast path through module state). Mutant that copies `run_external_cli`'s `_BWRAP_WARNED` global fails the AST check.
- [ ] **AC-23.** **`_classify_outcome` extracted to a shared, pure module.** `src/codegenie/transforms/sandbox/_classify.py` defines:
  ```python
  def classify_outcome(
      process_result: ProcessResult | None,
      raised_exception: Exception | None,
      spec: JailedSubprocessSpec,
      signals: ClassifierSignals,  # cgroups OOM kill, peak_rss_mib, elapsed_s, etc.
  ) -> JailedSubprocessResult: ...
  ```
  Pure (no I/O — caller passes ProcessResult and signals). Unit-tested independently in `tests/unit/transforms/sandbox/test_classify.py` with parametric inputs covering EACH `JailedSubprocessResult` variant + each SIGKILL discriminator branch (AC-5). `BwrapAdapter.run` delegates to it; `SandboxExecAdapter` (S4-03) MUST consume the same classifier (note for the implementer; story tracks this).
- [ ] **AC-24.** **`Syscall` `StrEnum` + module-level `Final` syscall set — no primitive obsession.** Define `class Syscall(StrEnum): MOUNT = "mount"; PIVOT_ROOT = "pivot_root"; PTRACE = "ptrace"; BPF = "bpf"; UNSHARE = "unshare"; KEYCTL = "keyctl"` (six members). `_BLOCKED_SYSCALLS: Final[frozenset[Syscall]] = frozenset({Syscall.MOUNT, Syscall.PIVOT_ROOT, Syscall.PTRACE, Syscall.BPF, Syscall.UNSHARE, Syscall.KEYCTL})`. `_build_seccomp_filter(blocked: frozenset[Syscall]) -> bytes` — input typed. `BwrapAdapter.run` passes `_BLOCKED_SYSCALLS` (the module-level constant), never inlines literal syscall names at the call site. Adding/removing a syscall is a one-row data edit + a one-row `_BLOCKED_SYSCALLS` edit. Mutant that types `_build_seccomp_filter(blocked: set[str])` fails `mypy --strict` at the call site.
- [ ] **AC-25.** **`match spec.network` on `NetworkPolicy` sum — exhaustive, not `isinstance` ladder.** Implementation outline pins:
  ```python
  match spec.network:
      case DenyAll():
          # no netns/pf setup needed; bwrap --unshare-all unshares netns
          pass
      case RegistryAllowlist(hosts=h):
          netns_handle = _setup_netns_with_allowlist(h)
      case _:  # mypy reports `case _` as unreachable — exhaustiveness proof
          assert_never(spec.network)
  ```
  Test: `tests/unit/transforms/sandbox/test_bwrap_network_dispatch_mypy.py` is a subprocess-mypy negative test (mirrors S4-01 AC-9a pattern): commenting out the `RegistryAllowlist` arm makes `mypy --strict` flag `assert_never(spec.network)` as reachable. Phase 5 adding a third `NetworkPolicy` variant (e.g., `TunneledEgress`) triggers the same fence.
- [ ] **AC-26.** **Perf smoke (Linux-only, `@pytest.mark.bench`-marked, NOT in `make check`).** `BwrapAdapter().run(_spec(cmd=("/bin/true",)))` on a warm jail completes in ≤ 1.0 s wall time (3-run median). ADR-0006 §Tradeoffs row 6 commits to 80–200 ms substrate cost — 1.0 s is a 5× headroom that catches catastrophic slowdowns (e.g., per-call libseccomp init, per-call netns table recreate) without flaking on cold CI runners. NOT a regression gate — S9-03's `bench_workflow_e2e_warm` owns the real budget.

## Implementation outline

1. Create `src/codegenie/transforms/sandbox/__init__.py` (empty or re-exporting `BwrapAdapter` and the to-come `SandboxExecAdapter`).
2. Create `src/codegenie/transforms/sandbox/_classify.py` (AC-23). Pure module — `def classify_outcome(process_result, raised_exception, spec, signals) -> JailedSubprocessResult`. No I/O imports.
3. Create `src/codegenie/transforms/sandbox/bwrap.py`. Imports: `from __future__ import annotations`, `asyncio`, `os`, `pathlib.Path`, `shutil`, `sys`, `tempfile`, `time`, `uuid`, `typing.{Final, assert_never}`, `codegenie.exec.run_allowlisted` (NOT `run_external_cli` — see header doc-debt note), the `Syscall` `StrEnum` + `_BLOCKED_SYSCALLS` constant, `codegenie.transforms.sandbox._classify.classify_outcome`, `codegenie.transforms.sandbox_jail.{JailedSubprocessSpec, JailedSubprocessResult, DenyAll, RegistryAllowlist, JailSetupFailed}` (plus `SubprocessJail` if structural typing needs it — Protocol is satisfied structurally, no explicit base class).
4. Define `class Syscall(StrEnum)` with six members (AC-24); define `_BLOCKED_SYSCALLS: Final[frozenset[Syscall]]` at module scope. No literal syscall strings elsewhere in the module.
5. Define `class BwrapAdapter:` with `async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult`.
6. Inside `run` — use a single `try/finally` so cleanup (AC-19) is unconditional:
   - Compose the bwrap argv prefix: `["bwrap", "--unshare-all", "--new-session", "--die-with-parent", "--ro-bind", "/", "/", "--tmpfs", "/tmp", "--bind", str(spec.cwd), str(spec.cwd)]`. **`str(spec.cwd)`, NOT `str(spec.cwd.absolute)`** — `SandboxedPath` instances are already-resolved absolute paths per ADR-0011; `pathlib.Path.absolute` is a method, not a property, and `str(bound_method)` yields `"<bound method...>"`.
   - Build the seccomp filter via the hand-written BPF helper at `tools/seccomp/build_filter.py` (or `src/codegenie/transforms/sandbox/_seccomp.py` — pin which during green; story validator recommends the in-tree `src/` path to avoid `tools/` import friction with the `make fence` step). Write to a temp file via `tempfile.NamedTemporaryFile(delete=False)`; `--seccomp <fd>` integer of the open file descriptor flows into argv. Register the temp-file path for cleanup in the `try/finally`.
   - Dispatch on `NetworkPolicy` using `match` (AC-25):
     ```python
     match spec.network:
         case DenyAll():
             netns_handle = None
         case RegistryAllowlist(hosts=h):
             netns_handle = _setup_netns_with_allowlist(h, uniquely_named=True)  # AC-20 Strategy A
         case _:
             assert_never(spec.network)
     ```
   - Build the inner-env mapping: `env_extra: dict[str, str] = dict(spec.env.to_env_mapping())` (concrete `dict[str, str]` so `run_allowlisted`'s `_filter_env` takes the documented path).
   - Append `spec.cmd` to the bwrap argv.
   - Call `process_result_or_exc = await _safely_call_chokepoint(argv, cwd=spec.cwd, timeout_s=spec.time_budget_s, env_extra=env_extra)` — a thin internal wrapper that calls `run_allowlisted` and captures BOTH return-value and exception (so the classifier sees both branches uniformly).
   - Collect `signals: ClassifierSignals` post-mortem (cgroups v2 `memory.events:oom_kill`, `memory.peak`, `elapsed_s` from a monotonic timer, stderr-bytes for NetworkDenied/DiskQuotaExceeded signature matching).
   - Return `classify_outcome(process_result, raised_exception, spec, signals)`.
   - **`finally`:** unlink seccomp temp file; if `netns_handle` not None, `_teardown_netns(netns_handle)`. Both unconditional; both idempotent (re-runnable on partial setup failure).
7. **`_classify_outcome` SIGKILL tie-break (AC-5):** inside `_classify.py`, the dispatch order is (a) timeout deadline hit (`elapsed_s >= spec.time_budget_s - SLACK`) → `TimedOut`; (b) cgroups v2 `oom_kill > 0` OR (`peak_rss_mib >= spec.memory_mib` AND SIGKILL) → `OomKilled`; (c) `returncode != 0` AND stderr matches a `_NETWORK_DENIED_PATTERNS: Final[tuple[re.Pattern, ...]]` AND the host literal in argv is NOT in `spec.network.hosts` (when `network` is `RegistryAllowlist`) → `NetworkDenied(host)`; (d) `returncode != 0` AND stderr matches `_DISK_QUOTA_PATTERNS` → `DiskQuotaExceeded` (best-effort); (e) else → `Completed(exit_code=returncode, ...)`.
8. **NetworkDenied false-positive prevention (Coverage H2).** The classifier requires BOTH (a) a stderr signature match AND (b) host-not-in-allowlist. Ambiguous failures (no signature match, or `network.kind == "deny_all"`) → `Completed(exit_code=N, stderr=...)`. Misclassifying a DNS failure as `NetworkPolicyViolation` would trigger exit-4 in the orchestrator — operator-blocking. False negatives are preferable to false positives here.
9. **Cleanup discipline (AC-19).** Use a single `try/finally` wrapping the full body of `run`. The seccomp temp file is opened with `delete=False` so the fd can outlive the open-context; the file path is held in a local and unlinked in `finally`. The netns handle is a small dataclass (`@dataclass(frozen=True) class NetnsHandle: name: str`) so `_teardown_netns(handle)` is a typed call. No `try/except Exception:` swallows.
10. Write the unit tests (AC-1..AC-7, AC-10, AC-11, AC-16, AC-17, AC-18, AC-19, AC-22) against a mocked `run_allowlisted`.
11. Write the live integration tests (AC-3 kernel-boundary, AC-8, AC-9, AC-12, AC-26) gated on `sys.platform == "linux"` with explicit `pytest.fail` (not `pytest.skip`) when `bwrap` is missing on Linux, when `node` is missing for AC-9, or when `/usr/bin/unshare`/`python` are missing for AC-3 kernel-boundary.
12. Run `mypy --strict`, `ruff`, and `pytest tests/unit/transforms/sandbox/ tests/integration/transforms/`. On a Linux dev box or CI runner with `CAP_NET_ADMIN` + `bubblewrap` + `node`, the integration tests should be green; on macOS, they skip (AC-8 / AC-9 / AC-12 all check `sys.platform`).
13. Run `make lint-imports` (AC-14) and the AST stateless check (AC-22).

## TDD plan — red / green / refactor

The AC list (AC-1..AC-26) is **authoritative**; the code samples below are illustrative skeletons of the most-load-bearing tests, written against the corrected chokepoint (`run_allowlisted`, NOT `run_external_cli`) and the corrected SandboxedPath idiom (`str(spec.cwd)`, NOT `str(spec.cwd.absolute)`). The full test list maps 1:1 to the Files-to-touch table.

### Red — write the failing tests first

`tests/unit/transforms/sandbox/test_bwrap_unit.py` (cross-platform; mocks `run_allowlisted`):

```python
from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path
from typing import get_type_hints
from unittest import mock

import pytest

from codegenie.exec import ProcessResult, ProbeTimeoutError, DisallowedSubprocessError
from codegenie.transforms.sandbox.bwrap import BwrapAdapter  # RED: module doesn't exist yet
from codegenie.transforms.sandbox_jail import (
    Completed, DenyAll, JailedSubprocessResult, JailedSubprocessSpec,
    JailSetupFailed, NetworkDenied, NpmEnv, OomKilled, RegistryAllowlist,
    SubprocessJail, TimedOut,
)
from codegenie.types.identifiers import RegistryUrl
from tests.unit.transforms.sandbox._fakes import FakeSandboxedPath, make_process_result


def _spec(**over: object) -> JailedSubprocessSpec:
    defaults: dict[str, object] = dict(
        cmd=("/bin/echo", "hi"),
        cwd=FakeSandboxedPath("/tmp/jail"),  # __str__ returns "/tmp/jail"
        env=NpmEnv(),
        network=DenyAll(),
        time_budget_s=5.0,
        memory_mib=128,
        pids_max=64,
    )
    defaults.update(over)
    return JailedSubprocessSpec(**defaults)  # type: ignore[arg-type]


# AC-1: structural Protocol conformance (NO isinstance — SubprocessJail is NOT @runtime_checkable)
def test_bwrap_adapter_conforms_to_protocol_structurally() -> None:
    adapter: SubprocessJail = BwrapAdapter()  # mypy-time check; raises at runtime if class missing
    assert inspect.iscoroutinefunction(BwrapAdapter.run)
    sig = inspect.signature(BwrapAdapter.run)
    assert set(sig.parameters.keys()) == {"self", "spec"}
    hints = get_type_hints(BwrapAdapter.run)
    assert hints["spec"] is JailedSubprocessSpec
    assert hints["return"] is JailedSubprocessResult


# AC-2: argv shape matches ADR-0006 §Decision exactly, NO extra injected flags
async def test_argv_shape_matches_adr_0006(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_run_allowlisted(argv, *, cwd, timeout_s, env_extra=None):
        captured["argv"] = list(argv)
        captured["cwd"] = cwd
        captured["timeout_s"] = timeout_s
        captured["env_extra"] = dict(env_extra or {})
        return make_process_result(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(
        "codegenie.transforms.sandbox.bwrap.run_allowlisted", fake_run_allowlisted
    )
    spec = _spec()
    await BwrapAdapter().run(spec)
    argv = captured["argv"]
    prefix = [
        "bwrap", "--unshare-all", "--new-session", "--die-with-parent",
        "--ro-bind", "/", "/", "--tmpfs", "/tmp",
        "--bind", str(spec.cwd), str(spec.cwd),
    ]
    assert argv[: len(prefix)] == prefix
    # Seccomp flag + fd integer; fd value is implementation-defined non-negative int
    assert argv[len(prefix)] == "--seccomp"
    assert argv[len(prefix) + 1].isdigit()
    # Tail is spec.cmd verbatim (AC-11)
    assert tuple(argv[-len(spec.cmd):]) == spec.cmd
    # No injected flags between prefix+seccomp and cmd-tail (AC-2 full-shape)
    inner_start = len(prefix) + 2
    inner_end = len(argv) - len(spec.cmd)
    assert inner_start == inner_end, f"unexpected flags injected: {argv[inner_start:inner_end]}"


# AC-3 (helper-input + helper-output): seccomp filter integrity at the helper boundary
async def test_seccomp_helper_input_and_output(monkeypatch, tmp_path) -> None:
    from codegenie.transforms.sandbox.bwrap import Syscall, _BLOCKED_SYSCALLS
    captured_blocked: dict[str, frozenset] = {}
    real_bytes = b"\x06\x00\x00\x00\x00\x00\xff\x7f"  # whatever the real helper returns

    def fake_build_filter(blocked: frozenset) -> bytes:
        captured_blocked["set"] = blocked
        return real_bytes

    monkeypatch.setattr(
        "codegenie.transforms.sandbox._seccomp.build_filter", fake_build_filter
    )
    captured_argv: dict[str, list[str]] = {}

    async def fake_run_allowlisted(argv, **kwargs):
        captured_argv["argv"] = list(argv)
        return make_process_result(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(
        "codegenie.transforms.sandbox.bwrap.run_allowlisted", fake_run_allowlisted
    )
    await BwrapAdapter().run(_spec())
    assert captured_blocked["set"] == _BLOCKED_SYSCALLS == frozenset({
        Syscall.MOUNT, Syscall.PIVOT_ROOT, Syscall.PTRACE,
        Syscall.BPF, Syscall.UNSHARE, Syscall.KEYCTL,
    })
    # Output flows into argv: the fd in argv points to a file whose contents == real_bytes
    fd_str = captured_argv["argv"][captured_argv["argv"].index("--seccomp") + 1]
    import os
    on_disk = os.read(int(fd_str), 4096)  # or fdopen + read; details TBD by impl
    assert on_disk == real_bytes


# AC-4: AST walk against forbidden subprocess primitives
def test_module_has_no_direct_subprocess_or_exec() -> None:
    import ast
    src_root = Path("src/codegenie/transforms/sandbox")
    forbidden_attrs = {
        ("subprocess", "run"), ("subprocess", "Popen"), ("subprocess", "call"),
        ("subprocess", "check_call"), ("subprocess", "check_output"),
        ("os", "system"), ("os", "popen"),
        ("asyncio", "create_subprocess_exec"), ("asyncio", "create_subprocess_shell"),
    }
    forbidden_attr_prefixes = {("os", "exec"), ("os", "spawn"), ("os", "posix_spawn")}
    for py in src_root.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    pair = (node.func.value.id, node.func.attr)
                    assert pair not in forbidden_attrs, f"{py}: forbidden call {pair}"
                    for mod, prefix in forbidden_attr_prefixes:
                        assert not (pair[0] == mod and pair[1].startswith(prefix)), \
                            f"{py}: forbidden call {pair}"
                # Catch getattr(subprocess, ...)
                if (isinstance(node.func, ast.Name) and node.func.id == "getattr"
                    and node.args and isinstance(node.args[0], ast.Name)
                    and node.args[0].id == "subprocess"):
                    raise AssertionError(f"{py}: getattr(subprocess, ...) indirection forbidden")
            # shell=True keyword on any call
            for kw in getattr(node, "keywords", []) or []:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    raise AssertionError(f"{py}: shell=True forbidden")


# AC-5: variant translation with real-shape ProcessResult + SIGKILL discriminator
@pytest.mark.parametrize(
    "scenario, result_or_exc, signals_kwargs, expected_variant, expected_check",
    [
        ("clean_zero",
         make_process_result(returncode=0),
         dict(elapsed_s=0.05, peak_rss_mib=10),
         Completed,
         lambda r: r.exit_code == 0),
        ("sigkill_at_deadline_low_rss",  # timeout wins tie-break
         make_process_result(returncode=-9),
         dict(elapsed_s=5.05, peak_rss_mib=10, oom_kill_count=0),  # spec.time_budget_s=5.0
         TimedOut,
         lambda r: r.budget_s == 5.0),
        ("sigkill_under_deadline_high_rss",  # OOM wins
         make_process_result(returncode=-9),
         dict(elapsed_s=0.5, peak_rss_mib=200, oom_kill_count=1),  # spec.memory_mib=128
         OomKilled,
         lambda r: r.peak_rss_mib == 200),
        ("network_denied_with_signature_and_disallowed_host",
         make_process_result(returncode=6, stderr=b"connect: Network is unreachable\n"),
         dict(elapsed_s=0.1, peak_rss_mib=10),
         NetworkDenied,
         lambda r: "github.com" in r.host),
        ("ambiguous_failure_no_signature",  # false-positive prevention
         make_process_result(returncode=1, stderr=b"some random failure\n"),
         dict(elapsed_s=0.1, peak_rss_mib=10),
         Completed,
         lambda r: r.exit_code == 1),
    ],
)
async def test_variant_translation_with_sigkill_discriminator(
    scenario, result_or_exc, signals_kwargs, expected_variant, expected_check, monkeypatch
):
    async def fake_run_allowlisted(argv, **kwargs):
        return result_or_exc
    monkeypatch.setattr(
        "codegenie.transforms.sandbox.bwrap.run_allowlisted", fake_run_allowlisted
    )
    monkeypatch.setattr(
        "codegenie.transforms.sandbox.bwrap._collect_signals",
        lambda *a, **k: signals_kwargs,
    )
    cmd = ("node", "-e", "fetch('https://github.com/')") if "network" in scenario else ("/bin/echo", "x")
    network = RegistryAllowlist(hosts=frozenset({RegistryUrl("https://registry.npmjs.org")})) \
        if "network" in scenario else DenyAll()
    spec = _spec(cmd=cmd, network=network)
    result = await BwrapAdapter().run(spec)
    assert isinstance(result, expected_variant), f"{scenario}: got {result!r}"
    assert expected_check(result), f"{scenario}: predicate failed on {result!r}"


# AC-10: NpmEnv.to_env_mapping passed to run_allowlisted's env_extra
async def test_npm_env_mapping_reaches_run_allowlisted(monkeypatch) -> None:
    captured = {}
    async def fake(argv, *, cwd, timeout_s, env_extra=None):
        captured["env_extra"] = dict(env_extra or {})
        return make_process_result(returncode=0)
    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake)
    await BwrapAdapter().run(_spec(env=NpmEnv()))
    assert captured["env_extra"]["npm_config_ignore_scripts"] == "true"
    assert isinstance(captured["env_extra"], dict)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in captured["env_extra"].items())


# AC-16: typed-error fence — no bare exception escapes the Port boundary
@pytest.mark.parametrize(
    "raised_exc, expected_kind",
    [
        (ProbeTimeoutError("bwrap exceeded timeout_s=5.0 (elapsed_ms=5050)"), TimedOut),
        (DisallowedSubprocessError("bwrap not in ALLOWED_BINARIES"), JailSetupFailed),
    ],
)
async def test_no_bare_exception_escapes_port(raised_exc, expected_kind, monkeypatch):
    async def fake(argv, **k):
        raise raised_exc
    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_allowlisted", fake)
    result = await BwrapAdapter().run(_spec())
    assert isinstance(result, expected_kind), f"got {result!r}; expected {expected_kind.__name__}"
```

Additional test files per the Files-to-touch table (skeletons omitted for brevity — the ACs are authoritative):

- `test_bwrap_protocol.py` (AC-1 structural + `_StubBwrapAdapter` call-site)
- `test_bwrap_stateless.py` (AC-22 AST + runtime double-call)
- `test_bwrap_network_dispatch_mypy.py` (AC-25 subprocess-mypy negative — mirror S4-01 AC-9a pattern)
- `test_classify.py` (AC-23 + AC-5 parametric)
- `test_seccomp_builder.py` (AC-24 + mutation-resistance: different inputs → different bytes)
- `test_bwrap_properties.py` (AC-18 Hypothesis)
- `test_bwrap_no_direct_subprocess.py` (AC-4 AST walk shown above; moved into its own file)
- `test_bwrap_unit.py::test_cleanup_on_chokepoint_exception` (AC-19)
- `test_bwrap_unit.py::test_argv_determinism_across_two_calls` (AC-17)
- `test_bwrap_unit.py::test_concurrent_runs_isolated_netns` (AC-20 Strategy A)

`tests/integration/transforms/test_bwrap_hello_world.py` (AC-8 — fail-not-skip on Linux):

```python
from __future__ import annotations
import shutil
import sys

import pytest

from codegenie.transforms.sandbox.bwrap import BwrapAdapter
from codegenie.transforms.sandbox_jail import (
    Completed, DenyAll, JailedSubprocessSpec, NpmEnv,
)
from codegenie.transforms._forward import SandboxedPath  # S1-04 stable import path


@pytest.mark.asyncio
async def test_bwrap_hello_world(tmp_path) -> None:
    if sys.platform != "linux":
        pytest.skip("bwrap is the Linux substrate; macOS uses sandbox-exec (S4-03)")
    if shutil.which("bwrap") is None:
        pytest.fail(
            "bwrap missing on Linux runner — CI setup step "
            "`apt-get install -y bubblewrap` failed or was skipped. "
            "Per ADR-0006 §Consequences + High-level-impl §Step 4 Risks (L310), "
            "this MUST fail (not skip) — silent skips defeat the substrate choice."
        )
    # SandboxedPath is currently TypeAlias = pathlib.Path (S1-04); S4-04 substitutes the real type.
    # Pre-S4-04: pass tmp_path directly. Post-S4-04: SandboxedPath.create(tmp_path, ".").unwrap().
    sp: SandboxedPath = tmp_path  # noqa — TypeAlias; substitute when S4-04 lands
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hello"),
        cwd=sp,
        env=NpmEnv(),
        network=DenyAll(),
        time_budget_s=5.0,
        memory_mib=64,
        pids_max=32,
    )
    result = await BwrapAdapter().run(spec)
    assert isinstance(result, Completed)
    assert result.exit_code == 0
```

`tests/integration/transforms/test_bwrap_network_policy.py` (AC-9 — live netns/pf check; **uses `node` not `curl`**, fail-not-skip if node missing):

```python
from __future__ import annotations
import os
import shutil
import sys

import pytest

from codegenie.transforms.sandbox.bwrap import BwrapAdapter
from codegenie.transforms.sandbox_jail import (
    Completed, JailedSubprocessSpec, NetworkDenied, NpmEnv, RegistryAllowlist,
)
from codegenie.transforms._forward import SandboxedPath
from codegenie.types.identifiers import RegistryUrl


@pytest.fixture
def _linux_bwrap_node_or_fail():
    if sys.platform != "linux":
        pytest.skip("Linux substrate")
    if shutil.which("bwrap") is None:
        pytest.fail("bwrap missing on Linux runner (see test_bwrap_hello_world)")
    if shutil.which("node") is None:
        pytest.fail(
            "node missing on Linux runner — needed for AC-9 network-policy live test. "
            "curl is intentionally NOT used (it's in the deny list of "
            "test_allowed_binaries_closed_set_regression). NO silent skip."
        )
    # AC-21: CAP_NET_ADMIN required for netns/pf setup
    if os.geteuid() != 0:
        # Heuristic: check capabilities file or attempt a no-op netns create.
        # If neither root nor CAP_NET_ADMIN, fail loudly.
        try:
            with open(f"/proc/{os.getpid()}/status") as f:
                if "CapEff:" not in f.read() or "0000000000001000" not in f.read():
                    pytest.fail(
                        "CAP_NET_ADMIN missing on Linux runner — run under sudo or "
                        "`setcap cap_net_admin+ep /usr/bin/python3`. NO silent skip."
                    )
        except OSError:
            pass


_REGISTRY_HOSTS = frozenset({RegistryUrl("https://registry.npmjs.org")})


@pytest.mark.asyncio
async def test_allowlist_permits_npm_registry(_linux_bwrap_node_or_fail, tmp_path) -> None:
    sp: SandboxedPath = tmp_path  # substitute when S4-04 lands
    spec = JailedSubprocessSpec(
        cmd=("node", "-e",
             "fetch('https://registry.npmjs.org/').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(2))"),
        cwd=sp,
        env=NpmEnv(),
        network=RegistryAllowlist(hosts=_REGISTRY_HOSTS),
        time_budget_s=10.0, memory_mib=128, pids_max=64,
    )
    result = await BwrapAdapter().run(spec)
    assert isinstance(result, Completed), f"unexpected: {result!r}"
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_allowlist_denies_github(_linux_bwrap_node_or_fail, tmp_path) -> None:
    sp: SandboxedPath = tmp_path
    spec = JailedSubprocessSpec(
        cmd=("node", "-e",
             "fetch('https://github.com/').then(r => process.exit(0)).catch(() => process.exit(1))"),
        cwd=sp,
        env=NpmEnv(),
        network=RegistryAllowlist(hosts=_REGISTRY_HOSTS),
        time_budget_s=10.0, memory_mib=128, pids_max=64,
    )
    result = await BwrapAdapter().run(spec)
    assert isinstance(result, NetworkDenied), f"expected NetworkDenied, got {result!r}"
    assert "github.com" in result.host
```

Run — every unit test fails (module missing); integration tests on a Linux runner fail at import time, then green after green-step.

### Green — make it pass

Implement per the Implementation outline. Order:
1. `Syscall` `StrEnum` + `_BLOCKED_SYSCALLS` constant (AC-24).
2. `_seccomp.py::build_filter` hand-written BPF (AC-3 helper input + output).
3. `_classify.py::classify_outcome` pure classifier (AC-23 + AC-5 SIGKILL discriminator + AC-5 NetworkDenied false-positive prevention).
4. `bwrap.py` argv composer with `str(spec.cwd)` (NOT `.absolute`) — passes AC-2.
5. `match`-dispatch on `NetworkPolicy` for DenyAll / RegistryAllowlist routing (AC-25 + AC-6 + AC-7).
6. `_setup_netns_with_allowlist` with uniquely-named netns (AC-20 Strategy A).
7. `BwrapAdapter.run` body — `try/finally` cleanup (AC-19), env_extra propagation (AC-10), `cmd` verbatim tail (AC-11), chokepoint call to `run_allowlisted`, classifier delegation, typed-error fence (AC-16).
8. Integration tests on Linux (AC-8 / AC-3-kernel-boundary / AC-9 / AC-12 / AC-26).

### Refactor — clean up

- Verify `_build_bwrap_argv(spec) -> list[str]` is extracted as a pure helper if `run` exceeds ~80 lines (functional-core discipline). The classifier (AC-23) and seccomp builder (AC-24) are already extracted by AC requirement — not optional.
- Verify `_setup_netns_with_allowlist(hosts: frozenset[RegistryUrl]) -> NetnsHandle` is a single function with a typed return (NetnsHandle dataclass), not a tuple.
- Module docstring cites ADR-0006 §Decision (exact bwrap flags + six seccomp syscalls) and the Validation note ("chokepoint is `run_allowlisted`, not `run_external_cli` — ADR-0012 §Decision documentation drift").
- Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/transforms/sandbox/ tests/`, `make lint-imports`.
- Confirm `pytest tests/unit/transforms/sandbox/ tests/integration/transforms/` green on a Linux box with `bubblewrap` + `node` + `CAP_NET_ADMIN`; on macOS, integration tests skip cleanly with the "Linux substrate" message.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/sandbox/__init__.py` | New package init (empty or one re-export). |
| `src/codegenie/transforms/sandbox/bwrap.py` | New: `BwrapAdapter` (structurally conforms to `SubprocessJail` — Protocol is NOT `@runtime_checkable`) with bwrap argv composer, seccomp filter handle, netns/pf integration via `match`-dispatch on `NetworkPolicy`, delegation to `_classify_outcome` for variant translation (AC-1..AC-7, AC-10..AC-11, AC-22, AC-25). |
| `src/codegenie/transforms/sandbox/_classify.py` | **NEW** (AC-23): pure `classify_outcome(process_result, raised_exception, spec, signals) -> JailedSubprocessResult` shared with `SandboxExecAdapter` (S4-03). Owns the SIGKILL discriminator (timeout-vs-OOM tie-break per AC-5), the NetworkDenied false-positive prevention (AC-5 / Coverage H2), the DiskQuotaExceeded best-effort path. |
| `src/codegenie/transforms/sandbox/_seccomp.py` | **NEW**: hand-written BPF builder `build_filter(blocked: frozenset[Syscall]) -> bytes` (AC-24). ~30 lines of `struct.pack` BPF bytecode using `linux/seccomp.h` constants. No new Python runtime dep (rejects the `pyseccomp` choice from the original story per Validation note above). |
| `tests/unit/transforms/sandbox/_fakes.py` | **NEW** (moved from `src/`): `FakeSandboxedPath` (shared with S4-01's tests if not already shared) + the parametric outcome-mocking helpers that AC-5 needs. **NOT under `src/`** — production-side test helpers are a smell. |
| `tests/unit/transforms/sandbox/test_bwrap_protocol.py` | **NEW** (AC-1): structural Protocol conformance via mypy + `inspect.signature` + `_StubBwrapAdapter`-style call-site exercise. NO `isinstance`. |
| `tests/unit/transforms/sandbox/test_bwrap_unit.py` | **NEW** (AC-2, AC-6, AC-7, AC-10, AC-11, AC-16, AC-17, AC-19): mocked `run_allowlisted` for argv shape, env_extra propagation, `match`-dispatch on `NetworkPolicy`, typed-error fence, determinism, cleanup-on-exception. |
| `tests/unit/transforms/sandbox/test_bwrap_no_direct_subprocess.py` | **NEW** (AC-4): AST walk against every module under `src/codegenie/transforms/sandbox/`. |
| `tests/unit/transforms/sandbox/test_bwrap_stateless.py` | **NEW** (AC-22): AST check + runtime double-call check for no module-level mutable globals. |
| `tests/unit/transforms/sandbox/test_bwrap_network_dispatch_mypy.py` | **NEW** (AC-25): subprocess-mypy negative test — commenting out the `RegistryAllowlist` arm fails mypy on `assert_never`. Mirrors S4-01 AC-9a. |
| `tests/unit/transforms/sandbox/test_classify.py` | **NEW** (AC-23, AC-5 SIGKILL discriminator): parametric tests of `classify_outcome` covering every variant + every tie-break branch. |
| `tests/unit/transforms/sandbox/test_seccomp_builder.py` | **NEW** (AC-24): tests `build_filter(_BLOCKED_SYSCALLS)` returns BPF bytecode whose magic-number/length match the expected shape; also a parametric tests that `build_filter(frozenset([Syscall.MOUNT]))` differs from `build_filter(frozenset([Syscall.PTRACE]))` (mutant that returns constant bytes for any input fails). |
| `tests/unit/transforms/sandbox/test_bwrap_properties.py` | **NEW** (AC-18): Hypothesis properties — DenyAll-no-share-net, allowlist-host-coverage, verbatim-cmd-preservation. |
| `tests/integration/transforms/test_bwrap_hello_world.py` | **NEW** (AC-8): Linux-only hello-world live test, fail-not-skip when bwrap missing. |
| `tests/integration/transforms/test_bwrap_seccomp_live.py` | **NEW** (AC-3 kernel-boundary): Linux-only live test that attempts a blocked syscall (`unshare -U`) and asserts SIGSYS. |
| `tests/integration/transforms/test_bwrap_network_policy.py` | **NEW** (AC-9): Linux-only live netns/pf egress tests using `node -e fetch(...)` (NOT `curl` — curl is in the deny list of the closed-set regression test). |
| `tests/integration/transforms/test_bwrap_postinstall_canary.py` | **NEW** (AC-12): two variants — substrate+flag (Variant A) and substrate-only-with-flag-disabled (Variant B = negative control). |
| `tests/integration/test_ci_setup_fence.py` | **NEW** (AC-15): greps `.github/workflows/*.yml` for `bubblewrap\|bwrap`; xfails until S9-01 lands, then hard-fails-if-missing. |
| `tests/fixtures/phase03/postinstall_canary/package.json` | **NEW** (AC-12 fixture): `{"scripts": {"postinstall": "node -e \"require('fs').writeFileSync(process.env.CANARY_PATH, 'x')\""}}`. |
| `tests/fixtures/phase03/postinstall_canary/README.md` | **NEW** (AC-12 fixture): one-line note on `CANARY_PATH` env-var contract; cross-reference to S8-04 for the full adversarial corpus. |

## Out of scope

- **`SandboxExecAdapter` (macOS)** — S4-03. Mirror Adapter on a different substrate; nightly-only test. MUST consume the shared `_classify_outcome` from this story (AC-23) — do not duplicate.
- **`SandboxedPath` real implementation** — S4-04. This story imports it from `codegenie.transforms._forward` (the stable shim path per S1-04) but does not write it; unit tests use `FakeSandboxedPath` from `tests/unit/transforms/sandbox/_fakes.py`; integration tests use `tmp_path` directly while the alias resolves to `pathlib.Path` (substitute to `SandboxedPath.create(tmp_path, ".").unwrap()` when S4-04 lands).
- **`ALLOWED_BINARIES` amendment for `bwrap` / `sandbox-exec` / `npm` / `jq`** — S4-05. **Precondition for this story.** S4-05 must (a) add `bwrap` (and `sandbox-exec`, `npm`, `jq`) to `ALLOWED_BINARIES` AND (b) remove `bwrap`/`bubblewrap` from `tests/unit/test_exec.py::test_allowed_binaries_closed_set_regression` (lines 362-363). Without both halves, this story's `run_allowlisted("bwrap", ...)` calls fail before any spawn. `curl` is NOT added by S4-05 — this story's AC-9 uses `node` (already in S4-05's set) instead.
- **`Capability` tokens + ruff fence** — S4-05. `BwrapAdapter` itself carries no capability (capabilities gate recipe engines, not substrates).
- **Full postinstall-canary adversarial test** — S8-04 lands `tests/adversarial/test_postinstall_canary.py` under `@pytest.mark.phase03_adv` with the full fixture portfolio. This story lands the integration-tier precursor (AC-12 Variant A) AND a negative control (AC-12 Variant B) that proves the substrate — not just the `--ignore-scripts` flag — is what suppresses the canary.
- **`bench_workflow_e2e_warm` performance budget** — S9-03. This story has only the AC-26 smoke (≤ 1.0 s wall-time on `/bin/true`, `@pytest.mark.bench`, NOT in `make check`).
- **The pf/iptables management itself across distros** — the Adapter's `_setup_netns_with_allowlist` is the seam; specific implementation (libpcap, iproute2, nftables, `setns(2)` direct) is the Adapter-author's choice within the constraint that the AC-9 live test passes on `ubuntu-24.04`. AC-20 Strategy A (uniquely-named netns per call) is pinned.
- **CI YAML edit** — S9-01 lands `.github/workflows/*.yml` changes (`apt-get install -y bubblewrap` + `node` setup + a Linux job that exposes `CAP_NET_ADMIN`). AC-15 pins the test discipline (`test_ci_setup_fence.py`) that xfails today and hard-fails-if-missing post-S9-01.
- **ADR-0012 §Decision wording amendment** — doc-only follow-up. The current ADR-0012 §Decision says "the SubprocessJail adapters wrap bwrap / sandbox-exec via `run_external_cli`" — this is documentation drift. The correct seam is `run_allowlisted` (which has `env_extra` and does NOT prepend its own implicit bwrap-wrap). Surface in `_attempts/S4-02.md` Attempt 1.
- **`High-level-impl.md:128` wording amendment** — doc-only follow-up. Line 128 says `pytest.skip` is correct; line 310 and ADR-0006 say `pytest.fail`. The latter wins. Surface in `_attempts/S4-02.md` Attempt 1.

## Notes for the implementer

- **Fail-not-skip is load-bearing.** Per `High-level-impl §Step 4 Risks` line 310 and `phase-arch-design.md §Edge case E7`: silent `pytest.skip` when `bwrap` is missing on Linux is the single most dangerous failure mode — it hides a missing CI setup step. AC-8 / AC-9 / AC-12 / AC-3-kernel-boundary use `pytest.fail` after the Linux-platform check passes. On macOS, `pytest.skip("Linux substrate")` is correct — the substrate genuinely isn't bwrap there. **Doc-debt:** `High-level-impl.md:128` says "must `pytest.skip`" — sloppy wording that contradicts L310 + ADR-0006. Surface in `_attempts/S4-02.md` Attempt 1 for a follow-up doc-only amendment; do NOT edit High-level-impl in this story (Rule 3 — surgical changes).
- **Single chokepoint: `run_allowlisted`.** Per Validation note (header) — ADR-0012 §Decision's "run_external_cli" wording is documentation drift. The Phase 2 `run_external_cli` is the probe-binary chokepoint that does its own bwrap-wrapping (`_maybe_wrap_with_bwrap`, `src/codegenie/exec/__init__.py:428`); calling it with `argv=["bwrap", ...]` would double-wrap AND collide with the closed-set regression test that pins `bwrap`/`bubblewrap` as MUST-NOT-be-allowlisted (`tests/unit/test_exec.py:362-363`). `run_allowlisted` is the canonical single-spawn chokepoint with `env_extra` support. AC-4's AST walk pins the single-chokepoint discipline at module level. **Surface in `_attempts/S4-02.md`:** "ADR-0012 §Decision wording needs amendment — adapters use `run_allowlisted`, not `run_external_cli`. Follow-up doc-only ADR amendment."
- **Seccomp filter is hand-written BPF — NO new Python runtime dep.** The original story listed `pyseccomp` as an option; validator removed it (no ADR amendment for a new runtime dep). The six syscalls are a fixed list — `_seccomp.py::build_filter(blocked: frozenset[Syscall]) -> bytes` returns ~30 lines of `struct.pack` BPF bytecode using `linux/seccomp.h` constants (`AUDIT_ARCH_X86_64`, `BPF_LD | BPF_W | BPF_ABS`, `seccomp_data.nr`, etc.). Syscall numbers per `/usr/include/asm/unistd_64.h`: `mount=165`, `pivot_root=155`, `ptrace=101`, `bpf=321`, `unshare=272`, `keyctl=250`. If a future need genuinely requires libseccomp, surface as a follow-up ADR amendment story. **No `pyseccomp`, no `seccomp`, no `libseccomp-python` in this story.**
- **Network policy enforcement uses uniquely-named netns per call (AC-20 Strategy A).** Each `BwrapAdapter().run()` creates a netns named `f"codegenie-jail-{uuid.uuid4().hex[:12]}"` so concurrent calls never share iptables tables. Teardown is unconditional via the `try/finally` (AC-19). Requires `CAP_NET_ADMIN` on the runner — see AC-21 for the typed `JailSetupFailed(reason="cap-net-admin-missing")` path when absent; integration test fixtures `pytest.fail` if `CAP_NET_ADMIN` is missing on Linux (no silent skip on permission failures). Document the `setcap cap_net_admin+ep` requirement in the operator runbook (S9-04 entry).
- **OOM signal source: cgroups v2 `memory.events`.** Read post-mortem from `/sys/fs/cgroup/<scope>/memory.events:oom_kill` (where `<scope>` is the cgroup the bwrap child ran in). On runners without cgroups v2 (cgroups v1 only), fall back to the `child_returncode == -SIGKILL AND peak_rss_mib > spec.memory_mib` heuristic — annotate the variant as `confidence='medium'` if the variant supports it (S4-01 doesn't currently include a confidence field on `OomKilled` — surface as a follow-up if needed; for now, the heuristic stands without annotation and AC-5's tie-break order applies).
- **NetworkDenied false-positive prevention.** The classifier returns `NetworkDenied(host)` ONLY when BOTH (a) the stderr matches a `_NETWORK_DENIED_PATTERNS` regex (`r"connect: Network is unreachable"`, `r"connect: Permission denied"`, `r"getaddrinfo.*Temporary failure"`, etc.) AND (b) the host literal appears in `spec.cmd` AND (c) that host is NOT in `spec.network.hosts` (when `network` is `RegistryAllowlist`). Ambiguous failures → `Completed(exit_code=N, stderr=<preserved>)`. Misclassifying a real failure as `NetworkPolicyViolation` triggers exit-4 in the orchestrator → operator-blocking; false negatives are strictly preferable.
- **DiskQuotaExceeded mechanism is best-effort.** bwrap's `--tmpfs /tmp` default size can be tuned via `--tmpfs-size <bytes>` (consider adding to the bwrap argv based on `spec.memory_mib` × a multiplier; not required for AC-5 to pass). The classifier matches `r"No space left on device"` in stderr; if not matched, falls back to `Completed`. S8-04 owns the adversarial-corpus backfill that constructs a fixture forcing the path.
- **`SandboxedPath` import path is stable.** Per S4-01 AC-11, `JailedSubprocessSpec.cwd: SandboxedPath` is imported from `codegenie.transforms._forward` (the established Phase-3-Step-1 shim — `TypeAlias = pathlib.Path` today; S4-04 substitutes the alias at the same import path). Integration tests should use `from codegenie.transforms._forward import SandboxedPath` (NOT `from codegenie.plugins.sandbox_path import SandboxedPath`). If S4-04 has not landed when this story is implemented, the unit tests use `FakeSandboxedPath` from `tests/unit/transforms/sandbox/_fakes.py`. The Adapter calls `str(spec.cwd)` (SandboxedPath instances are already-resolved absolute paths per ADR-0011) — **NOT `str(spec.cwd.absolute)`** (which is the bound-method-repr bug the original story carried).
- **No registry pattern for substrates.** A `@register_jail("linux-bwrap")` decorator pattern would match the codebase's `@register_probe` / `@register_index_freshness_check` / `@register_dep_graph_strategy` precedents — but substrate selection happens at orchestrator construction time, not request time, so a registry adds ceremony without paying rent (Rule 2). Constructor injection (`RemediationOrchestrator(sandbox: SubprocessJail | None = None)`) is the right shape — Phase 5's `FirecrackerAdapter` swaps in via constructor argument. Do NOT introduce a registry here; do NOT hard-code `BwrapAdapter()` in any orchestrator or recipe-engine constructor (always accept a `SubprocessJail` parameter).
- **No capability token.** ADR-0011 capability tokens (e.g., `GitLocalOpsCapability`) gate **recipe engines** (callers), not substrates. `BwrapAdapter` is a pure mechanism — no `Capability` field, no construction-time token check. S4-05 lands the `Capability` infrastructure for recipe-engine call sites.
- **Stateless across calls.** No module-level mutable globals introduced (AC-22). Do NOT copy `run_external_cli`'s `_BWRAP_WARNED` pattern — it's hidden state across `.run()` calls and a testability hazard. Any caching MUST be instance state passed via constructor (and there's no reason to cache anything in this story — seccomp bytes are deterministic from `_BLOCKED_SYSCALLS`; netns is per-call).
- **Pure helpers carry the logic; `run()` is the only impure code.** Functional-core / imperative-shell discipline per CLAUDE.md. `classify_outcome` is pure (no I/O). `_build_seccomp_filter` is pure. The argv composer is pure. `run` is the only function in the module that does I/O (chokepoint call, file open, netns syscalls).
- **Strict types throughout.** `argv: list[str]`, `cmd: tuple[str, ...]`, `env_extra: dict[str, str]` — no `Any`, no `object`, no untyped dicts. Test-side `dict[str, object]` capture dicts are scaffolding only; production-side types are tight.
- **Performance envelope ~80–200 ms per spawn.** ADR-0006 §Tradeoffs row 6. AC-26 is a perf SMOKE (≤ 1.0 s, 5× headroom) marked `@pytest.mark.bench` — NOT in `make check`, NOT a regression gate. S9-03's `bench_workflow_e2e_warm` owns the real budget.
- **No `LowLevelAPIWishlist` features.** Resist the urge to add `JailedSubprocessSpec.uid_map`, `gid_map`, `extra_bind_ro_paths`, etc. — every field is in ADR-0006 §Decision or it isn't in the Port. Adding fields here without amending S4-01 + ADR-0006 is silent contract drift; if a need arises, surface it as a follow-up ADR-amendment story (Rule 8 — Read before you write).
- **`SandboxExecAdapter` (S4-03) MUST consume `_classify_outcome` and `_seccomp` symmetries.** The classifier is substrate-agnostic; the seccomp/sandbox-profile builder is substrate-specific (`_seccomp.py` for Linux; an analogous `_sandbox_exec_profile.py` for macOS). S4-03 implementer: DO NOT copy-paste `classify_outcome` — import it. Rule-of-two satisfied at the boundary where the second adapter would otherwise duplicate.
