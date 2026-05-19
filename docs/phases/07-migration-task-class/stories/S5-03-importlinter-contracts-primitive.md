# Story S5-03 — Import-linter contracts: primitive forbids LLM + cannot import `plugins/`

**Step:** Step 5 — Phase 7 byte-edit allowlist fence + import-linter contracts + `PLUGINS.lock`
**Status:** Ready
**Effort:** S
**Depends on:** S5-01 (byte-edit allowlist fence is in place — pyproject.toml is row 9 of the allowlist, so this edit is allowlisted by ADR-0009).
**ADRs honored:** Phase 7 ADR-0009 (pyproject.toml is row 9 — runtime dep + import-linter contracts are both additive bands within that allowlisted file); Phase 7 ADR-0004 (`vuln_provenance` primitive home — primitives are pure, deterministic, LLM-free); Phase 7 ADR-0005 (probes live under plugin tree); Phase 7 ADR-0001 (no `MultiPluginCoordinator` — by enforcing port-before-adapter direction in the import graph, the primitive cannot smuggle plugin-specific behavior); Phase 3 ADR-0011 (honest framing — import-linter is lint, not runtime fence); Phase 0 import-linter precedent (`codegenie.cli must not top-level import heavy modules`).

## Context

Phase 7 introduces two new top-level Python trees:
1. `src/codegenie/primitives/vuln_provenance/` — the new primitive (typed surface; pure logic; no I/O).
2. `plugins/distroless-migration--node--npm/` — the new task-class plugin.

The deterministic-only commitment ("no LLM anywhere in `codegenie/`") and the hexagonal-architecture commitment ("primitive is the port; plugins are the adapters; adapters import from primitive, never the reverse") both need CI hard-blocks before they land. Without import-linter contracts:
- A future PR could quietly `import anthropic` under `src/codegenie/primitives/vuln_provenance/` and Phase 7's "primitive is LLM-free" claim becomes aspirational.
- A future PR could import `plugins.distroless_migration_node_npm.adapters.alpine_provenance` from within the primitive, inverting the dependency direction and turning the primitive into a plugin-aware kernel — exactly the Ship-of-Theseus pattern Phase 7 ADR-0009 fights elsewhere.

Phase 0 (S1-05) established the import-linter contract style: `[[tool.importlinter.contracts]]` blocks under `pyproject.toml`, with `type = "forbidden"`, `source_modules`, `forbidden_modules`, and `as_packages = true` to scope to whole package trees. Phase 3 S1-05 extended this for `codegenie.plugins` and `codegenie.transforms`. This story extends it twice more:
1. **LLM-SDK forbiddance:** `src/codegenie/primitives/vuln_provenance/` and `plugins/distroless-migration--*/` may not import `{anthropic, langgraph, openai, langchain, transformers}` (the `FORBIDDEN_LLM_SDKS` set).
2. **Port-before-adapter direction:** `src/codegenie/primitives/vuln_provenance/` may not import from `plugins/` (any plugin slug, current or future).

The contracts are mechanical; the failure mode is loud (`make lint-imports` exits non-zero, names the offending import).

**Honest framing (Phase 3 ADR-0011 carry-forward):** import-linter walks the static import graph; runtime dynamic imports via `importlib.import_module(...)` or `getattr(sys.modules, ...)` are not caught. The complementary runtime-closure scan lives in `tests/fence/test_phase7_no_llm.py` (S1-06's territory).

## References — where to look

- **Phase ADRs:**
  - `../ADRs/0004-vuln-provenance-primitive-home.md` — primitive lives at `src/codegenie/primitives/vuln_provenance/`; pure, deterministic.
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — plugin tree at `plugins/distroless-migration--node--npm/`.
  - `../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md` — port-before-adapter direction is the architectural commitment this story enforces mechanically.
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` row 9 — `pyproject.toml` is allowlisted for `dockerfile-parse` (one runtime dep). This story's import-linter additions are *additional bands* under the already-existing `[tool.importlinter]` section and DO NOT require a new row in the allowlist (additive contract blocks within an allowlisted file).
- **Phase 1/3 ADRs:**
  - `Phase 0 ADR (S1-05)` — established `pyproject.toml [tool.importlinter]` as the canonical contracts home (NOT `tools/lint/importlinter.cfg`; honor existing convention per Rule 11).
  - `Phase 3 ADR (S1-05)` — extends contracts for `codegenie.plugins` + `codegenie.transforms`; same shape, same forbidden-modules set.
- **Architecture:**
  - `../phase-arch-design.md §Testing strategy §"CI gates"` — names `make lint-imports` as the load-bearing gate.
  - `../phase-arch-design.md §Component design §C4` — primitive surface diagram (the import graph this story closes).
- **Existing code:**
  - `pyproject.toml §[tool.importlinter]` lines 318–380 — read every existing contract; the new contracts mirror the shape EXACTLY (`type = "forbidden"`, `as_packages = true`, `include_external_packages = true` at the section level).
  - `tests/fence/test_phase3_importlinter_contracts_shape.py` — parses `pyproject.toml` and asserts each contract names exactly the five `FORBIDDEN_LLM_SDKS` and `as_packages = True`. This story extends it (one parametrized row per new contract) to cover the new contracts.
  - `tests/fence/test_lint_imports_catches_planted_leak.py` — the planted-import subprocess test that proves the contracts are actually load-bearing. This story extends it with planted imports under the new source modules.
  - `src/codegenie/_fence.py` — `FORBIDDEN_LLM_SDKS` constant. Single source of truth for the SDK names.
  - `Makefile §lint-imports` — `lint-imports: $(VENV)/bin/lint-imports`. No edits needed.

## Goal

Extend `pyproject.toml [tool.importlinter]` with the new contracts so:
1. `src/codegenie/primitives/vuln_provenance/` (as a package) may not import any of `FORBIDDEN_LLM_SDKS`.
2. `plugins/distroless-migration--node--npm/` (as a package) may not import any of `FORBIDDEN_LLM_SDKS` — note: this requires the plugin to be import-linter-discoverable, which requires the plugin to be a proper Python package under a path import-linter walks. Coordinate with the existing plugin-discovery convention (Phase 3 S2-03 plugin-loader pattern).
3. `src/codegenie/primitives/vuln_provenance/` may not import from any `plugins.*` module (port-before-adapter direction).

`make lint-imports` exits 0 with the new contracts and a planted-import test proves each contract is load-bearing.

## Acceptance criteria

**Contract additions (AC-1 through AC-3)**
- [ ] **AC-1** `pyproject.toml [tool.importlinter]` gains a new `[[tool.importlinter.contracts]]` block:
  ```toml
  [[tool.importlinter.contracts]]
  name = "codegenie.primitives.vuln_provenance must not import LLM SDKs"
  type = "forbidden"
  source_modules = ["codegenie.primitives.vuln_provenance"]
  as_packages = true
  forbidden_modules = ["anthropic", "langgraph", "openai", "langchain", "transformers"]
  ```
- [ ] **AC-2** `pyproject.toml [tool.importlinter]` gains a new contract for the plugin tree. The plugin's Python package name (e.g., `plugins.distroless_migration_node_npm` if the plugin uses Python's dotted-name convention, or whatever the existing plugin-loader walks) is named explicitly:
  ```toml
  [[tool.importlinter.contracts]]
  name = "plugins.distroless-migration--node--npm must not import LLM SDKs"
  type = "forbidden"
  source_modules = ["plugins.distroless_migration_node_npm"]  # exact module path per plugin-loader convention; verify
  as_packages = true
  forbidden_modules = ["anthropic", "langgraph", "openai", "langchain", "transformers"]
  ```
  **Coordinate with existing plugin-import convention** (read `src/codegenie/plugins/loader.py` for the dotted-name convention; if the existing convention uses underscores instead of hyphens at the Python module level — likely, since hyphens are not valid Python identifiers — the contract names the underscored form).
- [ ] **AC-3** `pyproject.toml [tool.importlinter]` gains a new contract enforcing port-before-adapter direction:
  ```toml
  [[tool.importlinter.contracts]]
  name = "codegenie.primitives.vuln_provenance must not import from plugins/"
  type = "forbidden"
  source_modules = ["codegenie.primitives.vuln_provenance"]
  as_packages = true
  forbidden_modules = ["plugins"]  # or "plugins.*" per import-linter's matcher syntax
  ```
  **Verify the import-linter matcher syntax** — `forbidden_modules` accepts module names; whether `"plugins"` matches all submodules depends on `as_packages` semantics. If `as_packages = true` on `forbidden_modules` is not the right knob, use a per-plugin row OR an `import-linter` `independence` contract instead. Pin the exact form at implementation time after reading import-linter's docs.

**Contract-shape verification (AC-4)**
- [ ] **AC-4** `tests/fence/test_phase3_importlinter_contracts_shape.py` is extended (parametrized) to cover the three new contracts:
  - Each contract names exactly the five `FORBIDDEN_LLM_SDKS` (AC-1 / AC-2) — drift fails.
  - Each contract has `as_packages = True` — drift fails.
  - The port-before-adapter contract (AC-3) names exactly `plugins` (or the agreed matcher form) — drift fails.
  - Source modules are `["codegenie.primitives.vuln_provenance"]` / `["plugins.distroless_migration_node_npm"]` respectively — drift fails.
  - Add a `_EXPECTED_PHASE7_CONTRACTS: Final[tuple[ExpectedContract, ...]]` constant with three rows; parametrize the existing test infrastructure.

**Planted-leak verification (AC-5) — Rule 12 fail-loud**
- [ ] **AC-5** `tests/fence/test_lint_imports_catches_planted_leak.py` is extended (parametrized) so each new contract has at least one planted-import case that proves the contract is load-bearing:
  - **AC-5.a** Plant `src/codegenie/primitives/vuln_provenance/_test_planted_anthropic_leak.py` containing `import anthropic`. Run `make lint-imports` as a subprocess. Assert non-zero exit AND the failure message names `anthropic` AND `codegenie.primitives.vuln_provenance`. Remove the file.
  - **AC-5.b** Plant `plugins/distroless-migration--node--npm/_test_planted_openai_leak.py` containing `import openai`. Same shape; assert the failure names `openai` AND the plugin slug. Remove.
  - **AC-5.c** Plant `src/codegenie/primitives/vuln_provenance/_test_planted_plugin_leak.py` containing `from plugins.vulnerability_remediation_node_npm import adapters`. Run `make lint-imports`. Assert non-zero exit AND the failure names the `plugins` source AND the primitive source path. Remove.
  - Each planted-leak case is parametrized; the planted file is created in a `pytest.fixture` (yield + cleanup) so a test failure does not leave the file on disk.
  - **AC-5.d** Out-of-test evidence: 3-line evidence block per contract (red SHA / removal SHA / green SHA) recorded in `_attempts/S5-03.md`. Three independent blocks = three independent load-bearing demonstrations.

**Cross-fence integration (AC-6)**
- [ ] **AC-6** `make lint-imports` exits 0 at story landing (all three new contracts pass).
- [ ] **AC-6.a** `pytest tests/fence/test_phase7_no_byte_edits_to_locked_files.py` exits 0 — `pyproject.toml` is row 9 of the byte-edit allowlist, so adding the contract blocks is allowed.
- [ ] **AC-6.b** `make check` exits 0; no other fence regresses.

**Wiring (AC-7 through AC-8)**
- [ ] **AC-7** `ruff check`, `ruff format --check`, `mypy --strict` on touched files clean.
- [ ] **AC-8** TDD plan's red test exists in git history (commit SHA recorded in `_attempts/S5-03.md`), green at story landing.

## Implementation outline

1. **Read the existing contracts** in `pyproject.toml` lines 318–380. Mirror the shape exactly: `name`, `type = "forbidden"`, `source_modules`, `as_packages = true`, `forbidden_modules` matching `FORBIDDEN_LLM_SDKS` byte-for-byte.
2. **Verify the plugin's Python module path.** Read `src/codegenie/plugins/loader.py` to find the convention. Likely shape: `plugins.<slug-with-underscores>.api` (Python-identifier-clean form). If the loader uses `importlib.util.spec_from_file_location` to bypass the dotted-name convention, the import-linter contract may need `source_modules` named differently — coordinate with the loader's discovery.
3. **Add the three new contract blocks** to `pyproject.toml`. Run `make lint-imports` — should exit 0.
4. **Extend `tests/fence/test_phase3_importlinter_contracts_shape.py`** with the parametrized `_EXPECTED_PHASE7_CONTRACTS` rows. Run the test — should exit 0 (the test parses `pyproject.toml` and finds the contracts).
5. **Extend `tests/fence/test_lint_imports_catches_planted_leak.py`** with three new parametrized planted-leak cases (AC-5.a–c). The fixture creates the planted file in `tmp_path`-equivalent (actually inside `src/`, since import-linter walks the source tree — using `tmp_path` does not exercise the actual contract; the planted file must be inside `src/codegenie/primitives/vuln_provenance/` to be in import-linter's source-graph). Use a `pytest.fixture` with `yield` + cleanup-on-exit; the `try/finally` ensures the file is removed even on test failure.
6. **Plant the out-of-test violations** (AC-5.d): on a throwaway branch, create a real planted file, run `make lint-imports`, record red SHA + output; remove; record green SHA. Three independent blocks in `_attempts/S5-03.md`.
7. **Run `make check`** — green.

## TDD plan (red → green → refactor)

**Red:**
1. Before adding any contracts, plant `src/codegenie/primitives/vuln_provenance/_test_planted_anthropic_leak.py` containing `import anthropic`. Run `make lint-imports` — exits 0 (no contract guards this path yet).
2. This proves the gap exists: without the contract, the leak is silent.

**Green:**
1. Add the AC-1 contract block to `pyproject.toml`.
2. Run `make lint-imports` — exits non-zero with the planted file named. **Red turns to red-by-coverage.**
3. Remove the planted file. Run `make lint-imports` — exits 0.
4. Repeat for AC-2 + AC-3 (plant under each new source-module surface; add contract; verify red; remove; verify green).
5. Extend `tests/fence/test_phase3_importlinter_contracts_shape.py` with the parametrized rows; run — green.
6. Extend `tests/fence/test_lint_imports_catches_planted_leak.py` with the three planted-leak parametrized cases; run — green.
7. Run `make check` — green.

**Refactor:**
1. Extract `_EXPECTED_PHASE7_CONTRACTS` to share the parametrization shape with the existing `_EXPECTED_PHASE3_CONTRACTS` (if one exists) — same data shape, different rows.
2. Confirm `ruff` / `mypy --strict` clean.
3. Sort contracts in `pyproject.toml` by `source_modules` for deterministic reading.

## Files to touch

- `pyproject.toml` — three new `[[tool.importlinter.contracts]]` blocks (additive bands within row 9 of the byte-edit allowlist).
- `tests/fence/test_phase3_importlinter_contracts_shape.py` — extended with three new parametrized rows.
- `tests/fence/test_lint_imports_catches_planted_leak.py` — extended with three new planted-leak parametrized cases.
- `_attempts/S5-03.md` — append-only attempt log with three 3-line out-of-test planted-leak evidence blocks.

## Out of scope

- **Runtime-closure scan for LLM SDKs under the new tree** — that's S1-06's `tests/fence/test_phase7_no_llm.py` (the dynamic-import companion fence; import-linter is the static-graph companion).
- **`tools/lint/importlinter.cfg`** — does not exist; honor existing `pyproject.toml [tool.importlinter]` convention per Rule 11.
- **Generalizing contracts to ALL future plugins** — Phase 8+ adds its own contract row per new plugin. The shape is data-driven; one contract per plugin tree.
- **Cryptographic enforcement** — import-linter is lint, not runtime fence. Phase 3 ADR-0011 framing.

## Notes for the implementer

- **Verify the plugin's Python-importable module path BEFORE writing the contract.** The plugin's directory is `plugins/distroless-migration--node--npm/`, but hyphens are not valid in Python module identifiers. The existing plugin-loader convention (Phase 3 S2-03) almost certainly converts to underscores: `plugins.distroless_migration_node_npm`. **Confirm by reading `src/codegenie/plugins/loader.py` first** — if the loader uses `importlib.util.spec_from_file_location` to bypass the dotted-name limitation, the import-linter `source_modules` field needs a different form (or the contract simply doesn't apply at the loader level; you'd put the contract on the *file path* via a different tool). Coordinate with how Phase 3's `plugins/vulnerability-remediation--node--npm/` is handled — if it is NOT covered by an import-linter contract today, that's a gap, and adding the Phase 7 plugin to a similar gap is acceptable; the planted-leak test still proves the contract is load-bearing at the dotted-name level.
- **`forbidden_modules = ["plugins"]` semantics for AC-3.** Import-linter's `forbidden_modules` matches at the module level. Whether a single `"plugins"` entry matches all `plugins.*` submodules depends on the matcher; this story documents the open question. The simpler resolution: name each known plugin explicitly: `forbidden_modules = ["plugins.vulnerability_remediation_node_npm", "plugins.distroless_migration_node_npm"]`. Phase 8 adds its own plugin's row. This is data-driven; one row per plugin Phase 7 knows about. **Pin the form at implementation time after a 5-minute read of import-linter's docs; surface the decision in `_attempts/S5-03.md`.**
- **Anti-pattern explicitly avoided:** do NOT create a custom import-graph walker. Import-linter is the canonical tool; reusing it preserves the Phase 0 / Phase 3 convention (Rule 11).
- **Surface conflicts (Rule 7):** if you find that adding the AC-3 contract makes the existing primitive code red (i.e., some unintended `from plugins.x import y` already exists in `src/codegenie/primitives/vuln_provenance/`), STOP. The fix is to either remove the dependency (the primitive should not import from plugins) or amend the ADR (very unlikely; the architectural commitment is firm). Do not weaken the contract to make the red go away.
- **Performance:** import-linter is fast (< 5 s on a clean repo). No perf budget concerns; `make lint-imports` stays at its current cost band.
- **CI integration:** `make lint-imports` is already a `make check` dependency (per `Makefile`); no CI config edit needed.
