# Story S5-01 — `NpmPackageUpgradeTransform` (`transforms/npm_package_upgrade.py`)

**Step:** Step 5 — Ship `NpmPackageUpgradeTransform`, `RemediationOrchestrator`, `PatchBranchWriter`, and the `codegenie remediate` CLI surface
**Status:** Ready
**Effort:** L
**Depends on:** S3-07 (`NcuRecipeEngine`), S3-08 (`LockfileResolver`), S3-09 (`LockfileCanonicalizer`); transitively S1-02 (`Transform` ABC), S1-05 (`ALLOWED_BINARIES`), S1-07 (audit events)
**ADRs honored:** ADR-0001, ADR-0002, ADR-0003, ADR-0006, ADR-0011, ADR-0014

## Context

This is the **only** concrete `Transform` Phase 3 ships and the integration point that proves the `Transform` ABC frozen in S1-02 works end-to-end. The transform owns the five-step worktree-level vertical slice that turns a `Recipe` + a `CveEntry` into a byte-deterministic `package-lock.json` diff: (1) `git worktree add`, (2) `RecipeEngine.apply`, (3) `LockfileResolver.run`, (4) `LockfileCanonicalizer.canonicalize`, (5) bot-identity commit + `git format-patch -1 --stdout`. Every step emits a typed audit event from S1-07; the transform itself never catches `Exception` because the orchestrator catches once per Component-design #1's failure-behavior contract.

The class is registered via `@register_transform` (S1-02) with `name = "npm_package_upgrade"`, `applies_to_tasks = ["vuln_remediation"]`, `applies_to_languages = ["javascript","typescript"]`, `requires_recipe_engines = ["ncu","openrewrite"]`. The engine-availability snapshot per Gap 6 means the transform reads engine availability from `ApplyContext`, never re-calls `RecipeEngine.available()` — the orchestrator captured that decision at entry.

The five-step flow is the contract Phase 4 wraps with RAG/LLM fallback, Phase 6 wraps with LangGraph, and Phase 9 wraps with Temporal — all additive. Any future "improvement" that collapses two of these steps into one quietly breaks every downstream extension's snapshot.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #4 NpmPackageUpgradeTransform` — full internal design, performance envelope, failure behavior, tradeoffs.
  - `../phase-arch-design.md §"Component design" #1 Transform ABC` — failure-behavior contract: transform never catches `Exception`.
  - `../phase-arch-design.md §"Process view — happy-path remediate run"` — sequence diagram showing every audit event.
  - `../phase-arch-design.md §"Data model" — TransformInput / ApplyContext / TransformOutput / RecipeApplication` — Pydantic shapes.
- **Phase ADRs:**
  - `../ADRs/0001-transform-recipe-engine-two-abc-contract.md` — `Transform` ABC contract (frozen at v0.3.0; snapshot test gates).
  - `../ADRs/0003-recipe-engine-ncu-default-openrewrite-stub-registered.md` — engine seat ordering; `requires_recipe_engines` declaration order.
  - `../ADRs/0011-lockfile-canonicalization-and-npm-digest-pin-for-deterministic-diffs.md` — the canonicalizer is load-bearing; `LC_ALL=C` + LF + top-level sort.
  - `../ADRs/0014-allowed-binaries-additions-npm-ncu-java.md` — `git`, `npm`, `ncu` allow-listed; the transform's subprocess calls must route through Phase-2 `exec.run_in_sandbox`.
- **Production ADRs:**
  - `../../../production/adrs/0006-deterministic-gather-no-llm.md` — Phase 3 extends the no-LLM invariant to `transforms/`.
  - `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — Phase 4's wrap point.
- **Source design:**
  - `../final-design.md §"Components" #4` — synth-canonicalization provenance; performance-first's `--package-lock-only` + best-practices' worktree usage.
  - `../final-design.md §"Goals" #20` — fixture-portfolio determinism canary anchored on this transform.
- **Existing code:**
  - `src/codegenie/transforms/contract.py` (S1-02) — `Transform` ABC + `@register_transform`.
  - `src/codegenie/transforms/models.py` (S1-04) — `TransformInput`, `ApplyContext`, `TransformOutput`, `RecipeApplication`.
  - `src/codegenie/recipes/contract.py` (S1-03) — `RecipeEngine` ABC.
  - `src/codegenie/recipes/engines/ncu.py` (S3-07) — default engine; reads `engine_availability` snapshot.
  - `src/codegenie/transforms/lockfile_resolver.py` (S3-08) — `LockfileResolver.run(worktree)`.
  - `src/codegenie/transforms/lockfile_canonicalizer.py` (S3-09) — `LockfileCanonicalizer.canonicalize(bytes) -> bytes`.
  - `src/codegenie/audit/events.py` (S1-07) — typed event payloads.
  - `src/codegenie/exec.py` (Phase 1; extended S1-02 Phase 2) — `run_in_sandbox`; never `subprocess.run` directly.
  - `src/codegenie/tools/digests.yaml` (S3-03) — pinned npm/ncu digests.

## Goal

Implement `src/codegenie/transforms/npm_package_upgrade.py` as the single concrete `Transform` for Phase 3 — a deterministic five-step pipeline that produces `.codegenie/remediation/<run-id>/diff/<recipe-id>.patch` from a recipe + a fresh worktree, emitting one typed audit event per step, never catching `Exception`, and reading engine availability from the snapshot in `ApplyContext` rather than re-calling `RecipeEngine.available()`.

## Acceptance criteria

- [ ] `src/codegenie/transforms/npm_package_upgrade.py` exports `NpmPackageUpgradeTransform(Transform)` decorated with `@register_transform` from S1-02.
- [ ] Class attributes verbatim: `name = "npm_package_upgrade"`, `applies_to_tasks = ("vuln_remediation",)`, `applies_to_languages = ("javascript", "typescript")`, `requires_recipe_engines = ("ncu", "openrewrite")`, `declared_inputs = (<glob list for package.json, package-lock.json, npm-shrinkwrap.json>)`.
- [ ] `applies(self, ctx: RepoContextView) -> bool` returns `True` only when `ctx.node_manifest` is present, lockfile dialect ∈ `{"npm-v1","npm-v2","npm-v3"}` (excludes `pnpm`, `yarn-classic`, `yarn-berry` — those surface as `reason="unsupported_dialect"` at the selector layer, not here).
- [ ] `run(self, input: TransformInput, ctx: ApplyContext) -> TransformOutput` implements the five-step flow in this exact order: `_add_worktree → _apply_recipe → _resolve_lockfile → _canonicalize_lockfile → _commit_and_format_patch`.
- [ ] Step 1 — `_add_worktree`: invokes `git -c core.hooksPath=/dev/null worktree add <repo>/.codegenie/remediation/<run-id>/worktree HEAD` via `exec.run_in_sandbox`; refuses if `<run-id>` already has a worktree (`WorktreeAlreadyExists`); refuses if the source repo's tree is dirty (`WorkingTreeNotClean`). Emits no audit event of its own (worktree adds are scaffolding); per-step instrumentation begins at step 2.
- [ ] Step 2 — `_apply_recipe`: reads `engine = ctx.engine_availability[input.recipe.engine].engine` (Gap 6 snapshot), calls `engine.apply(input.recipe, worktree_path, ctx)`, captures `RecipeApplication`; emits `recipe.engine.invoked` with `engine_name`, `recipe_id`, `exit_code`, `wall_ms`. On non-zero exit, returns `TransformOutput(confidence="low", errors=["recipe_failed: " + stderr_first_1KB], skipped=False, diff_path=None)` — does NOT raise.
- [ ] Step 3 — `_resolve_lockfile`: invokes `LockfileResolver.run(worktree_path)` (S3-08); emits `npm.install.run` with `mode="package_lock_only"`, `exit_code`, `wall_ms`, `egress_bytes`. On `LockfileResolveFailed` after bounded transient retries inside the resolver, returns `TransformOutput(confidence="low", errors=["lockfile_resolve_failed: " + str(exc.last_exit)], skipped=False)` — does NOT raise.
- [ ] Step 4 — `_canonicalize_lockfile`: reads worktree's `package-lock.json` bytes, invokes `LockfileCanonicalizer.canonicalize(bytes)` (S3-09), writes the canonical bytes back. The canonicalizer is pure-Python; if it raises, the transform lets it propagate (canary CI test catches this loud failure per ADR-0011).
- [ ] Step 5 — `_commit_and_format_patch`: invokes `git -c core.hooksPath=/dev/null -c commit.gpgsign=false -c user.email=codegenie-bot@codegenie.invalid -c user.name=codegenie-bot commit -am "<auto-generated message>"`; then `git -c core.hooksPath=/dev/null format-patch -1 --stdout > .codegenie/remediation/<run-id>/diff/<recipe-id>.patch`. Bot identity MUST be set via per-invocation `-c` flags, NEVER via `git config user.email/user.name`. Emits `transform.applied` with `transform_name="npm_package_upgrade"`, `files_changed_count`, `diff_bytes`, `confidence`.
- [ ] On the happy path, returns `TransformOutput(name="npm_package_upgrade", diff_path=<...>, branch_name=None, files_changed=[...], confidence="high", warnings=[], errors=[], skipped=False)`. `branch_name` is None at the transform layer — `PatchBranchWriter` (S5-04) sets it.
- [ ] The transform **never** catches `Exception` (the orchestrator catches once). The only `except` clauses permitted are typed and re-raise after wrapping into `TransformOutput.errors` for the two documented failure modes (engine non-zero exit, resolver exhaustion).
- [ ] `tests/unit/transforms/test_npm_package_upgrade.py` ships ≥ 10 tests covering: happy path golden diff, lockfile-canonicalization-golden cross-check, worktree-already-exists refusal, source-tree-dirty refusal, engine non-zero exit propagates to `confidence="low"` + `errors=["recipe_failed: ..."]`, resolver exhaustion propagates to `confidence="low"` + `errors=["lockfile_resolve_failed: ..."]`, bot committer identity verified (parsed from the produced patch), `core.hooksPath=/dev/null` honored (a hook in source tree would have written a marker file — assert absent), `commit.gpgsign=false` honored (no signature header in patch), engine availability read from snapshot (not via re-calling `available()`; mock `engine.available` to flip mid-run and assert the snapshot's value is what got used).
- [ ] `Transform.applies` snapshot from S1-02 still passes (no ABC drift).
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Write the failing tests under `tests/unit/transforms/test_npm_package_upgrade.py` (red).
2. Create `src/codegenie/transforms/npm_package_upgrade.py` skeleton with class attributes + `applies` + `run` raising `NotImplementedError`. Commit; tests still red.
3. Implement `_add_worktree` — call `exec.run_in_sandbox` with the four-flag `git worktree add`; check the destination doesn't exist; verify source repo is clean via `git status --porcelain` (empty stdout).
4. Implement `_apply_recipe` — read `ctx.engine_availability[recipe.engine]`; call `engine.apply(recipe, worktree, ctx)`; on non-zero, build `TransformOutput` with `confidence="low"` and return early.
5. Implement `_resolve_lockfile` — wrap `LockfileResolver.run(worktree)`; catch `LockfileResolveFailed` only; build `TransformOutput` failure shape.
6. Implement `_canonicalize_lockfile` — read `worktree/package-lock.json`, call `LockfileCanonicalizer.canonicalize`, write back. No error handling — let exceptions propagate (canary).
7. Implement `_commit_and_format_patch` — two `exec.run_in_sandbox` invocations with the four `-c` flags. Build the commit message from `recipe.id` + `advisory.cve_id` (deterministic — same input → same message). Write the patch file under `.codegenie/remediation/<run-id>/diff/<recipe-id>.patch`.
8. Wire audit events at the documented points (steps 2, 3, 5). Use the typed payloads from `audit/events.py` (S1-07).
9. Run pytest, ruff, mypy on touched files.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/transforms/test_npm_package_upgrade.py`.

```python
# Test signatures only — no implementation.

def test_happy_path_produces_canonical_diff_golden(tmp_path, fixture_express_bundle, ncu_engine_snapshot): ...
def test_lockfile_canonicalization_golden_matches_recorded_resolution(...): ...
def test_refuses_when_worktree_already_exists_for_run_id(tmp_path, ...): ...
def test_refuses_when_source_tree_dirty(tmp_path, ...): ...
def test_engine_non_zero_exit_returns_confidence_low_errors_recipe_failed(...): ...
def test_resolver_exhaustion_returns_confidence_low_errors_lockfile_resolve_failed(...): ...
def test_bot_committer_identity_parsed_from_patch(...): ...
def test_core_hookspath_devnull_honored_pre_commit_hook_did_not_run(...): ...
def test_commit_gpgsign_false_honored_no_signature_header_in_patch(...): ...
def test_engine_availability_read_from_snapshot_not_live_call(monkeypatch, ...): ...
def test_recipe_engine_invoked_event_emitted_once_per_run(audit_capture, ...): ...
def test_transform_applied_event_emitted_with_diff_bytes_and_files_changed(audit_capture, ...): ...
def test_transform_never_catches_bare_exception_canonicalizer_failure_propagates(...): ...
def test_applies_returns_false_for_pnpm_workspace_dialect(...): ...
def test_applies_returns_false_for_yarn_classic_dialect(...): ...
```

Run pytest; confirm all 15 fail with `NotImplementedError` or `ModuleNotFoundError`. Commit as red marker.

### Green — make it pass

Land the five private helpers + the `run` dispatcher per the implementation outline. Keep helper signatures small: each takes `(self, input, ctx, prior_step_output)` and returns either a partial `TransformOutput` (failure short-circuit) or a step-local result the next helper consumes. The dispatcher composes them in a flat sequence — no nested try/except, no early-return mazes.

Wire audit events at the three documented emit points. The golden diff test is the load-bearing canary: when it goes green, the canonicalizer + resolver + engine + bot-identity surface are all working together. If golden bytes drift, that's either an `npm` minor-version bump (rotate the fixture per S7-01) or a canonicalizer regression (debug from there).

### Refactor — clean up

- Extract the bot-identity flag tuple into a module-level constant `_GIT_BOT_FLAGS: tuple[str, ...]` reused by every `exec.run_in_sandbox` call here AND in `PatchBranchWriter` (S5-04 imports it). This is the only shared surface — define it once.
- Add a module docstring naming ADR-0001, ADR-0006 (no-retry-inside contract), ADR-0011 (canonicalization), and a one-sentence summary of each step.
- Add `mypy: strict_optional = True` if not already inherited from the package config.
- Make sure `_commit_and_format_patch` emits `transform.applied` AFTER the patch file is on disk (so an emit-then-die failure mode doesn't leave an audit event referencing a missing file).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/npm_package_upgrade.py` | New — concrete `Transform` per phase-arch §"Component design" #4 |
| `tests/unit/transforms/test_npm_package_upgrade.py` | New — ≥ 10 tests per the red plan |
| `tests/unit/transforms/fixtures/express-happy-path.bundle` | New — minimal express fixture (real fixture portfolio lands in S7-01; this is the unit-level smoke fixture) |
| `tests/unit/transforms/fixtures/recorded-canonical-diff.patch` | New — golden bytes the happy-path test asserts against |

## Out of scope

- **The orchestrator that calls this transform** — handled by S5-03. This story exposes the contract; S5-03 wires the six-call backbone.
- **The branch writer** — handled by S5-04. This transform sets `TransformOutput.branch_name = None`; the writer fills it.
- **Engine-availability snapshot construction** — handled by S5-03 (snapshot built at orchestrator entry) and S3-07 (selector populates per-engine `available()` boolean). This story only **reads** the snapshot via `ApplyContext.engine_availability`.
- **The `cache.replay` audit event** — emitted from inside `LockfileResolver` per S3-08; the transform's `npm.install.run` event is the gross-call audit, the resolver's `cache.replay` is the fine-grained replay event.
- **OpenRewrite-engine integration** — `requires_recipe_engines` declares `"openrewrite"` but the actual second engine seat lands in S6-01. The transform's flow is engine-agnostic; selecting the openrewrite engine is the selector's job (S3-06).
- **Phase-4 RAG fallback** — when no recipe matches, the transform isn't called (the selector short-circuits with `reason="catalog_miss"`). Phase 4 wraps this layer additively; this story does not anticipate the wrap.
- **`codegenie remediation gc`** — `.codegenie/remediation/<run-id>/` cleanup is documented in S7-07's runbook stub; this story leaves the directory on disk.

## Notes for the implementer

- **The transform never catches `Exception`.** Two `except` clauses are permitted: `RecipeEngineNonZeroExit` (or whatever S3-07 raises) and `LockfileResolveFailed`. Everything else propagates — the orchestrator's CLI safety net (S5-05) catches once and emits `meta.unexpected_exception`. If you find yourself adding `except Exception` to "be safe", stop — you're masking the canary the canonicalizer regression test depends on.
- **Bot identity flags are per-invocation `-c`, never `git config`.** A future contributor (or AI agent) "improving" the code to call `git config user.email codegenie-bot@codegenie.invalid` once at the top would silently rely on user-level git config and break in any container that has a different `user.name` set. The `_GIT_BOT_FLAGS` constant is the canonical surface; both this file and `branch_writer.py` (S5-04) import it. A unit test in this file AND in `test_branch_writer.py` (S5-04) parses the patch's `From:` and `Author:` lines to confirm the bot identity got through — encoded twice deliberately.
- **Engine availability is read from `ctx.engine_availability`, never via `engine.available()`.** Gap 6 in `phase-arch-design.md` is explicit: the snapshot is captured once at orchestrator entry (S5-03). If you re-call `available()` in the transform, the Temporal-Activity-replay path in Phase 9 will see different availability between selector and transform — the property test in `tests/adv/test_engine_availability_snapshot.py` (S3-07) pins this; do not break it.
- **The `--package-lock-only` paper-lockfile critique is absorbed by the install validator.** Stage 6 (`install_validator`, S4-02) runs `npm ci` and verifies the paper-lock survives a real install. The transform's job is just to produce a canonically-formatted diff; if the diff is wrong, the install validator fails closed at exit 6 — that's the safety net. Do not add an "extra `npm ci` check" inside the transform — that's the gate's job.
- **The audit event order matters.** `recipe.engine.invoked` fires after the engine returns (whether it succeeded or not); `npm.install.run` fires after the resolver returns (whether cache-hit or cache-miss); `transform.applied` fires last, after the patch file is on disk. Audit-chain readers (Phase 4) consume these in order; reordering them silently rewrites the contract.
- **The commit message must be deterministic.** Two invocations with the same `recipe.id` and `advisory.cve_id` MUST produce the same commit message — otherwise the determinism canary in S7-03 will see different SHAs across 5 runs. Suggested format: `f"chore(deps): upgrade per {recipe.id} addresses {advisory.cve_id}"` — single line, no timestamps, no run-id.
- **`exec.run_in_sandbox`'s default profile is correct here.** Step 1 (worktree add) is fs-only, no network needed. Step 2 (engine apply) is engine-dependent — `NcuRecipeEngine` declares `network="scoped" allowlist=["registry.npmjs.org"]`. Step 3 (resolver) declares the same. Steps 4–5 (canonicalize, commit, format-patch) are fs-only. Do not "simplify" by adding `network="none"` to every call — the recipe engine and resolver legitimately need scoped egress.
- **Per Rule 3 (Surgical Changes):** do not "improve" `lockfile_resolver.py` (S3-08), `lockfile_canonicalizer.py` (S3-09), or `recipes/engines/ncu.py` (S3-07) while wiring this transform. Those contracts are pinned by their own stories' tests. If a real bug in any of them blocks this story, file it; don't fix it in this PR.
