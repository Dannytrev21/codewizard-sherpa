# ADR-0023: `RuntimeCompatProbe` folds uid/PID-1/filesystem/locale assumptions into one advisory probe

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** amendment-a · advisory-probe · honest-confidence · gather-or-refuse · open-closed
**Related:** [0005](0005-probes-live-under-plugin-not-core-tree.md), [0021](0021-runtime-shell-invocation-probe.md), [0025](0025-migration-refusal-taxonomy.md), [0026](0026-migration-confidence-aggregation.md), [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)

## Context

Amendment A's governing principle (`../final-design.md §Amendment A §A.1`) is that Phase 7 must, for every migration, either **gather enough context to transform correctly** or **refuse with typed evidence** — shipping a broken image is the one unacceptable outcome. Gaps G7–G10 (`../final-design.md §Amendment A §A.2`) catalogue four runtime-environment hazard families that a naive `FROM` swap silently breaks because the Chainguard distroless target runs as `nonroot` (uid 65532) with a minimal filesystem:

- **G7 — uid/user delta.** Source builds as root; the target is `nonroot`. `COPY` without `--chown`, writes outside `$HOME`/`/tmp`, and privileged `EXPOSE` < 1024 all fail post-migration.
- **G8 — PID-1/signal handling.** An app with no `SIGTERM` listener, run as PID 1, gets a slow (kill-timeout) shutdown instead of a graceful drain.
- **G9 — filesystem assumptions.** Literal-path `fs.readFile` of `/etc/passwd`, `/etc/timezone`, or `/tmp` assumes a full base image; distroless trims these.
- **G10 — locale/timezone.** `process.env.TZ` and ICU-dependent dependencies assume locale data the distroless image may not carry.

Unlike G1/G4 (which can produce typed *refusals*), G7–G10 are mostly **non-deterministic to auto-fix** — whether a missing `--chown` matters depends on what the app writes, and a missing `SIGTERM` handler is a code change no recipe can author safely. The design question is how to surface them: as their own probes, folded into one, or not at all. `../phase-arch-design.md §Component design — Amendment A §20` resolves them into a single `RuntimeCompatProbe` with a WARN disposition.

## Options considered

- **Option A — Four separate probes, one per hazard family** (`UserUidProbe`, `Pid1SignalProbe`, `FilesystemAssumptionProbe`, `LocaleTzProbe`). **Pattern:** One probe per concern. **Rejected** — over-fragmented for findings that are uniformly advisory: 4× the registry dispatch, 4× the JSON sub-schema + `$ref` wiring, 4× the fence allowlist rows (ADR-0029), 4× the golden-fixture directories — with no behavioural payoff, since none of the four can refuse and none gates.
- **Option B — One combined `RuntimeCompatProbe` with findings grouped by family** (`user_uid | pid1_signals | filesystem | locale_tz`). **Pattern:** Cohesive advisory probe + grouped sum-type findings. The four families share one parse pass (`dockerfile-parse` + tree-sitter JS/TS), one slice, one schema, one disposition.
- **Option C — Skip the probe; let the Phase 5 `DistrolessBuildGate` catch runtime breakage.** **Pattern:** Build-gate-as-detector. **Rejected** — a build-gate failure is not actionable: the operator gets "build failed" (or worse, a *passing* build that fails at container runtime, which the build gate never exercises) with no hint as to which of dozens of runtime assumptions broke. WARN-with-source-location is the actionable signal the human merger needs.

## Decision

Adopt **Option B.** Ship one `RuntimeCompatProbe` at `plugins/distroless-migration--node--npm/probes/runtime_compat_probe.py` — Layer C, `tier="task_specific"`, static, plugin-internal per [0005](0005-probes-live-under-plugin-not-core-tree.md). It combines a `dockerfile-parse` pass (for `COPY` without `--chown`, writes outside `$HOME`/`/tmp`, privileged `EXPOSE`) with a tree-sitter JS/TS pass over the existing `javascript`/`typescript` grammars (for literal-path `fs.readFile`, `process.env.TZ`, ICU-dependent deps) — no new grammar, no `tree-sitter-bash`. It emits `RuntimeCompatSlice`: typed findings grouped under `user_uid | pid1_signals | filesystem | locale_tz`, plus the probe's own `confidence: Literal["high","medium","low"]`. The disposition is **WARN** — every finding is surfaced in the PR description (M3); none blocks. The recipe does not refuse on `RuntimeCompatSlice` findings. The human merger decides, because the fixes (add a `SIGTERM` handler, parameterise a hardcoded path) are code changes no deterministic recipe can author.

## Tradeoffs

| Gain | Cost |
|---|---|
| One probe = one registry dispatch, one sub-schema, one `$ref`, one fence row, one golden-fixture dir — 4× cheaper than Option A for findings that are uniformly advisory | The four families are heterogeneous (Dockerfile uid vs JS literal-path); the single probe carries two parsers. Mitigated: both parsers already exist in-tree; the probe is a thin orchestrator over them |
| WARN-with-source-location is actionable — the human merger sees "literal `fs.readFile('/etc/passwd')` at `src/auth.ts:42`" and decides | Advisory findings can be ignored; a real PID-1 hazard may merge unnoticed. Accepted: a recipe cannot author a `SIGTERM` handler safely, and a hard fail on a *maybe*-hazard would block legitimate migrations (cf. [0012](0012-dockerfile-policy-gate-strict-and-no-override.md)'s objective-signal discipline — these signals are not objective enough to gate) |
| Findings grouped by a closed `family` sum type — consumers `match` exhaustively; the PR-description renderer iterates families, never branches on strings | Adding a fifth hazard family is a Phase-7-ADR amendment + a new `family` variant + schema growth. Worth it; mirrors the open/closed marker-catalog discipline (`_BASE_IMAGE_KIND_RULES`) |
| The probe `confidence` feeds the [0026](0026-migration-confidence-aggregation.md) rollup — a `low`-confidence `RuntimeCompatProbe` (e.g. unparseable Dockerfile) degrades `MigrationConfidence` like any other load-bearing probe | `RuntimeCompatProbe` is *advisory* yet its `confidence` is load-bearing for the rollup — the distinction (finding disposition = WARN, but probe health = input to refusal) must be documented so it is not read as a contradiction. Handled here and in [0026](0026-migration-confidence-aggregation.md) |

## Pattern fit

Implements **Plugin-contributed probe** ([0005](0005-probes-live-under-plugin-not-core-tree.md); [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)) — registers via `@register_probe`, obeys the frozen Probe ABC, lives under the plugin's `probes/`. Instantiates **Sum type for grouped findings** (production ADR-0033) — the `family` discriminant is a closed enum, not a string. Honours **Gather-or-refuse, never ship broken** (`../final-design.md §Amendment A §A.1`) by choosing the WARN arm honestly: where a deterministic fix is impossible, the probe gathers evidence and hands the judgement to the human rather than pretending a refusal or a silent auto-fix.

## Consequences

- `plugins/distroless-migration--node--npm/probes/runtime_compat_probe.py` is a net-new file; `plugins/distroless-migration--node--npm/schema/runtime_compat.schema.json` is its sub-schema (`additionalProperties: false` at every node, Phase 1 ADR-0004). Both are allowlisted by [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md).
- The envelope `repo_context.schema.json` gains one `$ref` for `runtime_compat` (allowlisted, [0029](0029-amend-byte-edit-allowlist-for-amendment-a.md)).
- `RuntimeCompatSlice` carries `findings: tuple[RuntimeCompatFinding, ...]`, each tagged `family: Literal["user_uid","pid1_signals","filesystem","locale_tz"]` with a source-location payload (file + line / instruction index), and the probe's `confidence`.
- The probe declares `_WARNING_IDS: Final[frozenset[str]]` (e.g. `runtime_compat.dockerfile_parse_failed`) validated at import via `raise AssertionError(...)`.
- M3's `transformations_applied` / PR-description bundle renders the grouped findings; the recipe never refuses on them.
- `RuntimeCompatProbe.confidence` is a load-bearing input to `aggregate_migration_confidence` ([0026](0026-migration-confidence-aggregation.md)).
- Golden fixtures land under `tests/golden/probes/runtime_compat/` — one fixture per family plus a clean-repo baseline.
- Adding a fifth hazard family requires a Phase-7-ADR amendment, a new `family` variant, and a schema + fixture addition.

## Reversibility

**Medium.** The slice `name` (`runtime_compat`) and the `family` discriminant are the load-bearing contract — the M3 PR-description renderer and any future consumer read findings by family, not by Python import path. Splitting the probe back into four later would change the slice surface (four slice names instead of one) and force every consumer + the TCCM `must_read` list to migrate — a coordinated change, not a free one. Reversing the WARN *disposition* to a refusal would be a sharper change: it would start blocking migrations that ship fine today, and contradicts §A.1's reasoning that these hazards are non-deterministic to fix.

## Evidence / sources

- `../final-design.md §Amendment A §A.1` (governing principle), `§A.2` (G7–G10 row), `§A.4` (in scope)
- `../phase-arch-design.md §Component design — Amendment A §20` (`RuntimeCompatProbe`), `§Amendment A gaps — G1–G17, M1–M3`
- [ADR-0005 — Probes live under the plugin, not the core tree](0005-probes-live-under-plugin-not-core-tree.md)
- [ADR-0021 — `RuntimeShellInvocationProbe` (G4/G12 — the deterministic-refusal sibling)](0021-runtime-shell-invocation-probe.md)
- [ADR-0026 — `MigrationConfidence` aggregation](0026-migration-confidence-aggregation.md)
- [production ADR-0007 — Probe contract preserved POC→service](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)
- [production ADR-0033 — Domain modeling discipline](../../../production/adrs/0033-domain-modeling-discipline.md)
