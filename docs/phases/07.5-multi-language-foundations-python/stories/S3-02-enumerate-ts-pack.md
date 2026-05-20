# Story S3-02 — Fully enumerate `TS_PACK` (Gap 2)

**Step:** Step 3 — Retrofit TypeScript as `LanguagePack` #1 (by reference)
**Status:** Ready
**Effort:** M
**Depends on:** S3-01, S3-03
**ADRs honored:** ADR-0006, ADR-0003, ADR-0001, ADR-0002

## Context
The phase's headline proof — "Python is `LanguagePack` #2, which validates the abstraction" — requires a *real, completely enumerated* `LanguagePack` #1. The architect's Gap 2 flags that the design names `TS_PACK` but never specifies four of its seven fields, and the registry-drift test (S3-04) that proves the retrofit is honest *depends* on `TS_PACK.layer_a_probes` being complete. This story constructs `TS_PACK` with every field explicitly enumerated — `layer_a_probes` verified against the actual Phase 1 imports in `codegenie/probes/__init__.py` — and registers it `probes_self_registered=True`.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Gap analysis & improvements §Gap 2` — the under-specified `TS_PACK`; the mandate to enumerate it as a concrete deliverable, not "retrofit by reference" for the field set.
- **Architecture:** `../phase-arch-design.md §Component design — LanguagePack` — the seven fields and their types.
- **Phase ADRs:** `../ADRs/0006-typescript-retrofit-by-reference-probes-self-registered.md` — ADR-0006 — `probes_self_registered=True`; no probe fan-out; `layer_a_probes` records the Phase 1 Layer-A probe classes for conformance to consume.
- **Phase ADRs:** `../ADRs/0003-grammars-modeled-one-to-many-relation.md` — ADR-0003 — `grammars=("typescript", "tsx", "javascript")`; `language=Language("typescript")`.
- **Phase ADRs:** `../ADRs/0001-languagepack-total-frozen-value-contract-and-freeze.md` — ADR-0001 — `LanguagePack` is the total frozen value; an incomplete construction is a `mypy --strict` error.
- **Phase ADRs:** `../ADRs/0002-register-language-validate-all-then-commit-no-unregister.md` — ADR-0002 — `register_language` validates then commits; idempotent per `Language`.
- **Source design:** `../final-design.md §Synthesis ledger` — CR-2 (the retrofit seam), CR-7 (the `grammars` one-to-many).
- **Existing code:** `src/codegenie/probes/__init__.py` — the Phase 1 explicit-import block; the source of truth for *which* Layer-A probe classes exist.
- **Existing code:** `src/codegenie/probes/language_detection.py`, `node_build_system.py`, `node_manifest.py`, `test_inventory.py`, `ci.py`, `deployment.py` — the six classes with `layer = "A"` (`LanguageDetectionProbe`, `NodeBuildSystemProbe`, `NodeManifestProbe`, `TestInventoryProbe`, `CIProbe`, `DeploymentProbe`).
- **Existing code:** `src/codegenie/grammars/lock.py` — `SupportedLanguage` `Literal`; `supported_languages()` (used by `validate_pack`'s grammar-wired check).
- **Existing code (this phase):** `src/codegenie/languages/typescript_detector.py` (S3-03) — the `project_detector` field value; `src/codegenie/languages/packs/__init__.py` (S3-01) — the collection point.

## Goal
Construct `TS_PACK` with all seven `LanguagePack` fields explicitly enumerated and call `register_language(TS_PACK)` at the import of `packs/typescript.py`.

## Acceptance criteria
- [ ] The TDD red test exists, is committed, and is green: `tests/unit/languages/test_ts_pack.py` asserts `register_language(TS_PACK)` succeeds and `default_language_registry.all() == (TS_PACK,)` after importing `codegenie.languages.packs`.
- [ ] `TS_PACK.layer_a_probes` is enumerated against `codegenie/probes/__init__.py` — a test asserts `set(TS_PACK.layer_a_probes)` equals the set of probe classes with `layer == "A"` reachable from `probes/__init__.py` (the implementer makes the deliberate inclusion decision and the test pins it; see Notes).
- [ ] `TS_PACK.grammars == ("typescript", "tsx", "javascript")`; `TS_PACK.language == Language("typescript")`; `TS_PACK.probes_self_registered is True`.
- [ ] `TS_PACK.project_detector` is the real `TypeScriptProjectDetector` (S3-03); `TS_PACK.search_adapter_module` resolves (`validate_pack`'s adapter-import check passes).
- [ ] Registering `TS_PACK` performs **no probe fan-out** — a test asserts the probe registry (`default_registry.all_probes()`) is byte-identical before and after `register_language(TS_PACK)` (ADR-0006: `probes_self_registered=True` skips the fan-out).
- [ ] `packs/__init__.py` gains exactly one additive line `from codegenie.languages.packs import typescript  # noqa: F401 — registration` (no other edit to that file).
- [ ] No Phase 1–7 shipped file is edited (`git diff` is confined to `codegenie/languages/` + tests + the one `packs/__init__.py` import line).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest`, `make fence`, `make lint-imports` all pass; the full Node/TypeScript regression suite stays green.
- [ ] Status set to `Done` on completion.

## Implementation outline
1. Read `src/codegenie/probes/__init__.py` and the six `layer = "A"` modules. Enumerate the Phase 1 Layer-A probe classes: `LanguageDetectionProbe`, `NodeBuildSystemProbe`, `NodeManifestProbe`, `TestInventoryProbe`, and decide on `CIProbe` / `DeploymentProbe` inclusion (see Notes — they are `layer = "A"`; the architect text names the first four but `CIProbe`/`DeploymentProbe` also carry `layer = "A"`; resolve deliberately and document the choice).
2. Create `src/codegenie/languages/packs/typescript.py`: import the probe classes, the `TypeScriptProjectDetector`, `Language`, and construct `TS_PACK = LanguagePack(language=..., grammars=("typescript","tsx","javascript"), project_detector=TypeScriptProjectDetector(), layer_a_probes=(...), dep_graph_strategies={...}, search_adapter_module="...", probes_self_registered=True)`.
3. Populate `dep_graph_strategies` with the Node strategy(ies) keyed by their `PackageManager` — verify against `codegenie/depgraph/registry.py` and the Node plugin manifest which Node strategies exist; if none are pack-owned, an empty `Mapping` is the honest value (note the decision; ties to Open Question 6 / Gap 1).
4. Set `search_adapter_module` to the existing Node search-adapter `"module:ClassName"` import path (verify it resolves — `validate_pack` will import-check it).
5. At module bottom, call `register_language(TS_PACK)`.
6. Add the one additive import line to `packs/__init__.py`.
7. Run the full regression suite + `make fence` + `make lint-imports`.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_ts_pack.py`.
Test name: `test_ts_pack_registers_and_is_only_language` — importing `codegenie.languages.packs` registers exactly `TS_PACK` and nothing else at this step.
```python
# arrange: ensure codegenie.languages.packs is imported (the import fires register_language)
# act: registered = default_language_registry.all()
# assert: registered == (TS_PACK,)   # exactly one pack at Step 3
#   intent: TS_PACK is a real, registered LanguagePack #1 before Python exists
```
Add `test_ts_pack_layer_a_probes_match_phase1_imports` — collect every probe class with `layer == "A"` reachable from `codegenie.probes.__init__` and assert `set(TS_PACK.layer_a_probes)` equals that set (encodes Gap 2: the tuple is *deliberately* complete, not partial — a future Phase-1 Layer-A probe must force this test red).
Add `test_ts_pack_registration_does_not_fan_out_probes` — snapshot `default_registry.all_probes()`, call `register_language(TS_PACK)` a second time (idempotent), assert the probe set is unchanged (ADR-0006: `probes_self_registered=True` ⇒ no fan-out, ADR-0002: idempotent).
Add `test_ts_pack_fields_enumerated` — assert `grammars`, `language`, `probes_self_registered`, and that `project_detector` is a `TypeScriptProjectDetector` and `search_adapter_module` import-resolves.
All fail before `packs/typescript.py` exists.

### Green — make it pass
Write `packs/typescript.py` constructing `TS_PACK` with every field and calling `register_language(TS_PACK)`; add the one import line to `packs/__init__.py`. `validate_pack` runs inside `register_language` — fix any grammar-wired / adapter-resolve failure surfaced.

### Refactor — clean up
Add a module docstring stating `TS_PACK` is `LanguagePack` #1, retrofitted by reference (ADR-0006), and that the field set was enumerated deliberately against `probes/__init__.py` (Gap 2). Confirm `layer_a_probes` is a `tuple` (frozen-value discipline). Make the `layer_a_probes`-vs-imports test the *living* documentation of the inclusion decision — a comment in the test naming why `CIProbe`/`DeploymentProbe` are in or out.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/languages/packs/typescript.py` | New — constructs `TS_PACK` and calls `register_language(TS_PACK)`. |
| `src/codegenie/languages/packs/__init__.py` | One additive `import typescript` line (registration trigger). |
| `tests/unit/languages/test_ts_pack.py` | Red tests: registers, layer-A enumeration, no fan-out, fields. |

## Out of scope
- The registry-drift test (`default_registry` ⊇ union of packs' `layer_a_probes`) — that is S3-04.
- `PYTHON_PACK` and the second `EXPECTED_LANGUAGE_COUNT` — S7-01.
- Any new probe, grammar, or dep-graph strategy — TypeScript's are all already shipped.
- Editing `LanguageDetectionProbe` or any Phase 1 probe — ADR-0006/ADR-0043 forbid it.

## Notes for the implementer
- **Gap 2 is the whole point of this story.** Do not leave `layer_a_probes` partial — enumerate it deliberately and pin it with a test that goes red if Phase 1's Layer-A probe set ever changes. "Retrofit by reference" applies to *registration history*, never to the field set.
- The architect text (Gap 2 / ADR-0006) names `LanguageDetectionProbe, NodeBuildSystemProbe, NodeManifestProbe, TestInventoryProbe` — but `CIProbe` and `DeploymentProbe` also carry `layer = "A"` in the shipped code. This is a genuine inclusion decision: `layer_a_probes` is consumed only by conformance and the drift test, so the safest reading is *every shipped `layer == "A"` probe class*. Make the call, document it in the test comment, and ensure the S3-04 drift test's "at least the union" framing still holds either way.
- `probes_self_registered=True` means `register_language(TS_PACK)` must NOT call `register_probe` — re-registering an already-registered Phase 1 probe raises `ProbeError` (ADR-0006). Verify the no-fan-out test actually exercises this path.
- `dep_graph_strategies` for `TS_PACK`: verify against `codegenie/depgraph/registry.py` whether Node strategies are pack-owned or were registered elsewhere (Gap 1 / Open Question 6). An empty `Mapping` is acceptable and honest if no Node strategy is pack-scoped — do not invent strategy references.
- `search_adapter_module` must be a real `"module:ClassName"` path that imports — `validate_pack` import-checks it; a typo is a `LanguageRegistryError` at registration.
- The full Phase 1–7 regression suite (~2,300 tests) must stay green — this story adds nothing to shipped behavior, so any regression means a fan-out or import side effect leaked.
