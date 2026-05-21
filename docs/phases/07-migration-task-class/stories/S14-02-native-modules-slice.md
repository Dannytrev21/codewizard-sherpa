# Story S14-02 — `NodeManifestProbe` native-module-artifact slice extension (additive `native_module_artifacts` field)

**Step:** Step 14 — Build-toolchain classification + native modules (G3)
**Status:** Ready
**Effort:** M
**Depends on:** S14-01 (the build-toolchain classification catalogs + loader — the multi-stage recipe consumes *both* S14-01's catalogs and this story's slice field; the two Step-14 stories ship the G3 gather pair together)
**ADRs honored:** Phase 7 ADR-0020 (build-time-only toolchain vs runtime libraries — §Decision: "The `NodeManifestProbe` slice gains an additive field … Each `NativeModule` records the detection signal (`binding.gyp`, a `*.node` artifact, or a `node-gyp` dependency in the resolved tree)"), Phase 7 ADR-0029 (the byte-edit allowlist enumerates every Amendment-A source-file addition — §Decision row 6: "The `NodeManifestProbe` slice schema — gains exactly one additive field … (ADR-0020)" — this story's edit to `node_manifest.py` and its sub-schema rides that pre-permitted allowlist row), production ADR-0007 (the frozen Probe ABC is preserved POC→service — extension is by additive field, never an ABC edit), Phase 1 ADR-0004 (per-probe sub-schema `additionalProperties: false` at every node — the additive field is wired with that strictness preserved)

## Context

`final-design.md §Amendment A §A.2` gap G3: the multi-stage refactor recipe must select a builder stage when, and only when, the source repo's dependency tree contains **native modules** — packages with a compiled-C/C++/Rust component that `node-gyp` (or `prebuild`/`node-pre-gyp`) builds against headers. A pure-JavaScript dependency tree needs no compiler and no `*-dev` builder image; a native-module tree forces a `cgr.dev/chainguard/node:*-dev` builder stage, after which the compiled `node_modules` is `COPY`'d into the distroless runner. ADR-0020 §Context names native modules as "the trigger that forces a builder stage in the first place."

ADR-0020 §Decision resolves G3 with two pieces. S14-01 shipped the first — the `apk`/`apt` build-toolchain classification catalogs. This story ships the second: an **additive field** on the existing `NodeManifestProbe` slice that records the native-module detection signals. ADR-0020 §Decision: "The `NodeManifestProbe` slice gains an additive field … Each `NativeModule` records the detection signal (`binding.gyp`, a `*.node` artifact, or a `node-gyp` dependency in the resolved tree). The slice extension is additive to the existing sub-schema (`additionalProperties: false` preserved) and is enumerated in the ADR-0029 byte-edit allowlist."

**A naming disambiguation the implementer must honor (Rule 7 — surface, do not average).** `NodeManifestProbe`'s `primary` slice block *already* carries a field named `native_modules` — a nested object `{detected: bool, packages: [...]}` from Phase 1 S3-05, ADR-0006. That existing field is a **catalog cross-reference**: it matches resolved dependency *names* against `src/codegenie/catalogs/native_modules.yaml`. It answers "does a *known-native* package name appear in the resolved tree?" — a name-list lookup, not a filesystem-evidence scan. The field this story adds is a **distinct concept**: filesystem-and-tree *evidence* of native compilation — a `binding.gyp` file on disk, a `*.node` build artifact on disk, a `node-gyp` dependency in the resolved tree. Reusing the name `native_modules` for the new field would collide with the S3-05 object and break every existing consumer that reads `primary.native_modules.detected`. **This story therefore names the new field `native_module_artifacts: tuple[NativeModuleArtifact, ...]`** — a new sibling field under `primary`, alongside (not replacing) the existing `native_modules` object. ADR-0020's prose says "`native_modules: tuple[NativeModule, ...]`"; the concrete name `native_module_artifacts` honors ADR-0020's *intent* (an additive tuple field of typed detection records) while respecting the pre-existing S3-05 field — exactly the "surface the conflict, pick the safe name, do not silently shadow" discipline. The story's acceptance criteria pin this name; if a reviewer prefers a different non-colliding name, that is a one-line rename, but the existing `native_modules` object MUST NOT be touched.

This is an **additive schema-field change**, the textbook ADR-0029 row-6 case: the slice gains one field, `additionalProperties: false` is preserved at every node, no existing field is altered, the envelope `$ref` is unchanged (the probe already has a `$ref`). Existing consumers of the slice are unaffected — they never read the new field.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Amendment A §17` — "Build-toolchain classification catalog + native-module slice" — "The `NodeManifestProbe` slice is extended with a `native_modules: tuple[NativeModule, ...]` field (detects `binding.gyp`, `*.node`, `node-gyp` in the resolved tree)." Read with the naming-disambiguation note above.
  - `../final-design.md §Amendment A §A.2` gap G3 row — disposition GATHER, component "`apk/apt` classification catalog + `NodeManifestProbe` native-module slice", ADR 0020, Step 14.
  - `../final-design.md §Amendment A §A.4` — "the gather probes (Steps 13–15) must land *before* the recipe stories (existing Step 10) execute — the recipes consume the new slices." This slice is one of those.
- **Phase ADRs:**
  - `../ADRs/0020-build-toolchain-classification-catalog.md §Decision` — the additive-field decision; §Consequences ("The `NodeManifestProbe` sub-schema gains the additive `native_modules` array; the envelope `$ref` is unchanged"); §Pattern-fit ("The `NativeModule` slice obeys newtype + sum-type domain-modeling discipline; the probe slice extension stays within the frozen Probe ABC — extension by additive field, never an ABC edit"); §Consequences ("Golden fixtures cover a pure-JS project (no builder stage), a native-module project (builder stage selected) …").
  - `../ADRs/0029-amend-byte-edit-allowlist-for-amendment-a.md §Decision row 6` — "The `NodeManifestProbe` slice schema — gains exactly one additive field: `native_modules: tuple[NativeModule, ...]` (ADR-0020)." The byte-edit to `node_manifest.py` and its `.schema.json` is pre-permitted by this row.
- **Production ADRs:**
  - `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — the frozen Probe ABC. The slice extension adds a field to `ProbeOutput.schema_slice`; it does NOT touch the `Probe` ABC, the `run(self, repo, ctx)` signature, or any `ProbeContext` attribute.
- **Sibling stories:**
  - `S14-01-toolchain-classification-catalog.md` — the first Step 14 story; this story depends on it. S14-01 ships the classification catalogs; this story ships the slice field; the multi-stage recipe consumes both.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/probes/node_manifest.py` — the probe this story extends. Read the module docstring, the existing `NativeModuleHit` TypedDict (line ~117), `_cross_reference_native_modules` (line ~301), and the `run()` slice-assembly block (line ~428: `native_hits = _cross_reference_native_modules(...)`, line ~449: `"native_modules": {...}`). The new field is assembled *alongside* the existing `native_modules` object, in the same `primary` block — understand the existing seam before adding to it.
  - `src/codegenie/schema/probes/node_manifest.schema.json` — the sub-schema. The new field is a new property under `primary.properties`, added to `primary.required`. Note `primary.additionalProperties: false` (line ~17) — that strictness is preserved; the new field is what makes the slice still validate.
  - `src/codegenie/probes/_lockfiles/` — the resolved-dependency-tree flatteners (`_pnpm`, `_npm`, `_yarn`). The `node-gyp` detection reads the *resolved* tree these produce; do not re-walk the lockfile.
  - `tests/unit/probes/` — the existing `NodeManifestProbe` test suite. The new field's tests sit alongside; the existing tests must stay green (backward compatibility).
  - `tests/fixtures/portfolio/native-modules/` — an existing fixture with a `binding.gyp`, a `package.json`, a `pnpm-lock.yaml`, and a `src/` directory. This is the native-module fixture AC-2 asserts against; verify it carries a detectable native-module signal (`binding.gyp` is present per the fixture listing).
  - `tests/fixtures/portfolio/minimal-ts/` — a pure-TypeScript fixture with no native modules; the empty-tuple fixture for AC-3.
- **Roadmap context:**
  - `docs/roadmap.md` Phase 7 — the distroless-migration task class; Amendment A deepens its gather pipeline.

## Goal

Extend the existing `NodeManifestProbe` `primary` slice with one additive field, `native_module_artifacts: tuple[NativeModuleArtifact, ...]`, a tuple of frozen typed records each carrying the native-module package name and the detection reason (`binding_gyp`, `node_artifact`, or `node_gyp_dependency`). The field is populated by a pure detection helper that scans the repo snapshot for `binding.gyp` files, `*.node` build artifacts, and a `node-gyp` dependency in the resolved tree. The slice still validates against the updated sub-schema (`additionalProperties: false` preserved), the envelope `$ref` is unchanged, and every existing consumer of the slice — which never reads the new field — is unaffected.

## Acceptance criteria

### The `NativeModuleArtifact` typed record + detection-reason sum type

- [ ] AC-1 — `src/codegenie/probes/node_manifest.py` defines a `NativeModuleArtifact` frozen typed record carrying exactly two fields: `package: str` (the npm package name the artifact belongs to, or the repo-relative path stem when the artifact is not attributable to a single package) and `detection_reason: DetectionReason`. The record is immutable — a frozen Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` if the probe already emits Pydantic records, otherwise a frozen `dataclass` matching the module's existing record convention (the module currently uses `TypedDict` for `NativeModuleHit` — match the surrounding convention unless the slice serialization forces Pydantic; surface the choice in the attempt log per Rule 11).
- [ ] AC-2 — `DetectionReason` is a closed sum type — `Literal["binding_gyp", "node_artifact", "node_gyp_dependency"]` — plus a module-level `Final` frozenset `_NATIVE_MODULE_DETECTION_REASONS` of the three values. No raw `str` for the reason; no fourth value.

### Detection logic — populated correctly on a native-module repo

- [ ] AC-3 — A pure module-level helper `_detect_native_module_artifacts(repo: RepoSnapshot, resolved: Mapping[str, str]) -> tuple[NativeModuleArtifact, ...]` scans for three signals and returns one `NativeModuleArtifact` per distinct detected signal: (a) every `binding.gyp` file in the snapshot → reason `binding_gyp`; (b) every `*.node` file in the snapshot → reason `node_artifact`; (c) `node-gyp` present in the resolved-dependency mapping → one record with reason `node_gyp_dependency`. The helper is pure (no I/O beyond the snapshot it is handed) and is AST-walk-testable (functional-core discipline).
- [ ] AC-4 — On `tests/fixtures/portfolio/native-modules/` the probe emits a non-empty `native_module_artifacts` tuple: at minimum one record with `detection_reason == "binding_gyp"` (the fixture ships a `binding.gyp`). The test asserts the specific reason value, not merely a non-empty tuple — a test that only checks `len(...) > 0` would pass even if every record were mis-tagged.
- [ ] AC-5 — On `tests/fixtures/portfolio/minimal-ts/` (a pure-TypeScript fixture with no `binding.gyp`, no `*.node`, no `node-gyp` dependency) the probe emits `native_module_artifacts == ()` — an empty tuple, not a missing field, not `None`. The test asserts exact equality with the empty tuple.
- [ ] AC-6 — The detection helper produces a deterministic, stably-ordered tuple: artifacts are sorted by `(repo-relative path, detection_reason)` so two runs over the same snapshot emit byte-identical slices (determinism is load-bearing for the content cache and golden fixtures). A unit test runs the helper twice on the same snapshot and asserts tuple equality.
- [ ] AC-7 — `node-gyp` detection reads the **resolved dependency mapping** the existing lockfile flatteners (`_flatten_pnpm` / `_flatten_npm` / `_flatten_yarn`) already produce — it does NOT re-parse the lockfile and does NOT shell out to `npm ls` (ADR-0011 carry-forward). A unit test feeds a resolved mapping containing `node-gyp` and asserts exactly one `node_gyp_dependency` record; a mapping without it yields zero such records.

### Sub-schema extension — additive, strictness preserved

- [ ] AC-8 — `src/codegenie/schema/probes/node_manifest.schema.json` gains `native_module_artifacts` as a new property under `primary.properties`, and the string `"native_module_artifacts"` is appended to `primary.required`. The property is an `array` of objects; each object has `additionalProperties: false`, `required: ["package", "detection_reason"]`, `package` a `string`, `detection_reason` an `enum` of exactly `["binding_gyp", "node_artifact", "node_gyp_dependency"]`.
- [ ] AC-9 — `primary.additionalProperties` stays `false`; every nested node added stays `additionalProperties: false` (Phase 1 ADR-0004). The pre-existing `native_modules` object under `primary` is **byte-unchanged** — its `properties`, `required`, and `additionalProperties` are not touched.
- [ ] AC-10 — The envelope schema `src/codegenie/schema/repo_context.schema.json` is **not edited** — `NodeManifestProbe` already carries a `$ref` to its sub-schema; an additive field inside the sub-schema needs no envelope change (ADR-0020 §Consequences: "the envelope `$ref` is unchanged").
- [ ] AC-11 — A test validates a real `NodeManifestProbe` slice (the one emitted on the `native-modules` fixture) against the updated sub-schema and asserts it passes; a test validates a hand-built slice carrying a `native_module_artifacts` entry with a fourth, unknown `detection_reason` value and asserts schema validation *fails* (the `enum` is the closed-set guard at the schema layer).

### Backward compatibility — existing consumers unaffected

- [ ] AC-12 — Every pre-existing `NodeManifestProbe` unit / integration / golden test stays green with no edit other than (where a golden fixture pins the full slice JSON) the additive `native_module_artifacts` key appearing in the regenerated golden. No existing assertion on `primary.native_modules`, `primary.direct_dependencies`, `primary.lockfile`, or any other field changes value.
- [ ] AC-13 — A test asserts the slice round-trips: a slice emitted *before* this story (a fixture JSON without `native_module_artifacts`) is NOT a valid input to the updated schema (the field is `required`) — confirming the field is genuinely required, not silently optional — AND the probe, after this story, always emits the field (empty tuple when nothing is detected), so the probe's own output always satisfies the updated schema. (This pins the "additive-but-required, probe always emits it" contract — the field is required at the schema and the probe is the only producer, so no live slice ever lacks it.)
- [ ] AC-14 — The Phase 1 / Phase 2 probe-contract fence (`tests/unit/test_probe_contract.py`) and the structural fences under `tests/fence/` stay green — the slice extension adds a field to `ProbeOutput.schema_slice` only; it does not touch the `Probe` ABC, the `run(self, repo, ctx)` signature, `ProbeContext`, or the registry.

### Strict typing + structural conformance

- [ ] AC-15 — `mypy --strict src/codegenie/probes/node_manifest.py` clean. No `Any` introduced; `tuple[NativeModuleArtifact, ...]` is the field type; the detection helper is fully typed.
- [ ] AC-16 — `ruff format`, `ruff check`, `make lint-imports` all green. No new import is added that crosses an architectural boundary; the detection helper uses only `RepoSnapshot`, `pathlib`, and the existing `_lockfiles` resolved mapping.
- [ ] AC-17 — `make check` green (full local gate including the Phase 3–6.5 regression suite — hard pre-merge gate per Phase 7 ADR-0009).
- [ ] AC-18 — The byte-edit allowlist fence (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) reports the edits to `src/codegenie/probes/node_manifest.py` and `src/codegenie/schema/probes/node_manifest.schema.json` as **permitted** — they ride ADR-0029 row category 6 (the `NodeManifestProbe` slice additive field). The fence does NOT fire; if it does, ADR-0029 row 6 did not land (S13-03's job) and that is the conversation to surface (Rule 12), not a reason to silently add a row.

## Implementation outline

1. **Read `node_manifest.py` end to end.** Understand the existing `NativeModuleHit` TypedDict, `_cross_reference_native_modules`, and the `run()` slice-assembly that builds `primary.native_modules`. The new field is assembled in the *same* `primary` block; do not disturb the existing `native_modules` object.
2. **Confirm the ADR-0029 row-6 allowlist entry exists.** `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` must already enumerate the `NodeManifestProbe` slice additive-field row (S13-03's job). If absent, this story is blocked on S13-03 — surface, do not add the row here.
3. **Define `DetectionReason` + `NativeModuleArtifact`.** `DetectionReason = Literal["binding_gyp", "node_artifact", "node_gyp_dependency"]`; `_NATIVE_MODULE_DETECTION_REASONS: Final[frozenset[str]] = frozenset({...})`. `NativeModuleArtifact` as a frozen record matching the module's convention (TypedDict-vs-Pydantic-vs-dataclass — pick to match the surrounding code and the slice-serialization need; document the choice in the attempt log).
4. **Implement `_detect_native_module_artifacts(repo, resolved)`.** Pure helper: glob the snapshot for `**/binding.gyp` and `**/*.node`; check `"node-gyp" in resolved`; build one record per signal; sort by `(path, detection_reason)` for determinism; return the tuple. No I/O beyond the snapshot.
5. **Wire the field into `run()`.** In the `primary` slice-assembly block, call `_detect_native_module_artifacts(...)` and add `"native_module_artifacts": [...]` (serialized records) to the `primary` mapping, alongside the existing `native_modules` object.
6. **Extend the sub-schema.** Add `native_module_artifacts` to `primary.properties` and to `primary.required` in `node_manifest.schema.json`. The array's item schema: `additionalProperties: false`, `required: ["package", "detection_reason"]`, `detection_reason` an `enum` of the three values. Leave the existing `native_modules` object byte-unchanged. Leave `repo_context.schema.json` untouched.
7. **Write the new tests.** Native-module fixture → non-empty tuple with `binding_gyp` reason (AC-4); pure-JS fixture → empty tuple (AC-5); determinism double-run (AC-6); `node-gyp`-in-resolved-mapping unit test (AC-7); schema-validation pass on a real slice and fail on a bad `detection_reason` (AC-11); the additive-but-required round-trip contract test (AC-13).
8. **Regenerate any golden fixtures.** Where a golden test pins the full `NodeManifestProbe` slice JSON, regenerate it so the additive key appears. Confirm no other key changed value (AC-12).
9. **Run `make check`.** Confirm the Phase 3–6.5 regression suite, the probe-contract fence, and the byte-edit allowlist fence are all green.

## TDD plan — red / green / refactor

### Red — failing test first

Author `tests/unit/probes/test_node_manifest_native_module_artifacts.py::test_native_module_fixture_emits_binding_gyp_artifact` BEFORE the field exists:

```python
from pathlib import Path

from codegenie.probes.node_manifest import NodeManifestProbe
# ... existing test harness imports for building a RepoSnapshot + ProbeContext


async def test_native_module_fixture_emits_binding_gyp_artifact() -> None:
    """A repo with a binding.gyp on disk must surface a native_module_artifacts
    record tagged `binding_gyp` — this is the signal the multi-stage recipe
    keys the `*-dev` builder-stage decision on (ADR-0020 §Decision). A pure-JS
    repo would not need a builder stage; mis-detecting here ships a broken
    image."""
    fixture = Path("tests/fixtures/portfolio/native-modules")
    output = await _run_node_manifest_probe(fixture)  # existing harness helper
    primary = output.schema_slice["manifests"]["primary"]
    artifacts = primary["native_module_artifacts"]
    reasons = {a["detection_reason"] for a in artifacts}
    assert "binding_gyp" in reasons, (
        f"expected a binding_gyp artifact on the native-modules fixture, "
        f"got reasons={reasons}"
    )
```

Run: `pytest tests/unit/probes/test_node_manifest_native_module_artifacts.py -x` — expect a `KeyError: 'native_module_artifacts'` (the field is not in the slice yet). This is the red bar. The test encodes *intent* — the `binding_gyp` reason is the load-bearing builder-stage trigger, not an incidental detail — so it would fail if the field were emitted but always empty, or if `binding.gyp` detection were dropped.

### Green — minimum code

Define `DetectionReason` + `NativeModuleArtifact`, implement `_detect_native_module_artifacts`, wire it into `run()`, extend the sub-schema. Re-run the test. Iterate until green. Then add the empty-tuple (AC-5), determinism (AC-6), `node-gyp`-mapping (AC-7), schema-validation (AC-11), and round-trip-contract (AC-13) tests one at a time; each becomes red, then green.

### Refactor

- Confirm `_detect_native_module_artifacts` is pure and AST-walk-testable — no `open()`, no `os.walk` outside the handed snapshot. The functional-core discipline is enforced by AST tests in sibling probes; match it.
- Confirm the record-type choice (TypedDict vs frozen Pydantic vs frozen dataclass) matches the module's surrounding convention — `NodeManifestProbe` currently uses `TypedDict` for `NativeModuleHit`; a `TypedDict` for `NativeModuleArtifact` keeps the module internally consistent (Rule 11). Document the call in `_attempts/S14-02.md`.
- Confirm the sort key `(path, detection_reason)` makes the tuple deterministic; if a snapshot can carry two `binding.gyp` files at the same path (it cannot), the tie-break is moot — the key is total.
- Confirm the existing `native_modules` object is byte-identical to its pre-story form — diff `node_manifest.schema.json` and verify only the additive property + the one `required` array element changed.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/node_manifest.py` | **Edit (additive — ADR-0029 row 6).** Add `DetectionReason`, `_NATIVE_MODULE_DETECTION_REASONS`, `NativeModuleArtifact`, the pure `_detect_native_module_artifacts` helper, and the `native_module_artifacts` key in the `primary` slice-assembly block. The existing `native_modules` object is untouched. |
| `src/codegenie/schema/probes/node_manifest.schema.json` | **Edit (additive — ADR-0029 row 6).** Add `native_module_artifacts` to `primary.properties` and `primary.required`; `additionalProperties: false` and the closed `detection_reason` enum preserved. The existing `native_modules` object is byte-unchanged. |
| `tests/unit/probes/test_node_manifest_native_module_artifacts.py` | **New.** Native-module-fixture detection, pure-JS empty tuple, determinism double-run, `node-gyp`-in-resolved-mapping, schema-validation pass/fail, additive-but-required round-trip contract. |
| `tests/golden/probes/node_manifest/*` (if a golden pins the full slice) | **Edit (regenerate).** The additive `native_module_artifacts` key appears in the regenerated golden; no other key changes value. |
| `_attempts/S14-02.md` | **New.** Append-only attempt log: the record-type choice (TypedDict vs Pydantic), the AC-18 byte-edit-fence-permitted note, the golden-regeneration diff. |

**Other Phase 0–6.5 files:** none edited. The two edits above are the only byte-edits, both pre-permitted by ADR-0029 row category 6.

## Out of scope

- **The build-toolchain classification catalogs.** S14-01's job — already shipped. This story ships only the native-module-artifact slice field; the multi-stage recipe consumes both.
- **The multi-stage refactor recipe's builder-stage selection.** `DockerfileMultiStageRefactorTransform` (design-of-record §10) reads `native_module_artifacts` (non-empty → select the `cgr.dev/chainguard/node:*-dev` builder image) and the S14-01 catalogs; that consumption is the recipe story's job, not this one.
- **Touching the existing `native_modules` catalog-cross-reference object.** Phase 1 S3-05 / ADR-0006 owns that field. This story adds a *sibling* field; it does not refactor, merge, or rename the existing one. Conflating the two concepts would break every existing consumer of `primary.native_modules`.
- **Parsing `binding.gyp` contents or compiling anything.** Detection is presence-of-signal only — a `binding.gyp` *exists*, a `*.node` *exists*, `node-gyp` *is in the resolved tree*. The probe reports the fact; it does not interpret the gyp file or run a build (facts-not-judgments).
- **`prebuild` / `node-pre-gyp` / `prebuildify` detection beyond `node-gyp`.** The three signals in AC-3 are the ADR-0020-named set. Additional native-build toolchains are a catalog-curation / future-ADR conversation, not this story.
- **Detecting native modules in non-Node ecosystems.** `NodeManifestProbe` is Node-only by its `_admits_node_project` language filter; this story does not widen that.

## Notes for the implementer

- **The naming-disambiguation is the load-bearing decision of this story.** `primary` already has a `native_modules` object (S3-05 catalog cross-reference). The new field MUST be a distinct name — this story pins `native_module_artifacts`. Reusing `native_modules` would shadow the S3-05 object and break `primary.native_modules.detected` consumers. ADR-0020's prose says `native_modules: tuple[NativeModule, ...]`; that is the *intent* (an additive tuple of typed detection records), and `native_module_artifacts` honors the intent without the collision. This is Rule 7 in action — surface the conflict, pick the safe name, do not silently average two fields into one.
- **Two `native_modules`-flavored fields, two distinct questions.** The old `native_modules` object answers "is a *known-native package name* in the resolved tree?" (a name-list lookup against `catalogs/native_modules.yaml`). The new `native_module_artifacts` answers "is there *filesystem/tree evidence* of native compilation here?" (`binding.gyp` on disk, `*.node` on disk, `node-gyp` dependency). They can disagree — a repo can vendor a `binding.gyp` for a package not in the catalog, or list a catalog-known package that ships only prebuilt binaries. Both signals are useful; the recipe reads `native_module_artifacts` for the builder-stage decision.
- **`additionalProperties: false` is preserved, not relaxed.** Phase 1 ADR-0004 requires it at every node. The additive field is a new property *inside* the strict object; it does not change the strictness. Adding the field to `primary.required` (not leaving it optional) is deliberate — the probe is the only producer and always emits it (empty tuple when nothing is detected), so making it required keeps the schema honest about what a live slice always contains (AC-13).
- **The detection helper is pure — functional-core discipline.** `_detect_native_module_artifacts` takes the `RepoSnapshot` and the resolved mapping and returns a tuple. No `open()`, no `os.walk` outside the snapshot, no shelling out. `run()` stays the only impure code. Sibling probes enforce this with AST-walking tests; match the convention.
- **`node-gyp` detection reads the resolved tree, never `npm ls`.** ADR-0011 carry-forward: no `npm ls`, no `bun.lockb` parse. The lockfile flatteners (`_flatten_pnpm` / `_flatten_npm` / `_flatten_yarn`) already produce a `Mapping[str, str]` of resolved package → version; `"node-gyp" in resolved` is the check. Do not re-parse the lockfile for this.
- **Determinism is load-bearing.** The slice flows into the content cache and golden fixtures; two runs over the same snapshot must emit byte-identical slices. Sort the artifact tuple by `(repo-relative path, detection_reason)`. A filesystem glob's iteration order is not guaranteed — sort explicitly.
- **Match the module's record convention.** `node_manifest.py` uses a `TypedDict` (`NativeModuleHit`) for its existing native-module records. A `TypedDict` for `NativeModuleArtifact` keeps the module internally consistent (Rule 11 — conform to the local convention even if a frozen Pydantic model is your taste). If the slice-serialization path forces Pydantic, surface that and document it in the attempt log rather than forking the convention silently.
- **The byte-edit is pre-permitted, not amended here.** ADR-0029 §Decision row 6 already names "the `NodeManifestProbe` slice schema — gains exactly one additive field." S13-03 lands that allowlist row. This story consumes it. Do NOT add an allowlist row in this story — if the byte-edit fence flags `node_manifest.py` or its schema, S13-03's row did not land and that is the conversation to surface (Rule 12).
- **Extension by addition, never an ABC edit.** Production ADR-0007 freezes the `Probe` ABC. This story adds a field to `ProbeOutput.schema_slice` — it does NOT touch `base.py`, the `run(self, repo, ctx)` signature, `ProbeContext`, or the registry. The probe-contract fence (`tests/unit/test_probe_contract.py`) stays green precisely because nothing in the frozen contract moved.
- **Regenerate goldens, verify nothing else moved.** If a golden test pins the full `NodeManifestProbe` slice JSON, the additive key will appear on regeneration — that is expected. Diff the regenerated golden and confirm *only* `native_module_artifacts` is new and no existing key's value changed. A changed existing value means the additive field leaked into existing logic — a bug, not a golden refresh.
