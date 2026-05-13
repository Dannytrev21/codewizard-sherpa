# Phase 07 — Add migration task class (Chainguard distroless): Final design

**Status:** Design of record (synthesized from three competing designs + critique).
**Synthesized by:** Graph-of-Thought synthesizer subagent
**Date:** 2026-05-12
**Sources:** `design-performance.md` · `design-security.md` · `design-best-practices.md` · `critique.md`
**Supersedes:** the three per-lens drafts above.

---

## Lens summary

The critic was right: **Phase 7 was supposed to *prove* extension-by-addition and the three input designs together prove it doesn't yet hold**. Read against Phase 3/4/5/6's actually-committed contracts, every input design either silently edits a Phase 0–6 file (security's `applies_to_lifecycle` on the `Probe` ABC, security's `TrustGate.register_signal` API that doesn't exist, security's per-task wall-clock cap on the microVM, best-practices' new closed-`Literal` values in `Recipe.engine` / `RecipeSelection.reason`) or forks the contract surface (performance's `MigrationLedger` + `cli/sherpa.py` parallel CLI). The synthesizer's central job is not to pick among the three designs but to **name the contract-extension points honestly, propose the *minimum* additive ADR set that opens them, and reject the maximalist proposals that smuggle service-shaped infrastructure (security's `codegenie-secretd` daemon) into a "Single Python project, no services, no databases" POC** (`CLAUDE.md` veto, called out explicitly by the critic).

The position taken: **hybrid (c) from the orchestrator framing.** ADR-0028 is amended in Phase 7 to permit **two named additive-extension patterns** plus a *very* small set of additive value extensions on existing closed `Literal`s, each one ADR-gated and surfaced loudly — and Phase 7 carries the cost of being the phase that lands the amendment. The alternative (forking everything to keep a zero-line-edit promise) inherits doubled surface area to Phase 8 and is materially worse. The amendment is bounded: no edits to behavioral logic of existing probes / engines / gates / nodes; only additive enum values, default-empty kwargs, and one `ClassVar` default on the `Probe` ABC. Each is captured as a per-phase ADR under `docs/phases/07-migration-task-class/ADRs/` and the production-level ADR-0028 receives a one-paragraph "extension-by-addition refinement" amendment.

Where the lenses dominate:

- **[B]'s shape dominates package layout, file homes, and naming.** New probes live next to old probes (`src/codegenie/probes/`), new recipes are *data* under `src/codegenie/recipes/catalog/docker/`, the new graph factory is `build_distroless_loop()` in `src/codegenie/graph/`, the new CLI verb is `codegenie migrate` (not a parallel `sherpa`), and `cli/loop.py` is **not** edited (Phase 6's exit criterion #14 is honored). The new ledger is `DistrolessLedger` (parallel to `VulnLedger`; ADR-0022 "Three Strikes" still applies — strike two; abstraction deferred to Phase 15).
- **[P]'s shape dominates runtime budgets, caching, and gate plumbing.** Buildkit local-cache + grype-DB cache under `.codegenie/cache/`; pre-rendered `base_catalog.json` shaped for Phase 8's Redis hot view; `dive` output reused for `shell_presence` (one tool invocation, two signals); regression-suite wall-clock as a budget-tracked perf canary.
- **[S]'s shape dominates the gate-time-vs-gather-time decision and the adversarial-Dockerfile corpus.** `ShellInvocationTraceProbe` runs **at gate time** inside the Phase-5 chokepoint — never at gather time against the target's entrypoint (closes critic perf.1, which correctly attacked performance's "run the entrypoint at gather time" as a Phase-2 threat-model violation). The adversarial-Dockerfile corpus (≥30 fixtures) lands; round-trip parse equivalence is required; `dockerfile-parse` runs as a subprocess with a hard wall-clock and a 1 MB input cap.
- **All three are overridden on credentials and `dive`.** Security's `codegenie-secretd` per-host daemon is rejected (`CLAUDE.md` veto: "Single Python project, no services, no databases. Filesystem-backed everything"). Credentials live in the operator's `~/.docker/config.json`, exactly where every CI pipeline already keeps them — best-practices' Open Question #7 lands as the answer. `dive` runs **inside the Phase-5 sandbox chokepoint** (security's threat-model concern about `dive`'s CVE history is honored; the cost is keeping `dive`'s output strictly Pydantic-validated, `extra="forbid"`).
- **Departures from all three.** (1) The extension-by-addition pattern is *named and counted*: exactly six additive seams open in Phase 7, each ADR-gated, each with a contract-snapshot test that regenerates. (2) `applies_to_lifecycle` is **not** added to the `Probe` ABC; instead `ShellInvocationTraceProbe` registers under a *new* registry (`@register_gate_probe`) that lives in a new module — same `Probe` ABC, same shape, different registry, so the Phase-2 coordinator never sees it and never has to learn the word "lifecycle." This closes critic sec.1 + sec.2 cleanly. (3) The `image_size_post / image_size_pre ≤ 0.8` signal is **dropped as a strict-AND input** (critic sec.3); it ships as an advisory `dive_efficiency` signal whose `passed` is always `True` but whose `details` carry the ratio for human review — preserving "facts, not judgments" and keeping legitimate Alpine→glibc migrations from auto-failing.

The user's highest-priority decision, surfaced once at the top of this document: **the ADR-0028 amendment that authorizes six named additive seams**. The full text of that amendment is in §"Roadmap coherence check" with the conflict-resolution scores that defend each seam. If the user wants a strict zero-edit Phase 7, the alternative shape (the all-fork option) is also documented in §"Departures from all three inputs" with its costs.

---

## Goals (concrete, measurable)

| # | Goal | Target | Provenance |
|---|---|---|---|
| 1 | **Workflows-per-hour, distroless task class only, single-worker** | ≥ 6 / hr cold (no caches), ≥ 24 / hr warm — slightly below `[P]`'s 30/hr; the critic's perf.2 attack landed (Linux DinD numbers are worse than macOS DiD). | `[P+synth]` |
| 2 | **Workflows-per-hour, mixed portfolio (vuln + distroless), single-worker, warm** | ≥ 10 / hr — slightly below `[P]`'s 12/hr for the same reason | `[P+synth]` |
| 3 | **Time-to-PR p95, distroless recipe hot path** | ≤ 240 s (was 180 s in `[P]`; raised to absorb honest Linux DinD numbers and the gate-time `ShellInvocationTraceProbe` budget) | `[P+synth]` |
| 4 | **Time-to-PR p95, distroless RAG-fallback path** | ≤ 420 s | `[P+synth]` |
| 5 | **Time-to-PR p95, distroless LLM-fallback path** | ≤ 600 s | `[P+synth]` |
| 6 | **$/PR, distroless recipe path** | $0 (no LLM call) | `[P]` |
| 7 | **$/PR, distroless LLM-fallback path** | ≤ $0.12 (Sonnet 4.7; Phase 4 cap unchanged) | `[P]` |
| 8 | **Buildx layer-cache hit rate, 3-fixture portfolio after first run** | ≥ 85% pulled-layer; ≥ 60% derived-layer | `[P]` |
| 9 | **Per-worker steady-state memory ceiling** | ≤ 2.4 GB | `[P]` |
| 10 | **Regression suite wall-clock (full vuln + distroless, `pytest-xdist -n auto`, LFS-pack-restored caches)** | p50 ≤ 4 min, p95 ≤ 7 min — **measured** in CI; if it regresses >10% in any Phase 7 PR, the `tests/perf/test_regression_suite_wall_clock.py` canary fires (closes critic best-practices.5: the additive-diff gate retiring is fine, but the *time-budget* canary survives forever) | `[P+B+synth]` |
| 11 | **Adversarial-Dockerfile corpus coverage** | ≥ 30 fixtures (BOM, UTF-16, CR line endings, `ONBUILD`, 2 MB file, parse-bomb, unicode normalization, hidden `\r`, Windows-1252) — every one either parses to a clean AST or is rejected with the documented `dockerfile.parse_rejected` reason code | `[S]` |
| 12 | **Dockerfile round-trip safety property** | `parse(serialize(parse(x))) == parse(x)` on the corpus | `[S]` |
| 13 | **Sandbox boundary** | `ShellInvocationTraceProbe` and `tools/dive.py` run **inside** Phase 5's `run_in_sandbox` chokepoint with the existing `gate_isolation_class` annotation propagating downstream — **no new microVM profile, no rootfs-digest bump, no Chainguard credential inside the microVM workload env** (closes critic sec.4 on rootfs growth; honors `CLAUDE.md` "no services") | `[synth — picks an additive overlay flag from [P] but rejects [S]'s 600 MB rootfs bump]` |
| 14 | **Credential surface** | Operator-side `~/.docker/config.json` only; Phase 7 does **not** read it, store it, mint tokens against it, or run a credential broker daemon. The egress for `cgr.dev` rides Phase 5's existing scoped-egress posture (extended with `cgr.dev` in the allowlist via ADR-P7-002). | `[B+synth — rejects [S]'s `codegenie-secretd`]` |
| 15 | **Public surface introduced by Phase 7** | 2 new probes; 1 new `RecipeEngine` impl; 1 new `Transform` impl; 1 new graph factory; 1 new CLI verb (`codegenie migrate`); 1 new Pydantic ledger (`DistrolessLedger`); 4 new `@register_signal_kind` registrations; 0 new ABCs; 0 new top-level packages; 6 ADR-gated additive seams (enumerated in §"Roadmap coherence check"). | `[B+synth]` |
| 16 | **Tokens contributed inside Phase 7's package boundary** | 0 (probes + transforms + recipes + catalogs may not import `anthropic` / `chromadb`; fence-CI extended) | `[B]` |
| 17 | **Phase 3/4/5/6 regression suite** | 100% pass on every Phase 7 PR as a hard merge gate | `[P+S+B]` |
| 18 | **Frozen Phase 0–6 *behavioral* code** | The Phase 7 PR may only add Phase-0–6-side edits enumerated in §"Roadmap coherence check" ADR-P7-001..006 (each adds a default value, registers a new value in an open registry / catalog, or appends a value to a previously-closed `Literal` with a contract-snapshot regenerated in the same PR). Any other Phase 0–6 line change fails CI. | `[synth — replaces [B]'s file-level freeze and [S]'s BLAKE3-of-source freeze with a *contract-surface freeze with an explicit named-amendment list*]` |
| 19 | **E2E exit criterion** | Migrate a Node.js fixture from `node:20-bullseye-slim` to `cgr.dev/chainguard/node:20` — recipe match → build → grype shows non-positive CVE delta → dive reports no `/bin/sh` in final image → `ShellInvocationTraceProbe` reports `runtime_shell_count == 0` → patch + branch produced. | `[B+roadmap]` |

---

## Architecture

```
            codegenie migrate <repo> [--cve <id> | --target distroless]
                                │
                                ▼  ─────────────  NEW CLI verb in cli/migrate.py  [B]
                ┌──────────────────────────────────────────────┐
                │  src/codegenie/cli/migrate.py  (NEW)          │
                │   - mirrors cli/loop.py readiness pattern     │
                │   - DOES NOT edit cli/loop.py or cli/         │
                │     remediate.py — Phase 6 exit criterion     │
                │     #14 is preserved                          │
                │   - inlines its own shared options (no        │
                │     extract to common.py)   [B Open Q #5]     │
                └──────────────────┬───────────────────────────┘
                                   │
                                   ▼
                ┌──────────────────────────────────────────────┐
                │  build_distroless_loop()  (NEW)               │
                │  src/codegenie/graph/distroless_loop.py       │
                │   - SAME factory shape as Phase 6's           │
                │     build_vuln_loop()                          │
                │   - SAME AuditedSqliteSaver (untouched)        │
                │   - SAME HumanRequest/HumanDecision (untouched)│
                │   - SAME @pure_edge decorator (untouched)      │
                │   - NEW DistrolessLedger (Pydantic, extra=     │
                │     forbid, schema_version Literal["v0.7.0"])  │
                │   - Nodes mirror vuln_loop one-to-one with     │
                │     one extra (resolve_target_image)           │
                │   - replan_with_phase4 calls Phase 4's         │
                │     FallbackTier.run(..., task_type=           │
                │     "distroless_migration", ...)               │
                │     — Phase 4 gains a default-None task_type   │
                │       kwarg via ADR-P7-003                     │
                └──────────────────┬───────────────────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────────┐
        │                          │                              │
        ▼                          ▼                              ▼
┌──────────────────┐  ┌──────────────────────┐  ┌──────────────────────────┐
│ Phase 2 Skills   │  │ Phase 3/4 unmodified │  │ Phase 5 GateRunner +     │
│ loader UNCHANGED │  │ Transform /          │  │ three-retry UNCHANGED    │
│ reads new        │  │ RecipeEngine         │  │ consumes new signal      │
│ skills/builtins/ │  │ registries +         │  │ kinds via existing       │
│ distroless/      │  │ DockerfileEngine     │  │ @register_signal_kind    │
│ *.md             │  │ + DockerfileBaseImage│  │ (Phase 5 open registry)  │
│ (additive data)  │  │ SwapTransform        │  │                          │
└──────────────────┘  └──────────────────────┘  └──────────────────────────┘
                                   │
                                   ▼
        ┌────────────────────────────────────────────────────────────────┐
        │ NEW probes (registered via existing @register_probe):           │
        │   src/codegenie/probes/base_image.py                            │
        │     applies_to_tasks=["distroless_migration","vuln_remediation"]│
        │     applies_to_lifecycle="gather" (default; Probe ABC unchanged)│
        │   src/codegenie/probes/shell_invocation_trace.py                │
        │     registered via @register_gate_probe (NEW registry, new     │
        │     module src/codegenie/probes/gate_registry.py) —             │
        │     same Probe ABC, no field added to the ABC                   │
        │     applies_to_tasks=["distroless_migration"]                   │
        │     declared_inputs include image_digest of candidate image    │
        └────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
        ┌────────────────────────────────────────────────────────────────┐
        │ NEW recipe engine + transform (registered via existing decorators):│
        │   src/codegenie/recipes/engines/dockerfile_engine.py           │
        │     wraps `dockerfile-parse`; OpenRewrite path NOT shipped in   │
        │     Phase 7 (critic best-practices.4: rewrite-docker covers     │
        │     multi-stage refactor poorly; we drop the decorative seat    │
        │     and ship the handrolled path only — recorded as ADR-P7-004) │
        │   src/codegenie/transforms/dockerfile_base_image_swap.py        │
        │     mirrors NpmPackageUpgradeTransform; uses git format-patch   │
        └────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
        ┌────────────────────────────────────────────────────────────────┐
        │ NEW catalogs + skills (data only):                              │
        │   src/codegenie/catalogs/distroless/                            │
        │     cve_image_recommendations.yaml   (the roadmap-mandated      │
        │                                       CVE→image lookup table)  │
        │     image_dialect_rules.yaml                                    │
        │     _schema.json                                                │
        │   src/codegenie/recipes/catalog/docker/                         │
        │     distroless_node_swap.yaml                                   │
        │     distroless_node_multistage.yaml                             │
        │     distroless_static_go.yaml                                   │
        │   src/codegenie/skills/builtins/distroless/                     │
        │     distroless-node.md                                          │
        │     distroless-static.md                                        │
        │     distroless-base.md                                          │
        │   src/codegenie/rag/seed_corpus/distroless/                     │
        │     N solved-example .md files                                  │
        └────────────────────────────────────────────────────────────────┘

  Cross-cutting plumbing under .codegenie/  (NEW):
    .codegenie/cache/buildkit/         ← buildx local cache (oci-dir, content-addressed)
    .codegenie/cache/grype-db/         ← grype vuln DB, single fetch / 24h TTL,
                                          flock(2) coordination
    .codegenie/cache/base_catalog.json ← pre-rendered hot-view (Phase 8-shape)
    .codegenie/cache/dockerfile-parse/ ← Pydantic-serialized parse results
    .codegenie/migration/<run-id>/     ← per-workflow workspace
       audit/<run-id>.jsonl            ← chained to Phase 2/5/6 audit chain
       checkpoints/<run-id>.sqlite3    ← AuditedSqliteSaver (Phase 6 unchanged)
       patches/Dockerfile.diff
       diff/<recipe-id>.patch
       raw/{build.log, dive.json, scenarios/*.trace.log}
```

The shape is a *deliberate mirror* of Phase 6 + Phase 3 + Phase 2. Reading either subgraph teaches the other.

---

## Components

### 1. `BaseImageProbe` (NEW Layer C gather-time probe)

- **Provenance:** `[P+B+S]` (all three converged).
- **Purpose:** Capture base-image lineage as **evidence** (no judgments) — `FROM` references, multi-stage shape, parsed users, parsed entrypoints, observed final-stage characteristics.
- **Interface:** Standard `Probe` ABC, **unchanged**. `name="base_image"`. `layer="C"`. `applies_to_tasks=["distroless_migration","vuln_remediation"]` (base-image CVEs are vulns; the slice is reusable). `applies_to_languages=["*"]`. `declared_inputs=["**/Dockerfile","**/Dockerfile.*","**/*.dockerfile"]` plus a fingerprint on `~/.docker/config.json` registry-mirror config. `timeout_seconds=30`. `cache_strategy="content"`.
- **Internal design:** Pure Python over `dockerfile-parse`. Emits a `DockerfileInventory` Pydantic slice. For multi-stage Dockerfiles, identifies the final stage by `--from` reference (or textually-last `FROM`). Flags `ARG`-indirect FROMs with `confidence=medium`. Resolves *manifest digest* (not layer bytes) via `docker buildx imagetools inspect --raw` with a 24h cache; cache key includes `--platform=linux/amd64` (closes critic perf.assumption.2: multi-arch silently sharing a digest). **No `docker pull` here.** `parser_skipped_lines: int` is surfaced so silent under-coverage is visible (critic perf.honest-confidence concern from `IndexHealthProbe` re-applied to Phase 7).
- **Why this choice over alternatives:** `[P]`, `[B]`, `[S]` all agreed; the synthesizer adds the `--platform` cache-key fix from critic perf.assumption.2.
- **Tradeoffs accepted:** `dockerfile-parse` doesn't perfectly handle BuildKit `--mount=type=...` heredocs in 1.5+; the probe degrades to `confidence: medium` on partial parse. Adversarial Dockerfiles with `parser_skipped_lines > 0` are treated by `RecipeSelector` as a recipe miss (forcing the RAG/LLM path), closing critic best-practices.hidden-assumption.3.

### 2. `ShellInvocationTraceProbe` (NEW Layer C gate-time probe)

- **Provenance:** `[S+P+synth]`. Lifecycle classification taken from `[S]`; cache key + 10s strace budget from `[P]`; **registration via a new `@register_gate_probe` decorator** instead of an `applies_to_lifecycle` field on the `Probe` ABC — this is the synthesizer's resolution of the critic's load-bearing attack (sec.1, sec.2).
- **Purpose:** Observe whether the **candidate (post-recipe) image's** entrypoint actually invokes a shell at runtime. Single signal that empirically validates the distroless target.
- **Interface:** Standard `Probe` ABC, unchanged. Registered via `@register_gate_probe` from a new module `src/codegenie/probes/gate_registry.py` (additive seam ADR-P7-001 — see §"Roadmap coherence check"). `applies_to_tasks=["distroless_migration"]`. `declared_inputs=["__image_digest__:<candidate>", "**/test/scenarios/*.yaml"]`. The *candidate* image digest is the one produced inside the gate; the cache key invalidates on every recipe re-apply. `timeout_seconds=30` (security's 30 s ceiling absorbs the critic's perf.risk.1 attack — perf's 10 s budget was too tight and would produce too many `confidence=medium` cache entries).
- **Internal design:**
  1. **Runs inside the Phase 5 `run_in_sandbox` chokepoint**, never at gather time, never on the orchestrator host. Closes critic perf.1 + critic sec.6.
  2. Reuses Phase 5's existing `gate_isolation_class` annotation; emits `shared_kernel` on macOS DinD, `microvm` on Linux Firecracker — Phase 11's promotion logic reads that annotation (Phase 5 contract). **No new sandbox profile; no rootfs digest bump.** Closes critic sec.4.
  3. The probe's gate-time work is: (a) `docker buildx build --load --cache-from=local --cache-to=local mode=max .` against the post-recipe Dockerfile; (b) `docker run --rm --network=none --pids-limit=64 --memory=512m --read-only --tmpfs /tmp --user nobody:nobody --cap-drop=ALL` of the rebuilt image with `strace -f -e trace=execve,connect,openat` for ≤30 s; (c) parse `execve` events into `runtime_shell_count`, `traced_binaries`, `network_endpoints_touched`. Confidence `high` if the entrypoint completed under budget; `medium` if budget exhausted. The `dive` projection (component 6) supplies `static_shell_binary_count` — same tool invocation, separate signal.
  4. **No Chainguard registry credential in the workload env.** The Docker daemon already authenticates against `cgr.dev` via the operator's `~/.docker/config.json`; the workload itself runs `--network=none` and so has no network at all.
- **Why this choice over alternatives:**
  - **Lifecycle field on Probe ABC `[S]` — rejected.** Critic sec.1 landed: adding a `ClassVar` default to `src/codegenie/probes/base.py` is a Phase 2 edit; Phase 2's coordinator would also need to learn to refuse gate-lifecycle probes at gather time (another edit).
  - **Probe at gather time `[P]` — rejected.** Critic perf.1 landed: executing the target's entrypoint at gather time violates Phase 2's threat model. No.
  - **New `@register_gate_probe` registry `[synth]`.** A 30 LOC new module that exports a decorator. The probe class is unchanged (same `Probe` ABC). The Phase-2 coordinator never sees it because gate probes register into a *different* registry and the gate-control loop (Phase 5) is what reads it. Phase 2's coordinator code is byte-identical pre-and-post Phase 7.
- **Tradeoffs accepted:**
  - 30 s budget may produce false positives on slow-starting entrypoints (security blind spot landed); we ship a single configurable in `tools/digests.yaml#gate.shell_trace.budget_s` and treat the budget as advisory in v0.7.0 (HITL escalation on timeout, not auto-fail).
  - Phase 2's old "stub `RuntimeTraceProbe` with `applies()=False`" stays in place forever as a no-op. Acceptable: best-practices Open Q #1 considered (a)–(c); we land (b). Recorded in ADR-P7-005.

### 3. `DockerfileRecipeEngine` (NEW `RecipeEngine` impl)

- **Provenance:** `[B+synth]`. Handrolled path only; OpenRewrite path **not shipped** (critic best-practices.4).
- **Purpose:** Apply Dockerfile-shaped recipes (base-image swap, multi-stage refactor) via `dockerfile-parse` AST mutation with deterministic re-serialization.
- **Interface:** Implements Phase 3's `RecipeEngine` ABC verbatim. `available()` returns `True` iff `dockerfile-parse` is importable and `docker buildx` is on `$PATH`. Selected by recipes whose `engine: dockerfile` field matches — and `Recipe.engine`'s closed `Literal` is extended additively via ADR-P7-006 (the explicit named extension; Phase 3's contract-snapshot test regenerates in the same PR).
- **Internal design:**
  - **AST mutation only.** `dockerfile-parse` strict mode; UTF-8 strict; BOM rejected; `\r` rejected; `ONBUILD` rejected; size cap 1 MB; subprocess wall-clock 10 s per parse (security's hardening).
  - **Round-trip safety.** `parse(serialize(parse(input))) == parse(input)` is asserted before any patch is written. Failure raises `RoundTripFailure` and the recipe is treated as a miss (RAG/LLM fallback). Closes critic sec.adversarial-Dockerfile concerns + critic best-practices.hidden-assumption.2.
  - **No OpenRewrite path.** Critic best-practices.4 landed: `rewrite-docker` covers base-image swaps well and multistage refactors poorly; shipping the seat as primary when one of the two named recipes can't use it is decorative. Phase 15's recipe-authoring work re-evaluates; Phase 7 ships handrolled-only and records the deferral in ADR-P7-004.
  - **Deterministic ordering.** Same byte-stability helper Phase 3 uses (`git format-patch -1 --stdout`, `core.hooksPath=/dev/null`, bot identity). The `dockerfile-canonicalize` helper is **byte-only**: strip trailing whitespace, normalize line endings to LF, do not reorder. No semantically-significant rewrites (closes critic best-practices.hidden-assumption.2).
- **Why this choice over alternatives:** `[B]` argued OpenRewrite primary + handrolled fallback. Critic landed: OpenRewrite can't do the harder of the two named recipes. We ship handrolled only; the OpenRewrite seat returns when Phase 15 commissions it with a working multi-stage corpus.
- **Tradeoffs accepted:** Phase 15 inherits the "decide whether OpenRewrite ever returns for Docker" question. Recorded as a Phase-7-deferred issue in ADR-P7-004.

### 4. `DockerfileBaseImageSwapTransform` (NEW `Transform` impl)

- **Provenance:** `[B]`.
- **Purpose:** The Phase 7 transform — selects a Chainguard target via the catalog, applies the recipe via `DockerfileRecipeEngine`, produces a deterministic git-format-patch.
- **Interface:** Implements Phase 3's `Transform` ABC verbatim. `applies_to_tasks=["distroless_migration"]`. `applies_to_languages=["*"]` (recipe-level language gating).
- **Internal design:** Mirrors `NpmPackageUpgradeTransform`. `git worktree add` to `.codegenie/migration/<run-id>/worktree`; `DockerfileRecipeEngine.apply`; `dockerfile-canonicalize`; `git format-patch -1 --stdout`. No lockfile equivalent; `validate_in_sandbox` (Phase 5) runs the `docker buildx build` validator instead.
- **Why this choice over alternatives:** All three designs converged on this shape; the only disagreement was on file homes, resolved in `[B]`'s favor.
- **Tradeoffs accepted:** Multi-stage refactor is harder than base-image swap; Phase 7 ships two recipes that cover narrow shapes (Node `npm-build → distroless-runtime`, Go `go-build → static-distroless`). The catalog grows in Phase 15.

### 5. `build_distroless_loop()` (NEW LangGraph factory)

- **Provenance:** `[B+P+synth]`. Topology from `[B]`; `MigrationLedger` vs `DistrolessLedger` naming from `[B]`; pre-rendered hot view from `[P]`; **one named additional node** (`resolve_target_image`) departs from all three.
- **Purpose:** SHERPA-disciplined state machine for the distroless migration loop. Mirrors `build_vuln_loop()` exactly in factory shape.
- **Interface:** Identical signature to Phase 6's `build_vuln_loop()`: `(checkpointer, max_attempts=3, force_rebuild=False) -> CompiledGraph`. Module-level lazy compile; same `AuditedSqliteSaver`; same `HumanRequest`/`HumanDecision` from Phase 6's `hitl.py` (imported verbatim).
- **Internal design:**
  - **Nodes (11 total; one more than `vuln_loop`):** `ingest_target` → `resolve_target_image` (new, reads `.codegenie/cache/base_catalog.json`) → `select_recipe` → {matched: `apply_recipe`, miss: `rag_lookup`} → `replan_with_phase4` (on RAG miss) → `apply_recipe` → `validate_in_sandbox` → `record_attempt` → `await_human` → `emit_artifact` / `escalate`. Same `@pure_edge` decorator from Phase 6.
  - **State model: `DistrolessLedger`.** Pydantic `extra="forbid"`, `frozen=False`, `schema_version: Literal["v0.7.0"]`. Fields shaped to mirror `VulnLedger` where possible: `workflow_id`, `thread_id`, `repo_path`, `target_image_recommendation`, `dockerfile_path`, `recipe_selection`, `last_engine`, `retry_count`, `chain_head`, `prior_attempts`, `events`. **No shared base class with `VulnLedger`.** Critic was concerned about Phase 8's supervisor reading two schemas — that's Phase 8's job; the supervisor will dispatch on `task_type` and either know about both ledgers or unify them in a Phase 8 ADR. Phase 7 inherits one debt; Phase 8 pays the price of being the unification phase. ADR-0022 Three Strikes: strike one was vuln, strike two is distroless, abstraction deferred to Phase 15 / Phase 8.
  - **`replan_with_phase4` calls Phase 4's `FallbackTier.run(..., task_type="distroless_migration", ...)`.** Phase 4's `FallbackTier.run` gains a `task_type: str | None = None` kwarg via ADR-P7-003 (additive default). When `task_type` is non-None, Phase 4 selects the matching prompt template (`migration_distroless.v1.yaml`) and the matching solved-example collection (`distroless_solved_examples_promoted`) — both new files under Phase 4's existing `prompts/` and the vector DB. No behavioral change for vuln callers (the default keeps the existing path).
  - **HITL contract reused verbatim.** `HumanRequest`/`HumanDecision` from `codegenie.graph.hitl` are imported. The exported JSON contract (`docs/contracts/hitl-v0.6.0.json`) does **not** change.
  - **Checkpointer reused verbatim.** Same `AuditedSqliteSaver`; per-workflow SQLite file under `.codegenie/migration/checkpoints/<workflow_id>.sqlite3` (different directory, same writer).
  - **CLI dispatch.** A new `codegenie migrate` verb in `cli/migrate.py` (a new file). **`cli/loop.py` is not modified.** This is `[B]`'s choice over `[P]`'s parallel `cli/sherpa.py` — Phase 6 named `cli/sherpa.py` as the *future* dispatch home for Phase 8's supervisor; Phase 7 does not coin that file (closes critic perf.5).
- **Why this choice over alternatives:** `[P]` proposed `cli/sherpa.py` with `run/resume/inspect/replay` subcommand surface; critic perf.5 attacked: that forks the CLI before Phase 8 even arrives, and `codegenie sherpa resume` can't operate on a vuln workflow. We ship `codegenie migrate` as a parallel verb (mirrors Phase 6's `codegenie loop`); Phase 8's supervisor takes the dispatch surface when it lands.
- **Tradeoffs accepted:** Two ledgers (Phase 8 inherits the merge); two CLI verbs (`loop` and `migrate`; Phase 8 unifies). Documented in §"Roadmap coherence check".

### 6. `dive_signal` + `shell_presence_signal` (NEW signal kinds, one dive invocation)

- **Provenance:** `[P+S+synth]`. `[P]`'s "one dive invocation, two signals" trick + `[S]`'s threat model on `dive` (runs inside the sandbox chokepoint, output strictly Pydantic-parsed).
- **Purpose:** Image-efficiency facts (size, layer count, wasted bytes) and a static shell-binary check (no `/bin/sh` in the runtime layer) emitted as gate signals.
- **Interface:** Two `@register_signal_kind` registrations under `src/codegenie/sandbox/signals/` — `dive` (file: `dive.py`) and `shell_presence` (file: `shell_presence.py`). The `dive` collector invokes `tools/dive.py` inside the Phase 5 sandbox chokepoint; `shell_presence` is a *projection on the dive result* (no extra invocation). Both return `ObjectiveSignals` fragments — Phase 5's existing extension contract.
- **Internal design:**
  - **`dive` collector:** parses `dive --json` output via a strict Pydantic model (`extra="forbid"`). Returns `passed=True` always (advisory); `details` carries `final_size_bytes`, `efficiency_pct`, `wasted_bytes`. Closes critic sec.3: the `image_size_post / image_size_pre ≤ 0.8` strict-AND is **dropped** because it auto-fails legitimate Alpine→glibc migrations. Phase 13's calibration window (per ADR-0015) decides whether to harden later.
  - **`shell_presence` collector:** reads the `dive` Pydantic result and emits `passed = (static_shell_binary_count == 0)`. Sub-50 ms. Heuristic shell-name list: `/bin/sh`, `/bin/bash`, `/bin/dash`, `/bin/busybox`, `/usr/bin/sh`, `/usr/bin/bash`. Security's "scan ELF symbols too" is deferred (security blind spot landed; Chainguard distroless images don't ship arbitrary binaries by construction).
  - **Strict-AND inputs added (additive on the open registry):** `build`, `grype`, `shell_presence`, `shell_invocation_trace`, plus the advisory `dive` collector (always `passed=True`). Phase 5's open registry absorbs this with one `ObjectiveSignals` widening per kind, captured as ADR-P5-amendment style additions inside ADR-P7-002.
- **Why this choice over alternatives:** `[P]`'s one-invocation-two-signals is correct; `[S]`'s "two separate dive invocations" is wasteful and was flagged by critic perf.things-missed. `[S]`'s strict-AND on size ratio fails legitimate migrations (critic sec.3).
- **Tradeoffs accepted:** `dive`'s output schema is upstream-versioned; we pin `tools/digests.yaml#sandbox.dive` and re-vendor on each upstream release. ELF-symbol scanning deferred to a future phase.

### 7. `tools/buildkit.py` + `tools/dive.py` + `tools/dockerfile_parse.py` (NEW tool wrappers)

- **Provenance:** `[P+B+synth]`. Same wrapper pattern as Phase 2's `tools/syft.py`, `tools/grype.py`.
- **Purpose:** Centralize external CLI invocation in one place per tool. Probes / signal collectors consume **typed Pydantic models**, never raw subprocess output.
- **Interface:** Each wrapper is a function returning a strict Pydantic model. All invoke `codegenie.exec.run_in_sandbox` from Phase 0/1; **none** use `subprocess.run` directly.
- **Internal design:**
  - `tools/buildkit.py`: `docker buildx build --load --cache-from=type=local,src=.codegenie/cache/buildkit --cache-to=type=local,dest=.codegenie/cache/buildkit,mode=max`. Returns `BuildkitResult(exit_code, image_digest, manifest_path, layer_count, wall_clock_ms)`.
  - `tools/dive.py`: `dive --json --ci <image_digest>`. Returns `DiveResult` (strict Pydantic).
  - `tools/dockerfile_parse.py`: in-process `dockerfile-parse` wrapper — *or* subprocess if a hostile-Dockerfile fixture flags `--isolate-parser`. Returns `DockerfileInventory`.
- **Why this choice over alternatives:** Phase 2's wrapper convention is the project's idiom; the only design that argued against it was `[S]` (which proposed running everything inside the microVM rootfs). We honor `[S]`'s sandbox concern by routing every wrapper through `run_in_sandbox` (Phase 5 chokepoint), but the wrapper Python code lives in `tools/`.
- **Tradeoffs accepted:** Adding `docker`, `dive` to Phase 0's `ALLOWED_BINARIES` is one additive ADR (ADR-P7-002 covers it as a bundle).

### 8. Pre-rendered `base_catalog.json` hot view

- **Provenance:** `[P]`. Forward-shaped for Phase 8 / ADR-0013 Redis hot views.
- **Purpose:** Make `resolve_target_image` sub-millisecond by caching CVE→image mappings + current Chainguard digest snapshots.
- **Interface:** Single JSON file at `.codegenie/cache/base_catalog.json`, keyed on a snapshot SHA of `cve_image_recommendations.yaml` + Chainguard registry-index snapshot.
- **Internal design:** Rendered by a new `render_base_catalog()` function called at end-of-gather; mmap-read by `resolve_target_image` node. Shape-compatible with Phase 8's Redis layout (same JSON schema, same key, same staleness signal).
- **Why this choice over alternatives:** `[B]` and `[S]` read the YAML each time, paying the parse cost on every workflow. `[P]`'s pre-render is sub-50 ms once at end-of-gather and serves microseconds-per-lookup forever. Phase 8 lifts the file into Redis without schema changes.
- **Tradeoffs accepted:** Catalog is read-only during a workflow; Chainguard mid-run rotations use the staler digest until the next gather. Recorded in failure-modes table.

### 9. `tests/perf/test_regression_suite_wall_clock.py` (NEW perf canary, never retired)

- **Provenance:** `[P+synth]`. Critic best-practices.5 demanded a *permanent* enforcement of extension-by-addition rather than `[B]`'s one-shot CI gate. The synth response: replace the one-shot additive-diff gate with a **permanent contract-surface snapshot + a permanent regression-suite wall-clock canary**.
- **Purpose:** A budget-tracking canary that fires when the regression suite p95 regresses >10%. Survives Phase 7 — Phase 8/9/10/.../15 each pay if they slip the budget.
- **Interface:** A pytest fixture under `tests/perf/`.

### 10. Contract-surface snapshot test (NEW; replaces `[B]`'s one-shot diff gate)

- **Provenance:** `[synth]`. The synthesizer's response to the critic's "extension-by-addition cannot be one-shot" attack.
- **Purpose:** A permanent CI test that snapshots **the public contract surfaces** of Phases 0–6 — the Pydantic models, the ABCs, the registry decorator signatures, the closed `Literal`s — and asserts byte-stability against a checked-in `tools/contract-surface.snapshot.json`. Any change to a contract surface (e.g., adding a value to `Recipe.engine`'s `Literal`) requires regenerating the snapshot in the same PR. The regenerator emits a structured diff that the PR template requires the author to summarize and link to an ADR.
- **Interface:** `tests/integration/test_contract_surface_snapshot.py`. Uses Pydantic's `model_json_schema()` + Python introspection on registry decorators. Survives forever.
- **Why this choice over alternatives:** `[B]`'s one-shot file-level additive-diff gate retires after Phase 7 (critic best-practices.5 landed); `[S]`'s BLAKE3-over-source freeze breaks on any whitespace edit. The contract-surface snapshot is the *right* freeze: it catches behavioral / API drift but doesn't punish refactoring within a file.
- **Tradeoffs accepted:** Authors of additive ADRs run a one-line regenerate command. Documented in the Phase 7 PR template.

---

## Data flow

End-to-end run, `codegenie migrate ./services/auth --target distroless`:

1. **CLI entry.** `cli/migrate.py` parses options. Tool-readiness check: `git`, `docker`, `dive`, `dockerfile-parse` (Python). Same readiness pattern as `cli/remediate.py` (read; do not edit). **Trust boundary crossing:** repo bytes enter the orchestrator; treat as untrusted.
2. **Load context.** `repo-context.yaml` mmap'd; schema-validated; `IndexHealthProbe.confidence ≥ medium` checked. `BaseImageProbe` slice is already present (registered into Phase 2's coordinator at probe-discovery time — additive, no coordinator edit). `ShellInvocationTraceProbe` slice is **not** present yet — it's a gate probe, populated during Stage 5.
3. **Resolve target image.** `resolve_target_image` node reads `.codegenie/cache/base_catalog.json` (mmap; sub-microsecond). Maps `node:20.10.0-bullseye` → `cgr.dev/chainguard/node:20-distroless@sha256:<pinned>`. Image-name allowlist regex validated.
4. **Build initial `DistrolessLedger`.** `schema_version="v0.7.0"`, `workflow_id`, `thread_id=workflow_id`, `repo_path`, `target_image_recommendation`, `chain_head=<from Phase 6 audit chain>`, `prior_attempts=[]`.
5. **`ainvoke()` `build_distroless_loop()`.** LangGraph runtime takes over. **Per-workflow SQLite checkpointer** under `.codegenie/migration/checkpoints/<workflow_id>.sqlite3`. BLAKE3 chain extension semantics from Phase 6 unchanged.
6. **`select_recipe` node:** matches `distroless_node_swap.yaml` or `distroless_node_multistage.yaml` based on `base_image.is_multistage`. **No LLM.** On miss → `rag_lookup` → `replan_with_phase4`. `[P+S — agree]`
7. **`apply_recipe` node:** invokes `DockerfileBaseImageSwapTransform`. `dockerfile-parse` strict-mode parse → AST mutation → re-serialize → round-trip assert → `git format-patch -1`. **Byte-deterministic** across runs.
8. **`validate_in_sandbox` node (Phase 5 GateRunner, unchanged):** signals collected via the open `@register_signal_kind` registry. The signals for distroless are:
   - `build` (existing) — `tools/buildkit.py` runs `docker buildx build --load --cache-from=local --cache-to=local`. Warm: 10–25 s on Mac DiD; 25–60 s on Linux DinD/Firecracker. **Trust boundary crossing:** `docker buildx` invokes RUN steps in the new Dockerfile — Phase 5's `run_in_sandbox` is the only thing between RUN code and the host. Egress allowlist (Phase 5 extended additively, ADR-P7-002): `cgr.dev`, `docker.io` added.
   - `grype` (existing) — scans the rebuilt image. CVE delta computed against the *pre*-image's grype result (captured at gather time).
   - `dive` (new, additive) — advisory signal; `passed=True` always; details carry size/efficiency/wasted.
   - `shell_presence` (new, additive) — strict-AND: `passed = (static_shell_binary_count == 0)`. Projection on dive result; ~50 ms.
   - `shell_invocation_trace` (new, additive, gate probe) — strict-AND: `passed = (runtime_shell_count == 0 && confidence == "high")`. 30 s budget; `passed=False, retryable=True` on timeout (HITL on retry exhaustion).
9. **Strict-AND verdict** via Phase 5's `StrictAndGate.evaluate` → Phase 3's `TrustScorer.score` (unchanged). On failure: Phase 5's three-retry loop fires; `record_attempt` writes `AttemptSummary` with `prior_failure_summary`; retry-1 re-enters `replan_with_phase4` with `prior_attempts` (ADR-P5-002 unchanged) and `task_type="distroless_migration"` (ADR-P7-003 new).
10. **HITL fires** on retry exhaustion via the same `await_human` mechanism. `HumanRequest`/`HumanDecision` JSON contract identical.
11. **`emit_artifact`:** writes `.codegenie/migration/<run-id>/migration-report.yaml`, `.codegenie/migration/<run-id>/diff/<recipe-id>.patch`, `.codegenie/migration/<run-id>/raw/{build.log, dive.json, scenarios/*.trace.log}`, chained audit entries. Branch `codegenie/distroless/<short-sha>`.
12. **Exit 0** on success. Phase 8's supervisor (when it lands) reads `DistrolessLedger.last_engine` + the audit chain to compute ROI.

**Where the path crosses lenses:**
- *Step 8 build signal* crosses **[S]** (egress allowlist, sandbox boundary) and **[P]** (buildkit cache hit rate, wall-clock budget).
- *Step 8 shell_invocation_trace signal* crosses **[S]** (gate-time only; runs the candidate image inside Phase 5 chokepoint; closes critic perf.1) and **[P]** (cache key, 30 s budget).
- *Step 9 strict-AND* crosses **[B]** (open registry, no closed Literal) and **[S]** (advisory `dive`, not strict-AND on size ratio; closes critic sec.3).

---

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery | Source |
|---|---|---|---|---|
| Hostile Dockerfile fails strict UTF-8 / BOM / CR / size / `ONBUILD` checks | `DockerfileRecipeEngine` raises `DockerfileRejected` | No patch written; no sandbox started | Subgraph routes to `await_human_review` with reason code | `[S]` |
| `dockerfile-parse` hangs or RCEs | 10 s subprocess wall-clock; output not deserialized if late | Parser runs as subprocess (or in-VM); no orchestrator state corruption | `dockerfile.parse_rejected` audit event; escalate | `[S]` |
| Recipe round-trip fails | `DockerfileRecipeEngine.apply` asserts `parse(serialize(parse(input))) == parse(input)` | No patch written | Audit `dockerfile.recipe_applied(ast_round_trip_ok=false)`; HITL | `[S]` |
| `base_catalog.json` returns a typosquat candidate (poisoned YAML) | Image-name allowlist regex `^cgr\.dev/chainguard/[a-z0-9-]+(@sha256:[a-f0-9]{64}\|:[a-z0-9._-]+)$` | Selector refuses; recipe miss | RAG / LLM fallback (same allowlist applies); HITL on persistent miss | `[S]` |
| `BaseImageProbe`'s `imagetools inspect` fails | HTTPS roundtrip non-200 | Probe emits `confidence: low`, `resolved_at=null` | Selector falls through to `catalog_miss`; Phase 4 owns fallback | `[P]` |
| Buildkit cache poisoning | Build exit ≠ 0 with cache-IO error | Cache entries are content-addressed (buildkit native); per-entry `created_by_codegenie_version` annotation evicts forward on version mismatch | Retry once with `--cache-from` only; if fails, GC the corrupted entry; if still fails, signal `confidence: low` | `[P]` |
| Buildkit concurrent-write race (cross-workflow) | Buildkit's own consistency check on cache-export | Phase 7 documents the risk; `flock(2)` on the cache root for `--cache-to` writes | Retry; if persistent, escalate to HITL — Phase 9's Temporal idempotency closes this for distributed workers | `[P+synth]` (critic perf.4 partial mitigation; not fully solved in Phase 7) |
| Grype DB update race | `flock(2)` on `.last_update` sentinel | First arriver wins; later arrivers see fresh sentinel | Pessimistic: cross-platform `flock` test in CI; documented blind spot | `[P]` (critic perf.assumption.1 acknowledged) |
| Multi-arch manifest list returned by `imagetools inspect` | Cache key now includes `--platform=linux/amd64` | Single-arch cache | Multi-arch deferred to Phase 7.1; documented blind spot | `[synth — closes critic perf.assumption.2]` |
| Strace probe times out (30 s budget exhausted) | `subprocess.TimeoutExpired` | `confidence=medium`, `entrypoint_invokes_shell="unknown"` | Strict-AND fails (`passed=False, retryable=True`); retry; HITL on exhaust | `[S+P+synth]` |
| Rebuilt image build fails in sandbox | Phase 5 `GateRunner` (unchanged); `build` signal exit ≠ 0 | Sandbox per-attempt teardown unchanged | Phase 5's three-retry; retry-1 re-enters `replan_with_phase4` with `prior_attempts`+ `task_type` (ADR-P7-003) | `[P+S]` |
| `shell_presence` finds shell in rebuilt image | `dive` enumeration | `passed=False`, strict-AND fail | Retry with `distroless` (vs `distroless-dev`) target; HITL on exhaust | `[P+S]` |
| `dive_efficiency` regression (image grew) | `dive` collector | **Advisory only** (`passed=True`; details flagged for human review) | None — gate passes; surfaced in `migration-report.yaml` | `[synth — closes critic sec.3; rejects [S]'s strict-AND on size ratio]` |
| Phase 0–6 source code edited (forbidden) | `tests/integration/test_contract_surface_snapshot.py` permanent canary | PR cannot merge | Author either reverts or amends an ADR + regenerates the snapshot | `[synth — replaces [B]'s one-shot file-diff gate]` |
| `cve_image_recommendations.yaml` stale | `last_verified > 90d` per-row timestamp | `confidence=medium` warning at `resolve_target_image` | Operator runs `codegenie cache refresh base-catalog`; Phase 14 will automate | `[B]` |
| Carried forward from Phase 5 | Phase 5 detections / containments / recoveries | unchanged | unchanged | `[P5]` |

---

## Resource & cost profile

- **Tokens per Phase 7 run:**
  - Recipe path: 0.
  - RAG path: Phase 4's RAG-hit shape unchanged; 0 LLM tokens (the cache + the seed `rag/seed_corpus/distroless/` corpus carry the hit).
  - LLM-fallback path: ≤ 40 k input + 8 k output, $≤ 0.12 per goal #7.

- **Wall-clock per workflow** (honest about Linux DinD numbers; critic perf.2 landed):
  - Recipe hot path: p50 ≈ 90 s, p95 ≤ 240 s.
  - Recipe cold path: p50 ≈ 200 s, p95 ≤ 360 s.
  - RAG fallback hot: p50 ≈ 260 s, p95 ≤ 420 s.
  - LLM fallback: p50 ≈ 380 s, p95 ≤ 600 s.

- **Memory per worker (steady state, single workflow):**
  - Orchestrator + LangGraph + planner: ~280 MB (Phase 6 baseline).
  - ChromaDB mmap + embed worker: ~720 MB (Phase 4 baseline; only loaded if RAG path engages).
  - Buildkit/grype/dive transient peaks: ~700 MB during Stage 5.
  - **Ceiling: 2.4 GB.**

- **Storage:**
  - Per workflow durable: ≤ 40 MB (patch + branch + audit chain + ledger checkpoint).
  - Per workflow ephemeral: ≤ 250 MB (image manifest reference; image bytes in containerd's content store, not under `.codegenie/`).
  - Portfolio caches: `.codegenie/cache/buildkit/` multi-GB (capped via `codegenie cache gc`); `grype-db/` ~150 MB; `strace/` <1 MB per fixture.

- **Network:** Chainguard registry pulls during build (~150–300 MB per cold base). Operator-side `~/.docker/config.json` authenticates. Phase 5's existing scoped-egress allowlist extends additively (`cgr.dev` + `docker.io`).

- **Cost of security controls vs `[P]`'s ideal:** ~30 s extra wall-clock per workflow attributable to the `shell_invocation_trace` 30 s budget (vs `[P]`'s 10 s budget). The synthesizer accepted this because `[P]`'s 10 s produced too many `confidence=medium` cache entries, which then cascaded into `await_human` escalations and inflated $/PR.

---

## Test plan

**Unit tests** (per-component, fast):
- `tests/unit/probes/test_base_image.py` — ≥ 14 tests covering: single/multi-stage Dockerfile parsing, `ARG`-indirect FROMs (`confidence=medium`), `FROM scratch`, BuildKit heredoc → `parser_skipped_lines > 0`, malformed Dockerfile typed error, `applies_to_tasks` matrix, `declared_inputs` glob coverage, `cache_key()` invalidation, intent test (`test_base_image_emits_facts_not_judgments`).
- `tests/unit/probes/test_shell_invocation_trace.py` — ≥ 10 tests with mocked strace output; tests `applies_to_tasks=["distroless_migration"]`; tests budget-exhaust behavior; sanitizer Pass 5 strips prompt-injection markers from raw trace bytes.
- `tests/unit/recipes/engines/test_dockerfile_engine.py` — ≥ 12 tests: round-trip safety property (Hypothesis); byte-determinism across 5 runs; `ONBUILD` refusal; BOM/CR rejection; size cap; subprocess wall-clock.
- `tests/unit/transforms/test_dockerfile_base_image_swap.py` — ≥ 8 tests: `Transform` ABC compliance, worktree handling, dirty-tree refusal, branch naming, format-patch determinism.
- `tests/unit/sandbox/signals/test_dive_signal.py` — recorded `dive --json` output; assert advisory `passed=True`.
- `tests/unit/sandbox/signals/test_shell_presence_signal.py` — fixture dive output with/without `/bin/sh`; assert strict-AND.
- `tests/unit/graph/test_distroless_state.py` — `DistrolessLedger` `extra="forbid"` rejection; runtime `id()` diff hook fires on in-place mutation; `schema_version: Literal["v0.7.0"]` pin.
- `tests/unit/graph/test_distroless_edges.py` — every `@pure_edge` predicate × every branch.
- `tests/unit/catalogs/test_distroless_catalogs.py` — schema validation; closed-enum CI gate on `confidence_band`.

**Adversarial tests** (≥ 30 fixtures, Goal #11):
- `tests/adversarial/dockerfiles/` — BOM, UTF-16, CR line endings, `ONBUILD`, mid-Dockerfile `ARG x=$(curl atk)`, deeply-nested heredocs, 2 MB file, parse-bomb (recursive `FROM ... AS ...`), unicode normalization, hidden `\r` in `FROM`, Windows-1252. Property test on round-trip equivalence.
- `tests/adversarial/typosquat_lookup.py` — fixture `CVE-XXX → cgr.dev/chamguard/node:20` → allowlist regex rejects.
- `tests/adversarial/build_egress_blocked.py` — Dockerfile contains `RUN curl https://evil.test/` → in-VM egress proxy drops.

**Integration tests** (in CI):
- `tests/integration/test_migrate_node_e2e.py` — Express fixture; `node:20-bullseye-slim` → `cgr.dev/chainguard/node:20`; golden patch; **the roadmap E2E exit criterion** (goal #19).
- `tests/integration/test_migrate_static_go_e2e.py` — Go fixture; multi-stage refactor; golden patch.
- `tests/integration/test_migrate_handrolled_path.py` — single-engine path (no OpenRewrite); assert produces valid output.
- `tests/integration/test_migrate_shell_required_hitl.py` — entrypoint shells out at runtime; `ShellInvocationTraceProbe` flags it; gate fails; `await_human` interrupt; mocked `HumanDecision(action="abort")` aborts cleanly.
- `tests/integration/test_migrate_recipe_miss_llm_fallback.py` — recipe miss → RAG miss → `replan_with_phase4(task_type="distroless_migration")` → cassette-driven LLM response → patch produced. Asserts ≤ $0.12 spend (goal #7).
- `tests/integration/test_migrate_replay_after_kill.py` — SIGKILL during `validate_in_sandbox`; resume produces byte-identical final state.
- **`tests/integration/test_phase3_4_5_6_unchanged.py`** — re-runs every Phase 3/4/5/6 test verbatim. Failure = hard merge gate (Phase 7 entry per `roadmap.md`).
- **`tests/integration/test_contract_surface_snapshot.py`** — the permanent contract-surface canary (component 10).

**Performance regression** (permanent, never retired):
- `tests/perf/test_regression_suite_wall_clock.py` — full suite p50 ≤ 4 min, p95 ≤ 7 min; fires on >10% regression.
- `tests/perf/test_buildkit_cache_hit_rate.py` — assert ≥ 85% pulled-layer cache hits on 2nd-and-after fixture run.
- `tests/perf/test_workflow_throughput.py` — 6 cold + 24 warm workflows; assert goal #1.

**Property tests:**
- `tests/property/test_dockerfile_engine_idempotent.py` — applying base-image-swap recipe twice produces the same diff.
- `tests/property/test_dockerfile_engine_roundtrip.py` — `parse(serialize(parse(x))) == parse(x)` on the adversarial corpus.

**Golden files:**
- `tests/golden/distroless_loop_topology.json` — `build_distroless_loop().get_graph().to_json()`. CI gate.
- `tests/golden/dockerfile_swap_node20.patch`.
- `tests/golden/dockerfile_multistage_go.patch`.

**Not in Phase 7 (deferred):**
- Cross-host cache sharing → Phase 9 (Temporal idempotency).
- Multi-arch builds → Phase 7.1.
- Cosign / Rekor verification → Phase 16 hardening.
- ROI dashboard cost attribution → Phase 13.
- Real PR opening → Phase 11.
- ELF-symbol scanning for non-heuristic shell-binary detection → Phase 12+.

---

## Risks (top 5)

1. **The strace probe is the new B2.** Silent under-coverage on entrypoints that shell out only on a specific request is the worst failure mode (perf risk #1). Mitigation: `confidence=medium` on budget exhaust; strict-AND treats `medium` as fail; the human-merge requirement (ADR-0009) is the last line; an adversarial fixture (Node service that shells out only on `/admin`) ships with the corpus.

2. **The Phase 4 `task_type` extension (ADR-P7-003) is the load-bearing additive seam.** If Phase 4's RAG retrieval doesn't actually score distroless-shaped solved examples higher than vuln-shaped ones, the LLM path produces vuln-shaped patches for distroless inputs and the gate fails consistently — driving every fallback workflow to retry-3 escalation. Mitigation: ship at least 8 seeded distroless solved examples in `rag/seed_corpus/distroless/`; an integration test asserts the retriever returns a distroless example as top-1 for a distroless query.

3. **The 30 s strace budget under Linux DinD may be too tight or too loose.** Goal #5 LLM-fallback p95 ≤ 600 s assumes the budget is honest. Mitigation: configurable in `tools/digests.yaml#gate.shell_trace.budget_s`; `tests/perf/baseline.json` tracks the empirical distribution; bump with an ADR amendment if p95 entrypoint-steady-state-time exceeds 24 s.

4. **The contract-surface snapshot test fires on legitimate refactors and authors learn to regenerate it without thinking.** Phase 7's lasting protection against accidental Phase 0–6 edits depends on PRs that touch the snapshot being reviewed with full attention. Mitigation: the regeneration command emits a structured diff to the PR description; the PR template requires the author to link a specific ADR ID. Phase 8's first PR is the first test of this discipline.

5. **`base_catalog.json` becomes stale faster than `IndexHealthProbe` can detect.** Chainguard rotates tags continuously. Mitigation: per-row `resolved_at`; `BaseImageProbe` emits `confidence=medium` on entries >12h old; gate treats `medium` as advisory; operator-gated `codegenie cache refresh base-catalog`. Phase 14 will continuous-gather + webhook this.

---

## Synthesis ledger

### Vertex count

Walked the three designs, extracted atomic decision vertices.

- **Performance design**: 28 vertices extracted.
- **Security design**: 36 vertices extracted.
- **Best-practices design**: 22 vertices extracted.
- **Total: 86 vertices.**

The high count is driven by Phase 7's contract-extension complexity — every input proposed multiple seams, every seam is a vertex. Pruned 8 trivially-subsumed vertices on first pass; the table below reflects post-prune counts.

### Edges

- **AGREE**: 24 — three designs (or two with the third silent) converged on the same shape. Examples: `BaseImageProbe` purpose + interface; `DockerfileBaseImageSwapTransform` mirroring `NpmPackageUpgradeTransform`; reuse of Phase 6 HITL contract verbatim; `DistrolessLedger`/`MigrationLedger` as parallel (not unified) ledger.
- **CONFLICT**: 19 — incompatible decisions on the same dimension. Resolved in the table below.
- **COMPLEMENT**: 21 — different aspects of the same dimension, both kept. Examples: `[P]`'s buildkit cache + `[S]`'s `dockerfile-parse` strict-mode + `[B]`'s `Transform` ABC reuse; `[S]`'s adversarial corpus + `[B]`'s property tests + `[P]`'s perf canary.
- **SUBSUME**: 14 — one is a strictly more general version of another. Examples: `[B]`'s "additive enum value with ADR" subsumes `[P]`'s "fork the enum"; Phase 5's open `@register_signal_kind` registry subsumes `[B]`'s closed-`Literal` proposal.

### Conflict-resolution table

For every CONFLICT edge resolved, one row. Scoring: 0–3 per dimension; 0 on commitments-fit = veto.

| # | Dimension | [P] picks | [S] picks | [B] picks | Winner | Exit-fit | Roadmap-fit | Commitments-fit | Critic-fit | Sum |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `ShellInvocationTraceProbe` lifecycle | Gather-time, pre-built fixture image | Gate-time, new `applies_to_lifecycle` field on ABC | Gate-time, kept on existing ABC; stub left in place | **[synth]** Gate-time via new `@register_gate_probe` registry; ABC unchanged | 3 | 3 | 3 | 3 | **12** |
| 2 | Probe ABC additive field | n/a | `applies_to_lifecycle: ClassVar = ["gather"]` (Phase 2 edit) | Avoid (Open Q #1) | **[B+synth]** No ABC edit; separate registry module | 3 | 3 | 3 | 3 | **12** |
| 3 | Coordinator branch for gate probes | Implicit | Yes (refuse `["gate"]` at gather time) | Avoid | **[B+synth]** No coordinator edit; gate registry sits outside Phase 2 coordinator | 3 | 3 | 3 | 3 | **12** |
| 4 | Credential storage | Operator `~/.docker/config.json` (Phase 13 deferred) | New `codegenie-secretd` daemon + AF_UNIX + age-encrypted file | Operator `~/.docker/config.json` (Open Q #7) | **[P+B]** Operator `~/.docker/config.json`; no broker daemon | 3 | 3 | **3 (S=0)** | 3 | **12** |
| 4a | (S's `codegenie-secretd` evaluated) | — | — | — | **vetoed**: `CLAUDE.md` "Single Python project, no services, no databases" — commitments-fit = 0 | 0 | 0 | **0 (veto)** | 0 | 0 |
| 5 | `dive` location | Inside Phase 5 chokepoint; output reused for `shell_presence` | Inside microVM with rootfs bump | Inside Phase 5 chokepoint | **[P+B+S]** Inside Phase 5 chokepoint; reused for both signals; *no rootfs bump* | 3 | 3 | 3 | 2 | **11** |
| 6 | Rootfs digest bump | No bump (existing chokepoint) | +350 MB (buildx, dive, dockerfile-parse, cosign, image-runner) | Not addressed | **[P+synth]** No bump; sandbox unchanged | 3 | 3 | 2 | 3 | **11** |
| 7 | Cosign / Rekor signature verification | n/a | Yes, strict-AND fail on invalid | Not addressed | **[synth — defer to Phase 16]** Critic sec.5: Chainguard's signing infrastructure isn't a documented stable contract at Phase 7 time; ship in Phase 16 hardening | 3 | 3 | 3 | 3 | **12** |
| 8 | `Recipe.engine` Literal extension | Implicit (data-only recipes; selector reads catalog) | Implicit | Add `"dockerfile"` value (Open Q #6) | **[B+synth]** Add `"dockerfile"` via ADR-P7-006; contract-snapshot regenerates | 3 | 3 | 3 | 3 | **12** |
| 9 | `RecipeSelection.reason` Literal extension | Implicit reuse of `"catalog_miss"` | n/a | Add `"unsupported_image_dialect"` | **[P+synth]** Reuse `"unsupported_dialect"` (already exists in Phase 3); do NOT add a new value. Closes critic best-practices.2 | 3 | 3 | 3 | 3 | **12** |
| 10 | Phase 4 task-class routing | Corpus-level routing (no API edit) | "Phase 4 LLM fallback (called only on retry-2)" — vague | Explicit `task_type` kwarg (Open Q #3) | **[B+synth]** Add `task_type: str | None = None` kwarg via ADR-P7-003; default keeps existing callsites unchanged | 3 | 3 | 3 | 3 | **12** |
| 11 | Phase 5 signal API used | n/a | New `TrustGate.register_signal(...)` (made up) | Existing `@register_signal_kind` | **[B]** Existing `@register_signal_kind`; security's API doesn't exist | 3 | 3 | 3 | 3 | **12** |
| 11a | (S's `TrustGate.register_signal` evaluated) | — | — | — | **vetoed**: API doesn't exist in Phase 5 — commitments-fit = 0 | 0 | 0 | **0 (veto)** | 0 | 0 |
| 12 | Sandbox wall-clock cap | Phase 5's existing cap | Raised from 5 min to 10 min "for migration gates only" | n/a | **[P]** Use Phase 5's existing cap; gates that exceed it fail naturally. Per-task-class wall-clock map would be a Phase 5 edit | 3 | 3 | 3 | 2 | **11** |
| 13 | Strict-AND on image-size ratio | `dive_efficiency` advisory (`passed=True`; details only) | `image_size_post / image_size_pre ≤ 0.8` strict-AND | n/a | **[P+synth]** Advisory only; closes critic sec.3 (Alpine→glibc false positives) | 3 | 3 | 3 | 3 | **12** |
| 14 | Strace budget | 10 s | 30 s | n/a | **[S]** 30 s — closes critic perf.risk.1 (10 s produces too many `confidence=medium`); configurable | 3 | 3 | 3 | 3 | **12** |
| 15 | Ledger schema unification | Parallel `MigrationLedger` | Composed `MigrationLoopState` in `LoopState` | Parallel `DistrolessLedger`; Three Strikes deferred | **[B+P]** Parallel `DistrolessLedger`; ADR-0022 Three Strikes — Phase 8 unifies. Critic acknowledged: Phase 8 inherits the merge | 3 | 2 | 3 | 2 | **10** |
| 16 | CLI dispatch home | New `cli/sherpa.py` with `run/resume/inspect/replay` parallel to `cli/loop.py` | Same `codegenie` entry, `--task distroless` flag | New `codegenie migrate` verb | **[B]** New `codegenie migrate`; Phase 8 supervisor takes the dispatch later. Closes critic perf.5 | 3 | 3 | 3 | 3 | **12** |
| 17 | Phase 6 `cli/loop.py` edited | No (parallel `cli/sherpa.py`) | n/a | No (new `cli/migrate.py`) | **[B+P]** No edit; honors Phase 6 exit criterion #14 | 3 | 3 | 3 | 3 | **12** |
| 18 | OpenRewrite `rewrite-docker` shipped | Implicit "recipe data" — no engine class | Not addressed | Primary engine, with handrolled fallback | **[synth]** Drop OpenRewrite seat for Phase 7; ship handrolled only. Closes critic best-practices.4 | 3 | 2 | 3 | 3 | **11** |
| 19 | Adversarial-Dockerfile corpus size | n/a | ≥ 30 fixtures | 4 fixtures | **[S]** ≥ 30 fixtures. Closes critic best-practices.things-missed (adversarial coverage) | 3 | 3 | 3 | 3 | **12** |
| 20 | Round-trip parse safety | n/a | `parse(serialize(parse(x))) == parse(x)` property | Not addressed | **[S]** Property test on adversarial corpus | 3 | 3 | 3 | 3 | **12** |
| 21 | Extension-by-addition enforcement | n/a | BLAKE3 over every source file — breaks on whitespace | One-shot file-level additive-diff gate, retired | **[synth]** Permanent contract-surface snapshot test (component 10). Closes critic best-practices.5 | 3 | 3 | 3 | 3 | **12** |
| 22 | Multi-arch image manifest handling | Cache key omits `--platform` | n/a | n/a | **[synth]** Cache key includes `--platform=linux/amd64`. Closes critic perf.assumption.2 | 3 | 2 | 3 | 3 | **11** |
| 23 | Buildkit cache concurrency-tolerance claim | "Concurrency-tolerant" (asserted) | n/a | n/a | **[synth]** Acknowledge race risk; ship `flock(2)` on cache root for `--cache-to`; Phase 9 Temporal idempotency closes the rest. Documented blind spot. Closes critic perf.4 partially | 2 | 2 | 3 | 2 | **9** |

**Edges flagged by critic as AGREE-on-blind-spot, scored separately:**

| Dimension | Consensus | Synth | Why |
|---|---|---|---|
| All three treat Phase 5's `gate_isolation_class` as not their problem | Phase 7 emits whatever the Phase 5 backend reports (`shared_kernel` on Mac DiD; `microvm` on Linux Firecracker) | **Adopt consensus + document**. Recorded as ADR-P7 reference: Phase 7's migration gates emit the same annotation Phase 5 already produces; Phase 11's promotion logic reads the annotation. No new value needed. |
| All three implicitly assume Phase 4 either already routes by task class or will be silently extended | Add `task_type` kwarg, default-None, via ADR-P7-003 | **Resolved**. See row 10 above. |
| All three ship the OpenRewrite-shaped integration despite none verifying Chainguard image coverage | Drop OpenRewrite for Phase 7; ship handrolled only | **Resolved**. See row 18. |

### Shared blind spots considered

The critic identified three patterns where all three lenses quietly agreed on something questionable:

1. **`gate_isolation_class` left undefined for migration gates.** Carried forward: Phase 7 emits the Phase 5 backend's value verbatim; Phase 11 reads it. No new value is needed. This is the consensus the synthesizer carried forward.
2. **Phase 4 `FallbackTier.run` task-class routing.** Departed from the implicit consensus. ADR-P7-003 makes the kwarg additive + default-None; the contract surface is named and the extension is loud.
3. **OpenRewrite `rewrite-docker` coverage.** Departed from the consensus. The OpenRewrite seat is dropped for Phase 7 (critic landed: it can't do multi-stage refactor; shipping it as a primary that always falls through is decorative). Phase 15 re-evaluates.

### Departures from all three inputs

The synthesizer picked a position none of the three proposed in the following places:

1. **`@register_gate_probe` registry (synthesis original).** Both `[S]` and `[B]` proposed lifecycle classification on the `Probe` ABC (additive field). `[P]` proposed running the probe at gather time. Synthesizer: keep the ABC byte-stable, route gate probes through a *separate registry module* that gate-control (not the Phase 2 coordinator) reads. Closes critic sec.1 and sec.2 cleanly.

2. **Contract-surface snapshot test as permanent canary (synthesis original).** `[B]`'s one-shot additive-diff gate retires after Phase 7 (critic best-practices.5 landed). `[S]`'s BLAKE3-of-source freeze breaks on whitespace edits. Synthesizer: a *contract-surface* snapshot test — Pydantic schemas + ABC interfaces + closed Literals + registry decorator signatures — survives forever, allows in-file refactors, fires on contract drift. Authors regenerate it in the same PR as the ADR.

3. **Six named additive seams + ADR-0028 one-paragraph amendment (synthesis original).** Rather than the maximalist "no edits, ever" (which forces forks that Phase 8 inherits) or the minimalist "edit whatever" (which silently violates the load-bearing commitment), the synthesizer enumerates *exactly six* additive seams:
   - **ADR-P7-001**: New module `src/codegenie/probes/gate_registry.py` exporting `@register_gate_probe`. **Pure addition** (new file).
   - **ADR-P7-002**: Phase 5 `ObjectiveSignals` widened by 4 optional fields (`dive`, `shell_presence`, `shell_invocation_trace`, `base_image`); Phase 0 `ALLOWED_BINARIES` extended by `docker`, `dive`; Phase 5 egress allowlist extended by `cgr.dev`, `docker.io`. All additive; same pattern as ADR-P5-amendment style used inside Phase 5.
   - **ADR-P7-003**: Phase 4 `FallbackTier.run(..., task_type: str | None = None, ...)` kwarg additive default-None. Phase 4 contract-snapshot test regenerates.
   - **ADR-P7-004**: OpenRewrite `rewrite-docker` deferred from Phase 7 (critic best-practices.4); handrolled-only.
   - **ADR-P7-005**: `RuntimeTraceProbe` Phase 2 stub kept in place forever as a no-op; `ShellInvocationTraceProbe` ships as a sibling new file with a distinct name.
   - **ADR-P7-006**: Phase 3 `Recipe.engine` Literal extended additively with `"dockerfile"`. Phase 3 contract-snapshot test regenerates.
   
   Each ADR is small (≤ 1 page), names the exact diff, and the Phase 7 PR template requires linking each ADR to the file lines it justifies.

4. **`dive_efficiency` as advisory-only (synthesis original).** `[S]` proposed `image_size_post / image_size_pre ≤ 0.8` as strict-AND. Critic sec.3 landed: legitimate Alpine→glibc migrations fail this. Synthesizer: ship the signal but `passed=True` always; `details` carry the ratio for human review. Phase 13's calibration window decides whether to harden.

5. **Strict zero-edit alternative (the option the synthesizer rejected).** If the user wants zero Phase 0–6 edits including these six seams, the alternative shape is: (a) Phase 7 ships its own `MigrationFallbackTier` mirroring `FallbackTier.run`'s signature plus a `task_type` kwarg (parallel mediator); (b) the new `DistrolessLedger` carries its own engine enum independent of Phase 6's; (c) the contract-surface snapshot test still ships (closes critic best-practices.5). Cost: Phase 4's prompt library and vector store collection are still extended (necessarily; the LLM has to produce distroless-shaped output somehow), but the *interface* edits move to Phase 8 instead of Phase 7. The synthesizer argues the cost of forking `FallbackTier` is materially worse than the cost of one additive kwarg — but the choice is the user's, and ADR-P7-003 explicitly carries the deferred-fork option as the documented alternative.

---

## Exit-criteria checklist

For each Phase 7 exit criterion in `roadmap.md`:

- [x] **"Both task classes run from the same orchestration."** → `codegenie loop run <repo> --cve <id>` (vuln) and `codegenie migrate <repo> --target distroless` (distroless) both build LangGraph subgraphs from the same `graph/` package, both use the same `AuditedSqliteSaver`, both extend the same BLAKE3 audit chain, both honor the same `HumanRequest`/`HumanDecision` HITL contract. Phase 8's supervisor unifies the dispatch surface.
- [x] **"The diff for this phase touches only new files — no Phase 0–6 source code is modified."** → **Qualified**. The contract-surface snapshot test (component 10) is the permanent enforcement. The six named additive seams (ADR-P7-001..006) are the explicit list of behavioral-shape-preserving additions to Phase 0–6 files / surfaces. Every one regenerates a contract-snapshot in the same PR; every one is justified by a ≤ 1-page ADR. **The roadmap's literal "only new files" assertion is amended in ADR-0028 to "only new files plus additive enum/kwarg/optional-field extensions captured in per-phase ADRs."** This is the load-bearing decision of the synthesis.
- [x] **"The full vuln-remediation regression suite runs as a hard gate before merging this phase."** → `tests/integration/test_phase3_4_5_6_unchanged.py` runs every prior-phase integration test verbatim; failure blocks merge.
- [x] **"End-to-end test migrates a Node.js service with a vulnerable base image to a Chainguard distroless image."** → `tests/integration/test_migrate_node_e2e.py`.

---

## Load-bearing commitments check

For each commitment in `production/design.md §2`:

- **§2.1 No LLM in the gather pipeline.** **Honored.** `BaseImageProbe` and `ShellInvocationTraceProbe` are deterministic Python; both registered to the open registries; neither imports `anthropic` / `chromadb`. Fence-CI extended to deny LLM-SDK imports in `probes/`, `transforms/`, `recipes/`, `catalogs/`. The synthesizer's `@register_gate_probe` registry sits outside the gather pipeline by construction.
- **§2.2 Facts, not judgments.** **Honored.** `BaseImageProbe` slice keys are observable evidence terms (no `is_distroless_candidate`, no `safe_to_migrate`). `ShellInvocationTraceProbe` reports `runtime_shell_count`, `traced_binaries`, `network_endpoints_touched` — the conclusion lives in the gate. `dive_efficiency` ships advisory (`passed=True`) rather than judgment.
- **§2.3 Honest confidence.** **Honored.** `BaseImageProbe.parser_skipped_lines > 0` → `confidence=medium`; `imagetools inspect` resolution >12h old → `confidence=medium`; `ShellInvocationTraceProbe` budget-exhaust → `confidence=medium`. Gate treats `medium` as fail (strict-AND).
- **§2.4 Determinism over probabilism for structural changes.** **Honored.** Recipe path is byte-deterministic via `dockerfile-parse` AST mutation + canonical re-serialization + round-trip safety property. LLM appears only at `replan_with_phase4` (Phase 4 path; unchanged).
- **§2.5 Extension by addition.** **Honored *with explicit, named amendment*.** The contract-surface snapshot test is the permanent enforcement; the six ADR-gated seams are the loud, reviewable extensions. **This is the commitment the synthesizer most carefully refined**: critic sec.1/sec.2 and critic best-practices.5/best-practices.2 collectively showed that the *literal* "no Phase 0–6 source edits, ever" reading of ADR-0028 forces forks that defeat the commitment's intent. The amendment's text: "Extension by addition means *behavior-preserving additive extension*: new files; new registry entries; new optional fields on Pydantic models; new default-None kwargs; new values in previously-closed `Literal`s — each gated by a per-phase ADR that names the exact diff. Behavior-changing edits to existing logic remain forbidden."
- **§2.6 Organizational uniqueness as data, not prompts.** **Honored.** `cve_image_recommendations.yaml`, `image_dialect_rules.yaml`, `_schema.json` all schema-validated; recipe catalog files under `recipes/catalog/docker/` are data. Phase 4's RAG retrieves structured catalog entries.
- **§2.7 Progressive disclosure.** **Honored.** `BaseImageProbe` emits parsed Dockerfile structure as a slice; raw bytes stay under `.codegenie/context/raw/dockerfiles/<sha>/`. `ShellInvocationTraceProbe` emits a compact summary; raw strace logs stay under `.codegenie/context/raw/traces/<scenario>/`. `RepoContext` indexes; never inlines.
- **§2.8 Humans always merge.** **Honored.** `await_human` interrupt; reused HumanRequest/HumanDecision; Phase 11 owns PR opening; ADR-0009 unchanged.
- **§2.9 Cost is observable end-to-end and bounded per workflow.** **Honored.** `GraphEvent` stream is unchanged; Phase 13 reads it. `FallbackTier`'s cost-cap hook still applies; Phase 7 adds no new LLM call paths.
- **`CLAUDE.md` "Single Python project, no services, no databases. Filesystem-backed everything."** **Honored.** `[S]`'s `codegenie-secretd` daemon is vetoed (commitments-fit = 0 in the conflict-resolution table); credentials live in `~/.docker/config.json`. No new long-running processes. All caches filesystem-backed.

---

## Roadmap coherence check

**What prior phases established that this design depends on:**
- **Phase 0**: `fence` CI job (deny LLM imports under `probes/`); `ALLOWED_BINARIES` list (extended additively).
- **Phase 1**: `Probe` ABC (unchanged); `@register_probe` decorator (used as-is); `run_in_sandbox` (used as-is).
- **Phase 2**: Coordinator (byte-identical); `DockerfileProbe` (C1) co-exists with new `BaseImageProbe` (C-layer extension); `IndexHealthProbe` (B2) reads new probe slices via the existing `consumes_peer_outputs` mechanism (no new mechanism needed); raw-output discipline + sanitizer Pass 5; `tools/` wrapper convention.
- **Phase 3**: `RecipeEngine` ABC + `Transform` ABC (byte-identical); `RecipeSelection.reason` Literal (reused, NOT extended — critic best-practices.2 landed); `TrustScorer.score` (unchanged); `Recipe.engine` Literal **extended additively** with `"dockerfile"` via ADR-P7-006; `git format-patch` invocation pattern; `ApplyContext.prior_attempts` (ADR-P5-002 unchanged).
- **Phase 4**: `FallbackTier.run` (extended additively with `task_type` kwarg via ADR-P7-003); RAG retriever shape; seed corpus pattern (`rag/seed_corpus/`); fence-wrapping for untrusted text; LLM cost-cap hook.
- **Phase 5**: `GateRunner.run` + `run_one` (unchanged); `@register_signal_kind` open registry (used as-is); `ObjectiveSignals` Pydantic model widened by 4 optional fields (ADR-P7-002); `gate_isolation_class` annotation (unchanged; Phase 7 emits whatever Phase 5 backend reports); three-retry per-gate; `run_in_sandbox` chokepoint; egress allowlist extended additively.
- **Phase 6**: `AuditedSqliteSaver` (unchanged); `HumanRequest`/`HumanDecision` (verbatim); `@pure_edge` (unchanged); `cli/loop.py` (not edited); BLAKE3 chain extension semantics; `GraphEvent` (unchanged; Phase 7's `record_attempt` emits the same shape).

**What this design establishes that later phases will need:**
- **Phase 8 (Hierarchical Planner)**: must read both `VulnLedger` and `DistrolessLedger` schemas; will dispatch `task_class` to the right `build_*_loop()` factory; will subsume the `codegenie loop` + `codegenie migrate` CLI surfaces behind a supervisor. The pre-rendered `base_catalog.json` hot view is shape-compatible with Phase 8's Redis hot views.
- **Phase 9 (Temporal)**: workflow idempotency closes the buildkit concurrent-write race that Phase 7 documents as a partial blind spot.
- **Phase 11 (Handoff + Learning)**: reads `gate_isolation_class` (unchanged), the BLAKE3 audit chain, and the new `migration-report.yaml` artifact.
- **Phase 13 (AgentOps)**: reads `GraphEvent.wall_clock_ms` + `FallbackTier.cost_tokens` + the new `dive` advisory signal for calibration on `image_size_post / image_size_pre` (which Phase 7 ships as advisory; Phase 13 decides whether to harden).
- **Phase 14 (Continuous gather)**: `BaseImageProbe`'s `resolved_at` per-row timestamp + the `cve_image_recommendations.yaml` `last_verified` per-row timestamp are the seams for webhook-driven refresh.
- **Phase 15 (Agentic recipe authoring)**: revisits the OpenRewrite `rewrite-docker` deferral (ADR-P7-004); grows `cve_image_recommendations.yaml` from solved examples; unifies `VulnLedger` and `DistrolessLedger` if Phase 8 hasn't yet (ADR-0022 Three Strikes).
- **Phase 16 (Production hardening)**: cosign signature verification + Rekor transparency log (security's design.7 deferred); production-grade credential broker (security's `codegenie-secretd` revisited *as a service*, not a daemon dropped into a local POC).

**New ADRs implied by this design:**
- **ADR-P7-001**: New module `src/codegenie/probes/gate_registry.py` exporting `@register_gate_probe`. New file; no Phase 0–6 edit.
- **ADR-P7-002**: Phase 5 `ObjectiveSignals` widening (4 optional fields); Phase 0 `ALLOWED_BINARIES` extension; Phase 5 egress allowlist extension. Each is an existing extension mechanism used additively.
- **ADR-P7-003**: Phase 4 `FallbackTier.run` gains `task_type: str | None = None` kwarg; default keeps existing callsites unchanged.
- **ADR-P7-004**: OpenRewrite `rewrite-docker` deferred from Phase 7 to Phase 15.
- **ADR-P7-005**: Phase 2 `RuntimeTraceProbe` stub stays in place forever as a no-op; `ShellInvocationTraceProbe` ships as a sibling new file with a distinct name.
- **ADR-P7-006**: Phase 3 `Recipe.engine` Literal extended additively with `"dockerfile"`.
- **ADR-0028 amendment** (production-level, one paragraph): "Extension by addition" formally permits the additive seams enumerated above.

---

## Open questions deferred to implementation

1. **Strace 30 s budget tuning.** Configurable in `tools/digests.yaml#gate.shell_trace.budget_s`. Phase 7 ships 30 s; Phase 13's perf canary tracks the empirical distribution; bump (with an ADR amendment) if p95 entrypoint-steady-state-time exceeds 24 s.
2. **`flock(2)` cross-platform behavior on the grype DB sentinel.** macOS BSD flock vs Linux fcntl-based flock. CI matrix must include both. Documented blind spot; stress test in `tests/integration/test_grype_db_concurrent_refresh.py`.
3. **Multi-arch image-manifest handling.** Phase 7 ships `linux/amd64`-only fixtures; the cache key includes `--platform=linux/amd64`. Multi-arch is a Phase 7.1 follow-up.
4. **OpenRewrite `rewrite-docker` re-evaluation in Phase 15.** ADR-P7-004 names the deferral; Phase 15's agentic recipe authoring is the right phase to decide whether the OpenRewrite seat returns for Docker recipes.
5. **`base_catalog.json` schema versioning for Phase 8's Redis lift.** Phase 7 pins `Literal["v0.7.0"]`; Phase 8 either reuses the schema literal or introduces a versioning policy across the filesystem↔Redis boundary. The synthesizer flags this for Phase 8; out of scope here.
6. **Pre-warm strategy for `cgr.dev` base images.** First workflow on a fresh CI runner pays the cold pull (~150–300 MB). A `codegenie cache prewarm` operator command is a small addition; Phase 7 ships the workflow without it and lets the operator add the command if they want (~30 LOC).
7. **`cve_image_recommendations.yaml` validation CI gate.** Phase 7 ships ~30 hand-curated entries with a closed-enum CI gate on `confidence_band`. Whether the ingest pipeline grows an automated bumping ceremony is a Phase 14+ question.
8. **`DistrolessLedger` ↔ `VulnLedger` unification.** Phase 8's supervisor must read both. Phase 8 either ships one supervisor that knows both schemas, or unifies the ledgers via a Phase 8 ADR. Phase 7's responsibility ends at "two ledgers; structurally similar; both honor `extra="forbid"` + `schema_version` literal pin". The synthesizer notes this is the largest debt Phase 7 bequeaths.
9. **The strict zero-edit alternative.** The synthesizer recommends the six-seam additive amendment but documents the all-fork alternative in §"Departures from all three inputs" #5. If the user prefers zero Phase 0–6 edits at the cost of doubled surface area in Phase 8, the alternative is fully specified.
