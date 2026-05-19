# ADR-0004: `vuln.provenance` primitive lives at `src/codegenie/primitives/vuln_provenance/`

**Status:** Accepted
**Date:** 2026-05-19
**Tags:** adr-0039 · bounded-primitive · directory-layout · precedent
**Related:** [0005](0005-probes-live-under-plugin-not-core-tree.md), [0007](0007-provenance-adapter-registry-stores-classes.md), [0008](0008-no-vuln-provenance-cache-in-phase-7.md), [production ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md), [production ADR-0039](../../../production/adrs/0039-bounded-additive-core-primitives.md), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md)

## Context

[Production ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md) commits to a `vuln.provenance(cve_id, package_id, image_ref) -> Provenance` primitive and the seven-variant `Provenance` discriminated union, but leaves the placement question explicit: "where does this live in the tree?" [Production ADR-0039](../../../production/adrs/0039-bounded-additive-core-primitives.md) admits bounded additive primitives into the kernel under strict criteria but does not pre-assign a directory.

The three lens designs disagreed: performance-first put it in a new `src/codegenie/vuln_provenance/` top-level package; security-first put it in `src/codegenie/vuln/provenance/`; best-practices put it in `src/codegenie/primitives/vuln_provenance/`. Per `final-design.md §Lens summary` ("non-obvious carry-forward: the `vuln.provenance` primitive lives at `src/codegenie/primitives/vuln_provenance/` — explicitly establishing `src/codegenie/primitives/` as the additive home ADR-0039 implies"), the synthesis adopts best-practices' placement and **promotes the directory to a precedent**: future ADR-0039 bounded core primitives also land under `primitives/`.

## Options considered

- **Option A — `src/codegenie/vuln_provenance/` as a new top-level package.** Performance-first position. **Pattern:** Flat top-level layout. Sets the precedent that every bounded primitive gets its own top-level package — top-level namespace bloats with every additive primitive.
- **Option B — `src/codegenie/vuln/provenance/` (vuln-namespaced).** Security-first position. **Pattern:** Domain-namespaced sub-package. Implies a `vuln/` umbrella with sibling primitives; commits to a domain taxonomy Phase 7 does not need.
- **Option C — `src/codegenie/primitives/vuln_provenance/` with `primitives/` as the additive home for all future ADR-0039 bounded core primitives.** **Pattern:** Layered architecture — `primitives/` is the named layer the kernel-frozen fence treats as the entry point for additive core surface.

## Decision

Adopt **Option C.** `vuln.provenance` lives at `src/codegenie/primitives/vuln_provenance/`. The `primitives/` directory is **the named home** for ADR-0039 bounded additive core primitives. Future bounded primitives (per ADR-0039's criteria) land under `primitives/{name}/` without further architectural debate. The seven-variant `Provenance` discriminated union (ADR-0038 verbatim), the `VulnProvenanceAdapter` Protocol, the `@register_provenance_adapter` decorator, the `assemble_provenance` free function, the SBOM cross-verifier, and the syft reader all live under `primitives/vuln_provenance/`.

## Tradeoffs

| Gain | Cost |
|---|---|
| Future bounded primitives land in a named, discoverable home — `primitives/` becomes the answer to "where does this go?" without a fresh architectural argument | Small precedent risk: `primitives/` may become a dumping ground if ADR-0039's criteria are applied loosely. Mitigated by ADR-0039 itself (its admission criteria are explicit) and by the Phase 7 fence allowlist ([0009](0009-phase-7-byte-edit-allowlist-fence.md)) which gates additions |
| `src/codegenie/__init__.py` gains exactly one new import line for the new primitive — fence allowlist authorizes this one edit | One additional layer of nesting in import paths (`from codegenie.primitives.vuln_provenance import Provenance`); explicit vs. shorter `from codegenie.vuln_provenance import Provenance` |
| Mirrors `src/codegenie/types/`, `src/codegenie/cache/`, `src/codegenie/exec/`, `src/codegenie/coordinator/` — named-layer convention the codebase already uses | Engineers must learn one more layer name; lookup cost is small but real |
| Co-locates the primitive's types, protocols, registry, assembly, and supporting verifier in one tree — operators navigate one directory to read the whole primitive | The `sbom_verifier.py` could arguably live in a `sbom/` sub-package; co-locating it here keeps the primitive coherent at the cost of one cross-cutting module |
| Sets the precedent that ADR-0039 primitives are **module-shaped**, not class-hierarchies — primitives are functions over typed data | An engineer adding a primitive that genuinely needs class hierarchy must justify the deviation; that's a feature, not a bug |

## Pattern fit

Implements **Layered architecture** (toolkit §Architecture / boundaries; production ADR-0039 §Decision) — `primitives/` is the named kernel layer the rest of the codebase consumes; consumers depend on the primitive's public `__init__.py` surface, not on internal modules. Also instantiates **Module-as-namespace discipline** (CLAUDE.md "Functional core / imperative shell"): the primitive is a module-level set of pure functions and typed records, not a class hierarchy. Mirrors `src/codegenie/cache/` and `src/codegenie/grammars/` layout.

## Consequences

- `src/codegenie/primitives/__init__.py` is created (empty or re-exporting `vuln_provenance` public surface).
- `src/codegenie/primitives/vuln_provenance/__init__.py` re-exports the public surface: `Provenance`, `AppDirect`, `AppTransitive`, `AppVendored`, `BaseImage`, `RuntimeBundled`, `Both`, `Unknown`, `AppKind`, `BaseKind`, `UnknownReason`, `AdapterConfidence`, `VulnProvenanceAdapter`, `register_provenance_adapter`, `Layer`, `Ecosystem`, `ProvenanceAdapterId`, `assemble_provenance`, `provenance`, `ProvenanceError`, `RegistryError`, `SyftSbom`.
- Sub-modules: `types.py`, `protocols.py`, `registry.py`, `assembly.py`, `sbom_verifier.py`, `syft_reader.py`, `errors.py`, `events.py`.
- `src/codegenie/__init__.py` gains exactly one import line (Phase 7 fence allowlist row #3).
- An `import_linter` contract extends the cold-start defense ([production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md)) to `src/codegenie/primitives/vuln_provenance/` — no LLM SDK imports.
- A fence test (`tests/fence/test_phase7_no_llm.py`) extends the runtime closure assertion to the new tree.
- A fence asserts no `model_construct()` call sites under `src/codegenie/primitives/vuln_provenance/` (smart-constructor bypass defense per `critique.md §Anti-patterns avoided`).
- Future ADR-0039 primitives that surface in later phases (e.g., a hypothetical `dep_chain.distance` primitive, or `image_provenance.attestation`) will land under `primitives/{name}/` by precedent.
- The `primitives/` layer is **kernel surface** for the purposes of [production ADR-0007](../../../production/adrs/0007-probe-contract-frozen.md) and the kernel-frozen fence — additions are admitted only under ADR-0039's criteria.

## Reversibility

**Low.** Once Phase 8's Planner, Phase 10's Stage 1 Assessment, and Phase 14's caching layer all import `from codegenie.primitives.vuln_provenance import ...`, restructuring the directory is a coordinated multi-phase change. The `__init__.py` re-export surface is the contract; reversal would force every downstream consumer to migrate. The fence allowlist makes the cost visible at every PR.

## Evidence / sources

- `../final-design.md §Lens summary` ("non-obvious carry-forward §1"), §Goals, §Synthesis ledger row 1 + 4
- `../phase-arch-design.md §Component design §1` (`VulnProvenancePrimitive`), §Component design §2 (`Provenance` discriminated union)
- `../critique.md §Things this design missed` (best-practices' placement praised by synthesis), §Cross-design observations
- [production ADR-0038 — Vulnerability provenance attribution](../../../production/adrs/0038-vulnerability-provenance-attribution.md)
- [production ADR-0039 — Bounded additive core primitives](../../../production/adrs/0039-bounded-additive-core-primitives.md)
- [production ADR-0033 — Domain modeling discipline](../../../production/adrs/0033-domain-modeling-discipline.md)
- [production ADR-0005 — No LLM in gather pipeline](../../../production/adrs/0005-no-llm-in-gather-pipeline.md)
