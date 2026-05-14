# Techniques — testing methodologies the critics and researcher can apply

Reference catalog of testing/validation techniques. Critics use these as a vocabulary when filing findings; the researcher uses them when looking up canonical patterns.

## Rule 9 — Tests verify intent, not just behavior

This is the polestar from CLAUDE.md global rules. Every other technique here is downstream of it.

**The frame:** A test is a contract about what the function *means*, not what it *currently does*. Two implementations of the same function should both pass the same intent-verifying test, even if their internals differ.

**The diagnostic:** Could you imagine a different, equally-correct implementation that would fail this test? If yes, the test is over-fit to the current implementation — it's a behavior test, not an intent test.

## Mutation testing thinking

**Pattern:** For each test, ask: "if the production code were mutated in obvious ways, would this test catch it?" Common mutations:

- Replace a return value with a constant (`return result` → `return None`, `return 0`, `return ""`)
- Replace a conditional with its inverse (`if x:` → `if not x:`)
- Replace `>` with `>=`, `==` with `!=`, etc.
- Delete a statement
- Replace a function body with `pass`

**Use:** As a thought experiment in Stage 2B for every test in the TDD plan. If any mutation passes the test, the test is too weak.

**Tools (if formal mutation testing is needed):** `mutmut`, `cosmic-ray` for Python. Usually overkill for individual story validation — the thought experiment is the cheap version.

**Source:** Jia, Y. & Harman, M. "An Analysis and Survey of the Development of Mutation Testing." IEEE TSE 2011. https://doi.org/10.1109/TSE.2010.62

## Property-based testing (QuickCheck / hypothesis)

**Pattern:** Instead of writing example-based tests ("given input A, output is B"), write *properties* that should hold for any input ("for all inputs, decode(encode(x)) == x"). A test runner generates many random inputs and checks the property.

**Use:** When the function has invariants — symmetric operations (encode/decode, parse/format), idempotent operations (sort, normalize), bounded transforms (any output ≤ any input), commutative operations.

**Common invariant patterns:**
- **Round-trip:** `decode(encode(x)) == x` for all valid x
- **Idempotence:** `f(f(x)) == f(x)` for all x
- **Inverse:** `g(f(x)) == x` for all x
- **Commutativity:** `f(a, b) == f(b, a)` for all a, b
- **Associativity:** `f(a, f(b, c)) == f(f(a, b), c)`
- **Monotonicity:** `a < b → f(a) < f(b)`
- **Boundary preservation:** `f(empty) == empty`, `f(singleton) == singleton`

**Tools:** `hypothesis` (Python), `fast-check` (TS/JS), `quickcheck` (Haskell — the original).

**Source:** Claessen, K. & Hughes, J. "QuickCheck: A Lightweight Tool for Random Testing of Haskell Programs." ICFP 2000.
Also: David MacIver's `hypothesis` docs — https://hypothesis.readthedocs.io/

## Metamorphic testing

**Pattern:** When the function's "right answer" is too hard to compute independently (the oracle problem), define *relations between outputs* given related inputs. You don't need to know the right answer; you just need to know that two related inputs should produce related outputs.

**Use:** When the function does something hard to verify directly — ML model outputs, gather-pipeline RepoContext, search ranking, ML training. Whenever you can't write `assert f(x) == expected_value` because computing `expected_value` is what `f` itself does.

**Examples:**
- Adding a file to a repo should never *decrease* `detected_languages` count
- Running gather on a subset of files should produce a subset of the RepoContext
- A sort should be idempotent: `sort(sort(x)) == sort(x)`
- A search engine should rank documents that contain the query at least as highly as documents that don't

**Source:** Chen, T.Y. et al. "Metamorphic Testing: A New Approach for Generating Next Test Cases." Technical Report HKUST-CS98-01, 1998.
Recent survey: Chen, T.Y. et al. "Metamorphic Testing: A Review of Challenges and Opportunities." ACM Computing Surveys 2018. arXiv:1708.05858

## INVEST framework — story shape

**Pattern:** A well-formed user story is:

- **Independent** — implementable without other stories' completion (or has explicit dependencies)
- **Negotiable** — the *what* is captured; the *how* is for the implementer
- **Valuable** — produces observable value (passes an exit criterion, ships a feature)
- **Estimable** — the implementer can size it (not "boil the ocean")
- **Small** — fits in one autonomous-agent execution; not weeks of work
- **Testable** — every AC is verifiable (the polestar of this skill)

**Use:** Consistency critic uses this to assess story-level health. If a story fails I (Independent — has un-stated dependencies), N (Negotiable — over-specifies impl), V (Valuable — does nothing observable), or T (Testable — vague ACs), flag it.

**Source:** Bill Wake, "INVEST in Good Stories, and SMART Tasks." 2003. https://xp123.com/articles/invest-in-good-stories-and-smart-tasks/

## Specification by example

**Pattern:** Concrete examples in the AC make tests easier to write and make the AC harder to misinterpret. Instead of "the formatter handles edge cases", give: "input `[]` → output `\"\"`; input `[1]` → output `\"1\"`; input `[1,2,3]` → output `\"1, 2, 3\"`".

**Use:** Whenever an AC is about transforming inputs to outputs and the transform has multiple cases. The Editor (Stage 4) should prefer ACs that include 1-3 concrete input/output examples over abstract behavioral descriptions.

**Source:** Adzic, G. "Specification by Example: How Successful Teams Deliver the Right Software." Manning, 2011.

## Given/When/Then structure (BDD)

**Pattern:** Frame ACs as Given (initial state), When (action), Then (observable outcome). Forces all three to be explicit.

**Example:**
- Given: a directory containing `app.ts` and `package.json` declaring `"type": "module"`
- When: the user runs `codegenie gather` from that directory
- Then: `repo-context.yaml` contains `detected_languages: [typescript]` and `module_system: esm`

**Use:** Optional. Helpful for ACs that have non-trivial setup or post-conditions. Don't force it on every AC — short ACs read better without.

**Source:** Dan North, 2006. "Introducing BDD." https://dannorth.net/introducing-bdd/

## Test pyramid + test doubles

**Pattern:** Most tests should be fast unit tests; fewer integration tests; even fewer end-to-end tests. When external dependencies make unit tests hard, use *test doubles* (mocks, stubs, fakes, spies) — but understand which kind you're using.

**Use:** The Test-Quality critic should notice if a TDD plan over-relies on mocks (the "mock-of-mock" smell) or under-tests integration. Match the codebase's existing balance.

**Source:** Mike Cohn, "Succeeding with Agile" 2009 (pyramid); Gerard Meszaros, "xUnit Test Patterns" 2007 (doubles vocabulary).

## When the technique catalog isn't enough

Some test problems don't have canonical answers in the catalog above. Examples:

- Testing concurrent / distributed behavior deterministically
- Testing LLM-produced outputs
- Testing GUI / visual outputs
- Testing security properties

For these, Stage 3 Research escalates to arXiv. See [`researcher.md`](researcher.md) for how to find canonical patterns in the academic literature.

## Composition

Real stories often want multiple techniques stacked:

- **Example-based test** for the happy path (one or two cases) — *Specification by Example*
- **Property-based test** for the invariants that hold across inputs — *QuickCheck / hypothesis*
- **Metamorphic test** for behaviors where computing the right answer is hard — *Chen et al.*
- **Negative-space test** for what the system refuses to do — pulls from *Coverage critic*'s catalog

The Editor (Stage 4) should consider whether each AC's test plan covers the right *combination* of techniques, not just whether one example test exists.

---

## Design-quality vocabulary (Stage 2D — Design-Patterns critic)

The first three critics evaluate the story's *specification* (what must be true). The Design-Patterns critic evaluates the story's *prescription* (what shape the implementation takes). Pattern names below are vocabulary the critic uses when filing findings — the actual finding always names an observable consequence, never just the pattern.

The catalog below is intentionally biased toward the codebase's load-bearing commitments (`Extension by addition`, `Determinism over probabilism for structural changes`, `Organizational uniqueness as data, not prompts`). Patterns that don't serve those commitments aren't called out, even if classical.

### Plugin architecture / Kernel + Registry
A small, stable kernel knows nothing about specific features; a registry holds the capabilities. New features land as new files the kernel already knows how to call. The tradition behind VS Code, pytest, Babel, webpack, Claude Code's own skills.

**Use when:** ≥ 3 concrete sibling features share a contract (parsers, probes, lockfile formats, task classes).
**Don't use when:** < 3 concrete consumers exist (Rule 2 — three similar lines is better).
**Codebase precedent:** `parsers/_io.py` + `parsers/_depth.py` as kernel; `safe_json.py` / `safe_yaml.py` / `jsonc.py` as strategies; `parser_kind` literal as registry-via-discriminator.

### Strategy pattern (GoF)
Interchangeable algorithms behind a common interface. Each strategy is selected at runtime by some discriminator (often a string literal or a type tag).
**Codebase use:** every `parsers/safe_*.py` is a strategy over the shared kernel; lockfile parsers (`_pnpm`, `_npm`, `_yarn`) likewise.

### Open/Closed Principle (SOLID)
Open for extension, closed for modification. Adding a new capability shouldn't require editing existing code — only adding new code.
**Diagnostic:** if the story prescribes editing more than one or two existing files (beyond a one-line docstring extension), look hard at whether the change is mechanically additive.

### Dependency Inversion (SOLID / DIP)
Depend on abstractions, not concretions. High-level modules don't import from low-level modules; both depend on an abstraction (an ABC, a `Protocol`, or a duck-typed contract).
**Diagnostic:** if the kernel imports from a sibling strategy module, the dependency direction is wrong. Lift the shared helper.

### Hexagonal architecture / Ports & Adapters
The application core is pure; I/O lives at the edges. The core defines ports (interfaces it needs); adapters implement the ports against real systems (filesystem, network, database).
**Codebase use:** probe logic is the core; subprocess / filesystem access is the adapter (`exec/`, `parsers/`, `cache/`).

### Registry pattern
A central lookup of capabilities, populated at load time (decorator-registered) or runtime (filesystem-walked). The lookup is by a discriminator key.
**YAGNI guard:** until three concrete consumers exist, the implicit registry (a `Final[str]` discriminator on the strategy's emitted events) is enough; no decorator-registry needed.

### Capability pattern
Pass permissions / authority explicitly as tokens; do not rely on ambient authority. Caller possesses a `WriteHandle` object → caller can write. No `WriteHandle` → caller cannot.
**Codebase use:** Phase 1's `BudgetingContext.report_bytes` is capability-shaped — a probe can record bytes only if it holds the context handle the coordinator gave it.

### Event sourcing
State is an append-only log of events; the current state is a fold of the log. Enables replay, audit, time-travel debugging.
**Codebase use:** structlog events with `parser_kind` / `cap_kind` / `path` / `parser` fields ARE the event stream for the gather pipeline. Phase 13's cost ledger and Phase 6's state machine are explicit event sources.
**Diagnostic:** stories that prescribe `logger.warning(f"failed: {x}")` (transient strings, no structure) should be flagged toward `_logger.warning("event.name", **fields)`.

### Newtype pattern
Distinct types for distinct domain identifiers. `UserId`, `ThreadId`, `ToolCallId`, `RunId`. Never raw `str` or `int` for cross-module identifiers.
**Python idioms:** `typing.NewType("RepoRelPath", str)`, `typing.Literal["safe_json", "safe_yaml", ...]`, `enum.StrEnum`, or a frozen `@dataclass`.
**Threshold:** promote when the identifier crosses ≥ 2 module boundaries. Don't promote for module-internal scratch state.

### Make illegal states unrepresentable
The type system rejects invalid combinations at compile time, not runtime.
- "Optional field only meaningful in some states" → tagged union (one case per state, each carrying its required fields)
- "List that must be non-empty" → `NonEmptyList[T]` (smart constructor enforces invariant)
- "String that must match a pattern" → newtype + smart constructor

### Chain of responsibility / Pipeline
A sequence of handlers, each given a chance to handle (return) or pass through. Explicit list iteration > implicit `if/elif/else` tower.
**Diagnostic:** stories that prescribe nested `if/elif/else` over a closed set of cases should be flagged toward `for handler in HANDLERS: result = handler(req); if result is not None: return result`.

### Adapter pattern
Wraps a third-party interface in the project's own typed interface. Translates exceptions, types, and idioms. Third-party types never escape the adapter.
**Codebase use:** `parsers/safe_yaml.py` is an adapter over `yaml.CSafeLoader`; `yaml.YAMLError` is translated to `MalformedYAMLError` at the boundary and never escapes the parser package.

### Command pattern
Actions represented as data (a `Command` value with fields), not as function calls. Enables logging, deferring, retrying, replaying.
**Codebase use:** Phase 6's state machine consumes `Command` values; Phase 13's cost ledger appends a `BudgetEntry` per `RunCommand`. Overkill for direct execution paths (Phase 1's gather); flag only when the architecture explicitly calls for replay.

### Specification pattern
Predicates as composable data with `.and_()`, `.or_()`, `.not_()` operators. Enables filter logic to be data-driven rather than code-driven.
**Threshold:** worth promoting only when ≥ 4 predicates with potential reordering and reuse across multiple consumers. For two-or-three-predicate boolean ladders, plain `and`/`or` is fine.

### Functional core, imperative shell
The kernel of business logic is a pure function over data; side-effecting work (filesystem, network, logging) wraps it.
**Codebase use:** `_strip_comments(data: bytes) -> bytes` is the pure core; `jsonc.load(path)` is the imperative shell.
**Diagnostic:** if the story prescribes a single function that does I/O AND parses AND walks AND emits events, the pure stages should be pinned as separately importable helpers (AC-shaped: "the parser logic must be callable with bytes-only, no path/fd argument").

### Small modules with deep interfaces (Ousterhout)
Few intent-revealing functions over rich types > many shallow functions over primitives. The depth is in the implementation, not the surface.
**Codebase use:** `safe_json.load` is one function over a rich shape (Path + caps); twenty internal helpers hide the complexity.
**Diagnostic:** if a story prescribes a public surface with > 5 functions or with primitive-laden signatures (`def foo(a: str, b: int, c: str, d: int) -> dict[str, Any]`), flag for re-shaping.

### Composition over inheritance
Assemble behavior from collaborators (constructor-injected dependencies) rather than from class-hierarchy mixin towers.
**Codebase precedent:** Phase 0's `Probe` ABC is a *contract surface*, not behavior-sharing. Mixins for behavior are flagged.

### Tagged union / sum type
A type with a closed set of cases, each carrying its own fields. Python idioms: frozen dataclasses with a `Literal` discriminator, consumed via `match`. Or pydantic discriminated unions.
**Use when:** a result / state / event has ≥ 2 cases where the dependent fields differ.

### Smart constructor
A type that can only be constructed through a validating function. Public `__init__` is hidden; `Foo.create(...)` is the only entry, and it rejects invalid inputs at the boundary.
**Use when:** the type carries an invariant the rest of the system relies on (e.g., `WarningId = <module>.<symbol>` — a smart constructor `WarningId.from_probe(probe_name, symbol)` rejects garbage).

### Strict typing
`mypy --strict` / `pyright --strict` clean. No `Any` in public signatures, no untyped functions, no implicit `Optional`, no untyped `dict` shuffling.
**Codebase commitment:** Phase 0 already mandates strict; the Design-Patterns critic flags any prescribed `# type: ignore` or `Any` in a public signature as a regression.

---

## How the Design-Patterns critic uses this vocabulary

When filing a finding, name the pattern AND name an observable consequence. Pattern names are taste; consequences are contracts.

> ### F1 — Missed extension point on `parser_kind` (smell: hard-coded extension point; pattern: Strategy / Open/Closed)
> The implementation outline prescribes a `match parser_kind: case "safe_json": ...; case "safe_yaml": ...` switch inside `_emit_cap_event`. Adding `toml` would require editing the kernel. **Observable fix:** the kernel takes `parser_kind: str` and emits it untouched; new parsers add their kind at the call site, requiring zero edits to `parsers/_io.py`. Trace: CLAUDE.md "Extension by addition"; arch §"Component design" #8.

The synthesizer takes the observable fix and either turns it into an AC (when rule-of-three is reached) or surfaces it in `Notes for the implementer` (when not). Pattern names belong in the prose; ACs name behaviours.
