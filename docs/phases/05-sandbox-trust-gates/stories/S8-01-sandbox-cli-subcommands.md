# Story S8-01 — `codegenie sandbox {health,inspect,gc,prepare}` Click subcommands

**Step:** Step 8 — Operator CLI surface + end-to-end smoke
**Status:** Ready
**Effort:** M
**Depends on:** S6-04, S7-04
**ADRs honored:** ADR-0004, ADR-0005, ADR-0007, ADR-0013

## Context

Phase 5's runtime primitives (`SandboxClient`, `RetryLedger`, `SandboxHealthProbe`, `auto_detect`, `sandbox prepare`) are now all in place but operators have no way to inspect or maintain them. This story lands the four operator-facing Click subcommands under `codegenie sandbox` that close roadmap §Goal 15 and make `attempts.jsonl` + sandbox run dirs debuggable without writing custom Python.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — CLI surface (codegenie sandbox)` — exact subcommand surface, performance envelope, failure behavior.
  - `../phase-arch-design.md §Cross-cutting concerns §Replay / debugability` — `inspect` semantics; BLAKE3 chain re-verified every call.
  - `../phase-arch-design.md §Cross-cutting concerns §Idempotence` — `gc` idempotent on same `--older-than`; `prepare` idempotent on identical digests.
- **Phase ADRs:**
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — `health` must surface `gate_isolation_class` per backend.
  - `../ADRs/0005-phase4-chain-head-compatibility.md` — `inspect` reads the Phase 4 chain-head from `.codegenie/remediation/<run-id>/chain_head.bin` and warns on mismatch (does not abort — `inspect` is read-only).
  - `../ADRs/0007-pre-execute-marker-for-resume-safety.md` — `inspect` must render `pre_execute` markers distinctly from `attempt` rows.
  - `../ADRs/0013-digest-pinned-policy-yaml-codegenie-owned.md` — `prepare` validates `tools/digests.yaml#sandbox.policy_yaml` before rebake.
- **Production ADRs:**
  - `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — `health` is a probe surface; output schema is contract-stable.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Operator CLI"`.
- **Existing code:**
  - `src/codegenie/cli/__init__.py` — top-level Click group; add `sandbox` sub-group here.
  - `src/codegenie/sandbox/health/probe.py` (S3-06) — `SandboxHealthProbe.run()` returns `SandboxHealth`.
  - `src/codegenie/sandbox/registry.py` (S6-04) — `auto_detect()` and `get_backend(name)`.
  - `src/codegenie/gates/retry_ledger.py` (S2-01..S2-03) — `attempts()` + chain verification.
  - `src/codegenie/sandbox/firecracker/rootfs.py` (S6-03) — rootfs bake entry point reused by `prepare`.

## Goal

Ship the four Click subcommands `codegenie sandbox {health, inspect <gate-run-id>, gc [--older-than 7d], prepare [--backend firecracker]}` with chain verification on `inspect`, idempotent housekeeping for `gc` and `prepare`, and structured exit codes.

## Acceptance criteria

- [ ] `codegenie sandbox health` instantiates the auto-detected backend (or the one passed via `--backend`), calls `SandboxClient.health()`, pretty-prints `backend`, `reachable`, `confidence`, `gate_isolation_class`, `reasons`, `warnings`, and exits 0 on `reachable=True`, 1 otherwise.
- [ ] `codegenie sandbox inspect <gate-run-id>` resolves `<gate-run-id>` to `.codegenie/remediation/<run-id>/gates/<gate_id>/`, calls `RetryLedger.attempts()` (which re-verifies the BLAKE3 chain end-to-end), and pretty-prints one row per attempt with columns `attempt_id`, `started_at`, `duration_ms`, `state`, `failing_signals`, `sandbox_run_id`, `chain_hash[:8]`; `pre_execute` markers are rendered on their own row with a `►` prefix so they are visually distinct from `attempt` rows.
- [ ] `inspect` exits 0 on a valid chain; exits 13 with a single-line structured error on `AuditChainCorrupted` or `LedgerAttemptOutOfOrder`; exits 2 on unknown `<gate-run-id>` (Click usage error).
- [ ] `inspect` reads `.codegenie/remediation/<run-id>/chain_head.bin` if present and prints a `chain-head-match: yes|no` line; mismatch warns to stderr but does not change exit code (inspect is read-only per ADR-0005 — startup-only verification is `RetryLedger.__init__`'s job).
- [ ] `codegenie sandbox gc [--older-than 7d]` removes every `.codegenie/sandbox/runs/<id>/` directory whose `mtime` is older than the window and every `.codegenie/remediation/<run-id>/gates/*/sandbox/<sandbox-run-id>/` matching the same predicate; default window is `7d`; accepts `7d`, `48h`, `30m` (regex-validated).
- [ ] `gc` is idempotent: a second invocation with the same `--older-than` value within the same wall-clock second removes 0 dirs and exits 0 with `removed: 0` JSON line on stdout.
- [ ] `gc` never touches `attempts.jsonl`, `manifest.yaml`, `chain_head.bin`, or any file inside `.codegenie/remediation/<run-id>/gates/<gate_id>/` *outside* `sandbox/`; covered by an explicit test that pre-populates a fake `attempts.jsonl` and asserts it survives.
- [ ] `codegenie sandbox prepare [--backend firecracker]` invokes the rootfs bake (S6-03) only when the on-disk digest of `tools/firecracker/<rootfs_digest>/rootfs.ext4` does not match `tools/digests.yaml#sandbox.rootfs`; on match, exits 0 with `already-prepared: true` and never re-bakes.
- [ ] `prepare` raises `FirecrackerKvmMissing` and exits 1 with the structured reason on a macOS host with no KVM; the message tells the operator that DinD is the supported backend.
- [ ] All four commands emit one structlog event per invocation (`cli.sandbox.health`, `cli.sandbox.inspect`, `cli.sandbox.gc`, `cli.sandbox.prepare`) with `command`, `exit_code`, and the relevant args (no env, no paths outside the repo).
- [ ] `tests/cli/test_sandbox_cli.py` ≥ 90% line coverage on `src/codegenie/cli/sandbox.py`; uses `click.testing.CliRunner` for every subcommand.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/cli`, `pytest tests/cli/test_sandbox_cli.py` all pass.

## Implementation outline

1. Create `src/codegenie/cli/sandbox.py` with `@click.group("sandbox")` registered on the top-level `codegenie` group.
2. Implement `health`: call `sandbox.registry.auto_detect()` (or honor `--backend {did,firecracker,auto}`); instantiate the client; call `.health()`; pretty-print via a small `_render_health(h: SandboxHealth)` helper (table-style, no third-party tables — `click.echo` is enough).
3. Implement `inspect <gate-run-id>`:
   - Parse `<gate-run-id>` as `<remediation-run-id>:<gate_id>` (colon-separated) or fall back to walking `.codegenie/remediation/*/gates/<gate-run-id>/`.
   - Construct `RetryLedger(run_dir, gate_id, prev_chain_head=None)` and call `.attempts()` to re-verify the chain.
   - Open `attempts.jsonl` a second time line-by-line to render `pre_execute` markers (which `.attempts()` skips by design — markers are not `Attempt` rows).
   - Read `chain_head.bin` if present; compare to `ledger.head()`; print `chain-head-match`.
4. Implement `gc --older-than`:
   - Parse the window with a single regex `^(\d+)(d|h|m)$`; convert to a `timedelta`.
   - Walk both `.codegenie/sandbox/runs/*` and `.codegenie/remediation/*/gates/*/sandbox/*`; `shutil.rmtree` each whose `mtime < now - window`.
   - Emit a single JSON line on stdout: `{"removed": N, "older_than": "7d"}`.
5. Implement `prepare --backend firecracker`:
   - Read `tools/digests.yaml#sandbox.rootfs`; compute the on-disk BLAKE3 of `tools/firecracker/<rootfs_digest>/rootfs.ext4` if present.
   - If hashes match → `click.echo({"already-prepared": true})` and return.
   - Else call `codegenie.sandbox.firecracker.rootfs.bake(...)` (S6-03 surface).
6. Wire `cli.sandbox.*` structlog event constants in `src/codegenie/cli/_events.py` (or reuse Step 1's event-constants module if structured that way).

## TDD plan — red / green / refactor

### Red

Test file path: `tests/cli/test_sandbox_cli.py`

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from codegenie.cli import cli  # top-level group
from codegenie.gates.retry_ledger import RetryLedger
from codegenie.sandbox.contract import SandboxHealth


def test_health_prints_backend_and_isolation_class(monkeypatch, capsys) -> None:
    fake = SandboxHealth(
        backend="docker_in_docker",
        reachable=True,
        confidence="high",
        reasons=[],
        warnings=["strace SYS_PTRACE missing"],
        detected_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )

    class _FakeClient:
        gate_isolation_class = "shared_kernel"
        def health(self) -> SandboxHealth:
            return fake

    monkeypatch.setattr("codegenie.sandbox.registry.auto_detect", lambda: _FakeClient())

    result = CliRunner().invoke(cli, ["sandbox", "health"])
    assert result.exit_code == 0, result.output
    assert "docker_in_docker" in result.output
    assert "shared_kernel" in result.output
    assert "strace SYS_PTRACE missing" in result.output


def test_inspect_verifies_chain_and_renders_pre_execute_markers(tmp_path: Path, monkeypatch) -> None:
    # Build a real 2-attempt ledger with a pre_execute marker between them.
    run_dir = tmp_path / "remediation" / "run-1"
    run_dir.mkdir(parents=True)
    ledger = RetryLedger(run_dir=run_dir, gate_id="stage6_validate", prev_chain_head=None)
    # ... helper from S2-01 to record two valid attempts with a pre-execute marker
    # between them via ledger.record_pre_execute(...) (S2-02)
    # write chain_head.bin matching ledger.head()
    (run_dir / "chain_head.bin").write_bytes(ledger.head())

    monkeypatch.chdir(tmp_path.parent)  # so .codegenie/... resolves
    # arrange .codegenie symlink/dir as the CLI expects
    result = CliRunner().invoke(cli, ["sandbox", "inspect", "run-1:stage6_validate"])

    assert result.exit_code == 0, result.output
    assert "attempt_id" in result.output and "chain_hash" in result.output
    assert "►" in result.output, "pre_execute markers must use the ► prefix row"
    assert "chain-head-match: yes" in result.output


def test_inspect_exits_13_on_tampered_chain(tmp_path: Path, monkeypatch) -> None:
    # build ledger, tamper a byte in attempts.jsonl, expect exit 13
    ...


def test_gc_idempotent_and_does_not_touch_attempts_jsonl(tmp_path: Path, monkeypatch) -> None:
    # populate .codegenie/sandbox/runs/old/ (mtime older than 7d)
    # populate .codegenie/remediation/r1/gates/g1/attempts.jsonl (must survive)
    # first invocation: removed > 0; second invocation: removed == 0
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    r1 = runner.invoke(cli, ["sandbox", "gc", "--older-than", "7d"])
    assert r1.exit_code == 0
    payload1 = json.loads([ln for ln in r1.output.splitlines() if ln.startswith("{")][-1])
    assert payload1["removed"] >= 1

    r2 = runner.invoke(cli, ["sandbox", "gc", "--older-than", "7d"])
    assert r2.exit_code == 0
    payload2 = json.loads([ln for ln in r2.output.splitlines() if ln.startswith("{")][-1])
    assert payload2["removed"] == 0
    assert (tmp_path / ".codegenie" / "remediation" / "r1" / "gates" / "g1" / "attempts.jsonl").exists()


def test_prepare_skips_when_digest_matches(tmp_path: Path, monkeypatch) -> None:
    # write tools/digests.yaml with sandbox.rootfs digest = blake3 of a fake rootfs.ext4
    # ensure rootfs.ext4 on disk matches that digest
    # invoke prepare; assert no bake function was called and output contains "already-prepared"
    ...
```

### Green

Implement only what each red test demands. `_render_health` is one `click.echo` per field. `_render_attempts` is one printf-style line per row. `gc` uses `Path.stat().st_mtime` + `time.time() - window.total_seconds()`. `prepare` short-circuits on digest match before any `bake(...)` import is invoked (assert via `monkeypatch.setattr` raising if called when it shouldn't be).

### Refactor

- Pull row-rendering into `cli/sandbox/_render.py` so the Click handler stays declarative.
- Extract the `<gate-run-id>` parser into `cli/sandbox/_resolve.py` with a focused test (`test_resolve.py`).
- Use `click.exceptions.UsageError` for the unknown-gate-run-id case so the exit code is the Click default of 2 without manual `sys.exit`.
- Document all four subcommands' `--help` output with one example each (Click auto-generates the rest).
- Add `__all__` exports.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli/sandbox.py` | New module — the `sandbox` Click sub-group + four subcommands. |
| `src/codegenie/cli/__init__.py` | Register `sandbox` group on the top-level `codegenie` group. |
| `src/codegenie/cli/_render.py` (optional) | Pretty-printers for `SandboxHealth` and `Attempt` rows. |
| `src/codegenie/cli/_events.py` | `cli.sandbox.*` structlog event-name constants. |
| `tests/cli/test_sandbox_cli.py` | Red test + the four happy-path + adversarial cases. |
| `tests/cli/conftest.py` | Shared `tmp_codegenie_repo` fixture (creates `.codegenie/` skeleton). |

## Out of scope

- `codegenie remediate` flag wiring (`--sandbox-backend`, `--max-attempts-override`, `--allow-test-network`) — S8-02.
- The headline E2E test — S8-03.
- Coverage report and ADR audit — S8-04.
- Rich/Tabulate dependency — `click.echo` is sufficient; do not pull a table library for this story.
- Phase 11 evidence-bundle export — Phase 11 owns it; `inspect` only reads.
- Concurrent-invocation safety on `gc` — `fcntl.flock` from S7-04 covers `remediate`; `gc` is a pure filesystem operation and acceptably racy with itself.

## Notes for the implementer

- The CLI must never instantiate `RetryLedger` with a non-`None` `prev_chain_head` from a guessed source. `inspect` is read-only: pass `prev_chain_head=None`, then *separately* compare `ledger.head()` against the on-disk `chain_head.bin` and print the result — do not let the constructor abort the inspection.
- `gc`'s window-parsing regex must reject `7days`, `7D`, `-7d`, `0d`; add a parametrized test for the rejected forms.
- Do not import anything from `sandbox/did/` or `sandbox/firecracker/` directly in `cli/sandbox.py` — go through `sandbox/registry.py`. The CLI is a thin shell over the registry; that's what makes Phase 7 distroless register a new backend with zero CLI edits.
- The `pre_execute` row renderer must not call `Attempt.model_validate_json` on those lines — they are not `Attempt` rows. Read them as raw dicts with `json.loads` and assert `payload["kind"] == "pre_execute"`.
- macOS contributors will run `prepare` and get `FirecrackerKvmMissing`. That is expected and not a story failure; surface the supported-backend hint and exit non-zero.
- Exit code 13 for chain-corruption is **new** in Phase 5 and distinct from 11 (`escalate`) and 12 (`failed_unrecoverable`). Document the exit-code table in `--help` epilog.
- `gc` walking inside `.codegenie/remediation/*/gates/*/sandbox/*` must use `Path.glob("remediation/*/gates/*/sandbox/*")` — do NOT recurse into `attempts.jsonl`-bearing directories. The test asserting `attempts.jsonl` survival is load-bearing.
