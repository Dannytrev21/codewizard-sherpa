# Fixture — `node_yarn_legacy`

Yarn **Classic** (1.x) repo shape. Used by S2-02a (yarn variant detection) +
S3-03 (yarn lockfile parser).

**Distinguishing signals:**

- `package.json#packageManager: "yarn@1.22.19"` — priority-1 signal (Corepack-declared, deterministic).
- `yarn.lock` present with Classic header (`# yarn lockfile v1`).
- No `.yarnrc.yml`, no `.yarn/`, no `.pnp.*` — none of the Berry markers.

**Expected probe output (S2-02a):**

- `build_system.package_manager == "yarn-classic"`
- No `node_build_system.yarn_variant_inferred` warning (priority-1 hit).

**Additional consumer (S3-06):** the
`tests/integration/probes/test_node_manifest_yarn_legacy.py`
parity-integration smoke runs `NodeManifestProbe` against this fixture
twice — once with `_yarn._HAS_PYARN` left alone (pyarn arm) and once
with it monkey-patched to `False` (hand-rolled arm) — and asserts both
arms produce byte-identical `manifests` slices via `mocker.spy`-proved
observably-distinct code paths. The fixture's `package.json` and
`yarn.lock` are load-bearing for that test; do not edit them.
