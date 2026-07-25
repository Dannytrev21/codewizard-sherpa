# Story S4-01 — `sbom_verifier.py` cross-check pure function

**Step:** Step 4 — `AlpineVulnProvenanceAdapter` + `DistrolessVulnProvenanceAdapter` + `sbom_verifier.py`
**Status:** HARDENED (phase-story-validator, 2026-07-24 — pre-executor pass; see `_validation/S4-01-sbom-verifier-cross-check.md`)
**Effort:** S
**Depends on:** S1-05 (`SyftSbom` Pydantic reader)
**ADRs honored:** Phase 7 ADR-0004 (primitive home — verifier lives in `src/codegenie/primitives/vuln_provenance/`), Phase 7 ADR-0008 (no `vuln.provenance` cache — verifier is a pure function over inputs), production ADR-0033 (domain-modeling discipline — `Verification` is a sum type, `MismatchError` is a typed record, no raw `dict`)

## Validation notes (phase-story-validator 2026-07-24)

Ran four critics (coverage / consistency / test-quality / design-patterns). No `NEEDS RESEARCH`. Verdict: **HARDENED**. Substantive edits below; full audit in `_validation/S4-01-sbom-verifier-cross-check.md`.

- **Fence ownership (F-CON-1 · block-resolved):** AC-14's standalone fence file `test_sbom_verifier_reads_known_fields_only.py` collided with S4-04 AC-10 (S4-04's `test_alpine_adapter_reads_known_fields_only.py` explicitly walks all three modules — Alpine adapter, Distroless adapter, `sbom_verifier.py`). Deleted from Files-to-touch. AC-14 downgraded to a *conformance* requirement: the shipped module must pass S4-04's fence when it lands. This eliminates duplicate ownership and lets S4-04 remain the single source of truth for the SBOM read-set policy.
- **Import allowlist (F-CON-2 · block-resolved):** AC-6's frozen import set omitted `codegenie.types.parsers`, but AC-11 requires the verifier to call `LayerDigest`'s smart constructor. That constructor is `parse_layer_digest` in `src/codegenie/types/parsers.py` (`identifiers.py`'s `LayerDigest` is a bare `NewType` — identity, no validation). Added `codegenie.types.parsers` to the allowlist.
- **`try_cross_check` boundary (F-CON-3 / F-DP-1 · block-resolved):** AC-7's original signature took an already-typed `ImageManifest`, so `ValidationError` could never fire — the smart constructor was dead code. Reframed the boundary: `try_cross_check` accepts `image_manifest_raw: Mapping[str, Any]` and constructs `ImageManifest` inside — that's where `ValidationError` is real and `MismatchError` is meaningful. Preserves the goal's smart-constructor discipline without inventing a fake failure path.
- **Metamorphic property (F-TQ-3 · block-resolved):** AC-16's `f(x) == f(x)` determinism alone passes for a broken impl that returns `VerificationOk` unconditionally. Added AC-17b: metamorphic property — adding a `LayerDigest` to `image_manifest.layers` that equals some `loc.layerID` in the SBOM must never flip `Ok → Mismatch`. Catches `all` vs `any` swaps.
- **New MismatchReason `artifact_not_in_sbom` (F-COV-1 · harden):** AC-3 originally overloaded `sbom_artifact_has_no_locations` for two distinct conditions (artifact missing from SBOM entirely vs. artifact present with `locations=[]`). Operators triaging `sbom.routing_anomaly` events lose signal. Added `"artifact_not_in_sbom"` as a distinct fifth reason; split AC-10 accordingly.
- **Capture malformed raw string (F-COV-3 / F-TQ-2 · harden):** AC-11 discarded the raw offending `layerID` string when `parse_layer_digest` failed. Added `claimed_layer_raw: str | None` to `VerificationMismatch` (populated only for `layer_id_malformed`). Extended AC-11's test assertion to pin the raw string round-trip.
- **`image_digest` field (F-COV-4 · harden):** `ImageManifest.image_digest` was declared but unused in the decision tree. Added AC-9b: `VerificationMismatch.image_digest: ImageDigest` populated on every mismatch. Enables cross-workflow correlation of poisoned SBOMs against the same image (`sbom.routing_anomaly` dashboard).
- **Closed-set positive fence for `MismatchReason` (F-DP-2 · harden):** Added AC-20b — `typing.get_args(MismatchReason)` matches an exact tuple. Mirrors Phase 7's `_ADAPTER_DISPATCH_ORDER` closed-tuple discipline. Adding a sixth reason surfaces as a fence break, not a silent additive.
- **Coverage patches (F-COV-5 · harden):** Added ACs for duplicate `(name, version)` artifacts (verifier considers union of all locations), empty `image_manifest.layers=()` tuple, and precedence between `layer_id_malformed` vs. `layer_id_not_in_manifest` when both conditions coexist.
- **`__init__.py` re-export test (F-COV-6 · harden):** Added AC-15b pinning that `codegenie.primitives.vuln_provenance.__all__` contains the eight public names. Mirrors S2-01 export discipline.
- **Mutation-catch strengthening (F-TQ-1 / F-TQ-4 / F-TQ-7 · harden):** Parameterized AC-8's happy-path test with a paired positive/negative fixture (same SBOM, two manifests) so `Ok`-always mutants die. Split AC-10 into two distinct named tests. Added `test_multi_location_mismatch_when_none_match`.
- **Runtime → static exhaustiveness (F-TQ-5 · harden):** Added AC-13b — a `mypy --strict` negative fixture asserts `assert_never` fires when a `match` omits a `Verification` variant. Runtime `assert_never` alone requires the missing branch's input to reach the test.
- **Notes cleanups (F-CON-4, F-CON-5, F-CON-6, F-CON-8, F-DP-3 · nit):** Corrected the `SyftSbom.descriptor` rationale (S1-05 deferred the field; fence guards a *future* addition). Documented the adapter-side lossy 4→1 mapping (all `MismatchReason` collapse to `UnknownReason.SBOM_LAYER_ATTRIBUTION_ABSENT` on the adapter surface; adapters MUST forward the specific `MismatchReason` on `sbom.routing_anomaly` for diagnosability). Clarified `MismatchError` vs. `AdapterError` boundary. Reworded Refactor step to not prescribe `_classify_location` by name. Added anti-pattern: do NOT add `_WARNING_IDS` (probe-only convention per Phase 1 ADR-0007).

## Context

`assemble_provenance` (Step 2) dispatches `AlpineVulnProvenanceAdapter` (S4-02) and `DistrolessVulnProvenanceAdapter` (S4-03) against a Syft SBOM whose schema deliberately tolerates `extra="allow"` (Phase 2 carry-forward — see `phase-arch-design.md §Data model` + `SyftSbom` definition at line 1037). **Gap 3** in the arch (`phase-arch-design.md §Gap 3 — SBOM byte-level trust beyond layer attribution`) names the danger: a poisoned SBOM can claim a `layerID` that doesn't actually appear in the image's manifest. Without a structural cross-check at adapter time, the Alpine adapter could silently attribute a CVE to `BaseImage(layer_digest=...)` based purely on attacker-controlled text — handing every downstream gate a false-attested record.

`sbom_verifier.py` is the structural defense: a **pure** function `cross_check_sbom_layer_attribution(sbom, image_manifest) -> Verification` that takes the (already-parsed) `SyftSbom` and the (already-resolved) image manifest, and returns a typed sum (`Verification.Ok | Verification.Mismatch(reason)`). It reads **only** the known load-bearing fields from `SyftSbom` — `locations[].layerID`, `name`, `version` — and **never** recurses into the tolerated `extra` content. The verifier is consumed by every base-image adapter (S4-02 + S4-03) and by `NpmVulnProvenanceAdapter` (Step 3) so the same defense applies uniformly across layers.

The function is pure, synchronous, ≤ 80 LOC, no I/O, no logging, no globals — it is a textbook *functional core* under the imperative shell of the adapter calling it (CLAUDE.md §"Functional core / imperative shell"). Its smart-constructor `try_cross_check(sbom, image_manifest_raw, ...)` accepts the **raw** manifest bytes (`Mapping[str, Any]`), constructs `ImageManifest` inside a `ValidationError` boundary, and returns `Result[Verification, MismatchError]`. This is the only real failure boundary — once inside the pure function, no exception can escape (AC-17 totality).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §Module tree` (line 248 — `VP_SBOM["sbom_verifier.py"]` placement inside `src/codegenie/primitives/vuln_provenance/`).
  - `../phase-arch-design.md §Scenario D — Failure path (SBOM/manifest mismatch → Unknown)` (lines 488–515 — the verifier's role in the failure flow + the `sbom.routing_anomaly` event the orchestrator emits when it sees a mismatch).
  - `../phase-arch-design.md §Component design §7b. AlpineVulnProvenanceAdapter` (line 752 — "cross-verifies via `sbom_verifier.py`"; mismatch is a `Unknown` return, **not** an exception).
  - `../phase-arch-design.md §Edge cases row #1` (line 1240 — poisoned SBOM → `Unknown(reason="sbom_layer_attribution_absent")` + `sbom.routing_anomaly` emitted by the orchestrator, NOT by the verifier).
  - `../phase-arch-design.md §Data model` (lines 1037–1053 — `SyftSbom` / `SyftArtifact` / `SyftLocation` with `extra="allow"` deliberately; `layerID: str | None` is the load-bearing field).
  - `../phase-arch-design.md §Gap 3 — SBOM byte-level trust beyond layer attribution` (lines 1423–1428 — Phase 12 owns the deeper signature; Phase 7's defensive guard is read-only-known-fields + AST fence in S4-04).
- **Phase ADRs:**
  - `../ADRs/0004-vuln-provenance-primitive-home.md` — `sbom_verifier.py` is named explicitly in §Consequences (line 42); lives at `src/codegenie/primitives/vuln_provenance/sbom_verifier.py`.
  - `../ADRs/0008-no-vuln-provenance-cache-in-phase-7.md` — the verifier MUST be pure / stateless; caching is Phase 14's problem.
- **Sibling story that owns the AST fence:**
  - `S4-04-sbom-tampering-property-and-fence.md` §AC-10 — S4-04's `tests/fence/test_alpine_adapter_reads_known_fields_only.py` walks THREE modules: the Alpine adapter, the Distroless adapter, and `sbom_verifier.py`. **This story does NOT ship a separate fence file.** Ship the module in a fence-passing shape; S4-04's fence enforces it.
- **Production ADRs:**
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — `Verification` is a tagged sum, not a bool; `MismatchError` is a frozen Pydantic model, not a `dict`.
  - `../../../production/adrs/0038-vulnerability-provenance-attribution.md` — the primitive's parent ADR; names "SBOM" as the gather-time evidence that adapter-time queries join over.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/result.py` — canonical `Result[T, E] = Ok[T] | Err[E]` (frozen Pydantic discriminated union on `kind`). **Reuse.** Do not create a new `Result` module.
  - `src/codegenie/primitives/vuln_provenance/syft_reader.py` (S1-05-shipped) — defines `SyftSbom`, `SyftArtifact`, `SyftLocation`. **S1-05 shipped WITHOUT a `descriptor` field** (deferred via `# TODO(future)`); the arch data model mentions it, but the shipped shape is a subset. **Import only these typed names.** Do not duck-type around them.
  - `src/codegenie/primitives/vuln_provenance/errors.py` (S1-04-shipped) — `ProvenanceError(CodegenieError)`, `RegistryError(ProvenanceError)`, `AdapterError(ProvenanceError)` are the shipped three. `MismatchError(ProvenanceError)` is added by this story (see AC-5; distinct from `AdapterError`).
  - `src/codegenie/types/identifiers.py` — `LayerDigest`, `ImageDigest` (S1-01-shipped). Used for the typed `image_manifest` parameter shape. These are bare `NewType` — no validation.
  - `src/codegenie/types/parsers.py` — `parse_layer_digest(s: str) -> Result[LayerDigest, ParseError]` is the smart constructor. This is the module the verifier imports for parsing — NOT `identifiers.py` alone.

## Goal

Ship `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` exporting a pure function `cross_check_sbom_layer_attribution(sbom, image_manifest) -> Verification` that returns a 2-variant tagged sum (`Ok | Mismatch(reason)`) over the SBOM's claimed layer attribution vs. the image manifest's actual layer set — reading **only** the load-bearing fields (`locations[].layerID`, `name`, `version`), never recursing into the SBOM's `extra` content. Smart-constructor entry point `try_cross_check(sbom, image_manifest_raw, ...) -> Result[Verification, MismatchError]` handles the **real** boundary — constructing `ImageManifest` from raw external bytes, catching Pydantic `ValidationError` at that boundary.

## Acceptance criteria

### Module shape + public surface

- [ ] AC-1 — File `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` exists with `__all__ = ["ImageManifest", "MismatchError", "MismatchReason", "Verification", "VerificationMismatch", "VerificationOk", "cross_check_sbom_layer_attribution", "try_cross_check"]` (sorted, exact). `MismatchError` is re-exported here for one-import ergonomics; canonical home is `errors.py`.
- [ ] AC-2 — `Verification` is a Pydantic discriminated union over the literal `kind` field with two variants:
  - `VerificationOk(kind=Literal["ok"])`.
  - `VerificationMismatch(kind=Literal["mismatch"], reason: MismatchReason, claimed_layer: LayerDigest | None, claimed_layer_raw: str | None, known_layers: tuple[LayerDigest, ...], image_digest: ImageDigest)`.
  - Both variants `model_config = ConfigDict(frozen=True, extra="forbid")`.
  - `claimed_layer_raw` is populated **only** for `reason="layer_id_malformed"` (captures the offending string that failed `parse_layer_digest`); `None` for every other reason. `image_digest` is populated on every mismatch — enables cross-workflow correlation of poisoned SBOMs on the `sbom.routing_anomaly` dashboard.
- [ ] AC-3 — `MismatchReason` is `Literal["artifact_not_in_sbom", "layer_id_malformed", "layer_id_not_in_manifest", "sbom_artifact_has_no_locations", "sbom_layer_attribution_absent"]` — exactly **five** members, sorted. **Closed set — additive only via ADR amendment.**
  - `"artifact_not_in_sbom"` — the SBOM contains no artifact matching `(artifact_name, artifact_version)`.
  - `"sbom_artifact_has_no_locations"` — the artifact exists but its `locations` list is empty.
  - `"sbom_layer_attribution_absent"` — the artifact has locations but every `layerID is None`.
  - `"layer_id_malformed"` — at least one `layerID` failed `parse_layer_digest` and none of the parseable ones matched.
  - `"layer_id_not_in_manifest"` — at least one `layerID` parsed cleanly but none are in `image_manifest.layers`.
- [ ] AC-4 — `ImageManifest` is a frozen Pydantic model `ImageManifest(image_digest: ImageDigest, layers: tuple[LayerDigest, ...])`. `extra="forbid"`. Construction is the caller's responsibility (Phase 7 has no `image_manifest_resolver` shipped — the adapter calls Phase 2's existing `image_digest_resolver` and assembles). Note: `image_manifest.layers = ()` is a valid state (image has no readable layers); the verifier handles it — see AC-11c.
- [ ] AC-5 — `MismatchError(ProvenanceError)` typed exception class is added to `src/codegenie/primitives/vuln_provenance/errors.py` (the only edit to that file in this story). **Distinct from `AdapterError`:** `MismatchError` is raised at the verifier's input-validation boundary (malformed raw `ImageManifest` bytes); `AdapterError` is raised inside adapter `attribute()` on runtime failures. Verifier never raises `AdapterError`.
- [ ] AC-6 — Public `cross_check_sbom_layer_attribution(sbom: SyftSbom, image_manifest: ImageManifest, *, artifact_name: str, artifact_version: str) -> Verification` is a pure function: no I/O, no logging, no globals mutated, deterministic, ≤ 80 LOC body. Module-purity AST fence test (`tests/unit/primitives/vuln_provenance/test_sbom_verifier_module_purity.py`) asserts the top-level import-set is exactly `{__future__, collections.abc, typing, pydantic, codegenie.result, codegenie.primitives.vuln_provenance.syft_reader, codegenie.primitives.vuln_provenance.errors, codegenie.types.identifiers, codegenie.types.parsers}` — no `logging`, no `pathlib`, no `subprocess`. **This is a module-purity test, NOT the SBOM-field-read fence** (that's S4-04's ownership; see AC-14).
- [ ] AC-7 — Smart-constructor `try_cross_check(sbom: SyftSbom, image_manifest_raw: Mapping[str, Any], *, artifact_name: str, artifact_version: str) -> Result[Verification, MismatchError]`:
  - Accepts the manifest as a raw `Mapping[str, Any]` (typical shape: parsed JSON from `docker manifest inspect`).
  - Constructs `ImageManifest(**image_manifest_raw)` inside a `try/except ValidationError`. On failure returns `Err(MismatchError(message=..., details={"validation_error": str(e), ...}))`.
  - On success, delegates to `cross_check_sbom_layer_attribution(sbom, manifest, ...)` and wraps in `Ok(...)`.
  - The pure function itself never raises (AC-17).

### Behavioral correctness — sum-type exhaustive

- [ ] AC-8 — Happy path (parameterized positive/negative pair): SBOM has a `SyftArtifact(name=X, version=Y, locations=[SyftLocation(path=..., layerID="sha256:abc...")])`. Two manifests are asserted in the **same** test (`pytest.mark.parametrize` over `(manifest, expected_kind)`): (a) `image_manifest.layers = (LayerDigest("sha256:abc..."),)` → `VerificationOk(kind="ok")`; (b) `image_manifest.layers = (LayerDigest("sha256:zzz..."),)` → `VerificationMismatch(reason="layer_id_not_in_manifest")`. **Kills `Ok`-always mutants** (F-TQ-1). Round-trip Pydantic-serializable + `extra="forbid"` rejection test also included.
- [ ] AC-9 — Mismatch (single-location): SBOM claims `layerID="sha256:DEADBEEF...(64 lowercase hex)"` but `image_manifest.layers = (LayerDigest("sha256:abc...(64 hex)"),)` → returns `VerificationMismatch(reason="layer_id_not_in_manifest", claimed_layer=LayerDigest("sha256:DEADBEEF..."), claimed_layer_raw=None, known_layers=(LayerDigest("sha256:abc..."),), image_digest=<manifest.image_digest>)`. Test asserts **every** field exactly (not just `reason`).
- [ ] AC-10a — Locations empty: SBOM artifact's `locations == []` → `VerificationMismatch(reason="sbom_artifact_has_no_locations", claimed_layer=None, claimed_layer_raw=None, known_layers=<manifest.layers>, image_digest=<manifest.image_digest>)`. Named test: `test_mismatch_when_locations_list_empty`.
- [ ] AC-10b — All `layerID` absent: SBOM artifact has locations but `loc.layerID is None` for every location → `VerificationMismatch(reason="sbom_layer_attribution_absent", claimed_layer=None, claimed_layer_raw=None, known_layers=<manifest.layers>, image_digest=<manifest.image_digest>)`. Named test: `test_mismatch_when_all_layer_ids_none`.
- [ ] AC-10c — Artifact absent from SBOM: caller queries `(artifact_name="left-pad", version="1.0.0")` but SBOM has no such artifact → `VerificationMismatch(reason="artifact_not_in_sbom", claimed_layer=None, claimed_layer_raw=None, known_layers=<manifest.layers>, image_digest=<manifest.image_digest>)`. **This is the new distinct reason** — split out from the old `sbom_artifact_has_no_locations` overload so operator dashboards can distinguish "SBOM never heard of this package" (likely indexer failure) from "SBOM has the package with zero location metadata" (likely Syft bug). Named test: `test_mismatch_when_artifact_not_in_sbom`.
- [ ] AC-11 — Malformed `layerID`: `SyftLocation.layerID == ""` or doesn't satisfy the `sha256:[0-9a-f]{64}` shape that `parse_layer_digest` enforces → `VerificationMismatch(reason="layer_id_malformed", claimed_layer=None, claimed_layer_raw="<the offending string>", known_layers=<manifest.layers>, image_digest=<manifest.image_digest>)`. The verifier MUST NOT raise on malformed input; `parse_layer_digest` is wrapped in a `Result` check inside the verifier, not propagated. Test asserts `claimed_layer_raw` exact-matches the offending string (kills mutants that lose the evidence).
- [ ] AC-11b — Priority when both malformed AND not-in-manifest apply: SBOM has two locations, one with malformed `layerID` and one with a valid `LayerDigest` that isn't in `image_manifest.layers` → `reason="layer_id_malformed"` wins (malformed is strictly worse evidence — attacker-shaped input vs. mere mis-attribution). Named test: `test_priority_malformed_over_not_in_manifest`.
- [ ] AC-11c — Empty manifest `layers=()`: SBOM claims any valid `layerID` but `image_manifest.layers = ()` → `VerificationMismatch(reason="layer_id_not_in_manifest", claimed_layer=<parsed>, claimed_layer_raw=None, known_layers=(), image_digest=<manifest.image_digest>)`. **Must NOT raise; must NOT crash on empty tuple.** Named test: `test_empty_manifest_layers_returns_not_in_manifest`.
- [ ] AC-12 — Multi-location artifact (positive AND inverse):
  - Positive: SBOM has the artifact appearing in multiple locations (legitimate; same package staged into multiple layers); verifier returns `Ok` iff **at least one** location's `layerID` is in `image_manifest.layers`. Other-location entries are not considered failures. Named test: `test_multi_location_ok_if_any_matches`.
  - Inverse: 3 valid `LayerDigest` locations, **none** in `image_manifest.layers` → `VerificationMismatch(reason="layer_id_not_in_manifest")`. Named test: `test_multi_location_mismatch_when_none_match` (kills mutants that return `layer_id_malformed` for the multi-loc case).
- [ ] AC-12b — Duplicate `(name, version)` artifacts in SBOM: Syft legitimately emits the same `(name, version)` twice when a package is staged into both a builder and runtime layer. Verifier must consider the **union** of all matching artifacts' locations before deciding `Ok` vs. mismatch. Named test: `test_duplicate_artifact_uses_union_of_locations` — two matching artifacts, first has no matching layerID, second does → `Ok` (not mismatch from the first artifact alone).
- [ ] AC-13 — Runtime exhaustiveness: `tests/unit/primitives/vuln_provenance/test_sbom_verifier_exhaustiveness.py::test_match_covers_all_verification_kinds` — every consumer-side `match` over `Verification` covers `kind="ok"` and `kind="mismatch"` and proves exhaustiveness via `assert_never`.
- [ ] AC-13b — Static exhaustiveness: `tests/unit/primitives/vuln_provenance/test_sbom_verifier_mypy_negative.py::test_missing_arm_surfaces_mypy_error` — runs `mypy --strict` against an inline fixture `.py` that omits the `mismatch` arm of a `match` on `Verification`; asserts mypy emits an `assert_never` error. Precedent: sibling `test_provenance_mypy_negative.py` / `test_types_mypy_negative.py`. **Static enforcement is what "closed sum type" actually buys us**; the runtime `assert_never` in AC-13 requires the missing branch's input to reach the test.

### Defensive — Gap 3 guard (the heart of this story)

- [ ] AC-14 — **The shipped `sbom_verifier.py` module must pass S4-04's fence when it lands.** S4-04's `tests/fence/test_alpine_adapter_reads_known_fields_only.py` (S4-04 AC-10) walks `sbom_verifier.py` and rejects `getattr(_, "extra", _)`, `_.model_extra`, `_.__pydantic_extra__`, `dict(_)`, `dict(_).items/keys/values`, `sbom.descriptor`, `sbom.descriptor[...]`, `vars(_)`, `_.__dict__`. This story does NOT ship a separate fence file. To keep S4-04 mechanical, the executor MUST ALSO avoid the Pydantic v2 escape hatches enumerated in `Notes for the implementer` §"Fence discipline" (`.model_dump()`, `.model_dump_json()`, `.dict()` (v1 shim), `model_fields_set`, `for f in artifact.model_fields`, `pickle.dumps`) — these are not yet in S4-04's rejection list but expose the same read-any-extra surface; if they slip in, S4-04 will need extension.
- [ ] AC-15 — No `dict[str, Any]` anywhere in the module. AST fence (`tests/fence/test_no_any_in_provenance_surface.py` from S1-06, already shipped) covers this transitively. `MismatchError.details: dict[str, str]` is admitted (concrete value type; not `Any`) per S1-06 fence semantics.
- [ ] AC-15b — `__init__.py` re-export test: `tests/unit/primitives/vuln_provenance/test_sbom_verifier_reexports.py::test_public_names_are_reachable_from_package` — asserts `codegenie.primitives.vuln_provenance.__all__` is a superset of the eight names in AC-1's `__all__` and that each name is importable as an attribute of the package. Prevents "consumer imports from `...sbom_verifier` directly, defeating the primitive boundary" (mirrors S2-01 export discipline).

### Purity + determinism

- [ ] AC-16 — Hypothesis determinism property (`tests/property/vuln_provenance/test_sbom_verifier_determinism.py`): for any valid pair `(sbom, image_manifest)` drawn from **module-local** strategy builders (do NOT depend on S4-04's adversarial strategies — this story ships its own minimal happy-path strategies so it can land before S4-04), `cross_check_sbom_layer_attribution(sbom, im) == cross_check_sbom_layer_attribution(sbom, im)`. Determinism + idempotence.
- [ ] AC-16b — **Metamorphic property (same file):** adding a `LayerDigest` to `image_manifest.layers` that equals some `loc.layerID` in the SBOM must never flip `Ok → Mismatch` (it may only flip `Mismatch → Ok` or stay the same). Formal: for drawn `(sbom, im, extra_layer)` where `extra_layer` equals some parseable `loc.layerID` in the artifact, `cross_check(sbom, im.model_copy(update={"layers": im.layers + (extra_layer,)}))` returns `Ok` if the original returned `Ok`, and returns `Ok` if the original was `Mismatch(reason="layer_id_not_in_manifest")` and `extra_layer` matches. Kills `all` vs `any` swaps.
- [ ] AC-17 — Hypothesis totality property (same file) — for any drawn `(sbom, image_manifest)`, the function **never raises** any `Exception` (wrap call in `try/except Exception: pytest.fail(...)`). Mirrors the totality discipline established for parsers in Phase 3 S1-01 AC-17.
- [ ] AC-17b — `try_cross_check` boundary test: `tests/unit/primitives/vuln_provenance/test_try_cross_check_boundary.py::test_err_on_malformed_manifest_raw` — pass `image_manifest_raw = {"image_digest": "not-a-digest", "layers": "should-be-tuple"}` → returns `Err(MismatchError)` with `details["validation_error"]` non-empty. Kills mutants that let malformed manifests through.
- [ ] AC-18 — `mypy --strict src/codegenie/primitives/vuln_provenance/sbom_verifier.py tests/unit/primitives/vuln_provenance/test_sbom_verifier.py` clean.
- [ ] AC-19 — `ruff check`, `ruff format --check` clean on touched files.
- [ ] AC-20 — `make lint-imports` green — verifier may not import from `plugins/` (port-before-adapter; S1-06's import-linter contract enforces).
- [ ] AC-20b — Positive closed-set fence for `MismatchReason`: `tests/unit/primitives/vuln_provenance/test_mismatch_reason_closed.py::test_reason_literal_is_exactly_five_members` asserts `typing.get_args(MismatchReason) == ("artifact_not_in_sbom", "layer_id_malformed", "layer_id_not_in_manifest", "sbom_artifact_has_no_locations", "sbom_layer_attribution_absent")` (exact tuple, sorted). A silent sixth member surfaces as a fence break. Mirrors Phase 7's `_ADAPTER_DISPATCH_ORDER` closed-tuple discipline.
- [ ] AC-21 — Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay green (`make check` — hard pre-merge gate per Phase 7 ADR-0009).
- [ ] AC-22 — Story Status updated to `GREEN`.

## Implementation outline

1. Add `MismatchError(ProvenanceError)` to `src/codegenie/primitives/vuln_provenance/errors.py` — single typed exception class, fields `message: str, details: dict[str, str]` (note: `dict[str, str]` is OK — concrete value type, not `Any`; the S1-06 fence explicitly permits this).
2. Create `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` skeleton:
   - Imports per AC-6 (including `codegenie.types.parsers` for `parse_layer_digest`).
   - `MismatchReason: TypeAlias = Literal[...]` — five members, sorted.
   - `VerificationOk(_Frozen)` and `VerificationMismatch(_Frozen)` with `kind: Literal[...]` discriminators and the field sets from AC-2.
   - `Verification: TypeAlias = Annotated[VerificationOk | VerificationMismatch, Field(discriminator="kind")]`.
   - `ImageManifest(_Frozen)` with `image_digest: ImageDigest`, `layers: tuple[LayerDigest, ...]`.
3. Implement `cross_check_sbom_layer_attribution(sbom, image_manifest, *, artifact_name, artifact_version) -> Verification`:
   - Find **all** artifacts in `sbom.artifacts` matching `(name == artifact_name, version == artifact_version)`. If none → `VerificationMismatch(reason="artifact_not_in_sbom", claimed_layer=None, claimed_layer_raw=None, known_layers=image_manifest.layers, image_digest=image_manifest.image_digest)`.
   - Take the **union** of `locations` across all matching artifacts (AC-12b). If the union is empty → `VerificationMismatch(reason="sbom_artifact_has_no_locations", ...)`.
   - For each `loc` in the union: if `loc.layerID is None` skip; else call `parse_layer_digest(loc.layerID)`:
     - On `Ok(digest)`: record `digest`; check membership in `image_manifest.layers`.
     - On `Err`: record the raw string as "malformed" (keep the first-seen for `claimed_layer_raw`).
   - Decision tree (AC-11b priority):
     - If any parseable `LayerDigest` is in `image_manifest.layers` → `VerificationOk`.
     - Else if every `layerID is None` (no parseable, no malformed) → `VerificationMismatch(reason="sbom_layer_attribution_absent")`.
     - Else if any malformed was seen → `VerificationMismatch(reason="layer_id_malformed", claimed_layer=None, claimed_layer_raw=<first malformed raw string>, ...)`. **Malformed wins over "not in manifest" (AC-11b).**
     - Else (all parseable, none matched) → `VerificationMismatch(reason="layer_id_not_in_manifest", claimed_layer=<first parseable LayerDigest>, claimed_layer_raw=None, ...)`.
4. Implement `try_cross_check(sbom, image_manifest_raw: Mapping[str, Any], *, artifact_name, artifact_version) -> Result[Verification, MismatchError]`:
   - `try: manifest = ImageManifest(**image_manifest_raw)` inside `except ValidationError as e: return Err(MismatchError(message="invalid image manifest", details={"validation_error": str(e), "artifact_name": artifact_name, "artifact_version": artifact_version}))`.
   - Otherwise: `return Ok(cross_check_sbom_layer_attribution(sbom, manifest, artifact_name=artifact_name, artifact_version=artifact_version))`.
5. Wire `__init__.py` re-exports per AC-1 + AC-15b.
6. Write the unit + property + module-purity + closed-set + boundary tests. **Do NOT write a `test_sbom_verifier_reads_known_fields_only.py` — that's S4-04's ownership.**
7. Run `make check`, fix lint, commit.

## TDD plan (red → green → refactor)

**Red (write tests first, watch them fail):**
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py::test_ok_vs_mismatch_when_layer_matches_or_not` — parameterized happy/inverse pair per AC-8.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py::test_mismatch_layer_id_not_in_manifest_single_location` — full record shape per AC-9.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py::test_mismatch_when_locations_list_empty` — AC-10a.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py::test_mismatch_when_all_layer_ids_none` — AC-10b.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py::test_mismatch_when_artifact_not_in_sbom` — AC-10c (new reason).
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py::test_mismatch_malformed_layer_id_captures_raw` — AC-11 (asserts `claimed_layer_raw` exact-matches).
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py::test_priority_malformed_over_not_in_manifest` — AC-11b.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py::test_empty_manifest_layers_returns_not_in_manifest` — AC-11c.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py::test_multi_location_ok_if_any_matches` — AC-12 positive.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py::test_multi_location_mismatch_when_none_match` — AC-12 inverse.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py::test_duplicate_artifact_uses_union_of_locations` — AC-12b.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier_exhaustiveness.py::test_match_covers_all_verification_kinds` — AC-13.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier_mypy_negative.py::test_missing_arm_surfaces_mypy_error` — AC-13b.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier_reexports.py::test_public_names_are_reachable_from_package` — AC-15b.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier_module_purity.py::test_import_set_matches_allowlist` — AC-6.
- `tests/unit/primitives/vuln_provenance/test_mismatch_reason_closed.py::test_reason_literal_is_exactly_five_members` — AC-20b.
- `tests/unit/primitives/vuln_provenance/test_try_cross_check_boundary.py::test_err_on_malformed_manifest_raw` — AC-17b.
- `tests/property/vuln_provenance/test_sbom_verifier_determinism.py::test_determinism` — AC-16.
- `tests/property/vuln_provenance/test_sbom_verifier_determinism.py::test_metamorphic_add_matching_layer_never_flips_ok_to_mismatch` — AC-16b.
- `tests/property/vuln_provenance/test_sbom_verifier_determinism.py::test_totality` — AC-17.

**Green:** implement per §Implementation outline until every red test is green.

**Refactor:** if the decision tree in `cross_check_sbom_layer_attribution` exceeds ~40 lines, extract a per-location classification helper as a module-private function (implementer's choice of name and signature). Keep public surface unchanged.

## Files to touch

**New:**
- `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` (≤ 120 LOC including docstrings + types).
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py`.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier_exhaustiveness.py`.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier_mypy_negative.py`.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier_reexports.py`.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier_module_purity.py`.
- `tests/unit/primitives/vuln_provenance/test_mismatch_reason_closed.py`.
- `tests/unit/primitives/vuln_provenance/test_try_cross_check_boundary.py`.
- `tests/property/vuln_provenance/test_sbom_verifier_determinism.py`.

**Edited (additive only):**
- `src/codegenie/primitives/vuln_provenance/errors.py` — add `MismatchError(ProvenanceError)` class.
- `src/codegenie/primitives/vuln_provenance/__init__.py` — re-export `Verification`, `VerificationOk`, `VerificationMismatch`, `MismatchReason`, `ImageManifest`, `cross_check_sbom_layer_attribution`, `try_cross_check`, `MismatchError`.

**Do NOT touch:**
- `src/codegenie/primitives/vuln_provenance/syft_reader.py` (S1-05 owns it; this story only reads from it).
- Anything under `plugins/` (S4-02 + S4-03 consume the verifier; they ship in separate stories).
- `tests/fence/test_alpine_adapter_reads_known_fields_only.py` (S4-04 owns; this story ships in a fence-passing shape).

## Out of scope

- The Alpine adapter call site (S4-02).
- The Distroless adapter (S4-03).
- The `sbom.routing_anomaly` event emission — the orchestrator emits this when an adapter returns `Unknown(reason="sbom_layer_attribution_absent")`. The verifier itself is silent; it returns a typed value, nothing more.
- The S4-04 AST-walk fence file — S4-04 owns the fence-of-record for the SBOM read-set on `sbom_verifier.py`.
- Sigstore-bundled signed-SBOM verification (Phase 12 / Phase 13.5 territory; deferred per Gap 3).
- Caching of verification results (Phase 7 ADR-0008 — no cache; verifier is pure and cheap).
- Logging — the verifier is silent; callers log if they want.
- An `ImageManifestSource` port — with N=2 consumers (S4-02, S4-03), rule-of-three isn't met. Callers wrap Phase 2's `image_digest_resolver`. Document in Notes.

## Notes for the implementer

- **Fence discipline (S4-04 is watching).** S4-04's AC-8/9 hard-code an allowlist `{"name", "version", "artifacts", "locations", "layerID", "path"}` and a rejection list for `.extra`, `.model_extra`, `.__pydantic_extra__`, `dict(_)`, `.descriptor`, `vars(_)`, `.__dict__`. **Additionally avoid** these Pydantic v2 escape hatches (not yet in S4-04's list but same-shape violations — flagged by phase-story-validator F-COV-2): `.model_dump()`, `.model_dump_json()`, `.dict()` (v1 shim), `.model_fields_set`, `for f in artifact.model_fields`, `pickle.dumps(_)`, `_.__pydantic_fields_set__`. Reading known fields via direct attribute access (`artifact.name`, `loc.layerID`) is the only sanctioned path.
- **The `SyftSbom.descriptor` field is a *future* concern.** S1-05 deliberately deferred `descriptor` (see `syft_reader.py` line 27 `# TODO(future)`); the shipped `SyftSbom` has only `artifacts`. S4-04's fence still rejects `sbom.descriptor[...]` defensively so that when a later story lands the field, no adapter can silently start reading it. Do not touch `descriptor` in this story. If you find yourself needing data from `descriptor`, stop — the answer is "no", and the right move is an ADR amendment to widen the verifier's read-set.
- **Adapter-side lossy mapping (S4-02/S4-03 will need this).** Arch Scenario D collapses all four verifier `MismatchReason` values to the single `UnknownReason.SBOM_LAYER_ATTRIBUTION_ABSENT` on the adapter surface (the seven-variant `Unknown` union is a stable contract; adding four sub-reasons is out of Phase 7 scope). To preserve operator diagnosability, S4-02/S4-03 **MUST forward the specific `MismatchReason`** on a structured `sbom.routing_anomaly` event field (e.g., `{"kind": "sbom.routing_anomaly", "mismatch_reason": "layer_id_malformed", "claimed_layer_raw": "..."}`). Otherwise the five-reason vocabulary shipped here is dead surface. This is a note for S4-02/S4-03; S4-01 just ships the typed values.
- **`Verification` is a 2-variant sum, not a `bool`**. A `bool` return forces every consumer to maintain context-specific reason strings; the typed `MismatchReason` literal puts the reason vocabulary in one enumerable place — operators reading `sbom.routing_anomaly` events see a closed set.
- **`MismatchReason` is closed.** Adding a sixth reason later requires an ADR amendment, mirroring the Phase 7 ADR-0006 closed-tuple discipline for `_ADAPTER_DISPATCH_ORDER`. AC-20b's positive fence catches accidental additions.
- **Why the smart constructor exists.** `cross_check_sbom_layer_attribution` is pure and never raises (AC-17). `try_cross_check` exists for the **real boundary** — the caller has raw manifest bytes (typical shape: parsed JSON from `docker manifest inspect`) and needs the Pydantic `ValidationError` caught. If the bytes are malformed, that's a `MismatchError`, not a verifier output — keep the two distinct.
- **`MismatchError` vs. `AdapterError` — distinct classes for distinct boundaries.** `MismatchError` = verifier input boundary (raw manifest bytes fail Pydantic validation). `AdapterError` = adapter runtime failure (e.g., SBOM layer attribution absent for a specific row inside `attribute()`). Never conflate; `assemble_provenance` catches `ProvenanceError` at the top and maps to `Unknown(reason="adapter_error")` in both cases.
- **Do NOT add `_WARNING_IDS`.** That `Final[frozenset[str]]` catalog is a **probe-only** convention per Phase 1 ADR-0007. The verifier is silent (no logging, no warning IDs); adding the catalog is Rule-2 over-engineering.
- **Performance envelope.** The verifier is called once per `(cve_id, package_id)` resolution; for portfolio scale, that's ~10⁴ calls per gather. With Pydantic `frozen=True` overhead the function is ~5–10 μs; well under the ≤ 50 ms primitive perf envelope. No need to optimize for now.
- **Don't return `None` for "no mismatch"**. `Verification` is a sum; `Ok` is the success arm. `Optional[VerificationMismatch]` would force every caller to `if v is not None`-branch — illegal under sum-type discipline (production ADR-0033).
- **No `ImageManifestSource` port.** N=2 consumers (S4-02, S4-03) both build the manifest via Phase 2's `image_digest_resolver` + a `docker manifest inspect` call. Rule-of-three not met; skip the port. If Phase 8+ adds a third consumer, elevate then.
