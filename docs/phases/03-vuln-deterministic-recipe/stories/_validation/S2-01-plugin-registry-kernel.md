# Validation report — S2-01 — PluginRegistry kernel + Plugin/Adapter/RecipeEngine Protocols

**Validated:** 2026-05-18
**Validator:** phase-story-validator skill (autonomous run via story-validation-corrector scheduled task)
**Verdict:** **HARDENED**
**Story file:** `docs/phases/03-vuln-deterministic-recipe/stories/S2-01-plugin-registry-kernel.md`

---

## Context brief

S2-01 ships the **kernel** of the Phase 3 plugin architecture (ADR-0002, ADR-0004, ADR-0031): three `Protocol`s (`Plugin`, `Adapter`, `RecipeEngine`) in `protocols.py`, one `PluginRegistry` class + module-level `default_registry: Final[PluginRegistry]` instance + `register_plugin(plugin, *, registry=None) -> Plugin` helper in `registry.py`, typed exceptions in `errors.py`, and a fence test that pins `Plugin`'s four-member surface (ADR-0004).

This is the **4th** decorator-registry in the codebase (after `probes/registry.py`, `indices/registry.py`, `depgraph/registry.py`). The closed-for-modification kernel anchors every Phase 3+ plugin; Phase 7 distroless lands as a new directory + decorator call with zero kernel edits.

**Load-bearing context:**
- ADR-0002 §Decision: instance-with-default-singleton + fixture isolation; "kernel must stay tiny — no eager validation, no side effects at registration."
- ADR-0004 §Consequences: `Plugin` Protocol surface is **exactly four** members (`manifest`, `build_subgraph`, `adapters`, `transforms`); fence test asserts the count.
- ADR-0010 §Decision: `PluginId` newtype mandatory; no raw `str` for domain IDs.
- High-level-impl.md Step 2 done-criteria is the **union** of S2-01..S2-04 — S2-01 owns only the kernel surface.
- Sibling precedent: `src/codegenie/probes/registry.py` is the mirror; `_validation/S1-10-depgraph-strategy-registry.md` is the most recent registry-kernel validation framing.

**Original story strengths:**
- Correctly cited ADR-0002 / ADR-0004 / ADR-0010 across Context, Notes, and ACs.
- Out-of-scoped manifest model (S2-02), loader (S2-03), resolver (S2-04) cleanly.
- Mirrored `probes/registry.py` discipline in Notes §2 verbatim.
- Named cross-test isolation as the load-bearing assertion ADR-0002 §Consequences enumerates.
- Picked the right TDD red test (`test_collision_raises`).

**Original story weaknesses (resolved here):**
- `resolve()` returned `PluginResolution`, but `PluginResolution` is an S2-04 deliverable per `S1-03-tagged-union-outcomes.md:378` — a hard symbol contradiction at `mypy --strict` time.
- Many ACs were prose-only ("register one / register two") with no concrete test bodies or assertions; mutation-resistance was thin (Test-Quality F1, F2, F3, F4, F5, F6).
- AC-6 fence-test mechanism cited `Plugin.__abstractmethods__`, which `Protocol` (especially `@runtime_checkable`) does not populate the way ABCs do — the test as written would either fail or trivially pass.
- `register_plugin(plugin)` (no `registry=` kwarg) default path was named but not tested — a regression could land `(registry).register(plugin)` and crash silently on the singleton path.
- `register_plugin` return-identity (`is plugin`) not asserted — `return None` mutant passes the rest.
- `PluginAlreadyRegistered` / `PluginNotRegistered` typed `.name` attribute not specified — string `args[0]` match is tautological with the hardcoded fixture name.
- Cross-test pollution assertion was half-specified (negative control only — passes trivially if `all()` is broken to return `()`).
- `tests/fence/` directory does not yet exist (S2-01 is the first story to populate it); no AC creates `__init__.py`.
- `make_fake_plugin` fixture spec was omitted entirely — executor would improvise, risking `mypy --strict` failure on `Plugin.manifest: PluginManifest` typing.
- `Adapter` Protocol's surface was described as "one or two methods" — half-specified; downstream fixtures would diverge.
- 4th-registry rule-of-three observation not recorded; the `depgraph/registry.py:30-38` precedent of *explicitly documenting* the deferred extract was not carried forward.
- `register` return type `-> Plugin` (story) vs `-> None` (arch C2 line 466) divergence not flagged.
- `all() -> tuple[Plugin, ...]` (story) vs `-> list[Plugin]` (arch C2 line 469) divergence not flagged.
- `@register_plugin` non-decorator shape's *rationale* (plugins are instances, not classes) not articulated — reviewers would assume it's an oversight vs. the three sibling dual-shape decorators.

---

## Stage 2 — Four critic reports

### Coverage critic — 10 findings

| ID  | Severity | Title                                                                | Resolution                                                                                                                                       |
| --- | -------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| F1  | harden   | Four-member fence-test method ambiguous                              | Applied — AC-7 pins `dir(Plugin) - dunders` + `__annotations__["manifest"]` (NOT `__abstractmethods__`)                                          |
| F2  | harden   | `register_plugin(plugin)` default-registry path not asserted         | Applied — AC-10 (default-singleton smoke) + autouse cleanup fixture in `conftest.py`                                                             |
| F3  | harden   | `register_plugin` return-value identity not tested                   | Applied — AC-3 strengthened: `register_plugin(p, registry=r) is p`                                                                               |
| F4  | harden   | `resolve()` stub message + exception type not pinned                 | Applied — AC-2 names `NotImplementedError` + literal substring `"S2-04"` in message                                                              |
| F5  | harden   | `all()` order assertion too thin (two elements + hash-coincidence)   | Applied — AC-5 mandates three-element identity-tuple assertion with names whose alphabetic ≠ insertion order                                     |
| F6  | harden   | `PluginAlreadyRegistered` / `PluginNotRegistered` typed `.name`      | Applied — AC-4 mandates `.name: PluginId` attribute + tests assert `exc.name == ...` (composes with Test-Quality F4/F6)                          |
| F7  | harden   | `@runtime_checkable` not exercised behaviorally                      | Applied — AC-8 (isinstance smoke) requires `isinstance(make_fake_plugin(), Plugin)` and asymmetry checks                                         |
| F8  | harden   | `Adapter` / `RecipeEngine` surfaces not frozen                       | Applied via Out-of-scope clarification — `Adapter` reduced to single attribute `primitive: PrimitiveName` (no methods this story); `RecipeEngine` surface named precisely; freezing deferred to S5/S7 |
| F9  | nit      | Cross-test pollution needs positive control                          | Applied — AC-6 (cross-test isolation) mandates BOTH halves: registry A contains its plugin; registry B is empty; `default_registry` snapshot eq |
| F10 | nit      | Out-of-scope omits concurrency / re-import                           | Applied — Out-of-scope expanded with concurrency + module-reload paragraphs                                                                      |

### Test-Quality critic — 10 findings

| ID  | Severity | Title                                                              | Resolution                                                                                                                                                                       |
| --- | -------- | ------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F1  | harden   | `all()` ordering test absent; `return ()` mutant survives          | Applied — concrete TDD test `test_all_returns_registration_order` pinned with identity-tuple equality on three distinct names                                                    |
| F2  | harden   | Default-registry path untested                                     | Applied — TDD test `test_register_plugin_default_singleton_path` with autouse `restore_default_registry` fixture (mirrors `tests/unit/test_registry.py` precedent)                |
| F3  | harden   | `register_plugin` return-identity untested                         | Applied — TDD test `test_register_plugin_returns_plugin_unchanged` asserts `register_plugin(p, registry=r) is p`                                                                  |
| F4  | harden   | Collision-message assertion tautological                           | Applied — `PluginAlreadyRegistered` exposes typed `.name: PluginId` + message names both colliding `{module}.{qualname}` (mirrors `probes/registry.py:154-158`)                  |
| F5  | harden   | Cross-test pollution half-specified                                | Applied — AC-6 + concrete TDD test `test_fresh_registries_are_isolated` with both positive and negative assertions                                                                |
| F6  | harden   | `get(unknown)` typed payload untested                              | Applied — TDD test `test_get_unknown_raises_plugin_not_registered_with_typed_name` asserts `exc.name == PluginId(...)`                                                            |
| F7  | nit      | `resolve()` "S2-04" substring untested                             | Applied — `pytest.raises(NotImplementedError, match="S2-04")`                                                                                                                     |
| F8  | block    | `make_fake_plugin` fixture spec missing                            | Applied — Implementation outline §0 pins the fixture as a frozen dataclass with a `_FakeManifest(name: PluginId)` field; explicitly listed in Files-to-touch                     |
| F9  | nit      | Property-based ordering test would harden vs. dict-rehash mutants  | Deferred — F1's three-element identity-tuple test catches the dominant mutants; surfaced in Notes §"Optional property test" as available cheap upgrade if executor has budget    |
| F10 | harden   | Fence-test introspection method underspecified                     | Applied — AC-7 explicitly forbids `__abstractmethods__` and pins `dir(Plugin) - dunders == {manifest, build_subgraph, adapters, transforms}` + `'manifest' in __annotations__`   |

### Consistency critic — 10 findings

| ID  | Severity | Title                                                                            | Resolution                                                                                                                                                                                                |
| --- | -------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F1  | block    | `PluginResolution` referenced before it ships (S2-04 owns it)                    | Applied — AC-9 adds `src/codegenie/plugins/resolution.py` shipping a minimal `class PluginResolution: ...` placeholder; S2-04 expands to the `ConcreteResolution \| UniversalFallbackResolution` sum type |
| F2  | harden   | `register` return type contradicts arch (`-> None` in arch, `-> Plugin` in story) | Applied — Notes §3 acknowledges divergence; story tightens per `probes/registry.py:139` precedent; arch C2 line 466 marked as follow-up cleanup                                                          |
| F3  | nit      | `all()` return type tuple vs list                                                | Applied — Notes §3 acknowledges divergence; story's `tuple` is correct per immutability convention + `probes/registry.py:189` precedent                                                                  |
| F4  | nit      | `default_registry: Final` divergence from precedent                              | Applied — Notes §2 names `Final` as intentional per ADR-0002 §Consequences; tighter than precedent on purpose                                                                                              |
| F5  | block    | `tests/fence/` directory does not yet exist                                      | Applied — Files-to-touch now includes `tests/fence/__init__.py` (empty marker); Implementation outline §6 names "first story to populate `tests/fence/`"                                                  |
| F6  | harden   | `PluginManifest` forward-ref shape under `from __future__ import annotations`    | Applied — AC-7 pins `'manifest' in Plugin.__annotations__` semantics; forward-ref expected to be the string `"PluginManifest"` at runtime, sufficient for the fence-test contract                          |
| F7  | harden   | Cross-test pollution mechanism not specified                                     | Applied — AC-6 + Notes §4 pin the snapshot mechanism: autouse session-fixture captures `default_registry.all()` at session start and re-asserts equality at session end                                  |
| F8  | harden   | Goal names `Adapter` / `RecipeEngine` but only `Plugin` is frozen                | Applied — Goal text amended; explicit "freezing deferred to S5/S7" added to Out-of-scope; `Adapter` reduced to single attribute (no methods this story)                                                  |
| F9  | harden   | `make_fake_plugin(name=str)` risks raw-`str` leak to `PluginId`-typed paths      | Applied — fixture spec mandates `_FakeManifest(name=PluginId(name))` wrap inside the helper; `PluginId(...)` lift is at exactly one boundary                                                              |
| F10 | nit      | Step 2 done-criteria is union of S2-01..S2-04, not S2-01 alone                   | Applied — Context paragraph clarified; Notes §7 names the union scope                                                                                                                                     |

### Design-Patterns critic — 6 findings

| ID  | Severity | Title                                                                                                | Resolution                                                                                                                                                                                                                                                                                  |
| --- | -------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F1  | harden   | Rule-of-three (now four) kernel-extract observation not recorded                                     | Applied — Notes §"Rule-of-three observation" added (mirrors `depgraph/registry.py:30-38` verbatim); module docstring in `plugins/registry.py` will carry the same paragraph; extract still deferred (Rule 2 — resolve-machinery dominates LOC); trigger pinned: "lift at N=5 or shared-surface need" |
| F2  | nit      | `@register_plugin` non-decorator asymmetry not justified                                             | Applied — Notes §3 rewritten: plugins are *instances* (carry manifest + state), not classes — class-decorator shape doesn't compose; asymmetry is intentional, not oversight; ADR-0002 §Decision is the authority                                                                            |
| F3  | harden   | `Adapter` Protocol surface "one or two methods" is half-specified                                    | Applied — Implementation outline §3 reduces `Adapter` to a single attribute `primitive: PrimitiveName` (no methods this story); surface freeze deferred to S7 when adapters carry real responsibility; Out-of-scope explicitly names this deferral                                            |
| F4  | harden   | Cross-test isolation idiom not pinned                                                                | Applied — Notes §4 pins snapshot-based assertion; sibling precedent `indices/registry.py:198-208`'s `unregister_for_tests()` is referenced as the next-step-if-needed marker                                                                                                                 |
| F5  | nit      | AC-3 "decorator-style helper" wording is misleading (plugins aren't classes)                         | Applied — AC-3 rewritten: "returns the plugin unchanged so a plugin's `api.py` can chain it (`PLUGIN = register_plugin(MyPlugin())`)"                                                                                                                                                       |
| F6  | nit      | `__slots__` + `@runtime_checkable` decisions are correct YAGNI applications — recorded for context  | No change required — kept as Notes §"Deliberately not adopted" so future PRs don't second-guess.                                                                                                                                                                                            |

---

## Stage 3 — Researcher

**Not invoked.** No critic finding was tagged `NEEDS RESEARCH`. All resolutions reuse this codebase's existing precedents (`probes/registry.py`, `indices/registry.py`, `depgraph/registry.py`, the three S1-* validation reports) and Python-runtime semantics (`Protocol` introspection).

---

## Stage 4 — Edits applied to story

The story file was rewritten in place with surgical edits. Summary of structural changes:

1. **Context paragraph** clarified to name S2-01 as the *kernel split* — covering `register` / `get` / `all` + Protocol declarations + cross-test isolation; `resolve()` ships with a placeholder return type that S2-04 expands. Step 2 done-criteria scope (union of S2-01..S2-04) named explicitly.
2. **Goal** amended — only `Plugin` Protocol surface is fence-frozen; `Adapter` shipped with a single attribute (no methods); `RecipeEngine` shipped with named methods stubbed for Step 5; full freezes deferred to S5/S7.
3. **Acceptance criteria** restructured (11 ACs, each verifiable):
   - AC-1: Protocol declarations (`Plugin` four members; `Adapter` single attribute; `RecipeEngine` named-method surface).
   - AC-2: `PluginRegistry` public surface — `register(plugin) -> Plugin`, `get(name: PluginId) -> Plugin`, `all() -> tuple[Plugin, ...]`, `resolve(scope: "PluginScope") -> "PluginResolution"`; `resolve` raises `NotImplementedError` and `"S2-04"` substring must appear in `str(exc)`.
   - AC-3: `register_plugin(plugin, *, registry: PluginRegistry | None = None) -> Plugin` — returns `plugin` (identity, tested with `is`); `registry=None` mutates `default_registry`.
   - AC-4: typed exceptions — `PluginAlreadyRegistered.name: PluginId`, `PluginNotRegistered.name: PluginId`; collision message names both colliding `{module}.{qualname}` registrations.
   - AC-5: `all()` returns insertion order — three-plugin identity-tuple equality test with names where alphabetic ≠ insertion order.
   - AC-6: cross-test isolation — both positive (registry A contains its plugin) and negative (fresh registry B is empty) controls + session-scoped `default_registry.all()` snapshot equality assertion.
   - AC-7: fence test — `{n for n in dir(Plugin) if not n.startswith('_')} == {'manifest', 'build_subgraph', 'adapters', 'transforms'}` AND `'manifest' in Plugin.__annotations__`; explicitly does NOT use `__abstractmethods__`.
   - AC-8: runtime-checkable smoke — `isinstance(make_fake_plugin(), Plugin) is True`; `isinstance(object(), Plugin) is False`.
   - AC-9: `src/codegenie/plugins/resolution.py` ships a minimal placeholder `class PluginResolution: ...` (S2-04 expands to the sum-type variants); allows `resolve` return-type annotation to resolve under `mypy --strict`.
   - AC-10: default-singleton smoke — `register_plugin(plugin)` (no `registry=` kwarg) places plugin in `default_registry.all()`; teardown removes it.
   - AC-11: `ruff check`, `ruff format --check`, `mypy --strict` clean on the new modules + tests.
4. **Implementation outline** restructured into 8 numbered steps (was 7); explicit `tests/fence/__init__.py` creation; explicit `make_fake_plugin` fixture spec; concrete fence-test mechanism.
5. **TDD plan** expanded — single red test preserved; named follow-on tests (`test_all_returns_registration_order`, `test_register_plugin_returns_plugin_unchanged`, `test_register_plugin_default_singleton_path`, `test_get_unknown_raises_plugin_not_registered_with_typed_name`, `test_resolve_stub_names_s2_04`, `test_runtime_checkable_protocols_match_fakes`, `test_fresh_registries_are_isolated`) each pinned with concrete assertion shape.
6. **Files to touch** expanded — adds `tests/fence/__init__.py`, `tests/fixtures/plugins/__init__.py`, `src/codegenie/plugins/resolution.py`.
7. **Out of scope** expanded — adds concurrency, module-reload, `Adapter`/`RecipeEngine` surface freeze deferrals.
8. **Notes for the implementer** restructured with eight subsections:
   - §1 Kernel-must-stay-tiny (unchanged).
   - §2 Mirror `probes/registry.py` discipline + `Final` annotation rationale.
   - §3 `@register_plugin` non-decorator rationale (plugins are instances) + `register` / `all()` return-type tightening vs. arch.
   - §4 Cross-test isolation mechanism (snapshot pattern).
   - §5 `PluginId` newtype boundary (single lift inside `make_fake_plugin`).
   - §6 Rule-of-three observation — *now four* registries, extract still deferred, trigger pinned.
   - §7 Step 2 done-criteria is the union of S2-01..S2-04 (do not implement S2-03 / S2-04 deliverables here).
   - §8 Deliberately-not-adopted decisions (`__slots__`, dual-shape decorator) — pre-empts future second-guessing.

The original story's substance (Protocols + Registry + decorator helper + typed errors + fixture isolation) is preserved; the validator only **tightened**, **disambiguated**, and **added test specificity**. No scope change.

---

## Verdict — HARDENED

The story now passes the four critics:

- **Coverage:** every AC is individually verifiable; the lazy-implementation thought experiment no longer admits a passing-but-wrong impl.
- **Test-Quality:** every AC has at least one concrete test that would fail under an obvious mutation (`return None`, `set()` ordering, broken default path, untyped exception payload, `__abstractmethods__` semantics).
- **Consistency:** no contradiction with phase ADRs; the `PluginResolution` symbol gap is closed by a minimal placeholder file; the arch-divergence on `register`'s return type is *acknowledged* and the precedent justifies the tightening.
- **Design-Patterns:** kernel discipline preserved (no `__slots__`, no dual-shape decorator, no DI container); 4th-registry rule-of-three observation recorded so the kernel-extract opportunity survives; `Adapter` / `RecipeEngine` half-specified surfaces collapsed to single attributes + clear S5/S7 hand-off.

Ready for `phase-story-executor`.
