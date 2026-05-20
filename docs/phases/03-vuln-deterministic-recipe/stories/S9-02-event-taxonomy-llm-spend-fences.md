# Story S9-02 — Event-taxonomy completeness fence + `$0.00` LLM-spend assertion

**Step:** Step 9 — CI gates, import-linter contracts, performance baselines, bench backfill hook
**Status:** HARDENED
**Effort:** S
**Depends on:** S9-01 (CI / `tests/fence/` wiring). For the fence tests to run *green* (not merely exist) the artifacts they read must be shipped: **S6-01** (`src/codegenie/plugins/events.py` — the two discriminated unions), **S6-04 / S5-02 / S6-02** (`transforms/` emit sites), **S7-01 / S7-03** (plugin-subgraph emit sites under `plugins/{slug}/`), **S5-05** (`RemediationReport` schema — the LLM-spend fence locks the *absence* of `llm_cost_usd`), **S8-02** (the first golden `remediation-report.yaml`). The executor must pause if any of these is not GREEN — see TDD §Red.
**ADRs honored:** ADR-0005 (two-stream event log — the discriminated unions `WorkflowInternalEvent` / `WorkflowSpanningEvent` are the source of truth this fence enforces; "crossing the taxonomy boundary requires an ADR amendment" is the rule the test makes mechanical), ADR-0011 (honest framing — silent dead enum values and undeclared emits are exactly the kind of decay this fence prevents)

## Validation notes (2026-05-20 — phase-story-validator)

Verdict: **HARDENED**. One block-tier defect + eight harden/nit findings. The story's *goal* — two mechanical fences (event-taxonomy completeness + a `$0.00` LLM-spend assertion) — is sound and traces to `High-level-impl.md §Step 9` and ADR-0005. The *mechanism* prescribed by AC-1 and the §Red TDD plan was built on a wrong model of the S6-01 `EventLog` API.

**Block-tier closure:**

1. **Taxonomy-fence extraction contradicted the shipped S6-01 API (Consistency).** S6-01 (`HARDENED`) ships `WorkflowInternalEvent` / `WorkflowSpanningEvent` as **module-level `TypeAlias = Annotated[V1 | V2 | …, Field(discriminator="event_type")]`** — *not* class definitions — and `emit_internal(event)` / `emit_spanning(event)` take a **constructed Pydantic variant instance**, never an `event_type=` keyword. The original `_extract_literal_set("WorkflowInternalEvent")` looked for an `ast.ClassDef` with an `event_type` `AnnAssign` (would raise `AssertionError` — the alias is an `AnnAssign`, not a `ClassDef`); the original `_extract_emit_sites()` looked for `keyword(arg="event_type")` on the emit calls (would find zero — *every* declared literal falsely reported "dead"). AC-1, the Implementation outline steps 1–3, the §Notes escape hatch, and both §Red test files were rewritten to the correct model: resolve each union alias's `Annotated[…]` member list → variant classes → each class's `event_type: Literal[…]` default; extract emit sites from the **constructed variant class** in the first positional argument of `emit_internal` / `emit_spanning`.

**Harden-tier closures:**

2. §Context taxonomy enumeration was stale (14 internal / 8 spanning) — S6-01 ships **16 / 9**. Corrected, and marked illustrative: `events.py` is the only runtime source of truth; the fence derives the set by AST and must never hard-code a count.
3. Stale reference to `tests/fence/test_phase3_importlinter_contracts.py` — that file does not exist; S9-01 explicitly forbade forking it. Repointed to the real precedents `test_phase3_importlinter_contracts_shape.py` and the auto-discovering AST-walk fence `test_phase3_cross_plugin_isolation.py`.
4. `Depends on:` understated the real prerequisites — expanded to name S5-05 / S6-01 / S6-04 / S8-02 + the emit-site stories.
5. New AC added for **variable-event** (`event = SomeVariant(...); log.emit_internal(event)`) and **factory-constructor** (`Variant.from_result(...)` — the exact shape S6-01 AC-MIG's migrated `cache prune` CLI emit uses) emit sites. With the corrected API these are first-class, not the rare case the original §Notes assumed.
6. The taxonomy fence's extraction logic is now mandated as **pure, path-parameterised functions** so the real fence and the `tmp_path` negative-regression tests call the *same* code — the original helpers hard-coded module-level `EVENTS` / `SEARCH_ROOTS`, leaving the negative-regression ACs unsatisfiable.
7. §Notes escape-hatch (`# fence-allow:`) and the alias-resolution note re-keyed off the corrected API.

Full report: [`_validation/S9-02-event-taxonomy-llm-spend-fences.md`](_validation/S9-02-event-taxonomy-llm-spend-fences.md).

## Context

ADR-0005 ships two Pydantic discriminated unions, each shipped by S6-01 as a **module-level `TypeAlias = Annotated[V1 | V2 | … , Field(discriminator="event_type")]`** over a set of frozen variant classes (`src/codegenie/plugins/events.py`) — *not* as `class WorkflowInternalEvent` definitions. As shipped: `WorkflowInternalEvent` has **16** variants (`PluginsLoaded`, `PluginResolved`, `BundleBuilt`, `BundleEntryPromoted`, `RecipeMatched`, `RecipeApplied`, `RecipeSkipped`, `RecipeFailed`, `InstallStageOutcome`, `TestStageOutcome`, `LocalBranchWritten`, `RequiresHumanReview`, `AdapterDegraded`, `StageOutcome`, `FilesystemRaceDetected`, `GitHooksDisabledForRun`) and `WorkflowSpanningEvent` has **9** (`WorkflowStarted`, `WorkflowCompleted`, `CostSandboxRun`, `CapabilityMinted`, `CapabilityUsed`, `PluginRegistryCorrupted`, `BenchReplayable`, `StaleVulnIndex`, `CacheGcCompleted`); each variant carries an `event_type: Literal["<snake>"]` discriminator field. **This list is illustrative — `events.py` is the only runtime source of truth; the fence derives the variant set from it by AST and must never hard-code a count.** (`phase-arch-design.md §Component design C9`; S6-01 AC-6 / AC-7.)

Two failure modes the human eye misses:

1. **Dead enum values.** A variant lands in a union (because someone *planned* to emit it) but no production code path ever constructs that variant inside an `emit_internal(...)` / `emit_spanning(...)` call. The taxonomy lies about what the system actually does. Phase 9's Temporal/Postgres migration would lift a never-populated event type and propagate the lie.
2. **Undeclared / mis-stream emits.** A call site constructs an event variant that is not a member of the stream's union — a typo'd class name, or a `WorkflowSpanningEvent` variant handed to `emit_internal(...)`. Pydantic's discriminated-union validation rejects a genuinely-unknown shape at runtime — but only if the call site is exercised by a test, and it cannot catch a *valid spanning variant emitted on the wrong stream*. The fence walks the AST for every `.emit_internal(...)` / `.emit_spanning(...)` call, reads the variant class constructed in the first positional argument, and cross-references it against the declared union for that stream.

The second fence target is the `$0.00` LLM-spend assertion. Phase 3 is the deterministic-recipe path; no LLM is invoked; therefore no `remediation-report.yaml` Phase 3 produces should carry a nonzero `llm_cost_usd`. The strongest version of this assertion is **the field must not exist at all** in any Phase 3 `RemediationReport`. Asserting "nonzero is zero" is too lax — a field-with-value-0 is still a field the schema admits, which means Phase 3 has silently agreed to a cost-tracking concept it has no business shipping. Absence is the right signal. (Phase 4 will add `llm_cost_usd` to its own report variant additively when LLM fallback lands; Phase 3's report type must not pre-empt it.)

The fence walks every `tests/golden/remediation-reports/*.yaml` golden file plus every `remediation-report.yaml` produced under `.codegenie/context/` during the test run and asserts `"llm_cost_usd"` is not a key (at any nesting depth). On nonzero / present, fail with the offending file path so the operator can investigate.

S9-01 wired the CI infrastructure (matrix, `import-linter` contracts, `make check` extension). This story lands two specific fence tests inside that infrastructure: one for taxonomy completeness, one for LLM-spend absence.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C9` (Event taxonomy — contract) — the two discriminated unions; the fence reads this as the spec.
  - `../phase-arch-design.md §Harness engineering / Determinism vs. probabilism` — the three-layer LLM fence; the `$0.00` assertion is the *evidence* layer ("no LLM cost ever recorded"), complementing the structural import-linter contract and the runtime closure fence.
  - `../phase-arch-design.md §Testing strategy / CI gates` — `make fence` (the cold-start fence) + `tests/fence/test_event_taxonomy_complete.py` + `tests/fence/test_no_llm_spend.py` are the two new fence tests this story ships.
  - `../High-level-impl.md §Step 9` — the verbatim Done criterion: "`pytest tests/fence/test_event_taxonomy_complete.py` green — every event type has both a declared variant and an emit site" and "`tests/fence/test_no_llm_spend.py` greps every produced `remediation-report.yaml` and fails on any nonzero `llm_cost_usd` field (field must not exist in Phase 3)".
- **Phase ADRs:**
  - `../ADRs/0005-two-stream-event-log-per-adr-0034.md` — "Adding a new event variant requires editing the corresponding discriminated-union module + supplying a Pydantic `extra="forbid"` payload schema. Cross-cutting concerns ... go on the spanning stream; per-workflow state transitions ... go on the internal stream." The fence is how that rule is mechanized.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — the discipline-as-tests pattern.
- **Existing code:**
  - `src/codegenie/plugins/events.py` (S6-01) — the two `TypeAlias = Annotated[…]` unions + the frozen variant classes; the fence resolves the union members and reads each class's `event_type` literal. **Note the shape: `WorkflowInternalEvent` / `WorkflowSpanningEvent` are module-level `AnnAssign` aliases, not `ClassDef`s** — see S6-01 AC-6 / AC-7 + Implementation outline step 3.
  - `src/codegenie/transforms/orchestrator.py` (S6-04) — the primary emit site; the fence's AST walk reads from here + every plugin's subgraph. Emit sites construct a variant instance (`emit_internal(RecipeApplied(...))`); some use a factory (`emit_spanning(CacheGcCompleted.from_result(...))` — S6-01 AC-MIG) or a variable (`event = …; emit_internal(event)`).
  - `tests/golden/remediation-reports/*.yaml` (S8-02; directory + README created by S5-05 AC-Golden-1) — the golden corpus; the LLM-spend fence walks them.
  - `tests/fence/test_phase3_cross_plugin_isolation.py` (S9-01) — the auto-discovering AST-walk fence; mirror its directory-glob + `ast.parse` discovery shape. `tests/fence/test_phase3_importlinter_contracts_shape.py` — sibling meta-fence; mirror its docstring + ADR cross-reference conventions. (The originally-named `test_phase3_importlinter_contracts.py` does not exist — S9-01 explicitly forbade forking it.)

## Goal

Ship two fence tests that mechanically close two failure modes Phase 3 cannot tolerate: taxonomy decay (dead enum values or undeclared emits) and LLM-spend leakage into the deterministic-recipe path. Both run under `make check` and fail loud with a specific diagnostic naming the offending file + literal.

## Acceptance criteria

- [ ] `tests/fence/test_event_taxonomy_complete.py` (NEW) parses `src/codegenie/plugins/events.py` and, for each of the two discriminated-union **type aliases** `WorkflowInternalEvent` / `WorkflowSpanningEvent` (shipped by S6-01 as module-level `TypeAlias = Annotated[V1 | V2 | …, Field(discriminator="event_type")]` — **not** class definitions), resolves the `Annotated[…]` member list to its variant classes and reads each class's `event_type: Literal["…"] = "…"` default — yielding two `{class_name: event_type_literal}` maps (internal + spanning). AST-walks `src/codegenie/plugins/`, `src/codegenie/transforms/`, and `plugins/{slug}/**/*.py` for `.emit_internal(...)` / `.emit_spanning(...)` calls; at each call site reads the **constructed variant class** from the first positional argument (`emit_internal` / `emit_spanning` take a constructed Pydantic event instance — there is **no** `event_type=` keyword). Asserts: (a) every variant class declared in a union is constructed-and-emitted ≥1 time on the matching stream (no dead enum); (b) every class constructed inside an `emit_internal` / `emit_spanning` call is a member of that stream's union (no undeclared emit, no typo, no mis-stream emit — a `WorkflowSpanningEvent` variant such as `BenchReplayable` constructed inside `emit_internal(...)` is a failure). (validator: rewrote — original prescribed `WorkflowInternalEvent.event_type` `ClassDef` extraction + `event_type=`-kwarg call sites, both of which contradict the shipped S6-01 API; see Validation notes #1.)
- [ ] **Variable / factory emit sites are resolved, not silently dropped.** When the first positional argument of an `emit_internal` / `emit_spanning` call is (a) a classmethod/factory call — `log.emit_spanning(CacheGcCompleted.from_result(result, …))`, the exact shape S6-01 AC-MIG's migrated `cache prune` CLI emit uses — or (b) a bare `Name` (`event = RecipeApplied(...); log.emit_internal(event)`), the fence resolves the variant class: factory calls via the `Attribute(value=Name(<Class>), attr=…)` receiver; bare-`Name` args via a one-hop lookup of the nearest `<name> = <Variant>(...)` assignment within the enclosing function. If the class still cannot be resolved statically, the fence **fails** with a diagnostic naming `file:line`, unless the emit (or its assignment) carries a `# fence-allow: <ClassName>[, <ClassName>]` comment naming the possible variant(s) — those names are then folded into the emit-site set. (validator: added — with the corrected S6-01 API, variable- and factory-constructed events are first-class, not the rare case the original §Notes assumed.)
- [ ] `tests/fence/test_no_llm_spend.py` (NEW) walks: (a) `tests/golden/remediation-reports/*.yaml` and (b) any `**/remediation-report.yaml` produced during the test run under a configurable root (default: `.codegenie/`). For each YAML, recursively walks the parsed dict and asserts the key `"llm_cost_usd"` is **absent at every nesting depth**. Failure message names the file path and the JSON-pointer at which the key was found.
- [ ] The taxonomy fence's extraction logic is implemented as **pure, path-parameterised functions** — `declared_variants(events_path: Path) -> dict[str, dict[str, str]]` and `emit_sites(search_roots: Sequence[Path]) -> dict[str, set[str]]` — so the real fence (repo paths) and the negative-regression sub-tests (a `tmp_path` fake tree) drive the *same* code. The taxonomy fence has paired negative regression sub-tests (kept in the same file): one points the functions at a `tmp_path` fake events module + emit-site tree containing a synthetic emitted class **not** in the fake union (asserts the fence catches the undeclared/mis-stream emit) and one containing a synthetic declared variant with **no** emit site (asserts the fence catches the dead enum). The `tmp_path` scoping means the real codebase is never polluted. (validator: hardened — the original helpers hard-coded module-level `EVENTS` / `SEARCH_ROOTS`, leaving these negative ACs unsatisfiable.)
- [ ] `tests/fence/test_no_llm_spend.py` has a negative regression: a `tmp_path` YAML with `outcome: {llm_cost_usd: 0}` makes the fence fail with the JSON-pointer `/outcome/llm_cost_usd`. A second negative case asserts deep-nesting detection (`a/b/c/llm_cost_usd`).
- [ ] Both fence tests run under `make check` (Phase 3 `tests/fence/` directory wired in S9-01) and fail loud with a diagnostic naming (a) the union member literal + stream for taxonomy failures, (b) the YAML file + JSON-pointer for LLM-spend failures.
- [ ] `mypy --strict` clean; `ruff check`, `ruff format --check` clean on touched files.
- [ ] TDD plan's red test exists, committed, green.

## Implementation outline

1. **Taxonomy fence — declared variant extraction (`declared_variants(events_path)`).** `ast.parse` `events.py`. (a) Find the two module-level `AnnAssign` nodes whose target is `WorkflowInternalEvent` / `WorkflowSpanningEvent`; their value is `Subscript(Name("Annotated"), Tuple([<union>, Field(...)]))` — walk the `<union>` `BinOp` (`ast.BitOr`) tree to collect the member variant `Name`s. (b) Walk every `ClassDef`; find its `event_type` `AnnAssign` whose annotation is `Subscript(Name("Literal"), <slice>)` — note a single-member `Literal["x"]` has an `ast.Constant` slice, **not** an `ast.Tuple`; handle both. Output: two `{class_name: event_type_literal}` maps (internal + spanning). Fail loud if a union member has no matching `ClassDef` or no `event_type` literal.
2. **Taxonomy fence — emit-site extraction (`emit_sites(search_roots)`).** `rglob("*.py")` over `src/codegenie/plugins/`, `src/codegenie/transforms/`, and the top-level `plugins/` package root (plugin subgraphs live under `plugins/{slug}/`). For each file `ast.parse` and find `ast.Call` nodes whose `func` is `Attribute(attr="emit_internal" | "emit_spanning")`. From `call.args[0]` resolve the variant class: a direct constructor `Call(func=Name(<Class>))`; a factory `Call(func=Attribute(value=Name(<Class>), attr=…))`; a bare `Name` via a one-hop lookup of the nearest `<name> = <Variant>(...)` assignment inside the enclosing function. Unresolvable args fail the fence unless the line carries a `# fence-allow: <Class>` comment. Output: `{"emit_internal": {class names…}, "emit_spanning": {class names…}}`.
3. **Taxonomy fence — assertions.** Map each emitted class to its stream via the union membership from step 1. Assert: (a) every declared variant class is constructed-and-emitted ≥1 time on its own stream (no dead enum); (b) every emitted class is a member of the union for the method it was emitted on (no undeclared, no typo, no mis-stream — `BenchReplayable` is a `WorkflowSpanningEvent`; constructing it inside `emit_internal(...)` fails). Diagnostics name the class, the stream, and (for emit failures) `file:line`.
4. **LLM-spend fence — discovery.** Use `pathlib.Path.rglob` on both roots; load each YAML via `yaml.safe_load`; walk the result with a recursive helper that yields `(json_pointer, value)` tuples.
5. **LLM-spend fence — assertion.** For each YAML, assert no walked node has key `"llm_cost_usd"`. Failure message: `f"llm_cost_usd present in {path} at {json_pointer}: this field must not exist in Phase 3 (ADR-0005, see story S9-02)."`
6. **Negative regression scaffolding.** Both fence tests build a `tmp_path` synthetic case (fake module / fake YAML) and re-run the same logic to confirm the failure mode is detected. Keep the negatives inside the same file so the contract is co-located with its proof.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/fence/test_event_taxonomy_complete.py`

The extraction helpers below are **pure and path-parameterised** so the §Refactor step can lift them into `tests/fence/_helpers.py` unchanged and the negative-regression sub-tests can drive the *same* code against a `tmp_path` fake tree.

```python
import ast
from collections.abc import Sequence
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EVENTS = REPO / "src" / "codegenie" / "plugins" / "events.py"
SEARCH_ROOTS = (
    REPO / "src" / "codegenie" / "plugins",
    REPO / "src" / "codegenie" / "transforms",
    REPO / "plugins",
)
# {alias name in events.py: stream key}. S6-01 ships these as module-level
# `TypeAlias = Annotated[V1 | V2 | ..., Field(discriminator="event_type")]`.
_UNION_ALIASES = {"WorkflowInternalEvent": "internal", "WorkflowSpanningEvent": "spanning"}


def _union_member_names(tree: ast.Module, alias: str) -> frozenset[str]:
    """Variant class names in `<alias>: TypeAlias = Annotated[A | B | ..., Field(...)]`."""
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == alias
            and isinstance(node.value, ast.Subscript)
        ):
            sl = node.value.slice  # Annotated[...] -> Tuple([<union>, Field(...)])
            union = sl.elts[0] if isinstance(sl, ast.Tuple) else sl
            names: set[str] = set()
            stack: list[ast.expr] = [union]
            while stack:
                n = stack.pop()
                if isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr):
                    stack += [n.left, n.right]
                elif isinstance(n, ast.Name):
                    names.add(n.id)
            return frozenset(names)
    raise AssertionError(f"union alias {alias!r} not found as a module-level AnnAssign")


def _event_type_literal(classdef: ast.ClassDef) -> str | None:
    """The single string in a `event_type: Literal["x"]` field default."""
    for stmt in classdef.body:
        if (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.target.id == "event_type"
            and isinstance(stmt.annotation, ast.Subscript)
            and isinstance(stmt.annotation.value, ast.Name)
            and stmt.annotation.value.id == "Literal"
        ):
            sl = stmt.annotation.slice
            const = sl.elts[0] if isinstance(sl, ast.Tuple) else sl  # single-member Literal
            if isinstance(const, ast.Constant) and isinstance(const.value, str):
                return const.value
    return None


def declared_variants(events_path: Path) -> dict[str, dict[str, str]]:
    """{"internal": {ClassName: event_type_literal}, "spanning": {...}} — pure."""
    tree = ast.parse(events_path.read_text())
    classes = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    out: dict[str, dict[str, str]] = {"internal": {}, "spanning": {}}
    for alias, stream in _UNION_ALIASES.items():
        for cls_name in _union_member_names(tree, alias):
            cdef = classes.get(cls_name)
            assert cdef is not None, f"{alias} member {cls_name} has no ClassDef in events.py"
            lit = _event_type_literal(cdef)
            assert lit is not None, f"variant {cls_name} has no event_type Literal"
            out[stream][cls_name] = lit
    return out


def _resolved_class(arg: ast.expr, fn: ast.AST | None) -> str | None:
    """Variant class an emit-call argument constructs (direct / factory / one-hop var)."""
    if isinstance(arg, ast.Call):
        f = arg.func
        if isinstance(f, ast.Name):
            return f.id                                   # RecipeApplied(...)
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            return f.value.id                             # CacheGcCompleted.from_result(...)
    if isinstance(arg, ast.Name) and fn is not None:
        for stmt in ast.walk(fn):                         # one-hop `event = Variant(...)`
            if isinstance(stmt, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == arg.id for t in stmt.targets
            ):
                return _resolved_class(stmt.value, None)
    return None


def emit_sites(search_roots: Sequence[Path]) -> dict[str, set[str]]:
    """{"emit_internal": {ClassName...}, "emit_spanning": {ClassName...}} — pure.

    Unresolvable args raise AssertionError naming file:line unless the line
    carries a `# fence-allow: <Class>` comment (folded into the set instead).
    """
    sites: dict[str, set[str]] = {"emit_internal": set(), "emit_spanning": set()}
    for root in search_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            src = path.read_text()
            tree = ast.parse(src)
            enclosing: dict[ast.AST, ast.AST] = {}
            for fn in ast.walk(tree):
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for sub in ast.walk(fn):
                        enclosing.setdefault(sub, fn)
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in sites
                    and node.args
                ):
                    cls = _resolved_class(node.args[0], enclosing.get(node))
                    if cls is None:
                        # fall back to a `# fence-allow:` comment on the call line
                        line = src.splitlines()[node.lineno - 1]
                        marker = "# fence-allow:"
                        assert marker in line, (
                            f"{path}:{node.lineno} — {node.func.attr}(...) argument is not a "
                            f"statically-resolvable event variant; add `# fence-allow: <Class>`"
                        )
                        cls = line.split(marker, 1)[1].strip()
                    sites[node.func.attr].update(c.strip() for c in cls.split(","))
    return sites


def test_every_declared_variant_has_an_emit_site() -> None:
    """No dead enum values: every variant class in a union must be constructed
    inside an emit call on its own stream. A dead variant lies about what the
    system does and would propagate the lie into Phase 9's Temporal/Postgres
    migration (ADR-0005)."""
    declared = declared_variants(EVENTS)
    sites = emit_sites(SEARCH_ROOTS)
    dead_internal = set(declared["internal"]) - sites["emit_internal"]
    dead_spanning = set(declared["spanning"]) - sites["emit_spanning"]
    assert not dead_internal, f"Dead internal variants (no emit site): {sorted(dead_internal)}"
    assert not dead_spanning, f"Dead spanning variants (no emit site): {sorted(dead_spanning)}"


def test_every_emit_site_is_in_the_declared_union() -> None:
    """No undeclared emits and no mis-stream emits. A typo'd or wrong-stream
    variant slips past Pydantic until the call site is exercised; the AST walk
    catches it the moment it lands. `BenchReplayable` (a WorkflowSpanningEvent)
    constructed inside `emit_internal(...)` is a failure."""
    declared = declared_variants(EVENTS)
    sites = emit_sites(SEARCH_ROOTS)
    bad_internal = sites["emit_internal"] - set(declared["internal"])
    bad_spanning = sites["emit_spanning"] - set(declared["spanning"])
    assert not bad_internal, f"emit_internal constructs non-internal variants: {sorted(bad_internal)}"
    assert not bad_spanning, f"emit_spanning constructs non-spanning variants: {sorted(bad_spanning)}"
```

Plus `tests/fence/test_no_llm_spend.py`:

```python
from pathlib import Path
from typing import Iterator

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "tests" / "golden" / "remediation-reports"
PRODUCED = REPO / ".codegenie"


def _walk(node: object, pointer: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(node, dict):
        for k, v in node.items():
            child = f"{pointer}/{k}"
            yield child, k
            yield from _walk(v, child)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{pointer}/{i}")


def _yaml_files() -> Iterator[Path]:
    if GOLDEN.exists():
        yield from GOLDEN.rglob("*.yaml")
    if PRODUCED.exists():
        yield from PRODUCED.rglob("remediation-report.yaml")


def test_no_remediation_report_carries_llm_cost_usd() -> None:
    """Phase 3 is the deterministic-recipe path; no LLM is invoked. The
    absence of `llm_cost_usd` is the right signal — a zero-valued field still
    encodes 'this system tracks LLM cost', which Phase 3 must not pre-empt
    (Phase 4 adds the field additively when LLM fallback lands)."""
    failures: list[str] = []
    for path in _yaml_files():
        doc = yaml.safe_load(path.read_text()) or {}
        for pointer, key in _walk(doc):
            if key == "llm_cost_usd":
                failures.append(f"{path}: {pointer}")
    assert not failures, (
        "llm_cost_usd must not exist in any Phase 3 remediation-report.yaml:\n  "
        + "\n  ".join(failures)
    )
```

State why they fail: until the emit-site coverage of S6-04 + S6-01 + S5-02 lands, there will be declared variants without emit sites (and vice versa); the test names the specific gaps. **The story cannot reach green before its prerequisites (see header `Depends on:`) are GREEN** — `events.py` must exist for `declared_variants` to parse, and the orchestrator + plugin emit sites must exist for `emit_sites` to find them. The executor must pause and report if any prerequisite is missing rather than weakening the fence. The LLM-spend fence is structurally green from day one *if* the schema in S5-05 omits the field — the test exists to **lock** that absence in place.

### Green — minimal pass
- For each dead variant the taxonomy fence names, either (a) add the missing emit site to the relevant subgraph node or (b) remove the variant from the union with an ADR amendment.
- For each undeclared / mis-stream emit the fence names, either (a) add the variant class to the correct union or (b) fix the typo / move the emit to the correct stream at the call site.
- LLM-spend fence is green when no `RemediationReport` schema carries `llm_cost_usd` and no test fixture pre-populates one — both should already be true post-S5-05; the test makes the contract permanent.

### Refactor
- Lift `SEARCH_ROOTS` and the pure path-parameterised helpers (`declared_variants(events_path)`, `emit_sites(search_roots)`, and their private sub-helpers) into a `tests/fence/_helpers.py` module. Keeping them pure and path-injected is what lets the negative-regression sub-tests drive the *same* code against a `tmp_path` fake tree. S9-01 did **not** create `_helpers.py` (its files were `test_phase3_cross_plugin_isolation.py` + `test_phase3_cross_plugin_planted.py`); this story creates it.
- Add the negative regression sub-tests (synthetic fake source tree + synthetic YAML) using `tmp_path`. These pay rent the moment someone "improves" the AST walk and silently breaks coverage.
- Document at the top of each file the exact ADR + story this fence answers — future readers should see the *why* before the *how*.
- Edge cases from §Edge cases that touch this code: every emit site listed in §Edge cases (E2 `RequiresHumanReview`, E7 `NetworkPolicyViolation`, E8 postinstall canary, E12 `FilesystemRaceDetected`, E14 `GitHooksDisabledForRun`, E15 `StaleVulnIndex`, E17 `PluginRejected(integrity_mismatch)`, E18 `LowConfidenceAnswerUsed`) must surface as either an emit site or a declared literal — the fence is the ratchet that catches drift.

## Files to touch

| Path | Why |
|---|---|
| `tests/fence/test_event_taxonomy_complete.py` | NEW — taxonomy completeness fence (declared ↔ emitted). |
| `tests/fence/test_no_llm_spend.py` | NEW — absence-of-`llm_cost_usd` fence over goldens + produced reports. |
| `tests/fence/_helpers.py` | NEW — shared pure, path-parameterised AST helpers (`declared_variants`, `emit_sites`). Required: the negative-regression sub-tests must drive the *same* extraction code as the real fence. S9-01 did not create this file. |

## Out of scope

- **The event taxonomy itself** — owned by S6-01 (`EventLog` + the two discriminated unions).
- **Emit-site implementations** — owned by S6-04 (orchestrator), S5-02 (`NpmLockfileRecipeEngine`), S6-02 (`TrustScorer`), S7-01 / S7-03 (plugin subgraphs). This story does NOT add emit sites; it asserts the ones that should exist do exist.
- **`llm_cost_usd` field in Phase 4** — Phase 4 adds the field additively to its `LLMFallbackReport` (or extends `RemediationReport` per ADR amendment). When Phase 4 lands, this fence's `tests/fence/test_no_llm_spend.py` may need to scope its YAML search to "Phase 3 reports only" — pick whatever signal the Phase 4 ADR introduces (e.g., `report.kind == "deterministic"`).
- **Runtime closure fence (`test_no_llm_in_transforms.py`)** — owned by S1-05.
- **`make fence` / `make check` extension** — wired in S9-01.

## Notes for the implementer

- **Variable- and factory-constructed emits are the common case, not a yellow flag.** S6-01's `emit_internal` / `emit_spanning` take a **constructed event instance**; production call sites are `log.emit_internal(RecipeApplied(...))`, `event = self._build(...); log.emit_internal(event)`, or `log.emit_spanning(CacheGcCompleted.from_result(result, …))`. The fence resolves the variant class from the first positional argument: direct constructor `Call(func=Name)`, factory `Call(func=Attribute(value=Name, attr=…))`, or a one-hop `<name> = <Variant>(...)` assignment lookup inside the enclosing function. Only when none of those resolve does the fence fail — and then the call site (or its assignment) may carry a `# fence-allow: <ClassName>[, <ClassName>]` comment naming the possible variant(s). There is **no** `event_type=` keyword anywhere in the `EventLog` API — the original story prescribed one; it does not exist (see Validation notes #1).
- **Union resolution must follow the `TypeAlias`, not a `ClassDef`.** S6-01 ships `WorkflowInternalEvent` / `WorkflowSpanningEvent` as module-level `TypeAlias = Annotated[V1 | V2 | …, Field(discriminator="event_type")]` — there is no `class WorkflowInternalEvent`. Walk the `Annotated[…]` `BinOp` (`|`) tree for the member classes, then read each member class's own `event_type: Literal["…"]` default. A single-member `Literal["x"]` has an `ast.Constant` slice (not an `ast.Tuple`) — handle both. If a future refactor introduces an intermediate alias (`event_type: SomeAlias` where `SomeAlias = Literal[...]`), follow it one level; deeper than that and the union shape needs the ADR-0005 amendment.
- **Don't grep YAML text.** `"llm_cost_usd"` appearing in a YAML comment would false-positive a raw `grep`. Parse with `yaml.safe_load` and walk the dict; that's the only honest fence.
- **`PRODUCED = REPO / ".codegenie"` is workspace-local.** CI runs in a fresh checkout where `.codegenie/` is empty until tests produce artifacts; the fence then walks zero produced files plus the goldens. That's the intended steady state. Operators running locally with stale `.codegenie/` artifacts will see the fence catch any historical leak — make the message actionable ("run `make clean` and retry" if the file is from a prior workflow).
- **The taxonomy fence is the ratchet that makes ADR-0005 a contract instead of a hope.** Without it, the discriminated union and the call sites drift independently and Phase 9's migration becomes archaeology. Treat regressions to this fence as ADR-0005 amendments, not test fixes.
- **Match the established Phase 3 fence shape** — `tests/fence/test_phase3_cross_plugin_isolation.py` (S9-01) is the auto-discovering AST-walk precedent (directory glob + `ast.parse`); `tests/fence/test_phase3_importlinter_contracts_shape.py` is the meta-fence whose docstring discipline + top-of-file ADR cross-reference to mirror. The originally-named `test_phase3_importlinter_contracts.py` does not exist — S9-01 explicitly forbade forking it.
