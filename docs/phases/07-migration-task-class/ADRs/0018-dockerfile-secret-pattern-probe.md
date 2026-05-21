# ADR-0018: `DockerfileSecretPatternProbe` inventories source-side secret acquisition; `COPY`'d external scripts are classified opaque and refused, not parsed

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** amendment-a · probe · secret-acquisition · open-closed · refusal-honesty
**Related:** [0005](0005-probes-live-under-plugin-not-core-tree.md), [0009](0009-phase-7-byte-edit-allowlist-fence.md), [0025](0025-migration-refusal-taxonomy.md), [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)

## Context

Amendment A (`../final-design.md §Amendment A §A.2`, Gap G1) found the gather pipeline does not inventory how the source repo acquires secrets *during the build*. A naive `FROM` swap can silently drop a `--mount=type=secret`, an `ARG`-injected token, a `COPY .npmrc`, an auth-header `curl`, or a `COPY`'d credential-fetching script — the image then builds clean, passes `DockerfilePolicyGate`, merges, and 500s in production when the secret path is gone. The original `ShellInvocationTraceProbe` ([0002](0002-shell-invocation-trace-probe-runs-in-microvm.md)) observes shell *during* the build but never classifies *what kind of* secret acquisition the `Dockerfile` performs.

The hard case is a `COPY`'d shell script that is then `RUN`. Parsing that script to recover its secret behaviour would require adding a `tree-sitter-bash` grammar to the runtime closure — a new supply-chain surface — and the script's behaviour is non-deterministic anyway (it reads env, branches on host state). `final-design.md §Amendment A §A.3 ¶3` is explicit: `tree-sitter-bash` is deliberately NOT added.

## Options considered

- **Option A — Add `tree-sitter-bash` and parse the `COPY`'d scripts to recover their secret behaviour.** **Pattern:** Deep static analysis via grammar. **Rejected** — a new grammar dependency widens the supply-chain surface the `fence` job guards, and an opaque host-state-dependent script cannot be transformed deterministically even if parsed. Effort buys nothing the recipe can act on.
- **Option B — Detect + classify + refuse: AST-walk the `Dockerfile`, classify each secret-acquisition instruction into a closed `kind` set, and record a `COPY`'d-then-`RUN` script as `external_script` = opaque without parsing it.** **Pattern:** Inventory-and-refuse; opaque-input quarantine.
- **Option C — Ignore source-side secrets; let the recipe swap `FROM` and trust the build gate.** **Pattern:** Optimistic transform. **Rejected** — ships images that build clean and 500 in production when the secret path vanishes; this is the one unacceptable outcome named in `§A.1`.

## Decision

Adopt **Option B.** Ship `DockerfileSecretPatternProbe` at `plugins/distroless-migration--node--npm/probes/dockerfile_secret_pattern_probe.py` — Layer C, `tier="task_specific"`, `heaviness="light"`, static, `cache_strategy="content"`, `declared_inputs=["**/Dockerfile", "**/Dockerfile.*", "**/Containerfile"]`. It obeys the frozen Probe ABC ([production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)), registers via `@register_probe`, and lives under the plugin per [0005](0005-probes-live-under-plugin-not-core-tree.md).

The probe AST-walks the `Dockerfile` via `dockerfile-parse` and emits `SecretPatternSlice` — an ordered tuple of typed `SecretPattern` records, each tagged `kind ∈ {buildkit_secret_mount, env_arg_injection, file_copy_credential, auth_header_fetch, external_script}` with the instruction index and the referenced env var / path. Classification is data, not branching code: a module-level `_SECRET_PATTERN_RULES: Final[tuple[SecretRule, ...]]` open/closed catalog reuses the Phase 2 sanitizer's secret-shaped-name regexes.

A `COPY`'d shell script that is subsequently `RUN` is classified `external_script` = **opaque**: the probe records the invocation and the script path but does **not** parse the script. The recipe later REFUSES on any opaque record via `RefusedOpaqueSecretScript` ([0025](0025-migration-refusal-taxonomy.md)); it rewrites `env_arg_injection` into a portable `--mount=type=secret` form only where deterministic.

## Tradeoffs

| Gain | Cost |
|---|---|
| Source-side secret acquisition is inventoried before the recipe runs; a dropped secret path becomes a typed refusal, not a production 500 | One more plugin probe in the gather wave; mitigated by `heaviness="light"` and a pure static `dockerfile-parse` pass — no build, no network |
| `tree-sitter-bash` stays out of the runtime closure — the `fence` job's supply-chain surface is unchanged | Opaque scripts are refused rather than transformed; some migrations a human could do by hand are escalated to HITL. Honest: the recipe cannot do them deterministically anyway |
| `_SECRET_PATTERN_RULES` is an open/closed catalog reusing the Phase 2 sanitizer regexes — new secret shapes are one tuple row, no edit to walk logic | The catalog must stay in sync with the sanitizer's regexes; a shared-constant import keeps them single-sourced |
| `external_script` quarantine makes "we could not see inside this" a first-class, evidenced outcome | Engineers must learn that an `external_script` finding is a refusal trigger, not a warning — documented in the plugin's recipe contract |

## Pattern fit

Instantiates **Open/Closed via data catalog** (CLAUDE.md §Open/Closed seams — module-level `Final` tuples iterated, never branched on): `_SECRET_PATTERN_RULES` is the marker catalog; adding a secret shape is a row. Instantiates **Plugin-contributed probe** ([0005](0005-probes-live-under-plugin-not-core-tree.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)). Instantiates **Opaque-input quarantine / refusal honesty** (`§A.1` governing principle): an input the probe cannot deterministically reason about is classified, recorded, and refused — never optimistically transformed.

## Consequences

- `plugins/distroless-migration--node--npm/probes/dockerfile_secret_pattern_probe.py` is a net-new file; its sub-schema `.../schema/dockerfile_secret_pattern.schema.json` (`additionalProperties: false` at every node) is net-new.
- The envelope `src/codegenie/schema/repo_context.schema.json` gains one `$ref`; `src/codegenie/plugins/loader.py` gains one additive import line — both authorized by the [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md) byte-edit allowlist amendment to [0009](0009-phase-7-byte-edit-allowlist-fence.md).
- `src/codegenie/transforms/outcomes.py` gains the `RefusedOpaqueSecretScript` variant ([0025](0025-migration-refusal-taxonomy.md)); the recipe `match`es it exhaustively.
- Golden fixtures land under `tests/golden/probes/dockerfile_secret_pattern/`, including a `COPY`'d-script-then-`RUN` fixture asserting the `external_script` classification and the absence of any script-content parsing.
- Implemented in Amendment A Step 13 (`../final-design.md §A.2`, Gap G1; `High-level-impl.md` Step 13).

## Reversibility

**Medium.** The probe `name` and `SecretPatternSlice` shape are the load-bearing contract the recipe consumes by slice name; relocating or rewriting the probe internals is cheap. Reversing the **policy** — choosing to parse opaque scripts — would force `tree-sitter-bash` into the runtime closure and a `fence`-job amendment, a multi-component change.

## Evidence / sources

- `../final-design.md §Amendment A §A.2` (Gap G1), `§A.3 ¶3` (`tree-sitter-bash` deliberately not added)
- `../phase-arch-design.md §Component design — Amendment A §15` (`DockerfileSecretPatternProbe`)
- [0005 — Probes live under the plugin, not the core tree](0005-probes-live-under-plugin-not-core-tree.md)
- [0025 — Migration refusal taxonomy](0025-migration-refusal-taxonomy.md)
- [production ADR-0007 — Probe contract preserved POC to service](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)
