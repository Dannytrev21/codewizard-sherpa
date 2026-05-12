# Story S1-03 — `src/codegenie/recipes/` package skeleton + `RecipeEngine` ABC + registry

**Step:** Step 1 — Plant the two ABCs, the four Phase 0/1/2 additive edits, and the foundations every Phase 3 component consumes
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0001, ADR-0002, ADR-0003

## Context

`RecipeEngine` is the second of Phase 3's two public ABCs (ADR-0001). It defines the plug-in execution backend for recipes; Phase 3 ships two concrete engines (`NcuRecipeEngine` default + `OpenRewriteEngineStub` opt-in) but the contract is what Phase 7 (Chainguard) and Phase 15 (agent-authored recipes) extend by addition. This story plants the package, the ABC, and the engine registry — no concrete engines, no selector, no recipe catalog — only the contract surface. The same frozen-schema discipline that S1-02 applies to `Transform` applies here: the engine's `apply()` signature and the `RecipeApplication` return shape are snapshot-tested at v0.3.0 so any drift fails CI red.

ADR-0002 places `recipes/` as a sibling top-level package to `transforms/` so the Phase-0 fence CI can refuse LLM SDK imports under the entire recipes subtree (S1-09 plants the fence test). The `available()` method on the ABC is the single most important detail — it gates engine eligibility in the selector (ADR-0004) and produces `RecipeSelection(reason="no_engine")` rather than raising when an engine's preflight fails.

## References — where to look

- **Architecture:** `../phase-arch-design.md §"Component design" #2 (RecipeEngine ABC + two implementations)` — `available()` gating, statelessness, sandbox routing.
- **Architecture:** `../phase-arch-design.md §"Development view — module tree"` — `recipes/contract.py`, `recipes/registry.py`, `recipes/engines/` placement.
- **Architecture:** `../phase-arch-design.md §"Data model" → Inputs/Outputs` — `ApplyContext`, `RecipeApplication` field set.
- **Phase ADRs:** `../ADRs/0001-transform-recipe-engine-two-abc-contract.md` — ADR-0001 — two-ABC commitment; `RecipeEngine.apply` signature.
- **Phase ADRs:** `../ADRs/0002-two-new-top-level-packages-transforms-recipes.md` — ADR-0002 — package layout.
- **Phase ADRs:** `../ADRs/0003-recipe-engine-ncu-default-openrewrite-stub-registered.md` — ADR-0003 — `available()` gates concrete engines; `EngineUnavailable` semantics.
- **Production ADRs:** `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — recipe-first commitment that makes engines load-bearing for Phase 4.
- **Source design:** `../final-design.md §"Components" #2 RecipeEngine ABC with two impls`.
- **Source design:** `../final-design.md §"Synthesis ledger" "Conflict-resolution table" row "Recipe engine pick"`.
- **Existing code:** `src/codegenie/probes/registry.py` (Phase 0) — duplicate-name rejection pattern this story mirrors. `src/codegenie/transforms/registry.py` (S1-02, sibling story) — identical pattern for transforms.

## Goal

Land `src/codegenie/recipes/{__init__.py, contract.py, registry.py}` so that (a) the `RecipeEngine` ABC declares `name`, `applies_to_engines`, `available() -> bool`, and `apply(recipe, repo_overlay, ctx) -> RecipeApplication`, (b) `@register_engine` rejects duplicate-name registration, (c) `available()` gating is unit-tested (an unavailable engine is enumerable but not eligible), and (d) a frozen Pydantic schema-dump snapshot of `ApplyContext` and `RecipeApplication` lives at `tests/unit/recipes/snapshots/recipe_engine_contract_v0_3_0.json`.

## Acceptance criteria

- [ ] `src/codegenie/recipes/__init__.py` exports `RecipeEngine`, `ApplyContext`, `RecipeApplication`, `register_engine`, `all_engines`, `available_engines`.
- [ ] `src/codegenie/recipes/contract.py` defines `class RecipeEngine(ABC)` with class-level `name: str` (engine identifier, e.g., `"ncu"` or `"openrewrite"`) and `applies_to_engines: Sequence[str]` (subset of the same engine vocabulary used by `Recipe.engine`); abstract methods `available(self) -> bool` and `apply(self, recipe: Recipe, repo_overlay: Path, ctx: ApplyContext) -> RecipeApplication`.
- [ ] `ApplyContext` is a frozen Pydantic model with `extra="forbid"` and the fields from `phase-arch-design.md §"Data model" → Inputs`: `npm_minor_digest: str`, `registry_mirror_digest: str`, `sandbox_runner: Callable` (typed as `Callable[..., ProcessResult]` — concrete signature lives in Phase 2's `exec.py`), `audit: AuditWriter` (forward ref — Phase 2 type), `run_id: str`.
- [ ] `RecipeApplication` is a frozen Pydantic model with `extra="forbid"` and the fields from `phase-arch-design.md §"Data model" → Outputs`: `diff: bytes`, `files_changed: list[Path]`, `engine_stdout_path: Path`, `engine_stderr_path: Path`, `exit_code: int`.
- [ ] `src/codegenie/recipes/registry.py` exposes `@register_engine`, `all_engines() -> Sequence[type[RecipeEngine]]`, `available_engines() -> Sequence[RecipeEngine]` (instantiates each registered class with no-args and returns those whose `available()` is `True`).
- [ ] Duplicate-name registration raises `RuntimeError` at decoration time with the message `f"duplicate engine name: {cls.name}"` (matches Phase 0/S1-02 wording).
- [ ] `tests/unit/recipes/test_contract.py` includes (a) a snapshot test asserting `ApplyContext.model_json_schema()` + `RecipeApplication.model_json_schema()` equal `tests/unit/recipes/snapshots/recipe_engine_contract_v0_3_0.json`, (b) a structural assertion `RecipeApplication.model_fields["diff"].annotation is bytes`, (c) a structural assertion that `available()` and `apply()` are abstract (instantiating an incomplete subclass raises `TypeError`).
- [ ] `tests/unit/recipes/test_registry.py` covers (a) happy registration, (b) duplicate-name rejection, (c) `available_engines()` filters out engines whose `available()` returns `False` (use a test-double engine subclass that returns `False` to assert exclusion), (d) `available_engines()` returns a tuple ordered by registration insertion.
- [ ] No `subprocess.run`/`subprocess.Popen`/`os.system` imports under `src/codegenie/recipes/`.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/recipes/ tests/unit/recipes/` pass.

## Implementation outline

1. Read `src/codegenie/transforms/contract.py` and `src/codegenie/transforms/registry.py` (S1-02 sibling) to confirm the duplicate-rejection pattern is identical. Rule 11 — same shape.
2. Write `tests/unit/recipes/test_contract.py` red — snapshot path does not exist; schema-dump assertion fails.
3. Write `tests/unit/recipes/test_registry.py` red — `from codegenie.recipes import register_engine` ImportErrors. Include the `available()` gating test using a test-double engine subclass (declared inside the test module, registered + unregistered via a context manager fixture).
4. Create the package: `src/codegenie/recipes/__init__.py`, `contract.py`, `registry.py`. Module docstrings cite ADR-0001/0003.
5. Implement `RecipeEngine` ABC. `applies_to_engines` is a class-level `Sequence[str]` (subclasses set, e.g., `("ncu",)` for `NcuRecipeEngine`). `available()` and `apply()` are abstract.
6. Implement `ApplyContext` and `RecipeApplication`. Forward refs (`Recipe`, `AuditWriter`) resolved lazily via `TYPE_CHECKING` blocks; S1-04 imports the concrete types and `model_rebuild()`-es.
7. Implement `registry.py` with `_ENGINES: dict[str, type[RecipeEngine]] = {}`. `all_engines()` returns `tuple(_ENGINES.values())`. `available_engines()` instantiates each `cls()` (no-arg constructor — engines are stateless per ADR-0001) and includes the instance if `instance.available()` is `True`. Cache instances per process so `available()` is called once per registered engine.
8. Generate the snapshot JSON once; commit it.
9. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest tests/unit/recipes/`.

## TDD plan — red / green / refactor

### Red — failing test first

Test file paths: `tests/unit/recipes/test_contract.py`, `tests/unit/recipes/test_registry.py`.

```python
# tests/unit/recipes/test_contract.py
import json
from pathlib import Path
from codegenie.recipes.contract import RecipeEngine, ApplyContext, RecipeApplication

SNAPSHOT = Path(__file__).parent / "snapshots" / "recipe_engine_contract_v0_3_0.json"

def test_apply_context_and_recipe_application_schema_matches_v0_3_0_snapshot():
    # arrange: load canonical snapshot
    # act: dump current schemas
    # assert: equal — drift fails CI red
    ...

def test_recipe_application_diff_is_bytes_not_str():
    # ADR-0001: engines emit raw bytes; canonicalization is downstream
    assert RecipeApplication.model_fields["diff"].annotation is bytes

def test_recipe_engine_abc_cannot_be_instantiated_without_available_and_apply():
    # ABCMeta enforces abstract method discipline
    with pytest.raises(TypeError):
        _IncompleteEngine()
```

```python
# tests/unit/recipes/test_registry.py
import pytest
from codegenie.recipes.registry import register_engine, all_engines, available_engines
from codegenie.recipes.contract import RecipeEngine

def test_register_engine_happy_path():
    # decorate a minimal RecipeEngine subclass with available()==True;
    # assert it appears in all_engines() and available_engines()
    ...

def test_duplicate_name_registration_raises_runtime_error():
    # mirrors Phase 0 @register_probe posture
    ...

def test_available_engines_filters_unavailable():
    # register an engine whose available() returns False;
    # all_engines() includes it; available_engines() excludes it
    ...
```

Run; commit red.

### Green — make it pass

- Create the three files under `src/codegenie/recipes/`. ABC docstring lists the four contract members; references ADR-0001 + ADR-0003.
- `ApplyContext` is frozen Pydantic. `sandbox_runner: Callable` typed against Phase 2's `RunInSandbox` protocol (use a forward ref if Phase 2 has not exported a protocol type; otherwise import directly).
- `RecipeApplication` is frozen Pydantic. `diff: bytes` (intentional — engines emit raw patch bytes; `LockfileCanonicalizer` in Step 3 normalizes).
- Registry copies the S1-02 pattern with engine-shaped identifiers. The one new method is `available_engines()` — call sites in S3 (selector) consume this.
- Generate the canonical snapshot JSON once; commit.

### Refactor — clean up

- ABC docstring: explicit "engines are stateless given their `ApplyContext`" — Phase 7 implementers will read this first.
- `__all__` on `__init__.py` lists exactly the public names.
- `available_engines()` cache-per-process documented inline: "instances are constructed once at first call; `available()` may invoke `which <bin>` or read a digest file — keep it cheap and idempotent."
- `mypy --strict` clean — `Sequence[str]` on `applies_to_engines`; `Callable[..., ProcessResult]` on `sandbox_runner`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/recipes/__init__.py` | Public package surface |
| `src/codegenie/recipes/contract.py` | `RecipeEngine` ABC + `ApplyContext` + `RecipeApplication` |
| `src/codegenie/recipes/registry.py` | `@register_engine`, `all_engines()`, `available_engines()` |
| `tests/unit/recipes/__init__.py` | pytest package marker |
| `tests/unit/recipes/test_contract.py` | Snapshot + structural tests |
| `tests/unit/recipes/test_registry.py` | Decorator + available() gating |
| `tests/unit/recipes/snapshots/recipe_engine_contract_v0_3_0.json` | Frozen schema dump |

## Out of scope

- **Concrete `NcuRecipeEngine`** — Step 3 (separate story under `recipes/engines/ncu.py`).
- **Concrete `OpenRewriteEngineStub`** — Step 6.
- **`Recipe`, `RecipeSelection`, `ApplyConstraints`, `RecipeSelector`** — recipe-shape Pydantic models land in S1-04; the selector is Step 3.
- **`recipes/catalog/`, `recipes/selector.yaml`, `recipes/digests.yaml`** — Step 3.
- **Fence test for `recipes/`** — S1-09.

## Notes for the implementer

- **`available()` is the load-bearing gate, not exceptions.** When an engine is missing on a developer's machine (no `java`, no `ncu`), the selector emits `RecipeSelection(reason="no_engine")` and the run exits cleanly. Engines do **not** raise `EngineUnavailable` from `available()` — they return `False`. `EngineUnavailable` is reserved for the case where `available()` returned `True` but the engine then crashed inside `apply()` — that wrap is the coordinator's job (S5-02).
- **No-arg constructor convention.** `available_engines()` instantiates each registered class with `cls()` — engines must have parameterless constructors. Subclasses initialize their internal state (e.g., cached `which java` result) lazily on first call. Document this in the ABC docstring.
- **`applies_to_engines` vs `name`.** Reading the architecture, the two look redundant — an engine named `"ncu"` always has `applies_to_engines = ("ncu",)`. The distinction matters for Phase 7+: a future hypothetical `OpenRewriteUnifiedEngine` could declare `applies_to_engines = ("openrewrite", "rewrite-yaml")` — supporting multiple `Recipe.engine` values from one class. Keep both fields; resist conflating.
- **`diff: bytes`, not `str`.** The npm lockfile is UTF-8; node_modules paths are typically ASCII; `git apply` accepts both. But engine output may include non-UTF-8 bytes (e.g., file-mode bits in unified diff headers). `bytes` is correct; the canonicalizer (Step 3) decodes/re-encodes deterministically.
- **`sandbox_runner` is in `ApplyContext`, not on the engine.** The engine never imports `codegenie.exec.run_in_sandbox` directly — it calls `ctx.sandbox_runner(...)`. This is what keeps engines fence-clean (S1-09) and unit-testable (a test passes an in-process fake `sandbox_runner` callable).
- **Snapshot regeneration is forbidden without an ADR.** If a future implementer expands `ApplyContext` (e.g., adds `proxy_url`), they must amend ADR-0001's append-only field policy and regenerate the snapshot in the same PR.
- Do not import `pydantic.v1`. Use pydantic v2.
