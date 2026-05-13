# Phase 07 — Add migration task class (Chainguard distroless): High-level implementation plan

**Status:** Implementation plan
**Date:** 2026-05-12
**Architecture reference:** [phase-arch-design.md](phase-arch-design.md)
**ADRs:** [ADRs/](ADRs/)
**Source design:** [final-design.md](final-design.md)
**Roadmap reference:** [docs/roadmap.md](../../roadmap.md) §"Phase 7"

## Executive summary

The engineer is adding **Chainguard distroless container migration** as a second task class on top of the existing vuln-remediation SHERPA loop, with the *introduction itself* as the integration test for the "extension by addition" commitment. The central work shape is: (1) **land the contract seams first** — six ADR-gated additive seams into Phase 0–6 surfaces *plus* the permanent contract-surface snapshot canary that enforces them forever, (2) then build the new probes/recipes/transform/ledger/graph/CLI as *new files* in a vertical slice, (3) close the adversarial edge cases and harden performance with the dedicated canaries. This order is dictated by the fact that the six seams (gate-probe registry, `ObjectiveSignals` widening, `FallbackTier` kwarg, `Recipe.engine` Literal, `ALLOWED_BINARIES` extension, egress-allowlist extension) are *contracts* every later step compiles against, and the snapshot canary is the merge gate that catches anyone — including this same phase — from drifting beyond them. The hard merge gate at the end is the full Phase 3/4/5/6 regression suite passing unchanged plus the Node.js Express → Chainguard distroless end-to-end test.

## Order of operations

This is a contracts-first, vertical-slice, harden-last sequence. Step 1 lands all six additive seams in a single PR with their ADRs and the *initial* contract-surface snapshot, because every later step imports or extends one of these surfaces and the snapshot must exist before any later edit can be detected as drift. Steps 2–4 then build the new files (probes, recipe engine + transform, ledger + graph factory + CLI) in dependency order — probes feed recipes feed the transform feeds the graph feeds the CLI. Step 5 lights up the end-to-end Node.js happy path (the roadmap exit-criterion test). Steps 6–7 broaden coverage: adversarial Dockerfile corpus + property tests, then the gap-analysis fixes the architect flagged (sidecar strace, cache locking, snapshot-regen CI audit, task-type mismatch safety). Step 8 closes performance canaries and the wall-clock regression test. Step 9 is the merge-gate green — the full Phase 3/4/5/6 regression suite plus the contract-surface snapshot plus the workflow-throughput perf tests must all be green. Tests land *with* their step, not after.

---

## Step 1 — Establish the six additive seams, ADRs, and the contract-surface snapshot canary

**Goal:** Every Phase 0–6 surface that Phase 7 will compile against is widened, justified by an ADR, and frozen against further drift by a permanent CI canary — in one merged PR — before any new Phase 7 file is written.

**Features delivered:**
- New file `src/codegenie/probes/gate_registry.py` exporting `@register_gate_probe` and `all_gate_probes()` (ADR-P7-001 — pure addition).
- Additive edits in `src/codegenie/sandbox/signals/models.py` (four optional `None`-defaulted fields on `ObjectiveSignals`), `src/codegenie/sandbox/host/allowed_binaries.py` (+`docker`, +`dive`), `src/codegenie/sandbox/host/egress_allowlist.py` (+`cgr.dev`, +`docker.io`) — ADR-P7-002.
- Additive `task_type: str | None = None` kwarg on `FallbackTier.run` in `src/codegenie/planner/fallback_tier.py` — ADR-P7-003. Default branch is byte-identical to existing behavior.
- Additive `"dockerfile"` value on `Recipe.engine` `Literal` in `src/codegenie/recipes/contract.py` — ADR-P7-006.
- ADR-P7-004 (OpenRewrite `rewrite-docker` deferral) and ADR-P7-005 (`RuntimeTraceProbe` stub preservation) — pure-deferral / pure-preservation, no diff.
- ADR-P7-007 (`dive_efficiency` advisory-only) recorded as a design constraint.
- Production ADR amendment: one-paragraph amendment to ADR-0028 ("extension by addition" formally means *behavior-preserving additive extension*) per `phase-arch-design.md §Path to production end state`.
- `tools/contract-surface.snapshot.json` — initial snapshot covering Phase 0–6 Pydantic schemas, ABC signatures, closed Literals, registry decorator signatures, `ALLOWED_BINARIES`, egress allowlist, and the new `FallbackTier.run` signature.
- `tests/integration/test_contract_surface_snapshot.py` — permanent canary that fails on drift; supports `pytest --update-contract-snapshot` to regenerate intentionally.
- `tests/integration/test_phase4_default_task_type_behavior_unchanged.py` — asserts ADR-P7-003 is behavior-preserving when `task_type=None`.
- CI gate `tools/snapshot_regen_audit.py` (per Gap 5) — runs in GitHub Actions; on any PR that modifies the snapshot, scrape the body for `ADR-(P\d+-\d+|0\d+)` and require the matching ADR file is modified in the same PR.

**Done criteria:**
- [ ] All six ADR markdown files exist under `docs/phases/07-migration-task-class/ADRs/` and are linked from the per-phase ADR index.
- [ ] ADR-0028 amendment paragraph is appended to `docs/production/adrs/ADR-0028*.md` and references back to ADR-P7-001..006.
- [ ] `pytest tests/integration/test_contract_surface_snapshot.py` is green on `master` with the new snapshot.
- [ ] `pytest tests/integration/test_phase4_default_task_type_behavior_unchanged.py` is green (vuln callers see byte-identical results to pre-edit `FallbackTier.run`).
- [ ] Phase 0–6 full unit-test suite still green (no behavior regression from the four edits).
- [ ] `tools/snapshot_regen_audit.py` runs in CI and blocks a synthetic PR that updates the snapshot without an ADR in the same PR.
- [ ] Fence-CI extended: `anthropic|chromadb|sentence-transformers` imports denied under `probes/`, `transforms/`, `recipes/`, `catalogs/` (G18).

**Depends on:** Phase 0–6 merged; access to write under `docs/production/adrs/` for the ADR-0028 amendment.

**Effort:** M — the diffs are small but six ADRs and the initial snapshot generator need to be written and reviewed carefully.

**Risks specific to this step:** The snapshot generator under-covers something (e.g., misses a registry decorator), so later drift goes undetected — mitigate by reviewing the snapshot diff manually for each Phase 0–6 contract listed in `phase-arch-design.md §Component 10`. ADR-0028 amendment is the single most controversial decision in the phase; expect review pushback and pre-write the rationale.

---

## Step 2 — Land tool wrappers and the pre-rendered base catalog hot view

**Goal:** Deterministic, Pydantic-typed wrappers around `dockerfile-parse`, `docker buildx`, `dive`, and `strace` exist so every later step depends only on typed return values, not raw subprocess parsing; and `.codegenie/cache/base_catalog.json` is renderable from `cve_image_recommendations.yaml`.

**Features delivered:**
- `src/codegenie/tools/dockerfile_parse.py` — strict-mode wrapper; UTF-8 only; BOM/CR/`ONBUILD`/size>1MB rejected; 10s subprocess wall-clock; Pydantic `DockerfileInventory` model with `parser_skipped_lines: int`.
- `src/codegenie/tools/buildkit.py` — `docker buildx build`, `imagetools inspect --raw --platform=linux/amd64`, auto-creates named builder `codegenie-distroless` on first use (per Gap 7), parses stderr for auth failures (`RegistryAuthFailed`), pinned digest in `tools/digests.yaml#sandbox.buildkit_image`.
- `src/codegenie/tools/dive.py` — `dive --json` Pydantic model with `extra="forbid"`; raises on upstream schema break.
- `src/codegenie/tools/strace.py` — subprocess wrapper around `strace -f -e trace=execve,connect,openat` with configurable budget.
- `src/codegenie/sandbox/host/cache_lock.py` (Gap 2) — `fcntl.flock` wrapper with `pyfilelock` cross-platform fallback; `with cache_lock(path, timeout_s=30): ...`; raises `CacheLockTimeout`.
- `src/codegenie/catalogs/distroless/` — `cve_image_recommendations.yaml` (hand-curated seed; 3+ rows for Node, Go, Python), `_schema.json`, `render_base_catalog()`, `read_base_catalog()`.
- `tools/digests.yaml` extended (additively): `sandbox.dive`, `sandbox.strace`, `sandbox.strace_sidecar`, `sandbox.buildkit_image`, `gate.shell_trace.budget_s` (default 30).
- Unit tests: `tests/unit/tools/test_dockerfile_parse.py`, `tests/unit/tools/test_buildkit.py` (auto-bootstrap idempotence per Gap 7), `tests/unit/tools/test_dive.py`, `tests/unit/sandbox/host/test_cache_lock.py` (cross-platform matrix).
- `tests/integration/test_buildkit_builder_bootstrap.py` (Gap 7) — fresh-runner fixture asserts `codegenie-distroless` builder is created idempotently.
- `tests/integration/test_cache_lock_matrix.py` (Gap 2) — same scenario under macOS BSD flock + Linux fcntl + `pyfilelock`.

**Done criteria:**
- [ ] All four `tools/*.py` wrappers return Pydantic models; no caller parses raw subprocess output.
- [ ] `cache_lock` test matrix green on macOS + Linux CI.
- [ ] `render_base_catalog()` produces a JSON file that round-trips through `read_base_catalog()` and matches the `tools/contract-surface.snapshot.json#base_catalog` shape.
- [ ] Builder-bootstrap integration test green on a runner where `codegenie-distroless` does not pre-exist.
- [ ] `mypy --strict` clean on `src/codegenie/tools/`, `src/codegenie/sandbox/host/cache_lock.py`, `src/codegenie/catalogs/distroless/`.

**Depends on:** Step 1 (contract surface frozen so `tools/*` callers cannot accidentally widen it).

**Effort:** M — five wrappers + a hot-view renderer + cross-platform locking is real work but contained.

**Risks specific to this step:** `pyfilelock` and native `fcntl.flock` semantics may diverge on edge cases (shared mode, fork inheritance); document the divergence in `cache_lock.py` docstring rather than papering over it.

---

## Step 3 — Land `BaseImageProbe` and `ShellInvocationTraceProbe` with their signal collectors

**Goal:** The two new probes exist, register correctly (one gather-time via `@register_probe`, one gate-time via `@register_gate_probe`), emit facts not judgments, and the four new `@register_signal_kind` collectors light up `ObjectiveSignals`'s new optional fields.

**Features delivered:**
- `src/codegenie/probes/base_image.py` (Layer-C, `@register_probe`, `applies_to_tasks=["distroless_migration","vuln_remediation"]`).
- `src/codegenie/probes/shell_invocation_trace.py` (`@register_gate_probe`, `applies_to_tasks=["distroless_migration"]`, 30s budget).
- **Strace runs in a sibling sidecar container** (per Gap 4) — `docker run --pid=container:<candidate> codegenie-strace-sidecar:<pinned-digest>`; sidecar image pinned in `tools/digests.yaml#sandbox.strace_sidecar`.
- `src/codegenie/sandbox/signals/dive.py` — advisory-only collector (`passed=True` always; closes critic sec.3).
- `src/codegenie/sandbox/signals/shell_presence.py` — strict-AND collector projecting on the dive result (no second dive invocation).
- `src/codegenie/sandbox/signals/shell_invocation_trace.py` — strict-AND collector projecting `ShellInvocationTraceProbe` output.
- `src/codegenie/sandbox/signals/base_image.py` — gate-time projection of `BaseImageProbe` for audit-chain consumption.
- Pydantic signal models (`DiveSignal`, `ShellPresenceSignal`, `ShellInvocationTraceSignal`, `BaseImageSignal`) registered in `src/codegenie/sandbox/signals/models.py` (the additive widening landed in Step 1).
- Unit tests per `phase-arch-design.md §Testing strategy ›Unit tests`: `test_base_image.py` (≥14), `test_shell_invocation_trace.py` (≥10), four `test_*_signal.py`.
- **Intent tests** (Rule 9): `test_base_image_emits_facts_not_judgments` and `test_shell_trace_emits_facts_not_judgments` — assert no output field name contains `is_*|safe_*|recommended_*`.
- `tests/integration/test_strace_sidecar_pid_share.py` (Gap 4) — asserts sidecar PID-shares with candidate and PID 1 in the candidate is *not* strace.
- `tests/integration/test_strace_idempotent.py` — re-running the trace on the same candidate digest produces the same `runtime_shell_count`.
- `tests/integration/test_objective_signals_widening_compat.py` (Gap 3) — `TrustScorer.score(signals)` and `StrictAndGate.evaluate(signals, ctx)` handle every populated/non-populated combination of the new four fields without exception.

**Done criteria:**
- [ ] Both probes register at import time; `all_gate_probes()` returns exactly one entry (`ShellInvocationTraceProbe`); Phase 2 coordinator does not see it (asserted by a coordinator-import test).
- [ ] Strace sidecar PID-share test green; candidate's PID 1 is the candidate's own entrypoint, not strace.
- [ ] Advisory `dive` collector returns `passed=True` even when `size_ratio_post_pre > 1.0`.
- [ ] `ObjectiveSignals` widening compat test green for v0.6-shape (all-None) *and* v0.7-shape (all four fields populated) fixtures.
- [ ] Idempotence integration test green: re-tracing same image digest produces byte-identical `ShellInvocationTrace`.
- [ ] Phase 2 `RuntimeTraceProbe` stub still resolves to `applies() = False` (ADR-P7-005 preserved).

**Depends on:** Steps 1 (registries, signal-model widening) and 2 (tool wrappers, sidecar digest pinned).

**Effort:** L — strace + DinD + sidecar PID-share is the most subtle work in the phase.

**Risks specific to this step:** Strace under DinD on macOS will hit subtle PID-namespace issues; budget extra time for the sidecar test on M-series Macs. The 30s budget may be too tight on cold paths — Step 8's empirical canary calibrates.

---

## Step 4 — Land `DockerfileRecipeEngine`, `DockerfileBaseImageSwapTransform`, and the multi-stage refactor recipe

**Goal:** The recipe path can match a distroless target, mutate the Dockerfile AST deterministically, round-trip safely, and produce a clean `git format-patch` — for both single-stage swap and multi-stage refactor — without OpenRewrite.

**Features delivered:**
- `src/codegenie/recipes/engines/dockerfile_engine.py` — implements `RecipeEngine` ABC; strict AST mutation; round-trip safety assertion (`parse(serialize(parse(x))) == parse(x)`); byte-only canonicalization (LF + trailing-whitespace strip — no semantic rewrites); deterministic `git format-patch` with fixed bot identity.
- `src/codegenie/transforms/dockerfile_base_image_swap.py` — implements `Transform` ABC; `applies_to_tasks=["distroless_migration"]`; uses `git worktree add`.
- `src/codegenie/recipes/catalog/docker/` — two seed recipes: `swap_base_image_single_stage.yaml` (Node Express path) and `multi_stage_distroless_refactor.yaml` (Go static binary path); both `engine: "dockerfile"`.
- Unit tests: `test_dockerfile_engine.py` (≥12, includes Hypothesis round-trip), `test_dockerfile_base_image_swap.py` (≥8).
- Property tests: `tests/property/test_dockerfile_engine_roundtrip.py` (G14), `tests/property/test_dockerfile_engine_idempotent.py`.
- Golden files: `tests/golden/dockerfile_swap_node20.patch`, `tests/golden/dockerfile_multistage_go.patch` (updatable via `pytest --update-golden`).

**Done criteria:**
- [ ] `DockerfileRecipeEngine.available()` returns `True` iff `dockerfile-parse` importable AND `docker buildx` on `$PATH`.
- [ ] Round-trip property holds on the adversarial corpus stubbed in Step 6 (initially passes on a small fixture set; full corpus lights up in Step 6).
- [ ] Five-run determinism: applying either seed recipe five times produces byte-identical patches (no `random` / no `time` / no env-dependent ordering).
- [ ] Two golden patches match exactly on the Express + static-Go fixtures.
- [ ] `RoundTripFailure`, `DockerfileRejected`, `WorktreeContaminated` all raise loudly (no silent `False` returns).
- [ ] Fence-CI confirms no `anthropic|chromadb|sentence-transformers` imports under `recipes/` or `transforms/`.

**Depends on:** Steps 1 (Literal extended), 2 (`dockerfile-parse` wrapper).

**Effort:** M — the round-trip property is the load-bearing test; once it's green the rest is mechanical.

**Risks specific to this step:** `dockerfile-parse`'s serializer is *not* round-trip-stable for some inputs (e.g., embedded heredocs); the recipe must reject these cleanly rather than producing a corrupt patch. Initial fixtures may be too permissive — Step 6's corpus will surface the gaps.

---

## Step 5 — Land `DistrolessLedger`, `build_distroless_loop()`, `cli/migrate.py`, and run the Node.js Express end-to-end

**Goal:** A new operator can run `codegenie migrate <repo> --target distroless --cve <id>` against the Express fixture and get a Chainguard distroless PR-ready patch through the recipe path — closing roadmap exit criterion G5.

**Features delivered:**
- `src/codegenie/graph/state_distroless.py` — `DistrolessLedger` (`extra="forbid"`, `schema_version: Literal["v0.7.0"]`), `TargetImageRecommendation`, `MigrationReport` Pydantic models.
- `src/codegenie/graph/nodes/distroless/` — 11 node modules: `ingest_target`, `resolve_target_image` (mmap-reads `base_catalog.json`; image-name allowlist regex enforced here), `select_recipe`, `rag_lookup`, `replan_with_phase4` (passes `task_type="distroless_migration"`), `apply_recipe`, `validate_in_sandbox`, `record_attempt`, `emit_artifact`. (`await_human` and `escalate` are imported verbatim from Phase 6.)
- `src/codegenie/graph/distroless_loop.py` — `build_distroless_loop(checkpointer, max_attempts, force_rebuild)` factory; same module-level singleton + `(id(checkpointer), max_attempts)` cache key as Phase 6; `interrupt_before=["await_human"]`.
- `src/codegenie/graph/edges.py` extended additively with `route_after_resolve_target` `@pure_edge` predicate (returns `Literal["ok","catalog_miss"]`). **Note:** this is an *additive function in an existing file* — verify against ADR-P7-001..006 to confirm it falls under the seam set; if not, file a `route_after_resolve_target` *new file* under `graph/edges_distroless.py` to honor "new files only" except where ADR'd.
- `src/codegenie/cli/migrate.py` — Click verbs: `run`, `resume`, `inspect`, `replay`, `render`. `workflow_id = blake3(f"{repo_root_blake3}|wf:distroless:{advisory_canonical_id or target_image}".encode())[:16]` (per Gap 1 — `wf:<task>:` prefix prevents cross-task chain-head collisions).
- `tests/fixtures/repos/express-distroless/` — Node Express service with `node:20-bullseye-slim` base.
- `tests/integration/test_migrate_node_e2e.py` — **G5 / roadmap exit-criterion test.** Recipe match → buildkit build → grype non-positive CVE delta → dive reports no `/bin/sh` → `runtime_shell_count == 0` → patch produced + golden match.
- `tests/integration/test_chain_no_collision_across_tasks.py` (Gap 1) — launches one vuln + one distroless workflow with intentionally identical `<run-id>` and asserts audit chains live in disjoint directories.
- `tests/integration/test_migrate_replay_after_kill.py` — SIGKILL during `validate_in_sandbox`; resume produces byte-identical final state.
- Unit tests: `test_distroless_state.py`, `test_distroless_edges.py`, `test_migrate_cli.py`.
- Golden file: `tests/golden/distroless_loop_topology.json`, `tests/golden/migration_report_node_e2e.yaml`.

**Done criteria:**
- [ ] `codegenie migrate <express-fixture> --target distroless --cve CVE-2025-XXXX` exits 0 and produces `.codegenie/migration/<run-id>/migration-report.yaml` matching the golden.
- [ ] Recipe path runs: `last_engine == "dockerfile_recipe"`.
- [ ] `grype` CVE delta on the candidate image is `≤ 0` vs the pre-image.
- [ ] `ShellInvocationTraceProbe` reports `runtime_shell_count == 0`, `confidence == "high"`.
- [ ] `dive` reports no `/bin/sh` in the final image layer.
- [ ] Replay-after-SIGKILL test green; byte-identical final ledger.
- [ ] Cross-task chain-no-collision test green.
- [ ] CLI exit codes match Phase 6: `0` ok / `11` escalate / `12` paused / `13` checkpoint tampered / `1` unexpected.

**Depends on:** Steps 1–4.

**Effort:** L — biggest step; ties all earlier components together, lands the E2E exit-criterion test.

**Risks specific to this step:** First end-to-end run will surface latent bugs in tools/wrappers; budget time for Step 2/3 fixes. The Express fixture's `node:20-bullseye-slim` base must be `docker pull`-able from CI runners.

---

## Step 6 — Broaden coverage: adversarial Dockerfile corpus, second E2E fixture, HITL path, LLM-fallback path

**Goal:** Every edge case in `phase-arch-design.md §Edge cases` (≥16 entries), the ≥30-fixture adversarial corpus (G13), and the three non-happy-path E2E flows (multi-stage Go, shell-required HITL, recipe-miss LLM fallback) are exercised.

**Features delivered:**
- `tests/adversarial/dockerfiles/` — ≥30 fixtures per G13 list (BOM, UTF-16-LE/BE, CR/CRLF, `ONBUILD`, 2 MB, parse-bomb, NFC/NFKC, hidden `\r`, Windows-1252, embedded null, 100 MB, 200-stage, `#syntax=` directive, `FROM scratch`, multi-platform `FROM`, prompt-injection in `LABEL`/`RUN`, etc.).
- Property tests over the corpus: round-trip equivalence (G14); image-name allowlist Hypothesis test (`tests/property/test_image_name_allowlist.py`); ledger serialization (`tests/property/test_distroless_ledger_serialization.py`); gate predicates (`tests/property/test_gate_predicates.py`).
- `tests/fixtures/repos/static-go-distroless/` — multi-stage Go service; `tests/integration/test_migrate_static_go_e2e.py`.
- `tests/fixtures/repos/shell-required-distroless/` — Node service whose `/admin` route shells out; `tests/integration/test_migrate_shell_required_hitl.py` (assert `await_human` interrupt; mocked `HumanDecision(action="abort")` aborts cleanly).
- `tests/fixtures/repos/heredoc-buildkit-distroless/` — BuildKit heredoc; asserts `parser_skipped_lines > 0` → recipe miss.
- `tests/fixtures/repos/alpine-to-glibc-distroless/` — image-grows-legitimately fixture (closes critic sec.3).
- `tests/integration/test_migrate_recipe_miss_llm_fallback.py` — recipe miss → RAG miss → `FallbackTier.run(task_type="distroless_migration")` (cassette-driven); asserts $≤ $0.12 (G9) and produces a distroless-shaped patch.
- `tests/integration/test_rag_distroless_top1.py` — distroless query returns distroless example as top-1 (Risk #2 mitigation).
- `tests/integration/test_phase4_task_type_mismatch_safety.py` (Gap 6) — vuln advisory + `task_type="distroless_migration"` → loud failure (either gate fail or `OutputValidator` rejection).
- `tests/integration/test_supervisor_logs_task_type.py` — `xfail` until Phase 8 ships; defining it now blocks Phase 8 from regressing.
- `tests/adversarial/typosquat_lookup.py` — `cgr.dev/chamguard/...` rejected by allowlist regex.
- `tests/adversarial/build_egress_blocked.py` — `RUN curl https://evil.test/` → egress proxy drops; `sandbox.egress.blocked` audit event recorded.
- New prompt template: `src/codegenie/planner/prompts/migration_distroless.v1.yaml` (schema-validated, version-pinned; loaded when `task_type="distroless_migration"`).
- Vector store collection: `distroless_solved_examples_promoted` seeded with ≥3 hand-curated examples for RAG retrieval.

**Done criteria:**
- [ ] ≥ 30 adversarial Dockerfile fixtures present; every fixture either parses cleanly or is rejected with a documented `dockerfile.parse_rejected` reason code.
- [ ] Round-trip property holds on every fixture in the corpus.
- [ ] Static-Go E2E green; multi-stage refactor recipe matches and produces golden patch.
- [ ] Shell-required HITL E2E green; `await_human` fires with the correct `HumanRequest.reason`.
- [ ] LLM-fallback E2E green; cassette-driven, asserts `≤ $0.12`.
- [ ] Task-type mismatch safety test green (vuln + distroless task_type fails loudly).
- [ ] Distroless RAG top-1 test green.
- [ ] Adversarial typosquat + egress-block tests green.
- [ ] `migration_distroless.v1.yaml` prompt template schema-validates.

**Depends on:** Steps 1–5.

**Effort:** L — corpus authoring + four fixture repos + a real cassette is the bulk-volume work in the phase.

**Risks specific to this step:** Cassette recording for the LLM-fallback E2E needs a real `anthropic` call once; cassette format drift between cassette-record and cassette-replay environments may show up. Adversarial corpus may surface a `dockerfile-parse` bug that requires upstream pinning or a workaround.

---

## Step 7 — Wire the wall-clock + performance canaries and the fence-CI extension

**Goal:** The regression-suite wall-clock canary, buildkit cache hit rate, workflow throughput, dockerfile engine p95, and strace budget distribution tests are green at the baseline values pinned in `phase-arch-design.md §Goals`.

**Features delivered:**
- `tests/perf/test_regression_suite_wall_clock.py` (G12) — p50 ≤ 4 min, p95 ≤ 7 min; uses `pytest -n auto`; baseline at `tests/perf/baseline.json`; `pytest --update-perf-baseline` flag for deliberate bumps.
- `tests/perf/test_buildkit_cache_hit_rate.py` (G10) — ≥ 85% pulled-layer + ≥ 60% derived-layer after 3-fixture warm-up run.
- `tests/perf/test_workflow_throughput.py` (G6/G7) — 6 cold + 24 warm distroless workflows on Linux DinD; ≥ 10/hr mixed-portfolio warm.
- `tests/perf/test_dockerfile_engine_p95.py` — round-trip p95 ≤ 100 ms.
- `tests/perf/test_strace_budget_distribution.py` (Risk #3) — warns if empirical p95 entrypoint-steady-state > 24 s (signals the 30 s budget needs raising).
- `tests/e2e/test_mixed_portfolio_warm.py` (G7).
- Fence-CI extension config: deny `anthropic|chromadb|sentence-transformers` imports under `src/codegenie/{probes,transforms,recipes,catalogs}/`.
- Per-worker steady-state memory measurement integrated into the throughput test (G11 — ≤ 2.4 GB).

**Done criteria:**
- [ ] Wall-clock canary baseline pinned in `tests/perf/baseline.json`; canary green on CI.
- [ ] Buildkit cache hit rate ≥ 85% pulled / ≥ 60% derived asserted on 2nd-and-after run.
- [ ] Cold throughput ≥ 6/hr, warm distroless-only ≥ 24/hr, warm mixed ≥ 10/hr on the reference Linux DinD runner.
- [ ] Dockerfile engine p95 ≤ 100 ms.
- [ ] Strace budget distribution test runs and emits empirical p50/p95 (warning only — informational for Phase 13).
- [ ] Per-worker steady-state memory ≤ 2.4 GB recorded.
- [ ] Fence-CI extension blocks a synthetic PR that imports `anthropic` under `recipes/`.

**Depends on:** Steps 1–6 (all functional code complete).

**Effort:** M — measurement infrastructure, not new feature code; the work is calibrating thresholds.

**Risks specific to this step:** Reference-runner choice matters; baseline locked to a CI runner class. Document the runner in `tests/perf/baseline.json`'s metadata so future bumps are honest.

---

## Step 8 — Pre-flight final regression and snapshot-discipline rehearsal

**Goal:** Before the merge button is touched, every gate that the merge depends on is exercised end-to-end and verified to fail loudly when broken — including the snapshot-canary discipline itself.

**Features delivered:**
- `tests/integration/test_phase3_4_5_6_unchanged.py` — full Phase 3/4/5/6 integration suite re-imported verbatim (G4 hard merge gate).
- `tests/graph/test_pep_no_O_optimizations.py` — extended from Phase 6 to cover `route_after_resolve_target` and any other Phase 7 `@pure_edge`s.
- `tests/integration/test_grype_db_concurrent_refresh.py` — macOS BSD flock + Linux fcntl matrix.
- Two manual rehearsal PRs (locally, not merged) to validate Step 1's discipline:
  - Rehearsal A: a no-op edit to a Phase 0–6 file that is *not* one of the six seams — verify `test_contract_surface_snapshot.py` fires and `tools/snapshot_regen_audit.py` blocks the PR.
  - Rehearsal B: a legitimate additive snapshot regen — verify `pytest --update-contract-snapshot` produces a clean diff and the audit script accepts the PR when the ADR is updated in the same change.
- Documentation: `docs/phases/07-migration-task-class/operator-notes.md` — how operators set up `~/.docker/config.json` for `cgr.dev`; how to bump `gate.shell_trace.budget_s`; how to run `pytest --update-contract-snapshot`. *(Skip if the repo convention is no operator docs at this phase; defer to Phase 11.)*

**Done criteria:**
- [ ] Full Phase 3/4/5/6 integration suite green verbatim — no edits.
- [ ] All G4-gating tests are in CI's `merge` lane.
- [ ] Rehearsal A fails CI as expected; Rehearsal B passes.
- [ ] `python -O` startup test fails loudly (assertions stripped) — protects `@pure_edge`.
- [ ] Grype-DB concurrent-refresh matrix green on both macOS + Linux runners.
- [ ] PR description links every ADR-P7-001..007 and the ADR-0028 amendment.

**Depends on:** Steps 1–7.

**Effort:** S — execution, not authoring.

**Risks specific to this step:** Flake on the perf canaries under CI load; if so, defer flaky test gating to soft-fail and raise as a Phase 7.1 follow-up rather than weakening the assertions.

---

## Exit-criteria mapping

Per the roadmap (verbatim) and the synthesis ledger's named amendment.

| Exit criterion | Step(s) |
|---|---|
| **Both task classes run from the same orchestration substrate** (vuln via `codegenie loop`; distroless via `codegenie migrate`; same `AuditedSqliteSaver`, BLAKE3 audit chain, `HumanRequest`/`HumanDecision`; G1). | Steps 1, 5 |
| **The diff for this phase touches only new files — no Phase 0–6 source code is modified** — *amended (ADR-0028 amendment) to "new files plus six ADR-gated additive seams (ADR-P7-001..006), each regenerating the contract-surface snapshot in the same PR"* (G2, G3). | Step 1 (lands the seams, ADRs, snapshot canary); Step 8 (rehearses the discipline) |
| **The full vuln-remediation regression suite runs as a hard gate before merging this phase** (G4). | Step 8 |
| **End-to-end test migrates a Node.js service with a vulnerable base image to a Chainguard distroless image** (G5). | Step 5 |
| Throughput G6/G7, time-to-PR G8, $/PR G9, cache hit rate G10, memory G11. | Step 7 |
| Regression-suite wall-clock canary G12 (permanent). | Steps 1 (snapshot canary), 7 (wall-clock canary) |
| Adversarial Dockerfile corpus ≥ 30 (G13); round-trip safety property (G14). | Steps 4 (engine property), 6 (full corpus) |
| `ShellInvocationTraceProbe` gate-time-only via `@register_gate_probe` (G15); `dive_efficiency` advisory (G16). | Steps 1, 3 |
| Operator-side credentials only (G17); zero LLM tokens inside Phase 7 boundary (G18). | Steps 1, 2, 7 (fence-CI) |
| No new ABCs, no new top-level packages, no Phase 2 coordinator / Phase 6 `cli/loop.py` edits, no rootfs bump (G19). | Step 1 (snapshot canary structurally enforces) |
| Handrolled-only recipes (G20); OpenRewrite deferral. | Step 4; ADR-P7-004 |

Every step traces to at least one exit criterion. The snapshot canary is the *enforcement* mechanism for G2/G3/G19; the per-phase ADR-0028 amendment is the *definition* of "extension by addition" for this and every later phase.

---

## Implementation-level risks

Distinct from `phase-arch-design.md §Risks` (which lists design-level risks). These are about *the work*:

1. **ADR-0028 amendment gets stuck in review.** The amendment changes the meaning of the load-bearing commitment in `CLAUDE.md` / production design. If review pushback delays it, every later step is blocked because the six seams cannot land without the production-ADR amendment as their justification. **Signal:** Step 1 PR sits in review > 1 week. **Action:** Pre-write the rationale (it's in `final-design.md §Synthesis ledger ›Departures #3`); if reviewers prefer the strict zero-edit alternative, fall back to `final-design.md §Departures #5` (parallel `MigrationFallbackTier`, parallel engine enum) and re-plan from Step 2.
2. **Snapshot canary over-fires on legitimate refactors during Phase 7 itself.** The same engineer making the changes is also responsible for amending the snapshot. Fatigue erodes discipline. **Signal:** Snapshot regens are committed without an accompanying ADR change. **Action:** `tools/snapshot_regen_audit.py` (Gap 5) is the *mechanical* defense; review the CI logs for snapshot diffs at each step boundary to make sure no inadvertent contract change slipped through.
3. **`docker buildx` + `dive` + `strace` toolchain pinning drift across CI runners.** `tools/digests.yaml` is the single source of truth for tool digests, but CI runner images can pre-bake versions that mask drift. **Signal:** Step 5 E2E green locally, red on CI, with subtle error messages. **Action:** Pin every binary by digest in `tools/digests.yaml`; runner image rebuild on every digest bump; document in operator-notes.
4. **Round-trip safety property breaks on a `dockerfile-parse` upstream change.** The library is single-maintained and brittle on edge cases (BuildKit heredocs especially). **Signal:** Step 4 property test red on a Hypothesis-generated input that previously passed. **Action:** Pin `dockerfile-parse` version in `pyproject.toml`; if a real bug is found, reject the input via the strict-mode parser rather than working around it; document the bug class in the adversarial corpus.
5. **Strace sidecar's 30 s budget too tight under DinD on M-series Mac developers.** Recipe authoring and local testing happen on the developer's Mac, not on the Linux reference runner. **Signal:** Step 5 E2E green on Linux CI, intermittently red on Mac local. **Action:** `gate.shell_trace.budget_s` is the configurable in `tools/digests.yaml`; raise locally without changing the CI baseline; Step 7's empirical distribution test surfaces if 30 s needs to be bumped on the reference runner too.
6. **Phase 2 coordinator regression hidden by registry separation.** `@register_gate_probe` lives in a separate registry, but the Phase 2 `Probe` ABC is *shared*. An invariant change at the ABC level (e.g., a default-method override) would silently break gate probes without firing the snapshot canary, which tracks the ABC signature but not behavior. **Signal:** Step 3 unit tests green, but Step 5 E2E fails inside `ShellInvocationTraceProbe.run()`. **Action:** `tests/unit/probes/test_gate_registry_isolation.py` asserts `all_gate_probes()` exists, returns the expected names, and the Phase 2 coordinator's `all_probes()` does not include them. Land this assertion in Step 1.
7. **`cgr.dev` cold-pull rate-limit on shared CI runners.** Chainguard's public registry rate-limits unauthenticated pulls; CI runners that don't carry credentials hit the limit and Step 5's E2E flakes. **Signal:** E2E intermittent red with `429 Too Many Requests`. **Action:** Document operator-side `~/.docker/config.json` for CI runners; if needed, add `codegenie cache prewarm cgr.dev` (the deferred ~30 LOC) as a Phase 7.1 follow-up.

---

## What's next — handoff to Phase 8

What's materially different about the system after this phase ships, and what Phase 8 (Hierarchical Planner + pre-rendered Redis hot views) will pick up:

- **New artifacts now on disk:**
  - `.codegenie/migration/checkpoints/<workflow_id>.sqlite3` — distroless workflow checkpoints; `workflow_id = blake3(...|wf:distroless:...)[:16]` (per Gap 1). Phase 8's supervisor `inspect`s either vuln or distroless checkpoints uniformly via the existing `AuditedSqliteSaver` ABC.
  - `.codegenie/migration/<run-id>/migration-report.yaml` — per-run distroless report; Phase 11 (Handoff) will translate to GitHub PR body; Phase 13 (cost ledger) reads cost figures from it.
  - `.codegenie/cache/base_catalog.json` — pre-rendered hot view; **shape-compatible with Phase 8's Redis hot view (ADR-0013).** Phase 8 lifts the file into Redis without schema work.
- **New contracts ready for consumers:**
  - `DistrolessLedger` (`schema_version: Literal["v0.7.0"]`, `extra="forbid"`) — Phase 8's supervisor `model_validate_json`s both `DistrolessLedger` and `VulnLedger` to determine `task_type` and dispatch.
  - `FallbackTier.run(..., task_type: str | None = None)` — Phase 8's supervisor passes `task_type` per dispatched workflow (ADR-P7-003).
  - `@register_gate_probe` registry — Phase 8 (or any later phase) registers new gate probes via the same decorator (ADR-P7-001).
  - `BaseImageSignal`, `DiveSignal`, `ShellPresenceSignal`, `ShellInvocationTraceSignal` — Phase 8 reads them from the gate audit chain for ROI scoring.
  - `MigrationReport` Pydantic — Phase 11 + Phase 13 consume.
- **New CI gates in place:**
  - `tests/integration/test_contract_surface_snapshot.py` — permanent; Phase 8 is the *first* phase that intentionally amends the snapshot for a non-Phase-7 reason. Phase 8's first PR is the live test of the discipline.
  - `tools/snapshot_regen_audit.py` — GitHub Actions enforces ADR-linked snapshot regens forever.
  - `tests/perf/test_regression_suite_wall_clock.py` — permanent p50/p95 wall-clock canary.
  - Fence-CI extension blocks LLM-SDK imports under `probes/`, `transforms/`, `recipes/`, `catalogs/`.
- **Implicit assumptions Phase 8 can now make:**
  - Both `build_vuln_loop` and `build_distroless_loop` have identical factory signatures `(checkpointer, max_attempts, force_rebuild) -> CompiledGraph` — the supervisor calls one or the other on `task_type`.
  - `HumanRequest`/`HumanDecision` JSON contract (`docs/contracts/hitl-v0.6.0.json`) is unchanged and dispatchable uniformly.
  - Phase 5's `@register_signal_kind` open registry is the extension point; no new mechanism needed.
  - The contract-surface snapshot is the *enforcement* of behavior-preserving additive extension. Phase 8 inherits the discipline mechanically.
- **Acknowledged debt Phase 8 inherits (named in `phase-arch-design.md §Integration with Phase 8`):**
  - Two ledgers (`VulnLedger`, `DistrolessLedger`) — ADR-0022 Three Strikes; strike two. Phase 8 (or Phase 15) does the merge.
  - Two CLI verbs (`codegenie loop`, `codegenie migrate`) — Phase 8's supervisor unifies the operator surface.
  - Two `last_engine` Literal value sets (`"recipe"` vs `"dockerfile_recipe"`) — unification needed for cross-task ROI.
  - `tests/integration/test_supervisor_logs_task_type.py` is `xfail` today; Phase 8 must make it green to ship.
