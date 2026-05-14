# Story S1-06 — `ALLOWED_BINARIES` eleven additions (ADR-0001)

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** 02-ADR-0001

## Context

Every Layer B/C/G probe in Phase 2 shells out to a system binary: `scip-typescript`, `tree-sitter`, `semgrep`, `ast-grep`, `ripgrep`, `gitleaks`, `syft`, `grype`, `docker`, `strace`. Phase 0 froze `codegenie.exec.run_allowlisted` as the single subprocess chokepoint and `ALLOWED_BINARIES` as the auditable list. Phase 1 added `node` via a one-binary ADR. Phase 2 adds the rest via an omnibus ADR (02-ADR-0001). This story performs the additive edit — one frozenset extension — and adds the test that the sensitive-env-var strip continues to work.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #3 — run_external_cli` — names the eight Layer B/G tools (`scip-typescript`, `syft`, `grype`, `semgrep`, `ast-grep`, `ripgrep`, `gitleaks`, `tree-sitter`).
  - `../phase-arch-design.md §"Component design" #6 — RuntimeTraceProbe` — names the Layer C tools (`docker`, `strace`).
  - `../phase-arch-design.md §"Anti-patterns avoided"` row "Capability passed through ten frames" — `run_external_cli` is the registry; this allowlist is its data.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md` — 02-ADR-0001 — the omnibus governance ADR; lists eight new entries (`docker`, `strace`, `semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, `tree-sitter`). The manifest references **eleven** additions; reconcile: 02-ADR-0001 documents the named-trigger eight; the manifest adds three more (`ast-grep`, `ripgrep`, `node` is **already** in Phase 1's frozenset — recount: the eight in the ADR + `ast-grep` + `ripgrep` = ten new; plus `node` from Phase 1 = eleven *post-Phase-2* total above Phase 0's `{"git"}`). **This story adds ten entries** (`docker`, `strace`, `semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, `tree-sitter`, `ast-grep`, `ripgrep`). The final `ALLOWED_BINARIES` is `{"git", "node", "semgrep", "syft", "grype", "gitleaks", "scip-typescript", "ast-grep", "ripgrep", "tree-sitter", "docker", "strace"}` — twelve entries (the manifest's "eleven new" wording counts the additions relative to Phase 0; reconcile the count in the test against the actual frozenset).
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md` — production ADR-0012 — `docker` is the named upgrade door for Phase 5's microVM substitution.
- **Source design:**
  - `../final-design.md §"External CLI runtime additions to ALLOWED_BINARIES"` — the enumerated list and install commands.
- **Existing code:**
  - `src/codegenie/exec.py` — `ALLOWED_BINARIES = frozenset({"git", "node"})` (Phase 0 + Phase 1 ADR-0001); the `_SENSITIVE_EXACT` set and `_SENSITIVE_PREFIX` tuple are the env-strip defense. Extension is one line.
  - `tests/unit/exec/test_run_allowlisted.py` (Phase 0/1) — existing coverage of allowlist rejection + env strip; this story extends without weakening.
- **External docs (only if directly relevant):**
  - `docs/localv2.md §6` — tool install commands for the CLI's missing-tool message.

## Goal

Extend `src/codegenie/exec.py` `ALLOWED_BINARIES` from `{"git", "node"}` to the twelve-entry final set `{"git", "node", "semgrep", "syft", "grype", "gitleaks", "scip-typescript", "ast-grep", "ripgrep", "tree-sitter", "docker", "strace"}` — additively — and add a test asserting all new entries are present *and* that the existing sensitive-env-var strip continues to drop `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `SSH_AUTH_SOCK`, and every `AWS_*` key.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/exec.py` `ALLOWED_BINARIES` is `frozenset({"git", "node", "semgrep", "syft", "grype", "gitleaks", "scip-typescript", "ast-grep", "ripgrep", "tree-sitter", "docker", "strace"})` — exactly twelve entries; no others. The literal definition site (one line) is the only change.
- [ ] **AC-2.** Each of the ten *new* entries (everything except `git` and `node`) is named in 02-ADR-0001's table OR is justified in this story's "Notes for the implementer" with a named-trigger probe per `localv2.md §5.2–5.6` (since the manifest names eleven and 02-ADR-0001's ADR table names eight, the three extra are: `ast-grep` for `localv2.md §5.6 G2`, `ripgrep` for `localv2.md §5.6 G3`, and one of `docker`/`strace` already in the eight — file an ADR amendment to 02-ADR-0001 if any reviewer flags the gap).
- [ ] **AC-3.** `_SENSITIVE_EXACT` and `_SENSITIVE_PREFIX` are **untouched** — the env strip defense is unchanged.
- [ ] **AC-4.** `tests/unit/exec/test_allowed_binaries.py` is a new test file (or an extension to an existing one) asserting:
  - Every entry in `ALLOWED_BINARIES` is in the expected set (no surprises).
  - The expected set is exactly twelve entries (no silent additions).
  - Calling `run_allowlisted([binary, "--version"], cwd=tmp_path, timeout_s=5.0)` for each of the ten new binaries either succeeds **or** raises `ToolMissingError` (the binary is not on `$PATH`) — but never `DisallowedSubprocessError`. (Note: this test SKIPS in environments where the binary isn't installed; we only care that the allowlist accepts it.)
  - The sensitive env strip continues to drop `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `SSH_AUTH_SOCK`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` from `env_extra` (parametrized; for each, calling with `env_extra={KEY: "leak"}` triggers the `subproc.env_extra.sensitive_key_dropped` structlog event and the child env never contains the key — verified by passing a tool that echoes env, OR by inspecting the env passed to a mocked `asyncio.create_subprocess_exec`).
- [ ] **AC-5.** Phase 0 `forbidden-patterns` pre-commit (catch direct `subprocess.run` / `asyncio.create_subprocess_exec` outside `exec.py`) continues to be green; this story does not add a second chokepoint.
- [ ] **AC-6.** The contract-freeze snapshot test for `exec.py`'s **signature** (if one exists; Phase 0 ADR-0012 likely shipped one) stays green — only the `ALLOWED_BINARIES` constant changes, not the `run_allowlisted` signature.
- [ ] **AC-7.** The TDD plan's red test exists, was committed, and is green.
- [ ] **AC-8.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/exec/` all pass on the touched files.

## Implementation outline

1. Open `src/codegenie/exec.py`; change the one line:
   ```python
   ALLOWED_BINARIES: frozenset[str] = frozenset({
       "git", "node",
       "semgrep", "syft", "grype", "gitleaks",
       "scip-typescript", "ast-grep", "ripgrep", "tree-sitter",
       "docker", "strace",
   })
   ```
2. Update the module docstring at the top of `exec.py`: add one sentence — *"Phase 2 (02-ADR-0001) extends `ALLOWED_BINARIES` with the ten Layer B/C/G tools listed in `docs/phases/02-context-gather-layers-b-g/ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md`. Future additions are ADR-amend or new-phase-ADR; no silent expansion."*
3. Write red tests (see TDD plan); confirm they fail because new binaries aren't in `ALLOWED_BINARIES`.
4. Make the one-line edit; confirm green.
5. Refactor: nothing to refactor in `exec.py` — the change is data, not logic. Verify the env-strip test continues to pass.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/exec/test_allowed_binaries.py`

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from codegenie.errors import DisallowedSubprocessError, ToolMissingError
from codegenie.exec import ALLOWED_BINARIES, run_allowlisted


EXPECTED_NEW_BINARIES = {
    "semgrep", "syft", "grype", "gitleaks",
    "scip-typescript", "ast-grep", "ripgrep", "tree-sitter",
    "docker", "strace",
}
EXPECTED_TOTAL = {"git", "node"} | EXPECTED_NEW_BINARIES


def test_allowed_binaries_is_exact_twelve_entry_set() -> None:
    # AC-1 — strict equality; silent additions or deletions fail this test.
    assert ALLOWED_BINARIES == EXPECTED_TOTAL


def test_every_new_binary_is_present() -> None:
    # AC-2 — every named-trigger entry is registered.
    for b in EXPECTED_NEW_BINARIES:
        assert b in ALLOWED_BINARIES, f"missing: {b}"


@pytest.mark.parametrize("binary", sorted(EXPECTED_NEW_BINARIES))
async def test_new_binary_not_rejected_by_allowlist(binary: str, tmp_path: Path) -> None:
    """The allowlist accepts each new binary. The call may raise
    ToolMissingError if the binary is not installed in this environment
    (e.g., `strace` on macOS); that is expected and fine. The invariant is
    that DisallowedSubprocessError is NEVER raised."""
    try:
        await run_allowlisted([binary, "--version"], cwd=tmp_path, timeout_s=5.0)
    except DisallowedSubprocessError:
        pytest.fail(f"{binary!r} must be allowlisted; got DisallowedSubprocessError")
    except (ToolMissingError, Exception):
        # ToolMissingError (binary not installed) is fine.
        # Any other exception (non-zero exit from --version, etc.) is also fine
        # for this allowlist-acceptance test; we only assert non-rejection.
        pass


@pytest.mark.parametrize("sensitive_key", [
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN", "SSH_AUTH_SOCK",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
])
async def test_sensitive_env_var_is_dropped_from_child_env(
    sensitive_key: str, tmp_path: Path,
) -> None:
    """AC-4 — sensitive env vars passed via env_extra are stripped before
    the child process is spawned. Verified by patching
    asyncio.create_subprocess_exec to capture the env dict and asserting
    the sensitive key is absent."""
    import asyncio as _aio
    captured: dict[str, dict[str, str]] = {}

    class _FakeProc:
        returncode = 0
        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b""
        async def wait(self) -> int:
            return 0
        def terminate(self) -> None: ...
        def kill(self) -> None: ...
        pid = 12345

    async def fake_exec(*args: object, **kwargs: object) -> _FakeProc:
        captured["env"] = kwargs.get("env", {})  # type: ignore[assignment]
        return _FakeProc()

    with patch.object(_aio, "create_subprocess_exec", fake_exec):
        await run_allowlisted(
            ["git", "--version"],
            cwd=tmp_path,
            timeout_s=5.0,
            env_extra={sensitive_key: "leak-value"},
        )

    assert sensitive_key not in captured["env"], (
        f"{sensitive_key} must be stripped from child env; "
        f"actual env keys: {sorted(captured['env'].keys())}"
    )


def test_phase_0_sensitive_constants_unchanged() -> None:
    """AC-3 — _SENSITIVE_EXACT and _SENSITIVE_PREFIX are unchanged."""
    from codegenie.exec import _SENSITIVE_EXACT, _SENSITIVE_PREFIX
    assert _SENSITIVE_EXACT == frozenset({
        "SSH_AUTH_SOCK", "GITHUB_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    })
    assert _SENSITIVE_PREFIX == ("AWS_",)
```

Run — the first two tests fail (`semgrep` not in `ALLOWED_BINARIES`). Commit.

### Green — make it pass

One-line edit in `src/codegenie/exec.py`:

```python
ALLOWED_BINARIES: frozenset[str] = frozenset({
    "git", "node",
    "semgrep", "syft", "grype", "gitleaks",
    "scip-typescript", "ast-grep", "ripgrep", "tree-sitter",
    "docker", "strace",
})
```

### Refactor — clean up

- Update the module docstring of `exec.py` with the Phase-2 reference (02-ADR-0001).
- Nothing else in `exec.py` changes. The Phase 0/1 invariants (six chokepoint invariants — shell-off, stdin=DEVNULL, env-strip, cwd-mandatory, timeout-mandatory, allowlist) are not touched.
- The `forbidden-patterns` pre-commit hook (Phase 0) catches any direct `subprocess.run` outside `exec.py`; this story does not alter that.
- Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/exec.py tests/unit/exec/test_allowed_binaries.py`, `pytest tests/unit/exec/ -v`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/exec.py` | One-line edit: extend `ALLOWED_BINARIES`; one-sentence docstring note. |
| `tests/unit/exec/test_allowed_binaries.py` | New test file; allowlist coverage + env-strip parametric. |

## Out of scope

- **`run_external_cli` wrapper** — handled by S1-07; this story only extends the allowlist `run_external_cli` will rely on.
- **The Phase 2 ADRs** — handled by S1-11 (all nine ADRs land together).
- **Tool-readiness check edits in `cli.py`** — `localv2.md §6` install-command messages for missing tools land in S8-02/S8-03 alongside the CLI summary line. This story is allowlist-only.
- **`docker run --network=none --cap-drop=ALL --security-opt=no-new-privileges` flag enforcement** — those are per-call-site flags supplied by `RuntimeTraceProbe` (S5-02). The allowlist accepts the binary; the hardening is the caller's responsibility (02-ADR-0001 §Tradeoffs row 3).
- **`bubblewrap`/`bwrap` addition** — `bwrap` is **not** added to `ALLOWED_BINARIES`. `run_external_cli` (S1-07) invokes `bwrap` directly via `asyncio.create_subprocess_exec` because it's a wrapper, not a tool the probe-side authors call. **Reconcile with 02-ADR-0001 if this surfaces** — the ADR table lists eight tools; the wrapper-pattern exception for `bwrap` may need a one-sentence amendment.

## Notes for the implementer

- **Frozenset literal is the entire change.** Resist refactoring `exec.py` (Rule 3 — Surgical Changes). The module is Phase 0 chokepoint; surgical means one-line.
- **Count discipline.** The manifest says "eleven additions"; 02-ADR-0001's table lists eight; the final frozenset has twelve entries (10 new + `git` + `node`). The test pins the *expected total set* explicitly (`EXPECTED_TOTAL`); the discrepancy between "eleven" (likely "eleven binaries beyond Phase 0's original `{git}`") and "ten" (added in Phase 2) is documentation drift the manifest will reconcile — the test is the source of truth on disk.
- **`bwrap` is NOT in the allowlist.** `run_external_cli` (S1-07) `exec`s `bwrap` directly as a wrapper around `argv`. If a reviewer flags this as a chokepoint hole, the answer is: `bwrap` is invoked from `exec.py` only, with the same `_filter_env` discipline, and the call site is auditable via `grep "bwrap"` (one location). File an amendment to 02-ADR-0001 if the policy needs to be stated explicitly.
- **Allowlist-acceptance test handles missing tools gracefully.** `strace` on macOS, `gitleaks` on a dev workstation that hasn't installed it — both raise `ToolMissingError`. The test only asserts the *allowlist* accepts the binary (`DisallowedSubprocessError` is never raised). Do not require `--version` to succeed; do not skip with `pytest.skip` based on `shutil.which` (the test would lie about CI coverage).
- **Env-strip test uses a fake subprocess.** Patching `asyncio.create_subprocess_exec` is the right level of mock — high enough to capture the env dict, low enough to actually exercise `_filter_env`. Do not mock at `_filter_env` directly; that misses the integration.
- **`tests/adv/test_no_shell_true.py` (Phase 0 S4-05) still holds.** That test asserts no file under `src/codegenie/` other than `exec.py` imports `asyncio.create_subprocess_exec` or `subprocess.run`. This story does not introduce a second site; S1-07's `run_external_cli` lives in `exec.py`.
