# Story S7-02 — Fixtures batch 2: `monorepo-pnpm` + **load-bearing** `stale-scip` full materialization

**Step:** Step 7 — Plant five-repo fixture portfolio + per-probe golden files + remaining adversarial corpus
**Status:** Ready
**Effort:** M
**Depends on:** S7-01 (fixtures batch 1 — patterns + shape-test conventions transfer wholesale), S4-02 (`stale-scip` STUB + `test_stale_scip_fixture.py` CI-gating adversarial — this story is the FULL materialization of the fixture the adversarial already references)
**ADRs honored:** ADR-0001 (allowlisted binaries — `regenerate.sh` for both fixtures invokes only allowlisted tools, including `scip-typescript` from S1-06's list), ADR-0006 (`IndexFreshness` location — `CommitsBehind` is the structural assertion the fixture's adversarial test reads), ADR-0007 (no plugin loader — neither fixture seeds `plugins/`), ADR-0009 (pytest-xdist veto — closed-set fixture trees, regen-script-only mutation surface).

## Context

This story lands the remaining two of the five fixture repos:

1. **`monorepo-pnpm/`** — exercises `DepGraphProbe` cross-package edges via a real pnpm workspace. Three packages (`packages/lib-a/`, `packages/lib-b/`, `packages/app/`) with `app` depending on both libs, `lib-b` depending on `lib-a`. The `dep_graph` slice for this fixture contains real inter-package edges; `tree_sitter_import_graph` records the `import` adjacency between the workspace packages.
2. **`stale-scip/`** — **the load-bearing roadmap exit-criterion fixture.** Pre-populated SCIP index from a prior commit; HEAD has moved since; `IndexHealthProbe` (S4-01) must catch the staleness in CI (`test_stale_scip_fixture.py` from S4-02). S4-02 landed a STUB directory + minimal SCIP blob + `README.md` policy so the adversarial test could run during Step 4; this story produces the **full materialization** — populated `.ts` files, a real SCIP index built from a prior commit, two committed commits documented in the fixture so the staleness path is real.

The synthesis ledger pins three Step-7 implementation risks to this story:

- **Risk #3 (`stale-scip` regeneration silently breaks the load-bearing exit).** A future contributor regenerates the SCIP fixture against current HEAD; the test still passes (because `CommitsBehind.n >= 0` is trivially satisfied) but no longer exercises staleness. **Defense:** `regenerate.sh` for `stale-scip` MUST error out if invoked against current HEAD; `README.md` documents the structural assertion (`CommitsBehind.n >= 1` **and** `last_indexed != current_HEAD`); the S4-02 adversarial asserts both inequalities — but the fixture's `regenerate.sh` is the front-line guard.
- **Risk #5 (golden-file non-determinism).** Inherited from S7-01; this story compounds it because `monorepo-pnpm`'s `pnpm install` against the public registry may produce slightly different lockfile bytes across runs. The discipline: pin the lockfile bytes at fixture creation time, never re-run `pnpm install` in `regenerate.sh` (the lockfile is committed; the regen script asserts it has not drifted).
- **Risk #8 (Phase 3 protocol drift).** `monorepo-pnpm` is one of the two fixtures Phase 3's first plugin author will use as a target (per "Next-phase integration" table in `phase-arch-design.md`). The dep-graph evidence this fixture produces is what Phase 3's `DepGraphAdapter` will consume; the fixture's shape is part of the Protocol contract. Document this in the fixture's `README.md` so Phase 3's author sees the explicit handoff.

This story is also the natural landing point for the **shared `_shape_test_kernel.py`** the Rule-of-Three guard in S7-01 deferred. With five fixtures (Phase 1's `node_typescript_helm/` + S7-01's three + this story's two), the kernel earns its keep.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Testing strategy" → "Fixture portfolio"` — `monorepo-pnpm` + `stale-scip` rows.
  - `../phase-arch-design.md §"Component design" #1` (`IndexHealthProbe` — the `stale-scip` adversarial consumer).
  - `../phase-arch-design.md §"Component design" #11` (`DepGraphProbe` — `monorepo-pnpm`'s primary exerciser).
  - `../phase-arch-design.md §"Edge cases"` row 11 (stale-scip fixture in CI — deliberate seed; the table row this story implements).
  - `../phase-arch-design.md §"Implementation risks"` #3, #5, #8.
- **Phase ADRs:** ADR-0006 (`IndexFreshness` sum type — `CommitsBehind` variant is the structural assertion), ADR-0007 (no plugin loader — `monorepo-pnpm` ships zero `plugins/`).
- **Implementation plan:** `../High-level-impl.md §"Step 7"` — `monorepo-pnpm` + `stale-scip` bullets.
- **Source design:** `../final-design.md §"Open questions"` #7 (`stale-scip` regeneration policy — this story implements the named documentation discipline).
- **Existing code:**
  - `tests/adv/phase02/test_stale_scip_fixture.py` (S4-02 — the adversarial this story's fixture must satisfy).
  - `tests/fixtures/portfolio/stale-scip/README.md` (S4-02 stub — this story extends it).
  - `tests/fixtures/portfolio/minimal-ts/` + `native-modules/` + `distroless-target/` (S7-01 — shape conventions transfer).

## Goal

Two fixtures exist under `tests/fixtures/portfolio/`:

1. **`monorepo-pnpm/`** — pnpm workspace with three packages; root `pnpm-workspace.yaml`; `packages/lib-a/{package.json,src/index.ts}`, `packages/lib-b/{package.json,src/index.ts}` (imports `lib-a`), `packages/app/{package.json,src/index.ts}` (imports both); a single root `pnpm-lock.yaml` resolving all internal + minimal external deps; root `Dockerfile`, `.github/workflows/ci.yml`, `tsconfig.json` at each package level; shape test (`tests/unit/test_fixture_monorepo_pnpm_shape.py`).
2. **`stale-scip/`** — full materialization: TypeScript source tree (≤ 50 files), a real SCIP index file at `.codegenie/context/raw/scip-index.scip` **committed** (this is the only fixture in the portfolio where `.codegenie/` IS committed — and only the `raw/scip-index.scip` blob, not `.codegenie/cache/`); commit history with at least two commits, with the SCIP built from the older commit and HEAD pointed at the newer one. `regenerate.sh` errors out if invoked against current HEAD (Implementation risk #3). `README.md` explicitly documents the regeneration ritual.

The shared `_shape_test_kernel.py` is extracted to `tests/fixtures/portfolio/_shape_test_kernel.py` and consumed by all five fixtures' shape tests + Phase 1's `node_typescript_helm/` shape test.

## Acceptance criteria

**`monorepo-pnpm/` fixture tree shape**

- [ ] **AC-1.** `tests/fixtures/portfolio/monorepo-pnpm/` directory exists.
- [ ] **AC-2 — `pnpm-workspace.yaml`** declares `packages: ["packages/*"]`; parses via `safe_yaml.load`.
- [ ] **AC-3 — `package.json`** at root declares `"name": "monorepo-pnpm-fixture"`, `"private": true`, `"workspaces": ["packages/*"]` (redundant with `pnpm-workspace.yaml`, but pnpm reads either); `"devDependencies": {"typescript": "^5.3.0"}`; no `dependencies`. Parses via `safe_json.load`.
- [ ] **AC-4 — `packages/lib-a/package.json`** declares `"name": "@monorepo-pnpm/lib-a"`, `"version": "0.0.1"`, `"main": "src/index.ts"`, no dependencies. Parses.
- [ ] **AC-5 — `packages/lib-a/src/index.ts`** exports a single function `add(a: number, b: number): number`.
- [ ] **AC-6 — `packages/lib-b/package.json`** declares `"name": "@monorepo-pnpm/lib-b"`, `"version": "0.0.1"`, `"main": "src/index.ts"`, `"dependencies": {"@monorepo-pnpm/lib-a": "workspace:*"}` (the load-bearing pnpm workspace-protocol marker `DepGraphProbe` exercises). Parses.
- [ ] **AC-7 — `packages/lib-b/src/index.ts`** imports from `@monorepo-pnpm/lib-a` and exports a derived function. The `import` statement is the load-bearing edge `tree_sitter_import_graph` records.
- [ ] **AC-8 — `packages/app/package.json`** declares `"name": "@monorepo-pnpm/app"`, `"version": "0.0.1"`, `"main": "src/index.ts"`, `"dependencies": {"@monorepo-pnpm/lib-a": "workspace:*", "@monorepo-pnpm/lib-b": "workspace:*", "express": "^4.18.2"}`. Parses.
- [ ] **AC-9 — `packages/app/src/index.ts`** imports from both internal packages + `express`; declares a trivial Express handler. The two internal imports are what `dep_graph` slice records as cross-package edges.
- [ ] **AC-10 — root `pnpm-lock.yaml`** is committed; `lockfileVersion: '6.0'`; resolves all three internal packages via the `workspace:*` protocol; resolves `express` and its transitive deps to pinned versions. Parses via `safe_yaml.load`. **The lockfile is committed once and never regenerated by `regenerate.sh`** — regen is `pnpm install --frozen-lockfile` only (asserts the lockfile has not drifted).
- [ ] **AC-11 — `tsconfig.json`** at each package level; root `tsconfig.json` with `"references"` declaring all three packages (TS project-references shape; exercises `tsconfig`-walk paths).
- [ ] **AC-12 — root `Dockerfile`** is multi-stage; `FROM node:20-slim AS build` builds the app; final stage `FROM node:20-slim`; `USER node`; `CMD ["node", "packages/app/dist/index.js"]`. Parses by the Phase-2 Dockerfile probe.
- [ ] **AC-13 — root `.github/workflows/ci.yml`** declares one job `build` with `run: pnpm install --frozen-lockfile && pnpm -r build && pnpm -r test`. Parses via `safe_yaml.load`.
- [ ] **AC-14 — `README.md`** lists every file by relpath, names every probe in `consumers`, AND explicitly documents (in prose) "Phase 3 entry-gate target — `DepGraphAdapter`'s first plugin will produce cross-package edges from this fixture." This is the Risk-#8 named handoff.

**`stale-scip/` fixture full materialization**

- [ ] **AC-15.** `tests/fixtures/portfolio/stale-scip/` directory contains the full TypeScript source tree (≤ 50 files); the S4-02 stub directory + minimal SCIP blob is replaced wholesale by the full fixture.
- [ ] **AC-16 — source tree.** `src/` contains at least 5 `.ts` files with real `export` / `import` statements; `package.json` declares `typescript` devDependency; `tsconfig.json` is valid JSONC.
- [ ] **AC-17 — committed `.codegenie/context/raw/scip-index.scip`** exists. It is the ONLY file under `.codegenie/` that is committed (not `.codegenie/cache/`, not anything else). The fixture's `.gitignore` allowlists this specific path: `.codegenie/` + `!.codegenie/context/` + `!.codegenie/context/raw/` + `!.codegenie/context/raw/scip-index.scip`.
- [ ] **AC-18 — git history.** The fixture has **at least two committed commits** with distinct SHAs. The SCIP at AC-17 was built from the earlier commit's tree. HEAD points at the later commit. After-fixture-checkout, `git rev-parse HEAD` returns a different SHA from the SCIP's `last_indexed_commit` metadata. (Mechanics: the fixture lives in its own subtree but tracks its own micro-git-history via a bundled `packed-refs` + `HEAD` file in a `.git-fixture/` directory, OR by checking the fixture into the parent repo as-is and recording the prior-commit SHA in a sibling `last-indexed-commit.txt` file — implementer picks; S4-02's stub already chose one path, this story honors it.)
- [ ] **AC-19 — `last-indexed-commit.txt`** (or equivalent metadata file the fixture's `regenerate.sh` reads) records the prior commit SHA the SCIP was built from. The S4-02 adversarial reads this file to assert `last_indexed != current_HEAD`.
- [ ] **AC-20 — `regenerate.sh` errors out if invoked against current HEAD.** Concretely: the script checks `git rev-parse HEAD` against `last-indexed-commit.txt`. If they match, the script writes a clear error message (`"ERROR: Refusing to regenerate stale-scip SCIP against current HEAD. The whole point of this fixture is that HEAD has moved past last_indexed. See README.md §Regeneration policy."`) and exits 1. Verified by a pytest under `tests/unit/test_stale_scip_regenerate_refuses_current_head.py` that runs `regenerate.sh` against a pristine fixture (skipped unless `CODEGENIE_REGEN_FIXTURES=1`).
- [ ] **AC-21 — `regenerate.sh` legitimate path.** When invoked correctly (with `--from-commit <prior-SHA>` or via the `last-indexed-commit.txt` it has not yet updated), the script: (a) checks out the prior commit; (b) runs `scip-typescript` (via `run_allowlisted`) producing a SCIP index; (c) writes the SCIP to `.codegenie/context/raw/scip-index.scip`; (d) updates `last-indexed-commit.txt` to the just-built-from SHA; (e) returns to HEAD; (f) does NOT update HEAD itself.
- [ ] **AC-22 — `README.md`** documents the regeneration ritual explicitly. Required sections: "Why this fixture exists", "Structural assertion (CommitsBehind.n >= 1 AND last_indexed != current_HEAD — tool-version-agnostic)", "Regeneration policy — DO NOT retarget against current HEAD", "How to add a new commit (and the SCIP-vs-HEAD invariant that survives)". The README is the Risk-#3 front-line guard.

**Shared `_shape_test_kernel.py` extraction**

- [ ] **AC-23 — `tests/fixtures/portfolio/_shape_test_kernel.py`** is extracted with the `_FileSpec`, `_ProbeName`, `_ParserKind` types, the closed-set predicates (`enumerate_tracked`, the parametrized-test-body factories `make_existence_test`, `make_parses_test`, `make_content_invariants_test`, `make_line_endings_test`, `make_no_forbidden_subpaths_test`, `make_tree_is_closed_set_test`, `make_readme_references_every_spec_test`). The kernel passes `mypy --strict`.
- [ ] **AC-24 — every fixture's shape test consumes the kernel.** `tests/unit/test_fixture_{minimal_ts,native_modules,distroless_target,monorepo_pnpm,stale_scip}_shape.py` import the kernel; each declares only its `_FIXTURE` path + its `_FILE_SPECS` tuple + its content-check predicate functions. The parametrized-test machinery lives in the kernel.
- [ ] **AC-25 — Phase 1's `test_fixture_node_typescript_helm_shape.py` also migrates to the kernel.** This is the sixth consumer and is the final demonstration that the kernel pays off (Rule of Three conclusively past). The migration preserves every existing AC (S2-03's AC-1..AC-23) — those still pass after the kernel migration.
- [ ] **AC-26 — kernel exposes `_ProbeName` as the Phase-1 + Phase-2 closed set.** The Literal grows from Phase 1's 6 entries to the full 33 Phase-1 + Phase-2 probe names listed in S7-01's AC-25 example block. A test asserts the closed set runtime-equals the documented one (preserves S2-03's AC-18).

**Closed-set + forbidden-subpath + line-ending invariants per new fixture**

- [ ] **AC-27 — `monorepo-pnpm/` closed-set complement.** `test_fixture_monorepo_pnpm_tree_is_closed_set` walks the tree and asserts no extra/missing files. `node_modules/` MUST NOT be present (gitignored AND post-`pnpm install --frozen-lockfile` cleanup is not run — the install never happens in regen).
- [ ] **AC-28 — `stale-scip/` closed-set complement.** `test_fixture_stale_scip_tree_is_closed_set` walks the tree and asserts no extra/missing files — with the `.codegenie/context/raw/scip-index.scip` allowlisted (the kernel's `enumerate_tracked` defaults to excluding `.codegenie/`; this fixture overrides the default with an explicit `include_paths={".codegenie/context/raw/scip-index.scip"}`).
- [ ] **AC-29 — no `.codegenie/cache/` under either new fixture.** Inherited from S7-01's central guard test (`tests/unit/test_no_committed_codegenie_cache_under_portfolio_fixtures.py`) — passes against the new fixtures.
- [ ] **AC-30 — line endings per file** for every file in both new fixtures (the kernel-provided test).
- [ ] **AC-31 — `regenerate.sh` invokes only allowlisted binaries** per fixture (the kernel-provided static check).

**`stale-scip` structural assertion survives regeneration (Risk #3 defense)**

- [ ] **AC-32 — adversarial test from S4-02 passes against the full fixture.** `tests/adv/phase02/test_stale_scip_fixture.py` (landed in S4-02; this story does NOT edit it) asserts `isinstance(slice.freshness, Stale)`, `isinstance(slice.freshness.reason, CommitsBehind)`, `slice.freshness.reason.n >= 1`, **and** `slice.freshness.reason.last_indexed != current_HEAD`. With the full materialization in place, this CI-gating test passes.
- [ ] **AC-33 — `last_indexed != current_HEAD` (both inequalities) is the structural assertion** in the adversarial — not just `n >= 1` (which `>= 0` would trivially satisfy). The S4-02 file already encodes this; this story's contribution is making the inequality non-trivially true.

**Determinism, audit hygiene, type cleanliness**

- [ ] **AC-34 — `regenerate.sh` byte-identical-twice** for `monorepo-pnpm/` (manual local verification; documented in PR). For `stale-scip/`, the byte-identical-twice claim is restricted: re-running `regenerate.sh --from-commit <same-SHA>` twice produces a byte-identical SCIP only if `scip-typescript` is itself deterministic for the same input (it is; documented in the README).
- [ ] **AC-35 — every new shape-test + kernel passes `mypy --strict`.**
- [ ] **AC-36 — Phase 1's `test_fixture_node_typescript_helm_shape.py` still passes** after the kernel migration. Mandatory: run the existing test suite, observe green; the migration is refactor-by-extraction, not behavior change.

## Implementation outline

1. **Plant `monorepo-pnpm/` first (no risky surface).**
   - `mkdir -p tests/fixtures/portfolio/monorepo-pnpm/{packages/lib-a/src,packages/lib-b/src,packages/app/src,.github/workflows}`.
   - Write the shape test (`tests/unit/test_fixture_monorepo_pnpm_shape.py`) — TDD red, modeled on S7-01's three fixtures (still using inlined parametrized-test bodies; the kernel extraction comes later).
   - Plant each file per AC-2..AC-14.
   - Generate the `pnpm-lock.yaml` once locally on a scratch directory matching the manifest; copy it in; commit it; `regenerate.sh` is `pnpm install --frozen-lockfile` (asserts the lockfile is intact, does NOT regenerate it).
   - Run shape test. Green.
2. **Plant `stale-scip/` full materialization.**
   - Read the S4-02 stub (`tests/fixtures/portfolio/stale-scip/README.md` + the stub blob) to honor the design decision it codified (`.git-fixture/` vs sibling-`last-indexed-commit.txt` — pick whichever S4-02 chose).
   - Write the shape test (`tests/unit/test_fixture_stale_scip_shape.py`) — still inlined parametrized bodies; TDD red.
   - Plant the TypeScript source tree (≤ 50 `.ts` files; trivial `export`/`import` content).
   - On a scratch worktree: commit the source as commit #1. Run `scip-typescript` (manually, via `run_allowlisted("scip-typescript", ...)`) against commit #1's tree. Capture `scip-index.scip`. Move HEAD forward with at least one additional commit that changes a file the SCIP indexed. Copy the SCIP into the fixture at `.codegenie/context/raw/scip-index.scip`. Record commit #1's SHA in `last-indexed-commit.txt`.
   - Plant the carefully-allowlisted `.gitignore`: `.codegenie/` + `!.codegenie/context/` + `!.codegenie/context/raw/` + `!.codegenie/context/raw/scip-index.scip`. Verify `git status` shows only the allowlisted SCIP file as tracked under `.codegenie/`.
   - Write `regenerate.sh` per AC-20 + AC-21. **Test it.** Run it against a pristine checkout, observe the refusal (AC-20). Run it with `--from-commit <commit-1-SHA>`, observe successful regeneration (AC-21). Update `README.md` with the explicit ritual (AC-22).
   - Run the existing `tests/adv/phase02/test_stale_scip_fixture.py` from S4-02 — it must pass against the full fixture (AC-32 + AC-33).
   - Run `pytest tests/unit/test_fixture_stale_scip_shape.py -v`. Green.
3. **Extract the shared kernel.**
   - Compare the three S7-01 shape-test files + the two new shape-test files + Phase 1's `test_fixture_node_typescript_helm_shape.py`. The duplicated machinery is in the parametrized-test bodies; the variable parts are `_FIXTURE`, `_FILE_SPECS`, the content-check predicates, the `_ProbeName` Literal (already shared across S7-01 fixtures — confirm it matches).
   - Write `tests/fixtures/portfolio/_shape_test_kernel.py` with the `_FileSpec`, `_ProbeName`, `_ParserKind` types + the test-body factories (`make_existence_test`, `make_parses_test`, `make_content_invariants_test`, `make_line_endings_test`, `make_no_forbidden_subpaths_test`, `make_tree_is_closed_set_test`, `make_readme_references_every_spec_test`).
   - One at a time: migrate `test_fixture_minimal_ts_shape.py` → kernel-consumer; run; observe green. Same for `native_modules`, `distroless_target`, the two new fixtures, AND Phase 1's `node_typescript_helm`.
   - Verify all six shape tests still pass.
4. **Run the central no-committed-cache guard** (`tests/unit/test_no_committed_codegenie_cache_under_portfolio_fixtures.py` from S7-01) — it now must allowlist `stale-scip/.codegenie/context/raw/scip-index.scip` as an exception. Update the test to assert: under `tests/fixtures/portfolio/`, no `.codegenie/cache/` exists, AND the only `.codegenie/` content is the allowlisted `stale-scip/.codegenie/context/raw/scip-index.scip`.
5. Final pass: `mypy --strict`, `ruff`, `ruff format --check`. Run the full Phase 2 test suite. Green.

## TDD plan — red / green / refactor

### Red — failing shape tests first

For `monorepo-pnpm`, the shape test mirrors S7-01:

```python
# tests/unit/test_fixture_monorepo_pnpm_shape.py (excerpt)
_FILE_SPECS: tuple[_FileSpec, ...] = (
    _FileSpec("pnpm-workspace.yaml", ("node_build_system", "dep_graph"), "safe_yaml", (_workspace_declares_packages,)),
    _FileSpec("package.json", ("node_build_system", "node_manifest"), "safe_json", (_root_pkg_shape,)),
    _FileSpec("packages/lib-a/package.json", ("node_manifest", "dep_graph"), "safe_json", (_lib_a_pkg_shape,)),
    _FileSpec("packages/lib-a/src/index.ts", ("language_detection", "tree_sitter_import_graph"), "text", (_lib_a_exports_add,)),
    _FileSpec("packages/lib-b/package.json", ("node_manifest", "dep_graph"), "safe_json",
              (_lib_b_pkg_shape, _lib_b_declares_workspace_dep_on_lib_a)),
    _FileSpec("packages/lib-b/src/index.ts", ("language_detection", "tree_sitter_import_graph"),
              "text", (_lib_b_imports_from_lib_a,)),
    _FileSpec("packages/app/package.json", ("node_manifest", "dep_graph"), "safe_json",
              (_app_pkg_shape, _app_declares_workspace_deps_on_both_libs)),
    _FileSpec("packages/app/src/index.ts", ("language_detection", "tree_sitter_import_graph"),
              "text", (_app_imports_from_both_libs,)),
    _FileSpec("pnpm-lock.yaml", ("node_build_system", "node_manifest", "dep_graph"),
              "safe_yaml", (_lock_v6_header,)),
    _FileSpec("tsconfig.json", ("node_build_system",), "jsonc", (_tsconfig_root_references_all_three,)),
    _FileSpec("Dockerfile", ("dockerfile", "runtime_trace", "entrypoint"), "text",
              (_dockerfile_multistage, _dockerfile_uses_node_slim, _dockerfile_runs_as_node_user)),
    _FileSpec(".github/workflows/ci.yml", ("ci",), "safe_yaml", (_ci_runs_recursive_build,)),
    _FileSpec("README.md", (), "text", (_readme_documents_phase3_entry_gate_target,)),
)
```

The load-bearing content predicates for `monorepo-pnpm`:

- `_lib_b_declares_workspace_dep_on_lib_a(pkg)` — asserts `pkg["dependencies"]["@monorepo-pnpm/lib-a"] == "workspace:*"`. Mutation: drop the dep → fails.
- `_lib_b_imports_from_lib_a(raw_bytes)` — asserts `'from "@monorepo-pnpm/lib-a"'` is in the source. Mutation: remove the import → fails.
- `_app_declares_workspace_deps_on_both_libs(pkg)` — asserts both `workspace:*` deps. Mutation: drop either → fails.
- `_app_imports_from_both_libs(raw_bytes)` — asserts both `from "@monorepo-pnpm/lib-a"` AND `from "@monorepo-pnpm/lib-b"`. Mutation: drop either → fails. (This is the load-bearing pair the `tree_sitter_import_graph` golden depends on.)
- `_readme_documents_phase3_entry_gate_target(raw_bytes)` — asserts the literal phrase `"Phase 3 entry-gate target"` appears in `README.md`. The phrase is the Risk-#8 named handoff.

For `stale-scip`:

```python
_FILE_SPECS: tuple[_FileSpec, ...] = (
    _FileSpec("package.json", ("node_build_system", "node_manifest"), "safe_json", (_pkg_declares_typescript,)),
    _FileSpec("tsconfig.json", ("node_build_system",), "jsonc", (_tsconfig_shape,)),
    _FileSpec("src/a.ts", ("language_detection",), "text", (_a_ts_exports,)),
    _FileSpec("src/b.ts", ("language_detection",), "text", (_b_ts_imports_a,)),
    _FileSpec("src/c.ts", ("language_detection",), "text", (_c_ts_imports_b,)),
    _FileSpec("src/d.ts", ("language_detection",), "text", (_d_ts_imports_c,)),
    _FileSpec("src/e.ts", ("language_detection",), "text", (_e_ts_imports_d,)),
    _FileSpec(".codegenie/context/raw/scip-index.scip", ("scip_index", "index_health"), None,
              (_scip_blob_non_empty, _scip_blob_metadata_records_prior_commit,)),
    _FileSpec("last-indexed-commit.txt", ("index_health",), "text",
              (_last_indexed_is_valid_sha, _last_indexed_not_equal_to_current_head,)),
    _FileSpec("regenerate.sh", (), "text",
              (_regen_refuses_current_head, _regen_invokes_only_allowlisted_binaries,)),
    _FileSpec("README.md", (), "text",
              (_readme_documents_structural_assertion, _readme_documents_regen_ritual,)),
)
```

The load-bearing content predicates for `stale-scip`:

- `_last_indexed_not_equal_to_current_head(raw_bytes)` — reads the SHA, runs `git rev-parse HEAD` (subprocess, via `run_allowlisted`), asserts they differ. **This is the Risk-#3 front-line invariant.** Mutation: a contributor regenerates the SCIP against current HEAD and updates `last-indexed-commit.txt` to match → this predicate fails immediately.
- `_regen_refuses_current_head(raw_bytes)` — greps the regen script for the explicit check `if [ "$(git rev-parse HEAD)" == "$(cat last-indexed-commit.txt)" ]; then echo "ERROR..."; exit 1; fi` (or its equivalent). The grep pins the load-bearing guard.
- `_scip_blob_metadata_records_prior_commit(_)` — opens the SCIP blob, reads its `Metadata.toolInfo` and `Document.relativePath` records; asserts the SCIP was built against the prior tree (smoke; not a deep equality).
- `_readme_documents_structural_assertion(raw_bytes)` — asserts the README contains both `"CommitsBehind.n >= 1"` AND `"last_indexed != current_HEAD"` phrases verbatim. The README is the **front-line** documentation guard.

### Green — make it pass

Plant the trees. Run the shape tests. Green. Then extract the kernel.

### Mutation-resistance witness table

| Mutation | Test that catches it |
|---|---|
| Drop `"@monorepo-pnpm/lib-a": "workspace:*"` from `lib-b/package.json` | `test_fixture_monorepo_pnpm_content_invariants[packages/lib-b/package.json]` via `_lib_b_declares_workspace_dep_on_lib_a` |
| Remove the `import` from `app/src/index.ts` (silently breaks the `tree_sitter_import_graph` golden) | `_app_imports_from_both_libs` |
| Contributor regenerates `stale-scip` SCIP against current HEAD + updates `last-indexed-commit.txt` to match | `_last_indexed_not_equal_to_current_head` + `tests/adv/phase02/test_stale_scip_fixture.py` (from S4-02) BOTH fail |
| Contributor "fixes" `regenerate.sh` to allow regen against current HEAD | `_regen_refuses_current_head` grep predicate fails |
| Stray `node_modules/` committed to `monorepo-pnpm` | `test_no_forbidden_subpaths[node_modules]` (kernel-provided) |
| Stray `.codegenie/cache/blobs/x` committed under any portfolio fixture | `tests/unit/test_no_committed_codegenie_cache_under_portfolio_fixtures.py` (S7-01) |
| `stale-scip/.gitignore` over-broadens to `.codegenie/` (silently un-allowlists the SCIP blob) | `test_fixture_stale_scip_tree_is_closed_set` (the SCIP becomes missing) |
| README drops the "Phase 3 entry-gate target" phrase from `monorepo-pnpm/README.md` | `_readme_documents_phase3_entry_gate_target` |
| README drops the structural-assertion phrasing from `stale-scip/README.md` | `_readme_documents_structural_assertion` |
| Kernel extraction silently changes behavior (e.g., `enumerate_tracked` excludes a different default) | Phase 1's `test_fixture_node_typescript_helm_shape.py` regression (still passing is the proof) |

### Refactor — clean up

- The kernel extraction is the refactor. The pre-existing five shape tests + Phase 1's `node_typescript_helm` shape test all migrate to consume the kernel; the kernel itself is mypy-strict, no `Any` outside `payload: Any`, no untyped helpers.
- `_ProbeName` in the kernel is the **Phase-1 + Phase-2 closed set** (33 entries). A test in the kernel module (`tests/unit/test_shape_test_kernel.py`) asserts the closed set equals the documented one.
- `regenerate.sh` byte-identical-twice for `monorepo-pnpm` is the same Phase-1 Step-6 discipline; the PR description records the local check result. For `stale-scip`, the check is restricted (re-running `regenerate.sh --from-commit <same-SHA>` twice) because `scip-typescript` itself is deterministic for the same input.
- Update `tests/unit/test_no_committed_codegenie_cache_under_portfolio_fixtures.py` to allowlist `stale-scip/.codegenie/context/raw/scip-index.scip` as the single fixture-side `.codegenie/` exception. **No other exception** without an explicit story-level review.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/portfolio/monorepo-pnpm/` (tree per AC-2..AC-14) | pnpm workspace; `DepGraphProbe` cross-package edges; Phase-3 entry-gate target |
| `tests/fixtures/portfolio/stale-scip/` (full materialization replacing the S4-02 stub) | **Load-bearing.** The roadmap exit-criterion fixture |
| `tests/fixtures/portfolio/_shape_test_kernel.py` | Shared `_FileSpec` + parametrized-test factories (Rule of Three conclusively past) |
| `tests/unit/test_fixture_monorepo_pnpm_shape.py` | Shape test |
| `tests/unit/test_fixture_stale_scip_shape.py` | Shape test (regen-script grep predicate + `last_indexed` SHA invariant) |
| `tests/unit/test_fixture_minimal_ts_shape.py` (migrate to kernel) | Was direct-pattern in S7-01; now consumes kernel |
| `tests/unit/test_fixture_native_modules_shape.py` (migrate to kernel) | Same |
| `tests/unit/test_fixture_distroless_target_shape.py` (migrate to kernel) | Same |
| `tests/unit/test_fixture_node_typescript_helm_shape.py` (Phase 1; migrate to kernel) | Phase-1 fixture consumes the kernel — the sixth consumer demonstrates the kernel pays off |
| `tests/unit/test_no_committed_codegenie_cache_under_portfolio_fixtures.py` (update for `stale-scip` exception) | Allowlist the single `.codegenie/context/raw/scip-index.scip` |
| `tests/unit/test_shape_test_kernel.py` | Asserts the kernel's `_ProbeName` Literal closed set equals the Phase-1 + Phase-2 set |

## Out of scope

- **Golden file regeneration + ~70 goldens** — S7-03.
- **Adversarial corpus** (`hostile_skills_yaml`, `concurrent_gather_race`, `no_inmemory_secret_leak`, `phase3_handoff_smoke`) — S7-04.
- **Property tests + portfolio sweep integration** — S7-05.
- **CI wiring** (`portfolio` job, `adv-phase02` job) — S8-03.
- **`stale-scip` adversarial test itself** (`tests/adv/phase02/test_stale_scip_fixture.py`) — already lives in S4-02; this story only ensures it passes against the full materialization (AC-32 + AC-33), does not edit it.
- **Pre-built `monorepo-pnpm/node_modules/` cache for CI speedup** — explicitly out. The regen-each-run policy is what Phase 2 ships; the escape valve lives in `final-design.md §"Open questions"` #6 and triggers only on hosted-runner bench failure.

## Notes for the implementer

- **Risk #3 is the load-bearing risk this story defends.** If a future contributor regenerates the `stale-scip` SCIP against current HEAD, the load-bearing exit criterion silently stops exercising staleness. **Three layers of defense, all in this story:**
  1. `regenerate.sh` refuses to run against current HEAD (AC-20).
  2. `last-indexed-commit.txt` records the prior SHA; the shape test asserts it differs from `git rev-parse HEAD` (AC-19 + content predicate `_last_indexed_not_equal_to_current_head`).
  3. The S4-02 adversarial asserts both `n >= 1` AND `last_indexed != current_HEAD` (already coded; this story's job is making it non-trivially true).

  Document all three layers in `stale-scip/README.md` so a future contributor knows the chain. Test the regen-script refusal **before** opening the PR.

- **`monorepo-pnpm`'s `pnpm-lock.yaml` byte-stability matters for golden determinism.** Pin the lockfile bytes at fixture creation: run `pnpm install` once in a scratch directory matching the manifest exactly, copy the lockfile in, commit it, and **never re-run `pnpm install` in `regenerate.sh`** (regen is `pnpm install --frozen-lockfile` only — a verify step, not a regenerate step). If the public registry repushes any of `monorepo-pnpm`'s deps, the regen step would observe a mismatch and fail loudly — which is the correct behavior; the fix is then to re-pin the lockfile in a deliberate fixture-update PR.

- **The kernel extraction in this story has been deferred from S7-01 deliberately.** S7-01 had three consumers (Rule of Three boundary, not past); this story brings the count to five new + one Phase-1 = six. Six is conclusively past the rule. The kernel is the natural landing point — extract once, migrate all six consumers in one PR, observe Phase-1 regressions stay green (AC-25 + AC-36).

- **`stale-scip` `.gitignore` allowlist syntax.** The four-line block to allowlist exactly one path under `.codegenie/`:
  ```
  .codegenie/
  !.codegenie/context/
  !.codegenie/context/raw/
  !.codegenie/context/raw/scip-index.scip
  ```
  Each negation un-ignores its target directory; only the final negation un-ignores the file itself. `git check-ignore -v` (a developer-side debug command) confirms the path is tracked. Run it during fixture authoring; record the result in PR description.

- **Why no `node_modules/` under `monorepo-pnpm/`.** Phase 2's `node_build_system` probe (Phase 1) reads `pnpm-lock.yaml`; it does NOT read `node_modules/`. Committing `node_modules/` would bloat the fixture by an order of magnitude AND introduce non-determinism (transitive-dep version-resolution drift). The probes that need the resolved tree (Phase 3+ adapters) reach through their adapters, not through the file system.

- **`scip-typescript` version pin matters for `stale-scip`'s SCIP blob bytes.** Pin the tool version used to build the fixture SCIP (record in `stale-scip/README.md`). When the production tool version updates (S4-03 records the `scip-typescript` version pin), the fixture SCIP may need a deliberate regen. The structural assertion (`CommitsBehind.n >= 1`) survives tool-version drift; the SCIP blob bytes do not.

- **Phase-3 handoff note (Risk #8).** `monorepo-pnpm/README.md` explicitly names this as the Phase-3 entry-gate target. When Phase 3's author lands the first `DepGraphAdapter` implementation, they will smoke against this fixture's `dep_graph` slice. Any Protocol drift between Phase 2's `Protocol` shape and Phase 3's first implementation surfaces here (in addition to S7-04's `test_phase3_handoff_smoke.py` skip-and-unskip ritual).

### Patterns DELIBERATELY deferred

- **Pre-built fixture caches under `tests/fixtures/portfolio/_cache/`** — out of scope; regen-each-run policy is what Phase 2 ships.
- **A YAML-based `MANIFEST.yaml` SSoT inside each fixture** — Python-as-SSoT continues to work; lift only if a fourth consumer of the manifest appears (e.g., a build-system probe needing it at runtime).
- **A second SCIP indexer (e.g., `scip-go`) for the `stale-scip` fixture** — out; Phase 2 fixtures are TypeScript-only. Phase 6+ may introduce a polyglot variant.
- **A `git` history visualization committed alongside the fixture** — out; the README's prose is enough.
