# Story S4-03 — `SandboxExecAdapter` (macOS) + `tooling/sandbox/macos-npm.sb` profile

**Step:** Step 4 — SubprocessJail Port + Bwrap + sandbox-exec + ALLOWED_BINARIES amendment
**Status:** Ready
**Effort:** M
**Depends on:** S4-01 (`SubprocessJail` Protocol, `JailedSubprocessSpec`, `JailedSubprocessResult` variants, `NetworkPolicy`); transitively S1-03
**ADRs honored:** 03-ADR-0006 (`SandboxExecAdapter` is the macOS Adapter; §Decision pins `sandbox-exec -f <generated.sb>` with `deny default` + explicit allows; §Consequences pins the nightly-only CI cadence and the deprecation-flagged-but-accepted-for-Phase-3 framing); 03-ADR-0012 (`sandbox-exec` added to `ALLOWED_BINARIES` — S4-05's data change)

## Context

The macOS sibling of S4-02. The architecture spec (`phase-arch-design.md §Component design C8` — SandboxExecAdapter bullet) commits to `sandbox-exec -f <generated.sb>` with a `deny default` Scheme-syntax profile carrying explicit allow-rules for (a) the jail directory itself and (b) every host in the `NetworkPolicy.RegistryAllowlist`. The same `SubprocessJail` Port S4-02 implements on Linux is implemented here on macOS — operator-laptop developers (most of whom are on Mac) get a working substrate without waiting for Phase 5's Lima / DinD.

**Three macOS-specific framings the implementer must internalize:**

1. **`sandbox-exec` is deprecation-flagged by Apple.** ADR-0006 §Tradeoffs row 3 names this explicitly: "macOS `sandbox-exec` is deprecation-flagged by Apple; Phase 5 substitutes Lima/DinD on macOS. Phase 3 carries the tech-debt explicitly (sized as ~150 LOC of `.sb` profile generation)." The architecture *accepts* this — there is no workaround within Phase 3's scope. The Adapter ships, works on `macOS 14+`, and the deprecation is documented at the symbol.

2. **Nightly-only integration cadence.** ADR-0006 §Consequences row 4: "macOS CI runs as a nightly smoke job (not per-PR) — sandbox-exec adapter is exercised once per day; Linux bwrap path is the per-PR substrate." Phase 3 unit tests run on every PR (mocked substrate); the live `sandbox-exec` invocation runs only on the nightly macOS runner. This story lands the nightly job marker (`@pytest.mark.nightly_macos` or equivalent — verify Phase 2 precedent) and the test gating.

3. **Online-mode-default rejection of security's offline-prefetch flow.** Per ADR-0006 §Context and `critique.md §Issue 2`, the original security-lens design proposed an "online prefetch then offline npm" flow that creates a second, unjailed trust boundary. Both Adapters reject it; this story's `.sb` profile carries network-allow rules for the registry allowlist, not network-deny + offline-cache assumptions.

The `.sb` profile content is implementation-defined per ADR-0006 §Consequences ("macOS `sandbox-exec` profile content (`tooling/sandbox/macos-npm.sb`) is implementation-defined; the architecture only commits to the policy at the YAML/profile level"). This story picks and writes that profile, documents its load-bearing clauses, and ships a generator that produces per-`JailedSubprocessSpec` instantiations (since the jail directory and allowlist hosts vary per call).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C8` — `SandboxExecAdapter` bullet: `sandbox-exec -f <generated.sb>` + `deny default` + explicit allow-rules for jail and registry.
  - `../phase-arch-design.md §Tradeoffs (consolidated)` — substrate-cost row (~50–150 ms per macOS spawn).
  - `../phase-arch-design.md §Physical view` — macOS substrate placement; nightly cadence.
  - `../phase-arch-design.md §Edge case E7` — `.npmrc` redirect → `NetworkDenied(host)`; same threat model as Linux.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md` — §Decision pins the Adapter shape; §Tradeoffs row 3 documents the macOS deprecation acceptance; §Consequences row 3 pins `tooling/sandbox/macos-npm.sb` as the profile path; §Consequences row 4 pins nightly CI cadence.
  - `../ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md` — `sandbox-exec` admitted to `ALLOWED_BINARIES` (S4-05).
- **Source design:**
  - `../final-design.md §Open questions deferred to implementation` — bullet 3: "macOS `sandbox-exec` profile content … S4-03 writes `tooling/sandbox/macos-npm.sb`."
  - `../High-level-impl.md §Step 4 features delivered` — pins `src/codegenie/transforms/sandbox/sandbox_exec.py` and `tooling/sandbox/macos-npm.sb`.
- **Existing code:**
  - `src/codegenie/exec/__init__.py::run_external_cli` — outer chokepoint the Adapter wraps `sandbox-exec` through.
  - `src/codegenie/transforms/sandbox/bwrap.py` (S4-02) — the sibling Adapter; mirror the helper-extraction shape (`_build_*_argv`, `_setup_*`, `_translate_result`) so the two adapters read in parallel.
  - Phase 2 nightly-marker precedent: search `pyproject.toml [tool.pytest.ini_options] markers` for any existing `nightly` / `nightly_macos` marker; if absent, this story declares it.

## Goal

Land:
1. `tooling/sandbox/macos-npm.sb` — the static template `.sb` profile with `deny default`, allow-rules for the jail directory (placeholder `{{JAIL}}` substituted at instantiation), file-read of system frameworks needed for `npm`/`node` to run, and a `(allow network*)` clause whose targets are substituted from the `NetworkPolicy.RegistryAllowlist`.
2. `src/codegenie/transforms/sandbox/sandbox_exec.py` — `SandboxExecAdapter(SubprocessJail)` that:
   - Reads the `.sb` template, substitutes per-spec values, writes to a per-invocation temp file (under `spec.cwd` so it's auto-cleaned).
   - Invokes `sandbox-exec -f <generated.sb> <inner-argv>` through `run_external_cli`.
   - Translates exit signals → `JailedSubprocessResult` variants per the same vocabulary as S4-02.
3. `tests/integration/transforms/test_sandbox_exec_hello_world.py` — macOS-only, **nightly-only** (gated via `@pytest.mark.nightly_macos` and `sys.platform == "darwin"`).
4. `tests/unit/transforms/sandbox/test_sandbox_exec_unit.py` — cross-platform mocked unit tests asserting profile generation + Adapter routing.

`mypy --strict` clean. Online-mode default. `--ignore-scripts` enforced (the env half rides on `NpmEnv.to_env_mapping()` per S4-01; the CLI half is consumer responsibility per S4-05).

## Acceptance criteria

- [ ] **AC-1.** `tooling/sandbox/macos-npm.sb` exists with a `(version 1)` header, `(deny default)`, explicit allow-rules for: (a) `(allow file-read*)` on `/usr`, `/Library/Developer/CommandLineTools`, `/System` (read-only system frameworks needed for `npm`/`node`); (b) `(allow file-read* file-write*)` on the substituted jail directory token; (c) `(allow process-exec)` for `npm` and `node` paths; (d) `(allow network*)` on substituted registry-allowlist hosts only (or `(deny network*)` when `NetworkPolicy.DenyAll`). A unit test (`test_macos_sb_profile_template_well_formed`) reads the file and asserts the `(version 1)`, `(deny default)`, and `{{JAIL}}` / `{{ALLOWLIST_HOSTS}}` substitution tokens are all present.
- [ ] **AC-2.** `src/codegenie/transforms/sandbox/sandbox_exec.py` exists and exports `SandboxExecAdapter`. A unit test asserts the Adapter conforms to `SubprocessJail` (Protocol check; structural mypy verification).
- [ ] **AC-3.** `SandboxExecAdapter` generates a per-invocation `.sb` file by reading the template and substituting `{{JAIL}}` → `str(spec.cwd.absolute)` and `{{ALLOWLIST_HOSTS}}` → the materialized allow-rules. A unit test (`test_generated_sb_substitution`) passes a `spec` with `cwd=<tmp_path>` and `network=RegistryAllowlist(hosts=frozenset({RegistryUrl("https://registry.npmjs.org")}))`, captures the generated `.sb` text (via monkeypatching the file-write call), and asserts:
  - `{{JAIL}}` and `{{ALLOWLIST_HOSTS}}` tokens are absent from the output (every placeholder substituted).
  - The string `str(tmp_path)` appears in the output (jail substituted).
  - `registry.npmjs.org` appears in the `(allow network*)` clause.
  - `(deny default)` is present and is the first non-version line.
- [ ] **AC-4.** Generated `.sb` for `NetworkPolicy.DenyAll` contains `(deny network*)` (or no `(allow network*)` clause at all — either implementation is fine; the test pins the observable: zero allowed hosts). A unit test passes `network=DenyAll()` and asserts no `allow network` clause references any external host.
- [ ] **AC-5.** `SandboxExecAdapter.run` invokes `run_external_cli` with argv prefix `["sandbox-exec", "-f", <generated-sb-path>, *spec.cmd]`. A unit test mocks `run_external_cli` and asserts the argv prefix.
- [ ] **AC-6.** `SandboxExecAdapter` NEVER calls `subprocess.run`, `asyncio.create_subprocess_exec`, `os.system`, `os.popen`, or uses `shell=True`. A grep test reads the module source and asserts none of those patterns appear. (Mirrors S4-02 AC-4 — single chokepoint discipline.)
- [ ] **AC-7.** Result-variant translation parametric — same shape as S4-02 AC-5; cross-platform unit test mocks the underlying `run_external_cli` outcome and asserts each `JailedSubprocessResult` variant is reachable: `Completed` on clean exit; `TimedOut` when the deadline trips; `NetworkDenied(host=...)` when sandbox-exec denies a connect (sandbox-exec writes a recognizable signature to stderr — the Adapter parses it).
- [ ] **AC-8.** `NpmEnv.to_env_mapping()` is passed to `run_external_cli`'s `env_extra` — the `npm_config_ignore_scripts="true"` defense rides through verbatim. Mirror of S4-02 AC-10. Unit test asserts the captured `env_extra` contains the key.
- [ ] **AC-9.** `spec.cmd` is preserved verbatim including any `--ignore-scripts` CLI token. Mirror of S4-02 AC-11.
- [ ] **AC-10.** **Nightly-only macOS integration test.** `tests/integration/transforms/test_sandbox_exec_hello_world.py` is marked `@pytest.mark.nightly_macos` (the marker is declared in this story if Phase 2 has no precedent; otherwise reuse). Test body:
  - Skip if `sys.platform != "darwin"`.
  - Skip if `shutil.which("sandbox-exec") is None` — sandbox-exec is built into macOS, so this skip is paranoia; document in the skip message that this should never trigger on a real Mac runner.
  - Run `SandboxExecAdapter().run(spec)` with `spec.cmd = ("/bin/echo", "hello")`, `network=DenyAll()`, and assert `Completed(exit_code=0)`.
  - This test does NOT run per-PR; it runs on the nightly macOS CI job. The pytest marker registration discipline pins this.
- [ ] **AC-11.** **Nightly-only network-policy live test.** `tests/integration/transforms/test_sandbox_exec_network_policy.py` (same nightly-macOS gating) runs two cases:
  - `RegistryAllowlist(hosts=frozenset({RegistryUrl("https://registry.npmjs.org")}))` + `cmd=("/usr/bin/curl", "--max-time", "5", "-o", "/dev/null", "-s", "https://registry.npmjs.org/")` → `Completed`.
  - Same allowlist + `cmd=("/usr/bin/curl", "--max-time", "5", "https://github.com/")` → `NetworkDenied(host=...)`.
  - These are the macOS mirror of S4-02 AC-9.
- [ ] **AC-12.** `pyproject.toml [tool.pytest.ini_options] markers` declares `nightly_macos` (or reuses an existing marker if Phase 2 declared one — verify before adding). A pytest meta-test asserts the marker is registered (running `pytest --collect-only -m nightly_macos` exits 0 with the two AC-10/AC-11 tests collected).
- [ ] **AC-13.** `mypy --strict src/codegenie/transforms/sandbox/sandbox_exec.py tests/unit/transforms/sandbox/test_sandbox_exec_unit.py` clean. `ruff check` + `ruff format --check` clean on touched files.
- [ ] **AC-14.** `make lint-imports` Phase 3 contract (S1-05): no LLM SDK appears in `src/codegenie/transforms/sandbox/sandbox_exec.py`'s import closure.
- [ ] **AC-15.** Profile-template safety regression: a unit test (`test_sb_template_does_not_allow_default_writes`) asserts the literal substring `(allow default)` does NOT appear in `tooling/sandbox/macos-npm.sb`, and `(deny default)` does appear exactly once. Catches the regression where a maintainer flips the polarity by accident — `deny default` is the structural backbone of the profile per ADR-0006.

## Implementation outline

1. Write `tooling/sandbox/macos-npm.sb` template (~80–150 lines). Approximate skeleton (Scheme-syntax Apple sandbox profile language):
   ```
   (version 1)
   (deny default)

   ;; Read system frameworks node/npm need to start
   (allow file-read*
     (subpath "/usr/lib")
     (subpath "/usr/bin")
     (subpath "/usr/local/bin")
     (subpath "/Library/Developer/CommandLineTools")
     (subpath "/System/Library/Frameworks"))

   ;; Read + write inside the jail
   (allow file-read* file-write*
     (subpath "{{JAIL}}"))

   ;; tmpfs-equivalent on macOS — /tmp is per-user
   (allow file-read* file-write*
     (subpath "/private/tmp"))

   ;; Process invocation (npm shells out to node)
   (allow process-exec
     (subpath "/usr/local/bin")
     (subpath "/usr/bin"))

   ;; Network policy — substituted per spec
   {{ALLOWLIST_HOSTS}}

   ;; Required syscall surface — minimal
   (allow mach-lookup)
   (allow sysctl-read)
   (allow process-fork)
   (allow signal (target self))
   ```
2. Create `src/codegenie/transforms/sandbox/sandbox_exec.py`. Imports: `from __future__ import annotations`, `pathlib.Path`, `tempfile`, `shutil`, `sys`, `codegenie.exec.run_external_cli`, `codegenie.transforms.sandbox_jail.{...}`.
3. Define `class SandboxExecAdapter:` with `async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult`.
4. Helper `_render_profile(template: str, spec: JailedSubprocessSpec) -> str`:
   - Read `tooling/sandbox/macos-npm.sb` once at adapter init (module-level `_TEMPLATE = Path("tooling/sandbox/macos-npm.sb").read_text()` — cache it; the file is content-pinned in the repo).
   - Substitute `{{JAIL}}` → `str(spec.cwd.absolute)`.
   - Substitute `{{ALLOWLIST_HOSTS}}` → rendered Scheme clauses based on `spec.network`:
     - `DenyAll` → empty string (the `deny default` covers it).
     - `RegistryAllowlist(hosts)` → for each `host` in `hosts`, emit `(allow network* (remote tcp "<hostname>:443"))` (parse hostname out of the `RegistryUrl`).
5. In `run`:
   - Render the profile, write to `<spec.cwd>/.sandbox-exec.sb` (per-invocation file; cleaned up by the caller via `tmp_path`).
   - Compose argv: `["sandbox-exec", "-f", <profile-path>, *spec.cmd]`.
   - Build env: `spec.env.to_env_mapping()`.
   - `await run_external_cli(argv, cwd=spec.cwd.absolute, timeout_s=spec.time_budget_s, env_extra=env, allowlisted_egress=frozenset(...))`.
   - Translate the outcome to `JailedSubprocessResult` — sandbox-exec writes denial reasons to stderr; parse for `Sandbox: ... deny network` and extract the host into `NetworkDenied(host=...)`.
6. Register `nightly_macos` pytest marker in `pyproject.toml` if not present.
7. Write all unit tests (AC-1..AC-9, AC-12, AC-15).
8. Write the nightly-only integration tests (AC-10, AC-11).
9. Run `mypy --strict`, `ruff`, `pytest tests/unit/transforms/sandbox/test_sandbox_exec_unit.py -v`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

`tests/unit/transforms/sandbox/test_sandbox_exec_unit.py` (cross-platform; module-import + profile-generation tests):

```python
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from codegenie.transforms.sandbox.sandbox_exec import (  # RED
    SandboxExecAdapter, _render_profile,
)
from codegenie.transforms.sandbox_jail import (
    Completed, DenyAll, JailedSubprocessSpec, NetworkDenied, NpmEnv,
    RegistryAllowlist, SubprocessJail, TimedOut,
)
from codegenie.types.identifiers import RegistryUrl


# AC-1: template file exists and contains the load-bearing tokens
def test_macos_sb_profile_template_well_formed() -> None:
    profile = Path("tooling/sandbox/macos-npm.sb")
    assert profile.exists(), "tooling/sandbox/macos-npm.sb missing — AC-1"
    text = profile.read_text()
    assert "(version 1)" in text
    assert "(deny default)" in text
    assert "{{JAIL}}" in text
    assert "{{ALLOWLIST_HOSTS}}" in text


# AC-15: polarity regression
def test_sb_template_does_not_allow_default_writes() -> None:
    text = Path("tooling/sandbox/macos-npm.sb").read_text()
    assert "(allow default)" not in text, "polarity flip — (allow default) MUST NOT appear"
    assert text.count("(deny default)") == 1, "(deny default) must appear exactly once"


# AC-2
def test_sandbox_exec_adapter_conforms() -> None:
    adapter: SubprocessJail = SandboxExecAdapter()
    assert hasattr(adapter, "run")


# AC-3: substitution
def test_generated_sb_substitution(tmp_path: Path) -> None:
    from tests.unit.transforms._fakes import FakeSandboxedPath
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"),
        cwd=FakeSandboxedPath(str(tmp_path)),  # type: ignore[arg-type]
        env=NpmEnv(),
        network=RegistryAllowlist(hosts=frozenset({
            RegistryUrl("https://registry.npmjs.org"),
        })),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    template = Path("tooling/sandbox/macos-npm.sb").read_text()
    rendered = _render_profile(template, spec)
    assert "{{JAIL}}" not in rendered
    assert "{{ALLOWLIST_HOSTS}}" not in rendered
    assert str(tmp_path) in rendered
    assert "registry.npmjs.org" in rendered
    assert "(deny default)" in rendered


# AC-4
def test_generated_sb_deny_all_has_no_allow_network(tmp_path: Path) -> None:
    from tests.unit.transforms._fakes import FakeSandboxedPath
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"),
        cwd=FakeSandboxedPath(str(tmp_path)),  # type: ignore[arg-type]
        env=NpmEnv(),
        network=DenyAll(),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    template = Path("tooling/sandbox/macos-npm.sb").read_text()
    rendered = _render_profile(template, spec)
    # No allow-network rule references any external host
    import re
    allow_net = re.findall(r"\(allow network[^\)]*remote tcp[^\)]+\)", rendered)
    assert allow_net == [], f"DenyAll must not yield any allow-network rules; got {allow_net!r}"


# AC-5: argv prefix
async def test_argv_prefix_matches_adr_0006(monkeypatch, tmp_path) -> None:
    from tests.unit.transforms._fakes import FakeSandboxedPath
    captured = {}
    async def fake(*a, **k):
        captured["argv"] = a[0] if a else k.get("argv")
        return type("R", (), {"exit_code": 0, "stdout": b"", "stderr": b"", "wall_s": 0.0})()
    monkeypatch.setattr(
        "codegenie.transforms.sandbox.sandbox_exec.run_external_cli", fake,
    )
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"),
        cwd=FakeSandboxedPath(str(tmp_path)),  # type: ignore[arg-type]
        env=NpmEnv(), network=DenyAll(),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    await SandboxExecAdapter().run(spec)
    argv = captured["argv"]
    assert argv[0] == "sandbox-exec"
    assert argv[1] == "-f"
    # argv[2] is the generated .sb path; argv[3:] is spec.cmd verbatim
    assert tuple(argv[3:]) == spec.cmd


# AC-6
def test_module_has_no_direct_subprocess() -> None:
    src = Path("src/codegenie/transforms/sandbox/sandbox_exec.py").read_text()
    for bad in ("subprocess.run", "create_subprocess_exec", "os.system", "os.popen", "shell=True"):
        assert bad not in src, f"forbidden subprocess pattern: {bad!r}"


# AC-7: result-variant translation
@pytest.mark.parametrize(
    "fake_outcome, expected",
    [
        ("clean_zero", Completed),
        ("timeout", TimedOut),
        ("network_denied_github", NetworkDenied),
    ],
)
async def test_result_variant_translation(
    fake_outcome: str, expected: type, monkeypatch, tmp_path,
) -> None:
    from codegenie.transforms.sandbox._fakes_for_tests import inject_fake_outcome
    inject_fake_outcome(monkeypatch, fake_outcome, adapter="sandbox_exec")
    from tests.unit.transforms._fakes import FakeSandboxedPath
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"),
        cwd=FakeSandboxedPath(str(tmp_path)),  # type: ignore[arg-type]
        env=NpmEnv(), network=DenyAll(),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    result = await SandboxExecAdapter().run(spec)
    assert isinstance(result, expected)


# AC-8: env mapping
async def test_env_mapping_reaches_run_external_cli(monkeypatch, tmp_path) -> None:
    from tests.unit.transforms._fakes import FakeSandboxedPath
    captured = {}
    async def fake(*a, **k):
        captured["env_extra"] = k.get("env_extra", {})
        return type("R", (), {"exit_code": 0, "stdout": b"", "stderr": b"", "wall_s": 0.0})()
    monkeypatch.setattr("codegenie.transforms.sandbox.sandbox_exec.run_external_cli", fake)
    spec = JailedSubprocessSpec(
        cmd=("npm", "--version"),
        cwd=FakeSandboxedPath(str(tmp_path)),  # type: ignore[arg-type]
        env=NpmEnv(), network=DenyAll(),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    await SandboxExecAdapter().run(spec)
    assert captured["env_extra"].get("npm_config_ignore_scripts") == "true"


# AC-9: cmd preserved
async def test_cmd_preserved_verbatim(monkeypatch, tmp_path) -> None:
    from tests.unit.transforms._fakes import FakeSandboxedPath
    captured = {}
    async def fake(*a, **k):
        captured["argv"] = a[0] if a else k.get("argv")
        return type("R", (), {"exit_code": 0, "stdout": b"", "stderr": b"", "wall_s": 0.0})()
    monkeypatch.setattr("codegenie.transforms.sandbox.sandbox_exec.run_external_cli", fake)
    cmd = ("npm", "install", "--ignore-scripts", "--package-lock-only", "--no-audit")
    spec = JailedSubprocessSpec(
        cmd=cmd,
        cwd=FakeSandboxedPath(str(tmp_path)),  # type: ignore[arg-type]
        env=NpmEnv(), network=DenyAll(),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    await SandboxExecAdapter().run(spec)
    tail = captured["argv"][-len(cmd):]
    assert tuple(tail) == cmd


# AC-12: nightly_macos marker registered
def test_nightly_macos_marker_registered() -> None:
    import subprocess
    out = subprocess.run(
        ["pytest", "--markers"], capture_output=True, text=True, check=True,
    ).stdout
    assert "nightly_macos" in out
```

`tests/integration/transforms/test_sandbox_exec_hello_world.py` (AC-10):

```python
from __future__ import annotations
import shutil
import sys

import pytest

from codegenie.transforms.sandbox.sandbox_exec import SandboxExecAdapter
from codegenie.transforms.sandbox_jail import (
    Completed, DenyAll, JailedSubprocessSpec, NpmEnv,
)


@pytest.mark.nightly_macos
@pytest.mark.asyncio
async def test_sandbox_exec_hello_world(tmp_path) -> None:
    if sys.platform != "darwin":
        pytest.skip("macOS substrate; Linux uses bwrap (S4-02)")
    if shutil.which("sandbox-exec") is None:
        pytest.skip("sandbox-exec missing — built into macOS so this should never trigger")
    from codegenie.plugins.sandbox_path import SandboxedPath  # S4-04
    sp = SandboxedPath.create(tmp_path, ".").unwrap()
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hello"),
        cwd=sp, env=NpmEnv(), network=DenyAll(),
        time_budget_s=5.0, memory_mib=64, pids_max=32,
    )
    result = await SandboxExecAdapter().run(spec)
    assert isinstance(result, Completed)
    assert result.exit_code == 0
```

Run — all RED (module + template missing). Commit.

### Green — make it pass

1. Write `tooling/sandbox/macos-npm.sb`. Run AC-1 + AC-15 — green.
2. Implement `_render_profile`. Run AC-3 + AC-4 — green.
3. Implement `SandboxExecAdapter.run` with argv composition + run_external_cli call + outcome translation. Run AC-2, AC-5..AC-9 — green.
4. Register `nightly_macos` marker in `pyproject.toml`. Run AC-12 — green.
5. On a macOS dev box (or wait for nightly), run AC-10 + AC-11 — green.

### Refactor — clean up

- Mirror S4-02's helper extraction: `_build_argv`, `_render_profile`, `_translate_result` — so the two adapters read in parallel and the reviewer can verify the Port is implemented identically on both substrates.
- Cache the template read at module load: `_TEMPLATE = Path(__file__).parent.parent.parent.parent / "tooling" / "sandbox" / "macos-npm.sb"` (compute the repo root once; don't re-read per spec).
- Module docstring cites ADR-0006 §Decision + §Tradeoffs row 3 (deprecation acceptance).
- `ruff format`, `mypy --strict`, full unit suite green.

## Files to touch

| Path | Why |
|---|---|
| `tooling/sandbox/macos-npm.sb` | New: `.sb` profile template with `(deny default)`, system-framework reads, jail bind, allowlist-host network rules. Approximately 80–150 lines per ADR-0006 §Tradeoffs row 3 sizing. |
| `src/codegenie/transforms/sandbox/sandbox_exec.py` | New: `SandboxExecAdapter(SubprocessJail)` — template render + `sandbox-exec` invocation via `run_external_cli` + result-variant translator (AC-2..AC-9). |
| `pyproject.toml` | Add `nightly_macos` marker under `[tool.pytest.ini_options] markers` if not already present (AC-12). |
| `tests/unit/transforms/sandbox/test_sandbox_exec_unit.py` | New: AC-1..AC-9, AC-12, AC-15. Cross-platform; mocks the substrate. |
| `tests/integration/transforms/test_sandbox_exec_hello_world.py` | New: AC-10. Nightly + macOS-only. |
| `tests/integration/transforms/test_sandbox_exec_network_policy.py` | New: AC-11. Nightly + macOS-only. |

## Out of scope

- **`BwrapAdapter`** — S4-02.
- **`SubprocessJail` Protocol + `JailedSubprocessSpec` + variants** — S4-01.
- **`SandboxedPath` real implementation** — S4-04 (`FakeSandboxedPath` shim used in unit tests).
- **`ALLOWED_BINARIES` amendment for `sandbox-exec` / `npm` / `curl`** — S4-05.
- **Lima / DinD substitution** — Phase 5 (`05-ADR-0004`). Documented at the symbol; not implemented.
- **`.sb` profile content evolution for OpenRewrite JVM invocation** — Phase 7 (`OpenRewriteRecipeEngine` activated). This story's profile covers `npm` + `node` only; the template's `process-exec` rules add `java` when Phase 7 needs it.
- **Per-PR macOS CI runner cost optimization** — explicitly out per ADR-0006 §Consequences row 4. Nightly cadence is the decision.
- **Full postinstall-canary adversarial test on macOS** — S8-04 (`@pytest.mark.phase03_adv`). The nightly integration tests here only prove the substrate works; the adversarial portfolio runs on the full fixture set later.

## Notes for the implementer

- **Deprecation acceptance is real.** ADR-0006 §Tradeoffs row 3 says: "macOS `sandbox-exec` is deprecation-flagged by Apple; Phase 5 substitutes Lima/DinD on macOS. Phase 3 carries the tech-debt explicitly (sized as ~150 LOC of `.sb` profile generation)." Resist any urge to switch to a "more modern" macOS sandbox API (App Sandbox, com.apple.developer.sandbox.* entitlements) — those are GUI-app-tier; Phase 5 owns the proper substitution. Write the `.sb` profile, document the deprecation in the module docstring, move on.
- **`.sb` profile is Scheme-syntax.** Apple's profile language is a small Scheme dialect documented in `man sandbox-exec` and Apple's archived "App Sandbox Design Guide." Allowed forms: `(version 1)`, `(deny default)`, `(allow <action> <args>)`, `(deny <action> <args>)`. Common actions: `file-read*`, `file-write*`, `network*`, `process-exec`, `mach-lookup`, `sysctl-read`. Target forms: `(subpath "/path")`, `(remote tcp "host:port")`. Get the syntax right or the substrate refuses to start (sandbox-exec exits non-zero with a parse error on stderr; the Adapter translates this to a sentinel `Completed(exit_code=...)` since it's a substrate-setup failure, not a child failure — surface it loudly in the test output).
- **Nightly marker convention.** Phase 2 may or may not have an existing `nightly_macos` / `nightly` marker — check `pyproject.toml [tool.pytest.ini_options] markers` and `grep -r "@pytest.mark.nightly" tests/` before declaring a new one. If Phase 2 uses a different name (`nightly`, `macos_nightly`), follow that precedent (Rule 11). The AC-12 test pins whatever marker is chosen.
- **Substrate cost ~50–150 ms per spawn.** Per ADR-0006 §Tradeoffs and `phase-arch-design.md §Tradeoffs (consolidated)`. The template render + file write should add <10 ms. No bench in this story.
- **No second trust boundary.** Per ADR-0006 §Context and `critique.md §Issue 2`: do NOT add an "offline prefetch" mode. Online-mode-default with `RegistryAllowlist` is the architecture. The `.sb` profile has `(allow network*)` clauses for the allowed registry hosts; the deny-by-default backbone keeps everything else closed.
- **NetworkDenied(host) extraction from stderr.** sandbox-exec writes denial messages to stderr in a recognizable format: `Sandbox: <process>(<pid>) deny(1) network-outbound <host>:<port>`. The Adapter's result-translator parses the latest such line and extracts the host into `NetworkDenied(host=...)`. If multiple denies occurred, the first is canonical (the connect that triggered the failure). Test fixture for AC-11 should produce exactly one denial for cleanness.
- **`/usr/bin/curl` is preinstalled on macOS.** Use it in AC-11 directly. If a CI matrix has a stripped runner, fall back to `node -e "fetch(...)"` (node is already in `ALLOWED_BINARIES`).
- **Mirror S4-02 helper shapes.** The two adapters should read in parallel — same helper names (`_render_*` / `_build_*_argv` / `_translate_result`), same control-flow shape. A reviewer comparing the two files side-by-side should see the only differences are substrate-specific. This is the Hexagonal-Port pattern's payoff (ADR-0006 §Pattern fit) — preserve it stylistically too.
- **Forward-string `SandboxedPath`** — same discipline as S4-02 (Notes-for-implementer bullet 2 there). The unit tests use `FakeSandboxedPath`; the integration tests require S4-04. If S4-04 lands first (its dependency arrow on the manifest DAG suggests it can), use the real type from day one in the integration tests.
- **S4-05's `--ignore-scripts` static fence will close on the CLI half.** This Adapter does not enforce the CLI `--ignore-scripts` token; per ADR-0006 the env half is structural (S4-01 `NpmEnv`) and the CLI half is the consumer's responsibility (S5-02 `NpmLockfileRecipeEngine`). S4-05 adds a static fence test asserting every npm-related call site has `--ignore-scripts` literally in `cmd`. Don't preempt that fence here.
