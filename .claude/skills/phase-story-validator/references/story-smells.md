# Story smells — catalog of red flags

A reference catalog of patterns that should make the critics suspicious. Not every smell is a defect — context matters — but each one warrants a look. Critics should refer to this catalog by name when filing findings ("AC-3 is a Tautology smell").

## AC-shaped smells

### Tautology
**Symptom:** AC asserts something that is true by construction or by the language. Always passes.

**Examples:**
- "The function returns a value when called with valid input" (returning *something* is trivial)
- "The list contains items after appending"
- "The path exists after creating it"

**Fix:** Tighten to assert *what* value, *what* item, *what* properties.

---

### Vague qualitative
**Symptom:** AC uses subjective or undefined adjectives. No third party can pass/fail it without further interpretation.

**Examples:**
- "Handles errors gracefully"
- "Performs well"
- "Is well-tested"
- "Follows best practices"
- "Has good test coverage"

**Fix:** Replace with the observable contract. "Handles errors gracefully" → "When the input file is unreadable, exits code 2 and prints `error: cannot read {path}: {os error}` to stderr".

---

### Implementation-leaking
**Symptom:** AC names a specific implementation rather than the observable behavior. Over-constrains the implementation; useless if the impl changes.

**Examples:**
- "Uses a binary search algorithm" (no observable difference for a caller)
- "Caches results in a dict"
- "Calls the foo() helper"

**Fix:** Restate in terms the caller can observe. "Uses binary search" → "Lookup time is O(log n) for any input size; verified by timing test that asserts ratio".

---

### Negative-space gap
**Symptom:** ACs only specify the happy path. No ACs describe what the system *refuses* to do, or what it *errors* on.

**Examples:**
- All ACs assume valid input — none describe invalid-input behavior
- All ACs describe writes — none describe what's *not* written

**Fix:** Add negative-space ACs. For every "X happens when Y", consider "X does NOT happen when ¬Y" or "Z happens when input is invalid".

---

### Orphan AC
**Symptom:** AC doesn't trace to the goal, an exit criterion, an ADR, or a CLAUDE.md commitment. No upstream source.

**Fix:** Either remove the AC, or amend the goal/story scope to explain why it's there. Don't act on orphan ACs.

---

### "Some" / "any" without quantifier
**Symptom:** AC says "some result" or "any valid output" without bounding the set.

**Examples:**
- "Returns some integer when called" (any int? including negative? including overflow?)
- "Outputs any valid YAML"

**Fix:** Bound the set. "Returns a non-negative integer ≤ 2^31".

---

## Test-shaped smells

### Tautological test
**Symptom:** Test asserts something that follows from the test's own setup rather than from the code's behavior.

**Example:**
```python
def test_add():
    assert add(2, 3) == 2 + 3  # passes if Python's + works
```

**Fix:** Compute the expected value independently, ideally by hand. `assert add(2, 3) == 5`.

---

### Hard-coded matching hard-coded
**Symptom:** Production code returns a literal; test asserts on the same literal. Changing both leaves the test passing.

**Example:**
```python
# production
def greeting():
    return "hello"

# test
def test_greeting():
    assert greeting() == "hello"
```

**Fix:** Either move the literal to a config the test can independently verify against, or change the test to assert on a *property* of the value (length > 0, contains expected token) plus a separate snapshot test for the exact string.

---

### Mock-of-mock
**Symptom:** Function under test calls a dependency; test mocks the dependency to return a value; test asserts the function returned that value. The function is just plumbing; the mock is being tested.

**Example:**
```python
def fetch_user(client, id):
    return client.get(f"/users/{id}")

def test_fetch_user(mocker):
    client = mocker.Mock()
    client.get.return_value = {"id": 1, "name": "alice"}
    assert fetch_user(client, 1) == {"id": 1, "name": "alice"}
```

**Fix:** Either the function is too thin to test directly (test at the next layer up where business logic lives), or the test should assert on *interactions* with the dependency rather than the return value — but interaction-only tests have their own risks.

---

### "Doesn't throw"
**Symptom:** Test asserts only that some code path executed without raising. Says nothing about *what it did*.

**Example:**
```python
def test_compute_doesnt_crash():
    try:
        compute(input_data)
    except Exception:
        pytest.fail("compute crashed")
```

**Fix:** Assert on the *result* of `compute`, not just its non-crash. If a non-crash is genuinely the AC (rare), name the test `test_compute_does_not_raise_on_valid_input` and explain why no return-value assertion is possible.

---

### Coverage-driven
**Symptom:** Test exists to hit a line in the coverage report. Has no clear AC trace. Often named `test_function_works` or `test_branch_2`.

**Fix:** Identify what AC the test should be verifying. If none, delete it (and accept the lower coverage number — coverage isn't the goal, behavior verification is).

---

### Mock leakage
**Symptom:** Test asserts on mock call args using string matching. Brittle to internal refactors.

**Example:**
```python
def test_calls_database():
    mock_db.execute.assert_called_with("SELECT * FROM users WHERE id = 1")
```

**Fix:** Test the *outcome*: what state should exist in the (real or in-memory) database after the operation, regardless of which SQL the implementation chose. Or, if testing the SQL string is genuinely the AC, name the test honestly and accept it'll break on refactor.

---

### Flaky / non-deterministic
**Symptom:** Test depends on filesystem ordering, dict iteration order in older pythons, the system clock, network availability, or `random` without a seed.

**Fix:** Seed the randomness, freeze the clock, mock the network, sort the inputs. Or restructure the AC so order/timing doesn't matter (e.g., `assert set(actual) == set(expected)` instead of asserting on a list).

---

### Asserting on logs
**Symptom:** Test reads log output and asserts on it as a proxy for behavior.

**Example:**
```python
def test_processes_user(caplog):
    process_user(user)
    assert "Processed user 1" in caplog.text
```

**Fix:** Assert on the actual side effect (state change, return value, emitted event). Logs are operator-facing strings and routinely change; they aren't contracts.

---

## Story-level smells

### Empty Out-of-scope
**Symptom:** Story has no Out-of-scope section, or it's empty/vague.

**Why it matters:** Every meaningful story has things it intentionally doesn't do. An empty section often means the author didn't think about scope boundaries.

**Fix:** Even a single bullet helps. "Out of scope: configuration loading from non-YAML files (Phase 1)" tells the executor where the boundary is.

---

### "Add X" with no Y
**Symptom:** Goal is "Add a new feature X" but ACs don't describe what changes for users of X.

**Fix:** The goal should describe the *observable result* of adding X. "Add a cache" → "When the same input is gathered twice within 24h, the second invocation completes in ≤ 50ms (vs ≥ 1000ms uncached)".

---

### Dependency cliff
**Symptom:** Story implicitly requires un-shipped work from a later story or phase. Will fail in isolation.

**Fix:** Either add the dependency as an explicit blocker in the story's header, or restructure to use only what's shipped.

---

### Wrong task class
**Symptom:** Story for Phase N implements a concern that belongs to Phase M.

**Fix:** Move the story to its correct phase. Don't try to retain it in the wrong phase.

---

### Stale references
**Symptom:** Story references an ADR by number that doesn't exist, or a section in a doc that has been renamed.

**Fix:** Update the references. If an ADR has been superseded, link to the superseding ADR. If a section has been renamed, link to the new name.

---

## Design-pattern smells

These are the patterns the Design-Patterns critic (Stage 2D) scans for. They live in the **Implementation outline** / **Files to touch** / **Notes for the implementer** sections of a story — not in the ACs themselves. Pattern names are not testable; the *consequence* of the pattern is. When filing a finding, name the smell and propose either a `Notes for the implementer` paragraph (most cases) or an *observable-behaviour* AC (only when the rule-of-three threshold is crossed).

### Primitive obsession
**Symptom:** Raw `str` / `int` / `dict` used for **identifiers** that the rest of the system passes around (probe IDs, warning IDs, parser kinds, run IDs, paths-relative-to-repo-root, ToolCallId, RunId). The type system can't distinguish "an absolute disk path" from "a repo-relative POSIX path" or "a probe name" from "a warning kind".

**Fix:** Promote to `NewType` (`typing.NewType("RepoRelPath", str)`), `Literal["safe_json", "safe_yaml", ...]`, or `StrEnum` when the identifier crosses ≥ 2 module boundaries. Don't promote for module-internal scratch state (Rule 2).

**Diagnostic:** Grep for `path: str` and `path: Path` across the repo. If different callers mean different things by "path", the second usage needs a newtype.

---

### Anaemic data class
**Symptom:** Pydantic model / dataclass with `dict[str, Any]`, optional fields that are only meaningful in certain states (`cap: int | None` where `cap` is set only when `kind == "cap_exceeded"`), or a `kind: Literal["ok", "error"]` discriminator with no enforcement that the dependent fields match.

**Fix:** Tagged union / sum type. `Result = Ok(value: T) | Timeout(elapsed_ms: int) | Refused(reason: str)` as frozen dataclasses, consumed via `match`. The type system catches "I forgot to handle the timeout case" at type-check time.

---

### Implicit registry
**Symptom:** The implementation outline says "to add a new X, add an entry to the `_REGISTRY` dict in module Y" — i.e., a central registration list every sibling must edit.

**Fix:** Either a decorator-registered registry (`@register_probe` populates a module-level dict at import time; new probes are new files that import the decorator) OR filesystem-discovered (the registry walks `probes/layer_a/*.py` at startup). Both are Open/Closed. Only worth introducing at rule-of-three.

---

### Hidden state
**Symptom:** Module-level mutables (`_cache: dict[str, Foo] = {}` at module top), singletons, lazy globals initialized on first use. Test isolation, reentrance, and concurrent-use hazards.

**Fix:** Pass state as an argument (constructor inject, `ProbeContext`, `RunContext`). Module-level constants (`_PARSER_NAME: Final[str] = "safe_json"`) are fine; module-level mutables are not.

---

### Pure-impure tangle
**Symptom:** A single function opens a file, reads bytes, parses, walks the parsed tree, AND emits structured events. Five concerns, one signature.

**Fix:** Pin the pure logic as a separately importable helper (`_strip_comments(data: bytes) -> bytes`); the I/O wrapper becomes the imperative shell. Pure helper is table-testable without filesystem fixtures.

**Diagnostic:** Can a unit test for the pure logic be written with bytes/dataclasses only? If yes but the story prescribes a single function, split.

---

### Dependency Inversion violation
**Symptom:** The kernel imports from a strategy module. Example: `parsers/_io.py` doing `from codegenie.parsers.safe_json import _emit_cap_event` — the kernel depends on a specific sibling.

**Fix:** Lift the shared helper to the kernel; strategy modules call into the kernel. Dependencies point INTO the kernel, never out of it.

---

### Untyped dict shuffling
**Symptom:** A function takes `dict[str, Any]`, returns `dict[str, Any]`, and each caller plucks different keys. No type-system enforcement of the contract; readers must grep all callers to understand what the dict carries.

**Fix:** Define a `TypedDict` or a frozen dataclass with named fields. Phase 0 sets the bar at `mypy --strict`; this is a regression check.

---

### Deep inheritance
**Symptom:** Three or more levels of class hierarchy. `class FooProbe(BaseProbe, MetricsMixin, RetryMixin, LoggerMixin): ...`. Behavior is spread across the inheritance graph; reading one class doesn't tell you what `FooProbe()` actually does.

**Fix:** Composition. `class FooProbe: def __init__(self, metrics: Metrics, retry: Retry, logger: Logger): ...`. Each collaborator is a parameter; the probe assembles them. Phase 0's `Probe` ABC is the *contract surface* — that's fine. Stacked mixins for behavior sharing are not.

---

### Catch-all exception
**Symptom:** `except Exception` (or worse, `except BaseException`) in core logic, particularly in the imperative shell where it swallows genuine bugs.

**Fix:** Catch the narrowest exception you can name. `OSError` for filesystem boundary, `json.JSONDecodeError` for parse, `yaml.YAMLError` for YAML. Anything broader is "fail loud" violation (Rule 12).

---

### Pattern-name AC
**Symptom:** Story has an AC like "uses the Strategy pattern" or "implements the Registry pattern". Pattern names are not testable; a third party can't run a check and get a pass/fail.

**Fix:** Restate as an *observable behaviour*. "Strategy pattern" → "adding a new parser sibling under `src/codegenie/parsers/*.py` requires zero edits to `parsers/_io.py`". The pattern name belongs in the discussion / `Notes for the implementer`, never in an AC.

---

### Premature abstraction
**Symptom:** Story introduces an ABC, factory, decorator-registry, or `Protocol` for what is the FIRST concrete consumer of a would-be family. The story-writer guessed at a future need.

**Fix:** Rule 2 — three similar lines is better than premature abstraction. Strip the scaffolding; ship the concrete code. Note the pattern *opportunity* in `Notes for the implementer` so the next sibling story can promote when the count reaches three.

---

### Missed kernel extraction
**Symptom:** The opposite of premature abstraction. The story is the THIRD or LATER concrete sibling but still copies the kernel logic inline. The previous siblings did the same; nobody extracted.

**Fix:** Mandate the kernel extract in this story. Add an *observable* AC like "the post-parse depth walker logic lives in exactly one file (`parsers/_depth.py`)" — the AC is testable by file count + grep.

---

### Hard-coded extension point
**Symptom:** The implementation has a `match {key}: case "foo": ...; case "bar": ...; case "baz": ...` switch in the kernel, where each case dispatches to a strategy module. Adding the next strategy is a kernel edit.

**Fix:** Pass the discriminator as data (the strategy supplies `parser_kind="..."` at the call site; the kernel emits it untouched). The structlog event keyed by `parser_kind` is the de-facto registry; no central list needed.

---

### `Any` in public signature
**Symptom:** A function exported from a module has `-> Any`, `*args: Any`, `**kwargs: Any`, or `dict[str, Any]` in its public surface. Callers can't rely on the type system; mypy treats every usage as unconstrained.

**Fix:** Replace with a generic (`TypeVar`), a sum type (`Result = Success[T] | Failure`), or a `TypedDict`. `Any` is acceptable inside a module as a private helper for ergonomic reasons (`Any` from a third-party untyped lib); it must not appear in the public surface.

---

## Using this catalog

When a critic files a finding, naming the smell is helpful:

> ### F1 — AC-3 is a Vague qualitative smell
> ...

This helps the Synthesizer cluster related findings, and helps the validation report be scannable across stories. Over time, the catalog itself may grow — append new patterns as they're discovered. Don't delete entries; the codebase's smell catalog is an asset.
