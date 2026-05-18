# Architecture audit — 2026-05-18

**Status:** Review memo, non-canonical
**Scope:** Production design, roadmap, phase packages, ADR lifecycle, and live gather-pipeline closeout fences
**Disposition:** Record the full criticism ledger here; only Tier 1 items are in the current implementation scope.

## Four kinds of broken promise

| Class | Meaning |
|---|---|
| healthy reassessment | New evidence legitimately changed the best design; older text must be superseded cleanly |
| stale-doc drift | The design changed elsewhere, but old wording was never repaired |
| unresolved contradiction | Two active docs currently promise incompatible things |
| execution gap | The design is sound, but the implementation or closeout checks failed to realize it |

## Findings ledger

| Tier | Confidence | Classification | Finding | Evidence | Recommended disposition |
|---|---|---|---|---|---|
| 1 | high | stale-doc drift | Canonical production opening still described distroless-first sequencing after vuln-first was accepted | `docs/production/design.md`; ADR-0028 | Rewrite canonical framing; mark older local docs historical |
| 1 | high | unresolved contradiction | Phase 7 promised a plugin-directory-only diff while accepted `vuln.provenance` work requires a new shared primitive | `docs/roadmap.md`; ADR-0038 | Narrow the invariant with a new ADR |
| 1 | high | stale-doc drift | Roadmap and landing page still said Phase 6 was pending redesign even after later docs depended on it | `docs/index.md`; `docs/roadmap.md`; Phase 6.5 package | Rebuild Phase 6 design artifacts and relink |
| 1 | high | stale-doc drift | Older Phase 4 wording said “RAG hit, not LLM” although the accepted path is RAG shaping a cheaper LLM call | `docs/roadmap.md`; Phase 4 design | Amend wording to the accepted model |
| 1 | high | stale-doc drift | `bench_score.mean` survived after `lower_bound_95` became the honest promotion signal | roadmap; Phase 6.5 ADR-0002 | Replace canonical claims and amend older source ADR text |
| 1 | high | execution gap | `SbomProbe` and `CveProbe` existed but were not wired into the default registry or envelope schema | probe modules, `probes/__init__.py`, repo-context schema | Fix wiring and add repo-wide fences |
| 1 | high | execution gap | Layer-B-only closeout tests let probe/schema misses escape elsewhere | Layer B tests | Generalize checks repo-wide |
| 1 | high | stale-doc drift | ADR lifecycle could not distinguish accepted-but-evidence-pending decisions | ADR README/templates | Add `Provisional Accepted`, review triggers, reciprocal supersession |
| 1 | high | unresolved contradiction | Phase 6.5 depended on a concrete Phase 6 builder before Phase 6 had a stable consumer contract | Phase 6.5 docs | Phase 6 owns a stable harness-facing SUT contract |
| 1 | high | design omission | No production ADR yet covered data retention/classification, model+prompt release qualification, or multi-plugin coordination | production ADR index | Add ADRs before portfolio-scale rollout |
| 1 | high | sequencing gap | Repo-side opt-out first appeared in the portal era, after real PR opening was already planned | roadmap phases 10–13.5 | Move the policy primitive to Phase 10; keep portal as later projection |
| 2 | medium | healthy reassessment | Event sourcing grew stronger than the earliest simple-ledger framing | production ADR-0034 lineage | Keep current design; cross-link rather than backport prose everywhere |
| 2 | medium | design pressure | Story sizes have grown large enough to strain one-session execution | phase story manifests | Consider a later story-sizing pass, but do not mix into Tier 1 |
| 2 | medium | design pressure | Portal scheduling may deserve reevaluation once operator workflow evidence exists | roadmap | Defer until workflow data exists |
| 3 | medium | speculative cleanup | Some graph abstractions may eventually collapse if later phases reveal unnecessary ceremony | phase packages | Defer until repeated pain appears |
| 3 | medium | speculative cleanup | Wider docs normalization beyond active contradictions would create churn without changing contracts | broad docs set | Leave out of current initiative |

## Promise analysis

The distroless-first promise is a **healthy reassessment**: the system learned that vulnerability remediation is the better first task class, and ADR-0028 records the tradeoff. The old promise becomes a problem only where stale canonical docs still repeat it.

The Phase 7 plugin-directory-only promise is an **unresolved contradiction** rather than an execution failure. Later design work found a genuinely shared routing primitive; the old literal invariant was overfit. The right repair is a narrower, explicit invariant, not forcing the implementation into the wrong layer.

The `SbomProbe` / `CveProbe` miss is an **execution gap**. The architecture already said how probes and schemas are wired; the implementation simply failed to close the loop, and the tests were too narrow to catch it.

The `bench_score.mean` and “RAG hit, not LLM” claims are **stale-doc drift**. The better decision had already been made elsewhere; the old text just lingered.

## Tier summary

- **Tier 1:** lifecycle governance, canonical contradiction cleanup, Phase 6 redesign, missing policy ADRs, repo opt-out sequencing, and closeout fences.
- **Tier 2:** worthy follow-up work once Tier 1 is stable.
- **Tier 3:** speculative cleanup with insufficient evidence today.
