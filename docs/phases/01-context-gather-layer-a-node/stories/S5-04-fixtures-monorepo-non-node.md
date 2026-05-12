# Story S5-04 — Fixtures `node_monorepo_turbo` + `non_node_go`

**Step:** Step 5 — Adversarial corpus + integration end-to-end + fixture portfolio
**Status:** Ready
**Effort:** S
**Depends on:** S2-04, S3-06, S4-03
**ADRs honored:** ADR-0010 (Layer A slices optional at envelope), ADR-0004 (per-probe sub-schema `additionalProperties: false`)

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

- [ ] `tests/fixtures/node_monorepo_turbo/` exists with the following minimum-viable structure:
  - `package.json` with `"workspaces": ["packages/*"]` and a `"name": "monorepo-root"`, `"private": true`.
  - `turbo.json` with a minimal valid turbo schema (`{"$schema": "https://turbo.build/schema.json", "pipeline": {"build": {}}}` or current equivalent — confirm against Turborepo's actual schema at land-time).
  - `packages/app-web/package.json` and `packages/app-api/package.json` — two workspace members, each with `"name": "@scope/app-web"` / `"@scope/app-api"` and a minimal `"dependencies"` block.
  - `pnpm-lock.yaml` (or `package-lock.json`; pick one and document why) at repo root.
  - `README.md` documenting (1) what this fixture is, (2) which probes it exercises (`LanguageDetectionProbe.monorepo`, `NodeBuildSystemProbe`), (3) which integration test consumes it (`test_monorepo_turbo.py` in S5-05), (4) what the test's expected outcome is at a high level.
- [ ] `tests/fixtures/non_node_go/` exists with the following minimum-viable structure:
  - `go.mod` with `module example.com/non-node-fixture` and `go 1.22`.
  - `go.sum` (empty or trivial) — optional; include if `go.mod` references any dependency.
  - `main.go` with a trivial `package main` + `func main()`.
  - `internal/` directory with one `.go` file to make the language detection counts non-trivial.
  - **No** `package.json`, **no** `tsconfig.json`, **no** `pnpm-lock.yaml`, **no** node-related files of any kind.
  - `README.md` documenting (1) this is a Go-only fixture, (2) it asserts ADR-0010 (envelope validates with only `language_stack`), (3) the consuming integration test is `test_non_node_repo.py` in S5-05, (4) Phase 1's five Node-only probes are filtered out by `Registry.for_task` against `applies_to_languages`.
- [ ] Each fixture's `README.md` is under 30 lines and references `phase-arch-design.md §"Fixture portfolio"` for context.
- [ ] Each fixture is checked into git (no `.gitignore` exclusion); the directory is part of the working tree.
- [ ] No fixture contains hostile bytes, real secrets, or content from outside the repo's scope; each is hand-authored deterministic content.
- [ ] `tests/fixtures/README.md` (which already exists if Phase 0 created it; otherwise create it) lists both new fixtures in its table with a one-line description each.
- [ ] Running `codegenie gather tests/fixtures/non_node_go/` exits 0 and produces a `repo-context.yaml` that contains a `language_stack` slice with `primary: "go"` (or whichever Go-key the language map uses) and **does not** contain `build_system`, `manifests`, `test_inventory` slices for Node — these are absent (key not present), not null. This is a smoke check, not a full integration test — that lands in S5-05.
- [ ] Running `codegenie gather tests/fixtures/node_monorepo_turbo/` exits 0 and produces a `repo-context.yaml` whose `language_stack.monorepo` block is populated. Again: smoke check; the structural assertions are in S5-05.

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

This story is data-only (fixture files + README). Standard red/green/refactor doesn't apply cleanly. But the **TDD spirit** holds: the consuming integration tests in S5-05 are the verification. The work here is to make the fixtures real enough that S5-05's assertions can hold.

### Red — what's the failing observable?

Before this story: `tests/integration/probes/test_monorepo_turbo.py` and `test_non_node_repo.py` (which land in S5-05) would fail with `FileNotFoundError` on `tests/fixtures/node_monorepo_turbo/` and `tests/fixtures/non_node_go/`. S5-04 makes those paths real.

A useful local check that this story is done:

```bash
# These should exit 0 and produce non-empty output
codegenie gather tests/fixtures/non_node_go/ && \
  yq '.probes.language_stack.primary' .codegenie/context/repo-context.yaml
# expect: go

codegenie gather tests/fixtures/node_monorepo_turbo/ && \
  yq '.probes.language_stack.monorepo' .codegenie/context/repo-context.yaml
# expect: a non-null block with workspace markers
```

If the second command returns `null`, the fixture's monorepo markers aren't being picked up — verify the fixture has at least one of the markers from S2-01's seed list (`pnpm-workspace.yaml`, `lerna.json`, `nx.json`, `turbo.json`, or `package.json#workspaces`).

### Green — make it real

Author the directory trees and READMEs per the structure in Acceptance Criteria. Commit the directories. Run the local smoke check above.

### Refactor — clean up

After authoring:

- Verify each README links to `phase-arch-design.md §"Fixture portfolio"` and to the consuming S5-05 test path.
- Verify no `.DS_Store` or editor artifacts in the fixture trees (`find tests/fixtures/node_monorepo_turbo/ -name .DS_Store` should be empty).
- Confirm the `non_node_go` fixture really has zero Node-related files: `find tests/fixtures/non_node_go/ -name "package.json" -o -name "*.lock" -o -name "tsconfig*"` should return nothing.
- Verify deterministic content — no timestamps, no machine-specific paths in any file.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/node_monorepo_turbo/package.json` | Root `package.json` with workspaces |
| `tests/fixtures/node_monorepo_turbo/turbo.json` | Turbo schema marker |
| `tests/fixtures/node_monorepo_turbo/packages/app-web/package.json` | Workspace member |
| `tests/fixtures/node_monorepo_turbo/packages/app-api/package.json` | Workspace member |
| `tests/fixtures/node_monorepo_turbo/pnpm-lock.yaml` | Minimal lockfile (or `package-lock.json`) |
| `tests/fixtures/node_monorepo_turbo/README.md` | Fixture rationale + consumer pointer |
| `tests/fixtures/non_node_go/go.mod` | Go module declaration |
| `tests/fixtures/non_node_go/main.go` | Trivial entry point |
| `tests/fixtures/non_node_go/internal/handler.go` | Second `.go` file for non-trivial count |
| `tests/fixtures/non_node_go/README.md` | Fixture rationale + ADR-0010 pointer |
| `tests/fixtures/README.md` | Update inventory table (or create if absent) |

## Out of scope

- **Integration tests against these fixtures** — owned by S5-05.
- **Real-world OSS-repo fixtures** (e.g. cloning `expressjs/express`) — `final-design.md §"Integration tests"` notes `test_real_oss_fixture.py` as an option; explicitly deferred to Phase 2 if needed.
- **Multi-language monorepos** (e.g. Node + Python in one repo) — Phase 2's surface; Phase 1 is Layer A Node only.
- **Workspace-member-level probe traversal** (e.g. running `NodeManifestProbe` on each `packages/*/package.json`) — explicit Phase 2 concern (`phase-arch-design.md §"Open questions"`).
- **Generating fixtures from real-world repos** — out of scope; hand-authored deterministic content is the convention.

## Notes for the implementer

- **The `non_node_go` fixture is a contract test for ADR-0010.** It must be **purely** Go — adding any Node marker (even an empty `package.json`) breaks the test. Sanity-check with the `find` command in the refactor section before opening the PR.
- **The `node_monorepo_turbo` fixture must have at least one canonical monorepo marker.** S2-01's seed list is `{pnpm-workspace.yaml, lerna.json, nx.json, turbo.json, package.json#workspaces}`. The fixture uses **two** (`turbo.json` and `package.json#workspaces`) to verify the probe handles multi-marker repos correctly — not a single-marker happy path. Document this in the README.
- **The lockfile choice (`pnpm-lock.yaml` vs `package-lock.json`) is fixture-defining.** Pick `pnpm-lock.yaml` for `node_monorepo_turbo` since turbo + pnpm is the most common combo in the wild; this also exercises `NodeBuildSystemProbe`'s lockfile-precedence detection (S2-02). Document the choice in the README so a future contributor doesn't switch the lockfile and break the assumption.
- **Don't run `pnpm install` against the fixture to generate a real lockfile** — that would install packages and pollute the dev environment with `node_modules/` (which then needs `.gitignore` discipline). Hand-author a minimal `pnpm-lock.yaml` with the `lockfileVersion: '6.0'` header + an empty packages section. The S2-02 lockfile-precedence check just reads the **presence** of the file, not its contents.
- **`go.sum` is optional.** If `go.mod` lists no dependencies (recommended for the minimal fixture), there is no `go.sum`. Including a `go.sum` with a fake hash will look real but won't change probe behavior — skip it.
- **The README's "Consumed by" line is the breadcrumb a future contributor follows when they accidentally break the fixture.** Don't omit it. The convention used in S2-03 and S3-06 is the precedent.
- **Fixture-tree determinism is implicit.** Don't include build artifacts, IDE config (`.vscode/`, `.idea/`), or anything Git would otherwise consider noise. The fixtures live under `tests/fixtures/` and are checked in verbatim; treat them as canonical content.
