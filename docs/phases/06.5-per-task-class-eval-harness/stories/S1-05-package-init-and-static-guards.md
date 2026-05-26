# Story S1-05 — Package `__init__` + static smuggling/SDK guards

**Step:** Step 1 — Establish contracts: package scaffold, wire models, registry, Protocol
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-02, S1-03, S1-04
**ADRs honored:** ADR-0008 (substring ban at the dict-key / breakdown-key value layer), Phase 5 ADR-0014 (`ObjectiveSignals` substring-ban field-walking precedent — ported), Phase 0 import-linter contract (parallel structural defense at `codegenie.eval.**`), production ADR-0008 (`objective-signal trust score` — facts not LLM judgment)

## Validation notes (2026-05-26)

`phase-story-validator` v1 hardened this story. Four critics ran (Coverage, Test-Quality, Consistency, Design-Patterns); no `NEEDS RESEARCH` — every pattern is precedented in this repo (`src/codegenie/_fence.py:50` for the `Final[frozenset[str]]` source-of-truth pattern; `tests/fence/_phase4_scanner.py:walk_imports` for the *single* AST-import-walking kernel; `tests/fence/_fixtures_phase4/` + `tests/fence/test_pyproject_fence_phase4_negatives.py` for the planted-positive-control fixture pattern). Findings converged on:

1. **AC-4's "synthetic violation injection" was documentation, not executed code** — both static guards would have passed forever even if the detection mechanism was completely broken (mutation: shrink `BANNED` to `()` — no test fails). Ported the planted-positive-control pattern from `tests/fence/_fixtures_phase4/`.
2. **Substring list was duplicated inline** (story's own Notes admit it lives in 4 future locations). Rule-of-three crossed by the story's own enumeration. Extracted `src/codegenie/eval/_smuggling.py` (private, leading-underscore — does NOT widen the 9-name public surface) as the structural source-of-truth, mirroring `_fence.py:FORBIDDEN_LLM_SDKS`.
3. **AST walker re-implemented `tests/fence/_phase4_scanner.py:walk_imports`** — Phase-4's deliberate lesson ("there is exactly one AST-walking implementation under `tests/fence/`") was about to be silently violated. Reuse `walk_imports`; the missing `node.level == 0` relative-import guard comes for free.
4. **Tests were placed in `tests/unit/`** but the codebase convention puts structural-defense / AST-walking guards under `tests/fence/`. Moved.
5. **Recursion-shape coverage matrix missing** — sanity test pinned only `tuple[FailureMode, ...]`. Added parametrised synthetic models covering `Optional[X]`, `list[X]`, `dict[str, X]`, `Annotated[X, ...]`, two-level chains, self-referential cycles, and forward-ref annotations under `from __future__ import annotations`.
6. **Import-shape coverage matrix missing** — added planted fixtures across bare / dotted / aliased / multi-name / `from-import` / dotted-from / relative / string-mention-only shapes.

Verdict: **HARDENED.** One block-grade finding (F-COV-4 / F-TQ-1 / F-DP-8 — load-bearing AC-4 documentation problem) and a dozen hardens, all in-place-fixable with patterns precedented in this repo. The mutation set the hardened suite resists: shrink `SMUGGLING_SUBSTRINGS`; narrow `BANNED_ROOTS`; flip `f.lower()` → `f`; drop `node.level == 0`; drop `.split(".", 1)[0]`; rename `__all__` → `_all_`; duplicate an entry in `__all__`; re-export the wrong symbol with the right name; bypass via `__import__("anthropic")` (acknowledged residual — CODEOWNERS compensating); regex-false-positive a docstring mentioning `anthropic` (AST-not-regex guarantee); silently vacuous walker on `from __future__ import annotations`-using models; silently vacuous AST walker when `src/codegenie/eval/` is missing or empty.

See `_validation/S1-05-package-init-and-static-guards.md` for the full audit.

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

### Public-surface contract

- [ ] **AC-1**: `src/codegenie/eval/__init__.py` defines `__all__` containing exactly these nine names, in alphabetical order: `"BenchCase"`, `"BenchRunReport"`, `"BenchScore"`, `"PromotionVerdict"`, `"Rubric"`, `"TaskClass"`, `"TaskClassRegistry"`, `"default_registry"`, `"register_task_class"`. `set(pkg.__all__) == EXPECTED_PUBLIC` AND `len(pkg.__all__) == 9` AND `len(set(pkg.__all__)) == 9` (catches duplicates). Adding any tenth name MUST fail CI; removing any name MUST also fail. `__all__` is the contract boundary for `from codegenie.eval import *` (non-`__all__` symbols may exist in `codegenie.eval.__dict__` as transitive import side-effects; those are not part of the public contract).
- [ ] **AC-2**: `"FailureMode"` is **not** in `__all__`. `FailureMode` is reachable via `BenchScore.model_fields["failure_modes"].annotation` (the typed-via-`BenchScore` path); widening the public surface to expose it directly requires an ADR amendment. Verified by a test that asserts both halves.
- [ ] **AC-3**: For every name in `__all__`, `getattr(pkg, name)` is **identity-equal** to the canonical symbol from its source module: `pkg.BenchScore is codegenie.eval.models.BenchScore`, `pkg.Rubric is codegenie.eval.rubric.Rubric`, `pkg.register_task_class is codegenie.eval.registry.register_task_class`, etc. Mutation guard: re-exporting the wrong symbol with the right name (`pkg.BenchScore = "BenchScore"`) fails this AC; mypy `--strict` alone cannot catch it.
- [ ] **AC-4**: `from codegenie.eval import BenchScore, BenchCase, BenchRunReport, PromotionVerdict, Rubric, TaskClass, TaskClassRegistry, default_registry, register_task_class` succeeds in a fresh interpreter (one process-isolated import).
- [ ] **AC-5**: `__init__.py` module docstring contains the substrings `"ADR-0008"`, `"Phase 5 ADR-0014"`, AND either `"smuggling"` or `"LLM-judgment"` — AST-introspected on the parsed module via `ast.get_docstring`. Mirrors the sibling Protocol-port docstring discipline pinned by S1-04 (`vuln_index/protocol.py:1-15`).

### Smuggling-substring source-of-truth (`_smuggling.py` extraction)

- [ ] **AC-6**: `src/codegenie/eval/_smuggling.py` defines `SMUGGLING_SUBSTRINGS: Final[frozenset[str]] = frozenset({"confidence", "llm", "self_reported", "model_says"})` (canonical lowercase, since the check is `b in field.lower()`). Module docstring names Phase 5 ADR-0014 + Phase 6.5 ADR-0008 as cross-phase contract owners and links to `_fence.py:FORBIDDEN_LLM_SDKS` as the structural precedent. Leading-underscore module name keeps it private — it does NOT appear in `__all__` and is NOT part of the 9-name public surface.
- [ ] **AC-7**: `tests/fence/test_bench_score_static.py` imports `from codegenie.eval._smuggling import SMUGGLING_SUBSTRINGS` and uses it as the **only** source-of-truth — the literal four-string set MUST NOT appear inline in the test file (a `grep -E '"confidence"|"llm"|"self_reported"|"model_says"' tests/fence/test_bench_score_static.py` MUST return empty). When future stories (S3-04 runtime defense-in-depth, S7-01 fence assertion #5) consume the same list, they import from the same source.

### Recursive Pydantic field-graph guard (`test_bench_score_static.py`)

- [ ] **AC-8**: `tests/fence/test_bench_score_static.py` recursively walks the Pydantic field graph reachable from `BenchScore`, `BenchRunReport`, AND `PromotionVerdict`. For every field name `f` reached, the test asserts `not any(b in f.lower() for b in SMUGGLING_SUBSTRINGS)`. The case-insensitive check is verified by a parametrised positive-control test using synthetic models (defined inside the test function, NOT at module scope) — at minimum `LlmConfidence`, `MODEL_SAYS_score`, `llm_x`, `x_confidence`, `self_reported_rating`, `nested_models_say_yes` — each MUST be flagged.
- [ ] **AC-9** (recursion-shape matrix): The walker correctly descends into every Pydantic-supported nested-annotation shape. Parametrised positive-control tests use synthetic local models that contain a banned field (`llm_confidence`) inside each container — `tuple[X, ...]`, `list[X]`, `dict[str, X]`, `Optional[X]` (= `X | None`), `Union[X, Y]`, `Annotated[X, Field(...)]`, and a two-level chain `A → B → C` — and assert the walker flags the banned field in every container shape. The walker terminates safely on a self-referential model (`class Tree(BaseModel): children: list["Tree"]`).
- [ ] **AC-10** (forward-ref correctness): The walker correctly handles models defined under `from __future__ import annotations`. It uses Pydantic's `model.model_rebuild()` (or `typing.get_type_hints(model, ...)`) so string annotations are resolved to types before introspection. Verified by a synthetic test that defines a model under `from __future__ import annotations` with a nested `BaseModel` containing a banned field — the walker MUST flag it.
- [ ] **AC-11** (the sanity floor): `test_walker_actually_recurses_into_nested_models` MUST PASS today against the real wire types — at minimum the qualname set returned by `_walk(BenchScore, set())` MUST include `"FailureMode"` (proves at least one level of descent against production wire types). Vacuous-walker regression catcher.

### AST-walking LLM-SDK-import guard (`test_eval_package_imports_no_llm_sdk.py`)

- [ ] **AC-12** (reuse the single AST-walking kernel): `tests/fence/test_eval_package_imports_no_llm_sdk.py` calls `tests/fence/_phase4_scanner.py::walk_imports(files, forbidden=BANNED_ROOTS)` — it MUST NOT re-implement `ast.walk` / `ast.Import` / `ast.ImportFrom` inline (per Phase 4's load-bearing lesson: "there is exactly one AST-walking implementation under `tests/fence/`"). This brings the `node.level == 0` relative-import guard, the multi-name iteration, the dotted-name `.split(".", 1)[0]` extraction, and the binary-file `SyntaxError` skip for free.
- [ ] **AC-13** (banned set): `BANNED_ROOTS: Final[frozenset[str]] = frozenset({"anthropic", "openai", "langchain", "langgraph", "transformers"})` — matches arch §CI gates (line 1026) verbatim. Path-scoped to `src/codegenie/eval/**` (the eval *harness* may not import these); the closure-scoped `_fence.FORBIDDEN_LLM_SDKS` is a different mechanism over a different artifact (`[project].dependencies`) — they do not derive from each other (see Notes for implementer).
- [ ] **AC-14** (import-shape matrix via planted fixtures): Add `tests/fence/_fixtures_eval/` containing at minimum these `.py.txt` planted-violator fixtures (mirroring `tests/fence/_fixtures_phase4/`):
  - `violator_eval_imports_anthropic_bare.py.txt` — `import anthropic`
  - `violator_eval_imports_anthropic_dotted.py.txt` — `import anthropic.client`
  - `violator_eval_imports_anthropic_aliased.py.txt` — `import anthropic as a`
  - `violator_eval_imports_openai_and_anthropic.py.txt` — `import openai, anthropic`
  - `violator_eval_from_openai.py.txt` — `from openai import OpenAI`
  - `violator_eval_from_dotted_anthropic.py.txt` — `from anthropic.client import X`
  - `benign_eval_mentions_anthropic_in_string_only.py.txt` — string literal `"anthropic"` + a comment, NO import
  - `benign_eval_relative_import.py.txt` — `from . import errors` (relative import — MUST NOT trip)

  Add `tests/fence/test_eval_static_negatives.py` with a parametrised test: copy each fixture to a `tmp_path` mirror of the package, call `walk_imports`, assert (a) every violator fixture is flagged, (b) every benign fixture returns an empty list. This is the mutation-resistance test AC-4 of the original story promised but did not deliver. **Acknowledged out-of-scope:** `__import__("anthropic")` and `importlib.import_module("anthropic")` — AST walker cannot detect these; CODEOWNERS on `src/codegenie/eval/` is the compensating control (same posture as ADR-0008 §Tradeoffs row 3 for dynamic StrEnum-value computation).
- [ ] **AC-15** (live scanner over the real package): `walk_imports(sorted(EVAL_PKG.rglob("*.py")), forbidden=BANNED_ROOTS)` returns `[]` against the live `src/codegenie/eval/**/*.py` tree.

### Vacuous-scan defenses (named-set asserts, not magic numbers)

- [ ] **AC-16**: The live scanner's input MUST include every load-bearing module: `{f.name for f in EVAL_PKG.rglob("*.py")} >= {"__init__.py", "errors.py", "models.py", "registry.py", "rubric.py"}`. If a load-bearing module is renamed or deleted, the test fails loudly naming the missing file — not silently pass on a `>= 4` magic threshold.
- [ ] **AC-17**: `EVAL_PKG.is_dir()` (the package directory exists); the scanner's file list is non-empty. Failure message names the resolved absolute path.

### Structural-not-wall-clock performance defense

- [ ] **AC-18** (structural perf observable, not wall-clock): Both static-guard test modules MUST be AST-only. A meta-test grep-scans the two test files and asserts they do NOT contain `importlib.import_module(`, `import anthropic`, `import openai`, `import langchain`, `import langgraph`, or `import transformers` anywhere outside of docstrings/comments (i.e., not as live import statements). The original "≤ 200 ms" wall-clock claim is unreliable on CI variance; the structural observable (the tests don't import the modules they police) is what made the perf claim achievable in the first place and is what should be pinned.

### Process / gate ACs

- [ ] **AC-19**: The red tests from §TDD plan (including the planted-fixture parametrised tests) exist, were committed at the red marker, AND are now green.
- [ ] **AC-20**: `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/eval/`, AND `pytest tests/fence/test_eval_package_public_surface.py tests/fence/test_bench_score_static.py tests/fence/test_eval_package_imports_no_llm_sdk.py tests/fence/test_eval_static_negatives.py` all pass.

## Implementation outline

1. **Land the smuggling source-of-truth FIRST** (private constant module). Create `src/codegenie/eval/_smuggling.py`:
   - Module docstring: cite Phase 6.5 ADR-0008, Phase 5 ADR-0014, link `_fence.py:FORBIDDEN_LLM_SDKS` as the structural precedent (per AC-6).
   - Body: `SMUGGLING_SUBSTRINGS: Final[frozenset[str]] = frozenset({"confidence", "llm", "self_reported", "model_says"})` — canonical lowercase.
   - Leading-underscore module name — NOT re-exported by `__init__.py` (NOT in `__all__`).
2. Write the four test files first (red); confirm `ImportError` for the public-surface test, planted-fixture parametrisations fail substantively for the two static guards, and the live scanners are currently green-by-vacuity (which is fine — the planted-fixture tests prove the mechanism works).
3. Edit `src/codegenie/eval/__init__.py` (S1-01 left it stubbed):
   - Module docstring (per AC-5) cites `ADR-0008`, `Phase 5 ADR-0014`, mentions `smuggling` / `LLM-judgment`. Mirror `src/codegenie/vuln_index/__init__.py:1-29` and `src/codegenie/probes/__init__.py:1-14` shape.
   - Imports from sibling modules (absolute, grouped alphabetically by submodule per sibling convention) — `from codegenie.eval.models import BenchCase, BenchRunReport, BenchScore, PromotionVerdict`, `from codegenie.eval.registry import TaskClass, TaskClassRegistry, default_registry, register_task_class`, `from codegenie.eval.rubric import Rubric`.
   - `__all__ = ["BenchCase", "BenchRunReport", "BenchScore", "PromotionVerdict", "Rubric", "TaskClass", "TaskClassRegistry", "default_registry", "register_task_class"]` (alphabetical, exactly nine).
4. Implement `tests/fence/test_eval_package_public_surface.py` per AC-1..AC-5: exact-set equality, length, set-of-set length (duplicate guard), `FailureMode` absence + reachability, identity-equality to source-module symbols, module-docstring `ast.get_docstring`-introspected.
5. Implement `tests/fence/test_bench_score_static.py`:
   - Walk Pydantic field graph: for each of `BenchScore`, `BenchRunReport`, `PromotionVerdict`, get `model.model_fields: dict[str, FieldInfo]`; call `model.model_rebuild()` first (or use `typing.get_type_hints(model, include_extras=True)`) so forward refs under `from __future__ import annotations` resolve to types (per AC-10).
   - `_candidate_models(annotation)` recursively descends via `typing.get_args(annotation)` — handles `tuple[X, ...]`, `list[X]`, `dict[K, V]` (both K and V), `Optional[X]` (= `Union[X, None]`), `Union[X, Y]`, `Annotated[X, ...]`.
   - For every field name `f`, assert `not any(b in f.lower() for b in SMUGGLING_SUBSTRINGS)` — imported from `codegenie.eval._smuggling` (per AC-7; the literal four-string tuple MUST NOT appear inline).
   - Parametrised positive-control tests use synthetic local models (defined inside the test function so they don't pollute the module's import-time field graph) — per AC-8 + AC-9. Self-referential model verifies the `seen: set[type]` cycle guard works (per AC-9).
6. Implement `tests/fence/test_eval_package_imports_no_llm_sdk.py`:
   - Reuse `from tests.fence._phase4_scanner import walk_imports, ImportViolation`. **Do NOT re-implement `ast.walk` / `ast.Import` / `ast.ImportFrom` inline** (per AC-12 and Phase-4's deliberate "one AST kernel" lesson).
   - `BANNED_ROOTS: Final[frozenset[str]] = frozenset({"anthropic", "openai", "langchain", "langgraph", "transformers"})` (per AC-13). `from typing import Final`.
   - Live test: `assert walk_imports(sorted(EVAL_PKG.rglob("*.py")), forbidden=BANNED_ROOTS) == []` (per AC-15). Diagnostic message names file:package on failure (the `ImportViolation` value carries both).
   - Named-set sanity floor (per AC-16): `{f.name for f in EVAL_PKG.rglob("*.py")} >= {"__init__.py", "errors.py", "models.py", "registry.py", "rubric.py"}`.
7. Implement `tests/fence/test_eval_static_negatives.py` and `tests/fence/_fixtures_eval/` per AC-14:
   - Eight `.py.txt` fixtures listed in AC-14 (mirror `tests/fence/_fixtures_phase4/` naming).
   - One parametrised test takes (fixture_filename, expected_violation_count) tuples and asserts `walk_imports` returns the expected number of `ImportViolation` records when scanning the planted fixture. Violators expect `>= 1`; benign fixtures (string-mention + relative-import) expect `== 0`.
   - Use `tmp_path` + `shutil.copy` of `.py.txt` → `.py` so the planted fixture is well-formed Python at scan time. The `.py.txt` suffix prevents accidental import by pytest collection.
8. Implement the structural perf observable per AC-18: a small meta-test in `tests/fence/test_eval_package_imports_no_llm_sdk.py` (or sibling) grep-scans the two static-guard test files for live `import anthropic` / `import openai` / `importlib.import_module(` statements outside docstrings/comments — using `tokenize` rather than naive `read_text` so string literals don't false-positive.
9. Run all gates: `ruff format`, `ruff check`, `mypy --strict src/codegenie/eval/`, `pytest tests/fence/test_eval_*.py tests/fence/test_bench_score_static.py`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file paths: `tests/fence/test_eval_package_public_surface.py`, `tests/fence/test_bench_score_static.py`, `tests/fence/test_eval_package_imports_no_llm_sdk.py`, `tests/fence/test_eval_static_negatives.py`. Fixtures: `tests/fence/_fixtures_eval/*.py.txt`.

```python
# tests/fence/test_eval_package_public_surface.py
"""Public-surface contract for codegenie.eval — pins the 9-name re-export.

See ADR-0008, Phase 5 ADR-0014, phase-arch-design.md §Component design — Public
interface. Adding any tenth name requires an ADR amendment per the
extension-by-addition discipline (CLAUDE.md "Extension by addition").
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

import codegenie.eval as pkg
import codegenie.eval.models as _models
import codegenie.eval.registry as _registry
import codegenie.eval.rubric as _rubric

EXPECTED_PUBLIC = frozenset({
    "BenchCase", "BenchRunReport", "BenchScore", "PromotionVerdict", "Rubric",
    "TaskClass", "TaskClassRegistry", "default_registry", "register_task_class",
})


def test_public_surface_is_exactly_nine_names() -> None:
    # AC-1. Adding/removing without an ADR amendment fails CI.
    # Set-equality catches additions AND removals; len() catches duplicate-with-
    # spurious-name pattern; len(set(...)) catches duplicates directly.
    assert set(pkg.__all__) == EXPECTED_PUBLIC
    assert len(pkg.__all__) == 9
    assert len(set(pkg.__all__)) == 9, "duplicate entry in __all__"


def test_failure_mode_is_not_in_all_but_is_reachable_via_bench_score() -> None:
    # AC-2. The contract is: FailureMode is reached via BenchScore.failure_modes,
    # not via package root. Widening requires an ADR amendment.
    assert "FailureMode" not in pkg.__all__
    # Reachability: BenchScore.failure_modes annotation is tuple[FailureMode, ...].
    # The annotation MUST be non-None and contain FailureMode in its type args.
    import typing
    ann = pkg.BenchScore.model_fields["failure_modes"].annotation
    assert ann is not None, "BenchScore.failure_modes annotation missing"
    args = typing.get_args(ann)
    qualnames = {getattr(a, "__qualname__", None) for a in args}
    assert "FailureMode" in qualnames, (
        f"FailureMode unreachable via BenchScore.failure_modes; args={args!r}"
    )


def test_each_public_name_is_identity_equal_to_source_module_symbol() -> None:
    # AC-3. Mutation guard: `pkg.BenchScore = "BenchScore"` is the regression
    # this catches and mypy can't.
    assert pkg.BenchCase is _models.BenchCase
    assert pkg.BenchRunReport is _models.BenchRunReport
    assert pkg.BenchScore is _models.BenchScore
    assert pkg.PromotionVerdict is _models.PromotionVerdict
    assert pkg.Rubric is _rubric.Rubric
    assert pkg.TaskClass is _registry.TaskClass
    assert pkg.TaskClassRegistry is _registry.TaskClassRegistry
    assert pkg.default_registry is _registry.default_registry
    assert pkg.register_task_class is _registry.register_task_class


def test_all_nine_names_resolve_in_fresh_interpreter() -> None:
    # AC-4. Reimport in a forced fresh module to catch any startup-import error
    # that the test-process global cache might mask.
    importlib.reload(pkg)
    for name in EXPECTED_PUBLIC:
        assert hasattr(pkg, name), f"{name} missing after reload"


def test_init_docstring_cites_load_bearing_adrs() -> None:
    # AC-5. Module docstring must cite ADR-0008, Phase 5 ADR-0014, and
    # smuggling/LLM-judgment framing. AST-introspected so docstring drift is
    # caught at CI time, not in code review.
    init_path = Path(_models.__file__).parent / "__init__.py"
    tree = ast.parse(init_path.read_text(encoding="utf-8"))
    doc = ast.get_docstring(tree) or ""
    assert "ADR-0008" in doc, "init docstring missing ADR-0008 citation"
    assert "Phase 5 ADR-0014" in doc, "init docstring missing Phase 5 ADR-0014 citation"
    assert ("smuggling" in doc.lower() or "llm-judgment" in doc.lower()), (
        "init docstring missing smuggling/LLM-judgment framing"
    )
```

```python
# tests/fence/test_bench_score_static.py
"""Recursive Pydantic field-graph walker per ADR-0008 + Phase 5 ADR-0014.

Banned substrings live at codegenie.eval._smuggling.SMUGGLING_SUBSTRINGS — the
literal four-string set MUST NOT appear inline here (AC-7). The walker is the
load-bearing structural defense Phase 5 ADR-0014 pioneers, ported to Phase 6.5
wire types and parametrised against synthetic positive-controls per AC-8/9/10.
"""
from __future__ import annotations

import typing
from typing import Annotated, Union

import pytest
from pydantic import BaseModel, ConfigDict, Field

from codegenie.eval import BenchRunReport, BenchScore, PromotionVerdict
from codegenie.eval._smuggling import SMUGGLING_SUBSTRINGS


def _candidate_models(annotation: object) -> list[type[BaseModel]]:
    out: list[type[BaseModel]] = []
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        out.append(annotation)
    for a in typing.get_args(annotation) or ():
        out.extend(_candidate_models(a))
    return out


def _walk(model: type[BaseModel], seen: set[type[BaseModel]]) -> list[tuple[str, str]]:
    """Returns (model_qualname, field_name) pairs; recurses into nested BaseModels.

    Calls model.model_rebuild() to resolve forward-ref string annotations under
    `from __future__ import annotations` (AC-10).
    """
    if model in seen:
        return []
    seen.add(model)
    # Forward-ref resolution: get_type_hints over model.__annotations__ runs
    # the same resolution Pydantic does for model_fields[name].annotation,
    # but explicit so the test's invariant is unambiguous.
    try:
        model.model_rebuild()
    except Exception:  # noqa: BLE001 — rebuild can no-op safely
        pass
    out: list[tuple[str, str]] = []
    for field_name, finfo in model.model_fields.items():
        out.append((model.__qualname__, field_name))
        for nested in _candidate_models(finfo.annotation):
            out.extend(_walk(nested, seen))
    return out


def _contains_smuggling(name: str) -> bool:
    return any(b in name.lower() for b in SMUGGLING_SUBSTRINGS)


# ---- Live test against production wire types ---------------------------------

def test_no_field_name_contains_smuggling_substring_in_production_wire_types() -> None:
    # AC-8 live half: no production model carries a banned field name.
    fields = (
        _walk(BenchScore, set())
        + _walk(BenchRunReport, set())
        + _walk(PromotionVerdict, set())
    )
    offenders = [(m, f) for (m, f) in fields if _contains_smuggling(f)]
    assert offenders == [], (
        f"LLM-judgment-smuggling defense breached. Offending (model, field): "
        f"{offenders}. See ADR-0008 + Phase 5 ADR-0014."
    )


def test_walker_actually_recurses_into_nested_models() -> None:
    # AC-11. Sanity floor against production types: BenchScore -> FailureMode.
    # If empty, the substring ban is silently vacuous.
    fields = _walk(BenchScore, set())
    qualnames = {m for (m, _) in fields}
    assert "FailureMode" in qualnames


# ---- Synthetic positive-control matrix (mutation-resistance) ----------------

@pytest.mark.parametrize("banned_name", [
    "llm_score", "llmScore", "LlmScore", "score_llm",                     # llm
    "confidence", "model_confidence", "Confidence", "evidence_confidence",  # confidence
    "self_reported", "self_reported_score", "SelfReportedRating",         # self_reported
    "model_says", "model_says_yes", "ModelSaysScore",                     # model_says
])
def test_walker_flags_synthetic_field_with_banned_substring(banned_name: str) -> None:
    # AC-8 positive-control: defining a synthetic model with a banned field
    # name and confirming the substring check flags it. Models are local to
    # the test (NOT module-scope) so they don't pollute production type graphs.
    fields_dict = {banned_name: (float, 0.0)}
    Synth = type("_Synth", (BaseModel,), {
        "__annotations__": {banned_name: float},
        banned_name: 0.0,
        "model_config": ConfigDict(frozen=True, extra="forbid"),
    })
    walked = _walk(Synth, set())
    names = [f for (_, f) in walked]
    assert banned_name in names, "walker did not return the field at all"
    assert _contains_smuggling(banned_name), (
        f"substring check failed to flag {banned_name!r} — substring ban broken"
    )


# ---- Recursion-shape matrix (AC-9) ------------------------------------------

class _Leaf(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    llm_confidence: float = 0.0


class _InTuple(BaseModel):
    children: tuple[_Leaf, ...]


class _InList(BaseModel):
    children: list[_Leaf]


class _InDictValue(BaseModel):
    children: dict[str, _Leaf]


class _InOptional(BaseModel):
    child: _Leaf | None = None


class _InUnion(BaseModel):
    child: Union[_Leaf, int]


class _InAnnotated(BaseModel):
    child: Annotated[_Leaf, Field(description="...")]


class _ChainB(BaseModel):
    leaf: _Leaf


class _ChainA(BaseModel):
    b: _ChainB


@pytest.mark.parametrize("container", [
    _InTuple, _InList, _InDictValue, _InOptional, _InUnion, _InAnnotated, _ChainA,
])
def test_walker_descends_into_every_container_shape(container: type[BaseModel]) -> None:
    # AC-9. Each container shape MUST surface _Leaf.llm_confidence.
    fields = _walk(container, set())
    offenders = [(m, f) for (m, f) in fields if _contains_smuggling(f)]
    assert offenders, (
        f"walker silently skipped {container.__qualname__} — recursion shape lost"
    )


class _Recursive(BaseModel):
    children: list["_Recursive"] = []


_Recursive.model_rebuild()


def test_walker_terminates_on_self_referential_model() -> None:
    # AC-9. Cycle guard via seen-set: a self-referential model MUST NOT infinite-loop.
    fields = _walk(_Recursive, set())
    assert fields, "walker returned empty on a recursive model"


# ---- Forward-ref correctness (AC-10) ----------------------------------------

def test_walker_resolves_forward_ref_annotations() -> None:
    # AC-10. Inline a model defined under `from __future__ import annotations`
    # (this whole file is — see top). Its nested annotation must resolve to
    # _Leaf so the walker can descend.
    class _ForwardRef(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")
        leaf: _Leaf  # under `from __future__ import annotations` this is a string

    fields = _walk(_ForwardRef, set())
    offenders = [(m, f) for (m, f) in fields if _contains_smuggling(f)]
    assert offenders, (
        "walker failed to resolve forward-ref annotation; "
        "substring ban silently vacuous on PEP-563 modules"
    )
```

```python
# tests/fence/test_eval_package_imports_no_llm_sdk.py
"""AST-walk src/codegenie/eval/**/*.py; reject imports of LLM SDKs.

Reuses tests/fence/_phase4_scanner.py:walk_imports — the single AST-walking
kernel for the repo's import fences (per AC-12 and Phase-4's deliberate "one
AST implementation" lesson). The eval-harness path-scoped ban is PARALLEL to
Phase 0's closure-scoped `FORBIDDEN_LLM_SDKS` (different mechanism, different
artifact) — see Notes for implementer.
"""
from __future__ import annotations

from pathlib import Path
from typing import Final

from tests.fence._phase4_scanner import walk_imports

BANNED_ROOTS: Final[frozenset[str]] = frozenset({
    "anthropic", "openai", "langchain", "langgraph", "transformers",
})
EVAL_PKG: Final[Path] = (
    Path(__file__).resolve().parents[2] / "src" / "codegenie" / "eval"
)


def test_no_llm_sdk_imports_in_eval_package() -> None:
    # AC-15. Live scan against the real package.
    assert EVAL_PKG.is_dir(), f"eval package not found at {EVAL_PKG}"  # AC-17
    py_files = sorted(EVAL_PKG.rglob("*.py"))
    assert py_files, f"AST walker found no .py files under {EVAL_PKG}"  # AC-17
    violations = walk_imports(py_files, forbidden=BANNED_ROOTS)
    assert violations == [], (
        "Banned LLM-SDK imports detected in src/codegenie/eval/ — the harness "
        "must remain SDK-free per stories/README.md §Cross-cutting concerns:\n"
        + "\n".join(f"{v.file}: import {v.package}" for v in violations)
    )


def test_load_bearing_modules_are_present_in_scan_input() -> None:
    # AC-16. Named-set superset assertion — if a load-bearing module is
    # renamed/deleted, this test fails loudly naming the missing file.
    required = {"__init__.py", "errors.py", "models.py", "registry.py", "rubric.py"}
    present = {f.name for f in EVAL_PKG.rglob("*.py")}
    missing = required - present
    assert not missing, f"load-bearing eval modules missing from scan input: {missing}"
```

```python
# tests/fence/test_eval_static_negatives.py
"""Planted-positive-control + benign-mention fixtures for the eval SDK-import
guard and the smuggling-substring guard. Mutation-resistance pattern ported
from tests/fence/test_pyproject_fence_phase4_negatives.py (AC-14 / AC-7).

Each fixture lives as `.py.txt` (NOT `.py`) so pytest collection does not
attempt to import it. The test copies fixtures into a tmp_path mirror of the
package and runs the SAME `walk_imports` scanner the live test uses — kills
both the live and mutation tests together if the scanner regresses.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from tests.fence._phase4_scanner import walk_imports
from tests.fence.test_eval_package_imports_no_llm_sdk import BANNED_ROOTS

_FIXTURES = Path(__file__).parent / "_fixtures_eval"


@pytest.mark.parametrize("fixture_name,expected_min_violations", [
    ("violator_eval_imports_anthropic_bare.py.txt", 1),
    ("violator_eval_imports_anthropic_dotted.py.txt", 1),
    ("violator_eval_imports_anthropic_aliased.py.txt", 1),
    ("violator_eval_imports_openai_and_anthropic.py.txt", 2),
    ("violator_eval_from_openai.py.txt", 1),
    ("violator_eval_from_dotted_anthropic.py.txt", 1),
])
def test_walker_flags_planted_violator_fixtures(
    fixture_name: str, expected_min_violations: int, tmp_path: Path,
) -> None:
    # AC-14. Each planted import shape MUST yield at least the expected
    # violation count. This is the mutation-resistance test that makes
    # AC-15's live scan meaningful — if walk_imports regresses to a no-op,
    # this test dies first.
    src = _FIXTURES / fixture_name
    dst = tmp_path / "fake.py"
    shutil.copy(src, dst)
    violations = walk_imports([dst], forbidden=BANNED_ROOTS)
    assert len(violations) >= expected_min_violations, (
        f"{fixture_name}: expected >= {expected_min_violations} violations, "
        f"got {len(violations)}: {violations!r}"
    )


@pytest.mark.parametrize("fixture_name", [
    "benign_eval_mentions_anthropic_in_string_only.py.txt",
    "benign_eval_relative_import.py.txt",
])
def test_walker_does_not_flag_benign_fixtures(
    fixture_name: str, tmp_path: Path,
) -> None:
    # AC-14. Benign mentions (string literals, comments, relative imports)
    # MUST NOT be flagged — the AST-not-regex guarantee.
    src = _FIXTURES / fixture_name
    dst = tmp_path / "fake.py"
    shutil.copy(src, dst)
    violations = walk_imports([dst], forbidden=BANNED_ROOTS)
    assert violations == [], (
        f"{fixture_name}: AST scanner false-positive on benign fixture: {violations!r}"
    )


# ---- Substring-ban mechanism mutation-guard (AC-7) ---------------------------

def test_substring_ban_flags_synthetic_banned_field() -> None:
    # AC-14 + AC-7. The substring ban mechanism MUST flag a synthetic model
    # whose field name contains a banned substring. Mirrors the planted-import
    # mutation guard for the static SDK-import test.
    from codegenie.eval._smuggling import SMUGGLING_SUBSTRINGS

    class _Smuggler(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")
        llm_confidence: float = 0.0

    field_names = list(_Smuggler.model_fields.keys())
    flagged = [
        n for n in field_names
        if any(b in n.lower() for b in SMUGGLING_SUBSTRINGS)
    ]
    assert flagged == ["llm_confidence"], (
        f"substring-ban regression: expected ['llm_confidence'], got {flagged!r}"
    )
```

**Planted-fixture content** (one fixture per planted shape; place at `tests/fence/_fixtures_eval/`):

```python
# violator_eval_imports_anthropic_bare.py.txt
import anthropic  # planted positive-control for AC-14
```

```python
# violator_eval_imports_anthropic_dotted.py.txt
import anthropic.client  # dotted form; .split(".",1)[0] must extract "anthropic"
```

```python
# violator_eval_imports_anthropic_aliased.py.txt
import anthropic as a  # aliased — alias.name == "anthropic" is what counts
```

```python
# violator_eval_imports_openai_and_anthropic.py.txt
import openai, anthropic  # multi-name — each alias is its own violation
```

```python
# violator_eval_from_openai.py.txt
from openai import OpenAI  # bare `from`
```

```python
# violator_eval_from_dotted_anthropic.py.txt
from anthropic.client import X  # dotted from-import; root extraction must catch it
```

```python
# benign_eval_mentions_anthropic_in_string_only.py.txt
"""Module that names anthropic only in a docstring and a string literal.

# anthropic mentioned in a comment too
"""
SENTINEL = "anthropic mentioned in a string literal"
# AST scanner must NOT flag this (no import statement present).
```

```python
# benign_eval_relative_import.py.txt
from . import errors  # relative import; node.level == 1 — MUST be ignored
```

Run all four test modules; confirm each planted-violator fixture fails (assertion fires that violations are non-empty) and the benign fixtures pass. Confirm the live scanner over `src/codegenie/eval/` reports zero violations. Commit the red marker.

### Green — make it pass

- Land `src/codegenie/eval/_smuggling.py` per §Implementation outline #1.
- Edit `src/codegenie/eval/__init__.py` per §Implementation outline #3 — three `from … import …` lines (one per submodule), `__all__` listing nine names alphabetically, module docstring citing the ADRs.
- Confirm all four test modules pass:
  - `pytest tests/fence/test_eval_package_public_surface.py` — green (the 9-name surface is wired correctly).
  - `pytest tests/fence/test_bench_score_static.py` — green (no production model carries a banned field; synthetic positive-controls all flag correctly; recursion-shape matrix green; forward-refs resolve).
  - `pytest tests/fence/test_eval_package_imports_no_llm_sdk.py` — green (no banned import anywhere in `src/codegenie/eval/`; load-bearing modules all present).
  - `pytest tests/fence/test_eval_static_negatives.py` — green (every planted violator yields ≥ expected violations; every benign fixture yields zero).

### Refactor — clean up

- `__init__.py` ≤ 25 lines including the docstring (the docstring grew to accommodate AC-5; +5 lines headroom over the original 20-line target).
- Confirm `_walk` and `_candidate_models` are the *entire* helper surface of `test_bench_score_static.py` (one extra helper is one too many).
- Confirm `tests/fence/test_eval_package_imports_no_llm_sdk.py` reuses `walk_imports` — `grep -E "(ast\.walk|ast\.Import|ast\.ImportFrom)" tests/fence/test_eval_package_imports_no_llm_sdk.py` MUST return empty (per AC-12).
- Confirm `tests/fence/test_bench_score_static.py` does not contain the literal four-string set inline — `grep -E '"confidence"|"llm"|"self_reported"|"model_says"' tests/fence/test_bench_score_static.py` MUST return empty (per AC-7).
- Add `# noqa: F401` only where unavoidable (re-exports do not need it because the names appear in `__all__`).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/_smuggling.py` | **New file** — `SMUGGLING_SUBSTRINGS: Final[frozenset[str]]` as the single source-of-truth (AC-6); leading-underscore keeps it private — NOT in `__all__` |
| `src/codegenie/eval/__init__.py` | Modify — wire the nine public names from S1-02, S1-03, S1-04; docstring cites ADR-0008 + Phase 5 ADR-0014 (AC-5) |
| `tests/fence/test_eval_package_public_surface.py` | New file — pins the nine public names exactly + identity-equality + docstring-citation discipline (AC-1..AC-5) |
| `tests/fence/test_bench_score_static.py` | New file — recursive Pydantic field-graph substring ban + synthetic positive-control matrix + recursion-shape matrix + forward-ref resolution (AC-7, AC-8, AC-9, AC-10, AC-11) |
| `tests/fence/test_eval_package_imports_no_llm_sdk.py` | New file — calls `tests/fence/_phase4_scanner.py::walk_imports` over `src/codegenie/eval/**/*.py`; named-set sanity floor (AC-12, AC-13, AC-15, AC-16, AC-17) |
| `tests/fence/test_eval_static_negatives.py` | **New file** — planted-positive-control + benign-mention parametrised tests over `_fixtures_eval/` (AC-14) — the mutation-resistance test AC-4 of the original story promised but did not deliver |
| `tests/fence/_fixtures_eval/violator_eval_imports_anthropic_bare.py.txt` | **New fixture** — `import anthropic` |
| `tests/fence/_fixtures_eval/violator_eval_imports_anthropic_dotted.py.txt` | **New fixture** — `import anthropic.client` |
| `tests/fence/_fixtures_eval/violator_eval_imports_anthropic_aliased.py.txt` | **New fixture** — `import anthropic as a` |
| `tests/fence/_fixtures_eval/violator_eval_imports_openai_and_anthropic.py.txt` | **New fixture** — `import openai, anthropic` (multi-name) |
| `tests/fence/_fixtures_eval/violator_eval_from_openai.py.txt` | **New fixture** — `from openai import OpenAI` |
| `tests/fence/_fixtures_eval/violator_eval_from_dotted_anthropic.py.txt` | **New fixture** — `from anthropic.client import X` |
| `tests/fence/_fixtures_eval/benign_eval_mentions_anthropic_in_string_only.py.txt` | **New fixture** — string-literal mention only (AST-not-regex guarantee) |
| `tests/fence/_fixtures_eval/benign_eval_relative_import.py.txt` | **New fixture** — `from . import errors` (relative — `node.level > 0` filter) |

## Out of scope

- **`test_breakdown_keys_static.py` (the per-task-class StrEnum-value ban)** — handled by S5-01 (vuln-remediation) and S6-01 (distroless); this story's `test_bench_score_static.py` is the *field-name* defense, and the StrEnum-value defense lands when the first task class registers a `BreakdownKey`. **However**: S5-01 / S6-01 / S3-04 / S7-01 #5 will all consume `codegenie.eval._smuggling.SMUGGLING_SUBSTRINGS` (per AC-6) — this story lands the source-of-truth even though only `test_bench_score_static.py` consumes it today.
- **Fence-CI seven assertions (the AST + filesystem walk over `bench/<name>/`)** — handled by S7-01; this story owns the package-scoped static defenses, not the bench-scoped ones.
- **`pyproject.toml [tool.importlinter]` contract amendment** — **NOT appropriate** at this story boundary. Phase 0's import-linter contract (`docs/phases/00-bullet-tracer-foundations/stories/S1-05-ci-fence-import-linter.md` AC-5) polices *heavy modules at cold-start* (`yaml`, `jsonschema`, `pydantic`, `blake3`, `structlog`) at `codegenie.cli` and `codegenie` — a fundamentally different scope (cold-start cost discipline) and mechanism (import-linter contracts over `[project].dependencies`). The LLM-SDK ban inside `src/codegenie/eval/**` is a **parallel structural defense** with different scope (LLM-SDK imports in a specific subpackage) and different mechanism (in-test AST walk via `_phase4_scanner.py:walk_imports`). The arch's word "extends" (line 1026) means "adds a parallel structural defense," not "amends the existing contract."
- **Per-submodule cold-start fence test for `codegenie.eval`** — deferred to S2-01 (loader); mirrors `tests/fence/test_per_submodule_cold_start.py` precedent. The cold-start budget Notes claim (≤ 600 ms per arch line 695) is real, but the structural test that pins it belongs with the loader where heavy imports might land.
- **`__import__("anthropic")` / `importlib.import_module("anthropic")` bypass detection** — acknowledged residual; CODEOWNERS on `src/codegenie/eval/` is the current compensating control. Same posture as ADR-0008 §Tradeoffs row 3 (dynamic StrEnum-value computation). A future Phase 16 story may add a `_DynamicImportCall` AST walker.
- **Wall-clock perf gate (the original "≤ 200 ms" claim)** — replaced by the structural observable (AC-18: tests do not live-import the modules they police). Wall-clock claims on CI variance are unreliable; the structural property is what made the original perf claim achievable in the first place.
- **Extending the banned-substring list or banned-import set** — any expansion of `SMUGGLING_SUBSTRINGS` requires amending ADR-0008 + Phase 5 ADR-0014 in the same change-train (cross-phase contract). Any expansion of `BANNED_ROOTS` requires amending arch §CI gates.
- **Adding `FailureMode` to the public surface** — explicitly forbidden by AC-2; widening requires an ADR amendment.
- **Auto-deriving `BANNED_ROOTS` from `codegenie._fence.FORBIDDEN_LLM_SDKS`** — they are *intentionally different* path-scoped vs. closure-scoped mechanisms (see Notes for implementer). Don't auto-derive.

## Notes for the implementer

### Discipline

- The nine-name limit is *the* discipline. Adding a tenth ("just `FailureMode`, it's harmless") starts the API-debt accretion that `extension by addition` is designed to prevent. The public surface is the load-bearing contract Phase 7 / Phase 11 / Phase 13 will pin against — any addition is a forever commitment.
- Adding `FailureMode` directly to the public surface is the most likely well-intentioned wrong move. The decision (per arch §Component design — models.py and §Goal #1) is that `FailureMode` is reached *through* `BenchScore.failure_modes`. AC-2 pins both halves: absence-from-`__all__` AND reachability-via-the-typed-path. Don't relax one without the other.

### Smuggling source-of-truth (`_smuggling.py`)

- Place `_smuggling.py` next to the other private helpers Phase 6.5 might land later; do NOT promote it to a top-level constant (it's a discipline detail, not a public API). The leading-underscore name + absence from `__all__` is the structural marker.
- This story IS the rule-of-three cross-over. By the story's own enumeration the substring list is consumed by: (a) `test_bench_score_static.py` (here), (b) `test_breakdown_keys_static.py` (S5-01 / S6-01), (c) S3-04 runtime defense-in-depth, (d) S7-01 fence assertion #5, (e) Phase 5 ADR-0014's eventual `test_objective_signals_static.py`. Five concrete consumers — the constant module pays its way immediately. The precedent is `src/codegenie/_fence.py:50` (`FORBIDDEN_LLM_SDKS`) which was extracted for exactly this reason.
- ADRs (Phase 6.5 ADR-0008 + Phase 5 ADR-0014) will need a §Consequences-line amendment in a later cleanup PR to point at `_smuggling.py` as the structural source-of-truth. That amendment is not in this story's scope — but flag the staleness when this story merges so the cleanup is tracked.

### The `walk_imports` reuse (Phase-4's deliberate lesson)

- `tests/fence/_phase4_scanner.py` is **the** AST-walking kernel for this repo. The Phase 4 story that introduced it (per `_phase4_scanner.py:11-13`) explicitly says: *"There is exactly one AST-walking implementation under `tests/fence/`. Mutating it kills every Phase-4 fence test simultaneously."* The eval-package guard joins that family. Do NOT re-implement `ast.walk` / `ast.Import` / `ast.ImportFrom` inline. AC-12 makes this a structural requirement.
- Reusing `walk_imports` brings the `node.level == 0` relative-import filter for free — relative imports like `from . import errors` have `node.module == "errors"`, which COULD accidentally match `BANNED_ROOTS` in the future if a banned-name overlap appears. The `node.level == 0` guard makes this safe.

### Banned-set relationships (path-scoped vs. closure-scoped)

- `BANNED_ROOTS` (this story) is **path-scoped** to `src/codegenie/eval/**`. It bans the five LLM-SDK roots from the eval harness specifically.
- `codegenie._fence.FORBIDDEN_LLM_SDKS` (Phase 0 + Phase 4) is **closure-scoped**: it scans `pyproject.toml [project].dependencies` for distribution-name leaks across the entire `codegenie` runtime closure. It admits `anthropic` (path-scoped at `fallback/leaf/anthropic_adapter.py`) and bans `sentence-transformers` / `torch` (embedding SDKs that COULD become alternative backends).
- The two sets are intentionally different: one polices files inside `src/codegenie/eval/`; the other polices distribution-name leaks in pyproject.toml. They do not derive from each other; they enforce orthogonal properties. AC-13 pins `BANNED_ROOTS` to the arch §CI gates list verbatim. If a future ADR expands either set, the other does NOT auto-update.

### Sibling Protocol-port / module-shape lineage

- `__init__.py`'s docstring discipline mirrors `src/codegenie/vuln_index/__init__.py:1-29` and `src/codegenie/probes/__init__.py:1-14` (both cite ADRs by id in the module docstring). The AST-introspected docstring check in AC-5 is the S1-04 validator's pattern (which originally surfaced the convention for `vuln_index/protocol.py`); the convention is now structural, not social.
- `_walk` and `_candidate_models` are the **first** concrete instance of the recursive-Pydantic-field-walk pattern in the repo. The Phase 5 ADR-0014 sibling walker (when it lands at `tests/sandbox/test_objective_signals_static.py`) will be the second. Rule of three not yet crossed: keep both copies, do not preemptively share. When the third walker arrives, `tests/_helpers/pydantic_field_walk.py` becomes the extract target — same deferred-extract framing as the S1-04 `port_base.py` discussion.

### Forward-ref correctness (AC-10)

- `model.model_rebuild()` is idempotent and safe to call before introspecting `model_fields`. Pydantic v2 typically resolves annotations during class definition, but `from __future__ import annotations` defers resolution to first-introspection time. Calling `model_rebuild()` explicitly forces resolution and makes the test invariant unambiguous — without it, `finfo.annotation` MIGHT be `str` (an unresolved forward ref), and `typing.get_args(str_annotation)` returns `()`, silently making the walker vacuous on PEP-563 modules.

### Subtle gotchas

- `Path(__file__).resolve().parents[2]` — the test now lives at `tests/fence/test_*.py` (NOT `tests/unit/`). `parents[2]` from `tests/fence/test_*.py` is the repo root; `parents[2] / "src" / "codegenie" / "eval"` resolves correctly. Verify with `assert EVAL_PKG.is_dir()` (AC-17) before relying on it.
- The planted-fixture suffix is `.py.txt` (NOT `.py`). The `.py` extension would make pytest attempt to collect them as test modules; the `.py.txt` suffix keeps them on-disk as text. The test copies them to a `tmp_path / "fake.py"` so the scanner sees a well-formed `.py` filename at scan time.
- The structural perf observable (AC-18) uses `tokenize` (not naive `read_text` + regex) to ignore string literals when checking that the static-guard test modules do not contain live `import anthropic` statements. A docstring or comment mentioning `import anthropic` MUST NOT trip this — same AST-not-regex guarantee as the planted-benign-mention fixture.

### Specification-by-example for the dynamic-import bypass

- A contributor could try to bypass the SDK-import ban by writing `__import__("anthropic")` or `importlib.import_module("anthropic")` — neither is caught by `ast.Import` / `ast.ImportFrom`. This is an **acknowledged residual** (same posture as the breakdown-key dynamic-value-computation residual called out in ADR-0008 §Tradeoffs row 3). CODEOWNERS on `src/codegenie/eval/` is the compensating control. Phase 16 may add a `_DynamicImportCall` AST walker; do NOT add it here (Rule 3 — surgical changes).
