# Story S7-03 — Add the warm/cold-equivalence property test

**Step:** Step 7 — Close the exit criteria: latency, decision-log completeness, and adversarial gates
**Status:** Ready
**Effort:** M
**Depends on:** S5-04
**ADRs honored:** ADR-0003, ADR-0006

## Context
The hot-view cache is only *safe* if it changes latency and never the answer. ADR-0003 and ADR-0006 both pin this as a property-tested invariant: a hot-view-served read and a cold-storage read of the same gather must produce byte-identical planner context. This story adds the Hypothesis property test that proves it — closing Open Question 6 ("does the `ColdStoreReader` read the exact `RepoContext` artifact the renderer rendered from?") with an executable invariant. It is exit-criteria closeout / security-property work: without this test, a hot-view miss could silently change the planner's routing decision.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Testing strategy / Property tests` — "**Warm/cold equivalence** (Hypothesis) — for the same inputs, a hot-view-served read and a cold-storage read produce the *identical* planner context. The cache must never change the answer — only the latency."
  - `../phase-arch-design.md §Scenario 2` — the fail-closed-to-cold-storage path; "planner context is byte-identical to the no-tamper run."
  - `../phase-arch-design.md §C5 — HotViewRenderer` — `render_hot_views` is pure; the cold reader re-uses the *same* pure derivation so equivalence is structural.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-hot-view-integrity-by-gather-id-content-addressing.md` — ADR-0003 §Consequences — "A property test must hold: a hot-view-served read and a cold-storage read produce *byte-identical* planner context. The cache changes latency, never the answer."
  - `../ADRs/0006-cold-storage-fallback-reads-the-rendered-repocontext.md` — ADR-0006 §Consequences — "A warm/cold-equivalence Hypothesis property test is a Phase-8 deliverable — it is the test that proves the cache is safe." The cold adapter resolves the artifact by `gather_id`.
- **Source design:**
  - `../final-design.md §Open questions deferred to implementation` — Open Question 5/6: cold-storage read-path identity must be confirmed before this property test holds byte-for-byte.
- **Existing code (if any):**
  - `src/codegenie/hotviews/store.py` — `HotViewStore`, `ColdStoreReader` Protocol, the disk-`RepoContext` cold adapter (shipped S3-02 / S5-02).
  - `src/codegenie/hotviews/renderer.py` — pure `render_hot_views` and `write_hot_views` (shipped S5-03 / S5-04).
  - `tests/golden/hotviews/` — the golden `RepoContext` + rendered slices the renderer is tested against; reuse as a Hypothesis seed corpus.
  - Existing Hypothesis usage — `tests/unit/plugins/test_resolver_property.py` (the resolver totality property test) — mirror the `@given` / `@settings` style.

## Goal
Add a Hypothesis property test asserting that for any gathered `RepoContext`, a warm `HotViewStore.get_all` read and a cold-storage read produce byte-identical planner context.

## Acceptance criteria
- [ ] A Hypothesis property test (`@given(...)` over `RepoContext` fixtures / generated inputs) asserts that, for the same `(repo, gather_id)`, the four slices served warm from Redis equal the four slices served by the `ColdStoreReader` — compared by their canonical serialized bytes (e.g. `model_dump_json()` or `model_dump(mode="json")`).
- [ ] The comparison is byte-level (serialized form), not field-spot-check — a single differing nested value must fail the test.
- [ ] The warm read is forced through the binding-match path (valid `gather_id` + `slice_schema_version`) and the cold read is forced through the `ColdStoreReader` (e.g. flushed Redis or a deliberate miss) — the test exercises both code paths, not the same one twice.
- [ ] The cold reader is confirmed to resolve the artifact by the same `gather_id` the renderer rendered from (Open Question 6) — the test's setup wires that identity explicitly and a comment records the verification.
- [ ] The Hypothesis input strategy is deterministic enough to be CI-stable (a fixed `@seed` or a bounded, derandomized strategy) and `@settings` caps the example count so the suite stays fast.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Build a Hypothesis strategy that produces (or selects from) gathered `RepoContext` artifacts plus their `gather_id` — the golden `tests/golden/hotviews/` corpus is the seed; a small generated variation strategy widens coverage.
2. For each example: render the four slices via `render_hot_views`, write them to a real (or fake) Redis, then read once warm via `HotViewStore.get_all` and once cold via the `ColdStoreReader` adapter against the same on-disk `RepoContext`.
3. Serialize both result mappings canonically and assert equality.
4. Add a second variant that flushes Redis between render and read so `get_all`'s fail-closed path is the one producing the "warm" comparand — proving the fallback itself preserves equivalence.
5. Cap `@settings(max_examples=...)` and pin a `@seed` so the test is CI-stable.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/property/test_warm_cold_equivalence.py`

```python
@given(repo_context=gathered_repo_contexts())
@settings(max_examples=50, deadline=None)
def test_warm_and_cold_reads_are_byte_identical(repo_context: RepoContext) -> None:
    # WHY: ADR-0003/0006 — the hot-view cache must change latency, never the
    # answer. If a warm read and a cold read of the same gather ever diverge,
    # a Redis miss silently changes the planner's routing decision.
    gather_id = repo_context.gather_id
    slices = render_hot_views(repo, repo_context, active_tccms, gather_id)
    asyncio.run(write_hot_views(slices, store))

    warm = asyncio.run(store.get_all(repo))
    cold = asyncio.run(cold_reader.read_all(repo, gather_id))

    assert {k: v.model_dump_json() for k, v in warm.items()} == \
           {k: v.model_dump_json() for k, v in cold.items()}
```

### Green — make it pass
No new production code expected — S5-04 (renderer) and S5-02 (store + cold fallback) already single-source the derivation through pure `render_hot_views`, so warm and cold compute the same bytes. If the test fails, the cold adapter is reading a *different* artifact (Open Question 6 unresolved) — fix the adapter's `gather_id` resolution, do not weaken the assertion.

### Refactor — clean up
Module docstring naming ADR-0003/0006; type hints on the strategy and helpers; a comment recording the Open-Question-6 verification (which on-disk path the cold reader resolves and why it is the renderer's source artifact). Honor §Harness engineering — deterministic seed, bounded example count.

## Files to touch
| Path | Why |
|---|---|
| `tests/property/test_warm_cold_equivalence.py` | The Hypothesis warm/cold-equivalence property test (new file). |
| `tests/property/conftest.py` | The `gathered_repo_contexts` strategy / Redis + cold-reader fixtures, if not reusable. |

## Out of scope
- The Redis-tamper adversarial tests (wrong `gather_id`, attacker `risk_flags` bytes) — that is S7-04 (this story proves equivalence on *honest* inputs; S7-04 proves it survives tampering).
- The `invalidates`-monotone property test — that ships with S5-04.
- Any change to `render_hot_views` or the `ColdStoreReader` adapter — this story is a test only; a divergence is a bug to fix in the S5 code.

## Notes for the implementer
- The whole point is byte-identity. Compare serialized forms, not a handful of fields — a thin assertion (Rule 9) would pass even when a nested payload differs.
- Open Question 6 is the trap: if the `ColdStoreReader` reads a *newer* gather (a re-gather between render and read), the property genuinely fails and that is correct — the test must pin both reads to the *same* `gather_id`.
- Exercise the actual fail-closed path in at least one variant (flush Redis so `get_all` itself falls to cold) — otherwise the test only proves `render_hot_views` is deterministic, not that the store's fallback preserves equivalence.
- Pin a Hypothesis `@seed` and cap `max_examples` — an un-seeded property test that occasionally explores an expensive `RepoContext` is a CI flake source.
- `render_hot_views` is pure (functional core); both warm and cold should route through it — if you find a second "cold renderer," that is the ADR-0006 anti-pattern (two implementations to keep in sync) and a bug.

## ADRs honored
- **ADR-0003** — implements the §Consequences-mandated byte-identical warm/cold property test.
- **ADR-0006** — the cold reader resolves the artifact by `gather_id`; the test is the deliverable that proves the cache is safe.
