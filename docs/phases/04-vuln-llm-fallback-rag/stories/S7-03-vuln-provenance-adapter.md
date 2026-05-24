# Story S7-03 — `NpmVulnProvenanceAdapter` (Phase-4-scoped subset)

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** HARDENED (BLOCKED on upstream) — see [`_validation/S7-03-vuln-provenance-adapter.md`](_validation/S7-03-vuln-provenance-adapter.md) for the full audit.
**Effort:** S (excluding upstream-blocker resolution)
**Depends on (HARD):**
- **S2-01 (this phase)** — `ProvenanceGate.classify(cve_id, package_id, image_ref, sbom) -> Provenance` + the `ProvenanceClassifier` facade Protocol; the gate is the adapter's downstream consumer. **HARDENED, not yet GREEN** (UB-3).
- **Phase 3 S7-05** — `is_app_layer_lookup` pure helper + `VerifyCveInAppLayerNode` (the **canonical** Phase 3 deliverable; there is no Phase-3 `NpmVulnProvenanceAdapter` class to "generalize"). **HARDENED, not yet GREEN** (UB-2).
- **Phase 3 plugin scaffold** — `plugins/vulnerability-remediation--node--npm/` directory with the plugin's `api.py` and `tccm.yaml`. **Not yet implemented** (UB-1).
- **Production primitive** — `src/codegenie/primitives/vuln_provenance/{types.py, protocols.py, errors.py, registry.py}` (already shipped). Source of truth for the `Provenance` discriminated union (lower-case `kind`), the `VulnProvenanceAdapter` Protocol (`attribute(...)` + `confidence()`), the `AdapterError` typed-exception hierarchy, and the `@register_provenance_adapter` decorator.

**ADRs honored:** production ADR-0038 (provenance gate semantics — the seven-variant primitive); Phase 4 ADR-0012 (`ProvenanceGate` as tier-0; `{BaseImage, RuntimeBundled, Unknown}` refuse); Phase 7 ADR-0004 (primitive home: `src/codegenie/primitives/vuln_provenance/`); Phase 7 ADR-0005 (adapter lives under plugin directory, **not** `src/codegenie/`); Phase 7 ADR-0007 (registry stores **classes**; construction via factory with closed kwarg vocabulary); Phase 7 ADR-0009 (Phase-7 byte-edit allowlist — this story creates a **new** plugin file, which is additive, not an edit).

## Validation notes (2026-05-24, scheduled validator run)

Hardened by `phase-story-validator`. Full audit: [`_validation/S7-03-vuln-provenance-adapter.md`](_validation/S7-03-vuln-provenance-adapter.md). Verdict: **HARDENED with upstream BLOCKED status**. The story's goal is sound; the original draft contradicted every shipped contract. Block-tier closures:

- **No Phase-3 `NpmVulnProvenanceAdapter` class exists to "generalize."** Phase 3 S7-05 ships a pure `is_app_layer_lookup` helper plus a `VerifyCveInAppLayerNode` subgraph node — not an adapter class. This story creates a **new** adapter file that **composes** the Phase 3 helper. The "Surgical per Global Rule 3" framing inverts the right discipline; the load-bearing CLAUDE.md commitment is **"Extension by addition — no silent edits."**
- **The adapter Protocol method is `attribute(cve_id, package_id, image_ref, sbom) -> Provenance`, NOT `classify(advisory, repo_ctx) -> Provenance`.** `CveAdvisory` and `RepoContext` are not importable types. The shipped Protocol is at `src/codegenie/primitives/vuln_provenance/protocols.py`. `confidence() -> AdapterConfidence` is the second required method.
- **`Provenance` variants live at `codegenie.primitives.vuln_provenance.types`**, not at `codegenie.fallback.types` (which does not exist). The discriminator field is `kind` and values are lower-case (`"app_direct"`, `"app_transitive"`, …) per S2-01's hardening.
- **Phase-4 scope produces only `{AppDirect, AppTransitive, AppVendored, Unknown}`.** Base-image and runtime-bundled classification requires Phase 7's base-image adapter chain plus `assemble_provenance`. The Phase-4 subset collapses missing-base-image-evidence to `Unknown(reason="no_adapter_resolved")`; Phase 7 S3-02 widens the same class additively to the full seven variants.
- **File path is `adapters/npm_provenance.py`**, not `adapters/vuln_provenance.py`. Matches Phase 7 S3-02's canonical naming and the "one provenance adapter per ecosystem" pattern.
- **The `is_app_layer(advisory, repo_ctx) -> bool` wrapper proposed in the original AC-2 is removed.** S2-01 already shipped `is_app_layer(provenance: Provenance) -> bool` over lower-case `_APP_LAYER_PROVENANCE_KINDS`. Two same-named functions with different signatures is a code smell; the gate is the consumer of the adapter, no wrapper is needed.

## Context

ADR-0012 elevates the production ADR-0038 `vuln.provenance` primitive to a **tier-0 explicit gate** in `FallbackTier.run`. The gate (S2-01, HARDENED) delegates classification to a `ProvenanceClassifier` facade Protocol over already-extracted typed inputs (`CveId`, `PackageId`, `ImageRef | None`, `SyftSbom`). This story ships the **first concrete adapter** the gate's classifier wraps: the NPM `VulnProvenanceAdapter`.

There is **no Phase-3 adapter class to generalize**. Phase 3 S7-05 ships a precursor — a pure `is_app_layer_lookup` helper (callable directly over the resolved npm dep graph + the CVE's affected-package set) and a `VerifyCveInAppLayerNode` (a `SubgraphNode` for the npm plugin's subgraph). The Phase 3 story explicitly says it "seeds the adapter shape Phase 7 inherits." This story builds that adapter: a class implementing the shipped `VulnProvenanceAdapter` Protocol, decorated `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)`, composing the Phase 3 pure helper.

The Phase-4 scope is deliberately a **subset of the full seven-variant production**. Without the base-image adapter chain (Phase 7) and `assemble_provenance` orchestration (Phase 7 S2-04), the adapter cannot honestly classify `BaseImage` or `RuntimeBundled` — there is no base-image evidence reader on the Phase-4 ingress. The right discipline is fail-closed: app-layer evidence produces `AppDirect`/`AppTransitive`/`AppVendored`; absent app-layer evidence collapses to `Unknown(reason="no_adapter_resolved")` per the `UnknownReason` taxonomy (`primitives/vuln_provenance/types.py:122`). The gate's `_APP_LAYER_PROVENANCE_KINDS` (`{"app_direct", "app_transitive", "app_vendored", "both"}`) refuses any non-app-layer result — `Unknown` is on the refuse side, so the Phase-4 cost protection holds.

This story is **additive**, not an edit. The adapter is a new file under the plugin directory. The Phase 3 pure helper is consumed via import only — never edited (Phase 7 ADR-0009 byte-edit-allowlist discipline). Phase 7 S3-02 will **widen** the same class to all seven variants when the base-image adapter and `assemble_provenance` chain land; both stories touch the file additively (the `Both` arm and the `BaseImage` arm are appended, the existing arms are byte-preserved).

**Upstream blockers (must clear before this story is Ready):**

1. **UB-1** — `plugins/vulnerability-remediation--node--npm/` plugin tree does not exist (only `plugins/__init__.py`, `plugins/PLUGINS.lock`, `plugins/PLUGINS.lock.README.md`). Phase 3 plugin scaffold must land first. Same blocker as Phase 7 S3-02 and S3-03.
2. **UB-2** — Phase 3 S7-05 not yet GREEN. The `is_app_layer_lookup` helper this story composes against does not yet exist as code.
3. **UB-3** — Phase 4 S2-01 not yet GREEN. Without `ProvenanceGate` + `ProvenanceClassifier`, the adapter has no consumer.
4. **UB-4** — Phase 7 S3-02 cross-coordination. If Phase 7 S3-02 ships first, S7-03 is a near-no-op (its adapter already satisfies Phase 4 needs). If S7-03 ships first, Phase 7 S3-02 widens it additively. Story execution order is a project decision; surface in the attempt log at execute time.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 6 — ProvenanceGate` — "Delegates to plugin's `NpmVulnProvenanceAdapter`."
  - `../phase-arch-design.md §Scenario 3` — sequence diagram of the refuse path.
  - `../phase-arch-design.md §Edge case #1` — `Unknown` / base-image case.
  - `../phase-arch-design.md §Goals — G7` — zero-LLM-token invariant on non-app-layer.
- **Phase 4 ADRs:**
  - `../ADRs/0012-provenance-gate-explicit-tier-zero.md` — tier-0 commitment; `_APP_LAYER_PROVENANCE_KINDS` seam; refuse-set semantics; `ProvenanceClassified` event ownership (gate, not adapter).
  - `../ADRs/0003-path-scoped-fence-amendment.md` — Phase-4 plugin code lives under `plugins/`, not `src/codegenie/`; the kernel-frozen fence protects `src/codegenie/{probes,coordinator,cache,output,schema,plugins/protocols.py}/`.
- **Phase 7 ADRs (governing the adapter shape):**
  - `../../07-migration-task-class/ADRs/0004-vuln-provenance-primitive-home.md` — primitive home; the adapter consumes `Provenance` from `codegenie.primitives.vuln_provenance`.
  - `../../07-migration-task-class/ADRs/0005-probes-live-under-plugin-not-core-tree.md` — the adapter file lives under the plugin directory, even though it consumes a `src/codegenie/primitives/` Protocol.
  - `../../07-migration-task-class/ADRs/0007-provenance-adapter-registry-stores-classes.md` — registry stores classes; construction at dispatch time via `AdapterFactory` with closed `{sbom_reader, logger, image_manifest_cache}` kwarg vocabulary.
  - `../../07-migration-task-class/ADRs/0009-phase-7-byte-edit-allowlist-fence.md` — this story creates a new plugin file (additive); no edits to existing Phase 3 files.
- **Production ADRs:**
  - `../../../production/adrs/0038-vulnerability-provenance-attribution.md` — the seven-variant `Provenance` primitive and refuse-mode semantics.
- **Source design:**
  - `../final-design.md §Component 6 — ProvenanceGate`.
- **High-level impl:**
  - `../High-level-impl.md §Step 7` — names this file (note: the High-level-impl text says `vuln_provenance.py`; the canonical file is `npm_provenance.py` per Phase 7 S3-02 layout — see Validation notes).
- **Sibling stories (precedents):**
  - `S2-01-provenance-gate-tier-zero.md` and its `_validation/` report — the precedent that resolved the same primitive/signature drift this story closes.
  - `../../07-migration-task-class/stories/S3-02-npm-vuln-provenance-adapter.md` — Phase 7's canonical adapter story (BLOCKED on same upstream); same Protocol, same decorator, same file path, widens this story's Phase-4 subset.
  - `../../03-vuln-deterministic-recipe/stories/S7-05-npm-app-layer-precheck.md` — Phase 3's pure-helper precursor this adapter composes against.
- **Existing code (read before writing):**
  - `src/codegenie/primitives/vuln_provenance/types.py` — `Provenance` discriminated union (lower-case `kind`); seven variant classes; `AdapterConfidence` `StrEnum`; `UnknownReason` `Literal` taxonomy.
  - `src/codegenie/primitives/vuln_provenance/protocols.py` — `VulnProvenanceAdapter` Protocol with `attribute(cve_id, package_id, image_ref, sbom) -> Provenance` + `confidence() -> AdapterConfidence`. Do not redefine.
  - `src/codegenie/primitives/vuln_provenance/errors.py` — `ProvenanceError` / `AdapterError`; the typed-exception path.
  - `src/codegenie/primitives/vuln_provenance/registry.py` — `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)` decorator; `_REGISTRY` dict.
  - `src/codegenie/primitives/vuln_provenance/syft_reader.py` — `SyftSbom` Pydantic model.
  - `src/codegenie/types/identifiers.py` — `CveId`, `PackageId`, `ImageRef`, `ImageDigest`, `LayerDigest` newtypes.
  - `tests/unit/fallback/test_provenance_gate.py` (after S2-01 lands) — fixture idioms for `AppDirect`/`AppTransitive`/`AppVendored`/`Unknown` construction.

## Goal

Land `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` containing `NpmVulnProvenanceAdapter` — a class implementing the shipped `VulnProvenanceAdapter` Protocol (`attribute(cve_id, package_id, image_ref, sbom) -> Provenance` + `confidence() -> AdapterConfidence`), decorated `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)`. The Phase-4 subset produces `AppDirect`, `AppTransitive`, `AppVendored`, and `Unknown(reason)` only; base-image / runtime-bundled / `Both` variants collapse to `Unknown(reason="no_adapter_resolved")` until Phase 7 S3-02 widens. Composes against (does not edit) Phase 3 S7-05's `is_app_layer_lookup` pure helper. After this story lands, `ProvenanceGate.classify(...)` (S2-01) wired with this adapter returns the rich sum type that lets Phase 4 emit `Refused(PROVENANCE_NOT_APP_LAYER)` deterministically for everything outside `_APP_LAYER_PROVENANCE_KINDS`.

## Acceptance criteria

> **Validator note.** Every AC below is pinned to the **shipped** Protocol (`attribute(...) + confidence()`), the **shipped** discriminator contract (lower-case `kind`), and the **shipped** primitive module (`codegenie.primitives.vuln_provenance`). PascalCase class names are used only in `isinstance(...)` checks and constructor calls; **all behavioral assertions go through `result.kind == "<lower_case_string>"`**.

- [ ] **AC-1 — File location and additive discipline.** `plugins/vulnerability-remediation--node--npm/adapters/__init__.py` and `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` exist as **new** files (additive per Phase 7 ADR-0009 — no edits to any existing file under `plugins/vulnerability-remediation--node--npm/`). The module docstring cites CLAUDE.md "Extension by addition" and Phase 7 ADR-0009. No edits to any file under `src/codegenie/`.

- [ ] **AC-2 — Class implements `VulnProvenanceAdapter` Protocol structurally.** `NpmVulnProvenanceAdapter` is a class. `isinstance(NpmVulnProvenanceAdapter(...), VulnProvenanceAdapter)` is `True` (the Protocol is `@runtime_checkable`; this asserts method names exist). A second test uses `inspect.signature(NpmVulnProvenanceAdapter.attribute)` to byte-pin the signature exactly to the Protocol's: `attribute(self, cve_id: CveId, package_id: PackageId, image_ref: ImageRef | None, sbom: SyftSbom) -> Provenance`. A third test confirms `confidence()` is callable and returns an `AdapterConfidence` member.

- [ ] **AC-3 — Registry decorator at class definition.** The class is decorated `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)` at definition. After importing the module, `_REGISTRY[(Layer.APP, Ecosystem.NPM)] is NpmVulnProvenanceAdapter` (class identity, not instance — per Phase 7 ADR-0007).

- [ ] **AC-4 — Constructor: closed DI kwargs vocabulary, no I/O.** The `__init__` signature is keyword-only with exactly the closed Phase 7 ADR-0007 vocabulary `{sbom_reader, logger, image_manifest_cache}`. No positional args. A test asserts `inspect.signature(NpmVulnProvenanceAdapter.__init__).parameters.keys() == {"self", "sbom_reader", "logger", "image_manifest_cache"}` and that every non-`self` parameter is `KEYWORD_ONLY`. A second test patches `pathlib.Path.read_text` to raise `RuntimeError("I/O at construction")` and instantiates the adapter — no exception (the constructor stores references only).

- [ ] **AC-5 — `attribute(...)` produces the Phase-4 subset; base-layer evidence collapses to `Unknown`.** For inputs where the Phase 3 `is_app_layer_lookup` helper resolves the package in the npm dep graph:
  - chain length == 1 → `AppDirect(manifest_path=..., package=package_id, confidence=AdapterConfidence.HIGH)`
  - chain length ≥ 2 → `AppTransitive(manifest_path=..., package=package_id, chain=(...), confidence=AdapterConfidence.HIGH)` with `chain[-1] == package_id` and `len(chain) >= 2`
  - vendored copy (under a `vendor/` directory; lockfile absent for the path) → `AppVendored(vendored_path=..., package=package_id, confidence=AdapterConfidence.DEGRADED)`
  - package absent from the dep graph entirely → `Unknown(reason="sbom_layer_attribution_absent", details={"package_id": str(package_id)})`
  - `image_ref is not None` AND lookup absent in app layer → `Unknown(reason="no_adapter_resolved", details={"image_ref": str(image_ref), "note": "phase4_subset"})` (the Phase-7 base-image adapter chain is required for honest `BaseImage`/`RuntimeBundled` classification; the Phase-4 subset cannot produce them).
  - **Never** returns `Both` or `BaseImage` or `RuntimeBundled` — those variants require Phase 7 widening. A property test asserts `result.kind not in {"both", "base_image", "runtime_bundled"}` for every input across the Hypothesis strategy.

- [ ] **AC-6 — Adapter errors raise `AdapterError`; the primitive folds.** Lockfile parse failure, malformed `package-lock.json`, missing required SBOM layer attribution → raise `AdapterError("<message>")`. The adapter does **not** catch its own `AdapterError` and convert to `Unknown` — that is `assemble_provenance`'s job (Phase 7 S2-04). A unit test feeds a deliberately-truncated lockfile and asserts `AdapterError` propagates from `attribute(...)`. Bare `except Exception` is forbidden — the only typed-exception path is `AdapterError`.

- [ ] **AC-7 — `confidence()` returns `HIGH` / `DEGRADED` / `UNAVAILABLE` per the documented conditions.** `HIGH` when the lockfile parsed cleanly **and** the queried package was resolved in the app layer; `DEGRADED` when the lockfile is fresh but the queried package is absent (vendored / not-in-app-layer case); `UNAVAILABLE` when no `package-lock.json` is reachable in the `RepoContext` slice at all. A table-driven test parametrizes one fixture per condition and asserts the returned `AdapterConfidence` member.

- [ ] **AC-8 — Pure helper composed, not re-implemented.** The lockfile walk is **not** re-derived inside `npm_provenance.py`. The adapter imports the pure helper Phase 3 S7-05 ships (`is_app_layer_lookup` or the symbol Phase 3 S7-05 exports — pinned at execute time from the landed Phase 3 code). The adapter's `attribute(...)` is the imperative shell: reads `RepoContext` slices via the injected `sbom_reader` / `image_manifest_cache`, calls the pure helper, and constructs the appropriate `Provenance` variant. A test imports the helper from the Phase 3 module path and asserts `npm_provenance.py` calls it (via `monkeypatch` of the imported symbol — the test asserts the call happens with the expected arguments).

- [ ] **AC-9 — Lower-case `kind` discriminator contract.** Every behavioral assertion uses `result.kind == "<lower_case>"`. The constants `"app_direct"`, `"app_transitive"`, `"app_vendored"`, `"unknown"` appear in tests; PascalCase class names appear only in constructor calls and `isinstance` checks. A constant-pin test asserts `tuple(result.kind for result in _phase4_subset_examples) == ("app_direct", "app_transitive", "app_vendored", "unknown", "unknown")`.

- [ ] **AC-10 — Multi-package CVE logical-OR; scoped-name normalization.** A CVE listing multiple affected packages produces `AppDirect`/`AppTransitive` if **any** of them is in the app layer (logical OR, not AND, not first-only). Matching normalizes both the CVE's affected package names and the resolved dep-graph keys to lowercase; scoped names (`@scope/name`) match by their full normalized form. A parametrized test covers `(single_present, single_absent, multi_one_present_one_absent, multi_all_absent, scoped_normalized)`.

- [ ] **AC-11 — Determinism across calls.** Calling `attribute(...)` twice with byte-identical inputs returns equal `Provenance` (Pydantic equality). For `AppTransitive`, the `chain` is stable across calls (no set/dict-iteration nondeterminism). A property test (Hypothesis or a deterministic fixture-replay) asserts equality across 100 paired calls.

- [ ] **AC-12 — `_WARNING_IDS` declared and validated at import time.** Module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset({"vuln_provenance.adapter_error", "vuln_provenance.no_adapter_resolved"})`. A runtime check at import time uses `raise AssertionError(...)` (**not** bare `assert` — forbidden by the `forbidden-patterns` hook) to verify each ID matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. A `tests/fence/` test confirms this module is registered.

- [ ] **AC-13 — Forbidden patterns absent.** No `subprocess.run`, `os.system`, `os.popen`, `shell=True`, `eval(`, `exec(`, `__import__(`, `pickle.loads`, `assert ` (bare), or `# type: ignore` (in production code; test-only mypy-negative snippets exempt) anywhere in `npm_provenance.py`. The existing `forbidden-patterns` pre-commit hook is the enforcement.

- [ ] **AC-14 — Strict typing.** `mypy --strict` is clean for `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` and the new tests. Public signatures contain no `Any`. The return annotation on `attribute(...)` is `Provenance` (the alias from `codegenie.primitives.vuln_provenance.types`), not `AppDirect | AppTransitive | …`.

- [ ] **AC-15 — Kernel frozen + plugin-path discipline.** `tests/fence/test_kernel_frozen.py` is green: zero edits to `src/codegenie/{probes,coordinator,cache,output,schema,plugins/protocols.py}/`, zero edits to `RemediationOrchestrator`, `Plugin` Protocol, `RecipeEngine` Protocol, `Transform` ABC, `VulnProvenanceAdapter` Protocol, `_REGISTRY`. `make lint-imports` is green: `plugins/.../adapters/npm_provenance.py` imports only from `codegenie.primitives.*`, `codegenie.types.*`, `codegenie.errors`, stdlib, and `plugins/vulnerability-remediation--node--npm/subgraph/*` (for the Phase 3 pure helper).

- [ ] **AC-16 — Full gate green.** `make check` clean: `ruff check`, `ruff format --check`, `mypy --strict`, the **whole `pytest -q` suite**. The TDD red tests below exist, are committed, and are green.

## Implementation outline

1. **Read first** (Global Rule 8): `src/codegenie/primitives/vuln_provenance/{types.py, protocols.py, errors.py, registry.py}` and the Phase 3 S7-05 pure helper module (path pinned from the landed Phase 3 code; the symbol name is whatever S7-05 exports — most likely `is_app_layer_lookup` under `plugins/vulnerability-remediation--node--npm/subgraph/verify_app_layer.py`).
2. Create `plugins/vulnerability-remediation--node--npm/adapters/__init__.py` (empty or re-export per the plugin's `recipes/__init__.py` convention).
3. Create `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py`:
   - `from __future__ import annotations`
   - imports: stdlib (`inspect`, `pathlib.Path`, `re`, `typing`); `codegenie.primitives.vuln_provenance.{types, protocols, errors, registry}` (variants, Protocol, errors, decorator); `codegenie.types.identifiers.{CveId, PackageId, ImageRef}`; `plugins.vulnerability_remediation_node_npm.subgraph.verify_app_layer` (the Phase 3 pure helper).
   - module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset({"vuln_provenance.adapter_error", "vuln_provenance.no_adapter_resolved"})` with `raise AssertionError(...)` regex validation at import time.
   - `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)` decorating `class NpmVulnProvenanceAdapter:`.
   - `__init__(self, *, sbom_reader: SyftSbomReader, logger: Logger, image_manifest_cache: ImageManifestCache) -> None:` — stores references; no I/O.
   - `def attribute(self, cve_id, package_id, image_ref, sbom) -> Provenance:` — calls the Phase 3 pure helper; dispatches by chain length / vendored / absent / image-ref-set to the appropriate variant; raises `AdapterError` only on parse failure / programming-bug-shaped input. **Never** returns `Both`, `BaseImage`, or `RuntimeBundled` (Phase-4 subset discipline).
   - `def confidence(self) -> AdapterConfidence:` — returns the per-call confidence band based on the most recent lookup state (or `UNAVAILABLE` if no lookup has been performed against a fresh lockfile).
4. Write tests at `tests/unit/plugins/vulnerability_remediation_node_npm/test_npm_provenance.py` first (TDD red). See plan below.
5. Add the AST/import fence at `tests/fence/test_npm_provenance_plugin_boundary.py` proving the adapter imports only from the allowed set.
6. Wire the adapter into `ProvenanceGate` via S2-01's `ProvenanceClassifier` facade — instantiate the adapter at the plugin's `transforms()` composition root (S7-01's territory; this story does **not** edit `FallbackTier` or the gate). Add `tests/integration/test_provenance_gate_with_npm_adapter.py` asserting end-to-end gate dispatch over four Phase-4-subset fixtures (`app_direct_express`, `app_transitive_lodash`, `app_vendored_left_pad`, `package_absent`).
7. Run `make check`; iterate until green.

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/unit/plugins/vulnerability_remediation_node_npm/test_npm_provenance.py
from __future__ import annotations

import inspect
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from hypothesis import given, strategies as st

from codegenie.primitives.vuln_provenance import (
    AdapterConfidence,
    AdapterError,
    AppDirect,
    AppTransitive,
    AppVendored,
    Provenance,
    SyftSbom,
    Unknown,
    VulnProvenanceAdapter,
)
from codegenie.primitives.vuln_provenance.registry import (
    Ecosystem,
    Layer,
    _REGISTRY,
)
from codegenie.types.identifiers import CveId, ImageRef, PackageId

from plugins.vulnerability_remediation_node_npm.adapters.npm_provenance import (
    NpmVulnProvenanceAdapter,
)


# ---------- DI fakes ----------

class FakeSbomReader:
    def __init__(self) -> None:
        self.calls: list[object] = []

class FakeLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []
    def info(self, msg: str, **_: object) -> None:
        self.messages.append(msg)

class FakeImageManifestCache:
    def __init__(self) -> None:
        self.lookups: list[ImageRef] = []


@pytest.fixture
def adapter() -> NpmVulnProvenanceAdapter:
    return NpmVulnProvenanceAdapter(
        sbom_reader=FakeSbomReader(),
        logger=FakeLogger(),
        image_manifest_cache=FakeImageManifestCache(),
    )


# ---------- Registry + Protocol-shape tests ----------

def test_registered_in_provenance_registry() -> None:
    assert _REGISTRY[(Layer.APP, Ecosystem.NPM)] is NpmVulnProvenanceAdapter


def test_runtime_checkable_protocol_conformance(adapter: NpmVulnProvenanceAdapter) -> None:
    assert isinstance(adapter, VulnProvenanceAdapter)


def test_attribute_signature_matches_protocol() -> None:
    sig = inspect.signature(NpmVulnProvenanceAdapter.attribute)
    params = list(sig.parameters)
    assert params == ["self", "cve_id", "package_id", "image_ref", "sbom"]
    # Return annotation pinned to the alias (string form under PEP 563)
    assert "Provenance" in str(sig.return_annotation)


def test_constructor_kwargs_are_closed_vocabulary() -> None:
    sig = inspect.signature(NpmVulnProvenanceAdapter.__init__)
    assert set(sig.parameters) == {"self", "sbom_reader", "logger", "image_manifest_cache"}
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        assert param.kind == inspect.Parameter.KEYWORD_ONLY


def test_no_io_at_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    def _explode(*_: object, **__: object) -> None:
        raise RuntimeError("I/O at construction")
    monkeypatch.setattr(Path, "read_text", _explode)
    NpmVulnProvenanceAdapter(
        sbom_reader=FakeSbomReader(),
        logger=FakeLogger(),
        image_manifest_cache=FakeImageManifestCache(),
    )  # no exception


# ---------- Variant production (Phase-4 subset) ----------

# Fixture builders elided — they construct CveId/PackageId/ImageRef/SyftSbom plus
# the npm dep graph slice the Phase 3 helper consumes. The implementer pins them
# at execute time against the landed Phase 3 S7-05 helper signature.

@pytest.mark.parametrize(
    "fixture_name,expected_kind,expected_class",
    [
        ("app_direct_express", "app_direct", AppDirect),
        ("app_transitive_lodash_through_express", "app_transitive", AppTransitive),
        ("app_vendored_old_left_pad", "app_vendored", AppVendored),
        ("absent_package", "unknown", Unknown),
    ],
)
def test_attribute_phase4_subset(
    adapter: NpmVulnProvenanceAdapter,
    request: pytest.FixtureRequest,
    fixture_name: str,
    expected_kind: str,
    expected_class: type[Provenance],
) -> None:
    cve_id, package_id, image_ref, sbom = request.getfixturevalue(fixture_name)
    result = adapter.attribute(
        cve_id=cve_id, package_id=package_id, image_ref=image_ref, sbom=sbom,
    )
    assert result.kind == expected_kind
    assert isinstance(result, expected_class)


def test_app_transitive_chain_invariants(adapter, app_transitive_lodash_through_express) -> None:
    cve_id, package_id, image_ref, sbom = app_transitive_lodash_through_express
    result = adapter.attribute(cve_id=cve_id, package_id=package_id, image_ref=image_ref, sbom=sbom)
    assert isinstance(result, AppTransitive)
    assert len(result.chain) >= 2
    assert result.chain[-1] == package_id


def test_absent_package_returns_unknown_sbom_attribution_absent(adapter, absent_package) -> None:
    cve_id, package_id, image_ref, sbom = absent_package
    result = adapter.attribute(cve_id=cve_id, package_id=package_id, image_ref=image_ref, sbom=sbom)
    assert isinstance(result, Unknown)
    assert result.reason == "sbom_layer_attribution_absent"
    assert result.details == {"package_id": str(package_id)}


def test_image_ref_present_but_app_absent_collapses_to_no_adapter_resolved(
    adapter, image_ref_present_app_absent,
) -> None:
    cve_id, package_id, image_ref, sbom = image_ref_present_app_absent
    result = adapter.attribute(cve_id=cve_id, package_id=package_id, image_ref=image_ref, sbom=sbom)
    assert isinstance(result, Unknown)
    assert result.reason == "no_adapter_resolved"


def test_never_returns_both_base_image_or_runtime_bundled(
    adapter, all_phase4_fixtures,
) -> None:
    forbidden_kinds = {"both", "base_image", "runtime_bundled"}
    for cve_id, package_id, image_ref, sbom in all_phase4_fixtures:
        result = adapter.attribute(cve_id=cve_id, package_id=package_id, image_ref=image_ref, sbom=sbom)
        assert result.kind not in forbidden_kinds


# ---------- Failure modes ----------

def test_malformed_lockfile_raises_adapter_error(adapter, malformed_lockfile_ctx) -> None:
    cve_id, package_id, image_ref, sbom = malformed_lockfile_ctx
    with pytest.raises(AdapterError):
        adapter.attribute(cve_id=cve_id, package_id=package_id, image_ref=image_ref, sbom=sbom)


# ---------- Determinism + idempotence ----------

@pytest.mark.parametrize("fixture_name", [
    "app_direct_express", "app_transitive_lodash_through_express",
    "app_vendored_old_left_pad", "absent_package",
])
def test_attribute_is_idempotent(adapter, request, fixture_name) -> None:
    cve_id, package_id, image_ref, sbom = request.getfixturevalue(fixture_name)
    r1 = adapter.attribute(cve_id=cve_id, package_id=package_id, image_ref=image_ref, sbom=sbom)
    r2 = adapter.attribute(cve_id=cve_id, package_id=package_id, image_ref=image_ref, sbom=sbom)
    assert r1 == r2


# ---------- Multi-package logical-OR + scoped-name normalisation ----------

@pytest.mark.parametrize("fixture_name,expected_kind", [
    ("multi_pkg_one_present_one_absent", "app_direct"),
    ("multi_pkg_all_absent", "unknown"),
    ("scoped_name_present_uppercased", "app_direct"),
])
def test_multi_package_and_scoped_name(adapter, request, fixture_name, expected_kind) -> None:
    cve_id, package_id, image_ref, sbom = request.getfixturevalue(fixture_name)
    result = adapter.attribute(cve_id=cve_id, package_id=package_id, image_ref=image_ref, sbom=sbom)
    assert result.kind == expected_kind


# ---------- confidence() ----------

@pytest.mark.parametrize("fixture_name,expected_confidence", [
    ("clean_lockfile_resolved", AdapterConfidence.HIGH),
    ("clean_lockfile_package_absent", AdapterConfidence.DEGRADED),
    ("no_lockfile_reachable", AdapterConfidence.UNAVAILABLE),
])
def test_confidence_band(adapter, request, fixture_name, expected_confidence) -> None:
    cve_id, package_id, image_ref, sbom = request.getfixturevalue(fixture_name)
    adapter.attribute(cve_id=cve_id, package_id=package_id, image_ref=image_ref, sbom=sbom)
    assert adapter.confidence() == expected_confidence


# ---------- Composition with the Phase 3 pure helper ----------

def test_adapter_composes_phase3_pure_helper(adapter, app_direct_express, monkeypatch) -> None:
    """The adapter MUST call the Phase 3 helper; it does not re-derive the walk."""
    from plugins.vulnerability_remediation_node_npm.subgraph import verify_app_layer
    calls: list[object] = []
    real = verify_app_layer.is_app_layer_lookup
    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real(*args, **kwargs)
    monkeypatch.setattr(verify_app_layer, "is_app_layer_lookup", spy)
    cve_id, package_id, image_ref, sbom = app_direct_express
    adapter.attribute(cve_id=cve_id, package_id=package_id, image_ref=image_ref, sbom=sbom)
    assert len(calls) == 1  # exactly one delegation per attribute call


# ---------- Hypothesis: closed-union guarantee + monotonicity ----------

@given(st.data())
def test_attribute_always_returns_phase4_subset_variant(adapter, data) -> None:
    """Every input → one of the four Phase-4-subset variants. No None, no leak."""
    fixture = data.draw(_phase4_input_strategy())
    cve_id, package_id, image_ref, sbom = fixture
    result = adapter.attribute(cve_id=cve_id, package_id=package_id, image_ref=image_ref, sbom=sbom)
    assert result.kind in {"app_direct", "app_transitive", "app_vendored", "unknown"}


@given(st.data())
def test_monotonicity_adding_app_layer_evidence_flips_unknown_to_present(adapter, data) -> None:
    """Adding evidence that the package IS in the app layer must flip
    Unknown→{AppDirect,AppTransitive,AppVendored}, never the reverse."""
    base_fixture = data.draw(_absent_fixture_strategy())
    cve_id, package_id, image_ref, sbom_absent = base_fixture
    result_absent = adapter.attribute(cve_id=cve_id, package_id=package_id, image_ref=image_ref, sbom=sbom_absent)
    assert result_absent.kind == "unknown"

    sbom_present = _add_app_layer_evidence(sbom_absent, package_id)
    result_present = adapter.attribute(cve_id=cve_id, package_id=package_id, image_ref=image_ref, sbom=sbom_present)
    assert result_present.kind in {"app_direct", "app_transitive", "app_vendored"}


# ---------- _WARNING_IDS regex pin ----------

def test_warning_ids_match_canonical_regex() -> None:
    import re
    from plugins.vulnerability_remediation_node_npm.adapters import npm_provenance
    pat = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    for wid in npm_provenance._WARNING_IDS:
        assert pat.match(wid), f"warning id violates canonical shape: {wid}"
```

Plus the AST import-fence at `tests/fence/test_npm_provenance_plugin_boundary.py`:

```python
def test_npm_provenance_imports_only_allowed_modules() -> None:
    import ast
    from pathlib import Path
    tree = ast.parse(Path(
        "plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py"
    ).read_text())
    allowed_prefixes = (
        "codegenie.primitives.vuln_provenance",
        "codegenie.types.identifiers",
        "codegenie.errors",
        "plugins.vulnerability_remediation_node_npm.subgraph",
        # stdlib — checked via stdlib-module list, not by prefix
    )
    import sys
    stdlib = set(sys.stdlib_module_names)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            top = node.module.split(".")[0]
            assert (
                node.module.startswith(allowed_prefixes) or top in stdlib
            ), f"forbidden import: {node.module}"
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert (
                    alias.name.startswith(allowed_prefixes) or top in stdlib
                ), f"forbidden import: {alias.name}"
```

Run; expect `ModuleNotFoundError: plugins.vulnerability_remediation_node_npm.adapters.npm_provenance` (the file does not yet exist) for the unit tests, and a clean fail on the import-fence test.

### Green — make it pass

Implement `npm_provenance.py` per the outline. Keep `attribute(...)` thin: delegate the walk to the Phase 3 pure helper; map (chain length, vendored-ness, absence, image-ref-set) to the four Phase-4-subset variants. Raise `AdapterError` on parse failure only — never catch it.

### Refactor — clean up

- Extract any inline branch chains into named private helpers named after the **evidence** they consume, not the variant they produce (`_chain_from_lockfile`, `_vendored_path_or_none`, `_normalize_pkg_name`).
- Keep the constructor strictly DI; no env reads, no global config lookups.
- Strict `__all__` at module top.
- Re-run S2-01's `tests/unit/fallback/test_provenance_gate.py` (after S2-01 is GREEN) to confirm the gate's seven-variant coverage is preserved when the gate is wired with this adapter as its `ProvenanceClassifier`. Re-run `tests/fence/test_kernel_frozen.py` (S1-07) — must stay green.
- Add a one-line module docstring naming the Phase-7 widening seam: "S3-02 (Phase 7) widens this adapter to produce `BaseImage`/`RuntimeBundled`/`Both` once the base-image adapter chain lands; the existing arms are byte-preserved."

## Files to touch

| Path | Why |
|---|---|
| `plugins/vulnerability-remediation--node--npm/adapters/__init__.py` | New file (additive). Empty or per-plugin re-export convention. |
| `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` | New file (additive). The `NpmVulnProvenanceAdapter` class — Phase-4-subset variant production, `@register_provenance_adapter` decoration, DI kwargs `{sbom_reader, logger, image_manifest_cache}`, composes Phase 3 S7-05's pure helper. |
| `tests/unit/plugins/vulnerability_remediation_node_npm/__init__.py` | New (if absent). |
| `tests/unit/plugins/vulnerability_remediation_node_npm/test_npm_provenance.py` | TDD red tests: registry, Protocol conformance, signature pin, no-I/O-at-construction, Phase-4-subset variant table, chain invariants, absent-package, image-ref-set-collapse, never-Both/BaseImage/RuntimeBundled, malformed-lockfile-AdapterError, idempotence, multi-package logical-OR, scoped-name normalisation, `confidence()` band table, composition with Phase 3 helper, Hypothesis closed-union + monotonicity, `_WARNING_IDS` regex. |
| `tests/unit/plugins/vulnerability_remediation_node_npm/conftest.py` | Per-variant fixtures over real `CveId`/`PackageId`/`ImageRef`/`SyftSbom` instances. |
| `tests/fixtures/provenance/` | Minimal manifest + lockfile mini-repos, one per Phase-4-subset fixture. |
| `tests/fence/test_npm_provenance_plugin_boundary.py` | AST import-fence proving the adapter imports only from the allowed set. |
| `tests/integration/test_provenance_gate_with_npm_adapter.py` | End-to-end gate dispatch over four Phase-4-subset fixtures, wiring the adapter as `ProvenanceGate`'s `ProvenanceClassifier` (via the plugin's `transforms()` composition root). |

## Out of scope

- `BaseImage` / `RuntimeBundled` / `Both` variant production — requires the Phase 7 base-image adapter chain + `assemble_provenance` orchestration (Phase 7 S2-04 / S3-02 / S4-02 / S4-03). The Phase-4 subset collapses these to `Unknown(reason="no_adapter_resolved")`.
- Widening from the Phase-4 subset to the full seven-variant adapter — owned by Phase 7 S3-02 (additive to this file).
- `is_app_layer(...)` predicate at the adapter level — S2-01 owns `is_app_layer(provenance: Provenance) -> bool` over `Provenance` already. Adapter callers (the gate) use that predicate; the adapter itself does not expose one.
- `ProvenanceClassified` event emission — owned by `ProvenanceGate` (S2-01). The adapter is silent on events.
- `FallbackTier.run` wiring — owned by S6-01 / S7-01 (composition root that instantiates the adapter + gate + classifier facade).
- Phase 3 S7-05's pure helper itself — consumed via import only; this story does not edit any Phase 3 file.
- The E2E event-absence test (`tests/integration/test_phase4_provenance_short_circuits.py`) — owned by S7-06.

## Notes for the implementer

- **Additive, not surgical.** This is a **new file** under the plugin tree. CLAUDE.md's load-bearing commitment is "Extension by addition — no silent edits." Global Rule 3 (Surgical Changes) governs edits to existing code; it does not apply here. The Phase 3 pure helper is **consumed via import only** — `from plugins.vulnerability_remediation_node_npm.subgraph.verify_app_layer import is_app_layer_lookup` — never edited.

- **Phase-4 subset, Phase-7 widens.** The adapter produces only `AppDirect`, `AppTransitive`, `AppVendored`, and `Unknown`. Phase 7 S3-02 widens the same class to produce `BaseImage` / `RuntimeBundled` / `Both` additively (appending arms to whatever dispatch pattern this story lands; the existing arms must be byte-preserved by Phase 7 S3-02). Surface the seam in the module docstring.

- **Lower-case `kind` discriminator contract.** Class names are PascalCase (`AppDirect`); discriminator values are lower-case (`"app_direct"`). Tests assert behavior via `result.kind == "<lower_case>"`. S2-01 already pinned this in its validation; do not re-introduce PascalCase strings.

- **Fail-loud `AdapterError` discipline.** Parse failures, malformed lockfiles, programming-bug-shaped inputs → `raise AdapterError(...)`. The adapter does **not** catch its own `AdapterError` and fold to `Unknown(reason="adapter_error")` — that is `assemble_provenance`'s job (Phase 7 S2-04). Bare `except Exception` is forbidden. Unrelated exceptions (e.g., `TypeError` from a misuse) must propagate (Global Rule 12 fail-loud).

- **DI factory vocabulary is closed.** `{sbom_reader, logger, image_manifest_cache}` are the only constructor kwargs. Phase 7 ADR-0007 pins this. Adding a kwarg requires a Phase 7 ADR-0007 amendment.

- **Composition over reimplementation.** The adapter's `attribute(...)` calls the Phase 3 pure helper; it does **not** re-derive the lockfile walk. Even if the Phase 3 helper's signature is awkward, the adapter adapts (Adapter pattern); editing Phase 3 code consumes a Phase 7 ADR-0009 allowlist row this story does not own.

- **Pure helper vs imperative shell.** `attribute(...)` is the only impure method on the public surface (it reads `RepoContext` slices via the injected `sbom_reader` / `image_manifest_cache`). Any inline classification logic must factor through module-private pure helpers named for the evidence they consume.

- **No `is_app_layer` wrapper at the adapter level.** S2-01 already shipped `is_app_layer(provenance: Provenance) -> bool` over lower-case `_APP_LAYER_PROVENANCE_KINDS`. The gate is the consumer; the adapter is silent on the predicate. (The original draft of this story proposed a same-named wrapper with a different signature — that would be a code smell.)

- **Newtype identifiers everywhere.** All inputs (`CveId`, `PackageId`, `ImageRef`) and internal walking primitives (`ImageDigest`, `LayerDigest`, `RuntimeId`, `DockerStageName`) are newtypes from `codegenie.types.identifiers`. Raw `str` is forbidden at the API boundary. `mypy --strict` is the gate.

- **Upstream blockers acknowledged.** UB-1 (plugin tree), UB-2 (Phase 3 helper), UB-3 (S2-01 GREEN), UB-4 (Phase 7 S3-02 sequencing) must all be considered before execution. The executor should open the attempt log with the four blockers' status, and if any is still BLOCKED, surface a `BLOCKED-PARTIAL` rather than inventing a workaround (Global Rule 12).
