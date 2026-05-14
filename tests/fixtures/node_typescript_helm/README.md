# `node_typescript_helm/` fixture

The canonical **Phase-1 fixture**. Its name telegraphs the four dimensions
it exercises: **Node**, **TypeScript**, **pnpm**, **Helm**.

This tree is the single repo-under-test used by:

- `S2-04` — warm-path memo integration (`framework_hints == ["express"]`,
  exactly one memo hit + one memo miss across `language_detection` +
  `node_build_system`).
- `S2-05` — cache-hit-on-real-repo integration test (load-bearing Phase-1
  exit criterion #2).
- `S5-05` — `test_layer_a_end_to_end.py` (load-bearing Phase-1 exit
  criterion #1).
- `S6-01` — golden anchor at `tests/golden/node_typescript_helm.repo-context.yaml`.

> **The fixture's bytes are part of the contract.** Adding or removing any
> file changes the S6-01 golden and forces a regen-script run. The shape
> test at `tests/unit/test_fixture_node_typescript_helm_shape.py` enforces
> the closed set mechanically (AC-14). See
> [`../../docs/phases/01-context-gather-layer-a-node/phase-arch-design.md`](../../../docs/phases/01-context-gather-layer-a-node/phase-arch-design.md)
> for the canonical slice descriptions each probe emits.

## File-by-file — which probes consume what

| Relpath | Consuming probe(s) | Purpose |
|---|---|---|
| `package.json` | `language_detection`, `node_build_system`, `node_manifest`, `test_inventory` | Declares `express` (seeds `framework_hints`), the `tsc`/`vitest` scripts, `engines.node = ">=20.0.0"`. No `packageManager` field — keeps the S2-02 `package_manager.declaration_lockfile_disagree` path silent. |
| `pnpm-lock.yaml` | `node_build_system`, `node_manifest` | Header-only pnpm v6 lockfile (`lockfileVersion: '6.0'`). Picks `pnpm` via the S2-02 lockfile-precedence chain. Content minimal; S3-05's native-module catalog cross-reference uses a different fixture. |
| `tsconfig.json` | `node_build_system` | JSONC with **both** `//` line comments and `/* */` block comments — load-bearing for exercising `codegenie.parsers.jsonc`'s state-machine comment stripper on the warm integration path. |
| `.nvmrc` | `node_build_system` | Pinned Node `v20.11.0` (exact one-line LF-terminated content). Exercises the `engines.node` → `.nvmrc` precedence step. |
| `src/index.ts` | `language_detection` | Trivial Express stub. Bumps the `.ts` extension count to exactly 1. The `import express from "express"` line is pinned by AC-6. |
| `.github/workflows/ci.yml` | `ci` | One job (`build`), one `run` step. Populates `CIProbe`'s slice in S5-05. |
| `deploy/chart/Chart.yaml` | `deployment` | Modern Helm v2 chart shape. Populates `DeploymentProbe.type == "helm"` in S5-05. |
| `deploy/chart/values.yaml` | `deployment` | Primary `image_reference` (`ghcr.io/example/node-typescript-helm:0.0.1`). |
| `deploy/chart/values-prod.yaml` | `deployment` | Multi-environment entry — overrides `image.tag = "prod-0.0.1"`. Exercises the `environments: list[EnvironmentEntry]` path per ADR-0012. |

## Forbidden subpaths

The shape test rejects any of:

- `node_modules/` — would dirty the golden and explode the byte count.
- `.codegenie/` — the integration tests write their own outputs here at
  runtime; a checked-in directory would either collide or get clobbered.
- `.gitignore` — fixtures must be self-contained; `gitignore` semantics
  are tested in dedicated `gitignore` fixtures.
- `dist/` and `coverage/` — build/test artifacts; fixtures must contain
  only sources.

## Maintenance rule

Adding a file requires:

1. Inserting one `_FileSpec` entry into `_FILE_SPECS` in
   `tests/unit/test_fixture_node_typescript_helm_shape.py`.
2. Adding a row to the table above (AC-17 enforces this — the test reads
   this README and asserts every spec's `relpath` and every consumer name
   appears literally in the prose).

Every byte of every file is justified by exactly one downstream consumer.
Resist the urge to "round out" the fixture — every addition forces an
S6-01 golden regen.
