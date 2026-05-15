# `tests/fixtures/` — fixture inventory

Hand-authored deterministic repository fixtures used by Phase-1 unit,
integration, and adversarial tests. Each fixture's tree is **closed-set**
(pinned by a shape test) so a stray file fails before it can dirty a
downstream golden silently.

| Fixture | Exercises | Consumed by | ADR anchor |
|---|---|---|---|
| `empty_repo/` | `LanguageDetectionProbe` zero-files path. | Phase 0 smoke + Layer-A unit tests. | — |
| `js_only/` | JavaScript-only language detection (no TS, no Helm). | `LanguageDetectionProbe` unit tests. | — |
| `polyglot/` | Multi-language ranking (`primary` alpha-sorted-first within max-count set). | `LanguageDetectionProbe` unit tests. | — |
| `node_typescript_helm/` | The **canonical Phase 1 fixture**: Node + TypeScript + pnpm + Helm. Anchors the S6-01 golden. | S2-04, S2-05, S5-05, S6-01. See `phase-arch-design.md §"Fixture portfolio"`. | — |
| `node_pnpm_native/` | pnpm + `bcrypt` + `sharp`; exercises native-module catalog hits. | S3-06 manifest fixture tests. | — |
| `node_yarn_legacy/` | Yarn classic + `yarn.lock`; exercises both `pyarn` and the hand-rolled fallback path. | S3-06 manifest fixture tests. | — |
| `node_yarn_berry_pnp/` | Yarn Berry Plug'n'Play variant. | S2-02a variant-detection tests. | — |
| `node_yarn_berry_nonpnp/` | Yarn Berry non-PnP variant. | S2-02a variant-detection tests. | — |
| `node_monorepo_turbo/` | `turbo.json` + `package.json#workspaces` — multi-marker monorepo invariant (S2-01 `_MONOREPO_PRECEDENCE`). | S5-04 shape test + S5-05 `test_monorepo_turbo.py`. See `docs/phases/01-context-gather-layer-a-node/phase-arch-design.md §"Fixture portfolio"`. | — |
| `non_node_go/` | Non-Node repo flowing through Phase 1 — only `language_stack` populated; the three Node-only probes filtered out. | S5-04 shape test + S5-05 `test_non_node_repo.py`. See `docs/phases/01-context-gather-layer-a-node/phase-arch-design.md §"Fixture portfolio"`. | `ADRs/0010-layer-a-slices-optional-at-envelope.md` |
| `_yarn_corpus/` | Yarn lockfile-parser parity oracle corpus (auto-discovered). | S3-04 oracle tests. | — |

## Conventions

- **LF line endings, final newline.** Shape tests enforce this for every text file.
- **No build artifacts, no IDE config.** `node_modules/`, `dist/`, `coverage/`, `.vscode/`, `.idea/`, `.DS_Store` are forbidden — adding them would either pollute test isolation or dirty the S6-01 golden.
- **Hand-authored deterministic content.** No timestamps, no machine-specific absolute paths, no real secrets.
- **Adding a fixture file is one tuple-entry insertion** in the fixture's shape-test `_FILE_SPECS` constant — never edit the parametrized test bodies. This is Open/Closed at the file boundary.
