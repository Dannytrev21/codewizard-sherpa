# Story S3-05 — Postinstall-RCE adversarial fixture + `BuildGraphProbe` end-to-end

**Step:** Step 3 — Ship `IndexHealthProbe` (B2) and `BuildGraphProbe` (B5)
**Status:** Ready
**Effort:** S
**Depends on:** S3-02 (`BuildGraphProbe` + wrapper-level `--ignore-scripts` invariant + `tests/unit/tools/test_pnpm_invariant.py`)
**ADRs honored:** ADR-0007 (`BuildGraphProbe` `--ignore-scripts` invariant), ADR-0003 (`run_in_sandbox` `network="none"`), production ADR-0006 (deterministic gather)

## Context

S3-02 enforces `--ignore-scripts` at the wrapper layer — the unit test `tests/unit/tools/test_pnpm_invariant.py` pins the first line of defense (the wrapper raises `ToolInvariantViolation` if the flag is missing). This story lands the **integration check**: a real `BuildGraphProbe` run against a hostile fixture whose `package.json` declares `scripts.postinstall: "touch /tmp/POWNED"`, asserting that `/tmp/POWNED` does **not** exist on disk after the probe runs. The two together — wrapper-level unit test (first line) + end-to-end adversarial test (integration check) — pin the postinstall-RCE invariant from both directions (`phase-arch-design.md "Implementation-level risks" #4`).

This is the canonical Phase 2 adversarial fixture. The pattern (hostile-input fixture + assertion on observable side-effect absence) is the template the Step 8 ≥ 40-fixture adversarial corpus copies.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #6 BuildGraphProbe` — `test_buildgraph_postinstall_blocked.py` is named explicitly as the adversarial test that pins the invariant.
  - `../phase-arch-design.md §"Edge cases & testing strategy"` (the adversarial fixtures section) — `test_buildgraph_postinstall_blocked.py` listed under the postinstall-RCE row.
  - `../phase-arch-design.md §"Implementation-level risks" #4` — the wrapper-level invariant + the integration check as the dual-defense pattern.
- **Phase ADRs:**
  - `../ADRs/0007-buildgraph-ignore-scripts-and-resolution-status.md` — ADR-0007 — names this adversarial test (`tests/adv/test_buildgraph_postinstall_blocked.py`) as the structural witness for the invariant.
  - `../ADRs/0003-subprocess-sandbox-profile-extension.md` — ADR-0003 — `run_in_sandbox` with `network="none"` is the sandbox path the probe uses for stage 2.
- **Source design:**
  - `../final-design.md §"Risks" #1` — `--ignore-scripts` discipline as ongoing convention; the adversarial fixture is the assert-discipline-survives-refactor mechanism.
- **High-level impl:**
  - `../High-level-impl.md §"Step 3"` deliverable bullet for the postinstall-RCE adversarial test.
- **Existing code (Step 3 prior + Step 1):**
  - `src/codegenie/probes/build_graph.py` (S3-02) — the probe under test.
  - `src/codegenie/tools/_pm_invariants.py` (S3-02) — the wrapper-level invariant; this test exercises the **end-to-end** path through it.
  - `src/codegenie/exec.py` — `run_in_sandbox` with `network="none"` from S1-02.

## Goal

Land the `tests/fixtures/postinstall_rce_attempt/` fixture and the adversarial test `tests/adv/test_buildgraph_postinstall_blocked.py` that runs `BuildGraphProbe` against the fixture and asserts no side-effect file (`/tmp/POWNED` or an equivalent test-local path) materializes on disk after the run — pinning the wrapper-level `--ignore-scripts` invariant from the integration direction.

## Acceptance criteria

- [ ] `tests/fixtures/postinstall_rce_attempt/` exists and contains:
  - `package.json` declaring `{"name": "postinstall-rce-attempt", "version": "0.0.1", "private": true, "scripts": {"postinstall": "touch <CANARY_PATH>", "preinstall": "touch <CANARY_PATH>"}, "workspaces": ["packages/*"]}`. The `<CANARY_PATH>` token is replaced at test time with a per-test `tmp_path / "POWNED"` (do **not** use a real `/tmp/POWNED` — see Notes on test isolation).
  - `pnpm-workspace.yaml` declaring `packages: ["packages/*"]` so the monorepo flag from Phase 1's `LanguageDetectionProbe` returns `True` (otherwise `BuildGraphProbe.applies()` returns `False` and stage 2 never dispatches — see Notes).
  - `packages/a/package.json` and `packages/b/package.json` as minimal workspace members.
  - **No** `node_modules/`. **No** `pnpm-lock.yaml`. **No** real `pnpm` install was ever run against this fixture; it's a tripwire, not a buildable repo.
- [ ] `tests/adv/test_buildgraph_postinstall_blocked.py` exists. The test:
  - **Pre-condition:** `pnpm` is on `$PATH` (mark the test `pytest.mark.skipif(shutil.which("pnpm") is None, reason="pnpm required for integration check")`). If pnpm is not present, the test skips with a clear reason rather than passing vacuously.
  - **Arrange:** copy the fixture to a `tmp_path`-rooted location and substitute `<CANARY_PATH>` with `tmp_path / "POWNED"`. Confirm `not canary.exists()` at the start.
  - **Act:** instantiate `BuildGraphProbe` and run it against a `RepoSnapshot` rooted at the fixture copy. The probe goes through stage 1 (static parse, always) then stage 2 (`pnpm list -r --depth -1 --json --ignore-scripts` inside `run_in_sandbox(network="none")`).
  - **Assert:** after `await BuildGraphProbe().run(snapshot, ctx)`, `not canary.exists()` — `pnpm` did not run the `postinstall` script. The slice may emit `resolution_status: static_only` (pnpm failed to enumerate because there's no `pnpm-lock.yaml`) or `resolution_status: resolved` (depending on the pnpm version); both outcomes are acceptable. The **only** load-bearing assertion is the canary file's absence.
- [ ] The test is **deterministic**: the canary path is unique per test invocation (via `tmp_path`); no shared `/tmp/POWNED` state leaks between tests or processes.
- [ ] The test is **bounded**: total runtime ≤ 10 seconds wall-clock; if `pnpm` hangs, the probe's `timeout_seconds = 60` enforces the upper bound, but the test additionally asserts wall-clock completion (use `pytest-timeout` if Phase 0/1 already pins it).
- [ ] PR body documents the dual-defense pattern: (a) wrapper-level unit test `test_pnpm_invariant.py` (first line); (b) integration check `test_buildgraph_postinstall_blocked.py` (this story).
- [ ] `ruff format --check`, `ruff check`, `mypy --strict tests/adv/test_buildgraph_postinstall_blocked.py`, and the adversarial test all pass (when pnpm is available; the test skips when not).

## Implementation outline

1. **Build the fixture skeleton** under `tests/fixtures/postinstall_rce_attempt/`:
   - `package.json` with the `postinstall` + `preinstall` scripts targeting a `<CANARY_PATH>` placeholder. Both hooks are wired because some pnpm versions only run one of them on `pnpm list`. The wrapper's `--ignore-scripts` blocks both.
   - `pnpm-workspace.yaml` declaring two workspace packages.
   - `packages/a/package.json` + `packages/b/package.json` — minimal `{"name": "a", "version": "0.0.0", "private": true}` (and similarly for `b`).
2. **Write the adversarial test** at `tests/adv/test_buildgraph_postinstall_blocked.py`:
   - `pytest.mark.skipif` on `shutil.which("pnpm")` absence.
   - `tmp_path` fixture; copy the fixture; substitute `<CANARY_PATH>`.
   - Build a `RepoSnapshot` rooted at the copy. Phase 1's `LanguageDetectionProbe.monorepo` flag must report `True` for `BuildGraphProbe.applies()` to dispatch stage 2 — either reuse the LD probe in the test harness or fabricate the snapshot with `detected_languages.monorepo = True` directly (preferred for test speed).
   - `await BuildGraphProbe().run(snapshot, ctx)`.
   - Assert the canary file does **not** exist.
3. **Confirm test isolation:** run the test twice in sequence; the second run must also pass without cleanup. Run it concurrently (via `pytest -p xdist -n 2` if available) to confirm no `/tmp/POWNED`-style collision.
4. **Document** the dual-defense pattern in the PR body and in a one-line comment at the top of the test file.

## TDD plan — red / green / refactor

### Red — failing test first

The story is structured red-then-green at the *fixture* level. Without the fixture and test file, `pytest tests/adv/test_buildgraph_postinstall_blocked.py` fails with collection error.

```python
# tests/adv/test_buildgraph_postinstall_blocked.py
"""Pins: BuildGraphProbe's stage 2 cannot trigger postinstall scripts.
The wrapper-level invariant (S3-02 test_pnpm_invariant.py) is the first line;
this is the end-to-end integration check.
Traces to: phase-arch-design.md §Implementation-level risks #4; ADR-0007; ADR-0003."""
from __future__ import annotations
import shutil
import shutil as _shutil
from pathlib import Path
import pytest

from codegenie.probes.build_graph import BuildGraphProbe

pytestmark = pytest.mark.skipif(
    shutil.which("pnpm") is None,
    reason="pnpm required for postinstall-RCE end-to-end integration check",
)

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "postinstall_rce_attempt"

def _materialize_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """Copy fixture to tmp_path; substitute <CANARY_PATH> with a per-test path."""
    dst = tmp_path / "repo"
    _shutil.copytree(FIXTURE_ROOT, dst)
    canary = tmp_path / "POWNED"
    pkg = (dst / "package.json").read_text().replace("<CANARY_PATH>", str(canary))
    (dst / "package.json").write_text(pkg)
    return dst, canary

@pytest.mark.asyncio
async def test_buildgraph_postinstall_blocked(tmp_path, snapshot_for, ctx_for):
    repo, canary = _materialize_fixture(tmp_path)
    assert not canary.exists(), "fixture pre-condition: canary must not exist"
    snapshot = snapshot_for(repo, monorepo=True)
    ctx = ctx_for(repo)

    await BuildGraphProbe().run(snapshot, ctx)

    assert not canary.exists(), (
        "postinstall RCE protection broke: canary file materialized, "
        "meaning pnpm ran the postinstall script. The wrapper-level "
        "--ignore-scripts invariant (ADR-0007) is breached. Re-run S3-02's "
        "test_pnpm_invariant.py to localize the regression."
    )
```

Run `pytest tests/adv/test_buildgraph_postinstall_blocked.py -q`. With S3-02's wrapper enforcement in place, the test should pass once the fixture exists. If it fails (canary materializes), **stop** — the wrapper is broken; revert to S3-02 and fix the invariant.

### Green — smallest impl shape

1. Create the fixture tree as described in **Implementation outline**.
2. Write the test file per the snippet above.
3. Confirm the test passes (canary does **not** exist after the run).

### Refactor — bounded cleanup

- The `_materialize_fixture` helper may be reused by Step 8's adversarial corpus expansion — if so, extract to `tests/adv/_helpers.py` only when a second test imports it. Premature extraction is worse than duplication.
- The assertion message is intentionally verbose — it tells future maintainers where to look on regression. Keep it.
- Confirm `pytest-asyncio` is wired (Phase 0/1 dependency); if not, drop the `@pytest.mark.asyncio` decorator and use `asyncio.run(...)` inline.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/postinstall_rce_attempt/package.json` | New — hostile fixture with `postinstall` + `preinstall` canary-touch scripts |
| `tests/fixtures/postinstall_rce_attempt/pnpm-workspace.yaml` | New — declares the monorepo so `BuildGraphProbe.applies()` returns `True` |
| `tests/fixtures/postinstall_rce_attempt/packages/a/package.json` | New — minimal workspace member |
| `tests/fixtures/postinstall_rce_attempt/packages/b/package.json` | New — minimal workspace member |
| `tests/adv/test_buildgraph_postinstall_blocked.py` | New — the end-to-end integration check |
| `tests/adv/__init__.py` | New (if absent) — pytest collection marker |

## Out of scope

- **`/tmp/POWNED` literal canary path** — the original ADR-0007 + arch text mentions `/tmp/POWNED` literally, but Phase 2's test isolation invariant requires a per-test path. Use `tmp_path / "POWNED"`. Document the deviation inline.
- **Yarn / npm equivalents of the postinstall fixture** — `yarn workspaces list` and `npm ls` do **not** run scripts (per ADR-0007), so they don't need adversarial tests. If a future PR proposes them, document the no-op and skip.
- **`docker build` postinstall RCE** — `SyftSBOMProbe` builds an image inside a sandbox; that adversarial fixture (hostile-Dockerfile + `RUN curl ... | sh`) lands in Step 6 (S6-XX). This story is `BuildGraphProbe`-scoped.
- **Wrapper-layer unit test (`test_pnpm_invariant.py`)** — landed in S3-02. The two tests are paired; do **not** duplicate the wrapper-level assertion in this story.
- **Step 8's ≥ 40-fixture adversarial corpus expansion** — Step 8 takes this fixture as one of the ≥ 40; this story lands only the postinstall-RCE one.

## Notes for the implementer

- **Why both `postinstall` and `preinstall`** in the fixture: pnpm has historically been inconsistent about which lifecycle script `pnpm list` triggers (some versions run `preinstall` even on read-only commands). Wiring both hooks closes the gap and makes the test resilient to pnpm-version drift. The `--ignore-scripts` flag blocks **all** lifecycle scripts.
- **Per-test canary path** (`tmp_path / "POWNED"`) is non-negotiable. A literal `/tmp/POWNED` would (a) collide across parallel test runs, (b) leak state between sequential test runs if a cleanup is missed, (c) require root on some CI runners to set up. The deviation from ADR-0007's text is documented inline; the architectural invariant (the canary must not materialize) is preserved.
- **The `LanguageDetectionProbe.monorepo` flag** must be `True` for `BuildGraphProbe.applies()` to dispatch stage 2. The test fabricates `monorepo=True` on the snapshot directly to avoid running LD as a precondition. If you cannot fabricate the flag (Phase 0/1 snapshot may be frozen), run `LanguageDetectionProbe` inline in the test — it's cheap, and the fixture's `pnpm-workspace.yaml` plus `packages/*/package.json` should make LD return `monorepo=True` deterministically.
- **`pnpm` not on `$PATH`** at CI time → test skips, not fails. The wrapper-level unit test from S3-02 (`test_pnpm_invariant.py`) carries the security load when pnpm isn't installed. Make sure CI's setup step `pnpm install -g` (or the appropriate install) happens **before** this test runs; document the dependency in the project's CI config (out of scope for this story file, but flag in the PR body).
- **If the canary materializes**, do **not** suppress the test. The wrapper invariant is breached. Revert to S3-02, fix `assert_ignore_scripts`, and re-run. The whole point of the dual-defense pattern is that a regression here is loud.
- **Concurrent test isolation** — confirm `pytest -p xdist -n 4 tests/adv/test_buildgraph_postinstall_blocked.py` passes (run four copies concurrently). If it doesn't, the `tmp_path` fixture is leaking — `pytest`'s default `tmp_path` is per-test-and-per-worker, so this should work; if it doesn't, the bug is upstream.
- **No internet access** in the test — `run_in_sandbox(network="none")` from ADR-0003 is the contract. If `pnpm list` tries to reach a registry, the sandbox blocks it; that's expected (and is part of why `resolution_status: static_only` is an acceptable outcome from this test — the load-bearing assertion is the canary, not the resolution status).
- The test file's top docstring should explicitly link the wrapper-level test (`test_pnpm_invariant.py`) so a future maintainer reading the regression-fail message knows where to look first.
