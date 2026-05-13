# Story S1-05 — Ship Layer-0 introspection + schema-pin CI gates

**Step:** Step 1 — Scaffold `graph/` package, ship `VulnLedger` + HITL contracts + structural CI gates
**Status:** Ready
**Effort:** S
**Depends on:** S1-04
**ADRs honored:** ADR-0005, ADR-0012

## Context
This story closes Step 1 by landing the four Layer-0 static / introspection CI gates that protect every later Phase 6 commit from a class of silent regression: a `confidence` / `llm_says` / `self_reported` field sneaking into `VulnLedger`; a `schema_version` literal that drifts without a deliberate bump; a `graph/` import of `anthropic`; and a Python invocation under `-O` (which strips the `assert` statements `route_after_attempt` relies on). These tests are fast, structural, and run on every PR — they are the "lint-fast feedback" floor of the test pyramid.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Testing strategy — Test pyramid Layer 0` (lines 1156–1158) — Layer-0 budget is ~5 s; runs on every PR.
  - `../phase-arch-design.md §Testing strategy — CI gates` (lines 1196–1207) — enumerates all Layer-0 gates including schema validation against `tests/fixtures/checkpoints/v0.6.0/*.json`.
  - `../phase-arch-design.md §Agentic best practices — Confidence handling` (lines 1116) — `test_no_self_confidence_in_loopstate.py` introspects the model.
  - `../phase-arch-design.md §Component 4 — Failure behavior` (line 746) — `test_pep_no_O_optimizations.py` exists because `route_after_attempt` uses `assert`.
- **Phase ADRs:**
  - `../ADRs/0005-static-schema-version-literal-pin.md` — ADR-0005 — the schema-version literal is the contract; round-trip fixtures are the structural enforcer.
  - `../ADRs/0012-pure-edge-discipline-tests-over-acl-machinery.md` — ADR-0012 — tests verify *intent*, not appearance; introspection refuses confidence-shaped fields.
- **Source design:**
  - `../final-design.md §Goals row 11` (schema-version pin) and `§Goals row 19` (tests verify intent).

## Goal
Land four Layer-0 tests — `test_no_self_confidence_in_loopstate.py`, `test_schema_version_pin.py`, `test_fence_graph_no_anthropic.py` (a richer version of the smoke test S1-01 shipped), and `test_pep_no_O_optimizations.py` — so every PR after Step 1 is gated against confidence-field creep, schema drift, fence violations, and `python -O` execution.

## Acceptance criteria
- [ ] `tests/graph/test_no_self_confidence_in_loopstate.py` introspects `VulnLedger.model_fields` and fails if any field name contains the substring `confidence`, `llm_says`, or `self_reported` (case-insensitive); also fails if any field annotation is or contains `Any` / `dict[str, Any]` / `Mapping[str, Any]` (closes ADR-0005's "no Any" gate).
- [ ] `tests/graph/test_schema_version_pin.py` round-trips at least two committed fixtures under `tests/fixtures/checkpoints/v0.6.0/` (`minimal_ledger.json` from S1-02 plus one `populated_ledger.json` this story authors); both must `model_validate` and re-`model_dump_json` byte-identical (canonical-key sort).
- [ ] `tests/graph/test_schema_version_pin.py` includes a *negative* row: a fixture with `schema_version: "v0.5.99"` raises `ValidationError`.
- [ ] `tests/graph/test_fence_graph_no_anthropic.py` (extends the S1-01 smoke) covers all four fence rules added in S1-01 — anthropic/chromadb/sentence-transformers ban, `edges.py` no `random|time|os|datetime`, no sibling-node imports, no `langgraph.types.interrupt` outside `await_human.py`.
- [ ] `tests/graph/test_pep_no_O_optimizations.py` asserts `sys.flags.optimize == 0` and emits a clear message instructing the operator to run without `-O` / `PYTHONOPTIMIZE`.
- [ ] All four tests run in < 5 s combined (Layer 0 budget).
- [ ] The TDD plan's red tests exist, were committed, and are green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/graph/ -k "no_self_confidence or schema_version_pin or fence_graph or no_O"` all pass.

## Implementation outline
1. Author `tests/fixtures/checkpoints/v0.6.0/populated_ledger.json` — a hand-built fixture with `recipe_selection`, `patch`, `prior_attempts=[one Attempt]`, `last_outcome`, `human_request`, `events=[one GraphEvent]`. This is the maximalist round-trip fixture.
2. Write `test_no_self_confidence_in_loopstate.py` — uses `VulnLedger.model_fields` (Pydantic v2) to walk field names and annotations; uses `typing.get_type_hints` and `typing.get_args` to peel `Optional[...]` / `Union[...]` wrappers when checking for `Any`.
3. Write `test_schema_version_pin.py` — parametrized over fixtures in `tests/fixtures/checkpoints/v0.6.0/`; uses the `_canonical` helper from S1-02 for byte-identical comparison; one parametric row for the negative `v0.5.99` case.
4. Write `test_fence_graph_no_anthropic.py` — extends S1-01's smoke with parametric rows for each of the four fence rules. Each row synthesizes a violating file under `tmp_path` and asserts `FenceViolation` from the existing fence runner.
5. Write `test_pep_no_O_optimizations.py` — single assertion on `sys.flags.optimize`; on failure print: `"Tests must run without -O or PYTHONOPTIMIZE because route_after_attempt uses assert (ADR-0012). See tools/policy/graph-thresholds.yaml."`.
6. Confirm all four tests run quickly enough that Layer 0 stays within its ~5 s budget.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/graph/test_no_self_confidence_in_loopstate.py`

```python
def test_vuln_ledger_has_no_confidence_shaped_field() -> None:
    # arrange: import the real VulnLedger
    forbidden_substrings = ("confidence", "llm_says", "self_reported")
    # act + assert: walk model_fields, fail loud on any match
    for field_name in VulnLedger.model_fields:
        lower = field_name.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lower, (
                f"VulnLedger field '{field_name}' contains '{forbidden}'. "
                f"Phase 6 routing reads objective signals only (ADR-0012). "
                f"Move this field to a dedicated planner component."
            )


def test_vuln_ledger_field_annotations_contain_no_any() -> None:
    # arrange: peel Optional/Union wrappers and check leaves
    # act + assert: no annotation contains typing.Any or dict[str, Any]
    hints = get_type_hints(VulnLedger)
    for name, annotation in hints.items():
        leaves = _peel_annotation(annotation)
        for leaf in leaves:
            assert leaf is not Any, f"VulnLedger.{name} is typed Any — see ADR-0005"
```

Test file path: `tests/graph/test_schema_version_pin.py`

```python
FIXTURES = sorted((REPO_ROOT / "tests/fixtures/checkpoints/v0.6.0").glob("*.json"))

@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.name)
def test_vuln_ledger_fixture_round_trips_byte_identical(fixture: Path) -> None:
    # arrange
    raw = fixture.read_text()
    # act
    ledger = VulnLedger.model_validate_json(raw)
    re_emitted = ledger.model_dump_json(by_alias=True, exclude_none=False)
    # assert: canonical-key sort then compare
    assert _canonical(json.loads(re_emitted)) == _canonical(json.loads(raw))


def test_schema_version_mismatch_rejected() -> None:
    # arrange: load a real fixture and rewrite schema_version
    payload = json.loads((REPO_ROOT / "tests/fixtures/checkpoints/v0.6.0/minimal_ledger.json").read_text())
    payload["schema_version"] = "v0.5.99"
    # act + assert
    with pytest.raises(ValidationError):
        VulnLedger.model_validate(payload)
```

Test file path: `tests/graph/test_fence_graph_no_anthropic.py` (replaces the S1-01 smoke)

```python
@pytest.mark.parametrize("rule_id,offender_path,offender_body", [
    ("graph_no_anthropic", "codegenie/graph/x.py", "import anthropic\n"),
    ("graph_no_chromadb", "codegenie/graph/x.py", "import chromadb\n"),
    ("graph_no_sentence_transformers", "codegenie/graph/x.py", "import sentence_transformers\n"),
    ("graph_edges_no_time", "codegenie/graph/edges.py", "import time\n"),
    ("graph_edges_no_os", "codegenie/graph/edges.py", "import os\n"),
    ("graph_edges_no_random", "codegenie/graph/edges.py", "import random\n"),
    ("graph_edges_no_datetime_module", "codegenie/graph/edges.py", "import datetime\n"),
    ("graph_nodes_no_sibling_import", "codegenie/graph/nodes/foo.py",
     "from codegenie.graph.nodes import bar\n"),
    ("graph_only_await_human_imports_interrupt", "codegenie/graph/nodes/bogus.py",
     "from langgraph.types import interrupt\n"),
])
def test_fence_rule_rejects_violation(tmp_path: Path, rule_id: str,
                                      offender_path: str, offender_body: str) -> None:
    # arrange: synthesize the violating file under tmp_path
    target = tmp_path / offender_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(offender_body)
    # act + assert
    with pytest.raises(FenceViolation) as exc:
        run_fence(rule_set="phase6_graph", roots=[tmp_path])
    assert rule_id in str(exc.value) or offender_path in str(exc.value)


def test_edges_datetime_fromisoformat_is_whitelisted(tmp_path: Path) -> None:
    # arrange: the whitelist case — `from datetime import fromisoformat` is legal
    target = tmp_path / "codegenie/graph/edges.py"
    target.parent.mkdir(parents=True)
    target.write_text("from datetime import fromisoformat\n")
    # act + assert: no FenceViolation raised
    run_fence(rule_set="phase6_graph", roots=[tmp_path])  # silent pass
```

Test file path: `tests/graph/test_pep_no_O_optimizations.py`

```python
def test_python_optimize_flag_is_zero() -> None:
    # arrange + act + assert: catches both -O and PYTHONOPTIMIZE
    assert sys.flags.optimize == 0, (
        "Phase 6 tests must run without -O / PYTHONOPTIMIZE because "
        "route_after_attempt uses `assert state.last_outcome is not None` "
        "(ADR-0012). Re-run with plain `pytest`."
    )
```

### Green — make it pass
Author the four test files plus the second fixture (`populated_ledger.json`). All four tests should be passing immediately because S1-02 already shipped a `VulnLedger` that conforms; this story exists to *pin* the conformance so a future PR cannot regress it.

### Refactor — clean up
- Extract `_peel_annotation(annotation)` and `_canonical(obj)` helpers into `tests/graph/_introspection.py` so S1-02's round-trip test and this story's tests share one canonicalization path.
- Move the fixture-glob pattern into `tests/conftest.py` or a module-level `FIXTURES` constant for parametrize-id readability.
- Add a one-line docstring to each test file referencing the ADR it implements.

## Files to touch
| Path | Why |
|---|---|
| `tests/graph/test_no_self_confidence_in_loopstate.py` | Introspect `VulnLedger.model_fields` — no confidence-shaped field, no `Any`. |
| `tests/graph/test_schema_version_pin.py` | Round-trip every `tests/fixtures/checkpoints/v0.6.0/*.json` + negative schema-version case. |
| `tests/graph/test_fence_graph_no_anthropic.py` | Parametric coverage of all four fence rules from S1-01 + whitelist case. |
| `tests/graph/test_pep_no_O_optimizations.py` | One-line `sys.flags.optimize == 0` assertion. |
| `tests/fixtures/checkpoints/v0.6.0/populated_ledger.json` | Maximalist round-trip fixture (all optional fields populated). |
| `tests/graph/_introspection.py` (new) | Shared `_canonical` + `_peel_annotation` helpers. |

## Out of scope
- **Topology golden** (`tests/golden/vuln_loop_topology.json`) — Layer-0 gate but owned by S5-02.
- **`test_audited_node_decorator_applied.py`** — verifies every `graph/nodes/*.py` uses `@audited_node`; owned by S4-01 once the decorator and nodes exist.
- **`test_only_await_human_imports_interrupt.py` static lint** — this story covers it via the fence rule; a Python-AST version of the same check (referenced in ADR-0008) is owned by S4-08.
- **HITL contract export gate** (`docs/contracts/hitl-v0.6.0.json` diff) — owned by S7-05.
- **`test_pydantic_no_any.py`** — folded into `test_no_self_confidence_in_loopstate.py` here for budget; if it grows to need its own file, that's a follow-up story, not a scope-creep into this one.

## Notes for the implementer
- **`get_type_hints` resolves forward references.** After S1-04 lands `events.py` and `__init__.py` calls `VulnLedger.model_rebuild()`, `typing.get_type_hints(VulnLedger)` returns concrete types. If forward refs are unresolved at test time, surface the error loudly — that's a real bug, not a test workaround.
- **Pydantic v2 `model_fields` vs v1 `__fields__`.** Use v2. If the project pins v1, surface in dep file rather than supporting both.
- **`_peel_annotation` must handle `Optional[X]`, `Union[X, None]`, `list[X]`, `dict[K, V]`** recursively. The leaves you check are everything that isn't a `Union` / generic wrapper.
- **The fence runner's `rule_set` argument** is whatever S1-01 chose for the YAML group name (`phase6_graph` was the suggestion). Match exactly — if S1-01 used a different name, update both files.
- **`populated_ledger.json` is hand-authored — keep it small.** Two `prior_attempts`, one `events` entry, one `human_request`, no `human_decision`. Goal: exercise every optional-field code path *exactly once*. Avoid huge text blobs in `summary` fields; the fixture should be < 4 KB.
- **CLAUDE.md Rule 9 (Tests verify intent, not just behavior).** `test_no_self_confidence_in_loopstate.py` would be worthless if it just checked one specific field name. The substring-scan over **all** field names is the form that catches a sneaky `routing_confidence`, `model_self_reported_pass`, etc.
- **CLAUDE.md Rule 12 (Fail loud).** Every assertion above carries a remediation message in its failure string. Do not weaken this; a passing-but-noisy test is worse than a failing-but-clear one.
- **Layer-0 time budget is ~5 s.** Round-trip tests over two small fixtures + fence rule parametrization (~10 rows) + introspection over ~18 fields = well under a second. Do not add slow operations here.
