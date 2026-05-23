# Story S6-04 — `tsc` admitted to `ALLOWED_BINARIES`

**Step:** Step 6 — Compose FallbackTier + register typecheck.typescript SignalKind + integration
**Status:** HARDENED
**Effort:** S
**Depends on:** S1-05 (path-scoped fence amendment lands cleanly)
**ADRs honored:** ADR-04-0015 (`typecheck.typescript` SignalKind + `tsc` admitted), production Phase-2 ADR-0001 (omnibus subprocess-allowlist), production Phase-3 ADR-0012 (ALLOWED_BINARIES amendment via ADR pattern)

## Validation notes (2026-05-22)

Hardened by `phase-story-validator`. Major changes:

- **Goal reframed (Cluster B, block):** the original "admit `./node_modules/.bin/tsc`
  as a path" directly contradicts the bare-name closed-set convention asserted at
  five independent codebase sites (`__init__.py:245-247` docstring, bubblewrap
  precedent at `test_exec.py:397-406`, path-traversal regression at
  `test_allowlist_phase3.py:156-176`, sum-type discipline per CLAUDE.md Phase-2
  ADR-0006, Phase-3 family closure tests). Per Global Rule 7 (surface conflicts,
  don't average them), the validator picks the more-tested convention. The story
  now admits **bare-name `"tsc"`**; narrow-admission discipline (only the
  repo-local `./node_modules/.bin/tsc` ever runs) lives caller-side in S6-05's
  `TypecheckTypescriptSignal` via `env_extra={"PATH": str(repo / "node_modules"
  / ".bin")}` — the existing `run_allowlisted` seam.
- **ADR-04-0015 + `High-level-impl.md` §175 stale (Cluster E, block):**
  ADR-04-0015 §Decision/§Tradeoffs/§Consequences claim "content-hashed per major
  Node version per Phase 3 ADR-0012's amendment pattern" — Phase 3 ADR-0012
  admits **bare names with no hashing**. Mechanically wrong. `High-level-impl.md`
  §175 names "ADR-04-0001" — typo for ADR-04-0015. Both flagged for amendment;
  AC-12 + AC-13 land them in the same PR. Same flagging pattern S1-05's
  validator used for ADR-0003.
- **TDD plan uncompilable (Cluster A, block):** the original imported
  `AllowlistViolation` (real symbol is `DisallowedSubprocessError` in
  `codegenie.errors`), called `run_allowlisted` synchronously (real signature
  is `async`), passed positional `(binary, args)` (real signature is `argv:
  list[str]`), missed required `timeout_s` kwarg, and read `result.exit_code`
  (real field is `returncode`). Both test stubs rewritten async-with-real-API
  and consolidated into one file matching Phase-3's `test_allowlist_phase3.py`
  family pattern (Cluster D + D-5).
- **Closure-test updates enumerated (Cluster C, block):** three closure-equality
  sites must move 16 → 17 (`tests/unit/test_exec.py:352`,
  `tests/unit/exec/test_allowed_binaries.py`,
  `tests/unit/exec/test_allowlist_phase3.py:72-76`). The original named a
  non-existent `test_allowlist_closure.py`. Listed explicitly in Files to touch.
- **Test plan now mirrors Phase-3 family pattern (Cluster D):** ADR cross-document
  gate, module-docstring assertion, parametric path-traversal rejection,
  parametric env-strip, `_RUNNING_PROCS` weakref-cleanup, plus a property-style
  "delta = exactly `{'tsc'}` vs Phase-3 closed set" assertion as the single
  cleanest mutation barrier.

Full audit log: [`_validation/S6-04-tsc-allowed-binary.md`](_validation/S6-04-tsc-allowed-binary.md).

## Context

Phase 0–3 hold the invariant: every external binary called from Phase-3+ runtime
is in the closed `ALLOWED_BINARIES` frozenset; admission requires an ADR
amendment (Phase 3 ADR-0012's pattern; Phase 2 ADR-0001 omnibus). The closed
set carries a **bare-name discipline** — every existing entry (`git`, `node`,
`npm`, `bwrap`, `sandbox-exec`, `jq`, …) is a bare binary name, and the
bubblewrap precedent (`tests/unit/test_exec.py:397-406`) pins this discipline
structurally: **short bare name IN; canonical long name / path / alias OUT**.
The path-traversal regression at `tests/unit/exec/test_allowlist_phase3.py:
156-176` enforces it per-binary: `[f"./{b}" for b in NEW_BINARIES]` raises
`DisallowedSubprocessError` *before* spawn (`spy.assert_not_awaited()`).
`tsc` is currently **not** on the allowlist. S6-05 cannot ship the
`TypecheckTypescriptSignal` collector until this story merges.

[ADR-04-0015](../ADRs/0015-typecheck-typescript-signal-and-tsc-allowed-binary.md)
is the amendment. **⚠ Stale ADR text** — §Decision (line 27) and §Tradeoffs
(line 35) and §Consequences (line 51) say "add `./node_modules/.bin/tsc`
(content-hashed per major Node version per Phase 3 ADR-0012's amendment
pattern)." Phase-3 ADR-0012 admits **bare names with no content-hashing**;
the "path + content-hashed" framing is mechanically wrong (analogous to the
ADR-0003 staleness S1-05 flagged). The same ADR's §Pattern-fit (line 44)
correctly says "only one ADR amendment to `ALLOWED_BINARIES`" and "following
the Phase 3 ADR-0012 pattern" — bare-name. The validator resolved toward
the §Pattern-fit framing per Global Rule 7. AC-12 amends the §Decision /
§Tradeoffs / §Consequences text in the same PR.

The admitted entry is **`"tsc"`** (bare). Narrow-admission discipline lives
caller-side in S6-05: the signal prepends `repo / "node_modules" / ".bin"`
to `PATH` via `env_extra` so the `tsc` resolved at spawn time is **always**
the repo-local copy — `asyncio.create_subprocess_exec` resolves `argv[0]`
via the child process's `PATH`, never the parent's. Phase 7's distroless
plugin won't have a Node toolchain at all; it simply doesn't register the
signal, so the admission is harmless for Phase 7.

This story is mechanically small but contract-load-bearing: the path-traversal
regression family must extend over `tsc` (the deliberate-violation discipline
that proves the admission is narrow), and the closure-equality assertion
across all three closure sites must move 16 → 17 in lockstep.

## References — where to look

- **Architecture:** [phase-arch-design.md §Component 11 — TypecheckTypescriptSignal](../phase-arch-design.md);
  §Deployment view ("SubprocessJail allowlist amended"); §Harness (subprocess
  discipline).
- **Phase ADRs:** [ADR-04-0015](../ADRs/0015-typecheck-typescript-signal-and-tsc-allowed-binary.md)
  (the amendment). **⚠ §Decision / §Tradeoffs / §Consequences carry stale
  "content-hashed path" framing — AC-12 amends these to match §Pattern-fit's
  correct bare-name claim.**
- **Production ADRs:** Phase 3 ADR-0012 (amendment-via-ADR pattern; **bare-name**
  admission, no content-hashing); Phase 2 ADR-0001 (omnibus allowlist).
- **High-level impl:** [High-level-impl.md §Step 6](../High-level-impl.md)
  Features delivered ("ADR-04-0001 amends `ALLOWED_BINARIES`"). **⚠ §175 has
  a typo — the amending ADR is ADR-04-0015. AC-13 fixes it.**
- **Existing code:** `src/codegenie/exec/__init__.py` — `ALLOWED_BINARIES`
  frozenset (lines 105–130), `run_allowlisted` (line 235; docstring at lines
  245–247 pins "must be a bare binary name"), `ProcessResult` (line 158).
- **Existing tests (closure-equality sites — all three must move 16 → 17):**
  - `tests/unit/test_exec.py` — `_PHASE_2_EXPECTED_BINARIES` constant (lines
    321–338); `test_node_in_allowed_binaries` (line 341, pins
    `ALLOWED_BINARIES == _PHASE_2_EXPECTED_BINARIES`);
    `test_allowed_binaries_closed_set_regression` (line 383, parametric over
    never-allowlisted binaries — `tsc` MUST NOT be added here).
  - `tests/unit/exec/test_allowed_binaries.py` — Phase 2 closure.
  - `tests/unit/exec/test_allowlist_phase3.py` — Phase 3 closure
    (`EXPECTED_TOTAL` at line 53; `len == 16` at line 72;
    `test_allowed_binaries_is_exact_sixteen_entry_set` at line 72).
- **Existing test family pattern (mirror in `test_allowlist_phase4.py`):**
  `tests/unit/exec/test_allowlist_phase3.py` carries the 8-AC family
  (closure exact-equality, ADR cross-document gate, per-binary allowlist
  acceptance, per-binary path-traversal rejection with
  `spy.assert_not_awaited()`, env-strip parametric, `_RUNNING_PROCS` weakref
  cleanup). Phase 4 follows the same shape — Open/Closed at the file
  boundary (one new `test_allowlist_phase4.py`, one ADR amendment, one row).

## Goal

Admit bare-name **`"tsc"`** to the `ALLOWED_BINARIES` frozenset (matching the
existing bare-name + bubblewrap-precedent convention) so

```python
await run_allowlisted(["tsc", "--noEmit", "--pretty", "false"],
                     cwd=repo_root,
                     timeout_s=30.0,
                     env_extra={"PATH": str(repo_root / "node_modules" / ".bin")})
```

resolves the repo-local `./node_modules/.bin/tsc` at the child's `PATH`
lookup. Extend the Phase-3 path-traversal regression family over `tsc` so
path-shaped invocations (`./node_modules/.bin/tsc`, `/usr/local/bin/tsc`,
`./tsc`, `tsc.bat`) raise `DisallowedSubprocessError` *before* spawn. Amend
ADR-04-0015 §Decision/§Tradeoffs/§Consequences + `High-level-impl.md` §175
in the same PR so the surrounding docs land consistent with the code.

Narrow-admission discipline (only the repo-local `./node_modules/.bin/tsc`
ever actually runs) is **out of scope for this story** — it lives caller-side
in S6-05's `TypecheckTypescriptSignal` via the `env_extra={"PATH": ...}`
seam already shipped in `run_allowlisted`'s Phase-0 signature.

## Acceptance criteria

- [ ] **AC-1 — bare name `"tsc"` admitted** (validator: hardened — Cluster B / C-Consistency-1 / D-1). The literal string `"tsc"` (not a path) appears in `src/codegenie/exec/__init__.py:ALLOWED_BINARIES` exactly once, appended in a Phase-4 group with the comment `# Phase 4 ADR-04-0015 addition` mirroring the Phase-2 / Phase-3 grouping convention. The set is **phase-grouped, not alphabetical** (verified by reading lines 105–130 first; Global Rule 8 + Rule 11).

- [ ] **AC-2 — `run_allowlisted([tsc, --version], cwd=tmp_path, timeout_s=5.0)` passes the allowlist check** (validator: hardened — T-1, T-2, T-3; Cluster A). Asserted via the Phase-3 sibling pattern (`tests/unit/exec/test_allowlist_phase3.py:138-148`): catch `DisallowedSubprocessError` explicitly and `pytest.fail` on it; tolerate `ToolMissingError`/`FileNotFoundError`/`ProbeTimeoutError` as environment artifacts. No shim script — the allowlist behavior is the only thing under test.

- [ ] **AC-3 — path-shaped invocations rejected** (validator: hardened — T-4, T-9, C-Coverage-8). The path-traversal regression extends over `tsc`: parametrized over `["/usr/local/bin/tsc", "/usr/bin/tsc", "/opt/homebrew/bin/tsc", "./node_modules/.bin/tsc", "./tsc", "./node_modules/.bin/tsc.bat", "./node_modules/.bin/../../usr/bin/tsc"]`, each call raises `DisallowedSubprocessError` (imported from `codegenie.errors`, NOT a fictional `AllowlistViolation`). Each test installs `spy = mock.AsyncMock(side_effect=AssertionError("must not spawn"))` via `monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)` and asserts `spy.assert_not_awaited()` — proving rejection happens **before** spawn (mirrors `test_allowlist_phase3.py:170-176`).

- [ ] **AC-4 — closure-equality sites bump 16 → 17 in lockstep** (validator: hardened — T-5, C-Consistency-3, D-6). Update all three closure-equality sites in the same PR:
  - `tests/unit/test_exec.py` — add `"tsc"` to the constant (rename to `_PHASE_4_EXPECTED_BINARIES` or chain `_PHASE_3_EXPECTED_BINARIES | {"tsc"}` — the chain form is OCP-friendlier for the next phase amendment). `test_node_in_allowed_binaries` (line 341) asserts the new union.
  - `tests/unit/exec/test_allowed_binaries.py` — closure-equality assertion updated similarly.
  - `tests/unit/exec/test_allowlist_phase3.py` — `EXPECTED_TOTAL` (line 53) and `len == 16` (line 72) move to 17. Document inline that the new entry is Phase-4 — the test stays anchored at the Phase-3 family for AC-4/AC-5 historical-precedent purposes.

- [ ] **AC-5 — closed-set regression preserves `tsc`-paths-disallowed** (validator: new — T-9). The parametric `test_allowed_binaries_closed_set_regression` at `tests/unit/test_exec.py:355` MUST NOT be widened to admit `"tsc"` — bare `tsc` is the new entry, but the `test_allowed_binaries_closed_set_regression`'s `denied` list pins **never-allowlisted** binaries (`bash`, `sh`, `python`, `bubblewrap`, …); none of those move. Asserted by leaving that test untouched and adding a paired new test `test_tsc_paths_remain_disallowed` parametrized over the path-traversal cases (= AC-3).

- [ ] **AC-6 — ADR cross-document gate** (validator: new — T-6). `tests/unit/exec/test_allowlist_phase4.py::test_adr_0015_enumerates_tsc` reads `docs/phases/04-vuln-llm-fallback-rag/ADRs/0015-typecheck-typescript-signal-and-tsc-allowed-binary.md` and asserts the backticked identifier `` `tsc` `` appears in its body. Cross-document gate: code-side admissions cannot land without the matching ADR enumeration. Mirrors `test_allowlist_phase3.py:116-129`.

- [ ] **AC-7 — `codegenie.exec` module docstring references ADR-04-0015** (validator: new — T-7). `tests/unit/exec/test_allowlist_phase4.py::test_exec_module_docstring_phase4_present` normalizes the docstring and asserts both `"04-ADR-0015"` (or `"ADR-04-0015"` — match the existing project ADR-naming convention; verify by reading the Phase-3 reference style at `__init__.py:97-104` first) and a phrase capturing the addition (e.g. `"one binary"`) are present. Mirrors `test_allowlist_phase3.py:97-108`.

- [ ] **AC-8 — env-strip applies to `tsc`** (validator: new — Phase-3 AC-7 parity). `tests/unit/exec/test_allowlist_phase4.py::test_env_strip_applies_to_tsc` parametrized over sensitive keys `("OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "ANTHROPIC_API_KEY", "SSH_AUTH_SOCK")` — each is dropped from the captured child env when passed in `env_extra`, AND a `subproc.env_extra.sensitive_key_dropped` structlog event fires at `log_level == "warning"`. Mirrors `test_allowlist_phase3.py:187-228`.

- [ ] **AC-9 — `_RUNNING_PROCS` weakref-table cleaned up after every `tsc` exit path** (validator: new — T-8). `tests/unit/exec/test_allowlist_phase4.py::test_tsc_running_procs_cleaned_up` asserts `len(_RUNNING_PROCS) == 0` after invocation (success / not-installed / spawn-time miss). Phase 7's coordinator-cancel pathway depends on the table staying accurate. Mirrors `test_allowlist_phase3.py:236-252`.

- [ ] **AC-10 — property-style delta assertion** (validator: new — T-11). `tests/unit/exec/test_allowlist_phase4.py::test_phase4_admits_exactly_tsc` asserts `ALLOWED_BINARIES - _PHASE_3_EXPECTED_BINARIES == frozenset({"tsc"})`. Single line, single mutation barrier: catches both silent drift (something else admitted) and over-broad admission (e.g., `"tsc"` plus a sibling).

- [ ] **AC-11 — no widening of `run_allowlisted` spawn/env/timeout invariants** (validator: refined — C-Coverage-6, C-Consistency-7). The diff touches only `src/codegenie/exec/__init__.py` (the `ALLOWED_BINARIES` block + module docstring), the three closure-equality test sites, the new `tests/unit/exec/test_allowlist_phase4.py`, and the two doc amendments (AC-12, AC-13). The six Phase-0 invariants (`__init__.py:1-54`: allowlist check, no-shell, `stdin=DEVNULL`, env-by-omission, mandatory `cwd`, mandatory `timeout_s` with SIGTERM-grace-SIGKILL escalation) are not modified. Reviewer-verifiable via `git diff --stat`.

- [ ] **AC-12 — ADR-04-0015 amended** (validator: new — Cluster E). The §Decision (line 27), §Tradeoffs row 1 (line 35), and §Consequences (line 51) text strings change in lockstep:
  - `add `./node_modules/.bin/tsc` (content-hashed per major Node version)` → `admit bare name `tsc``
  - "supply-chain surface grows; content-hashed path mitigates substitution attacks" → "supply-chain surface grows; narrow-admission discipline lives caller-side in `TypecheckTypescriptSignal` via `env_extra={\"PATH\": str(repo / \"node_modules\" / \".bin\")}`, mirroring the Phase-3 ADR-0012 bare-name pattern"
  - The §Pattern-fit section (already correct) is the canonical text — §Decision must match it. Attempt log records this amendment per Global Rule 7 (mirrors how S1-05 handled ADR-0003 §Decision staleness).

- [ ] **AC-13 — `High-level-impl.md` §175 typo fixed** (validator: new — C-Consistency-4). `ADR-04-0001 amends ALLOWED_BINARIES` → `ADR-04-0015 amends ALLOWED_BINARIES` (and the bullet text matches AC-12's "admit bare name `tsc`" wording).

- [ ] **AC-14 — pre-commit forbidden-patterns hook still rejects `subprocess.run(..., shell=True)`, `os.system`, etc.** (validator: refined — original AC). The admission doesn't widen the broader subprocess discipline (CLAUDE.md §Subprocess discipline). Asserted by running `pre-commit run --all-files` green.

- [ ] **AC-15 — `make check`, `make lint`, `make lint-imports`, `make fence` all green** (validator: refined — original AC). The Phase-0-fence test (`make fence`) is unaffected; this is a subprocess-allowlist amendment, not an LLM-SDK-fence amendment.

## Implementation outline

1. **Read first (Global Rule 8).** Read `src/codegenie/exec/__init__.py:1-130`,
   `tests/unit/exec/test_allowlist_phase3.py:1-253` (the family pattern to
   mirror), `tests/unit/test_exec.py:300-410` (closure regressions + bubblewrap
   precedent). Confirm the bare-name convention before writing a single line.

2. **Amend ADR-04-0015 first (Rule 12 — fail loud).** Edit §Decision,
   §Tradeoffs, §Consequences as enumerated in AC-12. The §Pattern-fit
   section is the canonical text; §Decision must match it. The amendment is
   the narrative correction; the code follows.

3. **Fix `High-level-impl.md` §175 typo (AC-13).** `ADR-04-0001` → `ADR-04-0015`;
   bullet text matches AC-12's wording.

4. **Add the row.** In `src/codegenie/exec/__init__.py:ALLOWED_BINARIES`, append
   `"tsc"` to a Phase-4 group with the comment `# Phase 4 ADR-04-0015 addition`.
   Update the module docstring's "Phase-N additions" paragraph to enumerate
   the Phase-4 addition (mirrors `__init__.py:37-43`'s Phase-2/Phase-3
   enumeration).

5. **Land `tests/unit/exec/test_allowlist_phase4.py`** with the 8-section
   banner structure mirroring Phase-3: AC-1 closure exact-equality + Phase-3
   union preserved + new-entry-present; AC-6 ADR cross-document gate;
   AC-7 docstring assertion; AC-2 per-`tsc` allowlist acceptance; AC-3 + AC-5
   per-`tsc` path-traversal rejection (with `spy.assert_not_awaited()`);
   AC-8 env-strip parametric; AC-9 `_RUNNING_PROCS` cleanup; AC-10 delta-from-
   Phase-3 property.

6. **Update the three closure-equality sites in lockstep (AC-4).** Prefer the
   chain form `_PHASE_4_EXPECTED_BINARIES = _PHASE_3_EXPECTED_BINARIES | {"tsc"}`
   so Phase 5's next admission is `_PHASE_5_EXPECTED_BINARIES = _PHASE_4_EXPECTED_BINARIES | {...}`.

7. **Run `make check`** end-to-end. The Phase-3 closure tests will fail before
   step 6 lands; that's the structural defense doing its job (Rule 12 —
   fail loud).

## TDD plan — red / green / refactor

### Red — write the failing tests first

Single new file `tests/unit/exec/test_allowlist_phase4.py`, mirroring the
Phase-3 sibling. The header below pins the constants; the section banners
mirror Phase-3's 8 ACs.

```python
# tests/unit/exec/test_allowlist_phase4.py
"""Tests for Phase 4 / S6-04 — ``ALLOWED_BINARIES`` single-binary amendment
(04-ADR-0015).

Mirrors the Phase-3 (S4-05) family pattern at
``tests/unit/exec/test_allowlist_phase3.py``:

* exact-equality on the seventeen-entry closed frozenset;
* ADR cross-document gate (the new binary enumerated as a backticked
  identifier in 04-ADR-0015's body);
* per-binary allowlist-acceptance;
* per-binary path-traversal rejection (absolute / relative paths fail
  *before* spawn);
* env-strip parametric over (new-binary × sensitive-key) pairs;
* ``_RUNNING_PROCS`` weakref cleanup on every exit path;
* property-style "delta = exactly {'tsc'}" mutation barrier.

ADR cross-reference: ``docs/phases/04-vuln-llm-fallback-rag/ADRs/
0015-typecheck-typescript-signal-and-tsc-allowed-binary.md``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest import mock

import pytest
import structlog

from codegenie.errors import (
    DisallowedSubprocessError,
    ProbeTimeoutError,
    ToolMissingError,
)
from codegenie.exec import ALLOWED_BINARIES, run_allowlisted

# Phase 3 baseline (mirrors test_allowlist_phase3.py's EXPECTED_TOTAL).
_PHASE_3_EXPECTED_BINARIES: frozenset[str] = frozenset(
    {
        "git", "node", "semgrep", "syft", "grype", "gitleaks",
        "scip-typescript", "ast-grep", "rg", "tree-sitter",
        "docker", "strace", "npm", "bwrap", "sandbox-exec", "jq",
    }
)
NEW_BINARIES: frozenset[str] = frozenset({"tsc"})
EXPECTED_TOTAL: frozenset[str] = _PHASE_3_EXPECTED_BINARIES | NEW_BINARIES  # 17

def _make_spawn_spy(monkeypatch: pytest.MonkeyPatch) -> mock.AsyncMock:
    fake_proc = mock.MagicMock()
    fake_proc.pid = 77779
    fake_proc.returncode = 0
    fake_proc.communicate = mock.AsyncMock(return_value=(b"", b""))
    spy = mock.AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    return spy

# ───────────────────────────────────────────────────────────────────────────
# AC-1 / AC-4 — exact-equality on the seventeen-entry closed set + Phase-3
# baseline preserved + Phase-4 new-entry present.
# ───────────────────────────────────────────────────────────────────────────

def test_allowed_binaries_is_exact_seventeen_entry_set() -> None:
    assert ALLOWED_BINARIES == EXPECTED_TOTAL
    assert len(ALLOWED_BINARIES) == 17

def test_phase_3_baseline_preserved() -> None:
    for name in _PHASE_3_EXPECTED_BINARIES:
        assert name in ALLOWED_BINARIES, f"Phase-3 baseline binary missing: {name!r}"

def test_phase_4_new_entry_present() -> None:
    assert "tsc" in ALLOWED_BINARIES

# ───────────────────────────────────────────────────────────────────────────
# AC-10 — property-style "delta = exactly {'tsc'}" mutation barrier.
# ───────────────────────────────────────────────────────────────────────────

def test_phase4_admits_exactly_tsc() -> None:
    assert ALLOWED_BINARIES - _PHASE_3_EXPECTED_BINARIES == frozenset({"tsc"})

# ───────────────────────────────────────────────────────────────────────────
# AC-7 — module docstring records the Phase 4 amendment.
# ───────────────────────────────────────────────────────────────────────────

def test_exec_module_docstring_phase4_present() -> None:
    import codegenie.exec as exec_mod
    doc = " ".join((exec_mod.__doc__ or "").split())
    assert "04-ADR-0015" in doc or "ADR-04-0015" in doc
    assert "tsc" in doc  # short enumeration that Phase 4 added tsc

# ───────────────────────────────────────────────────────────────────────────
# AC-6 — ADR cross-document gate: tsc enumerated as a backticked identifier.
# ───────────────────────────────────────────────────────────────────────────

def test_adr_0015_enumerates_tsc() -> None:
    adr = Path(__file__).resolve().parents[3] / (
        "docs/phases/04-vuln-llm-fallback-rag/ADRs/"
        "0015-typecheck-typescript-signal-and-tsc-allowed-binary.md"
    )
    text = adr.read_text(encoding="utf-8")
    assert "`tsc`" in text, "04-ADR-0015 must enumerate `tsc` as a backticked identifier"

# ───────────────────────────────────────────────────────────────────────────
# AC-2 — tsc allowlist acceptance.
# ───────────────────────────────────────────────────────────────────────────

async def test_tsc_not_rejected_by_allowlist(tmp_path: Path) -> None:
    try:
        await run_allowlisted(["tsc", "--version"], cwd=tmp_path, timeout_s=5.0)
    except DisallowedSubprocessError:
        pytest.fail("'tsc' must be allowlisted; got DisallowedSubprocessError")
    except (ToolMissingError, ProbeTimeoutError, FileNotFoundError):
        pass  # environment artifact, not allowlist behavior

# ───────────────────────────────────────────────────────────────────────────
# AC-3 / AC-5 — path-traversal rejection: every path-shaped invocation fails
# BEFORE spawn (spy.assert_not_awaited()).
# ───────────────────────────────────────────────────────────────────────────

_TSC_TRAVERSAL_CASES: list[str] = [
    "/usr/local/bin/tsc",
    "/usr/bin/tsc",
    "/opt/homebrew/bin/tsc",
    "./node_modules/.bin/tsc",
    "./tsc",
    "./node_modules/.bin/tsc.bat",
    "./node_modules/.bin/../../usr/bin/tsc",
]

@pytest.mark.parametrize("argv0", _TSC_TRAVERSAL_CASES)
async def test_tsc_paths_remain_disallowed(
    argv0: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = mock.AsyncMock(side_effect=AssertionError("must not spawn"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    with pytest.raises(DisallowedSubprocessError):
        await run_allowlisted([argv0, "--version"], cwd=tmp_path, timeout_s=1.0)
    spy.assert_not_awaited()

# ───────────────────────────────────────────────────────────────────────────
# AC-8 — env-strip applies to tsc invocations.
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "sensitive_key",
    ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY",
     "GITHUB_TOKEN", "SSH_AUTH_SOCK"],
)
async def test_env_strip_applies_to_tsc(
    sensitive_key: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = _make_spawn_spy(monkeypatch)
    with structlog.testing.capture_logs() as events:
        await run_allowlisted(
            ["tsc", "--version"], cwd=tmp_path, timeout_s=5.0,
            env_extra={sensitive_key: "leak-value"},
        )
    assert spy.await_args is not None
    captured_env: dict[str, str] = spy.await_args.kwargs["env"]
    assert sensitive_key not in captured_env
    drop_events = [
        e for e in events
        if e.get("event") == "subproc.env_extra.sensitive_key_dropped"
        and e.get("key") == sensitive_key
    ]
    assert drop_events and drop_events[0]["log_level"] == "warning"

# ───────────────────────────────────────────────────────────────────────────
# AC-9 — _RUNNING_PROCS weakref cleanup on every exit path for tsc.
# ───────────────────────────────────────────────────────────────────────────

async def test_tsc_running_procs_cleaned_up(tmp_path: Path) -> None:
    from codegenie.exec import _RUNNING_PROCS
    try:
        await run_allowlisted(["tsc", "--version"], cwd=tmp_path, timeout_s=5.0)
    except DisallowedSubprocessError:
        pytest.fail("'tsc' must be allowlisted")
    except (ToolMissingError, ProbeTimeoutError, FileNotFoundError):
        pass
    assert len(_RUNNING_PROCS) == 0
```

### Green — make it pass

- Apply AC-12 + AC-13 doc amendments first (Rule 12 — narrative correction
  precedes code).
- Add `"tsc"` to `ALLOWED_BINARIES` in `src/codegenie/exec/__init__.py` with
  the `# Phase 4 ADR-04-0015 addition` comment. Update the module docstring's
  Phase-additions paragraph to enumerate the Phase-4 row.
- Update the three closure-equality sites in lockstep (`tests/unit/test_exec.py`,
  `tests/unit/exec/test_allowed_binaries.py`,
  `tests/unit/exec/test_allowlist_phase3.py`) so they go 16 → 17. Prefer the
  chain form (`_PHASE_4 = _PHASE_3 | {"tsc"}`) so Phase 5's amendment is
  one more chain link, not a rewrite.

### Refactor — clean up

- Resist refactoring the allowlist module while adding the row — Global Rule 3
  (surgical changes).
- Don't introduce a `NarrowAdmissionPolicy` registry now (Rule 2 — single
  instance). Flag the YAGNI line in Notes-for-implementer: the **third**
  repo-local binary (Phase 5+) triggers the registry refactor, not a third
  hack (Design-Patterns critic D-7).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/exec/__init__.py` | Add `"tsc"` to `ALLOWED_BINARIES` (lines 105–130) + update module docstring's Phase-additions paragraph (lines 37–43 region). |
| `docs/phases/04-vuln-llm-fallback-rag/ADRs/0015-typecheck-typescript-signal-and-tsc-allowed-binary.md` | AC-12 — amend §Decision (line 27), §Tradeoffs row 1 (line 35), §Consequences (line 51) to match §Pattern-fit's bare-name framing. |
| `docs/phases/04-vuln-llm-fallback-rag/High-level-impl.md` | AC-13 — §175 `ADR-04-0001` → `ADR-04-0015` + bullet text matches bare-name framing. |
| `tests/unit/exec/test_allowlist_phase4.py` | **New** — 8-section Phase-3-family-pattern test file (AC-1, AC-2, AC-3, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10). |
| `tests/unit/test_exec.py` | AC-4 — `_PHASE_2_EXPECTED_BINARIES` → chain to `_PHASE_4_EXPECTED_BINARIES = _PHASE_3_EXPECTED_BINARIES | {"tsc"}` (or rename appropriately); `test_node_in_allowed_binaries` (line 341) asserts the new union. `test_allowed_binaries_closed_set_regression` (line 383) **stays unchanged** (per AC-5). |
| `tests/unit/exec/test_allowed_binaries.py` | AC-4 — closure-equality assertion updated to 17 entries. |
| `tests/unit/exec/test_allowlist_phase3.py` | AC-4 — `EXPECTED_TOTAL` (line 53) + `len == 16` (line 72) bump to 17; inline comment explains the Phase-4 chain. |

## Out of scope

- The `TypecheckTypescriptSignal` collector that actually invokes `tsc` and
  owns the narrow-admission `env_extra={"PATH": ...}` discipline — **S6-05**.
- The applicability matrix (`tsconfig.json` + `.ts` files detection) — **S6-06**.
- Phase 7's distroless plugin question (does it inherit `typecheck.typescript`
  or not) — Phase 7 / Phase 6.5 decision.
- Promoting `typecheck.typescript` to a shared
  `vulnerability-remediation--node--*` base plugin per ADR-0031 — deferred per
  arch open question 3.
- Per-entry content-hashing / per-entry narrow-admission policy registry —
  premature (single instance today; Rule 2). Flag the third repo-local entry
  as the YAGNI trigger.

## Notes for the implementer

- **Read first (Rule 8).** `src/codegenie/exec/__init__.py` lines 1–130
  carries the convention. `tests/unit/exec/test_allowlist_phase3.py` is the
  family pattern to mirror — it's the Phase-3 sibling that landed the previous
  amendment and is the canonical shape for Phase 4 (Rule 11).

- **ADR-04-0015 + High-level-impl.md amendments are part of this PR**
  (AC-12, AC-13). The Decision/Tradeoffs/Consequences text that says
  "content-hashed per major Node version" is mechanically wrong; the
  §Pattern-fit section is correct. This is the same kind of staleness S1-05's
  validator flagged in ADR-0003 — log it in the attempt log per Rule 7 and
  amend in the same PR as the code so the closure-equality assertions land
  alongside the corrected surrounding text.

- **Narrow-admission discipline is caller-side, not allowlist-side.**
  `run_allowlisted` is uniform (bare names); the signal owns its own narrowing
  via `env_extra={"PATH": str(repo / "node_modules" / ".bin")}`. This is the
  Open/Closed factoring (Design-Patterns critic D-2): the allowlist closure-
  equality structural defense survives untouched; the discipline lives where
  it matters (in S6-05's signal). Don't be tempted to admit the path string
  into the allowlist — five independent codebase assertions hold the bare-name
  convention (docstring lines 245–247, bubblewrap precedent at
  `test_exec.py:397-406`, path-traversal regression at
  `test_allowlist_phase3.py:156-176`, sum-type discipline per CLAUDE.md
  Phase-2 ADR-0006, three closure-equality sites). Five-vs-one; Rule 7 says
  pick the more-tested.

- **The bubblewrap precedent is your North Star.** Short name `"bwrap"` IN;
  canonical long name `"bubblewrap"` and any path-shaped invocation OUT. That
  precedent pins the policy on the long-name companion at two locations
  (the closed-set regression parametrize at `test_exec.py:355-381` + the
  dedicated `test_bubblewrap_long_name_remains_disallowed` at line 397).
  Follow the same shape for `tsc`: short name IN; paths OUT (= AC-3 + AC-5).

- **Closure-test chain form.** Prefer `_PHASE_4 = _PHASE_3 | {"tsc"}` over a
  freshly enumerated set — the chain form means the next phase's amendment is
  a one-row append, not a 17-line copy-paste (Open/Closed at the file
  boundary; cheaper future PRs).

- **Don't refactor the allowlist module.** Surgical changes (Rule 3). The
  story is one row + tests + two doc amendments.

- **YAGNI flag for the next contributor (Design-Patterns D-7).** If Phase 5
  brings a second repo-local binary (e.g., `eslint`), the current bare-name +
  caller-PATH-scoping factoring scales. The **third** repo-local binary is
  the right point to factor out a `NarrowAdmissionPolicy` registry — until
  then, three similar caller-side patches is the cheaper code (Rule 2). Note
  in the attempt log if you spot a second repo-local binary on the horizon.

- This story is small (S effort). Do not gold-plate by refactoring the
  allowlist module, building a `NarrowAdmissionPolicy` registry, or adding
  per-entry content-hash plumbing. Surgical (Rule 3).
