# Story S4-03 — `DistrolessVulnProvenanceAdapter` (already-distroless detection)

**Step:** Step 4 — `AlpineVulnProvenanceAdapter` + `DistrolessVulnProvenanceAdapter` + `sbom_verifier.py`
**Status:** Ready
**Effort:** S
**Depends on:** S2-04 (`assemble_provenance` + `_ADAPTER_DISPATCH_ORDER`), S4-01 (`sbom_verifier.py`), S4-02 (plugin tree bootstrap + `adapters/__init__.py`)
**ADRs honored:** Phase 7 ADR-0004 (primitive home — adapter lives under the plugin), Phase 7 ADR-0005 (plugin-contributed probes + adapters), Phase 7 ADR-0007 (registry stores classes, not instances)

## Context

`DistrolessVulnProvenanceAdapter` is the **refuser**. Unlike `AlpineVulnProvenanceAdapter` (S4-02), which *attributes* a vulnerable package to the Alpine `apk` database, this adapter exists to **recognize that a repo's base image is already distroless** (e.g., `FROM cgr.dev/chainguard/node` or `FROM gcr.io/distroless/nodejs20`) and **refuse to attribute**. Its return on a positive detection is `Unknown(reason="base_image_already_distroless")` — a typed signal to the migration plugin's match step that `Applicability.NotApplicable` is the correct response.

The adapter's job is therefore narrow: read the `BaseImageProbe` slice (when present), check `base_image_kind == "distroless"`, return the dedicated `Unknown` reason. If the slice is absent, return `Unknown(reason="base_image_probe_absent")` (same defensive degradation as the Alpine adapter — Step 7 hasn't shipped yet).

The adapter is registered at `(Layer.BASE_IMAGE, Ecosystem.DPKG)`. Distroless images are debian-derived in practice, hence `DPKG`. The placement is a slight stretch of the ecosystem taxonomy — distroless images intentionally have **no package manager at runtime**, so "DPKG" is a label of provenance (the image was built from debian-slim) rather than a runtime package manager. The arch (`phase-arch-design.md §Component design §7c.`) calls this a "placeholder" assignment; the trade-off is acceptable because the adapter's job is to refuse, and the ecosystem-tiebreaker (S2-03's `Ecosystem`-enum-sorted iteration) means this adapter is consulted **before** any future `(BASE_IMAGE, DPKG)` debian-runtime adapter — exactly the order operators want (recognize distroless first, then attempt attribution).

The adapter is small: ≤ 60 LOC body, no SBOM cross-verification (the verifier is for attribution; this adapter refuses to attribute), no `confidence` complexity (always `AdapterConfidence.HIGH` when it returns its dedicated reason; `AdapterConfidence.LOW` otherwise).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §7c. DistrolessVulnProvenanceAdapter` (lines 760–765 — full component spec).
  - `../phase-arch-design.md §Edge cases row #3` (line 1242 — "Base image is already distroless → migration plugin returns `NotApplicable`; vuln plugin may still apply if the CVE has app provenance").
  - `../phase-arch-design.md §Component design §7b. AlpineVulnProvenanceAdapter` (S4-02-owned; read as the sibling-shape precedent).
  - `../phase-arch-design.md §Component design §2 — Provenance discriminated union` — `Unknown(reason: UnknownReason)` where `UnknownReason` literal includes `"base_image_already_distroless"`.
- **Phase ADRs:**
  - `../ADRs/0004-vuln-provenance-primitive-home.md` — primitive home for `Unknown`/`UnknownReason`.
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — adapter lives in the plugin tree.
  - `../ADRs/0007-provenance-adapter-registry-stores-classes.md` — DI-kwarg vocabulary + class-not-instance registration.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py` (S4-02-shipped) — the sibling adapter; mirror the `__init__` + `confidence` shape. The `attribute` body is **simpler** here — no SBOM cross-verification.
  - `src/codegenie/primitives/vuln_provenance/types.py` (S1-02-owned) — confirm `UnknownReason.BASE_IMAGE_ALREADY_DISTROLESS` is in the enum. If not, the value is added additively (coordinate with S1-02 implementer like the parallel work in S4-02).
  - `src/codegenie/primitives/vuln_provenance/registry.py` (S2-01) — `@register_provenance_adapter`.

## Goal

Ship `plugins/distroless-migration--node--npm/adapters/distroless_provenance.py` containing `DistrolessVulnProvenanceAdapter` registered at `(Layer.BASE_IMAGE, Ecosystem.DPKG)`. The adapter inspects the `BaseImageProbe` slice for `base_image_kind == "distroless"` and returns `Unknown(reason=UnknownReason.BASE_IMAGE_ALREADY_DISTROLESS)` on positive detection. The migration plugin's match step uses this signal to return `Applicability.NotApplicable` so the workflow short-circuits cleanly.

## Acceptance criteria

### Module shape + registration (Phase 7 ADR-0007 compliant)

- [ ] AC-1 — `plugins/distroless-migration--node--npm/adapters/distroless_provenance.py` exists with `class DistrolessVulnProvenanceAdapter` decorated `@register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.DPKG)`.
- [ ] AC-2 — `__init__` accepts only kwargs from the closed DI vocabulary: `sbom_reader: SbomReader | None = None`, `logger: Logger | None = None`, `image_manifest_cache: ImageManifestCache | None = None`. **No positional args; no I/O at construction.**
- [ ] AC-3 — `attribute(self, *, cve_id: CveId, package_id: PackageId, image_ref: ImageRef | None, sbom: SyftSbom, repo_context: RepoContext) -> Provenance` signature matches the sibling `AlpineVulnProvenanceAdapter` exactly.
- [ ] AC-4 — `confidence(self) -> AdapterConfidence` returns `AdapterConfidence.HIGH` when the last `attribute` returned the dedicated `BASE_IMAGE_ALREADY_DISTROLESS` reason; `AdapterConfidence.LOW` otherwise.
- [ ] AC-5 — Module declares `_WARNING_IDS: Final[frozenset[str]] = frozenset({"distroless_provenance.base_image_probe_absent"})` validated at import via `raise AssertionError(...)`.
- [ ] AC-6 — Side-effect registration wired: `plugins/distroless-migration--node--npm/api.py` gains a second explicit-import line — `from .adapters import distroless_provenance  # noqa: F401`. The `api.py` now has two side-effect import lines (the Alpine one from S4-02 + this one).
- [ ] AC-7 — `tests/integration/test_provenance_assembly_via_plugins.py` (extended) — after plugin import, `_REGISTRY[(Layer.BASE_IMAGE, Ecosystem.DPKG)] is DistrolessVulnProvenanceAdapter` (the class).

### Behavioral correctness — sum-type exhaustive

- [ ] AC-8 — Distroless detected: `repo_context.probes["BaseImage"].kind == "distroless"` → returns `Unknown(reason=UnknownReason.BASE_IMAGE_ALREADY_DISTROLESS)`. The adapter does NOT touch the SBOM in this case — it short-circuits on the probe slice alone.
- [ ] AC-9 — Non-distroless base: `repo_context.probes["BaseImage"].kind == "minimal"` (Alpine) → returns `Unknown(reason=UnknownReason.BASE_IMAGE_NOT_DISTROLESS)` (a typed "this is not my problem" signal; the Alpine adapter will handle this image). **The adapter does not raise; it returns the typed signal.**
- [ ] AC-10 — Non-distroless base, kind `"full"` (debian-slim or ubuntu) → returns `Unknown(reason=UnknownReason.BASE_IMAGE_NOT_DISTROLESS)`. Same path as AC-9.
- [ ] AC-11 — Unknown base kind: `repo_context.probes["BaseImage"].kind == "unknown"` → returns `Unknown(reason=UnknownReason.BASE_IMAGE_NOT_DISTROLESS)`. Conservative: we don't know, so we refuse to claim distroless.
- [ ] AC-12 — `BaseImageProbe` slice absent: `repo_context.probes.get("BaseImage") is None` → `Unknown(reason=UnknownReason.BASE_IMAGE_PROBE_ABSENT)`. **No exception.**
- [ ] AC-13 — Match exhaustiveness: `tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance_exhaustiveness.py` proves `match attribute(...): case Unknown(): ...; case _: pytest.fail(...)`. (The adapter never returns `BaseImage` — it refuses.)

### Defensive — no SBOM recursion

- [ ] AC-14 — The adapter does NOT iterate `sbom.artifacts`, does NOT read `sbom.descriptor`, does NOT call any verifier. (Confirmed by AST inspection in `tests/fence/test_distroless_adapter_does_not_touch_sbom.py` — a sibling fence to S4-04's Alpine fence.) **The adapter's job is to refuse based on probe data alone.**
- [ ] AC-15 — No `dict[str, Any]` anywhere in the module (covered by S1-06's no-`Any` fence).

### Hygiene

- [ ] AC-16 — `mypy --strict plugins/distroless-migration--node--npm/adapters/distroless_provenance.py` clean.
- [ ] AC-17 — `ruff check`, `ruff format --check` clean.
- [ ] AC-18 — `make lint-imports` green: the adapter may import from `codegenie.primitives.vuln_provenance.*` but NOT from `codegenie.coordinator`, `codegenie.cache`, or any LLM SDK.
- [ ] AC-19 — `tests/fence/test_phase7_no_llm.py` (S1-06) green.
- [ ] AC-20 — Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay green (`make check`).
- [ ] AC-21 — Story Status updated to `Done`.

## Implementation outline

1. Confirm `UnknownReason` (from S1-02) carries `BASE_IMAGE_ALREADY_DISTROLESS`, `BASE_IMAGE_NOT_DISTROLESS`, `BASE_IMAGE_PROBE_ABSENT`. If any are missing, add them additively (coordinate with S1-02 implementer per the parallel work in S4-02; the additions are part of `UnknownReason`'s closed-but-extensible enum surface).
2. Author `plugins/distroless-migration--node--npm/adapters/distroless_provenance.py`:
   - Module docstring naming Phase 7 ADR-0004 / ADR-0005 / ADR-0007.
   - `_WARNING_IDS` declaration.
   - `class DistrolessVulnProvenanceAdapter` decorated `@register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.DPKG)`.
   - `__init__` storing DI kwargs (no I/O).
   - `attribute` — decision tree:
     a. `slice = repo_context.probes.get("BaseImage")`. If `None` → `Unknown(reason=UnknownReason.BASE_IMAGE_PROBE_ABSENT)`.
     b. If `slice.kind == "distroless"` → `Unknown(reason=UnknownReason.BASE_IMAGE_ALREADY_DISTROLESS)`.
     c. Else → `Unknown(reason=UnknownReason.BASE_IMAGE_NOT_DISTROLESS)`.
   - `confidence` — track the last decision via a frozen attribute (or rebuild per-call); return `HIGH` only when the last decision was `BASE_IMAGE_ALREADY_DISTROLESS`.
3. Add the second side-effect import to `plugins/distroless-migration--node--npm/api.py` — `from .adapters import distroless_provenance  # noqa: F401`.
4. Author the test files.
5. Run `make check`, fix lint, commit.

## TDD plan (red → green → refactor)

**Red (write tests first, watch them fail):**
- `tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance.py::test_distroless_base_returns_already_distroless_unknown` — fixture slice with `kind="distroless"`; expect `Unknown(reason=UnknownReason.BASE_IMAGE_ALREADY_DISTROLESS)`. **Fails:** adapter doesn't exist.
- `tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance.py::test_alpine_base_returns_not_distroless_unknown` — fixture slice with `kind="minimal"`; expect `Unknown(reason=UnknownReason.BASE_IMAGE_NOT_DISTROLESS)`.
- `tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance.py::test_full_base_returns_not_distroless_unknown` — `kind="full"`; same as above.
- `tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance.py::test_unknown_base_returns_not_distroless_unknown` — `kind="unknown"`; conservative refusal.
- `tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance.py::test_base_image_probe_absent_returns_probe_absent` — `repo_context.probes` empty.
- `tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance.py::test_construction_does_no_io` — instantiate with no args; assert no FS / no log.
- `tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance.py::test_registry_holds_class_not_instance` — after import, `_REGISTRY[(Layer.BASE_IMAGE, Ecosystem.DPKG)] is DistrolessVulnProvenanceAdapter`.
- `tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance.py::test_adapter_does_not_read_sbom` — pass an SBOM with a known-poison artifact (`name="absurd"`, `version="absurd"`); adapter ignores it; returns based on probe slice alone. (Behavioral; the AST fence is the structural backup.)
- `tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance_exhaustiveness.py::test_match_arms` — `match` covers `Unknown`; `BaseImage` is never produced; `_: pytest.fail(...)`.
- `tests/fence/test_distroless_adapter_does_not_touch_sbom.py::test_no_sbom_iteration` — AST-walks the module, rejects `for _ in sbom.artifacts:`, `sbom.descriptor[...]`, `sbom.artifacts[...]`. Asserts the only references to `sbom` are the parameter declaration in `attribute`.
- `tests/integration/test_provenance_assembly_via_plugins.py` (extended) — after plugin import, `_REGISTRY[(Layer.BASE_IMAGE, Ecosystem.DPKG)] is DistrolessVulnProvenanceAdapter`; `assemble_provenance(...)` on a distroless-target fixture returns `Unknown(reason=BASE_IMAGE_ALREADY_DISTROLESS)`.

**Green:** implement per §Implementation outline.

**Refactor:** body is ≤ 30 LOC; no refactor anticipated. If a future adapter shares the "read probe slice → return typed `Unknown`" shape, extract a `_classify_base_image_kind(slice) -> UnknownReason` module-private helper — but **only** at the rule of three (third adapter doing the same thing), not now.

## Files to touch

**New:**
- `plugins/distroless-migration--node--npm/adapters/distroless_provenance.py` (≤ 80 LOC).
- `tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance.py`.
- `tests/unit/plugins/distroless_migration_node_npm/test_distroless_provenance_exhaustiveness.py`.
- `tests/fence/test_distroless_adapter_does_not_touch_sbom.py`.

**Edited (additive only):**
- `plugins/distroless-migration--node--npm/api.py` — add `from .adapters import distroless_provenance  # noqa: F401` line.
- `src/codegenie/primitives/vuln_provenance/types.py` — `UnknownReason` extended with new values if not already present (coordinate with S1-02).
- `tests/integration/test_provenance_assembly_via_plugins.py` — one new test case.

**Do not touch:**
- `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py` (S4-02-owned).
- `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` (S4-01-owned; this adapter does not call it).
- Anything under `src/codegenie/probes/`.

## Out of scope

- The Alpine adapter (S4-02).
- The Hypothesis SBOM-tampering test + AST fence for Alpine (S4-04; this story's sibling fence `test_distroless_adapter_does_not_touch_sbom.py` is more aggressive: it asserts the adapter doesn't touch the SBOM **at all**).
- `BaseImageProbe` itself (Step 7).
- Recognizing alternative distroless registries (e.g., `nvcr.io/nvidia/distroless/*`) — the `base_image_kind` enum value `"distroless"` is the only signal this adapter reads; Step 7's `BaseImageProbe` classification table (`_BASE_IMAGE_KIND_RULES`) owns the per-registry mapping.
- The `Applicability.NotApplicable` translation — that lives in the migration plugin's match step (Step 8 / Step 11).

## Notes for the implementer

- **The adapter is intentionally simple.** Its job is to refuse, cleanly, with a typed signal. Resist the urge to make it "smarter" — e.g., reading the SBOM to corroborate the probe slice. That would defeat the structural separation (`AlpineVulnProvenanceAdapter` does the attribution work; this adapter is the refuser).
- **`BASE_IMAGE_NOT_DISTROLESS` vs `BASE_IMAGE_NOT_ALPINE` are siblings, not synonyms.** The Alpine adapter returns the latter when the probe slice doesn't match its ecosystem; this adapter returns the former. Operators reading `sbom.routing_anomaly`-shaped events can disambiguate.
- **The `Ecosystem.DPKG` label is a placeholder.** Per `phase-arch-design.md §7c.`, distroless images are debian-derived, so `DPKG` is the closest match in the current `Ecosystem` enum (S2-01). A future ADR amendment may add `Ecosystem.DISTROLESS_NODE` or similar — but Phase 7 does not need that taxonomy. Don't add it now.
- **The intentional asymmetry with the Alpine adapter.** Alpine: attributes (returns `BaseImage`). Distroless: refuses (returns `Unknown`). This asymmetry is the architecture's load-bearing claim — the assembly free function (S2-04) sees a `Unknown` from this adapter and continues iteration; the migration plugin's match step sees the dedicated `BASE_IMAGE_ALREADY_DISTROLESS` reason and short-circuits. Don't blur this.
- **Don't try to load `BaseImageProbe`'s slice into a typed model here.** The probe slice (Step 7) is its own typed Pydantic model. This adapter reads the field `slice.kind` — that's it. If you find yourself wanting to read more fields, you're past the scope.
- **Confidence rationale.** When the adapter returns `BASE_IMAGE_ALREADY_DISTROLESS`, it has high-confidence direct probe evidence (the Dockerfile's `FROM` line resolved to a distroless registry). Anything else is low-confidence by design — the adapter's job ended at "not distroless"; the actual attribution is someone else's adapter's problem.
- **The AST fence `test_distroless_adapter_does_not_touch_sbom.py` is strict.** Even a `_ = sbom` line (assigning to underscore) is forbidden. The adapter's `attribute` signature accepts `sbom` because the Protocol requires it, but the body never references the parameter. Mark it `_sbom` if the linter complains about an unused parameter — but check the codebase convention first (search for an `_unused` pattern; if none exists, leave `sbom` and rely on `# noqa: ARG002` or the strict-yet-tolerant `ruff` configuration).
