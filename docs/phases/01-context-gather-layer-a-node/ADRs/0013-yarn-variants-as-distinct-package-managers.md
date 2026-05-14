# ADR-0013 (Phase 1): Yarn Classic and Yarn Berry as distinct `package_manager` values

**Status:** Accepted
**Date:** 2026-05-13
**Tags:** schema · package-manager · plugin-dispatch · extension-by-addition
**Related:** ADR-0003 (parser choice), ADR-0004 (subschema `additionalProperties: false`), ADR-0007 (warning-ID pattern), production ADR-0031 (plugin architecture), production ADR-0032 (language search adapters)

## Context

The shipped `NodeBuildSystemProbe` (story S2-02, commit `8c8ad84`) emits `build_system.package_manager` from an enum currently shaped as `["bun", "pnpm", "yarn", "npm", null]`. The `"yarn"` value collapses two operationally distinct package managers:

- **Yarn Classic (v1.x)** — `node_modules`-based resolution; `.yarnrc` config file; custom `yarn.lock` format (not YAML); `yarn install` produces a `node_modules` tree.
- **Yarn Berry (v2+)** — Plug'n'Play (`.pnp.cjs`) resolution by default (no `node_modules`); `.yarnrc.yml` config file; YAML `yarn.lock` format; `yarn install` produces a `.pnp.cjs` resolution graph; `nodeLinker: node-modules` is an opt-in fallback.

This isn't a minor version bump — Yarn 2's release notes explicitly describe a "complete rewrite" of the package manager with a new dependency-resolution architecture. The differences propagate everywhere:

- **Lockfile format.** Classic's `yarn.lock` is a custom format; Berry's is YAML. The Phase 1 parser-choice ADR (ADR-0003) names `pyarn` — `pyarn` parses **Classic only**. Berry needs `yaml.CSafeLoader` (already in Phase 1 via `safe_yaml`).
- **Dependency resolution.** Classic walks `node_modules`; Berry walks `.pnp.cjs`. A `dep_graph.consumers(package)` query (production ADR-0030 / ADR-0032) is implemented differently per variant — Classic adapter walks the file tree; Berry adapter walks the PnP resolution graph.
- **Container/distroless impact.** A multi-stage Dockerfile for a Classic repo copies `node_modules`. A Berry-PnP repo has no `node_modules` to copy — the runner stage may not even need Node's full module loader at all. The distroless-migration plugin family (production roadmap Phase 7) treats these as fundamentally different cases.

Production ADR-0031 (plugin architecture) treats `(task × language × build-tool)` as the plugin scope tuple. `vulnerability-remediation--node--yarn-classic` and `vulnerability-remediation--node--yarn-berry` are explicitly enumerated as distinct plugins in that ADR's examples. **Phase 8's Supervisor reads `package_manager` from the gathered `RepoContext` for plugin dispatch.** If the probe collapses Yarn variants, the Supervisor cannot dispatch — both plugins would match (or worse, the wrong one would).

This ADR resolves the collapse at the gather layer — the right layer per the production design's "facts, not judgments" commitment (`docs/production/design.md §2`). The probe captures the specific evidence; the Planner consumes it without inference.

## Options considered

- **Option A — split the enum at the probe layer.** Replace `"yarn"` with `"yarn-classic"` and `"yarn-berry"`. Probe adds a small variant-detection function that runs after the `_LOCKFILE_PRECEDENCE` resolution when the resolved manager is yarn. Plugin scope tuple reads `package_manager` directly.
- **Option B — keep the flat enum; rely on `package_manager_version`.** Have the consumer (Phase 8's Supervisor) combine `package_manager + package_manager_version` to derive `yarn-classic` vs `yarn-berry` at dispatch time. Probe stays simpler.
- **Option C — tagged sum type.** Make `package_manager` a discriminated union (`{kind: "yarn", variant: "classic"}` etc.). Schema becomes a Pydantic v2 discriminated union per production ADR-0033.
- **Option D — add a parallel `package_manager_family` field.** Two fields conveying overlapping info; consumers pick.

## Decision

**Adopt Option A.** Replace the single `"yarn"` enum value with `"yarn-classic"` and `"yarn-berry"`. Implement a small variant-detection function (`_detect_yarn_variant`) that runs after the lockfile-precedence resolution when the resolved manager is yarn. The function is priority-ordered, deterministic, uses only filesystem existence checks plus the already-parsed `package.json#packageManager` field.

### Detection algorithm (priority order)

Strongest signal first; fall through on negative.

| Priority | Signal | Result | Confidence |
|---|---|---|---|
| 1 | `package.json#packageManager` matches `^yarn@1\.` | `yarn-classic` | high (Corepack-declared, deterministic) |
| 2 | `package.json#packageManager` matches `^yarn@(2|3|4|\d+)\.` (major ≥ 2) | `yarn-berry` | high |
| 3 | `.yarnrc.yml` exists in repo root (Berry-only filename; Classic uses `.yarnrc`) | `yarn-berry` | high |
| 4 | `.yarn/` directory exists in repo root (Berry's releases/plugins layout) | `yarn-berry` | high |
| 5 | `.pnp.cjs` or `.pnp.loader.mjs` exists in repo root (Berry PnP mode) | `yarn-berry` | high |
| 6 | Default — `yarn.lock` present with no Berry markers | `yarn-classic` | medium (heuristic) |

Priority 6 (the safe-default) emits the warning `node_build_system.yarn_variant_inferred` (matches the ADR-0007 pattern). The warning surfaces that the variant was inferred from the absence of Berry markers, not positively detected. A malformed `packageManager` value at priority 1 emits `node_build_system.package_manager_field_unparseable` and falls through to priority 3.

### Schema change

- Enum: `["bun", "pnpm", "yarn", "npm", null]` → `["bun", "pnpm", "yarn-classic", "yarn-berry", "npm", null]`
- `$id` bump: `v0.1.0.json` → `v0.2.0.json` (per ADR-0004 schema versioning convention)
- Description updated to name both variants and the detection-priority order

## Tradeoffs

| Gain | Cost |
|---|---|
| Plugin scope tuple (production ADR-0031) reads `package_manager` directly; no field combination at dispatch time | One small detection function added to the probe (~30 lines); two new fixtures land |
| Berry's distinct lockfile format (S3-03's parser choice) gets a clean discriminator at gather time — the parser knows which variant it's parsing from `RepoContext`, not from re-detecting | Existing `tests/fixtures/node_yarn_legacy/` covers Classic; two new Berry fixtures must be authored (pnp + non-pnp) |
| Future operational forks (Yarn 5+ if it ever ships another architectural rewrite) extend the function, never edit the lockfile tuple — Open/Closed seam preserved | Schema `$id` bump signals a contract change; any external consumer that pinned `v0.1.0` must update (acceptable — probe shipped this week, no external consumers yet) |
| Detection logic is fully deterministic + uses only stdlib path checks; no new dependencies | The priority-6 safe-default is a heuristic — emits a warning to surface the medium-confidence inference rather than hide it (Rule 12: fail loud) |
| Probe stays a "facts not judgments" producer — the Planner doesn't need to know how variant detection works, only the result | One more warning ID to register; one cross-check (S3-05 `package_manager_version` should agree with the variant — Classic versions are 1.x; Berry versions are 2+.x) |

## Consequences

- **S2-02a-yarn-variant-detection** is the follow-up story implementing this ADR. The shipped S2-02 stays GREEN; S2-02a layers the variant-detection seam on top.
- **S3-03 (yarn lockfile parser) must branch on variant.** Classic uses `pyarn` (per ADR-0003); Berry uses `yaml.CSafeLoader` (Phase 1's existing `safe_yaml`). The choice is keyed on the now-distinguished `package_manager` value. S3-03's design will absorb this when it's authored.
- **S3-05 (NodeManifest probe) cross-check.** When `S3-05` populates `package_manager_version`, it cross-checks: `yarn-classic` should have version `1.*`; `yarn-berry` should have version `2+.*`. Inconsistency emits `node_manifest.package_manager_variant_version_mismatch`.
- **Schema $id versioning.** This is the first per-probe sub-schema `$id` bump within Phase 1. The pattern (`vMAJOR.MINOR.PATCH.json`) is established here for future contract changes. ADR-0004 ratified `additionalProperties: false` as the schema discipline; this ADR ratifies semver-on-$id as the contract-evolution discipline.
- **Plugin scope reads `package_manager` directly.** Phase 8's Supervisor pulls `repo_context.node_build_system.build_system.package_manager` and matches against plugin `scope.build_systems`. The match is a literal string compare — no combining, no inference.
- **Adapter dispatch (production ADR-0032).** When Phase 3+ ships Yarn plugins, `vulnerability-remediation--node--yarn-classic` registers its own `dep_graph` adapter (walks `node_modules`); `vulnerability-remediation--node--yarn-berry` registers its own (walks `.pnp.cjs`). The two plugins share most of the Node-vuln behavior via `extends: vulnerability-remediation--node--*` inheritance per ADR-0031.
- **No cascade through Phase 0 or other Phase 1 probes.** This ADR is self-contained to the `NodeBuildSystemProbe`'s output. Other probes (`LanguageDetectionProbe`, `NodeManifestProbe`, etc.) are unaffected — they consume or produce different fields.

## Reversibility

**Low cost.** The probe shipped this week; the only blast radius is the schema enum + the detection function + two new fixtures + the test additions. Reverse migration (collapsing back to `"yarn"`) would require coordinated edits across the probe + schema + tests, plus accepting that Phase 8's Supervisor cannot dispatch on Yarn variant — which would force a re-engineering at the orchestration layer. Recommended direction: keep the split; revisit only if Yarn Berry's adoption stalls and the variant distinction stops mattering operationally (extremely unlikely — Berry's PnP model is now the default in new projects).

## Evidence / sources

- `src/codegenie/probes/node_build_system.py` — the shipped probe; `_LOCKFILE_PRECEDENCE` is the Open/Closed seam this ADR extends
- `src/codegenie/schema/probes/node_build_system.schema.json` — the schema that gains the enum update
- ADR-0003 (Phase 1) — `pyarn` parser choice; Classic-only by design
- ADR-0004 (Phase 1) — subschema `additionalProperties: false` + `$id` versioning
- ADR-0007 (Phase 1) — warning-ID pattern that `yarn_variant_inferred` and `package_manager_field_unparseable` conform to
- Production ADR-0031 — plugin scope tuple (`task × language × build-tool`); `yarn-classic` / `yarn-berry` enumerated as distinct scopes
- Production ADR-0032 — language search adapters; per-variant `dep_graph` implementations
- Yarn Berry migration documentation (https://yarnpkg.com/getting-started/migration) — the canonical source on Berry's filesystem markers (`.yarnrc.yml`, `.yarn/`, `.pnp.cjs`) and the `packageManager` field convention
- Node.js `packageManager` field specification (Corepack) — https://nodejs.org/api/packages.html#packagemanager
