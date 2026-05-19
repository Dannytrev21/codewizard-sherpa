# Story S4-04 — Hypothesis SBOM-tampering property test + known-fields-only AST fence

**Step:** Step 4 — `AlpineVulnProvenanceAdapter` + `DistrolessVulnProvenanceAdapter` + `sbom_verifier.py`
**Status:** Ready
**Effort:** M
**Depends on:** S4-02 (`AlpineVulnProvenanceAdapter`), S4-03 (`DistrolessVulnProvenanceAdapter`)
**ADRs honored:** Phase 7 ADR-0004 (primitive home — Gap 3 defensive guards live with the primitive's consumers in the plugin tree), production ADR-0033 (domain-modeling discipline — sum-type discipline survives Hypothesis-drawn adversarial input), production ADR-0007 (probe contract frozen — equivalent discipline for adapter typed surface)

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

## Acceptance criteria

### Hypothesis property test

- [ ] AC-1 — `tests/property/vuln_provenance/test_sbom_tampering.py` exists and runs in CI under `@pytest.mark.phase07_adv` (or the existing closest marker — verify against `pyproject.toml [tool.pytest.ini_options]`; do not add a new marker without coordination).
- [ ] AC-2 — The test defines a Hypothesis strategy `poisoned_sbom_strategy()` that draws `SyftSbom` instances satisfying at least these adversarial shapes (parametrized over ≥ 6 shapes; each shape generates ≥ 20 cases for ≥ 120 cases total):
  - **Shape A (no-attribution):** every `SyftLocation.layerID is None`.
  - **Shape B (malformed `layerID`):** `layerID` is a non-`sha256:` string (`"not-a-digest"`, `""`, `"sha256:"`, `"sha256:DEADBEEF"` (uppercase), `"sha512:..."`, `"layer-0"`).
  - **Shape C (truncated/over-length `layerID`):** `layerID = "sha256:" + ("a" * n)` for `n in [0, 1, 32, 63, 65, 128, 1024]`.
  - **Shape D (fabricated valid-shape `layerID` not in manifest):** `layerID = "sha256:" + 64-hex-char-random` where the random hex is **not** in the corresponding `ImageManifest.layers`.
  - **Shape E (poisoned `extra` content):** SBOM with `extra` keys carrying `dict[str, str]` content designed to look like load-bearing fields (`{"layerID": "sha256:...", "real_layer": "..."}`). The adapter must NOT read these; the verifier must NOT read these.
  - **Shape F (poisoned `descriptor`):** `SyftSbom.descriptor = {"version": "evil", "name": "..."}` carrying prompt-injection-shaped strings (deterministic recipes treat them as data; adapter must not parse).
- [ ] AC-3 — For **every** drawn `SyftSbom`, the test calls `assemble_provenance(cve_id=fixture_cve, package_id=fixture_pkg, image_ref=fixture_image_ref, sbom=poisoned_sbom)` via the registered adapter chain (Alpine + Distroless both loaded). The assertion is:
  - The return value is `Provenance` (one of the seven variants; `extra="forbid"` Pydantic-typed).
  - The return is `Unknown(reason=UnknownReason.SBOM_LAYER_ATTRIBUTION_ABSENT)` OR `Unknown(reason=UnknownReason.BASE_IMAGE_PROBE_ABSENT)` OR `Unknown(reason=UnknownReason.BASE_IMAGE_NOT_DISTROLESS)` OR `BaseImage(...)` (the typed-attested arm, which is unreachable from a poisoned SBOM by construction — included so the test fails loudly if the assembly silently mis-attributes).
  - The return is **NEVER** `AppDirect`, `AppTransitive`, `AppVendored`, `RuntimeBundled`, `Both`. (The Phase 3 npm adapter is loaded; the test fixture deliberately has no `package-lock.json` so the npm adapter returns `Unknown` cleanly. Any other return is a defect.)
- [ ] AC-4 — The test wraps `assemble_provenance(...)` in `try/except Exception as e: pytest.fail(f"adapter raised {type(e).__name__} on poisoned SBOM: {e}")`. **No `KeyError`. No `AttributeError`. No `ValidationError`. No `TypeError`. No uncaught exception of any kind.** (Rule 12 — fail loud.)
- [ ] AC-5 — Determinism property: `assemble_provenance(...)` on the same drawn SBOM twice returns equal `Provenance` instances. (Hypothesis-shrinking reuses the same draw — `@hypothesis.settings(deadline=None, max_examples=120)`; the test pins the seed via `@hypothesis.settings(...)` and asserts equality across two calls.)
- [ ] AC-6 — Hypothesis statistics: the test prints draw distribution at the end of the run (helpful when a future engineer adds a seventh shape and wonders if it's actually being hit). Use `hypothesis.event(...)` to tag each shape.

### AST-walk fence test

- [ ] AC-7 — `tests/fence/test_alpine_adapter_reads_known_fields_only.py` exists and runs in CI under the existing `tests/fence/` discovery.
- [ ] AC-8 — The fence parses `plugins/distroless-migration--node--npm/adapters/alpine_provenance.py` with `ast.parse(source)` and walks the tree. It collects **every attribute access on a name aliased to `SyftSbom`, `SyftArtifact`, `SyftLocation`** and asserts the accessed attribute name is in the closed allowlist `{"name", "version", "artifacts", "locations", "layerID", "path"}`. (The allowlist is hard-coded in the fence; growing it requires editing the fence — visibility is the point.)
- [ ] AC-9 — The fence rejects any of these patterns, even on aliased names:
  - `getattr(<sbom-or-artifact-or-location>, "extra", ...)`.
  - `getattr(<sbom-or-artifact-or-location>, "model_extra", ...)`.
  - `<sbom-or-artifact-or-location>.model_extra`.
  - `<sbom-or-artifact-or-location>.__pydantic_extra__`.
  - `dict(<sbom-or-artifact-or-location>)`.
  - `dict(<sbom-or-artifact-or-location>).items()` / `.keys()` / `.values()`.
  - `<sbom>.descriptor` (the `dict[str, Any]` field is explicitly off-limits).
  - `<sbom>.descriptor[...]`.
  - `vars(<sbom-or-artifact-or-location>)`.
  - `<sbom-or-artifact-or-location>.__dict__`.
- [ ] AC-10 — The fence also walks `plugins/distroless-migration--node--npm/adapters/distroless_provenance.py` and `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` and applies the same rejection rules. (One fence file, three modules.)
- [ ] AC-11 — **Negative test for the fence itself:** the fence's own test suite includes a deliberately-failing fixture — a tiny Python file at `tests/fence/_ignore_sbom_drift_fixtures/bad_adapter.py` that DOES `getattr(artifact, "extra", {})`. The fence machinery is invoked against the fixture in `tests/fence/test_alpine_adapter_reads_known_fields_only_meta.py::test_fence_catches_planted_drift` and the assertion is that the fence **fails** on the fixture. **This is the fence's own self-test: prove it actually catches a violation.** (Mirrors the Phase 0 fence-self-test discipline, e.g., the `tests/fence/test_pyproject_fence.py` self-test.)
- [ ] AC-12 — The fence uses AST-only inspection — no execution, no `inspect.getsource(...)`-via-import (to keep the fence independent of any runtime state). Plain `ast.parse(Path(...).read_text())`.

### Cross-checks + hygiene

- [ ] AC-13 — Both tests are runnable standalone: `pytest tests/property/vuln_provenance/test_sbom_tampering.py -v` and `pytest tests/fence/test_alpine_adapter_reads_known_fields_only.py -v` (and the `_meta.py` self-test).
- [ ] AC-14 — The property test's runtime is bounded: `@hypothesis.settings(deadline=None, max_examples=120)` — actual wall-clock on Phase 0 CI's runners is ≤ 30 seconds. (Profile and adjust `max_examples` downward if needed, but never below 100 per AC.)
- [ ] AC-15 — `mypy --strict tests/property/vuln_provenance/test_sbom_tampering.py tests/fence/test_alpine_adapter_reads_known_fields_only.py` clean. The tests carry typed signatures — no `Any` on the strategy functions, no `Any` on the fixture builders.
- [ ] AC-16 — `ruff check`, `ruff format --check` clean.
- [ ] AC-17 — `make lint-imports` green — both test files may import from `codegenie.primitives.vuln_provenance.*`; the property test additionally imports from the plugin tree to load the adapters; the fence imports only `ast` + `pathlib` + stdlib (no plugin-tree imports — it reads source files as text).
- [ ] AC-18 — `tests/fence/test_phase7_no_llm.py` (S1-06) green.
- [ ] AC-19 — Phase 3–6.5 regression suite + `bench/vuln-remediation/` cassette replay green (`make check` — hard pre-merge gate per Phase 7 ADR-0009).
- [ ] AC-20 — Story Status updated to `Done`.

## Implementation outline

1. Author `tests/property/vuln_provenance/test_sbom_tampering.py`:
   - Hypothesis strategies for each of the six shapes (A–F). Build them composably from `hypothesis.strategies.builds(SyftLocation, layerID=...)`, `lists(syft_location_strategy())`, etc.
   - Fixture: a `BaseImageProbe` slice with a known `ImageManifest.layers = ("sha256:KNOWN...",)`. **Crucially, the random Shape-D hex must not equal `"sha256:KNOWN..."`** — assert this in the strategy via `assume(...)`.
   - Per-shape `@hypothesis.given(...)` test function; each function calls `assemble_provenance(...)` and runs the AC-3 assertion + AC-4 try/except discipline.
   - Tag with `hypothesis.event("shape:A_no_attribution")` etc. for visibility.
2. Author `tests/fence/test_alpine_adapter_reads_known_fields_only.py`:
   - `KNOWN_FIELD_ALLOWLIST: Final[frozenset[str]] = frozenset({"name", "version", "artifacts", "locations", "layerID", "path"})`.
   - `FORBIDDEN_ACCESS_PATTERNS: Final[frozenset[str]] = frozenset({"extra", "model_extra", "__pydantic_extra__", "__dict__", "descriptor"})`.
   - `_SBOM_TYPE_NAMES: Final[frozenset[str]] = frozenset({"SyftSbom", "SyftArtifact", "SyftLocation"})`.
   - `_collect_sbom_aliases(tree: ast.AST) -> set[str]` — walks `tree` collecting names assigned via `: SyftSbom`, `: SyftArtifact`, `: SyftLocation` (function parameter annotations + assignment targets). Returns the alias set.
   - `_walk_attribute_accesses(tree, aliases) -> list[Violation]` — visits every `ast.Attribute` and `ast.Call` node; flags violations against AC-9's rejection rules.
   - `_walk_subscript_accesses(tree, aliases)` — flags `.descriptor[...]` and `dict(...)[...]` patterns.
   - Test asserts the violations list is empty for each of the three target modules.
3. Author `tests/fence/_ignore_sbom_drift_fixtures/bad_adapter.py`:
   - Minimal file with a planted violation — e.g., a function that does `getattr(artifact, "extra", {}).get("layerID")`.
4. Author `tests/fence/test_alpine_adapter_reads_known_fields_only_meta.py::test_fence_catches_planted_drift`:
   - Imports the fence's `_walk_attribute_accesses` function (or the public `find_violations(path) -> list[Violation]` helper if the fence exposes one); runs it against the planted fixture; asserts violations are found.
5. Run `make check`. Property test should pass cleanly; if any draw fails, **read the failure** — the failure is likely a defect in S4-01/S4-02/S4-03, not a flaky test. Surface the defect explicitly (Rule 12).
6. Commit.

## TDD plan (red → green → refactor)

**Red:**
- Write the property test first — point it at the **existing** Alpine + Distroless adapters from S4-02/S4-03. If S4-02/S4-03's defensive behavior is correctly implemented, the test passes immediately (which is good — but check by **deliberately introducing a regression** in a scratch branch: change S4-02's `Unknown(reason=SBOM_LAYER_ATTRIBUTION_ABSENT)` to `AppDirect(...)`. The test must catch this. Revert the regression before committing.).
- Write the fence test. Run it against the existing S4-02/S4-03 source. Confirm zero violations.
- Write `_ignore_sbom_drift_fixtures/bad_adapter.py` + the `_meta.py` self-test. The self-test should **fail** initially (because the fence-impl function isn't exposed yet).

**Green:**
- Implement the fence's `_walk_attribute_accesses` / `find_violations` helpers.
- The self-test now passes.

**Refactor:**
- If the property test's strategy code exceeds ~120 LOC, extract per-shape strategy builders into a small `_strategies.py` helper module under `tests/property/vuln_provenance/_strategies/`. Keep the test file's `@given` decorators tightly readable.
- If the fence's AST walker exceeds ~150 LOC, extract `_SbomAccessAuditor(ast.NodeVisitor)` as a separate class within the fence module.

## Files to touch

**New:**
- `tests/property/vuln_provenance/test_sbom_tampering.py` (≤ 250 LOC).
- `tests/fence/test_alpine_adapter_reads_known_fields_only.py` (≤ 200 LOC).
- `tests/fence/test_alpine_adapter_reads_known_fields_only_meta.py` (≤ 50 LOC).
- `tests/fence/_ignore_sbom_drift_fixtures/__init__.py` (empty).
- `tests/fence/_ignore_sbom_drift_fixtures/bad_adapter.py` (planted-violation fixture; ≤ 30 LOC).

**Edited:**
- None outside `tests/`. **This story adds no production code.**

**Do not touch:**
- `plugins/distroless-migration--node--npm/adapters/*.py` (S4-02/S4-03 own; if a defect surfaces, escalate via a separate fix-up story or hand-off to the implementer of the originating story).
- `src/codegenie/primitives/vuln_provenance/sbom_verifier.py` (S4-01-owned).
- `src/codegenie/primitives/vuln_provenance/syft_reader.py` (S1-05-owned).

## Out of scope

- Generating poisoned SBOMs **as files on disk** (the property test builds in-memory `SyftSbom` instances via Pydantic strategies). The `tests/fixtures/portfolio/node-poisoned-sbom/` filesystem fixture is S12-01's responsibility.
- Adversarial Dockerfile / prompt-injection tests (S12-04).
- Catalog YAML tamper-detection (S9-02).
- Sigstore-bundled signed-SBOM verification (Phase 12 / Phase 13.5 territory).
- Performance bench for the adapters under poisoned SBOMs (S12-05 — the perf bench uses honest fixtures, not adversarial draws).

## Notes for the implementer

- **The property test is the headline-correctness invariant for Phase 7's adapter layer.** If it fails after S4-02/S4-03 ship, that's a real defect — surface it (Rule 12 — fail loud). Do NOT mark the test `@pytest.mark.xfail` or weaken any assertion to make it pass.
- **`assume(...)` is your friend.** Shape D (fabricated `layerID`) requires the drawn hex to **not** equal a known good `layerID`. Use `hypothesis.assume(drawn_hex != known_hex)` — Hypothesis will discard the rare collisions.
- **The fence test's negative self-test is non-negotiable.** Without `_meta.py`, the fence could silently pass on a real violation (e.g., a bug in the AST walker that mis-identifies aliased names). The self-test fixture proves the fence works. Mirrors `tests/fence/test_pyproject_fence.py`'s discipline.
- **`SyftSbom.descriptor` is named in the fence even though no current adapter touches it.** This is **structural defense** — the fence is what prevents a future engineer from "just one quick read" of `descriptor`. Adding `descriptor` to the rejection set costs nothing now and protects the future.
- **Hypothesis `max_examples=120` is the floor.** Phase 7 ADR-0009's regression-gate discipline requires defenses that **scale with adversarial creativity**. If you have CI budget for `max_examples=500`, take it — the test is bounded by the adapter's ~20 ms perf envelope, so ≤ 30 seconds wall-clock at 500 examples.
- **Don't conflate "fence" and "property test".** The fence is **static** (AST inspection of source files at CI time); the property test is **dynamic** (calls `assemble_provenance` with adversarial inputs). They cover orthogonal failure modes:
  - **Static drift:** an engineer reaches into `getattr(artifact, "extra", ...)`. The property test would not catch this if the engineer guards their access with `.get("layerID", None)` cleverly. The fence catches it because the *pattern* is forbidden.
  - **Dynamic poisoning:** an attacker crafts an SBOM whose existing fields lie about layer attribution. The fence cannot catch this because the source code does the right thing structurally. The property test catches it because the adapter's behavior is asserted on the typed return.
- **Be aggressive with `hypothesis.event(...)`.** Tagging each shape gives you per-shape draw counts in the test output — you'll see immediately if Shape E is hitting 0.1% of draws because the strategy is mis-built.
- **The fence's allowlist (`KNOWN_FIELD_ALLOWLIST`) is the most precious shared resource here.** Growing it requires:
  1. Editing the fence file (visible in PR diff).
  2. An ADR amendment justifying the new field.
  3. Coordinator review (CODEOWNERS if the fence is owned by a team).
  Treat the allowlist as the typed boundary of the entire Gap-3 defense.
- **No `Any` anywhere in the test code.** The strategies are typed `SearchStrategy[SyftSbom]`, etc. The fence's `Violation` is a frozen Pydantic record, not a `dict`. Mirrors the S1-06 no-`Any` fence.
