# Story S7-05 — Probe-contract conformance + envelope-validation integration test

**Step:** Step 7 — `BaseImageProbe` + `ShellInvocationTraceProbe` under the plugin (sandboxed)
**Status:** Ready
**Effort:** S
**Depends on:** S7-03 (sub-schemas + envelope `$ref` + goldens). The integration test consumes the schemas + goldens this story validates against.
**ADRs honored:** Phase 0 ADR-0007 (frozen Probe ABC — both new probes must satisfy the conformance fence, identically to existing probes); Phase 7 ADR-0005 (probes live under `plugins/distroless-migration--node--npm/probes/` — the conformance fence walks plugin probes alongside core probes); Phase 1 ADR-0004 (envelope schema is the single source of truth for slice shapes); Phase 7 ADR-0009 (this story is **test-only** — no Phase 0–6.5 byte-edits).

## Context

This story is the **closing integration story for Step 7**. The previous four stories (S7-01, S7-02, S7-03, S7-04) shipped: the two probes, their sub-schemas, the envelope `$ref`s, the goldens, the `ALLOWED_BINARIES` amendment, and the `dockerfile-parse` runtime dep. This story proves the parts compose correctly:

1. The **probe-context-conformance fence** (existing `tests/fence/test_probe_context_conformance.py` style — landed in Phase 0 / Phase 1) extends to cover both new plugin probes. The fence walks every registered `Probe`, instantiates it with a synthetic `ProbeContext`, and asserts the probe's `run(repo, ctx)` signature is the frozen two-arg shape, that no probe references a `ProbeContext` attribute not declared in the ABC (per Phase 1 ADR-0002 / Phase 2 ADR-0004's closed-extension discipline), and that `name` / `layer` / `tier` are well-typed. The fence is the structural integrity check for the registry — every probe, plugin or core, must pass.

2. The **envelope-validation integration test** (`tests/integration/test_probe_outputs_validate_against_envelope.py`) runs each new probe against its canonical fixture, captures the slice, merges it into a synthetic `RepoContext` envelope, and validates the merged envelope against `src/codegenie/schema/repo_context.schema.json`. This is the **round-trip proof** that S7-01's slice shape + S7-03's sub-schemas + the envelope's two `$ref` insertions all agree. Without this test, drift between the slice and the schema lands silently.

3. The story closes `mypy --strict` over `plugins/distroless-migration--node--npm/probes/` — both probes must type-check cleanly as a directory unit (not just per-file). This catches cross-module type drift (e.g., a typed `SlicePayload` exported from `_models.py` that the probe doesn't match).

This is the **smallest test-only story in Step 7** — no production code lands, no byte-edits to Phase 0–6.5 files, no new ADR consequences. But it's the **integration choke point** for Step 7: if any of S7-01..S7-04's contracts drifted during implementation, this story is where the drift surfaces. S8-01..S8-04 (which wire the plugin manifest + TCCM + loader) depend on this story's tests being green — without them, plugin resolution at Step 8 has no guarantee the probes' slices are envelope-valid.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy §Fence / structural` — names the probe-context-conformance fence as the universal probe gate; both new probes must pass.
  - `../phase-arch-design.md §Testing strategy §Integration tests` — names `test_probe_outputs_validate_against_envelope.py` as the round-trip integrity check.
- **Phase ADRs:**
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` §Consequences — the conformance fence walks plugin probes alongside core probes ("the registry contains exactly the expected probes after import").
  - `../ADRs/0009-phase-7-byte-edit-allowlist-fence.md` — this story is test-only; no allowlist row consumed.
- **Existing code:**
  - `tests/fence/test_probe_context_conformance.py` (Phase 0 / Phase 1 — verify exact filename in the current repo via `ls tests/fence/`) — the fence this story extends. **Read its current shape before editing**; mirror its parametrize style.
  - `src/codegenie/probes/base.py` — the frozen ABC the fence enforces.
  - `src/codegenie/schema/repo_context.schema.json` — post-S7-03 envelope.
  - `plugins/distroless-migration--node--npm/probes/` — post-S7-01 + S7-02 probe modules.
  - `plugins/distroless-migration--node--npm/schema/` — post-S7-03 sub-schemas.
  - `tests/golden/probes/{base_image,shell_invocation_trace}/` — post-S7-03 goldens.
- **Sibling stories:**
  - `S7-01`, `S7-02`, `S7-03`, `S7-04` — all five must be GREEN before this story runs to green.
  - `S8-03-plugin-loader-and-tccm-resolver.md` — depends on this story to confirm probes are wired correctly before adding the loader explicit-import row.

## Goal

Land a test-only story that extends the existing probe-context-conformance fence to cover both new plugin probes (`BaseImageProbe` + `ShellInvocationTraceProbe`); ships a new integration test (`tests/integration/test_probe_outputs_validate_against_envelope.py`) that round-trips each probe's slice through the updated envelope schema and matches against the canonical golden files; verifies `mypy --strict plugins/distroless-migration--node--npm/probes` clean as a directory unit.

## Acceptance criteria

**Probe-context-conformance fence (AC-1 through AC-4)**
- [ ] **AC-1** The existing probe-context-conformance fence file (`tests/fence/test_probe_context_conformance.py` — or the equivalent canonical filename in the current repo) is **extended to import both new plugin probes** — verified by the fence's discovery mechanism picking up `BaseImageProbe` and `ShellInvocationTraceProbe` via the registry (NOT a hardcoded list). The fence's `pytest -v` output shows both probe class names in the parametrize matrix when run after this story. **Read the existing fence file before deciding HOW to extend it** — if the fence uses `Registry.all()` or equivalent, plugin imports may be needed at the fence's top to trigger `@register_probe` side effects; mirror the existing precedent (typically a single `from plugins.distroless_migration_node_npm import api  # noqa: F401` line in the fence's setup, **NOT** in the production loader — the production wiring is S8-03).
- [ ] **AC-2** `BaseImageProbe` passes the conformance fence: two-arg `run(self, repo, ctx)` signature; `name`, `layer`, `tier`, `applies_to_tasks`, `applies_to_languages`, `requires`, `declared_inputs`, `timeout_seconds`, `cache_strategy` are all present + well-typed; the probe does NOT reference a `ProbeContext` attribute outside the ABC's declared set (`cache_dir`, `output_dir`, `workspace`, `logger`, `config`, `parsed_manifest`, `input_snapshot`, `image_digest_resolver`). Verified by the fence's per-probe parametrize assertion.
- [ ] **AC-3** `ShellInvocationTraceProbe` passes the conformance fence + one additional sub-assertion: the probe references `ctx.sandbox_client` (the Phase 5-wired attribute per ADR-0002 §Consequences). Because `sandbox_client` is **not** declared on the Phase 0 ABC, the conformance fence's "no undeclared attribute" rule must include `sandbox_client` in its admitted set (added by S6-02's amendment, mirroring how Phase 1 ADR-0002 / Phase 2 ADR-0004 admitted `parsed_manifest` + `image_digest_resolver`). If S6-02 didn't update the fence's admitted-attribute set, this story makes the addition. **Acceptable byte-edit**: the conformance fence is a test file, not Phase 0–6.5 production; no row #-of-fence-allowlist is consumed.
- [ ] **AC-4** **Planted-violation guard** (parametrized): plant a synthetic probe class with `def run(self, repo): ...` (one-arg) into a `tmp_path` plugin and assert the fence's discovery catches it (parametrize over: one-arg `run`, missing `name`, missing `layer`, drift on `cache_strategy` value). Red-by-construction inside the test suite.

**Envelope-validation integration test (AC-5 through AC-8)**
- [ ] **AC-5** `tests/integration/test_probe_outputs_validate_against_envelope.py` exists. For each of the six base-image fixtures (S7-03 AC-8 through AC-13) and each of the three shell-trace fixtures (S7-03 AC-14 through AC-16), the test:
  1. Constructs a `RepoSnapshot` over the fixture directory.
  2. Constructs a `ProbeContext` with a stub `image_digest_resolver` (for `BaseImageProbe`) or a stub `sandbox_client` returning the canned `SpawnResult` (for `ShellInvocationTraceProbe`).
  3. `await probe.run(repo, ctx)` → captures `ProbeOutput.schema_slice`.
  4. Merges the slice under the envelope's `probes` key: `envelope = {..., "probes": {<probe.name>: schema_slice[<probe.name>]}}`.
  5. Validates `jsonschema.validate(envelope, repo_context_schema)` — assert no `ValidationError`.
  6. Asserts the slice **equals** the golden file (`assert schema_slice == json.load(golden_path)`).
  Parametrized over the nine fixture/golden pairs.
- [ ] **AC-6** **Round-trip Pydantic check** (consumes S7-03 AC-4 models): for each slice, `model_class.model_validate(slice_payload)` round-trips byte-for-byte through `.model_dump(mode="json")`. This is the strong-typed mirror of the JSON-schema check.
- [ ] **AC-7** **Sub-schema isolation check**: the test ALSO validates each slice against its plugin-local sub-schema (`plugins/.../schema/<name>.schema.json`) — not just via the envelope. Catches a case where the envelope `$ref` resolves to a stale schema while the plugin's sub-schema is updated, or vice versa.
- [ ] **AC-8** **Envelope-key coverage**: post-validation, the envelope's `probes` dict contains exactly the two new keys `base_image` and `shell_invocation_trace` (the test constructs an envelope with only these two, validates, then constructs a second envelope with these two PLUS an existing Phase 1 probe slice — e.g., `dockerfile` — and confirms both validate). Pins that the two new `$ref` insertions don't break sibling slice validation.

**`mypy --strict` directory check (AC-9)**
- [ ] **AC-9** `mypy --strict plugins/distroless-migration--node--npm/probes` exits 0 as a directory invocation. A Makefile target addition (e.g., `typecheck-phase7-probes:`) is permitted **if** the existing `make typecheck` already includes `src/codegenie/` but excludes `plugins/`; if so, this story extends `make typecheck` (or adds the new target). **NB:** if extending `make typecheck` requires a byte-edit to the Makefile, this story may consume an unused fence-allowlist row OR add the row via ADR-0009 amendment (one-line story-time decision per **Rule 7**: surface and prefer the additive new target over an in-place `make typecheck` edit). Pinned strategy: **add `typecheck-plugins` as a new target wired into `make check`**; the Makefile already has the discipline of one-target-per-concern (mirror `make fence`, `make lint-imports`). The byte-edit fence treats `Makefile` as in-scope for row #11 if it's not already enumerated — **implementer note**: confirm by reading `tests/fence/test_phase7_no_byte_edits_to_locked_files.py` after S5-01 lands; if `Makefile` is in-scope and not allowlisted, surface as a blocker rather than back-channel-editing.

**Coverage + regression (AC-10 + AC-11)**
- [ ] **AC-10** `make check` green after this story lands. Specifically:
  - All new conformance-fence parametrize rows green.
  - All new envelope-integration parametrize rows green.
  - `mypy --strict` on the plugin probes directory green.
  - Phase 3–6.5 regression suite green (no regression to existing fences caused by extending `test_probe_context_conformance.py`).
  - The byte-edit allowlist fence (S5-01) green — no Phase 0–6.5 file is edited by this story.
- [ ] **AC-11** **Negative-test regression guard**: a deliberately-malformed slice (e.g., `confidence: "extreme"` — not in the enum; or an extra unknown key) is REJECTED by both the sub-schema check (AC-7) and the envelope check (AC-5). Parametrized over three bad-slice mutations per probe. Pins that the schemas are actually strict, not just structurally present.

## Implementation outline

1. **Read the existing conformance fence first.** `ls tests/fence/` and identify the canonical filename (likely `test_probe_context_conformance.py` or `test_probe_context_attribute_conformance.py`). Read it; note the parametrize style; note how it discovers probes (via `Registry.all()` / `default_registry` vs. hardcoded). **Mirror the discovery style** — if it's hardcoded today, decide whether this story refactors to registry-driven (a separate concern; surface as cleanup) or hardcodes the two new probe class names (the cheaper, surgical option per Rule 3). Pinned choice: **hardcode if the existing fence is hardcoded; refactor only if registry-driven is the existing style.**

2. **Extend the conformance fence:**
   - Add import line at the top: `from plugins.distroless_migration_node_npm.probes import base_image_probe, shell_trace_probe  # noqa: F401  -- side-effect register`. (This is the test-only import; the production loader's import row is S8-03.)
   - If the fence's admitted-`ProbeContext`-attribute set is a `Final` frozenset, add `"sandbox_client"` to it (acceptable byte-edit of a test file; surface in `_attempts/` if the set lives in `src/codegenie/`-side code rather than the test).
   - Add parametrize rows for both probe class names (or rely on auto-discovery if the existing fence works that way).

3. **Write `tests/integration/test_probe_outputs_validate_against_envelope.py`:**
   ```python
   import json
   from pathlib import Path
   import pytest
   import jsonschema

   from plugins.distroless_migration_node_npm.probes import base_image_probe, shell_trace_probe
   # ... etc.

   _GOLDENS_BASE_IMAGE = [
       ("distroless-target", Path("tests/fixtures/portfolio/node-distroless-target")),
       ("alpine", Path("tests/fixtures/portfolio/node-vulnerable-alpine")),
       # ... six total
   ]
   _GOLDENS_SHELL_TRACE = [
       ("distroless-target", Path("tests/fixtures/portfolio/node-distroless-target"),
        sandbox_stubs.SUCCESS_NO_SHELL),
       # ... three total
   ]

   @pytest.mark.parametrize("name,fixture", _GOLDENS_BASE_IMAGE)
   async def test_base_image_slice_validates(name, fixture, envelope_schema, sub_schemas, ctx_factory):
       probe = base_image_probe.BaseImageProbe()
       ctx = ctx_factory(image_digest_resolver=_stub_resolver_for(fixture))
       repo = _repo_snapshot_for(fixture)
       output = await probe.run(repo, ctx)
       slice_payload = output.schema_slice
       # 1. sub-schema validates
       jsonschema.validate(slice_payload["base_image"], sub_schemas["base_image"])
       # 2. envelope validates with the slice merged in
       envelope = {"probes": {"base_image": slice_payload["base_image"]}}
       jsonschema.validate(envelope, envelope_schema)
       # 3. golden matches
       expected = json.loads(Path(f"tests/golden/probes/base_image/{name}.json").read_text())
       assert slice_payload == expected
   ```
   Mirror for shell_invocation_trace; parametrize over the three stub `SpawnResult` instances.

4. **Negative-test rows:**
   ```python
   @pytest.mark.parametrize("mutation", [
       {"confidence": "extreme"},
       {"unexpected_key": True},
       {"dockerfiles": "not-a-list"},
   ])
   def test_malformed_base_image_slice_rejected(mutation, sub_schemas, envelope_schema):
       # take a valid golden, mutate, assert validation fails
       ...
   ```

5. **Makefile / typecheck wiring (AC-9):**
   - Check `Makefile`'s `typecheck:` target. If it's `mypy --strict src/`, this story adds a parallel target:
     ```makefile
     typecheck-plugins:
         mypy --strict plugins/distroless-migration--node--npm/probes plugins/distroless-migration--node--npm/schema
     ```
     and wires it into `make check`.
   - **If editing `Makefile` is gated by the byte-edit fence and `Makefile` is in the locked set**, surface immediately and either add a row via ADR-0009 amendment OR use a per-story local invocation in CI (less ideal — surface as cleanup).

6. **Run** `make check` end-to-end; record evidence in `_attempts/S7-05.md` (parametrize matrix results + Phase 3–6.5 regression-suite green).

## TDD plan (red → green → refactor)

**Red 1** — write `test_probe_outputs_validate_against_envelope.py::test_base_image_slice_validates[distroless-target-...]`. Pytest fails: module not found or fixture-stub not wired.

**Green 1** — write the stub `_repo_snapshot_for` + `_stub_resolver_for` helpers; import the probe; run the probe; assert validation. Iterate one fixture row at a time.

**Red 2** — `test_shell_invocation_trace_slice_validates[no-trace-available-...]`. Fails because `image_digest` is null in the golden but the schema (per S7-03 AC-16) admits null OR `"sha256:..."`. Verify the schema actually accepts null in the no-trace case (S7-03 pinned this); fix if not.

**Green 2** — schemas accept; slice validates; golden matches.

**Red 3** — `test_malformed_base_image_slice_rejected[mutation-1]`. Fails because the parametrize matrix doesn't exist yet.

**Green 3** — write the negative tests; verify the schemas reject each mutation with a `jsonschema.ValidationError`.

**Red 4** — extend the conformance fence; the parametrize for `BaseImageProbe` runs; assertion fails if the probe drifted on any ABC attribute.

**Green 4** — confirm AC-2 / AC-3 holds (the probes already conform from S7-01 / S7-02; if not, surface as a S7-01/S7-02 bug to fix BEFORE landing this story).

**Refactor** — extract `envelope_schema` + `sub_schemas` to a `conftest.py` fixture so the parametrize doesn't re-load JSON. **Do not** extract a `ProbeIntegrationHarness` class — Rule 2 says minimum code; the helpers are inline functions.

## Files to touch

**New files:**
- `tests/integration/test_probe_outputs_validate_against_envelope.py`
- `tests/integration/conftest.py` (or extension of an existing conftest; provides `envelope_schema`, `sub_schemas`, `ctx_factory` fixtures)
- `tests/unit/plugins/distroless_migration_node_npm/probes/test_conformance_extension.py` (if the existing fence needs additional plugin-side tests beyond its core parametrize)

**Edited files (test-only, no Phase 0–6.5 production edits):**
- `tests/fence/test_probe_context_conformance.py` (or the canonical existing name) — adds plugin probe imports + parametrize rows.
- `Makefile` — adds `typecheck-plugins` target wired into `make check`. **NB**: if `Makefile` is locked by S5-01's fence and no row admits this story, this AC is a blocker — surface and resolve before landing.

**Files NOT touched** (would violate the byte-edit allowlist): `src/codegenie/probes/base.py`, `src/codegenie/schema/repo_context.schema.json` (S7-03 already consumed row #4), `src/codegenie/exec/__init__.py` (S7-04 consumed row #8), `pyproject.toml` (S7-04 consumed row #9), `src/codegenie/plugins/loader.py` (S8-03 owns row #10).

## Out of scope

- **The production loader explicit-import** (`src/codegenie/plugins/loader.py` row #10) — S8-03 owns. This story uses test-side imports for fence + integration assertion; the production load path lands in S8-03.
- **The `plugin.yaml` manifest** — S8-01 owns.
- **TCCM `derived_queries:`** — S8-02 + S8-03 own.
- **End-to-end migration tests** — S12-02 (`test_distroless_migration_e2e.py`) and S12-03 (`test_both_provenance_emits_coordination_event_e2e.py`) own; this story stops at slice-validates-envelope, not full migration.
- **Real `docker buildx` invocation** — S7-02's tests use stub `SandboxClient`s; this story's integration test continues that. The real Docker invocation lands at the e2e layer (S12-02) with `@pytest.mark.phase07_e2e` and `--privileged` runners.
- **Performance benchmarks** — S12-05 owns `@pytest.mark.bench` perf tests for both probes.

## Notes for the implementer

- **Rule 8 — read before you write.** The existing `tests/fence/test_probe_context_conformance.py` (or canonical name) is the precedent. **Read its parametrize style, attribute-set discipline, and discovery mechanism before deciding how to extend it.** Forking the discovery style breaks Rule 11.
- **Rule 9 — tests verify intent.** Each parametrize row must encode "why" — `test_base_image_slice_validates[unknown.json]` should comment-include "// reason: `kind=unknown` carries typed `reason` per S7-03 AC-12". Bare `assert slice == golden` without intent is brittle to regenerated goldens; the comment is the load-bearing audit trail.
- **Rule 12 — fail loud.** The negative tests (AC-11) are the load-bearing fence-of-the-fence: they prove the schemas are actually strict. **Plant the malformations in a tmp-path golden copy, NOT in the real golden file** — a slip will commit garbage to `tests/golden/`.
- **The conformance fence's "no undeclared `ProbeContext` attribute" rule is the supply-chain hygiene line.** A future plugin probe that reaches for `ctx.openai_client = ...` would silently widen the trust boundary; the fence rejects it. `ctx.sandbox_client` is admitted by ADR-0002 + S6-02; this story's AC-3 is the codification.
- **`jsonschema` library version**: the repo currently uses Draft 2020-12 per S7-03's `$schema` choice. Verify `jsonschema>=4.18` is in the dev-deps; `pip show jsonschema`. If not, **do not** add it in this story — surface as a setup gap.
- **`async def` test discipline**: pytest config has `asyncio_mode = "auto"` (per CLAUDE.md); declare the probe-running tests as `async def` without `@pytest.mark.asyncio`.
- **The `ctx_factory` fixture is reusable.** Build it to take `**overrides` and return a `ProbeContext` with the rest stubbed; downstream stories (S10-04, S10-05) will need the same shape for their gate tests. **Do not over-extract though** — a single `conftest.py`-level fixture is enough; don't build a "test harness" Python library.
- **Parametrize over fixture+golden pairs, not over probes**. Nine rows total (six base-image + three shell-trace). Each row's `id=` is the fixture name (e.g., `"distroless-target"`). This makes pytest output readable: a failing row's name immediately tells the reader which fixture broke.
- **Phase 3–6.5 regression-cassette check is mandatory.** Even though this story is test-only, the extended conformance fence walks the registry; if the registry now has more probes than before, a cassette-replay test that pickled the registry state could diverge. Run the cassette replay (`bench/vuln-remediation/cassettes/`) and record byte-equality (ε ≤ $0.01) in `_attempts/S7-05.md`.
- **Token budget (Rule 6)**: this story is ≤ 2k tokens to implement. If you're approaching 3k, you're either rewriting the existing conformance fence (out of scope — surface as cleanup) or over-decomposing the parametrize. Keep it flat; nine rows, one parametrize call per probe.
- **Story-step closure**: when this story is GREEN, Step 7 is closed and S8-01 can pick up the plugin manifest. Update the step-7 status in the manifest README's per-step status (the executor handles this).
