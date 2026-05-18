# `minimal-ts/` fixture

The **smallest happy path** Phase-2 portfolio fixture. Every
language-agnostic Phase-2 probe runs against it without producing a
`confidence="unavailable"` result for spurious reasons. It is the smoke
anchor for the `portfolio` CI job (S8-03) — if any probe regresses, this
fixture's golden diff fails first.

This tree is the smallest-tier consumer of:

- Phase-1 Layer A probes (`language_detection`, `node_build_system`,
  `node_manifest`, `ci`, `deployment`, `test_inventory`).
- Phase-2 Layer B probes (`index_health`, `scip_index`,
  `tree_sitter_import_graph`, `dep_graph`, `generated_code`,
  `node_reflection`, `semantic_index_meta`).
- Phase-2 Layer C probes (`runtime_trace`, `dockerfile`, `entrypoint`,
  `shell_usage`, `certificate`, `sbom`, `cve`).
- Phase-2 Layer D probes (`skills_index`, `conventions`, `adrs`,
  `repo_notes`, `repo_config`, `policy`, `exceptions`, `external_docs`).
- Phase-2 Layer E probes (`ownership`, `service_topology`, `slo`).
- Phase-2 Layer G probes (`semgrep`, `ast_grep`, `ripgrep_curated`,
  `gitleaks`, `test_coverage_mapping`).

> **The fixture's bytes are part of the contract.** Adding or removing
> any file changes one or more goldens. The shape test at
> `tests/unit/test_fixture_minimal_ts_shape.py` enforces the closed set
> mechanically (S7-01 AC-26). See
> [`../../../docs/phases/02-context-gather-layers-b-g/phase-arch-design.md`](../../../docs/phases/02-context-gather-layers-b-g/phase-arch-design.md)
> for canonical slice descriptions each probe emits.

## File-by-file — which probes consume what

| Relpath | Consuming probe(s) | Purpose |
|---|---|---|
| `package.json` | `language_detection`, `node_build_system`, `node_manifest`, `test_inventory` | Declares `express` (seeds `framework_hints`), the `tsc`/`vitest` scripts, `engines.node = ">=20.0.0"`. |
| `pnpm-lock.yaml` | `node_build_system`, `node_manifest`, `dep_graph` | Header-only pnpm v6 lockfile (`lockfileVersion: '6.0'`). Picks `pnpm` via S2-02's lockfile-precedence chain; `dep_graph` consumes the empty `packages: {}` happy path. |
| `tsconfig.json` | `node_build_system` | JSONC with **both** `//` line comments and `/* */` block comments — exercises `codegenie.parsers.jsonc`'s state-machine comment stripper on the warm integration path. |
| `.nvmrc` | `node_build_system` | Pinned Node `v20.11.0` (exact one-line LF-terminated content). Exercises the `engines.node` → `.nvmrc` precedence step. |
| `src/index.ts` | `language_detection` | Trivial Express stub. Bumps the `.ts` extension count to exactly 1. |
| `.github/workflows/ci.yml` | `ci` | One job (`build`), one `run` step. Populates `CIProbe`'s slice. |
| `Dockerfile` | `dockerfile`, `entrypoint`, `shell_usage`, `certificate`, `runtime_trace`, `sbom`, `cve` | Minimal single-stage `node:20-slim` image so Layer C probes produce populated slices without exotic edge cases. |
| `deploy/chart/Chart.yaml` | `deployment` | Modern Helm v2 chart shape. Populates `DeploymentProbe.type == "helm"`. |
| `deploy/chart/values.yaml` | `deployment` | Primary `image_reference` (`ghcr.io/example/minimal-ts:0.0.1`). |
| `deploy/chart/values-prod.yaml` | `deployment` | Multi-environment entry — overrides `image.tag = "prod-0.0.1"`. Exercises the `environments: list[EnvironmentEntry]` path per Phase-1 ADR-0012. |
| `README.md` | — | This file — documents every spec.relpath and every probe consumer (AC-29). |
| `regenerate.sh` | — | Review-as-code (S7-01 AC-22). Idempotent skeleton-verify; no package-manager invocation. |
| `.gitignore` | — | One line (`.codegenie/`). The cache and runtime artifacts are never committed (S7-01 AC-33). |

## Forbidden subpaths

The shape test rejects any of `node_modules/`, `.codegenie/`, `dist/`,
`coverage/`, `build/`, `build/Release/`, `.DS_Store` — would either
dirty the golden, break test isolation, or signal a `node-gyp` rebuild
that should never happen here.

## Maintenance rule

Adding a file requires:

1. Inserting one `_FileSpec` entry into `_FILE_SPECS` in
   `tests/unit/test_fixture_minimal_ts_shape.py`.
2. Adding a row to the table above (AC-29 enforces this — the test
   reads this README and asserts every spec's `relpath` and every
   consumer name appears literally in the prose).

Every byte of every file is justified by exactly one downstream
consumer. Resist the urge to "round out" the fixture — every addition
forces a golden regen.
