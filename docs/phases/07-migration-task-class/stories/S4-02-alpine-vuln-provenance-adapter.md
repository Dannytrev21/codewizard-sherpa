# Story S4-02 — `AlpineVulnProvenanceAdapter` + plugin tree scaffolding

**Step:** Step 4 — `AlpineVulnProvenanceAdapter` + `DistrolessVulnProvenanceAdapter` + `sbom_verifier.py`
**Status:** Ready
**Effort:** M
**Depends on:** S2-04 (`assemble_provenance` + `_ADAPTER_DISPATCH_ORDER`), S4-01 (`sbom_verifier.py`)
**ADRs honored:** Phase 7 ADR-0004 (primitive home — adapter lives under the plugin, NOT in `src/codegenie/primitives/`), Phase 7 ADR-0005 (plugin-contributed surface — `plugins/distroless-migration--node--npm/` tree bootstrapped here), Phase 7 ADR-0007 (registry stores classes, not instances; `__init__` accepts DI kwargs), Phase 7 ADR-0009 (byte-edit allowlist — this story adds an entire new plugin tree which is additive-only by definition)

## Context

S2-04 + S2-01 ship the `vuln.provenance` primitive's adapter registry and assembly. The Phase 3 plugin's `NpmVulnProvenanceAdapter` (S3-02) registered the first concrete adapter — Layer.APP, Ecosystem.NPM. This story registers the **first base-image adapter**: `AlpineVulnProvenanceAdapter` at `(Layer.BASE_IMAGE, Ecosystem.APK)`. Conceptually it answers: "given this CVE on this Alpine-derived image, is the vulnerable package coming from the Alpine `apk` database (base-image layer), or somewhere else?"

This story also **bootstraps the entire `plugins/distroless-migration--node--npm/` directory tree** for the first time. Per Phase 7 ADR-0005, the migration plugin's probes, adapters, recipes, schema, and skills all live under this plugin directory — never under `src/codegenie/`. The directory bootstrap is additive by construction: every file is new. The byte-edit allowlist (S5-01) does not need an entry for any of these files because they fall outside the "Phase 0–6.5 file" scope the fence guards.

The adapter is deliberately **defensive against missing data**. Phase 7 Step 7 ships `BaseImageProbe`, which produces the slice the adapter reads to map `SyftSbom.locations[].layerID` → `(image_digest, layer_digest, distro_pkg, stage)`. Step 4 lands **before** Step 7 — so the adapter MUST degrade cleanly to `Unknown(reason="sbom_layer_attribution_absent")` when the `BaseImageProbe` slice is absent from the gathered `RepoContext`. The defensive guard is mechanical (returns `Unknown`, does not raise) and is the same behavior the production system will exhibit when the probe was skipped on a non-migration workflow.

Cross-verification against `sbom_verifier.py` (S4-01) is the structural defense against poisoned SBOMs (Gap 3). The adapter calls the verifier and converts a `VerificationMismatch` into `Unknown(reason="sbom_layer_attribution_absent")` — the verifier returns evidence, the adapter returns the typed sum. **No exceptions cross the adapter boundary** except the typed `ProvenanceError` hierarchy.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §7b. AlpineVulnProvenanceAdapter` (lines 752–758 — the full component spec; "SBOM mismatch is a `Unknown` return, NOT an exception").
  - `../phase-arch-design.md §Module tree` (lines 269–299 — full plugin directory layout; `adapters/`, `probes/`, `recipes/`, `schema/`, `subgraph/`, `skills/`, `data/`, `plugin.yaml`, `tccm.yaml`).
  - `../phase-arch-design.md §Component design §2 — Provenance discriminated union` — `BaseImage(image_digest: ImageDigest, layer_digest: LayerDigest, distro_pkg: DistroPackage, stage: DockerStageName)` is the typed return shape on hit; `Unknown(reason: UnknownReason)` on miss.
  - `../phase-arch-design.md §Scenario B — Migration via base-image attribution` (around line 419 — Alpine adapter is invoked, returns `BaseImage(...)`).
  - `../phase-arch-design.md §Scenario D — Failure path` (lines 488–515 — SBOM mismatch → `Unknown`).
  - `../phase-arch-design.md §Edge cases row #1` (line 1240 — poisoned SBOM → `Unknown(reason="sbom_layer_attribution_absent")`).
- **Phase ADRs:**
  - `../ADRs/0004-vuln-provenance-primitive-home.md` — the primitive is **consumed by**, not authored by, the plugin. The adapter lives in the plugin tree.
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — same precedent applies to adapters: plugin-contributed.
  - `../ADRs/0007-provenance-adapter-registry-stores-classes.md` — `__init__` accepts DI kwargs from the closed set `{sbom_reader, logger, image_manifest_cache}`; no I/O at construction; the registry stores the class, not an instance.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — plugin-internal contribution shape.
  - `../../../production/adrs/0038-vulnerability-provenance-attribution.md` — `BaseImage` variant definition.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/primitives/vuln_provenance/protocols.py` (S1-04) — `VulnProvenanceAdapter` Protocol shape.
  - `src/codegenie/primitives/vuln_provenance/registry.py` (S2-01) — `@register_provenance_adapter(layer=..., ecosystem=...)` signature.
  - `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` (S4-01) — `cross_check_sbom_layer_attribution`, `Verification`, `VerificationOk`, `VerificationMismatch`, `ImageManifest`.
  - `src/codegenie/primitives/vuln_provenance/types.py` (S1-03) — `BaseImage`, `Unknown`, `UnknownReason`.
  - `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` (S3-02) — the **sibling-shape precedent**. Read this BEFORE writing the Alpine adapter. The Alpine adapter's `__init__`, `attribute`, and `confidence` methods follow the same shape.

## Goal

Ship the `plugins/distroless-migration--node--npm/` plugin directory bootstrap (empty `__init__.py` files + the adapter sub-tree) and land `AlpineVulnProvenanceAdapter` registered at `(Layer.BASE_IMAGE, Ecosystem.APK)`. The adapter reads `SyftSbom.locations[].layerID`, cross-verifies via `sbom_verifier.py`, and returns `BaseImage(...)` on hit, `Unknown(reason="sbom_layer_attribution_absent")` on mismatch, or `Unknown(reason="base_image_probe_absent")` when the `BaseImageProbe` slice is missing (Step 7 hasn't landed yet).

## Acceptance criteria

### Directory bootstrap

- [ ] AC-1 — `plugins/distroless-migration--node--npm/__init__.py` exists (empty, with `# Phase 7 plugin tree; see ../ADRs/0005-probes-live-under-plugin-not-core-tree.md` header).
- [ ] AC-2 — `plugins/distroless-migration--node--npm/adapters/__init__.py` exists (empty).
- [ ] AC-3 — `plugins/distroless-migration--node--npm/api.py` exists with a single explicit-import side-effect block — `from .adapters import alpine_provenance  # noqa: F401` (one line for now; S4-03 adds the second; S8-01 ships the rest of `api.py`).
- [ ] AC-4 — Fence test `tests/fence/test_provenance_primitive_in_plugin_directory.py` (extended by S5-02; this story may ship a placeholder assertion-only stub) confirms the adapter class is defined under `plugins/distroless-migration--node--npm/adapters/`, NOT under `src/codegenie/`.

### Adapter — public shape (Phase 7 ADR-0007 compliant)

- [ ] AC-5 — `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py` defines `class AlpineVulnProvenanceAdapter` decorated `@register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.APK)`.
- [ ] AC-6 — `__init__` accepts only kwargs from the closed DI vocabulary (Phase 7 ADR-0007): `sbom_reader: SbomReader | None = None`, `logger: Logger | None = None`, `image_manifest_cache: ImageManifestCache | None = None`. **No positional args. No I/O at construction.** A pytest test instantiates the class with zero args and asserts no exception, no logging, no filesystem touch.
- [ ] AC-7 — `attribute(self, *, cve_id: CveId, package_id: PackageId, image_ref: ImageRef | None, sbom: SyftSbom, repo_context: RepoContext) -> Provenance` is the signature. The `repo_context` kwarg is how the adapter reads the `BaseImageProbe` slice (when present). All kwargs typed; no `Any`.
- [ ] AC-8 — `confidence(self) -> AdapterConfidence` returns `AdapterConfidence.HIGH` when the `BaseImageProbe` slice is present and the verifier returned `Ok`; `AdapterConfidence.LOW` otherwise. (The arch's "confidence: high/medium/low" pattern from `CLAUDE.md §"Honest confidence"`.)
- [ ] AC-9 — Module declares `_WARNING_IDS: Final[frozenset[str]] = frozenset({"alpine_provenance.base_image_probe_absent", "alpine_provenance.sbom_layer_attribution_absent"})` validated at import time via `raise AssertionError(...)` (bare `assert` is forbidden by the `forbidden-patterns` pre-commit hook). The ID pattern matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` (Phase 1 ADR-0007).

### Behavioral correctness

- [ ] AC-10 — Happy path: `BaseImageProbe` slice present in `repo_context.probes["BaseImage"]` with `from_image_digest = sha256:abc...` and `layer_digest_map = {"sha256:xyz...": ("apk", "alpine-3.18.2", "builder")}`; SBOM artifact for `package_id` has `locations[0].layerID == "sha256:xyz..."`; verifier returns `VerificationOk`; adapter returns `BaseImage(image_digest=ImageDigest("sha256:abc..."), layer_digest=LayerDigest("sha256:xyz..."), distro_pkg=DistroPackage(distro="alpine", name="openssl", version="3.1.4-r1"), stage=DockerStageName("builder"))`.
- [ ] AC-11 — Verifier mismatch: SBOM claims `layerID="sha256:DEADBEEF..."` not in image manifest → `cross_check_sbom_layer_attribution` returns `VerificationMismatch(reason="layer_id_not_in_manifest")` → adapter returns `Unknown(reason=UnknownReason.SBOM_LAYER_ATTRIBUTION_ABSENT)`.
- [ ] AC-12 — `BaseImageProbe` slice absent (Step 7 hasn't shipped, or non-migration workflow): `repo_context.probes.get("BaseImage") is None` → adapter returns `Unknown(reason=UnknownReason.BASE_IMAGE_PROBE_ABSENT)` (additive enum value; this story extends `UnknownReason` if not already present from S1-02). Adapter logs nothing; no exception.
- [ ] AC-13 — SBOM has no artifact matching `package_id`: adapter returns `Unknown(reason=UnknownReason.SBOM_LAYER_ATTRIBUTION_ABSENT)`. The verifier is the source of truth — no parallel logic in the adapter.
- [ ] AC-14 — Adapter ecosystem filter: if `image_ref is None` OR the probed `base_image_kind != "minimal" and != "full"` (e.g., distroless), adapter returns `Unknown(reason=UnknownReason.BASE_IMAGE_NOT_ALPINE)`. **The Distroless adapter (S4-03) handles the distroless case explicitly** — this adapter exits cleanly.
- [ ] AC-15 — Match statement exhaustiveness: `tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance_exhaustiveness.py` proves `match attribute(...): case BaseImage(): ... case Unknown(): ... case _: assert_never(_)` is enforced.

### Defensive — Gap 3 read-only-known-fields (the heart of S4-04's fence)

- [ ] AC-16 — Adapter reads ONLY `sbom.artifacts[i].name`, `sbom.artifacts[i].version`, `sbom.artifacts[i].locations[j].layerID`, and `sbom.artifacts[i].locations[j].path`. **It does NOT touch `sbom.descriptor`, does NOT iterate `model_extra`, does NOT call `getattr(_, "extra", _)`.** This AC is locked by S4-04's AST fence (`tests/fence/test_alpine_adapter_reads_known_fields_only.py`); this story must implement the adapter so that fence passes.
- [ ] AC-17 — Adapter does NOT mutate `sbom` (frozen Pydantic — would raise anyway, but the test asserts the adapter does not even attempt a `model_copy(update=...)`).

### Performance + isolation

- [ ] AC-18 — Performance envelope: `tests/perf/test_alpine_provenance_adapter.py` (`@pytest.mark.bench`) asserts p99 ≤ 20 ms per call on a 100-artifact SBOM. (Honest single-call cost; portfolio scale is Phase 10's concern.)
- [ ] AC-19 — `mypy --strict plugins/distroless-migration--node--npm/adapters/alpine_provenance.py` clean.
- [ ] AC-20 — `ruff check`, `ruff format --check` clean.
- [ ] AC-21 — `make lint-imports` green: the adapter may import from `codegenie.primitives.vuln_provenance.*` but NOT from `codegenie.coordinator`, `codegenie.cache`, or any LLM SDK. Import-linter contract extended by S5-03; this story's adapter must respect it.
- [ ] AC-22 — `tests/fence/test_phase7_no_llm.py` (S1-06) green: no `anthropic`/`openai`/`langgraph`/`langchain`/`transformers` reachable from this module's import closure.
- [ ] AC-23 — Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay green (`make check` — hard pre-merge gate per Phase 7 ADR-0009).
- [ ] AC-24 — Story Status updated to `Done`.

## Implementation outline

1. Create the directory tree: `plugins/distroless-migration--node--npm/__init__.py`, `.../adapters/__init__.py`, `.../api.py`.
2. Verify `UnknownReason` enum (from S1-02) carries `SBOM_LAYER_ATTRIBUTION_ABSENT`, `BASE_IMAGE_PROBE_ABSENT`, `BASE_IMAGE_NOT_ALPINE`. If any are missing, add them additively (this story authors the additions; flag in the PR for the S1-02 implementer to acknowledge — coordinate via an explicit "depends on S1-02 amendment" note in the commit if needed).
3. Author `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py`:
   - Module docstring naming Phase 7 ADR-0004 / ADR-0005 / ADR-0007.
   - `_WARNING_IDS` declaration validated at import.
   - `class AlpineVulnProvenanceAdapter` decorated `@register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.APK)`.
   - `__init__(self, *, sbom_reader=None, logger=None, image_manifest_cache=None)` — store args, no I/O.
   - `attribute(self, *, cve_id, package_id, image_ref, sbom, repo_context)` — core decision tree:
     a. Read `base_image_slice = repo_context.probes.get("BaseImage")`. If `None` → `Unknown(reason=UnknownReason.BASE_IMAGE_PROBE_ABSENT)`.
     b. If `base_image_slice.kind not in ("minimal", "full")` (Alpine is one of those) → `Unknown(reason=UnknownReason.BASE_IMAGE_NOT_ALPINE)`.
     c. Build `ImageManifest` from `base_image_slice` (image_digest + tuple of LayerDigests).
     d. Call `cross_check_sbom_layer_attribution(sbom, image_manifest, artifact_name=..., artifact_version=...)`.
     e. `match` on `Verification`: `VerificationOk` → look up `(layer_digest → (apk_pkg_name, version, stage))` from the probe slice's layer-to-package map, return `BaseImage(...)`. `VerificationMismatch` → `Unknown(reason=UnknownReason.SBOM_LAYER_ATTRIBUTION_ABSENT)`.
   - `confidence` returns `AdapterConfidence.HIGH` if the last `attribute` call returned `BaseImage`, else `AdapterConfidence.LOW`. (Tracked via a frozen-record approach since the adapter is otherwise stateless — or rebuild on each `confidence` call; the implementer chooses, but no mutable instance state.)
4. Author the test files per the TDD plan.
5. Run `make check`, fix lint, commit.

## TDD plan (red → green → refactor)

**Red (write tests first, watch them fail):**
- `tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance.py::test_layer_match_returns_base_image` — happy path; fixture SBOM + fixture `BaseImageProbe` slice; expect `BaseImage(...)`. **Fails:** adapter doesn't exist.
- `tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance.py::test_poisoned_layer_id_returns_unknown_sbom_attribution_absent` — fixture SBOM with `layerID="sha256:DEAD..."` not in manifest; expect `Unknown(reason=UnknownReason.SBOM_LAYER_ATTRIBUTION_ABSENT)`.
- `tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance.py::test_base_image_probe_absent_returns_unknown_probe_absent` — `repo_context.probes` empty; expect `Unknown(reason=UnknownReason.BASE_IMAGE_PROBE_ABSENT)`. Adapter MUST NOT raise.
- `tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance.py::test_distroless_base_returns_unknown_not_alpine` — `base_image_slice.kind == "distroless"`; expect `Unknown(reason=UnknownReason.BASE_IMAGE_NOT_ALPINE)`.
- `tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance.py::test_construction_does_no_io` — instantiate `AlpineVulnProvenanceAdapter()` with `pytest`'s `tmp_path`-locked CWD; assert no filesystem reads, no logger emits, no network. (`pyfakefs` or `monkeypatch` on `open`.)
- `tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance.py::test_registry_holds_class_not_instance` — after `import alpine_provenance`, `_REGISTRY[(Layer.BASE_IMAGE, Ecosystem.APK)]` is `AlpineVulnProvenanceAdapter` (the class), NOT an instance (`isinstance(_REGISTRY[...], type)`).
- `tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance_exhaustiveness.py::test_match_arms` — `match` over the adapter's return covers `BaseImage` and `Unknown`, with `assert_never`.
- `tests/integration/test_provenance_assembly_via_plugins.py` (extended) — plugin import → `assemble_provenance(...)` → Alpine adapter invoked → typed `BaseImage` return. (Property-test-style: arrange a fixture that mounts the Alpine flow.)

**Green:** implement per §Implementation outline.

**Refactor:** if the `attribute` body exceeds ~80 LOC, extract `_extract_image_manifest_from_slice(slice) -> ImageManifest` and `_extract_distro_package(slice, layer_digest, package_name) -> DistroPackage | None` as module-private helpers. Keep the decision tree itself flat (linear `if/match` cascade, no deeply nested branches).

## Files to touch

**New:**
- `plugins/distroless-migration--node--npm/__init__.py`.
- `plugins/distroless-migration--node--npm/adapters/__init__.py`.
- `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py` (≤ 200 LOC).
- `plugins/distroless-migration--node--npm/api.py` (≤ 10 LOC; just the side-effect import).
- `tests/unit/plugins/distroless_migration_node_npm/__init__.py`.
- `tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance.py`.
- `tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance_exhaustiveness.py`.
- `tests/perf/test_alpine_provenance_adapter.py` (`@pytest.mark.bench`).

**Edited (additive only):**
- `src/codegenie/primitives/vuln_provenance/types.py` (S1-02-owned; this story only extends `UnknownReason` if needed — coordinate with S1-02 implementer if values are missing).
- `tests/integration/test_provenance_assembly_via_plugins.py` (extended with one new test case; the file itself was authored in S3-01).

**Do not touch:**
- Any file under `src/codegenie/probes/` (probes are plugin-contributed per ADR-0005).
- Any file under `plugins/vulnerability-remediation--node--npm/` (Phase 3 plugin; byte-locked except via the S5-01 allowlist).
- `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` (S4-01-owned; consume, don't edit).

## Out of scope

- The Distroless adapter (S4-03) — separate ecosystem (`DPKG`), separate decision tree.
- The Hypothesis SBOM-tampering property test + AST fence (S4-04 — those tests cover both Alpine + Distroless adapters and the verifier together).
- `BaseImageProbe` itself — Step 7. This story stubs the slice's read-side and tests with fixture data; the probe lives later.
- `plugin.yaml` and `tccm.yaml` — Step 8 (S8-01 / S8-04).
- `PLUGINS.lock` entry — Step 5 (S5-04).
- Adapter performance optimization beyond the 20 ms envelope — Phase 14 caching territory.

## Notes for the implementer

- **The plugin tree is empty by design at this story's boundary.** Only `__init__.py`, `adapters/__init__.py`, `adapters/alpine_provenance.py`, and a one-line `api.py` exist. S4-03 adds `distroless_provenance.py`; Step 5 adds `PLUGINS.lock`; Step 7 adds `probes/`; Step 8 adds `plugin.yaml` + `tccm.yaml`; Steps 9–11 add `data/`, `recipes/`, `subgraph/`. Don't get ahead of the dependency DAG.
- **The `BaseImageProbe` slice shape is forward-referenced.** Step 7's `BaseImageProbe` produces a `BaseImageSlice` Pydantic model. This story uses fixture data shaped against `phase-arch-design.md §Data model BaseImageSlice` (around line 1019: `from_image_digest`, `kind`, `layers`, etc.). When Step 7 lands the real slice, the adapter's read path may need a one-line widening — but the fixture-shape should match exactly. **Read `phase-arch-design.md` lines 1019–1023 before writing fixtures.**
- **Don't catch broad exceptions.** The adapter `match`es on `Verification` (typed) and reads typed probe slices (typed). The only place a raise is plausible is `cross_check_sbom_layer_attribution`'s `try_cross_check` wrapper — and S4-01 documents that the pure function never raises. If you find yourself adding `except Exception:`, stop — the adapter is wrong.
- **`api.py` is a stub.** It is **not** the same as `S8-01`'s `api.py`, which adds the plugin instance, TCCM resolver wiring, and probe imports. This story's `api.py` is intentionally minimal — one explicit-import line so adapter registration fires when the loader imports the plugin. Adding more here is scope creep.
- **`AlpineVulnProvenanceAdapter` does not own its layer-digest-to-package map.** That map is produced by `BaseImageProbe` (Step 7). This adapter is read-only over the probe slice. If the slice doesn't carry the map, the adapter returns `Unknown(reason=BASE_IMAGE_PROBE_ABSENT)` — it does not try to compute the map itself.
- **The `__init__.py` for the plugin tree is empty, not re-exporting.** The plugin's public surface is its `plugin.yaml` (Step 8). The directory's `__init__.py` is just the marker file. (Avoid the temptation to put adapters into `__all__` — they register via decorator side effects, not by import re-export.)
- **Performance: 20 ms p99 is honest single-call cost.** The adapter walks the SBOM artifact list looking for the `package_id` match. For 10⁴-artifact SBOMs the linear scan dominates; consider a one-time `dict[PackageId, SyftArtifact]` build inside `attribute()` — but only if the bench fixture grows beyond 100 artifacts (Phase 7 fixture portfolio S12-01 stays small). Premature optimization is a Rule-2 violation.
