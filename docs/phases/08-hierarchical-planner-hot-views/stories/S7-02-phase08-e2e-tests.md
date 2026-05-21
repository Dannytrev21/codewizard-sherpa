# Story S7-02 — Add the phase08_e2e latency and routing tests

**Step:** Step 7 — Close the exit criteria: latency, decision-log completeness, and adversarial gates
**Status:** Ready
**Effort:** M
**Depends on:** S6-04
**ADRs honored:** ADR-0005, ADR-0007, ADR-0008

## Context
This story closes both Phase 8 exit criteria with the two end-to-end tests the architecture names as the gates. The routing e2e drives a fixture vuln-remediation workflow through the full `Supervisor → Planner` path and asserts a `RouteDecided` event is in the workflow-internal stream — exit criterion 1, "the chosen path is logged on every workflow." The latency e2e runs 200 sequential `get_all` calls after a real render against a `redis:7-alpine` and asserts measured `p95 < 50 ms` — exit criterion 2. Unlike the S7-01 bench (advisory), these `@pytest.mark.phase08_e2e` tests are the merge gate.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Testing strategy / Test pyramid` — "**e2e** (`@pytest.mark.phase08_e2e`, two tests) — a fixture vuln-remediation workflow through the full Supervisor → Planner path, asserting the `RouteDecided` event is in the log; a hot-view latency e2e running 200 sequential `get_all` calls after a real render, asserting `p95 < 50 ms` (measured, not asserted-by-faith)."
  - `../phase-arch-design.md §Scenario 1` — the happy-path warm vuln-remediation recipe route; the exact sequence the routing e2e exercises.
  - `../phase-arch-design.md §Control flow` — the `resolve → build_bundle → route → decide → dispatch` ordering; `route` emits `RouteDecided` via `emit_internal` before returning.
  - `../phase-arch-design.md §Fixture portfolio` — "A Node/npm repo with a recipe-eligible CVE (recipe route)" — the fixture this e2e uses.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0005-50ms-p95-exit-criterion-scoped-to-hot-view-read.md` — ADR-0005 — the latency e2e measures `get_all` + deserialization only; "200 sequential `get_all` calls after a real render against a `redis:7-alpine`, asserting `p95 < 50 ms`."
  - `../ADRs/0007-routing-events-into-existing-event-log.md` — ADR-0007 — `RouteDecided` rides the existing `EventLog`; the e2e asserts it via `EventLog.replay`, not a new store.
  - `../ADRs/0008-route-events-in-the-workflow-internal-stream.md` — ADR-0008 — `RouteDecided` is a `WorkflowInternalEvent`; the e2e reads the *internal* stream, not the spanning stream.
- **Existing code (if any):**
  - `pyproject.toml §[tool.pytest.ini_options] markers` — `phase08_e2e` is **not** yet registered; this story (or S1) must add it. `--strict-markers` is on, so an unregistered marker is a hard error.
  - `tests/integration/test_event_replay.py` — the `EventLog` + `InMemorySink` replay pattern to mirror.
  - `src/codegenie/supervisor/graph.py` — `run_supervisor` (shipped S6-02/S6-03/S6-04).
  - `src/codegenie/plugins/events.py` — `EventLog.emit_internal` / `EventLog.replay`; the `WorkflowInternalEvent` union.

## Goal
Add two `@pytest.mark.phase08_e2e` tests — one proving `RouteDecided` is logged on every workflow, one proving measured `get_all` `p95 < 50 ms` — so both Phase 8 exit criteria have a CI-gating end-to-end test.

## Acceptance criteria
- [ ] `phase08_e2e` is a registered pytest marker in `pyproject.toml` (added to the `markers` list — `--strict-markers` requires it).
- [ ] A `@pytest.mark.phase08_e2e` routing test runs a fixture Node/npm vuln-remediation workflow through `run_supervisor` and asserts, via `EventLog.replay` over the **workflow-internal** stream, that exactly one `RouteDecided` event for that `workflow_id` is present.
- [ ] The routing test asserts the `RouteDecided` event's `route` matches the `RouteDecision.route` the Supervisor returned (the logged path equals the chosen path).
- [ ] A `@pytest.mark.phase08_e2e` latency test renders four valid slices to a real `redis:7-alpine`, runs 200 sequential `HotViewStore.get_all` calls, and asserts the p95 of the timing distribution is `< 50 ms`.
- [ ] The latency test fails (does not skip) if `p95 >= 50 ms` — it is the merge gate for exit criterion 2; it skips only if Docker / Redis is unavailable.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Register the `phase08_e2e` marker in `pyproject.toml §markers` with a one-line description.
2. Create `tests/e2e/test_phase08_e2e.py` (or the repo's existing e2e directory) with the two tests.
3. Routing test: build a `SupervisorState` for the recipe-eligible Node/npm fixture, an `InMemorySink`-backed `EventLog`, run `run_supervisor`, then `EventLog.replay` and filter `WorkflowInternalEvent`s for `RouteDecided` with the matching `workflow_id`; assert exactly one and that its `route` field equals the decision's route.
4. Latency test: render + write four valid binding-matching slices, then 200× `get_all` collecting `perf_counter` samples; compute p95; assert `< 0.050`.
5. Confirm the e2e suite runs in CI under a `-m phase08_e2e` selector (or is included in the default suite once the marker exists — match how `phase02_adv` is wired).

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/e2e/test_phase08_e2e.py`

```python
@pytest.mark.phase08_e2e
async def test_route_decided_logged_on_every_workflow(vuln_node_fixture, redis_container) -> None:
    # WHY: exit criterion 1 — "the chosen path is logged on every workflow."
    # Drives the full Supervisor->Planner path and proves a RouteDecided event
    # lands in the workflow-internal stream with the same route the Supervisor chose.
    sink = InMemorySink()
    event_log = EventLog(internal_sink=sink, ...)
    decision = await run_supervisor(graph, supervisor_state)
    internal = [e for e in event_log.replay(workflow_id) if isinstance(e, RouteDecided)]
    assert len(internal) == 1
    assert internal[0].route == decision.route  # logged path == chosen path


@pytest.mark.phase08_e2e
def test_hot_view_get_all_p95_under_50ms(redis_container, rendered_repo) -> None:
    # WHY: exit criterion 2 — measured, not asserted-by-faith. ADR-0005 pins
    # the scope to get_all + deserialization. This e2e is the merge gate.
    store = HotViewStore(redis=redis_container.client, ...)
    samples = sorted(
        _time_get_all(store, rendered_repo.repo_id) for _ in range(200)
    )
    p95 = samples[int(len(samples) * 0.95)]
    assert p95 < 0.050
```

### Green — make it pass
No new production code — S6-04 and S5-02 already ship the full path. "Green" is both e2e tests passing against a live `redis:7-alpine`. A failing routing test means a routing edge skipped the append (S6-05 should already catch that statically); a failing latency test is a real regression per ADR-0005.

### Refactor — clean up
Module docstring naming the two exit criteria; type hints on the fixtures; extract a `_time_get_all` helper. Honor §Harness engineering — assert on the internal stream only (ADR-0008), use `EventLog.replay` not a private field.

## Files to touch
| Path | Why |
|---|---|
| `tests/e2e/test_phase08_e2e.py` | The two `@pytest.mark.phase08_e2e` exit-criteria tests (new file). |
| `pyproject.toml` | Register the `phase08_e2e` marker in `[tool.pytest.ini_options].markers`. |
| `tests/e2e/conftest.py` | Fixtures (recipe-eligible Node/npm workflow, Redis container) if not reusable. |

## Out of scope
- The advisory `@pytest.mark.bench` canary — that is S7-01.
- The decision-log *completeness* adversarial test (N workflows → N events) — that is S7-05.
- The Redis-tamper adversarial tests — S7-04.
- The warm/cold-equivalence property test — S7-03.

## Notes for the implementer
- ADR-0008 is load-bearing here: `RouteDecided` is a `WorkflowInternalEvent`. Read the **internal** stream via `EventLog.replay`; reading the spanning stream would find nothing and the test would be a false negative.
- Assert the *logged route equals the chosen route* — a test that only checks "a `RouteDecided` exists" would pass even if the event recorded the wrong path. The test must verify intent, not just presence (Rule 9).
- The latency e2e must **fail**, not skip, on `p95 >= 50 ms` — it is the gate. Skip only when the container itself is unavailable.
- Co-locate the `redis:7-alpine` container with the test process (local socket); the ~25× headroom assumes that topology (High-level-impl §Risk 3).
- `--strict-markers` is on — the `phase08_e2e` marker must be registered before the test file is collected or the whole suite errors.

## ADRs honored
- **ADR-0005** — the latency e2e measures the `get_all` + deserialization scope only.
- **ADR-0007** — the routing e2e asserts against the existing `EventLog`, not a new store.
- **ADR-0008** — the routing e2e reads the workflow-internal stream where `RouteDecided` rides.
