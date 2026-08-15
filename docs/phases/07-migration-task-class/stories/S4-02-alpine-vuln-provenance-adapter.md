# Story S4-02 — `AlpineVulnProvenanceAdapter` + plugin tree scaffolding

**Step:** Step 4 — `AlpineVulnProvenanceAdapter` + `DistrolessVulnProvenanceAdapter` + `sbom_verifier.py`
**Status:** HARDENED (phase-story-validator, 2026-08-14 — pre-executor pass; see `_validation/S4-02-alpine-vuln-provenance-adapter.md`)
**Effort:** M
**Depends on:** S2-04 (`assemble_provenance` + `_ADAPTER_DISPATCH_ORDER`), S4-01 (`sbom_verifier.py`)
**ADRs honored:** Phase 7 ADR-0004 (primitive home — adapter lives under the plugin, NOT in `src/codegenie/primitives/`), Phase 7 ADR-0005 (plugin-contributed surface — `plugins/distroless-migration--node--npm/` tree bootstrapped here), Phase 7 ADR-0007 (registry stores classes, not instances; `__init__` accepts DI kwargs from the closed set — **this story amends the set with one entry, `base_image_slice_provider`**), Phase 7 ADR-0009 (byte-edit allowlist — this story adds an entire new plugin tree which is additive-only by definition; the two Phase-7-owned kernel edits below — `_DI_KWARGS` +1 entry, `UnknownReason` +2 members — are additive extensions to Phase 7 files, not byte-edits to Phase 0–6.5 locked files)

## Validation notes (2026-08-14)

Four **BLOCK-severity** structural issues were resolved without changing the story's goal or scope:

1. **Kernel Protocol collision** — original AC-7 added `repo_context: RepoContext` as a fifth keyword-only kwarg on `attribute(...)`. The shipped Protocol (`src/codegenie/primitives/vuln_provenance/protocols.py`) is frozen at **four positional args** (`cve_id, package_id, image_ref, sbom`) and `assemble_provenance` (S2-04) calls it positionally with those four args. Adding a fifth kwarg would either break every existing adapter (`NpmVulnProvenanceAdapter`) or force a byte-edit to `assembly.py`. Resolution: the `BaseImageProbe` slice is read via a **DI-injected `base_image_slice_provider`** on `__init__` (Phase 7 ADR-0007 amendment — one new entry in the closed `_DI_KWARGS` set). Protocol signature unchanged. Production wiring of the provider lands with the plugin loader (S8-03).
2. **`AdapterConfidence.LOW` does not exist** — original AC-8 branched on `HIGH` vs `LOW`. Shipped `AdapterConfidence` (`types.py`) is `HIGH | DEGRADED | UNAVAILABLE`. Compounded by a semantic error: `confidence()` per the Protocol docstring is **adapter-class-level static** (used by the dispatch tie-breaker), NOT per-call state. Per-call confidence lives on the returned `BaseImage.confidence` field. Resolution: `confidence()` returns static `AdapterConfidence.HIGH`; `BaseImage.confidence` is populated per-call on successful attribution.
3. **`UnknownReason` attribute-access syntax vs closed `Literal[...]` shape** — every original AC used `UnknownReason.SBOM_LAYER_ATTRIBUTION_ABSENT` (enum syntax). Shipped `UnknownReason` is a `Literal["sbom_layer_attribution_absent", "no_adapter_resolved", "adapter_error", "base_image_already_distroless", "build_failed", "dockerfile_parse_failed"]` — string values, not enum members. Compounded by two missing values: `"base_image_probe_absent"` and `"base_image_not_alpine"` are not in the shipped union. Resolution: all ACs rewritten with lowercase string literals; the two new values are added via additive extension of the Phase-7-owned `types.py` (fine per ADR-0009 — the fence guards Phase 0–6.5 locked files, not Phase 7's own kernel Literals).
4. **Fixture data does not match shipped `BaseImageSlice` shape** — original AC-10 fixture used `layer_digest_map = {"sha256:xyz...": ("apk", "alpine-3.18.2", "builder")}` (invented shape). Shipped `BaseImageSlice` (per `phase-arch-design.md` line 1136) carries `paths, stages, confidence` where each `BaseImageStage` has `name, ref, digest, kind`. Similarly, `DistroPackage` fixture used a tuple where `types.py` ships `(name, version, distro)` with `distro: Literal["alpine", "debian", "ubuntu", "rhel"]`. Resolution: every fixture data block rewritten against the shipped model shapes.

Twelve **HARDEN-severity** tightening edits: metamorphic property (adding a matching layer never flips `BaseImage → Unknown`); parameterized-collapse test (all five `MismatchReason` values from S4-01 map to `"sbom_layer_attribution_absent"`); `case _: assert_never(_)` syntax fix (`_` is the wildcard, not a name — captured as `case x: assert_never(x)`); duplicate-artifact union-of-locations coverage (mirrors S4-01 F-COV-5); zero-artifact SBOM; static-confidence test; all-three-kwarg construction test; adapter-collapses-verifier-mismatch parameterized test; find-artifact-by-package-id helper rule-of-three note; `_WARNING_IDS` dropped (Phase 1 ADR-0007 is probe-only; adapter is silent — mirrors S4-01 F-CON-8); reference to the yet-to-ship `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` reframed as a **spec-side precedent** (via S3-02's hardened story) rather than a file-on-disk to read; verifier call-signature clarified (S4-01 verifier takes `(sbom, image_manifest)` — the adapter first filters the SBOM to the target `package_id` artifact, then either calls the verifier on a scoped view or performs the layer-membership check inline against the artifact's `locations[].layerID`).

Three **NIT-severity** touch-ups folded in.

No goal or scope change. The story remains "ship the plugin tree bootstrap + AlpineAdapter registered at `(BASE_IMAGE, APK)`, defensive against every documented missing-data path."

## Context

S2-04 + S2-01 ship the `vuln.provenance` primitive's adapter registry and assembly. The Phase 3 plugin's `NpmVulnProvenanceAdapter` (S3-02) will register the first concrete adapter — `(Layer.APP, Ecosystem.NPM)`. This story registers the **first base-image adapter**: `AlpineVulnProvenanceAdapter` at `(Layer.BASE_IMAGE, Ecosystem.APK)`. Conceptually it answers: "given this CVE on this Alpine-derived image, is the vulnerable package coming from the Alpine `apk` database (base-image layer), or somewhere else?"

This story also **bootstraps the entire `plugins/distroless-migration--node--npm/` directory tree** for the first time. Per Phase 7 ADR-0005, the migration plugin's probes, adapters, recipes, schema, and skills all live under this plugin directory — never under `src/codegenie/`. The directory bootstrap is additive by construction: every file is new. The byte-edit allowlist (S5-01) does not need an entry for any of these files because they fall outside the "Phase 0–6.5 file" scope the fence guards.

The adapter is deliberately **defensive against missing data**. Phase 7 Step 7 ships `BaseImageProbe`, which produces the `BaseImageSlice` (per `phase-arch-design.md §Data model` line 1136 — `paths, stages, confidence`; each `BaseImageStage` carries `name, ref, digest, kind`) the adapter reads to map SBOM `locations[].layerID` → `(image_digest, layer_digest, distro_pkg, stage)`. Step 4 lands **before** Step 7 — so the adapter MUST degrade cleanly to `Unknown(reason="base_image_probe_absent")` when the slice is absent. The defensive guard is mechanical (returns `Unknown`, does not raise) and is the same behavior the production system will exhibit when the probe was skipped on a non-migration workflow.

**How the adapter reads the `BaseImageSlice` (kernel-contract-preserving design).** The shipped `VulnProvenanceAdapter` Protocol has a four-arg `attribute(cve_id, package_id, image_ref, sbom)` and `assemble_provenance` calls it positionally with those four. Adding a fifth `repo_context` kwarg would break the frozen kernel contract. Instead, the adapter accepts a **DI-injected `base_image_slice_provider: BaseImageSliceProvider | None = None`** on `__init__` (per Phase 7 ADR-0007's DI-vocabulary extension protocol). The provider is a `Callable[[], BaseImageSlice | None]` — a zero-arg closure that returns the current-workflow slice or `None` when the probe hasn't run. This story amends `_DI_KWARGS` in `src/codegenie/primitives/vuln_provenance/factory.py` with exactly one new entry (`base_image_slice_provider`); the Phase 7 ADR-0007 amendment is documented inline in the ADR file as part of this story's landing. Production wiring — building a real provider that closes over `RepoContext.probes["BaseImage"]` and injecting a `DefaultAdapterFactory` with it — lands in S8-01 / S8-03. This story uses fixture providers.

Cross-verification against `sbom_verifier.py` (S4-01, HARDENED — will ship with `cross_check_sbom_layer_attribution(sbom, image_manifest) -> Verification` and `try_cross_check(sbom, image_manifest_raw, ...) -> Result[Verification, MismatchError]`) is the structural defense against poisoned SBOMs (Gap 3). The adapter first finds the SBOM artifact matching `package_id` (union of `locations[]` across duplicate entries), builds an `ImageManifest` from the injected `BaseImageSlice`, calls `cross_check_sbom_layer_attribution` with the manifest, and — critically — **collapses every one of the five `MismatchReason` values S4-01 defines** (`layer_id_malformed`, `layer_id_not_in_manifest`, `sbom_artifact_has_no_locations`, `artifact_not_in_sbom`, and any future addition) to a single `Unknown(reason="sbom_layer_attribution_absent")` on the adapter surface. The specific `MismatchReason` is forwarded on the structured `sbom.routing_anomaly` event for operator diagnosability (per S4-01 F-CON-5's Notes-for-implementer). **No exceptions cross the adapter boundary** except the typed `ProvenanceError` hierarchy.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §7b. AlpineVulnProvenanceAdapter` (lines 748–754 — the full component spec; "SBOM mismatch is a `Unknown` return, NOT an exception").
  - `../phase-arch-design.md §Module tree` (lines 269–299 — full plugin directory layout; `adapters/`, `probes/`, `recipes/`, `schema/`, `subgraph/`, `skills/`, `data/`, `plugin.yaml`, `tccm.yaml`).
  - `../phase-arch-design.md §Component design §2 — Provenance discriminated union` — `BaseImage(image_digest: ImageDigest, layer_digest: LayerDigest, distro_pkg: DistroPackage, stage: DockerStageName | None, confidence: AdapterConfidence)` is the typed return shape on hit; `Unknown(reason: UnknownReason, details: dict[str, str] | None)` on miss.
  - `../phase-arch-design.md §Data model BaseImageSlice` (lines 1136–1145) — the actual shape: `paths: list[Path], stages: list[BaseImageStage], confidence: Literal["high","medium","low"]`; each `BaseImageStage` has `name: DockerStageName | None, ref: ImageRef, digest: ImageDigest, kind: Literal["distroless","minimal","full","vendor_specific","unknown"]`. **Read this before writing fixtures — the story's original `layer_digest_map` shape was invented.**
  - `../phase-arch-design.md §Scenario B — Migration via base-image attribution` (around line 419 — Alpine adapter is invoked, returns `BaseImage(...)`).
  - `../phase-arch-design.md §Scenario D — Failure path` (lines 488–515 — SBOM mismatch → `Unknown`).
  - `../phase-arch-design.md §Edge cases row #1` (line 1240 — poisoned SBOM → `Unknown(reason="sbom_layer_attribution_absent")`).
- **Phase ADRs:**
  - `../ADRs/0004-vuln-provenance-primitive-home.md` — the primitive is **consumed by**, not authored by, the plugin. The adapter lives in the plugin tree.
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — same precedent applies to adapters: plugin-contributed.
  - `../ADRs/0007-provenance-adapter-registry-stores-classes.md` — `__init__` accepts DI kwargs from the closed set. **This story amends the set by adding `base_image_slice_provider`** (one entry) per the amendment protocol documented in `factory.py`'s module docstring §"To grow the DI vocabulary". The ADR-0007 amendment lands as part of this story's PR.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — plugin-internal contribution shape.
  - `../../../production/adrs/0038-vulnerability-provenance-attribution.md` — `BaseImage` variant definition.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/primitives/vuln_provenance/protocols.py` (S1-04, shipped) — `VulnProvenanceAdapter` Protocol shape. **Signature is `attribute(self, cve_id, package_id, image_ref, sbom) -> Provenance` — four positional args, NO `repo_context`. Frozen kernel contract.**
  - `src/codegenie/primitives/vuln_provenance/registry.py` (S2-01, shipped) — `@register_provenance_adapter(layer=..., ecosystem=...)` signature; `Layer`/`Ecosystem` StrEnum declaration orders.
  - `src/codegenie/primitives/vuln_provenance/factory.py` (S2-02, shipped) — `_DI_KWARGS` closed vocabulary; `DefaultAdapterFactory`; the amendment protocol this story follows (see §"To grow the DI vocabulary").
  - `src/codegenie/primitives/vuln_provenance/assembly.py` (S2-03/S2-04, shipped) — `assemble_provenance` calls `factory(cls).attribute(cve_id, package_id, image_ref, sbom)` positionally. **This is why the story cannot add a fifth kwarg.**
  - `src/codegenie/primitives/vuln_provenance/types.py` (S1-02/S1-03, shipped) — `BaseImage`, `Unknown`, `UnknownReason` (a **`Literal[...]` union**, NOT an enum — use string values), `DistroPackage` (`name, version, distro: Literal[…]`), `AdapterConfidence` (`HIGH | DEGRADED | UNAVAILABLE` — **no `LOW` member**).
  - `src/codegenie/primitives/vuln_provenance/errors.py` (S1-04, shipped) — `ProvenanceError`, `AdapterError`, `RegistryError`.
  - **S4-01 hardened story** (`../stories/S4-01-sbom-verifier-cross-check.md`) — `cross_check_sbom_layer_attribution(sbom, image_manifest) -> Verification` and `try_cross_check(sbom, image_manifest_raw, ...) -> Result[Verification, MismatchError]`. `MismatchReason` has 5 values as of S4-01's HARDENED pass (`layer_id_malformed, layer_id_not_in_manifest, sbom_artifact_has_no_locations, artifact_not_in_sbom, plus one held-open`). **S4-01 has not shipped yet; the shape is spec-side only.**
  - **S3-02 hardened story** (`../stories/S3-02-npm-vuln-provenance-adapter.md`) — sibling-shape precedent for `__init__` + `attribute` + `confidence`. **The file `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` has NOT shipped yet (S3-02 is `BLOCKED` on the phase-3 plugin directory build-out per CLAUDE.md).** Read the story, not the (nonexistent) file, for the sibling shape.

## Goal

Ship the `plugins/distroless-migration--node--npm/` plugin directory bootstrap (empty `__init__.py` files + the adapter sub-tree) and land `AlpineVulnProvenanceAdapter` registered at `(Layer.BASE_IMAGE, Ecosystem.APK)`. The adapter:

- Accepts a DI-injected `base_image_slice_provider` on `__init__` (Phase 7 ADR-0007 amendment — one new entry in `_DI_KWARGS`).
- Reads the `BaseImageSlice` via `base_image_slice_provider()` when called.
- Finds the SBOM artifact matching `package_id` (using the union of `locations[]` across duplicate SBOM entries).
- Cross-verifies via S4-01's verifier and returns:
  - `BaseImage(image_digest, layer_digest, distro_pkg, stage, confidence=AdapterConfidence.HIGH)` on verifier `VerificationOk` with a resolved layer-to-distro-package mapping.
  - `Unknown(reason="sbom_layer_attribution_absent")` when the verifier returns any `VerificationMismatch` reason (all 5 collapse to this one adapter-surface reason).
  - `Unknown(reason="base_image_probe_absent")` when the slice provider is absent OR returns `None` (Step 7 hasn't shipped, or a non-migration workflow).
  - `Unknown(reason="base_image_not_alpine")` when the resolved base-image `kind` is not `"minimal"` / `"full"` (i.e., `distroless`, `vendor_specific`, `unknown`).
- Adds exactly two additive members to the Phase-7-owned `UnknownReason` `Literal` union: `"base_image_probe_absent"` and `"base_image_not_alpine"` (legal under ADR-0009 because `types.py` is a Phase 7 file, not a Phase 0–6.5 locked one).
- Adds exactly one additive member to `_DI_KWARGS` in `factory.py`: `"base_image_slice_provider"` (per ADR-0007's documented amendment protocol; the corresponding ADR-0007 amendment lands in the same PR).

Every path returns typed `Provenance`; **no exceptions cross the adapter boundary except `ProvenanceError` subclasses**.

## Acceptance criteria

### Directory bootstrap

- [ ] AC-1 — `plugins/distroless-migration--node--npm/__init__.py` exists (empty, with `# Phase 7 plugin tree; see ../ADRs/0005-probes-live-under-plugin-not-core-tree.md` header).
- [ ] AC-2 — `plugins/distroless-migration--node--npm/adapters/__init__.py` exists (empty).
- [ ] AC-3 — `plugins/distroless-migration--node--npm/api.py` exists with a single explicit-import side-effect block — `from .adapters import alpine_provenance  # noqa: F401` (one line for now; S4-03 adds the second; S8-01 ships the rest of `api.py`).
- [ ] AC-4 — Fence test `tests/fence/test_provenance_primitive_in_plugin_directory.py` (extended by S5-02; this story may ship a placeholder assertion-only stub) confirms the adapter class is defined under `plugins/distroless-migration--node--npm/adapters/`, NOT under `src/codegenie/`.

### DI vocabulary extension (Phase 7 ADR-0007 amendment)

- [ ] AC-5 — `src/codegenie/primitives/vuln_provenance/factory.py` is edited (additive Phase-7-file extension, legal under ADR-0009): `_DI_KWARGS` gains exactly one new entry, `"base_image_slice_provider"`. `DefaultAdapterFactory.__init__` gains one new kwarg `base_image_slice_provider: object | None = None`. `DefaultAdapterFactory.__call__`'s `available` dict gains the corresponding entry. Module docstring's amendment history is extended.
- [ ] AC-6 — A **new type alias** is defined at `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py`: `BaseImageSliceProvider = Callable[[], BaseImageSlice | None]`. (Not exposed on the plugin's public surface; adapters that need slice providers declare and consume them at their local scope. If S4-03 needs the same alias, the third consumer triggers a rule-of-three extract to a plugin-shared module — flagged in Notes.)
- [ ] AC-7 — `docs/phases/07-migration-task-class/ADRs/0007-provenance-adapter-registry-stores-classes.md` is amended in-place (an `## Amendment (2026-08-XX)` section at the top) documenting the addition of `base_image_slice_provider` to the closed `_DI_KWARGS` vocabulary. Original decision text is not touched (the amendment is additive).

### `UnknownReason` extension (Phase 7 additive edit)

- [ ] AC-8 — `src/codegenie/primitives/vuln_provenance/types.py` `UnknownReason` `Literal[...]` gains exactly two new members: `"base_image_probe_absent"` and `"base_image_not_alpine"`. (Legal under ADR-0009 because `types.py` is a Phase 7 file, not a Phase 0–6.5 locked one. The closed-set positive fence — if one is added by a future story — must be updated to match. Story flags this coordination note in the PR.)

### Adapter — public shape (Phase 7 ADR-0007 compliant)

- [ ] AC-9 — `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py` defines `class AlpineVulnProvenanceAdapter` decorated `@register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.APK)`.
- [ ] AC-10 — `__init__` accepts only kwargs from the ADR-0007-amended closed DI vocabulary: `sbom_reader: object | None = None`, `logger: object | None = None`, `image_manifest_cache: object | None = None`, `base_image_slice_provider: BaseImageSliceProvider | None = None`. **No positional args. No I/O at construction.** A pytest test (`test_construction_does_no_io`) instantiates the class with zero args and with all four kwargs (`monkeypatch`'d `open`/`os.stat`/`socket.socket` to raise if touched) and asserts no exception, no logging, no filesystem or network activity.
- [ ] AC-11 — `attribute(self, cve_id: CveId, package_id: PackageId, image_ref: ImageRef | None, sbom: SyftSbom) -> Provenance` is the signature — **four positional args exactly matching the frozen `VulnProvenanceAdapter` Protocol (S1-04)**. All parameter types are pinned; no `Any`. **No `repo_context` kwarg; no keyword-only star.** The `BaseImageSlice` is obtained by calling `self._base_image_slice_provider()` when non-None.
- [ ] AC-12 — `confidence(self) -> AdapterConfidence` returns the static value `AdapterConfidence.HIGH` (adapter-class-level, per the Protocol docstring — the dispatch tie-breaker uses this). Per-call confidence is populated on the returned `BaseImage.confidence` field (also `AdapterConfidence.HIGH` on successful attribution). Test `test_confidence_is_static_high` calls `confidence()` twice without an `attribute()` call in between and asserts both return `AdapterConfidence.HIGH`; the adapter has **no mutable instance state** (asserted by `test_no_mutable_instance_state` — `getattr(adapter, "_last_attribute_result", None)` is `None` and stays `None` after an `attribute()` call).

### Behavioral correctness

- [ ] AC-13 — Happy path (`test_layer_match_returns_base_image`): `base_image_slice_provider` returns a `BaseImageSlice` with a single `BaseImageStage(name=DockerStageName("builder"), ref=ImageRef("alpine:3.18.2"), digest=ImageDigest("sha256:abc..."), kind="minimal")`; SBOM artifact for `package_id=PackageId("openssl@3.1.4-r1")` has `locations=[SyftLocation(path="/lib/apk/db/installed", layerID="sha256:abc...")]` (matches the stage's digest); verifier returns `VerificationOk`; adapter returns `BaseImage(image_digest=ImageDigest("sha256:abc..."), layer_digest=LayerDigest("sha256:abc..."), distro_pkg=DistroPackage(name="openssl", version="3.1.4-r1", distro="alpine"), stage=DockerStageName("builder"), confidence=AdapterConfidence.HIGH)`.
- [ ] AC-14 — Verifier-mismatch collapse (`test_verifier_mismatches_collapse_to_sbom_layer_attribution_absent`, parameterized over all five `MismatchReason` values from S4-01): for each `MismatchReason` the fixture verifier returns, the adapter returns `Unknown(reason="sbom_layer_attribution_absent", details={"mismatch_reason": <the specific MismatchReason>})`. This proves the 5→1 collapse-with-provenance-preservation contract (S4-01 F-CON-5 Notes) — the specific reason survives in `details` for the `sbom.routing_anomaly` event, but the closed adapter surface is one value.
- [ ] AC-15 — `base_image_slice_provider is None` (`test_slice_provider_none_returns_probe_absent`): adapter returns `Unknown(reason="base_image_probe_absent")`. Adapter emits no logs; no exception raised.
- [ ] AC-16 — `base_image_slice_provider()` returns `None` (`test_slice_provider_returns_none_returns_probe_absent`): identical outcome to AC-15 (adapter treats a `None`-returning provider identically to a missing provider).
- [ ] AC-17 — `image_ref is None` (`test_no_image_ref_returns_probe_absent`): the workflow is non-container; adapter returns `Unknown(reason="base_image_probe_absent")` (probe is trivially inapplicable — a `Unknown` variant with a specific reason preserves the operator-facing narrative that "no image to probe = no base-image slice").
- [ ] AC-18 — SBOM has no artifact matching `package_id` (`test_artifact_not_in_sbom_returns_sbom_layer_attribution_absent`): adapter returns `Unknown(reason="sbom_layer_attribution_absent", details={"mismatch_reason": "artifact_not_in_sbom"})`. (Aligns with S4-01's fifth `MismatchReason`.)
- [ ] AC-19 — Non-Alpine base image (`test_distroless_base_returns_unknown_not_alpine`, `test_vendor_specific_returns_unknown_not_alpine`, parameterized): `BaseImageStage.kind in ("distroless", "vendor_specific", "unknown")` → adapter returns `Unknown(reason="base_image_not_alpine", details={"observed_kind": <kind>})`. **The Distroless adapter (S4-03) handles the `"distroless"` case explicitly** — this adapter exits cleanly here; the two adapters coexist on the `Layer.BASE_IMAGE` walk (Alpine at `APK`, Distroless at `DPKG`), and both may return `Unknown` on the same call.
- [ ] AC-20 — Duplicate SBOM artifacts (`test_duplicate_artifacts_use_union_of_locations`, mirrors S4-01 F-COV-5): `sbom.artifacts` contains two entries for the same `(name, version)` matching `package_id`, one with `locations[].layerID="sha256:abc..."` (matches manifest) and one with `locations[].layerID="sha256:DEAD..."` (mismatches). Adapter takes the union — the matching layer is found — returns `BaseImage(...)`. First-match-wins would return `Unknown`; the fixture's ordering exercises both orderings via `@pytest.mark.parametrize`.
- [ ] AC-21 — Zero-artifact SBOM (`test_empty_sbom_returns_sbom_layer_attribution_absent`): `sbom.artifacts=[]`; slice provider present with valid Alpine stages. Adapter returns `Unknown(reason="sbom_layer_attribution_absent", details={"mismatch_reason": "artifact_not_in_sbom"})`. (Distinct from AC-15's `"base_image_probe_absent"` — here the probe *did* run; the SBOM is the deficient input.)
- [ ] AC-22 — Empty stages list (`test_slice_with_empty_stages_returns_probe_absent`): `BaseImageSlice(paths=[], stages=[], confidence="low")` returned from provider. Adapter returns `Unknown(reason="base_image_probe_absent", details={"stages_len": "0"})` — a probe slice with zero stages is operationally indistinguishable from a probe that ran-but-found-nothing.
- [ ] AC-23 — Match statement exhaustiveness (`test_alpine_provenance_exhaustiveness.py::test_match_arms`): the test proves `match attribute(...): case BaseImage(): ... case Unknown(): ... case unreachable: assert_never(unreachable)` is enforced. **Note: `_` in a `match` arm is the wildcard, NOT a name — the arm must capture as a named variable (`unreachable`) for `assert_never` to receive a value.** A companion `mypy --strict` negative fixture (`test_missing_arm_surfaces_mypy_error`) asserts mypy emits an `assert_never` error when the `unknown` arm is omitted (precedent: sibling `test_provenance_mypy_negative.py`).

### Metamorphic property + composition

- [ ] AC-24 — Metamorphic property (`test_adding_matching_layer_never_flips_ok_to_unknown`, Hypothesis-driven): given any fixture `(sbom, base_image_slice)` where the adapter returns `BaseImage(...)`, adding a new `BaseImageStage` with a fresh digest to the slice's `stages` tuple (concatenated, not replaced) MUST still return `BaseImage(...)` with the same `image_digest` and `layer_digest`. Guards against `all` vs `any` swaps and off-by-one set-membership bugs in the verifier-adapter composition. Mirrors S4-01 AC-16b's metamorphic pattern.
- [ ] AC-25 — Integration test extension (`tests/integration/test_provenance_assembly_via_plugins.py`, extended): registers `AlpineVulnProvenanceAdapter` via the plugin's `api.py` side-effect import; calls `assemble_provenance(...)` with a fixture-injected `DefaultAdapterFactory(base_image_slice_provider=lambda: <fixture slice>)`; asserts the returned `Provenance` is `BaseImage(...)` with the expected fields. Confirms the DI extension flows end-to-end through the shipped kernel — the frozen `attribute()` signature is preserved.

### Defensive — Gap 3 read-only-known-fields (the heart of S4-04's fence)

- [ ] AC-26 — Adapter reads ONLY `sbom.artifacts[i].name`, `sbom.artifacts[i].version`, `sbom.artifacts[i].locations[j].layerID`, and `sbom.artifacts[i].locations[j].path`. **It does NOT touch `sbom.descriptor`, does NOT iterate `model_extra`, does NOT call `getattr(artifact, "extra", default)`, `.model_dump()`, `.model_dump_json()`, `.dict()`, `.model_fields_set`, `__pydantic_fields_set__`, `pickle.dumps`, or iterate `for f in artifact.model_fields`.** This AC is locked by S4-04's AST fence (`tests/fence/test_alpine_adapter_reads_known_fields_only.py`); this story must implement the adapter so that fence passes. (Full escape-hatch list mirrors the S4-01 F-COV-2 Notes.)
- [ ] AC-27 — Adapter does NOT mutate `sbom`, does NOT mutate the returned `BaseImageSlice`, does NOT rebind `self._base_image_slice_provider` (frozen Pydantic on `sbom`/`slice` — would raise anyway, but the test `test_adapter_does_not_mutate_inputs` asserts the adapter does not even attempt a `model_copy(update=...)`).

### Performance + isolation

- [ ] AC-28 — Performance envelope (`tests/perf/test_alpine_provenance_adapter.py`, `@pytest.mark.bench`): asserts p99 ≤ 20 ms per call on a 100-artifact SBOM. Median ≤ 5 ms. Test harness note: single-process, Python 3.11+, no CI-time optimizer flags; the bench is honest single-call cost. Portfolio scale is Phase 10's concern.
- [ ] AC-29 — `mypy --strict plugins/distroless-migration--node--npm/adapters/alpine_provenance.py` clean.
- [ ] AC-30 — `ruff check`, `ruff format --check` clean.
- [ ] AC-31 — `make lint-imports` green: the adapter may import from `codegenie.primitives.vuln_provenance.*` but NOT from `codegenie.coordinator`, `codegenie.cache`, or any LLM SDK. Import-linter contract extended by S5-03; this story's adapter must respect it.
- [ ] AC-32 — `tests/fence/test_phase7_no_llm.py` (S1-06) green: no `anthropic`/`openai`/`langgraph`/`langchain`/`transformers`/`sentence-transformers`/`torch` reachable from this module's import closure.
- [ ] AC-33 — Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay green (`make check` — hard pre-merge gate per Phase 7 ADR-0009).
- [ ] AC-34 — Story Status updated to `Done` after implementation lands.

## Implementation outline

1. **Directory bootstrap.** Create `plugins/distroless-migration--node--npm/__init__.py`, `.../adapters/__init__.py`, `.../api.py` (one-line side-effect import).
2. **DI vocabulary extension** (kernel additive edit — coordinated with ADR-0007 amendment in the same PR):
   - `src/codegenie/primitives/vuln_provenance/factory.py`: add `"base_image_slice_provider"` to `_DI_KWARGS`; add the kwarg + storage + `available[]` entry in `DefaultAdapterFactory`; extend the module docstring's amendment history.
   - `docs/phases/07-migration-task-class/ADRs/0007-provenance-adapter-registry-stores-classes.md`: append `## Amendment (2026-08-XX)` documenting the one-entry addition.
3. **`UnknownReason` extension** (kernel additive edit): `src/codegenie/primitives/vuln_provenance/types.py`'s `UnknownReason = Literal[...]` gains `"base_image_probe_absent"` and `"base_image_not_alpine"` (alphabetical among the reason values, or append — implementer's choice; the sort order isn't load-bearing).
4. **Author `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py`:**
   - Module docstring naming Phase 7 ADR-0004 / ADR-0005 / ADR-0007 (and the ADR-0007 amendment landing in this PR).
   - **NO `_WARNING_IDS` declaration** (Phase 1 ADR-0007 is probe-only discipline; adapters are silent per AC-27 mirror & S4-01 F-CON-8).
   - `BaseImageSliceProvider = Callable[[], BaseImageSlice | None]` type alias.
   - `class AlpineVulnProvenanceAdapter` decorated `@register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.APK)`.
   - `__init__(self, *, sbom_reader=None, logger=None, image_manifest_cache=None, base_image_slice_provider=None)` — store args, no I/O.
   - `attribute(self, cve_id, package_id, image_ref, sbom)` — **four positional args exactly matching the frozen Protocol.** Core decision tree:
     a. If `image_ref is None` → `Unknown(reason="base_image_probe_absent")` (AC-17).
     b. `slice = self._base_image_slice_provider() if self._base_image_slice_provider is not None else None`. If `slice is None` → `Unknown(reason="base_image_probe_absent")` (AC-15/AC-16).
     c. If `not slice.stages` → `Unknown(reason="base_image_probe_absent", details={"stages_len": "0"})` (AC-22).
     d. Find the Alpine-eligible stages: `alpine_stages = [s for s in slice.stages if s.kind in ("minimal", "full")]`. If none → `Unknown(reason="base_image_not_alpine", details={"observed_kind": ",".join(sorted({s.kind for s in slice.stages}))})` (AC-19).
     e. `matching_artifacts = _find_artifacts_by_package_id(sbom, package_id)`. If empty → `Unknown(reason="sbom_layer_attribution_absent", details={"mismatch_reason": "artifact_not_in_sbom"})` (AC-18/AC-21).
     f. Aggregate the target-artifact `locations[].layerID`s (union across duplicates, drop `None` values) (AC-20).
     g. Build `ImageManifest(image_digest=alpine_stages[0].digest, layers=tuple(LayerDigest(s.digest) for s in alpine_stages))` (typed, ready for the verifier).
     h. Call `cross_check_sbom_layer_attribution(sbom, image_manifest)`.
     i. `match` on `Verification`:
        - `VerificationOk` → determine the winning `layer_digest` (the first `stages` digest that appears in the artifact's `locations[].layerID` union); construct `DistroPackage(name=<artifact.name>, version=<artifact.version>, distro="alpine")`; return `BaseImage(image_digest=<manifest.image_digest>, layer_digest=<winning>, distro_pkg=<distro_pkg>, stage=<winning stage's name>, confidence=AdapterConfidence.HIGH)`.
        - `VerificationMismatch(reason=<r>)` → `Unknown(reason="sbom_layer_attribution_absent", details={"mismatch_reason": <r>})` — collapse ALL 5 (or future N) mismatch reasons to the single adapter-surface reason, preserving `<r>` in `details` (AC-14).
   - `confidence(self) -> AdapterConfidence`: `return AdapterConfidence.HIGH` (static; no state).
   - Private module helper `_find_artifacts_by_package_id(sbom: SyftSbom, package_id: PackageId) -> tuple[SyftArtifact, ...]`: filter `sbom.artifacts` by `(a.name, a.version) == PackageId decomposition`. Returns a tuple (union across duplicates). **Rule-of-three note**: S4-03's Distroless adapter and any future ecosystem adapter will need the same lookup — flag as an extract-to-plugin-shared-module candidate when the third caller lands (see Notes-for-implementer).
5. **Author the test files per the TDD plan.**
6. **Run `make check`, fix lint, commit.** Confirm `bench/vuln-remediation/` cassette replay still green (Phase-3 hard gate — Phase 7 does not regress).

## TDD plan (red → green → refactor)

**Red (write tests first, watch them fail):**

`tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance.py`:

- `test_construction_does_no_io` — instantiate with zero args and with all four DI kwargs; monkeypatched `builtins.open`, `os.stat`, `socket.socket` raise if touched. Also asserts no `logger.info/warning/error` call (structlog mock).
- `test_registry_holds_class_not_instance` — after `import alpine_provenance`, `_REGISTRY[(Layer.BASE_IMAGE, Ecosystem.APK)]` is `AlpineVulnProvenanceAdapter` (the class), NOT an instance (`isinstance(_REGISTRY[...], type)` and `_REGISTRY[...] is AlpineVulnProvenanceAdapter`).
- `test_confidence_is_static_high` — `AlpineVulnProvenanceAdapter().confidence()` returns `AdapterConfidence.HIGH`; two consecutive calls return the same value; still `HIGH` after an `attribute(...)` call that returned `Unknown`.
- `test_no_mutable_instance_state` — after an `attribute(...)` call, no new instance attributes have been added (`vars(adapter)` unchanged compared to post-`__init__`).
- `test_layer_match_returns_base_image` (AC-13) — happy path.
- `test_verifier_mismatches_collapse_to_sbom_layer_attribution_absent` (AC-14) — parameterized over all 5 `MismatchReason` values; verifier fixture returns the reason; adapter collapses.
- `test_slice_provider_none_returns_probe_absent` (AC-15).
- `test_slice_provider_returns_none_returns_probe_absent` (AC-16).
- `test_no_image_ref_returns_probe_absent` (AC-17).
- `test_artifact_not_in_sbom_returns_sbom_layer_attribution_absent` (AC-18) — asserts `details["mismatch_reason"] == "artifact_not_in_sbom"`.
- `test_distroless_base_returns_unknown_not_alpine` (AC-19) — parameterized over `("distroless", "vendor_specific", "unknown")`.
- `test_duplicate_artifacts_use_union_of_locations` (AC-20) — parameterized over the two orderings.
- `test_empty_sbom_returns_sbom_layer_attribution_absent` (AC-21).
- `test_slice_with_empty_stages_returns_probe_absent` (AC-22).
- `test_adapter_does_not_mutate_inputs` (AC-27) — pass frozen inputs; `id()` and Pydantic hash unchanged post-call.

`tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance_exhaustiveness.py`:

- `test_match_arms` (AC-23) — `case BaseImage`, `case Unknown`, `case unreachable: assert_never(unreachable)`. **Note: `unreachable` is the arm-name capture; `case _:` alone cannot pass a value to `assert_never`.**
- `test_missing_arm_surfaces_mypy_error` (AC-23 static side) — runs `mypy --strict` against an inline fixture that omits the `Unknown` arm; asserts a `[assert_never]`-shaped error line.

`tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance_metamorphic.py`:

- `test_adding_matching_layer_never_flips_ok_to_unknown` (AC-24, `@given(...)`) — Hypothesis strategy generates a base `(sbom, base_image_slice)` that yields `BaseImage(...)`; the strategy also produces a fresh `BaseImageStage` with a random digest; the property asserts the augmented slice still yields `BaseImage(...)` with the same `image_digest` and `layer_digest`.

`tests/integration/test_provenance_assembly_via_plugins.py` (extended):

- `test_assemble_provenance_with_alpine_adapter_returns_base_image` (AC-25) — full end-to-end.

`tests/perf/test_alpine_provenance_adapter.py` (`@pytest.mark.bench`):

- `test_alpine_adapter_p99_under_20ms_on_100_artifact_sbom` (AC-28).

`tests/fence/test_provenance_primitive_in_plugin_directory.py` (stub extension for AC-4):

- Assertion-only stub confirming the adapter class is under `plugins/distroless-migration--node--npm/adapters/`. Full AST fence lands in S5-02.

**Green:** implement per §Implementation outline.

**Refactor:** if the `attribute` body exceeds ~80 LOC, extract `_extract_image_manifest_from_slice(slice) -> ImageManifest` and `_find_winning_stage(matching_layers, stages) -> BaseImageStage` as module-private helpers. Keep the decision tree itself flat (linear `if/match` cascade, no deeply nested branches). Do NOT extract `_find_artifacts_by_package_id` to a shared plugin module in this story — the rule-of-three threshold isn't met until S4-03 lands its Distroless adapter and (later) any third ecosystem adapter needs it.

## Files to touch

**New:**
- `plugins/distroless-migration--node--npm/__init__.py`.
- `plugins/distroless-migration--node--npm/adapters/__init__.py`.
- `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py` (≤ 200 LOC).
- `plugins/distroless-migration--node--npm/api.py` (≤ 10 LOC; just the side-effect import).
- `tests/unit/plugins/distroless_migration_node_npm/__init__.py`.
- `tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance.py`.
- `tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance_exhaustiveness.py`.
- `tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance_metamorphic.py`.
- `tests/perf/test_alpine_provenance_adapter.py` (`@pytest.mark.bench`).

**Edited (additive-only, Phase-7-owned files — legal under ADR-0009 which fences Phase 0–6.5 locked files):**
- `src/codegenie/primitives/vuln_provenance/factory.py` — extend `_DI_KWARGS` (+1); extend `DefaultAdapterFactory.__init__` (+1 kwarg) and `__call__.available` (+1 entry); extend module docstring amendment history.
- `src/codegenie/primitives/vuln_provenance/types.py` — extend `UnknownReason` `Literal[...]` (+2 members).
- `docs/phases/07-migration-task-class/ADRs/0007-provenance-adapter-registry-stores-classes.md` — append `## Amendment (2026-08-XX)` block.
- `tests/integration/test_provenance_assembly_via_plugins.py` — one new test case (the file itself was authored in S3-01/S2-04).
- `tests/fence/test_provenance_primitive_in_plugin_directory.py` — placeholder assertion-only extension (S5-02 lands the full AST walker).

**Do not touch:**
- `src/codegenie/primitives/vuln_provenance/protocols.py` — the `VulnProvenanceAdapter` Protocol is **frozen kernel contract**; the story's design preserves it.
- `src/codegenie/primitives/vuln_provenance/assembly.py` — `assemble_provenance` calls `attribute(cve_id, package_id, image_ref, sbom)` positionally; unchanged.
- `src/codegenie/primitives/vuln_provenance/registry.py`, `errors.py`, `syft_reader.py` — Phase 7 shipped, byte-locked.
- Any file under `src/codegenie/probes/` (probes are plugin-contributed per ADR-0005).
- Any file under `plugins/vulnerability-remediation--node--npm/` (Phase 3 plugin; byte-locked except via the S5-01 allowlist).
- `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` (S4-01-owned; consume, don't edit).
- `tests/fence/test_alpine_adapter_reads_known_fields_only.py` (S4-04-owned; conformance-only relationship here — AC-26).

## Out of scope

- The Distroless adapter (S4-03) — separate ecosystem (`DPKG`), separate decision tree.
- The Hypothesis SBOM-tampering property test + AST fence (S4-04 — those tests cover both Alpine + Distroless adapters and the verifier together).
- `BaseImageProbe` itself — Step 7. This story stubs the slice's read-side via fixture providers; the probe lives later.
- Production wiring of the `base_image_slice_provider` in the plugin loader — S8-01 / S8-03. This story ships the DI kwarg + adapter's consumption; production wiring closes over `RepoContext.probes["BaseImage"]` later.
- Extracting `_find_artifacts_by_package_id` to a plugin-shared module — deferred until N≥3 consumers exist (rule-of-three; currently N=1 with S4-03 as N=2).
- `plugin.yaml` and `tccm.yaml` — Step 8 (S8-01 / S8-04).
- `PLUGINS.lock` entry — Step 5 (S5-04).
- Adapter performance optimization beyond the 20 ms envelope — Phase 14 caching territory.
- A closed-set positive fence on `UnknownReason` (mirror of S4-01 AC-20b for `MismatchReason`) — deferred; a future story may add one. This story flags the coordination note in the PR when it lands.

## Notes for the implementer

- **The plugin tree is empty by design at this story's boundary.** Only `__init__.py`, `adapters/__init__.py`, `adapters/alpine_provenance.py`, and a one-line `api.py` exist. S4-03 adds `distroless_provenance.py`; Step 5 adds `PLUGINS.lock`; Step 7 adds `probes/`; Step 8 adds `plugin.yaml` + `tccm.yaml`; Steps 9–11 add `data/`, `recipes/`, `subgraph/`. Don't get ahead of the dependency DAG.

- **The frozen `VulnProvenanceAdapter` Protocol is load-bearing.** `attribute(self, cve_id, package_id, image_ref, sbom) -> Provenance` — four positional args, in that order. `assemble_provenance` calls it positionally. Adding a fifth arg, adding `*` for keyword-only, adding `repo_context` — any of these breaks the frozen contract and either forces a byte-edit to `assembly.py` (allowed as additive extension of a Phase-7 file, but a kernel-contract change) or breaks `NpmVulnProvenanceAdapter` when S3-02 ships. The `BaseImageSlice` is read via DI, not by widening the Protocol.

- **The ADR-0007 amendment is a story-scope deliverable.** `factory.py`'s module docstring says: "To grow the DI vocabulary: (1) propose an ADR-0007 amendment to the closed set; (2) extend `_DI_KWARGS`; (3) extend `DefaultAdapterFactory.__init__` and the `available` mapping in `__call__`; (4) update this docstring; (5) update ADR-0007 §Consequences." All five steps land in the same PR as the adapter. The amendment is one entry (`"base_image_slice_provider"`); its shape (`Callable[[], BaseImageSlice | None]`) is documented in the adapter's module docstring.

- **`UnknownReason` is a `Literal[...]` union, NOT an enum.** Use `"base_image_probe_absent"`, not `UnknownReason.BASE_IMAGE_PROBE_ABSENT`. The seven-variant `Provenance` discriminated union routes on the `kind` discriminator; `Unknown.reason` is a plain string field validated against the Literal. When adding the two new members, keep the closed-set property intact — a downstream `match/assert_never` block will need the additions when it walks `UnknownReason` (search the repo before shipping to find any such walk).

- **`AdapterConfidence` has NO `LOW` member.** The shipped values are `HIGH | DEGRADED | UNAVAILABLE`. `confidence()` returns adapter-class-level static confidence for the dispatch tie-breaker; per-call confidence lives on `BaseImage.confidence` (also an `AdapterConfidence` value). This adapter's `confidence()` always returns `HIGH`; its `BaseImage.confidence` is `HIGH` on successful attribution. `Unknown` variants don't carry per-call confidence.

- **Do NOT add `_WARNING_IDS`** to the adapter module. Phase 1 ADR-0007's `_WARNING_IDS: Final[frozenset[str]]` + `raise AssertionError` discipline is **probe-only** — probes emit `WarningId`s in their outputs; adapters do not. AC-15/AC-17/AC-22 all specify the adapter is silent (no logs, no exceptions). Mirrors S4-01 F-CON-8. If this feels like drift from an old habit, it's because the S3-02 sibling story (which also drops `_WARNING_IDS`) has not shipped yet, so the visible precedent isn't in the tree.

- **The `BaseImageSlice` shape is authoritative in the arch, not in shipped code.** `phase-arch-design.md §Data model` lines 1136–1145 pin the fields (`paths, stages, confidence`; each `BaseImageStage` has `name, ref, digest, kind`). Step 7's `BaseImageProbe` will ship a Pydantic model matching this shape. Fixtures in this story must construct `BaseImageSlice` instances against this shape — the original story's `layer_digest_map = {"sha256:xyz...": ("apk", "alpine-3.18.2", "builder")}` was invented and does NOT exist on the arch's slice model. Every fixture rewritten in the hardened ACs above uses only fields the arch names.

- **Verifier collapse — the 5→1 adapter-surface reason mapping.** S4-01's verifier reports 5 `MismatchReason` values (`layer_id_malformed`, `layer_id_not_in_manifest`, `sbom_artifact_has_no_locations`, `artifact_not_in_sbom`, plus a fifth). The adapter surface exposes exactly ONE `UnknownReason` — `"sbom_layer_attribution_absent"` — for ALL of them. Operator diagnosability is preserved via `details["mismatch_reason"]` on the `Unknown` variant, which the `sbom.routing_anomaly` event log will forward on the structured event (per S4-01 F-CON-5's adapter-side lossy mapping note). This preserves the seven-variant `Unknown` contract without dropping information.

- **Verifier invocation shape.** S4-01's `cross_check_sbom_layer_attribution(sbom, image_manifest) -> Verification` takes the full `sbom` and full `image_manifest`; it does not accept per-artifact scoping kwargs. The adapter's decision tree first filters `sbom.artifacts` down to the `package_id` matches (via the private `_find_artifacts_by_package_id` helper), then calls the verifier with the full sbom + built manifest. The verifier's answer is a whole-SBOM verdict; the adapter interprets `VerificationOk` as "at least one target-artifact layerID is in the manifest" for its resolution path. If a per-artifact scoped verifier is needed later, that's an S4-01 amendment, not an S4-02 concern.

- **`api.py` is a stub.** It is **not** the same as `S8-01`'s `api.py`, which adds the plugin instance, TCCM resolver wiring, and probe imports. This story's `api.py` is intentionally minimal — one explicit-import line so adapter registration fires when the loader imports the plugin. Adding more here is scope creep.

- **`AlpineVulnProvenanceAdapter` does not own its layer-to-package mapping.** The mapping is derived from `BaseImageSlice.stages` (each `BaseImageStage` carries `digest` and `kind`; the adapter matches SBOM `locations[].layerID` against the stage digests). If the slice doesn't carry the mapping information, the adapter returns `Unknown(reason="base_image_probe_absent")` — it does not attempt to reconstruct the mapping from other sources.

- **The `__init__.py` for the plugin tree is empty, not re-exporting.** The plugin's public surface is its `plugin.yaml` (Step 8). The directory's `__init__.py` is just the marker file. (Avoid the temptation to put adapters into `__all__` — they register via decorator side effects, not by import re-export.)

- **`case _: assert_never(_)` does NOT work.** In a `match` arm, `_` is the **wildcard** pattern, not a name binding — `assert_never(_)` reads `_` as the module-level free name (typically `NameError`). Capture the value as a named variable in the arm: `case unreachable: assert_never(unreachable)`. Precedent: `assembly.py`'s final `case _: assert_never((app_result, base_result))` works because `assert_never` is called with an explicit tuple, not with `_`.

- **Performance: 20 ms p99 is honest single-call cost.** The adapter walks the SBOM artifact list looking for the `package_id` match. For 10⁴-artifact SBOMs the linear scan dominates; consider a one-time `dict[PackageId, tuple[SyftArtifact, ...]]` build inside `attribute()` — but only if the bench fixture grows beyond 100 artifacts (Phase 7 fixture portfolio S12-01 stays small). Premature optimization is a Rule-2 violation.

- **Rule-of-three deferral for `_find_artifacts_by_package_id`.** Right now N=1 (this adapter). S4-03's Distroless adapter will make N=2. The third caller (any future ecosystem adapter — RPM, DPKG-for-Ubuntu, etc.) triggers the extract. Keep the helper module-private in this story; don't hoist prematurely.

- **`base_image_slice_provider` fixtures — how tests construct one.** A fixture provider is a zero-arg callable returning a `BaseImageSlice` or `None`. Simplest pattern: `provider = lambda: BaseImageSlice(paths=[Path("Dockerfile")], stages=[BaseImageStage(name=DockerStageName("builder"), ref=ImageRef("alpine:3.18.2"), digest=ImageDigest("sha256:abc..."), kind="minimal")], confidence="high")`. For "provider raises" adversarial cases (deferred to S4-04's adversarial pass), the adapter would still catch via `AdapterError` — that's a later concern.
