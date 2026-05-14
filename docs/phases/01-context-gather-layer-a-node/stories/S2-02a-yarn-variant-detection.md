# S2-02a — Yarn variant detection: split `yarn` into `yarn-classic` and `yarn-berry`

**Status:** Not started
**Estimate:** S (≈1 working day)
**Depends on:** S2-02 (GREEN — the existing NodeBuildSystemProbe)
**Blocks:** S3-03 (yarn lockfile parser — needs to know which variant to choose), plus any Phase 8 plugin-dispatch work
**Step:** Step 2 (follow-up on the shipped NodeBuildSystemProbe)
**Authored:** 2026-05-13

## Context

The shipped `NodeBuildSystemProbe` (S2-02, commit `8c8ad84`) emits `package_manager ∈ {"bun", "pnpm", "yarn", "npm", null}`. The `"yarn"` value collapses Yarn Classic (1.x) and Yarn Berry (2+) into one bucket. Production ADR-0031 (plugin architecture) treats them as **distinct plugin scopes** — `vulnerability-remediation--node--yarn-classic` and `vulnerability-remediation--node--yarn-berry` are different plugins with different probes, adapters, and recipes — because their dependency models are architecturally different (`node_modules` resolution vs. Plug'n'Play `.pnp.cjs`). Phase 8's Supervisor reads `package_manager` for plugin dispatch; if the probe collapses, the Supervisor cannot dispatch correctly.

This story fixes the collapse at the gather layer (the right layer: facts not judgments — production design.md §2). The probe was designed with Open/Closed enum extension as a first-class seam (`_LOCKFILE_PRECEDENCE` tuple docstring: *"Adding a new package manager is a single tuple-entry insertion + schema enum bump + fixture test. Zero edits to selection logic."*). This story exercises that seam.

The decision is recorded in [Phase 1 ADR-0013](../ADRs/0013-yarn-variants-as-distinct-package-managers.md).

## References

| Reference | What to read |
|---|---|
| [ADRs/0013-yarn-variants-as-distinct-package-managers.md](../ADRs/0013-yarn-variants-as-distinct-package-managers.md) | The decision: split `yarn` into `yarn-classic` + `yarn-berry`. Detection algorithm + priority order. |
| [production/adrs/0031-plugin-architecture.md](../../../production/adrs/0031-plugin-architecture.md) | Plugin scope tuple (task × language × build-tool); `yarn-classic` and `yarn-berry` are distinct scopes. |
| [production/adrs/0032-language-search-adapters.md](../../../production/adrs/0032-language-search-adapters.md) | Yarn Classic and Yarn Berry will register different `dep_graph` adapters (node_modules walk vs PnP graph) — this distinction starts here. |
| [final-design.md §"NodeBuildSystemProbe"](../final-design.md) | The probe's design of record; the "Package-manager resolution by lockfile precedence" bullet gets the yarn-variant follow-on. |
| [phase-arch-design.md §"Component design" #2](../phase-arch-design.md) | Public interface; the schema is the contract surface that changes. |
| [stories/S2-02-node-build-system-probe.md](S2-02-node-build-system-probe.md) | The GREEN base story this one extends. |
| `src/codegenie/probes/node_build_system.py` | The shipped probe. The `_LOCKFILE_PRECEDENCE` tuple is the Open/Closed seam this story uses. |
| `src/codegenie/schema/probes/node_build_system.schema.json` | The schema with the current collapsed enum. |
| Yarn Berry migration docs (https://yarnpkg.com/getting-started/migration) | Berry's distinguishing filesystem markers (`.yarnrc.yml`, `.yarn/`, `.pnp.cjs`). |

## Goal

Make `NodeBuildSystemProbe` emit `yarn-classic` or `yarn-berry` (never `"yarn"`) when `yarn.lock` is the winning lockfile. Detection is deterministic, priority-ordered, uses converging signals (`package.json#packageManager` first; filesystem markers next; safe-default classic with a warning). Schema enum changes from `["bun", "pnpm", "yarn", "npm", null]` to `["bun", "pnpm", "yarn-classic", "yarn-berry", "npm", null]`. The change is surgical: same probe, same coordinator contract, same cache discipline — only the value space of one field widens. Schema `$id` bumps `v0.1.0 → v0.2.0` to record the contract change.

## Acceptance criteria

- [ ] **AC-1 — Schema enum updated.** `node_build_system.schema.json` `package_manager` enum is exactly `["bun", "pnpm", "yarn-classic", "yarn-berry", "npm", null]`. The string `"yarn"` is no longer a valid value. Schema `$id` bumps to `v0.2.0.json`.
- [ ] **AC-2 — Classic from `packageManager` v1.** A fixture repo with `package.json#packageManager == "yarn@1.22.19"` (or any `yarn@1.*`) produces `package_manager == "yarn-classic"` and no `yarn_variant_inferred` warning.
- [ ] **AC-3 — Berry from `packageManager` v2/3/4.** A fixture repo with `package.json#packageManager` starting `yarn@2.`, `yarn@3.`, or `yarn@4.` (any 2+ major) produces `package_manager == "yarn-berry"` and no `yarn_variant_inferred` warning.
- [ ] **AC-4 — Berry from `.yarnrc.yml` marker.** When `packageManager` is absent AND `.yarnrc.yml` exists in repo root, the probe produces `"yarn-berry"` and no warning. (Classic uses `.yarnrc` — note the file extension difference is the distinguishing signal.)
- [ ] **AC-5 — Berry from `.yarn/` directory marker.** When priorities 1–2 are negative AND `.yarn/` directory exists, the probe produces `"yarn-berry"` and no warning.
- [ ] **AC-6 — Berry from PnP file marker.** When priorities 1–3 are negative AND `.pnp.cjs` OR `.pnp.loader.mjs` exists, the probe produces `"yarn-berry"` and no warning.
- [ ] **AC-7 — Classic safe-default with warning.** When `yarn.lock` is the resolved lockfile AND priorities 1–4 are all negative (no Berry markers), the probe produces `"yarn-classic"` AND emits the warning `node_build_system.yarn_variant_inferred` (matches the ADR-0007 pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`). The warning surfaces that confidence is medium — the result is the safe-default, not a positive identification.
- [ ] **AC-8 — Malformed `packageManager` falls through to marker detection.** A `package.json#packageManager` value that does not match `^yarn@\d+\.` (e.g., `"yarn"`, `"yarn@xyz"`, `"yarn@"`) is ignored at priority 1 and detection falls through to priorities 2–5. A `node_build_system.package_manager_field_unparseable` warning is emitted.
- [ ] **AC-9 — Non-yarn unaffected.** When the winning lockfile is `bun.lockb`, `pnpm-lock.yaml`, or `package-lock.json`, no variant-detection logic runs and `package_manager` is the existing single-value resolution (`bun`, `pnpm`, `npm`). No regression.
- [ ] **AC-10 — Existing S2-02 ACs all still pass.** The 22 ACs from S2-02 continue to hold: lockfile precedence, multi-lockfile warning, `tsconfig.json` extends chain, node-version precedence, bundler dict-lookup, `package.json#scripts` verbatim, etc. The full S2-02 test suite is green.
- [ ] **AC-11 — Two new fixtures land.**
  - `tests/fixtures/node_yarn_berry_pnp/` — Berry with PnP: `.yarnrc.yml` + `.pnp.cjs` + `yarn.lock` (Berry YAML header) + `package.json` with `packageManager: "yarn@4.5.0"`.
  - `tests/fixtures/node_yarn_berry_nonpnp/` — Berry without PnP: `.yarnrc.yml` + `yarn.lock` (Berry YAML header) + `package.json` with `packageManager: "yarn@3.6.4"`, no `.pnp.cjs` or `.yarn/` directory.
  - The existing `tests/fixtures/node_yarn_legacy/` validates as `yarn-classic` (already shaped this way; no edits to that fixture).
- [ ] **AC-12 — Schema validation rejects old `"yarn"` value.** A synthetic envelope written with `package_manager: "yarn"` raises `SchemaValidationError`. (Catches any caller or test that didn't update past v0.1.0.)
- [ ] **AC-13 — `_detect_yarn_variant()` is pure given inputs.** The detection function takes (`repo_root: Path`, `parsed_manifest: dict | None`) and returns `Literal["yarn-classic", "yarn-berry"]` (no side effects, no I/O beyond filesystem existence checks on the listed marker paths). Property test: calling it twice on the same fixture produces the same result.
- [ ] **AC-14 — Open/Closed seam preserved.** The `_LOCKFILE_PRECEDENCE` tuple still resolves the lockfile first (no change to its shape); variant detection runs in a separate, additive function called only when the resolved manager is yarn. Adding a future variant (e.g., yarn-modern-v5 if it ever forks) is again a single function-call seam edit.
- [ ] **AC-15 — Golden files updated.** Any committed golden file under `tests/golden/` that referenced `package_manager: "yarn"` is updated to `yarn-classic` (Classic fixtures) or `yarn-berry` (Berry fixtures). CI golden diff is clean.

## Implementation outline

1. **Schema first.** Update `node_build_system.schema.json`: bump `$id`, update `package_manager` enum, update the description string to name both variants and the detection-priority order.
2. **Add the detection function.** New module-level function `_detect_yarn_variant(repo_root, parsed_manifest) -> Literal["yarn-classic", "yarn-berry"]` in `node_build_system.py`. Implementation is a small priority-ordered chain (~30 lines):
   ```
   if packageManager matches yarn@(\d+)\.(\d+) and major == 1: return yarn-classic
   if packageManager matches yarn@(\d+)\.(\d+) and major >= 2: return yarn-berry
   if (repo_root / ".yarnrc.yml").exists(): return yarn-berry
   if (repo_root / ".yarn").is_dir(): return yarn-berry
   if (repo_root / ".pnp.cjs").exists() or (repo_root / ".pnp.loader.mjs").exists(): return yarn-berry
   emit "yarn_variant_inferred" warning; return yarn-classic
   ```
3. **Wire into resolution.** In the probe's main `run()` flow, when the resolved lockfile is `yarn.lock` (the third entry in `_LOCKFILE_PRECEDENCE`), call `_detect_yarn_variant()` instead of using the static `"yarn"` string. For other lockfiles, keep the static string from the tuple.
4. **Fixtures.** Create the two new fixtures with minimal viable content. Each fixture's `README.md` documents what makes it specifically Classic or Berry (which markers are present/absent).
5. **Tests.** New test file `tests/unit/probes/test_node_build_system_yarn_variant.py` covers ACs 1–14 with one test per AC where practical (tests 2–9 are the priority chain). One integration test runs the full gather on each of the three yarn fixtures and asserts the final `repo-context.yaml` shape.
6. **Golden updates.** Run the test suite; update any failing golden files; commit the golden diff as part of the same PR.

## TDD plan — red / green / refactor

### Red phase (write all failing tests first; each must fail for the right reason)

| Test | Asserts | Fixture |
|---|---|---|
| `test_schema_enum_excludes_bare_yarn` | Schema validator rejects `package_manager: "yarn"`; accepts `yarn-classic`, `yarn-berry` | n/a (synthetic envelope) |
| `test_yarn_classic_from_packagemanager_v1` | `package_manager == "yarn-classic"` for `packageManager: "yarn@1.22.19"`; no `yarn_variant_inferred` warning | `node_yarn_legacy/` (extended with `packageManager` field) |
| `test_yarn_berry_from_packagemanager_v3` | `"yarn-berry"`; no warning | `node_yarn_berry_nonpnp/` |
| `test_yarn_berry_from_packagemanager_v4` | `"yarn-berry"`; no warning | `node_yarn_berry_pnp/` |
| `test_yarn_berry_from_yarnrc_yml` | `"yarn-berry"`; no warning | synthesized fixture (or temp-dir construct in test) |
| `test_yarn_berry_from_yarn_dir` | `"yarn-berry"`; no warning | synthesized fixture |
| `test_yarn_berry_from_pnp_cjs` | `"yarn-berry"`; no warning | `node_yarn_berry_pnp/` |
| `test_yarn_classic_safe_default_emits_warning` | `"yarn-classic"`; warning `node_build_system.yarn_variant_inferred` present | synthesized: only `yarn.lock`, no other markers |
| `test_packagemanager_malformed_falls_through` | `package_manager_field_unparseable` warning + correct fallback resolution | synthesized: `packageManager: "yarn@xyz"` + `.yarnrc.yml` → still `yarn-berry` |
| `test_npm_unaffected_by_variant_detection` | `package_manager == "npm"` (no `yarn_variant_*` warnings) | `node_typescript_helm/` (existing pnpm fixture — adapted, or use a pure npm fixture) |
| `test_detect_function_idempotent` | Property test (hypothesis): same `(repo_root, parsed_manifest)` yields same result | synthesized over priority cases |

Run the tests. Confirm every one fails for the right reason (schema validator currently accepts `"yarn"`; probe currently returns `"yarn"`). If any test passes accidentally, the test is wrong — strengthen before proceeding (Rule 9: tests verify intent).

### Green phase (minimum code to pass each test)

1. Update schema enum + `$id`.
2. Add `_detect_yarn_variant()`.
3. Wire into `run()`'s lockfile resolution.
4. Confirm all red tests now green.
5. Run the full S2-02 test suite — must stay green (AC-10).

### Refactor (while green)

- If priority-2/3/4 marker checks share a helper, extract.
- Confirm no regex backtracking on the `packageManager` parse (the regex is anchored + tight: `^yarn@(\d+)\.`).
- Run full Phase 1 test suite. No regressions.
- Update golden files (AC-15).

## Files to touch

| Path | Action | Reason |
|---|---|---|
| `src/codegenie/schema/probes/node_build_system.schema.json` | Modify | Enum + `$id` + description |
| `src/codegenie/probes/node_build_system.py` | Modify | Add `_detect_yarn_variant()`; wire into `run()` |
| `tests/unit/probes/test_node_build_system_yarn_variant.py` | Create | Per-AC unit tests + property test |
| `tests/fixtures/node_yarn_berry_pnp/package.json` | Create | Fixture with `packageManager: "yarn@4.5.0"` + a minimal dep |
| `tests/fixtures/node_yarn_berry_pnp/yarn.lock` | Create | Berry YAML header |
| `tests/fixtures/node_yarn_berry_pnp/.yarnrc.yml` | Create | Berry-only marker file |
| `tests/fixtures/node_yarn_berry_pnp/.pnp.cjs` | Create | PnP marker (can be a stub) |
| `tests/fixtures/node_yarn_berry_pnp/README.md` | Create | Document what makes this fixture Berry-PnP |
| `tests/fixtures/node_yarn_berry_nonpnp/package.json` | Create | Fixture with `packageManager: "yarn@3.6.4"` |
| `tests/fixtures/node_yarn_berry_nonpnp/yarn.lock` | Create | Berry YAML header |
| `tests/fixtures/node_yarn_berry_nonpnp/.yarnrc.yml` | Create | Berry-only marker file |
| `tests/fixtures/node_yarn_berry_nonpnp/README.md` | Create | Document Berry-no-PnP shape |
| `tests/golden/*` | Modify (as needed) | Any golden file with `package_manager: "yarn"` updates to `yarn-classic` or `yarn-berry` |
| (consequential) `docs/phases/01-context-gather-layer-a-node/ADRs/0013-yarn-variants-as-distinct-package-managers.md` | Already created in the same PR train | The decision record |

## Out of scope

- **Yarn Berry's lockfile *parsing*.** That belongs to S3-03. This story changes detection of the package manager only, not parsing. S3-03 must now branch on `yarn-classic` vs `yarn-berry` when choosing a parser (Berry's lockfile is YAML — `yaml.CSafeLoader` is the right primitive; Classic's `pyarn`-or-hand-rolled per ADR-0003 covers Classic only). S3-03's design will absorb this.
- **Bun version variants.** Bun is a single family today; no architectural fork worth splitting on.
- **pnpm version variants.** pnpm v6–v9 are forward-compatible enough at the plugin level; one family.
- **npm v6 vs v7+.** Lockfile-version differences live in `S3-05` (NodeManifest) cross-check, not here.
- **Schema migrations for already-emitted data.** The probe shipped this week (commit `8c8ad84`); no production data exists at the old value space. The migration is the new-fixture additions + golden updates in this PR.
- **Plugin-side adapters.** `yarn-classic` and `yarn-berry` will register different `dep_graph` adapters per ADR-0032, but the adapter implementations land in Phase 3 plugins, not here.

## Notes for implementer

- **The Open/Closed seam is the design point.** The `_LOCKFILE_PRECEDENCE` tuple stays as-is — variant detection is a *separate function* called after the static lockfile→manager resolution. Future variants (if Yarn 5+ ever ships an architectural change again) are an extension to that function, not edits to the tuple.
- **`.yarnrc.yml` vs `.yarnrc`.** Note the file extension. `.yarnrc.yml` is **Berry-only**; `.yarnrc` is the deprecated Classic config. Don't confuse them.
- **Yarn Berry without PnP.** Berry supports `nodeLinker: node-modules` (in `.yarnrc.yml`) which means no `.pnp.cjs`. The `node_yarn_berry_nonpnp/` fixture covers this case — Berry the package manager, but Classic-style resolution. The plugin distinction is still Berry because the *manager* differs, even though the resolution model matches Classic. This is intentional: plugins are scoped on the manager, not on the resolution model.
- **`packageManager` regex.** Anchor the regex and bound the capture: `^yarn@(\d+)\.\d+\.\d+` (full semver) or `^yarn@(\d+)\.` (major only). Major-only is sufficient for variant detection; pre-release suffixes (`yarn@4.0.0-rc.42`) match the latter cleanly.
- **Confidence accounting.** Priorities 1–4 yield definitive detection → confidence stays whatever the rest of the probe computes. Priority 5 (safe-default) is medium confidence in this dimension; the warning IS the confidence signal — the probe's overall `confidence` field is unaffected because the lockfile-precedence step already determines the family with certainty.
- **Warning emission.** Both new warnings (`yarn_variant_inferred`, `package_manager_field_unparseable`) match the ADR-0007 pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. Add them to any warning-ID registry / constant list per the Phase 1 convention.
- **No new dependencies.** This story adds zero runtime dependencies. The regex is stdlib `re`; `pathlib.Path.exists()` / `.is_dir()` are stdlib. No `yaml.load` of `.yarnrc.yml` needed for detection — its mere *existence* is the signal.
- **Run `phase-story-validator` on this story before executing.** Coverage critic will pressure-test missing edge cases (e.g., `packageManager: "yarn@1"` — no minor.patch — should it be parsed?); test-quality critic will catch any tautological tests; consistency critic will check ADR alignment.
