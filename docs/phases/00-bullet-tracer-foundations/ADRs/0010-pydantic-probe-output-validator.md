# ADR-0010: Pydantic `_ProbeOutputValidator` as the probe-output trust boundary

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** validation · trust-boundary · type-safety · security
**Related:** [ADR-0007](0007-probe-contract-frozen-snapshot.md), [ADR-0008](0008-output-sanitizer-two-pass-chokepoint.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)

## Context

Every probe — including third-party probes a future phase might compose with — emits a `ProbeOutput` that the rest of the system trusts. The dataclass-based `ProbeOutput` from `../../../localv2.md §4` declares `schema_slice: dict[str, Any]` — which means *anything* can land in it: `bytes`, `Callable`, deeply-nested objects, secret-shaped keys. Phase 11 commits these outputs into a real repo as PR evidence; Phase 13 attributes cost based on them; Phase 14 caches them.

The performance and best-practices lenses left `schema_slice` as `dict[str, Any]`. The security lens proposed wrapping it in a Pydantic model with a recursive `JSONValue` type. The best-practices lens explicitly rejected pydantic in Phase 0 ("defer to Phase 6").

`../critique.md §3.2.2` rejects the deferral: Phase 4 introduces `anthropic` and `langgraph`, both of which depend on pydantic v2. Postponing pydantic means every probe written between Phase 1 and Phase 5 gets rewritten in Phase 6 from dataclass-only to pydantic-validated — an unbudgeted migration buried in Phase 6's scope. `../critique.md §7.5` adds: nowhere does the design encode the load-bearing rule "probes report facts, not judgments." A recursive type that refuses `Callable` / `bytes` / `Any` makes that rule structural — enforced by what types are representable.

The trust boundary needs to land in Phase 0. The contract (`localv2.md §4`) must stay dataclass-based to preserve [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md). The validator is internal to the coordinator.

## Options considered

- **No validator; trust probe outputs as written (`[P]`, `[B]`).** Anything in `schema_slice`. Phase 11 commits whatever a buggy probe writes; Phase 14 caches arbitrary objects.
- **Manual type-check at the writer.** Coordinator inspects `schema_slice` keys/values against an enumeration. Misses recursive nesting; brittle.
- **Wrap `ProbeOutput` itself in pydantic (`[S]` initial proposal).** Changes the §4 contract — breaks [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md). Rejected by the synthesis.
- **Pydantic `_ProbeOutputValidator` constructed *from* the dataclass `ProbeOutput` inside the coordinator (synth compromise).** Contract stays dataclass-based; validator is an implementation detail of the coordinator's trust boundary. Validator declares `schema_slice: dict[str, JSONValue]` where `JSONValue = None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]` recursively — no `bytes`, no `Callable`, no `Any`. Field-name regex rejects secret-shaped keys. Confidence must be `Literal["high", "medium", "low"]`.

## Decision

**`src/codegenie/coordinator/validator.py` defines `_ProbeOutputValidator(BaseModel)` (Pydantic v2, `model_config = ConfigDict(frozen=True, extra="forbid")`). The Coordinator constructs the validator from each `ProbeOutput` immediately after probe `run()` returns and before `OutputSanitizer.scrub`. The validator enforces:**

1. **`schema_slice: dict[str, JSONValue]`** — recursive type allowing only JSON-representable values.
2. **Field-name regex** — keys matching `(?i)^.*(secret|token|password|credential|api[_-]?key|auth[_-]?token|bearer|access[_-]?key|private[_-]?key).*$` raise `SecretLikelyFieldNameError`.
3. **`confidence: Literal["high", "medium", "low"]`**.

**The `Probe` ABC and `ProbeOutput` dataclass in `src/codegenie/probes/base.py` remain byte-for-byte `../../../localv2.md §4`** ([ADR-0007](0007-probe-contract-frozen-snapshot.md)). The validator is *internal* to the coordinator and lazy-imported from the CLI entry to preserve cold-start.

## Tradeoffs

| Gain | Cost |
|---|---|
| "Facts, not judgments" (`production/design.md §2.2`) is structurally enforced: `Callable`, `bytes`, opaque types are unrepresentable in `schema_slice` | Pydantic v2 enters the gather closure as a runtime dependency (~ 40 ms import cost behind a lazy-import boundary, mitigated by [ADR-0006](0006-pyproject-toml-extras-shape.md)) |
| Phase 4's `anthropic` / `langgraph` were going to force pydantic anyway — adopting it now avoids the Phase-6 migration of every probe written Phase 1-5 (`critique.md §3.2.2`) | Two representations of `ProbeOutput`: the dataclass contract (lifts to service) and the Pydantic validator (internal). Coherence is checked in `final-design.md §L5` |
| Field-name regex catches obvious secret-shaped keys at probe-emit time, *before* serialization — defense in depth alongside `OutputSanitizer` ([ADR-0008](0008-output-sanitizer-two-pass-chokepoint.md))'s repeat pass | Regex has false positives (e.g., `decryption_steps` matches `*token*`-ish patterns); false-positive probes fail loud, which is the right direction |
| `SecretLikelyFieldNameError` surfaces probe bugs immediately — a probe trying to emit `github_token` rings the bell | Probe authors must know the field-name regex; documented in the probe-authoring guide (Phase 1) |
| Lift to service ([production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)) is unchanged — the contract still lifts as dataclass; the validator is an implementation detail | The "dataclass contract + Pydantic wrapper" pattern must be understood by contributors; the docstring in `validator.py` explains the seam |
| `confidence: Literal[...]` enforces the three-value contract — no probe smuggles `"unknown"` or `"high_with_caveats"` | One more place the literal values are enumerated; mitigated by being type-checked |

## Consequences

- The Coordinator's dispatch path becomes: `probe.run() → ProbeOutput (dataclass) → _ProbeOutputValidator (Pydantic) → OutputSanitizer.scrub → CacheStore.put`. Each arrow is a tested boundary.
- `pydantic>=2.7` is in `[project.dependencies]` ([ADR-0006](0006-pyproject-toml-extras-shape.md)).
- The validator is lazy-imported from inside the `gather` command body in `cli.py`. `codegenie --help` does not import pydantic; the cold-start budget holds.
- `_ProbeOutputValidator` is intentionally private (leading underscore) — contributors should not import it from outside the coordinator. The contract surface is the dataclass.
- The Phase 0 unit test `test_probe_output_validator.py` asserts: `bytes` field → validation error; `github_token` key → `SecretLikelyFieldNameError`; deeply-nested `bytes` → rejection; valid recursive JSON passes.
- Phase 4's deterministic ↔ probabilistic boundary (LLM-fallback) inherits the same pattern: a frozen Pydantic model at the leaf-agent input, internal to the agent wrapper.
- Phase 8's Trust-Aware gates subscribe to the `probe.success` lifecycle event with `confidence=...` as a structlog kwarg — the validator's enforcement of the three literal values is what makes that subscription type-safe.

## Reversibility

**Medium.** Removing the validator and accepting `dict[str, Any]` is mechanically a few lines. Practically, every probe written Phase 1+ relies on the structural guarantee that the validator enforces (probe authors don't manually JSON-check their outputs). Removing forces every probe to add its own validation or accept the risk. The contract direction holds: the dataclass contract lifts to service; the validator is an internal seam that can evolve.

## Evidence / sources

- `../final-design.md §2.3` (Probe contract — Pydantic at the trust boundary; dataclass stays the contract)
- `../final-design.md §L3 row 8` (pydantic in Phase 0 wins 12 vs Phase 6 deferral's 4)
- `../final-design.md §L5` (Coherence check — two representations resolved)
- `../critique.md §3.2.2` (Critic rejects the Phase 6 deferral)
- `../critique.md §7.5` (Critic flags missing "facts, not judgments" structural rule)
- `../phase-arch-design.md §Component design / Coordinator` (Validator lives inside the coordinator)
- `../phase-arch-design.md §Data model` (Pydantic envelope at the trust boundary)
- [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) — dataclass contract preservation invariant
