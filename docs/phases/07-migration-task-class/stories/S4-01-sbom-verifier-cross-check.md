# Story S4-01 — `sbom_verifier.py` cross-check pure function

**Step:** Step 4 — `AlpineVulnProvenanceAdapter` + `DistrolessVulnProvenanceAdapter` + `sbom_verifier.py`
**Status:** Ready
**Effort:** S
**Depends on:** S1-05 (`SyftSbom` Pydantic reader)
**ADRs honored:** Phase 7 ADR-0004 (primitive home — verifier lives in `src/codegenie/primitives/vuln_provenance/`), Phase 7 ADR-0008 (no `vuln.provenance` cache — verifier is a pure function over inputs), production ADR-0033 (domain-modeling discipline — `Verification` is a sum type, `MismatchError` is a typed record, no raw `dict`)

## Context

`assemble_provenance` (Step 2) dispatches `AlpineVulnProvenanceAdapter` (S4-02) and `DistrolessVulnProvenanceAdapter` (S4-03) against a Syft SBOM whose schema deliberately tolerates `extra="allow"` (Phase 2 carry-forward — see `phase-arch-design.md §Data model` + `SyftSbom` definition at line 1037). **Gap 3** in the arch (`phase-arch-design.md §Gap 3 — SBOM byte-level trust beyond layer attribution`) names the danger: a poisoned SBOM can claim a `layerID` that doesn't actually appear in the image's manifest. Without a structural cross-check at adapter time, the Alpine adapter could silently attribute a CVE to `BaseImage(layer_digest=...)` based purely on attacker-controlled text — handing every downstream gate a false-attested record.

`sbom_verifier.py` is the structural defense: a **pure** function `cross_check_sbom_layer_attribution(sbom, image_manifest) -> Verification` that takes the (already-parsed) `SyftSbom` and the (already-resolved) image manifest, and returns a typed sum (`Verification.Ok | Verification.Mismatch(reason)`). It reads **only** the known load-bearing fields from `SyftSbom` — `locations[].layerID`, `name`, `version` — and **never** recurses into the tolerated `extra` content. The verifier is consumed by every base-image adapter (S4-02 + S4-03) and by `NpmVulnProvenanceAdapter` (Step 3) so the same defense applies uniformly across layers.

The function is pure, synchronous, ≤ 80 LOC, no I/O, no logging, no globals — it is a textbook *functional core* under the imperative shell of the adapter calling it (CLAUDE.md §"Functional core / imperative shell"). Its smart-constructor returns `Result[Verification, MismatchError]` so adapter call sites can disambiguate "I successfully ran the check and got a typed mismatch" from "I couldn't even run the check because the inputs were malformed".

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
- **Production ADRs:**
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — `Verification` is a tagged sum, not a bool; `MismatchError` is a frozen Pydantic model, not a `dict`.
  - `../../../production/adrs/0038-vulnerability-provenance-attribution.md` — the primitive's parent ADR; names "SBOM" as the gather-time evidence that adapter-time queries join over.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/result.py` — canonical `Result[T, E] = Ok[T] | Err[E]` (frozen Pydantic discriminated union on `kind`). **Reuse.** Do not create a new `Result` module.
  - `src/codegenie/primitives/vuln_provenance/syft_reader.py` (lands in S1-05) — defines `SyftSbom`, `SyftArtifact`, `SyftLocation`. **Import only these typed names.** Do not duck-type around them.
  - `src/codegenie/primitives/vuln_provenance/errors.py` (lands in S1-04) — `ProvenanceError(CodegenieError)` is the base; `MismatchError(ProvenanceError)` is added by this story.
  - `src/codegenie/types/identifiers.py` — `LayerDigest`, `ImageDigest` (land in S1-01). Used for the typed `image_manifest` parameter shape.

## Goal

Ship `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` exporting a pure function `cross_check_sbom_layer_attribution(sbom, image_manifest) -> Verification` that returns a 2-variant tagged sum (`Ok | Mismatch(reason)`) over the SBOM's claimed layer attribution vs. the image manifest's actual layer set — reading **only** the load-bearing fields (`locations[].layerID`, `name`, `version`), never recursing into the SBOM's `extra` content. Smart-constructor entry point `try_cross_check(...) -> Result[Verification, MismatchError]` handles malformed inputs at the type boundary.

## Acceptance criteria

### Module shape + public surface

- [ ] AC-1 — File `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` exists with `__all__ = ["Verification", "VerificationOk", "VerificationMismatch", "MismatchReason", "ImageManifest", "cross_check_sbom_layer_attribution", "try_cross_check", "MismatchError"]` (sorted, exact).
- [ ] AC-2 — `Verification` is a Pydantic discriminated union over the literal `kind` field with two variants: `VerificationOk(kind=Literal["ok"])` and `VerificationMismatch(kind=Literal["mismatch"], reason: MismatchReason, claimed_layer: LayerDigest | None, known_layers: tuple[LayerDigest, ...])`. Both variants `model_config = ConfigDict(frozen=True, extra="forbid")`.
- [ ] AC-3 — `MismatchReason` is `Literal["sbom_layer_attribution_absent", "layer_id_not_in_manifest", "layer_id_malformed", "sbom_artifact_has_no_locations"]` — no other reasons accepted (additive only via ADR amendment).
- [ ] AC-4 — `ImageManifest` is a frozen Pydantic model `ImageManifest(image_digest: ImageDigest, layers: tuple[LayerDigest, ...])`. `extra="forbid"`. Construction is the caller's responsibility (Phase 7 has no `image_manifest_resolver` shipped — the adapter calls Phase 2's existing `image_digest_resolver` and assembles).
- [ ] AC-5 — `MismatchError(ProvenanceError)` typed exception class is added to `src/codegenie/primitives/vuln_provenance/errors.py` (the only edit to that file in this story).
- [ ] AC-6 — Public `cross_check_sbom_layer_attribution(sbom: SyftSbom, image_manifest: ImageManifest, *, artifact_name: str, artifact_version: str) -> Verification` is a pure function: no I/O, no logging, no globals mutated, deterministic, ≤ 80 LOC body. Module-purity AST fence test asserts the import-set is exactly `{__future__, typing, pydantic, codegenie.result, codegenie.primitives.vuln_provenance.syft_reader, codegenie.primitives.vuln_provenance.errors, codegenie.types.identifiers}` — no `logging`, no `pathlib`, no `subprocess`.
- [ ] AC-7 — Smart-constructor `try_cross_check(sbom, image_manifest, *, artifact_name, artifact_version) -> Result[Verification, MismatchError]` wraps the pure function; returns `Err(MismatchError(...))` only when the inputs cannot be type-checked (e.g., `image_manifest.layers` empty AND SBOM claims a layer). The pure function itself never raises.

### Behavioral correctness — sum-type exhaustive

- [ ] AC-8 — Happy path: SBOM has a `SyftArtifact(name=X, version=Y, locations=[SyftLocation(path=..., layerID="sha256:abc...")])` and `image_manifest.layers` contains that same `LayerDigest` → returns `VerificationOk(kind="ok")`. Round-trip Pydantic-serializable + `extra="forbid"` rejection test.
- [ ] AC-9 — Mismatch: SBOM claims `layerID="sha256:DEADBEEF..."` but `image_manifest.layers = (LayerDigest("sha256:abc..."),)` → returns `VerificationMismatch(reason="layer_id_not_in_manifest", claimed_layer=LayerDigest("sha256:DEADBEEF..."), known_layers=(LayerDigest("sha256:abc..."),))`.
- [ ] AC-10 — Absent attribution: SBOM artifact's `locations` is empty list → `VerificationMismatch(reason="sbom_artifact_has_no_locations", claimed_layer=None, known_layers=...)`. SBOM artifact's `locations[*].layerID is None` for every location → `VerificationMismatch(reason="sbom_layer_attribution_absent", claimed_layer=None, known_layers=...)`.
- [ ] AC-11 — Malformed `layerID`: `SyftLocation.layerID == ""` or doesn't satisfy the `sha256:[0-9a-f]{64}` shape that `LayerDigest`'s smart constructor enforces → `VerificationMismatch(reason="layer_id_malformed", claimed_layer=None, known_layers=...)`. The verifier MUST NOT raise on malformed input; the smart-constructor for `LayerDigest` is wrapped in a `Result` check inside the verifier, not propagated.
- [ ] AC-12 — Multi-location artifact: SBOM has the artifact appearing in multiple locations (legitimate; same package staged into multiple layers); verifier returns `Ok` iff **at least one** location's `layerID` is in `image_manifest.layers`. Other-location entries are not considered failures.
- [ ] AC-13 — Match statement with `assert_never` in `tests/unit/primitives/vuln_provenance/test_sbom_verifier_exhaustiveness.py` — every consumer-side `match` over `Verification` covers `kind="ok"` and `kind="mismatch"` and proves exhaustiveness via `assert_never`.

### Defensive — Gap 3 guard (the heart of this story)

- [ ] AC-14 — The function reads ONLY `sbom.artifacts[i].name`, `sbom.artifacts[i].version`, `sbom.artifacts[i].locations[j].layerID`. The AST fence (`tests/fence/test_sbom_verifier_reads_known_fields_only.py`, sibling to S4-04's adapter fence) walks `sbom_verifier.py` and rejects any `getattr(artifact, "extra", ...)`, `dict(artifact)`, `artifact.model_extra`, `artifact.__pydantic_extra__`, and the patterns `sbom.descriptor[...]` (`SyftSbom.descriptor` is `dict[str, Any]` — explicitly off-limits). No `for k, v in sbom.descriptor.items()`-style recursion.
- [ ] AC-15 — No `dict[str, Any]` anywhere in the module. AST fence (`tests/fence/test_no_any_in_provenance_surface.py` from S1-06) covers this transitively.

### Purity + determinism

- [ ] AC-16 — Hypothesis property test `tests/property/vuln_provenance/test_sbom_verifier_determinism.py` — for any valid pair `(sbom, image_manifest)` drawn from Pydantic-shaped strategies, `cross_check_sbom_layer_attribution(sbom, im) == cross_check_sbom_layer_attribution(sbom, im)`. Determinism + idempotence.
- [ ] AC-17 — Hypothesis property test (same file) — for any drawn `(sbom, image_manifest)`, the function **never raises** any `Exception` (wrap call in `try/except Exception: pytest.fail(...)`). Mirrors the totality discipline established for parsers in Phase 3 S1-01 AC-17.
- [ ] AC-18 — `mypy --strict src/codegenie/primitives/vuln_provenance/sbom_verifier.py tests/unit/primitives/vuln_provenance/test_sbom_verifier.py` clean.
- [ ] AC-19 — `ruff check`, `ruff format --check` clean on touched files.
- [ ] AC-20 — `make lint-imports` green — verifier may not import from `plugins/` (port-before-adapter; S1-06's import-linter contract enforces).
- [ ] AC-21 — Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay green (`make check` — hard pre-merge gate per Phase 7 ADR-0009).
- [ ] AC-22 — Story Status updated to `Done`.

## Implementation outline

1. Add `MismatchError(ProvenanceError)` to `src/codegenie/primitives/vuln_provenance/errors.py` — single typed exception class, `frozen=True, extra="forbid"`, fields `message: str, details: dict[str, str]` (note: `dict[str, str]` is OK at the exception boundary per existing precedent; the `Any` fence covers the typed surface).
2. Create `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` skeleton:
   - Imports per AC-6.
   - `MismatchReason: TypeAlias = Literal[...]`.
   - `VerificationOk(_Frozen)` and `VerificationMismatch(_Frozen)` with `kind: Literal[...]` discriminators.
   - `Verification: TypeAlias = Annotated[VerificationOk | VerificationMismatch, Field(discriminator="kind")]`.
   - `ImageManifest(_Frozen)` with `image_digest: ImageDigest`, `layers: tuple[LayerDigest, ...]`.
3. Implement `cross_check_sbom_layer_attribution(sbom, image_manifest, *, artifact_name, artifact_version) -> Verification`:
   - Find the artifact in `sbom.artifacts` matching `(name == artifact_name, version == artifact_version)`. If absent → `VerificationMismatch(reason="sbom_artifact_has_no_locations", ...)` (sentinel reuse — the artifact-absent and locations-empty cases share the "we cannot attribute" reason; the AST fence + the typed reason still allow the operator to disambiguate via the `claimed_layer=None` signal).
   - If `artifact.locations == []` → same `VerificationMismatch(reason="sbom_artifact_has_no_locations", ...)`.
   - For each `loc in artifact.locations`: if `loc.layerID is None` skip; else try `LayerDigest`'s smart constructor (wrap; do NOT propagate raise) — on parse failure, record `layer_id_malformed`; on parse success, check membership in `image_manifest.layers`.
   - Decision tree: if any location's `LayerDigest` is in `image_manifest.layers` → `VerificationOk`. Else if every `layerID is None` → `VerificationMismatch(reason="sbom_layer_attribution_absent")`. Else if any `layerID` malformed and none matched → `VerificationMismatch(reason="layer_id_malformed", claimed_layer=<first malformed raw string captured as None per type signature>, known_layers=image_manifest.layers)`. Else → `VerificationMismatch(reason="layer_id_not_in_manifest", claimed_layer=<first parseable LayerDigest>, known_layers=image_manifest.layers)`.
4. Add the smart-constructor `try_cross_check(...) -> Result[Verification, MismatchError]` that catches `ValidationError` on `ImageManifest` and returns `Err(MismatchError("invalid image manifest", details={...}))`. Otherwise returns `Ok(cross_check_sbom_layer_attribution(...))`.
5. Write the unit + property + AST-fence tests.
6. Run `make check`, fix lint, commit.

## TDD plan (red → green → refactor)

**Red (write tests first, watch them fail):**
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py::test_ok_when_layer_matches_manifest` — happy path; expect `VerificationOk`. **Fails:** module doesn't exist.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py::test_mismatch_layer_id_not_in_manifest` — claimed layer absent from manifest; expect `VerificationMismatch(reason="layer_id_not_in_manifest")`.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py::test_mismatch_attribution_absent_when_all_layer_ids_none` — every location has `layerID=None`; expect `VerificationMismatch(reason="sbom_layer_attribution_absent")`.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py::test_mismatch_malformed_layer_id` — `layerID="not-a-sha256"`; expect `VerificationMismatch(reason="layer_id_malformed")`. **Critical: must NOT raise.**
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py::test_artifact_not_in_sbom_returns_mismatch_not_raises` — caller queries `(artifact_name="left-pad", version="1.0.0")` but SBOM has no such artifact. Expect typed mismatch.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py::test_multi_location_ok_if_any_matches` — artifact with 3 locations, one matches → `Ok`.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier_exhaustiveness.py::test_match_covers_all_verification_kinds` — `match` over `Verification` with `assert_never`.
- `tests/property/vuln_provenance/test_sbom_verifier_determinism.py::test_determinism` — same input twice → equal result.
- `tests/property/vuln_provenance/test_sbom_verifier_determinism.py::test_totality` — never raises on Hypothesis-drawn inputs.
- `tests/fence/test_sbom_verifier_reads_known_fields_only.py::test_no_extra_access` — AST-walks the module, rejects `getattr(_, "extra", _)`, `model_extra`, `__pydantic_extra__`, `dict(artifact)`, `sbom.descriptor`-touches.

**Green:** implement per §Implementation outline until every red test is green.

**Refactor:** if the decision tree in `cross_check_sbom_layer_attribution` exceeds ~40 lines, extract `_classify_location(loc: SyftLocation, known_layers: frozenset[LayerDigest]) -> _LocationStatus` as a module-private helper (single source of truth for the per-location classification). Keep public surface unchanged.

## Files to touch

**New:**
- `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` (≤ 120 LOC including docstrings + types).
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier.py`.
- `tests/unit/primitives/vuln_provenance/test_sbom_verifier_exhaustiveness.py`.
- `tests/property/vuln_provenance/test_sbom_verifier_determinism.py`.
- `tests/fence/test_sbom_verifier_reads_known_fields_only.py`.

**Edited (additive only):**
- `src/codegenie/primitives/vuln_provenance/errors.py` — add `MismatchError(ProvenanceError)` class.
- `src/codegenie/primitives/vuln_provenance/__init__.py` — re-export `Verification`, `VerificationOk`, `VerificationMismatch`, `MismatchReason`, `ImageManifest`, `cross_check_sbom_layer_attribution`, `try_cross_check`, `MismatchError`.

**Do not touch:**
- `src/codegenie/primitives/vuln_provenance/syft_reader.py` (S1-05 owns it; this story only reads from it).
- Anything under `plugins/` (S4-02 + S4-03 consume the verifier; they ship in separate stories).

## Out of scope

- The Alpine adapter call site (S4-02).
- The Distroless adapter (S4-03).
- The `sbom.routing_anomaly` event emission — the orchestrator emits this when an adapter returns `Unknown(reason="sbom_layer_attribution_absent")`. The verifier itself is silent; it returns a typed value, nothing more.
- Sigstore-bundled signed-SBOM verification (Phase 12 / Phase 13.5 territory; deferred per Gap 3).
- Caching of verification results (Phase 7 ADR-0008 — no cache; verifier is pure and cheap).
- Logging — the verifier is silent; callers log if they want.

## Notes for the implementer

- **The `SyftSbom.descriptor: dict[str, Any]` field is poison.** The Phase 7 arch (`§Data model` line 1042) deliberately leaves it as `dict[str, Any]`. The verifier MUST NOT touch it. The AST fence (AC-14) is the mechanical guard. If you find yourself needing data from `descriptor`, stop — the answer is "no", and the right move is an ADR amendment to widen the verifier's read-set.
- **`Verification` is a 2-variant sum, not a `bool`**. A `bool` return forces every consumer to maintain context-specific reason strings; the typed `MismatchReason` literal puts the reason vocabulary in one enumerable place — operators reading `sbom.routing_anomaly` events see a closed set.
- **`MismatchReason` is closed.** Adding a fifth reason later requires an ADR amendment, mirroring the Phase 7 ADR-0006 closed-tuple discipline for `_ADAPTER_DISPATCH_ORDER`. The five-or-fewer reasons keep operator-side anomaly dashboards human-readable.
- **Why the smart constructor exists.** `cross_check_sbom_layer_attribution` is pure and never raises. `try_cross_check` exists for the **boundary** where the caller's `ImageManifest` is built from external bytes (e.g., a `docker manifest inspect` JSON parsed at adapter time). If the bytes are malformed, that's a `MismatchError`, not a verifier output — keep the two distinct.
- **Performance envelope.** The verifier is called once per `(cve_id, package_id)` resolution; for portfolio scale, that's ~10⁴ calls per gather. With Pydantic `frozen=True` overhead the function is ~5–10 μs; well under the ≤ 50 ms primitive perf envelope. No need to optimize for now.
- **Don't return `None` for "no mismatch"**. `Verification` is a sum; `Ok` is the success arm. `Optional[VerificationMismatch]` would force every caller to `if v is not None`-branch — illegal under sum-type discipline (production ADR-0033).
- **The `sbom.descriptor` Pydantic field type is `dict[str, Any]`**. This may fight the no-`Any` fence from S1-06 — confirm with the S1-05 implementer that `SyftSbom` is admitted as the one tolerated exception per the existing arch text (line 1226: "`SyftSbom` carries `extra="allow"` deliberately"). If the fence rejects `descriptor`'s type, escalate to the S1-05 / S1-06 implementer before forking.
