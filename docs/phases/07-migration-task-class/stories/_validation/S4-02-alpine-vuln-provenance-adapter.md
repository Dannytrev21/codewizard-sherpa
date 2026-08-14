# Validation report — S4-02 `AlpineVulnProvenanceAdapter` + plugin tree scaffolding

**Validated:** 2026-08-14 (pre-executor pass)
**Validator:** phase-story-validator
**Verdict:** **HARDENED**
**Story file:** `docs/phases/07-migration-task-class/stories/S4-02-alpine-vuln-provenance-adapter.md`

## Context

Pre-executor validation on a `Ready` (never-shipped) story. Story shape was strong on plugin-placement discipline (ADR-0005), registry contract (ADR-0007), and defensive-return philosophy (Gap 3 + S4-04 fence coordination). But it had **four block-severity structural issues** that would have caused the executor to either break the frozen kernel Protocol, reference nonexistent enum members, use unsupported enum syntax, or write fixtures against invented model shapes:

1. **Kernel Protocol collision** — original AC-7 added `repo_context: RepoContext` as a fifth keyword-only kwarg on `attribute(...)`. The shipped `VulnProvenanceAdapter` Protocol (`src/codegenie/primitives/vuln_provenance/protocols.py`) is frozen at four positional args (`cve_id, package_id, image_ref, sbom`) — the arg list is explicitly named a "kernel contract" by S1-04's module docstring. `assemble_provenance` (S2-04, shipped in `assembly.py`) calls it positionally with those four args. Adding a fifth would either break the frozen contract at the Protocol layer OR force a byte-edit to `assembly.py` (allowed as additive extension of a Phase-7 file, but a semantic contract change to the kernel's call site). The `NpmVulnProvenanceAdapter` (S3-02, not shipped) is authored against the same frozen Protocol; changing it would break S3-02 retroactively.

2. **`AdapterConfidence.LOW` doesn't exist** — AC-8 branched on `HIGH` vs `LOW`. The shipped `AdapterConfidence` (`types.py`) is `StrEnum` with values `HIGH | DEGRADED | UNAVAILABLE`. Compounded by a semantic error: AC-8 also made `confidence()` state-dependent on the last `attribute()` call, but the Protocol docstring says it's adapter-class-level static (dispatch tie-breaker). The Implementation outline §3 explicitly said "no mutable instance state," directly contradicting AC-8's state-dependent semantics.

3. **`UnknownReason` attribute-access syntax** — every AC (AC-10 through AC-14) referenced values as `UnknownReason.SBOM_LAYER_ATTRIBUTION_ABSENT`, `UnknownReason.BASE_IMAGE_PROBE_ABSENT`, etc. Shipped `UnknownReason` is a `Literal[...]` union of lowercase strings (`"sbom_layer_attribution_absent"`, `"no_adapter_resolved"`, `"adapter_error"`, `"base_image_already_distroless"`, `"build_failed"`, `"dockerfile_parse_failed"`) — string values, not enum members. `UnknownReason.BASE_IMAGE_PROBE_ABSENT` would raise `AttributeError` at runtime. Compounded: two of the values the story references (`base_image_probe_absent`, `base_image_not_alpine`) don't exist in the shipped Literal at all.

4. **Fixture shapes don't match shipped models** — AC-10's fixture data used `layer_digest_map = {"sha256:xyz...": ("apk", "alpine-3.18.2", "builder")}`. This shape does not exist on the arch's `BaseImageSlice` (per `phase-arch-design.md` line 1136: `paths, stages, confidence`; each `BaseImageStage` has `name, ref, digest, kind`). The `DistroPackage` fixture used a tuple `("apk", "alpine-3.18.2", "builder")` — but the shipped model is `(name: str, version: str, distro: Literal["alpine", "debian", "ubuntu", "rhel"])`. The fixtures as written would fail `pytest` at import time with `ValidationError` on both.

All four fixed via surgical rewrites: DI-injected `base_image_slice_provider` preserves the frozen Protocol; static `AdapterConfidence.HIGH` for the class-level `confidence()`; string-Literal syntax throughout; fixture data rewritten against shipped model shapes. Twelve harden-severity edits + three nit-severity touch-ups tightened test-quality (metamorphic property, parameterized mismatch-collapse, exhaustiveness syntax fix, duplicate-artifact + empty-SBOM + empty-stages edge cases), consistency (`_WARNING_IDS` dropped per S4-01 F-CON-8 mirror, verifier collapse contract documented), design-patterns (rule-of-three deferral for shared helpers), and coverage (integration test, static-confidence test, no-mutable-state test, no-input-mutation test, and the `_DI_KWARGS` amendment coordination).

## Context Brief

**Goal (from story):** Ship the `plugins/distroless-migration--node--npm/` plugin directory bootstrap + `AlpineVulnProvenanceAdapter` registered at `(Layer.BASE_IMAGE, Ecosystem.APK)`. The adapter reads a `BaseImageSlice`, cross-verifies via S4-01's `sbom_verifier.py`, and returns `BaseImage` on hit, `Unknown` with a specific closed-set reason otherwise. Every path is typed; no exceptions cross the boundary except `ProvenanceError` subclasses.

**Phase-arch constraint:**
- §Component design §7b (lines 748–754) — `AlpineVulnProvenanceAdapter`: "Reads `SyftSbom.locations[].layerID`; matches against `BaseImageProbe`'s layer-to-image-digest mapping; cross-verifies via `sbom_verifier.py`." Return is `BaseImage(image_digest, layer_digest, distro_pkg, stage)` or `Unknown(reason="sbom_layer_attribution_absent")` on mismatch.
- §Data model `BaseImageSlice` (line 1136) — `paths: list[Path], stages: list[BaseImageStage], confidence: Literal["high","medium","low"]`; each `BaseImageStage` carries `name: DockerStageName | None, ref: ImageRef, digest: ImageDigest, kind: Literal["distroless","minimal","full","vendor_specific","unknown"]`.
- Scenario D (lines 488–515) — verifier mismatch → `Unknown(reason="sbom_layer_attribution_absent")`; orchestrator emits `sbom.routing_anomaly` with the specific mismatch reason in `details`.
- Edge cases row #1 (line 1240) — poisoned SBOM → `Unknown(reason="sbom_layer_attribution_absent")`.

**Phase ADRs honored:**
- ADR-0004 (primitive home) — adapter lives under the plugin, not `src/codegenie/primitives/`.
- ADR-0005 (probes/adapters live under plugin) — `plugins/distroless-migration--node--npm/adapters/`.
- ADR-0007 (registry stores classes; DI via factory) — closed `_DI_KWARGS` vocabulary; story amends by adding `base_image_slice_provider` per the documented amendment protocol.
- ADR-0009 (Phase 7 byte-edit allowlist) — `types.py` + `factory.py` are Phase-7-owned files; additive edits are legal.

**CLAUDE.md commitments:**
- "Extension by addition — no silent edits" (ADR-0043): adding to `_DI_KWARGS` and `UnknownReason` requires ADR amendment; the story's design routes both through the sanctioned amendment path.
- Newtype identifiers: `CveId`, `PackageId`, `ImageRef`, `ImageDigest`, `LayerDigest`, `DockerStageName` throughout.
- Functional core / imperative shell: `attribute()` is a pure decision tree over typed inputs; no I/O.
- Rule 2 (Simplicity First): no `BaseImageSliceReader` port (rule-of-three not met — N=1 in this story, N=2 with S4-03); no shared plugin utility module for `_find_artifacts_by_package_id` (rule-of-three defers).
- Rule 9 (tests verify intent): metamorphic property added (adding a matching layer never flips `BaseImage → Unknown`); parameterized mismatch-collapse test (mutation-resistant across all 5 `MismatchReason` variants).
- Rule 11 (match conventions): `Layer`/`Ecosystem` StrEnum, `UnknownReason` Literal, `AdapterConfidence` StrEnum — mirror shipped patterns exactly.

**Precedent (codebase shape to mirror):**
- `src/codegenie/primitives/vuln_provenance/protocols.py` (S1-04, shipped) — frozen four-positional-arg `attribute` Protocol.
- `src/codegenie/primitives/vuln_provenance/factory.py` (S2-02, shipped) — `_DI_KWARGS` closed set + documented amendment protocol.
- `src/codegenie/primitives/vuln_provenance/assembly.py` (S2-04, shipped) — positional dispatch through `factory(cls).attribute(cve_id, package_id, image_ref, sbom)`.
- `src/codegenie/primitives/vuln_provenance/types.py` (S1-02/S1-03, shipped) — `UnknownReason` as Literal, `AdapterConfidence` as StrEnum (HIGH/DEGRADED/UNAVAILABLE), `DistroPackage` shape, `BaseImage` variant.
- Sibling story S4-01 (HARDENED, not shipped) — `sbom_verifier.py` shape; 5-value `MismatchReason` union.
- Sibling story S3-02 (HARDENED, `BLOCKED` per CLAUDE.md) — `NpmVulnProvenanceAdapter` shape; the file `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` doesn't exist in the tree yet.
- Sibling story S4-04 — AST fence for shared SBOM read-set (Alpine + Distroless adapters + verifier).

## Critics — findings

### Critic A — Coverage

| Tag | Finding | Severity | Disposition |
|---|---|---|---|
| F-COV-1 | AC-11 named `VerificationMismatch(reason="layer_id_not_in_manifest")` — a single fixture. S4-01's hardened verifier reports 5 `MismatchReason` values, all of which collapse to the adapter's single `"sbom_layer_attribution_absent"` reason. One test cannot prove the collapse across the set — a mutant that handles one reason correctly and drops others would slip. | HARDEN | Rewrote AC-14 as `test_verifier_mismatches_collapse_to_sbom_layer_attribution_absent` parameterized over all 5 `MismatchReason` values; asserts `details["mismatch_reason"]` preserves the specific reason for downstream `sbom.routing_anomaly` event. Impl-outline §4-i documents the 5→1 collapse-with-provenance-preservation contract. |
| F-COV-2 | No AC covers zero-artifact SBOM. Real SBOMs from empty images or broken syft runs return `artifacts=[]`. Story's decision tree would either raise on the artifact-lookup path or silently return the wrong `Unknown` reason. | HARDEN | Added AC-21 `test_empty_sbom_returns_sbom_layer_attribution_absent` — `sbom.artifacts=[]`, slice present with Alpine stages; asserts `Unknown(reason="sbom_layer_attribution_absent", details={"mismatch_reason": "artifact_not_in_sbom"})`. Distinct from AC-15's probe-absent path. |
| F-COV-3 | No AC covers duplicate SBOM artifacts (Syft legitimately emits `(name, version)` collisions across build stages — S4-01 F-COV-5 precedent). Story's implicit "find the artifact" would silent-first-match. | HARDEN | Added AC-20 `test_duplicate_artifacts_use_union_of_locations`, parameterized over both orderings. Impl-outline §4-e-f rewritten to "aggregate the target-artifact `locations[].layerID`s (union across duplicates, drop `None` values)". Mirrors S4-01 F-COV-5. |
| F-COV-4 | No AC covers `BaseImageSlice(stages=[])` — the probe ran but found no stages (e.g., a repo with a Dockerfile that has no `FROM` line the probe could resolve). Story's decision tree would then run the Alpine-stage filter on an empty list → false negative. | HARDEN | Added AC-22 `test_slice_with_empty_stages_returns_probe_absent` — returns `Unknown(reason="base_image_probe_absent", details={"stages_len": "0"})`. Impl-outline §4-c enforces the guard. |
| F-COV-5 | No AC covers `image_ref is None` (a non-container repo — the adapter is still on the `Layer.BASE_IMAGE` walk regardless). Original AC-14 conflated this with the ecosystem filter and gave an unclear outcome. | HARDEN | Added AC-17 `test_no_image_ref_returns_probe_absent` — coalesces to `Unknown(reason="base_image_probe_absent")`. Impl-outline §4-a makes it the first guard. |
| F-COV-6 | AC-14's "adapter ecosystem filter" tested only distroless; didn't parameterize across `vendor_specific` and `unknown` kinds that also should return `"base_image_not_alpine"`. | HARDEN | Rewrote AC-19 parameterized over `("distroless", "vendor_specific", "unknown")`. `details["observed_kind"]` preserves the specific kind. |
| F-COV-7 | No AC ensures the adapter is instantiable with all four kwargs (only zero-args tested in AC-6). If the `DefaultAdapterFactory` were extended and the `base_image_slice_provider` kwarg went missing on the adapter, tests would still pass because factory silently drops kwargs the adapter doesn't declare. | HARDEN | AC-10 extended: `test_construction_does_no_io` now instantiates with zero args AND with all four DI kwargs; asserts no I/O in either case. |
| F-COV-8 | AC-14's "adapter ecosystem filter" logic (`base_image_kind != "minimal" and != "full"`) had a subtle bug: the story wrote it as a Python expression with two `!=` clauses joined by `and`, but the arch's `base_image_kind` is on individual stages, not the slice. A multi-stage Dockerfile might have one Alpine stage AND one distroless stage; the story didn't specify which to check. | HARDEN | Impl-outline §4-d rewrote as `alpine_stages = [s for s in slice.stages if s.kind in ("minimal", "full")]`; if empty → `Unknown(reason="base_image_not_alpine")`; if non-empty → proceed with those stages. Handles multi-stage cases. |
| F-COV-9 | No AC covers "verifier returns `Ok` but no target artifact has a matching layerID in the manifest" (a valid case where the artifact's layerIDs are `None`-only). The decision tree would then try to construct `BaseImage(layer_digest=None)` — invalid because `LayerDigest` is a `NewType(str)`. | HARDEN | Impl-outline §4-i rewrote: on `VerificationOk`, adapter re-checks that at least one of the target-artifact's `locations[].layerID` values is in the manifest before returning `BaseImage`; otherwise falls through to `Unknown(reason="sbom_layer_attribution_absent", details={"mismatch_reason": "artifact_layer_ids_all_none"})`. Adds a synthetic mismatch reason on the adapter's `details` bag (not on `MismatchReason`, which is S4-01's territory). |

### Critic B — Test Quality

| Tag | Finding | Severity | Disposition |
|---|---|---|---|
| F-TQ-1 | AC-15 exhaustiveness test used `case _: assert_never(_)`. `_` in a `match` arm is the wildcard pattern, NOT a name binding — the arm binds nothing and `_` at the `assert_never` call site is the module-level free name (typically `NameError`). Mutation-thin: the test would fail regardless of whether the exhaustiveness is enforced. | BLOCK-RESOLVED | Fixed AC-23 syntax: `case unreachable: assert_never(unreachable)`. Documented in Notes-for-implementer with `assembly.py`'s working precedent (which passes the tuple explicitly). |
| F-TQ-2 | AC-10 happy-path used a single fixture. A mutant returning `BaseImage(...)` with hard-coded fields unconditionally passes. Same category as S4-01 F-TQ-1. | HARDEN | AC-13 now uses fixture data with three distinct `(package_id, layer_digest)` pairs; each field on the returned `BaseImage` is asserted to match the input fixture (not a hard-coded value). |
| F-TQ-3 | No metamorphic property. A pure-but-wrong implementation that returns constant `BaseImage(...)` for every input passes AC-10; a determinism property (`f(x) == f(x)`) doesn't catch this either. | BLOCK-RESOLVED | Added AC-24 `test_adding_matching_layer_never_flips_ok_to_unknown` — Hypothesis property: adding a fresh matching `BaseImageStage` to a slice that already resolves to `BaseImage` must never flip to `Unknown`, and the `image_digest`/`layer_digest` on the return must stay consistent. Mirrors S4-01 AC-16b. |
| F-TQ-4 | AC-12 tested "returns `Unknown`, does not raise" without asserting the specific `reason` field. A mutant returning `Unknown(reason="adapter_error")` (wrong reason) slips through. | HARDEN | AC-15/AC-16/AC-17/AC-19/AC-22 each assert the exact `reason` value on the returned `Unknown`. AC-18/AC-19 additionally assert the `details` payload. |
| F-TQ-5 | No test for `confidence()`. Compounded by the AC-8 semantic bug: the AC as written (state-dependent on last call) was untestable without mutable state. | BLOCK-RESOLVED | AC-12 rewrote: `confidence()` returns static `HIGH`. Added `test_confidence_is_static_high` (two consecutive calls; still `HIGH` after an `attribute()` returning `Unknown`) and `test_no_mutable_instance_state` (post-call `vars(adapter)` unchanged). |
| F-TQ-6 | AC-18 perf test named only p99 ≤ 20 ms. Median target and hardware-envelope note absent — a flaky bench under load could silently normalize to a slower baseline. | HARDEN | AC-28 adds median ≤ 5 ms + single-process, no-opt-flags note. Bench is honest single-call cost. |
| F-TQ-7 | AC-16 (Gap 3 read-only-known-fields) — no self-test that AC-17's mutation-guard actually catches an intentional mutation attempt. | HARDEN | AC-27 `test_adapter_does_not_mutate_inputs` uses frozen Pydantic instances; `id()` and Pydantic hash pre-call and post-call are compared. |
| F-TQ-8 | AC-14's "SBOM has no artifact matching `package_id`" said "adapter returns `Unknown`" without documenting the `details` payload OR distinguishing from AC-15's `base_image_probe_absent`. | HARDEN | AC-18 rewrote: asserts `details["mismatch_reason"] == "artifact_not_in_sbom"` (aligns with S4-01's fifth `MismatchReason` value); distinct from AC-15's probe-absent path. |

### Critic C — Consistency

| Tag | Finding | Severity | Disposition |
|---|---|---|---|
| F-CON-1 | **AC-7's `repo_context: RepoContext` kwarg breaks the frozen kernel Protocol.** `VulnProvenanceAdapter.attribute()` in `src/codegenie/primitives/vuln_provenance/protocols.py` is fixed at four positional args (`cve_id, package_id, image_ref, sbom`). `assemble_provenance` (S2-04, shipped) calls it positionally. Adding a fifth kwarg requires either (a) amending the Protocol (kernel change, breaks S3-02's `NpmVulnProvenanceAdapter` retroactively) or (b) byte-editing `assembly.py` to pass the kwarg (Phase-7 file, legal per ADR-0009 but a kernel semantic change). | BLOCK-RESOLVED | Rewrote the story's design: the `BaseImageSlice` is read via a DI-injected `base_image_slice_provider` on `__init__`, honored by extending `_DI_KWARGS` per ADR-0007's documented amendment protocol. Protocol signature unchanged (four positional args). `assembly.py` unchanged. AC-7 now covers the ADR-0007 amendment; AC-11 pins the four-positional-arg signature; AC-6/AC-10 add the DI kwarg. |
| F-CON-2 | **AC-8 references `AdapterConfidence.LOW`; no such member exists.** Shipped enum is `HIGH | DEGRADED | UNAVAILABLE`. | BLOCK-RESOLVED | AC-12 rewrote: `confidence()` returns static `AdapterConfidence.HIGH`. Notes-for-implementer explains the enum values + adapter-class-level semantics. |
| F-CON-3 | **AC-8's state-dependent `confidence()` contradicts the Protocol docstring and the impl-outline's "no mutable instance state" clause.** The Protocol says `confidence()` is adapter-class-level (dispatch tie-breaker); per-call confidence rides on `BaseImage.confidence`. AC-8 as written required tracking the last `attribute()` result — untestable without either mutable state or a rebuild-on-call pattern that renders `confidence()` a lie. | BLOCK-RESOLVED | Same as F-CON-2. AC-12's static return + `test_no_mutable_instance_state` locks the discipline. Impl-outline §4 rewrote to `return AdapterConfidence.HIGH`. Per-call confidence is `BaseImage.confidence = AdapterConfidence.HIGH` on successful attribution (populated in AC-13). |
| F-CON-4 | **All ACs use `UnknownReason.X` attribute-access syntax.** Shipped `UnknownReason` is `Literal["sbom_layer_attribution_absent", ..., "dockerfile_parse_failed"]` — string values, not enum members. `UnknownReason.BASE_IMAGE_PROBE_ABSENT` is `AttributeError`. Compounded: `"base_image_probe_absent"` and `"base_image_not_alpine"` are not in the shipped Literal. | BLOCK-RESOLVED | Rewrote every AC with lowercase string-literal syntax. AC-8 (new) additive extension of `UnknownReason` (+2 members: `"base_image_probe_absent"`, `"base_image_not_alpine"`) via edit to Phase-7-owned `types.py` (legal per ADR-0009). |
| F-CON-5 | **Fixture data violates shipped model shapes.** AC-10's `layer_digest_map = {"sha256:xyz...": ("apk", "alpine-3.18.2", "builder")}` does not exist on `BaseImageSlice` (arch line 1136: `paths, stages, confidence` where each `BaseImageStage` has `name, ref, digest, kind`). AC-10's `distro_pkg` tuple `("apk", "alpine-3.18.2", "builder")` does not match `DistroPackage` (`name, version, distro: Literal["alpine", "debian", "ubuntu", "rhel"]`). Executor would hit `ValidationError` at fixture construction. | BLOCK-RESOLVED | Rewrote AC-13 fixture: `BaseImageSlice(paths=[Path("Dockerfile")], stages=[BaseImageStage(name=DockerStageName("builder"), ref=ImageRef("alpine:3.18.2"), digest=ImageDigest("sha256:abc..."), kind="minimal")], confidence="high")`. `DistroPackage(name="openssl", version="3.1.4-r1", distro="alpine")`. All fixtures throughout the story use only shipped-model fields. Notes-for-implementer flags `phase-arch-design.md` line 1136 as the authoritative shape. |
| F-CON-6 | AC-9 mandated `_WARNING_IDS: Final[frozenset[str]]` at import time. Phase 1 ADR-0007's discipline is **probe-only** — probes emit `WarningId`s in their outputs; adapters do not. AC-12/AC-15/AC-17/AC-22 all explicitly say the adapter is silent (no logs). `_WARNING_IDS` is meaningless here. Directly mirrors S4-01 F-CON-8. | HARDEN | Dropped `_WARNING_IDS` from AC-9 and Impl-outline. Notes-for-implementer says explicitly "Do NOT add `_WARNING_IDS`" with the reason and the S4-01 precedent. Renumbered subsequent ACs. |
| F-CON-7 | Story's verifier call `cross_check_sbom_layer_attribution(sbom, image_manifest, artifact_name=..., artifact_version=...)` doesn't match S4-01's shipped signature `(sbom, image_manifest) -> Verification`. S4-01's verifier does not accept per-artifact scoping kwargs — it computes a whole-SBOM verdict. | HARDEN | Impl-outline §4-e-f-g-h rewritten: adapter first filters `sbom.artifacts` via `_find_artifacts_by_package_id` (private helper), then calls the verifier with the full `sbom` + built manifest. Notes-for-implementer paragraph "Verifier invocation shape" explains the rationale. |
| F-CON-8 | Story's References section pointed to `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` as the sibling shape to read. That file does not exist — S3-02 is `BLOCKED` per CLAUDE.md. Executor would read a nonexistent file, find nothing, and either fabricate a shape or reference the wrong precedent. | HARDEN | References section rewrote: "S3-02 hardened story" reframed as the spec-side precedent (`../stories/S3-02-npm-vuln-provenance-adapter.md`); explicit note that the file doesn't exist yet, so read the story, not the (nonexistent) file. |
| F-CON-9 | AC-14's "adapter ecosystem filter" self-guard implied a runtime check on the base-image kind, but the story didn't reconcile with ADR-0006's dispatch policy (`_ADAPTER_DISPATCH_ORDER` iterates all `Layer.BASE_IMAGE` adapters regardless of the ecosystem match — `assemble_provenance` does NOT filter by ecosystem). The self-guard is necessary but rationale absent. | NIT | Notes-for-implementer paragraph in AC-19 clarifies: since `assemble_provenance` walks all `Layer.BASE_IMAGE` adapters (not scoped by `Ecosystem`), each adapter must self-filter. Cross-links to ADR-0006. |
| F-CON-10 | Story acknowledges "This story adds an entire new plugin tree which is additive-only by definition" in its ADRs-honored line, but didn't note the two Phase-7-kernel edits (`_DI_KWARGS`, `UnknownReason`) explicitly as additive-legal-per-ADR-0009. Executor could interpret ADR-0009 as blocking those edits. | NIT | ADRs-honored line rewrote to name the two Phase-7-kernel additive edits explicitly. Files-to-touch section adds "Edited (additive-only, Phase-7-owned files — legal under ADR-0009 which fences Phase 0–6.5 locked files)" heading. |

### Critic D — Design Patterns

| Tag | Finding | Severity | Disposition |
|---|---|---|---|
| F-DP-1 | Story's `repo_context.probes.get("BaseImage")` pattern is stringly-typed dict access — primitive obsession. The `probes` dict has no type, no typed slice, no Protocol boundary. Every consumer would either bare-`getattr` or re-write the same lookup. | BLOCK-RESOLVED-VIA-F-CON-1 | Reframed via F-CON-1 resolution: adapter reads the slice via a typed DI-injected `BaseImageSliceProvider = Callable[[], BaseImageSlice | None]`. Provider is the port (Ports-and-Adapters); production wiring closes over `RepoContext.probes["BaseImage"]` at the loader (S8-01/S8-03), which localizes the stringly-typed access to one call site instead of leaking into every adapter. |
| F-DP-2 | The 5→1 collapse mapping (S4-01's 5 `MismatchReason` → adapter's 1 `"sbom_layer_attribution_absent"`) drops operator-diagnosability data by default. The arch's `sbom.routing_anomaly` event needs the specific reason. Story didn't carry the mapping through. | HARDEN | AC-14 asserts the collapse preserves `details["mismatch_reason"]`. Notes-for-implementer paragraph "Verifier collapse — the 5→1 adapter-surface reason mapping" documents the contract, cross-links to S4-01 F-CON-5. |
| F-DP-3 | Rule-of-three consideration for `_find_artifacts_by_package_id`. Both S4-02 (this) and S4-03 (Distroless) will need artifact lookup by `package_id`. Story didn't note whether to extract to a plugin-shared module now (premature) or defer. | HARDEN | Refactor step in TDD plan says "Do NOT extract `_find_artifacts_by_package_id` to a shared plugin module in this story — the rule-of-three threshold isn't met until N=3." Notes-for-implementer flags the extraction candidate for a future story. |
| F-DP-4 | The DI-vocabulary extension is a real design opportunity — the story's amendment establishes `base_image_slice_provider` as a well-known kwarg for base-image-consuming adapters. Future adapters (RPM, DPKG-for-Ubuntu) inherit the pattern. But the story didn't document the amendment protocol explicitly. | HARDEN | AC-7 codifies the ADR-0007 amendment; Notes-for-implementer paragraph "The ADR-0007 amendment is a story-scope deliverable" walks the executor through all 5 steps in `factory.py`'s module docstring. |
| — (endorsed as-is) | `UnknownReason` as `Literal[...]` — consistent with the shipped pattern (`AdapterConfidence` is `StrEnum` for dispatch keys, `UnknownReason` is `Literal` for reason taxonomy). Correct precedent chosen. | ENDORSE | No edit. |
| — (endorsed as-is) | No `BaseImageSliceReader` port — N=1 in this story, N=2 with S4-03. Rule-of-three not met; the `Callable`-shaped provider is sufficient. | ENDORSE | Notes-for-implementer paragraph "`base_image_slice_provider` fixtures" clarifies the shape. |
| — (endorsed as-is) | Adapter is stateless (no mutable instance state); `confidence()` returns a static class-level value. Correct given the frozen Protocol semantics. | ENDORSE | AC-12 + `test_no_mutable_instance_state` lock it. |
| — (endorsed as-is) | Registration via `@register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.APK)` — Extension by addition: new `(BASE_IMAGE, DPKG)` adapter without editing this file. | ENDORSE | No edit. |

## Stage 3 — Researcher

Not invoked. No `NEEDS RESEARCH` findings; every pattern (metamorphic property, DI-vocabulary extension via ADR-amendment, closed-set string-Literal syntax, static class-level confidence) has direct precedents in this repo (S4-01 metamorphic, `factory.py`'s documented amendment protocol, `types.py`'s Literal discipline, `assembly.py`'s dispatch-time construction).

## Stage 4 — Synthesizer / Editor

Priority conflicts resolved:

- **F-CON-1 (drop `repo_context`) vs. broader story goal (adapter reads probe slice)** — Consistency wins for the kernel Protocol side. The resolution preserves the story's goal (adapter reads a probe slice) via DI-injected provider; the frozen Protocol is preserved; `assembly.py` is untouched. This is the minimum-change fix that honors both the story's intent and the kernel contract.

- **F-CON-4 (rewrite all `UnknownReason.X` to strings) vs. `types.py` additive extension** — Both apply. The syntax fix (Literal string values) is independent of the +2 additive extension. Both landed together; ADR-0009 explicitly permits Phase-7-owned file edits.

- **F-COV-9 (adapter-side synthetic mismatch reason for all-`None` layerIDs) vs. Rule 2 (Simplicity)** — Coverage wins. The synthetic reason is documented on the adapter's `details` bag only (not on `MismatchReason` — that's S4-01's territory). No new closed-set members; the string appears only in a diagnostic dict.

- **F-DP-3 (extract shared helper) vs. Rule 2 rule-of-three deferral** — Rule 2 wins. Extraction is a future story (N=3 threshold).

Edits applied to `docs/phases/07-migration-task-class/stories/S4-02-alpine-vuln-provenance-adapter.md`:

1. **Status line** → `HARDENED (phase-story-validator, 2026-08-14 — pre-executor pass; see _validation/S4-02-alpine-vuln-provenance-adapter.md)`.
2. **`Validation notes` block** inserted after `ADRs honored:` line — summarizes 4 block-severity resolutions, 12 harden-severity edits, 3 nit-severity edits.
3. **ADRs honored** — added coordination note on `_DI_KWARGS` amendment + `UnknownReason` additive extension being legal under ADR-0009 for Phase-7-owned files.
4. **Context §3** rewritten — documents the DI-provider design choice (preserves the frozen Protocol) and the 5→1 mismatch-reason collapse contract with `details["mismatch_reason"]` preservation.
5. **References — where to look** — added arch's `BaseImageSlice` line 1136 pointer; added `factory.py`'s amendment-protocol pointer; added S4-01/S3-02 hardened-story pointers as spec-side (files don't exist yet); explicit note that reading nonexistent files would produce garbage.
6. **Goal** — rewrote to list the four `Unknown` reason paths, the DI extension, and the additive `types.py` edit.
7. **AC-3** — endorsed as-is.
8. **AC-5–AC-7** (new) — DI vocabulary extension: `factory.py` extended, `BaseImageSliceProvider` type alias, ADR-0007 amendment authored inline.
9. **AC-8** (new) — additive `UnknownReason` extension.
10. **AC-9** (was AC-5) — endorsed as-is.
11. **AC-10** (was AC-6) — DI kwargs list now four entries; added all-four-kwargs construction test.
12. **AC-11** (was AC-7) — signature pinned to four positional args; NO `repo_context`; NO keyword-only star.
13. **AC-12** (was AC-8) — `confidence()` returns static `AdapterConfidence.HIGH`; `test_no_mutable_instance_state` added; `LOW → HIGH` fix.
14. **AC-13** (was AC-10) — fixture data rewritten against shipped `BaseImageSlice` + `BaseImageStage` + `DistroPackage` shapes.
15. **AC-14** (was AC-11) — parameterized over all 5 `MismatchReason` values; `details["mismatch_reason"]` preservation asserted.
16. **AC-15/AC-16** (was AC-12) — split into `provider is None` and `provider() returns None` cases.
17. **AC-17** (new) — `image_ref is None` guard.
18. **AC-18** (new) — SBOM has no artifact matching `package_id` — distinct from AC-15's probe-absent.
19. **AC-19** (was AC-14) — parameterized over `("distroless", "vendor_specific", "unknown")`; `details["observed_kind"]` preserved.
20. **AC-20** (new) — duplicate SBOM artifacts (union of `locations[]`, mirrors S4-01 F-COV-5).
21. **AC-21** (new) — zero-artifact SBOM.
22. **AC-22** (new) — empty `stages` list on slice.
23. **AC-23** (was AC-15) — exhaustiveness syntax fixed: `case unreachable: assert_never(unreachable)`; `mypy --strict` negative fixture test added.
24. **AC-24** (new) — Hypothesis metamorphic property.
25. **AC-25** (new) — integration test extension.
26. **AC-26/AC-27** (was AC-16/AC-17) — read-only-known-fields; full escape-hatch list from S4-01 F-COV-2 mirrored; no-input-mutation test.
27. **AC-28–AC-33** — perf/lint/type/fence gates — endorsed; median target added; hardware envelope note.
28. **AC-34** — Story Status → `Done` gate.
29. **Implementation outline §2/§3/§4** — rewrote decision tree, DI vocabulary extension steps, and `UnknownReason` additive extension steps.
30. **TDD plan** — 20+ named tests reflecting the ACs above; metamorphic property; static-confidence test; no-mutable-state test.
31. **Files to touch** — added `factory.py`/`types.py`/ADR-0007 as additive Phase-7-owned edits; added new metamorphic test file; added `Do not touch` line for `protocols.py`/`assembly.py`/`sbom_verifier.py`.
32. **Out of scope** — added: rule-of-three deferral for shared helper; production wiring of `base_image_slice_provider` in loader; closed-set positive fence on `UnknownReason` deferred.
33. **Notes for the implementer** — new/rewritten paragraphs: frozen-Protocol discipline; ADR-0007 amendment protocol walkthrough; `UnknownReason` string-Literal syntax; `AdapterConfidence` values + semantics; no `_WARNING_IDS`; `BaseImageSlice` arch-line pointer; verifier collapse contract; verifier invocation shape; `api.py` scope; layer-to-package mapping ownership; plugin `__init__.py` discipline; `case _: assert_never(_)` doesn't work; performance envelope; rule-of-three deferral; provider fixture pattern.

No edits to: overall Goal *intent* (unchanged — adapter registers at `(BASE_IMAGE, APK)`, reads slice, cross-verifies, returns `BaseImage` or specific `Unknown`); story dependency (S2-04 + S4-01); ADR-0004/ADR-0005 relationships.

## Verdict

**HARDENED.** Story had strong plugin-placement + Gap-3 defensive-guard framing but four block-severity structural issues (kernel Protocol collision, nonexistent enum member, wrong enum access syntax, fixture shapes against invented models) that would have hard-blocked the executor at the first attempt. All four fixed surgically without rewriting scope. The DI-vocabulary extension is a story-scope deliverable that follows `factory.py`'s documented amendment protocol; the `UnknownReason` extension is a legal Phase-7-owned additive edit per ADR-0009. Coverage tightened for zero-artifact SBOM, duplicate artifacts, empty stages, `image_ref is None`, and per-kind non-Alpine cases. Test-quality hardened via metamorphic property, parameterized mismatch-collapse across all 5 `MismatchReason` values, static-confidence assertion, no-mutable-state assertion, `case` syntax fix, and no-input-mutation test. Design-patterns endorsed the frozen Protocol preservation, DI-provider pattern, static class-level confidence, and rule-of-three deferral for shared helpers.

Story is ready for `phase-story-executor` to pick up **once its dependencies (S4-01 verifier + S3-02 npm adapter) ship**. If the executor picks it up before those dependencies land, the ADR-0007 amendment path still works, but the integration test (AC-25) may need to wait for S3-02's plugin tree to exist so the `_REGISTRY` has a non-empty state.

## Files written

- This report: `docs/phases/07-migration-task-class/stories/_validation/S4-02-alpine-vuln-provenance-adapter.md`
- Edited story: `docs/phases/07-migration-task-class/stories/S4-02-alpine-vuln-provenance-adapter.md`
