# Story S1-05 — Package `__init__` + static smuggling/SDK guards

**Step:** Step 1 — Establish contracts: package scaffold, wire models, registry, Protocol
**Status:** Ready
**Effort:** M
**Depends on:** S1-02, S1-03, S1-04
**ADRs honored:** ADR-0008 (substring ban at the dict-key / breakdown-key value layer), Phase 5 ADR-0014 (`ObjectiveSignals` substring-ban field-walking precedent — ported), Phase 0 import-linter contract (extended to ban LLM SDKs from `codegenie.eval.**`), production ADR-0008 (`objective-signal trust score` — facts not LLM judgment)

## Context

This is the closing story for Step 1 — it wires the package's public surface and lands two AST-walking guards that make the contract structurally smuggling-resistant. The first guard (`test_bench_score_static.py`) recursively walks Pydantic field graphs reachable from `BenchScore` and rejects the four banned substrings (`confidence`, `llm`, `self_reported`, `model_says`); the second (`test_eval_package_imports_no_llm_sdk.py`) AST-walks every `.py` file under `src/codegenie/eval/` and rejects any `import anthropic | openai | langchain | langgraph | transformers`. Both fail loud at CI, not at runtime.

The `__init__.py` re-exports exactly the nine names Phase 7 / Phase 11 / Phase 13 consumers will pin: `register_task_class`, `TaskClassRegistry`, `default_registry`, `TaskClass`, `BenchCase`, `BenchScore`, `BenchRunReport`, `PromotionVerdict`, `Rubric`. Anything more is API debt; anything less breaks downstream phases.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Public interface` (each `src/codegenie/eval/*.py` entry lists what it exports) — synthesize into a single `__init__.py` re-export.
  - `../phase-arch-design.md §Testing strategy — Unit` — names `test_bench_score_static.py` and `test_breakdown_keys_static.py` as load-bearing; this story owns the first (and a parallel `test_eval_package_imports_no_llm_sdk.py`). The breakdown-key static test will be added per task class as benches land (S5-01, S6-01); the field-walking version lives here.
  - `../phase-arch-design.md §CI gates` — both files block merge.
  - `../phase-arch-design.md §Cross-cutting concerns — No-LLM-SDK import discipline` (in `stories/README.md`) — `src/codegenie/eval/**/*.py` may not import `anthropic`, `openai`, `langchain`, `langgraph`, `transformers`.
- **Phase ADRs:**
  - `../ADRs/0008-breakdown-keys-strenum-with-substring-ban.md` — the substring list is `confidence`, `llm`, `self_reported`, `model_says`; *value*-level enforcement; shared with Phase 5 ADR-0014.
- **Production / cross-phase precedent:**
  - `../../05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — the original field-name-walking ban; this story ports the *recursive field walker* mechanic.
  - `../../../production/adrs/0008-objective-signal-trust-score.md` — the commitment both bans preserve ("facts, not judgments").
  - `../../00-bullet-tracer-foundations/stories/S1-05-ci-fence-import-linter.md` (if present) — Phase 0's import-linter contract that this story extends.
- **This phase, earlier stories:**
  - S1-01 — `errors.py` (not re-exported; consumers do `from codegenie.eval.errors import ...`).
  - S1-02 — `BenchCase`, `BenchScore`, `BenchRunReport`, `PromotionVerdict` (and `FailureMode` — intentionally *not* in the public ≤ 9 surface; consumers reach it through `BenchScore.failure_modes`).
  - S1-03 — `register_task_class`, `TaskClassRegistry`, `default_registry`, `TaskClass`.
  - S1-04 — `Rubric`.

## Goal

Wire `src/codegenie/eval/__init__.py` re-exporting exactly nine names; land `tests/unit/test_bench_score_static.py` (recursive field-graph substring ban) and `tests/unit/test_eval_package_imports_no_llm_sdk.py` (AST-walking SDK-import ban) as CI-blocking gates.

## Acceptance criteria

- [ ] `src/codegenie/eval/__init__.py` re-exports **exactly** these nine names: `register_task_class`, `TaskClassRegistry`, `default_registry`, `TaskClass`, `BenchCase`, `BenchScore`, `BenchRunReport`, `PromotionVerdict`, `Rubric`. `__all__` enumerates all nine; `from codegenie.eval import *` exposes all nine and nothing else.
- [ ] `FailureMode` is intentionally **not** in `__all__` — it is reached via `BenchScore.failure_modes`. The red test asserts its absence; widening the public surface requires an ADR amendment.
- [ ] `tests/unit/test_bench_score_static.py` recursively walks the Pydantic field graph reachable from `BenchScore`, `BenchRunReport`, and `PromotionVerdict`; rejects any field name containing `confidence`, `llm`, `self_reported`, or `model_says` (case-insensitive substring match per ADR-0008).
- [ ] `tests/unit/test_eval_package_imports_no_llm_sdk.py` AST-walks every `.py` file under `src/codegenie/eval/` (via `ast.parse` + `ast.walk`); for every `ast.Import` and `ast.ImportFrom`, asserts the module root is not in `{"anthropic", "openai", "langchain", "langgraph", "transformers"}`. Failure names the file and line.
- [ ] Both static tests fail loudly when a synthetic violation is injected: the red test §TDD plan demonstrates the failure injection.
- [ ] Both static tests execute in ≤ 200 ms combined (they are AST-only; no imports of the modules they check).
- [ ] `from codegenie.eval import BenchScore, BenchCase, BenchRunReport, PromotionVerdict, Rubric, TaskClass, TaskClassRegistry, default_registry, register_task_class` succeeds; mypy `--strict` resolves all nine names through the package.
- [ ] The red tests from §TDD plan exist, were committed at the red marker, and are now green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest tests/unit/test_eval_public_surface.py tests/unit/test_bench_score_static.py tests/unit/test_eval_package_imports_no_llm_sdk.py` all pass.

## Implementation outline

1. Write all three test files first (red); confirm `ImportError` for the public-surface test and substantive failures for the two static guards.
2. Edit `src/codegenie/eval/__init__.py` (S1-01 left it stubbed):
   - Imports from sibling modules — `from codegenie.eval.models import BenchCase, BenchScore, BenchRunReport, PromotionVerdict`, `from codegenie.eval.registry import TaskClass, TaskClassRegistry, default_registry, register_task_class`, `from codegenie.eval.rubric import Rubric`.
   - `__all__ = ["BenchCase", "BenchRunReport", "BenchScore", "PromotionVerdict", "Rubric", "TaskClass", "TaskClassRegistry", "default_registry", "register_task_class"]` (alphabetical, exactly nine).
   - Module docstring naming `../phase-arch-design.md §Component design — Public interface` as the source-of-truth for the nine names.
3. Implement `tests/unit/test_bench_score_static.py`:
   - Walk Pydantic field graph: for each of `BenchScore`, `BenchRunReport`, `PromotionVerdict`, get `model.model_fields: dict[str, FieldInfo]`; recurse into nested models (e.g., `BenchScore.failure_modes`'s annotation drops to `FailureMode`); collect every `(model_qualname, field_name)` tuple.
   - For every field name, assert no banned substring is present (case-insensitive).
   - Plant a synthetic-violation comment block (the "self-test") showing the test fails on a faux `LlmConfidence` field — this is documentation, not executed code.
4. Implement `tests/unit/test_eval_package_imports_no_llm_sdk.py`:
   - `pathlib.Path("src/codegenie/eval").rglob("*.py")` → for each file, `ast.parse(text)` → `ast.walk` → collect `ast.Import.names` and `ast.ImportFrom.module` (just the top-level root).
   - Assert root not in `{"anthropic", "openai", "langchain", "langgraph", "transformers"}`; on failure, message names file path + lineno + offending import.
5. Run all gates: `ruff format`, `ruff check`, `mypy --strict src/codegenie/eval/`, `pytest tests/unit/test_eval_*.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/unit/test_eval_public_surface.py`, `tests/unit/test_bench_score_static.py`, `tests/unit/test_eval_package_imports_no_llm_sdk.py`.

```python
# tests/unit/test_eval_public_surface.py
import codegenie.eval as pkg

EXPECTED_PUBLIC = frozenset({
    "BenchCase", "BenchRunReport", "BenchScore", "PromotionVerdict", "Rubric",
    "TaskClass", "TaskClassRegistry", "default_registry", "register_task_class",
})


def test_public_surface_is_exactly_nine_names():
    # Adding/removing without an ADR amendment fails CI. Consumers in
    # Phase 7 / Phase 11 / Phase 13 pin against this set.
    assert set(pkg.__all__) == EXPECTED_PUBLIC
    assert len(pkg.__all__) == 9


def test_failure_mode_is_not_public():
    # FailureMode is reached via BenchScore.failure_modes; widening the surface
    # requires an ADR amendment per ../phase-arch-design.md §Component design.
    assert "FailureMode" not in pkg.__all__


def test_all_nine_names_resolve_via_package_root():
    for name in EXPECTED_PUBLIC:
        assert getattr(pkg, name) is not None
```

```python
# tests/unit/test_bench_score_static.py
"""Recursive Pydantic field-graph walker per ADR-0008 + Phase 5 ADR-0014.

Banned substrings (case-insensitive): confidence, llm, self_reported, model_says.
The test fails the first time a smuggling field name slips in via ADR-amendment
or via cargo-cult expansion of a wire type. This is the load-bearing structural
defense Phase 5 ADR-0014 pioneers, ported to the Phase 6.5 wire types.
"""
from pydantic import BaseModel

from codegenie.eval import BenchRunReport, BenchScore, PromotionVerdict

BANNED = ("confidence", "llm", "self_reported", "model_says")


def _walk(model: type[BaseModel], seen: set[type]) -> list[tuple[str, str]]:
    """Returns list of (model_qualname, field_name); recurses into nested BaseModels."""
    if model in seen:
        return []
    seen.add(model)
    fields: list[tuple[str, str]] = []
    for field_name, finfo in model.model_fields.items():
        fields.append((model.__qualname__, field_name))
        ann = finfo.annotation
        # Recurse into any BaseModel inside the annotation (tuple/list/dict args, Optional, etc.).
        for nested in _candidate_models(ann):
            fields.extend(_walk(nested, seen))
    return fields


def _candidate_models(annotation) -> list[type]:  # type: ignore[no-untyped-def]
    import typing
    out: list[type] = []
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        out.append(annotation)
    args = typing.get_args(annotation) or ()
    for a in args:
        out.extend(_candidate_models(a))
    return out


def test_no_field_name_contains_smuggling_substring():
    fields = (
        _walk(BenchScore, set())
        + _walk(BenchRunReport, set())
        + _walk(PromotionVerdict, set())
    )
    offenders = [(m, f) for (m, f) in fields if any(b in f.lower() for b in BANNED)]
    assert offenders == [], (
        f"LLM-judgment-smuggling defense breached. Offending (model, field): "
        f"{offenders}. See ADR-0008 + Phase 5 ADR-0014."
    )


def test_walker_actually_recurses_into_nested_models():
    # Sanity: BenchScore.failure_modes drops to FailureMode; walker must include
    # FailureMode's fields. If this returns [] the walker is broken and the
    # substring ban is silently vacuous.
    fields = _walk(BenchScore, set())
    qualnames = {m for (m, _) in fields}
    assert "FailureMode" in qualnames
```

```python
# tests/unit/test_eval_package_imports_no_llm_sdk.py
"""AST-walk src/codegenie/eval/**/*.py; reject imports of LLM SDKs.

The harness must never import anthropic, openai, langchain, langgraph, or
transformers. The SUT may; the harness may not. This is the structural
extension of Phase 0's import-linter contract per stories/README.md
§Cross-cutting concerns — No-LLM-SDK import discipline.
"""
import ast
from pathlib import Path

BANNED_ROOTS = frozenset({"anthropic", "openai", "langchain", "langgraph", "transformers"})
EVAL_PKG = Path(__file__).resolve().parents[2] / "src" / "codegenie" / "eval"


def _banned_imports_in(py_file: Path) -> list[tuple[int, str]]:
    tree = ast.parse(py_file.read_text())
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in BANNED_ROOTS:
                    found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            if root in BANNED_ROOTS:
                found.append((node.lineno, node.module))
    return found


def test_no_llm_sdk_imports_in_eval_package():
    assert EVAL_PKG.is_dir(), f"eval package not found at {EVAL_PKG}"
    py_files = sorted(EVAL_PKG.rglob("*.py"))
    assert py_files, "AST walker found no .py files — scan path is wrong"

    offenders: list[str] = []
    for f in py_files:
        for lineno, mod in _banned_imports_in(f):
            offenders.append(f"{f}:{lineno}: import {mod}")

    assert offenders == [], (
        "Banned LLM-SDK imports detected in src/codegenie/eval/ — the harness "
        "must remain SDK-free per stories/README.md §Cross-cutting concerns:\n"
        + "\n".join(offenders)
    )


def test_walker_scanned_at_least_four_files():
    # Sanity floor: errors.py + models.py + registry.py + rubric.py + __init__.py = 5.
    # If this drops below 4 the walker is silently empty.
    assert len(list(EVAL_PKG.rglob("*.py"))) >= 4
```

Run all three; confirm `ImportError` on the public-surface test and `AssertionError` (or at least failures the green pass will resolve). Commit the red marker.

### Green — make it pass

- Edit `src/codegenie/eval/__init__.py` per §Implementation outline #2 — five `from ... import ...` lines, one `__all__` listing nine names alphabetically.
- The two static-guard tests are *defensive* — they pass *because* nobody has yet violated them. Confirm:
  - `pytest tests/unit/test_bench_score_static.py` is green (no banned substring in any of the three model graphs).
  - `pytest tests/unit/test_eval_package_imports_no_llm_sdk.py` is green (no banned import anywhere in `src/codegenie/eval/`).

### Refactor — clean up

- Add `__version__: Final[str] = "0.1.0"` to `__init__.py` only if `phase-arch-design.md` requires it — at the time of writing it does not; do not add. Consumers reach versioning through `codegenie.__version__` (Phase 0).
- `__init__.py` ≤ 20 lines including the docstring.
- Refactor the recursive walker in `test_bench_score_static.py` so `_walk` and `_candidate_models` are *the entire helper surface*; one extra helper is one too many for a test of this size.
- Add a one-line comment to `__init__.py` reading `# Public surface pinned by test_eval_public_surface.py — see ADR-0008 / Phase 5 ADR-0014.`
- Confirm the AST-walking import test handles `from foo import bar` and `import foo.bar` symmetrically — both must extract `foo` as the root.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/__init__.py` | Modify — wire the nine public names from S1-02, S1-03, S1-04 |
| `tests/unit/test_eval_public_surface.py` | New file — pins the nine public names exactly |
| `tests/unit/test_bench_score_static.py` | New file — recursive Pydantic field-graph substring ban |
| `tests/unit/test_eval_package_imports_no_llm_sdk.py` | New file — AST-walking LLM-SDK import ban |

## Out of scope

- **`test_breakdown_keys_static.py` (the per-task-class StrEnum-value ban)** — handled by S5-01 (vuln-remediation) and S6-01 (distroless); this story's `test_bench_score_static.py` is the *field-name* defense, and the StrEnum-value defense lands when the first task class registers a `BreakdownKey`.
- **Fence-CI seven assertions (the AST + filesystem walk over `bench/<name>/`)** — handled by S7-01; this story owns the package-scoped static defenses, not the bench-scoped ones.
- **Import-linter contract update for Phase 0** — `phase-arch-design.md §CI gates` says this story *extends* Phase 0's contract. The pragmatic extension is the new AST-walking test (this story); editing the Phase 0 `importlinter.ini` is deferred — not needed at this phase boundary because the new test enforces the rule independently.
- **Extending the banned-substring list** — any addition requires amending ADR-0008 + Phase 5 ADR-0014 in the same change-train (cross-phase contract).
- **Adding `FailureMode` to the public surface** — explicitly forbidden by AC #2; widening requires an ADR amendment.

## Notes for the implementer

- The nine-name limit is *the* discipline. Adding a tenth ("just `FailureMode`, it's harmless") starts the API-debt accretion that `extension by addition` is designed to prevent. The public surface is the load-bearing contract Phase 7 / Phase 11 / Phase 13 will pin against — any addition is a forever commitment.
- The substring list (`confidence`, `llm`, `self_reported`, `model_says`) lives in *two* test files, one ADR (Phase 5 ADR-0014), and one fence-CI assertion (S7-01 #5). Future expansions must touch all four locations in the same PR — the ADR text explicitly notes this is "the single source-of-truth shared with Phase 5 ADR-0014."
- `_candidate_models` is the subtle part: Pydantic v2 nests `BaseModel`s inside `tuple[FailureMode, ...]`, `Optional[X]`, etc. Use `typing.get_args(annotation)` recursively. Test `test_walker_actually_recurses_into_nested_models` is the structural marker that the walker is not silently vacuous — a future refactor that breaks `_candidate_models` will fail there before it fails on a real smuggling field.
- The AST-walking test uses `Path(__file__).resolve().parents[2]` to locate `src/codegenie/eval/`. This assumes the test lives at `tests/unit/test_*.py` and the package at `src/codegenie/eval/` — both are Phase 0 conventions. If the layout is different in this repo (check via `ls`), adjust the path computation accordingly; otherwise the test silently scans nothing and is vacuous (the `test_walker_scanned_at_least_four_files` sanity floor catches this).
- `from codegenie.eval import *` is the public contract API. Some downstream consumers will do this; others will do `from codegenie.eval import BenchScore`. Both must work; `__all__` is the gate for the star-import.
- mypy `--strict` over `src/codegenie/eval/__init__.py` must resolve all nine names. If it complains about `default_registry: TaskClassRegistry` not having an explicit type at the re-export site, add `default_registry: TaskClassRegistry  # re-exported from registry.py`.
- Per `phase-arch-design.md §Performance envelope`, the package's cold-start cost must stay under 600 ms (matching `codegenie gather`). The `__init__.py` imports *only* model classes — no `pydantic` deep-load, no `tomllib`, no `yaml`. If you find yourself adding heavy imports here, move them to `loader.py` (S2-01) where they belong.
- The AST-walking test does **not** import the modules it scans (it `ast.parse`s text). This is intentional: if the test imported the modules, an `import anthropic` would fail at the test-import step rather than the assertion step, and the error message would be less actionable. Keep it AST-only.
- Watch out: a contributor could try to bypass the SDK-import ban by writing `__import__("anthropic")` or `importlib.import_module("anthropic")` — neither is caught by `ast.Import` / `ast.ImportFrom`. This is an *acknowledged residual* (same as the breakdown-key dynamic-value-computation residual called out in ADR-0008); CODEOWNERS on `src/codegenie/eval/` is the compensating control. Phase 16 may extend.
