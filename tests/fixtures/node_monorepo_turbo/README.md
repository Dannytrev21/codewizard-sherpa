# `node_monorepo_turbo/` fixture

A minimal **turbo + pnpm monorepo** for Phase 1.

**Exercises:** `LanguageDetectionProbe`'s monorepo block (S2-01) +
`NodeBuildSystemProbe` (S2-02) on a multi-marker turbo workspace.
**Consumed by:** `tests/integration/probes/test_monorepo_turbo.py` (S5-05).
**Phase 1 design ref:**
`docs/phases/01-context-gather-layer-a-node/phase-arch-design.md §"Fixture portfolio"`.

The root declares **both** `turbo.json` AND `package.json#workspaces` so
the precedence-chain walk in `_MONOREPO_PRECEDENCE` (S2-01) hits two
markers — `turbo` wins (`tool == "turbo"`) and `markers` is the sorted
union `["package.json", "turbo.json"]`. The shape test
`tests/unit/test_fixture_node_monorepo_turbo_shape.py` pins that
invariant mechanically (`test_monorepo_two_markers_detected`).

Workspace-member traversal is a Phase 2 concern; Phase 1 reads only the
root `package.json` plus the workspace declaration.

## File-by-file

| Relpath | Consuming probe(s) | Purpose |
|---|---|---|
| `package.json` | `language_detection`, `node_build_system`, `node_manifest` | Root manifest. `name == "monorepo-root"`, `private: true`, `workspaces: ["packages/*"]`. No `packageManager` field — keeps the S2-02 `package_manager.declaration_lockfile_disagree` path silent. |
| `turbo.json` | `language_detection` | Turbo schema marker. Uses turbo v2's `tasks` shape (forward-compatible — `_turbo_json_minimum_shape` predicate accepts either `tasks` or v1's `pipeline`). |
| `packages/app-web/package.json` | — | Workspace member. Read by Phase 2; pinned here for completeness. |
| `packages/app-api/package.json` | — | Second workspace member. |
| `pnpm-lock.yaml` | `node_build_system`, `node_manifest` | Header-only pnpm v6 lockfile (`lockfileVersion: '6.0'`). Picks `pnpm` via the S2-02 lockfile-precedence chain. |
| `README.md` | — | This file. |
