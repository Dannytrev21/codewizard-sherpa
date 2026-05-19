# ADR-0016: TCCM gains a `derived_queries:` band separating derived-callable invocations from `must_read`

**Status:** Accepted
**Date:** 2026-05-19
**Tags:** tccm · adr-0029 · progressive-disclosure · schema-additive · critic-roadmap6
**Related:** [0004](0004-vuln-provenance-primitive-home.md), [0009](0009-phase-7-byte-edit-allowlist-fence.md), [production ADR-0029](../../../production/adrs/0029-task-class-context-manifests.md), [production §2.7](../../../production/design.md)

## Context

[Production ADR-0029](../../../production/adrs/0029-task-class-context-manifests.md) defines the TCCM (Task-Class Context Manifest) — a per-plugin YAML that declares `must_read`, `should_read`, and `provides`/`requires` indices over the gathered `RepoContext`. The commitment ([production §2.7 Progressive disclosure](../../../production/design.md)) is that TCCMs **index evidence**, not inline it: `must_read` names the files/slices to load at decision time.

The security-first lens design proposed adding `vuln.provenance(cve_id, package_id, image_ref)` as a **`must_read` derived query** — embedding a function call as a `must_read` entry. Best-practices proposed a `derived` block. The critic landed roadmap-6 against the security framing:

> "TCCMs are supposed to index evidence, not inline it. […] Embedding a *function call* as a `must_read` entry conflates 'the evidence to load' with 'the computation to invoke' — the progressive-disclosure commitment is about the former, not the latter."

The synthesis adds a new TCCM band, `derived_queries:`, that holds derived-callable invocations explicitly separate from `must_read`. `final-design.md §Synthesis ledger departure #4` and `phase-arch-design.md §Component design §13` (TCCM `derived_queries` band) lock the additive Pydantic-schema field.

## Options considered

- **Option A — Embed function calls in `must_read`.** Security-first. **Pattern:** Conflate-evidence-with-computation. Rejected per §2.7 progressive disclosure.
- **Option B — Embed function calls in a `derived:` band (single word).** Best-practices. **Pattern:** Additive TCCM band. Acceptable; the synthesis preferred a slightly more descriptive name.
- **Option C — Add `derived_queries:` band to the TCCM Pydantic schema; each entry has `{name, compute, args}`; loader resolves `compute` to an imported callable at plugin-load time.** **Pattern:** Typed-derived-query band.

## Decision

Adopt **Option C.** The TCCM Pydantic schema (`src/codegenie/plugins/tccm.py`) gains exactly one new optional band:

```python
class DerivedQuery(_Frozen):
    name: str
    compute: str   # dotted callable path, e.g. "vuln.provenance"
    args: dict[str, str]   # template strings resolved against workflow + repo context

class Tccm(BaseModel):
    must_read: list[EvidenceRef] = []
    should_read: list[EvidenceRef] = []
    provides: list[str] = []
    requires: list[str] = []
    derived_queries: list[DerivedQuery] = []   # NEW BAND
    # extra="forbid"
```

The TCCM loader resolves `compute: "vuln.provenance"` to the imported callable at plugin-load time. Phase 7's `plugins/distroless-migration--node--npm/tccm.yaml` ships a single `derived_queries:` entry invoking `vuln.provenance(cve_id, package_id, image_ref)`. Existing TCCMs without `derived_queries:` continue to parse unchanged (default is empty list). The Pydantic `extra="forbid"` discipline is preserved. The arg-template grammar (`$workflow.cve` vs `${workflow.cve}` vs other) is deferred to the first implementation story (Open Question §9 in arch spec).

## Tradeoffs

| Gain | Cost |
|---|---|
| `must_read` stays "evidence to load"; `derived_queries:` is "computation to invoke" — the §2.7 progressive-disclosure commitment is honored | One more TCCM band for engineers to learn; mitigated by the band's small surface (three fields per entry) and self-documenting names |
| Future task classes can declare arbitrary derived callables (`vuln.provenance`, future `dep_chain.distance`, etc.) by adding `derived_queries:` entries — no schema growth per derived query | The set of callable `compute` references becomes a small public vocabulary; renaming `vuln.provenance` later coordinates with every consumer plugin |
| TCCM loader fails fast at plugin-load time if `compute:` resolves to an unknown callable; Supervisor refuses to start with a file/line diagnostic | Plugin authors must spell `vuln.provenance` correctly; typos surface at load time, not at workflow time. Acceptable; mirrors `@register_probe` discipline |
| Existing TCCMs (Phase 3, Phase 6.5, etc.) parse unchanged — `derived_queries: list[DerivedQuery] = []` default makes the band purely additive | Phase 3's `plugins/vulnerability-remediation--node--npm/tccm.yaml` may want to add its own `derived_queries:` entry (e.g., `provenance` as a derived call); allowlisted by fence row #2 ([0009](0009-phase-7-byte-edit-allowlist-fence.md)) |
| The band's typed shape (`DerivedQuery` Pydantic model) keeps Pydantic `extra="forbid"` integrity across the TCCM surface — no `dict[str, Any]` smuggled in | The `args: dict[str, str]` field is open-shape (any string keys allowed) — the arg names are validated at callable-dispatch time, not at TCCM-load time. Tradeoff accepted: arg validation belongs at the callable, not at the manifest |

## Pattern fit

Implements **Additive Pydantic-schema band** (toolkit §Composition / coupling — Open/Closed via additive optional fields): existing consumers ignore the new band; new consumers opt in. Also instantiates **Typed-derived-query** (toolkit §Behavioral — Strategy via data): the derived query is data declaring which callable to invoke and which args to pass; the callable is the strategy. Honors [production §2.7 Progressive disclosure](../../../production/design.md): evidence loading and derived-computation invocation are separate bands in the manifest.

## Consequences

- `src/codegenie/plugins/tccm.py` gains the `derived_queries: list[DerivedQuery] = []` field on the `Tccm` Pydantic model. Fence allowlist row #5 ([0009](0009-phase-7-byte-edit-allowlist-fence.md)) authorizes the one-line edit.
- A new `DerivedQuery` Pydantic model is added to the same module (or a sibling) with `frozen=True, extra="forbid"`.
- TCCM loader resolves each `derived_queries[].compute` to an imported callable at plugin-load time:
  - "vuln.provenance" → `from codegenie.primitives.vuln_provenance import provenance`
  - Unknown reference → load-time failure with file/line diagnostic; Supervisor refuses to start.
- `plugins/distroless-migration--node--npm/tccm.yaml` ships exactly one `derived_queries:` entry: `name: provenance, compute: vuln.provenance, args: {cve_id: $workflow.cve, package_id: $workflow.package, image_ref: $repo.base_image}`.
- `plugins/vulnerability-remediation--node--npm/tccm.yaml` adds one `derived_queries:` entry too (fence allowlist row #2). The Phase 3 plugin's TCCM grows additively; existing fields untouched.
- Integration test `tests/integration/test_tccm_distroless_derived_queries_loads.py` proves: TCCM loads, validates, `compute` resolves to the callable, args-template resolution works end-to-end.
- Open Question §9 (arg-template syntax `$workflow.cve` vs `${workflow.cve}` etc.) is deferred to the first plugin-loader implementation story; existing TCCMs without `derived_queries:` continue to parse unchanged regardless of grammar choice.
- The future "list of well-known derived-query callables" becomes a load-bearing vocabulary; growing it requires either a new bounded primitive (ADR-0039 path) or an additive entry in `compute:` resolution. Both are ADR-worthy events.

## Reversibility

**Medium.** Removing the `derived_queries:` band entirely would orphan Phase 7's tccm.yaml entries and require migrating to a different shape (e.g., a separate `derivations.yaml` file). Renaming the band is a coordinated schema change across all plugins that have adopted it. Growing the band (new fields per entry) is forward-additive under Pydantic `extra="forbid"` discipline. Resolving the arg-template grammar is a one-time pick; changing the grammar later is a multi-plugin migration.

## Evidence / sources

- `../final-design.md §Goals` ("TCCM for `distroless-migration` ships as one YAML file […] `vuln.provenance(...)` is referenced as a **derived query under `derived_queries`**"), §Synthesis ledger departure #4, §Component §13 (TCCM `derived_queries` band)
- `../phase-arch-design.md §Component design §13` (TCCM `derived_queries` band — additive Pydantic schema field), §Data model (TCCM derived-queries schema — additive band)
- `../critique.md §Roadmap-level critiques §6` (TCCM `must_read` should not embed function calls; progressive-disclosure commitment)
- [production ADR-0029 — Task-class context manifests](../../../production/adrs/0029-task-class-context-manifests.md)
- [production §2.7 — Progressive disclosure](../../../production/design.md)
