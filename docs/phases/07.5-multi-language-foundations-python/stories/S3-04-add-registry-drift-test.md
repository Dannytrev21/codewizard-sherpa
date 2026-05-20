# Story S3-04 — Add the registry-drift test (at-least-the-union)

**Step:** Step 3 — Retrofit TypeScript as `LanguagePack` #1 (by reference)
**Status:** Ready
**Effort:** S
**Depends on:** S3-02
**ADRs honored:** ADR-0006, ADR-0002

## Context
The TypeScript retrofit is "by reference": `TS_PACK.layer_a_probes` records probe classes but `register_language` never fans them out. The honesty mitigation for that asymmetry (architect Gap 2 / ADR-0006 Risk #2) is a drift test that proves the live probe registry actually *contains* every probe each pack claims. The subtlety this story must get right: the test asserts **at least the union**, never equality — Phase 2–7 added dozens of Layer B–G probes that belong to *no* `LanguagePack`, so a strict-equality test would be permanently red.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Gap analysis & improvements §Gap 2` — the drift test is named as the retrofit-honesty mitigation; "at least the union, not equality."
- **Architecture:** `../phase-arch-design.md §Component design — register_language() + validate_pack()` — the no-shadow / fan-out asymmetry the drift test guards.
- **Phase ADRs:** `../ADRs/0006-typescript-retrofit-by-reference-probes-self-registered.md` — ADR-0006 — "the drift test asserts the probe registry contains *at least* the union of all packs' `layer_a_probes` — strict equality is wrong (Layer B–G probes belong to no pack)."
- **Phase ADRs:** `../ADRs/0002-register-language-validate-all-then-commit-no-unregister.md` — ADR-0002 — `register_language` fans `probes_self_registered=False` packs out; `probes_self_registered=True` packs are by reference.
- **Existing code:** `src/codegenie/probes/registry.py` — `default_registry`, `default_registry.all_probes()` — the live probe registry surface the test reads.
- **Existing code:** `src/codegenie/probes/__init__.py` — imports every shipped probe (Layer A–G), so the live registry is fully populated after this import.
- **Existing code (this phase):** `src/codegenie/languages/packs/typescript.py` (S3-02) — `TS_PACK`; `default_language_registry` — the source of "all packs."

## Goal
Add a test asserting that for every registered `LanguagePack`, every class in `pack.layer_a_probes` is present in the live `default_registry`, scoped to subset (`⊆`) not equality.

## Acceptance criteria
- [ ] The TDD red test exists, is committed, and is green: `tests/unit/languages/test_registry_drift.py` asserts `union(pack.layer_a_probes for pack in default_language_registry.all())` is a **subset** of `default_registry.all_probes()`.
- [ ] The test imports `codegenie.probes` (so the full Layer A–G registry is populated) and `codegenie.languages.packs` (so all packs are registered) before asserting — no ordering flake.
- [ ] The assertion is `⊆`, not `==` — a comment in the test explains *why* equality is wrong (Phase 2–7 Layer B–G probes belong to no pack); a deliberate near-miss negative check confirms the test would catch a pack claiming a probe absent from the registry.
- [ ] The test passes with the registry as-shipped (`TS_PACK`'s `layer_a_probes` are all in `default_registry` — they self-registered in Phase 1).
- [ ] A negative-direction assertion or a documented mutation note proves teeth: an injected pack with a fabricated probe class not in the registry makes the drift test fail (Rule 9 — the test must fail for the right reason).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` (if the test has typed helpers), and `pytest` pass on touched files.
- [ ] Status set to `Done` on completion.

## Implementation outline
1. Create `tests/unit/languages/test_registry_drift.py`.
2. In the test body: import `codegenie.probes` and `codegenie.languages.packs`; build `claimed = set().union(*(p.layer_a_probes for p in default_language_registry.all()))` and `live = set(default_registry.all_probes())`.
3. Assert `claimed <= live` with a failure message listing `claimed - live` (the drifted probes) so a failure is self-diagnosing.
4. Add an explanatory comment block: equality is wrong because Layer B–G probes belong to no pack; the invariant is one-directional (every claimed probe is registered, not every registered probe is claimed).
5. Add a negative test (`test_drift_test_has_teeth`) that constructs a throwaway `LanguagePack` (or a fake namespace) whose `layer_a_probes` contains a probe class never registered, and asserts the subset check fails for that input — proving the assertion is not vacuous.
6. Run `pytest tests/unit/languages/test_registry_drift.py` and the full suite.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_registry_drift.py`.
Test name: `test_probe_registry_contains_at_least_union_of_pack_layer_a_probes`.
```python
# arrange: import codegenie.probes (populates default_registry, all layers)
#          import codegenie.languages.packs (registers TS_PACK)
# act: claimed = union of p.layer_a_probes for p in default_language_registry.all()
#      live = set(default_registry.all_probes())
# assert: claimed <= live   # subset — NEVER ==
#   intent: every probe a pack claims is genuinely in the live registry;
#           the retrofit's "by reference" tuple is not a paper claim (Gap 2)
```
This is red until S3-02 has registered `TS_PACK` with a complete `layer_a_probes`. If `TS_PACK.layer_a_probes` is incomplete, this test still *passes* (subset holds for a subset) — so the teeth come from the negative test, not this one alone.

Test name: `test_drift_test_has_teeth` — a fabricated pack-shaped object whose `layer_a_probes` includes a probe class absent from `default_registry` makes the subset check `False`.
```python
# arrange: a fake/throwaway pack with layer_a_probes=(SomeUnregisteredProbeClass,)
# act: claimed_fake <= live
# assert: that expression is False
#   intent: prove the subset assertion would actually catch a drifted pack (Rule 9)
```

### Green — make it pass
The positive test passes once S3-02 registered `TS_PACK` (its probes self-registered in Phase 1, so they are all in `default_registry`). The negative test passes because the fabricated probe class is genuinely absent. No production code changes — this is a pure test story.

### Refactor — clean up
Extract a small helper `_claimed_layer_a_probes() -> set[type[Probe]]` for readability if both tests need it. Tighten the failure message to name the drifted classes. Add a module docstring referencing Gap 2 and ADR-0006 so a future reader understands why the assertion is `⊆` and never `==`.

## Files to touch
| Path | Why |
|---|---|
| `tests/unit/languages/test_registry_drift.py` | New — the at-least-the-union drift test + the teeth negative test. |

## Out of scope
- Equality-style "registry == union of packs" assertions — explicitly wrong (ADR-0006); do not add one.
- The dispatch-order conformance assertion (`test_language_probes_actually_dispatched`) — that is Gap 3 / S7-03, a different invariant (registered *and dispatched*).
- `EXPECTED_LANGUAGE_COUNT` and the collection-completeness guard — S7-02.
- `PYTHON_PACK` — when S7-01 registers it, this same test auto-extends to cover it (no edit needed here; that is the point of `default_language_registry.all()`).

## Notes for the implementer
- **`⊆`, never `==`.** This is the single most important constraint of the story. Phase 2–7 added Layer B–G probes (`dep_graph`, `cve`, `gitleaks`, `semgrep`, …) that belong to no pack; equality would be permanently red. The architect calls this out three times.
- The positive subset test is *weak on its own* — a partial `TS_PACK.layer_a_probes` still satisfies a subset. The honesty teeth come from (a) S3-02's separate `layer_a_probes`-matches-Phase-1-imports test and (b) this story's `test_drift_test_has_teeth` negative case. Do not collapse them.
- Import order matters: import `codegenie.probes` and `codegenie.languages.packs` explicitly in the test so the registries are populated regardless of test-collection order — do not rely on another test having imported them.
- When `PYTHON_PACK` lands (S7-01), `PYTHON_PACK.layer_a_probes` *are* fanned out (`probes_self_registered=False`), so the subset invariant must still hold — this test needs no change then, which is the design intent; verify the test reads `default_language_registry.all()` dynamically, not a hard-coded `[TS_PACK]`.
- Keep this a pure test story — touch no `src/` file.
