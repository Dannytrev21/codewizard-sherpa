# Story S4-01 — Wire the `tree-sitter-python` grammar row

**Step:** Step 4 — Build the Python Layer A/B probes and the `tree-sitter-python` grammar row
**Status:** Ready
**Effort:** S
**Depends on:** S2-05
**ADRs honored:** ADR-0003, ADR-0007

## Context
Every Python probe that parses a file goes through the grammar kernel's `language_for(name)` indirection — probes never import a `tree_sitter_*` package directly. Phase 7.5 must add Python to that kernel before any Python probe can parse, and ADR-0003 mandates it land as exactly one row in `_DISPATCH` plus one pinned PyPI wheel — the same "add a grammar = one dispatch row + one wheel" pattern 02-ADR-0011 established for TypeScript/JavaScript.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — Python Layer A/B probes` — the grammar wheel loads lazily on first `language_for("python")`; the wheel is *not* imported at pack-definition time.
- **Architecture:** `../phase-arch-design.md §Control flow` — "the loud edits" list: `SupportedLanguage` Literal `+1` and `grammars.lock._DISPATCH` `+1` row are compiler-policed loud edits, not violations.
- **Phase ADRs:** `../ADRs/0003-grammars-modeled-one-to-many-relation.md` — ADR-0003 — "adding a future grammar is a `SupportedLanguage` Literal `+1` and a `_DISPATCH` `+1` row; `register_language` never writes `_DISPATCH`."
- **Phase ADRs:** `../ADRs/0007-python-probes-hardened-parse-only-no-exec.md` — ADR-0007 — Python probes are parse-only; the grammar kernel is the parse path.
- **Existing code:** `src/codegenie/grammars/lock.py` — `SupportedLanguage` Literal, `_DISPATCH` dict (`language-name → (pypi-module-name, capsule-factory-attr)`), `_build_language`, `supported_languages()`, `language_for`, `GrammarLoadRefused`.
- **Existing code:** `pyproject.toml` lines ~42–54 — the `tree-sitter` / `tree-sitter-typescript` / `tree-sitter-javascript` pinned dependency block; the comment already names `tree-sitter-python` as the next additive dep line.
- **Existing code:** `tests/unit/` grammar-kernel tests (e.g. `test_grammar_lock.py` or equivalent) — the existing pattern for asserting `language_for` and `supported_languages()`.
- **External docs:** PyPI `tree-sitter-python` — the wheel package; exposes a `language()` capsule factory (verify the exact attr name against the installed wheel before pinning the `_DISPATCH` row).

## Goal
Pin the `tree-sitter-python` PyPI wheel and add the `+1` `_DISPATCH` row so `language_for("python")` lazily loads a usable tree-sitter `Language`.

## Acceptance criteria
- [ ] A red test in the grammar-kernel test module asserts `language_for("python")` returns a tree-sitter `Language` and that `"python"` appears in `supported_languages()`; it fails before the change.
- [ ] `tree-sitter-python` is pinned in `pyproject.toml` with a version range matching the sibling grammar pins, and `uv.lock` is regenerated to include it with hashes.
- [ ] `SupportedLanguage` Literal is extended with `"python"` and `_DISPATCH` gains exactly one row `"python": ("tree_sitter_python", "<capsule-factory-attr>")` (attr verified against the installed wheel).
- [ ] `make fence` is green — the `tree-sitter-python` wheel pin is present and no `FORBIDDEN_LLM_SDK` rode in alongside it (the fence's wheel-pin assertion may need the extension in S8-02; if the existing fence already enumerates grammar pins, extend it here).
- [ ] Lazy-load is preserved: importing `codegenie.grammars.lock` does not import `tree_sitter_python`; a test asserts `tree_sitter_python` is absent from `sys.modules` until the first `language_for("python")`.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/`, and `pytest` pass on the touched files; Status set to `Done`.

## Implementation outline
1. Add `tree-sitter-python` to the `pyproject.toml` dependency block, version-range-matched to the sibling grammar pins; regenerate `uv.lock`.
2. Inspect the installed wheel to confirm the capsule-factory attribute name (`language` is the likely name, as for `tree-sitter-javascript`).
3. Extend `SupportedLanguage = Literal["typescript", "tsx", "javascript"]` with `"python"`.
4. Add the `"python"` row to `_DISPATCH`; `functools.lru_cache(maxsize=len(_DISPATCH))` auto-resizes since it is derived from `_DISPATCH`.
5. Update the module docstring's "add a Phase-8 row" example if it still names `"python"` as hypothetical.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/test_grammar_lock.py` (or the existing grammar-kernel test module — match the repo's location).
Test name: `test_language_for_python_loads_lazily`.
```python
def test_language_for_python_loads_lazily() -> None:
    # arrange: codegenie.grammars.lock is imported; tree_sitter_python is NOT yet imported.
    # act: call language_for("python").
    # assert: returns a tree_sitter.Language; "python" in supported_languages();
    #         tree_sitter_python is now present in sys.modules but was absent before the call.
```
This fails today: `"python"` is not in `SupportedLanguage` / `_DISPATCH`, so `language_for("python")` raises `GrammarLoadRefused`.

### Green — make it pass
Pin the wheel, extend the `SupportedLanguage` Literal, add the single `_DISPATCH` row. No new functions — the kernel's `_build_language` / `language_for` already dispatch generically off `_DISPATCH`.

### Refactor — clean up
Confirm the module docstring no longer calls `"python"` a *future* row. Keep the `_DISPATCH` row alphabetically or grouped sensibly with the existing rows. Verify `supported_languages()` is still sorted-deterministic.

## Files to touch
| Path | Why |
|---|---|
| `pyproject.toml` | Pin the `tree-sitter-python` wheel (additive dep line). |
| `uv.lock` | Regenerated lockfile carrying the new wheel + hashes. |
| `src/codegenie/grammars/lock.py` | `SupportedLanguage` Literal `+1`; `_DISPATCH` `+1` row; docstring touch-up. |
| `tests/unit/test_grammar_lock.py` | The red test for `language_for("python")` + lazy-load assertion. |

## Out of scope
- The Python probes themselves (S4-02, S4-04, S4-05, S4-07).
- The `make fence` `tree-sitter-python`-pin assertion *finalization* if it requires broader fence rework — that closes in S8-02; do the minimal extension here.
- Java / any other grammar — Phase 8.

## Notes for the implementer
- Verify the capsule-factory attribute name against the *installed* `tree-sitter-python` wheel before committing the `_DISPATCH` row — a wrong attr surfaces only as a `GrammarLoadRefused` at runtime (the kernel's `getattr` branch), not at import.
- Keep the version range consistent with the `tree-sitter` runtime range (`>=0.23,<0.26`) — an ABI mismatch between the runtime and the grammar wheel is exactly the `RuntimeError` branch `GrammarLoadRefused` folds in.
- `make fence`'s `FORBIDDEN_LLM_SDKS` set (`anthropic, langgraph, openai, langchain, transformers`) must stay clean — confirm the new wheel pulls no LLM SDK transitively.
- Do not touch the coordinator or any probe — this story is purely the kernel + pin (ADR-0003: `register_language` never writes `_DISPATCH`, and neither does any probe).
