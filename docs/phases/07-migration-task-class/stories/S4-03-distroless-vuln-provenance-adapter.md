# Story S4-03 — `DistrolessVulnProvenanceAdapter` (already-distroless detection)

**Step:** Step 4 — `AlpineVulnProvenanceAdapter` + `DistrolessVulnProvenanceAdapter` + `sbom_verifier.py`
**Status:** HARDENED (phase-story-validator, 2026-08-14 — pre-executor pass; see `_validation/S4-03-distroless-vuln-provenance-adapter.md`)
**Effort:** S
**Depends on:** S2-04 (`assemble_provenance` + `_ADAPTER_DISPATCH_ORDER`), S4-01 (`sbom_verifier.py` — read for shape only; the Distroless adapter does not call the verifier), S4-02 (plugin tree bootstrap + `adapters/__init__.py` + `api.py` + the `_DI_KWARGS` amendment adding `base_image_slice_provider` + the `UnknownReason` extensions `"base_image_probe_absent"` and `"base_image_not_alpine"`)
**ADRs honored:** Phase 7 ADR-0004 (primitive home — adapter lives under the plugin), Phase 7 ADR-0005 (plugin-contributed probes + adapters), Phase 7 ADR-0007 (registry stores classes, not instances; DI via factory — this story reuses the `base_image_slice_provider` kwarg S4-02 added), Phase 7 ADR-0009 (byte-edit allowlist — this story adds a single new adapter file under the S4-02-bootstrapped plugin tree, plus one additive extension to Phase-7-owned `types.py` — `UnknownReason` gains `"base_image_not_distroless"`)

## Validation notes (2026-08-14)

Nine **BLOCK-severity** structural issues were resolved without changing the story's goal or scope. Seven of them mirror the S4-02 sibling story's blocks (`_validation/S4-02-alpine-vuln-provenance-adapter.md`); two are Distroless-specific:

1. **Kernel Protocol collision** — original AC-3 declared `attribute(self, *, cve_id, package_id, image_ref, sbom, repo_context: RepoContext) -> Provenance` (keyword-only, five parameters including `repo_context`). The shipped `VulnProvenanceAdapter` Protocol (`src/codegenie/primitives/vuln_provenance/protocols.py`) is frozen at **four positional args** (`cve_id, package_id, image_ref, sbom`) and `assemble_provenance` (S2-04, shipped in `assembly.py`) calls it positionally with those four. Adding a fifth kwarg or forcing keyword-only would break the frozen contract. Resolution: mirror S4-02's solution — the `BaseImageSlice` is read via the DI-injected `base_image_slice_provider: BaseImageSliceProvider | None = None` that S4-02 adds to the closed `_DI_KWARGS` vocabulary. No new ADR-0007 amendment; the Distroless adapter inherits S4-02's amendment.
2. **`AdapterConfidence.LOW` does not exist** — original AC-4 branched on `HIGH` vs `LOW`. Shipped `AdapterConfidence` (`types.py`) is `HIGH | DEGRADED | UNAVAILABLE`. Compounded by a semantic error: `confidence()` per the Protocol docstring is **adapter-class-level static** (used by the dispatch tie-breaker), NOT per-call state. Resolution: `confidence()` returns static `AdapterConfidence.HIGH`; the per-call decision is expressed through the `Unknown.reason` discriminator instead.
3. **`UnknownReason.BASE_IMAGE_ALREADY_DISTROLESS` attribute-access syntax vs closed `Literal[...]` shape** — every original AC used enum syntax (`UnknownReason.BASE_IMAGE_ALREADY_DISTROLESS`, `.BASE_IMAGE_NOT_DISTROLESS`, `.BASE_IMAGE_PROBE_ABSENT`). Shipped `UnknownReason` is a `Literal[...]` union of lowercase strings. Attribute access would `AttributeError` at runtime. Resolution: all ACs rewritten with lowercase string literals.
4. **Missing `UnknownReason` value** — original AC-9/AC-10/AC-11 referenced `"base_image_not_distroless"`, which is not in the shipped Literal. S4-02 adds `"base_image_probe_absent"` and `"base_image_not_alpine"` (siblings). Resolution: this story additively extends `UnknownReason` with exactly one new value, `"base_image_not_distroless"` (legal per ADR-0009 — `types.py` is a Phase 7 file). Landed in the same PR as this adapter.
5. **`BaseImageSlice` shape mismatch** — original AC-8 through AC-12 read `repo_context.probes["BaseImage"].kind` (top-level `kind` on the slice). Shipped `BaseImageSlice` (per `phase-arch-design.md` line 1136–1145) is `paths: list[Path], stages: list[BaseImageStage], confidence: Literal[...]`; each `BaseImageStage` carries `kind: Literal["distroless","minimal","full","vendor_specific","unknown"]`. There is **no top-level `kind`** — `kind` is per-stage. Resolution: the adapter's decision tree operates over `slice.stages`, not `slice.kind`; the story pins "distroless" as **the last stage's `kind`** (see BLOCK-9 for the multi-stage rationale).
6. **`_WARNING_IDS` misuse** — original AC-5 declared `_WARNING_IDS: Final[frozenset[str]] = frozenset({"distroless_provenance.base_image_probe_absent"})`. Phase 1 ADR-0007's `_WARNING_IDS` + `raise AssertionError` discipline is **probe-only**; adapters are silent (typed `Provenance` returns; no warnings emitted). S4-02 dropped this per S4-01 F-CON-8 mirror. Resolution: `_WARNING_IDS` removed from all ACs. Adapter emits no logs, no warnings.
7. **`repo_context` doesn't reach the adapter** — original AC-6 and Implementation outline §2 read `repo_context.probes.get("BaseImage")`, but `attribute()` never receives a `repo_context` (BLOCK-1 above). Resolution: the adapter reads the slice via `self._base_image_slice_provider()` (the S4-02-amended DI kwarg). Production wiring — building a real provider that closes over `RepoContext.probes["BaseImage"]` — lands with the plugin loader (S8-01 / S8-03).
8. **Composition-loss on the `Unknown.reason` signal (Distroless-specific)** — the original Context claimed the "return on a positive detection is `Unknown(reason="base_image_already_distroless")` — a typed signal to the migration plugin's match step". But `assemble_provenance` (shipped in `assembly.py` lines 173–187) treats **every** `Unknown` return as "continue walking to the next adapter"; if both the Alpine adapter and this adapter return `Unknown` for a distroless-target repo, the composed `Provenance` collapses to `Unknown(reason="no_adapter_resolved")` and the specific `"base_image_already_distroless"` reason is **lost** before Step 8's resolver / match step sees it. Resolution: the Context is corrected to state that (a) the raw adapter return is the authoritative signal, (b) Step 8's `PluginResolver` / match step must consume the raw adapter output (or a preserved-details bag) rather than the composed `Provenance`, and (c) resolving the composition-preservation question is a **Step 8 / S8-03 concern** that this story explicitly does not attempt. A `TODO(step-8)` inline comment in the adapter module docstring anchors the deferral. This is not a S4-03 bug — it is a phase-arch handoff gap that must be surfaced.
9. **Multi-stage Dockerfile ambiguity** — original AC-8 (`slice.kind == "distroless"`) hid a multi-stage question: what if a repo's Dockerfile has one distroless stage AND one non-distroless stage? For migration purposes, the **final** stage (the runtime image) is what determines whether migration applies — a builder stage using debian-slim followed by a distroless runtime stage means the repo is already migrated. Resolution: the decision tree is pinned to `slice.stages[-1].kind` (the last-listed stage, matching Dockerfile FROM order). A separate AC (AC-16) covers the multi-stage case explicitly: mixed builder + distroless-runtime → `"base_image_already_distroless"`; distroless-builder + non-distroless-runtime → `"base_image_not_distroless"` (needs migration).

Six **HARDEN-severity** tightening edits: parameterized-kind test (all five `BaseImageStage.kind` values); `assert_never` exhaustiveness with a named capture (`case unreachable: assert_never(unreachable)`) — `_` in a `match` arm is the wildcard, not a name; `image_ref is None` guard (mirror S4-02 AC-17); empty-stages guard (mirror S4-02 AC-22); integration test extension against `assemble_provenance` to lock the composition semantics (including the composition-loss BLOCK-8 observation as an explicit `pytest.xfail`-style assertion); `test_no_mutable_instance_state` mirror.

Three **NIT-severity** touch-ups folded in.

No goal or scope change. The story remains "ship the `DistrolessVulnProvenanceAdapter` at `(BASE_IMAGE, DPKG)`; refuse on positive distroless detection; do not touch the SBOM; degrade cleanly when the probe slice is absent".

## Context

`DistrolessVulnProvenanceAdapter` is the **refuser**. Unlike `AlpineVulnProvenanceAdapter` (S4-02), which *attributes* a vulnerable package to the Alpine `apk` database, this adapter exists to **recognize that a repo's final base image is already distroless** (e.g., `FROM cgr.dev/chainguard/node` or `FROM gcr.io/distroless/nodejs20`) and **refuse to attribute**. Its return on a positive detection is `Unknown(reason="base_image_already_distroless", details={"final_stage_kind": "distroless"})` — a typed signal that the migration plugin's match step (Step 8) will consume to report `Applicability.NotApplicable`.

**Known composition-loss gap (Step 8 / S8-03 concern).** `assemble_provenance` (S2-04, shipped) treats every `Unknown` return as "continue walking within the layer-set". If both the Alpine adapter and this adapter return `Unknown` for a distroless-target repo, the composed `Provenance` collapses to `Unknown(reason="no_adapter_resolved")` — the specific `"base_image_already_distroless"` reason is **lost** by the time the composed result reaches Step 8's resolver. Preserving this signal end-to-end (either by having Step 8's resolver consume raw adapter outputs, or by adding a "definitive-Unknown" semantics to `assemble_provenance`) is deliberately out of scope for S4-03. This story ships the adapter and its raw output contract; a `TODO(step-8)` inline note in the module docstring anchors the handoff.

The adapter's job is narrow: read the `BaseImageSlice` (via the S4-02-amended `base_image_slice_provider` DI kwarg), inspect **the final stage** (`slice.stages[-1].kind`), return the dedicated `Unknown` reason. If the slice is absent (probe not run or provider not injected), return `Unknown(reason="base_image_probe_absent")` — same defensive degradation as the Alpine adapter.

The adapter is registered at `(Layer.BASE_IMAGE, Ecosystem.DPKG)`. Distroless images are debian-derived in practice, hence `DPKG`. The placement is a slight stretch of the ecosystem taxonomy (distroless runtime images intentionally have **no package manager at runtime** — "DPKG" is a label of *provenance*, since the image was built from debian-slim, rather than of runtime package manager). The arch (`phase-arch-design.md §Component design §7c.`) calls this a "placeholder" assignment; a future ADR amendment may introduce `Ecosystem.DISTROLESS_NODE` or similar, but Phase 7 does not need that taxonomy.

**Ordering note.** `Ecosystem` enum declaration order (S2-01, shipped) is `NPM, YARN_BERRY, PNPM, APK, DPKG, RPM` — so within `Layer.BASE_IMAGE`, the Alpine adapter (`APK`) is consulted **before** this adapter (`DPKG`). On a distroless-target repo, Alpine will return `Unknown(reason="base_image_not_alpine")` (per S4-02 AC-19), the walk continues, and Distroless is consulted next. This is the natural composition order — no reordering is needed. The story's earlier claim that "distroless is consulted first" was a documentation error corrected in the 2026-08-14 validation pass.

The adapter is small: ≤ 60 LOC body, no SBOM cross-verification (the verifier is for attribution; this adapter refuses to attribute), no per-call `confidence` state (always static `AdapterConfidence.HIGH` per the Protocol tie-breaker; per-call decision rides on the `Unknown.reason` discriminator).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §7c. DistrolessVulnProvenanceAdapter` (lines 758–763 — full component spec).
  - `../phase-arch-design.md §Component design §7b. AlpineVulnProvenanceAdapter` (S4-02-owned; read as the sibling-shape precedent — DI kwarg surface, static-confidence discipline, `Unknown`-with-details pattern).
  - `../phase-arch-design.md §Edge cases row #3` (line 1364 — "Base image is already distroless → migration plugin returns `NotApplicable`; vuln plugin may still apply if the CVE has app provenance").
  - `../phase-arch-design.md §Data model BaseImageSlice` (lines 1136–1145) — `paths: list[Path], stages: list[BaseImageStage], confidence: Literal["high","medium","low"]`; each `BaseImageStage` has `name: DockerStageName | None, ref: ImageRef, digest: ImageDigest, kind: Literal["distroless","minimal","full","vendor_specific","unknown"]`. **Read this before writing fixtures — there is NO top-level `kind` on the slice.**
  - `../phase-arch-design.md §Component design §2 — Provenance discriminated union` — `Unknown(reason: UnknownReason, details: dict[str, str] | None)`.
  - `../phase-arch-design.md §Control flow` (lines 1194–1203) — the composition semantics that motivate BLOCK-8's Step-8 deferral (`(None, None) → Unknown(no_adapter_resolved)` drops the specific reason).
- **Phase ADRs:**
  - `../ADRs/0004-vuln-provenance-primitive-home.md` — primitive home for `Unknown`/`UnknownReason`; adapter lives under plugin per ADR-0005.
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — adapter lives in the plugin tree.
  - `../ADRs/0007-provenance-adapter-registry-stores-classes.md` — DI-kwarg vocabulary + class-not-instance registration. **S4-02 amends this ADR to add `base_image_slice_provider`; this story inherits that amendment and does not add a further one.**
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` — Phase-7-owned `types.py` may be additively extended; the `UnknownReason` +1 addition (`"base_image_not_distroless"`) is legal.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py` (S4-02-shipped) — the sibling adapter; mirror the `__init__` + `confidence` shape. The `attribute` body is **simpler** here — no SBOM cross-verification, no verifier call, no artifact lookup.
  - `plugins/distroless-migration--node--npm/api.py` (S4-02-shipped) — currently has one side-effect import for `alpine_provenance`. This story adds the second — `from .adapters import distroless_provenance  # noqa: F401`.
  - `src/codegenie/primitives/vuln_provenance/types.py` (S1-02/S1-03, shipped) — `UnknownReason` is a **`Literal[...]` union of lowercase strings**, NOT an enum. `AdapterConfidence` is `StrEnum` with values `HIGH | DEGRADED | UNAVAILABLE` (**no `LOW` member**). S4-02 extends `UnknownReason` with `"base_image_probe_absent"` and `"base_image_not_alpine"`; this story adds `"base_image_not_distroless"` (the third + final Phase-7 addition).
  - `src/codegenie/primitives/vuln_provenance/protocols.py` (S1-04, shipped) — `attribute(self, cve_id, package_id, image_ref, sbom) -> Provenance` — **frozen four-positional-arg kernel contract**. NO `repo_context`.
  - `src/codegenie/primitives/vuln_provenance/factory.py` (S2-02, shipped + S4-02-amended) — `_DI_KWARGS` closed set including `base_image_slice_provider`.
  - `src/codegenie/primitives/vuln_provenance/registry.py` (S2-01, shipped) — `@register_provenance_adapter` decorator; `Layer`/`Ecosystem` StrEnum declaration orders. Confirms `APK` is declared BEFORE `DPKG` within `Ecosystem` (so Alpine runs first — see ordering note in §Context).
  - `src/codegenie/primitives/vuln_provenance/assembly.py` (S2-04, shipped) — the composition logic that motivates BLOCK-8's deferral.
  - **S4-02 hardened story** (`../stories/S4-02-alpine-vuln-provenance-adapter.md`) — canonical sibling for `__init__`, `confidence()`, DI-kwarg consumption, exhaustiveness discipline, no-mutable-state discipline, `_WARNING_IDS` omission rationale.

## Goal

Ship `plugins/distroless-migration--node--npm/adapters/distroless_provenance.py` containing `DistrolessVulnProvenanceAdapter` registered at `(Layer.BASE_IMAGE, Ecosystem.DPKG)`. The adapter:

- Satisfies the frozen `VulnProvenanceAdapter` Protocol — `attribute(self, cve_id, package_id, image_ref, sbom) -> Provenance` (four positional args, exactly).
- Accepts the closed DI kwarg vocabulary on `__init__`: `sbom_reader`, `logger`, `image_manifest_cache`, `base_image_slice_provider` (inherited from S4-02's ADR-0007 amendment). No new kernel edits.
- Reads the `BaseImageSlice` via `self._base_image_slice_provider()` when the provider is injected.
- Inspects **the final stage** (`slice.stages[-1].kind`) and returns:
  - `Unknown(reason="base_image_already_distroless", details={"final_stage_kind": "distroless", "stage_count": <n>})` when the last stage's kind is `"distroless"`.
  - `Unknown(reason="base_image_not_distroless", details={"final_stage_kind": <observed>, "stage_count": <n>})` when the last stage's kind is `"minimal"`, `"full"`, `"vendor_specific"`, or `"unknown"`.
  - `Unknown(reason="base_image_probe_absent", details={"reason": "provider_missing"})` when the provider is `None`.
  - `Unknown(reason="base_image_probe_absent", details={"reason": "provider_returned_none"})` when the provider returned `None` (probe skipped).
  - `Unknown(reason="base_image_probe_absent", details={"reason": "no_image_ref"})` when `image_ref is None`.
  - `Unknown(reason="base_image_probe_absent", details={"stages_len": "0"})` when the slice has no stages.
- **Never touches the SBOM.** The `sbom` parameter is accepted (Protocol requirement) but never read; a fence AST-walks the module to guarantee this.
- Adds exactly one new member to the Phase-7-owned `UnknownReason` Literal: `"base_image_not_distroless"`. (Legal under ADR-0009 — `types.py` is a Phase 7 file.)
- Every path returns typed `Provenance`; no exceptions cross the boundary except `ProvenanceError` subclasses (none are raised in this adapter — it is unconditionally total).

## Acceptance criteria

### `UnknownReason` extension (Phase 7 additive edit)

- [ ] AC-1 — `src/codegenie/primitives/vuln_provenance/types.py` `UnknownReason` `Literal[...]` gains exactly one new member: `"base_image_not_distroless"`. Legal under ADR-0009 because `types.py` is a Phase 7 file. If S4-02 has not yet landed its own `UnknownReason` additions (`"base_image_probe_absent"`, `"base_image_not_alpine"`) by the time this story merges, the executor coordinates with S4-02 to land the three additions together; the sort order among the reason values is not load-bearing.

### Module shape + registration (Phase 7 ADR-0007 compliant)

- [ ] AC-2 — `plugins/distroless-migration--node--npm/adapters/distroless_provenance.py` exists with `class DistrolessVulnProvenanceAdapter` decorated `@register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.DPKG)`.
- [ ] AC-3 — `__init__` accepts only kwargs from the S4-02-amended closed DI vocabulary: `sbom_reader: object | None = None`, `logger: object | None = None`, `image_manifest_cache: object | None = None`, `base_image_slice_provider: BaseImageSliceProvider | None = None`. **No positional args; no I/O at construction.** A pytest test (`test_construction_does_no_io`) instantiates the class with zero args and with all four kwargs (`monkeypatch`'d `open` / `os.stat` / `socket.socket` to raise if touched) and asserts no exception, no logging, no filesystem or network activity.
- [ ] AC-4 — `attribute(self, cve_id: CveId, package_id: PackageId, image_ref: ImageRef | None, sbom: SyftSbom) -> Provenance` — **four positional args exactly matching the frozen `VulnProvenanceAdapter` Protocol (S1-04)**. All parameter types are pinned; no `Any`. **No `repo_context` kwarg; no keyword-only star.** The `BaseImageSlice` is obtained by calling `self._base_image_slice_provider()` when non-`None`.
- [ ] AC-5 — `confidence(self) -> AdapterConfidence` returns the static value `AdapterConfidence.HIGH` (adapter-class-level, per the Protocol docstring — dispatch tie-breaker). Per-call decision rides on the returned `Unknown.reason` discriminator. Test `test_confidence_is_static_high` calls `confidence()` twice without an `attribute()` call in between; asserts both return `AdapterConfidence.HIGH`. Test `test_no_mutable_instance_state` — `vars(adapter)` after any `attribute()` call is identical to `vars(adapter)` post-`__init__` (no `_last_result`, no cache, no counter).
- [ ] AC-6 — Module declares `BaseImageSliceProvider = Callable[[], BaseImageSlice | None]` as a module-local type alias. **`_WARNING_IDS` is intentionally NOT declared** — Phase 1 ADR-0007 is probe-only discipline; adapters are silent (typed returns, no warnings).
- [ ] AC-7 — Side-effect registration wired: `plugins/distroless-migration--node--npm/api.py` gains a second explicit-import line — `from .adapters import distroless_provenance  # noqa: F401`. The `api.py` now has two side-effect import lines (the Alpine one from S4-02 + this one).
- [ ] AC-8 — Test `test_registry_holds_class_not_instance` — after `import distroless_provenance`, `_REGISTRY[(Layer.BASE_IMAGE, Ecosystem.DPKG)] is DistrolessVulnProvenanceAdapter` (`isinstance(_REGISTRY[...], type)` AND identity check). Confirms ADR-0007 compliance.

### Behavioral correctness — final-stage-driven decision tree

- [ ] AC-9 — Positive detection, single stage (`test_single_distroless_stage_returns_already_distroless`): slice has one `BaseImageStage(name=None, ref=ImageRef("cgr.dev/chainguard/node:latest"), digest=ImageDigest("sha256:aaa..."), kind="distroless")`; adapter returns `Unknown(reason="base_image_already_distroless", details={"final_stage_kind": "distroless", "stage_count": "1"})`. Adapter does NOT read `sbom` on this path.
- [ ] AC-10 — Positive detection, multi-stage (`test_multistage_with_distroless_runtime_returns_already_distroless`): slice has two stages — `BaseImageStage(name=DockerStageName("builder"), kind="full", ...)` followed by `BaseImageStage(name=DockerStageName("runtime"), kind="distroless", ...)`; adapter returns `Unknown(reason="base_image_already_distroless", details={"final_stage_kind": "distroless", "stage_count": "2"})`. **This is the load-bearing multi-stage case: only the final stage's kind determines whether migration applies. A builder using debian-slim followed by a distroless runtime is already-migrated.**
- [ ] AC-11 — Negative detection, single stage (`test_single_non_distroless_stage_returns_not_distroless`, parameterized over `("minimal", "full", "vendor_specific", "unknown")`): slice has one stage of the given `kind`; adapter returns `Unknown(reason="base_image_not_distroless", details={"final_stage_kind": <kind>, "stage_count": "1"})`. **The adapter does not raise; it returns the typed signal.**
- [ ] AC-12 — Negative detection, multi-stage with distroless-builder-only (`test_multistage_with_distroless_builder_only_returns_not_distroless`): slice has two stages — `BaseImageStage(kind="distroless", name=DockerStageName("builder"))` followed by `BaseImageStage(kind="full", name=DockerStageName("runtime"))`; adapter returns `Unknown(reason="base_image_not_distroless", details={"final_stage_kind": "full", "stage_count": "2"})`. **Guards the inverse of AC-10 — a distroless earlier stage does not make the repo "already distroless" if the runtime stage isn't.**
- [ ] AC-13 — `base_image_slice_provider is None` (`test_slice_provider_none_returns_probe_absent`): adapter returns `Unknown(reason="base_image_probe_absent", details={"reason": "provider_missing"})`. Adapter emits no logs; no exception raised.
- [ ] AC-14 — `base_image_slice_provider()` returns `None` (`test_slice_provider_returns_none_returns_probe_absent`): adapter returns `Unknown(reason="base_image_probe_absent", details={"reason": "provider_returned_none"})`. Semantically distinct from AC-13's "provider missing" case, preserved via `details["reason"]`.
- [ ] AC-15 — `image_ref is None` (`test_no_image_ref_returns_probe_absent`): the workflow is non-container; adapter returns `Unknown(reason="base_image_probe_absent", details={"reason": "no_image_ref"})` (probe is trivially inapplicable — a `Unknown` variant with a specific reason preserves the operator-facing narrative). Mirror of S4-02 AC-17.
- [ ] AC-16 — Empty stages (`test_slice_with_empty_stages_returns_probe_absent`): `BaseImageSlice(paths=[], stages=[], confidence="low")` returned from provider. Adapter returns `Unknown(reason="base_image_probe_absent", details={"stages_len": "0"})` — a probe slice with zero stages is operationally indistinguishable from a probe that ran-but-found-nothing. Mirror of S4-02 AC-22.
- [ ] AC-17 — Match exhaustiveness (`tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance_exhaustiveness.py::test_match_arms`): the test proves `match attribute(...): case Unknown(): ...; case unreachable: assert_never(unreachable)`. **`_` in a `match` arm is the wildcard, NOT a name — the arm must capture as a named variable (`unreachable`) for `assert_never` to receive a value.** A companion static-side check (`test_missing_arm_surfaces_mypy_error`) asserts mypy emits an `[assert_never]` error when the `Unknown` arm is omitted (precedent: sibling `test_provenance_mypy_negative.py`). The adapter never returns any non-`Unknown` variant; the test documents this exhaustive shape.

### Defensive — no SBOM read (structural AST fence)

- [ ] AC-18 — The adapter does NOT read any attribute of `sbom` — no `sbom.artifacts` iteration, no `sbom.descriptor` access, no `sbom.model_dump()` / `.dict()` / `.model_dump_json()` / `.model_fields_set` / `__pydantic_fields_set__` / `pickle.dumps` call, no `for f in sbom.model_fields` loop, no `getattr(sbom, ...)`. **Behavioral proof** (`test_adapter_does_not_read_sbom`): pass an SBOM with a poison artifact (name/version chosen so that any accidental iteration would surface); adapter's return is identical for a poison-artifact SBOM and a zero-artifact SBOM (proof by output equality on differing inputs).
- [ ] AC-19 — **Structural proof** (`tests/fence/test_distroless_adapter_does_not_touch_sbom.py`): AST-walks the adapter module and rejects every `Attribute` / `Subscript` / `Call` / `Name` node that resolves to the `sbom` parameter of `attribute()` other than the parameter declaration itself. The only permitted use is the parameter name in the signature. The fence enumerates the specific escape-hatch API list from AC-18. Mirrors S4-04's Alpine-side fence in structure.
- [ ] AC-20 — Adapter does NOT mutate the returned `BaseImageSlice` (frozen Pydantic — would raise anyway, but `test_adapter_does_not_mutate_inputs` asserts the adapter does not even attempt a `model_copy(update=...)` or any attribute assignment).

### Integration + composition-loss handoff

- [ ] AC-21 — Integration test extension (`tests/integration/test_provenance_assembly_via_plugins.py`): registers `DistrolessVulnProvenanceAdapter` (plus S4-02's `AlpineVulnProvenanceAdapter`) via the plugin's `api.py` side-effect imports; calls `assemble_provenance(...)` with a fixture-injected `DefaultAdapterFactory(base_image_slice_provider=lambda: <distroless-fixture-slice>)`. Two assertions:
  - (a) When only the Distroless adapter is registered, the composed result is `Unknown(reason="base_image_already_distroless", ...)` (single-adapter case; the specific reason survives when it is the sole `Unknown`).
  - (b) When both Alpine + Distroless are registered and both return `Unknown` on a distroless-target fixture, the composed result is `Unknown(reason="no_adapter_resolved", ...)` — **the specific `"base_image_already_distroless"` reason is lost by `assemble_provenance`'s composition**. This assertion is marked with a `pytest.mark.xfail(strict=False, reason="Step 8 / S8-03 composition-preservation deferral")` label that documents the known gap. When Step 8 lands the resolver contract that preserves the reason, this xfail flips to a strict pass (executor will remove the `xfail` marker at that time).
- [ ] AC-22 — Fence test `tests/fence/test_provenance_primitive_in_plugin_directory.py` (S5-02 extends; this story adds a placeholder assertion-only stub) confirms the adapter class is defined under `plugins/distroless-migration--node--npm/adapters/`, NOT under `src/codegenie/`.

### Hygiene

- [ ] AC-23 — `mypy --strict plugins/distroless-migration--node--npm/adapters/distroless_provenance.py` clean.
- [ ] AC-24 — `ruff check`, `ruff format --check` clean.
- [ ] AC-25 — `make lint-imports` green: the adapter may import from `codegenie.primitives.vuln_provenance.*` and `codegenie.types.identifiers` but NOT from `codegenie.coordinator`, `codegenie.cache`, or any LLM SDK. Import-linter contract extended by S5-03; this story's adapter must respect it.
- [ ] AC-26 — `tests/fence/test_phase7_no_llm.py` (S1-06) green: no `anthropic`/`openai`/`langgraph`/`langchain`/`transformers`/`sentence-transformers`/`torch` reachable from this module's import closure.
- [ ] AC-27 — Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay green (`make check` — hard pre-merge gate per Phase 7 ADR-0009).
- [ ] AC-28 — Story Status updated to `Done` after implementation lands.

## Implementation outline

1. **`UnknownReason` extension** (kernel additive edit; coordinate with S4-02 if not yet landed): `src/codegenie/primitives/vuln_provenance/types.py`'s `UnknownReason = Literal[...]` gains `"base_image_not_distroless"`. (Sort order not load-bearing; append or alphabetize per implementer's taste. If S4-02's additions aren't yet in place at this executor's cut, land all three together and coordinate the PR.)

2. **Author `plugins/distroless-migration--node--npm/adapters/distroless_provenance.py`** (≤ 80 LOC):
   - Module docstring naming Phase 7 ADR-0004 / ADR-0005 / ADR-0007 (and inheriting S4-02's ADR-0007 amendment; no new amendment required). Include a `TODO(step-8)` comment naming BLOCK-8 — the composition-loss deferral to S8-03.
   - **NO `_WARNING_IDS` declaration** (probe-only discipline).
   - `BaseImageSliceProvider = Callable[[], BaseImageSlice | None]` type alias (module-local; if S4-02 exposes this alias, prefer the shared import — rule-of-three watch).
   - `class DistrolessVulnProvenanceAdapter` decorated `@register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.DPKG)`.
   - `__init__(self, *, sbom_reader=None, logger=None, image_manifest_cache=None, base_image_slice_provider=None)` — store args, no I/O.
   - `attribute(self, cve_id, package_id, image_ref, sbom)` — **four positional args exactly matching the frozen Protocol.** The `sbom` parameter is accepted but never referenced (the AST fence AC-19 proves this). Core decision tree:
     a. If `image_ref is None` → `Unknown(reason="base_image_probe_absent", details={"reason": "no_image_ref"})` (AC-15).
     b. If `self._base_image_slice_provider is None` → `Unknown(reason="base_image_probe_absent", details={"reason": "provider_missing"})` (AC-13).
     c. `slice_ = self._base_image_slice_provider()`. If `slice_ is None` → `Unknown(reason="base_image_probe_absent", details={"reason": "provider_returned_none"})` (AC-14).
     d. If `not slice_.stages` → `Unknown(reason="base_image_probe_absent", details={"stages_len": "0"})` (AC-16).
     e. `final_stage = slice_.stages[-1]`; `stage_count = str(len(slice_.stages))`.
     f. If `final_stage.kind == "distroless"` → `Unknown(reason="base_image_already_distroless", details={"final_stage_kind": "distroless", "stage_count": stage_count})` (AC-9/AC-10).
     g. Else → `Unknown(reason="base_image_not_distroless", details={"final_stage_kind": final_stage.kind, "stage_count": stage_count})` (AC-11/AC-12).
   - `confidence(self) -> AdapterConfidence`: `return AdapterConfidence.HIGH` (static; no state).
   - Note the intentional non-mention of `sbom` in the body — the linter may complain (`ARG002 unused-method-argument`). Use `# noqa: ARG002` on the `sbom` parameter or add a `del sbom` shim at the first line if the codebase convention prefers explicit un-use. Check `alpine_provenance.py`'s handling of `image_manifest_cache` / any other unused DI kwarg first.

3. **Add the second side-effect import to `plugins/distroless-migration--node--npm/api.py`** — `from .adapters import distroless_provenance  # noqa: F401`.

4. **Author the test files** per the TDD plan.

5. **Run `make check`, fix lint, commit.** Confirm `bench/vuln-remediation/` cassette replay still green (Phase-3 hard gate — Phase 7 does not regress).

## TDD plan (red → green → refactor)

**Red (write tests first, watch them fail):**

`tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance.py`:

- `test_construction_does_no_io` (AC-3) — instantiate with zero args and with all four DI kwargs; monkeypatched `builtins.open`, `os.stat`, `socket.socket` raise if touched. Also asserts no `logger.info/warning/error` call (structlog mock).
- `test_registry_holds_class_not_instance` (AC-8) — after `import distroless_provenance`, `_REGISTRY[(Layer.BASE_IMAGE, Ecosystem.DPKG)] is DistrolessVulnProvenanceAdapter`.
- `test_confidence_is_static_high` (AC-5) — two consecutive calls return `AdapterConfidence.HIGH`; still `HIGH` after an `attribute(...)` call that returned `Unknown`.
- `test_no_mutable_instance_state` (AC-5) — after any `attribute(...)` call, `vars(adapter)` is unchanged compared to post-`__init__`.
- `test_single_distroless_stage_returns_already_distroless` (AC-9).
- `test_multistage_with_distroless_runtime_returns_already_distroless` (AC-10).
- `test_single_non_distroless_stage_returns_not_distroless` (AC-11) — parameterized over `("minimal", "full", "vendor_specific", "unknown")`; asserts exact `reason` and `details["final_stage_kind"]`.
- `test_multistage_with_distroless_builder_only_returns_not_distroless` (AC-12).
- `test_slice_provider_none_returns_probe_absent` (AC-13) — asserts `details["reason"] == "provider_missing"`.
- `test_slice_provider_returns_none_returns_probe_absent` (AC-14) — asserts `details["reason"] == "provider_returned_none"`.
- `test_no_image_ref_returns_probe_absent` (AC-15) — asserts `details["reason"] == "no_image_ref"`.
- `test_slice_with_empty_stages_returns_probe_absent` (AC-16) — asserts `details["stages_len"] == "0"`.
- `test_adapter_does_not_read_sbom` (AC-18) — pass an SBOM with a poison artifact (name = `"POISON"`, version = `"POISON"`, `locations=[SyftLocation(path="/POISON", layerID="POISON")]`); assert return is identical to the same call with `sbom=SyftSbom(artifacts=[], descriptor=...)`. Output equality proves the adapter doesn't branch on SBOM content.
- `test_adapter_does_not_mutate_inputs` (AC-20) — pass frozen `BaseImageSlice` fixture; `id()` and Pydantic hash unchanged post-call.

`tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance_exhaustiveness.py`:

- `test_match_arms` (AC-17) — `case Unknown()`, `case unreachable: assert_never(unreachable)`. **`unreachable` is the arm-name capture; `case _:` alone cannot pass a value to `assert_never`.**
- `test_missing_arm_surfaces_mypy_error` (AC-17 static side) — runs `mypy --strict` against an inline fixture that omits the `Unknown` arm; asserts a `[assert_never]`-shaped error line.

`tests/fence/test_distroless_adapter_does_not_touch_sbom.py` (AC-19):

- AST-walks `plugins/distroless-migration--node--npm/adapters/distroless_provenance.py`; enumerates every `Name` node inside `DistrolessVulnProvenanceAdapter.attribute`'s function body whose `id == "sbom"`; asserts the list is empty. Also enumerates `Attribute` nodes with `.value.id == "sbom"` and `Subscript` nodes with `.value.id == "sbom"`; asserts both empty. The permitted appearance is the parameter name in the function signature (AST arg node, not `Name`).

`tests/integration/test_provenance_assembly_via_plugins.py` (extended, AC-21):

- `test_distroless_adapter_alone_preserves_specific_reason` (AC-21a) — register ONLY `DistrolessVulnProvenanceAdapter`; call `assemble_provenance(...)`; assert `Unknown(reason="base_image_already_distroless", ...)`.
- `test_distroless_and_alpine_both_unknown_composes_to_no_adapter_resolved` (AC-21b, `pytest.mark.xfail(strict=False, reason="Step 8 / S8-03 composition-preservation deferral")`) — register BOTH adapters; both return `Unknown` on a distroless-target fixture (Alpine returns `"base_image_not_alpine"`, Distroless returns `"base_image_already_distroless"`); composed result is `Unknown(reason="no_adapter_resolved")` — the specific Distroless reason is lost. Documents the known gap.

`tests/fence/test_provenance_primitive_in_plugin_directory.py` (extended for AC-22):

- Placeholder assertion confirming the adapter class is under `plugins/distroless-migration--node--npm/adapters/`. Full AST fence lands in S5-02.

**Green:** implement per §Implementation outline.

**Refactor:** body is ≤ 40 LOC; no refactor anticipated. **Rule-of-three watch:** the "read slice → inspect a stage's `kind` → return typed `Unknown`" shape is now shared with the Alpine adapter (S4-02) — that is N=2. Do NOT extract a `_classify_by_stage_kind(slice, predicate) -> UnknownReason` helper in this story; wait for the third consumer (a hypothetical future `RhelVulnProvenanceAdapter` or `RuntimeBundledVulnProvenanceAdapter`) to trigger the extract. If S4-02 exposes `BaseImageSliceProvider` from a shared module by the time this story lands, prefer the shared import over redeclaring the alias locally — that alias is the second consumer and the natural hoist point.

## Files to touch

**New:**
- `plugins/distroless-migration--node--npm/adapters/distroless_provenance.py` (≤ 80 LOC).
- `tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance.py`.
- `tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance_exhaustiveness.py`.
- `tests/fence/test_distroless_adapter_does_not_touch_sbom.py`.

**Edited (additive-only, Phase-7-owned files — legal under ADR-0009 which fences Phase 0–6.5 locked files):**
- `plugins/distroless-migration--node--npm/api.py` — add `from .adapters import distroless_provenance  # noqa: F401` line (S4-02 established the file with the Alpine import).
- `src/codegenie/primitives/vuln_provenance/types.py` — extend `UnknownReason` `Literal[...]` (+1 member, `"base_image_not_distroless"`).
- `tests/integration/test_provenance_assembly_via_plugins.py` — two new test cases (AC-21a and AC-21b).
- `tests/fence/test_provenance_primitive_in_plugin_directory.py` — placeholder assertion-only extension.

**Do not touch:**
- `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py` (S4-02-owned; byte-locked once shipped).
- `plugins/distroless-migration--node--npm/__init__.py`, `adapters/__init__.py` (S4-02-owned).
- `src/codegenie/primitives/vuln_provenance/protocols.py` — frozen kernel contract.
- `src/codegenie/primitives/vuln_provenance/assembly.py` — the composition semantics that motivate BLOCK-8's Step-8 deferral are locked here; this story preserves them.
- `src/codegenie/primitives/vuln_provenance/registry.py`, `factory.py` (factory was amended by S4-02; no further extension here), `errors.py`, `syft_reader.py`.
- `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` (S4-01-owned; this adapter explicitly does not call it).
- Any file under `src/codegenie/probes/` (probes are plugin-contributed per ADR-0005).
- Any file under `plugins/vulnerability-remediation--node--npm/` (Phase 3 plugin; byte-locked except via the S5-01 allowlist).

## Out of scope

- The Alpine adapter (S4-02) — separate ecosystem (`APK`), separate decision tree, cross-verifier path.
- The SBOM-tampering Hypothesis property + AST fence for Alpine (S4-04; this story's sibling fence `test_distroless_adapter_does_not_touch_sbom.py` is stricter — it asserts the adapter doesn't touch the SBOM **at all**, whereas the Alpine fence enumerates a permitted read-set).
- `BaseImageProbe` itself (Step 7).
- Production wiring of the `base_image_slice_provider` in the plugin loader — S8-01 / S8-03. This story uses fixture providers.
- Recognizing alternative distroless registries (e.g., `nvcr.io/nvidia/distroless/*`) — the `BaseImageStage.kind` enum value `"distroless"` is the only signal this adapter reads; Step 7's `BaseImageProbe` classification table (`_BASE_IMAGE_KIND_RULES`) owns the per-registry mapping.
- The `Applicability.NotApplicable` translation — that lives in the migration plugin's match step (Step 8 / Step 11).
- **The composition-preservation fix for `assemble_provenance`** (BLOCK-8 above). Preserving the specific `"base_image_already_distroless"` reason end-to-end is deliberately deferred to Step 8 / S8-03; this story ships the raw adapter output contract and documents the loss via AC-21b's `xfail` assertion. When Step 8's resolver contract lands, the executor removes the `xfail` marker (or the resolver bypasses `assemble_provenance` for match-time signals — either resolution is compatible with this adapter's contract).
- A closed-set positive fence on `UnknownReason` — deferred to a later Phase 7 hardening story.

## Notes for the implementer

- **The adapter is intentionally simple.** Its job is to refuse, cleanly, with a typed signal. Resist the urge to make it "smarter" — e.g., reading the SBOM to corroborate the probe slice. That would defeat the structural separation (`AlpineVulnProvenanceAdapter` does the attribution work; this adapter is the refuser). The AC-19 AST fence is strict: the module must not reference `sbom` anywhere in the body.

- **The frozen `VulnProvenanceAdapter` Protocol is load-bearing.** `attribute(self, cve_id, package_id, image_ref, sbom) -> Provenance` — four positional args, in that order. `assemble_provenance` calls it positionally. Adding a fifth arg, adding `*` for keyword-only, adding `repo_context` — any of these breaks the frozen contract and either forces a byte-edit to `assembly.py` or breaks the Alpine and future adapters. The `BaseImageSlice` is read via the DI-injected `base_image_slice_provider` (inherited from S4-02's ADR-0007 amendment).

- **No new ADR-0007 amendment.** S4-02 added `base_image_slice_provider` to the closed `_DI_KWARGS` set; this story consumes that kwarg. No further factory changes.

- **`UnknownReason` is a `Literal[...]` union, NOT an enum.** Use `"base_image_already_distroless"`, not `UnknownReason.BASE_IMAGE_ALREADY_DISTROLESS`. Use `"base_image_not_distroless"` (the new addition) and `"base_image_probe_absent"` (S4-02-added). All-lowercase snake_case string values throughout.

- **`AdapterConfidence` has NO `LOW` member.** The shipped values are `HIGH | DEGRADED | UNAVAILABLE`. `confidence()` returns the static class-level value used by the dispatch tie-breaker; per-call decisions ride on the `Unknown.reason` discriminator. This adapter's `confidence()` always returns `HIGH` because the adapter is high-confidence about its "not my problem" refusal (it either has direct probe evidence or the typed absence thereof).

- **Do NOT add `_WARNING_IDS`** to the adapter module. Phase 1 ADR-0007's `_WARNING_IDS: Final[frozenset[str]]` + `raise AssertionError` discipline is **probe-only** — probes emit `WarningId`s in their outputs; adapters do not. Mirrors S4-01 F-CON-8 and S4-02's HARDENED discipline.

- **The `BaseImageSlice` shape is authoritative in the arch, not in shipped code.** `phase-arch-design.md §Data model` lines 1136–1145 pin the fields. Step 7's `BaseImageProbe` ships the Pydantic model matching this shape. Fixtures in this story must construct `BaseImageSlice` instances against this shape — `paths: list[Path], stages: list[BaseImageStage], confidence: Literal[...]`. **There is NO top-level `kind` field on the slice**; `kind` lives per-stage on `BaseImageStage`.

- **Multi-stage semantics — the final stage wins.** For migration purposes, `slice.stages[-1].kind` determines whether the repo is already distroless. A repo with a debian builder + a distroless runtime is **already-migrated**; a repo with a distroless builder + a debian runtime **needs migration**. AC-10 and AC-12 lock this via explicit fixtures. If future work shows the final-stage heuristic is wrong (e.g., a probe reports stages in a different order than the Dockerfile lists them), coordinate with Step 7's `BaseImageProbe` owner to pin the ordering contract.

- **`api.py` gets the SECOND side-effect import.** S4-02 established `plugins/distroless-migration--node--npm/api.py` with one line — `from .adapters import alpine_provenance  # noqa: F401`. This story adds a second line — `from .adapters import distroless_provenance  # noqa: F401`. The file now has two lines. S8-01 later adds the rest of `api.py` (plugin instance, TCCM resolver wiring, probe imports); this story does NOT add any of that.

- **Composition-loss gap (BLOCK-8) — how the adapter cooperates with the eventual fix.** The `Unknown.reason="base_image_already_distroless"` signal is not preserved by `assemble_provenance` when a second adapter (Alpine) also returns `Unknown`. This is a known Step 8 / S8-03 concern. The adapter's design cooperates with three possible resolutions: (1) Step 8's resolver reads raw adapter outputs (bypassing `assemble_provenance` for the match-step signal); (2) `assemble_provenance` grows a "definitive Unknown" concept that short-circuits on this reason; (3) the resolver reads `RepoContext.probes["BaseImage"]` directly and this adapter is retained purely for the audit-log completeness path. In all three cases the adapter's raw output contract stays fixed. The `TODO(step-8)` inline note in the module docstring anchors the deferral.

- **`Ecosystem.DPKG` is a placeholder.** Per `phase-arch-design.md §7c.`, distroless images are debian-derived, so `DPKG` is the closest match in the current `Ecosystem` enum. A future ADR amendment may add `Ecosystem.DISTROLESS_NODE` — but Phase 7 does not need that taxonomy. Don't add it now.

- **Ordering: Alpine runs before Distroless in the natural composition.** `Ecosystem` declaration order (S2-01, shipped) is `NPM, YARN_BERRY, PNPM, APK, DPKG, RPM` — so within `Layer.BASE_IMAGE`, `APK` (Alpine) is consulted first, then `DPKG` (this adapter). On a distroless-target repo, Alpine returns `Unknown("base_image_not_alpine")`, the walk continues, this adapter returns `Unknown("base_image_already_distroless")`. The story's earlier claim that "distroless is consulted first" was a documentation error — corrected in the 2026-08-14 validation.

- **The intentional asymmetry with the Alpine adapter.** Alpine: attributes (returns `BaseImage`) OR refuses with a specific reason. Distroless: **always** refuses (returns `Unknown`). This asymmetry is the architecture's load-bearing claim — the Distroless adapter is a pure informational refuser.

- **The AST fence `test_distroless_adapter_does_not_touch_sbom.py` is strict.** Even a `_ = sbom` line (assigning to underscore) is forbidden. The adapter's `attribute` signature accepts `sbom` because the Protocol requires it, but the body never references the parameter. If the linter complains about an unused parameter, use `# noqa: ARG002` on the parameter or the function — check `alpine_provenance.py` (S4-02-shipped) for the codebase-approved noqa placement first.

- **Rule-of-three watch on shared "read-slice-inspect-stage" logic.** N=2 with S4-02's Alpine adapter. Do NOT extract a shared helper in this story. When a third consumer lands (RHEL adapter, RuntimeBundled adapter, etc.), extract at that point. If S4-02 exposes `BaseImageSliceProvider` from a shared module, prefer the import over redeclaring the alias — that alias is the second consumer and its own natural hoist point.

- **Zero LLM reachability.** The adapter must not import `anthropic`, `openai`, `langgraph`, `langchain`, `transformers`, `sentence-transformers`, or `torch` — direct or transitive. The Phase 7 fence (`tests/fence/test_phase7_no_llm.py`, S1-06) catches this. Adapters read typed inputs and return typed outputs; there is no model call anywhere in the vuln-provenance primitive.
