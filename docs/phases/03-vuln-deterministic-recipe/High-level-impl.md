# Phase 3 — Vuln remediation: deterministic recipe path: High-level implementation plan

**Status:** Implementation plan
**Date:** 2026-05-12
**Architecture reference:** [phase-arch-design.md](phase-arch-design.md)
**ADRs:** [ADRs/](ADRs/)
**Source design:** [final-design.md](final-design.md)
**Roadmap reference:** [docs/roadmap.md](../../roadmap.md) §"Phase 3"

## Executive summary

The engineer lands the second load-bearing contract in the system — the `Transform` ABC — and its sibling `RecipeEngine` ABC, mounted under two new top-level packages (`src/codegenie/transforms/`, `src/codegenie/recipes/`) with `cve/` and `validation/` folded under `transforms/`. One concrete transform (`NpmPackageUpgradeTransform`) drives one default engine (`NcuRecipeEngine`) plus one opt-in registered-but-narrow stub engine (`OpenRewriteEngineStub`) so the engine seam is *proven* to extend. Around the transform sit the CVE feed surface (`codegenie cve sync` with content-addressed snapshots + best-effort signatures + graded staleness advisory), the `CveRetractionProbe`, the `LockfilePolicyScanner` with graded `--allow-policy-violations` escape valve, the `LockfileResolver` with bounded transient retry, the `LockfileCanonicalizer` (LC_ALL=C + key sort + LF), the single-profile `ValidationGate` with the new `test_execution=True` overlay flag plus `--network=none` default + `gate.signal_escalate` audit event, the strict-AND `TrustScorer`, the `PatchBranchWriter`, and the linear six-call `RemediationOrchestrator`. Phase 0/1/2 edits are limited to four ADR-gated additive changes (`ALLOWED_BINARIES +3`: `npm`/`ncu`/`java`; Phase-2 Skills frontmatter optional `applies_to.cve_patterns`; audit-event-type enum extension; new CLI subcommand groups). Seven steps. Contracts + foundations first, CVE feed surface next (the only network-touching code path), then the engine + transform vertical, then policy + validation, then orchestrator + branch writer + audit extension, then the OpenRewrite stub seam, then the adversarial corpus + determinism canary + Phase 4 handoff verification.

## Order of operations

The ordering principle is **contracts before consumers, default-engine vertical-slice before second-engine seam, deterministic primitives before the gate, adversarial corpus last**. (1) Step 1 lands the two ABCs, the two registries, the `RecipeSelection` Pydantic, the new exceptions, the audit-event enum extension, the Phase-2 `run_in_sandbox` `test_execution=True` overlay (the single additive edit Phase 2 promised), and the Phase-0 `fence` extension to `transforms/` + `recipes/` — every Phase 3 component consumes at least one of these. (2) Step 2 stands up the CVE feed surface in isolation (`cve sync` + content-addressed store + parsers + `CveEntryNormalizer` + staleness advisory) because it is the only network-touching code and because the orchestrator + selector cannot resolve an advisory without it; `CveRetractionProbe` ships here too because it is part of the `cve sync` post-step. (3) Step 3 builds the `NcuRecipeEngine` default vertical — `tools/npm.py` + `tools/ncu.py` wrappers with the wrapper-level `NpmScriptsEnabled` guard, `recipes/digests.yaml` pin manifest, `RecipeRegistry` + selector + `selector.yaml` decision table, `LockfileResolver` + `LockfileCanonicalizer` + cache key + `cache.replay` event. (4) Step 4 ships the `LockfilePolicyScanner` (typed violations + `--allow-policy-violations` flag) and the single-profile `ValidationGate` (install + test + build validators on the new overlay flag, network-required signature scan, `gate.signal_escalate` audit event + on-disk escalation JSON). (5) Step 5 lands the `NpmPackageUpgradeTransform` + `RemediationOrchestrator` + `PatchBranchWriter` + `TrustScorer` + `codegenie remediate` CLI surface + the documented exit-code mapping, plus the audit event payload schemas (`audit/events.py`). (6) Step 6 wires the `OpenRewriteEngineStub` second seat (opt-in, `--engine=openrewrite`, JVM-gated, pinned-jar smoke recipe). (7) Step 7 lands the ≥ 30 adversarial fixtures, the `.bundle` + `npm-resolution.json` + pinned local registry mirror portfolio, the determinism canary (5× byte-identical), the perf canaries, the `test_phase2_unchanged` regression hard-gate, the Phase-4 handoff verification, and the four new CI gates (`fence` extension, `tool_digests_verify` extension for `npm`/`ncu`/`openrewrite-jar`, `recipes_digests_yaml` parity, adversarial corpus gate, determinism canary).

## Step 1 — Plant the two ABCs, the four Phase 0/1/2 additive edits, and the foundations every Phase 3 component consumes

**Goal:** Both load-bearing contracts (`Transform` ABC + `RecipeEngine` ABC), their registries, the boundary Pydantic models (`TransformInput`, `TransformOutput`, `RecipeApplication`, `ApplyContext`, `RecipeSelection`, `ValidatorOutput`, `GateOutcome`, `TrustScore`, `RemediationReport`), and the four ADR-gated additive edits to Phase 0/1/2 (`ALLOWED_BINARIES +3`, Phase-2 Skills frontmatter `applies_to.cve_patterns`, audit-event enum extension, `run_in_sandbox` `test_execution=True` overlay flag) are on disk and unit-tested in isolation. No engine, no transform, no orchestrator yet — only the contracts and the seams.

**Features delivered:**
- `src/codegenie/transforms/__init__.py`, `contract.py`, `registry.py` per `phase-arch-design.md §"Component design" #1`. `Transform` ABC declares `name`, `declared_inputs`, `applies_to_tasks`, `applies_to_languages`, `requires_recipe_engines`, `applies()`/`run()`. `@register_transform` decorator parallels Phase 1's `@register_probe`. No `success` field on `TransformOutput` — validators emit `passed` (facts not judgments). `TransformInput` and `TransformOutput` are frozen Pydantic with `extra="forbid"`.
- `src/codegenie/recipes/__init__.py`, `contract.py`, `registry.py`, `models.py` per `phase-arch-design.md §"Component design" #2`. `RecipeEngine` ABC declares `name`, `applies_to_engines`, `available()`, `apply()`. `Recipe`, `ApplyConstraints`, `ApplyContext`, `RecipeApplication`, `RecipeSelection` Pydantic models with `extra="forbid"`. `RecipeSelection.reason` is `Literal["matched","no_engine","range_break","peer_dep_conflict","unsupported_dialect","catalog_miss"]` — closed enum is the public contract Phase 4 reads (ADR-P3-002).
- `src/codegenie/exec.py` extended in place per ADR-P3-009. `ALLOWED_BINARIES` extends from Phase 2's eight binaries to include `npm`, `ncu`, `java`. Credential-strip continues unchanged.
- `src/codegenie/exec.py` `run_in_sandbox` gains a new keyword arg `test_execution: bool = False` per ADR-P3-005. When `True`: writable upper-layer overlay over `/work`, larger PID/wall budgets (1024/600 s), `--ignore-scripts` *not* enforced at the wrapper level (because the test command itself is allowed to run scripts), `--network=none` remains the default. Linux `bwrap` + macOS `sandbox-exec` parity preserved. This is the **single** Phase-2-substrate edit Phase 2's design promised (`final-design.md §"Roadmap coherence check"`).
- `src/codegenie/skills/models.py` extended in place per ADR-P3-010: `applies_to.cve_patterns: list[str] = ["*"]` optional additive field on the `ApplyConstraints` model. Phase 2 Skills loader unchanged; the schema is forward-compatible per Phase 2's `SCHEMA-EVOLUTION-POLICY.md` minor-bump rule.
- `src/codegenie/audit/events.py` (new module) — Pydantic event payload schemas for the Phase-3 event-type set (`cve.feed.synced`, `cve.feed.signature_check`, `cve.retraction.detected`, `recipe.selected`, `recipe.engine.invoked`, `transform.applied`, `lockfile.scanned`, `lockfile.policy_violation`, `npm.install.run`, `tests.executed`, `gate.failed`, `gate.signal_escalate`, `evidence_stale.marked`, `branch.created`, `branch.refused_dirty_tree`, `branch.refused_exists`, `cache.replay`, `meta.unexpected_exception`). `src/codegenie/audit_writer.py` event-type enum extended in place (one-line additive edit). Malformed event → dropped to stderr + `meta.event_validation_failure` appended (chain integrity preserved).
- `src/codegenie/errors.py` extended: `NpmScriptsEnabled`, `RecipeNotInDigestManifest`, `CveSnapshotCorrupt`, `CveSignatureMismatch`, `AdvisoryNotInStore`, `WorkingTreeNotClean`, `BranchExists`, `LockfileResolveFailed`, `LockfileMalformed`, `TransformError`, `EngineUnavailable`.
- `src/codegenie/cli.py` extended with three new click subcommand *groups* (entry-point only, no implementation yet): `remediate`, `cve`, `recipes`. Each `--help` prints "not yet implemented" with exit code 2 until Step 5.
- Phase-0 `fence` CI job extended (`scripts/fence_imports.py` or equivalent): `src/codegenie/transforms/` and `src/codegenie/recipes/` import-closure forbids `anthropic`, `langgraph`, `chromadb`, `qdrant`, `qdrant-client`, `sentence-transformers`, `voyageai`, `openai` (ADR-P3-008).
- ADRs in `docs/phases/03-vuln-deterministic-recipe/ADRs/` created: ADR-P3-001 (`Transform` ABC contract frozen at v0.3.0), ADR-P3-002 (`RecipeEngine` ABC + `RecipeSelection` structured triple), ADR-P3-005 (single sandbox profile + `test_execution=True` overlay + `--network=none` default + `gate.signal_escalate`), ADR-P3-008 (package layout: two new top-level packages; `cve/` + `validation/` fold under `transforms/`), ADR-P3-009 (`ALLOWED_BINARIES` adds `npm`, `ncu`, `java` — opt-in), ADR-P3-010 (Skills schema additive `applies_to.cve_patterns`).
- New structlog event names registered in `src/codegenie/logging.py` constants: every Phase-3 event-type from §14 of the arch doc, plus `phase3.fence.violation`. New structured fields: `cve_id`, `recipe_id`, `engine_name`, `run_id`.

**Done criteria:**
- [ ] `tests/unit/transforms/test_contract.py` — Pydantic schema dump snapshot test (`test_transform_contract.py`) mirrors Phase 0's `test_probe_contract.py`; ABC signature drift fails CI red.
- [ ] `tests/unit/transforms/test_registry.py` — `@register_transform` happy path; duplicate-name rejection.
- [ ] `tests/unit/recipes/test_contract.py` — `test_recipe_engine_contract.py` snapshot; `RecipeEngine.available()` returns `bool`; `RecipeSelection.reason` closed enum.
- [ ] `tests/unit/recipes/test_registry.py` — engine registration; duplicate-name rejection; `available()` gating.
- [ ] `tests/unit/exec/test_test_execution_overlay.py` — `test_execution=True` enables writable overlay; larger PID/wall budgets; `--ignore-scripts` not enforced at wrapper level in this mode; `--network=none` remains default.
- [ ] `tests/unit/exec/test_allowed_binaries_phase3.py` — `npm`, `ncu`, `java` in `ALLOWED_BINARIES`; env-strip unchanged.
- [ ] `tests/unit/audit/test_events_phase3.py` — every Phase-3 event-type schema validates; malformed payload → dropped + `meta.event_validation_failure` appended.
- [ ] `tests/unit/skills/test_cve_patterns_field.py` — `applies_to.cve_patterns` defaults to `["*"]`; Phase 2 fixtures still load (forward compat); new field round-trips.
- [ ] `tests/adv/test_phase3_fence_no_llm_imports.py` — fence CI gate ensures `anthropic`, `langgraph`, etc. not importable from `transforms/` or `recipes/` import closure.
- [ ] `tests/adv/test_phase3_no_subprocess_direct.py` — AST scan of `src/codegenie/transforms/` and `src/codegenie/recipes/`; no `subprocess.run`/`Popen` outside `src/codegenie/exec.py` and `src/codegenie/tools/`.
- [ ] All Step 1 code passes strict mypy.
- [ ] Phase 0/1/2 `fence` + `tool_digests_verify` + `conventions_catalog_parity` CI jobs stay green (no regressions).

**Depends on:** Phase 2 shipped and `main` green. The `test_execution=True` overlay edit is the Phase-2 commitment surfaced in `final-design.md §"Roadmap coherence check"` — if Phase 2's sandbox profile cannot host a writable overlay, this step blocks until Phase 2 amends.

**Effort:** L — two new packages, six ADRs, the single Phase-2 chokepoint edit (highest review surface), the audit-event enum extension, the Skills schema additive field, the fence extension. Splitting threshold: if the PR exceeds 1,500 LOC, split into Step 1a (contracts + Pydantic + fence extension + ADRs P3-001/002/008/010) and Step 1b (`test_execution=True` overlay + `ALLOWED_BINARIES` + audit events + ADRs P3-005/009).

**Risks specific to this step:** The `test_execution=True` overlay is the **only** Phase-2-chokepoint amendment in Phase 3 — encode the allowed-keyword-set in `run_in_sandbox` so a fourth network keyword can't slip in later (parity with Phase 2's snapshot-attribute discipline). The `Transform` ABC is reviewed against four future-phase use cases (Phase 4 wraps selector; Phase 5 wraps coordinator with three-retry; Phase 7 adds `DockerfileBaseImageSwapTransform`; Phase 15 emits agent-authored recipes); the snapshot test freezes the signature so any drift is a deliberate ADR-amended choice. `RecipeSelection.reason` is closed in code but the closed set was chosen with Phase 4's needs in mind — a sixth reason requires an ADR amendment + code + schema PR in the same change (the Phase-2 `detect.type` discipline).

## Step 2 — Ship the CVE feed surface and `CveRetractionProbe`

**Goal:** `codegenie cve sync` is on disk, the only network-touching codepath in Phase 3 (outside `npm install`'s scoped registry pulls). Snapshots are content-addressed, hash-verified on read, signature-checked best-effort. Staleness emits a graded advisory. `CveRetractionProbe` runs as the last step of every sync and writes `evidence_stale.marked` to prior remediations' audit chains.

**Features delivered:**
- `src/codegenie/transforms/cve/__init__.py`, `models.py` per `phase-arch-design.md §"Component design" #7`. `Severity`, `AffectedRange`, `Provenance`, `Reference`, `CveEntry` Pydantic with `extra="forbid"`. `Provenance.signature_verified: bool | None` where `None` means "unsupported", not "unknown".
- `src/codegenie/transforms/cve/feeds/nvd.py`, `ghsa.py`, `osv.py` — one parser module per source. Each module exports `parse(raw_bytes) -> list[CveEntry]`. Sandboxed-`curl` + `git` fetch from inside `run_in_sandbox(network="scoped", allowlist=[<feed-host>])`. Raw bytes pass through Phase-2 `OutputSanitizer` Pass 5 (prompt-injection marker tagger); `references[].prompt_injection_marker_count` populated.
- `src/codegenie/transforms/cve/normalizer.py` — `CveEntryNormalizer.merge(records: list[CveEntry]) -> CveEntry` joins NVD/GHSA/OSV records on the same CVE ID and aliases. Commutative + idempotent (Hypothesis tests).
- `src/codegenie/transforms/cve/store.py` — content-addressed storage at `.codegenie/cve/snapshots/<source>/<sha256>.json.gz`. `CveFeedReader.get(cve_id) -> CveEntry`; `CveFeedReader.staleness(source) -> Staleness({age_days, status})`. Hash-mismatch on read → `CveSnapshotCorrupt` (hard fail). mmap'd index for sub-1-ms `get` in steady state.
- `src/codegenie/transforms/cve/syncer.py` — `CveFeedSyncer.sync(source, *, since)`. Best-effort signature verification: NVD `.meta` GPG against `tools/cve-feeds/nvd-public.asc`; GHSA/OSV `git verify-commit` against pinned GitHub `web-flow` key set. Result recorded as `Provenance.signature_verified`; **does not gate the sync** (synth-softening per ADR-P3-007). Sync emits `cve.feed.synced` + `cve.feed.signature_check` audit events.
- `src/codegenie/transforms/cve/retraction_probe.py` — `CveRetractionProbe.run(prior_audit_dir, prior_snapshot, new_snapshot) -> RetractionReport` per `phase-arch-design.md §"Component design" #8` and Gap 4. Invoked as last step of `cve sync`. Diffs `withdrawn` field; for any record flipped false → true, scans `prior_audit_dir/**/audit/*.jsonl` and appends `evidence_stale.marked` event to each prior remediation's chain (append-only; chain head advances for the prior run). Conservative on partial retraction: marks stale + records disagreement.
- `tools/cve-feeds/nvd-public.asc` — pinned NVD GPG public key.
- `tools/cve-feeds/github-web-flow-keys.asc` — pinned GitHub `web-flow` key set.
- Staleness advisory enforcement: every `codegenie remediate` invocation checks `staleness(source)`; emits warn>7d / `confidence` floor at low>30d / refuses>90d unless `--allow-stale-feeds`.
- CLI: `codegenie cve sync --source {nvd,ghsa,osv,all} [--since DATE]`. Tool-readiness check at startup verifies `curl`, `git`, GPG availability.
- ADR-P3-007 created: CVE feed integrity — content-hash gate, best-effort signature, graded staleness advisory.
- ADR-P3-006 created: `CveRetractionProbe` lives under `src/codegenie/transforms/cve/` (not `src/codegenie/probes/`); does NOT register via `@register_probe`; shaped like a probe so Phase 14 can promote it cleanly (Gap 4 resolution).

**Done criteria:**
- [ ] `tests/unit/transforms/cve/test_nvd_parser.py`, `test_ghsa_parser.py`, `test_osv_parser.py` — ≥ 6 tests per parser including parser-bomb fixtures, malformed JSON, missing fields, alias graphs.
- [ ] `tests/unit/transforms/cve/test_normalizer.py` — ≥ 8 tests for `merge`: commutative (Hypothesis), idempotent (Hypothesis), dedup, severity tie-break.
- [ ] `tests/unit/transforms/cve/test_store.py` — content-addressed write + read; hash-mismatch raises `CveSnapshotCorrupt`; `mmap` index `get` round-trips; `staleness` computes correct status at 0/7/30/90-day boundaries.
- [ ] `tests/unit/transforms/cve/test_syncer.py` — happy-path sync writes `cve.feed.synced` audit event; signature failure recorded as `signature_verified=False` but sync continues; unsupported signature path emits `None`.
- [ ] `tests/unit/transforms/cve/test_retraction_probe.py` — synthetic withdrawn record; prior run's audit chain gains `evidence_stale.marked` event; chain head advances.
- [ ] `tests/integration/test_cve_retraction_marks_evidence_stale.py` — end-to-end retraction flow.
- [ ] `tests/adv/test_cve_snapshot_hash_mismatch_rejected.py` — corrupted snapshot on disk; loud read failure.
- [ ] `tests/adv/test_cve_sync_egress_scoped.py` — sync attempts to fetch outside `allowlist` are denied by sandbox; loud `probe.sandbox.network_egress_attempted` event.
- [ ] `tests/golden/cve/{nvd,ghsa,osv}/<cve-id>.json` — frozen feed-parser goldens; ≥ 3 per source.
- [ ] All Step 2 code passes strict mypy.

**Depends on:** Step 1 (contracts, exceptions, audit events, `test_execution` overlay not required here — Step 2 uses Phase-2's stock sandbox).

**Effort:** M — three parsers + normalizer + store + syncer + retraction probe. The signature-verification surface is the trickiest part because GPG key custody (NVD) and `git verify-commit` (GHSA web-flow) have different lifecycle expectations; both are *best-effort* per ADR-P3-007 so neither blocks the sync — but both must record their result honestly into `Provenance.signature_verified`.

**Risks specific to this step:** Feeds drift in shape (NVD 2.0 vs 1.1; OSV schema evolution); pin the parser's expected schema version in the parser module and emit a loud warning + `signature_verified=None` if a future schema bump deviates. The `CveRetractionProbe` is shaped like a probe but **must not** be registered via `@register_probe` (Gap 4 resolution) — encode the no-registration invariant in a test that imports the module and asserts the registry is unchanged after import. The Phase-14 promotion path is documented in ADR-P3-006 so a later phase doesn't accidentally fork the implementation.

## Step 3 — Ship the `NcuRecipeEngine` vertical: `tools/npm` + `tools/ncu` wrappers, `LockfileResolver`, `LockfileCanonicalizer`, recipe catalog + selector

**Goal:** The default-engine vertical is on disk. A `Recipe` loads from YAML with digest verification; the `RecipeSelector` returns a `RecipeSelection(recipe, reason, diagnostics)` triple for any synthetic input without raising; the `NcuRecipeEngine.apply()` invokes `ncu` inside `run_in_sandbox` and returns a `RecipeApplication`; the `LockfileResolver` runs `npm install --package-lock-only --ignore-scripts --no-audit --no-fund` with bounded transient retry, cache key includes the four content hashes, and a cache hit emits `cache.replay` referencing the original chain head; the `LockfileCanonicalizer` is byte-stable and idempotent.

**Features delivered:**
- `src/codegenie/tools/npm.py` (new) — typed wrapper per Phase-2 precedent. Routes through `exec.run_in_sandbox`. **Wrapper-level `--ignore-scripts` guard**: raises `NpmScriptsEnabled` if any caller invokes `install`/`ci` without `--ignore-scripts` and `test_execution=False`. The guard is in the wrapper, not the orchestrator, so a future caller (e.g., Phase 7's Docker transform) inherits the invariant automatically.
- `src/codegenie/tools/ncu.py` (new) — typed wrapper for `npm-check-updates`. Routes through `exec.run_in_sandbox(network="scoped", allowlist=["registry.npmjs.org"])`.
- `src/codegenie/catalogs/tools/digests.yaml` extended — SHA-256 pins added for `npm` (minor-version-precision; ADR-P3-009 spec) and `ncu`. CI `tool_digests_verify` extends to check the new binaries.
- `src/codegenie/recipes/digests.yaml` (new) — SHA-256 pin manifest for recipe YAML files (ADR-P3-010-style per Gap 2). `RecipeRegistry.load()` refuses any recipe whose on-disk hash mismatches → `RecipeNotInDigestManifest`.
- `src/codegenie/recipes/catalog/npm/<recipe-id>.yaml` — at minimum one shipped recipe (e.g., `npm-upgrade-patched-v1`) defining `{id, engine: ncu, ecosystem: npm, kind: version_bump, applies_to: {...}, params: {...}, declared_inputs: [...], digest, priority}`.
- `src/codegenie/recipes/selector.py` — `RecipeSelector.select(view, advisory, skills) -> RecipeSelection`. Reads `selector.yaml` decision table; resolves to candidate set; filters by (1) ecosystem, (2) `cve_patterns`, (3) `semver_range_predicate` (`range_break` reason), (4) `RecipeEngine.available()` (`no_engine` reason), (5) Phase-2 depgraph peer-dep check (`peer_dep_conflict` reason). Ties on `priority` are errors. **Never raises for routine no-match cases** — Hypothesis property test `test_selector_is_total.py` asserts.
- `src/codegenie/recipes/selector.yaml` — flat decision table; Python `match/case` dispatch reads it.
- `src/codegenie/recipes/engines/ncu.py` — `NcuRecipeEngine` class per `phase-arch-design.md §"Component design" #2a`. `available()` does `which ncu` + version-digest check. `apply()` calls `tools.ncu.run(...)` then returns `RecipeApplication`. Engine-availability snapshot captured **once at orchestrator entry** per Gap 6.
- `src/codegenie/transforms/lockfile/resolver.py` — `LockfileResolver.run(worktree_path) -> ResolverResult(lockfile_bytes, cache_hit, npm_stdout_path, npm_stderr_path)` per `phase-arch-design.md §"Component design" #5`. Cache key `blake3((blake3(package.json) || blake3(package-lock.json) || npm_minor_digest || registry_mirror_digest))` stored under `.codegenie/cache/lockfile/<key>.zst`. Bounded transient-error retry ≤ 3 on `transient_npm_codes` (network, ETIMEDOUT, EAI_AGAIN, registry 5xx) with exponential backoff (200 ms, 500 ms, 1.2 s). Non-transient → fail fast with captured exit code. **Cache hit emits `cache.replay` audit event referencing original chain head** (synth-added per `final-design.md §"Components" #5`).
- `src/codegenie/transforms/lockfile/canonicalizer.py` — `LockfileCanonicalizer.canonicalize(bytes) -> bytes` per `phase-arch-design.md §"Component design" #6`. Parse via stdlib `json` with depth cap. Sort top-level keys lexically; sort `packages` and `dependencies` sub-objects deterministically (by key path); re-emit LF + no trailing whitespace. Idempotent (Hypothesis property test).
- ADR-P3-003 created: lockfile canonicalization (LC_ALL=C + key sort + LF) + `npm` digest pin for deterministic diff output.

**Done criteria:**
- [ ] `tests/unit/tools/test_npm_wrapper.py` — happy path, non-zero exit, timeout, malformed JSON, missing binary (`ToolNotFound`). Wrapper raises `NpmScriptsEnabled` when caller omits `--ignore-scripts` in non-test mode; does not raise in `test_execution=True`.
- [ ] `tests/unit/tools/test_ncu_wrapper.py` — same shape, 4 tests minimum.
- [ ] `tests/unit/recipes/test_registry_digest_verification.py` — `RecipeRegistry.load()` refuses recipe with hash mismatch (`RecipeNotInDigestManifest`).
- [ ] `tests/unit/recipes/test_selector.py` — ≥ 14 tests: one per `reason` enum × matched/unmatched paths; engine-availability filter; ambiguity error on priority tie.
- [ ] `tests/unit/recipes/test_selector_is_total.py` — Hypothesis property: any `(advisory, view, skills)` returns `RecipeSelection` without raising.
- [ ] `tests/unit/recipes/engines/test_ncu_engine.py` — ≥ 4 tests: happy path, non-zero exit, peer-dep refusal, sandbox error. `available()` correct on/off `$PATH`.
- [ ] `tests/unit/transforms/lockfile/test_resolver.py` — ≥ 6 tests: cache key derivation; cache-hit path emits `cache.replay`; transient retry exhaustion → `LockfileResolveFailed`; non-transient fail-fast; cache key includes all four content hashes.
- [ ] `tests/unit/transforms/lockfile/test_canonicalizer.py` — ≥ 4 tests: LF normalization, top-level key sort, sub-object sort, oversize cap; `test_canonicalizer_idempotent.py` Hypothesis property `canonicalize(canonicalize(x)) == canonicalize(x)`.
- [ ] `tests/adv/test_npm_wrapper_rejects_scripts_enabled.py` — wrapper raises `NpmScriptsEnabled` when caller omits the flag outside `test_execution=True`.
- [ ] `tests/adv/test_recipes_digests_yaml_drift_breaks_load.py` — recipe content edited without digest update; `RecipeRegistry.load()` refuses (`RecipeNotInDigestManifest`).
- [ ] `tests/unit/test_recipe_digest_in_cache_key.py` — recipe digest change ⇒ transform-apply cache key change (per Gap 2).
- [ ] New CI job extension `recipes_digests_verify` — every recipe YAML's on-disk hash matches `recipes/digests.yaml`. Wired into PR CI.
- [ ] All Step 3 code passes strict mypy.

**Depends on:** Step 1 (contracts + Pydantic + audit events + `test_execution` overlay) + Step 2 (advisory pipeline — the selector consumes `CveEntry`).

**Effort:** L — densest vertical-slice step. Two new tool wrappers, recipe registry + selector + decision table + ≥ 1 shipped recipe, `NcuRecipeEngine`, `LockfileResolver` with the four-component cache key, `LockfileCanonicalizer`. The `recipes/digests.yaml` manifest discipline (Gap 2) is the new load-bearing CI artifact.

**Risks specific to this step:** The wrapper-level `NpmScriptsEnabled` invariant is the trust boundary — if a future probe author writes `tools.npm.run(..., flags=["install"])` (without `--ignore-scripts`) in non-test mode, the wrapper raises before the subprocess starts. The adversarial test pins this. The `LockfileResolver` cache key drops npm patch-version (synth choice per `final-design.md §Goals #8`) to avoid portfolio-wide stampedes; if real-world drift shows this is too aggressive, ADR-P3-003 amends to include patch. The selector's `peer_dep_conflict` check requires Phase-2 `BuildGraphProbe`'s `resolved_edges`; if the gathered `repo-context.yaml` has `resolution_status == "static_only"`, fall back to `declared_edges` with `confidence: medium` and document the degradation.

## Step 4 — Ship `LockfilePolicyScanner` (graded escape) and the single-profile `ValidationGate` (install/test/build + signal-escalate)

**Goal:** Pre-transform lockfile policy scan refuses known-hostile patterns with a typed-violation surface; `--allow-policy-violations <types>` is the operator's audit-able opt-in. Post-transform validation gate runs install + test + (opt-in) build inside Phase-2's `run_in_sandbox` chokepoint with the new `test_execution=True` overlay; `--network=none` is the test default; network-required test failure emits `gate.signal_escalate` audit event + on-disk escalation JSON + non-zero exit 8 (does **not** auto-allow egress).

**Features delivered:**
- `src/codegenie/transforms/validation/__init__.py`, `lockfile_policy.py` per `phase-arch-design.md §"Component design" #10`. `LockfilePolicyScanner.scan(lockfile_path, *, allowed_registries, allowed_violations) -> LockfileScanResult(violations)`. Typed Pydantic violation models: `RegistryRedirect`, `MissingIntegrity`, `LifecycleScriptDeclared`, `PublishConfigOverride`, `ResolutionsRedirect`. Hard size cap (≤ 50 MB; Phase-2 cap inherited). Schema-malformed lockfile → `LockfileMalformed` (loud, not a violation).
- `src/codegenie/transforms/validation/install.py` — `install_validator(transform_output) -> ValidatorOutput`. Invokes `npm ci --ignore-scripts --no-audit --no-fund` via `run_in_sandbox(network="scoped", allowlist=["registry.npmjs.org"], test_execution=False)`. Wall budget: 180 s default. Emits `npm.install.run` audit event with `egress_bytes` recorded.
- `src/codegenie/transforms/validation/test.py` — `test_validator(transform_output, *, allow_test_network) -> ValidatorOutput`. Invokes `npm test` via `run_in_sandbox(test_execution=True, network="none" if not allow_test_network else "scoped allowlist")`. Wall budget: 600 s; PID budget: 1024. On non-zero exit, scans stderr for **network-required signatures**: `ENOTFOUND`, `ECONNREFUSED`, `getaddrinfo`, `getaddrinfo ENOTFOUND`, `getaddrinfo EAI_AGAIN`, `DNS lookup`, `Connection refused 127.0.0.1`, `connect ECONNREFUSED`, `KafkaTimeout`, common ORM connect strings (Open Question #3 — initial set; tunable via `recipes/network_signatures.yaml`). Match → `requires_network=true`, `confidence=medium`, **does not auto-allow egress**.
- `src/codegenie/transforms/validation/build.py` — `build_validator(transform_output) -> ValidatorOutput`. Opt-in via `package.json#scripts.build`. Same sandbox, `test_execution=False`, `network="scoped"`.
- `src/codegenie/transforms/validation/trust_score.py` — `TrustScorer.score(signals) -> TrustScore(binary, confidence, detail)` per `phase-arch-design.md §"Component design" #12`. Strict-AND of nine objective signals per ADR-0008. Audit log records *which* signal flipped.
- `src/codegenie/transforms/validation/gate.py` — `validate(transform_output, *, allow_test_network) -> GateOutcome(green, confidence, validators, signal_escalate, trust_score)` orchestrates the three validators and the trust scorer. Maps to exit codes: 0 green; 6 install/test/build fail without network signature; 8 test fail **with** network signature.
- **`gate.signal_escalate` operator surface** per Gap 3:
  - JSON event written to `.codegenie/remediation/<run-id>/escalations/<utc>.json` containing `{kind, suggested_flag: "--allow-test-network", signal, timestamp, validator_name}`.
  - `remediation-report.yaml` top-level `escalations: [...]` section populated.
  - CLI stderr banner printed prominently on exit 8.
- `src/codegenie/recipes/network_signatures.yaml` — pinned list of stderr regexes for the network-required scan. Closed enum on signature kind; new signatures require code + schema PR in the same change.
- ADR-P3-004 created: `LockfilePolicyScanner` violations are retryable-with-widening at Phase 5; Phase 3 ships `--allow-policy-violations` graded escape.

**Done criteria:**
- [ ] `tests/unit/transforms/validation/test_lockfile_policy.py` — one test per violation type (`RegistryRedirect`, `MissingIntegrity`, `LifecycleScriptDeclared`, `PublishConfigOverride`, `ResolutionsRedirect`) + `--allow-policy-violations` flag path; oversize lockfile → hard cap fires; malformed lockfile → `LockfileMalformed` (not a violation).
- [ ] `tests/unit/transforms/validation/test_install.py` — happy; non-zero install fails closed; `network="scoped"` enforced; `npm.install.run` audit event with `egress_bytes`.
- [ ] `tests/unit/transforms/validation/test_test_gate.py` — happy; non-zero test fails closed without network signature → exit 6; non-zero test with network signature → `requires_network=true`, `gate.signal_escalate` event, exit 8; `--allow-test-network` opt-in widens sandbox to scoped allowlist.
- [ ] `tests/unit/transforms/validation/test_build.py` — opt-in path activates only when `scripts.build` present.
- [ ] `tests/unit/transforms/validation/test_trust_score.py` + Hypothesis `test_trust_score_strict_and.py` — strict-AND property; any false signal → low; all true and `tests.duration_vs_baseline_pct ≤ 150` → high; otherwise medium.
- [ ] `tests/adv/test_test_profile_refuses_scoped_network_without_flag.py` — sandbox raises if `network="scoped"` requested for test without `--allow-test-network` propagated.
- [ ] `tests/integration/test_remediate_lockfile_policy_violation_blocked.py` — fixture lockfile redirects registry; exit 7 with `escalation.policy_violation` audit event.
- [ ] `tests/integration/test_remediate_lockfile_policy_violation_allowed.py` — same fixture + `--allow-policy-violations RegistryRedirect` → exit 0.
- [ ] `tests/integration/test_remediate_test_needs_network_escalates.py` — fixture test imports `pg`; exit 8; escalation JSON on disk; `remediation-report.yaml` has `escalations: [...]`.
- [ ] All Step 4 code passes strict mypy.

**Depends on:** Step 1 (`test_execution=True` overlay, audit events) + Step 3 (`tools.npm` wrapper with `NpmScriptsEnabled` guard).

**Effort:** M — three validators + scanner + trust scorer + gate. The network-required signature scan is the highest-cognitive-load piece because the signature catalog (Open Question #3) is empirical and will evolve. Pinning the initial set in `network_signatures.yaml` makes future updates auditable.

**Risks specific to this step:** The `gate.signal_escalate` exit-8 path is **the** Phase-3-flavored honest-failure mode — the architecture explicitly does **not** auto-allow egress on the network signature match. Adversarial test pins this: a test failing with `ENOTFOUND` must not result in the sandbox being silently widened to `scoped`; it must exit 8 and require an explicit operator re-run with `--allow-test-network`. The `LockfilePolicyScanner` `--allow-policy-violations` flag takes a comma-separated list of types; closed-enum validation in click prevents typos (e.g., `--allow-policy-violations registry-redirect` vs `RegistryRedirect`) from silently allowing nothing.

## Step 5 — Ship `NpmPackageUpgradeTransform`, `RemediationOrchestrator`, `PatchBranchWriter`, and the `codegenie remediate` CLI surface

**Goal:** The end-to-end `codegenie remediate <repo> --cve <id>` flow works on a Node fixture with `NcuRecipeEngine`. The six-call linear sync orchestrator runs in order; failure preserves worktree + branch + audit slice; the exit-code mapping is documented and enforced; the green-path `PatchBranchWriter` finalizes the branch + writes `remediation-report.yaml` + `diff/<recipe-id>.patch` + `raw/*` + `audit/<run-id>.jsonl`.

**Features delivered:**
- `src/codegenie/transforms/npm_package_upgrade.py` — `NpmPackageUpgradeTransform(Transform)` per `phase-arch-design.md §"Component design" #4`. `name = "npm_package_upgrade"`, `applies_to_tasks = ["vuln_remediation"]`, `applies_to_languages = ["javascript","typescript"]`, `requires_recipe_engines = ["ncu", "openrewrite"]`. Internal flow:
  1. `git worktree add` into `.codegenie/remediation/<run-id>/worktree` (refuses if `<run-id>` already has a worktree; calls `PatchBranchWriter._refuse_dirty_tree()` for the source).
  2. `RecipeEngine.apply(recipe, worktree, ctx)`.
  3. `LockfileResolver.run(worktree)`.
  4. `LockfileCanonicalizer.canonicalize(lockfile_bytes)`.
  5. `git -c core.hooksPath=/dev/null -c commit.gpgsign=false -c user.email=codegenie-bot@codegenie.invalid -c user.name=codegenie-bot commit`; `git format-patch -1 --stdout` → `.codegenie/remediation/<run-id>/diff/<recipe-id>.patch`.
  Each step emits its typed audit event. The transform never catches `Exception` — the orchestrator catches once per Component-design #1 failure behavior.
- `src/codegenie/transforms/coordinator.py` — `remediate(repo_root, cve_id, *, run_id, config) -> RemediationReport` per `phase-arch-design.md §"Component design" #9`. Six explicit function calls (`load_context`, `resolve_advisory`, `select_recipe`, `scan_lockfile`, `apply_transform`, `validate`, `write_branch`). No async, no retry inside the orchestrator (Phase 5 wraps). Docstring explicitly states the no-retry property so Phase 5 extends without contradicting. Failure preservation: worktree + partial branch + audit slice remain on disk under `.codegenie/remediation/<run-id>/` on any non-green exit code.
- `src/codegenie/transforms/branch_writer.py` — `PatchBranchWriter.write(outcome) -> BranchHandoff` per `phase-arch-design.md §"Component design" #13`. Refuses dirty tree (`WorkingTreeNotClean`); refuses existing branch (`BranchExists`); branch name = `codegenie/vuln-fix/<cve-id>-<short-sha>`; every git invocation uses the four `-c` flags (hooks disabled, gpg disabled, bot identity); writes the full artifact bundle.
- `src/codegenie/transforms/context.py` — `RepoContextView` read-only wrapper around `repo-context.yaml`; consumed by `Transform.applies()`. `load_context(repo_root, *, auto_gather)` validates schema; checks `IndexHealthProbe.confidence ≥ medium` on the `cve` domain; if `auto_gather` and stale → re-runs Phase 0/1/2 gather in-process. Gather failure → exit 9 per Gap 7.
- CLI: `codegenie remediate <repo> --cve <id> [--engine {ncu,openrewrite}] [--allow-policy-violations <types>] [--allow-test-network] [--allow-stale-feeds] [--strict] [--auto-gather|--no-auto-gather] [--run-id <id>]`. Click validates `--cve` against `CVE-\d{4}-\d{4,}`. Tool-readiness check (`git`, `npm`, `ncu`; `java` only when `--engine=openrewrite`).
- CLI: `codegenie recipes list [--engine X] [--task vuln_remediation]`.
- Exit-code mapping enforced in CLI layer:

  | Code | Meaning |
  |---|---|
  | 0 | success |
  | 4 | no_recipe (selection.reason != "matched") |
  | 5 | transform_fail (engine or resolver) |
  | 6 | validation_fail (install/build/test failed without network signal) |
  | 7 | policy_violation (LockfilePolicyScanner refused) |
  | 8 | signal_escalate (test failed with network-required signature) |
  | 9 | auto_gather_failure (precondition gather failed) |

- **Engine-availability snapshot capture** per Gap 6: the orchestrator captures `RecipeEngine.available()` **once at entry** into `RemediationAttempt.engine_availability`; the transform reads from the snapshot, not by re-calling `available()`.

**Done criteria:**
- [ ] `tests/unit/transforms/test_npm_package_upgrade.py` — ≥ 10 tests: happy path; lockfile-canonicalization golden; worktree dirty refusal; engine-error propagation; resolver-error propagation; bot committer identity verified.
- [ ] `tests/unit/transforms/test_coordinator.py` — ≥ 6 tests, one per exit-code path (0, 4, 5, 6, 7, 8, 9).
- [ ] `tests/unit/transforms/test_branch_writer.py` — happy; dirty-tree refusal (`WorkingTreeNotClean`); existing-branch refusal (`BranchExists`); bot committer identity; `core.hooksPath=/dev/null` honored; `commit.gpgsign=false` honored.
- [ ] `tests/unit/transforms/test_context.py` — `load_context` validates schema; stale + `auto_gather=True` re-runs gather; gather failure → exit 9.
- [ ] `tests/integration/test_remediate_express_e2e.py` — express fixture, ncu engine, full happy path; exit 0; branch on disk; `remediation-report.yaml` present.
- [ ] `tests/integration/test_remediate_no_recipe_clean_skip.py` — selector miss → exit 4 → `TransformOutput(skipped=True, errors=["catalog_miss"])`.
- [ ] `tests/integration/test_remediate_install_fails.py` — bumped version fails `npm ci`; exit 6.
- [ ] `tests/integration/test_remediate_pnpm_workspace.py` — exit 4 with `reason="unsupported_dialect"`.
- [ ] `tests/integration/test_remediate_yarn_classic.py` — same shape.
- [ ] `tests/integration/test_remediate_auto_gather_failure_exit_9.py` — Gap 7 verification.
- [ ] `tests/adv/test_engine_availability_snapshot.py` — Gap 6 verification: synthetic environmental flux between selector + transform; both see the same `available()` result.
- [ ] All Step 5 code passes strict mypy.

**Depends on:** Steps 1–4. The orchestrator is the integration point for every prior component.

**Effort:** L — orchestrator + transform + branch writer + context loader + CLI surface + nine integration tests. The exit-code mapping is the operator-facing contract; the CLI layer's mapping table is asserted by tests.

**Risks specific to this step:** The orchestrator's no-retry-inside discipline is the contract Phase 5 wraps; the docstring is load-bearing. The `auto_gather` recursion (Gap 7) is the only place Phase 3 can invoke Phase 0/1/2 — exit 9 propagates with the gather's audit slice attached, and both layers append to the same chain (no chain break). The bot committer identity (`codegenie-bot@codegenie.invalid`) is set per-invocation via `-c` flags, never via `git config` — encode this in `test_branch_writer.py` so a future refactor cannot silently rely on user-level git config.

## Step 6 — Ship `OpenRewriteEngineStub` (opt-in, JVM-gated, pinned-jar smoke recipe)

**Goal:** The second engine seat is registered and proven to extend the `RecipeEngine` ABC. `--engine=openrewrite` opts in to the stub; if `java` is missing or the pinned jar digest mismatches, the selector emits `RecipeSelection(reason="no_engine")` cleanly without failing the run. One smoke-tested OpenRewrite-shaped recipe ships under `recipes/openrewrite-stub/`. No Maven Central reach-through; no install ceremony.

**Features delivered:**
- `tools/openrewrite/<digest>.jar` — pinned self-contained jar. SHA-256 in `tools/digests.yaml`.
- `src/codegenie/tools/openrewrite.py` (new) — typed wrapper. Routes through `exec.run_in_sandbox(network="none")`. Invokes `java -Xmx2g -jar tools/openrewrite/<digest>.jar <recipe-id>`. Initial heap/wall: `-Xmx2g`, 300 s (Open Question #5; tunable in `recipes/openrewrite-stub/config.yaml`).
- `src/codegenie/recipes/engines/openrewrite_stub.py` — `OpenRewriteEngineStub(RecipeEngine)`. `available()` returns False if `java` missing OR jar digest mismatches (the engine is *registered-but-unavailable*; selector emits `reason="no_engine"` with `diagnostics={"engine":"openrewrite","available":False}`). `apply()` calls `tools.openrewrite.run(...)`.
- `src/codegenie/recipes/catalog/openrewrite-stub/<recipe-id>.yaml` — one shipped recipe (final candidate per Open Question #1; e.g., `org.openrewrite.npm.UpgradeDependencyVersion`-shaped or a minimal internal equivalent). Digest pinned in `recipes/digests.yaml`.
- `src/codegenie/recipes/catalog/openrewrite-stub/config.yaml` — JVM heap + wall-clock config.
- CLI: `--engine=openrewrite` propagates through orchestrator → selector → transform.

**Done criteria:**
- [ ] `tests/unit/recipes/engines/test_openrewrite_stub.py` — ≥ 3 tests: smoke recipe success on a CI runner with `java`; `available() == False` when `java` missing; `available() == False` when jar digest mismatch.
- [ ] `tests/integration/test_remediate_openrewrite_stub_e2e.py` — single recipe via `OpenRewriteEngineStub`; CI-matrix-skipped on runners without `java` (skip reason recorded).
- [ ] `tests/adv/test_openrewrite_stub_isolation.py` — JVM invocation inside `run_in_sandbox(network="none")` cannot reach Maven Central; no file written outside worktree.
- [ ] `tests/adv/test_tools_digests_yaml_drift_breaks_install.py` — `openrewrite-jar` digest mismatch at install; CI red.
- [ ] All Step 6 code passes strict mypy.

**Depends on:** Steps 1–5.

**Effort:** S — one engine class + one tool wrapper + one shipped recipe + one config file. The JVM-gating discipline is well-established (Phase 2 precedent for opt-in tools); the stub uses a self-contained jar so there is no Maven mirror to maintain (`final-design.md §"Components" #2`).

**Risks specific to this step:** The OpenRewrite stub recipe choice (Open Question #1) may need to be a minimal internal recipe if the OpenRewrite npm ecosystem is too thin — document the final choice in the ADR amendment if it deviates from the upstream candidate. The JVM cold-start cost (2–4 s) is acceptable because the engine is opt-in via `--engine=openrewrite`; the default `ncu` path is unaffected.

## Step 7 — Harden: ≥ 30 adversarial fixtures, determinism canary, perf canaries, Phase-2 regression hard-gate, and Phase 4 handoff verification

**Goal:** Adversarial corpus (≥ 30 fixtures) exists and is CI-gated. The determinism canary runs the full pipeline 5× on the same fixture and asserts byte-identical diffs and branch SHAs. The perf canaries assert hot-path p95 ≤ 30 s (excluding test suite) and lockfile cache hit rate ≥ 70% across the portfolio. The Phase-2 regression hard-gate (`test_phase2_unchanged.py`) re-runs every Phase 2 integration test verbatim. The Phase 4 handoff contract is verified by an integration test that consumes `RecipeSelection.reason`, `TransformOutput.errors`, and the `RemediationReport` shape.

**Features delivered:**
- `tests/fixtures/repos_bundles/` — ≥ 6 `.bundle` files (express, pnpm-workspace, yarn-classic, peer-dep-conflict, monorepo, postinstall-rce-attempt) per `phase-arch-design.md §"Component design" #15`.
- `tests/fixtures/npm-mirror/` — pinned local registry mirror (~5 MB, tarball-stub directory). `tests/fixtures/npm-mirror/digests.yaml` pins tarball hashes.
- For each fixture: recorded `npm-resolution.json` capturing the exact lockfile-resolution result on bundle-creation day (Open Question #2 — convention TBD; the chosen mechanism is documented in the ADR amendment).
- `tests/adv/` — ≥ 30 fixtures covering: npm-install postinstall blocked, lockfile policy violations (all five types), test-execution isolation (filesystem, network, wall, pid, memory, fork-bomb), OpenRewrite-stub isolation, git-hooks-disabled, signing-key absent, branch refusals (dirty + existing), audit chain integrity, no-credentials-in-sandbox, fence-job tests, CVE snapshot tampering, recipe digest drift, tools digest drift. Synth-relaxed from S's ≥ 40 because ten of S's fixtures targeted a second sandbox profile that does not exist in this design.
- `tests/integration/test_byte_identical_diff_5x.py` — determinism canary; runs full pipeline 5× on the canary fixture; asserts byte-identical diffs and branch tree SHAs (ADR-P3-003).
- `tests/integration/test_hot_path_latency.py` — performance canary; caches warm; assert p95 ≤ 30 s (excluding test suite execution); fixture has a one-test suite finishing < 1 s.
- `tests/integration/test_lockfile_cache_hit_rate.py` — performance canary; assert ≥ 70% lockfile cache hits across the fixture portfolio.
- `tests/integration/test_fixture_mirror_pin_integrity.py` — asserts mirror tarball hashes against `tests/fixtures/npm-mirror/digests.yaml` per Gap 5.
- `tests/integration/test_phase2_unchanged.py` — re-runs every Phase-2 integration test verbatim against `nestjs/nest` pin (regression hard-gate per Phase-7 precedent in Phase 2).
- `tests/integration/test_phase4_handoff_contract.py` — verifies that a Phase-4-shaped consumer can read `RecipeSelection.reason`, `TransformOutput.errors`, `ValidatorOutput.errors`, and `RemediationReport` without importing any Phase 3 internals. Acts as the load-bearing handoff snapshot.
- Memory regression canary: `resource.getrusage(RUSAGE_CHILDREN)` peak RSS in the hot-path test; fail if > 1.5 GB.
- New CI gates wired:
  - `fence` — extended to forbid LLM SDKs under `transforms/` + `recipes/` (Step 1, finalized here as CI-gating).
  - `tool_digests_verify` — extended to verify `npm`, `ncu`, `openrewrite-jar` digests.
  - `recipes_digests_verify` — every recipe YAML's on-disk hash matches `recipes/digests.yaml`.
  - `determinism_canary` — blocks merge.
  - `adversarial_corpus` — blocks merge.
- Coverage ratchets: 90% line / 80% branch on new packages; 95% line / 90% branch on `transforms/contract.py`, `recipes/contract.py`, `transforms/coordinator.py`.
- Operator runbook: `docs/phases/03-vuln-deterministic-recipe/runbook.md` documents the `signal_escalate` flow ("What to do when you see `signal_escalate`") per Gap 3, fixture rotation policy per Gap 5, and the `codegenie remediation gc` policy stub per Open Question #11.

**Done criteria:**
- [ ] ≥ 30 fixtures under `tests/adv/` pass; corpus gates the merge.
- [ ] `test_byte_identical_diff_5x.py` passes; CI-gating.
- [ ] `test_hot_path_latency.py` passes p95 ≤ 30 s.
- [ ] `test_lockfile_cache_hit_rate.py` passes ≥ 70%.
- [ ] `test_phase2_unchanged.py` re-runs every Phase 2 integration test green.
- [ ] `test_phase4_handoff_contract.py` confirms the consumable surface is intact.
- [ ] `test_fixture_mirror_pin_integrity.py` passes; mirror size ≤ 5 MB (warns at 10 MB per Gap 5).
- [ ] All five new/extended CI gates green on the merge commit.
- [ ] Runbook on disk; cross-linked from `README.md` and from CLI exit-code-8 stderr banner.
- [ ] Roadmap exit criterion verified end-to-end: `codegenie remediate <node-fixture> --cve <id>` writes a working patch on `codegenie/vuln-fix/<cve-id>-<short-sha>`; the diff applies via `git apply`; `npm ci --ignore-scripts` succeeds; the repo's own `npm test` passes inside the sandboxed gate.

**Depends on:** Steps 1–6 (every prior step must be green before the corpus hardens).

**Effort:** L — fixture authoring is the time sink. The 5× determinism canary is the highest-value-per-LOC test in the phase because it catches `npm` output drift, `ncu` non-determinism, and lockfile-canonicalizer regressions in one pass.

**Risks specific to this step:** Fixture portfolio rotation policy (Gap 5) is the maintenance cost: the recorded `npm-resolution.json` is the authoritative "what npm would produce on this lockfile + registry-mirror combination today" — never re-derived from live `npm install` in CI. Quarterly rotation is gated by an ADR amendment; npm major-version bumps trigger an out-of-cycle rotation. The mirror size budget (≤ 5 MB target; ≥ 10 MB triggers git-lfs migration per Open Question #8) is the early-warning signal — the `test_fixture_mirror_pin_integrity.py` test surfaces drift loudly. The Phase-4 handoff test (`test_phase4_handoff_contract.py`) is the contract-snapshot equivalent for the *consumer* side — if Phase 4 needs an additional field, an ADR amendment + this test's update is the required gate.

## Exit-criteria mapping

> Roadmap §"Phase 3" exit: "Given a Node.js repo with a known npm CVE, the system writes a working patch diff on a local branch that — when applied — installs cleanly and passes the repo's own tests."

| Exit criterion | Step(s) |
|---|---|
| Reads `RepoContext` and Skills | Step 5 (`load_context` + `RepoContextView`) |
| Chooses a recipe | Step 3 (`RecipeSelector.select` → `RecipeSelection`) |
| Applies it (deterministic transform) | Step 3 (`NcuRecipeEngine`) + Step 5 (`NpmPackageUpgradeTransform`) + Step 6 (`OpenRewriteEngineStub` opt-in) |
| Writes the diff plus a local branch | Step 5 (`PatchBranchWriter`); branch `codegenie/vuln-fix/<cve-id>-<short-sha>`; diff at `.codegenie/remediation/<run-id>/diff/` |
| No LLM in this loop | Step 1 (`fence` CI extension to `transforms/` + `recipes/`); Step 7 (CI-gating) |
| Installs cleanly | Step 4 (`install_validator` — `npm ci --ignore-scripts`) |
| Passes the repo's own tests | Step 4 (`test_validator` — `npm test` in `--network=none` overlay); Step 7 (gate verified end-to-end on real fixture) |
| Single-repo, local, deterministic | Step 5 (linear sync orchestrator); Step 7 (determinism canary 5× byte-identical) |

## Implementation-level risks

1. **The `Transform` ABC v0.3.0 is the most consequential review in Phase 3.** Phase 4/5/7/15 all inherit. Mitigation: snapshot test freezes the signature; review against four future-phase use cases is the merge-gate; `requires_recipe_engines` is the new declarative field over the Probe shape — needed because engines are pluggable, but the deviation is documented in ADR-P3-001 so a future reviewer doesn't try to "harmonize" the contracts.
2. **`npm install --package-lock-only` is the diff-generation primitive and is not perfectly deterministic across npm versions.** Mitigation: `npm` digest pin in `tools/digests.yaml`; cache key includes `npm_minor_digest` (patch dropped); `LockfileCanonicalizer` (LC_ALL=C + key sort + LF). Residual: npm minor bumps trigger portfolio-wide cache rebuild — pre-warm on the bump PR's CI run. `tests/adv/test_tools_digests_yaml_drift_breaks_install.py` pins the discipline.
3. **`LockfilePolicyScanner` may block legitimate enterprise repos.** Mitigation: `--allow-policy-violations <types>` graded escape valve; Phase 5 wraps with widening retry; runbook documents common legitimate cases (GitHub-tarball deps, `publishConfig.registry` for private publishing). The closed-enum on violation types prevents typo-silent-allowance.
4. **`gate.signal_escalate` has no human in the local POC** (Gap 3). Mitigation: prominent stderr banner + on-disk escalation JSON + `remediation-report.yaml#escalations[]` section + runbook entry. Phase 5's gate machinery routes to LangGraph `interrupt()`; Phase 11 routes to CODEOWNERS notifier. The audit event is the source-of-truth.
5. **OpenRewrite stub coverage is intentionally narrow (one recipe).** Mitigation: the *contract* ships, not the catalog. Phase 4–7 expand. The narrow coverage is documented in the design and ADR-P3-002 so a future engineer doesn't interpret one recipe as a "TODO".
6. **CVE feed staleness silently producing wrong bumps.** Mitigation: snapshot-staleness graded advisory (warn>7d / low>30d / refuse>90d); `CveRetractionProbe` marks `evidence_stale` on prior remediations; `--allow-stale-feeds` is the explicit operator opt-in. Phase 14 closes with webhook ingestion.
7. **`recipes/digests.yaml` drift** (Gap 2). Mitigation: `recipes_digests_verify` CI gate; PR must update YAML + manifest in the same commit; `tests/adv/test_recipes_digests_yaml_drift_breaks_load.py` asserts.
8. **Fixture portfolio rotation cost** (Gap 5). Mitigation: quarterly cadence gated by ADR amendment; out-of-cycle triggers documented; `test_fixture_mirror_pin_integrity.py` surfaces drift loudly; mirror size budget ≤ 5 MB.
9. **Engine availability check inconsistency** (Gap 6). Mitigation: snapshot captured once at orchestrator entry into `RemediationAttempt.engine_availability`; transform reads from snapshot, not by re-calling `available()`. Property test `test_engine_availability_snapshot.py` pins.
10. **`auto_gather` recursion failure** (Gap 7). Mitigation: gather failure → exit 9 with gather's audit slice attached; both layers append to the same chain (no chain break). `test_remediate_auto_gather_failure_exit_9.py` pins.

## What's next — handoff to Phase 4

- **New artifacts on disk:**
  - `.codegenie/remediation/<run-id>/remediation-report.yaml` — index of every artifact + `escalations[]` section.
  - `.codegenie/remediation/<run-id>/diff/<recipe-id>.patch` — the byte-deterministic patch.
  - `.codegenie/remediation/<run-id>/raw/{ncu.json, install.log, test.xml, ...}` — raw subprocess outputs.
  - `.codegenie/remediation/<run-id>/audit/<run-id>.jsonl` — BLAKE3-chained Phase-3 audit slice that extends Phase-2's chain.
  - `.codegenie/remediation/<run-id>/escalations/<utc>.json` — `gate.signal_escalate` payloads (when applicable).
  - `.codegenie/cve/snapshots/<source>/<sha256>.json.gz` — content-addressed CVE feed snapshots.
  - `.codegenie/cache/lockfile/<key>.zst` — lockfile resolver cache.
  - `src/codegenie/recipes/catalog/npm/*.yaml` + `recipes/openrewrite-stub/*.yaml` — recipe catalog (Phase 15's authoring target).
  - `src/codegenie/recipes/digests.yaml` — recipe pin manifest (Gap 2 discipline).

- **New contracts ready for Phase 4 consumers:**
  - **`Transform` ABC** (frozen at v0.3.0; `tests/unit/transforms/test_contract.py` pins). Phase 4's `PlanningOrchestrator` wraps the selector at the orchestrator layer; never edits `transforms/contract.py`.
  - **`RecipeEngine` ABC** (frozen at v0.3.0; `tests/unit/recipes/test_contract.py` pins). Phase 4 adds new engines additively; never edits `recipes/contract.py`.
  - **`RecipeSelection(recipe, reason, diagnostics)` triple** with closed `reason` enum. Phase 4 reads `selection.reason` to route the recipe → RAG → LLM-fallback decision chain: `"catalog_miss"` → RAG; `"range_break"` / `"peer_dep_conflict"` / `"unsupported_dialect"` → RAG + LLM with diagnostics; `"no_engine"` → exit cleanly (LLM cannot install Java); `"matched"` → no LLM, Phase 3 path proceeds.
  - **`TransformOutput.errors`** + **`ValidatorOutput.errors`** — typed-string diagnostic signals Phase 4 feeds the LLM at fallback time.
  - **`RemediationReport` schema** — Phase 6 (LangGraph state ledger), Phase 9 (Temporal Activity output), Phase 11 (PR body construction), Phase 13 (cost ledger) all consume.
  - **`TrustScore.binary == False` or `TrustScore.confidence == "low"`** — the trigger Phase 4 reads to activate RAG/LLM fallback.
  - **Audit chain Phase-3 event set** — Phase 8 (`confidence_summary` hot view), Phase 11 (PR evidence bundle), Phase 14 (transparency log promotion) consume.
  - **`cve.store` snapshot model** — Phase 14 webhook ingestion replaces manual `cve sync`; the snapshot interface is forward-compatible.

- **New CI gates in place:**
  - `fence` — forbids `anthropic`, `langgraph`, `chromadb`, `qdrant`, `sentence-transformers`, `voyageai`, `openai` under `transforms/` + `recipes/`.
  - `tool_digests_verify` — extended to include `npm`, `ncu`, `openrewrite-jar`.
  - `recipes_digests_verify` — every recipe YAML's on-disk hash matches `recipes/digests.yaml`.
  - `determinism_canary` — 5× byte-identical diff + branch SHA blocks merge.
  - `adversarial_corpus` — ≥ 30 fixtures block merge.
  - Coverage ratchet at 90/80, 95/90 on the three contract files.

- **Implicit assumptions Phase 4 can now make:**
  - The deterministic recipe path is the *first* attempt; Phase 4's planner is the *fallback* — invoked only when `RecipeSelection.reason != "matched"` or `TrustScore.confidence == "low"`.
  - The `Transform` ABC is frozen; any Phase 4 extension is *additive* (new transforms registered via `@register_transform`, new fields with defaults preserving v0.3.0 caller behavior; Gap 1 policy).
  - The `RecipeEngine` ABC is frozen; Phase 4 may register a new LLM-backed engine (e.g., `LlmRecipeEngine`) so long as it satisfies `available()` + `apply()`.
  - The `RecipeSelection.reason` closed-enum set was chosen with Phase 4's needs in mind; a sixth reason requires an ADR amendment + code + schema PR in the same change (the Phase-2 `detect.type` discipline carried forward).
  - The audit chain advances across Phase 2 → Phase 3 → Phase 4 with no chain break; Phase 4's new event types append to the enum additively.
  - The validation gate's strict-AND `TrustScorer` is the objective-signal source-of-truth; Phase 4 does **not** feed LLM-self-reported confidence into the score (ADR-0008 carried forward).
  - The `gate.signal_escalate` exit-8 path is the honest-failure mode; Phase 5's gate machinery routes to `interrupt()` once that lands. Phase 4 does **not** auto-allow egress on the network signature.
  - `auto_gather` exit 9 is a hard precondition failure; Phase 4 inherits without modification.
  - `OpenRewriteEngineStub` is registered-but-narrow (one recipe); Phase 15's recipe-authoring target is OpenRewrite-shaped recipes authored *against* this engine. Phase 4 may stub new OpenRewrite recipes (with digest discipline) into the catalog before Phase 15 lands the agent.
