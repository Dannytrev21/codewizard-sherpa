# Story S5-04 — Fixtures `node_monorepo_turbo` + `non_node_go`

**Step:** Step 5 — Adversarial corpus + integration end-to-end + fixture portfolio
**Status:** Done — 2026-05-15 (attempt 1; see `_attempts/S5-04.md`)
**Effort:** S
**Depends on:** S2-04, S3-06, S4-03
**ADRs honored:** ADR-0010 (Layer A slices optional at envelope), ADR-0004 (per-probe sub-schema `additionalProperties: false`), ADR-0007 (warning ID pattern — fixture content must not silently produce warnings that violate it)

## Validation notes (2026-05-15 — phase-story-validator)

This story is the **third** consumer of the typed-fixture-manifest precedent first established by S2-03 (`node_typescript_helm`) — Rule of three is met. Both new fixtures get a `_FILE_SPECS: tuple[_FileSpec, ...]` closed-set typed manifest under `tests/unit/`, mirroring the S2-03 pattern (`tests/unit/test_fixture_node_typescript_helm_shape.py`). Adding a fixture file = one NamedTuple-entry insertion, zero edits to the parametrized test bodies (Open/Closed at the file boundary, "Extension by addition" load-bearing commitment).

Key corrections versus the first-draft story:

- **Slice-filter accuracy.** The first draft said "Phase 1's five Node-only probes are filtered out by `Registry.for_task`." Source-of-truth code (`src/codegenie/probes/{ci,deployment}.py`) shows `ci` and `deployment` declare `applies_to_languages = ["*"]` — they run on every repo, including Go-only. Only three Phase 1 probes (`node_build_system`, `node_manifest`, `test_inventory`) are Node-filtered. The `non_node_go` fixture's README and ACs now reflect the actual observable: `node_build_system`, `node_manifest`, `test_inventory` keys are **absent**; `ci`, `deployment` slices **may be present** with empty contents (still ADR-0010 compliant — sub-schemas declare slices optional at envelope's `probes.*` level).
- **Closed-set complement.** First draft used a `find` command in Refactor as the "no Node files in `non_node_go`" check — operator-run, not regression-protected. Replaced with parametrized `test_no_forbidden_subpaths` + a closed-set walk test (`test_fixture_tree_is_closed_set`).
- **Multi-marker monorepo invariant.** First draft buried "use **two** markers" in Notes-for-implementer. Lifted to AC-MR-3 — both `turbo.json` AND `package.json#workspaces` must be present; running `LanguageDetectionProbe._detect_monorepo` over the fixture must yield `tool == "turbo"` (first hit) and `markers == ["package.json", "turbo.json"]` (sorted union). This pins the precedence-chain code path the fixture exists to exercise.
- **Parseability invariants.** Every JSON / YAML / JSONC file in either fixture must round-trip through `parsers.safe_json` / `parsers.safe_yaml`. A malformed minimal pnpm lockfile would pass first-draft existence ACs and fail opaquely in S2-04 / S5-05. Same parseability-AC discipline the S2-03 hardening introduced.
- **README cross-reference test.** Every relpath and every consumer name listed in `_FILE_SPECS` must appear literally in the fixture's `README.md`. Catches drift between the README breadcrumb and the actual fixture tree (Notes-for-implementer says "the breadcrumb a future contributor follows when they accidentally break the fixture"; now it's test-enforced).
- **Design-pattern lifts** (per primary user focus): typed `_FixtureName` / `_ProbeName` / `_ParserKind` `Literal` closed sets (make illegal states unrepresentable); `_FILE_SPECS` SSoT shared by shape test, README cross-reference test, and (Phase-2) future golden regen script; same Open/Closed-at-file-boundary precedent S2-01's `_MONOREPO_PRECEDENCE` and S2-02's `_LOCKFILE_PRECEDENCE` set in production code.

Validation report: [`_validation/S5-04-fixtures-monorepo-non-node.md`](_validation/S5-04-fixtures-monorepo-non-node.md).

## Context

Phase 1 ships five new fixture trees under `tests/fixtures/` (`phase-arch-design.md §"Fixture portfolio"`). Three landed in earlier steps:

- `node_typescript_helm/` (S2-03) — the canonical Node + TypeScript + pnpm + Helm fixture; the golden-file anchor.
- `node_pnpm_native/` (S3-06) — pnpm + `bcrypt` + `sharp`; exercises native-module catalog hits.
- `node_yarn_legacy/` (S3-06) — yarn classic + `yarn.lock`; exercises both `pyarn` and hand-rolled paths.

This story lands the remaining two fixtures:

- `node_monorepo_turbo/` — `turbo.json` + `package.json#workspaces`. Exercises `LanguageDetectionProbe`'s monorepo block (S2-01) on a real-shaped turbo workspace. The S5-05 integration test (`test_monorepo_turbo.py`) reads this fixture.
- `non_node_go/` — Go-only repo (no `package.json`, no Node manifests). Exercises ADR-0010: a non-Node repo flowing through Phase 1 must produce a valid envelope with only `language_stack` populated (the five Node-only probes filter out via `applies_to_languages`). The S5-05 integration test (`test_non_node_repo.py`) reads this fixture.

These fixtures are pure data — no Python code, no production touch. The story is small (S effort) because the structural surface is "files on disk in a documented shape." But the **shape** matters: each fixture's `README.md` documents what scenario it exercises so Phase 2 contributors don't accidentally edit them into something else.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Fixture portfolio"` — the five-fixture inventory.
  - `../phase-arch-design.md §"Component design" #1 (LanguageDetectionProbe extension)` — monorepo marker detection (`pnpm-workspace.yaml`, `lerna.json`, `nx.json`, `turbo.json`, `package.json#workspaces`).
  - `../phase-arch-design.md §"Edge cases"` row 11 — non-Node repo behavior.
  - `../phase-arch-design.md §"Scenarios"` Scenario 4 (non-Node) — the runtime path `non_node_go` exercises.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0010-layer-a-slices-optional-at-envelope.md` — non-Node repos must validate with only `language_stack`. The `non_node_go` fixture is the input that proves it.
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — each sub-schema's strictness is preserved; the fixtures don't introduce extra fields.
- **Source design:**
  - `../final-design.md §"Test plan"` → "Integration tests" — `test_non_node_repo.py` and `test_monorepo_turbo.py` are the two consumers.
  - `../High-level-impl.md §"Step 5"` — fixture portfolio bullet.
- **Existing fixtures (reference patterns):**
  - `tests/fixtures/node_typescript_helm/` (S2-03) — the canonical Node fixture shape and `README.md` style.
  - `tests/fixtures/node_pnpm_native/` and `tests/fixtures/node_yarn_legacy/` (S3-06) — the Node fixture shape for the manifest-probe tests.
- **Style reference:** S2-03's `README.md` (one-paragraph fixture rationale).

## Goal

`tests/fixtures/node_monorepo_turbo/` and `tests/fixtures/non_node_go/` exist on disk, each with a `README.md` explaining what scenario the fixture exercises and how it composes with the S5-05 integration test that consumes it. Running `codegenie gather` against each fixture produces output that the S5-05 integration tests will assert against — but those assertions land in S5-05, not here.

## Acceptance criteria

Each AC is **individually verifiable** (a third party can run a check and get binary pass/fail). ACs prefixed `MR-` apply to `node_monorepo_turbo/`; ACs prefixed `NN-` apply to `non_node_go/`; ACs prefixed `SHARED-` apply to both.

### `tests/fixtures/node_monorepo_turbo/`

- [x] **AC-MR-1 — Closed-set file tree.** The fixture's path set equals `{spec.relpath for spec in _FILE_SPECS_MONOREPO_TURBO}` exactly. No stray files, no missing files. Enforced by `test_fixture_tree_is_closed_set[node_monorepo_turbo]` walking the tree and comparing against the typed manifest. The closed set is:
  - `package.json`
  - `turbo.json`
  - `packages/app-web/package.json`
  - `packages/app-api/package.json`
  - `pnpm-lock.yaml`
  - `README.md`
- [x] **AC-MR-2 — `package.json` shape (root).** Parses via `parsers.safe_json.load`; `name == "monorepo-root"`; `private is True`; `workspaces == ["packages/*"]`; `packageManager` key is **absent** (mirrors S2-03 silent-agree-by-absence convention; otherwise S2-02's `package_manager.declaration_lockfile_disagree` path fires and dirties downstream signals).
- [x] **AC-MR-3 — Multi-marker invariant (THE reason this fixture exists).** Running `LanguageDetectionProbe._detect_monorepo(repo_root, parsed_pkg_json)` over the fixture yields `tool == "turbo"` AND `markers == ["package.json", "turbo.json"]` (sorted union of hits). Asserts BOTH precedence-chain markers are detected — not a single-marker happy path. Pinned by `test_monorepo_two_markers_detected`.
- [x] **AC-MR-4 — `turbo.json` shape.** Parses via `parsers.safe_json.load`. Minimum keys: `$schema` (a string starting with `https://turbo.build/`) AND at least one of `pipeline` (turbo ≤ 1.x) or `tasks` (turbo ≥ 2.x). Implementer picks the current shape; the test allows either via `_turbo_json_minimum_shape` predicate (forward-compatible).
- [x] **AC-MR-5 — Workspace members parse cleanly.** `packages/app-web/package.json` and `packages/app-api/package.json` each parse via `parsers.safe_json.load`; each has `name == "@scope/app-web"` / `name == "@scope/app-api"` respectively; each has a `version` field; each has a `dependencies` field (may be `{}`). Workspace-member traversal is Phase 2; Phase 1 reads only the root.
- [x] **AC-MR-6 — Lockfile shape pins build-system signal.** `pnpm-lock.yaml` parses via `parsers.safe_yaml.load`; `lockfileVersion == "6.0"` (S2-03 precedent — pnpm v8+ emits this version; consistent across the Phase 1 pnpm fixture set). The chosen lockfile is `pnpm-lock.yaml` (not `package-lock.json`) because turbo + pnpm is the most common combo and exercises `NodeBuildSystemProbe`'s lockfile-precedence chain.
- [x] **AC-MR-7 — README content fidelity.** README is ≤ 30 lines, references `phase-arch-design.md §"Fixture portfolio"`, names the consuming integration test `test_monorepo_turbo.py` (S5-05), and names every consumer probe listed in `_FILE_SPECS_MONOREPO_TURBO[i].consumers` literally. Enforced by `test_readme_references_every_spec[node_monorepo_turbo]`.
- [x] **AC-MR-8 — Smoke check.** Running `codegenie gather tests/fixtures/node_monorepo_turbo/` exits 0 and produces a `repo-context.yaml` whose `probes.language_stack.monorepo.tool == "turbo"` and whose `probes.language_stack.monorepo.markers` is a non-empty list containing both `"package.json"` and `"turbo.json"`. The structural per-slice assertions land in S5-05.

### `tests/fixtures/non_node_go/`

- [x] **AC-NN-1 — Closed-set file tree.** The fixture's path set equals `{spec.relpath for spec in _FILE_SPECS_NON_NODE_GO}` exactly. The closed set is:
  - `go.mod`
  - `main.go`
  - `internal/handler.go`
  - `README.md`
- [x] **AC-NN-2 — Forbidden subpaths absent (ADR-0010 contract guardrail).** Parametrized `test_no_forbidden_subpaths[non_node_go]` over `{"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "tsconfig.json", "tsconfig.base.json", ".nvmrc", "node_modules", ".codegenie", "dist", "coverage", ".DS_Store", ".idea", ".vscode"}` — every entry MUST be absent recursively under the fixture root. This is the load-bearing contract test for ADR-0010: adding ANY Node marker would break the "non-Node repo gathers cleanly" invariant.
- [x] **AC-NN-3 — `go.mod` exact content.** `go.mod` contains exactly the bytes (LF line endings, final newline): `b"module example.com/non-node-fixture\n\ngo 1.22\n"`. Enforced by `_go_mod_exact_bytes` predicate. No `go.sum` because `go.mod` declares no dependencies (Notes for implementer: a `go.sum` with a fake hash would look real but won't change probe behavior — skip it).
- [x] **AC-NN-4 — Two `.go` files, both valid `package` declarations.** `main.go` starts with `package main` on its first non-empty line and contains a `func main()` body; `internal/handler.go` starts with `package internal` on its first non-empty line. (Probes do not parse Go; this AC defends a future contributor running `go build` for sanity checking.)
- [x] **AC-NN-5 — `language_detection` primary slice.** Smoke check: `codegenie gather tests/fixtures/non_node_go/` exits 0; the resulting `probes.language_stack.primary == "go"`; `probes.language_stack.counts["go"] >= 2` (two `.go` files); `probes.language_stack.monorepo is None` (no monorepo markers).
- [x] **AC-NN-6 — Node-only slice keys ABSENT in envelope (not `null`).** Same smoke check: `repo-context.yaml`'s `probes` mapping does NOT contain the keys `node_build_system`, `node_manifest`, `test_inventory`. These are filtered out by `Registry.for_task` against `applies_to_languages = ["javascript", "typescript"]`. Per ADR-0010, absence is the contract — not `null`-valued presence. The shape test asserts `"node_build_system" not in yaml_doc["probes"]` etc.
- [x] **AC-NN-7 — `ci` / `deployment` slices MAY be present with empty contents.** `ci` and `deployment` declare `applies_to_languages = ["*"]` — they run on every repo, including this Go-only one. The AC permits (does not require) `probes.ci` and `probes.deployment` to be present with empty / null inner slices. **Required wording in README:** "CI and Deployment probes (`applies_to_languages = ['*']`) run on this fixture and may produce empty slices — only `node_build_system`, `node_manifest`, `test_inventory` are filtered out."
- [x] **AC-NN-8 — README content fidelity.** README is ≤ 30 lines, references both `phase-arch-design.md §"Fixture portfolio"` AND `ADRs/0010-layer-a-slices-optional-at-envelope.md`, names the consuming integration test `test_non_node_repo.py` (S5-05), and explicitly states "only three Phase 1 probes are filtered out" (NOT "five" — that was a first-draft inconsistency). Enforced by `test_readme_references_every_spec[non_node_go]` (relpath + consumer presence) plus a literal-string check for "ADR-0010" and "three".

### `tests/fixtures/` (top-level inventory file)

- [x] **AC-SHARED-1 — Inventory README.** `tests/fixtures/README.md` exists (creating it if absent — Phase 0 did not) and contains a table with at least one row per fixture under `tests/fixtures/`, including the two new ones. Each row has columns `{fixture, exercises, consumed-by, ADR-anchor}`. Both new rows reference `phase-arch-design.md §"Fixture portfolio"`.

### Parametrized shape tests under `tests/unit/`

- [x] **AC-SHARED-2 — Typed `_FILE_SPECS` manifest (Open/Closed at the file boundary).** Each new fixture has a typed manifest constant. `tests/unit/test_fixture_node_monorepo_turbo_shape.py` defines `_FILE_SPECS_MONOREPO_TURBO: tuple[_FileSpec, ...]`; `tests/unit/test_fixture_non_node_go_shape.py` defines `_FILE_SPECS_NON_NODE_GO: tuple[_FileSpec, ...]`. Both use the same `_FileSpec` NamedTuple shape S2-03 established `(relpath: str, consumers: tuple[_ProbeName, ...], parser: _ParserKind | None, content_checks: tuple[Callable[[Any], None], ...])`. Adding a fixture file = one tuple entry insertion, zero edits to parametrized test bodies.
- [x] **AC-SHARED-3 — `Literal` closed sets prevent typo'd consumers.** Both shape tests import (or locally re-declare with the identical members) the `_ProbeName = Literal["language_detection", "node_build_system", "node_manifest", "ci", "deployment", "test_inventory"]` and `_ParserKind = Literal["safe_json", "safe_yaml", "jsonc", "text"]` aliases from `test_fixture_node_typescript_helm_shape.py` (S2-03 precedent). A typo like `"deployments"` (plural) fails at `mypy --strict` AND at the contract test `test_probe_name_literal_matches_phase_1_closed_set`.
- [x] **AC-SHARED-4 — Parseability + content_checks parametrized tests.** Both shape tests run the same battery of parametrized tests S2-03 established:
  - `test_fixture_file_exists[<relpath>]` — file presence.
  - `test_fixture_file_parses[<relpath>]` — invokes `spec.parser` if non-None and asserts no exception.
  - `test_fixture_file_content_checks[<relpath>]` — invokes each `spec.content_checks` predicate.
  - `test_fixture_tree_is_closed_set` — walks the tree and asserts the path set equals `{spec.relpath for spec in _FILE_SPECS}`.
  - `test_readme_references_every_spec` — every `spec.relpath` and every consumer name appears literally in `README.md`.
  - `test_no_forbidden_subpaths` — fixture-specific forbidden-subpath list is absent recursively.
  - `test_fixture_file_line_endings` — every text file uses LF line endings + final newline.
- [x] **AC-SHARED-5 — `mypy --strict` clean.** Both new shape-test modules pass `mypy --strict` with no `# type: ignore` annotations. `_FileSpec` is a `NamedTuple` (typed at construction); every content-check predicate is fully typed.
- [x] **AC-SHARED-6 — Determinism.** Each fixture is hand-authored deterministic content: no timestamps, no machine-specific absolute paths, LF line endings, final newline. No hostile bytes, no real secrets, no content from outside the repo's scope. (Note: ADR-0007's warning-ID pattern is not directly involved — these fixtures should not produce warnings.)
- [x] **AC-SHARED-7 — Both fixtures are committed to git.** No `.gitignore` exclusion for either path; `git ls-files tests/fixtures/node_monorepo_turbo/` and `git ls-files tests/fixtures/non_node_go/` both return the closed-set file list.

## Implementation outline

1. **`tests/fixtures/node_monorepo_turbo/`** — author the directory tree by hand. Use the latest turbo schema URL at land-time (consult `turbo.build/schema.json` to confirm the current shape). Keep the fixture small: two workspace members, ~30 LOC total across `package.json` files. The lockfile can be minimal — generate it with `pnpm install --lockfile-only` once locally, then commit; or hand-author the smallest valid pnpm lockfile if `pnpm` isn't available at fixture-creation time (the parser tolerates a near-empty lockfile).
2. **`tests/fixtures/non_node_go/`** — author the directory tree by hand. `go.mod` + `main.go` + one `internal/*.go` file is enough. The fixture is not built or run; only the language-detection walker reads it. Make sure the `.go` files have valid Go syntax (the walker doesn't parse them, but a future contributor running `go build` to sanity-check shouldn't hit a parse error).
3. **Author each fixture's `README.md`** in the documented shape:
   ```markdown
   # Fixture: node_monorepo_turbo

   **Exercises:** `LanguageDetectionProbe.monorepo` (S2-01) + `NodeBuildSystemProbe` (S2-02).
   **Consumed by:** `tests/integration/probes/test_monorepo_turbo.py` (S5-05).
   **Phase 1 design ref:** `docs/phases/01-context-gather-layer-a-node/phase-arch-design.md §"Fixture portfolio"`.

   This fixture is a minimal turbo-monorepo: a root `package.json` declaring
   `workspaces: ["packages/*"]`, a `turbo.json`, and two workspace members
   (`app-web`, `app-api`). The gather should detect monorepo markers and
   populate `language_stack.monorepo`. Workspace-member traversal is a Phase 2
   concern; Phase 1 produces the root-level slice only.
   ```
4. **Update `tests/fixtures/README.md`** to add rows for the two new fixtures. If the file doesn't exist (Phase 0 didn't create it), create it with a minimal table format.
5. **Manual smoke check** locally: `codegenie gather tests/fixtures/non_node_go/` and `tests/fixtures/node_monorepo_turbo/` each exit 0 and produce a non-empty `repo-context.yaml`. Note: this is a sanity check, not a CI gate — the gates are in S5-05.

## TDD plan — red / green / refactor

This story ships **fixture data PLUS two shape-test modules** that mechanically enforce the fixture-content contract. The data-only framing in the first draft was insufficient — S2-03's hardened story proved that fixture content has structural invariants worth pinning at land-time (closed-set complement, parseability, README cross-reference, forbidden subpaths) and we follow that precedent here. Adding the shape tests is the third concrete consumer of the typed-`_FileSpec`-manifest pattern; the kernel is the within-file precedent in `tests/unit/test_fixture_node_typescript_helm_shape.py` from S2-03.

### Red — write the failing tests first

1. **Write `tests/unit/test_fixture_node_monorepo_turbo_shape.py`** (initially failing — fixture does not exist):
   - Define `_FILE_SPECS_MONOREPO_TURBO: tuple[_FileSpec, ...]` per AC-SHARED-2. Use the S2-03 `_FileSpec` NamedTuple shape; for the content predicates, write the pure functions inline (`_pkg_json_root_shape`, `_turbo_json_minimum_shape`, `_workspace_member_shape`, `_pnpm_lock_v6_header`).
   - Add the parametrized batteries from AC-SHARED-4 (`test_fixture_file_exists`, `test_fixture_file_parses`, `test_fixture_file_content_checks`, `test_fixture_tree_is_closed_set`, `test_readme_references_every_spec`, `test_no_forbidden_subpaths`, `test_fixture_file_line_endings`).
   - Add the standalone `test_monorepo_two_markers_detected` (AC-MR-3) calling `LanguageDetectionProbe._detect_monorepo` directly with a parsed `package.json` and asserting `tool == "turbo"`, `markers == ["package.json", "turbo.json"]`.
   - Add `test_probe_name_literal_matches_phase_1_closed_set` (AC-SHARED-3) — assert `get_args(_ProbeName)` equals the Phase 1 closed set.
   - Run: `pytest tests/unit/test_fixture_node_monorepo_turbo_shape.py`. **EVERY test fails** with `FileNotFoundError` or assertion errors. (Red.)
2. **Write `tests/unit/test_fixture_non_node_go_shape.py`** (initially failing):
   - Define `_FILE_SPECS_NON_NODE_GO: tuple[_FileSpec, ...]` per AC-NN-1.
   - Inline predicates: `_go_mod_exact_bytes`, `_main_go_starts_with_package_main`, `_handler_go_starts_with_package_internal`, `_readme_mentions_adr_0010_and_three`.
   - Same parametrized battery from AC-SHARED-4.
   - Add `test_no_forbidden_subpaths` parametrized over the full ADR-0010 forbidden-subpaths set (AC-NN-2) — including every Node marker.
   - Run: **EVERY test fails**. (Red.)

### Green — hand-author the fixtures

3. **`tests/fixtures/node_monorepo_turbo/`** — author the directory tree by hand. Use the latest `turbo.json` schema URL at land-time (consult `turbo.build/schema.json` to confirm the current shape; AC-MR-4's predicate accepts either turbo ≤ 1.x `pipeline` shape or turbo ≥ 2.x `tasks` shape). Keep the fixture small: two workspace members, ~30 LOC total across `package.json` files. Hand-author a minimal `pnpm-lock.yaml` with `lockfileVersion: '6.0'` (S2-03 precedent — do NOT run `pnpm install` against the fixture; that pollutes the dev env with `node_modules/`).
4. **`tests/fixtures/non_node_go/`** — author the directory tree by hand. `go.mod` exact bytes per AC-NN-3; `main.go` and `internal/handler.go` each with a `package` declaration. No `go.sum` (the module declares no dependencies).
5. **Author each fixture's `README.md`** following the precedent from `tests/fixtures/node_typescript_helm/README.md` (S2-03). Required sections:
   - One-paragraph "what this fixture is" pointing at `phase-arch-design.md §"Fixture portfolio"`.
   - "Exercises:" naming each consuming probe verbatim (must match `_FILE_SPECS[i].consumers`).
   - "Consumed by:" naming `test_monorepo_turbo.py` (S5-05) or `test_non_node_repo.py` (S5-05).
   - For `non_node_go/README.md` **specifically**: a clause stating "only three Phase 1 probes (`node_build_system`, `node_manifest`, `test_inventory`) are filtered out; `ci` and `deployment` declare `applies_to_languages = ['*']` and run, producing empty slices per ADR-0010" — and a literal "ADR-0010" reference. AC-NN-8 enforces this.
6. **Update `tests/fixtures/README.md`** per AC-SHARED-1 (create if absent — Phase 0 did not).
7. Run: `pytest tests/unit/test_fixture_node_monorepo_turbo_shape.py tests/unit/test_fixture_non_node_go_shape.py`. **All tests pass.** (Green.)

### Refactor — verify the contract holds end-to-end

8. **Manual smoke check** — confirms AC-MR-8 / AC-NN-5 / AC-NN-6 / AC-NN-7:
   ```bash
   codegenie gather tests/fixtures/non_node_go/ && \
     yq '.probes.language_stack.primary, .probes | has("node_build_system")' .codegenie/context/repo-context.yaml
   # expect: "go" then "false"

   codegenie gather tests/fixtures/node_monorepo_turbo/ && \
     yq '.probes.language_stack.monorepo.tool, .probes.language_stack.monorepo.markers' .codegenie/context/repo-context.yaml
   # expect: "turbo" then ["package.json", "turbo.json"]
   ```
9. **`mypy --strict` on the new shape-test modules** — AC-SHARED-5.
10. **`ruff check tests/unit/test_fixture_*_shape.py` clean.** No `# noqa`.
11. **`git ls-files tests/fixtures/node_monorepo_turbo/ tests/fixtures/non_node_go/`** returns the closed sets (AC-SHARED-7).

### Mutation log — what the hardened suite catches that the first-draft "smoke check" did not

| Mutation | Caught by | First-draft caught? |
|---|---|---|
| Drop `workspaces` from `package.json`; keep `turbo.json` | `test_monorepo_two_markers_detected` (AC-MR-3) — only one marker now | **NO** (smoke check still finds `tool: turbo`) |
| `turbo.json` is `{}` | `_turbo_json_minimum_shape` (AC-MR-4) | **NO** |
| `pnpm-lock.yaml` is empty / malformed YAML | `test_fixture_file_parses[pnpm-lock.yaml]` (AC-MR-6) | **NO** |
| Stray `notes.md` added to either fixture | `test_fixture_tree_is_closed_set` | **NO** |
| `non_node_go/package.json` accidentally added | `test_no_forbidden_subpaths` (AC-NN-2) | NO (Refactor `find` is operator-run, not regression-protected) |
| `non_node_go/.nvmrc` or `tsconfig.json` accidentally added | `test_no_forbidden_subpaths` | **NO** |
| `go.mod` has a trailing space mutation | `_go_mod_exact_bytes` (AC-NN-3) | **NO** |
| README drops the `LanguageDetectionProbe` consumer reference | `test_readme_references_every_spec` (AC-MR-7) | **NO** |
| README still says "five probes filtered out" | `test_non_node_go_readme_mentions_three_not_five` (AC-NN-8) | **NO** |
| CRLF line endings sneak in via Windows editor | `test_fixture_file_line_endings` (AC-SHARED-4) | **NO** |
| Workspace member has no `name` field | `_workspace_member_shape` (AC-MR-5) | **NO** |
| Implementer picks `package-lock.json` instead of `pnpm-lock.yaml` | `test_fixture_tree_is_closed_set` fails on missing `pnpm-lock.yaml` | **NO** |
| Future contributor adds `coverage/` dir under `non_node_go/` | `test_no_forbidden_subpaths[coverage]` | **NO** |

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/node_monorepo_turbo/package.json` | Root `package.json` with workspaces |
| `tests/fixtures/node_monorepo_turbo/turbo.json` | Turbo schema marker |
| `tests/fixtures/node_monorepo_turbo/packages/app-web/package.json` | Workspace member |
| `tests/fixtures/node_monorepo_turbo/packages/app-api/package.json` | Workspace member |
| `tests/fixtures/node_monorepo_turbo/pnpm-lock.yaml` | Minimal `lockfileVersion: '6.0'` lockfile (AC-MR-6) |
| `tests/fixtures/node_monorepo_turbo/README.md` | Fixture rationale + consumer pointer (AC-MR-7) |
| `tests/fixtures/non_node_go/go.mod` | Go module declaration — exact bytes per AC-NN-3 |
| `tests/fixtures/non_node_go/main.go` | Trivial entry point — `package main` + `func main()` |
| `tests/fixtures/non_node_go/internal/handler.go` | Second `.go` file (`package internal`) for non-trivial count |
| `tests/fixtures/non_node_go/README.md` | Fixture rationale + ADR-0010 pointer (AC-NN-8) — must mention "three" not "five" |
| `tests/fixtures/README.md` | Inventory table — create if absent (AC-SHARED-1) |
| **`tests/unit/test_fixture_node_monorepo_turbo_shape.py`** | **NEW.** Typed `_FILE_SPECS_MONOREPO_TURBO` manifest + parametrized AC-SHARED-4 battery + `test_monorepo_two_markers_detected` (AC-MR-3). S2-03 precedent. |
| **`tests/unit/test_fixture_non_node_go_shape.py`** | **NEW.** Typed `_FILE_SPECS_NON_NODE_GO` manifest + parametrized AC-SHARED-4 battery + extended forbidden-subpath set (AC-NN-2). |

## Out of scope

- **Integration tests against these fixtures** — owned by S5-05.
- **Real-world OSS-repo fixtures** (e.g. cloning `expressjs/express`) — `final-design.md §"Integration tests"` notes `test_real_oss_fixture.py` as an option; explicitly deferred to Phase 2 if needed.
- **Multi-language monorepos** (e.g. Node + Python in one repo) — Phase 2's surface; Phase 1 is Layer A Node only.
- **Workspace-member-level probe traversal** (e.g. running `NodeManifestProbe` on each `packages/*/package.json`) — explicit Phase 2 concern (`phase-arch-design.md §"Open questions"`).
- **Generating fixtures from real-world repos** — out of scope; hand-authored deterministic content is the convention.

## Notes for the implementer

### Design patterns / extension-by-addition (primary concern this validation surfaced)

- **Follow the S2-03 precedent literally.** `tests/unit/test_fixture_node_typescript_helm_shape.py` is the kernel for this story's two new shape-test modules. Both new modules use the SAME `_FileSpec: NamedTuple`, the SAME `_ProbeName: Literal[...]`, the SAME `_ParserKind: Literal[...]`, and the SAME parametrized test bodies. Rule 11 (match the codebase's conventions): conform, don't fork.
- **`_FILE_SPECS` as single source of truth (SSoT).** This is the third concrete consumer of the typed-fixture-manifest family (S2-03 was the first; if S3-06 added a `node_pnpm_native` shape test, it would be the second; S5-04 adds two more). The rule-of-three threshold for "lift to a shared kernel" is met — but **not** in this story. Per Rule 2 + Rule 3 (Simplicity First + Surgical Changes), keep the typed `_FileSpec` / `_ProbeName` / `_ParserKind` declarations in each shape-test module for now. Surface the lift opportunity (move to `tests/unit/_fixture_shape_kernel.py`) for the Phase 2 golden-portfolio work — that's the fourth consumer, and that's the right moment. Document the opportunity here so it doesn't get lost.
- **`_FILE_SPECS` is closed-set; adding a fixture file is one tuple-entry insertion.** This is Open/Closed at the file boundary — the same precedent S2-01's `_MONOREPO_PRECEDENCE` and S2-02's `_LOCKFILE_PRECEDENCE` set in production code. The parametrized test bodies never grow.
- **Make illegal states unrepresentable.** `_ProbeName` is a `Literal[...]` closed set — a typo'd consumer like `"deployments"` (plural) fails at `mypy --strict` AND at the runtime contract test (`test_probe_name_literal_matches_phase_1_closed_set`). Do not weaken to `str`.
- **Content-check predicates are pure functions.** Each predicate (`_pkg_json_root_shape`, `_turbo_json_minimum_shape`, etc.) takes one input and asserts, no I/O, no shared state. Functional core / imperative shell — the imperative shell is the parametrized test body that reads the file and dispatches to the parser.
- **No new mutable globals.** `_FILE_SPECS` is a module-level `tuple` (immutable). All `Literal` aliases are `TypeAlias`-declared (Python 3.12+ `type` keyword preferred if the rest of the codebase has migrated).

### Fixture-content discipline

- **The `non_node_go` fixture is the contract test for ADR-0010.** It must be **purely** Go — adding any Node marker (even an empty `package.json`) breaks the test. `test_no_forbidden_subpaths` (AC-NN-2) makes this enforceable at land-time, not operator-discretion.
- **The `node_monorepo_turbo` fixture uses TWO markers deliberately.** `turbo.json` AND `package.json#workspaces` — not a single-marker happy path. AC-MR-3 pins this. Hand-author both; do NOT remove `workspaces` from `package.json`. (S2-01's `_MONOREPO_PRECEDENCE` linear scan must hit both entries; the precedence-chain code path is what the fixture exists to exercise.)
- **The lockfile is `pnpm-lock.yaml` with `lockfileVersion: '6.0'`** (AC-MR-6). Do NOT run `pnpm install` against the fixture — that pollutes the dev env with `node_modules/`. Hand-author the minimal header (S2-03 precedent file: `tests/fixtures/node_typescript_helm/pnpm-lock.yaml`).
- **`go.sum` is omitted.** `go.mod` declares no dependencies (AC-NN-3 pins the exact bytes); a `go.sum` with a fake hash would look real but won't change probe behavior — skip it.
- **The README is the breadcrumb a future contributor follows when they accidentally break the fixture.** `test_readme_references_every_spec` (AC-MR-7, AC-NN-8) now enforces it mechanically.
- **`non_node_go/README.md` must say "three" not "five".** The first-draft story said "five Phase 1 probes filtered out" — source-of-truth code shows only three (`node_build_system`, `node_manifest`, `test_inventory`). `ci` and `deployment` declare `applies_to_languages = ["*"]` and run on every repo. Match the README to the observable. AC-NN-8 enforces.
- **Fixture-tree determinism is implicit.** No build artifacts, no IDE config (`.vscode/`, `.idea/`), no `.DS_Store`. AC-NN-2 enforces this mechanically for `non_node_go/`; the closed-set test (AC-MR-1) enforces it for `node_monorepo_turbo/` (only listed files allowed).

### Cross-references the implementer will need

- `tests/unit/test_fixture_node_typescript_helm_shape.py` — the kernel to copy from (S2-03 hardened).
- `tests/fixtures/node_typescript_helm/README.md` — the README style to mirror.
- `src/codegenie/probes/language_detection.py:164` — `_MONOREPO_PRECEDENCE` (the precedence chain AC-MR-3 exercises).
- `src/codegenie/probes/{ci,deployment}.py` — confirms `applies_to_languages = ["*"]` for those two probes (the source-of-truth for AC-NN-7's wording).
- `src/codegenie/parsers/{safe_json,safe_yaml,jsonc}.py` — the parsers AC-SHARED-4 parameterizes.
- `docs/phases/01-context-gather-layer-a-node/ADRs/0010-layer-a-slices-optional-at-envelope.md` — the ADR `non_node_go/README.md` must cite (AC-NN-8).
- `docs/phases/01-context-gather-layer-a-node/ADRs/0004-per-probe-subschema-additional-properties-false.md` — composing ADR (envelope-strict + slice-strict, slice-optional at `probes.*`).
