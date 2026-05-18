# Story S7-02 — `rag_query_builder` plugin recipe

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** Ready
**Effort:** S
**Depends on:** S7-01 (`FallbackTierPlanRecipeEngine` constructed via plugin), S1-04 (`Query` Pydantic model), S5-01 (`SolvedExampleRetriever` consumes typed `Query`)
**ADRs honored:** ADR-0003 (path-scoped fence — builder lives plugin-side, no SDK imports), production-ADR-0031 (extension by addition; plugin-scoped)

## Context

`SolvedExampleRetriever.query(advisory, repo_ctx)` (S5-01) embeds a `Query` Pydantic model — not a hand-formatted f-string — to avoid stringly-typed retrieval. The retriever takes the query *builder* via injection because the natural-text shape of the query is **plugin-scoped knowledge**: the npm plugin knows the canonical concatenation of `task_class | language | build_system | cve_id | package_id | version_constraint | ...`; the Phase 7 distroless plugin will know a different shape.

Phase 5 step §5 in High-level-impl is explicit: "Builds `Query` via plugin's `rag_query_builder` (Step 7 ships the plugin-side builder; this step takes it via injection)." So Step 5's retriever knows the *Protocol* shape of the builder; this story ships the npm plugin's concrete builder.

The arch's anti-pattern row is firm: "RAG query is a typed `Query` Pydantic model, never a hand-formatted f-string." If the implementer is tempted to `return Query(text=f"vuln_remediation/node/npm | cve={advisory.cve_id} | ...")`, the typed-model discipline still demands the field-by-field construction be explicit and named, not an opaque template literal.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Development view` — `plugins --> p_rag_q["recipes/rag_query_builder.py (NEW)"]` (the file path).
  - `../phase-arch-design.md §Component 9 — SolvedExampleRetriever` — "Builds `Query` (Pydantic frozen, extra=forbid) via plugin's `rag_query_builder`".
  - `../phase-arch-design.md §Anti-patterns avoided` — "Stringly-typed identifiers... RAG query is a typed `Query` Pydantic model, never a hand-formatted f-string."
  - `../phase-arch-design.md §Process view §Scenario 1` — `Retr->>Emb: embed("vuln_remediation/node/npm | cve=2026-1234 | ...")` shows the canonical concatenation shape (display form only; the builder produces the typed model that *serializes* to this text).
- **Phase ADRs:**
  - `../ADRs/0003-path-scoped-fence-amendment.md` — builder lives plugin-side and must not import any admitted SDK.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — plugin scope = task-class × language × build-system; the builder concatenates exactly these.
- **Source design:**
  - `../final-design.md §Component 9 — SolvedExampleRetriever` (whatever it says about query construction).
- **High-level impl:**
  - `../High-level-impl.md §Step 5` (§features delivered, retriever builds `Query` via plugin's `rag_query_builder` via injection).
  - `../High-level-impl.md §Step 7` (this story ships the plugin-side builder).
- **Existing code:**
  - `src/codegenie/rag/models.py` (S1-04) — `Query` Pydantic model definition.
  - `src/codegenie/rag/retriever.py` (S5-01) — how `Query` flows into embed.
  - `src/codegenie/types/identifiers.py` — Newtypes (`PackageId`, `SemverString`).
  - `plugins/vulnerability-remediation--node--npm/recipes/` — existing recipe layout (mirror naming/style; Global Rule 11).

## Goal

Land `plugins/vulnerability-remediation--node--npm/recipes/rag_query_builder.py` exposing a `build(advisory, repo_ctx) -> Query` callable (free function or `@dataclass(frozen=True)` callable; mirror the plugin's existing recipe shape) that constructs a typed `Query` with the npm-plugin canonical fields — and is consumed by `SolvedExampleRetriever` via dependency injection at retriever-construction time.

## Acceptance criteria

- [ ] `plugins/vulnerability-remediation--node--npm/recipes/rag_query_builder.py` exists and exports `build(advisory: CveAdvisory, repo_ctx: RepoContext) -> Query`. The signature matches the `RagQueryBuilder` Protocol declared in Step 5's retriever (read `src/codegenie/rag/retriever.py` first to confirm the Protocol shape; surface a conflict per Global Rule 7 if the names differ).
- [ ] The returned `Query` is constructed **field-by-field** from typed inputs — no f-string templating; field values are `PackageId`, `SemverString`, `cve_id: str` (from `CveAdvisory.id`), `task_class="vulnerability-remediation"`, `language="node"`, `build_system="npm"`, with all values cited explicitly in the constructor call.
- [ ] `Query` is `frozen=True, extra="forbid"` (already from S1-04); the builder uses only Newtypes / Pydantic fields, never raw `str` for domain identifiers — AST-walking discipline test (mirrors Phase-3 pattern) is added or extended.
- [ ] Unit test (`tests/unit/plugin/test_rag_query_builder.py`) asserts:
  - Two distinct CVEs produce two distinct `Query` instances with different `cve_id`.
  - The same `(advisory, repo_ctx)` produces a `Query` that hashes-equal across calls (determinism for embed-cache lookup; `Query` must support equality from its frozen-extra-forbid Pydantic shape).
  - Missing-package-id `CveAdvisory` raises `ValueError` (via `Query`'s validator), not a silently empty field.
- [ ] The builder is wired into `SolvedExampleRetriever` construction inside the plugin's TCCM (read S7-01's `FallbackTierPlanRecipeEngine.__init__` to see exactly where the retriever is built; surface a conflict if the wiring point is unclear).
- [ ] AST-walking test asserts `rag_query_builder.py` contains zero f-strings whose template includes `advisory.` or `repo_ctx.` (the typed-model discipline guard).
- [ ] AST-walking test asserts `rag_query_builder.py` does not import `anthropic`/`chromadb`/`fastembed`/`onnxruntime` (ADR-0003).
- [ ] `make check` clean: `ruff format`, `ruff check`, `mypy --strict`, `pytest -q` all green.
- [ ] TDD red test exists, committed, green.

## Implementation outline

1. Read `src/codegenie/rag/models.py` first — confirm the exact `Query` field names. Read `src/codegenie/rag/retriever.py` to confirm the `RagQueryBuilder` Protocol signature.
2. Read an existing recipe in `plugins/vulnerability-remediation--node--npm/recipes/` to match style (free function vs class; module-level vs nested).
3. Create `rag_query_builder.py` with a single `build(advisory, repo_ctx) -> Query` callable. Implementation pulls `package_id`, `version_constraint` from `advisory`; pulls `build_system="npm"`, `language="node"` from constants; passes them positionally/keyword to `Query(...)` with no string templating.
4. If `CveAdvisory` lacks `package_id` on some variants, raise `ValueError("rag_query_builder requires package_id")` — defense in depth; the retriever cannot meaningfully embed without it.
5. Update the plugin's wiring code (likely `plugins/vulnerability-remediation--node--npm/__init__.py` or the TCCM module) to pass `rag_query_builder.build` into `SolvedExampleRetriever.__init__` (or equivalent injection point).
6. Add unit tests + AST discipline tests.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/plugin/test_rag_query_builder.py
from __future__ import annotations
import ast
import inspect
import pytest
from codegenie.rag.models import Query
from plugins.vulnerability_remediation_node_npm.recipes import rag_query_builder


def test_build_returns_typed_query(advisory_express_1234, repo_ctx):
    q = rag_query_builder.build(advisory_express_1234, repo_ctx)
    assert isinstance(q, Query)
    assert q.task_class == "vulnerability-remediation"
    assert q.language == "node"
    assert q.build_system == "npm"
    assert q.cve_id == advisory_express_1234.id


def test_build_is_deterministic(advisory_express_1234, repo_ctx):
    q1 = rag_query_builder.build(advisory_express_1234, repo_ctx)
    q2 = rag_query_builder.build(advisory_express_1234, repo_ctx)
    assert q1 == q2
    assert hash(q1) == hash(q2)  # frozen Pydantic supports hashing


def test_distinct_cves_yield_distinct_queries(
    advisory_express_1234, advisory_lodash_9876, repo_ctx,
):
    q1 = rag_query_builder.build(advisory_express_1234, repo_ctx)
    q2 = rag_query_builder.build(advisory_lodash_9876, repo_ctx)
    assert q1 != q2
    assert q1.cve_id != q2.cve_id


def test_missing_package_id_raises(advisory_no_package_id, repo_ctx):
    with pytest.raises(ValueError, match="package_id"):
        rag_query_builder.build(advisory_no_package_id, repo_ctx)


def test_no_fstring_templating_over_inputs():
    """Discipline: typed Query construction, not f-string concatenation."""
    src = inspect.getsource(rag_query_builder)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            # f-string detected — confirm it does not reference advisory or repo_ctx
            for v in node.values:
                if isinstance(v, ast.FormattedValue):
                    code = ast.unparse(v.value)
                    assert "advisory" not in code and "repo_ctx" not in code, (
                        f"f-string templates over typed input: {code}"
                    )


def test_no_forbidden_sdk_imports():
    src = inspect.getsource(rag_query_builder)
    tree = ast.parse(src)
    bad = {"anthropic", "chromadb", "fastembed", "onnxruntime"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name.split(".")[0] for a in (node.names or [])]
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module.split(".")[0])
            assert not (bad & set(names))
```

Run: `pytest tests/unit/plugin/test_rag_query_builder.py -v`. All six tests fail before implementation.

### Green — make it pass

Implement `build(...)` with explicit keyword construction of `Query(...)`. Raise `ValueError` on missing `package_id`. Wire the builder into retriever construction. Add fixtures.

### Refactor — clean up

- Add a module-level docstring naming the canonical field order; cite the arch §Scenario 1 sequence line as the source.
- If the plugin already exposes a `RECIPE_REGISTRY` pattern, register the builder there; otherwise export only the `build` function.
- Run `make check`; verify the `test_kernel_frozen.py` invariant from S1-07 still holds (no edits to `src/codegenie/plugins/`).

## Files to touch

| Path | Why |
|---|---|
| `plugins/vulnerability-remediation--node--npm/recipes/rag_query_builder.py` | New — the plugin's typed query builder. |
| `plugins/vulnerability-remediation--node--npm/__init__.py` (or equivalent TCCM wiring) | Wire `rag_query_builder.build` into `SolvedExampleRetriever` construction. |
| `tests/unit/plugin/test_rag_query_builder.py` | TDD red tests + discipline guards. |
| `tests/unit/plugin/conftest.py` | Fixtures: `advisory_express_1234`, `advisory_lodash_9876`, `advisory_no_package_id`, `repo_ctx`. |

## Out of scope

- The retriever's embed/store/classify pipeline (S5-01 / S5-02).
- The actual query text format used by the embedder — that's a property of the canonical Pydantic-serialization shape, not the builder's responsibility.
- `plugin.yaml` thresholds (S7-04).
- E2E retrieval tests (S7-06 / S7-07).

## Notes for the implementer

- Mirror the plugin's existing recipe naming (Global Rule 11). If existing recipes are `class FooRecipe` with a `apply(...)` method, this story may want `class RagQueryBuilder` with `build(...)`. If existing recipes are free functions, this story should be a free function. Surface the conflict per Global Rule 7 if the plugin contains both shapes.
- The hashing assertion is fragile if `Query` uses `frozen=True` but not `model_config = ConfigDict(frozen=True)` Pydantic v2 — read the model and pick the correct equality/hashing assertion. If `Query` is frozen but un-hashable, use `q1.model_dump() == q2.model_dump()` instead.
- The f-string discipline test is the canonical guard for primitive-obsession resurrection — if a future story is tempted to "speed up" the builder with `Query(text=f"...")`, this test catches it.
- The builder is **stateless** — no class needed unless the plugin's existing recipe shape demands one. Stateless free functions compose with `SolvedExampleRetriever` via the injection point; no factory pattern.
