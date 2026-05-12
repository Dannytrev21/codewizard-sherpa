# Story S3-05 — `JailedLeafLlmAgent` + bwrap jail launcher + file-based RPC

**Step:** Step 3 — Ship `LeafLlmAgent` implementations + `EgressProxy` + cassette discipline
**Status:** Ready
**Effort:** L
**Depends on:** S3-04 (`EgressProxy` daemon), S3-01 (`AnthropicClient` shim)
**ADRs honored:** ADR-P4-004, ADR-P4-007, ADR-P4-013, ADR-P4-011

## Context
`JailedLeafLlmAgent` is the Linux-default `LeafLlmAgent` implementation. The agent runs as a subprocess under `bwrap --unshare-all --uid <agent-uid>` with **no repo working tree, no `.codegenie/cache/`, no `~/.ssh`** bind-mounted — only `/agent-jail/<run-id>/{in,out}` is writable, and only the EgressProxy UDS at `unix:/jail/egress.sock` is reachable. Communication uses **file-based RPC** (orchestrator writes `req.json` into the jail, agent reads, agent writes `resp.json`, orchestrator reads). This is the second-highest security-review surface in the phase (after the proxy itself). Startup-order matters: the EgressProxy must be listening before the jail is spawned, or the agent will fail immediately with no audit trail.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design / 2. LeafLlmAgent` — agent process boundary on Linux; `§Process view` — startup ordering (proxy UDS readiness → jail spawn); `§Edge cases #12, #13, #18` — proxy deny, working-tree read, `--leaf=in_process` warning on Linux; `§Adversarial tests` — `test_e2e_jailed_leaf_linux.py`.
- **Phase ADRs:**
  - `../ADRs/0004-leaf-llm-agent-protocol-os-tiered.md` — ADR-P4-004 — Protocol membership; OS-tiered default selection.
  - `../ADRs/0007-anthropic-model-pin-via-versioned-alias.md` — ADR-P4-007 — model alias resolution (already done in S3-01, consumed here).
  - `../ADRs/0013-api-key-store-env-var-refused.md` — ADR-P4-013 — agent process MUST NOT have the key in its env; jail strips env.
- **Source design:** `../final-design.md §Synthesis ledger row "Agent process boundary"` — Phase 4 in-process default; jail mode is the security-strict Linux path.
- **High-level impl:** `../High-level-impl.md §Step 3` bullets on `jailed.py` and `jail_launcher.py`.
- **Existing code:**
  - `src/codegenie/llm/leaf_anthropic/in_process.py` (S3-02) — protocol surface; reuse `_artifacts.py` dumper.
  - `src/codegenie/llm/leaf_anthropic/egress_proxy.py` (S3-04) — proxy + readiness probe.
  - `src/codegenie/llm/leaf_anthropic/client.py` (S3-01) — same shim used inside the jail.

## Goal
Run the Anthropic call inside a `bwrap --unshare-all --uid` jail that can only talk to the EgressProxy via UDS, exchanges requests/responses via file-based RPC, and provably cannot read the repo working tree, the codegenie cache, or any developer secrets.

## Acceptance criteria
- [ ] `src/codegenie/llm/leaf_anthropic/jailed.py` defines `JailedLeafLlmAgent(LeafLlmAgent)` with `available()` and `invoke(request: LlmRequest) -> LlmResponse`.
- [ ] `src/codegenie/llm/leaf_anthropic/jail_launcher.py` defines `JailLauncher` that:
  - resolves the `agent-uid` from config (default `--agent-uid` CLI flag or `CODEGENIE_AGENT_UID` env on the orchestrator host);
  - provisions `/agent-jail/<run-id>/{in,out}` with mode `0o700` owned by `agent-uid`;
  - builds the `bwrap` argv: `--unshare-all`, `--uid <agent-uid>`, `--bind /agent-jail/<run-id>/in /jail/in`, `--bind /agent-jail/<run-id>/out /jail/out`, `--bind /jail/egress.sock /jail/egress.sock`, `--ro-bind /usr /usr`, minimal `/lib`, **no** `--bind` of cwd, `$HOME`, `~/.ssh`, `~/.codegenie/`, repo path;
  - clears env (`--clearenv`) so `ANTHROPIC_API_KEY` cannot leak into the agent process.
- [ ] `JailedLeafLlmAgent.invoke(req)`:
  - **polls `EgressProxy.ready()`** before spawning the jail (startup-order test asserts this);
  - serializes the `LlmRequest` to `/agent-jail/<run-id>/in/req.json`;
  - spawns the bwrap subprocess pointing at an entry script that reads `req.json`, calls `AnthropicClient.messages_stream(...)` via `unix:/jail/egress.sock`, validates incrementally (S3-03), and writes `resp.json` to `/agent-jail/<run-id>/out`;
  - on completion the orchestrator reads `resp.json`, runs `OutputValidator` final pass, writes telemetry via `_artifacts.py`, and returns `LlmResponse`.
- [ ] On Linux, the default `--leaf` is `jailed`; `--leaf=in_process` emits `audit.warning(leaf_in_process_on_linux)` and proceeds (covered already by S3-02's test; this story re-verifies via integration).
- [ ] **Working-tree EACCES assertion:** `tests/integration/test_e2e_jailed_leaf_linux.py` (Linux-only) spawns the full jail with a real `req.json`, then has the entry script attempt `open("/path/to/repo/package.json")` — must raise `PermissionError` / EACCES.
- [ ] **No direct Anthropic reach:** same test attempts a TCP connect to `api.anthropic.com:443` from inside the jail — must fail with `OSError`/network unreachable.
- [ ] **Startup-order test:** `tests/integration/test_jailed_startup_order.py` asserts that if the EgressProxy is not yet `ready()`, `invoke()` waits (bounded timeout) and the bwrap subprocess is **not** spawned until readiness is confirmed.
- [ ] `tests/unit/llm/test_jail_launcher_argv.py` asserts the `bwrap` argv contains `--unshare-all`, `--uid`, `--clearenv`, the three required `--bind` paths, and contains **none** of the forbidden paths (cwd, `$HOME`, `~/.codegenie`, `~/.ssh`).
- [ ] ruff, ruff format, mypy strict on both files; pytest green on Linux job.

## Implementation outline
1. **`JailLauncher.build_argv(run_id, agent_uid, entry_script)`** — pure function; returns `list[str]`. Cover with `test_jail_launcher_argv.py`.
2. **`JailLauncher.provision(run_id, agent_uid)`** — `mkdir` with `0o700`, chown to `agent-uid`; idempotent.
3. **Entry script** — `src/codegenie/llm/leaf_anthropic/_jail_entry.py`: reads `/jail/in/req.json`, builds `AnthropicClient` pointed at `unix:/jail/egress.sock` (Anthropic SDK accepts `base_url` override; verify), invokes streaming + incremental validator, writes `/jail/out/resp.json`. The entry script is the only code that runs inside the jail.
4. **`JailedLeafLlmAgent.invoke(req)`**:
   - poll `proxy.ready()` with a 5s bounded retry;
   - write `req.json` (canary present — the agent inside the jail needs it for the validator's canary check; the **redacted** copy is what `_artifacts.py` writes outside the jail);
   - `subprocess.run(bwrap_argv, timeout=600s)` — workflow wall-clock kill;
   - read `resp.json`, parse to `LlmResponse`, run synchronous `OutputValidator` final pass for defense-in-depth.
5. **Telemetry:** `_artifacts.py` from S3-02 writes `raw.json`, redacted `request.json`, cost-ledger line — the orchestrator side does this, not the jailed process.
6. **`available()`** on Linux: returns `True` only when (a) `bwrap` is on PATH, (b) `agent-uid` resolves, (c) `/jail/egress.sock` exists or `EgressProxy` is startable, (d) `ApiKeyStore` returns a key (the orchestrator has it; the jail doesn't).
7. Add `--leaf={in_process,jailed}` CLI flag wiring in `src/codegenie/cli/...` so the selector path is testable end-to-end on Linux.

## TDD plan — red / green / refactor

### Red
Test file paths:
- `tests/unit/llm/test_jail_launcher_argv.py`
- `tests/integration/test_jailed_startup_order.py`
- `tests/integration/test_e2e_jailed_leaf_linux.py`

```python
# test_jail_launcher_argv.py
from codegenie.llm.leaf_anthropic.jail_launcher import JailLauncher

def test_argv_contains_required_flags_and_omits_forbidden_paths(tmp_path):
    launcher = JailLauncher(jail_root=tmp_path / "agent-jail")
    argv = launcher.build_argv(run_id="r1", agent_uid=4242, entry_script="/usr/local/bin/codegenie-jail-entry")
    assert "bwrap" == os.path.basename(argv[0])
    assert "--unshare-all" in argv
    assert "--clearenv" in argv
    assert any(a == "--uid" and argv[i+1] == "4242" for i, a in enumerate(argv))
    binds = [argv[i+1] + " " + argv[i+2] for i, a in enumerate(argv) if a == "--bind"]
    assert any("/agent-jail/r1/in /jail/in" in b for b in binds)
    assert any("/agent-jail/r1/out /jail/out" in b for b in binds)
    assert any("/jail/egress.sock" in b for b in binds)
    # forbidden paths
    joined = " ".join(argv)
    assert os.path.expanduser("~/.ssh") not in joined
    assert os.path.expanduser("~/.codegenie") not in joined
    assert "/proc/self/cwd" not in joined
```

```python
# test_jailed_startup_order.py  (Linux-only)
@pytest.mark.linux_only
def test_invoke_waits_for_proxy_ready_before_spawning(monkeypatch, slow_starting_proxy, jailed_agent):
    spawn_calls = []
    monkeypatch.setattr("subprocess.run", lambda *a, **k: spawn_calls.append(a) or _ok_resp())
    # proxy.ready() returns False for 200ms, then True
    jailed_agent.invoke(make_request())
    # spawn must not happen before proxy.ready() returns True
    assert slow_starting_proxy.first_ready_ts < spawn_calls[0]._invoked_ts
```

```python
# test_e2e_jailed_leaf_linux.py  (Linux-only)
@pytest.mark.linux_only
def test_jailed_agent_cannot_read_repo_or_reach_anthropic(running_proxy, jailed_agent_with_probe_entry, tmp_repo):
    # entry script attempts to (a) open a repo file and (b) TCP-connect api.anthropic.com:443
    resp = jailed_agent_with_probe_entry.invoke(make_request(probe_repo_path=str(tmp_repo / "package.json")))
    assert resp.diagnostics["repo_open_errno"] == errno.EACCES
    assert resp.diagnostics["anthropic_tcp_errno"] in (errno.ENETUNREACH, errno.EPERM, errno.EACCES)
```

### Green
- `JailLauncher.build_argv` minimal happy path; integration tests drive jail-spawn with a probe entry script that records the two errnos into `resp.diagnostics`.
- Use `subprocess.run` with `timeout=600`.

### Refactor
- Extract `_wait_for_proxy(proxy, timeout)` so other consumers (Phase 5 microVM) can reuse the readiness probe.
- Add docstring on `JailedLeafLlmAgent` enumerating the three "cannot reach" invariants and citing the test that proves each.
- Add a Hypothesis property test stub: any `run_id` from a constrained char-set produces an argv with no shell-meta characters.
- Logging hygiene: jail-entry-script logs go to `/jail/out/agent.log` and are surfaced under `.codegenie/remediation/<run-id>/llm/agent.log` by the orchestrator post-run.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/llm/leaf_anthropic/jailed.py` | The agent. |
| `src/codegenie/llm/leaf_anthropic/jail_launcher.py` | argv builder + provisioner. |
| `src/codegenie/llm/leaf_anthropic/_jail_entry.py` | The script that runs inside the jail. |
| `src/codegenie/llm/leaf_anthropic/__init__.py` | Export `JailedLeafLlmAgent`. |
| `tests/unit/llm/test_jail_launcher_argv.py` | Red — argv shape. |
| `tests/integration/test_jailed_startup_order.py` | Red — startup ordering. |
| `tests/integration/test_e2e_jailed_leaf_linux.py` | Red — full Linux E2E. |
| `docs/runbooks/linux-agent-uid-setup.md` (new, lightweight) | Operator runbook for provisioning `agent-uid` on CI runners. |
| `.github/workflows/linux.yml` | Wire the Linux-only job to run these tests. |

## Out of scope
- **EgressProxy daemon** — S3-04 ships it.
- **Streaming parser** — S3-03 ships the incremental validator; the jail entry script reuses it.
- **Cassette discipline** — S3-06.
- **microVM-based agent** — Phase 5.
- **`agent-uid` provisioning automation** — documented in the runbook; provisioning itself is operator-action.

## Notes for the implementer
1. **`--clearenv` is load-bearing.** Without it the agent inherits `ANTHROPIC_API_KEY` from the orchestrator's env, defeating S2-04's hard-refuse rule. Add an explicit unit assertion (`assert "ANTHROPIC_API_KEY" not in env_passed_to_subprocess`).
2. **`unix:` base_url support in the SDK.** Verify that the chosen Anthropic SDK version honors `base_url="unix:///jail/egress.sock"`-style schemes; if not, route via `httpx` directly inside the entry script and adapt the response into the SDK's `LlmResponse` shape.
3. **Startup ordering is a real bug class.** `bwrap` will happily spawn before the UDS exists; the agent will then get `ENOENT` on connect and you'll waste a token budget reading the failure mode. Bound proxy `ready()` polling to 5s, fail fast, audit.
4. **Working-tree EACCES test must be hostile.** The probe entry script must try to open a known repo file by absolute path — relying on "no cwd bind" is correct but the test must prove it, not just trust the launcher.
5. **`bwrap --uid` requires either CAP_SYS_ADMIN or a setuid bwrap binary.** Document this in the runbook; the Linux CI runner needs setup. Without it, `bwrap` will silently fall back and the jail won't actually isolate.
6. **File-based RPC is the contract Phase 5 swaps.** Phase 5's microVM uses the same `req.json` / `resp.json` shapes; keep the serializer free of bwrap-specific quirks (no symlinks, sorted keys, LF). A future swap shouldn't require rewriting the entry script.
7. **600s wall-clock kill is a hard upper bound.** `subprocess.run(timeout=600)` will `kill()` the child; this is intentional. Make sure the entry script handles SIGTERM cleanly — flush `resp.json` partial state or refuse to (current default: don't flush; treat as `LlmTimeout`).
8. **`tests/security/test_no_api_key_in_logs.py` extends here.** Scan `/jail/out/agent.log` as well — proves the agent never logged something it didn't have.
