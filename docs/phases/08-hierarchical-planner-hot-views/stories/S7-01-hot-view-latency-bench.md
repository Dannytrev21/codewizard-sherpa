# Story S7-01 — Add the hot-view latency bench canary

**Step:** Step 7 — Close the exit criteria: latency, decision-log completeness, and adversarial gates
**Status:** Ready
**Effort:** S
**Depends on:** S5-02
**ADRs honored:** ADR-0005, ADR-0003

## Context
Phase 8 exit criterion 2 — "hot views serve agent context in `<50 ms p95`" — needs a *measured* guard, not an assertion of faith. This story adds the `@pytest.mark.bench` canary that ADR-0005 names the named performance-regression canary: it times `HotViewStore.get_all` against a real `redis:7-alpine` and asserts `p95 < 50 ms`. It is exit-criteria closeout work — the bench is advisory (it never gates merge) but a `> 20 %` regression surfaces a CI annotation, making a latency regression a loud, dated signal rather than a silent drift.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Testing strategy / Performance regression tests` — "`@pytest.mark.bench` (advisory, CI-tracked) — `HotViewStore.get_all` against a real local Redis asserting `p95 < 50 ms`; **this is the canary** for exit criterion 2. A second bench asserts warm-path Supervisor overhead `p95 < 5 ms`."
  - `../phase-arch-design.md §G2` — "`HotViewStore.get_all(repo)` serves the four ADR-0013 slices in one pipelined Redis round-trip + Pydantic deserialization … Scope is pinned to the read + deserialization (08-ADR-0004)."
  - `../phase-arch-design.md §C4 — HotViewStore` — performance envelope: `get_all` (4 keys, one pipeline) ≈ 1–2 ms; `< 50 ms p95` met with ~25× headroom on the dev substrate.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0005-50ms-p95-exit-criterion-scoped-to-hot-view-read.md` — ADR-0005 — the `< 50 ms p95` is pinned to `get_all` + Pydantic deserialization *only*; explicitly excludes resolution, Bundle building, routing. The bench measures exactly that scope.
  - `../ADRs/0003-hot-view-integrity-by-gather-id-content-addressing.md` — ADR-0003 — `get_all` verifies the `(repo, slice, gather_id, slice_schema_version)` binding on every read; the bench must time the warm path (matching binding, no fallback).
- **Existing code (if any):**
  - `pyproject.toml §[tool.pytest.ini_options]` — the `markers` list already registers `bench`; the default `addopts` excludes `-m bench`. No new marker needed.
  - `src/codegenie/hotviews/store.py` — `HotViewStore` (shipped by S5-01/S5-02); `get_all(repo) -> Mapping[HotViewSliceName, HotViewSlice]`.
  - `tests/integration/conftest.py` — existing integration fixtures; check for an existing `redis` container fixture pattern before writing a new one.

## Goal
Add a `@pytest.mark.bench` test that measures `HotViewStore.get_all` p95 against a real `redis:7-alpine` and fails if `p95 >= 50 ms`, plus a second bench asserting warm-path Supervisor overhead `p95 < 5 ms`.

## Acceptance criteria
- [ ] A `@pytest.mark.bench` test times `HotViewStore.get_all` over a real `redis:7-alpine` (pre-loaded with four valid, binding-matching slices) and asserts the p95 of the timing distribution is `< 50 ms`.
- [ ] A second `@pytest.mark.bench` test asserts warm-path Supervisor overhead (the `resolve → build_bundle → route` graph minus the hot-view read itself) has `p95 < 5 ms`.
- [ ] Both benches are excluded from the default `pytest` run (they carry `@pytest.mark.bench`, which the default `addopts` excludes) and run only under `pytest -m bench`.
- [ ] The latency bench measures only the ADR-0005-pinned scope — `get_all` + Pydantic deserialization — with no plugin resolution, Bundle building, or routing folded into the timed region.
- [ ] The bench skips cleanly (`pytest.skip`) when Docker / `redis:7-alpine` is unavailable, rather than failing.
- [ ] The TDD plan's red test exists, was committed, and is green (green = bench passes under `pytest -m bench` with a live Redis).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Locate or add a session-scoped `redis:7-alpine` container fixture (reuse the S5/S6 integration Redis fixture if one exists; otherwise add one under `tests/bench/conftest.py` that skips when Docker is absent).
2. Write `tests/bench/test_hot_view_latency.py` with the two `@pytest.mark.bench` tests.
3. The latency bench: render + write four valid slices once, then call `get_all` N≥200 times collecting per-call wall-clock samples (`time.perf_counter`); compute p95 from the sorted samples; assert `p95 < 0.050` seconds.
4. The Supervisor-overhead bench: run the full `run_supervisor` path N times, subtract the measured `get_all` cost, and assert the remaining `p95 < 0.005` seconds.
5. Discard a small warm-up prefix of samples (JIT / connection-pool warm-up) before computing p95 so the number reflects steady state.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/bench/test_hot_view_latency.py`

```python
@pytest.mark.bench
def test_get_all_p95_under_50ms(redis_container, rendered_repo) -> None:
    # WHY: exit criterion 2 — hot views serve agent context in <50ms p95.
    # ADR-0005 pins the scope to get_all + deserialization only. This bench
    # is the named regression canary; a >20% drift surfaces a CI annotation.
    store = HotViewStore(redis=redis_container.client, ...)
    samples: list[float] = []
    for _ in range(200):
        t0 = time.perf_counter()
        asyncio.run(store.get_all(rendered_repo.repo_id))
        samples.append(time.perf_counter() - t0)
    samples = sorted(samples[20:])  # drop warm-up
    p95 = samples[int(len(samples) * 0.95)]
    assert p95 < 0.050, f"hot-view get_all p95 {p95*1000:.1f}ms exceeds 50ms SLO"
```

A second test, `test_supervisor_overhead_p95_under_5ms`, asserts the warm-path Supervisor overhead (graph minus the `get_all` read) has `p95 < 0.005`.

### Green — make it pass
No production code changes — the bench passes because S5-01/S5-02 already met the SLO with ~25× headroom. "Green" is the bench passing under `pytest -m bench` against a live `redis:7-alpine`. If it fails, that is a real regression to investigate per ADR-0005 §Consequences — never widen the threshold.

### Refactor — clean up
Type hints on the fixture and the test helpers; a module docstring stating the ADR-0005 scope pin; pull the percentile computation into a small `_p95(samples)` helper if both benches use it. Honor §Harness engineering — no I/O outside the timed region beyond the warm-up loop.

## Files to touch
| Path | Why |
|---|---|
| `tests/bench/test_hot_view_latency.py` | The two `@pytest.mark.bench` canaries (new file). |
| `tests/bench/conftest.py` | A `redis:7-alpine` container fixture if none is reusable (new or extended). |

## Out of scope
- The `phase08_e2e` latency e2e test (200-call measured run) — that is S7-02.
- The warm/cold-equivalence property test — S7-03.
- Any production-code latency optimization — the SLO is already met; this story only measures.

## Notes for the implementer
- The bench is **advisory** — it must never gate merge (the `bench` marker is excluded from the default `addopts`). The `phase08_e2e` test (S7-02) is the gate; this is the canary.
- ADR-0005 is strict: time **only** `get_all` + deserialization. Folding Bundle building into the timed region (which is ADR-0030-graph-query-dominated, unbounded) would make the number meaningless.
- Run the container over a local socket — the design's ~25× headroom is a dev-substrate number; a true regression is large and obvious. If the bench is flaky in CI, investigate the regression, do not relax the threshold (ADR-0005 §Consequences / High-level-impl §Risk 3).
- Drop a warm-up prefix before computing p95 — the first few calls pay connection-pool setup that is not steady-state latency.

## ADRs honored
- **ADR-0005** — the bench measures exactly the `get_all` + deserialization scope, nothing upstream.
- **ADR-0003** — the timed path is the warm path (binding matches, no cold fallback); the slices are pre-loaded valid.
