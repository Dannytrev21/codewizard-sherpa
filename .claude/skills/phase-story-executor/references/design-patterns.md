# Design Patterns — the refactor & validator lens

This is **not** a checklist to grind through. It's a lens applied at two
moments in the workflow:

- **Refactor step** (Stage 2 inner loop, after green): "before I move to
  the next AC, does any of this code commit a known anti-pattern, or
  miss a project-aligned pattern that would obviously fit?"
- **Validator cross-cutting gate** (Stage 3): "would a sharp reviewer
  flag any of this on a code review?"

Two principles override every pattern below:

1. **Rule 2 — Simplicity first.** No pattern for a single-use site. No
   premature abstraction. Three similar lines is better than a wrong
   abstraction. A pattern is justified when it removes friction *that
   already exists in the code right now*, not friction you expect to
   exist later.
2. **Rule 11 — Match the codebase's conventions.** This codebase
   already uses several patterns heavily (Registry, Capability, Plugin,
   extension-by-addition); diverging from those is a refactor — surface
   it, don't fork it silently.

## Patterns the codebase already uses (reinforce, don't reinvent)

These appear across `docs/production/design.md` and the Phase 0/1
implementation. New code should fit into them, not work around them.

| Pattern | Where it lives | What to do |
|---|---|---|
| **Plugin / Pluggable kernel** | `coordinator` + `probes/*` — coordinator knows nothing about specific probes | New probes register *into* the registry. **Never** edit the coordinator to handle a new probe. |
| **Registry pattern** | `probes/registry.py` — `@register_probe` decorator + `for_task()` lookup | Add a new probe by adding a decorated subclass in its own module. Importing the module registers it. |
| **Capability pattern** | Each probe declares `declared_inputs`, `applies_to_tasks`, `applies_to_languages` | New probe declares its capabilities up front; coordinator filters by them. No runtime introspection. |
| **Open/Closed via extension** | "Adding Java, Python, or a new task type must be new probes + new Skills, never edits to existing probes or the coordinator" (`CLAUDE.md`) | This is load-bearing. A story that requires editing the coordinator to support a new task class is a story that should be split. |
| **Chokepoint modules** (Strategy + single-source-of-truth) | `exec.py`, `hashing.py`, `parsers/safe_json.py`, `parsers/safe_yaml.py`, `output/writer.py` — exactly one importer of the dangerous operation | New dangerous operation? Add a chokepoint module; ban direct imports via `import-linter`. Never re-implement the operation inline. |
| **Pipeline / Chain of responsibility** | `coordinator` orchestrates probes; `output/sanitizer.py` two-pass walk before writer | Multi-step transforms go through ordered stages, each with one responsibility. Never collapse stages into one giant function. |
| **Dependency inversion** | `Probe` ABC in `probes/base.py` — coordinator depends on the contract, not concrete probes | New concrete probe depends on the ABC. The ABC never imports a concrete probe. |
| **Functional core, imperative shell** | Probes are mostly pure functions over filesystem reads; `cli.py` is the imperative shell that wires I/O | Pure logic in probes/parsers/transforms; I/O at the edges. |
| **Newtype for domain primitives** | `WarningId`, `CacheKey`, `BlobSha256`, `RunId`, `ProbeName` (where they exist) | Identifiers that mean different things must have different types. **Never** raw `str` for IDs that have a semantic — wrap them in a `NewType` or a frozen dataclass. |
| **Strict typing** | `mypy --strict` on `src/`; no `Any`, no untyped dict-shuffling | This is enforced in CI. New code must clear `mypy --strict`. `Mapping[str, JSONValue]` over `dict[str, Any]`. |
| **Markers-only exceptions** | `errors.py` subclasses — single positional `args[0]`, no instance state | The marker-only invariant is pinned by `test_subclasses_are_markers_only`. **Never** add `__init__` to a marker subclass. Detail goes in the formatted message string. |

## Patterns to reach for when they genuinely fit

These are not the codebase's default, but a reviewer would welcome them
*when the code naturally calls for them*. Apply during refactor; don't
manufacture the need.

### Strategy pattern (GoF)
**When:** the same operation has 2+ implementations selected at runtime
by some discriminator (e.g., lockfile format: pnpm vs npm vs yarn).
**How:** define a tiny protocol/ABC, implement each variant, dispatch
via a dict-lookup or a registry — not an `if/elif` ladder over types.
**When NOT:** one implementation only. "We might have another someday"
is a Rule 2 violation.

### Smart constructor / Make illegal states unrepresentable
**When:** a value has invariants that can't be expressed in the type
alone (e.g., "non-empty list", "Path that exists", "string matching
this regex").
**How:** a `classmethod` (or module-level factory) that validates and
returns the instance — or `pydantic` / `dataclass(frozen=True)` with
`__post_init__` validation. The raw constructor is private or
unreachable.
**When NOT:** the type already encodes the invariant (e.g., `Path` over
`str`, `int` over `str` for a count).

### Tagged union / sum type for state
**When:** a value is one of several distinct shapes — e.g., a probe
result is `Cached | Ran(success=True) | Ran(success=False) | Skipped`.
**How:** a `Literal`-tagged dataclass family or `match`/`case` over the
tag. Each branch has its own fields; impossible-by-construction is the
goal.
**When NOT:** one shape with optional fields — that's not a sum type,
it's just a partially-filled record. Don't tag fields with
"is_success" booleans and pretend they're branches.

### Adapter pattern (Ports & Adapters / Hexagonal)
**When:** the code talks to an external system (filesystem, subprocess,
HTTP, structlog, …) and you want the core logic testable without
hitting that system.
**How:** define a thin protocol in the core, implement it once for
production and once for tests. The core depends on the protocol, not
the concrete adapter.
**When NOT:** you only call the external system in one place and a
`monkeypatch` would do the job for tests. Don't build an adapter for
hypothetical alternate backends.

### Specification pattern
**When:** you have a growing set of *predicates* over a domain object
(e.g., "is this probe applicable to this task?") and they need to be
combined / inspected.
**How:** small predicate objects with an `and_/or_/not_` algebra; or
just functions of type `Probe -> bool` composed with stdlib `all`/`any`.
**When NOT:** you have one predicate. A function is fine.

### Command pattern
**When:** an action needs to be recorded, replayed, deferred, or
audited — e.g., the audit ledger of probe runs.
**How:** the action is a frozen dataclass + an `execute(ctx)` method.
The dispatcher records the dataclass; replay re-runs it.
**When NOT:** the action runs and is forgotten. Don't wrap every
function call in a Command.

### Event sourcing for agent runs
**When:** you need to reconstruct *what the agent did* later — auditing
probe runs, cache hits, sanitizer rejections, …
**How:** each significant action emits an immutable record into an
append-only ledger; current state is `fold(events)`. The codebase's
`audit.py` already does this for run records.
**When NOT:** a probe's internal state is ephemeral and the only
observable is its final output. Don't event-source what nobody reads.

### Small modules with deep interfaces
**When:** a module exposes a wide, complicated surface that no caller
uses fully.
**How:** narrow the public surface to the smallest verb set that
satisfies callers; keep the implementation as deep as needed. One
public function with a focused signature beats five overlapping
exported helpers.
**Smell:** an `__all__` with 12 entries where callers only ever import
2 of them.

### Composition over inheritance
**When:** you find yourself extending a class to "add a behavior".
**How:** pass the behavior in as a collaborator (a function, a small
object) instead. Inheritance is for *contract*, not *reuse* — that's
what the `Probe` ABC is, and it's where inheritance stops.
**Smell:** two-level deep inheritance (subclass of subclass of base).

## Anti-patterns the validator should flag

If the validator (Stage 3) catches any of these, return to Stage 2 to
fix. These survive tests passing — they show up at review time.

| Smell | Why it's bad | Fix |
|---|---|---|
| **`Any` in a function signature on `src/`** | mypy strict gap; loses every downstream type guarantee | Concrete type, `Mapping[str, JSONValue]`, or a `TypeVar`. Never `Any`. |
| **Raw `str` / `int` for identifiers** with semantics | `WarningId == "package_json.size_cap"` is indistinguishable from any random string | `NewType("WarningId", str)` or a frozen dataclass. |
| **`if isinstance(x, ConcreteSubclass)`** in code that consumes a polymorphic interface | Breaks open/closed; adding a sibling subclass breaks this site | Move the behavior onto the interface, or use `match`/`case` over a tagged union. |
| **"Manager" / "Helper" / "Util" classes** with mixed responsibilities | Wide, shallow surface; nothing the name commits to | Split by responsibility; rename to a verb the class enforces. |
| **Mutable global state** (module-level dicts, singletons that aren't `Final`) | Wrecks testability and concurrency | Pass state explicitly; cache via `functools.lru_cache` on a pure function. |
| **Long parameter lists (>5 unrelated args)** | The function is doing too much; or the args are a missing dataclass | Group into a frozen dataclass; or split the function. |
| **Dict-shuffling at module boundaries** (passing `dict[str, Any]` between layers) | Loses type safety; encourages "I'll just add a key here" creep | Define a `TypedDict` or dataclass at the boundary. |
| **Exception for control flow** (catching expected outcomes) | Hides the success/failure shape from the type system | Return a tagged union (Result-like) or an `Optional`; raise only for genuinely exceptional cases. |
| **Re-implementing a chokepoint inline** (calling `os.open` directly when `safe_json` exists; calling `subprocess.run` directly when `exec.run_allowlisted` exists) | Bypasses the project's structural defenses | Route through the existing chokepoint. If you can't, surface the gap. |
| **Catching `Exception` or `BaseException`** | Swallows bugs we want to see (Rule 12 — fail loud) | Catch the specific subclass; let everything else propagate. |
| **Comments that explain WHAT** the code does | Well-named identifiers already do that (`CLAUDE.md`) | Delete the comment; or rename the identifier; or extract a function with a verb name. |

## How to apply this in the workflow

### During Stage 2 refactor (after each AC goes green)

Spend ~60 seconds on this checklist before moving to the next AC:

- [ ] Did I introduce any raw `str` / `int` / `Any` for something with a semantic? → Newtype it.
- [ ] Did I add an `if/elif` ladder over a closed set of variants? → Tagged union or strategy.
- [ ] Is there a chokepoint module for this operation that I should be using instead? → Route through it.
- [ ] Is there mutable module-level state I just added? → Make it `Final` or pass it explicitly.
- [ ] Did I catch `Exception` or `OSError` more broadly than necessary? → Narrow to the specific subclass.
- [ ] Does the new public surface (`__all__` entries) match what callers actually need? → Trim it.
- [ ] Did I extend an existing class via subclassing when composition would do? → Refactor before this lands.

If you change something based on this checklist, **re-run the tests
before moving on**. The refactor must stay green.

### During Stage 3 validation

Add a `Design quality` row to the gates table. Look for the
anti-patterns above. If you find any in code added by *this* story
(not legacy), the validation result is **FAIL** — return to Stage 2 to
fix.

Do **not** flag anti-patterns in code the story didn't add. Those are
out-of-scope (Rule 3 — surgical changes) and belong in the follow-ups
list, not in the validator's RETURN list.

## What to log in the attempt journal

When you applied a pattern intentionally — or chose not to — record it
in the journal under "Refactor decisions". One line each. Examples:

- "Pulled `_open_and_read` + `_decode_and_validate` out of `load` —
  pipeline / chain pattern; one concern per function."
- "Considered a strategy registry for lockfile parsers but deferred —
  only one parser exists today (Rule 2)."
- "Used `Mapping[str, JSONValue]` over `dict[str, Any]` — strict-typing
  rule; mypy --strict would have flagged the `Any`."

This is what makes future stories able to read past attempts and
understand *why* the structure looks the way it does.

## When in doubt

If you're unsure whether a pattern applies, **err on the side of
simpler code** (Rule 2). It is always easier to add a Strategy /
Registry / Adapter later when the second use site arrives than to
unwind a premature abstraction. The patterns above are tools, not
goals.
