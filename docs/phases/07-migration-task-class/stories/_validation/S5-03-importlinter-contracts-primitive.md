# Validation report — S5-03 import-linter contracts

**Story:** `docs/phases/07-migration-task-class/stories/S5-03-importlinter-contracts-primitive.md`
**Validator run:** 2026-08-14 (`phase-story-validator` first pass — pre-executor)
**Verdict:** **HARDENED** — the goal is preserved; three ACs required substantive rewrite because the story-as-drafted specified a mechanism (import-linter static contract over `plugins/*`) that cannot work with the codebase's actual plugin-loading convention. No RESCUE because the *intent* (fence LLM-SDK imports out of the plugin tree; fence primitive → plugins direction) is coherent and can be delivered by substituting an AST-based file-path fence for the plugin-tree half while keeping import-linter for the primitive half.

## Stage 1 — Context brief

**Story goal (preserved):** Extend Phase 7's CI fencing so (a) the plugin tree cannot import LLM SDKs and (b) the `vuln_provenance` primitive cannot import from `plugins/*` (port-before-adapter direction).

**Pipeline position:** Step 5 of Phase 7 High-level-impl (fence-before-edits). Depends on S5-01 (byte-edit allowlist; pyproject.toml is row 9). Sibling to S5-02 (probes live under plugin tree).

**Load-bearing constraints read:**
- **Phase 7 ADR-0004** — primitive lives at `src/codegenie/primitives/vuln_provenance/`; Consequences clause names "an `import_linter` contract extends the cold-start defense … to the new primitive."
- **Phase 7 ADR-0005** — plugin probes ship under `plugins/distroless-migration--node--npm/probes/`.
- **Phase 7 ADR-0009** — the 10-row byte-edit allowlist; row 9 is `pyproject.toml`. Additional import-linter contracts are additive bands within row 9.
- **Phase 4 ADR-0003** — `anthropic` is path-scoped to the leaf adapter and **excluded** from the `codegenie.primitives.vuln_provenance` contract's `forbidden_modules`. This is critical: the story's original AC-1 lists `anthropic` in `forbidden_modules`, which contradicts the truth already in `pyproject.toml`.
- **CLAUDE.md — Extension by addition:** the mechanism should generalize so that Phase 8+ plugins get free fence coverage. Per-plugin rows are a Ship-of-Theseus smell.

**Codebase reality (Rule 8 — read before you write):**
- `pyproject.toml § [tool.importlinter]` line 548–559 **already** contains the contract for `codegenie.primitives.vuln_provenance` under the name `"phase-7 primitive does not import LLM SDKs"`. It was landed by S1-06 (GREEN, 2026-05-19). Its `forbidden_modules` is `["openai", "langchain", "langgraph", "transformers", "sentence_transformers", "torch"]` — **six** names, `anthropic` intentionally absent (Phase-4 ADR-0003 path-scope) and `torch` + `sentence_transformers` intentionally added (Phase-4 ADR-0003 closure widen).
- `tests/fence/test_phase7_importlinter_contracts_shape.py` **already exists** and shape-pins the contract via canonicalized-name comparison against `codegenie._fence.FORBIDDEN_LLM_SDKS`. This is the phase-7-specific version of the phase-3 shape-pin test.
- `tests/fence/test_lint_imports_catches_phase7_planted_leak.py` **already exists** and does the planted-`import torch` proof against the primitive tree.
- `pyproject.toml` `root_packages = ["codegenie"]` — **`plugins/` is not walked by import-linter.** Adding `plugins` to root_packages is not viable because plugin directories use hyphens (`plugins/vulnerability-remediation--node--npm/`, `plugins/distroless-migration--node--npm/`) which are not valid Python identifiers.
- `src/codegenie/plugins/loader.py` line 293–321 — the loader deliberately uses `importlib.util.spec_from_file_location(mod_name, api_path)` with a **synthetic module name** `_codegenie_plugin_{slug_with_underscores}_api`. Plugin `api.py` and its intra-plugin siblings never appear in `sys.modules` under a `plugins.*` dotted name. The docstring on `plugins/vulnerability-remediation--node--npm/__init__.py` is explicit: "loaded via `importlib.util.spec_from_file_location` — NOT a bare `import plugins.vulnerability_remediation__node__npm`."
- Consequence: **import-linter's static graph cannot see plugin tree files as `plugins.*` modules.** A contract with `source_modules = ["plugins.distroless_migration_node_npm"]` would silently match zero files.

**Adjacent-precedent pattern for the correct plugin-tree mechanism:** `tests/fence/test_no_any_in_plugin_surface.py` uses `walk_any_annotations()` from `codegenie._phase3_fence` — an **AST walk over file paths**, not module names — to enforce the "no `Any` under `src/codegenie/{plugins,transforms}`" rule. That shape (path-walking + AST inspection) is the only mechanism that works for the hyphenated plugin trees.

## Stage 2 — Critic findings

### Coverage critic

| # | Sev | Finding |
|---|---|---|
| Cov-1 | block | AC-1 duplicates the already-shipped S1-06 contract; adding a second contract creates two sources of truth for the same forbidden set. |
| Cov-2 | block | AC-2's mechanism (`source_modules = ["plugins.distroless_migration_node_npm"]`) matches zero files because (a) `plugins` is not in `root_packages` and (b) the loader uses `spec_from_file_location` — the plugin never appears in the dotted-name graph. AC-2 as written passes vacuously = worst possible failure mode. |
| Cov-3 | block | AC-3's `forbidden_modules = ["plugins"]` matcher form is left as an open question in the story itself, with no AC that pins the correct form. Executor would ship a guess. |
| Cov-4 | harden | No AC verifies "adding a Phase 8+ plugin gets fence coverage for free" — Open/Closed compliance for the fence itself. |
| Cov-5 | harden | No mutation-resistance metamorphic test for the contracts (e.g., "removing the contract makes the planted-leak test flip green → red"). Existing planted-leak tests are one-way. |

### Test-quality critic

| # | Sev | Finding |
|---|---|---|
| TQ-1 | block | AC-5.c uses the wrong plugin slug: `from plugins.vulnerability_remediation_node_npm import adapters` — that's the Phase-3 plugin, not the Phase-7 distroless plugin. Copy-paste error that would ship a broken test. |
| TQ-2 | harden | AC-5's "assert failure message names X" is fragile string matching. The existing `test_lint_imports_catches_phase7_planted_leak.py` uses lower-cased substring matching + dumps stdout on failure — mirror that style. |
| TQ-3 | harden | AC-4 shape-pin lists 5 SDK names literally. It should pin against `FORBIDDEN_LLM_SDKS` via `packaging.utils.canonicalize_name` set-equality — the pattern already established in `test_phase7_importlinter_contracts_shape.py`. Literal 5-name lists drift silently. |
| TQ-4 | harden | The TDD plan's Red step ("plant a file; verify `make lint-imports` exits 0") is a good demonstration of the gap-before-fence, but there's no AST-fence equivalent for the plugin-tree path (which is the mechanism that actually works). Add a mirror Red step for the plugin-tree AST fence. |

### Consistency critic

| # | Sev | Finding |
|---|---|---|
| Con-1 | block | AC-1 contradicts S1-06's shipped contract (already GREEN). Adding a second contract for the same source-module forks the source of truth. |
| Con-2 | block | AC-1's `forbidden_modules = ["anthropic", "langgraph", "openai", "langchain", "transformers"]` contradicts Phase-4 ADR-0003, which moved `anthropic` to path-scope (excluded from this contract) and widened the closure to include `torch` and `sentence_transformers`. |
| Con-3 | block | Story references `tests/fence/test_phase3_importlinter_contracts_shape.py` for extension — but a Phase-7-specific version exists at `tests/fence/test_phase7_importlinter_contracts_shape.py`. Rule 8 failure in the story itself. |
| Con-4 | block | Story references `tests/fence/test_lint_imports_catches_planted_leak.py` — but a Phase-7-specific version exists at `tests/fence/test_lint_imports_catches_phase7_planted_leak.py`. Extend the phase-7 version. |
| Con-5 | harden | "Phase 7 ADR-0011" citation in the ADRs-honored line is wrong — Phase 7 ADR-0011 is "No Chainguard credential class." The intended framing citation is Phase 3 ADR-0011 (already cited correctly later) and production ADR-0043 (extension-by-addition-means-no-silent-edits). |
| Con-6 | harden | AC-3/AC-5 references mix `plugins.vulnerability_remediation_node_npm` and `plugins.distroless_migration_node_npm`. Choose one for AC-5 planted-leak evidence (must match a real directory) and be consistent. |

### Design-patterns critic

| # | Sev | Finding |
|---|---|---|
| DP-1 | structural | Per-plugin contract rows is primitive obsession over plugins and violates Open/Closed at the file boundary: Phase 8+ adds one row per plugin. The pattern that scales is **one path-walking AST fence over `plugins/**/*.py`** that discovers new plugin directories automatically. Matches the `walk_any_annotations` / `PHASE3_ROOTS` precedent (Phase 3 ADR-0010). Adding a plugin gets fence coverage for free — no `pyproject.toml` or fence-file edit. |
| DP-2 | structural | The story's chosen mechanism (import-linter for plugin tree) is **structurally incompatible with the plugin loader convention** (`spec_from_file_location` + hyphenated dirs). This is not a small paper-cut; it is why the mechanism must be substituted for the plugin-tree half. The primitive-tree half (AC-3) is import-linter-compatible because `src/codegenie/primitives/vuln_provenance/` IS in root_packages. |
| DP-3 | harden | Reuse `codegenie._fence.FORBIDDEN_LLM_SDKS` (single source of truth) as the forbidden set both for the import-linter matcher AND for the AST-fence walker. Never fork the constant. Precedent: every existing fence canonicalizes against it. |
| DP-4 | nit | Story's "surface the decision in `_attempts/S5-03.md`" for AC-3's matcher-form open question is decision-in-implementation for a structural question. Pin the form at validation-time. |

## Stage 3 — Researcher (skipped)

No `NEEDS RESEARCH` findings surfaced. The AST-file-walk pattern is already the codebase's precedent (`walk_any_annotations`); no external research needed.

## Stage 4 — Synthesis + edits

Conflict resolution: **Consistency wins** (source of truth is the arch/ADR + the already-shipped S1-06 contract). Design-patterns' DP-1 restructuring aligns with Consistency (removing duplication) rather than conflicting with it, so both fire. Rule 3 (Surgical Changes) constrains the scope: the primitive-side contract (AC-3) stays import-linter; only the plugin-tree half (AC-2) gets the mechanism substitution.

### Edits applied to the story

- **Front-matter** — ADRs-honored line: `Phase 7 ADR-0011` corrected to `production ADR-0043` (extension-by-addition-means-no-silent-edits); `S1-06` added to Depends-on (prior art); `S3-03` added to Depends-on with a Preconditions call-out for BLOCKED status; Status stays `Ready` pending executor pickup.
- **Preconditions section** — new; documents S1-06 as prior art for the primitive contract, S3-03 BLOCKED implications for the plugin-tree fence, and the AST-vs-import-linter mechanism split.
- **Context** — rewritten to reflect the true state (S1-06 shipped the primitive contract; the plugin tree has no coverage today; the loader convention rules out import-linter for the plugin trees).
- **Goal** — restated as three narrower goals:
  1. Verify the S1-06 primitive contract remains shape-pinned (no new contract).
  2. Add an **AST-file-walk fence** over `plugins/**/*.py` rejecting `import <SDK>` for any name in `FORBIDDEN_LLM_SDKS` (mechanism substituted from import-linter).
  3. Add an **import-linter contract** enforcing port-before-adapter direction: `codegenie.primitives.vuln_provenance` must not import from `plugins`.
- **AC-1 (was: duplicate primitive contract)** — rewritten to a **shape-verification AC** citing S1-06's contract. No new contract added. The AC exists to make the executor prove the S1-06 contract is still the canonical source (mutation-resistance for the S1-06 shape-pin).
- **AC-2 (was: import-linter for plugin tree)** — rewritten as an AST-file-walk fence at `tests/fence/test_no_llm_sdk_imports_in_plugin_trees.py`. Reuses `FORBIDDEN_LLM_SDKS`. Walks `plugins/**/*.py` (excluding `__pycache__`, planted-test files with the `_test_planted_` prefix). Fails on any `import X` or `from X import ...` where `canonicalize_name(X.split(".")[0])` matches `FORBIDDEN_LLM_SDKS`. Covers every plugin tree (existing `vulnerability-remediation--node--npm/` and future `distroless-migration--node--npm/`) automatically.
- **AC-3 (was: import-linter primitive → plugins)** — kept as import-linter, matcher form pinned: `source_modules = ["codegenie.primitives.vuln_provenance"]`, `as_packages = true`, `forbidden_modules = ["plugins"]`. Rationale: import-linter walks source_modules (in root_packages) and inspects their `import` statements textually; `forbidden_modules = ["plugins"]` matches any `plugins` / `plugins.X` import found in a source file, regardless of whether `plugins` is itself in `root_packages`. `as_packages = true` on the source side is load-bearing (submodules under `primitives.vuln_provenance`); the semantics are settled.
- **AC-4** — extends `test_phase7_importlinter_contracts_shape.py` (correct file) with one new parametrized row for the port-before-adapter contract. Shape-pin: `source_modules == ["codegenie.primitives.vuln_provenance"]`, `as_packages is True`, `forbidden_modules == ["plugins"]`.
- **AC-5** — split into two sub-groups:
  - **AC-5.a** — planted-leak for AC-3 (port-before-adapter): plant `src/codegenie/primitives/vuln_provenance/_test_planted_plugin_import.py` containing `from plugins.vulnerability_remediation_node_npm import adapters` (the plugin slug the STATIC AST refers to; the runtime loader uses a synthetic name, but the AST is what import-linter reads). Assert `make lint-imports` exits non-zero and names `plugins` + `vuln_provenance` in stdout. Extend `test_lint_imports_catches_phase7_planted_leak.py` (correct file). Fixture-managed cleanup (try/finally).
  - **AC-5.b** — planted-leak for AC-2 (plugin-tree AST fence): plant `plugins/vulnerability-remediation--node--npm/_test_planted_torch_import.py` containing `import torch`. Assert `pytest tests/fence/test_no_llm_sdk_imports_in_plugin_trees.py` exits non-zero and names `torch` + the file path. Fixture-managed cleanup. **`torch` is the canonical planted SDK** (not `anthropic`, which is path-scoped elsewhere and would false-negative here per the same rationale documented in `test_lint_imports_catches_phase7_planted_leak.py`).
  - **AC-5.c** — three-line out-of-test evidence per AC in `_attempts/S5-03.md`: red SHA / removal SHA / green SHA. Independent demonstrations.
- **AC-6/AC-7/AC-8** — kept, wording tightened to name the corrected files.
- **Files to touch** — corrected file list; adds the new `tests/fence/test_no_llm_sdk_imports_in_plugin_trees.py` (net-new file, additive under Rule 3 / ADR-0009 for tests-not-src).
- **Implementation outline + TDD plan** — rewritten to match the AC restructuring; Red step for AC-2 uses the AST fence (import-linter would false-green).
- **Out of scope** — expanded to explicitly name: (i) growing `root_packages`, (ii) renaming plugin dirs to underscored form (major cross-cutting), (iii) making plugins Python-package-discoverable via `[tool.setuptools.packages]` (would require dir renames or `find_packages(exclude=...)` gymnastics).
- **Notes for the implementer** — expanded with the design-pattern rationale (DP-1 / DP-2 / DP-3), including the explicit reason why the plugin-tree half uses an AST fence and not import-linter, so a future engineer doesn't "helpfully" migrate it and re-open the vacuously-passing gap.

### Design-pattern opportunities elevated to ACs

- **AC-2's AST fence walks the plugin tree by *directory*, not by explicit slug enumeration.** This is Open/Closed at the file boundary: adding a Phase 8+ plugin gets fence coverage for free. Restated as an observable AC: "adding a new plugin directory under `plugins/` must NOT require editing `test_no_llm_sdk_imports_in_plugin_trees.py` or `pyproject.toml`." A parametrized `pytest` test that discovers plugin dirs at module import time via `sorted(Path('plugins').glob('*/'))` satisfies this. Third-plugin threshold reached (existing Phase-3 plugin + Phase-7 distroless plugin + any Phase-8 plugin) — kernel/extract is justified, not premature.

### Verdict rationale

**HARDENED, not RESCUE.** The story's goal is preserved; the mechanism swap is deterministic (existing precedent — `walk_any_annotations` — is the template). The critical block-severity findings (Cov-1/2/3, Con-1/2/3/4, TQ-1, DP-1/2) all have concrete, minimally invasive fixes.

**Blast radius:** small — one new test file (additive), three ACs rewritten, no new import-linter contract added (only a shape-verification for the existing S1-06 contract + one new contract for AC-3), no new PyPI dep.

**What did NOT get elevated to an AC:**
- Growing `root_packages` to include `plugins` — deferred (dir-rename cross-cutting change; separate story or Phase 8+ ADR).
- Renaming plugin dirs from hyphenated to underscored form — deferred (breaks `PLUGINS.lock` digests, plugin loader convention, ADR-0011).
- A `codegenie._fence.FORBIDDEN_LLM_SDKS`-consuming shared walker module — deferred (rule-of-three not reached for this shape; primitive walker + plugin walker = 2). Recorded in Notes-for-implementer.
