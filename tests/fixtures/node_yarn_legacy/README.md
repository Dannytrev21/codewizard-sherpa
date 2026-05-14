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
