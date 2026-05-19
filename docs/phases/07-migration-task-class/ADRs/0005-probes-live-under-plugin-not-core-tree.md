# ADR-0005: New probes ship under `plugins/distroless-migration--node--npm/probes/`, not under `src/codegenie/probes/`

**Status:** Accepted
**Date:** 2026-05-19
**Tags:** adr-0031 · plugin-architecture · probe-placement · open-closed
**Related:** [0002](0002-shell-invocation-trace-probe-runs-in-microvm.md), [0004](0004-vuln-provenance-primitive-home.md), [0009](0009-phase-7-byte-edit-allowlist-fence.md), [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-frozen.md)

## Context

[Production ADR-0031](../../../production/adrs/0031-plugin-architecture.md) is explicit in its plugin-directory layout: every plugin contributes its own `probes/`, `adapters/`, `subgraph/`, `skills/`, and `recipes/` directories. The whole pitch of the plugin architecture is that adding a task class adds new probes **inside the plugin directory**, never by editing the core probe tree.

The three lens designs disagreed: performance-first and security-first placed `BaseImageProbe` and `ShellInvocationTraceProbe` under `plugins/distroless-migration--node--npm/probes/`; best-practices placed them under `src/codegenie/probes/layer_c/` and `src/codegenie/probes/layer_d/` — adding task-class-specific probes to the core probe tree. The critic landed BP-5 against this: best-practices' placement entrenches a precedent that future task classes' probes go in core, directly contradicting ADR-0031.

`final-design.md §Lens summary §5` ("the new probes ship under the plugin, not under `src/codegenie/probes/`") and §Synthesis ledger row 5 (score **15/15**) lock the plugin-internal placement.

## Options considered

- **Option A — Probes under `src/codegenie/probes/layer_c/` and `src/codegenie/probes/layer_d/`** (layer-coded in the core tree). Best-practices position. **Pattern:** Layer-by-layer organization. Entrenches the precedent that task-class-specific probes live in core; every future task class then debates "core or plugin?"
- **Option B — Probes under `plugins/distroless-migration--node--npm/probes/` with `@register_probe` decorator discovered by the explicit-import plugin loader.** **Pattern:** Plugin-contributed extension per ADR-0031.
- **Option C — Probes under a hybrid `src/codegenie/probes/migration/` sub-namespace.** Half-measure. **Rejected** because it preserves the core-tree dependency while pretending to namespace it.

## Decision

Adopt **Option B.** `BaseImageProbe` lives at `plugins/distroless-migration--node--npm/probes/base_image_probe.py`. `ShellInvocationTraceProbe` lives at `plugins/distroless-migration--node--npm/probes/shell_trace_probe.py`. Both implement [production ADR-0007](../../../production/adrs/0007-probe-contract-frozen.md)'s frozen Probe ABC. Both register via `@register_probe` at module import time. The explicit-import collection point (`src/codegenie/plugins/loader.py`) gains exactly one additive import line per plugin — the only Phase-7 touch to the loader, allowlisted by [0009](0009-phase-7-byte-edit-allowlist-fence.md). Each probe's JSON sub-schema lives under `plugins/distroless-migration--node--npm/schema/` (also additive); the envelope schema gains one `$ref` per probe.

## Tradeoffs

| Gain | Cost |
|---|---|
| ADR-0031's plugin-internal-contributions precedent holds; future task classes (`opentelemetry-migration`, `language-upgrade`, ...) add probes by the same shape | Probes are spread across the tree (`src/codegenie/probes/` + each plugin's `probes/`); engineers learn two places to look. Mitigated: `make check`'s registry test enumerates all discovered probes regardless of location |
| `applies_to_tasks=["distroless-migration"]` is the dispatch-time filter at the registry level; the probes never run for non-migration workflows | The filter is dispatch-time, not gather-time — Gap 1 in arch spec. Phase 10 portfolio-scale dispatch cost is named and deferred |
| A fence test (`tests/fence/test_provenance_primitive_in_plugin_directory.py`) AST-asserts that the two new probes live under `plugins/distroless-migration--node--npm/probes/`, not under `src/codegenie/probes/` — the placement is mechanically enforced | Adding the fence adds one CI file; the fence must be updated row-by-row when new plugins land. Worth it; mirrors Phase 3's per-phase fence discipline |
| Plugin co-locates probes, adapters, recipes, skills, schema — operators read one directory tree to understand the plugin | Schema `$ref` resolution must cross the core/plugin boundary; resolved by ADR-0009's allowlisted `$ref` insertion into the envelope schema |
| Cold-start defense (`make lint-imports`) continues to gate probe collection — the explicit-import seam is the supply-chain hygiene line per CLAUDE.md | The plugin loader's explicit-import row is load-bearing; adding a probe is one new import line (allowlisted) |

## Pattern fit

Implements **Plugin / Registry** ([production ADR-0031](../../../production/adrs/0031-plugin-architecture.md); toolkit §Composition / coupling — Plugin architecture as the named precedent): probes register via `@register_probe` at import; the registry is the kernel; plugins contribute. Also instantiates **Open/Closed at the file boundary** (toolkit §Composition / coupling — Open/Closed): adding a task class = new plugin directory + one explicit-import line, never an edit to existing probe modules or to `src/codegenie/probes/`.

## Consequences

- `plugins/distroless-migration--node--npm/probes/base_image_probe.py` and `.../shell_trace_probe.py` are net-new files. They are the plugin's contribution surface; nothing in `src/codegenie/probes/` is touched.
- `plugins/distroless-migration--node--npm/schema/base_image.schema.json` and `.../shell_invocation_trace.schema.json` are the plugin-local probe sub-schemas (`additionalProperties: false` at every node per Phase 1 ADR-0004).
- The envelope `src/codegenie/schema/repo_context.schema.json` gains exactly two `$ref` insertions (one per probe), allowlisted by [0009](0009-phase-7-byte-edit-allowlist-fence.md) row #4.
- `src/codegenie/plugins/loader.py` gains exactly one additive import line for the new plugin's probe modules, allowlisted by [0009](0009-phase-7-byte-edit-allowlist-fence.md) row #10.
- `tests/fence/test_provenance_primitive_in_plugin_directory.py` AST-walks the new probe locations and asserts:
  - probe classes are defined under `plugins/distroless-migration--node--npm/probes/`,
  - no `BaseImageProbe` or `ShellInvocationTraceProbe` class exists in `src/codegenie/probes/`,
  - the registry contains exactly the expected probes after import.
- Golden fixtures for both probes live under `tests/golden/probes/{base_image,shell_invocation_trace}/`.
- The precedent **probes are plugin-contributed** is now operationally enforced; future task-class plugins follow this shape.
- Best-practices' core-tree placement is closed off structurally — a future PR placing a task-class-specific probe under `src/codegenie/probes/` would have to either justify the deviation via ADR amendment or fail the fence.

## Reversibility

**Medium.** The probes' `name` and slice shape are the load-bearing contract for downstream consumers (TCCM `must_read: [base_image, shell_invocation_trace]` references them by slice name, not by Python import path). Relocating the source files preserves the contract; rewiring the loader is a small change. However, reversing the **policy** (moving probes back into core) would force every future task-class plugin to migrate — that's a multi-phase coordination cost.

## Evidence / sources

- `../final-design.md §Lens summary §5`, §Synthesis ledger row 5 (score 15/15)
- `../phase-arch-design.md §Component design §8 (`BaseImageProbe`), §9 (`ShellInvocationTraceProbe`), §Testing strategy §Fence / structural
- `../critique.md §Attacks on the best-practices design §5` (probe placement; ADR-0031 disagrees)
- [production ADR-0031 — Plugin architecture](../../../production/adrs/0031-plugin-architecture.md)
- [production ADR-0007 — Probe contract frozen](../../../production/adrs/0007-probe-contract-frozen.md)
- [Phase 1 ADR-0004 — Per-probe sub-schemas with `additionalProperties: false`](../../01-phase-1-layer-a-probes-ci-deploy-test-inventory/ADRs/0004-additivity-via-per-probe-subschemas.md)
