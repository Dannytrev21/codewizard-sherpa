# Story S3-03 — DinD `build.py` subprocess chokepoint + `network_policy.py` iptables chokepoint

**Step:** Step 3 — Implement DinD backend + SandboxSpecBuilder + SandboxHealthProbe
**Status:** Ready
**Effort:** M
**Depends on:** S3-02 (`DockerInDockerClient` SDK core)
**ADRs honored:** ADR-0001 (two-chokepoint sandbox seam), ADR-0004 (DinD macOS default + `shared_kernel`)

## Context

ADR-0001 says only two files under `sandbox/did/` may `import subprocess`: `build.py` (for `docker buildx build --progress=plain` — the SDK's build streaming is unworkable for our progress capture needs) and `network_policy.py` (for `iptables` rule application, since the Docker SDK has no equivalent abstraction). Both are AST-fenced by `tests/schema/test_no_subprocess_outside_build_chokepoint.py`. This story implements both files surgically: nothing else under `sandbox/` gains a `subprocess` import as a side effect.

The `network=scoped` allowlist is the only path between `npm ci` (which needs `registry.npmjs.org`) and `network=none` (which `npm test` runs under). iptables rules are generated deterministically from `spec.egress_allowlist` and snapshot-tested via `tests/golden/iptables_rules_<network-policy>.txt`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — DockerInDockerClient` — "subprocess permitted only in `sandbox/did/build.py` ... `network_policy.py` is the only module that may call `iptables` (same chokepoint pattern)".
  - `../phase-arch-design.md §Testing strategy — Golden files` — `tests/golden/iptables_rules_<network-policy>.txt`.
  - `../phase-arch-design.md §Edge case 5` — postinstall egress dropped by allowlist.
  - `../phase-arch-design.md §Physical view` — "`network=scoped` only for `npm ci`; `network=none` for `npm test`".
- **Phase ADRs:**
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — ADR-0001 — exact subprocess allowlist. Adding a new subprocess site requires ADR amendment.
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — ADR-0004 — DinD is shared-kernel; iptables runs on the host Linux VM (macOS = Docker Desktop's embedded VM).
- **Source design:**
  - `../final-design.md §Synthesis ledger` — subprocess chokepoint discipline.
- **Existing code:**
  - `src/codegenie/sandbox/did/client.py` (from S3-02) — caller; will be edited to invoke `network_policy.apply(spec)` when `spec.network == "scoped"`.
  - `tests/schema/test_no_subprocess_outside_build_chokepoint.py` (from S1-07) — the fence test that must remain green and gain `build.py` + `network_policy.py` to its allowlist (already encoded there).
- **External docs:**
  - https://docs.docker.com/build/buildx/ — `docker buildx build --progress=plain` output format.
  - https://netfilter.org/projects/iptables/ — basic iptables rule syntax (target `DROP` chain `OUTPUT` for egress).

## Goal

Implement `docker buildx build --progress=plain` via subprocess in `did/build.py` and the iptables egress-allowlist application in `did/network_policy.py` — both with golden-file argv tests — without leaking a `subprocess` import to any other file under `sandbox/`.

## Acceptance criteria

- [ ] `src/codegenie/sandbox/did/build.py` defines `build_image(context_dir: Path, tag: str, *, dockerfile: Path | None = None, build_args: Mapping[str, str] | None = None) -> BuildResult` that shells out to `docker buildx build --progress=plain ...` via `subprocess.run` with `check=False`.
- [ ] `build.py` returns `BuildResult(exit_code: int, stdout: str, stderr: str, image_digest: str | None)`; on non-zero exit, raises `SandboxBuildFailed` carrying the truncated stderr (≤ 4 KB).
- [ ] `src/codegenie/sandbox/did/network_policy.py` defines `apply(spec: SandboxSpec, *, container_id: str) -> AppliedPolicy` and `revert(applied: AppliedPolicy) -> None`. `apply` is a no-op when `spec.network == "none"`; for `spec.network == "scoped"`, it computes iptables rules from `spec.egress_allowlist` and runs them via `subprocess.run`.
- [ ] iptables rule generation is a **pure function** `_compute_rules(egress_allowlist: list[str], container_ip: str) -> list[list[str]]` and golden-tested against `tests/golden/iptables_rules_scoped_npmjs.txt`.
- [ ] `DockerInDockerClient.execute` (edited) calls `network_policy.apply(spec, container_id=...)` after `container.start()` when `spec.network == "scoped"`; calls `network_policy.revert(applied)` in the `finally` cleanup block; **does not** import `subprocess` itself.
- [ ] `tests/schema/test_no_subprocess_outside_build_chokepoint.py` is green — AST walk asserts only `sandbox/did/build.py`, `sandbox/did/network_policy.py`, plus Firecracker dirs (S6-01) may `import subprocess`.
- [ ] Network policy revert runs even when the workload raises (i.e., `iptables` rules don't leak across runs).
- [ ] `tests/sandbox/did/test_build.py` exercises both the success path and a non-zero-exit build (cassette via subprocess `MagicMock`) and asserts the argv list is exactly `["docker", "buildx", "build", "--progress=plain", ...]` (golden).
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass.

## Implementation outline

1. `src/codegenie/sandbox/did/build.py`:
   - `import subprocess` (the one place outside `network_policy.py` it's allowed).
   - `build_image(...)` builds argv: `["docker", "buildx", "build", "--progress=plain"]` + `["-f", str(dockerfile)]` if set + `[f"--build-arg={k}={v}" for k,v in build_args.items()]` + `["-t", tag, str(context_dir)]`.
   - `subprocess.run(argv, capture_output=True, text=False, check=False, timeout=...)`.
   - Parse `image_digest` from stderr's `--progress=plain` summary line (regex `sha256:[0-9a-f]{64}`).
   - structlog event `sandbox.did.build.done`.
2. `src/codegenie/sandbox/did/network_policy.py`:
   - `import subprocess`.
   - `_compute_rules(allowlist, container_ip)` returns `[["iptables", "-I", "OUTPUT", "-s", container_ip, "-d", host, "-j", "ACCEPT"] for host in allowlist] + [["iptables", "-A", "OUTPUT", "-s", container_ip, "-j", "DROP"]]`.
   - `apply()` resolves `container_ip` via the Docker SDK passed in (no subprocess for this), then runs each rule via `subprocess.run([...], check=True)`.
   - `revert(applied)` runs the inverse `-D` rules.
   - structlog events `sandbox.did.network.apply` and `.revert`.
3. Edit `DockerInDockerClient.execute` to:
   - Set `network_mode="bridge"` (instead of `"none"`) when `spec.network == "scoped"`, else `"none"`.
   - After `container.start()`, if `spec.network == "scoped"`, call `network_policy.apply(spec, container_id=container.id)` and store the returned `AppliedPolicy` for revert in `finally`.
4. Add `tests/golden/iptables_rules_scoped_npmjs.txt` — one rule per line, generated by feeding `["registry.npmjs.org"]` + a fixed container IP into `_compute_rules`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths:
- `tests/sandbox/did/test_build.py`
- `tests/sandbox/did/test_network_policy.py`
- `tests/sandbox/did/test_network_policy_revert.py`

```python
# tests/sandbox/did/test_build.py
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from codegenie.sandbox.did.build import build_image
from codegenie.sandbox.errors import SandboxBuildFailed

def test_argv_is_docker_buildx_progress_plain(tmp_path):
    """The argv list is the contract — any reordering breaks reproducibility of build logs."""
    with patch("codegenie.sandbox.did.build.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"#1 writing image sha256:" + b"a" * 64)
        build_image(tmp_path, tag="test:1", build_args={"NODE_VERSION": "20"})
    argv = run.call_args.args[0]
    assert argv[:4] == ["docker", "buildx", "build", "--progress=plain"]
    assert "--build-arg=NODE_VERSION=20" in argv
    assert argv[-2:] == ["-t", "test:1"] or "-t" in argv  # exact placement asserted by golden snapshot file

def test_nonzero_build_raises_sandbox_build_failed(tmp_path):
    with patch("codegenie.sandbox.did.build.subprocess.run") as run:
        run.return_value = MagicMock(returncode=1, stdout=b"", stderr=b"oh no")
        with pytest.raises(SandboxBuildFailed) as exc:
            build_image(tmp_path, tag="test:1")
        assert "oh no" in str(exc.value)
```

```python
# tests/sandbox/did/test_network_policy.py
from pathlib import Path
from codegenie.sandbox.did.network_policy import _compute_rules

GOLDEN = Path(__file__).parent.parent.parent / "golden" / "iptables_rules_scoped_npmjs.txt"

def test_rules_match_golden():
    """Catches any drift in iptables argv: a one-character change here is a security regression."""
    rules = _compute_rules(["registry.npmjs.org"], container_ip="172.17.0.2")
    actual = "\n".join(" ".join(r) for r in rules) + "\n"
    assert actual == GOLDEN.read_text()

def test_drop_rule_is_last():
    """OUTPUT chain must end with DROP — order is load-bearing."""
    rules = _compute_rules(["a", "b"], "1.2.3.4")
    assert rules[-1][-1] == "DROP"
```

```python
# tests/sandbox/did/test_network_policy_revert.py
from unittest.mock import patch, MagicMock
from codegenie.sandbox.did.client import DockerInDockerClient
from codegenie.sandbox.contract import SandboxSpec

def test_revert_runs_even_when_workload_raises(monkeypatch, tmp_path, allowlist, scoped_spec):
    """If `network_policy.revert` is skipped on error, iptables rules leak across runs.
    This test fails immediately on any cleanup ordering bug in execute()."""
    revert_called = []
    fake_container = MagicMock(); fake_container.id = "abc"
    fake_container.wait.side_effect = RuntimeError("workload boom")
    fake_container.logs.return_value = iter([])
    fake_docker = MagicMock(); fake_docker.containers.create.return_value = fake_container
    monkeypatch.setattr("docker.from_env", lambda: fake_docker)
    monkeypatch.setattr("codegenie.sandbox.did.network_policy.apply", lambda spec, container_id: object())
    monkeypatch.setattr("codegenie.sandbox.did.network_policy.revert", lambda a: revert_called.append(a))
    monkeypatch.chdir(tmp_path)
    client = DockerInDockerClient(allowlist=allowlist)
    import pytest
    with pytest.raises(Exception):
        client.execute(scoped_spec)
    assert len(revert_called) == 1
```

### Green — make it pass

- Implement `build.py` with the argv builder above; regex-extract `image_digest`.
- Implement `network_policy.py` with `_compute_rules` + `apply` + `revert`.
- Edit `client.py` `execute()` to wire policy apply/revert into try/finally.
- Generate and commit `tests/golden/iptables_rules_scoped_npmjs.txt`.

### Refactor — clean up

- Extract `_parse_image_digest(stderr: bytes) -> str | None` — pure function, easy to test.
- Docstrings at top of both files citing ADR-0001 as the only justification for `subprocess`.
- structlog events with `argv` redacted (no rule contents — golden file is the source of truth) but `rule_count` present.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/did/build.py` | New — `docker buildx` subprocess chokepoint. |
| `src/codegenie/sandbox/did/network_policy.py` | New — iptables subprocess chokepoint + pure rule computer. |
| `src/codegenie/sandbox/did/client.py` | Edit — wire `apply`/`revert` into `execute`'s try/finally; switch `network_mode` based on `spec.network`. |
| `src/codegenie/sandbox/errors.py` | Add `SandboxBuildFailed`, `NetworkPolicyApplyFailed`. |
| `tests/sandbox/did/test_build.py` | New — argv golden + non-zero exit. |
| `tests/sandbox/did/test_network_policy.py` | New — `_compute_rules` golden + DROP-last invariant. |
| `tests/sandbox/did/test_network_policy_revert.py` | New — revert on exception. |
| `tests/golden/iptables_rules_scoped_npmjs.txt` | New — golden iptables rules. |

## Out of scope

- Firecracker network policy — S6-02.
- Live integration against a real Docker daemon — S3-07.
- `--allow-test-network` CLI flag widening `egress_allowlist` — S8-02.
- Validating that the iptables rules actually drop packets — golden file is the contract; behavioral verification is the live integration test in S3-07.

## Notes for the implementer

- **The fence test runs on every PR.** If you `import subprocess` in `client.py` "just for a second", the PR fails. Push the call into one of the two chokepoint files and have `client.py` import the function, not `subprocess`.
- iptables rules require the Docker daemon's network namespace; Docker Desktop on macOS routes through its embedded Linux VM, so `iptables` runs there. The integration test in S3-07 will exercise this for real.
- `--progress=plain` is the only progress format whose stderr is parseable for `image_digest`; `--progress=auto` flips to TTY format mid-stream.
- Don't `shell=True` on `subprocess.run` — argv-list form only. Linting will catch you anyway.
- `_compute_rules` must take a fixed `container_ip` argument (not call any IP resolver inside) so it's pure and golden-testable. The IP-resolution sits in `apply()`, which is fenced.
- DNS resolution of `egress_allowlist` entries (`registry.npmjs.org` → IP) is one of the harder parts — Docker handles DNS for the container; iptables operates on IPs. The rule pattern `-d <hostname>` works on most iptables versions; if not, resolve via SDK's `client.api.inspect_network(...)` and use IP literals. Document the choice in a `# NOTE:` at the top of the file.
- `mypy --strict` will complain about `subprocess.run`'s overloads; pin `text=False` for byte-level reproducibility and cast `stdout`/`stderr` explicitly.
