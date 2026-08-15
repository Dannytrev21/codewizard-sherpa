# Validation report — S4-03 `DistrolessVulnProvenanceAdapter`

**Validated:** 2026-08-14 (pre-executor pass)
**Validator:** phase-story-validator
**Verdict:** **HARDENED**
**Story file:** `docs/phases/07-migration-task-class/stories/S4-03-distroless-vuln-provenance-adapter.md`

## Context

Pre-executor validation on a `Ready` (never-shipped) story. The story's core intent — a small, defensive, SBOM-untouching refuser adapter at `(Layer.BASE_IMAGE, Ecosystem.DPKG)` — is architecturally sound. But it inherited **seven of the same block-severity structural bugs** the sibling S4-02 story had (kernel Protocol contradiction, `UnknownReason` enum syntax vs shipped `Literal[str]`, non-existent `AdapterConfidence.LOW`, `_WARNING_IDS` misuse, invented `BaseImageSlice.kind` shape, `repo_context` that the frozen four-arg Protocol does not deliver, and `AdapterConfidence` per-call state that contradicts the Protocol's static-tie-breaker docstring), plus **two Distroless-specific block-severity issues**: (a) an architectural composition-loss gap — `assemble_provenance` (shipped) drops the specific `"base_image_already_distroless"` reason when a second adapter also returns `Unknown` for the same layer, and (b) a multi-stage Dockerfile ambiguity — the original AC-8 read `slice.kind` as if it were a top-level field, hiding the "which stage decides?" question. Six harden-severity tightening edits + three nit-severity touch-ups.

## Context Brief

**Goal (from story):** Ship `plugins/distroless-migration--node--npm/adapters/distroless_provenance.py` — a small refuser adapter that recognizes when a repo's final Dockerfile stage is already distroless and returns a typed `Unknown` signal instead of attempting attribution. Does not touch the SBOM (a strict AST fence proves this).

**Phase-arch constraint:**
- §Component design §7c (lines 758–763) — Distroless adapter: "refuses to attribute — returns `Unknown(reason="base_image_already_distroless")`". Inspects `BaseImageProbe` slice for `base_image_kind == "distroless"`.
- §Data model `BaseImageSlice` (lines 1136–1145) — `paths, stages, confidence`; each `BaseImageStage` has `name, ref, digest, kind: Literal["distroless","minimal","full","vendor_specific","unknown"]`. **No top-level `kind` on the slice.**
- Edge cases row #3 (line 1364) — "Base image is already distroless → migration plugin returns `NotApplicable`".
- §Control flow (lines 1194–1203) — composition semantics: `(None, None) → Unknown(reason="no_adapter_resolved")` — the composed result drops the specific reason.

**Phase ADRs honored:**
- ADR-0004 (primitive home) — adapter under plugin, not `src/codegenie/primitives/`.
- ADR-0005 (probes/adapters live under plugin) — `plugins/distroless-migration--node--npm/adapters/`.
- ADR-0007 (registry stores classes; DI via factory) — story inherits S4-02's amendment adding `base_image_slice_provider` to `_DI_KWARGS`. No new amendment.
- ADR-0009 (Phase 7 byte-edit allowlist) — `types.py` is a Phase-7-owned file; `UnknownReason` +1 addition (`"base_image_not_distroless"`) is legal.

**CLAUDE.md commitments:**
- "Extension by addition" — adding to `UnknownReason` is via additive Literal extension.
- Newtype identifiers: `CveId`, `PackageId`, `ImageRef`, `ImageDigest`, `LayerDigest`, `DockerStageName` throughout.
- Functional core / imperative shell: `attribute()` is a pure decision tree over typed inputs; no I/O.
- Rule 2 (Simplicity First): no premature helper extract — the "read slice → inspect stage → return Unknown" shape is now N=2 (Alpine + Distroless); rule-of-three defers to a hypothetical third adapter.
- Rule 9 (tests verify intent): parameterized-kind test across all five `BaseImageStage.kind` values; multi-stage builder-vs-runtime coverage; behavioral SBOM-untouched test + AST fence.
- Rule 11 (match conventions): `Literal[str]` for `UnknownReason` (not enum), `StrEnum` for `AdapterConfidence`, `match/assert_never` with named-capture arm.
- Rule 12 (fail loud): the composition-loss gap is surfaced via an explicit `xfail`-marked integration test rather than silently hoping Step 8 fixes it.

**Precedent (codebase shape to mirror):**
- `src/codegenie/primitives/vuln_provenance/protocols.py` (S1-04, shipped) — frozen four-positional-arg `attribute` Protocol.
- `src/codegenie/primitives/vuln_provenance/factory.py` (S2-02, shipped; S4-02 amends) — `_DI_KWARGS` closed set including `base_image_slice_provider`.
- `src/codegenie/primitives/vuln_provenance/assembly.py` (S2-04, shipped) — composition drops the specific `Unknown.reason` when both layer adapters return `Unknown`.
- `src/codegenie/primitives/vuln_provenance/types.py` (S1-02/S1-03, shipped) — `UnknownReason` as Literal, `AdapterConfidence` as StrEnum (HIGH/DEGRADED/UNAVAILABLE), `BaseImage` variant.
- Sibling story S4-02 (HARDENED, not yet shipped) — canonical sibling shape; the `_DI_KWARGS` amendment lands with S4-02.

## Critics — findings

### Critic A — Coverage

| Tag | Finding | Severity | Disposition |
|---|---|---|---|
| F-COV-1 | Original AC-8 read `repo_context.probes["BaseImage"].kind` (top-level `kind`). Shipped `BaseImageSlice` has `stages: list[BaseImageStage]`; `kind` lives per-stage. Multi-stage Dockerfiles have multiple stages with potentially different kinds — the AC hid a "which stage wins?" question. | BLOCK | AC-9/AC-10/AC-11/AC-12 rewritten around `slice.stages[-1].kind` (final stage). AC-10 adds the load-bearing multi-stage case: builder (`full`) + distroless runtime → `"base_image_already_distroless"`. AC-12 adds the inverse: distroless builder + non-distroless runtime → `"base_image_not_distroless"`. Notes-for-implementer documents the "final stage wins" heuristic and the fallback (coordinate with Step 7's ordering contract if the heuristic proves wrong). |
| F-COV-2 | No AC covers `image_ref is None` (a non-container repo — the adapter is still on the `Layer.BASE_IMAGE` walk regardless of image-ref-ness). | HARDEN | Added AC-15 `test_no_image_ref_returns_probe_absent`, mirror of S4-02 AC-17; asserts `details["reason"] == "no_image_ref"`. |
| F-COV-3 | No AC covers `BaseImageSlice(stages=[])` — probe ran but found no stages (repo with no parseable Dockerfile). Original decision tree would then index `slice.stages[-1]` → `IndexError`. | BLOCK | Added AC-16 `test_slice_with_empty_stages_returns_probe_absent`; adapter guards `not slice.stages` before the final-stage index. Mirror of S4-02 AC-22. |
| F-COV-4 | AC-9's negative-detection test covered `"minimal"` and `"full"` only; original AC-11 covered `"unknown"`. `"vendor_specific"` (the fifth kind value) was not covered. A mutant that special-cases `"vendor_specific"` slips. | HARDEN | AC-11 parameterized over all four non-distroless kinds (`"minimal", "full", "vendor_specific", "unknown"`); asserts exact `reason` and `details["final_stage_kind"]` on each. |
| F-COV-5 | Two "provider absent" cases (`provider is None` vs `provider() returns None`) were collapsed to one AC. Operator diagnosability requires distinguishing "the adapter wasn't wired with a provider" from "the probe was wired but didn't run". | HARDEN | Split into AC-13 (`provider is None`, `details["reason"] == "provider_missing"`) and AC-14 (`provider() returns None`, `details["reason"] == "provider_returned_none"`). Two distinct `details["reason"]` values preserve the diagnostic. |
| F-COV-6 | No AC covers the composition-loss handoff — the story's Context claimed `Unknown(reason="base_image_already_distroless")` reaches the migration plugin's match step, but `assemble_provenance` drops the specific reason. Silent failure mode: Step 8 lands, resolver reads composed `Unknown(reason="no_adapter_resolved")`, distroless-target repos silently route to the universal HITL fallback instead of `NotApplicable`. | BLOCK | Added AC-21a (single-adapter case; specific reason survives) + AC-21b (both-adapters case; composed collapses to `"no_adapter_resolved"`, marked `pytest.mark.xfail(strict=False, reason="Step 8 / S8-03 composition-preservation deferral")`). The xfail explicitly documents the gap; when Step 8 lands the resolver contract, the executor removes the marker. Context and Out-of-scope sections rewritten to name this as a known handoff. |
| F-COV-7 | No AC covers the fence-directory placement (adapter under `plugins/`, not `src/codegenie/`). S4-02 covers the Alpine class; without a Distroless-class assertion, a future refactor could move it silently. | HARDEN | AC-22 stubs the class-location assertion; S5-02 lands the full walker. |
| F-COV-8 | No AC ensures the adapter is instantiable with all four DI kwargs (`sbom_reader`, `logger`, `image_manifest_cache`, `base_image_slice_provider`). Only zero-args was implicit. If `_DI_KWARGS` were extended and a kwarg missing on the adapter, tests would silently pass because the factory drops kwargs the adapter doesn't declare. | HARDEN | AC-3 extended: `test_construction_does_no_io` instantiates with zero args AND with all four DI kwargs; asserts no I/O in either case. |

### Critic B — Test Quality

| Tag | Finding | Severity | Disposition |
|---|---|---|---|
| F-TQ-1 | Original AC-13 exhaustiveness test used `case _: pytest.fail(...)`. `_` in a `match` arm is the wildcard, NOT a name binding — the arm captures nothing and `assert_never(_)` (or `pytest.fail(_)`) reads `_` as the module-level free name. The test doesn't actually exercise exhaustiveness. Mutation-thin. | BLOCK-RESOLVED | AC-17 rewritten as `case unreachable: assert_never(unreachable)`. Companion `test_missing_arm_surfaces_mypy_error` adds the static-side proof via a mypy-negative fixture. Notes-for-implementer documents `assembly.py`'s working precedent (`case _: assert_never((app_result, base_result))` works because the tuple is passed explicitly). |
| F-TQ-2 | Original AC-8 asserted a single happy-path fixture. A mutant returning constant `Unknown(reason="base_image_already_distroless")` for every input would pass. | HARDEN | AC-9 (single stage) + AC-10 (multi-stage) + AC-11 (parameterized negative over 4 kinds) + AC-12 (inverse multi-stage) collectively require the adapter to actually branch on `stages[-1].kind`. A constant-return mutant fails at least three of these. |
| F-TQ-3 | Original AC-14 (SBOM untouched) proved via behavioral means only — pass a poison SBOM, check the return. A structural fence catches accidental future refactors (e.g., a developer adding `logger.debug(sbom.descriptor)` for diagnostics). | HARDEN | Split into AC-18 (behavioral — output equality on two SBOMs with differing content) + AC-19 (structural AST fence in `tests/fence/test_distroless_adapter_does_not_touch_sbom.py`). Two-pronged defense. |
| F-TQ-4 | No test for `confidence()`. Compounded by the original AC-4's per-call state contradicting the Protocol's static-tie-breaker docstring. | BLOCK-RESOLVED | AC-5 rewritten: `confidence()` returns static `HIGH`. Added `test_confidence_is_static_high` (two consecutive calls; still `HIGH` after any `attribute()` call) and `test_no_mutable_instance_state` (post-call `vars(adapter)` unchanged). |
| F-TQ-5 | No `details` bag assertion on any `Unknown` return. A mutant returning the right `reason` but the wrong `details` (or `details=None`) slips. Operator diagnosability requires the `details` bag. | HARDEN | Every behavioral AC (AC-9 through AC-16) asserts the exact `details` dict — `final_stage_kind`, `stage_count`, `reason`, or `stages_len` — depending on the code path. Enables downstream `sbom.routing_anomaly` event structure. |
| F-TQ-6 | No test for adapter's input non-mutation. `BaseImageSlice` is frozen so mutation would raise, but a `.model_copy(update={...})` call would silently do the wrong thing. | HARDEN | AC-20 `test_adapter_does_not_mutate_inputs` — asserts `id()` and Pydantic hash of the input slice unchanged post-call. |

### Critic C — Consistency

| Tag | Finding | Severity | Disposition |
|---|---|---|---|
| F-CON-1 | Original AC-3 declared `attribute(self, *, cve_id, package_id, image_ref, sbom, repo_context: RepoContext) -> Provenance` — five keyword-only parameters including `repo_context`. The shipped `VulnProvenanceAdapter` Protocol (`src/codegenie/primitives/vuln_provenance/protocols.py`) is frozen at four positional args (`cve_id, package_id, image_ref, sbom`) — the module docstring calls it a "kernel contract". `assemble_provenance` (S2-04, shipped in `assembly.py` line 167) calls it positionally with those four. Adding a fifth kwarg or forcing keyword-only would either break every existing adapter or force a byte-edit to `assembly.py`. | BLOCK-RESOLVED | AC-4 rewritten as `attribute(self, cve_id, package_id, image_ref, sbom) -> Provenance`. `BaseImageSlice` reached via the S4-02-amended `base_image_slice_provider` DI kwarg. Notes-for-implementer explicitly documents "no new ADR-0007 amendment — inherit S4-02's". |
| F-CON-2 | Original AC-4 branched on `AdapterConfidence.HIGH` vs `AdapterConfidence.LOW`. Shipped `AdapterConfidence` (`types.py` line 100) is `StrEnum` with values `HIGH | DEGRADED | UNAVAILABLE`. `LOW` does not exist. Compounded by a semantic bug: the Protocol docstring says `confidence()` is "adapter-class-level static" (dispatch tie-breaker), NOT per-call state — but the story made it per-call. | BLOCK-RESOLVED | AC-5 rewritten: static `AdapterConfidence.HIGH`. Per-call decision rides on the `Unknown.reason` discriminator. Notes-for-implementer documents the Protocol's static-tie-breaker rationale. |
| F-CON-3 | Every original AC used enum-attribute syntax on `UnknownReason` (`.BASE_IMAGE_ALREADY_DISTROLESS`, `.BASE_IMAGE_NOT_DISTROLESS`, `.BASE_IMAGE_PROBE_ABSENT`). Shipped `UnknownReason` is `Literal[...]` of lowercase strings (`types.py` lines 122–129). Attribute access would `AttributeError` at runtime — every test would fail at import. | BLOCK-RESOLVED | Every AC rewritten with lowercase string literals. Notes-for-implementer explicitly states "UnknownReason is a Literal, NOT an enum". |
| F-CON-4 | Two of the three `UnknownReason` values the story referenced (`base_image_not_distroless`, `base_image_probe_absent`) are not in the shipped Literal. S4-02 adds `"base_image_probe_absent"` and `"base_image_not_alpine"` (its own sibling additions). This story adds `"base_image_not_distroless"`. | BLOCK-RESOLVED | AC-1 pins the additive edit: one new member on `UnknownReason`, coordinated with S4-02 if not yet landed. Files-to-touch names `types.py` explicitly. |
| F-CON-5 | Original AC-5 declared `_WARNING_IDS: Final[frozenset[str]]` on the adapter module. Phase 1 ADR-0007's `_WARNING_IDS` + `raise AssertionError` discipline is probe-only; adapters are silent (S4-02 dropped this per S4-01 F-CON-8 mirror). The story would have failed the S4-02 discipline check. | BLOCK-RESOLVED | `_WARNING_IDS` removed from all ACs. AC-6 explicitly documents the omission. Notes-for-implementer mirrors S4-02's rationale. |
| F-CON-6 | Original Context and AC-6 read `repo_context.probes.get("BaseImage")` — but `attribute()` never receives `repo_context` (F-CON-1). The story's decision tree was structurally unreachable. | BLOCK-RESOLVED | Fixed by F-CON-1 resolution: adapter reads `self._base_image_slice_provider()`. Production wiring (closing over `RepoContext.probes["BaseImage"]`) deferred to S8-01 / S8-03 per Out-of-scope. |
| F-CON-7 | Original Context claimed "the ecosystem-tiebreaker means this adapter is consulted **before** any future `(BASE_IMAGE, DPKG)` debian-runtime adapter — exactly the order operators want (recognize distroless first, then attempt attribution)". Shipped `Ecosystem` enum declaration order (`registry.py` line 70) is `NPM, YARN_BERRY, PNPM, APK, DPKG, RPM` — so `APK` (Alpine) is consulted BEFORE `DPKG` (Distroless). The "distroless first" claim is factually wrong. | BLOCK-RESOLVED | Context §Ordering note rewritten: Alpine runs first, returns `Unknown("base_image_not_alpine")` on a distroless-target repo, the walk continues, Distroless runs. This is the natural composition and needs no reordering. |
| F-CON-8 | Original Context and Goal claimed `Unknown(reason="base_image_already_distroless")` reaches "the migration plugin's match step" — but `assemble_provenance` (shipped `assembly.py` lines 173–187) treats every `Unknown` as "continue walking", and if both Alpine and Distroless return `Unknown` for a distroless-target repo the composed result is `Unknown(reason="no_adapter_resolved")` — the specific reason is lost. The story's claimed downstream contract does not hold. | BLOCK | Context §Known composition-loss gap paragraph added. Out-of-scope explicitly names the composition-preservation fix as Step 8 / S8-03's concern. AC-21b marks the composition-loss with an `xfail` and documents the three possible resolutions (raw-adapter-read, definitive-Unknown short-circuit, direct-probe-read). Notes-for-implementer explains how the adapter cooperates with all three. |
| F-CON-9 | `plugins/distroless-migration--node--npm/` bootstrap is S4-02's territory. Original story didn't clearly state S4-02 must land the bootstrap first. | NIT | Added dep on S4-02 explicitly in the `**Depends on:**` header; Context §How-the-adapter-reads-the-slice paragraph clarifies inheritance of the ADR-0007 amendment. |

### Critic D — Design Patterns

| Tag | Finding | Severity | Disposition |
|---|---|---|---|
| F-DP-1 | The adapter is a pure decision-tree with typed inputs and outputs — functional core, no imperative shell. Story's original outline had that shape but was obscured by the `repo_context` shim. | (positive — F-CON-1 fix makes it explicit) | Notes-for-implementer names the functional-core discipline. Body ≤ 40 LOC keeps the tree flat (no nested branches). |
| F-DP-2 | The "read slice → inspect a stage's `kind` → return typed `Unknown`" shape is now shared with S4-02's Alpine adapter (N=2). Should a helper be extracted now? Global Rule 2 + rule-of-three say no. | (positive design-pattern note) | Refactor section documents rule-of-three deferral. Notes-for-implementer names the natural hoist point (third adapter) and the second-consumer hint on `BaseImageSliceProvider` alias (prefer shared import if S4-02 exposes it). |
| F-DP-3 | `Unknown.reason` is the discriminator carrying per-call intent — a tagged-union / sum-type pattern. Story leverages this correctly (no boolean flags, no `Any`, no dict-shuffling). | (positive) | Preserved as-is. |
| F-DP-4 | Adapter has no mutable instance state. Post-init `vars(adapter)` is stable. This is a hexagonal-port discipline — the port is stateless; state (if any) lives in injected dependencies. | (positive) | AC-5's `test_no_mutable_instance_state` locks the discipline. |
| F-DP-5 | The adapter's registration under `(Layer.BASE_IMAGE, Ecosystem.DPKG)` uses the plugin/registry pattern's canonical decorator entry point. No branching code path is introduced — the kernel discovers the adapter by import side-effect. | (positive) | Preserved as-is. AC-7 pins the side-effect import line. |
| F-DP-6 | The composition-loss gap (F-CON-8) is technically a "primitive obsession" on `UnknownReason` at the composition layer — `assemble_provenance` should carry a richer "definitive Unknown" concept. But solving it here would be a kernel change; deferring to Step 8 is correct. | (design opportunity flagged for Step 8) | Notes-for-implementer names the three possible resolutions and the cooperative contract this adapter maintains for all three. Not a S4-03 concern to fix, but flagged as a design smell that Step 8 must address. |
| F-DP-7 | `details: dict[str, str]` on `Unknown` is untyped-dict-shuffling in the strictest sense — but the shape is intentionally open per production ADR-0033 for operator diagnosability, and the values used here (`final_stage_kind`, `stage_count`, `reason`, `stages_len`) are documented per AC and consumed by the `sbom.routing_anomaly` event schema (in the arch's Scenario D). Design-Patterns critic accepts as a documented open-schema use. | NIT | Every AC that returns `Unknown` pins the exact `details` shape in its assertion, so mutation-thinness on the shape is not silent. |

## Research

No `NEEDS RESEARCH` findings. All issues resolved from existing precedent (S4-02's HARDENED pass, shipped kernel code, Phase-7 arch design).

## Verdict

**HARDENED.** Nine block-severity structural issues resolved; six harden-severity tightening edits + three nit-severity touch-ups folded in. No goal or scope change. Story is executor-ready: every AC is individually verifiable, the AC set collectively guarantees the goal, every AC has at least one test in the TDD plan that would fail on a wrong implementation, no `AdapterConfidence.LOW` / no `repo_context` / no enum-attribute-syntax landmines remain, the composition-loss gap is explicitly surfaced (not silently expected), and the multi-stage semantics are pinned to the final-stage-wins heuristic.

The story's story text is now consistent with:

- `src/codegenie/primitives/vuln_provenance/protocols.py` (S1-04, shipped) — frozen Protocol.
- `src/codegenie/primitives/vuln_provenance/types.py` (S1-02/S1-03, shipped) — `UnknownReason` Literal, `AdapterConfidence` StrEnum.
- `src/codegenie/primitives/vuln_provenance/factory.py` (S2-02, shipped; S4-02-amended) — `_DI_KWARGS` closed set.
- `src/codegenie/primitives/vuln_provenance/assembly.py` (S2-04, shipped) — composition semantics that motivate the Step-8 handoff.
- `../phase-arch-design.md` §Data model line 1136 — `BaseImageSlice` shape.
- Sibling story S4-02 (HARDENED, not shipped) — canonical shape mirror.

## Edits applied (summary)

- Rewrote `**Depends on:**` header to name S4-02's `_DI_KWARGS` amendment + `UnknownReason` extensions explicitly.
- Added `## Validation notes (2026-08-14)` block after the header.
- Rewrote §Context to remove the false "distroless first" ordering claim, add the composition-loss handoff paragraph, and pin the multi-stage "final stage wins" semantics.
- Rewrote §References to correctly identify `UnknownReason` as Literal (not enum) and `AdapterConfidence` as HIGH/DEGRADED/UNAVAILABLE.
- Rewrote §Goal to describe the frozen four-arg Protocol shape, the DI-kwarg consumption, and the six specific `Unknown.reason`+`details` return shapes.
- Rewrote every AC (AC-1 through AC-28) — replaced enum syntax with Literal strings, replaced `AdapterConfidence.LOW` with the correct value, replaced `repo_context.probes["BaseImage"].kind` with `slice.stages[-1].kind`, split the two "provider absent" cases, added multi-stage coverage (AC-10 + AC-12), added parameterized-kind negative coverage (AC-11), added integration test with the composition-loss `xfail` (AC-21), added mypy-negative exhaustiveness proof (AC-17b), added no-mutable-state check (AC-5).
- Rewrote §Implementation outline to match the corrected AC shape.
- Rewrote §TDD plan with corrected fixture shapes and the split provider-absent tests.
- Rewrote §Files to touch — no `_DI_KWARGS` amendment (inherited from S4-02); `UnknownReason` +1 addition; no `_WARNING_IDS` in the module.
- Expanded §Out of scope with the composition-loss deferral to Step 8 / S8-03.
- Rewrote §Notes for the implementer to document: frozen Protocol, no new ADR amendment, string-literal `UnknownReason`, no `LOW` on `AdapterConfidence`, no `_WARNING_IDS`, corrected `BaseImageSlice` shape, "final stage wins" heuristic, second-import for `api.py`, composition-loss cooperation, `Ecosystem.DPKG` placeholder rationale, corrected ordering (Alpine before Distroless), rule-of-three watch on shared helpers.

## Follow-on observations (out of scope for this story)

- **BLOCK-8 preservation contract** — Step 8 / S8-03 must resolve how the specific `Unknown.reason="base_image_already_distroless"` reaches the migration plugin's match step. The three candidate resolutions (raw-adapter-read, definitive-Unknown short-circuit in `assemble_provenance`, direct-probe-read in the resolver) are all compatible with this story's adapter contract. When Step 8 lands its choice, the executor removes the `xfail` marker on AC-21b (or the resolver bypasses `assemble_provenance` for this signal and AC-21b's assertion is retained as a documented behavior of the composition layer).
- **`Ecosystem.DISTROLESS_NODE` future amendment** — if a Phase 8+ story needs to distinguish distroless-node from distroless-python, the `Ecosystem` enum grows a member and the Distroless adapter's registration key updates. This is not a Phase-7 concern.
- **Rule-of-three shared helper** — the "read slice → inspect stage kind → return typed Unknown" shape is N=2 at end-of-story-4. A hypothetical `RhelVulnProvenanceAdapter` or `RuntimeBundledVulnProvenanceAdapter` would be N=3 and the natural extract point.
- **`BaseImageSliceProvider` alias sharing** — if S4-02 exposes the alias from a shared plugin module, this story's local redeclaration is a candidate for one-line-import replacement. Rule-of-three-adjacent; noted in Refactor + Notes.
