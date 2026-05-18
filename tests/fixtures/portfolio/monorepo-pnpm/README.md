# monorepo-pnpm — pnpm workspace with three packages

A Phase-2 portfolio fixture exercising **cross-package edges** via a
real `pnpm` workspace. Three packages plus a root manifest:

- `packages/lib-a/` — leaf library. `packages/lib-a/package.json` +
  `packages/lib-a/src/index.ts` export `add(a, b)`.
- `packages/lib-b/` — depends on `lib-a` via the
  `workspace:*` protocol. `packages/lib-b/package.json` +
  `packages/lib-b/src/index.ts` (imports `add` from `@monorepo-pnpm/lib-a`,
  re-exports `addThree`).
- `packages/app/` — depends on both libs plus `express`.
  `packages/app/package.json` + `packages/app/src/index.ts` (imports
  from `@monorepo-pnpm/lib-a`, `@monorepo-pnpm/lib-b`, and `express`).

Top-level files: `package.json`, `pnpm-workspace.yaml`, `tsconfig.json`,
`pnpm-lock.yaml`, `Dockerfile`, `.github/workflows/ci.yml`,
`.npmrc` (`ignore-scripts=true` defense-in-depth), `.gitignore`,
`regenerate.sh`.

Per-package TypeScript build configs:
`packages/lib-a/tsconfig.json`, `packages/lib-b/tsconfig.json`,
`packages/app/tsconfig.json`. The root `tsconfig.json` carries the TS
project-`references` array; each per-package `tsconfig.json` is
`composite: true`.

## Probe consumers

| Probe | What it reads |
|---|---|
| `language_detection` | `packages/*/src/*.ts` |
| `node_build_system` | `package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml`, `tsconfig.json` |
| `node_manifest` | `package.json`, `packages/*/package.json`, `.npmrc` |
| `dep_graph` | `pnpm-workspace.yaml`, `pnpm-lock.yaml`, `packages/*/package.json` — the load-bearing fixture for cross-package edges |
| `tree_sitter_import_graph` | `packages/lib-b/src/index.ts`, `packages/app/src/index.ts` — `import` adjacency between workspace packages |
| `dockerfile` | `Dockerfile` |
| `runtime_trace` | `Dockerfile` (multi-stage) |
| `entrypoint` | `Dockerfile` |
| `ci` | `.github/workflows/ci.yml` |

## Regeneration policy

`./regenerate.sh` is `mkdir`/coreutils-only. It does NOT invoke
`pnpm install` or any `pnpm` subcommand — `pnpm` is NOT in
`ALLOWED_BINARIES` per ADR-0001. The `pnpm-lock.yaml` is committed
**hand-authored bytes**.

To bump dependency versions: in a scratch directory exactly matching
this fixture's manifest, run `pnpm install --lockfile-only` once on the
contributor's local box; copy the resulting `pnpm-lock.yaml` into the
fixture; commit. The fixture-local `.npmrc` pins
`ignore-scripts=true` so any operator that later runs `pnpm install`
locally does not trigger lifecycle scripts.

The static-check test
`tests/unit/test_fixture_monorepo_pnpm_regenerate_allowlist.py`
asserts the regen script invokes only `ALLOWED_BINARIES ∪ coreutils`
and that `pnpm` does NOT appear in the invoked set.

## Phase 3 entry-gate target

This fixture is the **Phase 3 entry-gate target** for `DepGraphAdapter`.
When the first plugin author lands the Phase-3 `DepGraphAdapter`
implementation, they will smoke against this fixture's `dep_graph`
slice. Any drift between Phase-2's `Protocol` shape and Phase-3's first
implementation surfaces here, in addition to the
`test_phase3_handoff_smoke.py` skip-and-unskip ritual landed by S7-04.

## Why no `node_modules/` committed

Phase-2's `node_build_system` probe (Phase 1) reads `pnpm-lock.yaml`;
it does NOT read `node_modules/`. Committing `node_modules/` would
bloat the fixture by an order of magnitude and introduce
non-determinism (transitive-dep version-resolution drift). The probes
that need the resolved tree (Phase-3+ adapters) reach through their
adapters, not through the file system.
