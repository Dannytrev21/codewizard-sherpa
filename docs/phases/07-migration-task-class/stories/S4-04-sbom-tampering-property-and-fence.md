# Story S4-04 — Hypothesis SBOM-tampering property test + known-fields-only AST fence

**Step:** Step 4 — `AlpineVulnProvenanceAdapter` + `DistrolessVulnProvenanceAdapter` + `sbom_verifier.py`
**Status:** HARDENED (phase-story-validator, 2026-08-14 — pre-executor pass; see `_validation/S4-04-sbom-tampering-property-and-fence.md`)
**Effort:** M
**Depends on:** S4-01 (`sbom_verifier.py` — must be `Done`, not just `HARDENED`), S4-02 (`AlpineVulnProvenanceAdapter` — must be `Done`), S4-03 (`DistrolessVulnProvenanceAdapter` — must be `Done`), S1-05 (owns `syft_reader.py`; this story adds a `_KNOWN_SBOM_FIELDS` frozenset — coordinate the additive edit)
**ADRs honored:** Phase 7 ADR-0004 (primitive home — Gap 3 defensive guards live with the primitive's consumers in the plugin tree), production ADR-0033 (domain-modeling discipline — sum-type discipline survives Hypothesis-drawn adversarial input), production ADR-0007 (probe contract frozen — equivalent discipline for adapter typed surface), production ADR-0039 (bounded additive core primitives — the fence is a consumer of the primitive's own field catalogs, not a mirror)

## Validation notes (2026-08-14)

Seven merged edits during the phase-story-validator pass — full audit at `_validation/S4-04-sbom-tampering-property-and-fence.md`:

1. **Single-source-of-truth for the SBOM known-field catalog** (was BLOCK). Fence no longer hardcodes an allowlist; it imports `_KNOWN_LOCATION_FIELDS`, `_KNOWN_ARTIFACT_FIELDS`, and (new) `_KNOWN_SBOM_FIELDS` from `codegenie.primitives.vuln_provenance.syft_reader`. Adds one additive edit to `syft_reader.py` for the missing catalog.
2. **Factual correction on `SyftSbom.descriptor`** (was BLOCK). Shipped `SyftSbom` has no typed `descriptor` field — Shape F's poisoned-`descriptor` case is constructed via `SyftSbom(**{"descriptor": {...}})` and lands in `__pydantic_extra__`. Fence still forbids the name.
3. **Pre-flight AC-0** (was BLOCK). Story is blocked until S4-01/S4-02/S4-03 are `Done` (not just `HARDENED`) — the fence walks source files that don't exist yet. Executor halts with a `_lessons.md` entry if any target file is missing.
4. **Walker-helper-module pattern** (was BLOCK-RESOLVED). Mirrors the shipped `test_no_any_in_provenance_surface.py` — walker in `tests/fence/_lib/sbom_access_audit.py`; fence file consumes it; `_SHAPE_MATRIX` parametrized snippets prove the walker per pattern shape. Removed the `_meta.py` + `_ignore_sbom_drift_fixtures/bad_adapter.py` scratch-file approach.
5. **Full `Unknown.reason` allow-set** (was HARDEN). AC-3 now enumerates the closed set of six reasons `assemble_provenance` can produce on a poisoned-SBOM call path, and explicitly forbids the three that indicate a defect.
6. **`SbomShape` StrEnum + shape-completeness assertion** (was HARDEN). Shapes A–G live as `class SbomShape(StrEnum)` members in the shared strategies module; AC-6 asserts every enum member appears in `hypothesis.stats.event_counts` (silent-skip → silent-fail).
7. **Deterministic Shape-D construction, no `assume(...)`** (was HARDEN). Shape D uses a manifest with `layers = ()` so every drawn hex is guaranteed-not-in-manifest without rejection sampling.

Plus: marker choice pinned (no `phase07_adv` — property test runs in the default suite); `@pytest.mark.timeout(60)` on the property test; try/except wrapper dropped from AC-4 (Hypothesis's own falsifying-example reporter is louder than `pytest.fail`); `image_ref=None` (Shape G) added; `Violation` typed as a `NamedTuple` with a `Literal` `kind`.

## Context

S4-01 (verifier), S4-02 (Alpine adapter), and S4-03 (Distroless adapter) all read from `SyftSbom` — the one Pydantic model in the primitive that deliberately tolerates `extra="allow"` (Phase 2 carry-forward; `phase-arch-design.md` line 1226: "`SyftSbom` carries `extra="allow"` deliberately"). This is a **deliberate hole in the typed boundary**: Phase 2 chose not to enumerate every field syft emits, and the cost of forking syft's schema for every minor version was too high. The hole is named in **Gap 3** of the arch (`phase-arch-design.md §Gap 3 — SBOM byte-level trust beyond layer attribution`, lines 1423–1428).

This story ships the **two structural defenses** that make the hole survivable until Phase 12 closes it:

1. **A Hypothesis property test** (`tests/property/vuln_provenance/test_sbom_tampering.py`) — generates 100+ adversarial `SyftSbom` instances with malformed, poisoned, or fabricated `locations[].layerID` values; runs the full `assemble_provenance(...)` path through both base-image adapters; asserts **every case lands in `Unknown(reason="sbom_layer_attribution_absent")` or a typed-attested `BaseImage`**, with **NO `KeyError`, NO silent `app_direct` mis-attribution, NO uncaught exception**.
2. **An AST-walk fence test** (`tests/fence/test_alpine_adapter_reads_known_fields_only.py`) — statically asserts that the Alpine adapter (and, by extension, the Distroless adapter and the verifier) read **only** the known-load-bearing fields (`SyftArtifact.name`, `SyftArtifact.version`, `SyftLocation.layerID`, `SyftLocation.path`) and **never** recurse into `extra` content. The fence catches **future drift** — a year from now, an engineer who reaches into `sbom.descriptor` or `getattr(artifact, "extra", {})` hits a CI failure before merge.

Together, the two defenses turn Gap 3 from a "hope the implementer remembers" risk into a mechanically-enforced invariant. They cap the blast radius of any future poisoned-SBOM attack at "the adapter returns `Unknown`" — the orchestrator's `sbom.routing_anomaly` event lights up, the workflow routes to HITL, no PR opens. This is the **headline correctness property** of Phase 7's adapter layer.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap 3 — SBOM byte-level trust beyond layer attribution` (lines 1423–1428) — verbatim: "Phase 7 adds a defensive guard inside the adapter: the adapter reads ONLY the fields it consumes (`locations[].layerID`, `name`, `version`) and never recurses into `extra` content. A fence test (`tests/fence/test_alpine_adapter_reads_known_fields_only.py`) AST-walks the adapter and asserts no `getattr(sbom_artifact, "extra", ...)` or `dict(sbom_artifact).items()` pattern is used."
  - `../phase-arch-design.md §Testing strategy §Property tests` (line 1284) — verbatim AC: "`tests/property/vuln_provenance/test_sbom_tampering.py` — 100+ generated SBOMs with malformed/poisoned `locations[].layerID`; every case lands in `Unknown(reason="sbom_layer_attribution_absent")` or a typed-attested result. **No `KeyError`, no silent `app_direct`.**"
  - `../phase-arch-design.md §Edge cases row #1` (line 1240).
  - `../phase-arch-design.md §Data model SyftSbom` (lines 1037–1053) — the `extra="allow"` declaration; `descriptor: dict[str, Any]` is the broadest hole.
  - `../phase-arch-design.md §Testing strategy §Adversarial / property` and §Coverage table.
- **Phase ADRs:**
  - `../ADRs/0004-vuln-provenance-primitive-home.md` — primitive home (the fence ensures the consumers respect the boundary).
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py` (S4-02-shipped).
  - `plugins/distroless-migration--node--npm/adapters/distroless_provenance.py` (S4-03-shipped).
  - `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` (S4-01-shipped).
  - `src/codegenie/primitives/vuln_provenance/syft_reader.py` (S1-05-shipped).
  - `tests/property/` — search for existing Hypothesis tests in the codebase to mirror style. (Phase 3 + Phase 6.5 have property-test precedents.)
  - `tests/fence/` — search for existing AST-walk fence tests. The probe-context conformance fence and the "no-`Any`" fence (S1-06) are the closest precedents.
- **Prior validation history:**
  - `../../03-vuln-deterministic-recipe/stories/_validation/` — search for property-test hardening patterns (NFKC normalization in Phase 3 S1-01 is a good shape reference for Hypothesis adversarial drawing).

## Goal

Ship two structural defenses that make Gap 3 a mechanically-enforced invariant:

1. A Hypothesis property test (`tests/property/vuln_provenance/test_sbom_tampering.py`) drawing ≥ 100 adversarial SBOMs and asserting every adapter run lands in a typed-safe state.
2. An AST-walk fence (`tests/fence/test_alpine_adapter_reads_known_fields_only.py`) that statically catches future drift into untyped SBOM content.

## Pre-flight

- [ ] AC-0 — **Pre-flight guard.** Confirm all three target source files exist:
  - `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py` (owned by S4-02).
  - `plugins/distroless-migration--node--npm/adapters/distroless_provenance.py` (owned by S4-03).
  - `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` (owned by S4-01).

  If any is missing, **mark this story `BLOCKED-PARTIAL`, write a `_lessons.md` entry naming the missing precondition, and halt execution.** Do NOT stub out the missing files — S4-01/S4-02/S4-03 own their creation and this story only fires once they ship. (The three stories are `HARDENED` as of 2026-08-14 but not yet `Done`; verify before starting.)

## Acceptance criteria

### Hypothesis property test

- [ ] AC-1 — `tests/property/vuln_provenance/test_sbom_tampering.py` exists and runs in the **default** `pytest -q` suite (no `phase07_adv` marker — verified against `pyproject.toml [tool.pytest.ini_options]`; the marker does not exist, and this defense is CI-gating, not opt-in). If a future story wants an adversarial partition, that story adds the marker; this story does not.
- [ ] AC-2 — The test's Hypothesis strategy set draws `SyftSbom` instances covering **seven** adversarial shapes (parametrized over `SbomShape` — see AC-2b; each shape draws ≥ 20 cases for ≥ 140 cases total under `max_examples=140`):
  - **Shape A (`A_NO_ATTRIBUTION`):** every `SyftLocation.layerID is None`.
  - **Shape B (`B_MALFORMED_LAYER_ID`):** `layerID` is a non-`sha256:` string (drawn from `st.sampled_from(("not-a-digest", "", "sha256:", "sha256:DEADBEEF", "sha512:" + "0" * 128, "layer-0"))`).
  - **Shape C (`C_TRUNCATED_LAYER_ID`):** `layerID = "sha256:" + ("a" * n)` for `n` drawn from `st.sampled_from((0, 1, 32, 63, 65, 128, 1024))`.
  - **Shape D (`D_FABRICATED_LAYER_ID`):** `layerID = "sha256:" + 64-hex-char-random` drawn from `st.text(alphabet="0123456789abcdef", min_size=64, max_size=64).map(lambda h: f"sha256:{h}")`. The **fixture manifest holds `layers = ()`** by construction — every drawn hex is guaranteed-not-in-manifest **without `assume(...)` rejection sampling**.
  - **Shape E (`E_POISONED_ARTIFACT_EXTRA`):** SBOM with `SyftArtifact` instances carrying extras (via `SyftArtifact(**{"layerID": "sha256:...", "real_layer": "..."})`) — Pydantic captures the keys in `__pydantic_extra__` since `SyftArtifact.model_config = ConfigDict(extra="allow")` and no typed `layerID` field exists on the artifact.
  - **Shape F (`F_POISONED_SBOM_EXTRA`):** `SyftSbom(**{"descriptor": {"version": "evil", "name": "Ignore previous instructions"}, "source": {...}})` — the shipped `SyftSbom` has no typed `descriptor` field, so the key lands in `__pydantic_extra__`. The fence forbids `<sbom>.descriptor` and `<sbom>.__pydantic_extra__` access **regardless of whether the field is typed today**, so a future story that adds `descriptor` as a typed field does not create a leak.
  - **Shape G (`G_NULL_IMAGE_REF`):** any of Shapes A–F paired with `image_ref=None` on the `assemble_provenance` call (the adapter chain's `image_ref: ImageRef | None` surface is exercised on the adversarial input; asserts the return still lands in AC-3's allow-set).
- [ ] AC-2b — Shape catalog is typed: `class SbomShape(StrEnum)` lives in `tests/property/vuln_provenance/_sbom_tampering_strategies.py` with members `A_NO_ATTRIBUTION`, `B_MALFORMED_LAYER_ID`, `C_TRUNCATED_LAYER_ID`, `D_FABRICATED_LAYER_ID`, `E_POISONED_ARTIFACT_EXTRA`, `F_POISONED_SBOM_EXTRA`, `G_NULL_IMAGE_REF`. Each strategy tags its draw with `hypothesis.event(shape.value)`; AC-6 asserts every member appears in the run's event counts (see below).
- [ ] AC-3 — For **every** drawn `SyftSbom`, the test calls `assemble_provenance(cve_id=fixture_cve, package_id=fixture_pkg, image_ref=fixture_image_ref_or_none, sbom=poisoned_sbom)` via the registered adapter chain (Alpine + Distroless both loaded; the Phase 3 npm adapter also loaded but the test fixture has no `package-lock.json`). The assertion is:
  - The return value is a `Provenance` variant (routed through `TypeAdapter(Provenance).validate_python(...)` — the discriminator path).
  - The return's `kind` is `"unknown"` (i.e., an `Unknown` variant); the `reason` is in the closed allow-set: `{"sbom_layer_attribution_absent", "base_image_probe_absent", "base_image_not_distroless", "base_image_not_alpine", "no_adapter_resolved", "adapter_error"}`.
  - The return's `reason` is **NEVER** any of `{"build_failed", "dockerfile_parse_failed", "base_image_already_distroless"}` (those come from other code paths; reaching them on a poisoned-SBOM call is a defect).
  - The return's `kind` is **NEVER** any of `{"app_direct", "app_transitive", "app_vendored", "base_image", "runtime_bundled", "both"}` (mis-attribution on a poisoned SBOM is the headline correctness violation).
- [ ] AC-4 — **No exception discipline.** The test does NOT wrap `assemble_provenance(...)` in `try/except`. Hypothesis's own falsifying-example reporter surfaces the raw traceback and shrunk-input, which is a louder failure signal than a wrapped `pytest.fail`. If the callee raises `KeyError`, `AttributeError`, `ValidationError`, `TypeError`, or any other exception, Hypothesis reports it directly (Rule 12 — fail loud; the pytest error surface is louder than a wrapped `pytest.fail`).
- [ ] AC-5 — **Functional determinism.** For every drawn SBOM, the test calls `assemble_provenance(...)` **twice** with byte-identical inputs and asserts the two returned `Provenance` instances compare equal (Pydantic `__eq__`). This extends `test_idempotence.py`'s clean-input property to the poisoned-input surface. (Not a seed-determinism claim — Hypothesis's seed is CI-dependent by default; the assertion is pure-function-of-inputs.)
- [ ] AC-6 — **Shape-completeness assertion.** The test emits `hypothesis.event(shape.value)` at the top of every strategy's draw. A `finalize`-style helper (implemented via a pytest fixture that captures `hypothesis.stats` or, simpler, a per-test `_seen: set[SbomShape]` populated by the strategies and asserted at teardown) asserts `_seen == set(SbomShape)` — every enum member appeared at least once. A regression that mis-composes the `st.one_of` and silently drops Shape E fires this AC, not silent-green.

### AST-walk fence — walker library + fence file + shape matrix

- [ ] AC-7 — `tests/fence/test_alpine_adapter_reads_known_fields_only.py` exists and runs in CI under the existing `tests/fence/` discovery.
- [ ] AC-8 — The fence's per-type allowlist is **not hardcoded**; it is imported from `codegenie.primitives.vuln_provenance.syft_reader`:
  - `_KNOWN_LOCATION_FIELDS: frozenset[str]` (shipped) — the `SyftLocation` allowlist.
  - `_KNOWN_ARTIFACT_FIELDS: frozenset[str]` (shipped) — the `SyftArtifact` allowlist.
  - `_KNOWN_SBOM_FIELDS: frozenset[str]` (**added by AC-8a**) — the `SyftSbom` allowlist.

  The fence's walker checks each attribute access against the allowlist for the type of the aliased name. Adding a new field to any Syft type is a **one-line addition to the appropriate `_KNOWN_*_FIELDS` frozenset** in `syft_reader.py`; the fence picks it up automatically (no fence-file edit required for typed-field additions).
- [ ] AC-8a — **Additive edit to `syft_reader.py`** (coordinate with S1-05's owner): add `_KNOWN_SBOM_FIELDS: Final[frozenset[str]] = frozenset({"artifacts"})` with the docstring "Fields adapters may read on a `SyftSbom`. S4-04's AST-walk fence asserts every adapter reads only members of this set; growing it is a two-line change here + a one-line fence update (which imports this constant)." Verify the addition is covered by Phase 7 ADR-0009's byte-edit allowlist (S5-01 territory); if not, coordinate the allowlist row.
- [ ] AC-9 — The fence rejects any of these patterns, even on aliased names (walker in `tests/fence/_lib/sbom_access_audit.py`):
  - `getattr(<sbom-or-artifact-or-location>, "extra", ...)`.
  - `getattr(<sbom-or-artifact-or-location>, "model_extra", ...)`.
  - `<sbom-or-artifact-or-location>.model_extra`.
  - `<sbom-or-artifact-or-location>.__pydantic_extra__`.
  - `dict(<sbom-or-artifact-or-location>)`.
  - `dict(<sbom-or-artifact-or-location>).items()` / `.keys()` / `.values()`.
  - `<sbom>.descriptor` / `<sbom>.source` / `<sbom>.distro` (aspirational-typed fields the shipped model does not yet declare — the fence forbids them so a future typed-field addition doesn't create a leak).
  - `<sbom>.descriptor[...]` (subscript-after-forbidden-attribute).
  - `vars(<sbom-or-artifact-or-location>)`.
  - `<sbom-or-artifact-or-location>.__dict__`.

  Any attribute access whose accessed name is **not** in the imported per-type allowlist is a violation (default-deny).
- [ ] AC-10 — The fence walks a **named, typed target list** `_SBOM_CONSUMER_TARGETS: Final[tuple[Path, ...]]` at the module level of the fence file:
  ```python
  _SBOM_CONSUMER_TARGETS: Final[tuple[Path, ...]] = (
      _REPO_ROOT / "plugins/distroless-migration--node--npm/adapters/alpine_provenance.py",
      _REPO_ROOT / "plugins/distroless-migration--node--npm/adapters/distroless_provenance.py",
      _REPO_ROOT / "src/codegenie/primitives/vuln_provenance/sbom_verifier.py",
  )
  ```
  The fence parametrizes over the tuple (`@pytest.mark.parametrize`) so one failing target is one failing test row (not a merged assertion). Floor guard: `test_each_sbom_consumer_target_exists` asserts every entry is a real file — silent-green on a deleted target is impossible (Rule 12; mirrors `test_no_any_in_provenance_surface.py`'s `test_each_phase7_root_exists_and_is_non_empty`).
- [ ] AC-11 — **Walker-helper library** at `tests/fence/_lib/sbom_access_audit.py` exposing a typed public surface:
  ```python
  class Violation(NamedTuple):
      file: Path
      line: int
      kind: Literal["forbidden_attr", "forbidden_getattr", "forbidden_dict_call",
                    "forbidden_vars_call", "forbidden_dunder_dict",
                    "unknown_attr"]
      snippet: str

  def find_violations(source: str, path: Path, *,
                      sbom_fields: frozenset[str],
                      artifact_fields: frozenset[str],
                      location_fields: frozenset[str]) -> tuple[Violation, ...]: ...
  ```
  Both the fence file and the walker's own tests import from this helper. **`_SHAPE_MATRIX: Final[tuple[tuple[str, bool, str], ...]]`** in the fence file parametrizes positive+negative snippets (source-code fragments + expected-hit + docstring); each row is independently asserted, so a walker regression that drops one pattern (e.g., forgets to handle `getattr` with a string default) fires exactly the row that pattern covers. Mirrors `test_no_any_in_provenance_surface.py`'s `_SHAPE_MATRIX` discipline.

  **Removed from this design:** `_meta.py`, `_ignore_sbom_drift_fixtures/`, `bad_adapter.py` (scratch-file self-test pattern is not the Phase-7 idiom).
- [ ] AC-12 — The walker uses AST-only inspection — no execution, no `inspect.getsource(...)`-via-import. Plain `ast.parse(source)` + `ast.walk` (or an `ast.NodeVisitor` subclass). Idempotent and side-effect-free.

### Cross-checks + hygiene

- [ ] AC-13 — All three test artifacts are runnable standalone:
  - `pytest tests/property/vuln_provenance/test_sbom_tampering.py -v --no-cov`.
  - `pytest tests/fence/test_alpine_adapter_reads_known_fields_only.py -v --no-cov`.
- [ ] AC-14 — The property test's runtime is bounded by `@hypothesis.settings(deadline=None, max_examples=140)` **plus** a CI-enforced ceiling `@pytest.mark.timeout(60)` (2× the 30-second design target as a hard ceiling). If a future strategy regression widens draw complexity, the timeout fires; the AC does not silently blow through.
- [ ] AC-15 — `mypy --strict` clean on the property test, the fence test, the strategies module, and the walker library. No `Any` anywhere; typed `Violation` `NamedTuple`; typed `SbomShape` enum; typed strategy return types.
- [ ] AC-16 — `ruff check`, `ruff format --check` clean.
- [ ] AC-17 — `make lint-imports` green:
  - Property test may import from `codegenie.primitives.vuln_provenance.*` and from `plugins.distroless_migration__node__npm.adapters.*` (needed to trigger adapter registration).
  - Fence file may import from `codegenie.primitives.vuln_provenance.syft_reader` (the three `_KNOWN_*_FIELDS` constants — **data-only read**, no functional coupling). May NOT import from any plugin-tree module.
  - Walker library imports only stdlib (`ast`, `pathlib`, `typing`).
- [ ] AC-18 — `tests/fence/test_phase7_no_llm.py` (S1-06) green.
- [ ] AC-19 — Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay green (`make check` — hard pre-merge gate per Phase 7 ADR-0009).
- [ ] AC-20 — Story Status updated to `Done`.

## Implementation outline

1. **Run AC-0 pre-flight.** Confirm the three target source files exist. Halt with `BLOCKED-PARTIAL` if any is missing.
2. **Additive edit to `syft_reader.py`** (AC-8a). Coordinate with S1-05's owner: add `_KNOWN_SBOM_FIELDS: Final[frozenset[str]] = frozenset({"artifacts"})` with the "S4-04 fence source of truth" docstring, mirroring the two sibling catalogs at lines 41–49. Verify Phase 7 ADR-0009's byte-edit allowlist covers `syft_reader.py` for this addition (S5-01 territory).
3. **Author `tests/property/vuln_provenance/_sbom_tampering_strategies.py`** — the shared strategies module:
   - `class SbomShape(StrEnum)` with the seven members (AC-2b).
   - One per-shape strategy function returning `SearchStrategy[SyftSbom]`. Each function `hypothesis.event(shape.value)`-tags its draw.
   - Fixture builders: `def empty_image_manifest() -> ImageManifest: return ImageManifest(layers=())` (Shape D's deterministic-construction guarantee).
   - `def poisoned_sbom_strategy() -> SearchStrategy[tuple[SyftSbom, SbomShape]]`: `st.one_of(...)` composed over the per-shape strategies; returns the `(sbom, shape)` pair so the test can populate a `_seen` set for the completeness assertion.
4. **Author `tests/fence/_lib/sbom_access_audit.py`** — the walker helper library:
   - `class Violation(NamedTuple)` with the typed fields from AC-11.
   - `def find_violations(source: str, path: Path, *, sbom_fields, artifact_fields, location_fields) -> tuple[Violation, ...]`:
     - `ast.parse(source)` → `ast.walk`.
     - Collect aliases assigned via `: SyftSbom`, `: SyftArtifact`, `: SyftLocation` annotations (function params + assignments + AnnAssign).
     - Visit `ast.Attribute` nodes; if `.value.id` is an alias, check `.attr` against the per-type allowlist; flag if missing.
     - Visit `ast.Call` nodes; flag `getattr(<alias>, "<forbidden-name>", ...)`, `dict(<alias>)`, `vars(<alias>)`.
     - Flag `<alias>.__dict__`, `<alias>.__pydantic_extra__`, `<alias>.model_extra`.
     - Return the collected violations as a sorted `tuple[Violation, ...]`.
   - `tests/fence/_lib/__init__.py` — empty (marker file for the helper package).
5. **Author `tests/property/vuln_provenance/test_sbom_tampering.py`**:
   - Imports strategies from `_sbom_tampering_strategies`.
   - `@given(poisoned_sbom_strategy())` decorated test function.
   - `@hypothesis.settings(deadline=None, max_examples=140)` + `@pytest.mark.timeout(60)`.
   - Body: unpack `(sbom, shape)`, populate `_seen.add(shape)`, call `assemble_provenance(...)` twice (AC-5), assert equality + AC-3's typed-return constraints.
   - `hypothesis.event(shape.value)` tag (already emitted by the strategy — this is defensive).
   - Session-scoped fixture asserts `_seen == set(SbomShape)` at teardown (AC-6).
6. **Author `tests/fence/test_alpine_adapter_reads_known_fields_only.py`**:
   - Imports `find_violations`, `Violation` from `tests.fence._lib.sbom_access_audit`.
   - Imports `_KNOWN_LOCATION_FIELDS`, `_KNOWN_ARTIFACT_FIELDS`, `_KNOWN_SBOM_FIELDS` from `codegenie.primitives.vuln_provenance.syft_reader`.
   - Defines `_SBOM_CONSUMER_TARGETS: Final[tuple[Path, ...]]` per AC-10.
   - Defines `_SHAPE_MATRIX: Final[tuple[tuple[str, bool, str], ...]]` with positive+negative snippets per AC-11 (each row: source-code fragment, expected-hit boolean, docstring).
   - `test_each_sbom_consumer_target_exists` — floor guard per AC-10.
   - `test_target_has_no_violations` — parametrized over `_SBOM_CONSUMER_TARGETS`; asserts `find_violations(...) == ()`.
   - `test_walker_catches_each_shape` — parametrized over `_SHAPE_MATRIX`; asserts the walker's per-snippet coverage.
7. Run `make check`. Property test should pass cleanly against the shipped adapters. **If a draw fails, read the failure — the falsifying example is likely a defect in S4-01/S4-02/S4-03, not a flaky test. Surface the defect explicitly (Rule 12).**
8. Commit.

## TDD plan (red → green → refactor)

**Red:**
- Write the walker library (`tests/fence/_lib/sbom_access_audit.py`) with the `Violation` NamedTuple and a stub `find_violations` that returns `()` unconditionally.
- Write the fence file (`test_alpine_adapter_reads_known_fields_only.py`) with `_SHAPE_MATRIX` and the parametrized `test_walker_catches_each_shape` test. **These tests fail** — every positive snippet expects a violation but the stub returns none.
- Write the strategies module (`_sbom_tampering_strategies.py`) and the property test (`test_sbom_tampering.py`). If S4-02/S4-03's defensive behavior is correctly implemented, the property test passes immediately (good — validate by **deliberately introducing a regression** in a scratch branch: change one shipped adapter's `Unknown(reason="sbom_layer_attribution_absent")` to `AppDirect(...)`. The property test must catch this. Revert.).

**Green:**
- Implement `find_violations` — the AST walker per AC-9. `test_walker_catches_each_shape` now passes for every row.
- `test_target_has_no_violations` runs against the three shipped source files and passes (assuming S4-01/S4-02/S4-03 already read only allowlisted fields, which their HARDENED validations pin).

**Refactor:**
- If the walker exceeds ~200 LOC, extract `_SbomAccessAuditor(ast.NodeVisitor)` as a helper class inside `sbom_access_audit.py`. Keep the public `find_violations` surface stable.
- If the per-shape strategies exceed ~120 LOC, they already live in `_sbom_tampering_strategies.py` — no further extraction needed.

## Files to touch

**New:**
- `tests/property/vuln_provenance/_sbom_tampering_strategies.py` (≤ 200 LOC).
- `tests/property/vuln_provenance/test_sbom_tampering.py` (≤ 150 LOC).
- `tests/fence/_lib/__init__.py` (empty marker file).
- `tests/fence/_lib/sbom_access_audit.py` (≤ 250 LOC — the walker library).
- `tests/fence/test_alpine_adapter_reads_known_fields_only.py` (≤ 250 LOC — the fence file with `_SBOM_CONSUMER_TARGETS` + `_SHAPE_MATRIX`).

**Edited (additive, coordinated with S1-05's owner):**
- `src/codegenie/primitives/vuln_provenance/syft_reader.py` — add one new module-level `frozenset` constant `_KNOWN_SBOM_FIELDS` and its docstring (≤ 5 LOC net addition). Verify Phase 7 ADR-0009 byte-edit allowlist coverage before landing.

**Do not touch:**
- `plugins/distroless-migration--node--npm/adapters/*.py` (S4-02/S4-03 own; if a defect surfaces, escalate via a separate fix-up story).
- `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` (S4-01-owned).
- Any typed-field declarations in `syft_reader.py` (S1-05-owned; this story only adds the `_KNOWN_SBOM_FIELDS` constant).

## Out of scope

- Generating poisoned SBOMs **as files on disk** (the property test builds in-memory `SyftSbom` instances via Pydantic strategies). The `tests/fixtures/portfolio/node-poisoned-sbom/` filesystem fixture is S12-01's responsibility.
- Adversarial Dockerfile / prompt-injection tests (S12-04).
- Catalog YAML tamper-detection (S9-02).
- Sigstore-bundled signed-SBOM verification (Phase 12 / Phase 13.5 territory).
- Performance bench for the adapters under poisoned SBOMs (S12-05 — the perf bench uses honest fixtures, not adversarial draws).

## Notes for the implementer

- **Pre-flight is non-negotiable.** AC-0 halts execution if the three target source files don't exist. S4-01/S4-02/S4-03 are `HARDENED` as of 2026-08-14 but not yet `Done`; the executor picking this story up must confirm those three shipped before starting. Write a `_lessons.md` entry and mark `BLOCKED-PARTIAL` if any is missing — do NOT stub out the missing files.
- **The fence is a *consumer* of the primitive's field catalogs, not a mirror.** `syft_reader.py` already declares `_KNOWN_LOCATION_FIELDS` + `_KNOWN_ARTIFACT_FIELDS` as "S4-04 fence source of truth"; this story adds the missing `_KNOWN_SBOM_FIELDS` sibling. Adding a new field to any Syft type is a **one-line addition to one `_KNOWN_*_FIELDS` frozenset** in `syft_reader.py`; the fence picks it up automatically. Do NOT redeclare an allowlist inside the fence file — that is the single-source-of-truth violation this story exists to prevent.
- **Follow `test_no_any_in_provenance_surface.py`'s shape, not `test_pyproject_fence.py`'s.** The canonical Phase-7 AST-walk fence is walker-in-library + fence-file-consumes-it + `_SHAPE_MATRIX`-parametrized-per-pattern. No `_meta.py`. No planted-fixture files under `tests/fence/_ignore_*/`. `test_vuln_provenance_no_model_construct.py` is the second-cleanest precedent (simpler; single-file fence).
- **The property test is the headline-correctness invariant for Phase 7's adapter layer.** If it fails after S4-02/S4-03 ship, that's a real defect in the shipped adapter — surface it (Rule 12 — fail loud). Do NOT mark the test `@pytest.mark.xfail` or weaken any assertion to make it pass.
- **Deterministic Shape-D construction, not `assume(...)`.** Rejection sampling loops. Use a fixture manifest with `layers = ()` so every drawn hex is guaranteed-not-in-manifest by construction. Hypothesis's own docs deprecate `assume(...)` in favor of `st.builds(...).filter(...)` / `st.integers(...).map(...)`; deterministic construction is faster and shrinks better.
- **`SyftSbom.descriptor` / `.source` / `.distro` are named in the fence even though the shipped model does not typed-declare them.** This is structural defense — the fence prevents a future engineer from "just one quick read" of these aspirational fields via `__pydantic_extra__`, and if a future story adds one as a typed field the fence still forbids the name until an explicit `_KNOWN_SBOM_FIELDS` addition + fence-shape update.
- **`SbomShape` StrEnum is the completeness anchor.** Without it, a bug that silently drops one shape from the `st.one_of` composition slips (the total draw count stays at 140; you'd never notice Shape E is missing). AC-6's `_seen == set(SbomShape)` teardown assertion is what makes silent-skip loud-fail.
- **No exception-wrapping in the property test.** Hypothesis's own falsifying-example reporter surfaces the raw traceback + shrunk input, which is a stronger failure signal than a wrapped `pytest.fail(f"raised {type(e)}")`. Do NOT re-add the try/except pattern.
- **The `_SBOM_CONSUMER_TARGETS` tuple is the natural extension point.** Today it holds three entries (Rule-of-three threshold reached but not crossed). When a fourth SBOM-consuming module lands (e.g., a debian adapter, or Phase 3's `npm_provenance.py` if it ever grows an SBOM-attribution path), the hoist point is to convert the tuple to auto-discovery over a `_SBOM_CONSUMER_ROOTS: Final[tuple[Path, ...]]` glob. Not this story's concern.
- **Don't conflate "fence" and "property test".** They cover orthogonal failure modes:
  - **Static drift:** an engineer reaches into `getattr(artifact, "extra", ...)`. The property test wouldn't catch this if the engineer guards the access with `.get("layerID", None)` cleverly. The fence catches it because the *pattern* is forbidden regardless of runtime behavior.
  - **Dynamic poisoning:** an attacker crafts an SBOM whose existing fields lie about layer attribution. The fence cannot catch this because the source code does the right thing structurally. The property test catches it because the adapter's behavior is asserted on the typed return under adversarial input.
- **CI wall-clock ceiling.** `@pytest.mark.timeout(60)` is a hard ceiling; `@hypothesis.settings(max_examples=140)` is the design floor. If future adapters grow expensive (e.g., the runtime adapter Phase 8+ ships), increase `timeout` first, then decide whether `max_examples` needs to drop. Never disable the timeout to "make it green".
- **`_KNOWN_SBOM_FIELDS` growth path.** If a future adapter needs to read `SyftSbom.source` (the aspirational typed field), the discipline is: (1) declare `source: SyftSource` on `SyftSbom` in `syft_reader.py`, (2) add `"source"` to `_KNOWN_SBOM_FIELDS`, (3) that's it — the fence automatically permits the access. Rule 11 (match conventions) — mirror the two shipped catalogs' patterns exactly.
- **No `Any` anywhere in the test code.** Strategies are `SearchStrategy[SyftSbom]`; `Violation` is a typed `NamedTuple`; every helper is typed. Mirrors the S1-06 no-`Any` fence.
