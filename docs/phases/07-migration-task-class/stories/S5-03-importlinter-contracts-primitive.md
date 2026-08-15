# Story S5-03 — LLM-SDK fence for `plugins/**` (AST walk) + port-before-adapter contract (import-linter)

**Step:** Step 5 — Phase 7 byte-edit allowlist fence + import-linter contracts + `PLUGINS.lock`
**Status:** HARDENED (phase-story-validator, 2026-08-14 — pre-executor pass; see [`_validation/S5-03-importlinter-contracts-primitive.md`](_validation/S5-03-importlinter-contracts-primitive.md))
**Effort:** S
**Depends on:**
- **S1-06 (GREEN)** — prior art: the `codegenie.primitives.vuln_provenance` LLM-SDK import-linter contract is ALREADY shipped and shape-pinned by `tests/fence/test_phase7_importlinter_contracts_shape.py`. This story does NOT re-ship it; AC-1 is a shape-verification AC that pins the S1-06 contract as the sole source of truth for the primitive-side fence.
- **S5-01** — byte-edit allowlist fence is in place; `pyproject.toml` is row 9, so the AC-3 additive contract block is allowlisted.
- **S3-03 (BLOCKED)** — the Phase-7 distroless plugin scaffold at `plugins/distroless-migration--node--npm/`. AC-2 covers `plugins/**` via directory glob, so the fence is trivially green for the currently-existing plugin tree (`plugins/vulnerability-remediation--node--npm/`) and becomes semantically load-bearing on the Phase-7 plugin the moment S3-03 unblocks. Land AC-2 now so the fence is ready.

**ADRs honored:**
- Phase 7 ADR-0009 (byte-edit allowlist row 9: `pyproject.toml` — additive contract blocks + additive `[tool.importlinter]` bands within the allowlisted file; no new allowlist row required for the net-new test file at `tests/fence/…`, which is under the tests tree, not the locked src surface).
- Phase 7 ADR-0004 (`vuln_provenance` primitive home — the primitive-side contract that S1-06 shipped extends the deterministic-only commitment to kernel surface).
- Phase 7 ADR-0005 (probes live under plugin tree — the plugin tree the AC-2 AST fence walks is the same tree ADR-0005 designates).
- Phase 7 ADR-0001 (no `MultiPluginCoordinator` — enforcing port-before-adapter direction in the primitive's import graph makes it structurally impossible for the primitive to smuggle plugin-specific behavior).
- Phase 4 ADR-0003 (`anthropic` is path-scoped to `codegenie.fallback.leaf.anthropic_adapter`; `FORBIDDEN_LLM_SDKS` is the six-name canonical closure — the AC-2 walker canonicalizes via `packaging.utils.canonicalize_name` to match the S1-06 pattern).
- Phase 3 ADR-0011 (honest framing — import-linter and AST fences are lint, not runtime; dynamic-import bypasses are documented, CODEOWNERS on `tests/fence/` is the social anchor).
- production ADR-0043 (extension-by-addition means no silent edits — AC-2's directory-glob walker is Open/Closed: Phase 8+ plugins get fence coverage for free without a `pyproject.toml` edit or a fence-file amendment).
- Phase 0 import-linter precedent (`codegenie.cli must not top-level import heavy modules` — same TOML shape).

## Preconditions

1. **S1-06 shipped the `codegenie.primitives.vuln_provenance` LLM-SDK contract.** It lives at `pyproject.toml [tool.importlinter]` under the contract name `"phase-7 primitive does not import LLM SDKs"` with `forbidden_modules = ["openai", "langchain", "langgraph", "transformers", "sentence_transformers", "torch"]` (six names — `anthropic` intentionally absent per Phase-4 ADR-0003 path-scope; `torch` + `sentence_transformers` intentionally included per Phase-4 ADR-0003 closure widen). This story does not add a second primitive contract; AC-1 is a shape-verification AC only.

2. **The plugin loader uses `importlib.util.spec_from_file_location` with a synthetic module name** (`_codegenie_plugin_{slug_with_underscores}_api`) — see `src/codegenie/plugins/loader.py` line 301-321 and the docstring on `plugins/vulnerability-remediation--node--npm/__init__.py`. Plugin trees have hyphens in their directory names (`vulnerability-remediation--node--npm`, `distroless-migration--node--npm`) which are not valid Python identifiers. Two consequences:
   - **`plugins/*` cannot appear in import-linter's `root_packages`** — the dirs are not walkable as Python packages.
   - **The plugin's runtime module name is `_codegenie_plugin_...` — not `plugins.…`** — so import-linter's static graph would not resolve a hypothetical `source_modules = ["plugins.…"]` entry against runtime state either.
   The import-linter static graph reads what a source file *textually says* about its imports, which is the only reason `forbidden_modules = ["plugins"]` in the AC-3 contract works: it fires on the *textual* `import plugins…` statement inside a `src/codegenie/primitives/vuln_provenance/*.py` source file, regardless of whether `plugins` resolves at runtime.
   For the plugin-tree side (AC-2), the mechanism is an **AST file-walk over `plugins/**/*.py`** (mirror of `codegenie._phase3_fence.walk_any_annotations` — the same shape as `tests/fence/test_no_any_in_plugin_surface.py`), NOT an import-linter contract. See the AC-2 rationale in Notes-for-implementer for why not to migrate this to import-linter later.

3. **S3-03 is BLOCKED** (see `docs/phases/07-migration-task-class/stories/S3-03-npm-adapter-plugin-wiring.md`). The `plugins/distroless-migration--node--npm/` tree does not yet exist. This does NOT block S5-03: the AC-2 walker is directory-glob-based, so it discovers whichever plugins exist at runtime; today it covers the Phase-3 plugin tree and becomes semantically load-bearing on the Phase-7 tree the moment S3-03 lands. Land the fence now so the mechanism is proven and the Phase-7 plugin arrives to a green invariant.

## Context

Phase 7 introduces two top-level Python trees the deterministic-only commitment must reach:
1. `src/codegenie/primitives/vuln_provenance/` — the bounded-additive primitive (ADR-0004). **Already covered by S1-06's import-linter contract.**
2. `plugins/distroless-migration--node--npm/` (S3-03, BLOCKED) — the new task-class plugin tree. **Not yet covered by any fence.**

Without the coverage this story lands:
- A future PR could add `import openai` under `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py` and the deterministic-only guarantee for plugin trees dies silently. Neither the S1-06 import-linter contract (which is scoped to the primitive) nor the runtime-closure scan at `tests/fence/test_phase7_no_llm.py` (which walks the primitive only) would fire.
- A future PR could add `from plugins.vulnerability_remediation_node_npm.adapters import npm_provenance` under `src/codegenie/primitives/vuln_provenance/assembly.py`, inverting the port-before-adapter direction and turning the primitive into a plugin-aware kernel — exactly the Ship-of-Theseus pattern Phase 7 ADR-0009 fights elsewhere.

The right mechanism differs per surface:
- **Primitive-side (already shipped by S1-06):** import-linter — the primitive lives under `codegenie.primitives.vuln_provenance` (in `root_packages`), so static-graph coverage works.
- **Plugin-side (this story):** an **AST file-walk over `plugins/**/*.py`** rejecting any `import` statement whose top-level module canonicalizes into `FORBIDDEN_LLM_SDKS`. This is directory-glob-based (Open/Closed: new plugin dirs are covered automatically) and hyphenated-dir-tolerant (the walker traverses file paths, not Python module names).
- **Port-before-adapter (this story):** import-linter — the primitive IS in `root_packages` so its source files are statically walkable. `source_modules = ["codegenie.primitives.vuln_provenance"]` + `forbidden_modules = ["plugins"]` + `as_packages = true` catches any `import plugins…` / `from plugins…` textually present in a primitive source file.

**Honest framing (Phase 3 ADR-0011 carry-forward):** both mechanisms walk static text. Runtime dynamic imports via `importlib.import_module(...)` are NOT caught. The complementary runtime-closure scan for the primitive lives at `tests/fence/test_phase7_no_llm.py` (S1-06); an analogous runtime scan for plugin trees is Out-of-scope (plugins are loaded via `spec_from_file_location`, so `pkgutil.walk_packages` semantics don't apply — a Phase-8 story can add a bespoke runtime scan if needed).

## References — where to look

- **Phase ADRs:**
  - `../ADRs/0004-vuln-provenance-primitive-home.md` — primitive home; Consequences already-honored by S1-06.
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — the plugin tree AC-2 walks.
  - `../ADRs/0001-no-multi-plugin-coordinator-in-phase-7.md` — the port-before-adapter direction AC-3 enforces mechanically.
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` row 9 — `pyproject.toml` allowlist. AC-3's TOML block is an additive band within row 9. AC-2's net-new test file lives under `tests/fence/` (not part of the locked src surface).
- **Cross-phase ADRs:**
  - `../../04-vuln-llm-fallback-rag/ADRs/0003-path-scoped-fence-amendment.md` — `anthropic` path-scope + `torch` / `sentence_transformers` closure widen; the source of truth for why the S1-06 contract's `forbidden_modules` list differs from a naive "five LLM SDKs" enumeration.
  - `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` — extension-by-addition; AC-2's directory-glob walker instantiates this at the fence boundary.
  - `Phase 3 ADR-0011` (honest framing) — cited in the AST fence's docstring.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `pyproject.toml § [tool.importlinter]` lines 453–559 — read every contract; AC-3 mirrors the shape byte-for-byte (`type = "forbidden"`, `as_packages = true`, `include_external_packages = true` at the section level).
  - `pyproject.toml § [tool.importlinter]` lines 548–559 — the S1-06 primitive contract. AC-1 pins its shape; do NOT touch it.
  - `tests/fence/test_phase7_importlinter_contracts_shape.py` — the phase-7-specific shape-pin. AC-4 extends this with one new parametrized case for AC-3.
  - `tests/fence/test_lint_imports_catches_phase7_planted_leak.py` — the phase-7-specific planted-leak. AC-5.a extends this with the port-before-adapter planted-leak.
  - `tests/fence/test_no_any_in_plugin_surface.py` + `src/codegenie/_phase3_fence.py` (`walk_any_annotations`, `PHASE3_ROOTS`, `Violation`) — the canonical AST-file-walk pattern the AC-2 fence mirrors. Reuse the `Violation` shape; do not fork.
  - `src/codegenie/_fence.py` — `FORBIDDEN_LLM_SDKS` constant. Sole source of truth for the SDK names. Canonicalize via `packaging.utils.canonicalize_name` (Phase-4 ADR-0003).
  - `src/codegenie/plugins/loader.py` lines 293–321 — the `spec_from_file_location` loading convention; the reason AC-2 uses an AST walker and not import-linter.
  - `Makefile § lint-imports` — `lint-imports: $(VENV)/bin/lint-imports`. No edits needed.
  - `Makefile § fence` — the AC-2 test is picked up by the existing `make fence` target's discovery (all `tests/fence/*.py`); no wiring edit needed.

## Goal

1. **Verify (do not re-ship)** that the S1-06 `codegenie.primitives.vuln_provenance` import-linter contract is the sole source of truth for the primitive-side LLM-SDK fence — its `forbidden_modules` still equals `FORBIDDEN_LLM_SDKS` under `canonicalize_name` set-equality; there is no second primitive contract.
2. **Add an AST file-walk fence** at `tests/fence/test_no_llm_sdk_imports_in_plugin_trees.py` that walks `plugins/**/*.py`, discovers plugin directories at test-collection time, and rejects any top-level `import <X>` or `from <X> import ...` whose leading module canonicalizes into `FORBIDDEN_LLM_SDKS`. The walker is directory-glob-based: adding a new plugin directory requires zero edits to the fence file.
3. **Add one import-linter contract** to `pyproject.toml [tool.importlinter]` enforcing port-before-adapter: `codegenie.primitives.vuln_provenance` (as package) may not import from `plugins` (any submodule, any depth).

`make lint-imports` exits 0 with the new contract; `pytest tests/fence/test_no_llm_sdk_imports_in_plugin_trees.py` exits 0 today (no violations); planted-leak evidence proves each of the three surfaces is load-bearing.

## Acceptance criteria

**Primitive-side shape-verification (AC-1) — no new contract; pin S1-06 as source of truth**

- [ ] **AC-1** `tests/fence/test_phase7_importlinter_contracts_shape.py` is either (a) already asserts (existing tests: `test_phase7_contract_present`, `test_phase7_contract_forbids_exactly_the_llm_sdk_closure`, `test_phase7_contract_as_packages_true`, `test_phase7_contract_include_external_packages_true`) that the S1-06 contract's shape is byte-locked to `FORBIDDEN_LLM_SDKS`, OR (b) is extended with one new negative test `test_no_second_primitive_contract_exists`: parse `pyproject.toml`, collect every contract whose `source_modules == ["codegenie.primitives.vuln_provenance"]`, assert `len(contracts) == 1`. This makes it a fence failure to ship a duplicate primitive contract in a later PR (mutation guard against the exact anti-pattern the pre-hardening draft of this story proposed).

**Plugin-tree AST fence (AC-2) — Open/Closed via directory-glob**

- [ ] **AC-2.a — Walker + registry-of-plugins pattern.** New file `tests/fence/test_no_llm_sdk_imports_in_plugin_trees.py`. Contents:
  - A module-level `_PLUGIN_ROOT: Final[Path] = Path("plugins")` and `_PLUGIN_DIRS: Final[tuple[Path, ...]] = tuple(sorted(p for p in _PLUGIN_ROOT.glob("*/") if p.is_dir() and not p.name.startswith("__")))`.
  - The walker function `_walk_llm_sdk_imports(src: str, path: Path) -> list[Violation]` uses `ast.parse` + `ast.walk` to find `ast.Import` and `ast.ImportFrom` nodes; for each, canonicalize the top-level module name via `packaging.utils.canonicalize_name(name.split(".")[0])`; if the canonical form is in `{canonicalize_name(n) for n in FORBIDDEN_LLM_SDKS}`, emit a `Violation(path=path, lineno=node.lineno, kind="llm_sdk_import", detail=<offending name>)`. Reuse `codegenie._phase3_fence.Violation` (mirror `walk_any_annotations`'s dataclass); do NOT fork.
  - A pytest test `test_no_llm_sdk_imports_in_plugin_trees` collects every `plugins/**/*.py` (excluding `__pycache__`, files starting with `_test_planted_`), runs the walker, asserts `violations == []`, and prints all violations if non-empty (Rule 12 fail loud).
- [ ] **AC-2.b — Parametrized planted-positive for mutation-resistance.** A parametrized test `test_planted_llm_sdk_import_is_caught` writes each of `{"torch", "openai", "langchain", "langgraph", "transformers", "sentence_transformers"}` (six names — canonicalized to `FORBIDDEN_LLM_SDKS` after excluding `anthropic` per Phase-4 ADR-0003) as `import {sdk}` into a `tmp_path`-hosted file, calls `_walk_llm_sdk_imports` on the file contents, asserts exactly one `Violation` naming that SDK. `anthropic` is exercised as a NEGATIVE case: planting `import anthropic` produces zero violations (path-scope belongs to a separate fence — this walker must not false-fire on it).
- [ ] **AC-2.c — Open/Closed AC (observable).** Adding a new plugin directory under `plugins/{new-slug}/` MUST NOT require editing `tests/fence/test_no_llm_sdk_imports_in_plugin_trees.py` or `pyproject.toml`. Verified by a test `test_walker_discovers_plugin_dirs_at_collection` that asserts `_PLUGIN_DIRS` was computed via `Path("plugins").glob("*/")` (AST-parse the test module, walk for the exact `Path("plugins").glob("*/")` call). This closes the design-pattern hole the pre-hardening draft opened (per-plugin rows = primitive obsession over plugins).
- [ ] **AC-2.d — Directory-hyphen safety.** The walker traverses `plugins/vulnerability-remediation--node--npm/**/*.py` and any future `plugins/distroless-migration--node--npm/**/*.py` correctly despite hyphens in the dir name. A metamorphic test constructs a temporary hyphenated dir `tmp_path / "distroless-migration--node--npm" / "adapters" / "planted.py"` with `import torch`, runs the walker rooted at `tmp_path`, asserts the violation is found.

**Port-before-adapter import-linter contract (AC-3)**

- [ ] **AC-3** `pyproject.toml [tool.importlinter]` gains exactly one new `[[tool.importlinter.contracts]]` block:
  ```toml
  [[tool.importlinter.contracts]]
  name = "codegenie.primitives.vuln_provenance must not import from plugins/"
  type = "forbidden"
  source_modules = ["codegenie.primitives.vuln_provenance"]
  as_packages = true
  forbidden_modules = ["plugins"]
  ```
  `as_packages = true` is load-bearing on the source side (submodules of the primitive: `types`, `protocols`, `assembly`, `registry`, `sbom_verifier`, `syft_reader`, `errors`). The `forbidden_modules = ["plugins"]` entry matches any textual `import plugins` or `from plugins.X import …` statement inside a primitive source file, regardless of whether `plugins` itself is in `root_packages` (import-linter treats `forbidden_modules` as a textual pattern over the source-side static-import graph). The `include_external_packages = true` set at the `[tool.importlinter]` section level (line 458) already covers external-package traversal for other contracts and does not need repeating here.

**Contract-shape verification for AC-3 (AC-4) — extension of phase-7 shape-pin**

- [ ] **AC-4** `tests/fence/test_phase7_importlinter_contracts_shape.py` is extended with one new parametrized test group `test_phase7_port_before_adapter_contract_*`:
  - The contract named `"codegenie.primitives.vuln_provenance must not import from plugins/"` exists under `[tool.importlinter.contracts]`.
  - Its `type == "forbidden"`.
  - Its `source_modules == ["codegenie.primitives.vuln_provenance"]`.
  - Its `as_packages is True`.
  - Its `forbidden_modules == ["plugins"]`.
  Introduce a module-level constant `_EXPECTED_PORT_BEFORE_ADAPTER_CONTRACT: Final[dict[str, object]]` so drift is diff-obvious.

**Planted-leak verification (AC-5) — Rule 12 fail-loud, three independent surfaces**

- [ ] **AC-5.a** — AC-3 (import-linter port-before-adapter) planted-leak. Extends `tests/fence/test_lint_imports_catches_phase7_planted_leak.py` with `test_lint_imports_catches_planted_plugin_import_under_primitive`. Fixture creates `src/codegenie/primitives/vuln_provenance/_test_planted_plugin_import.py` containing `from plugins.vulnerability_remediation_node_npm import adapters  # noqa: F401` (the plugin slug named here is what the STATIC AST sees; the runtime loader is unrelated). Runs `lint-imports` as a subprocess. Asserts non-zero exit AND `plugins` in stdout (lower-cased) AND `vuln_provenance` in stdout. Fixture `try/finally` removes the file even on assertion failure. Mirror the exact fail-loud style of the existing `test_lint_imports_catches_planted_anthropic_under_primitive` in the same file.
- [ ] **AC-5.b** — AC-2 (plugin-tree AST fence) planted-leak. In `tests/fence/test_no_llm_sdk_imports_in_plugin_trees.py`, a fixture creates `plugins/vulnerability-remediation--node--npm/_test_planted_torch_import.py` containing `import torch  # noqa: F401` (`torch` is canonical — it is in `FORBIDDEN_LLM_SDKS` after Phase-4 ADR-0003 closure widen, and it is NOT path-scoped elsewhere; `anthropic` would false-negative because it is intentionally NOT in the plugin fence's forbidden set for the same Phase-4 ADR-0003 reason). Runs the walker; asserts one `Violation` naming `torch` + the file path. Fixture `try/finally` cleanup.
- [ ] **AC-5.c** — Out-of-test evidence (three independent 3-line blocks in `_attempts/S5-03.md`): (red SHA / removal SHA / green SHA) for (i) AC-1 shape-pin (plant a duplicate primitive contract, assert AC-1 goes red; remove; verify green), (ii) AC-3 planted plugin import in primitive, (iii) AC-2 planted `import torch` in a plugin tree. Three surfaces = three independent load-bearing demonstrations. Each block also records the exact `pytest`/`make lint-imports` command that surfaced red.

**Cross-fence integration (AC-6)**

- [ ] **AC-6** `make lint-imports` exits 0 at story landing (S1-06 primitive contract green, new AC-3 contract green).
- [ ] **AC-6.a** `pytest tests/fence/test_no_llm_sdk_imports_in_plugin_trees.py -v` exits 0 at story landing (no violations against the currently-shipped `plugins/` tree).
- [ ] **AC-6.b** `pytest tests/fence/test_phase7_no_byte_edits_to_locked_files.py` exits 0 — `pyproject.toml` is row 9 of the byte-edit allowlist so the AC-3 additive block is permitted; the AC-2 net-new file lives under `tests/fence/` (outside the locked src surface).
- [ ] **AC-6.c** `pytest tests/fence/test_phase7_importlinter_contracts_shape.py -v` exits 0 with the AC-4 additions.
- [ ] **AC-6.d** `make check` exits 0; no other fence regresses.

**Wiring (AC-7 through AC-8)**

- [ ] **AC-7** `ruff check`, `ruff format --check`, `mypy --strict` on touched files clean. `tests/fence/test_no_llm_sdk_imports_in_plugin_trees.py` uses `from __future__ import annotations`, matches the type-annotation discipline of `tests/fence/test_no_any_in_plugin_surface.py`.
- [ ] **AC-8** TDD plan's Red step exists in git history (commit SHA recorded in `_attempts/S5-03.md`), green at story landing.

## Implementation outline

1. **Read `tests/fence/test_no_any_in_plugin_surface.py` + `src/codegenie/_phase3_fence.py`** (Rule 8). Note the shape: `walk_any_annotations(src, path) -> list[Violation]`, `PHASE3_ROOTS: Final[tuple[Path, ...]]`, planted-positive parametrization, fail-loud violation printing. Mirror this shape for the LLM-SDK walker.
2. **Read the S1-06 contract at `pyproject.toml` lines 548–559 and `tests/fence/test_phase7_importlinter_contracts_shape.py`**. Confirm AC-1's shape-verification tests already exist; add only the negative "no second primitive contract" assertion.
3. **Add the AC-3 contract block** to `pyproject.toml`. Run `make lint-imports` — should exit 0 (no primitive source file imports from `plugins`).
4. **Write `tests/fence/test_no_llm_sdk_imports_in_plugin_trees.py`** with the walker, live scan, parametrized planted-positive, `anthropic`-negative, Open/Closed AST-self-check, and hyphenated-directory metamorphic test. Reuse `Violation` from `codegenie._phase3_fence`; import `FORBIDDEN_LLM_SDKS` from `codegenie._fence`.
5. **Extend `tests/fence/test_phase7_importlinter_contracts_shape.py`** with AC-4's parametrized case for the port-before-adapter contract.
6. **Extend `tests/fence/test_lint_imports_catches_phase7_planted_leak.py`** with AC-5.a's planted-plugin-import case. Mirror the existing test's fail-loud style.
7. **Land AC-2's planted-leak** as an in-file fixture inside `tests/fence/test_no_llm_sdk_imports_in_plugin_trees.py` (AC-5.b).
8. **Plant the three out-of-test evidence blocks** on a throwaway branch; record red / removal / green SHAs in `_attempts/S5-03.md`.
9. **Run `make check`** — green. Confirm no other fence regresses.

## TDD plan (red → green → refactor)

**Red — for AC-2 (plugin-tree AST fence, mechanism substitution):**
1. BEFORE writing the AC-2 walker, plant `plugins/vulnerability-remediation--node--npm/_test_planted_torch_import.py` containing `import torch`. Run `make lint-imports` — exits 0 (import-linter does not walk `plugins/`, so this is silent). Run `pytest tests/fence/test_phase7_no_llm.py` — exits 0 (runtime-closure scan is scoped to the primitive tree, so this is silent too).
2. **This proves the gap.** Neither existing fence catches an LLM-SDK import in a plugin tree.

**Red — for AC-3 (import-linter port-before-adapter):**
1. Plant `src/codegenie/primitives/vuln_provenance/_test_planted_plugin_import.py` containing `from plugins.vulnerability_remediation_node_npm import adapters`. Run `make lint-imports` — exits 0 (no contract guards this direction yet).

**Green:**
1. Add the AC-3 contract block to `pyproject.toml`. `make lint-imports` — exits non-zero on the planted primitive file (Red → Red-by-coverage). Remove the planted file — exits 0.
2. Write the AC-2 walker + tests. `pytest tests/fence/test_no_llm_sdk_imports_in_plugin_trees.py` — exits non-zero on the planted `torch` file (Red-by-coverage). Remove the planted file — exits 0.
3. Extend AC-4's shape-pin. Run — green.
4. Extend AC-5.a's planted-leak. Run — green (subprocess-planted file exercises the AC-3 contract end-to-end).
5. `make check` — green.

**Refactor:**
1. Confirm `Violation` reuse (no fork of the dataclass); confirm `FORBIDDEN_LLM_SDKS` is imported (not literalized). If any drift, unify.
2. Confirm `ruff check` / `ruff format --check` / `mypy --strict` clean.
3. Confirm AC-2.c's Open/Closed self-check test truly discovers plugin dirs at collection time (AST-parse the fence module for the exact `Path("plugins").glob("*/")` call, so a well-meaning "refactor to hardcode the plugin list" is caught).

## Files to touch

- `pyproject.toml` — one new `[[tool.importlinter.contracts]]` block (AC-3; additive band within row 9 of the byte-edit allowlist).
- `tests/fence/test_no_llm_sdk_imports_in_plugin_trees.py` — **new file** (AC-2 walker + live scan + parametrized planted-positive + `anthropic`-negative + Open/Closed AST-self-check + hyphenated-directory metamorphic + AC-5.b fixture).
- `tests/fence/test_phase7_importlinter_contracts_shape.py` — extended with AC-4 (port-before-adapter parametrized case) and AC-1 (`test_no_second_primitive_contract_exists`).
- `tests/fence/test_lint_imports_catches_phase7_planted_leak.py` — extended with AC-5.a (`test_lint_imports_catches_planted_plugin_import_under_primitive`).
- `_attempts/S5-03.md` — append-only attempt log with three 3-line out-of-test planted-leak evidence blocks.

**NOT touched:** the existing S1-06 primitive contract at `pyproject.toml` lines 548–559 (AC-1 verifies it stays as-is); `tests/fence/test_lint_imports_catches_planted_leak.py` (the Phase-3 file — Phase-7 tests live in the phase-7-specific files); `tests/fence/test_phase3_importlinter_contracts_shape.py` (same reason).

## Out of scope

- **Growing `root_packages` to include `plugins`** — deferred; would require renaming every plugin dir to underscored form (breaks `PLUGINS.lock` digests, plugin loader convention, ADR-0011). Separate Phase-8+ story if it becomes desirable.
- **Renaming `plugins/vulnerability-remediation--node--npm/` (or the Phase-7 sibling) to underscored form** — deferred; massive cross-cutting change.
- **A runtime-closure scan for plugin trees** (analog of `tests/fence/test_phase7_no_llm.py`) — deferred; plugins load via `spec_from_file_location` so `pkgutil.walk_packages` semantics don't apply. If a Phase-8+ story surfaces a lazy-import bypass, a bespoke scan can be added then.
- **Extracting a shared `codegenie._fence.walk_llm_sdk_imports` helper** into `codegenie._fence` — deferred until the rule-of-three is reached (primitive walker + plugin walker = 2). Recorded in Notes-for-implementer.
- **Cryptographic enforcement** — import-linter + AST walker are lint, not runtime fence. Phase 3 ADR-0011 framing.

## Notes for the implementer

- **Do NOT ship a second primitive contract.** S1-06 already landed the `"phase-7 primitive does not import LLM SDKs"` contract at `pyproject.toml` lines 548–559. Its `forbidden_modules` is intentionally six names, intentionally EXCLUDES `anthropic` (Phase-4 ADR-0003 path-scope), intentionally INCLUDES `torch` and `sentence_transformers` (Phase-4 ADR-0003 closure widen). AC-1's `test_no_second_primitive_contract_exists` will fail loudly if you add a duplicate — do not chase that red by editing the S1-06 contract; the correct fix is to delete your duplicate.
- **AC-2 uses an AST walker, NOT import-linter, deliberately.** Reason (documented so a future "helpful cleanup" doesn't undo it): import-linter's `root_packages = ["codegenie"]` cannot include `plugins` because plugin dirs use hyphens (`vulnerability-remediation--node--npm`) that are not valid Python identifiers. The plugin loader deliberately uses `importlib.util.spec_from_file_location` with a synthetic module name (`_codegenie_plugin_...`), so the plugin never appears in the dotted-name graph either. An import-linter contract with `source_modules = ["plugins.X"]` would silently match zero files — the worst possible failure mode. The AST walker traverses `plugins/**/*.py` by *file path*, which is hyphen-tolerant and loader-independent. **Do not migrate this to import-linter.** If a future story finds a way to make plugins Python-package-discoverable (dir renames + `PLUGINS.lock` regen + loader-convention amendment), reconsider then — via ADR amendment to Phase 7 ADR-0009 and this story's Notes.
- **Reuse, do not fork.** `Violation` from `codegenie._phase3_fence`, `FORBIDDEN_LLM_SDKS` from `codegenie._fence`, `packaging.utils.canonicalize_name` for name comparison (mirror `test_phase7_importlinter_contracts_shape.py`'s canonical-set-equality pattern). If you find yourself copying the `Violation` dataclass or literalizing the SDK list, stop.
- **AC-2 walker uses AST, not regex.** `ast.parse(src)` + `ast.walk` finding `ast.Import` and `ast.ImportFrom` nodes is the only way to correctly ignore SDK names appearing in docstrings, comments, or string constants. Regex over source text would false-fire on `"import torch"` in a test docstring.
- **`anthropic` handling — a common trap.** `anthropic` is in `FORBIDDEN_LLM_SDKS`? NO — it was removed from that constant in Phase-4 S1-05 / ADR-0003 (path-scope to the leaf adapter). Confirm: `python -c "from codegenie._fence import FORBIDDEN_LLM_SDKS; print(FORBIDDEN_LLM_SDKS)"` shows six names, no `anthropic`. AC-2's `anthropic`-negative test locks in this behavior — a well-meaning "let's add anthropic to the plugin fence" would false-fire on the leaf-adapter callsite and the negative test catches it before the false-fire ships.
- **AC-3 matcher form is settled.** The pre-hardening draft left this as an open question; validation pinned it: `source_modules = ["codegenie.primitives.vuln_provenance"]`, `as_packages = true`, `forbidden_modules = ["plugins"]`. The `as_packages` flag on the SOURCE side is what covers primitive submodules; the `forbidden_modules = ["plugins"]` entry is a textual pattern that matches `import plugins…` / `from plugins…` inside primitive source files, regardless of whether `plugins` is a real Python package at runtime.
- **Rule of three, watch for it.** After AC-2 lands there are two LLM-SDK walkers (S1-06's `test_phase7_no_llm.py` — runtime closure; this story's `test_no_llm_sdk_imports_in_plugin_trees.py` — AST walk). A third arrival — e.g., a Phase-8 workflow-tree AST walk — is the trigger to extract a shared `codegenie._fence.walk_llm_sdk_imports` helper. Do NOT extract now (Rule 2 — Simplicity First; three similar lines is better than a premature abstraction).
- **Surface conflicts (Rule 7):** if you find that adding the AC-3 contract makes the existing primitive code red (i.e., some unintended `from plugins.X import Y` already exists under `src/codegenie/primitives/vuln_provenance/`), STOP. The fix is to remove the primitive → plugin dependency, not to weaken the contract. The primitive is a port; plugins are adapters; the direction is architectural (ADR-0001, ADR-0004).
- **Performance:** the AC-2 walker runs `ast.parse` on every `plugins/**/*.py` file — currently ~30 files across the shipped plugin tree, plus whatever the Phase-7 plugin adds. Runtime is < 100 ms. `make fence` picks up the new test file automatically; no CI wiring edit needed.
- **CI integration:** `make lint-imports` is already a `make check` dependency; the AC-3 contract fires there. `make fence` is already a `make check` dependency; the AC-2 walker fires there. No `Makefile` edits.
