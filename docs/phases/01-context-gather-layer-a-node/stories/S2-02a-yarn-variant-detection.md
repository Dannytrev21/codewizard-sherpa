# S2-02a — Yarn variant detection: split `yarn` into `yarn-classic` and `yarn-berry`

**Status:** Done — 2026-05-14 (phase-story-executor; see [`_attempts/S2-02a.md`](_attempts/S2-02a.md))
**Estimate:** S (≈1 working day)
**Depends on:** S2-02 (GREEN — the existing NodeBuildSystemProbe)
**Blocks:** Phase 8 plugin-dispatch work (Supervisor reads `package_manager` directly). **NOTE:** S3-03 (yarn lockfile parser) was authored *after* this story and chose a **unified** parser dispatching on `_HAS_PYARN` (pyarn-vs-handrolled), not on `yarn-classic` vs `yarn-berry` — so the gather-layer variant split here informs the Planner, not the parser. See Out-of-scope §1 below.
**Step:** Step 2 (follow-up on the shipped NodeBuildSystemProbe)
**Authored:** 2026-05-13
**Hardened:** 2026-05-14 (phase-story-validator — see `_validation/S2-02a-yarn-variant-detection.md`)

## Validation notes (added 2026-05-14)

This story passed through `phase-story-validator` once. Net changes:

- **Implementation status reconciled.** At validation time, the variant-detection code (`_BERRY_MARKERS`, `_detect_yarn_variant`, schema `v0.2.0`, modified `run()` wiring) is already present in working-tree changes ahead of execution. ACs were re-cast where useful from "implement X" to "X is present" so the executor can verify, not redo. The remaining net-new work for the executor is: fixture content under `node_yarn_berry_pnp/` + `node_yarn_berry_nonpnp/`, the new unit-test module, golden-file regeneration, and the warning-ID registry assertion.
- **Stale S3-03 claim corrected.** S3-03's hardened story (commit `3ada173`) chose a unified parser dispatching on `_HAS_PYARN` rather than on variant. The original Out-of-scope §1 sentence about S3-03 "absorbing" the variant distinction is wrong; updated to match the shipped design.
- **Priority-conflict ACs added (AC-16, AC-17).** Test-quality critic flagged that no AC pins "priority 1 wins over priority 3" — a priority-order-flip mutation would pass the original test set. Two explicit conflict tests added.
- **Open/Closed extension AC added (AC-18) + compile-time discipline AC added (AC-19).** Design-patterns critic flagged that the Berry-marker scan should be a module-level tuple parallel to `_LOCKFILE_PRECEDENCE` / `_BUNDLERS_SORTED` / `_NODE_VERSION_PINNED_SOURCES`, with an import-time priority assert. The shipped code already does this via `_BERRY_MARKERS`; the AC promotes the property from implicit-in-source to explicit-in-spec so a future refactor that flattens it back to an if-chain trips the gate.
- **Warning-emission location pinned (AC-20).** Coverage + consistency critics flagged that neither AC-7 nor AC-8 said *where* the warning lands; the shipped probe places all warnings into `slice.warnings` and leaves `ProbeOutput.warnings` empty. Made explicit.
- **AC wording tightened across the board.** AC-2 / AC-3 / AC-4 / AC-5 / AC-6 / AC-8 / AC-13 / AC-14 rewritten for precision: regex anchor explanation, "major ≥ 2" rather than the enumeration `{2,3,4}`, marker preconditions (yarn.lock must be the winning lockfile), AC-13 reworded from "pure" to "deterministic with read-only filesystem I/O on the enumerated marker paths only" (the original wording was a contradiction — `Path.exists()` is I/O).
- **TDD plan strengthened.** Idempotency property test replaced with a hypothesis property test that pins the *priority invariant* (higher-priority signals override lower-priority signals); regex-too-loose mutation cases added to malformed parametrize; explicit absent-warning assertions added for the well-formed-input tests.
- **Notes for implementer expanded.** Added paragraphs on (a) the functional-core/imperative-shell opportunity for `_detect_yarn_variant` if the signature is ever revisited, (b) confidence-demotion asymmetry rationale (variant is a secondary dimension under a certain family), (c) local-dev cache invalidation behavior on the schema `$id` bump.
- **Schema `$id` `v0.2.0` increment surfaced as a known policy gap.** ADR-0004 explicitly defers sub-schema versioning policy to Phase 2; ADR-0013 chose `v0.2.0` ahead of that policy. The removal of `"yarn"` from the enum is arguably MAJOR semver (old envelopes become invalid). Noted in implementer notes for Phase 2 ratification; not blocking.

Verdict: **HARDENED** — ready for `phase-story-executor`.



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

- [x] **AC-1 — Schema enum updated.** `node_build_system.schema.json` `package_manager` enum is exactly `["bun", "pnpm", "yarn-classic", "yarn-berry", "npm", null]`. The string `"yarn"` is no longer a valid value. Schema `$id` bumps to `.../v0.2.0.json`. (See implementer notes §"Schema $id increment" for the deferred-policy gap on whether `v0.2.0` vs `v1.0.0` is the right semver for a value-removal enum change; ADR-0004 explicitly defers this policy.)

- [x] **AC-2 — Classic from `packageManager` major == 1.** When `package.json#packageManager` matches `^yarn@(\d+)\.` with captured major == `1` (e.g., `yarn@1.22.19`, `yarn@1.0.0`, `yarn@1.22.19-rc.1`, `yarn@1.22.19+sha224.abcd`), the probe produces `package_manager == "yarn-classic"`, no `yarn_variant_inferred` warning, and no `package_manager_field_unparseable` warning. The trailing `\.` anchor is intentional: it disambiguates a fully-formed `yarn@1.x` (Classic) from the under-specified `yarn@1` (no minor) which falls through to AC-8 instead.

- [x] **AC-3 — Berry from `packageManager` major ≥ 2.** When `package.json#packageManager` matches `^yarn@(\d+)\.` with captured major ≥ `2` (e.g., `yarn@2.4.3`, `yarn@3.6.4`, `yarn@4.5.0`, `yarn@10.0.0`, `yarn@4.0.0-rc.42`, `yarn@4.5.0+sha224.abcd`), the probe produces `package_manager == "yarn-berry"`, no `yarn_variant_inferred` warning, and no `package_manager_field_unparseable` warning. Detection MUST parse the integer major out of the regex capture and branch on `major == 1` vs `major >= 2` — not on a hardcoded set `{2,3,4}`. A property test exercising random major ∈ [2, 99] is required.

- [x] **AC-4 — Berry from `.yarnrc.yml` marker.** **Precondition:** `yarn.lock` is the winning lockfile per `_LOCKFILE_PRECEDENCE` (i.e., no higher-precedence lockfile like `pnpm-lock.yaml` is also present). When the precondition holds, `packageManager` is absent or non-yarn, AND `.yarnrc.yml` exists in repo root, the probe produces `"yarn-berry"` and no `yarn_variant_inferred` warning. A repo with both `.yarnrc.yml` AND legacy `.yarnrc` (mid-migration) resolves to `yarn-berry` via the `.yarnrc.yml` signal — the legacy `.yarnrc` is *not* consulted (Classic is only inferred via the AC-7 safe-default).

- [x] **AC-5 — Berry from `.yarn/` directory marker.** **Precondition:** same as AC-4. When priorities 1–3 are all negative AND `repo_root / ".yarn"` is a directory (`Path.is_dir()` true), the probe produces `"yarn-berry"` and no warning.

- [x] **AC-6 — Berry from PnP file marker.** **Precondition:** same as AC-4. When priorities 1–4 are all negative AND `repo_root / ".pnp.cjs"` OR `repo_root / ".pnp.loader.mjs"` exists, the probe produces `"yarn-berry"` and no warning.

- [x] **AC-7 — Classic safe-default with warning.** When `yarn.lock` is the winning lockfile AND priorities 1–5 are all negative (no Berry markers, no positive Yarn `packageManager` field), the probe produces `"yarn-classic"` AND appends the warning `node_build_system.yarn_variant_inferred` to `build_system.warnings` (the slice's warnings list — see AC-20). The warning surfaces that confidence in the variant dimension is medium (the result is a safe-default inference, not a positive signal). The probe's overall `confidence` field is **not** demoted at this point — see implementer notes §"Confidence accounting" for the asymmetry rationale vs. `multi_lockfile`.

- [x] **AC-8 — Malformed / non-string `packageManager` falls through to marker detection.** A `package.json#packageManager` value that is **not a string** (missing field, `null`, integer, list, dict, boolean) OR is a string that begins with `yarn@` but does not match `^yarn@(\d+)\.` (e.g., `"yarn@"`, `"yarn@xyz"`, `"yarn@1"` (no minor), `"yarn@2x"`, `"yarn@123abc"`, `"yarn@1x.0"`) is treated as priority-1-negative; detection falls through to priorities 3–6. For **string** values that look yarn-shaped but fail the regex (begins with `"yarn"`), the warning `node_build_system.package_manager_field_unparseable` is appended to `build_system.warnings`. For **missing field**, `null`, or non-string types, the field is treated as simply absent and *no* `package_manager_field_unparseable` warning is emitted (absence is the normal case, not a soft-degrade signal). The bare string `"yarn"` (no `@`-suffix) IS yarn-shaped enough to warrant the unparseable warning per the shipped probe's parsing convention.

- [x] **AC-9 — Non-yarn unaffected.** When the winning lockfile is `bun.lockb`, `pnpm-lock.yaml`, or `package-lock.json`, no variant-detection logic runs and `package_manager` is the existing single-value resolution (`bun`, `pnpm`, `npm`). No `yarn_variant_*` warnings or `package_manager_field_unparseable` warning are emitted regardless of `.yarnrc.yml` / `.yarn/` / `.pnp.cjs` presence (legacy Berry config left behind after a migration to pnpm/npm/bun must not trigger yarn-variant signals).

- [x] **AC-9b — Variant detection co-exists with cross-manager disagreement.** When `yarn.lock` is the winning lockfile AND `package.json#packageManager` declares a non-yarn manager (e.g., `pnpm@8`, `npm@10`), the probe still runs variant detection through priorities 3–6 (the `packageManager` string is non-yarn so priorities 1–2 are negative; no `package_manager_field_unparseable` is emitted because the field parsed cleanly — it merely disagrees). Both `package_manager.declaration_lockfile_disagree` (from S2-02) AND the appropriate variant outcome (positive Berry marker or AC-7 safe-default) appear in `build_system.warnings`.

- [x] **AC-10 — Existing S2-02 ACs all still pass.** The 22 ACs from S2-02 continue to hold: lockfile precedence, multi-lockfile warning, `tsconfig.json` extends chain, node-version precedence, bundler dict-lookup, `package.json#scripts` verbatim, etc. The full S2-02 test suite is green.

- [x] **AC-11 — Two new fixtures land.**
  - `tests/fixtures/node_yarn_berry_pnp/` — Berry with PnP: `.yarnrc.yml` + `.pnp.cjs` + `yarn.lock` + `package.json` with `packageManager: "yarn@4.5.0"`. (A minimal Classic `# yarn lockfile v1\n` header is sufficient for the lockfile body — detection looks at markers, not lockfile content; see AC-22.)
  - `tests/fixtures/node_yarn_berry_nonpnp/` — Berry without PnP: `.yarnrc.yml` + `yarn.lock` + `package.json` with `packageManager: "yarn@3.6.4"`, **no** `.pnp.cjs` or `.yarn/` directory.
  - The existing `tests/fixtures/node_yarn_legacy/` validates as `yarn-classic` (already shaped this way; no edits to that fixture).
  - Each new fixture's `README.md` documents which markers are present/absent and which detection priority is expected to fire.

- [x] **AC-12 — Schema validation rejects old `"yarn"` value.** A synthetic envelope written with `package_manager: "yarn"` is rejected by the project's real validation entry point (`codegenie.schema.validator.validate(...)`, not a hand-rolled `jsonschema.validate(...)`) and surfaces a `SchemaValidationError`. The test exercises the integration point, not a hand-rolled stub.

- [x] **AC-13 — `_detect_yarn_variant()` is deterministic and side-effect-free beyond enumerated marker reads.** The detection function takes (`repo_root: Path`, `parsed_manifest: Mapping[str, Any] | None`) and returns a tuple `(Literal["yarn-classic", "yarn-berry"], list[str])` where the second element is the warning IDs to emit (typically empty; non-empty only for the safe-default and the `package_manager_field_unparseable` cases). The function:
  - Performs read-only filesystem I/O **only** via `Path.exists()` / `Path.is_dir()` on the marker paths enumerated in `_BERRY_MARKERS` (`.yarnrc.yml`, `.yarn`, `.pnp.cjs`, `.pnp.loader.mjs`).
  - Performs no writes, no network calls, no subprocess calls, no logging.
  - Mutates no module-level state.
  - Property test (`hypothesis`): for any random combination of (`packageManager` string drawn from a strategy of valid+malformed shapes, present-marker set drawn from the powerset of `{.yarnrc.yml, .yarn, .pnp.cjs, .pnp.loader.mjs}`) the function (a) returns a value in `{"yarn-classic", "yarn-berry"}`, (b) returns the same value on a second call with identical inputs, (c) honors the *priority invariant*: a positive priority-1 signal forces `yarn-classic` regardless of any lower-priority signal; a positive priority-2 signal forces `yarn-berry` regardless of any lower-priority signal.

- [x] **AC-14 — Open/Closed seam preserved (lockfile tuple).** The `_LOCKFILE_PRECEDENCE` tuple's shape is unchanged. Its index-`[2]` entry is the seam where the static `"yarn"` literal is now overridden by `_detect_yarn_variant`. The probe's module docstring AND an inline comment at the tuple definition name the override — so a reader grepping for `"yarn"` does not mistake the literal for the emitted value. Adding a future variant (e.g., yarn-modern-v5 if it ever forks) is an entry in `_BERRY_MARKERS` and/or one branch in `_detect_yarn_variant`'s major-version check — never an edit to `_LOCKFILE_PRECEDENCE` itself.

- [x] **AC-15 — Golden files updated.** Any committed golden file under `tests/golden/` that referenced `package_manager: "yarn"` is updated to `yarn-classic` (Classic fixtures) or `yarn-berry` (Berry fixtures). CI golden diff is clean.

- [x] **AC-16 — Priority-conflict test 1: `packageManager` major == 1 beats `.yarnrc.yml`.** A fixture (or `tmp_path`-constructed repo) with `package.json#packageManager == "yarn@1.22.19"` AND `.yarnrc.yml` present AND `yarn.lock` present produces `package_manager == "yarn-classic"` — proving priority 1 wins over priority 3. No `yarn_variant_inferred` warning. (This test catches the priority-order-flip mutation that the original AC set would not.)

- [x] **AC-17 — Priority-conflict test 2: `.yarnrc.yml` beats `.pnp.cjs` + `.yarn/`.** A fixture with only `.yarnrc.yml` + `.pnp.cjs` + `.yarn/` directory + `yarn.lock` (no `packageManager` field) produces `package_manager == "yarn-berry"` via the priority-3 signal. No warnings. Removing `.yarnrc.yml` from the same fixture still produces `yarn-berry` via priority 4 (`.yarn/`); removing `.yarn/` too still produces `yarn-berry` via priority 5 (`.pnp.cjs`). The cascade is observable and tested.

- [x] **AC-18 — Berry markers are a module-level priority tuple (`_BERRY_MARKERS`).** The four filesystem-marker priorities (`.yarnrc.yml`, `.yarn`, `.pnp.cjs`, `.pnp.loader.mjs`) live as a `Final[tuple[tuple[str, Callable[[Path], bool]], ...]]` at module scope, in priority order, parallel to `_LOCKFILE_PRECEDENCE` / `_BUNDLERS_SORTED` / `_NODE_VERSION_PINNED_SOURCES`. `_detect_yarn_variant` iterates the tuple — it does NOT hand-roll an `if/elif` chain over the four markers. Adding a hypothetical sixth Berry marker (e.g., a future `.yarn-state.json`) is one tuple-entry insertion plus one fixture test; zero edits to `_detect_yarn_variant`'s control flow.

- [x] **AC-19 — Compile-time discipline assertion on `_BERRY_MARKERS`.** A module-level `assert _BERRY_MARKERS[0][0] == ".yarnrc.yml"` (or equivalent priority anchor) fails at import if the priority head drifts. The two new warning IDs (`node_build_system.yarn_variant_inferred`, `node_build_system.package_manager_field_unparseable`) are added to `_WARNING_IDS: frozenset[str]`; the existing import-time regex assertion (`assert _ID_PATTERN.match(_id) ...`) continues to pass for both. Removing either ID from `_WARNING_IDS` while keeping it emitted by `_detect_yarn_variant` would fail an integration test that walks the probe's emitted-warnings vs. the declared set.

- [x] **AC-20 — Warning emission location pinned.** Both new warnings (`node_build_system.yarn_variant_inferred`, `node_build_system.package_manager_field_unparseable`) are appended to `build_system.warnings` (the slice's `warnings` list, mirroring the existing `package_manager.multi_lockfile` / `package_manager.declaration_lockfile_disagree` warnings). `ProbeOutput.warnings` stays `[]`. Typed-exception error IDs continue to land on `ProbeOutput.errors` per ADR-0007.

- [x] **AC-21 — Absent-warning assertions on well-formed inputs.** Every test that exercises a positive priority-1 or priority-2 outcome (AC-2, AC-3) asserts both `"node_build_system.yarn_variant_inferred" not in build_system.warnings` AND `"node_build_system.package_manager_field_unparseable" not in build_system.warnings`. A mutant that always emits one of these warnings would fail these tests. (Without this AC, a constant-warning mutant could pass the positive-case suite.)

- [x] **AC-22 — Lockfile body is not consulted for variant detection.** A regression test confirms that writing the Classic header `# yarn lockfile v1\n` into a fixture's `yarn.lock` while ALSO placing a `.yarnrc.yml` marker yields `yarn-berry` — proving the marker-not-body rule. Future "improvements" that try to discriminate variant by reading the lockfile YAML signature would break this test.

## Implementation outline

1. **Schema first.** Update `node_build_system.schema.json`: bump `$id` to `v0.2.0`, update the `package_manager` enum to `["bun", "pnpm", "yarn-classic", "yarn-berry", "npm", null]`, update the description string to name both variants and the detection-priority order.
2. **Add the marker registry and the detection function (Open/Closed — AC-18).** Two new module-level objects in `node_build_system.py`:
   ```python
   # Priority-ordered Berry filesystem markers. Parallel in shape to
   # _LOCKFILE_PRECEDENCE / _BUNDLERS_SORTED / _NODE_VERSION_PINNED_SOURCES.
   # Adding a future Berry marker is one tuple-entry insertion; zero edits
   # to _detect_yarn_variant's control flow (AC-18).
   _BERRY_MARKERS: Final[tuple[tuple[str, Callable[[Path], bool]], ...]] = (
       (".yarnrc.yml",     lambda root: (root / ".yarnrc.yml").exists()),
       (".yarn",           lambda root: (root / ".yarn").is_dir()),
       (".pnp.cjs",        lambda root: (root / ".pnp.cjs").exists()),
       (".pnp.loader.mjs", lambda root: (root / ".pnp.loader.mjs").exists()),
   )

   # Import-time priority anchor (AC-19) — mirrors the _LOCKFILE_PRECEDENCE
   # anchor (`[0][1] == "bun"`) and the _BUNDLERS_SORTED sortedness assert.
   assert _BERRY_MARKERS[0][0] == ".yarnrc.yml", (
       "S2-02a _BERRY_MARKERS: '.yarnrc.yml' must be the highest-priority "
       f"Berry filesystem marker (got {_BERRY_MARKERS[0]!r})"
   )

   def _detect_yarn_variant(
       repo_root: Path,
       parsed_manifest: Mapping[str, Any] | None,
   ) -> tuple[Literal["yarn-classic", "yarn-berry"], list[str]]:
       """Returns (variant, warning_ids_to_emit). See ADR-0013 for priorities.

       AC-13: deterministic; read-only Path.exists()/.is_dir() on _BERRY_MARKERS
       paths only. No writes, no logging, no subprocess, no module-state mutation.
       """
       warnings: list[str] = []
       pm = parsed_manifest.get("packageManager") if parsed_manifest else None
       if isinstance(pm, str) and pm.startswith("yarn"):
           m = re.match(r"^yarn@(\d+)\.", pm)
           if m is not None:
               return ("yarn-classic" if int(m.group(1)) == 1 else "yarn-berry"), warnings
           warnings.append("node_build_system.package_manager_field_unparseable")
       for _name, predicate in _BERRY_MARKERS:
           if predicate(repo_root):
               return "yarn-berry", warnings
       warnings.append("node_build_system.yarn_variant_inferred")
       return "yarn-classic", warnings
   ```
   Add both new warning IDs (`node_build_system.yarn_variant_inferred`, `node_build_system.package_manager_field_unparseable`) to the module's `_WARNING_IDS` frozenset so the import-time regex assertion covers them (AC-19).
3. **Wire into `run()`.** When the static lockfile-precedence resolution would pick `"yarn"` (the index-`[2]` entry in `_LOCKFILE_PRECEDENCE`), call `_detect_yarn_variant(repo.root, pkg)` instead, append the returned warnings to `slice["warnings"]` (AC-20), and use the returned variant as the `package_manager` value. Add an inline `# NOTE:` comment at the `("yarn.lock", "yarn")` tuple line pointing to the override (AC-14). For other lockfiles, keep the static string from the tuple.
4. **Fixtures.** Create the two new fixtures with minimal viable content. Each fixture's `README.md` documents which markers are present/absent AND which detection priority is expected to fire (per AC-11).
5. **Tests.** New test file `tests/unit/probes/test_node_build_system_yarn_variant.py` covers ACs 1–22:
   - One test per priority-positive case (ACs 2, 3, 4, 5, 6) using fixtures + `tmp_path`-synthesized repos.
   - **Priority-conflict tests (ACs 16, 17)** — the most important mutation-resistance coverage; without them a priority-order-flip mutation passes.
   - Malformed `packageManager` parametrize (AC-8) covers strings (`"yarn"`, `"yarn@"`, `"yarn@xyz"`, `"yarn@1"`, `"yarn@2"`, `"yarn@2x"`, `"yarn@123abc"`, `"yarn@1x.0"`) AND non-string types (missing, `None`, `42`, `[]`, `{}`, `""`, `True`). String-yarn-shaped emits the warning; non-string types do not.
   - Hypothesis property test (AC-13) over (`packageManager` strategy × marker-powerset strategy) pinning the priority invariant.
   - Schema rejection test (AC-12) using the real `codegenie.schema.validator.validate` entry point.
   - Lockfile-body-ignored regression test (AC-22).
   - Absent-warning assertions on every positive-case test (AC-21).
   - Cross-manager disagreement test (AC-9b).
   - One integration test runs the full gather on each of the three yarn fixtures and asserts the final `repo-context.yaml` shape.
6. **Golden updates.** Run the test suite; update any failing golden files; commit the golden diff as part of the same PR.

## TDD plan — red / green / refactor

### Red phase (write all failing tests first; each must fail for the right reason)

| Test | Asserts | Fixture |
|---|---|---|
| `test_schema_enum_excludes_bare_yarn` | Real `codegenie.schema.validator.validate(...)` rejects `package_manager: "yarn"`; accepts `yarn-classic`, `yarn-berry`. **AC-12** | n/a (synthetic envelope through the real validator entry point) |
| `test_yarn_classic_from_packagemanager_v1` | `package_manager == "yarn-classic"` for `packageManager: "yarn@1.22.19"`; both `yarn_variant_inferred` AND `package_manager_field_unparseable` are **absent** from `build_system.warnings` (AC-21). **AC-2** | `node_yarn_legacy/` (extended with `packageManager` field) |
| `test_yarn_classic_from_packagemanager_v1_corepack_integrity` | `yarn-classic` for `packageManager: "yarn@1.22.19+sha224.abcd"` (Corepack integrity suffix); no warnings (AC-21). **AC-2** | `tmp_path` |
| `test_yarn_berry_from_packagemanager_v3` | `"yarn-berry"`; no warnings (AC-21). **AC-3** | `node_yarn_berry_nonpnp/` |
| `test_yarn_berry_from_packagemanager_v4` | `"yarn-berry"`; no warnings (AC-21). **AC-3** | `node_yarn_berry_pnp/` |
| `test_yarn_berry_from_packagemanager_v10_property` | Hypothesis: random major ∈ [2, 99] (e.g. `yarn@10.0.0`, `yarn@42.1.0`) → `"yarn-berry"`; major == 1 → `"yarn-classic"`. Catches the hardcoded-`{2,3,4}` mutation. **AC-3** | `tmp_path` + hypothesis strategies |
| `test_yarn_berry_from_yarnrc_yml` | `"yarn-berry"`; no warnings. Precondition: `yarn.lock` is the only lockfile (so yarn wins precedence). **AC-4** | `tmp_path` |
| `test_yarn_berry_from_yarn_dir` | `"yarn-berry"`; no warnings; only `.yarn/` directory present (not `.yarnrc.yml`). **AC-5** | `tmp_path` |
| `test_yarn_berry_from_pnp_cjs` | `"yarn-berry"`; no warnings; only `.pnp.cjs` present. **AC-6** | `node_yarn_berry_pnp/` |
| `test_yarn_berry_from_pnp_loader_mjs` | `"yarn-berry"`; no warnings; only `.pnp.loader.mjs` present (no `.pnp.cjs`). **AC-6** | `tmp_path` |
| `test_priority1_classic_wins_over_yarnrc_yml` | `packageManager: "yarn@1.22.19"` + `.yarnrc.yml` + `yarn.lock` → `"yarn-classic"`; no warnings. Catches priority-order-flip mutation. **AC-16** | `tmp_path` |
| `test_priority1_classic_wins_over_pnp_cjs` | `packageManager: "yarn@1.22.19"` + `.pnp.cjs` + `yarn.lock` → `"yarn-classic"`; no warnings. Catches a different priority-flip mutation. **AC-16** | `tmp_path` |
| `test_priority3_yarnrc_yml_wins_over_yarn_dir_and_pnp` | `.yarnrc.yml` + `.yarn/` + `.pnp.cjs` + `yarn.lock` (no `packageManager`) → `"yarn-berry"`; no warnings. Removing `.yarnrc.yml` still produces berry via priority 4; removing `.yarn/` too still produces berry via priority 5. **AC-17** | `tmp_path` (constructs the three sub-cases) |
| `test_yarn_classic_safe_default_emits_warning` | `"yarn-classic"`; `node_build_system.yarn_variant_inferred` in `build_system.warnings` (not `ProbeOutput.warnings`). **AC-7, AC-20** | `tmp_path`: only `yarn.lock`, no other markers, no `packageManager` |
| `test_packagemanager_malformed_strings_param` | Parametrized: `"yarn"`, `"yarn@"`, `"yarn@xyz"`, `"yarn@1"`, `"yarn@2"`, `"yarn@2x"`, `"yarn@123abc"`, `"yarn@1x.0"` — all emit `package_manager_field_unparseable` AND fall through to marker detection (when `.yarnrc.yml` present, result is `yarn-berry`; otherwise safe-default `yarn-classic` with both warnings present). **AC-8** | `tmp_path` |
| `test_packagemanager_non_string_param` | Parametrized: missing field, `None`, `42`, `[]`, `{}`, `""`, `True`, `False` — fall through with **no** `package_manager_field_unparseable` warning (absence is normal). **AC-8** | `tmp_path` |
| `test_cross_manager_declaration_disagreement` | `packageManager: "pnpm@8.0.0"` + only `yarn.lock` + no Berry markers → `yarn-classic` via safe-default + BOTH `package_manager.declaration_lockfile_disagree` AND `node_build_system.yarn_variant_inferred` in `build_system.warnings`; NO `package_manager_field_unparseable` (the field parsed cleanly). **AC-9b** | `tmp_path` |
| `test_npm_unaffected_by_variant_detection` | `package_manager == "npm"` even if `.yarnrc.yml` / `.yarn/` / `.pnp.cjs` are also present (legacy Berry config left over from a migration). No `yarn_variant_*` or `package_manager_field_unparseable` warnings. **AC-9** | `tmp_path` |
| `test_pnpm_higher_precedence_skips_variant_detection` | Both `pnpm-lock.yaml` AND `yarn.lock` + `.yarnrc.yml` + `.pnp.cjs` → `package_manager == "pnpm"`; `multi_lockfile` warning present; NO `yarn_variant_*` warnings. Pins the "variant detection only runs when yarn.lock wins" precondition. **AC-4 precondition, AC-9** | `tmp_path` |
| `test_lockfile_body_ignored_by_variant_detection` | `# yarn lockfile v1\n` (Classic header) in `yarn.lock` + `.yarnrc.yml` → `yarn-berry`. Pins "markers, not lockfile body" intent against a future "improvement". **AC-22** | `tmp_path` |
| `test_property_priority_invariant` | Hypothesis: for any `(packageManager string ∈ valid+malformed set, marker_set ∈ powerset({.yarnrc.yml, .yarn, .pnp.cjs, .pnp.loader.mjs}))`, assert: (a) result ∈ `{"yarn-classic","yarn-berry"}`, (b) same inputs → same output, (c) priority-1-positive forces classic regardless of markers, (d) priority-2-positive forces berry regardless of markers, (e) removing a strictly-lower-priority marker does not change the result when a higher-priority signal is present (metamorphic). Catches constant-return AND priority-flip mutants. **AC-13** | `tmp_path` + hypothesis strategies |
| `test_berry_markers_priority_anchor` | `assert _BERRY_MARKERS[0][0] == ".yarnrc.yml"` — verifies the import-time discipline assertion is present and aligned with AC-19. **AC-18, AC-19** | n/a (introspection) |
| `test_new_warning_ids_in_registry` | Both `node_build_system.yarn_variant_inferred` and `node_build_system.package_manager_field_unparseable` are members of `_WARNING_IDS`. **AC-19** | n/a (introspection) |
| `test_lockfile_tuple_shape_preserved` | `_LOCKFILE_PRECEDENCE` is a 4-tuple; the index-`[2]` entry's first element is `"yarn.lock"`. Comment / docstring at the line names the override. **AC-14** | n/a (introspection) |

Run the tests. Confirm every one fails for the right reason (the executor verifies that any pre-existing red-phase test still asserts intent; tests that pass against a constant-return mutant must be strengthened before the green phase, per Rule 9).

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

- **Yarn Berry's lockfile *parsing*.** That belongs to S3-03 (`_yarn.py`). This story changes detection of the package manager only, not parsing. **Correction (2026-05-14):** the original prose here said *"S3-03 must now branch on `yarn-classic` vs `yarn-berry` when choosing a parser"* — but the hardened S3-03 story (commit `3ada173`) chose a **unified** parser that dispatches on `_HAS_PYARN` (whether `pyarn` is importable) rather than on variant. The hand-rolled scanner inside `_yarn.py` handles both the Classic format and the Berry YAML-ish format. The gather-layer variant split this story lands therefore feeds the **Planner / Supervisor dispatch** (production ADR-0031), not the parser. ADR-0013's Consequences §2 ("S3-03 must branch on variant") should be amended to reflect this; tracked as a follow-up in `_validation/S2-02a-yarn-variant-detection.md`.
- **Bun version variants.** Bun is a single family today; no architectural fork worth splitting on.
- **pnpm version variants.** pnpm v6–v9 are forward-compatible enough at the plugin level; one family.
- **npm v6 vs v7+.** Lockfile-version differences live in `S3-05` (NodeManifest) cross-check, not here.
- **Schema migrations for already-emitted data.** The probe shipped this week (commit `8c8ad84`); no production data exists at the old value space. The migration is the new-fixture additions + golden updates in this PR.
- **Plugin-side adapters.** `yarn-classic` and `yarn-berry` will register different `dep_graph` adapters per ADR-0032, but the adapter implementations land in Phase 3 plugins, not here.

## Notes for implementer

- **The Open/Closed seam is the design point — two layers of it.** Two parallel tuples now exist: `_LOCKFILE_PRECEDENCE` (unchanged shape; index-`[2]` is the override point for `yarn`) and `_BERRY_MARKERS` (new; the priority-ordered Berry filesystem-marker registry). Both are module-level `Final[tuple[...]]` with import-time discipline asserts (AC-19). Adding a future variant signal is one entry in `_BERRY_MARKERS` — never an edit to `_detect_yarn_variant`'s control flow. Adding a hypothetical future Yarn 5 variant is one branch in the major-version check at the top of `_detect_yarn_variant` — never an edit to `_LOCKFILE_PRECEDENCE`. Two seams, both observable by AC.
- **`.yarnrc.yml` vs `.yarnrc`.** Note the file extension. `.yarnrc.yml` is **Berry-only**; `.yarnrc` is the deprecated Classic config. Don't confuse them. A repo with both (mid-migration) is covered by AC-4: `.yarnrc.yml` wins; the legacy `.yarnrc` is not consulted for detection.
- **Yarn Berry without PnP.** Berry supports `nodeLinker: node-modules` (in `.yarnrc.yml`) which means no `.pnp.cjs`. The `node_yarn_berry_nonpnp/` fixture covers this case — Berry the package manager, but Classic-style resolution. The plugin distinction is still Berry because the *manager* differs, even though the resolution model matches Classic. This is intentional: plugins are scoped on the manager, not on the resolution model.
- **`packageManager` regex.** Anchor: `^yarn@(\d+)\.`. The trailing `\.` is load-bearing — it disambiguates fully-formed `yarn@1.x` (Classic) from the under-specified `yarn@1` (which falls through to AC-8 as unparseable). Pre-release suffixes (`yarn@4.0.0-rc.42`) and Corepack integrity suffixes (`yarn@4.5.0+sha224.abcd`) match the anchor cleanly.
- **Confidence accounting (asymmetry rationale).** Priorities 1–5 yield definitive detection → the probe's overall `confidence` field is unaffected. Priority 6 (safe-default classic) is *medium* confidence in the variant dimension, but does **not** demote the overall `confidence` field — the warning IS the confidence signal at this layer. This is asymmetric with `multi_lockfile`, which DOES demote to `"low"`. Rationale: variant ambiguity is a **secondary** dimension under a CERTAIN package-manager family (`yarn.lock` is the winning lockfile — that part is unambiguous). `multi_lockfile` is ambiguity in the PRIMARY family resolution, which is why it demotes. If a future plugin needs the medium-confidence variant signal to gate behavior, query `"node_build_system.yarn_variant_inferred" in build_system.warnings`, not the overall `confidence`.
- **Warning emission target.** Both new warnings (`yarn_variant_inferred`, `package_manager_field_unparseable`) match the ADR-0007 pattern and are added to the probe's `_WARNING_IDS` frozenset (AC-19) so the existing import-time regex assertion covers them. They land in `build_system.warnings` (the slice's warnings list), NOT on `ProbeOutput.warnings` (which remains `[]` per the shipped S2-02 convention).
- **No new dependencies.** This story adds zero runtime dependencies. The regex is stdlib `re`; `pathlib.Path.exists()` / `.is_dir()` are stdlib. No `yaml.load` of `.yarnrc.yml` needed for detection — its mere *existence* is the signal.
- **Functional-core / imperative-shell opportunity (Notes only — not an AC).** The shipped `_detect_yarn_variant(repo_root, parsed_manifest)` performs `Path.exists()` / `.is_dir()` calls inline. A purer alternative takes a pre-computed `present_berry_markers: frozenset[str]` and returns a pure function of (`packageManager` string, marker set). This makes the chooser hypothesis-friendly without `tmp_path` and decouples I/O from logic (functional core / imperative shell). Rule 2 tension: at one caller and ~30 LOC, the current shape is fine — surface only if a second consumer appears (e.g., the Phase 8 Supervisor wants to re-run the chooser against a hypothetical marker set). Don't refactor prematurely.
- **Primitive obsession (Notes only).** `Literal["yarn-classic", "yarn-berry"]` is the current return-type. With S3-03 dispatch + Phase 8 Supervisor dispatch reading the value, ≥ 3 module boundaries will share it. If a third real consumer crystalizes, lift to `class PackageManager(StrEnum)` in a single shared module (`codegenie.probes.types`) — not retrofitted per-call-site. CLAUDE.md "Newtype pattern for every domain primitive" applies once the rule-of-three threshold is met; right now, `Literal[...]` is enough.
- **Local-dev cache invalidation.** Existing `.codegenie/cache/` entries written before the `$id` `v0.2.0` bump will fail schema validation on next gather and be silently rebuilt. No production data exists at the old value space (probe shipped this week, no external consumers). Document this in the PR description so a teammate who pulls and re-runs locally is not surprised by a one-time cache-rebuild stall.
- **Schema `$id` increment — deferred policy gap.** ADR-0004 explicitly defers sub-schema versioning policy to Phase 2 ("No release-versioning policy for sub-schemas is introduced in Phase 1"). ADR-0013 unilaterally chose `v0.1.0 → v0.2.0`. The removal of `"yarn"` from the enum is arguably MAJOR semver (old envelopes become invalid; AC-12 makes the breaking nature explicit). When Phase 2 ratifies the policy, revisit whether this bump should retroactively be re-tagged `v1.0.0` and the policy clarified. Not blocking — accept as a known gap.
