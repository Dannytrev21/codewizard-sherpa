# ADR-0003: `@register_probe(heaviness=, runs_last=)` — registry annotations, not Probe ABC fields

**Status:** Accepted
**Date:** 2026-05-14
**Tags:** registry · coordinator · scheduling · contract-preservation · open-closed · chokepoint
**Related:** 02-ADR-0007, [Phase 0 ADR — probe contract surface](../../00-bullet-tracer-foundations/ADRs/), [Phase 1 ADR-0002](../../01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md)

## Context

The Phase 0 coordinator dispatches probes under a single `asyncio.Semaphore(min(cpu_count(), 8))` budget. Phase 2 introduces probes with vastly different cost profiles: `SCIPIndexProbe` and `RuntimeTraceProbe` are heavy (8–90 s), Layer G scanners are medium (3–8 s), and the load-bearing `IndexHealthProbe` (B2) must dispatch **after** every other probe so it can read sibling slice metadata to construct its `IndexFreshness` value (`phase-arch-design.md §"Process view"` load-bearing properties 1 & 3; `final-design.md §"Components" #1, #13`). Without some scheduling input, a cold gather hits the wall-clock target only by topological accident.

Three competing shapes surfaced:
- The **performance lens** proposed `cost_tier: Literal[0,1,2,3]` as a new field on the `Probe` ABC itself, plus per-tier semaphores. Probes self-classify; the coordinator reads the ABC field.
- The **security lens** proposed `ProbeContext.capabilities: ProbeCapabilities` as a discriminated union (`InProcessCapabilities | SubprocessSandboxCapabilities | ContainerSandboxCapabilities`) — a new mandatory field on `ProbeContext` that every existing Phase 0/1 probe would have to `match` exhaustively on to stay typecheck-clean.
- The **best-practices lens** proposed nothing — let topological order from `requires=` carry the scheduling, even though the load-bearing `runs_last` semantic isn't a true dependency.

The critic ([critique.md §"Attacks on the performance-first design" #2](../critique.md), §"Attacks on the security-first design" #2) attacked both contract changes: `localv2.md §4` declares the probe contract frozen; [Phase 1 ADR-0002](../../01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md) added `parsed_manifest` to `ProbeContext` (not to `Probe`), and that was an ADR-gated single optional `Callable | None = None`. `cost_tier` on `Probe` is "data the coordinator needs, smuggled onto the probe contract." `capabilities: ProbeCapabilities` is a coordinated every-file edit dressed as additive. Critic finding #2 was the load-bearing observation: **`cost_tier` is data the coordinator needs to dispatch, not data the probe needs to declare** — and Phase 0's `@register_probe` decorator is already the kernel-side registry that scheduling annotations naturally live on.

The synthesis (`final-design.md §"Conflict-resolution table" row 2`, `final-design.md §"Components" #13`) picked the registry-annotation path: extend the Phase 0 `@register_probe` decorator with optional kwargs `heaviness` and `runs_last`. The coordinator reads them when sorting the ready-queue under the existing single semaphore. The `Probe` ABC is untouched. `ProbeContext` is untouched (Phase 2's one optional addition — `image_digest_resolver` — is governed by 02-ADR-0004, not by this ADR).

## Options considered

- **Option A — `cost_tier: Literal[0,1,2,3]` on the `Probe` ABC + per-tier semaphores.** **Pattern:** Strategy (per-tier semaphores). Performance lens's pick. Violates [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) (Probe contract preserved POC→service); critic finding #2 + critic [P] hidden-assumption #2 (per-tier sizing degenerates to 2-vs-2 starvation on `cpu_count()=2` GitHub-hosted runners).
- **Option B — `ProbeContext.capabilities: ProbeCapabilities` discriminated union.** **Pattern:** Capability + sum type. Security lens's pick. Every existing probe must `match` exhaustively; coordinated every-file edit; the discriminator is paid by every probe to satisfy a coordinator scheduling concern.
- **Option C — No scheduling input; rely on `requires=` topology and luck.** **Pattern:** none. Best-practices lens's pick. The load-bearing `IndexHealthProbe.runs_last` semantic is not a topological requirement (B2 reads sibling *outputs*; it doesn't require their *execution* in the `requires=` sense — it just needs to run last); modeling it as `requires=[every-other-probe]` is a hack that scales O(N) and lies about dependencies.
- **Option D — Registry-side annotations via `@register_probe(heaviness=…, runs_last=…)` decorator kwargs; coordinator reads them from the registry, not from the probe class.** **Pattern:** Registry + decorator-data. Synthesis pick. Scheduling concern lives at the coordinator's layer; the `Probe` ABC and `ProbeContext` are untouched; mirrors [Phase 1 ADR-0002](../../01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md)'s "additive optional" precedent at the right layer.

## Decision

Adopt **Option D**. The Phase 0 `@register_probe` decorator is extended with two **optional keyword arguments**:

```python
def register_probe(
    *,
    heaviness: Literal["light", "medium", "heavy"] = "light",
    runs_last: bool = False,
) -> Callable[[type[Probe]], type[Probe]]: ...
```

The kwargs are stored on the registry entry, not on the `Probe` class. The coordinator extends by ~15 LOC to sort the ready-queue (heavy first, lights filling slots) and to reserve the final slot for any `runs_last=True` probe. The single `Semaphore(min(cpu_count(), 8))` is preserved — no per-tier semaphores. The `Probe` ABC, `ProbeContext` (this ADR), and `cache_strategy` discriminator are unchanged. **Pattern: Registry + decorator-data at the right layer — scheduling concerns annotate the registry entry; the contract surface is untouched.**

## Tradeoffs

| Gain | Cost |
|---|---|
| `Probe` ABC stays frozen — [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) preserved verbatim; Phase 0 contract-freeze snapshot (`tests/unit/test_probe_contract.py`) continues to pass without amendment | The coordinator's `_dispatch` grows by ~15 LOC for the sort step; this is a non-trivial Phase 0 coordinator edit even if the chokepoint surface (Semaphore, wait_for, isolation try/except, ProbeOutput flow) is preserved |
| `ProbeContext` is untouched by this ADR — every Phase 0/1 probe runs unchanged. The one additive Phase 2 `ProbeContext` field (`image_digest_resolver`) is a separate ADR (02-ADR-0004) governed by [Phase 1 ADR-0002](../../01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md)'s precedent | Two annotation channels for "what the coordinator needs to know about a probe": `requires=` on the contract for topological dependencies, registry kwargs for scheduling. The split is honest (dependencies vs. cost) but documentation must make it visible |
| Single `Semaphore(min(cpu_count(), 8))` preserved — `cpu_count()=2` (GitHub-hosted runner) does not starve; heavy probes simply *start first* under the same budget | The "heavy probes first" sort is a soft optimization, not a guarantee — on `cpu_count()=2`, `SCIPIndexProbe` (~10 s) + `RuntimeTraceProbe` (~90 s) still serialize; the bench canary `tests/bench/bench_portfolio_walltime_hosted_runner.py` (Gap 2 improvement) makes this measurable |
| `runs_last=True` cleanly encodes B2's "dispatch after siblings" requirement without the `requires=[every-other-probe]` topological hack | `runs_last` is a global ordering primitive (one probe per gather may set it); a future need for "runs before X but after Y" is not expressed here — that's `requires=`'s job and should stay there |
| Annotation kwargs default safely — existing decorator call sites (`@register_probe` without args) keep their `heaviness="light", runs_last=False` semantics, so Phase 0/1 probes need no edit | Phase 0/1 probes that *should* be `heaviness="medium"` (e.g., `NodeManifest` on a 500-MB lockfile) won't be unless someone retrofits — Phase 2 deliberately doesn't retrofit (Rule 3 — surgical changes); the retrofit is a tracked backlog item |
| Scheduling data is grep-able at the decorator call site — `grep -nE 'register_probe.*heaviness=.heavy.' src/` lists every heavy probe in seconds | The registry entry's shape grows past "the class itself"; a future change to the registry-entry record type touches more code than today's "registry[name] = cls" |

## Pattern fit

Pattern: **Registry + decorator-data** (`design-patterns-toolkit.md §"Registry pattern"`). The toolkit's prescription — "A registry is a dict; the decorator is `def register(name): def wrap(cls): registry[name] = cls; return cls; return wrap`. Stay that simple" — admits exactly the extension we make: the registry value becomes a small record (`ProbeRegEntry(probe_class, heaviness, runs_last)`) instead of bare `cls`. The pattern's failure mode the toolkit warns against ("a registry that does more than registration — eager validation, side effects, cross-references at registration time") is avoided: annotations are pure data; nothing runs at registration time except writing to the dict. Composes with **Open/Closed** (`design-patterns-toolkit.md §"Open/Closed Principle"`) — a new probe is a new file + decorator, not an edit to the coordinator's sort logic; the coordinator's sort sees an opaque annotation. Composes with [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md)'s "newtype + sum type" discipline via the `Literal["light", "medium", "heavy"]` discriminator — `heaviness` is typed, not stringly-typed.

## Consequences

- `src/codegenie/probes/registry.py` (the existing Phase 0 module) gains a `ProbeRegEntry` record type holding `(probe_cls, heaviness, runs_last)`. `register_probe`'s signature gains two kwargs; existing call sites (Phase 0 + Phase 1 probes) continue to work without edit.
- `src/codegenie/coordinator.py` gains ~15 LOC: the ready-queue is sorted by `heaviness` (heavy first), and any `runs_last=True` probe is held back until siblings finish. The Semaphore is unchanged.
- `tests/unit/test_probe_contract.py` (Phase 0 freeze snapshot) continues to pass — the `Probe` ABC and `ProbeContext` are untouched by this ADR.
- `tests/unit/probes/layer_b/test_index_health_probe.py` asserts `runs_last=True` is respected by the coordinator (dispatch ordering observable via probe-start timestamps).
- `tests/bench/bench_portfolio_walltime_hosted_runner.py` (Gap 2 improvement) emulates `cpu_count()=2` via `CODEGENIE_FORCE_CPU_COUNT=2` and measures actual hosted-runner walltime — the hidden-assumption test the critic [P] §"hidden assumption" #2 demanded.
- The annotation channel is now the named extension point for future scheduling concerns (`runs_first`, `cooperative_yield`, `min_memory_mb`); each new kwarg is an ADR amendment to this one — same shape as `ALLOWED_BINARIES` additions (02-ADR-0001).
- The performance-lens-proposed per-tier semaphores stay rejected; if scheduling intelligence past "sort by heaviness" is ever needed, it lives in `coordinator.py`'s sort function, not in the registry contract.

## Reversibility

**Medium.** Removing the kwargs is a coordinator-side edit (drop the sort; ignore the annotations) plus deletion of the registry record's extra fields. Probes carrying `@register_probe(heaviness="heavy")` would continue to compile and run; the decorator would accept and silently discard the kwargs. The harder reversal is removing `runs_last` semantics if `IndexHealthProbe` ever needs to be re-modeled as a topological-tail probe via `requires=` — but B2's actual dependency shape ("reads slice metadata", not "depends on probe execution") would resist that reshaping. The kwarg path is the boring shape; reverting would re-introduce the `requires=[every-other-probe]` hack the design explicitly rejected.

## Evidence / sources

- `../final-design.md §"Conflict-resolution table" row 2` — the resolution
- `../final-design.md §"Components" #13` — registry annotations as the right-layer answer
- `../phase-arch-design.md §"Logical view"` — `ProbeRegistry` class card and `Coordinator` "sort-order edit only" annotation
- `../phase-arch-design.md §"Process view"` — load-bearing property 1 (`IndexHealthProbe` dispatches after every sibling via `runs_last=True`)
- `../critique.md §"Attacks on the performance-first design" #2` — `cost_tier` is data the coordinator needs, smuggled onto Probe ABC
- `../critique.md §"Attacks on the security-first design" #2` — `ProbeContext.capabilities` is coordinated every-file edit
- [Phase 0 ADRs](../../00-bullet-tracer-foundations/ADRs/) — `Probe` ABC + `@register_probe` decorator + Coordinator chokepoint definitions
- [Phase 1 ADR-0002](../../01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md) — additive-optional precedent at the `ProbeContext` layer
- [Production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) — Probe contract preserved POC→service; this ADR is the structural promise that Phase 2 honors it
- [Production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) — `Literal["light","medium","heavy"]` is the typed discriminator
