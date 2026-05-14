# Fixture — `node_yarn_berry_nonpnp`

Yarn **Berry** (3.x) repo using `nodeLinker: node-modules` (no PnP). The
**manager** is Berry; the **resolution model** is Classic-style.

The plugin scope (production ADR-0031) is keyed on the *manager*, not the
resolution model — so this is `yarn-berry`, not `yarn-classic`. The
`node_yarn_berry_nonpnp` fixture exists explicitly to lock that decision
into a test.

**Distinguishing signals:**

- `package.json#packageManager: "yarn@3.6.4"` — priority-1 (Berry, major ≥ 2).
- `.yarnrc.yml` with `nodeLinker: node-modules` (Berry config; no PnP).
- `yarn.lock` with Berry YAML header.
- **No** `.pnp.cjs` / `.pnp.loader.mjs` / `.yarn/` directory.

**Expected probe output (S2-02a):**

- `build_system.package_manager == "yarn-berry"`
- No `node_build_system.yarn_variant_inferred` warning.
