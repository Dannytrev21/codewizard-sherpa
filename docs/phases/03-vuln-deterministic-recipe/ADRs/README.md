# Phase 3 — Vuln remediation: deterministic recipe path: ADRs

Architecture Decision Records for Phase 3, in Nygard format. Each ADR captures one load-bearing decision: the context, the alternatives considered, what was chosen, the tradeoffs accepted, the consequences, and how reversible the choice is.

**Phase architecture:** [phase-arch-design.md](../phase-arch-design.md) — full architecture spec.
**Source design:** [final-design.md](../final-design.md) — synthesized from three competing lens designs.
**Critique:** [critique.md](../critique.md) — devil's-advocate findings that shaped many of these decisions.
**Production reference:** [docs/production/adrs/](../../../production/adrs/) — the project-level ADR set this phase composes with.
**Prior phases:** [Phase 0 ADRs](../../00-bullet-tracer-foundations/ADRs/) · [Phase 1 ADRs](../../01-context-gather-layer-a-node/ADRs/) · [Phase 2 ADRs](../../02-context-gather-layers-b-g/ADRs/) — the spine these decisions extend.

## Index

| # | Title | Tags |
|---|---|---|
| [0001](0001-transform-recipe-engine-two-abc-contract.md) | Phase 3 introduces exactly two public ABCs — `Transform` and `RecipeEngine` — and no `Validator` ABC | contract · abc · extension-by-addition · synthesizer-departure · phase-3-foundation |
| [0002](0002-two-new-top-level-packages-transforms-recipes.md) | Two new top-level packages (`transforms/`, `recipes/`); `cve/` and `validation/` fold under `transforms/` | package-layout · extension-by-addition · scope-discipline · synthesizer-departure |
| [0003](0003-recipe-engine-ncu-default-openrewrite-stub-registered.md) | Ship two recipe engines — `NcuRecipeEngine` (default) and `OpenRewriteEngineStub` (registered, opt-in, JVM-gated) | recipe-engine · openrewrite · ncu · synthesizer-departure · phase-15-anchor · roadmap-fit |
| [0004](0004-recipe-selection-structured-triple-not-optional.md) | `RecipeSelection` is a structured `(recipe, reason, diagnostics)` triple — not `Optional[Recipe]` | contract · phase-4-handoff · diagnostic-signal · synthesizer-departure |
| [0005](0005-single-sandbox-profile-test-execution-overlay-signal-escalate.md) | One sandbox profile + `test_execution=True` overlay flag; `--network=none` default with `gate.signal_escalate` for network-needing tests | sandbox · chokepoint-preservation · validation-gate · synthesizer-departure · phase-5-handoff |
| [0006](0006-retry-deferred-to-phase-5-transient-io-exception.md) | No retry inside the Phase 3 orchestrator; transient-I/O retry only inside `LockfileResolver` | retry · escalation · linear-orchestrator · phase-5-handoff · scope-discipline |
| [0007](0007-lockfile-policy-scanner-graded-allow-policy-violations.md) | `LockfilePolicyScanner` is a fact-emitting validator with a graded `--allow-policy-violations` escape valve; widening retry deferred to Phase 5 | lockfile-policy · supply-chain · facts-not-judgments · synthesizer-departure · phase-5-handoff |
| [0008](0008-cve-feed-integrity-content-hash-best-effort-signature-graded-staleness.md) | CVE feed integrity — content-hash gate, best-effort signature, graded staleness advisory (7d warn / 30d low-confidence / 90d refuse) | cve · supply-chain · staleness · synthesizer-departure · phase-14-handoff |
| [0009](0009-cve-retraction-probe-evidence-stale-marker.md) | Ship `CveRetractionProbe` in Phase 3 (under `transforms/cve/`) to mark prior remediations as `evidence_stale` when CVEs are withdrawn | cve · retraction · audit · synthesizer-addition · phase-14-handoff · probe-shaped-but-not-probe |
| [0010](0010-audit-chain-extension-cache-replay-event.md) | Phase 3 extends the Phase 2 BLAKE3 audit chain with new event types; cache hits emit `cache.replay` referencing the original chain head | audit · chain · cache-replay · phase-2-extension · tamper-evidence |
| [0011](0011-lockfile-canonicalization-and-npm-digest-pin-for-deterministic-diffs.md) | Lockfile canonicalization (`LC_ALL=C`, top-level key sort, LF endings) + pinned `npm` digest for byte-deterministic diffs; `recipes/digests.yaml` for recipe immutability | determinism · canonicalization · digest-pinning · synthesizer-addition · recipe-versioning |
| [0012](0012-test-fixture-bundle-plus-resolution-plus-pinned-mirror.md) | Test fixtures = `.bundle` + recorded `npm-resolution.json` + pinned local registry mirror; quarterly rotation policy | test-fixtures · registry-drift · determinism · synthesizer-departure · phase-evolution |
| [0013](0013-confidence-strict-and-of-binary-signals-no-llm.md) | Phase-3 confidence is the strict-AND of binary objective signals; no LLM and no human-merge in this phase | confidence · trust-score · facts-not-judgments · human-handoff · phase-3-floor |
| [0014](0014-allowed-binaries-additions-npm-ncu-java.md) | Add `npm`, `ncu`, and `java` (opt-in) to `ALLOWED_BINARIES`; extend `tools/digests.yaml` for each | allowlist · tool-use · supply-chain · phase-3-tools · synthesizer-mechanical |

## Conventions

- **Filenames** are `NNNN-kebab-case-title.md` with zero-padded four-digit numbers, numbered locally per phase starting at 0001.
- **Numbers are immutable** — a superseded ADR keeps its number; the new one gets the next number and cross-links.
- **Cross-references** to production ADRs use `../../../production/adrs/NNNN-*.md`. Cross-references to other phase ADRs use the relative filename inside this folder. Cross-references to Phase 0/1/2 ADRs use `../../00-bullet-tracer-foundations/ADRs/NNNN-*.md`, `../../01-context-gather-layer-a-node/ADRs/NNNN-*.md`, `../../02-context-gather-layers-b-g/ADRs/NNNN-*.md`.
- **The phase-arch-design and final-design documents are the architecture contract**; ADRs are the durable rationale. When the two diverge, the ADR is the *why* and the arch doc is the *what*.

## What got an ADR

These decisions met the bar — a real choice with viable alternatives, load-bearing on Phase 3 implementation or Phase 4+ interfaces, durable enough that a future reader benefits from rationale before changing them.

The 15-row conflict-resolution table and seven "Departures from all three inputs" in `final-design.md "Synthesis ledger"` surfaced the ADR candidates; the set was consolidated to 14 ADRs covering:

- **Public contract surface** — two-ABC commitment (0001), package layout (0002), `RecipeSelection` triple (0004). Each fixes a downstream-phase consumption surface (Phase 4 reads `reason`; Phase 7 adds transforms; Phase 15 authors recipes).
- **Recipe-engine decision (the most consequential phase-3 choice per the critic)** — `ncu` default + `OpenRewriteEngineStub` (0003). Honors the roadmap's named OpenRewrite seat while bounding operational burden.
- **Sandbox and gate posture** — single profile + test-execution overlay + signal-escalate (0005). Resolves the three-way design fight (P fast-path / S two profiles HARD / B no sandbox) with the critic's recommended single-profile-plus-overlay.
- **Retry and escalation discipline** — defer retry to Phase 5; transient I/O retry only in lockfile resolver (0006). Closes the retry-layer collision the critic flagged in performance-first and security-first.
- **Lockfile-policy posture** — graded `--allow-policy-violations` (0007). Softens security-first's HARD non-retryable per critic recommendation; preserves the fact-emitting discipline.
- **CVE supply-chain integrity** — content-hash + best-effort signature + graded staleness (0008), `CveRetractionProbe` (0009). Closes the critic's "all three missed retraction" blind spot and softens security-first's key-rotation brittleness.
- **Audit chain extension** — Phase-2 BLAKE3 chain extended with Phase-3 event types; cache-replay back-reference (0010). Closes the cache-vs-audit consistency gap the critic flagged in performance-first.
- **Determinism mechanisms** — lockfile canonicalization + `npm` minor-digest pin + `recipes/digests.yaml` (0011), three-part test fixtures (0012). Address the "all three quietly assumed `npm` is deterministic" blind spot.
- **Confidence model and Phase-3 boundary** — strict-AND signal set, no-LLM fence extension to `transforms/`/`recipes/`, human-handoff fidelity at the local-branch boundary (0013). Cements `production ADR-0005`, `0008`, `0009` for Phase 3.
- **Tool allowlist extension** — `npm`, `ncu`, `java` opt-in (0014). Follows the Phase 2 ADR-0005 per-binary-named precedent.

## Decisions noted but not yet documented

Surfaced during ADR extraction as plausibly worth ADR-ing, but the documentation in `final-design.md` and `phase-arch-design.md` doesn't develop them enough to write a confident ADR. Flagged for the implementer / next-phase author:

- **Skills schema additive field `applies_to.cve_patterns` (defaults to `["*"]`)** (`final-design.md §"Roadmap coherence check" §"New ADRs implied"` ADR-P3-010; `phase-arch-design.md §"Component design" #3`). The additive-field discipline is contained inside ADR-0001's "append-only Transform ABC" policy and Phase 2 ADR-0008's "closed-enum CI lint" precedent. A dedicated ADR was deferred as a mechanical schema extension; the implementer should surface one if a second `applies_to.<task_pattern>` field is requested before Phase 7 (which would establish the "every task class gets its own axis" pattern).

- **Branch naming convention** (`codegenie/vuln-fix/<cve-id>-<short-sha>`) (`final-design.md §"Goals" §"Trust & safety goals"` #12; `§"Synthesis ledger"` row "Branch naming"). All three designs converged with minor variants; the synth picked best-practices' `vuln-fix/<cve>-<sha>`. A dedicated ADR was deferred — the convention is documented in `phase-arch-design.md §"Component design" #13 "PatchBranchWriter"` and Phase 11's PR-opening ADR will compose with it. If short-sha collisions surface in practice (vanishingly rare per the design), an amendment to Phase 11's ADRs captures the resolution.

- **Per-event payload schemas for the Phase-3 audit events** (ADR-0010 lists the events; full payloads are in `phase-arch-design.md §"Data model" §"Audit event payload extensions"`). The event vocabulary is closed by ADR-0010; the per-event Pydantic models are mechanical and live in code. A dedicated ADR was deferred unless one event grows non-trivial cross-phase consumer contracts (likely `gate.signal_escalate` or `escalation.policy_violation` when Phase 5/11 land their consumer contracts).

- **`auto_gather` recursion semantics and exit 9** (`phase-arch-design.md §"Gap analysis" §"Gap 7"`). The hard-precondition-failure exit and audit-chain-no-break behavior are documented; a dedicated ADR was deferred as the orchestration of "Phase 3 invokes Phase 0/1/2 gather in-process" is an integration concern, not an architectural decision.

- **Engine-availability snapshot at orchestrator entry** (`phase-arch-design.md §"Gap analysis" §"Gap 6"`). The snapshot pattern (capture once, read from snapshot) is documented; the cross-Activity flux concern is purely Phase-9 (Temporal) territory. A dedicated ADR was deferred — the pattern is contained inside ADR-0003 and ADR-0004 (which read the snapshot for engine selection).

- **Network-required test signature scan pattern set** (`final-design.md §"Open questions"` #3; ADR-0005 references the initial set). The pattern set is tunable; ADR-0005 commits to the *mechanism*. If the set grows past one screen of patterns or develops cross-phase consumer contracts, an ADR amendment captures the policy.

- **OpenRewrite stub recipe choice** (`final-design.md §"Open questions"` #1). The implementer may roll a minimal internal recipe under the same engine contract if the npm OpenRewrite ecosystem is too thin. ADR-0003 commits to *registering* the engine and shipping one recipe; the specific recipe is an implementation decision and gets an ADR only if the choice has cross-phase implications.

- **`npm-resolution.json` recording mechanism for fixtures** (`final-design.md §"Open questions"` #2). Convention TBD between `npm install --json --package-lock-only` and a custom canonical extract. ADR-0012 commits to the *file*; the exact format is an implementation decision and gets an ADR only if there's a cross-phase impact.

- **CVE-feed snapshot-staleness threshold calibration** (`final-design.md §"Open questions"` #4). The 7/30/90-day defaults are committed in ADR-0008. If operator feedback in Phase 4+ requires adjustment, an amendment to ADR-0008 captures the choice.
