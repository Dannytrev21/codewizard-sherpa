# Story S6-01 — `OpenRewriteEngineStub` + `tools/openrewrite.py` wrapper + jar pin + smoke recipe + isolation adversarial

**Step:** Step 6 — Ship `OpenRewriteEngineStub` (opt-in, JVM-gated, pinned-jar smoke recipe)
**Status:** Ready
**Effort:** L (single bundled delivery: pinned jar + tool wrapper + engine class + smoke recipe YAML + config YAML + CLI plumbing + unit/integration/adversarial tests)
**Depends on:** S5-05 (CLI surface with `--engine` plumbing), S5-01 (`NpmPackageUpgradeTransform.requires_recipe_engines = ["ncu", "openrewrite"]`), S3-06 (`RecipeSelector` + `reason="no_engine"` path), S3-07 (`NcuRecipeEngine` + `EngineRegistry` pattern), S3-04 (`recipes/digests.yaml` pin manifest), S3-03 (`tools/digests.yaml` extension), S1-03 (`RecipeEngine` ABC + `EngineRegistry`), S1-05 (`ALLOWED_BINARIES +java`)
**ADRs honored:** ADR-0003 (two-engine seat, OpenRewrite registered-but-narrow), ADR-0004 (`RecipeSelection` structured triple, `reason="no_engine"`), ADR-0014 (`ALLOWED_BINARIES` extension — `java` opt-in), ADR-0011 (recipe digest pin discipline), ADR-0013 (no-LLM `fence` extends to `recipes/`)

## Context

`OpenRewriteEngineStub` is the **second seat** of the `RecipeEngine` ABC. It is the load-bearing proof that the contract extends — without it, the engine registry is a single-implementation construct that Phase 4/7/15 inherit as a stub-shaped TODO rather than a proven seam (`phase-arch-design.md §"Component design" #2b`, ADR-0003 *Decision* §2). Coverage is intentionally narrow: one pinned self-contained jar, one shipped recipe, one CLI opt-in (`--engine=openrewrite`), one config file. There is **no Maven mirror, no Maven Central reach-through, no signed-manifest ceremony, and no install ceremony** beyond what `tools/digests.yaml` already enforces. If `java` is absent or the jar digest mismatches at startup, the engine registers as **unavailable** and the selector emits `RecipeSelection(reason="no_engine", diagnostics={"engine": "openrewrite", "available": False})` cleanly — the run never raises (ADR-0003 §"Decision" #2; `phase-arch-design.md §"Component design" #2b` *Failure behavior*).

The opt-in discipline matters: the default `ncu` path is unaffected by JVM cold-start cost (2–4 s); the OpenRewrite engine only spins up when an operator explicitly passes `--engine=openrewrite`. The architecture explicitly does **not** auto-select OpenRewrite recipes when both engines are available — that flag is the only opt-in signal (ADR-0003 *Tradeoffs* row 4; `phase-arch-design.md §"Component design" #2b` *Performance envelope*).

This is a single L-effort bundled story because the four deliverables are tightly coupled: the wrapper subprocess invariants (network=none, env-strip, heap/wall bounds) cannot be tested without the engine; the engine `available()` semantics cannot be tested without the wrapper's digest-check seam; the smoke recipe cannot be loaded without `recipes/digests.yaml` carrying its hash; and the adversarial isolation pin tests the **composition** of all three. Splitting would create stub-shaped intermediate stories.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #2 RecipeEngine ABC + two implementations` — both engines' interface, dependencies, performance envelopes, failure behavior.
  - `../phase-arch-design.md §"Component design" #2b OpenRewriteEngineStub` — `available()` semantics, `apply()` invocation shape, JVM heap/wall budgets, opt-in CLI flag, sandbox profile (`network="none"`).
  - `../phase-arch-design.md §"Component design" #3 RecipeSelector` — selector emits `reason="no_engine"` when an OpenRewrite-engine recipe is selected but the engine is unavailable (engine-availability is part of the match).
  - `../phase-arch-design.md §"Goals" #4` — second engine seat goal.
  - `../phase-arch-design.md §"Gap analysis" §"Gap 6 — Engine availability check happens twice"` — `available()` is read once from `RemediationAttempt.engine_availability` snapshot, never re-called at apply-time.
- **Phase ADRs:**
  - `../ADRs/0003-recipe-engine-ncu-default-openrewrite-stub-registered.md` — Decision §2; Tradeoffs; Consequences; Reversibility "Medium".
  - `../ADRs/0004-recipe-selection-structured-triple-not-optional.md` — `RecipeSelection.reason` closed enum; `no_engine` is one of six values.
  - `../ADRs/0014-allowed-binaries-additions-npm-ncu-java.md` — `java` opt-in in `ALLOWED_BINARIES`; digest cache-key discipline.
  - `../ADRs/0011-lockfile-canonicalization-and-npm-digest-pin-for-deterministic-diffs.md` — recipe digest pin discipline (`recipes/digests.yaml`).
- **Production ADRs:**
  - `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — recipe-first invariant Phase 3 anchors; Phase 15 authoring target.
  - `../../../production/design.md §2.4` — recipes-as-data invariant; engine selection is data, engine implementation is code.
- **Source design:**
  - `../final-design.md §"Components" #2` — two-engine commitment; self-contained jar; no Maven mirror.
  - `../final-design.md §"Open questions" #1` — smoke recipe choice (`UpgradeDependencyVersion`-shaped vs minimal internal recipe).
  - `../final-design.md §"Open questions" #5` — JVM heap/wall budgets (`-Xmx2g`, 300 s).
  - `../High-level-impl.md §"Step 6 — Ship OpenRewriteEngineStub"` — features delivered + done criteria.
- **Existing code (consumed):**
  - `src/codegenie/recipes/contract.py` (S1-03) — `RecipeEngine` ABC; snapshot-frozen.
  - `src/codegenie/recipes/registry.py` (S1-03) — `@register_engine` decorator; engines self-register at import.
  - `src/codegenie/recipes/engines/ncu.py` (S3-07) — `NcuRecipeEngine` as the pattern to mirror (same wrapper-call shape; same `available()`/`apply()` interface).
  - `src/codegenie/tools/ncu.py` (S3-02) — wrapper pattern (typed Pydantic return; routes through `exec.run_in_sandbox`).
  - `src/codegenie/exec.py` (S1-05 + S1-06) — `run_in_sandbox(..., network="none", env_strip=ALL_CREDS, profile="default")`; `ALLOWED_BINARIES` includes `java`.
  - `src/codegenie/catalogs/tools/digests.yaml` (Phase 2 S1-08; extended S3-03) — extend here with `openrewrite-jar` entry (per-platform if jar is platform-specific; usually `all: sha256:...` since jars are JVM-portable).
  - `src/codegenie/catalogs/tools/__init__.py` / `digests.py` — `get("openrewrite-jar")` helper.
  - `src/codegenie/recipes/digests.yaml` (S3-04) — extend here with the smoke recipe's content hash.
  - `src/codegenie/recipes/selector.py` (S3-06) — already filters by engine availability; this story is the second engine that exercises that path.
  - `src/codegenie/errors.py` — re-use existing `ToolNotFound`, `ToolDigestMismatch` (Phase 2 S1-08); add no new exceptions.
- **CLI surface:**
  - `src/codegenie/cli/remediate.py` (S5-05) — `--engine={ncu,openrewrite}` flag already wired; this story adds the `java`-readiness check guarded by `--engine=openrewrite` and propagates the engine choice through orchestrator → selector → transform.

## Goal

Ship a registered-but-narrow `OpenRewriteEngineStub` that proves the `RecipeEngine` ABC extends to a second implementation backed by a pinned self-contained JVM jar, gated by `--engine=openrewrite` and (`java` + jar digest) availability, with one smoke-tested recipe and an adversarial test pinning network-none isolation — without touching the default `ncu` hot path.

## Acceptance criteria

- [ ] `src/codegenie/recipes/engines/openrewrite_stub.py` defines `OpenRewriteEngineStub(RecipeEngine)` with `name = "openrewrite"`, registered via `@register_engine` from S1-03; `available() -> bool` returns `False` if `shutil.which("java") is None` OR if the SHA-256 of `tools/openrewrite/<digest>.jar` does not match `tools.digests.get("openrewrite-jar")`; `apply(recipe, worktree, ctx) -> RecipeApplication` delegates to `tools.openrewrite.run(...)`.
- [ ] `src/codegenie/tools/openrewrite.py` ships a typed wrapper: `run(recipe_id: str, worktree: Path, *, heap: str = "2g", wall_seconds: int = 300, run_id: str) -> OpenRewriteResult` (Pydantic) that routes through `exec.run_in_sandbox(network="none", env_strip=ALL_CREDS, profile="default", wall_seconds=...)` and invokes `java -Xmx<heap> -jar tools/openrewrite/<digest>.jar <recipe-id>` with the worktree as the cwd; no direct `subprocess.run` calls; `tool_digest` field populated from `tools.digests.get("openrewrite-jar")`.
- [ ] `tools/openrewrite/<digest>.jar` is committed at `tools/openrewrite/<digest>.jar` (or fetched-and-verified at install time per Phase 2 ADR-0004 precedent; document choice in the catalog's leading comment); `src/codegenie/catalogs/tools/digests.yaml` extends with an `openrewrite-jar` entry (single `sha256:` value — jars are JVM-portable; no per-platform split needed — document this departure from the `linux_amd64`/`darwin_arm64` binary pattern in the schema and a leading comment).
- [ ] `src/codegenie/recipes/catalog/openrewrite-stub/<recipe-id>.yaml` ships one smoke-tested recipe with `engine: openrewrite`, `ecosystem: npm`, `kind: version_bump`, valid `applies_to`, `digest: sha256:...`, and `params` matching the recipe runner's expected schema; final recipe identity per Open Question #1 (`UpgradeDependencyVersion`-shaped if upstream is workable; minimal internal recipe otherwise — document choice in the recipe YAML leading comment and amend ADR-0003 if it deviates from upstream).
- [ ] `src/codegenie/recipes/catalog/openrewrite-stub/config.yaml` ships JVM heap + wall-clock config (`heap: "2g"`, `wall_seconds: 300`) — tunable; loaded by the wrapper at startup.
- [ ] `src/codegenie/recipes/digests.yaml` (from S3-04) extends with the smoke recipe's content hash; load-time hash verification refuses unpinned recipes (`RecipeNotInDigestManifest`).
- [ ] `src/codegenie/cli/remediate.py` tool-readiness extends: if `--engine=openrewrite`, fail-loud at startup when `java` is absent or jar digest mismatches (exit code 4 `no_recipe` with `RecipeSelection(reason="no_engine")` propagation — **NOT** a non-zero pre-check exit; the orchestrator must reach the selector and emit the structured reason; the CLI banner explains the cause).
- [ ] Engine availability is captured **once** at orchestrator entry into `RemediationAttempt.engine_availability` (`phase-arch-design.md §"Gap analysis" §Gap 6`); the selector reads from the snapshot, not by re-calling `available()` per recipe. The transform does the same — `tests/adv/test_engine_availability_snapshot.py` (S3-07) covers the invariant; this story does not re-test it but verifies its consumption path is wired (one unit test in this story reads engine availability from a passed snapshot, not by calling `available()`).
- [ ] `tests/unit/recipes/engines/test_openrewrite_stub.py` ships ≥ 3 tests (per High-level-impl Step 6 *Done criteria*): smoke recipe success when `java` is present + jar digest matches; `available() == False` when `java` is missing (`shutil.which` patched); `available() == False` when jar digest mismatches (digest catalog patched).
- [ ] `tests/integration/test_remediate_openrewrite_stub_e2e.py` runs the full `codegenie remediate <repo> --cve <id> --engine=openrewrite` happy path on a CI-matrix entry with `java` available; **CI-matrix-skipped** on runners without `java` via `pytest.skip("java not available; matrix entry skipped")` with skip reason logged structurally (skip reason recorded per Step 6 done criteria).
- [ ] `tests/adv/test_openrewrite_stub_isolation.py` pins the network-none isolation invariant: a fake recipe attempts to resolve a Maven Central host (e.g., `repo1.maven.org`); the run **must fail with a connect-refused/DNS-blocked signature** that confirms `network="none"` was honored; and the JVM **must not write any file outside the worktree** (verified by snapshotting `tmp_path` and the entire repo root before/after; only the worktree directory contents may diff).
- [ ] All Step 6 code passes `ruff check`, `ruff format --check`, `mypy --strict`, `pytest`. Coverage for `recipes/engines/openrewrite_stub.py` and `tools/openrewrite.py` ≥ 90% line / 80% branch per cross-cutting "Coverage ratchets" in `stories/README.md §"Cross-cutting concerns"`.
- [ ] Phase-0 `fence` job (extended in S1-09 to `transforms/` + `recipes/`) keeps green; this story imports no LLM SDK under `recipes/engines/openrewrite_stub.py`.

## Implementation outline

The bundle splits into six deliverables. Land them in this order so each layer's tests have a green dependency:

1. **Pin the jar.**
   - Place the pinned self-contained jar at `tools/openrewrite/<digest>.jar` (off `src/`, like Phase 2's `tools/digests.yaml` pattern). The exact upstream artifact (or internal-build artifact) is the implementer's choice per Open Question #1; the only invariant is *self-contained* — no Maven resolution at runtime.
   - Extend `src/codegenie/catalogs/tools/digests.yaml` with an `openrewrite-jar` entry. Jars are JVM-portable; a single `sha256:` value is sufficient. Document the platform-key departure (vs `linux_amd64`/`darwin_arm64`) in the catalog leading comment and in `_schema.json` (allow either `{linux_amd64, darwin_arm64}` or `{all}` shape for this entry only — keep the schema additive).
   - Update `scripts/check_tool_digests.py` (Phase 2 S1-08) to include `openrewrite-jar` in the verifier loop **only** when the jar file exists on disk; absence on a runner without `--engine=openrewrite` use must not red-gate CI. The wrapper raises `ToolNotFound` / `ToolDigestMismatch` at engine startup; install-gate absence is a runner config concern (mirror Phase 2 S1-08's "absent → exit 0 with warning" convention).
   - Adversarial coverage delegated to S7-02's `test_tools_digests_yaml_drift_breaks_install.py` (extended there per Step 7).

2. **Wire the wrapper.**
   - Create `src/codegenie/tools/openrewrite.py` mirroring `src/codegenie/tools/ncu.py` (S3-02) shape: a `run(...)` function plus a Pydantic `OpenRewriteResult(stdout: str, stderr: str, exit_code: int, wall_ms: int, tool_digest: str)`.
   - The wrapper reads the jar digest via `tools.digests.get("openrewrite-jar")` and **fails loud** with `ToolDigestMismatch` if the on-disk jar's SHA-256 disagrees — this is the digest-check seam that `OpenRewriteEngineStub.available()` re-uses (factor it as `_jar_digest_matches() -> bool`).
   - Subprocess invocation: `["java", f"-Xmx{heap}", "-jar", str(jar_path), recipe_id]`. cwd = worktree. Route through `exec.run_in_sandbox(network="none", env_strip=ALL_CREDS, profile="default", wall_seconds=wall_seconds)`.
   - Configuration: load `recipes/openrewrite-stub/config.yaml` at module import via `safe_yaml.load`; expose `_CONFIG: MappingProxyType` with `heap`, `wall_seconds`. Per Open Question #5: `heap="2g"`, `wall_seconds=300`.

3. **Wire the engine.**
   - Create `src/codegenie/recipes/engines/openrewrite_stub.py`. Class `OpenRewriteEngineStub(RecipeEngine)` per S1-03's ABC. `name = "openrewrite"`. Register via `@register_engine` so the import-time registry picks it up (same pattern as `NcuRecipeEngine` in S3-07).
   - `available(self) -> bool`: `shutil.which("java") is not None and tools.openrewrite._jar_digest_matches()`. Both branches checked.
   - `apply(self, recipe: Recipe, worktree: Path, ctx: ApplyContext) -> RecipeApplication`: delegate to `tools.openrewrite.run(recipe.params["recipe_id"], worktree, run_id=ctx.run_id)`; map result → `RecipeApplication(exit_code, stdout_tail, stderr_tail, wall_ms)`; on non-zero, return rather than raise (the transform inspects `exit_code` and emits `confidence: low, errors=[engine.stderr first 1KB]` per `phase-arch-design.md §"Component design" #2b` *Failure behavior*).
   - Engine is **stateless given `ApplyContext`** (`phase-arch-design.md §"Component design" #2b` *Internal design*). No instance state survives across `apply()` calls.

4. **Ship the smoke recipe.**
   - `src/codegenie/recipes/catalog/openrewrite-stub/<recipe-id>.yaml` — the single shipped recipe. Final choice per Open Question #1. Schema fields per `phase-arch-design.md §"Component design" #3` `Recipe` model: `id`, `engine: openrewrite`, `ecosystem: npm`, `kind: version_bump`, `applies_to: {ecosystem, languages, package_glob, cve_patterns, semver_range_predicate}`, `params: {recipe_id: <jar-internal-id>, ...}`, `declared_inputs`, `digest: sha256:...`, `priority: 200` (lower priority than `ncu` recipes so it never auto-selects without explicit `--engine=openrewrite` filtering; the selector already filters by engine choice but the priority offset is belt-and-suspenders).
   - `src/codegenie/recipes/catalog/openrewrite-stub/config.yaml` — JVM heap + wall-clock + any per-recipe knobs.
   - Compute the recipe YAML's SHA-256 and append to `src/codegenie/recipes/digests.yaml` (S3-04). The recipe loader (S3-05/S3-06) refuses unpinned recipes via `RecipeNotInDigestManifest`; CI gate `recipes_digests_verify` (S7-07) enforces drift refusal.

5. **Plumb `--engine=openrewrite` end-to-end.**
   - S5-05 already lands the `--engine={ncu,openrewrite}` Click option. Verify in this story that the choice flows: `cli/remediate.py` → `RemediationOrchestrator` (S5-03) → `RecipeSelector.select` (S3-06) where it filters out non-matching engines → `NpmPackageUpgradeTransform.apply` (S5-01) which calls `engine_registry.get(recipe.engine).apply(...)`.
   - Tool-readiness check: when `--engine=openrewrite`, the CLI's startup check verifies `java` is on `$PATH`. **Do not** fail-loud at the CLI layer; let the orchestrator reach the selector so the operator sees the structured `no_engine` signal. The CLI banner (stderr) and exit-code mapping (exit 4 `no_recipe`) carry the operator-facing message. (Honest-failure invariant per cross-cutting concerns; mirrors `gate.signal_escalate` discipline of refusing silent widening.)
   - Engine-availability snapshot capture (Gap 6): the orchestrator (S5-03) captures `engine_availability: dict[str, bool]` once at entry by iterating the engine registry and calling each `available()`. This story's engine slots into that snapshot; verify via a unit test that the engine's `apply()` is reachable when the snapshot says `{"openrewrite": True}` and that the selector emits `reason="no_engine"` when the snapshot says `{"openrewrite": False}`.

6. **Write the tests.** Single test file per category. Bundling rationale per Step 6 framing: one focused TDD red test file covers the engine-class unit tests; the smoke recipe E2E and the isolation adversarial live in their own files but are written together because the isolation file shares fixtures with the E2E happy path (same fixture repo, opposite assertions).

## TDD plan — red / green / refactor

### Red — write the failing tests first

Three test files. Land all three as failing in the first commit; the green wave lands the engine + wrapper + recipe.

**File 1:** `tests/unit/recipes/engines/test_openrewrite_stub.py` — the engine's three-test minimum.

```python
# Test signatures only — no implementation.

def test_available_true_when_java_and_jar_digest_match(monkeypatch, fake_jar_digest_match): ...
# Intent: with shutil.which("java") returning a non-None path AND the on-disk jar's
# SHA-256 matching tools.digests.get("openrewrite-jar"), available() returns True.
# This is the load-bearing happy path: both conditions are AND-gated.

def test_available_false_when_java_missing(monkeypatch): ...
# Intent: pin the registered-but-unavailable invariant. shutil.which("java") is patched
# to return None. available() must return False without raising. The selector consumer
# (S3-06) then emits RecipeSelection(reason="no_engine") — verified in the integration
# test file. This test is the *unit-level* pin: the engine, in isolation, must not
# raise on missing java.

def test_available_false_when_jar_digest_mismatch(monkeypatch, fake_jar_digest_mismatch): ...
# Intent: pin the digest-mismatch branch. shutil.which("java") returns a path; the
# on-disk jar bytes are tampered (test fixture writes mismatched bytes); available()
# returns False. Distinguishes the two failure modes — operator stderr banner should
# tell them which one tripped. Implementer surfaces this via a structured log event,
# not via the bool return — but the bool itself must short-circuit the selector.

def test_apply_reads_from_engine_availability_snapshot_not_by_recalling_available(monkeypatch): ...
# Intent: pin Gap-6 invariant from phase-arch-design.md. The transform/coordinator
# passes engine_availability snapshot into ApplyContext; the engine's apply() does
# NOT re-call self.available() — environmental flux mid-run cannot change the
# selection. Patch shutil.which to flip between True/False mid-test; apply() result
# must be invariant.

def test_apply_returns_recipe_application_on_nonzero_exit_does_not_raise(monkeypatch, fake_subprocess_nonzero): ...
# Intent: pin failure-behavior contract from phase-arch-design.md §"Component design"
# #2b "Failure behavior". Engine non-zero exit during apply() returns
# RecipeApplication(exit_code=N, stderr_tail=...) — transform inspects.
```

**File 2:** `tests/integration/test_remediate_openrewrite_stub_e2e.py` — the smoke recipe happy path E2E.

```python
import pytest
import shutil

@pytest.mark.skipif(shutil.which("java") is None, reason="java not available; matrix entry skipped")
def test_remediate_openrewrite_stub_happy_path(tmp_path, express_bundle_fixture, pinned_cve_snapshot): ...
# Intent: end-to-end test of `codegenie remediate <repo> --cve <id> --engine=openrewrite`
# on a Node.js fixture (express-shaped — bundle restored from tests/fixtures/repos_bundles/
# per S7-01) with a known CVE. Asserts: exit 0; .codegenie/remediation/<run-id>/
# branch was written; the diff file exists; the audit chain includes a recipe.apply
# event with engine="openrewrite"; the engine_availability snapshot in
# remediation-report.yaml shows {"openrewrite": true, "ncu": true}. Skipped on
# runners without java; skip reason logged structurally per Step 6 done criteria.

@pytest.mark.skipif(shutil.which("java") is None, reason="java not available; matrix entry skipped")
def test_remediate_openrewrite_explicit_engine_overrides_default_ncu(tmp_path, express_bundle_fixture): ...
# Intent: when --engine=openrewrite is passed AND the catalog has both an ncu recipe
# and an openrewrite recipe matching the advisory, the selector picks the openrewrite
# recipe — not the higher-priority ncu one. Pins the operator-opt-in invariant: the
# flag is the explicit signal, not auto-selection on availability.

def test_remediate_openrewrite_no_engine_when_java_missing(tmp_path, express_bundle_fixture, monkeypatch): ...
# Intent: pin the registered-but-unavailable end-to-end behavior. Patch
# shutil.which("java") to None at orchestrator entry. CLI exits 4 (no_recipe);
# the remediation-report.yaml's recipe_selection.reason == "no_engine"; diagnostics
# carry {"engine": "openrewrite", "available": False}; stderr banner explains
# "java not available — install java 17+ or drop --engine=openrewrite".
# This is the load-bearing "honest failure" pin — no silent fallback to ncu.
```

**File 3:** `tests/adv/test_openrewrite_stub_isolation.py` — the network-none + filesystem-isolation adversarial.

```python
import pytest
import shutil

@pytest.mark.skipif(shutil.which("java") is None, reason="java not available")
def test_openrewrite_stub_cannot_reach_maven_central(tmp_path, malicious_recipe_resolving_maven): ...
# Intent: pin ADR-0003's "no Maven Central reach-through" invariant. A test-only
# malicious recipe attempts to resolve a maven-shaped host (e.g., repo1.maven.org
# via DNS or HTTP from inside the JVM). With network="none" enforced by the
# sandbox, the JVM must observe a connect-refused / DNS-blocked signature in stderr.
# Failure mode this test exists to catch: a future implementer forgets the
# network="none" arg and the JVM transparently resolves maven artifacts at runtime,
# silently breaking the recipes-as-data invariant. Pins network="none" by
# asserting on the failure shape, not by asserting on the absence of a network
# call (which would be unfalsifiable).

@pytest.mark.skipif(shutil.which("java") is None, reason="java not available")
def test_openrewrite_stub_writes_only_inside_worktree(tmp_path, express_bundle_fixture): ...
# Intent: pin the "no file written outside worktree" invariant (Step 6 done criteria;
# phase-arch-design.md §"Component design" #2b). Snapshot the entire repo root and
# tmp_path before invoking the engine; snapshot again after; assert that the diff
# is contained to the worktree subdirectory and the .codegenie/remediation/<run-id>/
# subtree. Any file created outside (e.g., a JVM dump in $HOME, a Maven local
# cache write under ~/.m2) fails the test. Failure mode this catches: a JVM
# implementation that writes to ~/.m2 or System.getProperty("user.home") for
# even the offline path silently escapes the sandbox's filesystem boundary.

@pytest.mark.skipif(shutil.which("java") is None, reason="java not available")
def test_openrewrite_stub_honors_wall_clock_budget(tmp_path, slow_recipe_fixture): ...
# Intent: pin Open Question #5's 300 s wall budget. A test-only recipe that
# sleeps in its main method past 300 s must be killed; wrapper returns
# RecipeApplication(exit_code=124 or equivalent timeout signal); transform
# emits confidence: low. Failure mode: a future config change relaxes the wall
# budget silently and a slow OpenRewrite recipe DoSes the orchestrator.

@pytest.mark.skipif(shutil.which("java") is None, reason="java not available")
def test_openrewrite_stub_subprocess_env_is_credential_stripped(tmp_path, env_with_creds): ...
# Intent: pin env_strip=ALL_CREDS invariant. Pre-set HOME, AWS_*, GITHUB_TOKEN,
# NPM_TOKEN, MAVEN_OPTS in the test process env; the JVM subprocess (probed via
# a test-only recipe that dumps System.getenv() to stdout) must NOT see any of
# them. Pins the wrapper's routing through exec.run_in_sandbox(env_strip=ALL_CREDS).
# Failure mode: future refactor passes env=os.environ directly to subprocess and
# leaks credentials to the JVM.
```

Run all three; confirm they fail with `ModuleNotFoundError` (engine class not present), `RecipeNotInDigestManifest` (recipe not pinned), or `FileNotFoundError` (jar not pinned). Commit as red marker.

### Green — make them pass

Land the deliverables in the order listed under "Implementation outline" (jar + digest catalog → wrapper → engine class → smoke recipe + config + digest pin → CLI plumbing verification). Each commit narrowly targets one deliverable; the test file specific to that layer should go green at the matching commit.

### Refactor — clean up

- The jar-digest-check seam (`tools.openrewrite._jar_digest_matches()`) is the **single source of truth** for digest verification; the engine's `available()` and the wrapper's pre-invocation check both call this seam — do not duplicate the SHA-256 computation.
- The smoke recipe's `<recipe-id>.yaml` leading comment documents the Open-Question-#1 choice (upstream OpenRewrite recipe name or internal recipe ID) and links to the ADR-0003 amendment if the choice deviates from `org.openrewrite.npm.UpgradeDependencyVersion`.
- The config YAML's leading comment documents Open Question #5's resolution (`heap="2g"`, `wall_seconds=300`); tunables are typed `Final`.
- `OpenRewriteEngineStub` is stateless — no instance-level caches. The digest-check result is **not** cached; checks run at `available()` call time. (`available()` itself is only called once per `remediate` invocation by the orchestrator snapshot capture, so caching is unnecessary.)
- Engine registration: `@register_engine("openrewrite")` at module bottom (mirroring `NcuRecipeEngine`); the registry is import-time populated.
- The wrapper's subprocess argv is a `tuple[str, ...]` constant assembled once per call; no `shell=True`; no environment merging beyond the sandbox layer.
- The fence (S1-09) check covers `recipes/engines/openrewrite_stub.py`; verify by running `ruff check --select TID` (or whatever the fence's tooling is) locally before push.

## Files to touch

| Path | Why |
|---|---|
| `tools/openrewrite/<digest>.jar` | New — pinned self-contained jar artifact (out-of-`src/`, per Phase 2 `tools/digests.yaml` pattern) |
| `src/codegenie/tools/openrewrite.py` | New — typed wrapper; `run(...) -> OpenRewriteResult`; routes through `exec.run_in_sandbox(network="none")`; jar-digest seam |
| `src/codegenie/recipes/engines/openrewrite_stub.py` | New — `OpenRewriteEngineStub(RecipeEngine)`; `available()` + `apply()`; `@register_engine("openrewrite")` |
| `src/codegenie/recipes/catalog/openrewrite-stub/<recipe-id>.yaml` | New — single smoke recipe; engine="openrewrite"; digest-pinned |
| `src/codegenie/recipes/catalog/openrewrite-stub/config.yaml` | New — JVM heap + wall-clock config |
| `src/codegenie/recipes/digests.yaml` | Extend — append smoke recipe's SHA-256 |
| `src/codegenie/catalogs/tools/digests.yaml` | Extend — append `openrewrite-jar: sha256:...` (jar-portable; single platform-key) |
| `src/codegenie/catalogs/tools/_schema.json` | Minor extension — allow either per-platform keys OR `{all}` for jar entries |
| `scripts/check_tool_digests.py` | Extend — include `openrewrite-jar` in verifier loop (absent → exit 0 warn, per S1-08 convention) |
| `src/codegenie/cli/remediate.py` | Verify `--engine=openrewrite` plumbing; add structured stderr banner on `reason="no_engine"` exit |
| `tests/unit/recipes/engines/test_openrewrite_stub.py` | New — ≥ 5 unit tests (Step 6 done criteria minimum is 3; this file lands 5 covering both `available()` branches + snapshot-consumption + apply-failure-shape) |
| `tests/integration/test_remediate_openrewrite_stub_e2e.py` | New — ≥ 3 integration tests; CI-matrix-skipped on runners without `java` (skip reason logged) |
| `tests/adv/test_openrewrite_stub_isolation.py` | New — ≥ 4 adversarial tests covering network-none, filesystem-isolation, wall-clock, env-strip |

## Out of scope

- **Maven mirror + signed-manifest ceremony** — explicitly rejected in Phase 3 per ADR-0003 *Decision* §"No Maven mirror" and the design-security.md rejection trail. Any phase that needs full OpenRewrite Maven resolution surfaces a new ADR (likely Phase 7 or later).
- **Multiple OpenRewrite recipes / a recipe catalog beyond the smoke recipe** — Phase 4 and Phase 7 expand; Phase 15 authors against. This story ships **one** recipe per ADR-0003 ("coverage is intentionally narrow in v0.3.0").
- **JVM version pinning** — `java` 17+ is the documented floor in `phase-arch-design.md §"Component design" #2b` *Dependencies*; this story does **not** pin a specific JDK distribution or major version digest in `tools/digests.yaml`. If a future incompatibility surfaces, surface an amendment to ADR-0014.
- **`tools/digests.yaml` drift adversarial test for `openrewrite-jar`** — handled in S7-02 (`test_tools_digests_yaml_drift_breaks_install.py` is extended there per Step 7 done criteria; this story ships the catalog entry, not the drift gate).
- **CI matrix entry adding a `java`-enabled runner** — wire in S7-07 (CI gates step). This story ships the `@pytest.mark.skipif` guards; S7-07 ensures at least one matrix entry actually has `java` installed so the E2E + adversarial tests are non-trivially exercised in CI.
- **Phase 15 authoring loop / agent-authored OpenRewrite recipes** — Phase 15 owns. This story anchors the contract.
- **OpenRewriteEngineStub-specific `recipe-fail` audit event** — Phase-3 audit event enum (S1-07) carries the generic `recipe.apply` event with `engine` discriminator; no engine-specific event needed.
- **Engine-availability snapshot test** — owned by S3-07's `tests/adv/test_engine_availability_snapshot.py`; this story's `test_apply_reads_from_engine_availability_snapshot_not_by_recalling_available` is the engine-class-side pin only.

## Notes for the implementer

- **The point is the contract, not the catalog** (ADR-0003 *Decision* §"contract anchor, not a feature"). If the OpenRewrite npm ecosystem turns out to have no usable upstream recipe shape — and Open Question #1 hints this is plausible — rolling a minimal internal recipe under the same engine contract is the correct call. Document the choice in the recipe YAML's leading comment, the smoke recipe ADR-0003 amendment, and the catalog README. Per Rule 1 (Think Before Coding), do **not** force-fit an upstream recipe if it doesn't actually exist; surface the gap and pick the minimal-internal-recipe path.
- **Honest-failure invariant** (cross-cutting concerns in `stories/README.md`). When `--engine=openrewrite` is passed and `java` is missing, the run does **NOT** silently fall back to `ncu` — it exits 4 with `reason="no_engine"`. The operator's flag is the signal that they want OpenRewrite; respecting that signal means honestly reporting when it can't be honored, not redirecting them to the default. Per Rule 12 (Fail loud), the CLI banner explicitly tells the operator what is missing and how to fix it.
- **No re-call of `available()` at apply-time** (Gap 6). The orchestrator (S5-03) captures the engine-availability snapshot **once** at entry. Every downstream consumer reads from the snapshot. If an implementer is tempted to add a "just-to-be-safe" `if self.available()` check inside `apply()`, that is a regression — environmental flux mid-run cannot change the selection, and re-calling `available()` would make the run non-deterministic. The unit test `test_apply_reads_from_engine_availability_snapshot_not_by_recalling_available` is the load-bearing pin.
- **Jar artifact location**: the jar lives **outside `src/`** at `tools/openrewrite/<digest>.jar` to mirror Phase 2's `tools/` convention for non-Python install artifacts. The catalog (`src/codegenie/catalogs/tools/digests.yaml`) and the wrapper (`src/codegenie/tools/openrewrite.py`) are Python; the jar is a binary install artifact. Per Rule 11 (match conventions), do not move the jar under `src/` for "convenience" — `tools/` is the established home.
- **Jar size and Git LFS**: if the pinned self-contained OpenRewrite jar exceeds Git's recommended object size (50 MB warning, 100 MB error), surface to the reviewer before committing. Phase 2 ADR-0004 documents the "fetch-and-verify at install time" alternative; if applied here, document the fetch URL + verification flow in the jar's leading-comment placeholder file (`tools/openrewrite/README.md`) and update `scripts/check_tool_digests.py` to handle the fetch-and-verify path additively. Default plan is commit-directly if size ≤ 30 MB.
- **JVM cold-start cost is acceptable because the engine is opt-in.** Do **not** add a JVM daemon, JIT warmup script, or any other latency optimization in Phase 3 — they trade complexity for a path that, by design, the hot common case never takes (ADR-0003 *Tradeoffs* row 4). Per Rule 2 (Simplicity first), the JVM cold-start is what it is; the default `ncu` path remains the throughput surface.
- **The `<recipe-id>.yaml` filename**: pick the recipe id at implementation time (Open Question #1). If `UpgradeDependencyVersion`-shaped, name it `npm-upgrade-dependency-version-openrewrite-v1.yaml`. If a minimal internal recipe, name it `npm-version-bump-openrewrite-v1.yaml`. Either way, the `id` field inside the YAML matches the filename stem; the recipe digest in `recipes/digests.yaml` keys on the full path.
- **Engine name is `"openrewrite"`** — singular, lowercase, no underscores. This is the closed enum value in `Recipe.engine: Literal["ncu", "openrewrite"]` (`phase-arch-design.md §"Component design" #3`); the registry key matches; the CLI flag matches. Per Rule 7 (surface conflicts), do not introduce a third spelling (`open-rewrite`, `open_rewrite`, etc.) — the enum is closed in code at ADR-0003.
- **Snapshot-frozen ABC**: `RecipeEngine` ABC from S1-03 is snapshot-tested (CODEOWNERS-gated). This story does **not** add or modify any methods on the ABC. If `OpenRewriteEngineStub` requires a new method on the ABC, surface in PR description as a snapshot-update; require ADR-0001 amendment + snapshot regeneration in the same PR (mirrors Phase 2's `consumes_peer_outputs` discipline per cross-cutting "Snapshot-frozen ABC contracts").
- **`additionalProperties: false` discipline**: every YAML this story ships (`<recipe-id>.yaml`, `config.yaml`) has `additionalProperties: false` at every nesting level in its schema, and `schema_version: "v1"` at the root. Add an extra-field-rejection unit test to `tests/unit/recipes/engines/test_openrewrite_stub.py` confirming a `bogus_field: 1` at root is rejected at load time.
- **Coverage ratchet**: this story ships ~300 LOC of new code under `recipes/engines/` and `tools/`; CI ratchet is 90% line / 80% branch on new packages (`stories/README.md §"Cross-cutting concerns"` and S7-07's CI wire). Plan unit tests to hit both `available()` branches, both wrapper exit-code branches, and the digest-mismatch branch — that gets the new code into ratchet range comfortably.
- **Per Rule 10 (Checkpoint after every significant step)**, the recommended commit cadence is one commit per deliverable in the "Implementation outline" ordering (jar → wrapper → engine → recipe → CLI verify → tests-green-wave). Six commits give six checkpoint surfaces; the reviewer reads the diff incrementally.
- **Phase 4 / Phase 15 handoff sanity check**: the smoke recipe is the load-bearing exemplar Phase 15's agent reads when learning the OpenRewrite recipe shape. Pick a smoke recipe whose YAML structure generalizes — not one with weirdly recipe-specific params. The leading comment in the YAML calls this out so the next implementer (Phase 4 expansion, Phase 7 distroless, or Phase 15 authoring loop) knows the file is exemplary by design.
