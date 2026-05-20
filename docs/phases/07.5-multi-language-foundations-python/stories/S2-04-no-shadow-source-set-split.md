# Story S2-04 — Specify the no-shadow source-set split (Gap 1)

**Step:** Step 2 — Land the `register_language` / `validate_pack` kernel and `LanguageRegistry`
**Status:** Ready
**Effort:** M
**Depends on:** S2-03
**ADRs honored:** ADR-0002, ADR-0006

## Context
The no-shadow check is the most subtle part of `validate_pack`: it must catch a Python probe whose `name` collides with *any* already-registered probe — including Phase 2–7 Layer B–G probes that belong to no `LanguagePack` at all. Architect Gap 1 specifies the correct, complete source set: the **live `default_probe_registry`** (not the set of registered packs), and the probe-name check runs **only for `probes_self_registered=False` packs** (a retrofit pack's probes *are* the registry's existing content — comparing them to themselves is meaningless). The `PackageManager`-key no-shadow check reads `DepGraphRegistry` and runs for *every* pack.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Gap analysis & improvements — Gap 1` — the full specification: the no-shadow check reads the live `default_probe_registry`, gated on `probes_self_registered=False`; the `PackageManager`-key check reads `DepGraphRegistry` for every pack. Read this in full — it is the contract for this story.
- **Architecture:** `../phase-arch-design.md §Component design — register_language() + validate_pack()` — the no-shadow check listed as the fourth `validate_pack` check.
- **Architecture:** `../phase-arch-design.md §Edge cases` row 10 — a new pack claiming an already-registered probe name / `PackageManager` key raises `LanguageRegistryError` naming both call sites.
- **Architecture:** `../phase-arch-design.md §Open questions deferred to implementation` — OQ6 — verify whether Node dep-graph strategies are pre-registered in `DepGraphRegistry` and mirror the split accordingly.
- **Phase ADRs:** `../ADRs/0002-register-language-validate-all-then-commit-no-unregister.md` — ADR-0002 — Consequences bullet: "the no-shadow check reads the live `default_probe_registry` … runs only for `probes_self_registered=False` packs"; the `PackageManager`-key check reads `DepGraphRegistry` for every pack.
- **Phase ADRs:** `../ADRs/0006-typescript-retrofit-by-reference-probes-self-registered.md` — ADR-0006 — the probe-name no-shadow check skip lives here, not in the fan-out step; a retrofit pack's probes belong to Phase 1, not to a colliding pack.
- **Existing code:** `src/codegenie/probes/registry.py` — `default_registry` is the live probe registry; inspect how to enumerate the registered probe `name`s (the `Registry` entries / `for_task` surface).
- **Existing code:** `src/codegenie/depgraph/registry.py` — `default_dep_graph_registry`; `registered_ecosystems()` returns the `frozenset[PackageManager]` to test membership against.

## Goal
Implement the no-shadow check inside `validate_pack` — a probe-name check against the live `default_probe_registry` (gated on `probes_self_registered=False`) and a `PackageManager`-key check against `DepGraphRegistry` (every pack) — raising `LanguageRegistryError` naming both colliding sites.

## Acceptance criteria
- [ ] The TDD red test in `tests/unit/languages/test_no_shadow.py` exists, is committed, and was observed failing before implementation.
- [ ] The probe-name no-shadow check reads the **live `default_probe_registry`** — a unit test proves a Python probe colliding with a Phase 2–7 probe that belongs to *no pack* (e.g. a Layer-D probe) is caught.
- [ ] The probe-name no-shadow check **does not run** for `probes_self_registered=True` packs — a unit test registers a retrofit pack whose `layer_a_probes` are already in the registry and asserts no false-positive `LanguageRegistryError`.
- [ ] The `PackageManager`-key no-shadow check reads `DepGraphRegistry` (`registered_ecosystems()` or equivalent) and runs for **every** pack — a unit test proves a pack reusing an already-registered `PackageManager` key raises.
- [ ] Every no-shadow failure raises `LanguageRegistryError` whose message names **both** the offending name/key and the prior registration site.
- [ ] OQ6 is resolved in-story: the implementer verifies against `codegenie/depgraph/registry.py` whether Node strategies are pre-registered and records the finding (in the test docstring or a code comment); the `PackageManager`-key check behaves correctly either way.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest tests/unit/languages/test_no_shadow.py` pass; the ADR-0002 "Consequences" note is reviewed and consistent.
- [ ] Story `**Status:**` set to `Done`.

## Implementation outline
1. In `src/codegenie/languages/registry.py`, add a private `_check_no_shadow(pack: LanguagePack) -> None` and call it from `validate_pack` (after the grammar/adapter checks).
2. **Probe-name check:** if `pack.probes_self_registered is False`, enumerate the `name`s currently in `default_probe_registry`; for each `probe_cls` in `pack.layer_a_probes`, if `probe_cls.name` is already present, raise `LanguageRegistryError` naming the name and the prior site.
3. **Self-registered skip:** if `pack.probes_self_registered is True`, skip the probe-name check entirely — its probes are the registry's existing content by definition.
4. **`PackageManager`-key check:** for every pack, enumerate the keys in `default_dep_graph_registry`; for each `pm` in `pack.dep_graph_strategies`, if `pm` is already registered, raise `LanguageRegistryError` naming the key and the prior site.
5. Verify OQ6: read `codegenie/depgraph/registry.py` (and the Node plugin manifest) to confirm whether Node strategies are pre-registered; document the finding; the key check works in both cases.
6. Keep `_check_no_shadow` pure-read — no writes (ADR-0002 validate-all-then-commit).

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_no_shadow.py`.

```python
# test_probe_name_collision_with_non_pack_probe_is_caught
#   arrange: a probes_self_registered=False pack whose layer_a_probes
#            includes a probe with name == a registered Phase 2-7 probe's name
#   act/assert: validate_pack(pack) raises LanguageRegistryError naming
#               both the name and the prior site

# test_self_registered_pack_skips_probe_name_check
#   arrange: a probes_self_registered=True pack referencing
#            already-registered probe classes
#   act:     validate_pack(pack)  -> must NOT raise (no false positive)
#   assert:  returns None

# test_package_manager_key_collision_raises_for_every_pack
#   arrange: a pack (either probes_self_registered value) whose
#            dep_graph_strategies reuses an already-registered PackageManager key
#   act/assert: validate_pack(pack) raises LanguageRegistryError naming the key
```

Must fail with `AttributeError`/`AssertionError` (no `_check_no_shadow` / wrong behavior) before implementation.

### Green — make it pass
Add `_check_no_shadow` reading the live `default_probe_registry` and `default_dep_graph_registry`. The probe-name branch is gated on `probes_self_registered`; the `PackageManager`-key branch is unconditional.

### Refactor — clean up
Docstring citing Gap 1 + ADR-0002 + ADR-0006; precise types; the OQ6 finding recorded in a comment; confirm the check is pure-read and `mypy --strict` clean; verify the messages name both sites.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/languages/registry.py` | Add `_check_no_shadow` + wire it into `validate_pack`. |
| `tests/unit/languages/test_no_shadow.py` | New — the no-shadow source-set-split unit tests. |

## Out of scope
- The probe-fan-out skip for self-registered packs — that lives in `register_language` (S2-03), distinct from the no-shadow skip here.
- Idempotence + the `language.registered` event — S2-05.
- Constructing `TS_PACK` (the first real `probes_self_registered=True` consumer) — S3-02.

## Notes for the implementer
- The single most important point (Gap 1): the probe-name check reads the **live `default_probe_registry`**, *not* the set of registered `LanguagePack`s. If you only consult registered packs you will miss a collision with a Phase 2–7 Layer-D probe that belongs to no pack — exactly the hole Gap 1 closes.
- The `probes_self_registered` gate lives in *two distinct places* with distinct meanings: here (skip the no-shadow *check* — the retrofit's probes are already the registry's content) and in `register_language` S2-03 (skip the *fan-out* — do not re-register). Do not conflate them.
- The `PackageManager`-key check runs for **every** pack — a retrofit pack's strategies are *not* auto-pre-registered the way Phase 1 probes are. Verify this against `codegenie/depgraph/registry.py` (OQ6) and record what you find; if Node strategies *are* pre-registered via the plugin layer, the check still behaves correctly because it reads the live registry.
- This check is pure-read — it must never write. It runs inside `validate_pack`, which is validate-all-then-commit; a write here would break ADR-0002's "nothing written on failure" guarantee.
- Name *both* sites in the error: the offending name/key and the prior registration origin — mirror the `DepGraphRegistry` duplicate-error UX so a developer can grep both.
- After implementing, re-read ADR-0002's "Consequences" section — it already states this split; confirm the code matches the ADR and note any follow-up if it does not.
