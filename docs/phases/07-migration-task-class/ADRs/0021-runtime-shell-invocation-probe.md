# ADR-0021: `RuntimeShellInvocationProbe` statically detects app-code shell-out; `src/**` hits block, `tests/**` hits are advisory

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** amendment-a · g4 · g12 · tree-sitter · static-analysis · refusal
**Related:** [0002](0002-shell-invocation-trace-probe-runs-in-microvm.md), [0005](0005-probes-live-under-plugin-not-core-tree.md), [0009](0009-phase-7-byte-edit-allowlist-fence.md), [0025](0025-migration-refusal-taxonomy.md), [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)

## Context

`final-design.md §Amendment A §A.2` gaps G4 and G12. A Chainguard distroless runtime image has no `/bin/sh` and no shell utilities. Application code that shells out at runtime — `child_process.exec`/`execSync`/`spawn`, `Bun.spawn`, `Deno.run` — builds clean and passes the Dockerfile policy gate, then fails with `ENOENT` the first time that code path executes in production. The design-of-record's `ShellInvocationTraceProbe` ([ADR-0002](0002-shell-invocation-trace-probe-runs-in-microvm.md)) observes shell invocations *during the image build*; it says nothing about what the app does *at runtime*. That is the gap G4 names.

G12 is the inverse failure: test fixtures and test harnesses legitimately shell out (`execSync('git ...')` in a setup script, integration tests spawning helpers). A probe that treats every shell-out as blocking would refuse a perfectly valid production migration because of code that never runs in the shipped image. The probe must distinguish *production* shell-out from *test-infra* shell-out.

`phase-arch-design.md §Component design — Amendment A §18` resolves both to a single plugin-internal probe that walks JS/TS sources and tags each hit with a path-derived criticality. Critically, Amendment A §A.3 departure #3 forbids adding `tree-sitter-bash` — G4 needs the JS/TS call graph, not bash parsing.

## Options considered

- **Option A — Runtime / dynamic detection by executing the app.** Run the application (or its test suite) under instrumentation and observe `execve` calls, the way [ADR-0002](0002-shell-invocation-trace-probe-runs-in-microvm.md)'s build trace works. **Pattern:** Dynamic trace. **Rejected** — requires executing arbitrary app code, is non-deterministic (only covers exercised paths), and a shell-out on a cold error branch is exactly the case that ships broken; coverage is the wrong tool for a completeness question.
- **Option B — Static tree-sitter AST walk over JS/TS sources.** Use the existing `grammars.lock.language_for("javascript" | "typescript")` grammars to find `child_process` member calls, `Bun.spawn`, `Deno.run`; classify each hit by file path. **Pattern:** Static AST analysis with scope-aware matching.
- **Option C — Regex grep for `child_process` / `exec(`.** **Pattern:** Textual pattern match. **Rejected** — false positives on strings, comments, and unrelated identifiers; no scope awareness (cannot tell an import alias from a property access); no reliable path/criticality association.

## Decision

Adopt **Option B.** Ship `RuntimeShellInvocationProbe` at `plugins/distroless-migration--node--npm/probes/runtime_shell_invocation_probe.py` — Layer C, `tier="task_specific"`, `heaviness="light"`, static, plugin-internal per [ADR-0005](0005-probes-live-under-plugin-not-core-tree.md), registered via `@register_probe`, obeying the frozen Probe ABC ([production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)).

The probe walks JS/TS sources via the **existing** `grammars.lock.language_for("javascript" | "typescript")` grammars — **no `tree-sitter-bash`, no new grammar wheel.** A module-level `Final` query catalog enumerates the shell-out forms (`child_process.exec`, `child_process.execSync`, `child_process.spawn`, `Bun.spawn`, `Deno.run`); detection is catalog-driven, not branching.

Each hit emits a typed record carrying:

- the file path,
- `argv[0]` — the literal first argument where statically resolvable, else the sentinel `dynamic`,
- `criticality ∈ {blocking, advisory}` derived from path: `src/**` is `blocking`; `tests/**` and `*.test.*` / `*.spec.*` are `advisory` (this closes G12 — test-infra shell-out must not block a valid production migration).

Because distroless has no `/bin/sh` at runtime, any `blocking` hit whose `argv[0]` is outside the safe set `{node, npm, yarn}` triggers the typed refusal `RefusedRuntimeShellOutInProductionCode` ([ADR-0025](0025-migration-refusal-taxonomy.md)), with the source location in the structured payload. A `blocking` hit with a `dynamic` `argv[0]` is also a refusal — an unresolvable invocation target cannot be cleared statically.

## Tradeoffs

| Gain | Cost |
|---|---|
| Static analysis covers every code path, including cold error branches a dynamic trace would miss — completeness, the property that matters for "ships broken" | Static analysis cannot resolve fully dynamic `argv[0]` (computed command strings); these become `dynamic` → refusal, which is conservative but may refuse a case a human could clear |
| Reuses the existing `javascript`/`typescript` grammars — zero new runtime deps, honoring Amendment A §A.3 departure #3 | TSX / JSX, Bun and Deno dialects are covered only insofar as the JS/TS grammars parse them; exotic syntax may parse-fail and is reported as `low` confidence rather than silently skipped |
| Path-derived `criticality` closes the G12 false-negative — test fixtures that shell out are `advisory`, never blocking | The `src/**` vs `tests/**` split is a convention; a project that puts production code under `tests/` or test code under `src/` is misclassified — mitigated by emitting the path so a reviewer can see the basis |
| `argv[0]` allowlist `{node, npm, yarn}` lets a self-invoking process (`spawn('node', ...)`) pass — distroless ships `node` — without a blanket refusal | The allowlist is a small `Final` set; broadening it (e.g. a project that legitimately spawns a bundled binary) needs an ADR amendment |
| Plugin-internal placement keeps the probe off the core tree per [ADR-0005](0005-probes-live-under-plugin-not-core-tree.md); future task classes follow the same shape | Another probe spread across the plugin tree; mitigated — `make check`'s registry test enumerates it regardless of location |

## Pattern fit

Implements **static AST analysis with a data-driven query catalog** — the shell-out forms are a module-level `Final` tuple iterated against tree-sitter query results, mirroring `_REFLECTION_QUERIES` in the Layer B Node-reflection probe. Instantiates **Plugin / Registry** ([ADR-0005](0005-probes-live-under-plugin-not-core-tree.md)) and the frozen Probe ABC ([production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)). The `criticality` and `argv[0]`-sentinel fields are sum-typed, not stringly-typed; the refusal path feeds the closed `RemediationOutcome.PendingHumanReview` variant set ([ADR-0025](0025-migration-refusal-taxonomy.md)) — refuse with typed evidence, never ship broken.

## Consequences

- `plugins/distroless-migration--node--npm/probes/runtime_shell_invocation_probe.py` is a net-new file; its sub-schema `plugins/distroless-migration--node--npm/schema/runtime_shell_invocation.schema.json` is net-new (`additionalProperties: false` at every node).
- The envelope schema gains one `$ref`; the plugin loader gains one additive import line — both enumerated in [ADR-0029](0029-amend-byte-edit-allowlist-for-amendment-a.md).
- The probe emits `RuntimeShellInvocationSlice`; the recipe and `MigrationConfidence` aggregator consume it.
- A `blocking` hit outside `{node, npm, yarn}`, or any `blocking` hit with `dynamic` `argv[0]`, produces `RefusedRuntimeShellOutInProductionCode` ([ADR-0025](0025-migration-refusal-taxonomy.md)).
- Golden fixtures cover: a `src/**` `execSync('curl ...')` (refusal), a `tests/**` `execSync('git ...')` (advisory, no refusal), a `src/**` `spawn('node', ...)` (allowed), and a `dynamic` `argv[0]` (refusal).

## Reversibility

**Medium.** The probe `name` and `RuntimeShellInvocationSlice` shape are the contract downstream consumers bind to; relocating the source file preserves it. The query catalog and the `{node, npm, yarn}` allowlist are data — tuning them is a one-file change plus golden-fixture updates. Reversing the **policy** — for example, abandoning the `src/**`/`tests/**` criticality split — would re-open the G12 false-negative and require re-validating every prior migration's refusal record, so the discipline itself is harder to undo than the code.

## Evidence / sources

- `../final-design.md §Amendment A §A.2` (gaps G4, G12), §A.3 departure #3 (`tree-sitter-bash` deliberately not added)
- `../phase-arch-design.md §Component design — Amendment A §18`
- [ADR-0002 — ShellInvocationTraceProbe runs in micro-VM](0002-shell-invocation-trace-probe-runs-in-microvm.md) (build-time trace, the gap this complements)
- [ADR-0005 — Probes live under the plugin, not the core tree](0005-probes-live-under-plugin-not-core-tree.md)
- [ADR-0025 — Refusal taxonomy `PendingHumanReview` variants](0025-migration-refusal-taxonomy.md)
- [production ADR-0007 — Probe contract preserved POC→service](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)
