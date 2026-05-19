# Phase 7 — Cross-story lessons learned

Append-only ledger of lessons that apply to *other* Phase 7 stories. One
bullet per lesson; cite the originating story; keep it short.

## 2026-05-19 — S1-01 (newtype identifiers)

- **Python 3.13 yields bare strings (not `ForwardRef`) from `typing.get_args(tuple["X", "Y"])`.** Tests that introspect `TypeAlias` forward references must accept both shapes (`isinstance(a, ForwardRef) else a` to extract the name).
- **TYPE_CHECKING-guarded imports from not-yet-landed modules need an `[[tool.mypy.overrides]]` entry** with `ignore_missing_imports = true`. The override should name the originating story and be removed when the target module lands. Phase 1's `networkx`, S3-04's `pyarn`, and S1-01's `codegenie.primitives.vuln_provenance.registry` are the established pattern.
- **`_NEWTYPE_REGISTRY` is for `NewType`s only — `TypeAlias` rows do NOT belong.** `__all__` is the superset; the registry tests must subtract `TypeAlias` names before asserting key-equality.
- **Phase 7 `_NEWTYPE_REGISTRY` entries cite ADR-0004 / ADR-0006**, not Phase 3's ADR-0010. The Phase 3 `test_newtype_registry_matches_all` was extended (additively) to branch the ADR-citation check on Phase membership.
- **Phase 7 `Ecosystem` Enum (S2-01) collides at the symbol level with the Phase 3 `Ecosystem` Literal (`codegenie.types.identifiers`).** This is intentional — different modules, different membership, different responsibility. The Phase 7 alias chain uses underscored `_PhVnEcosystem` / `_PhVnLayer` to keep the symbols distinct; AC-11 sentinel test fails loud on accidental cross-module imports.

## 2026-05-19 — S1-02 (DistroPackage + enums + fences)

- **`_Frozen` is new in Phase 7, NOT inherited from Phase 3.** Phase 3's `transforms/outcomes.py` uses repeated inline `model_config = ConfigDict(frozen=True, extra="forbid")`. S1-02 introduces the shared `_Frozen(BaseModel)` base under `primitives/vuln_provenance/types.py` and the AC-11 AST-walk fence (`tests/fence/test_vuln_provenance_frozen_base.py`) locks it scoped to `primitives/vuln_provenance/`. Future stories adding `BaseModel` subclasses in this subpackage MUST inherit `_Frozen` or amend ADR-0004.
- **`Field(min_length=1)` alone admits `" "` and `"\t"` (length 1).** Use a `field_validator` enforcing `value.strip() == value and value != ""` on every string field that downstream consumers index by — `(distro, name, version)` tuples poison silently under whitespace contamination. Sibling primitive records should mirror the pattern.
- **`model_construct(...)` is forbidden under `primitives/vuln_provenance/`** by the AC-14 fence (`tests/fence/test_vuln_provenance_no_model_construct.py`). It skips validation, which would let an adapter admit `DistroPackage(distro="centos", ...)` and poison the event log. Use the validating constructor; if a test or fixture needs the bypass, build the fixture outside the primitive tree.
- **`StrEnum` (Python 3.11+) is the codebase precedent** (`transforms/sandbox/_seccomp.py`), not the older `(str, Enum)` shape. Ruff UP042 enforces this. The static contract is identical — `mypy --strict` rejects a raw `str` where the enum is annotated either way; the AC-15 negative test pins this.
- **The kernel-frozen fence (`tests/fence/test_kernel_frozen.py`) admits `primitives/` as an additive top-level package** (S1-02 added `"primitives"` to `_TOP_LEVEL_PHASE3_PACKAGES` alongside `plugins`, `transforms`, `vuln_index`). Future Phase 7 stories that touch `src/codegenie/primitives/vuln_provenance/*` do NOT need per-file allowlist entries — the directory is admitted at the top level.
- **`__init__.py.__all__` is locked by `test_types_dunder_all.py`** to exactly `["AdapterConfidence", "DistroPackage", "UnknownReason"]` today. S1-03 grows the tuple additively (`AppDirect`, `AppKind`, ..., `Unknown`) and updates `_EXPECTED_PUBLIC_ALL` in the test. Sort-order: ASCII (`_` > capital letters).
- **JSON round-trip is the minimum AC for every nested record in `Provenance`.** AC-12's `model_dump_json` → `model_validate_json` → equals pattern catches silent serialization drift before downstream phases consume the event log. Mirror for every variant S1-03 lands.
