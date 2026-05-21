# ADR-0025: Migration refusal is a closed typed taxonomy of `RemediationOutcome.PendingHumanReview` variants, each carrying source-location evidence

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** refusal-as-outcome · sum-types · make-illegal-states-unrepresentable · amendment-a · §22 · G5 · M2
**Related:** [0009](0009-phase-7-byte-edit-allowlist-fence.md), [0018](0018-dockerfile-secret-pattern-probe.md), [0021](0021-runtime-shell-invocation-probe.md), [0026](0026-migration-confidence-aggregation.md), [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md), [Phase 3 ADR-0010](../../03-vuln-deterministic-recipe/ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md), [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md)

## Context

`final-design.md §Amendment A §A.1` sets the governing principle: for every migration it attempts, Phase 7 must either **gather enough context to transform the case correctly**, or **refuse with typed evidence** naming the exact source location. Shipping a broken image — one that builds clean, passes the gate, merges, then `ENOENT`s at runtime — is the single unacceptable outcome.

Refusal must therefore be a *first-class outcome*, not an error and not a silent skip. When the recipe (`DockerfileBaseImageSwapTransform` / `DockerfileMultiStageRefactorTransform`) hits a case it cannot transform deterministically — an opaque `COPY`'d secret-acquisition script, a runtime `child_process.exec` in `src/**`, an unclassified native module, a non-deterministic entrypoint, an architecture loss, an external-registry base image — refusing *with evidence* is cheaper than shipping a diff and rolling it back in production.

Phase 3 already ships `RemediationOutcome` in `src/codegenie/transforms/outcomes.py` with a `PendingHumanReview` arm. Amendment A's gap M2 (`final-design.md §A.2`) and `phase-arch-design.md §Component design — Amendment A §22` require that arm to become a *closed typed taxonomy* rather than a free-text reason. Gap G5 (shell-form `ENTRYPOINT`/`CMD`) also lands here: deterministic rewrites are applied, non-deterministic ones refuse via a named variant.

## Options considered

- **Option A — A generic `PendingHumanReview(reason: str)` carrying a free-text string.** Simple, no schema growth. **Pattern:** Stringly-typed escape hatch. **Rejected** — neither the policy gate, the `MigrationConfidence` aggregator ([0026](0026-migration-confidence-aggregation.md)), nor the human operator can reason about a free-text reason; `match` cannot be exhaustive over `str`; the PR description cannot render a structured source location; two probes refusing "the same way" drift to two different strings.
- **Option B — A closed set of typed `PendingHumanReview` variants, each with a structured source-location payload.** **Pattern:** Make illegal states unrepresentable + exhaustive sum-type matching (`match`/`assert_never`). The variant set is closed at the type level; the compiler/type-checker forces every consumer to handle every case.
- **Option C — Raise exceptions for un-transformable cases and let the orchestrator's `except` clause convert them.** **Pattern:** Errors-as-control-flow. **Rejected** — refusal is a *valid, expected* outcome of a correct run, not a crash; modelling it as an exception conflates "the recipe declined" with "the recipe broke," loses the structured payload through the `traceback`, and tempts a broad `except` that swallows real bugs.

## Decision

Adopt **Option B.** Add a closed set of refusal variants to `RemediationOutcome.PendingHumanReview` in `src/codegenie/transforms/outcomes.py` (an ADR-gated additive byte-edit to a Phase 3 file — enumerated in [ADR-0029](0029-amend-byte-edit-allowlist-for-amendment-a.md)'s allowlist amendment, row 5):

- `RefusedOpaqueSecretScript` — a `COPY`'d shell script is then `RUN`; the probe does not parse the script ([ADR-0018](0018-dockerfile-secret-pattern-probe.md), no `tree-sitter-bash`), so the secret-acquisition path cannot be preserved deterministically.
- `RefusedRuntimeShellOutInProductionCode` — a `blocking` `RuntimeShellInvocationProbe` hit ([ADR-0021](0021-runtime-shell-invocation-probe.md)) in `src/**` with `argv[0]` outside `{node, npm, yarn}`; distroless has no `/bin/sh` at runtime.
- `RefusedNativeModulesUnclassified` — `binding.gyp` / `*.node` present but a build-toolchain package is absent from the `apk`/`apt` classification catalog, so the multi-stage split cannot be computed.
- `RefusedNonDeterministicEntrypoint` — shell-form `ENTRYPOINT`/`CMD`, `npm start`, or an env-substituted `CMD` that cannot be deterministically rewritten to exec-form (gap **G5**).
- `RefusedArchitectureLoss` — the source supports an architecture (e.g. `armv7`) the recommended Chainguard image does not.
- `RefusedExternalRegistryBaseImage` — the base image is from a non-public / mirror registry the migration cannot resolve or attest against.

Each variant carries a structured source-location payload: the file path and the line / Dockerfile-instruction index that triggered the refusal. The set is **closed** — adding a variant is an ADR amendment to this document. Every consumer (recipe, policy gate, `MigrationConfidence` aggregator, PR-description renderer) dispatches with `match` and a final `case _: assert_never(...)` so a new variant is a type error until every consumer is updated.

**Gap G5 — shell-form `ENTRYPOINT`/`CMD`.** The recipe transformation contract applies *deterministic* rewrites where the form is unambiguous (`CMD node server.js` → `CMD ["node", "server.js"]`); cases that cannot be deterministically rewritten (`npm start`, `sh -c "$START_CMD"`, env-substituted argv) refuse via `RefusedNonDeterministicEntrypoint` rather than guessing.

## Tradeoffs

| Gain | Cost |
|---|---|
| Refusal is a first-class, typed outcome — the validator, the `MigrationConfidence` aggregator, and the operator all reason about a discrete variant, not a string | Six new variant classes plus their payloads grow `outcomes.py`; the byte-edit is ADR-gated ([0029](0029-amend-byte-edit-allowlist-for-amendment-a.md)) and reviewed |
| `match`/`assert_never` makes "a consumer forgot to handle a refusal" a type error, not a production surprise | Every new consumer of `PendingHumanReview` must handle all six cases; adding a seventh variant is a coordinated edit across consumers — the explicit cost of a closed taxonomy |
| The structured source-location payload renders directly into the PR description — the human sees *which line* the recipe declined on | The payload shape (file + line/instruction index) is a small contract; a probe that wants to refuse with richer evidence needs an ADR amendment |
| Refusing is cheaper than shipping-and-rolling-back: a typed refusal costs one PR-less run; a broken merge costs a production incident | A migration that *could* have been transformed with more gather depth refuses instead — accepted: gather depth grows by ADR (Amendment A), refusal is the honest floor |

## Pattern fit

Implements **make-illegal-states-unrepresentable** (toolkit §Types — a free-text reason admits states no consumer can handle; a closed variant set admits only the six the system understands) and **exhaustive sum-type matching** (`match` + `assert_never`, mirroring the seven-variant `Provenance` union and `MigrationConfidence`'s `High | Degraded | Refused` rollup — [ADR-0026](0026-migration-confidence-aggregation.md)). Refusal-as-outcome mirrors [Phase 3 ADR-0010](../../03-vuln-deterministic-recipe/ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md)'s universal-HITL refuse mode and honors "Facts, not judgments" (CLAUDE.md) — the probe reports evidence, the recipe reports a typed decline, the human decides. The variant set is **data-shaped discipline**: closed at the type, extended by ADR.

## Consequences

- `src/codegenie/transforms/outcomes.py` gains six `PendingHumanReview` variants with structured source-location payloads — enumerated in [ADR-0029](0029-amend-byte-edit-allowlist-for-amendment-a.md) row 5.
- The recipe (`DockerfileBaseImageSwapTransform`, `DockerfileMultiStageRefactorTransform`) is no longer "always produces a diff" — it produces a diff *or* a typed refusal (`final-design.md §A.3 departure #2`). Stories S10-01/S10-02/S10-03 have their acceptance criteria amended.
- `RefusedNonDeterministicEntrypoint` closes gap G5: the recipe rewrites deterministic shell-form `CMD`/`ENTRYPOINT` and refuses the rest.
- A property test asserts every `PendingHumanReview` variant carries a non-empty source-location payload; an exhaustiveness test asserts a synthetic seventh variant breaks `mypy --strict` at every consumer.
- A goldens fixture per variant locks the operator-readable refusal shape across changes.
- Adding a seventh refusal variant requires an ADR amendment to this document plus a fence-allowlist row only if it touches an existing file beyond `outcomes.py`.

## Reversibility

**Medium.** The six variants become a contract the recipe, policy gate, aggregator, and PR renderer all `match` on; collapsing the taxonomy back to a free-text reason would force every consumer to migrate and would lose the source-location payload Phase 8's Planner expects. Adding a variant is straightforward (ADR amendment + additive class). Restructuring the payload shape is a coordinated edit but does not break Phase 7's structure.

## Evidence / sources

- `../final-design.md §Amendment A §A.1` (governing principle — gather-or-refuse), §A.2 gap M2 + gap G5, §A.3 departure #2 (the recipe gains the ability to refuse)
- `../phase-arch-design.md §Component design — Amendment A §22` (refusal taxonomy — the six variants + structured payload), §15/§18 (the probes that trigger `RefusedOpaqueSecretScript` / `RefusedRuntimeShellOutInProductionCode`)
- `src/codegenie/transforms/outcomes.py` — Phase 3's `RemediationOutcome` / `PendingHumanReview` (the extension point)
- [Phase 7 ADR-0009 — byte-edit allowlist fence](0009-phase-7-byte-edit-allowlist-fence.md) and [ADR-0029](0029-amend-byte-edit-allowlist-for-amendment-a.md) (the ADR-gated additive edit to `outcomes.py`)
- [Phase 3 ADR-0010 — domain-modeling discipline (scope sum type + newtypes)](../../03-vuln-deterministic-recipe/ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md) (precedent: refusal as a first-class outcome)
- [production ADR-0009 — humans always merge](../../../production/adrs/0009-humans-always-merge.md)
- CLAUDE.md "Load-bearing architectural commitments — Facts, not judgments; Honest confidence"
