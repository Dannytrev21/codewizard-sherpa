# Story S2-02 — Implement `validate_pack` checks (totality, grammar-wired, adapter-resolves)

**Step:** Step 2 — Land the `register_language` / `validate_pack` kernel and `LanguageRegistry`
**Status:** Ready
**Effort:** M
**Depends on:** S2-01, S1-02
**ADRs honored:** ADR-0001, ADR-0002, ADR-0003

## Context
`register_language` is validate-all-then-commit (ADR-0002): every check must run *before any registry write*, so a colliding or un-wired pack fails loudly at import with nothing written. This story lands `validate_pack` — the all-checks-no-writes function — covering the three checks that do not touch other registries (totality, grammar-wired, adapter-import-resolves); the no-shadow check is deliberately split out to S2-04 (Gap 1) and `register_language` itself to S2-03.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — register_language() + validate_pack()` — the `validate_pack` signature and the four check categories; the explicit "all checks before any registry write" sequencing.
- **Architecture:** `../phase-arch-design.md §Process view` — the sequence diagram: `validate_pack` runs totality · grammars ⊆ supported_languages() · search_adapter_module resolves · no-shadow, then `register_language` proceeds.
- **Architecture:** `../phase-arch-design.md §Edge cases` rows 9, 13 — an un-wired grammar key and a missing wheel each raise `LanguageRegistryError` at import.
- **Phase ADRs:** `../ADRs/0002-register-language-validate-all-then-commit-no-unregister.md` — ADR-0002 — `validate_pack` runs every check before any write; failure raises `LanguageRegistryError` with nothing written.
- **Phase ADRs:** `../ADRs/0003-grammars-modeled-one-to-many-relation.md` — ADR-0003 — `grammars` is a `tuple[SupportedLanguage, ...]`; every member must be in `grammars.lock.supported_languages()`.
- **Phase ADRs:** `../ADRs/0011-python-search-adapter-tree-sitter-first-scip-deferred.md` — ADR-0011 — `search_adapter_module` is a `"module:ClassName"` import path (ADR-0032 idiom) that must resolve.
- **Existing code:** `src/codegenie/grammars/lock.py` — `supported_languages()` returns the tuple of wired grammar keys; this is the set the grammar-wired check tests membership against.
- **Existing code:** `src/codegenie/errors.py` — `LanguageRegistryError` is the single failure type.
- **Source design:** `../final-design.md §Synthesis ledger` — CR-2 row (the validate-all-then-commit resolution).

## Goal
Land `validate_pack(pack: LanguagePack) -> None` in `src/codegenie/languages/registry.py` running the totality, grammar-wired, and adapter-import-resolves checks, raising `LanguageRegistryError` on the first failure with nothing written.

## Acceptance criteria
- [ ] The TDD red test in `tests/unit/languages/test_validate_pack.py` exists, is committed, and was observed failing before implementation.
- [ ] `validate_pack` performs **no registry writes** — a unit test injects a check-failing pack and asserts the probe / depgraph / language registries are byte-identical to their pre-call state.
- [ ] **Grammar-wired check:** a pack whose `grammars` includes a key absent from `grammars.lock.supported_languages()` raises `LanguageRegistryError` naming the offending key (Edge case 9).
- [ ] **Adapter-resolves check:** a pack whose `search_adapter_module` `"module:ClassName"` path does not import, or whose class is absent, raises `LanguageRegistryError` naming the unresolvable path.
- [ ] **Totality check:** present as an explicit (Pydantic-backed, no-op-for-symmetry) assertion — documented as such; a pack that somehow reached `validate_pack` non-total still fails loudly.
- [ ] The error message for every failure names the offending field/key so a developer can locate it without re-running.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest tests/unit/languages/test_validate_pack.py` pass on touched files.
- [ ] Story `**Status:**` set to `Done`.

## Implementation outline
1. In `src/codegenie/languages/registry.py`, add `def validate_pack(pack: LanguagePack) -> None`.
2. **Totality:** Pydantic already guarantees field presence; add an explicit no-op-for-symmetry comment/assertion (the value cannot be partial — it is a `mypy` error upstream). Do not use a bare `assert` — use an explicit `raise LanguageRegistryError(...)` if a defensive check is kept.
3. **Grammar-wired:** for each member of `pack.grammars`, check membership in `grammars.lock.supported_languages()`; on the first miss raise `LanguageRegistryError` naming the key and the supported set.
4. **Adapter-resolves:** split `pack.search_adapter_module` on `":"`, `importlib.import_module` the module, `getattr` the class — any failure → `LanguageRegistryError` naming the path.
5. Order checks cheap-to-expensive; the function returns `None` on success and raises on the first failure — no partial success.
6. Wire `validate_pack` into `__all__` / `__init__` re-exports only if part of the ≤ 6-name surface; otherwise keep it module-internal until S2-03 calls it.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_validate_pack.py`.

```python
# test_unwired_grammar_key_raises
#   arrange: a LanguagePack with grammars=("typescript", "klingon")
#   act/assert: validate_pack(pack) raises LanguageRegistryError;
#               message mentions "klingon"

# test_unresolvable_adapter_module_raises
#   arrange: a pack with search_adapter_module="codegenie.does_not_exist:Nope"
#   act/assert: validate_pack(pack) raises LanguageRegistryError naming the path

# test_valid_pack_passes_without_writing
#   arrange: a fully-valid pack; snapshot default_registry / default_dep_graph_registry
#   act:     validate_pack(pack)
#   assert:  returns None; both substrate registries unchanged

# test_failure_writes_nothing
#   arrange: a grammar-unwired pack; snapshot all three registries
#   act/assert: validate_pack raises; all three registries byte-identical
```

Must fail with `ImportError`/`AttributeError` (no `validate_pack`) before implementation.

### Green — make it pass
Add `validate_pack` with the three checks. Keep each check a small pure-ish helper (`_check_grammars_wired`, `_check_adapter_resolves`) so the function reads as a sequence. No no-shadow logic yet — that is S2-04.

### Refactor — clean up
Extract the check helpers to module-private functions (functional-core discipline); docstrings citing ADR-0002/0003/0011; precise types; ensure every raise path carries a locatable message; confirm `mypy --strict` clean and no bare `assert`.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/languages/registry.py` | Add `validate_pack` + the private check helpers. |
| `tests/unit/languages/test_validate_pack.py` | New — the validate-pack check unit tests. |

## Out of scope
- The no-shadow check (probe-name + `PackageManager`-key) — S2-04 (Gap 1) — `validate_pack` will call into it there.
- `register_language` itself (the commit + fan-out) — S2-03.
- Idempotence + the `language.registered` event — S2-05.

## Notes for the implementer
- `validate_pack` writes *nothing* — this is the load-bearing ADR-0002 property. Every test must assert the substrate registries are untouched on failure; do not let a check accidentally call `register_probe`.
- The grammar-wired check is *validate-only*: `register_language` never writes the `_DISPATCH` dict — that row is a loud manual source edit (S4-01). `validate_pack` only asserts the row is already present.
- Adapter resolution uses `importlib` — a missing module and a present-module-missing-class are both failures; name the exact path in both messages.
- Do not implement the no-shadow check here even partially — Gap 1 (S2-04) specifies a subtle source-set split (live `default_probe_registry`, gated on `probes_self_registered`); a half-version here would contradict S2-04.
- Keep totality as an explicit no-op-for-symmetry: Pydantic + `mypy` already guarantee it, but the ADR-0002 sequence names it as one of the four checks — document why it is a no-op rather than silently omitting it.
- Order the checks cheap-first (grammar membership) before expensive (`importlib.import_module`) so a common misconfiguration fails fast.
