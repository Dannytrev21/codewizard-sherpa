# ADR-0033: Domain modeling discipline — newtype + smart constructor + sum type + illegal-states-unrepresentable

**Status:** Accepted
**Date:** 2026-05-13
**Tags:** typing · correctness · discipline · python
**Related:** ADR-0007, ADR-0029, ADR-0030, ADR-0031, ADR-0032, ADR-0034

## Context

Codewizard-sherpa is fundamentally identifier-heavy and state-machine-heavy:

- **Identifiers everywhere.** A single workflow touches `WorkflowId`, `RepoId`, `PluginId`, `AdapterId`, `ProbeId`, `SkillId`, `RecipeId`, `SymbolId`, `BundleId`, `AttemptId`, `SignalKind`, `CodeLocation`, plus identifiers for every TCCM entry, every event, every cost-ledger row. Without typing discipline these are all interchangeable raw `str`. Passing the wrong one is undetectable until runtime — usually long after the bug shipped.
- **State machines everywhere.** Trust gates have outcomes. Bundles have build states. Plugin resolution has match results. Attempt logs have phases. Adapters have confidence states. Without sum types and exhaustiveness checking, every branch in every handler risks missing a case.
- **Half-valid states everywhere.** A `Bundle` with `tccm=None` and `is_universal_fallback=False`? Currently representable. A `PluginResolution` with both `concrete_plugin` and `universal_fallback` set? Currently representable. These are bugs the type system *could* prevent but doesn't, because the type structure permits them.

Phase 0 commits to `mypy --strict` in CI (per `CLAUDE.md`). That catches `Any` smuggling and untyped functions — necessary but insufficient. The structural failure modes above slip past it because the types involved (`str`, `Optional[X]`, `bool`) are *syntactically* correct even when *semantically* wrong.

The discipline this ADR formalizes is the natural completion of the strict-typing commitment: **model the domain, not just the syntax.**

**Status of existing code at adoption.** Phase 0 has shipped to implementation; Phase 1 is in progress. Both predate this ADR and contain raw `str` for domain identifiers and `Optional[X]` / `bool` flags in places where newtype and sum types would be cleaner. This ADR applies *forward* — Phase 1 onwards adopts the discipline for any new code; Phase 0 (and Phase 1 work already done) gets an opportunistic retrofit as files are touched, with a planned focused refactor pass as a tracked backlog item.

## Options considered

- **Option A — keep `mypy --strict` only.** Catches `Any`, untyped functions, missing return types. Doesn't catch ID confusion or half-valid states. Status quo.
- **Option B — `mypy --strict` + Pydantic for I/O boundaries.** Pydantic validates external data. Helps but doesn't reach internal identifiers, internal state machines, or internal field combinations.
- **Option C — full domain modeling cluster.** Newtype for every domain identifier; smart constructors for every parseable value; tagged unions for every state machine; types designed so illegal states cannot exist. This ADR.

## Decision

**Adopt Option C — full domain modeling cluster, applied forward from this ADR.**

### 1. Newtype for every domain primitive

Every identifier or domain-specific primitive uses `typing.NewType` (or a Pydantic wrapper for primitives needing validation):

```python
from typing import NewType

WorkflowId  = NewType("WorkflowId", str)
RepoId      = NewType("RepoId", str)
PluginId    = NewType("PluginId", str)
AdapterId   = NewType("AdapterId", str)
ProbeId     = NewType("ProbeId", str)
SkillId     = NewType("SkillId", str)
RecipeId    = NewType("RecipeId", str)
SymbolId    = NewType("SymbolId", str)
AttemptId   = NewType("AttemptId", str)
BundleId    = NewType("BundleId", str)
SignalKind  = NewType("SignalKind", str)
TaskClass   = NewType("TaskClass", str)
Language    = NewType("Language", str)
BuildSystem = NewType("BuildSystem", str)
EventId     = NewType("EventId", str)
# ... and so on
```

At call sites: `def resolve_plugin(workflow: WorkflowId, repo: RepoId, ...) -> PluginId: ...`. Passing a `RepoId` where `WorkflowId` is expected is a type error at check time, not a production incident.

Raw `str` is reserved for genuinely-untyped contexts (log lines, user-facing strings). For paths, use `pathlib.Path`.

### 2. Smart constructors for parseable values

Anything constructed from external data (yaml, json, env var, user CLI input, network payload) parses through a constructor that returns a `Result[T, ParseError]`:

```python
@dataclass(frozen=True)
class PluginScope:
    task_class: TaskClass
    language: Language
    build_system: BuildSystem

    @classmethod
    def parse(cls, s: str) -> Result["PluginScope", ParseError]:
        parts = s.split("--")
        if len(parts) != 3:
            return Err(ParseError(f"expected task--lang--build, got {s!r}"))
        return Ok(cls(TaskClass(parts[0]), Language(parts[1]), BuildSystem(parts[2])))
```

Construction without parsing is allowed in trusted contexts (after upstream validation, or with literal values from code). External-boundary data must go through `parse`.

### 3. Tagged unions / sum types for state machines

Use Pydantic v2 discriminated unions for state machines. Pattern matching with exhaustiveness checking (Python 3.11+ `match` + `mypy --strict` + `assert_never`) makes missing-case bugs compile errors.

```python
from typing import Annotated, Literal, Union, assert_never
from pydantic import BaseModel, Field

class BuildPass(BaseModel):
    kind: Literal["pass"] = "pass"
    artifacts: list[Path]

class BuildFail(BaseModel):
    kind: Literal["fail"] = "fail"
    log: str
    exit_code: int

class BuildSkipped(BaseModel):
    kind: Literal["skipped"] = "skipped"
    reason: str

BuildOutcome = Annotated[Union[BuildPass, BuildFail, BuildSkipped], Field(discriminator="kind")]

def render_outcome(outcome: BuildOutcome) -> str:
    match outcome:
        case BuildPass(artifacts=a): return f"pass: {len(a)} artifacts"
        case BuildFail(log=l):       return f"fail: {l[:100]}"
        case BuildSkipped(reason=r): return f"skipped: {r}"
        case _ as unreachable:       assert_never(unreachable)
```

Domains to model as sum types: `BuildOutcome`, `TestOutcome`, `GateDecision`, `PluginMatch`, `BundleResolution`, `AdapterConfidence`, `AttemptResult`, `EvalVerdict`, `ProbeOutcome`. Anything that's currently a `str` enum, `bool` flag, or `Optional[X]` that "really represents" a discriminated choice.

### 4. Make illegal states unrepresentable

Where two fields would be mutually exclusive (or co-required), encode that in the type structure instead of relying on runtime guards.

**Bad** (representable but illegal):

```python
class Bundle(BaseModel):
    tccm: ResolvedTCCM | None
    is_universal_fallback: bool
    # `Bundle(tccm=None, is_universal_fallback=False)` typechecks but is invalid
```

**Good** (illegal state unrepresentable):

```python
class ConcreteBundle(BaseModel):
    kind: Literal["concrete"] = "concrete"
    tccm: ResolvedTCCM        # mandatory

class FallbackBundle(BaseModel):
    kind: Literal["fallback"] = "fallback"
    fallback_reason: FallbackReason

Bundle = Annotated[Union[ConcreteBundle, FallbackBundle], Field(discriminator="kind")]
```

Now `Bundle` is *either* concrete with a TCCM *or* fallback with a reason. The third case ("neither") and the fourth ("both") are not type-constructible.

### Tooling

- `mypy --strict` (already in CI from Phase 0)
- `mypy --warn-unreachable` (catches dead branches that exhaustive sum types eliminate)
- `mypy --enable-error-code=truthy-bool` (catches "is truthy?" checks against values that should be sum types)
- Pre-commit / CI lint flagging raw `str` parameters whose names end in `_id` / are named `*Id` — heuristic but high-signal

## Tradeoffs

| Gain | Cost |
|---|---|
| ID-confusion bugs caught at type-check time, not in production | More upfront type-design work (designing newtype hierarchies + smart constructors) |
| Half-valid states (e.g., `Bundle(tccm=None, fallback=False)`) become unrepresentable | Pydantic boilerplate per sum-type variant (mitigated by tooling and a few helper functions) |
| Missing-case bugs become compile errors via exhaustive `match` + `assert_never` | Onboarding cost — contributors learn the pattern |
| Refactor confidence skyrockets — type checker tells you exactly what breaks | Pattern matching is Python 3.11+, already the floor per Phase 0 |
| Code reads like a domain model — `plugin_id: PluginId` self-documents intent | One-time retrofit cost on Phase 0 + early Phase 1 code |

## Consequences

- **Phase 1 (in progress) adopts this discipline for any new code from the date of this ADR.** Pre-existing Phase 1 code is allowed to remain temporarily; opportunistic retrofit as files are touched.
- **Phase 0 retrofit is a planned follow-up.** Tracked as a backlog item ("type-rigor retrofit"). Can be formalized as a Phase 0.5 entry in the roadmap if scope grows; for now, opportunistic file-by-file retrofit is acceptable.
- **All new ADRs reference newtype names.** When ADR-0029 talks about `workflow_id`, the actual code surface is `workflow_id: WorkflowId`, not `workflow_id: str`. The ADRs stay text-level; the implementation must respect the discipline.
- **Code review discipline.** PRs that introduce raw `str` for domain identifiers, `Optional[X]` for fields that should be sum-type variants, or `bool` flags that should be Literal discriminators get reviewed against this ADR.
- **Event sourcing (ADR-0034) depends on this.** Typed events are dramatically more valuable than untyped events; without ADR-0033's discipline, ADR-0034 produces a low-leverage event soup.
- **ADR-0032 adapters benefit immediately.** The Protocol method `confidence() -> float` should become `confidence() -> AdapterConfidence` (a sum type: `Trusted | Degraded | Unavailable`). Adapter dispatch logic gets sharper.
- **ADR-0029 / ADR-0030 / ADR-0031 surfaces** — Bundle, TCCM-derived results, PluginMatch, AdapterConfidence — get re-modeled as sum types as they're implemented. The ADRs themselves don't need to be amended; the implementation respects the discipline.

## Reversibility

**Low cost early; high cost late.** Adopting now means a small retrofit on Phase 0 + early Phase 1 (small file count); adopting after Phase 5 (when ~5× more code exists) means a substantial multi-week refactor. There is no good reason to defer. Reverse migration (removing the discipline once adopted) is technically reversible but would require coordinated stripping of types across the codebase and accepting the correctness regression — not recommended.

## Evidence / sources

- Python `typing.NewType` — https://docs.python.org/3/library/typing.html#typing.NewType
- Pydantic v2 discriminated unions — https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions
- Yaron Minsky, "Effective ML" (2010) — "make illegal states unrepresentable" (the foundational framing)
- Hillel Wayne on smart constructors — informal but canonical contemporary writeup
- John Ousterhout, *A Philosophy of Software Design* (2018) — module/interface depth
- `CLAUDE.md` Global Rules: Rule 9 ("Tests verify intent, not just behavior") + Rule 12 ("Fail loud") — typed signals are how the system fails loud at compile time, before tests even run
