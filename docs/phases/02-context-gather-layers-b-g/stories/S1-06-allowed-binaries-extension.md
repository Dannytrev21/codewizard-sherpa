# Story S1-06 — `ALLOWED_BINARIES` eleven additions (ADR-0001)

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** HARDENED 2026-05-15 (phase-story-validator, Pass 1 + Pass 2)
**Effort:** S
**Depends on:** —
**ADRs honored:** 02-ADR-0001

## Validation notes (2026-05-15 — phase-story-validator)

Verdict: **HARDENED**. Two passes recorded on 2026-05-15. Full audit at [`_validation/S1-06-allowed-binaries-extension.md`](_validation/S1-06-allowed-binaries-extension.md).

### Pass 1 — three initial gaps patched

1. **Two existing Phase-1 tests pin the old closed-set `{git, node}` and will fail when this story lands.** The original story said "the literal definition site (one line) is the only change" (AC-1) — that's wrong. The Open/Closed regression guards must be updated, not deleted:
   - `tests/unit/test_exec.py::test_node_in_allowed_binaries` (line ~316) asserts `ALLOWED_BINARIES == frozenset({"git", "node"})`.
   - `tests/unit/probes/test_deployment.py::test_allowed_binaries_invariant_unchanged` (line ~591) asserts `ALLOWED_BINARIES == {"git", "node"}`.
   Both added to "Files to touch" and pinned by AC-9.
2. **AC-2's "file an ADR amendment if a reviewer flags the gap" was a deferral.** `ast-grep` and `ripgrep` are prescribed by this story but are not enumerated in 02-ADR-0001's table (which lists 8 named-trigger binaries; this story adds 10). The amendment is now mandatory under AC-10 (one-paragraph append + one table row each), not optional.
3. **TDD-plan test's exception swallow was too broad.** `except (ToolMissingError, Exception):` masks any regression that raises something unexpected. Narrowed to `except (ToolMissingError, FileNotFoundError, ProbeTimeoutError, RuntimeError):` with explicit per-exception comments. `DisallowedSubprocessError` remains the only exception the test *fails* on.

### Pass 2 — four-critic deep audit (Coverage / Test-Quality / Consistency / Design-Patterns)

The four-critic audit surfaced six additional real gaps (two block-tier, four harden-tier) that Pass 1 missed because it was a light-touch sanity-check. Closures:

- **AC-2 rewrite (Coverage F2, block).** Original AC-2 *still* contained the unverifiable prose ("named in 02-ADR-0001's table OR justified in Notes") that Pass 1 had only redirected through AC-10. The deferral language was preserved in the AC text itself, making it impossible for the executor's Ralph-Wiggum validator to verify. Rewritten as a pytest meta-test (`test_adr_0001_enumerates_all_new_binaries`) that opens `02-ADR-0001.md` after AC-10's amendment lands and asserts `EXPECTED_NEW_BINARIES ⊆ {entries-named-in-Decision-section}` plus substring presence of "ten new entries".
- **AC-11 (Coverage F3, block) — module docstring pin.** Implementation-outline step 2 demands a one-sentence docstring update; no AC asserted it. Mutant: forget the docstring → all tests pass. AC-11 adds `assert "02-ADR-0001" in codegenie.exec.__doc__` and `assert "ten Layer B/C/G tools" in codegenie.exec.__doc__`.
- **AC-12 (Test-Quality M2, harden) — env-strip per new binary.** AC-4's env-strip mock test calls `run_allowlisted(["git", "--version"], ...)` — proving env-strip works *for `git`*. A mutant that special-cases env handling for new binaries (`if binary in NEW: env = os.environ.copy()`) slips past. AC-12 parametrizes env-strip over `(binary, sensitive_key)` ∈ `{"docker", "semgrep"} × SENSITIVE_KEYS` and mirrors Phase 1's `test_node_invocation_env_extra_drops_sensitive_keys` precedent at `tests/unit/test_exec.py:370`.
- **AC-13 (Test-Quality M5, harden) — weakref-table cleanup per new binary.** Phase 0 / 1 family precedent pins `_RUNNING_PROCS` empty after every exit path (`tests/unit/test_exec.py:191, 209, 249, 465`). Original Test 3 (allowlist-acceptance, parametric over 10 new binaries) has no such pin. AC-13 adds the one-line assertion per case.
- **AC-14 (Test-Quality M11 + Coverage F6, harden) — path-traversal regression for new binaries.** Phase 0 Test 1 parametrizes `[/usr/bin/git, ./git]` as `DisallowedSubprocessError`. The 10 new binaries inherit this discipline structurally, but no AC pins it. A future regression that pre-resolves `argv[0]` via `shutil.which()` would silently break the discipline. AC-14 parametrizes over `[/usr/bin/{b}, ./{b}]` for the 10 new entries.
- **AC-15 (Design-Patterns F1 + Test-Quality M9, harden) — closed-set negative list extended with `bwrap`/`bubblewrap`.** Pass 1's AC-9 said "keep `test_allowed_binaries_closed_set_regression`'s parametrize list unchanged." That misses the structural pin for `bwrap`/`bubblewrap` — which Notes-for-implementer explicitly call out as the intentional wrapper-pattern exception. AC-15 extends the parametrize list with `["bwrap", "bubblewrap", "eval", "exec", "kill", "chmod", "chown", "dd", "nc"]`. This makes the wrapper-pattern policy structurally true at the test boundary.
- **AC-10 extended (Consistency F2/F3, harden).** Pass 1's AC-10 amends 02-ADR-0001 §Decision ("eight" → "ten") and adds `ast-grep` + `ripgrep`. Pass 2 extends AC-10 to also (a) update §Tradeoffs row 2 ("Eight new CVE feeds" → "Ten new CVE feeds") so the operational-hygiene consequence stays consistent, and (b) add a §Consequences bullet recording the `bwrap`-not-in-allowlist policy as a load-bearing decision rather than a story-internal Note that disappears after merge.
- **AC-16 (Coverage F5, harden) — `AWS_*` prefix-match coverage.** Original AC-4 listed three concrete `AWS_*` keys but didn't exercise the `_SENSITIVE_PREFIX` tuple path with an arbitrary `AWS_FOO`. Phase 0 Test 9 (`tests/unit/test_exec.py:283`) has this coverage for `git`; AC-16 carries it forward for one new binary.

### Notes-for-implementer additions (out-of-scope observations recorded for future)

- **Primitive obsession on `BinaryName` (Design-Patterns F2, nit).** The codebase has newtype discipline (production ADR-0033, applied in S1-05). Promoting `frozenset[str]` → `frozenset[BinaryName]` is premature; binary names cross zero module boundaries today. Recorded as a Notes paragraph only.
- **Rule-of-three for phase-batch-ADR tooling (Design-Patterns F3, nit).** Phase 0 + Phase 1 + Phase 2 is the third "phase-omnibus ADR + frozenset extension." Future tooling (precommit hook that fails if `git diff` touches `ALLOWED_BINARIES` without touching a `docs/phases/*/ADRs/*allowed-binaries*.md` file) belongs to a separate process-tooling story (likely S1-11 forbidden-patterns extension or new Phase 4). Recorded as a Notes paragraph only.
- **Patch-style consistency (Test-Quality M6, nit).** The new test file's `patch.object(_aio, "create_subprocess_exec", fake_exec)` is functionally correct but stylistically diverges from the eight existing precedents in `tests/unit/test_exec.py` (`monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)`). The executor should match the family convention (Rule 11).

Stage 3 (research) skipped on both passes — no `NEEDS RESEARCH` findings; everything was answerable from existing arch + production ADRs + Phase 0/1 test precedent + verified repo state.

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

- [ ] **AC-1.** `src/codegenie/exec.py` `ALLOWED_BINARIES` is `frozenset({"git", "node", "semgrep", "syft", "grype", "gitleaks", "scip-typescript", "ast-grep", "ripgrep", "tree-sitter", "docker", "strace"})` — exactly twelve entries; no others. The literal definition site in `exec.py` is one line; the only other code edits in this story are (a) the one-sentence Phase 2 docstring note inside `exec.py`, and (b) the two Phase-1 closed-set assertions called out in AC-9 — the Open/Closed regression guards that pin the *current* closed set against silent drift and so must move forward with the set.
- [ ] **AC-2.** A pytest meta-test (`test_adr_0001_enumerates_all_new_binaries` in `tests/unit/exec/test_allowed_binaries.py`) opens `docs/phases/02-context-gather-layers-b-g/ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md` and asserts:
  - The string `"ten new entries"` is present (Decision section), and the string `"eight new entries"` is **absent** (mutually exclusive after AC-10's amendment).
  - Each binary in `EXPECTED_NEW_BINARIES` (the ten new entries) appears literally as a backticked identifier in the file (`"`docker`"`, `"`ast-grep`"`, etc.). This is a structural cross-document gate — code-side additions cannot land without the matching ADR enumeration, which is the policy of 02-ADR-0001 ("a binary added to `ALLOWED_BINARIES` requires an ADR; the omnibus ADR's enumeration IS the audit trail"). Replaces the original prose deferral ("file an amendment if a reviewer flags the gap") with a pass/fail assertion the executor's Validator can run.
- [ ] **AC-3.** `_SENSITIVE_EXACT` and `_SENSITIVE_PREFIX` are **untouched** — the env strip defense is unchanged.
- [ ] **AC-4.** `tests/unit/exec/test_allowed_binaries.py` is a new test file (or an extension to an existing one) asserting:
  - Every entry in `ALLOWED_BINARIES` is in the expected set (no surprises).
  - The expected set is exactly twelve entries (no silent additions).
  - Calling `run_allowlisted([binary, "--version"], cwd=tmp_path, timeout_s=5.0)` for each of the ten new binaries either succeeds **or** raises `ToolMissingError` (the binary is not on `$PATH`) — but never `DisallowedSubprocessError`. (Note: this test SKIPS in environments where the binary isn't installed; we only care that the allowlist accepts it.)
  - The sensitive env strip continues to drop `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `SSH_AUTH_SOCK`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` from `env_extra` (parametrized; for each, calling with `env_extra={KEY: "leak"}` triggers the `subproc.env_extra.sensitive_key_dropped` structlog event and the child env never contains the key — verified by passing a tool that echoes env, OR by inspecting the env passed to a mocked `asyncio.create_subprocess_exec`).
- [ ] **AC-5.** Phase 0 `forbidden-patterns` pre-commit (catch direct `subprocess.run` / `asyncio.create_subprocess_exec` outside `exec.py`) continues to be green; this story does not add a second chokepoint.
- [ ] **AC-6.** The contract-freeze snapshot test for `exec.py`'s **signature** (if one exists; Phase 0 ADR-0012 likely shipped one) stays green — only the `ALLOWED_BINARIES` constant changes, not the `run_allowlisted` signature.
- [ ] **AC-7.** The TDD plan's red test exists, was committed, and is green.
- [ ] **AC-8.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/exec/ tests/unit/test_exec.py tests/unit/probes/test_deployment.py` all pass on the touched files. (The two pre-existing test files are pinned by AC-9; the new dir is the new test file from AC-4.)

- [ ] **AC-9.** The two pre-existing Phase-1 closed-set assertions are updated to reflect the new twelve-entry frozenset, *not deleted*:
  - `tests/unit/test_exec.py::test_node_in_allowed_binaries` — change the equality assertion from `frozenset({"git", "node"})` to the twelve-entry `EXPECTED_TOTAL`. Add a docstring sentence noting Phase 2 02-ADR-0001 as the governance ADR. **Keep `test_allowed_binaries_closed_set_regression`'s parametrize list (`["bash", "sh", "python", "curl", "wget", "ssh"]`) unchanged** — those six remain forbidden under the Phase-2 closed-set discipline.
  - `tests/unit/probes/test_deployment.py::test_allowed_binaries_invariant_unchanged` — rename to `test_allowed_binaries_invariant_phase2` (or equivalent forward-looking name) and update its equality assertion + docstring. The "AC-37 / Phase-1-end invariant" comment becomes "AC-37 / Phase-2-end invariant; 02-ADR-0001".
  - **Why:** these two tests are the Open/Closed regression guard described in `phase-arch-design.md §"Anti-patterns avoided"` ("silent expansion of ALLOWED_BINARIES"). Deleting them would weaken the discipline; freezing them at `{git, node}` would block this story. Updating them forward is the extension-by-addition path.

- [ ] **AC-10.** `docs/phases/02-context-gather-layers-b-g/ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md` is amended in this same story to enumerate `ast-grep` and `ripgrep` as Layer G named-trigger additions AND to record the `bwrap`-not-in-allowlist policy as a load-bearing consequence:
  - **Decision text:** "**eight new entries**: `docker`, `strace`, `semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, `tree-sitter`" → "**ten new entries**: `docker`, `strace`, `semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, `tree-sitter`, `ast-grep`, `ripgrep`". The named-trigger probes for the additions are `localv2.md §5.6 G2` (ast-grep — structural-pattern Layer G probe) and `localv2.md §5.6 G3` (ripgrep — curated literal-pattern Layer G probe). Both are referenced in `phase-arch-design.md §"Component design" #3 run_external_cli` (line 493) and `final-design.md §"Components" §3 _run_external_cli` (line 224).
  - **Tradeoffs row 2 update:** "Eight new CVE feeds to follow" → "Ten new CVE feeds to follow". Update the parenthetical to `(docker, syft, grype, gitleaks, semgrep, ast-grep, ripgrep, scip-typescript, tree-sitter, strace)`. The operational-hygiene consequence (number of feeds to watch) MUST stay consistent with the Decision count; otherwise the ADR contradicts itself in two places.
  - **New §Consequences bullet — `bwrap`/`bubblewrap` policy:** add one bullet — *"`bwrap`/`bubblewrap` is intentionally NOT in `ALLOWED_BINARIES`. `run_external_cli` (S1-07) invokes `bwrap` from inside `src/codegenie/exec.py` itself as a hardening wrapper over `argv`, not as a probe-callable tool. The structural defenses (`_filter_env` env-by-omission, no shell, `tests/adv/test_no_shell_true.py` single-file invariant) all apply because the invocation lives inside the chokepoint module. The closed-set guard in `tests/unit/test_exec.py::test_allowed_binaries_closed_set_regression` pins `bwrap` and `bubblewrap` to NOT be in `ALLOWED_BINARIES` (AC-15)."*  This converts the Notes-for-implementer paragraph into a recorded decision so the policy survives the merge.
  - **Why mandatory, not optional:** Pass 1's AC-10 already framed the amendment as mandatory because deferring it created code/ADR drift on landing. Pass 2 extends the amendment to close two more drift sources (CVE-feed count, `bwrap` policy) that would otherwise reappear as policy questions in future reviews.
  - `02-ADR-0001 §"Reversibility"` and `§"Pattern fit"` paragraphs are unchanged — the amendment only updates the count, the enumeration, the CVE-feed row, and adds one Consequences bullet.

- [ ] **AC-11. Module docstring pin.** `tests/unit/exec/test_allowed_binaries.py::test_exec_module_docstring_phase2_present` reads `codegenie.exec.__doc__` and asserts the substrings `"02-ADR-0001"` AND `"ten Layer B/C/G tools"` are both present. The docstring update from Implementation outline step 2 is a load-bearing audit-trail edit; without this assertion a wrong impl that lands the frozenset edit but forgets the docstring passes every original AC. (Family precedent: Phase 1 `tests/unit/test_exec.py:316` references ADR-0001 in test docstrings but never asserts it on the module docstring; Phase 2 tightens the rope.)

- [ ] **AC-12. Env-strip parametric extends to new binaries (Layer B/G + Layer C).** AC-4's env-strip mock test uses `["git", "--version"]` argv. AC-12 adds at least three parametric cases that exercise env-strip with `argv = ["docker", "--version"]` (Layer C representative) and `argv = ["semgrep", "--version"]` (Layer B/G representative) over a sample of sensitive keys (`OPENAI_API_KEY`, `AWS_SECRET_ACCESS_KEY`, `GITHUB_TOKEN`). Each must:
  - Show the sensitive key absent from the captured env.
  - Emit the `subproc.env_extra.sensitive_key_dropped` structlog event with `key=<the key>` and `log_level=warning`.
  - Family precedent: `tests/unit/test_exec.py:370 test_node_invocation_env_extra_drops_sensitive_keys`. Closes the "per-binary env-handling special-casing" mutant the original AC-4 missed.

- [ ] **AC-13. `_RUNNING_PROCS` weakref-table cleanup pinned per new binary.** The parametric allowlist-acceptance test (AC-4 third bullet) calls `run_allowlisted([binary, "--version"], ...)` for each of the 10 new binaries. AC-13 adds an assertion inside the parametric: `from codegenie.exec import _RUNNING_PROCS; assert len(_RUNNING_PROCS) == 0` after each call returns or raises. Family precedent: `tests/unit/test_exec.py:191, 209, 249, 465`. Closes the "skip the `finally:` pop for new binaries" mutant; protects Phase 7's coordinator-cancel pathway.

- [ ] **AC-14. Path-traversal regression for the ten new binaries.** `tests/unit/exec/test_allowed_binaries.py::test_new_binaries_reject_resolved_paths` parametrizes over `[(f"/usr/bin/{b}", b) for b in EXPECTED_NEW_BINARIES] + [(f"./{b}", b) for b in EXPECTED_NEW_BINARIES]` (20 cases) and asserts each raises `DisallowedSubprocessError`. The bare-binary-name discipline is structurally inherited from Phase 0 `tests/unit/test_exec.py:34-43`; AC-14 makes the inheritance explicit so a regression that pre-resolves `argv[0]` via `shutil.which()` is caught by CI. The test spies `asyncio.create_subprocess_exec` to confirm `DisallowedSubprocessError` fires *before* any spawn (Phase 0 invariant 1).

- [ ] **AC-15. Closed-set negative-list parametrize is extended (supersedes AC-9 "unchanged" instruction).** `tests/unit/test_exec.py::test_allowed_binaries_closed_set_regression` (line 327) parametrize list is **extended additively** with `["bwrap", "bubblewrap", "eval", "exec", "kill", "chmod", "chown", "dd", "nc"]`. The original six (`bash`, `sh`, `python`, `curl`, `wget`, `ssh`) stay. The test docstring gains one sentence: *"`bwrap`/`bubblewrap` is the wrapper-pattern exception (02-ADR-0001 §Consequences). The other seven are adjacent dangerous binaries Phase 2 calls out as never-allowlisted."* This converts AC-9's "keep the parametrize list unchanged" into the right call given Notes-for-implementer §3 documents `bwrap` as intentionally absent. The negative-list test IS the structural enforcement that the registry stays closed.

- [ ] **AC-16. `AWS_*` prefix-match coverage on a new binary.** AC-4's env-strip parametric covers concrete `AWS_*` keys (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`) but does not exercise the `_SENSITIVE_PREFIX` *tuple* path with an arbitrary `AWS_FOO`. AC-16 adds one parametric case (`binary="docker"`, `sensitive_key="AWS_FOO"`) that asserts the key is dropped from the captured env AND emits the `subproc.env_extra.sensitive_key_dropped` structlog event. Family precedent: `tests/unit/test_exec.py:283 test_env_extra_drops_sensitive_keys` exercises `AWS_FOO` for `git`; AC-16 carries the prefix-match coverage forward for new binaries.

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
    from codegenie.errors import ProbeTimeoutError

    try:
        await run_allowlisted([binary, "--version"], cwd=tmp_path, timeout_s=5.0)
    except DisallowedSubprocessError:
        pytest.fail(f"{binary!r} must be allowlisted; got DisallowedSubprocessError")
    except ToolMissingError:
        pass  # binary not installed in this environment — expected on dev/CI
    except ProbeTimeoutError:
        pass  # rare: `--version` ran past 5s; allowlist is still proven open
    except FileNotFoundError:
        pass  # asyncio.create_subprocess_exec spawn-time miss; equivalent to ToolMissingError
    # Any other exception type is a real regression — let it propagate to fail the test.


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


# ── AC-11: module docstring pin ─────────────────────────────────────────────
def test_exec_module_docstring_phase2_present() -> None:
    """AC-11 — the Phase-2 audit-trail docstring update is in place. Catches
    the mutant that lands the frozenset edit but forgets the docstring."""
    import codegenie.exec as exec_module
    doc = exec_module.__doc__ or ""
    assert "02-ADR-0001" in doc, "Phase 2 ADR reference missing from exec module docstring"
    assert "ten Layer B/C/G tools" in doc, "Phase 2 enumeration phrase missing"


# ── AC-2: ADR cross-document gate ───────────────────────────────────────────
def test_adr_0001_enumerates_all_new_binaries() -> None:
    """AC-2 — the omnibus ADR's Decision section enumerates exactly the new
    set. This is the structural cross-document gate: code-side additions
    cannot land without the matching ADR enumeration (02-ADR-0001's policy)."""
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[3]
    adr = repo_root / "docs/phases/02-context-gather-layers-b-g/ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md"
    text = adr.read_text()
    assert "ten new entries" in text, "ADR must say 'ten new entries' after AC-10's amendment"
    assert "eight new entries" not in text, "ADR still says 'eight' — AC-10's amendment missing"
    for b in EXPECTED_NEW_BINARIES:
        assert f"`{b}`" in text, f"binary {b!r} not enumerated in 02-ADR-0001"


# ── AC-12: env-strip per-new-binary (Layer B/G + Layer C representatives) ───
@pytest.mark.parametrize("binary", ["docker", "semgrep"])
@pytest.mark.parametrize("sensitive_key", [
    "OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN",
])
async def test_new_binary_env_strip(
    binary: str,
    sensitive_key: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-12 — env-strip continues to fire when argv is a new (non-git)
    binary. Catches the mutant: `if binary in NEW: env = os.environ.copy()`.
    Style matches the eight precedents in tests/unit/test_exec.py via
    monkeypatch.setattr (Rule 11)."""
    import asyncio
    import structlog
    from unittest import mock

    fake_proc = mock.MagicMock()
    fake_proc.pid = 55555
    fake_proc.returncode = 0
    fake_proc.communicate = mock.AsyncMock(return_value=(b"", b""))
    spy = mock.AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)

    with structlog.testing.capture_logs() as captured_events:
        await run_allowlisted(
            [binary, "--version"],
            cwd=tmp_path,
            timeout_s=5.0,
            env_extra={sensitive_key: "leak"},
        )

    captured_env = spy.await_args.kwargs["env"]
    assert sensitive_key not in captured_env, (
        f"{sensitive_key} leaked through env_extra for binary={binary!r}"
    )
    drop_events = [
        e for e in captured_events
        if e.get("event") == "subproc.env_extra.sensitive_key_dropped"
    ]
    assert any(e["key"] == sensitive_key for e in drop_events), (
        f"structlog drop event missing for {sensitive_key!r}"
    )


# ── AC-13: _RUNNING_PROCS cleanup per new binary ────────────────────────────
@pytest.mark.parametrize("binary", sorted(EXPECTED_NEW_BINARIES))
async def test_new_binary_running_procs_cleaned_up(
    binary: str, tmp_path: Path,
) -> None:
    """AC-13 — every exit path of run_allowlisted pops the weakref entry.
    Catches the mutant: `if binary in NEW: skip the finally:` pop."""
    from codegenie.errors import ProbeTimeoutError
    from codegenie.exec import _RUNNING_PROCS

    try:
        await run_allowlisted([binary, "--version"], cwd=tmp_path, timeout_s=5.0)
    except (DisallowedSubprocessError,):
        pytest.fail(f"{binary!r} must be allowlisted")
    except (ToolMissingError, ProbeTimeoutError, FileNotFoundError):
        pass  # any reachable exit path
    assert len(_RUNNING_PROCS) == 0, f"weakref leak after {binary!r} call"


# ── AC-14: path-traversal regression for new binaries ───────────────────────
@pytest.mark.parametrize(
    "argv",
    [[f"/usr/bin/{b}", "--version"] for b in sorted(EXPECTED_NEW_BINARIES)]
    + [[f"./{b}", "--version"] for b in sorted(EXPECTED_NEW_BINARIES)],
)
async def test_new_binary_rejects_resolved_paths(
    argv: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-14 — bare-binary-name discipline inherited from Phase 0 (test_exec.py
    line 34-43). DisallowedSubprocessError must fire BEFORE any spawn."""
    import asyncio
    from unittest import mock
    spy = mock.AsyncMock(side_effect=AssertionError("must not spawn"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    with pytest.raises(DisallowedSubprocessError):
        await run_allowlisted(argv, cwd=tmp_path, timeout_s=1.0)
    spy.assert_not_awaited()


# ── AC-16: AWS_* prefix-match coverage on a new binary ──────────────────────
async def test_new_binary_aws_prefix_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-16 — the _SENSITIVE_PREFIX tuple path (`AWS_*`) drops an arbitrary
    AWS_FOO key when argv is a new binary. Family precedent:
    tests/unit/test_exec.py:283 exercises AWS_FOO for git."""
    import asyncio
    import structlog
    from unittest import mock

    fake_proc = mock.MagicMock()
    fake_proc.pid = 44444
    fake_proc.returncode = 0
    fake_proc.communicate = mock.AsyncMock(return_value=(b"", b""))
    spy = mock.AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)

    with structlog.testing.capture_logs() as captured_events:
        await run_allowlisted(
            ["docker", "--version"],
            cwd=tmp_path,
            timeout_s=5.0,
            env_extra={"AWS_FOO": "leak", "NODE_OPTIONS": "--no-warnings"},
        )

    captured_env = spy.await_args.kwargs["env"]
    assert "AWS_FOO" not in captured_env  # prefix-match dropped it
    assert captured_env.get("NODE_OPTIONS") == "--no-warnings"  # legitimate extra survives
    drop_events = [
        e for e in captured_events
        if e.get("event") == "subproc.env_extra.sensitive_key_dropped"
    ]
    assert {e["key"] for e in drop_events} == {"AWS_FOO"}
```

### Companion edit — `tests/unit/test_exec.py` (AC-15: extend the closed-set negative list)

In `tests/unit/test_exec.py::test_allowed_binaries_closed_set_regression` (line 327), extend the parametrize list **additively** with the Phase-2 negative entries:

```python
@pytest.mark.parametrize(
    "denied",
    # Phase 1 originals — adjacent dangerous interpreters/clients
    ["bash", "sh", "python", "curl", "wget", "ssh",
     # Phase 2 additions — wrapper-pattern exceptions and adjacent
     # dangerous binaries 02-ADR-0001 §Consequences pins as never-allowlisted.
     "bwrap", "bubblewrap", "eval", "exec", "kill", "chmod", "chown", "dd", "nc"],
)
def test_allowed_binaries_closed_set_regression(denied: str) -> None:
    """Open/Closed regression: any of these binaries appearing in
    ALLOWED_BINARIES is a structural break. `bwrap`/`bubblewrap` are the
    wrapper-pattern exception (02-ADR-0001 §Consequences) — they are
    intentionally invoked from inside exec.py only, not allowlisted.
    """
    from codegenie.exec import ALLOWED_BINARIES
    assert denied not in ALLOWED_BINARIES
```

Run — the AC-1, AC-2, AC-11 tests fail (ADR not yet amended; frozenset still `{git, node}`; docstring not updated). The closed-set extension tests pass (the binaries weren't and aren't in `ALLOWED_BINARIES`). Commit.

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
| `src/codegenie/exec.py` | One-line edit: extend `ALLOWED_BINARIES` to twelve entries; one-sentence Phase-2 docstring note (AC-1, AC-11). |
| `tests/unit/exec/test_allowed_binaries.py` | New test file. Tests for AC-1, AC-2 (ADR cross-document gate), AC-3, AC-4, AC-11 (docstring), AC-12 (env-strip per new binary), AC-13 (weakref cleanup per new binary), AC-14 (path-traversal regression for new binaries), AC-16 (`AWS_*` prefix on new binary). |
| `tests/unit/test_exec.py` | Update `test_node_in_allowed_binaries` to assert the twelve-entry set (AC-9). **Extend** `test_allowed_binaries_closed_set_regression` parametrize list with `["bwrap", "bubblewrap", "eval", "exec", "kill", "chmod", "chown", "dd", "nc"]` (AC-15, supersedes AC-9's "unchanged" instruction). |
| `tests/unit/probes/test_deployment.py` | Update `test_allowed_binaries_invariant_unchanged` → `test_allowed_binaries_invariant_phase2` with new equality and Phase-2-end-invariant docstring (AC-9). |
| `docs/phases/02-context-gather-layers-b-g/ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md` | Amend §Decision: "eight" → "ten new entries"; add `ast-grep`/`ripgrep`. Amend §Tradeoffs row 2: "Eight new CVE feeds" → "Ten new CVE feeds". Add §Consequences bullet recording the `bwrap`-not-in-allowlist wrapper-pattern exception (AC-10). |

## Out of scope

- **`run_external_cli` wrapper** — handled by S1-07; this story only extends the allowlist `run_external_cli` will rely on.
- **The Phase 2 ADRs** — handled by S1-11 (all nine ADRs land together).
- **Tool-readiness check edits in `cli.py`** — `localv2.md §6` install-command messages for missing tools land in S8-02/S8-03 alongside the CLI summary line. This story is allowlist-only.
- **`docker run --network=none --cap-drop=ALL --security-opt=no-new-privileges` flag enforcement** — those are per-call-site flags supplied by `RuntimeTraceProbe` (S5-02). The allowlist accepts the binary; the hardening is the caller's responsibility (02-ADR-0001 §Tradeoffs row 3).
- **`bubblewrap`/`bwrap` addition** — `bwrap` is **not** added to `ALLOWED_BINARIES`. `run_external_cli` (S1-07) invokes `bwrap` directly from inside `src/codegenie/exec.py` because it's a hardening wrapper around `argv`, not a tool the probe-side authors call. The wrapper-pattern exception is now recorded as a §Consequences bullet in 02-ADR-0001 (per AC-10) and structurally pinned by `tests/unit/test_exec.py::test_allowed_binaries_closed_set_regression` (per AC-15).

## Notes for the implementer

- **Frozenset literal is the entire change.** Resist refactoring `exec.py` (Rule 3 — Surgical Changes). The module is Phase 0 chokepoint; surgical means one-line.
- **Count discipline.** The manifest says "eleven additions"; 02-ADR-0001's table lists eight (becomes ten after AC-10's amendment); the final frozenset has twelve entries (10 new + `git` + `node`). The test pins the *expected total set* explicitly (`EXPECTED_TOTAL`); the discrepancy between "eleven" (likely "eleven binaries beyond Phase 0's original `{git}`") and "ten" (added in Phase 2) is documentation drift — the test is the source of truth on disk.
- **`bwrap` is NOT in the allowlist (now structurally enforced).** AC-15 extends the closed-set negative-list regression with `["bwrap", "bubblewrap", ...]`; AC-10 records the wrapper-pattern exception in 02-ADR-0001 §Consequences. The policy is now load-bearing at three locations: the ADR text, the regression test, and the chokepoint's frozenset literal. A future contributor who tries to add `bwrap` to `ALLOWED_BINARIES` will trip AC-15 and AC-1's exact-equality simultaneously.
- **Allowlist-acceptance test handles missing tools gracefully.** `strace` on macOS, `gitleaks` on a dev workstation that hasn't installed it — both raise `ToolMissingError`. The test only asserts the *allowlist* accepts the binary (`DisallowedSubprocessError` is never raised). Do not require `--version` to succeed; do not skip with `pytest.skip` based on `shutil.which` (the test would lie about CI coverage). Validator-narrowed exception set: `(ToolMissingError, ProbeTimeoutError, FileNotFoundError)` — `Exception` was too broad.
- **Env-strip test style — match the family (Rule 11).** The validator's Test-Quality critic (M6) noted the original draft used `with patch.object(_aio, "create_subprocess_exec", fake_exec):` while the eight existing precedents in `tests/unit/test_exec.py` use `monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)`. The AC-12 / AC-16 tests in the TDD plan use `monkeypatch.setattr`. Keep that style. Both forms are functionally correct; the precedent wins.
- **`tests/adv/test_no_shell_true.py` (Phase 0 S4-05) still holds.** That test asserts no file under `src/codegenie/` other than `exec.py` imports `asyncio.create_subprocess_exec` or `subprocess.run`. This story does not introduce a second site; S1-07's `run_external_cli` lives in `exec.py`.

### Design-pattern observations (out of scope for S1-06 — recorded for future)

- **`BinaryName` newtype is premature (Design-Patterns F2, nit).** The codebase has newtype discipline for domain primitives (production ADR-0033, applied in S1-05 to `IndexId`/`SkillId`/etc.). Promoting `ALLOWED_BINARIES: frozenset[str]` → `frozenset[BinaryName]` would force every probe to wrap `BinaryName("docker")` for zero current safety gain — binary names cross zero module boundaries today (`run_allowlisted` reads `argv[0]` as `str`; callers pass `list[str]`). Per Rule 2 (Simplicity First) and Rule 3 (Surgical Changes), do NOT introduce a newtype in this story. If a future phase adds per-binary metadata (hardening flags, layer, named-trigger probe), promote `ALLOWED_BINARIES` to `Mapping[BinaryName, BinaryEntry]` where `BinaryEntry` is a frozen dataclass — but only when that's the third caller, not before.

- **Rule-of-three for phase-batch-ADR tooling (Design-Patterns F3, out-of-scope observation).** Phase 0 + Phase 1 + Phase 2 is the third "phase-omnibus ADR + frozenset extension" — the rule-of-three threshold for tooling. A precommit hook that fails if `git diff` touches `ALLOWED_BINARIES` in `exec.py` without also touching a `docs/phases/*/ADRs/*allowed-binaries*.md` file would convert the social-contract policy ("a binary added to `ALLOWED_BINARIES` requires an ADR") into a structural guard. This is **not** in scope for S1-06 — file under a future S1-11 (forbidden-patterns extension) or Phase 4 (tooling-vs-LLM hardening) story. Recorded so the executor doesn't bundle it.

- **Registry pattern hygiene confirmed (Design-Patterns D3, no action).** Per the design-patterns toolkit cited in 02-ADR-0001 §"Pattern fit": "a registry that does more than registration — eager validation, side effects, cross-references at registration time — is the failure mode." `ALLOWED_BINARIES = frozenset({...})` is the simplest possible shape and passes the bar. The chokepoint reads it as `binary in ALLOWED_BINARIES` and that's the entire interface. No structural change needed.
