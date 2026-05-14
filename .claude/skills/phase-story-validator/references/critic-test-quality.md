# Critic B — Test Quality

Stage 2B. The Test-Quality critic's question: **would the TDD plan's tests catch an obviously wrong implementation?** If a junior engineer wrote a deliberately lazy or wrong version of the code, would these tests fail?

This is the most important critic for a story headed to autonomous-agent execution. Weak tests are worse than no tests — they make the agent (and the human reviewer) think the code is verified when it isn't.

## What this critic reads

- The Context Brief (from Stage 1)
- The story's TDD plan section in full
- One adjacent test file from the codebase, if one exists in the directory the story will add tests to (`Glob`-find one, `Read` it). The point is to spot the *local test style* — if the rest of the project uses property-based tests, this story probably should too.
- The project's `pyproject.toml` test config — what frameworks / plugins are in use (`hypothesis`, `pytest-mock`, `pytest-xdist`, etc.)
- [`references/techniques.md`](techniques.md) — mutation thinking, property-based, metamorphic, specification-by-example, Rule 9
- [`references/story-smells.md`](story-smells.md) — test-shaped red flags

## The questions to answer

For each test in the TDD plan:

1. **Does it verify intent or just behavior?** (Rule 9)
   - **Intent:** the test asserts the AC's meaning — would still pass if the implementation were changed in any reasonable way
   - **Behavior:** the test asserts the current code's quirks — would fail if any reasonable refactor changed implementation details
   - Bad: `assert mock.method.call_args[1] == {"timeout": 30}` (asserts the method *was called* a certain way — testing the mock, not the system)
   - Good: `assert response.status == "ok" and response.took_ms < 1000` (asserts the observable behavior the AC promised)

2. **Mutation-test thought experiment:** if you mutated the production code in obvious ways, would the test still pass?
   - Replace the return value with `None` — does any test fail? If not, the tests don't check what's returned.
   - Replace all conditionals with `True` — does any test fail? If not, the tests don't exercise the branches.
   - Replace the function body with `pass` — does any test fail? If not, the tests don't run the code at all.
   - Delete the file — does any test even import-fail? If not, the tests test the wrong thing.

3. **Is the assertion strong enough to actually constrain the implementation?**
   - `assert result is not None` — almost never strong enough; True, 0, [], {} all pass
   - `assert isinstance(result, list)` — slightly stronger but doesn't check contents
   - `assert result == [Path("foo.ts"), Path("bar.js")]` — strong; constrains both type and value
   - `assert sorted(r.path for r in result) == ["bar.js", "foo.ts"]` — strong AND order-tolerant (often what you actually want)

4. **Is there a hidden invariant suitable for property-based testing?**
   - If the function transforms a value, what invariants hold for *any* input? (e.g., "decoding then encoding returns the original", "sorting is idempotent", "merging two repocontexts is commutative")
   - These are stronger than example-based tests because they generalize.

5. **Is there no oracle, but a metamorphic relation?**
   - For functions where the "right answer" is hard to compute independently (e.g., gather-pipeline outputs, ML predictions), use *relations between outputs*: "adding a file should never decrease detected_languages count", "running on a subset of the repo should produce a subset of the context"

6. **Are the tests deterministic?**
   - Anything depending on filesystem ordering, dict iteration order in older pythons, network conditions, system clock, random without seed?
   - Flaky tests are worse than no tests — they teach the next agent to ignore failures.

## Common thin-test patterns to flag

See [`references/story-smells.md`](story-smells.md) for the full catalog. The most common in this codebase will likely be:

- **Tautology**: `assert add(2, 3) == 2 + 3` — asserts the language works, not the function
- **Hard-coded matching hard-coded**: production code returns `"hello"`, test asserts `result == "hello"`; if you changed both to `"world"` it still passes — the test isn't grounded in *why* "hello" is right
- **Mock-of-mock**: function under test calls `dep.foo()`; test mocks `dep.foo` to return `42`, asserts that the function returned `42` — testing the mock
- **"Doesn't throw"**: `try: f(input); except: pytest.fail()` — asserts only that *some* code path executed, not that it did the right thing
- **Coverage-driven**: test exists to hit a line, not to verify intent — usually has a name like `test_function_works`

## Finding format

```markdown
## Test-Quality critic findings — {STORY-ID}

### F1 — Test 1 is tautological
- **Severity:** block
- **What's wrong:** TDD plan Test 1 reads "test_language_detection_finds_typescript: create a .ts file, assert that detected_languages contains 'typescript'". But the AC is just "detects TypeScript", which is what the test asserts. If the production code's TypeScript detection logic is wrong (e.g., only matches `.ts` files but misses `.tsx`), this test wouldn't catch it.
- **Proposed fix:** Tighten to: "given a directory with `app.ts`, `component.tsx`, and `script.mts`, assert detected_languages contains 'typescript' AND the evidence field cites all three file extensions"
- **Confidence:** high
- **Source:** mutation test: replace TypeScript detection with `return "typescript" if any(".ts" in f for f in files) else None` — would pass the current test but miss `.tsx`/`.mts`

### F2 — Missing property-based test for cache-key determinism
- **Severity:** harden
- **What's wrong:** AC-4 requires cache keys to be deterministic across runs. The current TDD plan tests this for a single fixture. But cache-key determinism is exactly the kind of invariant property-based testing was designed for — `hypothesis` should generate arbitrary file trees and assert that hashing the same tree twice yields the same key.
- **Proposed fix:** Add to TDD plan: "Test 5 (property-based, hypothesis): generate arbitrary nested dicts of file metadata; assert hash(metadata) == hash(metadata) and hash(metadata_a) != hash(metadata_b) when metadata_a != metadata_b"
- **Confidence:** high
- **Source:** project's `pyproject.toml` already lists hypothesis as a dev dep; one adjacent test uses it; this story should too
- **Citation:** hypothesis docs — "Stateful testing & strategies"

### F3 — Tests for AC-7 may not be feasible deterministically
- **Severity:** NEEDS RESEARCH
- **What's wrong:** AC-7 requires that "concurrent gather invocations produce identical output". This is a concurrency-correctness test — easy to write a flaky version, hard to write a deterministic version. Story's TDD plan doesn't address how.
- **Proposed fix:** unknown — could use pytest-asyncio with controlled scheduling, could use `threading` with explicit barriers, could be a hypothesis stateful test. Defers to researcher.
- **Confidence:** low
- **Source:** edge case identified by Coverage critic + this critic's concurrency-test scan
```

Severity tags match Coverage's: `block`, `harden`, `nit`, `NEEDS RESEARCH`.

## What this critic is NOT for

- Not for naming style or test organization (those are nits at best)
- Not for arguing about pytest vs unittest (the project has picked; respect Rule 11)
- Not for testing the framework — if the story tests "pytest itself works", flag it once and move on
- Not for over-engineering — if an AC is genuinely a one-line check, one example test is fine; don't insist on property-based for everything
