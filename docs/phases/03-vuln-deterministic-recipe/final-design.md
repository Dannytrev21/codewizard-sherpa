# Phase 3 — Vuln remediation: deterministic recipe path: Final design

**Status:** Design of record.
**Synthesized by:** Graph-of-Thought synthesizer subagent
**Date:** 2026-05-12
**Sources:** `design-performance.md` · `design-security.md` · `design-best-practices.md` · `critique.md`

---

## Lens summary

Phase 3 ships the first **transform** — the second load-bearing contract in the system after Phase 1's `Probe`. Three competing designs proposed three different shapes: performance-first reframed transforms as ad-hoc `stdlib JSON mutation` for throughput; security-first wrapped everything in two divergent sandbox profiles plus a signed-feed ceremony; best-practices proposed four new top-level packages and three coordinate ABCs. The critic flagged that all three are wrong in characteristic ways: performance-first **drops the recipe-as-data property** entirely, security-first **redefines retries into Phase-4 planner work and breaks real repos with `--network=none` HARD on tests**, and best-practices **proliferates packages and ABCs** while making testing brittle by freezing registry resolution in git bundles.

The synthesis takes the best-practices ABC shape (because Phase 4, 5, 7, 15 all extend the contract Phase 3 lands), the performance-first cost discipline (cache aggressively, `--package-lock-only` on the diff path, mmap'd fix-index), and the security-first trust posture (mandatory `--ignore-scripts` outside test execution, `LockfilePolicyScanner` as a fact-emitting probe with **retryable policy violations**, audit chain extension), with one **departure from all three**: the recipe engine is an ABC with **two implementations shipping** — `NcuRecipeEngine` (the Phase 3 default) and `OpenRewriteEngineStub` (a one-recipe smoke test, registered, golden-tested, JVM-gated). This preserves the roadmap's named OpenRewrite seat without taking on the full Maven-mirror operational ceremony, and gives Phase 15 a recipe ecosystem to author into rather than a single-CLI surface.

Phase 3 is one repo, one process, no async, no state machine. The orchestrator is six function calls in a row. The retry policy is **deferred to Phase 5** (best-practices wins; performance-first's transient-error retry is the only exception, and it lives inside the lockfile resolver — not the orchestrator). Network egress for CVE feeds is **fixture-pinned for tests + `codegenie cve sync` for operators**, with content-hashing on every snapshot and *signature verification where the upstream supports it* (NVD JSON 2.0 `.meta`, GHSA web-flow commits) but **not blocking on signature failure** in v0.3.0 — the gate is "snapshot hash matches manifest"; signature is a confidence input. CVE retraction becomes a probe (`CveRetractionProbe`) that marks prior remediations as `evidence_stale`. The validation gate runs full `npm test` in Phase 1/2's existing `run_in_sandbox` chokepoint (one profile, with a `test_execution=True` overlay flag — second sandbox profile is *not* added in Phase 3). Tests that need network signal-escalate to human via the audit log; Phase 3 does not silently allow egress.

---

## Goals (concrete, measurable)

Provenance: `[P]` performance · `[S]` security · `[B]` best-practices · `[synth]` synthesizer.

### Contract goals

1. **Public ABCs introduced:** **two** — `Transform` and `RecipeEngine`. Validators are **functions** on the `Transform`, not a third ABC. Recipes are **YAML data** under `src/codegenie/recipes/catalog/`. `[B-shape, synth-trimmed]`
2. **New top-level packages:** **two** — `src/codegenie/transforms/` (contains the ABC, the npm transform, the orchestrator, validator helpers, and CVE-feed reader) and `src/codegenie/recipes/` (engine ABC, ncu + openrewrite-stub engines, catalog loader, selector). CVE-feed code lives under `transforms/cve/`. Validation helpers live under `transforms/validation/`. No `cve/` or `validation/` top-level packages. `[synth — departs from B's four-package layout per critic §best-practices.3]`
3. **`Transform` ABC contract** modeled on the v0.1.0 `Probe` ABC: `name`, `declared_inputs`, `applies_to_tasks`, `applies_to_languages`, `applies()`/`run()`. Frozen at v0.3.0 with a snapshot test (`test_transform_contract.py`). `[B]`
4. **`RecipeEngine` ABC** with two registered implementations in v0.3.0: `NcuRecipeEngine` (default for npm version bumps; on PATH check at startup) and `OpenRewriteEngineStub` (one smoke-tested recipe; requires `java` + a pinned `tools/openrewrite/<digest>.jar`; **JVM availability is opt-in via `--engine=openrewrite` and the orchestrator skips it cleanly when java/jar missing**). `[synth — explicit response to critic's roadmap-level OpenRewrite critique]`
5. **Selector returns a structured signal**, not `Optional[Recipe]`: `RecipeSelection(recipe: Recipe | None, reason: Literal["matched","no_engine","range_break","peer_dep_conflict","unsupported_dialect","catalog_miss"], diagnostics: dict)`. Phase 4 wraps the selector by reading `reason`. `[synth — closes critic's "best-practices hidden assumption #1"]`

### Cost & latency goals

6. **Tokens per run: 0.** Phase 0 `fence` CI job extended with `src/codegenie/transforms/`, `src/codegenie/recipes/`. `[P, S, B]`
7. **Wall-clock targets** (Node fixture, M-series Mac / 4-vCPU Linux runner):
   - Hot path (RepoContext cached, lockfile resolve cached, fast-suite green): **p50 ≤ 30 s, p95 ≤ 90 s** including a small test suite. `[P-relaxed]`
   - Cold lockfile + full `npm test`: **p50 ≤ 120 s, p95 ≤ 240 s**, dominated by `npm install` + the repo's suite. `[P+B]`
   - Selector + transform-apply alone: **p50 ≤ 3 s.** `[B]`
8. **Lockfile resolver cache hit rate target ≥ 70%** across the fixture portfolio. Cache key includes npm minor-version digest, **not patch** — this avoids portfolio-wide stampedes on every `npm` patch release. `[P, synth — picks P's open question #6]`

### Trust & safety goals

9. **`--ignore-scripts` mandatory** on every `npm install`/`npm ci` invocation. **Off only inside the validation `npm test` step**, which is the test command itself. Wrapper-level guard raises `NpmScriptsEnabled` if any caller skips the flag in non-test mode. CI test asserts. `[S]`
10. **`LockfilePolicyScanner` as a fact-emitting validator** (not a Phase-2 probe; not a recipe engine). It produces `LockfileScanResult.violations: list[Violation]`. Violations are **retryable with widening** at Phase 5 (per critic recommendation), but in Phase 3 — which has no retry layer — they produce `TransformOutput(confidence="low", warnings=[...])` and **the orchestrator emits an `escalation.policy_violation` audit event but continues if `--allow-policy-violations` is set, else exits non-zero**. Policy violations are *not* hard-non-retryable. `[S-shape, synth-softened per critic §security.2]`
11. **Test execution sandbox:** Phase 2's existing `run_in_sandbox` chokepoint with a new `test_execution=True` overlay flag. The overlay (a) keeps the chokepoint single, (b) gives test execution a writable upper layer for the test runner's tmp output, (c) keeps `--network=none` **as the default with an explicit escalation signal — not a HARD wall**. If a test fails with a recognizable network-required signature, the validator emits `confidence: medium`, `requires_network: true`, and **the audit record requests human escalation** (per critic recommendation: "tests run in `--network=none` by default and the validation gate's 'needs network' signal escalates to human, not auto-allow"). `[synth — single profile + escalation, departs from both P (scoped) and S (HARD)]`
12. **Branch hygiene:** name = `codegenie/vuln-fix/<cve-id>-<short-sha>` where `<short-sha>` is the abbreviated HEAD SHA at remediate time. Refuse dirty working tree (`WorkingTreeNotClean`). Refuse existing branch (`BranchExists`). No `git push`. `git -c core.hooksPath=/dev/null -c commit.gpgsign=false`. Bot committer identity. `[S+B converge]`
13. **CVE feed integrity** (synth of all three feeds):
    - All snapshots stored content-addressed: `.codegenie/cve/snapshots/<source>/<sha256>.json.gz`. Cache key includes content hash. **Hash-mismatch on read = hard fail.** `[P+S]`
    - Signature verification where supported (NVD `.meta` GPG, GHSA `web-flow` commit signatures) is **best-effort and recorded as a confidence input**, not a gate. Phase 16 hardens to gated. `[synth — softens S per critic §security §"hidden assumption #1"]`
    - `codegenie cve sync` is the only network-touching CLI surface in Phase 3 (matches B); cron-style fetching is deferred to Phase 14 (matches B). `[B]`
    - Snapshot staleness emitted as an **advisory on every `remediate` invocation** (warning if any source > 7 days; degrades confidence at 30 days; refuses at 90 days unless `--allow-stale-feeds`). `[synth — closes critic's "agree-but-questionable" CVE-feed staleness gap and prepares for Phase 14]`
14. **CVE retraction:** new `CveRetractionProbe` (in `src/codegenie/transforms/cve/`). On every `cve sync`, diff the new snapshot against the prior one for any record whose `withdrawn` field flipped on. For any prior remediation referencing a withdrawn CVE, mark the run's `evidence_stale: true` in its audit record. **This is a Phase 3 deliverable**, picked up because all three designs missed it (critic §"shared blind spots #3"). `[synth — addition]`
15. **Audit chain extension.** Phase 2's BLAKE3-chained JSONL audit log gains Phase 3 event types: `cve.feed.synced`, `cve.feed.signature_check`, `cve.retraction.detected`, `recipe.selected`, `recipe.engine.invoked`, `transform.applied`, `lockfile.scanned`, `npm.install.run`, `tests.executed`, `gate.failed`, `evidence_stale.marked`, `branch.created`. **Cache hits replay the original event chain** (the original BLAKE3 hash is included in the cache key; serving from cache re-emits a `cache.replay` event referencing the original chain head). `[S+synth — closes critic §performance "audit chain extension" and §"hidden assumption #2"]`
16. **Confidence is the strict-AND of objective signals** per ADR-0008. Signal set (synth of S's list + P's signals): `lockfile.parse_ok`, `lockfile.policy_violation_count == 0`, `recipe.engine.exit_status == 0`, `npm.install.exit_status == 0`, `npm.install.disallowed_egress_bytes == 0`, `tests.exit_status == 0`, `tests.duration_vs_baseline_pct ≤ 200`, `cve.delta.direction ≤ 0`, `patch.git_apply_dryrun_ok`. Any false → `confidence: low`. `[S]`

### Retry & escalation

17. **No retry inside the Phase 3 orchestrator.** The three-retry default (ADR-0014) is **Phase 5's gate machinery** wrapped around the orchestrator. The single exception: the lockfile resolver retries `npm install --package-lock-only` up to 3 times on `transient_npm_codes` (network, ETIMEDOUT, EAI_AGAIN) — but this is **transient I/O retry inside one subprocess wrapper**, not policy retry. `[B-shape, P-narrow exception, synth — closes critic §performance.3 and §security.5: neither security's parameter-sweep nor performance's broader retry is correct; Phase 4 wraps with planner-driven retry; Phase 5 wraps with gate retry]`
18. **Linear sync orchestrator** (`transforms/coordinator.py`). Six function calls. No async, no LangGraph, no Temporal. Phase 6 wraps; Phase 9 wraps. Function signatures + `RemediationReport` schema are the contract those phases preserve. `[B]`

### Determinism

19. **Byte-deterministic diff.** The transform writes `package.json` + lockfile through a pinned `npm` digest (in `tools/digests.yaml`) and runs `git format-patch -1 --stdout` to capture the patch. A canary test runs the transform 5× and asserts byte-identical diffs and branch trees. **`npm install` is invoked with `--no-audit --no-fund` and `LC_ALL=C` to suppress non-deterministic output ordering; the resulting lockfile is passed through `npm-lockfile-canonicalize` (a small synth helper that sorts top-level keys and normalizes line endings to LF)**. `[synth — closes critic-flagged blind spot "manifest write-back deterministic ordering"]`
20. **Test fixtures.** Each fixture is a `.bundle` file **plus a recorded `npm-resolution.json`** capturing the exact lockfile-resolution result on bundle-creation day. The test runs `ncu` + `npm install --package-lock-only` against a **pinned local registry mirror** (`tests/fixtures/npm-mirror/` — a tarball-stub directory, ~5 MB total, lazy-loaded). Goldens assert the diff against the recorded resolution. This makes tests deterministic against npm registry drift (closes critic §best-practices.5). `[synth — departs from B's bundle-only approach]`

---

## Architecture

```
                              codegenie remediate <repo> --cve <id>
                                              │
                                              ▼
                          ┌──────────────────────────────────────┐
                          │  Phase 0 CLI entry (click)            │   [B]
                          │  + tool-readiness: git, npm, ncu      │
                          │  + optional: java (only if            │
                          │    --engine=openrewrite)              │
                          └──────────────────┬───────────────────┘
                                             │
                                             ▼
              ┌──────────────────────────────────────────────────────────┐
              │  Stage 1: Load context                                    │  [B]
              │   - read .codegenie/context/repo-context.yaml             │
              │   - validate schema; check IndexHealth confidence ≥ med   │
              │   - `--auto-gather` (default) re-runs Phase 0/1/2         │
              │     gather in-process on staleness; else fail loud        │
              └──────────────────┬───────────────────────────────────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────────────────────────────┐
              │  Stage 2: Resolve Advisory                                │  [B+S+synth]
              │   - cve.store.get(cve_id) reads pinned snapshot           │
              │   - snapshot-staleness check (warn>7d / low conf>30d /    │
              │     refuse>90d unless --allow-stale-feeds)                │
              │   - CveRetractionProbe on prior remediations              │
              └──────────────────┬───────────────────────────────────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────────────────────────────┐
              │  Stage 3: Select Recipe → Plan                            │  [B+P]
              │   - recipes.selector.select(repo_ctx, advisory, skills)   │
              │   - returns RecipeSelection (recipe | reason)             │
              │   - on reason=catalog_miss → exit 4 cleanly (Phase 4      │
              │     wraps with RAG/LLM)                                   │
              │   - FixPlan groups multiple CVEs per package (one bump)   │
              └──────────────────┬───────────────────────────────────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────────────────────────────┐
              │  Stage 4: Lockfile policy scan (pre-transform)            │  [S]
              │   - LockfilePolicyScanner reads lockfile                  │
              │   - emits violations (registry-redirect, missing          │
              │     integrity, hostile scripts/overrides/resolutions)     │
              │   - on violations + no --allow-policy-violations →        │
              │     exit 7 with escalation.policy_violation event         │
              └──────────────────┬───────────────────────────────────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────────────────────────────┐
              │  Stage 5: Apply Transform on worktree                     │  [B+P+synth]
              │   - git worktree add → .codegenie/remediation/<run-id>/   │
              │   - NpmPackageUpgradeTransform.run(input)                 │
              │      RecipeEngine.apply(recipe, worktree, ctx) →          │
              │        Ncu | OpenRewriteStub  (engine ABC)                │
              │      LockfileResolver.run(worktree)                       │
              │        = npm install --package-lock-only --ignore-scripts │
              │          --no-audit --no-fund                             │
              │        with bounded retry on transient_npm_codes (3x)     │
              │        cache key includes npm minor-digest + registry-    │
              │        mirror digest + content hashes; cache hit replays  │
              │   - canonicalize lockfile (LC_ALL=C, key sort, LF)        │
              │   - git format-patch -1 --stdout → diff/<recipe-id>.patch │
              └──────────────────┬───────────────────────────────────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────────────────────────────┐
              │  Stage 6: Validate                                        │  [synth]
              │   - install_validator: npm ci --ignore-scripts in        │
              │     run_in_sandbox(network="scoped",                      │
              │       allowlist=["registry.npmjs.org"])                   │
              │   - test_validator: npm test in run_in_sandbox(           │
              │       test_execution=True, network="none")                │
              │     · single profile + overlay flag (NOT a new sandbox)   │
              │     · on "needs network" failure signature →              │
              │       emit confidence=medium + requires_network=true →    │
              │       gate.signal_escalate (HUMAN, not auto-allow)        │
              │   - build_validator (opt-in if scripts.build present)     │
              │   - all three emit ValidatorOutput                        │
              └──────────────────┬───────────────────────────────────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────────────────────────────┐
              │  Stage 7: Trust score + handoff                           │  [S+B]
              │   - TrustScorer.score(signals): strict-AND                │
              │   - PatchBranchWriter:                                    │
              │     · refuses dirty tree, refuses existing branch         │
              │     · git -c core.hooksPath=/dev/null commit.gpgsign=false│
              │     · writes .codegenie/remediation/<run-id>/             │
              │       ├── remediation-report.yaml                         │
              │       ├── diff/<recipe-id>.patch                          │
              │       ├── raw/{ncu.json, install.log, test.xml, ...}      │
              │       └── audit/<run-id>.jsonl (BLAKE3-chained, appends   │
              │           to Phase 2 chain)                               │
              │   - exit codes: 0=success, 4=no_recipe, 5=transform_fail, │
              │     6=validation_fail, 7=policy_violation,                │
              │     8=signal_escalate                                     │
              └──────────────────────────────────────────────────────────┘

  Package layout (synth):
  src/codegenie/transforms/
    contract.py            ← Transform ABC, TransformInput, TransformOutput  [B]
    registry.py            ← @register_transform decorator
    coordinator.py         ← linear sync orchestrator
    context.py             ← RepoContextView (read-only)
    npm_package_upgrade.py ← THE Phase 3 transform
    cve/                   ← (was its own package in B; folded in per critic.B.3)
      models.py            ← Advisory, AffectedRange, Provenance
      feeds/{nvd,ghsa,osv}.py
      store.py
      retraction_probe.py  ← CveRetractionProbe (synth-added)
    validation/            ← (was its own package in B; folded in)
      install.py           ← npm ci validator
      test.py              ← npm test validator (single sandbox, overlay)
      build.py             ← opt-in build validator
      trust_score.py       ← strict-AND scorer
      lockfile_policy.py   ← LockfilePolicyScanner (was S's separate component)

  src/codegenie/recipes/
    engine.py              ← RecipeEngine ABC + Ncu + OpenRewriteStub
    selector.py            ← selection logic
    selector.yaml          ← (data) decision table
    models.py              ← Recipe, RecipeApplication, RecipeSelection
    catalog/npm/*.yaml     ← recipe definitions (data)
```

---

## Components

### 1. `Transform` ABC + registry

- **Provenance:** `[B]`
- **Purpose:** Define the contract every transform satisfies. Modeled byte-for-byte on `Probe` ABC v0.1.0.
- **Interface:** `TransformInput(repo_root, worktree_root, branch_name, advisory, recipe, repo_context_path, run_id)` → `TransformOutput(name, diff_path, branch_name, files_changed, confidence, warnings, errors, skipped)`. No `success` field — validators emit `passed`. `[B's "facts not judgments" application]`
- **Internal design:** Pydantic models at boundary. `@register_transform` decorator mirrors `@register_probe`. Phase 0 fence excludes `anthropic`, `langgraph`, etc. from `transforms/`.
- **Why this choice over alternatives:** Performance-first proposed no top-level ABC (just a recipe registry of YAML). Critic flagged this is exactly the contract Phase 4/5/7/15 must extend. Security-first introduced `RecipeRegistry`/`RecipeExecutor` without a Transform top-line. Best-practices got the shape right.
- **Tradeoffs accepted:** Slightly heavier than performance-first; the contract is what enables additivity.

### 2. `RecipeEngine` ABC with two impls

- **Provenance:** `[synth — direct response to critic's "recipe-engine pick" arbitration point]`
- **Purpose:** Engines are *how* a recipe is applied. The contract makes Phase 7 (Dockerfile rewrites) and Phase 15 (agent-authored recipes) extensible by addition.
- **Interface:** `RecipeEngine.apply(recipe: Recipe, repo: Path, ctx: ApplyContext) -> RecipeApplication(diff: bytes, files_changed, engine_stdout, engine_stderr, exit_code)`. Engines are stateless given their context.
- **Implementations shipped:**
  - **`NcuRecipeEngine`** — default for all `(ecosystem=npm, kind=version_bump)` recipes. Calls `ncu --packageFile package.json --upgrade --target patch --filter <pkg>` then defers lockfile generation to the `LockfileResolver`. On PATH check at startup.
  - **`OpenRewriteEngineStub`** — registered; ships with **one** recipe (`org.openrewrite.npm.UpgradeDependencyVersion`-shaped smoke test); requires `java` + a pinned `tools/openrewrite/<digest>.jar`. **Opt-in via `--engine=openrewrite`.** If `java` or the jar is missing, the engine is registered-but-unavailable; the selector emits `RecipeSelection(reason="no_engine")` rather than failing the run. Phase 15's recipe-authoring target is OpenRewrite-shaped recipes; this stub anchors the contract.
- **Why this choice over alternatives:** Performance-first dropped recipes entirely (raw JSON mutation). Critic: that defeats Phase 15. Best-practices shipped only `ncu`. Critic: roadmap names OpenRewrite first. Security-first shipped OpenRewrite with an unspecified Maven-mirror ceremony. Critic: ceremony custody undocumented. **Synth response: ship both engines, default to ncu for throughput and developer ergonomics, keep OpenRewrite as a registered second seat with a smoke test so the contract is proven to extend.** The Maven mirror is deferred — the OpenRewrite stub is a single-recipe JVM invocation against the pinned jar, no Maven resolution at runtime.
- **Tradeoffs accepted:** OpenRewrite coverage is intentionally narrow in v0.3.0 (one recipe). The point is the contract, not the catalog. Phase 4–7 expand it.

### 3. `recipes` selector + catalog

- **Provenance:** `[B + synth-richer-return-type]`
- **Purpose:** Map `(advisory, repo_context, skills)` to a `Recipe` or a structured no-match reason.
- **Interface:** `select(...) -> RecipeSelection(recipe: Recipe | None, reason, diagnostics: dict)`. The `reason` enum is the public contract Phase 4 reads. Performance-first's "skipped: no_recipe" was binary; this is the structured version critic §"best-practices hidden assumption #1" demanded.
- **Internal design:** Loads YAML recipes from `catalog/npm/*.yaml`; loads `selector.yaml` decision table; consumes Phase 2 Skills loader (with additive `applies_to.cve_patterns` field — same as B). Plain Python `match/case` for the operator dispatch. **No DSL.** Engine availability is part of the match: a recipe whose `engine: openrewrite` is unselectable if java is missing — produces `reason="no_engine"`.
- **Why this choice over alternatives:** Same as B; richer return type closes the diagnostic-signal gap.

### 4. `NpmPackageUpgradeTransform`

- **Provenance:** `[B + P-cost discipline]`
- **Purpose:** The Phase 3 transform. Applies a recipe on a worktree, generates a deterministic diff.
- **Interface:** standard `Transform`. `applies_to_tasks=["vuln_remediation"]`, `applies_to_languages=["javascript","typescript"]`.
- **Internal design:**
  - `git worktree add` into `.codegenie/remediation/<run-id>/worktree`.
  - Engine.apply (ncu or openrewrite-stub) → mutates `package.json`.
  - `LockfileResolver.run` → `npm install --package-lock-only --ignore-scripts --no-audit --no-fund` inside `run_in_sandbox(network="scoped", allowlist=["registry.npmjs.org"])`. Bounded transient-error retry (≤3, network/timeout codes only). **Cache key includes `(blake3(package.json), blake3(package-lock.json), npm_minor_digest, registry_mirror_digest)`** — performance-first's key, with patch-version dropped per P's open question #6 to avoid stampedes.
  - Lockfile canonicalization (LC_ALL=C, top-level key sort, LF endings) before commit — synth-added to close critic's "manifest write-back" gap.
  - `git -c core.hooksPath=/dev/null -c commit.gpgsign=false -c user.email=<bot> -c user.name=codegenie-bot` for commit; `git format-patch -1 --stdout` for the patch.
- **Why this choice over alternatives:** Performance-first's `--package-lock-only` on the diff path is the right primitive (critic challenged but the design's response is correct: validation re-runs `npm ci` so the paper-lock is verified before exit). Worktree (not user working tree) is converged best-practice. The canonicalization step is new because *all three* implicitly assumed `npm` produces consistent output (critic §"manifest write-back").
- **Tradeoffs accepted:** Some flake risk if upstream `npm` minor-version output changes mid-portfolio — mitigated by pinning `npm` digest in `tools/digests.yaml` and a per-bump canary test.

### 5. `LockfileResolver`

- **Provenance:** `[P-engine, S-sandbox]`
- **Purpose:** Generate `package-lock.json` for the bumped `package.json` deterministically. Cache aggressively.
- **Interface:** `(repo_path, package_json_post) -> (new_lockfile_bytes, lockfile_diff, cache_hit: bool)`.
- **Internal design:** Performance-first's design verbatim, with two changes — (a) sandbox network=`"scoped"` allowlist `registry.npmjs.org` only (matches S); (b) cache hit re-emits a `cache.replay` audit event referencing the original chain head (closes critic §performance "audit chain extension").
- **Why this choice over alternatives:** The only design that addresses the cost target. The "paper lockfile" critique is correct in principle but absorbed by Stage 6's `npm ci` validator — we never ship a diff that hasn't survived an actual `npm ci` in the same run.
- **Tradeoffs accepted:** Cache-key drift on npm minor-version upgrades invalidates the cache portfolio-wide; documented; pre-warmed during the npm-version bump PR's CI run.

### 6. `LockfilePolicyScanner` (validation helper)

- **Provenance:** `[S, synth-softened]`
- **Purpose:** Reject lockfiles with disallowed structural patterns before install.
- **Interface:** `scan(lockfile_path, *, allowed_registries) -> LockfileScanResult(violations)`. Violations are typed: `RegistryRedirect`, `MissingIntegrity`, `LifecycleScriptDeclared`, `PublishConfigOverride`, `ResolutionsRedirect`.
- **Internal design:** Pure Python. Reads lockfile JSON/YAML with hard size caps (≤ 50 MB).
- **Why this choice over alternatives:** Critic §security.2 flagged that S's hard-non-retryable + no-escape-valve fails legitimate repos. **Synth resolution:** violations are still emitted, but the orchestrator's response is graded:
  - Default: violations → `confidence: low`, exit 7 with `escalation.policy_violation` audit event.
  - `--allow-policy-violations=<list-of-violation-types>` flag: operator can opt in to specific known-legitimate cases (e.g., GitHub-tarball deps under a known org).
  - Phase 5 will wrap this with three-retry widening logic per critic recommendation.
- **Tradeoffs accepted:** Legitimate corporate registries that override `publishConfig.registry` will require operator opt-in for the first run. Documented loudly.

### 7. Validation gate (single sandbox + overlay)

- **Provenance:** `[synth — departs from all three]`
- **Purpose:** Verify the diff installs cleanly, tests pass, and (opt-in) builds.
- **Internal design:**
  - **One sandbox profile** (Phase 1/2's `run_in_sandbox`), parameterized with `test_execution: bool`. When True: writable overlay over `/work`, larger PID/wall budgets, `--ignore-scripts` is OFF (the test command runs scripts by definition), `--network=none` by default.
  - Validators are plain functions returning `ValidatorOutput(name, passed, stdout_path, stderr_path, duration_ms, confidence, warnings, errors)`.
  - `install_validator`: `npm ci --ignore-scripts --no-audit --no-fund`, `network="scoped"` to `registry.npmjs.org`.
  - `test_validator`: `npm test`, `network="none"`. On non-zero exit, inspects stderr for known "needs network" signatures (`ENOTFOUND`, `ECONNREFUSED`, `getaddrinfo`, common DB-client error strings). Match → emit `requires_network: true` + `confidence: medium` + audit event `gate.signal_escalate` (does not auto-allow egress). Operator can then re-run with `--allow-test-network` after review.
  - `build_validator`: opt-in via `package.json#scripts.build`. Same sandbox.
- **Why this choice over alternatives:** Performance-first's fast-path test selection is unsafe at the exit criterion (critic §performance.4 — depgraph-reverse-reachability misses dynamic loads); synth runs the **whole `npm test`** as best-practices does. Security-first's two profiles + HARD `--network=none` breaks real Node test suites and routes to nonexistent humans (critic §security.4). **Synth response: one profile, overlay flag, network-none default with explicit escalation signal**, per critic recommendation verbatim.
- **Tradeoffs accepted:** Slower than performance-first's fast-path (worth it for correctness). More permissive than security-first's HARD profile (worth it for usability; the escalation signal preserves operator control).

### 8. `CveFeedSyncer` + `cve.store`

- **Provenance:** `[B + S-integrity + synth-soften]`
- **Purpose:** Read CVE feeds out-of-band; store content-addressed pinned snapshots; serve advisories to the orchestrator.
- **Interface:** `codegenie cve sync --source {nvd,ghsa,osv} [--since DATE]`; `cve.store.get(cve_id) -> Advisory`.
- **Internal design:** B's structure. Adds: content-addressed storage with hash verification on read (P, S); best-effort signature check (S, softened — recorded as confidence input, not gate); staleness advisory (synth — warns/degrades/refuses at 7/30/90 days).
- **Why this choice over alternatives:** B's manual sync is the right Phase 3 shape (Phase 14 automates). Security-first's signed-snapshot HARD gate is brittle (NIST/GitHub key rotations break the system; critic §security "hidden assumption #1"). Performance-first's cron is out of scope per critic §performance.3. **Synth: B-shape + content-hash gate + signature-best-effort + staleness advisory.**
- **Tradeoffs accepted:** A truly fresh CVE published 30 min ago won't be remediable until operator runs sync. Phase 14 closes this with webhook ingestion.

### 9. `CveRetractionProbe` (new)

- **Provenance:** `[synth — addresses critic §"shared blind spots #3"]`
- **Purpose:** Detect CVEs that have been withdrawn since a prior remediation referenced them.
- **Interface:** Runs as part of `codegenie cve sync`. Diffs new snapshot against prior; for any record whose `withdrawn` flips from false to true, finds prior remediation runs referencing it (under `.codegenie/remediation/*/audit/*.jsonl`) and writes `evidence_stale: true` to their audit chain.
- **Why this choice over alternatives:** All three designs missed this. Including it in v0.3.0 prevents silent reliance on retracted CVE data.

### 10. Linear sync orchestrator

- **Provenance:** `[B]`
- **Purpose:** Run the seven stages in order.
- **Interface:** `remediate(repo_root, cve_id, *, run_id, config) -> RemediationReport`. Phase 6 wraps with a LangGraph state machine *that does not change this signature*. Phase 9 wraps that with Temporal Activities.
- **Internal design:** Six function calls in sequence. Stage transitions emit typed audit events. Failures preserve worktree + branch on disk; exit codes documented.

### 11. CLI surface

- **Provenance:** `[B]`
- **Subcommands:** `codegenie remediate <repo> --cve <id> [--engine {ncu,openrewrite}] [--allow-policy-violations <types>] [--allow-test-network] [--allow-stale-feeds] [--strict] [--auto-gather|--no-auto-gather]`, `codegenie cve sync --source {nvd,ghsa,osv|all} [--since DATE]`, `codegenie recipes list [--engine X] [--task vuln_remediation]`.
- **Why this choice over alternatives:** Same shape as B. Two new flags (`--allow-policy-violations`, `--allow-test-network`) exist to make the synth's gate-softening operationally honest — escalations are explicit operator choices, not silent allowances.

---

## Data flow

End-to-end run for `codegenie remediate ./services/auth --cve CVE-2024-FAKE-NPM`:

1. **CLI entry** — tool readiness (`git`, `npm`, `ncu`; `java` optional). Click validates `--cve` against regex.
2. **Load context** — mmap `repo-context.yaml`; validate schema; check `IndexHealthProbe.confidence ≥ medium` (else fail loud / auto-gather if `--auto-gather`).
3. **Resolve advisory** — `cve.store.get("CVE-2024-FAKE-NPM")` → `Advisory`. Staleness check.
4. **Select recipe** — `selector.select(...)` → `RecipeSelection(recipe=…, reason="matched")`. On `reason ∈ {catalog_miss, no_engine, range_break, peer_dep_conflict, unsupported_dialect}` → exit 4 with structured `TransformOutput(skipped=True, errors=[reason])` (Phase 4 reads this).
5. **Lockfile policy scan** — `LockfilePolicyScanner.scan(...)` → on violations + no `--allow-policy-violations` → exit 7.
6. **Apply transform** — git worktree add; `RecipeEngine.apply` (NcuRecipeEngine for the common case); `LockfileResolver.run` (cache hit ≈ 5 ms, cold ≈ 2–10 s); canonicalize lockfile; commit; format-patch.
7. **Validate** — install, test, build (opt-in). On test failure with network signature → exit 8 (`signal_escalate`).
8. **Trust score** — strict-AND. If green: `PatchBranchWriter` finalizes branch; if not: status `failed`, worktree preserved.
9. **Write artifacts** — `.codegenie/remediation/<run-id>/{remediation-report.yaml, diff/*.patch, raw/*, audit/*.jsonl}`. Audit chain extends Phase 2's.
10. **Exit 0** on success.

---

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery | Source |
|---|---|---|---|---|
| CVE not in advisory store | `cve.store.get` returns None | Hard fail `AdvisoryNotInStore` | Operator runs `codegenie cve sync` | [B] |
| Feed snapshot hash mismatch on read | content-hash check | Refuse read; emit `cve.feed.corrupt` | Operator re-syncs | [P+S] |
| Feed signature check failed (best-effort) | GPG verify | Warning in audit; confidence input degraded | Operator inspects | [synth] |
| Snapshot > 90 days stale | sync metadata | Refuse `remediate` unless `--allow-stale-feeds` | Operator syncs | [synth] |
| CVE retracted since prior remediation | `CveRetractionProbe` | Marks `evidence_stale: true` on prior run audit chain | Phase 4+ reads, plans accordingly | [synth] |
| Selector finds no recipe | `select()` returns `reason ∈ {catalog_miss,...}` | Exit 4; structured TransformOutput | Phase 4 wraps with RAG/LLM | [B+synth] |
| Engine missing on PATH (java for openrewrite) | startup check + selector | `reason="no_engine"` → exit 4 | Operator installs engine or uses ncu | [synth] |
| `ncu` refuses (peer-dep conflict) | engine exit non-zero | `confidence=low`, `errors=["peer_dep_conflict"]` | Phase 4 LLM fallback | [B] |
| Lockfile policy violation | `LockfilePolicyScanner` | Exit 7 unless `--allow-policy-violations` | Operator reviews / Phase 5 widening | [S+synth] |
| `npm install` transient network error | `LockfileResolver` exit codes | Retry ≤ 3 on transient_npm_codes | Self-heals or fails fast | [P] |
| `npm install --package-lock-only` non-transient fail | resolver | Fail fast with captured exit code | Operator inspects raw/install.log | [P] |
| `npm ci` (install validator) fails | validator | `passed=False`; branch preserved; status=failed | Operator inspects | [B] |
| Test suite fails | test validator | `passed=False`; status=failed; branch preserved | Operator / Phase 4 retry | [B] |
| Test suite fails with network-required signature | test validator stderr scan | `requires_network=true`; exit 8 `gate.signal_escalate` | Operator reviews; re-runs `--allow-test-network` | [synth] |
| `--ignore-scripts` flag missing on install call | `NpmRunner` wrapper guard | Raises `NpmScriptsEnabled` | Bug in PR; CI red | [S] |
| `git apply` outside repo | `--ro-bind` worktree | Sandbox refuses | N/A | [S] |
| `.git/hooks/pre-commit` shell | `core.hooksPath=/dev/null` always | Never executes | N/A | [S] |
| User signing key leak | `commit.gpgsign=false` always | No signing attempted | N/A | [S] |
| Dirty working tree | PatchBranchWriter check | `WorkingTreeNotClean`; abort | Operator stashes | [S+B] |
| Branch name collision | `git rev-parse --verify` | `BranchExists`; abort | Operator deletes / rotates `--run-id` | [B] |
| Cache poisoning (lockfile cache wrong) | content-hash + validation oracle | Validation fails; cache entry refreshed | Re-run | [P] |
| Worktree already exists | precondition check | Hard fail; operator chooses | Manual cleanup | [B] |
| Audit log tampering | BLAKE3 chain break | Chain emits `meta.chain_break`; loud | Forensic | [S] |
| Disk fills up | per-tmpfs cap | `enospc`; orchestrator fails gracefully | Operator GC `.codegenie/` | [P+S] |

---

## Resource & cost profile

- **Tokens per run: 0.** Fence CI extended to new packages. `[P,S,B]`
- **Wall-clock (single-worker M-series Mac, ~1k-file Node fixture):**
  - Hot path: p50 ≤ 30 s / p95 ≤ 90 s (includes a small test suite).
  - Cold lockfile + full suite: p50 ≤ 120 s / p95 ≤ 240 s.
- **Per-worker memory:** Python process ≤ 350 MB; npm/test subprocess capped at 4 GB (test profile) / 900 MB (non-test).
- **Disk:** `.codegenie/cve/` ≤ 200 MB; `.codegenie/cache/lockfile/` ≤ 2 GB across portfolio; `.codegenie/remediation/<run-id>/` ≤ 20 MB typical.
- **Network:** zero outbound from `codegenie` process except (a) `codegenie cve sync` (manual operator), (b) `npm install` inside scoped sandbox.
- **New `ALLOWED_BINARIES` entries (one ADR each):** `npm`, `ncu`, `java` (opt-in). `git` was added in earlier phases.
- **OpenRewrite Maven mirror:** **NOT introduced** in Phase 3. The OpenRewrite stub engine uses a self-contained pinned jar with one recipe; full Maven resolution is deferred to a future phase that needs it.

---

## Test plan

### Unit tests (`tests/unit/`)

- Per CVE-feed parser (3 modules) × ≥ 6 tests each.
- `Advisory.merge`: ≥ 8 tests (commutative, idempotent, dedup, severity tie-break).
- `selector.select`: ≥ 14 tests (one per `reason` enum × matched/unmatched paths; engine-availability filter).
- `RecipeEngine` ABC: registry tests; engine selection; `OpenRewriteEngineStub` when java missing → unavailable.
- `NpmPackageUpgradeTransform`: ≥ 10 tests including lockfile-canonicalization golden.
- `LockfileResolver`: cache key derivation; transient retry; replay event on cache hit.
- `LockfilePolicyScanner`: one test per violation type + `--allow-policy-violations` flag path.
- Validators (install/test/build): ≥ 4 tests each; network-signature scan; escalation event.
- `TrustScorer`: strict-AND property test.
- `coordinator.remediate`: full happy + each exit code path.

### Integration tests (`tests/integration/`)

- `test_remediate_express_e2e.py` — express fixture, ncu engine.
- `test_remediate_openrewrite_stub_e2e.py` — single recipe via OpenRewriteEngineStub (only runs in CI matrix with `java` available; otherwise skip with reason).
- `test_remediate_pnpm_workspace.py`.
- `test_remediate_yarn_classic.py`.
- `test_remediate_no_recipe_clean_skip.py`.
- `test_remediate_install_fails.py`.
- `test_remediate_test_needs_network_escalates.py` — fixture test imports `pg`; orchestrator emits `signal_escalate`.
- `test_remediate_lockfile_policy_violation_blocked.py`.
- `test_remediate_lockfile_policy_violation_allowed.py` — same fixture + `--allow-policy-violations RegistryRedirect`.
- `test_cve_retraction_marks_evidence_stale.py`.
- `test_phase2_unchanged.py` — re-runs every Phase 2 integration test verbatim.

### Adversarial tests (`tests/adv/`)

- All of S's `--ignore-scripts`, lockfile-policy, test-execution-isolation, OpenRewrite-stub-isolation, git-hooks-disabled, signing-key absent, branch refusals, audit chain integrity, no-credentials-in-sandbox, fence-job tests. **Target ≥ 30 fixtures** (synth-relaxed from S's ≥ 40 to keep the corpus maintainable while preserving coverage; the missing ten are about TestSandboxProfile-only behaviors that don't exist in the single-profile design).

### Determinism canary

- `test_byte_identical_diff_5x.py` — run remediate 5× on the same fixture; assert byte-identical diffs and branch SHAs.

### Performance canary

- `test_hot_path_latency.py` — caches warm; assert p95 ≤ 30 s (excluding test suite execution).
- `test_lockfile_cache_hit_rate.py` — across the fixture portfolio, assert ≥ 70% lockfile cache hits.

### Golden-file tests

- Every recipe ships a golden diff at `tests/golden/transforms/<recipe-id>/<fixture>/expected.patch`.
- Every `Advisory` ships goldens for the three feed parsers under `tests/golden/cve/`.
- Test fixtures use `.bundle` + recorded `npm-resolution.json` + a tiny pinned local registry mirror — closes critic §best-practices.5.

### Property tests

- `test_selector_is_total.py` — Hypothesis: any `(advisory, repo_ctx, skills)` returns `RecipeSelection` without raising.
- `test_advisory_merge_commutative.py` and `_idempotent.py`.
- `test_trust_score_strict_and.py`.
- `test_audit_event_schema_validates_or_drops.py`.

### Contract snapshot

- `test_transform_contract.py` mirrors Phase 0's `test_probe_contract.py`. Signature drift → CI red.

---

## Risks (top 5)

1. **`Transform` ABC v0.3.0 is the most consequential review in the phase.** Phase 4/5/7/15 inherit it. **Mitigation:** review against four future-phase use cases (Phase 4 wraps selector; Phase 5 wraps coordinator with three-retry; Phase 7 adds `DockerfileBaseImageSwapTransform`; Phase 15 emits agent-authored recipes); snapshot test freezes signature; signature drift → CI red.
2. **`npm install --package-lock-only` is the diff-generation primitive and is not perfectly deterministic across npm versions.** **Mitigation:** pin npm digest in `tools/digests.yaml`; cache key includes npm minor-version; canonicalize lockfile output (LC_ALL=C + key sort + LF). **Residual:** npm minor bumps trigger portfolio-wide cache rebuild — pre-warm on bump PR.
3. **`LockfilePolicyScanner` may block legitimate enterprise repos.** Critic-flagged. **Mitigation:** `--allow-policy-violations <types>` opt-in flag; Phase 5 wraps with widening; document common legitimate cases (GitHub-tarball deps, `publishConfig.registry` for private publishing).
4. **OpenRewrite stub is a contract anchor with very narrow coverage.** **Mitigation:** explicit in the design — Phase 3 is one recipe; Phase 4/7 expand. The stub exists so Phase 15 has a target to author into and Phase 7 has a contract to extend.
5. **CVE feed staleness silently produces wrong bumps.** **Mitigation:** snapshot-staleness advisory (warn>7d / low conf>30d / refuse>90d); `CveRetractionProbe` marks `evidence_stale` on prior remediations; Phase 14 closes with webhook ingestion.

---

## Synthesis ledger

### Vertex count
- P (performance vertices): 38
- S (security vertices): 47
- B (best-practices vertices): 42
- synth-additions: 7
- Total considered: ~134

### Edges
- AGREE: 18 (e.g., `--ignore-scripts` on install, worktree usage, no-push, refuse-dirty-tree)
- CONFLICT: 11 (engine default, sandbox profiles, validation gate, retry semantics, etc.)
- COMPLEMENT: 14 (B's ABC + P's cache + S's audit chain)
- SUBSUME: 5 (B's `validation/` ABC subsumed into S's `LockfilePolicyScanner`)

### Conflict-resolution table

| Dimension | [P] picks | [S] picks | [B] picks | Winner | Exit fit | Roadmap fit | Commit fit | Critic-survivability | Sum |
|---|---|---|---|---|---|---|---|---|---|
| Recipe engine default | stdlib JSON mutation | OpenRewrite + maven-mirror | `ncu` only | **`Ncu` default + `OpenRewriteStub` registered (synth)** | 3 | 3 | 3 | 3 | 12 |
| Top-level Transform ABC | none | `RecipeRegistry` only | `Transform`+`Validator`+`Recipe` | **`Transform` + `RecipeEngine` only (synth-trimmed B)** | 3 | 3 | 3 | 3 | 12 |
| New top-level packages | 0 | 1 (`remediation/`) | 4 | **2 (`transforms/`, `recipes/`); cve/validation fold in** | 2 | 3 | 3 | 3 | 11 |
| Diff-generation install | `--package-lock-only` | `npm ci --ignore-scripts` | `npm install --ignore-scripts` | **`--package-lock-only` for diff; `npm ci` re-validates in Stage 6** | 3 | 3 | 3 | 3 | 12 |
| Validation test gate | fast-path subset | TestSandboxProfile HARD `none` | full `npm test` no sandbox | **Full `npm test` in single sandbox + `none` default + signal-escalate on network** | 3 | 3 | 3 | 3 | 12 |
| Sandbox boundary count | 1 | 2 | 0 new | **1 (Phase 2's chokepoint + `test_execution=True` overlay)** | 3 | 3 | 3 | 3 | 12 |
| CVE feed cadence | 60-min cron | manual signed ceremony | manual `cve sync` | **Manual `cve sync` + content-hash + best-effort signature + staleness advisory** | 3 | 3 | 3 | 3 | 12 |
| Lockfile policy | none | hard-non-retryable | none | **Retryable-with-widening (Phase 5); `--allow-policy-violations` escape valve in P3** | 3 | 3 | 3 | 3 | 12 |
| Three-retry semantics | transient + recipe retry | parameter sweep | defer to Phase 5 | **Defer to Phase 5 (B); transient I/O retry only inside lockfile resolver** | 3 | 3 | 3 | 3 | 12 |
| CVE retraction | unaddressed | unaddressed | unaddressed | **`CveRetractionProbe` (synth-added)** | 3 | 3 | 3 | 3 | 12 |
| Fixture portfolio | golden lockfile diffs | adversarial corpus ≥40 | `.bundle` files | **`.bundle` + recorded `npm-resolution.json` + pinned local registry mirror** | 3 | 3 | 3 | 3 | 12 |
| Branch naming | `codegenie/cve/<ids>-<attempt>` | `codegenie/vuln/<cve>/<digest>` | `codegenie/vuln-fix/<cve>-<sha>` | **`codegenie/vuln-fix/<cve-id>-<short-sha>` (B)** | 3 | 3 | 3 | 3 | 12 |
| Manifest write-back determinism | implicit | implicit | implicit | **Explicit canonicalization (LC_ALL=C, key sort, LF) + `npm` digest pin** | 3 | 3 | 3 | 3 | 12 |
| Audit chain on cache hit | absent | extends Phase 2 chain | per-run-id unchained | **Extend Phase 2 BLAKE3 chain; cache hit emits `cache.replay` referencing original head** | 3 | 3 | 3 | 3 | 12 |
| Worktree pattern | per-attempt parallel | overlay inside sandbox | one worktree, sequential | **One worktree, sequential, refuses dirty tree; worktree inside sandbox for `npm` invocations** | 2 | 3 | 3 | 3 | 11 |

### Shared blind spots considered (per critic §"cross-design")

1. **Running the repo's tests as part of validation = executing attacker code.** All three designs accept this. Phase 5 microVM is the real defense. Synth carries forward this acceptance with the strictest single-profile sandbox we can afford without breaking real test suites.
2. **Reuse of Phase 2's `run_in_sandbox` chokepoint.** All three depend on it. Synth makes this dependency explicit — if Phase 2's bwrap profile cannot host `npm install`, Phase 3 cannot run and that's a Phase 2 bug.
3. **CVE retraction.** All three missed. Synth ships `CveRetractionProbe`.
4. **Manifest write-back determinism.** All three implicitly assumed. Synth ships canonicalization.

### Departures from all three inputs

1. **Ship two recipe engines in v0.3.0.** Critic forced the choice. Neither P nor B keeps OpenRewrite; S keeps it with unspecified ceremony. Synth ships ncu as default + OpenRewrite *stub* (one recipe, no Maven runtime, opt-in). The roadmap's OpenRewrite seat is honored; operational burden is bounded.
2. **`RecipeSelection` is structured, not `Optional[Recipe]`.** B's binary return type fails Phase 4. Synth returns a `(recipe, reason, diagnostics)` triple.
3. **Single sandbox profile + `test_execution=True` overlay flag.** Neither S (two profiles) nor B (zero new sandbox usage) nor P (one profile + scoped network) gets this right. Synth uses one profile with a test-mode overlay AND adds an explicit `signal_escalate` audit event for network-needing tests — per critic recommendation verbatim.
4. **Test fixture portfolio = `.bundle` + `npm-resolution.json` + pinned local registry mirror.** B's pure-bundle approach is registry-drift-brittle (critic §best-practices.5). Synth adds the resolution snapshot + local mirror.
5. **Lockfile canonicalization step.** None of the three named it; critic surfaced it. Synth ships it.
6. **`CveRetractionProbe`.** Synth-added.
7. **Snapshot-staleness graded advisory** (warn / degrade / refuse). Synth-added to soften B's manual-sync brittleness without taking on cron complexity.

---

## Exit-criteria checklist (against roadmap Phase 3)

> "Given a Node.js repo with a known npm CVE, the system writes a working patch diff on a local branch that — when applied — installs cleanly and passes the repo's own tests."

- ✅ **Reads `RepoContext` and Skills.** Stage 1 + Stage 3 selector. Phase 0/1/2 outputs are read-only.
- ✅ **Chooses a recipe.** Stage 3 `selector.select` → `RecipeSelection`.
- ✅ **Applies it.** Stage 5 transform + engine (ncu by default; openrewrite-stub opt-in).
- ✅ **Writes the diff plus a local branch.** Stage 7 `PatchBranchWriter`; branch `codegenie/vuln-fix/<cve-id>-<short-sha>`; diff under `.codegenie/remediation/<run-id>/diff/`.
- ✅ **No LLM in this loop.** Fence CI extended; `transforms/`, `recipes/` may not import LLM SDKs.
- ✅ **Installs cleanly.** Stage 6 install validator (`npm ci --ignore-scripts` in scoped sandbox).
- ✅ **Passes the repo's own tests.** Stage 6 test validator (`npm test` in `--network=none` overlay sandbox). Tests that legitimately need network signal-escalate to human rather than silently fail — operator can opt in.
- ✅ **Single-repo, local, deterministic.** No GitHub API. No `git push`. Linear sync orchestrator. Determinism canary asserts byte-identical diffs over 5 runs.

---

## Load-bearing commitments check (§2 of `production/design.md`)

- **§2.1 No LLM in gather pipeline → extended to transforms.** Fence covers `transforms/`, `recipes/`. ✅
- **§2.2 Facts not judgments.** `TransformOutput` has no `success`; `ValidatorOutput.passed` is per-signal; `RecipeSelection.reason` is structured; `Advisory` carries provenance, not "should remediate." ✅
- **§2.3 Honest confidence.** `confidence ∈ {high,medium,low}` on every Transform + Validator + the strict-AND TrustScorer; staleness signal degrades confidence. ✅
- **§2.4 Determinism over probabilism for structural changes.** Recipes are YAML data; engine ABC enables OpenRewrite-style structural recipes; lockfile canonicalization makes output deterministic; no LLM. ✅
- **§2.5 Extension by addition.** Two new packages; zero edits to Phase 0/1/2 code (one additive ADR-gated change to Phase 2 Skills frontmatter: `applies_to.cve_patterns`); Phase 2 regression suite runs in Phase 3 CI. ✅
- **§2.6 Org uniqueness as data.** Recipes in YAML; selector.yaml decision table; Skills frontmatter. ✅
- **§2.7 Progressive disclosure.** `remediation-report.yaml` indexes; raw outputs under `raw/`. ✅
- **§2.8 Humans always merge.** No `git push`; no GitHub API; Phase 3 stops at local branch + audit + report. ✅
- **§2.9 Cost observability.** Audit log records per-stage wall-clock, RSS, network bytes; zero LLM tokens by construction. ✅

### Tension surfaced explicitly

- **Exit criterion vs. §2.3/§2.8.** "Passes the repo's own tests" is a *judgment* (does the bump work?). The synthesis routes this through objective signals (`tests.exit_status`, `tests.duration_vs_baseline_pct`) and an honest escalation signal when the test environment fundamentally cannot satisfy the gate (network-required tests). This honors §2.3 (honest confidence) at the cost of accepting that some real repos will require operator opt-in for the first run. Critic flagged S's HARD profile for breaking real repos; this design accepts the more permissive default while logging the escalation. **The tension is real and surfaced.**

---

## Roadmap coherence check

### Prior phases this depends on

- **Phase 0** — CLI shell, `pyproject.toml`, fence CI, `exec.run_allowlisted`, audit writer base, tool-readiness check.
- **Phase 1** — Probe ABC pattern (Transform mirrors it), content-addressed cache, `RepoContext` schema, Node Layer A probes.
- **Phase 2** — `run_in_sandbox` chokepoint, Skills loader, `IndexHealthProbe` (B2), grype CVE probe in `RepoContext.cve_scan`, depgraph, conventions catalog. **The synth `test_execution=True` overlay flag is a Phase 2 commitment — if Phase 2's sandbox profile cannot host `npm test` in a writable overlay, Phase 3 needs Phase 2 to amend its design before Phase 3 ships.**

### What later phases need (and how Phase 3 delivers)

- **Phase 4 (LLM fallback + RAG).** Reads `RecipeSelection.reason` to decide RAG/LLM path; reads `TransformOutput.errors` + `ValidatorOutput.errors` for diagnostic context; ingests successful remediation runs as solved examples. Synth delivers structured signals.
- **Phase 5 (Sandbox + Trust gates).** Wraps the linear orchestrator with the three-retry gate machinery. The orchestrator's docstring explicitly states it has no retry of its own (except transient I/O inside lockfile resolver). Phase 5 also wraps `LockfilePolicyScanner` with widening-retry. Synth makes both extensions purely additive.
- **Phase 6 (LangGraph state machine).** Wraps the linear orchestrator without changing its function signature or `RemediationReport` schema. Synth honors.
- **Phase 7 (Chainguard distroless).** Adds `DockerfileBaseImageSwapTransform` + new recipes + new engine (likely OpenRewrite-shaped or a Docker-specific engine). Extends `Transform` ABC and `RecipeEngine` ABC additively. Synth's `RecipeEngine` ABC anchors this.
- **Phase 11 (PR opening).** Adds a `git push` step + GitHub API; Phase 3's local-branch output is the exact input. Synth honors.
- **Phase 14 (Continuous gather + CVE webhook).** Replaces the manual `codegenie cve sync` with webhook-driven sync. The `cve.store` interface and snapshot-staleness logic are forward-compatible. Synth delivers.
- **Phase 15 (Agentic recipe authoring).** Authors new YAML recipes against the catalog + new OpenRewrite recipes against the registered engine. Without the OpenRewrite stub in Phase 3, Phase 15's authoring target is constrained to ncu-parameterizations. **The synth's two-engine choice is the load-bearing decision for Phase 15.**

### New ADRs implied

- **ADR-P3-001** Transform ABC contract frozen at v0.3.0 (mirrors Probe v0.1.0).
- **ADR-P3-002** RecipeEngine ABC with two implementations; OpenRewrite ships as a stub for contract anchoring.
- **ADR-P3-003** Lockfile canonicalization (LC_ALL=C, key sort, LF) + `npm` digest pin for deterministic diff output.
- **ADR-P3-004** `LockfilePolicyScanner` violations are retryable-with-widening at Phase 5; in Phase 3, escape valve is `--allow-policy-violations`.
- **ADR-P3-005** Test execution sandbox: single profile + `test_execution=True` overlay; `--network=none` default + signal-escalate for network-needing tests.
- **ADR-P3-006** `CveRetractionProbe` and `evidence_stale` markers on prior runs.
- **ADR-P3-007** CVE feed integrity: content-hash gate, best-effort signature, graded staleness advisory.
- **ADR-P3-008** Package layout: two new top-level packages (`transforms/`, `recipes/`); `cve/` and `validation/` fold under `transforms/`.
- **ADR-P3-009** ALLOWED_BINARIES additions: `npm`, `ncu`, `java` (opt-in for OpenRewrite stub).
- **ADR-P3-010** Skills schema additive field `applies_to.cve_patterns` (defaults to `["*"]`).

---

## Open questions deferred to implementation

1. **OpenRewrite stub recipe choice.** Which exact recipe ships as the smoke test? Candidate: `org.openrewrite.npm.UpgradeDependencyVersion`-shaped — but the OpenRewrite npm ecosystem is genuinely thin. May need to roll a minimal internal recipe under the same engine contract.
2. **`npm-resolution.json` recording mechanism for fixtures.** Convention TBD: do we record `npm install --json --package-lock-only` output, or a custom canonical extract? Affects test reproducibility.
3. **Network-required test signature scan.** Which exact patterns trigger `requires_network: true`? Initial set: `ENOTFOUND`, `ECONNREFUSED`, `getaddrinfo`, `ETIMEDOUT` + DNS lookups + common ORM connection errors. Tunable.
4. **Snapshot-staleness thresholds.** Defaults are 7/30/90 days; calibrated against operator feedback in Phase 4+.
5. **`OpenRewriteEngineStub` JVM heap + wall-clock budgets.** Initial: `-Xmx2g`, 300 s wall. Tunable in `recipes/openrewrite-stub/config.yaml`.
6. **`tools/digests.yaml` extension format for ncu and openrewrite-jar.** Follow Phase 2 precedent; emit one ADR per binary added.
7. **`evidence_stale` semantics for partial retractions.** When NVD retracts but GHSA retains, what is the run marked? Conservative default: mark stale; record the disagreement.
8. **Test fixture mirror size.** Target ≤ 5 MB; if it grows past 10 MB, switch to git-lfs or lazy-fetch.
