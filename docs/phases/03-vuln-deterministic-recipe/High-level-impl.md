# Phase 03 — Vuln remediation: deterministic recipe path: High-level implementation plan

**Status:** Implementation plan
**Date:** 2026-05-17
**Architecture reference:** [phase-arch-design.md](phase-arch-design.md)
**ADRs:** [ADRs/](ADRs/)
**Source design:** [final-design.md](final-design.md)
**Roadmap reference:** [docs/roadmap.md](../../roadmap.md) §"Phase 3"

## Executive summary

Phase 3 lands the first **plugin** (`vulnerability-remediation--node--npm`), the **universal HITL fallback**, and the Phase-5-named contract seams (`RemediationOrchestrator`, `TrustScorer`, `Transform` ABC, `ApplyContext`, `RecipeEngine`, `remediation-report.yaml`). The central work shape is *contracts before adapters, adapters before consumers, fixtures before claims*: every typed primitive — newtype IDs, tagged unions, Pydantic models — ships in Step 1 with the CI fences that will refuse to let later steps degrade them; the `Plugin`/`PluginRegistry` kernel and the `SubprocessJail` Port ship before any plugin or adapter that depends on them; the first end-to-end `npm install` + `npm test` against a real Express CVE fixture is gate Step 6, not Step 9. By the time the third synthetic plugin lands in Step 7, the plugin contract has already been bake-tested through three loaders, the two-stream event log is the canonical replay primitive, and Phase 4 / Phase 5 / Phase 6.5 each have an unedited surface to consume.

## Order of operations

**Domain primitives → kernel → Port → contract surface → end-to-end vertical slice → third plugin → fixture portfolio → CI gates.** Rationale: the ADR-0033-anchored newtypes and tagged unions are the load-bearing type vocabulary every later module references; landing them in Step 1 with `mypy --strict` + `ruff check` + the LLM-SDK-fence import-linter contract means later steps cannot silently widen `str` to `WorkflowId` or smuggle `Any` past `extra="forbid"`. The `Plugin`/`PluginRegistry` kernel (Step 2) and `SubprocessJail` Port (Step 4) precede any concrete plugin or adapter because hexagonal port-before-adapter is non-negotiable: an adapter coded against a not-yet-stable Protocol pays for itself twice. The first vertical slice (Step 6) chooses the headline Express CVE so the roadmap exit criterion is exercised the moment the orchestrator can run end-to-end, not in a final integration step. The third synthetic plugin (Step 7) bake-tests the contract while edits are still cheap, before Phase 7 ships the distroless plugin under the "zero edits" rule. Fixture portfolio (Step 8) and CI gates / bench backfill (Step 9) come last because they test properties of an already-working system. The pattern-driven sequencing constraints — **newtypes in Step 1**, **registry-before-plugins** (Step 2 → Step 7), **ports-before-adapters** (Step 4 internal), **tagged-unions-before-state-machines** (Step 1 → Step 6), and **type-strict from day 1** (Step 1's done criteria, not bolted on) — drive the whole sequence.

## Step 1 — Scaffold packages, domain primitives, sum types, and structural CI fences

**Goal:** Every typed primitive Phase 3 ever uses exists in code with `extra="forbid"` enforcement, `mypy --strict` clean, and CI fences that block regression — before any orchestrator or plugin logic lands.

**Features delivered:**
- `src/codegenie/plugins/__init__.py` and `src/codegenie/transforms/__init__.py` packages created.
- `src/codegenie/types/identifiers.py` extended with `PluginId`, `RecipeId`, `TransformId`, `WorkflowId`, `EventId`, `CveId`, `PackageId`, `BranchName`, `BlobDigest`, `RegistryUrl`, `SignalKind`, `PrimitiveName`, `TransformKind`, `AttemptNumber` (all `NewType` + smart-constructor wrappers returning `Result[T, ParseError]`).
- `src/codegenie/plugins/scope.py`: `ScopeDim = Concrete | Wildcard` sum type, `PluginScope` dataclass, `PluginScope.parse(s) -> Result[PluginScope, ParseError]`.
- `src/codegenie/transforms/apply_context.py`: `ApplyContext` + `AttemptSummary` Pydantic models (Phase 5 reads `prior_attempts: list = []` already).
- `src/codegenie/transforms/transform.py`: `Transform` ABC + `TransformProvenance` Pydantic.
- `src/codegenie/transforms/outcomes.py`: `RecipeOutcome` (`Applied | Skipped | NotApplicable | Failed`), `RemediationOutcome` (`Validated | RequiresHumanReview | NotApplicable | Failed`), `NodeTransition` (`Advance | ShortCircuit | Escalate`), `AdapterConfidence` (`High | Degraded | Unavailable`), `Applicability` (`Applies | NotApplies`) — every one a Pydantic discriminated union with `Discriminator("kind")`.
- `src/codegenie/plugins/resolution.py`: `ConcreteResolution | UniversalFallbackResolution` sum.
- `tools/lint/importlinter.cfg` amended with Phase 3 LLM-SDK contracts covering `src/codegenie/{plugins,transforms}/` and `plugins/`.
- `tests/fence/test_no_llm_in_transforms.py`: runtime-closure scan of the Phase 3 surface against `FORBIDDEN_LLM_SDKS`.
- `tests/fence/test_no_any_in_plugin_surface.py`: AST-walk asserting no new `Any` or `dict[str, Any]` annotations under `src/codegenie/{plugins,transforms}/`.
- `tests/fence/test_kernel_frozen.py`: git-diff Phase 0/1/2 file list against ADR-anchored allowlist (only `ALLOWED_BINARIES` and `import-linter` edits permitted).

**Done criteria:**
- [ ] `make check` green with the new packages present (lint, typecheck, test, fence).
- [ ] `make lint-imports` green with the new Phase 3 contracts.
- [ ] `pytest tests/unit/types/test_identifiers_phase3.py` covers smart-constructor round-trip + parse-error variant for every newtype.
- [ ] `pytest tests/unit/plugins/test_scope.py` covers `Concrete | Wildcard` `matches(...)` algebra and `specificity()` partial order via a Hypothesis property test.
- [ ] `mypy --strict src/codegenie/plugins src/codegenie/transforms` clean.
- [ ] `tests/fence/test_no_any_in_plugin_surface.py` fails on a deliberately-planted `dict[str, Any]` and is removed once verified.
- [ ] Every sum-type module is consumed by at least one `match` statement with `assert_never` (verified by `tests/unit/transforms/test_exhaustiveness.py`).

**Depends on:** Phase 0/1/2 packages on disk (`codegenie.types.identifiers`, `codegenie.exec`, `codegenie.output.sanitizer`).

**Effort:** M — mechanical but volume is high (13 newtypes + 6 sum types + 5 fence tests).

**Risks specific to this step:** Existing Phase 0/1/2 code may already use raw `str` for some IDs Phase 3 newtypes (e.g., `WorkflowId` does not exist yet). Audit before introducing; if a collision is found, surface it as a follow-up cleanup ticket — do NOT refactor Phase 0/1/2 code inside this step (G6 forbids it).

## Step 2 — Plugin Registry kernel, manifest schema, loader, resolver

**Goal:** The closed-for-modification ADR-0031 kernel exists and resolves a `PluginScope` against zero, one, or many plugins; `extends`-chain walking, cycle detection, integrity check, and `UniversalFallbackResolution` are all wired and tested.

**Features delivered:**
- `src/codegenie/plugins/protocols.py`: `Plugin` Protocol, `Adapter` Protocol, `RecipeEngine` Protocol.
- `src/codegenie/plugins/manifest.py`: `PluginManifest` Pydantic + `from_yaml(path) -> Result[PluginManifest, ManifestError]`.
- `src/codegenie/plugins/registry.py`: `PluginRegistry` class, module-level `default_registry`, `@register_plugin(plugin, *, registry=None)` decorator.
- `src/codegenie/plugins/resolver.py`: `(specificity desc, precedence desc, name asc)` resolution + `extends` walker (max depth 4, visited-set cycle check) + TCCM compose.
- `src/codegenie/plugins/loader.py`: filesystem walk over `plugins/*/plugin.yaml`, `importlib.import_module` per plugin, per-directory sha256 verification against `plugins/PLUGINS.lock` (relabeled "integrity check" not "signature").
- `src/codegenie/plugins/errors.py`: `PluginAlreadyRegistered`, `PluginExtendsCycle`, `PluginRejected`.
- `plugins/PLUGINS.lock` initial file (empty until Step 7 lands the first concrete plugin).
- `CODEOWNERS` entry for `plugins/PLUGINS.lock` (CODEOWNERS-gated edits).

**Done criteria:**
- [ ] `pytest tests/unit/plugins/test_registry.py` covers register/get/all + collision raises `PluginAlreadyRegistered`.
- [ ] `pytest tests/unit/plugins/test_resolver.py` covers: exact match > wildcard; precedence ties broken by name; no-match → `UniversalFallbackResolution` (NOT exception); extends chain at depth 4 ok / depth 5 raises; `A extends B extends A` raises `PluginExtendsCycle`.
- [ ] `pytest tests/unit/plugins/test_loader.py` covers: missing manifest, malformed YAML, `PLUGINS.lock` mismatch raise `PluginRejected` with exit code 4.
- [ ] Property test (Hypothesis): for any generated set of `PluginScope`s, the resolver returns either a `ConcreteResolution` whose `plugin.scope.matches(...)` is True or a `UniversalFallbackResolution`.
- [ ] Fresh-`PluginRegistry()` fixture isolation verified (no cross-test bleed via `default_registry`).
- [ ] `mypy --strict` clean on `src/codegenie/plugins/{protocols,registry,resolver,loader,manifest,errors}.py`.

**Depends on:** Step 1 (newtypes, `PluginScope`, sum types).

**Effort:** M — kernel must be right; resolver algorithm is small but the `extends` composition has corner cases.

## Step 3 — TCCM, `BundleBuilder`, `VulnIndex`, and content-addressed cache

**Goal:** A plugin can declare TCCM `must_read`/`should_read`/`may_read` queries; the builder dispatches them through Phase 2 language search adapters, returns a typed `Bundle`, and content-address-caches by an input fingerprint that includes `vuln_index.digest`.

**Features delivered:**
- `src/codegenie/plugins/tccm.py`: `TCCM`, `ContextQuery` Pydantic models (ADR-0029).
- `src/codegenie/vuln_index/`: sqlite `VulnIndex` (`lookup`, `affecting_range`, `digest`), Alembic migrations, NVD 2.0 / GHSA / OSV ingest with smart-constructor parsers (1 MiB / depth-16 caps).
- `codegenie vuln-index refresh` CLI subcommand.
- `src/codegenie/plugins/bundle.py`: `BundleBuilder.build(...)` with `asyncio.Semaphore(min(4, os.cpu_count()))`, `CODEGENIE_BUNDLE_CONCURRENCY` env override, deterministic serial fallback on `AdapterConfidence.Degraded` (NOT hedged race).
- `src/codegenie/plugins/cache.py`: BLAKE3 cache key `blake3(plugin_id || plugin_version || primitive || canonicalize(args) || repo_ctx.digest || scip.digest || dep_graph.digest || vuln_index.digest)`.
- `src/codegenie/plugins/cache_gc.py`: `BundleCacheGc` invoked once-a-day at orchestrator init via `.codegenie/cache/.gc-stamp`; operator-invoked via `codegenie cache prune`. (Gap 4 fix.)

**Done criteria:**
- [ ] `pytest tests/unit/plugins/test_bundle.py` covers cache-hit / cache-miss / `vuln_index.digest` invalidation; degraded adapter triggers declared fallback deterministically.
- [ ] Property test: `BundleCacheKey` round-trip — same inputs → same key over 50 randomized runs.
- [ ] Property test: serial-fallback semantics — across 100 runs with a `Degraded` primary adapter, the fallback is invoked exactly once per query (never raced).
- [ ] `pytest tests/unit/vuln_index/test_lookup.py` p99 < 10 ms over 100 lookups (advisory `bench`).
- [ ] `pytest tests/unit/vuln_index/test_parsers.py` covers NVD/GHSA/OSV parse + size/depth-cap rejection.
- [ ] `codegenie vuln-index refresh` end-to-end populates a test sqlite; `StaleVulnIndex` event emitted when `mtime > 7 days` (configurable via `CODEGENIE_VULN_INDEX_MAX_AGE_DAYS`).
- [ ] `codegenie cache prune` exits 0 and emits one `CacheGcCompleted` spanning event.

**Depends on:** Step 1 (newtypes, sum types), Step 2 (`Plugin` Protocol for `ConcreteResolution.composed_tccm` shape), Phase 2 search adapters (ADR-0032).

**Effort:** L — sqlite + three CVE-feed parsers + cache GC + concurrency primitive; volume dominates.

## Step 4 — `SubprocessJail` Port + `BwrapAdapter` (Linux) + `SandboxExecAdapter` (macOS) + `ALLOWED_BINARIES` amendment

**Goal:** Every Phase 3 subprocess (`npm install`, `npm test`, `git`) runs inside a network-namespaced, seccomp-filtered, tmpfs-rooted jail with typed env, typed network policy, and a typed tagged-union return. The Hexagonal Port Phase 5 will substitute with Firecracker / DinD is in place.

**Features delivered:**
- `src/codegenie/transforms/sandbox_jail.py`: `SubprocessJail` Protocol, `JailedSubprocessSpec` Pydantic, `JailedSubprocessResult = Completed | TimedOut | OomKilled | NetworkDenied | DiskQuotaExceeded` discriminated union, `NpmEnv | GitEnv` typed env wrappers, `NetworkPolicy = DenyAll | RegistryAllowlist(hosts)` sum.
- `src/codegenie/transforms/sandbox_path.py`: `SandboxedPath.create(jail, relative) -> Result[SandboxedPath, PathEscape]`; `.open(mode)` always `O_NOFOLLOW`.
- `src/codegenie/transforms/sandbox/bwrap.py`: `BwrapAdapter` — `bwrap --unshare-all --new-session --die-with-parent --ro-bind / / --tmpfs /tmp --bind <jail> <jail>`; seccomp blocks `mount`, `pivot_root`, `ptrace`, `bpf`, `unshare`, `keyctl`.
- `src/codegenie/transforms/sandbox/sandbox_exec.py`: `SandboxExecAdapter` — generates `tooling/sandbox/macos-npm.sb` per spec with `deny default` + explicit jail/registry allows.
- `src/codegenie/exec/__init__.py::ALLOWED_BINARIES` amended with `npm`, `bwrap`, `sandbox-exec`, `jq` (Phase 3 ADR-P3-008 amends 02-ADR-0001).
- `--ignore-scripts` enforced at both CLI (`npm install --ignore-scripts`) AND env (`npm_config_ignore_scripts=true`).
- `src/codegenie/plugins/capabilities.py`: `NpmInstallCapability`, `FsReadWriteCapability`, `GitLocalOpsCapability` (no `push` field — minting push is type-impossible), `CapabilityBundle`, single `mint(...)` entry point.
- `tooling/ruff_rules/no_capability_construction.py`: AST-walk fails on `*Capability(...)` construction outside `capabilities.py` or `tests/`.

**Done criteria:**
- [ ] `pytest tests/unit/transforms/test_sandbox_jail.py` covers every `JailedSubprocessResult` variant via a stub adapter.
- [ ] `pytest tests/integration/transforms/test_bwrap_hello_world.py` (Linux only, skipped elsewhere): `npm --version` runs inside `BwrapAdapter`; `curl github.com` returns `NetworkDenied` under `RegistryAllowlist(["registry.npmjs.org"])`.
- [ ] `pytest tests/integration/transforms/test_sandbox_exec_hello_world.py` (macOS only, skipped elsewhere) — same shape.
- [ ] `pytest tests/unit/transforms/test_sandbox_path.py` — TOCTOU symlink swap raises `OSError(ELOOP)` at `open()`; `is_relative_to(jail)` enforced.
- [ ] `pytest tests/static/test_capability_fence.py` runs the custom ruff rule across `src/` + `plugins/` and asserts zero violations.
- [ ] `ALLOWED_BINARIES` change covered by a fence test asserting the new four binaries are present and no others were added.
- [ ] `--ignore-scripts` adversarial test: `tests/adversarial/test_postinstall_canary.py` confirms canary file unwritten when a fixture's `postinstall` would create it.

**Depends on:** Step 1 (sum types, newtypes), `codegenie.exec` (Phase 0).

**Effort:** L — two real OS adapters, seccomp filter design, network namespace plumbing, and capability lint rule. macOS adapter requires a Mac runner for the integration test (nightly job, not per-PR).

**Risks specific to this step:** `bwrap` is not present on every CI image — add a setup step that installs it (`apt-get install -y bwrap`); macOS `sandbox-exec` is deprecation-flagged upstream but Phase 5 substitutes — accept and document. Test that exits 0 when `bwrap` missing must `pytest.skip` (not silently pass).

## Step 5 — `Transform` ABC consumers, `RecipeEngine` Protocol, `RecipeRegistry`, lockfile policy

**Goal:** A plugin can declare recipes via `@register_recipe`; the orchestrator can iterate them in `(precedence desc, name asc)` order; the day-1 `NpmLockfileRecipeEngine` (production) and `OpenRewriteRecipeEngine` (scaffold) both conform to `RecipeEngine`; `LockfilePolicy` evaluates lockfiles against `tools/policy/lockfile-policy.yaml`.

**Features delivered:**
- `src/codegenie/plugins/recipe_registry.py`: `RecipeRegistry` + `@register_recipe(plugin_id, *, registry=None)` mirroring `PluginRegistry` shape. (Gap 3 fix.)
- `src/codegenie/transforms/recipe_engine.py`: `RecipeEngine` Protocol + `NpmLockfileTransform` and `DockerfileBaseImageTransform` (Phase-7-preview, never invoked by Phase 3).
- `src/codegenie/transforms/engines/npm_lockfile.py`: `NpmLockfileRecipeEngine` — pure-Python parse `package.json` (orjson, 1 MiB cap), in-mem edit (preserve key order), `O_NOFOLLOW` write-back, `SubprocessJail.run(npm install --package-lock-only --ignore-scripts --no-audit --prefer-offline)`, parse new lockfile (32 MiB / depth 24 cap), return `RecipeOutcome.Applied(NpmLockfileTransform(...))`.
- `src/codegenie/transforms/engines/openrewrite.py`: `OpenRewriteRecipeEngine` scaffold — Protocol-conformant, JVM subprocess wrapped in `SubprocessJail`, one Phase-7-tagged Dockerfile-base-image-swap fixture, `@pytest.mark.phase_7_preview` test.
- `tools/policy/lockfile-policy.yaml` (codegenie-owned) + `src/codegenie/transforms/policy/lockfile_policy.py`: `LockfilePolicy.from_yaml(path) -> Result[LockfilePolicy, ParseError]`, `LockfilePolicy.evaluate(lockfile_doc) -> list[PolicyViolation]`, `PolicyViolation = UnauthorizedRegistry(registry, package)` (Phase 7 widens additively). (Gap 2 fix.)
- `src/codegenie/transforms/report.py`: `RemediationReport` Pydantic model + writer for `remediation-report.yaml`.

**Done criteria:**
- [ ] `pytest tests/unit/transforms/test_npm_lockfile_engine.py` covers happy path + size/depth-cap rejection + `O_NOFOLLOW` enforcement.
- [ ] `pytest tests/unit/transforms/test_openrewrite_engine.py -m phase_7_preview` boots JVM under `SubprocessJail`, runs the one fixture, returns `RecipeOutcome.Applied`.
- [ ] `pytest tests/unit/plugins/test_recipe_registry.py` — `@register_recipe` + first-`Applies(plan)`-wins iteration; all-`NotApplies` short-circuits with `RecipeOutcome.NotApplicable(reason=ALL_RECIPES_NOT_APPLICABLE)`.
- [ ] `pytest tests/unit/transforms/test_lockfile_policy.py` — parse + evaluate; `UnauthorizedRegistry` correctly detected on an attacker-`.npmrc` fixture.
- [ ] Golden file `tests/golden/lockfiles/express-cve-2024-21501.before.json` and `.after.json` byte-equal under `NpmLockfileRecipeEngine`.
- [ ] `remediation-report.yaml` writer round-trips a hand-built `RemediationReport` instance.

**Depends on:** Step 1 (`Transform` ABC, `RecipeOutcome`), Step 2 (`Plugin` shape so recipes know their owning plugin), Step 4 (`SubprocessJail`, `SandboxedPath`).

**Effort:** L — two recipe engines (one full, one scaffold), policy loader, lockfile parsing with caps, plus the per-plugin `RecipeRegistry` pattern.

## Step 6 — `RemediationOrchestrator`, `TrustScorer`, two-stream `EventLog`, `SubgraphNode` Protocol, end-to-end happy path

**Goal:** `codegenie remediate <repo> --cve <id>` runs the full 11-step happy path end-to-end against `express-cve-2024-21501/`, writing a local branch and a `remediation-report.yaml`. The Phase-5-named seam `_validate_stage6` exists with its exact signature; the two-stream event log writes both files.

**Features delivered:**
- `src/codegenie/plugins/events.py`: `EventLog` (`emit_internal`, `emit_spanning`, `replay`, `flush`); per-workflow `jsonl.zst` for internal; BLAKE3-chained shared `append.jsonl.zst` for spanning (`fcntl.flock` cross-process safety).
- `WorkflowInternalEvent` / `WorkflowSpanningEvent` discriminated unions with all payload variants from §Component design C9.
- `src/codegenie/transforms/trust_scorer.py`: `TrustScorer(event_log)` (constructor-injected — Gap 5 fix); `score(signals) -> TrustOutcome`; strict-AND; `confidence` folded from `AdapterDegraded` events in the same `workflow_id`.
- `src/codegenie/transforms/signal_kinds.py`: `@register_signal_kind` open registry; Phase 3 registers `build`, `install`, `tests`, `lockfile_policy`, `cve_delta`.
- `src/codegenie/plugins/subgraph.py`: `SubgraphNode` Protocol with `async def run(state) -> NodeTransition` returning `Advance(state) | ShortCircuit(outcome) | Escalate(reason)`. (Gap 1 fix.)
- `src/codegenie/transforms/orchestrator.py`: `RemediationOrchestrator.__init__(registry, vuln_index, event_log, *, sandbox=None)`; `async def run(repo, cve, context=ApplyContext()) -> RemediationOutcome`; `async def _validate_stage6(transform, ctx) -> StageOutcome` as a method (Phase 5 wrap-target).
- 5-node subgraph implementation: `ingest_cve → match_recipe → apply_recipe → stage6_validate → write_branch` as `SubgraphNode` instances.
- `src/codegenie/transforms/git_local_ops.py`: `LocalGitOps.create_patch_branch(...)` with `core.hooksPath=/dev/null`, `GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=/bin/false`; emits `GitHooksDisabledForRun`.
- `src/codegenie/cli/remediate.py`: `codegenie remediate <repo> --cve <id>` CLI (click).
- `.codegenie/.lock` `fcntl.flock` exclusive lock for concurrent-invocation detection (`WorkflowConcurrent`, exit 8).

**Done criteria:**
- [ ] `pytest tests/integration/test_end_to_end_express_cve.py` — `codegenie remediate ./tests/fixtures/repos/express-cve-2024-21501 --cve CVE-2024-21501` exits 0, writes a branch matching `codegenie/cve-2024-21501-*`, writes `remediation-report.yaml` whose `outcome.kind == "validated"` and `trust_outcome.passed == true`, and inside `SubprocessJail` `npm install` + `npm test` both pass.
- [ ] `pytest tests/unit/transforms/test_orchestrator.py` covers `RemediationOrchestrator.run` with each stage mocked; every `RemediationOutcome` variant reachable.
- [ ] `pytest tests/unit/transforms/test_trust_scorer.py` — strict-AND across all 2^5 signal combinations; `confidence="degraded"` when an `AdapterDegraded` event is in the workflow's event log.
- [ ] `pytest tests/unit/plugins/test_events.py` — two-stream writer; BLAKE3 chain verifies on the spanning stream; replay round-trip is byte-equal (modulo timestamps).
- [ ] `pytest tests/integration/test_event_replay.py` — `EventLog.replay()` reconstructs the post-state byte-equal modulo timestamps + `workflow_id`.
- [ ] `pytest tests/integration/test_phase5_contract_snapshot.py` — `RemediationOrchestrator`, `TrustScorer`, `Transform`, `ApplyContext`, `RecipeEngine`, `remediation-report.yaml` schemas snapshot match a frozen golden file. **Failure here means Phase 5 cannot ship.**
- [ ] Concurrent-invocation: second `codegenie remediate` on same repo while first runs exits 8 with `WorkflowConcurrent`.
- [ ] `codegenie audit verify` extended to verify BLAKE3 chain on the spanning stream; refuses on break.

**Depends on:** Steps 1–5.

**Effort:** L — this is the vertical-slice step; it integrates everything from Steps 1–5 and adds the orchestrator + events + scorer + CLI on top. Highest integration risk in the phase.

**Risks specific to this step:** First end-to-end run will surface integration gaps (e.g., a `SignalKind` is registered too late, a `CapabilityBundle` missing a field a recipe expected). Mitigation: keep stages 1–5 frozen during this step; surface every integration gap as a fix in *this* step, not a refactor of earlier steps.

## Step 7 — First production plugin, universal HITL fallback plugin, synthetic third plugin

**Goal:** Three plugins are registered and resolvable by the kernel: `plugins/vulnerability-remediation--node--npm/` (production), `plugins/universal--*--*/` (universal fallback), `tests/fixtures/plugins/example--noop--*/` (synthetic). The plugin contract is bake-tested against all three before Phase 7 ships its first new task class.

**Features delivered:**
- `plugins/vulnerability-remediation--node--npm/`:
  - `plugin.yaml` with `PluginManifest` (scope: `vulnerability-remediation--node--npm`).
  - `api.py` declaring the plugin instance, calling `@register_plugin(...)`.
  - `tccm.yaml` declaring `must_read`/`should_read`/`may_read` queries.
  - `recipes/`: four `RecipeProtocol` implementations — `NpmLockfileSemverBumpRecipe`, `NpmPeerDepConflictRecipe`, `NpmTransitiveOverridesRecipe`, `NpmMajorBumpRefuseRecipe` — registered via the plugin-local `RecipeRegistry`.
  - `subgraph/`: 5 `SubgraphNode` implementations.
  - `adapters/`: npm-specific implementations of the four ADR-0032 language search adapters (`dep_graph.consumers`, `import_graph.reverse_lookup`, `scip.refs`, `test_inventory.tests_exercising`).
- `plugins/universal--*--*/`:
  - `plugin.yaml` with scope `(*, *, *)` and lowest precedence.
  - `subgraph/` writes sanitized markdown to `.codegenie/handoff/<workflow_id>.md` (NFKC + ANSI/bidi/zero-width strip), emits `RequiresHumanReview`, returns `RemediationOutcome.RequiresHumanReview(reason=NoConcreteMatch)`.
- `tests/fixtures/plugins/example--noop--*/`: synthetic plugin exercising every Protocol surface (Plugin, Adapter, RecipeEngine, RecipeProtocol).
- `plugins/PLUGINS.lock` populated with the two production plugin tree digests.

**Done criteria:**
- [ ] `pytest tests/integration/test_three_plugin_contract.py` loads all three plugins, exercises `Plugin.build_subgraph`, `Plugin.adapters`, `Plugin.transforms`, the recipe-registry walk, and the universal-fallback resolution path.
- [ ] `pytest tests/integration/test_universal_fallback.py`: `codegenie remediate ./tests/fixtures/repos/cargo-fixture --cve CVE-2024-Y` exits 7 with `.codegenie/handoff/*.md` written.
- [ ] `pytest tests/unit/plugins/test_recipe_protocol.py`: each of the four npm recipes' `applies(...)` returns the right `Applicability` variant against fixture inputs.
- [ ] Negative test: `tests/integration/test_universal_fallback_never_silent.py` — when a concrete plugin's `import_module` raises, loader exits 4 with `PluginRejected(import_error)` *before* resolution (universal does NOT silently substitute).
- [ ] `PLUGINS.lock` mismatch test: mutate a plugin file post-lock; loader exits 4 with `PluginRejected(integrity_mismatch)`.

**Depends on:** Steps 1–6 (kernel, Port, recipe engine, orchestrator all in place).

**Effort:** L — three plugins, four recipes each with `applies` logic, full TCCM declaration, four language-adapter implementations. Volume dominates.

## Step 8 — Fixture portfolio, golden files, determinism property, adversarial tests

**Goal:** The full Phase 3 fixture portfolio is on disk; the determinism property test passes over 100 Hypothesis runs; every adversarial case from §Edge cases E1–E20 has a regression test.

**Features delivered:**
- `tests/fixtures/repos/`:
  - `express-cve-2024-21501/` (happy path; Step 6 already created stub — extend).
  - `monorepo-workspaces/` (npm workspaces; vuln in one workspace).
  - `transitive-only-cve/` (vuln only in transitive; `overrides` recipe).
  - `peer-dep-conflict/` (`NotApplicable`-emitting).
  - `major-bump-required/` (`MAJOR_BUMP_REFUSE`-emitting).
  - `breaking-test-suite/` (install passes, tests fail → `Validated(passed=False)`).
  - `stale-scip/` (stale Phase 2 index; freshness signal).
  - `malformed-package-json/` (depth-22 nesting; parse-cap rejection).
  - `malicious-npmrc/` (`.npmrc` redirects registry → `NetworkDenied`).
  - `postinstall-canary/` (postinstall writes canary; assert canary unwritten).
- ≥5 CVE fixtures total (roadmap exit-criterion satisfier).
- `tests/golden/`:
  - `lockfiles/express-cve-2024-21501.{before,after}.json`.
  - `remediation-reports/express-cve-2024-21501.yaml` (modulo `workflow_id` + timestamps).
  - `event-streams/express-cve-2024-21501.spanning.jsonl` + `.internal.jsonl`.
- `tests/property/test_transform_determinism.py`: Hypothesis-driven property over `(repo_snapshot_sha, cve_record_digest, plugin_version, recipe_version, vuln_index_digest)` asserting byte-identical `transform.diff_bytes` over 100 runs.
- `tests/adversarial/` (marked `@pytest.mark.phase03_adv`): CVE-record size/depth caps; `package.json` / `package-lock.json` caps; `--ignore-scripts` canary; egress denial; symlink TOCTOU; capability-construction fence (already in Step 4); recipe-authoring abuse precursor; lockfile re-resolve introduces NEW CVE → `cve_delta_introduced`.
- `tests/integration/test_yarn_berry_routed_to_universal.py`: Yarn Berry repo falls through to universal fallback.
- `tests/integration/test_extends_chain.py`: `extends`-chain composition test (depth 4 ok).

**Done criteria:**
- [ ] All fixtures present and `pytest tests/fixtures/test_fixtures_load.py` smoke-loads each.
- [ ] `pytest tests/property/test_transform_determinism.py --hypothesis-seed=0` produces identical `diff_bytes` across all 100 runs (cardinal Goal G4).
- [ ] `pytest tests/adversarial/ -m phase03_adv` green; every E1–E20 case has at least one passing test.
- [ ] Golden-file comparisons byte-equal (modulo whitelisted nondeterminism: timestamps, `workflow_id`, `event_id`).
- [ ] `pytest tests/integration/test_breaking_test_suite.py` — recipe applies cleanly but `npm test` fails → orchestrator returns `Validated(passed=False, failing=["tests"])`; **no retry** (Phase 3 alone; Phase 5 wraps).
- [ ] `cve_delta` signal: `tests/adversarial/test_cve_delta_introduced.py` — lockfile resolves a transitive that itself has a known CVE; `TrustOutcome.passed == False`; branch NOT created.

**Depends on:** Steps 6 + 7 (orchestrator and plugins must work end-to-end before properties are meaningful).

**Effort:** L — 10 fixtures × real `package.json`/`package-lock.json` content; determinism property is one of the highest-trust tests in the codebase; adversarial coverage is dense.

**Risks specific to this step:** Fixture drift — real `npm install` resolutions change when the registry changes. Mitigation: pin every fixture's `package-lock.json` to exact versions; assert no implicit-version `^`/`~` resolution in golden comparisons.

## Step 9 — CI gates, import-linter contracts, performance baselines, bench backfill hook

**Goal:** CI hard-blocks every Phase 3 invariant; performance budgets have a 7-day rolling baseline; `BenchReplayable` events flow on the spanning stream so Phase 6.5 can lift cases mechanically.

**Features delivered:**
- `make check` extended to include Phase 3 fence tests; CI matrix verified across Python 3.11 / 3.12 × `ubuntu-24.04`.
- `make lint-imports` — Phase 3 `import-linter` contracts: no LLM SDK under `src/codegenie/{plugins,transforms}/`; no cross-plugin imports; no `import codegenie.plugins.subgraph` from plugin folders (subgraph contract is consumed via `Plugin.build_subgraph` only).
- `tests/fence/test_pyproject_fence.py` confirmed to extend to Phase 3 packages (no LLM SDK appears in the runtime closure).
- `tests/fence/test_event_taxonomy_complete.py`: every `event_type` literal in `WorkflowInternalEvent` / `WorkflowSpanningEvent` has a corresponding emit site in code (no dead enum values, no undeclared emits).
- Bench harness:
  - `tests/bench/bench_plugin_registry_build.py` — < 500 ms for 3 plugins.
  - `tests/bench/bench_bundle_builder_warm.py` — < 5 ms.
  - `tests/bench/bench_bundle_builder_cold.py` — < 300 ms.
  - `tests/bench/bench_vuln_index_lookup.py` — < 10 ms p99 over 100 lookups.
  - `tests/bench/bench_recipe_match.py` — < 60 ms p95.
  - `tests/bench/bench_event_appender_throughput.py` — > 30,000 events/sec.
  - `tests/bench/bench_workflow_e2e_warm.py` — < 20 s p50, < 35 s p95.
- Relative-budget assertion: > 25% regression vs. 7-day rolling mean fails the bench job.
- `BenchReplayable` spanning event emitted at end of every workflow with input-snapshot fingerprint + `Transform.diff_bytes_sha256`.
- `tests/integration/test_phase65_backfill_hook.py`: Phase 6.5's `codegenie eval backfill` (stub interface) consumes ≥10 `BenchReplayable` events from the spanning stream and produces eval cases without manual editing.
- Operator-readable runbook entry in `docs/operations/phase03-runbook.md` (1 page).
- `$0.00` LLM-spend CI assertion: a job greps a synthetic cost ledger for Phase 3 surface and fails on any nonzero LLM cost record.

**Done criteria:**
- [ ] CI green on a fresh PR: `make check`, `make lint-imports`, `make fence`, the three integration contracts (`test_phase5_contract_snapshot`, `test_three_plugin_contract`, `test_end_to_end_express_cve`), and the bench job.
- [ ] First green CI run records the bench baseline to `tests/bench/.baseline.json`; subsequent runs assert against the 7-day rolling mean.
- [ ] `pytest tests/integration/test_phase65_backfill_hook.py` produces ≥10 eval cases mechanically from the test event stream.
- [ ] `pytest tests/fence/test_event_taxonomy_complete.py` green — every event type has both a declared variant and an emit site.
- [ ] `codegenie remediate --help` and `codegenie vuln-index refresh --help` and `codegenie cache prune --help` all exit 0.
- [ ] LLM-spend assertion: `tests/fence/test_no_llm_spend.py` greps every produced `remediation-report.yaml` and fails on any nonzero `llm_cost_usd` field (field must not exist in Phase 3).

**Depends on:** Steps 1–8.

**Effort:** M — mostly assembly + baseline recording. The bench harness exists as Phase 2 precedent; reuse the relative-budget pattern from Phase 2's `bench`-marked tests.

## Exit-criteria mapping

| Exit criterion (verbatim or close from roadmap §Phase 3) | Step(s) |
|---|---|
| Given a Node.js repo with a known npm CVE, the system writes a working patch diff on a local branch that — when applied — installs cleanly and passes the repo's own tests. | Step 6 (`test_end_to_end_express_cve.py`), Step 8 (≥5 CVE fixtures) |
| Plugin loader works (first plugin ships) — `plugins/vulnerability-remediation--node--npm/` | Step 2 (loader), Step 7 (first concrete plugin) |
| Universal HITL fallback plugin ships — `plugins/universal--*--*/` | Step 7 (universal fallback impl), Step 8 (`test_yarn_berry_routed_to_universal.py`) |
| Plugin contract bake-tested against ≥3 plugins (extension-by-addition test for Phase 7) | Step 7 (synthetic `example--noop--*` + `test_three_plugin_contract.py`) |
| No LLM in this loop (deterministic recipe path) | Step 1 (`import-linter` contract), Step 9 (`$0.00` LLM-spend assertion, `test_no_llm_in_transforms.py`) |
| OpenRewrite recipe scaffold (per roadmap "Tooling & setup: OpenRewrite recipes for npm dependency updates") | Step 5 (`OpenRewriteRecipeEngine` scaffold + Dockerfile fixture) |
| CVE data ingestion (NVD JSON 2.0, GHSA, OSV) | Step 3 (`VulnIndex` parsers) |
| Library of fixture repos with known vulnerable lockfiles; edge-case fixtures (peer-dep conflicts, transitive-only, semver corners) | Step 8 (full fixture portfolio) |
| Before/after lockfile + `package.json` diff assertions; test suite still passes; no semantic regression | Step 6 (vertical slice), Step 8 (golden files), Step 8 (`test_breaking_test_suite.py`) |
| Four ADR-0032 language search adapters wrapping Phase 2 structural probes | Step 7 (plugin `adapters/`) |
| Plugin bundles its own subgraph, TCCM, npm/Node-specific probes, Skills, OpenRewrite recipes | Step 7 (plugin layout) |

Every exit criterion maps to at least one step. No gap.

## Implementation-level risks

1. **bwrap / sandbox-exec availability on CI runners.** What could go sideways: `ubuntu-24.04` runner lacks `bwrap`, or the runner's seccomp profile blocks the syscalls we need. Signal: Step 4's integration tests `pytest.skip`-ing silently instead of running; or `bwrap` returning `EPERM` on `unshare`. Action: explicit `apt-get install -y bwrap` in CI; assert presence in `test_bwrap_hello_world.py` setup; fail the job (not skip) when on Linux and `bwrap` missing.
2. **Determinism property test flakiness from npm registry drift.** What could go sideways: a published version of a fixture's transitive dep changes content between runs (rare but happens; e.g., `npm publish --force`). Signal: Step 8's `test_transform_determinism.py` flips green/red on different days. Action: every fixture pins exact `package-lock.json` versions; the property test runs with `npm install --prefer-offline --offline` against a pre-warmed cache committed to the repo (not the live registry).
3. **`PLUGINS.lock` churn during plugin development.** What could go sideways: every `plugin.yaml` edit forces a `PLUGINS.lock` regen, slowing iteration. Signal: Step 7 PRs become noisy with `PLUGINS.lock` diffs. Action: `codegenie plugins lock-update` regen helper; pre-commit hook that auto-updates the lock if and only if `plugins/` changed; document the workflow in the Step 7 runbook.
4. **Phase 5 contract snapshot test brittleness.** What could go sideways: legitimate Phase 3 evolution post-Step 6 changes a Pydantic model field and breaks the snapshot, blocking unrelated work. Signal: PRs touching `transforms/` repeatedly modify the golden file. Action: distinguish *additive* (new optional field with `default_factory`) from *breaking* (rename, remove, required-add) — the snapshot test allows additive deltas; breaking deltas require explicit ADR amendment + golden refresh. Encode this distinction in the test, not in reviewer judgment.
5. **TOCTOU `ELOOP` handling slips past consumers.** What could go sideways: a recipe engine opens a `SandboxedPath` but does not catch `OSError(errno=ELOOP)`, so a symlink-swap fixture surfaces as an unhandled exception instead of `FilesystemRaceDetected`. Signal: Step 8's symlink-TOCTOU adversarial test produces a stack trace, not the expected typed outcome. Action: a single `with_sandbox_open(...)` helper that catches `ELOOP` and emits the event; lint rule (or grep test) asserting every `.open(...)` on a `SandboxedPath` is routed through the helper.

## What's next — handoff to Phase 04

After Phase 3 ships, Phase 4 picks up the following stable surfaces — none of them require edits to Phase 3 code:

- **New artifacts on disk.** `plugins/vulnerability-remediation--node--npm/`, `plugins/universal--*--*/`, `plugins/PLUGINS.lock`, `.codegenie/cache/bundles/`, `.codegenie/events/workflow-internal/*.jsonl.zst`, `.codegenie/events/spanning/append.jsonl.zst`, `.codegenie/handoff/<workflow_id>.md`, `vuln-index.sqlite`, `tools/policy/lockfile-policy.yaml`, `tooling/sandbox/macos-npm.sb`.
- **New contracts ready.** `Plugin` Protocol + `PluginRegistry` + `@register_plugin`; `Transform` ABC (Phase 4's `LLMProducedTransform(Transform)` subclasses it additively); `RecipeEngine` Protocol (Phase 4 adds an `LLMRecipeEngine` adapter); `ApplyContext` with `prior_attempts: list = []` (Phase 4 reads it at LLM-prompt-build time); `RecipeOutcome.NotApplicable(reason: NotApplicableReason)` with the four Phase 3 reasons (Phase 4's fallback trigger; reason taxonomy extends additively); `TrustSignal` shape (Phase 4 emits the same shape); two-stream event taxonomy with `WorkflowInternalEvent` / `WorkflowSpanningEvent` discriminated unions (Phase 4 extends both additively with `LlmInvocationStarted`, `RagLookupHit`, etc.).
- **New CI gates.** `make lint-imports` (Phase 4 amends to *permit* `anthropic`/`langgraph` under `src/codegenie/llm/` only); `test_phase5_contract_snapshot.py` (Phase 4 must not break it); the bench harness with 7-day rolling baseline.
- **Implicit assumptions Phase 4 can now make.** A `RecipeOutcome.NotApplicable(reason=...)` from Phase 3 is the canonical signal to dispatch LLM fallback. The `prior_attempts` list will be populated when Phase 5's `GateRunner` wraps `_validate_stage6` — Phase 4 writes its prompt builder to consume it without conditional checks. The `BenchReplayable` spanning events are the seed source for Phase 4's solved-example store — `.codegenie/solved/<task_class>/<example_id>.json` schema sits on top, additively.
- **What Phase 4 cannot assume.** No retry envelope in Phase 3 — `Validated(passed=False)` is terminal until Phase 5 wraps. No microVM — `SubprocessJail` substrate remains bwrap/sandbox-exec until Phase 5 substitutes Firecracker / DinD. No `git push` — `GitLocalOpsCapability` still has no `push` field (Phase 11).
