# Story S10-02 — `DockerfileMultiStageRefactorTransform` synchronous per-stage AST

**Step:** Step 10 — `DockerfileBaseImageSwapTransform` + `DockerfileMultiStageRefactorTransform` + three gates
**Status:** Ready
**Effort:** L
**Depends on:** S10-01 (`DockerfileBaseImageSwapTransform` ships first; this story's recipe runs *after* the base-image swap)
**ADRs honored:** [Phase 7 ADR-0014](../ADRs/0014-multi-stage-refactor-recipe-synchronous.md) (**synchronous, NO `asyncio.gather` over per-stage AST work**), [Phase 7 ADR-0013](../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md) (pure-Python `dockerfile-parse`)

> **⚠ Amendment A sequencing note (2026-05-20).** This story predates Phase 7 Amendment A ([`../final-design.md` §Amendment A](../final-design.md)). Its acceptance criteria are **extended by [S16-02](S16-02-recipe-contract-amendment.md)** — the multi-stage refactor consumes the build-toolchain catalog ([S14-01](S14-01-toolchain-classification-catalog.md)) and `native_modules` slice ([S14-02](S14-02-native-modules-slice.md)) to place deps in the right stage and select the `*-dev` builder image, and refuses via the [S16-01](S16-01-migration-refusal-taxonomy.md) taxonomy. Do **not** execute before Steps 13–16 land. See [`README.md` §"Stories — Amendment A"](README.md).

## Context

`DockerfileMultiStageRefactorTransform` is the expensive path: the source Dockerfile has shell-using `RUN` lines (e.g., `RUN apk add --no-cache curl && curl -fL ... | tar xz ...`) that **cannot** survive a distroless runtime stage (no `/bin/sh`). The recipe rewrites the Dockerfile so those shell operations move into a **builder stage**, and the runtime stage receives only the produced artifacts via `COPY --from=builder`. The runtime stage gets exec-form `CMD`; shell-form commands are out.

Performance-first proposed parallelizing the per-stage AST manipulation via `asyncio.gather`. The critic landed this as theatrical (`critique.md`): `asyncio.gather` over CPU-bound work without `loop.run_in_executor(...)` is sequential with async overhead — no parallelism happens. [ADR-0014](../ADRs/0014-multi-stage-refactor-recipe-synchronous.md) locks the recipe as **synchronous**: a plain Python `for` loop over stages. The p99 budget is **≤ 350 ms** on typical 2–3 stage Dockerfiles. If a Phase-13 telemetry pass shows multi-stage wall-clock is genuinely the bottleneck, a future ADR can ship `run_in_executor` with thread-pool tuning — but that's data-driven future work, not Phase-7 speculative optimization.

The risk profile is highest here in Step 10: per-stage AST manipulation has corner cases (`COPY --from=base` referencing a now-removed stage; `ARG`-driven stage names; build-time secrets). [Edge case #7 in `phase-arch-design.md`](../phase-arch-design.md) names this: a Dockerfile with `COPY --from=base` referencing a removed stage produces a broken Dockerfile — and `DockerfilePolicyGate` (S10-03) catches it. **The fixtures must be pinned BEFORE implementation** so the recipe is written against concrete edge cases, not in the abstract.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §11` — `DockerfileMultiStageRefactorTransform` per-stage AST manipulation; synchronous; p99 ≤ 350 ms; `TransformOutcome(kind="not_applicable", reason="dockerfile_parse_failed")` failure path.
  - `../phase-arch-design.md §Edge cases #7` — `COPY --from=base` referencing removed stage → broken Dockerfile → caught by `DockerfilePolicyGate`. The recipe SHOULD detect this and refuse upfront (cheaper than waiting for the gate).
  - `../phase-arch-design.md §Edge cases #13` — `dockerfile-parse` cannot parse exotic Dockerfile syntax (heredocs, ARG-driven FROM) → `not_applicable`.
  - `../phase-arch-design.md §Patterns considered and deliberately rejected` — `asyncio.gather` over per-stage CPU-bound work is theatrical.
- **Phase ADRs:**
  - [`../ADRs/0014-multi-stage-refactor-recipe-synchronous.md`](../ADRs/0014-multi-stage-refactor-recipe-synchronous.md) — synchronous recipe; **AC-2 below requires AST-walk fence** mechanically rejecting `asyncio.gather` in the recipe body.
  - [`../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md`](../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md) — pure-Python `dockerfile-parse`, not OpenRewrite.
- **Existing code:**
  - `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py` (S10-01) — sibling recipe; mirror its file layout, `Transform` ABC compliance shape, DI of catalog + logger, golden-diff testing.
  - `src/codegenie/transforms/transform.py` — `Transform` ABC.
  - Phase 3 `plugins/vulnerability-remediation--node--npm/recipes/npm_lockfile_pin.py` — the closest-sibling concrete recipe.
  - `tests/fixtures/portfolio/multi-stage-dockerfile/Dockerfile` (S12-01 fixture; **this story creates the seed fixtures it depends on as part of pinning edge cases**).

## Goal

Land `plugins/distroless-migration--node--npm/recipes/dockerfile_multi_stage.py`. `DockerfileMultiStageRefactorTransform(Transform)` is a synchronous, pure-Python `dockerfile-parse`-driven recipe that walks the Dockerfile stage-by-stage in a plain `for` loop, identifies shell-using `RUN` lines that must move to a builder stage, rewrites the runtime stage to use exec-form `CMD` and `COPY --from=builder`, and produces a deterministic byte-identical diff matching `tests/golden/dockerfile-diffs/multi-stage-refactor.diff`. The recipe body contains **no `asyncio.gather` over per-stage work** — enforced mechanically by an AST-walk fence (AC-2 below). Lands in p99 ≤ 350 ms across 1000 trials on a 4-stage Dockerfile.

## Acceptance criteria

### Recipe surface

- [ ] **AC-1 — Module + class location.** `plugins/distroless-migration--node--npm/recipes/dockerfile_multi_stage.py` defines `class DockerfileMultiStageRefactorTransform(Transform)`. Constructor signature mirrors S10-01: `__init__(self, *, catalog: ChainguardCatalog, logger: Logger) -> None`. `isinstance(t, Transform)` is `True`; the four ABC attributes are class-level annotations (mirror Phase 0 `Probe(ABC)` precedent).
- [ ] **AC-2 — AST-walk fence: NO `asyncio.gather` in recipe body.** `tests/fence/test_dockerfile_multi_stage_no_asyncio_gather.py` parses `dockerfile_multi_stage.py` via `ast.parse(...)`, walks all `Call` nodes in `DockerfileMultiStageRefactorTransform.apply` AND any helper methods/functions in the module, and asserts that NONE call `asyncio.gather`, `asyncio.wait`, `asyncio.as_completed`, `loop.run_in_executor`, or `concurrent.futures.*.submit`. The fence is mechanical — not a doc-comment, not a convention. A deliberately-planted `await asyncio.gather(...)` in the recipe body fails the fence with a clear file/line diagnostic. (Locks ADR-0014.)
- [ ] **AC-3 — Synchronous shape proven at runtime.** The recipe's `apply()` is either a plain `def` (not `async def`) or an `async def` with no `await` keyword in the body. Test: `inspect.iscoroutinefunction(DockerfileMultiStageRefactorTransform.apply)` is `False` (pin the simpler `def` shape); OR if `async def` is preferred for orchestrator-compat (ADR-0014 §Consequences allows either), the AST-walk fence ALSO asserts zero `await` statements in `apply()`. Pick one shape and stay with it; document in the module docstring.

### `applicability()` semantics

- [ ] **AC-4 — `Applies` iff multi-stage shell rewrite is genuinely needed.** `applicability(ctx)` returns `Applies` only when: (a) the Dockerfile parses cleanly; (b) at least one stage uses shell-using `RUN` AND at least one of those `RUN` lines produces artifacts referenced by a downstream stage (otherwise it's just a `RUN` that should be deleted, not moved); (c) the target distroless image (per the catalog row) genuinely lacks `/bin/sh`. Otherwise `NotApplicable(reason=...)`.
- [ ] **AC-5 — Typed `NotApplicable` reasons** pulled from module-level `_NOT_APPLICABLE_REASONS: Final[frozenset[str]]`: `"dockerfile_parse_failed"`, `"no_shell_rewrite_needed"` (single-stage with no shell), `"shell_invocation_not_rewritable"` (the shell command isn't a known artifact-producer per a small `_REWRITABLE_PATTERNS: Final[tuple[Pattern[str], ...]]` allowlist; matches edge case #2 in arch design), `"copy_from_stage_dangling"` (`COPY --from=<name>` references a stage the recipe would remove — the recipe refuses upfront rather than producing a broken diff per edge case #7).
- [ ] **AC-6 — Module-level `_WARNING_IDS: Final[frozenset[str]]`** (`dockerfile_multi_stage.*` namespace) validated at import via `raise AssertionError(...)` (NOT bare `assert`). Pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` (Phase 1 ADR-0007).

### `apply()` semantics and determinism

- [ ] **AC-7 — Per-stage AST manipulation in a plain `for` loop.** The body iterates `for stage in parsed.structure:` (or equivalent `dockerfile-parse` API). No `asyncio.gather`. No thread pool. No `concurrent.futures`.
- [ ] **AC-8 — Shell-using `RUN` lines move to a builder stage.** Given a Dockerfile with `RUN apk add --no-cache curl && curl ... | tar xz ...` in the runtime stage, `apply()` produces a Dockerfile with that line moved into a `FROM <pre-distroless> AS builder` stage and the runtime stage receiving the produced artifact via `COPY --from=builder`. Exact diff: byte-equal to `tests/golden/dockerfile-diffs/multi-stage-refactor.diff`.
- [ ] **AC-9 — Runtime stage exec-form `CMD`.** Shell-form `CMD npm start` in the runtime stage is rewritten to exec-form `CMD ["npm", "start"]`. If the original `CMD` is already exec-form, no change.
- [ ] **AC-10 — Idempotence.** Applying the recipe to its own output yields `NotApplicable(reason="no_shell_rewrite_needed")` — the rewrite has already happened. Test: `tests/unit/transforms/recipes/test_dockerfile_multi_stage.py::test_idempotent`.
- [ ] **AC-11 — Property test: stage-order permutation.** Hypothesis-generated 4-stage Dockerfiles with a builder stage + runtime stage and 2 unrelated intermediate stages → `apply()` produces byte-identical output across stage-order permutations (the recipe doesn't depend on input ordering). `tests/property/transforms/test_dockerfile_multi_stage_idempotence.py`.

### Edge-case fixtures pinned BEFORE implementation

- [ ] **AC-12 — Edge-case fixture set committed first.** `tests/fixtures/recipes/dockerfile-multi-stage/` contains, at minimum, these six fixtures committed in the same PR as (or one PR ahead of) the recipe body:
  - `simple-2-stage/Dockerfile` — builder + runtime; happy path.
  - `4-stage-rewrite/Dockerfile` — the perf benchmark fixture; matches the golden diff.
  - `copy-from-removed-stage/Dockerfile` — `COPY --from=base` references a stage the rewrite would remove (edge case #7); expected outcome: `NotApplicable(reason="copy_from_stage_dangling")`.
  - `unrewriteable-shell/Dockerfile` — `RUN /bin/sh -c "complicated; pipeline; |&" `; expected outcome: `NotApplicable(reason="shell_invocation_not_rewritable")`.
  - `already-multistage-clean/Dockerfile` — already builder + runtime, no shell in runtime; expected outcome: `NotApplicable(reason="no_shell_rewrite_needed")`.
  - `arg-driven-from/Dockerfile` — `ARG NODE_VERSION; FROM node:${NODE_VERSION}`; expected outcome: `NotApplicable(reason="dockerfile_parse_failed")` per edge case #13.
- [ ] **AC-13 — Each edge-case fixture has a paired unit test** asserting the expected `Applicability` and (where applicable) the expected diff. Tests are committed BEFORE the recipe body (red-first per Rule 9).

### Golden + perf

- [ ] **AC-14 — Golden diff pinned.** `tests/golden/dockerfile-diffs/multi-stage-refactor.diff` exists and is byte-equal to the recipe's output on `tests/fixtures/recipes/dockerfile-multi-stage/4-stage-rewrite/Dockerfile`.
- [ ] **AC-15 — p99 ≤ 350 ms.** `tests/perf/test_dockerfile_recipes.py::test_multi_stage_p99_under_350ms` runs `apply()` on the 4-stage fixture 1000 times; p99 ≤ 350 ms. Marked `@pytest.mark.bench`. (Honest cost per ADR-0014; the synchronous shape pays it explicitly.)

### Gates

- [ ] **AC-16** — `mypy --strict plugins/distroless-migration--node--npm/recipes/` clean.
- [ ] **AC-17** — `ruff check ... && ruff format --check` clean.
- [ ] **AC-18** — `make lint-imports` green (no LLM SDK; no `codegenie.exec` import in the recipe module — same rule as S10-01).
- [ ] **AC-19** — Phase 3–6.5 regression suite green; `bench/vuln-remediation/` cassette replay byte-equal.

## Implementation outline

1. **Pin the six edge-case fixtures first** (`tests/fixtures/recipes/dockerfile-multi-stage/`). Each fixture is a single `Dockerfile` plus an optional `expected.diff` (for the happy paths). Commit these BEFORE the recipe body.
2. **Write the failing tests** (`tests/unit/transforms/recipes/test_dockerfile_multi_stage.py`) — one per fixture, asserting expected `Applicability` outcome. Also write the AST-walk fence test (`tests/fence/test_dockerfile_multi_stage_no_asyncio_gather.py`) — it fails because the file doesn't exist yet. Also write the property test scaffold (`tests/property/transforms/test_dockerfile_multi_stage_idempotence.py`).
3. **Land `plugins/distroless-migration--node--npm/recipes/dockerfile_multi_stage.py`** with a synchronous `apply()` that: (a) parses the Dockerfile via `dockerfile-parse`; (b) iterates stages in a plain `for` loop; (c) classifies each `RUN` line via `_REWRITABLE_PATTERNS`; (d) reconstructs a new Dockerfile with shell-using artifact-producing `RUN` lines moved into a `builder` stage and the runtime stage referencing them via `COPY --from=builder`; (e) rewrites shell-form `CMD` to exec-form; (f) emits unified diff via `difflib.unified_diff`.
4. **Module-level `_REWRITABLE_PATTERNS: Final[tuple[Pattern[str], ...]]`** — a small allowlist (e.g., `apk add ... && wget|curl ... | tar xz`, `apt-get install`, ` build && ` heuristics). Iterated, not branched. Documented in the module docstring with one example per pattern.
5. **Pre-check for `COPY --from=<removed-stage>`** before rewriting: if the rewrite would dangle a `COPY --from=base`, return `NotApplicable(reason="copy_from_stage_dangling")` upfront. This is cheaper than letting `DockerfilePolicyGate` (S10-03) catch it after-the-fact.
6. **Land the golden diff** (`tests/golden/dockerfile-diffs/multi-stage-refactor.diff`) by hand-running the recipe on `tests/fixtures/recipes/dockerfile-multi-stage/4-stage-rewrite/Dockerfile` and capturing the output. Hand-review.
7. **AST-walk fence** (`tests/fence/test_dockerfile_multi_stage_no_asyncio_gather.py`): `ast.parse(open(recipe_path).read())` → `ast.walk` → assert no `Attribute` access matching `asyncio.gather|asyncio.wait|asyncio.as_completed`, no `Call` to `loop.run_in_executor`. Fence message names ADR-0014.
8. **Perf bench** — `tests/perf/test_dockerfile_recipes.py::test_multi_stage_p99_under_350ms` over 1000 trials; p99 assertion.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/fence/test_dockerfile_multi_stage_no_asyncio_gather.py`

```python
import ast
from pathlib import Path

RECIPE = Path(
    "plugins/distroless-migration--node--npm/recipes/dockerfile_multi_stage.py"
)

_BANNED_DOTTED_NAMES = {
    ("asyncio", "gather"),
    ("asyncio", "wait"),
    ("asyncio", "as_completed"),
}


def _dotted(node: ast.AST) -> tuple[str, ...]:
    """Walk Attribute chain into a dotted tuple ('asyncio', 'gather')."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return tuple(reversed(parts))


def test_recipe_body_contains_no_asyncio_gather() -> None:
    tree = ast.parse(RECIPE.read_text())
    offending: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            dotted = _dotted(node.func)
            if len(dotted) >= 2 and dotted[-2:] in _BANNED_DOTTED_NAMES:
                offending.append((node.lineno, ".".join(dotted)))
            # run_in_executor on any object
            if isinstance(node.func, ast.Attribute) and node.func.attr == "run_in_executor":
                offending.append((node.lineno, f"<obj>.run_in_executor"))
    assert not offending, (
        f"ADR-0014 violation in {RECIPE}: per-stage async-fan-out is theatrical "
        f"(CPU-bound without run_in_executor). Synchronous recipe required. "
        f"Offending: {offending}"
    )


def test_apply_method_has_no_await() -> None:
    tree = ast.parse(RECIPE.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == "apply":
            awaits = [n for n in ast.walk(node) if isinstance(n, ast.Await)]
            assert not awaits, (
                f"ADR-0014: apply() must be synchronous (no `await` in body). "
                f"Found: {[(a.lineno) for a in awaits]}"
            )
            return
    raise AssertionError("apply() method not found in recipe module")
```

State why it fails: `FileNotFoundError` — the recipe module doesn't exist yet.

### Green — minimal pass

- Land the six edge-case fixtures.
- Land `dockerfile_multi_stage.py` with synchronous `apply()` (plain `def`, no `async`, no `await`). Iterate stages in a plain `for` loop. Implement the rewrite logic using `dockerfile-parse`'s `DockerfileParser.structure` (list of dicts with `instruction`, `value`, `startline`).
- Land the golden diff.
- All AC-12 fixtures' paired tests pass.

### Refactor

- Hoist the rewrite-decision predicates into pure helper functions (`_is_shell_using_run`, `_is_artifact_producer`, `_finds_dangling_copy_from`). Test each in isolation.
- Pin `_REWRITABLE_PATTERNS` as a module-level `Final` tuple of `re.compile(...)` patterns. Each pattern carries a one-line comment naming the apt/apk command shape it matches. Document the allowlist's growth path (new pattern = new tuple row + new test fixture).
- Confirm the `Refactor` pass doesn't introduce `asyncio.gather`; re-run the AST-walk fence.
- Add a contract-snapshot-helper docstring on `DockerfileMultiStageRefactorTransform`: names ADR-0014, names ADR-0013, names the golden file, names the synchronous shape.
- Confirm p99 ≤ 350 ms. If it regresses, suspect: (a) recompiling regex on every call (use module-level `Final`); (b) recreating the `DockerfileParser` per stage (instantiate once per `apply`); (c) string-concatenation in a loop (`"".join(parts)`).

## Files to touch

| Path | Why |
|---|---|
| `plugins/distroless-migration--node--npm/recipes/dockerfile_multi_stage.py` | NEW — synchronous per-stage AST rewrite recipe per ADR-0014; uses `dockerfile-parse` per ADR-0013; **no `asyncio.gather`**. |
| `plugins/distroless-migration--node--npm/recipes/__init__.py` | Extend from S10-01 — additive import line so `dockerfile_multi_stage` registers (if S8-03's `api.py` side-effect-imports the recipes package). |
| `tests/fixtures/recipes/dockerfile-multi-stage/simple-2-stage/Dockerfile` | NEW — happy-path 2-stage fixture. |
| `tests/fixtures/recipes/dockerfile-multi-stage/4-stage-rewrite/Dockerfile` | NEW — 4-stage perf fixture; golden-diff seed. |
| `tests/fixtures/recipes/dockerfile-multi-stage/copy-from-removed-stage/Dockerfile` | NEW — edge case #7 fixture. |
| `tests/fixtures/recipes/dockerfile-multi-stage/unrewriteable-shell/Dockerfile` | NEW — `shell_invocation_not_rewritable` fixture. |
| `tests/fixtures/recipes/dockerfile-multi-stage/already-multistage-clean/Dockerfile` | NEW — already-rewritten; idempotence path. |
| `tests/fixtures/recipes/dockerfile-multi-stage/arg-driven-from/Dockerfile` | NEW — edge case #13 (`dockerfile_parse_failed`). |
| `tests/unit/transforms/recipes/test_dockerfile_multi_stage.py` | NEW — AC-4..AC-10 + AC-13 suite; one test per fixture. |
| `tests/property/transforms/test_dockerfile_multi_stage_idempotence.py` | NEW — Hypothesis stage-order permutation property (AC-11). |
| `tests/fence/test_dockerfile_multi_stage_no_asyncio_gather.py` | NEW — AST-walk fence enforcing AC-2 + AC-3. |
| `tests/golden/dockerfile-diffs/multi-stage-refactor.diff` | NEW — pinned exemplar diff (AC-14). |
| `tests/perf/test_dockerfile_recipes.py` | Extend from S10-01 — `test_multi_stage_p99_under_350ms` (AC-15), `@pytest.mark.bench`. |

## Out of scope

- **Base-image swap (single `FROM` rewrite)** — S10-01. This story handles only the multi-stage shell-relocation; the base-image swap is composed by the orchestrator (both recipes apply to the same Dockerfile if both `applicability()` calls return `Applies`).
- **`docker buildx build`** — `DistrolessBuildGate` (S10-04). This recipe produces a diff; it does NOT build the image.
- **`DockerfilePolicyGate` invariant evaluation** — S10-03.
- **`run_in_executor` / thread-pool parallelism** — explicitly deferred per ADR-0014. If Phase 13 telemetry justifies it, a future ADR ships it. Phase 7 does not.
- **Real-shell `RUN` parsing beyond the allowlist** — only `_REWRITABLE_PATTERNS` shapes ship in this story. A future ADR can widen the allowlist; do not silently broaden it in this story.

## Notes for the implementer

- **ADR-0014 is the canonical citation.** The synchronous shape is the decision; `asyncio.gather` over per-stage AST work is theatrical (no parallelism without `run_in_executor`); the simpler synchronous loop ships. The AST-walk fence (AC-2) is the mechanical enforcement — not a comment, not a convention. If you reach for `asyncio.gather` for "consistency with async-everywhere conventions", the fence will refuse the commit.
- **Pin fixtures BEFORE the recipe body.** Rule 9: tests verify intent; the intent is "this Dockerfile shape produces that diff." If the fixtures are written after the recipe, the tests become tautological (they pass because they were authored to match what the recipe happens to do). Six fixtures, six paired tests, then the recipe. The ordering is load-bearing for catching the corner cases.
- **`copy_from_stage_dangling` is a deliberate pre-check.** Edge case #7 names a real failure: the rewrite could produce a Dockerfile with `COPY --from=base` referencing a stage the rewrite removed. `DockerfilePolicyGate` (S10-03) catches it as a strict-AND failure — but the recipe should refuse upfront so operators get a `NotApplicable` diagnostic, not a gate failure they have to debug. Cheap check (build the set of stage names *after* rewrite; assert all `COPY --from=` references resolve); refuse if any dangle.
- **`_REWRITABLE_PATTERNS` is a closed allowlist.** Each pattern matches a known artifact-producing shell command shape. If you find yourself wanting to add a regex for "anything with `&&`", stop — that's primitive obsession on shell strings. The pattern should match a specific command shape (`apk add ... && curl ... | tar xz`) and be tested with a paired fixture. A new pattern is a new ADR amendment if it widens the trust boundary; a new pattern that narrows to a specific shape is a fixture + a pattern row + a paired test.
- **`async def` vs `def`.** ADR-0014 §Consequences allows either, but pick one and stay. Recommendation: plain `def`. Rationale: Phase 5's orchestrator calls recipes via `await Transform.apply(ctx)`-shaped dispatch in some places — but Phase 3's `npm_lockfile_pin.py` ships a plain `def apply()` and it works (the orchestrator handles the sync/async dispatch). Match Phase 3's precedent (global Rule 11).
- **`dockerfile-parse` API caveats.** The library uses `DockerfileParser` with mutable `content`/`structure` attributes; the parser is stateful. Construct one parser instance per `apply()` invocation; never share across invocations. Mutating `structure` directly is supported but undocumented — reconstruct the Dockerfile text from the modified structure and re-parse if you need a clean view.
- **Performance budget — honest cost.** p99 ≤ 350 ms on a 4-stage Dockerfile is honest. Most Dockerfiles in the corpus are 2-3 stage; expect ~150 ms typical. The bench fixture is intentionally 4-stage to exercise the upper bound.
- **`TransformProvenance.capability_use_id`** — see S10-01 notes; same pattern (sentinel until S4-05 ships).
- **Idempotence path.** Applying the recipe to its own output should return `NotApplicable(reason="no_shell_rewrite_needed")` — the rewrite has already happened (no shell-using `RUN` lines remain in the runtime stage). This is a non-negotiable invariant; without it, double-runs produce diverging Dockerfiles. The property test (AC-11) catches regressions.
- **Defer parallelism honestly.** ADR-0014 §Consequences names the deferred-improvement note: include the docstring line "Per-stage parallelism via `loop.run_in_executor` is a deferred optimization; revisit with Phase 13 telemetry if multi-stage wall-clock becomes the workflow bottleneck." Don't TODO it in code — TODOs rot. The ADR is the canonical note.
