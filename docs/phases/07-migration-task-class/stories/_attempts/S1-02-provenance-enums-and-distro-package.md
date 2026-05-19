# S1-02 attempt log — `DistroPackage`, supporting enums, fences

Story: [`S1-02-provenance-enums-and-distro-package.md`](../S1-02-provenance-enums-and-distro-package.md).
Append-only journal.

## 2026-05-19 — Attempt 1: GREEN on first pass

### Outcome

GREEN. All 15 hardened ACs (the validator rewrote the AC list — see
`_validation/S1-02-provenance-enums-and-distro-package.md`) carry runtime
evidence. Gates green:

```
$ .venv/bin/pytest tests/unit/primitives/ tests/fence/test_vuln_provenance_frozen_base.py tests/fence/test_vuln_provenance_no_model_construct.py --no-cov
53 passed in 7.40s

$ .venv/bin/python -m mypy --strict src/
Success: no issues found in 188 source files

$ .venv/bin/ruff check src/codegenie/primitives/ tests/unit/primitives/ tests/fence/test_vuln_provenance_*.py tests/fence/test_kernel_frozen.py
All checks passed!

$ .venv/bin/lint-imports --config pyproject.toml --no-cache
Contracts: 4 kept, 0 broken.

$ .venv/bin/pytest tests/fence/ --no-cov
230 passed, 28 skipped, 1 xfailed in 26.60s

Full suite: 5367 passed, 7 pre-existing env failures (identical to the
S1-01 attempt-log set — secret-in-source SCIP fixture×2, goldens,
docker sandbox×2, lint-imports PATH×2).
```

### ReAct trace (compressed)

| Thought | Action | Observation |
|---|---|---|
| Story called for AppKind/BaseKind TYPE_CHECKING placeholders. | Read the modified story file. | Validator HARDENED the story: AppKind/BaseKind are out-of-scope (AC-5 inverted) — they land in S1-03 alongside the variants they bind. |
| `_Frozen` is new in Phase 7 (the original story said "established by Phase 3" — wrong; Phase 3 uses inline `model_config = ConfigDict(...)`). | Walked `transforms/outcomes.py`; confirmed inline-config style. | Phase 7 introduces `_Frozen` as the shared base. Fence AC-11 locks the new convention scoped to `primitives/vuln_provenance/`. |
| `Field(min_length=1)` admits `" "` (length 1). | Added `field_validator` enforcing `value.strip() == value and value != ""`. | All four whitespace-contamination matrix rows pass. |
| Ruff UP042 rejects `class X(str, Enum)`; codebase precedent (`transforms/sandbox/_seccomp.py`) uses `StrEnum`. | Switched `AdapterConfidence` to `StrEnum`. | Identical semantics: `isinstance(m, str)`, value-equality, JSON round-trip. AC-15 mypy-negative test confirms the static contract (raw `str` not accepted). |
| New top-level package `src/codegenie/primitives/` would be flagged as a Phase 0/1/2 kernel modification by `tests/fence/test_kernel_frozen.py` once committed. | Extended `_TOP_LEVEL_PHASE3_PACKAGES` in `test_kernel_frozen.py` to include `"primitives"` with a comment naming Phase 7 ADR-0004 / production ADR-0039 as the precedent for this directory. | Kernel-frozen fence stays green. The set now admits Phase 3 (`plugins`, `transforms`, `vuln_index`) + Phase 7 (`primitives`); future ADR-0039 primitives land additively under `primitives/{name}/`. |
| Module-purity fence needs exact-set semantics, not subset. | Exposed `_ALLOWED_TOP_LEVEL_IMPORTS: Final[frozenset[str]]` at module level; assertion is `imported == _ALLOWED_TOP_LEVEL_IMPORTS`. | Drift in either direction (extras OR missing seed imports) is a CI failure. |

### Deviations from the story (worth flagging)

1. **`AdapterConfidence` uses `StrEnum`, not the literal `(str, Enum)` shape named in AC-3.** Identical runtime semantics; codebase precedent (`transforms/sandbox/_seccomp.py:41`); ruff UP042 enforces the modern form. The static contract is unchanged — the AC-15 mypy-negative test proves a raw `str` is still rejected where `AdapterConfidence` is annotated, and the AC-8 round-trip / value / distinctness assertions all hold.
2. **`tests/fence/test_kernel_frozen.py` touched** — admits `primitives/` as a top-level additive package (mirrors the existing precedent for `plugins/`, `transforms/`, `vuln_index/`). This was the cleanest pattern; the alternative was per-file allowlist entries, which would balloon as S1-03 / S1-04 / S1-05 land. The story's Files-to-touch table does not name this file; calling it out so S1-03's executor knows the precedent.

### Files touched (final)

| Path | Why |
|---|---|
| `src/codegenie/primitives/__init__.py` | NEW — empty package init (Phase 7 ADR-0004 home for bounded primitives). |
| `src/codegenie/primitives/vuln_provenance/__init__.py` | NEW — public `__all__ = ["AdapterConfidence", "DistroPackage", "UnknownReason"]`. |
| `src/codegenie/primitives/vuln_provenance/types.py` | NEW — `_Frozen`, `AdapterConfidence` (`StrEnum`), `UnknownReason` (`Literal[6]`), `DistroPackage` with whitespace `field_validator`. |
| `tests/unit/primitives/__init__.py` + `tests/unit/primitives/vuln_provenance/__init__.py` | NEW — test package inits. |
| `tests/unit/primitives/vuln_provenance/test_types_phase7.py` | NEW — ACs 2/3/4/6/7/8/12. 38 cases. |
| `tests/unit/primitives/vuln_provenance/test_types_module_purity.py` | NEW — AC-9. Exact-set module imports + no-relative-imports. |
| `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py` | NEW — AC-13. Locked tuples for both `types.__all__` + `__init__.__all__`. |
| `tests/unit/primitives/vuln_provenance/test_types_mypy_negative.py` | NEW — AC-15. Three reject-cases + three negative-control accept-cases via subprocess-mypy. |
| `tests/fence/test_vuln_provenance_frozen_base.py` | NEW — AC-11. AST-walk asserts every `class X(BaseModel)` under `primitives/vuln_provenance/` inherits `_Frozen`. |
| `tests/fence/test_vuln_provenance_no_model_construct.py` | NEW — AC-14. AST-walk forbids `model_construct(...)` call sites under the primitive. |
| `tests/fence/test_kernel_frozen.py` | EXTENDED — `_TOP_LEVEL_PHASE3_PACKAGES` admits `"primitives"`. |

### Tests added (summary)

| File | Count | ACs covered |
|---|---|---|
| `tests/unit/primitives/vuln_provenance/test_types_phase7.py` | 38 cases | AC-1, AC-2, AC-3, AC-4, AC-6, AC-7, AC-8, AC-12 |
| `tests/unit/primitives/vuln_provenance/test_types_module_purity.py` | 2 cases | AC-9 |
| `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py` | 2 cases | AC-13 |
| `tests/unit/primitives/vuln_provenance/test_types_mypy_negative.py` | 6 cases | AC-15 |
| `tests/fence/test_vuln_provenance_frozen_base.py` | 4 cases | AC-11 |
| `tests/fence/test_vuln_provenance_no_model_construct.py` | 3 cases | AC-14 |
| **Total** | **55 new pytest items** | All 15 ACs |

### Refactor decisions

- **No premature abstraction.** `_Frozen` is the only abstraction introduced — and even that is forced by AC-11. No mixins, no `Generic[T]` base, no `@dataclass`. Three records, three enums-or-Literals, one validator.
- **`StrEnum` over `(str, Enum)`.** Match codebase convention (Rule 11) over the story's literal text. The mypy-negative test proves the static contract is unchanged.
- **One `field_validator` for `name`+`version`, not two.** Same rule on both fields; one decorator with `("name", "version")` keeps the rule's purpose visible in one place. Whitespace handling lives at the smart-constructor seam (production ADR-0033 §Smart constructors).

### Lessons for the next Phase 7 story (S1-03)

- **Grow the `__init__.py` `__all__` additively** — the `test_types_dunder_all.py` locked tuple `_EXPECTED_PUBLIC_ALL` must be updated when S1-03 adds the seven variant classes + `AppKind` / `BaseKind`. Sort-position: `AppKind`, `AdapterConfidence`, `AppDirect`, `AppTransitive`, `AppVendored`, `BaseImage`, `BaseKind`, `Both`, `DistroPackage`, `RuntimeBundled`, `Unknown`, `UnknownReason` (ASCII order).
- **Every new `class X(BaseModel)` under `primitives/vuln_provenance/` MUST inherit `_Frozen`** — the AC-11 fence will catch a direct `BaseModel` subclass at collection time. If S1-03 needs a non-frozen pattern, amend ADR-0004 and update `_ADMITTED_FROZEN_BASES`.
- **No `model_construct(...)` call sites** — the AC-14 fence walks the entire primitive tree. The validating constructor is the only admitted construction path.
- **`AppKind` / `BaseKind` land in `types.py` alongside the variant classes** — same file, same atomic landing, so the discriminated-union aliases can reference the variant names without forward strings.
- **The `_Frozen` base lives in `types.py`** — sibling modules under `primitives/vuln_provenance/` should `from codegenie.primitives.vuln_provenance.types import _Frozen` rather than redeclaring the inline `ConfigDict(...)`. The AC-11 fence enforces this.
- **JSON round-trip for every new variant** — the AC-12 pattern (`model_dump_json` → `model_validate_json` → equals) catches silent serialization drift before the event log nests the payload. Mirror this for `AppDirect`, `AppTransitive`, `AppVendored`, `BaseImage`, `RuntimeBundled`, `Both`, `Unknown`.
- **Kernel-frozen allowlist precedent** — `primitives/` is admitted at the directory level (in `_TOP_LEVEL_PHASE3_PACKAGES`); S1-03 / S1-04 do not need to add per-file entries.
