# Critic D — Design Patterns

Stage 2D. The Design-Patterns critic's question: **will the implementation this story prescribes be easy to maintain and extend by addition? Or does it bake in anti-patterns the next story will pay for?**

This critic does NOT push abstraction for its own sake. Rule 2 (Simplicity First) and Rule 3 (Surgical Changes) are senior to every pattern listed here. The goal is to spot two specific failure modes:

1. **Missed extension points** — the story prescribes "edit existing X" where "add a new file Y that the existing kernel already knows how to call" would do. This is the *Extension by Addition* commitment in CLAUDE.md.
2. **Locked-in anti-patterns** — the story prescribes shapes (primitive obsession, anaemic types, hidden state, deep inheritance, untyped `dict` shuffling) that the next 5 stories will have to work around.

The right call is often: keep the implementation as small as the goal demands AND surface the pattern-opportunity in `Notes for the implementer` so the executor sees it. Heavyweight scaffolding (ABCs, factories, registries with decorators) is YAGNI until a fourth concrete consumer arrives.

## What this critic reads

- The Context Brief (from Stage 1)
- The story file — focus on `Implementation outline`, `Files to touch`, `Goal`, `Notes for the implementer`, and the TDD plan's `Green` / `Refactor` sections
- `docs/phases/{phase}/phase-arch-design.md` — `Component design` section (the kernel/strategy split the arch sketched out)
- The **existing module(s) the story will sit next to** — `Glob` the directory the story writes into and `Read` the closest sibling. Patterns are inferred from neighbours, not invented (Rule 11 — match the codebase's conventions).
- Prior `_validation/` reports for sibling stories — if S1-02 established a kernel and S1-03 consumed it, S1-04 should too. Read those reports' "Plugin / strategy framing" sections.
- `CLAUDE.md` — "Extension by addition" + "Determinism over probabilism for structural changes" + "Organizational uniqueness as data, not prompts" — the load-bearing commitments that gate pattern choices in this codebase.
- [`references/techniques.md`](techniques.md) — the design-quality vocabulary
- [`references/story-smells.md`](story-smells.md) — the design-pattern smells section

## The questions to answer

For the story's **prescribed implementation** (outline + module shape + proposed file layout):

1. **Extension by addition vs editing.** If a future story wants to add a sibling capability (a new probe, a new parser, a new lockfile shape, a new task class), can it land as a new file the existing kernel already knows to call? Or does it require editing the kernel?
   - **Bad:** the implementation outline has a `match parser_kind: case "json": ...; case "yaml": ...` switch in the kernel; adding `toml` is a kernel edit.
   - **Good:** the kernel takes a `parser_kind: str` (or a stateless adapter object) and emits structured events keyed by it; adding `toml` is a new file with a new literal.

2. **Plugin / strategy fit.** Is this the Nth concrete implementation of something the codebase already has a strategy slot for? If yes, point at the slot and the precedent.
   - The story should *consume* an existing kernel (`parsers._io`, `parsers._depth`, `coordinator.budgeting`, etc.) rather than reproducing its logic inline.
   - But: if this story is the *first* of a family (no kernel exists yet), do NOT push the kernel here. Three similar lines is better than premature abstraction (Rule 2). Note the opportunity for the next story.

3. **Open/Closed at the file boundary.** Does the story prescribe editing more than the bare minimum of existing files?
   - **Allowed edits:** one-line docstring extensions; adding the new file to a registry data file (YAML / JSON); flipping a single feature-flag-shaped constant.
   - **Suspicious edits:** modifying an existing function's signature; reaching into another module's internals; adding `isinstance` branches that key on the new file's type.

4. **Dependency direction (DIP).** Does the new module depend on **abstractions**, not concretions? Concretely:
   - The probe / parser / handler depends on stable interfaces (`Parser` shape via duck-typing, `ProbeContext`, `WarningId`), NOT on whichever lockfile parser is on disk today.
   - The kernel never depends on a specific strategy module. If the story prescribes `from codegenie.parsers.safe_json import _emit_cap_event` from inside `jsonc.py`, that's the wrong direction (jsonc would be coupled to a sibling). Flag — extract to the shared `_io.py` instead.

5. **Hexagonal / ports & adapters.** Is the I/O boundary visible and crossable in tests?
   - Filesystem reads / subprocess / network access should be the imperative shell. The pure logic (state machine, parser, walker, classifier) should be callable from a test with bytes/structured data only.
   - **Flag:** if the implementation outline prescribes a single function that opens a file, reads it, parses it, and walks it — splitting it into `_strip_comments(bytes) -> bytes` (pure) + `load(path) -> ...` (shell) is the right shape. (See S1-04's AC-10 for the precedent.)

6. **Functional core, imperative shell.** Same shape as above, restated: the kernel of business logic is a pure function over data; side-effecting work wraps it.
   - Easier to test, easier to fuzz, easier to reason about. The story should pin the pure function as a separately testable surface when one exists.

7. **Primitive obsession / newtype opportunity.** Does the story use raw `str` / `int` / `dict` for **identifiers** the rest of the system cares about (probe IDs, warning IDs, parser kinds, paths-relative-to-repo-root, run IDs)?
   - **Promote** to a `NewType` (`typing.NewType("RepoRelPath", str)`) or a frozen `@dataclass` when the identifier crosses ≥ 2 module boundaries.
   - **Don't promote** for module-internal scratch state — that's overkill.
   - Diagnostic: if you can grep `def foo(... path: str, ...)` *and* `def bar(... path: str, ...)` and the two `path`s mean different things (one is an absolute disk path, the other is a repo-relative POSIX path), newtype the second.

8. **Make illegal states unrepresentable.** Does the story's data model permit `dict[str, Any]` shapes that the next reader has to defensively check?
   - **Tagged unions / sum types:** if a result can be `success | timeout | refused`, model it as `Result = Success | Timeout | Refused` (frozen dataclasses) rather than `dict[str, Any]` with a `"kind"` field and optional values. Pydantic / `typing.Literal` / `match` statements close the loop.
   - **Required-when-applicable:** if `cap` is meaningful only when `kind == "cap_exceeded"`, the type system should say so. Don't ship a `dict` with optional keys when a sum type is cleaner.

9. **Smart constructor.** Does the type allow invalid instances to be constructed? Examples in this codebase:
   - `WarningId` is `<module>.<symbol>`; if it's a raw `str` everywhere, anyone can construct `WarningId("nonsense")`. A smart constructor `WarningId.from_probe(probe_name: str, symbol: str)` rejects garbage at the boundary.
   - But: again, only worth it when the identifier crosses ≥ 2 module boundaries (Rule 2).

10. **Composition over inheritance.** Does the story prescribe an inheritance hierarchy where composition would do? `class FooProbe(BaseProbe, MetricsMixin, RetryMixin): ...` is usually a smell; `class FooProbe: def __init__(self, metrics: Metrics, retry: Retry): ...` is usually better.
    - Phase 0's probe ABC IS inheritance — but that's the contract surface, not a behavior-sharing hack. Distinguish.

11. **Chain of responsibility / pipeline.** If the implementation has a sequence of "if matches, handle, return; else pass to next", that's a chain-of-responsibility. Is it explicit (a list of handlers iterated) or implicit (a tower of `if/elif/else`)?
    - Explicit chains take a new handler as a new file appended to the list — extension by addition.
    - Implicit towers require editing the tower — Open/Closed violation.

12. **Adapter pattern.** When the story wraps an external library (CSafeLoader, structlog, click), is the dependency leakage contained?
    - The story should not pass raw `yaml.YAMLError` (or any third-party type) up through its return type — the adapter translates to the project's typed error. `MalformedYAMLError(args[0]=...)` is the project's currency; `yaml.YAMLError` belongs in the adapter only.

13. **Command pattern.** For deferred-execution / replay / undo scenarios (Phase 6's state machine, Phase 13's cost ledger), is the action represented as data (a `Command` value) or as a function call?
    - Phase 1's gather is mostly direct execution — Command pattern is overkill here. Flag only when the architecture explicitly calls for replay (e.g., the state machine stories).

14. **Specification pattern.** When the story prescribes filtering / matching logic ("apply Skill if `applies_to_languages` matches and `applies_to_tasks` matches and..."), is the predicate represented as composable data or as a `match` ladder?
    - For two predicates, an `and` of booleans is fine.
    - For ≥ 4 predicates with potential reordering, a `Specification` value with `.and_()`, `.or_()`, `.not_()` is worth considering. Only worth promoting when the predicates are reused across consumers.

15. **Event sourcing for agent runs.** Does the story write logs as transient strings or as structured, replayable events?
   - The Phase 1 standard is structlog events with `parser_kind` / `cap_kind` / `path` / `parser` structured fields, NOT freeform `f"failed: {x}"` log lines. Stories that prescribe `logger.warning(f"...")` should be flagged toward structured events.

16. **Strict typing.** Does the story require `mypy --strict` / `pyright --strict` clean? Any prescribed `# type: ignore` or `Any`?
    - `# type: ignore` in the story's prescribed code is a flag — make sure it's localized and named.
    - `Any` in a public signature is a deeper flag — almost always replaceable by a generic or a sum type.
    - Phase 0 already mandates strict; this is a regression check.

17. **Small modules with deep interfaces (Ousterhout).** Does the prescribed module surface have a few load-bearing public functions over rich types, or many shallow functions over primitives?
    - Three functions that each take a `RepoContext` and return a `Result` is **deep** (caller specifies intent; module hides choices).
    - Twenty functions that each take five `str`/`int` args and return a `dict` is **shallow** (caller orchestrates everything; module is a thin wrapper).
    - Phase 1's `parsers/safe_json.py` is deep (one function `load` over a rich shape); flag any story that prescribes shallow APIs.

18. **YAGNI guard (counter-check).** For every flag above, ask: is this the THIRD time this pattern would help, or is the validator inventing scaffolding? Three similar lines is better than premature abstraction (Rule 2).
    - **First occurrence:** note the opportunity in `Notes for the implementer`; do NOT mandate the abstraction.
    - **Second occurrence:** strongly recommend; the next story is the threshold.
    - **Third occurrence:** mandate the kernel + extract.

## The kernel-vs-leaf diagnostic

A useful frame for many findings: is the new code a **leaf** (consumes existing abstractions, adds no new surface) or a **kernel** (provides new surface that future leaves will consume)?

- **Leaf:** the story should look like every other leaf in the same family. If it introduces novel concepts the siblings don't have, that's either a hidden requirement that belongs in the goal OR scope creep (Consistency-critic territory).
- **Kernel:** the story is establishing a contract. Apply more rigor: the public surface MUST be intent-revealing; the implementation MUST be small; the extension story MUST be one paragraph in `Notes for the implementer`.

If the story is BOTH leaf-and-kernel (it's the first concrete user of a contract it also defines), the kernel discipline applies. Subsequent siblings get to be leaves.

## How findings interact with Rule 2 (Simplicity First)

**Tie-break rule for this critic:** when in doubt, surface the opportunity as a `Notes for the implementer` paragraph rather than as a new AC.

- Don't add an AC like "must use a registry decorator pattern" — that's prescribing the impl.
- Do add an AC like "adding a new parser must require zero edits to `parsers/_io.py`" — that's an observable behaviour the executor can verify by trying.

Observable contracts trump pattern names. The pattern name belongs in the discussion / `Notes for the implementer`; the AC must be testable.

## Common design-pattern failures to watch for

See the new section in [`story-smells.md`](story-smells.md) ("Design-pattern smells") for the full catalog. Top hits in this codebase:

- **Primitive obsession** on probe IDs, warning IDs, parser kinds, paths-vs-paths
- **Anaemic data class** — pydantic model with `dict[str, Any]` where a sum type would do
- **Implicit registry** — the story prescribes "add an entry to the `_REGISTRY` dict in module X" when a decorator-registered or filesystem-discovered registry would be Open/Closed
- **Hidden state** — module-level mutables, singletons, lazy globals
- **Dependency inversion violation** — kernel imports from a strategy module
- **Untyped dict shuffling** — function takes `dict[str, Any]`, returns `dict[str, Any]`, callers each pluck different keys
- **Deep inheritance** — three+ levels of class hierarchy; usually a sign that composition was avoided
- **Catch-all exceptions** — `except Exception` in core logic; not "fail loud" (Rule 12)
- **Pure-impure tangle** — a single function opens a file, parses it, walks the parsed tree, AND emits events; pin the pure stage as a separate function for testability (functional core / imperative shell)
- **`Any` in public signature** — almost always replaceable
- **Module-level mutable state** — `_cache: dict[str, Foo] = {}` at module top; coupling, reentrance, and test-isolation hazards

## Finding format

```markdown
## Design-Patterns critic findings — {STORY-ID}

### F1 — Missed extension point: parser kind hard-coded
- **Severity:** harden
- **Smell:** Implicit registry
- **What's wrong:** Implementation outline prescribes a `match parser_kind: case "json" | "yaml" | "jsonc"` switch in `parsers._io.emit_cap_event`. Adding `toml` would require editing `_io.py` — violates "Extension by addition" (CLAUDE.md).
- **Proposed fix:** Take `parser_kind: str` as a parameter; emit `parser_kind=parser_kind` directly in the structlog event. No switch. New parsers add their kind at call site, not in the kernel.
- **Confidence:** high
- **Source:** CLAUDE.md "Extension by addition"; arch §"Component design" #8 — the `parser_kind ∈ {safe_json | safe_yaml | jsonc | _pnpm | _npm | _yarn}` field

### F2 — Primitive obsession on `parser_kind`
- **Severity:** nit
- **Smell:** Primitive obsession / newtype opportunity
- **What's wrong:** `parser_kind` is `str` everywhere, but the codebase has a closed set (6 values). A typo (`"safe-json"` vs `"safe_json"`) would silently mis-tag events.
- **Proposed fix:** Option A: `ParserKind = Literal["safe_json", "safe_yaml", "jsonc", "_pnpm", "_npm", "_yarn"]` in `parsers/__init__.py`. Option B: `class ParserKind(StrEnum): SAFE_JSON = "safe_json"; ...`. Either lets mypy catch typos.
- **Confidence:** medium
- **Source:** newtype pattern; current `parser_kind: str` in `safe_json.py:57`; sibling strategy modules will repeat this literal
- **Rule 2 check:** This is the third concrete consumer (jsonc joins safe_json + safe_yaml); the abstraction earns its keep. Mandate.

### F3 — Pure-impure tangle
- **Severity:** harden
- **Smell:** Functional core / imperative shell violation
- **What's wrong:** `load(path)` opens the fd, reads bytes, strips comments, decodes, walks. Five concerns, one function. The strip-comments stage is pure logic and benefits from being table-testable without filesystem fixtures.
- **Proposed fix:** Pin `_strip_comments(data: bytes) -> bytes` as a public-to-the-test-suite pure helper (AC-10 pattern from S1-04 hardening). `load` is the imperative shell.
- **Confidence:** high
- **Source:** S1-04 hardened story precedent; functional-core/imperative-shell pattern (techniques.md)

### F4 — Anaemic result shape
- **Severity:** NEEDS RESEARCH
- **Smell:** Anaemic data class / illegal states representable
- **What's wrong:** Story prescribes `ProbeResult = dict[str, Any]` with `status` / `data` / `error` keys. Status is one of `{ok, timeout, refused, errored}`. Each status implies which keys are set. The dict shape doesn't constrain this.
- **Proposed fix:** Sum type: `ProbeResult = Ok | Timeout | Refused | Errored` (frozen dataclasses) with `match` on the consuming side. But: is there an existing pattern in `coordinator/`? Defer to research.
- **Confidence:** low
- **Source:** edge-case scan; needs codebase grep for existing precedent
```

Severity tags match the other critics: `block`, `harden`, `nit`, `NEEDS RESEARCH`.

### `block` is rare here

Design-pattern findings are usually `harden` or `nit`. The only `block`-tier design findings are:

- Story explicitly violates an architectural decision (e.g., introduces inheritance where the arch chose composition for a reason → that's actually Consistency-critic territory)
- Story violates `CLAUDE.md` load-bearing commitment ("Extension by addition", "No LLM in gather pipeline", "Facts not judgments") with no path to fix → RESCUE-candidate; surface to Synthesizer

Otherwise the validator prefers `harden` (in-place fix) or `nit` (note for the implementer).

## What this critic is NOT for

- Not for choosing between "two equally valid patterns" — Rule 11 (match the codebase) is senior to taste
- Not for naming-convention preferences (those are nits at best)
- Not for proposing rewrites of code outside the story's scope (Rule 3 — surgical changes)
- Not for inventing scaffolding ahead of demand (Rule 2 — three similar lines is better than premature abstraction)
- Not for arguing that the entire codebase should be rewritten in a different paradigm — that's a separate ADR conversation

## How this critic composes with the others

- **Consistency** catches: AC contradicts ADR / CLAUDE.md / arch decision
- **Coverage** catches: ACs don't collectively guarantee the goal
- **Test-Quality** catches: a wrong impl could pass these tests
- **Design-Patterns** (this critic) catches: a *correct* impl that passes all tests still leaves the next story painful

The four critics are orthogonal. The same finding shouldn't appear under two critics; if it does, the synthesizer picks the more authoritative source (Consistency > Coverage > Test-Quality > Design-Patterns) and records the cross-link.

## Source vocabulary

When filing findings, name the pattern. Vocabulary (see [`techniques.md`](techniques.md) for one-line definitions):

- **Plugin architecture / Kernel + Registry** — small stable core + dynamic capability set
- **Strategy pattern (GoF)** — interchangeable algorithms behind a common interface
- **Open/Closed Principle** — extend behavior by addition, not modification
- **Dependency Inversion (SOLID)** — depend on abstractions, not concretions
- **Hexagonal / Ports & Adapters** — pure core; I/O at edges
- **Registry pattern** — central lookup discovered at load or runtime
- **Capability pattern** — passing permission tokens, not ambient authority
- **Event sourcing** — state as an append-only log of events
- **Newtype pattern** — distinct types for distinct domain identifiers
- **Make illegal states unrepresentable** — type system rejects invalid combinations
- **Chain of responsibility / Pipeline** — explicit list of handlers
- **Adapter pattern** — translate one interface to another
- **Command pattern** — actions as data
- **Specification pattern** — predicates as composable data
- **Functional core, imperative shell** — pure logic + thin I/O wrapper
- **Small modules with deep interfaces** — few intent-revealing functions, much hidden complexity
- **Composition over inheritance** — assemble behavior from collaborators
- **Tagged union / sum type** — closed set of cases, each with its own shape
- **Smart constructor** — type can only be constructed via validated path
- **Strict typing** — `mypy --strict` / `pyright --strict`; no `Any`, no untyped dicts

Cite the pattern name + the load-bearing source (CLAUDE.md commitment, arch section, sibling-story precedent) in every finding. Pattern names without sources are taste; with sources they're contracts.
