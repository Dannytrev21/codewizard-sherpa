# Story S9-01 — `make check` + `import-linter` Phase 3 contracts wired into CI

**Step:** Step 9 — CI gates, import-linter contracts, performance baselines, bench backfill hook
**Status:** Ready
**Effort:** M
**Depends on:** S8-04
**ADRs honored:** ADR-0012 (amends `ALLOWED_BINARIES` with `bwrap` — the binary the Linux CI job must `apt-get install` or S4-02 silently `pytest.skip`s instead of running), ADR-0005 (two-stream event log — fence tests in Step 9 read from the on-disk paths this ADR pins), ADR-0006 (hexagonal `SubprocessJail` Port — the Linux substrate is `bwrap`; CI must provide it), ADR-0011 (honest framing — the CI gate, not "the spirit of the test," is what blocks regression)

## Context

Phase 3 finally has every invariant Steps 1–8 promised — newtype identifiers, sum-type outcomes, plugin registry kernel, two-stream EventLog with BLAKE3 chain, sandboxed subprocess jail, four recipes, three plugins, ≥10 fixtures, 100-run determinism property, and 20 adversarial regressions. Every one of those invariants is **convention** until CI hard-blocks regression. Step 9 turns conventions into gates.

`make check` today runs `lint → typecheck → test → fence` (`Makefile §check`). It does NOT yet run `make lint-imports` (the existing CI workflow invokes it as a separate step in the `lint` job — see `.github/workflows/ci.yml §lint`). Phase 3 adds three new `import-linter` contracts that need to live in `pyproject.toml § [tool.importlinter]` and execute as part of `make lint-imports`:

1. **No LLM SDK under `src/codegenie/{plugins,transforms}/`.** Mirrors production ADR-0005's pyproject-fence pattern: the `FORBIDDEN_LLM_SDKS` set (`anthropic`, `langgraph`, `openai`, `langchain`, `transformers`) must not appear in the transitive closure under either Phase 3 package. This is the structural complement to S1-05's runtime fence (`tests/fence/test_no_llm_in_transforms.py`) — both layers required.
2. **No cross-plugin imports.** A file under `plugins/vulnerability-remediation--node--npm/` may not import from `plugins/universal--*--*/` or from `tests/fixtures/plugins/example--noop--*/`. Plugins are independently loadable; cross-plugin imports would defeat the registry pattern and bifurcate the contract (the same anti-pattern critique called out in `phase-arch-design.md §Gap 3` for recipe registration).
3. **No direct import of `codegenie.plugins.subgraph` from plugin folders.** Plugins consume the subgraph contract via `Plugin.build_subgraph()` only (the Protocol from S6-03). A direct import would let a plugin reach into the orchestrator's internals — a leak the `SubgraphNode` Protocol exists to prevent.

The third invariant Step 9 must lock down is the Linux CI substrate. S4-02 ships `BwrapAdapter`; its integration tests must FAIL (not `pytest.skip`) when `bwrap` is missing on a Linux runner — silent skips are the exact `phase-arch-design.md §Implementation-level risks #1` failure mode. The CI workflow needs an explicit `apt-get install -y bubblewrap` step on `ubuntu-24.04`, plus a `test_bwrap_present.py`-style assertion at suite setup that fails the job loudly on Linux when the binary is missing.

The CI matrix (`.github/workflows/ci.yml § jobs.lint.strategy.matrix`) already runs Python 3.11 × `ubuntu-24.04` and Python 3.12 × `ubuntu-24.04` for `lint`. Step 9 extends the same matrix discipline to the `test` and `fence` jobs (today both are 3.11-only — see `.github/workflows/ci.yml §typecheck`, §test, §fence) so Phase 3 regressions on 3.12 surface in CI rather than at release.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy / CI gates (required jobs)` — `make check`, `make lint-imports`, `make fence`, `test_phase5_contract_snapshot`, `test_three_plugin_contract`, `test_end_to_end_express_cve` are the six required jobs Step 9 wires.
  - `../phase-arch-design.md §Harness engineering / Determinism vs. probabilism` — the three-layer LLM-fence: `import-linter` contract + `test_no_llm_in_transforms.py` + `make fence`. This story lands the first; the other two ship in S1-05 / Phase 0's existing `test_pyproject_fence.py`.
  - `../phase-arch-design.md §Implementation-level risks #1` (`bwrap` availability) — the named failure mode this story closes.
- **Phase ADRs:**
  - `../ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md` — `bwrap` is in `ALLOWED_BINARIES` because the `SubprocessJail` adapter needs it; the CI runner must therefore have it installed.
  - `../ADRs/0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md` — Linux Adapter is `BwrapAdapter`; the binary is non-optional on Linux.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — "loud failure when the substrate is missing" is the discipline this story instantiates at the CI layer.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — the parent pattern `import-linter` contract #1 mirrors for the Phase 3 surface.
- **Existing code:**
  - `Makefile` — `check`, `lint`, `lint-imports`, `typecheck`, `test`, `fence` targets. Extend `check` without breaking the existing chain.
  - `.github/workflows/ci.yml` — six-job CI shape; matrix already exists on `lint`; extend to `test` and `fence`.
  - `pyproject.toml § [tool.importlinter]` — two contracts ship today (`codegenie.cli` + `codegenie.__init__` heavy-module forbids); Phase 3 appends three more.
  - `tests/unit/test_pyproject_fence.py` — the runtime-closure fence; remains unchanged but is reasserted by the matrix expansion.

## Goal

Wire every Phase 3 invariant into CI as a hard-block gate: `make check` runs Phase 3 fence tests; `make lint-imports` enforces three new Phase 3 `import-linter` contracts; the CI matrix runs 3.11 + 3.12 × `ubuntu-24.04` for `lint`, `typecheck`, `test`, and `fence`; `bwrap` is installed on every Linux CI job that runs the integration suite; S4-02's `BwrapAdapter` integration test FAILS loudly (does not skip) when `bwrap` is missing on Linux.

## Acceptance criteria

- [ ] `Makefile §check` runs the Phase 3 fence tests via `pytest -q tests/fence/` (or equivalent extension) without losing the existing `lint → typecheck → test → fence` order. The existing `fence` target (which runs `tests/unit/test_pyproject_fence.py`) is preserved; the Phase 3 additions land under `tests/fence/` so the production fence pattern is not retargeted.
- [ ] `pyproject.toml § [tool.importlinter]` has three new `[[tool.importlinter.contracts]]` entries:
  - **Contract A — no LLM SDK under Phase 3 packages.** `type = "forbidden"`; `source_modules = ["codegenie.plugins", "codegenie.transforms"]`; `forbidden_modules = ["anthropic", "langgraph", "openai", "langchain", "transformers"]`; named "Phase 3 packages must not import LLM SDKs".
  - **Contract B — no cross-plugin imports.** `type = "forbidden"`; `source_modules` enumerates every plugin package under `plugins/` (today: `plugins.vulnerability-remediation--node--npm`, `plugins.universal--*--*`, `tests.fixtures.plugins.example--noop--*`); `forbidden_modules` is the same list minus self. Implemented as N pairwise contracts (one per plugin source, forbidding the other plugin targets) — `import-linter` does not natively express "no peer", so explicit enumeration is the honest shape.
  - **Contract C — no direct import of `codegenie.plugins.subgraph` from plugin folders.** `type = "forbidden"`; `source_modules` = plugin packages (as in B); `forbidden_modules = ["codegenie.plugins.subgraph"]`.
- [ ] `make lint-imports` exits 0 on a clean tree and fails with a contract-name-specific diagnostic when any of the three contracts is violated by a deliberate test-only injection.
- [ ] `.github/workflows/ci.yml` extends the matrix on `test`, `typecheck`, and `fence` to Python `["3.11", "3.12"]` × `os: ["ubuntu-24.04"]` (mirrors the existing `lint` job's matrix shape).
- [ ] `.github/workflows/ci.yml` adds an explicit `apt-get install -y bubblewrap` step to every Linux CI job that runs the Phase 3 integration tests (`test` job at minimum). The step runs before `pip install`; failure to install fails the job.
- [ ] `tests/integration/test_bwrap_present.py` (NEW) asserts `shutil.which("bwrap") is not None` on Linux at module-import time. The assertion uses `pytest.fail(...)` (not `pytest.skip(...)`) when on Linux and `bwrap` is missing. On macOS the test `pytest.skip("Linux substrate only")`. Lives under `tests/integration/` so the existing test job picks it up automatically.
- [ ] `tests/fence/test_phase3_importlinter_contracts.py` (NEW) parses `pyproject.toml`, asserts the three Phase 3 contracts exist by name (A/B/C), and asserts each contract's `source_modules`/`forbidden_modules` match the spec. (This is the meta-fence: it prevents a future PR from silently weakening or removing a contract.)
- [ ] `tests/unit/test_ci_workflow.py` (existing) gains assertions for: matrix presence on `test`/`typecheck`/`fence`; the `apt-get install -y bubblewrap` step; ordering (`apt-get` precedes `pip install`).
- [ ] `make check` on a fresh tree green; `make lint-imports` green; matrix CI green on a draft PR.
- [ ] `mypy --strict` clean; `ruff check`, `ruff format --check` clean on touched files.
- [ ] TDD plan's red test exists, committed, green.

## Implementation outline

1. **Phase 3 `tests/fence/` directory.** Create `tests/fence/__init__.py` + `tests/fence/test_phase3_importlinter_contracts.py`. The new directory is the Phase 3 home for fence tests; `tests/unit/test_pyproject_fence.py` stays untouched (production-ADR-0005 cold-start fence).
2. **`pyproject.toml § [tool.importlinter]` extension.** Append three contracts (A/B/C) per AC. Keep the existing two contracts unchanged. Document each new contract with a `# Phase 3 ADR-XXXX` cross-reference comment.
3. **`Makefile §check` extension.** Replace `check: lint typecheck test fence` with `check: lint typecheck test fence fence-phase3`; add a `fence-phase3` target running `pytest -q tests/fence/`. Order: the production `fence` runs first (it's the cold-start invariant); Phase 3's `fence-phase3` is additive. Alternative: extend `fence:` itself to glob `tests/fence/` AND `tests/unit/test_pyproject_fence.py` — pick whichever preserves the production-fence-in-bare-install constraint (see `.github/workflows/ci.yml §fence` for the bare-install discipline; the cold-start fence MUST run without `[dev]` installed, but Phase 3 fence tests can assume `[dev]`).
4. **CI matrix expansion.** Edit `.github/workflows/ci.yml` `typecheck`, `test`, and `fence` jobs to add `strategy.matrix.python: ["3.11", "3.12"]` + `os: ["ubuntu-24.04"]` mirroring `lint`. Verify `test_ci_workflow.py` assertions get updated.
5. **`bubblewrap` install step.** Insert `- name: Install bubblewrap (Linux SubprocessJail substrate, ADR-0006 + ADR-0012)\n  run: sudo apt-get update && sudo apt-get install -y bubblewrap` before `Install dev extras` on the `test` job. Asserted by `test_ci_workflow.py`.
6. **`test_bwrap_present.py`.** One module, two tests: `test_bwrap_present_on_linux` (`shutil.which("bwrap") is not None`; `pytest.fail` if missing) and `test_skip_on_macos` (`sys.platform == "darwin"` ⇒ `pytest.skip`). Place under `tests/integration/`.
7. **Negative regression tests.** For each `import-linter` contract, write a `tests/fence/test_phase3_importlinter_contracts.py` test that (a) parses `pyproject.toml` and asserts the contract is present + correctly shaped, and (b) optionally exercises `import-linter`'s API to confirm the contract evaluates (subprocess-invoke `lint-imports --config pyproject.toml --contract <name>` and assert exit 0).
8. **Documentation.** Update `docs/contributing.md` (or equivalent) with a one-line "Phase 3 CI gates" note — the runbook entry proper ships in S9-04.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/fence/test_phase3_importlinter_contracts.py`

```python
import tomllib
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
_FORBIDDEN_LLM = {"anthropic", "langgraph", "openai", "langchain", "transformers"}


def _contracts() -> list[dict]:
    data = tomllib.loads(PYPROJECT.read_text())
    return data["tool"]["importlinter"]["contracts"]


def test_phase3_no_llm_sdk_contract_present() -> None:
    """Contract A: no LLM SDK under Phase 3 packages (mirrors production ADR-0005).

    Why it matters: an LLM SDK appearing in the runtime closure under
    src/codegenie/{plugins,transforms}/ would break the Phase 3 deterministic-only
    commitment (phase-arch-design.md §Harness engineering / Determinism vs.
    probabilism). The contract is the structural complement to the runtime
    fence; both must pass.
    """
    contracts = _contracts()
    matches = [c for c in contracts if c.get("name") == "Phase 3 packages must not import LLM SDKs"]
    assert matches, "Contract A missing"
    c = matches[0]
    assert c["type"] == "forbidden"
    assert set(c["source_modules"]) == {"codegenie.plugins", "codegenie.transforms"}
    assert _FORBIDDEN_LLM <= set(c["forbidden_modules"])


def test_phase3_no_cross_plugin_imports_contract_present() -> None:
    """Contract B: plugins must not import from one another (the registry pattern
    is the only legal handshake; cross-plugin imports bifurcate the contract)."""
    names = {c.get("name") for c in _contracts()}
    assert any("cross-plugin imports forbidden" in (n or "") for n in names)


def test_phase3_no_subgraph_import_from_plugins_contract_present() -> None:
    """Contract C: plugins consume the subgraph contract via Plugin.build_subgraph()
    only (the SubgraphNode Protocol from S6-03)."""
    contracts = _contracts()
    matches = [c for c in contracts if "subgraph internals" in (c.get("name") or "")]
    assert matches
    assert "codegenie.plugins.subgraph" in matches[0]["forbidden_modules"]
```

Plus `tests/integration/test_bwrap_present.py`:

```python
import shutil
import sys

import pytest


@pytest.mark.skipif(sys.platform == "darwin", reason="Linux substrate only (ADR-0006)")
def test_bwrap_present_on_linux() -> None:
    """bwrap is the Linux SubprocessJail substrate (ADR-0006 + ADR-0012).
    Missing it would let S4-02's integration test pytest.skip silently — the
    exact failure mode phase-arch-design.md §Implementation-level risks #1 names.
    Fail loud."""
    if shutil.which("bwrap") is None:
        pytest.fail(
            "bwrap missing on Linux runner. Install: apt-get install -y bubblewrap. "
            "See phase-arch-design.md §Implementation-level risks #1."
        )
```

State why they fail: the three `import-linter` contracts do not yet exist in `pyproject.toml`; `bubblewrap` may not be installed on the local dev box (the test then fails loud, as intended).

### Green — minimal pass
- Append the three contracts to `pyproject.toml § [tool.importlinter]`.
- Add the `apt-get install -y bubblewrap` step to the CI `test` job and extend the matrix on `test`/`typecheck`/`fence`.
- Extend `Makefile §check` to include the Phase 3 fence directory.
- Locally install `bubblewrap` (or run the test on a CI-provisioned runner) to make `test_bwrap_present.py` green.

### Refactor
- Lift the `FORBIDDEN_LLM_SDKS` set used by the fence test from a shared module (DRY against `tests/unit/test_pyproject_fence.py`'s constant).
- Add a `make ci-locally` convenience target that runs `make check` + `make lint-imports` + `pytest tests/fence/ tests/integration/` so contributors can pre-verify before pushing.
- Edge cases from §Edge cases that touch this code: E10 (universal fallback substitution while concrete plugin import-fails) — Contract B's cross-plugin forbid is the structural defense; the runtime defense ships in S2-03/S7-04.

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` | Append three Phase 3 `[[tool.importlinter.contracts]]` entries (A/B/C) with one-line ADR cross-references. |
| `Makefile` | Extend `check` to include Phase 3 fence directory; add `fence-phase3` (or extend `fence`) target. |
| `.github/workflows/ci.yml` | Add `apt-get install -y bubblewrap` to `test` job; extend matrix on `test`/`typecheck`/`fence` to 3.11 + 3.12 × `ubuntu-24.04`. |
| `tests/fence/__init__.py` | NEW — Phase 3 fence-test package. |
| `tests/fence/test_phase3_importlinter_contracts.py` | NEW — meta-fence: contracts exist + correctly shaped. |
| `tests/integration/test_bwrap_present.py` | NEW — assert `bwrap` on Linux; fail loud (not skip). |
| `tests/unit/test_ci_workflow.py` | Extend with assertions for the new matrix entries + `apt-get` step ordering. |

## Out of scope

- **Event-taxonomy completeness fence** — handled by S9-02.
- **`$0.00` LLM-spend assertion** — handled by S9-02.
- **Bench harness + rolling baseline** — handled by S9-03.
- **`BenchReplayable` event emit** — handled by S9-04 (the spanning event is owned by S6-01 + S6-04; Step 9 only adds the bench-backfill consumer).
- **Operator runbook** — handled by S9-04.
- **macOS sandbox-exec install step** — Phase 3's macOS integration tests run nightly (per `phase-arch-design.md §Testing strategy`); the install step is N/A on GitHub macOS runners (sandbox-exec ships with the OS).
- **`java` install step (OpenRewrite)** — Phase 7 amends `ALLOWED_BINARIES` with `java` per ADR-0012 §Decision; Phase 3 scaffolds `OpenRewriteRecipeEngine` but does NOT invoke it, so the runner does not need a JDK yet.

## Notes for the implementer

- **Three layers of LLM-fence, not one.** `import-linter` (this story, Contract A) is the *structural* fence — it sees the static import graph. `tests/fence/test_no_llm_in_transforms.py` (S1-05) is the *runtime-closure* fence — it imports the package and walks `sys.modules`. `tests/unit/test_pyproject_fence.py` (Phase 0) is the *bare-install* fence — it runs without `[dev]` to measure the actual gather-pipeline closure. All three must pass; do not collapse them.
- **`make fence` vs `tests/fence/`.** The existing `make fence` target runs ONLY `tests/unit/test_pyproject_fence.py` and is invoked by the bare-install `fence` CI job (see `.github/workflows/ci.yml §fence` — `[dev]` is deliberately NOT installed there). The new `tests/fence/test_phase3_importlinter_contracts.py` reads `pyproject.toml` and may rely on `[dev]`; route it through `make check` (which assumes `[dev]`), not through the bare-install `fence` job. Read `Makefile` carefully before consolidating targets.
- **Contract B enumeration is honest.** `import-linter` does not have a "no peer" relation; the contract has to enumerate `(source, forbidden)` pairs explicitly. With 3 plugins today this is 3 contract rows (or one contract with 3 source entries and pairwise-built forbidden lists). When Phase 7 lands the fourth plugin, the contract gets one more row — make this an additive edit, not a refactor.
- **`shutil.which` is the right primitive** for `test_bwrap_present.py`. Subprocess-invoking `bwrap --version` would catch broken-binary cases too, but adds startup-cost and would itself fail for ENOENT — `shutil.which` is the contract-correct fast path.
- **The CI `test` job's `bench-collection-guard` step** (existing, S5-01) collects exactly 3 bench tests. S9-03 will add 7 more bench files; that guard needs to be relaxed or replaced **in S9-03**, NOT here. This story preserves the count at 3.
- **`apt-get update` before `apt-get install`** — the bare `install` will sometimes 404 on a fresh GitHub Actions runner because the cached apt indices are pruned aggressively. Always pair them.
- **Match the existing CI-workflow comment style** — every job in `.github/workflows/ci.yml` has a `# ---...---` banner naming the ADR or story it implements. Phase 3 additions get a `# Phase 3: S9-01 / ADR-0006 + ADR-0012` banner.
- **`fence-phase3` naming is a suggestion** — if the implementer chooses to extend `fence:` itself (gluing both fence directories under one target), document why in the Makefile comment and update `test_ci_workflow.py` to match.
