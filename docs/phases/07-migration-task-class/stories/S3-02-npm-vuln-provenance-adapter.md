# Story S3-02 — `NpmVulnProvenanceAdapter` body + DI kwargs

**Step:** Step 3 — `NpmVulnProvenanceAdapter` in Phase 3 plugin as additive new file (first byte-edit territory)
**Status:** BLOCKED (2026-05-20; see [`_attempts/S3-02-npm-vuln-provenance-adapter.md`](_attempts/S3-02-npm-vuln-provenance-adapter.md); story hardened by validator 2026-08-14, blockers preserved)
**Validator status:** HARDENED (2026-08-14) — see [`_validation/S3-02-npm-vuln-provenance-adapter.md`](_validation/S3-02-npm-vuln-provenance-adapter.md). Goal preserved; Context / ACs / Implementation outline / TDD plan rewritten against the **landed** Protocol shape (SBOM-walk, not lockfile-walk).

> **BLOCKED — do not execute until resolved.** Two structural upstream
> blockers remain from the 2026-05-20 attempt:
>
> - **Blocker B (bench cassette absent).** `bench/vuln-remediation/` does
>   not exist; the byte-equal cost-ledger regression assertion is
>   unverifiable.
> - **Blocker F (S3-01 integration-fixture defect).** Both positive-path
>   tests in `tests/integration/test_provenance_assembly_via_plugins.py`
>   query `PackageId("lodash")` and expect contradictory `AppDirect` /
>   `AppTransitive` outcomes; the fixture `_fixtures/syft_sboms/npm_lodash_app.json`
>   ships `lodash` and `express` as two peer top-level
>   `node_modules/*/package.json` entries, so no deterministic adapter can
>   satisfy both. Fix must land BEFORE S3-02 executes (restructure the
>   fixture to `express` direct at `node_modules/express/package.json` +
>   `lodash` transitive at `node_modules/express/node_modules/lodash/package.json`;
>   repoint the transitive test at `lodash`; the direct test at `express`).
>
> Blocker A (Phase 3 plugin directory) has partially resolved: the plugin
> directory now exists under `plugins/vulnerability-remediation--node--npm/`
> with `plugin.yaml`, `api.py`, `config.py`, and a stub `adapters/__init__.py`.
> The `adapters/` package predates this story (contains `ts_typecheck_signal.py`
> from Phase 4 S6-05); the story's original AC-1 ("create `__init__.py`")
> is stale — the validator dropped it. Blockers C–E (Protocol / variant /
> confidence / error shape divergence) resolved by rewriting the story
> against the landed contract (see Validation notes below). Blocker G (AC-12
> vs Out-of-scope) resolved by demoting AC-12 to an in-plugin unit contract
> and moving the `xfail`-removal to S3-03's scope.
**Effort:** M

## Validation notes (2026-08-14)

The validator rewrote every section below the header that referenced the
non-landed lockfile-walk contract. **The Goal (land an `NpmVulnProvenanceAdapter`
returning typed `AppDirect | AppTransitive | Unknown(reason)` variants) is
preserved.** The evidence source, DI vocabulary, variant field names, error
class shape, and `AdapterConfidence` type all changed to match the code
actually shipped by S1-02..S1-04 and S2-01..S2-04.

**Contract deltas against the pre-validator story:**

| Aspect | Pre-validator story assumed | Landed code (source of truth) |
|---|---|---|
| `attribute()` signature | keyword-only `(*, cve_id, package_id, image_ref, sbom, repo_context)` | positional `(self, cve_id, package_id, image_ref: ImageRef \| None, sbom)` — no `*`, no `repo_context` — `src/codegenie/primitives/vuln_provenance/protocols.py:74` |
| Evidence source | `package.json` + `package-lock.json` from `RepoContext` | **SBOM only** — `SyftArtifact.locations[].path` `node_modules/` nesting classifies direct vs transitive |
| `AppDirect` fields | `(package_id, version, locked_version, location)` | `(kind, manifest_path, package, confidence)` — `types.py:190` |
| `AppTransitive` fields | `(package_id, version, locked_version, location, chain=[...])` | `(kind, manifest_path, package, chain: min_length=2, confidence)` — `types.py:203`; `chain` length 1 collapses to `AppDirect` |
| `AdapterConfidence` | Payload sum type `.High` / `.Degraded(reason=...)` / `.Unavailable(reason=...)` | Flat `StrEnum` — `HIGH / DEGRADED / UNAVAILABLE`, no payload — `types.py:100` |
| `AdapterError` construction | `AdapterError("vuln_provenance.adapter_error", details={"error": str(e)})` | Plain marker exception `AdapterError(str(e))` — no `details=` kwarg — `errors.py:92` |
| DI kwarg types | Concrete `SyftSbomReader` / `Logger` / `ImageManifestCache` | Closed vocabulary `{sbom_reader, logger, image_manifest_cache}` typed `object \| None` — `factory.py:54`, `factory.py:88` |
| `verifier: SbomVerifier \| None` DI | Prescribed defensive-degradation kwarg | **Out of contract** — `_DI_KWARGS` is closed at three names; adding a fourth requires an ADR-0007 amendment. Cross-verification deferred to a future post-S4-01 wiring story. |
| Adapters `__init__.py` | Story AC-1 said "create new file" | File already exists (`ts_typecheck_signal.py` sibling) — AC removed |
| ADR-0009 row #1 | Story claimed 2 new files (`__init__.py` + `npm_provenance.py`) | ADR-0009 row #1 is `npm_provenance.py` **only**; a second file would be a fence violation |

**Byte-edit allowlist status — sister-contradiction inherited from S3-03.**
The S3-03 validation surfaced that ADR-0009 (canonical) and
High-level-impl.md §Step 5 disagree on the 10-row list — `api.py` appears in
one but not the other; `pyproject.toml` appears in the other but not the
first. S3-02 itself creates only allowlist row #1 (`npm_provenance.py`), so
this story is not blocked on the contradiction, but the executor should
NOT presume `api.py` is allowlisted when landing the eventual S3-03 wiring.

**Design-pattern posture (per validator, preserved through Notes-for-implementer):**
The classifier is a single regex + one pure function (~40 LOC total); no
marker catalog and no sibling `_classify_sbom_locations.py` extraction
until Yarn PnP / pnpm virtual store layouts land (rule-of-three deferral).
No `AbstractVulnProvenanceAdapter` base class — the Protocol IS the seam,
and S4-02 / S4-03 read entirely disjoint evidence, so no shared classifier
exists to lift.


**Depends on (HARD):** S3-01 (contract test exists — this story does NOT flip its `xfail` markers; that is S3-03's job — but the fixture defect at `_fixtures/syft_sboms/npm_lodash_app.json` MUST be resolved before S3-02 executes, see Blocker F); S2-01 (`@register_provenance_adapter` decorator + `Layer` / `Ecosystem` enums — landed at `src/codegenie/primitives/vuln_provenance/registry.py`); S2-02 (`AdapterFactory` Protocol with the CLOSED `_DI_KWARGS = {sbom_reader, logger, image_manifest_cache}` typed `object | None` — landed at `factory.py:54`); S2-04 (`assemble_provenance(cve_id, package_id, image_ref, sbom, ...)` positional dispatch — landed at `assembly.py:167`); S1-03 (seven-variant `Provenance` union — `AppDirect`, `AppTransitive`, `Unknown` constructable — landed at `types.py`); S1-04 (`VulnProvenanceAdapter` Protocol, positional `attribute()` signature — landed at `protocols.py:74-80`); S1-05 (`SyftSbom` / `SyftArtifact` / `SyftLocation` Pydantic models with `extra="allow"` — landed at `syft_reader.py`). **S3-02 depends on the LANDED shape of each — the story text above pins every landed callsite by file:line to prevent future drift.**
**ADRs honored:** [ADR-0007](../ADRs/0007-provenance-adapter-registry-stores-classes.md) (the decorator registers the **class**, not an instance; construction happens at dispatch time via `AdapterFactory`); [ADR-0004](../ADRs/0004-vuln-provenance-primitive-home.md) (the adapter consumes the primitive's `attribute(...) -> Provenance` Protocol; returns one of seven variants); [ADR-0005](../ADRs/0005-probes-live-under-plugin-not-core-tree.md) (adapter lives under the plugin directory, NOT under `src/codegenie/` — even though it consumes a `src/codegenie/primitives/` Protocol); [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — **this story creates `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py`, which is Phase 7 byte-edit allowlist row #1 (an entire new file under an existing Phase 3 plugin directory; the directory is not itself a Phase 3 file, but the plugin tree as a whole is Phase 0–6.5 surface — see ADR-0009 row 1 verbatim)**

## Context

S3-01 wrote the integration test red-first; this story turns its three positive-path scenarios green by landing the actual adapter body. The adapter is small in line count but load-bearing: it is the **first concrete implementation** of the `VulnProvenanceAdapter` Protocol, the first thing the registry resolves to a real class, and the first byte-edit territory Phase 7 enters (consuming allowlist row #1 per Phase 7 ADR-0009 enumeration).

**Evidence source (landed contract).** `assemble_provenance` (`src/codegenie/primitives/vuln_provenance/assembly.py:167`) dispatches positionally: `factory(cls).attribute(cve_id, package_id, image_ref, sbom)`. The adapter receives ONLY the `SyftSbom` — no `RepoContext`, no live filesystem access. The classification signal is `SyftArtifact.locations[].path` `node_modules/` nesting:

- `node_modules/{pkg}/package.json` (top-level) → `pkg` is a **direct** dep.
- `node_modules/{parent}/node_modules/{pkg}/package.json` (nested once) → `pkg` is **transitive** via `parent`; chain = `(parent, pkg)`.
- `node_modules/a/node_modules/b/node_modules/pkg/package.json` (deep) → chain = `(a, b, pkg)`.
- Scoped packages ride under one segment: `node_modules/@types/lodash/package.json` → the `@types/lodash` slug is one hop (NOT two).

The adapter walks `sbom.artifacts` looking for the queried `package_id`; for the *first* matching artifact (npm hoisting rule: direct beats transitive — pin as an invariant, see AC-DP), it classifies the artifact's `locations[0].path` and returns one of the seven `Provenance` variants:

| Outcome | Condition | Returned variant (landed shape) |
|---|---|---|
| `AppDirect(kind, manifest_path, package, confidence)` | Chain length 1 (top-level `node_modules/{pkg}/package.json`) | `manifest_path = Path("node_modules") / pkg / "package.json"`; `confidence = AdapterConfidence.HIGH` |
| `AppTransitive(kind, manifest_path, package, chain, confidence)` | Chain length ≥ 2 (min_length pinned by Pydantic `Field(min_length=2)`) | `chain: tuple[PackageId, ...]` walked from outermost hop to queried pkg (inclusive); `confidence = AdapterConfidence.HIGH` |
| `Unknown(reason="sbom_layer_attribution_absent", details={"package_id": str(package_id)})` | `sbom.artifacts` contains NO artifact matching `package_id`, OR the matching artifact has zero `locations`, OR none of its `locations[].path` values are under `node_modules/…/package.json` | Defensive default — better to honestly say "I don't see this in the SBOM" than guess |
| **Raises `AdapterError(str(e))`** | `SyftArtifact` shape violates the `node_modules/` grammar in a way the classifier can't fold to `Unknown` (e.g., a malformed path this adapter cannot parse safely) | Rule 12 fail-loud at the adapter boundary; `assemble_provenance` catches `ProvenanceError` (parent of `AdapterError`) and converts to `Unknown(reason="adapter_error")`. **The adapter NEVER returns `Unknown(reason="adapter_error")` directly.** |

**Not from `RepoContext`.** The story previously described walking `package-lock.json` from `RepoContext`. The landed Protocol does not pass `RepoContext`. Any implementation that reaches for a live `package-lock.json` (via `sbom_reader` I/O or otherwise) is out-of-contract and will be caught by AC-NoIO (patch `Path.read_text` / `builtins.open` to raise; call `attribute()`; assert no raise).

**DI kwargs (landed vocabulary).** `factory.py:54` pins `_DI_KWARGS: Final[frozenset[str]] = frozenset({"sbom_reader", "logger", "image_manifest_cache"})`, each typed `object | None` (`factory.py:88-98`). An adapter's `__init__` MAY declare any subset of these three names; the factory passes only names in the intersection of `_DI_KWARGS` and the adapter's declared parameters. The npm adapter genuinely needs none of them (the SBOM arrives as a call argument; no cache lookup; logging is optional). Constructor SHOULD declare `logger: object | None = None` for observability (structural — the factory passes `None` from `default_adapter_factory`), and MAY omit `sbom_reader` and `image_manifest_cache` entirely — the factory is a pure pass-through and does not require the adapter to declare a full kwarg set.

**Functional core / imperative shell.** The adapter has no I/O at construction and no I/O inside `attribute()`. The only impure surface is `attribute()`'s exception raising; the classifier is a pure module-private function `_classify_sbom_locations(paths: Sequence[str], target: PackageId) -> tuple[PackageId, ...] | None` (returns `None` when no `node_modules/` path matches, else the resolution chain including the target as the last element).

**Warning IDs (Phase 0/1 convention).** The adapter's `_WARNING_IDS: Final[frozenset[str]]` module-level constant enumerates every warning ID this module may emit. Validated at import time via `if not <cond>: raise AssertionError("…")` — **bare `assert` is forbidden by the `forbidden-patterns` pre-commit hook**. Under the SBOM-walk contract, the ID set is:

```python
_WARNING_IDS: Final[frozenset[str]] = frozenset({
    "vuln_provenance.adapter_error",                # generic marker — raised via AdapterError
    "vuln_provenance.sbom_missing_locations",       # matched artifact had no locations
    "vuln_provenance.node_modules_path_malformed",  # classifier rejected the path shape
})
```

Each ID matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` (Phase 1 ADR-0007 regex). A fence under `tests/fence/` extends the existing `_WARNING_IDS` validator registry.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design §7a NpmVulnProvenanceAdapter"` (lines ~742–750) — the canonical spec verbatim.
  - `../phase-arch-design.md §"Component design §1 VulnProvenancePrimitive"` (lines ~520–610) — the `Provenance` union surface the adapter must return.
  - `../phase-arch-design.md §"Scenario A — App-only CVE"` (sequence diagram) — the `attribute(...)` call site.
  - `../phase-arch-design.md §"Decision points"` row for `Unknown` reasons — `sbom_layer_attribution_absent` is the canonical "I don't see this in the SBOM" reason.
  - `../phase-arch-design.md §"Failure behavior"` row in §7a — lockfile parse error → `AdapterError` → assembly converts to `Unknown(reason="adapter_error")`.
- **Phase 7 ADRs:**
  - [ADR-0004](../ADRs/0004-vuln-provenance-primitive-home.md) — `Provenance` union home + variants.
  - [ADR-0005](../ADRs/0005-probes-live-under-plugin-not-core-tree.md) — adapter under plugin, not under `src/codegenie/`.
  - [ADR-0007](../ADRs/0007-provenance-adapter-registry-stores-classes.md) — registry stores classes; construction via `AdapterFactory` at dispatch time.
  - [ADR-0009](../ADRs/0009-phase-7-byte-edit-allowlist-fence.md) — this story creates an allowlisted file (row #1).
- **High-level impl:** `../High-level-impl.md §"Step 3 — Features delivered"` (lines 96–101) — the bullet-by-bullet spec. **The implementer should read it verbatim**.
- **Phase 3 reference (read-only):**
  - `plugins/vulnerability-remediation--node--npm/recipes/` — existing recipe code that walks `package-lock.json`. **Do not import from this directory**; the adapter must re-derive its own lockfile walk. The reference is for understanding the lockfile shape only.
  - `docs/phases/03-vuln-deterministic-recipe/ADRs/0033-newtype-identifiers.md` (if it exists) — Phase 3's newtype discipline; Phase 7 ADR-0004 extends.
- **Existing primitive surface (consumed):**
  - `src/codegenie/primitives/vuln_provenance/protocols.py` — `VulnProvenanceAdapter`, `AdapterFactory`.
  - `src/codegenie/primitives/vuln_provenance/types.py` — `AppDirect`, `AppTransitive`, `Unknown`.
  - `src/codegenie/primitives/vuln_provenance/registry.py` — `register_provenance_adapter`, `Layer`, `Ecosystem`.
  - `src/codegenie/primitives/vuln_provenance/errors.py` — `AdapterError`.
  - `src/codegenie/types/identifiers.py` — `CveId`, `PackageId`, `ImageRef`.
- **Forbidden-patterns / convention:**
  - `CLAUDE.md §"Conventions"` — `_WARNING_IDS: Final[frozenset[str]]` + `raise AssertionError(...)` validation (NOT bare `assert`).
  - `CLAUDE.md §"Functional core / imperative shell"` — no I/O at construction; pure helpers carry the logic.

## Goal

Land `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` containing `NpmVulnProvenanceAdapter` — a class satisfying the landed `VulnProvenanceAdapter` Protocol shape (`src/codegenie/primitives/vuln_provenance/protocols.py`), decorated `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)`, classifying direct vs transitive from `SyftArtifact.locations[].path` `node_modules/` nesting, returning typed `AppDirect | AppTransitive | Unknown(reason="sbom_layer_attribution_absent")` variants (and raising `AdapterError` for genuinely malformed SBOM shapes). After this story lands, the adapter is instantiable, registers on module import, and — with a stub `AdapterFactory` in unit tests — deterministically returns the correct variant for the SBOM-fixture inputs pinned in AC-Direct / AC-Transitive / AC-Absent.

**`xfail`-removal is NOT this story's job.** S3-01's integration-test `xfail(strict=True)` markers get removed by **S3-03** (the story that adds the `api.py` import line that fires the decorator via the canonical `load_plugins(...)` loader). S3-02 alone cannot flip the integration tests green because `_REGISTRY` is populated only when `api.py` runs. S3-02's unit tests exercise the adapter class directly (importing the module or invoking the class through the primitive's `_REGISTRY` fixture after triggering the decorator via a controlled import). This scope split matches S3-03's Validation-notes framing.

**S3-01 fixture defect (Blocker F) MUST be resolved before this story executes.** The current fixture ships `lodash` and `express` as peer top-level dependencies; a correct adapter cannot satisfy both "`lodash` is direct" and "`lodash` is transitive via `express`" simultaneously. The pre-execution fix (surfaced to the operator, not silently applied): restructure `tests/integration/_fixtures/syft_sboms/npm_lodash_app.json` so `express` is at `node_modules/express/package.json` (direct) and `lodash` is at `node_modules/express/node_modules/lodash/package.json` (transitive); repoint `test_npm_adapter_returns_app_direct_for_root_dependency` at `express`; leave the transitive test at `lodash`. This is a fixture-correctness fix per S3-01's own attempt log, NOT a widening to accommodate a wrong implementation.

## Acceptance criteria

**Files created (byte-edit allowlist scope).**
- [ ] **AC-File:** `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` exists as a new file. **This IS the sole byte-edit allowlist row #1 per Phase 7 ADR-0009.** The `adapters/__init__.py` file already exists (Phase 4 sibling `ts_typecheck_signal.py` predates this story) — this story does NOT touch it, so no fence violation.

**Registration contract.**
- [ ] **AC-Register-Class:** `NpmVulnProvenanceAdapter` is a class (not an instance) decorated `@register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)` at class definition. After the module is imported, `_REGISTRY[(Layer.APP, Ecosystem.NPM)] is NpmVulnProvenanceAdapter` (class identity, ADR-0007 §Decision — closes BP-3). The unit test uses the `provenance_registry_reset` autouse fixture (mirrors `tests/unit/primitives/vuln_provenance/test_assembly.py`) to isolate registry state.
- [ ] **AC-Runtime-Check:** `isinstance(NpmVulnProvenanceAdapter(), VulnProvenanceAdapter)` returns `True` (verifies method-name conformance under the `@runtime_checkable` Protocol — `mypy --strict` is the signature gate).

**Constructor / DI contract.**
- [ ] **AC-Init-Positional:** Constructor signature declares parameters that are a subset of `_DI_KWARGS = {"sbom_reader", "logger", "image_manifest_cache"}` (per `src/codegenie/primitives/vuln_provenance/factory.py:54`), each typed `object | None` with a `None` default. The npm adapter's landed shape is:
  ```python
  def __init__(self, *, logger: object | None = None) -> None: ...
  ```
  (declaring only `logger`; `sbom_reader` and `image_manifest_cache` are omitted because the adapter genuinely does not need them — the factory's introspection-based dispatch permits partial DI declarations). A unit test asserts `inspect.signature(NpmVulnProvenanceAdapter.__init__).parameters` contains only names in the `_DI_KWARGS ∪ {"self"}` set — no `RepoContext`, no `SyftSbomReader` typed reader, no positional args after `self`.
- [ ] **AC-NoIO-Init:** Constructor does NO I/O. A unit test monkeypatches `pathlib.Path.read_text`, `pathlib.Path.open`, and `builtins.open` to raise `RuntimeError("I/O at construction")`, instantiates `NpmVulnProvenanceAdapter()`, asserts no exception raised.
- [ ] **AC-NoIO-Attribute:** `attribute(...)` does NO filesystem I/O either. A unit test monkeypatches the same three call sites, invokes `attribute(cve_id, package_id, image_ref=None, sbom=<valid SBOM>)`, asserts the call returns a `Provenance` without raising. This kills the "adapter secretly reaches for a real `package-lock.json`" mutant that would slip past a construction-only I/O check.
- [ ] **AC-Idempotent:** Three consecutive `attribute(...)` calls with byte-identical inputs return `==`-equal `Provenance` values (kills any per-call hidden-state cache or first-call mutation).

**`attribute()` signature.**
- [ ] **AC-Signature:** `attribute(self, cve_id: CveId, package_id: PackageId, image_ref: ImageRef | None, sbom: SyftSbom) -> Provenance` — **positional parameters (no `*`)**, `image_ref` typed `ImageRef | None`, matches `src/codegenie/primitives/vuln_provenance/protocols.py:74-80` byte-for-byte in name + order + type. `inspect.signature` smoke test asserts the parameter list `["self", "cve_id", "package_id", "image_ref", "sbom"]` in that order with no `**kwargs`.
- [ ] **AC-ImageRef-None:** `attribute(..., image_ref=None, sbom=<npm_sbom>)` returns the same `Provenance` as the same call with a valid `ImageRef`. The APP-layer adapter ignores `image_ref` (base-image adapters consume it in Step 4).

**Returned-variant contract.**
- [ ] **AC-Direct:** For an SBOM containing `SyftArtifact(name="express", locations=[SyftLocation(path="node_modules/express/package.json")])`, `attribute(..., package_id=PackageId("express"), sbom=…)` returns `AppDirect(kind="app_direct", manifest_path=Path("node_modules/express/package.json"), package=PackageId("express"), confidence=AdapterConfidence.HIGH)`. Assert full equality (all four fields) — kills the "always AppDirect with hardcoded field values" mutant.
- [ ] **AC-Transitive:** For an SBOM containing `SyftArtifact(name="lodash", locations=[SyftLocation(path="node_modules/express/node_modules/lodash/package.json")])`, `attribute(..., package_id=PackageId("lodash"), sbom=…)` returns `AppTransitive(kind="app_transitive", manifest_path=Path("node_modules/express/node_modules/lodash/package.json"), package=PackageId("lodash"), chain=(PackageId("express"), PackageId("lodash")), confidence=AdapterConfidence.HIGH)`. `chain` is the full tuple from outermost hop through the queried package — assert full tuple equality via `==`, not `len(chain) >= 2` alone (which the "always AppDirect + always chain=(pkg, pkg)" mutant survives).
- [ ] **AC-Deep-Nesting:** For depth-3 nesting `node_modules/a/node_modules/b/node_modules/pkg/package.json`, chain is `(a, b, pkg)` — 3 elements. Parametrized over depths 2, 3, and 4.
- [ ] **AC-Scoped:** For `node_modules/@types/lodash/package.json`, the `@types/lodash` scoped-package slug is **one** hop — result is `AppDirect(package=PackageId("@types/lodash"))`, chain length would be 1 (so `AppDirect`, not `AppTransitive` with `chain=("@types", "lodash")`). A parametrized test also covers scoped-transitive `node_modules/express/node_modules/@types/lodash/package.json` → `chain=(express, @types/lodash)`.
- [ ] **AC-Absent-No-Match:** For an SBOM whose `artifacts` list contains no entry with `name == package_id`, `attribute(...)` returns `Unknown(reason="sbom_layer_attribution_absent", details={"package_id": str(package_id)})`. Assert `Unknown.details["package_id"] == str(package_id)`.
- [ ] **AC-Absent-No-Locations:** For an SBOM whose matching artifact has `locations=[]`, `attribute(...)` returns `Unknown(reason="sbom_layer_attribution_absent", details={"package_id": str(package_id)})` (same as no-match — from the classifier's perspective, "matched but no evidence" and "unmatched" are both "cannot attribute").
- [ ] **AC-Non-NodeModules-Path:** For an SBOM whose matching artifact's only location is outside `node_modules/` (e.g., `dist/bundle.js`, `src/index.js`), classifier rejects the path — result is `Unknown(reason="sbom_layer_attribution_absent", details={"package_id": str(package_id)})`. Test parametrized over: (a) `dist/bundle.js`, (b) `src/lodash.js`, (c) `vendor/lodash/index.js`.
- [ ] **AC-Hoisting-Priority:** When the same `package_id` appears at BOTH a direct location (`node_modules/lodash/package.json`) AND a nested location (`node_modules/express/node_modules/lodash/package.json`) in the SBOM, the adapter returns `AppDirect` for the direct entry — the npm hoisting winner is deterministic. This invariant must be documented AND pinned by a test (otherwise the two-location arm silently becomes implementation-defined).
- [ ] **AC-Fail-Loud:** For SBOM shapes the classifier genuinely cannot parse safely (e.g., a `SyftArtifact` whose `locations[0].path` starts with `node_modules/` but the tail is grammar-malformed — no `/package.json` suffix, e.g. `node_modules/express/deeply-broken`), the adapter **raises `AdapterError(...)`** — NEVER returns `Unknown(reason="adapter_error")` directly. A test asserts `pytest.raises(AdapterError)`; a companion test asserts that if the outcome is folded via `assemble_provenance`, the returned `Provenance` is `Unknown(reason="adapter_error")` (the primitive converts). Failure-mode-negative check: `assert not any(p.kind == "unknown" and p.reason == "adapter_error" for p in adapter_direct_call_results)`.

**`confidence()` contract (flat StrEnum).**
- [ ] **AC-Confidence:** `NpmVulnProvenanceAdapter().confidence()` returns `AdapterConfidence.HIGH` unconditionally (adapter-class-level confidence used by the dispatch tie-breaker per `protocols.py:92-98`). This is a pure, stateless method with no dependence on `attribute()` call history — no `_last_outcome` field, no cache. The per-call confidence rides on the returned variant's `.confidence` field (which is `HIGH` for the SBOM-nesting adapter — the classifier is deterministic when it produces a chain).

**Import + fence discipline.**
- [ ] **AC-WarningIds:** Module-level `_WARNING_IDS: Final[frozenset[str]]` declares exactly `frozenset({"vuln_provenance.adapter_error", "vuln_provenance.sbom_missing_locations", "vuln_provenance.node_modules_path_malformed"})`. Validation runs at import time via `if not <cond>: raise AssertionError(...)` (bare `assert` is forbidden by `forbidden-patterns`). Each ID matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. A fence test extending the existing `_WARNING_IDS` validator registry confirms this module is registered.
- [ ] **AC-Forbidden-Patterns:** No `subprocess.run`, `os.system`, `os.popen`, `shell=True`, `eval(`, `exec(`, `__import__(`, `pickle.loads`, no bare `assert` — verified by `pre-commit run forbidden-patterns --files plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py`.
- [ ] **AC-Imports:** The adapter imports only from `codegenie.primitives.vuln_provenance.*` (registry, types, errors), `codegenie.types.identifiers` (newtypes), `pydantic`, and the standard library. NO import from `codegenie.parsers.*`, `codegenie.probes.*`, `codegenie.plugins.*`, or `plugins.vulnerability_remediation__node__npm.recipes.*`. `make lint-imports` clean; no LLM SDK.
- [ ] **AC-Pure-Helper:** The classifier is a pure module-private function `_classify_sbom_locations(paths: Sequence[str], target: PackageId) -> tuple[PackageId, ...] | None`. Returns `None` when zero paths match `node_modules/` grammar; else returns the resolution chain (`(target,)` for depth 1 — but callers should return `AppDirect` for this case, so the function's caller does the "chain length 1 collapses to AppDirect" translation). Pure function is unit-tested with hand-built `Sequence[str]` inputs — no adapter instance required. Kept inline in `npm_provenance.py` (Rule 2 — no sibling `_classify_sbom_locations.py` extraction until Yarn PnP / pnpm layouts land).

**Deterministic-order invariants (mutation-killers).**
- [ ] **AC-Deterministic-Same-Sbom:** Two adapter instances constructed from the factory (via `default_adapter_factory`) return `==`-equal `Provenance` when invoked with byte-identical `sbom` inputs (no instance-level nondeterminism).

**Registry-isolation for tests.**
- [ ] **AC-Registry-Fixture:** Every unit test in `tests/unit/plugins/vulnerability_remediation_node_npm/test_npm_provenance.py` uses the `provenance_registry_reset` autouse fixture (defined in `tests/unit/primitives/vuln_provenance/conftest.py`). No unit test invokes `load_plugins(...)`. No unit test monkeypatches `_REGISTRY` directly.

**Integration seam (deferred to S3-03).**
- [ ] **AC-S3-01-Deferred:** This story does NOT remove `xfail(strict=True)` markers from `tests/integration/test_provenance_assembly_via_plugins.py`; that removal is S3-03's job (S3-03 lands `api.py` import wiring). S3-02's PR touches no integration-test files. **If** the S3-01 fixture defect (Blocker F) has been resolved before S3-02 executes AND the test file is not touched in S3-02's PR, this AC is satisfied by absence.

**Regression + gates.**
- [ ] **AC-Mypy:** `mypy --strict plugins/vulnerability-remediation--node--npm/adapters` clean including `npm_provenance.py`.
- [ ] **AC-Ruff:** `ruff format --check`, `ruff check plugins/vulnerability-remediation--node--npm/adapters` clean.
- [ ] **AC-Full-Check:** `make check` green including Phase 3–6.5 regression suite. **If** `bench/vuln-remediation/` cassette does not exist at execution time (Blocker B unresolved), the cassette-replay assertion is out of scope for THIS story — surface in the attempt log; do not synthesize a cassette. If the bench cassette DOES exist, cassette replay ε ≤ $0.01 is asserted.
- [ ] **AC-Fence-Compliance:** `pytest tests/fence/test_phase7_no_byte_edits_to_locked_files.py` (or equivalent) green — only allowlisted files have byte-changes.
- [ ] **AC-Status:** Story `Status:` line updated to `Done` after all above check out AND both Blocker B (bench cassette) and Blocker F (S3-01 fixture) have resolved. If either blocker persists at execution time, status stays `BLOCKED-PARTIAL`; document what was completed in the attempt log.

## Implementation outline

**Precondition — do NOT skip.** Before writing code, confirm both Blocker B (`ls bench/vuln-remediation/`) and Blocker F (open `tests/integration/_fixtures/syft_sboms/npm_lodash_app.json`; confirm `express` lives at `node_modules/express/package.json` AND `lodash` lives at `node_modules/express/node_modules/lodash/package.json`; confirm the S3-01 direct test queries `express` and the transitive test queries `lodash`). If either fails, STOP. Do NOT synthesize the cassette. Do NOT restructure the fixture as a "while I'm here" edit. Both are surfaced in `_attempts/S3-02-…` and route to the S3-01 owner + a Phase-3 bench-cassette owner respectively.

1. **Skeleton.** Create `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` with the module-level `_WARNING_IDS` constant + `if not <cond>: raise AssertionError(...)` validation block (mirror `src/codegenie/probes/language_detection.py` for the shape). The `adapters/__init__.py` file already exists — do NOT create or modify it. This step consumes byte-edit allowlist row #1 (ADR-0009) and no other rows.
2. **Class signature (DI-minimal).**
   ```python
   from __future__ import annotations
   from pathlib import Path
   from typing import Final
   import re

   from codegenie.primitives.vuln_provenance.errors import AdapterError
   from codegenie.primitives.vuln_provenance.registry import (
       Ecosystem, Layer, register_provenance_adapter,
   )
   from codegenie.primitives.vuln_provenance.types import (
       AdapterConfidence, AppDirect, AppTransitive, Provenance, Unknown,
   )
   from codegenie.types.identifiers import CveId, ImageRef, PackageId

   @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
   class NpmVulnProvenanceAdapter:
       """First concrete `VulnProvenanceAdapter`. Classifies (cve_id, package_id)
       from `SyftArtifact.locations[].path` node_modules/ nesting."""

       def __init__(self, *, logger: object | None = None) -> None:
           # DI vocabulary is closed at _DI_KWARGS = {sbom_reader, logger,
           # image_manifest_cache}; this adapter declares only `logger` because
           # the SBOM arrives as a call arg (no reader needed) and the adapter
           # has no image-manifest cross-verification (deferred until S4-01).
           # Factory (factory.py:99) inspects __init__ and passes only names
           # in the intersection — omitting kwargs is safe.
           self._logger = logger
   ```
3. **Pure classifier helper (module-private, inline).**
   ```python
   _NODE_MODULES_PATH_RE: Final[re.Pattern[str]] = re.compile(
       r"^(?:.+/)?node_modules/(?P<chain>(?:@[^/]+/[^/]+|[^/]+)"
       r"(?:/node_modules/(?:@[^/]+/[^/]+|[^/]+))*)/package\.json$"
   )
   """Match a `node_modules/…/package.json` location string.

   The `chain` group captures package slugs (`pkg` OR `@scope/pkg`) joined by
   `/node_modules/` separators. Depth is derived by splitting the captured
   group on `/node_modules/`. Scoped packages ride as one slug — the alt
   `@[^/]+/[^/]+` in each hop is intentional.
   """

   def _classify_sbom_locations(
       paths: Sequence[str],
       target: PackageId,
   ) -> tuple[PackageId, ...] | None:
       """Return the resolution chain (outermost hop … target), or None if
       no location matches the node_modules/ grammar for `target`.

       PURE function — no I/O, no logging, no exception raising (returns None
       for non-matches; the caller decides whether that's `Unknown` or
       `AdapterError`). Sorts matching chains by depth ASC so hoisting-priority
       (direct beats transitive for the same package) is deterministic.
       """
       chains: list[tuple[PackageId, ...]] = []
       for path in paths:
           m = _NODE_MODULES_PATH_RE.match(path)
           if m is None:
               continue
           hops = tuple(PackageId(h) for h in m.group("chain").split("/node_modules/"))
           if hops[-1] != target:
               continue  # this artifact's location points to a sibling, not target
           chains.append(hops)
       if not chains:
           return None
       chains.sort(key=len)  # shallowest first (hoisting-priority)
       return chains[0]
   ```
4. **`attribute(...)` (positional signature, SBOM-only, ≤ 30 LOC body).**
   ```python
   def attribute(
       self,
       cve_id: CveId,
       package_id: PackageId,
       image_ref: ImageRef | None,
       sbom: SyftSbom,
   ) -> Provenance:
       matching = [a for a in sbom.artifacts if a.name == str(package_id)]
       if not matching:
           return Unknown(
               reason="sbom_layer_attribution_absent",
               details={"package_id": str(package_id)},
           )
       # SyftArtifact.locations may legitimately be [] (upstream tolerates
       # extras but this adapter's contract says no locations = cannot attribute).
       paths: list[str] = [loc.path for a in matching for loc in a.locations]
       if not paths:
           return Unknown(
               reason="sbom_layer_attribution_absent",
               details={"package_id": str(package_id)},
           )
       chain = _classify_sbom_locations(paths, package_id)
       if chain is None:
           return Unknown(
               reason="sbom_layer_attribution_absent",
               details={"package_id": str(package_id)},
           )
       # Reconstruct the manifest_path for the chosen chain — mirrors the
       # path shape the classifier consumed. Uses the same slug ordering.
       manifest_str = "node_modules/" + "/node_modules/".join(str(h) for h in chain) + "/package.json"
       manifest_path = Path(manifest_str)
       if len(chain) == 1:
           return AppDirect(
               manifest_path=manifest_path,
               package=chain[0],
               confidence=AdapterConfidence.HIGH,
           )
       return AppTransitive(
           manifest_path=manifest_path,
           package=chain[-1],
           chain=chain,  # Pydantic Field(min_length=2) enforces length
           confidence=AdapterConfidence.HIGH,
       )
   ```
   **Under-contract raise-`AdapterError` case:** a `SyftArtifact` whose location starts with `node_modules/` but has a malformed tail (no `/package.json` suffix in a way the regex rejects while indicating the artifact SHOULD have been matchable). The current regex simply skips these paths (returns None from classifier → Unknown); no `AdapterError` is raised for grammar-mismatches — the "malformed" case is folded into `Unknown(sbom_layer_attribution_absent)`. **The AC-Fail-Loud test covers the raise arm via a deliberately-broken `SyftLocation` fixture (see TDD plan).** If the executor determines during implementation that no genuine `AdapterError`-warranting failure mode exists on the SBOM-walk surface, drop the raise arm entirely and remove `"vuln_provenance.adapter_error"` from `_WARNING_IDS` — surface in the attempt log.
5. **`confidence(...)` — pure constant.**
   ```python
   def confidence(self) -> AdapterConfidence:
       return AdapterConfidence.HIGH
   ```
   No `_last_outcome` field, no state, no dependence on prior `attribute()` calls. The three-value gradient (`HIGH / DEGRADED / UNAVAILABLE`) is the *class-level* confidence used by the dispatch tie-breaker (`protocols.py:92-98`). The per-call confidence lives on each returned variant's `.confidence` field.
6. **No cross-verification via `sbom_verifier` in this story.** The story previously prescribed a `verifier: SbomVerifier | None = None` DI kwarg for defensive degradation against S4-01 absence. That kwarg is **out of contract** — `_DI_KWARGS` is closed at three names (`factory.py:54`). Adding `verifier` requires an ADR-0007 amendment. Per Rule 2 + Rule 3, S3-02 does NOT attempt cross-verification. When S4-01 lands and (in a future story) the DI vocabulary is widened, cross-verification is added uniformly to all adapters — NOT per-adapter defensively. Any `try: from … import sbom_verifier except ImportError` pattern is a fence violation of the "load-order fragility" discipline.
7. **DO NOT touch `tests/integration/test_provenance_assembly_via_plugins.py`.** The `xfail`-marker removal is S3-03's scope (per AC-S3-01-Deferred). Editing that file in S3-02 either (a) turns it red (no `api.py` wiring yet — adapter isn't registered by the canonical loader), or (b) requires a byte-edit outside allowlist row #1. Neither is acceptable.

## Test-driven development plan

**Red — substantive failures, not import errors.** A `ModuleNotFoundError` red is weak: it also fires if the test path is typo'd or a stub is checked in. Start the red phase with a stub `npm_provenance.py` that imports the primitives and raises `NotImplementedError` from `attribute()` / `confidence()`. Write the unit tests in `tests/unit/plugins/vulnerability_remediation_node_npm/test_npm_provenance.py`; each test is a focused assertion of one AC. Every test should fail with a concrete `AssertionError` or `NotImplementedError`, NOT a `ModuleNotFoundError`. Target red count: ≈ 18 substantive failures (one per AC in the Direct / Transitive / Deep-Nesting / Scoped / Absent-No-Match / Absent-No-Locations / Non-NodeModules-Path / Hoisting-Priority / Fail-Loud / Confidence / Idempotent / NoIO-Init / NoIO-Attribute / ImageRef-None / Init-Positional / Register-Class / Runtime-Check / WarningIds set — 18 total). Commit red.

**Test structure — intent in the name.**
- `test_top_level_node_modules_nesting_classifies_as_direct` (AC-Direct)
- `test_single_hop_node_modules_nesting_produces_transitive_chain_len_2` (AC-Transitive)
- `test_deep_node_modules_nesting_produces_chain_matching_depth` (AC-Deep-Nesting, parametrized over depths 2/3/4)
- `test_scoped_package_slug_counts_as_one_hop` (AC-Scoped, parametrized direct + transitive)
- `test_absent_from_sbom_returns_unknown_with_package_id_detail` (AC-Absent-No-Match)
- `test_matching_artifact_with_empty_locations_returns_unknown` (AC-Absent-No-Locations)
- `test_location_outside_node_modules_returns_unknown` (AC-Non-NodeModules-Path, parametrized)
- `test_hoisted_package_prefers_direct_over_transitive` (AC-Hoisting-Priority)
- `test_malformed_node_modules_path_folds_to_unknown_not_adapter_error` (AC-Fail-Loud — the negative arm)
- `test_confidence_returns_high_unconditionally_and_is_stateless` (AC-Confidence)
- `test_three_calls_with_same_sbom_are_equal` (AC-Idempotent)
- `test_no_io_at_construction` (AC-NoIO-Init — monkeypatches read_text/open/Path.open)
- `test_no_io_inside_attribute_method` (AC-NoIO-Attribute — same monkeypatch, mutation-killer for "adapter secretly reads package-lock.json")
- `test_image_ref_none_returns_same_as_valid_image_ref` (AC-ImageRef-None)
- `test_init_declares_only_subset_of_di_kwargs` (AC-Init-Positional — `inspect.signature`)
- `test_registry_stores_class_not_instance` (AC-Register-Class)
- `test_isinstance_of_protocol_returns_true` (AC-Runtime-Check)
- `test_warning_ids_frozenset_shape_and_regex` (AC-WarningIds)

**Parametrization discipline.** Direct + Transitive + Deep-Nesting + Scoped + Non-NodeModules-Path are `@pytest.mark.parametrize`d. Full input/output tuple equality (`==` on the entire returned variant) — NOT just field-name / length checks. This kills the "always AppDirect with hardcoded fields" and "always chain=(x, x)" mutants.

**Test isolation.** Every test uses the `provenance_registry_reset` autouse fixture from `tests/unit/primitives/vuln_provenance/conftest.py` (extend the collection to include the new plugin path). Registry state does not leak between tests; no `load_plugins(...)` call inside the unit suite.

**Fixture discipline.** Each test constructs its own inline `SyftSbom` via `SyftSbom(artifacts=[SyftArtifact(name=…, locations=[SyftLocation(path=…)])])` — do NOT reuse the S3-01 integration-test fixture (`_fixtures/syft_sboms/npm_lodash_app.json`) — that fixture is under S3-01's ownership and known to be defective (Blocker F). Isolated unit fixtures kill the "fixture-shape mutation" surface.

**Green.** Write the adapter body just-enough to make each unit test pass. The classifier body is ≤ 20 LOC (one regex + one comprehension + one sort). The `attribute()` body is ≤ 30 LOC (list comprehension + three if-branches + variant construction). Total adapter file: ≤ 100 LOC.

**Integration hand-off.** S3-02 does NOT touch the S3-01 integration file. The `xfail`-removal handshake is S3-03's scope. When both S3-02 and S3-03 land AND Blocker F has been resolved, the three positive-path integration tests transition red → green as a natural consequence of the canonical `load_plugins(...)` firing `api.py` which imports `npm_provenance`.

**Refactor.** Do NOT extract the classifier into a sibling `_classify_sbom_locations.py`. The classifier is single-consumer (one adapter, one grammar). Extraction would introduce a naming problem the moment S4-02 lands a totally different apk-db classifier. Rule 2 + Rule 3 — keep inline. Re-run `mypy --strict` + `ruff check` + `make lint-imports` + the full unit suite.

**Metamorphic test candidate (deferred to S4-04 per Out-of-scope).** Property test: for any `SyftArtifact` whose `locations[0].path` matches `_NODE_MODULES_PATH_RE`, `_classify_sbom_locations(paths, target=<last hop>)` returns a chain of length = 1 + count("`/node_modules/`") in the matched substring. S4-04 owns this per current out-of-scope; recorded here as a follow-up hook.

## Files to touch

- `plugins/vulnerability-remediation--node--npm/adapters/npm_provenance.py` (new — **the sole file this story creates; byte-edit allowlist row #1 per ADR-0009**).
- `tests/unit/plugins/vulnerability_remediation_node_npm/test_npm_provenance.py` (new).
- `tests/unit/plugins/vulnerability_remediation_node_npm/__init__.py` (new if absent).

**Files this story explicitly does NOT touch (would fail the byte-edit fence):**
- `plugins/vulnerability-remediation--node--npm/adapters/__init__.py` — already exists (Phase 4 sibling).
- `plugins/vulnerability-remediation--node--npm/api.py` — S3-03's scope.
- `plugins/vulnerability-remediation--node--npm/tccm.yaml` — S3-03's scope.
- `tests/integration/test_provenance_assembly_via_plugins.py` — S3-03's scope (xfail removal follows the wiring).
- `tests/integration/_fixtures/syft_sboms/npm_lodash_app.json` — S3-01 owner's scope (Blocker F resolution).
- `pyproject.toml`, `src/codegenie/__init__.py`, or any other Phase 0–6.5 file — not needed for the SBOM-walk implementation.

## Out of scope

- `plugins/vulnerability-remediation--node--npm/api.py` — the import-wiring line is S3-03's byte-edit (numbered row varies depending on whether ADR-0009 or High-level-impl.md is the canonical allowlist source; S3-03's validation surfaces this contradiction).
- `plugins/vulnerability-remediation--node--npm/tccm.yaml` — S3-03 owns the one new `derived_queries:` block (aligned with S8-02 schema).
- `BaseImageVulnProvenanceAdapter` / `AlpineVulnProvenanceAdapter` — Step 4.
- `sbom_verifier.py` implementation — S4-01. **S3-02 does NOT wire a `verifier: SbomVerifier | None = None` defensive DI kwarg** (that would violate ADR-0007's closed `_DI_KWARGS`). Cross-verification is added uniformly to all adapters in a future post-S4-01 wiring story that amends ADR-0007.
- Property tests over the adapter (Hypothesis SBOM-tampering) — S4-04 owns; this story's tests are example-based + parametrized.
- Performance bench — S12-05 owns the p99 ≤ 50 ms assertion.
- `bench/vuln-remediation/` cassette creation — an upstream Phase 3 obligation, not S3-02's. If the cassette does not exist at execution time, the cassette-replay assertion in AC-Full-Check is skipped; document in the attempt log.
- S3-01 fixture restructure (Blocker F) — an S3-01 owner's obligation. S3-02 does NOT edit the fixture as a "while I'm here" fix; that widens S3-01's scope and contradicts the "do NOT silently widen S3-01's test fixtures" invariant.

## Notes for the implementer

- **Do NOT import from `plugins/vulnerability-remediation--node--npm/recipes/`.** The historical framing ("promoted from Phase 3 refuse-mode shape") is a hint about domain intuition, not an instruction to reuse code. Any import from `recipes/` (a) locks the adapter to Phase 3 internals that will change independently, and (b) may consume an allowlisted-edit budget the story doesn't own. Re-derive independently.
- **The classifier's regex is single-consumer — keep it inline.** Do NOT introduce a marker catalog `_NPM_PATH_CLASSIFIER_RULES: Final[tuple[Rule, ...]]` — one grammar, one regex, one function is enough. Yarn PnP (`.yarn/cache/pkg-...zip`) and pnpm's virtual store (`.pnpm/pkg@x.y.z/node_modules/pkg`) each have entirely different grammars; when they land as separate adapters (Phase 7.5 S2-02/S3-01), each ships its own module with its own regex. Rule-of-three trigger is at that point — NOT here.
- **The Protocol IS the seam. Do NOT create an `AbstractVulnProvenanceAdapter` base class or template method.** S4-02 (Alpine reads apk databases) and S4-03 (Distroless reads `BaseImageProbe` slices) share zero classification logic with S3-02. The abstraction is already the `VulnProvenanceAdapter` Protocol — anything more is speculative kernelism.
- **`AppTransitive.chain` semantics.** Chain is the resolution path from the outermost hop to (and including) the queried package. Length 1 collapses to `AppDirect` (never emit `AppTransitive(chain=(pkg,))` — Pydantic `Field(min_length=2)` will reject it at construction time; caller must translate). For `node_modules/express/node_modules/lodash/package.json` querying `lodash`, chain is `(express, lodash)` — length 2. For depth 3 (`a/node_modules/b/node_modules/c/node_modules/pkg`), chain is `(a, b, c, pkg)` — length 4. The queried package IS the tail element.
- **Re bare `assert`:** `python -m codegenie ...` startup runs each module's import-time validation; bare `assert` is stripped in `-O` mode. Use `if not <cond>: raise AssertionError("...")`. The `forbidden-patterns` pre-commit hook catches violations.
- **Re cassette replay:** if `bench/vuln-remediation/` exists at execution time, the byte-equality replay MUST be green — S3-02 registers into the primitive's `_REGISTRY`, NOT Phase 3's recipe registry, so Phase 3 recipe dispatch is unaffected. Any drift is a bug in the adapter's decorator or an unintended side effect at import time — surface immediately.
- **Re `image_ref: ImageRef | None`.** The APP-layer adapter ignores this parameter (base-image adapters consume it in Step 4). Store it as `_ = image_ref` at the top of `attribute()` to make the "unused parameter" intent explicit; do NOT delete the parameter from the signature (Protocol conformance requires it).
- **Re DI vocabulary minimalism.** The story lands `__init__(self, *, logger: object | None = None)` declaring ONLY `logger`. This is deliberate: the factory (`factory.py:99-113`) inspects `__init__` and passes only names in the intersection of `_DI_KWARGS` and the adapter's declared params — omitting kwargs is safe and reduces spurious `None`-holding fields. If a future revision needs `sbom_reader` (e.g., for lazy-load), add it to the constructor when the need lands, not preemptively.
- **Re the `AdapterError` fail-loud arm.** If, during implementation, no SBOM-shape genuinely warrants raising `AdapterError` (the classifier's "return None on non-match" approach cleanly covers every malformed case as `Unknown(sbom_layer_attribution_absent)`), drop the raise arm entirely: remove `"vuln_provenance.adapter_error"` from `_WARNING_IDS`, delete the raise call, and document in the attempt log. Do NOT keep a raise path with no reachable trigger — that's dead code that lies about the failure surface.
- **Re Blocker F (S3-01 fixture defect).** If the fixture has not been restructured before this story executes, the executor's job is to STOP and log — not to edit the fixture. The correct restructure (surfaced in the story Goal) is: `express` at `node_modules/express/package.json` (direct query target for the direct test), `lodash` at `node_modules/express/node_modules/lodash/package.json` (transitive query target for the transitive test). The direct test's assertion becomes `PackageId("express")`; the transitive test stays on `PackageId("lodash")`. This is a fixture-correctness fix per S3-01's own attempt log — NOT a widening for a wrong impl.
- **Re the design-pattern posture in general.** This story is deliberately Rule-2-forward: ONE regex, ONE pure function, ONE class, ~100 LOC total. Every temptation to abstract now (marker catalog, base class, verifier DI, sibling module extraction) is a YAGNI trap. The extension seams are the Protocol (for a second adapter), the registry (for a second ecosystem), and future ADR amendments (for the DI kwarg vocabulary). None of those are code S3-02 writes.
