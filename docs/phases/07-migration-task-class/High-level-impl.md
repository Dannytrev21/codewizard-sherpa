# Phase 7 — Add migration task class (Chainguard distroless): High-level implementation plan

**Status:** Implementation plan
**Date:** 2026-05-19
**Architecture reference:** [phase-arch-design.md](phase-arch-design.md)
**ADRs:** [ADRs/](ADRs/)
**Source design:** [final-design.md](final-design.md)
**Roadmap reference:** [docs/roadmap.md](../../roadmap.md) §"Phase 7"

## Executive summary

Phase 7 lands a **second production task class** (Chainguard distroless container migration) and the introduction itself is the test that the system can grow by addition. The implementation shape is *primitive-before-adapters, registry-before-adapters, fence-before-edits, plugin-as-the-only-new-tree*: the seven-variant `Provenance` discriminated union + smart-constructor newtypes + the `VulnProvenanceAdapter` Protocol land in Step 1 with `mypy --strict` clean and the LLM-fence import-linter contract extended; the `@register_provenance_adapter` registry + `_ADAPTER_DISPATCH_ORDER` + `assemble_provenance` free function land in Step 2 before any adapter calls them; the byte-edit allowlist fence (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) lands in the SAME step as the first allowed edit, not bolted on at the end; the new `plugins/distroless-migration--node--npm/` tree is the only new top-level directory besides `src/codegenie/primitives/vuln_provenance/`; Phase 5's `SandboxClient.spawn(...)` gains exactly one `role: SandboxRole` parameter (additive enum) before `ShellInvocationTraceProbe` ships. The headline end-to-end test (`tests/e2e/test_distroless_migration_e2e.py`) and the headline coordination test (`tests/e2e/test_both_provenance_emits_coordination_event_e2e.py`) are exit-gate Step 11 / Step 12 work, not Step 13 work — the regression suite for Phase 3–6.5 runs from Step 1 onward as a hard pre-merge gate.

## Order of operations

**Primitive contracts → registry kernel → Phase-3 adapter (in-plugin additive file) → Phase-7 adapters → fence allowlist → Phase 5 sandbox amendment → in-plugin probes → plugin TCCM + manifest → CVE-to-image catalog → recipes + policy gate → `Both` event + CLI → test-pyramid backfill.** Rationale: the ADR-0033/ADR-0038-anchored newtypes and the seven-variant `Provenance` union are the load-bearing type vocabulary every later module references; landing them in Step 1 with `mypy --strict` + `ruff check` + import-linter clean means later steps cannot silently widen `Provenance` or smuggle `Any` past `extra="forbid"`. The plugin/registry kernel (Step 2) precedes any adapter that uses it because Plugin/Registry is non-negotiable: an adapter coded against a not-yet-stable Protocol pays for itself twice. The fence allowlist (Step 5) lands the moment the first byte-edit hits a Phase 0–6.5 file because "additive" stops being aspirational and becomes a CI invariant only when there's a test that fails on the 11th byte-edit. Phase 5's `SandboxRole` amendment (Step 6) lands before the heavy probe (Step 7) so the probe can write its `spawn(role=Role.PROBE)` call against a stable signature. `Both`-variant emission + CLI (Step 11) lands before the e2e suite (Step 12) so the e2e tests can pin the exact exit-code-8 + `coordination-summary.yaml` shape they assert.

Pattern-driven sequencing constraints:

- **Newtypes + Smart constructors land Step 1** (`ImageRef`, `ImageDigest`, `LayerDigest`, `CveId`, `PackageId`, `ProvenanceAdapterId`, `RuntimeId`, `DockerStageName`, `DistroPackage`). Raw `str` is type-illegal at every typed boundary thereafter.
- **Plugin/Registry kernel (`@register_provenance_adapter`) lands in Step 2 before adapters use it.** Registry stores classes, not instances (critic BP-3).
- **Hexagonal Port (`VulnProvenanceAdapter` Protocol) lands in Step 1 before any adapter implementation in Steps 3–4.**
- **Tagged-union `Provenance` (seven variants, nested `Both`) lands in Step 1** before `assemble_provenance` consumes it in Step 2.
- **Open/Closed via additive enum** for `SandboxRole` (Step 6) — one Phase 5 amendment, future task classes' roles ride the same seam.
- **Strategy-via-data (`_ADAPTER_DISPATCH_ORDER` `Final` tuple) lands in Step 2** — registration order is never load-bearing.
- **Fence test for byte-edit allowlist lands in Step 5, the same step as the first allowed Phase-3-plugin file edit** (Step 3's `npm_provenance.py` is technically a new file under that plugin; the fence allowlist must be in place before Step 5 closes).
- **`mypy --strict` + `ruff check` + `make lint-imports` clean from Step 1 onward.** No "we'll fix it later." Each step's done-criteria includes the gate.
- **`make check` + Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay run as a hard pre-merge gate from Step 1 onward.** Phase 7 PRs cannot merge if they regress Phase 3 behavior; this is enforced from the first commit.

## Step 1 — Scaffold `vuln.provenance` primitive: newtypes, Provenance union, Protocol, errors

**Goal:** Every typed primitive Phase 7 ever uses exists in code with `extra="forbid"` enforcement, `mypy --strict` clean, the seven-variant `Provenance` discriminated union (verbatim from ADR-0038) constructable and round-trippable, the `VulnProvenanceAdapter` Protocol defined, and the LLM-SDK import-linter contract extended to cover the new tree — before any adapter or registry logic lands.

**Features delivered:**
- New top-level `src/codegenie/primitives/__init__.py` package (the ADR-0039 additive home).
- `src/codegenie/primitives/vuln_provenance/__init__.py` exporting the public surface (`Provenance`, `AppDirect`, `AppTransitive`, `AppVendored`, `BaseImage`, `RuntimeBundled`, `Both`, `Unknown`, `AppKind`, `BaseKind`, `UnknownReason`, `AdapterConfidence`, `VulnProvenanceAdapter`).
- `src/codegenie/primitives/vuln_provenance/types.py` — seven-variant Pydantic v2 discriminated union per ADR-0038 verbatim; `Both.app_record: AppKind` and `Both.base_record: BaseKind` are nested discriminated unions over non-`Both`/non-`Unknown` variants so `Both(Both, ...)` is rejected at validation time; all variants `frozen=True, extra="forbid"`.
- `src/codegenie/primitives/vuln_provenance/protocols.py` — `@runtime_checkable VulnProvenanceAdapter(Protocol)` with `attribute(...) -> Provenance` and `confidence() -> AdapterConfidence`. **No `cost_band`, no `applies_when`** (critic Perf-5).
- `src/codegenie/primitives/vuln_provenance/errors.py` — `ProvenanceError(CodegenieError)` hierarchy; `RegistryError`, `AdapterError`.
- `src/codegenie/primitives/vuln_provenance/syft_reader.py` — `SyftSbom`, `SyftArtifact`, `SyftLocation` Pydantic models. `model_config = ConfigDict(extra="allow")` (Phase 2 deliberate decision); adapters read only known fields (Gap 3 defensive guard).
- `src/codegenie/types/identifiers.py` extended with `CveId`, `PackageId`, `ImageRef`, `ImageDigest` (`sha256:` prefix asserted), `LayerDigest`, `RuntimeId`, `DockerStageName`, `ProvenanceAdapterId = tuple[Layer, Ecosystem]`. Each `NewType` + smart-constructor wrapper returning `Result[T, ParseError]` (mirrors Phase 3 ADR-0033 discipline).
- `DistroPackage` Pydantic model under `types.py` (frozen, three-field; `distro: Literal["alpine", "debian", "ubuntu", "rhel"]`).
- `pyproject.toml [tool.importlinter]` contract extended: `src/codegenie/primitives/vuln_provenance/` forbidden imports of `anthropic|openai|langchain|langgraph|transformers`.
- `tests/fence/test_phase7_no_llm.py` — runtime-closure scan of the new primitive surface against `FORBIDDEN_LLM_SDKS`.
- `tests/fence/test_no_any_in_provenance_surface.py` — AST-walk asserting no new `Any` or `dict[str, Any]` annotations under `src/codegenie/primitives/vuln_provenance/`.

**Done criteria:**
- [ ] `pytest tests/unit/primitives/vuln_provenance/test_types.py` covers construction + JSON round-trip + `frozen=True` rejection + `extra="forbid"` rejection for every one of the seven variants.
- [ ] `pytest tests/unit/primitives/vuln_provenance/test_both_recursion_rejected.py` — `Both(Both(...), ...)` raises `ValidationError` at construction (the type system enforces the recursion guard, not a runtime check).
- [ ] `pytest tests/unit/types/test_identifiers_phase7.py` covers smart-constructor round-trip + parse-error variant for every new newtype (`ImageDigest` requires `sha256:` prefix; malformed input returns `ParseError`).
- [ ] `mypy --strict src/codegenie/primitives src/codegenie/types/identifiers.py` clean.
- [ ] `ruff check src/codegenie/primitives` clean.
- [ ] `make lint-imports` green with the new contract.
- [ ] `tests/fence/test_phase7_no_llm.py` green; fails on a deliberately-planted `import anthropic` in the primitive and is removed once verified.
- [ ] Every sum-type variant is consumed by at least one `match` statement with `assert_never` in a test (verified by `tests/unit/primitives/vuln_provenance/test_exhaustiveness.py`).
- [ ] `make check` (full suite) green including Phase 3–6.5 regression tests.

**Depends on:** Phase 0/1/2/3 packages on disk (`codegenie.types.identifiers`, `codegenie.errors`, Pydantic v2 already in deps).

**Effort:** M — mechanical but volume is high (8 new newtypes + 7 union variants + 2 fence tests + 1 new top-level package).

**Risks specific to this step:** None major. `Both`'s nested discriminated union is the one piece that's easy to get wrong — pin it explicitly with a "`Both(Both, ...)` rejected at construction" unit test before landing.

## Step 2 — Registry kernel, `_ADAPTER_DISPATCH_ORDER`, `assemble_provenance` free function

**Goal:** The Plugin/Registry seam for adapters exists; `@register_provenance_adapter` stores adapter classes (not instances); the dispatch policy lives in one `Final` tuple operators can read; `assemble_provenance(...)` walks the policy deterministically and composes results into a single `Provenance` via `match` + `assert_never`. No adapter implementations yet — the kernel is closed for modification before adapters arrive.

**Features delivered:**
- `src/codegenie/primitives/vuln_provenance/registry.py` — `Layer` enum (`APP | BASE_IMAGE | RUNTIME`), `Ecosystem` enum (`NPM | YARN_BERRY | PNPM | APK | DPKG | RPM`), `ProvenanceAdapterId = tuple[Layer, Ecosystem]`, module-level `_REGISTRY: Final[dict[ProvenanceAdapterId, type[VulnProvenanceAdapter]]] = {}`, `@register_provenance_adapter(layer=..., ecosystem=...)` decorator (raises `RegistryError` on duplicate key — fast-fail at plugin-import time).
- `src/codegenie/primitives/vuln_provenance/assembly.py` — module-level `_ADAPTER_DISPATCH_ORDER: Final[tuple[tuple[Layer, ...], ...]] = ((Layer.APP,), (Layer.BASE_IMAGE,), (Layer.RUNTIME,))`. `assemble_provenance(cve_id, package_id, image_ref, sbom, *, registry=None, adapter_factory=None) -> Provenance` walks the tuple; within a layer-set, iterates adapters in `Ecosystem`-enum-sorted order (deterministic, NOT `dict.items()` order); collects the first non-`Unknown` per layer (`app_result`, `base_result`); composes via `match (app_result, base_result)` into one of `Unknown(reason="no_adapter_resolved")`, `app`, `base`, or `Both(app_record=app, base_record=base)` — ≤ 80 LOC total.
- `assemble_provenance` catches `ProvenanceError` → converts to `Unknown(reason="adapter_error", details={...})`; all other exceptions propagate (Rule 12 fail-loud).
- `src/codegenie/primitives/vuln_provenance/__init__.py` exports `assemble_provenance`, `register_provenance_adapter`, `Layer`, `Ecosystem`.
- `AdapterFactory` Protocol in `protocols.py` — DI-aware construction; well-known kwarg names `{sbom_reader, logger, image_manifest_cache}` (Phase 7 ADR-0010 draft; final names pinned here).
- `tests/conftest.py` extended with a `provenance_registry_reset` pytest fixture that snapshots and restores `_REGISTRY` per test (mirrors Phase 2 `freshness` registry isolation pattern).
- Public-surface module `src/codegenie/primitives/vuln_provenance/__init__.py` exports the `provenance(...)` thin-wrapper callable that TCCM `derived_queries:` resolves `compute: vuln.provenance` to.

**Done criteria:**
- [ ] `pytest tests/unit/primitives/vuln_provenance/test_registry.py` covers: `@register_provenance_adapter` happy path stores the class; duplicate `(layer, ecosystem)` raises `RegistryError` at decoration time; registry survives import order shuffles when isolated via fixture.
- [ ] `pytest tests/unit/primitives/vuln_provenance/test_assembly.py` covers all four `match (app, base)` arms with stub adapters: `(None, None)` → `Unknown(reason="no_adapter_resolved")`; `(app, None)` → `app`; `(None, base)` → `base`; `(app, base)` → `Both(app_record=app, base_record=base)`.
- [ ] `pytest tests/unit/primitives/vuln_provenance/test_assembly_error_handling.py` — adapter raising `ProvenanceError` becomes `Unknown(reason="adapter_error")`; adapter raising `RuntimeError` propagates.
- [ ] `pytest tests/property/vuln_provenance/test_dispatch_order_invariant.py` (Hypothesis) — 50 registration-order permutations; `assemble_provenance` result is byte-identical (locks critic BP-1).
- [ ] `pytest tests/property/vuln_provenance/test_idempotence.py` — calling `assemble_provenance` twice with identical inputs returns equal `Provenance` instances.
- [ ] `mypy --strict src/codegenie/primitives/vuln_provenance` clean.
- [ ] `make check` green.

**Depends on:** Step 1 (newtypes, `Provenance` union, Protocol, errors).

**Effort:** M — kernel must be right; the assembly function is small but the `match` block with nested unions is corner-case-heavy.

**Risks specific to this step:** `Ecosystem`-enum-sorted iteration order is the subtle bit — write the test BEFORE the implementation so a `dict.items()` regression fails loud.

## Step 3 — `NpmVulnProvenanceAdapter` in Phase 3 plugin as additive new file (first byte-edit territory)

**Goal:** The first concrete `VulnProvenanceAdapter` ships as an additive new file inside `plugins/vulnerability-remediation--node--npm/adapters/`, registers via `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)`, reads gathered `RepoContext` for npm lockfile evidence, returns `AppDirect | AppTransitive | Unknown(reason)` — and the Phase 3 plugin's behavior is byte-identical against the `bench/vuln-remediation/` cassette replay. **This is the first byte-edit Phase 7 makes to a Phase 0–6.5 file; the fence allowlist (Step 5) must be planned for now.**

**Features delivered:**
- `plugins/vulnerability-remediation--node--npm/adapters/__init__.py` (new file, additive).
- `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` — `NpmVulnProvenanceAdapter` class satisfying `VulnProvenanceAdapter` Protocol. Constructor accepts `sbom_reader`, `logger`, `image_manifest_cache` via DI kwargs (no I/O at construction). `attribute(...)` reads `package.json` + `package-lock.json` from the gathered `RepoContext`, walks the resolved tree; chain length 1 → `AppDirect`; chain length > 1 → `AppTransitive`; absent → `Unknown(reason="sbom_layer_attribution_absent")`. Cross-verifies via `sbom_verifier.py` (lives in the primitive, Step 4).
- `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` declares module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset({"vuln_provenance.adapter_error"})` validated at import time via `raise AssertionError(...)` (bare `assert` is forbidden by `forbidden-patterns`).
- `plugins/vulnerability-remediation--node--npm/api.py` — **one** added import line: `from .adapters import npm_provenance  # noqa: F401  # registers via decorator`. This is the explicit-import collection point (CLAUDE.md mandates explicit-import; no `importlib.metadata` entry-points).
- `plugins/vulnerability-remediation--node--npm/tccm.yaml` — **one** new line under an existing band documenting the adapter availability (TBD whether this is a `should_read:` entry or a `derived_queries:` entry — pinned in story-writing once Step 8's TCCM schema lands).

**Done criteria:**
- [ ] `pytest tests/unit/plugins/vulnerability_remediation_node_npm/test_npm_provenance.py` covers happy path (direct dep → `AppDirect`; transitive → `AppTransitive` with chain length ≥ 2; absent → `Unknown`), DI kwargs honored, no I/O at construction.
- [ ] `pytest tests/integration/test_provenance_assembly_via_plugins.py` — full plugin-load → `@register_provenance_adapter` fires → `assemble_provenance(...)` invokes `NpmVulnProvenanceAdapter` and returns typed result.
- [ ] `bench/vuln-remediation/` cassette replay green; cost-ledger byte-equality preserved (ε ≤ $0.01).
- [ ] `make check` green; **Phase 3–6.5 regression suite green (hard pre-merge gate)**.
- [ ] `mypy --strict plugins/vulnerability-remediation--node--npm/adapters` clean.

**Depends on:** Steps 1–2.

**Effort:** M — the adapter is small but it's the first touch of a Phase 3 plugin file, so the regression-suite gate is load-bearing.

**Risks specific to this step:** Adapter contract incompatibility with the promoted-from-Phase-3 refuse-mode shape could force editing Phase 3 plugin code beyond the allowed two files — **mitigate by writing the contract test (`test_provenance_assembly_via_plugins.py`) first**, before the adapter body lands, so the contract is the green-light. If a Phase 3 internal API doesn't satisfy `NpmVulnProvenanceAdapter`'s read needs, surface as a follow-up cleanup ticket — do NOT refactor Phase 3 code in this step.

## Step 4 — `AlpineVulnProvenanceAdapter` + `DistrolessVulnProvenanceAdapter` + `sbom_verifier.py`

**Goal:** The two base-image adapters ship under the new Phase 7 plugin tree; `sbom_verifier.py` lands in the primitive (consumed by all adapters) and cross-checks `SyftSbom.locations[].layerID` against image-manifest digests; poisoned SBOMs land in `Unknown(reason="sbom_layer_attribution_absent")` — no `KeyError`, no silent `app_direct`.

**Features delivered:**
- `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` — pure function `cross_check_sbom_layer_attribution(sbom, image_manifest) -> Verification` returning `Verification.Ok | Verification.Mismatch(reason)`. Reads ONLY `locations[].layerID`, `name`, `version` from `SyftSbom` (Gap 3 defensive: never recurses into `extra` content). Smart constructor returning `Result[Verification, MismatchError]`.
- `plugins/distroless-migration--node--npm/` directory created (new plugin tree). Empty `__init__.py` files where needed.
- `plugins/distroless-migration--node--npm/adapters/__init__.py`.
- `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py` — `AlpineVulnProvenanceAdapter` decorated `@register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.APK)`. Reads `SyftSbom.locations[].layerID`; matches against `BaseImageProbe`'s layer-to-image-digest mapping (Step 7's slice — defensive against absence: returns `Unknown(reason="sbom_layer_attribution_absent")` until Step 7 ships). Returns `BaseImage(image_digest, layer_digest, distro_pkg, stage)` on hit.
- `plugins/distroless-migration--node--npm/adapters/distroless_provenance.py` — `DistrolessVulnProvenanceAdapter` decorated `@register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.DPKG)`. Inspects `BaseImageProbe` slice for `base_image_kind == "distroless"`; if so, returns `Unknown(reason="base_image_already_distroless")`.
- `plugins/distroless-migration--node--npm/api.py` — declares the plugin instance, imports adapters for side-effect registration.
- `tests/fixtures/portfolio/node-poisoned-sbom/` — Alpine fixture with fabricated `layerID` values that don't match the image manifest.

**Done criteria:**
- [ ] `pytest tests/unit/plugins/distroless_migration_node_npm/test_alpine_provenance.py` covers happy path (layer match → `BaseImage`) and mismatch (poisoned `layerID` → `Unknown(reason="sbom_layer_attribution_absent")`).
- [ ] `pytest tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance.py` covers distroless detection → `Unknown(reason="base_image_already_distroless")`.
- [ ] `pytest tests/unit/primitives/vuln_provenance/test_sbom_verifier.py` covers `Verification.Ok` and `Verification.Mismatch(reason)` arms; pure-function (no I/O).
- [ ] `pytest tests/property/vuln_provenance/test_sbom_tampering.py` (Hypothesis) — 100+ generated SBOMs with malformed/poisoned `locations[].layerID`; every case lands in `Unknown(reason="sbom_layer_attribution_absent")` or a typed-attested result. **No `KeyError`, no silent `app_direct`.**
- [ ] `pytest tests/fence/test_alpine_adapter_reads_known_fields_only.py` — AST-walks the alpine adapter and asserts no `getattr(sbom_artifact, "extra", ...)` or `dict(sbom_artifact).items()` recursion (Gap 3 defensive).
- [ ] `mypy --strict plugins/distroless-migration--node--npm/adapters src/codegenie/primitives/vuln_provenance/sbom_verifier.py` clean.
- [ ] `make check` green.

**Depends on:** Steps 1–3. Step 7's `BaseImageProbe` slice is referenced defensively — Step 4 ships without it and the adapter degrades to `Unknown` cleanly.

**Effort:** M — two adapters + the verifier + a Hypothesis property test + a fence AST-walk.

**Risks specific to this step:** `SyftSbom` with `extra="allow"` is the one tolerated `dict[str, Any]`-like surface — the fence test that asserts the adapter reads only known fields is the only thing preventing future drift.

## Step 5 — Phase 7 byte-edit allowlist fence + import-linter contracts

**Goal:** The mechanical definition of "additive" lands as a CI invariant: `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` enumerates the ten allowed Phase 7 byte-edits and fails on any other touch of a Phase 0–6.5 file. Import-linter contracts for the new tree are wired. Without this step, Steps 3 + 4 are unprotected; future steps would be tempted to "just one more byte-edit."

**Features delivered:**
- `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` — git-diff against the Phase 6.5 baseline (HEAD or pinned tag); every changed file outside the enumerated allowlist is a fence failure. The allowlist (10 enumerated rows):
  1. `src/codegenie/__init__.py` — one new import line for the primitive.
  2. `src/codegenie/schema/repo_context.schema.json` — two `$ref` insertions (one per new probe slice).
  3. `src/codegenie/exec/__init__.py` — two new `ALLOWED_BINARIES` rows (`dive`, `docker buildx`).
  4. `src/codegenie/sandbox/client.py` — one new `role: SandboxRole = Role.GATE` parameter (Step 6).
  5. `src/codegenie/sandbox/__init__.py` — one new `Role` enum export (Step 6).
  6. `src/codegenie/plugins/tccm.py` — additive `derived_queries: list[DerivedQuery] = []` schema field (Step 8).
  7. `src/codegenie/plugins/loader.py` — one new explicit-import line for the migration plugin (Step 8).
  8. `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` — new file (Step 3).
  9. `plugins/vulnerability-remediation--node--npm/api.py` — one new import line for the adapter (Step 3).
  10. `plugins/vulnerability-remediation--node--npm/tccm.yaml` — one new entry (Step 3).
- `tests/fence/test_provenance_primitive_in_plugin_directory.py` — asserts the two new probes live under the plugin's `probes/` directory and NOT under `src/codegenie/probes/`.
- `pyproject.toml [tool.importlinter]` extended: `src/codegenie/primitives/vuln_provenance/` and `plugins/distroless-migration--*/` may not import LLM SDKs.
- `pyproject.toml [tool.importlinter]` extended: the primitive may not import from `plugins/` (port-before-adapter direction enforced).
- `plugins/PLUGINS.lock` entry for the new plugin's sha256(dir_tree). CODEOWNERS-gated (existing Phase 3 mechanism).
- `tests/fence/test_phase7_chainguard_lookup_table_loads.py` placeholder (pinned file-hash check; Step 9 fills in the actual hash once the catalog YAML is finalized).

**Done criteria:**
- [ ] `pytest tests/fence/test_phase7_no_byte_edits_to_locked_files.py` green on the current diff; fails on a deliberately-planted edit to a non-allowlisted Phase 3 file.
- [ ] `pytest tests/fence/test_provenance_primitive_in_plugin_directory.py` green.
- [ ] `make lint-imports` green with the new import-linter contracts.
- [ ] `plugins/PLUGINS.lock` updated and CODEOWNERS-reviewed.
- [ ] `make check` green.

**Depends on:** Steps 1–4 (the fence needs the actual file paths to allowlist).

**Effort:** S — a focused enumeration test + import-linter config diffs.

**Risks specific to this step:** The allowlist must match reality exactly; if Step 6 (Phase 5 amendment) lands with a slightly different file path than enumerated row #4 / #5, the fence will fail. Coordinate file paths during story-writing.

## Step 6 — Phase 5 `SandboxRole` additive enum + `SandboxClient.spawn(role=...)` amendment

**Goal:** Phase 5's `SandboxClient.spawn(...)` gains exactly one additive `role: SandboxRole` parameter (default `Role.GATE`); `Role.PROBE` is the second enum value. Same Firecracker/gVisor (Linux) and Lima (macOS) stack handles both roles; no parallel `probe-control` process ships. Phase 7 ADR-0003 records the amendment; this is the one explicit Phase 5 edit Phase 7 makes.

**Features delivered:**
- `src/codegenie/sandbox/__init__.py` exports `SandboxRole` (the enum) — additive.
- `src/codegenie/sandbox/client.py` — `class SandboxRole(str, Enum): GATE = "gate"; PROBE = "probe"`. `SandboxClient.spawn(...)` signature gains `role: SandboxRole = SandboxRole.GATE`. Behavior diff between roles: `PROBE` enables eBPF host-side trace capture and short container boot; `GATE` keeps the existing gate behavior unchanged. **Default = GATE so all existing Phase 5 callsites are byte-identical.**
- `docs/phases/07-migration-task-class/ADRs/0003-sandbox-role-additive-enum.md` — Nygard ADR recording the amendment, the rejection of a separate `probe-control` process, and the Phase 5 ratification dependency.
- `tests/integration/test_sandbox_client_role_probe.py` — `SandboxClient.spawn(role=Role.PROBE)` boots a microVM identical to `Role.GATE` plus eBPF trace capture; default-arg invocation byte-identical to pre-amendment.

**Done criteria:**
- [ ] `pytest tests/integration/test_sandbox_client_role_probe.py` covers both roles; default-arg path unchanged.
- [ ] `pytest tests/unit/sandbox/test_role_enum.py` covers enum values and string round-trip.
- [ ] **Every existing Phase 5 `SandboxClient.spawn(...)` callsite is byte-unchanged** — verified by `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` showing `client.py` has exactly the enumerated additive change and nothing else.
- [ ] Phase 5's existing test suite green (no regression).
- [ ] `mypy --strict src/codegenie/sandbox` clean.
- [ ] `make check` green.

**Depends on:** Step 5 (fence allowlist must be in place before this edit).

**Effort:** S — one parameter + one enum value + one ADR + one integration test.

**Risks specific to this step:** Phase 5 must accept the amendment. If rejected (unlikely; this is the synthesis-departure architecture's load-bearing piece), the fallback is to ship the heavy probe under `Role.GATE` and accept audit-clarity cost — record the fallback in the ADR's Risks section.

## Step 7 — `BaseImageProbe` + `ShellInvocationTraceProbe` under the plugin (sandboxed)

**Goal:** Two new probes ship inside the Phase 7 plugin (`plugins/distroless-migration--node--npm/probes/`), each obeying the frozen Probe ABC; `BaseImageProbe` is light + static + Layer C; `ShellInvocationTraceProbe` is heavy + `runs_last=True` + Layer D and executes target builds ONLY via `SandboxClient.spawn(role=Role.PROBE)`. Sub-schemas under the plugin's `schema/` directory; wired into the envelope via one additive `$ref` insertion per probe.

**Features delivered:**
- `plugins/distroless-migration--node--npm/probes/__init__.py`.
- `plugins/distroless-migration--node--npm/probes/base_image_probe.py` — `BaseImageProbe(Probe)` decorated `@register_probe`. Layer C, tier `task_specific`, `applies_to_tasks=["distroless-migration"]`, `declared_inputs=["**/Dockerfile", "**/Dockerfile.*", "**/Containerfile", "image-digest:<resolved>"]`, `cache_strategy="content"`. Parses Dockerfile via `dockerfile-parse`; for each `FROM`, calls `ctx.image_digest_resolver` (Phase 2 ADR-0004 capability); classifies via module-level `_BASE_IMAGE_KIND_RULES: Final[tuple[BaseImageRule, ...]]` (open/closed marker catalog). Emits warning ID `base_image.dockerfile_parse_failed` on parse failure (matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`).
- `plugins/distroless-migration--node--npm/probes/shell_trace_probe.py` — `ShellInvocationTraceProbe(Probe)` decorated `@register_probe(heaviness="heavy", runs_last=True)`. Layer D, `requires=["BaseImage"]`. `run()` calls ONLY `ctx.sandbox_client.spawn(role=Role.PROBE, workspace=repo.workspace, command=["docker", "buildx", "build", "--target=builder", "."], capture_trace=True)`. No `subprocess.run`, no `os.system`, no `os.popen`, no `shell=True`. Emits warning IDs `shell_invocation_trace.sandbox_boot_failed`, `shell_invocation_trace.build_failed`.
- `plugins/distroless-migration--node--npm/schema/base_image.schema.json` — `BaseImageSlice` Pydantic-derived sub-schema; `additionalProperties: false` at every node.
- `plugins/distroless-migration--node--npm/schema/shell_invocation_trace.schema.json` — `ShellInvocationTraceSlice` sub-schema.
- `src/codegenie/schema/repo_context.schema.json` — two additive `$ref` insertions under `properties.probes` (one per new slice).
- `dockerfile-parse` added to `pyproject.toml` runtime dependencies (the ONE net-new Python runtime dep).
- `src/codegenie/exec/__init__.py::ALLOWED_BINARIES` amended with `dive`, `docker buildx` (Phase 7 ADR-0011 records the omnibus). **`strace` is NOT added.**
- `tests/fence/test_shell_trace_probe_isolation.py` — AST-walks `ShellInvocationTraceProbe.run()` and asserts only `SandboxClient.spawn(...)` is reachable; rejects `subprocess.run`, `os.system`, `os.popen`, `shell=True`. Uses `raise AssertionError("...")` (bare `assert` forbidden).
- Golden files `tests/golden/probes/base_image/{distroless-target,alpine,multi-stage,scratch,unknown,debian-slim}.json`.
- Golden files `tests/golden/probes/shell_invocation_trace/{distroless-target,with-shell,no-trace-available}.json`.

**Done criteria:**
- [ ] `pytest tests/unit/probes/base_image/test_base_image_probe.py` covers happy path (Alpine, distroless, multi-stage, scratch, unknown, debian-slim) against golden files.
- [ ] `pytest tests/unit/probes/shell_invocation_trace/test_shell_trace_probe.py` covers happy path with a stub `SandboxClient`; `count > 0` and `count == 0` arms; build-failed degradation to `confidence: "low"`.
- [ ] `pytest tests/fence/test_shell_trace_probe_isolation.py` green; fails on a deliberately-planted `subprocess.run(...)` call inside `run()`.
- [ ] Probe-contract conformance fence (existing `tests/fence/test_probe_context_conformance.py` / similar) green for both new probes.
- [ ] `pytest tests/integration/test_probe_outputs_validate_against_envelope.py` — both new slices validate against the updated `repo_context.schema.json`.
- [ ] `mypy --strict plugins/distroless-migration--node--npm/probes` clean.
- [ ] `make check` green.

**Depends on:** Steps 1–6.

**Effort:** L — two probes (one light + one heavy), two sub-schemas, two ALLOWED_BINARIES amendments, one AST-walk fence, golden files for both. The heavy probe's sandbox integration is the integration-risk piece.

**Risks specific to this step:** Phase 5's `SandboxClient.spawn(role=Role.PROBE)` API behavior must match what `ShellInvocationTraceProbe.run()` assumes (trace JSON shape, host-side eBPF capture). Pin the integration test (`test_sandbox_client_role_probe.py` from Step 6) BEFORE writing the probe body.

## Step 8 — `DistrolessMigrationPlugin` manifest + TCCM `derived_queries:` band + plugin loader wiring

**Goal:** The plugin manifest and TCCM exist; the TCCM's new `derived_queries:` band resolves `compute: vuln.provenance` to the imported primitive callable; the plugin loader's explicit-import line is added; the resolver picks the migration plugin for `(task=distroless-migration, language=node, build=npm)` workflows.

**Features delivered:**
- `plugins/distroless-migration--node--npm/plugin.yaml` — `PluginManifest`: `id: distroless-migration--node--npm`, `scope: {task: distroless-migration, language: node, build: npm}`, `precedence: 100`, `extends: null`, `requirements.external_tools: [docker, dive, docker-buildx]`.
- `plugins/distroless-migration--node--npm/tccm.yaml`:
  - `must_read: [dockerfile, base_image, sbom]`
  - `should_read: [shell_invocation_trace, node_build_system]`
  - `derived_queries: [{name: provenance, compute: vuln.provenance, args: {cve_id: $workflow.cve, package_id: $workflow.package, image_ref: $repo.base_image}}]`
- `src/codegenie/plugins/tccm.py` — Pydantic schema gains additive `derived_queries: list[DerivedQuery] = []` field (the byte-edit enumerated in Step 5 row #6). `DerivedQuery(_Frozen)` typed model: `name: str`, `compute: str` (dotted callable, e.g. `"vuln.provenance"`), `args: dict[str, str]` (template strings; arg-template syntax pinned in story-writing: open question §9).
- `src/codegenie/plugins/tccm.py` loader resolves `compute:` to the imported callable at plugin-load time; unknown `compute:` references → loader fails fast with file/line diagnostic; Supervisor refuses to start.
- `src/codegenie/plugins/loader.py` — one new explicit-import line for `plugins.distroless_migration_node_npm.api` (enumerated row #7 of fence allowlist).
- `plugins/distroless-migration--node--npm/api.py` — declares the plugin instance, imports adapters + probes + recipes for side-effect registration.
- `plugins/distroless-migration--node--npm/skills/recipe-selection-hints.md` — YAML-frontmatter skill (recipe-selection hints; no LLM in Phase 7 — this is for Phase 8 consumption).

**Done criteria:**
- [ ] `pytest tests/integration/test_plugin_resolution_phase7.py` — Dockerfile + `package.json` fixture; resolver returns `distroless-migration--node--npm` for base-image-only CVE; returns `vulnerability-remediation--node--npm` for app-only.
- [ ] `pytest tests/integration/test_tccm_distroless_derived_queries_loads.py` — TCCM YAML loads; validates against extended Pydantic schema; `derived_queries.compute` resolves to the imported callable.
- [ ] `pytest tests/unit/plugins/test_tccm_derived_queries.py` — unknown `compute:` reference raises at plugin-load with file/line diagnostic; existing TCCMs without `derived_queries:` continue to parse unchanged (backward-compat).
- [ ] `mypy --strict src/codegenie/plugins/tccm.py plugins/distroless-migration--node--npm` clean.
- [ ] `make check` green.

**Depends on:** Steps 1–7.

**Effort:** M — plugin manifest + TCCM additive schema + loader explicit-import + integration tests for resolution.

**Risks specific to this step:** TCCM arg-template syntax (`$workflow.cve` vs `${workflow.cve}` vs another shape — open question §9) is not yet pinned. Pick at story-writing time; existing TCCMs must continue to parse unchanged.

## Step 9 — CVE-to-image catalog YAML + loader + file-hash fence

**Goal:** A frozen YAML CVE-to-image-recommendation catalog ships in the plugin's `data/`; the loader validates the catalog against a Pydantic schema; a file-hash fence detects out-of-CODEOWNERS tampering; refresh is a documented CODEOWNERS-gated PR process. **No Sigstore, no STS, no signed-artifact upgrade in Phase 7** (deferred per Phase 7 ADR-0007).

**Features delivered:**
- `plugins/distroless-migration--node--npm/data/chainguard_image_recommendation_table.yaml` — frozen YAML. Schema: `{cve_id: CveId, recommended_chainguard_image: ImageRef, image_digest: ImageDigest, notes: str}` rows.
- `plugins/distroless-migration--node--npm/data/loader.py` — `load_chainguard_catalog(path) -> Result[ChainguardCatalog, ParseError]`. Pydantic-validated; `frozen=True, extra="forbid"`; rejects malformed entries with file/line diagnostic. Loader rejects entries lacking `sha256:` digest (smart-constructor enforced via `ImageDigest` newtype).
- `docs/phases/07-migration-task-class/ADRs/0007-deferred-sigstore-catalog-upgrade.md` — Nygard ADR recording the deferred upgrade path.
- `tests/fence/test_phase7_chainguard_lookup_table_loads.py` — pins the file sha256 hash; tamper detection at CI time. CODEOWNERS-gated refresh is the only legitimate hash-update path.
- `docs/phases/07-migration-task-class/catalog-refresh-process.md` — documents the CODEOWNERS-reviewed publish workflow.
- Initial catalog seeded with the e2e fixture's CVE and the Chainguard `node` recommendation digest.

**Done criteria:**
- [ ] `pytest tests/unit/plugins/distroless_migration_node_npm/test_catalog_loader.py` covers happy load, malformed entry rejection, missing digest rejection.
- [ ] `pytest tests/fence/test_phase7_chainguard_lookup_table_loads.py` green; fails on a deliberately-planted byte-edit to the YAML.
- [ ] `mypy --strict plugins/distroless-migration--node--npm/data` clean.
- [ ] `make check` green.

**Depends on:** Step 1 (`ImageDigest` newtype with `sha256:` smart constructor).

**Effort:** S — one YAML file + one loader + one fence test + one process doc. Effort is in the catalog content (correct Chainguard recommendation digests), which is data-collection work.

**Risks specific to this step:** Operator-side tamper is the threat model; the file-hash fence is the only defense in Phase 7. If the threat model is later ratified to require Sigstore, the deferred ADR-0007 names the upgrade path.

## Step 10 — `DockerfileBaseImageSwapTransform` + `DockerfileMultiStageRefactorTransform` + `DockerfilePolicyGate` + `DistrolessBuildGate` + `ShellInvocationDeltaGate`

**Goal:** Two deterministic Dockerfile recipes extending Phase 3's `Transform` ABC ship under the plugin; three Phase 5 gate-catalog contributions register via `@register_signal_kind`; strict-AND policy gate has no `--allow-policy-violations` override; `DockerfileMultiStageRefactorTransform` is synchronous (no `asyncio.gather`).

**Features delivered:**
- `plugins/distroless-migration--node--npm/recipes/__init__.py`.
- `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py` — `DockerfileBaseImageSwapTransform(Transform)`. Reads `data/chainguard_image_recommendation_table.yaml` (via Step 9's loader). Pure-Python `dockerfile-parse` AST manipulation: single `FROM` swap + multi-stage runner adjustments (`COPY --from=builder`, `USER nonroot`, exec-form ENTRYPOINT). **No `docker build` in the recipe** — building is `DistrolessBuildGate`'s job. `applicability()` returns `Applies` only when the catalog has a matching recommendation; `apply()` returns `TransformOutcome.Applied(diff)`.
- `plugins/distroless-migration--node--npm/recipes/dockerfile_multi_stage.py` — `DockerfileMultiStageRefactorTransform(Transform)`. Per-stage AST manipulation: moves shell-using `RUN` lines into a builder stage; runtime stage gets exec-form `CMD`. **Synchronous, no `asyncio.gather`** (CPU-bound).
- `plugins/distroless-migration--node--npm/recipes/dockerfile_policy_gate.py` — `DockerfilePolicyGate(Gate)` decorated `@register_signal_kind(name="dockerfile_policy", isolation_class="none")`. Six invariants: USER set non-root; no new `--cap-add`; no new `--privileged`; exec-form ENTRYPOINT; no shell-form HEALTHCHECK; no new build-time secret mounts. **No `--allow-policy-violations` override.** Pure function over rendered Dockerfile text + parsed AST.
- `plugins/distroless-migration--node--npm/recipes/distroless_build_gate.py` — `DistrolessBuildGate(Gate)` decorated `@register_signal_kind(name="distroless_build", isolation_class="microvm")`. Runs `docker buildx build --target=runtime` via `SandboxClient.spawn(role=Role.GATE)`.
- `plugins/distroless-migration--node--npm/recipes/shell_invocation_delta_gate.py` — `ShellInvocationDeltaGate(Gate)` decorated `@register_signal_kind(name="shell_invocation_delta", isolation_class="microvm")`. Re-runs the shell-trace probe against the migrated image via `SandboxClient.spawn(role=Role.GATE)`; passes iff `shell_invocations.count == 0`.
- Golden files `tests/golden/dockerfile-diffs/{alpine-to-chainguard,multi-stage-refactor}.diff`.

**Done criteria:**
- [ ] `pytest tests/unit/transforms/recipes/test_dockerfile_base_image_swap.py` covers happy path against golden diff; lookup miss → `not_applicable(reason="no_distroless_counterpart")`; unparseable Dockerfile → `not_applicable(reason="dockerfile_parse_failed")`. p99 ≤ 80 ms.
- [ ] `pytest tests/unit/transforms/recipes/test_dockerfile_multi_stage.py` covers multi-stage refactor against golden diff; synchronous execution (no `asyncio.gather` in body — verified by AST walk). p99 ≤ 350 ms.
- [ ] `pytest tests/unit/gates/test_dockerfile_policy_gate.py` covers all six invariants; each invariant has a fail-fixture and a pass-fixture; strict-AND failure produces `DockerfilePolicyGateFailed(failing_invariants=[...])`.
- [ ] `pytest tests/integration/test_gates_register_phase7.py` — all three gates register via `@register_signal_kind` and participate in strict-AND scoring; no override flag exists.
- [ ] `pytest tests/perf/test_dockerfile_recipes.py` (`@pytest.mark.bench`) — swap ≤ 80 ms p99 across 1000 trials; multi-stage ≤ 350 ms p99.
- [ ] `mypy --strict plugins/distroless-migration--node--npm/recipes` clean.
- [ ] `make check` green.

**Depends on:** Steps 1–9.

**Effort:** L — two recipes + three gates + policy invariants + golden files + perf tests.

**Risks specific to this step:** `DockerfileMultiStageRefactorTransform` is the highest-complexity piece; the per-stage AST manipulation has corner cases (`COPY --from=base` referencing removed stage, etc. — Edge case #7). Pin edge-case fixtures before the implementation.

## Step 11 — `Both` variant emission + `coordination-summary.yaml` writer + `codegenie list-coordination-candidates` CLI

**Goal:** When `assemble_provenance` returns `Both`, the orchestrator emits a typed `RequiresMultiPluginCoordination` event into the spanning log + writes `coordination-summary.yaml` + exits with code 8. The operator-facing `codegenie list-coordination-candidates` subcommand reads the spanning log and shows pending events. **No `MultiPluginCoordinator` class ships** (Phase 8 owns it per ADR-0042).

**Features delivered:**
- `src/codegenie/primitives/vuln_provenance/events.py` — `RequiresMultiPluginCoordination(_TypedEvent)` with `workflow_id: WorkflowId`, `app_record: AppKind`, `base_record: BaseKind`, `summary_path: Path`, `emitted_at: datetime`, `schema_version: Literal["phase-7-0"] = "phase-7-0"` (Gap 2 forward-compat).
- `plugins/distroless-migration--node--npm/subgraph/api.py` — `emit_coordination(orch_ctx, both: Both) -> None` writes the typed event to the spanning log and writes `coordination-summary.yaml` to `.codegenie/coordination/<workflow_id>.yaml`. Returns `Applicability.PendingCoordination`. Orchestrator translates `PendingCoordination` to CLI exit code 8.
- `coordination-summary.yaml` Pydantic schema: `workflow_id`, `cve_id`, `app` (kind + package + manifest_path), `base` (kind + image_digest + distro_pkg), `proposed_plugin_routes`, `awaiting: phase_8_planner`, `schema_version: "phase-7-0"`. `extra="forbid"`.
- `.codegenie/coordination/_index.tsv` — append-on-write index (Gap 5 mitigation; the pre-Phase-13.5 portfolio-scale-friendly format).
- `src/codegenie/cli/list_coordination_candidates.py` — `codegenie list-coordination-candidates [--since DATE] [--format yaml|table|json]` walks `.codegenie/events/spanning/*.jsonl.zst`, filters on `kind == "requires_multi_plugin_coordination"`, formats.
- Exit-code constant `EXIT_PENDING_COORDINATION = 8` added (existing exit-code module). Documented in CLI `--help`.
- Golden file `tests/golden/coordination-summary/both-app-direct-plus-base-image.yaml`.

**Done criteria:**
- [ ] `pytest tests/unit/primitives/vuln_provenance/test_events.py` covers `RequiresMultiPluginCoordination` round-trip JSON + `extra="forbid"` rejection.
- [ ] `pytest tests/unit/plugins/distroless_migration_node_npm/test_emit_coordination.py` covers the writer: event lands in spanning log, summary YAML written, TSV index appended.
- [ ] `pytest tests/unit/cli/test_list_coordination_candidates.py` covers `--format yaml|table|json` outputs.
- [ ] `pytest tests/integration/test_both_exits_with_code_8.py` — full workflow with `Both` provenance exits with code 8.
- [ ] Golden-file equality on `coordination-summary.yaml` shape.
- [ ] `mypy --strict src/codegenie/primitives/vuln_provenance/events.py src/codegenie/cli/list_coordination_candidates.py` clean.
- [ ] `make check` green.

**Depends on:** Steps 1–10.

**Effort:** M — typed event + YAML writer + CLI subcommand + golden file + TSV index. CLI subcommand is small but `--format table` formatting deserves care.

**Risks specific to this step:** `coordination-summary.yaml` schema is provisional (open question §1); the `schema_version: "phase-7-0"` field is the forward-compat hook for Phase 8 to introduce `phase-8-0` additive fields. Pin the minimal Phase-7-0 shape here; do NOT speculate on Planner-specific fields.

## Step 12 — End-to-end test suite + property tests + adversarial tests + regression-gate enforcement

**Goal:** The headline e2e tests pass: vulnerable Node.js → Chainguard distroless migration; `Both` provenance emits the coordination event. Property tests pin the load-bearing invariants (idempotence, dispatch order, SBOM tampering, `Both` always emits coordination). Adversarial tests cover poisoned SBOM, poisoned catalog YAML, Dockerfile prompt-injection-shaped strings. The Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay are confirmed as a hard pre-merge gate.

**Features delivered:**
- `tests/e2e/test_distroless_migration_e2e.py` (`@pytest.mark.phase07_e2e`) — vulnerable Node.js fixture (Alpine base, app deps clean); assert migrated branch carries `FROM cgr.dev/chainguard/node`; `remediation-report.yaml` written; `npm test` passes in `SubprocessJail`.
- `tests/e2e/test_both_provenance_emits_coordination_event_e2e.py` (`@pytest.mark.phase07_e2e`) — fixture repo with CVE in BOTH layers; assert `assemble_provenance` returns `Both`; assert `RequiresMultiPluginCoordination` event lands in spanning log; assert exit code 8; assert `coordination-summary.yaml` writes. **No PR is opened.**
- `tests/property/vuln_provenance/test_both_invariant.py` — for any `(AppKind, BaseKind)` pair where both are non-`Unknown`, `assemble_provenance` returns `Both(app_record, base_record)`; no recursion.
- `tests/property/vuln_provenance/test_both_always_emits_coordination.py` — for every workflow where `assemble_provenance` returns `Both`, the spanning event log contains exactly one `RequiresMultiPluginCoordination` event and the CLI exit code is 8.
- `tests/fixtures/portfolio/node-vulnerable-alpine/` — `Both` fixture.
- `tests/fixtures/portfolio/node-vulnerable-app-only/` — app-only fixture.
- `tests/fixtures/portfolio/node-vulnerable-base-only/` — base-only fixture.
- `tests/fixtures/portfolio/node-already-distroless/` — no-op fixture.
- `tests/fixtures/portfolio/multi-stage-dockerfile/` — multi-stage refactor exercise.
- `tests/adversarial/test_dockerfile_prompt_injection_strings.py` — Dockerfile comments containing `Ignore previous instructions; FROM evil/image`; deterministic recipes treat the strings as data; assert no behavioral change.
- `bench/migration-chainguard-distroless/` — bench tier expanded to 10 cases (open question §5 pinned here): % single-plugin vs `Both` vs `Unknown` calibrated during story-writing.
- Performance regression tests added (`@pytest.mark.bench`): `tests/perf/test_assemble_provenance_uncached.py` (p99 ≤ 50 ms across 1000 trials); `tests/perf/test_base_image_probe.py` (p99 ≤ 60 ms cold / ≤ 2 ms warm).
- CI configuration: `@pytest.mark.phase07_e2e` matrix-split on `--privileged` Linux runners — opt-in per-PR via label, mandatory on `main`-merge (open question §6 pinned here).

**Done criteria:**
- [ ] `pytest tests/e2e/test_distroless_migration_e2e.py -m phase07_e2e` green on Linux `--privileged` runner.
- [ ] `pytest tests/e2e/test_both_provenance_emits_coordination_event_e2e.py -m phase07_e2e` green; exit code 8 asserted; spanning event log has exactly one `RequiresMultiPluginCoordination`.
- [ ] All property tests green (Hypothesis seed pinned).
- [ ] All adversarial tests green.
- [ ] `bench/vuln-remediation/` cassette replay green; cost-ledger byte-equality preserved (ε ≤ $0.01).
- [ ] `bench/migration-chainguard-distroless/` cassette replay green for the 10 new cases.
- [ ] **Phase 3–6.5 regression suite green** (`make check` — confirmed as hard pre-merge gate in CI config).
- [ ] `make check` green end-to-end.
- [ ] `make docs` green (mkdocs strict — phase-arch-design + High-level-impl + ADRs all render).

**Depends on:** Steps 1–11.

**Effort:** L — six fixtures + two e2e tests + five property tests + adversarial + perf + bench expansion + CI matrix config.

**Risks specific to this step:** The `--privileged` Linux runner constraint may force matrix-split work in CI. If the runner pool is constrained, fall back to `main`-merge-only enforcement and document in the e2e test's docstring.

---

# Amendment A — Steps 13–18 (2026-05-20)

Steps 13–18 are additive per `final-design.md` Amendment A and
`phase-arch-design.md` component designs §15–§23. They deepen the gather
pipeline so a distroless migration is transformed correctly or **refused with
typed evidence**. **Sequencing:** Steps 13–15 (gather probes) land *before* the
existing Step 10 recipe stories execute; Steps 16–18 layer after. The
still-`Ready` stories S7-01, S8-02/S8-03, S10-01/S10-02/S10-03 have their
acceptance criteria amended to consume the new slices.

## Step 13 — Source-secret + target-image gather (G1, G2)

**Goal:** Two new probes — `DockerfileSecretPatternProbe` inventories how the
source repo acquires build secrets; `TargetImageContentProbe` inventories what
the recommended Chainguard image already provides. `crane` joins
`ALLOWED_BINARIES`. The byte-edit allowlist fence (ADR-0009) is amended for
every Amendment-A source file.

**Features delivered:**
- `plugins/distroless-migration--node--npm/probes/dockerfile_secret_pattern_probe.py` — `DockerfileSecretPatternProbe(Probe)`, Layer C, light, static, `@register_probe`. `dockerfile-parse` AST walk; `_SECRET_PATTERN_RULES: Final[tuple[SecretRule, ...]]` open/closed catalog; `external_script` classified opaque (no `tree-sitter-bash`).
- `plugins/distroless-migration--node--npm/probes/target_image_content_probe.py` — `TargetImageContentProbe(Probe)`, Layer E, `cache_strategy="content"`, `declared_inputs=["image-digest:<target-resolved>"]`. `crane manifest`/`crane config` + Chainguard SBOM via the `SbomProbe` machinery.
- Probe sub-schemas under `plugins/distroless-migration--node--npm/schema/{secret_pattern,target_image_content}.schema.json`; two additive `$ref` insertions into `repo_context.schema.json`.
- `src/codegenie/exec/__init__.py::ALLOWED_BINARIES` += `crane` (ADR-0028).
- `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` allowlist amended per ADR-0029.
- Golden fixtures under `tests/golden/probes/{secret_pattern,target_image_content}/`.

**Done criteria:**
- [ ] Unit tests cover each `SecretPattern.kind` against golden Dockerfiles; `external_script` produces the opaque record.
- [ ] `TargetImageContentProbe` golden tests cover `shell_present` true/false, `already_satisfied_run_lines`, `supported_architectures`.
- [ ] Both slices validate against the updated envelope schema.
- [ ] `mypy --strict` + `make check` green.

**Depends on:** Steps 1–9. **Effort:** L. **ADRs:** 0018, 0019, 0028, 0029.

## Step 14 — Build-toolchain classification + native modules (G3)

**Goal:** A frozen classification catalog splits `apk`/`apt` packages into
`build_toolchain | runtime_library | diagnostic`; `NodeManifestProbe`'s slice
gains a `native_modules` field. The multi-stage recipe uses both to put each dep
in the right stage and to select the `*-dev` builder image when native modules
are present.

**Features delivered:**
- `plugins/distroless-migration--node--npm/data/apk_classification.yaml` + `apt_classification.yaml` — frozen, CODEOWNERS-gated, loaded through the catalog-loader seam.
- `NodeManifestProbe` slice extended with `native_modules: tuple[NativeModule, ...]` (additive schema field; detects `binding.gyp`, `*.node`, `node-gyp`).
- Catalog file-hash fence (mirrors S9-02's catalog fence shape).

**Done criteria:**
- [ ] Catalog loader rejects an unknown classification value; every catalog entry has a known disposition.
- [ ] `native_modules` slice populated correctly on a native-module fixture and empty on a pure-JS fixture.
- [ ] `mypy --strict` + `make check` green.

**Depends on:** Step 13. **Effort:** M. **ADRs:** 0020, 0029.

## Step 15 — Runtime-compatibility gather (G4, G6, G7–G10, G12)

**Goal:** Three probes surface the runtime-environment hazards a `nonroot`
distroless image introduces: app-code shell-out, healthcheck/deployment-probe
shell dependence, and uid/PID-1/filesystem/locale assumptions.

**Features delivered:**
- `plugins/distroless-migration--node--npm/probes/runtime_shell_invocation_probe.py` — tree-sitter JS/TS (`grammars.lock.language_for`); typed hits with `criticality ∈ {blocking, advisory}` by path (`src/**` blocking, `tests/**` advisory — G12).
- `plugins/distroless-migration--node--npm/probes/container_probe_compat_probe.py` — analyses the deployment manifests `DeploymentProbe` locates (`docker-compose.yml`, K8s, helm) for `exec`/`curl`/`wget` probes.
- `plugins/distroless-migration--node--npm/probes/runtime_compat_probe.py` — uid/user delta, PID-1/signals, filesystem (`/etc/passwd`, `/tmp`, literal-path `fs.readFile`), locale/TZ.
- Three probe sub-schemas + three additive `$ref` insertions.
- Golden fixtures for each probe.

**Done criteria:**
- [ ] `RuntimeShellInvocationProbe` classifies a `src/**` `child_process.exec` blocking and a `tests/**` one advisory.
- [ ] `ContainerProbeCompatProbe` flags a K8s `exec` liveness probe and a `HEALTHCHECK curl`.
- [ ] `RuntimeCompatProbe` flags a `COPY` without `--chown` and a privileged `EXPOSE`.
- [ ] All three slices validate against the envelope schema; `make check` green.

**Depends on:** Steps 6 (SandboxRole), 13. **Effort:** L. **ADRs:** 0021, 0022, 0023, 0029.

## Step 16 — Refusal taxonomy + recipe transformation contract (G5, M2)

**Goal:** A closed refusal taxonomy makes "cannot transform deterministically" a
typed outcome with evidence; the recipes gain typed gather inputs and the
ability to refuse. Amends the still-`Ready` stories S10-01/S10-02/S10-03.

**Features delivered:**
- `src/codegenie/transforms/outcomes.py` — additive `RemediationOutcome.PendingHumanReview` variants (`RefusedOpaqueSecretScript`, `RefusedRuntimeShellOutInProductionCode`, `RefusedNativeModulesUnclassified`, `RefusedNonDeterministicEntrypoint`, `RefusedArchitectureLoss`, `RefusedExternalRegistryBaseImage`), each with a structured source-location payload. ADR-gated byte-edit (ADR-0029).
- `DockerfileBaseImageSwapTransform` + `DockerfileMultiStageRefactorTransform` — gain typed inputs (`SecretPatternSlice`, `TargetImageContentSlice`, `native_modules`); strip `already_satisfied_run_lines`; rewrite shell-form `ENTRYPOINT`/`CMD` to exec-form where deterministic; refuse otherwise.
- `DockerfilePolicyGate` consumes the refusal taxonomy.

**Done criteria:**
- [ ] Each refusal variant has a test producing it from a crafted fixture; `match`/`assert_never` exhaustiveness holds.
- [ ] The swap recipe drops a redundant `RUN apk add ca-certificates` and rewrites `CMD node x` → `CMD ["node","x"]`.
- [ ] An opaque-secret-script fixture yields `RefusedOpaqueSecretScript`, not a diff.
- [ ] `mypy --strict` + `make check` green.

**Depends on:** Steps 13–15. **Effort:** L. **ADRs:** 0025, 0029.

## Step 17 — Migration confidence + multi-arch / external-registry checks (M1, G11, G13)

**Goal:** A single `MigrationConfidence` rollup the orchestrator refuses
against; `BaseImageProbe` extended for architecture-coverage delta and
non-public-registry detection. Amends still-`Ready` story S7-01.

**Features delivered:**
- `MigrationConfidence = High | Degraded(reasons) | Refused(reason)` sum type + `aggregate_migration_confidence(...)` pure function.
- `BaseImageProbe` slice extended with `supported_architectures` (source) and `non_public_registry: bool`; arch-loss → `RefusedArchitectureLoss`; non-public mirror → `AdapterConfidence.Degraded` + WARN.

**Done criteria:**
- [ ] `aggregate_migration_confidence` returns `Degraded` when any probe is `low`; property-tested.
- [ ] An armv7-only source against an amd64/arm64 target yields `RefusedArchitectureLoss`.
- [ ] `mypy --strict` + `make check` green.

**Depends on:** Steps 13–16. **Effort:** M. **ADRs:** 0024, 0026, 0029.

## Step 18 — Migration observability (G14–G17, M3)

**Goal:** Make the migration's effect legible to the human merger and reuse the
heavy trace probe across CVEs.

**Features delivered:**
- `transformations_applied: tuple[TransformationKind, ...]` on the migration record; rendered into the PR description.
- Workflow events `MigrationSizeRegression` (pre/post compressed size, G14); `pre_migration_image_ref` capture for the rollback runbook (G15); attestation diff (G16).
- `ShellInvocationTraceProbe` content-cache entry reused across CVEs for the same `(Dockerfile, package.json, image-digest)` (G17).

**Done criteria:**
- [ ] PR description includes `transformations_applied`, image-size delta, and the rollback line.
- [ ] A second CVE against the same repo reuses the cached trace (cache-hit asserted).
- [ ] `mypy --strict` + `make check` green.

**Depends on:** Steps 13–17. **Effort:** M. **ADRs:** 0027, 0029.

---

## Exit-criteria mapping

| Roadmap exit criterion | Step(s) that satisfy it |
|---|---|
| Both task classes run from the same orchestration | Step 8 (plugin manifest + TCCM + resolver wiring) → Step 10 (recipes + gates) → Step 12 (e2e tests confirm via `tests/e2e/test_distroless_migration_e2e.py` and `tests/integration/test_plugin_resolution_phase7.py`) |
| Existing plugins and stable existing behavior are unchanged | Step 5 (byte-edit allowlist fence with 10 enumerated rows) + Step 12 (Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay as hard pre-merge gate) |
| Any shared primitive added is bounded, additive, ADR-backed, and covered by regression tests | Step 1 (primitive lands at `src/codegenie/primitives/vuln_provenance/` under ADR-0039; types + Protocol + errors) + Step 2 (registry + assembly under the same primitive) + Step 5 (import-linter contract bounds the primitive's imports) + Steps 1/2/4/11 (regression tests: property + unit + integration + e2e covering every primitive surface) |
| `vuln.provenance` primitive lands with at least app + base-image adapters; adapter-chain assembly answered | Step 1 (primitive types) + Step 2 (assembly + `_ADAPTER_DISPATCH_ORDER`) + Step 3 (`NpmVulnProvenanceAdapter` — app layer) + Step 4 (`AlpineVulnProvenanceAdapter` + `DistrolessVulnProvenanceAdapter` — base-image layer) |
| `Both` provenance variant produces evidence, not coordination | Step 11 (`RequiresMultiPluginCoordination` event + `coordination-summary.yaml` + exit code 8 + `codegenie list-coordination-candidates` CLI; **no `MultiPluginCoordinator` class ships**) |

## Implementation-level risks

These are work-level, not design-level. Design-level risks live in `phase-arch-design.md §Risks`.

1. **Adapter contract incompatibility with the promoted Phase 3 `NpmVulnProvenanceAdapter` shape.** Phase 3 ships a refuse-mode shape per ADR-0038 Consequences; Phase 7 ships a real adapter as an additive file. If the contract diverges, Phase 7 would be tempted to byte-edit Phase 3's internals and break the byte-edit invariant. **Mitigate:** write the integration test (`tests/integration/test_provenance_assembly_via_plugins.py`) FIRST in Step 3, before the adapter body lands. The test pins the API surface Phase 3's internals must expose; if missing, surface as a follow-up Phase 3 ticket (not an inline edit).

2. **Phase 5 amendment ratification delay (Step 6).** Phase 7 ADR-0003 records the `SandboxRole` amendment; Phase 5 must accept it. If rejected, fallback to `Role.GATE` for the heavy probe with audit-clarity cost. **Mitigate:** sequence ADR-0003 ratification as a blocking precondition for Step 6 story-writing.

3. **The byte-edit allowlist fence (Step 5) lands after Steps 3 + 4 have already edited Phase 3 plugin files.** Without Step 5 in place, Steps 3 + 4 are unprotected. **Mitigate:** the allowlist fence in Step 5 enumerates BOTH past edits (Steps 3 + 4) and future edits (Steps 6 + 7 + 8). Story-writing for Step 5 must precede Step 3 implementation, even though Step 5 ships after Steps 3 + 4.

4. **Plugin resolver ambiguity on `Both` workflows.** When BOTH plugins match `(task=vulnerability-remediation, language=node, build=npm)` via `vuln.provenance(...)` returning `Both`, the resolver must surface `PendingCoordination` rather than pick one. **Mitigate:** Step 8's resolution integration test (`tests/integration/test_plugin_resolution_phase7.py`) covers this case explicitly; Step 11's `Both` emission produces the typed event.

5. **`dockerfile-parse` AST edge cases (heredoc, ARG-driven FROM, build args).** `BaseImageProbe` and the two recipes all depend on `dockerfile-parse` correctness. **Mitigate:** Edge case #13 in `phase-arch-design.md` pins the failure mode (`base_image.dockerfile_parse_failed` warning + `confidence: "low"`); fixture portfolio in Step 12 includes exotic Dockerfile shapes; recipes return `not_applicable(reason="dockerfile_parse_failed")` rather than crashing.

6. **CI matrix split for `@pytest.mark.phase07_e2e` (Step 12).** The `--privileged` Linux runner requirement may not be available on every PR. **Mitigate:** open question §6 — pin "opt-in per-PR via label, mandatory on `main`-merge" at story-writing; falls back to `main`-merge-only if runner pool is constrained.

7. **`bench/migration-chainguard-distroless/` cassette tier expansion to 10 cases (Step 12).** Phase 6.5 ships 3 seeds; growing to 10 requires curated case selection. **Mitigate:** open question §5 — case distribution (% single-plugin vs `Both` vs `Unknown`) calibrated against bench-tier threshold during Step 12 story-writing; do not block earlier steps on this.

8. **TCCM `derived_queries:` arg-template syntax (Step 8).** Open question §9 — pin during Step 8 story-writing. **Mitigate:** existing TCCMs without `derived_queries:` must continue to parse unchanged (backward-compat done-criterion).

## What's next — handoff to Phase 8

### New artifacts on disk

- `src/codegenie/primitives/vuln_provenance/` — the bounded core primitive; ADR-0039's additive home now established.
- `plugins/distroless-migration--node--npm/` — second production plugin; reads its own probes + recipes + gates + adapters + catalog YAML.
- `.codegenie/context/raw/{base_image,shell_invocation_trace}.json` — two new probe outputs.
- `.codegenie/context/repo-context.yaml` — gains two new probe slices via additive `$ref` insertions.
- `.codegenie/coordination/<workflow_id>.yaml` + `_index.tsv` — `coordination-summary.yaml` writes on `Both` exit.
- `.codegenie/events/spanning/*.jsonl.zst` — four new event variants: `ProvenanceQueried`, `BaseImageResolved`, `ShellInvocationObserved`, `RequiresMultiPluginCoordination`. Plus `DistrolessMigrationProposed`, `DockerfilePolicyGate{Passed,Failed}` in workflow-internal.

### New contracts ready for Phase 8

- **`Provenance` discriminated union** — Phase 8's Planner imports `Provenance, AppKind, BaseKind, Both` and routes on the variant. Stable from Phase 7 onward per ADR-0039.
- **`@register_provenance_adapter` registry** — Phase 8's Planner may query `_REGISTRY` (read-only) to enumerate available adapters for routing decisions; may not mutate.
- **`assemble_provenance(...)` callable** — Phase 8's Stage 1 Assessment (Phase 10) calls this per `(repo, cve)` pair to compute eligibility distributions per task class. Phase 7's TCCM `derived_queries:` is the in-workflow consumer; Phase 10's portfolio-scale Assessment is the cross-workflow consumer.
- **`RequiresMultiPluginCoordination` typed event** — Phase 8's Planner is the canonical consumer. Phase 8 reads the spanning log, projects pending events, emits coordinated child workflows. Phase 7 ships `schema_version: "phase-7-0"`; Phase 8 may add `phase-8-0` additive fields.
- **`SandboxRole.PROBE` enum value** — Phase 8's Planner may decide to schedule probes on cheaper runners; the `role` parameter is the routing signal.
- **`derived_queries:` TCCM band** — Phase 8's Planner reads the TCCM to know which derived queries each plugin expects; the schema is typed.

### New CI gates in place

- **Byte-edit allowlist fence** (`tests/fence/test_phase7_no_byte_edits_to_locked_files.py`) — mechanical "additive" enforcement; future phases inherit and extend.
- **Phase 7 LLM-fence** (`tests/fence/test_phase7_no_llm.py`) — `import_linter` contract; the primitive and the plugin may not import LLM SDKs.
- **Shell-trace probe isolation fence** (`tests/fence/test_shell_trace_probe_isolation.py`) — AST-walk asserts only `SandboxClient.spawn(...)` is reachable in the heavy probe's `run()`.
- **Plugin-directory probe fence** (`tests/fence/test_provenance_primitive_in_plugin_directory.py`) — task-class-specific probes live under the plugin, not under `src/codegenie/probes/`.
- **Chainguard catalog tamper fence** (`tests/fence/test_phase7_chainguard_lookup_table_loads.py`) — pinned file-hash check.
- **Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay** confirmed as hard pre-merge gate; cost-ledger byte-equality (ε ≤ $0.01).
- **`@pytest.mark.phase07_e2e` matrix-split** — opt-in per-PR via label, mandatory on `main`-merge.

### Implicit assumptions Phase 8 Planner can rely on

- **`assemble_provenance` is total.** Every `(cve_id, package_id, image_ref, sbom)` tuple returns exactly one of seven `Provenance` variants. The Planner can pattern-match exhaustively.
- **`Both` is unambiguous.** When `Both` is emitted, the event in the spanning log carries the typed `app_record` + `base_record` (not raw `dict`). Phase 8 doesn't need to re-parse SBOMs.
- **Adapter registration is deterministic.** Plugin load order doesn't affect dispatch order (`_ADAPTER_DISPATCH_ORDER` is explicit). Phase 8 doesn't have to reason about plugin-load timing.
- **The spanning event log is append-only.** `RequiresMultiPluginCoordination` events accumulate; Phase 8's projector reads in order; no Phase 7 mutation.
- **No coordination sequencing exists yet.** Phase 7 emits the event and exits — Phase 8 is the canonical sequencer per ADR-0042. Phase 11 will add atomicity enforcement; Phase 7 does NOT pre-empt that.
- **No `vuln.provenance` cache exists.** Phase 14 owns caching per ADR-0038 §Tradeoffs; Phase 8 must not assume cache hits. Each `assemble_provenance` call is recomputed from inputs.
- **No real PRs are opened.** Phase 11 is the first PR-at-scale phase; Phase 7 writes diffs and `remediation-report.yaml` but doesn't `git` + `gh pr create`. Phase 8's Planner must not assume PR creation has happened.

---

**End of high-level implementation plan.**
