# Story S1-06 — import-linter contracts mirroring the fence

**Step:** Step 1 — Establish Phase-4 type substrate + path-scoped fence amendment
**Status:** HARDENED
**Effort:** S
**Depends on:** S1-05
**ADRs honored:** ADR-0003 (path-scoped fence — `import-linter` is the *lint-time* belt-and-suspenders alongside the *test-time* pytest fence)

## Validation notes

Validated: 2026-05-21
Verdict: HARDENED
Findings addressed: 12 — 4 block, 7 harden, 1 nit. Findings verified directly against the installed `import-linter 2.11` (no research needed).

Changes applied:
- **Block (C1/C2): `as_packages = true` added to all four contracts.** AC-1 and the TDD-plan TOML omitted it. import-linter treats each `source_modules` entry as a *single module* unless `as_packages = true` — without it only each package's `__init__.py` is scanned, so a probe at `codegenie/probes/foo.py` importing `anthropic` slips straight through. The Phase-3/Phase-7 LLM-SDK contracts already in `pyproject.toml` set it explicitly; `test_phase3_importlinter_contracts_shape.py` pins it as load-bearing.
- **Block (V1): AC-4's "forward-clean whitelist" premise was mechanically false — corrected.** Verified: the `forbidden` contract defaults `unmatched_ignore_imports_alerting = ERROR` (`importlinter/contracts/forbidden.py`). A pre-populated `ignore_imports` naming a not-yet-existent module (`codegenie.rag.store -> chromadb`) makes `lint-imports` **ERROR** with "Could not find import" — `make lint-imports` would not exit 0. Contracts #2/#3/#4 now ship with `ignore_imports` omitted; each downstream story (S3-02, S4-01, S4-03) appends its own edge when it lands the real import — true extension-by-addition.
- **Block (T1): the TDD-plan negative test invoked a non-existent entrypoint.** `python -m importlinter` fails ("No module named importlinter.__main__"); there is no `lint` subcommand — both verified. `assert returncode != 0` would have passed for the wrong reason. Corrected to the `lint-imports` console script.
- **Block (C4): cross-story hazard surfaced (Rule 7).** S1-05's narrowing of `FORBIDDEN_LLM_SDKS` breaks `test_phase3/7_importlinter_contracts_shape.py` (they assert `set(forbidden_modules) == FORBIDDEN_LLM_SDKS`). `make check` cannot be green until the Phase-3/Phase-7 contracts are reconciled — folded into AC-8 + Notes.
- **Harden (T2/D1): added a static shape-drift test as the primary mutation guard**, mirroring the established precedent `test_phase3/7_importlinter_contracts_shape.py` (Rule 11). Phase-3/Phase-7 shipped *only* a shape test — no live-fire test, no fixtures. The brittle synthetic-tmp-pyproject test is reframed as optional (AC-7).
- **Harden (D2): the shape test couples the contracts to one source of truth** — expected `forbidden_modules`/`source_modules` are derived from the Phase-4 fence constants S1-05 lands.
- **Harden (V2): `include_external_packages = true` is now asserted by the shape test** (was only "verified present").
- **Harden (T3): removed the `tomli_w` dependency** — it is only a transitive dep of `pip-audit`, not declared. The shape test uses stdlib `tomllib` (read-only).
- **Harden (C3): corrected the stale Context claim** — `pyproject.toml` has six `forbidden` contracts (not two); the relevant precedent is the Phase-3/Phase-7 LLM-SDK contracts.
- **Harden (T4): noted the env / `sys.path` collision risk** in the optional live-fire test.
- **Nit (D3): noted the path-vs-module-name translation** the shape test needs when coupling to `GATHER_PIPELINE_PATHS`.

Full audit log: `_validation/S1-06-import-linter-contracts.md`

## Context

The path-scoped fence (S1-05) is a pytest gate — runtime evidence that the runtime closure is clean. ADR-0003's tradeoff column names import-linter as the **complementary lint-time enforcement**: "both `import-linter` (lint-time) and pytest (test-time) enforce the same boundary — belt-and-suspenders." If a contributor runs `pre-commit` but skips pytest locally, the import-linter contracts in `pyproject.toml § [tool.importlinter]` are what catch a regression at PR time before CI ever runs. This story mirrors S1-05's four assertions as four `import-linter` `forbidden` contracts, and ships a deliberate-violation fixture proving the contract fires with a diagnostic the next reader can act on.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap analysis → Gap 5` — "`import-linter` contracts (`.importlinter`) enforce the same edges at lint time."
  - `../phase-arch-design.md §Testing strategy → CI gates` — `make lint-imports` is a CI gate.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-path-scoped-fence-amendment.md` §Decision — the four-edge boundary.
  - `../ADRs/0003-path-scoped-fence-amendment.md` §Tradeoffs — "belt-and-suspenders" framing.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `pyproject.toml § [tool.importlinter]` — existing root config (`root_packages`, `include_external_packages = true`) and **six** `forbidden` contracts: two Phase-0 cold-start contracts (`codegenie.cli`, `codegenie` `__init__`), one ADR-0013 amendment (`codegenie.types.identifiers` ↛ `codegenie.probes`), and **two Phase-3 + one Phase-7 LLM-SDK contracts**. The Phase-3/Phase-7 LLM-SDK contracts (`codegenie.plugins`/`codegenie.transforms`/`codegenie.primitives.vuln_provenance` must not import LLM SDKs) — each with `as_packages = true` and a paired shape-drift test — are **the precedent this story mirrors**, not the cold-start pair. Mirror their schema; do not edit existing contracts except per AC-8 (the S1-05 narrowing reconciliation).
  - `tests/fence/test_phase3_importlinter_contracts_shape.py` and `tests/fence/test_phase7_importlinter_contracts_shape.py` — **the established convention for a "ship an import-linter contract" story**: a static `tomllib`-read shape-drift test. This story's AC-6 mirrors it. Phase 3/7 shipped *only* such a test — no live-fire test, no `_fixtures` directory.
  - `Makefile` `lint-imports` target — confirms `make lint-imports` runs `lint-imports --config pyproject.toml --no-cache`.

## Goal

Add four `forbidden` import-linter contracts to `pyproject.toml § [tool.importlinter.contracts]` so `make lint-imports` enforces the same path-scoped admissions as the pytest fence in S1-05 — at lint time, before tests run.

## Acceptance criteria

### Contracts landed

- [ ] AC-1 — `pyproject.toml § [tool.importlinter.contracts]` ships four new `[[tool.importlinter.contracts]]` blocks, **each `type = "forbidden"` and each carrying `as_packages = true`**:
  1. **`gather pipeline must not import phase-4 admitted or forbidden packages`** — `source_modules = ["codegenie.probes", "codegenie.coordinator", "codegenie.cache", "codegenie.output", "codegenie.schema"]`; `as_packages = true`; `forbidden_modules` is the `PHASE4_ADMITTED_PACKAGES ∪ PHASE4_STILL_FORBIDDEN` union in **import-name** spelling: `["anthropic", "chromadb", "fastembed", "onnxruntime", "langgraph", "openai", "langchain", "transformers", "sentence_transformers", "torch"]` (note `sentence_transformers` with an underscore — import-linter matches module names, not PyPI distribution names).
  2. **`anthropic may be imported only by the leaf adapter`** — `source_modules = ["codegenie"]`; `as_packages = true`; `forbidden_modules = ["anthropic"]`. **`ignore_imports` is omitted (empty) by this story** — see AC-4. S3-02 appends `"codegenie.fallback.leaf.anthropic_adapter -> anthropic"` when it lands the real import.
  3. **`chromadb may be imported only under codegenie.rag`** — `source_modules = ["codegenie"]`; `as_packages = true`; `forbidden_modules = ["chromadb"]`. `ignore_imports` omitted; S4-03 appends `"codegenie.rag.store -> chromadb"` when it lands `store.py`.
  4. **`fastembed and onnxruntime may be imported only under codegenie.rag`** — `source_modules = ["codegenie"]`; `as_packages = true`; `forbidden_modules = ["fastembed", "onnxruntime"]`. `ignore_imports` omitted; S4-01 appends the `codegenie.rag.embedder -> fastembed` / `-> onnxruntime` edges.
  - **validator (block C1/C2):** every earlier version of this AC and the TDD-plan TOML omitted `as_packages = true` on one or more contracts. Without it import-linter scans only each package's `__init__.py`, so a violating submodule (`codegenie/probes/foo.py`) is invisible to the contract. The Phase-3/Phase-7 LLM-SDK contracts in `pyproject.toml` set it explicitly and `test_phase3_importlinter_contracts_shape.py` pins it as load-bearing — mirror that.
- [ ] AC-2 — Each contract carries a `name` field naming ADR-0003 (mirror the Phase-3 contract style: `name = "ADR-0003: gather pipeline must not import phase-4 admitted or forbidden packages"`).
- [ ] AC-3 — `include_external_packages = true` remains present at the `[tool.importlinter]` root (required for `forbidden_modules` to name third-party packages). AC-6's shape test **asserts** it — it is not merely "verified by eye."

### Verification — green path

- [ ] AC-4 — `make lint-imports` exits 0 against the current source tree. The four contracts ship with `ignore_imports` **omitted (empty)**, so there are zero offenders and — critically — zero *unmatched* ignore entries. **validator (block V1):** verified against import-linter 2.11 — the `forbidden` contract defaults `unmatched_ignore_imports_alerting = ERROR` (`importlinter/contracts/forbidden.py`). A pre-populated `ignore_imports` naming a not-yet-existent module (`codegenie.rag.store -> chromadb`) makes `lint-imports` **ERROR** with "Could not find import", so the earlier "forward-clean whitelist" plan would have broken `make lint-imports` on day one. Empty `ignore_imports` now + each downstream story appending its own edge is the correct extension-by-addition path.
- [ ] AC-5 — `pyproject.toml` `[tool.importlinter]` config parses clean: `lint-imports --config pyproject.toml --debug` reports the four new contracts with no parse warning.

### Verification — shape-drift test (primary mutation guard)

- [ ] AC-6 — `tests/fence/test_phase4_importlinter_contracts_shape.py` lands, **mirroring the established precedent `tests/fence/test_phase3_importlinter_contracts_shape.py` / `…_phase7_…`** (Rule 11 — match the convention; this is the third story in that family). It statically reads `pyproject.toml` via stdlib `tomllib` and asserts, for each of the four new contracts (parametrized by `name`):
  1. the contract is present;
  2. `type == "forbidden"`;
  3. `as_packages is True` (the C1/C2 mutation guard — a silent drop of this flag fires the test);
  4. `source_modules` equals the expected list;
  5. `forbidden_modules` (as a set) equals the expected set;
  6. and, once, that `include_external_packages is True` at the `[tool.importlinter]` root (AC-3).
  - **Source-of-truth coupling (validator D2):** the expected `forbidden_modules` / `source_modules` are **derived from the Phase-4 fence constants** `PHASE4_ADMITTED_PACKAGES`, `PHASE4_STILL_FORBIDDEN`, `GATHER_PIPELINE_PATHS` that S1-05 lands in `tests/fence/test_pyproject_fence_phase4.py` — imported, not re-typed as string literals. A future widening/narrowing of the path-scoped pytest fence then immediately changes this test's expectation, so the lint-time fence and the test-time fence cannot silently drift apart. `GATHER_PIPELINE_PATHS` holds path strings (`"src/codegenie/probes/"`); contract #1's `source_modules` holds dotted module names (`"codegenie.probes"`) — the test translates path → module (`removeprefix("src/")`, `rstrip("/")`, `replace("/", ".")`).
- [ ] AC-7 — *(optional, complementary)* A live-fire negative test that plants a violator and runs the **`lint-imports` console script** to prove a contract actually rejects a violation. If included, it MUST: resolve the `lint-imports` console script via `shutil.which("lint-imports")` — NOT `python -m importlinter` (no `__main__`, no `lint` subcommand — verified); pass `--config` and `--no-cache`; and merge `os.environ` into any `env=` it sets (a bare `env={"PYTHONPATH": …}` drops `PATH`/`HOME` and risks the real editable-installed `codegenie` colliding with the synthetic tree on `sys.path`). **This test is optional:** AC-6's shape test is the always-on mutation guard, so omitting AC-7 — or deferring it to the S3-06 runbook if it proves brittle on CI — is NOT a coverage regression. Record the choice in the attempt log.

### Hygiene

- [ ] AC-8 — `make check` is green. **validator (block C4 — cross-story hazard, Rule 7):** S1-05 narrows `FORBIDDEN_LLM_SDKS` (removes `anthropic`, adds `sentence-transformers`/`torch`). That makes `tests/fence/test_phase3_importlinter_contracts_shape.py::test_contract_forbids_exactly_the_llm_sdk_closure` and the `…_phase7_…` equivalent **fail** — they assert `set(forbidden_modules) == FORBIDDEN_LLM_SDKS`, and the Phase-3/Phase-7 contracts still list the old 5-member set including `anthropic`; the new distribution-named `sentence-transformers` (hyphen) also can never set-equal an import-name `forbidden_modules` entry (`sentence_transformers`, underscore). `make check` cannot be green until that is reconciled. S1-06 owns import-linter contracts, so reconciling the Phase-3/Phase-7 contracts **and** their shape tests' set-comparison (canonicalize separators, or compare the import-name projection) is in-scope here — or escalate per the Notes. Log it in the attempt log either way.
- [ ] AC-9 — `ruff check`, `ruff format --check`, `mypy --strict` clean on touched files.
- [ ] AC-10 — The TDD plan's red test (`test_phase4_importlinter_contracts_shape.py`) exists, is committed, was red before the contracts landed, and is green after.

## Implementation outline

1. Read existing `pyproject.toml § [tool.importlinter]` to confirm root config (`root_packages`, `include_external_packages = true`) and study the Phase-3/Phase-7 LLM-SDK contracts as the schema precedent.
2. Land the red test first: `tests/fence/test_phase4_importlinter_contracts_shape.py`, mirroring `test_phase3_importlinter_contracts_shape.py`. It is red until step 3 lands the contracts (`_load()` returns an empty dict, so `test_all_four_phase4_contracts_present` fails).
3. Append the four new `[[tool.importlinter.contracts]]` blocks per AC-1 — **all with `as_packages = true`, all with `ignore_imports` omitted** — grouped under an ADR-0003 comment header.
4. Run `make lint-imports` locally; verify exit 0 (AC-4). Run the shape test; verify green (AC-6/AC-10).
5. Run `make check`. If `test_phase3/7_importlinter_contracts_shape.py` is red from the S1-05 `FORBIDDEN_LLM_SDKS` narrowing (AC-8 / block C4), reconcile the Phase-3/Phase-7 contracts and those shape tests' set-comparison, and log the cross-story reconciliation in the attempt log.
6. *(Optional — AC-7)* If a live-fire negative test is wanted, add it invoking the `lint-imports` console script against a planted violator. If it proves brittle on CI, drop it — the shape test is the always-on guard — and record the choice in the attempt log.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/fence/test_phase4_importlinter_contracts_shape.py` — a static `tomllib`-read shape-drift test, **structurally a copy of `tests/fence/test_phase3_importlinter_contracts_shape.py`** with the Phase-4 contract names and expected sets. No subprocess, no `tomli_w`, no fixtures.

```python
"""Shape-pin for the four Phase 4 import-linter contracts in ``pyproject.toml``.

Audit + lint enforcement, NOT runtime (ADR-0003 — the lint-time belt-and-
suspenders alongside the pytest fence ``tests/fence/test_pyproject_fence_phase4.py``).
If a future cleanup silently drops ``as_packages = true``, narrows
``forbidden_modules``, retargets ``source_modules``, or removes
``include_external_packages``, this test fires.

The expected sets are DERIVED from the Phase-4 fence constants so the lint-time
contracts and the test-time fence stay coupled to one source of truth.
"""
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Final

import pytest

# Source of truth — the same constants the pytest path-scoped fence uses (S1-05).
from tests.fence.test_pyproject_fence_phase4 import (
    GATHER_PIPELINE_PATHS,
    PHASE4_ADMITTED_PACKAGES,
    PHASE4_STILL_FORBIDDEN,
)

_PYPROJECT: Final[Path] = Path("pyproject.toml")

_GATHER: Final = (
    "ADR-0003: gather pipeline must not import phase-4 admitted or forbidden packages"
)
_ANTHROPIC: Final = "ADR-0003: anthropic may be imported only by the leaf adapter"
_CHROMADB: Final = "ADR-0003: chromadb may be imported only under codegenie.rag"
_EMBED: Final = (
    "ADR-0003: fastembed and onnxruntime may be imported only under codegenie.rag"
)
_NAMES: Final[tuple[str, ...]] = (_GATHER, _ANTHROPIC, _CHROMADB, _EMBED)


def _path_to_module(p: str) -> str:
    """`"src/codegenie/probes/"` -> `"codegenie.probes"` (D3 — path vs. module)."""
    return p.removeprefix("src/").rstrip("/").replace("/", ".")


_EXPECTED_SOURCE_MODULES: Final[dict[str, list[str]]] = {
    _GATHER: sorted(_path_to_module(p) for p in GATHER_PIPELINE_PATHS),
    _ANTHROPIC: ["codegenie"],
    _CHROMADB: ["codegenie"],
    _EMBED: ["codegenie"],
}
_EXPECTED_FORBIDDEN: Final[dict[str, set[str]]] = {
    _GATHER: set(PHASE4_ADMITTED_PACKAGES) | set(PHASE4_STILL_FORBIDDEN),
    _ANTHROPIC: {"anthropic"},
    _CHROMADB: {"chromadb"},
    _EMBED: {"fastembed", "onnxruntime"},
}


def _load() -> dict[str, dict[str, object]]:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    contracts = data.get("tool", {}).get("importlinter", {}).get("contracts", [])
    return {c["name"]: c for c in contracts if c.get("name") in _NAMES}


def test_all_four_phase4_contracts_present() -> None:
    missing = set(_NAMES) - set(_load())
    assert not missing, f"Missing Phase-4 import-linter contracts: {missing}"


def test_root_includes_external_packages() -> None:
    """AC-3 — required so `forbidden_modules` may name third-party packages."""
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    assert data["tool"]["importlinter"].get("include_external_packages") is True


@pytest.mark.parametrize("name", _NAMES)
def test_contract_is_forbidden_type(name: str) -> None:
    assert _load()[name].get("type") == "forbidden"


@pytest.mark.parametrize("name", _NAMES)
def test_contract_uses_as_packages_true(name: str) -> None:
    """AC-1 (C1/C2) — without `as_packages = true` only each package
    __init__.py is scanned; a violating submodule slips through."""
    assert _load()[name].get("as_packages") is True, (
        f"Contract `{name}` must declare `as_packages = true`."
    )


@pytest.mark.parametrize("name", _NAMES)
def test_contract_source_modules(name: str) -> None:
    got = _load()[name].get("source_modules")
    assert isinstance(got, list)
    assert sorted(got) == _EXPECTED_SOURCE_MODULES[name]


@pytest.mark.parametrize("name", _NAMES)
def test_contract_forbidden_modules_mirror_the_fence(name: str) -> None:
    """AC-1 (D2) — `forbidden_modules` mirrors the Phase-4 fence constants.
    Drift = the lint-time fence silently diverges from the pytest fence."""
    got = _load()[name].get("forbidden_modules")
    assert isinstance(got, list)
    assert set(got) == _EXPECTED_FORBIDDEN[name], (
        f"Contract `{name}` forbidden_modules drift: {set(got)} != "
        f"{_EXPECTED_FORBIDDEN[name]}"
    )
```

State why it fails: the four new contracts don't exist in `pyproject.toml` yet, so `_load()` returns an empty dict and `test_all_four_phase4_contracts_present` (plus every parametrized case, which `KeyError`s on the missing contract) fails.

> **Import-path note (D2):** the test imports `GATHER_PIPELINE_PATHS` / `PHASE4_ADMITTED_PACKAGES` / `PHASE4_STILL_FORBIDDEN` from `tests/fence/test_pyproject_fence_phase4.py` — where S1-05 lands them. If S1-05's executor instead places those constants in `tests/fence/_phase4_scanner.py` (the shared test-package-private helper S1-05 also creates), update the `from …` line to match. Either way the constants must be **imported**, never re-typed — that import IS the drift coupling.

### Green — make it pass

1. Append the four new `[[tool.importlinter.contracts]]` blocks to `pyproject.toml`, grouped under an ADR-0003 comment header. Each carries `name`, `type = "forbidden"`, `source_modules`, **`as_packages = true`**, and `forbidden_modules`. **No `ignore_imports`** (AC-4).
2. Run `make lint-imports` locally; verify exit 0.
3. Run the shape test; verify all cases green.

The four `pyproject.toml` blocks (illustrative — final exact form lives in `pyproject.toml`):

```toml
# ---------------------------------------------------------------------------
# Phase 4 (ADR-0003) path-scoped admissions — the lint-time belt-and-suspenders
# alongside the pytest fence tests/fence/test_pyproject_fence_phase4.py (S1-05).
# `ignore_imports` is intentionally absent: the admitted edges
# (anthropic_adapter -> anthropic, rag.store -> chromadb, rag.embedder ->
# fastembed/onnxruntime) do not exist yet. import-linter's `forbidden` contract
# defaults `unmatched_ignore_imports_alerting = ERROR`, so whitelisting a
# not-yet-existent edge would break `make lint-imports`. Each downstream story
# (S3-02, S4-01, S4-03) appends its own `ignore_imports` line when it lands the
# real import — extension by addition, audit trail stays honest.
# ---------------------------------------------------------------------------

[[tool.importlinter.contracts]]
name = "ADR-0003: gather pipeline must not import phase-4 admitted or forbidden packages"
type = "forbidden"
as_packages = true
source_modules = [
  "codegenie.probes",
  "codegenie.coordinator",
  "codegenie.cache",
  "codegenie.output",
  "codegenie.schema",
]
forbidden_modules = [
  "anthropic", "chromadb", "fastembed", "onnxruntime",
  "langgraph", "openai", "langchain", "transformers",
  "sentence_transformers", "torch",
]

[[tool.importlinter.contracts]]
name = "ADR-0003: anthropic may be imported only by the leaf adapter"
type = "forbidden"
as_packages = true
source_modules = ["codegenie"]
forbidden_modules = ["anthropic"]
# ignore_imports omitted — S3-02 appends `codegenie.fallback.leaf.anthropic_adapter -> anthropic`.

[[tool.importlinter.contracts]]
name = "ADR-0003: chromadb may be imported only under codegenie.rag"
type = "forbidden"
as_packages = true
source_modules = ["codegenie"]
forbidden_modules = ["chromadb"]
# ignore_imports omitted — S4-03 appends `codegenie.rag.store -> chromadb`.

[[tool.importlinter.contracts]]
name = "ADR-0003: fastembed and onnxruntime may be imported only under codegenie.rag"
type = "forbidden"
as_packages = true
source_modules = ["codegenie"]
forbidden_modules = ["fastembed", "onnxruntime"]
# ignore_imports omitted — S4-01 appends `codegenie.rag.embedder -> fastembed` / `-> onnxruntime`.
```

### Refactor — clean up

- Confirm `include_external_packages = true` remains at the `[tool.importlinter]` root (required so `forbidden_modules` may name third-party packages — `pyproject.toml` already has this; do not remove).
- Reconcile `make check`: if the S1-05 `FORBIDDEN_LLM_SDKS` narrowing has left `test_phase3/7_importlinter_contracts_shape.py` red (AC-8 / block C4), fix the Phase-3/Phase-7 contracts and those shape tests' set-comparison, and log the cross-story reconciliation in the attempt log.
- Edge cases enumerated in arch §Edge cases that touch this code: #15 (extras vs. dependencies — import-linter scans the actual import graph; extras are irrelevant here).

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` | Append four `[[tool.importlinter.contracts]]` blocks (all `as_packages = true`, all `ignore_imports` omitted) under an ADR-0003 comment header. |
| `tests/fence/test_phase4_importlinter_contracts_shape.py` | NEW — static `tomllib`-read shape-drift test mirroring `test_phase3_importlinter_contracts_shape.py`. The primary mutation guard. |
| `tests/fence/test_phase3_importlinter_contracts_shape.py` | Likely — reconcile `test_contract_forbids_exactly_the_llm_sdk_closure` with the S1-05-narrowed `FORBIDDEN_LLM_SDKS` (AC-8 / block C4). |
| `tests/fence/test_phase7_importlinter_contracts_shape.py` | Likely — same reconciliation as the Phase-3 shape test. |
| Phase-3/Phase-7 contracts in `pyproject.toml` | Likely — update their `forbidden_modules` to the post-S1-05 LLM-SDK set (AC-8 / block C4). |

## Out of scope

- **The pytest path-scoped fence test** — S1-05 (this story is the lint-time complement).
- **Narrowing `codegenie._fence.FORBIDDEN_LLM_SDKS` itself** — S1-05. This story only reconciles the *import-linter contracts* (and their shape tests) that mirror it (AC-8).
- **Populating the `ignore_imports` whitelists** — the contracts ship with `ignore_imports` empty; S3-02 (anthropic edge), S4-01 (fastembed/onnxruntime edges), S4-03 (chromadb edge) each append their own edge when they land the real import.
- **`tests/fence/test_kernel_frozen.py`** — S1-07.
- **`BudgetToken` import-linter contract restricting to `{tier.py, leaf/anthropic_adapter.py}`** — S2-05 (different contract, different forbidden symbol).
- **`_phase4_local_capability_mint` import-linter contract restricting to `{src/codegenie/gates/, src/codegenie/rag/ingest.py}`** — S4-06.
- **Adding `langgraph` to the lint-time forbidden set explicitly** — already covered by the gather-pipeline contract (which lists all PHASE4_STILL_FORBIDDEN packages); a dedicated contract is overkill until Phase 6 amends.

## Notes for the implementer

- **`as_packages = true` is load-bearing on all four contracts (block C1/C2).** Without it import-linter treats each `source_modules` entry as a *single module* and scans only its `__init__.py` — a violating submodule (`codegenie/probes/foo.py` doing `import anthropic`) is completely invisible to the contract. The Phase-3/Phase-7 LLM-SDK contracts already in `pyproject.toml` set it explicitly; the Phase-3 shape test docstring calls it "load-bearing." Do not omit it; the shape test (`test_contract_uses_as_packages_true`) catches a silent drop.
- **⚠ Ship `ignore_imports` EMPTY — do not pre-populate it (block V1).** Verified against import-linter 2.11: the `forbidden` contract defaults `unmatched_ignore_imports_alerting = ERROR` (`importlinter/contracts/forbidden.py`). An `ignore_imports` entry naming a module that does not yet exist (`codegenie.rag.store -> chromadb`) makes `lint-imports` **error** with "Could not find import" — `make lint-imports` would not exit 0 on day one. The earlier story draft's "forward-clean whitelist" premise was mechanically wrong. The correct path: contracts ship with `ignore_imports` omitted; S3-02 (anthropic edge), S4-01 (fastembed/onnxruntime edges), S4-03 (chromadb edge) each append one explicit edge line when they land the real import. That is true extension-by-addition and keeps the audit trail honest — each admitted edge is one reviewed line in `pyproject.toml`, never a glob.
- **The shape-drift test is the mutation guard — mirror the established precedent.** `tests/fence/test_phase3_importlinter_contracts_shape.py` and `…_phase7_…` are the convention (Rule 11): a static `tomllib` read of `pyproject.toml`, parametrized assertions on `type` / `as_packages` / `source_modules` / `forbidden_modules`. Phase 3 and Phase 7 shipped *only* such a test — no live-fire `lint-imports` run, no `_fixtures` directory. Copy that file's structure; do not invent a new mechanism.
- **Couple the contracts to the fence constants (D2).** The shape test must `import` `GATHER_PIPELINE_PATHS` / `PHASE4_ADMITTED_PACKAGES` / `PHASE4_STILL_FORBIDDEN` (the same constants the pytest fence uses) and derive its expectations from them — never re-type the package lists as string literals. That import IS the belt-and-suspenders coupling: widen the pytest fence and the lint contract's expectation moves in lockstep. `GATHER_PIPELINE_PATHS` is path strings; `source_modules` is dotted module names — translate (`removeprefix("src/")`, `rstrip("/")`, `replace("/", ".")`).
- **⚠ Cross-story hazard — the S1-05 narrowing breaks the Phase-3/Phase-7 shape tests (block C4, Rule 7).** S1-05 narrows `FORBIDDEN_LLM_SDKS` to drop `anthropic` and add `sentence-transformers`/`torch`. `test_phase3_importlinter_contracts_shape.py::test_contract_forbids_exactly_the_llm_sdk_closure` (and the Phase-7 twin) assert `set(forbidden_modules) == FORBIDDEN_LLM_SDKS`; after the narrowing those fail two ways — the Phase-3/Phase-7 contracts still list `anthropic`, and the new distribution-named `sentence-transformers` (hyphen) can never set-equal an import-name `forbidden_modules` entry (`sentence_transformers`, underscore). `make check` (AC-8) cannot be green until this is reconciled. S1-06 owns import-linter contracts, so handle it here: update the Phase-3/Phase-7 contracts' `forbidden_modules` and adjust those shape tests' comparison to canonicalize separators (or compare against the import-name projection of the deny-set). If S1-05's executor already reconciled it (a competent executor running `make check` would be forced to), confirm and move on. Either way, record the resolution in the attempt log and flag whether ADR-0003 / the Phase-3 contract comment need an amendment.
- **No `make lint-imports` Makefile changes.** The target already runs `lint-imports --config pyproject.toml --no-cache`; new contracts are discovered automatically.
- **The optional live-fire test (AC-7) — if you build it, build it right.** `python -m importlinter` does not work (no `__main__.py`) and there is no `lint` subcommand — both verified. Resolve the `lint-imports` console script via `shutil.which("lint-imports")`. Merge `os.environ` into any `env=` you pass to `subprocess.run` (a bare `env={"PYTHONPATH": …}` drops `PATH`/`HOME`). Beware the editable-installed real `codegenie` colliding with a synthetic tmp `codegenie` on `sys.path`. Because the shape test is the always-on guard, this test is genuinely optional — if it fights CI, drop it and note the choice.
- **No edits to the cold-start / ADR-0013 contracts.** The two Phase-0 cold-start contracts and the `codegenie.types.identifiers ↛ codegenie.probes` contract stay verbatim. This story is additive for new contracts; the only existing-contract edits permitted are the AC-8 Phase-3/Phase-7 reconciliation.
- **CI fail-loud expectation (Rule 12).** When a future PR adds `import anthropic` outside the leaf adapter, the developer sees one failure from the pytest fence (S1-05) and one from `make lint-imports` (S1-06) — belt-and-suspenders means the diagnostic shows up in both, giving the next reader two independent signals naming ADR-0003.
