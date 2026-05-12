# Story S1-02 — `run_in_sandbox` network + scoped-egress + ro_bind extension

**Step:** Step 1 — Plant sandbox extension, tool wrappers, tool-digest pin manifest, and the four Phase-0/1 in-place edits
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0003

## Context

Phase 2 is the first phase that executes foreign code on hostile input at scale: `scip-typescript`, `semgrep`, `gitleaks`, `syft`, `grype`, `docker build`, and tree-sitter grammars all load attacker-controlled bytes. The security lens proposed a four-strategy `SandboxStrategy` interface plus a local registry mirror plus a built `codegenie/probe-runtime` image; the critic dismantled that as scope creep that forward-declares Phase 5 and Phase 14 infrastructure. The synthesis chose to extend Phase 1's existing `run_in_sandbox` chokepoint in place with a tighter Phase 2 profile — same call site, same probe-side contract, new keyword args for `network`, `scoped_egress_hosts`, `ro_bind`.

This is one of the **four ADR-gated in-place edits** Phase 2 makes to Phase 0/1 code (the others are `ALLOWED_BINARIES` in S1-03, `output_sanitizer.py` in S1-09, `coordinator.py` + `probes/base.py` in S1-11). Every other Phase 2 file is new. The signature must remain backward compatible for every existing caller — default `network="none"` matches Phase 1's behavior exactly.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #2 (tools/ wrappers)` — every wrapper routes through `run_in_sandbox`, never `subprocess.run`.
  - `../phase-arch-design.md §"Goals" #8` — "subprocess sandbox profile (Linux + macOS parity)" goal statement.
  - `../phase-arch-design.md §"Edge cases"` — `network="none"` default; `network="scoped"` allowlist enforced per-call; macOS best-effort limitation.
- **Phase ADRs:**
  - `../ADRs/0003-subprocess-sandbox-profile-extension.md` — ADR-0003 — full decision; `network: Literal["none","scoped"] = "none"`, `scoped_egress_hosts: Sequence[str] = ()`, `ro_bind: Sequence[Path] = ()`; extended `--unsetenv` list; `bwrap --unshare-net` on Linux + `sandbox-exec (deny network*)` on macOS; no new `SandboxStrategy`.
- **Production ADRs:**
  - `../../../production/adrs/0019-sandbox-execution-stack.md` — the deferred microVM question Phase 5 owns; this story preserves the chokepoint so the future swap is one-branch.
- **Source design:**
  - `../final-design.md §"Components" #2 Subprocess sandbox profile extension` — interface spec.
  - `../final-design.md §"Conflict-resolution table" D2` — the resolution rejecting `SandboxStrategy`.
- **Existing code:**
  - `src/codegenie/exec.py` (Phase 0 + Phase 1) — `run_in_sandbox`, `ALLOWED_BINARIES`, `--unsetenv` list. Extend in place; do not rewrite.
  - `src/codegenie/errors.py` — `SandboxLaunchError` added by S1-01.
  - `src/codegenie/logging.py` — `PROBE_SANDBOX_NETWORK_EGRESS_ATTEMPTED`, `FIELD_SANDBOX_NETWORK` added by S1-01.

## Goal

Extend `src/codegenie/exec.run_in_sandbox` with `network`, `scoped_egress_hosts`, and `ro_bind` keyword arguments and a tighter credential-strip list, preserving the existing two-arg call shape for every Phase 0/1 caller, so Phase 2 wrappers can declare per-call network policy at the chokepoint.

## Acceptance criteria

- [ ] `src/codegenie/exec.run_in_sandbox` accepts `network: Literal["none","scoped"] = "none"`, `scoped_egress_hosts: Sequence[str] = ()`, `ro_bind: Sequence[Path] = ()` as keyword-only parameters; the existing positional/keyword arguments are unchanged in order, name, and default.
- [ ] On Linux, `network="none"` invocation passes `--unshare-net` to `bwrap`; `network="scoped"` builds an allowlist constraint over `scoped_egress_hosts` (helper `with_scoped_network(hosts)` or equivalent inline construction).
- [ ] On macOS, `network="none"` invocation uses the `sandbox-exec` profile at `src/codegenie/exec/sandbox_exec.profile` with `(deny network*)`; module-level documentation states this is **best-effort** and the CLI startup banner surfaces the limitation.
- [ ] The `--unsetenv` list extends to include `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `CHAINGUARD_TOKEN`, `GITHUB_TOKEN`, plus `AWS_*`, `GCP_*`, `AZURE_*` prefix matches; additionally a regex stripper removes any env var whose name matches `(?i).*(token|secret|password|key|api_key).*`.
- [ ] Each `ro_bind` path is bound read-only into the sandbox at the same path (or under a documented mount root); missing paths raise `SandboxLaunchError`.
- [ ] When `network="scoped"` is requested with an empty `scoped_egress_hosts`, the call raises `SandboxLaunchError(detail="scoped network requires at least one host")`.
- [ ] When a `network="scoped"` egress is *attempted* by the child process, the wrapper emits `probe.sandbox.network_egress_attempted` with `sandbox_network: "scoped"`, `tool_name: <argv[0]>`, `hosts: scoped_egress_hosts` fields (one event per call regardless of whether the egress succeeded).
- [ ] Linux failure to launch `bwrap` (binary missing or returns non-zero on the setup phase before exec) raises `SandboxLaunchError`; existing Phase 1 callers see the same exception they saw before this story.
- [ ] `tests/unit/exec/test_run_in_sandbox_network.py` — five tests: `network="none"` default; `network="scoped"` with allowlist; `bwrap --unshare-net` argv assertion (Linux); `sandbox-exec` profile path assertion (macOS); `network="scoped"` with empty hosts raises `SandboxLaunchError`.
- [ ] `tests/unit/exec/test_credential_strip.py` — every name in the documented list plus a regex sampler (`MY_API_KEY`, `secret_value`, `db_password`) is stripped from the child env; an unrelated `PATH` survives.
- [ ] Phase 0/1 callers in `tests/unit/exec/test_run_in_sandbox.py` continue to pass with no edits.
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write the failing tests first under `tests/unit/exec/test_run_in_sandbox_network.py` and `tests/unit/exec/test_credential_strip.py`. Use `unittest.mock` to patch `subprocess` and capture argv.
2. Extend `run_in_sandbox` signature with the three new keyword-only parameters (`*` separator preserved; new params after the existing trailing `*` block).
3. Linux branch: append `--unshare-net` when `network="none"`; for `network="scoped"`, construct the bwrap network namespace + allowlist (per `phase-arch-design.md` "Component design" #2). Document that scoped enforcement is implemented via the `with_scoped_network` helper which constructs the right argv tail.
4. macOS branch: load the `sandbox-exec.profile` from `src/codegenie/exec/sandbox_exec.profile` (commit the file); inject `(deny network*)` when `network="none"`; for `network="scoped"`, document the best-effort posture and emit the egress-attempted event.
5. `ro_bind`: for each path, append `--ro-bind <abs> <abs>` to the bwrap argv (Linux) or add to the sandbox-exec profile template (macOS). Validate existence; raise `SandboxLaunchError` on missing.
6. Credential strip: extend the `--unsetenv` literal list with the documented names; add the regex stripper that walks `os.environ` keys and emits `--unsetenv <name>` for each match. Compile the regex once at module scope (`Final[re.Pattern]`).
7. Empty-hosts guard: `if network == "scoped" and not scoped_egress_hosts: raise SandboxLaunchError(detail="scoped network requires at least one host")`.
8. Emit `probe.sandbox.network_egress_attempted` event from the wrapper at call time when `network="scoped"`; the field set is documented above.
9. Commit `src/codegenie/exec/sandbox_exec.profile` if not already shipped from Phase 1.
10. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/exec.py tests/unit/exec/`, `pytest tests/unit/exec/`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/exec/test_run_in_sandbox_network.py`.

```python
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import codegenie.errors as e
from codegenie.exec import run_in_sandbox


@pytest.mark.skipif(sys.platform != "linux", reason="Linux-specific bwrap argv assertion")
def test_network_none_default_passes_unshare_net_on_linux():
    # arrange: spy on subprocess.run
    with patch("codegenie.exec._spawn") as spawn:
        spawn.return_value = ("", "", 0)
        # act
        run_in_sandbox(["echo", "hi"], allowlist=["echo"], env={}, timeout_s=1.0, cwd=Path("/tmp"))
    # assert: --unshare-net present in bwrap argv
    argv = spawn.call_args.args[0]
    assert "--unshare-net" in argv


def test_scoped_requires_hosts():
    with pytest.raises(e.SandboxLaunchError) as exc:
        run_in_sandbox(
            ["grype", "db", "update"],
            allowlist=["grype"], env={}, timeout_s=1.0, cwd=Path("/tmp"),
            network="scoped", scoped_egress_hosts=(),
        )
    assert "scoped" in exc.value.detail


def test_ro_bind_missing_path_raises():
    with pytest.raises(e.SandboxLaunchError):
        run_in_sandbox(
            ["scip-typescript", "--version"],
            allowlist=["scip-typescript"], env={}, timeout_s=1.0, cwd=Path("/tmp"),
            ro_bind=(Path("/this/does/not/exist"),),
        )
```

```python
# tests/unit/exec/test_credential_strip.py
from pathlib import Path
from unittest.mock import patch

from codegenie.exec import run_in_sandbox


def test_credential_env_stripped():
    parent_env = {
        "PATH": "/usr/bin",
        "OPENAI_API_KEY": "sk-x",
        "ANTHROPIC_API_KEY": "sk-y",
        "MY_API_KEY": "z",
        "DB_PASSWORD": "p",
        "AWS_ACCESS_KEY_ID": "a",
    }
    with patch("codegenie.exec._spawn") as spawn:
        spawn.return_value = ("", "", 0)
        run_in_sandbox(["echo", "hi"], allowlist=["echo"], env=parent_env,
                       timeout_s=1.0, cwd=Path("/tmp"))
    argv = spawn.call_args.args[0]
    # every credential-shaped name appears as --unsetenv in the bwrap argv
    for name in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "MY_API_KEY", "DB_PASSWORD", "AWS_ACCESS_KEY_ID"]:
        assert f"--unsetenv" in argv and name in argv
    # PATH survives
    assert "PATH" not in [argv[i+1] for i, v in enumerate(argv) if v == "--unsetenv"]
```

Run; confirm test failures because the parameters / behavior don't exist yet. Commit as red marker.

### Green — make it pass

Extend `run_in_sandbox` signature in `src/codegenie/exec.py`:

```
def run_in_sandbox(
    argv, *,
    allowlist, env, timeout_s, cwd,
    network: Literal["none", "scoped"] = "none",
    scoped_egress_hosts: Sequence[str] = (),
    ro_bind: Sequence[Path] = (),
) -> ProcessResult: ...
```

Inside, branch on `sys.platform`. On Linux, build `bwrap` argv as before, append `--unshare-net` for `none`, scoped argv for `scoped`, `--ro-bind` for each `ro_bind`, and `--unsetenv NAME` for each stripped env name (literal + regex match). On macOS, load and template the `sandbox-exec.profile`.

The `_spawn` indirection is the seam unit tests patch.

### Refactor — clean up

- Move the credential-strip list to a module-level `Final[tuple[str, ...]]` and the regex to a `Final[re.Pattern]`.
- Extract Linux argv construction into a small `_build_bwrap_argv(...)` helper for readability; do not over-decompose.
- Document the macOS limitation at the top of the module docstring (Rule 12 — fail loud, but the right "loud" here is the CLI banner from Phase 0).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/exec.py` | Extend `run_in_sandbox`; extend `--unsetenv`; add regex stripper |
| `src/codegenie/exec/sandbox_exec.profile` | Commit profile if not already present |
| `tests/unit/exec/test_run_in_sandbox_network.py` | New — five tests |
| `tests/unit/exec/test_credential_strip.py` | New — extended env-strip coverage |

## Out of scope

- **Adding the six new binaries to `ALLOWED_BINARIES`** — handled by S1-03.
- **The CLI startup banner that surfaces the macOS limitation** — extended in S1-08 alongside the digest verifier wiring; this story commits the documented behavior in the docstring.
- **Tool wrappers consuming the new args** — handled by S1-05, S1-06, S1-07.
- **Per-tool scoped-egress allowlists (`grype-vuln-db-host`, registry-host)** — those values live in the wrappers (S1-05 for grype, S1-06 for docker); this story only validates the mechanism.
- **`SandboxStrategy` interface or rootless Podman** — explicitly rejected by ADR-0003.

## Notes for the implementer

- The default `network="none"` must produce **byte-identical** bwrap argv to Phase 1's existing default for the `argv` portion that Phase 1 controlled — otherwise existing Phase 1 unit tests break and the "extension by addition" claim of this ADR fails. If your refactor changes argv ordering for the default case, restructure to preserve it.
- `bwrap --unshare-net` is the Linux mechanism; `sandbox-exec`'s `(deny network*)` is **best-effort** on macOS (system calls go through the kernel; some IPC paths can still leak). Document the limitation in the module docstring and in the CLI banner; do not pretend macOS parity is exact.
- The regex stripper `(?i).*(token|secret|password|key|api_key).*` is broad on purpose. The cost is a few extra `--unsetenv` flags for benign env vars (`KEYBINDINGS`, `KEYCHAIN_PATH`). The benefit is that credential-shaped names that operators invent later are still stripped. Per Rule 12 (Fail loud), over-stripping is the safe direction.
- `scoped_egress_hosts` must be passed as a `Sequence[str]` (not `list`) so mypy enforces immutability at the type level. Phase 1 ADR-0008 made this convention for `parsers/` arguments; carry it forward.
- `ro_bind` paths must be absolute. Add a runtime check (`if not path.is_absolute(): raise SandboxLaunchError(...)`) — relative paths inside a sandbox are confusing and likely a bug.
- The `probe.sandbox.network_egress_attempted` event fires on **any** scoped call, not just on actual egress. That keeps the event meaningful: "the wrapper requested scoped network for this call." Phase 14's observability stack can correlate with downstream `grype db update` / `docker build` audit entries to detect actual egress.
- Do **not** introduce a `SandboxStrategy` class even as a "future-proofing" stub. ADR-0003 is explicit: the chokepoint is the abstraction. A stub class would invite future contributors to expand it.
- The `with_scoped_network` helper hinted at in ADR-0003 can be a free function in `exec.py` returning a list of argv tail entries; keep it small and inline-callable. Do not export it from `codegenie/__init__.py`.
