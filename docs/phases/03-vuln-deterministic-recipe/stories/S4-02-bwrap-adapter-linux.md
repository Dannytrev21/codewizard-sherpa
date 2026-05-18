# Story S4-02 — `BwrapAdapter` (Linux) — `bwrap --unshare-all` + seccomp + netns

**Step:** Step 4 — SubprocessJail Port + Bwrap + sandbox-exec + ALLOWED_BINARIES amendment
**Status:** Ready
**Effort:** L
**Depends on:** S4-01 (`SubprocessJail` Protocol, `JailedSubprocessSpec`, `JailedSubprocessResult` discriminated union, `NetworkPolicy = DenyAll | RegistryAllowlist` sum); transitively S1-03 (sum types)
**ADRs honored:** 03-ADR-0006 (`BwrapAdapter` is the Linux Adapter of the `SubprocessJail` Port; bwrap command-line and seccomp filter pinned in §Decision); 03-ADR-0012 (`bwrap` added to `ALLOWED_BINARIES` — S4-05 lands the data change; this story is the consumer)

## Context

S4-01 landed the `SubprocessJail` Protocol — `async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult` — but no implementation. This story lands the **Linux Adapter**: `BwrapAdapter` wraps every child invocation in `bwrap --unshare-all --new-session --die-with-parent --ro-bind / / --tmpfs /tmp --bind <jail> <jail>`, applies a seccomp filter that blocks `mount`, `pivot_root`, `ptrace`, `bpf`, `unshare`, `keyctl`, and enforces `NetworkPolicy` at the network-namespace layer (parent owns netns; child sees `lo` + pf-routed allowlist hosts).

The architecture rationale (`phase-arch-design.md §Component design C8`, §Physical view, §Edge cases E7+E8+E12) is that Phase 3 cannot wait for Phase 5's Firecracker microVM, but the operator-laptop / CI threat model demands real isolation against a malicious target repo's `package.json`. bwrap on Linux + sandbox-exec on macOS (S4-03) are the two interim substrates; Phase 5's `FirecrackerAdapter` and `DinDAdapter` substitute via the same Port.

`bwrap` invocations route through `run_external_cli` (Phase 2's wrapper around `run_allowlisted`) — no `subprocess.run` direct calls (ADR-0012 §Decision: "the `SubprocessJail` adapters wrap `bwrap` / `sandbox-exec` via `run_external_cli` — they do NOT bypass the chokepoint"). S4-05 amends `ALLOWED_BINARIES` to admit `bwrap` (and the inner `npm` for the recipe-engine call sites); this story consumes that amendment.

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
5. Routes through `run_external_cli` for the outer `bwrap` invocation (no direct `subprocess.run`).
6. An integration test (`tests/integration/transforms/test_bwrap_hello_world.py`) **fails** (does NOT skip) when run on Linux with `bwrap` missing — loud failure surface for CI's `apt-get install -y bubblewrap` step.

`mypy --strict` clean. The Adapter's failure path emits typed `JailedSubprocessResult` variants only — no bare exceptions cross the Port boundary.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/transforms/sandbox/__init__.py` and `src/codegenie/transforms/sandbox/bwrap.py` exist. `BwrapAdapter` is exported and conforms to `SubprocessJail` (Protocol check: `isinstance(BwrapAdapter(), SubprocessJail)` via `runtime_checkable` or structural mypy verification).
- [ ] **AC-2.** `BwrapAdapter.run` invokes `run_external_cli` with argv starting `["bwrap", "--unshare-all", "--new-session", "--die-with-parent", "--ro-bind", "/", "/", "--tmpfs", "/tmp", "--bind", <jail-abs>, <jail-abs>, ...]`. A unit test mocks `run_external_cli` (or `asyncio.create_subprocess_exec` inside it) and asserts the argv prefix exactly matches. The mock returns a synthesized `Completed`-equivalent and the test verifies the Adapter translates correctly.
- [ ] **AC-3.** The seccomp filter passed to bwrap (via `--seccomp <fd>` or an equivalent `--seccomp` mechanism the Adapter author chooses; ADR-0006 leaves the wire format to the Adapter) blocks exactly six syscalls: `mount`, `pivot_root`, `ptrace`, `bpf`, `unshare`, `keyctl`. A unit test asserts the filter content (either the BPF bytecode if generated in-process, or the `seccomp-tools` output of the temp file the Adapter writes) contains the six syscall names.
- [ ] **AC-4.** `BwrapAdapter` NEVER calls `subprocess.run`, `asyncio.create_subprocess_exec`, `os.system`, `os.popen`, or `shell=True`. A grep test (`tests/unit/transforms/sandbox/test_bwrap_no_direct_subprocess.py`) reads `src/codegenie/transforms/sandbox/bwrap.py` and asserts none of those patterns appear. The single subprocess chokepoint is `run_external_cli` (Phase 2 ADR-0001 / `forbidden-patterns` hook discipline).
- [ ] **AC-5.** Every `JailedSubprocessResult` variant is reachable. Unit tests with a mocked `run_external_cli` synthesize each underlying signal/condition and assert the Adapter translates to the right variant:
  - Clean exit 0 → `Completed(exit_code=0, wall_time_s=..., stdout_bytes=..., stderr_bytes=...)`.
  - Child killed with SIGKILL after the deadline → `TimedOut(budget_s=spec.time_budget_s, elapsed_s=...)` (NOT `Completed(exit_code=-9)`).
  - Child killed by OOM (oom_score / cgroups signal — mocked by setting `peak_rss_mib > spec.memory_mib`) → `OomKilled(peak_rss_mib=...)`.
  - Child attempted egress to a host not in `RegistryAllowlist` (mocked by raising the pf/netns-blocked condition) → `NetworkDenied(host="evil.example.com")`.
  - Tmpfs/disk-quota signal → `DiskQuotaExceeded(quota_bytes=..., bytes_written=...)`.
- [ ] **AC-6.** `NetworkPolicy = DenyAll` results in child invocation with no network interfaces beyond `lo`. A unit test passes `NetworkPolicy.DenyAll()` and asserts the bwrap argv contains no `--share-net` and the netns setup omits any host-route. (Implementation detail of "how" is Adapter-author choice; the test pins the observable contract: `--unshare-all` ⇒ unshared netns ⇒ DenyAll satisfied.)
- [ ] **AC-7.** `NetworkPolicy = RegistryAllowlist(hosts)` results in netns + pf/iptables rules permitting exactly those hosts on port 443. A unit test passes `RegistryAllowlist(hosts=frozenset({RegistryUrl("https://registry.npmjs.org")}))` and asserts the Adapter calls its host-allow-rules helper with that exact frozenset. (The pf/iptables call itself is mocked at this layer; integration test in AC-9 exercises the live path.)
- [ ] **AC-8.** **Linux-only integration test, FAIL not SKIP when bwrap missing.** `tests/integration/transforms/test_bwrap_hello_world.py` runs on Linux runners only (gated by `sys.platform == "linux"`; on macOS the test does `pytest.skip("Linux substrate")` — explicit, non-Linux skip is acceptable). On Linux:
  - The test runs `await BwrapAdapter().run(spec)` where `spec.cmd = ("/bin/echo", "hello")` (or another bwrap-allowlisted demonstration that doesn't need network) and asserts `Completed(exit_code=0)`.
  - When `shutil.which("bwrap") is None` on Linux, the test calls `pytest.fail("bwrap missing on Linux runner — CI's apt-get install -y bubblewrap step failed or was skipped")`. This is the load-bearing assertion per `High-level-impl §Step 4 Risks`: silent skip defeats the substrate choice.
- [ ] **AC-9.** **Linux-only network-policy live test.** `tests/integration/transforms/test_bwrap_network_policy.py` (same Linux/skip gate; same fail-when-bwrap-missing discipline) runs two cases inside the live jail:
  - `RegistryAllowlist(hosts=frozenset({RegistryUrl("https://registry.npmjs.org")}))` + `cmd=("curl", "--max-time", "5", "https://registry.npmjs.org/")` → `Completed` (network reachable; curl exits 0 or with a 200/3xx HTTP code). Note: this requires `curl` to be available inside the jail's `--ro-bind / /` view; if the CI image lacks `curl`, the test uses `node -e "fetch(...)..."` since `node` is already in `ALLOWED_BINARIES` and on the runner.
  - `RegistryAllowlist(hosts=frozenset({RegistryUrl("https://registry.npmjs.org")}))` + `cmd=("curl", "--max-time", "5", "https://github.com/")` → `NetworkDenied(host=...)` (`github.com` is not in the allowlist; connect blocked by netns/pf rules).
- [ ] **AC-10.** Mocked-substrate unit test for `JailedSubprocessSpec.env` flow: when `env = NpmEnv()`, the Adapter passes the result of `env.to_env_mapping()` (which always contains `npm_config_ignore_scripts="true"` per S4-01 AC-7) to `run_external_cli`'s `env_extra` parameter. Asserts the captured env contains the key. This ties S4-01's structural env defense to S4-02's call-site discipline.
- [ ] **AC-11.** The Adapter does not bypass `--ignore-scripts` at the CLI layer either — though the CLI half of `--ignore-scripts` is the consumer's (S5-02's `NpmLockfileRecipeEngine`) responsibility per ADR-0006, this Adapter does NOT strip or modify `spec.cmd`. A unit test passes `spec.cmd = ("npm", "install", "--ignore-scripts", "--package-lock-only")` and asserts the inner `cmd` is preserved verbatim in the bwrap invocation. (S4-05 lands the static fence test that ties npm-engine call sites to `--ignore-scripts` in `cmd`.)
- [ ] **AC-12.** Postinstall-canary adversarial precursor: `tests/integration/transforms/test_bwrap_postinstall_canary.py` (Linux-only) builds a tiny fixture `package.json` whose `scripts.postinstall` writes a canary file outside the jail's bind-mount target. Runs `BwrapAdapter().run(JailedSubprocessSpec(cmd=("npm", "install", "--ignore-scripts", "--package-lock-only"), ...))` and asserts:
  - `Completed(exit_code=0)` returned.
  - Canary file does NOT exist after the run (the postinstall is suppressed by `--ignore-scripts` env+CLI; even if postinstall ran, the bwrap binds prevent writing outside the jail).
  - Full adversarial regression test (`tests/adversarial/test_postinstall_canary.py` under `@pytest.mark.phase03_adv`) is S8-04's responsibility; this story lands the integration-tier precursor that proves the substrate works.
- [ ] **AC-13.** `mypy --strict src/codegenie/transforms/sandbox/ tests/unit/transforms/sandbox/ tests/integration/transforms/` clean. `ruff check` + `ruff format --check` clean on touched files.
- [ ] **AC-14.** `make lint-imports` Phase 3 contract (S1-05): no LLM SDK imported from `src/codegenie/transforms/sandbox/`. The `tests/fence/test_no_llm_in_transforms.py` extends to cover the new submodule (or already does via prefix matching).
- [ ] **AC-15.** CI integration: `.github/workflows/*.yml` (the Phase 3 / `make check` runner config; or whichever workflow runs `pytest tests/integration/`) has an explicit `- run: sudo apt-get install -y bubblewrap` (or equivalent) step on the Linux job. S9-01 lands the actual CI config edit; this AC pins that the integration test will detect a missing setup-step regression by failing loudly (per AC-8).

## Implementation outline

1. Create `src/codegenie/transforms/sandbox/__init__.py` (empty or re-exporting `BwrapAdapter` and the to-come `SandboxExecAdapter`).
2. Create `src/codegenie/transforms/sandbox/bwrap.py`. Imports: `from __future__ import annotations`, `asyncio`, `os`, `pathlib.Path`, `shutil`, `sys`, `time`, `codegenie.exec.run_external_cli`, `codegenie.transforms.sandbox_jail.{SubprocessJail, JailedSubprocessSpec, JailedSubprocessResult, Completed, TimedOut, OomKilled, NetworkDenied, DiskQuotaExceeded, DenyAll, RegistryAllowlist}`.
3. Define `class BwrapAdapter:` with `async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult`.
4. Inside `run`:
   - Compose the bwrap argv prefix: `["bwrap", "--unshare-all", "--new-session", "--die-with-parent", "--ro-bind", "/", "/", "--tmpfs", "/tmp", "--bind", str(spec.cwd.absolute), str(spec.cwd.absolute)]`.
   - Generate the seccomp filter for the six blocked syscalls; write to a temp file or pass via `--seccomp <fd>` per the chosen mechanism.
   - Configure the network namespace per `spec.network`: `DenyAll` → nothing extra (bwrap's `--unshare-all` covers it); `RegistryAllowlist` → set up parent-process netns with pf/iptables rules permitting only `spec.network.hosts` on port 443. (Implementation detail: a helper module `src/codegenie/transforms/sandbox/network.py` may emerge — surgical, only if the bwrap module exceeds ~250 lines.)
   - Build the inner-env mapping: `env_extra = spec.env.to_env_mapping()` (the NpmEnv / GitEnv structural defenses ride along automatically).
   - Append `spec.cmd` to the bwrap argv.
   - `await run_external_cli(argv, cwd=spec.cwd.absolute, timeout_s=spec.time_budget_s, env_extra=env_extra, allowlisted_egress=frozenset(...))`.
   - Translate the `run_external_cli` return / exception to the right `JailedSubprocessResult` variant. Specifically: `ProbeTimeoutError` → `TimedOut`; oom-signal (post-mortem check via `resource.getrusage` or cgroups inspection) → `OomKilled`; non-zero exit → `Completed(exit_code=..)` (failure-mode classification is the caller's; the Port wraps the outcome but does not interpret npm-specific exit codes); netns-blocked egress (detected via the child's stderr or a sentinel error) → `NetworkDenied`.
5. Write the unit tests against a mocked `run_external_cli` (AC-1..AC-7, AC-10, AC-11).
6. Write the live integration tests (AC-8, AC-9, AC-12) gated on `sys.platform == "linux"` with explicit `pytest.fail` (not `pytest.skip`) when `bwrap` is missing on Linux.
7. Run `mypy --strict`, `ruff`, and `pytest tests/unit/transforms/sandbox/ tests/integration/transforms/`. On a Linux dev box or CI runner, the integration tests should be green; on macOS, they skip (AC-8 / AC-9 / AC-12 all check `sys.platform`).

## TDD plan — red / green / refactor

### Red — write the failing tests first

`tests/unit/transforms/sandbox/test_bwrap_unit.py` (cross-platform; mocks `run_external_cli`):

```python
from __future__ import annotations

import sys
from unittest import mock

import pytest

from codegenie.transforms.sandbox.bwrap import BwrapAdapter  # RED: module doesn't exist yet
from codegenie.transforms.sandbox_jail import (
    Completed, DenyAll, JailedSubprocessSpec, NetworkDenied, NpmEnv,
    OomKilled, RegistryAllowlist, SubprocessJail, TimedOut,
)
from codegenie.types.identifiers import RegistryUrl


def _spec(**over: object) -> JailedSubprocessSpec:
    from tests.unit.transforms._fakes import FakeSandboxedPath  # tiny test helper
    defaults: dict[str, object] = dict(
        cmd=("/bin/echo", "hi"),
        cwd=FakeSandboxedPath("/tmp/jail"),
        env=NpmEnv(),
        network=DenyAll(),
        time_budget_s=5.0,
        memory_mib=128,
        pids_max=64,
    )
    defaults.update(over)
    return JailedSubprocessSpec(**defaults)  # type: ignore[arg-type]


# AC-1: Adapter conforms to Protocol
def test_bwrap_adapter_conforms_to_protocol() -> None:
    adapter: SubprocessJail = BwrapAdapter()
    assert hasattr(adapter, "run")


# AC-2: argv prefix matches ADR-0006 §Decision exactly
async def test_argv_prefix_matches_adr_0006(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_run_external_cli(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["argv"] = args[0] if args else kwargs.get("argv")
        captured["kwargs"] = kwargs
        return type("R", (), {"exit_code": 0, "stdout": b"", "stderr": b"", "wall_s": 0.05})()

    monkeypatch.setattr(
        "codegenie.transforms.sandbox.bwrap.run_external_cli", fake_run_external_cli
    )
    await BwrapAdapter().run(_spec())
    argv = captured["argv"]
    expected_prefix = [
        "bwrap", "--unshare-all", "--new-session", "--die-with-parent",
        "--ro-bind", "/", "/", "--tmpfs", "/tmp",
        "--bind", "/tmp/jail", "/tmp/jail",
    ]
    assert argv[: len(expected_prefix)] == expected_prefix


# AC-3: seccomp filter blocks exactly the six syscalls
async def test_seccomp_filter_blocks_six_syscalls(monkeypatch, tmp_path) -> None:
    captured_seccomp: dict[str, set[str]] = {}

    def fake_build_seccomp(blocked: set[str]) -> bytes:
        captured_seccomp["blocked"] = set(blocked)
        return b"\x00"  # opaque BPF placeholder for the test

    monkeypatch.setattr(
        "codegenie.transforms.sandbox.bwrap._build_seccomp_filter", fake_build_seccomp
    )
    # stub run_external_cli so the test doesn't actually spawn
    async def noop(*a, **k):
        return type("R", (), {"exit_code": 0, "stdout": b"", "stderr": b"", "wall_s": 0.0})()
    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_external_cli", noop)

    await BwrapAdapter().run(_spec())
    assert captured_seccomp["blocked"] == {
        "mount", "pivot_root", "ptrace", "bpf", "unshare", "keyctl",
    }


# AC-4: no direct subprocess use anywhere in the module
def test_module_has_no_direct_subprocess() -> None:
    from pathlib import Path
    src = Path("src/codegenie/transforms/sandbox/bwrap.py").read_text()
    for bad in ("subprocess.run", "create_subprocess_exec", "os.system", "os.popen", "shell=True"):
        assert bad not in src, f"forbidden subprocess pattern in bwrap.py: {bad!r}"


# AC-5: result-variant translation across mocked underlying signals
@pytest.mark.parametrize(
    "fake_outcome, expected_variant",
    [
        ("clean_zero", Completed),
        ("timeout", TimedOut),
        ("oom", OomKilled),
        ("egress_blocked", NetworkDenied),
        # disk_quota covered in a dedicated parametric below
    ],
)
async def test_result_variant_translation(
    fake_outcome: str, expected_variant: type, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The exact fake-injection mechanism depends on the Adapter's internals;
    # the test pins the contract: each underlying signal → one typed variant.
    from codegenie.transforms.sandbox._fakes_for_tests import inject_fake_outcome
    inject_fake_outcome(monkeypatch, fake_outcome)
    result = await BwrapAdapter().run(_spec())
    assert isinstance(result, expected_variant)


# AC-6: DenyAll ⇒ no --share-net
async def test_deny_all_no_share_net(monkeypatch) -> None:
    captured = {}
    async def fake(*a, **k):
        captured["argv"] = a[0] if a else k.get("argv")
        return type("R", (), {"exit_code": 0, "stdout": b"", "stderr": b"", "wall_s": 0.0})()
    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_external_cli", fake)
    await BwrapAdapter().run(_spec(network=DenyAll()))
    assert "--share-net" not in captured["argv"]


# AC-7: RegistryAllowlist passes hosts to the allow-rules helper exactly
async def test_registry_allowlist_routes_hosts(monkeypatch) -> None:
    captured_hosts: dict[str, frozenset[RegistryUrl]] = {}

    def fake_setup_netns(hosts):  # noqa: ANN001
        captured_hosts["hosts"] = hosts
    monkeypatch.setattr(
        "codegenie.transforms.sandbox.bwrap._setup_netns_with_allowlist", fake_setup_netns
    )
    async def noop(*a, **k):
        return type("R", (), {"exit_code": 0, "stdout": b"", "stderr": b"", "wall_s": 0.0})()
    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_external_cli", noop)
    hosts = frozenset({RegistryUrl("https://registry.npmjs.org")})
    await BwrapAdapter().run(_spec(network=RegistryAllowlist(hosts=hosts)))
    assert captured_hosts["hosts"] == hosts


# AC-10: NpmEnv.to_env_mapping passed to run_external_cli's env_extra
async def test_npm_env_mapping_reaches_run_external_cli(monkeypatch) -> None:
    captured = {}
    async def fake(*a, **k):
        captured["env_extra"] = k.get("env_extra", {})
        return type("R", (), {"exit_code": 0, "stdout": b"", "stderr": b"", "wall_s": 0.0})()
    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_external_cli", fake)
    await BwrapAdapter().run(_spec(env=NpmEnv()))
    assert captured["env_extra"].get("npm_config_ignore_scripts") == "true"


# AC-11: spec.cmd is preserved verbatim, including --ignore-scripts
async def test_cmd_preserved_verbatim(monkeypatch) -> None:
    captured = {}
    async def fake(*a, **k):
        captured["argv"] = a[0] if a else k.get("argv")
        return type("R", (), {"exit_code": 0, "stdout": b"", "stderr": b"", "wall_s": 0.0})()
    monkeypatch.setattr("codegenie.transforms.sandbox.bwrap.run_external_cli", fake)
    cmd = ("npm", "install", "--ignore-scripts", "--package-lock-only", "--no-audit")
    await BwrapAdapter().run(_spec(cmd=cmd))
    # the inner cmd is the tail of the bwrap argv; verbatim preservation
    for token in cmd:
        assert token in captured["argv"]
    # in-order, contiguous
    n = len(cmd)
    tail = captured["argv"][-n:]
    assert tuple(tail) == cmd
```

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


@pytest.mark.asyncio
async def test_bwrap_hello_world(tmp_path) -> None:
    if sys.platform != "linux":
        pytest.skip("bwrap is the Linux substrate; macOS uses sandbox-exec (S4-03)")
    if shutil.which("bwrap") is None:
        pytest.fail(
            "bwrap missing on Linux runner — CI setup step "
            "`apt-get install -y bubblewrap` failed or was skipped. "
            "Per High-level-impl §Step 4 Risks, this MUST fail (not skip) — "
            "silent skips defeat the substrate choice."
        )
    from codegenie.plugins.sandbox_path import SandboxedPath  # S4-04
    jail = tmp_path
    sp = SandboxedPath.create(jail, ".").unwrap()  # Result[SandboxedPath, PathEscape]
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

`tests/integration/transforms/test_bwrap_network_policy.py` (AC-9 — live netns/pf check):

```python
from __future__ import annotations
import shutil
import sys

import pytest

from codegenie.transforms.sandbox.bwrap import BwrapAdapter
from codegenie.transforms.sandbox_jail import (
    Completed, JailedSubprocessSpec, NetworkDenied, NpmEnv, RegistryAllowlist,
)
from codegenie.types.identifiers import RegistryUrl


@pytest.fixture
def _linux_bwrap_or_fail():
    if sys.platform != "linux":
        pytest.skip("Linux substrate")
    if shutil.which("bwrap") is None:
        pytest.fail("bwrap missing on Linux runner (see test_bwrap_hello_world)")


@pytest.mark.asyncio
async def test_allowlist_permits_npm_registry(_linux_bwrap_or_fail, tmp_path) -> None:
    from codegenie.plugins.sandbox_path import SandboxedPath
    sp = SandboxedPath.create(tmp_path, ".").unwrap()
    spec = JailedSubprocessSpec(
        cmd=("curl", "--max-time", "5", "-o", "/dev/null", "-s", "-w", "%{http_code}",
             "https://registry.npmjs.org/"),
        cwd=sp,
        env=NpmEnv(),
        network=RegistryAllowlist(hosts=frozenset({
            RegistryUrl("https://registry.npmjs.org"),
        })),
        time_budget_s=10.0, memory_mib=128, pids_max=64,
    )
    result = await BwrapAdapter().run(spec)
    assert isinstance(result, Completed), f"unexpected: {result!r}"


@pytest.mark.asyncio
async def test_allowlist_denies_github(_linux_bwrap_or_fail, tmp_path) -> None:
    from codegenie.plugins.sandbox_path import SandboxedPath
    sp = SandboxedPath.create(tmp_path, ".").unwrap()
    spec = JailedSubprocessSpec(
        cmd=("curl", "--max-time", "5", "https://github.com/"),
        cwd=sp,
        env=NpmEnv(),
        network=RegistryAllowlist(hosts=frozenset({
            RegistryUrl("https://registry.npmjs.org"),
        })),
        time_budget_s=10.0, memory_mib=128, pids_max=64,
    )
    result = await BwrapAdapter().run(spec)
    assert isinstance(result, NetworkDenied)
    assert "github.com" in result.host
```

Run — every unit test fails (module missing); integration tests on a Linux runner fail at import time, then green after green-step.

### Green — make it pass

Implement `BwrapAdapter` per the Implementation outline. Order: argv composer first (passes AC-2), seccomp filter (AC-3), DenyAll/Allowlist routing (AC-6, AC-7), env mapping (AC-10), cmd preservation (AC-11), result-variant translator (AC-5). Then run the integration tests on a Linux box (or CI).

### Refactor — clean up

- Extract argv composition into a pure helper `_build_bwrap_argv(spec) -> tuple[str, ...]` if the `run` method exceeds ~80 lines (functional-core discipline; mirrors the codebase convention from `phase-arch-design.md §Anti-patterns avoided`).
- Extract seccomp-filter generation into `_build_seccomp_filter(blocked: set[str]) -> bytes` so the AC-3 monkeypatch target is real, not a hand-waved sentinel.
- Extract `_setup_netns_with_allowlist(hosts: frozenset[RegistryUrl]) -> None` (or a small `Network` helper class) so the AC-7 monkeypatch target is real.
- Add module docstring citing ADR-0006 §Decision (the exact bwrap flags + the six seccomp syscalls).
- Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/transforms/sandbox/ tests/`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/sandbox/__init__.py` | New package init (empty or one re-export). |
| `src/codegenie/transforms/sandbox/bwrap.py` | New: `BwrapAdapter(SubprocessJail)` with bwrap argv composer, seccomp filter, netns/pf integration, result-variant translator (AC-1..AC-7, AC-10..AC-11). |
| `src/codegenie/transforms/sandbox/_fakes_for_tests.py` | Tiny helper for AC-5's parametric mock injection. Lives next to the production code (not under `tests/`) so the production code can import it under `if TYPE_CHECKING:` for typing only. Alternative: move to `tests/_helpers/` if the project's convention forbids prod-side test helpers (verify via `grep -r "_fakes_for_tests" src/` for precedent). |
| `tests/unit/transforms/sandbox/test_bwrap_unit.py` | New: AC-1..AC-7, AC-10, AC-11 against mocked `run_external_cli`. |
| `tests/unit/transforms/sandbox/test_bwrap_no_direct_subprocess.py` | New: AC-4 grep test. |
| `tests/integration/transforms/test_bwrap_hello_world.py` | New: AC-8 Linux-only hello-world live test with fail-not-skip discipline. |
| `tests/integration/transforms/test_bwrap_network_policy.py` | New: AC-9 Linux-only live netns/pf egress tests. |
| `tests/integration/transforms/test_bwrap_postinstall_canary.py` | New: AC-12 postinstall-canary integration precursor. |
| `tests/unit/transforms/_fakes.py` | Existing or new helper holding `FakeSandboxedPath` shim (shared with S4-01's tests). If the S4-04 real `SandboxedPath` has landed, prefer the real one. |

## Out of scope

- **`SandboxExecAdapter` (macOS)** — S4-03. Mirror Adapter on a different substrate; nightly-only test.
- **`SandboxedPath` implementation** — S4-04. This story imports it but does not write it; if S4-04 lands later, the integration tests use the real path; in the unit tests, `FakeSandboxedPath` suffices.
- **`ALLOWED_BINARIES` amendment for `bwrap` / `npm` / `curl`** — S4-05. This story's integration tests assume `bwrap` is allowlisted; if it isn't, they fail at `run_external_cli` rejection — which is the right red signal that S4-05 must land alongside or before this story.
- **`Capability` tokens + ruff fence** — S4-05.
- **Full postinstall-canary adversarial test** — S8-04 lands `tests/adversarial/test_postinstall_canary.py` under `@pytest.mark.phase03_adv` with the full fixture portfolio. This story lands only the integration-tier precursor (AC-12) that proves the substrate works on one fixture.
- **`bench_workflow_e2e_warm` performance budget** — S9-03.
- **The pf/iptables management itself across distros** — the Adapter's `_setup_netns_with_allowlist` is the seam; specific implementation (libpcap, iproute2, nftables, `setns(2)` direct) is the Adapter-author's choice within the constraint that the AC-9 live test passes on `ubuntu-24.04`.
- **CI YAML edit** — S9-01 lands `.github/workflows/*.yml` changes (the `apt-get install -y bubblewrap` step). AC-15 here pins the test discipline that surfaces a missing CI step.

## Notes for the implementer

- **Fail-not-skip is load-bearing.** Per `High-level-impl §Step 4 Risks` and `phase-arch-design.md §Edge case E7`: silent `pytest.skip` when `bwrap` is missing on Linux is the single most dangerous failure mode — it hides a missing CI setup step and lets a regression land that the threat model says must be caught. The `_linux_bwrap_or_fail` fixture in AC-8 / AC-9 uses `pytest.fail` after the Linux-platform check passes. On macOS, `pytest.skip("Linux substrate")` is correct — the substrate genuinely isn't bwrap there.
- **Single chokepoint: `run_external_cli`.** Per ADR-0012 §Decision and the `forbidden-patterns` pre-commit hook (`tests/adv/test_no_shell_true.py` enforces no `subprocess.run` outside `src/codegenie/exec.py`). The Adapter assembles argv + env + cwd and calls `run_external_cli` — that's the whole subprocess surface. AC-4's grep test pins this at file level.
- **Seccomp wire format is the Adapter-author's call.** ADR-0006 says "seccomp blocks `mount`, `pivot_root`, `ptrace`, `bpf`, `unshare`, `keyctl`" — it does NOT mandate libseccomp vs hand-written BPF vs `--seccomp <fd>` mechanism. AC-3 pins the *which-six*; the *how* is implementation choice. If using libseccomp (Python bindings via `pyseccomp` or `seccomp`), add the dep to `pyproject.toml`'s Phase 3 dependency group with an ADR-0006 cross-reference; if hand-writing BPF, ship a small `tools/seccomp/build_filter.py` helper. Either is fine.
- **Network policy enforcement is parent-process responsibility.** ADR-0006 §Decision: "Parent process owns the network namespace; child sees `lo` + pf-routed `RegistryAllowlist`." The Adapter creates the netns + pf/iptables rules, then `bwrap --unshare-all` keeps the child in that netns. The pf/iptables tooling needs CAP_NET_ADMIN — Linux CI runners have it; rootless dev workstations may need a one-time `setcap` or `sudo` setup helper. Document in the operator runbook (S9-04 entry).
- **DiskQuotaExceeded mechanism.** bwrap's `--tmpfs /tmp` has a default size; if a child writes > tmpfs cap, the underlying write fails with ENOSPC. The Adapter's translator catches this in the child's exit status / stderr (or by polling cgroups disk-quota signals on Linux) and emits `DiskQuotaExceeded(quota_bytes=..., bytes_written=...)`. If a clean wire-format isn't available cheaply, leave the variant *reachable but rarely-triggered* — S8-04's adversarial-test backfill can construct a deliberate fixture.
- **Forward-string `SandboxedPath`.** Per S4-01 AC-11, `JailedSubprocessSpec.cwd: SandboxedPath` is forward-imported under `TYPE_CHECKING`. The Adapter calls `spec.cwd.absolute` — a `Path`-typed property. If S4-04 has not landed when this story is implemented, the unit tests use `FakeSandboxedPath` (a tiny shim exposing `.absolute`); the integration tests require S4-04 to land first. The dependency DAG (manifest) shows S4-04 depending on S4-01, with S4-02 also depending on S4-01 — implementers may take S4-04 first (smaller story, S effort) so the integration tests have a real `SandboxedPath` from day one.
- **Performance envelope ~80–200 ms per spawn.** ADR-0006 §Tradeoffs row 6 and `phase-arch-design.md §Tradeoffs (consolidated)`. The Adapter's setup cost (seccomp file write, netns creation, pf rules) should fit within this envelope on `ubuntu-24.04` CI runners. No bench in this story; S9-03 lands `bench_workflow_e2e_warm` which includes substrate cost.
- **No `LowLevelAPIWishlist` features.** Resist the urge to add `JailedSubprocessSpec.uid_map`, `gid_map`, `extra_bind_ro_paths`, etc. — every field is in ADR-0006 §Decision or it isn't in the Port. Adding fields here without amending S4-01 + ADR-0006 is silent contract drift; if a need arises, surface it as a follow-up ADR-amendment story (Rule 8 — Read before you write).
