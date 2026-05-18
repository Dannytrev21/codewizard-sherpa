# ADR-0004: Plugin-private capabilities live on TCCM `provides`/`requires`, NOT on the kernel `Plugin` Protocol

**Status:** Accepted
**Date:** 2026-05-17
**Tags:** plugin-architecture · open-closed · kernel-discipline · phase-7-extension
**Related:** [0002](0002-plugin-registry-kernel-instance-with-default-singleton.md), [0009](0009-recipe-engine-protocol-with-two-implementations-day-1.md), [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md), [production ADR-0029](../../../production/adrs/0029-task-class-context-manifests.md)

## Context

The best-practices lens design proposed `Plugin` Protocol with four methods: `manifest`, `build_subgraph`, `adapters`, and **`cve_feed_parsers`**. The fourth method is *task-class-specific* — it only makes sense for vulnerability-remediation plugins; a Phase-7 distroless plugin has no CVE feeds to parse, it has base-image policy rules. If the kernel `Plugin` Protocol carries a `cve_feed_parsers()` method, then the kernel knows about vulnerability remediation — violating ADR-0031's "extension by addition" promise: Phase 7 distroless either implements a no-op `cve_feed_parsers()` (kernel pollution) or the Protocol grows new methods every time a task class lands (kernel mutation).

The critic flagged this in `critique.md` Issue 4 and `final-design.md §Synthesis ledger row "Plugin Protocol surface"` resolved it: task-class-specific capabilities live on the plugin's TCCM `provides` map (`ADR-0029 §provides/requires` machinery), keyed under a capability namespace; the kernel `Plugin` Protocol stays at four task-class-agnostic methods (`manifest`, `build_subgraph`, `adapters`, `transforms`).

## Options considered

- **Option A — Add `cve_feed_parsers()` to the kernel `Plugin` Protocol.** Phase 7 distroless implements it as a no-op or returns `[]`. **Pattern:** Anti-pattern from toolkit §Open/Closed — the kernel `Plugin` Protocol grows every time a task class lands; reviewers must update the kernel for any new task class.
- **Option B — Subclass the `Plugin` Protocol per task class: `VulnPlugin(Plugin)` with `cve_feed_parsers()`; `DistrolessPlugin(Plugin)` with `dockerfile_capabilities()`.** **Pattern:** Composition over inheritance violated — a plugin's task-class identity is data (its scope tuple), not a type. Class hierarchy explosion at the kernel.
- **Option C — Task-class-specific capabilities declared in TCCM `provides.vuln_index_capabilities` (vuln) / `provides.dockerfile_capabilities` (distroless) / etc.; the kernel knows about none of these.** Plugin code reads its own TCCM at subgraph-build time and dispatches accordingly. **Pattern:** Open/Closed at the kernel boundary; ADR-0029 machinery reused.

## Decision

Adopt **Option C.** The `Plugin` Protocol surface is exactly four methods: `manifest`, `build_subgraph(registry) -> PluginSubgraph`, `adapters() -> dict[PrimitiveName, Adapter]`, `transforms() -> dict[TransformKind, RecipeEngine]`. Task-class-specific knowledge lives in the plugin's `tccm.yaml` under `provides.{capability_namespace}`. Phase 3's vuln plugin declares `provides.vuln_index_capabilities: {nvd_parser: api:NvdParser, ghsa_parser: api:GhsaParser, osv_parser: api:OsvParser}`; Phase 7's distroless plugin will declare `provides.dockerfile_capabilities: {base_image_policy: api:BaseImagePolicy}`. The kernel knows about neither namespace.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 7 distroless lands with zero edits to `src/codegenie/plugins/protocols.py` — the kernel `Plugin` Protocol is frozen | TCCM `provides` namespace is unstructured strings; typos surface only at consumer time (e.g., `vuln_idx_capabilities` vs `vuln_index_capabilities`) |
| TCCM `provides`/`requires` machinery (ADR-0029) is reused — one machinery for both runtime context queries AND task-class capability declarations | Reviewers must learn that TCCM does double duty (context manifest AND capability advertisement) |
| Each plugin's subgraph reads its own TCCM and dispatches against its own capability namespace — no kernel-level dispatch grows with task-class count | A capability-namespace consumer in one plugin can't directly call into another plugin's namespace; cross-plugin reuse requires explicit composition via `extends` |
| Adding a new task class is adding a new plugin directory + a new TCCM `provides` namespace — zero edits to kernel or to any existing plugin | The convention "capability namespaces are per-task-class" is enforced by convention + code review, not by types — a misguided plugin author could pollute a namespace |
| `provides` map keys are typed strings (capability name) → values are import paths (`module:Class`) — broken imports surface at plugin load time, not at workflow time (per ADR-0031 §Schema enforcement) | Import-path strings are a soft contract; refactoring a `provides` target's module path requires updating the YAML |

## Pattern fit

Implements **Open/Closed Principle** (toolkit §Composition / coupling patterns) at the kernel `Plugin` Protocol boundary — the kernel is open for extension (new task classes register new TCCM namespaces) and closed for modification (no kernel edits required for new task classes). Also instantiates **Composition over inheritance** (toolkit) — task-class-specific behavior composes via TCCM data, not via type-hierarchy specialization. Reuses ADR-0029 TCCM machinery as a Bridge between kernel knowledge and plugin-private knowledge.

## Consequences

- `src/codegenie/plugins/protocols.py` has exactly four methods on `Plugin`; a fence test (`tests/fence/test_plugin_protocol_frozen.py`) asserts the method count.
- Vuln plugin's `tccm.yaml` declares `provides.vuln_index_capabilities` with three entries (NVD, GHSA, OSV parsers); `BundleBuilder` reads these via `composed_tccm.provides["vuln_index_capabilities"]`.
- The `example--noop--*` synthetic plugin (per ADR-0013) declares a `provides.example_capabilities` namespace — exercises the contract surface at 3 plugins.
- Phase 7 distroless will declare `provides.dockerfile_capabilities` — adds a new namespace; kernel sees nothing new.
- `provides`/`requires` value parsing is typed via ADR-0029 Pydantic models; broken import paths fail fast at plugin load with `PluginRejected(import_error)`.
- ADR-0029's TCCM contract is the de facto extension mechanism for any future task-class-specific knowledge — a forcing function to keep the kernel small.
- New invariant: adding a method to the kernel `Plugin` Protocol requires an ADR amendment + the fence test update + every plugin's compliance.

## Reversibility

**Medium-high.** TCCM-declared capabilities can be promoted to typed Protocol methods if a capability becomes universal across task classes (the convention is: if 3+ task classes need the same shape, lift it to the kernel via amendment). The reverse — demoting a kernel method to TCCM — would require every plugin's TCCM to be amended. The current shape favors additive extension; reversal is local to a single ADR + a single Protocol edit.

## Consequences for Phase 4 / Phase 7

- **Phase 4 (LLM fallback)** reads `provides.vuln_index_capabilities` to find parsers for new feed sources additively; no kernel changes.
- **Phase 7 (distroless)** ships `plugins/distroless-migration--node--npm/tccm.yaml` with `provides.dockerfile_capabilities`; the kernel `Plugin` Protocol is unchanged. The Phase 7 "zero edits" exit criterion is satisfied at the kernel boundary by construction.

## Evidence / sources

- `../phase-arch-design.md §Component design C2`, §Departures from all three inputs #4
- `../final-design.md §Synthesis ledger row "Plugin Protocol surface"` (score 15/15)
- `../critique.md §Best-practices design — Issue 4` (`cve_feed_parsers()` flagged as kernel pollution)
- [production ADR-0031 — plugin architecture §Plugin manifest](../../../production/adrs/0031-plugin-architecture.md)
- [production ADR-0029 — Task-class context manifests](../../../production/adrs/0029-task-class-context-manifests.md)
- design-patterns-toolkit.md §Open/Closed Principle, §Composition over inheritance
