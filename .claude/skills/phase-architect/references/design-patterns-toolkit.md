# Design Patterns Toolkit — shared by every agent in this skill

**Read this before you write a design, a critique, or a synthesis.** Every design choice in a phase artifact must be evaluated against this catalog. Designs that ignore the catalog get attacked by the critic; designs that misapply patterns get attacked by the critic; the synthesizer scores pattern-fit as a tied criterion alongside exit-fit, roadmap-fit, commitments-fit, and critic-survivability.

The catalog is **language-agnostic** but the codewizard-sherpa codebase is Python 3.11+ with Pydantic v2, asyncio, click, and (later) Temporal + LangGraph. Examples are calibrated to that stack.

## How to use this catalog

For each significant design decision (a component, an interface, a state machine, a contract), do three things:

1. **Identify the patterns that apply.** Most decisions touch 1–3 patterns. Be honest about which.
2. **State why those patterns fit *this* problem** — not as ceremony, as a real argument. "Strategy because we need three interchangeable rubric implementations sharing a common interface" beats "Strategy because patterns are good."
3. **Acknowledge the patterns you *deliberately* didn't apply, and why.** Over-applied patterns hurt more than missing ones.

A design that mentions zero patterns is suspicious. A design that mentions twelve is ceremony. **Three to six explicit pattern decisions per phase design is the calibrated range.**

## Anti-patterns to flag explicitly

Before the catalog, the things to attack on sight:

- **Pattern soup.** Every component named after a pattern (`FooFactory`, `BarStrategy`, `BazBuilder`, `QuxObserver`). Patterns are tools, not nouns to scatter.
- **Premature pluggability.** "We made it pluggable in case…" with one implementation. YAGNI. If there's exactly one strategy, it's a function, not a Strategy.
- **Inheritance for code reuse.** If the only reason a class extends another is to share methods, it should be composition + a small helper.
- **Stringly-typed identifiers.** `repo_id: str` everywhere instead of a `RepoId` newtype. Every domain primitive shows up in 50 call sites; without a newtype you can't refactor or even grep meaningfully.
- **Untyped `dict[str, Any]` interfaces.** A "flexible" payload format is a contract you can't see and can't refactor. Pydantic models or TypedDicts, always.
- **Boolean flags on public methods** (`force=True`, `strict=False`, `dry_run=True`). Each flag doubles the behavioral surface. Two flags = four behaviors that need testing. Prefer separate methods or a typed enum/Literal argument.
- **Tag-and-dispatch without a tagged union.** `if record["kind"] == "x": …` repeated across modules. The `kind` field is a sum type; model it that way (Pydantic discriminated union, `Literal` tag).
- **Capability passed through ten frames as a parameter.** That's a context object trying to escape — make it explicit (ContextVar, a small Context dataclass, or a registry).
- **Side effects in constructors / module import time.** Module load runs DB calls, file reads, network. Untestable. Use smart constructors or factory functions.

---

## The catalog

### Architecture-scale patterns

#### Plugin architecture / Pluggable systems
- **What:** A small, stable kernel that knows nothing about specific features, plus a registry of capabilities added without modifying the kernel. (VS Code, pytest, Babel, webpack, Claude Code.)
- **When to apply in codewizard:** any place we said "extension by addition." The probe contract (`@register_probe`), the signal-kind registry (`@register_signal_kind`), the task-class registry (`@register_task_class`), the trust-tier rubric registry. The kernel never imports the plugins; the plugins register on import.
- **Failure mode if misapplied:** a "pluggable" design where the kernel still has a hardcoded list of plugin names, or where adding a plugin requires editing a central dispatch table. That's not pluggable; that's an `if/elif` ladder with extra steps.

#### Hexagonal architecture / Ports and adapters
- **What:** The core domain (pure business logic) talks to the outside world only through *ports* (interfaces). *Adapters* implement those ports for specific technologies (filesystem, HTTP, Temporal, GitHub).
- **When to apply:** anywhere the design crosses a trust or technology boundary. The gather pipeline (core) talks to filesystems / git / network probes (adapters) through a probe Port. The Planner talks to LLM providers (Anthropic, OpenAI) through a leaf-LLM Port. Sandbox isolation is a Port with adapters (subprocess, microVM, Firecracker).
- **Failure mode:** a "hexagonal" design that smuggles `requests.get(...)` directly into a domain function. The whole point is that the core doesn't know about HTTP.

#### Functional core, imperative shell
- **What:** Pure functions in the middle (no I/O, no state, fully testable). Side-effects pushed to the edges (the shell). The shell calls the core; the core never calls the shell.
- **When to apply:** scoring rubrics, BCa bootstrap, decision-classification logic, slice-merging, planning. Anywhere "given inputs, compute outputs deterministically" is the requirement. The harness coordinator is the shell; each probe's logic is the core.
- **Failure mode:** mocking explodes. A function that takes 11 mock arguments is a function that should have been pure.

### Behavioral patterns

#### Strategy pattern (GoF)
- **What:** A family of interchangeable algorithms behind a common interface. Pick one at runtime.
- **When to apply:** rubric implementations (`Rubric` Protocol with `score(case, output) -> BenchScore`), promotion-gate evaluators, sandbox runners (`SubprocessRunner`, `MicroVMRunner`, `FirecrackerRunner`), recipe transformers.
- **Failure mode:** Strategy with a single implementation = unnecessary indirection. Wait for the second implementation before extracting.

#### Chain of responsibility / Pipeline
- **What:** A request travels through a sequence of handlers; each can process, pass, or short-circuit.
- **When to apply:** the 7-stage pipeline (Discovery → Assessment → … → Learning), the recipe → RAG → LLM-fallback decision chain, the per-PR strict-AND signal evaluation, the gather coordinator's per-layer probe sequencing.
- **Failure mode:** a "pipeline" where each stage has 14 ways to mutate shared state. Pipelines work because each stage's contract is narrow.

#### Command pattern
- **What:** Encapsulate an action as an object with `execute()` (and ideally `undo()` and `serialize()`). Decouples invoker from receiver, enables logging, replay, audit.
- **When to apply:** every agent action that lands in the audit chain. PR creation, gate transitions, recipe applications, eval runs. A `Command` is a typed Pydantic record + an executor; its serialized form is what the audit chain stores.
- **Failure mode:** Command for trivial in-process function calls. Reserve for things that need audit, retry, or replay.

#### Specification pattern
- **What:** Encapsulate a yes/no business rule as an object that can be combined (`AND`/`OR`/`NOT`) and reused.
- **When to apply:** trust-tier promotion conditions (`HasMinCases AND LowerBound95AboveThreshold AND ZeroBlockSeverity AND AuditClean AND Complete AND IsolationHomogeneous`). Each clause is a Specification; `evaluate()` ANDs them and returns the failed-condition list.
- **Failure mode:** a 60-line `if/elif` bool-flag chain instead of named, testable, composable specifications.

#### Adapter pattern
- **What:** Wrap an incompatible interface to make it match the one your client expects.
- **When to apply:** wrapping `subprocess.run`, `asyncio.create_subprocess_exec`, Temporal activities, Anthropic/OpenAI SDKs behind one common port. Wrapping `tempfile.TemporaryDirectory` so a probe can swap in tmpfs in tests.
- **Failure mode:** an Adapter that re-exports the same interface unchanged. If you didn't translate, you wrote a forwarder.

### Structural / typing patterns

#### Newtype pattern
- **What:** A zero-cost wrapper type that distinguishes domain-meaningful identifiers from raw `str`/`int`/`UUID`. `NewType("RepoId", str)`, `NewType("RunId", str)`, `NewType("CaseId", str)`, `NewType("CommitSha", str)`.
- **When to apply:** every domain primitive. `RepoId`, `PRNumber`, `RunId`, `CaseId`, `BenchmarkId`, `TaskClassName`, `ProbeName`, `SkillName`, `CassetteId`, `ChainHead`, `BlobDigest`. **Especially identifiers that flow across module boundaries.**
- **Failure mode:** swapping a `RepoId` for a `PRNumber` because both are `str`. Type checker can't help. Newtypes make this a compile-time error.

#### Tagged union / sum type for state
- **What:** A union of concrete variants, each with its own fields, distinguished by a discriminator field. In Python: Pydantic discriminated unions, or `Literal["x"]` tags on dataclasses.
- **When to apply:** state machines (PR-execution states), failure-mode taxonomies (`FailureMode` with `severity: Literal["block","warn","info"]`), edge classification (`AGREE | CONFLICT | COMPLEMENT | SUBSUME`), promotion verdicts (`Sufficient | Insufficient(reasons)`), trust tiers.
- **Failure mode:** booleans for state. `is_pending: bool, is_running: bool, is_done: bool` instead of `Status = Literal["pending","running","done"]`. Booleans allow illegal combinations.

#### Smart constructor
- **What:** A factory that validates inputs and refuses to construct invalid instances. The raw constructor is private (or doesn't exist); only the smart constructor is public.
- **When to apply:** every wire type. `BenchScore.from_dict(...)`, `RepoContext.load(path)`, `TrustTiersConfig.from_yaml(path)`. Pydantic's validators are the language idiom.
- **Failure mode:** every caller has to remember to call `.validate()` afterward. They won't.

#### Make illegal states unrepresentable
- **What:** Choose types so the impossible state can't be constructed in the first place. `Optional[T]` instead of `T` + `is_set: bool`. `tuple[int, int]` instead of `(int, int)` in a dict.
- **When to apply:** every domain model. `BenchScore` with `passed: bool, score: float | None` is wrong if `passed=True` requires `score` to be present — model it as a tagged union (`PassedScore(score=…) | FailedScore(reasons=…)`).
- **Failure mode:** runtime checks ("if x.passed and x.score is None: raise") propagating through the codebase. Each one is an admission that the type was wrong.

### Composition / coupling patterns

#### Composition over inheritance
- **What:** Build behavior by combining smaller objects, not by extending base classes.
- **When to apply:** almost always in modern Python. Use Protocols + composition; reserve inheritance for genuine `is-a` relationships (which are rare).
- **Failure mode:** a 6-level abstract base hierarchy where `ConcretePerformanceBenchmarkRubric` extends `BenchmarkRubric` extends `Rubric` extends `Scorable` extends `Auditable` extends `BaseRubric`. None of those abstractions are doing work.

#### Dependency inversion
- **What:** Depend on abstractions, not concretions. The high-level module declares a Protocol; the low-level module implements it.
- **When to apply:** every cross-module boundary. The `Runner` doesn't import `subprocess`; it depends on a `RubricRunner` Protocol. The `Planner` doesn't import `anthropic`; it depends on a `LeafLLM` Protocol.
- **Failure mode:** mocking out `subprocess.run` everywhere because every class hardcoded it.

#### Open/Closed Principle
- **What:** Open for extension, closed for modification. Adding a new feature should not require editing existing code.
- **When to apply:** every place we said "extension by addition." A new task class lands as new files (probes + skills + recipes + bench). Zero edits to existing files.
- **Failure mode:** the central `dispatch_task_class(name)` function has a `match name` block that grows every time. That's modification, not extension.

#### Capability pattern
- **What:** A token (object) that grants permission to perform an action. Holding the token = having the capability. No capability = no operation.
- **When to apply:** sandbox capability grants (`FilesystemWriteCapability(path=…)` instead of "trust the caller"), cost ledger access (`SpendCapability(budget_usd=…)`), promotion (`PromotionApprovalToken` only obtainable via human review).
- **Failure mode:** "is_admin" booleans checked everywhere. A capability is harder to forge than a flag.

### Run-shape patterns

#### Event sourcing for agent runs
- **What:** State is an immutable log of events. Current state is a fold over events. Replay = re-running the fold.
- **When to apply:** the audit chain (already event-sourced via BLAKE3-chained records). The eval-harness chain. The cost ledger. Anywhere you might ask "what did the agent actually do, and can I replay it?"
- **Failure mode:** event sourcing for state that doesn't need replayability. CRUD is fine if CRUD is what you need.

#### Registry pattern
- **What:** A central object that maps names → registered things. Things register themselves at import time via decorator.
- **When to apply:** `@register_probe`, `@register_signal_kind`, `@register_task_class`. The registry is a dict; the decorator is `def register(name): def wrap(cls): registry[name] = cls; return cls; return wrap`. Stay that simple.
- **Failure mode:** a registry that does more than registration — eager validation, side effects, cross-references at registration time. Keep it dumb; validate on use.

### Module-shape patterns

#### Small modules with deep interfaces
- **What:** A module's public surface should be much smaller than its internal complexity. The interface is what you see; the depth is what's behind it.
- **When to apply:** every module. `codegenie.eval` exports ≤9 names (the architect's chosen ceiling for Phase 6.5). Internally it has cache, audit, runner, registry, models, errors — all hidden behind the 9.
- **Failure mode:** every internal helper exported. Now changing an internal helper is a breaking change.

#### Type everything, strictly
- **What:** `mypy --strict` (or `pyright --strict`) in CI. No `Any`, no untyped functions, no untyped dicts. Public APIs always typed; internal helpers also typed (the cost is one line per function).
- **When to apply:** universally. Already a project commitment per `production/design.md` §2.
- **Failure mode:** `# type: ignore` scattered. Each one is a TODO that won't get done.

---

## Pattern fit as a synthesis criterion

When the synthesizer scores conflicts, **pattern-fit** is a tied criterion alongside exit-criteria-fit, roadmap-fit, commitments-fit, and critic-survivability:

> **Pattern-fit (0–3).** Does this choice apply the patterns the problem actually calls for? Does it avoid premature pluggability and ceremony? Does it make illegal states harder to construct? 3 = clearly aligned, 0 = clearly ceremonious or fights the language.

Pattern-fit is **not** veto-strength (commitments-fit is the only veto). A pattern-light design that nails performance and security can win; a pattern-heavy design that misses the load-bearing commitment loses. But all else equal, the pattern-aligned choice wins.
