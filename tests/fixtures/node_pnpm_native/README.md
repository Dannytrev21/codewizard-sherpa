# Fixture — `node_pnpm_native`

pnpm-locked repo declaring two seed-catalog native modules (`bcrypt`,
`sharp`) plus one non-native control (`lodash`). Used by S3-06's
end-to-end integration test for `NodeManifestProbe`.

**What this fixture exercises:**

- **Native-module catalog cross-reference** —
  `manifests.primary.native_modules.detected == True` with **both**
  `bcrypt` and `sharp` flagged `requires_node_gyp: true`.
- **Tautology kill (S3-06 AC-3)** — `lodash` is the non-native control:
  if the lockfile is not actually parsed, `lodash` won't appear in
  resolved deps and the test fails. Pinned native-only outputs (a
  probe that hardcoded `{"bcrypt", "sharp"}`) cannot satisfy
  `assert "lodash" in resolved`.
- **Multi-probe end-to-end signal (S3-06 AC-4)** — same gather populates
  `language_detection.primary` and
  `node_build_system.package_manager == "pnpm"`. First end-to-end Phase 1
  evidence on multi-probe gather against a realistic Node repo.
- **Multi-lockfile (Edge case #7, S3-06 AC-5)** — parametrized variant
  drops a stray `yarn.lock` next to `pnpm-lock.yaml`; asserts
  `confidence: low` + `lockfile.multi_present` warning.

**Distinguishing signals:**

- `package.json#packageManager: "pnpm@8.15.4"` — priority-1 build-system signal.
- `pnpm-lock.yaml` (pnpm-format) with `/bcrypt@5.1.1` and `/sharp@0.32.6`
  v9-style package keys (pnpm v8+ emits `lockfileVersion: '6.0'`).
- Specific pinned versions (no caret/tilde ranges) so test assertions
  stay stable across re-installs of the dev environment.

**Expected probe output:**

- `manifests.primary.native_modules.packages` is a superset of
  `[{"name": "bcrypt", "requires_node_gyp": true},
    {"name": "sharp",  "requires_node_gyp": true}]`.
- `manifests.catalog_version == NATIVE_MODULES_CATALOG_VERSION`.
- Clean (no stray lockfile): `confidence: high`, `warnings: []`.
- Stray yarn.lock dropped: `confidence: low`, `warnings`
  contains `lockfile.multi_present`.
