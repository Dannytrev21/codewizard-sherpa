# Story S1-06 — import-linter contracts mirroring the fence

**Step:** Step 1 — Establish Phase-4 type substrate + path-scoped fence amendment
**Status:** Ready
**Effort:** S
**Depends on:** S1-05
**ADRs honored:** ADR-0003 (path-scoped fence — `import-linter` is the *lint-time* belt-and-suspenders alongside the *test-time* pytest fence)

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
  - `pyproject.toml § [tool.importlinter]` — existing root config and two `forbidden` contracts (Phase-0 cold-start defense for `codegenie.cli` and `codegenie`'s `__init__`). Mirror the schema; do not change existing contracts.
  - `Makefile` `lint-imports` target — confirms `make lint-imports` runs `lint-imports --config pyproject.toml` (or equivalent).

## Goal

Add four `forbidden` import-linter contracts to `pyproject.toml § [tool.importlinter.contracts]` so `make lint-imports` enforces the same path-scoped admissions as the pytest fence in S1-05 — at lint time, before tests run.

## Acceptance criteria

### Contracts landed

- [ ] AC-1 — `pyproject.toml § [tool.importlinter.contracts]` ships four new `forbidden` contracts:
  1. **`gather pipeline must not import phase-4 admitted or forbidden packages`** — `source_modules = ["codegenie.probes", "codegenie.coordinator", "codegenie.cache", "codegenie.output", "codegenie.schema"]`; `forbidden_modules = ["anthropic", "chromadb", "fastembed", "onnxruntime", "langgraph", "openai", "langchain", "transformers", "sentence_transformers", "torch"]`.
  2. **`anthropic may be imported only by the leaf adapter`** — `source_modules = ["codegenie"]` (with `as_packages = true`); `forbidden_modules = ["anthropic"]`; `ignore_imports = ["codegenie.fallback.leaf.anthropic_adapter -> anthropic"]`.
  3. **`chromadb may be imported only under codegenie.rag`** — `source_modules = ["codegenie"]`; `forbidden_modules = ["chromadb"]`; `ignore_imports` lists every `codegenie.rag.* -> chromadb` edge by **explicit module name** (not glob), with a `# TODO(phase-4-step-1)` comment noting the list grows as S4-03 lands `store.py` and the rest of `rag/` arrives.
  4. **`fastembed and onnxruntime may be imported only under codegenie.rag`** — same shape as (3), with `forbidden_modules = ["fastembed", "onnxruntime"]`.
- [ ] AC-2 — Each contract carries a `name` field that names ADR-0003 in human-readable form (mirror the existing Phase-0 contract style: `name = "ADR-0003: gather pipeline must not import phase-4 admitted or forbidden packages"`).
- [ ] AC-3 — `include_external_packages = true` (already set at `[tool.importlinter]` root) — verified to remain present; required for `forbidden_modules` to name third-party packages.

### Verification — green path

- [ ] AC-4 — `make lint-imports` exits 0 against the current source tree (no `codegenie.fallback.leaf.anthropic_adapter.py` exists yet because S3-02 ships it; `ignore_imports` whitelists the future edge so the contract is forward-clean).
- [ ] AC-5 — `pyproject.toml` `[tool.importlinter]` config validates: `lint-imports --debug` (or equivalent) parses the new contracts without warning.

### Verification — deliberate-violation negative test (mutation guard)

- [ ] AC-6 — `tests/fence/test_import_linter_contracts.py` ships a parametrized test that:
  1. For each of the four new contracts (named by their `name` string), **synthetically writes a violator Python file** under a `tmp_path` (e.g., `tmp/codegenie/probes/violator.py` containing `import anthropic`).
  2. Invokes `lint-imports --config <synthetic-pyproject> --no-cache` against the synthetic tree (a small `pyproject.toml` is materialized with the contract under test and `root_packages` pointed at the tmp tree).
  3. Asserts a non-zero exit code AND the contract's `name` substring appears in stdout.
  - **Critical:** the parametrized fixture reads the contract definitions from the real `pyproject.toml` so a contract narrowing/widening in `pyproject.toml` immediately changes the negative test's expectation (mutation guard — pasting the contract names as string constants in two places defeats this).
- [ ] AC-7 — Alternative simpler shape acceptable if AC-6's tmp-pyproject indirection is too brittle: **commit four deliberately-violating fixture files under `tests/fence/_fixtures_phase4_importlinter/` with `.py.txt` extension** (same convention as S1-05) and document in the runbook (S3-06) the manual verification step: "Rename the fixture to `.py`, place under a synthesized `src/codegenie/probes/`, run `make lint-imports`, observe the four named contracts fire." This shifts AC-6 from automated to manual + runbook; **AC-6's automated shape is the preferred form**; the alternative is the fallback documented in the attempt log if the tmp-pyproject indirection fails on CI for reasons specific to import-linter's loader.

### Hygiene

- [ ] AC-8 — `ruff check`, `ruff format --check`, `mypy --strict` clean on touched files. `make check` green.
- [ ] AC-9 — The TDD plan's red test exists, is committed, and is green.

## Implementation outline

1. Read existing `pyproject.toml § [tool.importlinter]` to confirm root config (`root_packages`, `include_external_packages`).
2. Append the four new `[[tool.importlinter.contracts]]` blocks per AC-1. The `ignore_imports` lists name the *target* edges (the permitted source → forbidden-module edges) using import-linter's `<source-module> -> <target-module>` syntax.
3. Run `make lint-imports` locally to verify clean.
4. Land `tests/fence/test_import_linter_contracts.py`: parametrized negative test routing four fixtures through `lint-imports` against a synthesized tmp pyproject.
5. If AC-6's automated negative-test shape proves brittle on CI (import-linter's loader semantics), fall back to AC-7's manual-runbook documentation and surface the deferral in the attempt log.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/fence/test_import_linter_contracts.py`

```python
"""ADR-0003 belt-and-suspenders — every Phase-4 path-scope contract has a
deliberate-violation negative test routed through `lint-imports` against a
synthesized tmp project. Mutation guard: changing the contract's `name` field
in pyproject.toml without updating the expected substring kills this test.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _phase4_contracts() -> list[dict]:
    data = tomllib.loads(PYPROJECT.read_text())
    contracts = data.get("tool", {}).get("importlinter", {}).get("contracts", [])
    # The four Phase-4 contracts name ADR-0003.
    return [c for c in contracts if "ADR-0003" in c.get("name", "")]


CASES = [
    # (contract-name-substring, violator_rel_path, violator_import_line)
    (
        "gather pipeline must not import phase-4",
        "src/codegenie/probes/violator.py",
        "import anthropic\n",
    ),
    (
        "anthropic may be imported only by the leaf adapter",
        "src/codegenie/fallback/violator.py",
        "import anthropic\n",
    ),
    (
        "chromadb may be imported only under codegenie.rag",
        "src/codegenie/fallback/violator.py",
        "import chromadb\n",
    ),
    (
        "fastembed and onnxruntime may be imported only under codegenie.rag",
        "src/codegenie/fallback/violator.py",
        "import onnxruntime\n",
    ),
]


@pytest.mark.parametrize("name_substr,rel_path,line", CASES)
def test_each_contract_fires_on_planted_violation(
    tmp_path: Path, name_substr: str, rel_path: str, line: str
) -> None:
    # Confirm the contract is present in the real pyproject (mutation guard).
    contracts = _phase4_contracts()
    assert any(name_substr in c["name"] for c in contracts), (
        f"Contract naming substring {name_substr!r} missing from pyproject; "
        f"defined contracts: {[c['name'] for c in contracts]}"
    )

    # Materialize a synthetic project rooted at tmp_path that contains the
    # violator and a minimal pyproject.toml carrying ONLY the contract under
    # test (so lint-imports' diagnostic is unambiguous).
    target = tmp_path / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(line)
    # Walk up to ensure each package along the path has an __init__.py.
    cur = target.parent
    while cur != tmp_path:
        (cur / "__init__.py").touch()
        cur = cur.parent

    # Synthesize pyproject with the contract under test only.
    target_contract = next(c for c in contracts if name_substr in c["name"])
    cfg = _render_importlinter_pyproject(target_contract)
    (tmp_path / "pyproject.toml").write_text(cfg)

    result = subprocess.run(
        [sys.executable, "-m", "importlinter", "lint",
         "--config", str(tmp_path / "pyproject.toml"), "--no-cache"],
        capture_output=True, text=True, cwd=tmp_path,
        env={"PYTHONPATH": str(tmp_path / "src")},
    )
    assert result.returncode != 0, (
        f"import-linter did not fail on planted violation for {name_substr!r}: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert name_substr in result.stdout, (
        f"import-linter failed but did not name {name_substr!r}; output:\n{result.stdout}"
    )


def _render_importlinter_pyproject(contract: dict) -> str:
    import tomli_w  # if not available, use string-build fallback
    body = {
        "tool": {
            "importlinter": {
                "root_packages": ["codegenie"],
                "include_external_packages": True,
                "contracts": [contract],
            }
        }
    }
    return tomli_w.dumps(body)
```

State why it fails: the four new contracts don't exist in `pyproject.toml` yet, so `_phase4_contracts()` returns an empty list and every parametrized case fails the membership assertion.

### Green — make it pass

1. Append the four new `[[tool.importlinter.contracts]]` blocks to `pyproject.toml`. Each carries `name`, `type = "forbidden"`, `source_modules`, `forbidden_modules`, and (for contracts 2–4) `ignore_imports`.
2. Update the comment block above the existing contracts (if any) to cite ADR-0003.
3. Run `make lint-imports` locally; verify exit 0.
4. Run the new negative test; verify all four cases fire.

The four `pyproject.toml` blocks (illustrative — final exact form lives in `pyproject.toml`):

```toml
[[tool.importlinter.contracts]]
name = "ADR-0003: gather pipeline must not import phase-4 admitted or forbidden packages"
type = "forbidden"
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
source_modules = ["codegenie"]
forbidden_modules = ["anthropic"]
# Only the leaf adapter is permitted. S3-02 lands the import; until then, this
# whitelist is forward-clean (no offender exists).
ignore_imports = [
  "codegenie.fallback.leaf.anthropic_adapter -> anthropic",
]

[[tool.importlinter.contracts]]
name = "ADR-0003: chromadb may be imported only under codegenie.rag"
type = "forbidden"
source_modules = ["codegenie"]
forbidden_modules = ["chromadb"]
# S4-03 lands store.py with `import chromadb`. The list grows as rag/ modules
# add explicit edges (preferred over glob — keeps the audit trail honest).
ignore_imports = [
  "codegenie.rag.store -> chromadb",
]

[[tool.importlinter.contracts]]
name = "ADR-0003: fastembed and onnxruntime may be imported only under codegenie.rag"
type = "forbidden"
source_modules = ["codegenie"]
forbidden_modules = ["fastembed", "onnxruntime"]
ignore_imports = [
  "codegenie.rag.embedder -> fastembed",
  "codegenie.rag.embedder -> onnxruntime",
]
```

### Refactor — clean up

- Confirm `include_external_packages = true` remains at the `[tool.importlinter]` root (required so `forbidden_modules` may name third-party packages — pyproject already has this; do not remove).
- Group the four new contracts under a `# Phase 4 (ADR-0003) path-scoped admissions` section header comment so the next reader sees the cluster.
- Edge cases enumerated in arch §Edge cases that touch this code: #15 (extras vs. dependencies — import-linter scans the actual import graph; extras are irrelevant here).

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` | Append four `[[tool.importlinter.contracts]]` blocks; group under ADR-0003 comment header. |
| `tests/fence/test_import_linter_contracts.py` | NEW — parametrized negative tests routing planted violators through `lint-imports` against synthesized tmp pyprojects. |

## Out of scope

- **The pytest path-scoped fence test** — S1-05 (this story is the lint-time complement).
- **`tests/fence/test_kernel_frozen.py`** — S1-07.
- **`BudgetToken` import-linter contract restricting to `{tier.py, leaf/anthropic_adapter.py}`** — S2-05 (different contract, different forbidden symbol).
- **`_phase4_local_capability_mint` import-linter contract restricting to `{src/codegenie/gates/, src/codegenie/rag/ingest.py}`** — S4-06.
- **Adding `langgraph` to the lint-time forbidden set explicitly** — already covered by the gather-pipeline contract (which lists all PHASE4_STILL_FORBIDDEN packages); a dedicated contract is overkill until Phase 6 amends.

## Notes for the implementer

- **`ignore_imports` uses explicit module-name edges, not globs.** Naming `codegenie.rag.store -> chromadb` (not `codegenie.rag.* -> chromadb`) keeps the audit trail honest — every new admitted edge is one explicit line in `pyproject.toml`. ADR-0003's "the path allowlist is config in a test file, not in a more central manifest" tradeoff names this trade-off.
- **The whitelist is forward-clean.** When this story lands, `codegenie.fallback.leaf.anthropic_adapter` doesn't exist yet (S3-02 ships it); `codegenie.rag.store` doesn't exist yet (S4-03 ships it); `codegenie.rag.embedder` doesn't exist (S4-01). The `ignore_imports` entries are forward-clean — they whitelist edges that will become real later. import-linter accepts whitelisted-but-not-yet-existent edges without warning (verify against the installed version; surface per Rule 7 if not).
- **The negative test is the mutation guard for the contracts.** Mirror S1-05's pattern: a contributor who tightens or loosens a contract's `forbidden_modules` in `pyproject.toml` should see a paired negative test fail. The parametrized fixture reads the contract names from `pyproject.toml` directly so a rename in pyproject changes the expected substring automatically.
- **The synthetic-pyproject negative test may need a fallback.** import-linter's loader can be opinionated about `root_packages` discovery; if the parametrized AC-6 shape proves brittle on CI (e.g., the synthetic tree must include a `pyproject.toml`-relative `src/` package), document the workaround in the attempt log and consider falling back to AC-7's manual-runbook shape. **Prefer the automated shape**: a manual runbook step erodes over time.
- **No `make lint-imports` Makefile changes.** The target already runs `lint-imports --config pyproject.toml`; the new contracts are discovered automatically.
- **Mutation kill — name substrings, not exact names.** The negative test asserts `name_substr in result.stdout` rather than full-name equality so import-linter's diagnostic format (which may add prefixes/suffixes) does not break the assertion. The substring is uniquely picked from the contract name so any rename surfaces the conflict.
- **No edits to existing contracts.** The two Phase-0 cold-start contracts (`codegenie.cli must not top-level import heavy modules`, `codegenie (__init__) must not top-level import heavy modules`) stay verbatim; this story is additive only.
- **CI fail-loud expectation (Rule 12).** When a future PR adds `import anthropic` outside the leaf adapter, the developer sees one error from the pytest fence (S1-05) and one from import-linter (S1-06) — belt-and-suspenders means the diagnostic shows up in both `make test` and `make lint-imports`, which gives the next reader two independent signals naming ADR-0003.
