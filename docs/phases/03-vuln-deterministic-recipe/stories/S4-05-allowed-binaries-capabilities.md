# Story S4-05 — `ALLOWED_BINARIES` amendment + `Capability` tokens + `mint()` chokepoint + ruff custom fence + `--ignore-scripts` enforcement

**Step:** Step 4 — SubprocessJail Port + Bwrap + sandbox-exec + ALLOWED_BINARIES amendment
**Status:** Ready
**Effort:** M
**Depends on:** S4-04 (`SandboxedPath` exists; capability scope references it); transitively S4-01 (`SubprocessJail` Port consumers reference capability tokens), S1-01 (`PluginId`, `RegistryUrl` newtypes), and Phase 2 ADR-0001 (the omnibus this story amends)
**ADRs honored:** 03-ADR-0012 (amend `ALLOWED_BINARIES` with `npm`, `bwrap`, `sandbox-exec`, `jq` — amends 02-ADR-0001); 03-ADR-0011 (honest framing — `Capability` tokens are *audit + lint*, NOT runtime-unforgeable; `GitLocalOpsCapability` has no `push` field as a real type-level invariant); 03-ADR-0006 (`--ignore-scripts` enforced at BOTH CLI and env)

## Context

This is the **data + fence** story of Step 4. Three load-bearing changes land together:

### (1) `ALLOWED_BINARIES` amendment (data change, ADR-0012)

Phase 2 ADR-0001 (the omnibus subprocess-discipline ADR) established `ALLOWED_BINARIES` as a closed `frozenset` in `src/codegenie/exec/__init__.py` with twelve entries: `git`, `node`, `semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, `ast-grep`, `ripgrep`, `tree-sitter`, `docker`, `strace`. Adding a binary requires an ADR amendment.

Phase 3 adds four: `npm` (recipe engine + Stage-6 validate), `bwrap` (Linux jail adapter), `sandbox-exec` (macOS jail adapter), `jq` (operator-tooling adjunct for `codegenie audit verify | jq ...` patterns). Total post-Step-4: sixteen entries.

This story is the **amendment**: it lands the explicit ADR cross-reference, updates `src/codegenie/exec/__init__.py::ALLOWED_BINARIES` (and the comments above it), and pins the new total at a fence test that breaks on any silent drift. ADR-0012 §Decision: "the `SubprocessJail` adapters (`BwrapAdapter`, `SandboxExecAdapter`) wrap `bwrap` / `sandbox-exec` via `run_external_cli` — they do NOT bypass the chokepoint."

S1-06 (the Phase 2 precedent for this kind of amendment) is the structural template. Mirror its discipline: closed-set exact-equality test, per-binary path-traversal rejection, env-strip applies to new binaries, weakref cleanup pinned per binary, ADR cross-document gate.

### (2) `Capability` tokens + single `mint()` chokepoint (ADR-0011)

`src/codegenie/plugins/capabilities.py` ships three frozen Pydantic models — `NpmInstallCapability`, `FsReadWriteCapability`, `GitLocalOpsCapability` — plus a `CapabilityBundle` aggregator and **one and only one** `mint()` entry point. Per ADR-0011 §Decision §Capability tokens:

- These are **audit + lint enforcement**, NOT runtime unforgeability. Pydantic models can be constructed anywhere; the type system doesn't know its caller. The defense is (a) every `mint()` call emits a `CapabilityMinted` spanning event (S6-01 lands the event infrastructure; this story emits at the right shape with a forward-import), and (b) a **custom ruff rule** AST-walks `src/` + `plugins/` and fails on any `*Capability(...)` construction outside `capabilities.py` or `tests/`.

- **`GitLocalOpsCapability` has NO `push` field.** Minting a `push` capability is type-impossible. This IS a real type-level invariant — for one specific operation that matters most (per production ADR-0009 "humans always merge"). The story's ACs pin this structurally.

### (3) `--ignore-scripts` enforcement at CLI + env (ADR-0006)

S4-01 already pins the **env half** (`npm_config_ignore_scripts="true"`) structurally inside `NpmEnv.to_env_mapping()`. This story adds the **CLI half** fence: a static lint test that asserts every npm-related call site in `src/codegenie/transforms/engines/` (S5-02's home) constructs `JailedSubprocessSpec.cmd` with `--ignore-scripts` literally in the tuple. Together, the env-half and CLI-half close the historical npm bug where one or the other was honored but not both.

S5-02 has not landed yet; this story's fence is **forward-looking** — it scans for the pattern `JailedSubprocessSpec(...cmd=(... "npm", ...))` and asserts `--ignore-scripts` is present in the same tuple. The fence is structural: when S5-02 lands, it will trip if the implementer forgets `--ignore-scripts`. (This is the "tests-first" inverse: write the fence test before the consumer exists.)

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C10` — `Capability` tokens + `SandboxedPath`; honest framing; `mint()` chokepoint; ruff lint rule.
  - `../phase-arch-design.md §Component design C8` — `--ignore-scripts` both at CLI and env; npm bug history.
  - `../phase-arch-design.md §Goal G6` — "Zero edits to Phase 0/1/2 — the only permitted edits: extending `ALLOWED_BINARIES`."
  - `../phase-arch-design.md §Edge case E8` — postinstall canary regression test (S8-04 lands the full adversarial fixture; this story lands the structural fence).
  - `../phase-arch-design.md §Tradeoffs (consolidated)` — `Capability` is audit + lint, NOT runtime-unforgeable; honest framing.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md` — the amendment ADR. §Decision pins the four new binaries; §Consequences pins the `tests/unit/exec/test_allowlist.py` exact-contents test; §Tradeoffs row 1 pins the single-chokepoint preservation.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — §Decision §Capability tokens block pins the three capability types + `mint()` chokepoint + `GitLocalOpsCapability` has no `push` field + custom ruff rule + lint fence test path.
  - `../ADRs/0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md` — §Decision pins `--ignore-scripts` at BOTH CLI and env; this story closes the CLI-half fence.
- **Phase 2 ADRs (the amendment target):**
  - `../../02-context-gather-layers-b-g/ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md` — the omnibus this story amends explicitly (per ADR-0012 §Decision "amends 02-ADR-0001"). Mirror the amendment style of the S1-06 Phase 2 story (which amended this same ADR to extend from eight to ten Layer B/C/G binaries).
- **Source design:**
  - `../final-design.md §Synthesis ledger rows "Capability tokens"` (score 15/15) and `"Plugin loader trust model"` (score 13/15).
  - `../High-level-impl.md §Step 4 features delivered` — pins `src/codegenie/plugins/capabilities.py` + `tooling/ruff_rules/no_capability_construction.py` + `tests/static/test_capability_fence.py`.
- **Existing code:**
  - `src/codegenie/exec/__init__.py::ALLOWED_BINARIES` — the closed frozenset this amendment edits. Current twelve entries; this story makes it sixteen.
  - `src/codegenie/types/identifiers.py` — `PluginId`, `RegistryUrl` newtypes capabilities reference.
  - `src/codegenie/plugins/sandbox_path.py` (S4-04) — `SandboxedPath` may be referenced by `FsReadWriteCapability.scope`.
  - Phase 2 story precedent: `docs/phases/02-context-gather-layers-b-g/stories/S1-06-allowed-binaries-extension.md` — the structural template for the allowlist-amendment portion. **Read this story before starting** (Rule 8).
- **External docs:**
  - `tooling/ruff_rules/` — verify whether the codebase already has a custom-ruff-rules infrastructure or a `flake8`-plugin equivalent. If neither, this story may need to land the scaffolding plus the rule.

## Goal

Land all three changes in a single coherent story:

1. **`ALLOWED_BINARIES` amendment** to `{git, node, semgrep, syft, grype, gitleaks, scip-typescript, ast-grep, ripgrep, tree-sitter, docker, strace, npm, bwrap, sandbox-exec, jq}` (sixteen entries). Pin in `tests/unit/exec/test_allowlist.py` (or equivalent) with exact-equality, per-binary path-traversal rejection, env-strip applies to new binaries, weakref cleanup. ADR-0012 cross-document gate test asserts the amendment is enumerated in the ADR.

2. **`Capability` tokens + `mint()`** at `src/codegenie/plugins/capabilities.py`:
   - `NpmInstallCapability(BaseModel, frozen=True, extra="forbid")` with `registry: RegistryUrl`, `_minted_by: PluginId`.
   - `FsReadWriteCapability(BaseModel, frozen=True, extra="forbid")` with `scope: SandboxedPath`, `_minted_by: PluginId`.
   - `GitLocalOpsCapability(BaseModel, frozen=True, extra="forbid")` — fields for `repo: SandboxedPath`, `branch_namespace: str`, `_minted_by: PluginId`. **No `push` field.** Type-impossible to mint.
   - `CapabilityBundle(BaseModel, frozen=True, extra="forbid")` aggregator with `npm: NpmInstallCapability | None`, `fs: FsReadWriteCapability | None`, `git: GitLocalOpsCapability | None`.
   - `mint(plugin: PluginId, scope: CapabilityScope) -> CapabilityBundle` — the ONLY mint point. Emits a forward-shaped `CapabilityMinted` event (S6-01 lands the real event writer; this story emits to a forward-declared sink).

3. **Custom ruff rule `tooling/ruff_rules/no_capability_construction.py`** that AST-walks `src/` + `plugins/` (excluding `src/codegenie/plugins/capabilities.py` and `tests/**`) and reports any `*Capability(...)` construction. **`tests/static/test_capability_fence.py`** runs the rule and asserts zero violations.

4. **`--ignore-scripts` CLI-half static fence** at `tests/static/test_npm_ignore_scripts_cli_present.py`: AST-walks `src/codegenie/transforms/engines/` (forward-looking — S5-02's home) for any `JailedSubprocessSpec(...cmd=(... "npm", ... "install" | "test" | "ci", ...))` tuple and asserts `"--ignore-scripts"` is literally present in the same tuple.

`mypy --strict` clean. `make check` + `make lint-imports` green.

## Acceptance criteria

### Allowlist amendment

- [ ] **AC-1.** `src/codegenie/exec/__init__.py::ALLOWED_BINARIES` is `frozenset({"git", "node", "semgrep", "syft", "grype", "gitleaks", "scip-typescript", "ast-grep", "ripgrep", "tree-sitter", "docker", "strace", "npm", "bwrap", "sandbox-exec", "jq"})` — exactly sixteen entries. Module-level comment above the literal is updated to reference both 02-ADR-0001 (Phase 2 amendment) AND 03-ADR-0012 (Phase 3 amendment).
- [ ] **AC-2.** Module docstring at top of `exec/__init__.py` gains one sentence: "Phase 3 (03-ADR-0012) extends with four binaries (`npm`, `bwrap`, `sandbox-exec`, `jq`) — see `docs/phases/03-vuln-deterministic-recipe/ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md`." A pytest meta-test (`test_exec_module_docstring_phase3_present`) asserts the substrings `"03-ADR-0012"` AND `"four binaries"` (or equivalent enumeration phrase) are present.
- [ ] **AC-3.** `tests/unit/exec/test_allowlist.py` (or `tests/unit/exec/test_allowed_binaries.py` — match the Phase 2 file convention) asserts:
  - `ALLOWED_BINARIES == EXPECTED_TOTAL_SIXTEEN` (exact equality; silent additions / deletions fail).
  - Every new binary (`npm`, `bwrap`, `sandbox-exec`, `jq`) is present.
  - The Phase-2 twelve-entry baseline is preserved.
- [ ] **AC-4.** ADR-0012 cross-document gate (mirrors S1-06's AC-2): `test_adr_0012_enumerates_all_new_binaries` opens `docs/phases/03-vuln-deterministic-recipe/ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md` and asserts each of `{npm, bwrap, sandbox-exec, jq}` appears literally as a backticked identifier. If S1-06 added enforcement for "exactly N entries" string-match, mirror that pattern with "four new binaries" or whatever phrase ADR-0012 §Decision actually uses (verify against the ADR text).
- [ ] **AC-5.** Per-new-binary parametric test asserting `run_allowlisted([binary, "--version"], ...)` for each of `{npm, bwrap, sandbox-exec, jq}` either succeeds or raises `ToolMissingError` / `ProbeTimeoutError` / `FileNotFoundError` — but **never** `DisallowedSubprocessError`. Mirrors S1-06 AC-4.
- [ ] **AC-6.** Per-new-binary path-traversal rejection: parametric over `[(f"/usr/bin/{b}", b) for b in NEW_BINARIES] + [(f"./{b}", b) for b in NEW_BINARIES]` asserts each raises `DisallowedSubprocessError` and `asyncio.create_subprocess_exec` is NOT awaited (spy-asserted). Mirrors S1-06 AC-14.
- [ ] **AC-7.** Env-strip parametric extends to new binaries: at least one new binary × `{OPENAI_API_KEY, AWS_SECRET_ACCESS_KEY, GITHUB_TOKEN}` triple asserts the key is dropped from the captured child env AND the `subproc.env_extra.sensitive_key_dropped` structlog event fires. Mirrors S1-06 AC-12.
- [ ] **AC-8.** `_RUNNING_PROCS` weakref cleanup per new binary: parametric over `NEW_BINARIES` asserts `len(_RUNNING_PROCS) == 0` after each `run_allowlisted` exit path. Mirrors S1-06 AC-13.
- [ ] **AC-9.** Closed-set negative-list regression test in `tests/unit/test_exec.py::test_allowed_binaries_closed_set_regression` is extended (NOT replaced) — the parametrize list keeps Phase 1 + Phase 2's entries AND adds NOTHING for Phase 3 (since `bwrap` and `sandbox-exec` are now ALLOWED, they leave the negative list; verify the Phase 2 story landed `bwrap` / `bubblewrap` in the negative list per its AC-15 — if so, REMOVE `bwrap` from that parametrize list in this story and add a one-line comment explaining the move from "negative" to "allowed" in Phase 3, with cross-reference to 03-ADR-0012). Symmetric ratchet: the closed-set discipline survives even when the polarity flips.

### Capability tokens + mint chokepoint

- [ ] **AC-10.** `src/codegenie/plugins/capabilities.py` exists and exports exactly: `NpmInstallCapability`, `FsReadWriteCapability`, `GitLocalOpsCapability`, `CapabilityBundle`, `mint`, `CapabilityScope`. No other public symbols leak.
- [ ] **AC-11.** Each of the three capability types is a frozen Pydantic model (`model_config = ConfigDict(frozen=True, extra="forbid")`). A parametrized test asserts:
  - Construction with an unknown field raises `ValidationError`.
  - Instance mutation raises `ValidationError`.
- [ ] **AC-12.** **`GitLocalOpsCapability` has no `push` field — the type-level invariant.** A test asserts:
  - `"push" not in GitLocalOpsCapability.model_fields`.
  - Attempting `GitLocalOpsCapability(repo=..., branch_namespace=..., push=True)` raises `ValidationError` (Pydantic's `extra="forbid"` rejects unknown fields).
  - The class docstring contains the substring `"no push field"` (or `"NO push field"`) and references `03-ADR-0011` and production `ADR-0009`. The framing is structural.
- [ ] **AC-13.** `mint(plugin, scope) -> CapabilityBundle` is the only function in `capabilities.py` that constructs `*Capability` instances. A grep test reads the module source and asserts the constructors `NpmInstallCapability(`, `FsReadWriteCapability(`, `GitLocalOpsCapability(` appear inside the `mint` function only (substring search bounded by `def mint` and the next `def `).
- [ ] **AC-14.** `mint()` emits a `CapabilityMinted` event by calling a forward-imported event sink (`from codegenie.plugins.events import emit_capability_minted` or a `TYPE_CHECKING`-guarded forward shim if S6-01 hasn't landed). When the real sink is absent, the call is a no-op; when present (S6-01 onward), the event flows to the spanning stream. A test monkeypatches the emit function and asserts it's called once per `mint()` invocation with the right shape (`plugin_id`, `bundle_digest`).

### Ruff custom rule + fence test

- [ ] **AC-15.** `tooling/ruff_rules/no_capability_construction.py` exists, implementing a Python AST walker (or ruff plugin per the codebase's existing pattern — verify before choosing) that:
  - Scans all `.py` files under `src/` AND `plugins/`.
  - Reports any `Call` node whose `func` is `Name(id="NpmInstallCapability" | "FsReadWriteCapability" | "GitLocalOpsCapability" | "CapabilityBundle")` AND whose enclosing file is NOT `src/codegenie/plugins/capabilities.py` AND NOT under `tests/`.
  - Returns the list of violations with file path + line number.
- [ ] **AC-16.** `tests/static/test_capability_fence.py` invokes the AST walker over the whole repo and asserts zero violations. Additional test cases:
  - Synthesized fixture file `tests/static/_capability_fence_fixtures/bad.py` containing `NpmInstallCapability(registry=...)` outside `capabilities.py` is detected (the test reads the file from a fixture dir, not as a real source file; or the walker is invoked over a list of files including the fixture).
  - Construction inside `tests/` is permitted (no violation).
  - Construction inside `capabilities.py::mint` is permitted.
- [ ] **AC-17.** The ruff rule is wired into `make check` (or `make lint` / `make lint-imports` — pick the right Make target per the codebase's discipline). A test asserts the rule actually runs as part of the gate by `subprocess`-invoking `make check` (or the targeted command) with a fixture file injected and observing the failure exit code; OR by `pytest`-collecting `tests/static/test_capability_fence.py` and confirming it's in the default test selection.

### `--ignore-scripts` CLI-half static fence

- [ ] **AC-18.** `tests/static/test_npm_ignore_scripts_cli_present.py` AST-walks `src/codegenie/transforms/engines/` (and any other Phase 3 module that constructs `JailedSubprocessSpec` with an npm cmd) and:
  - Finds every `Call` node `JailedSubprocessSpec(...)`.
  - Extracts the `cmd=` keyword's tuple/list literal.
  - If the literal starts with `"npm"` AND contains any of `{"install", "test", "ci", "audit", "ls"}`, asserts `"--ignore-scripts"` is also literally present in the tuple/list.
  - Skips Calls inside `tests/` (they may construct adversarial fixtures).
  - **Forward-looking**: if `src/codegenie/transforms/engines/` has zero matching files yet (S5-02 not landed), the test must `pytest.skip("Phase 3 npm engines not yet present — fence is forward-looking")` AND emit a warning that the fence is dormant. When S5-02 lands, the test wakes up structurally.
- [ ] **AC-19.** A unit test fixture (`tests/static/_ignore_scripts_fence_fixtures/bad_engine.py`) containing a `JailedSubprocessSpec(cmd=("npm", "install", "--package-lock-only"))` (missing `--ignore-scripts`) is detected by the walker; the test asserts the fence reports the violation. This proves the fence is alive even before S5-02 lands.

### Gates

- [ ] **AC-20.** `mypy --strict src/codegenie/{exec,plugins/capabilities.py} tests/unit/exec/ tests/unit/plugins/test_capabilities.py tests/static/` clean.
- [ ] **AC-21.** `ruff check` + `ruff format --check` clean on all touched files.
- [ ] **AC-22.** `make check` green (extended by AC-17 + AC-18 fences).
- [ ] **AC-23.** `make lint-imports` Phase 3 contracts green — no LLM SDK appears in `src/codegenie/plugins/capabilities.py`'s import closure.

## Implementation outline

1. **Allowlist amendment first** (smallest blast radius). Edit `src/codegenie/exec/__init__.py`:
   - Add `"npm"`, `"bwrap"`, `"sandbox-exec"`, `"jq"` to the frozenset literal.
   - Update the comment above with a 03-ADR-0012 cross-reference.
   - Update the module docstring (AC-2).
   - Run S1-06 family tests; they may break (the Phase-2 closed-set assertion in `tests/unit/test_exec.py::test_node_in_allowed_binaries` or equivalent will need to be updated forward — verify and update with a docstring note "Phase 3 ratchet" — Rule 11).
2. **Write the new allowlist tests** in `tests/unit/exec/test_allowlist_phase3.py` (or extend Phase 2's file — match precedent): AC-3..AC-9.
3. **Capability module**: create `src/codegenie/plugins/capabilities.py`:
   - Define the three frozen Pydantic models. Each has a `_minted_by: PluginId` private-ish field (Pydantic v2 supports underscore-prefixed names with `populate_by_name=True`).
   - Define `CapabilityScope` (likely a small Pydantic model carrying the scope description — registry URL for npm; jail SandboxedPath for fs; repo + branch namespace for git).
   - Define `mint(plugin: PluginId, scope: CapabilityScope) -> CapabilityBundle`:
     - Pattern-match on `scope` discriminator (or accept individual `*Scope` types and dispatch).
     - Construct the right `*Capability`(ies) inside `mint`.
     - Emit `CapabilityMinted` via the forward sink (S6-01 forward shim).
     - Return `CapabilityBundle(npm=..., fs=..., git=...)`.
4. **Write capability tests** in `tests/unit/plugins/test_capabilities.py`: AC-10..AC-14.
5. **Ruff custom rule**: verify whether the codebase has a custom-rule scaffolding (`tooling/ruff_rules/` directory may not exist yet). If absent, this is two pieces:
   - Pure-Python AST walker: `tooling/ruff_rules/no_capability_construction.py` exposes `find_violations(roots: list[Path]) -> list[Violation]`.
   - `tests/static/test_capability_fence.py` invokes the walker.
   - If the codebase already has a true ruff-plugin convention (e.g., a `ruff` config that loads custom rules), follow it. Otherwise, the AST-walker + pytest-fence pattern is the precedent (S1-05 likely uses this for `test_no_any_in_plugin_surface.py`).
6. **`--ignore-scripts` CLI-half static fence**: write `tests/static/test_npm_ignore_scripts_cli_present.py` with the AST walker described in AC-18. Land the bad-fixture (AC-19) to prove the fence is alive.
7. **Update ADR-0012** if any of the test text references "four new binaries" or specific phrasing — match the ADR (Rule 11). Verify the ADR-0012 §Decision text reads as expected; if it diverges, this story amends the ADR's exact wording before the AC-4 cross-document test can pass.
8. **Run the full gate**: `make check`, `make lint-imports`. Iterate until green.

## TDD plan — red / green / refactor

### Red — write the failing tests first

`tests/unit/exec/test_allowlist_phase3.py`:

```python
from __future__ import annotations
from pathlib import Path
from unittest import mock
import pytest

from codegenie.errors import DisallowedSubprocessError, ToolMissingError
from codegenie.exec import ALLOWED_BINARIES, run_allowlisted, _RUNNING_PROCS

NEW_BINARIES = {"npm", "bwrap", "sandbox-exec", "jq"}
PHASE2_BASELINE = {
    "git", "node", "semgrep", "syft", "grype", "gitleaks",
    "scip-typescript", "ast-grep", "ripgrep", "tree-sitter",
    "docker", "strace",
}
EXPECTED_TOTAL = PHASE2_BASELINE | NEW_BINARIES  # sixteen entries


# AC-1
def test_allowed_binaries_is_exact_sixteen_entry_set() -> None:
    assert ALLOWED_BINARIES == EXPECTED_TOTAL


# AC-2
def test_exec_module_docstring_phase3_present() -> None:
    import codegenie.exec as exec_module
    doc = exec_module.__doc__ or ""
    assert "03-ADR-0012" in doc, "Phase 3 ADR reference missing from exec docstring"


# AC-4 — ADR cross-document gate
def test_adr_0012_enumerates_all_new_binaries() -> None:
    adr = Path(
        "docs/phases/03-vuln-deterministic-recipe/ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md"
    )
    text = adr.read_text()
    for b in NEW_BINARIES:
        assert f"`{b}`" in text, f"{b!r} not enumerated in 03-ADR-0012"


# AC-5
@pytest.mark.parametrize("binary", sorted(NEW_BINARIES))
async def test_new_binary_not_rejected_by_allowlist(binary: str, tmp_path: Path) -> None:
    from codegenie.errors import ProbeTimeoutError
    try:
        await run_allowlisted([binary, "--version"], cwd=tmp_path, timeout_s=5.0)
    except DisallowedSubprocessError:
        pytest.fail(f"{binary!r} must be allowlisted; got DisallowedSubprocessError")
    except (ToolMissingError, ProbeTimeoutError, FileNotFoundError):
        pass


# AC-6 — path traversal
@pytest.mark.parametrize(
    "argv",
    [[f"/usr/bin/{b}", "--version"] for b in sorted(NEW_BINARIES)]
    + [[f"./{b}", "--version"] for b in sorted(NEW_BINARIES)],
)
async def test_new_binary_rejects_resolved_paths(
    argv: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    spy = mock.AsyncMock(side_effect=AssertionError("must not spawn"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    with pytest.raises(DisallowedSubprocessError):
        await run_allowlisted(argv, cwd=tmp_path, timeout_s=1.0)
    spy.assert_not_awaited()


# AC-7 — env-strip per new binary
@pytest.mark.parametrize("binary", ["npm", "jq"])
@pytest.mark.parametrize("sensitive_key", ["OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN"])
async def test_new_binary_env_strip(
    binary: str, sensitive_key: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio, structlog
    fake_proc = mock.MagicMock()
    fake_proc.pid = 1; fake_proc.returncode = 0
    fake_proc.communicate = mock.AsyncMock(return_value=(b"", b""))
    spy = mock.AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    with structlog.testing.capture_logs() as events:
        await run_allowlisted([binary, "--version"], cwd=tmp_path, timeout_s=5.0,
                              env_extra={sensitive_key: "leak"})
    assert sensitive_key not in spy.await_args.kwargs["env"]
    drops = [e for e in events if e.get("event") == "subproc.env_extra.sensitive_key_dropped"]
    assert any(e["key"] == sensitive_key for e in drops)


# AC-8 — weakref cleanup per new binary
@pytest.mark.parametrize("binary", sorted(NEW_BINARIES))
async def test_new_binary_running_procs_cleaned_up(binary: str, tmp_path: Path) -> None:
    from codegenie.errors import ProbeTimeoutError
    try:
        await run_allowlisted([binary, "--version"], cwd=tmp_path, timeout_s=5.0)
    except DisallowedSubprocessError:
        pytest.fail(f"{binary!r} must be allowlisted")
    except (ToolMissingError, ProbeTimeoutError, FileNotFoundError):
        pass
    assert len(_RUNNING_PROCS) == 0
```

`tests/unit/plugins/test_capabilities.py`:

```python
from __future__ import annotations
import inspect, pytest
from pydantic import ValidationError

from codegenie.plugins.capabilities import (
    CapabilityBundle, CapabilityScope, FsReadWriteCapability,
    GitLocalOpsCapability, NpmInstallCapability, mint,
)
from codegenie.types.identifiers import PluginId, RegistryUrl


# AC-11 — frozen + extra="forbid"
@pytest.mark.parametrize("cls", [NpmInstallCapability, FsReadWriteCapability, GitLocalOpsCapability])
def test_capability_frozen_and_forbid(cls: type) -> None:
    # Construction with surprise field rejected
    with pytest.raises(ValidationError):
        cls(surprise="x")  # type: ignore[call-arg]


# AC-12 — GitLocalOpsCapability has NO push field
def test_git_local_ops_has_no_push_field() -> None:
    assert "push" not in GitLocalOpsCapability.model_fields
    with pytest.raises(ValidationError):
        GitLocalOpsCapability(push=True)  # type: ignore[call-arg]


def test_git_local_ops_docstring_pins_no_push() -> None:
    doc = (GitLocalOpsCapability.__doc__ or "").lower()
    assert "no push field" in doc or "push field is absent" in doc
    assert "03-adr-0011" in doc or "adr-0011" in doc
    assert "adr-0009" in doc  # production "humans always merge"


# AC-13 — only mint() constructs capabilities
def test_only_mint_constructs_capabilities() -> None:
    import codegenie.plugins.capabilities as mod
    src = inspect.getsource(mod)
    mint_src = inspect.getsource(mod.mint)
    for name in ("NpmInstallCapability(", "FsReadWriteCapability(", "GitLocalOpsCapability("):
        outside_mint = src.replace(mint_src, "")
        assert name not in outside_mint, (
            f"{name!r} constructed outside mint() — only mint() may instantiate capabilities"
        )


# AC-14 — mint emits CapabilityMinted
def test_mint_emits_capability_minted(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict[str, object]] = []
    def fake_emit(event: object) -> None:  # noqa: ANN001
        captured.append({"event": event})
    monkeypatch.setattr(
        "codegenie.plugins.capabilities._emit_capability_minted", fake_emit
    )
    bundle = mint(
        plugin=PluginId("vulnerability-remediation--node--npm"),
        scope=CapabilityScope.npm(registry=RegistryUrl("https://registry.npmjs.org")),
    )
    assert isinstance(bundle, CapabilityBundle)
    assert len(captured) == 1
```

`tests/static/test_capability_fence.py`:

```python
from __future__ import annotations
from pathlib import Path

from tooling.ruff_rules.no_capability_construction import find_violations


def test_no_capability_construction_outside_chokepoint() -> None:
    roots = [Path("src"), Path("plugins")]
    violations = find_violations(roots)
    # capabilities.py and tests/** are permitted (excluded by walker)
    assert violations == [], f"capability constructions found: {violations!r}"


def test_walker_detects_synthesized_violation(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("from codegenie.plugins.capabilities import NpmInstallCapability\n"
                   "x = NpmInstallCapability(registry='https://x')\n")
    violations = find_violations([tmp_path])
    assert len(violations) == 1
    assert "NpmInstallCapability" in str(violations[0])
```

`tests/static/test_npm_ignore_scripts_cli_present.py`:

```python
from __future__ import annotations
import ast
from pathlib import Path
import pytest


def _find_npm_specs_missing_ignore_scripts(root: Path) -> list[tuple[Path, int]]:
    findings: list[tuple[Path, int]] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "JailedSubprocessSpec"):
                continue
            for kw in node.keywords:
                if kw.arg != "cmd": continue
                if not isinstance(kw.value, (ast.Tuple, ast.List)): continue
                tokens = [el.value for el in kw.value.elts if isinstance(el, ast.Constant)]
                if not tokens or tokens[0] != "npm": continue
                if not any(t in ("install", "test", "ci", "audit", "ls") for t in tokens):
                    continue
                if "--ignore-scripts" not in tokens:
                    findings.append((path, node.lineno))
    return findings


def test_every_npm_spec_includes_ignore_scripts() -> None:
    engines = Path("src/codegenie/transforms/engines")
    if not engines.exists() or not any(engines.rglob("*.py")):
        pytest.skip("Phase 3 npm engines not yet present (S5-02) — fence dormant")
    violations = _find_npm_specs_missing_ignore_scripts(engines)
    assert violations == [], (
        f"JailedSubprocessSpec with npm cmd missing --ignore-scripts: {violations!r}"
    )


def test_fence_detects_synthesized_violation(tmp_path: Path) -> None:
    bad = tmp_path / "bad_engine.py"
    bad.write_text(
        "from codegenie.transforms.sandbox_jail import JailedSubprocessSpec\n"
        "spec = JailedSubprocessSpec(cmd=('npm', 'install', '--package-lock-only'),\n"
        "                            cwd=None, env=None, network=None,\n"
        "                            time_budget_s=1.0, memory_mib=1, pids_max=1)\n"
    )
    violations = _find_npm_specs_missing_ignore_scripts(tmp_path)
    assert len(violations) == 1
```

Run — all RED (modules + amendment missing). Commit.

### Green — make it pass

1. Edit `src/codegenie/exec/__init__.py` to extend `ALLOWED_BINARIES` and update docstring + comment. Run allowlist tests — green.
2. Implement `src/codegenie/plugins/capabilities.py` per the outline. Run capability tests — green.
3. Implement `tooling/ruff_rules/no_capability_construction.py` (pure-Python AST walker). Run fence test — green (zero real violations; synthesized fixture detected).
4. Add `tests/static/test_npm_ignore_scripts_cli_present.py`. Run — green (skips since S5-02 not landed; synthesized violation detected).
5. Run `make check`, `make lint-imports`. Iterate until green.

### Refactor — clean up

- Surface the `bwrap` → `ALLOWED_BINARIES` polarity flip (Phase 2's closed-set test had `bwrap` in the negative list per S1-06 AC-15; Phase 3 flips it). The closed-set test in `tests/unit/test_exec.py` must lose `bwrap` AND `bubblewrap` (`bubblewrap` is the same tool; verify) with a one-line comment cross-referencing 03-ADR-0012.
- Add module docstring at `src/codegenie/plugins/capabilities.py` reciting ADR-0011's honest framing verbatim.
- `ruff format`, `mypy --strict`, full test suite.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/exec/__init__.py` | Extend `ALLOWED_BINARIES` to sixteen entries; update comment + docstring with 03-ADR-0012 cross-reference (AC-1, AC-2). |
| `src/codegenie/plugins/capabilities.py` | New: three capability Pydantic models + `CapabilityBundle` + `mint()` chokepoint + forward-shim `_emit_capability_minted` (AC-10..AC-14). |
| `tooling/ruff_rules/__init__.py` | New (or existing per codebase) — package init for custom rules. |
| `tooling/ruff_rules/no_capability_construction.py` | New: AST walker that flags any `*Capability(...)` outside `capabilities.py` and `tests/` (AC-15). |
| `tests/unit/exec/test_allowlist_phase3.py` | New (or extend Phase 2's file per precedent): AC-3..AC-9 amendment tests. |
| `tests/unit/test_exec.py` | Update `test_node_in_allowed_binaries` (or whatever the Phase 2 ratchet asserts the closed set) to the new sixteen-entry total; remove `bwrap`/`bubblewrap` from `test_allowed_binaries_closed_set_regression` parametrize with one-line cross-reference comment (AC-9). |
| `tests/unit/plugins/test_capabilities.py` | New: AC-10..AC-14. |
| `tests/static/test_capability_fence.py` | New: AC-15..AC-17 — runs the AST walker; asserts zero violations; verifies synthesized violation detected. |
| `tests/static/test_npm_ignore_scripts_cli_present.py` | New: AC-18..AC-19 — forward-looking fence on S5-02's call sites. |
| `Makefile` | If the custom ruff rule needs explicit `make` target wiring (verify against existing `make lint` / `make check`), add the rule invocation surgically (AC-17). |

## Out of scope

- **`SubprocessJail` Protocol** — S4-01.
- **`BwrapAdapter` / `SandboxExecAdapter`** — S4-02 / S4-03. This story makes their binaries allowlistable; it does NOT implement them.
- **`SandboxedPath`** — S4-04. Capabilities reference it as a scope type.
- **Real `CapabilityMinted` event sink** — S6-01 lands the two-stream `EventLog`. This story emits via a forward shim that becomes a no-op when the real sink is absent and a one-call invocation when present.
- **`PLUGINS.lock` integrity check + loader** — S2-03. This story does not touch plugin loading.
- **`OpenRewriteRecipeEngine` `--ignore-scripts` equivalent** — Phase 3's `OpenRewriteRecipeEngine` is scaffold-only (per ADR-0009); the `--ignore-scripts` fence covers npm engines (S5-02). When Phase 7 enables OpenRewrite for real, a sibling fence for JVM-side script execution is a separate Phase-7 story.
- **`java` in `ALLOWED_BINARIES`** — explicitly out per ADR-0012 §Decision: "`java` is NOT added in Phase 3 (the `OpenRewriteRecipeEngine` is scaffolded but not invoked by Phase-3 workflows per ADR-0009). Phase 7 amends to add `java`."
- **Postinstall canary adversarial test** — S8-04 (`@pytest.mark.phase03_adv`). This story lands the structural CLI-half fence; S8-04 lands the live-fixture regression.
- **Sigstore plugin signing** — Phase 11. ADR-0011 §Consequences flags this as the substitution target for `PLUGINS.lock`'s SHA-256 tree digest; out of scope here.

## Notes for the implementer

- **S1-06 is the structural template.** Read `docs/phases/02-context-gather-layers-b-g/stories/S1-06-allowed-binaries-extension.md` before starting — it's the precedent for the allowlist-amendment portion. Mirror its discipline: exact-equality test, ADR cross-document gate, env-strip per new binary, weakref cleanup per binary, path-traversal regression, closed-set negative-list update. Don't reinvent. The S1-06 attempt log records 16 ACs; this story is the smaller Phase 3 sibling with 4 new binaries → ~6 amendment-specific ACs plus 14 capability/fence ACs.
- **Single chokepoint preservation is non-negotiable.** Per ADR-0012 §Decision: "the `SubprocessJail` adapters wrap `bwrap` / `sandbox-exec` via `run_external_cli` — they do NOT bypass the chokepoint." The amendment does NOT create a `run_jailed` parallel path. S4-02 and S4-03 already call `run_external_cli`; this story just admits `bwrap` and `sandbox-exec` to the closed frozenset.
- **`bwrap` polarity flip — surface, don't hide.** Phase 2 S1-06 AC-15 likely added `bwrap` (and `bubblewrap` as alias) to `test_allowed_binaries_closed_set_regression`'s negative-list parametrize. Phase 3 flips: `bwrap` is now ALLOWED. The flip is correct (Phase 2's reasoning was "wrapper-pattern exception — bwrap is invoked from inside exec.py only"; Phase 3 needs `bwrap` callable from `BwrapAdapter`). Update the closed-set negative-list parametrize by REMOVING `bwrap` and `bubblewrap` with a one-line comment: `# bwrap removed by 03-ADR-0012 — now allowlisted for BwrapAdapter (Phase 3 S4-02)`. This is a *symmetric ratchet* per Rule 11 — the negative-list discipline survives even when polarity flips.
- **`GitLocalOpsCapability` has NO `push` field — type-impossible to mint.** ADR-0011 §Decision: "minting one is type-impossible. This IS a real type-level invariant for one specific operation (per ADR-0009 humans-always-merge)." AC-12 enforces structurally. A maintainer adding `push: bool = False` to the model is breaking the invariant; the test catches it. Document the invariant at the class docstring.
- **`mint()` is the ONLY chokepoint.** The AC-13 grep test enforces this at file level. The AC-15..AC-17 ruff fence enforces it repo-wide. Two layers: file-internal (mint() is the only constructor caller inside `capabilities.py`) and repo-wide (no other file in `src/` or `plugins/` constructs `*Capability` directly). Together they make accidental bypass require deliberate intent.
- **Custom ruff rule scaffolding — verify existing precedent first.** `grep -r "tooling/ruff_rules" .` and `grep -r "ast.walk" tests/` to check whether the codebase has an established AST-walker pattern (S1-05 likely does for `test_no_any_in_plugin_surface.py`). If yes, mirror it (Rule 11). The "custom ruff rule" framing in ADR-0011 may or may not be literally a ruff plugin — pure-Python AST walker invoked from a `tests/static/` test is the more likely realization given the codebase's Python-only discipline. The point is the AST-level enforcement, not the literal ruff-plugin packaging.
- **`--ignore-scripts` fence is forward-looking.** S5-02 lands the `NpmLockfileRecipeEngine` that's the fence's primary target. The fence ships before its target — when S5-02 lands, the fence wakes up structurally. AC-18 requires the dormant-skip to be loud (a warning, not a silent pass). AC-19 proves the fence is alive via a synthesized fixture.
- **`CapabilityMinted` event sink forward shim.** S6-01 lands the real `EventLog`. This story emits via `_emit_capability_minted(event)` — a module-level function defined inside `capabilities.py` that's a no-op when no sink is registered. When S6-01 lands, it monkey-patches (or otherwise wires) the real sink. Avoid creating a circular dep between `plugins/capabilities.py` and `plugins/events.py` — the forward shim resolves it cleanly. (S6-01's executor can wire the real sink at orchestrator init; this story's tests monkey-patch the shim.)
- **ADR-0012 text alignment.** AC-4's cross-document gate asserts each new binary is backtick-enumerated in the ADR. Read the ADR text first: §Decision should already say something like "Add `npm`, `bwrap`, `sandbox-exec`, `jq`." If the ADR's wording diverges from what the test asserts, amend the ADR's text first (then write the test pinning the now-correct wording). Don't write the test to match a wording that doesn't exist (Rule 7).
- **Effort sizing.** M is honest: the allowlist amendment is small (mirror S1-06), the capability module is medium (~150 LOC + Pydantic discipline), the ruff fence is small (~50 LOC AST walker + 30 LOC tests), the `--ignore-scripts` fence is small (~50 LOC AST walker). Total ~3-4 hours of focused work for an experienced implementer. If something blows up (e.g., the codebase has no `tooling/ruff_rules/` precedent and needs scaffolding), surface in attempt log and consider splitting capabilities + amendment + fence into separate sub-stories.
- **AC-9 cross-file ratchet** is the trickiest piece. Verify the Phase 2 closed-set test's current state before editing — it may have moved between Phase 2 and Phase 3 development. The ratchet rule: any binary that was structurally pinned as "never-allowlisted" but is now allowlisted MUST get a one-line ratchet-update comment with the ADR cross-reference. Silent removal defeats the audit trail.
