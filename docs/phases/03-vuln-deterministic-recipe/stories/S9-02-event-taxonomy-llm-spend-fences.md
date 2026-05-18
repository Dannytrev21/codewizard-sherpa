# Story S9-02 — Event-taxonomy completeness fence + `$0.00` LLM-spend assertion

**Step:** Step 9 — CI gates, import-linter contracts, performance baselines, bench backfill hook
**Status:** Ready
**Effort:** S
**Depends on:** S9-01
**ADRs honored:** ADR-0005 (two-stream event log — the discriminated unions `WorkflowInternalEvent` / `WorkflowSpanningEvent` are the source of truth this fence enforces; "crossing the taxonomy boundary requires an ADR amendment" is the rule the test makes mechanical), ADR-0011 (honest framing — silent dead enum values and undeclared emits are exactly the kind of decay this fence prevents)

## Context

ADR-0005 ships two Pydantic discriminated unions: `WorkflowInternalEvent.event_type ∈ {plugin_resolved, bundle_built, recipe_matched, recipe_applied, recipe_skipped, recipe_failed, install_stage_outcome, test_stage_outcome, local_branch_written, requires_human_review, adapter_degraded, stage_outcome, filesystem_race_detected, git_hooks_disabled_for_run}` and `WorkflowSpanningEvent.event_type ∈ {workflow_started, workflow_completed, cost_sandbox_run, capability_minted, capability_used, plugin_registry_corrupted, bench_replayable, stale_vuln_index}` (`phase-arch-design.md §Component design C9`).

Two failure modes the human eye misses:

1. **Dead enum values.** A literal lands in the union (because someone *planned* to emit it) but no production code path ever calls `emit_internal(...)` / `emit_spanning(...)` with that literal. The taxonomy lies about what the system actually does. Phase 9's Temporal/Postgres migration would lift a never-populated event type and propagate the lie.
2. **Undeclared emits.** A call site emits an event whose `event_type` literal is not in the union. Pydantic with `extra="forbid"` would reject this at runtime — but only if the call site is exercised by a test. A code path emitting a typo (`"recipe_appplied"`) that nothing tests slips past until production. The fence walks the AST for every `.emit_internal(...)` / `.emit_spanning(...)` call and cross-references the literal against the declared union.

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
  - `src/codegenie/plugins/events.py` (S6-01) — the union definitions; the fence reads literals from these classes.
  - `src/codegenie/transforms/orchestrator.py` (S6-04) — the primary emit site; the fence's AST walk reads from here + every plugin's subgraph.
  - `tests/golden/remediation-reports/*.yaml` (S8-02) — the golden corpus; the LLM-spend fence walks them.
  - `tests/fence/test_phase3_importlinter_contracts.py` (S9-01) — sibling fence; mirror its discovery + shape conventions.

## Goal

Ship two fence tests that mechanically close two failure modes Phase 3 cannot tolerate: taxonomy decay (dead enum values or undeclared emits) and LLM-spend leakage into the deterministic-recipe path. Both run under `make check` and fail loud with a specific diagnostic naming the offending file + literal.

## Acceptance criteria

- [ ] `tests/fence/test_event_taxonomy_complete.py` (NEW) parses `src/codegenie/plugins/events.py` and extracts the two `Literal[...]` sets for `WorkflowInternalEvent.event_type` and `WorkflowSpanningEvent.event_type`. AST-walks `src/codegenie/{plugins,transforms}/` and every `plugins/*/api.py` for `.emit_internal(...)` / `.emit_spanning(...)` calls; extracts the `event_type=` literal at each call site. Asserts: (a) every declared literal has ≥1 emit site somewhere in the searched packages (no dead enum), and (b) every emit-site literal is in the declared union for that stream (no undeclared emit, no mis-stream emit — `bench_replayable` emitted via `emit_internal` is a failure).
- [ ] `tests/fence/test_no_llm_spend.py` (NEW) walks: (a) `tests/golden/remediation-reports/*.yaml` and (b) any `**/remediation-report.yaml` produced during the test run under a configurable root (default: `.codegenie/`). For each YAML, recursively walks the parsed dict and asserts the key `"llm_cost_usd"` is **absent at every nesting depth**. Failure message names the file path and the JSON-pointer at which the key was found.
- [ ] The taxonomy fence has paired negative regression sub-tests (kept in the same file): one injects a synthetic emit-site literal not in the union (asserts the fence catches it) and one injects a synthetic declared literal with no emit site (asserts the fence catches it). The sub-tests use a `tmp_path`-scoped fake source tree so they do not pollute the real codebase.
- [ ] `tests/fence/test_no_llm_spend.py` has a negative regression: a `tmp_path` YAML with `outcome: {llm_cost_usd: 0}` makes the fence fail with the JSON-pointer `/outcome/llm_cost_usd`. A second negative case asserts deep-nesting detection (`a/b/c/llm_cost_usd`).
- [ ] Both fence tests run under `make check` (Phase 3 `tests/fence/` directory wired in S9-01) and fail loud with a diagnostic naming (a) the union member literal + stream for taxonomy failures, (b) the YAML file + JSON-pointer for LLM-spend failures.
- [ ] `mypy --strict` clean; `ruff check`, `ruff format --check` clean on touched files.
- [ ] TDD plan's red test exists, committed, green.

## Implementation outline

1. **Taxonomy fence — declared literals extraction.** Open `src/codegenie/plugins/events.py`, parse with `ast.parse`, walk for the two `ClassDef`s. For each, find the `event_type:` `AnnAssign` and extract the `Literal[...]` Tuple of `Constant` strings. Output: two `frozenset[str]`s (internal + spanning).
2. **Taxonomy fence — emit-site extraction.** Walk `src/codegenie/{plugins,transforms}/` and `plugins/*/api.py` (use `pathlib.Path.rglob("*.py")`). For each file, `ast.parse` and find `ast.Call` nodes where `func` is `Attribute(attr="emit_internal" | "emit_spanning")`. For each, locate the `keyword(arg="event_type")` and read its `Constant.value`. Skip calls where the literal is not a constant (raise a typed warning naming the location — variable-literal emits should be rare; if any exist in production code, they need a `# fence-ignore` rationale).
3. **Taxonomy fence — assertions.** Cross-reference: every declared literal has emit count ≥ 1; every emit literal is in the corresponding stream's union; `bench_replayable` emitted via `emit_spanning` (not `emit_internal`) and vice versa.
4. **LLM-spend fence — discovery.** Use `pathlib.Path.rglob` on both roots; load each YAML via `yaml.safe_load`; walk the result with a recursive helper that yields `(json_pointer, value)` tuples.
5. **LLM-spend fence — assertion.** For each YAML, assert no walked node has key `"llm_cost_usd"`. Failure message: `f"llm_cost_usd present in {path} at {json_pointer}: this field must not exist in Phase 3 (ADR-0005, see story S9-02)."`
6. **Negative regression scaffolding.** Both fence tests build a `tmp_path` synthetic case (fake module / fake YAML) and re-run the same logic to confirm the failure mode is detected. Keep the negatives inside the same file so the contract is co-located with its proof.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/fence/test_event_taxonomy_complete.py`

```python
import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EVENTS = REPO / "src" / "codegenie" / "plugins" / "events.py"
SEARCH_ROOTS = [
    REPO / "src" / "codegenie" / "plugins",
    REPO / "src" / "codegenie" / "transforms",
    REPO / "plugins",
]


def _extract_literal_set(class_name: str) -> frozenset[str]:
    tree = ast.parse(EVENTS.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for stmt in node.body:
                if (
                    isinstance(stmt, ast.AnnAssign)
                    and isinstance(stmt.target, ast.Name)
                    and stmt.target.id == "event_type"
                ):
                    # event_type: Literal["a", "b", ...]
                    literal_subscript = stmt.annotation
                    if isinstance(literal_subscript, ast.Subscript):
                        slice_node = literal_subscript.slice
                        if isinstance(slice_node, ast.Tuple):
                            return frozenset(
                                e.value for e in slice_node.elts
                                if isinstance(e, ast.Constant) and isinstance(e.value, str)
                            )
    raise AssertionError(f"event_type Literal not found on {class_name}")


def _extract_emit_sites() -> dict[str, set[str]]:
    """Return {"emit_internal": {literals...}, "emit_spanning": {literals...}}."""
    sites: dict[str, set[str]] = {"emit_internal": set(), "emit_spanning": set()}
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in sites
                ):
                    for kw in node.keywords:
                        if kw.arg == "event_type" and isinstance(kw.value, ast.Constant):
                            sites[node.func.attr].add(kw.value.value)
    return sites


def test_every_declared_literal_has_an_emit_site() -> None:
    """No dead enum values: every Literal in the union must be emitted somewhere
    in the searched packages. A dead literal lies about what the system does
    and would propagate the lie into Phase 9's Temporal/Postgres migration
    (ADR-0005)."""
    declared_internal = _extract_literal_set("WorkflowInternalEvent")
    declared_spanning = _extract_literal_set("WorkflowSpanningEvent")
    sites = _extract_emit_sites()
    dead_internal = declared_internal - sites["emit_internal"]
    dead_spanning = declared_spanning - sites["emit_spanning"]
    assert not dead_internal, f"Dead internal literals (no emit site): {sorted(dead_internal)}"
    assert not dead_spanning, f"Dead spanning literals (no emit site): {sorted(dead_spanning)}"


def test_every_emit_site_is_in_the_declared_union() -> None:
    """No undeclared emits and no mis-stream emits. A typo'd literal slips past
    Pydantic until the call site is exercised; the AST walk catches it the
    moment it lands."""
    declared_internal = _extract_literal_set("WorkflowInternalEvent")
    declared_spanning = _extract_literal_set("WorkflowSpanningEvent")
    sites = _extract_emit_sites()
    undeclared_internal = sites["emit_internal"] - declared_internal
    undeclared_spanning = sites["emit_spanning"] - declared_spanning
    assert not undeclared_internal, f"emit_internal literals not in union: {sorted(undeclared_internal)}"
    assert not undeclared_spanning, f"emit_spanning literals not in union: {sorted(undeclared_spanning)}"
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

State why they fail: until the emit-site coverage of S6-04 + S6-01 + S5-02 lands, there will be declared literals without emit sites (and vice versa); the test names the specific gaps. The LLM-spend fence is structurally green from day one *if* the schema in S5-05 omits the field — the test exists to **lock** that absence in place.

### Green — minimal pass
- For each dead literal the taxonomy fence names, either (a) add the missing emit site to the relevant subgraph node or (b) remove the literal from the union with an ADR amendment.
- For each undeclared emit the fence names, either (a) add the literal to the union or (b) fix the typo at the call site.
- LLM-spend fence is green when no `RemediationReport` schema carries `llm_cost_usd` and no test fixture pre-populates one — both should already be true post-S5-05; the test makes the contract permanent.

### Refactor
- Lift `SEARCH_ROOTS` and the AST helpers into a `tests/fence/_helpers.py` module shared with S9-01's `test_phase3_importlinter_contracts.py` (DRY without entangling the contracts).
- Add the negative regression sub-tests (synthetic fake source tree + synthetic YAML) using `tmp_path`. These pay rent the moment someone "improves" the AST walk and silently breaks coverage.
- Document at the top of each file the exact ADR + story this fence answers — future readers should see the *why* before the *how*.
- Edge cases from §Edge cases that touch this code: every emit site listed in §Edge cases (E2 `RequiresHumanReview`, E7 `NetworkPolicyViolation`, E8 postinstall canary, E12 `FilesystemRaceDetected`, E14 `GitHooksDisabledForRun`, E15 `StaleVulnIndex`, E17 `PluginRejected(integrity_mismatch)`, E18 `LowConfidenceAnswerUsed`) must surface as either an emit site or a declared literal — the fence is the ratchet that catches drift.

## Files to touch

| Path | Why |
|---|---|
| `tests/fence/test_event_taxonomy_complete.py` | NEW — taxonomy completeness fence (declared ↔ emitted). |
| `tests/fence/test_no_llm_spend.py` | NEW — absence-of-`llm_cost_usd` fence over goldens + produced reports. |
| `tests/fence/_helpers.py` | OPTIONAL — shared AST + path helpers (created if S9-01 didn't already need them). |

## Out of scope

- **The event taxonomy itself** — owned by S6-01 (`EventLog` + the two discriminated unions).
- **Emit-site implementations** — owned by S6-04 (orchestrator), S5-02 (`NpmLockfileRecipeEngine`), S6-02 (`TrustScorer`), S7-01 / S7-03 (plugin subgraphs). This story does NOT add emit sites; it asserts the ones that should exist do exist.
- **`llm_cost_usd` field in Phase 4** — Phase 4 adds the field additively to its `LLMFallbackReport` (or extends `RemediationReport` per ADR amendment). When Phase 4 lands, this fence's `tests/fence/test_no_llm_spend.py` may need to scope its YAML search to "Phase 3 reports only" — pick whatever signal the Phase 4 ADR introduces (e.g., `report.kind == "deterministic"`).
- **Runtime closure fence (`test_no_llm_in_transforms.py`)** — owned by S1-05.
- **`make fence` / `make check` extension** — wired in S9-01.

## Notes for the implementer

- **Variable-literal emits are a yellow flag, not red.** If a production call site does `.emit_internal(event_type=resolved_kind, ...)` where `resolved_kind` is a runtime variable, the AST walk cannot statically resolve it. In that case, emit a `pytest.warns(UserWarning)`-style diagnostic naming the file + line, *and* fail unless the call site carries a `# fence-allow: <literal>, <literal>` comment naming the possible literals. The fence stays mechanical; the human escape hatch is documented at the call site.
- **`event_type` literal-set extraction is fragile to reordering.** If S6-01 lands the unions as `Literal[a, b, c]` split across two lines, `ast.parse` still works — the literal-tuple AST shape is invariant. But if someone refactors to `event_type: SomeAlias` where `SomeAlias = Literal[...]` elsewhere in the file, the simple extraction needs to follow the alias. Keep the resolution loop one level deep; if it needs to be deeper, the union shape probably needs the ADR amendment ADR-0005 names.
- **Don't grep YAML text.** `"llm_cost_usd"` appearing in a YAML comment would false-positive a raw `grep`. Parse with `yaml.safe_load` and walk the dict; that's the only honest fence.
- **`PRODUCED = REPO / ".codegenie"` is workspace-local.** CI runs in a fresh checkout where `.codegenie/` is empty until tests produce artifacts; the fence then walks zero produced files plus the goldens. That's the intended steady state. Operators running locally with stale `.codegenie/` artifacts will see the fence catch any historical leak — make the message actionable ("run `make clean` and retry" if the file is from a prior workflow).
- **The taxonomy fence is the ratchet that makes ADR-0005 a contract instead of a hope.** Without it, the discriminated union and the call sites drift independently and Phase 9's migration becomes archaeology. Treat regressions to this fence as ADR-0005 amendments, not test fixes.
- **Match `tests/fence/test_phase3_importlinter_contracts.py`'s shape** — same docstring discipline, same `pyproject.toml`-style ADR cross-reference at the top of each test.
