# Fixture — `node_yarn_berry_pnp`

Yarn **Berry** (2+) repo in **Plug'n'Play** mode. Used by S2-02a + S3-03.

**Distinguishing signals (any one is sufficient; this fixture has all three):**

- `package.json#packageManager: "yarn@4.5.0"` — priority-1 (Berry, major ≥ 2).
- `.yarnrc.yml` (Berry-only — note the `.yml` extension; Classic uses `.yarnrc`).
- `.pnp.cjs` — Berry PnP resolution graph marker.
- `yarn.lock` with Berry YAML header (`__metadata`, `resolution`).

**Expected probe output (S2-02a):**

- `build_system.package_manager == "yarn-berry"`
- No `node_build_system.yarn_variant_inferred` warning (priority-1 hit).
