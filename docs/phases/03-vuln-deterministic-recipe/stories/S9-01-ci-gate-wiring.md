# Story S9-01 — Phase 3 structural CI gates: cross-plugin isolation + bwrap substrate

**Step:** Step 9 — CI gates, import-linter contracts, performance baselines, bench backfill hook
**Status:** HARDENED (validated 2026-05-20 — see [`_validation/S9-01-ci-gate-wiring.md`](_validation/S9-01-ci-gate-wiring.md))
**Effort:** M
**Depends on:** S6-03 (ships `codegenie.plugins.subgraph`), S7-01..S7-04 (ship the concrete `plugins/{slug}/` directories Contracts B/C operate over), S8-04
**ADRs honored:** ADR-0012 (amends `ALLOWED_BINARIES` with `bwrap` — the binary the Linux CI integration job must `apt-get install` or S4-02 silently `pytest.skip`s instead of running), ADR-0006 (hexagonal `SubprocessJail` Port — the Linux substrate is `bwrap`; CI must provide it), ADR-0011 (honest framing — the CI gate, not "the spirit of the test," is what blocks regression; structural fences are audit + lint, not runtime guarantees)

## Validation notes

Validated: 2026-05-20
Verdict: HARDENED
Findings addressed: 17 total — 7 `block`, 8 `harden`, 2 `nit` (full audit log: [`_validation/S9-01-ci-gate-wiring.md`](_validation/S9-01-ci-gate-wiring.md))

This story drifted hard from shipped reality between authoring and validation. The hardening pass reconciled it; the **goal is unchanged**, the **scope shrank** because sibling stories shipped part of the original surface:

- **Contract A is already shipped** — S1-05 landed the LLM-SDK import-linter fence as *two* contracts (`codegenie.plugins` / `codegenie.transforms`, each `as_packages = true`), shape-pinned by `tests/fence/test_phase3_importlinter_contracts_shape.py`. The original AC-2 "Contract A" (one contract named "Phase 3 packages must not import LLM SDKs") contradicted that shipped shape. Removed from scope; the original TDD red test that asserted the single-contract shape was deleted (it was RED-for-the-wrong-reason and a "fix" would have broken two existing tests).
- **`tests/fence/` + `make check`/`make fence` are already wired** — S1-05 created the directory and the `fence:` recipe already globs `tests/fence/`. The original "create `tests/fence/__init__.py`" + `fence-phase3` target work was struck.
- **CI is 12 jobs, not 6** — Phase 2 (S8-03) added canonical matrixed lanes (`unit`, `integration`, `portfolio`, `mypy`, …) all on 3.11 + 3.12. The original "extend the matrix on `test`/`typecheck`/`fence`" was retargeted to the one real gap: getting the *new* `tests/fence/` Phase 3 gate onto a matrixed lane.
- **Contracts B/C reframed as Open/Closed observables** — the original AC mandated *N pairwise enumerated import-linter rows*, which forces a `pyproject.toml` edit per new plugin (the story itself admitted "Phase 7 adds one more row"). That violates CLAUDE.md "Extension by addition". The ACs are now mechanism-agnostic and carry a zero-config-edit-per-new-plugin observable; the auto-discovering AST fence (`test_plugins_sandbox_path_purity.py`) is the recommended shape.
- **Planted-violation test made mandatory** — the original left "does the gate actually *catch* a violation" as an optional step; for a load-bearing gate that is the only test that proves the gate fires.

## Context

Phase 3 has every invariant Steps 1–8 promised — newtype identifiers, sum-type outcomes, plugin registry kernel, two-stream EventLog with BLAKE3 chain, sandboxed subprocess jail, four recipes, three plugins, ≥10 fixtures, 100-run determinism property, 20 adversarial regressions. Several of those invariants are **already CI-gated**; Step 9's job is to close the remaining structural gaps.

**What is already shipped (do NOT redo it):**

- `make check` runs `lint → typecheck → test → fence` (`Makefile §check`). The `fence` target already globs the whole Phase 3 fence directory: `pytest -q tests/unit/test_pyproject_fence.py tests/fence/ --no-cov` (`Makefile §fence`, S1-05). A new test file dropped under `tests/fence/` is picked up by `make check` and `make fence` **with no Makefile edit** — and `tests/fence/test_fence_target_wiring.py` actively pins that recipe shape, so editing the `fence:` recipe would break a fence test.
- The LLM-SDK import-linter fence for the Phase 3 packages exists as **two** `forbidden` contracts in `pyproject.toml § [tool.importlinter]` — `codegenie.plugins must not import LLM SDKs` and `codegenie.transforms must not import LLM SDKs`, each `as_packages = true`, `forbidden_modules` mirroring `codegenie._fence.FORBIDDEN_LLM_SDKS`. Shipped GREEN by S1-05; shape-pinned by `tests/fence/test_phase3_importlinter_contracts_shape.py`. **S9-01 does not add, rename, merge, or modify these.**
- The CI matrix (3.11 + 3.12 × `ubuntu-24.04`) is in place on the canonical Phase-2 lanes: `lint`, `contract-freeze`, `unit`, `integration`, `portfolio`, `adv-phase02`, `mypy`, `bench`. `mypy` is the canonical matrixed alias of `typecheck`; `unit` + `integration` + `portfolio` are the canonical matrixed test lanes. The workflow has 12 jobs; the legacy single-version `typecheck` / `test` / `fence` jobs survive but are superseded for 3.12 coverage by those canonical lanes.

**What Step 9 still has to land:**

1. **Cross-plugin import isolation (Contract B).** A file under one concrete plugin directory (`plugins/{slug}/`) must not import from a sibling plugin directory. Cross-plugin imports defeat the registry pattern and bifurcate the plugin contract (the anti-pattern `phase-arch-design.md §Gap 3` names for recipe registration). No such gate exists yet.
2. **Subgraph-internals isolation (Contract C).** Plugins consume the subgraph contract via `Plugin.build_subgraph()` only — the `SubgraphNode` Protocol from S6-03. A direct `import codegenie.plugins.subgraph` from a plugin folder reaches into orchestrator internals the Protocol exists to hide. No such gate exists yet. (`codegenie.plugins.subgraph` is shipped by S6-03 — a hard dependency of this story.)
3. **The Linux CI substrate.** S4-02 ships `BwrapAdapter`; its integration tests must FAIL (not `pytest.skip`) when `bwrap` is missing on a Linux runner — silent skips are exactly `phase-arch-design.md §Implementation-level risks #1`. CI needs an explicit `apt-get install -y bubblewrap` step on every Linux job that runs `tests/integration/`, plus a `test_bwrap_present.py` assertion that fails the job loudly on Linux when the binary is missing.
4. **3.12 coverage for the Phase 3 fence directory.** `tests/fence/` currently reaches CI only via the legacy 3.11-only `test` job — the matrixed `unit` lane runs `tests/unit/` only, and the bare-install `fence` job runs only `tests/unit/test_pyproject_fence.py`. The new Phase 3 structural gate must run on 3.11 **and** 3.12.

### A note on mechanism — import-linter vs. AST fence

`import-linter` cannot natively express "no peer import." Expressing Contract B as `import-linter` contracts therefore forces *explicit pairwise enumeration* — one `[[tool.importlinter.contracts]]` row per (plugin, forbidden-peer) pair — and every new plugin then requires a `pyproject.toml` edit. That is a kernel edit per plugin: it violates CLAUDE.md's load-bearing **"Extension by addition"** commitment. It also needs `pyproject.toml § [tool.importlinter].root_packages` extended from `["codegenie"]` to include `plugins` (the concrete plugins live in the repo-root `plugins/` package, not under `codegenie`).

The codebase already has the Open/Closed alternative: `tests/fence/test_plugins_sandbox_path_purity.py` is an **auto-discovering AST-walk fence** — it globs the plugin directories and walks each module's imports, needing zero edits when a new plugin lands. The ACs below are therefore written **mechanism-agnostic** with an explicit zero-config-edit observable; the AST fence is the recommended shape (see Notes for the implementer).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy / CI gates (required jobs)` — `make check`, `make lint-imports`, `make fence`, `test_phase5_contract_snapshot`, `test_three_plugin_contract`, `test_end_to_end_express_cve` are the required jobs Step 9 wires.
  - `../phase-arch-design.md §Implementation-level risks #1` (`bwrap` availability) — the named silent-skip failure mode this story closes.
  - `../phase-arch-design.md §Gap 3` — cross-plugin coupling is a recipe-registration anti-pattern; Contract B is its structural defense.
- **Phase ADRs:**
  - `../ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md` — `bwrap` is in `ALLOWED_BINARIES`; the CI runner must have it installed. `java` is NOT added in Phase 3.
  - `../ADRs/0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md` — Linux Adapter is `BwrapAdapter`; the binary is non-optional on Linux.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — "loud failure when the substrate is missing" is the discipline this story instantiates at the CI layer; fences are audit + lint, not runtime guarantees.
- **Production ADRs:**
  - `../../../production/adrs/0005-no-llm-in-gather-pipeline.md` — the parent pattern the already-shipped LLM-SDK contracts mirror (context only; not in this story's scope).
- **Existing code — read before touching:**
  - `Makefile` — `check`, `lint`, `lint-imports`, `typecheck`, `test`, `fence` targets. `fence` already globs `tests/fence/`; `lint-imports` is deliberately a separate target (see its comment).
  - `.github/workflows/ci.yml` — the **12-job** workflow. The `integration` job is the lane that runs `tests/integration/`. The bare-install `fence` job runs only `test_pyproject_fence.py` — do NOT route Phase 3 fence tests through it.
  - `tests/unit/test_ci_workflow.py` — the YAML-parsing meta-test for the workflow; `_LEGACY_JOBS` / `_PHASE2_JOBS` enumerate the current job set. Extend this; reconcile job names against it first.
  - `tests/fence/test_phase3_importlinter_contracts_shape.py` — the existing meta-fence for the two shipped LLM-SDK contracts. Extend this file if a new import-linter contract is added; do not fork a parallel `test_phase3_importlinter_contracts.py`.
  - `tests/fence/test_plugins_sandbox_path_purity.py` — the auto-discovering AST-walk fence precedent for Contracts B/C.
  - `tests/fence/test_lint_imports_catches_planted_leak.py` — the planted-violation behavior-test precedent for AC-5.
  - `tests/fence/test_fence_target_wiring.py` — pins the `Makefile §fence` recipe shape.
  - `src/codegenie/_fence.py` — `FORBIDDEN_LLM_SDKS` is the source-of-truth set; import it, never re-type it.
  - `plugins/__init__.py` + `plugins/loader.py` — the repo-root plugin package; plugins load via `importlib.import_module("plugins.{slug}.api")`.

## Goal

Wire the remaining Phase 3 structural invariants into CI as hard-block gates: a cross-plugin import-isolation gate and a subgraph-internals-isolation gate, both Open/Closed (a new plugin requires zero edits to the gate's configuration); `bwrap` installed on every Linux CI job that runs the integration suite; S4-02's `BwrapAdapter` integration test FAILS loudly (does not skip) when `bwrap` is missing on Linux; and the new Phase 3 fence test running on the 3.11 + 3.12 matrix.

## Acceptance criteria

- [ ] **AC-1 — Phase 3 fence collection (reconciled).** The new Phase 3 structural-gate fence test(s) land under the existing `tests/fence/` package and are collected by `make check` and `make fence` with **no `Makefile` edit** (the `fence` target already globs `tests/fence/` — `Makefile §fence`, S1-05). Verified by running `make fence` and confirming the new test node IDs appear in pytest output. (validator: reconciled — original "create `tests/fence/__init__.py`" + `fence-phase3` target struck; the directory and wiring already exist.)
- [ ] **AC-2 — Contract A is out of scope.** The LLM-SDK import-linter fence for the Phase 3 packages is **already shipped** (S1-05) as two `forbidden` contracts (`codegenie.plugins must not import LLM SDKs`, `codegenie.transforms must not import LLM SDKs`, each `as_packages = true`) and shape-pinned by `tests/fence/test_phase3_importlinter_contracts_shape.py`. S9-01 does not add, rename, merge, or modify them, and does not duplicate their meta-fence. (validator: reconciled — original "Contract A: one contract" contradicted shipped reality.)
- [ ] **AC-3 — Cross-plugin import isolation (Contract B).** A structural gate fails the build (non-zero `make lint-imports`, OR a RED `tests/fence/` test) when any module under a concrete plugin directory `plugins/{slug}/` imports from a sibling plugin directory `plugins/{other-slug}/`. **Adding a new plugin directory requires zero edits to the gate's configuration** — the gate *discovers* plugin directories, it does not *enumerate* them. Mechanism is the implementer's choice (see Notes); the auto-discovering AST-walk fence is the recommended Open/Closed shape.
- [ ] **AC-4 — Subgraph-internals isolation (Contract C).** A structural gate fails the build when any module under `plugins/{slug}/` imports `codegenie.plugins.subgraph` (plugins consume the subgraph contract via `Plugin.build_subgraph()` only — the `SubgraphNode` Protocol from S6-03). Adding a new plugin requires zero edits to the gate's configuration. If implemented as an `import-linter` `forbidden` contract, `source_modules` MUST be the stable parent package (`source_modules = ["plugins"]`, `as_packages = true`) — never a per-plugin enumeration — and `pyproject.toml § [tool.importlinter].root_packages` MUST be extended to include `plugins`.
- [ ] **AC-5 — Planted-violation behavior test (mandatory, one per gate).** For each of the two gates (B, C), a test plants a deliberate violating import inside a (real or temp) plugin directory, runs the gate, asserts it **FAILS** with a diagnostic naming the gate and the offending import, then removes the planted file in a `finally` block. Modeled on `tests/fence/test_lint_imports_catches_planted_leak.py`. A gate that is *present but inert* (empty forbidden set, unresolved `source_modules`, AST walker that never flags) MUST turn this test RED. This is the only test that proves the gate fires — it is not optional.
- [ ] **AC-6 — bwrap on every integration-running CI job.** `.github/workflows/ci.yml` runs `sudo apt-get update && sudo apt-get install -y bubblewrap` on every Linux CI job that executes `tests/integration/` — concretely the `integration` job, and any other lane whose pytest invocation collects `tests/integration/`. The step runs **before** `pip install`; install failure fails the job. (validator: retargeted from the original "the `test` job" — `tests/integration/` runs in the `integration` lane.)
- [ ] **AC-7 — bwrap-presence fail-loud test.** `tests/integration/test_bwrap_present.py` (NEW): on Linux, a test function asserts `shutil.which("bwrap") is not None` and calls `pytest.fail(...)` — NOT `pytest.skip(...)` — with an actionable message (`Install: apt-get install -y bubblewrap`) when `bwrap` is missing. On macOS the test `pytest.skip`s. The platform decision is a pure helper `_bwrap_required(platform: str) -> bool` that is table-tested (`("linux", True)`, `("darwin", False)`) so the policy is verified on every OS, not only where the branch happens to execute. Resolve import-time vs. function-time: the `shutil.which` check runs inside a test function, not at module import.
- [ ] **AC-8 — S4-02 BwrapAdapter test audited for fail-loud.** S4-02's `BwrapAdapter` integration test is confirmed to FAIL (hard error / `pytest.fail`) — not `pytest.skip` — when `bwrap` is missing on Linux. If it currently skips, it is corrected. This closes `phase-arch-design.md §Implementation-level risks #1` (the named silent-skip failure mode) at the test layer as well as the substrate layer.
- [ ] **AC-9 — Phase 3 fence runs on 3.11 + 3.12.** The new `tests/fence/` Phase 3 gate test executes on both Python 3.11 and 3.12 in CI. Implemented by adding `tests/fence/` to a matrixed lane's pytest invocation OR by adding a matrixed `phase3-fence` job — implementer's choice, stated in the impl. No mechanical matrix expansion of the legacy single-version `typecheck` / `test` / `fence` jobs: 3.12 coverage for typecheck and tests already exists via the canonical matrixed `mypy` / `unit` / `integration` / `portfolio` lanes (S8-03).
- [ ] **AC-10 — `test_ci_workflow.py` extended.** `tests/unit/test_ci_workflow.py` gains **per-job** assertions (not `any()`-across-all-jobs, which the existing matrix test already satisfies via `lint`): (a) the `bubblewrap` install step is present on the integration-running job; (b) the `apt-get` step's index precedes the `pip install` step's index in that job; (c) the new Phase 3 fence test reaches a matrixed lane. Job names are reconciled against the actual 12-job workflow (`_LEGACY_JOBS` / `_PHASE2_JOBS` in the file) before any assertion is written.
- [ ] **AC-11 — meta-fence shape assertions.** Any new `import-linter` contract added by this story (Contract C, if the import-linter mechanism is chosen) is shape-pinned by **extending** `tests/fence/test_phase3_importlinter_contracts_shape.py` — not by a parallel file. The meta-fence asserts, per contract: name present, `type == "forbidden"`, exact `source_modules`, `as_packages` value, and `forbidden_modules` content. Removing or weakening any field turns the meta-fence RED. Any forbidden-LLM-SDK set referenced in test code is imported from `codegenie._fence.FORBIDDEN_LLM_SDKS`; no SDK-name list is re-typed.
- [ ] **AC-12 — `make lint-imports` local-gate decision.** Either `make check` is extended to also run `lint-imports`, OR the story documents (in §Out of scope) why `lint-imports` deliberately remains a separate target (`Makefile §lint-imports` comment). Decide and state it explicitly — the documented local gate must not silently diverge from what CI's `lint` job enforces.
- [ ] **AC-13 — gates green.** `make check` green on a fresh tree; `make lint-imports` green (with `plugins` reachable by `import-linter` if any contract references it); matrix CI green on a draft PR.
- [ ] **AC-14 — typing + lint clean.** `mypy --strict` clean; `ruff check` and `ruff format --check` clean on every touched file.
- [ ] **AC-15 — TDD red test exists, committed, green.** The TDD plan's red tests below exist, were committed RED, and are GREEN at story close.

## Implementation outline

1. **Cross-plugin isolation gate (Contract B) — AC-3.** Add `tests/fence/test_phase3_cross_plugin_isolation.py`. Recommended shape: an auto-discovering AST-walk fence — glob `plugins/*/` (skip non-directories and `__pycache__`), `ast.parse` each `*.py`, collect `import` / `import-from` targets, flag any whose dotted path resolves to `plugins.{other_slug}` where `{other_slug}` is a *different* discovered plugin directory. Zero per-plugin configuration. Mirror the structure of `tests/fence/test_plugins_sandbox_path_purity.py`.
2. **Subgraph-internals isolation gate (Contract C) — AC-4.** Either fold the `codegenie.plugins.subgraph` check into the same AST fence from step 1 (cheapest — one fence covers both), or add an `import-linter` `forbidden` contract with `source_modules = ["plugins"]` + `as_packages = true` and extend `root_packages` to `["codegenie", "plugins"]`. If the import-linter path is taken, extend `test_phase3_importlinter_contracts_shape.py` per AC-11.
3. **Planted-violation tests — AC-5.** One per gate. Plant a violating import inside a plugin directory (use a temp file under a real plugin dir, cleaned in `finally`, or a `tmp_path` plugin fixture), invoke the gate, assert non-zero exit / RED with the gate name + offending import in the diagnostic. Model on `tests/fence/test_lint_imports_catches_planted_leak.py`.
4. **`bubblewrap` install step — AC-6.** Insert `- name: Install bubblewrap (Linux SubprocessJail substrate, ADR-0006 + ADR-0012)\n  run: sudo apt-get update && sudo apt-get install -y bubblewrap` **before** the `Install dev extras` step on the `integration` job (and any other lane that collects `tests/integration/`). Match the existing CI-workflow comment-banner style.
5. **`test_bwrap_present.py` — AC-7.** New module under `tests/integration/`. A pure helper `_bwrap_required(platform: str) -> bool` (`True` for `"linux"`, `False` for `"darwin"`), table-tested. A `test_bwrap_present_on_linux` that, when `_bwrap_required(sys.platform)` is true and `shutil.which("bwrap") is None`, calls `pytest.fail(...)`; otherwise `pytest.skip("Linux substrate only")` on macOS.
6. **S4-02 audit — AC-8.** Grep the S4-02 `BwrapAdapter` integration test. Confirm it hard-fails (not `pytest.skip`) when `bwrap` is missing on Linux. Correct it if it skips. Record the file path + outcome in the attempt log.
7. **3.12 coverage for `tests/fence/` — AC-9.** Add `tests/fence/` to a matrixed lane's pytest invocation, or add a matrixed `phase3-fence` job. Do not touch the legacy `typecheck` / `test` / `fence` job matrices.
8. **`test_ci_workflow.py` extension — AC-10.** Per-job assertions for the `bubblewrap` step, step ordering (compare step indices), and matrixed-lane collection of the Phase 3 fence test. Reconcile job names against the live workflow first.
9. **`make lint-imports` decision — AC-12.** Decide; document the choice.
10. **Documentation.** One-line "Phase 3 CI gates" note in `docs/contributing.md` (the operator runbook proper ships in S9-04).

## TDD plan — red / green / refactor

### Red — write the failing tests first

**`tests/fence/test_phase3_cross_plugin_isolation.py`** — Contracts B + C.

```python
"""Phase 3 S9-01 — structural gate: plugin directories are independently
loadable. A module under plugins/{slug}/ may not import a sibling plugin
(Contract B) nor codegenie.plugins.subgraph (Contract C — the subgraph
contract is consumed via Plugin.build_subgraph() only). Auto-discovering:
adding a new plugin requires zero edits to this file.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

PLUGINS_ROOT = Path(__file__).resolve().parents[2] / "plugins"


def _plugin_slugs() -> list[str]:
    return sorted(
        p.name for p in PLUGINS_ROOT.iterdir()
        if p.is_dir() and p.name != "__pycache__" and (p / "__init__.py").exists()
    )


def _imports_in(module: Path) -> set[str]:
    tree = ast.parse(module.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


def test_no_cross_plugin_imports() -> None:
    """Contract B: a plugin must not import a sibling plugin. Cross-plugin
    imports defeat the registry pattern and bifurcate the plugin contract."""
    slugs = _plugin_slugs()
    assert slugs, "no plugin directories discovered — Contract B cannot be vacuous"
    offenders: list[str] = []
    for slug in slugs:
        peers = {f"plugins.{s}" for s in slugs if s != slug}
        for module in (PLUGINS_ROOT / slug).rglob("*.py"):
            for imp in _imports_in(module):
                if any(imp == peer or imp.startswith(peer + ".") for peer in peers):
                    offenders.append(f"{module}: imports {imp}")
    assert not offenders, "cross-plugin imports forbidden:\n" + "\n".join(offenders)


def test_no_plugin_imports_subgraph_internals() -> None:
    """Contract C: plugins consume the subgraph contract via
    Plugin.build_subgraph() only (the SubgraphNode Protocol, S6-03)."""
    offenders: list[str] = []
    for slug in _plugin_slugs():
        for module in (PLUGINS_ROOT / slug).rglob("*.py"):
            for imp in _imports_in(module):
                if imp == "codegenie.plugins.subgraph" or imp.startswith(
                    "codegenie.plugins.subgraph."
                ):
                    offenders.append(f"{module}: imports {imp}")
    assert not offenders, (
        "plugins must not import codegenie.plugins.subgraph directly:\n"
        + "\n".join(offenders)
    )
```

**`tests/fence/test_phase3_cross_plugin_planted.py`** — AC-5 behavior proof. Plants a real violating `.py` inside a discovered plugin directory, runs the gate's checker, asserts it is caught, removes the file in `finally`. (One planted case for Contract B, one for Contract C.)

**`tests/integration/test_bwrap_present.py`** — AC-7.

```python
import shutil
import sys

import pytest


def _bwrap_required(platform: str) -> bool:
    """bwrap is the Linux SubprocessJail substrate (ADR-0006); it is not
    required on macOS, which uses sandbox-exec."""
    return platform.startswith("linux")


@pytest.mark.parametrize(
    ("platform", "expected"), [("linux", True), ("darwin", False)]
)
def test_bwrap_required_policy(platform: str, expected: bool) -> None:
    """The platform→requirement decision is verified on every OS — not only
    where the live branch happens to execute."""
    assert _bwrap_required(platform) is expected


def test_bwrap_present_on_linux() -> None:
    """Missing bwrap would let S4-02's integration test pytest.skip silently —
    the exact failure mode phase-arch-design.md §Implementation-level risks #1
    names. Fail loud (ADR-0011)."""
    if not _bwrap_required(sys.platform):
        pytest.skip("Linux substrate only (ADR-0006)")
    if shutil.which("bwrap") is None:
        pytest.fail(
            "bwrap missing on Linux runner. Install: apt-get install -y bubblewrap. "
            "See phase-arch-design.md §Implementation-level risks #1."
        )
```

**`tests/unit/test_ci_workflow.py`** — AC-10. New per-job assertions: the integration job has a `bubblewrap` install step; that step's index precedes the `pip install` step's index; the Phase 3 fence test reaches a matrixed lane.

**Why they fail first:** the cross-plugin / subgraph gates do not exist (the planted-violation tests have nothing to catch them with); `bubblewrap` is not installed in any CI job; `test_ci_workflow.py` has no bwrap assertions. **Determinism note:** `test_bwrap_present_on_linux` *skips* on macOS — it does not contribute a RED there. The deterministic RED on any OS comes from the cross-plugin gate tests, the planted-violation tests, and the `test_ci_workflow.py` assertions.

### Green — minimal pass

- Add `test_phase3_cross_plugin_isolation.py` (the gate) + the planted-violation tests.
- Add the `apt-get install -y bubblewrap` step to the `integration` job; add `tests/fence/` to a matrixed lane (or a `phase3-fence` job).
- Add `test_bwrap_present.py`; install `bubblewrap` locally (or run on a CI-provisioned runner) to make it green.
- Extend `test_ci_workflow.py`.
- If the import-linter mechanism is chosen for Contract C: add the contract + extend `test_phase3_importlinter_contracts_shape.py` + extend `root_packages`.

### Refactor

- If any forbidden-LLM-SDK set is referenced in new test code, import `codegenie._fence.FORBIDDEN_LLM_SDKS` — do not re-type the list (it already exists in `_fence.py` and in the two shipped contracts; a third copy crosses the rule-of-three).
- Edge cases from §Edge cases that touch this code: E10 (universal fallback substitution while a concrete plugin import-fails) — Contract B's cross-plugin isolation is the structural defense; the runtime defense ships in S2-03 / S7-04.

## Files to touch

| Path | Why |
|---|---|
| `.github/workflows/ci.yml` | Add `apt-get install -y bubblewrap` to the `integration` job (and any other `tests/integration/`-collecting lane); ensure `tests/fence/` runs on a matrixed lane (AC-6, AC-9). Match the existing `# ---` comment-banner style. |
| `tests/fence/test_phase3_cross_plugin_isolation.py` | NEW — the auto-discovering cross-plugin + subgraph-internals gate (AC-3, AC-4). |
| `tests/fence/test_phase3_cross_plugin_planted.py` | NEW — planted-violation behavior proof, one case per gate (AC-5). |
| `tests/integration/test_bwrap_present.py` | NEW — assert `bwrap` on Linux; fail loud (not skip); pure-helper platform policy table-tested (AC-7). |
| `tests/unit/test_ci_workflow.py` | Extend with per-job assertions for the `bubblewrap` step, step ordering, and matrixed-lane collection (AC-10). |
| `pyproject.toml` | ONLY if Contract C uses the import-linter mechanism: add the contract + extend `root_packages` to include `plugins` (AC-4). Not needed if Contract C folds into the AST fence. |
| `tests/fence/test_phase3_importlinter_contracts_shape.py` | EXTEND — only if a new import-linter contract is added (AC-11). Do not fork a parallel file. |
| `Makefile` | ONLY if AC-12 decides to add `lint-imports` to the `check` chain. The `fence` target is NOT touched — it already globs `tests/fence/`. |
| `docs/contributing.md` | One-line "Phase 3 CI gates" note (runbook proper ships in S9-04). |

## Out of scope

- **Contract A (no LLM SDK under Phase 3 packages)** — already shipped by S1-05 as two `import-linter` contracts, shape-pinned by `test_phase3_importlinter_contracts_shape.py`. Not touched.
- **`tests/fence/__init__.py` and `make fence` / `make check` wiring** — already shipped by S1-05; the directory exists and is globbed.
- **CI matrix on the legacy `typecheck` / `test` / `fence` jobs** — 3.12 coverage already exists via the canonical matrixed `mypy` / `unit` / `integration` / `portfolio` lanes (S8-03). Only the *new* `tests/fence/` Phase 3 gate needs matrix wiring (AC-9).
- **Event-taxonomy completeness fence** and the **`$0.00` LLM-spend assertion** — S9-02.
- **Bench harness + rolling baseline** and the **`BenchReplayable` backfill consumer** — S9-03 / S9-04.
- **Operator runbook** — S9-04.
- **macOS `sandbox-exec` install step** — N/A on GitHub macOS runners (`sandbox-exec` ships with the OS); Phase 3 macOS integration tests run nightly per `phase-arch-design.md §Testing strategy`.
- **`java` install step (OpenRewrite)** — Phase 7 amends `ALLOWED_BINARIES` with `java`; Phase 3 scaffolds `OpenRewriteRecipeEngine` but does not invoke it, so the runner needs no JDK.
- **`make ci-locally` convenience target** — speculative (Rule 2); a `docs/contributing.md` one-liner suffices.

## Notes for the implementer

- **Precondition — this story has hard upstream dependencies.** Contract C forbids importing `codegenie.plugins.subgraph`, a module shipped by **S6-03**. Contracts B/C operate over the concrete `plugins/{slug}/` directories, shipped by **S7-01..S7-04**. None of those exist at validation time (the repo-root `plugins/` currently holds only `PLUGINS.lock` + `__init__.py`). Per CLAUDE.md the Phase 3 `S5-02 → S8` engine chain is BLOCKED pending a `/phase-architect` decision — **S9-01 cannot be executed until S6-03 and S7-01..S7-04 are GREEN.** If picked up before then, mark it `BLOCKED` like its predecessors; do not ship a gate pointing at a phantom module (`import-linter` errors hard on an unresolvable `forbidden_modules` / `source_modules` entry).
- **Prefer the AST fence over import-linter for Contracts B/C.** `import-linter` cannot express "no peer," so a cross-plugin contract there means *N pairwise enumerated rows* and a `pyproject.toml` edit per new plugin — a kernel edit that breaks "Extension by addition" (CLAUDE.md). The auto-discovering AST-walk fence globs `plugins/*/` and needs zero edits when a fourth plugin lands. `tests/fence/test_plugins_sandbox_path_purity.py` is the precedent — same structure, same directory. The story's ACs are mechanism-agnostic, but the AST fence is strongly recommended; the zero-config-edit clause in AC-3/AC-4 is the observable that must hold whichever mechanism is chosen.
- **If you do use import-linter for Contract C**, `source_modules` must be the stable parent package (`["plugins"]`, `as_packages = true`) so new sub-packages are auto-covered — never a per-plugin list — and `root_packages` must gain `plugins`. The existing `codegenie.plugins must not import LLM SDKs` contract (`source_modules = ["codegenie.plugins"]`, `as_packages = true`) is the shape to mirror.
- **The planted-violation test is the load-bearing one.** Every other gate test parses config or walks the AST and confirms the gate *exists* — only the planted test confirms the gate *fires*. A contract present but mis-shaped (typo'd `source_modules` resolving to nothing, an AST walker that never flags) passes every presence test and catches nothing. Make AC-5 mandatory; copy `test_lint_imports_catches_planted_leak.py`'s plant→run→assert→`finally`-cleanup structure.
- **`shutil.which` is the right primitive** for `test_bwrap_present.py`. Subprocess-invoking `bwrap --version` would catch broken-binary cases too but adds startup cost and itself ENOENT-fails — `shutil.which` is the contract-correct fast path.
- **Reconcile job names before editing `test_ci_workflow.py`.** The workflow has 12 jobs; the file's `_LEGACY_JOBS` / `_PHASE2_JOBS` sets are authoritative. The integration suite runs in the `integration` lane, not the legacy `test` job — the `bubblewrap` step must land where `tests/integration/` actually runs.
- **The `bench-collection-guard` step** in the `test` job (S5-01) collects exactly 3 bench tests. S9-03 adds more; that guard is relaxed **in S9-03**, not here. This story preserves the count at 3.
- **`apt-get update` before `apt-get install`** — a bare `install` 404s intermittently on fresh GitHub runners with pruned apt indices. Always pair them.
- **Do not touch the `Makefile §fence` recipe.** `tests/fence/test_fence_target_wiring.py` and the Phase-0 `test_fence_recipe_invokes_pytest_on_fence_test_path` pin its exact substring; a new `tests/fence/` file is collected with no edit.
