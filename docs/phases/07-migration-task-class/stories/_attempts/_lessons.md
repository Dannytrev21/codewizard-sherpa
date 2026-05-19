# Phase 7 — Cross-story lessons learned

Append-only ledger of lessons that apply to *other* Phase 7 stories. One
bullet per lesson; cite the originating story; keep it short.

## 2026-05-19 — S1-01 (newtype identifiers)

- **Python 3.13 yields bare strings (not `ForwardRef`) from `typing.get_args(tuple["X", "Y"])`.** Tests that introspect `TypeAlias` forward references must accept both shapes (`isinstance(a, ForwardRef) else a` to extract the name).
- **TYPE_CHECKING-guarded imports from not-yet-landed modules need an `[[tool.mypy.overrides]]` entry** with `ignore_missing_imports = true`. The override should name the originating story and be removed when the target module lands. Phase 1's `networkx`, S3-04's `pyarn`, and S1-01's `codegenie.primitives.vuln_provenance.registry` are the established pattern.
- **`_NEWTYPE_REGISTRY` is for `NewType`s only — `TypeAlias` rows do NOT belong.** `__all__` is the superset; the registry tests must subtract `TypeAlias` names before asserting key-equality.
- **Phase 7 `_NEWTYPE_REGISTRY` entries cite ADR-0004 / ADR-0006**, not Phase 3's ADR-0010. The Phase 3 `test_newtype_registry_matches_all` was extended (additively) to branch the ADR-citation check on Phase membership.
- **Phase 7 `Ecosystem` Enum (S2-01) collides at the symbol level with the Phase 3 `Ecosystem` Literal (`codegenie.types.identifiers`).** This is intentional — different modules, different membership, different responsibility. The Phase 7 alias chain uses underscored `_PhVnEcosystem` / `_PhVnLayer` to keep the symbols distinct; AC-11 sentinel test fails loud on accidental cross-module imports.
