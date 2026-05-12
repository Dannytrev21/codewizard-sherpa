# Story S1-06 — `run_in_sandbox` `test_execution=True` overlay flag

**Step:** Step 1 — Plant the two ABCs, the four Phase 0/1/2 additive edits, and the foundations every Phase 3 component consumes
**Status:** Ready
**Effort:** M
**Depends on:** S1-05
**ADRs honored:** ADR-0005

## Context

Phase 3's Stage 6 validation gate runs `npm ci` + `npm test` + opt-in `npm run build` inside the Phase-2 sandbox chokepoint. The test command **runs scripts by definition** (Jest hooks, mocha `before*`, etc.) and needs a writable `/work` overlay for tmp output — neither of which the Phase-2 `--ignore-scripts ON, read-only bind` posture allows. ADR-0005 resolves this by adding one new keyword argument to `run_in_sandbox`: `test_execution: bool = False`. When `True`, the bwrap/sandbox-exec profile composes (a) a writable upper-layer overlay over `/work`, (b) larger PID and wall-clock budgets (1024 PIDs / 600 s wall vs. Phase-2 default), (c) suspended wrapper-level `--ignore-scripts` enforcement (the test command itself runs scripts), and (d) `--network=none` remaining the default (not a hard wall — the operator opts in via `--allow-test-network` and `gate.signal_escalate` exposes the choice).

This is the **single** Phase-2-chokepoint amendment Phase 3 makes. Every other Phase 3 component goes through this chokepoint; if the overlay edit breaks Phase 2's existing tests, the whole phase blocks. The story's load-bearing artifact is the allowed-keyword-set enforcement (parity with Phase 2's snapshot-attribute discipline) so a fourth network keyword cannot slip in via a future "while we're here" edit. Linux `bwrap` and macOS `sandbox-exec` get parity; macOS is documented as "best-effort" per Phase 2 precedent.

## References — where to look

- **Architecture:** `../phase-arch-design.md §"Component design" #11 (ValidationGate)` — install_validator and test_validator profiles; the signal-escalate flow.
- **Architecture:** `../phase-arch-design.md §"Physical view" → "Sand" subgraph` — the overlay composition (writable upper for /work; larger pid/wall budgets; --ignore-scripts off only for npm test).
- **Architecture:** `../phase-arch-design.md §"Harness engineering" → "Determinism"` — the keyword-set invariant (no silent network-keyword expansion).
- **Phase ADRs:** `../ADRs/0005-single-sandbox-profile-test-execution-overlay-signal-escalate.md` — ADR-0005 — full decision rationale, signature, network-required signature scan (the signature-scan logic itself lives in S4-*, not this story).
- **Phase 2 ADRs:** `../../02-context-gather-layers-b-g/ADRs/0003-subprocess-sandbox-profile-extension.md` — Phase 2's `run_in_sandbox` chokepoint that this story extends.
- **Production ADRs:** `../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md` — Phase 5's microVM target; the `test_execution` overlay translates to microVM resource caps without changing the call signature.
- **Source design:** `../final-design.md §"Roadmap coherence check" §"Prior phases"` — the Phase 2 commitment surfaced here; if Phase 2's bwrap profile cannot host a writable overlay, this story blocks.
- **Existing code:** `src/codegenie/exec.py` `run_in_sandbox` — the chokepoint function. Phase 2 ADR-0003's profile assembly logic.

## Goal

Add a `test_execution: bool = False` keyword-only parameter to `run_in_sandbox` (`src/codegenie/exec.py`); when `True`, compose the overlay profile (writable `/work` upper layer, 1024-PID and 600-s budgets, suspended wrapper-level `--ignore-scripts` enforcement, `--network=none` default) on both Linux (`bwrap`) and macOS (`sandbox-exec`); when `False`, behavior is byte-identical to Phase 2; pin every behavior with unit tests and pin the allowed-keyword-set so a fourth network keyword cannot slip in unnoticed.

## Acceptance criteria

- [ ] `run_in_sandbox` signature in `src/codegenie/exec.py` gains a keyword-only `test_execution: bool = False` parameter. All Phase 2 + Phase 1 callers continue to compile and pass with their existing arguments (default behavior unchanged).
- [ ] When `test_execution=False`, the assembled subprocess command (bwrap `argv` on Linux; sandbox-exec rules on macOS) is byte-identical to Phase 2 — a regression test pins this by capturing the Phase-2 `argv` for a representative call and asserting equality post-edit.
- [ ] When `test_execution=True` on Linux, the bwrap `argv` includes:
  - `--tmpfs /work-overlay-upper` (or implementation-equivalent writable upper layer over `/work`)
  - `--ro-bind` on the original repo paths preserved (read-only base layer)
  - PID limit raised to 1024 (cgroup or `--unshare-pid` + ulimit; mirror Phase 2's idiom)
  - Wall-clock budget raised to 600 s
  - `--unshare-net` (or equivalent `--network=none` enforcement) preserved as default
  - `--ignore-scripts` **not** injected by the wrapper (callers pass the test command itself, which is allowed to run scripts)
- [ ] When `test_execution=True` on macOS, the sandbox-exec profile reflects parity at best-effort granularity — writable overlay simulated via tmpfs-equivalent (`/tmp` redirection) and the `(deny network*)` rule preserved. The macOS branch is documented as "best-effort" per Phase 2 precedent.
- [ ] **Keyword-set invariant.** A new module-private `_ALLOWED_KEYWORDS: frozenset[str]` (or equivalent assertion) lists the exact set of keyword arguments `run_in_sandbox` accepts — Phase 2's set + `test_execution`. A unit test inspects `inspect.signature(run_in_sandbox).parameters` and asserts it equals the pinned set; this catches a future "while we're here" addition of a fourth network keyword (the `network` parameter's `Literal["none","scoped"]` is unchanged in this story).
- [ ] `tests/unit/exec/test_test_execution_overlay.py` covers (Linux branch; macOS branch via `sys.platform` skip): (a) `test_execution=True` raises PID/wall budgets to 1024/600 s; (b) writable overlay is composed; (c) `--ignore-scripts` is not injected; (d) `--network=none` remains the default; (e) `test_execution=False` is byte-identical to Phase 2.
- [ ] `tests/unit/exec/test_run_in_sandbox_keyword_invariant.py` pins the allowed-keyword set.
- [ ] The Phase 2 `tests/adv/test_phase2_sandbox_*` tests continue green (no regression).
- [ ] No edits to `ALLOWED_BINARIES` (that was S1-05).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/exec.py tests/unit/exec/`.

## Implementation outline

1. Read `src/codegenie/exec.py`'s `run_in_sandbox` end-to-end — Rule 8. Identify (a) the Phase-2 keyword set, (b) the bwrap `argv` assembly site (Linux), (c) the sandbox-exec profile assembly site (macOS), (d) where PID/wall budgets are set.
2. Write `tests/unit/exec/test_test_execution_overlay.py` red — `test_execution=True` is not yet a recognized keyword; `TypeError` on call.
3. Write `tests/unit/exec/test_run_in_sandbox_keyword_invariant.py` red — the pinned keyword set does not yet include `test_execution`.
4. Add the keyword-only `test_execution: bool = False` to the function signature. Update `_ALLOWED_KEYWORDS` (or equivalent invariant) to include it.
5. Branch the bwrap profile assembly: when `test_execution=True`, append the overlay flags and bump the PID/wall budgets. Keep the Phase-2 path untouched for `test_execution=False`.
6. Branch the sandbox-exec profile (macOS): same idea, simulated with `/tmp` redirection or equivalent. Document the best-effort posture inline.
7. Suspend the wrapper-level `--ignore-scripts` injection when `test_execution=True`. The wrapper-level guard that raises `NpmScriptsEnabled` (the typed exception from S1-01) is only active when `test_execution=False`. Document this with a one-line comment citing ADR-0005.
8. Run `pytest tests/unit/exec/ tests/adv/test_phase2_sandbox_*.py`; green.

## TDD plan — red / green / refactor

### Red — failing test first

Test file paths: `tests/unit/exec/test_test_execution_overlay.py`, `tests/unit/exec/test_run_in_sandbox_keyword_invariant.py`.

```python
# tests/unit/exec/test_test_execution_overlay.py
import sys
import pytest
from codegenie.exec import run_in_sandbox, _build_sandbox_argv  # symbol name may differ

@pytest.mark.skipif(sys.platform != "linux", reason="bwrap profile is Linux-only path")
def test_test_execution_true_composes_writable_overlay_on_linux():
    argv = _build_sandbox_argv(
        argv=["bash", "-c", "echo hi"], allowlist=[], env={},
        timeout_s=600, cwd="/work", network="none", test_execution=True,
    )
    assert any("overlay" in a or "tmpfs" in a for a in argv)  # exact spelling per impl

def test_test_execution_true_raises_pid_and_wall_budgets():
    # PID limit -> 1024; wall -> 600 s; assert from the resolved limits dict
    ...

def test_test_execution_true_does_not_inject_ignore_scripts():
    # The test command runs scripts by definition; the wrapper guard is suspended
    argv = _build_sandbox_argv(..., test_execution=True)
    assert "--ignore-scripts" not in argv  # only when test_execution=True; the caller wraps npm test directly

def test_test_execution_true_keeps_network_none_default():
    argv = _build_sandbox_argv(..., test_execution=True)  # network defaults to "none"
    # bwrap: --unshare-net present; sandbox-exec: (deny network*) present
    ...

def test_test_execution_false_byte_identical_to_phase2():
    # Capture the Phase 2 argv for a canonical call shape and assert equality
    ...
```

```python
# tests/unit/exec/test_run_in_sandbox_keyword_invariant.py
import inspect
from codegenie.exec import run_in_sandbox

# Pinned set: Phase 2 keywords + test_execution. Anything else => CI red.
EXPECTED_KW = {
    "argv", "allowlist", "env", "timeout_s", "cwd", "network",
    "test_execution",
    # ... any other Phase-2 keyword names; capture verbatim
}

def test_run_in_sandbox_accepts_exactly_the_pinned_keyword_set():
    actual = set(inspect.signature(run_in_sandbox).parameters)
    assert actual == EXPECTED_KW, (
        f"run_in_sandbox keyword set drifted: expected {EXPECTED_KW}, got {actual}. "
        "Any new keyword requires an ADR amendment."
    )
```

Run; commit red.

### Green — make it pass

- Add `test_execution: bool = False` keyword-only to the signature.
- In the bwrap branch, `if test_execution:` add the overlay flags + bump the budgets. Keep Phase 2's logic untouched in the else branch.
- In the sandbox-exec branch, simulate the overlay via tmpfs redirection (mirror Phase 2's macOS idiom).
- Suspend wrapper-level `--ignore-scripts` when `test_execution=True`. The wrapper guard module (`tools/npm.py` in Step 3) reads `test_execution` from kwargs and skips raising `NpmScriptsEnabled` when `True`.
- Update `_ALLOWED_KEYWORDS` (or equivalent) to include `"test_execution"`.

### Refactor — clean up

- Module docstring on `exec.py`: append "Phase 3 — ADR-0005 — `test_execution=True` overlay flag for the validation gate's test-runner profile."
- One-line comment above the overlay branch: `# ADR-0005: writable upper layer + larger budgets; --network=none default preserved.`
- Confirm `mypy --strict` is clean; `test_execution: bool` reads correctly through the call chain.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/exec.py` | Add `test_execution: bool = False` keyword; branch bwrap + sandbox-exec profile assembly |
| `tests/unit/exec/test_test_execution_overlay.py` | New tests pinning every overlay behavior |
| `tests/unit/exec/test_run_in_sandbox_keyword_invariant.py` | Pinned keyword-set invariant |

## Out of scope

- **Network-required test signature scan** (`ENOTFOUND`, `ECONNREFUSED`, etc.) and the `gate.signal_escalate` audit event emission — both live in `transforms/validation/test.py` (Step 4) and `transforms/validation/network_signatures.py`. This story plants only the overlay flag; the validator code that reads it lives later.
- **`--allow-test-network` CLI flag** — the operator opt-in flag lands with the `codegenie remediate` body in Step 5. This story does not add CLI surface.
- **`network="scoped"` allowlist for tests** — implied by `--allow-test-network`; Step 4 wires the validator to call `run_in_sandbox(network="scoped", allowlist=[...], test_execution=True)` when the operator opts in.
- **`tools/npm.py` wrapper-guard that raises `NpmScriptsEnabled`** — Step 3 (`tools/npm.py` story). This story ensures the wrapper-level injection is suspended when `test_execution=True`, but the wrapper itself lives later.
- **macOS overlay parity beyond best-effort** — Phase 2 ADR-0003 already documents macOS as best-effort; this story does not tighten that posture.
- **Phase 5's microVM promotion** — `test_execution` translates to microVM resource caps without changing the call signature; that work is Phase 5.

## Notes for the implementer

- **The keyword-set invariant test is the load-bearing safeguard.** Without it, a future "while we're here" PR could add `network="scoped_dns_only"` or `allow_root=True` or similar and silently weaken the chokepoint. The pinned set forces an ADR amendment for any addition. Reuse the spelling from Phase 2's sandbox-attribute discipline (`Phase 2 ADR-0008`'s closed-enum CI lint precedent — this is the in-process equivalent).
- **Byte-identical regression for `test_execution=False`.** Capture the Phase-2 argv for at least three canonical call shapes (install_validator-shaped, scoped-network-shaped, default-no-network-shaped) before editing; pin those as canonical expected outputs in the test. After the edit, the assertions hold; any deviation is the regression.
- **`--ignore-scripts` suspension.** The Phase 2 wrapper injects `--ignore-scripts` automatically when the caller's argv starts with `npm` or `node`. That injection is suspended when `test_execution=True` — but the wrapper that actually injects lives in `tools/npm.py` (Step 3). Document the contract here: when `test_execution=True` is passed through `run_in_sandbox`'s `**kwargs` to the wrapper layer, the wrapper checks the flag and skips injection. This story plants the `test_execution` parameter; Step 3 reads it.
- **Overlay flags vary by bwrap version.** Phase 2's bwrap pin (`tools/digests.yaml`) fixes a known version; consult that digest for the exact flag spelling. If the pinned bwrap predates `--tmpfs` overlay support, use the documented Phase 2 idiom for writable mounts.
- **macOS best-effort.** Use the same sandbox-exec template Phase 2 ships; substitute the equivalent profile rule for the writable overlay. Document the gap inline: "sandbox-exec does not isolate as strongly as bwrap; this branch is best-effort and Phase 5's microVM is the load-bearing fix."
- **PID/wall budget defaults.** Phase 2's default is documented in ADR-0003 (~900 MB RSS / ~180 s wall / ~256 PIDs). When `test_execution=True`, raise to **1024 PIDs / 600 s wall** per ADR-0005. RSS budget (Phase 2's 900 MB → 4 GB in ADR-0005) is part of the same overlay profile.
- **No `subprocess.run` outside the existing chokepoint.** This story only edits `run_in_sandbox`; do not introduce new subprocess call sites. The Phase 2 fence enforces this at CI time.
- **Test the negative path explicitly.** Calling `run_in_sandbox(..., test_execution=True, network="scoped")` is allowed (the `--allow-test-network` operator opt-in path). Calling it with an invented keyword (`network="hard_none"`) raises `TypeError` at function-call time; the invariant test catches it at CI time.
