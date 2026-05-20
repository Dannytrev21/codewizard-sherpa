# Story S2-03 — Implement `register_language` validate-then-commit fan-out

**Step:** Step 2 — Land the `register_language` / `validate_pack` kernel and `LanguageRegistry`
**Status:** Ready
**Effort:** M
**Depends on:** S2-02, S2-01
**ADRs honored:** ADR-0002, ADR-0006

## Context
`register_language` is the one privileged registration operation of Phase 7.5: it calls `validate_pack`, publishes the pack into `LanguageRegistry` via build-then-publish, then — for a non-self-registered pack only — fans `layer_a_probes` and `dep_graph_strategies` into the existing append-only `@register_probe` / `@register_dep_graph_strategy` registries. The `probes_self_registered=True` retrofit (TypeScript, ADR-0006) skips the probe fan-out so it does not re-register Phase 1 probes and crash with `ProbeError`.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — register_language() + validate_pack()` — the validate-all-then-commit sequence: `validate_pack` → build-then-publish → Python-only fan-out.
- **Architecture:** `../phase-arch-design.md §Process view` — the sequence diagram showing the TS path (no fan-out) and the Python path (fan-out ×4 probes, ×3 strategies).
- **Architecture:** `../phase-arch-design.md §Control flow` — decision points 1 (`probes_self_registered`?) and 2 (`validate_pack` outcome?).
- **Architecture:** `../phase-arch-design.md §Edge cases` rows 12 (mid-fan-out crash residual) and 16 (the retrofit skips the probe fan-out).
- **Phase ADRs:** `../ADRs/0002-register-language-validate-all-then-commit-no-unregister.md` — ADR-0002 — validate-all-then-commit; no `unregister`; the mid-fan-out residual is contained, not eliminated.
- **Phase ADRs:** `../ADRs/0006-typescript-retrofit-by-reference-probes-self-registered.md` — ADR-0006 — `register_language` skips the probe fan-out when `probes_self_registered=True`.
- **Existing code:** `src/codegenie/probes/registry.py` — `register_probe` / `default_registry`; duplicate registration raises `ProbeError`.
- **Existing code:** `src/codegenie/depgraph/registry.py` — `register_dep_graph_strategy` / `default_dep_graph_registry`; duplicate raises `DepGraphRegistryError`.
- **Source design:** `../final-design.md §Synthesis ledger` — CR-2 (validate-all-then-commit) and the build-then-publish reconciliation.

## Goal
Land `register_language(pack: LanguagePack) -> None` in `src/codegenie/languages/registry.py` — call `validate_pack`, build-then-publish into `LanguageRegistry`, then fan probes/strategies into the existing registries for `probes_self_registered=False` packs only.

## Acceptance criteria
- [ ] The TDD red test in `tests/unit/languages/test_register_language.py` exists, is committed, and was observed failing before implementation.
- [ ] `register_language` calls `validate_pack` first; a `validate_pack` failure propagates `LanguageRegistryError` with **nothing written** to any of the three registries (unit test snapshots all three).
- [ ] On success, the pack is published into `LanguageRegistry` via build-then-publish; `default_language_registry.get(pack.language)` returns it afterward.
- [ ] A `probes_self_registered=True` pack does **not** call `register_probe` (verified — re-registering a Phase 1 probe would raise `ProbeError`); its `dep_graph_strategies` are still fanned out.
- [ ] A `probes_self_registered=False` pack fans every `layer_a_probes` entry into the probe registry and every `dep_graph_strategies` entry into `DepGraphRegistry`; a unit test asserts the fanned-out probes are **callable and dispatchable** (intent over behavior — Rule 9), not merely "a key exists".
- [ ] The grammar `_DISPATCH` dict is **never written** by `register_language` (validate-only — Edge case 9).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest tests/unit/languages/test_register_language.py` pass on touched files; `import-linter` updated for the new cross-package fan-out imports.
- [ ] Story `**Status:**` set to `Done`.

## Implementation outline
1. In `src/codegenie/languages/registry.py`, add `def register_language(pack: LanguagePack) -> None`.
2. **Validate:** call `validate_pack(pack)` first — any raise propagates with nothing written.
3. **Build-then-publish:** call `default_language_registry.register(pack)` (the build-then-publish `register` from S2-01).
4. **Python-only fan-out:** if `pack.probes_self_registered is False`, loop `pack.layer_a_probes` calling `register_probe` for each; otherwise skip the probe loop.
5. **Strategy fan-out:** loop `pack.dep_graph_strategies.items()` calling `register_dep_graph_strategy(pm)(strategy)` for every pack (retrofit packs included — see S2-04 / OQ6).
6. Never touch `grammars.lock._DISPATCH`.
7. Re-export `register_language` from `codegenie.languages.__init__` (within the ≤ 6-name surface).

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_register_language.py`.

```python
# test_validate_failure_writes_nothing
#   arrange: a grammar-unwired pack; snapshot probe / depgraph / language registries
#   act/assert: register_language(pack) raises LanguageRegistryError;
#               all three registries byte-identical to pre-call state

# test_self_registered_pack_skips_probe_fan_out
#   arrange: a pack with probes_self_registered=True referencing an
#            already-registered probe class
#   act:     register_language(pack)  -> must NOT raise ProbeError
#   assert:  pack is in default_language_registry; register_probe NOT called
#            for that pack's probes (spy / no-duplicate-error)

# test_new_pack_fans_probes_and_strategies_dispatchably
#   arrange: a probes_self_registered=False pack with fresh probe classes
#            and a fresh dep-graph strategy
#   act:     register_language(pack)
#   assert:  each probe is in default_registry AND survives a for_task /
#            dispatch query (callable + dispatchable, not just "key exists");
#            the strategy resolves via DepGraphRegistry.dispatch
```

Must fail with `ImportError`/`AttributeError` (no `register_language`) before implementation.

### Green — make it pass
Add `register_language` with the validate → build-then-publish → conditional fan-out sequence. Use a fresh independent probe/depgraph registry pattern in tests so the global singletons are not polluted; or register/clean carefully. Keep the function a thin orchestration over `validate_pack` + the three registries.

### Refactor — clean up
Docstring citing ADR-0002/0006; precise types; confirm the `probes_self_registered` branch is the *only* place the skip lives (the no-shadow check skip is S2-04, not here); ensure `mypy --strict` clean.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/languages/registry.py` | Add `register_language`. |
| `src/codegenie/languages/__init__.py` | Re-export `register_language` (≤ 6-name surface). |
| `tests/unit/languages/test_register_language.py` | New — the register-language fan-out unit tests. |
| `pyproject.toml` / `.importlinter` config | Allow `codegenie.languages` → `codegenie.probes.registry` / `codegenie.depgraph.registry` imports. |

## Out of scope
- The no-shadow check internals — S2-04 (Gap 1). `validate_pack` (called from S2-02) will gain the no-shadow call there; this story consumes `validate_pack` as it stands after S2-02.
- Per-`Language` idempotence (re-register is a no-op) + the `language.registered` event — S2-05.
- The Hypothesis property test — S2-06.
- Constructing real packs (`TS_PACK` / `PYTHON_PACK`) — Steps 3 and 7.

## Notes for the implementer
- The mid-fan-out crash residual (a *new* pack crashing on probe 3 of 5) is **contained, not eliminated** (ADR-0002): it happens at import, before any gather, fails loudly. Do not paper over it with a fake rollback — there is no `unregister`. Land a unit test asserting the partial state is *detectable* if you simulate a mid-fan-out failure.
- The `probes_self_registered=True` skip applies *only* to the probe fan-out. Strategy fan-out still runs for retrofit packs — `@register_dep_graph_strategy` is not auto-fired the way Phase 1 `@register_probe` is (verify against `codegenie/depgraph/registry.py`; this is OQ6, resolved in S2-04).
- Intent-over-behavior (Rule 9): the fan-out test must prove probes are *dispatchable* — run a `for_task` / coordinator-style query — not merely assert a registry key exists. A registered-but-undispatchable probe is exactly the Gap 3 failure S7-03 also guards.
- `register_language` never writes `_DISPATCH` — the grammar row is a loud manual source edit (S4-01). If a test ever sees `_DISPATCH` mutate, the design is violated.
- Order matters: `validate_pack` *before* any `register` call. If validation passes but build-then-publish raises a duplicate-`Language` error, that is a separate (idempotence) concern handled in S2-05 — for this story a duplicate `Language` may still raise.
- Keep tests from polluting the global `default_registry` / `default_dep_graph_registry` — prefer constructing fresh registries and injecting them, or register uniquely-named probes and assert dispatchability without leaking into sibling tests.
